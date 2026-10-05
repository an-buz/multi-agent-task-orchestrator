"""Agent API schemas."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

NonBlank = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class AgentCreate(BaseModel):
    """Validated agent creation input."""

    name: Annotated[NonBlank, Field(max_length=100)]
    role: Annotated[NonBlank, Field(max_length=500)]
    system_prompt: NonBlank
    model: str = "claude-sonnet"
    temperature: float = Field(default=0.7, ge=0.0, le=1.0)
    max_tokens: int = Field(default=4096, ge=1)
    context_window: int = Field(default=128000, ge=1)
    tools: list[str] = Field(default_factory=list)


class AgentRead(BaseModel):
    """Public agent representation."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    role: str
    system_prompt: str
    model: str
    temperature: float
    max_tokens: int
    context_window: int
    tools: list[str]
    created_at: datetime
    updated_at: datetime
