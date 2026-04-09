from __future__ import annotations

from datetime import datetime, timezone
import uuid

import pytest
from fastapi.testclient import TestClient

from app.core.db import get_db
from app.main import fastapi_app
from app.models import ConnectedAccount
from app.services.teams_service import TeamsService


def _login(client: TestClient) -> dict:
    resp = client.post(
        "/api/v1/auth/dev-login",
        json={"email": "teams-api-test@example.com", "full_name": "Teams Tester"},
    )
    assert resp.status_code == 200
    return resp.json()["user"]


def _seed_teams_account(client: TestClient, user_id: str) -> ConnectedAccount:
    db_gen = fastapi_app.dependency_overrides[get_db]()
    db = next(db_gen)
    account = ConnectedAccount(
        id=uuid.uuid4(),
        user_id=uuid.UUID(user_id),
        provider="teams",
        provider_account_id="teams-account-1",
        account_email="teams-user@example.com",
        access_token_encrypted="dummy",
        refresh_token_encrypted=None,
        scopes="Chat.ReadWrite",
        account_metadata={"tenant": "common"},
    )
    db.add(account)
    db.commit()
    return account


def test_teams_conversations_requires_auth(client: TestClient) -> None:
    resp = client.get("/api/v1/teams/conversations")
    assert resp.status_code == 401


def test_list_teams_conversations_mocked(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    user = _login(client)
    account = _seed_teams_account(client, user["id"])

    def fake_list(self, *, user_id, account_id=None, search=None, unread_only=False):
        return [
            {
                "account_id": str(account.id),
                "conversation_id": "19:chat-id",
                "name": "Project Chat",
                "sender": "Alice",
                "preview": "Latest Teams update",
                "unread_count": 1,
                "message_count": 4,
                "has_attachments": False,
                "latest_received_at": datetime.now(timezone.utc),
            }
        ]

    monkeypatch.setattr(TeamsService, "list_conversations", fake_list)

    resp = client.get("/api/v1/teams/conversations")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["total"] == 1
    assert payload["conversations"][0]["conversation_id"] == "19:chat-id"


def test_send_teams_message_mocked(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    user = _login(client)
    account = _seed_teams_account(client, user["id"])

    def fake_send(self, *, user_id, conversation_id, text, account_id=None):
        assert conversation_id == "19:chat-id"
        assert text == "Hello Teams"
        return {"conversation_id": conversation_id, "message_id": "abc-123"}

    monkeypatch.setattr(TeamsService, "send_message", fake_send)

    resp = client.post(
        "/api/v1/teams/send",
        json={"account_id": str(account.id), "conversation_id": "19:chat-id", "text": "Hello Teams"},
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["status"] == "sent"
    assert payload["message_id"] == "abc-123"
