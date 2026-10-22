"""Demo catalogue, canned streaming, and real PostgreSQL workflow lifecycle checks."""

import asyncio
from unittest.mock import AsyncMock

import pytest
from alembic import command
from alembic.config import Config
from app.core.config import Settings, get_settings
from app.db.run_repository import RunRepository
from app.demo.catalogue import (
    DEMO_TASK,
    ROLES,
    agent_payloads,
    demo_id,
    seed_demo,
    workflow_payloads,
)
from app.demo.launcher import DemoPorts, demo_environment
from app.demo.responses import load_scenarios
from app.llm.providers import MockLLMProvider, create_provider
from app.models.agent import Agent
from app.models.run_event import RunEvent
from app.models.workflow import Workflow
from app.orchestrator.executor import DAGExecutor
from app.orchestrator.planner import PlannerExecutor
from app.schemas.decision import DecisionResolution
from app.schemas.run import RunCreate
from app.schemas.workflow import validate_workflow_graph
from app.services.runs import RunService
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from test_run_integration import infrastructure as _infrastructure

infrastructure = _infrastructure


def test_demo_forces_mock_even_with_real_provider_settings() -> None:
    settings = Settings(
        _env_file=None,
        demo_mode=True,
        llm_provider_mode="real",
        code_executor_backend="docker",
        run_token_budget=100,
    )
    assert settings.llm_provider_mode == "mock"
    assert settings.code_executor_backend == "disabled"
    assert settings.run_token_budget is None
    for model in ("claude-sonnet", "gpt-4o"):
        assert isinstance(create_provider(model, settings), MockLLMProvider)


def test_demo_environment_isolates_storage_and_matches_frontend_api() -> None:
    env = demo_environment(DemoPorts(backend_port=18001, frontend_port=3001))
    assert env["DEMO_MODE"] == "true"
    assert env["DATABASE_URL"].endswith(":15432/orchestrator_demo")
    assert env["REDIS_URL"] == "redis://127.0.0.1:17379/0"
    assert env["NEXT_PUBLIC_API_URL"] == "http://localhost:18001/api/v1"
    assert env["CORS_ORIGINS"] == '["http://localhost:3001"]'


async def test_seed_rejects_regular_mode_before_touching_database() -> None:
    session = AsyncMock()
    with pytest.raises(ValueError, match="DEMO_MODE"):
        await seed_demo(session, Settings(_env_file=None, demo_mode=False))
    session.execute.assert_not_called()


async def test_all_fifteen_responses_stream_and_regular_mock_stays_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEMO_MODE", "true")
    get_settings.cache_clear()
    settings = get_settings()
    agents = agent_payloads(settings)
    assert len(agents) == 5
    assert {agent.role for agent in agents} >= {"developer", "qa", "reviewer"}
    outputs: set[str] = set()
    for workflow in workflow_payloads():
        assert validate_workflow_graph(workflow) == []
        assert len(workflow.steps) == 5
        for role, agent in zip(ROLES, agents, strict=True):
            provider = MockLLMProvider()
            chunks = [
                chunk
                async for chunk in provider.stream(
                    agent.system_prompt,
                    [{"role": "user", "content": f"[demo:{workflow.execution_type}]\nTask"}],
                    agent.model,
                    [],
                    temperature=agent.temperature,
                    max_tokens=agent.max_tokens,
                )
            ]
            response = chunks[-1].response
            assert response is not None
            assert response.model_dump() == {
                **load_scenarios()[workflow.execution_type]["results"][role],
                "tool_calls": [],
                "message": {},
                "stop_reason": "stop",
                "refused": False,
            }
            assert "".join(chunk.text_delta for chunk in chunks) == response.content
            assert len(chunks) > 2
            outputs.add(response.content)
    assert len(outputs) == 15
    monkeypatch.setenv("DEMO_MODE", "false")
    get_settings.cache_clear()
    response = await MockLLMProvider().complete("[demo:developer]", "[demo:sequential]", "gpt-4o")
    assert response.content.startswith("Mock response:")


async def test_seed_and_all_three_demo_workflows_complete_after_confirmation(
    infrastructure: tuple[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    database_url, redis_url = infrastructure
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("REDIS_URL", redis_url)
    get_settings.cache_clear()
    settings = get_settings()
    engine = create_async_engine(database_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        await asyncio.to_thread(command.upgrade, Config("alembic.ini"), "head")
        async with sessions() as session:
            await seed_demo(session, settings)
            await seed_demo(session, settings)
            assert await session.scalar(select(func.count()).select_from(Agent)) == 5
            assert await session.scalar(select(func.count()).select_from(Workflow)) == 6
            for workflow in workflow_payloads():
                stored = await session.get(Workflow, demo_id("workflow", workflow.execution_type))
                assert stored is not None
                repository = RunRepository(session)
                service = RunService(repository)
                created = await service.create(
                    RunCreate(workflow_id=stored.id, task=DEMO_TASK, context_text="Demo context")
                )
                run = await repository.get(created.id)
                assert run is not None
                await PlannerExecutor(repository).execute(run)
                assert run.status == "AWAITING_CONFIRMATION"
                steps = await repository.steps(run.id)
                assert all(step.status == "PENDING" and step.output is None for step in steps)
                await DAGExecutor(repository).execute(run)
                assert all(step.output is None for step in steps)
                await service.confirm(run.id)
                await DAGExecutor(repository).execute(run)
                assert run.status == "COMPLETED"
                fixture = load_scenarios()[workflow.execution_type]
                steps = await repository.steps(run.id)
                assert len(steps) == 5
                for role, step in zip(ROLES, steps, strict=True):
                    assert step.status == "COMPLETED"
                    assert step.output == fixture["results"][role]["content"]
                    assert "Demo context" in step.input
                    assert DEMO_TASK in step.input
                    for parent in step.depends_on:
                        assert steps[parent - 1].output in step.input
                assert run.total_tokens == 680 + sum(
                    sum(value["usage"].values()) for value in fixture["results"].values()
                )
                assert fixture["results"]["writer"]["content"] in run.final_report
                events = list(
                    await session.scalars(
                        select(RunEvent).where(RunEvent.run_id == run.id).order_by(RunEvent.id)
                    )
                )
                assert any(event.event == "agent:stream_chunk" for event in events)
                active: set[int] = set()
                completed: set[int] = set()
                peak = 0
                for event in events:
                    if event.event != "agent:status_change":
                        continue
                    number = event.data["stepNumber"]
                    if event.data["status"] == "IN_PROGRESS":
                        assert set(steps[number - 1].depends_on) <= completed
                        active.add(number)
                        peak = max(peak, len(active))
                    elif event.data["status"] == "COMPLETED":
                        active.discard(number)
                        completed.add(number)
                assert (
                    peak == {"sequential": 1, "parallel": 4, "hybrid": 2}[workflow.execution_type]
                )
                # Re-seeding must preserve previous runs and edited catalogue records.
                stored.title = f"Edited {workflow.execution_type}"
                await session.commit()
                await seed_demo(session, settings)
                assert stored.title == f"Edited {workflow.execution_type}"
                assert (await repository.get(run.id)).status == "COMPLETED"
    finally:
        await engine.dispose()


async def test_decision_variants_pause_and_support_every_resolution_after_reload(
    infrastructure: tuple[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    database_url, redis_url = infrastructure
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("REDIS_URL", redis_url)
    get_settings.cache_clear()
    engine = create_async_engine(database_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        await asyncio.to_thread(command.upgrade, Config("alembic.ini"), "head")
        async with sessions() as session:
            await seed_demo(session, get_settings())
            await seed_demo(session, get_settings())
            assert await session.scalar(select(func.count()).select_from(Workflow)) == 6
        for workflow in workflow_payloads(with_decisions=True):
            assert validate_workflow_graph(workflow) == []
            for action in ("assign_fixes", "continue", "cancel"):
                async with sessions() as session:
                    repository = RunRepository(session)
                    service = RunService(repository)
                    created = await service.create(
                        RunCreate(
                            workflow_id=demo_id("workflow", workflow.execution_type + "_decision"),
                            task=DEMO_TASK,
                        )
                    )
                    run = await service.require(created.id)
                    await PlannerExecutor(repository).execute(run)
                    assert run.status == "AWAITING_CONFIRMATION"
                    await DAGExecutor(repository).execute(run)
                    assert not await repository.decisions(run.id)
                    await service.confirm(run.id)
                    await DAGExecutor(repository).execute(run)
                    assert run.status == "PAUSED"
                    assert run.pause_reasons == ["USER_DECISION_REQUIRED"]
                    steps = await repository.steps(run.id)
                    assert [step.status for step in steps] == ["COMPLETED"] * 4 + ["PENDING"]
                    decisions = await repository.decisions(run.id)
                    assert len(decisions) == 1
                    assert decisions[0].source_step_number == 4
                    assert decisions[0].suggested_agent_id == demo_id("agent", "developer")
                    preserved = [
                        (step.output, step.tokens_prompt, step.attempt) for step in steps[:4]
                    ]
                    run_id, decision_id = run.id, decisions[0].id
                async with sessions() as session:
                    repository = RunRepository(session)
                    service = RunService(repository)
                    run = await service.require(run_id)
                    await DAGExecutor(repository).execute(run)
                    assert run.status == "PAUSED"
                    payload = DecisionResolution(
                        action=action,
                        agent_id=demo_id("agent", "developer")
                        if action == "assign_fixes"
                        else None,
                        task="Fix title validation" if action == "assign_fixes" else None,
                    )
                    await service.resolve_decision(run_id, decision_id, payload)
                    await DAGExecutor(repository).execute(run)
                    assert run.status == ("CANCELLED" if action == "cancel" else "COMPLETED")
                    steps = await repository.steps(run_id)
                    assert preserved == [
                        (step.output, step.tokens_prompt, step.attempt) for step in steps[:4]
                    ]
                    decisions = await repository.decisions(run_id)
                    assert len(decisions) == 1 and decisions[0].status == "RESOLVED"
                    assert len(steps) == (7 if action == "assign_fixes" else 5)
                    if action == "assign_fixes":
                        assert "Correction handoff" in steps[5].output
                        assert "Correction verified" in steps[6].output
                        parents = [1, 2, 3, 4] if workflow.execution_type == "parallel" else [4]
                        assert steps[4].depends_on == [*parents, 6, 7]
                    if action != "cancel":
                        assert "User decision demo" in run.final_report
                        assert run.pause_reasons == []
                        assert all(step.status == "COMPLETED" for step in steps)
                        assert (
                            run.total_tokens
                            == run.planning_prompt_tokens
                            + run.planning_completion_tokens
                            + sum(step.tokens_prompt + step.tokens_completion for step in steps)
                        )
    finally:
        await engine.dispose()
