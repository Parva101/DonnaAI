"""Notification preferences and digest APIs."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.db import get_db
from app.models import User
from app.schemas.notifications import (
    DailyDigestResponse,
    NotificationPreferencesResponse,
    NotificationPreferencesUpdate,
)
from app.services.notification_service import NotificationService

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("/preferences", response_model=NotificationPreferencesResponse)
def get_preferences(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> NotificationPreferencesResponse:
    svc = NotificationService(db)
    prefs = svc.get_preferences(user_id=current_user.id)
    return NotificationPreferencesResponse(preferences=prefs)


@router.patch("/preferences", response_model=NotificationPreferencesResponse)
def update_preferences(
    payload: NotificationPreferencesUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> NotificationPreferencesResponse:
    svc = NotificationService(db)
    try:
        prefs = svc.update_preferences(
            user_id=current_user.id,
            patch=payload.model_dump(exclude_unset=True),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return NotificationPreferencesResponse(preferences=prefs)


@router.get("/digest", response_model=DailyDigestResponse)
def get_digest(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DailyDigestResponse:
    svc = NotificationService(db)
    summary, items = svc.build_daily_digest(user_id=current_user.id)
    return DailyDigestResponse(
        generated_at=svc.generated_at(),
        summary=summary,
        top_items=items,
    )
