"""Shared async Redis client.

Redis is the Celery broker, the RedBeat schedule store, the token-bucket rate
limiter for Telegram (SPEC §5.8) and the per-source collection lock (SPEC §8).
All of those go through this one lazily-created connection pool.
"""

from __future__ import annotations

from redis.asyncio import Redis

from app.config import get_settings
from app.core.logging import get_logger

log = get_logger(__name__)

# Redis key namespace. Declared here rather than at each use site so the API and
# the workers cannot drift apart on a key name.
KEY_PREFIX = "hayabusa"
HEARTBEAT_KEY = f"{KEY_PREFIX}:heartbeat"
SOURCE_LOCK_KEY = f"{KEY_PREFIX}:lock:source:{{source_id}}"
TELEGRAM_BUCKET_KEY = f"{KEY_PREFIX}:ratelimit:telegram:{{scope}}"

_client: Redis | None = None


def get_redis() -> Redis:
    """Process-wide Redis client, created on first use.

    `decode_responses=True` below means every reply arrives as `str`. Binary
    payloads would need a separate client constructed without it.
    """
    global _client
    if _client is None:
        settings = get_settings()
        _client = Redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_timeout=5,
            socket_connect_timeout=5,
            health_check_interval=30,
            retry_on_timeout=True,
        )
    return _client


async def ping_redis() -> bool:
    """True if Redis answers PING. Used by `/ready`."""
    try:
        return bool(await get_redis().ping())
    except Exception as exc:  # noqa: BLE001 - readiness must not raise
        log.warning("redis_ping_failed", error=str(exc))
        return False


async def close_redis() -> None:
    """Release the connection pool on graceful shutdown."""
    global _client
    if _client is not None:
        await _client.aclose()
        log.info("redis_client_closed")
    _client = None
