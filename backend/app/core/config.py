"""Environment-backed application settings."""

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal, Self

from pydantic import AnyHttpUrl, Field, PostgresDsn, RedisDsn, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"
    database_url: PostgresDsn = PostgresDsn(
        "postgresql+asyncpg://app:app@localhost:5432/orchestrator"
    )
    redis_url: RedisDsn = RedisDsn("redis://localhost:16379/0")
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
    tavily_search_url: str = "https://api.tavily.com/search"
    tool_max_rounds: int = Field(default=8, ge=1, le=50)
    tool_max_calls: int = Field(default=16, ge=1, le=100)
    tool_output_max_chars: int = Field(default=20000, ge=1)
    tool_timeout: float = Field(default=30, gt=0)
    pdf_max_pages: int = Field(default=100, ge=1)
    code_executor_image: str = "python:3.14-slim"
    code_executor_memory: str = "128m"
    code_executor_cpus: float = Field(default=0.5, gt=0)
    code_executor_pids: int = Field(default=64, ge=1)
    code_executor_workspace_bytes: int = Field(default=16 * 1024 * 1024, ge=1)
    run_token_budget: int | None = Field(default=None, ge=1)
    context_file_max_bytes: int = Field(default=5 * 1024 * 1024, ge=1)
    run_context_max_chars: int = Field(default=200000, ge=1)
    llm_provider_mode: Literal["real", "mock"] = "mock"
    demo_mode: bool = False
    mock_stream_chunk_chars: int = Field(default=12, ge=1, le=10000)
    mock_stream_delay: float = Field(default=0.2, ge=0, le=5)
    code_executor_backend: Literal["docker", "disabled"] = "disabled"
    max_parallel_steps: int = Field(default=4, ge=1, le=100)
    worker_job_timeout: int = Field(default=600, ge=1)
    recovery_batch_size: int = Field(default=100, ge=1, le=1000)
    cleanup_batch_size: int = Field(default=100, ge=1, le=1000)
    unused_file_retention_days: int = Field(default=7, ge=1)
    terminal_event_retention_days: int = Field(default=30, ge=1)
    code_executor_scope: str = Field(default="local", pattern=r"^[a-zA-Z0-9_.-]+$")
    code_executor_orphan_age_seconds: int = Field(default=3600, ge=1)
    cleanup_docker_timeout: float = Field(default=10, gt=0)
    run_poll_interval: float = Field(default=0.5, gt=0)
    planner_model: str = "claude-sonnet"
    default_agent_model: str = "claude-sonnet"
    default_agent_temperature: float = Field(default=0.7, ge=0, le=1)
    default_agent_max_tokens: int = Field(default=4096, ge=1, le=8192)
    export_pdf_font_path: Path = Field(
        default_factory=lambda: (
            Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts/arial.ttf"
            if os.name == "nt"
            else Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
        )
    )
    planner_max_tokens: int = Field(default=4096, ge=1)
    planner_temperature: float = Field(default=0.2, ge=0, le=1)
    planner_max_repairs: int = Field(default=2, ge=0, le=5)
    llm_request_timeout: float = Field(default=60.0, gt=0)
    context_safety_margin_tokens: int = Field(default=256, ge=0)
    openai_encoding: str = "o200k_base"
    cors_origins: list[AnyHttpUrl] = Field(
        default_factory=lambda: [AnyHttpUrl("http://localhost:3000")]
    )

    @field_validator("database_url")
    @classmethod
    def require_async_postgres(cls, value: PostgresDsn) -> PostgresDsn:
        if value.scheme != "postgresql+asyncpg":
            raise ValueError("DATABASE_URL must use postgresql+asyncpg")
        return value

    @model_validator(mode="after")
    def enforce_demo_simulation(self) -> Self:
        if self.demo_mode:
            self.llm_provider_mode = "mock"
            self.code_executor_backend = "disabled"
            self.run_token_budget = None
        return self


@lru_cache
def get_settings() -> Settings:
    """Return cached process settings."""
    return Settings()
