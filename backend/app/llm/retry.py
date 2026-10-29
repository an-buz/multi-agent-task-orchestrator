"""Shared retry policy for transient LLM failures."""

import httpx
from anthropic import APIConnectionError as AnthropicConnectionError
from openai import APIConnectionError as OpenAIConnectionError
from tenacity import AsyncRetrying, retry_if_exception, stop_after_attempt, wait_exponential_jitter


def _is_retryable_llm_error(exception: BaseException) -> bool:
    """Recognize transient network errors and provider HTTP 429/5xx responses."""

    if isinstance(
        exception,
        (
            TimeoutError,
            ConnectionError,
            httpx.TransportError,
            AnthropicConnectionError,
            OpenAIConnectionError,
        ),
    ):
        return True

    status_code = getattr(exception, "status_code", None)

    if isinstance(exception, httpx.HTTPStatusError):
        status_code = exception.response.status_code

    return status_code == 429 or (isinstance(status_code, int) and 500 <= status_code <= 599)


def llm_retrying() -> AsyncRetrying:
    """Build the common three-attempt exponential retry policy."""

    return AsyncRetrying(
        stop=stop_after_attempt(3),
        wait=wait_exponential_jitter(initial=1, max=4),
        retry=retry_if_exception(_is_retryable_llm_error),
        reraise=True,
    )
