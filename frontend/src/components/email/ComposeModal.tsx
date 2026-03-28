import { useState, useRef, useEffect } from "react";
import { X, Send, Loader2, Minus } from "lucide-react";
import { cn } from "@/lib/utils";
import { sendEmail } from "@/lib/api";
import type { EmailFull } from "@/types";

export type ComposeMode = "new" | "reply" | "forward";

type Props = {
  mode: ComposeMode;
  /** The original email for reply/forward */
  originalEmail?: EmailFull | null;
  /** Connected account ID to send from */
  accountId: string;
  onClose: () => void;
  onSent: () => void;
};

function buildQuotedBody(email: EmailFull): string {
  const date = email.received_at
    ? new Date(email.received_at).toLocaleString()
    : "";
  const from = email.from_name
    ? `${email.from_name} <${email.from_address}>`
    : email.from_address ?? "";

  const header = `\n\n---------- ${
    email.subject ? `${email.subject}` : "Original Message"
  } ----------\nOn ${date}, ${from} wrote:\n\n`;

  return header + (email.body_text || email.snippet || "");
}

export function ComposeModal({
  mode,
  originalEmail,
  accountId,
  onClose,
  onSent,
}: Props) {
  const [to, setTo] = useState("");
  const [cc, setCc] = useState("");
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [showCc, setShowCc] = useState(false);
  const [isSending, setIsSending] = useState(false);
  const [isMinimized, setIsMinimized] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const bodyRef = useRef<HTMLTextAreaElement>(null);

  // Pre-fill based on mode
  useEffect(() => {
    if (!originalEmail) return;

    if (mode === "reply") {
      setTo(originalEmail.reply_to || originalEmail.from_address || "");
      setSubject(
        originalEmail.subject?.startsWith("Re:")
          ? originalEmail.subject
          : `Re: ${originalEmail.subject ?? ""}`
      );
      setBody(buildQuotedBody(originalEmail));
    } else if (mode === "forward") {
      setTo("");
      setSubject(
        originalEmail.subject?.startsWith("Fwd:")
          ? originalEmail.subject
          : `Fwd: ${originalEmail.subject ?? ""}`
      );
      setBody(buildQuotedBody(originalEmail));
    }
  }, [mode, originalEmail]);

  // Focus body for reply, to for forward/new
  useEffect(() => {
    const timer = setTimeout(() => {
      if (mode === "reply" && bodyRef.current) {
        bodyRef.current.focus();
        bodyRef.current.setSelectionRange(0, 0);
      }
    }, 100);
    return () => clearTimeout(timer);
  }, [mode]);

  const handleSend = async () => {
    if (!to.trim()) {
      setError("Please enter a recipient.");
      return;
    }

    setError(null);
    setIsSending(true);
    try {
      await sendEmail({
        account_id: accountId,
        to: to
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean),
        cc: cc
          ? cc
              .split(",")
              .map((s) => s.trim())
              .filter(Boolean)
          : undefined,
        subject: subject || undefined,
        body: body,
        in_reply_to: mode === "reply" ? originalEmail?.gmail_message_id ?? undefined : undefined,
        thread_id: mode === "reply" ? originalEmail?.thread_id ?? undefined : undefined,
      });
      onSent();
      onClose();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to send email.");
    } finally {
      setIsSending(false);
    }
  };

  // Keyboard shortcut: Ctrl+Enter to send
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      handleSend();
    }
  };

  const title =
    mode === "reply"
      ? "Reply"
      : mode === "forward"
        ? "Forward"
        : "New Email";

  if (isMinimized) {
    return (
      <div className="fixed bottom-0 right-6 z-50">
        <button
          onClick={() => setIsMinimized(false)}
          className="flex items-center gap-2 h-10 px-4 rounded-t-lg bg-primary text-primary-foreground text-sm font-medium shadow-xl hover:bg-primary/90 transition-colors"
        >
          {title}
          {subject && (
            <span className="text-xs text-primary-foreground/70 truncate max-w-[200px]">
              — {subject}
            </span>
          )}
        </button>
      </div>
    );
  }

  return (
    <div
      className="fixed bottom-0 right-6 w-[520px] max-w-[calc(100vw-48px)] bg-card border border-border rounded-t-xl shadow-2xl z-50 flex flex-col"
      style={{ maxHeight: "80vh" }}
      onKeyDown={handleKeyDown}
    >
      {/* Title bar */}
      <div className="flex items-center gap-2 px-4 py-2.5 bg-secondary/50 rounded-t-xl border-b border-border cursor-move">
        <span className="text-sm font-medium text-foreground flex-1">
          {title}
        </span>
        <button
          onClick={() => setIsMinimized(true)}
          className="p-1 rounded hover:bg-secondary transition-colors"
        >
          <Minus className="h-3.5 w-3.5 text-muted-foreground" />
        </button>
        <button
          onClick={onClose}
          className="p-1 rounded hover:bg-secondary transition-colors"
        >
          <X className="h-3.5 w-3.5 text-muted-foreground" />
        </button>
      </div>

      {/* Form */}
      <div className="flex-1 overflow-y-auto">
        {/* To */}
        <div className="flex items-center border-b border-border">
          <span className="text-xs text-muted-foreground pl-4 w-10">To</span>
          <input
            type="text"
            value={to}
            onChange={(e) => setTo(e.target.value)}
            placeholder="recipient@email.com"
            className="flex-1 h-9 px-2 text-sm bg-transparent text-foreground placeholder:text-muted-foreground focus:outline-none"
            autoFocus={mode !== "reply"}
          />
          {!showCc && (
            <button
              onClick={() => setShowCc(true)}
              className="text-xs text-muted-foreground hover:text-foreground px-3 transition-colors"
            >
              Cc
            </button>
          )}
        </div>

        {/* CC */}
        {showCc && (
          <div className="flex items-center border-b border-border">
            <span className="text-xs text-muted-foreground pl-4 w-10">Cc</span>
            <input
              type="text"
              value={cc}
              onChange={(e) => setCc(e.target.value)}
              placeholder="cc@email.com"
              className="flex-1 h-9 px-2 text-sm bg-transparent text-foreground placeholder:text-muted-foreground focus:outline-none"
            />
          </div>
        )}

        {/* Subject */}
        <div className="flex items-center border-b border-border">
          <span className="text-xs text-muted-foreground pl-4 w-10">Sub</span>
          <input
            type="text"
            value={subject}
            onChange={(e) => setSubject(e.target.value)}
            placeholder="Subject"
            className="flex-1 h-9 px-2 text-sm bg-transparent text-foreground placeholder:text-muted-foreground focus:outline-none"
          />
        </div>

        {/* Body */}
        <textarea
          ref={bodyRef}
          value={body}
          onChange={(e) => setBody(e.target.value)}
          placeholder="Write your message…"
          rows={12}
          className="w-full p-4 text-sm bg-transparent text-foreground placeholder:text-muted-foreground focus:outline-none resize-none"
        />
      </div>

      {/* Error */}
      {error && (
        <div className="px-4 py-2 text-xs text-red-400 bg-red-500/10 border-t border-red-500/20">
          {error}
        </div>
      )}

      {/* Bottom bar */}
      <div className="flex items-center gap-2 px-4 py-2.5 border-t border-border">
        <button
          onClick={handleSend}
          disabled={isSending}
          className="flex items-center gap-2 h-8 px-4 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 disabled:opacity-50 transition-colors"
        >
          {isSending ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <Send className="h-3.5 w-3.5" />
          )}
          {isSending ? "Sending…" : "Send"}
        </button>
        <span className="text-[10px] text-muted-foreground ml-auto">
          Ctrl+Enter to send
        </span>
      </div>
    </div>
  );
}
