from __future__ import annotations

from fastapi.testclient import TestClient


def _login(client: TestClient) -> dict:
    resp = client.post(
        "/api/v1/auth/dev-login",
        json={"email": "voice-api-test@example.com", "full_name": "Voice Tester"},
    )
    assert resp.status_code == 200
    return resp.json()["user"]


def test_create_and_list_voice_calls(client: TestClient) -> None:
    _login(client)

    create_resp = client.post(
        "/api/v1/voice/calls",
        json={
            "intent": "Book a table for 2 tonight",
            "target_name": "Nobu",
            "target_phone": "+12125550123",
        },
    )
    assert create_resp.status_code == 200
    call = create_resp.json()
    assert call["status"] in {"completed", "queued_external"}

    list_resp = client.get("/api/v1/voice/calls")
    assert list_resp.status_code == 200
    payload = list_resp.json()
    assert payload["total"] >= 1
