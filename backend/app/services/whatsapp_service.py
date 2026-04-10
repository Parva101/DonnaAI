"""WhatsApp service adapter backed by OpenClaw gateway RPC."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import ConnectedAccount, User
from app.schemas.connected_account import ConnectedAccountCreate, ConnectedAccountUpdate
from app.services.connected_account_service import ConnectedAccountService
from app.services.openclaw_gateway_client import OpenClawGatewayClient


class WhatsAppService:
    """OpenClaw-backed WhatsApp read/write service."""

    def __init__(self, db: Session, *, account_id: str | None = None) -> None:
        self.db = db
        self.account_svc = ConnectedAccountService(db)
        self.account_id = (
            (account_id or "").strip()
            or (settings.openclaw_whatsapp_account_id or "").strip()
            or "default"
        )
        self.openclaw = OpenClawGatewayClient(
            channel=(settings.openclaw_whatsapp_channel or "whatsapp").strip().lower() or "whatsapp",
            account_id=self.account_id,
        )
        self._user_jid_re = re.compile(r"^(\d+)(?::\d+)?@(s\.whatsapp\.net|c\.us|lid)$", re.IGNORECASE)
        self._group_jid_re = re.compile(r"^[0-9]+(?:-[0-9]+)*@g\.us$", re.IGNORECASE)

    def _normalize_target(self, raw_target: str) -> str:
        candidate = (raw_target or "").strip()
        while candidate.lower().startswith("whatsapp:"):
            candidate = candidate.split(":", 1)[1].strip()
        if not candidate:
            raise ValueError("Message target cannot be empty.")
        if candidate.startswith("agent:"):
            return candidate
        if self._group_jid_re.match(candidate):
            local = candidate.split("@", 1)[0]
            return f"{local}@g.us"

        user_match = self._user_jid_re.match(candidate)
        if user_match:
            digits = user_match.group(1)
            return f"{digits}@s.whatsapp.net"

        if "@" in candidate:
            raise ValueError("Invalid WhatsApp target format.")

        digits = "".join(ch for ch in candidate if ch.isdigit())
        if not digits:
            raise ValueError("Invalid WhatsApp target format.")
        return f"{digits}@s.whatsapp.net"

    def normalize_target(self, raw_target: str) -> str:
        return self._normalize_target(raw_target)

    @staticmethod
    def _extract_message_id(payload: Any) -> str | None:
        if not isinstance(payload, dict):
            return None
        for key in ("messageId", "message_id", "id"):
            value = payload.get(key)
            if value is not None and str(value).strip():
                return str(value).strip()
        nested = payload.get("result")
        if isinstance(nested, dict):
            for key in ("messageId", "message_id", "id"):
                value = nested.get(key)
                if value is not None and str(value).strip():
                    return str(value).strip()
        return None

    @staticmethod
    def _extract_sender(session: dict[str, Any]) -> str:
        return str(
            session.get("subject")
            or session.get("displayName")
            or session.get("derivedTitle")
            or session.get("lastTo")
            or session.get("key")
            or "WhatsApp"
        )

    @staticmethod
    def _is_group(session: dict[str, Any]) -> bool:
        chat_type = str(session.get("chatType") or "").strip().lower()
        kind = str(session.get("kind") or "").strip().lower()
        return chat_type in {"group", "channel"} or kind == "group"

    @staticmethod
    def _is_internal_or_self_session(session: dict[str, Any]) -> bool:
        """Skip OpenClaw internal/self sessions from user-facing inbox."""
        key = str(session.get("key") or "").strip().lower()
        if key.endswith(":main"):
            return True

        origin = session.get("origin")
        if isinstance(origin, dict):
            provider = str(origin.get("provider") or "").strip().lower()
            if provider in {"heartbeat", "webchat"}:
                return True

            from_id = str(origin.get("from") or "").strip()
            to_id = str(origin.get("to") or "").strip()
            if from_id and to_id and from_id == to_id:
                return True

        return False

    def ensure_connected_account(self, user: User) -> ConnectedAccount:
        existing = self.account_svc.get_by_provider(
            user_id=user.id,
            provider="whatsapp",
            provider_account_id=self.account_id,
        )
        metadata = {
            "integration": "openclaw",
            "channel": self.openclaw.channel,
            "account_id": self.account_id,
            "gateway_url": self.openclaw.gateway_url,
            "connected_at": datetime.now(timezone.utc).isoformat(),
        }
        if existing:
            return self.account_svc.update(
                existing,
                ConnectedAccountUpdate(account_metadata=metadata, account_email=self.account_id),
            )
        return self.account_svc.create(
            user,
            ConnectedAccountCreate(
                provider="whatsapp",
                provider_account_id=self.account_id,
                account_email=self.account_id,
                access_token_encrypted=None,
                refresh_token_encrypted=None,
                token_expires_at=None,
                scopes=None,
                account_metadata=metadata,
            ),
        )

    def start_listener(self) -> dict[str, Any]:
        try:
            payload = self.openclaw.call(
                "web.login.start",
                {
                    "accountId": self.account_id,
                    "force": False,
                    "timeoutMs": min(self.openclaw.gateway_timeout_ms, 30_000),
                },
                timeout_ms=max(self.openclaw.gateway_timeout_ms, 30_000),
            )
        except ValueError as exc:
            if "provider is not available" not in str(exc).lower():
                raise
            self.openclaw.ensure_channel_account()
            payload = self.openclaw.call(
                "web.login.start",
                {
                    "accountId": self.account_id,
                    "force": False,
                    "timeoutMs": min(self.openclaw.gateway_timeout_ms, 30_000),
                },
                timeout_ms=max(self.openclaw.gateway_timeout_ms, 30_000),
            )
        # Prime the login waiter briefly so OpenClaw can surface immediate pairing
        # errors and complete channel start when scan happens quickly.
        self._wait_login_progress(timeout_ms=1_000)
        qr_data_url = payload.get("qrDataUrl") if isinstance(payload, dict) else None
        return {
            "running": True,
            "pid": None,
            "device_id": self.account_id,
            "qr_data_uri": qr_data_url if isinstance(qr_data_url, str) else None,
            "message": payload.get("message") if isinstance(payload, dict) else None,
        }

    def _wait_login_progress(self, *, timeout_ms: int = 1_000) -> dict[str, Any] | None:
        try:
            payload = self.openclaw.call(
                "web.login.wait",
                {
                    "accountId": self.account_id,
                    "timeoutMs": max(timeout_ms, 1_000),
                },
                timeout_ms=max(timeout_ms + 2_000, 3_000),
            )
        except Exception:
            return None
        return payload if isinstance(payload, dict) else None

    def status(self) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        try:
            snapshot = self.openclaw.channel_snapshot() or {}
        except Exception as exc:
            return {
                "running": False,
                "pid": None,
                "device_id": self.account_id,
                "qr_data_uri": None,
                "qr_text": str(exc),
                "connection_state": "error",
                "me_jid": None,
                "state_updated_at": now.isoformat(),
                "state_age_seconds": None,
            }
        if not snapshot:
            try:
                self.openclaw.ensure_channel_account()
                snapshot = self.openclaw.channel_snapshot() or {}
            except Exception:
                snapshot = {}

        wait_result: dict[str, Any] | None = None
        if snapshot:
            try:
                linked_now = bool(snapshot.get("linked"))
                connected_now = bool(snapshot.get("connected"))
            except Exception:
                linked_now = False
                connected_now = False
            if not linked_now and not connected_now:
                wait_result = self._wait_login_progress(timeout_ms=1_000)
                if wait_result and wait_result.get("connected"):
                    refreshed = self.openclaw.channel_snapshot() or {}
                    if refreshed:
                        snapshot = refreshed

        connected = bool(snapshot.get("connected"))
        running = bool(snapshot.get("running"))
        configured = bool(snapshot.get("configured"))
        linked = bool(snapshot.get("linked"))
        busy = bool(snapshot.get("busy"))
        last_error = str(snapshot.get("lastError") or "").strip()
        lowered_error = last_error.lower()
        benign_error = (
            not last_error
            or "not linked" in lowered_error
            or "not connected" in lowered_error
            or "disconnected" in lowered_error
            or "stopped" in lowered_error
        )

        if connected:
            connection_state = "connected"
        elif linked:
            connection_state = "linked"
        elif configured and not linked:
            connection_state = "waiting_qr"
        elif running or busy:
            connection_state = "connecting"
        elif last_error and not benign_error:
            connection_state = "error"
        else:
            connection_state = "disconnected"

        me_jid: str | None = None
        probe = snapshot.get("probe")
        if isinstance(probe, dict):
            for key in ("meJid", "jid", "me_jid"):
                value = probe.get(key)
                if isinstance(value, str) and value.strip():
                    me_jid = value.strip()
                    break

        last_probe_ms = OpenClawGatewayClient.to_int(snapshot.get("lastProbeAt"))
        state_updated_at = OpenClawGatewayClient.iso_from_ms(last_probe_ms) or now.isoformat()
        state_age_seconds: float | None = None
        if last_probe_ms is not None:
            dt = OpenClawGatewayClient.datetime_from_ms(last_probe_ms)
            if dt is not None:
                state_age_seconds = max((now - dt).total_seconds(), 0.0)

        qr_data_uri: str | None = None
        qr_text: str | None = (
            str(wait_result.get("message") or "").strip() if isinstance(wait_result, dict) else None
        ) or last_error or None
        if linked and not connected:
            if running:
                qr_text = "WhatsApp is linked and reconnecting."
            else:
                qr_text = (
                    "WhatsApp is linked, but no active listener is running. "
                    f"Run: openclaw channels login --channel {self.openclaw.channel} --account {self.account_id}"
                )
        should_probe_qr = (not connected) and (not linked) and connection_state in {"waiting_qr", "disconnected"}
        if should_probe_qr:
            try:
                login = self.openclaw.call(
                    "web.login.start",
                    {
                        "accountId": self.account_id,
                        "force": False,
                        # OpenClaw can take ~15s+ to return the first QR.
                        "timeoutMs": min(self.openclaw.gateway_timeout_ms, 20_000),
                    },
                    timeout_ms=max(self.openclaw.gateway_timeout_ms, 22_000),
                )
                if isinstance(login, dict):
                    qr_candidate = login.get("qrDataUrl")
                    if isinstance(qr_candidate, str) and qr_candidate.strip():
                        qr_data_uri = qr_candidate
                    message = login.get("message")
                    if isinstance(message, str) and message.strip():
                        qr_text = message
            except Exception as exc:
                if not qr_text:
                    qr_text = str(exc)

        return {
            "running": running,
            "pid": None,
            "device_id": self.account_id,
            "qr_data_uri": qr_data_uri,
            "qr_text": qr_text,
            "connection_state": connection_state,
            "me_jid": me_jid,
            "state_updated_at": state_updated_at,
            "state_age_seconds": state_age_seconds,
        }

    def list_conversations(
        self,
        *,
        limit: int = 5000,
        search: str | None = None,
        unread_only: bool = False,
    ) -> list[dict[str, Any]]:
        try:
            sessions = self.openclaw.list_sessions(
                limit=max(int(limit), 1),
                search=search or None,
                include_last_message=True,
                include_derived_titles=True,
            )
        except Exception:
            return []

        search_lc = search.strip().lower() if search else None
        rows: list[dict[str, Any]] = []
        for session in sessions:
            if not isinstance(session, dict):
                continue
            if self._is_internal_or_self_session(session):
                continue

            session_key = str(session.get("key") or "").strip()
            if not session_key:
                continue

            unread_count = OpenClawGatewayClient.to_int(session.get("unreadCount")) or 0
            if unread_only and unread_count <= 0:
                continue

            sender = self._extract_sender(session)
            preview_raw = session.get("lastMessagePreview")
            preview = preview_raw.strip() if isinstance(preview_raw, str) and preview_raw.strip() else None
            if search_lc:
                blob = f"{session_key} {sender} {preview or ''}".lower()
                if search_lc not in blob:
                    continue

            updated_ms = OpenClawGatewayClient.to_int(session.get("updatedAt"))
            message_count = OpenClawGatewayClient.to_int(session.get("messageCount"))
            if message_count is None:
                message_count = max(1, unread_count) if preview or unread_count else 0

            rows.append(
                {
                    "conversation_id": session_key,
                    "sender": sender,
                    "preview": preview,
                    "unread_count": max(unread_count, 0),
                    "message_count": max(message_count, 0),
                    "has_attachments": bool(session.get("lastMessageHasAttachments")),
                    "latest_received_at": OpenClawGatewayClient.datetime_from_ms(updated_ms),
                    "is_group": self._is_group(session),
                }
            )

        rows.sort(
            key=lambda item: (
                item["latest_received_at"] is None,
                item["latest_received_at"] or datetime.min.replace(tzinfo=timezone.utc),
            ),
            reverse=True,
        )
        return rows[:limit]

    def list_conversation_messages(
        self,
        *,
        chat_jid: str,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        try:
            history = self.openclaw.chat_history(
                session_key=chat_jid,
                limit=max(min(limit * 2, 1000), limit),
            )
        except Exception:
            return []

        rows: list[tuple[int, dict[str, Any]]] = []
        for idx, message in enumerate(history):
            if not isinstance(message, dict):
                continue
            role = str(message.get("role") or "").strip().lower()
            if role in {"tool", "system"}:
                continue

            # OpenClaw can keep local assistant error artifacts in session history.
            # These are not real WhatsApp messages and should not appear in Donna's inbox.
            has_transport_metadata = any(
                message.get(field) is not None
                for field in ("channel", "accountId", "fromMe", "sender", "authorName")
            )
            if role == "assistant" and not has_transport_metadata:
                continue

            msg_type = str(message.get("type") or role or "message").strip().lower() or "message"
            text = OpenClawGatewayClient.extract_text_from_message(message)
            if not text:
                if msg_type in {"conversation", "extendedtextmessage", "text", "message"}:
                    continue
                text = f"[{msg_type}]"

            timestamp = OpenClawGatewayClient.to_int(message.get("timestamp"))
            from_me = role == "assistant" or bool(message.get("fromMe"))
            sender = message.get("authorName") or message.get("sender") or ("You" if from_me else "Contact")
            msg_id = message.get("id") or message.get("message_id") or f"{chat_jid}-{idx}"

            rows.append(
                (
                    timestamp if timestamp is not None else idx,
                    {
                        "message_id": str(msg_id),
                        "sender": str(sender) if sender is not None else ("You" if from_me else "Contact"),
                        "from_me": from_me,
                        "text": text,
                        "message_type": msg_type,
                        "timestamp": timestamp,
                        "received_at": OpenClawGatewayClient.datetime_from_ms(timestamp),
                    },
                )
            )

        rows.sort(key=lambda item: item[0])
        return [item[1] for item in rows[-limit:]]

    def send_message(self, to: str, text: str) -> dict[str, Any]:
        message_text = text.strip()
        if not message_text:
            raise ValueError("Message text cannot be empty.")
        target = self._normalize_target(to)

        # Inbox conversation ids are OpenClaw session keys.
        # Use chat.send for session-key targets and raw send for direct IDs.
        payload: dict[str, Any]
        if target.startswith("agent:"):
            payload = self.openclaw.chat_send(session_key=target, text=message_text)
        else:
            payload = self.openclaw.raw_send(to=target, text=message_text)
        return {
            "status": "sent",
            "to": target,
            "message_id": self._extract_message_id(payload),
        }
