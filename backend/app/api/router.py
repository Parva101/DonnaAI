from fastapi import APIRouter

from app.api import (
    ai,
    calendar,
    connected_accounts,
    emails,
    inbox,
    news,
    notifications,
    oauth,
    routes,
    slack,
    slack_auth,
    spotify,
    spotify_auth,
    teams,
    teams_auth,
    voice,
    webhooks,
    whatsapp,
    whatsapp_auth,
)


api_router = APIRouter()
api_router.include_router(routes.router, tags=["health"])
api_router.include_router(connected_accounts.router)
api_router.include_router(oauth.router)
api_router.include_router(slack_auth.router)
api_router.include_router(teams_auth.router)
api_router.include_router(slack.router)
api_router.include_router(teams.router)
api_router.include_router(spotify_auth.router)
api_router.include_router(whatsapp_auth.router)
api_router.include_router(emails.router)
api_router.include_router(inbox.router)
api_router.include_router(calendar.router)
api_router.include_router(ai.router)
api_router.include_router(notifications.router)
api_router.include_router(voice.router)
api_router.include_router(news.router)
api_router.include_router(whatsapp.router)
api_router.include_router(spotify.router)
api_router.include_router(webhooks.router)
