from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ConnectedAccountCreate(BaseModel):
    provider: str = Field(..., min_length=1, max_length=50, examples=["google", "slack", "spotify"])
    provider_account_id: str = Field(..., min_length=1, max_length=255)
    account_email: str | None = None
    access_token_encrypted: str | None = None
    refresh_token_encrypted: str | None = None
    token_expires_at: datetime | None = None
    scopes: str | None = None
    account_metadata: dict | None = None


class ConnectedAccountUpdate(BaseModel):
    account_email: str | None = None
    access_token_encrypted: str | None = None
    refresh_token_encrypted: str | None = None
    token_expires_at: datetime | None = None
    scopes: str | None = None
    account_metadata: dict | None = None


class ConnectedAccountRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    provider: str
    provider_account_id: str
    account_email: str | None
    token_expires_at: datetime | None
    scopes: str | None
    account_metadata: dict | None
    created_at: datetime
    updated_at: datetime
    # NOTE: tokens are intentionally excluded from read responses
