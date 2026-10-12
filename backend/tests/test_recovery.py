"""Crash boundaries and safe retention regressions using fixture-backed mocks."""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock

import pytest
from app.llm.provider import LLMResponse
from app.orchestrator.executor import DAGExecutor
from app.orchestrator.planner import LLMPlanner, PlannerExecutor
from app.services.runs import RunService
from app.tools.containers import EXPIRES_LABEL, MANAGED_LABEL, SCOPE_LABEL, cleanup_containers
from app.workers.tasks import cleanup_resources

from test_executor import make_run
from test_planner import ScriptedMock, planning_run
from test_tools import FixtureTools


async def interrupt_after_save(repository, executor, run, predicate):
    original_save = repository.save

    async def save():
        await original_save()
        if predicate():
            raise asyncio.CancelledError

    repository.save = save
    try:
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(executor.execute(run), 3)
    finally:
        repository.save = original_save


async def test_terminal_response_checkpoint_survives_interruption_without_repeat() -> None:
    repository, run = await make_run([[], [1]])
    provider = ScriptedMock([])
    # Use a normal fixture completion without planner-specific assertions.
    response = LLMResponse(content="Saved response", usage={"input_tokens": 12, "output_tokens": 4})
    complete = AsyncMock(return_value=response)
    provider.complete = complete
    executor = DAGExecutor(repository, lambda _: provider)
    await interrupt_after_save(
        repository, executor, run, lambda: bool(repository.saved_steps[0].checkpoint)
    )
    first = repository.saved_steps[0]
    assert first.tokens_prompt == 12 and first.tokens_completion == 4
    assert first.status == "IN_PROGRESS"
    original_factory = Mock(return_value=provider)
    await DAGExecutor(repository, original_factory).execute(run)
    assert run.status == "COMPLETED"
    # Only the pending dependant needs a new request; the saved terminal turn is replayed.
    assert complete.await_count == 2
    assert original_factory.call_count == 1
    assert first.tokens_prompt == 12 and first.tokens_completion == 4
    assert not first.checkpoint


@pytest.mark.parametrize("boundary", ["response", "started", "done"])
async def test_tool_checkpoint_recovery(monkeypatch: pytest.MonkeyPatch, boundary: str) -> None:
    repository, run = await make_run([[]])
    step = repository.saved_steps[0]
    step.agent_config["tools"] = ["calculator"]
    provider = FixtureTools()
    execute_tool = AsyncMock(return_value=json.dumps({"value": 20.0}))
    monkeypatch.setattr("app.orchestrator.executor.ToolRuntime.execute", execute_tool)

    def reached():
        checkpoint = step.checkpoint or {}
        if not checkpoint:
            return False
        receipts = checkpoint["turns"][0]["tools"]
        return (
            not receipts
            if boundary == "response"
            else receipts.get("0", {}).get("state") == boundary
        )

    await interrupt_after_save(
        repository, DAGExecutor(repository, lambda _: provider), run, reached
    )
    assert step.tokens_prompt == 10 and step.tokens_completion == 4
    resumed = FixtureTools()
    resumed.calls = 1
    await DAGExecutor(repository, lambda _: resumed).execute(run)
    if boundary == "started":
        assert run.status == "FAILED"
        assert step.error["code"] == "tool_execution_interrupted"
        execute_tool.assert_not_awaited()
        assert resumed.calls == 1
        await RunService(repository).retry(run.id, 1)
        await DAGExecutor(repository, lambda _: FixtureTools()).execute(run)
        assert run.status == "COMPLETED"
        assert step.tokens_prompt == 38 and step.tokens_completion == 14
    else:
        assert run.status == "COMPLETED"
        execute_tool.assert_awaited_once()
        assert step.tokens_prompt == 28 and step.tokens_completion == 10
        assert resumed.calls == 2


@pytest.mark.parametrize("invalid_first", [False, True])
async def test_planner_response_checkpoint_and_repair_resume(invalid_first: bool) -> None:
    repository, _, run = await planning_run()
    provider = ScriptedMock(["invalid"] if invalid_first else [])
    await interrupt_after_save(
        repository,
        PlannerExecutor(repository, LLMPlanner(lambda _: provider)),
        run,
        lambda: bool(run.planning_checkpoint),
    )
    assert run.status == "PLANNING"
    assert run.total_tokens == 28
    resumed = ScriptedMock([])
    factory = Mock(return_value=resumed)
    await PlannerExecutor(repository, LLMPlanner(factory)).execute(run)
    assert run.status == "AWAITING_CONFIRMATION"
    assert run.total_tokens == (56 if invalid_first else 28)
    assert factory.call_count == int(invalid_first)
    assert len(resumed.requests) == int(invalid_first)
    assert not run.planning_checkpoint
    assert repository.saved_steps[0].attempt == 0


async def test_recovery_cannot_bypass_an_already_exceeded_budget() -> None:
    repository, run = await make_run([[]])
    response = LLMResponse(content="Saved", usage={"input_tokens": 10, "output_tokens": 4})
    step = repository.saved_steps[0]
    step.checkpoint = {
        "turns": [{"response": response.model_dump(mode="json"), "tools": {}}],
        "prompt_tokens": 10,
        "completion_tokens": 4,
        "duration_ms": 1,
    }
    step.tokens_prompt, step.tokens_completion, step.execution_time_ms = 10, 4, 1
    step.status = "IN_PROGRESS"
    DAGExecutor.update_totals(run, [step])
    run.planner_config = {**run.planner_config, "token_budget": run.total_tokens - 1}
    factory = Mock(side_effect=AssertionError("No new provider request is allowed"))
    await DAGExecutor(repository, factory).execute(run)
    assert run.status == "FAILED"
    assert step.error["code"] == "token_budget_exceeded"
    assert step.tokens_prompt == 10
    factory.assert_not_called()


async def test_container_sweeper_preserves_live_foreign_and_unlabelled_containers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CODE_EXECUTOR_BACKEND", "docker")
    from app.core.config import get_settings

    get_settings.cache_clear()
    now = datetime.now(UTC)
    old = (now - timedelta(hours=2)).isoformat()
    labels = {MANAGED_LABEL: "code", SCOPE_LABEL: "local", EXPIRES_LABEL: str(now.timestamp() - 1)}
    inspect = {
        "aaa": (labels, old),
        "bbb": ({**labels, EXPIRES_LABEL: str(now.timestamp() + 100)}, old),
        "ccc": ({**labels, SCOPE_LABEL: "other"}, old),
        "ddd": ({}, old),
        "eee": (labels, now.isoformat()),
        "fff": ({**labels, EXPIRES_LABEL: "nan"}, old),
    }
    removed = []

    async def command(*args):
        if args[0] == "ps":
            return "\n".join(inspect)
        if args[0] == "inspect":
            value, created = inspect[args[-1]]
            return json.dumps(value) + "|" + created
        assert args[:2] == ("rm", "--force")
        removed.append(args[-1])
        return ""

    monkeypatch.setattr("app.tools.containers.docker_command", command)
    assert await cleanup_containers(now) == 1
    assert removed == ["aaa"]


async def test_database_outage_does_not_skip_orphan_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.workers.tasks.async_session_factory", Mock(side_effect=OSError("fixture"))
    )
    sweep = AsyncMock(return_value=0)
    monkeypatch.setattr("app.workers.tasks.cleanup_containers", sweep)
    await cleanup_resources({})
    sweep.assert_awaited_once()
