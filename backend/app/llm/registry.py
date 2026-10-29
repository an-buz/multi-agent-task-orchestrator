"""Configured model and tool catalogues used by API validation and LLM clients."""

from dataclasses import dataclass
from typing import Literal

from app.core.config import Settings, get_settings


@dataclass(frozen=True)
class ModelInfo:
    key: str
    provider: Literal["anthropic", "openai", "gemini"]
    model_id: str
    tier: Literal["fast", "balanced", "powerful"]
    context_window: int | None
    max_output_tokens: int | None


@dataclass(frozen=True)
class ToolInfo:
    key: str
    name: str
    description: str


def get_model_registry(settings: Settings | None = None) -> dict[str, ModelInfo]:
    """Build public model keys mapped to current provider API model IDs."""

    active = settings or get_settings()

    if active.llm_provider_mode == "real":
        from app.llm.discovery import cached_models

        return cached_models(active)

    # Only reviewed model IDs may reuse these limits and sampling parameters.
    profiles: dict[str, tuple[str, int, int]] = {
        "claude-haiku-4-5-20251001": ("anthropic", 200_000, 64_000),
        "claude-haiku-4-5": ("anthropic", 200_000, 64_000),
        "claude-sonnet-4-6": ("anthropic", 1_000_000, 128_000),
        "claude-opus-4-6": ("anthropic", 1_000_000, 128_000),
        "gpt-4o": ("openai", 128_000, 16_384),
        "gemini-3.8-flash": ("gemini", 1_048_576, 65_536),
        "gemini-3.5-flash-lite": ("gemini", 1_048_576, 65_536),
    }

    def reviewed(
        key: str,
        provider: Literal["anthropic", "openai", "gemini"],
        model_id: str,
        tier: Literal["fast", "balanced", "powerful"],
    ) -> ModelInfo:
        profile = profiles.get(model_id)

        if profile is None or profile[0] != provider:
            raise ValueError("Configured provider model has no reviewed compatibility profile")

        return ModelInfo(key, provider, model_id, tier, profile[1], profile[2])

    return {
        "claude-haiku": reviewed("claude-haiku", "anthropic", "claude-haiku-4-5-20251001", "fast"),
        "claude-sonnet": reviewed("claude-sonnet", "anthropic", "claude-sonnet-4-6", "balanced"),
        "claude-opus": reviewed("claude-opus", "anthropic", "claude-opus-4-6", "powerful"),
        "gpt-4o": reviewed("gpt-4o", "openai", "gpt-4o", "balanced"),
        "gemini-flash": reviewed("gemini-flash", "gemini", "gemini-3.8-flash", "balanced"),
        "gemini-flash-lite": reviewed(
            "gemini-flash-lite", "gemini", "gemini-3.5-flash-lite", "fast"
        ),
    }


TOOLS = {
    "web_search": ToolInfo("web_search", "Web Search", "Search the web for relevant information."),
    "code_executor": ToolInfo("code_executor", "Code Executor", "Run code in an isolated sandbox."),
    "calculator": ToolInfo("calculator", "Calculator", "Evaluate safe mathematical expressions."),
    "file_reader": ToolInfo(
        "file_reader", "File Reader", "Read files attached to the current run."
    ),
}
