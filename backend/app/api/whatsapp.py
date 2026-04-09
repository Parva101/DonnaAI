"""WhatsApp bridge API routes."""

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
    WhatsAppMessagesResponse,
    WhatsAppMessage,
    WhatsAppSendRequest,
    WhatsAppSendResponse,
    WhatsAppStatusResponse,
)
from app.services.whatsapp_bridge_service import WhatsAppBridgeService

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
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WhatsAppStatusResponse:
    del current_user
    svc = WhatsAppBridgeService(db)
    return WhatsAppStatusResponse(**svc.status())


@router.get("/messages", response_model=WhatsAppMessagesResponse)
def whatsapp_messages(
    limit: int = Query(100, ge=1, le=500),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WhatsAppMessagesResponse:
    account = _get_whatsapp_account(db=db, user=current_user)
    if account is None:
        return WhatsAppMessagesResponse(messages=[])
    svc = WhatsAppBridgeService(db)
    rows = svc.list_messages(limit=limit)
    return WhatsAppMessagesResponse(messages=[WhatsAppMessage(**row) for row in rows])


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

    svc = WhatsAppBridgeService(db)
    items = svc.list_conversations(limit=limit, search=search, unread_only=unread_only)
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

    svc = WhatsAppBridgeService(db)
    items = svc.list_conversation_messages(chat_jid=chat_jid, limit=limit)
    messages = [WhatsAppConversationMessage(**item) for item in items]
    return WhatsAppConversationMessagesResponse(messages=messages, total=len(messages))


@router.post("/send", response_model=WhatsAppSendResponse)
def whatsapp_send(
    payload: WhatsAppSendRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WhatsAppSendResponse:
    account = _get_whatsapp_account(db=db, user=current_user)
    if account is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No WhatsApp account connected.",
        )
    svc = WhatsAppBridgeService(db)
    svc.send_message(to=payload.to, text=payload.text)
    return WhatsAppSendResponse(status="sent")
