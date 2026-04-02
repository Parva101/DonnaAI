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
  priority_score: number;
  priority_label: string;
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
  job_id: string;
  status: string;
  stage: string;
  mode: string;
  accounts_total: number;
  accounts_done: number;
  fetched_total: number;
  classify_total: number;
  classified_done: number;
  failed_count: number;
  remaining_pending: number;
  error: string | null;
  started_at: string | null;
  finished_at: string | null;
};

export type SyncAllStatus = {
  job: EmailSyncStatus;
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
  latest_email_id: string | null;
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

export type NewsArticle = {
  id: string;
  title: string;
  url: string;
  source: string;
  summary: string | null;
  topic: string;
  relevance_score: number;
  published_at: string | null;
  is_bookmarked: boolean;
};

export type NewsListResponse = {
  articles: NewsArticle[];
};

export type NewsSourceRead = {
  id: string;
  user_id: string;
  source_type: string;
  name: string;
  url: string | null;
  topic: string;
  enabled: boolean;
  fetch_interval_minutes: number;
  created_at: string;
  updated_at: string;
};

export type NewsSourceListResponse = {
  sources: NewsSourceRead[];
};

export type NewsBookmarkRead = {
  article_id: string;
  title: string;
  url: string;
  source: string;
  topic: string;
  published_at: string | null;
  bookmarked_at: string;
};

export type NewsBookmarkListResponse = {
  bookmarks: NewsBookmarkRead[];
};

export type WhatsAppStatus = {
  running: boolean;
  pid: number | null;
  device_id: string;
  qr_data_uri: string | null;
  qr_text: string | null;
  messages_log_exists: boolean;
  connection_state?: string | null;
  me_jid?: string | null;
  state_updated_at?: string | null;
  state_age_seconds?: number | null;
};

export type WhatsAppConversationSummary = {
  account_id: string;
  conversation_id: string;
  sender: string;
  preview: string | null;
  unread_count: number;
  message_count: number;
  has_attachments: boolean;
  latest_received_at: string | null;
  is_group: boolean;
};

export type WhatsAppConversationListResponse = {
  conversations: WhatsAppConversationSummary[];
  total: number;
};

export type WhatsAppConversationMessage = {
  message_id: string | null;
  sender: string | null;
  from_me: boolean;
  text: string | null;
  message_type: string | null;
  timestamp: number | null;
  received_at: string | null;
};

export type WhatsAppConversationMessagesResponse = {
  messages: WhatsAppConversationMessage[];
  total: number;
};

export type SlackConversationSummary = {
  account_id: string;
  conversation_id: string;
  name: string | null;
  sender: string;
  preview: string | null;
  unread_count: number;
  message_count: number;
  has_attachments: boolean;
  latest_received_at: string | null;
  is_im: boolean;
  is_private: boolean;
};

export type SlackConversationListResponse = {
  conversations: SlackConversationSummary[];
  total: number;
};

export type SlackMessage = {
  ts: string;
  sender: string | null;
  user_id: string | null;
  text: string | null;
  subtype: string | null;
  thread_ts: string | null;
  has_attachments: boolean;
};

export type SlackMessageListResponse = {
  messages: SlackMessage[];
  total: number;
};

export type SlackSendResponse = {
  status: string;
  channel: string;
  ts: string;
};

export type TeamsConversationSummary = {
  account_id: string;
  conversation_id: string;
  name: string | null;
  sender: string;
  preview: string | null;
  unread_count: number;
  message_count: number;
  has_attachments: boolean;
  latest_received_at: string | null;
};

export type TeamsConversationListResponse = {
  conversations: TeamsConversationSummary[];
  total: number;
};

export type TeamsMessage = {
  id: string;
  sender: string | null;
  from_me: boolean;
  text: string | null;
  created_at: string | null;
  has_attachments: boolean;
};

export type TeamsMessageListResponse = {
  messages: TeamsMessage[];
  total: number;
};

export type TeamsSendResponse = {
  status: string;
  conversation_id: string;
  message_id: string | null;
};

export type TeamsPresenceResponse = {
  account_id: string;
  availability: string;
  activity: string;
};

export type CalendarEvent = {
  account_id: string;
  provider: string;
  event_id: string;
  title: string;
  description: string | null;
  location: string | null;
  start_at: string;
  end_at: string;
  attendees: string[];
  organizer: string | null;
  is_all_day: boolean;
};

export type CalendarEventListResponse = {
  events: CalendarEvent[];
  total: number;
};

export type BusyBlock = {
  start_at: string;
  end_at: string;
};

export type SuggestSlotsResponse = {
  slots: BusyBlock[];
};

export type NotificationPreferences = {
  email_enabled: boolean;
  slack_enabled: boolean;
  whatsapp_enabled: boolean;
  teams_enabled: boolean;
  focus_mode: boolean;
  daily_digest_enabled: boolean;
  daily_digest_hour_utc: number;
};

export type NotificationPreferencesResponse = {
  preferences: NotificationPreferences;
};

export type DigestItem = {
  title: string;
  source: string;
  preview: string;
  url: string | null;
};

export type DailyDigestResponse = {
  generated_at: string;
  summary: string;
  top_items: DigestItem[];
};

export type ActionItem = {
  id: string;
  user_id: string;
  source_platform: string;
  source_ref: string | null;
  title: string;
  details: string | null;
  status: string;
  priority: string;
  score: number;
  due_at: string | null;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
};

export type ActionItemListResponse = {
  items: ActionItem[];
  total: number;
};

export type ActionItemExtractResponse = {
  items: ActionItem[];
};

export type PriorityScoreResult = {
  email_id: string;
  score: number;
  label: string;
};

export type PriorityScoreResponse = {
  results: PriorityScoreResult[];
};

export type ReplySuggestionsResponse = {
  suggestions: string[];
};

export type SemanticSearchItem = {
  email_id: string;
  score: number;
  subject: string | null;
  from_address: string | null;
  snippet: string | null;
  category: string;
};

export type SemanticSearchResponse = {
  results: SemanticSearchItem[];
};

export type VoiceCall = {
  id: string;
  user_id: string;
  target_name: string | null;
  target_phone: string | null;
  intent: string;
  status: string;
  transcript: string | null;
  summary: string | null;
  outcome: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
};

export type VoiceCallListResponse = {
  calls: VoiceCall[];
  total: number;
};
