"""Persistence operations for the workflow catalogue."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import Agent
from app.models.run import Run
from app.models.workflow import Workflow


class WorkflowRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_for_deletion(self, workflow_id: UUID) -> Workflow | None:
        return await self.session.scalar(
            select(Workflow)
            .where(Workflow.id == workflow_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    async def get(self, workflow_id: UUID) -> Workflow | None:
        return await self.session.get(Workflow, workflow_id)

    async def list(self, limit: int, offset: int) -> tuple[list[Workflow], int]:
        total = await self.session.scalar(select(func.count()).select_from(Workflow))
        values = await self.session.scalars(
            select(Workflow)
            .order_by(Workflow.updated_at.desc(), Workflow.id)
            .limit(limit)
            .offset(offset)
        )

        return list(values), total or 0

    async def agent_ids(self, agent_ids: set[UUID]) -> set[UUID]:
        return set(
            await self.session.scalars(
                select(Agent.id)
                .where(Agent.id.in_(agent_ids))
                .order_by(Agent.id)
                .with_for_update(read=True)
            )
        )

    async def save(self, workflow: Workflow) -> None:
        self.session.add(workflow)

        await self.session.commit()
        await self.session.refresh(workflow)

    async def has_runs(self, workflow_id: UUID) -> bool:
        return (
            await self.session.scalar(select(Run.id).where(Run.workflow_id == workflow_id).limit(1))
            is not None
        )

    async def delete(self, workflow: Workflow) -> None:
        await self.session.delete(workflow)
        await self.session.commit()
