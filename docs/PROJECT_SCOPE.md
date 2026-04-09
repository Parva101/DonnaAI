# DonnaAI Project Scope

## 1. Vision
DonnaAI is a personal assistant platform and dashboard for one user.

End goal:
- unify messages, email, calendar, and related context in one place
- let the user search, summarize, and act across platforms
- execute cross-platform tasks (for example: find info in chat A and forward to contact B on another platform)
- support a voice assistant later, once core data and action layers are reliable

Short version:
`DonnaAI = personal command center + cross-platform action engine + later voice interface`

## 2. Strategic Clarification (2026-04-09)
- DonnaAI will not depend on OpenClaw as the production integration runtime.
- OpenClaw repository in this project is a reference codebase for extracting proven connector patterns.
- DonnaAI backend must own:
  - ingestion workers
  - normalized storage
  - outbound execution
  - audit + idempotency guarantees

## 3. Product Goals
- Minimize app switching.
- Increase response speed with context-aware retrieval.
- Support user-approved cross-platform actions from one surface.
- Build enough reliability that voice can become just another interface layer.

## 4. Active Scope Now
- Ingestion and send/reply reliability for:
  - Gmail
  - Slack
  - WhatsApp
  - Teams
  - Calendar context
- Durable normalized storage for all platform messages (not just email).
- Unified inbox/thread views over persisted records.
- Cross-platform retrieval APIs for later agent context and voice.

Deferred:
- Full voicebot operation and morning call assistant.
- Additional email providers (Outlook/IMAP/SMTP).

## 5. Architecture Scope

### 5.1 Core Data and Action Layer (Build First)
- Canonical `conversation` and `message` models across platforms.
- Platform-specific raw payload retention for traceability.
- Cursor-based ingestion jobs with replay safety.
- Outbound dispatcher with idempotency and delivery logs.
- Search index over normalized records.

### 5.2 Assistant Layer (After 5.1 Is Stable)
- Summaries, prioritization, and suggested responses.
- Cross-platform instruction execution with approval controls.
- Context-aware orchestration (retrieve from A, send on B).

### 5.3 Voice Layer (After 5.1 + 5.2 Reliability)
- Morning briefing calls.
- Voice-directed replies, emails, and meeting scheduling.
- Voice fallback and audit integration with existing action logs.

## 6. Success Criteria
DonnaAI is successful when the user can:
1. Open one dashboard and see a complete cross-platform view.
2. Retrieve context from historical chats quickly.
3. Execute cross-platform actions accurately without switching apps.
4. Trust daily summaries enough to act immediately.
5. Later use voice on top of the same reliable action APIs.

## 7. Execution Discipline
- Every major implementation update must include:
  - relevant backend tests
  - frontend verification for changed flows
  - commit to `dev` branch with explicit scope
- Context and scope docs must be updated when strategy changes.

## 8. Last Updated
- 2026-04-09
