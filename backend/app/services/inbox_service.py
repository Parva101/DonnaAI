"""Unified inbox service across Gmail, Slack, WhatsApp, and Teams."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import String, case, cast, func, select
from sqlalchemy.orm import Session

from app.models.connected_account import ConnectedAccount
from app.models.email import Email
from app.schemas.inbox import InboxConversationSummary, InboxPlatformCount
from app.services.slack_service import SlackService
from app.services.teams_service import TeamsService
from app.services.whatsapp_bridge_service import WhatsAppBridgeService

SUPPORTED_PLATFORMS = {"gmail", "slack", "whatsapp", "teams", "all"}


class InboxService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.slack = SlackService(db)
        self.whatsapp = WhatsAppBridgeService(db)
        self.teams = TeamsService(db)

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
        all_conversations = self._collect_conversations(
            user_id=user_id,
            platform=platform,
            account_id=account_id,
            unread_only=unread_only,
            search=search,
        )
        total = len(all_conversations)
        return all_conversations[offset : offset + limit], total

    def get_platform_counts(
        self,
        user_id: UUID,
        *,
        account_id: UUID | None = None,
        search: str | None = None,
        platform: str | None = None,
    ) -> list[InboxPlatformCount]:
        conversations = self._collect_conversations(
            user_id=user_id,
            platform=platform,
            account_id=account_id,
            unread_only=False,
            search=search,
        )
        counts_by_platform: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "unread": 0})
        for conv in conversations:
            counts_by_platform[conv.platform]["total"] += 1
            if conv.unread_count > 0:
                counts_by_platform[conv.platform]["unread"] += 1

        preferred_order = ["gmail", "slack", "whatsapp", "teams"]
        sorted_platforms = sorted(
            counts_by_platform.items(),
            key=lambda item: preferred_order.index(item[0]) if item[0] in preferred_order else 99,
        )
        return [
            InboxPlatformCount(platform=platform_name, total=values["total"], unread=values["unread"])
            for platform_name, values in sorted_platforms
            if values["total"] > 0
        ]

    def _collect_conversations(
        self,
        *,
        user_id: UUID,
        platform: str | None,
        account_id: UUID | None,
        unread_only: bool,
        search: str | None,
    ) -> list[InboxConversationSummary]:
        normalized_platform = (platform or "all").lower()
        if normalized_platform not in SUPPORTED_PLATFORMS:
            return []

        # If account_id is provided without platform, infer the provider from account.
        inferred_platform = self._infer_platform_from_account(user_id=user_id, account_id=account_id)
        if normalized_platform == "all" and inferred_platform:
            normalized_platform = inferred_platform

        conversations: list[InboxConversationSummary] = []

        if normalized_platform in {"all", "gmail"}:
            conversations.extend(
                self._list_gmail_conversations(
                    user_id=user_id,
                    account_id=account_id,
                    unread_only=unread_only,
                    search=search,
                )
            )

        if normalized_platform in {"all", "slack"}:
            conversations.extend(
                self._list_slack_conversations(
                    user_id=user_id,
                    account_id=account_id,
                    unread_only=unread_only,
                    search=search,
                )
            )

        if normalized_platform in {"all", "whatsapp"}:
            conversations.extend(
                self._list_whatsapp_conversations(
                    user_id=user_id,
                    account_id=account_id,
                    unread_only=unread_only,
                    search=search,
                )
            )

        if normalized_platform in {"all", "teams"}:
            conversations.extend(
                self._list_teams_conversations(
                    user_id=user_id,
                    account_id=account_id,
                    unread_only=unread_only,
                    search=search,
                )
            )

        conversations.sort(
            key=lambda c: (
                c.latest_received_at is None,
                c.latest_received_at or datetime.min.replace(tzinfo=timezone.utc),
            ),
            reverse=True,
        )
        return conversations

    def _infer_platform_from_account(self, *, user_id: UUID, account_id: UUID | None) -> str | None:
        if not account_id:
            return None
        account = self.db.execute(
            select(ConnectedAccount).where(
                ConnectedAccount.id == account_id,
                ConnectedAccount.user_id == user_id,
            )
        ).scalar_one_or_none()
        if not account:
            return None
        if account.provider == "google":
            return "gmail"
        if account.provider in {"slack", "whatsapp", "teams"}:
            return account.provider
        return None

    def _list_gmail_conversations(
        self,
        *,
        user_id: UUID,
        account_id: UUID | None,
        unread_only: bool,
        search: str | None,
    ) -> list[InboxConversationSummary]:
        # Restrict account-filtered queries to Google accounts only.
        if account_id:
            inferred = self._infer_platform_from_account(user_id=user_id, account_id=account_id)
            if inferred not in {None, "gmail"}:
                return []

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

        rows = self.db.execute(conversations_stmt).all()

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
                    latest_email_id=str(row.latest_email_id),
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
        return conversations

    def _list_slack_conversations(
        self,
        *,
        user_id: UUID,
        account_id: UUID | None,
        unread_only: bool,
        search: str | None,
    ) -> list[InboxConversationSummary]:
        if account_id:
            inferred = self._infer_platform_from_account(user_id=user_id, account_id=account_id)
            if inferred not in {None, "slack"}:
                return []
        try:
            conversations = self.slack.list_conversations(
                user_id=user_id,
                account_id=account_id,
                unread_only=unread_only,
                search=search,
            )
        except Exception:
            return []

        return [
            InboxConversationSummary(
                conversation_id=item.conversation_id,
                platform="slack",
                account_id=item.account_id,
                latest_email_id=item.conversation_id,
                sender=item.sender,
                sender_address=None,
                subject=item.name,
                preview=item.preview,
                unread_count=item.unread_count,
                message_count=item.message_count,
                has_attachments=item.has_attachments,
                needs_review=False,
                category="uncategorized",
                latest_received_at=item.latest_received_at,
            )
            for item in conversations
        ]

    def _list_whatsapp_conversations(
        self,
        *,
        user_id: UUID,
        account_id: UUID | None,
        unread_only: bool,
        search: str | None,
    ) -> list[InboxConversationSummary]:
        stmt = select(ConnectedAccount).where(
            ConnectedAccount.user_id == user_id,
            ConnectedAccount.provider == "whatsapp",
        )
        if account_id:
            inferred = self._infer_platform_from_account(user_id=user_id, account_id=account_id)
            if inferred not in {None, "whatsapp"}:
                return []
            stmt = stmt.where(ConnectedAccount.id == account_id)

        accounts = list(self.db.execute(stmt).scalars())
        if not accounts:
            return []

        account = accounts[0]
        rows = self.whatsapp.list_messages(limit=5000)
        grouped: dict[str, dict] = {}

        for row in rows:
            chat_jid = (row.get("chat_jid") or row.get("sender_jid") or "").strip()
            if not chat_jid:
                continue
            group = grouped.setdefault(
                chat_jid,
                {
                    "message_count": 0,
                    "inbound_count": 0,
                    "latest_received_at": None,
                    "latest_text": None,
                    "latest_sender": None,
                    "latest_message_id": None,
                    "latest_type": None,
                },
            )

            group["message_count"] += 1
            if not row.get("from_me"):
                group["inbound_count"] += 1

            received_raw = row.get("received_at")
            received_at = None
            if isinstance(received_raw, str):
                try:
                    received_at = datetime.fromisoformat(received_raw.replace("Z", "+00:00"))
                except Exception:
                    received_at = None

            current_latest = group["latest_received_at"]
            if current_latest is None or (
                received_at is not None and received_at > current_latest
            ):
                group["latest_received_at"] = received_at
                group["latest_text"] = row.get("text")
                group["latest_sender"] = row.get("sender_jid")
                group["latest_message_id"] = row.get("message_id")
                group["latest_type"] = row.get("message_type")

        search_lc = search.strip().lower() if search else None
        conversations: list[InboxConversationSummary] = []
        for chat_jid, group in grouped.items():
            sender = (group["latest_sender"] or chat_jid or "WhatsApp").strip()
            preview = (group["latest_text"] or "").strip() or None
            unread_count = int(group["inbound_count"] or 0)

            if unread_only and unread_count <= 0:
                continue

            if search_lc:
                blob = " ".join([chat_jid, sender, preview or ""]).lower()
                if search_lc not in blob:
                    continue

            message_type = (group["latest_type"] or "").lower()
            has_attachments = message_type not in {"", "conversation", "extendedtextmessage"}
            conversations.append(
                InboxConversationSummary(
                    conversation_id=chat_jid,
                    platform="whatsapp",
                    account_id=account.id,
                    latest_email_id=group["latest_message_id"],
                    sender=sender,
                    sender_address=sender,
                    subject=None,
                    preview=preview,
                    unread_count=unread_count,
                    message_count=int(group["message_count"] or 0),
                    has_attachments=has_attachments,
                    needs_review=False,
                    category="uncategorized",
                    latest_received_at=group["latest_received_at"],
                )
            )
        return conversations

    def _list_teams_conversations(
        self,
        *,
        user_id: UUID,
        account_id: UUID | None,
        unread_only: bool,
        search: str | None,
    ) -> list[InboxConversationSummary]:
        if account_id:
            inferred = self._infer_platform_from_account(user_id=user_id, account_id=account_id)
            if inferred not in {None, "teams"}:
                return []

        try:
            conversations = self.teams.list_conversations(
                user_id=user_id,
                account_id=account_id,
                unread_only=unread_only,
                search=search,
            )
        except Exception:
            return []

        return [
            InboxConversationSummary(
                conversation_id=item.conversation_id,
                platform="teams",
                account_id=item.account_id,
                latest_email_id=item.conversation_id,
                sender=item.sender,
                sender_address=None,
                subject=item.name,
                preview=item.preview,
                unread_count=item.unread_count,
                message_count=item.message_count,
                has_attachments=item.has_attachments,
                needs_review=False,
                category="uncategorized",
                latest_received_at=item.latest_received_at,
            )
            for item in conversations
        ]

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
