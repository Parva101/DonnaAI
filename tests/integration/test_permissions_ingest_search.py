from datetime import datetime, timezone


def test_ingest_blocked_without_read_scope(client):
    payload = {
        "tenant_id": "tenant-a",
        "platform": "whatsapp",
        "account_id": "default",
        "event_type": "message.received",
        "source_event_id": "evt-1",
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "payload": {
            "chat_key": "chat-alpha",
            "source_message_id": "msg-1",
            "body_text": "Meeting moved to 6pm",
        },
    }
    resp = client.post("/v1/ingest/events", json=payload)
    assert resp.status_code == 403


def test_ingest_idempotency_and_search(client):
    scope_payload = {
        "tenant_id": "tenant-a",
        "platform": "whatsapp",
        "account_id": "default",
        "chat_key": "chat-alpha",
        "read_allowed": True,
        "write_allowed": False,
        "relay_allowed": False,
        "updated_by": "test",
    }
    scope_resp = client.put("/v1/permissions/scopes", json=scope_payload)
    assert scope_resp.status_code == 200

    ingest_payload = {
        "tenant_id": "tenant-a",
        "platform": "whatsapp",
        "account_id": "default",
        "event_type": "message.received",
        "source_event_id": "evt-2",
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "payload": {
            "chat_key": "chat-alpha",
            "thread_key": "thread-alpha",
            "source_message_id": "msg-2",
            "sender_key": "+15550000001",
            "body_text": "Meeting moved to 6pm",
            "metadata": {"lang": "en"},
        },
    }

    first = client.post("/v1/ingest/events", json=ingest_payload)
    assert first.status_code == 200
    assert first.json()["created"] is True
    assert first.json()["message_id"] is not None

    second = client.post("/v1/ingest/events", json=ingest_payload)
    assert second.status_code == 200
    assert second.json()["created"] is False

    search = client.get(
        "/v1/search/messages",
        params={"tenant_id": "tenant-a", "platform": "whatsapp", "q": "Meeting", "limit": 10},
    )
    assert search.status_code == 200
    results = search.json()
    assert len(results) == 1
    assert results[0]["chat_key"] == "chat-alpha"

