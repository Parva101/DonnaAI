import { useEffect, useRef, useState } from "react";
import {
  X,
  Star,
  Reply,
  Forward,
  Tag,
  Paperclip,
  ChevronDown,
  ExternalLink,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { getEmail, updateEmail } from "@/lib/api";
import type { EmailFull } from "@/types";
import { formatDistanceToNow, format } from "date-fns";

// Category display config
const CATEGORY_META: Record<string, { label: string; color: string }> = {
  work: { label: "Work", color: "bg-blue-500/20 text-blue-400" },
  personal: { label: "Personal", color: "bg-purple-500/20 text-purple-400" },
  school: { label: "School", color: "bg-cyan-500/20 text-cyan-400" },
  finance: { label: "Finance", color: "bg-green-500/20 text-green-400" },
  travel: { label: "Travel", color: "bg-orange-500/20 text-orange-400" },
  promotions: { label: "Promotions", color: "bg-pink-500/20 text-pink-400" },
  newsletters: { label: "Newsletters", color: "bg-indigo-500/20 text-indigo-400" },
  orders: { label: "Orders", color: "bg-amber-500/20 text-amber-400" },
  notifications: {
    label: "Notifications",
    color: "bg-zinc-500/20 text-zinc-400",
  },
  uncategorized: {
    label: "Uncategorized",
    color: "bg-zinc-500/20 text-zinc-500",
  },
};

const ALL_CATEGORIES = [
  "work",
  "personal",
  "school",
  "finance",
  "travel",
  "promotions",
  "newsletters",
  "orders",
  "notifications",
];

function getCategoryMeta(cat: string) {
  return (
    CATEGORY_META[cat] ?? {
      label: cat.charAt(0).toUpperCase() + cat.slice(1),
      color: "bg-indigo-500/20 text-indigo-400",
    }
  );
}

type Props = {
  emailId: string;
  onClose: () => void;
  onReply: (email: EmailFull) => void;
  onForward: (email: EmailFull) => void;
  onEmailUpdated: () => void;
};

export function EmailDetailPanel({
  emailId,
  onClose,
  onReply,
  onForward,
  onEmailUpdated,
}: Props) {
  const [email, setEmail] = useState<EmailFull | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [showCategoryMenu, setShowCategoryMenu] = useState(false);
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const categoryMenuRef = useRef<HTMLDivElement>(null);

  // Fetch full email
  useEffect(() => {
    setIsLoading(true);
    getEmail(emailId)
      .then((data) => setEmail(data))
      .catch(() => {})
      .finally(() => setIsLoading(false));
  }, [emailId]);

  // Close category menu on outside click
  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (
        categoryMenuRef.current &&
        !categoryMenuRef.current.contains(e.target as Node)
      ) {
        setShowCategoryMenu(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  // Write HTML body into sandboxed iframe
  useEffect(() => {
    if (!email?.body_html || !iframeRef.current) return;
    const doc = iframeRef.current.contentDocument;
    if (!doc) return;
    doc.open();
    doc.write(`
      <!DOCTYPE html>
      <html>
      <head>
        <meta charset="utf-8">
        <style>
          body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            font-size: 14px;
            line-height: 1.6;
            color: #d4d4d8;
            background: transparent;
            margin: 0;
            padding: 0;
            word-wrap: break-word;
            overflow-wrap: break-word;
          }
          a { color: #60a5fa; }
          img { max-width: 100%; height: auto; }
          blockquote {
            border-left: 3px solid #3f3f46;
            margin-left: 0;
            padding-left: 16px;
            color: #a1a1aa;
          }
          table { max-width: 100%; }
        </style>
      </head>
      <body>${email.body_html}</body>
      </html>
    `);
    doc.close();

    // Auto-resize iframe to content height
    const resizeObserver = new ResizeObserver(() => {
      if (iframeRef.current && doc.body) {
        iframeRef.current.style.height = `${doc.body.scrollHeight + 20}px`;
      }
    });
    if (doc.body) resizeObserver.observe(doc.body);
    return () => resizeObserver.disconnect();
  }, [email?.body_html]);

  // Toggle star
  const handleToggleStar = async () => {
    if (!email) return;
    const updated = await updateEmail(email.id, {
      is_starred: !email.is_starred,
    });
    setEmail(updated);
    onEmailUpdated();
  };

  // Change category
  const handleChangeCategory = async (newCategory: string) => {
    if (!email) return;
    const updated = await updateEmail(email.id, { category: newCategory });
    setEmail(updated);
    setShowCategoryMenu(false);
    onEmailUpdated();
  };

  // Confirm current AI category without changing it.
  const handleAgreeCategory = async () => {
    if (!email) return;
    const updated = await updateEmail(email.id, { category: email.category });
    setEmail(updated);
    onEmailUpdated();
  };

  // Format address list for display
  const formatAddresses = (
    addrs: { name: string; address: string }[] | null
  ) => {
    if (!addrs || addrs.length === 0) return null;
    return addrs
      .map((a) => (a.name ? `${a.name} <${a.address}>` : a.address))
      .join(", ");
  };

  if (isLoading) {
    return (
      <div className="fixed inset-y-0 right-0 w-[600px] bg-card border-l border-border shadow-2xl z-50 flex items-center justify-center">
        <div className="animate-pulse text-muted-foreground text-sm">
          Loading email…
        </div>
      </div>
    );
  }

  if (!email) {
    return (
      <div className="fixed inset-y-0 right-0 w-[600px] bg-card border-l border-border shadow-2xl z-50 flex items-center justify-center">
        <div className="text-muted-foreground text-sm">Email not found</div>
      </div>
    );
  }

  const catMeta = getCategoryMeta(email.category);

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/30 z-40"
        onClick={onClose}
      />

      {/* Panel */}
      <div className="fixed inset-y-0 right-0 w-[600px] max-w-full bg-card border-l border-border shadow-2xl z-50 flex flex-col animate-in slide-in-from-right duration-200">
        {/* Header bar */}
        <div className="flex items-center gap-2 px-5 py-3 border-b border-border shrink-0">
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg hover:bg-secondary transition-colors"
          >
            <X className="h-4 w-4 text-muted-foreground" />
          </button>

          <div className="flex-1" />

          {/* Star */}
          <button
            onClick={handleToggleStar}
            className="p-1.5 rounded-lg hover:bg-secondary transition-colors"
          >
            <Star
              className={cn(
                "h-4 w-4",
                email.is_starred
                  ? "fill-yellow-400 text-yellow-400"
                  : "text-muted-foreground"
              )}
            />
          </button>

          {/* Category dropdown */}
          <div className="relative" ref={categoryMenuRef}>
            <button
              onClick={() => setShowCategoryMenu(!showCategoryMenu)}
              className={cn(
                "flex items-center gap-1 px-2 py-1 rounded-md text-xs font-medium transition-colors",
                catMeta.color
              )}
            >
              <Tag className="h-3 w-3" />
              {catMeta.label}
              <ChevronDown className="h-3 w-3" />
            </button>

            {showCategoryMenu && (
              <div className="absolute right-0 top-full mt-1 w-44 rounded-lg border border-border bg-card shadow-xl z-50 py-1">
                <div className="px-3 py-1.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                  Move to category
                </div>
                {ALL_CATEGORIES.map((cat) => {
                  const meta = getCategoryMeta(cat);
                  return (
                    <button
                      key={cat}
                      onClick={() => handleChangeCategory(cat)}
                      className={cn(
                        "w-full flex items-center gap-2 px-3 py-1.5 text-sm text-left hover:bg-secondary transition-colors",
                        email.category === cat && "bg-secondary"
                      )}
                    >
                      <span
                        className={cn(
                          "h-2 w-2 rounded-full",
                          meta.color.replace("text-", "bg-").split(" ")[0]
                        )}
                      />
                      {meta.label}
                    </button>
                  );
                })}
              </div>
            )}
          </div>

          {/* Reply */}
          <button
            onClick={() => onReply(email)}
            className="p-1.5 rounded-lg hover:bg-secondary transition-colors"
            title="Reply"
          >
            <Reply className="h-4 w-4 text-muted-foreground" />
          </button>

          {/* Forward */}
          <button
            onClick={() => onForward(email)}
            className="p-1.5 rounded-lg hover:bg-secondary transition-colors"
            title="Forward"
          >
            <Forward className="h-4 w-4 text-muted-foreground" />
          </button>
        </div>

        {/* Email content — scrollable */}
        <div className="flex-1 overflow-y-auto">
          {/* Subject + meta */}
          <div className="px-5 py-4 space-y-3">
            <h1 className="text-lg font-semibold text-foreground leading-tight">
              {email.subject || "(no subject)"}
            </h1>

            {/* From */}
            <div className="flex items-start gap-3">
              <div className="h-9 w-9 rounded-full bg-primary/10 flex items-center justify-center shrink-0 mt-0.5">
                <span className="text-sm font-semibold text-primary">
                  {(email.from_name || email.from_address || "?")[0].toUpperCase()}
                </span>
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium text-foreground">
                    {email.from_name || email.from_address}
                  </span>
                  <span className="text-xs text-muted-foreground">
                    {email.received_at
                      ? format(new Date(email.received_at), "MMM d, yyyy 'at' h:mm a")
                      : ""}
                  </span>
                </div>
                <span className="text-xs text-muted-foreground">
                  {email.from_address}
                </span>
              </div>
              {email.received_at && (
                <span className="text-xs text-muted-foreground shrink-0">
                  {formatDistanceToNow(new Date(email.received_at), {
                    addSuffix: true,
                  })}
                </span>
              )}
            </div>

            {/* To / CC / BCC */}
            <div className="text-xs space-y-1 text-muted-foreground">
              {email.to_addresses && (
                <div>
                  <span className="font-medium text-muted-foreground/70">To: </span>
                  {formatAddresses(email.to_addresses)}
                </div>
              )}
              {email.cc_addresses && email.cc_addresses.length > 0 && (
                <div>
                  <span className="font-medium text-muted-foreground/70">Cc: </span>
                  {formatAddresses(email.cc_addresses)}
                </div>
              )}
              {email.bcc_addresses && email.bcc_addresses.length > 0 && (
                <div>
                  <span className="font-medium text-muted-foreground/70">Bcc: </span>
                  {formatAddresses(email.bcc_addresses)}
                </div>
              )}
            </div>

            {/* Attachment indicator */}
            {email.has_attachments && (
              <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                <Paperclip className="h-3 w-3" />
                <span>This email has attachments</span>
              </div>
            )}

            {/* Needs-review banner */}
            {email.needs_review && (
              <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 flex items-center justify-between gap-3">
                <p className="text-xs text-amber-300">
                  This classification needs human review. You can agree with the
                  current category or change it.
                </p>
                <button
                  onClick={handleAgreeCategory}
                  className="shrink-0 h-7 px-2.5 rounded-md bg-amber-400/20 text-amber-200 text-xs font-semibold hover:bg-amber-400/30 transition-colors"
                >
                  Agree
                </button>
              </div>
            )}

            {/* Labels */}
            {email.gmail_labels && email.gmail_labels.length > 0 && (
              <div className="flex flex-wrap gap-1">
                {email.gmail_labels
                  .filter(
                    (l) =>
                      !["INBOX", "UNREAD", "CATEGORY_PROMOTIONS", "CATEGORY_UPDATES", "CATEGORY_SOCIAL", "CATEGORY_FORUMS", "IMPORTANT"].includes(l)
                  )
                  .map((label) => (
                    <span
                      key={label}
                      className="text-[10px] px-1.5 py-0.5 rounded bg-secondary text-muted-foreground"
                    >
                      {label}
                    </span>
                  ))}
              </div>
            )}
          </div>

          {/* Divider */}
          <div className="border-t border-border" />

          {/* Body */}
          <div className="px-5 py-4">
            {email.body_html ? (
              <iframe
                ref={iframeRef}
                sandbox="allow-same-origin"
                className="w-full border-0 min-h-[200px]"
                style={{ background: "transparent" }}
                title="Email body"
              />
            ) : email.body_text ? (
              <pre className="text-sm text-foreground/90 whitespace-pre-wrap font-sans leading-relaxed">
                {email.body_text}
              </pre>
            ) : (
              <p className="text-sm text-muted-foreground italic">
                No content available
              </p>
            )}
          </div>
        </div>

        {/* Bottom action bar */}
        <div className="flex items-center gap-2 px-5 py-3 border-t border-border shrink-0">
          <button
            onClick={() => onReply(email)}
            className="flex items-center gap-2 h-9 px-4 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors"
          >
            <Reply className="h-4 w-4" />
            Reply
          </button>
          <button
            onClick={() => onForward(email)}
            className="flex items-center gap-2 h-9 px-4 rounded-lg bg-secondary text-foreground text-sm font-medium hover:bg-secondary/80 transition-colors"
          >
            <Forward className="h-4 w-4" />
            Forward
          </button>
          {email.gmail_message_id && (
            <a
              href={`https://mail.google.com/mail/u/0/#inbox/${email.gmail_message_id}`}
              target="_blank"
              rel="noopener noreferrer"
              className="ml-auto flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors"
            >
              Open in Gmail
              <ExternalLink className="h-3 w-3" />
            </a>
          )}
        </div>
      </div>
    </>
  );
}
