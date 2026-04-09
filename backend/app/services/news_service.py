"""News ingestion and curation service (RSS + NewsAPI + Hacker News)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Iterable
from uuid import UUID

import feedparser
import httpx
from pydantic import BaseModel, Field
from sqlalchemy import and_, delete, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import NewsArticle, NewsBookmark, NewsSource

HN_TOP_URL = "https://hacker-news.firebaseio.com/v0/topstories.json"
HN_ITEM_URL = "https://hacker-news.firebaseio.com/v0/item/{item_id}.json"
NEWSAPI_URL = "https://newsapi.org/v2/top-headlines"


class _ArticleAIResult(BaseModel):
    idx: int = Field(ge=0)
    summary: str
    topic: str
    relevance_score: float = Field(ge=0, le=1)


class _ArticleAIBatch(BaseModel):
    results: list[_ArticleAIResult]


class NewsService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_sources(self, *, user_id: UUID) -> list[NewsSource]:
        self._ensure_default_sources(user_id=user_id)
        stmt = select(NewsSource).where(NewsSource.user_id == user_id).order_by(NewsSource.created_at.desc())
        return list(self.db.execute(stmt).scalars())

    def _ensure_default_sources(self, *, user_id: UUID) -> None:
        existing = list(
            self.db.execute(select(NewsSource).where(NewsSource.user_id == user_id)).scalars()
        )
        if existing:
            return

        defaults = [
            NewsSource(
                user_id=user_id,
                source_type="hackernews",
                name="Hacker News",
                url="https://news.ycombinator.com/",
                topic="tech",
                enabled=True,
                fetch_interval_minutes=settings.news_fetch_interval_minutes,
            ),
            NewsSource(
                user_id=user_id,
                source_type="newsapi",
                name="NewsAPI Top Headlines",
                url="https://newsapi.org/",
                topic="all",
                enabled=True,
                fetch_interval_minutes=settings.news_fetch_interval_minutes,
            ),
            NewsSource(
                user_id=user_id,
                source_type="rss",
                name="TechCrunch RSS",
                url="https://techcrunch.com/feed/",
                topic="tech",
                enabled=True,
                fetch_interval_minutes=settings.news_fetch_interval_minutes,
            ),
        ]
        self.db.add_all(defaults)
        self.db.commit()

    def create_source(self, *, user_id: UUID, payload: dict) -> NewsSource:
        source = NewsSource(
            user_id=user_id,
            source_type=payload.get("source_type", "rss"),
            name=payload["name"],
            url=payload.get("url"),
            topic=payload.get("topic", "all"),
            enabled=bool(payload.get("enabled", True)),
            fetch_interval_minutes=int(payload.get("fetch_interval_minutes", settings.news_fetch_interval_minutes)),
        )
        self.db.add(source)
        self.db.commit()
        self.db.refresh(source)
        return source

    def update_source(self, *, user_id: UUID, source_id: UUID, patch: dict) -> NewsSource | None:
        source = self.db.get(NewsSource, source_id)
        if not source or source.user_id != user_id:
            return None
        for key, value in patch.items():
            if value is None:
                continue
            setattr(source, key, value)
        self.db.add(source)
        self.db.commit()
        self.db.refresh(source)
        return source

    def delete_source(self, *, user_id: UUID, source_id: UUID) -> bool:
        source = self.db.get(NewsSource, source_id)
        if not source or source.user_id != user_id:
            return False
        self.db.delete(source)
        self.db.commit()
        return True

    async def fetch_for_user(self, *, user_id: UUID, limit_per_source: int = 20) -> int:
        sources = self.list_sources(user_id=user_id)
        enabled = [s for s in sources if s.enabled]
        created = 0
        for source in enabled:
            if source.source_type == "rss":
                articles = await self._fetch_rss(source=source, limit=limit_per_source)
            elif source.source_type == "newsapi":
                articles = await self._fetch_newsapi(source=source, limit=limit_per_source)
            elif source.source_type == "hackernews":
                articles = await self._fetch_hn(source=source, limit=limit_per_source)
            else:
                articles = []

            articles = await self._apply_ai_enrichment(source=source, rows=articles)
            created += self._upsert_articles(user_id=user_id, source=source, rows=articles)

        self.db.commit()
        return created

    async def _fetch_rss(self, *, source: NewsSource, limit: int) -> list[dict]:
        if not source.url:
            return []
        parsed = feedparser.parse(source.url)
        rows: list[dict] = []
        for entry in (parsed.entries or [])[:limit]:
            title = str(entry.get("title") or "").strip()
            url = str(entry.get("link") or "").strip()
            if not title or not url:
                continue
            summary = str(entry.get("summary") or "").strip()
            published_raw = entry.get("published") or entry.get("updated")
            published_at = self._parse_datetime(published_raw)
            rows.append(
                {
                    "external_id": str(entry.get("id") or url),
                    "title": title,
                    "url": url,
                    "source_name": source.name,
                    "summary": self._one_line_summary(title, summary),
                    "topic": self._normalize_topic(source.topic, title),
                    "relevance_score": self._score_relevance(title, summary),
                    "published_at": published_at,
                }
            )
        return rows

    async def _fetch_hn(self, *, source: NewsSource, limit: int) -> list[dict]:
        rows: list[dict] = []
        async with httpx.AsyncClient(timeout=20) as client:
            ids_resp = await client.get(HN_TOP_URL)
            ids_resp.raise_for_status()
            ids = (ids_resp.json() or [])[: max(limit * 3, limit)]

            for item_id in ids:
                item_resp = await client.get(HN_ITEM_URL.format(item_id=item_id))
                if item_resp.status_code >= 400:
                    continue
                item = item_resp.json() or {}
                title = str(item.get("title") or "").strip()
                url = str(item.get("url") or "").strip()
                if not title or not url:
                    continue
                topic = self._normalize_topic(source.topic, title)
                if source.topic != "all" and topic != source.topic:
                    continue

                published_at = None
                if item.get("time"):
                    try:
                        published_at = datetime.fromtimestamp(item["time"], tz=timezone.utc)
                    except Exception:
                        published_at = None

                rows.append(
                    {
                        "external_id": f"hn-{item_id}",
                        "title": title,
                        "url": url,
                        "source_name": source.name,
                        "summary": self._one_line_summary(title, ""),
                        "topic": topic,
                        "relevance_score": self._score_relevance(title, ""),
                        "published_at": published_at,
                    }
                )
                if len(rows) >= limit:
                    break
        return rows

    async def _fetch_newsapi(self, *, source: NewsSource, limit: int) -> list[dict]:
        if not settings.news_api_key:
            return []

        category_map = {
            "all": None,
            "tech": "technology",
            "business": "business",
            "science": "science",
            "world": "general",
        }
        params: dict[str, str | int] = {"language": "en", "pageSize": limit}
        category = category_map.get(source.topic, None)
        if category:
            params["category"] = category

        headers = {"X-Api-Key": settings.news_api_key}
        rows: list[dict] = []

        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(NEWSAPI_URL, params=params, headers=headers)
            if resp.status_code >= 400:
                return []
            data = resp.json() or {}

        for i, item in enumerate(data.get("articles") or [], 1):
            title = str(item.get("title") or "").strip()
            url = str(item.get("url") or "").strip()
            if not title or not url:
                continue
            description = str(item.get("description") or "").strip()
            source_name = str((item.get("source") or {}).get("name") or source.name).strip()
            rows.append(
                {
                    "external_id": f"newsapi-{i}-{hash(url)}",
                    "title": title,
                    "url": url,
                    "source_name": source_name,
                    "summary": self._one_line_summary(title, description),
                    "topic": self._normalize_topic(source.topic, title),
                    "relevance_score": self._score_relevance(title, description),
                    "published_at": self._parse_datetime(item.get("publishedAt")),
                }
            )
        return rows

    async def _apply_ai_enrichment(self, *, source: NewsSource, rows: list[dict]) -> list[dict]:
        """Apply AI summary/topic/relevance when Gemini credentials are configured.

        Falls back to heuristic values already present in each row when AI is unavailable.
        """
        if not rows or not settings.google_api_key:
            return rows

        try:
            from google import genai
            from google.genai import types as genai_types

            payload_rows = []
            for idx, row in enumerate(rows):
                payload_rows.append(
                    {
                        "idx": idx,
                        "title": str(row.get("title") or "")[:240],
                        "description": str(row.get("summary") or "")[:480],
                    }
                )

            client = genai.Client(vertexai=True, api_key=settings.google_api_key)
            response = await client.aio.models.generate_content(
                model="gemini-2.5-flash-lite",
                contents=json.dumps(
                    {
                        "source_topic": source.topic or "all",
                        "allowed_topics": ["all", "tech", "business", "world", "science"],
                        "articles": payload_rows,
                    },
                    separators=(",", ":"),
                ),
                config=genai_types.GenerateContentConfig(
                    system_instruction=(
                        "You are a news curation assistant. "
                        "Return one-line summaries, topic classification, and relevance scores."
                    ),
                    response_mime_type="application/json",
                    response_schema=_ArticleAIBatch,
                    temperature=0.2,
                ),
            )
            parsed = getattr(response, "parsed", None)
            if parsed is None:
                text = (response.text or "").strip()
                if text:
                    parsed = _ArticleAIBatch.model_validate_json(text)
            await client.aio.aclose()

            if not isinstance(parsed, _ArticleAIBatch):
                return rows

            by_idx = {item.idx: item for item in parsed.results}
            enriched: list[dict] = []
            for idx, row in enumerate(rows):
                ai_item = by_idx.get(idx)
                if not ai_item:
                    enriched.append(row)
                    continue
                candidate_topic = self._normalize_topic_value(ai_item.topic)
                if (source.topic or "all").lower() != "all":
                    candidate_topic = (source.topic or "all").lower()
                enriched.append(
                    {
                        **row,
                        "summary": (ai_item.summary or row.get("summary") or row.get("title") or "")[:220],
                        "topic": candidate_topic,
                        "relevance_score": float(ai_item.relevance_score),
                    }
                )
            return enriched
        except Exception:
            return rows

    def _upsert_articles(self, *, user_id: UUID, source: NewsSource, rows: Iterable[dict]) -> int:
        created = 0
        now = datetime.now(timezone.utc)

        for row in rows:
            existing = self.db.execute(
                select(NewsArticle).where(
                    and_(
                        NewsArticle.user_id == user_id,
                        NewsArticle.url == row["url"],
                    )
                )
            ).scalar_one_or_none()

            if existing:
                existing.title = row["title"]
                existing.source_name = row["source_name"]
                existing.summary = row.get("summary")
                existing.topic = row.get("topic", "all")
                existing.relevance_score = float(row.get("relevance_score", 0.5))
                existing.published_at = row.get("published_at")
                existing.fetched_at = now
                existing.source_id = source.id
                self.db.add(existing)
                continue

            article = NewsArticle(
                user_id=user_id,
                source_id=source.id,
                external_id=row.get("external_id"),
                title=row["title"],
                url=row["url"],
                source_name=row["source_name"],
                summary=row.get("summary"),
                topic=row.get("topic", "all"),
                relevance_score=float(row.get("relevance_score", 0.5)),
                published_at=row.get("published_at"),
                fetched_at=now,
            )
            self.db.add(article)
            created += 1

        return created

    def list_articles(self, *, user_id: UUID, topic: str, limit: int) -> list[NewsArticle]:
        stmt = select(NewsArticle).where(NewsArticle.user_id == user_id)
        if topic != "all":
            stmt = stmt.where(NewsArticle.topic == topic)
        stmt = stmt.order_by(NewsArticle.published_at.desc(), NewsArticle.created_at.desc()).limit(limit)
        return list(self.db.execute(stmt).scalars())

    def list_bookmarks(self, *, user_id: UUID) -> list[tuple[NewsBookmark, NewsArticle]]:
        stmt = (
            select(NewsBookmark, NewsArticle)
            .join(NewsArticle, NewsBookmark.article_id == NewsArticle.id)
            .where(NewsBookmark.user_id == user_id)
            .order_by(NewsBookmark.created_at.desc())
        )
        return list(self.db.execute(stmt).all())

    def bookmark(self, *, user_id: UUID, article_id: UUID) -> bool:
        article = self.db.get(NewsArticle, article_id)
        if not article or article.user_id != user_id:
            return False

        exists = self.db.execute(
            select(NewsBookmark).where(
                NewsBookmark.user_id == user_id,
                NewsBookmark.article_id == article_id,
            )
        ).scalar_one_or_none()
        if exists:
            return True

        self.db.add(NewsBookmark(user_id=user_id, article_id=article_id))
        self.db.commit()
        return True

    def unbookmark(self, *, user_id: UUID, article_id: UUID) -> None:
        self.db.execute(
            delete(NewsBookmark).where(
                NewsBookmark.user_id == user_id,
                NewsBookmark.article_id == article_id,
            )
        )
        self.db.commit()

    @staticmethod
    def _parse_datetime(value: object) -> datetime | None:
        if not isinstance(value, str) or not value:
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except Exception:
            return None

    @staticmethod
    def _normalize_topic(source_topic: str, title: str) -> str:
        source_topic_lc = (source_topic or "all").strip().lower()
        if source_topic_lc != "all":
            return source_topic_lc

        text = title.lower()
        if any(k in text for k in ("ai", "software", "tech", "openai", "google", "microsoft")):
            return "tech"
        if any(k in text for k in ("market", "business", "finance", "funding", "stock")):
            return "business"
        if any(k in text for k in ("science", "space", "research", "nasa")):
            return "science"
        if any(k in text for k in ("world", "war", "election", "country", "global")):
            return "world"
        return "all"

    @staticmethod
    def _one_line_summary(title: str, description: str) -> str:
        text = (description or "").strip()
        if not text:
            return title[:180]
        one_line = " ".join(text.split())
        return one_line[:180]

    @staticmethod
    def _score_relevance(title: str, description: str) -> float:
        text = f"{title} {description}".lower()
        score = 0.5
        if any(k in text for k in ("breaking", "urgent", "major", "launch", "announces")):
            score += 0.2
        if any(k in text for k in ("ai", "productivity", "security", "finance", "market")):
            score += 0.2
        return round(min(score, 1.0), 3)

    @staticmethod
    def _normalize_topic_value(value: str | None) -> str:
        topic = (value or "all").strip().lower()
        return topic if topic in {"all", "tech", "business", "world", "science"} else "all"
