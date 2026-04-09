"""Unified inbox API routes across Gmail, Slack, and WhatsApp."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.db import get_db
from app.models import User
from app.schemas.inbox import ChatIngestionSyncRequest, ChatIngestionSyncResponse, InboxConversationListResponse
from app.services.chat_sync_service import ChatSyncService
from app.services.inbox_service import InboxService


router = APIRouter(prefix="/inbox", tags=["inbox"])


@router.get("/conversations", response_model=InboxConversationListResponse)
def list_conversations(
    platform: str | None = Query(
        None,
        description="Platform filter (supports: gmail, slack, whatsapp, teams)",
    ),
    account_id: UUID | None = Query(
        None,
        description="Filter by connected account",
    ),
    unread_only: bool = Query(
        False,
        description="Only include conversations with unread messages",
    ),
    search: str | None = Query(
        None,
        description="Search sender, subject, snippet",
    ),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> InboxConversationListResponse:
    svc = InboxService(db)
    conversations, total = svc.list_conversations(
        current_user.id,
        platform=platform,
        account_id=account_id,
        unread_only=unread_only,
        search=search,
        limit=limit,
        offset=offset,
    )
    platform_counts = svc.get_platform_counts(
        current_user.id,
        account_id=account_id,
        search=search,
    )
    return InboxConversationListResponse(
        conversations=conversations,
        total=total,
        platform_counts=platform_counts,
    )


@router.post("/sync/chats", response_model=ChatIngestionSyncResponse)
def sync_chat_ingestion(
    payload: ChatIngestionSyncRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ChatIngestionSyncResponse:
    sync = ChatSyncService(db)
    try:
        result = sync.sync_ingestion(
            user_id=current_user.id,
            platform=payload.platform,
            account_id=payload.account_id,
            conversation_limit=payload.conversation_limit,
            message_limit=payload.message_limit,
            unread_only=payload.unread_only,
            search=payload.search,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Chat sync failed: {exc}",
        )
    return ChatIngestionSyncResponse(
        status="ok",
        platform=str(result.get("platform") or payload.platform).lower(),
        totals=result.get("totals") or {},
        results=result.get("results") or [],
    )
