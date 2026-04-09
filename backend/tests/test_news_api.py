from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app.core.db import get_db
from app.main import app
from app.models import NewsArticle
from app.services.news_service import NewsService


def _login(client: TestClient) -> dict:
    resp = client.post(
        "/api/v1/auth/dev-login",
        json={"email": "news-api-test@example.com", "full_name": "News Tester"},
    )
    assert resp.status_code == 200
    return resp.json()["user"]


def _seed_article(client: TestClient, user_id: str) -> str:
    db_gen = app.dependency_overrides[get_db]()
    db = next(db_gen)
    article = NewsArticle(
        user_id=uuid.UUID(user_id),
        source_id=None,
        external_id="seed-article-1",
        title="AI in healthcare",
        url="https://example.com/ai-healthcare",
        source_name="Seed Source",
        summary="A quick summary",
        topic="tech",
        relevance_score=0.8,
    )
    db.add(article)
    db.commit()
    db.refresh(article)
    return str(article.id)


def test_news_sources_and_bookmarks(client: TestClient, monkeypatch) -> None:
    user = _login(client)
    article_id = _seed_article(client, user["id"])

    async def fake_fetch(self, *, user_id, limit_per_source=20):
        return 0

    monkeypatch.setattr(NewsService, "fetch_for_user", fake_fetch)

    sources_resp = client.get("/api/v1/news/sources")
    assert sources_resp.status_code == 200
    assert len(sources_resp.json()["sources"]) >= 1

    articles_resp = client.get("/api/v1/news/articles?topic=tech&limit=10")
    assert articles_resp.status_code == 200
    assert len(articles_resp.json()["articles"]) >= 1

    bookmark_resp = client.post(f"/api/v1/news/bookmarks/{article_id}")
    assert bookmark_resp.status_code == 200

    list_bookmarks = client.get("/api/v1/news/bookmarks")
    assert list_bookmarks.status_code == 200
    assert len(list_bookmarks.json()["bookmarks"]) >= 1
