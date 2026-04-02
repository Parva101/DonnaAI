"""Celery task definitions for sync/classification workflows."""

from __future__ import annotations

import asyncio
import logging
import traceback
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select

from app.core.celery_app import celery

logger = logging.getLogger(__name__)

RUNNING_SYNC_STATUSES = {"queued", "running"}
MAX_EMAIL_RETRIES = 3
BASE_RETRY_DELAY_SECONDS = 5


def _run_async(coro):
    """Run an async coroutine from a synchronous Celery task."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _is_rate_limit_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    markers = (
        "rate limit",
        "rate_limit",
        "resource_exhausted",
        "quota",
        "tokens per minute",
        "tokens per day",
        "429",
    )
    return any(marker in msg for marker in markers)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _job_status_payload(job) -> dict:
    def _iso(value):
        return value.isoformat() if value else None

    return {
        "job_id": str(job.id),
        "status": job.status,
        "stage": job.stage,
        "mode": job.mode,
        "accounts_total": int(job.accounts_total or 0),
        "accounts_done": int(job.accounts_done or 0),
        "fetched_total": int(job.fetched_total or 0),
        "classify_total": int(job.classify_total or 0),
        "classified_done": int(job.classified_done or 0),
        "failed_count": int(job.failed_count or 0),
        "remaining_pending": int(job.remaining_pending or 0),
        "error": job.error,
        "started_at": _iso(job.started_at),
        "finished_at": _iso(job.finished_at),
    }


async def _emit_job_status(user_id: UUID, job) -> None:
    try:
        from app.core.socketio_server import emit_global, emit_to_user

        payload = _job_status_payload(job)
        await emit_to_user(str(user_id), "email_sync_status", payload)
        # Backward-compatible broadcast for clients not joining user rooms.
        await emit_global("email_sync_status", payload)
    except Exception:
        logger.debug("[Sync Job %s] socket emit failed", job.id, exc_info=True)


@celery.task(name="health_check")
def health_check() -> dict[str, str]:
    """Trivial task to verify the worker is alive."""
    return {"status": "ok", "worker": "donnaai"}


@celery.task(name="run_email_sync_job", bind=True, max_retries=0)
def run_email_sync_job(
    self,
    job_id: str,
    user_id: str,
    account_ids: list[str] | None = None,
    classify_only: bool = False,
) -> dict:
    """Main background flow for email sync + classification progress jobs."""
    _run_async(
        _run_email_sync_job_async(
            job_id=UUID(job_id),
            user_id=UUID(user_id),
            account_ids=[UUID(a) for a in (account_ids or [])],
            classify_only=classify_only,
        )
    )
    return {"status": "done", "job_id": job_id}


@celery.task(name="sync_and_classify", bind=True, max_retries=2, default_retry_delay=30)
def sync_and_classify(self, account_id: str, user_id: str) -> dict:
    """Backward-compatible single-account sync/classify task wrapper."""
    from app.core.db import SessionLocal
    from app.models import EmailSyncJob, User

    db = SessionLocal()
    try:
        user_uuid = UUID(user_id)
        if db.get(User, user_uuid) is None:
            logger.warning("[sync_and_classify] User %s not found; skipping task", user_id)
            return {"status": "skipped", "reason": "user_not_found", "account_id": account_id}

        job = EmailSyncJob(
            user_id=user_uuid,
            status="queued",
            stage="queued",
            mode="sync_and_classify",
            accounts_total=1,
            accounts_done=0,
            fetched_total=0,
            classify_total=0,
            classified_done=0,
            failed_count=0,
            remaining_pending=0,
        )
        db.add(job)
        db.commit()
        db.refresh(job)
    finally:
        db.close()

    _run_async(
        _run_email_sync_job_async(
            job_id=job.id,
            user_id=UUID(user_id),
            account_ids=[UUID(account_id)],
            classify_only=False,
        )
    )
    return {"status": "done", "account_id": account_id, "job_id": str(job.id)}


async def _run_email_sync_job_async(
    *,
    job_id: UUID,
    user_id: UUID,
    account_ids: list[UUID],
    classify_only: bool,
) -> None:
    """Core async logic for sync + classify with durable progress updates."""
    from app.core.db import SessionLocal
    from app.models import ConnectedAccount, Email, EmailSyncJob
    from app.services.email_classifier import classify_emails_batch
    from app.services.gmail_service import GmailService

    db = SessionLocal()
    job: EmailSyncJob | None = None
    try:
        job = db.get(EmailSyncJob, job_id)
        if not job:
            logger.error("[Sync Job] Job %s not found", job_id)
            return

        job.status = "running"
        job.stage = "classifying" if classify_only else "syncing"
        job.error = None
        job.started_at = _utcnow()
        job.finished_at = None
        db.add(job)
        db.commit()
        await _emit_job_status(user_id, job)

        # Step 1: Sync from Gmail accounts.
        if not classify_only:
            valid_accounts: list[ConnectedAccount] = []
            for account_id in account_ids:
                account = db.get(ConnectedAccount, account_id)
                if not account:
                    continue
                if account.user_id != user_id or account.provider != "google":
                    continue
                scopes = account.scopes or ""
                if "gmail" not in scopes.lower():
                    continue
                valid_accounts.append(account)

            job.accounts_total = len(valid_accounts)
            job.accounts_done = 0
            job.fetched_total = 0
            db.add(job)
            db.commit()
            await _emit_job_status(user_id, job)

            for account in valid_accounts:
                try:
                    def _on_sync_progress(newly_synced: int) -> None:
                        job.fetched_total += newly_synced
                        db.add(job)
                        db.commit()

                    gmail = GmailService(db, account, progress_callback=_on_sync_progress)
                    new_emails = await gmail.sync_emails()
                    logger.info(
                        "[Sync Job %s] Synced %s new emails for %s",
                        job.id,
                        len(new_emails),
                        account.account_email,
                    )
                except Exception as exc:
                    job.failed_count += 1
                    logger.error(
                        "[Sync Job %s] Sync failed for %s: %s\n%s",
                        job.id,
                        account.account_email,
                        exc,
                        traceback.format_exc(),
                    )
                finally:
                    job.accounts_done += 1
                    db.add(job)
                    db.commit()
                    await _emit_job_status(user_id, job)

        # Step 2: Classify all remaining pending emails for the user.
        job.stage = "classifying"
        db.add(job)
        db.commit()

        pending_total = (
            db.execute(
                select(func.count())
                .select_from(Email)
                .where(
                    Email.user_id == user_id,
                    Email.category_source == "pending",
                )
            ).scalar()
            or 0
        )
        job.classify_total = int(pending_total)
        job.classified_done = 0
        job.remaining_pending = int(pending_total)
        db.add(job)
        db.commit()
        await _emit_job_status(user_id, job)

        if pending_total == 0:
            job.status = "completed"
            job.stage = "completed"
            job.finished_at = _utcnow()
            db.add(job)
            db.commit()
            await _emit_job_status(user_id, job)
            logger.info("[Sync Job %s] Nothing pending to classify", job.id)
            return

        pending_emails = db.execute(
            select(Email).where(
                Email.user_id == user_id,
                Email.category_source == "pending",
            )
        ).scalars().all()

        for email_obj in pending_emails:
            # If another process already classified it, skip.
            if email_obj.category_source != "pending":
                continue

            success = False
            for attempt in range(MAX_EMAIL_RETRIES):
                try:
                    category, source, needs_review = (await classify_emails_batch([email_obj]))[0]
                    email_obj.category = category
                    email_obj.category_source = source
                    email_obj.needs_review = needs_review
                    email_obj.human_reviewed_at = None
                    db.add(email_obj)
                    db.commit()

                    job.classified_done += 1
                    job.remaining_pending = (
                        db.execute(
                            select(func.count())
                            .select_from(Email)
                            .where(
                                Email.user_id == user_id,
                                Email.category_source == "pending",
                            )
                        ).scalar()
                        or 0
                    )
                    db.add(job)
                    db.commit()
                    if job.classified_done == 1 or job.classified_done % 10 == 0:
                        await _emit_job_status(user_id, job)
                    success = True
                    break
                except Exception as exc:
                    db.rollback()
                    if _is_rate_limit_error(exc):
                        job.status = "rate_limited"
                        job.stage = "failed"
                        job.error = str(exc)[:1200]
                        job.finished_at = _utcnow()
                        job.remaining_pending = (
                            db.execute(
                                select(func.count())
                                .select_from(Email)
                                .where(
                                    Email.user_id == user_id,
                                    Email.category_source == "pending",
                                )
                            ).scalar()
                            or 0
                        )
                        db.add(job)
                        db.commit()
                        await _emit_job_status(user_id, job)
                        logger.warning(
                            "[Sync Job %s] Stopped due to rate limit: %s",
                            job.id,
                            exc,
                        )
                        return

                    if attempt < MAX_EMAIL_RETRIES - 1:
                        wait = BASE_RETRY_DELAY_SECONDS * (2**attempt)
                        logger.warning(
                            "[Sync Job %s] Email %s attempt %s failed: %s (retry in %ss)",
                            job.id,
                            email_obj.id,
                            attempt + 1,
                            exc,
                            wait,
                        )
                        await asyncio.sleep(wait)
                        continue

                    job.failed_count += 1
                    db.add(job)
                    db.commit()
                    if job.failed_count == 1 or job.failed_count % 5 == 0:
                        await _emit_job_status(user_id, job)
                    logger.error(
                        "[Sync Job %s] Failed email %s after %s retries: %s\n%s",
                        job.id,
                        email_obj.id,
                        MAX_EMAIL_RETRIES,
                        exc,
                        traceback.format_exc(),
                    )

            if not success:
                # Leave as pending so retry can pick it up.
                continue

        remaining_pending = (
            db.execute(
                select(func.count())
                .select_from(Email)
                .where(
                    Email.user_id == user_id,
                    Email.category_source == "pending",
                )
            ).scalar()
            or 0
        )
        job.remaining_pending = int(remaining_pending)
        job.stage = "completed"
        job.finished_at = _utcnow()

        if remaining_pending > 0:
            job.status = "completed_with_errors"
            if not job.error:
                job.error = (
                    f"{remaining_pending} email(s) still pending. "
                    "Use retry to continue classification."
                )
        else:
            job.status = "completed"
            job.error = None

        db.add(job)
        db.commit()
        await _emit_job_status(user_id, job)
        logger.info(
            "[Sync Job %s] Completed with status=%s, classified=%s/%s, remaining=%s",
            job.id,
            job.status,
            job.classified_done,
            job.classify_total,
            job.remaining_pending,
        )

    except Exception as exc:
        logger.error("[Sync Job %s] Fatal failure: %s\n%s", job_id, exc, traceback.format_exc())
        if job:
            try:
                db.rollback()
                job.status = "failed"
                job.stage = "failed"
                job.error = str(exc)[:1200]
                job.finished_at = _utcnow()
                db.add(job)
                db.commit()
                await _emit_job_status(user_id, job)
            except Exception:
                pass
    finally:
        db.close()


@celery.task(name="sync_from_push", bind=True, max_retries=3, default_retry_delay=10)
def sync_from_push(self, account_id: str, user_id: str, history_id: str) -> dict:
    """Triggered by Gmail Pub/Sub webhook (incremental sync + classify new)."""
    _run_async(_sync_from_push_async(UUID(account_id), UUID(user_id), history_id))
    return {"status": "done", "account_id": account_id}


async def _sync_from_push_async(account_id: UUID, user_id: UUID, history_id: str) -> None:
    """Incremental sync triggered by Gmail push notification."""
    from app.core.db import SessionLocal
    from app.models import ConnectedAccount
    from app.services.email_classifier import classify_emails_batch
    from app.services.gmail_service import GmailService

    db = SessionLocal()
    try:
        account = db.get(ConnectedAccount, account_id)
        if not account:
            logger.error("[Push Sync] Account %s not found", account_id)
            return

        gmail = GmailService(db, account)
        new_emails = await gmail.sync_emails()
        logger.info("[Push Sync] %s new emails for %s", len(new_emails), account.account_email)

        for email_obj in new_emails:
            try:
                category, source, needs_review = (await classify_emails_batch([email_obj]))[0]
                email_obj.category = category
                email_obj.category_source = source
                email_obj.needs_review = needs_review
                email_obj.human_reviewed_at = None
                db.add(email_obj)
                db.commit()
            except Exception as exc:
                db.rollback()
                logger.warning("[Push Sync] Classification failed for %s: %s", email_obj.id, exc)

    except Exception as exc:
        logger.error("[Push Sync] Failed: %s\n%s", exc, traceback.format_exc())
    finally:
        db.close()


@celery.task(name="renew_gmail_watches")
def renew_gmail_watches() -> dict:
    """Renew Gmail Pub/Sub watches for all connected accounts."""
    _run_async(_renew_watches_async())
    return {"status": "done"}


async def _renew_watches_async() -> None:
    """Renew watches for all Gmail accounts with push enabled."""
    from app.core.config import settings
    from app.core.db import SessionLocal
    from app.models import ConnectedAccount
    from app.services.gmail_service import GmailService

    if not settings.gmail_pubsub_topic:
        logger.warning("[Watch Renew] GMAIL_PUBSUB_TOPIC not configured, skipping")
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
                logger.info("[Watch Renew] Renewed for %s", account.account_email)
            except Exception as exc:
                logger.error("[Watch Renew] Failed for %s: %s", account.account_email, exc)
    finally:
        db.close()


@celery.task(name="fetch_news_updates")
def fetch_news_updates() -> dict:
    """Fetch news from configured sources for all users."""
    _run_async(_fetch_news_updates_async())
    return {"status": "done"}


async def _fetch_news_updates_async() -> None:
    from app.core.db import SessionLocal
    from app.models import User
    from app.services.news_service import NewsService

    db = SessionLocal()
    try:
        users = list(db.execute(select(User)).scalars())
        for user in users:
            try:
                created = await NewsService(db).fetch_for_user(user_id=user.id, limit_per_source=20)
                logger.info("[News Fetch] user=%s new_articles=%s", user.id, created)
            except Exception as exc:
                logger.error("[News Fetch] user=%s failed: %s", user.id, exc)
    finally:
        db.close()


@celery.task(name="generate_daily_briefings")
def generate_daily_briefings() -> dict:
    """Generate a daily digest snapshot for each user."""
    _run_async(_generate_daily_briefings_async())
    return {"status": "done"}


async def _generate_daily_briefings_async() -> None:
    from app.core.db import SessionLocal
    from app.models import User
    from app.services.notification_service import NotificationService

    db = SessionLocal()
    try:
        users = list(db.execute(select(User)).scalars())
        for user in users:
            try:
                summary, items = NotificationService(db).build_daily_digest(user_id=user.id)
                logger.info(
                    "[Daily Briefing] user=%s items=%s summary=%s",
                    user.id,
                    len(items),
                    summary,
                )
            except Exception as exc:
                logger.error("[Daily Briefing] user=%s failed: %s", user.id, exc)
    finally:
        db.close()
