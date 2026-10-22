"""Human decisions stop dispatch, survive recovery, and preserve finished work."""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from app.llm.provider import LLMResponse, ToolCall
from app.llm.providers import MockLLMProvider
from app.models.agent import Agent
from app.orchestrator.executor import DAGExecutor
from app.schemas.decision import DecisionResolution
from app.schemas.event import EventEnvelope
from app.services.models import ModelService
from app.services.runs import RunError, RunService
from pydantic import ValidationError

from test_executor import make_run


def finding_response() -> LLMResponse:
    return LLMResponse.model_validate_json(
        (Path(__file__).parent / "fixtures/llm/decision.json").read_text()
    )


class FindingMock(MockLLMProvider):
    def __init__(self, findings: set[str] | None = None) -> None:
        self.findings = findings if findings is not None else {"Task 1"}
        self.calls: list[str] = []

    async def complete_tools(self, system_prompt, messages, model, tools, **kwargs):
        assert "request_user_decision" in {tool["name"] for tool in tools}
        prompt = messages[-1]["content"]
        self.calls.append(prompt)
        if prompt.split("\n", 1)[0] in self.findings:
            return finding_response()
        return LLMResponse.model_validate_json(
            (Path(__file__).parent / "fixtures/llm/completion.json").read_text()
        )


async def paused_run(dependencies=None):
    repository, run = await make_run(dependencies or [[], [1]])
    provider = FindingMock()
    await DAGExecutor(repository, lambda _: provider).execute(run)
    return repository, run, provider


async def test_pause_is_durable_and_does_not_rerun_completed_review() -> None:
    repository, run, provider = await paused_run()
    assert run.status == "PAUSED"
    assert run.pause_reasons == ["USER_DECISION_REQUIRED"]
    assert run.finished_at is None
    assert [step.status for step in repository.saved_steps] == ["COMPLETED", "PENDING"]
    assert len(provider.calls) == 1
    snapshot = await RunService(repository).read(run)
    assert snapshot.decisions[0].issues[0].title == "Empty email accepted"
    assert snapshot.decisions[0].status == "PENDING"
    for _ in range(2):
        await DAGExecutor(repository, lambda _: provider).execute(run)
    assert len(provider.calls) == len(repository.saved_decisions) == 1
    assert run.total_tokens == run.planning_prompt_tokens + run.planning_completion_tokens + 28
    for name, data in repository.saved_events:
        if name.startswith("decision:"):
            EventEnvelope(event=name, runId=run.id, ts=snapshot.created_at, data=data)


async def test_assignment_inserts_fix_verification_and_updates_explicit_input() -> None:
    repository, run, _ = await paused_run()
    downstream = repository.saved_steps[1]
    downstream.input_transform = "Original review: {{steps.1.output}}"
    source = repository.saved_steps[0]
    original = (source.output, source.attempt, dict(source.agent_config), source.tokens_prompt)
    service = RunService(repository)
    decision = repository.saved_decisions[0]
    payload = DecisionResolution(
        action="assign_fixes",
        agent_id=repository.agent.id,
        task="Implement validation",
        comment="Cover whitespace too",
    )
    await service.resolve_decision(run.id, decision.id, payload)
    assert run.status == "IN_PROGRESS"
    assert len(repository.saved_steps) == 4
    assert decision.followup_step_numbers == [3, 4]
    assert [step["step_number"] for step in run.plan["steps"]] == [1, 3, 4, 2]
    assert downstream.depends_on == [1, 3, 4]
    assert downstream.input is None
    assert repository.saved_steps[2].agent_config["tools"] == repository.agent.tools
    assert repository.saved_steps[3].agent_config == source.agent_config
    assert repository.saved_steps[3].depends_on == [1, 3]
    await service.resolve_decision(run.id, decision.id, payload)
    assert len(repository.saved_steps) == 4
    with pytest.raises(RunError):
        await service.resolve_decision(run.id, decision.id, DecisionResolution(action="continue"))
    provider = FindingMock(set())
    await DAGExecutor(repository, lambda _: provider).execute(run)
    assert run.status == "COMPLETED"
    assert len(provider.calls) == 3
    assert "Implement validation" in provider.calls[0]
    assert "Verify the fixes" in provider.calls[1]
    assert "Latest corrective work:\nFixture result" in provider.calls[2]
    assert "Verification:\nFixture result" in provider.calls[2]
    assert original == (source.output, source.attempt, source.agent_config, source.tokens_prompt)


async def test_continue_skips_corrections_without_repeating_review() -> None:
    repository, run, _ = await paused_run()
    service = RunService(repository)
    decision = repository.saved_decisions[0]
    payload = DecisionResolution(action="continue", comment="Accepted for this release")
    await service.resolve_decision(run.id, decision.id, payload)
    await service.resolve_decision(run.id, decision.id, payload)
    provider = FindingMock(set())
    await DAGExecutor(repository, lambda _: provider).execute(run)
    assert run.status == "COMPLETED"
    assert len(provider.calls) == 1
    assert len(repository.saved_steps) == 2
    assert decision.resolution["comment"] == "Accepted for this release"


async def test_assignment_hands_work_to_different_agent_with_its_own_grants(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository, run, _ = await paused_run()
    source = repository.saved_steps[0]
    developer = Agent(
        id=uuid4(),
        name="Developer",
        role="Fix code",
        system_prompt="Implement fixes",
        model="claude-sonnet",
        temperature=0.3,
        max_tokens=1024,
        context_window=128000,
        tools=["calculator"],
        requires_reconfiguration=False,
    )

    async def agents(ids):
        return {agent.id: agent for agent in (repository.agent, developer) if agent.id in ids}

    monkeypatch.setattr(repository, "agents", agents)
    await RunService(repository).resolve_decision(
        run.id,
        repository.saved_decisions[0].id,
        DecisionResolution(action="assign_fixes", agent_id=developer.id, task="Fix validation"),
    )
    fix, verification = repository.saved_steps[-2:]
    assert fix.agent_id == developer.id != source.agent_id
    assert fix.agent_config["system_prompt"] == "Implement fixes"
    assert fix.agent_config["tools"] == ["calculator"]
    assert verification.agent_id == source.agent_id
    assert verification.agent_config["tools"] == source.agent_config["tools"] == []
    provider = FindingMock(set())
    await DAGExecutor(repository, lambda _: provider).execute(run)
    assert run.status == "COMPLETED"


async def test_cancel_wins_over_late_findings() -> None:
    repository, run = await make_run([[], [1]])
    entered, release = asyncio.Event(), asyncio.Event()

    class LateMock(FindingMock):
        async def complete_tools(self, *args, **kwargs):
            entered.set()
            await release.wait()
            return finding_response()

    execution = asyncio.create_task(DAGExecutor(repository, lambda _: LateMock()).execute(run))
    try:
        await asyncio.wait_for(entered.wait(), 5)
        await RunService(repository).cancel(run.id)
        release.set()
        await execution
    finally:
        execution.cancel()
        await asyncio.gather(execution, return_exceptions=True)
    assert run.status == "CANCELLED"
    assert repository.saved_decisions == []
    assert not any(name == "decision:required" for name, _ in repository.saved_events)


@pytest.mark.parametrize("direct", [True, False])
async def test_cancellation_resolves_decisions_and_never_resumes(direct: bool) -> None:
    repository, run, provider = await paused_run()
    service = RunService(repository)
    decision = repository.saved_decisions[0]
    if direct:
        await service.cancel(run.id)
    else:
        payload = DecisionResolution(action="cancel", comment="Stop here")
        await service.resolve_decision(run.id, decision.id, payload)
        await service.resolve_decision(run.id, decision.id, payload)
        assert decision.resolution["comment"] == "Stop here"
    assert run.status == "CANCELLED"
    assert run.pause_reasons == []
    assert decision.status == "RESOLVED"
    assert repository.saved_steps[0].status == "COMPLETED"
    assert repository.saved_steps[1].status == "CANCELLED"
    await DAGExecutor(repository, lambda _: provider).execute(run)
    assert len(provider.calls) == 1


async def test_parallel_work_drains_without_dispatching_dependants(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository, run = await make_run([[], [], [1], [2]])
    active = asyncio.Event()
    release = asyncio.Event()
    requested = asyncio.Event()
    original_emit = repository.emit

    def emit(run_id, name, data):
        original_emit(run_id, name, data)
        if name == "decision:required":
            requested.set()

    monkeypatch.setattr(repository, "emit", emit)

    class ParallelMock(FindingMock):
        async def complete_tools(self, system_prompt, messages, model, tools, **kwargs):
            if messages[-1]["content"].startswith("Task 1"):
                await active.wait()
            else:
                active.set()
                await release.wait()
            return await super().complete_tools(system_prompt, messages, model, tools, **kwargs)

    provider = ParallelMock()
    execution = asyncio.create_task(DAGExecutor(repository, lambda _: provider).execute(run))
    try:
        await asyncio.wait_for(requested.wait(), 5)
        assert run.status == "IN_PROGRESS"
        with pytest.raises(RunError, match="Wait for active steps"):
            await RunService(repository).resolve_decision(
                run.id,
                repository.saved_decisions[0].id,
                DecisionResolution(action="continue"),
            )
        release.set()
        await execution
    finally:
        execution.cancel()
        await asyncio.gather(execution, return_exceptions=True)
    assert run.status == "PAUSED"
    assert [step.status for step in repository.saved_steps] == [
        "COMPLETED",
        "COMPLETED",
        "PENDING",
        "PENDING",
    ]
    assert len(provider.calls) == 2


async def test_all_parallel_decisions_must_be_resolved() -> None:
    repository, run = await make_run([[], [], [1, 2]])
    provider = FindingMock({"Task 1", "Task 2"})
    await DAGExecutor(repository, lambda _: provider).execute(run)
    assert len(repository.saved_decisions) == 2
    service = RunService(repository)
    first, second = repository.saved_decisions
    await service.resolve_decision(run.id, first.id, DecisionResolution(action="continue"))
    assert run.status == "PAUSED"
    await DAGExecutor(repository, lambda _: provider).execute(run)
    assert len(provider.calls) == 2
    await service.resolve_decision(run.id, second.id, DecisionResolution(action="continue"))
    await DAGExecutor(repository, lambda _: provider).execute(run)
    assert run.status == "COMPLETED"


async def test_multiple_assignments_form_acyclic_followups_and_keep_original_context() -> None:
    repository, run = await make_run([[], [], [1, 2]])
    await DAGExecutor(repository, lambda _: FindingMock({"Task 1", "Task 2"})).execute(run)
    service = RunService(repository)
    for decision in repository.saved_decisions:
        await service.resolve_decision(
            run.id,
            decision.id,
            DecisionResolution(
                action="assign_fixes",
                agent_id=repository.agent.id,
                task="Correct findings",
            ),
        )
    provider = FindingMock(set())
    await DAGExecutor(repository, lambda _: provider).execute(run)
    assert run.status == "COMPLETED"
    assert len(repository.saved_steps) == 7
    assert len(provider.calls) == 5
    assert repository.saved_steps[0].attempt == repository.saved_steps[1].attempt == 1


async def test_followup_recheck_can_request_another_decision() -> None:
    repository, run, _ = await paused_run()
    first = repository.saved_decisions[0]
    service = RunService(repository)
    await service.resolve_decision(
        run.id,
        first.id,
        DecisionResolution(
            action="assign_fixes",
            agent_id=repository.agent.id,
            task="Fix it",
        ),
    )
    provider = FindingMock(
        {
            "Verify the fixes against the original findings. "
            "Request another user decision if issues remain."
        }
    )
    await DAGExecutor(repository, lambda _: provider).execute(run)
    assert run.status == "PAUSED"
    assert len(repository.saved_decisions) == 2
    assert repository.saved_decisions[1].source_step_number == 4
    assert repository.saved_steps[1].status == "PENDING"
    await service.resolve_decision(
        run.id, repository.saved_decisions[1].id, DecisionResolution(action="continue")
    )
    await DAGExecutor(repository, lambda _: FindingMock(set())).execute(run)
    assert run.status == "COMPLETED"


async def test_recovery_during_drain_preserves_other_branch_receipts() -> None:
    repository, run, _ = await paused_run([[], [], [1, 2]])
    # Simulate worker loss while an independent branch has a durable terminal response.
    other = repository.saved_steps[1]
    other.status = "IN_PROGRESS"
    other.input = "Original branch input"
    other.checkpoint = {
        "turns": [
            {
                "response": finding_response()
                .model_copy(
                    update={
                        "content": "Saved independent result",
                        "tool_calls": [],
                        "stop_reason": "stop",
                    }
                )
                .model_dump(mode="json"),
                "tools": {},
            }
        ],
        "prompt_tokens": 20,
        "completion_tokens": 8,
        "duration_ms": 1,
        "provider_pending": False,
    }
    other.tokens_prompt = 20
    other.tokens_completion = 8
    other.execution_time_ms = 1
    run.status = "IN_PROGRESS"
    await DAGExecutor(repository, lambda _: FindingMock(set())).execute(run)
    assert run.status == "PAUSED"
    assert other.status == "PENDING"
    original_checkpoint = dict(other.checkpoint)
    await RunService(repository).resolve_decision(
        run.id,
        repository.saved_decisions[0].id,
        DecisionResolution(action="assign_fixes", agent_id=repository.agent.id, task="Fix it"),
    )
    assert other.input == "Original branch input"
    assert other.checkpoint == original_checkpoint
    assert other.depends_on == []
    provider = FindingMock(set())
    await DAGExecutor(repository, lambda _: provider).execute(run)
    assert run.status == "COMPLETED"
    assert other.output == "Saved independent result"
    assert other.tokens_prompt == 20


async def test_assignment_rejects_missing_or_unavailable_agent() -> None:
    repository, run, _ = await paused_run()
    decision = repository.saved_decisions[0]
    service = RunService(repository)
    with pytest.raises(RunError, match="no longer exists"):
        await service.resolve_decision(
            run.id,
            decision.id,
            DecisionResolution(
                action="assign_fixes",
                agent_id=uuid4(),
                task="Fix",
            ),
        )
    repository.agent.requires_reconfiguration = True
    with pytest.raises(RunError, match="available"):
        await service.resolve_decision(
            run.id,
            decision.id,
            DecisionResolution(
                action="assign_fixes",
                agent_id=repository.agent.id,
                task="Fix",
            ),
        )
    assert decision.status == "PENDING"
    assert run.status == "PAUSED"
    assert len(repository.saved_steps) == 2


async def test_model_recovery_cannot_clear_user_blocker(monkeypatch: pytest.MonkeyPatch) -> None:
    repository, run, provider = await paused_run()
    run.pause_reasons.append("MODEL_UNAVAILABLE")
    available = AsyncMock(return_value=set())
    monkeypatch.setattr(ModelService, "available", available)
    await DAGExecutor(repository, lambda _: provider).execute(run)
    available.assert_not_awaited()
    await RunService(repository).resolve_decision(
        run.id,
        repository.saved_decisions[0].id,
        DecisionResolution(action="continue"),
    )
    await DAGExecutor(repository, lambda _: provider).execute(run)
    assert run.status == "PAUSED"
    assert run.pause_reasons == ["MODEL_UNAVAILABLE"]
    assert len(provider.calls) == 1


@pytest.mark.parametrize("invalid", ["mixed", "extra", "missing", "unicode"])
async def test_invalid_decisions_fail_closed_without_running_tools(invalid: str) -> None:
    repository, run = await make_run([[]])
    response = finding_response()
    if invalid == "mixed":
        response.tool_calls.append(
            ToolCall(id="other", name="calculator", arguments={"expression": "1+1"})
        )
    elif invalid == "extra":
        response.tool_calls[0].arguments["tools"] = ["terminal_access"]
    elif invalid == "missing":
        response.tool_calls[0].arguments["issues"] = []
    else:
        response.tool_calls[0].arguments["issues"][0]["title"] = "bad\x00text"

    class InvalidMock(FindingMock):
        async def complete_tools(self, *args, **kwargs):
            return response

    await DAGExecutor(repository, lambda _: InvalidMock()).execute(run)
    assert run.status == "FAILED"
    assert repository.saved_steps[0].error["code"] == "invalid_decision_request"
    assert not repository.saved_decisions
    assert not any(name == "agent:tool_call" for name, _ in repository.saved_events)
    assert run.total_tokens == run.planning_prompt_tokens + run.planning_completion_tokens + 28


@pytest.mark.parametrize(
    "payload",
    [
        {"action": "assign_fixes"},
        {"action": "continue", "agent_id": str(uuid4())},
        {"action": "cancel", "tools": ["terminal_access"]},
    ],
)
def test_resolution_contract_rejects_ambiguous_or_privileged_input(payload) -> None:
    with pytest.raises(ValidationError):
        DecisionResolution.model_validate(payload)
