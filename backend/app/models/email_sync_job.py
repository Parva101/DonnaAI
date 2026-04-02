from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class EmailSyncJob(TimestampMixin, Base):
    """Tracks sync/classification progress for a user's email run."""

    __tablename__ = "email_sync_jobs"
    __table_args__ = (
        Index("ix_email_sync_jobs_user_created", "user_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # queued | running | completed | completed_with_errors | rate_limited | failed
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="queued")
    # queued | syncing | classifying | completed | failed
    stage: Mapped[str] = mapped_column(String(40), nullable=False, default="queued")
    mode: Mapped[str] = mapped_column(String(20), nullable=False, default="sync_and_classify")

    accounts_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    accounts_done: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    fetched_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    classify_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    classified_done: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    remaining_pending: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
