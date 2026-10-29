"""Context admission checks kept separate from authoritative usage metrics."""

import asyncio
import json
from typing import Any, Protocol, runtime_checkable

from app.core.config import get_settings
from app.llm.registry import get_model_registry


class ContextTooLarge(ValueError):
    """Input plus reserved output cannot fit the effective context window."""


@runtime_checkable
class TokenCountingProvider(Protocol):
    async def count_input_tokens(
        self,
        system_prompt: str,
        messages: list[dict[str, Any]],
        model: str,
        tools: list[dict[str, Any]],
    ) -> int: ...


def conservative_input_size(
    system_prompt: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
) -> int:
    """Byte-based admission fallback for mocks/custom providers, never billed usage."""

    payload = {"system": system_prompt, "messages": messages, "tools": tools}

    return len(json.dumps(payload, ensure_ascii=False).encode("utf-8"))


async def check_context(
    provider: object,
    system_prompt: str,
    messages: list[dict[str, Any]],
    model: str,
    tools: list[dict[str, Any]],
    max_tokens: int,
    context_window: int | None = None,
) -> None:
    settings = get_settings()
    info = get_model_registry(settings)[model]

    if max_tokens < 1 or (
        info.max_output_tokens is not None and max_tokens > info.max_output_tokens
    ):
        raise ValueError("Requested response exceeds the model output limit")

    windows = [value for value in (info.context_window, context_window) if value is not None]
    window = min(windows) if windows else None
    reserve = max_tokens + settings.context_safety_margin_tokens

    if window is not None and reserve >= window:
        raise ContextTooLarge("The reserved response leaves no room for input.")

    if isinstance(provider, TokenCountingProvider):
        async with asyncio.timeout(settings.llm_request_timeout):
            count = await provider.count_input_tokens(system_prompt, messages, model, tools)
    else:
        count = await asyncio.to_thread(conservative_input_size, system_prompt, messages, tools)

    if type(count) is not int or count < 0:
        raise ValueError("Invalid context admission count")

    if window is not None and count + reserve > window:
        raise ContextTooLarge("Input and reserved response exceed the context window.")
