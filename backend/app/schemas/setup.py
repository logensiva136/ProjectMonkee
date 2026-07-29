"""Onboarding wizard contract (SPEC §6.1).

The wizard keeps its state client-side across five steps and submits once. These
models describe that single atomic submission plus the two helper calls the UI
makes along the way (password strength, TOTP enrolment).
"""

from __future__ import annotations

import datetime as dt
import re
from typing import Annotated

from pydantic import BaseModel, EmailStr, Field, field_validator

USERNAME_PATTERN = r"^[a-z0-9._-]+$"


class SetupStatus(BaseModel):
    """Unauthenticated. Drives the frontend's hard redirect to /setup."""

    needs_setup: bool
    app_name: str
    org_name: str | None = None


class PasswordCheckRequest(BaseModel):
    """Live strength meter input (SPEC §6.1 step 3)."""

    password: str = Field(max_length=256)
    username: str | None = None
    email: str | None = None
    full_name: str | None = None


class PasswordCheckResponse(BaseModel):
    acceptable: bool
    score: int = Field(ge=0, le=4, description="zxcvbn score; 3 is the minimum accepted")
    problems: list[str] = Field(description="Blocking issues, shown verbatim to the user")
    warning: str = ""
    suggestions: list[str] = []
    crack_time: str = Field(description="Human-readable offline cracking estimate")


class TotpEnrolmentResponse(BaseModel):
    """Step 4: a secret to enrol, shown once and never returned again."""

    secret: str = Field(description="Base32, shown in copyable form")
    provisioning_uri: str
    qr_svg: str = Field(description="Inline SVG of the provisioning URI")


class MonogramPreviewResponse(BaseModel):
    """Live preview of the generated avatar when no logo is uploaded."""

    initials: str
    color: str
    svg: str


class LogoUploadResponse(BaseModel):
    filename: str
    url: str


class SetupCompleteRequest(BaseModel):
    """The single atomic submission that creates the instance (SPEC §6.1 step 5)."""

    # --- step 1: identity ---
    full_name: Annotated[str, Field(min_length=1, max_length=200)]
    username: Annotated[str, Field(min_length=3, max_length=32)]
    email: EmailStr

    # --- step 2: organisation ---
    org_name: Annotated[str | None, Field(max_length=200)] = None
    #: Filename returned by POST /setup/logo, if one was uploaded.
    logo_filename: str | None = None
    timezone: str = "Asia/Kuala_Lumpur"
    brand_color: Annotated[str, Field(pattern=r"^#[0-9A-Fa-f]{6}$")] = "#22D3EE"

    # --- step 3: password ---
    password: Annotated[str, Field(min_length=12, max_length=256)]

    # --- step 4: two-factor, mandatory ---
    totp_secret: Annotated[str, Field(min_length=16)]
    totp_code: Annotated[str, Field(pattern=r"^\d{6}$")]
    recovery_codes_acknowledged: bool

    @field_validator("username")
    @classmethod
    def _valid_username(cls, value: str) -> str:
        # Lowercased before matching so "Admin" is accepted and stored as
        # "admin", rather than rejected for a capital the user cannot see is
        # wrong. The column is citext, so case never distinguishes two accounts.
        lowered = value.strip().lower()
        if not re.match(USERNAME_PATTERN, lowered):
            raise ValueError(
                "Username may contain only lowercase letters, digits, dots, hyphens "
                "and underscores."
            )
        return lowered

    @field_validator("recovery_codes_acknowledged")
    @classmethod
    def _must_acknowledge(cls, value: bool) -> bool:
        if not value:
            raise ValueError("You must confirm you have saved your recovery codes.")
        return value


class SetupCompleteResponse(BaseModel):
    """Auto-login payload (SPEC §6.1 step 5).

    Recovery codes appear here and nowhere else, ever again — they are hashed
    at rest, so this response is the only chance to save them.
    """

    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Access token lifetime in seconds")
    user_id: str
    username: str
    recovery_codes: list[str]
    setup_completed_at: dt.datetime
