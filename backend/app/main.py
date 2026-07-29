"""FastAPI application factory.

Run with:
    uvicorn app.main:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.v1 import api_router
from app.api.v1.health import health, metrics, ready
from app.config import Settings, get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging, get_logger
from app.core.middleware import RequestContextMiddleware, SecurityHeadersMiddleware
from app.core.redis import close_redis
from app.db import dispose_engine

API_V1_PREFIX = "/api/v1"

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:  # noqa: ARG001 - FastAPI's signature
    """Start-up and graceful shutdown (SPEC §10).

    Connections are opened lazily on first use rather than here, so the API can
    start and report *why* it is not ready instead of crash-looping when Postgres
    is a few seconds behind it in the boot order.
    """
    settings: Settings = get_settings()
    log.info(
        "api_starting",
        app=settings.app_name,
        version=__version__,
        environment=settings.app_env,
        timezone=settings.app_timezone,
    )
    try:
        yield
    finally:
        await dispose_engine()
        await close_redis()
        log.info("api_stopped")


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings)

    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        summary="Threat intelligence, third-party risk and external attack surface monitoring",
        lifespan=lifespan,
        # SPEC §7: docs at /api/docs. The schema path is also what SPEC §9.0
        # Rule 0 points `openapi-typescript` at to generate frontend types.
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url=f"{API_V1_PREFIX}/openapi.json",
    )

    # --- middleware -------------------------------------------------------
    # Starlette applies middleware in reverse registration order, so the last
    # one added is the outermost. RequestContextMiddleware must be outermost:
    # it establishes the correlation ID everything else logs against.
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,  # refresh token travels as a cookie (SPEC §6.2)
            allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
            expose_headers=["X-Request-ID"],
            max_age=600,
        )
    app.add_middleware(SecurityHeadersMiddleware, hsts=settings.is_production)
    app.add_middleware(RequestContextMiddleware)

    register_exception_handlers(app)

    # --- routes -----------------------------------------------------------
    app.include_router(api_router, prefix=API_V1_PREFIX)

    # Probe endpoints are also served unprefixed for container healthchecks and
    # load balancers (DECISIONS.md D-006). Excluded from the OpenAPI schema so
    # the generated frontend types contain no duplicates.
    app.add_api_route("/health", health, methods=["GET"], include_in_schema=False)
    app.add_api_route("/ready", ready, methods=["GET"], include_in_schema=False)
    app.add_api_route("/metrics", metrics, methods=["GET"], include_in_schema=False)

    return app


app = create_app()
