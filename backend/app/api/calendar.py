"""Calendar API routes."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.db import get_db
from app.models import User
from app.schemas.calendar import (
    CalendarEventListResponse,
    CalendarEventCreateRequest,
    CalendarEventCreateResponse,
    FreeBusyRequest,
    FreeBusyResponse,
    SuggestSlotsRequest,
    SuggestSlotsResponse,
)
from app.services.calendar_service import CalendarService

router = APIRouter(prefix="/calendar", tags=["calendar"])


@router.get("/events", response_model=CalendarEventListResponse)
async def list_calendar_events(
    account_id: UUID | None = Query(None),
    start_at: datetime | None = Query(None),
    end_at: datetime | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CalendarEventListResponse:
    now = datetime.now(timezone.utc)
    start = start_at or now
    end = end_at or (start + timedelta(days=14))

    svc = CalendarService(db)
    try:
        events = await svc.list_events(
            user_id=current_user.id,
            account_id=account_id,
            start_at=start,
            end_at=end,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Calendar API failed: {exc}")

    sliced = events[:limit]
    return CalendarEventListResponse(events=sliced, total=len(events))


@router.post("/events", response_model=CalendarEventCreateResponse)
async def create_calendar_event(
    payload: CalendarEventCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CalendarEventCreateResponse:
    if payload.end_at <= payload.start_at:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Event end_at must be after start_at.",
        )

    svc = CalendarService(db)
    try:
        event = await svc.create_event(
            user_id=current_user.id,
            account_id=payload.account_id,
            title=payload.title,
            description=payload.description,
            location=payload.location,
            start_at=payload.start_at,
            end_at=payload.end_at,
            attendees=payload.attendees,
            is_all_day=payload.is_all_day,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Calendar API failed: {exc}")

    return CalendarEventCreateResponse(event=event)


@router.post("/freebusy", response_model=FreeBusyResponse)
async def get_freebusy(
    payload: FreeBusyRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FreeBusyResponse:
    svc = CalendarService(db)
    try:
        busy = await svc.freebusy(
            user_id=current_user.id,
            account_id=payload.account_id,
            start_at=payload.start_at,
            end_at=payload.end_at,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Calendar API failed: {exc}")

    return FreeBusyResponse(busy=busy)


@router.post("/suggest-slots", response_model=SuggestSlotsResponse)
async def suggest_slots(
    payload: SuggestSlotsRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SuggestSlotsResponse:
    svc = CalendarService(db)
    try:
        slots = await svc.suggest_slots(
            user_id=current_user.id,
            account_id=payload.account_id,
            date=payload.date,
            duration_minutes=payload.duration_minutes,
            count=payload.count,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Calendar API failed: {exc}")

    return SuggestSlotsResponse(slots=slots)
