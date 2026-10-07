"""Real PostgreSQL/Redis/ARQ integration with mock LLM calls only."""

import asyncio
from collections.abc import Generator
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from app.core.config import Settings, get_settings
from app.db.session import get_session
from app.main import app
from app.models.agent import Agent
from app.models.run_step import RunStep
from app.models.workflow import Workflow
from app.workers.runner import OrchestratorWorker
from app.workers.tasks import execute_run, recover_runs
from arq.connections import RedisSettings, create_pool
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from testcontainers.postgres import PostgresContainer
from testcontainers.redis import RedisContainer


@pytest.fixture(scope="module")
def infrastructure() -> Generator[tuple[str, str]]:
    with (
        PostgresContainer("postgres:16-alpine") as postgres,
        RedisContainer("redis:7-alpine") as redis,
    ):
        database_url = postgres.get_connection_url().replace(
            "postgresql+psycopg2", "postgresql+asyncpg"
        )
        redis_url = f"redis://{redis.get_container_host_ip()}:{redis.get_exposed_port(6379)}/0"
        yield database_url, redis_url


@pytest.mark.parametrize("deferred_dispatch", [False, True])
async def test_confirm_queue_execution_and_redelivery(
    infrastructure: tuple[str, str],
    monkeypatch: pytest.MonkeyPatch,
    deferred_dispatch: bool,
) -> None:
    database_url, redis_url = infrastructure
    monkeypatch.setenv("DATABASE_URL", database_url)
    get_settings.cache_clear()
    settings = Settings(
        _env_file=None, database_url=database_url, redis_url=redis_url, llm_provider_mode="mock"
    )
    engine = create_async_engine(database_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    pool = await create_pool(RedisSettings.from_dsn(redis_url))
    worker = OrchestratorWorker(
        functions=[execute_run],
        redis_pool=pool,
        burst=True,
        keep_result=0,
        handle_signals=False,
        poll_delay=0.01,
    )

    async def override_session():
        async with sessions() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    monkeypatch.setattr("app.workers.tasks.engine", engine)
    monkeypatch.setattr("app.workers.tasks.async_session_factory", sessions)
    monkeypatch.setattr("app.workers.queue.get_settings", lambda: settings)
    if deferred_dispatch:

        async def unavailable(run_id: UUID) -> None:
            pass

        monkeypatch.setattr("app.api.v1.runs.enqueue_run", unavailable)
    try:
        await asyncio.to_thread(command.upgrade, Config("alembic.ini"), "head")
        async with sessions() as session:
            agent = Agent(
                id=uuid4(),
                name=f"Mock reviewer {uuid4()}",
                role="Review",
                system_prompt="Be precise",
                model="claude-sonnet",
                temperature=0.2,
                max_tokens=1024,
                context_window=128000,
                tools=[],
            )
            workflow = Workflow(
                id=uuid4(),
                title="Mock pipeline",
                execution_type="sequential",
                steps=[
                    {"step_number": 1, "agent_id": str(agent.id), "depends_on": []},
                    {"step_number": 2, "agent_id": str(agent.id), "depends_on": [1]},
                ],
                graph_layout={},
            )
            session.add_all([agent, workflow])
            await session.commit()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            created = await client.post(
                "/api/v1/runs", json={"workflow_id": str(workflow.id), "task": "Analyze"}
            )
            assert created.status_code == 201
            run_id = created.json()["id"]
            # Even an accidentally delivered job cannot execute before confirmation.
            await execute_run({}, run_id)
            before = (await client.get(f"/api/v1/runs/{run_id}")).json()
            assert before["plan"]["steps"][0]["attempt"] == 0
            plan = created.json()["plan"]["steps"]
            plan[0]["subtask"] = "User edited task"
            assert (
                await client.patch(f"/api/v1/runs/{run_id}/plan", json={"steps": plan})
            ).status_code == 200
            confirms = await asyncio.gather(
                *[client.post(f"/api/v1/runs/{run_id}/confirm") for _ in range(2)]
            )
            assert sorted(response.status_code for response in confirms) == [200, 409]
            if deferred_dispatch:
                await recover_runs({"redis": pool})
            await worker.async_run()
            detail = (await client.get(f"/api/v1/runs/{run_id}")).json()
            assert detail["status"] == "COMPLETED"
            assert all(step["status"] == "COMPLETED" for step in detail["plan"]["steps"])
            assert detail["total_tokens"] > 0
            assert "User edited task" in detail["final_report"]
            # PostgreSQL ownership protects concurrent delivery and completed steps are skipped.
            await asyncio.gather(execute_run({}, run_id), execute_run({}, run_id))
            async with sessions() as session:
                steps = list(
                    await session.scalars(select(RunStep).where(RunStep.run_id == UUID(run_id)))
                )
                assert [step.attempt for step in steps] == [1, 1]
                assert steps[0].output and steps[0].output in (steps[1].input or "")
    finally:
        app.dependency_overrides.clear()
        await worker.close()
        await engine.dispose()
