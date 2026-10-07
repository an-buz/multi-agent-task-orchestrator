"""LLM tests always use mock mode and cannot construct live SDK clients."""

import pytest
from app.core.config import get_settings


@pytest.fixture(autouse=True)
def mock_llm_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER_MODE", "mock")
    get_settings.cache_clear()

    def reject_real_client(*args: object, **kwargs: object) -> None:
        raise AssertionError("Real LLM clients are forbidden in tests")

    monkeypatch.setattr("app.llm.providers.AsyncAnthropic", reject_real_client)
    monkeypatch.setattr("app.llm.providers.AsyncOpenAI", reject_real_client)
