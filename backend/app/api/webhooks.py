"""Webhook endpoints for external push notifications.

Gmail Pub/Sub sends a POST here whenever a watched mailbox changes.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import re
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import get_db
from app.models import ConnectedAccount
from app.services.chat_storage_service import ChatStorageService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_slack_ts(ts_raw: str | None) -> datetime | None:
    if not ts_raw:
        return None
    try:
        return datetime.fromtimestamp(float(ts_raw), tz=timezone.utc)
    except Exception:
        return None


def _parse_iso_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


def _strip_html(value: str | None) -> str:
    if not value:
        return ""
    text = value.replace("<br>", " ").replace("<br/>", " ").replace("<br />", " ")
    text = re.sub(r"<[^>]+>", " ", text)
    text = text.replace("&nbsp;", " ").strip()
    return re.sub(r"\s+", " ", text).strip()


async def _emit_platform_event(*, user_id: str, platform: str, payload: dict) -> None:
    try:
        from app.core.socketio_server import emit_global, emit_to_user

        event_payload = {
            "platform": platform,
            "timestamp": _utcnow_iso(),
            "payload": payload,
        }
        await emit_to_user(user_id, "inbox_platform_event", event_payload)
        # Fallback broadcast for clients not joined to user rooms.
        await emit_global("inbox_platform_event", event_payload)
    except Exception:
        logger.debug("Failed to emit realtime platform event", exc_info=True)


def _verify_slack_signature(*, body: bytes, timestamp: str, signature: str) -> bool:
    if not settings.slack_signing_secret:
        return True
    # Basic replay protection.
    try:
        ts = int(timestamp)
    except Exception:
        return False
    if abs(time.time() - ts) > 60 * 5:
        return False
    basestring = f"v0:{timestamp}:{body.decode('utf-8')}".encode("utf-8")
    expected = "v0=" + hmac.new(
        settings.slack_signing_secret.encode("utf-8"),
        basestring,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


@router.post("/gmail")
async def gmail_push_notification(request: Request, db: Session = Depends(get_db)) -> dict:
    """Receive Gmail Pub/Sub push notifications.

    Google sends:
    {
        "message": {
            "data": "<base64-encoded JSON>",  # {"emailAddress": "...", "historyId": "..."}
            "messageId": "...",
            "publishTime": "..."
        },
        "subscription": "..."
    }
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON")

    message = body.get("message", {})
    data_b64 = message.get("data")

    if not data_b64:
        logger.warning("[Gmail Webhook] No data in push notification")
        return {"status": "ignored"}

    # Decode the Pub/Sub message
    try:
        payload = json.loads(base64.urlsafe_b64decode(data_b64))
    except Exception:
        logger.warning("[Gmail Webhook] Failed to decode push data")
        return {"status": "ignored"}

    email_address = payload.get("emailAddress", "").lower()
    history_id = payload.get("historyId")

    if not email_address or not history_id:
        logger.warning(f"[Gmail Webhook] Missing fields: {payload}")
        return {"status": "ignored"}

    logger.info(f"[Gmail Webhook] Push for {email_address} (historyId: {history_id})")

    account = db.execute(
        select(ConnectedAccount).where(
            ConnectedAccount.provider == "google",
            ConnectedAccount.account_email == email_address,
        )
    ).scalar_one_or_none()

    if not account:
        logger.warning(f"[Gmail Webhook] No account found for {email_address}")
        return {"status": "ignored"}

    # Dispatch Celery task for incremental sync.
    from app.workers.tasks import sync_from_push

    sync_from_push.delay(
        account_id=str(account.id),
        user_id=str(account.user_id),
        history_id=history_id,
    )

    logger.info(f"[Gmail Webhook] Queued sync task for {email_address}")

    return {"status": "ok"}


@router.post("/slack/events")
async def slack_events(request: Request, db: Session = Depends(get_db)) -> dict:
    """Slack Events API webhook endpoint."""
    raw_body = await request.body()
    if not raw_body:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty request body")

    if settings.slack_signing_secret:
        timestamp = request.headers.get("X-Slack-Request-Timestamp", "")
        signature = request.headers.get("X-Slack-Signature", "")
        if not _verify_slack_signature(body=raw_body, timestamp=timestamp, signature=signature):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Slack signature")

    try:
        body = json.loads(raw_body.decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON")

    # Required for Slack webhook URL verification.
    if body.get("type") == "url_verification":
        challenge = body.get("challenge")
        if not challenge:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing challenge")
        return {"challenge": challenge}

    event = body.get("event") or {}
    event_type = event.get("type")
    team_id = body.get("team_id")
    logger.info(
        "[Slack Webhook] Received event type=%s team_id=%s event_id=%s",
        event_type,
        team_id,
        body.get("event_id"),
    )
    if team_id:
        accounts = list(
            db.execute(
                select(ConnectedAccount).where(
                    ConnectedAccount.provider == "slack",
                    ConnectedAccount.provider_account_id == str(team_id),
                )
            ).scalars()
        )
        storage = ChatStorageService(db)
        event_id = str(body.get("event_id") or "")
        channel_type = str(event.get("channel_type") or "").strip().lower()
        is_message_event = event_type == "message"
        has_changes = False

        for account in accounts:
            meta = dict(account.account_metadata or {})
            meta["last_slack_event_at"] = _utcnow_iso()
            meta["last_slack_event_type"] = str(event_type or "")
            account.account_metadata = meta
            db.add(account)
            has_changes = True

            await _emit_platform_event(
                user_id=str(account.user_id),
                platform="slack",
                payload={
                    "event_id": body.get("event_id"),
                    "event_type": event_type,
                    "team_id": team_id,
                },
            )

            if not is_message_event:
                continue

            message_payload = event.get("message") if event.get("subtype") == "message_changed" else event
            if not isinstance(message_payload, dict):
                continue
            if message_payload.get("subtype") == "message_deleted":
                continue

            conversation_id = str(message_payload.get("channel") or event.get("channel") or "").strip()
            message_ts = str(message_payload.get("ts") or "").strip()
            if not conversation_id or not message_ts:
                continue

            sender_id = str(message_payload.get("user") or "").strip() or None
            sender = (
                str(message_payload.get("username") or "").strip()
                or sender_id
                or str(message_payload.get("bot_id") or "").strip()
                or "Slack"
            )
            text = str(message_payload.get("text") or "").strip() or None
            bot_id = str(message_payload.get("bot_id") or "").strip()
            from_me = bool(
                (sender_id and sender_id == str(meta.get("authed_user_id") or "").strip())
                or (bot_id and bot_id == str(meta.get("bot_user_id") or "").strip())
            )
            sent_at = _parse_slack_ts(message_ts)

            conversation = storage.upsert_conversation(
                user_id=account.user_id,
                account_id=account.id,
                platform="slack",
                external_conversation_id=conversation_id,
                sender=sender,
                preview=text,
                latest_received_at=sent_at,
                has_attachments=bool(message_payload.get("files")),
                is_im=channel_type in {"im", "mpim"},
                is_private=channel_type in {"group"},
                metadata={
                    "source": "webhook",
                    "event_id": event_id,
                },
            )
            storage.upsert_message(
                conversation=conversation,
                external_message_id=message_ts,
                sender=sender,
                sender_id=sender_id,
                text=text,
                direction="outbound" if from_me else "inbound",
                subtype=str(message_payload.get("subtype") or "").strip() or None,
                thread_ref=str(message_payload.get("thread_ts") or "").strip() or None,
                has_attachments=bool(message_payload.get("files")),
                sent_at=sent_at,
                raw_payload=message_payload,
                fallback_seed=event_id or message_ts,
            )
            has_changes = True
        if accounts and has_changes:
            db.commit()

    return {"status": "ok"}


@router.get("/teams/events")
async def teams_validation(validationToken: str = Query(..., alias="validationToken")) -> str:  # noqa: N803
    """Microsoft Graph subscription validation handshake."""
    return validationToken


@router.post("/teams/events")
async def teams_events(request: Request, db: Session = Depends(get_db)) -> dict:
    """Microsoft Graph change notifications for Teams chats/messages."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON")

    notifications = body.get("value") or []
    logger.info("[Teams Webhook] Received %s notifications", len(notifications))

    if notifications:
        storage = ChatStorageService(db)
        accounts = list(
            db.execute(
                select(ConnectedAccount).where(ConnectedAccount.provider == "teams")
            ).scalars()
        )
        accounts_by_user: dict[str, list[ConnectedAccount]] = {}
        for account in accounts:
            accounts_by_user.setdefault(str(account.user_id), []).append(account)
        touched_users: set[str] = set()
        has_changes = False

        for notification in notifications:
            tenant_id = str(notification.get("tenantId") or "").strip()
            change_type = str(notification.get("changeType") or "").strip()
            resource = str(notification.get("resource") or "").strip()
            resource_data = notification.get("resourceData")
            if not isinstance(resource_data, dict):
                resource_data = {}

            chat_id = str(
                resource_data.get("chatId")
                or resource_data.get("conversationId")
                or ""
            ).strip()
            message_id = str(resource_data.get("id") or "").strip()
            if (not chat_id or not message_id) and resource:
                chat_match = re.search(r"chats\('([^']+)'\)", resource)
                message_match = re.search(r"messages\('([^']+)'\)", resource)
                if not chat_id and chat_match:
                    chat_id = chat_match.group(1).strip()
                if not message_id and message_match:
                    message_id = message_match.group(1).strip()
            body_obj = resource_data.get("body") if isinstance(resource_data.get("body"), dict) else {}
            text = _strip_html(body_obj.get("content")) or None
            created_at = _parse_iso_dt(str(resource_data.get("createdDateTime") or "").strip() or None)
            from_obj = resource_data.get("from") if isinstance(resource_data.get("from"), dict) else {}
            user_obj = from_obj.get("user") if isinstance(from_obj.get("user"), dict) else {}
            sender = str(user_obj.get("displayName") or user_obj.get("id") or "Teams").strip()
            sender_id = str(user_obj.get("id") or "").strip() or None

            for account in accounts:
                meta = dict(account.account_metadata or {})
                account_tenant = str(meta.get("tenant") or "").strip()
                if tenant_id and account_tenant and tenant_id != account_tenant:
                    continue
                touched_users.add(str(account.user_id))
                await _emit_platform_event(
                    user_id=str(account.user_id),
                    platform="teams",
                    payload={
                        "change_type": change_type,
                        "resource": resource,
                        "tenant_id": tenant_id or account_tenant,
                    },
                )

                if (
                    change_type.lower() in {"created", "updated"}
                    and chat_id
                    and message_id
                ):
                    conversation = storage.upsert_conversation(
                        user_id=account.user_id,
                        account_id=account.id,
                        platform="teams",
                        external_conversation_id=chat_id,
                        sender=sender,
                        preview=text,
                        latest_received_at=created_at,
                        metadata={
                            "source": "webhook",
                            "resource": resource,
                        },
                        is_group=True,
                    )
                    storage.upsert_message(
                        conversation=conversation,
                        external_message_id=message_id,
                        sender=sender,
                        sender_id=sender_id,
                        text=text,
                        direction=(
                            "outbound"
                            if sender_id and sender_id == str(account.provider_account_id or "").strip()
                            else "inbound"
                        ),
                        subtype=None,
                        thread_ref=None,
                        has_attachments=bool(resource_data.get("attachments")),
                        sent_at=created_at,
                        raw_payload=notification,
                        fallback_seed=message_id,
                    )
                    has_changes = True

        for user_id in touched_users:
            user_accounts = accounts_by_user.get(user_id) or []
            for account in user_accounts:
                meta = dict(account.account_metadata or {})
                meta["last_teams_event_at"] = _utcnow_iso()
                account.account_metadata = meta
                db.add(account)
                has_changes = True

        if touched_users and has_changes:
            db.commit()

    return {"status": "ok"}
