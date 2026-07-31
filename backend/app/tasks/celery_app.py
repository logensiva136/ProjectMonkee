"""Celery application: queues, scheduler and worker lifecycle (SPEC §8).

Queues follow the pipeline in SPEC §3 — collect -> enrich -> correlate ->
evaluate -> deliver — so a slow EASM scan cannot starve alert delivery.

Scheduling uses RedBeat (DECISIONS.md D-012): the schedule lives in Redis and can
be changed at runtime, which is what per-source polling intervals need. Note that
only *fixed* entries live in RedBeat; per-source timing is driven by
`source.next_poll_at` in Postgres and fanned out by `dispatch_due_sources`.
"""

from __future__ import annotations

from typing import Any

from celery import Celery
from celery.signals import setup_logging, worker_process_shutdown
from kombu import Queue

from app.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.tasks.base import AppTask, close_loop

log = get_logger(__name__)
settings = get_settings()

QUEUES = ("collect", "enrich", "correlate", "notify", "easm")

celery_app = Celery(
    "hayabusa",
    broker=settings.redis_url,
    backend=settings.redis_url,
    task_cls="app.tasks.base:AppTask",
    include=["app.tasks.system", "app.tasks.collect"],
)

celery_app.conf.update(
    # ---------------------------------------------------------- serialisation --
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    # Store timestamps in UTC and render per-user in the UI (SPEC §5).
    timezone="UTC",
    enable_utc=True,
    # ------------------------------------------------------------- reliability --
    # SPEC §8: acknowledge only after the task finishes, so a worker killed
    # mid-run returns its task to the broker instead of dropping it. This makes
    # at-least-once delivery the contract, which is why every task must be
    # idempotent.
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    # Tasks here are long and I/O-bound; prefetching a batch would leave work
    # queued behind a slow scan on one worker while another sits idle.
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=200,  # bound memory growth in long-lived workers
    # Per-task timeouts (SPEC §8). Individual tasks tighten these.
    task_soft_time_limit=600,
    task_time_limit=900,
    broker_connection_retry_on_startup=True,
    broker_transport_options={
        # Redelivery window for tasks whose worker died without acking.
        "visibility_timeout": 3600,
    },
    result_expires=86_400,
    # ------------------------------------------------------------------ queues --
    task_default_queue="collect",
    task_queues=tuple(Queue(name) for name in QUEUES),
    task_routes={
        "app.tasks.system.*": {"queue": "collect"},
        "app.tasks.collect.*": {"queue": "collect"},
        "app.tasks.enrich.*": {"queue": "enrich"},
        "app.tasks.correlate.*": {"queue": "correlate"},
        "app.tasks.notify.*": {"queue": "notify"},
        "app.tasks.easm.*": {"queue": "easm"},
    },
    # --------------------------------------------------------------- scheduler --
    beat_scheduler="redbeat.RedBeatScheduler",
    redbeat_redis_url=settings.redis_url,
    redbeat_key_prefix="hayabusa:beat:",
    # Held by whichever beat process is active; a second beat cannot double-fire
    # while the lock is alive.
    redbeat_lock_timeout=60,
    beat_max_loop_interval=30,
    beat_schedule={
        "heartbeat": {
            "task": "app.tasks.system.heartbeat",
            "schedule": 30.0,
            "options": {"queue": "collect", "expires": 25},
        },
        "dispatch_due_sources": {
            "task": "app.tasks.collect.dispatch_due_sources",
            "schedule": 60.0,
            "options": {"queue": "collect", "expires": 55},
        },
    },
)


@setup_logging.connect
def _configure_task_logging(**_kwargs: Any) -> None:
    """Stop Celery replacing the root logging config with its own.

    Connecting to this signal disables Celery's logging setup entirely, so worker
    output goes through the same structlog pipeline as the API (SPEC §10).
    """
    configure_logging(settings)


@worker_process_shutdown.connect
def _shutdown_worker(**_kwargs: Any) -> None:
    """Release the event loop when a worker process exits (SPEC §10: graceful shutdown)."""
    close_loop()
    log.info("worker_process_shutdown")


__all__ = ["QUEUES", "AppTask", "celery_app"]
