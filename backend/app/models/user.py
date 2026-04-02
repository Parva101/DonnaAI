from __future__ import annotations

import uuid

from sqlalchemy import JSON, Boolean, String, Uuid
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    preferences: Mapped[dict | None] = mapped_column(
        MutableDict.as_mutable(JSON),
        nullable=True,
    )

    connected_accounts: Mapped[list["ConnectedAccount"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )

    emails: Mapped[list["Email"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )

    email_sync_jobs: Mapped[list["EmailSyncJob"]] = relationship(
        cascade="all, delete-orphan",
    )

    action_items: Mapped[list["ActionItem"]] = relationship(
        cascade="all, delete-orphan",
    )

    news_sources: Mapped[list["NewsSource"]] = relationship(
        cascade="all, delete-orphan",
    )

    voice_calls: Mapped[list["VoiceCall"]] = relationship(
        cascade="all, delete-orphan",
    )
