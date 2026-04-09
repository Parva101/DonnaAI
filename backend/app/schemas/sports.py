"""Sports tracking and live score schemas."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.calendar import CalendarEvent


class SportsLeagueRead(BaseModel):
    key: str
    label: str


class SportsLeagueListResponse(BaseModel):
    leagues: list[SportsLeagueRead]


class SportsTeamRead(BaseModel):
    league: str
    league_label: str
    team_id: str
    team_name: str
    display_name: str
    abbreviation: str | None = None
    location: str | None = None
    logo_url: str | None = None


class SportsTeamSearchResponse(BaseModel):
    teams: list[SportsTeamRead]
    total: int


class SportsTrackTeamRequest(BaseModel):
    league: str = Field(min_length=2, max_length=24)
    team_id: str = Field(min_length=1, max_length=64)
    team_name: str = Field(min_length=1, max_length=120)
    display_name: str = Field(min_length=1, max_length=160)
    abbreviation: str | None = Field(default=None, max_length=32)
    logo_url: str | None = None


class SportsTrackedTeamRead(SportsTeamRead):
    id: UUID
    user_id: UUID
    created_at: datetime
    updated_at: datetime


class SportsTrackedTeamListResponse(BaseModel):
    teams: list[SportsTrackedTeamRead]
    total: int


class SportsGameTeamRead(BaseModel):
    team_id: str
    name: str
    abbreviation: str | None = None
    logo_url: str | None = None
    home_away: str
    score: int | None = None
    winner: bool | None = None
    record: str | None = None
    tracked: bool = False


class SportsGameRead(BaseModel):
    game_id: str
    league: str
    league_label: str
    start_time: datetime | None = None
    status: str
    status_detail: str | None = None
    state: str
    is_live: bool
    is_final: bool
    is_upcoming: bool
    period: int | None = None
    clock: str | None = None
    venue: str | None = None
    broadcast: str | None = None
    home: SportsGameTeamRead
    away: SportsGameTeamRead


class SportsGameListResponse(BaseModel):
    generated_at: datetime
    games: list[SportsGameRead]
    total: int


class SportsCalendarEventCreateRequest(BaseModel):
    account_id: UUID | None = None
    game_id: str = Field(min_length=1, max_length=128)
    league: str = Field(min_length=1, max_length=32)
    league_label: str = Field(min_length=1, max_length=80)
    start_time: datetime
    status: str = Field(min_length=1, max_length=120)
    status_detail: str | None = Field(default=None, max_length=240)
    venue: str | None = Field(default=None, max_length=240)
    broadcast: str | None = Field(default=None, max_length=120)
    home: SportsGameTeamRead
    away: SportsGameTeamRead
    title: str | None = Field(default=None, max_length=240)
    duration_minutes: int = Field(default=180, ge=30, le=720)


class SportsCalendarEventCreateResponse(BaseModel):
    status: str
    event: CalendarEvent
