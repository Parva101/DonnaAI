import { NavLink, useLocation } from "react-router";
import {
  LayoutDashboard,
  Inbox,
  Mail,
  Phone,
  Calendar,
  Newspaper,
  Settings,
  Bot,
  LogOut,
} from "lucide-react";
import { cn, getInitials } from "@/lib/utils";
import { useAuthStore } from "@/stores/authStore";
import { logout } from "@/lib/api";

const mainNav = [
  { icon: LayoutDashboard, label: "Dashboard", to: "/" },
  { icon: Inbox, label: "Inbox", to: "/inbox", badge: 12 },
  { icon: Mail, label: "Email", to: "/email", badge: 3 },
  { icon: Phone, label: "Voice", to: "/voice" },
  { icon: Calendar, label: "Calendar", to: "/calendar" },
  { icon: Newspaper, label: "News", to: "/news" },
];

const bottomNav = [{ icon: Settings, label: "Settings", to: "/settings" }];

export function Sidebar() {
  const location = useLocation();
  const user = useAuthStore((s) => s.user);
  const setUser = useAuthStore((s) => s.setUser);

  const handleLogout = async () => {
    try {
      await logout();
    } catch {
      // ignore
    }
    setUser(null);
  };

  return (
    <aside className="fixed inset-y-0 left-0 z-40 flex w-[240px] flex-col bg-sidebar border-r border-border">
      {/* Logo */}
      <div className="flex h-16 items-center gap-2.5 px-5 border-b border-border">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary">
          <Bot className="h-4.5 w-4.5 text-primary-foreground" />
        </div>
        <span className="text-[15px] font-semibold tracking-tight text-foreground">
          Donna AI
        </span>
      </div>

      {/* Main navigation */}
      <nav className="flex-1 overflow-y-auto px-3 py-4 space-y-1">
        {mainNav.map((item) => {
          const isActive =
            item.to === "/"
              ? location.pathname === "/"
              : location.pathname.startsWith(item.to);

          return (
            <NavLink
              key={item.to}
              to={item.to}
              className={cn(
                "group flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                isActive
                  ? "bg-sidebar-active text-primary"
                  : "text-sidebar-foreground hover:bg-sidebar-hover hover:text-foreground",
              )}
            >
              <item.icon
                className={cn(
                  "h-[18px] w-[18px] shrink-0",
                  isActive ? "text-primary" : "text-sidebar-foreground group-hover:text-foreground",
                )}
              />
              <span className="truncate">{item.label}</span>
              {item.badge ? (
                <span
                  className={cn(
                    "ml-auto inline-flex h-5 min-w-5 items-center justify-center rounded-full px-1.5 text-[11px] font-semibold",
                    isActive
                      ? "bg-primary text-primary-foreground"
                      : "bg-muted text-muted-foreground",
                  )}
                >
                  {item.badge}
                </span>
              ) : null}
            </NavLink>
          );
        })}
      </nav>

      {/* Bottom section */}
      <div className="border-t border-border px-3 py-3 space-y-1">
        {bottomNav.map((item) => {
          const isActive = location.pathname.startsWith(item.to);
          return (
            <NavLink
              key={item.to}
              to={item.to}
              className={cn(
                "group flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                isActive
                  ? "bg-sidebar-active text-primary"
                  : "text-sidebar-foreground hover:bg-sidebar-hover hover:text-foreground",
              )}
            >
              <item.icon className="h-[18px] w-[18px] shrink-0" />
              <span>{item.label}</span>
            </NavLink>
          );
        })}
      </div>

      {/* User section */}
      <div className="border-t border-border p-3">
        {user ? (
          <div className="flex items-center gap-3 rounded-lg px-2 py-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-full bg-primary/20 text-primary text-xs font-semibold">
              {getInitials(user.full_name || user.email)}
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-foreground truncate">
                {user.full_name || "User"}
              </p>
              <p className="text-[11px] text-muted-foreground truncate">
                {user.email}
              </p>
            </div>
            <button
              onClick={handleLogout}
              className="p-1 rounded-md text-muted-foreground hover:text-foreground hover:bg-sidebar-hover transition-colors"
              title="Sign out"
            >
              <LogOut className="h-4 w-4" />
            </button>
          </div>
        ) : (
          <NavLink
            to="/settings"
            className="flex items-center gap-3 rounded-lg px-3 py-2 text-sm text-muted-foreground hover:text-foreground hover:bg-sidebar-hover transition-colors"
          >
            <div className="flex h-8 w-8 items-center justify-center rounded-full bg-muted text-muted-foreground text-xs">
              ?
            </div>
            <span>Sign in</span>
          </NavLink>
        )}
      </div>
    </aside>
  );
}
