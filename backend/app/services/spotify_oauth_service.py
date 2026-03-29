"""Spotify OAuth 2.0 connect service."""

from __future__ import annotations

import base64
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

import httpx
import jwt
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import ConnectedAccount, User
from app.schemas.connected_account import ConnectedAccountCreate, ConnectedAccountUpdate
from app.services.connected_account_service import ConnectedAccountService
from app.services.user_service import UserService


SPOTIFY_AUTH_URL = "https://accounts.spotify.com/authorize"
SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"
SPOTIFY_ME_URL = "https://api.spotify.com/v1/me"

SPOTIFY_CONNECT_SCOPES = (
    "user-read-email "
    "user-read-private "
    "user-read-playback-state "
    "user-read-currently-playing "
    "user-modify-playback-state "
    "playlist-read-private "
    "playlist-read-collaborative "
    "playlist-modify-private "
    "playlist-modify-public "
    "user-library-read "
    "user-library-modify"
)


def _build_state(intent: str, *, user_id: UUID | None = None) -> str:
    payload: dict[str, Any] = {
        "intent": intent,
        "nonce": secrets.token_urlsafe(16),
        "exp": datetime.now(timezone.utc) + timedelta(minutes=10),
    }
    if user_id is not None:
        payload["user_id"] = str(user_id)
    return jwt.encode(payload, settings.session_secret_key, algorithm="HS256")


def _decode_state(state: str) -> dict[str, Any]:
    return jwt.decode(state, settings.session_secret_key, algorithms=["HS256"])


class SpotifyOAuthService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.user_svc = UserService(db)
        self.account_svc = ConnectedAccountService(db)

    def get_authorization_url(self, *, user_id: UUID) -> str:
        state = _build_state("connect", user_id=user_id)
        params = {
            "client_id": settings.spotify_client_id,
            "response_type": "code",
            "redirect_uri": settings.spotify_redirect_uri,
            "scope": SPOTIFY_CONNECT_SCOPES,
            "state": state,
            "show_dialog": "true",
        }
        return f"{SPOTIFY_AUTH_URL}?{httpx.QueryParams(params)}"

    async def exchange_code(self, code: str) -> dict[str, Any]:
        auth_raw = f"{settings.spotify_client_id}:{settings.spotify_client_secret}"
        basic_token = base64.b64encode(auth_raw.encode("utf-8")).decode("utf-8")
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                SPOTIFY_TOKEN_URL,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": settings.spotify_redirect_uri,
                },
                headers={
                    "Authorization": f"Basic {basic_token}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
            )
            if resp.status_code >= 400:
                self._raise_spotify_http_error(resp, context="token exchange")
            return resp.json()

    async def get_profile(self, access_token: str) -> dict[str, Any]:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                SPOTIFY_ME_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if resp.status_code >= 400:
                self._raise_spotify_http_error(resp, context="profile fetch")
            return resp.json()

    async def handle_connect_callback(self, code: str, user_id: UUID) -> ConnectedAccount:
        tokens = await self.exchange_code(code)
        profile = await self.get_profile(tokens["access_token"])

        spotify_id = profile["id"]
        email = profile.get("email")

        user = self.user_svc.get_user(user_id)
        if user is None:
            raise ValueError("User not found")

        return self._upsert_connected_account(user, spotify_id, email, profile, tokens)

    def _upsert_connected_account(
        self,
        user: User,
        spotify_id: str,
        email: str | None,
        profile: dict[str, Any],
        tokens: dict[str, Any],
    ) -> ConnectedAccount:
        existing = self.account_svc.get_by_provider(
            user_id=user.id,
            provider="spotify",
            provider_account_id=spotify_id,
        )

        expires_at = None
        if "expires_in" in tokens:
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=tokens["expires_in"])

        scopes = tokens.get("scope", SPOTIFY_CONNECT_SCOPES)
        metadata = {
            "display_name": profile.get("display_name"),
            "country": profile.get("country"),
            "product": profile.get("product"),
        }

        if existing is not None:
            return self.account_svc.update(
                existing,
                ConnectedAccountUpdate(
                    account_email=email,
                    access_token_encrypted=tokens.get("access_token"),
                    refresh_token_encrypted=tokens.get("refresh_token"),
                    token_expires_at=expires_at,
                    scopes=scopes,
                    account_metadata=metadata,
                ),
            )

        return self.account_svc.create(
            user,
            ConnectedAccountCreate(
                provider="spotify",
                provider_account_id=spotify_id,
                account_email=email,
                access_token_encrypted=tokens.get("access_token"),
                refresh_token_encrypted=tokens.get("refresh_token"),
                token_expires_at=expires_at,
                scopes=scopes,
                account_metadata=metadata,
            ),
        )

    @staticmethod
    def decode_state(state: str) -> dict[str, Any]:
        return _decode_state(state)

    @staticmethod
    def _raise_spotify_http_error(response: httpx.Response, *, context: str) -> None:
        status = response.status_code
        message = "Spotify OAuth request failed."

        try:
            payload = response.json()
            err = payload.get("error", payload)
            if isinstance(err, dict):
                message = (
                    err.get("message")
                    or err.get("error_description")
                    or err.get("error")
                    or message
                )
            elif isinstance(err, str):
                message = err
        except Exception:
            if response.text:
                message = response.text

        # Most common issue when adding a second Spotify account in dev mode.
        if status == 403:
            message = (
                f"{message} "
                "If your Spotify app is in Development mode, add this Spotify account "
                "in Dashboard > Users and access, then accept the invite."
            )

        raise ValueError(
            f"Spotify {context} failed ({status}): {message}"
        )
