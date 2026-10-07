"""Environment-backed application settings."""

from functools import lru_cache
from typing import Literal

from pydantic import AnyHttpUrl, Field, PostgresDsn, RedisDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"
    database_url: PostgresDsn = PostgresDsn(
        "postgresql+asyncpg://app:app@localhost:5432/orchestrator"
    )
    redis_url: RedisDsn = RedisDsn("redis://localhost:6379/0")
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    # Provider model identifiers stay configurable as providers retire model versions.
    anthropic_model_haiku: str = Field(
        default="claude-3-5-haiku-latest", validation_alias="ANTHROPIC_MODEL_HAIKU"
    )
    anthropic_model_sonnet: str = Field(
        default="claude-sonnet-4-5", validation_alias="ANTHROPIC_MODEL_SONNET"
    )
    anthropic_model_opus: str = Field(
        default="claude-opus-4-1", validation_alias="ANTHROPIC_MODEL_OPUS"
    )
    openai_model_default: str = Field(default="gpt-4o", validation_alias="OPENAI_MODEL_DEFAULT")
    tavily_api_key: str | None = None
    llm_provider_mode: Literal["real", "mock"] = "mock"
    code_executor_backend: Literal["docker", "disabled"] = "disabled"
    max_parallel_steps: int = Field(default=4, ge=1, le=100)
    worker_job_timeout: int = Field(default=600, ge=1)
    run_poll_interval: float = Field(default=0.5, gt=0)
    llm_request_timeout: float = Field(default=60.0, gt=0)
    cors_origins: list[AnyHttpUrl] = Field(
        default_factory=lambda: [AnyHttpUrl("http://localhost:3000")]
    )

    @field_validator("database_url")
    @classmethod
    def require_async_postgres(cls, value: PostgresDsn) -> PostgresDsn:
        if value.scheme != "postgresql+asyncpg":
            raise ValueError("DATABASE_URL must use postgresql+asyncpg")
        return value


@lru_cache
def get_settings() -> Settings:
    """Return cached process settings."""
    return Settings()
