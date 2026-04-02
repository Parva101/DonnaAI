"""Microsoft OAuth service used for Teams + Calendar Graph access."""

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
from app.schemas.connected_account import ConnectedAccountCreate, ConnectedAccountUpdate
from app.services.connected_account_service import ConnectedAccountService
from app.services.user_service import UserService

MICROSOFT_AUTH_URL = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize"
MICROSOFT_TOKEN_URL = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
MICROSOFT_ME_URL = "https://graph.microsoft.com/v1.0/me"

MICROSOFT_SCOPES = " ".join(
    [
        "openid",
        "profile",
        "email",
        "offline_access",
        "User.Read",
        "Chat.Read",
        "Chat.ReadWrite",
        "ChannelMessage.Read.All",
        "Presence.Read",
        "Calendars.Read",
    ]
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


class MicrosoftOAuthService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.user_svc = UserService(db)
        self.account_svc = ConnectedAccountService(db)

    def get_authorization_url(self, *, user_id: UUID) -> str:
        state = _build_state("connect", user_id=user_id)
        params = {
            "client_id": settings.microsoft_client_id,
            "response_type": "code",
            "redirect_uri": settings.microsoft_redirect_uri,
            "response_mode": "query",
            "scope": MICROSOFT_SCOPES,
            "state": state,
            "prompt": "consent",
        }
        auth_url = MICROSOFT_AUTH_URL.format(tenant=settings.microsoft_tenant_id)
        return f"{auth_url}?{httpx.QueryParams(params)}"

    async def exchange_code(self, code: str) -> dict[str, Any]:
        token_url = MICROSOFT_TOKEN_URL.format(tenant=settings.microsoft_tenant_id)
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                token_url,
                data={
                    "client_id": settings.microsoft_client_id,
                    "client_secret": settings.microsoft_client_secret,
                    "code": code,
                    "redirect_uri": settings.microsoft_redirect_uri,
                    "grant_type": "authorization_code",
                },
            )
            resp.raise_for_status()
            return resp.json()

    async def get_profile(self, access_token: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(
                MICROSOFT_ME_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            resp.raise_for_status()
            return resp.json()

    async def handle_connect_callback(self, code: str, user_id: UUID) -> ConnectedAccount:
        user = self.user_svc.get_user(user_id)
        if user is None:
            raise ValueError("User not found")

        tokens = await self.exchange_code(code)
        access_token = tokens.get("access_token")
        if not access_token:
            raise ValueError("Missing Microsoft access token")
        profile = await self.get_profile(access_token)

        account_object_id = str(profile.get("id") or "").strip()
        if not account_object_id:
            raise ValueError("Microsoft profile missing id")

        account_email = (
            str(profile.get("mail") or "").strip()
            or str(profile.get("userPrincipalName") or "").strip()
            or account_object_id
        )

        expires_at = None
        if "expires_in" in tokens:
            try:
                expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(tokens["expires_in"]))
            except Exception:
                expires_at = None

        existing = self.account_svc.get_by_provider(
            user_id=user.id,
            provider="teams",
            provider_account_id=account_object_id,
        )

        metadata = {
            "display_name": profile.get("displayName"),
            "user_principal_name": profile.get("userPrincipalName"),
            "tenant": settings.microsoft_tenant_id,
        }

        if existing is not None:
            return self.account_svc.update(
                existing,
                ConnectedAccountUpdate(
                    account_email=account_email,
                    access_token_encrypted=access_token,
                    refresh_token_encrypted=tokens.get("refresh_token"),
                    token_expires_at=expires_at,
                    scopes=tokens.get("scope", MICROSOFT_SCOPES),
                    account_metadata=metadata,
                ),
            )

        return self.account_svc.create(
            user,
            ConnectedAccountCreate(
                provider="teams",
                provider_account_id=account_object_id,
                account_email=account_email,
                access_token_encrypted=access_token,
                refresh_token_encrypted=tokens.get("refresh_token"),
                token_expires_at=expires_at,
                scopes=tokens.get("scope", MICROSOFT_SCOPES),
                account_metadata=metadata,
            ),
        )

    @staticmethod
    def decode_state(state: str) -> dict[str, Any]:
        return _decode_state(state)
