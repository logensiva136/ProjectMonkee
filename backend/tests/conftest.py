"""Shared pytest fixtures.

The environment is populated *before* `app.*` is imported anywhere, because
`get_settings()` is `lru_cache`d — the first import wins for the whole session.

From Phase 1 these tests need a real Postgres: the setup gate, RBAC and session
handling are database behaviour, and mocking them would only test the mocks.
Point `TEST_DATABASE_URL` at any Postgres 16; the schema is built and dropped
once per session.
"""

from __future__ import annotations

import asyncio
import base64
import os
import secrets
from collections.abc import AsyncIterator, Iterator

# --- environment must be set before importing the application ---------------
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("APP_SECRET_KEY", secrets.token_urlsafe(48))
os.environ.setdefault(
    "APP_ENCRYPTION_KEY",
    base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(),
)
os.environ.setdefault("LOG_FORMAT", "console")
os.environ.setdefault("LOG_LEVEL", "WARNING")
os.environ.setdefault(
    "DATABASE_URL",
    os.environ.get(
        "TEST_DATABASE_URL",
        "postgresql+asyncpg://postgres:postgres@localhost:5432/hayabusa_test",
    ),
)
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import get_settings
from app.core import setup_gate
from app.core.redis import close_redis, get_redis
from app.db import get_engine, get_sessionmaker
from app.main import create_app
from app.models import AppSetting, Base, utcnow
from app.seed import seed_all

EXTENSIONS = ("citext", "pg_trgm", "btree_gin")
_TABLES = ", ".join(f'"{table.name}"' for table in Base.metadata.sorted_tables)


async def _build_schema() -> None:
    """Drop and recreate every table, on a throwaway engine.

    `create_all` from the models rather than running Alembic: it is far faster,
    and migration correctness is checked separately by `alembic check` against a
    real database.
    """
    engine = create_async_engine(get_settings().database_url, poolclass=NullPool)
    try:
        async with engine.begin() as conn:
            # A real deployment gets these from the first migration; the test
            # schema is created straight from the models, so it needs them here.
            for extension in EXTENSIONS:
                await conn.execute(text(f'CREATE EXTENSION IF NOT EXISTS "{extension}"'))
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
    finally:
        await engine.dispose()


@pytest.fixture(scope="session", autouse=True)
def _schema() -> Iterator[None]:
    """Session-scoped schema setup.

    Synchronous on purpose. pytest-asyncio gives each test its own event loop,
    and an async session-scoped fixture would bind connections to a loop that is
    closed before the tests run. Driving the coroutine with `asyncio.run` on a
    private engine keeps this entirely self-contained.
    """
    asyncio.run(_build_schema())
    yield


@pytest.fixture(autouse=True)
async def _clean_state() -> AsyncIterator[None]:
    """Reset all shared state between tests: Postgres, Redis and process caches.

    Three things leak between tests otherwise, and each produced real failures:

    * **Rows** — TRUNCATE ... CASCADE rather than recreating the schema, which is
      an order of magnitude faster.
    * **Redis** — rate-limit counters are keyed by username, so without a flush
      the lockout tests poison every later login for the same user. The client
      is also *closed*: pytest-asyncio gives each test its own event loop, and a
      cached connection belongs to the loop that opened it, so reusing it raises
      "Event loop is closed".
    * **The setup-gate cache** — process-global, so one test completing
      onboarding would otherwise open the gate for every test after it.

    The Redis flush targets database 15 (see REDIS_URL above), never the default.
    """
    setup_gate.reset_setup_cache()
    await get_redis().flushdb()

    yield

    async with get_engine().begin() as conn:
        await conn.execute(text(f"TRUNCATE {_TABLES} RESTART IDENTITY CASCADE"))
    await get_redis().flushdb()
    await close_redis()


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    """A committing session, for arranging test data directly."""
    async with get_sessionmaker()() as db:
        yield db
        await db.commit()


@pytest.fixture
async def seeded(session: AsyncSession) -> None:
    """Permissions, roles and panels, as a real instance has after boot."""
    await seed_all(session)
    await session.commit()


@pytest.fixture
async def onboarded(session: AsyncSession, seeded: None) -> AppSetting:
    """An instance that has been through onboarding.

    Most tests need this: without it the SPEC §6.1 gate answers 409 to every
    route, which is correct but makes it impossible to test anything else.
    """
    setting = AppSetting(
        org_name="Test Bank Sdn Bhd",
        org_initials="TB",
        setup_completed_at=utcnow(),
    )
    session.add(setting)
    await session.commit()
    setup_gate.mark_setup_complete()
    return setting


@pytest.fixture(scope="session")
def app():  # type: ignore[no-untyped-def]
    return create_app()


@pytest.fixture
async def client(app) -> AsyncIterator[AsyncClient]:  # type: ignore[no-untyped-def]
    """HTTP client speaking to the app in-process — no network, no live server."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
