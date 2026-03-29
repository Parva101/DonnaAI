from fastapi import APIRouter

from app.api import connected_accounts, emails, inbox, oauth, routes, spotify, spotify_auth, webhooks


api_router = APIRouter()
api_router.include_router(routes.router, tags=["health"])
api_router.include_router(connected_accounts.router)
api_router.include_router(oauth.router)
api_router.include_router(spotify_auth.router)
api_router.include_router(emails.router)
api_router.include_router(inbox.router)
api_router.include_router(spotify.router)
api_router.include_router(webhooks.router)
