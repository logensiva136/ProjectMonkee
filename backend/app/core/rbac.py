"""Authentication and permission dependencies (SPEC §6.3).

Endpoints declare what they need:

    @router.post("/vendors", dependencies=[Depends(require("vendor:write"))])
    async def create_vendor(...): ...

    @router.get("/vendors")
    async def list_vendors(user: CurrentUser): ...

**The backend enforces permissions independently of the UI.** Panel visibility
decides what the sidebar shows; it has no bearing on what an endpoint allows.
A Viewer who hand-crafts a POST to `/api/v1/users` gets 403 from here, not from
a hidden button.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.context import set_actor_id
from app.core.errors import ForbiddenError, UnauthorizedError
from app.core.logging import get_logger
from app.core.security import TokenError, decode_token
from app.db import get_session
from app.models.identity import User
from app.models.rbac import Role

log = get_logger(__name__)

# auto_error=False so a missing header produces our problem+json 401 rather than
# Starlette's bare JSON body.
_bearer = HTTPBearer(auto_error=False, description="Access token from /auth/login")


async def get_current_user(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> User:
    """Resolve the caller from their bearer token.

    Roles and permissions are loaded from the database on each request rather
    than read out of the token. That costs one indexed query and buys immediate
    revocation: removing a role takes effect on the caller's very next request
    instead of whenever their 15-minute access token happens to expire.
    """
    if credentials is None or not credentials.credentials:
        raise UnauthorizedError("Authentication required.")

    try:
        subject = decode_token(credentials.credentials, expect="access")
    except TokenError as exc:
        raise UnauthorizedError("Invalid or expired access token.") from exc

    try:
        user_id = uuid.UUID(subject)
    except ValueError as exc:
        raise UnauthorizedError("Malformed access token.") from exc

    result = await session.execute(
        select(User)
        .where(User.id == user_id, User.deleted_at.is_(None))
        .options(selectinload(User.roles).selectinload(Role.permissions))
    )
    user = result.scalar_one_or_none()

    if user is None:
        raise UnauthorizedError("Account no longer exists.")
    if not user.is_active:
        raise UnauthorizedError("Account is disabled.")
    if user.is_locked:
        raise UnauthorizedError("Account is temporarily locked.")

    # Bind for the audit log and for structlog, so everything this request does
    # is attributable without threading the user through every call.
    set_actor_id(str(user.id))
    request.state.user = user
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def permissions_of(user: User) -> set[str]:
    """Every permission the user holds, via any of their roles.

    Soft-deleted roles are ignored: deleting a role must actually remove the
    access it granted.
    """
    return {
        permission.key
        for role in user.roles
        if role.deleted_at is None
        for permission in role.permissions
    }


def role_keys_of(user: User) -> set[str]:
    return {role.key for role in user.roles if role.deleted_at is None}


def require(*required: str) -> Callable[[User], Awaitable[User]]:
    """Dependency factory demanding every listed permission.

    Multiple arguments are ANDed — `require("easm:scan", "easm:write")` needs
    both. For an either/or, use `require_any`.
    """

    async def dependency(user: CurrentUser) -> User:
        held = permissions_of(user)
        missing = set(required) - held
        if missing:
            log.warning(
                "permission_denied",
                username=user.username,
                required=sorted(required),
                missing=sorted(missing),
            )
            raise ForbiddenError(
                f"This action requires the {', '.join(sorted(missing))} permission."
            )
        return user

    return dependency


def require_any(*accepted: str) -> Callable[[User], Awaitable[User]]:
    """Dependency factory demanding at least one of the listed permissions."""

    async def dependency(user: CurrentUser) -> User:
        if not (permissions_of(user) & set(accepted)):
            log.warning(
                "permission_denied",
                username=user.username,
                required_any=sorted(accepted),
            )
            raise ForbiddenError(f"This action requires one of: {', '.join(sorted(accepted))}.")
        return user

    return dependency
