"""Persistence for context files and run attachment references."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import load_only

from app.models.context_file import ContextFile, RunFile


class FileRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def attach(self, run_id: UUID, file_ids: list[UUID]) -> None:
        if not file_ids:
            return
        # Flush the new run before references; all rows still commit atomically.
        await self.session.flush()
        self.session.add_all(RunFile(run_id=run_id, file_id=file_id) for file_id in file_ids)

    async def get(self, file_id: UUID, *, lock: bool = False) -> ContextFile | None:
        query = select(ContextFile).where(ContextFile.id == file_id)
        if lock:
            query = query.with_for_update()
        return await self.session.scalar(query)

    async def for_run(self, run_id: UUID) -> list[ContextFile]:
        result = await self.session.scalars(
            select(ContextFile)
            .options(
                load_only(
                    ContextFile.id,
                    ContextFile.filename,
                    ContextFile.media_type,
                    ContextFile.size_bytes,
                    ContextFile.created_at,
                )
            )
            .join(RunFile, RunFile.file_id == ContextFile.id)
            .where(RunFile.run_id == run_id)
            .order_by(ContextFile.created_at, ContextFile.id)
        )
        return list(result)

    async def text_for_run(self, run_id: UUID) -> dict[str, str]:
        rows = await self.session.execute(
            select(ContextFile.id, ContextFile.text_content)
            .join(RunFile, RunFile.file_id == ContextFile.id)
            .where(RunFile.run_id == run_id)
        )
        return {str(file_id): text for file_id, text in rows}

    async def is_attached(self, file_id: UUID) -> bool:
        return (
            await self.session.scalar(
                select(RunFile.file_id).where(RunFile.file_id == file_id).limit(1)
            )
            is not None
        )

    async def save(self, file: ContextFile) -> None:
        self.session.add(file)
        await self.session.commit()
        await self.session.refresh(file)

    async def delete(self, file: ContextFile) -> None:
        await self.session.delete(file)
        await self.session.commit()
