"""Token encryption helpers for connected account credentials."""

from __future__ import annotations

import base64
import hashlib
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings

_PREFIX = "enc::"


def _derive_key_from_session_secret() -> str:
    digest = hashlib.sha256(settings.session_secret_key.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).decode("utf-8")


@lru_cache(maxsize=1)
def _get_fernet() -> Fernet:
    raw_key = (settings.token_encryption_key or "").strip() or _derive_key_from_session_secret()
    return Fernet(raw_key.encode("utf-8"))


def encrypt_token(value: str | None) -> str | None:
    if value is None:
        return None
    if not value:
        return value
    if value.startswith(_PREFIX):
        return value
    token = _get_fernet().encrypt(value.encode("utf-8")).decode("utf-8")
    return f"{_PREFIX}{token}"


def decrypt_token(value: str | None) -> str | None:
    if value is None:
        return None
    if not value:
        return value
    if not value.startswith(_PREFIX):
        # Backward compatibility for legacy plain-text rows.
        return value
    cipher_text = value[len(_PREFIX) :]
    try:
        return _get_fernet().decrypt(cipher_text.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        # Keep raw value so callers fail naturally if this cannot be used.
        return value
