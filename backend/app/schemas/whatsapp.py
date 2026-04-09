from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class WhatsAppStatusResponse(BaseModel):
    running: bool
    pid: int | None = None
    device_id: str
    qr_data_uri: str | None = None
    qr_text: str | None = None
    messages_log_exists: bool
    connection_state: str | None = None
    me_jid: str | None = None
    state_updated_at: str | None = None
    state_age_seconds: float | None = None


class WhatsAppSendRequest(BaseModel):
    to: str
    text: str


class WhatsAppSendResponse(BaseModel):
    status: str


class WhatsAppMessage(BaseModel):
    direction: str | None = None
    chat_jid: str | None = None
    sender_jid: str | None = None
    from_me: bool | None = None
    is_group: bool | None = None
    message_id: str | None = None
    timestamp: int | None = None
    received_at: str | None = None
    message_type: str | None = None
    text: str | None = None


class WhatsAppMessagesResponse(BaseModel):
    messages: list[WhatsAppMessage]


class WhatsAppConversationSummary(BaseModel):
    account_id: UUID
    conversation_id: str
    sender: str
    preview: str | None = None
    unread_count: int = 0
    message_count: int = 0
    has_attachments: bool = False
    latest_received_at: datetime | None = None
    is_group: bool = False


class WhatsAppConversationListResponse(BaseModel):
    conversations: list[WhatsAppConversationSummary]
    total: int


class WhatsAppConversationMessage(BaseModel):
    message_id: str | None = None
    sender: str | None = None
    from_me: bool = False
    text: str | None = None
    message_type: str | None = None
    timestamp: int | None = None
    received_at: datetime | None = None


class WhatsAppConversationMessagesResponse(BaseModel):
    messages: list[WhatsAppConversationMessage]
    total: int
