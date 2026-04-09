from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "services" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_phase0.db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")

from sqlalchemy import delete  # noqa: E402

from app.db.base import Base  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402
from app.models import ActionLog, Message, MessageEmbedding, PermissionScope, RawEvent  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def setup_db() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def client(setup_db) -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True)
def clean_tables() -> None:
    with SessionLocal() as db:
        # Child tables first, then parents.
        db.execute(delete(MessageEmbedding))
        db.execute(delete(ActionLog))
        db.execute(delete(Message))
        db.execute(delete(RawEvent))
        db.execute(delete(PermissionScope))
        db.commit()
    yield
