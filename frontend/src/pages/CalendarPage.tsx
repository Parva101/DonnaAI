import { Calendar, Clock, Users, MapPin, Video, Plus } from "lucide-react";
import { cn } from "@/lib/utils";

const days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const currentDayIndex = 2; // Wed

const todayEvents = [
  {
    id: "1",
    title: "Team Standup",
    time: "10:00 – 10:30 AM",
    attendees: ["John C.", "Sarah M.", "Anna L."],
    location: "Google Meet",
    color: "bg-primary",
    isNow: false,
  },
  {
    id: "2",
    title: "Design Review",
    time: "2:00 – 3:00 PM",
    attendees: ["Sarah M.", "Mike J."],
    location: "Conference Room B",
    color: "bg-purple-500",
    isNow: true,
  },
  {
    id: "3",
    title: "1:1 with Mike",
    time: "4:30 – 5:00 PM",
    attendees: ["Mike J."],
    location: "Zoom",
    color: "bg-success",
    isNow: false,
  },
];

const weekEvents = [
  { day: "Thu", title: "Client Presentation", time: "11:00 AM" },
  { day: "Thu", title: "Lunch with David", time: "12:30 PM" },
  { day: "Fri", title: "Sprint Retro", time: "3:00 PM" },
  { day: "Sat", title: "Dinner at Nobu", time: "8:00 PM" },
];

export function CalendarPage() {
  return (
    <div className="space-y-6">
      {/* Week strip */}
      <div className="rounded-xl border border-border bg-card p-4">
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-semibold text-foreground">March 2026</h3>
          <button className="flex items-center gap-2 h-8 px-3 rounded-lg bg-primary text-primary-foreground text-xs font-medium hover:bg-primary/90 transition-colors">
            <Plus className="h-3.5 w-3.5" />
            New Event
          </button>
        </div>
        <div className="grid grid-cols-7 gap-2">
          {days.map((day, i) => (
            <div
              key={day}
              className={cn(
                "flex flex-col items-center gap-1 py-3 rounded-lg transition-colors cursor-pointer",
                i === currentDayIndex
                  ? "bg-primary text-primary-foreground"
                  : "hover:bg-secondary text-muted-foreground hover:text-foreground",
              )}
            >
              <span className="text-xs font-medium">{day}</span>
              <span className={cn(
                "text-lg font-semibold",
                i === currentDayIndex ? "text-primary-foreground" : "text-foreground",
              )}>
                {17 + i}
              </span>
              {i <= 3 && (
                <span className={cn(
                  "h-1 w-1 rounded-full",
                  i === currentDayIndex ? "bg-primary-foreground" : "bg-primary",
                )} />
              )}
            </div>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Today's events */}
        <div className="lg:col-span-2 space-y-4">
          <h3 className="font-semibold text-foreground">Today's Events</h3>
          <div className="space-y-3">
            {todayEvents.map((event) => (
              <div
                key={event.id}
                className={cn(
                  "rounded-xl border bg-card p-5 transition-colors hover:border-primary/20 cursor-pointer",
                  event.isNow ? "border-primary/30 bg-primary/[0.03]" : "border-border",
                )}
              >
                <div className="flex items-start gap-4">
                  <div className={cn("h-full w-1 rounded-full self-stretch min-h-[60px]", event.color)} />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <h4 className="text-sm font-semibold text-foreground">{event.title}</h4>
                      {event.isNow && (
                        <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-primary/10 text-primary">
                          Now
                        </span>
                      )}
                    </div>
                    <div className="flex flex-wrap items-center gap-3 mt-2 text-xs text-muted-foreground">
                      <span className="flex items-center gap-1">
                        <Clock className="h-3 w-3" />
                        {event.time}
                      </span>
                      <span className="flex items-center gap-1">
                        <Users className="h-3 w-3" />
                        {event.attendees.join(", ")}
                      </span>
                      <span className="flex items-center gap-1">
                        {event.location.includes("Meet") || event.location.includes("Zoom") ? (
                          <Video className="h-3 w-3" />
                        ) : (
                          <MapPin className="h-3 w-3" />
                        )}
                        {event.location}
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* This week */}
        <div>
          <h3 className="font-semibold text-foreground mb-4">This Week</h3>
          <div className="rounded-xl border border-border bg-card divide-y divide-border">
            {weekEvents.map((event, i) => (
              <div key={i} className="px-4 py-3 hover:bg-secondary/40 transition-colors cursor-pointer">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-medium text-primary w-8">{event.day}</span>
                  <span className="text-sm text-foreground">{event.title}</span>
                </div>
                <span className="text-xs text-muted-foreground ml-10">{event.time}</span>
              </div>
            ))}
          </div>

          <div className="mt-4 flex items-center justify-center gap-2 py-4 text-sm text-muted-foreground">
            <Calendar className="h-4 w-4" />
            <span>Connect Google Calendar</span>
          </div>
        </div>
      </div>
    </div>
  );
}
