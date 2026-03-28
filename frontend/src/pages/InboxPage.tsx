import { Inbox, Search, Filter } from "lucide-react";
import { cn } from "@/lib/utils";

type Platform = "slack" | "gmail" | "whatsapp" | "teams" | "outlook";

const platformMeta: Record<Platform, { dot: string; label: string }> = {
  slack: { dot: "bg-green-500", label: "Slack" },
  gmail: { dot: "bg-red-400", label: "Gmail" },
  whatsapp: { dot: "bg-emerald-400", label: "WhatsApp" },
  teams: { dot: "bg-violet-400", label: "Teams" },
  outlook: { dot: "bg-blue-400", label: "Outlook" },
};

const conversations: {
  id: string;
  platform: Platform;
  sender: string;
  subject?: string;
  preview: string;
  time: string;
  unread: boolean;
  count?: number;
}[] = [
  { id: "1", platform: "slack", sender: "John Chen", preview: "Hey, can you review the PR for the auth module? I've addressed all the comments from the last round.", time: "2 min ago", unread: true, count: 3 },
  { id: "2", platform: "gmail", sender: "Sarah Miller", subject: "Q3 Report", preview: "Hi, please find attached the Q3 report. We need to review the numbers before the board meeting.", time: "15 min ago", unread: true },
  { id: "3", platform: "whatsapp", sender: "Mom", preview: "Call me when you get a chance 💕", time: "1 hr ago", unread: false },
  { id: "4", platform: "teams", sender: "Mike Johnson", preview: "Design review meeting moved to 3pm tomorrow. Can you prep the mockups?", time: "2 hr ago", unread: false },
  { id: "5", platform: "gmail", sender: "GitHub Notifications", subject: "PR #42 approved", preview: "Your pull request 'Add user authentication' has been approved and merged.", time: "3 hr ago", unread: false },
  { id: "6", platform: "slack", sender: "Anna Lee", preview: "Great work on the demo yesterday! The client loved the voice bot feature 🎉", time: "5 hr ago", unread: false },
  { id: "7", platform: "teams", sender: "DevOps Bot", preview: "Deployment to staging successful. All health checks passed.", time: "6 hr ago", unread: false },
  { id: "8", platform: "whatsapp", sender: "David Park", preview: "Are we still on for lunch tomorrow?", time: "8 hr ago", unread: false },
];

const filters: { label: string; platform?: Platform }[] = [
  { label: "All" },
  { label: "Slack", platform: "slack" },
  { label: "Email", platform: "gmail" },
  { label: "WhatsApp", platform: "whatsapp" },
  { label: "Teams", platform: "teams" },
];

export function InboxPage() {
  return (
    <div className="space-y-6">
      {/* Top bar */}
      <div className="flex items-center justify-between gap-4">
        <div className="relative flex-1 max-w-md">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <input
            type="text"
            placeholder="Search conversations..."
            className="h-10 w-full rounded-lg border border-border bg-card pl-10 pr-4 text-sm text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary/30 transition-colors"
          />
        </div>
        <button className="flex items-center gap-2 h-10 px-4 rounded-lg border border-border bg-card text-sm text-muted-foreground hover:text-foreground hover:bg-secondary transition-colors">
          <Filter className="h-4 w-4" />
          Filter
        </button>
      </div>

      {/* Platform filters */}
      <div className="flex gap-2">
        {filters.map((f, i) => (
          <button
            key={f.label}
            className={cn(
              "px-3.5 py-1.5 rounded-full text-sm font-medium transition-colors",
              i === 0
                ? "bg-primary text-primary-foreground"
                : "bg-secondary text-muted-foreground hover:text-foreground hover:bg-secondary/80",
            )}
          >
            {f.platform && (
              <span className={cn("inline-block h-2 w-2 rounded-full mr-2", platformMeta[f.platform].dot)} />
            )}
            {f.label}
          </button>
        ))}
      </div>

      {/* Conversation list */}
      <div className="rounded-xl border border-border bg-card divide-y divide-border">
        {conversations.map((conv) => {
          const meta = platformMeta[conv.platform];
          return (
            <div
              key={conv.id}
              className={cn(
                "flex items-start gap-4 px-5 py-4 cursor-pointer transition-colors hover:bg-secondary/40",
                conv.unread && "bg-primary/[0.02]",
              )}
            >
              {/* Avatar */}
              <div className="relative shrink-0">
                <div className={cn(
                  "flex h-10 w-10 items-center justify-center rounded-full text-sm font-semibold",
                  conv.unread ? "bg-primary/15 text-primary" : "bg-secondary text-muted-foreground",
                )}>
                  {conv.sender.split(" ").map(n => n[0]).join("").slice(0, 2)}
                </div>
                <span
                  className={cn("absolute -bottom-0.5 -right-0.5 h-3.5 w-3.5 rounded-full border-2 border-card", meta.dot)}
                  title={meta.label}
                />
              </div>

              {/* Content */}
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className={cn("text-sm font-medium truncate", conv.unread ? "text-foreground" : "text-muted-foreground")}>
                    {conv.sender}
                  </span>
                  {conv.subject && (
                    <>
                      <span className="text-muted-foreground">·</span>
                      <span className="text-sm text-muted-foreground truncate">{conv.subject}</span>
                    </>
                  )}
                </div>
                <p className={cn("text-sm mt-0.5 truncate", conv.unread ? "text-foreground/70" : "text-muted-foreground")}>
                  {conv.preview}
                </p>
              </div>

              {/* Meta */}
              <div className="flex flex-col items-end gap-1.5 shrink-0">
                <span className="text-[11px] text-muted-foreground whitespace-nowrap">{conv.time}</span>
                {conv.unread && (
                  <span className="flex h-5 min-w-5 items-center justify-center rounded-full bg-primary px-1.5 text-[10px] font-semibold text-primary-foreground">
                    {conv.count || 1}
                  </span>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* Footer hint */}
      <div className="flex items-center justify-center gap-2 py-4 text-sm text-muted-foreground">
        <Inbox className="h-4 w-4" />
        <span>Connect your platforms in Settings to see real messages</span>
      </div>
    </div>
  );
}
