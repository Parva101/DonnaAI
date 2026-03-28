import type { User, SessionResponse, ConnectedAccount, EmailListResponse, EmailFull, EmailSyncStatus, SyncAllStatus, EmailCategoryCount, EmailSendResponse, EmailComposeRequest } from "@/types";

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
    const text = await response.text();
    throw new ApiError(text || `Request failed with ${response.status}`, response.status);
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
