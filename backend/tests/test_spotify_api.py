"""Tests for Spotify player API routes."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch
import uuid

from fastapi.testclient import TestClient

from app.core.db import get_db
from app.main import app
from app.models import ConnectedAccount
from app.services.spotify_service import SpotifyAPIError


def _login(client: TestClient) -> dict:
    resp = client.post(
        "/api/v1/auth/dev-login",
        json={"email": "spotify-api@test.com", "full_name": "Spotify API User"},
    )
    assert resp.status_code == 200
    return resp.json()["user"]


def _create_spotify_account(
    client: TestClient,
    user_id: str,
    scopes: str,
    *,
    provider_account_id: str = "spotify-001",
    email: str = "spotify-api@test.com",
) -> str:
    db_gen = app.dependency_overrides[get_db]()
    db = next(db_gen)
    account = ConnectedAccount(
        id=uuid.uuid4(),
        user_id=uuid.UUID(user_id),
        provider="spotify",
        provider_account_id=provider_account_id,
        account_email=email,
        access_token_encrypted="spotify-access",
        refresh_token_encrypted="spotify-refresh",
        scopes=scopes,
    )
    db.add(account)
    db.commit()
    return str(account.id)


def test_spotify_player_requires_auth(client: TestClient) -> None:
    response = client.get("/api/v1/spotify/player")
    assert response.status_code == 401


def test_spotify_player_without_connected_account_returns_404(client: TestClient) -> None:
    _login(client)
    response = client.get("/api/v1/spotify/player")
    assert response.status_code == 404


@patch("app.api.spotify.SpotifyService.get_player_state", new_callable=AsyncMock)
def test_spotify_player_returns_state(mock_get_player_state: AsyncMock, client: TestClient) -> None:
    user = _login(client)
    _create_spotify_account(
        client,
        user["id"],
        "user-read-playback-state user-read-currently-playing user-modify-playback-state",
    )

    mock_get_player_state.return_value = {
        "is_playing": True,
        "progress_ms": 12345,
        "shuffle_state": False,
        "repeat_state": "off",
        "device": {
            "id": "device-1",
            "name": "MacBook Pro",
            "type": "Computer",
            "volume_percent": 65,
            "is_active": True,
            "is_restricted": False,
        },
        "item": {
            "id": "track-1",
            "name": "Test Song",
            "duration_ms": 300000,
            "artists": [{"name": "Test Artist"}],
            "album": {
                "name": "Test Album",
                "images": [{"url": "https://cdn.spotify.com/image.jpg"}],
            },
            "external_urls": {"spotify": "https://open.spotify.com/track/track-1"},
        },
    }

    response = client.get("/api/v1/spotify/player")
    assert response.status_code == 200
    data = response.json()
    assert data["has_active_device"] is True
    assert data["is_playing"] is True
    assert data["track"]["name"] == "Test Song"
    assert data["track"]["artists"][0]["name"] == "Test Artist"
    assert data["device"]["name"] == "MacBook Pro"


@patch("app.api.spotify.SpotifyService.play", new_callable=AsyncMock)
def test_spotify_play_endpoint_calls_service(mock_play: AsyncMock, client: TestClient) -> None:
    user = _login(client)
    _create_spotify_account(
        client,
        user["id"],
        "user-read-playback-state user-read-currently-playing user-modify-playback-state",
    )

    response = client.post("/api/v1/spotify/player/play")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert mock_play.await_count == 1


def test_spotify_modify_missing_scope_returns_400(client: TestClient) -> None:
    user = _login(client)
    _create_spotify_account(
        client,
        user["id"],
        "user-read-playback-state user-read-currently-playing",
    )

    response = client.post("/api/v1/spotify/player/play")
    assert response.status_code == 400
    assert "permissions missing" in response.json()["detail"].lower()


def test_spotify_volume_validation(client: TestClient) -> None:
    user = _login(client)
    _create_spotify_account(
        client,
        user["id"],
        "user-read-playback-state user-read-currently-playing user-modify-playback-state",
    )

    response = client.post("/api/v1/spotify/player/volume?percent=101")
    assert response.status_code == 422


@patch("app.api.spotify.SpotifyService.set_volume", new_callable=AsyncMock)
def test_spotify_volume_spotify_api_error_surfaces_status(
    mock_set_volume: AsyncMock,
    client: TestClient,
) -> None:
    user = _login(client)
    _create_spotify_account(
        client,
        user["id"],
        "user-read-playback-state user-read-currently-playing user-modify-playback-state",
    )
    mock_set_volume.side_effect = SpotifyAPIError(
        status_code=403,
        message="Premium required",
    )

    response = client.post("/api/v1/spotify/player/volume?percent=50")
    assert response.status_code == 403
    assert "Premium required" in response.json()["detail"]


def test_spotify_transfer_requires_auth(client: TestClient) -> None:
    response = client.post(
        "/api/v1/spotify/transfer",
        json={
            "source_account_id": str(uuid.uuid4()),
            "destination_account_id": str(uuid.uuid4()),
            "transfer_playlists": True,
            "transfer_liked_songs": True,
            "transfer_saved_albums": True,
        },
    )
    assert response.status_code == 401


def test_spotify_transfer_same_account_returns_400(client: TestClient) -> None:
    user = _login(client)
    account_id = _create_spotify_account(
        client,
        user["id"],
        (
            "playlist-read-private playlist-read-collaborative playlist-modify-private "
            "playlist-modify-public user-library-read user-library-modify"
        ),
    )
    response = client.post(
        "/api/v1/spotify/transfer",
        json={
            "source_account_id": account_id,
            "destination_account_id": account_id,
            "transfer_playlists": True,
            "transfer_liked_songs": True,
            "transfer_saved_albums": True,
        },
    )
    assert response.status_code == 400
    assert "must be different" in response.json()["detail"].lower()


def test_spotify_transfer_requires_scopes(client: TestClient) -> None:
    user = _login(client)
    source_id = _create_spotify_account(
        client,
        user["id"],
        "playlist-read-private",
        provider_account_id="spotify-source",
    )
    destination_id = _create_spotify_account(
        client,
        user["id"],
        "playlist-modify-private",
        provider_account_id="spotify-destination",
        email="spotify-api-destination@test.com",
    )
    response = client.post(
        "/api/v1/spotify/transfer",
        json={
            "source_account_id": source_id,
            "destination_account_id": destination_id,
            "transfer_playlists": True,
            "transfer_liked_songs": True,
            "transfer_saved_albums": False,
        },
    )
    assert response.status_code == 400
    assert "permissions missing" in response.json()["detail"].lower()


@patch("app.api.spotify.SpotifyTransferService.transfer", new_callable=AsyncMock)
def test_spotify_transfer_returns_summary(
    mock_transfer: AsyncMock,
    client: TestClient,
) -> None:
    user = _login(client)
    all_scopes = (
        "playlist-read-private playlist-read-collaborative "
        "playlist-modify-private playlist-modify-public "
        "user-library-read user-library-modify"
    )
    source_id = _create_spotify_account(
        client,
        user["id"],
        all_scopes,
        provider_account_id="spotify-source",
    )
    destination_id = _create_spotify_account(
        client,
        user["id"],
        all_scopes,
        provider_account_id="spotify-destination",
        email="spotify-api-destination@test.com",
    )

    mock_transfer.return_value = {
        "source_account_id": source_id,
        "destination_account_id": destination_id,
        "playlists_considered": 2,
        "playlists_copied": 2,
        "playlists_failed": 0,
        "playlist_tracks_transferred": 37,
        "liked_songs_transferred": 120,
        "saved_albums_transferred": 14,
        "warnings": [],
        "playlist_results": [],
    }

    response = client.post(
        "/api/v1/spotify/transfer",
        json={
            "source_account_id": source_id,
            "destination_account_id": destination_id,
            "transfer_playlists": True,
            "transfer_liked_songs": True,
            "transfer_saved_albums": True,
            "only_owned_playlists": True,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["playlists_copied"] == 2
    assert data["playlist_tracks_transferred"] == 37
    assert data["liked_songs_transferred"] == 120
    assert data["saved_albums_transferred"] == 14
    assert mock_transfer.await_count == 1
