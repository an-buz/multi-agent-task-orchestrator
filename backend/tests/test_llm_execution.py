"""Transient failures use one retry policy; SDK adapters preserve agent options."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from app.llm.providers import AnthropicProvider, OpenAIProvider
from app.llm.retry import llm_retrying
from tenacity import wait_none


class HTTPFailure(Exception):
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


@pytest.mark.parametrize("exception", [HTTPFailure(429), HTTPFailure(503), TimeoutError()])
async def test_transient_failures_retry_three_times(exception: Exception) -> None:
    call = AsyncMock(side_effect=[exception, exception, "success"])
    retry = llm_retrying()
    retry.wait = wait_none()
    async for attempt in retry:
        with attempt:
            result = await call()
    assert result == "success"
    assert call.await_count == 3


async def test_retry_exhaustion_and_non_retryable_failure() -> None:
    for failure, expected in [(HTTPFailure(429), 3), (HTTPFailure(401), 1)]:
        call = AsyncMock(side_effect=failure)
        retry = llm_retrying()
        retry.wait = wait_none()
        with pytest.raises(HTTPFailure):
            async for attempt in retry:
                with attempt:
                    await call()
        assert call.await_count == expected


async def test_anthropic_adapter_parameters_and_usage(monkeypatch: pytest.MonkeyPatch) -> None:
    create = AsyncMock(
        return_value=SimpleNamespace(
            content=[SimpleNamespace(type="text", text="Fixture")],
            usage=SimpleNamespace(input_tokens=17, output_tokens=11),
        )
    )
    constructor = Mock(return_value=SimpleNamespace(messages=SimpleNamespace(create=create)))
    monkeypatch.setattr("app.llm.providers.AsyncAnthropic", constructor)
    response = await AnthropicProvider("test-placeholder").complete(
        "System",
        "User",
        "claude-sonnet",
        temperature=0.2,
        max_tokens=1024,
    )
    constructor.assert_called_once_with(api_key="test-placeholder", max_retries=0, timeout=60.0)
    assert create.call_args.kwargs["temperature"] == 0.2
    assert create.call_args.kwargs["max_tokens"] == 1024
    assert response.usage.input_tokens == 17


async def test_openai_adapter_parameters_and_usage(monkeypatch: pytest.MonkeyPatch) -> None:
    create = AsyncMock(
        return_value=SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="Fixture"))],
            usage=SimpleNamespace(prompt_tokens=17, completion_tokens=11),
        )
    )
    constructor = Mock(
        return_value=SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=create))
        )
    )
    monkeypatch.setattr("app.llm.providers.AsyncOpenAI", constructor)
    response = await OpenAIProvider("test-placeholder").complete(
        "System",
        "User",
        "gpt-4o",
        temperature=0.2,
        max_tokens=1024,
    )
    constructor.assert_called_once_with(api_key="test-placeholder", max_retries=0, timeout=60.0)
    assert create.call_args.kwargs["temperature"] == 0.2
    assert create.call_args.kwargs["max_tokens"] == 1024
    assert response.usage.output_tokens == 11
