"""Audit trail (SPEC §5.1, §6.3).

Every mutating action records who did what, to which entity, and what changed.
The row is written in the *same transaction* as the change it describes, so an
action can never be applied without its audit entry, nor logged without having
happened.

`actor_username` is denormalised alongside `actor_id` so the trail stays legible
after an account is deleted — an audit log full of orphaned UUIDs answers no
questions during an incident review.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import get_request_id
from app.core.logging import get_logger
from app.models.identity import AuditLog, User

log = get_logger(__name__)

# Field names never written into `before`/`after`. The audit log is widely
# readable (`audit:read`), so a password hash or TOTP secret must not leak into
# it via a naive model dump.
_REDACTED_FIELDS = frozenset(
    {
        "password",
        "password_hash",
        "new_password",
        "current_password",
        "totp_secret",
        "totp_secret_encrypted",
        "token",
        "token_hash",
        "token_encrypted",
        "code_hash",
        "credentials_encrypted",
        "recovery_codes",
    }
)


def scrub(data: dict[str, Any] | None) -> dict[str, Any] | None:
    """Drop secret-bearing keys before they reach the audit table."""
    if data is None:
        return None
    return {
        key: ("***redacted***" if key in _REDACTED_FIELDS else value) for key, value in data.items()
    }


def changed_fields(
    before: dict[str, Any] | None, after: dict[str, Any] | None
) -> dict[str, Any] | None:
    """Reduce a pair of snapshots to just what differs.

    Storing whole objects on both sides makes the diff viewer show a hundred
    unchanged fields around the one that matters.
    """
    if before is None or after is None:
        return after
    return {key: value for key, value in after.items() if before.get(key) != value}


async def record(
    session: AsyncSession,
    *,
    action: str,
    actor: User | None = None,
    entity_type: str | None = None,
    entity_id: str | uuid.UUID | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    request: Request | None = None,
) -> AuditLog:
    """Append an audit row. Added to the caller's transaction, not committed here.

    `action` is a dotted verb phrase — `user.created`, `role.permissions_changed`,
    `auth.login_failed` — so the audit screen can filter by prefix.
    """
    entry = AuditLog(
        actor_id=actor.id if actor else None,
        actor_username=actor.username if actor else None,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
        before=scrub(before),
        after=scrub(after),
        ip=client_ip(request),
        ua=(request.headers.get("user-agent") if request else None),
        request_id=get_request_id(),
    )
    session.add(entry)

    log.info(
        "audit",
        action=action,
        actor=actor.username if actor else None,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
    )
    return entry


def client_ip(request: Request | None) -> str | None:
    """Best-effort client address.

    Prefers `X-Forwarded-For`'s first entry, which nginx sets. That header is
    caller-controlled when the app is reached directly, so this is good enough
    for an audit trail and rate limiting but is not an authorization input.
    """
    if request is None:
        return None

    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        candidate = forwarded.split(",")[0].strip()
        if candidate:
            return candidate

    return request.client.host if request.client else None
