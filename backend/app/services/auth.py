"""Authentication: login, MFA, session issue and refresh rotation (SPEC §6.2).

The refresh-token design is the part worth understanding.

Each login opens a *family*. Every refresh issues a new token in that family and
revokes the one presented. If a token that has already been revoked is presented
again, exactly one thing can have happened: the token was captured and replayed
(the legitimate client only ever holds the newest one). The response is to
revoke the entire family, which logs the real user out too. That is deliberate —
a forced re-login is a far better outcome than leaving a live session in an
attacker's hands.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass
from typing import Any, cast

from fastapi import Request, Response
from sqlalchemy import select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.core import ratelimit
from app.core.crypto import decrypt
from app.core.errors import RateLimitedError, UnauthorizedError
from app.core.logging import get_logger
from app.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    password_needs_rehash,
    verify_password,
    verify_recovery_code,
    verify_totp,
)
from app.models.base import utcnow
from app.models.identity import RecoveryCode, RefreshToken, User
from app.models.rbac import Role
from app.services import audit

log = get_logger(__name__)

REFRESH_COOKIE_NAME = "hayabusa_refresh"

# Rate-limit buckets (SPEC §6.2: 5 failures per username per 15 min, plus per-IP).
_BUCKET_USER = "login_user"
_BUCKET_IP = "login_ip"
_IP_LIMIT = 30  # a shared office NAT must not lock out a whole floor


@dataclass(frozen=True)
class TokenPair:
    access_token: str
    refresh_token: str
    expires_in: int


async def _load_user_by_username(session: AsyncSession, username: str) -> User | None:
    result = await session.execute(
        select(User)
        .where(User.username == username, User.deleted_at.is_(None))
        .options(selectinload(User.roles).selectinload(Role.permissions))
    )
    return result.scalar_one_or_none()


async def load_user(session: AsyncSession, user_id: uuid.UUID) -> User | None:
    result = await session.execute(
        select(User)
        .where(User.id == user_id, User.deleted_at.is_(None))
        .options(selectinload(User.roles).selectinload(Role.permissions))
    )
    return result.scalar_one_or_none()


# --------------------------------------------------------------------------- #
# Password step
# --------------------------------------------------------------------------- #


async def authenticate(
    session: AsyncSession,
    username: str,
    password: str,
    *,
    request: Request | None = None,
) -> User:
    """Verify username and password, applying lockout and rate limits.

    Every failure path raises the *same* error with the same message. Telling an
    attacker "no such user" versus "wrong password" hands them a free account
    enumeration oracle.
    """
    settings = get_settings()
    normalised = username.strip().lower()
    ip = audit.client_ip(request) or "unknown"

    ip_result = await ratelimit.hit(
        _BUCKET_IP, ip, limit=_IP_LIMIT, window_seconds=settings.lockout_minutes * 60
    )
    if not ip_result:
        raise RateLimitedError(
            "Too many sign-in attempts from this address. Try again shortly.",
            retry_after=ip_result.retry_after_seconds,
        )

    user_result = await ratelimit.hit(
        _BUCKET_USER,
        normalised,
        limit=settings.max_failed_logins,
        window_seconds=settings.lockout_minutes * 60,
    )
    if not user_result:
        raise RateLimitedError(
            f"Too many failed attempts. Try again in "
            f"{max(1, user_result.retry_after_seconds // 60)} minutes.",
            retry_after=user_result.retry_after_seconds,
        )

    user = await _load_user_by_username(session, normalised)
    invalid = UnauthorizedError("Incorrect username or password.")

    if user is None:
        # Still burn time on a hash so the response time does not reveal whether
        # the username exists. Argon2id at 64 MiB is ~50 ms; without this, a
        # missing user would answer in ~2 ms and enumeration would be trivial.
        hash_password(password)
        log.info("login_failed", username=normalised, reason="no_such_user", ip=ip)
        raise invalid

    if user.is_locked:
        remaining = int((user.locked_until - utcnow()).total_seconds()) if user.locked_until else 0
        log.warning("login_blocked", username=normalised, reason="locked", ip=ip)
        raise RateLimitedError(
            f"This account is locked. Try again in {max(1, remaining // 60)} minutes.",
            retry_after=max(remaining, 60),
        )

    if not verify_password(password, user.password_hash):
        user.failed_login_count += 1
        if user.failed_login_count >= settings.max_failed_logins:
            user.locked_until = utcnow() + dt.timedelta(minutes=settings.lockout_minutes)
            log.warning("account_locked", username=normalised, ip=ip)
            await audit.record(
                session,
                action="auth.account_locked",
                entity_type="user",
                entity_id=user.id,
                after={"failed_login_count": user.failed_login_count},
                request=request,
            )
        log.info("login_failed", username=normalised, reason="bad_password", ip=ip)

        # COMMIT BEFORE RAISING. The `get_session` dependency rolls back when a
        # handler raises, which would undo the increment along with the 401 — so
        # the counter would reset on every failure and the account would never
        # lock. Persisting it here is the whole mechanism, not an optimisation.
        await session.commit()
        raise invalid

    if not user.is_active:
        log.warning("login_blocked", username=normalised, reason="inactive", ip=ip)
        raise UnauthorizedError("This account has been disabled.")

    # Success: clear the counters so a user who mistyped twice is not one typo
    # away from a lockout for the rest of the window.
    user.failed_login_count = 0
    user.locked_until = None
    await ratelimit.reset(_BUCKET_USER, normalised)

    # Transparent upgrade if the Argon2 cost parameters have since been raised.
    if password_needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
        log.info("password_rehashed", username=normalised)

    return user


# --------------------------------------------------------------------------- #
# Second factor
# --------------------------------------------------------------------------- #


async def verify_second_factor(
    session: AsyncSession, user: User, code: str, *, request: Request | None = None
) -> None:
    """Accept a TOTP code or a single-use recovery code (SPEC §6.2)."""
    if not user.totp_enabled or not user.totp_secret_encrypted:
        raise UnauthorizedError("Two-factor authentication is not configured for this account.")

    secret = decrypt(user.totp_secret_encrypted)
    if verify_totp(secret, code):
        return

    if await _consume_recovery_code(session, user, code, request=request):
        return

    log.warning("mfa_failed", username=user.username)
    raise UnauthorizedError("That code is not valid.")


async def _consume_recovery_code(
    session: AsyncSession, user: User, code: str, *, request: Request | None = None
) -> bool:
    """Spend a recovery code if it matches an unused one.

    Codes are Argon2-hashed, so this compares against each unused hash in turn.
    With ten codes that is ten hashes worst case — acceptable on a path that is
    used a handful of times in an account's life.
    """
    result = await session.execute(
        select(RecoveryCode).where(RecoveryCode.user_id == user.id, RecoveryCode.used_at.is_(None))
    )
    for candidate in result.scalars():
        if verify_recovery_code(code, candidate.code_hash):
            candidate.used_at = utcnow()
            remaining = await session.execute(
                select(RecoveryCode).where(
                    RecoveryCode.user_id == user.id, RecoveryCode.used_at.is_(None)
                )
            )
            left = len(remaining.scalars().all()) - 0
            log.warning("recovery_code_used", username=user.username, remaining=left)
            await audit.record(
                session,
                action="auth.recovery_code_used",
                actor=user,
                entity_type="user",
                entity_id=user.id,
                after={"remaining_codes": left},
                request=request,
            )
            return True
    return False


# --------------------------------------------------------------------------- #
# Sessions
# --------------------------------------------------------------------------- #


async def issue_session(
    session: AsyncSession,
    user: User,
    *,
    request: Request | None = None,
    family_id: uuid.UUID | None = None,
) -> TokenPair:
    """Mint an access token and a refresh token, persisting the refresh side.

    Pass `family_id` to continue an existing family during rotation; omit it to
    start a new one at login.
    """
    settings = get_settings()
    raw_refresh = generate_refresh_token()

    record = RefreshToken(
        user_id=user.id,
        token_hash=hash_refresh_token(raw_refresh),
        family_id=family_id or uuid.uuid4(),
        expires_at=utcnow() + dt.timedelta(days=settings.refresh_token_ttl_days),
        user_agent=(request.headers.get("user-agent") if request else None),
        ip=audit.client_ip(request),
    )
    session.add(record)

    user.last_login_at = utcnow()

    return TokenPair(
        access_token=create_access_token(user.id),
        refresh_token=raw_refresh,
        expires_in=settings.access_token_ttl_minutes * 60,
    )


async def rotate_refresh_token(
    session: AsyncSession, raw_token: str, *, request: Request | None = None
) -> tuple[User, TokenPair]:
    """Exchange a refresh token for a new pair, detecting replay.

    See the module docstring for why a replayed token revokes the whole family.
    """
    token_hash = hash_refresh_token(raw_token)
    result = await session.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    stored = result.scalar_one_or_none()

    if stored is None:
        log.warning("refresh_unknown_token")
        raise UnauthorizedError("Session expired. Please sign in again.")

    if stored.revoked_at is not None:
        # Replay. The legitimate client only ever holds the newest token, so a
        # revoked one being presented means it leaked.
        await revoke_family(session, stored.family_id, reason="reuse_detected")
        log.error(
            "refresh_reuse_detected",
            user_id=str(stored.user_id),
            family_id=str(stored.family_id),
        )
        await audit.record(
            session,
            action="auth.refresh_reuse_detected",
            entity_type="user",
            entity_id=stored.user_id,
            after={"family_id": str(stored.family_id), "ip": audit.client_ip(request)},
            request=request,
        )

        # COMMIT BEFORE RAISING, for the same reason as the lockout counter in
        # `authenticate`: the request is about to fail with a 401, and the
        # session dependency rolls back on exception. Without this the family
        # revocation is silently undone and the stolen session keeps working —
        # which would make reuse detection a log line and nothing more.
        await session.commit()
        raise UnauthorizedError("Session is no longer valid. Please sign in again.")

    if stored.expires_at <= utcnow():
        raise UnauthorizedError("Session expired. Please sign in again.")

    user = await load_user(session, stored.user_id)
    if user is None or not user.is_active:
        raise UnauthorizedError("Account is unavailable.")

    stored.revoked_at = utcnow()
    stored.revoked_reason = "rotated"
    stored.last_used_at = utcnow()

    pair = await issue_session(session, user, request=request, family_id=stored.family_id)
    return user, pair


async def revoke_family(session: AsyncSession, family_id: uuid.UUID, *, reason: str) -> int:
    """Revoke every live token in a family. Returns how many were affected."""
    result = await session.execute(
        update(RefreshToken)
        .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=utcnow(), revoked_reason=reason)
    )
    # `rowcount` lives on CursorResult, which is what an UPDATE returns; the
    # declared `Result` type does not carry it.
    return int(cast("CursorResult[Any]", result).rowcount or 0)


async def revoke_token(session: AsyncSession, raw_token: str, *, reason: str) -> None:
    """Revoke a single token — the logout path."""
    await session.execute(
        update(RefreshToken)
        .where(
            RefreshToken.token_hash == hash_refresh_token(raw_token),
            RefreshToken.revoked_at.is_(None),
        )
        .values(revoked_at=utcnow(), revoked_reason=reason)
    )


async def revoke_all_for_user(
    session: AsyncSession, user_id: uuid.UUID, *, reason: str, except_id: uuid.UUID | None = None
) -> int:
    """Revoke every live session for a user, optionally sparing the current one."""
    statement = update(RefreshToken).where(
        RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None)
    )
    if except_id is not None:
        statement = statement.where(RefreshToken.id != except_id)

    result = await session.execute(statement.values(revoked_at=utcnow(), revoked_reason=reason))
    # `rowcount` lives on CursorResult, which is what an UPDATE returns; the
    # declared `Result` type does not carry it.
    return int(cast("CursorResult[Any]", result).rowcount or 0)


def set_refresh_cookie(response: Response, token: str) -> None:
    """Store the refresh token in an HttpOnly cookie (SPEC §6.2).

    HttpOnly so JavaScript — including anything injected via XSS — cannot read
    it. SameSite=Strict so it is not sent on cross-site navigations, which is
    what removes CSRF from the refresh endpoint. Path-scoped to /api so it is
    not attached to requests for static assets.

    `secure` follows the environment: it must be off in local HTTP development
    or the browser silently drops the cookie and every session dies at 15
    minutes, but it must be on in production.
    """
    settings = get_settings()
    response.set_cookie(
        REFRESH_COOKIE_NAME,
        token,
        max_age=settings.refresh_token_ttl_days * 24 * 60 * 60,
        httponly=True,
        secure=settings.is_production,
        samesite="strict",
        path="/api",
    )


def clear_refresh_cookie(response: Response) -> None:
    """Delete the refresh cookie. Attributes must match `set_refresh_cookie`."""
    response.delete_cookie(
        REFRESH_COOKIE_NAME,
        path="/api",
        httponly=True,
        secure=get_settings().is_production,
        samesite="strict",
    )


async def list_sessions(session: AsyncSession, user_id: uuid.UUID) -> list[RefreshToken]:
    """Live sessions for the sessions screen, newest first."""
    result = await session.execute(
        select(RefreshToken)
        .where(
            RefreshToken.user_id == user_id,
            RefreshToken.revoked_at.is_(None),
            RefreshToken.expires_at > utcnow(),
        )
        .order_by(RefreshToken.created_at.desc())
    )
    return list(result.scalars())
