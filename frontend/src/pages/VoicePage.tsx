import { Phone, Mic, MicOff, PhoneOff, Clock, ArrowUpRight, Bot } from "lucide-react";
import { cn } from "@/lib/utils";

const recentCalls = [
  {
    id: "1",
    business: "Nobu Restaurant",
    number: "+1-212-757-3000",
    purpose: "Reserve table for 4 on Saturday at 8pm",
    status: "success" as const,
    outcome: "Booked! Table for 4, Saturday 8pm. Confirmation #42.",
    time: "Today, 10:23 AM",
    duration: "2:34",
  },
  {
    id: "2",
    business: "Dr. Smith's Office",
    number: "+1-310-555-0123",
    purpose: "Schedule annual checkup",
    status: "partial" as const,
    outcome: "Available: March 25 at 2pm or March 28 at 10am. Which one?",
    time: "Yesterday, 3:15 PM",
    duration: "1:48",
  },
  {
    id: "3",
    business: "The Ritz-Carlton",
    number: "+1-800-542-8680",
    purpose: "Book suite for April 5-7",
    status: "failed" as const,
    outcome: "Went to voicemail. Want me to try again?",
    time: "Yesterday, 11:02 AM",
    duration: "0:22",
  },
];

const statusConfig = {
  success: { label: "Booked", color: "text-success bg-success/10" },
  partial: { label: "Pending", color: "text-warning bg-warning/10" },
  failed: { label: "Failed", color: "text-destructive bg-destructive/10" },
};

export function VoicePage() {
  return (
    <div className="space-y-8">
      {/* Call initiation */}
      <div className="rounded-xl border border-border bg-card p-6">
        <div className="flex items-center gap-3 mb-4">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary/10 text-primary">
            <Bot className="h-5 w-5" />
          </div>
          <div>
            <h3 className="font-semibold text-foreground">
              Make a call with Donna
            </h3>
            <p className="text-sm text-muted-foreground">
              Tell Donna what you need and she'll handle the call
            </p>
          </div>
        </div>

        <textarea
          placeholder={`"Reserve a table for 4 at Nobu on Saturday at 8pm"\n"Call Dr. Smith's office and schedule my annual checkup"\n"Book a hotel room at The Ritz for April 5-7"`}
          className="w-full h-28 rounded-lg border border-border bg-secondary p-4 text-sm text-foreground placeholder:text-muted-foreground resize-none focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary/30 transition-colors"
        />

        <div className="flex items-center gap-3 mt-4">
          <button className="flex items-center gap-2 h-10 px-5 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors">
            <Phone className="h-4 w-4" />
            Start Call
          </button>
          <span className="text-xs text-muted-foreground">
            Donna will look up the phone number and call on your behalf
          </span>
        </div>
      </div>

      {/* Active call panel (empty state) */}
      <div className="rounded-xl border border-dashed border-border bg-card/50 p-12 flex flex-col items-center justify-center gap-4">
        <div className="flex h-16 w-16 items-center justify-center rounded-full bg-secondary">
          <Phone className="h-7 w-7 text-muted-foreground" />
        </div>
        <div className="text-center">
          <p className="text-sm font-medium text-muted-foreground">
            No active call
          </p>
          <p className="text-xs text-muted-foreground mt-1">
            Start a call above and the live transcript will appear here
          </p>
        </div>
      </div>

      {/* Recent Calls */}
      <div className="rounded-xl border border-border bg-card">
        <div className="flex items-center justify-between p-5 border-b border-border">
          <h3 className="font-semibold text-foreground">Recent Calls</h3>
          <span className="text-xs text-muted-foreground">
            {recentCalls.length} calls
          </span>
        </div>
        <div className="divide-y divide-border">
          {recentCalls.map((call) => {
            const status = statusConfig[call.status];
            return (
              <div
                key={call.id}
                className="px-5 py-4 hover:bg-secondary/40 transition-colors cursor-pointer"
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium text-foreground">
                        {call.business}
                      </span>
                      <span className={cn("px-2 py-0.5 rounded-full text-[10px] font-semibold", status.color)}>
                        {status.label}
                      </span>
                    </div>
                    <p className="text-sm text-muted-foreground mt-0.5">
                      {call.purpose}
                    </p>
                    <p className="text-sm text-foreground/70 mt-1.5">
                      → {call.outcome}
                    </p>
                  </div>
                  <div className="flex flex-col items-end gap-1 shrink-0">
                    <span className="text-[11px] text-muted-foreground">
                      {call.time}
                    </span>
                    <span className="flex items-center gap-1 text-[11px] text-muted-foreground">
                      <Clock className="h-3 w-3" />
                      {call.duration}
                    </span>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
