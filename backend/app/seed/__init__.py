"""Idempotent seeding of permissions, roles and panels.

Run on every api container start, immediately after migrations:

    python -m app.seed

Idempotency is the whole design. Re-running must never duplicate a row, and —
more importantly — must *attach* anything new. When a later phase adds a
permission, the next boot grants it to Super Admin automatically; without that,
the first operator would silently lack a capability the code already enforces.

Existing grants on non-system roles are left alone. An administrator who removed
a permission from Security Analyst meant it, and a redeploy must not undo it.
"""

from __future__ import annotations

import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.logging import configure_logging, get_logger
from app.models.rbac import Panel, Permission, Role, RolePanel
from app.seed.definitions import PANELS, PERMISSIONS, ROLES

log = get_logger(__name__)


async def seed_permissions(session: AsyncSession) -> dict[str, Permission]:
    """Insert missing permissions, update drifted descriptions."""
    existing = {p.key: p for p in (await session.execute(select(Permission))).scalars()}

    for definition in PERMISSIONS:
        current = existing.get(definition.key)
        if current is None:
            current = Permission(
                key=definition.key,
                resource=definition.resource,
                action=definition.action,
                description=definition.description,
            )
            session.add(current)
            existing[definition.key] = current
            log.info("seed_permission_created", key=definition.key)
        elif current.description != definition.description:
            # Wording is owned by the code, so the permission matrix UI cannot
            # drift away from what the endpoints actually enforce.
            current.description = definition.description

    await session.flush()
    return existing


async def seed_panels(session: AsyncSession) -> dict[str, Panel]:
    """Insert missing panels and keep their presentation in step with the code."""
    existing = {p.key: p for p in (await session.execute(select(Panel))).scalars()}

    for definition in PANELS:
        current = existing.get(definition.key)
        if current is None:
            current = Panel(
                key=definition.key,
                name=definition.name,
                route=definition.route,
                icon=definition.icon,
                nav_group=definition.nav_group,
                sort_order=definition.sort_order,
            )
            session.add(current)
            existing[definition.key] = current
            log.info("seed_panel_created", key=definition.key)
        else:
            # The route especially: if a screen moves, the sidebar must follow
            # or every role gets a dead link.
            current.name = definition.name
            current.route = definition.route
            current.icon = definition.icon
            current.nav_group = definition.nav_group
            current.sort_order = definition.sort_order

    await session.flush()
    return existing


async def seed_roles(session: AsyncSession) -> dict[str, Role]:
    """Insert missing roles and reconcile their grants."""
    permissions = await seed_permissions(session)
    panels = await seed_panels(session)

    result = await session.execute(
        select(Role).options(selectinload(Role.permissions), selectinload(Role.panels))
    )
    existing = {r.key: r for r in result.scalars()}

    for definition in ROLES:
        role = existing.get(definition.key)
        is_new = role is None

        if role is None:
            role = Role(
                key=definition.key,
                name=definition.name,
                description=definition.description,
                is_system=True,
                # Passing the collections explicitly marks them as loaded. Without
                # this, reading `role.permissions` below on a freshly-flushed row
                # triggers a lazy load — which is synchronous attribute access
                # attempting IO, and raises MissingGreenlet under asyncio.
                permissions=[],
                panels=[],
            )
            session.add(role)
            await session.flush()
            existing[definition.key] = role
            log.info("seed_role_created", key=definition.key)
        else:
            role.name = definition.name
            role.description = definition.description
            role.is_system = True

        # --- permissions ---
        wanted = (
            set(permissions)
            if definition.permissions == ["*"]
            else {key for key in definition.permissions if key in permissions}
        )
        held = {p.key for p in role.permissions}

        if definition.permissions == ["*"]:
            # Super Admin must always hold every permission, including ones
            # added by a later phase. This is the line that stops the first
            # operator quietly losing access to a new capability.
            for key in wanted - held:
                role.permissions.append(permissions[key])
                log.info("seed_role_permission_granted", role=definition.key, permission=key)
        elif is_new:
            # For other roles, only seed on creation. An administrator who later
            # revoked a permission meant it; a redeploy must not silently
            # re-grant it.
            for key in sorted(wanted):
                role.permissions.append(permissions[key])

        # --- panels ---
        wanted_panels = (
            set(panels)
            if definition.panels == ["*"]
            else {key for key in definition.panels if key in panels}
        )
        held_panels = {rp.panel_key for rp in role.panels}

        if definition.panels == ["*"]:
            for key in wanted_panels - held_panels:
                session.add(RolePanel(role_id=role.id, panel_key=key, can_view=True))
        elif is_new:
            for key in sorted(wanted_panels):
                session.add(RolePanel(role_id=role.id, panel_key=key, can_view=True))

    await session.flush()
    return existing


async def seed_all(session: AsyncSession) -> None:
    """Apply every seed. Safe to call repeatedly."""
    await seed_roles(session)
    log.info("seed_complete")


async def _main() -> None:
    from app.config import get_settings
    from app.db import dispose_engine, get_sessionmaker

    configure_logging(get_settings())
    async with get_sessionmaker()() as session:
        await seed_all(session)
        await session.commit()
    await dispose_engine()


if __name__ == "__main__":
    asyncio.run(_main())
