"""WhatsApp bridge connect routes."""

from __future__ import annotations

from urllib.parse import urlencode

from fastapi import APIRouter, Depends, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.config import settings
from app.core.db import get_db
from app.models import User
from app.services.whatsapp_bridge_service import WhatsAppBridgeService

router = APIRouter(prefix="/auth/whatsapp", tags=["auth-whatsapp"])


@router.get("/connect")
def whatsapp_connect(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    """Connect WhatsApp bridge for the current user and start listener process."""
    svc = WhatsAppBridgeService(db)
    try:
        svc.ensure_connected_account(current_user)
        svc.start_listener()
        redirect_url = f"{settings.frontend_url}/settings?{urlencode({'connected': 'whatsapp'})}"
    except Exception as exc:
        redirect_url = f"{settings.frontend_url}/settings?{urlencode({'error': 'whatsapp_connect_failed', 'provider': 'whatsapp', 'detail': str(exc)})}"
    return RedirectResponse(url=redirect_url, status_code=status.HTTP_302_FOUND)
