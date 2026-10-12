"""Retention rules preserve runs, results and all attached files."""

from datetime import UTC, datetime, timedelta

from app.core.config import get_settings
from app.db.cleanup_repository import CleanupRepository


class CleanupService:
    def __init__(self, repository: CleanupRepository) -> None:
        self.repository = repository

    async def execute(self, now: datetime | None = None) -> dict[str, int]:
        settings = get_settings()
        moment = now or datetime.now(UTC)
        return {
            "files": await self.repository.files(
                moment - timedelta(days=settings.unused_file_retention_days),
                settings.cleanup_batch_size,
            ),
            "events": await self.repository.events(
                moment - timedelta(days=settings.terminal_event_retention_days),
                settings.cleanup_batch_size,
            ),
        }
