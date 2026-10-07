"""Best-effort dispatch; the worker also recovers confirmed runs from PostgreSQL."""

from uuid import UUID

import structlog
from arq.connections import RedisSettings, create_pool

from app.core.config import get_settings

logger = structlog.get_logger()


async def enqueue_run(run_id: UUID) -> None:
    try:
        redis = await create_pool(RedisSettings.from_dsn(str(get_settings().redis_url)))
        try:
            await redis.enqueue_job("execute_run", str(run_id), _job_id=f"run:{run_id}")
        finally:
            await redis.aclose()
    except Exception as exception:
        logger.warning(
            "run_dispatch_deferred", run_id=str(run_id), error_type=type(exception).__name__
        )
