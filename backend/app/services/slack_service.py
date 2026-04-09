"""Slack read/send helpers with OpenClaw-first fallback to Slack Web API."""

from __future__ import annotations

import logging
import random
import time
from datetime import datetime, timezone
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.token_crypto import decrypt_token
from app.models import ConnectedAccount
from app.schemas.slack import SlackConversationSummary, SlackMessage
from app.services.openclaw_gateway_client import OpenClawGatewayClient

logger = logging.getLogger(__name__)

SLACK_API_BASE = "https://slack.com/api"
SLACK_AUTH_ERRORS = {
    "account_inactive",
    "invalid_auth",
    "token_revoked",
    "token_expired",
    "not_authed",
    "org_login_required",
    "team_access_not_granted",
    "missing_scope",
    "invalid_token",
}
SLACK_TRANSIENT_ERRORS = {
    "internal_error",
    "ratelimited",
    "request_timeout",
}
SLACK_MAX_RETRIES = 3
SLACK_BASE_RETRY_SECONDS = 1.0
SLACK_MAX_RETRY_SECONDS = 20.0


class SlackService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.openclaw_enabled = bool(settings.openclaw_enable_slack)
        self.openclaw = OpenClawGatewayClient(
            channel=(settings.openclaw_slack_channel or "slack").strip().lower() or "slack",
            account_id=(settings.openclaw_slack_account_id or "").strip() or None,
        )

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
        base = min(SLACK_BASE_RETRY_SECONDS * (2 ** max(attempt - 1, 0)), SLACK_MAX_RETRY_SECONDS)
        jitter = random.uniform(0.0, 0.25)
        return max(base + jitter, retry_after)

    def _api_request(
        self,
        *,
        token: str,
        method: str,
        http_method: str,
        params: dict | None = None,
        payload: dict | None = None,
    ) -> dict:
        last_error: Exception | None = None
        for attempt in range(1, SLACK_MAX_RETRIES + 1):
            try:
                with httpx.Client(timeout=20) as client:
                    response = client.request(
                        http_method,
                        f"{SLACK_API_BASE}/{method}",
                        headers={"Authorization": f"Bearer {token}"},
                        params=params or None,
                        json=payload or None,
                    )
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_error = exc
                if attempt >= SLACK_MAX_RETRIES:
                    break
                delay = self._compute_retry_delay(attempt)
                logger.warning(
                    "Slack API %s transport error (attempt %s/%s): %s. Retrying in %.2fs.",
                    method,
                    attempt,
                    SLACK_MAX_RETRIES,
                    exc,
                    delay,
                )
                time.sleep(delay)
                continue

            status_code = response.status_code
            if status_code == 429:
                retry_after = self._parse_retry_after(response.headers.get("Retry-After"))
                if attempt >= SLACK_MAX_RETRIES:
                    raise RuntimeError(
                        f"Slack API rate limited for `{method}` after {attempt} attempts."
                    )
                delay = self._compute_retry_delay(attempt, retry_after=retry_after)
                logger.warning(
                    "Slack API %s rate limited (attempt %s/%s). Retrying in %.2fs.",
                    method,
                    attempt,
                    SLACK_MAX_RETRIES,
                    delay,
                )
                time.sleep(delay)
                continue

            if status_code in {500, 502, 503, 504}:
                if attempt >= SLACK_MAX_RETRIES:
                    raise RuntimeError(
                        f"Slack API `{method}` failed with HTTP {status_code} after retries."
                    )
                delay = self._compute_retry_delay(attempt)
                logger.warning(
                    "Slack API %s transient HTTP %s (attempt %s/%s). Retrying in %.2fs.",
                    method,
                    status_code,
                    attempt,
                    SLACK_MAX_RETRIES,
                    delay,
                )
                time.sleep(delay)
                continue

            if status_code in {401, 403}:
                raise ValueError(
                    "Slack access token is invalid or missing required scope. Reconnect Slack."
                )

            response.raise_for_status()
            data = response.json()
            if data.get("ok"):
                return data

            error_code = str(data.get("error") or "").strip()
            if error_code in SLACK_AUTH_ERRORS:
                raise ValueError(
                    "Slack access token is invalid or missing required scope. Reconnect Slack."
                )
            if error_code in SLACK_TRANSIENT_ERRORS:
                if attempt >= SLACK_MAX_RETRIES:
                    raise RuntimeError(
                        f"Slack API `{method}` transient error `{error_code}` persisted after retries."
                    )
                delay = self._compute_retry_delay(attempt)
                logger.warning(
                    "Slack API %s transient error %s (attempt %s/%s). Retrying in %.2fs.",
                    method,
                    error_code,
                    attempt,
                    SLACK_MAX_RETRIES,
                    delay,
                )
                time.sleep(delay)
                continue

            raise RuntimeError(error_code or f"Slack API call failed: {method}")

        raise RuntimeError(
            f"Slack API call `{method}` failed after {SLACK_MAX_RETRIES} attempts: {last_error}"
        )

    def _api_get(self, token: str, method: str, params: dict | None = None) -> dict:
        return self._api_request(
            token=token,
            method=method,
            http_method="GET",
            params=params,
        )

    def _api_post(self, token: str, method: str, payload: dict) -> dict:
        return self._api_request(
            token=token,
            method=method,
            http_method="POST",
            payload=payload,
        )

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

    @staticmethod
    def _is_openclaw_im(session: dict) -> bool:
        chat_type = str(session.get("chatType") or "").strip().lower()
        kind = str(session.get("kind") or "").strip().lower()
        return chat_type in {"im", "dm", "direct"} or kind in {"im", "dm", "direct"}

    @staticmethod
    def _is_openclaw_private(session: dict) -> bool:
        chat_type = str(session.get("chatType") or "").strip().lower()
        kind = str(session.get("kind") or "").strip().lower()
        return chat_type in {"private", "private_channel"} or kind in {"private", "private_channel"}

    @staticmethod
    def _openclaw_sender(session: dict) -> str:
        return str(
            session.get("subject")
            or session.get("displayName")
            or session.get("derivedTitle")
            or session.get("lastTo")
            or session.get("key")
            or "Slack"
        )

    @staticmethod
    def _openclaw_name(session: dict) -> str | None:
        candidate = session.get("displayName") or session.get("derivedTitle") or session.get("subject")
        if not isinstance(candidate, str):
            return None
        text = candidate.strip()
        return text or None

    @staticmethod
    def _openclaw_ts(payload: dict) -> str:
        ts_raw = payload.get("ts") or payload.get("timestamp")
        ts_ms = OpenClawGatewayClient.to_int(ts_raw)
        if ts_ms is not None:
            return f"{ts_ms / 1000:.6f}"
        return str(ts_raw or "")

    def _list_conversations_openclaw(
        self,
        *,
        user_id: UUID,
        account_id: UUID | None,
        search: str | None,
        unread_only: bool,
    ) -> list[SlackConversationSummary]:
        accounts = self._list_accounts(user_id=user_id, account_id=account_id)
        if not accounts:
            return []
        account = accounts[0]
        snapshot = self.openclaw.channel_snapshot()
        if not snapshot or not bool(snapshot.get("configured")):
            raise ValueError("OpenClaw Slack channel is not configured.")

        sessions = self.openclaw.list_sessions(
            limit=1000,
            search=search,
            include_last_message=True,
            include_derived_titles=True,
        )

        output: list[SlackConversationSummary] = []
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
                SlackConversationSummary(
                    account_id=account.id,
                    conversation_id=session_key,
                    name=self._openclaw_name(session),
                    sender=self._openclaw_sender(session),
                    preview=preview,
                    unread_count=max(unread_count, 0),
                    message_count=max(message_count, 0),
                    has_attachments=bool(session.get("lastMessageHasAttachments")),
                    latest_received_at=latest_received_at,
                    is_im=self._is_openclaw_im(session),
                    is_private=self._is_openclaw_private(session),
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
    ) -> list[SlackMessage]:
        # Keep account existence semantics aligned with native path.
        self._get_account(user_id=user_id, account_id=account_id)
        rows = self.openclaw.chat_history(
            session_key=conversation_id,
            limit=max(min(limit * 2, 1000), limit),
        )
        parsed: list[tuple[int, SlackMessage]] = []
        for idx, message in enumerate(rows):
            if not isinstance(message, dict):
                continue
            role = str(message.get("role") or "").strip().lower()
            if role in {"tool", "system"}:
                continue

            text = OpenClawGatewayClient.extract_text_from_message(message)
            if not text:
                continue

            ts_ms = OpenClawGatewayClient.to_int(message.get("timestamp"))
            ts = f"{ts_ms / 1000:.6f}" if ts_ms is not None else str(message.get("id") or f"{idx}")

            sender = (
                message.get("authorName")
                or message.get("sender")
                or ("You" if role == "assistant" else "Slack")
            )
            user_id_raw = message.get("authorId") or message.get("userId") or message.get("user")
            subtype = role or (str(message.get("type") or "").strip() or None)
            thread_ts = message.get("threadTs") or message.get("thread_ts")
            has_attachments = bool(message.get("attachments") or message.get("files"))

            parsed.append(
                (
                    ts_ms or idx,
                    SlackMessage(
                        ts=ts,
                        sender=str(sender) if sender is not None else None,
                        user_id=str(user_id_raw) if user_id_raw is not None else None,
                        text=text,
                        subtype=subtype,
                        thread_ts=str(thread_ts) if thread_ts is not None else None,
                        has_attachments=has_attachments,
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
        # Keep account existence semantics aligned with native path.
        self._get_account(user_id=user_id, account_id=account_id)
        payload = self.openclaw.chat_send(session_key=conversation_id, text=text)
        ts = self._openclaw_ts(payload)
        if ts:
            return {"channel": conversation_id, "ts": ts}

        fallback_payload = self.openclaw.raw_send(to=conversation_id, text=text)
        return {"channel": conversation_id, "ts": self._openclaw_ts(fallback_payload)}

    def _list_conversations_native(
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

    def _list_messages_native(
        self,
        *,
        user_id: UUID,
        conversation_id: str,
        account_id: UUID | None = None,
        limit: int = 50,
    ) -> list[SlackMessage]:
        conversation_id = conversation_id.strip()
        if not conversation_id:
            raise ValueError("Slack conversation id cannot be empty.")
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
            raise ValueError("Slack conversation id cannot be empty.")
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

    def list_conversations(
        self,
        *,
        user_id: UUID,
        account_id: UUID | None = None,
        search: str | None = None,
        unread_only: bool = False,
    ) -> list[SlackConversationSummary]:
        if self.openclaw_enabled:
            try:
                return self._list_conversations_openclaw(
                    user_id=user_id,
                    account_id=account_id,
                    search=search,
                    unread_only=unread_only,
                )
            except Exception as exc:
                logger.warning("Slack OpenClaw path failed, falling back to Slack API: %s", exc)

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
    ) -> list[SlackMessage]:
        if self.openclaw_enabled:
            try:
                return self._list_messages_openclaw(
                    user_id=user_id,
                    conversation_id=conversation_id,
                    account_id=account_id,
                    limit=limit,
                )
            except Exception as exc:
                logger.warning("Slack OpenClaw history failed, falling back to Slack API: %s", exc)

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
            raise ValueError("Slack conversation id cannot be empty.")

        if self.openclaw_enabled:
            try:
                return self._send_message_openclaw(
                    user_id=user_id,
                    conversation_id=conversation_id,
                    text=message_text,
                    account_id=account_id,
                )
            except Exception as exc:
                logger.warning("Slack OpenClaw send failed, falling back to Slack API: %s", exc)

        return self._send_message_native(
            user_id=user_id,
            conversation_id=conversation_id,
            text=message_text,
            account_id=account_id,
        )
