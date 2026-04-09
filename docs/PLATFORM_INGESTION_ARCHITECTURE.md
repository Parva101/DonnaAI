# DonnaAI Platform Ingestion Architecture

Last Updated: 2026-04-09
Owner: DonnaAI engineering

## 1. Objective
Build a DonnaAI-native ingestion and action foundation for Slack, WhatsApp, Teams, Gmail, and Calendar so higher layers (agent context orchestration, voice) can rely on consistent data.

## 2. Non-Negotiable Rules
- DonnaAI backend is the runtime for ingestion and outbound actions.
- OpenClaw code may be reused, but OpenClaw runtime is not required in production paths.
- Every outbound action is persisted with idempotency and delivery status.
- Every ingestion path must be replay-safe and cursor-based.

## 3. Target System Layout
- `connectors/`
  - platform clients and auth refresh (`slack`, `teams`, `whatsapp`, `gmail`, `calendar`)
- `ingestion/`
  - poll/webhook handlers, cursor management, normalization mappers
- `messaging/`
  - conversation/message/event stores and query services
- `actions/`
  - send/reply/forward dispatcher + delivery tracking
- `search/`
  - indexing + retrieval over normalized message records

## 4. Canonical Data Model

### 4.1 `conversations`
Purpose: cross-platform thread container.

Required fields:
- `id` (uuid)
- `user_id` (uuid)
- `platform` (`gmail|slack|whatsapp|teams`)
- `account_id` (fk connected_accounts)
- `external_conversation_id` (platform-native id)
- `title`
- `is_group`
- `last_message_at`
- `last_ingested_at`
- `metadata` (jsonb)

Indexes:
- `(user_id, platform, account_id, external_conversation_id)` unique
- `(user_id, last_message_at desc)`

### 4.2 `messages`
Purpose: canonical per-message storage.

Required fields:
- `id` (uuid)
- `conversation_id` (fk conversations)
- `user_id` (uuid)
- `platform`
- `account_id`
- `external_message_id`
- `external_thread_id` (nullable)
- `direction` (`inbound|outbound`)
- `sender_id`, `sender_label`
- `recipient_ids` (jsonb)
- `text`
- `content_type` (`text|image|video|audio|file|system|other`)
- `has_attachments`
- `sent_at`
- `ingested_at`
- `raw_payload` (jsonb, redacted where needed)

Indexes:
- `(conversation_id, sent_at)`
- `(user_id, platform, account_id, external_message_id)` unique
- full text / vector search index over normalized text

### 4.3 `message_events`
Purpose: non-message state updates and audit history.

Examples:
- edit/delete/reaction/read-receipt/ingestion-error

Required fields:
- `id`, `message_id`, `event_type`, `event_at`, `payload`

### 4.4 `outbound_actions`
Purpose: reliable send/reply/forward tracking.

Required fields:
- `id`
- `user_id`
- `platform`
- `account_id`
- `conversation_id` (nullable for new thread/create cases)
- `target`
- `action_type` (`send|reply|forward`)
- `request_payload`
- `idempotency_key` (unique)
- `status` (`queued|sent|failed|retrying`)
- `provider_message_id` (nullable)
- `error` (nullable)
- `created_at`, `updated_at`

## 5. Connector Contract
Each connector implements:
- `sync_conversations(since_cursor) -> list[ConversationDelta], next_cursor`
- `sync_messages(conversation_ref, since_cursor) -> list[MessageDelta], next_cursor`
- `send_message(target, text, idempotency_key) -> DeliveryResult`
- `health() -> ConnectorHealth`

Connector outputs are platform-specific DTOs transformed by Donna mappers into canonical tables.

## 6. Ingestion Pipeline
1. Load active connected accounts.
2. For each account, read last successful cursor.
3. Fetch deltas from platform API/webhook backlog.
4. Normalize and upsert:
  - conversation
  - message
  - message_event
5. Persist new cursor only after successful transaction.
6. Emit realtime event for inbox refresh.

Failure handling:
- soft failures create ingestion error events
- retries with exponential backoff
- poison records moved to dead-letter table/queue

## 7. Outbound Pipeline
1. API request creates `outbound_actions` row with idempotency key.
2. Dispatcher executes connector `send_message`.
3. On success:
  - action row `status=sent`
  - upsert outbound message into `messages`
4. On failure:
  - action row `status=failed` with error details
  - retry policy applied where safe

## 8. Migration from Current State
Phase step order:
1. Add canonical messaging tables + migrations.
2. Write Slack ingestion worker against native Slack APIs.
3. Write Teams ingestion worker against Graph.
4. Write WhatsApp ingestion worker for linked account path.
5. Keep existing endpoint contracts while switching data source from live-fetch to persisted records.
6. Remove OpenClaw runtime dependency from critical paths once parity is verified.

## 9. Verification Requirements per Major Update
- Backend:
  - unit tests for mapper logic and idempotency
  - integration tests for connector read/send flows
- Frontend:
  - verify inbox list, thread open, and send for affected platforms
- Evidence:
  - include command outputs and endpoint checks in logs/docs
- Git:
  - commit scoped changes to `dev` branch

## 10. Voice Readiness Gate
Voice implementation starts only when:
- ingestion lag is bounded and measurable
- cross-platform send success is stable
- summaries and retrieval run on persisted canonical records
- action audit trail is complete
