import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ArrowUpRight,
  ExternalLink,
  ListChecks,
  Loader2,
  Mail,
  MessageSquare,
  Music2,
  Newspaper,
  Pause,
  Phone,
  Play,
  SkipBack,
  SkipForward,
  TrendingUp,
  type LucideIcon,
} from "lucide-react";
import { format, formatDistanceToNow, isToday, parseISO } from "date-fns";

import {
  ApiError,
  SPOTIFY_CONNECT_URL,
  getDailyDigest,
  listConnectedAccounts,
  getTeamsPresence,
  getSpotifyPlayer,
  listActionItems,
  listCalendarEvents,
  listEmails,
  listInboxConversations,
  listNewsArticles,
  listVoiceCalls,
  spotifyNext,
  spotifyPause,
  spotifyPlay,
  spotifyPrevious,
  spotifySetVolume,
} from "@/lib/api";
import { cn, getGreeting } from "@/lib/utils";
import type {
  ActionItem,
  CalendarEvent,
  DailyDigestResponse,
  InboxConversationSummary,
  NewsArticle,
  SpotifyPlayerState,
  TeamsPresenceResponse,
} from "@/types";

type Platform = "gmail" | "slack" | "whatsapp" | "teams";

const platformMeta: Record<Platform, { dot: string; label: string }> = {
  gmail: { dot: "bg-red-400", label: "Gmail" },
  slack: { dot: "bg-green-500", label: "Slack" },
  whatsapp: { dot: "bg-emerald-400", label: "WhatsApp" },
  teams: { dot: "bg-violet-400", label: "Teams" },
};

function renderArtists(state: SpotifyPlayerState | null): string {
  if (!state?.track?.artists?.length) return "Unknown artist";
  return state.track.artists.map((a) => a.name).join(", ");
}

function formatEventTime(event: CalendarEvent): string {
  try {
    const start = parseISO(event.start_at);
    const end = parseISO(event.end_at);
    if (event.is_all_day) return "All day";
    return `${format(start, "p")} - ${format(end, "p")}`;
  } catch {
    return "Unknown time";
  }
}

function calcEventDuration(event: CalendarEvent): string {
  try {
    const start = parseISO(event.start_at).getTime();
    const end = parseISO(event.end_at).getTime();
    const mins = Math.max(Math.round((end - start) / 60000), 0);
    if (mins >= 60) {
      const h = Math.floor(mins / 60);
      const rem = mins % 60;
      return rem ? `${h}h ${rem}m` : `${h}h`;
    }
    return `${mins}m`;
  } catch {
    return "";
  }
}

export function DashboardPage() {
  const greeting = getGreeting();

  const [spotifyState, setSpotifyState] = useState<SpotifyPlayerState | null>(null);
  const [spotifyConnected, setSpotifyConnected] = useState<boolean | null>(null);
  const [spotifyLoading, setSpotifyLoading] = useState(true);
  const [spotifyBusy, setSpotifyBusy] = useState(false);
  const [spotifyError, setSpotifyError] = useState<string | null>(null);

  const [digest, setDigest] = useState<DailyDigestResponse | null>(null);
  const [actionItems, setActionItems] = useState<ActionItem[]>([]);
  const [teamsPresence, setTeamsPresence] = useState<TeamsPresenceResponse | null>(null);
  const [inboxRows, setInboxRows] = useState<InboxConversationSummary[]>([]);
  const [calendarRows, setCalendarRows] = useState<CalendarEvent[]>([]);
  const [newsRows, setNewsRows] = useState<NewsArticle[]>([]);
  const [unreadEmails, setUnreadEmails] = useState(0);
  const [todayCalls, setTodayCalls] = useState(0);

  const fetchSpotifyState = useCallback(async () => {
    try {
      const state = await getSpotifyPlayer();
      setSpotifyState(state);
      setSpotifyConnected(true);
      setSpotifyError(null);
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        setSpotifyConnected(false);
        setSpotifyState(null);
        setSpotifyError(null);
      } else if (err instanceof ApiError) {
        setSpotifyConnected(true);
        setSpotifyError(err.message);
      } else {
        setSpotifyConnected(true);
        setSpotifyError("Failed to load Spotify state.");
      }
    } finally {
      setSpotifyLoading(false);
    }
  }, []);

  const loadDashboard = useCallback(async () => {
    try {
      const accounts = await listConnectedAccounts().catch(() => []);
      const teamsAccount = accounts.find((acc) => acc.provider === "teams");
      const calendarAccount = accounts.find((acc) => acc.provider === "google");

      const [
        inboxRes,
        calendarRes,
        newsRes,
        digestRes,
        actionRes,
        presenceRes,
        emailsRes,
        callsRes,
      ] = await Promise.all([
        listInboxConversations({ limit: 6 }),
        calendarAccount
          ? listCalendarEvents({ limit: 3, account_id: calendarAccount.id }).catch(() => ({
              events: [],
              total: 0,
            }))
          : Promise.resolve({ events: [], total: 0 }),
        listNewsArticles({ topic: "all", limit: 4 }),
        getDailyDigest(),
        listActionItems("open"),
        teamsAccount ? getTeamsPresence(teamsAccount.id).catch(() => null) : Promise.resolve(null),
        listEmails({ is_read: false, limit: 1 }),
        listVoiceCalls(50),
      ]);

      setInboxRows(inboxRes.conversations);
      setCalendarRows(calendarRes.events.slice(0, 3));
      setNewsRows(newsRes.articles.slice(0, 4));
      setDigest(digestRes);
      setActionItems(actionRes.items.slice(0, 5));
      setTeamsPresence(presenceRes);
      setUnreadEmails(emailsRes.total);

      const callsToday = callsRes.calls.filter((call) => {
        if (!call.created_at) return false;
        try {
          return isToday(parseISO(call.created_at));
        } catch {
          return false;
        }
      });
      setTodayCalls(callsToday.length);
    } catch {
      // Keep dashboard resilient if one integration is unavailable.
    }
  }, []);

  useEffect(() => {
    void fetchSpotifyState();
    const timer = window.setInterval(() => {
      void fetchSpotifyState();
    }, 30000);
    return () => window.clearInterval(timer);
  }, [fetchSpotifyState]);

  useEffect(() => {
    void loadDashboard();
  }, [loadDashboard]);

  const runPlayerAction = useCallback(
    async (fn: () => Promise<unknown>) => {
      setSpotifyBusy(true);
      setSpotifyError(null);
      try {
        await fn();
        await fetchSpotifyState();
      } catch (err) {
        if (err instanceof ApiError) {
          setSpotifyError(err.message);
        } else {
          setSpotifyError("Spotify control request failed.");
        }
      } finally {
        setSpotifyBusy(false);
      }
    },
    [fetchSpotifyState],
  );

  const handleVolumeDelta = (delta: number) => {
    const current = spotifyState?.device?.volume_percent;
    if (current === undefined || current === null) return;
    const next = Math.max(0, Math.min(100, current + delta));
    void runPlayerAction(() => spotifySetVolume(next));
  };

  const stats: {
    title: string;
    value: string;
    detail: string;
    icon: LucideIcon;
    trend?: string;
    color: string;
  }[] = useMemo(
    () => [
      {
        title: "Messages",
        value: String(inboxRows.reduce((acc, row) => acc + row.unread_count, 0)),
        detail: "unread across inbox",
        icon: MessageSquare,
        color: "text-primary bg-primary/10",
      },
      {
        title: "Emails",
        value: String(unreadEmails),
        detail: "unread",
        icon: Mail,
        color: "text-purple-400 bg-purple-400/10",
      },
      {
        title: "Calls",
        value: String(todayCalls),
        detail: "today",
        icon: Phone,
        color: "text-success bg-success/10",
      },
      {
        title: "Tasks",
        value: String(actionItems.length),
        detail: "open",
        icon: ListChecks,
        trend: actionItems.length > 0 ? "Active" : "",
        color: "text-warning bg-warning/10",
      },
    ],
    [actionItems.length, inboxRows, todayCalls, unreadEmails],
  );

  return (
    <div className="space-y-8">
      <div>
        <h2 className="text-2xl font-bold text-foreground tracking-tight">{greeting}</h2>
        <p className="text-muted-foreground mt-1">Here is your live command center snapshot.</p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {stats.map((stat) => (
          <div
            key={stat.title}
            className="group relative overflow-hidden rounded-xl border border-border bg-card p-5 transition-colors hover:border-primary/20"
          >
            <div className="flex items-center justify-between">
              <p className="text-sm font-medium text-muted-foreground">{stat.title}</p>
              <div className={cn("rounded-lg p-2", stat.color)}>
                <stat.icon className="h-4 w-4" />
              </div>
            </div>
            <div className="mt-3 flex items-end gap-2">
              <span className="text-3xl font-bold text-foreground tracking-tight">{stat.value}</span>
              <span className="mb-1 text-sm text-muted-foreground">{stat.detail}</span>
            </div>
            {stat.trend && (
              <div className="mt-2 flex items-center gap-1 text-xs text-success">
                <TrendingUp className="h-3 w-3" />
                {stat.trend}
              </div>
            )}
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 rounded-xl border border-border bg-card">
          <div className="flex items-center justify-between p-5 border-b border-border">
            <h3 className="font-semibold text-foreground">Recent Conversations</h3>
          </div>
          <div className="divide-y divide-border">
            {inboxRows.length === 0 ? (
              <div className="px-5 py-8 text-sm text-muted-foreground">No conversations yet. Connect accounts from Settings.</div>
            ) : (
              inboxRows.map((msg) => {
                const meta = platformMeta[(msg.platform as Platform) ?? "gmail"] ?? platformMeta.gmail;
                return (
                  <div
                    key={`${msg.platform}-${msg.conversation_id}`}
                    className="flex items-start gap-3.5 px-5 py-3.5 hover:bg-secondary/40 transition-colors"
                  >
                    <div className="mt-2 flex flex-col items-center gap-1.5">
                      <span className={cn("h-2.5 w-2.5 rounded-full shrink-0", meta.dot)} title={meta.label} />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium text-foreground truncate">{msg.sender}</span>
                        <span className="text-[10px] uppercase tracking-wider text-muted-foreground">{meta.label}</span>
                      </div>
                      <p className="text-sm mt-0.5 truncate text-muted-foreground">{msg.preview || msg.subject || "(no preview)"}</p>
                    </div>
                    <div className="flex flex-col items-end gap-1 shrink-0">
                      <span className="text-[11px] text-muted-foreground whitespace-nowrap">
                        {msg.latest_received_at
                          ? formatDistanceToNow(parseISO(msg.latest_received_at), { addSuffix: true })
                          : ""}
                      </span>
                      {msg.unread_count > 0 && <span className="h-2 w-2 rounded-full bg-primary" />}
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>

        <div className="space-y-6">
          <div className="rounded-xl border border-border bg-card">
            <div className="flex items-center justify-between p-5 border-b border-border">
              <h3 className="font-semibold text-foreground">Calendar</h3>
            </div>
            <div className="p-4 space-y-3">
              {calendarRows.length === 0 ? (
                <p className="text-xs text-muted-foreground">No upcoming events in the selected window.</p>
              ) : (
                calendarRows.map((event) => (
                  <div
                    key={`${event.provider}-${event.event_id}`}
                    className="flex items-center gap-3 rounded-lg p-3 bg-secondary/40 hover:bg-secondary/60 transition-colors"
                  >
                    <div className="h-9 w-1 rounded-full shrink-0 bg-primary" />
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-foreground truncate">{event.title}</p>
                      <p className="text-xs text-muted-foreground">
                        {formatEventTime(event)} | {calcEventDuration(event)}
                      </p>
                    </div>
                    <ArrowUpRight className="h-4 w-4 text-muted-foreground shrink-0" />
                  </div>
                ))
              )}
            </div>
          </div>

          <div className="rounded-xl border border-border bg-card">
            <div className="flex items-center justify-between p-5 border-b border-border">
              <h3 className="font-semibold text-foreground">Spotify</h3>
              <Music2 className="h-4 w-4 text-green-400" />
            </div>

            <div className="p-4 space-y-3">
              {spotifyLoading ? (
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Loading player...
                </div>
              ) : spotifyConnected === false ? (
                <div className="space-y-2">
                  <p className="text-sm text-muted-foreground">Connect Spotify to control playback from Donna.</p>
                  <a
                    href={SPOTIFY_CONNECT_URL}
                    className="inline-flex items-center gap-2 h-8 px-3 rounded-lg bg-green-500/15 text-green-300 text-xs font-semibold hover:bg-green-500/25 transition-colors"
                  >
                    <Music2 className="h-3.5 w-3.5" />
                    Connect Spotify
                  </a>
                </div>
              ) : !spotifyState?.has_active_device || !spotifyState?.track ? (
                <div className="space-y-2">
                  <p className="text-sm text-muted-foreground">Spotify is connected, but no active player is available.</p>
                </div>
              ) : (
                <>
                  <div className="flex items-center gap-3">
                    {spotifyState.track.album_image_url ? (
                      <img
                        src={spotifyState.track.album_image_url}
                        alt={spotifyState.track.name}
                        className="h-12 w-12 rounded-md object-cover border border-border"
                      />
                    ) : (
                      <div className="h-12 w-12 rounded-md border border-border bg-secondary flex items-center justify-center">
                        <Music2 className="h-5 w-5 text-muted-foreground" />
                      </div>
                    )}
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-semibold text-foreground truncate">{spotifyState.track.name}</p>
                      <p className="text-xs text-muted-foreground truncate">{renderArtists(spotifyState)}</p>
                      <p className="text-[11px] text-muted-foreground truncate">
                        {spotifyState.device?.name || "Unknown device"}
                      </p>
                    </div>
                    {spotifyState.track.external_url && (
                      <a
                        href={spotifyState.track.external_url}
                        target="_blank"
                        rel="noreferrer"
                        className="text-muted-foreground hover:text-foreground"
                        title="Open in Spotify"
                      >
                        <ExternalLink className="h-4 w-4" />
                      </a>
                    )}
                  </div>

                  <div className="flex items-center justify-center gap-2">
                    <button
                      onClick={() => void runPlayerAction(() => spotifyPrevious())}
                      disabled={spotifyBusy}
                      className="h-8 w-8 rounded-full border border-border bg-secondary/50 text-muted-foreground hover:text-foreground disabled:opacity-60"
                      title="Previous"
                    >
                      <SkipBack className="h-4 w-4 mx-auto" />
                    </button>
                    <button
                      onClick={() =>
                        void runPlayerAction(() =>
                          spotifyState.is_playing ? spotifyPause() : spotifyPlay(),
                        )
                      }
                      disabled={spotifyBusy}
                      className="h-9 w-9 rounded-full bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-60"
                      title={spotifyState.is_playing ? "Pause" : "Play"}
                    >
                      {spotifyState.is_playing ? (
                        <Pause className="h-4 w-4 mx-auto" />
                      ) : (
                        <Play className="h-4 w-4 mx-auto" />
                      )}
                    </button>
                    <button
                      onClick={() => void runPlayerAction(() => spotifyNext())}
                      disabled={spotifyBusy}
                      className="h-8 w-8 rounded-full border border-border bg-secondary/50 text-muted-foreground hover:text-foreground disabled:opacity-60"
                      title="Next"
                    >
                      <SkipForward className="h-4 w-4 mx-auto" />
                    </button>
                  </div>

                  <div className="flex items-center justify-between">
                    <button
                      onClick={() => handleVolumeDelta(-10)}
                      disabled={spotifyBusy || spotifyState.device?.volume_percent === null}
                      className="h-7 px-2 rounded-md border border-border text-xs text-muted-foreground hover:text-foreground disabled:opacity-60"
                    >
                      Vol -
                    </button>
                    <span className="text-xs text-muted-foreground">
                      Volume {spotifyState.device?.volume_percent ?? "--"}%
                    </span>
                    <button
                      onClick={() => handleVolumeDelta(10)}
                      disabled={spotifyBusy || spotifyState.device?.volume_percent === null}
                      className="h-7 px-2 rounded-md border border-border text-xs text-muted-foreground hover:text-foreground disabled:opacity-60"
                    >
                      Vol +
                    </button>
                  </div>
                </>
              )}

              {spotifyError && <p className="text-xs text-destructive">{spotifyError}</p>}
            </div>
          </div>

          <div className="rounded-xl border border-border bg-card">
            <div className="flex items-center justify-between p-5 border-b border-border">
              <h3 className="font-semibold text-foreground">Top News</h3>
              <Newspaper className="h-4 w-4 text-orange-400" />
            </div>
            <div className="p-4 space-y-2">
              {newsRows.length === 0 ? (
                <p className="text-xs text-muted-foreground">No stories yet. Open News and run Fetch to populate.</p>
              ) : (
                newsRows.map((article) => (
                  <a
                    key={article.id}
                    href={article.url}
                    target="_blank"
                    rel="noreferrer"
                    className="block rounded-lg border border-border/60 bg-secondary/20 p-3 hover:border-primary/40"
                  >
                    <p className="text-xs text-primary uppercase tracking-wide">{article.source}</p>
                    <p className="text-sm text-foreground mt-1 line-clamp-2">{article.title}</p>
                    {article.summary && (
                      <p className="text-xs text-muted-foreground mt-1 line-clamp-2">{article.summary}</p>
                    )}
                  </a>
                ))
              )}
            </div>
          </div>

          <div className="rounded-xl border border-border bg-card">
            <div className="flex items-center justify-between p-5 border-b border-border">
              <h3 className="font-semibold text-foreground">Daily Briefing</h3>
            </div>
            <div className="p-4 space-y-3">
              {digest ? (
                <>
                  <p className="text-xs text-muted-foreground">{digest.summary}</p>
                  {digest.top_items.slice(0, 3).map((item, idx) => (
                    <div key={`${item.title}-${idx}`} className="rounded-lg border border-border/60 bg-secondary/20 p-3">
                      <p className="text-xs text-primary uppercase tracking-wide">{item.source}</p>
                      <p className="text-sm text-foreground mt-1 line-clamp-2">{item.title}</p>
                    </div>
                  ))}
                </>
              ) : (
                <p className="text-xs text-muted-foreground">Daily digest will appear after first sync.</p>
              )}
              {teamsPresence && (
                <p className="text-xs text-muted-foreground">
                  Teams presence: <span className="text-foreground">{teamsPresence.availability}</span> ({teamsPresence.activity})
                </p>
              )}
            </div>
          </div>

          <div className="rounded-xl border border-border bg-card">
            <div className="flex items-center justify-between p-5 border-b border-border">
              <h3 className="font-semibold text-foreground">Action Items</h3>
              <ListChecks className="h-4 w-4 text-warning" />
            </div>
            <div className="p-4 space-y-2">
              {actionItems.length === 0 ? (
                <p className="text-xs text-muted-foreground">No open items yet. AI extraction will populate this list.</p>
              ) : (
                actionItems.map((item) => (
                  <div key={item.id} className="rounded-lg border border-border/60 bg-secondary/20 p-3">
                    <p className="text-sm text-foreground line-clamp-2">{item.title}</p>
                    <p className="text-[11px] text-muted-foreground mt-1 uppercase tracking-wide">
                      {item.priority} priority - {item.source_platform}
                    </p>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
