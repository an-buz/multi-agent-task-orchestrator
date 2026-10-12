"""Persist provider turns and tool execution receipts for crash recovery."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20261012_0009"
down_revision = "20261008_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "runs", sa.Column("planning_checkpoint", postgresql.JSONB(), nullable=False,
                          server_default=sa.text("'{}'::jsonb")),
    )
    op.add_column(
        "run_steps",
        sa.Column("checkpoint", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )


def downgrade() -> None:
    op.drop_column("run_steps", "checkpoint")
    op.drop_column("runs", "planning_checkpoint")
