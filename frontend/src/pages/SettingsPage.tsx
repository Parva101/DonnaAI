import { FormEvent, useState, useEffect } from "react";
import { useSearchParams } from "react-router";
import {
  Settings,
  User,
  Link2,
  Bell,
  Palette,
  Shield,
  Mail,
  MessageSquare,
  Phone,
  Calendar,
  Music,
  Newspaper,
  CheckCircle2,
  Plus,
  Trash2,
  type LucideIcon,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/stores/authStore";
import {
  devLogin,
  ApiError,
  listConnectedAccounts,
  deleteConnectedAccount,
  GOOGLE_CONNECT_URL,
} from "@/lib/api";
import type { ConnectedAccount } from "@/types";

type PlatformConfig = {
  name: string;
  desc: string;
  icon: LucideIcon;
  provider: string; // maps to connected_accounts.provider
  color: string;
  connectUrl?: string; // OAuth URL if available
};

const platforms: PlatformConfig[] = [
  { name: "Gmail", desc: "Email with smart tabs", icon: Mail, provider: "google", color: "text-red-400", connectUrl: GOOGLE_CONNECT_URL },
  { name: "Outlook", desc: "Email + Calendar", icon: Mail, provider: "microsoft", color: "text-blue-400" },
  { name: "Slack", desc: "Messages & channels", icon: MessageSquare, provider: "slack", color: "text-green-400" },
  { name: "Teams", desc: "Microsoft Teams chat", icon: MessageSquare, provider: "teams", color: "text-violet-400" },
  { name: "WhatsApp", desc: "Personal number bridge", icon: Phone, provider: "whatsapp", color: "text-emerald-400" },
  { name: "Google Calendar", desc: "Events & scheduling", icon: Calendar, provider: "google_calendar", color: "text-blue-400" },
  { name: "Spotify", desc: "Music playback control", icon: Music, provider: "spotify", color: "text-green-400" },
  { name: "News Sources", desc: "RSS, NewsAPI, Hacker News", icon: Newspaper, provider: "news", color: "text-orange-400" },
];

const settingSections = [
  { icon: User, label: "Profile" },
  { icon: Link2, label: "Connections" },
  { icon: Bell, label: "Notifications" },
  { icon: Palette, label: "Appearance" },
  { icon: Shield, label: "Security" },
];

export function SettingsPage() {
  const user = useAuthStore((s) => s.user);
  const setUser = useAuthStore((s) => s.setUser);
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeSection, setActiveSection] = useState("Connections");
  const [connectedAccounts, setConnectedAccounts] = useState<ConnectedAccount[]>([]);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  const [searchParams] = useSearchParams();

  // Load connected accounts when user is authenticated
  useEffect(() => {
    if (user) {
      listConnectedAccounts()
        .then(setConnectedAccounts)
        .catch(() => {});
    }
  }, [user]);

  // Show success message from OAuth redirect
  useEffect(() => {
    const connected = searchParams.get("connected");
    if (connected) {
      setSuccessMsg(`Successfully connected ${connected}!`);
      // Refresh account list
      if (user) {
        listConnectedAccounts()
          .then(setConnectedAccounts)
          .catch(() => {});
      }
      const t = setTimeout(() => setSuccessMsg(null), 5000);
      return () => clearTimeout(t);
    }
  }, [searchParams, user]);

  const isProviderConnected = (provider: string) =>
    connectedAccounts.some((a) => a.provider === provider);

  const getAccountsForProvider = (provider: string) =>
    connectedAccounts.filter((a) => a.provider === provider);

  const handleDisconnect = async (accountId: string) => {
    try {
      await deleteConnectedAccount(accountId);
      setConnectedAccounts((prev) => prev.filter((a) => a.id !== accountId));
    } catch {
      setError("Failed to disconnect account.");
    }
  };

  const handleDevLogin = async (e: FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);
    setError(null);
    try {
      const session = await devLogin({ email, full_name: name });
      setUser(session.user);
      setEmail("");
      setName("");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to sign in.");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
        {/* Left nav */}
        <div className="lg:col-span-1">
          <nav className="rounded-xl border border-border bg-card p-2 space-y-0.5">
            {settingSections.map((section) => (
              <button
                key={section.label}
                onClick={() => setActiveSection(section.label)}
                className={cn(
                  "flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors",
                  activeSection === section.label
                    ? "bg-primary/10 text-primary"
                    : "text-muted-foreground hover:text-foreground hover:bg-secondary",
                )}
              >
                <section.icon className="h-4 w-4" />
                {section.label}
              </button>
            ))}
          </nav>
        </div>

        {/* Right content */}
        <div className="lg:col-span-3 space-y-6">
          {/* Dev auth panel (if not logged in) */}
          {!user && (
            <div className="rounded-xl border border-primary/20 bg-primary/[0.03] p-6">
              <h3 className="font-semibold text-foreground mb-1">
                Development Sign In
              </h3>
              <p className="text-sm text-muted-foreground mb-4">
                Temporary auth for development. Will be replaced by Google OAuth.
              </p>
              <form onSubmit={handleDevLogin} className="flex flex-col sm:flex-row gap-3">
                <input
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="your@email.com"
                  className="h-10 flex-1 rounded-lg border border-border bg-card px-4 text-sm text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary/30"
                />
                <input
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="Your name"
                  className="h-10 flex-1 rounded-lg border border-border bg-card px-4 text-sm text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary/30"
                />
                <button
                  type="submit"
                  disabled={isSubmitting}
                  className="h-10 px-5 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 disabled:opacity-50 transition-colors whitespace-nowrap"
                >
                  {isSubmitting ? "Signing in..." : "Dev Sign In"}
                </button>
              </form>
              {error && <p className="text-sm text-destructive mt-2">{error}</p>}
            </div>
          )}

          {/* Profile card (if logged in) */}
          {user && (
            <div className="rounded-xl border border-border bg-card p-6">
              <h3 className="font-semibold text-foreground mb-4">Profile</h3>
              <div className="flex items-center gap-4">
                <div className="flex h-14 w-14 items-center justify-center rounded-full bg-primary/20 text-primary text-lg font-semibold">
                  {(user.full_name || user.email).split(" ").map(n => n[0]).join("").slice(0, 2).toUpperCase()}
                </div>
                <div>
                  <p className="text-sm font-semibold text-foreground">
                    {user.full_name || "User"}
                  </p>
                  <p className="text-sm text-muted-foreground">{user.email}</p>
                </div>
              </div>
            </div>
          )}

          {/* Success banner */}
          {successMsg && (
            <div className="rounded-xl border border-green-500/20 bg-green-500/[0.05] px-5 py-3 text-sm text-green-400 flex items-center gap-2">
              <CheckCircle2 className="h-4 w-4" />
              {successMsg}
            </div>
          )}

          {/* Connected Platforms */}
          <div className="rounded-xl border border-border bg-card">
            <div className="p-5 border-b border-border">
              <h3 className="font-semibold text-foreground">
                Connected Platforms
              </h3>
              <p className="text-sm text-muted-foreground mt-0.5">
                Link your accounts to start seeing messages in Donna
              </p>
            </div>
            <div className="divide-y divide-border">
              {platforms.map((p) => {
                const providerAccounts = getAccountsForProvider(p.provider);
                const connected = providerAccounts.length > 0;
                return (
                  <div key={p.name} className="px-5 py-4 space-y-3">
                    <div className="flex items-center gap-4">
                      <div className={cn("flex h-10 w-10 items-center justify-center rounded-lg bg-secondary shrink-0", p.color)}>
                        <p.icon className="h-5 w-5" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-foreground">
                          {p.name}
                        </p>
                        <p className="text-xs text-muted-foreground">
                          {connected
                            ? `${providerAccounts.length} account${providerAccounts.length > 1 ? "s" : ""} connected`
                            : p.desc}
                        </p>
                      </div>
                      {!connected && p.connectUrl ? (
                        <a
                          href={p.connectUrl}
                          className="flex items-center gap-1.5 h-8 px-3 rounded-lg border border-border text-xs font-medium text-muted-foreground hover:text-foreground hover:bg-secondary transition-colors"
                        >
                          <Plus className="h-3.5 w-3.5" />
                          Connect
                        </a>
                      ) : !connected ? (
                        <button
                          disabled
                          className="flex items-center gap-1.5 h-8 px-3 rounded-lg border border-border text-xs font-medium text-muted-foreground opacity-40 cursor-not-allowed"
                        >
                          <Plus className="h-3.5 w-3.5" />
                          Soon
                        </button>
                      ) : null}
                    </div>
                    {/* List each connected account */}
                    {providerAccounts.map((account) => {
                      const needsGmailScopes = p.provider === "google" && account.scopes && !account.scopes.includes("gmail");
                      return (
                        <div
                          key={account.id}
                          className="flex items-center gap-3 ml-14 rounded-lg border border-border/50 bg-secondary/30 px-3 py-2"
                        >
                          <div className="flex-1 min-w-0">
                            <p className="text-sm text-foreground truncate">
                              {account.account_email || "Unknown email"}
                            </p>
                            {needsGmailScopes && (
                              <p className="text-[11px] text-amber-400 mt-0.5">
                                ⚠ Gmail access not granted
                              </p>
                            )}
                          </div>
                          <div className="flex items-center gap-2 shrink-0">
                            {needsGmailScopes && p.connectUrl ? (
                              <a
                                href={p.connectUrl}
                                className="flex items-center gap-1.5 h-7 px-2 rounded-md bg-amber-500/10 border border-amber-500/20 text-xs font-medium text-amber-400 hover:bg-amber-500/20 transition-colors"
                              >
                                <Mail className="h-3 w-3" />
                                Grant Access
                              </a>
                            ) : (
                              <span className="flex items-center gap-1 text-xs text-green-400 font-medium">
                                <CheckCircle2 className="h-3 w-3" />
                                OK
                              </span>
                            )}
                            <button
                              onClick={() => handleDisconnect(account.id)}
                              className="flex items-center gap-1 h-7 px-2 rounded-md text-xs text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-colors"
                              title="Disconnect"
                            >
                              <Trash2 className="h-3 w-3" />
                            </button>
                          </div>
                        </div>
                      );
                    })}
                    {/* Add another account button */}
                    {connected && p.connectUrl && (
                      <a
                        href={p.connectUrl}
                        className="flex items-center gap-1.5 ml-14 h-7 px-3 w-fit rounded-md border border-dashed border-border text-xs font-medium text-muted-foreground hover:text-foreground hover:bg-secondary transition-colors"
                      >
                        <Plus className="h-3 w-3" />
                        Add another account
                      </a>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
