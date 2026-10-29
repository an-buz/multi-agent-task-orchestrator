"""Console rendering, committed summaries, and job context isolation."""

import json
import os
import subprocess
import sys
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
import structlog
from app.db.run_repository import RunRepository
from app.workers import tasks
from app.workers.logging import log_run_event
from structlog.testing import capture_logs


@pytest.mark.parametrize(
    ("log_format", "colors", "tty", "no_color", "expect_json", "expect_color"),
    [
        ("auto", "auto", True, False, False, True),
        ("auto", "auto", False, False, True, False),
        ("console", "auto", True, True, False, False),
        ("console", "never", True, False, False, False),
        ("console", "always", False, False, False, True),
        ("json", "always", True, False, True, False),
    ],
)
def test_rendering_and_standard_library_logs(
    log_format, colors, tty, no_color, expect_json, expect_color
) -> None:
    # Isolate process-wide logging configuration from pytest's capture handlers.
    script = f"""
import logging, sys, structlog
from app.core.logging import configure_logging
sys.stderr.isatty = lambda: {tty!r}
configure_logging('WARNING', log_format={log_format!r}, log_colors={colors!r})
with structlog.contextvars.bound_contextvars(run_id='run-123'):
    structlog.get_logger('worker').info('hidden_info')
    structlog.get_logger('worker').warning('visible_warning', step_number=2)
    logging.getLogger('arq.worker').warning('queue_ready')
"""
    env = dict(os.environ)

    env.pop("NO_COLOR", None)

    if no_color:
        env["NO_COLOR"] = "1"

    result = subprocess.run(  # noqa: S603 - fixed interpreter and local test script
        [sys.executable, "-c", script], capture_output=True, text=True, env=env, check=True
    )

    assert not result.stdout
    assert "hidden_info" not in result.stderr
    assert ("\x1b[" in result.stderr) is expect_color

    lines = result.stderr.splitlines()

    assert len(lines) == 2

    if expect_json:
        first, second = map(json.loads, lines)

        assert first["event"] == "visible_warning"
        assert first["level"] == "warning"
        assert first["step_number"] == 2
        assert first["run_id"] == second["run_id"] == "run-123"
        assert second["logger"] == "arq.worker"
        assert "timestamp" in first
    else:
        assert "visible_warning" in lines[0] and "run-123" in lines[0]
        assert "queue_ready" in lines[1] and "arq.worker" in lines[1]


async def test_events_logged_only_after_commit_and_without_user_content() -> None:
    session = Mock(commit=AsyncMock(), rollback=AsyncMock())
    repository = RunRepository(session, event_observer=log_run_event)
    run_id, agent_id = uuid4(), uuid4()

    with capture_logs() as logs:
        repository.emit(
            run_id,
            "agent:completed",
            {
                "agentId": str(agent_id),
                "stepNumber": 1,
                "output": "PRIVATE OUTPUT",
                "tokensUsed": {"prompt": 8, "completion": 2, "total": 10},
                "executionTime": 1.25,
            },
        )

        assert logs == []

        await repository.save()
        await repository.save()

    assert len(logs) == 1
    assert logs[0]["run_id"] == str(run_id)
    assert logs[0]["agent_id"] == str(agent_id)
    assert logs[0]["tokens_used"]["total"] == 10
    assert "PRIVATE OUTPUT" not in str(logs)


async def test_rollback_and_failed_commit_do_not_log_events() -> None:
    session = Mock(commit=AsyncMock(), rollback=AsyncMock())
    observer = Mock()
    repository = RunRepository(session, event_observer=observer)
    run_id = uuid4()

    repository.emit(run_id, "task:cancelled", {"taskId": str(run_id)})

    await repository.release()
    await repository.save()

    observer.assert_not_called()
    repository.emit(run_id, "task:cancelled", {"taskId": str(run_id)})

    session.commit.side_effect = RuntimeError("database unavailable")

    with pytest.raises(RuntimeError):
        await repository.save()

    session.commit.side_effect = None

    await repository.save()

    observer.assert_not_called()


def test_stream_noise_and_sensitive_payloads_are_excluded() -> None:
    run_id = uuid4()

    with capture_logs() as logs:
        log_run_event(run_id, "agent:stream_chunk", {"textDelta": "PRIVATE DELTA"})
        log_run_event(run_id, "agent:stream_chunk", {"reset": True, "attempt": 2})
        log_run_event(
            run_id,
            "agent:tool_result",
            {"toolName": "calculator", "ok": False, "summary": "PRIVATE TOOL RESULT"},
        )
        log_run_event(
            run_id, "agent:failed", {"error": {"code": "llm_error", "message": "PRIVATE ERROR"}}
        )

    assert [item["event"] for item in logs] == [
        "llm_request_started",
        "agent:tool_result",
        "agent:failed",
    ]
    assert [item["log_level"] for item in logs] == ["info", "warning", "error"]
    assert "PRIVATE" not in str(logs)


async def test_job_failure_keeps_identity_without_leaking_context(monkeypatch) -> None:
    monkeypatch.setattr(tasks, "_run_job", AsyncMock(side_effect=RuntimeError("PRIVATE ERROR")))

    before = structlog.contextvars.get_contextvars()

    with (
        capture_logs(processors=[structlog.contextvars.merge_contextvars]) as logs,
        pytest.raises(RuntimeError),
    ):
        await tasks.plan_run({"job_id": "job-123"}, "run-123")

    assert [item["event"] for item in logs] == ["run_job_started", "run_job_failed"]

    for item in logs:
        assert item["run_id"] == "run-123"
        assert item["job_id"] == "job-123"
        assert item["phase"] == "planning"

    assert "PRIVATE" not in str(logs)
    assert structlog.contextvars.get_contextvars() == before
