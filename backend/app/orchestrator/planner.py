"""Provider-backed planning with a fixed DAG and cancellable persisted lifecycle."""

import asyncio
import json
from collections.abc import Awaitable, Callable
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime
from time import perf_counter
from typing import Any
from uuid import UUID

import structlog
from pydantic import ValidationError

from app.core.config import get_settings
from app.db.run_repository import RunRepository
from app.llm.context import ContextTooLarge, check_context
from app.llm.planning import PLANNER_SYSTEM_PROMPT, PlannedWorkflow
from app.llm.provider import IncompleteLLMResponse, LLMProvider, LLMResponse
from app.llm.providers import create_provider
from app.llm.retry import llm_retrying
from app.models.run import Run
from app.models.run_step import RunStep
from app.orchestrator.executor import DAGExecutor
from app.schemas.run import RunPlan

logger = structlog.get_logger()


@dataclass
class PlanningResult:
    plan: RunPlan | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    duration_ms: int = 0
    error: dict[str, str] | None = None


class LLMPlanner:
    def __init__(self, provider_factory: Callable[[str], LLMProvider] = create_provider) -> None:
        self.provider_factory = provider_factory

    async def generate(
        self,
        task: str,
        context: str,
        config: dict[str, Any],
        plan: RunPlan,
        roles: dict[int, dict[str, Any]],
        *,
        run_id: UUID | None = None,
        checkpoint: dict[str, Any] | None = None,
        on_checkpoint: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
    ) -> PlanningResult:
        started = perf_counter()
        result = PlanningResult()
        saved = deepcopy(checkpoint or {})
        turns: list[dict[str, Any]] = saved.get("turns", [])
        previous_duration = int(saved.get("duration_ms", 0))
        provider: LLMProvider | None = None
        try:
            if saved.get("provider_pending"):
                result.prompt_tokens = int(saved.get("prompt_tokens", 0))
                result.completion_tokens = int(saved.get("completion_tokens", 0))
                result.error = {
                    "code": "llm_execution_interrupted",
                    "message": "Planning provider outcome is unknown. Create a new run explicitly.",
                }
                return result
            model = str(config["model"])
            request = {
                "task": task,
                "context": context,
                "steps": [
                    {
                        "step_number": step.step_number,
                        "agent_id": str(step.agent_id),
                        "depends_on": step.depends_on,
                        "agent_name": step.agent_name,
                        "role": roles[step.step_number].get("role", step.agent_name),
                        "tools": roles[step.step_number].get("tools", []),
                    }
                    for step in plan.steps
                ],
            }
            for repair in range(int(config["max_repairs"]) + 1):
                budget = config.get("token_budget")
                remaining = (
                    int(budget) - result.prompt_tokens - result.completion_tokens
                    if budget is not None
                    else None
                )
                if remaining is not None and remaining <= 0 and repair >= len(turns):
                    result.error = {
                        "code": "token_budget_exceeded",
                        "message": "The run token budget was exhausted during planning.",
                    }
                    return result
                if repair:
                    request["validation_note"] = (
                        "The previous response was invalid. Return valid JSON matching the "
                        "required schema and exact supplied step identities and dependencies."
                    )
                if repair < len(turns):
                    response = LLMResponse.model_validate(turns[repair])
                else:
                    if provider is None:
                        provider = self.provider_factory(model)
                    async for attempt in llm_retrying():
                        with attempt:
                            user_prompt = json.dumps(request, ensure_ascii=False)
                            max_tokens = (
                                min(int(config["max_tokens"]), remaining)
                                if remaining is not None
                                else int(config["max_tokens"])
                            )
                            await check_context(
                                provider,
                                PLANNER_SYSTEM_PROMPT,
                                [{"role": "user", "content": user_prompt}],
                                model,
                                [],
                                max_tokens,
                            )
                            if on_checkpoint is not None:
                                await on_checkpoint(
                                    {
                                        "turns": deepcopy(turns),
                                        "prompt_tokens": result.prompt_tokens,
                                        "completion_tokens": result.completion_tokens,
                                        "duration_ms": previous_duration
                                        + round((perf_counter() - started) * 1000),
                                        "provider_pending": True,
                                    }
                                )
                            async with asyncio.timeout(get_settings().llm_request_timeout):
                                response = await provider.complete(
                                    PLANNER_SYSTEM_PROMPT,
                                    user_prompt,
                                    model,
                                    temperature=float(config["temperature"]),
                                    max_tokens=max_tokens,
                                )
                result.prompt_tokens += response.usage.input_tokens
                result.completion_tokens += response.usage.output_tokens
                if repair == len(turns):
                    turns.append(response.model_dump(mode="json"))
                    if on_checkpoint is not None:
                        await on_checkpoint(
                            {
                                "turns": deepcopy(turns),
                                "prompt_tokens": result.prompt_tokens,
                                "completion_tokens": result.completion_tokens,
                                "duration_ms": previous_duration
                                + round((perf_counter() - started) * 1000),
                                "provider_pending": False,
                            }
                        )
                if budget is not None and result.prompt_tokens + result.completion_tokens > int(
                    budget
                ):
                    result.error = {
                        "code": "token_budget_exceeded",
                        "message": "The run token budget was exceeded during planning.",
                    }
                    return result
                try:
                    response.require_complete()
                    parsed = PlannedWorkflow.model_validate_json(response.content)
                    by_number = {step.step_number: step for step in parsed.steps}
                    if len(by_number) != len(parsed.steps) or set(by_number) != {
                        step.step_number for step in plan.steps
                    }:
                        raise ValueError("Planner must preserve all workflow steps")
                    for original in plan.steps:
                        generated = by_number[original.step_number]
                        if (
                            generated.agent_id != original.agent_id
                            or generated.depends_on != original.depends_on
                        ):
                            raise ValueError("Planner changed the workflow graph")
                    validated = plan.model_copy(deep=True)
                    validated.summary = parsed.summary
                    for step in validated.steps:
                        step.subtask = by_number[step.step_number].subtask
                    result.plan = validated
                    return result
                except IncompleteLLMResponse:
                    raise
                except ValidationError, ValueError:
                    continue
            result.error = {
                "code": "invalid_plan",
                "message": "The planner returned an invalid plan.",
            }
        except Exception as exception:
            logger.warning(
                "planning_failed", run_id=str(run_id), error_type=type(exception).__name__
            )
            result.error = (
                {
                    "code": "llm_incomplete_response",
                    "message": "The provider returned an incomplete or refused planning response.",
                }
                if isinstance(exception, IncompleteLLMResponse)
                else {
                    "code": "context_too_large",
                    "message": (
                        "Planning input and reserved response exceed the model context window. "
                        "Reduce the task or attached context."
                    ),
                }
                if isinstance(exception, ContextTooLarge)
                else {"code": "planning_error", "message": "The plan could not be generated."}
            )
        finally:
            if provider is not None:
                try:
                    await provider.aclose()
                except Exception:
                    logger.warning("planner_close_failed", run_id=str(run_id))
            result.duration_ms = previous_duration + round((perf_counter() - started) * 1000)
        return result


class PlannerExecutor:
    def __init__(self, repository: RunRepository, planner: LLMPlanner | None = None) -> None:
        self.repository = repository
        self.planner = planner or LLMPlanner()

    async def execute(self, run: Run) -> None:
        run_id = run.id
        current = await self.repository.get(run_id, lock=True)
        if current is None or current.status != "PLANNING":
            await self.repository.save()
            return
        steps: list[RunStep] = await self.repository.steps(run_id)
        # Copy all request data before releasing the transaction for provider I/O.
        plan = RunPlan.model_validate(run.plan)
        task, context = run.task, run.context_text
        config = dict(run.planner_config)
        checkpoint = deepcopy(run.planning_checkpoint or {})
        if config.get("token_budget") is not None:
            config["token_budget"] = max(
                0,
                int(config["token_budget"])
                - run.total_tokens
                + checkpoint.get("prompt_tokens", 0)
                + checkpoint.get("completion_tokens", 0),
            )
        roles = {step.step_number: dict(step.agent_config) for step in steps}
        await self.repository.save()
        checkpoints: list[tuple[dict[str, Any], asyncio.Future[None]]] = []
        checkpoint_ready = asyncio.Event()

        async def on_checkpoint(value: dict[str, Any]) -> None:
            receipt: asyncio.Future[None] = asyncio.get_running_loop().create_future()
            checkpoints.append((value, receipt))
            checkpoint_ready.set()
            await receipt

        pending = asyncio.create_task(
            self.planner.generate(
                task,
                context,
                config,
                plan,
                roles,
                run_id=run_id,
                checkpoint=checkpoint,
                on_checkpoint=on_checkpoint,
            )
        )
        try:
            while True:
                notification = asyncio.create_task(checkpoint_ready.wait())
                try:
                    done, _ = await asyncio.wait(
                        {pending, notification},
                        timeout=get_settings().run_poll_interval,
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                finally:
                    notification.cancel()
                    await asyncio.gather(notification, return_exceptions=True)
                current = await self.repository.get(run_id, lock=True)
                if current is None or current.status != "PLANNING":
                    await self.repository.save()
                    return
                if checkpoints:
                    acknowledged = list(checkpoints)
                    for value, _ in acknowledged:
                        previous = current.planning_checkpoint or {}
                        current.planning_prompt_tokens += value["prompt_tokens"] - previous.get(
                            "prompt_tokens", 0
                        )
                        current.planning_completion_tokens += value[
                            "completion_tokens"
                        ] - previous.get("completion_tokens", 0)
                        current.planning_time_ms += value["duration_ms"] - previous.get(
                            "duration_ms", 0
                        )
                        current.planning_checkpoint = value
                    checkpoints.clear()
                    checkpoint_ready.clear()
                    DAGExecutor.update_totals(current, steps)
                    await self.repository.save()
                    for _, receipt in acknowledged:
                        if not receipt.done():
                            receipt.set_result(None)
                if pending in done:
                    result = pending.result()
                    previous = current.planning_checkpoint or {}
                    current.planning_prompt_tokens += result.prompt_tokens - previous.get(
                        "prompt_tokens", 0
                    )
                    current.planning_completion_tokens += result.completion_tokens - previous.get(
                        "completion_tokens", 0
                    )
                    current.planning_time_ms += result.duration_ms - previous.get("duration_ms", 0)
                    current.planning_checkpoint = {}
                    current.planning_error = result.error
                    if result.plan is None:
                        current.status = "FAILED"
                        current.finished_at = datetime.now(UTC)
                        self.repository.emit(
                            run_id,
                            "task:failed",
                            {
                                "taskId": str(run_id),
                                "failedSteps": [],
                            },
                        )
                    else:
                        current.plan = result.plan.model_dump(mode="json")
                        by_number = {step.step_number: step for step in result.plan.steps}
                        for step in await self.repository.steps(run_id):
                            step.subtask = by_number[step.step_number].subtask
                        current.status = "AWAITING_CONFIRMATION"
                        self.repository.emit(run_id, "plan:ready", {"plan": current.plan})
                    DAGExecutor.update_totals(current, await self.repository.steps(run_id))
                    await self.repository.save()
                    return
                await self.repository.save()
        finally:
            pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)
