"""chat_ingestion_foundation

Revision ID: 20260409_0007
Revises: 20260402_0006, f8de8784e5a2
Create Date: 2026-04-09 01:05:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260409_0007"
down_revision: Union[str, Sequence[str], None] = ("20260402_0006", "f8de8784e5a2")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "chat_conversations" not in tables:
        op.create_table(
            "chat_conversations",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("user_id", sa.Uuid(), nullable=False),
            sa.Column("account_id", sa.Uuid(), nullable=False),
            sa.Column("platform", sa.String(length=32), nullable=False),
            sa.Column("external_conversation_id", sa.String(length=255), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=True),
            sa.Column("sender", sa.String(length=255), nullable=True),
            sa.Column("preview", sa.Text(), nullable=True),
            sa.Column("unread_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("message_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("has_attachments", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("latest_received_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("is_group", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("is_im", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("is_private", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("conversation_metadata", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["account_id"], ["connected_accounts.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "user_id",
                "account_id",
                "platform",
                "external_conversation_id",
                name="uq_chat_conversations_external",
            ),
        )
        op.create_index(op.f("ix_chat_conversations_user_id"), "chat_conversations", ["user_id"], unique=False)
        op.create_index(
            op.f("ix_chat_conversations_account_id"),
            "chat_conversations",
            ["account_id"],
            unique=False,
        )
        op.create_index(op.f("ix_chat_conversations_platform"), "chat_conversations", ["platform"], unique=False)
        op.create_index(
            op.f("ix_chat_conversations_latest_received_at"),
            "chat_conversations",
            ["latest_received_at"],
            unique=False,
        )
        op.create_index(
            "ix_chat_conversations_user_platform_latest",
            "chat_conversations",
            ["user_id", "platform", "latest_received_at"],
            unique=False,
        )

    if "chat_messages" not in tables:
        op.create_table(
            "chat_messages",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("conversation_id", sa.Uuid(), nullable=False),
            sa.Column("user_id", sa.Uuid(), nullable=False),
            sa.Column("account_id", sa.Uuid(), nullable=False),
            sa.Column("platform", sa.String(length=32), nullable=False),
            sa.Column("external_message_id", sa.String(length=255), nullable=False),
            sa.Column("sender", sa.String(length=255), nullable=True),
            sa.Column("sender_id", sa.String(length=255), nullable=True),
            sa.Column("text", sa.Text(), nullable=True),
            sa.Column("direction", sa.String(length=16), nullable=False, server_default="inbound"),
            sa.Column("subtype", sa.String(length=64), nullable=True),
            sa.Column("thread_ref", sa.String(length=255), nullable=True),
            sa.Column("has_attachments", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("raw_payload", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["account_id"], ["connected_accounts.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["conversation_id"], ["chat_conversations.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "conversation_id",
                "external_message_id",
                name="uq_chat_messages_external_per_conversation",
            ),
        )
        op.create_index(op.f("ix_chat_messages_conversation_id"), "chat_messages", ["conversation_id"], unique=False)
        op.create_index(op.f("ix_chat_messages_user_id"), "chat_messages", ["user_id"], unique=False)
        op.create_index(op.f("ix_chat_messages_account_id"), "chat_messages", ["account_id"], unique=False)
        op.create_index(op.f("ix_chat_messages_platform"), "chat_messages", ["platform"], unique=False)
        op.create_index(op.f("ix_chat_messages_sent_at"), "chat_messages", ["sent_at"], unique=False)
        op.create_index(
            "ix_chat_messages_user_platform_sent",
            "chat_messages",
            ["user_id", "platform", "sent_at"],
            unique=False,
        )

    if "chat_outbound_actions" not in tables:
        op.create_table(
            "chat_outbound_actions",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("user_id", sa.Uuid(), nullable=False),
            sa.Column("account_id", sa.Uuid(), nullable=False),
            sa.Column("conversation_id", sa.Uuid(), nullable=True),
            sa.Column("platform", sa.String(length=32), nullable=False),
            sa.Column("action_type", sa.String(length=24), nullable=False, server_default="send"),
            sa.Column("target", sa.String(length=255), nullable=False),
            sa.Column("request_text", sa.Text(), nullable=True),
            sa.Column("request_payload", sa.JSON(), nullable=True),
            sa.Column("idempotency_key", sa.String(length=100), nullable=False),
            sa.Column("status", sa.String(length=24), nullable=False, server_default="queued"),
            sa.Column("provider_message_id", sa.String(length=255), nullable=True),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["account_id"], ["connected_accounts.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["conversation_id"], ["chat_conversations.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("idempotency_key"),
        )
        op.create_index(
            op.f("ix_chat_outbound_actions_user_id"),
            "chat_outbound_actions",
            ["user_id"],
            unique=False,
        )
        op.create_index(
            op.f("ix_chat_outbound_actions_account_id"),
            "chat_outbound_actions",
            ["account_id"],
            unique=False,
        )
        op.create_index(
            op.f("ix_chat_outbound_actions_conversation_id"),
            "chat_outbound_actions",
            ["conversation_id"],
            unique=False,
        )
        op.create_index(
            op.f("ix_chat_outbound_actions_platform"),
            "chat_outbound_actions",
            ["platform"],
            unique=False,
        )
        op.create_index(
            op.f("ix_chat_outbound_actions_idempotency_key"),
            "chat_outbound_actions",
            ["idempotency_key"],
            unique=True,
        )
        op.create_index(
            "ix_chat_outbound_actions_user_platform_status",
            "chat_outbound_actions",
            ["user_id", "platform", "status"],
            unique=False,
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "chat_outbound_actions" in tables:
        op.drop_index("ix_chat_outbound_actions_user_platform_status", table_name="chat_outbound_actions")
        op.drop_index(op.f("ix_chat_outbound_actions_idempotency_key"), table_name="chat_outbound_actions")
        op.drop_index(op.f("ix_chat_outbound_actions_platform"), table_name="chat_outbound_actions")
        op.drop_index(op.f("ix_chat_outbound_actions_conversation_id"), table_name="chat_outbound_actions")
        op.drop_index(op.f("ix_chat_outbound_actions_account_id"), table_name="chat_outbound_actions")
        op.drop_index(op.f("ix_chat_outbound_actions_user_id"), table_name="chat_outbound_actions")
        op.drop_table("chat_outbound_actions")

    if "chat_messages" in tables:
        op.drop_index("ix_chat_messages_user_platform_sent", table_name="chat_messages")
        op.drop_index(op.f("ix_chat_messages_sent_at"), table_name="chat_messages")
        op.drop_index(op.f("ix_chat_messages_platform"), table_name="chat_messages")
        op.drop_index(op.f("ix_chat_messages_account_id"), table_name="chat_messages")
        op.drop_index(op.f("ix_chat_messages_user_id"), table_name="chat_messages")
        op.drop_index(op.f("ix_chat_messages_conversation_id"), table_name="chat_messages")
        op.drop_table("chat_messages")

    if "chat_conversations" in tables:
        op.drop_index("ix_chat_conversations_user_platform_latest", table_name="chat_conversations")
        op.drop_index(op.f("ix_chat_conversations_latest_received_at"), table_name="chat_conversations")
        op.drop_index(op.f("ix_chat_conversations_platform"), table_name="chat_conversations")
        op.drop_index(op.f("ix_chat_conversations_account_id"), table_name="chat_conversations")
        op.drop_index(op.f("ix_chat_conversations_user_id"), table_name="chat_conversations")
        op.drop_table("chat_conversations")
