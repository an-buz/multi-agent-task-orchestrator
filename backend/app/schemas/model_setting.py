"""Public model settings contain no provider secrets."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ModelSwitch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(strict=True)


class ModelRead(BaseModel):
    key: str
    provider: Literal["anthropic", "openai"]
    model_id: str
    tier: Literal["fast", "balanced", "powerful"]
    context_window: int
    enabled: bool


class ModelCatalogue(BaseModel):
    items: list[ModelRead]
