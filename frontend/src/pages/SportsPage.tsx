import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { CalendarClock, CalendarPlus, Loader2, Plus, RefreshCw, Search, Trash2, Trophy, Tv } from "lucide-react";
import { format, formatDistanceToNow } from "date-fns";

import {
  addSportsGameToCalendar,
  ApiError,
  listSportsLeagues,
  listSportsLiveScores,
  listTrackedSportsTeams,
  searchSportsTeams,
  trackSportsTeam,
  untrackSportsTeam,
} from "@/lib/api";
import type { SportsGame, SportsLeague, SportsTeam, SportsTrackedTeam } from "@/types";

function gameStatusClass(game: SportsGame): string {
  if (game.is_live) return "bg-red-500/15 text-red-400 border-red-500/30";
  if (game.is_final) return "bg-muted text-muted-foreground border-border";
  return "bg-primary/15 text-primary border-primary/30";
}

function formatGameTime(game: SportsGame): string {
  if (!game.start_time) return "Time TBD";
  return format(new Date(game.start_time), "EEE, MMM d p");
}

export function SportsPage() {
  const [leagues, setLeagues] = useState<SportsLeague[]>([]);
  const [trackedTeams, setTrackedTeams] = useState<SportsTrackedTeam[]>([]);
  const [games, setGames] = useState<SportsGame[]>([]);
  const [generatedAt, setGeneratedAt] = useState<string | null>(null);

  const [loading, setLoading] = useState(true);
  const [gamesLoading, setGamesLoading] = useState(false);
  const [searching, setSearching] = useState(false);
  const [savingTeamKey, setSavingTeamKey] = useState<string | null>(null);
  const [calendarSavingGameId, setCalendarSavingGameId] = useState<string | null>(null);
  const [calendarMessage, setCalendarMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [searchText, setSearchText] = useState("");
  const [searchLeague, setSearchLeague] = useState("all");
  const [scoreLeague, setScoreLeague] = useState("all");
  const [searchResults, setSearchResults] = useState<SportsTeam[]>([]);

  const trackedKeySet = useMemo(
    () => new Set(trackedTeams.map((team) => `${team.league}:${team.team_id}`)),
    [trackedTeams],
  );

  const loadTrackedTeams = useCallback(async () => {
    const resp = await listTrackedSportsTeams();
    setTrackedTeams(resp.teams);
    return resp.teams;
  }, []);

  const loadScores = useCallback(async () => {
    setGamesLoading(true);
    try {
      if (trackedTeams.length === 0) {
        setGames([]);
        setGeneratedAt(null);
        return;
      }
      const resp = await listSportsLiveScores({
        league: scoreLeague !== "all" ? scoreLeague : undefined,
        limit: 100,
      });
      setGames(resp.games);
      setGeneratedAt(resp.generated_at);
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "Failed to load live scores.";
      setError(message);
    } finally {
      setGamesLoading(false);
    }
  }, [scoreLeague, trackedTeams.length]);

  const loadInitial = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [leagueResp] = await Promise.all([listSportsLeagues(), loadTrackedTeams()]);
      setLeagues(leagueResp.leagues);
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "Failed to load sports data.";
      setError(message);
    } finally {
      setLoading(false);
    }
  }, [loadTrackedTeams]);

  useEffect(() => {
    void loadInitial();
  }, [loadInitial]);

  useEffect(() => {
    void loadScores();
  }, [loadScores]);

  const onSearch = async (event: FormEvent) => {
    event.preventDefault();
    const query = searchText.trim();
    if (!query) {
      setSearchResults([]);
      return;
    }
    setSearching(true);
    setError(null);
    try {
      const resp = await searchSportsTeams({
        query,
        league: searchLeague === "all" ? undefined : searchLeague,
        limit: 30,
      });
      setSearchResults(resp.teams);
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "Team search failed.";
      setError(message);
      setSearchResults([]);
    } finally {
      setSearching(false);
    }
  };

  const onTrackTeam = async (team: SportsTeam) => {
    const key = `${team.league}:${team.team_id}`;
    setSavingTeamKey(key);
    setError(null);
    setCalendarMessage(null);
    try {
      await trackSportsTeam({
        league: team.league,
        team_id: team.team_id,
        team_name: team.team_name,
        display_name: team.display_name,
        abbreviation: team.abbreviation,
        logo_url: team.logo_url,
      });
      await loadTrackedTeams();
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "Failed to track team.";
      setError(message);
    } finally {
      setSavingTeamKey(null);
    }
  };

  const onUntrackTeam = async (team: SportsTrackedTeam) => {
    setSavingTeamKey(team.id);
    setError(null);
    setCalendarMessage(null);
    try {
      await untrackSportsTeam(team.id);
      await loadTrackedTeams();
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "Failed to remove tracked team.";
      setError(message);
    } finally {
      setSavingTeamKey(null);
    }
  };

  const onAddGameToCalendar = async (game: SportsGame) => {
    if (!game.start_time) {
      setError("Cannot add this game to calendar because its start time is not available yet.");
      return;
    }

    setCalendarSavingGameId(game.game_id);
    setError(null);
    setCalendarMessage(null);
    try {
      const result = await addSportsGameToCalendar({
        game_id: game.game_id,
        league: game.league,
        league_label: game.league_label,
        start_time: game.start_time,
        status: game.status,
        status_detail: game.status_detail,
        venue: game.venue,
        broadcast: game.broadcast,
        home: game.home,
        away: game.away,
      });
      setCalendarMessage(`Added "${result.event.title}" to calendar.`);
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "Failed to add game to calendar.";
      setError(message);
    } finally {
      setCalendarSavingGameId(null);
    }
  };

  const subtitle = useMemo(() => {
    if (loading) return "Loading sports trackers...";
    return `${trackedTeams.length} tracked team${trackedTeams.length === 1 ? "" : "s"} across ${leagues.length} leagues`;
  }, [leagues.length, loading, trackedTeams.length]);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold text-foreground">Sports Tracker</h2>
          <p className="text-sm text-muted-foreground mt-0.5">{subtitle}</p>
        </div>
        <button
          onClick={() => void loadScores()}
          className="flex items-center gap-2 h-9 px-4 rounded-lg border border-border bg-card text-sm text-muted-foreground hover:text-foreground hover:bg-secondary transition-colors"
          disabled={gamesLoading || loading}
        >
          {gamesLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
          Refresh Scores
        </button>
      </div>

      {error && (
        <div className="rounded-xl border border-destructive/30 bg-destructive/[0.08] px-4 py-3 text-sm text-destructive">
          {error}
        </div>
      )}
      {calendarMessage && (
        <div className="rounded-xl border border-primary/30 bg-primary/[0.08] px-4 py-3 text-sm text-primary">
          {calendarMessage}
        </div>
      )}

      <div className="grid grid-cols-1 xl:grid-cols-[2fr,1fr] gap-4">
        <div className="space-y-4">
          <div className="rounded-xl border border-border bg-card">
            <div className="px-5 py-4 border-b border-border flex items-center justify-between">
              <h3 className="text-sm font-semibold text-foreground">My Teams</h3>
              <span className="text-xs text-muted-foreground">{trackedTeams.length} tracked</span>
            </div>
            <div className="p-4">
              {trackedTeams.length === 0 ? (
                <p className="text-sm text-muted-foreground">No tracked teams yet. Search and add teams from the panel on the right.</p>
              ) : (
                <div className="flex flex-wrap gap-2">
                  {trackedTeams.map((team) => (
                    <div
                      key={team.id}
                      className="inline-flex items-center gap-2 rounded-full border border-border bg-secondary/25 px-3 py-1.5 text-xs"
                    >
                      {team.logo_url ? (
                        <img src={team.logo_url} alt={team.display_name} className="h-4 w-4 rounded-sm object-contain" />
                      ) : (
                        <Trophy className="h-3.5 w-3.5 text-muted-foreground" />
                      )}
                      <span className="font-medium text-foreground">{team.display_name}</span>
                      <span className="text-muted-foreground">{team.league_label}</span>
                      <button
                        onClick={() => void onUntrackTeam(team)}
                        className="text-muted-foreground hover:text-destructive transition-colors"
                        title="Remove team"
                        disabled={savingTeamKey === team.id}
                      >
                        {savingTeamKey === team.id ? (
                          <Loader2 className="h-3.5 w-3.5 animate-spin" />
                        ) : (
                          <Trash2 className="h-3.5 w-3.5" />
                        )}
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          <div className="rounded-xl border border-border bg-card">
            <div className="px-5 py-4 border-b border-border flex items-center justify-between gap-3">
              <div>
                <h3 className="text-sm font-semibold text-foreground">Live Scores</h3>
                <p className="text-xs text-muted-foreground mt-0.5">
                  {generatedAt ? `Updated ${formatDistanceToNow(new Date(generatedAt), { addSuffix: true })}` : "No updates yet"}
                </p>
              </div>
              <select
                value={scoreLeague}
                onChange={(event) => setScoreLeague(event.target.value)}
                className="h-8 rounded-md border border-border bg-secondary px-2.5 text-xs text-foreground"
              >
                <option value="all">All Leagues</option>
                {leagues.map((league) => (
                  <option key={league.key} value={league.key}>
                    {league.label}
                  </option>
                ))}
              </select>
            </div>
            <div className="p-4 space-y-3 max-h-[70vh] overflow-y-auto">
              {gamesLoading ? (
                <div className="flex items-center justify-center py-16">
                  <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
                </div>
              ) : games.length === 0 ? (
                <div className="py-16 text-center">
                  <p className="text-sm text-muted-foreground">No games found for your tracked teams in this league filter.</p>
                </div>
              ) : (
                games.map((game) => (
                  <div key={game.game_id} className="rounded-xl border border-border/70 bg-secondary/20 p-4 space-y-3">
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex items-center gap-2">
                        <span className="text-[11px] uppercase tracking-wider text-primary">{game.league_label}</span>
                        <span className={`rounded-full border px-2 py-0.5 text-[10px] font-medium ${gameStatusClass(game)}`}>
                          {game.status}
                        </span>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="text-xs text-muted-foreground">{formatGameTime(game)}</span>
                        <button
                          onClick={() => void onAddGameToCalendar(game)}
                          disabled={!game.start_time || calendarSavingGameId === game.game_id}
                          className="inline-flex items-center gap-1 rounded-md border border-border px-2 py-1 text-[11px] text-foreground hover:bg-secondary disabled:opacity-60"
                          title={game.start_time ? "Add game to calendar" : "Start time required"}
                        >
                          {calendarSavingGameId === game.game_id ? (
                            <Loader2 className="h-3.5 w-3.5 animate-spin" />
                          ) : (
                            <CalendarPlus className="h-3.5 w-3.5" />
                          )}
                          Add
                        </button>
                      </div>
                    </div>

                    {[game.away, game.home].map((team) => (
                      <div
                        key={`${game.game_id}-${team.home_away}`}
                        className={`flex items-center justify-between rounded-lg px-2 py-1.5 ${
                          team.tracked ? "bg-primary/10 border border-primary/25" : ""
                        }`}
                      >
                        <div className="flex items-center gap-2 min-w-0">
                          {team.logo_url ? (
                            <img src={team.logo_url} alt={team.name} className="h-6 w-6 rounded object-contain" />
                          ) : (
                            <Trophy className="h-4 w-4 text-muted-foreground" />
                          )}
                          <div className="min-w-0">
                            <p className="text-sm font-medium text-foreground truncate">
                              {team.name}
                              {team.tracked ? <span className="ml-1 text-[10px] text-primary align-middle">TRACKED</span> : null}
                            </p>
                            <p className="text-[11px] text-muted-foreground">{team.record || "-"}</p>
                          </div>
                        </div>
                        <p className="text-lg font-semibold text-foreground tabular-nums">{team.score ?? "-"}</p>
                      </div>
                    ))}

                    <div className="grid grid-cols-1 md:grid-cols-3 gap-2 text-xs text-muted-foreground">
                      <div className="flex items-center gap-1.5">
                        <CalendarClock className="h-3.5 w-3.5" />
                        <span>{game.status_detail || "No status detail yet"}</span>
                      </div>
                      <div className="flex items-center gap-1.5">
                        <Trophy className="h-3.5 w-3.5" />
                        <span>{game.venue || "Venue TBD"}</span>
                      </div>
                      <div className="flex items-center gap-1.5">
                        <Tv className="h-3.5 w-3.5" />
                        <span>{game.broadcast || "Broadcast TBD"}</span>
                      </div>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>

        <div className="space-y-4">
          <div className="rounded-xl border border-border bg-card p-4 space-y-3">
            <h3 className="text-sm font-semibold text-foreground">Add Teams</h3>
            <form onSubmit={(event) => void onSearch(event)} className="space-y-2">
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                <input
                  value={searchText}
                  onChange={(event) => setSearchText(event.target.value)}
                  placeholder="Search team name or abbreviation"
                  className="h-9 w-full rounded-lg border border-border bg-secondary pl-9 pr-3 text-sm text-foreground"
                />
              </div>
              <select
                value={searchLeague}
                onChange={(event) => setSearchLeague(event.target.value)}
                className="h-9 w-full rounded-lg border border-border bg-secondary px-3 text-sm text-foreground"
              >
                <option value="all">All Leagues</option>
                {leagues.map((league) => (
                  <option key={league.key} value={league.key}>
                    {league.label}
                  </option>
                ))}
              </select>
              <button
                type="submit"
                className="inline-flex items-center gap-2 h-8 px-3 rounded-lg bg-primary text-primary-foreground text-xs font-medium hover:bg-primary/90"
                disabled={searching}
              >
                {searching ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Search className="h-3.5 w-3.5" />}
                Search
              </button>
            </form>

            <div className="space-y-2 max-h-[500px] overflow-y-auto">
              {searchResults.length === 0 ? (
                <p className="text-xs text-muted-foreground">Search results appear here.</p>
              ) : (
                searchResults.map((team) => {
                  const key = `${team.league}:${team.team_id}`;
                  const alreadyTracked = trackedKeySet.has(key);
                  return (
                    <div key={key} className="rounded-lg border border-border/60 bg-secondary/25 px-3 py-2">
                      <div className="flex items-center justify-between gap-2">
                        <div className="min-w-0">
                          <p className="text-sm font-medium text-foreground truncate">{team.display_name}</p>
                          <p className="text-[11px] text-muted-foreground">
                            {team.league_label}
                            {team.abbreviation ? ` - ${team.abbreviation}` : ""}
                            {team.location ? ` - ${team.location}` : ""}
                          </p>
                        </div>
                        <button
                          onClick={() => void onTrackTeam(team)}
                          disabled={alreadyTracked || savingTeamKey === key}
                          className="inline-flex items-center gap-1 rounded-md border border-border px-2 py-1 text-[11px] text-foreground hover:bg-secondary disabled:opacity-60"
                        >
                          {savingTeamKey === key ? (
                            <Loader2 className="h-3.5 w-3.5 animate-spin" />
                          ) : (
                            <Plus className="h-3.5 w-3.5" />
                          )}
                          {alreadyTracked ? "Tracked" : "Track"}
                        </button>
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
