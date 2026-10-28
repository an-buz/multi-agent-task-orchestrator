"""Persist planner selection across HTTP sessions and freeze it into new Runs."""

from unittest.mock import AsyncMock
from uuid import UUID

from app.db.settings_repository import SettingsRepository
from app.models.run import Run

from test_model_settings import model_client as _model_client
from test_run_integration import infrastructure as _infrastructure

infrastructure = _infrastructure
model_client = _model_client


async def test_planner_settings_persist_and_only_affect_new_runs(model_client, monkeypatch):
    client, sessions = model_client
    monkeypatch.setattr("app.api.v1.runs.enqueue_plan", AsyncMock())
    defaults = {"default_model": "claude-haiku", "temperature": 0.3, "max_tokens": 2048}
    saved = await client.patch("/settings/config", json={**defaults, "planner_model": "gpt-4o"})
    assert saved.status_code == 200, saved.text
    # A legacy write must merge atomically without clearing the saved planner choice.
    assert (await client.patch("/settings/config", json=defaults)).json()[
        "planner_model"
    ] == "gpt-4o"
    async with sessions() as session:
        repository = SettingsRepository(session)
        assert (await repository.read())["planner_model"] == "gpt-4o"
        await repository.save({"temperature": 0.4})
        # Reading after the upsert must bypass any stale ORM identity-map object.
        assert (await repository.read())["temperature"] == 0.4
        assert (await repository.read())["planner_model"] == "gpt-4o"

    agent = await client.post(
        "/agents",
        json={
            "name": "Planner settings agent",
            "role": "Review",
            "system_prompt": "Review",
            "model": "claude-haiku",
        },
    )
    assert agent.status_code == 201, agent.text
    workflow = await client.post(
        "/workflows",
        json={
            "title": "Planner settings workflow",
            "execution_type": "sequential",
            "steps": [{"step_number": 1, "agent_id": agent.json()["id"]}],
            "graph_layout": {},
        },
    )
    assert workflow.status_code == 201, workflow.text
    payload = {"workflow_id": workflow.json()["id"], "task": "Review"}
    first = await client.post("/runs", json=payload)
    assert first.status_code == 201, first.text
    assert (
        await client.patch(
            "/settings/config", json={**defaults, "planner_model": "gemini-flash-lite"}
        )
    ).status_code == 200
    second = await client.post("/runs", json=payload)
    assert second.status_code == 201, second.text
    async with sessions() as session:
        assert (await session.get(Run, UUID(first.json()["id"]))).planner_config[
            "model"
        ] == "gpt-4o"
        assert (await session.get(Run, UUID(second.json()["id"]))).planner_config[
            "model"
        ] == "gemini-flash-lite"
    assert (
        await client.patch("/settings/models/gemini-flash-lite", json={"enabled": False})
    ).status_code == 200
    blocked = await client.post("/runs", json=payload)
    assert blocked.status_code == 422
    assert "planner model" in blocked.json()["error"]["message"]
    invalid = await client.patch(
        "/settings/config", json={**defaults, "planner_model": "gemini-flash-lite"}
    )
    assert invalid.status_code == 422
    assert (await client.get("/settings/config")).json()["planner_model"] == "gemini-flash-lite"
