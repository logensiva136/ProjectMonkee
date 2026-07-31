"""Async database engine and session management (SQLAlchemy 2.0 + asyncpg).

One engine per process, created lazily so that importing this module does not
open sockets — which matters for Alembic and for tests that swap the URL.

Request handlers take `session: AsyncSession = Depends(get_session)`. That
dependency owns the transaction boundary: it commits when the handler returns
normally and rolls back if it raises, so service code never has to remember to.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.config import get_settings
from app.core.logging import get_logger

log = get_logger(__name__)

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """Process-wide engine, created on first use."""
    global _engine
    if _engine is None:
        settings = get_settings()

        # Under pytest each test gets its own event loop, and a pooled asyncpg
        # connection is bound to the loop that opened it — so a pooled engine
        # hands the second test a connection attached to a closed loop. NullPool
        # opens and closes per use, which is slower but correct.
        pool_kwargs: dict[str, Any] = (
            {"poolclass": NullPool}
            if settings.app_env == "test"
            else {
                "pool_size": settings.db_pool_size,
                "max_overflow": settings.db_max_overflow,
                "pool_timeout": settings.db_pool_timeout_seconds,
            }
        )

        _engine = create_async_engine(
            settings.database_url,
            echo=settings.db_echo,
            **pool_kwargs,
            # Recycle below typical proxy/firewall idle timeouts, and verify a
            # connection before handing it out so a server restart surfaces as a
            # brief reconnect rather than a burst of errors. Both are no-ops
            # under NullPool, which never reuses a connection anyway.
            pool_recycle=settings.db_pool_recycle_seconds,
            pool_pre_ping=True,
            connect_args={
                "server_settings": {
                    "application_name": settings.app_name.lower(),
                    "timezone": "UTC",
                },
                # asyncpg caches prepared statements per connection; PgBouncer in
                # transaction mode cannot support that. Disabled defensively so
                # deployments can put a pooler in front without a code change.
                "statement_cache_size": 0,
            },
        )
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(
            bind=get_engine(),
            expire_on_commit=False,  # keep ORM objects usable after commit
            autoflush=False,
        )
    return _sessionmaker


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding a session wrapped in a transaction.

    The `async with` block closes the session on the way out no matter what, and
    the explicit commit/rollback makes the write boundary one obvious place.
    """
    async with get_sessionmaker()() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        else:
            await session.commit()


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """Same contract as `get_session`, for code outside the request cycle.

    Celery tasks use this via `async with session_scope() as session`.
    """
    async for session in get_session():
        yield session


async def ping_db() -> bool:
    """True if the database answers a trivial query. Used by `/ready`."""
    try:
        async with get_engine().connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception as exc:  # noqa: BLE001 - readiness must not raise
        log.warning("db_ping_failed", error=str(exc))
        return False


async def db_server_version() -> str | None:
    try:
        async with get_engine().connect() as conn:
            result = await conn.execute(text("SHOW server_version"))
            value: Any = result.scalar()
            return str(value) if value is not None else None
    except Exception:  # noqa: BLE001 - informational only
        return None


async def dispose_engine() -> None:
    """Close every pooled connection. Called on graceful shutdown (SPEC §10)."""
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
        log.info("db_engine_disposed")
    _engine = None
    _sessionmaker = None
