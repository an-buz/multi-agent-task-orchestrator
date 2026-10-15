"""Model switches and safe pause/resume integration; all LLM calls are mocks."""

import asyncio
from collections.abc import AsyncIterator
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from app.core.config import Settings
from app.db.model_repository import ModelRepository
from app.db.run_repository import RunRepository
from app.db.session import get_session
from app.llm.provider import LLMResponse
from app.llm.providers import MockLLMProvider
from app.main import app
from app.models.run_step import RunStep
from app.orchestrator.executor import DAGExecutor
from app.orchestrator.planner import PlannerExecutor
from app.schemas.run import RunCreate
from app.services.models import ModelService
from app.services.runs import RunService
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from test_run_integration import infrastructure as _infrastructure

infrastructure = _infrastructure


@pytest.mark.parametrize("provider", ["anthropic", "openai", "none", "mock"])
async def test_only_connected_provider_models_are_exposed(provider: str) -> None:
    repository = AsyncMock(spec=ModelRepository)
    repository.disabled.return_value = {"claude-opus"}
    settings = Settings(
        _env_file=None,
        llm_provider_mode="mock" if provider == "mock" else "real",
        anthropic_api_key="secret" if provider == "anthropic" else "",
        openai_api_key="secret" if provider == "openai" else "",
    )
    service = ModelService(repository, settings)
    catalogue = await service.catalogue()
    expected = (
        {"anthropic", "openai"}
        if provider == "mock"
        else set()
        if provider == "none"
        else {provider}
    )
    assert {model.provider for model in catalogue.items} == expected
    assert "claude-opus" not in await service.available()
    assert "secret" not in catalogue.model_dump_json()


@pytest.fixture
async def model_client(
    infrastructure: tuple[str, str],
) -> AsyncIterator[tuple[AsyncClient, async_sessionmaker[AsyncSession]]]:
    database_url, _ = infrastructure
    from app.core.config import get_settings

    engine = create_async_engine(database_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    # Alembic reads its URL from cached environment settings.
    import os

    old_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = database_url
    get_settings.cache_clear()
    await asyncio.to_thread(command.upgrade, Config("alembic.ini"), "head")

    async def override_session() -> AsyncIterator[AsyncSession]:
        async with sessions() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test/api/v1"
        ) as client:
            # Restore switches between tests sharing this temporary database.
            for key in ("claude-sonnet", "claude-haiku", "claude-opus", "gpt-4o"):
                assert (
                    await client.patch(f"/settings/models/{key}", json={"enabled": True})
                ).status_code == 200
            yield client, sessions
    finally:
        app.dependency_overrides.clear()
        if old_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = old_url
        get_settings.cache_clear()
        await engine.dispose()


async def create_confirmed(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> tuple[UUID, dict[str, object]]:
    payload: dict[str, object] = {
        "name": f"Model test {uuid4()}",
        "role": "Review",
        "system_prompt": "Be precise",
        "model": "claude-sonnet",
        "max_tokens": 1024,
        "temperature": 0.2,
    }
    response = await client.post("/agents", json=payload)
    assert response.status_code == 201, response.text
    agent_id = response.json()["id"]
    workflow = await client.post(
        "/workflows",
        json={
            "title": "Model policy",
            "execution_type": "sequential",
            "steps": [
                {"step_number": 1, "agent_id": agent_id},
                {"step_number": 2, "agent_id": agent_id, "depends_on": [1]},
            ],
        },
    )
    assert workflow.status_code == 201, workflow.text
    async with sessions() as session:
        repository = RunRepository(session)
        service = RunService(repository)
        created = await service.create(RunCreate(workflow_id=workflow.json()["id"], task="Review"))
        run = await repository.get(created.id)
        assert run is not None
        await PlannerExecutor(repository).execute(run)
        await service.confirm(run.id)
    return created.id, {**payload, "id": agent_id}


async def test_disable_pause_reconfigure_resume_and_preserve_completed(
    model_client: tuple[AsyncClient, async_sessionmaker[AsyncSession]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, sessions = model_client
    run_id, agent = await create_confirmed(client, sessions)
    started, release = asyncio.Event(), asyncio.Event()
    calls: list[str] = []

    class GatedMock(MockLLMProvider):
        async def complete(
            self,
            system_prompt: str,
            user_prompt: str,
            model: str,
            *,
            temperature: float = 0.7,
            max_tokens: int = 4096,
        ) -> LLMResponse:
            calls.append(model)
            started.set()
            await release.wait()
            return await super().complete(
                system_prompt, user_prompt, model, temperature=temperature, max_tokens=max_tokens
            )

    async def execute() -> None:
        async with sessions() as session:
            repository = RunRepository(session)
            run = await repository.get(run_id)
            assert run is not None
            await DAGExecutor(repository, lambda _: GatedMock()).execute(run)

    pending = asyncio.create_task(execute())
    try:
        await asyncio.wait_for(started.wait(), 5)
        disabled = await asyncio.wait_for(
            client.patch("/settings/models/claude-sonnet", json={"enabled": False}), 5
        )
        assert disabled.status_code == 200
        assert "claude-sonnet" not in {
            item["key"] for item in (await client.get("/agents/models")).json()["items"]
        }
        detail = (await client.get(f"/agents/{agent['id']}")).json()
        assert detail["available"] is False and detail["requires_reconfiguration"] is True
        blocked = await client.post(
            "/agents",
            json={
                **{key: value for key, value in agent.items() if key != "id"},
                "name": str(uuid4()),
            },
        )
        assert blocked.status_code == 422
        release.set()
        await asyncio.wait_for(pending, 5)
        paused = (await client.get(f"/runs/{run_id}")).json()
        assert paused["status"] == "PAUSED"
        assert [step["status"] for step in paused["plan"]["steps"]] == ["COMPLETED", "PENDING"]
        output, usage = paused["plan"]["steps"][0]["output"], paused["total_tokens"]
        # Re-enabling alone must not silently clear the durable repair requirement.
        await client.patch("/settings/models/claude-sonnet", json={"enabled": True})
        await execute()
        assert (await client.get(f"/runs/{run_id}")).json()["status"] == "PAUSED"
        assert len(calls) == 1
        values = {key: value for key, value in agent.items() if key != "id"}
        values["model"] = "claude-haiku"
        updated = await client.put(f"/agents/{agent['id']}", json=values)
        assert updated.status_code == 200 and updated.json()["available"] is True
        # The real recovery sweep must deliver PAUSED runs, not only active runs.
        from app.workers import tasks

        async with sessions() as session:
            monkeypatch.setattr(tasks, "engine", session.bind)
        monkeypatch.setattr(tasks, "async_session_factory", sessions)
        redis = AsyncMock()
        await tasks.recover_runs({"redis": redis})
        assert any(
            call.args[:2] == ("execute_run", str(run_id))
            for call in redis.enqueue_job.call_args_list
        )
        # Simulate a fresh recovery delivery after reconfiguration.
        await execute()
        completed = (await client.get(f"/runs/{run_id}")).json()
        assert completed["status"] == "COMPLETED"
        assert completed["plan"]["steps"][0]["output"] == output
        assert completed["plan"]["steps"][0]["attempt"] == 1
        assert completed["plan"]["steps"][0]["model"] == "claude-sonnet"
        assert completed["plan"]["steps"][1]["model"] == "claude-haiku"
        assert completed["total_tokens"] > usage
        assert len(calls) == 2
        async with sessions() as session:
            repaired = await session.scalar(
                select(RunStep).where(RunStep.run_id == run_id, RunStep.step_number == 2)
            )
            assert repaired and repaired.requires_reconfiguration is False
            events = await RunRepository(session).events(run_id, 0)
            assert {"task:paused", "task:resumed"} <= {event.event for event in events}
    finally:
        release.set()
        await asyncio.gather(pending, return_exceptions=True)


async def test_all_disabled_validation_and_paused_cancellation(
    model_client: tuple[AsyncClient, async_sessionmaker[AsyncSession]],
) -> None:
    client, sessions = model_client
    run_id, agent = await create_confirmed(client, sessions)
    for item in (await client.get("/settings/models")).json()["items"]:
        assert (
            await client.patch(f"/settings/models/{item['key']}", json={"enabled": False})
        ).status_code == 200
    assert (await client.get("/agents/models")).json()["items"] == []
    assert (
        await client.patch(
            "/settings/config",
            json={
                "default_model": "claude-sonnet",
                "temperature": 0.2,
                "max_tokens": 1024,
            },
        )
    ).status_code == 422
    assert (
        await client.patch("/settings/models/unknown", json={"enabled": True})
    ).status_code == 422
    assert (
        await client.patch("/settings/models/claude-sonnet", json={"enabled": "false"})
    ).status_code == 422
    async with sessions() as session:
        repository = RunRepository(session)
        run = await repository.get(run_id)
        assert run is not None
        await DAGExecutor(repository).execute(run)
    assert (await client.get(f"/runs/{run_id}")).json()["status"] == "PAUSED"
    run = (await client.get(f"/runs/{run_id}")).json()
    assert (
        await client.post("/runs", json={"workflow_id": run["workflow_id"], "task": "Blocked"})
    ).status_code == 422
    assert (
        await client.put(
            f"/agents/{agent['id']}",
            json={key: value for key, value in agent.items() if key != "id"},
        )
    ).status_code == 422
    assert (await client.post(f"/runs/{run_id}/cancel")).json()["status"] == "CANCELLED"
