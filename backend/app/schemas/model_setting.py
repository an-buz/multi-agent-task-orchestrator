"""Public model settings contain no provider secrets."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ModelSwitch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(strict=True)


class ModelRead(BaseModel):
    key: str
    provider: Literal["anthropic", "openai", "gemini"]
    model_id: str
    tier: Literal["fast", "balanced", "powerful"]
    context_window: int | None
    max_output_tokens: int | None
    enabled: bool


class ModelCatalogue(BaseModel):
    items: list[ModelRead]
    discovery_errors: dict[str, str] = Field(default_factory=dict)
