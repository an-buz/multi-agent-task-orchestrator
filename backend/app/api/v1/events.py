"""Server-Sent Events API routes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header
from sse_starlette.sse import EventSourceResponse

from app.api.v1.runs import Service
from app.db.session import async_session_factory
from app.events.stream import stream_run

router = APIRouter()


@router.get("/{run_id}/events")
async def run_events(
    run_id: UUID,
    service: Service,
    last_event_id: Annotated[int | None, Header(ge=0, le=9223372036854775807)] = None,
) -> EventSourceResponse:
    await service.require(run_id)
    await service.repository.release()
    return EventSourceResponse(
        stream_run(async_session_factory, run_id, last_event_id),
        ping=15,
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
