"""Spotify OAuth connect routes."""

from __future__ import annotations

import logging
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
from app.services.spotify_oauth_service import SpotifyOAuthService


router = APIRouter(prefix="/auth/spotify", tags=["auth-spotify"])
logger = logging.getLogger(__name__)


@router.get("/connect")
def spotify_connect(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    svc = SpotifyOAuthService(db)
    url = svc.get_authorization_url(user_id=current_user.id)
    return RedirectResponse(url=url, status_code=status.HTTP_302_FOUND)


@router.get("/callback")
async def spotify_callback(
    code: str = Query(...),
    state: str = Query(...),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    try:
        state_data = SpotifyOAuthService.decode_state(state)
    except (InvalidTokenError, Exception):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired OAuth state.",
        )

    intent = state_data.get("intent")
    if intent != "connect":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported Spotify OAuth intent.",
        )

    svc = SpotifyOAuthService(db)
    try:
        user_id = UUID(state_data["user_id"])
        await svc.handle_connect_callback(code, user_id)
        redirect_url = f"{settings.frontend_url}/settings?{urlencode({'connected': 'spotify'})}"
    except Exception as exc:
        logger.exception("Spotify OAuth callback failed")
        redirect_url = f"{settings.frontend_url}/settings?{urlencode({'error': 'spotify_oauth_failed', 'provider': 'spotify', 'detail': str(exc)})}"

    return RedirectResponse(url=redirect_url, status_code=status.HTTP_302_FOUND)
