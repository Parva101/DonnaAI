"""Slack read/send helpers built on Slack Web API."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.token_crypto import decrypt_token
from app.models import ConnectedAccount
from app.schemas.slack import SlackConversationSummary, SlackMessage

logger = logging.getLogger(__name__)

SLACK_API_BASE = "https://slack.com/api"


class SlackService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def _list_accounts(self, *, user_id: UUID, account_id: UUID | None = None) -> list[ConnectedAccount]:
        stmt = select(ConnectedAccount).where(
            ConnectedAccount.user_id == user_id,
            ConnectedAccount.provider == "slack",
        )
        if account_id:
            stmt = stmt.where(ConnectedAccount.id == account_id)
        return list(self.db.execute(stmt).scalars())

    def _get_account(self, *, user_id: UUID, account_id: UUID | None = None) -> ConnectedAccount:
        accounts = self._list_accounts(user_id=user_id, account_id=account_id)
        if not accounts:
            raise ValueError("No Slack account connected.")
        return accounts[0]

    def _api_get(self, token: str, method: str, params: dict | None = None) -> dict:
        with httpx.Client(timeout=20) as client:
            response = client.get(
                f"{SLACK_API_BASE}/{method}",
                headers={"Authorization": f"Bearer {token}"},
                params=params or {},
            )
        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After", "30")
            raise ValueError(f"Slack API rate limited. Retry after {retry_after}s.")
        response.raise_for_status()
        payload = response.json()
        if not payload.get("ok"):
            raise ValueError(payload.get("error") or f"Slack API call failed: {method}")
        return payload

    def _api_post(self, token: str, method: str, payload: dict) -> dict:
        with httpx.Client(timeout=20) as client:
            response = client.post(
                f"{SLACK_API_BASE}/{method}",
                headers={"Authorization": f"Bearer {token}"},
                json=payload,
            )
        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After", "30")
            raise ValueError(f"Slack API rate limited. Retry after {retry_after}s.")
        response.raise_for_status()
        data = response.json()
        if not data.get("ok"):
            raise ValueError(data.get("error") or f"Slack API call failed: {method}")
        return data

    @staticmethod
    def _parse_ts(ts_raw: str | None) -> datetime | None:
        if not ts_raw:
            return None
        try:
            return datetime.fromtimestamp(float(ts_raw), tz=timezone.utc)
        except Exception:
            return None

    def _get_user_display_name(self, token: str, user_id: str | None, cache: dict[str, str]) -> str | None:
        if not user_id:
            return None
        if user_id in cache:
            return cache[user_id]
        try:
            payload = self._api_get(token, "users.info", {"user": user_id})
            user = payload.get("user") or {}
            profile = user.get("profile") or {}
            name = (
                profile.get("display_name")
                or profile.get("real_name")
                or user.get("real_name")
                or user.get("name")
                or user_id
            )
            cache[user_id] = name
            return name
        except Exception:
            cache[user_id] = user_id
            return user_id

    def _resolve_sender(
        self,
        *,
        token: str,
        channel: dict,
        latest: dict,
        user_cache: dict[str, str],
    ) -> str:
        # DM channels: surface the human on the other side when possible.
        if channel.get("is_im"):
            im_user_id = channel.get("user")
            return (
                self._get_user_display_name(token, im_user_id, user_cache)
                or channel.get("name")
                or channel.get("id")
                or "Slack DM"
            )

        latest_user_id = latest.get("user")
        if latest_user_id:
            return (
                self._get_user_display_name(token, latest_user_id, user_cache)
                or channel.get("name")
                or channel.get("id")
                or "Slack"
            )

        return channel.get("name") or channel.get("id") or "Slack"

    def list_conversations(
        self,
        *,
        user_id: UUID,
        account_id: UUID | None = None,
        search: str | None = None,
        unread_only: bool = False,
    ) -> list[SlackConversationSummary]:
        accounts = self._list_accounts(user_id=user_id, account_id=account_id)
        summaries: list[SlackConversationSummary] = []
        search_lc = search.strip().lower() if search else None

        for account in accounts:
            token = account.access_token_encrypted
            token = decrypt_token(token)
            if not token:
                logger.warning("Slack account %s has no access token stored.", account.id)
                continue

            user_cache: dict[str, str] = {}
            cursor: str | None = None
            # Keep bounded paging to avoid very large requests in one UI load.
            for _ in range(8):
                params = {
                    "types": "public_channel,private_channel,im,mpim",
                    "exclude_archived": "true",
                    "limit": 200,
                }
                if cursor:
                    params["cursor"] = cursor

                payload = self._api_get(token, "conversations.list", params=params)
                channels = payload.get("channels") or []

                for channel in channels:
                    latest = channel.get("latest") or {}
                    latest_ts = latest.get("ts")
                    latest_received_at = self._parse_ts(latest_ts)
                    preview = (latest.get("text") or "").strip() or None

                    sender = self._resolve_sender(
                        token=token,
                        channel=channel,
                        latest=latest,
                        user_cache=user_cache,
                    )
                    name = channel.get("name")
                    unread_count = int(channel.get("unread_count_display") or channel.get("unread_count") or 0)
                    has_attachments = bool(latest.get("files"))
                    message_count = max(1, unread_count) if latest or unread_count else 0

                    if unread_only and unread_count <= 0:
                        continue

                    if search_lc:
                        blob = " ".join(
                            [
                                (sender or ""),
                                (name or ""),
                                (preview or ""),
                                (channel.get("id") or ""),
                            ]
                        ).lower()
                        if search_lc not in blob:
                            continue

                    # Skip empty rows that have no useful display information.
                    if not preview and not name and not sender and not latest_received_at:
                        continue

                    summaries.append(
                        SlackConversationSummary(
                            account_id=account.id,
                            conversation_id=channel.get("id") or "",
                            name=name,
                            sender=sender,
                            preview=preview,
                            unread_count=unread_count,
                            message_count=message_count,
                            has_attachments=has_attachments,
                            latest_received_at=latest_received_at,
                            is_im=bool(channel.get("is_im")),
                            is_private=bool(channel.get("is_private")),
                        )
                    )

                cursor = (payload.get("response_metadata") or {}).get("next_cursor") or None
                if not cursor:
                    break

        summaries.sort(
            key=lambda c: (
                c.latest_received_at is None,
                c.latest_received_at or datetime.min.replace(tzinfo=timezone.utc),
            ),
            reverse=True,
        )
        return summaries

    def list_messages(
        self,
        *,
        user_id: UUID,
        conversation_id: str,
        account_id: UUID | None = None,
        limit: int = 50,
    ) -> list[SlackMessage]:
        account = self._get_account(user_id=user_id, account_id=account_id)
        token = decrypt_token(account.access_token_encrypted)
        if not token:
            raise ValueError("Connected Slack account is missing access token.")

        payload = self._api_get(
            token,
            "conversations.history",
            params={"channel": conversation_id, "limit": max(1, min(limit, 200))},
        )
        user_cache: dict[str, str] = {}
        items = payload.get("messages") or []
        messages: list[SlackMessage] = []
        for item in reversed(items):
            user_id_raw = item.get("user")
            sender = (
                self._get_user_display_name(token, user_id_raw, user_cache)
                or item.get("username")
                or item.get("bot_id")
                or "Slack"
            )
            messages.append(
                SlackMessage(
                    ts=str(item.get("ts") or ""),
                    sender=sender,
                    user_id=user_id_raw,
                    text=item.get("text"),
                    subtype=item.get("subtype"),
                    thread_ts=item.get("thread_ts"),
                    has_attachments=bool(item.get("files")),
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
            raise ValueError("Connected Slack account is missing access token.")
        payload = self._api_post(
            token,
            "chat.postMessage",
            {
                "channel": conversation_id,
                "text": text,
            },
        )
        return {
            "channel": str(payload.get("channel") or conversation_id),
            "ts": str(payload.get("ts") or ""),
        }
