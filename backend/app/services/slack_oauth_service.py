"""Slack OAuth connect service."""

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

SLACK_AUTH_URL = "https://slack.com/oauth/v2/authorize"
SLACK_TOKEN_URL = "https://slack.com/api/oauth.v2.access"

SLACK_BOT_SCOPES = ",".join(
    [
        "channels:read",
        "channels:history",
        "groups:read",
        "groups:history",
        "im:read",
        "im:history",
        "mpim:read",
        "mpim:history",
        "chat:write",
        "users:read",
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


class SlackOAuthService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.user_svc = UserService(db)
        self.account_svc = ConnectedAccountService(db)

    def get_authorization_url(self, *, user_id: UUID) -> str:
        state = _build_state("connect", user_id=user_id)
        params = {
            "client_id": settings.slack_client_id,
            "scope": SLACK_BOT_SCOPES,
            "redirect_uri": settings.slack_redirect_uri,
            "state": state,
            "user_scope": "",
        }
        return f"{SLACK_AUTH_URL}?{httpx.QueryParams(params)}"

    async def exchange_code(self, code: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                SLACK_TOKEN_URL,
                data={
                    "client_id": settings.slack_client_id,
                    "client_secret": settings.slack_client_secret,
                    "code": code,
                    "redirect_uri": settings.slack_redirect_uri,
                },
            )
            resp.raise_for_status()
            payload = resp.json()
            if not payload.get("ok"):
                raise ValueError(payload.get("error") or "Slack OAuth failed")
            return payload

    async def handle_connect_callback(self, code: str, user_id: UUID) -> ConnectedAccount:
        tokens = await self.exchange_code(code)
        user = self.user_svc.get_user(user_id)
        if user is None:
            raise ValueError("User not found")
        return self._upsert_connected_account(user, tokens)

    def _upsert_connected_account(
        self,
        user: User,
        tokens: dict[str, Any],
    ) -> ConnectedAccount:
        team = tokens.get("team") or {}
        team_id = str(team.get("id") or "").strip()
        if not team_id:
            raise ValueError("Slack OAuth response missing team id")

        existing = self.account_svc.get_by_provider(
            user_id=user.id,
            provider="slack",
            provider_account_id=team_id,
        )

        authed_user = tokens.get("authed_user") or {}
        scopes = tokens.get("scope") or SLACK_BOT_SCOPES
        metadata = {
            "team_name": team.get("name"),
            "team_id": team_id,
            "app_id": tokens.get("app_id"),
            "bot_user_id": tokens.get("bot_user_id"),
            "authed_user_id": authed_user.get("id"),
        }

        account_email = (
            team.get("name")
            or authed_user.get("id")
            or team_id
        )

        if existing is not None:
            return self.account_svc.update(
                existing,
                ConnectedAccountUpdate(
                    account_email=account_email,
                    access_token_encrypted=tokens.get("access_token"),
                    refresh_token_encrypted=None,
                    token_expires_at=None,
                    scopes=scopes,
                    account_metadata=metadata,
                ),
            )

        return self.account_svc.create(
            user,
            ConnectedAccountCreate(
                provider="slack",
                provider_account_id=team_id,
                account_email=account_email,
                access_token_encrypted=tokens.get("access_token"),
                refresh_token_encrypted=None,
                token_expires_at=None,
                scopes=scopes,
                account_metadata=metadata,
            ),
        )

    @staticmethod
    def decode_state(state: str) -> dict[str, Any]:
        return _decode_state(state)
