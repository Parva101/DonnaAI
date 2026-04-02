from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app.core.db import get_db
from app.main import app
from app.models import Email


def _login(client: TestClient) -> dict:
    resp = client.post(
        "/api/v1/auth/dev-login",
        json={"email": "ai-api-test@example.com", "full_name": "AI Tester"},
    )
    assert resp.status_code == 200
    return resp.json()["user"]


def _seed_email(client: TestClient, user_id: str) -> str:
    db_gen = app.dependency_overrides[get_db]()
    db = next(db_gen)
    email = Email(
        user_id=uuid.UUID(user_id),
        account_id=uuid.uuid4(),
        gmail_message_id=str(uuid.uuid4()),
        thread_id="thread-ai-1",
        subject="Urgent: payment due today",
        snippet="Please review and pay the invoice today",
        from_address="billing@example.com",
        from_name="Billing",
        category="finance",
        category_source="ai",
        is_read=False,
    )
    db.add(email)
    db.commit()
    db.refresh(email)
    return str(email.id)


def test_ai_priority_score_and_search(client: TestClient) -> None:
    user = _login(client)
    email_id = _seed_email(client, user["id"])

    score_resp = client.post("/api/v1/ai/priority/score", json={"email_ids": [email_id]})
    assert score_resp.status_code == 200
    score_payload = score_resp.json()
    assert len(score_payload["results"]) == 1
    assert score_payload["results"][0]["label"] in {"low", "medium", "high"}

    search_resp = client.post("/api/v1/ai/search", json={"query": "invoice payment", "limit": 10})
    assert search_resp.status_code == 200
    search_payload = search_resp.json()
    assert len(search_payload["results"]) >= 1


def test_ai_action_item_extract_and_list(client: TestClient) -> None:
    _login(client)

    extract_resp = client.post(
        "/api/v1/ai/action-items/extract",
        json={
            "source_platform": "gmail",
            "text": "Please review the attached proposal. Follow up with legal tomorrow.",
        },
    )
    assert extract_resp.status_code == 200
    extracted = extract_resp.json()["items"]
    assert len(extracted) >= 1

    list_resp = client.get("/api/v1/ai/action-items")
    assert list_resp.status_code == 200
    listed = list_resp.json()["items"]
    assert len(listed) >= 1
