"""Add model availability and durable reconfiguration markers.

Revision ID: 0010
Revises: 0009
"""

import sqlalchemy as sa
from alembic import op

revision = "20261014_0010"
down_revision = "20261012_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "model_settings",
        sa.Column("key", sa.String(100), primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
    )
    for table in ("agents", "run_steps"):
        op.add_column(
            table,
            sa.Column("requires_reconfiguration", sa.Boolean(), nullable=False, server_default="false"),
        )


def downgrade() -> None:
    for table in ("run_steps", "agents"):
        op.drop_column(table, "requires_reconfiguration")
    op.drop_table("model_settings")
