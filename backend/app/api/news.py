"""News feed API routes."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.db import get_db
from app.models import User
from app.schemas.news import (
    NewsArticle,
    NewsBookmarkListResponse,
    NewsBookmarkRead,
    NewsListResponse,
    NewsSourceCreate,
    NewsSourceListResponse,
    NewsSourceRead,
    NewsSourceUpdate,
)
from app.services.news_service import NewsService

router = APIRouter(prefix="/news", tags=["news"])


@router.post("/fetch")
async def fetch_news_now(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    svc = NewsService(db)
    created = await svc.fetch_for_user(user_id=current_user.id, limit_per_source=20)
    return {"status": "ok", "new_articles": created}


@router.get("/articles", response_model=NewsListResponse)
async def list_news_articles(
    topic: str = Query("all", description="all|tech|business|world|science"),
    limit: int = Query(24, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> NewsListResponse:
    svc = NewsService(db)
    topic_filter = topic.strip().lower() or "all"

    articles = svc.list_articles(user_id=current_user.id, topic=topic_filter, limit=limit)
    if not articles:
        await svc.fetch_for_user(user_id=current_user.id, limit_per_source=20)
        articles = svc.list_articles(user_id=current_user.id, topic=topic_filter, limit=limit)

    bookmarks = svc.list_bookmarks(user_id=current_user.id)
    bookmarked_ids = {str(article.id) for _, article in bookmarks}

    return NewsListResponse(
        articles=[
            NewsArticle(
                id=str(article.id),
                title=article.title,
                url=article.url,
                source=article.source_name,
                summary=article.summary,
                topic=article.topic,
                relevance_score=article.relevance_score,
                published_at=article.published_at,
                is_bookmarked=str(article.id) in bookmarked_ids,
            )
            for article in articles
        ]
    )


@router.get("/sources", response_model=NewsSourceListResponse)
def list_sources(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> NewsSourceListResponse:
    svc = NewsService(db)
    sources = svc.list_sources(user_id=current_user.id)
    return NewsSourceListResponse(
        sources=[
            NewsSourceRead(
                id=s.id,
                user_id=s.user_id,
                source_type=s.source_type,
                name=s.name,
                url=s.url,
                topic=s.topic,
                enabled=s.enabled,
                fetch_interval_minutes=s.fetch_interval_minutes,
                created_at=s.created_at,
                updated_at=s.updated_at,
            )
            for s in sources
        ]
    )


@router.post("/sources", response_model=NewsSourceRead)
def create_source(
    payload: NewsSourceCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> NewsSourceRead:
    svc = NewsService(db)
    source = svc.create_source(user_id=current_user.id, payload=payload.model_dump())
    return NewsSourceRead(
        id=source.id,
        user_id=source.user_id,
        source_type=source.source_type,
        name=source.name,
        url=source.url,
        topic=source.topic,
        enabled=source.enabled,
        fetch_interval_minutes=source.fetch_interval_minutes,
        created_at=source.created_at,
        updated_at=source.updated_at,
    )


@router.patch("/sources/{source_id}", response_model=NewsSourceRead)
def update_source(
    source_id: UUID,
    payload: NewsSourceUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> NewsSourceRead:
    svc = NewsService(db)
    source = svc.update_source(
        user_id=current_user.id,
        source_id=source_id,
        patch=payload.model_dump(exclude_unset=True),
    )
    if not source:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source not found")
    return NewsSourceRead(
        id=source.id,
        user_id=source.user_id,
        source_type=source.source_type,
        name=source.name,
        url=source.url,
        topic=source.topic,
        enabled=source.enabled,
        fetch_interval_minutes=source.fetch_interval_minutes,
        created_at=source.created_at,
        updated_at=source.updated_at,
    )


@router.delete("/sources/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_source(
    source_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    svc = NewsService(db)
    deleted = svc.delete_source(user_id=current_user.id, source_id=source_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source not found")


@router.get("/bookmarks", response_model=NewsBookmarkListResponse)
def list_bookmarks(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> NewsBookmarkListResponse:
    svc = NewsService(db)
    rows = svc.list_bookmarks(user_id=current_user.id)
    return NewsBookmarkListResponse(
        bookmarks=[
            NewsBookmarkRead(
                article_id=article.id,
                title=article.title,
                url=article.url,
                source=article.source_name,
                topic=article.topic,
                published_at=article.published_at,
                bookmarked_at=bookmark.created_at,
            )
            for bookmark, article in rows
        ]
    )


@router.post("/bookmarks/{article_id}")
def bookmark_article(
    article_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    svc = NewsService(db)
    ok = svc.bookmark(user_id=current_user.id, article_id=article_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Article not found")
    return {"status": "bookmarked"}


@router.delete("/bookmarks/{article_id}", status_code=status.HTTP_204_NO_CONTENT)
def unbookmark_article(
    article_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    svc = NewsService(db)
    svc.unbookmark(user_id=current_user.id, article_id=article_id)
