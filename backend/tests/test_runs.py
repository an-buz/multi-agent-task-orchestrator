"""Tests for the run plan review API."""

from collections.abc import AsyncGenerator, Generator, Iterable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from app.db.session import get_session
from app.main import app
from app.models.agent import Agent
from app.models.run import Run
from app.models.workflow import Workflow
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

WORKFLOW_ID = UUID("4ac67d20-05d0-4246-a33b-51b88a17f51f")
AGENT_ID = UUID("025010d8-e77f-494b-bb42-e107c903970d")


class ResultList:
    """Iterable wrapper matching the subset of SQLAlchemy's result API used by routes."""

    def __init__(self, values: Iterable[Agent]) -> None:
        self.values = list(values)

    def __iter__(self) -> Iterable[Agent]:
        return iter(self.values)


class QueryResult:
    """Small async execute result for run list and detail queries."""

    def __init__(self, rows: list[tuple[Run, str]]) -> None:
        self.rows = rows

    def one_or_none(self) -> tuple[Run, str] | None:
        return self.rows[0] if self.rows else None

    def __iter__(self) -> Iterable[tuple[Run, str]]:
        return iter(self.rows)


class MemoryRunSession:
    """Store a single run in memory so API tests do not require PostgreSQL."""

    def __init__(self) -> None:
        now = datetime.now(UTC)
        self.workflow = Workflow(
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
        self.pending: Run | None = None

    def add(self, run: Run) -> None:
        run.id = uuid4()
        run.created_at = datetime.now(UTC)
        self.pending = run

    async def get(self, model: type[Any], item_id: UUID) -> Any:
        if model is Workflow and item_id == self.workflow.id:
            return self.workflow
        if model is Agent and item_id == self.agent.id:
            return self.agent
        if model is Run:
            return self.runs.get(item_id)
        return None

    async def scalars(self, _statement: object) -> ResultList:
        return ResultList([self.agent])

    async def scalar(self, _statement: object) -> int:
        return len(self.runs)

    async def execute(self, _statement: object) -> QueryResult:
        return QueryResult([(run, self.workflow.title) for run in self.runs.values()])

    async def commit(self) -> None:
        if self.pending is not None:
            self.runs[self.pending.id] = self.pending
            self.pending = None

    async def refresh(self, _instance: object) -> None:
        return None


@pytest.fixture
def test_client() -> Generator[TestClient, Any]:
    session = MemoryRunSession()

    async def override_session() -> AsyncGenerator[AsyncSession, Any]:
        yield session  # type: ignore[misc]

    app.dependency_overrides[get_session] = override_session
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
