"""Native Gemini wire contract, recovery and retries with local HTTP fixtures only."""

import asyncio
import json
from copy import deepcopy
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from app.core.config import Settings
from app.llm.gemini import GeminiProvider, gemini_contents, gemini_response
from app.llm.planning import PLANNER_SYSTEM_PROMPT
from app.llm.provider import IncompleteLLMResponse, LLMResponse
from app.llm.providers import MockGeminiProvider, create_provider
from app.llm.retry import llm_retrying
from app.orchestrator.executor import DAGExecutor
from app.orchestrator.planner import LLMPlanner, PlannerExecutor
from tenacity import wait_none

from test_planner import planning_run
from test_tools import tool_step


@pytest.fixture
def wire():
    return json.loads((Path(__file__).parent / "fixtures/llm/gemini.json").read_text())


def local_provider(monkeypatch, handler, settings=None):
    constructor = Mock(
        side_effect=lambda **kwargs: httpx.AsyncClient(
            **kwargs, transport=httpx.MockTransport(handler)
        )
    )
    monkeypatch.setattr("app.llm.gemini.GeminiClient", constructor)
    provider = GeminiProvider("fixture-secret", settings or Settings(_env_file=None))
    return provider, constructor


async def test_native_generation_counting_and_structured_planning(monkeypatch, wire):
    requests = []

    def handler(request):
        requests.append(request)
        assert request.headers["x-goog-api-key"] == "fixture-secret"
        assert "fixture-secret" not in str(request.url)
        return httpx.Response(
            200,
            json={"totalTokens": 19} if request.url.path.endswith("countTokens") else wire["text"],
        )

    settings = Settings(_env_file=None, gemini_api_url="https://gemini.example.test/v1beta")
    provider, constructor = local_provider(monkeypatch, handler, settings)
    tools = [
        {
            "name": "calculator",
            "description": "Calculate",
            "input_schema": {"type": "object", "additionalProperties": False},
        }
    ]
    try:
        assert (
            await provider.count_input_tokens(
                "System", [{"role": "user", "content": "User"}], "gemini-flash-lite", tools
            )
            == 19
        )
        response = await provider.complete(
            PLANNER_SYSTEM_PROMPT, "User", "gemini-flash-lite", temperature=0.2, max_tokens=1024
        )
        response.require_complete()
        assert (response.usage.input_tokens, response.usage.output_tokens) == (17, 10)
        count_payload = json.loads(requests[0].content)["generateContentRequest"]
        assert count_payload["model"] == "models/gemini-3.5-flash-lite"
        assert count_payload["systemInstruction"] == {"parts": [{"text": "System"}]}
        assert (
            count_payload["tools"][0]["functionDeclarations"][0]["parametersJsonSchema"]
            == tools[0]["input_schema"]
        )
        generation = json.loads(requests[1].content)
        assert generation["contents"] == [{"role": "user", "parts": [{"text": "User"}]}]
        assert generation["generationConfig"]["maxOutputTokens"] == 1024
        assert generation["generationConfig"]["temperature"] == 0.2
        assert generation["generationConfig"]["responseMimeType"] == "application/json"
        assert generation["generationConfig"]["responseJsonSchema"]["required"] == [
            "summary",
            "steps",
        ]
        assert "tools" not in generation
        assert requests[1].url.path.endswith("models/gemini-3.5-flash-lite:generateContent")
        constructor.assert_called_once_with(
            base_url=settings.gemini_api_url + "/",
            headers={"x-goog-api-key": "fixture-secret"},
            timeout=settings.llm_request_timeout,
        )
    finally:
        await provider.aclose()
    assert provider._client.is_closed


@pytest.mark.parametrize("with_ids", [False, True])
def test_parallel_calls_keep_names_ids_and_signed_parts_without_mutation(wire, with_ids):
    raw = wire["tool"]
    parts = raw["candidates"][0]["content"]["parts"]
    parts.append({"functionCall": {"name": "calculator", "args": {"expression": "4+5"}}})
    if with_ids:
        for index, part in enumerate(parts):
            part["functionCall"]["id"] = f"call-{index}"
    original = deepcopy(raw)
    response = gemini_response(raw)
    response.require_complete()
    assert len({call.id for call in response.tool_calls}) == 2
    # Simulate JSON checkpoint storage before rebuilding the next Gemini request.
    restored = LLMResponse.model_validate_json(response.model_dump_json())
    contents = gemini_contents(
        [
            {"role": "user", "content": "Calculate"},
            restored.message,
            *[
                {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": '{"error":"fixture failure"}' if index else '{"value":5}',
                }
                for index, call in enumerate(restored.tool_calls)
            ],
        ]
    )
    assert contents[1] == raw["candidates"][0]["content"]
    responses = [part["functionResponse"] for part in contents[2]["parts"]]
    assert [item["name"] for item in responses] == ["calculator", "calculator"]
    assert responses[0]["response"] == {"value": 5}
    assert responses[1]["response"] == {"error": "fixture failure"}
    assert [item.get("id") for item in responses] == (
        ["call-0", "call-1"] if with_ids else [None, None]
    )
    assert raw == original


@pytest.mark.parametrize(
    "reason", ["MAX_TOKENS", "SAFETY", "RECITATION", "MALFORMED_FUNCTION_CALL", "unknown"]
)
def test_incomplete_tool_calls_never_execute_and_keep_usage(wire, reason):
    wire["tool"]["candidates"][0]["finishReason"] = reason
    response = gemini_response(wire["tool"])
    assert response.tool_calls == []
    assert response.usage.output_tokens == 5
    with pytest.raises(IncompleteLLMResponse):
        response.require_complete()


def test_blocked_prompt_and_missing_usage_are_not_successful():
    response = gemini_response(
        {"promptFeedback": {"blockReason": "SAFETY"}, "usageMetadata": {"promptTokenCount": 9}}
    )
    assert response.refused and response.usage.output_tokens == 0
    with pytest.raises(IncompleteLLMResponse):
        response.require_complete()
    with pytest.raises(ValueError, match="no token usage"):
        gemini_response({"candidates": []})


def sse_response(raws):
    # Include comments, CRLF, split JSON across data lines and no final blank line.
    events = [": heartbeat\r\n"]
    for raw in raws:
        data = json.dumps(raw)
        split = data.index(":") + 1
        events.append(f"event: message\r\ndata: {data[:split]}\r\ndata: {data[split:]}\r\n\r\n")
    return httpx.Response(
        200, text="".join(events).rstrip(), headers={"content-type": "text/event-stream"}
    )


async def test_native_stream_filters_thoughts_and_keeps_cumulative_usage(monkeypatch, wire):
    raws = [
        {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {"text": "Private thought", "thought": True, "thoughtSignature": "c2ln"}
                        ]
                    }
                }
            ]
        },
        {
            "candidates": [{"content": {"parts": [{"text": "The result "}]}}],
            "usageMetadata": {"promptTokenCount": 17, "candidatesTokenCount": 2},
        },
        {"candidates": [{"content": {"parts": [{"text": "is 5."}]}, "finishReason": "STOP"}]},
        {"usageMetadata": wire["text"]["usageMetadata"]},
    ]

    def handler(request):
        assert request.url.path.endswith(":streamGenerateContent")
        assert request.url.params["alt"] == "sse"
        return sse_response(raws)

    provider, _ = local_provider(monkeypatch, handler)
    try:
        chunks = [
            chunk
            async for chunk in provider.stream(
                "System",
                [{"role": "user", "content": "User"}],
                "gemini-flash",
                [],
                temperature=0.7,
                max_tokens=1024,
            )
        ]
    finally:
        await provider.aclose()
    assert "".join(chunk.text_delta for chunk in chunks) == "The result is 5."
    assert sum(chunk.response is not None for chunk in chunks) == 1
    final = chunks[-1].response
    assert final.content == "The result is 5."
    assert (final.usage.input_tokens, final.usage.output_tokens) == (17, 10)
    assert final.message["gemini_content"]["parts"][0]["thoughtSignature"] == "c2ln"


@pytest.mark.parametrize("failure", ["usage", "finish", "error"])
async def test_incomplete_streams_do_not_become_successful(monkeypatch, wire, failure):
    raw = wire["text"]
    if failure == "usage":
        del raw["usageMetadata"]
    elif failure == "finish":
        del raw["candidates"][0]["finishReason"]
    else:
        raw = {"error": {"code": 503, "message": "private fixture text"}}
    provider, _ = local_provider(monkeypatch, lambda _: sse_response([raw]))
    try:
        with pytest.raises((ValueError, httpx.HTTPStatusError)) as error:
            chunks = [
                chunk
                async for chunk in provider.stream(
                    "System",
                    [{"role": "user", "content": "User"}],
                    "gemini-flash",
                    [],
                    temperature=0.7,
                    max_tokens=1024,
                )
            ]
            chunks[-1].response.require_complete()
        assert "private fixture text" not in str(error.value)
    finally:
        await provider.aclose()


@pytest.mark.parametrize("status", [400, 401, 429, 500, 503])
async def test_native_http_failures_use_shared_retry_policy(monkeypatch, wire, status):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(status, json={"error": {"code": status}})

    provider, _ = local_provider(monkeypatch, handler)
    retry = llm_retrying()
    retry.wait = wait_none()
    try:
        with pytest.raises(httpx.HTTPStatusError):
            async for attempt in retry:
                with attempt:
                    await provider.complete("System", "User", "gemini-flash-lite")
    finally:
        await provider.aclose()
    assert len(requests) == (3 if status in {429, 500, 503} else 1)


async def test_tool_checkpoint_recovery_reuses_receipt_and_original_signature(monkeypatch, wire):
    step = tool_step()
    step.agent_config["model"] = "gemini-flash-lite"
    generated = []

    def handler(request):
        if request.url.path.endswith(":countTokens"):
            return httpx.Response(200, json={"totalTokens": 20})
        generated.append(json.loads(request.content))
        return sse_response([wire["tool"] if len(generated) == 1 else wire["text"]])

    provider, _ = local_provider(monkeypatch, handler)
    execute = AsyncMock(return_value='{"value":5}')
    monkeypatch.setattr("app.orchestrator.executor.ToolRuntime.execute", execute)

    async def checkpoint(data):
        step.checkpoint = deepcopy(data)
        if data["turns"] and data["turns"][0]["tools"].get("0", {}).get("state") == "done":
            raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await DAGExecutor(None, lambda _: provider).complete(step, on_checkpoint=checkpoint)
    assert provider._client.is_closed
    provider, _ = local_provider(monkeypatch, handler)
    result = await DAGExecutor(None, lambda _: provider).complete(step)
    assert result.error is None
    assert result.response.content == "The result is 5."
    assert (result.prompt_tokens, result.completion_tokens) == (28, 15)
    assert len(generated) == 2
    assert generated[1]["contents"][1] == wire["tool"]["candidates"][0]["content"]
    assert generated[1]["contents"][2]["parts"][0]["functionResponse"] == {
        "name": "calculator",
        "response": {"value": 5},
    }
    execute.assert_awaited_once()
    assert provider._client.is_closed


async def test_factory_mock_missing_key_and_output_limit(monkeypatch):
    settings = Settings(_env_file=None, llm_provider_mode="mock", gemini_api_key="")
    assert isinstance(create_provider("gemini-flash-lite", settings), MockGeminiProvider)
    settings.llm_provider_mode = "real"
    with pytest.raises(ValueError, match="GEMINI_API_KEY"):
        create_provider("gemini-flash-lite", settings)
    requests = []
    provider, _ = local_provider(monkeypatch, lambda request: requests.append(request))
    try:
        for key, limit in [("gemini-flash", 65537), ("gemini-flash-lite", 0)]:
            with pytest.raises(ValueError, match="output limit"):
                await provider.complete("System", "User", key, max_tokens=limit)
        assert requests == []
    finally:
        await provider.aclose()


async def test_native_planner_waits_for_confirmation(monkeypatch, wire):
    repository, service, run = await planning_run()
    run.planner_config["model"] = "gemini-flash-lite"

    def handler(request):
        if request.url.path.endswith(":countTokens"):
            return httpx.Response(200, json={"totalTokens": 20})
        payload = json.loads(request.content)
        plan = json.loads(payload["contents"][0]["parts"][0]["text"])
        assert payload["generationConfig"]["responseMimeType"] == "application/json"
        result = {
            "summary": "Fixture plan",
            "steps": [
                {
                    key: value
                    for key, value in step.items()
                    if key in {"step_number", "agent_id", "depends_on"}
                }
                | {"subtask": "Review code"}
                for step in plan["steps"]
            ],
        }
        raw = deepcopy(wire["text"])
        raw["candidates"][0]["content"]["parts"] = [{"text": json.dumps(result)}]
        return httpx.Response(200, json=raw)

    provider, _ = local_provider(monkeypatch, handler)
    await PlannerExecutor(repository, LLMPlanner(lambda _: provider)).execute(run)
    assert run.status == "AWAITING_CONFIRMATION"
    assert run.total_tokens == 27
    assert repository.saved_steps[0].attempt == 0
    assert repository.saved_events[-1][0] == "plan:ready"
    assert provider._client.is_closed
    await service.confirm(run.id)
    assert run.status == "IN_PROGRESS"


async def test_closing_stream_releases_http_response(monkeypatch):
    class BlockingBody(httpx.AsyncByteStream):
        closed = False

        async def __aiter__(self):
            yield b'data: {"candidates":[{"content":{"parts":[{"text":"Partial"}]}}]}\n\n'
            await asyncio.Event().wait()

        async def aclose(self):
            self.closed = True

    body = BlockingBody()
    provider, _ = local_provider(monkeypatch, lambda _: httpx.Response(200, stream=body))
    stream = provider.stream(
        "System",
        [{"role": "user", "content": "User"}],
        "gemini-flash",
        [],
        temperature=0.7,
        max_tokens=1024,
    )
    try:
        assert (await anext(stream)).text_delta == "Partial"
        await stream.aclose()
        assert body.closed
    finally:
        await provider.aclose()
