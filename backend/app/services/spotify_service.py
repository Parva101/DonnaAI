"""Spotify Web API client bound to a connected account."""

from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.token_crypto import decrypt_token, encrypt_token
from app.models import ConnectedAccount


SPOTIFY_API_BASE = "https://api.spotify.com/v1"
SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"
SPOTIFY_LIBRARY_MAX_URIS = 40


class SpotifyAPIError(Exception):
    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


class SpotifyService:
    def __init__(self, db: Session, account: ConnectedAccount) -> None:
        self.db = db
        self.account = account

    async def get_player_state(self) -> dict[str, Any] | None:
        return await self._request_json(
            "GET",
            "/me/player",
            accepted_statuses={200, 204},
        )

    async def get_profile(self) -> dict[str, Any]:
        payload = await self._request_json("GET", "/me")
        return payload or {}

    async def list_playlists_page(self, *, limit: int = 50, offset: int = 0) -> dict[str, Any]:
        payload = await self._request_json(
            "GET",
            "/me/playlists",
            params={"limit": limit, "offset": offset},
        )
        return payload or {}

    async def list_playlist_tracks_page(
        self,
        playlist_id: str,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        try:
            payload = await self._request_json(
                "GET",
                f"/playlists/{playlist_id}/items",
                params={"limit": limit, "offset": offset},
            )
            return payload or {}
        except SpotifyAPIError as exc:
            # Backward-compatible fallback for clients that still use /tracks.
            if exc.status_code not in {404, 405}:
                raise
            payload = await self._request_json(
                "GET",
                f"/playlists/{playlist_id}/tracks",
                params={"limit": limit, "offset": offset},
            )
            return payload or {}

    async def create_playlist(
        self,
        *,
        name: str,
        description: str | None = None,
        public: bool = False,
        collaborative: bool = False,
    ) -> dict[str, Any]:
        payload = await self._request_json(
            "POST",
            "/me/playlists",
            json_body={
                "name": name,
                "description": description or "",
                "public": public,
                "collaborative": collaborative,
            },
            accepted_statuses={200, 201},
        )
        return payload or {}

    async def add_playlist_items(self, *, playlist_id: str, uris: list[str]) -> None:
        if not uris:
            return
        try:
            await self._request_no_content(
                "POST",
                f"/playlists/{playlist_id}/items",
                json_body={"uris": uris},
            )
        except SpotifyAPIError as exc:
            # Backward-compatible fallback for clients that still use /tracks.
            if exc.status_code not in {404, 405}:
                raise
            await self._request_no_content(
                "POST",
                f"/playlists/{playlist_id}/tracks",
                json_body={"uris": uris},
            )

    async def list_saved_tracks_page(self, *, limit: int = 50, offset: int = 0) -> dict[str, Any]:
        payload = await self._request_json(
            "GET",
            "/me/tracks",
            params={"limit": limit, "offset": offset},
        )
        return payload or {}

    async def save_tracks(self, *, track_ids: list[str]) -> None:
        if not track_ids:
            return
        uris = [f"spotify:track:{track_id}" for track_id in track_ids]
        await self._request_no_content(
            "PUT",
            "/me/library",
            params={"uris": ",".join(uris)},
        )

    async def list_saved_albums_page(self, *, limit: int = 50, offset: int = 0) -> dict[str, Any]:
        payload = await self._request_json(
            "GET",
            "/me/albums",
            params={"limit": limit, "offset": offset},
        )
        return payload or {}

    async def save_albums(self, *, album_ids: list[str]) -> None:
        if not album_ids:
            return
        uris = [f"spotify:album:{album_id}" for album_id in album_ids]
        await self._request_no_content(
            "PUT",
            "/me/library",
            params={"uris": ",".join(uris)},
        )

    async def play(self) -> None:
        await self._request_no_content("PUT", "/me/player/play")

    async def pause(self) -> None:
        await self._request_no_content("PUT", "/me/player/pause")

    async def next_track(self) -> None:
        await self._request_no_content("POST", "/me/player/next")

    async def previous_track(self) -> None:
        await self._request_no_content("POST", "/me/player/previous")

    async def set_volume(self, percent: int) -> None:
        await self._request_no_content(
            "PUT",
            "/me/player/volume",
            params={"volume_percent": percent},
        )

    async def _request_json(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        accepted_statuses: set[int] | None = None,
    ) -> dict[str, Any] | None:
        accepted = accepted_statuses or {200}
        response = await self._request(
            method,
            path,
            params=params,
            json_body=json_body,
        )
        if response.status_code not in accepted:
            self._raise_spotify_error(response)
        if response.status_code == 204:
            return None
        return response.json()

    async def _request_no_content(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> None:
        response = await self._request(
            method,
            path,
            params=params,
            json_body=json_body,
        )
        if response.status_code not in {200, 201, 202, 204}:
            self._raise_spotify_error(response)

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> httpx.Response:
        access_token = await self._ensure_access_token()
        headers = {"Authorization": f"Bearer {access_token}"}

        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.request(
                method,
                f"{SPOTIFY_API_BASE}{path}",
                params=params,
                json=json_body,
                headers=headers,
            )
            if response.status_code != 401:
                return response

            # Token likely expired; refresh once and retry.
            access_token = await self._refresh_access_token()
            headers["Authorization"] = f"Bearer {access_token}"
            return await client.request(
                method,
                f"{SPOTIFY_API_BASE}{path}",
                params=params,
                json=json_body,
                headers=headers,
            )

    def _raise_spotify_error(self, response: httpx.Response) -> None:
        status_code = response.status_code
        message = "Spotify request failed."
        endpoint = response.request.url.path if response.request else ""

        try:
            payload = response.json()
            error_obj = payload.get("error", payload)
            if isinstance(error_obj, dict):
                message = (
                    error_obj.get("message")
                    or error_obj.get("error_description")
                    or message
                )
            elif isinstance(error_obj, str):
                message = error_obj
        except Exception:
            if response.text:
                message = response.text

        if status_code == 403:
            lower_message = message.lower()
            if endpoint.startswith("/v1/me/player"):
                message = (
                    f"{message} "
                    "Playback control may require Spotify Premium or a controllable active device."
                )
            elif "insufficient client scope" in lower_message:
                message = (
                    f"{message} "
                    "Reconnect Spotify and accept all requested permissions."
                )
            elif endpoint == "/v1/me":
                message = (
                    f"{message} "
                    "If your Spotify app is in Development mode, ensure this account is "
                    "added in Dashboard > Users and access."
                )
            elif endpoint in {"/v1/me/tracks", "/v1/me/albums"}:
                message = (
                    f"{message} "
                    "This library endpoint may be restricted for your Spotify app mode."
                )

        if endpoint:
            message = f"{message} (endpoint: {endpoint})"

        raise SpotifyAPIError(status_code=status_code, message=message)

    async def _ensure_access_token(self) -> str:
        access_token = decrypt_token(self.account.access_token_encrypted)
        if not access_token:
            return await self._refresh_access_token()

        expires_at = self.account.token_expires_at
        if expires_at is None:
            return access_token

        now = datetime.now(timezone.utc)
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)

        # Refresh one minute early to avoid race with near-expiry tokens.
        if expires_at <= now + timedelta(seconds=60):
            return await self._refresh_access_token()

        return access_token

    async def _refresh_access_token(self) -> str:
        refresh_token = decrypt_token(self.account.refresh_token_encrypted)
        if not refresh_token:
            raise ValueError("Spotify refresh token missing. Reconnect Spotify.")

        auth_raw = f"{settings.spotify_client_id}:{settings.spotify_client_secret}"
        basic_token = base64.b64encode(auth_raw.encode("utf-8")).decode("utf-8")

        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                SPOTIFY_TOKEN_URL,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                },
                headers={
                    "Authorization": f"Basic {basic_token}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
            )
            response.raise_for_status()
            data = response.json()

        self.account.access_token_encrypted = encrypt_token(data["access_token"])
        if data.get("refresh_token"):
            self.account.refresh_token_encrypted = encrypt_token(data["refresh_token"])
        if "expires_in" in data:
            self.account.token_expires_at = datetime.now(timezone.utc) + timedelta(
                seconds=int(data["expires_in"])
            )
        if data.get("scope"):
            self.account.scopes = data["scope"]

        self.db.add(self.account)
        self.db.commit()
        self.db.refresh(self.account)

        return decrypt_token(self.account.access_token_encrypted) or ""
