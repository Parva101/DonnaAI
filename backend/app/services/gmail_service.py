"""Gmail API service.

Uses the Gmail REST API directly via httpx to sync emails.
Handles token refresh, incremental sync via historyId, and message parsing.
"""

from __future__ import annotations

import base64
import email as email_lib
import email.utils
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import ConnectedAccount, Email

logger = logging.getLogger(__name__)

GMAIL_API_BASE = "https://gmail.googleapis.com/gmail/v1"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"

# How many messages to fetch per page (Gmail max is 500)
MAX_RESULTS_PER_PAGE = 100



class GmailService:
    def __init__(self, db: Session, account: ConnectedAccount) -> None:
        self.db = db
        self.account = account
        self._access_token: str | None = account.access_token_encrypted

    # ── Token management ────────────────────────────────────────

    async def _ensure_valid_token(self) -> str:
        """Refresh the access token if it's expired."""
        if self.account.token_expires_at and self.account.token_expires_at > datetime.now(timezone.utc):
            return self._access_token or ""

        if not self.account.refresh_token_encrypted:
            raise ValueError("No refresh token available — user needs to reconnect Google.")

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "client_id": settings.google_client_id,
                    "client_secret": settings.google_client_secret,
                    "refresh_token": self.account.refresh_token_encrypted,
                    "grant_type": "refresh_token",
                },
            )
            resp.raise_for_status()
            data = resp.json()

        self._access_token = data["access_token"]
        self.account.access_token_encrypted = data["access_token"]
        if "refresh_token" in data:
            self.account.refresh_token_encrypted = data["refresh_token"]
        from datetime import timedelta
        self.account.token_expires_at = datetime.now(timezone.utc) + timedelta(
            seconds=data.get("expires_in", 3600)
        )
        self.db.add(self.account)
        self.db.commit()
        self.db.refresh(self.account)

        return self._access_token or ""

    async def _get_headers(self) -> dict[str, str]:
        token = await self._ensure_valid_token()
        return {"Authorization": f"Bearer {token}"}

    # ── List messages ───────────────────────────────────────────

    async def list_message_ids(
        self, *, max_results: int = MAX_RESULTS_PER_PAGE, page_token: str | None = None
    ) -> tuple[list[str], str | None]:
        """List message IDs from the user's inbox."""
        headers = await self._get_headers()
        params: dict[str, Any] = {
            "maxResults": max_results,
            "labelIds": "INBOX",
        }
        if page_token:
            params["pageToken"] = page_token

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{GMAIL_API_BASE}/users/me/messages",
                headers=headers,
                params=params,
            )
            resp.raise_for_status()
            data = resp.json()

        message_ids = [m["id"] for m in data.get("messages", [])]
        next_page = data.get("nextPageToken")
        return message_ids, next_page

    # ── Get single message ──────────────────────────────────────

    async def get_message(self, message_id: str) -> dict[str, Any]:
        """Fetch a single message with full body content."""
        headers = await self._get_headers()

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{GMAIL_API_BASE}/users/me/messages/{message_id}",
                headers=headers,
                params={"format": "full"},
            )
            resp.raise_for_status()
            return resp.json()

    # ── Parse message into Email model ──────────────────────────

    def parse_message(self, raw: dict[str, Any], user_id: UUID) -> Email:
        """Convert a Gmail API message response into an Email ORM object."""
        headers_list = raw.get("payload", {}).get("headers", [])
        headers_dict = {h["name"].lower(): h["value"] for h in headers_list}

        from_raw = headers_dict.get("from", "")
        from_name, from_address = self._parse_email_address(from_raw)

        to_raw = headers_dict.get("to", "")
        to_addresses = self._parse_address_list(to_raw)

        cc_raw = headers_dict.get("cc", "")
        cc_addresses = self._parse_address_list(cc_raw) if cc_raw else None

        body_text, body_html = self._extract_body(raw.get("payload", {}))

        labels = raw.get("labelIds", [])
        internal_date = int(raw.get("internalDate", 0))
        received_at = datetime.fromtimestamp(internal_date / 1000, tz=timezone.utc) if internal_date else None

        return Email(
            user_id=user_id,
            account_id=self.account.id,
            gmail_message_id=raw["id"],
            thread_id=raw.get("threadId"),
            history_id=raw.get("historyId"),
            subject=headers_dict.get("subject"),
            snippet=raw.get("snippet"),
            from_address=from_address,
            from_name=from_name,
            to_addresses=to_addresses,
            cc_addresses=cc_addresses,
            reply_to=headers_dict.get("reply-to"),
            body_text=body_text,
            body_html=body_html,
            is_read="UNREAD" not in labels,
            is_starred="STARRED" in labels,
            is_draft="DRAFT" in labels,
            has_attachments=self._has_attachments(raw.get("payload", {})),
            gmail_labels=labels,
            received_at=received_at,
            internal_date=internal_date,
            category="uncategorized",
            category_source="pending",
        )

    # ── Send message ─────────────────────────────────────────────

    async def send_message(
        self,
        *,
        to: list[str],
        subject: str | None = None,
        body: str = "",
        cc: list[str] | None = None,
        bcc: list[str] | None = None,
        in_reply_to: str | None = None,
        thread_id: str | None = None,
    ) -> dict[str, Any]:
        """Send an email via Gmail API.

        Builds an RFC 2822 message, base64url encodes it, and sends it.
        Returns the Gmail API response with id and threadId.
        """
        import email.mime.text

        headers = await self._get_headers()

        # Build the MIME message
        msg = email.mime.text.MIMEText(body, "plain", "utf-8")
        msg["To"] = ", ".join(to)
        if cc:
            msg["Cc"] = ", ".join(cc)
        if bcc:
            msg["Bcc"] = ", ".join(bcc)
        if subject:
            msg["Subject"] = subject
        if in_reply_to:
            msg["In-Reply-To"] = in_reply_to
            msg["References"] = in_reply_to

        # Encode to base64url
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")

        # Build the request body
        request_body: dict[str, Any] = {"raw": raw}
        if thread_id:
            request_body["threadId"] = thread_id

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{GMAIL_API_BASE}/users/me/messages/send",
                headers=headers,
                json=request_body,
            )
            resp.raise_for_status()
            return resp.json()

    # ── Incremental sync via historyId ────────────────────────

    async def list_history(
        self, *, start_history_id: str, page_token: str | None = None
    ) -> tuple[list[str], str | None, str | None]:
        """Get message IDs that changed since start_history_id.

        Returns (new_or_changed_message_ids, next_page_token, new_history_id).
        """
        headers = await self._get_headers()
        params: dict[str, Any] = {
            "startHistoryId": start_history_id,
            "historyTypes": "messageAdded",
            "labelId": "INBOX",
            "maxResults": 500,
        }
        if page_token:
            params["pageToken"] = page_token

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{GMAIL_API_BASE}/users/me/history",
                headers=headers,
                params=params,
            )
            if resp.status_code == 404:
                # historyId too old or invalid — need full sync
                return [], None, None
            resp.raise_for_status()
            data = resp.json()

        message_ids: list[str] = []
        for record in data.get("history", []):
            for added in record.get("messagesAdded", []):
                msg = added.get("message", {})
                msg_id = msg.get("id")
                labels = msg.get("labelIds", [])
                if msg_id and "INBOX" in labels:
                    message_ids.append(msg_id)

        new_history_id = data.get("historyId")
        next_page = data.get("nextPageToken")
        return message_ids, next_page, new_history_id

    # ── Full sync ───────────────────────────────────────────────

    async def sync_emails(self) -> list[Email]:
        """Smart sync: uses historyId for incremental, falls back to full.

        - First sync (no stored historyId): pages through the entire inbox.
        - Subsequent syncs: uses Gmail history API to fetch only new messages.
        Returns the list of newly created Email objects.
        """
        metadata = dict(self.account.account_metadata or {})
        last_history_id = metadata.get("last_history_id")

        if last_history_id:
            logger.info(f"Incremental sync from historyId {last_history_id}...")
            new_emails = await self._incremental_sync(last_history_id)
        else:
            logger.info("No historyId found — performing full sync...")
            new_emails = await self._full_sync()

        # Update sync metadata
        metadata = dict(self.account.account_metadata or {})
        metadata["last_sync_at"] = datetime.now(timezone.utc).isoformat()
        metadata["total_synced"] = metadata.get("total_synced", 0) + len(new_emails)

        # Store the latest historyId for next incremental sync
        if new_emails:
            # Use the highest historyId from the new emails
            max_hid = max(
                (int(e.history_id) for e in new_emails if e.history_id),
                default=None,
            )
            if max_hid:
                metadata["last_history_id"] = str(max_hid)
        elif not last_history_id:
            # Full sync with 0 new emails — get current historyId from profile
            hid = await self._get_profile_history_id()
            if hid:
                metadata["last_history_id"] = hid

        self.account.account_metadata = metadata
        self.db.add(self.account)
        self.db.commit()

        logger.info(f"Gmail sync complete: {len(new_emails)} new emails for account {self.account.id}")
        return new_emails

    async def _get_profile_history_id(self) -> str | None:
        """Fetch the current historyId from the Gmail profile."""
        headers = await self._get_headers()
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{GMAIL_API_BASE}/users/me/profile",
                headers=headers,
            )
            resp.raise_for_status()
            return resp.json().get("historyId")

    async def _incremental_sync(self, start_history_id: str) -> list[Email]:
        """Fetch only new messages since start_history_id."""
        user_id = self.account.user_id
        all_new_ids: list[str] = []
        page_token: str | None = None
        latest_history_id: str | None = None

        # Page through all history records
        while True:
            msg_ids, next_page, new_hid = await self.list_history(
                start_history_id=start_history_id, page_token=page_token
            )

            if msg_ids is None and next_page is None and new_hid is None:
                # historyId invalid — fall back to full sync
                logger.warning("historyId expired, falling back to full sync...")
                return await self._full_sync()

            all_new_ids.extend(msg_ids)
            if new_hid:
                latest_history_id = new_hid

            if not next_page:
                break
            page_token = next_page

        if not all_new_ids:
            logger.info("No new messages since last sync ✓")
            # Still update historyId
            if latest_history_id:
                metadata = dict(self.account.account_metadata or {})
                metadata["last_history_id"] = latest_history_id
                self.account.account_metadata = metadata
            return []

        # Deduplicate
        unique_ids = list(dict.fromkeys(all_new_ids))
        logger.info(f"History returned {len(unique_ids)} new message IDs")

        # Filter out already-synced
        existing_ids = set(
            row[0]
            for row in self.db.execute(
                Email.__table__.select()
                .where(Email.gmail_message_id.in_(unique_ids))
                .with_only_columns(Email.gmail_message_id)
            ).fetchall()
        )
        new_ids = [mid for mid in unique_ids if mid not in existing_ids]
        logger.info(f"After filtering existing: {len(new_ids)} to fetch")

        new_emails: list[Email] = []
        for msg_id in new_ids:
            try:
                raw = await self.get_message(msg_id)
                email_obj = self.parse_message(raw, user_id)
                self.db.add(email_obj)
                new_emails.append(email_obj)
            except Exception as e:
                logger.warning(f"Failed to sync message {msg_id}: {e}")
                continue

        if new_emails:
            self.db.commit()
            for em in new_emails:
                self.db.refresh(em)

        return new_emails

    async def _full_sync(self) -> list[Email]:
        """Fetch and store ALL emails from Gmail (initial sync)."""
        from sqlalchemy.exc import IntegrityError, DataError

        user_id = self.account.user_id
        account_id = self.account.id
        new_emails: list[Email] = []
        page_token: str | None = None
        total_fetched = 0

        # Pre-load ALL existing gmail_message_ids for this account
        # so we never try to insert a duplicate
        all_existing = set(
            row[0]
            for row in self.db.execute(
                Email.__table__.select()
                .where(Email.account_id == account_id)
                .with_only_columns(Email.gmail_message_id)
            ).fetchall()
        )
        logger.info(f"Already have {len(all_existing)} emails in DB for this account")

        while True:
            message_ids, page_token = await self.list_message_ids(
                max_results=MAX_RESULTS_PER_PAGE, page_token=page_token
            )

            if not message_ids:
                break

            total_fetched += len(message_ids)
            logger.info(f"Fetched {total_fetched} message IDs so far...")

            # Filter using the pre-loaded set
            new_ids = [mid for mid in message_ids if mid not in all_existing]
            logger.info(f"  → {len(new_ids)} new, {len(message_ids) - len(new_ids)} already exist")

            if not new_ids:
                if not page_token:
                    break
                continue

            page_emails: list[Email] = []
            for msg_id in new_ids:
                try:
                    raw = await self.get_message(msg_id)
                    email_obj = self.parse_message(raw, user_id)
                    self.db.add(email_obj)
                    page_emails.append(email_obj)
                    # Track so subsequent pages skip these too
                    all_existing.add(msg_id)
                except Exception as e:
                    logger.warning(f"Failed to fetch/parse message {msg_id}: {e}")
                    continue

            # Commit each page — with IntegrityError recovery
            if page_emails:
                try:
                    self.db.commit()
                    new_emails.extend(page_emails)
                    logger.info(f"Committed page — {len(new_emails)} total new emails")
                except (IntegrityError, DataError) as e:
                    logger.warning(f"Page commit failed, falling back to one-by-one: {e}")
                    self.db.rollback()
                    # Re-insert one by one, skipping bad rows
                    for em in page_emails:
                        try:
                            self.db.add(em)
                            self.db.commit()
                            new_emails.append(em)
                        except (IntegrityError, DataError):
                            self.db.rollback()
                            logger.debug(f"Skipping problem row {em.gmail_message_id}")

            if not page_token:
                break

        # Refresh all so relationships are loaded
        for em in new_emails:
            self.db.refresh(em)

        return new_emails

    # ── Helpers ─────────────────────────────────────────────────

    @staticmethod
    def _parse_email_address(raw: str) -> tuple[str | None, str | None]:
        name, addr = email_lib.utils.parseaddr(raw)
        return (name or None, addr or None)

    @staticmethod
    def _parse_address_list(raw: str) -> list[dict[str, str]]:
        addresses = []
        for chunk in raw.split(","):
            chunk = chunk.strip()
            if not chunk:
                continue
            name, addr = email_lib.utils.parseaddr(chunk)
            addresses.append({"name": name, "address": addr})
        return addresses if addresses else []

    @staticmethod
    def _extract_body(payload: dict[str, Any]) -> tuple[str | None, str | None]:
        """Recursively extract text/plain and text/html from the message payload."""
        text = None
        html = None

        def _walk(part: dict[str, Any]) -> None:
            nonlocal text, html
            mime = part.get("mimeType", "")
            body = part.get("body", {})
            data = body.get("data")

            if data:
                decoded = base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
                if mime == "text/plain" and text is None:
                    text = decoded
                elif mime == "text/html" and html is None:
                    html = decoded

            for sub in part.get("parts", []):
                _walk(sub)

        _walk(payload)
        return text, html

    @staticmethod
    def _has_attachments(payload: dict[str, Any]) -> bool:
        def _check(part: dict[str, Any]) -> bool:
            if part.get("filename"):
                return True
            return any(_check(sub) for sub in part.get("parts", []))
        return _check(payload)

    # ── Gmail Pub/Sub Watch ─────────────────────────────────────

    async def watch(self, topic_name: str) -> dict[str, Any]:
        """Register a Gmail push notification watch.

        Tells Gmail to send notifications to the given Pub/Sub topic
        whenever this mailbox changes. Watch expires after 7 days.
        Returns {historyId, expiration} from Gmail.
        """
        headers = await self._get_headers()
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{GMAIL_API_BASE}/users/me/watch",
                headers=headers,
                json={
                    "topicName": topic_name,
                    "labelIds": ["INBOX"],
                },
            )
            resp.raise_for_status()
            data = resp.json()

        # Store watch metadata on the account
        metadata = dict(self.account.account_metadata or {})
        metadata["watch_expiration"] = data.get("expiration")
        metadata["watch_history_id"] = data.get("historyId")
        self.account.account_metadata = metadata
        self.db.add(self.account)
        self.db.commit()

        logger.info(
            f"Gmail watch registered for {self.account.account_email} "
            f"(expires: {data.get('expiration')})"
        )
        return data

    async def unwatch(self) -> None:
        """Stop Gmail push notifications for this account."""
        headers = await self._get_headers()
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{GMAIL_API_BASE}/users/me/stop",
                headers=headers,
            )
            resp.raise_for_status()

        metadata = dict(self.account.account_metadata or {})
        metadata.pop("watch_expiration", None)
        metadata.pop("watch_history_id", None)
        self.account.account_metadata = metadata
        self.db.add(self.account)
        self.db.commit()

        logger.info(f"Gmail watch stopped for {self.account.account_email}")
