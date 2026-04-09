"""Teams API routes."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.db import get_db
from app.models import User
from app.schemas.teams import (
    TeamsConversationListResponse,
    TeamsMessageListResponse,
    TeamsPresenceResponse,
    TeamsSendRequest,
    TeamsSendResponse,
)
from app.services.chat_sync_service import ChatSyncService
from app.services.teams_service import TeamsService

router = APIRouter(prefix="/teams", tags=["teams"])


@router.get("/conversations", response_model=TeamsConversationListResponse)
def list_teams_conversations(
    account_id: UUID | None = Query(None),
    unread_only: bool = Query(False),
    search: str | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TeamsConversationListResponse:
    svc = ChatSyncService(db)
    try:
        conversations = svc.list_teams_conversations(
            user_id=current_user.id,
            account_id=account_id,
            unread_only=unread_only,
            search=search,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Teams API failed: {exc}")
    return TeamsConversationListResponse(conversations=conversations, total=len(conversations))


@router.get("/conversations/{conversation_id}/messages", response_model=TeamsMessageListResponse)
def list_teams_messages(
    conversation_id: str,
    account_id: UUID | None = Query(None),
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TeamsMessageListResponse:
    svc = ChatSyncService(db)
    try:
        messages = svc.list_teams_messages(
            user_id=current_user.id,
            conversation_id=conversation_id,
            account_id=account_id,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Teams API failed: {exc}")
    return TeamsMessageListResponse(messages=messages, total=len(messages))


@router.post("/send", response_model=TeamsSendResponse)
def send_teams_message(
    payload: TeamsSendRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TeamsSendResponse:
    if not payload.text.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Message text cannot be empty")

    svc = ChatSyncService(db)
    try:
        result = svc.send_teams_message(
            user_id=current_user.id,
            conversation_id=payload.conversation_id,
            text=payload.text,
            account_id=payload.account_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Teams API failed: {exc}")

    return TeamsSendResponse(
        status="sent",
        conversation_id=result["conversation_id"],
        message_id=result.get("message_id"),
    )


@router.get("/presence", response_model=TeamsPresenceResponse)
def get_teams_presence(
    account_id: UUID | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TeamsPresenceResponse:
    svc = TeamsService(db)
    try:
        return svc.get_presence(user_id=current_user.id, account_id=account_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Teams API failed: {exc}")
