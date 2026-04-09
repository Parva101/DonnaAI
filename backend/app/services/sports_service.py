"""Sports tracking + live scores service backed by ESPN and Cricbuzz public feeds."""

from __future__ import annotations

from datetime import datetime, timezone
import html
import re
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import SportsTrackedTeam
from app.schemas.sports import (
    SportsGameRead,
    SportsGameTeamRead,
    SportsLeagueRead,
    SportsTeamRead,
    SportsTrackTeamRequest,
)

ESPN_BASE = "https://site.api.espn.com/apis/site/v2/sports"
CRICBUZZ_LIVE_SCORES_URL = "https://www.cricbuzz.com/cricket-match/live-scores"

LEAGUE_CONFIG: dict[str, dict[str, str]] = {
    "nfl": {"provider": "espn", "sport": "football", "league": "nfl", "label": "NFL"},
    "nba": {"provider": "espn", "sport": "basketball", "league": "nba", "label": "NBA"},
    "wnba": {"provider": "espn", "sport": "basketball", "league": "wnba", "label": "WNBA"},
    "mlb": {"provider": "espn", "sport": "baseball", "league": "mlb", "label": "MLB"},
    "nhl": {"provider": "espn", "sport": "hockey", "league": "nhl", "label": "NHL"},
    "epl": {"provider": "espn", "sport": "soccer", "league": "eng.1", "label": "Premier League"},
    "laliga": {"provider": "espn", "sport": "soccer", "league": "esp.1", "label": "LaLiga"},
    "ucl": {"provider": "espn", "sport": "soccer", "league": "uefa.champions", "label": "UEFA Champions League"},
    "f1": {"provider": "espn", "sport": "racing", "league": "f1", "label": "Formula 1"},
    "ipl": {"provider": "cricbuzz", "sport": "cricket", "league": "ipl", "label": "IPL (Cricket)"},
    "cricket_intl": {
        "provider": "cricbuzz",
        "sport": "cricket",
        "league": "international",
        "label": "International Cricket",
    },
}

CRICKET_TEAM_CATALOG: dict[str, list[dict[str, Any]]] = {
    "ipl": [
        {"team_id": "csk", "display_name": "Chennai Super Kings", "abbreviation": "CSK"},
        {"team_id": "mi", "display_name": "Mumbai Indians", "abbreviation": "MI"},
        {
            "team_id": "rcb",
            "display_name": "Royal Challengers Bengaluru",
            "abbreviation": "RCB",
            "aliases": ["Royal Challengers Bangalore"],
        },
        {"team_id": "kkr", "display_name": "Kolkata Knight Riders", "abbreviation": "KKR"},
        {"team_id": "rr", "display_name": "Rajasthan Royals", "abbreviation": "RR"},
        {"team_id": "srh", "display_name": "Sunrisers Hyderabad", "abbreviation": "SRH"},
        {"team_id": "dc", "display_name": "Delhi Capitals", "abbreviation": "DC"},
        {"team_id": "lsg", "display_name": "Lucknow Super Giants", "abbreviation": "LSG"},
        {"team_id": "gt", "display_name": "Gujarat Titans", "abbreviation": "GT"},
        {"team_id": "pbks", "display_name": "Punjab Kings", "abbreviation": "PBKS"},
    ],
    "cricket_intl": [
        {"team_id": "india", "display_name": "India", "abbreviation": "IND"},
        {"team_id": "australia", "display_name": "Australia", "abbreviation": "AUS"},
        {"team_id": "england", "display_name": "England", "abbreviation": "ENG"},
        {"team_id": "pakistan", "display_name": "Pakistan", "abbreviation": "PAK"},
        {"team_id": "new_zealand", "display_name": "New Zealand", "abbreviation": "NZ"},
        {"team_id": "south_africa", "display_name": "South Africa", "abbreviation": "SA"},
        {"team_id": "sri_lanka", "display_name": "Sri Lanka", "abbreviation": "SL"},
        {"team_id": "bangladesh", "display_name": "Bangladesh", "abbreviation": "BAN"},
        {"team_id": "afghanistan", "display_name": "Afghanistan", "abbreviation": "AFG"},
        {"team_id": "west_indies", "display_name": "West Indies", "abbreviation": "WI"},
        {"team_id": "ireland", "display_name": "Ireland", "abbreviation": "IRE"},
        {"team_id": "zimbabwe", "display_name": "Zimbabwe", "abbreviation": "ZIM"},
        {"team_id": "netherlands", "display_name": "Netherlands", "abbreviation": "NED"},
        {"team_id": "scotland", "display_name": "Scotland", "abbreviation": "SCO"},
        {"team_id": "nepal", "display_name": "Nepal", "abbreviation": "NEP"},
        {"team_id": "uae", "display_name": "United Arab Emirates", "abbreviation": "UAE"},
    ],
}


def _normalize_lookup(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return slug or "unknown"


def _build_cricket_alias_map() -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for league_key, teams in CRICKET_TEAM_CATALOG.items():
        aliases: dict[str, str] = {}
        for team in teams:
            team_id = str(team.get("team_id") or "").strip()
            if not team_id:
                continue
            options = {
                str(team.get("display_name") or ""),
                str(team.get("abbreviation") or ""),
                team_id.replace("_", " "),
            }
            for alias in team.get("aliases") or []:
                options.add(str(alias or ""))
            for candidate in options:
                normalized = _normalize_lookup(candidate)
                if normalized:
                    aliases[normalized] = team_id
        out[league_key] = aliases
    return out


CRICKET_TEAM_ALIAS_MAP = _build_cricket_alias_map()
CRICBUZZ_MATCH_LINK_RE = re.compile(
    r'href="(?P<href>/live-cricket-scores/(?P<match_id>\d+)/[^"]+)"[^>]*title="(?P<title>[^"]+)"'
)


class SportsService:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def list_supported_leagues() -> list[SportsLeagueRead]:
        return [SportsLeagueRead(key=key, label=cfg["label"]) for key, cfg in LEAGUE_CONFIG.items()]

    @staticmethod
    def _normalize_league(league: str | None) -> str | None:
        if league is None:
            return None
        key = league.strip().lower()
        if not key:
            return None
        if key not in LEAGUE_CONFIG:
            raise ValueError(f"Unsupported league '{league}'.")
        return key

    @staticmethod
    def _league_label(league: str) -> str:
        return LEAGUE_CONFIG.get(league, {}).get("label", league.upper())

    @staticmethod
    def _provider(league: str) -> str:
        return LEAGUE_CONFIG.get(league, {}).get("provider", "espn")

    @staticmethod
    def _teams_url(league: str) -> str:
        cfg = LEAGUE_CONFIG[league]
        if cfg.get("provider") != "espn":
            raise ValueError(f"League '{league}' is not an ESPN-backed league.")
        return f"{ESPN_BASE}/{cfg['sport']}/{cfg['league']}/teams"

    @staticmethod
    def _scoreboard_url(league: str) -> str:
        cfg = LEAGUE_CONFIG[league]
        if cfg.get("provider") != "espn":
            raise ValueError(f"League '{league}' is not an ESPN-backed league.")
        return f"{ESPN_BASE}/{cfg['sport']}/{cfg['league']}/scoreboard"

    @staticmethod
    async def _fetch_json(url: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(url)
            response.raise_for_status()
            payload = response.json()
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    async def _fetch_text(url: str) -> str:
        headers = {"User-Agent": "DonnaAI/1.0 (+https://github.com/Parva101/DonnaAI)"}
        async with httpx.AsyncClient(timeout=20, headers=headers, follow_redirects=True) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.text

    @staticmethod
    def _team_match_score(*, query: str, team: SportsTeamRead) -> int:
        q = query.lower()
        display = team.display_name.lower()
        name = team.team_name.lower()
        abbr = (team.abbreviation or "").lower()
        location = (team.location or "").lower()

        if q == abbr:
            return 120
        if q == display:
            return 110
        if q == name:
            return 100
        if display.startswith(q):
            return 90
        if name.startswith(q):
            return 80
        if location.startswith(q):
            return 70
        if q in display:
            return 60
        if q in name:
            return 50
        if q in location:
            return 40
        return 0

    def _extract_teams(self, *, league: str, payload: dict[str, Any]) -> list[SportsTeamRead]:
        sports = payload.get("sports") or []
        output: list[SportsTeamRead] = []

        for sport in sports:
            leagues = (sport or {}).get("leagues") or []
            for league_obj in leagues:
                teams = (league_obj or {}).get("teams") or []
                for wrapper in teams:
                    team = (wrapper or {}).get("team") or {}
                    team_id = str(team.get("id") or "").strip()
                    if not team_id:
                        continue

                    logos = team.get("logos") or []
                    logo_url = None
                    if logos:
                        logo_url = (logos[0] or {}).get("href")

                    output.append(
                        SportsTeamRead(
                            league=league,
                            league_label=self._league_label(league),
                            team_id=team_id,
                            team_name=str(team.get("name") or team.get("displayName") or "").strip() or "Unknown Team",
                            display_name=str(team.get("displayName") or team.get("name") or "").strip() or "Unknown Team",
                            abbreviation=str(team.get("abbreviation") or "").strip() or None,
                            location=str(team.get("location") or "").strip() or None,
                            logo_url=logo_url,
                        )
                    )

        return output

    def _extract_cricket_catalog_teams(self, *, league: str) -> list[SportsTeamRead]:
        output: list[SportsTeamRead] = []
        for team in CRICKET_TEAM_CATALOG.get(league, []):
            team_id = str(team.get("team_id") or "").strip()
            display_name = str(team.get("display_name") or "").strip()
            if not team_id or not display_name:
                continue
            output.append(
                SportsTeamRead(
                    league=league,
                    league_label=self._league_label(league),
                    team_id=team_id,
                    team_name=display_name,
                    display_name=display_name,
                    abbreviation=str(team.get("abbreviation") or "").strip() or None,
                    location=None,
                    logo_url=None,
                )
            )
        return output

    async def search_teams(
        self,
        *,
        query: str,
        league: str | None = None,
        limit: int = 20,
    ) -> list[SportsTeamRead]:
        normalized_league = self._normalize_league(league)
        query_lc = query.strip().lower()
        if not query_lc:
            return []

        league_keys = [normalized_league] if normalized_league else list(LEAGUE_CONFIG.keys())
        scored: list[tuple[int, SportsTeamRead]] = []
        seen: set[tuple[str, str]] = set()

        for league_key in league_keys:
            if league_key is None:
                continue
            provider = self._provider(league_key)
            if provider == "cricbuzz":
                teams = self._extract_cricket_catalog_teams(league=league_key)
            else:
                payload = await self._fetch_json(self._teams_url(league_key))
                teams = self._extract_teams(league=league_key, payload=payload)

            for team in teams:
                dedupe_key = (team.league, team.team_id)
                if dedupe_key in seen:
                    continue
                match_score = self._team_match_score(query=query_lc, team=team)
                if match_score <= 0:
                    continue
                seen.add(dedupe_key)
                scored.append((match_score, team))

        scored.sort(key=lambda item: (-item[0], item[1].display_name.lower()))
        return [team for _, team in scored[: max(1, min(limit, 100))]]

    def list_tracked_teams(self, *, user_id: UUID, league: str | None = None) -> list[SportsTrackedTeam]:
        normalized_league = self._normalize_league(league)

        stmt = select(SportsTrackedTeam).where(SportsTrackedTeam.user_id == user_id)
        if normalized_league:
            stmt = stmt.where(SportsTrackedTeam.league == normalized_league)
        stmt = stmt.order_by(SportsTrackedTeam.league.asc(), SportsTrackedTeam.display_name.asc())
        return list(self.db.execute(stmt).scalars())

    def track_team(self, *, user_id: UUID, payload: SportsTrackTeamRequest) -> SportsTrackedTeam:
        league = self._normalize_league(payload.league)
        if league is None:
            raise ValueError("League is required.")

        existing = self.db.execute(
            select(SportsTrackedTeam).where(
                SportsTrackedTeam.user_id == user_id,
                SportsTrackedTeam.league == league,
                SportsTrackedTeam.team_id == payload.team_id.strip(),
            )
        ).scalar_one_or_none()
        if existing:
            return existing

        row = SportsTrackedTeam(
            user_id=user_id,
            league=league,
            team_id=payload.team_id.strip(),
            team_name=payload.team_name.strip(),
            display_name=payload.display_name.strip(),
            abbreviation=(payload.abbreviation or "").strip().upper() or None,
            logo_url=(payload.logo_url or "").strip() or None,
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def untrack_team(self, *, user_id: UUID, tracked_team_id: UUID) -> bool:
        row = self.db.get(SportsTrackedTeam, tracked_team_id)
        if row is None or row.user_id != user_id:
            return False
        self.db.delete(row)
        self.db.commit()
        return True

    @staticmethod
    def _parse_dt(value: Any) -> datetime | None:
        if not isinstance(value, str) or not value:
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except Exception:
            return None

    @staticmethod
    def _parse_int(value: Any) -> int | None:
        try:
            return int(value)
        except Exception:
            return None

    @staticmethod
    def _parse_cricket_title(title: str) -> tuple[str, str, str, str | None] | None:
        raw = title.strip()
        if not raw:
            return None

        left, status = raw, "Scheduled"
        if " - " in raw:
            left, status = raw.split(" - ", 1)
            left = left.strip()
            status = status.strip() or "Scheduled"

        teams_part = left
        context = None
        if "," in left:
            teams_part, context = left.split(",", 1)
            teams_part = teams_part.strip()
            context = context.strip() or None

        if " vs " not in teams_part.lower():
            return None
        away_name, home_name = [piece.strip() for piece in teams_part.split(" vs ", 1)]
        if not away_name or not home_name:
            return None

        return away_name, home_name, status, context

    @staticmethod
    def _cricket_status_flags(status: str) -> tuple[str, bool, bool, bool]:
        lowered = status.lower()
        final_tokens = (" won", "complete", "abandoned", "no result", "match drawn", "tied")
        upcoming_tokens = ("preview", "starts", "yet to start", "scheduled")
        live_tokens = ("live", "in progress", "stumps", "innings break", "rain delay")

        if any(token in lowered for token in final_tokens):
            return ("post", False, True, False)
        if any(token in lowered for token in upcoming_tokens):
            return ("pre", False, False, True)
        if any(token in lowered for token in live_tokens):
            return ("in", True, False, False)
        return ("pre", False, False, True)

    @staticmethod
    def _resolve_cricket_team_id(*, league: str, name: str) -> str:
        normalized = _normalize_lookup(name)
        if not normalized:
            return _slugify(name)

        league_aliases = CRICKET_TEAM_ALIAS_MAP.get(league, {})
        if normalized in league_aliases:
            return league_aliases[normalized]

        # Fall back to any known cricket alias in case the source feed labels differ by competition.
        for aliases in CRICKET_TEAM_ALIAS_MAP.values():
            if normalized in aliases:
                return aliases[normalized]
        return _slugify(name)

    @staticmethod
    def _cricket_team_meta(*, league: str, team_id: str) -> dict[str, Any]:
        for team in CRICKET_TEAM_CATALOG.get(league, []):
            if str(team.get("team_id") or "").strip() == team_id:
                return team
        for teams in CRICKET_TEAM_CATALOG.values():
            for team in teams:
                if str(team.get("team_id") or "").strip() == team_id:
                    return team
        return {}

    def _extract_cricket_games(
        self,
        *,
        league: str,
        html_payload: str,
        tracked_team_ids: set[str],
    ) -> list[SportsGameRead]:
        seen_match_ids: set[str] = set()
        output: list[SportsGameRead] = []

        for match in CRICBUZZ_MATCH_LINK_RE.finditer(html_payload):
            match_id = str(match.group("match_id") or "").strip()
            if not match_id or match_id in seen_match_ids:
                continue
            seen_match_ids.add(match_id)

            title = html.unescape(str(match.group("title") or "")).strip()
            parsed = self._parse_cricket_title(title)
            if parsed is None:
                continue
            away_name, home_name, status, context = parsed

            away_id = self._resolve_cricket_team_id(league=league, name=away_name)
            home_id = self._resolve_cricket_team_id(league=league, name=home_name)
            away_tracked = away_id in tracked_team_ids
            home_tracked = home_id in tracked_team_ids
            if not (away_tracked or home_tracked):
                continue

            away_meta = self._cricket_team_meta(league=league, team_id=away_id)
            home_meta = self._cricket_team_meta(league=league, team_id=home_id)
            state, is_live, is_final, is_upcoming = self._cricket_status_flags(status)

            output.append(
                SportsGameRead(
                    game_id=f"cricket:{match_id}",
                    league=league,
                    league_label=self._league_label(league),
                    start_time=None,
                    status=status,
                    status_detail=context,
                    state=state,
                    is_live=is_live,
                    is_final=is_final,
                    is_upcoming=is_upcoming,
                    period=None,
                    clock=None,
                    venue=None,
                    broadcast="Cricbuzz",
                    home=SportsGameTeamRead(
                        team_id=home_id,
                        name=home_name,
                        abbreviation=str(home_meta.get("abbreviation") or "").strip() or None,
                        logo_url=None,
                        home_away="home",
                        score=None,
                        winner=None,
                        record=None,
                        tracked=home_tracked,
                    ),
                    away=SportsGameTeamRead(
                        team_id=away_id,
                        name=away_name,
                        abbreviation=str(away_meta.get("abbreviation") or "").strip() or None,
                        logo_url=None,
                        home_away="away",
                        score=None,
                        winner=None,
                        record=None,
                        tracked=away_tracked,
                    ),
                )
            )

        return output

    def _extract_games(
        self,
        *,
        league: str,
        payload: dict[str, Any],
        tracked_team_ids: set[str],
    ) -> list[SportsGameRead]:
        events = payload.get("events") or []
        output: list[SportsGameRead] = []

        for event in events:
            competition = ((event or {}).get("competitions") or [{}])[0] or {}
            competitors = competition.get("competitors") or []
            if not competitors:
                continue

            parsed_teams: dict[str, SportsGameTeamRead] = {}
            for competitor in competitors:
                team = (competitor or {}).get("team") or {}
                team_id = str(team.get("id") or "").strip()
                if not team_id:
                    continue

                logo_url = (team.get("logo") or "").strip() or None
                if not logo_url:
                    logos = team.get("logos") or []
                    if logos:
                        logo_url = str((logos[0] or {}).get("href") or "").strip() or None

                home_away = str(competitor.get("homeAway") or "").strip().lower() or "away"
                records = competitor.get("records") or []
                record = None
                if records:
                    record = str((records[0] or {}).get("summary") or "").strip() or None

                parsed_teams[home_away] = SportsGameTeamRead(
                    team_id=team_id,
                    name=str(team.get("displayName") or team.get("name") or "").strip() or "Unknown Team",
                    abbreviation=str(team.get("abbreviation") or "").strip() or None,
                    logo_url=logo_url,
                    home_away=home_away,
                    score=self._parse_int(competitor.get("score")),
                    winner=competitor.get("winner"),
                    record=record,
                    tracked=team_id in tracked_team_ids,
                )

            home = parsed_teams.get("home")
            away = parsed_teams.get("away")
            if home is None or away is None:
                continue
            if not (home.tracked or away.tracked):
                continue

            status = (event or {}).get("status") or {}
            status_type = status.get("type") or {}
            state = str(status_type.get("state") or "").strip().lower()
            is_final = bool(status_type.get("completed")) or state == "post"
            is_live = state == "in"
            is_upcoming = state == "pre"

            venue = ((competition.get("venue") or {}).get("fullName") or "").strip() or None
            broadcasts = competition.get("broadcasts") or []
            broadcast = None
            if broadcasts:
                names = (broadcasts[0] or {}).get("names") or []
                if names:
                    broadcast = ", ".join([str(name).strip() for name in names if str(name).strip()]) or None

            game_id = str((event or {}).get("id") or "").strip()
            if not game_id:
                game_id = f"{league}:{home.team_id}:{away.team_id}:{event.get('date') or ''}"

            output.append(
                SportsGameRead(
                    game_id=game_id,
                    league=league,
                    league_label=self._league_label(league),
                    start_time=self._parse_dt(event.get("date")),
                    status=str(status_type.get("description") or "Scheduled"),
                    status_detail=str(status_type.get("shortDetail") or status_type.get("detail") or "").strip() or None,
                    state=state or ("post" if is_final else "pre"),
                    is_live=is_live,
                    is_final=is_final,
                    is_upcoming=is_upcoming,
                    period=self._parse_int(status.get("period")),
                    clock=str(status.get("displayClock") or "").strip() or None,
                    venue=venue,
                    broadcast=broadcast,
                    home=home,
                    away=away,
                )
            )

        return output

    async def list_live_games(
        self,
        *,
        user_id: UUID,
        league: str | None = None,
        limit: int = 50,
    ) -> list[SportsGameRead]:
        normalized_league = self._normalize_league(league)
        tracked = self.list_tracked_teams(user_id=user_id, league=normalized_league)
        if not tracked:
            return []

        by_league: dict[str, set[str]] = {}
        for row in tracked:
            by_league.setdefault(row.league, set()).add(str(row.team_id))

        games: list[SportsGameRead] = []
        cricket_live_html: str | None = None
        for league_key, team_ids in by_league.items():
            provider = self._provider(league_key)
            if provider == "cricbuzz":
                if cricket_live_html is None:
                    cricket_live_html = await self._fetch_text(CRICBUZZ_LIVE_SCORES_URL)
                games.extend(
                    self._extract_cricket_games(
                        league=league_key,
                        html_payload=cricket_live_html,
                        tracked_team_ids=team_ids,
                    )
                )
            else:
                payload = await self._fetch_json(self._scoreboard_url(league_key))
                games.extend(self._extract_games(league=league_key, payload=payload, tracked_team_ids=team_ids))

        def _sort_key(game: SportsGameRead) -> tuple[int, datetime]:
            rank = 2
            if game.is_live:
                rank = 0
            elif game.is_upcoming:
                rank = 1
            dt = game.start_time or datetime.max.replace(tzinfo=timezone.utc)
            return (rank, dt)

        games.sort(key=_sort_key)
        return games[: max(1, min(limit, 200))]
