"""Persistence operations for the agent catalogue."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import Agent


class AgentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, agent_id: UUID) -> Agent | None:
        return await self.session.get(Agent, agent_id)

    async def list(self, limit: int, offset: int) -> tuple[list[Agent], int]:
        total = await self.session.scalar(select(func.count()).select_from(Agent))
        agents = await self.session.scalars(
            select(Agent)
            .order_by(Agent.created_at.desc(), Agent.name, Agent.id)
            .limit(limit)
            .offset(offset)
        )
        return list(agents), total or 0

    async def save(self, agent: Agent) -> None:
        self.session.add(agent)
        await self.session.commit()
        await self.session.refresh(agent)

    async def rollback(self) -> None:
        await self.session.rollback()

    async def delete(self, agent: Agent) -> None:
        await self.session.delete(agent)
        await self.session.commit()
