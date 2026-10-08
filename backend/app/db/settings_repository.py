"""Atomic persistence of the shared agent defaults."""

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.app_config import AppConfig


class SettingsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def read(self) -> dict[str, object] | None:
        config = await self.session.get(AppConfig, 1)
        return config.defaults if config else None

    async def save(self, defaults: dict[str, object]) -> None:
        statement = insert(AppConfig).values(id=1, defaults=defaults)
        await self.session.execute(
            statement.on_conflict_do_update(
                index_elements=[AppConfig.id], set_={"defaults": defaults}
            )
        )
        await self.session.commit()
