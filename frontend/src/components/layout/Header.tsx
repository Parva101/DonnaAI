import { Search, Bell } from "lucide-react";
import { useLocation } from "react-router";
import { useAuthStore } from "@/stores/authStore";
import { getInitials } from "@/lib/utils";

const pageTitles: Record<string, string> = {
  "/": "Dashboard",
  "/inbox": "Inbox",
  "/email": "Email Hub",
  "/voice": "Voice Console",
  "/calendar": "Calendar",
  "/sports": "Sports Tracker",
  "/news": "News Feed",
  "/settings": "Settings",
};

export function Header() {
  const location = useLocation();
  const user = useAuthStore((s) => s.user);

  const title = pageTitles[location.pathname] ?? "Donna AI";

  return (
    <header className="sticky top-0 z-30 flex h-16 items-center justify-between border-b border-border bg-background/80 backdrop-blur-md px-6">
      <h1 className="text-lg font-semibold text-foreground">{title}</h1>

      <div className="flex items-center gap-3">
        {/* Search */}
        <div className="relative hidden md:block">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <input
            type="text"
            placeholder="Search messages, emails, contacts..."
            className="h-9 w-72 rounded-lg border border-border bg-secondary pl-9 pr-4 text-sm text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary/30 transition-colors"
          />
        </div>

        {/* Notifications */}
        <button className="relative flex h-9 w-9 items-center justify-center rounded-lg text-muted-foreground hover:bg-secondary hover:text-foreground transition-colors">
          <Bell className="h-[18px] w-[18px]" />
          <span className="absolute right-1.5 top-1.5 h-2 w-2 rounded-full bg-primary" />
        </button>

        {/* User avatar (mobile) */}
        {user && (
          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-primary/20 text-primary text-xs font-semibold lg:hidden">
            {getInitials(user.full_name || user.email)}
          </div>
        )}
      </div>
    </header>
  );
}
