"""Persisted agent configuration."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Float, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Agent(Base):
    """Agent settings used when executing workflow steps."""

    __tablename__ = "agents"
    __table_args__ = (UniqueConstraint("name", name="uq_agents_name"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    role: Mapped[str] = mapped_column(String(500), nullable=False)
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    temperature: Mapped[float] = mapped_column(Float, nullable=False, default=0.7)
    max_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=4096)
    context_window: Mapped[int] = mapped_column(Integer, nullable=False, default=128000)
    tools: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
