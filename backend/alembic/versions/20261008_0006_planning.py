"""Persist planner configuration, usage and failure state.

Revision ID: 20261008_0006
Revises: 20261007_0005
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261008_0006"
down_revision: str | None = "20261007_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("runs", sa.Column("planner_config", postgresql.JSONB(), nullable=False,
                                   server_default=sa.text("'{}'::jsonb")))
    for name in ("planning_prompt_tokens", "planning_completion_tokens", "planning_time_ms"):
        op.add_column("runs", sa.Column(name, sa.Integer(), nullable=False, server_default="0"))
    op.add_column("runs", sa.Column("planning_error", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    for name in ("planning_error", "planning_time_ms", "planning_completion_tokens",
                 "planning_prompt_tokens", "planner_config"):
        op.drop_column("runs", name)
