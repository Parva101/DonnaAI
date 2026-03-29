from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class InboxConversationSummary(BaseModel):
    conversation_id: str
    platform: str
    account_id: UUID
    latest_email_id: UUID
    sender: str
    sender_address: str | None
    subject: str | None
    preview: str | None
    unread_count: int
    message_count: int
    has_attachments: bool
    needs_review: bool
    category: str
    latest_received_at: datetime | None


class InboxPlatformCount(BaseModel):
    platform: str
    total: int
    unread: int


class InboxConversationListResponse(BaseModel):
    conversations: list[InboxConversationSummary]
    total: int
    platform_counts: list[InboxPlatformCount]
