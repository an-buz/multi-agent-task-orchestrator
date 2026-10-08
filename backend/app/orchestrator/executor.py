"""Dependency-aware execution with persisted checkpoints and provider-neutral calls."""

import asyncio
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from time import perf_counter

import structlog

from app.core.config import get_settings
from app.db.run_repository import RunRepository
from app.llm.provider import LLMProvider, LLMResponse
from app.llm.providers import create_provider
from app.llm.retry import llm_retrying
from app.models.run import Run
from app.models.run_step import RunStep

logger = structlog.get_logger()


def build_input(run: Run, step: RunStep, by_number: dict[int, RunStep]) -> str:
    """Expand only declared input variables; never execute template code."""
    values = {"task": run.task, "subtask": step.subtask, "context": run.context_text}
    for number in step.depends_on:
        values[f"steps.{number}.output"] = by_number[number].output or ""
    if not step.input_transform:
        dependencies = [
            f"Step {number}:\n{values[f'steps.{number}.output']}" for number in step.depends_on
        ]
        return "\n\n".join(
            value for value in [step.subtask, run.context_text, *dependencies] if value
        )

    def replace(match: re.Match[str]) -> str:
        key = match.group(1).strip()
        if key not in values:
            raise ValueError("Input template references an unsupported variable or dependency")
        return values[key]

    # Check the template before substitution so model output is never interpreted.
    remainder = re.sub(r"\{\{([^{}]+)\}\}", "", step.input_transform)
    if any(marker in remainder for marker in ("{{", "}}", "{%", "{#")):
        raise ValueError("Input templates support variable substitution only")
    return re.sub(r"\{\{([^{}]+)\}\}", replace, step.input_transform)


@dataclass
class StepResult:
    response: LLMResponse | None
    duration_ms: int
    error: dict[str, str] | None = None


class DAGExecutor:
    def __init__(
        self,
        repository: RunRepository,
        provider_factory: Callable[[str], LLMProvider] = create_provider,
        max_parallel_steps: int | None = None,
    ) -> None:
        self.repository = repository
        self.provider_factory = provider_factory
        self.limit = max_parallel_steps or get_settings().max_parallel_steps

    async def complete(self, step: RunStep) -> StepResult:
        started = perf_counter()
        provider: LLMProvider | None = None
        try:
            config = step.agent_config
            provider = self.provider_factory(str(config["model"]))
            async for attempt in llm_retrying():
                with attempt:
                    response = await provider.complete(
                        str(config["system_prompt"]),
                        step.input or "",
                        str(config["model"]),
                        temperature=float(config["temperature"]),
                        max_tokens=int(config["max_tokens"]),
                    )
            return StepResult(response, round((perf_counter() - started) * 1000))
        except Exception as exception:
            # Provider exception strings may contain prompts/keys; persist a safe message.
            logger.warning(
                "step_failed",
                run_id=str(step.run_id),
                step_number=step.step_number,
                agent_id=str(step.agent_id),
                error_type=type(exception).__name__,
            )
            return StepResult(
                None,
                round((perf_counter() - started) * 1000),
                {"code": "llm_error", "message": "The step could not be completed."},
            )
        finally:
            if provider is not None:
                try:
                    await provider.aclose()
                except Exception:
                    logger.warning(
                        "provider_close_failed",
                        run_id=str(step.run_id),
                        step_number=step.step_number,
                    )

    async def execute(self, run: Run) -> None:
        await self.repository.get(run.id, lock=True)
        if run.status != "IN_PROGRESS":
            await self.repository.save()
            return
        steps = await self.repository.steps(run.id)
        if not steps:
            run.status = "FAILED"
            run.finished_at = datetime.now(UTC)
            self.repository.emit(run.id, "task:failed", {"taskId": str(run.id), "failedSteps": []})
            await self.repository.save()
            return
        by_number = {step.step_number: step for step in steps}
        # A worker owns this run exclusively; recover only unfinished calls.
        for step in steps:
            if step.status == "IN_PROGRESS":
                step.status = "PENDING"
                self.status_event(run, step)
        await self.repository.save()
        active: dict[asyncio.Task[StepResult], RunStep] = {}
        try:
            while True:
                for step in steps:
                    if len(active) >= self.limit:
                        break
                    if step.status != "PENDING" or any(
                        number not in by_number or by_number[number].status != "COMPLETED"
                        for number in step.depends_on
                    ):
                        continue
                    if not await self.still_running(run):
                        return
                    step.attempt += 1
                    try:
                        if step.input is None:
                            step.input = build_input(run, step, by_number)
                    except ValueError:
                        step.status = "FAILED"
                        step.error = {
                            "code": "invalid_input_template",
                            "message": "Invalid input template.",
                        }
                        self.result_event(run, step)
                        await self.repository.save()
                        continue
                    step.status = "IN_PROGRESS"
                    step.error = None
                    self.status_event(run, step)
                    await self.repository.save()
                    active[asyncio.create_task(self.complete(step))] = step
                if not active:
                    break
                done, _ = await asyncio.wait(
                    active,
                    timeout=get_settings().run_poll_interval,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if not done:
                    if not await self.still_running(run):
                        return
                    await self.repository.save()
                    continue
                for task in done:
                    if not await self.still_running(run):
                        return
                    step = active.pop(task)
                    result = task.result()
                    step.execution_time_ms += result.duration_ms
                    step.error = result.error
                    if result.response is None:
                        step.status = "FAILED"
                    else:
                        step.status = "COMPLETED"
                        step.output = result.response.content
                        step.tokens_prompt += result.response.usage.input_tokens
                        step.tokens_completion += result.response.usage.output_tokens
                    self.update_totals(run, steps)
                    self.result_event(run, step)
                    await self.repository.save()
            if not await self.still_running(run):
                return
            self.update_totals(run, steps)
            run.status = (
                "COMPLETED" if all(step.status == "COMPLETED" for step in steps) else "FAILED"
            )
            if run.status == "COMPLETED":
                # Deterministic report compilation adds no fabricated provider usage.
                run.final_report = "\n\n".join(
                    f"## Step {step.step_number}: {step.agent_name}\n\n{step.output or ''}"
                    for step in steps
                )
            run.finished_at = datetime.now(UTC)
            if run.status == "COMPLETED":
                self.repository.emit(
                    run.id,
                    "task:finished",
                    {
                        "taskId": str(run.id),
                        "finalReport": run.final_report,
                        "totalTokens": run.total_tokens,
                        "totalTimeMs": run.total_time_ms,
                    },
                )
            else:
                self.repository.emit(
                    run.id,
                    "task:failed",
                    {
                        "taskId": str(run.id),
                        "failedSteps": [
                            step.step_number for step in steps if step.status == "FAILED"
                        ],
                    },
                )
            await self.repository.save()
        finally:
            for task in active:
                task.cancel()
            if active:
                await asyncio.gather(*active, return_exceptions=True)

    async def still_running(self, run: Run) -> bool:
        # Serialize checkpoints with cancel/retry; refresh avoids stale ORM status.
        await self.repository.get(run.id, lock=True)
        if run.status != "IN_PROGRESS":
            await self.repository.save()
            return False
        return True

    def status_event(self, run: Run, step: RunStep) -> None:
        self.repository.emit(
            run.id,
            "agent:status_change",
            {
                "agentId": str(step.agent_id),
                "stepNumber": step.step_number,
                "status": step.status,
            },
        )

    def result_event(self, run: Run, step: RunStep) -> None:
        self.status_event(run, step)
        data: dict[str, object] = {
            "agentId": str(step.agent_id),
            "stepNumber": step.step_number,
        }
        if step.status == "COMPLETED":
            data.update(
                {
                    "output": step.output,
                    "tokensUsed": {
                        "prompt": step.tokens_prompt,
                        "completion": step.tokens_completion,
                        "total": step.tokens_prompt + step.tokens_completion,
                    },
                    "executionTime": step.execution_time_ms / 1000,
                }
            )
            self.repository.emit(run.id, "agent:completed", data)
        else:
            data.update({"error": step.error, "retryable": True})
            self.repository.emit(run.id, "agent:failed", data)

    @staticmethod
    def update_totals(run: Run, steps: list[RunStep]) -> None:
        run.total_tokens = (
            run.planning_prompt_tokens
            + run.planning_completion_tokens
            + sum(step.tokens_prompt + step.tokens_completion for step in steps)
        )
        run.total_time_ms = run.planning_time_ms + sum(step.execution_time_ms for step in steps)
