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

Phase 0 scaffold is now in place:
- FastAPI service skeleton (`services/api`)
- Alembic migrations and foundation schema
- Ingestion/search/action API stubs
- Permission scope enforcement (`read/write/relay`)
- Docker local dependencies (Postgres + Redis)
- CI pipeline (lint, migration, tests)

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

## Phase 0 Quick Start

1. Copy env:

```powershell
copy .env.example .env
copy services\api\.env.example services\api\.env
```

2. Start dependencies:

```powershell
docker compose up -d
```

3. Install API deps:

```powershell
cd services\api
python -m venv .venv
.\.venv\Scripts\python -m pip install --upgrade pip
.\.venv\Scripts\python -m pip install -r requirements-dev.txt
```

4. Run migrations:

```powershell
.\.venv\Scripts\alembic -c alembic.ini upgrade head
```

5. Start API:

```powershell
.\.venv\Scripts\uvicorn app.main:app --reload --host 0.0.0.0 --port 8010
```

6. Run tests from repo root:

```powershell
pytest -q
```

## Phase 0 Endpoints

- `GET /health`
- `PUT /v1/permissions/scopes`
- `GET /v1/permissions/scopes`
- `POST /v1/ingest/events`
- `GET /v1/search/messages`
- `POST /v1/actions/plan`
- `POST /v1/actions/execute`
- `GET /v1/actions/{action_id}?tenant_id=...`

## Security and Public Repo Policy

This repository is public. Do not commit:
- `.env` files and secrets
- credentials, keys, tokens
- private docs/notes
- local databases, dumps, cookies, runtime artifacts

The `.gitignore` in this branch is hardened for these defaults.

## Next Step

Build Phase 1 connector wiring:
- OpenClaw event intake into `/v1/ingest/events`
- normalized context retrieval improvements
- real action executor adapters (still approval-gated)
