"""Tests for Spotify OAuth routes."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient


SPOTIFY_CONNECT_URL = "/api/v1/auth/spotify/connect"
SPOTIFY_CALLBACK_URL = "/api/v1/auth/spotify/callback"


def test_spotify_connect_requires_auth(client: TestClient) -> None:
    response = client.get(SPOTIFY_CONNECT_URL, follow_redirects=False)
    assert response.status_code == 401


def test_spotify_connect_redirects_when_authenticated(client: TestClient) -> None:
    client.post(
        "/api/v1/auth/dev-login",
        json={"email": "spotify-user@example.com", "full_name": "Spotify User"},
    )
    response = client.get(SPOTIFY_CONNECT_URL, follow_redirects=False)
    assert response.status_code == 302
    location = response.headers["location"]
    assert "accounts.spotify.com" in location
    assert "response_type=code" in location
    assert "state=" in location


def test_spotify_callback_with_invalid_state_returns_400(client: TestClient) -> None:
    response = client.get(
        SPOTIFY_CALLBACK_URL,
        params={"code": "fake-code", "state": "invalid-jwt-garbage"},
        follow_redirects=False,
    )
    assert response.status_code == 400
    assert "Invalid or expired" in response.json()["detail"]


@patch("app.services.spotify_oauth_service.SpotifyOAuthService.get_profile", new_callable=AsyncMock)
@patch("app.services.spotify_oauth_service.SpotifyOAuthService.exchange_code", new_callable=AsyncMock)
def test_spotify_callback_connect_stores_account(
    mock_exchange: AsyncMock,
    mock_profile: AsyncMock,
    client: TestClient,
) -> None:
    mock_exchange.return_value = {
        "access_token": "spotify-access-token",
        "refresh_token": "spotify-refresh-token",
        "expires_in": 3600,
        "scope": "user-read-playback-state user-modify-playback-state user-read-currently-playing",
    }
    mock_profile.return_value = {
        "id": "spotify-user-123",
        "email": "spotify-user@example.com",
        "display_name": "Spotify User",
        "country": "US",
        "product": "premium",
    }

    client.post(
        "/api/v1/auth/dev-login",
        json={"email": "spotify-user@example.com", "full_name": "Spotify User"},
    )

    connect_resp = client.get(SPOTIFY_CONNECT_URL, follow_redirects=False)
    location = connect_resp.headers["location"]

    import urllib.parse

    parsed = urllib.parse.urlparse(location)
    qs = urllib.parse.parse_qs(parsed.query)
    state = qs["state"][0]

    callback_resp = client.get(
        SPOTIFY_CALLBACK_URL,
        params={"code": "mock-auth-code", "state": state},
        follow_redirects=False,
    )

    assert callback_resp.status_code == 302
    assert "connected=spotify" in callback_resp.headers["location"]

    accounts_resp = client.get("/api/v1/connected-accounts")
    assert accounts_resp.status_code == 200
    accounts = accounts_resp.json()
    assert len(accounts) == 1
    assert accounts[0]["provider"] == "spotify"
    assert accounts[0]["account_email"] == "spotify-user@example.com"


@patch("app.services.spotify_oauth_service.SpotifyOAuthService.exchange_code", new_callable=AsyncMock)
def test_spotify_callback_failure_redirects_with_error_details(
    mock_exchange: AsyncMock,
    client: TestClient,
) -> None:
    mock_exchange.side_effect = RuntimeError("not on the Spotify app allowlist")

    client.post(
        "/api/v1/auth/dev-login",
        json={"email": "spotify-user@example.com", "full_name": "Spotify User"},
    )

    connect_resp = client.get(SPOTIFY_CONNECT_URL, follow_redirects=False)
    location = connect_resp.headers["location"]

    import urllib.parse

    parsed = urllib.parse.urlparse(location)
    qs = urllib.parse.parse_qs(parsed.query)
    state = qs["state"][0]

    callback_resp = client.get(
        SPOTIFY_CALLBACK_URL,
        params={"code": "mock-auth-code", "state": state},
        follow_redirects=False,
    )

    assert callback_resp.status_code == 302
    redirected = callback_resp.headers["location"]
    assert "error=spotify_oauth_failed" in redirected
    assert "provider=spotify" in redirected
    assert "not+on+the+Spotify+app+allowlist" in redirected


@patch("app.services.spotify_oauth_service.SpotifyOAuthService.get_profile", new_callable=AsyncMock)
@patch("app.services.spotify_oauth_service.SpotifyOAuthService.exchange_code", new_callable=AsyncMock)
def test_spotify_callback_profile_403_hint_is_exposed(
    mock_exchange: AsyncMock,
    mock_profile: AsyncMock,
    client: TestClient,
) -> None:
    mock_exchange.return_value = {"access_token": "token-123"}
    mock_profile.side_effect = ValueError(
        "Spotify profile fetch failed (403): Forbidden. If your Spotify app is in Development mode, add this Spotify account in Dashboard > Users and access, then accept the invite."
    )

    client.post(
        "/api/v1/auth/dev-login",
        json={"email": "spotify-user@example.com", "full_name": "Spotify User"},
    )

    connect_resp = client.get(SPOTIFY_CONNECT_URL, follow_redirects=False)
    location = connect_resp.headers["location"]

    import urllib.parse

    parsed = urllib.parse.urlparse(location)
    qs = urllib.parse.parse_qs(parsed.query)
    state = qs["state"][0]

    callback_resp = client.get(
        SPOTIFY_CALLBACK_URL,
        params={"code": "mock-auth-code", "state": state},
        follow_redirects=False,
    )

    assert callback_resp.status_code == 302
    redirected = callback_resp.headers["location"]
    assert "error=spotify_oauth_failed" in redirected
    assert "profile+fetch+failed+%28403%29" in redirected
    assert "Development+mode" in redirected
