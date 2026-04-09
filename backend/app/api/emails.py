"""Email Hub API routes."""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.db import get_db
from app.models import ConnectedAccount, EmailSyncJob, User

logger = logging.getLogger(__name__)
from app.schemas.email import (
    EmailCategoryCount,
    EmailComposeRequest,
    EmailListResponse,
    EmailRead,
    EmailSendResponse,
    EmailSummary,
    EmailSyncRequest,
    EmailSyncStatus,
    EmailUpdate,
    SyncAllStatus,
)
from app.services.email_service import EmailService

router = APIRouter(prefix="/emails", tags=["emails"])
RUNNING_SYNC_STATUSES = {"queued", "running"}


def _job_to_status(job: EmailSyncJob) -> EmailSyncStatus:
    return EmailSyncStatus(
        job_id=job.id,
        status=job.status,
        stage=job.stage,
        mode=job.mode,
        accounts_total=job.accounts_total,
        accounts_done=job.accounts_done,
        fetched_total=job.fetched_total,
        classify_total=job.classify_total,
        classified_done=job.classified_done,
        failed_count=job.failed_count,
        remaining_pending=job.remaining_pending,
        error=job.error,
        started_at=job.started_at,
        finished_at=job.finished_at,
    )


def _latest_sync_job(db: Session, user_id) -> EmailSyncJob | None:
    stmt = (
        select(EmailSyncJob)
        .where(EmailSyncJob.user_id == user_id)
        .order_by(EmailSyncJob.created_at.desc())
        .limit(1)
    )
    return db.execute(stmt).scalar_one_or_none()


def _active_sync_job(db: Session, user_id) -> EmailSyncJob | None:
    stmt = (
        select(EmailSyncJob)
        .where(
            EmailSyncJob.user_id == user_id,
            EmailSyncJob.status.in_(RUNNING_SYNC_STATUSES),
        )
        .order_by(EmailSyncJob.created_at.desc())
        .limit(1)
    )
    return db.execute(stmt).scalar_one_or_none()


@router.get("", response_model=EmailListResponse)
def list_emails(
    category: str | None = Query(None, description="Filter by category (e.g. 'work', 'school')"),
    account_id: UUID | None = Query(None, description="Filter by connected account"),
    is_read: bool | None = Query(None, description="Filter read/unread"),
    search: str | None = Query(None, description="Search subject, sender, snippet"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> EmailListResponse:
    svc = EmailService(db)
    emails, total = svc.list_emails(
        current_user.id,
        category=category,
        account_id=account_id,
        is_read=is_read,
        search=search,
        limit=limit,
        offset=offset,
    )
    categories = svc.get_category_counts(current_user.id, account_id=account_id)
    return EmailListResponse(
        emails=[EmailSummary.model_validate(e) for e in emails],
        total=total,
        categories=categories,
    )


@router.get("/categories", response_model=list[EmailCategoryCount])
def get_email_categories(
    account_id: UUID | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[EmailCategoryCount]:
    return EmailService(db).get_category_counts(current_user.id, account_id=account_id)


@router.post("/send", response_model=EmailSendResponse)
async def send_email(
    payload: EmailComposeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> EmailSendResponse:
    """Send an email via a connected Gmail account."""
    from app.services.gmail_service import GmailService
    from sqlalchemy import select

    # Verify the account belongs to the user and is Google
    stmt = select(ConnectedAccount).where(
        ConnectedAccount.id == payload.account_id,
        ConnectedAccount.user_id == current_user.id,
        ConnectedAccount.provider == "google",
    )
    account = db.execute(stmt).scalar_one_or_none()
    if account is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Google account not found. Connect Gmail first.",
        )

    scopes = account.scopes or ""
    if "gmail" not in scopes.lower():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Gmail access not granted. Reconnect Google with Gmail permissions.",
        )

    gmail = GmailService(db, account)
    try:
        result = await gmail.send_message(
            to=payload.to,
            cc=payload.cc,
            bcc=payload.bcc,
            subject=payload.subject,
            body=payload.body,
            in_reply_to=payload.in_reply_to,
            thread_id=payload.thread_id,
        )
        return EmailSendResponse(
            status="sent",
            gmail_message_id=result.get("id"),
            thread_id=result.get("threadId"),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to send email via Gmail: {e}",
        )


@router.post("/sync/all", response_model=SyncAllStatus)
async def sync_all_emails(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SyncAllStatus:
    """Create a sync job for all Gmail accounts and queue Celery worker."""
    from app.workers.tasks import run_email_sync_job

    stmt = select(ConnectedAccount).where(
        ConnectedAccount.user_id == current_user.id,
        ConnectedAccount.provider == "google",
    )
    accounts = db.execute(stmt).scalars().all()
    gmail_accounts = [a for a in accounts if a.scopes and "gmail" in a.scopes.lower()]

    if not gmail_accounts:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No Gmail accounts found. Connect Gmail first.",
        )

    active = _active_sync_job(db, current_user.id)
    if active:
        return SyncAllStatus(job=_job_to_status(active))

    job = EmailSyncJob(
        user_id=current_user.id,
        status="queued",
        stage="queued",
        mode="sync_and_classify",
        accounts_total=len(gmail_accounts),
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

    run_email_sync_job.delay(
        job_id=str(job.id),
        user_id=str(current_user.id),
        account_ids=[str(a.id) for a in gmail_accounts],
        classify_only=False,
    )

    return SyncAllStatus(
        job=_job_to_status(job),
    )


@router.post("/sync", response_model=EmailSyncStatus)
async def sync_emails(
    payload: EmailSyncRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> EmailSyncStatus:
    """Create a sync job for a specific Gmail account and queue worker."""
    from app.workers.tasks import run_email_sync_job

    # Verify the account belongs to the user and is Google
    stmt = select(ConnectedAccount).where(
        ConnectedAccount.id == payload.account_id,
        ConnectedAccount.user_id == current_user.id,
        ConnectedAccount.provider == "google",
    )
    account = db.execute(stmt).scalar_one_or_none()
    if account is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Google account not found. Connect Gmail first.",
        )

    scopes = account.scopes or ""
    if "gmail" not in scopes.lower():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Gmail access not granted. Reconnect Google with Gmail permissions.",
        )

    active = _active_sync_job(db, current_user.id)
    if active:
        return _job_to_status(active)

    job = EmailSyncJob(
        user_id=current_user.id,
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

    run_email_sync_job.delay(
        job_id=str(job.id),
        user_id=str(current_user.id),
        account_ids=[str(account.id)],
        classify_only=False,
    )

    return _job_to_status(job)


@router.post("/sync/retry", response_model=EmailSyncStatus)
async def retry_pending_classification(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> EmailSyncStatus:
    """Retry classification for remaining pending emails without fetching."""
    from app.workers.tasks import run_email_sync_job

    active = _active_sync_job(db, current_user.id)
    if active:
        return _job_to_status(active)

    job = EmailSyncJob(
        user_id=current_user.id,
        status="queued",
        stage="queued",
        mode="classify_pending",
        accounts_total=0,
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

    run_email_sync_job.delay(
        job_id=str(job.id),
        user_id=str(current_user.id),
        account_ids=[],
        classify_only=True,
    )

    return _job_to_status(job)


@router.get("/sync/status", response_model=EmailSyncStatus)
def get_sync_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> EmailSyncStatus:
    """Return the latest sync/classification job for the current user."""
    job = _latest_sync_job(db, current_user.id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No sync job found for this user.",
        )
    return _job_to_status(job)


@router.post("/watch")
async def watch_email_account(
    payload: EmailSyncRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Enable Gmail Pub/Sub push notifications for an account."""
    from sqlalchemy import select
    from app.services.gmail_service import GmailService
    from app.core.config import settings

    stmt = select(ConnectedAccount).where(
        ConnectedAccount.id == payload.account_id,
        ConnectedAccount.user_id == current_user.id,
        ConnectedAccount.provider == "google",
    )
    account = db.execute(stmt).scalar_one_or_none()
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Google account not found.")

    if not settings.gmail_pubsub_topic:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Gmail Pub/Sub topic not configured.",
        )

    gmail = GmailService(db, account)
    data = await gmail.watch(settings.gmail_pubsub_topic)
    return {"status": "watching", "expiration": data.get("expiration")}


@router.post("/unwatch")
async def unwatch_email_account(
    payload: EmailSyncRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Disable Gmail Pub/Sub push notifications for an account."""
    from sqlalchemy import select
    from app.services.gmail_service import GmailService

    stmt = select(ConnectedAccount).where(
        ConnectedAccount.id == payload.account_id,
        ConnectedAccount.user_id == current_user.id,
        ConnectedAccount.provider == "google",
    )
    account = db.execute(stmt).scalar_one_or_none()
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Google account not found.")

    gmail = GmailService(db, account)
    await gmail.unwatch()
    return {"status": "unwatched"}


# --- Path-parameter routes MUST come after fixed-path routes ---


@router.get("/{email_id}", response_model=EmailRead)
def get_email(
    email_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> EmailRead:
    email_obj = EmailService(db).get_email(email_id, user_id=current_user.id)
    if email_obj is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Email not found.")
    return email_obj


@router.patch("/{email_id}", response_model=EmailRead)
def update_email(
    email_id: UUID,
    payload: EmailUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> EmailRead:
    svc = EmailService(db)
    email_obj = svc.get_email(email_id, user_id=current_user.id)
    if email_obj is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Email not found.")
    return svc.update_email(email_obj, payload)
