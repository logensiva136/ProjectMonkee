"""Onboarding (SPEC §6.1).

The whole wizard resolves to one function, `complete_setup`, which runs in a
single transaction. Either the instance ends up fully configured — first user,
Super Admin role, settings row, seeded reference data, audit entry — or nothing
changed and the operator can retry. A half-onboarded instance with a user but no
roles would be unrecoverable through the UI, since the wizard would refuse to
run again.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from fastapi import Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import setup_gate
from app.core.crypto import encrypt
from app.core.errors import ConflictError, SetupAlreadyCompleteError, UnprocessableError
from app.core.logging import get_logger
from app.core.security import (
    RECOVERY_CODE_COUNT,
    generate_recovery_codes,
    hash_password,
    hash_recovery_code,
    validate_password,
    verify_totp,
)
from app.models.base import utcnow
from app.models.identity import AppSetting, RecoveryCode, User
from app.models.rbac import Role
from app.schemas.setup import SetupCompleteRequest
from app.seed import seed_all
from app.seed.definitions import BOOTSTRAP_ROLE_KEY
from app.services import audit
from app.services.monogram import derive_initials

log = get_logger(__name__)


async def get_app_setting(session: AsyncSession) -> AppSetting | None:
    """The singleton settings row, or None before onboarding."""
    return (await session.execute(select(AppSetting).limit(1))).scalar_one_or_none()


async def needs_setup(session: AsyncSession) -> bool:
    setting = await get_app_setting(session)
    return setting is None or setting.setup_completed_at is None


async def require_setup_incomplete(session: AsyncSession) -> None:
    """Guard for `/setup/*`: 410 Gone once onboarding has happened (SPEC §6.1)."""
    if not await needs_setup(session):
        raise SetupAlreadyCompleteError()


@dataclass
class SetupResult:
    """What onboarding produced.

    The router turns this into the HTTP response, because issuing the session
    (and its cookie) is a transport concern that does not belong in the service.
    """

    user: User
    recovery_codes: list[str]
    completed_at: dt.datetime


async def complete_setup(
    session: AsyncSession,
    payload: SetupCompleteRequest,
    *,
    request: Request | None = None,
) -> SetupResult:
    """Create the instance. Atomic — see the module docstring."""
    await require_setup_incomplete(session)

    # --- validate before writing anything -------------------------------
    # The TOTP code is checked here, not merely in the wizard UI: a client that
    # skipped step 4 must not be able to create an account without a second
    # factor, since SPEC §6.1 makes 2FA mandatory.
    if not verify_totp(payload.totp_secret, payload.totp_code):
        raise UnprocessableError(
            "That six-digit code is not valid for this secret. "
            "Check your authenticator app's clock and try the current code.",
            field="totp_code",
        )

    problems = validate_password(
        payload.password,
        username=payload.username,
        email=payload.email,
        full_name=payload.full_name,
    )
    if problems:
        raise UnprocessableError("; ".join(problems), field="password", problems=problems)

    # Defensive: the gate above should make this unreachable, but a concurrent
    # submission could slip between the check and the insert.
    existing = await session.execute(select(func.count()).select_from(User))
    if existing.scalar_one() > 0:
        raise ConflictError("An account already exists on this instance.")

    # --- reference data --------------------------------------------------
    # Seeded inside the same transaction so a failure below cannot leave roles
    # without the user that is supposed to hold them.
    await seed_all(session)

    role = (await session.execute(select(Role).where(Role.key == BOOTSTRAP_ROLE_KEY))).scalar_one()

    # --- the first operator ---------------------------------------------
    user = User(
        full_name=payload.full_name.strip(),
        username=payload.username,
        email=str(payload.email).lower(),
        password_hash=hash_password(payload.password),
        is_active=True,
        must_change_password=False,
        totp_secret_encrypted=encrypt(payload.totp_secret),
        totp_enabled=True,
        roles=[role],
    )
    session.add(user)
    await session.flush()

    # --- recovery codes ---------------------------------------------------
    codes = generate_recovery_codes(RECOVERY_CODE_COUNT)
    for code in codes:
        session.add(RecoveryCode(user_id=user.id, code_hash=hash_recovery_code(code)))

    # --- instance settings ------------------------------------------------
    org_name = (payload.org_name or "").strip() or None
    completed_at = utcnow()

    setting = await get_app_setting(session)
    if setting is None:
        setting = AppSetting()
        session.add(setting)

    setting.org_name = org_name
    setting.org_logo_path = payload.logo_filename
    # Initials come from the organisation when there is one, otherwise from the
    # operator's own name (SPEC §6.1 step 2).
    setting.org_initials = derive_initials(org_name or payload.full_name)
    setting.brand_color = payload.brand_color
    setting.timezone = payload.timezone
    setting.setup_completed_at = completed_at

    await audit.record(
        session,
        action="setup.completed",
        actor=user,
        entity_type="app_setting",
        entity_id=setting.id,
        after={
            "org_name": org_name,
            "username": user.username,
            "timezone": payload.timezone,
            "totp_enabled": True,
        },
        request=request,
    )

    await session.flush()

    # Open the in-process gate now, so the auto-login response and the very next
    # request are not blocked by the gate this call just satisfied.
    setup_gate.mark_setup_complete()

    log.info("setup_completed", username=user.username, org_name=org_name)

    return SetupResult(user=user, recovery_codes=codes, completed_at=completed_at)
