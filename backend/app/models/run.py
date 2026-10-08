"""Persisted workflow runs and their editable plans."""

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Run(Base):
    """A single requested execution of a workflow."""

    __tablename__ = "runs"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    workflow_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("workflows.id", ondelete="RESTRICT"), nullable=False
    )
    task: Mapped[str] = mapped_column(Text, nullable=False)
    context_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="AWAITING_CONFIRMATION")
    plan: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    planner_config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    planning_prompt_tokens: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    planning_completion_tokens: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    planning_time_ms: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    planning_error: Mapped[dict[str, str] | None] = mapped_column(JSONB, nullable=True)
    final_report: Mapped[str | None] = mapped_column(Text, nullable=True)
    total_tokens: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    total_time_ms: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
