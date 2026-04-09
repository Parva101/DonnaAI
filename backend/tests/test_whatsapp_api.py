"""Tests for WhatsApp OpenClaw API routes."""

from __future__ import annotations

from datetime import datetime, timezone
import uuid

import pytest
from fastapi.testclient import TestClient

from app.core.db import get_db
from app.main import fastapi_app
from app.models import ConnectedAccount
from app.services.chat_sync_service import ChatSyncService
from app.services.whatsapp_service import WhatsAppService


def _login(client: TestClient) -> dict:
    resp = client.post(
        "/api/v1/auth/dev-login",
        json={"email": "whatsapp-api-test@example.com", "full_name": "WhatsApp Tester"},
    )
    assert resp.status_code == 200
    return resp.json()["user"]


def _seed_whatsapp_account(client: TestClient, user_id: str) -> ConnectedAccount:
    db_gen = fastapi_app.dependency_overrides[get_db]()
    db = next(db_gen)
    account = ConnectedAccount(
        id=uuid.uuid4(),
        user_id=uuid.UUID(user_id),
        provider="whatsapp",
        provider_account_id="donna-whatsapp-poc",
        account_email="donna-whatsapp-poc",
        access_token_encrypted=None,
        refresh_token_encrypted=None,
        scopes=None,
        account_metadata={"device_id": "donna-whatsapp-poc"},
    )
    db.add(account)
    db.commit()
    return account


def test_whatsapp_conversations_requires_auth(client: TestClient) -> None:
    resp = client.get("/api/v1/whatsapp/conversations")
    assert resp.status_code == 401


def test_list_whatsapp_conversations_mocked(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    user = _login(client)
    account = _seed_whatsapp_account(client, user["id"])

    def fake_list_conversations(self, *, limit=5000, search=None, unread_only=False):
        assert unread_only is True
        return [
            {
                "conversation_id": "120363123@g.us",
                "sender": "Group 120363123",
                "preview": "Latest message",
                "unread_count": 2,
                "message_count": 8,
                "has_attachments": False,
                "latest_received_at": datetime.now(timezone.utc),
                "is_group": True,
            }
        ]

    monkeypatch.setattr(WhatsAppService, "list_conversations", fake_list_conversations)

    resp = client.get(f"/api/v1/whatsapp/conversations?account_id={account.id}&unread_only=true")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["total"] == 1
    assert payload["conversations"][0]["conversation_id"] == "120363123@g.us"
    assert payload["conversations"][0]["unread_count"] == 2


def test_list_whatsapp_messages_mocked(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    user = _login(client)
    account = _seed_whatsapp_account(client, user["id"])

    def fake_list_messages(self, *, chat_jid, limit=100, scan_limit=5000):
        assert chat_jid == "91999@s.whatsapp.net"
        assert limit == 20
        return [
            {
                "message_id": "abc-1",
                "sender": "You",
                "from_me": True,
                "text": "Hello there",
                "message_type": "conversation",
                "timestamp": 1775116186000,
                "received_at": datetime.now(timezone.utc),
            }
        ]

    monkeypatch.setattr(WhatsAppService, "list_conversation_messages", fake_list_messages)
    resp = client.get(
        f"/api/v1/whatsapp/conversations/91999@s.whatsapp.net/messages?account_id={account.id}&limit=20"
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["total"] == 1
    assert payload["messages"][0]["message_id"] == "abc-1"
    assert payload["messages"][0]["from_me"] is True


def test_send_whatsapp_message_mocked(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    user = _login(client)
    _seed_whatsapp_account(client, user["id"])

    def fake_send(self, to: str, text: str):
        assert to == "91999@s.whatsapp.net"
        assert text == "Ping from Donna"
        return {"status": "sent", "to": to, "message_id": "wa-msg-2"}

    monkeypatch.setattr(WhatsAppService, "send_message", fake_send)
    resp = client.post(
        "/api/v1/whatsapp/send",
        json={"to": "91999@s.whatsapp.net", "text": "Ping from Donna"},
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["status"] == "sent"
    assert payload["message_id"] == "wa-msg-2"


def test_send_whatsapp_message_normalizes_target(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    user = _login(client)
    account = _seed_whatsapp_account(client, user["id"])
    observed: dict[str, str] = {}

    def fake_send(self, to: str, text: str):
        observed["to"] = to
        assert text == "Normalized"
        return {"status": "sent", "to": to, "message_id": "wa-msg-3"}

    monkeypatch.setattr(WhatsAppService, "send_message", fake_send)
    resp = client.post(
        f"/api/v1/whatsapp/send?account_id={account.id}",
        json={"to": "+1 (602) 740-6693", "text": "Normalized"},
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert observed["to"] == "16027406693@s.whatsapp.net"
    assert payload["to"] == "16027406693@s.whatsapp.net"
    assert payload["message_id"] == "wa-msg-3"


def test_send_whatsapp_message_rejects_invalid_target(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = _login(client)
    account = _seed_whatsapp_account(client, user["id"])

    monkeypatch.setattr(WhatsAppService, "send_message", lambda self, to, text: {"status": "sent"})
    resp = client.post(
        f"/api/v1/whatsapp/send?account_id={account.id}",
        json={"to": "invalid@domain.com", "text": "Hello"},
    )
    assert resp.status_code == 400


def test_whatsapp_sync_mocked(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    user = _login(client)
    account = _seed_whatsapp_account(client, user["id"])

    def fake_sync(
        self,
        *,
        user_id,
        account_id,
        conversation_limit,
        message_limit,
        unread_only=False,
        search=None,
    ):
        assert account_id == account.id
        assert conversation_limit == 25
        assert message_limit == 50
        assert unread_only is True
        assert search == "billing"
        return {
            "platform": "whatsapp",
            "conversations_discovered": 3,
            "conversations_synced": 3,
            "messages_synced": 17,
            "failures": [],
        }

    monkeypatch.setattr(ChatSyncService, "sync_whatsapp_ingestion", fake_sync)

    resp = client.post(
        "/api/v1/whatsapp/sync",
        json={
            "account_id": str(account.id),
            "conversation_limit": 25,
            "message_limit": 50,
            "unread_only": True,
            "search": "billing",
        },
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["status"] == "ok"
    assert payload["conversations_discovered"] == 3
    assert payload["messages_synced"] == 17


def test_whatsapp_sync_requires_connected_account(client: TestClient) -> None:
    _login(client)
    resp = client.post("/api/v1/whatsapp/sync", json={})
    assert resp.status_code == 400
