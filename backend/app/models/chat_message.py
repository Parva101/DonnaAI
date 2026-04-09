from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    JSON,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class ChatMessage(TimestampMixin, Base):
    __tablename__ = "chat_messages"
    __table_args__ = (
        UniqueConstraint(
            "conversation_id",
            "external_message_id",
            name="uq_chat_messages_external_per_conversation",
        ),
        Index("ix_chat_messages_user_platform_sent", "user_id", "platform", "sent_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("chat_conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
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
    platform: Mapped[str] = mapped_column(String(32), nullable=False, index=True)

    external_message_id: Mapped[str] = mapped_column(String(255), nullable=False)
    sender: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sender_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    direction: Mapped[str] = mapped_column(String(16), nullable=False, default="inbound")
    subtype: Mapped[str | None] = mapped_column(String(64), nullable=True)
    thread_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    has_attachments: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    raw_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    conversation: Mapped["ChatConversation"] = relationship(
        "ChatConversation",
        back_populates="messages",
    )
