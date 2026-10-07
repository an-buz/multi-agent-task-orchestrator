"""Durable replay followed by live polling, without holding database connections."""

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.db.run_repository import RunRepository
from app.schemas.event import EventEnvelope, EventName
from app.services.runs import RunService


async def stream_run(
    sessions: async_sessionmaker[AsyncSession],
    run_id: UUID,
    after: int | None,
) -> AsyncIterator[dict[str, str]]:
    async with sessions() as session:
        repository = RunRepository(session)
        service = RunService(repository)
        run = await service.require(run_id, lock=True)
        snapshot = await service.read(run)
        watermark = await repository.event_cursor(run_id)
        await repository.release()
    cursor = watermark if after is None else after
    initial = {
        "event": "run:snapshot",
        "data": EventEnvelope(
            event="run:snapshot",
            runId=run_id,
            ts=datetime.now(UTC),
            data={"run": snapshot.model_dump(mode="json")},
        ).model_dump_json(),
    }
    if after is None:
        initial["id"] = str(watermark)
    yield initial
    while True:
        async with sessions() as session:
            events = await RunRepository(session).events(run_id, cursor)
        for event in events:
            cursor = event.id
            yield {
                "id": str(event.id),
                "event": event.event,
                "data": EventEnvelope(
                    event=cast(EventName, event.event),
                    runId=run_id,
                    ts=event.created_at,
                    data=event.data,
                ).model_dump_json(),
            }
        if len(events) < 100:
            await asyncio.sleep(get_settings().run_poll_interval)
