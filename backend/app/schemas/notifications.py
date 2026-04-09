from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class NotificationPreferences(BaseModel):
    email_enabled: bool = True
    slack_enabled: bool = True
    whatsapp_enabled: bool = True
    teams_enabled: bool = True
    focus_mode: bool = False
    daily_digest_enabled: bool = True
    daily_digest_hour_utc: int = Field(default=13, ge=0, le=23)


class NotificationPreferencesResponse(BaseModel):
    preferences: NotificationPreferences


class NotificationPreferencesUpdate(BaseModel):
    email_enabled: bool | None = None
    slack_enabled: bool | None = None
    whatsapp_enabled: bool | None = None
    teams_enabled: bool | None = None
    focus_mode: bool | None = None
    daily_digest_enabled: bool | None = None
    daily_digest_hour_utc: int | None = Field(default=None, ge=0, le=23)


class DigestItem(BaseModel):
    title: str
    source: str
    preview: str
    url: str | None = None


class DailyDigestResponse(BaseModel):
    generated_at: datetime
    summary: str
    top_items: list[DigestItem]
