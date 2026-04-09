"""WhatsApp OpenClaw API routes."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.db import get_db
from app.models import ConnectedAccount, User
from app.schemas.whatsapp import (
    WhatsAppConversationListResponse,
    WhatsAppConversationMessage,
    WhatsAppConversationMessagesResponse,
    WhatsAppConversationSummary,
    WhatsAppSendRequest,
    WhatsAppSendResponse,
    WhatsAppSyncRequest,
    WhatsAppSyncResponse,
    WhatsAppStatusResponse,
)
from app.services.chat_sync_service import ChatSyncService
from app.services.whatsapp_service import WhatsAppService

router = APIRouter(prefix="/whatsapp", tags=["whatsapp"])


def _get_whatsapp_account(
    *,
    db: Session,
    user: User,
    account_id: UUID | None = None,
) -> ConnectedAccount | None:
    stmt = select(ConnectedAccount).where(
        ConnectedAccount.user_id == user.id,
        ConnectedAccount.provider == "whatsapp",
    )
    if account_id:
        stmt = stmt.where(ConnectedAccount.id == account_id)
    return db.execute(stmt).scalar_one_or_none()


@router.get("/status", response_model=WhatsAppStatusResponse)
def whatsapp_status(
    account_id: UUID | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WhatsAppStatusResponse:
    account = _get_whatsapp_account(db=db, user=current_user, account_id=account_id)
    svc = WhatsAppService(db, account_id=account.provider_account_id if account else None)
    return WhatsAppStatusResponse(**svc.status())


@router.get("/conversations", response_model=WhatsAppConversationListResponse)
def whatsapp_conversations(
    account_id: UUID | None = Query(None),
    unread_only: bool = Query(False),
    search: str | None = Query(None),
    limit: int = Query(5000, ge=1, le=50000),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WhatsAppConversationListResponse:
    account = _get_whatsapp_account(db=db, user=current_user, account_id=account_id)
    if account is None:
        return WhatsAppConversationListResponse(conversations=[], total=0)

    sync = ChatSyncService(db)
    try:
        items = sync.list_whatsapp_conversations(
            user_id=current_user.id,
            account_id=account.id,
            unread_only=unread_only,
            search=search,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"WhatsApp API failed: {exc}",
        )
    conversations = [
        WhatsAppConversationSummary(
            account_id=account.id,
            conversation_id=item["conversation_id"],
            sender=item["sender"],
            preview=item.get("preview"),
            unread_count=int(item.get("unread_count") or 0),
            message_count=int(item.get("message_count") or 0),
            has_attachments=bool(item.get("has_attachments")),
            latest_received_at=item.get("latest_received_at"),
            is_group=bool(item.get("is_group")),
        )
        for item in items
    ]
    return WhatsAppConversationListResponse(conversations=conversations, total=len(conversations))


@router.get(
    "/conversations/{chat_jid}/messages",
    response_model=WhatsAppConversationMessagesResponse,
)
def whatsapp_conversation_messages(
    chat_jid: str,
    account_id: UUID | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WhatsAppConversationMessagesResponse:
    account = _get_whatsapp_account(db=db, user=current_user, account_id=account_id)
    if account is None:
        return WhatsAppConversationMessagesResponse(messages=[], total=0)

    sync = ChatSyncService(db)
    try:
        items = sync.list_whatsapp_messages(
            user_id=current_user.id,
            account_id=account.id,
            conversation_id=chat_jid,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"WhatsApp API failed: {exc}",
        )
    messages = [WhatsAppConversationMessage(**item) for item in items]
    return WhatsAppConversationMessagesResponse(messages=messages, total=len(messages))


@router.post("/send", response_model=WhatsAppSendResponse)
def whatsapp_send(
    payload: WhatsAppSendRequest,
    account_id: UUID | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WhatsAppSendResponse:
    account = _get_whatsapp_account(db=db, user=current_user, account_id=account_id)
    if account is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No WhatsApp account connected.",
        )
    sync = ChatSyncService(db)
    try:
        result = sync.send_whatsapp_message(
            user_id=current_user.id,
            account_id=account.id,
            to=payload.to,
            text=payload.text,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"WhatsApp API failed: {exc}",
        )
    return WhatsAppSendResponse(
        status="sent",
        to=str(result.get("to") or payload.to),
        message_id=(str(result.get("message_id")) if result.get("message_id") else None),
    )


@router.post("/sync", response_model=WhatsAppSyncResponse)
def whatsapp_sync(
    payload: WhatsAppSyncRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WhatsAppSyncResponse:
    account = _get_whatsapp_account(
        db=db,
        user=current_user,
        account_id=payload.account_id,
    )
    if account is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No WhatsApp account connected.",
        )

    sync = ChatSyncService(db)
    try:
        result = sync.sync_whatsapp_ingestion(
            user_id=current_user.id,
            account_id=account.id,
            unread_only=payload.unread_only,
            search=payload.search,
            conversation_limit=payload.conversation_limit,
            message_limit=payload.message_limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"WhatsApp API failed: {exc}",
        )

    return WhatsAppSyncResponse(
        status="ok",
        conversations_discovered=int(result.get("conversations_discovered") or 0),
        conversations_synced=int(result.get("conversations_synced") or 0),
        messages_synced=int(result.get("messages_synced") or 0),
        failures=result.get("failures") or [],
    )
