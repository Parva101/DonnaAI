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
  needs_review: boolean;
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
  human_reviewed_at: string | null;
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

export type InboxConversationSummary = {
  conversation_id: string;
  platform: string;
  account_id: string;
  latest_email_id: string;
  sender: string;
  sender_address: string | null;
  subject: string | null;
  preview: string | null;
  unread_count: number;
  message_count: number;
  has_attachments: boolean;
  needs_review: boolean;
  category: string;
  latest_received_at: string | null;
};

export type InboxPlatformCount = {
  platform: string;
  total: number;
  unread: number;
};

export type InboxConversationListResponse = {
  conversations: InboxConversationSummary[];
  total: number;
  platform_counts: InboxPlatformCount[];
};

export type SpotifyArtist = {
  name: string;
};

export type SpotifyTrack = {
  id: string | null;
  name: string;
  artists: SpotifyArtist[];
  album_name: string | null;
  album_image_url: string | null;
  duration_ms: number | null;
  external_url: string | null;
};

export type SpotifyDevice = {
  id: string | null;
  name: string;
  type: string | null;
  volume_percent: number | null;
  is_active: boolean;
  is_restricted: boolean;
};

export type SpotifyPlayerState = {
  account_id: string;
  has_active_device: boolean;
  is_playing: boolean;
  progress_ms: number;
  shuffle_state: boolean;
  repeat_state: string;
  track: SpotifyTrack | null;
  device: SpotifyDevice | null;
};

export type SpotifyTransferRequest = {
  source_account_id: string;
  destination_account_id: string;
  transfer_playlists: boolean;
  transfer_liked_songs: boolean;
  transfer_saved_albums: boolean;
  only_owned_playlists: boolean;
};

export type SpotifyPlaylistTransferResult = {
  source_playlist_id: string;
  source_playlist_name: string;
  destination_playlist_id: string | null;
  destination_playlist_name: string | null;
  tracks_transferred: number;
  skipped_unavailable_tracks: number;
  status: string;
  warning: string | null;
};

export type SpotifyTransferSummary = {
  source_account_id: string;
  destination_account_id: string;
  playlists_considered: number;
  playlists_copied: number;
  playlists_failed: number;
  playlist_tracks_transferred: number;
  liked_songs_transferred: number;
  saved_albums_transferred: number;
  warnings: string[];
  playlist_results: SpotifyPlaylistTransferResult[];
};
