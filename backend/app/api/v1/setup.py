"""First-run onboarding wizard (SPEC §6.1).

`/setup/status` is unauthenticated and always answers. Everything else here is
available only while the instance is un-onboarded; afterwards these routes are
410 Gone, permanently.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Request, Response, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.errors import UnprocessableError
from app.core.security import (
    generate_totp_secret,
    password_strength,
    totp_provisioning_uri,
    totp_qr_svg,
    validate_password,
)
from app.db import get_session
from app.schemas.setup import (
    LogoUploadResponse,
    MonogramPreviewResponse,
    PasswordCheckRequest,
    PasswordCheckResponse,
    SetupCompleteRequest,
    SetupCompleteResponse,
    SetupStatus,
    TotpEnrolmentResponse,
)
from app.services import auth as auth_service
from app.services import setup as setup_service
from app.services.media import MAX_LOGO_BYTES, process_logo
from app.services.monogram import derive_color, derive_initials, render_monogram_svg

router = APIRouter(prefix="/setup", tags=["setup"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def _gate(session: SessionDep) -> None:
    """Dependency making a route unavailable once onboarding has completed."""
    await setup_service.require_setup_incomplete(session)


GateDep = Annotated[None, Depends(_gate)]


@router.get(
    "/status",
    response_model=SetupStatus,
    summary="Whether this instance still needs onboarding",
)
async def setup_status(session: SessionDep) -> SetupStatus:
    """Unauthenticated, and never 410s — the frontend polls it on every boot."""
    settings = get_settings()
    setting = await setup_service.get_app_setting(session)
    return SetupStatus(
        needs_setup=setting is None or setting.setup_completed_at is None,
        app_name=settings.app_name,
        org_name=setting.org_name if setting else None,
    )


@router.post(
    "/password-check",
    response_model=PasswordCheckResponse,
    summary="Score a candidate password for the live strength meter",
)
async def check_password(payload: PasswordCheckRequest, _: GateDep) -> PasswordCheckResponse:
    """Runs the same policy the final submit enforces.

    Sharing the implementation means the meter can never say "strong" for a
    password that `/setup/complete` will then reject.
    """
    problems = validate_password(
        payload.password,
        username=payload.username,
        email=payload.email,
        full_name=payload.full_name,
    )
    personal = [v for v in (payload.username, payload.email, payload.full_name) if v]
    strength = password_strength(payload.password, user_inputs=personal)

    return PasswordCheckResponse(
        acceptable=not problems,
        score=strength["score"],
        problems=problems,
        warning=strength["warning"],
        suggestions=strength["suggestions"],
        crack_time=strength["crack_time"],
    )


@router.post(
    "/totp",
    response_model=TotpEnrolmentResponse,
    summary="Generate a TOTP secret and its QR code",
)
async def enrol_totp(_: GateDep, username: str = "operator") -> TotpEnrolmentResponse:
    """Mint a secret for the wizard to display.

    Nothing is persisted here. The client holds the secret through step 4 and
    submits it with `/setup/complete`, which re-verifies a fresh code against it
    before storing anything — so an abandoned wizard leaves no half-enrolled
    account behind.
    """
    secret = generate_totp_secret()
    uri = totp_provisioning_uri(secret, username)
    return TotpEnrolmentResponse(secret=secret, provisioning_uri=uri, qr_svg=totp_qr_svg(uri))


@router.post(
    "/monogram-preview",
    response_model=MonogramPreviewResponse,
    summary="Preview the generated avatar for a name",
)
async def preview_monogram(_: GateDep, name: str = "") -> MonogramPreviewResponse:
    """Live preview for step 2 when no logo is uploaded."""
    cleaned = name.strip() or "HAYABUSA"
    return MonogramPreviewResponse(
        initials=derive_initials(cleaned),
        color=derive_color(cleaned),
        svg=render_monogram_svg(cleaned),
    )


@router.post(
    "/logo",
    response_model=LogoUploadResponse,
    summary="Upload the organisation logo",
)
async def upload_logo(
    _: GateDep,
    file: Annotated[UploadFile, File(description="PNG, JPG, WebP or SVG, max 2 MB")],
) -> LogoUploadResponse:
    """Validate by magic bytes, strip metadata, normalise to 512x512 (SPEC §6.1).

    The size check happens after reading, but `UploadFile` spools to disk beyond
    a small threshold rather than buffering in memory, so an oversized upload
    cannot exhaust RAM before it is rejected.
    """
    data = await file.read()
    if len(data) > MAX_LOGO_BYTES:
        raise UnprocessableError(
            f"Logo must be 2 MB or smaller (received {len(data) / 1024 / 1024:.1f} MB)."
        )

    filename = process_logo(data, get_settings().upload_dir)
    return LogoUploadResponse(filename=filename, url=f"/api/v1/media/{filename}")


@router.post(
    "/complete",
    response_model=SetupCompleteResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create the instance and sign the first operator in",
)
async def complete(
    payload: SetupCompleteRequest,
    request: Request,
    response: Response,
    session: SessionDep,
    _: GateDep,
) -> SetupCompleteResponse:
    """One atomic transaction (SPEC §6.1 step 5).

    Creates the user, assigns Super Admin, writes settings, seeds reference
    data, records the audit entry, and returns an access token plus the refresh
    cookie so the operator lands signed in.
    """
    result = await setup_service.complete_setup(session, payload, request=request)

    pair = await auth_service.issue_session(session, result.user, request=request)
    auth_service.set_refresh_cookie(response, pair.refresh_token)

    return SetupCompleteResponse(
        access_token=pair.access_token,
        expires_in=pair.expires_in,
        user_id=str(result.user.id),
        username=result.user.username,
        recovery_codes=result.recovery_codes,
        setup_completed_at=result.completed_at,
    )
