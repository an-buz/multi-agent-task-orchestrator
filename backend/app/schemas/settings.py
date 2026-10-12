"""Public configuration and validated default agent parameters."""

from pydantic import ConfigDict, Field

from app.schemas.base import StorageModel


class AgentDefaults(StorageModel):
    model_config = ConfigDict(extra="forbid")

    default_model: str
    temperature: float = Field(ge=0, le=1)
    max_tokens: int = Field(ge=1, le=8192)


class AppConfigRead(AgentDefaults):
    llm_provider_mode: str
    code_executor_backend: str
    anthropic_key_configured: bool
    openai_key_configured: bool
    tavily_key_configured: bool
