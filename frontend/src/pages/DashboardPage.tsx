import {
  MessageSquare,
  Mail,
  Phone,
  ListChecks,
  TrendingUp,
  ArrowUpRight,
  Clock,
  Zap,
  type LucideIcon,
} from "lucide-react";
import { cn, getGreeting } from "@/lib/utils";

// ── Mock data ──────────────────────────────────────────

const stats: {
  title: string;
  value: string;
  detail: string;
  icon: LucideIcon;
  trend?: string;
  color: string;
}[] = [
  {
    title: "Messages",
    value: "24",
    detail: "+5 today",
    icon: MessageSquare,
    trend: "+12%",
    color: "text-primary bg-primary/10",
  },
  {
    title: "Emails",
    value: "12",
    detail: "unread",
    icon: Mail,
    color: "text-purple-400 bg-purple-400/10",
  },
  {
    title: "Calls",
    value: "3",
    detail: "today",
    icon: Phone,
    color: "text-success bg-success/10",
  },
  {
    title: "Tasks",
    value: "7",
    detail: "2 urgent",
    icon: ListChecks,
    trend: "",
    color: "text-warning bg-warning/10",
  },
];

type Platform = "slack" | "gmail" | "whatsapp" | "teams" | "outlook";

const platformMeta: Record<Platform, { dot: string; label: string }> = {
  slack: { dot: "bg-green-500", label: "Slack" },
  gmail: { dot: "bg-red-400", label: "Gmail" },
  whatsapp: { dot: "bg-emerald-400", label: "WhatsApp" },
  teams: { dot: "bg-violet-400", label: "Teams" },
  outlook: { dot: "bg-blue-400", label: "Outlook" },
};

const recentMessages: {
  id: string;
  platform: Platform;
  sender: string;
  content: string;
  time: string;
  unread: boolean;
}[] = [
  {
    id: "1",
    platform: "slack",
    sender: "John Chen",
    content: "Hey, can you review the PR for the auth module?",
    time: "2 min ago",
    unread: true,
  },
  {
    id: "2",
    platform: "gmail",
    sender: "Sarah Miller",
    content: "Q3 Report is attached. Please review by EOD.",
    time: "15 min ago",
    unread: true,
  },
  {
    id: "3",
    platform: "whatsapp",
    sender: "Mom",
    content: "Call me when you get a chance 💕",
    time: "1 hr ago",
    unread: false,
  },
  {
    id: "4",
    platform: "teams",
    sender: "Mike Johnson",
    content: "Design review meeting moved to 3pm tomorrow",
    time: "2 hr ago",
    unread: false,
  },
  {
    id: "5",
    platform: "gmail",
    sender: "GitHub",
    content: "Pull request #42 has been approved and merged",
    time: "3 hr ago",
    unread: false,
  },
  {
    id: "6",
    platform: "slack",
    sender: "Anna Lee",
    content: "Great work on the demo yesterday! 🎉",
    time: "5 hr ago",
    unread: false,
  },
];

const upcomingEvents = [
  { id: "1", title: "Team Standup", time: "10:00 AM", duration: "30 min", color: "bg-primary" },
  { id: "2", title: "Design Review", time: "2:00 PM", duration: "1 hr", color: "bg-purple-500" },
  { id: "3", title: "1:1 with Mike", time: "4:30 PM", duration: "30 min", color: "bg-success" },
];

const connectPlatforms = [
  { name: "Gmail", desc: "Sync emails with smart tabs", icon: Mail, connected: false },
  { name: "Slack", desc: "Messages and channels", icon: MessageSquare, connected: false },
  { name: "Calendar", desc: "Google & Outlook calendars", icon: Clock, connected: false },
  { name: "Voice", desc: "Outbound calls via Donna", icon: Phone, connected: false },
];

// ── Component ──────────────────────────────────────────

export function DashboardPage() {
  const greeting = getGreeting();

  return (
    <div className="space-y-8">
      {/* Hero */}
      <div>
        <h2 className="text-2xl font-bold text-foreground tracking-tight">
          {greeting} 👋
        </h2>
        <p className="text-muted-foreground mt-1">
          Here's your day at a glance
        </p>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {stats.map((stat) => (
          <div
            key={stat.title}
            className="group relative overflow-hidden rounded-xl border border-border bg-card p-5 transition-colors hover:border-primary/20"
          >
            <div className="flex items-center justify-between">
              <p className="text-sm font-medium text-muted-foreground">
                {stat.title}
              </p>
              <div className={cn("rounded-lg p-2", stat.color)}>
                <stat.icon className="h-4 w-4" />
              </div>
            </div>
            <div className="mt-3 flex items-end gap-2">
              <span className="text-3xl font-bold text-foreground tracking-tight">
                {stat.value}
              </span>
              <span className="mb-1 text-sm text-muted-foreground">
                {stat.detail}
              </span>
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

      {/* Main grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Recent Messages */}
        <div className="lg:col-span-2 rounded-xl border border-border bg-card">
          <div className="flex items-center justify-between p-5 border-b border-border">
            <h3 className="font-semibold text-foreground">Recent Messages</h3>
            <button className="text-xs text-primary hover:text-primary/80 font-medium transition-colors">
              View all
            </button>
          </div>
          <div className="divide-y divide-border">
            {recentMessages.map((msg) => {
              const meta = platformMeta[msg.platform];
              return (
                <div
                  key={msg.id}
                  className="flex items-start gap-3.5 px-5 py-3.5 hover:bg-secondary/40 transition-colors cursor-pointer"
                >
                  {/* Platform dot */}
                  <div className="mt-2 flex flex-col items-center gap-1.5">
                    <span
                      className={cn("h-2.5 w-2.5 rounded-full shrink-0", meta.dot)}
                      title={meta.label}
                    />
                  </div>
                  {/* Content */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span
                        className={cn(
                          "text-sm font-medium truncate",
                          msg.unread ? "text-foreground" : "text-muted-foreground",
                        )}
                      >
                        {msg.sender}
                      </span>
                      <span className="text-[10px] uppercase tracking-wider text-muted-foreground">
                        {meta.label}
                      </span>
                    </div>
                    <p
                      className={cn(
                        "text-sm mt-0.5 truncate",
                        msg.unread ? "text-foreground/80" : "text-muted-foreground",
                      )}
                    >
                      {msg.content}
                    </p>
                  </div>
                  {/* Time + unread */}
                  <div className="flex flex-col items-end gap-1 shrink-0">
                    <span className="text-[11px] text-muted-foreground whitespace-nowrap">
                      {msg.time}
                    </span>
                    {msg.unread && (
                      <span className="h-2 w-2 rounded-full bg-primary" />
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Right column */}
        <div className="space-y-6">
          {/* Today's Schedule */}
          <div className="rounded-xl border border-border bg-card">
            <div className="flex items-center justify-between p-5 border-b border-border">
              <h3 className="font-semibold text-foreground">Today's Schedule</h3>
              <button className="text-xs text-primary hover:text-primary/80 font-medium transition-colors">
                Calendar
              </button>
            </div>
            <div className="p-4 space-y-3">
              {upcomingEvents.map((event) => (
                <div
                  key={event.id}
                  className="flex items-center gap-3 rounded-lg p-3 bg-secondary/40 hover:bg-secondary/60 transition-colors"
                >
                  <div className={cn("h-9 w-1 rounded-full shrink-0", event.color)} />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-foreground truncate">
                      {event.title}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {event.time} · {event.duration}
                    </p>
                  </div>
                  <ArrowUpRight className="h-4 w-4 text-muted-foreground shrink-0" />
                </div>
              ))}
            </div>
          </div>

          {/* Connect Platforms */}
          <div className="rounded-xl border border-border bg-card">
            <div className="flex items-center justify-between p-5 border-b border-border">
              <h3 className="font-semibold text-foreground">
                Connect Platforms
              </h3>
              <Zap className="h-4 w-4 text-warning" />
            </div>
            <div className="p-4 space-y-2">
              {connectPlatforms.map((p) => (
                <button
                  key={p.name}
                  className="flex w-full items-center gap-3 rounded-lg p-3 text-left bg-secondary/40 hover:bg-secondary/60 transition-colors group"
                >
                  <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary/10 text-primary shrink-0">
                    <p.icon className="h-4 w-4" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-foreground">
                      {p.name}
                    </p>
                    <p className="text-xs text-muted-foreground">{p.desc}</p>
                  </div>
                  <span className="text-xs text-primary opacity-0 group-hover:opacity-100 transition-opacity font-medium">
                    Connect
                  </span>
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
