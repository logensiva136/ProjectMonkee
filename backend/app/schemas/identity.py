"""User, role, panel and audit contracts (SPEC §5.1, §6.3)."""

from __future__ import annotations

import datetime as dt
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.schemas.setup import USERNAME_PATTERN


class PanelOut(BaseModel):
    """A sidebar entry. The frontend builds navigation purely from these."""

    model_config = ConfigDict(from_attributes=True)

    key: str
    name: str
    route: str
    icon: str
    nav_group: str
    sort_order: int


class PermissionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key: str
    resource: str
    action: str
    description: str


class RoleSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    key: str
    name: str
    description: str
    is_system: bool


class RoleDetail(RoleSummary):
    permission_keys: list[str]
    panel_keys: list[str]
    user_count: int


class RoleCreate(BaseModel):
    key: Annotated[str, Field(min_length=2, max_length=64, pattern=r"^[a-z0-9_]+$")]
    name: Annotated[str, Field(min_length=1, max_length=100)]
    description: str = ""
    permission_keys: list[str] = []
    panel_keys: list[str] = []


class RoleUpdate(BaseModel):
    name: Annotated[str | None, Field(min_length=1, max_length=100)] = None
    description: str | None = None
    #: Full replacement lists. Omit to leave that dimension untouched.
    permission_keys: list[str] | None = None
    panel_keys: list[str] | None = None


class UserSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    full_name: str
    username: str
    email: str
    is_active: bool
    is_locked: bool
    totp_enabled: bool
    must_change_password: bool
    last_login_at: dt.datetime | None
    created_at: dt.datetime
    role_keys: list[str]
    initials: str


class UserCreate(BaseModel):
    full_name: Annotated[str, Field(min_length=1, max_length=200)]
    username: Annotated[str, Field(min_length=3, max_length=32)]
    email: EmailStr
    password: Annotated[str, Field(min_length=12, max_length=256)]
    role_keys: list[str] = []
    #: Force a change at first sign-in. Default true, because an administrator
    #: choosing another person's password means that password is already shared.
    must_change_password: bool = True

    @field_validator("username")
    @classmethod
    def _valid_username(cls, value: str) -> str:
        import re

        lowered = value.strip().lower()
        if not re.match(USERNAME_PATTERN, lowered):
            raise ValueError(
                "Username may contain only lowercase letters, digits, dots, hyphens "
                "and underscores."
            )
        return lowered


class UserUpdate(BaseModel):
    full_name: Annotated[str | None, Field(min_length=1, max_length=200)] = None
    email: EmailStr | None = None
    is_active: bool | None = None
    role_keys: list[str] | None = None


class PasswordResetRequest(BaseModel):
    new_password: Annotated[str, Field(min_length=12, max_length=256)]
    must_change_password: bool = True


class MeResponse(BaseModel):
    """Everything the frontend needs to render itself (SPEC §6.3).

    The sidebar and route guards are built from `panels` and `permissions`. The
    backend enforces permissions independently — this is what the UI *shows*,
    not what it is *allowed* to do.
    """

    user: UserSummary
    roles: list[RoleSummary]
    permissions: list[str]
    panels: list[PanelOut]
    org_name: str | None
    org_initials: str | None
    org_logo_url: str | None
    brand_color: str
    timezone: str


class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    actor_id: str | None
    actor_username: str | None
    action: str
    entity_type: str | None
    entity_id: str | None
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    ip: str | None
    ua: str | None
    request_id: str | None
    created_at: dt.datetime


class AppSettingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    org_name: str | None
    org_initials: str | None
    org_logo_url: str | None
    brand_color: str
    timezone: str
    setup_completed_at: dt.datetime | None
    preferences: dict[str, Any]


class AppSettingUpdate(BaseModel):
    org_name: Annotated[str | None, Field(max_length=200)] = None
    logo_filename: str | None = None
    brand_color: Annotated[str | None, Field(pattern=r"^#[0-9A-Fa-f]{6}$")] = None
    timezone: str | None = None
    preferences: dict[str, Any] | None = None


class CursorPage[T](BaseModel):
    """Cursor-paginated envelope (SPEC §7).

    Cursor rather than offset because UUIDv7 ids sort chronologically, so
    "everything after this id" is both an index seek and stable while new rows
    arrive — an offset would skip or repeat rows as the table grows underneath
    the reader.
    """

    items: list[T]
    next_cursor: str | None = None
    has_more: bool = False
