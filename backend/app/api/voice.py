"""Voice call API routes."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.db import get_db
from app.models import User
from app.schemas.voice import VoiceCallCreate, VoiceCallListResponse, VoiceCallRead
from app.services.voice_service import VoiceService

router = APIRouter(prefix="/voice", tags=["voice"])


def _to_call_read(call) -> VoiceCallRead:
    return VoiceCallRead(
        id=call.id,
        user_id=call.user_id,
        target_name=call.target_name,
        target_phone=call.target_phone,
        intent=call.intent,
        status=call.status,
        transcript=call.transcript,
        summary=call.summary,
        outcome=call.outcome,
        started_at=call.started_at,
        completed_at=call.completed_at,
        created_at=call.created_at,
        updated_at=call.updated_at,
    )


@router.post("/calls", response_model=VoiceCallRead)
def create_call(
    payload: VoiceCallCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> VoiceCallRead:
    if not payload.intent.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Call intent cannot be empty")

    svc = VoiceService(db)
    call = svc.create_call(
        user_id=current_user.id,
        intent=payload.intent,
        target_name=payload.target_name,
        target_phone=payload.target_phone,
    )
    return _to_call_read(call)


@router.get("/calls", response_model=VoiceCallListResponse)
def list_calls(
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> VoiceCallListResponse:
    svc = VoiceService(db)
    calls = svc.list_calls(user_id=current_user.id, limit=limit)
    return VoiceCallListResponse(calls=[_to_call_read(c) for c in calls], total=len(calls))


@router.get("/calls/{call_id}", response_model=VoiceCallRead)
def get_call(
    call_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> VoiceCallRead:
    svc = VoiceService(db)
    call = svc.get_call(user_id=current_user.id, call_id=call_id)
    if not call:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Call not found")
    return _to_call_read(call)
