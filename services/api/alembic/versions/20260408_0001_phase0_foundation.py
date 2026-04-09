"""Phase 0 foundation schema.

Revision ID: 20260408_0001
Revises:
Create Date: 2026-04-08
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260408_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "raw_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("platform", sa.String(length=32), nullable=False),
        sa.Column("account_id", sa.String(length=128), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("source_event_id", sa.String(length=255), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "platform", "account_id", "source_event_id", name="uq_raw_event_source"
        ),
    )
    op.create_index(op.f("ix_raw_events_tenant_id"), "raw_events", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_raw_events_platform"), "raw_events", ["platform"], unique=False)
    op.create_index(op.f("ix_raw_events_account_id"), "raw_events", ["account_id"], unique=False)
    op.create_index(op.f("ix_raw_events_event_type"), "raw_events", ["event_type"], unique=False)

    op.create_table(
        "contacts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("platform", sa.String(length=32), nullable=False),
        sa.Column("account_id", sa.String(length=128), nullable=False),
        sa.Column("contact_key", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "platform", "account_id", "contact_key", name="uq_contact_platform_key"),
    )
    op.create_index(op.f("ix_contacts_tenant_id"), "contacts", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_contacts_platform"), "contacts", ["platform"], unique=False)
    op.create_index(op.f("ix_contacts_account_id"), "contacts", ["account_id"], unique=False)

    op.create_table(
        "threads",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("platform", sa.String(length=32), nullable=False),
        sa.Column("account_id", sa.String(length=128), nullable=False),
        sa.Column("thread_key", sa.String(length=255), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "platform", "account_id", "thread_key", name="uq_thread_platform_key"),
    )
    op.create_index(op.f("ix_threads_tenant_id"), "threads", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_threads_platform"), "threads", ["platform"], unique=False)
    op.create_index(op.f("ix_threads_account_id"), "threads", ["account_id"], unique=False)

    op.create_table(
        "messages",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("platform", sa.String(length=32), nullable=False),
        sa.Column("account_id", sa.String(length=128), nullable=False),
        sa.Column("thread_key", sa.String(length=255), nullable=False),
        sa.Column("chat_key", sa.String(length=255), nullable=False),
        sa.Column("source_message_id", sa.String(length=255), nullable=False),
        sa.Column("sender_key", sa.String(length=255), nullable=True),
        sa.Column("body_text", sa.Text(), nullable=True),
        sa.Column("body_redacted", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "platform", "account_id", "source_message_id", name="uq_message_source"),
    )
    op.create_index(op.f("ix_messages_tenant_id"), "messages", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_messages_platform"), "messages", ["platform"], unique=False)
    op.create_index(op.f("ix_messages_account_id"), "messages", ["account_id"], unique=False)
    op.create_index(op.f("ix_messages_thread_key"), "messages", ["thread_key"], unique=False)
    op.create_index(op.f("ix_messages_chat_key"), "messages", ["chat_key"], unique=False)
    op.create_index(op.f("ix_messages_source_message_id"), "messages", ["source_message_id"], unique=False)
    op.create_index(op.f("ix_messages_sent_at"), "messages", ["sent_at"], unique=False)

    op.create_table(
        "message_embeddings",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("message_id", sa.String(length=36), nullable=False),
        sa.Column("embedding_model", sa.String(length=128), nullable=False),
        sa.Column("embedding_vector", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_message_embeddings_tenant_id"), "message_embeddings", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_message_embeddings_message_id"), "message_embeddings", ["message_id"], unique=False)

    op.create_table(
        "permission_scopes",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("platform", sa.String(length=32), nullable=False),
        sa.Column("account_id", sa.String(length=128), nullable=False),
        sa.Column("chat_key", sa.String(length=255), nullable=False),
        sa.Column("read_allowed", sa.Boolean(), nullable=False),
        sa.Column("write_allowed", sa.Boolean(), nullable=False),
        sa.Column("relay_allowed", sa.Boolean(), nullable=False),
        sa.Column("updated_by", sa.String(length=128), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "platform", "account_id", "chat_key", name="uq_permission_scope"),
    )
    op.create_index(op.f("ix_permission_scopes_tenant_id"), "permission_scopes", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_permission_scopes_platform"), "permission_scopes", ["platform"], unique=False)
    op.create_index(op.f("ix_permission_scopes_account_id"), "permission_scopes", ["account_id"], unique=False)
    op.create_index(op.f("ix_permission_scopes_chat_key"), "permission_scopes", ["chat_key"], unique=False)

    op.create_table(
        "action_logs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("action_type", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("source_platform", sa.String(length=32), nullable=True),
        sa.Column("source_chat_key", sa.String(length=255), nullable=True),
        sa.Column("target_platform", sa.String(length=32), nullable=True),
        sa.Column("target_chat_key", sa.String(length=255), nullable=True),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("requires_approval", sa.Boolean(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("trace_id", sa.String(length=64), nullable=True),
        sa.Column("error_text", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "idempotency_key", name="uq_action_idempotency"),
    )
    op.create_index(op.f("ix_action_logs_tenant_id"), "action_logs", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_action_logs_action_type"), "action_logs", ["action_type"], unique=False)
    op.create_index(op.f("ix_action_logs_status"), "action_logs", ["status"], unique=False)
    op.create_index(op.f("ix_action_logs_idempotency_key"), "action_logs", ["idempotency_key"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_action_logs_idempotency_key"), table_name="action_logs")
    op.drop_index(op.f("ix_action_logs_status"), table_name="action_logs")
    op.drop_index(op.f("ix_action_logs_action_type"), table_name="action_logs")
    op.drop_index(op.f("ix_action_logs_tenant_id"), table_name="action_logs")
    op.drop_table("action_logs")

    op.drop_index(op.f("ix_permission_scopes_chat_key"), table_name="permission_scopes")
    op.drop_index(op.f("ix_permission_scopes_account_id"), table_name="permission_scopes")
    op.drop_index(op.f("ix_permission_scopes_platform"), table_name="permission_scopes")
    op.drop_index(op.f("ix_permission_scopes_tenant_id"), table_name="permission_scopes")
    op.drop_table("permission_scopes")

    op.drop_index(op.f("ix_message_embeddings_message_id"), table_name="message_embeddings")
    op.drop_index(op.f("ix_message_embeddings_tenant_id"), table_name="message_embeddings")
    op.drop_table("message_embeddings")

    op.drop_index(op.f("ix_messages_sent_at"), table_name="messages")
    op.drop_index(op.f("ix_messages_source_message_id"), table_name="messages")
    op.drop_index(op.f("ix_messages_chat_key"), table_name="messages")
    op.drop_index(op.f("ix_messages_thread_key"), table_name="messages")
    op.drop_index(op.f("ix_messages_account_id"), table_name="messages")
    op.drop_index(op.f("ix_messages_platform"), table_name="messages")
    op.drop_index(op.f("ix_messages_tenant_id"), table_name="messages")
    op.drop_table("messages")

    op.drop_index(op.f("ix_threads_account_id"), table_name="threads")
    op.drop_index(op.f("ix_threads_platform"), table_name="threads")
    op.drop_index(op.f("ix_threads_tenant_id"), table_name="threads")
    op.drop_table("threads")

    op.drop_index(op.f("ix_contacts_account_id"), table_name="contacts")
    op.drop_index(op.f("ix_contacts_platform"), table_name="contacts")
    op.drop_index(op.f("ix_contacts_tenant_id"), table_name="contacts")
    op.drop_table("contacts")

    op.drop_index(op.f("ix_raw_events_event_type"), table_name="raw_events")
    op.drop_index(op.f("ix_raw_events_account_id"), table_name="raw_events")
    op.drop_index(op.f("ix_raw_events_platform"), table_name="raw_events")
    op.drop_index(op.f("ix_raw_events_tenant_id"), table_name="raw_events")
    op.drop_table("raw_events")

