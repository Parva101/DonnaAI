export type User = {
  id: string;
  email: string;
  full_name: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

export type ConnectedAccount = {
  id: string;
  user_id: string;
  provider: string;
  provider_account_id: string;
  account_email: string | null;
  scopes: string | null;
  created_at: string;
  updated_at: string;
};

export type Platform =
  | "slack"
  | "whatsapp"
  | "gmail"
  | "outlook"
  | "teams"
  | "calendar"
  | "spotify";

export type MockMessage = {
  id: string;
  platform: Platform;
  sender: string;
  content: string;
  time: string;
  unread: boolean;
};

export type MockEvent = {
  id: string;
  title: string;
  time: string;
  duration: string;
  color?: string;
};

export type SessionResponse = {
  user: User;
};

// ── Email Hub types ─────────────────────────────────────
export type EmailSummary = {
  id: string;
  account_id: string;
  gmail_message_id: string | null;
  thread_id: string | null;
  subject: string | null;
  snippet: string | null;
  from_address: string | null;
  from_name: string | null;
  to_addresses: { name: string; address: string }[] | null;
  category: string;
  category_source: string;
  is_read: boolean;
  is_starred: boolean;
  has_attachments: boolean;
  received_at: string | null;
};

export type EmailFull = EmailSummary & {
  user_id: string;
  body_text: string | null;
  body_html: string | null;
  cc_addresses: { name: string; address: string }[] | null;
  bcc_addresses: { name: string; address: string }[] | null;
  reply_to: string | null;
  is_draft: boolean;
  gmail_labels: string[] | null;
  created_at: string;
  updated_at: string;
};

export type EmailCategoryCount = {
  category: string;
  count: number;
  unread: number;
};

export type EmailListResponse = {
  emails: EmailSummary[];
  total: number;
  categories: EmailCategoryCount[];
};

export type EmailSyncStatus = {
  status: string;
  synced: number;
  classified: number;
  account_id: string;
};

export type SyncAllStatus = {
  status: string;
  accounts_queued: number;
  account_ids: string[];
};

export type EmailComposeRequest = {
  account_id: string;
  to: string[];
  cc?: string[];
  bcc?: string[];
  subject?: string;
  body: string;
  in_reply_to?: string;
  thread_id?: string;
};

export type EmailSendResponse = {
  status: string;
  gmail_message_id: string | null;
  thread_id: string | null;
};
