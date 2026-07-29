"""Mapping between identity models and their API representations.

Kept out of the routers so the same shape is produced everywhere a user or role
is returned — SPEC §9.0 Rule 6 puts formatting of derived values in Python, and
`initials`, `is_locked` and `role_keys` are exactly that.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.identity import User
from app.models.rbac import Role, UserRole
from app.schemas.identity import PanelOut, RoleDetail, RoleSummary, UserSummary


def to_user_summary(user: User) -> UserSummary:
    return UserSummary(
        id=str(user.id),
        full_name=user.full_name,
        username=user.username,
        email=user.email,
        is_active=user.is_active,
        is_locked=user.is_locked,
        totp_enabled=user.totp_enabled,
        must_change_password=user.must_change_password,
        last_login_at=user.last_login_at,
        created_at=user.created_at,
        role_keys=sorted(role.key for role in user.roles if role.deleted_at is None),
        initials=user.initials,
    )


def to_role_summary(role: Role) -> RoleSummary:
    return RoleSummary(
        id=str(role.id),
        key=role.key,
        name=role.name,
        description=role.description,
        is_system=role.is_system,
    )


async def to_role_detail(session: AsyncSession, role: Role) -> RoleDetail:
    count = await session.execute(
        select(func.count()).select_from(UserRole).where(UserRole.role_id == role.id)
    )
    return RoleDetail(
        id=str(role.id),
        key=role.key,
        name=role.name,
        description=role.description,
        is_system=role.is_system,
        permission_keys=sorted(p.key for p in role.permissions),
        panel_keys=sorted(rp.panel_key for rp in role.panels if rp.can_view),
        user_count=count.scalar_one(),
    )


def logo_url(filename: str | None) -> str | None:
    """Public URL for a stored logo, or None when the monogram is used instead."""
    return f"/api/v1/media/{filename}" if filename else None


def to_panel_out(panel: object) -> PanelOut:
    return PanelOut.model_validate(panel)
