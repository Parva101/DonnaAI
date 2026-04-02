from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class VoiceCallCreate(BaseModel):
    intent: str
    target_name: str | None = None
    target_phone: str | None = None


class VoiceCallRead(BaseModel):
    id: UUID
    user_id: UUID
    target_name: str | None = None
    target_phone: str | None = None
    intent: str
    status: str
    transcript: str | None = None
    summary: str | None = None
    outcome: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class VoiceCallListResponse(BaseModel):
    calls: list[VoiceCallRead]
    total: int
