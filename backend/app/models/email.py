from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator

from app.models.base import Base, TimestampMixin


class TSVector(TypeDecorator):
    """A cross-database tsvector type.

    Uses TSVECTOR on PostgreSQL, falls back to TEXT on other dialects (e.g. SQLite).
    This lets tests run with in-memory SQLite while production uses PG full-text search.
    """

    impl = Text
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            from sqlalchemy.dialects.postgresql import TSVECTOR
            return dialect.type_descriptor(TSVECTOR())
        return dialect.type_descriptor(Text())


class Email(TimestampMixin, Base):
    """Stores synced emails (currently Gmail; schema is multi-provider ready)."""

    __tablename__ = "emails"
    __table_args__ = (
        Index("ix_emails_user_category", "user_id", "category"),
        Index("ix_emails_user_received", "user_id", "received_at"),
        Index("ix_emails_gmail_id", "gmail_message_id", unique=True),
        Index("ix_emails_thread", "user_id", "thread_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("connected_accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ── Gmail-specific IDs ──────────────────────────────────────
    gmail_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    thread_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    history_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # ── Core email fields ───────────────────────────────────────
    subject: Mapped[str | None] = mapped_column(Text, nullable=True)
    snippet: Mapped[str | None] = mapped_column(Text, nullable=True)
    from_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    from_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    to_addresses: Mapped[list | None] = mapped_column(JSON, nullable=True)
    cc_addresses: Mapped[list | None] = mapped_column(JSON, nullable=True)
    bcc_addresses: Mapped[list | None] = mapped_column(JSON, nullable=True)
    reply_to: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Body ────────────────────────────────────────────────────
    body_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    body_html: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Classification ──────────────────────────────────────────
    category: Mapped[str] = mapped_column(
        String(50), nullable=False, default="uncategorized"
    )
    category_source: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending"
    )  # "rule", "ai", "user", "pending"
    needs_review: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    human_reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # ── Flags ───────────────────────────────────────────────────
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_starred: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_draft: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    has_attachments: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # ── Gmail labels ────────────────────────────────────────────
    gmail_labels: Mapped[list | None] = mapped_column(JSON, nullable=True)

    # ── Timestamps ──────────────────────────────────────────────
    received_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    internal_date: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    # ── Full-text search (PostgreSQL tsvector) ──────────────────
    search_vector = Column(TSVector, nullable=True)

    # ── Relationships ───────────────────────────────────────────
    user: Mapped["User"] = relationship(back_populates="emails")
    account: Mapped["ConnectedAccount"] = relationship()
