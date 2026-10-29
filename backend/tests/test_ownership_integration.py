"""Ownership loss cancels work and fences persistence against real PostgreSQL."""

import asyncio
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from app.core.config import get_settings
from app.db.run_repository import RunRepository
from app.db.session import get_session
from app.llm.provider import LLMResponse, ToolCall
from app.main import app
from app.models.agent import Agent
from app.models.workflow import Workflow
from app.orchestrator.executor import DAGExecutor
from app.orchestrator.planner import LLMPlanner, PlannerExecutor
from app.schemas.run import RunCreate
from app.services.runs import RunService
from app.workers import tasks
from app.workers.ownership import run_lock_key
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from test_run_integration import infrastructure as infrastructure


@pytest.mark.parametrize("phase", ["planning", "completion", "tool", "late_completion"])
async def test_ownership_connection_loss_stops_work_and_prevents_duplicate_dispatch(
    infrastructure: tuple[str, str], monkeypatch: pytest.MonkeyPatch, phase: str
) -> None:
    database_url, _ = infrastructure

    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("RUN_POLL_INTERVAL", "10" if phase == "late_completion" else "0.01")
    get_settings.cache_clear()

    engine = create_async_engine(database_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    monkeypatch.setattr(tasks, "engine", engine)

    entered, cancelled = asyncio.Event(), asyncio.Event()
    finish = asyncio.Event()
    calls = 0
    closed = AsyncMock()

    async def pause():
        entered.set()

        try:
            await finish.wait()
        finally:
            cancelled.set()

    class PausedProvider:
        async def complete(self, *args, **kwargs):
            nonlocal calls

            calls += 1

            await pause()

            return LLMResponse(
                content="Stale response", usage={"input_tokens": 13, "output_tokens": 5}
            )

        async def complete_tools(self, *args, **kwargs):
            nonlocal calls

            if phase != "tool":
                return await self.complete(*args, **kwargs)

            calls += 1

            return LLMResponse(
                content="",
                usage={"input_tokens": 7, "output_tokens": 3},
                tool_calls=[
                    ToolCall(id="call", name="calculator", arguments={"expression": "1+1"})
                ],
                message={"role": "assistant", "content": ""},
            )

        async def aclose(self):
            await closed()

    class Execution(DAGExecutor):
        def __init__(self, repository):
            super().__init__(repository, lambda _: PausedProvider())

    class Planning(PlannerExecutor):
        def __init__(self, repository):
            super().__init__(repository, LLMPlanner(lambda _: PausedProvider()))

    monkeypatch.setattr(tasks, "DAGExecutor", Execution)
    monkeypatch.setattr(tasks, "PlannerExecutor", Planning)

    if phase == "tool":

        async def paused_tool(self, call):
            return await pause()

        monkeypatch.setattr("app.orchestrator.executor.ToolRuntime.execute", paused_tool)

    first = None

    try:
        await asyncio.to_thread(command.upgrade, Config("alembic.ini"), "head")

        async with sessions() as session:
            agent = Agent(
                id=uuid4(),
                name=f"Ownership {uuid4()}",
                role="Review",
                system_prompt="Be precise",
                model="claude-sonnet",
                temperature=0.2,
                max_tokens=1024,
                context_window=128000,
                tools=["calculator"] if phase == "tool" else [],
            )
            workflow = Workflow(
                id=uuid4(),
                title="Ownership",
                execution_type="sequential",
                steps=[{"step_number": 1, "agent_id": str(agent.id), "depends_on": []}],
                graph_layout={},
            )

            session.add_all([agent, workflow])

            await session.commit()

            service = RunService(RunRepository(session))

            created = await service.create(
                RunCreate(workflow_id=workflow.id, task="Check ownership")
            )
            run = await service.require(created.id)

            if phase != "planning":
                await PlannerExecutor(service.repository).execute(run)

                await service.confirm(run.id)

            run_id = run.id

        first = asyncio.create_task(tasks.run_job(str(run_id), planning=phase == "planning"))

        await asyncio.wait_for(entered.wait(), 5)

        async with engine.connect() as connection:
            key = run_lock_key(run_id)

            pid = await connection.scalar(
                text(
                    "SELECT pid FROM pg_locks WHERE locktype='advisory' AND granted "
                    "AND classid = :high AND objid = :low AND objsubid = 1"
                ),
                {"high": (key >> 32) & 0xFFFFFFFF, "low": key & 0xFFFFFFFF},
            )

            assert pid is not None
            # A positive timeout waits for termination, rather than only signalling
            # it. Verify release before requiring the next delivery to execute.
            assert await connection.scalar(
                text("SELECT pg_terminate_backend(:pid, 5000)"), {"pid": pid}
            )
            assert not await connection.scalar(
                text(
                    "SELECT EXISTS (SELECT 1 FROM pg_locks "
                    "WHERE pid = :pid AND locktype = 'advisory' AND granted)"
                ),
                {"pid": pid},
            )

        # Dispatch after lock release: pending receipts prohibit reissuing work,
        # even before the old worker's watchdog processes the disconnect.
        await asyncio.wait_for(tasks.run_job(str(run_id), planning=phase == "planning"), 5)

        # A late response must not write through a fresh connection even when the
        # watchdog is deliberately slow and recovery has already failed the run.
        if phase == "late_completion":
            finish.set()

        outcome = (await asyncio.wait_for(asyncio.gather(first, return_exceptions=True), 5))[0]

        assert isinstance(outcome, Exception)
        assert cancelled.is_set()
        assert calls == 1

        closed.assert_awaited_once()

        async with sessions() as session:
            repository = RunRepository(session)

            run = await repository.get(run_id)

            assert run.status == "FAILED"

            if phase == "planning":
                assert run.planning_error["code"] == "llm_execution_interrupted"
            else:
                step = (await repository.steps(run_id))[0]

                assert step.status == "FAILED"
                assert step.output is None
                assert step.error["code"] == (
                    "tool_execution_interrupted" if phase == "tool" else "llm_execution_interrupted"
                )
                assert step.tokens_prompt == (7 if phase == "tool" else 0)
                assert step.tokens_completion == (3 if phase == "tool" else 0)

        if phase in {"completion", "late_completion"}:
            async with sessions() as session:
                await RunService(RunRepository(session)).retry(run_id, 1)

            monkeypatch.setattr(tasks, "DAGExecutor", DAGExecutor)

            await asyncio.wait_for(tasks.run_job(str(run_id), planning=False), 5)

            async with sessions() as session:
                repository = RunRepository(session)

                assert (await repository.get(run_id)).status == "COMPLETED"
                assert (await repository.steps(run_id))[0].output != "Stale response"

            assert calls == 1
    finally:
        if first is not None:
            first.cancel()

            await asyncio.gather(first, return_exceptions=True)

        await engine.dispose()

        get_settings.cache_clear()


async def test_step_number_boundaries_and_legacy_workflows_return_validation_errors(
    infrastructure: tuple[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    database_url, _ = infrastructure

    monkeypatch.setenv("DATABASE_URL", database_url)
    get_settings.cache_clear()

    engine = create_async_engine(database_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    async def override_session():
        async with sessions() as session:
            yield session

    app.dependency_overrides[get_session] = override_session

    monkeypatch.setattr("app.api.v1.runs.enqueue_plan", AsyncMock())

    try:
        await asyncio.to_thread(command.upgrade, Config("alembic.ini"), "head")

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            agent = await client.post(
                "/api/v1/agents",
                json={
                    "name": f"Bounds {uuid4()}",
                    "role": "Review",
                    "system_prompt": "Be precise",
                    "model": "claude-sonnet",
                    "temperature": 0.2,
                    "max_tokens": 1024,
                    "context_window": 128000,
                    "tools": [],
                },
            )

            assert agent.status_code == 201

            payload = {
                "title": "Bounds",
                "execution_type": "sequential",
                "steps": [
                    {"step_number": 2147483647, "agent_id": agent.json()["id"], "depends_on": []}
                ],
                "graph_layout": {},
            }

            workflow = await client.post("/api/v1/workflows", json=payload)

            assert workflow.status_code == 201

            run = await client.post(
                "/api/v1/runs", json={"workflow_id": workflow.json()["id"], "task": "Maximum step"}
            )

            assert run.status_code == 201

            await client.post(f"/api/v1/runs/{run.json()['id']}/cancel")

            payload["steps"][0]["step_number"] = 2147483648

            assert (await client.post("/api/v1/workflows", json=payload)).status_code == 422
            assert (
                await client.put(f"/api/v1/workflows/{workflow.json()['id']}", json=payload)
            ).status_code == 422
            assert (
                await client.post("/api/v1/workflows/validate", json=payload)
            ).status_code == 422

            async with sessions() as session:
                legacy_payload = {
                    **payload,
                    "steps": [
                        {
                            "step_number": 2147483648,
                            "agent_id": agent.json()["id"],
                            "depends_on": [],
                        },
                        {
                            "step_number": 2147483649,
                            "agent_id": agent.json()["id"],
                            "depends_on": [2147483648],
                        },
                    ],
                }

                legacy = Workflow(id=uuid4(), **legacy_payload)

                session.add(legacy)

                await session.commit()

            response = await client.post(
                "/api/v1/runs", json={"workflow_id": str(legacy.id), "task": "Legacy step"}
            )

            assert response.status_code == 422
            assert "edit the workflow" in response.json()["error"]["message"]

            detail = await client.get(f"/api/v1/workflows/{legacy.id}")

            assert detail.status_code == 200
            assert detail.json()["steps"][0]["step_number"] == 2147483648
            assert detail.json()["steps"][1]["depends_on"] == [2147483648]

            listing = await client.get("/api/v1/workflows")

            assert listing.status_code == 200

            items = {item["id"]: item for item in listing.json()["items"]}

            assert items[str(legacy.id)]["steps"] == detail.json()["steps"]
            assert items[workflow.json()["id"]]["steps"][0]["step_number"] == 2147483647
            # Compatibility reads must not allow invalid identifiers back into writes.
            assert (
                await client.put(f"/api/v1/workflows/{legacy.id}", json=legacy_payload)
            ).status_code == 422

            repaired = {
                **legacy_payload,
                "steps": [
                    {"step_number": 1, "agent_id": agent.json()["id"], "depends_on": []},
                    {"step_number": 2, "agent_id": agent.json()["id"], "depends_on": [1]},
                ],
            }

            updated = await client.put(f"/api/v1/workflows/{legacy.id}", json=repaired)

            assert updated.status_code == 200
            assert updated.json()["steps"][1]["depends_on"] == [1]

            runnable = await client.post(
                "/api/v1/runs", json={"workflow_id": str(legacy.id), "task": "Repaired step"}
            )

            assert runnable.status_code == 201
    finally:
        app.dependency_overrides.clear()

        await engine.dispose()

        get_settings.cache_clear()
