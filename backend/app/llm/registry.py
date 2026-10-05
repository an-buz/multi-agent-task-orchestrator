"""Configured model and tool catalogues used by API validation and LLM clients."""

from dataclasses import dataclass
from typing import Literal

from app.core.config import Settings, get_settings


@dataclass(frozen=True)
class ModelInfo:
    key: str
    provider: Literal["anthropic", "openai"]
    model_id: str
    tier: Literal["fast", "balanced", "powerful"]
    context_window: int


@dataclass(frozen=True)
class ToolInfo:
    key: str
    name: str
    description: str


def get_model_registry(settings: Settings | None = None) -> dict[str, ModelInfo]:
    """Build public model keys mapped to current provider API model IDs."""
    active = settings or get_settings()
    return {
        "claude-haiku": ModelInfo(
            "claude-haiku", "anthropic", active.anthropic_model_haiku, "fast", 200_000
        ),
        "claude-sonnet": ModelInfo(
            "claude-sonnet", "anthropic", active.anthropic_model_sonnet, "balanced", 200_000
        ),
        "claude-opus": ModelInfo(
            "claude-opus", "anthropic", active.anthropic_model_opus, "powerful", 200_000
        ),
        "gpt-4o": ModelInfo("gpt-4o", "openai", active.openai_model_default, "balanced", 128_000),
    }


TOOLS = {
    "web_search": ToolInfo("web_search", "Web Search", "Search the web for relevant information."),
    "code_executor": ToolInfo("code_executor", "Code Executor", "Run code in an isolated sandbox."),
    "calculator": ToolInfo("calculator", "Calculator", "Evaluate safe mathematical expressions."),
    "file_reader": ToolInfo(
        "file_reader", "File Reader", "Read files attached to the current run."
    ),
}
