"""Tests for Email Hub API routes."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db import get_db
from app.main import app
from app.models import Base, Email, ConnectedAccount, User


def _auth_login(client: TestClient) -> dict:
    """Dev-login and return the user dict."""
    resp = client.post(
        "/api/v1/auth/dev-login",
        json={"email": "test-email@test.com", "full_name": "Email Tester"},
    )
    assert resp.status_code == 200
    return resp.json()["user"]


def _create_account_and_emails(client: TestClient, user_id: str, db_override):
    """Create a connected account and some emails directly in the DB for testing."""
    from collections.abc import Generator
    from sqlalchemy.orm import Session
    from datetime import datetime, timezone

    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    # We reuse the test client's DB via dependency override
    # Instead, let's insert through the API-accessible DB
    pass


# ── Fixtures ─────────────────────────────────────────────


@pytest.fixture()
def authed_client(client: TestClient):
    """Client that is authenticated via dev-login."""
    _auth_login(client)
    return client


@pytest.fixture()
def client_with_emails(client: TestClient):
    """Client with authenticated user, a connected account, and some test emails."""
    user_data = _auth_login(client)
    user_id = user_data["id"]

    # Access the overridden DB session
    db_gen = app.dependency_overrides[get_db]()
    db = next(db_gen)

    # Create a connected account (Google)
    account = ConnectedAccount(
        id=uuid.uuid4(),
        user_id=uuid.UUID(user_id),
        provider="google",
        provider_account_id="123456",
        account_email="tester@gmail.com",
        scopes="openid,email,profile,gmail.modify",
        access_token_encrypted="fake-token",
        refresh_token_encrypted="fake-refresh",
    )
    db.add(account)
    db.commit()
    db.refresh(account)

    # Create test emails
    from datetime import datetime, timezone, timedelta

    now = datetime.now(timezone.utc)
    emails = [
        Email(
            user_id=uuid.UUID(user_id),
            account_id=account.id,
            gmail_message_id=f"msg_{i}",
            thread_id=f"thread_{i}",
            subject=f"Test Email {i}",
            snippet=f"This is email snippet {i}",
            from_address=f"sender{i}@example.com",
            from_name=f"Sender {i}",
            to_addresses=[{"name": "Me", "address": "tester@gmail.com"}],
            body_text=f"Full body of email {i}",
            body_html=f"<p>Full body of email {i}</p>",
            category=["work", "personal", "school", "finance", "notifications"][i % 5],
            category_source="rule",
            is_read=i % 2 == 0,
            is_starred=i == 0,
            has_attachments=i == 2,
            received_at=now - timedelta(hours=i),
        )
        for i in range(10)
    ]
    db.add_all(emails)
    db.commit()

    return client, user_id, account.id, [e.id for e in emails]


# ── Test: list emails ────────────────────────────────────


def test_list_emails_requires_auth(client: TestClient):
    resp = client.get("/api/v1/emails")
    assert resp.status_code == 401


def test_list_emails_empty(authed_client: TestClient):
    resp = authed_client.get("/api/v1/emails")
    assert resp.status_code == 200
    data = resp.json()
    assert data["emails"] == []
    assert data["total"] == 0
    assert data["categories"] == []


def test_list_emails_returns_emails(client_with_emails):
    client, user_id, account_id, email_ids = client_with_emails
    resp = client.get("/api/v1/emails")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 10
    assert len(data["emails"]) == 10
    # Should be sorted by received_at desc (most recent first)
    assert data["emails"][0]["subject"] == "Test Email 0"


def test_list_emails_filter_by_category(client_with_emails):
    client, *_ = client_with_emails
    resp = client.get("/api/v1/emails?category=work")
    assert resp.status_code == 200
    data = resp.json()
    for email in data["emails"]:
        assert email["category"] == "work"
    assert data["total"] == 2  # indices 0, 5


def test_list_emails_filter_by_read_status(client_with_emails):
    client, *_ = client_with_emails
    # Unread
    resp = client.get("/api/v1/emails?is_read=false")
    assert resp.status_code == 200
    data = resp.json()
    for email in data["emails"]:
        assert email["is_read"] is False
    assert data["total"] == 5  # odd indices


def test_list_emails_search(client_with_emails):
    client, *_ = client_with_emails
    resp = client.get("/api/v1/emails?search=sender3")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    assert any("sender3" in e["from_address"] for e in data["emails"])


def test_list_emails_pagination(client_with_emails):
    client, *_ = client_with_emails
    resp = client.get("/api/v1/emails?limit=3&offset=0")
    assert resp.status_code == 200
    page1 = resp.json()
    assert len(page1["emails"]) == 3
    assert page1["total"] == 10

    resp = client.get("/api/v1/emails?limit=3&offset=3")
    assert resp.status_code == 200
    page2 = resp.json()
    assert len(page2["emails"]) == 3
    # Ensure no overlap
    ids1 = {e["id"] for e in page1["emails"]}
    ids2 = {e["id"] for e in page2["emails"]}
    assert ids1.isdisjoint(ids2)


# ── Test: get categories ─────────────────────────────────


def test_get_categories(client_with_emails):
    client, *_ = client_with_emails
    resp = client.get("/api/v1/emails/categories")
    assert resp.status_code == 200
    cats = resp.json()
    assert len(cats) == 5  # work, personal, school, finance, notifications
    cat_names = {c["category"] for c in cats}
    assert "work" in cat_names
    assert "school" in cat_names
    # Each category should have count + unread
    for cat in cats:
        assert "count" in cat
        assert "unread" in cat
        assert cat["count"] >= 1


# ── Test: get single email ───────────────────────────────


def test_get_email_returns_full_body(client_with_emails):
    client, user_id, account_id, email_ids = client_with_emails
    email_id = str(email_ids[0])
    resp = client.get(f"/api/v1/emails/{email_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == email_id
    assert data["body_text"] == "Full body of email 0"
    assert data["body_html"] == "<p>Full body of email 0</p>"
    assert data["subject"] == "Test Email 0"


def test_get_email_not_found(authed_client: TestClient):
    fake_id = str(uuid.uuid4())
    resp = authed_client.get(f"/api/v1/emails/{fake_id}")
    assert resp.status_code == 404


# ── Test: update email ───────────────────────────────────


def test_update_email_star(client_with_emails):
    client, user_id, account_id, email_ids = client_with_emails
    email_id = str(email_ids[1])  # not starred

    resp = client.patch(
        f"/api/v1/emails/{email_id}",
        json={"is_starred": True},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_starred"] is True


def test_update_email_mark_read(client_with_emails):
    client, user_id, account_id, email_ids = client_with_emails
    email_id = str(email_ids[1])  # index 1 is unread

    resp = client.patch(
        f"/api/v1/emails/{email_id}",
        json={"is_read": True},
    )
    assert resp.status_code == 200
    assert resp.json()["is_read"] is True


def test_update_email_reclassify(client_with_emails):
    client, user_id, account_id, email_ids = client_with_emails
    email_id = str(email_ids[0])  # originally "work"

    resp = client.patch(
        f"/api/v1/emails/{email_id}",
        json={"category": "finance"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["category"] == "finance"
    assert data["category_source"] == "user"


def test_update_email_not_found(authed_client: TestClient):
    fake_id = str(uuid.uuid4())
    resp = authed_client.patch(
        f"/api/v1/emails/{fake_id}",
        json={"is_read": True},
    )
    assert resp.status_code == 404


# ── Test: sync requires auth ─────────────────────────────


def test_sync_requires_auth(client: TestClient):
    resp = client.post(
        "/api/v1/emails/sync",
        json={"account_id": str(uuid.uuid4())},
    )
    assert resp.status_code == 401


def test_sync_with_invalid_account(authed_client: TestClient):
    resp = authed_client.post(
        "/api/v1/emails/sync",
        json={"account_id": str(uuid.uuid4())},
    )
    assert resp.status_code == 404


# ── Test: send requires auth ─────────────────────────────


def test_send_requires_auth(client: TestClient):
    resp = client.post(
        "/api/v1/emails/send",
        json={
            "account_id": str(uuid.uuid4()),
            "to": ["test@test.com"],
            "body": "Hello",
        },
    )
    assert resp.status_code == 401


def test_send_with_invalid_account(authed_client: TestClient):
    resp = authed_client.post(
        "/api/v1/emails/send",
        json={
            "account_id": str(uuid.uuid4()),
            "to": ["test@test.com"],
            "body": "Hello",
        },
    )
    assert resp.status_code == 404
