"""Celery application.

Start a worker:
    celery -A app.core.celery_app worker --loglevel=info

Start beat (periodic tasks):
    celery -A app.core.celery_app beat --loglevel=info
"""

from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

celery = Celery(
    "donnaai",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

celery.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    # Auto-discover tasks in workers package
    imports=["app.workers.tasks"],
    # Periodic tasks
    beat_schedule={
        "renew-gmail-watches": {
            "task": "renew_gmail_watches",
            "schedule": crontab(hour=3, minute=0, day_of_week="*/6"),  # Every 6 days at 3am
        },
        "fetch-news-updates": {
            "task": "fetch_news_updates",
            "schedule": crontab(minute="*/30"),
        },
        "generate-daily-briefings": {
            "task": "generate_daily_briefings",
            "schedule": crontab(hour=settings.morning_briefing_hour_utc, minute=0),
        },
    },
)
