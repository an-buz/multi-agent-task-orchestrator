"""Tests for the run plan review API."""

from collections.abc import Generator
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
from app.services.runs import RunService
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


@pytest.fixture
def test_client(monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient, Any]:
    repository = MemoryRunRepository()
    app.dependency_overrides[get_run_service] = lambda: RunService(repository)
    monkeypatch.setattr("app.api.v1.runs.enqueue_run", AsyncMock())
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
    step = created["plan"]["steps"][0]
    response = test_client.patch(f"/api/v1/runs/{created['id']}/plan", json={"steps": [step, step]})
    assert response.status_code == 422
