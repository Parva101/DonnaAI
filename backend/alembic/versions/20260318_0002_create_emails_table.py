"""create emails table

Revision ID: 20260318_0002
Revises: 20260227_0001
Create Date: 2026-03-18
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260318_0002"
down_revision = "20260227_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "emails",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        # Gmail IDs
        sa.Column("gmail_message_id", sa.String(255), nullable=True),
        sa.Column("thread_id", sa.String(255), nullable=True),
        sa.Column("history_id", sa.String(64), nullable=True),
        # Core fields
        sa.Column("subject", sa.Text(), nullable=True),
        sa.Column("snippet", sa.Text(), nullable=True),
        sa.Column("from_address", sa.String(255), nullable=True),
        sa.Column("from_name", sa.String(255), nullable=True),
        sa.Column("to_addresses", sa.JSON(), nullable=True),
        sa.Column("cc_addresses", sa.JSON(), nullable=True),
        sa.Column("bcc_addresses", sa.JSON(), nullable=True),
        sa.Column("reply_to", sa.String(255), nullable=True),
        # Body
        sa.Column("body_text", sa.Text(), nullable=True),
        sa.Column("body_html", sa.Text(), nullable=True),
        # Classification
        sa.Column("category", sa.String(50), nullable=False, server_default="uncategorized"),
        sa.Column("category_source", sa.String(20), nullable=False, server_default="pending"),
        # Flags
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_starred", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_draft", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("has_attachments", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        # Gmail labels
        sa.Column("gmail_labels", sa.JSON(), nullable=True),
        # Timestamps
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("internal_date", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        # Constraints
        sa.PrimaryKeyConstraint("id", name="pk_emails"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_emails_user_id_users", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["account_id"], ["connected_accounts.id"], name="fk_emails_account_id_connected_accounts", ondelete="CASCADE"),
    )

    # Indexes
    op.create_index("ix_emails_user_id", "emails", ["user_id"])
    op.create_index("ix_emails_account_id", "emails", ["account_id"])
    op.create_index("ix_emails_user_category", "emails", ["user_id", "category"])
    op.create_index("ix_emails_user_received", "emails", ["user_id", "received_at"])
    op.create_index("ix_emails_gmail_id", "emails", ["gmail_message_id"], unique=True)
    op.create_index("ix_emails_thread", "emails", ["user_id", "thread_id"])
    op.create_index("ix_emails_received_at", "emails", ["received_at"])


def downgrade() -> None:
    op.drop_table("emails")
