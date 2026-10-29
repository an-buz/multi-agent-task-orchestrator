"""Provider contract regressions using SDK-parsed fixtures, never live clients."""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from anthropic.types import Message
from app.core.config import Settings, get_settings
from app.llm.context import check_context
from app.llm.provider import IncompleteLLMResponse, ToolCall
from app.llm.providers import AnthropicProvider, OpenAIProvider, anthropic_messages
from app.llm.registry import get_model_registry
from app.orchestrator.executor import DAGExecutor
from app.orchestrator.planner import LLMPlanner, PlannerExecutor
from app.schemas.agent import AgentCreate
from app.services.agents import AgentError, AgentService
from openai.types.chat import ChatCompletion

from test_executor import make_run
from test_planner import ScriptedMock, planning_run
from test_tools import tool_step


@pytest.mark.parametrize("tools", [False, True])
@pytest.mark.parametrize(
    ("provider_name", "ending"),
    [
        (provider, ending)
        for provider in ("anthropic", "openai")
        for ending in ("normal", "truncated", "refused", "filtered", "tool", "truncated_tool")
        if not (provider == "anthropic" and ending == "filtered")
    ],
)
async def test_sdk_requests_and_stop_metadata(
    monkeypatch: pytest.MonkeyPatch, provider_name: str, tools: bool, ending: str
) -> None:
    wire = json.loads((Path(__file__).parent / "fixtures/llm/provider_wire.json").read_text())
    raw = wire[provider_name]

    if provider_name == "anthropic":
        raw["stop_reason"] = {
            "normal": "end_turn",
            "truncated": "max_tokens",
            "refused": "refusal",
            "tool": "tool_use",
            "truncated_tool": "max_tokens",
        }[ending]

        if ending in {"tool", "truncated_tool"}:
            raw["content"] = [
                {
                    "type": "tool_use",
                    "id": "call_fixture",
                    "name": "calculator",
                    "input": {"expression": "2+3"},
                }
            ]

        native = Message.model_validate(raw)
        create = AsyncMock(return_value=native)
        constructor = Mock(return_value=SimpleNamespace(messages=SimpleNamespace(create=create)))

        monkeypatch.setattr("app.llm.providers.AsyncAnthropic", constructor)

        provider = AnthropicProvider("fixture-placeholder")
        key = "claude-sonnet"
    else:
        choice = raw["choices"][0]
        choice["finish_reason"] = {
            "normal": "stop",
            "truncated": "length",
            "refused": "stop",
            "filtered": "content_filter",
            "tool": "tool_calls",
            "truncated_tool": "length",
        }[ending]

        if ending == "refused":
            choice["message"].update(content=None, refusal="Fixture refusal")

        if ending in {"tool", "truncated_tool"}:
            choice["message"].update(
                content=None,
                tool_calls=[
                    {
                        "type": "function",
                        "id": "call_fixture",
                        "function": {"name": "calculator", "arguments": '{"expression":"2+3"}'},
                    }
                ],
            )

        native = ChatCompletion.model_validate(raw)
        create = AsyncMock(return_value=native)
        constructor = Mock(
            return_value=SimpleNamespace(
                chat=SimpleNamespace(completions=SimpleNamespace(create=create))
            )
        )

        monkeypatch.setattr("app.llm.providers.AsyncOpenAI", constructor)

        provider = OpenAIProvider("fixture-placeholder")
        key = "gpt-4o"

    if tools:
        response = await provider.complete_tools(
            "System",
            [{"role": "user", "content": "User"}],
            key,
            [
                {
                    "name": "calculator",
                    "description": "Calculate",
                    "input_schema": {"type": "object"},
                }
            ],
            temperature=0.2,
            max_tokens=1024,
        )
    else:
        response = await provider.complete("System", "User", key, temperature=0.2, max_tokens=1024)

    constructor.assert_called_once_with(
        api_key="fixture-placeholder",
        max_retries=0,
        timeout=get_settings().llm_request_timeout,
        base_url=(
            get_settings().anthropic_api_url.removesuffix("/v1")
            if provider_name == "anthropic"
            else get_settings().openai_api_url
        ),
    )

    kwargs = create.await_args.kwargs

    assert kwargs["model"] == get_model_registry()[key].model_id
    assert kwargs["temperature"] == 0.2
    assert kwargs["max_tokens" if provider_name == "anthropic" else "max_completion_tokens"] == 1024

    if provider_name == "openai":
        assert "max_tokens" not in kwargs

    assert (response.usage.input_tokens, response.usage.output_tokens) == (17, 11)
    assert response.stop_reason == (
        raw["stop_reason"] if provider_name == "anthropic" else raw["choices"][0]["finish_reason"]
    )

    if ending in {"truncated", "truncated_tool", "refused", "filtered"} or (
        ending == "tool" and not tools
    ):
        with pytest.raises(IncompleteLLMResponse):
            response.require_complete()
    else:
        response.require_complete()

    if ending == "tool" and tools:
        assert response.tool_calls[0].arguments == {"expression": "2+3"}

    if ending == "truncated_tool" and provider_name == "anthropic":
        assert response.tool_calls == []


def test_mock_catalogue_is_independent_of_removed_model_overrides() -> None:
    registry = get_model_registry(Settings(_env_file=None))

    assert registry["claude-haiku"].model_id == "claude-haiku-4-5-20251001"
    assert registry["claude-opus"].model_id == "claude-opus-4-6"
    assert registry["claude-sonnet"].model_id == "claude-sonnet-4-6"
    assert registry["gpt-4o"].max_output_tokens == 16384

    for field, model_id in [
        ("anthropic_model_haiku", "claude-3-5-haiku-latest"),
        ("anthropic_model_sonnet", "claude-sonnet-5-5"),
        ("openai_model_default", "o3"),
    ]:
        settings = Settings(_env_file=None).model_copy(update={field: model_id})

        assert get_model_registry(settings) == registry


async def test_output_limit_rejected_before_counting_and_generation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = AgentCreate(
        name="Agent", role="Review", system_prompt="System", model="gpt-4o", max_tokens=20000
    )

    with pytest.raises(AgentError) as error:
        AgentService(None).validate(payload)

    assert error.value.details["reason"] == "exceeds_model_output_limit"

    AgentService(None).validate(payload.model_copy(update={"max_tokens": 16384}))

    counter = AsyncMock()

    with pytest.raises(ValueError, match="output limit"):
        await check_context(
            SimpleNamespace(count_input_tokens=counter), "System", [], "gpt-4o", [], 20000
        )

    counter.assert_not_awaited()

    create = AsyncMock()

    monkeypatch.setattr(
        "app.llm.providers.AsyncOpenAI",
        Mock(
            return_value=SimpleNamespace(
                chat=SimpleNamespace(completions=SimpleNamespace(create=create))
            )
        ),
    )

    provider = OpenAIProvider("fixture-placeholder")

    with pytest.raises(ValueError, match="output limit"):
        await provider.complete("System", "User", "gpt-4o", max_tokens=20000)

    with pytest.raises(ValueError, match="output limit"):
        await provider.complete_tools("System", [], "gpt-4o", [], temperature=0.2, max_tokens=20000)

    create.assert_not_awaited()


def test_anthropic_tool_errors_keep_grouping_and_error_flag() -> None:
    messages = [
        {"role": "assistant", "blocks": []},
        {"role": "tool", "tool_call_id": "failed", "content": '{"error":"Fixture error"}'},
        {"role": "tool", "tool_call_id": "ok", "content": '{"value":5}'},
    ]

    results = anthropic_messages(messages)[-1]["content"]

    assert [block["tool_use_id"] for block in results] == ["failed", "ok"]
    assert results[0]["is_error"] is True
    assert "is_error" not in results[1]


@pytest.mark.parametrize("reason", ["max_tokens", "length", "refusal", "content_filter", "unknown"])
async def test_incomplete_step_preserves_usage_and_does_not_execute_tools(reason: str) -> None:
    provider = ScriptedMock([])
    response = provider.fixture.model_copy(
        update={
            "stop_reason": reason,
            "tool_calls": [ToolCall(id="call", name="calculator", arguments={"expression": "2+3"})],
        }
    )
    provider.complete_tools = AsyncMock(return_value=response)
    step = tool_step()
    step.agent_config["tools"] = ["calculator"]
    events = []

    result = await DAGExecutor(None, lambda _: provider).complete(
        step, on_tool=lambda *event: events.append(event)
    )

    assert result.error["code"] == "llm_incomplete_response"
    assert (result.prompt_tokens, result.completion_tokens) == (
        response.usage.input_tokens,
        response.usage.output_tokens,
    )
    assert not any(name == "agent:tool_call" for name, _ in events)
    assert provider.closed


async def test_incomplete_run_fails_and_planner_never_publishes_ready() -> None:
    repository, run = await make_run([[]])

    provider = ScriptedMock([])
    response = provider.fixture.model_copy(update={"stop_reason": "length"})
    provider.complete = AsyncMock(return_value=response)

    await DAGExecutor(repository, lambda _: provider).execute(run)

    assert run.status == "FAILED"
    assert repository.saved_steps[0].error["code"] == "llm_incomplete_response"
    assert repository.saved_steps[0].tokens_prompt == response.usage.input_tokens

    repository, _, run = await planning_run()

    provider = ScriptedMock([])
    provider.complete = AsyncMock(return_value=response)

    await PlannerExecutor(repository, LLMPlanner(lambda _: provider)).execute(run)

    assert run.status == "FAILED"
    assert run.planning_error["code"] == "llm_incomplete_response"
    assert run.total_tokens == response.usage.input_tokens + response.usage.output_tokens
    assert provider.complete.await_count == 1
    assert not any(name == "plan:ready" for name, _ in repository.saved_events)
