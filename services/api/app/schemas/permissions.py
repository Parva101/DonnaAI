from datetime import datetime

from pydantic import BaseModel, Field


class PermissionScopeUpsertRequest(BaseModel):
    tenant_id: str = Field(min_length=1, max_length=64)
    platform: str = Field(min_length=1, max_length=32)
    account_id: str = Field(min_length=1, max_length=128)
    chat_key: str = Field(min_length=1, max_length=255)
    read_allowed: bool = False
    write_allowed: bool = False
    relay_allowed: bool = False
    updated_by: str | None = Field(default=None, max_length=128)


class PermissionScopeResponse(BaseModel):
    id: str
    tenant_id: str
    platform: str
    account_id: str
    chat_key: str
    read_allowed: bool
    write_allowed: bool
    relay_allowed: bool
    updated_by: str | None
    updated_at: datetime

    model_config = {"from_attributes": True}

