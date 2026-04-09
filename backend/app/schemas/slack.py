from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class SlackConversationSummary(BaseModel):
    account_id: UUID
    conversation_id: str
    name: str | None = None
    sender: str
    preview: str | None = None
    unread_count: int = 0
    message_count: int = 0
    has_attachments: bool = False
    latest_received_at: datetime | None = None
    is_im: bool = False
    is_private: bool = False


class SlackConversationListResponse(BaseModel):
    conversations: list[SlackConversationSummary]
    total: int


class SlackMessage(BaseModel):
    ts: str
    sender: str | None = None
    user_id: str | None = None
    text: str | None = None
    subtype: str | None = None
    thread_ts: str | None = None
    has_attachments: bool = False


class SlackMessageListResponse(BaseModel):
    messages: list[SlackMessage]
    total: int


class SlackSendRequest(BaseModel):
    conversation_id: str = Field(..., min_length=1)
    text: str = Field(..., min_length=1)
    account_id: UUID | None = None


class SlackSendResponse(BaseModel):
    status: str
    channel: str
    ts: str
