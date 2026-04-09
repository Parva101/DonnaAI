from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app.core.db import get_db
from app.main import app
from app.models import Email, NewsArticle


def _login(client: TestClient) -> dict:
    resp = client.post(
        "/api/v1/auth/dev-login",
        json={"email": "notif-api-test@example.com", "full_name": "Notification Tester"},
    )
    assert resp.status_code == 200
    return resp.json()["user"]


def _seed_digest_data(client: TestClient, user_id: str) -> None:
    db_gen = app.dependency_overrides[get_db]()
    db = next(db_gen)
    db.add(
        Email(
            user_id=uuid.UUID(user_id),
            account_id=uuid.uuid4(),
            gmail_message_id=str(uuid.uuid4()),
            thread_id="notif-thread",
            subject="Action required",
            snippet="Please check this today",
            from_address="ops@example.com",
            from_name="Ops",
            category="work",
            category_source="ai",
            is_read=False,
        )
    )
    db.add(
        NewsArticle(
            user_id=uuid.UUID(user_id),
            source_id=None,
            external_id="news-1",
            title="Major AI launch",
            url="https://example.com/news/1",
            source_name="Example News",
            summary="Short summary",
            topic="tech",
            relevance_score=0.9,
        )
    )
    db.commit()


def test_notification_preferences_and_digest(client: TestClient) -> None:
    user = _login(client)
    _seed_digest_data(client, user["id"])

    prefs_resp = client.get("/api/v1/notifications/preferences")
    assert prefs_resp.status_code == 200
    assert prefs_resp.json()["preferences"]["daily_digest_enabled"] is True

    patch_resp = client.patch(
        "/api/v1/notifications/preferences",
        json={"focus_mode": True, "daily_digest_hour_utc": 9},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["preferences"]["focus_mode"] is True

    digest_resp = client.get("/api/v1/notifications/digest")
    assert digest_resp.status_code == 200
    payload = digest_resp.json()
    assert "summary" in payload
    assert len(payload["top_items"]) >= 1
