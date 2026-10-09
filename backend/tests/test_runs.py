"""Tests for the run plan review API."""

from collections.abc import AsyncIterator, Generator
from datetime import UTC, datetime
from typing import Any, cast
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from app.api.v1.runs import get_run_service
from app.db.run_repository import RunRepository
from app.main import app
from app.models.agent import Agent
from app.models.run import Run
from app.models.run_step import RunStep
from app.models.workflow import Workflow
from app.orchestrator.planner import PlannerExecutor
from app.schemas.run import RunCreate
from app.services.runs import RunError, RunService
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

WORKFLOW_ID = UUID("4ac67d20-05d0-4246-a33b-51b88a17f51f")
AGENT_ID = UUID("025010d8-e77f-494b-bb42-e107c903970d")


class MemoryRunRepository(RunRepository):
    """Repository double for transport and scheduler tests without external I/O."""

    def __init__(self) -> None:
        now = datetime.now(UTC)
        self.saved_workflow = Workflow(
            id=WORKFLOW_ID,
            title="Repository review",
            execution_type="sequential",
            steps=[{"step_number": 1, "agent_id": str(AGENT_ID), "depends_on": []}],
            graph_layout={},
        )
        self.agent = Agent(
            id=AGENT_ID,
            name="Reviewer",
            role="Review code changes",
            system_prompt="Be precise",
            model="claude-sonnet",
            temperature=0.2,
            max_tokens=1024,
            context_window=128000,
            tools=[],
            created_at=now,
            updated_at=now,
        )
        self.runs: dict[UUID, Run] = {}
        self.saved_steps: list[RunStep] = []
        self.saved_events: list[tuple[str, dict[str, Any]]] = []
        self.session = cast(AsyncSession, AsyncMock())

    def add(self, value: Run | RunStep) -> None:
        if isinstance(value, Run):
            value.created_at = datetime.now(UTC)
            self.runs[value.id] = value
        else:
            self.saved_steps.append(value)

    async def get(self, run_id: UUID, *, lock: bool = False) -> Run | None:
        return self.runs.get(run_id)

    async def workflow(self, workflow_id: UUID) -> Workflow | None:
        return self.saved_workflow if workflow_id == self.saved_workflow.id else None

    async def agents(self, agent_ids: set[UUID]) -> dict[UUID, Agent]:
        return {self.agent.id: self.agent} if self.agent.id in agent_ids else {}

    async def steps(self, run_id: UUID) -> list[RunStep]:
        return [step for step in self.saved_steps if step.run_id == run_id]

    async def list(self, limit: int, offset: int) -> tuple[list[Run], int]:
        return list(self.runs.values())[offset : offset + limit], len(self.runs)

    async def save(self) -> None:
        return None

    async def delete(self, run: Run) -> None:
        del self.runs[run.id]
        self.saved_steps = [step for step in self.saved_steps if step.run_id != run.id]

    def emit(self, run_id: UUID, event: str, data: dict[str, Any]) -> None:
        self.saved_events.append((event, data))


@pytest.mark.parametrize(
    ("status", "allowed"),
    [
        ("AWAITING_CONFIRMATION", True),
        ("COMPLETED", True),
        ("FAILED", True),
        ("CANCELLED", True),
        ("PLANNING", False),
        ("IN_PROGRESS", False),
        ("PENDING", False),
    ],
)
async def test_delete_run_state_rules(status: str, allowed: bool) -> None:
    repository = MemoryRunRepository()
    run = Run(id=uuid4(), status=status)
    repository.add(run)
    service = RunService(repository)
    if allowed:
        await service.delete(run.id)
        assert await repository.get(run.id) is None
        with pytest.raises(RunError) as missing:
            await service.delete(run.id)
        assert missing.value.status_code == 404
    else:
        with pytest.raises(RunError) as active:
            await service.delete(run.id)
        assert active.value.status_code == 409
        assert await repository.get(run.id) is run


@pytest.fixture
def test_client(monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient, Any]:
    repository = MemoryRunRepository()
    app.dependency_overrides[get_run_service] = lambda: RunService(repository)
    monkeypatch.setattr("app.api.v1.runs.enqueue_run", AsyncMock())

    async def plan_immediately(run_id: UUID) -> None:
        await PlannerExecutor(repository).execute(repository.runs[run_id])

    monkeypatch.setattr("app.api.v1.runs.enqueue_plan", plan_immediately)
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.clear()


def test_run_plan_can_be_created_edited_and_confirmed(test_client: TestClient) -> None:
    """A user can review and edit the mock plan before confirming it."""
    created = test_client.post(
        "/api/v1/runs",
        json={
            "workflow_id": str(WORKFLOW_ID),
            "task": "Review the latest changes",
            "context_text": "Focus on API contracts",
        },
    )
    assert created.status_code == 201
    run = created.json()
    assert run["status"] == "PLANNING"
    assert run["plan"] is None
    run = test_client.get(f"/api/v1/runs/{run['id']}").json()
    assert run["status"] == "AWAITING_CONFIRMATION"
    assert run["plan"]["steps"][0]["agent_name"] == "Reviewer"
    assert run["plan"]["steps"][0]["subtask"] == ("Review code changes: Review the latest changes")

    run_id = run["id"]
    run["plan"]["steps"][0]["subtask"] = "Review only the API contract changes"
    edited = test_client.patch(f"/api/v1/runs/{run_id}/plan", json=run["plan"])
    assert edited.status_code == 200
    assert edited.json()["plan"]["steps"][0]["subtask"] == ("Review only the API contract changes")

    detail = test_client.get(f"/api/v1/runs/{run_id}")
    assert detail.status_code == 200
    assert detail.json()["context_text"] == "Focus on API contracts"

    confirmed = test_client.post(f"/api/v1/runs/{run_id}/confirm")
    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "IN_PROGRESS"
    assert test_client.post(f"/api/v1/runs/{run_id}/confirm").status_code == 409
    assert test_client.patch(f"/api/v1/runs/{run_id}/plan", json=run["plan"]).status_code == 409


def test_runs_list_returns_total_and_items(test_client: TestClient) -> None:
    """The paginated run history uses the shared items/total response shape."""
    test_client.post(
        "/api/v1/runs",
        json={"workflow_id": str(WORKFLOW_ID), "task": "Review the latest changes"},
    )
    response = test_client.get("/api/v1/runs?limit=10&offset=0")
    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["workflow_title"] == "Repository review"


def test_run_creation_rejects_unknown_workflow(test_client: TestClient) -> None:
    """Unknown workflow IDs fail before a run is persisted."""
    response = test_client.post(
        "/api/v1/runs",
        json={"workflow_id": str(uuid4()), "task": "Review the latest changes"},
    )
    assert response.status_code == 404


def test_plan_rejects_duplicate_step_numbers(test_client: TestClient) -> None:
    created = test_client.post(
        "/api/v1/runs", json={"workflow_id": str(WORKFLOW_ID), "task": "Review"}
    ).json()
    created = test_client.get(f"/api/v1/runs/{created['id']}").json()
    step = created["plan"]["steps"][0]
    response = test_client.patch(f"/api/v1/runs/{created['id']}/plan", json={"steps": [step, step]})
    assert response.status_code == 422


def test_cancel_unconfirmed_run_is_idempotent(test_client: TestClient) -> None:
    created = test_client.post(
        "/api/v1/runs", json={"workflow_id": str(WORKFLOW_ID), "task": "Review"}
    ).json()
    path = f"/api/v1/runs/{created['id']}"
    cancelled = test_client.post(f"{path}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "CANCELLED"
    assert cancelled.json()["plan"]["steps"][0]["status"] == "CANCELLED"
    assert test_client.post(f"{path}/cancel").status_code == 200
    assert test_client.post(f"{path}/confirm").status_code == 409
    assert test_client.post(f"{path}/steps/1/retry").status_code == 409


async def test_retry_rejects_nonfailed_steps_and_terminal_cancel() -> None:
    repository = MemoryRunRepository()
    service = RunService(repository)
    created = await service.create(RunCreate(workflow_id=WORKFLOW_ID, task="Review"))
    run = repository.runs[created.id]
    run.status = "FAILED"
    with pytest.raises(RunError):
        await service.retry(run.id, 1)
    with pytest.raises(RunError) as missing:
        await service.retry(run.id, 2)
    assert missing.value.status_code == 404
    with pytest.raises(RunError):
        await service.cancel(run.id)


def test_sse_checks_run_and_validates_cursor_before_opening(test_client: TestClient) -> None:
    assert test_client.get(f"/api/v1/runs/{uuid4()}/events").status_code == 404
    for cursor in ("-1", "invalid", "9223372036854775808"):
        assert (
            test_client.get(
                f"/api/v1/runs/{uuid4()}/events",
                headers={"Last-Event-ID": cursor},
            ).status_code
            == 422
        )
        assert test_client.get(f"/api/v1/runs/{uuid4()}/events?after={cursor}").status_code == 422


def test_sse_query_replay_and_reconnect_header_priority(
    test_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    created = test_client.post(
        "/api/v1/runs",
        json={
            "workflow_id": str(WORKFLOW_ID),
            "task": "Replay QA",
        },
    ).json()
    cursors: list[int | None] = []

    async def fake_stream(
        sessions: object, run_id: UUID, after: int | None
    ) -> AsyncIterator[dict[str, str]]:
        cursors.append(after)
        yield {"event": "run:snapshot", "data": "{}"}

    monkeypatch.setattr("app.api.v1.events.stream_run", fake_stream)
    assert test_client.get(f"/api/v1/runs/{created['id']}/events?after=0").status_code == 200
    assert (
        test_client.get(
            f"/api/v1/runs/{created['id']}/events?after=0", headers={"Last-Event-ID": "12"}
        ).status_code
        == 200
    )
    assert cursors == [0, 12]


async def test_run_step_model_comes_from_execution_snapshot() -> None:
    repository = MemoryRunRepository()
    service = RunService(repository)
    created = await service.create(RunCreate(workflow_id=WORKFLOW_ID, task="Snapshot QA"))
    await PlannerExecutor(repository).execute(repository.runs[created.id])
    repository.agent.model = "claude-haiku"
    read = await service.read(repository.runs[created.id])
    assert read.plan and read.plan.steps[0].model == "claude-sonnet"
