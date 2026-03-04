"""
Celery application factory for Oneka AI background task queue.

Workers are started with:
    celery -A backend.src.celery_app worker --loglevel=info --concurrency=4

Beat scheduler (periodic tasks) is started with:
    celery -A backend.src.celery_app beat --loglevel=info
"""

from celery import Celery
from celery.schedules import crontab

from src.config import settings


def create_celery_app() -> Celery:
    app = Celery(
        "oneka",
        broker=settings.redis_url,
        backend=settings.redis_url,
        include=[
            "src.tasks.ingestion_tasks",
        ],
    )

    app.conf.update(
        # Serialisation
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        # Timezone
        timezone="Africa/Nairobi",
        enable_utc=True,
        # Reliability
        task_acks_late=True,
        task_reject_on_worker_lost=True,
        worker_prefetch_multiplier=1,
        # Results TTL — keep results 24 hours
        result_expires=86400,
        # ── Beat schedule ─────────────────────────────────────────
        beat_schedule={
            # eGP scraper — daily at 02:00 EAT
            "scrape-egp-daily": {
                "task": "src.tasks.ingestion_tasks.scrape_egp_task",
                "schedule": crontab(hour=2, minute=0),
            },
            # KMHFL registry refresh — first Sunday of every month at 03:00 EAT
            "refresh-kmhfl-monthly": {
                "task": "src.tasks.ingestion_tasks.refresh_kmhfl_task",
                "schedule": crontab(hour=3, minute=0, day_of_week=0),
            },
        },
    )

    return app


celery_app = create_celery_app()
