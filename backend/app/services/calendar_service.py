"""Calendar service for Google Calendar connected accounts."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.token_crypto import decrypt_token, encrypt_token
from app.models import ConnectedAccount
from app.schemas.calendar import BusyBlock, CalendarEvent

GOOGLE_CALENDAR_BASE = "https://www.googleapis.com/calendar/v3"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"


class CalendarService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def _list_accounts(self, *, user_id: UUID, account_id: UUID | None = None) -> list[ConnectedAccount]:
        stmt = select(ConnectedAccount).where(
            ConnectedAccount.user_id == user_id,
            ConnectedAccount.provider == "google",
        )
        if account_id:
            stmt = stmt.where(ConnectedAccount.id == account_id)
        accounts = list(self.db.execute(stmt).scalars())
        result: list[ConnectedAccount] = []
        for acc in accounts:
            scopes = (acc.scopes or "").lower()
            if "calendar" in scopes:
                result.append(acc)
        return result

    async def _ensure_valid_token(self, account: ConnectedAccount) -> str:
        if account.token_expires_at and account.token_expires_at > datetime.now(timezone.utc):
            current_access = decrypt_token(account.access_token_encrypted)
            if current_access:
                return current_access

        refresh_token = decrypt_token(account.refresh_token_encrypted)
        if not refresh_token:
            raise ValueError("No refresh token available for calendar account")

        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "client_id": settings.google_client_id,
                    "client_secret": settings.google_client_secret,
                    "refresh_token": refresh_token,
                    "grant_type": "refresh_token",
                },
            )
            resp.raise_for_status()
            data = resp.json()

        account.access_token_encrypted = encrypt_token(data.get("access_token"))
        if data.get("refresh_token"):
            account.refresh_token_encrypted = encrypt_token(data.get("refresh_token"))
        expires_in = int(data.get("expires_in", 3600))
        account.token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
        self.db.add(account)
        self.db.commit()
        self.db.refresh(account)
        decrypted = decrypt_token(account.access_token_encrypted)
        if not decrypted:
            raise ValueError("Failed to refresh Google access token")
        return decrypted

    @staticmethod
    def _parse_google_datetime(raw: str | None) -> datetime | None:
        if not raw:
            return None
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                return dt.replace(tzinfo=timezone.utc)
            return dt
        except Exception:
            return None

    def _to_calendar_event(self, *, account: ConnectedAccount, item: dict[str, Any]) -> CalendarEvent | None:
        start = item.get("start") or {}
        end = item.get("end") or {}
        start_raw = start.get("dateTime") or start.get("date")
        end_raw = end.get("dateTime") or end.get("date")
        start_dt = self._parse_google_datetime(start_raw)
        end_dt = self._parse_google_datetime(end_raw)
        if start_dt is None or end_dt is None:
            return None

        attendees = []
        for attendee in item.get("attendees") or []:
            email = attendee.get("email")
            if isinstance(email, str) and email.strip():
                attendees.append(email.strip())

        return CalendarEvent(
            account_id=account.id,
            provider="google",
            event_id=str(item.get("id") or ""),
            title=str(item.get("summary") or "(untitled event)"),
            description=item.get("description"),
            location=item.get("location"),
            start_at=start_dt,
            end_at=end_dt,
            attendees=attendees,
            organizer=(item.get("organizer") or {}).get("email"),
            is_all_day=bool(start.get("date") and not start.get("dateTime")),
        )

    async def list_events(
        self,
        *,
        user_id: UUID,
        account_id: UUID | None = None,
        start_at: datetime,
        end_at: datetime,
    ) -> list[CalendarEvent]:
        accounts = self._list_accounts(user_id=user_id, account_id=account_id)
        events: list[CalendarEvent] = []

        for account in accounts:
            token = await self._ensure_valid_token(account)
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.get(
                    f"{GOOGLE_CALENDAR_BASE}/calendars/primary/events",
                    headers={"Authorization": f"Bearer {token}"},
                    params={
                        "singleEvents": "true",
                        "orderBy": "startTime",
                        "timeMin": start_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
                        "timeMax": end_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
                        "maxResults": 250,
                    },
                )
                resp.raise_for_status()
                data = resp.json()

            for item in data.get("items", []):
                if not isinstance(item, dict):
                    continue
                normalized = self._to_calendar_event(account=account, item=item)
                if normalized is not None:
                    events.append(normalized)

        events.sort(key=lambda e: e.start_at)
        return events

    async def create_event(
        self,
        *,
        user_id: UUID,
        account_id: UUID | None,
        title: str,
        start_at: datetime,
        end_at: datetime,
        description: str | None = None,
        location: str | None = None,
        attendees: list[str] | None = None,
        is_all_day: bool = False,
    ) -> CalendarEvent:
        if end_at <= start_at:
            raise ValueError("Event end_at must be after start_at.")

        account = next(iter(self._list_accounts(user_id=user_id, account_id=account_id)), None)
        if account is None:
            raise ValueError("No Google Calendar account connected with calendar scope.")

        token = await self._ensure_valid_token(account)
        attendees_payload = [
            {"email": email.strip()}
            for email in (attendees or [])
            if isinstance(email, str) and email.strip()
        ]

        payload: dict[str, Any] = {
            "summary": title.strip(),
            "description": description.strip() if isinstance(description, str) and description.strip() else None,
            "location": location.strip() if isinstance(location, str) and location.strip() else None,
            "attendees": attendees_payload,
        }
        payload = {key: value for key, value in payload.items() if value not in (None, [], "")}

        if is_all_day:
            start_date = start_at.astimezone(timezone.utc).date()
            end_date = end_at.astimezone(timezone.utc).date()
            if end_date <= start_date:
                end_date = start_date + timedelta(days=1)
            payload["start"] = {"date": start_date.isoformat()}
            payload["end"] = {"date": end_date.isoformat()}
        else:
            payload["start"] = {"dateTime": start_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")}
            payload["end"] = {"dateTime": end_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")}

        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                f"{GOOGLE_CALENDAR_BASE}/calendars/primary/events",
                headers={"Authorization": f"Bearer {token}"},
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()

        if not isinstance(data, dict):
            raise ValueError("Google Calendar returned an invalid event response.")
        event = self._to_calendar_event(account=account, item=data)
        if event is None:
            raise ValueError("Failed to parse created calendar event.")
        return event

    async def freebusy(
        self,
        *,
        user_id: UUID,
        account_id: UUID | None,
        start_at: datetime,
        end_at: datetime,
    ) -> list[BusyBlock]:
        events = await self.list_events(
            user_id=user_id,
            account_id=account_id,
            start_at=start_at,
            end_at=end_at,
        )
        busy = [BusyBlock(start_at=e.start_at, end_at=e.end_at) for e in events]
        busy.sort(key=lambda b: b.start_at)
        return busy

    async def suggest_slots(
        self,
        *,
        user_id: UUID,
        account_id: UUID | None,
        date: datetime,
        duration_minutes: int,
        count: int,
    ) -> list[BusyBlock]:
        day_start = date.astimezone(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        busy = await self.freebusy(
            user_id=user_id,
            account_id=account_id,
            start_at=day_start,
            end_at=day_end,
        )

        work_start = day_start.replace(hour=9)
        work_end = day_start.replace(hour=17)
        cursor = work_start
        slot_duration = timedelta(minutes=duration_minutes)
        suggestions: list[BusyBlock] = []

        for block in busy:
            if cursor + slot_duration <= block.start_at and cursor + slot_duration <= work_end:
                suggestions.append(BusyBlock(start_at=cursor, end_at=cursor + slot_duration))
                if len(suggestions) >= count:
                    return suggestions
            if block.end_at > cursor:
                cursor = block.end_at

        while cursor + slot_duration <= work_end and len(suggestions) < count:
            suggestions.append(BusyBlock(start_at=cursor, end_at=cursor + slot_duration))
            cursor += slot_duration

        return suggestions
