from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class InboxConversationSummary(BaseModel):
    conversation_id: str
    platform: str
    account_id: UUID
    latest_email_id: str | None = None
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


class ChatIngestionFailure(BaseModel):
    conversation_id: str
    error: str


class ChatIngestionPlatformResult(BaseModel):
    platform: str
    conversations_discovered: int
    conversations_synced: int
    messages_synced: int
    failures: list[ChatIngestionFailure] = Field(default_factory=list)


class ChatIngestionTotals(BaseModel):
    conversations_discovered: int
    conversations_synced: int
    messages_synced: int
    failed_conversations: int


class ChatIngestionSyncRequest(BaseModel):
    platform: str = Field(default="all", min_length=3, max_length=24)
    account_id: UUID | None = None
    unread_only: bool = False
    search: str | None = None
    conversation_limit: int = Field(default=200, ge=1, le=5000)
    message_limit: int = Field(default=200, ge=1, le=2000)


class ChatIngestionSyncResponse(BaseModel):
    status: str
    platform: str
    totals: ChatIngestionTotals
    results: list[ChatIngestionPlatformResult]
