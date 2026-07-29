"""Redis-backed rate limiting (SPEC §6.2, §10).

Used for auth endpoints now and for Telegram's per-chat send limits in Phase 3.

The counter is a fixed window, not a sliding one. A fixed window allows a burst
straddling the boundary — up to 2x the limit across two adjacent windows — which
is a real weakness for a per-second API quota. For "5 failed logins per 15
minutes" it does not matter: an attacker gaining 10 attempts across a boundary
instead of 5 changes nothing about the economics of guessing an Argon2id-hashed
password. Fixed windows are two Redis commands and are trivially inspectable
during an incident, which is worth more here than theoretical precision.

Phase 3's Telegram limiter is per-second and *will* need a token bucket; that is
a separate function, not a change to this one.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.logging import get_logger
from app.core.redis import KEY_PREFIX, get_redis

log = get_logger(__name__)


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    remaining: int
    retry_after_seconds: int

    def __bool__(self) -> bool:
        return self.allowed


async def hit(bucket: str, identifier: str, *, limit: int, window_seconds: int) -> RateLimitResult:
    """Record an attempt and report whether it is allowed.

    `bucket` names the policy ("login", "login_ip"); `identifier` is who it
    applies to. Counting happens even when the caller is already over the limit,
    so sustained hammering keeps the window alive rather than letting it lapse.
    """
    key = f"{KEY_PREFIX}:ratelimit:{bucket}:{identifier}"
    redis = get_redis()

    # INCR then EXPIRE in one round trip. EXPIRE is set unconditionally rather
    # than only on the first hit, which is what keeps a sustained attack from
    # letting the key age out mid-attack.
    async with redis.pipeline(transaction=True) as pipe:
        pipe.incr(key)
        pipe.expire(key, window_seconds)
        results = await pipe.execute()

    count = int(results[0])
    ttl = await redis.ttl(key)
    retry_after = ttl if ttl and ttl > 0 else window_seconds

    if count > limit:
        log.warning(
            "rate_limit_exceeded",
            bucket=bucket,
            identifier=identifier,
            count=count,
            limit=limit,
        )
        return RateLimitResult(False, 0, retry_after)

    return RateLimitResult(True, max(0, limit - count), retry_after)


async def peek(bucket: str, identifier: str) -> int:
    """Current count without recording an attempt."""
    value = await get_redis().get(f"{KEY_PREFIX}:ratelimit:{bucket}:{identifier}")
    return int(value) if value else 0


async def reset(bucket: str, identifier: str) -> None:
    """Clear a counter — called after a successful login (SPEC §6.2)."""
    await get_redis().delete(f"{KEY_PREFIX}:ratelimit:{bucket}:{identifier}")
