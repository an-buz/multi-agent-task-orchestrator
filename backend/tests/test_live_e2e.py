"""The live browser launcher must override credentials and reject real SDK clients."""

import pytest
from app.llm import providers

from run_live_e2e import guard_providers, live_environment


def test_live_environment_overrides_inherited_provider_and_storage_settings(monkeypatch):
    for key in ("DATABASE_URL", "REDIS_URL", "ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.setenv(key, "must-not-be-used")
    monkeypatch.setenv("LLM_PROVIDER_MODE", "real")
    monkeypatch.setenv("DEMO_MODE", "true")
    env = live_environment("isolated-postgres", "isolated-redis", 18123, 3123)
    assert env["DATABASE_URL"] == "isolated-postgres"
    assert env["REDIS_URL"] == "isolated-redis"
    assert env["LLM_PROVIDER_MODE"] == "mock"
    assert env["DEMO_MODE"] == "false"
    assert env["CODE_EXECUTOR_BACKEND"] == "disabled"
    assert env["ANTHROPIC_API_KEY"] == env["OPENAI_API_KEY"] == ""
    assert env["NEXT_PUBLIC_API_URL"] == env["E2E_LIVE_API_URL"]
    assert env["CORS_ORIGINS"] == '["http://localhost:3123"]'


def test_live_services_reject_real_clients_before_network_access(monkeypatch):
    # Register the originals so pytest restores them after the service guard changes them.
    monkeypatch.setattr(providers, "AsyncAnthropic", providers.AsyncAnthropic)
    monkeypatch.setattr(providers, "AsyncOpenAI", providers.AsyncOpenAI)
    guard_providers()
    for client in (providers.AsyncAnthropic, providers.AsyncOpenAI):
        with pytest.raises(AssertionError, match="forbidden in live E2E"):
            client(api_key="unused")
