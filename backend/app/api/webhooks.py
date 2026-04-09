"""Webhook endpoints for external push notifications.

Gmail Pub/Sub sends a POST here whenever a watched mailbox changes.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import get_db
from app.models import ConnectedAccount

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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
        for account in accounts:
            meta = dict(account.account_metadata or {})
            meta["last_slack_event_at"] = _utcnow_iso()
            meta["last_slack_event_type"] = str(event_type or "")
            account.account_metadata = meta
            db.add(account)
            await _emit_platform_event(
                user_id=str(account.user_id),
                platform="slack",
                payload={
                    "event_id": body.get("event_id"),
                    "event_type": event_type,
                    "team_id": team_id,
                },
            )
        if accounts:
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
        accounts = list(
            db.execute(
                select(ConnectedAccount).where(ConnectedAccount.provider == "teams")
            ).scalars()
        )
        account_by_user = {str(a.user_id): a for a in accounts}
        touched_users: set[str] = set()

        for notification in notifications:
            tenant_id = str(notification.get("tenantId") or "").strip()
            change_type = str(notification.get("changeType") or "").strip()
            resource = str(notification.get("resource") or "").strip()

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

        for user_id in touched_users:
            account = account_by_user.get(user_id)
            if not account:
                continue
            meta = dict(account.account_metadata or {})
            meta["last_teams_event_at"] = _utcnow_iso()
            account.account_metadata = meta
            db.add(account)

        if touched_users:
            db.commit()

    return {"status": "ok"}
