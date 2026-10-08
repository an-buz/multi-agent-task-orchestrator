"""Anthropic, OpenAI, and deterministic mock provider implementations."""

import json

from anthropic import AsyncAnthropic
from openai import AsyncOpenAI

from app.core.config import Settings, get_settings
from app.llm.planning import PLANNER_SYSTEM_PROMPT
from app.llm.provider import LLMResponse, LLMUsage
from app.llm.registry import get_model_registry


class AnthropicProvider:
    """Adapter for Anthropic's Messages API."""

    def __init__(self, api_key: str) -> None:
        self._client = AsyncAnthropic(
            api_key=api_key, max_retries=0, timeout=get_settings().llm_request_timeout
        )

    async def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str,
        *,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        info = get_model_registry()[model]
        response = await self._client.messages.create(
            model=info.model_id,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        content = "".join(block.text for block in response.content if block.type == "text")
        return LLMResponse(
            content=content,
            usage=LLMUsage(
                input_tokens=response.usage.input_tokens, output_tokens=response.usage.output_tokens
            ),
        )

    async def aclose(self) -> None:
        await self._client.close()


class OpenAIProvider:
    """Adapter for OpenAI Chat Completions API."""

    def __init__(self, api_key: str) -> None:
        self._client = AsyncOpenAI(
            api_key=api_key, max_retries=0, timeout=get_settings().llm_request_timeout
        )

    async def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str,
        *,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        info = get_model_registry()[model]
        response = await self._client.chat.completions.create(
            model=info.model_id,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        content = response.choices[0].message.content or ""
        usage = response.usage
        return LLMResponse(
            content=content,
            usage=LLMUsage(
                input_tokens=usage.prompt_tokens if usage else 0,
                output_tokens=usage.completion_tokens if usage else 0,
            ),
        )

    async def aclose(self) -> None:
        await self._client.close()


class MockLLMProvider:
    """Provider-compatible deterministic local response for development without keys."""

    async def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str,
        *,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        del model, temperature, max_tokens
        if system_prompt == PLANNER_SYSTEM_PROMPT:
            request = json.loads(user_prompt)
            return LLMResponse(
                content=json.dumps(
                    {
                        "summary": "Mock plan for the supplied workflow",
                        "steps": [
                            {
                                "step_number": step["step_number"],
                                "agent_id": step["agent_id"],
                                "depends_on": step["depends_on"],
                                "subtask": f"{step['role']}: {request['task']}",
                            }
                            for step in request["steps"]
                        ],
                    }
                ),
                usage=LLMUsage(input_tokens=max(1, len(user_prompt.split())), output_tokens=5),
            )
        return LLMResponse(
            content=f"Mock response: {user_prompt[:500]}",
            usage=LLMUsage(input_tokens=max(1, len(user_prompt.split())), output_tokens=5),
        )

    async def aclose(self) -> None:
        pass


class MockAnthropicProvider(MockLLMProvider):
    """Anthropic model alias using the shared deterministic mock implementation."""


class MockOpenAIProvider(MockLLMProvider):
    """OpenAI model alias using the shared deterministic mock implementation."""


def create_provider(
    model: str, settings: Settings | None = None
) -> AnthropicProvider | OpenAIProvider | MockAnthropicProvider | MockOpenAIProvider:
    """Create configured mock or real provider, failing clearly when a key is missing."""
    active = settings or get_settings()
    info = get_model_registry(active).get(model)
    if info is None:
        raise ValueError(f"Unknown model key: {model}")
    if active.llm_provider_mode == "mock":
        return MockAnthropicProvider() if info.provider == "anthropic" else MockOpenAIProvider()
    if info.provider == "anthropic":
        if not active.anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY is required when LLM_PROVIDER_MODE=real")
        return AnthropicProvider(active.anthropic_api_key)
    if not active.openai_api_key:
        raise ValueError("OPENAI_API_KEY is required when LLM_PROVIDER_MODE=real")
    return OpenAIProvider(active.openai_api_key)
