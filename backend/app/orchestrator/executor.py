"""Dependency-aware execution with persisted checkpoints and provider-neutral calls."""

import asyncio
import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from time import perf_counter
from typing import Any

import structlog

from app.core.config import get_settings
from app.db.file_repository import FileRepository
from app.db.run_repository import RunRepository
from app.llm.provider import LLMProvider, LLMResponse, StreamingLLMProvider
from app.llm.providers import create_provider
from app.llm.retry import llm_retrying
from app.models.run import Run
from app.models.run_step import RunStep
from app.schemas.event import EventName
from app.tools.runtime import ToolRuntime

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
    prompt_tokens: int = 0
    completion_tokens: int = 0


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

    async def complete(
        self,
        step: RunStep,
        files: dict[str, str] | None = None,
        token_allowance: int | None = None,
        on_tool: Callable[[EventName, dict[str, Any]], None] | None = None,
    ) -> StepResult:
        started = perf_counter()
        provider: LLMProvider | None = None
        prompt_tokens = completion_tokens = 0
        error_code = "llm_error"
        try:
            config = step.agent_config
            provider = self.provider_factory(str(config["model"]))
            runtime = ToolRuntime(config.get("tools", []), files)
            definitions = runtime.definitions()
            messages: list[dict[str, Any]] = [{"role": "user", "content": step.input or ""}]
            call_count = 0
            for round_number in range(get_settings().tool_max_rounds + 1):
                remaining = (
                    token_allowance - prompt_tokens - completion_tokens
                    if token_allowance is not None
                    else None
                )
                if remaining is not None and remaining <= 0:
                    error_code = "token_budget_exceeded"
                    raise ValueError("Budget exhausted")
                max_tokens = (
                    min(int(config["max_tokens"]), remaining)
                    if remaining is not None
                    else int(config["max_tokens"])
                )
                async for attempt in llm_retrying():
                    with attempt:
                        if isinstance(provider, StreamingLLMProvider):
                            identity = {
                                "agentId": str(step.agent_id),
                                "stepNumber": step.step_number,
                                "attempt": step.attempt,
                            }
                            if on_tool is not None:
                                on_tool(
                                    "agent:stream_chunk",
                                    {**identity, "textDelta": "", "reset": True},
                                )
                            terminal: LLMResponse | None = None
                            async with asyncio.timeout(get_settings().llm_request_timeout):
                                stream = provider.stream(
                                    str(config["system_prompt"]),
                                    messages,
                                    str(config["model"]),
                                    definitions,
                                    temperature=float(config["temperature"]),
                                    max_tokens=max_tokens,
                                )
                                try:
                                    async for chunk in stream:
                                        if terminal is not None:
                                            raise ValueError("Chunk after terminal response")
                                        if chunk.text_delta and on_tool is not None:
                                            on_tool(
                                                "agent:stream_chunk",
                                                {
                                                    **identity,
                                                    "textDelta": chunk.text_delta,
                                                    "reset": False,
                                                },
                                            )
                                        terminal = chunk.response
                                finally:
                                    await stream.aclose()
                            if terminal is None:
                                raise ValueError("Stream ended without response usage")
                            response = terminal
                        elif definitions:
                            response = await provider.complete_tools(
                                str(config["system_prompt"]),
                                messages,
                                str(config["model"]),
                                definitions,
                                temperature=float(config["temperature"]),
                                max_tokens=max_tokens,
                            )
                        else:
                            response = await provider.complete(
                                str(config["system_prompt"]),
                                step.input or "",
                                str(config["model"]),
                                temperature=float(config["temperature"]),
                                max_tokens=max_tokens,
                            )
                prompt_tokens += response.usage.input_tokens
                completion_tokens += response.usage.output_tokens
                if (
                    token_allowance is not None
                    and prompt_tokens + completion_tokens > token_allowance
                ):
                    error_code = "token_budget_exceeded"
                    raise ValueError("Budget exceeded")
                if not response.tool_calls:
                    return StepResult(
                        response,
                        round((perf_counter() - started) * 1000),
                        prompt_tokens=prompt_tokens,
                        completion_tokens=completion_tokens,
                    )
                call_count += len(response.tool_calls)
                ids = [call.id for call in response.tool_calls]
                if (
                    round_number >= get_settings().tool_max_rounds
                    or call_count > get_settings().tool_max_calls
                    or len(set(ids)) != len(ids)
                ):
                    error_code = "tool_limit_exceeded"
                    raise ValueError("Tool loop limit exceeded")
                messages.append(response.message)
                for call in response.tool_calls:
                    identity = {
                        "agentId": str(step.agent_id),
                        "stepNumber": step.step_number,
                        "toolName": call.name,
                    }
                    if on_tool is not None:
                        on_tool(
                            "agent:tool_call",
                            {**identity, "input": {"argumentNames": sorted(call.arguments)}},
                        )
                    tool_result = await runtime.execute(call)
                    if on_tool is not None:
                        ok = "error" not in json.loads(tool_result)
                        on_tool(
                            "agent:tool_result",
                            {
                                **identity,
                                "ok": ok,
                                "summary": "Tool completed." if ok else "Tool failed.",
                            },
                        )
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call.id,
                            "content": tool_result,
                        }
                    )
            raise ValueError("Tool loop did not finish")
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
                {"code": error_code, "message": "The step could not be completed."},
                prompt_tokens,
                completion_tokens,
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
        current = await self.repository.get(run.id, lock=True)
        if current is None or current.status != "IN_PROGRESS":
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
        budget = run.planner_config.get("token_budget")
        # Serialize budgeted runs so parallel steps cannot spend the same remainder.
        limit = 1 if budget is not None else self.limit
        files = (
            await FileRepository(self.repository.session).text_for_run(run.id)
            if any("file_reader" in step.agent_config.get("tools", []) for step in steps)
            else {}
        )
        # A worker owns this run exclusively; recover only unfinished calls.
        for step in steps:
            if step.status == "IN_PROGRESS":
                step.status = "PENDING"
                self.status_event(run, step)
        await self.repository.save()
        active: dict[asyncio.Task[StepResult], RunStep] = {}
        tool_events: list[tuple[EventName, dict[str, Any]]] = []
        event_ready = asyncio.Event()

        def on_tool(name: EventName, data: dict[str, Any]) -> None:
            tool_events.append((name, data))
            event_ready.set()

        async def flush_tool_events() -> bool:
            if not tool_events:
                return True
            if not await self.still_running(run):
                return False
            for name, data in tool_events:
                if name == "agent:stream_chunk":
                    step = by_number[int(data["stepNumber"])]
                    output = ("" if data["reset"] else step.output or "") + str(data["textDelta"])
                    step.output = output or None
                    data["output"] = output
                self.repository.emit(run.id, name, data)
            tool_events.clear()
            event_ready.clear()
            await self.repository.save()
            return True

        try:
            while True:
                if not await flush_tool_events():
                    return
                for step in steps:
                    if len(active) >= limit:
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
                    step.output = None
                    self.status_event(run, step)
                    await self.repository.save()
                    self.update_totals(run, steps)
                    allowance = (
                        max(0, int(budget) - run.total_tokens) if budget is not None else None
                    )
                    active[asyncio.create_task(self.complete(step, files, allowance, on_tool))] = (
                        step
                    )
                if not active:
                    break
                notification = asyncio.create_task(event_ready.wait())
                try:
                    ready, _ = await asyncio.wait(
                        [*active, notification],
                        timeout=get_settings().run_poll_interval,
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    done = {task for task in active if task in ready}
                finally:
                    notification.cancel()
                    await asyncio.gather(notification, return_exceptions=True)
                if not await flush_tool_events():
                    return
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
                    step.tokens_prompt += result.prompt_tokens
                    step.tokens_completion += result.completion_tokens
                    if result.response is None:
                        step.status = "FAILED"
                    else:
                        step.status = "COMPLETED"
                        step.output = result.response.content
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
        current = await self.repository.get(run.id, lock=True)
        if current is None or current.status != "IN_PROGRESS":
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
