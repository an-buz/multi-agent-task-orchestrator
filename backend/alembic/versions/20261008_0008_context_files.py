"""Persist validated context files and run references."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20261008_0008"
down_revision = "20261008_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "context_files",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("media_type", sa.String(100), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.Column("text_content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "run_files",
        sa.Column("run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("runs.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("file_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("context_files.id", ondelete="RESTRICT"), primary_key=True),
    )
    op.create_index("ix_run_files_file_id", "run_files", ["file_id"])


def downgrade() -> None:
    op.drop_table("run_files")
    op.drop_table("context_files")
