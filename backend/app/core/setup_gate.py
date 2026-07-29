"""First-run gate (SPEC §6.1).

Until onboarding completes, every route except `/setup/*` and the probes answers
409. After it completes, `/setup/*` answers 410 forever.

Implemented as middleware rather than a per-router dependency deliberately: a
dependency has to be remembered on every new router, and the one time it is
forgotten is the time an un-onboarded instance exposes an endpoint. Middleware
covers routes that do not exist yet.

The completion flag is cached in the process once true. Setup is a one-way
transition — there is no supported path back to "not set up" — so the cache
never needs invalidating, and after the first request the gate costs nothing.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from sqlalchemy import select
from starlette.requests import Request
from starlette.responses import Response

from app.core.errors import problem_response
from app.core.logging import get_logger
from app.models.identity import AppSetting

log = get_logger(__name__)

# Reachable before onboarding. Probes must answer so a container does not look
# dead, and the docs must render so the API is explorable.
_EXEMPT_EXACT = frozenset(
    {
        "/health",
        "/ready",
        "/metrics",
        "/api/v1/health",
        "/api/v1/ready",
        "/api/v1/metrics",
        "/api/docs",
        "/api/redoc",
        "/api/docs/oauth2-redirect",
        "/api/v1/openapi.json",
    }
)
# Trailing slash matters. A bare "/api/v1/setup" prefix would also exempt
# "/api/v1/setupx" — and any future route whose name merely starts with "setup"
# would silently bypass the gate.
_EXEMPT_PREFIXES = ("/api/v1/setup/",)
_EXEMPT_EXACT_SETUP = "/api/v1/setup"

# None = not yet checked. True = complete (cached forever). False = re-check.
_setup_complete: bool | None = None


def path_is_exempt(path: str) -> bool:
    normalised = path.rstrip("/") or "/"
    if normalised in _EXEMPT_EXACT or normalised == _EXEMPT_EXACT_SETUP:
        return True
    return path.startswith(_EXEMPT_PREFIXES)


async def setup_is_complete() -> bool:
    """True once `app_setting.setup_completed_at` has been stamped."""
    global _setup_complete
    if _setup_complete:
        return True

    # Imported here rather than at module scope so importing this module does
    # not construct the engine (which would open sockets at import time).
    from app.db import get_sessionmaker

    async with get_sessionmaker()() as session:
        result = await session.execute(select(AppSetting.setup_completed_at).limit(1))
        completed_at = result.scalar_one_or_none()

    _setup_complete = completed_at is not None
    return _setup_complete


def mark_setup_complete() -> None:
    """Flip the cached flag the moment onboarding succeeds.

    Called by the setup service inside the same request that completes the
    wizard, so the auto-login response that follows is not itself blocked by
    the gate it just satisfied.
    """
    global _setup_complete
    _setup_complete = True
    log.info("setup_gate_opened")


def reset_setup_cache() -> None:
    """Clear the cached flag. Used by tests, which rebuild the database."""
    global _setup_complete
    _setup_complete = None


async def setup_gate_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Refuse ordinary traffic while the instance has not been onboarded."""
    if path_is_exempt(request.url.path):
        return await call_next(request)

    try:
        complete = await setup_is_complete()
    except Exception as exc:  # noqa: BLE001 - the gate must not 500 on a DB blip
        # Fail closed, and say so accurately: the instance is unavailable, not
        # un-onboarded. Answering 409 here would send an already-configured
        # instance's users back to the setup wizard during a database outage.
        log.error("setup_gate_check_failed", error=str(exc))
        return problem_response(
            request,
            status_code=503,
            title="Service Unavailable",
            detail="The database is unreachable. See /ready for dependency status.",
            problem_type="service-unavailable",
        )

    if complete:
        return await call_next(request)

    return problem_response(
        request,
        status_code=409,
        title="Setup Required",
        detail="This instance has not been set up yet. Complete onboarding at /setup.",
        problem_type="setup-required",
    )
