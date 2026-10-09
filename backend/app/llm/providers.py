"""Anthropic, OpenAI, and deterministic mock provider implementations."""

import asyncio
import json
from collections.abc import AsyncGenerator
from typing import Any, cast

from anthropic import AsyncAnthropic
from anthropic.types import MessageParam, ToolParam
from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessageParam, ChatCompletionToolParam

from app.core.config import Settings, get_settings
from app.llm.planning import PLANNER_SYSTEM_PROMPT
from app.llm.provider import LLMChunk, LLMResponse, LLMUsage, ToolCall
from app.llm.registry import get_model_registry


def parse_tool_arguments(raw: str) -> dict[str, Any]:
    """Keep usage and call identity even when a model emits invalid arguments."""
    try:
        value = json.loads(raw)
        if isinstance(value, dict):
            return cast(dict[str, Any], value)
    except ValueError, RecursionError:
        pass
    return {"_invalid_arguments": True}


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
        native: list[dict[str, Any]] = []
        for message in messages:
            if message["role"] == "tool":
                block = {
                    "type": "tool_result",
                    "tool_use_id": message["tool_call_id"],
                    "content": message["content"],
                }
                if (
                    native
                    and native[-1]["role"] == "user"
                    and isinstance(native[-1]["content"], list)
                ):
                    native[-1]["content"].append(block)
                else:
                    native.append({"role": "user", "content": [block]})
            elif message["role"] == "assistant":
                native.append({"role": "assistant", "content": message["blocks"]})
            else:
                native.append(message)
        response = await self._client.messages.create(
            model=get_model_registry()[model].model_id,
            system=system_prompt,
            messages=cast(list[MessageParam], native),
            tools=cast(list[ToolParam], tools),
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return LLMResponse(
            content="".join(block.text for block in response.content if block.type == "text"),
            usage=LLMUsage(
                input_tokens=response.usage.input_tokens, output_tokens=response.usage.output_tokens
            ),
            tool_calls=[
                ToolCall(id=block.id, name=block.name, arguments=cast(dict[str, Any], block.input))
                for block in response.content
                if block.type == "tool_use"
            ],
            message={
                "role": "assistant",
                "blocks": [block.model_dump() for block in response.content],
            },
        )


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
        response = await self._client.chat.completions.create(
            model=get_model_registry()[model].model_id,
            messages=cast(
                list[ChatCompletionMessageParam],
                [{"role": "system", "content": system_prompt}, *messages],
            ),
            tools=cast(
                list[ChatCompletionToolParam],
                [
                    {
                        "type": "function",
                        "function": {
                            "name": tool["name"],
                            "description": tool["description"],
                            "parameters": tool["input_schema"],
                        },
                    }
                    for tool in tools
                ],
            ),
            temperature=temperature,
            max_tokens=max_tokens,
        )
        message = response.choices[0].message
        calls = [call for call in message.tool_calls or [] if call.type == "function"]
        usage = response.usage
        return LLMResponse(
            content=message.content or "",
            usage=LLMUsage(
                input_tokens=usage.prompt_tokens if usage else 0,
                output_tokens=usage.completion_tokens if usage else 0,
            ),
            tool_calls=[
                ToolCall(
                    id=call.id,
                    name=call.function.name,
                    arguments=parse_tool_arguments(call.function.arguments),
                )
                for call in calls
            ],
            message={
                "role": "assistant",
                "content": message.content,
                "tool_calls": [call.model_dump() for call in calls],
            },
        )


class MockLLMProvider:
    """Provider-compatible deterministic local response for development without keys."""

    async def stream(
        self,
        system_prompt: str,
        messages: list[dict[str, Any]],
        model: str,
        tools: list[dict[str, Any]],
        *,
        temperature: float,
        max_tokens: int,
    ) -> AsyncGenerator[LLMChunk]:
        if tools:
            response = await self.complete_tools(
                system_prompt,
                messages,
                model,
                tools,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        else:
            response = await self.complete(
                system_prompt,
                str(messages[-1]["content"]),
                model,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        settings = get_settings()
        for offset in range(0, len(response.content), settings.mock_stream_chunk_chars):
            await asyncio.sleep(settings.mock_stream_delay)
            yield LLMChunk(
                text_delta=response.content[offset : offset + settings.mock_stream_chunk_chars]
            )
        yield LLMChunk(response=response)

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
        del tools
        return await self.complete(
            system_prompt,
            str(messages[-1]["content"]),
            model,
            temperature=temperature,
            max_tokens=max_tokens,
        )


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
