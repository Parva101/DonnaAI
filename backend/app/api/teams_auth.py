"""Microsoft Teams OAuth connect routes."""

from __future__ import annotations

from urllib.parse import urlencode
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from jwt import InvalidTokenError
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.config import settings
from app.core.db import get_db
from app.models import User
from app.services.microsoft_oauth_service import MicrosoftOAuthService

router = APIRouter(prefix="/auth/teams", tags=["auth-teams"])


@router.get("/connect")
def teams_connect(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    if not settings.microsoft_client_id or not settings.microsoft_client_secret:
        redirect_url = f"{settings.frontend_url}/settings?{urlencode({'error': 'teams_not_configured', 'provider': 'teams', 'detail': 'Set MICROSOFT_CLIENT_ID and MICROSOFT_CLIENT_SECRET in backend .env'})}"
        return RedirectResponse(url=redirect_url, status_code=status.HTTP_302_FOUND)

    svc = MicrosoftOAuthService(db)
    url = svc.get_authorization_url(user_id=current_user.id)
    return RedirectResponse(url=url, status_code=status.HTTP_302_FOUND)


@router.get("/callback")
async def teams_callback(
    code: str = Query(...),
    state: str = Query(...),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    try:
        state_data = MicrosoftOAuthService.decode_state(state)
    except (InvalidTokenError, Exception):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired OAuth state.",
        )

    if state_data.get("intent") != "connect":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported Teams OAuth intent.",
        )

    svc = MicrosoftOAuthService(db)
    try:
        user_id = UUID(state_data["user_id"])
        await svc.handle_connect_callback(code, user_id)
        redirect_url = f"{settings.frontend_url}/settings?{urlencode({'connected': 'teams'})}"
    except Exception as exc:
        redirect_url = f"{settings.frontend_url}/settings?{urlencode({'error': 'teams_oauth_failed', 'provider': 'teams', 'detail': str(exc)})}"

    return RedirectResponse(url=redirect_url, status_code=status.HTTP_302_FOUND)
