"""Create agents table.

Revision ID: 20261005_0001
Revises:
Create Date: 2026-10-05 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261005_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agents",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("role", sa.String(length=500), nullable=False),
        sa.Column("system_prompt", sa.Text(), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("temperature", sa.Float(), nullable=False),
        sa.Column("max_tokens", sa.Integer(), nullable=False),
        sa.Column("context_window", sa.Integer(), nullable=False),
        sa.Column("tools", postgresql.ARRAY(sa.String()), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_agents_name"),
    )


def downgrade() -> None:
    op.drop_table("agents")
