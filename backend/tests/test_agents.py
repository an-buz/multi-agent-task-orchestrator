"""Tests for agent creation validation and persistence."""

from collections.abc import AsyncGenerator, Generator
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest
from app.db.session import get_session
from app.main import app
from app.models.agent import Agent
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession


class MemorySession:
    """Small async session stub to exercise the HTTP contract without PostgreSQL."""

    def __init__(self) -> None:
        self.agent: Agent | None = None
        self.created_at = datetime.now(UTC)

    def add(self, agent: Agent) -> None:
        self.agent = agent

    async def commit(self) -> None:
        if self.agent is not None:
            self.agent.id = UUID("8db0829e-1134-4c3e-a9da-94564a9596fb")
            self.agent.created_at = self.created_at
            self.agent.updated_at = self.created_at

    async def refresh(self, agent: Agent) -> None:
        del agent


@pytest.fixture
def test_client() -> Generator[TestClient, Any]:
    session = MemorySession()

    async def override_session() -> AsyncGenerator[AsyncSession, Any]:
        yield session  # type: ignore[misc]

    app.dependency_overrides[get_session] = override_session
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.clear()


def test_create_agent_persists_agent(test_client: TestClient) -> None:
    """The frontend payload returns a created agent with its defaults and fields."""
    response = test_client.post(
        "/api/v1/agents",
        json={
            "name": "Market Analyst",
            "role": "Analyze the market",
            "system_prompt": "Be accurate and concise.",
            "model": "claude-sonnet",
            "temperature": 0.2,
            "max_tokens": 4096,
            "context_window": 128000,
            "tools": ["web_search"],
        },
    )

    assert response.status_code == 201
    assert response.json()["id"] == "8db0829e-1134-4c3e-a9da-94564a9596fb"
    assert response.json()["model"] == "claude-sonnet"
    assert response.json()["tools"] == ["web_search"]


def test_create_agent_rejects_unknown_model(test_client: TestClient) -> None:
    """Unknown public model keys cannot be stored."""
    response = test_client.post(
        "/api/v1/agents",
        json={"name": "Agent", "role": "Role", "system_prompt": "Prompt", "model": "unknown"},
    )

    assert response.status_code == 422


def test_models_and_tools_catalogues_are_available(test_client: TestClient) -> None:
    """Frontend catalogues match the accepted model aliases and safe tools."""
    models = test_client.get("/api/v1/agents/models")
    tools = test_client.get("/api/v1/agents/tools")

    assert models.status_code == 200
    assert {item["key"] for item in models.json()["items"]} >= {"claude-sonnet", "gpt-4o"}
    assert tools.status_code == 200
    assert "web_search" in {item["key"] for item in tools.json()["items"]}
