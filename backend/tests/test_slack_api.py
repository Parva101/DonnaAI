"""Tests for Slack API routes."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.services.slack_service import SlackService


def _login(client: TestClient) -> dict:
    resp = client.post(
        "/api/v1/auth/dev-login",
        json={"email": "slack-api-test@example.com", "full_name": "Slack Tester"},
    )
    assert resp.status_code == 200
    return resp.json()["user"]


def test_slack_conversations_requires_auth(client: TestClient) -> None:
    resp = client.get("/api/v1/slack/conversations")
    assert resp.status_code == 401


def test_list_slack_conversations_mocked(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    user = _login(client)
    fake_account_id = uuid.uuid4()

    def fake_list(self, *, user_id, account_id=None, search=None, unread_only=False):
        assert str(user_id) == user["id"]
        return [
            {
                "account_id": account_id or fake_account_id,
                "conversation_id": "C123",
                "name": "general",
                "sender": "Alice",
                "preview": "Hello Donna",
                "unread_count": 1,
                "message_count": 2,
                "has_attachments": False,
                "latest_received_at": None,
                "is_im": False,
                "is_private": False,
            }
        ]

    monkeypatch.setattr(SlackService, "list_conversations", fake_list)

    resp = client.get("/api/v1/slack/conversations")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["conversations"][0]["conversation_id"] == "C123"
    assert data["conversations"][0]["sender"] == "Alice"


def test_list_slack_messages_mocked(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _login(client)

    def fake_messages(self, *, user_id, conversation_id, account_id=None, limit=50):
        assert conversation_id == "C123"
        assert limit == 20
        return [
            {
                "ts": "1712086400.000100",
                "sender": "Alice",
                "user_id": "U1",
                "text": "Ping",
                "subtype": None,
                "thread_ts": None,
                "has_attachments": False,
            }
        ]

    monkeypatch.setattr(SlackService, "list_messages", fake_messages)
    resp = client.get("/api/v1/slack/conversations/C123/messages?limit=20")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["messages"][0]["text"] == "Ping"


def test_send_slack_message_mocked(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _login(client)

    def fake_send(self, *, user_id, conversation_id, text, account_id=None):
        assert conversation_id == "C123"
        assert text == "Hello from Donna"
        return {"channel": "C123", "ts": "1712086400.000200"}

    monkeypatch.setattr(SlackService, "send_message", fake_send)
    resp = client.post(
        "/api/v1/slack/send",
        json={"conversation_id": "C123", "text": "Hello from Donna"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "sent"
    assert data["channel"] == "C123"
