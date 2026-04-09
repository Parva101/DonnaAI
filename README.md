# DonnaAI

DonnaAI is being rebuilt as a personal operations layer on top of OpenClaw.

Core goals:
- Unify user-selected messages, email, and calendar context in one place.
- Enable trustworthy cross-platform search, summaries, and actions.
- Support safe cross-platform execution (with approvals and audit logs).
- Add voice workflows after core data/action reliability is proven.

## Branch Strategy

- `dev`: existing/legacy implementation (kept intact).
- `main`: reset foundation for the new DonnaAI direction.

## Current Status

This branch is intentionally reset to a clean baseline so the new architecture can be built without carrying forward mismatched code.

Planned first build phases:
1. Ingestion foundation (forward-only, consent-gated).
2. Unified retrieval and context packets.
3. Approval-gated action execution.
4. Voice orchestration on top of stable action/data layers.

## Planned Repository Layout

```text
apps/        # dashboard and future client apps
services/    # ingest, retrieval, action workers
packages/    # shared contracts, domain models, connector adapters
infra/       # deployment and infrastructure definitions
scripts/     # local ops and automation scripts
tests/       # integration and end-to-end tests
```

## Security and Public Repo Policy

This repository is public. Do not commit:
- `.env` files and secrets
- credentials, keys, tokens
- private docs/notes
- local databases, dumps, cookies, runtime artifacts

The `.gitignore` in this branch is hardened for these defaults.

## Next Step

Scaffold the new codebase (services, API contracts, DB schema v1) and implement the first vertical slice:
- ingest -> store -> retrieve -> approval -> execute -> audit
