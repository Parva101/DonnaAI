"""Microsoft Teams helpers with OpenClaw-first fallback to Graph API."""

from __future__ import annotations

import logging
import random
import time
from datetime import datetime, timedelta, timezone
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.token_crypto import decrypt_token, encrypt_token
from app.models import ConnectedAccount
from app.schemas.teams import TeamsConversationSummary, TeamsMessage, TeamsPresenceResponse
from app.services.openclaw_gateway_client import OpenClawGatewayClient

logger = logging.getLogger(__name__)
TEAMS_MAX_RETRIES = 3
TEAMS_BASE_RETRY_SECONDS = 1.0
TEAMS_MAX_RETRY_SECONDS = 20.0
TEAMS_GRAPH_TRANSIENT_STATUS = {429, 500, 502, 503, 504}


class TeamsService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.openclaw_enabled = bool(settings.openclaw_enable_teams)
        self.openclaw = OpenClawGatewayClient(
            channel=(settings.openclaw_teams_channel or "teams").strip().lower() or "teams",
            account_id=(settings.openclaw_teams_account_id or "").strip() or None,
        )

    def _list_accounts(self, *, user_id: UUID, account_id: UUID | None = None) -> list[ConnectedAccount]:
        stmt = select(ConnectedAccount).where(
            ConnectedAccount.user_id == user_id,
            ConnectedAccount.provider == "teams",
        )
        if account_id:
            stmt = stmt.where(ConnectedAccount.id == account_id)
        return list(self.db.execute(stmt).scalars())

    def _get_account(self, *, user_id: UUID, account_id: UUID | None = None) -> ConnectedAccount:
        accounts = self._list_accounts(user_id=user_id, account_id=account_id)
        if not accounts:
            raise ValueError("No Teams account connected.")
        return accounts[0]

    def _base_url(self) -> str:
        return settings.teams_graph_base_url.rstrip("/")

    @staticmethod
    def _parse_retry_after(value: str | None) -> float:
        if not value:
            return 0.0
        try:
            return max(float(value), 0.0)
        except Exception:
            return 0.0

    @staticmethod
    def _compute_retry_delay(attempt: int, retry_after: float = 0.0) -> float:
        base = min(TEAMS_BASE_RETRY_SECONDS * (2 ** max(attempt - 1, 0)), TEAMS_MAX_RETRY_SECONDS)
        jitter = random.uniform(0.0, 0.25)
        return max(base + jitter, retry_after)

    @staticmethod
    def _token_endpoint(tenant_id: str) -> str:
        tenant = (tenant_id or settings.microsoft_tenant_id).strip() or "common"
        return f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"

    def _refresh_access_token(self, account: ConnectedAccount) -> str:
        refresh_token = decrypt_token(account.refresh_token_encrypted)
        if not refresh_token:
            raise ValueError("Teams access token expired and no refresh token is available.")

        metadata = dict(account.account_metadata or {})
        tenant = str(metadata.get("tenant") or settings.microsoft_tenant_id or "common").strip() or "common"
        payload = {
            "client_id": settings.microsoft_client_id,
            "client_secret": settings.microsoft_client_secret,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "scope": account.scopes or "",
        }

        with httpx.Client(timeout=20) as client:
            response = client.post(
                self._token_endpoint(tenant),
                data=payload,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        response.raise_for_status()
        data = response.json()
        access_token = str(data.get("access_token") or "").strip()
        if not access_token:
            raise ValueError("Failed to refresh Teams access token.")

        account.access_token_encrypted = encrypt_token(access_token)
        new_refresh = str(data.get("refresh_token") or "").strip()
        if new_refresh:
            account.refresh_token_encrypted = encrypt_token(new_refresh)
        expires_in_raw = data.get("expires_in")
        try:
            expires_in = int(expires_in_raw)
            account.token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=max(expires_in, 0))
        except Exception:
            account.token_expires_at = None

        self.db.add(account)
        self.db.commit()
        self.db.refresh(account)
        return access_token

    def _api_request(
        self,
        *,
        token: str,
        path: str,
        method: str,
        params: dict | None = None,
        payload: dict | None = None,
    ) -> dict:
        last_error: Exception | None = None
        for attempt in range(1, TEAMS_MAX_RETRIES + 1):
            try:
                with httpx.Client(timeout=20) as client:
                    response = client.request(
                        method,
                        f"{self._base_url()}{path}",
                        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                        params=params or None,
                        json=payload or None,
                    )
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_error = exc
                if attempt >= TEAMS_MAX_RETRIES:
                    break
                delay = self._compute_retry_delay(attempt)
                logger.warning(
                    "Teams Graph %s %s transport error (attempt %s/%s): %s. Retrying in %.2fs.",
                    method,
                    path,
                    attempt,
                    TEAMS_MAX_RETRIES,
                    exc,
                    delay,
                )
                time.sleep(delay)
                continue

            status_code = response.status_code
            if status_code == 401:
                raise PermissionError("Teams access token is invalid or expired.")

            if status_code in TEAMS_GRAPH_TRANSIENT_STATUS:
                if attempt >= TEAMS_MAX_RETRIES:
                    raise RuntimeError(
                        f"Teams Graph API {method} {path} failed with HTTP {status_code} after retries."
                    )
                retry_after = self._parse_retry_after(response.headers.get("Retry-After"))
                delay = self._compute_retry_delay(attempt, retry_after=retry_after)
                logger.warning(
                    "Teams Graph %s %s transient HTTP %s (attempt %s/%s). Retrying in %.2fs.",
                    method,
                    path,
                    status_code,
                    attempt,
                    TEAMS_MAX_RETRIES,
                    delay,
                )
                time.sleep(delay)
                continue

            response.raise_for_status()
            if not response.content:
                return {}
            return response.json()

        raise RuntimeError(
            f"Teams Graph API {method} {path} failed after {TEAMS_MAX_RETRIES} attempts: {last_error}"
        )

    def _request_with_refresh(
        self,
        *,
        account: ConnectedAccount,
        path: str,
        method: str,
        params: dict | None = None,
        payload: dict | None = None,
    ) -> dict:
        token = decrypt_token(account.access_token_encrypted)
        if not token:
            raise ValueError("Connected Teams account is missing access token.")
        try:
            return self._api_request(
                token=token,
                path=path,
                method=method,
                params=params,
                payload=payload,
            )
        except PermissionError:
            refreshed_token = self._refresh_access_token(account)
            return self._api_request(
                token=refreshed_token,
                path=path,
                method=method,
                params=params,
                payload=payload,
            )

    def _api_get(self, account: ConnectedAccount, path: str, params: dict | None = None) -> dict:
        return self._request_with_refresh(
            account=account,
            path=path,
            method="GET",
            params=params,
        )

    def _api_post(self, account: ConnectedAccount, path: str, payload: dict) -> dict:
        return self._request_with_refresh(
            account=account,
            path=path,
            method="POST",
            payload=payload,
        )

    @staticmethod
    def _parse_dt(value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except Exception:
            return None

    @staticmethod
    def _strip_html(value: str | None) -> str:
        if not value:
            return ""
        text = value.replace("<br>", " ").replace("<br/>", " ").replace("<br />", " ")
        return (
            text.replace("<p>", " ")
            .replace("</p>", " ")
            .replace("<div>", " ")
            .replace("</div>", " ")
            .replace("&nbsp;", " ")
            .strip()
        )

    @staticmethod
    def _openclaw_sender(session: dict) -> str:
        return str(
            session.get("subject")
            or session.get("displayName")
            or session.get("derivedTitle")
            or session.get("lastTo")
            or session.get("key")
            or "Teams"
        )

    @staticmethod
    def _openclaw_name(session: dict) -> str | None:
        value = session.get("displayName") or session.get("derivedTitle") or session.get("subject")
        if isinstance(value, str):
            text = value.strip()
            return text or None
        return None

    def _list_conversations_openclaw(
        self,
        *,
        user_id: UUID,
        account_id: UUID | None,
        search: str | None,
        unread_only: bool,
    ) -> list[TeamsConversationSummary]:
        accounts = self._list_accounts(user_id=user_id, account_id=account_id)
        if not accounts:
            return []
        account = accounts[0]
        snapshot = self.openclaw.channel_snapshot()
        if not snapshot or not bool(snapshot.get("configured")):
            raise ValueError("OpenClaw Teams channel is not configured.")

        sessions = self.openclaw.list_sessions(
            limit=1000,
            search=search,
            include_last_message=True,
            include_derived_titles=True,
        )

        output: list[TeamsConversationSummary] = []
        for session in sessions:
            if not isinstance(session, dict):
                continue
            session_key = str(session.get("key") or "").strip()
            if not session_key:
                continue

            unread_count = OpenClawGatewayClient.to_int(session.get("unreadCount")) or 0
            if unread_only and unread_count <= 0:
                continue

            preview_raw = session.get("lastMessagePreview")
            preview = preview_raw.strip() if isinstance(preview_raw, str) and preview_raw.strip() else None
            updated_ms = OpenClawGatewayClient.to_int(session.get("updatedAt"))
            latest_received_at = OpenClawGatewayClient.datetime_from_ms(updated_ms)

            message_count = OpenClawGatewayClient.to_int(session.get("messageCount"))
            if message_count is None:
                message_count = max(1, unread_count) if preview or unread_count else 0

            output.append(
                TeamsConversationSummary(
                    account_id=account.id,
                    conversation_id=session_key,
                    name=self._openclaw_name(session),
                    sender=self._openclaw_sender(session),
                    preview=preview,
                    unread_count=max(unread_count, 0),
                    message_count=max(message_count, 0),
                    has_attachments=bool(session.get("lastMessageHasAttachments")),
                    latest_received_at=latest_received_at,
                )
            )

        output.sort(
            key=lambda c: (
                c.latest_received_at is None,
                c.latest_received_at or datetime.min.replace(tzinfo=timezone.utc),
            ),
            reverse=True,
        )
        return output

    def _list_messages_openclaw(
        self,
        *,
        user_id: UUID,
        conversation_id: str,
        account_id: UUID | None,
        limit: int,
    ) -> list[TeamsMessage]:
        # Keep account-existence behavior aligned with native path.
        self._get_account(user_id=user_id, account_id=account_id)
        rows = self.openclaw.chat_history(
            session_key=conversation_id,
            limit=max(min(limit * 2, 1000), limit),
        )

        parsed: list[tuple[int, TeamsMessage]] = []
        for idx, row in enumerate(rows):
            if not isinstance(row, dict):
                continue
            role = str(row.get("role") or "").strip().lower()
            if role in {"tool", "system"}:
                continue
            text = OpenClawGatewayClient.extract_text_from_message(row)
            if not text:
                continue
            ts_ms = OpenClawGatewayClient.to_int(row.get("timestamp"))
            sender = row.get("authorName") or row.get("sender") or ("You" if role == "assistant" else "Teams")
            msg_id = row.get("id") or row.get("message_id") or f"{conversation_id}-{idx}"

            parsed.append(
                (
                    ts_ms or idx,
                    TeamsMessage(
                        id=str(msg_id),
                        sender=str(sender) if sender is not None else None,
                        from_me=(role == "assistant"),
                        text=text,
                        created_at=OpenClawGatewayClient.datetime_from_ms(ts_ms),
                        has_attachments=bool(row.get("attachments") or row.get("files")),
                    ),
                )
            )

        parsed.sort(key=lambda item: item[0])
        return [msg for _, msg in parsed[-limit:]]

    def _send_message_openclaw(
        self,
        *,
        user_id: UUID,
        conversation_id: str,
        text: str,
        account_id: UUID | None,
    ) -> dict:
        # Keep account-existence behavior aligned with native path.
        self._get_account(user_id=user_id, account_id=account_id)
        payload = self.openclaw.chat_send(session_key=conversation_id, text=text)
        msg_id = payload.get("id") if isinstance(payload, dict) else None
        if msg_id:
            return {"conversation_id": conversation_id, "message_id": str(msg_id)}

        fallback_payload = self.openclaw.raw_send(to=conversation_id, text=text)
        fallback_id = fallback_payload.get("id") if isinstance(fallback_payload, dict) else None
        return {
            "conversation_id": conversation_id,
            "message_id": str(fallback_id) if fallback_id is not None else None,
        }

    def _list_conversations_native(
        self,
        *,
        user_id: UUID,
        account_id: UUID | None = None,
        search: str | None = None,
        unread_only: bool = False,
    ) -> list[TeamsConversationSummary]:
        accounts = self._list_accounts(user_id=user_id, account_id=account_id)
        output: list[TeamsConversationSummary] = []
        search_lc = search.strip().lower() if search else None

        for account in accounts:
            token = decrypt_token(account.access_token_encrypted)
            if not token and not account.refresh_token_encrypted:
                continue
            try:
                payload = self._api_get(account, "/me/chats", params={"$top": 50})
            except Exception as exc:
                logger.warning("Teams list conversations failed for account %s: %s", account.id, exc)
                continue

            chats = payload.get("value") or []
            for chat in chats:
                conv_id = str(chat.get("id") or "").strip()
                if not conv_id:
                    continue
                topic = (chat.get("topic") or "").strip() or None
                preview_obj = chat.get("lastMessagePreview") or {}
                preview = self._strip_html((preview_obj.get("body") or {}).get("content")) or None
                latest_received_at = self._parse_dt(chat.get("lastUpdatedDateTime"))

                sender = topic or "Teams Chat"
                if not topic:
                    members = chat.get("members") or []
                    if members:
                        sender = members[0].get("displayName") or members[0].get("email") or sender

                unread = int(chat.get("viewpoint", {}).get("unreadCount") or 0)
                if unread_only and unread <= 0:
                    continue

                if search_lc:
                    blob = " ".join([sender, topic or "", preview or "", conv_id]).lower()
                    if search_lc not in blob:
                        continue

                output.append(
                    TeamsConversationSummary(
                        account_id=account.id,
                        conversation_id=conv_id,
                        name=topic,
                        sender=sender,
                        preview=preview,
                        unread_count=unread,
                        message_count=max(1, unread),
                        has_attachments=False,
                        latest_received_at=latest_received_at,
                    )
                )

        output.sort(
            key=lambda c: (
                c.latest_received_at is None,
                c.latest_received_at or datetime.min.replace(tzinfo=timezone.utc),
            ),
            reverse=True,
        )
        return output

    def _list_messages_native(
        self,
        *,
        user_id: UUID,
        conversation_id: str,
        account_id: UUID | None = None,
        limit: int = 50,
    ) -> list[TeamsMessage]:
        conversation_id = conversation_id.strip()
        if not conversation_id:
            raise ValueError("Teams conversation id cannot be empty.")
        account = self._get_account(user_id=user_id, account_id=account_id)
        payload = self._api_get(
            account,
            f"/chats/{conversation_id}/messages",
            params={"$top": max(1, min(limit, 50))},
        )
        rows = payload.get("value") or []
        messages: list[TeamsMessage] = []
        for row in reversed(rows):
            from_obj = row.get("from") or {}
            user_obj = from_obj.get("user") or {}
            sender = user_obj.get("displayName") or user_obj.get("id") or "Teams"
            body = row.get("body") or {}
            text = self._strip_html(body.get("content"))
            messages.append(
                TeamsMessage(
                    id=str(row.get("id") or ""),
                    sender=sender,
                    from_me=False,
                    text=text or None,
                    created_at=self._parse_dt(row.get("createdDateTime")),
                    has_attachments=bool(row.get("attachments")),
                )
            )
        return messages

    def _send_message_native(
        self,
        *,
        user_id: UUID,
        conversation_id: str,
        text: str,
        account_id: UUID | None = None,
    ) -> dict:
        conversation_id = conversation_id.strip()
        if not conversation_id:
            raise ValueError("Teams conversation id cannot be empty.")
        account = self._get_account(user_id=user_id, account_id=account_id)

        payload = self._api_post(
            account,
            f"/chats/{conversation_id}/messages",
            {"body": {"contentType": "html", "content": text}},
        )
        return {
            "conversation_id": conversation_id,
            "message_id": str(payload.get("id") or ""),
        }

    def list_conversations(
        self,
        *,
        user_id: UUID,
        account_id: UUID | None = None,
        search: str | None = None,
        unread_only: bool = False,
    ) -> list[TeamsConversationSummary]:
        if self.openclaw_enabled:
            try:
                return self._list_conversations_openclaw(
                    user_id=user_id,
                    account_id=account_id,
                    search=search,
                    unread_only=unread_only,
                )
            except Exception as exc:
                logger.warning("Teams OpenClaw path failed, falling back to Graph API: %s", exc)

        return self._list_conversations_native(
            user_id=user_id,
            account_id=account_id,
            search=search,
            unread_only=unread_only,
        )

    def list_messages(
        self,
        *,
        user_id: UUID,
        conversation_id: str,
        account_id: UUID | None = None,
        limit: int = 50,
    ) -> list[TeamsMessage]:
        if self.openclaw_enabled:
            try:
                return self._list_messages_openclaw(
                    user_id=user_id,
                    conversation_id=conversation_id,
                    account_id=account_id,
                    limit=limit,
                )
            except Exception as exc:
                logger.warning("Teams OpenClaw history failed, falling back to Graph API: %s", exc)

        return self._list_messages_native(
            user_id=user_id,
            conversation_id=conversation_id,
            account_id=account_id,
            limit=limit,
        )

    def send_message(
        self,
        *,
        user_id: UUID,
        conversation_id: str,
        text: str,
        account_id: UUID | None = None,
    ) -> dict:
        message_text = text.strip()
        if not message_text:
            raise ValueError("Message text cannot be empty.")
        conversation_id = conversation_id.strip()
        if not conversation_id:
            raise ValueError("Teams conversation id cannot be empty.")

        if self.openclaw_enabled:
            try:
                return self._send_message_openclaw(
                    user_id=user_id,
                    conversation_id=conversation_id,
                    text=message_text,
                    account_id=account_id,
                )
            except Exception as exc:
                logger.warning("Teams OpenClaw send failed, falling back to Graph API: %s", exc)

        return self._send_message_native(
            user_id=user_id,
            conversation_id=conversation_id,
            text=message_text,
            account_id=account_id,
        )

    def get_presence(self, *, user_id: UUID, account_id: UUID | None = None) -> TeamsPresenceResponse:
        account = self._get_account(user_id=user_id, account_id=account_id)
        payload = self._api_get(account, "/me/presence")
        return TeamsPresenceResponse(
            account_id=account.id,
            availability=str(payload.get("availability") or "Unknown"),
            activity=str(payload.get("activity") or "Unknown"),
        )
