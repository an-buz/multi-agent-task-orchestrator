import asyncio
from unittest.mock import AsyncMock, Mock

import pytest
from app.workers import runner
from structlog.testing import capture_logs


def test_keyboard_interrupt_exits_without_traceback(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    async def interrupted_main() -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(runner, "main", interrupted_main)

    with capture_logs() as logs:
        runner.run()

    output = capsys.readouterr()
    assert logs == [
        {"event": "worker_stopped", "reason": "keyboard_interrupt", "log_level": "info"}
    ]
    assert "Traceback" not in output.out + output.err


def test_unexpected_errors_are_not_suppressed(monkeypatch: pytest.MonkeyPatch) -> None:
    async def failing_main() -> None:
        raise RuntimeError("worker failure")

    monkeypatch.setattr(runner, "main", failing_main)

    with pytest.raises(RuntimeError, match="worker failure"):
        runner.run()


async def test_cancelled_worker_still_closes_resources(monkeypatch: pytest.MonkeyPatch) -> None:
    worker = Mock()
    worker.async_run = AsyncMock(side_effect=asyncio.CancelledError)
    worker.close = AsyncMock()
    monkeypatch.setattr(runner, "OrchestratorWorker", Mock(return_value=worker))

    with pytest.raises(asyncio.CancelledError):
        await runner.main()

    worker.close.assert_awaited_once()
