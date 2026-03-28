"""Google OAuth 2.0 service.

Handles the full OAuth flow:
  1. Build authorization URL (login or connect intent)
  2. Exchange authorization code for tokens
  3. Fetch user profile from Google
  4. Create/update User + ConnectedAccount
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

import httpx
import jwt
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import ConnectedAccount, User
from app.services.connected_account_service import ConnectedAccountService
from app.services.user_service import UserService

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"

# Scopes per intent
LOGIN_SCOPES = "openid email profile"
CONNECT_SCOPES = (
    "openid email profile "
    "https://www.googleapis.com/auth/gmail.modify "
    "https://www.googleapis.com/auth/calendar"
)


def _build_state(intent: str, *, user_id: UUID | None = None) -> str:
    """Encode intent + nonce into a short-lived JWT state token."""
    payload: dict[str, Any] = {
        "intent": intent,
        "nonce": secrets.token_urlsafe(16),
        "exp": datetime.now(timezone.utc) + timedelta(minutes=10),
    }
    if user_id is not None:
        payload["user_id"] = str(user_id)
    return jwt.encode(payload, settings.session_secret_key, algorithm="HS256")


def _decode_state(state: str) -> dict[str, Any]:
    """Verify and decode the state JWT."""
    return jwt.decode(state, settings.session_secret_key, algorithms=["HS256"])


class GoogleOAuthService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.user_svc = UserService(db)
        self.account_svc = ConnectedAccountService(db)

    # ── Step 1: Authorization URL ──────────────────────────────

    def get_authorization_url(self, *, intent: str = "login", user_id: UUID | None = None) -> str:
        """Return the Google consent screen URL the frontend should redirect to."""
        scopes = CONNECT_SCOPES if intent == "connect" else LOGIN_SCOPES
        state = _build_state(intent, user_id=user_id)

        params = {
            "client_id": settings.google_client_id,
            "redirect_uri": settings.google_redirect_uri,
            "response_type": "code",
            "scope": scopes,
            "access_type": "offline",
            "prompt": "consent",
            "state": state,
        }
        return f"{GOOGLE_AUTH_URL}?{httpx.QueryParams(params)}"

    # ── Step 2: Exchange code → tokens ─────────────────────────

    async def exchange_code(self, code: str) -> dict[str, Any]:
        """Exchange the authorization code for access + refresh tokens."""
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "client_id": settings.google_client_id,
                    "client_secret": settings.google_client_secret,
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": settings.google_redirect_uri,
                },
            )
            resp.raise_for_status()
            return resp.json()

    # ── Step 3: Fetch user info ────────────────────────────────

    async def get_user_info(self, access_token: str) -> dict[str, Any]:
        """Fetch the Google user profile."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                GOOGLE_USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            resp.raise_for_status()
            return resp.json()

    # ── Step 4a: Handle login callback ─────────────────────────

    async def handle_login_callback(self, code: str) -> User:
        """Exchange code, get profile, find-or-create user, upsert connected account."""
        tokens = await self.exchange_code(code)
        profile = await self.get_user_info(tokens["access_token"])

        google_id: str = profile["id"]
        email: str = profile["email"]
        full_name: str | None = profile.get("name")

        # Find or create user
        user = self.user_svc.get_user_by_email(email)
        if user is None:
            from app.schemas.user import UserCreate

            user = self.user_svc.create_user(
                UserCreate(email=email, full_name=full_name, is_active=True)
            )

        # Upsert connected account
        self._upsert_connected_account(user, google_id, email, tokens)
        return user

    # ── Step 4b: Handle connect callback ───────────────────────

    async def handle_connect_callback(self, code: str, user_id: UUID) -> ConnectedAccount:
        """Exchange code, store tokens against existing user."""
        tokens = await self.exchange_code(code)
        profile = await self.get_user_info(tokens["access_token"])

        google_id: str = profile["id"]
        email: str = profile["email"]
        user = self.user_svc.get_user(user_id)
        if user is None:
            raise ValueError("User not found")

        return self._upsert_connected_account(user, google_id, email, tokens)

    # ── Helpers ─────────────────────────────────────────────────

    def _upsert_connected_account(
        self,
        user: User,
        google_id: str,
        email: str,
        tokens: dict[str, Any],
    ) -> ConnectedAccount:
        existing = self.account_svc.get_by_provider(
            user_id=user.id, provider="google", provider_account_id=google_id
        )

        expires_at = None
        if "expires_in" in tokens:
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=tokens["expires_in"])

        scopes = tokens.get("scope", "")

        if existing is not None:
            from app.schemas.connected_account import ConnectedAccountUpdate

            return self.account_svc.update(
                existing,
                ConnectedAccountUpdate(
                    account_email=email,
                    access_token_encrypted=tokens.get("access_token"),
                    refresh_token_encrypted=tokens.get("refresh_token"),
                    token_expires_at=expires_at,
                    scopes=scopes,
                ),
            )

        from app.schemas.connected_account import ConnectedAccountCreate

        return self.account_svc.create(
            user,
            ConnectedAccountCreate(
                provider="google",
                provider_account_id=google_id,
                account_email=email,
                access_token_encrypted=tokens.get("access_token"),
                refresh_token_encrypted=tokens.get("refresh_token"),
                token_expires_at=expires_at,
                scopes=scopes,
                account_metadata={"picture": tokens.get("picture")},
            ),
        )

    @staticmethod
    def decode_state(state: str) -> dict[str, Any]:
        return _decode_state(state)
