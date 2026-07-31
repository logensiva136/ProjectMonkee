"""Scheduled and on-demand collection tasks (SPEC §8).

`dispatch_due_sources` runs every minute from RedBeat. It selects sources whose
`next_poll_at` has passed and fans out one `collect_source` task per source.
`collect_source` takes a per-source Redis lock so two workers never run the same
source concurrently — the lock is the orchestration boundary, while
`run_collection` is the persistence logic.
"""

from __future__ import annotations

import uuid
from typing import Any

from app.core.logging import get_logger
from app.core.redis import SOURCE_LOCK_KEY, get_redis
from app.db import session_scope
from app.models.collection import Source, SourceRun
from app.models.enums import RunStatus
from app.services.collection import run_collection
from app.tasks.base import run_async
from app.tasks.celery_app import celery_app

log = get_logger(__name__)

# Long enough to cover a slow feed parse, but short enough that a killed worker
# does not stall a source for minutes.
SOURCE_LOCK_TTL_SECONDS = 300


@celery_app.task(
    name="app.tasks.collect.dispatch_due_sources",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=60,
    max_retries=3,
    soft_time_limit=55,
    time_limit=60,
)
def dispatch_due_sources(_self: Any) -> dict[str, Any]:
    """Schedule one `collect_source` task for every due source."""

    async def _run() -> dict[str, Any]:
        from sqlalchemy import select

        from app.models.base import utcnow

        dispatched = 0
        skipped = 0

        async with session_scope() as session:
            result = await session.execute(
                select(Source)
                .where(
                    Source.deleted_at.is_(None),
                    Source.enabled.is_(True),
                    Source.next_poll_at <= utcnow(),
                )
                .order_by(Source.next_poll_at)
            )
            due_sources = result.scalars().all()

        for source in due_sources:
            redis = get_redis()
            lock_key = SOURCE_LOCK_KEY.format(source_id=str(source.id))
            acquired = await redis.set(lock_key, "1", nx=True, ex=SOURCE_LOCK_TTL_SECONDS)
            if not acquired:
                skipped += 1
                log.debug("source_already_locked", source_id=str(source.id))
                continue

            collect_source.delay(str(source.id))
            dispatched += 1

        log.info(
            "dispatch_due_sources",
            dispatched=dispatched,
            skipped=skipped,
            due=len(due_sources),
        )
        return {"dispatched": dispatched, "skipped": skipped, "due": len(due_sources)}

    return run_async(_run())


@celery_app.task(
    name="app.tasks.collect.collect_source",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    max_retries=2,
    soft_time_limit=240,
    time_limit=300,
)
def collect_source(_self: Any, source_id: str) -> dict[str, Any]:
    """Collect a single source and release its lock."""

    async def _run() -> dict[str, Any]:
        from sqlalchemy import select

        from app.core.metrics import COLLECTION_RUNS

        async with session_scope() as session:
            result = await session.execute(
                select(Source).where(
                    Source.id == uuid.UUID(source_id),
                    Source.deleted_at.is_(None),
                    Source.enabled.is_(True),
                )
            )
            source = result.scalar_one_or_none()
            if source is None:
                log.warning("collect_source_missing", source_id=source_id)
                return {"status": "missing", "source_id": source_id}

            try:
                outcome = await run_collection(session, source)
            except Exception as exc:
                # Defensive: run_collection should handle its own exceptions, but
                # a task failure must still release the lock.
                log.error(
                    "collect_source_failed",
                    source_id=source_id,
                    error=str(exc),
                    exc_info=exc,
                )
                # Force a run row in failed state if none was committed.
                run = SourceRun(
                    source_id=source.id,
                    status=RunStatus.FAILED,
                    error=f"{type(exc).__name__}: {exc}",
                )
                session.add(run)
                await session.commit()
                COLLECTION_RUNS.labels(source.type, RunStatus.FAILED).inc()
                return {"status": "failed", "source_id": source_id, "error": str(exc)}

            return {
                "source_id": source_id,
                "status": outcome.run.status,
                "items_seen": outcome.items_seen,
                "items_new": outcome.items_new,
            }

    try:
        return run_async(_run())
    finally:
        # Release the lock even if the task raised. The async run is inside
        # run_async, so the lock release must be async too.
        async def _release() -> None:
            await get_redis().delete(SOURCE_LOCK_KEY.format(source_id=source_id))

        run_async(_release())
