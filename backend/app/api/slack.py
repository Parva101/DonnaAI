"""Slack API routes for connected workspace access."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.db import get_db
from app.models import User
from app.schemas.slack import (
    SlackConversationListResponse,
    SlackMessageListResponse,
    SlackSendRequest,
    SlackSendResponse,
)
from app.services.chat_sync_service import ChatSyncService

router = APIRouter(prefix="/slack", tags=["slack"])


@router.get("/conversations", response_model=SlackConversationListResponse)
def list_slack_conversations(
    account_id: UUID | None = Query(None),
    unread_only: bool = Query(False),
    search: str | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SlackConversationListResponse:
    svc = ChatSyncService(db)
    try:
        conversations = svc.list_slack_conversations(
            user_id=current_user.id,
            account_id=account_id,
            search=search,
            unread_only=unread_only,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Slack API failed: {exc}",
        )
    return SlackConversationListResponse(conversations=conversations, total=len(conversations))


@router.get("/conversations/{conversation_id}/messages", response_model=SlackMessageListResponse)
def list_slack_messages(
    conversation_id: str,
    account_id: UUID | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SlackMessageListResponse:
    svc = ChatSyncService(db)
    try:
        messages = svc.list_slack_messages(
            user_id=current_user.id,
            conversation_id=conversation_id,
            account_id=account_id,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Slack API failed: {exc}",
        )
    return SlackMessageListResponse(messages=messages, total=len(messages))


@router.post("/send", response_model=SlackSendResponse)
def send_slack_message(
    payload: SlackSendRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SlackSendResponse:
    svc = ChatSyncService(db)
    try:
        result = svc.send_slack_message(
            user_id=current_user.id,
            conversation_id=payload.conversation_id,
            text=payload.text,
            account_id=payload.account_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Slack API failed: {exc}",
        )
    return SlackSendResponse(status="sent", channel=result["channel"], ts=result["ts"])
