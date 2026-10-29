"""Persistence operations shared by the run service and worker."""

import builtins
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import Agent
from app.models.run import Run
from app.models.run_decision import RunDecision
from app.models.run_event import RunEvent
from app.models.run_step import RunStep
from app.models.workflow import Workflow
from app.schemas.event import EventEnvelope, EventName
from app.schemas.run import RunSummary


class RunRepository:
    def __init__(
        self,
        session: AsyncSession,
        ownership_check: Callable[[], None] | None = None,
        event_observer: Callable[[UUID, EventName, dict[str, Any]], None] | None = None,
    ) -> None:
        self.session = session
        self.ownership_check = ownership_check
        self.event_observer = event_observer
        self._pending_logs: list[tuple[UUID, EventName, dict[str, Any]]] = []

    async def get(self, run_id: UUID, *, lock: bool = False) -> Run | None:
        if lock:
            return await self.session.scalar(
                select(Run)
                .where(Run.id == run_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        return await self.session.get(Run, run_id)

    async def workflow(self, workflow_id: UUID, *, lock: bool = False) -> Workflow | None:
        if lock:
            return await self.session.scalar(
                select(Workflow)
                .where(Workflow.id == workflow_id)
                .with_for_update(read=True)
                .execution_options(populate_existing=True)
            )
        return await self.session.get(Workflow, workflow_id)

    async def agents(self, agent_ids: set[UUID]) -> dict[UUID, Agent]:
        values = await self.session.scalars(
            select(Agent)
            .where(Agent.id.in_(agent_ids))
            .order_by(Agent.id)
            .with_for_update(read=True)
            .execution_options(populate_existing=True)
        )
        return {agent.id: agent for agent in values}

    async def steps(self, run_id: UUID) -> list[RunStep]:
        return list(
            await self.session.scalars(
                select(RunStep).where(RunStep.run_id == run_id).order_by(RunStep.step_number)
            )
        )

    async def reconfiguration_flags(self, run_id: UUID) -> dict[int, bool]:
        rows = await self.session.execute(
            select(RunStep.step_number, RunStep.requires_reconfiguration).where(
                RunStep.run_id == run_id
            )
        )
        return {number: required for number, required in rows}

    async def decisions(self, run_id: UUID) -> list[RunDecision]:
        return list(
            await self.session.scalars(
                select(RunDecision)
                .where(RunDecision.run_id == run_id)
                .order_by(RunDecision.created_at, RunDecision.id)
            )
        )

    async def list(self, limit: int, offset: int) -> tuple[list[Run], int]:
        total = await self.session.scalar(select(func.count()).select_from(Run))
        values = await self.session.scalars(
            select(Run).order_by(Run.created_at.desc(), Run.id).limit(limit).offset(offset)
        )
        return list(values), total or 0

    async def summaries(self, limit: int, offset: int) -> tuple[builtins.list[RunSummary], int]:
        total = await self.session.scalar(select(func.count()).select_from(Run))
        rows = await self.session.execute(
            select(
                Run.id,
                Run.workflow_id,
                Workflow.title.label("workflow_title"),
                Run.task,
                Run.status,
                Run.total_tokens,
                Run.total_time_ms,
                Run.created_at,
                Run.started_at,
                Run.finished_at,
            )
            .join(Workflow, Run.workflow_id == Workflow.id)
            .order_by(Run.created_at.desc(), Run.id)
            .limit(limit)
            .offset(offset)
        )
        return [RunSummary.model_validate(row) for row in rows.mappings()], total or 0

    def add(self, value: Run | RunStep | RunDecision) -> None:
        self.session.add(value)

    async def save(self) -> None:
        if self.ownership_check is not None:
            self.ownership_check()
        try:
            await self.session.commit()
        except BaseException:
            self._pending_logs.clear()
            raise
        pending, self._pending_logs = self._pending_logs, []
        if self.event_observer is not None:
            for run_id, event, data in pending:
                self.event_observer(run_id, event, data)

    async def delete(self, run: Run) -> None:
        await self.session.delete(run)
        await self.session.commit()

    async def refresh(self, run: Run) -> None:
        await self.session.refresh(run)

    def emit(self, run_id: UUID, event: EventName, data: dict[str, Any]) -> None:
        payload = EventEnvelope(event=event, runId=run_id, ts=datetime.now(UTC), data=data)
        self.session.add(RunEvent(run_id=run_id, event=event, data=payload.data))
        if self.event_observer is not None:
            self._pending_logs.append((run_id, event, payload.data))

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
        self._pending_logs.clear()
        await self.session.rollback()
