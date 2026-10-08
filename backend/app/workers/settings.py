"""ARQ worker configuration."""

from arq.connections import RedisSettings
from arq.cron import cron

from app.core.config import get_settings
from app.workers.tasks import execute_run, plan_run, recover_runs


class WorkerSettings:
    """Execution jobs and recovery of durably confirmed runs."""

    redis_settings = RedisSettings.from_dsn(str(get_settings().redis_url))
    functions = [plan_run, execute_run]
    cron_jobs = [cron(recover_runs, second=0, run_at_startup=True)]
    job_timeout = get_settings().worker_job_timeout
    keep_result = 0
