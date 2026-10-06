"""Application settings endpoints."""

from typing import Any

from fastapi import APIRouter, Depends

from app.core.config import Settings, get_settings

router = APIRouter()


@router.get("/config")
def get_config(settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    """Return non-sensitive application configuration.

    Exposes LLM provider mode, code executor backend, and which API keys are configured,
    without exposing the actual key values.
    """
    return {
        "llm_provider_mode": settings.llm_provider_mode,
        "code_executor_backend": settings.code_executor_backend,
        "anthropic_key_configured": bool(settings.anthropic_api_key),
        "openai_key_configured": bool(settings.openai_api_key),
        "tavily_key_configured": bool(settings.tavily_api_key),
    }
