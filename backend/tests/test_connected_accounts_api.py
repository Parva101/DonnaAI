from __future__ import annotations

from fastapi.testclient import TestClient


ACCOUNTS_URL = "/api/v1/connected-accounts"


def _login(client: TestClient) -> None:
    """Helper: dev-login so the session cookie is set on the client."""
    client.post(
        "/api/v1/auth/dev-login",
        json={"email": "parv@example.com", "full_name": "Parv"},
    )


def _create_account(client: TestClient, *, provider: str = "google", provider_account_id: str = "g-123") -> dict:
    """Helper: create a connected account and return the response JSON."""
    resp = client.post(
        ACCOUNTS_URL,
        json={
            "provider": provider,
            "provider_account_id": provider_account_id,
            "account_email": "parv@gmail.com",
            "scopes": "email,calendar",
        },
    )
    return resp.json()


# ── Auth guard ─────────────────────────────────────────────────────────────

def test_list_connected_accounts_requires_auth(client: TestClient) -> None:
    response = client.get(ACCOUNTS_URL)
    assert response.status_code == 401


def test_create_connected_account_requires_auth(client: TestClient) -> None:
    response = client.post(ACCOUNTS_URL, json={"provider": "google", "provider_account_id": "x"})
    assert response.status_code == 401


# ── CRUD ───────────────────────────────────────────────────────────────────

def test_create_and_list_connected_accounts(client: TestClient) -> None:
    _login(client)
    created = _create_account(client)

    assert created["provider"] == "google"
    assert created["provider_account_id"] == "g-123"
    assert created["account_email"] == "parv@gmail.com"
    assert created["scopes"] == "email,calendar"
    # tokens must never leak in read responses
    assert "access_token_encrypted" not in created
    assert "refresh_token_encrypted" not in created

    # list
    list_resp = client.get(ACCOUNTS_URL)
    assert list_resp.status_code == 200
    accounts = list_resp.json()
    assert len(accounts) == 1
    assert accounts[0]["id"] == created["id"]


def test_get_connected_account_by_id(client: TestClient) -> None:
    _login(client)
    created = _create_account(client)

    resp = client.get(f"{ACCOUNTS_URL}/{created['id']}")
    assert resp.status_code == 200
    assert resp.json()["provider"] == "google"


def test_get_connected_account_not_found(client: TestClient) -> None:
    _login(client)

    resp = client.get(f"{ACCOUNTS_URL}/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404


def test_update_connected_account(client: TestClient) -> None:
    _login(client)
    created = _create_account(client)

    resp = client.patch(
        f"{ACCOUNTS_URL}/{created['id']}",
        json={"scopes": "email,calendar,drive", "account_email": "updated@gmail.com"},
    )
    assert resp.status_code == 200
    updated = resp.json()
    assert updated["scopes"] == "email,calendar,drive"
    assert updated["account_email"] == "updated@gmail.com"


def test_delete_connected_account(client: TestClient) -> None:
    _login(client)
    created = _create_account(client)

    del_resp = client.delete(f"{ACCOUNTS_URL}/{created['id']}")
    assert del_resp.status_code == 204

    # verify gone
    get_resp = client.get(f"{ACCOUNTS_URL}/{created['id']}")
    assert get_resp.status_code == 404

    list_resp = client.get(ACCOUNTS_URL)
    assert list_resp.json() == []


def test_duplicate_provider_account_returns_409(client: TestClient) -> None:
    _login(client)
    _create_account(client, provider="slack", provider_account_id="SLACK-001")

    dup_resp = client.post(
        ACCOUNTS_URL,
        json={"provider": "slack", "provider_account_id": "SLACK-001"},
    )
    assert dup_resp.status_code == 409
    assert "already connected" in dup_resp.json()["detail"].lower()


def test_multiple_providers_per_user(client: TestClient) -> None:
    _login(client)
    _create_account(client, provider="google", provider_account_id="g-1")
    _create_account(client, provider="slack", provider_account_id="s-1")
    _create_account(client, provider="spotify", provider_account_id="sp-1")

    list_resp = client.get(ACCOUNTS_URL)
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 3

    providers = {a["provider"] for a in list_resp.json()}
    assert providers == {"google", "slack", "spotify"}
