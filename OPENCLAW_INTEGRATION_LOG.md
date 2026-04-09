# OpenClaw Code Reuse Log

Last Updated: 2026-04-09
Owner: DonnaAI engineering
Status: Transition mode (native-first target, compatibility bridge active)

## Direction Lock
- DonnaAI target architecture is native connector runtime owned by DonnaAI.
- DonnaAI uses `openclaw/` as a source code reference to accelerate connector implementation.
- DonnaAI backend remains responsible for:
  - ingestion runtime
  - normalized persistence
  - outbound action execution
  - audit and policy controls

## Current Runtime Reality (2026-04-09)
- WhatsApp ingestion/send currently runs through an OpenClaw gateway compatibility adapter.
- Slack and Teams run native APIs by default, with optional OpenClaw fallback toggles.
- Canonical source of truth is DonnaAI DB (`chat_conversations`, `chat_messages`, `chat_outbound_actions`) regardless of upstream path.

## Why This Pivot
- Current OpenClaw runtime path creates ingestion reliability and account-state ambiguity for DonnaAI goals.
- DonnaAI needs deterministic, platform-owned ingestion into first-class DB tables to become context-aware.
- Core requirement is reliable data/action layers before agent and voice orchestration.

## Reuse Targets from OpenClaw
- Slack:
  - event/webhook parsing patterns
  - channel/conversation normalization patterns
  - outbound payload shaping and thread handling
- WhatsApp:
  - message extraction/normalization logic
  - reconnect/session lifecycle practices
  - target normalization and send safety patterns
- Teams:
  - Graph message handling patterns
  - conversation reference and thread resolution patterns
  - attachment/media parsing approaches

## DonnaAI Implementation Rule
If code is reused from OpenClaw, port it into DonnaAI-owned modules with Donna schemas and tests.

Do not:
- shell out to OpenClaw CLI in production flow
- require OpenClaw gateway to read/send messages
- treat OpenClaw session data as DonnaAI source of truth

## Immediate Build Focus (Phase A)
1. Create canonical DonnaAI models for `conversations`, `messages`, `message_events`, and `outbound_actions`.
2. Implement platform ingestion workers for Slack, Teams, and WhatsApp into those models.
3. Keep Gmail path intact and align it with the unified conversation model.
4. Implement reliable outbound send APIs with idempotency keys and delivery status tracking.
5. Drive unified inbox and search from persisted Donna records.

## Historical Note
Previous OpenClaw gateway-based adapter work remains in git history and may serve as temporary compatibility code until native Donna ingestion is complete. New development should target Donna-native connectors first.

## Latest Hardening Pass (2026-04-09)
- Added webhook-to-DB ingestion for:
  - Slack `message` events
  - Teams notifications when `resourceData` includes message payload
- Added connector transport hardening:
  - Slack retry/backoff for transient failures + explicit auth error surfacing
  - Teams retry/backoff + token refresh path using stored refresh token
- Improved WhatsApp outbound reliability:
  - target normalization (phone/JID handling)
  - provider message ID extraction + persistence into outbound action records

## Latest Connector Update (2026-04-09)
- Added explicit ingestion run APIs for deterministic sync execution:
  - `POST /api/v1/inbox/sync/chats` (all/slack/teams/whatsapp)
  - `POST /api/v1/whatsapp/sync`
- Added calendar action support used by cross-platform automations:
  - `POST /api/v1/calendar/events`
  - `POST /api/v1/sports/calendar/events` to convert tracked sports games into calendar events
- Sports frontend now includes per-game calendar action wiring (`Add`) for games with known start times.
