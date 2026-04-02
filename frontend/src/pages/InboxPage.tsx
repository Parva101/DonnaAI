import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Inbox, Loader2, RefreshCw, Search, Send } from "lucide-react";
import { formatDistanceToNow } from "date-fns";

import {
  ApiError,
  listInboxConversations,
  listSlackMessages,
  listTeamsMessages,
  listWhatsAppMessages,
  sendSlackMessage,
  sendTeamsMessage,
  sendWhatsAppMessage,
} from "@/lib/api";
import { cn } from "@/lib/utils";
import type {
  InboxConversationSummary,
  InboxPlatformCount,
  SlackMessage,
  TeamsMessage,
  WhatsAppConversationMessage,
} from "@/types";

type Platform = "gmail" | "slack" | "whatsapp" | "teams";
type PlatformFilter = "all" | Platform;

type ThreadMessage = {
  id: string;
  sender: string;
  text: string;
  sent_at: string | null;
  from_me: boolean;
  has_attachments?: boolean;
};

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

function parseSlackTs(ts: string | null): string | null {
  if (!ts) return null;
  const parsed = Number(ts);
  if (Number.isNaN(parsed)) return null;
  return new Date(parsed * 1000).toISOString();
}

function asThreadMessagesFromSlack(messages: SlackMessage[]): ThreadMessage[] {
  return messages.map((item) => ({
    id: item.ts || `slack-${Math.random().toString(36).slice(2, 10)}`,
    sender: item.sender || "Slack",
    text: (item.text || "").trim() || "(no text)",
    sent_at: parseSlackTs(item.ts),
    from_me: false,
    has_attachments: item.has_attachments,
  }));
}

function asThreadMessagesFromTeams(messages: TeamsMessage[]): ThreadMessage[] {
  return messages.map((item, index) => ({
    id: item.id || `teams-${index}`,
    sender: item.sender || "Teams",
    text: (item.text || "").trim() || "(no text)",
    sent_at: item.created_at,
    from_me: item.from_me,
    has_attachments: item.has_attachments,
  }));
}

function asThreadMessagesFromWhatsApp(messages: WhatsAppConversationMessage[]): ThreadMessage[] {
  return messages.map((item, index) => ({
    id: item.message_id || `${item.timestamp || "wa"}-${index}`,
    sender: item.sender || "WhatsApp",
    text: (item.text || "").trim() || "(no text)",
    sent_at: item.received_at,
    from_me: item.from_me,
    has_attachments: (item.message_type || "").toLowerCase() !== "conversation"
      && (item.message_type || "").toLowerCase() !== "extendedtextmessage"
      && (item.message_type || "").toLowerCase() !== "",
  }));
}

export function InboxPage() {
  const [activePlatform, setActivePlatform] = useState<PlatformFilter>("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [conversations, setConversations] = useState<InboxConversationSummary[]>([]);
  const [platformCounts, setPlatformCounts] = useState<InboxPlatformCount[]>([]);

  const [selectedConversationKey, setSelectedConversationKey] = useState<string | null>(null);
  const [threadMessages, setThreadMessages] = useState<ThreadMessage[]>([]);
  const [threadLoading, setThreadLoading] = useState(false);
  const [threadError, setThreadError] = useState<string | null>(null);
  const [composerText, setComposerText] = useState("");
  const [sendBusy, setSendBusy] = useState(false);
  const fetchRequestIdRef = useRef(0);
  const threadRequestIdRef = useRef(0);

  const fetchConversations = useCallback(async () => {
    const requestId = ++fetchRequestIdRef.current;
    setIsLoading(true);
    setLoadError(null);
    try {
      const res = await listInboxConversations({
        platform: activePlatform !== "all" ? activePlatform : undefined,
        search: searchQuery || undefined,
        limit: 100,
      });
      if (requestId !== fetchRequestIdRef.current) return;
      setConversations(res.conversations);
      setPlatformCounts(res.platform_counts);
    } catch (err) {
      if (requestId !== fetchRequestIdRef.current) return;
      const message = err instanceof ApiError ? err.message : "Failed to load inbox conversations.";
      setLoadError(message);
      setConversations([]);
      setPlatformCounts([]);
    } finally {
      if (requestId !== fetchRequestIdRef.current) return;
      setIsLoading(false);
    }
  }, [activePlatform, searchQuery]);

  useEffect(() => {
    fetchConversations();
  }, [fetchConversations]);

  const selectedConversation = useMemo(() => {
    if (!selectedConversationKey) return null;
    return (
      conversations.find(
        (conv) => `${conv.platform}:${conv.conversation_id}` === selectedConversationKey,
      ) ?? null
    );
  }, [conversations, selectedConversationKey]);

  useEffect(() => {
    if (!conversations.length) {
      setSelectedConversationKey(null);
      return;
    }
    if (!selectedConversationKey) {
      setSelectedConversationKey(`${conversations[0].platform}:${conversations[0].conversation_id}`);
      return;
    }
    const exists = conversations.some(
      (conv) => `${conv.platform}:${conv.conversation_id}` === selectedConversationKey,
    );
    if (!exists) {
      setSelectedConversationKey(`${conversations[0].platform}:${conversations[0].conversation_id}`);
    }
  }, [conversations, selectedConversationKey]);

  const fetchThread = useCallback(async () => {
    const requestId = ++threadRequestIdRef.current;
    if (!selectedConversation) {
      if (requestId !== threadRequestIdRef.current) return;
      setThreadMessages([]);
      setThreadError(null);
      return;
    }

    const platform = selectedConversation.platform as Platform;
    setThreadLoading(true);
    setThreadError(null);
    try {
      if (platform === "slack") {
        const data = await listSlackMessages(selectedConversation.conversation_id, {
          account_id: selectedConversation.account_id,
          limit: 100,
        });
        if (requestId !== threadRequestIdRef.current) return;
        setThreadMessages(asThreadMessagesFromSlack(data.messages));
      } else if (platform === "teams") {
        const data = await listTeamsMessages(selectedConversation.conversation_id, {
          account_id: selectedConversation.account_id,
          limit: 100,
        });
        if (requestId !== threadRequestIdRef.current) return;
        setThreadMessages(asThreadMessagesFromTeams(data.messages));
      } else if (platform === "whatsapp") {
        const data = await listWhatsAppMessages(selectedConversation.conversation_id, {
          account_id: selectedConversation.account_id,
          limit: 150,
        });
        if (requestId !== threadRequestIdRef.current) return;
        setThreadMessages(asThreadMessagesFromWhatsApp(data.messages));
      } else {
        if (requestId !== threadRequestIdRef.current) return;
        setThreadMessages([]);
      }
    } catch (err) {
      if (requestId !== threadRequestIdRef.current) return;
      const message = err instanceof ApiError ? err.message : "Failed to load conversation messages.";
      setThreadError(message);
      setThreadMessages([]);
    } finally {
      if (requestId !== threadRequestIdRef.current) return;
      setThreadLoading(false);
    }
  }, [selectedConversation]);

  useEffect(() => {
    fetchThread();
  }, [fetchThread]);

  const handleRefresh = async () => {
    setIsRefreshing(true);
    try {
      await fetchConversations();
      await fetchThread();
    } finally {
      setIsRefreshing(false);
    }
  };

  const handleSend = async () => {
    if (!selectedConversation || !composerText.trim()) return;
    const text = composerText.trim();
    const platform = selectedConversation.platform as Platform;
    if (platform !== "slack" && platform !== "whatsapp" && platform !== "teams") return;

    setSendBusy(true);
    setThreadError(null);
    try {
      if (platform === "slack") {
        await sendSlackMessage({
          account_id: selectedConversation.account_id,
          conversation_id: selectedConversation.conversation_id,
          text,
        });
      } else if (platform === "teams") {
        await sendTeamsMessage({
          account_id: selectedConversation.account_id,
          conversation_id: selectedConversation.conversation_id,
          text,
        });
      } else {
        await sendWhatsAppMessage({
          to: selectedConversation.conversation_id,
          text,
        });
      }
      setComposerText("");
      await fetchConversations();
      await fetchThread();
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "Failed to send message.";
      setThreadError(message);
    } finally {
      setSendBusy(false);
    }
  };

  const countByPlatform = useMemo(() => {
    const map = new Map<string, InboxPlatformCount>();
    for (const item of platformCounts) map.set(item.platform, item);
    return map;
  }, [platformCounts]);
  const allCount = useMemo(
    () => platformCounts.reduce((sum, item) => sum + item.total, 0),
    [platformCounts],
  );

  const threadPlatformMeta = selectedConversation
    ? platformMeta[(selectedConversation.platform as Platform) ?? "gmail"]
    : null;
  const canSend = selectedConversation && (
    selectedConversation.platform === "slack"
    || selectedConversation.platform === "whatsapp"
    || selectedConversation.platform === "teams"
  );

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
              ? allCount
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

      {loadError && (
        <div className="rounded-lg border border-destructive/30 bg-destructive/[0.08] px-4 py-3 text-sm text-destructive">
          {loadError}
        </div>
      )}

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
        <div className="grid grid-cols-1 xl:grid-cols-[420px,1fr] gap-4">
          <div className="rounded-xl border border-border bg-card divide-y divide-border max-h-[70vh] overflow-y-auto">
            {conversations.map((conv) => {
              const convKey = `${conv.platform}:${conv.conversation_id}`;
              const meta = platformMeta[(conv.platform as Platform) ?? "gmail"] ?? platformMeta.gmail;
              const unread = conv.unread_count > 0;
              const isSelected = convKey === selectedConversationKey;

              return (
                <button
                  key={convKey}
                  onClick={() => setSelectedConversationKey(convKey)}
                  className={cn(
                    "w-full text-left flex items-start gap-4 px-5 py-4 transition-colors hover:bg-secondary/40",
                    unread && "bg-primary/[0.02]",
                    isSelected && "bg-secondary/60",
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
                </button>
              );
            })}
          </div>

          <div className="rounded-xl border border-border bg-card flex flex-col min-h-[70vh]">
            {!selectedConversation ? (
              <div className="flex-1 flex items-center justify-center text-sm text-muted-foreground">
                Select a conversation to view details.
              </div>
            ) : (
              <>
                <div className="px-5 py-4 border-b border-border">
                  <div className="flex items-center gap-2">
                    {threadPlatformMeta && (
                      <span className={cn("inline-block h-2.5 w-2.5 rounded-full", threadPlatformMeta.dot)} />
                    )}
                    <h3 className="text-sm font-semibold text-foreground">{selectedConversation.sender}</h3>
                    <span className="text-xs text-muted-foreground">
                      {threadPlatformMeta?.label ?? selectedConversation.platform}
                    </span>
                  </div>
                  <p className="text-xs text-muted-foreground mt-1 truncate">
                    {selectedConversation.subject || selectedConversation.preview || selectedConversation.conversation_id}
                  </p>
                </div>

                <div className="flex-1 overflow-y-auto p-4 space-y-3">
                  {threadLoading ? (
                    <div className="flex items-center justify-center py-10">
                      <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
                    </div>
                  ) : threadError ? (
                    <div className="rounded-lg border border-destructive/30 bg-destructive/[0.08] px-4 py-3 text-sm text-destructive">
                      {threadError}
                    </div>
                  ) : threadMessages.length === 0 ? (
                    <div className="text-sm text-muted-foreground">
                      {selectedConversation.platform === "gmail"
                        ? "Gmail thread preview is available in Email Hub. Open the Email page for full thread details."
                        : `No recent ${selectedConversation.platform} messages found for this conversation.`}
                    </div>
                  ) : (
                    threadMessages.map((msg) => (
                      <div
                        key={msg.id}
                        className={cn(
                          "max-w-[85%] rounded-lg px-3 py-2 text-sm",
                          msg.from_me
                            ? "ml-auto bg-primary text-primary-foreground"
                            : "bg-secondary text-foreground",
                        )}
                      >
                        <p className={cn("text-xs mb-1", msg.from_me ? "text-primary-foreground/80" : "text-muted-foreground")}>
                          {msg.sender}
                        </p>
                        <p className="whitespace-pre-wrap break-words">{msg.text}</p>
                        <div className={cn("mt-1.5 text-[10px]", msg.from_me ? "text-primary-foreground/80" : "text-muted-foreground")}>
                          {msg.sent_at
                            ? formatDistanceToNow(new Date(msg.sent_at), { addSuffix: true })
                            : ""}
                          {msg.has_attachments ? " • attachment" : ""}
                        </div>
                      </div>
                    ))
                  )}
                </div>

                <div className="border-t border-border p-3">
                  {canSend ? (
                    <div className="flex items-center gap-2">
                      <input
                        value={composerText}
                        onChange={(e) => setComposerText(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter" && !e.shiftKey) {
                            e.preventDefault();
                            void handleSend();
                          }
                        }}
                        placeholder={`Message on ${threadPlatformMeta?.label ?? selectedConversation.platform}`}
                        className="h-10 flex-1 rounded-lg border border-border bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary/30"
                      />
                      <button
                        onClick={() => void handleSend()}
                        disabled={sendBusy || !composerText.trim()}
                        className="h-10 px-3 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 disabled:opacity-50 transition-colors"
                        title="Send message"
                      >
                        {sendBusy ? (
                          <Loader2 className="h-4 w-4 animate-spin" />
                        ) : (
                          <Send className="h-4 w-4" />
                        )}
                      </button>
                    </div>
                  ) : (
                    <p className="text-xs text-muted-foreground">
                      Sending from inbox is currently enabled for Slack, WhatsApp, and Teams.
                    </p>
                  )}
                </div>
              </>
            )}
          </div>
        </div>
      )}

      <div className="flex items-center justify-center gap-2 py-4 text-sm text-muted-foreground">
        <Inbox className="h-4 w-4" />
        <span>Inbox is live across Gmail, Slack, WhatsApp, and Teams.</span>
      </div>
    </div>
  );
}
