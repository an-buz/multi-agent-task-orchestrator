"""Persisted, non-sensitive agent defaults."""

from sqlalchemy import CheckConstraint, Integer
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AppConfig(Base):
    __tablename__ = "app_config"
    __table_args__ = (CheckConstraint("id = 1", name="app_config_singleton"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    defaults: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
