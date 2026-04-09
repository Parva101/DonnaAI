from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.services.sports_service import SportsService


def _login(client: TestClient) -> dict:
    resp = client.post(
        "/api/v1/auth/dev-login",
        json={"email": "sports-api-test@example.com", "full_name": "Sports Tester"},
    )
    assert resp.status_code == 200
    return resp.json()["user"]


def test_sports_endpoints_require_auth(client: TestClient) -> None:
    resp = client.get("/api/v1/sports/teams/tracked")
    assert resp.status_code == 401


def test_list_sports_leagues_includes_new_competitions(client: TestClient) -> None:
    _login(client)
    resp = client.get("/api/v1/sports/leagues")
    assert resp.status_code == 200
    keys = {league["key"] for league in resp.json()["leagues"]}
    assert {"laliga", "ucl", "f1", "ipl", "cricket_intl"}.issubset(keys)


def test_search_sports_teams_mocked(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _login(client)

    async def fake_search(self, *, query: str, league: str | None = None, limit: int = 20):
        assert query == "suns"
        assert league == "nba"
        return [
            {
                "league": "nba",
                "league_label": "NBA",
                "team_id": "21",
                "team_name": "Suns",
                "display_name": "Phoenix Suns",
                "abbreviation": "PHX",
                "location": "Phoenix",
                "logo_url": "https://example.com/phx.png",
            }
        ]

    monkeypatch.setattr(SportsService, "search_teams", fake_search)

    resp = client.get("/api/v1/sports/teams/search?query=suns&league=nba")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["total"] == 1
    assert payload["teams"][0]["display_name"] == "Phoenix Suns"


def test_search_cricket_teams_static_catalog(client: TestClient) -> None:
    _login(client)
    resp = client.get("/api/v1/sports/teams/search?query=india&league=cricket_intl")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["total"] >= 1
    assert any(team["display_name"] == "India" for team in payload["teams"])


def test_track_list_and_untrack_team(client: TestClient) -> None:
    user = _login(client)

    create_resp = client.post(
        "/api/v1/sports/teams/tracked",
        json={
            "league": "nba",
            "team_id": "21",
            "team_name": "Suns",
            "display_name": "Phoenix Suns",
            "abbreviation": "PHX",
            "logo_url": "https://example.com/phx.png",
        },
    )
    assert create_resp.status_code == 200
    created = create_resp.json()
    assert created["user_id"] == user["id"]
    assert created["league"] == "nba"
    assert created["team_id"] == "21"

    list_resp = client.get("/api/v1/sports/teams/tracked")
    assert list_resp.status_code == 200
    listed = list_resp.json()
    assert listed["total"] == 1
    assert listed["teams"][0]["display_name"] == "Phoenix Suns"

    delete_resp = client.delete(f"/api/v1/sports/teams/tracked/{created['id']}")
    assert delete_resp.status_code == 204

    empty_resp = client.get("/api/v1/sports/teams/tracked")
    assert empty_resp.status_code == 200
    assert empty_resp.json()["total"] == 0


def test_live_scores_mocked(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _login(client)

    async def fake_live(self, *, user_id, league=None, limit=50):
        assert league is None
        assert limit == 50
        return [
            {
                "game_id": "401999999",
                "league": "nba",
                "league_label": "NBA",
                "start_time": datetime(2026, 4, 9, 2, 0, tzinfo=timezone.utc),
                "status": "In Progress",
                "status_detail": "Q3 05:11",
                "state": "in",
                "is_live": True,
                "is_final": False,
                "is_upcoming": False,
                "period": 3,
                "clock": "05:11",
                "venue": "Footprint Center",
                "broadcast": "ESPN",
                "home": {
                    "team_id": "21",
                    "name": "Phoenix Suns",
                    "abbreviation": "PHX",
                    "logo_url": None,
                    "home_away": "home",
                    "score": 89,
                    "winner": None,
                    "record": "44-30",
                    "tracked": True,
                },
                "away": {
                    "team_id": "13",
                    "name": "Los Angeles Lakers",
                    "abbreviation": "LAL",
                    "logo_url": None,
                    "home_away": "away",
                    "score": 84,
                    "winner": None,
                    "record": "42-32",
                    "tracked": False,
                },
            }
        ]

    monkeypatch.setattr(SportsService, "list_live_games", fake_live)

    resp = client.get("/api/v1/sports/scores/live")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["total"] == 1
    assert payload["games"][0]["league"] == "nba"
    assert payload["games"][0]["is_live"] is True


def test_untrack_missing_team_returns_404(client: TestClient) -> None:
    _login(client)
    missing = uuid.uuid4()
    resp = client.delete(f"/api/v1/sports/teams/tracked/{missing}")
    assert resp.status_code == 404
