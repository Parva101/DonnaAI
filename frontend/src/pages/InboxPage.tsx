import { useCallback, useEffect, useMemo, useState } from "react";
import { Inbox, Loader2, RefreshCw, Search } from "lucide-react";
import { formatDistanceToNow } from "date-fns";

import { listInboxConversations } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { InboxConversationSummary, InboxPlatformCount } from "@/types";

type Platform = "gmail" | "slack" | "whatsapp" | "teams";
type PlatformFilter = "all" | Platform;

const platformMeta: Record<Platform, { dot: string; label: string }> = {
  gmail: { dot: "bg-red-400", label: "Gmail" },
  slack: { dot: "bg-green-500", label: "Slack" },
  whatsapp: { dot: "bg-emerald-400", label: "WhatsApp" },
  teams: { dot: "bg-violet-400", label: "Teams" },
};

const filters: { label: string; platform: PlatformFilter }[] = [
  { label: "All", platform: "all" },
  { label: "Gmail", platform: "gmail" },
  { label: "Slack", platform: "slack" },
  { label: "WhatsApp", platform: "whatsapp" },
  { label: "Teams", platform: "teams" },
];

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "??";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return `${parts[0][0] ?? ""}${parts[1][0] ?? ""}`.toUpperCase();
}

export function InboxPage() {
  const [activePlatform, setActivePlatform] = useState<PlatformFilter>("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [conversations, setConversations] = useState<InboxConversationSummary[]>([]);
  const [platformCounts, setPlatformCounts] = useState<InboxPlatformCount[]>([]);
  const [total, setTotal] = useState(0);

  const fetchConversations = useCallback(async () => {
    setIsLoading(true);
    try {
      const res = await listInboxConversations({
        platform: activePlatform !== "all" ? activePlatform : undefined,
        search: searchQuery || undefined,
        limit: 100,
      });
      setConversations(res.conversations);
      setPlatformCounts(res.platform_counts);
      setTotal(res.total);
    } catch {
      setConversations([]);
      setPlatformCounts([]);
      setTotal(0);
    } finally {
      setIsLoading(false);
    }
  }, [activePlatform, searchQuery]);

  useEffect(() => {
    fetchConversations();
  }, [fetchConversations]);

  const handleRefresh = async () => {
    setIsRefreshing(true);
    try {
      await fetchConversations();
    } finally {
      setIsRefreshing(false);
    }
  };

  const countByPlatform = useMemo(() => {
    const map = new Map<string, InboxPlatformCount>();
    for (const item of platformCounts) map.set(item.platform, item);
    return map;
  }, [platformCounts]);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-4">
        <div className="relative flex-1 max-w-md">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <input
            type="text"
            placeholder="Search conversations..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="h-10 w-full rounded-lg border border-border bg-card pl-10 pr-4 text-sm text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary/30 transition-colors"
          />
        </div>

        <button
          onClick={handleRefresh}
          disabled={isRefreshing}
          className="flex items-center gap-2 h-10 px-4 rounded-lg border border-border bg-card text-sm text-muted-foreground hover:text-foreground hover:bg-secondary transition-colors disabled:opacity-60"
        >
          {isRefreshing ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <RefreshCw className="h-4 w-4" />
          )}
          Refresh
        </button>
      </div>

      <div className="flex gap-2 overflow-x-auto">
        {filters.map((f) => {
          const active = f.platform === activePlatform;
          const count =
            f.platform === "all"
              ? total
              : (countByPlatform.get(f.platform)?.total ?? 0);
          const meta = f.platform === "all" ? null : platformMeta[f.platform];

          return (
            <button
              key={f.label}
              onClick={() => setActivePlatform(f.platform)}
              className={cn(
                "px-3.5 py-1.5 rounded-full text-sm font-medium transition-colors whitespace-nowrap",
                active
                  ? "bg-primary text-primary-foreground"
                  : "bg-secondary text-muted-foreground hover:text-foreground hover:bg-secondary/80",
              )}
            >
              {meta && (
                <span
                  className={cn(
                    "inline-block h-2 w-2 rounded-full mr-2",
                    meta.dot,
                  )}
                />
              )}
              {f.label}
              <span className={cn("ml-1.5 text-xs", active ? "text-primary-foreground/90" : "text-muted-foreground")}>
                {count}
              </span>
            </button>
          );
        })}
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-16">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </div>
      ) : conversations.length === 0 ? (
        <div className="rounded-xl border border-border bg-card py-14 text-center text-sm text-muted-foreground">
          {activePlatform === "all"
            ? "No inbox conversations yet."
            : `No conversations for ${platformMeta[activePlatform]?.label ?? activePlatform}.`}
        </div>
      ) : (
        <div className="rounded-xl border border-border bg-card divide-y divide-border">
          {conversations.map((conv) => {
            const meta = platformMeta[(conv.platform as Platform) ?? "gmail"] ?? platformMeta.gmail;
            const unread = conv.unread_count > 0;

            return (
              <div
                key={`${conv.platform}-${conv.conversation_id}`}
                className={cn(
                  "flex items-start gap-4 px-5 py-4 transition-colors hover:bg-secondary/40",
                  unread && "bg-primary/[0.02]",
                )}
              >
                <div className="relative shrink-0">
                  <div
                    className={cn(
                      "flex h-10 w-10 items-center justify-center rounded-full text-sm font-semibold",
                      unread
                        ? "bg-primary/15 text-primary"
                        : "bg-secondary text-muted-foreground",
                    )}
                  >
                    {initials(conv.sender)}
                  </div>
                  <span
                    className={cn(
                      "absolute -bottom-0.5 -right-0.5 h-3.5 w-3.5 rounded-full border-2 border-card",
                      meta.dot,
                    )}
                    title={meta.label}
                  />
                </div>

                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span
                      className={cn(
                        "text-sm font-medium truncate",
                        unread ? "text-foreground" : "text-muted-foreground",
                      )}
                    >
                      {conv.sender}
                    </span>
                    {conv.subject && (
                      <>
                        <span className="text-muted-foreground">|</span>
                        <span className="text-sm text-muted-foreground truncate">
                          {conv.subject}
                        </span>
                      </>
                    )}
                  </div>

                  <p
                    className={cn(
                      "text-sm mt-0.5 truncate",
                      unread ? "text-foreground/80" : "text-muted-foreground",
                    )}
                  >
                    {conv.preview || "(no preview)"}
                  </p>
                </div>

                <div className="flex flex-col items-end gap-1.5 shrink-0">
                  <span className="text-[11px] text-muted-foreground whitespace-nowrap">
                    {conv.latest_received_at
                      ? formatDistanceToNow(new Date(conv.latest_received_at), {
                          addSuffix: true,
                        })
                      : ""}
                  </span>
                  {unread && (
                    <span className="flex h-5 min-w-5 items-center justify-center rounded-full bg-primary px-1.5 text-[10px] font-semibold text-primary-foreground">
                      {conv.unread_count}
                    </span>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      <div className="flex items-center justify-center gap-2 py-4 text-sm text-muted-foreground">
        <Inbox className="h-4 w-4" />
        <span>Phase 3 inbox is live on Gmail threads. More platforms will be added incrementally.</span>
      </div>
    </div>
  );
}
