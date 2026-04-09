# DonnaAI Project Context Log

This is the authoritative continuity file for DonnaAI. Update this file on every major product or architecture change.

## Core Direction Lock (2026-04-09)
- DonnaAI is a personal assistant dashboard and action engine for one user.
- The core outcome is one place for messages, email, calendar, and context retrieval.
- The core capability is cross-platform actions:
  - retrieve context from platform A
  - send/forward/respond on platform B
- Voice assistant is planned, but only after data ingestion and action reliability are proven.
- OpenClaw runtime is not the target architecture.
  - `openclaw/` is a source-code reference repository to reuse patterns and adapter logic.
  - DonnaAI owns its own backend runtime, data model, and persistence.

## Mandatory Build Priorities
1. Platform integration reliability (Slack, WhatsApp, Teams, Email, Calendar).
2. Durable ingestion and normalized storage for non-email messages.
3. Reliable send/reply APIs per platform with auditability.
4. Unified inbox/search/summaries over DonnaAI-owned data.
5. Agent context orchestration and voice interface after items 1-4 are stable.

## Current Technical Reality (2026-04-09)
- Gmail is the only provider with durable first-class message persistence (`emails` table).
- Slack/Teams/WhatsApp are largely fetched live through service adapters and are not yet persisted as first-class message records in Donna DB.
- OpenClaw gateway-based integration code exists in Donna backend and can remain as temporary scaffolding, but target direction is native Donna-managed connector workers and persistence.

## Platform Strategy
- Email: Gmail API first, Outlook/IMAP/SMTP deferred.
- Slack: native OAuth + Web API ingestion/send, with webhook/event ingestion for near-real-time updates.
- Teams: native OAuth + Graph API ingestion/send and subscription/webhook ingestion.
- WhatsApp: durable linked-account ingestion/send path with reconnect-safe session management.
- Calendar: Google Calendar ingestion and action support aligned with briefing workflows.

## Architecture Principles
- DonnaAI is the source of truth for:
  - identity and account linking
  - normalized conversations/messages/events
  - embeddings/search indexes
  - action execution logs and approvals
- Connectors are adapters at the edge, never the data store.
- Every outbound action must have an idempotency key and persisted action record.
- Ingestion jobs must be cursor-driven, resumable, and replay-safe.

## Operational Conventions
- Keep docs synchronized with implementation decisions.
- For each major update:
  - run relevant backend tests
  - run frontend verification for affected flows
  - commit to `dev` branch with clear scope
- Record concrete validation evidence (commands, endpoints, behavior).

## Roadmap (Refined)
- Phase A: Connector + ingestion foundation (active priority).
- Phase B: Unified search/summarize/action layer over persisted data.
- Phase C: Agent context orchestration and automations.
- Phase D: Voice briefing and voice-command interface.

## Last Updated
- 2026-04-09
