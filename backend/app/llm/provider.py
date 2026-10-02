"""Provider interface shared by LLM backends."""

from typing import Protocol

from pydantic import BaseModel


class LLMUsage(BaseModel):
    """Token usage reported by an LLM provider."""

    input_tokens: int
    output_tokens: int


class LLMResponse(BaseModel):
    """Normalized text response and provider-reported usage."""

    content: str
    usage: LLMUsage


class LLMProvider(Protocol):
    """Interface implemented by real and mock LLM providers."""

    async def complete(self, system_prompt: str, user_prompt: str, model: str) -> LLMResponse:
        """Generate a completion and return provider usage."""
