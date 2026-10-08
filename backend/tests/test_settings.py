"""Regression tests for validated and non-sensitive settings persistence."""

from collections.abc import Generator
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest
from app.api.v1.settings import get_settings_service
from app.core.config import Settings
from app.db.settings_repository import SettingsRepository
from app.main import app
from app.services.settings import SettingsService
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession


class MemorySettingsRepository(SettingsRepository):
    def __init__(self) -> None:
        self.session = cast(AsyncSession, AsyncMock())
        self.defaults: dict[str, object] | None = None

    async def read(self) -> dict[str, object] | None:
        return self.defaults

    async def save(self, defaults: dict[str, object]) -> None:
        self.defaults = defaults


@pytest.fixture
def settings_client() -> Generator[TestClient, Any]:
    repository = MemorySettingsRepository()
    settings = Settings(_env_file=None, anthropic_api_key="test-secret")
    app.dependency_overrides[get_settings_service] = lambda: SettingsService(repository, settings)
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.clear()


def test_settings_are_saved_and_read_without_secrets(settings_client: TestClient) -> None:
    before = settings_client.get("/api/v1/settings/config")
    assert before.status_code == 200
    assert before.json()["default_model"] == "claude-sonnet"
    values = {"default_model": "claude-haiku", "temperature": 0.3, "max_tokens": 2048}
    saved = settings_client.patch("/api/v1/settings/config", json=values)
    assert saved.status_code == 200
    read = settings_client.get("/api/v1/settings/config")
    assert all(read.json()[key] == value for key, value in values.items())
    assert read.json()["anthropic_key_configured"] is True
    assert "test-secret" not in read.text


@pytest.mark.parametrize(
    "invalid",
    [
        {"default_model": "unknown"},
        {"temperature": 1.1},
        {"max_tokens": 0},
        {"max_tokens": 8193},
        {"anthropic_api_key": "must-not-save"},
    ],
)
def test_invalid_settings_do_not_overwrite_defaults(
    settings_client: TestClient, invalid: dict[str, object]
) -> None:
    before = settings_client.get("/api/v1/settings/config").json()
    values = {"default_model": "claude-haiku", "temperature": 0.3, "max_tokens": 2048}
    assert (
        settings_client.patch("/api/v1/settings/config", json=values | invalid).status_code == 422
    )
    assert settings_client.get("/api/v1/settings/config").json() == before
