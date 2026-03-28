import { useEffect, useState, useCallback } from "react";
import {
  Mail,
  Star,
  Paperclip,
  RefreshCw,
  Search,
  Loader2,
  Inbox,
  Pencil,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/stores/authStore";
import {
  listEmails,
  syncAllEmails,
  updateEmail,
  listConnectedAccounts,
  GOOGLE_CONNECT_URL,
} from "@/lib/api";
import type {
  EmailSummary,
  EmailFull,
  EmailCategoryCount,
  ConnectedAccount,
} from "@/types";
import { formatDistanceToNow } from "date-fns";
import { EmailDetailPanel } from "@/components/email/EmailDetailPanel";
import { ComposeModal, type ComposeMode } from "@/components/email/ComposeModal";

// Category display config — colors + nice labels
const CATEGORY_META: Record<string, { label: string; color: string }> = {
  work: { label: "Work", color: "text-blue-400" },
  personal: { label: "Personal", color: "text-purple-400" },
  school: { label: "School", color: "text-cyan-400" },
  finance: { label: "Finance", color: "text-green-400" },
  travel: { label: "Travel", color: "text-orange-400" },
  promotions: { label: "Promotions", color: "text-pink-400" },
  orders: { label: "Orders", color: "text-amber-400" },
  notifications: { label: "Notifications", color: "text-zinc-400" },
  uncategorized: { label: "Uncategorized", color: "text-zinc-500" },
};

function getCategoryMeta(cat: string) {
  return (
    CATEGORY_META[cat] ?? {
      label: cat.charAt(0).toUpperCase() + cat.slice(1),
      color: "text-indigo-400",
    }
  );
}

export function EmailPage() {
  const user = useAuthStore((s) => s.user);

  const [emails, setEmails] = useState<EmailSummary[]>([]);
  const [categories, setCategories] = useState<EmailCategoryCount[]>([]);
  const [accounts, setAccounts] = useState<ConnectedAccount[]>([]);
  const [total, setTotal] = useState(0);

  const [activeCategory, setActiveCategory] = useState("all");
  const [activeAccount, setActiveAccount] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [isSyncing, setIsSyncing] = useState(false);
  const [syncError, setSyncError] = useState<string | null>(null);

  // Detail panel state
  const [selectedEmailId, setSelectedEmailId] = useState<string | null>(null);

  // Compose modal state
  const [composeMode, setComposeMode] = useState<ComposeMode | null>(null);
  const [composeOriginal, setComposeOriginal] = useState<EmailFull | null>(null);

  // Load connected Google accounts
  useEffect(() => {
    listConnectedAccounts().then((accs) => {
      setAccounts(accs.filter((a) => a.provider === "google"));
    });
  }, []);

  // Fetch emails
  const fetchEmails = useCallback(async () => {
    setIsLoading(true);
    try {
      const res = await listEmails({
        category: activeCategory !== "all" ? activeCategory : undefined,
        account_id: activeAccount ?? undefined,
        search: searchQuery || undefined,
        limit: 100,
      });
      setEmails(res.emails);
      setCategories(res.categories);
      setTotal(res.total);
    } catch {
      // silently fail — no emails yet is fine
    } finally {
      setIsLoading(false);
    }
  }, [activeCategory, activeAccount, searchQuery]);

  useEffect(() => {
    if (user) fetchEmails();
  }, [user, fetchEmails]);

  // Sync emails from Gmail
  const handleSync = async () => {
    if (accounts.length === 0) return;
    setIsSyncing(true);
    setSyncError(null);
    try {
      await syncAllEmails();
      await fetchEmails();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      if (msg.includes("Gmail access not granted") || msg.includes("400")) {
        setSyncError(
          "Gmail access not granted. Go to Settings → click \"Grant Gmail Access\" on Gmail to enable email sync."
        );
      } else {
        setSyncError(`Sync failed: ${msg}`);
      }
    } finally {
      setIsSyncing(false);
    }
  };

  // Toggle star
  const handleToggleStar = async (email: EmailSummary) => {
    await updateEmail(email.id, { is_starred: !email.is_starred });
    setEmails((prev) =>
      prev.map((e) =>
        e.id === email.id ? { ...e, is_starred: !e.is_starred } : e
      )
    );
  };

  // Mark read on click + open detail panel
  const handleEmailClick = async (email: EmailSummary) => {
    if (!email.is_read) {
      await updateEmail(email.id, { is_read: true });
      setEmails((prev) =>
        prev.map((e) => (e.id === email.id ? { ...e, is_read: true } : e))
      );
    }
    setSelectedEmailId(email.id);
  };

  // Reply/Forward handlers (called from detail panel)
  const handleReply = (email: EmailFull) => {
    setComposeMode("reply");
    setComposeOriginal(email);
  };
  const handleForward = (email: EmailFull) => {
    setComposeMode("forward");
    setComposeOriginal(email);
  };

  // New compose
  const handleNewCompose = () => {
    setComposeMode("new");
    setComposeOriginal(null);
  };

  // Total across all categories
  const allCount = categories.reduce((sum, c) => sum + c.count, 0);
  const allUnread = categories.reduce((sum, c) => sum + c.unread, 0);

  // No Google accounts connected
  if (accounts.length === 0 && !isLoading) {
    return (
      <div className="flex flex-col items-center justify-center py-24 space-y-4">
        <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-primary/10">
          <Mail className="h-8 w-8 text-primary" />
        </div>
        <h2 className="text-lg font-semibold text-foreground">
          Connect Gmail to get started
        </h2>
        <p className="text-sm text-muted-foreground text-center max-w-md">
          Link your Google account with Gmail permissions to sync your emails
          and see them organized into smart categories.
        </p>
        <a
          href={GOOGLE_CONNECT_URL}
          className="mt-2 h-10 px-5 flex items-center gap-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors"
        >
          Connect Gmail
        </a>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      {/* Account selector + sync button */}
      <div className="flex items-center gap-3">
        <button
          onClick={() => setActiveAccount(null)}
          className={cn(
            "px-3 py-1.5 rounded-full text-sm font-medium transition-colors",
            !activeAccount
              ? "bg-primary text-primary-foreground"
              : "bg-secondary text-muted-foreground hover:text-foreground"
          )}
        >
          All Accounts
        </button>
        {accounts.map((acc) => (
          <button
            key={acc.id}
            onClick={() =>
              setActiveAccount(activeAccount === acc.id ? null : acc.id)
            }
            className={cn(
              "px-3 py-1.5 rounded-full text-sm font-medium transition-colors",
              activeAccount === acc.id
                ? "bg-primary text-primary-foreground"
                : "bg-secondary text-muted-foreground hover:text-foreground"
            )}
          >
            {acc.account_email ?? acc.provider}
          </button>
        ))}

        {/* Search */}
        <div className="ml-auto relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <input
            type="text"
            placeholder="Search emails…"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="h-9 w-64 rounded-lg border border-border bg-card pl-9 pr-3 text-sm text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary/30"
          />
        </div>

        {/* Sync button */}
        <button
          onClick={handleSync}
          disabled={isSyncing}
          className="flex items-center gap-2 h-9 px-4 rounded-lg bg-secondary text-foreground text-sm font-medium hover:bg-secondary/80 disabled:opacity-50 transition-colors"
        >
          {isSyncing ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <RefreshCw className="h-4 w-4" />
          )}
          {isSyncing ? "Syncing…" : "Sync"}
        </button>

        {/* Compose button */}
        <button
          onClick={handleNewCompose}
          className="flex items-center gap-2 h-9 px-4 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors"
        >
          <Pencil className="h-4 w-4" />
          Compose
        </button>
      </div>

      {/* Dynamic Smart Tabs — only show categories with content */}
      <div className="flex gap-1 border-b border-border overflow-x-auto">

      {/* Sync error banner */}
      {syncError && (
        <div className="mb-3 rounded-lg border border-amber-500/20 bg-amber-500/[0.05] px-4 py-3 text-sm text-amber-400 flex items-start gap-2">
          <span className="shrink-0 mt-0.5">⚠</span>
          <span>{syncError}</span>
        </div>
      )}
        <button
          onClick={() => setActiveCategory("all")}
          className={cn(
            "relative px-4 py-2.5 text-sm font-medium transition-colors whitespace-nowrap",
            activeCategory === "all"
              ? "text-primary"
              : "text-muted-foreground hover:text-foreground"
          )}
        >
          All
          <span
            className={cn(
              "ml-1.5 text-xs",
              activeCategory === "all"
                ? "text-primary"
                : "text-muted-foreground"
            )}
          >
            {allCount}
          </span>
          {activeCategory === "all" && (
            <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-primary rounded-full" />
          )}
        </button>

        {categories
          .filter((c) => c.count > 0)
          .map((cat) => {
            const meta = getCategoryMeta(cat.category);
            return (
              <button
                key={cat.category}
                onClick={() => setActiveCategory(cat.category)}
                className={cn(
                  "relative px-4 py-2.5 text-sm font-medium transition-colors whitespace-nowrap",
                  activeCategory === cat.category
                    ? "text-primary"
                    : "text-muted-foreground hover:text-foreground"
                )}
              >
                {meta.label}
                <span
                  className={cn(
                    "ml-1.5 text-xs",
                    activeCategory === cat.category
                      ? "text-primary"
                      : "text-muted-foreground"
                  )}
                >
                  {cat.count}
                </span>
                {cat.unread > 0 && (
                  <span className="ml-1 inline-flex h-4 min-w-4 items-center justify-center rounded-full bg-primary/20 px-1 text-[10px] font-bold text-primary">
                    {cat.unread}
                  </span>
                )}
                {activeCategory === cat.category && (
                  <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-primary rounded-full" />
                )}
              </button>
            );
          })}
      </div>

      {/* Email list */}
      {isLoading ? (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </div>
      ) : emails.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-20 space-y-3">
          <Inbox className="h-10 w-10 text-muted-foreground/40" />
          <p className="text-sm text-muted-foreground">
            {total === 0
              ? "No emails yet — click Sync to pull from Gmail"
              : "No emails in this category"}
          </p>
        </div>
      ) : (
        <div className="rounded-xl border border-border bg-card divide-y divide-border">
          {emails.map((email) => {
            const catMeta = getCategoryMeta(email.category);
            return (
              <div
                key={email.id}
                onClick={() => handleEmailClick(email)}
                className={cn(
                  "flex items-start gap-4 px-5 py-4 cursor-pointer transition-colors hover:bg-secondary/40",
                  !email.is_read && "bg-primary/[0.02]"
                )}
              >
                {/* Star */}
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    handleToggleStar(email);
                  }}
                  className="mt-0.5 shrink-0"
                >
                  <Star
                    className={cn(
                      "h-4 w-4 transition-colors",
                      email.is_starred
                        ? "fill-yellow-400 text-yellow-400"
                        : "text-muted-foreground/40 hover:text-muted-foreground"
                    )}
                  />
                </button>

                {/* Content */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span
                      className={cn(
                        "text-sm font-medium truncate",
                        !email.is_read
                          ? "text-foreground"
                          : "text-muted-foreground"
                      )}
                    >
                      {email.from_name || email.from_address || "Unknown"}
                    </span>
                    {email.has_attachments && (
                      <Paperclip className="h-3 w-3 text-muted-foreground shrink-0" />
                    )}
                    {/* Category badge */}
                    <span
                      className={cn(
                        "text-[10px] font-medium px-1.5 py-0.5 rounded bg-secondary",
                        catMeta.color
                      )}
                    >
                      {catMeta.label}
                    </span>
                  </div>
                  <p
                    className={cn(
                      "text-sm mt-0.5 truncate",
                      !email.is_read
                        ? "text-foreground"
                        : "text-muted-foreground"
                    )}
                  >
                    {email.subject || "(no subject)"}
                  </p>
                  <p className="text-xs text-muted-foreground mt-0.5 truncate">
                    {email.snippet}
                  </p>
                </div>

                {/* Time */}
                <div className="flex flex-col items-end gap-1 shrink-0">
                  <span className="text-[11px] text-muted-foreground whitespace-nowrap">
                    {email.received_at
                      ? formatDistanceToNow(new Date(email.received_at), {
                          addSuffix: true,
                        })
                      : ""}
                  </span>
                  {!email.is_read && (
                    <span className="h-2 w-2 rounded-full bg-primary" />
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Footer hint */}
      <div className="flex items-center justify-center gap-2 py-2 text-sm text-muted-foreground">
        <Mail className="h-4 w-4" />
        <span>
          Emails are auto-classified by AI into dynamic categories ·{" "}
          {categories.length} active tab{categories.length !== 1 ? "s" : ""}
        </span>
      </div>

      {/* Email Detail Panel */}
      {selectedEmailId && (
        <EmailDetailPanel
          emailId={selectedEmailId}
          onClose={() => setSelectedEmailId(null)}
          onReply={handleReply}
          onForward={handleForward}
          onEmailUpdated={fetchEmails}
        />
      )}

      {/* Compose Modal */}
      {composeMode && (
        <ComposeModal
          mode={composeMode}
          originalEmail={composeOriginal}
          accountId={activeAccount ?? accounts[0]?.id ?? ""}
          onClose={() => {
            setComposeMode(null);
            setComposeOriginal(null);
          }}
          onSent={fetchEmails}
        />
      )}
    </div>
  );
}
