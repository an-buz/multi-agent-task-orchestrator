"""Real PostgreSQL/Redis/ARQ integration with mock LLM calls only."""

import asyncio
import json
from collections.abc import Generator
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from app.core.config import Settings, get_settings
from app.db.run_repository import RunRepository
from app.db.session import get_session
from app.events.stream import stream_run
from app.llm.provider import LLMResponse
from app.llm.providers import MockLLMProvider
from app.main import app
from app.models.agent import Agent
from app.models.run import Run
from app.models.run_step import RunStep
from app.models.workflow import Workflow
from app.orchestrator.executor import build_input
from app.orchestrator.planner import LLMPlanner, PlannerExecutor
from app.workers.runner import OrchestratorWorker
from app.workers.tasks import execute_run, plan_run, recover_runs
from arq.connections import RedisSettings, create_pool
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
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


async def test_file_upload_run_snapshot_and_deletion(
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

    async def no_dispatch(run_id: UUID) -> None:
        pass

    app.dependency_overrides[get_session] = override_session
    monkeypatch.setattr("app.api.v1.runs.enqueue_plan", no_dispatch)
    try:
        await asyncio.to_thread(command.upgrade, Config("alembic.ini"), "head")
        async with sessions() as session:
            agent = Agent(
                id=uuid4(),
                name=f"File reviewer {uuid4()}",
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
                title="Files pipeline",
                execution_type="sequential",
                steps=[{"step_number": 1, "agent_id": str(agent.id), "depends_on": []}],
                graph_layout={},
            )
            session.add_all([agent, workflow])
            await session.commit()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            upload = await client.post(
                "/api/v1/files", files={"file": ("brief.md", b"# Facts\nA fact", "text/markdown")}
            )
            assert upload.status_code == 201
            file_id = upload.json()["id"]
            assert "content" not in upload.json()
            assert (await client.get(f"/api/v1/files/{file_id}")).json() == upload.json()
            download = await client.get(f"/api/v1/files/{file_id}/download")
            assert download.content == b"# Facts\nA fact"
            assert download.headers["x-content-type-options"] == "nosniff"
            payload = {
                "workflow_id": str(workflow.id),
                "task": "Analyze",
                "context_text": "User note",
                "file_ids": [file_id],
            }
            assert (
                await client.post("/api/v1/runs", json={**payload, "file_ids": [file_id, file_id]})
            ).status_code == 422
            assert (
                await client.post("/api/v1/runs", json={**payload, "file_ids": [str(uuid4())]})
            ).status_code == 404
            monkeypatch.setenv("RUN_CONTEXT_MAX_CHARS", "5")
            get_settings.cache_clear()
            assert (await client.post("/api/v1/runs", json=payload)).status_code == 413
            monkeypatch.delenv("RUN_CONTEXT_MAX_CHARS")
            get_settings.cache_clear()
            run = await client.post("/api/v1/runs", json=payload)
            assert run.status_code == 201
            body = run.json()
            assert (
                body["context_text"]
                == f"User note\n\nAttachment: brief.md (file_id: {file_id})\n# Facts\nA fact"
            )
            assert body["files"] == [upload.json()]
            run_id = body["id"]
            assert (await client.get(f"/api/v1/runs/{run_id}/files")).json() == [upload.json()]
            assert (await client.delete(f"/api/v1/files/{file_id}")).status_code == 409
            async with sessions() as session:
                repository = RunRepository(session)
                persisted = await repository.get(UUID(run_id))
                steps = await repository.steps(UUID(run_id))
                assert persisted is not None
                assert "# Facts" in build_input(persisted, steps[0], {})
                prompts: list[str] = []

                class CapturingMock(MockLLMProvider):
                    async def complete(self, system_prompt, user_prompt, model, **kwargs):
                        prompts.append(user_prompt)
                        return await super().complete(system_prompt, user_prompt, model, **kwargs)

                await PlannerExecutor(
                    repository, LLMPlanner(lambda model: CapturingMock())
                ).execute(persisted)
                assert json.loads(prompts[0])["context"] == body["context_text"]
                assert persisted.status == "AWAITING_CONFIRMATION"
            unused = await client.post(
                "/api/v1/files", files={"file": ("unused.txt", b"discard", "text/plain")}
            )
            unused_id = unused.json()["id"]
            assert (await client.delete(f"/api/v1/files/{unused_id}")).status_code == 204
            assert (await client.get(f"/api/v1/files/{unused_id}")).status_code == 404
            from app.db.file_repository import FileRepository
            from app.llm.provider import ToolCall
            from app.orchestrator.executor import DAGExecutor
            from app.services.runs import RunService

            from test_tools import pdf_bytes

            pdf = await client.post(
                "/api/v1/files", files={"file": ("brief.pdf", pdf_bytes(), "application/pdf")}
            )
            assert pdf.status_code == 201
            pdf_id = pdf.json()["id"]
            created = await client.post(
                "/api/v1/runs", json={**payload, "file_ids": [pdf_id], "token_budget": 10000}
            )
            assert created.status_code == 201
            pdf_run_id = UUID(created.json()["id"])
            assert created.json()["token_budget"] == 10000
            assert "Attachment fixture text" in created.json()["context_text"]
            async with sessions() as session:
                repository = RunRepository(session)
                persisted = await repository.get(pdf_run_id)
                assert persisted is not None
                await PlannerExecutor(repository).execute(persisted)
                await RunService(repository).confirm(pdf_run_id)
                steps = await repository.steps(pdf_run_id)
                steps[0].agent_config = {**steps[0].agent_config, "tools": ["file_reader"]}
                await repository.save()
                texts = await FileRepository(session).text_for_run(pdf_run_id)
                assert set(texts) == {pdf_id}

                class ReadingMock(MockLLMProvider):
                    calls = 0

                    async def complete_tools(self, system_prompt, messages, model, tools, **kwargs):
                        self.calls += 1
                        if self.calls == 1:
                            return LLMResponse(
                                content="",
                                usage={"input_tokens": 10, "output_tokens": 2},
                                tool_calls=[
                                    ToolCall(
                                        id="pdf", name="file_reader", arguments={"file_id": pdf_id}
                                    ),
                                    ToolCall(
                                        id="foreign",
                                        name="file_reader",
                                        arguments={"file_id": file_id},
                                    ),
                                ],
                                message={"role": "assistant", "blocks": []},
                            )
                        assert (
                            "Attachment fixture text" in json.loads(messages[-2]["content"])["text"]
                        )
                        assert "error" in json.loads(messages[-1]["content"])
                        return LLMResponse(
                            content="PDF reviewed", usage={"input_tokens": 20, "output_tokens": 4}
                        )

                await DAGExecutor(repository, lambda _: ReadingMock()).execute(persisted)
                assert persisted.status == "COMPLETED"
                assert steps[0].tokens_prompt == 30 and steps[0].tokens_completion == 6
                events = await repository.events(pdf_run_id, 0)
                tool_events = [event for event in events if event.event.startswith("agent:tool_")]
                assert [event.event for event in tool_events] == [
                    "agent:tool_call",
                    "agent:tool_result",
                    "agent:tool_call",
                    "agent:tool_result",
                ]
                assert tool_events[1].data["ok"] is True and tool_events[3].data["ok"] is False
                assert "Attachment fixture text" not in json.dumps(
                    [event.data for event in tool_events]
                )
            monkeypatch.setenv("CONTEXT_FILE_MAX_BYTES", "4")
            get_settings.cache_clear()
            oversized = await client.post(
                "/api/v1/files", files={"file": ("large.txt", b"12345", "text/plain")}
            )
            assert oversized.status_code == 413
    finally:
        app.dependency_overrides.clear()
        get_settings.cache_clear()
        await engine.dispose()


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
        functions=[plan_run, execute_run],
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
        monkeypatch.setattr("app.api.v1.runs.enqueue_plan", unavailable)
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
            assert created.json()["status"] == "PLANNING"
            assert created.json()["plan"] is None
            assert (await client.post(f"/api/v1/runs/{run_id}/confirm")).status_code == 409
            # Even an accidentally delivered job cannot execute before confirmation.
            await execute_run({}, run_id)
            if deferred_dispatch:
                await recover_runs({"redis": pool})
            await worker.async_run()
            before = (await client.get(f"/api/v1/runs/{run_id}")).json()
            assert before["status"] == "AWAITING_CONFIRMATION"
            assert before["planning_prompt_tokens"] > 0
            assert before["plan"]["steps"][0]["attempt"] == 0
            # Duplicate planning delivery cannot overwrite an approved draft or add usage.
            await asyncio.gather(plan_run({}, run_id), plan_run({}, run_id))
            assert (await client.get(f"/api/v1/runs/{run_id}")).json()["total_tokens"] == before[
                "total_tokens"
            ]
            plan = before["plan"]["steps"]
            plan[0]["subtask"] = "User edited task"
            assert (
                await client.patch(f"/api/v1/runs/{run_id}/plan", json={"steps": plan})
            ).status_code == 200
            confirms = await asyncio.gather(
                *[client.post(f"/api/v1/runs/{run_id}/confirm") for _ in range(2)]
            )
            assert sorted(response.status_code for response in confirms) == [200, 409]
            if deferred_dispatch:
                # Simulate persisted checkpoints left by a terminated worker.
                async with sessions() as session:
                    checkpoint = await RunRepository(session).steps(UUID(run_id))
                    checkpoint[0].status = "COMPLETED"
                    checkpoint[0].output = "Checkpoint: User edited task"
                    checkpoint[0].attempt = 1
                    checkpoint[0].tokens_prompt = 3
                    checkpoint[1].status = "IN_PROGRESS"
                    checkpoint[1].attempt = 1
                    await session.commit()
                await recover_runs({"redis": pool})
            await worker.async_run()
            detail = (await client.get(f"/api/v1/runs/{run_id}")).json()
            assert detail["status"] == "COMPLETED"
            assert all(step["status"] == "COMPLETED" for step in detail["plan"]["steps"])
            assert detail["total_tokens"] > 0
            assert "User edited task" in detail["final_report"]
            for format in ("json", "md", "pdf"):
                exported = await client.get(f"/api/v1/runs/{run_id}/export?format={format}")
                assert exported.status_code == 200
                assert exported.content
            defaults = {"default_model": "claude-haiku", "temperature": 0.4, "max_tokens": 2048}
            assert (await client.patch("/api/v1/settings/config", json=defaults)).status_code == 200
            # GET uses a new API session, proving defaults survive beyond the write request.
            config = (await client.get("/api/v1/settings/config")).json()
            assert all(config[key] == value for key, value in defaults.items())
            # PostgreSQL ownership protects concurrent delivery and completed steps are skipped.
            await asyncio.gather(execute_run({}, run_id), execute_run({}, run_id))
            async with sessions() as session:
                steps = list(
                    await session.scalars(select(RunStep).where(RunStep.run_id == UUID(run_id)))
                )
                steps.sort(key=lambda step: step.step_number)
                assert [step.attempt for step in steps] == [1, 2 if deferred_dispatch else 1]
                assert steps[0].output and steps[0].output in (steps[1].input or "")
                events = await RunRepository(session).events(UUID(run_id), 0)
                assert events[0].event == "plan:ready"
                assert events[-1].event == "task:finished"
                assert sum(event.event == "agent:completed" for event in events) == (
                    1 if deferred_dispatch else 2
                )
            stream = stream_run(sessions, UUID(run_id), events[0].id)
            try:
                snapshot = await anext(stream)
                assert snapshot["event"] == "run:snapshot"
                assert "id" not in snapshot  # Snapshot must not advance the replay cursor.
                assert json.loads(snapshot["data"])["data"]["run"]["status"] == "COMPLETED"
                replayed = [await anext(stream) for _ in events[1:]]
                assert [int(event["id"]) for event in replayed] == [e.id for e in events[1:]]
                assert all(json.loads(e["data"])["runId"] == run_id for e in replayed)
            finally:
                await stream.aclose()
            if not deferred_dispatch:
                await check_cancel_retry(client, sessions, workflow.id, monkeypatch)
                await check_planner_control(client, sessions, workflow.id, monkeypatch)
    finally:
        app.dependency_overrides.clear()
        await worker.close()
        await engine.dispose()


async def check_cancel_retry(
    client: AsyncClient,
    sessions: async_sessionmaker[AsyncSession],
    workflow_id: UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Separate API and worker sessions exercise stale status protection."""
    created = (
        await client.post(
            "/api/v1/runs",
            json={"workflow_id": str(workflow_id), "task": "Retry test"},
        )
    ).json()
    run_id = created["id"]
    await plan_run({}, run_id)
    await client.post(f"/api/v1/runs/{run_id}/confirm")
    provider = MockLLMProvider()
    original = provider.complete

    async def fail(*args: object, **kwargs: object) -> LLMResponse:
        raise ValueError("private error")

    monkeypatch.setattr(provider, "complete", fail)
    # Constructor defaults are bound at import time; patch its factory via the class.
    from app.orchestrator.executor import DAGExecutor

    class TestExecutor(DAGExecutor):
        def __init__(self, repository: RunRepository) -> None:
            super().__init__(repository, lambda _: provider)

    monkeypatch.setattr("app.workers.tasks.DAGExecutor", TestExecutor)
    await execute_run({}, run_id)
    assert (await client.get(f"/api/v1/runs/{run_id}")).json()["status"] == "FAILED"
    retried = await client.post(f"/api/v1/runs/{run_id}/steps/1/retry")
    assert retried.status_code == 200
    assert (await client.post(f"/api/v1/runs/{run_id}/steps/1/retry")).status_code == 409
    monkeypatch.setattr(provider, "complete", original)
    await execute_run({}, run_id)
    detail = (await client.get(f"/api/v1/runs/{run_id}")).json()
    assert detail["status"] == "COMPLETED"
    assert [step["attempt"] for step in detail["plan"]["steps"]] == [2, 1]

    created = (
        await client.post(
            "/api/v1/runs",
            json={"workflow_id": str(workflow_id), "task": "Cancel test"},
        )
    ).json()
    run_id = created["id"]
    await plan_run({}, run_id)
    await client.post(f"/api/v1/runs/{run_id}/confirm")
    entered = asyncio.Event()
    released = asyncio.Event()

    async def blocked(*args: object, **kwargs: object) -> LLMResponse:
        entered.set()
        await released.wait()
        return await original("System", "Cancelled result", "claude-sonnet")

    monkeypatch.setattr(provider, "complete", blocked)
    job = asyncio.create_task(execute_run({}, run_id))
    try:
        await asyncio.wait_for(entered.wait(), 5)
        cancelled = await client.post(f"/api/v1/runs/{run_id}/cancel")
        assert cancelled.status_code == 200
        released.set()  # Race the successful result with the committed cancellation.
        await asyncio.wait_for(job, 5)
        detail = (await client.get(f"/api/v1/runs/{run_id}")).json()
        assert detail["status"] == "CANCELLED"
        assert all(step["output"] is None for step in detail["plan"]["steps"])
        async with sessions() as session:
            persisted = await session.get(Run, UUID(run_id))
            assert persisted is not None
            assert persisted.status == "CANCELLED"
            events = await RunRepository(session).events(UUID(run_id), 0)
            assert events[-1].event == "task:cancelled"
        # Fresh subscriptions deliver a snapshot, then changes committed afterwards.
        stream = stream_run(sessions, UUID(run_id), None)
        try:
            snapshot = await anext(stream)
            cursor = int(snapshot["id"])
            async with sessions() as session:
                repository = RunRepository(session)
                await repository.get(UUID(run_id), lock=True)
                repository.emit(UUID(run_id), "task:cancelled", {"taskId": run_id})
                await repository.save()
            live = await asyncio.wait_for(anext(stream), 3)
            assert int(live["id"]) > cursor
            assert live["event"] == "task:cancelled"
        finally:
            await stream.aclose()
    finally:
        released.set()
        if not job.done():
            job.cancel()
        await asyncio.gather(job, return_exceptions=True)


async def check_planner_control(
    client: AsyncClient,
    sessions: async_sessionmaker[AsyncSession],
    workflow_id: UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.orchestrator.planner import LLMPlanner, PlannerExecutor

    provider = MockLLMProvider()
    entered, released = asyncio.Event(), asyncio.Event()

    class TestPlanner(PlannerExecutor):
        def __init__(self, repository: RunRepository) -> None:
            super().__init__(repository, LLMPlanner(lambda _: provider))

    monkeypatch.setattr("app.workers.tasks.PlannerExecutor", TestPlanner)

    async def blocked(*args: object, **kwargs: object) -> LLMResponse:
        entered.set()
        await released.wait()
        return LLMResponse(content="invalid", usage={"input_tokens": 10, "output_tokens": 2})

    monkeypatch.setattr(provider, "complete", blocked)
    created = (
        await client.post(
            "/api/v1/runs",
            json={
                "workflow_id": str(workflow_id),
                "task": "Cancel planning",
            },
        )
    ).json()
    run_id = created["id"]
    job = asyncio.create_task(plan_run({}, run_id))
    try:
        await asyncio.wait_for(entered.wait(), 3)
        assert (await client.post(f"/api/v1/runs/{run_id}/cancel")).status_code == 200
        released.set()
        await asyncio.wait_for(job, 3)
        detail = (await client.get(f"/api/v1/runs/{run_id}")).json()
        assert detail["status"] == "CANCELLED"
        async with sessions() as session:
            events = await RunRepository(session).events(UUID(run_id), 0)
            assert all(event.event != "plan:ready" for event in events)
    finally:
        released.set()
        if not job.done():
            job.cancel()
        await asyncio.gather(job, return_exceptions=True)

    async def invalid(*args: object, **kwargs: object) -> LLMResponse:
        return LLMResponse(content="invalid", usage={"input_tokens": 10, "output_tokens": 2})

    monkeypatch.setattr(provider, "complete", invalid)
    created = (
        await client.post(
            "/api/v1/runs",
            json={
                "workflow_id": str(workflow_id),
                "task": "Invalid plan",
            },
        )
    ).json()
    run_id = created["id"]
    await plan_run({}, run_id)
    detail = (await client.get(f"/api/v1/runs/{run_id}")).json()
    assert detail["status"] == "FAILED"
    assert detail["plan"] is None
    assert detail["planning_error"]["code"] == "invalid_plan"
    assert detail["total_tokens"] == 36
    assert (await client.post(f"/api/v1/runs/{run_id}/confirm")).status_code == 409
