"""System maintenance tasks.

`heartbeat` is the Phase 0 proof that beat -> broker -> worker is a closed loop
(SPEC §12). It is not throwaway scaffolding: once the collectors in SPEC §8 are
scheduled, a stale heartbeat is the signal that the scheduler has stalled, and a
stalled scheduler means collection has silently stopped — the failure mode a
monitoring platform can least afford.
"""

from __future__ import annotations

import json
import socket
from typing import Any

from app.core.logging import get_logger
from app.core.redis import HEARTBEAT_KEY, get_redis
from app.db import ping_db
from app.models.base import utcnow
from app.tasks.base import run_async
from app.tasks.celery_app import celery_app

log = get_logger(__name__)

# Comfortably longer than the 30 s schedule, so a single missed run still leaves
# the key readable (and visibly stale) rather than making it vanish.
HEARTBEAT_TTL_SECONDS = 300


@celery_app.task(
    name="app.tasks.system.heartbeat",
    bind=True,
    # A heartbeat that retries is lying about when it ran; let it fail and let
    # the next scheduled run tell the truth.
    autoretry_for=(),
    max_retries=0,
    soft_time_limit=20,
    time_limit=30,
)
def heartbeat(self: Any) -> dict[str, Any]:
    """Stamp Redis with the current time so `/ready` can prove the loop is alive."""

    async def _run() -> dict[str, Any]:
        redis = get_redis()
        database_ok = await ping_db()

        # INCR then read: the counter makes it obvious at a glance whether the
        # beat has been running steadily or was only just started.
        count = await redis.incr(f"{HEARTBEAT_KEY}:count")

        payload = {
            "at": utcnow().isoformat(),
            "count": count,
            "worker": socket.gethostname(),
            "task_id": self.request.id,
            "database_ok": database_ok,
        }
        await redis.set(HEARTBEAT_KEY, json.dumps(payload), ex=HEARTBEAT_TTL_SECONDS)
        return payload

    result = run_async(_run())
    log.info("heartbeat", count=result["count"], database_ok=result["database_ok"])
    return result
