import type {
  User,
  SessionResponse,
  ConnectedAccount,
  EmailListResponse,
  EmailFull,
  EmailSyncStatus,
  SyncAllStatus,
  EmailCategoryCount,
  EmailSendResponse,
  EmailComposeRequest,
  InboxConversationListResponse,
  SpotifyPlayerState,
  SpotifyTransferRequest,
  SpotifyTransferSummary,
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
