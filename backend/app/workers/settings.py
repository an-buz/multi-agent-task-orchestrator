"""ARQ worker configuration."""

from typing import Any

import structlog
from arq.connections import RedisSettings
from arq.cron import cron

from app.core.config import get_settings
from app.workers.tasks import cleanup_resources, execute_run, plan_run, recover_runs


async def startup(ctx: dict[str, Any]) -> None:
    del ctx
    structlog.get_logger(__name__).info("worker_ready")


async def shutdown(ctx: dict[str, Any]) -> None:
    del ctx
    structlog.get_logger(__name__).info("worker_stopped", reason="shutdown")


class WorkerSettings:
    """Execution jobs and recovery of durably confirmed runs."""

    redis_settings = RedisSettings.from_dsn(str(get_settings().redis_url))
    functions = [plan_run, execute_run]
    cron_jobs = [
        cron(recover_runs, second=0, run_at_startup=True),
        cron(cleanup_resources, minute=set(range(0, 60, 5)), second=15, run_at_startup=True),
    ]
    job_timeout = get_settings().worker_job_timeout
    keep_result = 0
    on_startup = startup
    on_shutdown = shutdown
