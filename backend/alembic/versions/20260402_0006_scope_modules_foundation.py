"""scope_modules_foundation

Revision ID: 20260402_0006
Revises: 20260331_0005
Create Date: 2026-04-02 01:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260402_0006"
down_revision: Union[str, Sequence[str], None] = "20260331_0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(inspector: sa.Inspector, table: str, column: str) -> bool:
    return any(c["name"] == column for c in inspector.get_columns(table))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "users" in inspector.get_table_names() and not _column_exists(inspector, "users", "preferences"):
        op.add_column("users", sa.Column("preferences", sa.JSON(), nullable=True))

    if "emails" in inspector.get_table_names():
        if not _column_exists(inspector, "emails", "priority_score"):
            op.add_column(
                "emails",
                sa.Column("priority_score", sa.Float(), nullable=False, server_default="0"),
            )
            op.alter_column("emails", "priority_score", server_default=None)
        if not _column_exists(inspector, "emails", "priority_label"):
            op.add_column(
                "emails",
                sa.Column("priority_label", sa.String(length=12), nullable=False, server_default="low"),
            )
            op.alter_column("emails", "priority_label", server_default=None)

    if "action_items" not in inspector.get_table_names():
        op.create_table(
            "action_items",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("user_id", sa.Uuid(), nullable=False),
            sa.Column("source_platform", sa.String(length=32), nullable=False),
            sa.Column("source_ref", sa.String(length=255), nullable=True),
            sa.Column("title", sa.String(length=255), nullable=False),
            sa.Column("details", sa.Text(), nullable=True),
            sa.Column("status", sa.String(length=24), nullable=False),
            sa.Column("priority", sa.String(length=12), nullable=False),
            sa.Column("score", sa.Integer(), nullable=False),
            sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_action_items_user_id"), "action_items", ["user_id"], unique=False)

    if "news_sources" not in inspector.get_table_names():
        op.create_table(
            "news_sources",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("user_id", sa.Uuid(), nullable=False),
            sa.Column("source_type", sa.String(length=20), nullable=False),
            sa.Column("name", sa.String(length=120), nullable=False),
            sa.Column("url", sa.Text(), nullable=True),
            sa.Column("topic", sa.String(length=40), nullable=False),
            sa.Column("enabled", sa.Boolean(), nullable=False),
            sa.Column("fetch_interval_minutes", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_news_sources_user_id"), "news_sources", ["user_id"], unique=False)

    if "news_articles" not in inspector.get_table_names():
        op.create_table(
            "news_articles",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("user_id", sa.Uuid(), nullable=False),
            sa.Column("source_id", sa.Uuid(), nullable=True),
            sa.Column("external_id", sa.String(length=255), nullable=True),
            sa.Column("title", sa.Text(), nullable=False),
            sa.Column("url", sa.Text(), nullable=False),
            sa.Column("source_name", sa.String(length=120), nullable=False),
            sa.Column("summary", sa.Text(), nullable=True),
            sa.Column("topic", sa.String(length=40), nullable=False),
            sa.Column("relevance_score", sa.Float(), nullable=False),
            sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["source_id"], ["news_sources.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_news_articles_user_id"), "news_articles", ["user_id"], unique=False)
        op.create_index(op.f("ix_news_articles_source_id"), "news_articles", ["source_id"], unique=False)
        op.create_index(op.f("ix_news_articles_external_id"), "news_articles", ["external_id"], unique=False)
        op.create_index("ix_news_articles_user_topic", "news_articles", ["user_id", "topic"], unique=False)

    if "news_bookmarks" not in inspector.get_table_names():
        op.create_table(
            "news_bookmarks",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("user_id", sa.Uuid(), nullable=False),
            sa.Column("article_id", sa.Uuid(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["article_id"], ["news_articles.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("user_id", "article_id"),
        )
        op.create_index(op.f("ix_news_bookmarks_user_id"), "news_bookmarks", ["user_id"], unique=False)
        op.create_index(op.f("ix_news_bookmarks_article_id"), "news_bookmarks", ["article_id"], unique=False)

    if "voice_calls" not in inspector.get_table_names():
        op.create_table(
            "voice_calls",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("user_id", sa.Uuid(), nullable=False),
            sa.Column("target_name", sa.String(length=255), nullable=True),
            sa.Column("target_phone", sa.String(length=80), nullable=True),
            sa.Column("intent", sa.Text(), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("transcript", sa.Text(), nullable=True),
            sa.Column("summary", sa.Text(), nullable=True),
            sa.Column("outcome", sa.Text(), nullable=True),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_voice_calls_user_id"), "voice_calls", ["user_id"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "voice_calls" in inspector.get_table_names():
        op.drop_index(op.f("ix_voice_calls_user_id"), table_name="voice_calls")
        op.drop_table("voice_calls")

    if "news_bookmarks" in inspector.get_table_names():
        op.drop_index(op.f("ix_news_bookmarks_article_id"), table_name="news_bookmarks")
        op.drop_index(op.f("ix_news_bookmarks_user_id"), table_name="news_bookmarks")
        op.drop_table("news_bookmarks")

    if "news_articles" in inspector.get_table_names():
        op.drop_index("ix_news_articles_user_topic", table_name="news_articles")
        op.drop_index(op.f("ix_news_articles_external_id"), table_name="news_articles")
        op.drop_index(op.f("ix_news_articles_source_id"), table_name="news_articles")
        op.drop_index(op.f("ix_news_articles_user_id"), table_name="news_articles")
        op.drop_table("news_articles")

    if "news_sources" in inspector.get_table_names():
        op.drop_index(op.f("ix_news_sources_user_id"), table_name="news_sources")
        op.drop_table("news_sources")

    if "action_items" in inspector.get_table_names():
        op.drop_index(op.f("ix_action_items_user_id"), table_name="action_items")
        op.drop_table("action_items")

    if "emails" in inspector.get_table_names() and _column_exists(inspector, "emails", "priority_label"):
        op.drop_column("emails", "priority_label")

    if "emails" in inspector.get_table_names() and _column_exists(inspector, "emails", "priority_score"):
        op.drop_column("emails", "priority_score")

    if "users" in inspector.get_table_names() and _column_exists(inspector, "users", "preferences"):
        op.drop_column("users", "preferences")
