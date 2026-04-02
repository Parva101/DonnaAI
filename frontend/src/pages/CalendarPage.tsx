import { useCallback, useEffect, useMemo, useState } from "react";
import { Calendar, Clock, Loader2, RefreshCw } from "lucide-react";
import { format, formatDistanceToNow } from "date-fns";

import { ApiError, listCalendarEvents, suggestCalendarSlots } from "@/lib/api";
import type { BusyBlock, CalendarEvent } from "@/types";

function dayKey(iso: string): string {
  return format(new Date(iso), "yyyy-MM-dd");
}

export function CalendarPage() {
  const [events, setEvents] = useState<CalendarEvent[]>([]);
  const [slots, setSlots] = useState<BusyBlock[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [suggesting, setSuggesting] = useState(false);

  const loadEvents = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const start = new Date();
      const end = new Date(Date.now() + 14 * 24 * 60 * 60 * 1000);
      const res = await listCalendarEvents({
        start_at: start.toISOString(),
        end_at: end.toISOString(),
      });
      setEvents(res.events);
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "Failed to load calendar events.";
      setError(message);
      setEvents([]);
    } finally {
      setLoading(false);
    }
  }, []);

  const loadSuggestedSlots = useCallback(async () => {
    setSuggesting(true);
    try {
      const now = new Date();
      const res = await suggestCalendarSlots({
        date: now.toISOString(),
        duration_minutes: 30,
        count: 5,
      });
      setSlots(res.slots);
    } catch {
      setSlots([]);
    } finally {
      setSuggesting(false);
    }
  }, []);

  useEffect(() => {
    void loadEvents();
    void loadSuggestedSlots();
  }, [loadEvents, loadSuggestedSlots]);

  const grouped = useMemo(() => {
    const map = new Map<string, CalendarEvent[]>();
    for (const event of events) {
      const key = dayKey(event.start_at);
      const list = map.get(key) ?? [];
      list.push(event);
      map.set(key, list);
    }

    const entries = Array.from(map.entries()).sort(([a], [b]) => a.localeCompare(b));
    return entries.map(([key, list]) => ({
      key,
      label: format(new Date(key), "EEE, MMM d"),
      events: list.sort((a, b) => new Date(a.start_at).getTime() - new Date(b.start_at).getTime()),
    }));
  }, [events]);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-foreground">Calendar Intelligence</h2>
          <p className="text-sm text-muted-foreground mt-0.5">
            Upcoming events and smart slot suggestions from connected calendars.
          </p>
        </div>
        <button
          onClick={() => void loadEvents()}
          className="flex items-center gap-2 h-9 px-4 rounded-lg border border-border bg-card text-sm text-muted-foreground hover:text-foreground hover:bg-secondary transition-colors"
        >
          {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
          Refresh
        </button>
      </div>

      {error && (
        <div className="rounded-xl border border-destructive/30 bg-destructive/[0.08] px-4 py-3 text-sm text-destructive">
          {error}
        </div>
      )}

      <div className="grid grid-cols-1 xl:grid-cols-[2fr,1fr] gap-4">
        <div className="rounded-xl border border-border bg-card">
          <div className="px-5 py-4 border-b border-border flex items-center justify-between">
            <h3 className="text-sm font-semibold text-foreground">Upcoming Events</h3>
            <span className="text-xs text-muted-foreground">{events.length} events</span>
          </div>
          <div className="p-4 space-y-4 max-h-[70vh] overflow-y-auto">
            {loading ? (
              <div className="flex items-center justify-center py-12">
                <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
              </div>
            ) : grouped.length === 0 ? (
              <div className="text-sm text-muted-foreground py-8 text-center">
                No upcoming events found. Connect Google Calendar in Settings if needed.
              </div>
            ) : (
              grouped.map((group) => (
                <div key={group.key} className="space-y-2">
                  <p className="text-xs uppercase tracking-wider text-muted-foreground">{group.label}</p>
                  <div className="space-y-2">
                    {group.events.map((event) => (
                      <div key={event.event_id} className="rounded-lg border border-border/60 bg-secondary/25 px-3 py-2">
                        <div className="flex items-center justify-between gap-2">
                          <p className="text-sm font-medium text-foreground truncate">{event.title}</p>
                          <span className="text-xs text-muted-foreground whitespace-nowrap">
                            {format(new Date(event.start_at), "p")} - {format(new Date(event.end_at), "p")}
                          </span>
                        </div>
                        <p className="text-xs text-muted-foreground mt-1 truncate">
                          {event.location || event.organizer || "No location"}
                        </p>
                      </div>
                    ))}
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        <div className="space-y-4">
          <div className="rounded-xl border border-border bg-card">
            <div className="px-5 py-4 border-b border-border flex items-center justify-between">
              <h3 className="text-sm font-semibold text-foreground">Suggested Slots</h3>
              <button
                onClick={() => void loadSuggestedSlots()}
                className="text-xs text-primary hover:text-primary/80"
              >
                {suggesting ? "Loading..." : "Recompute"}
              </button>
            </div>
            <div className="p-4 space-y-2">
              {slots.length === 0 ? (
                <p className="text-xs text-muted-foreground">No free slots detected in working hours.</p>
              ) : (
                slots.map((slot, idx) => (
                  <div key={`${slot.start_at}-${idx}`} className="rounded-lg border border-border/60 bg-secondary/25 px-3 py-2 text-xs">
                    <p className="text-foreground font-medium">
                      {format(new Date(slot.start_at), "EEE p")} - {format(new Date(slot.end_at), "p")}
                    </p>
                    <p className="text-muted-foreground mt-1">
                      {formatDistanceToNow(new Date(slot.start_at), { addSuffix: true })}
                    </p>
                  </div>
                ))
              )}
            </div>
          </div>

          <div className="rounded-xl border border-border bg-card p-4">
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Calendar className="h-4 w-4" />
              <span>Google Calendar sync is active through your Google connected account.</span>
            </div>
            <div className="flex items-center gap-2 text-sm text-muted-foreground mt-2">
              <Clock className="h-4 w-4" />
              <span>Slot suggestions use your real busy windows.</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
