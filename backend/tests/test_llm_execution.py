"""Transient failures use one retry policy with bounded attempts."""

from unittest.mock import AsyncMock

import pytest
from app.llm.retry import llm_retrying
from tenacity import wait_none


class HTTPFailure(Exception):
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


@pytest.mark.parametrize("exception", [HTTPFailure(429), HTTPFailure(503), TimeoutError()])
async def test_transient_failures_retry_three_times(exception: Exception) -> None:
    call = AsyncMock(side_effect=[exception, exception, "success"])
    retry = llm_retrying()
    retry.wait = wait_none()

    async for attempt in retry:
        with attempt:
            result = await call()

    assert result == "success"
    assert call.await_count == 3


async def test_retry_exhaustion_and_non_retryable_failure() -> None:
    for failure, expected in [(HTTPFailure(429), 3), (HTTPFailure(401), 1)]:
        call = AsyncMock(side_effect=failure)
        retry = llm_retrying()
        retry.wait = wait_none()

        with pytest.raises(HTTPFailure):
            async for attempt in retry:
                with attempt:
                    await call()

        assert call.await_count == expected
