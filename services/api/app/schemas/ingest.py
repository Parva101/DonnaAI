from datetime import datetime

from pydantic import BaseModel, Field


class IngestEventRequest(BaseModel):
    tenant_id: str = Field(min_length=1, max_length=64)
    platform: str = Field(min_length=1, max_length=32)
    account_id: str = Field(min_length=1, max_length=128)
    event_type: str = Field(min_length=1, max_length=64)
    source_event_id: str = Field(min_length=1, max_length=255)
    occurred_at: datetime
    payload: dict


class IngestEventResponse(BaseModel):
    event_id: str
    created: bool
    message_id: str | None = None

