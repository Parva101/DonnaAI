from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class ChatConversation(TimestampMixin, Base):
    __tablename__ = "chat_conversations"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "account_id",
            "platform",
            "external_conversation_id",
            name="uq_chat_conversations_external",
        ),
        Index("ix_chat_conversations_user_platform_latest", "user_id", "platform", "latest_received_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
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
    platform: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    external_conversation_id: Mapped[str] = mapped_column(String(255), nullable=False)

    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sender: Mapped[str | None] = mapped_column(String(255), nullable=True)
    preview: Mapped[str | None] = mapped_column(Text, nullable=True)
    unread_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    message_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    has_attachments: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    latest_received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)

    is_group: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_im: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_private: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    conversation_metadata: Mapped[dict | None] = mapped_column(
        MutableDict.as_mutable(JSON),
        nullable=True,
    )

    messages: Mapped[list["ChatMessage"]] = relationship(
        "ChatMessage",
        back_populates="conversation",
        cascade="all, delete-orphan",
    )
