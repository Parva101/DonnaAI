"""Webhook endpoints for external push notifications.

Gmail Pub/Sub sends a POST here whenever a watched mailbox changes.
"""

from __future__ import annotations

import base64
import json
import logging

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select

from app.core.db import SessionLocal
from app.models import ConnectedAccount

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/gmail")
async def gmail_push_notification(request: Request) -> dict:
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

    # Look up the connected account by email
    db = SessionLocal()
    try:
        account = db.execute(
            select(ConnectedAccount).where(
                ConnectedAccount.provider == "google",
                ConnectedAccount.account_email == email_address,
            )
        ).scalar_one_or_none()

        if not account:
            logger.warning(f"[Gmail Webhook] No account found for {email_address}")
            return {"status": "ignored"}

        # Dispatch Celery task for incremental sync
        from app.workers.tasks import sync_from_push

        sync_from_push.delay(
            account_id=str(account.id),
            user_id=str(account.user_id),
            history_id=history_id,
        )

        logger.info(f"[Gmail Webhook] Queued sync task for {email_address}")

    finally:
        db.close()

    return {"status": "ok"}
