from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class TeamsConversationSummary(BaseModel):
    account_id: UUID
    conversation_id: str
    name: str | None = None
    sender: str
    preview: str | None = None
    unread_count: int = 0
    message_count: int = 0
    has_attachments: bool = False
    latest_received_at: datetime | None = None


class TeamsConversationListResponse(BaseModel):
    conversations: list[TeamsConversationSummary]
    total: int


class TeamsMessage(BaseModel):
    id: str
    sender: str | None = None
    from_me: bool = False
    text: str | None = None
    created_at: datetime | None = None
    has_attachments: bool = False


class TeamsMessageListResponse(BaseModel):
    messages: list[TeamsMessage]
    total: int


class TeamsSendRequest(BaseModel):
    conversation_id: str
    text: str
    account_id: UUID | None = None


class TeamsSendResponse(BaseModel):
    status: str
    conversation_id: str
    message_id: str | None = None


class TeamsPresenceResponse(BaseModel):
    account_id: UUID
    availability: str
    activity: str
