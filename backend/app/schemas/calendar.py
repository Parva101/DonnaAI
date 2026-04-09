from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class CalendarEvent(BaseModel):
    account_id: UUID
    provider: str
    event_id: str
    title: str
    description: str | None = None
    location: str | None = None
    start_at: datetime
    end_at: datetime
    attendees: list[str] = Field(default_factory=list)
    organizer: str | None = None
    is_all_day: bool = False


class CalendarEventListResponse(BaseModel):
    events: list[CalendarEvent]
    total: int


class CalendarEventCreateRequest(BaseModel):
    account_id: UUID | None = None
    title: str = Field(min_length=1, max_length=240)
    description: str | None = None
    location: str | None = None
    start_at: datetime
    end_at: datetime
    attendees: list[str] = Field(default_factory=list)
    is_all_day: bool = False


class CalendarEventCreateResponse(BaseModel):
    event: CalendarEvent


class FreeBusyRequest(BaseModel):
    account_id: UUID | None = None
    start_at: datetime
    end_at: datetime


class BusyBlock(BaseModel):
    start_at: datetime
    end_at: datetime


class FreeBusyResponse(BaseModel):
    busy: list[BusyBlock]


class SuggestSlotsRequest(BaseModel):
    account_id: UUID | None = None
    date: datetime
    duration_minutes: int = Field(default=30, ge=15, le=240)
    count: int = Field(default=5, ge=1, le=20)


class SuggestSlotsResponse(BaseModel):
    slots: list[BusyBlock]
