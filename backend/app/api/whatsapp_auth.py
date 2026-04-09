"""WhatsApp OpenClaw connect routes."""

from __future__ import annotations

from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.config import settings
from app.core.db import get_db
from app.models import User
from app.services.whatsapp_service import WhatsAppService

router = APIRouter(prefix="/auth/whatsapp", tags=["auth-whatsapp"])


@router.get("/connect")
def whatsapp_connect(
    account_id: str | None = Query(default=None, min_length=1, max_length=200),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    """Connect WhatsApp for the current user and trigger OpenClaw QR login."""
    svc = WhatsAppService(db, account_id=account_id)
    try:
        svc.start_listener()
        svc.ensure_connected_account(current_user)
        redirect_url = f"{settings.frontend_url}/settings?{urlencode({'connected': 'whatsapp'})}"
    except Exception as exc:
        redirect_url = f"{settings.frontend_url}/settings?{urlencode({'error': 'whatsapp_connect_failed', 'provider': 'whatsapp', 'detail': str(exc)})}"
    return RedirectResponse(url=redirect_url, status_code=status.HTTP_302_FOUND)
