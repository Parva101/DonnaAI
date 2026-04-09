from datetime import datetime

from pydantic import BaseModel, Field


class ActionPlanRequest(BaseModel):
    tenant_id: str = Field(min_length=1, max_length=64)
    intent: str = Field(min_length=1)
    source_platform: str | None = Field(default=None, max_length=32)
    source_chat_key: str | None = Field(default=None, max_length=255)
    target_platform: str | None = Field(default=None, max_length=32)
    target_chat_key: str | None = Field(default=None, max_length=255)


class ActionPlanResponse(BaseModel):
    action_id: str
    status: str
    requires_approval: bool
    draft_payload: dict


class ActionExecuteRequest(BaseModel):
    tenant_id: str = Field(min_length=1, max_length=64)
    action_id: str = Field(min_length=1, max_length=36)
    idempotency_key: str = Field(min_length=1, max_length=128)
    approval_token: str | None = None


class ActionExecuteResponse(BaseModel):
    action_id: str
    status: str
    executed_at: datetime | None = None
    message: str


class ActionLogResponse(BaseModel):
    id: str
    tenant_id: str
    action_type: str
    status: str
    source_platform: str | None
    source_chat_key: str | None
    target_platform: str | None
    target_chat_key: str | None
    payload_json: dict
    reason: str | None
    confidence: float | None
    requires_approval: bool
    idempotency_key: str
    trace_id: str | None
    error_text: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

