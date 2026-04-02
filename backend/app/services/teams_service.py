"""Microsoft Teams read/send helpers built on Microsoft Graph API."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.token_crypto import decrypt_token
from app.models import ConnectedAccount
from app.schemas.teams import TeamsConversationSummary, TeamsMessage, TeamsPresenceResponse

logger = logging.getLogger(__name__)


class TeamsService:
    def __init__(self, db: Session) -> None:
        self.db = db

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

    def _api_get(self, token: str, path: str, params: dict | None = None) -> dict:
        with httpx.Client(timeout=20) as client:
            response = client.get(
                f"{self._base_url()}{path}",
                headers={"Authorization": f"Bearer {token}"},
                params=params or {},
            )
        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After", "30")
            raise ValueError(f"Teams API rate limited. Retry after {retry_after}s.")
        response.raise_for_status()
        return response.json() if response.content else {}

    def _api_post(self, token: str, path: str, payload: dict) -> dict:
        with httpx.Client(timeout=20) as client:
            response = client.post(
                f"{self._base_url()}{path}",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json=payload,
            )
        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After", "30")
            raise ValueError(f"Teams API rate limited. Retry after {retry_after}s.")
        response.raise_for_status()
        return response.json() if response.content else {}

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

    def list_conversations(
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
            token = account.access_token_encrypted
            token = decrypt_token(token)
            if not token:
                continue
            try:
                payload = self._api_get(token, "/me/chats", params={"$top": 50})
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
                        sender = (
                            members[0].get("displayName")
                            or members[0].get("email")
                            or sender
                        )

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

    def list_messages(
        self,
        *,
        user_id: UUID,
        conversation_id: str,
        account_id: UUID | None = None,
        limit: int = 50,
    ) -> list[TeamsMessage]:
        account = self._get_account(user_id=user_id, account_id=account_id)
        token = decrypt_token(account.access_token_encrypted)
        if not token:
            raise ValueError("Connected Teams account is missing access token.")

        payload = self._api_get(
            token,
            f"/chats/{conversation_id}/messages",
            params={"$top": max(1, min(limit, 50))},
        )
        rows = payload.get("value") or []
        messages: list[TeamsMessage] = []
        for row in reversed(rows):
            from_obj = row.get("from") or {}
            user_obj = (from_obj.get("user") or {})
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

    def send_message(
        self,
        *,
        user_id: UUID,
        conversation_id: str,
        text: str,
        account_id: UUID | None = None,
    ) -> dict:
        account = self._get_account(user_id=user_id, account_id=account_id)
        token = decrypt_token(account.access_token_encrypted)
        if not token:
            raise ValueError("Connected Teams account is missing access token.")

        payload = self._api_post(
            token,
            f"/chats/{conversation_id}/messages",
            {"body": {"contentType": "html", "content": text}},
        )
        return {
            "conversation_id": conversation_id,
            "message_id": str(payload.get("id") or ""),
        }

    def get_presence(self, *, user_id: UUID, account_id: UUID | None = None) -> TeamsPresenceResponse:
        account = self._get_account(user_id=user_id, account_id=account_id)
        token = decrypt_token(account.access_token_encrypted)
        if not token:
            raise ValueError("Connected Teams account is missing access token.")
        payload = self._api_get(token, "/me/presence")
        return TeamsPresenceResponse(
            account_id=account.id,
            availability=str(payload.get("availability") or "Unknown"),
            activity=str(payload.get("activity") or "Unknown"),
        )
