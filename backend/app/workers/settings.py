"""ARQ worker configuration."""

from arq.connections import RedisSettings

from app.core.config import get_settings


class WorkerSettings:
    """Minimal worker configuration; task functions are added with orchestration work."""

    redis_settings = RedisSettings.from_dsn(str(get_settings().redis_url))
    functions: list[object] = []
