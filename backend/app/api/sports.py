"""Sports tracking and live score API routes."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.db import get_db
from app.models import User
from app.schemas.sports import (
    SportsCalendarEventCreateRequest,
    SportsCalendarEventCreateResponse,
    SportsGameListResponse,
    SportsLeagueListResponse,
    SportsTeamSearchResponse,
    SportsTrackedTeamListResponse,
    SportsTrackedTeamRead,
    SportsTrackTeamRequest,
)
from app.services.calendar_service import CalendarService
from app.services.sports_service import SportsService

router = APIRouter(prefix="/sports", tags=["sports"])


@router.get("/leagues", response_model=SportsLeagueListResponse)
def list_sports_leagues() -> SportsLeagueListResponse:
    return SportsLeagueListResponse(leagues=SportsService.list_supported_leagues())


@router.get("/teams/search", response_model=SportsTeamSearchResponse)
async def search_sports_teams(
    query: str = Query(..., min_length=1, max_length=80),
    league: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SportsTeamSearchResponse:
    del current_user  # authentication required
    svc = SportsService(db)
    try:
        teams = await svc.search_teams(query=query, league=league, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Sports API failed: {exc}")
    return SportsTeamSearchResponse(teams=teams, total=len(teams))


@router.get("/teams/tracked", response_model=SportsTrackedTeamListResponse)
def list_tracked_sports_teams(
    league: str | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SportsTrackedTeamListResponse:
    svc = SportsService(db)
    try:
        rows = svc.list_tracked_teams(user_id=current_user.id, league=league)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    return SportsTrackedTeamListResponse(
        teams=[
            SportsTrackedTeamRead(
                id=row.id,
                user_id=row.user_id,
                league=row.league,
                league_label=svc._league_label(row.league),
                team_id=row.team_id,
                team_name=row.team_name,
                display_name=row.display_name,
                abbreviation=row.abbreviation,
                location=None,
                logo_url=row.logo_url,
                created_at=row.created_at,
                updated_at=row.updated_at,
            )
            for row in rows
        ],
        total=len(rows),
    )


@router.post("/teams/tracked", response_model=SportsTrackedTeamRead)
def track_sports_team(
    payload: SportsTrackTeamRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SportsTrackedTeamRead:
    svc = SportsService(db)
    try:
        row = svc.track_team(user_id=current_user.id, payload=payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    return SportsTrackedTeamRead(
        id=row.id,
        user_id=row.user_id,
        league=row.league,
        league_label=svc._league_label(row.league),
        team_id=row.team_id,
        team_name=row.team_name,
        display_name=row.display_name,
        abbreviation=row.abbreviation,
        location=None,
        logo_url=row.logo_url,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.delete("/teams/tracked/{tracked_team_id}", status_code=status.HTTP_204_NO_CONTENT)
def untrack_sports_team(
    tracked_team_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    svc = SportsService(db)
    deleted = svc.untrack_team(user_id=current_user.id, tracked_team_id=tracked_team_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tracked team not found")


@router.get("/scores/live", response_model=SportsGameListResponse)
async def list_live_scores(
    league: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SportsGameListResponse:
    svc = SportsService(db)
    try:
        games = await svc.list_live_games(user_id=current_user.id, league=league, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Sports API failed: {exc}")

    return SportsGameListResponse(
        generated_at=datetime.now(timezone.utc),
        games=games,
        total=len(games),
    )


@router.post("/calendar/events", response_model=SportsCalendarEventCreateResponse)
async def add_sports_game_to_calendar(
    payload: SportsCalendarEventCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SportsCalendarEventCreateResponse:
    title = (payload.title or "").strip() or f"{payload.away.name} at {payload.home.name}"
    start_at = payload.start_time
    if start_at.tzinfo is None:
        start_at = start_at.replace(tzinfo=timezone.utc)
    end_at = start_at + timedelta(minutes=payload.duration_minutes)

    details = [f"{payload.league_label} - {payload.status}"]
    if payload.status_detail:
        details.append(payload.status_detail)
    if payload.broadcast:
        details.append(f"Broadcast: {payload.broadcast}")
    if payload.game_id:
        details.append(f"DONNAAI_GAME_ID: {payload.game_id}")
    description = "\n".join(details)

    calendar = CalendarService(db)
    try:
        event = await calendar.create_event(
            user_id=current_user.id,
            account_id=payload.account_id,
            title=title,
            description=description,
            location=payload.venue,
            start_at=start_at,
            end_at=end_at,
            attendees=[],
            is_all_day=False,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Sports calendar sync failed: {exc}")

    return SportsCalendarEventCreateResponse(status="created", event=event)
