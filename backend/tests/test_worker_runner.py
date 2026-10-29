import asyncio
from unittest.mock import AsyncMock, Mock

import pytest
from app.core.config import Settings
from app.workers import runner
from arq.connections import RedisSettings
from structlog.testing import capture_logs


def test_default_redis_matches_ipv4_compose_binding(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("REDIS_URL", raising=False)
    configured = RedisSettings.from_dsn(str(Settings(_env_file=None).redis_url))
    assert (configured.host, configured.port, configured.database) == ("127.0.0.1", 16379, 0)
    monkeypatch.setenv("REDIS_URL", "redis://redis.internal:6379/2")
    configured = RedisSettings.from_dsn(str(Settings(_env_file=None).redis_url))
    assert (configured.host, configured.port, configured.database) == ("redis.internal", 6379, 2)


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
    configure = Mock()
    monkeypatch.setattr(runner, "configure_logging", configure)

    with pytest.raises(asyncio.CancelledError):
        await runner.main()

    worker.close.assert_awaited_once()
    configure.assert_called_once()
    options = runner.OrchestratorWorker.call_args.kwargs
    assert options["on_startup"] is runner.WorkerSettings.on_startup
    assert options["on_shutdown"] is runner.WorkerSettings.on_shutdown
