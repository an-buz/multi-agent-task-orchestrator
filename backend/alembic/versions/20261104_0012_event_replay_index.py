"""Index run event replay by run and cursor."""

from alembic import op

revision = "20261104_0012"
down_revision = "20261021_0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_run_events_run_id_id", "run_events", ["run_id", "id"])


def downgrade() -> None:
    op.drop_index("ix_run_events_run_id_id", table_name="run_events")
