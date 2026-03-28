"""Tests for Google OAuth routes.

These test the route-level behavior (redirects, state validation, error handling)
with Google API calls mocked out.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient


GOOGLE_LOGIN_URL = "/api/v1/auth/google/login"
GOOGLE_CONNECT_URL = "/api/v1/auth/google/connect"
GOOGLE_CALLBACK_URL = "/api/v1/auth/google/callback"


# ── Login redirect ──────────────────────────────────────────────

def test_google_login_redirects_to_google(client: TestClient) -> None:
    response = client.get(GOOGLE_LOGIN_URL, follow_redirects=False)
    assert response.status_code == 302
    location = response.headers["location"]
    assert "accounts.google.com" in location
    assert "response_type=code" in location
    assert "state=" in location


# ── Connect requires auth ──────────────────────────────────────

def test_google_connect_requires_auth(client: TestClient) -> None:
    response = client.get(GOOGLE_CONNECT_URL, follow_redirects=False)
    assert response.status_code == 401


def test_google_connect_redirects_when_authenticated(client: TestClient) -> None:
    # Login first
    client.post(
        "/api/v1/auth/dev-login",
        json={"email": "parv@example.com", "full_name": "Parv"},
    )
    response = client.get(GOOGLE_CONNECT_URL, follow_redirects=False)
    assert response.status_code == 302
    location = response.headers["location"]
    assert "accounts.google.com" in location
    assert "gmail" in location.lower()  # Gmail scope is included for connect


# ── Callback: invalid state ────────────────────────────────────

def test_callback_with_invalid_state_returns_400(client: TestClient) -> None:
    response = client.get(
        GOOGLE_CALLBACK_URL,
        params={"code": "fake-code", "state": "invalid-jwt-garbage"},
        follow_redirects=False,
    )
    assert response.status_code == 400
    assert "Invalid or expired" in response.json()["detail"]


# ── Callback: successful login flow (mocked Google) ────────────

@patch("app.services.oauth_service.GoogleOAuthService.get_user_info", new_callable=AsyncMock)
@patch("app.services.oauth_service.GoogleOAuthService.exchange_code", new_callable=AsyncMock)
def test_callback_login_creates_user_and_sets_cookie(
    mock_exchange: AsyncMock,
    mock_userinfo: AsyncMock,
    client: TestClient,
) -> None:
    mock_exchange.return_value = {
        "access_token": "mock-access-token",
        "refresh_token": "mock-refresh-token",
        "expires_in": 3600,
        "scope": "openid email profile",
    }
    mock_userinfo.return_value = {
        "id": "google-123456",
        "email": "parv@gmail.com",
        "name": "Parv",
        "picture": "https://lh3.googleusercontent.com/photo.jpg",
    }

    # First, get the login redirect to extract a valid state token
    login_resp = client.get(GOOGLE_LOGIN_URL, follow_redirects=False)
    location = login_resp.headers["location"]
    # Parse state from redirect URL
    import urllib.parse

    parsed = urllib.parse.urlparse(location)
    qs = urllib.parse.parse_qs(parsed.query)
    state = qs["state"][0]

    # Now hit the callback with the valid state
    callback_resp = client.get(
        GOOGLE_CALLBACK_URL,
        params={"code": "mock-auth-code", "state": state},
        follow_redirects=False,
    )

    assert callback_resp.status_code == 302
    assert "/dashboard" in callback_resp.headers["location"]
    assert "donna_session=" in callback_resp.headers.get("set-cookie", "")

    # Verify user was created
    me_resp = client.get("/api/v1/users/me")
    assert me_resp.status_code == 200
    assert me_resp.json()["email"] == "parv@gmail.com"


# ── Callback: successful connect flow (mocked Google) ──────────

@patch("app.services.oauth_service.GoogleOAuthService.get_user_info", new_callable=AsyncMock)
@patch("app.services.oauth_service.GoogleOAuthService.exchange_code", new_callable=AsyncMock)
def test_callback_connect_stores_account(
    mock_exchange: AsyncMock,
    mock_userinfo: AsyncMock,
    client: TestClient,
) -> None:
    mock_exchange.return_value = {
        "access_token": "mock-access-token",
        "refresh_token": "mock-refresh-token",
        "expires_in": 3600,
        "scope": "openid email profile https://www.googleapis.com/auth/gmail.modify",
    }
    mock_userinfo.return_value = {
        "id": "google-789",
        "email": "parv@gmail.com",
        "name": "Parv",
    }

    # Login via dev-login first
    client.post(
        "/api/v1/auth/dev-login",
        json={"email": "parv@example.com", "full_name": "Parv"},
    )

    # Get the connect redirect for valid state
    connect_resp = client.get(GOOGLE_CONNECT_URL, follow_redirects=False)
    location = connect_resp.headers["location"]
    import urllib.parse

    parsed = urllib.parse.urlparse(location)
    qs = urllib.parse.parse_qs(parsed.query)
    state = qs["state"][0]

    # Hit callback
    callback_resp = client.get(
        GOOGLE_CALLBACK_URL,
        params={"code": "mock-auth-code", "state": state},
        follow_redirects=False,
    )

    assert callback_resp.status_code == 302
    assert "connected=google" in callback_resp.headers["location"]

    # Verify connected account was stored
    accounts_resp = client.get("/api/v1/connected-accounts")
    assert accounts_resp.status_code == 200
    accounts = accounts_resp.json()
    assert len(accounts) == 1
    assert accounts[0]["provider"] == "google"
    assert accounts[0]["account_email"] == "parv@gmail.com"
