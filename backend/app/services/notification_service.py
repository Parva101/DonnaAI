"""Notification preferences and daily digest builder."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Email, NewsArticle, User
from app.schemas.notifications import DigestItem, NotificationPreferences

DEFAULT_PREFS = NotificationPreferences().model_dump()


class NotificationService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_preferences(self, *, user_id: UUID) -> NotificationPreferences:
        user = self.db.get(User, user_id)
        if not user:
            return NotificationPreferences()

        stored = dict(user.preferences or {})
        merged = {**DEFAULT_PREFS, **stored}
        return NotificationPreferences.model_validate(merged)

    def update_preferences(self, *, user_id: UUID, patch: dict) -> NotificationPreferences:
        user = self.db.get(User, user_id)
        if not user:
            raise ValueError("User not found")

        current = {**DEFAULT_PREFS, **dict(user.preferences or {})}
        for key, value in patch.items():
            if value is not None:
                current[key] = value
        validated = NotificationPreferences.model_validate(current)
        user.preferences = validated.model_dump()
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return validated

    def build_daily_digest(self, *, user_id: UUID) -> tuple[str, list[DigestItem]]:
        unread_stmt = (
            select(Email)
            .where(Email.user_id == user_id, Email.is_read.is_(False))
            .order_by(Email.priority_score.desc(), Email.received_at.desc())
            .limit(8)
        )
        unread = list(self.db.execute(unread_stmt).scalars())

        news_stmt = (
            select(NewsArticle)
            .where(NewsArticle.user_id == user_id)
            .order_by(
                NewsArticle.relevance_score.desc(),
                NewsArticle.published_at.desc(),
                NewsArticle.created_at.desc(),
            )
            .limit(10)
        )
        articles = list(self.db.execute(news_stmt).scalars())

        items: list[DigestItem] = []
        for email in unread:
            items.append(
                DigestItem(
                    title=email.subject or "(no subject)",
                    source=f"Email: {email.from_name or email.from_address or 'Unknown'}",
                    preview=(email.snippet or "").strip()[:180],
                    url=None,
                )
            )

        for article in articles[:10]:
            items.append(
                DigestItem(
                    title=article.title,
                    source=f"News: {article.source_name}",
                    preview=(article.summary or "").strip()[:180],
                    url=article.url,
                )
            )

        summary_parts = [
            f"{len(unread)} unread high-signal emails",
            f"{len(articles[:10])} top news stories",
        ]
        summary = "Morning briefing: " + " and ".join(summary_parts) + "."
        return summary, items

    def generated_at(self) -> datetime:
        return datetime.now(timezone.utc)
