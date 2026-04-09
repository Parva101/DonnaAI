import hashlib
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.message import Message
from app.models.raw_event import RawEvent
from app.schemas.ingest import IngestEventRequest
from app.services.permission_service import get_permission_scope


class IngestPolicyError(Exception):
    pass


def _payload_hash(payload: dict) -> str:
    digest = hashlib.sha256()
    digest.update(str(payload).encode("utf-8"))
    return digest.hexdigest()


def _resolve_chat_key(payload: dict) -> str | None:
    for key in ("chat_key", "thread_key", "chat_id", "conversation_id"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _resolve_source_message_id(payload: dict, fallback: str) -> str:
    for key in ("source_message_id", "message_id", "id"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return fallback


def ingest_event(db: Session, payload: IngestEventRequest) -> tuple[RawEvent, bool, Message | None]:
    chat_key = _resolve_chat_key(payload.payload)
    if chat_key:
        scope = get_permission_scope(db, payload.tenant_id, payload.platform, payload.account_id, chat_key)
        if scope is None or not scope.read_allowed:
            raise IngestPolicyError(
                f"Ingest blocked: read scope is disabled for {payload.platform}:{payload.account_id}:{chat_key}"
            )

    existing_stmt = select(RawEvent).where(
        RawEvent.tenant_id == payload.tenant_id,
        RawEvent.platform == payload.platform,
        RawEvent.account_id == payload.account_id,
        RawEvent.source_event_id == payload.source_event_id,
    )
    existing = db.scalar(existing_stmt)
    if existing is not None:
        return existing, False, None

    raw_event = RawEvent(
        tenant_id=payload.tenant_id,
        platform=payload.platform,
        account_id=payload.account_id,
        event_type=payload.event_type,
        source_event_id=payload.source_event_id,
        occurred_at=payload.occurred_at,
        payload_json=payload.payload,
        payload_hash=_payload_hash(payload.payload),
        received_at=datetime.now(timezone.utc),
        ingested_at=datetime.now(timezone.utc),
    )
    db.add(raw_event)

    normalized_message: Message | None = None
    if payload.event_type in {"message.received", "message.sent"} and chat_key:
        source_message_id = _resolve_source_message_id(payload.payload, payload.source_event_id)
        message_exists_stmt = select(Message).where(
            Message.tenant_id == payload.tenant_id,
            Message.platform == payload.platform,
            Message.account_id == payload.account_id,
            Message.source_message_id == source_message_id,
        )
        message_exists = db.scalar(message_exists_stmt)
        if message_exists is None:
            normalized_message = Message(
                tenant_id=payload.tenant_id,
                platform=payload.platform,
                account_id=payload.account_id,
                thread_key=payload.payload.get("thread_key") or chat_key,
                chat_key=chat_key,
                source_message_id=source_message_id,
                sender_key=payload.payload.get("sender_key"),
                body_text=payload.payload.get("body_text"),
                body_redacted=payload.payload.get("body_redacted") or payload.payload.get("body_text"),
                metadata_json=payload.payload.get("metadata"),
                sent_at=payload.payload.get("sent_at") or payload.occurred_at,
            )
            db.add(normalized_message)

    db.commit()
    db.refresh(raw_event)
    if normalized_message is not None:
        db.refresh(normalized_message)
    return raw_event, True, normalized_message

