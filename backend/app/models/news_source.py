from __future__ import annotations

import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class NewsSource(TimestampMixin, Base):
    __tablename__ = "news_sources"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    source_type: Mapped[str] = mapped_column(String(20), nullable=False, default="rss")
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    topic: Mapped[str] = mapped_column(String(40), nullable=False, default="all")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    fetch_interval_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
