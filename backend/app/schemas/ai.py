from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ReplySuggestionsRequest(BaseModel):
    email_id: UUID | None = None
    platform: str = "gmail"
    context: str
    tone: str | None = None


class ReplySuggestionsResponse(BaseModel):
    suggestions: list[str]


class PriorityScoreRequest(BaseModel):
    email_ids: list[UUID] = Field(default_factory=list)


class PriorityScoreResult(BaseModel):
    email_id: UUID
    score: float
    label: str


class PriorityScoreResponse(BaseModel):
    results: list[PriorityScoreResult]


class ActionItemRead(BaseModel):
    id: UUID
    user_id: UUID
    source_platform: str
    source_ref: str | None = None
    title: str
    details: str | None = None
    status: str
    priority: str
    score: int
    due_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class ActionItemListResponse(BaseModel):
    items: list[ActionItemRead]
    total: int


class ActionItemExtractRequest(BaseModel):
    source_platform: str = "gmail"
    source_ref: str | None = None
    text: str


class ActionItemExtractResponse(BaseModel):
    items: list[ActionItemRead]


class ActionItemUpdate(BaseModel):
    status: str | None = None
    priority: str | None = None
    due_at: datetime | None = None


class SemanticSearchRequest(BaseModel):
    query: str
    limit: int = Field(default=20, ge=1, le=100)


class SemanticSearchItem(BaseModel):
    email_id: UUID
    score: float
    subject: str | None = None
    from_address: str | None = None
    snippet: str | None = None
    category: str


class SemanticSearchResponse(BaseModel):
    results: list[SemanticSearchItem]
