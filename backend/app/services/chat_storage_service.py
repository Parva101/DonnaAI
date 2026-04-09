"""Canonical storage helpers for cross-platform chat ingestion and actions."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import and_, case, select
from sqlalchemy.orm import Session

from app.models import ChatConversation, ChatMessage, ChatOutboundAction


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ChatStorageService:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def _stable_message_id(
        *,
        platform: str,
        conversation_id: str,
        sender: str | None,
        text: str | None,
        sent_at: datetime | None,
        fallback_seed: str,
    ) -> str:
        payload = {
            "platform": platform,
            "conversation_id": conversation_id,
            "sender": sender,
            "text": text,
            "sent_at": sent_at.isoformat() if sent_at else None,
            "fallback_seed": fallback_seed,
        }
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=True).encode("utf-8")).hexdigest()
        return f"auto-{digest[:24]}"

    def upsert_conversation(
        self,
        *,
        user_id: UUID,
        account_id: UUID,
        platform: str,
        external_conversation_id: str,
        name: str | None = None,
        sender: str | None = None,
        preview: str | None = None,
        unread_count: int = 0,
        message_count: int = 0,
        has_attachments: bool = False,
        latest_received_at: datetime | None = None,
        is_group: bool = False,
        is_im: bool = False,
        is_private: bool = False,
        metadata: dict | None = None,
        commit: bool = False,
    ) -> ChatConversation:
        existing = self.db.execute(
            select(ChatConversation).where(
                ChatConversation.user_id == user_id,
                ChatConversation.account_id == account_id,
                ChatConversation.platform == platform,
                ChatConversation.external_conversation_id == external_conversation_id,
            )
        ).scalar_one_or_none()

        if existing:
            if name is not None:
                existing.name = name
            if sender is not None:
                existing.sender = sender
            if preview is not None:
                existing.preview = preview
            existing.unread_count = max(int(unread_count or 0), 0)
            existing.message_count = max(int(message_count or 0), existing.message_count, 0)
            existing.has_attachments = bool(has_attachments)
            if latest_received_at is not None:
                existing.latest_received_at = latest_received_at
            existing.is_group = bool(is_group)
            existing.is_im = bool(is_im)
            existing.is_private = bool(is_private)
            if metadata is not None:
                existing.conversation_metadata = metadata
            row = existing
        else:
            row = ChatConversation(
                user_id=user_id,
                account_id=account_id,
                platform=platform,
                external_conversation_id=external_conversation_id,
                name=name,
                sender=sender,
                preview=preview,
                unread_count=max(int(unread_count or 0), 0),
                message_count=max(int(message_count or 0), 0),
                has_attachments=bool(has_attachments),
                latest_received_at=latest_received_at,
                is_group=bool(is_group),
                is_im=bool(is_im),
                is_private=bool(is_private),
                conversation_metadata=metadata,
            )
            self.db.add(row)

        if commit:
            self.db.commit()
        else:
            self.db.flush()
        return row

    def list_conversations(
        self,
        *,
        user_id: UUID,
        platform: str | None = None,
        account_id: UUID | None = None,
        search: str | None = None,
        unread_only: bool = False,
        limit: int = 500,
    ) -> list[ChatConversation]:
        stmt = select(ChatConversation).where(ChatConversation.user_id == user_id)
        if platform:
            stmt = stmt.where(ChatConversation.platform == platform)
        if account_id:
            stmt = stmt.where(ChatConversation.account_id == account_id)
        if unread_only:
            stmt = stmt.where(ChatConversation.unread_count > 0)
        if search:
            pattern = f"%{search.strip()}%"
            stmt = stmt.where(
                ChatConversation.sender.ilike(pattern)
                | ChatConversation.name.ilike(pattern)
                | ChatConversation.preview.ilike(pattern)
                | ChatConversation.external_conversation_id.ilike(pattern)
            )
        nulls_last_sort = case((ChatConversation.latest_received_at.is_(None), 1), else_=0)
        stmt = stmt.order_by(
            nulls_last_sort.asc(),
            ChatConversation.latest_received_at.desc(),
            ChatConversation.updated_at.desc(),
        ).limit(max(limit, 1))
        return list(self.db.execute(stmt).scalars())

    def upsert_message(
        self,
        *,
        conversation: ChatConversation,
        sender: str | None,
        sender_id: str | None,
        text: str | None,
        direction: str,
        subtype: str | None,
        thread_ref: str | None,
        has_attachments: bool,
        sent_at: datetime | None,
        raw_payload: dict | None,
        external_message_id: str | None = None,
        fallback_seed: str = "",
        commit: bool = False,
    ) -> ChatMessage:
        message_external_id = (external_message_id or "").strip()
        if not message_external_id:
            message_external_id = self._stable_message_id(
                platform=conversation.platform,
                conversation_id=conversation.external_conversation_id,
                sender=sender,
                text=text,
                sent_at=sent_at,
                fallback_seed=fallback_seed or str(uuid4()),
            )

        existing = self.db.execute(
            select(ChatMessage).where(
                and_(
                    ChatMessage.conversation_id == conversation.id,
                    ChatMessage.external_message_id == message_external_id,
                )
            )
        ).scalar_one_or_none()

        if existing:
            existing.sender = sender
            existing.sender_id = sender_id
            existing.text = text
            existing.direction = direction
            existing.subtype = subtype
            existing.thread_ref = thread_ref
            existing.has_attachments = bool(has_attachments)
            existing.sent_at = sent_at
            existing.raw_payload = raw_payload
            row = existing
        else:
            row = ChatMessage(
                conversation_id=conversation.id,
                user_id=conversation.user_id,
                account_id=conversation.account_id,
                platform=conversation.platform,
                external_message_id=message_external_id,
                sender=sender,
                sender_id=sender_id,
                text=text,
                direction=direction,
                subtype=subtype,
                thread_ref=thread_ref,
                has_attachments=bool(has_attachments),
                sent_at=sent_at,
                raw_payload=raw_payload,
            )
            self.db.add(row)
            conversation.message_count = max(int(conversation.message_count or 0) + 1, 1)
            if sent_at and (
                conversation.latest_received_at is None
                or sent_at > conversation.latest_received_at
            ):
                conversation.latest_received_at = sent_at
        if commit:
            self.db.commit()
        else:
            self.db.flush()
        return row

    def list_messages(
        self,
        *,
        user_id: UUID,
        platform: str,
        conversation_external_id: str,
        account_id: UUID | None = None,
        limit: int = 200,
    ) -> list[ChatMessage]:
        filters = [
            ChatConversation.user_id == user_id,
            ChatConversation.platform == platform,
            ChatConversation.external_conversation_id == conversation_external_id,
        ]
        if account_id:
            filters.append(ChatConversation.account_id == account_id)

        conversation = self.db.execute(
            select(ChatConversation).where(*filters)
        ).scalar_one_or_none()

        if not conversation:
            return []

        stmt = (
            select(ChatMessage)
            .where(ChatMessage.conversation_id == conversation.id)
            .order_by(ChatMessage.sent_at.asc().nullslast(), ChatMessage.created_at.asc())
            .limit(max(limit, 1))
        )
        return list(self.db.execute(stmt).scalars())

    def record_outbound_action(
        self,
        *,
        user_id: UUID,
        account_id: UUID,
        platform: str,
        target: str,
        request_text: str,
        request_payload: dict | None,
        idempotency_key: str,
        conversation: ChatConversation | None = None,
        action_type: str = "send",
        status: str = "queued",
        provider_message_id: str | None = None,
        error: str | None = None,
        sent_at: datetime | None = None,
    ) -> ChatOutboundAction:
        existing = self.db.execute(
            select(ChatOutboundAction).where(ChatOutboundAction.idempotency_key == idempotency_key)
        ).scalar_one_or_none()
        if existing:
            return existing

        row = ChatOutboundAction(
            user_id=user_id,
            account_id=account_id,
            conversation_id=conversation.id if conversation else None,
            platform=platform,
            action_type=action_type,
            target=target,
            request_text=request_text,
            request_payload=request_payload,
            idempotency_key=idempotency_key,
            status=status,
            provider_message_id=provider_message_id,
            error=error,
            sent_at=sent_at,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def update_outbound_action(
        self,
        *,
        idempotency_key: str,
        status: str,
        provider_message_id: str | None = None,
        error: str | None = None,
    ) -> None:
        row = self.db.execute(
            select(ChatOutboundAction).where(ChatOutboundAction.idempotency_key == idempotency_key)
        ).scalar_one_or_none()
        if not row:
            return
        row.status = status
        row.provider_message_id = provider_message_id
        row.error = error
        if status == "sent":
            row.sent_at = _utc_now()
        self.db.flush()
