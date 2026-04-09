"""Integration-style API tests for chat persistence across platforms."""

from __future__ import annotations

from datetime import datetime, timezone
import uuid

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import select

from app.core.db import get_db
from app.main import fastapi_app
from app.models import ChatConversation, ChatMessage, ChatOutboundAction, ConnectedAccount
from app.services.slack_service import SlackService
from app.services.teams_service import TeamsService
from app.services.whatsapp_service import WhatsAppService


def _login(client: TestClient, *, email: str) -> dict:
    resp = client.post(
        "/api/v1/auth/dev-login",
        json={"email": email, "full_name": "Donna Tester"},
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
    scopes: str | None,
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
        scopes=scopes,
        account_metadata={},
    )
    db.add(account)
    db.commit()
    db.refresh(account)
    return account


def test_slack_api_persists_conversations_messages_and_outbound(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = _login(client, email="persist-slack@example.com")
    account = _seed_account(
        user_id=user["id"],
        provider="slack",
        provider_account_id="T-SLACK",
        scopes="channels:history,chat:write",
    )

    def fake_list_conversations(self, *, user_id, account_id=None, search=None, unread_only=False):
        return [
            {
                "account_id": account.id,
                "conversation_id": "C-PERSIST-1",
                "name": "general",
                "sender": "Alice",
                "preview": "hello",
                "unread_count": 1,
                "message_count": 2,
                "has_attachments": False,
                "latest_received_at": datetime.now(timezone.utc),
                "is_im": False,
                "is_private": False,
            }
        ]

    def fake_list_messages(self, *, user_id, conversation_id, account_id=None, limit=50):
        return [
            {
                "ts": "1712086400.000100",
                "sender": "Alice",
                "user_id": "U1",
                "text": "Persist me",
                "subtype": None,
                "thread_ts": None,
                "has_attachments": False,
            }
        ]

    def fake_send(self, *, user_id, conversation_id, text, account_id=None):
        return {"channel": conversation_id, "ts": "1712086400.000200"}

    monkeypatch.setattr(SlackService, "list_conversations", fake_list_conversations)
    monkeypatch.setattr(SlackService, "list_messages", fake_list_messages)
    monkeypatch.setattr(SlackService, "send_message", fake_send)

    conv_resp = client.get(f"/api/v1/slack/conversations?account_id={account.id}")
    assert conv_resp.status_code == 200
    msg_resp = client.get(f"/api/v1/slack/conversations/C-PERSIST-1/messages?account_id={account.id}")
    assert msg_resp.status_code == 200
    send_resp = client.post(
        "/api/v1/slack/send",
        json={"account_id": str(account.id), "conversation_id": "C-PERSIST-1", "text": "Outbound persist"},
    )
    assert send_resp.status_code == 200

    db = _db_session()
    conversation = db.execute(
        select(ChatConversation).where(
            ChatConversation.user_id == uuid.UUID(user["id"]),
            ChatConversation.platform == "slack",
            ChatConversation.external_conversation_id == "C-PERSIST-1",
        )
    ).scalar_one_or_none()
    assert conversation is not None

    messages = list(
        db.execute(
            select(ChatMessage).where(
                ChatMessage.user_id == uuid.UUID(user["id"]),
                ChatMessage.platform == "slack",
                ChatMessage.conversation_id == conversation.id,
            )
        ).scalars()
    )
    assert any(m.direction == "inbound" for m in messages)
    assert any(m.direction == "outbound" for m in messages)

    outbound = db.execute(
        select(ChatOutboundAction).where(
            ChatOutboundAction.user_id == uuid.UUID(user["id"]),
            ChatOutboundAction.platform == "slack",
            ChatOutboundAction.target == "C-PERSIST-1",
        )
    ).scalar_one_or_none()
    assert outbound is not None
    assert outbound.status == "sent"


def test_teams_api_persists_conversation_and_outbound(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = _login(client, email="persist-teams@example.com")
    account = _seed_account(
        user_id=user["id"],
        provider="teams",
        provider_account_id="teams-account",
        scopes="Chat.ReadWrite",
    )

    def fake_list(self, *, user_id, account_id=None, search=None, unread_only=False):
        return [
            {
                "account_id": account.id,
                "conversation_id": "19:persist-chat",
                "name": "Project Chat",
                "sender": "Bob",
                "preview": "Teams preview",
                "unread_count": 0,
                "message_count": 1,
                "has_attachments": False,
                "latest_received_at": datetime.now(timezone.utc),
            }
        ]

    def fake_send(self, *, user_id, conversation_id, text, account_id=None):
        return {"conversation_id": conversation_id, "message_id": "m-123"}

    monkeypatch.setattr(TeamsService, "list_conversations", fake_list)
    monkeypatch.setattr(TeamsService, "send_message", fake_send)

    conv_resp = client.get(f"/api/v1/teams/conversations?account_id={account.id}")
    assert conv_resp.status_code == 200
    send_resp = client.post(
        "/api/v1/teams/send",
        json={"account_id": str(account.id), "conversation_id": "19:persist-chat", "text": "Teams outbound"},
    )
    assert send_resp.status_code == 200

    db = _db_session()
    conversation = db.execute(
        select(ChatConversation).where(
            ChatConversation.user_id == uuid.UUID(user["id"]),
            ChatConversation.platform == "teams",
            ChatConversation.external_conversation_id == "19:persist-chat",
        )
    ).scalar_one_or_none()
    assert conversation is not None

    outbound = db.execute(
        select(ChatOutboundAction).where(
            ChatOutboundAction.user_id == uuid.UUID(user["id"]),
            ChatOutboundAction.platform == "teams",
            ChatOutboundAction.target == "19:persist-chat",
        )
    ).scalar_one_or_none()
    assert outbound is not None
    assert outbound.status == "sent"


def test_whatsapp_api_persists_messages_and_outbound(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = _login(client, email="persist-whatsapp@example.com")
    account = _seed_account(
        user_id=user["id"],
        provider="whatsapp",
        provider_account_id="wa-account-1",
        scopes=None,
    )

    def fake_list_conversations(self, *, limit=5000, search=None, unread_only=False):
        return [
            {
                "conversation_id": "91999@s.whatsapp.net",
                "sender": "WA Contact",
                "preview": "WA preview",
                "unread_count": 0,
                "message_count": 1,
                "has_attachments": False,
                "latest_received_at": datetime.now(timezone.utc),
                "is_group": False,
            }
        ]

    def fake_list_messages(self, *, chat_jid, limit=100):
        return [
            {
                "message_id": "wa-msg-1",
                "sender": "WA Contact",
                "from_me": False,
                "text": "WA inbound",
                "message_type": "conversation",
                "timestamp": 1775116186000,
                "received_at": datetime.now(timezone.utc),
            }
        ]

    def fake_send(self, to: str, text: str):
        return {"status": "sent", "to": to, "message_id": "wa-out-1"}

    monkeypatch.setattr(WhatsAppService, "list_conversations", fake_list_conversations)
    monkeypatch.setattr(WhatsAppService, "list_conversation_messages", fake_list_messages)
    monkeypatch.setattr(WhatsAppService, "send_message", fake_send)

    conv_resp = client.get(f"/api/v1/whatsapp/conversations?account_id={account.id}")
    assert conv_resp.status_code == 200
    msg_resp = client.get(
        f"/api/v1/whatsapp/conversations/91999@s.whatsapp.net/messages?account_id={account.id}",
    )
    assert msg_resp.status_code == 200
    send_resp = client.post(
        f"/api/v1/whatsapp/send?account_id={account.id}",
        json={"to": "91999@s.whatsapp.net", "text": "WA outbound"},
    )
    assert send_resp.status_code == 200

    db = _db_session()
    conversation = db.execute(
        select(ChatConversation).where(
            ChatConversation.user_id == uuid.UUID(user["id"]),
            ChatConversation.platform == "whatsapp",
            ChatConversation.external_conversation_id == "91999@s.whatsapp.net",
        )
    ).scalar_one_or_none()
    assert conversation is not None

    messages = list(
        db.execute(
            select(ChatMessage).where(
                ChatMessage.user_id == uuid.UUID(user["id"]),
                ChatMessage.platform == "whatsapp",
                ChatMessage.conversation_id == conversation.id,
            )
        ).scalars()
    )
    assert any(m.direction == "inbound" for m in messages)
    assert any(m.direction == "outbound" for m in messages)

    outbound = db.execute(
        select(ChatOutboundAction).where(
            ChatOutboundAction.user_id == uuid.UUID(user["id"]),
            ChatOutboundAction.platform == "whatsapp",
            ChatOutboundAction.target == "91999@s.whatsapp.net",
        )
    ).scalar_one_or_none()
    assert outbound is not None
    assert outbound.status == "sent"
    assert outbound.provider_message_id == "wa-out-1"
