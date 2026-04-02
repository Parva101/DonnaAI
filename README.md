# DonnaAI

DonnaAI is a unified personal assistant dashboard that combines:
- Multi-account Gmail sync + AI categorization
- Unified inbox across Gmail, Slack, WhatsApp, and Teams
- Calendar events and slot suggestions
- AI productivity tools (reply suggestions, priority scoring, action items, semantic search)
- Voice call workflow scaffolding (LiveKit + Twilio ready)
- Spotify playback controls and account-to-account library transfer
- News ingestion (RSS, NewsAPI, Hacker News) with bookmarks and daily briefing

## Quick Start (Docker Compose)

### 1) Configure env

Copy and edit:

```powershell
copy backend\.env.example backend\.env
copy frontend\.env.example frontend\.env
```

### 2) Start full stack

```powershell
docker compose up -d --build
```

Services:
- Frontend: `http://localhost:5173`
- Backend: `http://localhost:8010`
- API docs: `http://localhost:8010/docs`
- Postgres: `localhost:5433`
- Redis: `localhost:6379`

Optional WhatsApp bridge container:

```powershell
docker compose --profile whatsapp up -d --build
```

## Quick Start (Manual Local)

### Backend

```powershell
cd backend
..\.venv\Scripts\python -m pip install -e .[dev]
..\.venv\Scripts\alembic upgrade head
..\.venv\Scripts\uvicorn app.main:app --reload --host 0.0.0.0 --port 8010
```

### Celery worker + beat

```powershell
cd backend
..\.venv\Scripts\celery.exe -A app.core.celery_app worker --loglevel=info --pool=solo
..\.venv\Scripts\celery.exe -A app.core.celery_app beat --loglevel=info
```

### Frontend

```powershell
cd frontend
npm install
npm run dev
```

## Implemented API Areas

- `/api/v1/emails/*`
- `/api/v1/inbox/*`
- `/api/v1/slack/*`, `/api/v1/auth/slack/*`
- `/api/v1/whatsapp/*`, `/api/v1/auth/whatsapp/*`
- `/api/v1/teams/*`, `/api/v1/auth/teams/*`
- `/api/v1/calendar/*`
- `/api/v1/ai/*`
- `/api/v1/notifications/*`
- `/api/v1/voice/*`
- `/api/v1/spotify/*`, `/api/v1/auth/spotify/*`
- `/api/v1/news/*`
- `/api/v1/webhooks/*` (gmail/slack/teams)

## Notes

- Active email provider in scope is Gmail.
- Outlook/IMAP/SMTP are intentionally deferred.
- Connected account tokens are stored encrypted at rest via application-level token crypto helpers.
