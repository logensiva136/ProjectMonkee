"""Role, permission and panel administration (SPEC §6.3, §9.2 /admin/roles).

Two matrices are edited here:

* **permissions** — the security boundary, enforced by `require(...)` on every
  endpoint
* **panels** — sidebar visibility, which is presentation only

The API keeps them separate for the same reason the UI shows them as separate
grids: conflating them invites the assumption that hiding a screen protects it.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import ConflictError, ForbiddenError, NotFoundError, UnprocessableError
from app.core.rbac import CurrentUser, require
from app.db import get_session
from app.models.base import utcnow
from app.models.identity import User
from app.models.rbac import Panel, Permission, Role, RolePanel, UserRole
from app.schemas.auth import MessageResponse
from app.schemas.identity import (
    PanelOut,
    PermissionOut,
    RoleCreate,
    RoleDetail,
    RoleUpdate,
)
from app.seed.definitions import BOOTSTRAP_ROLE_KEY
from app.services import audit
from app.services.identity import to_role_detail

router = APIRouter(tags=["roles"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
ManageRoles = Annotated[User, Depends(require("role:manage"))]


async def _load_role(session: AsyncSession, role_id: uuid.UUID) -> Role:
    result = await session.execute(
        select(Role)
        .where(Role.id == role_id, Role.deleted_at.is_(None))
        .options(selectinload(Role.permissions), selectinload(Role.panels))
    )
    role = result.scalar_one_or_none()
    if role is None:
        raise NotFoundError("No such role.")
    return role


async def _resolve_permissions(session: AsyncSession, keys: list[str]) -> list[Permission]:
    if not keys:
        return []
    result = await session.execute(select(Permission).where(Permission.key.in_(keys)))
    found = list(result.scalars())

    missing = set(keys) - {p.key for p in found}
    if missing:
        raise UnprocessableError(f"Unknown permission(s): {', '.join(sorted(missing))}.")
    return found


async def _validate_panels(session: AsyncSession, keys: list[str]) -> list[str]:
    if not keys:
        return []
    result = await session.execute(select(Panel.key).where(Panel.key.in_(keys)))
    found = set(result.scalars())

    missing = set(keys) - found
    if missing:
        raise UnprocessableError(f"Unknown panel(s): {', '.join(sorted(missing))}.")
    return sorted(found)


async def _set_panels(session: AsyncSession, role: Role, keys: list[str]) -> None:
    """Replace a role's visible panels wholesale."""
    for existing in list(role.panels):
        await session.delete(existing)
    await session.flush()

    for key in keys:
        session.add(RolePanel(role_id=role.id, panel_key=key, can_view=True))


# --------------------------------------------------------------------------- #
# Reference data — readable by anyone signed in, so the UI can label things
# --------------------------------------------------------------------------- #


@router.get("/permissions", response_model=list[PermissionOut], summary="All permissions")
async def list_permissions(session: SessionDep, _: CurrentUser) -> list[PermissionOut]:
    """Every permission the code enforces, for the role matrix UI."""
    result = await session.execute(
        select(Permission).order_by(Permission.resource, Permission.action)
    )
    return [PermissionOut.model_validate(p) for p in result.scalars()]


@router.get("/panels", response_model=list[PanelOut], summary="All panels")
async def list_panels(session: SessionDep, _: CurrentUser) -> list[PanelOut]:
    """Every navigable screen, for the panel visibility matrix."""
    result = await session.execute(select(Panel).order_by(Panel.sort_order, Panel.name))
    return [PanelOut.model_validate(p) for p in result.scalars()]


# --------------------------------------------------------------------------- #
# Roles
# --------------------------------------------------------------------------- #


@router.get("/roles", response_model=list[RoleDetail], summary="List roles")
async def list_roles(session: SessionDep, _: ManageRoles) -> list[RoleDetail]:
    result = await session.execute(
        select(Role)
        .where(Role.deleted_at.is_(None))
        .options(selectinload(Role.permissions), selectinload(Role.panels))
        .order_by(Role.is_system.desc(), Role.name)
    )
    return [await to_role_detail(session, role) for role in result.scalars()]


@router.post(
    "/roles",
    response_model=RoleDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Create a custom role",
)
async def create_role(
    payload: RoleCreate, session: SessionDep, actor: ManageRoles, request: Request
) -> RoleDetail:
    clash = await session.execute(select(Role).where(Role.key == payload.key))
    if clash.scalar_one_or_none() is not None:
        raise ConflictError(f"A role with the key {payload.key!r} already exists.")

    role = Role(
        key=payload.key,
        name=payload.name,
        description=payload.description,
        is_system=False,
        permissions=await _resolve_permissions(session, payload.permission_keys),
        panels=[],
    )
    session.add(role)
    await session.flush()

    await _set_panels(session, role, await _validate_panels(session, payload.panel_keys))
    await session.flush()
    await session.refresh(role, ["permissions", "panels"])

    await audit.record(
        session,
        action="role.created",
        actor=actor,
        entity_type="role",
        entity_id=role.id,
        after={
            "key": role.key,
            "permissions": sorted(payload.permission_keys),
            "panels": sorted(payload.panel_keys),
        },
        request=request,
    )
    return await to_role_detail(session, role)


@router.get("/roles/{role_id}", response_model=RoleDetail, summary="Get a role")
async def get_role(role_id: uuid.UUID, session: SessionDep, _: ManageRoles) -> RoleDetail:
    return await to_role_detail(session, await _load_role(session, role_id))


@router.patch("/roles/{role_id}", response_model=RoleDetail, summary="Update a role")
async def update_role(
    role_id: uuid.UUID,
    payload: RoleUpdate,
    session: SessionDep,
    actor: ManageRoles,
    request: Request,
) -> RoleDetail:
    """Rename a role, or replace its permission and panel sets.

    System roles may be renamed and have their panel visibility tuned, but their
    permissions are fixed — Super Admin in particular must keep every
    permission, or the instance can be locked out of its own administration.
    """
    role = await _load_role(session, role_id)
    before = {
        "name": role.name,
        "permissions": sorted(p.key for p in role.permissions),
        "panels": sorted(rp.panel_key for rp in role.panels),
    }

    if payload.name is not None:
        role.name = payload.name
    if payload.description is not None:
        role.description = payload.description

    if payload.permission_keys is not None:
        if role.key == BOOTSTRAP_ROLE_KEY:
            raise ForbiddenError(
                "Super Admin holds every permission by definition and cannot be narrowed."
            )
        role.permissions = await _resolve_permissions(session, payload.permission_keys)

    if payload.panel_keys is not None:
        await _set_panels(session, role, await _validate_panels(session, payload.panel_keys))

    await session.flush()
    await session.refresh(role, ["permissions", "panels"])

    await audit.record(
        session,
        action="role.updated",
        actor=actor,
        entity_type="role",
        entity_id=role.id,
        before=before,
        after={
            "name": role.name,
            "permissions": sorted(p.key for p in role.permissions),
            "panels": sorted(rp.panel_key for rp in role.panels),
        },
        request=request,
    )
    return await to_role_detail(session, role)


@router.delete("/roles/{role_id}", response_model=MessageResponse, summary="Delete a role")
async def delete_role(
    role_id: uuid.UUID, session: SessionDep, actor: ManageRoles, request: Request
) -> MessageResponse:
    role = await _load_role(session, role_id)

    if role.is_system:
        raise ForbiddenError("System roles cannot be deleted.")

    holders = await session.execute(
        select(func.count()).select_from(UserRole).where(UserRole.role_id == role.id)
    )
    count = holders.scalar_one()
    if count:
        # Deleting a role out from under its holders would silently strip their
        # access with no record of what they used to have.
        raise ConflictError(
            f"{count} user(s) still hold this role. Reassign them before deleting it."
        )

    role.deleted_at = utcnow()
    await audit.record(
        session,
        action="role.deleted",
        actor=actor,
        entity_type="role",
        entity_id=role.id,
        before={"key": role.key},
        request=request,
    )
    return MessageResponse(message=f"Role {role.name!r} deleted.")
