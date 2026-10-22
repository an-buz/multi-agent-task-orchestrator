"""Persist user decisions and independent pause reasons.

Revision ID: 20261021_0011
Revises: 20261014_0010
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20261021_0011"
down_revision = "20261014_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "runs", sa.Column("pause_reasons", postgresql.JSONB(), nullable=False, server_default="[]")
    )
    op.create_table(
        "run_decisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_step_number", sa.Integer(), nullable=False),
        sa.Column("issues", postgresql.JSONB(), nullable=False),
        sa.Column("suggested_agent_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("suggested_task", sa.String(10000), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("resolution", postgresql.JSONB(), nullable=True),
        sa.Column("followup_step_numbers", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("run_id", "source_step_number"),
    )
    op.create_index("ix_run_decisions_run_id", "run_decisions", ["run_id"])


def downgrade() -> None:
    op.drop_table("run_decisions")
    op.drop_column("runs", "pause_reasons")
