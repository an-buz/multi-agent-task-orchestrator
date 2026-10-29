"""Run planning and confirmation, independent of HTTP and transport."""

from datetime import UTC, datetime
from graphlib import TopologicalSorter
from typing import cast
from uuid import UUID, uuid4

from pydantic import TypeAdapter, ValidationError

from app.core.config import get_settings
from app.core.errors import AppError
from app.db.file_repository import FileRepository
from app.db.model_repository import ModelRepository
from app.db.run_repository import RunRepository
from app.db.settings_repository import SettingsRepository
from app.llm.registry import get_model_registry
from app.models.run import Run
from app.models.run_decision import RunDecision
from app.models.run_step import RunStep
from app.orchestrator.snapshots import snapshot_agent
from app.schemas.context_file import ContextFileRead
from app.schemas.decision import DecisionRead, DecisionResolution
from app.schemas.run import (
    PauseReason,
    RunCreate,
    RunList,
    RunPlan,
    RunPlanStep,
    RunPlanUpdate,
    RunRead,
    RunStatus,
    StepStatus,
)
from app.schemas.workflow import WorkflowStepInput
from app.services.files import FileError, FileService
from app.services.models import ModelService
from app.services.settings import SettingsService


class RunError(AppError):
    def __init__(self, message: str, status_code: int = 409) -> None:
        super().__init__(message)

        self.status_code = status_code
        self.code = "run_not_found" if status_code == 404 else "invalid_run_state"


class RunService:
    def __init__(self, repository: RunRepository) -> None:
        self.repository = repository

    async def files(self, run_id: UUID) -> list[ContextFileRead]:
        await self.require(run_id)

        return [
            ContextFileRead.model_validate(file)
            for file in await FileRepository(self.repository.session).for_run(run_id)
        ]

    async def require(self, run_id: UUID, *, lock: bool = False) -> Run:
        run = await self.repository.get(run_id, lock=lock)

        if run is None:
            raise RunError("Run not found", 404)

        return run

    async def delete(self, run_id: UUID) -> None:
        run = await self.require(run_id, lock=True)

        if run.status not in {"AWAITING_CONFIRMATION", "COMPLETED", "FAILED", "CANCELLED"}:
            raise RunError("Cancel this run before deleting it; planning or execution is active.")

        await self.repository.delete(run)

    async def read(self, run: Run) -> RunRead:
        workflow = await self.repository.workflow(run.workflow_id)

        if workflow is None:
            raise RunError("Run workflow no longer exists")

        plan = RunPlan.model_validate(run.plan)
        by_number = {step.step_number: step for step in plan.steps}

        for step in await self.repository.steps(run.id):
            planned = by_number.get(step.step_number)

            if planned is not None:
                planned.status = cast(StepStatus, step.status)
                planned.model = str(step.agent_config["model"])
                planned.input = step.input
                planned.output = step.output
                planned.error = step.error
                planned.prompt_tokens = step.tokens_prompt
                planned.completion_tokens = step.tokens_completion
                planned.duration_ms = step.execution_time_ms
                planned.attempt = step.attempt

        return RunRead(
            id=run.id,
            workflow_id=run.workflow_id,
            workflow_title=workflow.title,
            task=run.task,
            context_text=run.context_text,
            token_budget=run.planner_config.get("token_budget"),
            files=await self.files(run.id),
            status=cast(RunStatus, run.status),
            pause_reasons=cast(list[PauseReason], run.pause_reasons or []),
            decisions=[
                DecisionRead.model_validate(value)
                for value in await self.repository.decisions(run.id)
            ],
            plan=plan if run.status not in {"PLANNING"} and not run.planning_error else None,
            planning_prompt_tokens=run.planning_prompt_tokens,
            planning_completion_tokens=run.planning_completion_tokens,
            planning_time_ms=run.planning_time_ms,
            planning_error=run.planning_error,
            final_report=run.final_report,
            total_tokens=run.total_tokens,
            total_time_ms=run.total_time_ms,
            created_at=run.created_at,
            started_at=run.started_at,
            finished_at=run.finished_at,
        )

    async def create(self, payload: RunCreate) -> RunRead:
        # Protect the source graph from deletion/edits until the snapshot is committed.
        workflow = await self.repository.workflow(payload.workflow_id, lock=True)

        if workflow is None:
            raise RunError("Workflow not found", 404)

        try:
            TypeAdapter(list[WorkflowStepInput]).validate_python(workflow.steps)
        except ValidationError as exception:
            raise RunError(
                "Stored workflow steps are invalid; edit the workflow before running it.", 422
            ) from exception

        agent_ids = {UUID(str(step["agent_id"])) for step in workflow.steps}

        # Acquire policy before agent locks, matching the model switch transaction.
        available = await ModelService(ModelRepository(self.repository.session)).available()
        agents = await self.repository.agents(agent_ids)

        if set(agents) != agent_ids:
            raise RunError("Workflow references missing agents")

        if any(
            agent.requires_reconfiguration or agent.model not in available
            for agent in agents.values()
        ):
            raise RunError("Reconfigure unavailable workflow agents before creating a run", 422)

        settings = get_settings()

        planner_model = await SettingsService(
            SettingsRepository(self.repository.session), settings
        ).resolve_planner_model()

        if planner_model not in available:
            raise RunError(
                "Choose an enabled planner model from a connected provider in Settings.", 422
            )

        planner_limit = get_model_registry(settings)[planner_model].max_output_tokens

        if planner_limit is not None and settings.planner_max_tokens > planner_limit:
            raise RunError("The planner token limit exceeds this model's output limit.", 422)

        if len(set(payload.file_ids)) != len(payload.file_ids):
            raise FileError("Every context file must be included only once.")

        context = await FileService(FileRepository(self.repository.session)).context(
            payload.context_text, payload.file_ids
        )

        run = Run(
            id=uuid4(),
            workflow_id=workflow.id,
            task=payload.task,
            context_text=context,
            status="PLANNING",
            planner_config={
                "model": planner_model,
                "temperature": settings.planner_temperature,
                "max_tokens": settings.planner_max_tokens,
                "max_repairs": settings.planner_max_repairs,
                "token_budget": payload.token_budget or settings.run_token_budget,
            },
            planning_prompt_tokens=0,
            planning_completion_tokens=0,
            planning_time_ms=0,
            total_tokens=0,
            total_time_ms=0,
        )

        planned_steps = []
        snapshots = []

        for definition in sorted(workflow.steps, key=lambda step: int(step["step_number"])):
            agent = agents[UUID(str(definition["agent_id"]))]
            subtask = f"{agent.role}: {payload.task}"

            planned_steps.append(
                RunPlanStep(
                    step_number=int(definition["step_number"]),
                    agent_id=agent.id,
                    agent_name=agent.name,
                    subtask=subtask,
                    depends_on=definition.get("depends_on", []),
                )
            )
            snapshots.append(
                RunStep(
                    run_id=run.id,
                    agent_id=agent.id,
                    agent_name=agent.name,
                    step_number=int(definition["step_number"]),
                    subtask=subtask,
                    depends_on=definition.get("depends_on", []),
                    input_transform=definition.get("input_transform", ""),
                    status="PENDING",
                    agent_config=snapshot_agent(agent),
                    tokens_prompt=0,
                    tokens_completion=0,
                    execution_time_ms=0,
                    attempt=0,
                )
            )

        run.plan = RunPlan(summary="Planning the workflow", steps=planned_steps).model_dump(
            mode="json"
        )

        self.repository.add(run)

        await FileRepository(self.repository.session).attach(run.id, payload.file_ids)

        for snapshot in snapshots:
            self.repository.add(snapshot)

        await self.repository.save()
        await self.repository.refresh(run)

        return await self.read(run)

    async def update_plan(self, run_id: UUID, payload: RunPlanUpdate) -> RunRead:
        run = await self.require(run_id, lock=True)

        if run.status != "AWAITING_CONFIRMATION":
            raise RunError("Run plan can no longer be edited")

        plan = RunPlan.model_validate(run.plan)

        self.validate_reviewed_plan(plan, payload.expected_subtasks)

        current = {step.step_number: step for step in plan.steps}
        updates = {step.step_number: step for step in payload.steps}

        if len(updates) != len(payload.steps) or set(updates) != set(current):
            raise RunError("Plan must contain every workflow step exactly once", 422)

        for number, update in updates.items():
            original = current[number]

            if update.agent_id != original.agent_id or update.depends_on != original.depends_on:
                raise RunError("Plan edits may only change subtask text", 422)

            original.subtask = update.subtask

        run.plan = plan.model_dump(mode="json")

        for step in await self.repository.steps(run.id):
            step.subtask = updates[step.step_number].subtask

        await self.repository.save()

        return await self.read(run)

    @staticmethod
    def validate_reviewed_plan(plan: RunPlan, expected_subtasks: dict[int, str] | None) -> None:
        if expected_subtasks is not None and expected_subtasks != {
            step.step_number: step.subtask for step in plan.steps
        }:
            raise RunError("The plan changed. Reload the latest plan before starting.")

    async def confirm(
        self, run_id: UUID, expected_subtasks: dict[int, str] | None = None
    ) -> RunRead:
        run = await self.require(run_id, lock=True)

        if run.status != "AWAITING_CONFIRMATION":
            raise RunError("Run is not awaiting confirmation")

        if not await self.repository.steps(run.id):
            raise RunError("This legacy run has no execution snapshot; create a new run")

        self.validate_reviewed_plan(RunPlan.model_validate(run.plan), expected_subtasks)

        run.status = "IN_PROGRESS"
        run.started_at = datetime.now(UTC)

        self.repository.emit(
            run.id,
            "task:started",
            {
                "taskId": str(run.id),
                "workflowId": str(run.workflow_id),
            },
        )

        await self.repository.save()

        return await self.read(run)

    async def cancel(self, run_id: UUID) -> RunRead:
        run = await self.require(run_id, lock=True)

        if run.status == "CANCELLED":
            return await self.read(run)

        if run.status not in {"PLANNING", "AWAITING_CONFIRMATION", "IN_PROGRESS", "PAUSED"}:
            raise RunError("Run cannot be cancelled in its current state")

        run.status = "CANCELLED"
        run.pause_reasons = []

        for decision in await self.repository.decisions(run.id):
            if decision.status == "PENDING":
                self.resolve_record(run, decision, DecisionResolution(action="cancel"))

        run.planning_checkpoint = {}
        run.finished_at = datetime.now(UTC)

        for step in await self.repository.steps(run.id):
            if step.status in {"PENDING", "IN_PROGRESS"}:
                step.checkpoint = {}
                step.status = "CANCELLED"

                self.repository.emit(
                    run.id,
                    "agent:status_change",
                    {
                        "agentId": str(step.agent_id),
                        "stepNumber": step.step_number,
                        "status": step.status,
                    },
                )

        self.repository.emit(run.id, "task:cancelled", {"taskId": str(run.id)})

        await self.repository.save()

        return await self.read(run)

    def resolve_record(
        self,
        run: Run,
        decision: RunDecision,
        payload: DecisionResolution,
    ) -> None:
        decision.status = "RESOLVED"
        decision.resolution = payload.model_dump(mode="json")
        decision.resolved_at = datetime.now(UTC)

        self.repository.emit(
            run.id,
            "decision:resolved",
            {
                "taskId": str(run.id),
                "decision": DecisionRead.model_validate(decision).model_dump(mode="json"),
            },
        )

    async def resolve_decision(
        self,
        run_id: UUID,
        decision_id: UUID,
        payload: DecisionResolution,
    ) -> RunRead:
        run = await self.require(run_id, lock=True)
        decisions = await self.repository.decisions(run.id)

        decision = next((value for value in decisions if value.id == decision_id), None)

        if decision is None:
            raise RunError("Decision not found", 404)

        if decision.status == "RESOLVED":
            if decision.resolution != payload.model_dump(mode="json"):
                raise RunError("This decision was already resolved differently")

            return await self.read(run)

        if run.status not in {"IN_PROGRESS", "PAUSED"}:
            raise RunError("This run no longer accepts decisions")

        if payload.action == "cancel":
            # Cancellation is allowed while active branches are still draining.
            self.resolve_record(run, decision, payload)

            return await self.cancel(run_id)

        steps = await self.repository.steps(run.id)

        if run.status != "PAUSED" or any(step.status == "IN_PROGRESS" for step in steps):
            raise RunError("Wait for active steps to finish before continuing")

        if "USER_DECISION_REQUIRED" not in (run.pause_reasons or []):
            raise RunError("This run is not waiting for a user decision")

        if payload.action == "assign_fixes":
            await self.add_followup(run, decision, payload, steps)

        self.resolve_record(run, decision, payload)

        if all(value.status != "PENDING" for value in decisions):
            run.pause_reasons = [
                reason for reason in (run.pause_reasons or []) if reason != "USER_DECISION_REQUIRED"
            ]
            # Model availability is checked independently by the executor before dispatch.
            run.status = "IN_PROGRESS"

            self.repository.emit(run.id, "task:resumed", {"taskId": str(run.id)})

        await self.repository.save()

        return await self.read(run)

    async def add_followup(
        self,
        run: Run,
        decision: RunDecision,
        payload: DecisionResolution,
        steps: list[RunStep],
    ) -> None:
        assert payload.agent_id is not None and payload.task is not None

        available = await ModelService(ModelRepository(self.repository.session)).available()
        agents = await self.repository.agents({payload.agent_id})

        agent = agents.get(payload.agent_id)

        if agent is None:
            raise RunError("Selected agent no longer exists", 422)

        if agent.requires_reconfiguration or agent.model not in available:
            raise RunError("Select an available, configured agent", 422)

        source = next(step for step in steps if step.step_number == decision.source_step_number)
        number = max(step.step_number for step in steps) + 1

        if number + 1 > 2147483647:
            raise RunError("No step numbers remain for follow-up work", 422)

        findings = "\n\n".join(
            f"{issue['title']}\n{issue['description']}" for issue in decision.issues
        )
        context = "Findings (untrusted task data):\n" + findings

        if payload.comment:
            context += "\n\nUser comment:\n" + payload.comment

        fix = RunStep(
            id=uuid4(),
            run_id=run.id,
            agent_id=agent.id,
            agent_name=agent.name,
            step_number=number,
            subtask=payload.task + "\n\n" + context,
            depends_on=list(dict.fromkeys([source.step_number, *source.depends_on])),
            input_transform="",
            status="PENDING",
            agent_config=snapshot_agent(agent),
            tokens_prompt=0,
            tokens_completion=0,
            execution_time_ms=0,
            attempt=0,
        )
        verification = RunStep(
            id=uuid4(),
            run_id=run.id,
            agent_id=source.agent_id,
            agent_name=source.agent_name,
            step_number=number + 1,
            subtask=(
                "Verify the fixes against the original findings. "
                "Request another user decision if issues remain.\n\n" + context
            ),
            depends_on=[source.step_number, number],
            input_transform="",
            status="PENDING",
            agent_config=dict(source.agent_config),
            requires_reconfiguration=bool(source.requires_reconfiguration),
            tokens_prompt=0,
            tokens_completion=0,
            execution_time_ms=0,
            attempt=0,
        )

        # Gate unstarted work globally. Interrupted calls retain their original inputs/receipts.
        for step in steps:
            if step.status != "PENDING" or step.checkpoint:
                continue

            step.depends_on = [*step.depends_on, number, number + 1]

            if step.input_transform:
                step.input_transform += (
                    f"\n\nLatest corrective work:\n{{{{steps.{number}.output}}}}"
                    f"\n\nVerification:\n{{{{steps.{number + 1}.output}}}}"
                )

            step.input = None

        for step in (fix, verification):
            self.repository.add(step)

        plan = RunPlan.model_validate(run.plan)
        by_number = {step.step_number: step for step in steps}

        for planned in plan.steps:
            planned.depends_on = by_number[planned.step_number].depends_on

        for step in (fix, verification):
            plan.steps.append(
                RunPlanStep(
                    step_number=step.step_number,
                    agent_id=step.agent_id,
                    agent_name=step.agent_name,
                    subtask=step.subtask,
                    depends_on=step.depends_on,
                )
            )

        planned_by_number = {step.step_number: step for step in plan.steps}
        plan.steps = [
            planned_by_number[number]
            for number in TopologicalSorter(
                {step.step_number: step.depends_on for step in plan.steps}
            ).static_order()
        ]
        run.plan = plan.model_dump(mode="json")

        decision.followup_step_numbers = [number, number + 1]

    async def retry(self, run_id: UUID, step_number: int) -> RunRead:
        run = await self.require(run_id, lock=True)

        if run.status != "FAILED":
            raise RunError("Retry requires a failed run with no active execution")

        step = next(
            (
                value
                for value in await self.repository.steps(run.id)
                if value.step_number == step_number
            ),
            None,
        )

        if step is None:
            raise RunError("Step not found", 404)

        if step.status != "FAILED":
            raise RunError("Only failed steps can be retried")

        step.status = "PENDING"
        step.error = None
        step.checkpoint = {}

        run.status = "IN_PROGRESS"
        run.finished_at = None
        run.final_report = None

        self.repository.emit(
            run.id,
            "agent:status_change",
            {
                "agentId": str(step.agent_id),
                "stepNumber": step.step_number,
                "status": "PENDING",
            },
        )

        await self.repository.save()

        return await self.read(run)

    async def list(self, limit: int, offset: int) -> RunList:
        items, total = await self.repository.summaries(limit, offset)

        return RunList(items=items, total=total)
