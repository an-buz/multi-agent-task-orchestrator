"""Safe console summaries of committed worker events."""

from typing import Any
from uuid import UUID

import structlog

from app.schemas.event import EventName

logger = structlog.get_logger(__name__)


def log_run_event(run_id: UUID, event: EventName, data: dict[str, Any]) -> None:
    """Allowlist operational metadata; never log user text or tool payloads."""
    if event == "agent:stream_chunk" and not data.get("reset"):
        return
    fields = {
        target: data[source]
        for source, target in (
            ("agentId", "agent_id"),
            ("stepNumber", "step_number"),
            ("status", "status"),
            ("attempt", "attempt"),
            ("toolName", "tool_name"),
            ("ok", "ok"),
            ("executionTime", "execution_time_seconds"),
            ("tokensUsed", "tokens_used"),
            ("totalTokens", "total_tokens"),
            ("totalTimeMs", "total_time_ms"),
            ("failedSteps", "failed_steps"),
        )
        if source in data
    }
    if event == "agent:failed":
        fields["error_code"] = data["error"]["code"]
    if event == "plan:ready":
        fields["step_count"] = len(data["plan"]["steps"])
    level = "error" if event in {"agent:failed", "task:failed"} else "info"
    if event == "task:paused" or data.get("ok") is False:
        level = "warning"
    logger.log(
        {"info": 20, "warning": 30, "error": 40}[level],
        "llm_request_started" if event == "agent:stream_chunk" else event,
        run_id=str(run_id),
        **fields,
    )
