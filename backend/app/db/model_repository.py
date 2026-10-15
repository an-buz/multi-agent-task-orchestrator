"""Model policy persistence shared by settings, agent validation and scheduling."""

from sqlalchemy import select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import Agent
from app.models.model_setting import ModelSetting
from app.models.run_step import RunStep


class ModelRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def disabled(self) -> set[str]:
        await self.session.execute(text("SELECT pg_advisory_xact_lock_shared(744029831)"))
        return set(
            await self.session.scalars(select(ModelSetting.key).where(~ModelSetting.enabled))
        )

    async def set_enabled(self, key: str, enabled: bool) -> None:
        await self.session.execute(text("SELECT pg_advisory_xact_lock(744029831)"))
        statement = insert(ModelSetting).values(key=key, enabled=enabled)
        await self.session.execute(
            statement.on_conflict_do_update(
                index_elements=[ModelSetting.key], set_={"enabled": enabled}
            )
        )
        if not enabled:
            await self.session.execute(
                update(Agent).where(Agent.model == key).values(requires_reconfiguration=True)
            )
            await self.session.execute(
                update(RunStep)
                .where(
                    RunStep.agent_config["model"].astext == key,
                    RunStep.status.in_(["PENDING", "IN_PROGRESS", "FAILED"]),
                )
                .values(requires_reconfiguration=True)
            )
        await self.session.commit()
