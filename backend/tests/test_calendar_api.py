from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.services.calendar_service import CalendarService


def _login(client: TestClient) -> dict:
    resp = client.post(
        "/api/v1/auth/dev-login",
        json={"email": "calendar-api-test@example.com", "full_name": "Calendar Tester"},
    )
    assert resp.status_code == 200
    return resp.json()["user"]


def test_calendar_events_requires_auth(client: TestClient) -> None:
    resp = client.get("/api/v1/calendar/events")
    assert resp.status_code == 401


def test_calendar_events_mocked(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _login(client)

    async def fake_list_events(self, *, user_id, account_id=None, start_at, end_at):
        return [
            {
                "account_id": "8a9deef6-9f6f-43ba-af6a-35a8d4d9a2db",
                "provider": "google",
                "event_id": "evt-1",
                "title": "Team Sync",
                "description": None,
                "location": "Meet",
                "start_at": start_at,
                "end_at": start_at + timedelta(minutes=30),
                "attendees": ["a@example.com"],
                "organizer": "owner@example.com",
                "is_all_day": False,
            }
        ]

    monkeypatch.setattr(CalendarService, "list_events", fake_list_events)

    resp = client.get("/api/v1/calendar/events")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["total"] == 1
    assert payload["events"][0]["title"] == "Team Sync"


def test_suggest_slots_mocked(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _login(client)

    async def fake_suggest_slots(self, *, user_id, account_id=None, date, duration_minutes, count):
        start = date.replace(hour=9, minute=0, second=0, microsecond=0, tzinfo=timezone.utc)
        return [{"start_at": start, "end_at": start + timedelta(minutes=duration_minutes)}]

    monkeypatch.setattr(CalendarService, "suggest_slots", fake_suggest_slots)

    resp = client.post(
        "/api/v1/calendar/suggest-slots",
        json={"date": datetime.now(timezone.utc).isoformat(), "duration_minutes": 30, "count": 3},
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert len(payload["slots"]) == 1


def test_create_calendar_event_mocked(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _login(client)
    start = datetime(2026, 4, 10, 15, 0, tzinfo=timezone.utc)
    end = start + timedelta(minutes=45)

    async def fake_create_event(
        self,
        *,
        user_id,
        account_id=None,
        title,
        start_at,
        end_at,
        description=None,
        location=None,
        attendees=None,
        is_all_day=False,
    ):
        assert title == "Donna Sync"
        assert start_at == start
        assert end_at == end
        assert description == "Cross-platform review"
        assert location == "Meet"
        assert attendees == ["owner@example.com"]
        assert is_all_day is False
        return {
            "account_id": "8a9deef6-9f6f-43ba-af6a-35a8d4d9a2db",
            "provider": "google",
            "event_id": "evt-created-1",
            "title": title,
            "description": description,
            "location": location,
            "start_at": start_at,
            "end_at": end_at,
            "attendees": attendees or [],
            "organizer": "owner@example.com",
            "is_all_day": False,
        }

    monkeypatch.setattr(CalendarService, "create_event", fake_create_event)

    resp = client.post(
        "/api/v1/calendar/events",
        json={
            "title": "Donna Sync",
            "description": "Cross-platform review",
            "location": "Meet",
            "start_at": start.isoformat(),
            "end_at": end.isoformat(),
            "attendees": ["owner@example.com"],
            "is_all_day": False,
        },
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["event"]["event_id"] == "evt-created-1"
    assert payload["event"]["title"] == "Donna Sync"


def test_create_calendar_event_rejects_invalid_window(client: TestClient) -> None:
    _login(client)
    start = datetime(2026, 4, 10, 15, 0, tzinfo=timezone.utc)

    resp = client.post(
        "/api/v1/calendar/events",
        json={
            "title": "Invalid",
            "start_at": start.isoformat(),
            "end_at": start.isoformat(),
        },
    )
    assert resp.status_code == 400
