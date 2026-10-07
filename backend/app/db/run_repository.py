"""Persistence operations shared by the run service and worker."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import Agent
from app.models.run import Run
from app.models.run_step import RunStep
from app.models.workflow import Workflow


class RunRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, run_id: UUID, *, lock: bool = False) -> Run | None:
        if lock:
            return await self.session.scalar(select(Run).where(Run.id == run_id).with_for_update())
        return await self.session.get(Run, run_id)

    async def workflow(self, workflow_id: UUID) -> Workflow | None:
        return await self.session.get(Workflow, workflow_id)

    async def agents(self, agent_ids: set[UUID]) -> dict[UUID, Agent]:
        values = await self.session.scalars(select(Agent).where(Agent.id.in_(agent_ids)))
        return {agent.id: agent for agent in values}

    async def steps(self, run_id: UUID) -> list[RunStep]:
        return list(
            await self.session.scalars(
                select(RunStep).where(RunStep.run_id == run_id).order_by(RunStep.step_number)
            )
        )

    async def list(self, limit: int, offset: int) -> tuple[list[Run], int]:
        total = await self.session.scalar(select(func.count()).select_from(Run))
        values = await self.session.scalars(
            select(Run).order_by(Run.created_at.desc(), Run.id).limit(limit).offset(offset)
        )
        return list(values), total or 0

    def add(self, value: Run | RunStep) -> None:
        self.session.add(value)

    async def save(self) -> None:
        await self.session.commit()

    async def refresh(self, run: Run) -> None:
        await self.session.refresh(run)
