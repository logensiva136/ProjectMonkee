"""Shared pytest fixtures.

The environment is populated *before* `app.*` is imported anywhere, because
`get_settings()` is `lru_cache`d — the first import wins for the whole session.
"""

from __future__ import annotations

import base64
import os
import secrets
from collections.abc import AsyncIterator

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
    "DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/hayabusa_test"
)
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app


@pytest.fixture(scope="session")
def app():  # type: ignore[no-untyped-def]
    return create_app()


@pytest.fixture
async def client(app) -> AsyncIterator[AsyncClient]:  # type: ignore[no-untyped-def]
    """HTTP client speaking to the app in-process — no network, no live server."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
