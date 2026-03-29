"""Celery task definitions.

All background tasks live here. Import the celery app and decorate with @celery.task.

Start a worker:
    celery -A app.core.celery_app worker --loglevel=info

Start beat (periodic tasks):
    celery -A app.core.celery_app beat --loglevel=info
"""

from __future__ import annotations

import asyncio
import logging
import traceback
from uuid import UUID

from app.core.celery_app import celery

logger = logging.getLogger(__name__)


def _run_async(coro):
    """Run an async coroutine from synchronous Celery task."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery.task(name="health_check")
def health_check() -> dict[str, str]:
    """Trivial task to verify the worker is alive."""
    return {"status": "ok", "worker": "donnaai"}


@celery.task(name="sync_and_classify", bind=True, max_retries=2, default_retry_delay=30)
def sync_and_classify(self, account_id: str, user_id: str) -> dict:
    """Sync emails from Gmail and classify pending ones.

    This is the main task dispatched by the /sync endpoint.
    Runs sync first, then classifies any pending emails.
    """
    _run_async(_sync_and_classify_async(UUID(account_id), UUID(user_id)))
    return {"status": "done", "account_id": account_id}


async def _sync_and_classify_async(account_id: UUID, user_id: UUID) -> None:
    """Core async logic for sync + classify."""
    from sqlalchemy import select
    from app.core.db import SessionLocal
    from app.services.gmail_service import GmailService
    from app.services.email_classifier import classify_emails_batch
    from app.models import ConnectedAccount, Email

    db = SessionLocal()
    try:
        account = db.get(ConnectedAccount, account_id)
        if not account:
            logger.error(f"[Celery Sync] Account {account_id} not found")
            return

        # ── Step 1: Sync ────────────────────────────────────────
        try:
            gmail = GmailService(db, account)
            new_emails = await gmail.sync_emails()
            logger.info(f"[Celery Sync] Fetched {len(new_emails)} new emails for {account.account_email}")
        except Exception as e:
            logger.error(f"[Celery Sync] Sync failed: {e}\n{traceback.format_exc()}")

        # ── Step 2: Classify pending ────────────────────────────
        pending = db.execute(
            select(Email).where(
                Email.user_id == user_id,
                Email.category_source == "pending",
            )
        ).scalars().all()

        if not pending:
            logger.info("[Celery Classify] No pending emails")
            return

        logger.info(f"[Celery Classify] {len(pending)} pending emails to classify")

        CHUNK_SIZE = 100
        CHUNK_DELAY = 2
        MAX_RETRIES = 3
        BACKOFF_BASE = 10
        total_classified = 0

        for i in range(0, len(pending), CHUNK_SIZE):
            chunk = pending[i : i + CHUNK_SIZE]
            success = False

            for attempt in range(MAX_RETRIES):
                try:
                    results = await classify_emails_batch(chunk)
                    for email_obj, (category, source, needs_review) in zip(chunk, results):
                        email_obj.category = category
                        email_obj.category_source = source
                        email_obj.needs_review = needs_review
                        email_obj.human_reviewed_at = None
                    db.commit()
                    total_classified += len(chunk)
                    success = True
                    logger.info(f"[Celery Classify] {total_classified}/{len(pending)} classified")
                    break
                except Exception as e:
                    db.rollback()
                    wait = BACKOFF_BASE * (2 ** attempt)
                    logger.warning(
                        f"[Celery Classify] Chunk {i // CHUNK_SIZE} attempt {attempt + 1} "
                        f"failed: {e} — retrying in {wait}s"
                    )
                    await asyncio.sleep(wait)

            if not success:
                logger.error(f"[Celery Classify] Chunk {i // CHUNK_SIZE} failed after {MAX_RETRIES} retries")

            if success:
                await asyncio.sleep(CHUNK_DELAY)

        logger.info(f"[Celery Classify] Done — {total_classified}/{len(pending)} classified")

    finally:
        db.close()


@celery.task(name="sync_from_push", bind=True, max_retries=3, default_retry_delay=10)
def sync_from_push(self, account_id: str, user_id: str, history_id: str) -> dict:
    """Triggered by Gmail Pub/Sub webhook — incremental sync only.

    Does NOT classify (to keep push handling fast).
    Classification is triggered separately or via periodic task.
    """
    _run_async(_sync_from_push_async(UUID(account_id), UUID(user_id), history_id))
    return {"status": "done", "account_id": account_id}


async def _sync_from_push_async(account_id: UUID, user_id: UUID, history_id: str) -> None:
    """Incremental sync triggered by Gmail push notification."""
    from app.core.db import SessionLocal
    from app.services.gmail_service import GmailService
    from app.models import ConnectedAccount

    db = SessionLocal()
    try:
        account = db.get(ConnectedAccount, account_id)
        if not account:
            logger.error(f"[Push Sync] Account {account_id} not found")
            return

        gmail = GmailService(db, account)
        new_emails = await gmail.sync_emails()
        logger.info(f"[Push Sync] {len(new_emails)} new emails for {account.account_email}")

        # Classify just the new emails if any
        if new_emails:
            from app.services.email_classifier import classify_emails_batch

            try:
                results = await classify_emails_batch(new_emails)
                for email_obj, (category, source, needs_review) in zip(new_emails, results):
                    email_obj.category = category
                    email_obj.category_source = source
                    email_obj.needs_review = needs_review
                    email_obj.human_reviewed_at = None
                db.commit()
                logger.info(f"[Push Sync] Classified {len(new_emails)} new emails")
            except Exception as e:
                db.rollback()
                logger.warning(f"[Push Sync] Classification failed: {e}")

    except Exception as e:
        logger.error(f"[Push Sync] Failed: {e}\n{traceback.format_exc()}")
    finally:
        db.close()


@celery.task(name="renew_gmail_watches")
def renew_gmail_watches() -> dict:
    """Renew Gmail Pub/Sub watches for all connected accounts.

    Scheduled to run every 6 days via Celery Beat (watches expire after 7).
    """
    _run_async(_renew_watches_async())
    return {"status": "done"}


async def _renew_watches_async() -> None:
    """Renew watches for all Gmail accounts with push enabled."""
    from sqlalchemy import select
    from app.core.db import SessionLocal
    from app.core.config import settings
    from app.services.gmail_service import GmailService
    from app.models import ConnectedAccount

    if not settings.gmail_pubsub_topic:
        logger.warning("[Watch Renew] GMAIL_PUBSUB_TOPIC not configured — skipping")
        return

    db = SessionLocal()
    try:
        accounts = db.execute(
            select(ConnectedAccount).where(ConnectedAccount.provider == "google")
        ).scalars().all()

        gmail_accounts = [a for a in accounts if a.scopes and "gmail" in a.scopes.lower()]

        for account in gmail_accounts:
            try:
                gmail = GmailService(db, account)
                await gmail.watch(settings.gmail_pubsub_topic)
                logger.info(f"[Watch Renew] Renewed for {account.account_email}")
            except Exception as e:
                logger.error(f"[Watch Renew] Failed for {account.account_email}: {e}")

    finally:
        db.close()
