"""Persistence operations shared by the run service and worker."""

import builtins
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import Agent
from app.models.run import Run
from app.models.run_event import RunEvent
from app.models.run_step import RunStep
from app.models.workflow import Workflow
from app.schemas.event import EventEnvelope, EventName


class RunRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, run_id: UUID, *, lock: bool = False) -> Run | None:
        if lock:
            return await self.session.scalar(
                select(Run)
                .where(Run.id == run_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
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

    async def delete(self, run: Run) -> None:
        await self.session.delete(run)
        await self.session.commit()

    async def refresh(self, run: Run) -> None:
        await self.session.refresh(run)

    def emit(self, run_id: UUID, event: EventName, data: dict[str, Any]) -> None:
        payload = EventEnvelope(event=event, runId=run_id, ts=datetime.now(UTC), data=data)
        self.session.add(RunEvent(run_id=run_id, event=event, data=payload.data))

    async def events(self, run_id: UUID, after: int) -> builtins.list[RunEvent]:
        return list(
            await self.session.scalars(
                select(RunEvent)
                .where(RunEvent.run_id == run_id, RunEvent.id > after)
                .order_by(RunEvent.id)
                .limit(100)
            )
        )

    async def event_cursor(self, run_id: UUID) -> int:
        return (
            await self.session.scalar(
                select(func.max(RunEvent.id)).where(RunEvent.run_id == run_id)
            )
            or 0
        )

    async def release(self) -> None:
        await self.session.rollback()
