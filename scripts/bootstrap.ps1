param(
  [switch]$NoDocker
)

$ErrorActionPreference = "Stop"

Write-Host "Bootstrapping DonnaAI Phase 0..."

if (-not $NoDocker) {
  Write-Host "Starting postgres + redis..."
  docker compose up -d
}

Push-Location services/api
try {
  python -m venv .venv
  .\.venv\Scripts\python -m pip install --upgrade pip
  .\.venv\Scripts\python -m pip install -r requirements-dev.txt
  $env:DATABASE_URL = "postgresql+psycopg://donnaai:donnaai@localhost:5433/donnaai"
  .\.venv\Scripts\alembic -c alembic.ini upgrade head
  Write-Host "Phase 0 bootstrap complete."
  Write-Host "Run API: .\\.venv\\Scripts\\uvicorn app.main:app --reload --host 0.0.0.0 --port 8010"
}
finally {
  Pop-Location
}

