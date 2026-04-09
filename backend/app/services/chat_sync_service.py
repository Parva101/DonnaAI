"""Orchestrates platform fetch/send + canonical DB persistence for chats."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi.encoders import jsonable_encoder
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ConnectedAccount
from app.schemas.slack import SlackConversationSummary, SlackMessage
from app.schemas.teams import TeamsConversationSummary, TeamsMessage
from app.services.chat_storage_service import ChatStorageService
from app.services.slack_service import SlackService
from app.services.teams_service import TeamsService
from app.services.whatsapp_service import WhatsAppService

logger = logging.getLogger(__name__)


class ChatSyncService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.storage = ChatStorageService(db)
        self.slack = SlackService(db)
        self.teams = TeamsService(db)

    def _resolve_account(
        self,
        *,
        user_id: UUID,
        provider: str,
        account_id: UUID | None = None,
    ) -> ConnectedAccount | None:
        stmt = select(ConnectedAccount).where(
            ConnectedAccount.user_id == user_id,
            ConnectedAccount.provider == provider,
        )
        if account_id:
            stmt = stmt.where(ConnectedAccount.id == account_id)
        stmt = stmt.order_by(ConnectedAccount.created_at.desc())
        return self.db.execute(stmt).scalars().first()

    @staticmethod
    def _parse_slack_ts(ts: str | None) -> datetime | None:
        if not ts:
            return None
        try:
            return datetime.fromtimestamp(float(ts), tz=timezone.utc)
        except Exception:
            return None

    def _persist_slack_conversations(
        self,
        *,
        user_id: UUID,
        conversations: list[SlackConversationSummary],
    ) -> None:
        for item in conversations:
            self.storage.upsert_conversation(
                user_id=user_id,
                account_id=item.account_id,
                platform="slack",
                external_conversation_id=item.conversation_id,
                name=item.name,
                sender=item.sender,
                preview=item.preview,
                unread_count=item.unread_count,
                message_count=item.message_count,
                has_attachments=item.has_attachments,
                latest_received_at=item.latest_received_at,
                is_group=not item.is_im,
                is_im=item.is_im,
                is_private=item.is_private,
                metadata={"source": "connector_sync"},
            )

    @staticmethod
    def _as_slack_conversations(rows: list[SlackConversationSummary | dict]) -> list[SlackConversationSummary]:
        normalized: list[SlackConversationSummary] = []
        for row in rows:
            if isinstance(row, SlackConversationSummary):
                normalized.append(row)
            else:
                normalized.append(SlackConversationSummary.model_validate(row))
        return normalized

    def _persist_slack_messages(
        self,
        *,
        user_id: UUID,
        account_id: UUID,
        conversation_id: str,
        messages: list[SlackMessage],
    ) -> None:
        latest = messages[-1] if messages else None
        conversation = self.storage.upsert_conversation(
            user_id=user_id,
            account_id=account_id,
            platform="slack",
            external_conversation_id=conversation_id,
            sender=latest.sender if latest else "Slack",
            preview=latest.text if latest else None,
            latest_received_at=self._parse_slack_ts(latest.ts) if latest else None,
            metadata={"source": "connector_sync"},
        )
        for index, msg in enumerate(messages):
            self.storage.upsert_message(
                conversation=conversation,
                external_message_id=msg.ts,
                sender=msg.sender,
                sender_id=msg.user_id,
                text=msg.text,
                direction="outbound" if (msg.sender or "").strip().lower() == "you" else "inbound",
                subtype=msg.subtype,
                thread_ref=msg.thread_ts,
                has_attachments=msg.has_attachments,
                sent_at=self._parse_slack_ts(msg.ts),
                raw_payload=msg.model_dump(mode="json"),
                fallback_seed=f"{conversation_id}:{index}",
            )

    @staticmethod
    def _as_slack_messages(rows: list[SlackMessage | dict]) -> list[SlackMessage]:
        normalized: list[SlackMessage] = []
        for row in rows:
            if isinstance(row, SlackMessage):
                normalized.append(row)
            else:
                normalized.append(SlackMessage.model_validate(row))
        return normalized

    def _fallback_slack_conversations(
        self,
        *,
        user_id: UUID,
        account_id: UUID | None,
        search: str | None,
        unread_only: bool,
    ) -> list[SlackConversationSummary]:
        rows = self.storage.list_conversations(
            user_id=user_id,
            platform="slack",
            account_id=account_id,
            search=search,
            unread_only=unread_only,
            limit=1000,
        )
        return [
            SlackConversationSummary(
                account_id=row.account_id,
                conversation_id=row.external_conversation_id,
                name=row.name,
                sender=row.sender or "Slack",
                preview=row.preview,
                unread_count=max(int(row.unread_count or 0), 0),
                message_count=max(int(row.message_count or 0), 0),
                has_attachments=bool(row.has_attachments),
                latest_received_at=row.latest_received_at,
                is_im=bool(row.is_im),
                is_private=bool(row.is_private),
            )
            for row in rows
        ]

    def _fallback_slack_messages(
        self,
        *,
        user_id: UUID,
        account_id: UUID | None,
        conversation_id: str,
        limit: int,
    ) -> list[SlackMessage]:
        rows = self.storage.list_messages(
            user_id=user_id,
            platform="slack",
            conversation_external_id=conversation_id,
            account_id=account_id,
            limit=limit,
        )
        return [
            SlackMessage(
                ts=row.external_message_id,
                sender=row.sender,
                user_id=row.sender_id,
                text=row.text,
                subtype=row.subtype,
                thread_ts=row.thread_ref,
                has_attachments=bool(row.has_attachments),
            )
            for row in rows
        ]

    def list_slack_conversations(
        self,
        *,
        user_id: UUID,
        account_id: UUID | None,
        search: str | None,
        unread_only: bool,
    ) -> list[SlackConversationSummary]:
        try:
            rows = self.slack.list_conversations(
                user_id=user_id,
                account_id=account_id,
                search=search,
                unread_only=unread_only,
            )
            normalized = self._as_slack_conversations(rows)
            self._persist_slack_conversations(user_id=user_id, conversations=normalized)
            self.db.commit()
            return normalized
        except Exception as exc:
            self.db.rollback()
            logger.warning("Slack sync failed, using persisted fallback: %s", exc)
            fallback = self._fallback_slack_conversations(
                user_id=user_id,
                account_id=account_id,
                search=search,
                unread_only=unread_only,
            )
            if fallback:
                return fallback
            raise

    def list_slack_messages(
        self,
        *,
        user_id: UUID,
        conversation_id: str,
        account_id: UUID | None,
        limit: int,
    ) -> list[SlackMessage]:
        try:
            rows = self.slack.list_messages(
                user_id=user_id,
                conversation_id=conversation_id,
                account_id=account_id,
                limit=limit,
            )
            normalized = self._as_slack_messages(rows)
            account = self._resolve_account(user_id=user_id, provider="slack", account_id=account_id)
            if account:
                self._persist_slack_messages(
                    user_id=user_id,
                    account_id=account.id,
                    conversation_id=conversation_id,
                    messages=normalized,
                )
                self.db.commit()
            return normalized
        except Exception as exc:
            self.db.rollback()
            logger.warning("Slack message sync failed, using persisted fallback: %s", exc)
            fallback = self._fallback_slack_messages(
                user_id=user_id,
                account_id=account_id,
                conversation_id=conversation_id,
                limit=limit,
            )
            if fallback:
                return fallback
            raise

    def send_slack_message(
        self,
        *,
        user_id: UUID,
        conversation_id: str,
        account_id: UUID | None,
        text: str,
    ) -> dict:
        account = self._resolve_account(user_id=user_id, provider="slack", account_id=account_id)
        if not account:
            raise ValueError("No Slack account connected.")

        idempotency_key = f"slack:{account.id}:{uuid4()}"
        conversation = self.storage.upsert_conversation(
            user_id=user_id,
            account_id=account.id,
            platform="slack",
            external_conversation_id=conversation_id,
            sender="Slack",
            preview=text,
            latest_received_at=_utcnow(),
            metadata={"source": "send"},
        )
        self.storage.record_outbound_action(
            user_id=user_id,
            account_id=account.id,
            platform="slack",
            target=conversation_id,
            request_text=text,
            request_payload={"conversation_id": conversation_id, "text": text},
            idempotency_key=idempotency_key,
            conversation=conversation,
            status="queued",
        )
        self.db.flush()

        try:
            result = self.slack.send_message(
                user_id=user_id,
                conversation_id=conversation_id,
                text=text,
                account_id=account_id,
            )
            provider_message_id = str(result.get("ts") or "")
            self.storage.update_outbound_action(
                idempotency_key=idempotency_key,
                status="sent",
                provider_message_id=provider_message_id,
            )
            self.storage.upsert_message(
                conversation=conversation,
                external_message_id=provider_message_id or None,
                sender="You",
                sender_id=None,
                text=text,
                direction="outbound",
                subtype=None,
                thread_ref=None,
                has_attachments=False,
                sent_at=self._parse_slack_ts(provider_message_id) or _utcnow(),
                raw_payload={"provider_result": result},
                fallback_seed=idempotency_key,
            )
            conversation.preview = text
            self.db.commit()
            return result
        except Exception as exc:
            self.storage.update_outbound_action(
                idempotency_key=idempotency_key,
                status="failed",
                error=str(exc),
            )
            self.db.commit()
            raise

    def _persist_teams_conversations(
        self,
        *,
        user_id: UUID,
        conversations: list[TeamsConversationSummary],
    ) -> None:
        for item in conversations:
            self.storage.upsert_conversation(
                user_id=user_id,
                account_id=item.account_id,
                platform="teams",
                external_conversation_id=item.conversation_id,
                name=item.name,
                sender=item.sender,
                preview=item.preview,
                unread_count=item.unread_count,
                message_count=item.message_count,
                has_attachments=item.has_attachments,
                latest_received_at=item.latest_received_at,
                is_group=True,
                metadata={"source": "connector_sync"},
            )

    @staticmethod
    def _as_teams_conversations(
        rows: list[TeamsConversationSummary | dict],
    ) -> list[TeamsConversationSummary]:
        normalized: list[TeamsConversationSummary] = []
        for row in rows:
            if isinstance(row, TeamsConversationSummary):
                normalized.append(row)
            else:
                normalized.append(TeamsConversationSummary.model_validate(row))
        return normalized

    def _persist_teams_messages(
        self,
        *,
        user_id: UUID,
        account_id: UUID,
        conversation_id: str,
        messages: list[TeamsMessage],
    ) -> None:
        latest = messages[-1] if messages else None
        conversation = self.storage.upsert_conversation(
            user_id=user_id,
            account_id=account_id,
            platform="teams",
            external_conversation_id=conversation_id,
            sender=latest.sender if latest else "Teams",
            preview=latest.text if latest else None,
            latest_received_at=latest.created_at if latest else None,
            metadata={"source": "connector_sync"},
        )
        for index, msg in enumerate(messages):
            self.storage.upsert_message(
                conversation=conversation,
                external_message_id=msg.id,
                sender=msg.sender,
                sender_id=None,
                text=msg.text,
                direction="outbound" if msg.from_me else "inbound",
                subtype=None,
                thread_ref=None,
                has_attachments=msg.has_attachments,
                sent_at=msg.created_at,
                raw_payload=msg.model_dump(mode="json"),
                fallback_seed=f"{conversation_id}:{index}",
            )

    @staticmethod
    def _as_teams_messages(rows: list[TeamsMessage | dict]) -> list[TeamsMessage]:
        normalized: list[TeamsMessage] = []
        for row in rows:
            if isinstance(row, TeamsMessage):
                normalized.append(row)
            else:
                normalized.append(TeamsMessage.model_validate(row))
        return normalized

    def _fallback_teams_conversations(
        self,
        *,
        user_id: UUID,
        account_id: UUID | None,
        search: str | None,
        unread_only: bool,
    ) -> list[TeamsConversationSummary]:
        rows = self.storage.list_conversations(
            user_id=user_id,
            platform="teams",
            account_id=account_id,
            search=search,
            unread_only=unread_only,
            limit=1000,
        )
        return [
            TeamsConversationSummary(
                account_id=row.account_id,
                conversation_id=row.external_conversation_id,
                name=row.name,
                sender=row.sender or "Teams",
                preview=row.preview,
                unread_count=max(int(row.unread_count or 0), 0),
                message_count=max(int(row.message_count or 0), 0),
                has_attachments=bool(row.has_attachments),
                latest_received_at=row.latest_received_at,
            )
            for row in rows
        ]

    def _fallback_teams_messages(
        self,
        *,
        user_id: UUID,
        account_id: UUID | None,
        conversation_id: str,
        limit: int,
    ) -> list[TeamsMessage]:
        rows = self.storage.list_messages(
            user_id=user_id,
            platform="teams",
            conversation_external_id=conversation_id,
            account_id=account_id,
            limit=limit,
        )
        return [
            TeamsMessage(
                id=row.external_message_id,
                sender=row.sender,
                from_me=row.direction == "outbound",
                text=row.text,
                created_at=row.sent_at,
                has_attachments=bool(row.has_attachments),
            )
            for row in rows
        ]

    def list_teams_conversations(
        self,
        *,
        user_id: UUID,
        account_id: UUID | None,
        search: str | None,
        unread_only: bool,
    ) -> list[TeamsConversationSummary]:
        try:
            rows = self.teams.list_conversations(
                user_id=user_id,
                account_id=account_id,
                search=search,
                unread_only=unread_only,
            )
            normalized = self._as_teams_conversations(rows)
            self._persist_teams_conversations(user_id=user_id, conversations=normalized)
            self.db.commit()
            return normalized
        except Exception as exc:
            self.db.rollback()
            logger.warning("Teams sync failed, using persisted fallback: %s", exc)
            fallback = self._fallback_teams_conversations(
                user_id=user_id,
                account_id=account_id,
                search=search,
                unread_only=unread_only,
            )
            if fallback:
                return fallback
            raise

    def list_teams_messages(
        self,
        *,
        user_id: UUID,
        conversation_id: str,
        account_id: UUID | None,
        limit: int,
    ) -> list[TeamsMessage]:
        try:
            rows = self.teams.list_messages(
                user_id=user_id,
                conversation_id=conversation_id,
                account_id=account_id,
                limit=limit,
            )
            normalized = self._as_teams_messages(rows)
            account = self._resolve_account(user_id=user_id, provider="teams", account_id=account_id)
            if account:
                self._persist_teams_messages(
                    user_id=user_id,
                    account_id=account.id,
                    conversation_id=conversation_id,
                    messages=normalized,
                )
                self.db.commit()
            return normalized
        except Exception as exc:
            self.db.rollback()
            logger.warning("Teams message sync failed, using persisted fallback: %s", exc)
            fallback = self._fallback_teams_messages(
                user_id=user_id,
                account_id=account_id,
                conversation_id=conversation_id,
                limit=limit,
            )
            if fallback:
                return fallback
            raise

    def send_teams_message(
        self,
        *,
        user_id: UUID,
        conversation_id: str,
        account_id: UUID | None,
        text: str,
    ) -> dict:
        account = self._resolve_account(user_id=user_id, provider="teams", account_id=account_id)
        if not account:
            raise ValueError("No Teams account connected.")

        idempotency_key = f"teams:{account.id}:{uuid4()}"
        conversation = self.storage.upsert_conversation(
            user_id=user_id,
            account_id=account.id,
            platform="teams",
            external_conversation_id=conversation_id,
            sender="Teams",
            preview=text,
            latest_received_at=_utcnow(),
            metadata={"source": "send"},
        )
        self.storage.record_outbound_action(
            user_id=user_id,
            account_id=account.id,
            platform="teams",
            target=conversation_id,
            request_text=text,
            request_payload={"conversation_id": conversation_id, "text": text},
            idempotency_key=idempotency_key,
            conversation=conversation,
            status="queued",
        )
        self.db.flush()

        try:
            result = self.teams.send_message(
                user_id=user_id,
                conversation_id=conversation_id,
                text=text,
                account_id=account_id,
            )
            provider_message_id = str(result.get("message_id") or "")
            self.storage.update_outbound_action(
                idempotency_key=idempotency_key,
                status="sent",
                provider_message_id=provider_message_id or None,
            )
            self.storage.upsert_message(
                conversation=conversation,
                external_message_id=provider_message_id or None,
                sender="You",
                sender_id=None,
                text=text,
                direction="outbound",
                subtype=None,
                thread_ref=None,
                has_attachments=False,
                sent_at=_utcnow(),
                raw_payload={"provider_result": result},
                fallback_seed=idempotency_key,
            )
            conversation.preview = text
            self.db.commit()
            return result
        except Exception as exc:
            self.storage.update_outbound_action(
                idempotency_key=idempotency_key,
                status="failed",
                error=str(exc),
            )
            self.db.commit()
            raise

    def list_whatsapp_conversations(
        self,
        *,
        user_id: UUID,
        account_id: UUID | None,
        unread_only: bool,
        search: str | None,
        limit: int,
    ) -> list[dict]:
        account = self._resolve_account(user_id=user_id, provider="whatsapp", account_id=account_id)
        if not account:
            return []

        service = WhatsAppService(self.db, account_id=account.provider_account_id)
        try:
            rows = service.list_conversations(limit=limit, search=search, unread_only=unread_only)
            for item in rows:
                self.storage.upsert_conversation(
                    user_id=user_id,
                    account_id=account.id,
                    platform="whatsapp",
                    external_conversation_id=str(item.get("conversation_id") or ""),
                    sender=item.get("sender"),
                    preview=item.get("preview"),
                    unread_count=int(item.get("unread_count") or 0),
                    message_count=int(item.get("message_count") or 0),
                    has_attachments=bool(item.get("has_attachments")),
                    latest_received_at=item.get("latest_received_at"),
                    is_group=bool(item.get("is_group")),
                    metadata={"source": "connector_sync"},
                )
            self.db.commit()
            return rows
        except Exception as exc:
            self.db.rollback()
            logger.warning("WhatsApp sync failed, using persisted fallback: %s", exc)
            stored = self.storage.list_conversations(
                user_id=user_id,
                platform="whatsapp",
                account_id=account.id,
                search=search,
                unread_only=unread_only,
                limit=limit,
            )
            return [
                {
                    "conversation_id": row.external_conversation_id,
                    "sender": row.sender or "WhatsApp",
                    "preview": row.preview,
                    "unread_count": int(row.unread_count or 0),
                    "message_count": int(row.message_count or 0),
                    "has_attachments": bool(row.has_attachments),
                    "latest_received_at": row.latest_received_at,
                    "is_group": bool(row.is_group),
                }
                for row in stored
            ]

    def list_whatsapp_messages(
        self,
        *,
        user_id: UUID,
        account_id: UUID | None,
        conversation_id: str,
        limit: int,
    ) -> list[dict]:
        account = self._resolve_account(user_id=user_id, provider="whatsapp", account_id=account_id)
        if not account:
            return []

        service = WhatsAppService(self.db, account_id=account.provider_account_id)
        try:
            rows = service.list_conversation_messages(chat_jid=conversation_id, limit=limit)
            conversation = self.storage.upsert_conversation(
                user_id=user_id,
                account_id=account.id,
                platform="whatsapp",
                external_conversation_id=conversation_id,
                sender=(rows[-1].get("sender") if rows else "WhatsApp"),
                preview=(rows[-1].get("text") if rows else None),
                latest_received_at=(rows[-1].get("received_at") if rows else None),
                metadata={"source": "connector_sync"},
            )
            for index, item in enumerate(rows):
                self.storage.upsert_message(
                    conversation=conversation,
                    external_message_id=(item.get("message_id") or None),
                    sender=item.get("sender"),
                    sender_id=None,
                    text=item.get("text"),
                    direction="outbound" if bool(item.get("from_me")) else "inbound",
                    subtype=item.get("message_type"),
                    thread_ref=None,
                    has_attachments=(
                        (item.get("message_type") or "").lower()
                        not in {"conversation", "extendedtextmessage", ""}
                    ),
                    sent_at=item.get("received_at"),
                    raw_payload=jsonable_encoder(item),
                    fallback_seed=f"{conversation_id}:{index}",
                )
            self.db.commit()
            return rows
        except Exception as exc:
            self.db.rollback()
            logger.warning("WhatsApp message sync failed, using persisted fallback: %s", exc)
            stored = self.storage.list_messages(
                user_id=user_id,
                platform="whatsapp",
                conversation_external_id=conversation_id,
                account_id=account.id,
                limit=limit,
            )
            return [
                {
                    "message_id": row.external_message_id,
                    "sender": row.sender,
                    "from_me": row.direction == "outbound",
                    "text": row.text,
                    "message_type": row.subtype,
                    "timestamp": int(row.sent_at.timestamp() * 1000) if row.sent_at else None,
                    "received_at": row.sent_at,
                }
                for row in stored
            ]

    def send_whatsapp_message(
        self,
        *,
        user_id: UUID,
        account_id: UUID | None,
        to: str,
        text: str,
    ) -> dict:
        account = self._resolve_account(user_id=user_id, provider="whatsapp", account_id=account_id)
        if not account:
            raise ValueError("No WhatsApp account connected.")

        service = WhatsAppService(self.db, account_id=account.provider_account_id)
        idempotency_key = f"whatsapp:{account.id}:{uuid4()}"
        conversation = self.storage.upsert_conversation(
            user_id=user_id,
            account_id=account.id,
            platform="whatsapp",
            external_conversation_id=to,
            sender="WhatsApp",
            preview=text,
            latest_received_at=_utcnow(),
            metadata={"source": "send"},
        )
        self.storage.record_outbound_action(
            user_id=user_id,
            account_id=account.id,
            platform="whatsapp",
            target=to,
            request_text=text,
            request_payload={"to": to, "text": text},
            idempotency_key=idempotency_key,
            conversation=conversation,
            status="queued",
        )
        self.db.flush()

        try:
            result = service.send_message(to=to, text=text)
            self.storage.update_outbound_action(
                idempotency_key=idempotency_key,
                status="sent",
                provider_message_id=None,
            )
            self.storage.upsert_message(
                conversation=conversation,
                external_message_id=None,
                sender="You",
                sender_id=None,
                text=text,
                direction="outbound",
                subtype="conversation",
                thread_ref=None,
                has_attachments=False,
                sent_at=_utcnow(),
                raw_payload={"provider_result": result},
                fallback_seed=idempotency_key,
            )
            conversation.preview = text
            self.db.commit()
            return result
        except Exception as exc:
            self.storage.update_outbound_action(
                idempotency_key=idempotency_key,
                status="failed",
                error=str(exc),
            )
            self.db.commit()
            raise


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)
