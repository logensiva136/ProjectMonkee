"""Authentication contract (SPEC §6.2)."""

from __future__ import annotations

import datetime as dt
from typing import Annotated, Literal

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: Annotated[str, Field(min_length=1, max_length=64)]
    password: Annotated[str, Field(min_length=1, max_length=256)]


class LoginResponse(BaseModel):
    """Either a finished login, or a demand for the second factor.

    `status` discriminates. When it is `mfa_required` the caller holds an
    `mfa_token` and no access token — the session does not exist yet.
    """

    status: Literal["authenticated", "mfa_required"]
    access_token: str | None = None
    token_type: str = "bearer"
    expires_in: int | None = None
    mfa_token: str | None = Field(
        default=None, description="Short-lived proof the password step passed; valid 5 minutes"
    )
    must_change_password: bool = False


class MfaVerifyRequest(BaseModel):
    mfa_token: str
    code: Annotated[str, Field(min_length=6, max_length=16)] = Field(
        description="Six-digit TOTP code, or a single-use recovery code"
    )


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    must_change_password: bool = False


class PasswordChangeRequest(BaseModel):
    current_password: Annotated[str, Field(min_length=1, max_length=256)]
    new_password: Annotated[str, Field(min_length=12, max_length=256)]


class SessionInfo(BaseModel):
    """A live refresh-token session, for the sessions screen (SPEC §6.2)."""

    id: str
    created_at: dt.datetime
    last_used_at: dt.datetime | None
    expires_at: dt.datetime
    ip: str | None
    user_agent: str | None
    is_current: bool


class RecoveryCodesResponse(BaseModel):
    """Regenerated codes. Shown once; only hashes are kept."""

    recovery_codes: list[str]


class MessageResponse(BaseModel):
    message: str
