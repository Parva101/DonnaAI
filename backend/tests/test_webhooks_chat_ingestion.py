"""Tests webhook-driven chat ingestion for Slack and Teams."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.db import get_db
from app.main import fastapi_app
from app.models import ChatConversation, ChatMessage, ConnectedAccount


def _login(client: TestClient, *, email: str) -> dict:
    resp = client.post(
        "/api/v1/auth/dev-login",
        json={"email": email, "full_name": "Webhook Tester"},
    )
    assert resp.status_code == 200
    return resp.json()["user"]


def _db_session():
    db_gen = fastapi_app.dependency_overrides[get_db]()
    db = next(db_gen)
    return db


def _seed_account(
    *,
    user_id: str,
    provider: str,
    provider_account_id: str,
    metadata: dict | None = None,
) -> ConnectedAccount:
    db = _db_session()
    account = ConnectedAccount(
        id=uuid.uuid4(),
        user_id=uuid.UUID(user_id),
        provider=provider,
        provider_account_id=provider_account_id,
        account_email=f"{provider_account_id}@example.com",
        access_token_encrypted="dummy",
        refresh_token_encrypted=None,
        scopes=None,
        account_metadata=metadata or {},
    )
    db.add(account)
    db.commit()
    db.refresh(account)
    return account


def test_slack_webhook_persists_message_to_chat_tables(client: TestClient) -> None:
    user = _login(client, email="webhook-slack@example.com")
    account = _seed_account(
        user_id=user["id"],
        provider="slack",
        provider_account_id="T123",
        metadata={"authed_user_id": "U-ME"},
    )

    payload = {
        "team_id": "T123",
        "event_id": "Ev-1",
        "event": {
            "type": "message",
            "channel": "C123",
            "channel_type": "channel",
            "user": "U123",
            "text": "Hello from Slack webhook",
            "ts": "1712086400.000100",
        },
    }
    resp = client.post("/api/v1/webhooks/slack/events", json=payload)
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"

    db = _db_session()
    conversation = db.execute(
        select(ChatConversation).where(
            ChatConversation.user_id == uuid.UUID(user["id"]),
            ChatConversation.account_id == account.id,
            ChatConversation.platform == "slack",
            ChatConversation.external_conversation_id == "C123",
        )
    ).scalar_one_or_none()
    assert conversation is not None
    assert conversation.preview == "Hello from Slack webhook"

    message = db.execute(
        select(ChatMessage).where(
            ChatMessage.user_id == uuid.UUID(user["id"]),
            ChatMessage.account_id == account.id,
            ChatMessage.platform == "slack",
            ChatMessage.external_message_id == "1712086400.000100",
        )
    ).scalar_one_or_none()
    assert message is not None
    assert message.text == "Hello from Slack webhook"
    assert message.direction == "inbound"


def test_teams_webhook_persists_resource_data_message(client: TestClient) -> None:
    user = _login(client, email="webhook-teams@example.com")
    account = _seed_account(
        user_id=user["id"],
        provider="teams",
        provider_account_id="aad-owner-1",
        metadata={"tenant": "common"},
    )

    payload = {
        "value": [
            {
                "tenantId": "common",
                "changeType": "created",
                "resource": "chats('19:chat-1')/messages('m-1')",
                "resourceData": {
                    "id": "m-1",
                    "chatId": "19:chat-1",
                    "createdDateTime": "2026-04-09T01:00:00Z",
                    "from": {"user": {"id": "aad-sender-1", "displayName": "Alice"}},
                    "body": {"contentType": "html", "content": "<p>Hello <b>Donna</b></p>"},
                },
            }
        ]
    }
    resp = client.post("/api/v1/webhooks/teams/events", json=payload)
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"

    db = _db_session()
    conversation = db.execute(
        select(ChatConversation).where(
            ChatConversation.user_id == uuid.UUID(user["id"]),
            ChatConversation.account_id == account.id,
            ChatConversation.platform == "teams",
            ChatConversation.external_conversation_id == "19:chat-1",
        )
    ).scalar_one_or_none()
    assert conversation is not None
    assert conversation.preview == "Hello Donna"

    message = db.execute(
        select(ChatMessage).where(
            ChatMessage.user_id == uuid.UUID(user["id"]),
            ChatMessage.account_id == account.id,
            ChatMessage.platform == "teams",
            ChatMessage.external_message_id == "m-1",
        )
    ).scalar_one_or_none()
    assert message is not None
    assert message.text == "Hello Donna"
    assert message.direction == "inbound"
