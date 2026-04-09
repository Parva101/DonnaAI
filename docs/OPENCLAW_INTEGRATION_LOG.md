# OpenClaw Code Reuse Log

Last Updated: 2026-04-09
Owner: DonnaAI engineering
Status: Runtime integration strategy archived; code reuse strategy active

## Direction Lock
- DonnaAI is not integrating OpenClaw as a production runtime dependency.
- DonnaAI uses `openclaw/` as a source code reference to accelerate connector implementation.
- DonnaAI backend remains responsible for:
  - ingestion runtime
  - normalized persistence
  - outbound action execution
  - audit and policy controls

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
