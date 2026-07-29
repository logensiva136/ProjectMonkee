"""`GET /me` — everything the frontend needs to render itself (SPEC §6.3).

The sidebar, the route guards and the org branding are all built from this one
response. Panel visibility here is UX; the backend enforces permissions
independently on every endpoint.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rbac import CurrentUser, permissions_of
from app.db import get_session
from app.models.rbac import Panel, RolePanel
from app.schemas.identity import MeResponse, PanelOut
from app.services import setup as setup_service
from app.services.identity import logo_url, to_role_summary, to_user_summary

router = APIRouter(tags=["me"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.get("/me", response_model=MeResponse, summary="The signed-in user and their access")
async def me(user: CurrentUser, session: SessionDep) -> MeResponse:
    role_ids = [role.id for role in user.roles if role.deleted_at is None]

    # A panel is visible if ANY of the user's roles grants it. Union rather than
    # intersection: holding an extra role must never take navigation away.
    panels: list[Panel] = []
    if role_ids:
        result = await session.execute(
            select(Panel)
            .join(RolePanel, RolePanel.panel_key == Panel.key)
            .where(RolePanel.role_id.in_(role_ids), RolePanel.can_view.is_(True))
            .distinct()
            .order_by(Panel.sort_order, Panel.name)
        )
        panels = list(result.scalars())

    setting = await setup_service.get_app_setting(session)

    return MeResponse(
        user=to_user_summary(user),
        roles=[to_role_summary(role) for role in user.roles if role.deleted_at is None],
        permissions=sorted(permissions_of(user)),
        panels=[PanelOut.model_validate(panel) for panel in panels],
        org_name=setting.org_name if setting else None,
        org_initials=setting.org_initials if setting else None,
        org_logo_url=logo_url(setting.org_logo_path) if setting else None,
        brand_color=setting.brand_color if setting else "#22D3EE",
        timezone=setting.timezone if setting else "Asia/Kuala_Lumpur",
    )
