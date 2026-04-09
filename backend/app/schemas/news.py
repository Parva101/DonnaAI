from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class NewsArticle(BaseModel):
    id: str
    title: str
    url: str
    source: str
    summary: str | None = None
    topic: str
    relevance_score: float = 0.5
    published_at: datetime | None = None
    is_bookmarked: bool = False


class NewsListResponse(BaseModel):
    articles: list[NewsArticle]


class NewsSourceCreate(BaseModel):
    source_type: str = Field(default="rss", description="rss|newsapi|hackernews")
    name: str
    url: str | None = None
    topic: str = "all"
    enabled: bool = True
    fetch_interval_minutes: int = Field(default=30, ge=5, le=360)


class NewsSourceUpdate(BaseModel):
    name: str | None = None
    url: str | None = None
    topic: str | None = None
    enabled: bool | None = None
    fetch_interval_minutes: int | None = Field(default=None, ge=5, le=360)


class NewsSourceRead(BaseModel):
    id: UUID
    user_id: UUID
    source_type: str
    name: str
    url: str | None = None
    topic: str
    enabled: bool
    fetch_interval_minutes: int
    created_at: datetime
    updated_at: datetime


class NewsSourceListResponse(BaseModel):
    sources: list[NewsSourceRead]


class NewsBookmarkRead(BaseModel):
    article_id: UUID
    title: str
    url: str
    source: str
    topic: str
    published_at: datetime | None = None
    bookmarked_at: datetime


class NewsBookmarkListResponse(BaseModel):
    bookmarks: list[NewsBookmarkRead]
