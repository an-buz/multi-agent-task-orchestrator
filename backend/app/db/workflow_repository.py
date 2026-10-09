"""Persistence operations for workflow deletion."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.run import Run
from app.models.workflow import Workflow


class WorkflowRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_for_deletion(self, workflow_id: UUID) -> Workflow | None:
        return await self.session.scalar(
            select(Workflow).where(Workflow.id == workflow_id).with_for_update()
        )

    async def has_runs(self, workflow_id: UUID) -> bool:
        return (
            await self.session.scalar(select(Run.id).where(Run.workflow_id == workflow_id).limit(1))
            is not None
        )

    async def delete(self, workflow: Workflow) -> None:
        await self.session.delete(workflow)
        await self.session.commit()
