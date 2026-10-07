"""Run planning and confirmation, independent of HTTP and transport."""

from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

from app.core.errors import AppError
from app.db.run_repository import RunRepository
from app.models.run import Run
from app.models.run_step import RunStep
from app.schemas.run import RunCreate, RunPlan, RunPlanStep, RunPlanUpdate, RunRead, StepStatus


class RunError(AppError):
    def __init__(self, message: str, status_code: int = 409) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = "run_not_found" if status_code == 404 else "invalid_run_state"


class RunService:
    def __init__(self, repository: RunRepository) -> None:
        self.repository = repository

    async def require(self, run_id: UUID, *, lock: bool = False) -> Run:
        run = await self.repository.get(run_id, lock=lock)
        if run is None:
            raise RunError("Run not found", 404)
        return run

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
            status=run.status,
            plan=plan,
            final_report=run.final_report,
            total_tokens=run.total_tokens,
            total_time_ms=run.total_time_ms,
            created_at=run.created_at,
            started_at=run.started_at,
            finished_at=run.finished_at,
        )

    async def create(self, payload: RunCreate) -> RunRead:
        workflow = await self.repository.workflow(payload.workflow_id)
        if workflow is None:
            raise RunError("Workflow not found", 404)
        agent_ids = {UUID(str(step["agent_id"])) for step in workflow.steps}
        agents = await self.repository.agents(agent_ids)
        if set(agents) != agent_ids:
            raise RunError("Workflow references missing agents")
        run = Run(
            id=uuid4(),
            workflow_id=workflow.id,
            task=payload.task,
            context_text=payload.context_text,
            status="AWAITING_CONFIRMATION",
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
                    agent_config={
                        "system_prompt": agent.system_prompt,
                        "model": agent.model,
                        "temperature": agent.temperature,
                        "max_tokens": agent.max_tokens,
                        "context_window": agent.context_window,
                        "tools": agent.tools,
                    },
                    tokens_prompt=0,
                    tokens_completion=0,
                    execution_time_ms=0,
                    attempt=0,
                )
            )
        run.plan = RunPlan(
            summary=f"Mock plan for workflow: {workflow.title}", steps=planned_steps
        ).model_dump(mode="json")
        self.repository.add(run)
        for snapshot in snapshots:
            self.repository.add(snapshot)
        self.repository.emit(run.id, "plan:ready", {"plan": run.plan})
        await self.repository.save()
        await self.repository.refresh(run)
        return await self.read(run)

    async def update_plan(self, run_id: UUID, payload: RunPlanUpdate) -> RunRead:
        run = await self.require(run_id, lock=True)
        if run.status != "AWAITING_CONFIRMATION":
            raise RunError("Run plan can no longer be edited")
        plan = RunPlan.model_validate(run.plan)
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

    async def confirm(self, run_id: UUID) -> RunRead:
        run = await self.require(run_id, lock=True)
        if run.status != "AWAITING_CONFIRMATION":
            raise RunError("Run is not awaiting confirmation")
        if not await self.repository.steps(run.id):
            raise RunError("This legacy run has no execution snapshot; create a new run")
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
        if run.status not in {"AWAITING_CONFIRMATION", "IN_PROGRESS"}:
            raise RunError("Run cannot be cancelled in its current state")
        run.status = "CANCELLED"
        run.finished_at = datetime.now(UTC)
        for step in await self.repository.steps(run.id):
            if step.status in {"PENDING", "IN_PROGRESS"}:
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

    async def list(self, limit: int, offset: int) -> dict[str, object]:
        runs, total = await self.repository.list(limit, offset)
        return {"items": [await self.read(run) for run in runs], "total": total}
