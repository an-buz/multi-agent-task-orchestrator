"""Behavior tests for dependency execution using mock data exclusively."""

import asyncio
import json
from pathlib import Path

import pytest
from app.llm.provider import LLMResponse
from app.llm.providers import MockLLMProvider
from app.models.run import Run
from app.orchestrator.executor import DAGExecutor, build_input
from app.schemas.run import RunCreate, RunPlanUpdate
from app.services.runs import RunService

from test_runs import MemoryRunRepository


class RecordingMock(MockLLMProvider):
    def __init__(self, fail: str | None = None) -> None:
        self.calls: list[str] = []
        self.active = 0
        self.peak = 0
        self.fail = fail

    async def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str,
        *,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        assert temperature == 0.2
        assert max_tokens == 1024
        assert system_prompt == "Be precise"
        self.calls.append(user_prompt)
        self.active += 1
        self.peak = max(self.peak, self.active)
        try:
            await asyncio.sleep(0)
            if self.fail and user_prompt.startswith(self.fail):
                raise ValueError("private provider details")
            fixture = json.loads(
                (Path(__file__).parent / "fixtures/llm/completion.json").read_text()
            )
            return LLMResponse.model_validate(fixture)
        finally:
            self.active -= 1


async def make_run(dependencies: list[list[int]]) -> tuple[MemoryRunRepository, Run]:
    repository = MemoryRunRepository()
    repository.saved_workflow.steps = [
        {"step_number": number, "agent_id": str(repository.agent.id), "depends_on": values}
        for number, values in enumerate(dependencies, 1)
    ]
    service = RunService(repository)
    created = await service.create(
        RunCreate(
            workflow_id=repository.saved_workflow.id, task="Analyze", context_text="User context"
        )
    )
    for step in repository.saved_steps:
        step.subtask = f"Task {step.step_number}"
    await service.confirm(created.id)
    return repository, repository.runs[created.id]


@pytest.mark.parametrize(
    ("dependencies", "peak"),
    [
        ([[], [1], [2]], 1),
        ([[], [], [1, 2]], 2),
        ([[], [1], [1], [2, 3]], 2),
    ],
)
async def test_execution_order_inputs_and_metrics(dependencies: list[list[int]], peak: int) -> None:
    repository, run = await make_run(dependencies)
    provider = RecordingMock()
    await DAGExecutor(repository, lambda _: provider).execute(run)
    assert run.status == "COMPLETED"
    assert provider.peak == peak
    assert run.total_tokens == 28 * len(dependencies)
    assert run.total_time_ms == sum(step.execution_time_ms for step in repository.saved_steps)
    for step in repository.saved_steps:
        assert step.status == "COMPLETED"
        assert step.input and "User context" in step.input
        for number in step.depends_on:
            assert f"Step {number}:\nFixture result" in step.input
            assert provider.calls.index(
                repository.saved_steps[number - 1].input or ""
            ) < provider.calls.index(step.input)
    assert run.final_report and "Fixture result" in run.final_report
    await DAGExecutor(repository, lambda _: provider).execute(run)
    assert len(provider.calls) == len(dependencies)


async def test_failed_branch_does_not_stop_independent_steps() -> None:
    repository, run = await make_run([[], [], [1], [2]])
    provider = RecordingMock(fail="Task 1")
    await DAGExecutor(repository, lambda _: provider).execute(run)
    assert run.status == "FAILED"
    assert [step.status for step in repository.saved_steps] == [
        "FAILED",
        "COMPLETED",
        "PENDING",
        "COMPLETED",
    ]
    assert repository.saved_steps[0].error == {
        "code": "llm_error",
        "message": "The step could not be completed.",
    }
    assert run.total_tokens == 56


async def test_parallel_limit_and_resume_skip_completed_steps() -> None:
    repository, run = await make_run([[], [], [], [1, 2, 3]])
    first = repository.saved_steps[0]
    first.status = "COMPLETED"
    first.output = "Already complete"
    first.tokens_prompt = 7
    repository.saved_steps[1].status = "IN_PROGRESS"
    provider = RecordingMock()
    await DAGExecutor(repository, lambda _: provider, max_parallel_steps=1).execute(run)
    assert provider.peak == 1
    assert len(provider.calls) == 3
    assert first.output == "Already complete"
    assert run.total_tokens == 7 + 28 * 3


async def test_worker_cannot_execute_unconfirmed_plan() -> None:
    repository, run = await make_run([[]])
    run.status = "AWAITING_CONFIRMATION"
    provider = RecordingMock()
    await DAGExecutor(repository, lambda _: provider).execute(run)
    assert provider.calls == []
    assert run.final_report is None


async def test_invalid_template_fails_step_without_calling_provider() -> None:
    repository, run = await make_run([[], []])
    repository.saved_steps[0].input_transform = "{{steps.2.output}}"
    provider = RecordingMock()
    await DAGExecutor(repository, lambda _: provider).execute(run)
    assert run.status == "FAILED"
    assert len(provider.calls) == 1
    assert (
        repository.saved_steps[0].error
        and repository.saved_steps[0].error["code"] == "invalid_input_template"
    )
    assert repository.saved_steps[1].status == "COMPLETED"


async def test_snapshot_survives_agent_changes_and_plan_edit() -> None:
    repository = MemoryRunRepository()
    service = RunService(repository)
    created = await service.create(
        RunCreate(workflow_id=repository.saved_workflow.id, task="Analyze")
    )
    repository.agent.system_prompt = "Changed"
    repository.agent.max_tokens = 5
    created.plan.steps[0].subtask = "Edited subtask"
    await service.update_plan(created.id, RunPlanUpdate(steps=created.plan.steps))
    step = repository.saved_steps[0]
    assert step.subtask == "Edited subtask"
    assert step.agent_config["system_prompt"] == "Be precise"
    assert step.agent_config["max_tokens"] == 1024


async def test_templates_only_allow_declared_dependencies() -> None:
    repository, run = await make_run([[], [1]])
    first, second = repository.saved_steps
    first.output = "Dependency {{task}}"
    second.input_transform = "{{ task }} | {{subtask}} | {{context}} | {{ steps.1.output }}"
    assert (
        build_input(run, second, {1: first, 2: second})
        == "Analyze | Task 2 | User context | Dependency {{task}}"
    )
    for invalid in ("{{steps.2.output}}", "{{context.__class__}}", "{% include 'file' %}"):
        second.input_transform = invalid
        with pytest.raises(ValueError):
            build_input(run, second, {1: first, 2: second})


async def test_cancellation_does_not_leave_detached_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    repository, run = await make_run([[], []])
    waiting = asyncio.Event()
    provider = MockLLMProvider()

    async def blocked(*args: object, **kwargs: object) -> LLMResponse:
        waiting.set()
        await asyncio.Event().wait()
        raise AssertionError("unreachable")

    monkeypatch.setattr(provider, "complete", blocked)
    task = asyncio.create_task(DAGExecutor(repository, lambda _: provider).execute(run))
    await waiting.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert all(step.status == "IN_PROGRESS" for step in repository.saved_steps)
