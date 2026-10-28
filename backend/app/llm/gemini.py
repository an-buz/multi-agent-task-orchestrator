"""Native Gemini GenerateContent adapter; tool execution stays in the orchestrator."""

import json
from collections.abc import AsyncGenerator
from copy import deepcopy
from typing import Any
from uuid import uuid4

import httpx
from httpx import AsyncClient as GeminiClient

from app.core.config import Settings, get_settings
from app.llm.planning import PLANNER_SYSTEM_PROMPT, PlannedWorkflow
from app.llm.provider import LLMChunk, LLMResponse, LLMUsage, ToolCall
from app.llm.registry import get_model_registry


def gemini_contents(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Replay original model parts, including signatures, and correlate tool results."""
    contents: list[dict[str, Any]] = []
    calls: dict[str, dict[str, Any]] = {}
    for message in messages:
        if message["role"] == "assistant":
            content = deepcopy(message["gemini_content"])
            native_calls = [
                part["functionCall"] for part in content["parts"] if "functionCall" in part
            ]
            ids = message["gemini_call_ids"]
            for call_id, call in zip(ids, native_calls, strict=True):
                calls[call_id] = call
            contents.append(content)
        elif message["role"] == "tool":
            call = calls[message["tool_call_id"]]
            try:
                result = json.loads(message["content"])
            except ValueError:
                result = message["content"]
            response = {
                "name": call["name"],
                "response": result if isinstance(result, dict) else {"result": result},
            }
            if call.get("id"):
                response["id"] = call["id"]
            part = {"functionResponse": response}
            if contents and contents[-1]["role"] == "user":
                contents[-1]["parts"].append(part)
            else:
                contents.append({"role": "user", "parts": [part]})
        else:
            contents.append({"role": "user", "parts": [{"text": message["content"]}]})
    return contents


def gemini_response(raw: dict[str, Any]) -> LLMResponse:
    """Normalize usage and stop metadata without accepting truncated tool calls."""
    usage = raw.get("usageMetadata")
    if not isinstance(usage, dict) or "promptTokenCount" not in usage:
        raise ValueError("Provider response has no token usage")
    candidates = raw.get("candidates", [])
    candidate = candidates[0] if candidates else {}
    content = candidate.get("content") or {"role": "model", "parts": []}
    parts = content.get("parts", [])
    reason = candidate.get("finishReason", "unknown")
    blocked = bool(raw.get("promptFeedback", {}).get("blockReason"))
    calls = [part["functionCall"] for part in parts if "functionCall" in part]
    ids = [call.get("id") or f"gemini_{uuid4().hex}" for call in calls]
    # Preserve all original parts even when no local call may be executed.
    return LLMResponse(
        content="".join(part.get("text", "") for part in parts if not part.get("thought")),
        usage=LLMUsage(
            input_tokens=usage["promptTokenCount"],
            output_tokens=usage.get("candidatesTokenCount", 0) + usage.get("thoughtsTokenCount", 0),
        ),
        stop_reason=("tool_calls" if calls else "stop") if reason == "STOP" else reason,
        refused=blocked
        or reason in {"SAFETY", "RECITATION", "BLOCKLIST", "PROHIBITED_CONTENT", "SPII"},
        tool_calls=[
            ToolCall(id=call_id, name=call["name"], arguments=call.get("args", {}))
            for call_id, call in zip(ids, calls, strict=True)
        ]
        if reason == "STOP" and not blocked
        else [],
        message={
            "role": "assistant",
            "gemini_content": deepcopy(content),
            "gemini_call_ids": ids,
        },
    )


class GeminiProvider:
    """Async native REST client with retries owned exclusively by llm/retry.py."""

    def __init__(self, api_key: str, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._client = GeminiClient(
            base_url=self.settings.gemini_api_url.rstrip("/") + "/",
            headers={"x-goog-api-key": api_key},
            timeout=self.settings.llm_request_timeout,
        )

    def _input(
        self, system_prompt: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "contents": gemini_contents(messages),
        }
        if tools:
            payload["tools"] = [
                {
                    "functionDeclarations": [
                        {
                            "name": tool["name"],
                            "description": tool["description"],
                            "parametersJsonSchema": tool["input_schema"],
                        }
                        for tool in tools
                    ]
                }
            ]
        return payload

    def _request(
        self,
        system_prompt: str,
        messages: list[dict[str, Any]],
        model: str,
        tools: list[dict[str, Any]],
        temperature: float,
        max_tokens: int,
    ) -> tuple[str, dict[str, Any]]:
        info = get_model_registry(self.settings)[model]
        if info.provider != "gemini":
            raise ValueError("Gemini requires a Gemini model")
        if not 1 <= max_tokens <= info.max_output_tokens:
            raise ValueError("Requested response exceeds the model output limit")
        payload = self._input(system_prompt, messages, tools)
        config: dict[str, Any] = {"temperature": temperature, "maxOutputTokens": max_tokens}
        if system_prompt == PLANNER_SYSTEM_PROMPT and not tools:
            config.update(
                responseMimeType="application/json",
                responseJsonSchema=PlannedWorkflow.model_json_schema(),
            )
        payload["generationConfig"] = config
        return info.model_id, payload

    async def count_input_tokens(
        self,
        system_prompt: str,
        messages: list[dict[str, Any]],
        model: str,
        tools: list[dict[str, Any]],
    ) -> int:
        info = get_model_registry(self.settings)[model]
        response = await self._client.post(
            f"models/{info.model_id}:countTokens",
            json={
                "generateContentRequest": {
                    "model": f"models/{info.model_id}",
                    **self._input(system_prompt, messages, tools),
                }
            },
        )
        response.raise_for_status()
        count = response.json().get("totalTokens")
        if type(count) is not int or count < 0:
            raise ValueError("Provider response has no valid input token count")
        return count

    async def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str,
        *,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        return await self.complete_tools(
            system_prompt,
            [{"role": "user", "content": user_prompt}],
            model,
            [],
            temperature=temperature,
            max_tokens=max_tokens,
        )

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
        model_id, payload = self._request(
            system_prompt, messages, model, tools, temperature, max_tokens
        )
        response = await self._client.post(f"models/{model_id}:generateContent", json=payload)
        response.raise_for_status()
        return gemini_response(response.json())

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
        model_id, payload = self._request(
            system_prompt, messages, model, tools, temperature, max_tokens
        )
        assembled: dict[str, Any] = {"candidates": [{"content": {"role": "model", "parts": []}}]}
        candidate = assembled["candidates"][0]
        async with self._client.stream(
            "POST", f"models/{model_id}:streamGenerateContent", params={"alt": "sse"}, json=payload
        ) as response:
            response.raise_for_status()
            async for raw in self._events(response):
                if "error" in raw:
                    code = raw["error"].get("code", 500)
                    raise httpx.HTTPStatusError(
                        "Gemini stream failed",
                        request=response.request,
                        response=httpx.Response(code, request=response.request),
                    )
                if "usageMetadata" in raw:
                    # Streaming usage is cumulative, not a delta to add for each chunk.
                    assembled.setdefault("usageMetadata", {}).update(raw["usageMetadata"])
                if "promptFeedback" in raw:
                    assembled["promptFeedback"] = raw["promptFeedback"]
                for incoming in raw.get("candidates", []):
                    if incoming.get("index", 0) != 0:
                        raise ValueError("Unexpected extra Gemini candidate")
                    if "finishReason" in incoming:
                        candidate["finishReason"] = incoming["finishReason"]
                    for part in incoming.get("content", {}).get("parts", []):
                        # Never merge signed parts or expose thought text in the console.
                        candidate["content"]["parts"].append(part)
                        if part.get("text") and not part.get("thought"):
                            yield LLMChunk(text_delta=part["text"])
        yield LLMChunk(response=gemini_response(assembled))

    async def _events(self, response: httpx.Response) -> AsyncGenerator[dict[str, Any]]:
        data: list[str] = []
        async for line in response.aiter_lines():
            if line.startswith("data:"):
                data.append(line[5:].lstrip(" "))
            elif not line and data:
                yield json.loads("\n".join(data))
                data.clear()
        if data:
            yield json.loads("\n".join(data))

    async def aclose(self) -> None:
        await self._client.aclose()
