"""Persist shared default agent parameters.

Revision ID: 20261008_0007
Revises: 20261008_0006
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261008_0007"
down_revision: str | None = "20261008_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "app_config",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("defaults", postgresql.JSONB(), nullable=False),
        sa.CheckConstraint("id = 1", name="app_config_singleton"),
    )


def downgrade() -> None:
    op.drop_table("app_config")
