import type {
  ActionItem,
  ActionItemExtractResponse,
  ActionItemListResponse,
  CalendarEventListResponse,
  User,
  SessionResponse,
  ConnectedAccount,
  DailyDigestResponse,
  EmailListResponse,
  EmailFull,
  EmailSyncStatus,
  SyncAllStatus,
  EmailCategoryCount,
  EmailSendResponse,
  EmailComposeRequest,
  InboxConversationListResponse,
  NewsBookmarkListResponse,
  NewsListResponse,
  NewsSourceRead,
  NewsSourceListResponse,
  NotificationPreferencesResponse,
  PriorityScoreResponse,
  ReplySuggestionsResponse,
  SemanticSearchResponse,
  SpotifyPlayerState,
  SpotifyTransferRequest,
  SpotifyTransferSummary,
  WhatsAppConversationListResponse,
  WhatsAppConversationMessagesResponse,
  WhatsAppStatus,
  TeamsConversationListResponse,
  TeamsMessageListResponse,
  TeamsPresenceResponse,
  TeamsSendResponse,
  SlackConversationListResponse,
  SlackMessageListResponse,
  SlackSendResponse,
  SuggestSlotsResponse,
  VoiceCall,
  VoiceCallListResponse,
} from "@/types";

const API_BASE =
  import.meta.env.VITE_API_BASE_URL ?? "/api/v1";

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      credentials: "include",
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
      ...init,
    });
  } catch {
    throw new ApiError(
      `Cannot reach backend at ${API_BASE}. Start the FastAPI server and try again.`,
      0,
    );
  }
  if (!response.ok) {
    const raw = await response.text();
    let message = raw || `Request failed with ${response.status}`;
    if (raw) {
      try {
        const payload = JSON.parse(raw) as { detail?: unknown; error?: unknown };
        if (typeof payload.detail === "string") {
          message = payload.detail;
        } else if (payload.detail !== undefined) {
          message = JSON.stringify(payload.detail);
        } else if (typeof payload.error === "string") {
          message = payload.error;
        }
      } catch {
        // Keep raw text fallback.
      }
    }
    throw new ApiError(message, response.status);
  }
  if (response.status === 204) return null as T;
  return (await response.json()) as T;
}

// ── Auth ────────────────────────────────────────────────
export function getCurrentUser(): Promise<User> {
  return request<User>("/users/me");
}

export function devLogin(payload: {
  email: string;
  full_name: string;
}): Promise<SessionResponse> {
  return request<SessionResponse>("/auth/dev-login", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function logout(): Promise<void> {
  await request<null>("/auth/logout", { method: "POST" });
}

// ── Users ───────────────────────────────────────────────
export function listUsers(): Promise<User[]> {
  return request<User[]>("/users");
}

// ── Connected Accounts ──────────────────────────────────
export function listConnectedAccounts(): Promise<ConnectedAccount[]> {
  return request<ConnectedAccount[]>("/connected-accounts");
}

export function deleteConnectedAccount(id: string): Promise<void> {
  return request<void>(`/connected-accounts/${id}`, { method: "DELETE" });
}

// ── OAuth URLs ──────────────────────────────────────────
export const GOOGLE_LOGIN_URL = `${API_BASE}/auth/google/login`;
export const GOOGLE_CONNECT_URL = `${API_BASE}/auth/google/connect`;
export const SLACK_CONNECT_URL = `${API_BASE}/auth/slack/connect`;
export const TEAMS_CONNECT_URL = `${API_BASE}/auth/teams/connect`;
export const WHATSAPP_CONNECT_URL = `${API_BASE}/auth/whatsapp/connect`;
export const SPOTIFY_CONNECT_URL = `${API_BASE}/auth/spotify/connect`;

// ── Emails ──────────────────────────────────────────────
export function listEmails(params?: {
  category?: string;
  account_id?: string;
  is_read?: boolean;
  search?: string;
  limit?: number;
  offset?: number;
}): Promise<EmailListResponse> {
  const qs = new URLSearchParams();
  if (params?.category) qs.set("category", params.category);
  if (params?.account_id) qs.set("account_id", params.account_id);
  if (params?.is_read !== undefined) qs.set("is_read", String(params.is_read));
  if (params?.search) qs.set("search", params.search);
  if (params?.limit) qs.set("limit", String(params.limit));
  if (params?.offset) qs.set("offset", String(params.offset));
  const query = qs.toString();
  return request<EmailListResponse>(`/emails${query ? `?${query}` : ""}`);
}

export function getEmail(id: string): Promise<EmailFull> {
  return request<EmailFull>(`/emails/${id}`);
}

export function updateEmail(id: string, data: { is_read?: boolean; is_starred?: boolean; category?: string }): Promise<EmailFull> {
  return request<EmailFull>(`/emails/${id}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });
}

export function syncEmails(accountId: string): Promise<EmailSyncStatus> {
  return request<EmailSyncStatus>("/emails/sync", {
    method: "POST",
    body: JSON.stringify({ account_id: accountId }),
  });
}

export function syncAllEmails(): Promise<SyncAllStatus> {
  return request<SyncAllStatus>("/emails/sync/all", {
    method: "POST",
  });
}

export function getEmailSyncStatus(): Promise<EmailSyncStatus> {
  return request<EmailSyncStatus>("/emails/sync/status");
}

export function retryPendingClassification(): Promise<EmailSyncStatus> {
  return request<EmailSyncStatus>("/emails/sync/retry", {
    method: "POST",
  });
}

export function getEmailCategories(accountId?: string): Promise<EmailCategoryCount[]> {
  const qs = accountId ? `?account_id=${accountId}` : "";
  return request<EmailCategoryCount[]>(`/emails/categories${qs}`);
}

export function sendEmail(data: EmailComposeRequest): Promise<EmailSendResponse> {
  return request<EmailSendResponse>("/emails/send", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

// —— Unified Inbox (Phase 3 kickoff) ——————————————————————————————
export function listInboxConversations(params?: {
  platform?: string;
  account_id?: string;
  unread_only?: boolean;
  search?: string;
  limit?: number;
  offset?: number;
}): Promise<InboxConversationListResponse> {
  const qs = new URLSearchParams();
  if (params?.platform) qs.set("platform", params.platform);
  if (params?.account_id) qs.set("account_id", params.account_id);
  if (params?.unread_only !== undefined) qs.set("unread_only", String(params.unread_only));
  if (params?.search) qs.set("search", params.search);
  if (params?.limit) qs.set("limit", String(params.limit));
  if (params?.offset) qs.set("offset", String(params.offset));
  const query = qs.toString();
  return request<InboxConversationListResponse>(`/inbox/conversations${query ? `?${query}` : ""}`);
}

// —— News ————————————————————————————————————————————————————————————————
export function listNewsArticles(params?: {
  topic?: string;
  limit?: number;
}): Promise<NewsListResponse> {
  const qs = new URLSearchParams();
  if (params?.topic) qs.set("topic", params.topic);
  if (params?.limit) qs.set("limit", String(params.limit));
  const query = qs.toString();
  return request<NewsListResponse>(`/news/articles${query ? `?${query}` : ""}`);
}

export function getWhatsAppStatus(): Promise<WhatsAppStatus> {
  return request<WhatsAppStatus>("/whatsapp/status");
}

export function listWhatsAppConversations(params?: {
  account_id?: string;
  unread_only?: boolean;
  search?: string;
  limit?: number;
}): Promise<WhatsAppConversationListResponse> {
  const qs = new URLSearchParams();
  if (params?.account_id) qs.set("account_id", params.account_id);
  if (params?.unread_only !== undefined) qs.set("unread_only", String(params.unread_only));
  if (params?.search) qs.set("search", params.search);
  if (params?.limit) qs.set("limit", String(params.limit));
  const query = qs.toString();
  return request<WhatsAppConversationListResponse>(`/whatsapp/conversations${query ? `?${query}` : ""}`);
}

export function listWhatsAppMessages(
  conversationId: string,
  params?: { account_id?: string; limit?: number },
): Promise<WhatsAppConversationMessagesResponse> {
  const qs = new URLSearchParams();
  if (params?.account_id) qs.set("account_id", params.account_id);
  if (params?.limit) qs.set("limit", String(params.limit));
  const query = qs.toString();
  return request<WhatsAppConversationMessagesResponse>(
    `/whatsapp/conversations/${encodeURIComponent(conversationId)}/messages${query ? `?${query}` : ""}`,
  );
}

export function sendWhatsAppMessage(payload: {
  to: string;
  text: string;
}): Promise<{ status: string }> {
  return request<{ status: string }>("/whatsapp/send", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function listSlackConversations(params?: {
  account_id?: string;
  unread_only?: boolean;
  search?: string;
}): Promise<SlackConversationListResponse> {
  const qs = new URLSearchParams();
  if (params?.account_id) qs.set("account_id", params.account_id);
  if (params?.unread_only !== undefined) qs.set("unread_only", String(params.unread_only));
  if (params?.search) qs.set("search", params.search);
  const query = qs.toString();
  return request<SlackConversationListResponse>(`/slack/conversations${query ? `?${query}` : ""}`);
}

export function listSlackMessages(
  conversationId: string,
  params?: { account_id?: string; limit?: number },
): Promise<SlackMessageListResponse> {
  const qs = new URLSearchParams();
  if (params?.account_id) qs.set("account_id", params.account_id);
  if (params?.limit) qs.set("limit", String(params.limit));
  const query = qs.toString();
  return request<SlackMessageListResponse>(
    `/slack/conversations/${encodeURIComponent(conversationId)}/messages${query ? `?${query}` : ""}`,
  );
}

export function sendSlackMessage(payload: {
  conversation_id: string;
  text: string;
  account_id?: string;
}): Promise<SlackSendResponse> {
  return request<SlackSendResponse>("/slack/send", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function listTeamsConversations(params?: {
  account_id?: string;
  unread_only?: boolean;
  search?: string;
}): Promise<TeamsConversationListResponse> {
  const qs = new URLSearchParams();
  if (params?.account_id) qs.set("account_id", params.account_id);
  if (params?.unread_only !== undefined) qs.set("unread_only", String(params.unread_only));
  if (params?.search) qs.set("search", params.search);
  const query = qs.toString();
  return request<TeamsConversationListResponse>(`/teams/conversations${query ? `?${query}` : ""}`);
}

export function listTeamsMessages(
  conversationId: string,
  params?: { account_id?: string; limit?: number },
): Promise<TeamsMessageListResponse> {
  const qs = new URLSearchParams();
  if (params?.account_id) qs.set("account_id", params.account_id);
  if (params?.limit) qs.set("limit", String(params.limit));
  const query = qs.toString();
  return request<TeamsMessageListResponse>(
    `/teams/conversations/${encodeURIComponent(conversationId)}/messages${query ? `?${query}` : ""}`,
  );
}

export function sendTeamsMessage(payload: {
  conversation_id: string;
  text: string;
  account_id?: string;
}): Promise<TeamsSendResponse> {
  return request<TeamsSendResponse>("/teams/send", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getTeamsPresence(accountId?: string): Promise<TeamsPresenceResponse> {
  const qs = accountId ? `?account_id=${accountId}` : "";
  return request<TeamsPresenceResponse>(`/teams/presence${qs}`);
}

export function listCalendarEvents(params?: {
  account_id?: string;
  start_at?: string;
  end_at?: string;
  limit?: number;
}): Promise<CalendarEventListResponse> {
  const qs = new URLSearchParams();
  if (params?.account_id) qs.set("account_id", params.account_id);
  if (params?.start_at) qs.set("start_at", params.start_at);
  if (params?.end_at) qs.set("end_at", params.end_at);
  if (params?.limit) qs.set("limit", String(params.limit));
  const query = qs.toString();
  return request<CalendarEventListResponse>(`/calendar/events${query ? `?${query}` : ""}`);
}

export function suggestCalendarSlots(payload: {
  account_id?: string;
  date: string;
  duration_minutes: number;
  count: number;
}): Promise<SuggestSlotsResponse> {
  return request<SuggestSlotsResponse>("/calendar/suggest-slots", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getNotificationPreferences(): Promise<NotificationPreferencesResponse> {
  return request<NotificationPreferencesResponse>("/notifications/preferences");
}

export function updateNotificationPreferences(payload: {
  email_enabled?: boolean;
  slack_enabled?: boolean;
  whatsapp_enabled?: boolean;
  teams_enabled?: boolean;
  focus_mode?: boolean;
  daily_digest_enabled?: boolean;
  daily_digest_hour_utc?: number;
}): Promise<NotificationPreferencesResponse> {
  return request<NotificationPreferencesResponse>("/notifications/preferences", {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function getDailyDigest(): Promise<DailyDigestResponse> {
  return request<DailyDigestResponse>("/notifications/digest");
}

export function getReplySuggestions(payload: {
  email_id?: string;
  platform?: string;
  context: string;
  tone?: string;
}): Promise<ReplySuggestionsResponse> {
  return request<ReplySuggestionsResponse>("/ai/reply-suggestions", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function scoreEmailPriorities(emailIds: string[]): Promise<PriorityScoreResponse> {
  return request<PriorityScoreResponse>("/ai/priority/score", {
    method: "POST",
    body: JSON.stringify({ email_ids: emailIds }),
  });
}

export function extractActionItems(payload: {
  source_platform?: string;
  source_ref?: string;
  text: string;
}): Promise<ActionItemExtractResponse> {
  return request<ActionItemExtractResponse>("/ai/action-items/extract", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function listActionItems(status?: string): Promise<ActionItemListResponse> {
  const qs = status ? `?status=${encodeURIComponent(status)}` : "";
  return request<ActionItemListResponse>(`/ai/action-items${qs}`);
}

export function updateActionItem(
  actionItemId: string,
  payload: { status?: string; priority?: string; due_at?: string | null },
): Promise<ActionItem> {
  return request<ActionItem>(`/ai/action-items/${actionItemId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function semanticSearch(payload: { query: string; limit?: number }): Promise<SemanticSearchResponse> {
  return request<SemanticSearchResponse>("/ai/search", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function fetchNewsNow(): Promise<{ status: string; new_articles: number }> {
  return request<{ status: string; new_articles: number }>("/news/fetch", {
    method: "POST",
  });
}

export function listNewsSources(): Promise<NewsSourceListResponse> {
  return request<NewsSourceListResponse>("/news/sources");
}

export function createNewsSource(payload: {
  source_type: string;
  name: string;
  url?: string;
  topic?: string;
  enabled?: boolean;
  fetch_interval_minutes?: number;
}): Promise<NewsSourceRead> {
  return request<NewsSourceRead>("/news/sources", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateNewsSource(
  sourceId: string,
  payload: {
    name?: string;
    url?: string;
    topic?: string;
    enabled?: boolean;
    fetch_interval_minutes?: number;
  },
): Promise<NewsSourceRead> {
  return request<NewsSourceRead>(`/news/sources/${sourceId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function deleteNewsSource(sourceId: string): Promise<void> {
  return request<void>(`/news/sources/${sourceId}`, {
    method: "DELETE",
  });
}

export function listNewsBookmarks(): Promise<NewsBookmarkListResponse> {
  return request<NewsBookmarkListResponse>("/news/bookmarks");
}

export function bookmarkNewsArticle(articleId: string): Promise<{ status: string }> {
  return request<{ status: string }>(`/news/bookmarks/${articleId}`, {
    method: "POST",
  });
}

export function unbookmarkNewsArticle(articleId: string): Promise<void> {
  return request<void>(`/news/bookmarks/${articleId}`, {
    method: "DELETE",
  });
}

export function listVoiceCalls(limit = 50): Promise<VoiceCallListResponse> {
  return request<VoiceCallListResponse>(`/voice/calls?limit=${limit}`);
}

export function createVoiceCall(payload: {
  intent: string;
  target_name?: string;
  target_phone?: string;
}): Promise<VoiceCall> {
  return request<VoiceCall>("/voice/calls", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

// —— Spotify ———————————————————————————————————————————————
export function getSpotifyPlayer(accountId?: string): Promise<SpotifyPlayerState> {
  const qs = accountId ? `?account_id=${accountId}` : "";
  return request<SpotifyPlayerState>(`/spotify/player${qs}`);
}

export function spotifyPlay(accountId?: string): Promise<{ status: string }> {
  const qs = accountId ? `?account_id=${accountId}` : "";
  return request<{ status: string }>(`/spotify/player/play${qs}`, { method: "POST" });
}

export function spotifyPause(accountId?: string): Promise<{ status: string }> {
  const qs = accountId ? `?account_id=${accountId}` : "";
  return request<{ status: string }>(`/spotify/player/pause${qs}`, { method: "POST" });
}

export function spotifyNext(accountId?: string): Promise<{ status: string }> {
  const qs = accountId ? `?account_id=${accountId}` : "";
  return request<{ status: string }>(`/spotify/player/next${qs}`, { method: "POST" });
}

export function spotifyPrevious(accountId?: string): Promise<{ status: string }> {
  const qs = accountId ? `?account_id=${accountId}` : "";
  return request<{ status: string }>(`/spotify/player/previous${qs}`, { method: "POST" });
}

export function spotifySetVolume(percent: number, accountId?: string): Promise<{ status: string }> {
  const qs = new URLSearchParams({ percent: String(percent) });
  if (accountId) qs.set("account_id", accountId);
  return request<{ status: string }>(`/spotify/player/volume?${qs.toString()}`, { method: "POST" });
}

export function spotifyTransferLibrary(payload: SpotifyTransferRequest): Promise<SpotifyTransferSummary> {
  return request<SpotifyTransferSummary>("/spotify/transfer", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function createUser(payload: {
  email: string;
  full_name: string;
  is_active: boolean;
}): Promise<User> {
  return request<User>("/users", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}
