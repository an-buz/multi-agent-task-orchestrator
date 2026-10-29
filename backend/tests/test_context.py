"""Context admission regressions; no real LLM requests or fabricated usage."""

import asyncio
import copy
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from app.core.config import get_settings
from app.llm.context import ContextTooLarge, check_context, conservative_input_size
from app.llm.providers import (
    AnthropicProvider,
    MockLLMProvider,
    OpenAIProvider,
    anthropic_messages,
    openai_input_size,
)
from app.llm.registry import get_model_registry
from app.llm.retry import llm_retrying
from app.orchestrator.executor import DAGExecutor
from app.orchestrator.planner import LLMPlanner, PlannerExecutor
from app.schemas.agent import AgentCreate
from app.services.agents import AgentError, AgentService
from tenacity import wait_none

from test_executor import make_run
from test_planner import ScriptedMock, planning_run
from test_tools import FixtureTools, tool_step


@pytest.mark.parametrize(("count", "fits"), [(89, True), (90, True), (91, False)])
async def test_context_boundary_reserves_output_and_uses_agent_window(
    monkeypatch: pytest.MonkeyPatch, count: int, fits: bool
) -> None:
    monkeypatch.setattr(get_settings(), "context_safety_margin_tokens", 0)

    counter = AsyncMock(return_value=count)
    provider = SimpleNamespace(count_input_tokens=counter)

    args = (provider, "System", [{"role": "user", "content": "User"}], "gpt-4o", [], 10, 100)

    if fits:
        await check_context(*args)
    else:
        with pytest.raises(ContextTooLarge):
            await check_context(*args)

    counter.assert_awaited_once()


async def test_model_window_caps_requested_window(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "context_safety_margin_tokens", 0)

    registry = get_model_registry()
    registry["gpt-4o"] = replace(registry["gpt-4o"], context_window=100)

    monkeypatch.setattr("app.llm.context.get_model_registry", lambda _: registry)

    provider = SimpleNamespace(count_input_tokens=AsyncMock(return_value=91))

    with pytest.raises(ContextTooLarge):
        await check_context(provider, "", [], "gpt-4o", [], 10, 200)


async def test_output_and_margin_can_reject_without_counting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(get_settings(), "context_safety_margin_tokens", 10)

    provider = SimpleNamespace(count_input_tokens=AsyncMock())

    with pytest.raises(ContextTooLarge):
        await check_context(provider, "", [], "gpt-4o", [], 90, 100)

    provider.count_input_tokens.assert_not_awaited()


@pytest.mark.parametrize("count", [-1, True, 1.5])
async def test_bad_counter_result_fails_closed(count: object) -> None:
    provider = SimpleNamespace(count_input_tokens=AsyncMock(return_value=count))

    with pytest.raises(ValueError, match="Invalid context"):
        await check_context(provider, "", [], "gpt-4o", [], 10)


async def test_dependency_output_is_checked_before_generation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository, run = await make_run([[], [1]])

    monkeypatch.setattr(get_settings(), "context_safety_margin_tokens", 0)

    dependency, target = repository.saved_steps
    dependency.status = "COMPLETED"
    dependency.output = "Long dependency result " * 1000

    target.agent_config.update(context_window=1500, max_tokens=10)

    provider = MockLLMProvider()
    calls = AsyncMock(wraps=provider.complete)

    monkeypatch.setattr(provider, "complete", calls)

    await DAGExecutor(repository, lambda _: provider).execute(run)

    assert run.status == "FAILED"
    assert dependency.status == "COMPLETED"
    assert target.status == "FAILED"
    assert target.error["code"] == "context_too_large"
    assert target.tokens_prompt == target.tokens_completion == 0
    assert "Long dependency" not in target.error["message"]

    calls.assert_not_awaited()


async def test_tool_history_growth_fails_and_preserves_usage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(get_settings(), "context_safety_margin_tokens", 0)

    provider = FixtureTools()
    counter = AsyncMock(side_effect=[0, 501])

    monkeypatch.setattr(provider, "count_input_tokens", counter, raising=False)

    step = tool_step()

    step.agent_config.update(context_window=500, max_tokens=10)

    result = await DAGExecutor(None, lambda _: provider).complete(step)

    assert provider.calls == 1 and provider.closed
    assert result.error["code"] == "context_too_large"
    assert (result.prompt_tokens, result.completion_tokens) == (10, 4)

    second = counter.await_args_list[1].args

    assert [message["role"] for message in second[1]] == ["user", "assistant", "tool"]
    assert second[3][0]["name"] == "calculator"


@pytest.mark.parametrize("repair", [False, True])
async def test_planner_checks_initial_input_and_repair(
    monkeypatch: pytest.MonkeyPatch, repair: bool
) -> None:
    repository, _, run = await planning_run()

    provider = ScriptedMock(["invalid"])
    over_window = get_model_registry()["claude-sonnet"].context_window + 1
    counts = [0, over_window] if repair else [over_window]

    monkeypatch.setattr(
        provider, "count_input_tokens", AsyncMock(side_effect=counts), raising=False
    )

    await PlannerExecutor(repository, LLMPlanner(lambda _: provider)).execute(run)

    assert run.status == "FAILED"
    assert run.planning_error["code"] == "context_too_large"
    assert len(provider.requests) == (1 if repair else 0)
    assert run.total_tokens == (28 if repair else 0)
    assert provider.closed
    assert not any(event == "plan:ready" for event, _ in repository.saved_events)


async def test_anthropic_count_uses_native_tool_conversation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    count = AsyncMock(return_value=SimpleNamespace(input_tokens=73))
    create = AsyncMock()

    monkeypatch.setattr(
        "app.llm.providers.AsyncAnthropic",
        Mock(
            return_value=SimpleNamespace(
                messages=SimpleNamespace(count_tokens=count, create=create)
            )
        ),
    )

    messages = [
        {"role": "user", "content": "Calculate"},
        {
            "role": "assistant",
            "blocks": [{"type": "tool_use", "id": "c", "name": "calculator", "input": {}}],
        },
        {"role": "tool", "tool_call_id": "c", "content": "result"},
    ]
    tools = [{"name": "calculator", "description": "Calculate", "input_schema": {"type": "object"}}]

    result = await AnthropicProvider("test-placeholder").count_input_tokens(
        "System", messages, "claude-sonnet", tools
    )

    assert result == 73

    native = count.await_args.kwargs

    assert native["system"] == "System" and native["tools"] == tools
    assert native["messages"][-1]["content"][0]["type"] == "tool_result"
    assert native["messages"][-1]["content"][0]["tool_use_id"] == "c"

    create.assert_not_awaited()


def test_openai_tokenizer_handles_unicode_special_text_and_tools() -> None:
    # Public tokenizer vocabulary is prepared/cached before offline test runs.
    messages = [{"role": "user", "content": "Привіт 👋 <|endoftext|>"}]
    tools = [{"name": "calculator", "description": "Calculate", "input_schema": {"type": "object"}}]
    small = openai_input_size("System", messages, [], "o200k_base")
    large = openai_input_size("System", messages, tools, "o200k_base")

    assert large > small > 0
    assert conservative_input_size("System", messages, tools) > large


async def test_openai_count_never_calls_generation(monkeypatch: pytest.MonkeyPatch) -> None:
    create = AsyncMock()

    monkeypatch.setattr(
        "app.llm.providers.AsyncOpenAI",
        Mock(
            return_value=SimpleNamespace(
                chat=SimpleNamespace(completions=SimpleNamespace(create=create))
            )
        ),
    )

    count = await OpenAIProvider("test-placeholder").count_input_tokens(
        "System", [{"role": "user", "content": "User"}], "gpt-4o", []
    )

    assert count > 0

    create.assert_not_awaited()


def test_native_count_conversion_does_not_mutate_input() -> None:
    messages = [
        {"role": "user", "content": [{"type": "text", "text": "Input"}]},
        {"role": "tool", "tool_call_id": "c", "content": "Result"},
    ]

    before = copy.deepcopy(messages)

    assert anthropic_messages(messages) == anthropic_messages(messages)
    assert messages == before


def test_agent_output_limit_must_leave_input_space() -> None:
    with pytest.raises(AgentError) as error:
        AgentService(None).validate(
            AgentCreate(
                name="Agent",
                role="Review",
                system_prompt="Prompt",
                max_tokens=100,
                context_window=100,
            )
        )

    assert error.value.details["reason"] == "must_leave_room_for_input"


async def test_count_timeout_retries_without_generation(monkeypatch: pytest.MonkeyPatch) -> None:
    repository, run = await make_run([[]])

    provider = MockLLMProvider()
    generation = AsyncMock(wraps=provider.complete)

    async def blocked(*args, **kwargs):
        await asyncio.Event().wait()

    def immediate_retry():
        retry = llm_retrying()
        retry.wait = wait_none()

        return retry

    counter = AsyncMock(side_effect=blocked)

    monkeypatch.setattr(provider, "count_input_tokens", counter, raising=False)
    monkeypatch.setattr(provider, "complete", generation)
    monkeypatch.setattr("app.orchestrator.executor.llm_retrying", immediate_retry)
    monkeypatch.setattr(get_settings(), "llm_request_timeout", 0.01)

    await asyncio.wait_for(DAGExecutor(repository, lambda _: provider).execute(run), 1)

    assert run.status == "FAILED"
    assert counter.await_count == 3

    generation.assert_not_awaited()

    assert repository.saved_steps[0].tokens_prompt == 0
