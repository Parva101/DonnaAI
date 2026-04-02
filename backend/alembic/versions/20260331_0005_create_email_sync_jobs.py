"""create_email_sync_jobs

Revision ID: 20260331_0005
Revises: 20260328_0004
Create Date: 2026-03-31 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260331_0005"
down_revision: Union[str, Sequence[str], None] = "20260328_0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "email_sync_jobs" in inspector.get_table_names():
        return

    op.create_table(
        "email_sync_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="queued"),
        sa.Column("stage", sa.String(length=40), nullable=False, server_default="queued"),
        sa.Column(
            "mode",
            sa.String(length=20),
            nullable=False,
            server_default="sync_and_classify",
        ),
        sa.Column("accounts_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("accounts_done", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("fetched_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("classify_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("classified_done", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("remaining_pending", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_email_sync_jobs_user_created",
        "email_sync_jobs",
        ["user_id", "created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_email_sync_jobs_user_id"),
        "email_sync_jobs",
        ["user_id"],
        unique=False,
    )

    op.alter_column("email_sync_jobs", "status", server_default=None)
    op.alter_column("email_sync_jobs", "stage", server_default=None)
    op.alter_column("email_sync_jobs", "mode", server_default=None)
    op.alter_column("email_sync_jobs", "accounts_total", server_default=None)
    op.alter_column("email_sync_jobs", "accounts_done", server_default=None)
    op.alter_column("email_sync_jobs", "fetched_total", server_default=None)
    op.alter_column("email_sync_jobs", "classify_total", server_default=None)
    op.alter_column("email_sync_jobs", "classified_done", server_default=None)
    op.alter_column("email_sync_jobs", "failed_count", server_default=None)
    op.alter_column("email_sync_jobs", "remaining_pending", server_default=None)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "email_sync_jobs" not in inspector.get_table_names():
        return

    op.drop_index(op.f("ix_email_sync_jobs_user_id"), table_name="email_sync_jobs")
    op.drop_index("ix_email_sync_jobs_user_created", table_name="email_sync_jobs")
    op.drop_table("email_sync_jobs")
