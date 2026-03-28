from fastapi import APIRouter

from app.api import connected_accounts, emails, oauth, routes, webhooks


api_router = APIRouter()
api_router.include_router(routes.router, tags=["health"])
api_router.include_router(connected_accounts.router)
api_router.include_router(oauth.router)
api_router.include_router(emails.router)
api_router.include_router(webhooks.router)
