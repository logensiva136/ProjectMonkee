"""HTTP middleware: request correlation, access logging, metrics, security headers.

Ordering note — Starlette runs middleware in reverse registration order, so
`RequestContextMiddleware` is added last in `create_app` to make it outermost.
That way the request ID exists before anything else runs and is still bound when
the error handlers build a problem+json body.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp
from uuid6 import uuid7

from app.core.context import reset_request_id, set_request_id
from app.core.logging import get_logger
from app.core.metrics import HTTP_REQUEST_DURATION, HTTP_REQUESTS

log = get_logger(__name__)

REQUEST_ID_HEADER = "X-Request-ID"

# Probe endpoints are hit every few seconds by Docker/Kubernetes; logging them
# would drown everything else.
_QUIET_PATHS = frozenset({"/health", "/ready", "/metrics", "/api/v1/health", "/api/v1/ready"})

Handler = Callable[[Request], Awaitable[Response]]


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Assign a correlation ID, time the request, log it, and record metrics."""

    async def dispatch(self, request: Request, call_next: Handler) -> Response:
        # Honour an upstream ID so a trace survives crossing the proxy, but only
        # if it is short enough not to be a log-injection vector.
        inbound = request.headers.get(REQUEST_ID_HEADER, "")
        request_id = inbound if 0 < len(inbound) <= 64 else str(uuid7())

        token = set_request_id(request_id)
        # Also stash it on the request. Starlette's ServerErrorMiddleware sits
        # *outside* this one, so by the time it handles an unexpected exception
        # the `finally` below has already reset the contextvar — `request.state`
        # is what lets the 500 body still carry the correlation ID.
        request.state.request_id = request_id
        started = time.perf_counter()
        status_code = 500

        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers[REQUEST_ID_HEADER] = request_id
            return response
        finally:
            duration = time.perf_counter() - started

            # Use the matched route template ("/vendors/{id}") rather than the
            # raw path, or every distinct ID would become its own metric series.
            route = request.scope.get("route")
            route_label = getattr(route, "path", None) or "unmatched"

            HTTP_REQUESTS.labels(request.method, route_label, str(status_code)).inc()
            HTTP_REQUEST_DURATION.labels(request.method, route_label).observe(duration)

            if request.url.path not in _QUIET_PATHS:
                log.info(
                    "http_request",
                    method=request.method,
                    path=request.url.path,
                    route=route_label,
                    status=status_code,
                    duration_ms=round(duration * 1000, 2),
                    client=request.client.host if request.client else None,
                )
            reset_request_id(token)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Defence-in-depth headers on API responses (SPEC §10).

    Nginx sets the full policy — including CSP — for the HTML the browser loads;
    these cover the API when it is reached directly, e.g. during `make dev` or by
    a scanner probing the api port.
    """

    def __init__(self, app: ASGIApp, *, hsts: bool = False) -> None:
        super().__init__(app)
        self.hsts = hsts

    async def dispatch(self, request: Request, call_next: Handler) -> Response:
        response = await call_next(request)
        headers = response.headers
        headers.setdefault("X-Content-Type-Options", "nosniff")
        headers.setdefault("X-Frame-Options", "DENY")
        headers.setdefault("Referrer-Policy", "no-referrer")
        headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
        if self.hsts:
            headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return response
