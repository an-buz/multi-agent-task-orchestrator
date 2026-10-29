"""Regression tests for validated and non-sensitive settings persistence."""

from collections.abc import Generator
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest
from app.api.v1.settings import get_settings_service
from app.core.config import Settings
from app.db.settings_repository import SettingsRepository
from app.main import app
from app.schemas.settings import AppConfigUpdate
from app.services.models import ModelUnavailable
from app.services.settings import SettingsError, SettingsService
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession


class MemorySettingsRepository(SettingsRepository):
    def __init__(self) -> None:
        self.session = cast(AsyncSession, AsyncMock())
        self.defaults: dict[str, object] | None = None

    async def read(self) -> dict[str, object] | None:
        return self.defaults

    async def save(self, defaults: dict[str, object]) -> None:
        self.defaults = {**(self.defaults or {}), **defaults}


@pytest.fixture
def settings_client() -> Generator[TestClient, Any]:
    repository = MemorySettingsRepository()
    settings = Settings(
        _env_file=None, anthropic_api_key="test-secret", gemini_api_key="gemini-secret"
    )
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
    assert before.json()["planner_model"] == "claude-sonnet"

    values = {
        "default_model": "claude-haiku",
        "planner_model": "gemini-flash-lite",
        "temperature": 0.3,
        "max_tokens": 2048,
    }

    saved = settings_client.patch("/api/v1/settings/config", json=values)

    assert saved.status_code == 200

    read = settings_client.get("/api/v1/settings/config")

    assert all(read.json()[key] == value for key, value in values.items())
    assert read.json()["anthropic_key_configured"] is True
    assert read.json()["gemini_key_configured"] is True
    assert "test-secret" not in read.text
    assert "gemini-secret" not in read.text


@pytest.mark.parametrize(
    "invalid",
    [
        {"default_model": "unknown"},
        {"temperature": 1.1},
        {"max_tokens": 0},
        {"max_tokens": 8193},
        {"anthropic_api_key": "must-not-save"},
        {"gemini_api_key": "must-not-save"},
        {"planner_model": "unknown"},
        {"planner_model": ""},
        {"planner_model": 42},
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


async def test_legacy_defaults_use_fallback_and_legacy_updates_preserve_planner():
    repository = MemorySettingsRepository()

    repository.defaults = {"default_model": "claude-haiku", "temperature": 0.3, "max_tokens": 2048}

    settings = Settings(_env_file=None, planner_model="gpt-4o")
    service = SettingsService(repository, settings)

    assert (await service.read()).planner_model == "gpt-4o"

    await service.update(AppConfigUpdate(**repository.defaults, planner_model="gemini-flash-lite"))

    # A new service instance reads persisted data rather than process configuration.
    service = SettingsService(
        repository, settings.model_copy(update={"planner_model": "claude-sonnet"})
    )

    assert (await service.read()).planner_model == "gemini-flash-lite"

    legacy = AppConfigUpdate(default_model="claude-haiku", temperature=0.4, max_tokens=1024)

    assert (await service.update(legacy)).planner_model == "gemini-flash-lite"
    assert repository.defaults["temperature"] == 0.4


@pytest.mark.parametrize("disabled", [False, True])
async def test_planner_selection_rejects_disconnected_or_disabled_models(monkeypatch, disabled):
    from app.llm.registry import get_model_registry

    registry = get_model_registry(Settings(_env_file=None, llm_provider_mode="mock"))

    async def fetch_models(provider, token, url, settings):
        return {key: info for key, info in registry.items() if info.provider == provider}

    monkeypatch.setattr("app.llm.discovery.fetch_models", fetch_models)

    repository = MemorySettingsRepository()
    settings = Settings(
        _env_file=None,
        llm_provider_mode="real",
        anthropic_api_key="placeholder",
        gemini_api_key="placeholder" if disabled else "",
    )

    if disabled:
        monkeypatch.setattr(
            "app.services.models.ModelService.available", AsyncMock(return_value={"claude-haiku"})
        )

    service = SettingsService(repository, settings)

    with pytest.raises(ModelUnavailable, match="planner"):
        await service.update(
            AppConfigUpdate(
                default_model="claude-haiku",
                planner_model="gemini-flash-lite",
                temperature=0.3,
                max_tokens=1024,
            )
        )

    assert repository.defaults is None


async def test_planner_selection_respects_configured_output_limit():
    repository = MemorySettingsRepository()
    settings = Settings(_env_file=None, planner_max_tokens=65537)

    with pytest.raises(SettingsError, match="planner token limit"):
        await SettingsService(repository, settings).update(
            AppConfigUpdate(
                default_model="claude-haiku",
                planner_model="gemini-flash-lite",
                temperature=0.3,
                max_tokens=1024,
            )
        )

    assert repository.defaults is None
