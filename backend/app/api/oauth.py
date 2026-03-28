"""Google OAuth API routes.

Two entry points:
  GET /auth/google/login   — initiate Google sign-in (creates user + session)
  GET /auth/google/connect — link Google account for an already-logged-in user
  GET /auth/google/callback — shared callback for both flows
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import RedirectResponse
from jwt import InvalidTokenError
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.config import settings
from app.core.db import get_db
from app.core.security import create_session_token
from app.models import User
from app.services.oauth_service import GoogleOAuthService


router = APIRouter(prefix="/auth/google", tags=["auth-google"])


@router.get("/login")
def google_login(db: Session = Depends(get_db)) -> RedirectResponse:
    """Redirect the user to Google's consent screen for login/signup."""
    svc = GoogleOAuthService(db)
    url = svc.get_authorization_url(intent="login")
    return RedirectResponse(url=url, status_code=status.HTTP_302_FOUND)


@router.get("/connect")
def google_connect(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    """Redirect to Google to connect Gmail/Calendar for the logged-in user."""
    svc = GoogleOAuthService(db)
    url = svc.get_authorization_url(intent="connect", user_id=current_user.id)
    return RedirectResponse(url=url, status_code=status.HTTP_302_FOUND)


@router.get("/callback")
async def google_callback(
    code: str = Query(...),
    state: str = Query(...),
    response: Response = Response(),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    """Handle the OAuth callback from Google.

    Decodes the state JWT to determine whether this is a login or connect flow,
    then processes accordingly and redirects back to the frontend.
    """
    # Decode and validate state
    try:
        state_data = GoogleOAuthService.decode_state(state)
    except (InvalidTokenError, Exception):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired OAuth state.",
        )

    intent = state_data.get("intent", "login")
    svc = GoogleOAuthService(db)

    try:
        if intent == "connect":
            user_id = UUID(state_data["user_id"])
            await svc.handle_connect_callback(code, user_id)
            redirect_url = f"{settings.frontend_url}/settings?connected=google"
        else:
            user = await svc.handle_login_callback(code)
            # Set session cookie
            session_token = create_session_token(user.id)
            redirect = RedirectResponse(
                url=f"{settings.frontend_url}/dashboard",
                status_code=status.HTTP_302_FOUND,
            )
            redirect.set_cookie(
                key=settings.session_cookie_name,
                value=session_token,
                httponly=True,
                secure=settings.session_cookie_secure,
                samesite="lax",
                max_age=settings.session_expire_minutes * 60,
                path="/",
            )
            return redirect

    except Exception as exc:
        redirect_url = f"{settings.frontend_url}/settings?error=oauth_failed&detail={exc}"

    return RedirectResponse(url=redirect_url, status_code=status.HTTP_302_FOUND)
