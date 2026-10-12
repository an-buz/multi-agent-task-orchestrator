"""Bounded cleanup under the same locks used by run/file mutation."""

from datetime import datetime

from sqlalchemy import delete, exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.context_file import ContextFile, RunFile
from app.models.run import Run
from app.models.run_event import RunEvent


class CleanupRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def files(self, cutoff: datetime, batch_size: int) -> int:
        candidates = list(
            await self.session.scalars(
                select(ContextFile.id)
                .where(
                    ContextFile.created_at < cutoff,
                    ~exists().where(RunFile.file_id == ContextFile.id),
                )
                .order_by(ContextFile.created_at, ContextFile.id)
                .limit(batch_size)
                .with_for_update(skip_locked=True)
            )
        )
        # Recheck references after acquiring locks, using a fresh statement snapshot.
        removed = list(
            await self.session.scalars(
                delete(ContextFile)
                .where(
                    ContextFile.id.in_(candidates),
                    ~exists().where(RunFile.file_id == ContextFile.id),
                )
                .returning(ContextFile.id)
            )
        )
        await self.session.commit()
        return len(removed)

    async def events(self, cutoff: datetime, batch_size: int) -> int:
        runs = list(
            await self.session.scalars(
                select(Run.id)
                .where(
                    Run.status.in_(["COMPLETED", "FAILED", "CANCELLED"]),
                    Run.finished_at < cutoff,
                    exists().where(RunEvent.run_id == Run.id, RunEvent.created_at < cutoff),
                )
                .order_by(Run.finished_at, Run.id)
                .limit(batch_size)
                .with_for_update(skip_locked=True)
            )
        )
        # One bounded batch of events, not an unbounded DELETE of a large run history.
        ids = (
            select(RunEvent.id)
            .where(RunEvent.run_id.in_(runs), RunEvent.created_at < cutoff)
            .order_by(RunEvent.id)
            .limit(batch_size)
        )
        removed = list(
            await self.session.scalars(
                delete(RunEvent).where(RunEvent.id.in_(ids)).returning(RunEvent.id)
            )
        )
        await self.session.commit()
        return len(removed)
