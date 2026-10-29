"""Authenticated model discovery with isolated, bounded per-provider caches."""

import asyncio
import hashlib
import re
from dataclasses import dataclass
from time import monotonic
from typing import Any, Literal
from weakref import WeakKeyDictionary

import httpx
import structlog
from httpx import AsyncClient as DiscoveryClient

from app.core.config import Settings, get_settings
from app.llm.registry import ModelInfo, get_model_registry

type Provider = Literal["anthropic", "openai", "gemini"]

logger = structlog.get_logger()


@dataclass
class CatalogueEntry:
    models: dict[str, ModelInfo]
    expires_at: float
    error: str | None = None


_cache: dict[tuple[Provider, str], CatalogueEntry] = {}
_locks: WeakKeyDictionary[asyncio.AbstractEventLoop, dict[tuple[Provider, str], asyncio.Lock]] = (
    WeakKeyDictionary()
)


def credentials(settings: Settings) -> list[tuple[Provider, str, str]]:
    candidates: list[tuple[Provider, str | None, str]] = [
        ("anthropic", settings.anthropic_api_key, settings.anthropic_api_url),
        ("openai", settings.openai_api_key, settings.openai_api_url),
        ("gemini", settings.gemini_api_key, settings.gemini_api_url),
    ]

    return [(provider, key, url) for provider, key, url in candidates if key]


def cache_key(provider: Provider, key: str, url: str) -> tuple[Provider, str]:
    digest = hashlib.sha256(f"{url}\0{key}".encode()).hexdigest()

    return provider, digest


def cached_models(settings: Settings) -> dict[str, ModelInfo]:
    return {
        key: info
        for provider, token, url in credentials(settings)
        if (entry := _cache.get(cache_key(provider, token, url))) is not None
        for key, info in entry.models.items()
    }


def discovery_errors(settings: Settings) -> dict[str, str]:
    return {
        provider: entry.error
        for provider, token, url in credentials(settings)
        if (entry := _cache.get(cache_key(provider, token, url))) is not None
        and entry.error is not None
    }


def positive_limit(value: object) -> int | None:
    return value if type(value) is int and value > 0 else None


def normalize_model(provider: Provider, raw: dict[str, Any]) -> ModelInfo | None:
    model_id = (
        raw.get("name", "").removeprefix("models/") if provider == "gemini" else raw.get("id")
    )

    if not isinstance(model_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]*", model_id):
        return None

    if provider == "gemini":
        if "generateContent" not in raw.get("supportedGenerationMethods", []):
            return None

        if any(part in model_id for part in ("image", "tts", "robotics", "computer-use")):
            return None

        window = positive_limit(raw.get("inputTokenLimit"))
        output = positive_limit(raw.get("outputTokenLimit"))
    else:
        if provider == "openai":
            # The list endpoint includes embeddings, media and Responses-only models.
            if not re.match(r"^(gpt-|chatgpt-|o[1-9])", model_id):
                return None

            if any(
                part in model_id
                for part in (
                    "audio",
                    "realtime",
                    "transcribe",
                    "tts",
                    "image",
                    "search",
                    "deep-research",
                    "-pro",
                    "codex",
                )
            ):
                return None

        window = positive_limit(raw.get("max_input_tokens"))
        output = positive_limit(raw.get("max_tokens"))

    # Discovery has no universal performance ranking; balanced is a neutral group.
    return ModelInfo(model_id, provider, model_id, "balanced", window, output)


async def fetch_models(
    provider: Provider, token: str, url: str, settings: Settings
) -> dict[str, ModelInfo]:
    headers = {
        "anthropic": {"x-api-key": token, "anthropic-version": "2023-06-01"},
        "openai": {"Authorization": f"Bearer {token}"},
        "gemini": {"x-goog-api-key": token},
    }[provider]
    params: dict[str, str] = {}
    models: dict[str, ModelInfo] = {}
    cursors: set[str] = set()

    async with (
        asyncio.timeout(settings.model_discovery_timeout),
        DiscoveryClient(
            base_url=url.rstrip("/") + "/",
            headers=headers,
            timeout=settings.model_discovery_timeout,
        ) as client,
    ):
        for _ in range(settings.model_discovery_max_pages):
            response = await client.get("models", params=params)
            response.raise_for_status()

            payload = response.json()
            rows = payload.get("models" if provider == "gemini" else "data")

            if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
                raise ValueError("Invalid provider catalogue")

            for row in rows:
                info = normalize_model(provider, row)

                if info is not None:
                    models[info.key] = info

            cursor = (
                payload.get("nextPageToken")
                if provider == "gemini"
                else payload.get("last_id")
                if payload.get("has_more")
                else None
            )

            if provider != "gemini" and payload.get("has_more") and not cursor:
                raise ValueError("Missing provider catalogue cursor")

            if not cursor:
                return dict(sorted(models.items()))

            if not isinstance(cursor, str) or cursor in cursors:
                raise ValueError("Invalid provider catalogue cursor")

            cursors.add(cursor)
            params = {"pageToken" if provider == "gemini" else "after_id": cursor}

    raise ValueError("Provider catalogue pagination limit exceeded")


async def refresh_provider(provider: Provider, token: str, url: str, settings: Settings) -> None:
    key = cache_key(provider, token, url)
    locks = _locks.setdefault(asyncio.get_running_loop(), {})

    async with locks.setdefault(key, asyncio.Lock()):
        entry = _cache.get(key)

        if entry is not None and entry.expires_at > monotonic():
            return

        try:
            models = await fetch_models(provider, token, url, settings)
        except (httpx.HTTPError, TimeoutError, ValueError, TypeError, AttributeError) as exception:
            # Never propagate provider bodies, request URLs or credentials to clients/logs.
            status = (
                exception.response.status_code
                if isinstance(exception, httpx.HTTPStatusError)
                else None
            )
            message = (
                "Authentication failed. Check the provider API key."
                if status in {401, 403}
                else "Could not fetch provider models. Discovery will retry automatically."
            )
            _cache[key] = CatalogueEntry(
                {}, monotonic() + settings.model_discovery_error_cache_seconds, message
            )
            logger.warning("model_discovery_failed", provider=provider, status_code=status)
        else:
            _cache[key] = CatalogueEntry(
                models, monotonic() + settings.model_discovery_cache_seconds
            )


async def refresh_model_registry(settings: Settings | None = None) -> dict[str, ModelInfo]:
    active = settings or get_settings()

    if active.llm_provider_mode == "real":
        await asyncio.gather(
            *(
                refresh_provider(provider, token, url, active)
                for provider, token, url in credentials(active)
            )
        )

    return get_model_registry(active)
