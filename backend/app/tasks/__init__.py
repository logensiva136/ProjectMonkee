"""Celery application and task modules.

`celery_app` is the entrypoint the worker and beat containers are pointed at:

    celery -A app.tasks worker -Q collect,enrich,correlate,notify,easm
    celery -A app.tasks beat  -S redbeat.RedBeatScheduler
"""

from app.tasks.celery_app import celery_app

__all__ = ["celery_app"]
