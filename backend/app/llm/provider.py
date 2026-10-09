"""Provider interface shared by LLM backends."""

from collections.abc import AsyncGenerator
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field


class ToolCall(BaseModel):
    id: str
    name: str
    arguments: dict[str, Any]


class LLMUsage(BaseModel):
    """Token usage reported by an LLM provider."""

    input_tokens: int
    output_tokens: int


class LLMResponse(BaseModel):
    """Normalized text response and provider-reported usage."""

    content: str
    usage: LLMUsage
    tool_calls: list[ToolCall] = Field(default_factory=list)
    message: dict[str, Any] = Field(default_factory=dict)


class LLMChunk(BaseModel):
    """Text delta or terminal response containing authoritative usage and tool calls."""

    text_delta: str = ""
    response: LLMResponse | None = None


@runtime_checkable
class StreamingLLMProvider(Protocol):
    """Optional streaming capability; complete-only providers remain supported."""

    def stream(
        self,
        system_prompt: str,
        messages: list[dict[str, Any]],
        model: str,
        tools: list[dict[str, Any]],
        *,
        temperature: float,
        max_tokens: int,
    ) -> AsyncGenerator[LLMChunk]: ...


class LLMProvider(Protocol):
    """Interface implemented by real and mock LLM providers."""

    async def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str,
        *,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        """Generate a completion and return provider usage."""

    async def aclose(self) -> None:
        """Release provider HTTP resources after the completion retry loop."""

    async def complete_tools(
        self,
        system_prompt: str,
        messages: list[dict[str, Any]],
        model: str,
        tools: list[dict[str, Any]],
        *,
        temperature: float,
        max_tokens: int,
    ) -> LLMResponse:
        """Continue a conversation containing native tool calls and results."""
