"""Streaming, retries and cancellation with fixture-backed mock responses only."""

import asyncio
import json
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from app.core.config import get_settings
from app.llm.provider import LLMChunk, LLMResponse
from app.llm.providers import MockLLMProvider
from app.orchestrator.executor import DAGExecutor
from app.schemas.event import EventEnvelope
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_none

from test_executor import make_run


def fixture_response() -> LLMResponse:
    return LLMResponse.model_validate_json(
        (Path(__file__).parent / "fixtures/llm/completion.json").read_text()
    )


class FixtureStream(MockLLMProvider):
    def __init__(self, fail_first: bool = False, hang: bool = False) -> None:
        self.calls = 0
        self.closed = 0
        self.fail_first = fail_first
        self.hang = hang

    async def stream(
        self,
        system_prompt: str,
        messages: list[dict[str, Any]],
        model: str,
        tools: list[dict[str, Any]],
        *,
        temperature: float,
        max_tokens: int,
    ) -> AsyncGenerator[LLMChunk]:
        self.calls += 1
        try:
            yield LLMChunk(
                text_delta="Discard me" if self.fail_first and self.calls == 1 else "Fixture "
            )
            if self.fail_first and self.calls == 1:
                raise TimeoutError("Private prompt")
            if self.hang:
                await asyncio.Event().wait()
            await asyncio.sleep(0.01)
            yield LLMChunk(text_delta="result")
            yield LLMChunk(response=fixture_response())
        finally:
            self.closed += 1


async def test_mock_stream_preserves_text_usage_and_tools() -> None:
    provider = MockLLMProvider()
    chunks = [
        chunk
        async for chunk in provider.stream(
            "Be precise",
            [{"role": "user", "content": "Привет 🌍"}],
            "claude-sonnet",
            [],
            temperature=0.2,
            max_tokens=1024,
        )
    ]
    terminal = chunks[-1].response
    assert terminal is not None
    assert "".join(chunk.text_delta for chunk in chunks) == terminal.content
    assert terminal.content == "Mock response: Привет 🌍"
    assert terminal.usage.output_tokens == 5
    assert sum(chunk.response is not None for chunk in chunks) == 1


async def test_stream_persists_partial_output_before_completion() -> None:
    repository, run = await make_run([[]])
    provider = FixtureStream()
    snapshots: list[tuple[str, str | None]] = []
    original_save = repository.save

    async def save() -> None:
        snapshots.append((repository.saved_steps[0].status, repository.saved_steps[0].output))
        await original_save()

    repository.save = save  # type: ignore[method-assign]
    await DAGExecutor(repository, lambda _: provider).execute(run)
    chunks = [data for event, data in repository.saved_events if event == "agent:stream_chunk"]
    assert chunks[0]["reset"] is True
    assert chunks[-1]["output"] == "Fixture result"
    assert ("IN_PROGRESS", "Fixture result") in snapshots
    assert ("IN_PROGRESS", "Fixture ") in snapshots
    assert run.status == "COMPLETED"
    assert repository.saved_steps[0].tokens_prompt == fixture_response().usage.input_tokens
    assert provider.closed == 1
    for data in chunks:
        EventEnvelope(event="agent:stream_chunk", runId=run.id, ts=datetime.now(UTC), data=data)
    names = [event for event, _ in repository.saved_events]
    assert names.index("agent:stream_chunk") < names.index("agent:completed")


async def test_transient_stream_retry_resets_partial_text(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.orchestrator.executor.llm_retrying",
        lambda: AsyncRetrying(
            stop=stop_after_attempt(3),
            wait=wait_none(),
            retry=retry_if_exception_type(TimeoutError),
            reraise=True,
        ),
    )
    repository, run = await make_run([[]])
    provider = FixtureStream(fail_first=True)
    await DAGExecutor(repository, lambda _: provider).execute(run)
    chunks = [data for event, data in repository.saved_events if event == "agent:stream_chunk"]
    assert sum(data["reset"] for data in chunks) == 2
    assert chunks[-1]["output"] == "Fixture result"
    assert repository.saved_steps[0].output == "Fixture result"
    assert provider.closed == 2
    assert run.status == "COMPLETED"


async def test_cancellation_stops_stream_and_preserves_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(get_settings(), "run_poll_interval", 0.001)
    repository, run = await make_run([[]])
    provider = FixtureStream(hang=True)
    original_save = repository.save

    async def save() -> None:
        await original_save()
        if repository.saved_steps[0].output == "Fixture ":
            run.status = "CANCELLED"

    repository.save = save  # type: ignore[method-assign]
    await asyncio.wait_for(DAGExecutor(repository, lambda _: provider).execute(run), 1)
    assert run.status == "CANCELLED"
    assert repository.saved_steps[0].output == "Fixture "
    assert provider.closed == 1
    assert not any(event == "agent:completed" for event, _ in repository.saved_events)
    assert run.final_report is None


async def test_incomplete_stream_fails_without_fabricating_usage() -> None:
    class Incomplete(FixtureStream):
        async def stream(
            self,
            system_prompt: str,
            messages: list[dict[str, Any]],
            model: str,
            tools: list[dict[str, Any]],
            *,
            temperature: float,
            max_tokens: int,
        ) -> AsyncGenerator[LLMChunk]:
            yield LLMChunk(text_delta="Partial")

    repository, run = await make_run([[]])
    await DAGExecutor(repository, lambda _: Incomplete()).execute(run)
    assert run.status == "FAILED"
    step = repository.saved_steps[0]
    assert step.output == "Partial"
    assert step.tokens_prompt == step.tokens_completion == 0
    assert step.error and "Private" not in json.dumps(step.error)
