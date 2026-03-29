"""Tests for unified inbox API routes."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import uuid

import pytest
from fastapi.testclient import TestClient

from app.core.db import get_db
from app.main import app
from app.models import ConnectedAccount, Email


def _auth_login(client: TestClient) -> dict:
    resp = client.post(
        "/api/v1/auth/dev-login",
        json={"email": "test-inbox@test.com", "full_name": "Inbox Tester"},
    )
    assert resp.status_code == 200
    return resp.json()["user"]


@pytest.fixture()
def authed_client(client: TestClient) -> TestClient:
    _auth_login(client)
    return client


@pytest.fixture()
def client_with_threaded_emails(client: TestClient):
    user_data = _auth_login(client)
    user_id = user_data["id"]

    db_gen = app.dependency_overrides[get_db]()
    db = next(db_gen)

    account = ConnectedAccount(
        id=uuid.uuid4(),
        user_id=uuid.UUID(user_id),
        provider="google",
        provider_account_id="google-sub-1",
        account_email="inbox.tester@gmail.com",
        scopes="openid,email,profile,gmail.modify",
        access_token_encrypted="fake-token",
        refresh_token_encrypted="fake-refresh",
    )
    db.add(account)
    db.commit()

    now = datetime.now(timezone.utc)
    emails = [
        # thread_alpha (3 total, 1 unread)
        Email(
            user_id=uuid.UUID(user_id),
            account_id=account.id,
            gmail_message_id="alpha_1",
            thread_id="thread_alpha",
            subject="Project kickoff",
            snippet="Latest update on kickoff tasks",
            from_address="alice@example.com",
            from_name="Alice",
            category="work",
            category_source="ai",
            is_read=False,
            received_at=now - timedelta(minutes=1),
        ),
        Email(
            user_id=uuid.UUID(user_id),
            account_id=account.id,
            gmail_message_id="alpha_2",
            thread_id="thread_alpha",
            subject="Re: Project kickoff",
            snippet="Older reply in the same thread",
            from_address="alice@example.com",
            from_name="Alice",
            category="work",
            category_source="ai",
            is_read=True,
            received_at=now - timedelta(hours=2),
        ),
        Email(
            user_id=uuid.UUID(user_id),
            account_id=account.id,
            gmail_message_id="alpha_3",
            thread_id="thread_alpha",
            subject="Re: Project kickoff",
            snippet="Oldest reply in the same thread",
            from_address="alice@example.com",
            from_name="Alice",
            category="work",
            category_source="ai",
            is_read=True,
            received_at=now - timedelta(days=1),
        ),
        # thread_beta (1 total, 0 unread)
        Email(
            user_id=uuid.UUID(user_id),
            account_id=account.id,
            gmail_message_id="beta_1",
            thread_id="thread_beta",
            subject="Bank statement",
            snippet="Your monthly statement is ready",
            from_address="noreply@bank.com",
            from_name="Bank",
            category="finance",
            category_source="rule",
            is_read=True,
            received_at=now - timedelta(minutes=10),
        ),
        # thread_gamma (2 total, 2 unread)
        Email(
            user_id=uuid.UUID(user_id),
            account_id=account.id,
            gmail_message_id="gamma_1",
            thread_id="thread_gamma",
            subject="Invoice #123",
            snippet="Please review and pay invoice #123",
            from_address="billing@vendor.com",
            from_name="Vendor Billing",
            category="orders",
            category_source="ai",
            needs_review=True,
            is_read=False,
            received_at=now - timedelta(minutes=30),
        ),
        Email(
            user_id=uuid.UUID(user_id),
            account_id=account.id,
            gmail_message_id="gamma_2",
            thread_id="thread_gamma",
            subject="Re: Invoice #123",
            snippet="Following up on invoice #123",
            from_address="billing@vendor.com",
            from_name="Vendor Billing",
            category="orders",
            category_source="ai",
            needs_review=True,
            is_read=False,
            received_at=now - timedelta(minutes=31),
        ),
    ]
    db.add_all(emails)
    db.commit()

    return client


def test_list_inbox_conversations_requires_auth(client: TestClient):
    resp = client.get("/api/v1/inbox/conversations")
    assert resp.status_code == 401


def test_list_inbox_conversations_grouped(client_with_threaded_emails):
    resp = client_with_threaded_emails.get("/api/v1/inbox/conversations")
    assert resp.status_code == 200
    data = resp.json()

    assert data["total"] == 3
    assert len(data["conversations"]) == 3
    assert data["platform_counts"] == [{"platform": "gmail", "total": 3, "unread": 2}]

    first = data["conversations"][0]
    assert first["conversation_id"] == "thread_alpha"
    assert first["platform"] == "gmail"
    assert first["message_count"] == 3
    assert first["unread_count"] == 1
    assert first["sender"] == "Alice"


def test_list_inbox_conversations_unread_only(client_with_threaded_emails):
    resp = client_with_threaded_emails.get("/api/v1/inbox/conversations?unread_only=true")
    assert resp.status_code == 200
    data = resp.json()

    assert data["total"] == 2
    assert len(data["conversations"]) == 2
    assert all(c["unread_count"] > 0 for c in data["conversations"])


def test_list_inbox_conversations_search(client_with_threaded_emails):
    resp = client_with_threaded_emails.get("/api/v1/inbox/conversations?search=invoice")
    assert resp.status_code == 200
    data = resp.json()

    assert data["total"] == 1
    assert len(data["conversations"]) == 1
    assert data["conversations"][0]["conversation_id"] == "thread_gamma"


def test_list_inbox_conversations_unsupported_platform(client_with_threaded_emails):
    resp = client_with_threaded_emails.get("/api/v1/inbox/conversations?platform=slack")
    assert resp.status_code == 200
    data = resp.json()

    assert data["total"] == 0
    assert data["conversations"] == []
    assert data["platform_counts"] == []
