from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

import jwt
from jwt import InvalidTokenError

from app.core.config import settings


def create_session_token(user_id: UUID) -> str:
    expires_at = datetime.now(timezone.utc) + timedelta(
        minutes=settings.session_expire_minutes
    )
    payload = {
        "sub": str(user_id),
        "type": "session",
        "exp": expires_at,
    }
    return jwt.encode(payload, settings.session_secret_key, algorithm="HS256")


def decode_session_token(token: str) -> UUID:
    payload = jwt.decode(
        token,
        settings.session_secret_key,
        algorithms=["HS256"],
    )

    if payload.get("type") != "session":
        raise InvalidTokenError("Invalid token type.")

    return UUID(payload["sub"])
