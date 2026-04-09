import { FormEvent, useCallback, useEffect, useState } from "react";
import { Bot, Clock, Loader2, Phone } from "lucide-react";
import { formatDistanceToNow } from "date-fns";

import { ApiError, createVoiceCall, listVoiceCalls } from "@/lib/api";
import type { VoiceCall } from "@/types";

export function VoicePage() {
  const [intent, setIntent] = useState("");
  const [targetName, setTargetName] = useState("");
  const [targetPhone, setTargetPhone] = useState("");
  const [calls, setCalls] = useState<VoiceCall[]>([]);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadCalls = useCallback(async () => {
    setLoading(true);
    try {
      const res = await listVoiceCalls(50);
      setCalls(res.calls);
      setError(null);
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "Failed to load voice calls.";
      setError(message);
      setCalls([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadCalls();
  }, [loadCalls]);

  const handleCreate = async (e: FormEvent) => {
    e.preventDefault();
    if (!intent.trim()) return;

    setSubmitting(true);
    setError(null);
    try {
      await createVoiceCall({
        intent: intent.trim(),
        target_name: targetName.trim() || undefined,
        target_phone: targetPhone.trim() || undefined,
      });
      setIntent("");
      setTargetName("");
      setTargetPhone("");
      await loadCalls();
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "Failed to start call.";
      setError(message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="space-y-8">
      <form onSubmit={handleCreate} className="rounded-xl border border-border bg-card p-6 space-y-4">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary/10 text-primary">
            <Bot className="h-5 w-5" />
          </div>
          <div>
            <h3 className="font-semibold text-foreground">Donna Voice Calls</h3>
            <p className="text-sm text-muted-foreground">
              Capture call intent now. If LiveKit/Twilio is configured, calls can be routed externally.
            </p>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <input
            value={targetName}
            onChange={(e) => setTargetName(e.target.value)}
            placeholder="Target name (optional)"
            className="h-10 rounded-lg border border-border bg-secondary px-3 text-sm text-foreground"
          />
          <input
            value={targetPhone}
            onChange={(e) => setTargetPhone(e.target.value)}
            placeholder="Phone number (optional)"
            className="h-10 rounded-lg border border-border bg-secondary px-3 text-sm text-foreground"
          />
        </div>

        <textarea
          value={intent}
          onChange={(e) => setIntent(e.target.value)}
          placeholder="Example: Book a table for 4 at Nobu this Saturday at 8pm"
          className="w-full h-28 rounded-lg border border-border bg-secondary p-4 text-sm text-foreground resize-none"
        />

        <div className="flex items-center gap-3">
          <button
            type="submit"
            disabled={submitting || !intent.trim()}
            className="flex items-center gap-2 h-10 px-5 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 disabled:opacity-50"
          >
            {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Phone className="h-4 w-4" />}
            Start Call
          </button>
          <button
            type="button"
            onClick={() => void loadCalls()}
            className="h-10 px-4 rounded-lg border border-border text-sm text-muted-foreground hover:text-foreground"
          >
            Refresh
          </button>
        </div>

        {error && (
          <div className="rounded-lg border border-destructive/30 bg-destructive/[0.08] px-4 py-3 text-sm text-destructive">
            {error}
          </div>
        )}
      </form>

      <div className="rounded-xl border border-border bg-card">
        <div className="flex items-center justify-between p-5 border-b border-border">
          <h3 className="font-semibold text-foreground">Recent Calls</h3>
          <span className="text-xs text-muted-foreground">{calls.length} calls</span>
        </div>

        <div className="divide-y divide-border">
          {loading ? (
            <div className="py-10 flex justify-center">
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
            </div>
          ) : calls.length === 0 ? (
            <div className="py-10 text-center text-sm text-muted-foreground">No calls yet.</div>
          ) : (
            calls.map((call) => (
              <div key={call.id} className="px-5 py-4">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="text-sm font-medium text-foreground">
                      {call.target_name || call.target_phone || "Voice Call"}
                    </p>
                    <p className="text-xs text-muted-foreground mt-0.5">{call.intent}</p>
                  </div>
                  <span className="text-xs text-primary uppercase tracking-wide">{call.status}</span>
                </div>
                <div className="mt-2 text-xs text-muted-foreground space-y-1">
                  {call.summary && <p>{call.summary}</p>}
                  {call.outcome && <p>{call.outcome}</p>}
                  <p className="flex items-center gap-1">
                    <Clock className="h-3 w-3" />
                    {call.created_at
                      ? formatDistanceToNow(new Date(call.created_at), { addSuffix: true })
                      : "recent"}
                  </p>
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
