"""User administration (SPEC §7, §9.2 /admin/users).

Every mutating route declares `user:manage`. That dependency is the security
boundary — hiding the Users panel from a role does not protect these endpoints.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import ConflictError, ForbiddenError, NotFoundError, UnprocessableError
from app.core.logging import get_logger
from app.core.rbac import require
from app.core.security import hash_password, validate_password
from app.db import get_session
from app.models.base import utcnow
from app.models.identity import RecoveryCode, User
from app.models.rbac import Role
from app.schemas.auth import MessageResponse, SessionInfo
from app.schemas.identity import (
    PasswordResetRequest,
    UserCreate,
    UserSummary,
    UserUpdate,
)
from app.services import audit
from app.services import auth as auth_service
from app.services.identity import to_user_summary

log = get_logger(__name__)
router = APIRouter(prefix="/users", tags=["users"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
ManageUsers = Annotated[User, Depends(require("user:manage"))]


async def _load(session: AsyncSession, user_id: uuid.UUID) -> User:
    result = await session.execute(
        select(User)
        .where(User.id == user_id, User.deleted_at.is_(None))
        .options(selectinload(User.roles))
    )
    user = result.scalar_one_or_none()
    if user is None:
        raise NotFoundError("No such user.")
    return user


async def _resolve_roles(session: AsyncSession, keys: list[str]) -> list[Role]:
    if not keys:
        return []
    result = await session.execute(
        select(Role).where(Role.key.in_(keys), Role.deleted_at.is_(None))
    )
    roles = list(result.scalars())

    missing = set(keys) - {role.key for role in roles}
    if missing:
        raise UnprocessableError(f"Unknown role(s): {', '.join(sorted(missing))}.")
    return roles


@router.get("", response_model=list[UserSummary], summary="List users")
async def list_users(
    session: SessionDep,
    _: ManageUsers,
    include_inactive: bool = True,
) -> list[UserSummary]:
    statement = select(User).where(User.deleted_at.is_(None)).options(selectinload(User.roles))
    if not include_inactive:
        statement = statement.where(User.is_active.is_(True))

    result = await session.execute(statement.order_by(User.created_at))
    return [to_user_summary(user) for user in result.scalars()]


@router.post(
    "",
    response_model=UserSummary,
    status_code=status.HTTP_201_CREATED,
    summary="Create a user",
)
async def create_user(
    payload: UserCreate, session: SessionDep, actor: ManageUsers, request: Request
) -> UserSummary:
    """Create an account.

    The new user has no second factor yet; they enrol one on first sign-in. An
    administrator cannot enrol it for them — that would mean holding someone
    else's second factor, which defeats the point of having one.
    """
    problems = validate_password(
        payload.password,
        username=payload.username,
        email=str(payload.email),
        full_name=payload.full_name,
    )
    if problems:
        raise UnprocessableError("; ".join(problems), field="password", problems=problems)

    clash = await session.execute(
        select(User).where((User.username == payload.username) | (User.email == str(payload.email)))
    )
    if clash.scalar_one_or_none() is not None:
        # citext columns make this comparison case-insensitive, so "Admin" and
        # "admin" collide as intended.
        raise ConflictError("That username or email address is already in use.")

    user = User(
        full_name=payload.full_name.strip(),
        username=payload.username,
        email=str(payload.email).lower(),
        password_hash=hash_password(payload.password),
        must_change_password=payload.must_change_password,
        roles=await _resolve_roles(session, payload.role_keys),
    )
    session.add(user)
    await session.flush()

    await audit.record(
        session,
        action="user.created",
        actor=actor,
        entity_type="user",
        entity_id=user.id,
        after={"username": user.username, "email": user.email, "roles": payload.role_keys},
        request=request,
    )
    return to_user_summary(user)


@router.get("/{user_id}", response_model=UserSummary, summary="Get a user")
async def get_user(user_id: uuid.UUID, session: SessionDep, _: ManageUsers) -> UserSummary:
    return to_user_summary(await _load(session, user_id))


@router.patch("/{user_id}", response_model=UserSummary, summary="Update a user")
async def update_user(
    user_id: uuid.UUID,
    payload: UserUpdate,
    session: SessionDep,
    actor: ManageUsers,
    request: Request,
) -> UserSummary:
    user = await _load(session, user_id)
    before = {
        "full_name": user.full_name,
        "email": user.email,
        "is_active": user.is_active,
        "roles": sorted(role.key for role in user.roles),
    }

    if payload.full_name is not None:
        user.full_name = payload.full_name.strip()
    if payload.email is not None:
        user.email = str(payload.email).lower()

    if payload.is_active is not None:
        # Deactivating yourself locks you out of the instance you are holding.
        if not payload.is_active and user.id == actor.id:
            raise ForbiddenError("You cannot deactivate your own account.")
        user.is_active = payload.is_active
        if not payload.is_active:
            await auth_service.revoke_all_for_user(session, user.id, reason="deactivated")

    if payload.role_keys is not None:
        if user.id == actor.id and "super_admin" not in payload.role_keys:
            # Removing your own Super Admin role with no other holder leaves the
            # instance permanently un-administrable.
            raise ForbiddenError("You cannot remove your own Super Admin role.")
        user.roles = await _resolve_roles(session, payload.role_keys)

    await session.flush()
    await audit.record(
        session,
        action="user.updated",
        actor=actor,
        entity_type="user",
        entity_id=user.id,
        before=before,
        after={
            "full_name": user.full_name,
            "email": user.email,
            "is_active": user.is_active,
            "roles": sorted(role.key for role in user.roles),
        },
        request=request,
    )
    return to_user_summary(user)


@router.delete(
    "/{user_id}", response_model=MessageResponse, summary="Deactivate and soft-delete a user"
)
async def delete_user(
    user_id: uuid.UUID, session: SessionDep, actor: ManageUsers, request: Request
) -> MessageResponse:
    """Soft delete: the audit trail must keep pointing at a real row."""
    user = await _load(session, user_id)
    if user.id == actor.id:
        raise ForbiddenError("You cannot delete your own account.")

    user.deleted_at = utcnow()
    user.is_active = False
    await auth_service.revoke_all_for_user(session, user.id, reason="user_deleted")

    await audit.record(
        session,
        action="user.deleted",
        actor=actor,
        entity_type="user",
        entity_id=user.id,
        before={"username": user.username},
        request=request,
    )
    return MessageResponse(message=f"{user.username} has been removed.")


@router.post("/{user_id}/password", response_model=MessageResponse, summary="Set a user's password")
async def reset_password(
    user_id: uuid.UUID,
    payload: PasswordResetRequest,
    session: SessionDep,
    actor: ManageUsers,
    request: Request,
) -> MessageResponse:
    user = await _load(session, user_id)

    problems = validate_password(
        payload.new_password,
        username=user.username,
        email=user.email,
        full_name=user.full_name,
    )
    if problems:
        raise UnprocessableError("; ".join(problems), field="new_password", problems=problems)

    user.password_hash = hash_password(payload.new_password)
    user.must_change_password = payload.must_change_password
    user.failed_login_count = 0
    user.locked_until = None
    await auth_service.revoke_all_for_user(session, user.id, reason="password_reset_by_admin")

    await audit.record(
        session,
        action="user.password_reset",
        actor=actor,
        entity_type="user",
        entity_id=user.id,
        request=request,
    )
    return MessageResponse(message="Password reset. All their sessions were signed out.")


@router.post(
    "/{user_id}/2fa/reset", response_model=MessageResponse, summary="Clear a user's second factor"
)
async def reset_two_factor(
    user_id: uuid.UUID, session: SessionDep, actor: ManageUsers, request: Request
) -> MessageResponse:
    """Recovery path for a lost authenticator (SPEC §7 `/auth/2fa/reset`).

    Clears the secret and every unused recovery code, so the user re-enrols at
    next sign-in. Deliberately high-privilege and always audited: this is the
    one action that can strip an account's second factor.
    """
    user = await _load(session, user_id)

    user.totp_secret_encrypted = None
    user.totp_enabled = False

    codes = await session.execute(select(RecoveryCode).where(RecoveryCode.user_id == user.id))
    for code in codes.scalars():
        await session.delete(code)

    await auth_service.revoke_all_for_user(session, user.id, reason="2fa_reset")

    log.warning("two_factor_reset", target=user.username, actor=actor.username)
    await audit.record(
        session,
        action="user.two_factor_reset",
        actor=actor,
        entity_type="user",
        entity_id=user.id,
        request=request,
    )
    return MessageResponse(message=f"Two-factor cleared for {user.username}.")


@router.post("/{user_id}/unlock", response_model=MessageResponse, summary="Unlock a user")
async def unlock_user(
    user_id: uuid.UUID, session: SessionDep, actor: ManageUsers, request: Request
) -> MessageResponse:
    user = await _load(session, user_id)
    user.failed_login_count = 0
    user.locked_until = None

    await audit.record(
        session,
        action="user.unlocked",
        actor=actor,
        entity_type="user",
        entity_id=user.id,
        request=request,
    )
    return MessageResponse(message=f"{user.username} unlocked.")


@router.get(
    "/{user_id}/sessions", response_model=list[SessionInfo], summary="A user's active sessions"
)
async def user_sessions(
    user_id: uuid.UUID, session: SessionDep, _: ManageUsers
) -> list[SessionInfo]:
    await _load(session, user_id)
    return [
        SessionInfo(
            id=str(token.id),
            created_at=token.created_at,
            last_used_at=token.last_used_at,
            expires_at=token.expires_at,
            ip=str(token.ip) if token.ip else None,
            user_agent=token.user_agent,
            is_current=False,  # never the administrator's own session
        )
        for token in await auth_service.list_sessions(session, user_id)
    ]


@router.delete(
    "/{user_id}/sessions", response_model=MessageResponse, summary="Sign a user out everywhere"
)
async def revoke_user_sessions(
    user_id: uuid.UUID, session: SessionDep, actor: ManageUsers, request: Request
) -> MessageResponse:
    await _load(session, user_id)
    count = await auth_service.revoke_all_for_user(session, user_id, reason="revoked_by_admin")

    await audit.record(
        session,
        action="user.sessions_revoked",
        actor=actor,
        entity_type="user",
        entity_id=user_id,
        after={"revoked": count},
        request=request,
    )
    return MessageResponse(message=f"Revoked {count} session(s).")
