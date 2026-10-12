"""Regressions found during the backend review, using no live LLM requests."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from anthropic import APIConnectionError as AnthropicConnectionError
from app.core.config import get_settings
from app.llm.provider import LLMChunk, LLMResponse, LLMUsage, ToolCall
from app.llm.providers import OpenAIProvider
from app.llm.retry import llm_retrying
from app.orchestrator.executor import DAGExecutor
from app.orchestrator.planner import LLMPlanner, PlannerExecutor
from app.schemas.agent import AgentCreate
from app.schemas.run import RunCreate
from app.schemas.workflow import WorkflowWrite
from openai import APIConnectionError as OpenAIConnectionError
from pydantic import ValidationError
from tenacity import wait_none

from test_executor import make_run
from test_planner import planning_run


def immediate_retry():
    retry = llm_retrying()
    retry.wait = wait_none()
    return retry


@pytest.mark.parametrize(
    "exception",
    [
        OpenAIConnectionError(request=httpx.Request("POST", "https://example.test")),
        AnthropicConnectionError(request=httpx.Request("POST", "https://example.test")),
        httpx.ConnectError("fixture"),
        httpx.ReadError("fixture"),
    ],
)
async def test_provider_connection_failures_retry(exception: Exception) -> None:
    call = AsyncMock(side_effect=[exception, exception, "success"])
    async for attempt in immediate_retry():
        with attempt:
            result = await call()
    assert result == "success"
    assert call.await_count == 3


async def test_application_error_named_timeout_is_not_retried() -> None:
    class InvalidTimeoutConfiguration(ValueError):
        pass

    call = AsyncMock(side_effect=InvalidTimeoutConfiguration("fixture"))
    with pytest.raises(InvalidTimeoutConfiguration):
        async for attempt in immediate_retry():
            with attempt:
                await call()
    assert call.await_count == 1


@pytest.mark.parametrize("tools", [[], ["calculator"]])
async def test_non_streaming_step_timeout_retries_and_closes(
    monkeypatch: pytest.MonkeyPatch, tools: list[str]
) -> None:
    repository, run = await make_run([[]])
    repository.saved_steps[0].agent_config["tools"] = tools
    monkeypatch.setattr(get_settings(), "llm_request_timeout", 0.01)
    monkeypatch.setattr("app.orchestrator.executor.llm_retrying", immediate_retry)
    cancelled = 0

    async def blocked(*args: object, **kwargs: object):
        nonlocal cancelled
        try:
            await asyncio.Event().wait()
        finally:
            cancelled += 1

    provider = SimpleNamespace(
        complete=AsyncMock(side_effect=blocked),
        complete_tools=AsyncMock(side_effect=blocked),
        aclose=AsyncMock(),
    )
    await asyncio.wait_for(DAGExecutor(repository, lambda _: provider).execute(run), 1)
    assert run.status == "FAILED"
    assert cancelled == 3
    provider.aclose.assert_awaited_once()
    step = repository.saved_steps[0]
    assert step.error and step.error["code"] == "llm_error"
    assert step.tokens_prompt == step.tokens_completion == 0


async def test_planning_timeout_retries_and_closes(monkeypatch: pytest.MonkeyPatch) -> None:
    repository, _, run = await planning_run()
    monkeypatch.setattr(get_settings(), "llm_request_timeout", 0.01)
    monkeypatch.setattr("app.orchestrator.planner.llm_retrying", immediate_retry)

    async def blocked(*args: object, **kwargs: object):
        await asyncio.Event().wait()

    provider = SimpleNamespace(complete=AsyncMock(side_effect=blocked), aclose=AsyncMock())
    executor = PlannerExecutor(repository, LLMPlanner(lambda _: provider))
    await asyncio.wait_for(executor.execute(run), 1)
    assert run.status == "FAILED"
    assert run.planning_error and run.planning_error["code"] == "planning_error"
    assert provider.complete.await_count == 3
    provider.aclose.assert_awaited_once()
    assert not any(event == "plan:ready" for event, _ in repository.saved_events)


@pytest.mark.parametrize("tools", [False, True])
async def test_openai_response_requires_authoritative_usage(
    monkeypatch: pytest.MonkeyPatch, tools: bool
) -> None:
    create = AsyncMock(
        return_value=SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="fixture", tool_calls=[]))],
            usage=None,
        )
    )
    monkeypatch.setattr(
        "app.llm.providers.AsyncOpenAI",
        lambda **kwargs: SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=create))
        ),
    )
    provider = OpenAIProvider("test-placeholder")
    with pytest.raises(ValueError, match="no token usage"):
        if tools:
            await provider.complete_tools(
                "System",
                [{"role": "user", "content": "User"}],
                "gpt-4o",
                [],
                temperature=0.2,
                max_tokens=1024,
            )
        else:
            await provider.complete("System", "User", "gpt-4o")


@pytest.mark.parametrize("field", ["input_tokens", "output_tokens"])
def test_negative_provider_usage_is_rejected(field: str) -> None:
    usage = {"input_tokens": 1, "output_tokens": 1, field: -1}
    with pytest.raises(ValidationError):
        LLMUsage.model_validate(usage)


@pytest.mark.parametrize("text", ["bad\x00text", "bad\ud800text"])
def test_unstorable_request_and_provider_text_is_rejected(text: str) -> None:
    for schema, data in [
        (AgentCreate, {"name": "Agent", "role": "Role", "system_prompt": text}),
        (RunCreate, {"workflow_id": uuid4(), "task": text}),
        (
            WorkflowWrite,
            {
                "title": "Pipeline",
                "execution_type": "sequential",
                "steps": [{"step_number": 1, "agent_id": uuid4()}],
                "graph_layout": {"node": {text: "value"}},
            },
        ),
        (LLMResponse, {"content": text, "usage": {"input_tokens": 1, "output_tokens": 1}}),
        (LLMChunk, {"text_delta": text}),
        (ToolCall, {"id": "call-1", "name": "calculator", "arguments": {"expression": text}}),
    ]:
        with pytest.raises(ValidationError):
            schema.model_validate(data)
