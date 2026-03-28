"""Email service — CRUD and query operations for the emails table."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import case, func, select, text
from sqlalchemy.orm import Session

from app.models.email import Email
from app.schemas.email import EmailCategoryCount, EmailUpdate


class EmailService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_emails(
        self,
        user_id: UUID,
        *,
        category: str | None = None,
        account_id: UUID | None = None,
        is_read: bool | None = None,
        search: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Email], int]:
        """List emails with filtering and pagination. Returns (emails, total_count)."""
        stmt = select(Email).where(Email.user_id == user_id)

        if category and category != "all":
            stmt = stmt.where(Email.category == category)
        if account_id:
            stmt = stmt.where(Email.account_id == account_id)
        if is_read is not None:
            stmt = stmt.where(Email.is_read == is_read)
        if search:
            # Use PostgreSQL tsvector full-text search if available
            if self.db.bind and self.db.bind.dialect.name == "postgresql":
                ts_query = func.plainto_tsquery("english", search)
                stmt = stmt.where(Email.search_vector.op("@@")(ts_query))
            else:
                # Fallback to ILIKE for SQLite / test environments
                pattern = f"%{search}%"
                stmt = stmt.where(
                    Email.subject.ilike(pattern)
                    | Email.from_name.ilike(pattern)
                    | Email.from_address.ilike(pattern)
                    | Email.snippet.ilike(pattern)
                )

        # Count
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = self.db.execute(count_stmt).scalar() or 0

        # Fetch page
        stmt = stmt.order_by(Email.received_at.desc()).limit(limit).offset(offset)
        emails = list(self.db.execute(stmt).scalars())

        return emails, total

    def get_email(self, email_id: UUID, *, user_id: UUID) -> Email | None:
        stmt = select(Email).where(Email.id == email_id, Email.user_id == user_id)
        return self.db.execute(stmt).scalar_one_or_none()

    def update_email(self, email_obj: Email, payload: EmailUpdate) -> Email:
        update_data = payload.model_dump(exclude_unset=True)
        if "category" in update_data:
            update_data["category_source"] = "user"
        for field, value in update_data.items():
            setattr(email_obj, field, value)
        self.db.add(email_obj)
        self.db.commit()
        self.db.refresh(email_obj)
        return email_obj

    def get_category_counts(self, user_id: UUID, *, account_id: UUID | None = None) -> list[EmailCategoryCount]:
        """Get distinct categories with total + unread counts."""
        stmt = (
            select(
                Email.category,
                func.count(Email.id).label("count"),
                func.sum(case((Email.is_read == False, 1), else_=0)).label("unread"),  # noqa: E712
            )
            .where(Email.user_id == user_id)
            .group_by(Email.category)
            .order_by(func.count(Email.id).desc())
        )
        if account_id:
            stmt = stmt.where(Email.account_id == account_id)

        rows = self.db.execute(stmt).all()
        return [
            EmailCategoryCount(category=row.category, count=row.count, unread=int(row.unread or 0))
            for row in rows
        ]

    def get_total_count(self, user_id: UUID) -> int:
        stmt = select(func.count(Email.id)).where(Email.user_id == user_id)
        return self.db.execute(stmt).scalar() or 0
