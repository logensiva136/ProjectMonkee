"""Liveness, readiness and metrics endpoints (SPEC §7, §10).

SPEC §10 requires liveness and readiness be *separate*: `/health` says the
process is running, `/ready` says it can actually serve. Conflating them makes an
orchestrator kill a healthy API whenever a dependency hiccups.
"""

from __future__ import annotations

import json
import time
from datetime import datetime

from fastapi import APIRouter, Response, status
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app import __version__
from app.config import get_settings
from app.core.logging import get_logger
from app.core.metrics import REGISTRY
from app.core.redis import HEARTBEAT_KEY, get_redis, ping_redis
from app.db import db_server_version, ping_db
from app.models.base import utcnow
from app.schemas.health import (
    DependencyCheck,
    HealthResponse,
    HeartbeatInfo,
    ReadyResponse,
)

log = get_logger(__name__)
router = APIRouter(tags=["system"])

# The heartbeat runs every 30 s; allow a couple of missed runs before calling it
# stale so a momentarily slow worker does not flap the indicator.
HEARTBEAT_STALE_AFTER_SECONDS = 90


@router.get("/health", response_model=HealthResponse, summary="Liveness probe")
async def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        app=settings.app_name,
        version=__version__,
        environment=settings.app_env,
        time=utcnow(),
    )


async def _check(name: str, probe: object) -> DependencyCheck:
    """Time a dependency probe and turn the result into a check row."""
    started = time.perf_counter()
    try:
        ok = bool(await probe)  # type: ignore[misc]  # probe is an awaitable bool
        detail = None
    except Exception as exc:  # noqa: BLE001 - readiness reports, never raises
        ok, detail = False, str(exc)
    return DependencyCheck(
        name=name,
        ok=ok,
        latency_ms=round((time.perf_counter() - started) * 1000, 2),
        detail=detail,
    )


async def _read_heartbeat() -> HeartbeatInfo | None:
    """Load the last heartbeat stamp written by the Celery beat/worker loop."""
    try:
        raw = await get_redis().get(HEARTBEAT_KEY)
    except Exception:  # noqa: BLE001 - Redis being down is already reported below
        return None
    if not raw:
        return None

    try:
        payload = json.loads(raw)
        stamped = payload["at"]
    except (ValueError, KeyError, TypeError):
        log.warning("heartbeat_unparseable")
        return None

    at = datetime.fromisoformat(stamped)
    age = (utcnow() - at).total_seconds()
    return HeartbeatInfo(
        at=at,
        count=int(payload.get("count", 0)),
        worker=str(payload.get("worker", "unknown")),
        age_seconds=round(age, 2),
        stale=age > HEARTBEAT_STALE_AFTER_SECONDS,
    )


@router.get(
    "/ready",
    response_model=ReadyResponse,
    summary="Readiness probe",
    responses={503: {"description": "A required dependency is unreachable"}},
)
async def ready(response: Response) -> ReadyResponse:
    """Report whether Postgres and Redis are reachable.

    Returns 503 when either is down so a load balancer stops sending traffic. The
    heartbeat is reported but does *not* affect the status code: a stalled
    scheduler is an operational problem, not a reason to refuse HTTP requests.
    """
    checks = [
        await _check("database", ping_db()),
        await _check("redis", ping_redis()),
    ]
    healthy = all(check.ok for check in checks)

    if not healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return ReadyResponse(
        status="ready" if healthy else "degraded",
        checks=checks,
        heartbeat=await _read_heartbeat() if checks[1].ok else None,
        database_version=await db_server_version() if checks[0].ok else None,
    )


@router.get(
    "/metrics",
    summary="Prometheus metrics",
    response_class=Response,
    responses={200: {"content": {CONTENT_TYPE_LATEST: {}}}},
)
async def metrics() -> Response:
    """Prometheus text exposition of the SPEC §10 metric set."""
    return Response(content=generate_latest(REGISTRY), media_type=CONTENT_TYPE_LATEST)
