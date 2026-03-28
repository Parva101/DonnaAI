# DonnaAI

DonnaAI is a personal assistant dashboard that unifies communication channels,
AI workflows, and eventually voice actions into one workspace.

This repository now contains the first executable Phase 1 foundation:

- `backend/`: FastAPI service skeleton
- `frontend/`: React 19 + Vite dashboard shell
- `whatsapp_bridge/`: validated WhatsApp Web bridge proof-of-concept
- `docs/`: product and planning docs

## Local development

### PostgreSQL

Local development now uses PostgreSQL through Docker Compose.

```powershell
docker compose up -d postgres
docker compose ps
```

The backend is configured to use:

- host: `127.0.0.1`
- port: `5433`
- database: `donnaai`
- user: `donnaai`
- password: `donnaai`

### Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python -m pip install -e .[dev]
.\.venv\Scripts\alembic upgrade head
.\.venv\Scripts\uvicorn app.main:app --reload
```

Backend health check:

```powershell
Invoke-WebRequest http://localhost:8000/api/v1/health
```

Database migration workflow:

```powershell
cd backend
.\.venv\Scripts\alembic upgrade head
```

When models change later, create a new revision:

```powershell
.\.venv\Scripts\alembic revision -m "describe schema change"
```

### Frontend

```powershell
cd frontend
npm install
npm run dev
```

### Celery Worker & Beat

Email sync/classify runs as background Celery tasks. Redis must be running first.

```powershell
docker compose up -d redis
```

Start the worker (use `--pool=solo` on Windows):

```powershell
cd backend
..\.venv\Scripts\celery.exe -A app.core.celery_app worker --loglevel=info --pool=solo
```

Start the beat scheduler (handles periodic tasks like Gmail watch renewal):

```powershell
cd backend
..\.venv\Scripts\celery.exe -A app.core.celery_app beat --loglevel=info
```

## Phase 1 target

Phase 1 is the foundation layer for:

- multi-user auth and account linkage
- Gmail as the first production integration
- unified inbox primitives and dashboard composition
- a repo structure that can absorb later modules without churn
