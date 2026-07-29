"""Authentication endpoints (SPEC §6.2).

Token model: a 15-minute access token returned in the body and held only in
browser memory, plus a 7-day refresh token in an HttpOnly SameSite=Strict
cookie that the JavaScript never sees.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import UnauthorizedError, UnprocessableError
from app.core.logging import get_logger
from app.core.rbac import CurrentUser
from app.core.security import (
    RECOVERY_CODE_COUNT,
    TokenError,
    create_mfa_token,
    decode_token,
    generate_recovery_codes,
    hash_password,
    hash_recovery_code,
    hash_refresh_token,
    validate_password,
    verify_password,
)
from app.db import get_session
from app.models.identity import RecoveryCode, RefreshToken
from app.schemas.auth import (
    LoginRequest,
    LoginResponse,
    MessageResponse,
    MfaVerifyRequest,
    PasswordChangeRequest,
    RecoveryCodesResponse,
    SessionInfo,
    TokenResponse,
)
from app.services import audit
from app.services import auth as auth_service

log = get_logger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.post("/login", response_model=LoginResponse, summary="Password step")
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    session: SessionDep,
) -> LoginResponse:
    """Verify credentials.

    When the account has TOTP enabled — which every account created through
    onboarding does — this returns only a five-minute `mfa_token`. No session
    exists and no cookie is set until the second factor is verified.
    """
    user = await auth_service.authenticate(
        session, payload.username, payload.password, request=request
    )

    if user.totp_enabled:
        log.info("login_password_ok", username=user.username, next="mfa")
        return LoginResponse(status="mfa_required", mfa_token=create_mfa_token(user.id))

    pair = await auth_service.issue_session(session, user, request=request)
    auth_service.set_refresh_cookie(response, pair.refresh_token)

    await audit.record(
        session,
        action="auth.login",
        actor=user,
        entity_type="user",
        entity_id=user.id,
        request=request,
    )
    return LoginResponse(
        status="authenticated",
        access_token=pair.access_token,
        expires_in=pair.expires_in,
        must_change_password=user.must_change_password,
    )


@router.post("/mfa/verify", response_model=TokenResponse, summary="Second factor")
async def verify_mfa(
    payload: MfaVerifyRequest,
    request: Request,
    response: Response,
    session: SessionDep,
) -> TokenResponse:
    """Complete login with a TOTP code or a single-use recovery code."""
    try:
        subject = decode_token(payload.mfa_token, expect="mfa")
    except TokenError as exc:
        raise UnauthorizedError("That sign-in attempt expired. Please start again.") from exc

    user = await auth_service.load_user(session, uuid.UUID(subject))
    if user is None or not user.is_active:
        raise UnauthorizedError("Account is unavailable.")

    await auth_service.verify_second_factor(session, user, payload.code, request=request)

    pair = await auth_service.issue_session(session, user, request=request)
    auth_service.set_refresh_cookie(response, pair.refresh_token)

    await audit.record(
        session,
        action="auth.login",
        actor=user,
        entity_type="user",
        entity_id=user.id,
        after={"mfa": True},
        request=request,
    )
    log.info("login_complete", username=user.username)

    return TokenResponse(
        access_token=pair.access_token,
        expires_in=pair.expires_in,
        must_change_password=user.must_change_password,
    )


@router.post("/refresh", response_model=TokenResponse, summary="Rotate the session")
async def refresh(request: Request, response: Response, session: SessionDep) -> TokenResponse:
    """Exchange the refresh cookie for a new token pair.

    Rotation is unconditional: the presented token is revoked and a new one
    issued. Presenting an already-revoked token is treated as replay and revokes
    the whole family — see `app.services.auth`.
    """
    raw = request.cookies.get(auth_service.REFRESH_COOKIE_NAME)
    if not raw:
        raise UnauthorizedError("No active session.")

    user, pair = await auth_service.rotate_refresh_token(session, raw, request=request)
    auth_service.set_refresh_cookie(response, pair.refresh_token)

    return TokenResponse(
        access_token=pair.access_token,
        expires_in=pair.expires_in,
        must_change_password=user.must_change_password,
    )


@router.post("/logout", response_model=MessageResponse, summary="End this session")
async def logout(request: Request, response: Response, session: SessionDep) -> MessageResponse:
    """Revoke the current refresh token and clear the cookie.

    Deliberately does not require authentication: an expired access token must
    not stop someone logging out, and the refresh cookie identifies the session
    on its own.
    """
    raw = request.cookies.get(auth_service.REFRESH_COOKIE_NAME)
    if raw:
        await auth_service.revoke_token(session, raw, reason="logout")

    auth_service.clear_refresh_cookie(response)
    return MessageResponse(message="Signed out.")


@router.get("/sessions", response_model=list[SessionInfo], summary="List active sessions")
async def list_sessions(
    user: CurrentUser, request: Request, session: SessionDep
) -> list[SessionInfo]:
    current_hash = None
    raw = request.cookies.get(auth_service.REFRESH_COOKIE_NAME)
    if raw:
        current_hash = hash_refresh_token(raw)

    return [
        SessionInfo(
            id=str(token.id),
            created_at=token.created_at,
            last_used_at=token.last_used_at,
            expires_at=token.expires_at,
            ip=str(token.ip) if token.ip else None,
            user_agent=token.user_agent,
            # Marking the current session stops an operator revoking the one
            # they are sitting in and wondering why they were signed out.
            is_current=token.token_hash == current_hash,
        )
        for token in await auth_service.list_sessions(session, user.id)
    ]


@router.delete(
    "/sessions/{session_id}",
    response_model=MessageResponse,
    summary="Revoke one session",
)
async def revoke_session(
    session_id: uuid.UUID, user: CurrentUser, session: SessionDep, request: Request
) -> MessageResponse:
    result = await session.execute(
        select(RefreshToken).where(RefreshToken.id == session_id, RefreshToken.user_id == user.id)
    )
    token = result.scalar_one_or_none()
    if token is None:
        raise UnauthorizedError("No such session.")

    # Revoke the family, not just the row: the token may already have been
    # rotated, and revoking a superseded row alone would leave the live one
    # working.
    await auth_service.revoke_family(session, token.family_id, reason="revoked_by_user")
    await audit.record(
        session,
        action="auth.session_revoked",
        actor=user,
        entity_type="refresh_token",
        entity_id=session_id,
        request=request,
    )
    return MessageResponse(message="Session revoked.")


@router.delete("/sessions", response_model=MessageResponse, summary="Revoke all sessions")
async def revoke_all_sessions(
    user: CurrentUser, session: SessionDep, request: Request
) -> MessageResponse:
    count = await auth_service.revoke_all_for_user(session, user.id, reason="revoked_all")
    await audit.record(
        session,
        action="auth.all_sessions_revoked",
        actor=user,
        entity_type="user",
        entity_id=user.id,
        after={"revoked": count},
        request=request,
    )
    return MessageResponse(message=f"Revoked {count} session(s).")


@router.post("/password/change", response_model=MessageResponse, summary="Change your password")
async def change_password(
    payload: PasswordChangeRequest,
    user: CurrentUser,
    session: SessionDep,
    request: Request,
    response: Response,
) -> MessageResponse:
    """Requires the current password, and ends every other session."""
    if not verify_password(payload.current_password, user.password_hash):
        raise UnauthorizedError("Your current password is incorrect.")

    problems = validate_password(
        payload.new_password,
        username=user.username,
        email=user.email,
        full_name=user.full_name,
    )
    if problems:
        raise UnprocessableError("; ".join(problems), field="new_password", problems=problems)

    user.password_hash = hash_password(payload.new_password)
    user.must_change_password = False

    # A password change is the standard response to a suspected compromise, so
    # every existing session must die — including any an attacker holds. The
    # caller is then re-issued a fresh one below.
    await auth_service.revoke_all_for_user(session, user.id, reason="password_changed")
    pair = await auth_service.issue_session(session, user, request=request)
    auth_service.set_refresh_cookie(response, pair.refresh_token)

    await audit.record(
        session,
        action="auth.password_changed",
        actor=user,
        entity_type="user",
        entity_id=user.id,
        request=request,
    )
    log.info("password_changed", username=user.username)
    return MessageResponse(message="Password changed. Other sessions have been signed out.")


@router.post(
    "/recovery-codes/regenerate",
    response_model=RecoveryCodesResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Replace your recovery codes",
)
async def regenerate_recovery_codes(
    user: CurrentUser, session: SessionDep, request: Request
) -> RecoveryCodesResponse:
    """Invalidate all existing codes and issue ten new ones.

    Returned in plaintext exactly once; only hashes are stored.
    """
    existing = await session.execute(select(RecoveryCode).where(RecoveryCode.user_id == user.id))
    for stored in existing.scalars():
        await session.delete(stored)

    codes = generate_recovery_codes(RECOVERY_CODE_COUNT)
    for code in codes:
        session.add(RecoveryCode(user_id=user.id, code_hash=hash_recovery_code(code)))

    await audit.record(
        session,
        action="auth.recovery_codes_regenerated",
        actor=user,
        entity_type="user",
        entity_id=user.id,
        request=request,
    )
    return RecoveryCodesResponse(recovery_codes=codes)
