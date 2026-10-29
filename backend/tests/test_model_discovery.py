"""Authenticated discovery and execution use HTTP fixtures, never real providers."""

import asyncio
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from app.core.config import Settings, get_settings
from app.db.model_repository import ModelRepository
from app.llm import discovery
from app.llm.context import ContextTooLarge, check_context
from app.llm.providers import OpenAIProvider, create_provider
from app.llm.registry import get_model_registry
from app.schemas.agent import AgentCreate
from app.services.agents import AgentService
from app.services.models import ModelService

from test_agents import MemorySession


def real_settings(**kwargs):
    return Settings(
        _env_file=None,
        llm_provider_mode="real",
        anthropic_api_key="",
        openai_api_key="fixture-secret",
        gemini_api_key="",
    ).model_copy(update=kwargs)


def install_transport(monkeypatch, handler):
    requests = []

    def handle(request):
        requests.append(request)

        return handler(request)

    def client(**kwargs):
        return httpx.AsyncClient(transport=httpx.MockTransport(handle), **kwargs)

    monkeypatch.setattr(discovery, "DiscoveryClient", client)

    return requests


@pytest.mark.parametrize("mode", ["mock", "real"])
async def test_mock_and_disconnected_modes_never_fetch(monkeypatch, mode):
    settings = real_settings(openai_api_key="", llm_provider_mode=mode)
    fetch = AsyncMock(side_effect=AssertionError("Network must not be used"))
    monkeypatch.setattr(discovery, "fetch_models", fetch)

    registry = await discovery.refresh_model_registry(settings)

    assert len(registry) == (6 if mode == "mock" else 0)
    fetch.assert_not_awaited()


@pytest.mark.parametrize("provider", ["anthropic", "openai", "gemini"])
async def test_authenticated_discovery_and_pagination(monkeypatch, provider):
    settings = real_settings(**{"openai_api_key": "", f"{provider}_api_key": "fixture-secret"})
    ids = {"anthropic": "claude-new", "openai": "gpt-new", "gemini": "gemini-new"}
    model_id = ids[provider]

    def handler(request):
        assert request.url.path.endswith("/models")
        assert "fixture-secret" not in str(request.url)
        header = {"anthropic": "x-api-key", "openai": "authorization", "gemini": "x-goog-api-key"}[
            provider
        ]
        assert request.headers[header] == (
            "Bearer fixture-secret" if provider == "openai" else "fixture-secret"
        )

        page_two = bool(request.url.params)
        suffix = "-second" if page_two else ""
        row = (
            {
                "name": f"models/{model_id}{suffix}",
                "supportedGenerationMethods": ["generateContent"],
                "inputTokenLimit": 32000,
                "outputTokenLimit": 4096,
            }
            if provider == "gemini"
            else {"id": model_id + suffix, "max_input_tokens": 32000, "max_tokens": 4096}
        )
        payload = {"models" if provider == "gemini" else "data": [row]}

        if not page_two:
            payload.update(
                {"nextPageToken": "next"}
                if provider == "gemini"
                else {"has_more": True, "last_id": "next"}
            )
        else:
            assert request.url.params["pageToken" if provider == "gemini" else "after_id"] == "next"

        return httpx.Response(200, json=payload)

    requests = install_transport(monkeypatch, handler)
    registry = await discovery.refresh_model_registry(settings)

    assert set(registry) == {model_id, model_id + "-second"}
    assert registry[model_id].context_window == 32000
    assert registry[model_id].max_output_tokens == 4096
    assert len(requests) == 2


async def test_cache_singleflight_expiry_and_key_isolation(monkeypatch):
    clock = [1.0]
    monkeypatch.setattr(discovery, "monotonic", lambda: clock[0])
    requests = install_transport(
        monkeypatch, lambda request: httpx.Response(200, json={"data": [{"id": "gpt-new"}]})
    )
    settings = real_settings()

    await asyncio.gather(*(discovery.refresh_model_registry(settings) for _ in range(8)))
    assert len(requests) == 1

    other = real_settings(openai_api_key="another-key")
    assert get_model_registry(other) == {}
    await discovery.refresh_model_registry(other)
    assert len(requests) == 2
    assert get_model_registry(real_settings(openai_api_key="")) == {}

    clock[0] += settings.model_discovery_cache_seconds + 1
    await discovery.refresh_model_registry(settings)
    assert len(requests) == 3


@pytest.mark.parametrize("failure", ["auth", "server", "timeout", "malformed", "cursor"])
async def test_failures_are_isolated_redacted_and_never_use_stale_models(monkeypatch, failure):
    settings = real_settings(anthropic_api_key="fixture-secret")
    fail = [False]

    def handler(request):
        if "anthropic" in request.url.host:
            return httpx.Response(200, json={"data": [{"id": "claude-new"}]})

        if fail[0]:
            if failure == "timeout":
                raise httpx.ReadTimeout("fixture-secret", request=request)

            if failure == "malformed":
                return httpx.Response(200, json={"data": "fixture-secret"})

            if failure == "cursor":
                return httpx.Response(
                    200, json={"data": [], "has_more": True, "last_id": "repeated"}
                )

            return httpx.Response(401 if failure == "auth" else 500, text="fixture-secret")

        return httpx.Response(200, json={"data": [{"id": "gpt-new"}]})

    requests = install_transport(monkeypatch, handler)
    await discovery.refresh_model_registry(settings)
    fail[0] = True

    for key, entry in discovery._cache.items():
        if key[0] == "openai":
            entry.expires_at = 0

    repository = AsyncMock(spec=ModelRepository)
    repository.disabled.return_value = set()
    service = ModelService(repository, settings)
    catalogue = await service.catalogue()

    assert [model.key for model in catalogue.items] == ["claude-new"]
    assert set(catalogue.discovery_errors) == {"openai"}
    assert "fixture-secret" not in catalogue.model_dump_json()
    count = len(requests)
    assert await service.available() == {"claude-new"}
    assert len(requests) == count


async def test_dynamic_ids_limits_switches_and_real_factory(monkeypatch):
    settings = real_settings()
    install_transport(
        monkeypatch,
        lambda request: httpx.Response(
            200,
            json={
                "data": [{"id": "gpt-new"}, {"id": "text-embedding-new"}, {"id": "gpt-image-new"}]
            },
        ),
    )
    monkeypatch.setattr(
        "app.services.agents.get_model_registry", lambda: get_model_registry(settings)
    )
    repository = AsyncMock(spec=ModelRepository)
    repository.disabled.return_value = {"gpt-new"}
    service = ModelService(repository, settings)

    catalogue = await service.catalogue()
    assert [model.key for model in catalogue.items] == ["gpt-new"]
    assert catalogue.items[0].context_window is None
    assert catalogue.items[0].max_output_tokens is None
    assert await service.available() == set()
    assert (await service.catalogue(enabled_only=True)).items == []
    await service.update("gpt-new", True)
    repository.set_enabled.assert_awaited_once_with("gpt-new", True)

    payload = AgentCreate(name="Discovered", role="Test", system_prompt="Test", model="gpt-new")
    AgentService(None).validate(payload)

    client = AsyncMock()
    monkeypatch.setattr("app.llm.providers.AsyncOpenAI", lambda **kwargs: client)
    provider = create_provider("gpt-new", settings)
    assert isinstance(provider, OpenAIProvider)
    client.chat.completions.create.return_value = type(
        "Response",
        (),
        {
            "choices": [
                type(
                    "Choice",
                    (),
                    {
                        "message": type("Message", (), {"content": "ok", "refusal": None})(),
                        "finish_reason": "stop",
                    },
                )()
            ],
            "usage": type("Usage", (), {"prompt_tokens": 1, "completion_tokens": 1})(),
        },
    )()

    response = await provider.complete("System", "User", "gpt-new")
    assert response.content == "ok"
    assert client.chat.completions.create.call_args.kwargs["model"] == "gpt-new"


async def test_unknown_provider_limits_keep_agent_context_admission(monkeypatch):
    info = replace(get_model_registry()["gpt-4o"], context_window=None, max_output_tokens=None)
    monkeypatch.setattr("app.llm.context.get_model_registry", lambda _: {"gpt-new": info})
    provider = SimpleNamespace(count_input_tokens=AsyncMock(return_value=1000))

    with pytest.raises(ContextTooLarge):
        await check_context(provider, "System", [], "gpt-new", [], 100, 1050)

    await check_context(provider, "System", [], "gpt-new", [], 100, 2000)


@pytest.mark.parametrize("model_id", ["o3", "gpt-5-mini", "gpt-6-sol"])
def test_reasoning_sampling_omits_unsupported_temperature(model_id):
    assert OpenAIProvider.sampling(model_id, 0.7) == {}


async def test_real_http_catalogue_and_agent_creation_use_discovered_ids(monkeypatch):
    from app.db.session import get_session
    from app.main import app

    monkeypatch.setenv("LLM_PROVIDER_MODE", "real")
    monkeypatch.setenv("OPENAI_API_KEY", "fixture-secret")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    get_settings.cache_clear()
    install_transport(
        monkeypatch, lambda request: httpx.Response(200, json={"data": [{"id": "gpt-discovered"}]})
    )
    session = MemorySession()

    async def override_session():
        yield session

    app.dependency_overrides[get_session] = override_session

    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test/api/v1"
        ) as client:
            catalogue = await client.get("/settings/models")
            assert catalogue.status_code == 200
            assert [model["key"] for model in catalogue.json()["items"]] == ["gpt-discovered"]
            assert catalogue.json()["discovery_errors"] == {}

            response = await client.post(
                "/agents",
                json={
                    "name": "Discovered agent",
                    "role": "Test",
                    "system_prompt": "System",
                    "model": "gpt-discovered",
                },
            )
            assert response.status_code == 201
            assert response.json()["model"] == "gpt-discovered"
            assert response.json()["available"] is True

            response = await client.post(
                "/agents",
                json={
                    "name": "Legacy",
                    "role": "Test",
                    "system_prompt": "System",
                    "model": "claude-sonnet",
                },
            )
            assert response.status_code == 422
    finally:
        app.dependency_overrides.pop(get_session, None)
