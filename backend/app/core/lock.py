"""Redis distributed locks, used to keep two workers from colliding on the same
source (SPEC §8).

A plain `SET key value NX EX seconds` — the textbook Redis lock. It is not the
Redlock algorithm (no multi-node quorum, no fencing token) and does not need to
be: the failure mode of two collectors racing on one source for a few seconds
is a handful of duplicate-key errors the dedupe layer already absorbs, not data
loss. Redlock's complexity buys correctness properties this use case does not
need.

The lock auto-expires, so a worker that crashes mid-collection cannot leave a
source permanently stuck — the lock frees itself and the next scheduled attempt
proceeds.
"""

from __future__ import annotations

import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from app.core.logging import get_logger
from app.core.redis import get_redis

log = get_logger(__name__)

# Longer than any single collection run should ever take (SPEC §8 gives tasks a
# soft/hard time limit well under this), so a lock never expires while its
# holder is still legitimately working — it exists purely to survive a crash.
DEFAULT_LOCK_TTL_SECONDS = 900

# Lua so "is this still my token?" and "delete it" happen as one atomic
# operation. Without that, a worker could time out, have Redis expire its lock,
# lose it to a second worker, and then delete the SECOND worker's lock on its
# own delayed cleanup — releasing a lock that had already moved on to protect
# something else.
_RELEASE_SCRIPT = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
else
    return 0
end
"""


@asynccontextmanager
async def try_lock(key: str, *, ttl_seconds: int = DEFAULT_LOCK_TTL_SECONDS) -> AsyncIterator[bool]:
    """Attempt to acquire `key`. Yields whether it was acquired.

    Never blocks waiting for a lock held by someone else — a source that is
    already being collected should be skipped this cycle, not queued behind the
    worker holding it.

        async with try_lock(key) as acquired:
            if not acquired:
                return
            ...
    """
    token = secrets.token_urlsafe(16)
    redis = get_redis()

    acquired = bool(await redis.set(key, token, nx=True, ex=ttl_seconds))
    try:
        yield acquired
    finally:
        if acquired:
            try:
                # redis.asyncio's eval typing returns Awaitable[str] | str depending on
                # the client; awaiting the call works at runtime and we ignore the
                # imprecise stub.
                await redis.eval(_RELEASE_SCRIPT, 1, key, token)  # type: ignore[misc]
            except Exception as exc:  # noqa: BLE001 — releasing must not mask the caller's outcome
                # Not fatal: the TTL still bounds how long the lock survives.
                log.warning("lock_release_failed", key=key, error=str(exc))
