from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class EmailRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    account_id: UUID
    gmail_message_id: str | None
    thread_id: str | None
    subject: str | None
    snippet: str | None
    from_address: str | None
    from_name: str | None
    to_addresses: list | None
    cc_addresses: list | None
    bcc_addresses: list | None
    reply_to: str | None
    body_text: str | None
    body_html: str | None
    category: str
    category_source: str
    needs_review: bool
    is_read: bool
    is_starred: bool
    is_draft: bool
    has_attachments: bool
    gmail_labels: list | None
    received_at: datetime | None
    human_reviewed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class EmailSummary(BaseModel):
    """Lightweight version for list views — no body content."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    account_id: UUID
    gmail_message_id: str | None
    thread_id: str | None
    subject: str | None
    snippet: str | None
    from_address: str | None
    from_name: str | None
    to_addresses: list | None
    category: str
    category_source: str
    needs_review: bool
    is_read: bool
    is_starred: bool
    has_attachments: bool
    received_at: datetime | None


class EmailUpdate(BaseModel):
    is_read: bool | None = None
    is_starred: bool | None = None
    category: str | None = None


class EmailCategoryCount(BaseModel):
    category: str
    count: int
    unread: int


class EmailListResponse(BaseModel):
    emails: list[EmailSummary]
    total: int
    categories: list[EmailCategoryCount]


class EmailComposeRequest(BaseModel):
    account_id: UUID
    to: list[str]
    cc: list[str] | None = None
    bcc: list[str] | None = None
    subject: str | None = None
    body: str = ""
    in_reply_to: str | None = None  # gmail_message_id of the original
    thread_id: str | None = None  # keep in same thread for replies


class EmailSendResponse(BaseModel):
    status: str
    gmail_message_id: str | None = None
    thread_id: str | None = None


class EmailSyncRequest(BaseModel):
    account_id: UUID


class EmailSyncStatus(BaseModel):
    status: str
    synced: int
    classified: int
    account_id: UUID


class SyncAllStatus(BaseModel):
    status: str
    accounts_queued: int
    account_ids: list[UUID]
