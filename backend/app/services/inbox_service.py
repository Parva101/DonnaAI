"""Unified inbox service built from Gmail email threads."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import String, case, cast, func, select
from sqlalchemy.orm import Session

from app.models.email import Email
from app.schemas.inbox import InboxConversationSummary, InboxPlatformCount


class InboxService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_conversations(
        self,
        user_id: UUID,
        *,
        platform: str | None = None,
        account_id: UUID | None = None,
        unread_only: bool = False,
        search: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[InboxConversationSummary], int]:
        # Phase 3 starts Gmail-first; other platforms return empty until ingesters are added.
        if platform and platform != "gmail":
            return [], 0

        thread_key = func.coalesce(
            Email.thread_id,
            Email.gmail_message_id,
            cast(Email.id, String()),
        )
        filters = [Email.user_id == user_id]

        if account_id:
            filters.append(Email.account_id == account_id)
        if search:
            self._append_search_filter(filters, search)

        nulls_last_sort = case((Email.received_at.is_(None), 1), else_=0)

        ranked_subq = (
            select(
                Email.id.label("latest_email_id"),
                Email.account_id.label("account_id"),
                Email.thread_id.label("thread_id"),
                Email.gmail_message_id.label("gmail_message_id"),
                Email.subject.label("subject"),
                Email.snippet.label("snippet"),
                Email.from_name.label("from_name"),
                Email.from_address.label("from_address"),
                Email.received_at.label("latest_received_at"),
                Email.created_at.label("created_at"),
                Email.category.label("category"),
                Email.needs_review.label("needs_review"),
                Email.has_attachments.label("has_attachments"),
                thread_key.label("thread_key"),
                func.row_number()
                .over(
                    partition_by=thread_key,
                    order_by=(
                        nulls_last_sort.asc(),
                        Email.received_at.desc(),
                        Email.created_at.desc(),
                        Email.id.desc(),
                    ),
                )
                .label("rn"),
            )
            .where(*filters)
            .subquery()
        )

        latest_subq = (
            select(ranked_subq)
            .where(ranked_subq.c.rn == 1)
            .subquery()
        )

        counts_subq = (
            select(
                thread_key.label("thread_key"),
                func.count(Email.id).label("message_count"),
                func.sum(
                    case((Email.is_read.is_(False), 1), else_=0)
                ).label("unread_count"),
            )
            .where(*filters)
            .group_by(thread_key)
            .subquery()
        )

        conversations_stmt = (
            select(
                latest_subq.c.latest_email_id,
                latest_subq.c.account_id,
                latest_subq.c.thread_id,
                latest_subq.c.gmail_message_id,
                latest_subq.c.subject,
                latest_subq.c.snippet,
                latest_subq.c.from_name,
                latest_subq.c.from_address,
                latest_subq.c.latest_received_at,
                latest_subq.c.category,
                latest_subq.c.needs_review,
                latest_subq.c.has_attachments,
                counts_subq.c.message_count,
                counts_subq.c.unread_count,
            )
            .join(
                counts_subq,
                counts_subq.c.thread_key == latest_subq.c.thread_key,
            )
        )

        if unread_only:
            conversations_stmt = conversations_stmt.where(counts_subq.c.unread_count > 0)

        total = self.db.execute(
            select(func.count()).select_from(conversations_stmt.subquery())
        ).scalar() or 0

        latest_nulls_last_sort = case(
            (latest_subq.c.latest_received_at.is_(None), 1),
            else_=0,
        )
        rows = self.db.execute(
            conversations_stmt
            .order_by(
                latest_nulls_last_sort.asc(),
                latest_subq.c.latest_received_at.desc(),
                latest_subq.c.created_at.desc(),
            )
            .limit(limit)
            .offset(offset)
        ).all()

        conversations: list[InboxConversationSummary] = []
        for row in rows:
            sender = (row.from_name or row.from_address or "Unknown").strip()
            preview = (row.snippet or "").strip() or None
            conversation_id = row.thread_id or row.gmail_message_id or str(row.latest_email_id)
            conversations.append(
                InboxConversationSummary(
                    conversation_id=conversation_id,
                    platform="gmail",
                    account_id=row.account_id,
                    latest_email_id=row.latest_email_id,
                    sender=sender,
                    sender_address=row.from_address,
                    subject=row.subject,
                    preview=preview,
                    unread_count=int(row.unread_count or 0),
                    message_count=int(row.message_count or 0),
                    has_attachments=bool(row.has_attachments),
                    needs_review=bool(row.needs_review),
                    category=row.category or "uncategorized",
                    latest_received_at=row.latest_received_at,
                )
            )

        return conversations, int(total)

    def get_platform_counts(
        self,
        user_id: UUID,
        *,
        account_id: UUID | None = None,
        search: str | None = None,
    ) -> list[InboxPlatformCount]:
        thread_key = func.coalesce(
            Email.thread_id,
            Email.gmail_message_id,
            cast(Email.id, String()),
        )
        filters = [Email.user_id == user_id]
        if account_id:
            filters.append(Email.account_id == account_id)
        if search:
            self._append_search_filter(filters, search)

        total = self.db.execute(
            select(func.count(func.distinct(thread_key))).where(*filters)
        ).scalar() or 0
        unread = self.db.execute(
            select(
                func.count(
                    func.distinct(
                        case((Email.is_read.is_(False), thread_key), else_=None)
                    )
                )
            ).where(*filters)
        ).scalar() or 0

        return [InboxPlatformCount(platform="gmail", total=int(total), unread=int(unread))]

    def _append_search_filter(self, filters: list, search: str) -> None:
        if self.db.bind and self.db.bind.dialect.name == "postgresql":
            ts_query = func.plainto_tsquery("english", search)
            filters.append(Email.search_vector.op("@@")(ts_query))
            return

        pattern = f"%{search}%"
        filters.append(
            Email.subject.ilike(pattern)
            | Email.from_name.ilike(pattern)
            | Email.from_address.ilike(pattern)
            | Email.snippet.ilike(pattern)
        )
