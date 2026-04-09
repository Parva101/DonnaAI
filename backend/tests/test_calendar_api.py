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
