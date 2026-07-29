"""Audit log reading (SPEC §7, §9.2 /admin/audit).

Read-only by design. There is no endpoint to edit or delete an audit row,
because a mutable audit trail is not evidence of anything.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import BadRequestError
from app.core.rbac import require
from app.db import get_session
from app.models.identity import AuditLog, User
from app.schemas.identity import AuditLogOut, CursorPage

router = APIRouter(prefix="/audit-logs", tags=["audit"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
ReadAudit = Annotated[User, Depends(require("audit:read"))]

MAX_LIMIT = 200


def _to_out(entry: AuditLog) -> AuditLogOut:
    return AuditLogOut(
        id=str(entry.id),
        actor_id=str(entry.actor_id) if entry.actor_id else None,
        actor_username=entry.actor_username,
        action=entry.action,
        entity_type=entry.entity_type,
        entity_id=entry.entity_id,
        before=entry.before,
        after=entry.after,
        ip=str(entry.ip) if entry.ip else None,
        ua=entry.ua,
        request_id=entry.request_id,
        created_at=entry.created_at,
    )


@router.get("", response_model=CursorPage[AuditLogOut], summary="Read the audit log")
async def list_audit_logs(
    session: SessionDep,
    _: ReadAudit,
    actor_id: uuid.UUID | None = None,
    action: Annotated[str | None, Query(description="Exact match, or a `prefix.` match")] = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    cursor: Annotated[str | None, Query(description="`id` of the last row seen")] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = 50,
) -> CursorPage[AuditLogOut]:
    """Newest first, cursor-paginated.

    The cursor is the last row's `id`. Because ids are UUIDv7 and therefore
    time-ordered, "everything older than this id" is both an index seek and
    stable while new rows are being written — an OFFSET would shift under the
    reader as the log grows.
    """
    statement = select(AuditLog).order_by(AuditLog.id.desc())

    if actor_id is not None:
        statement = statement.where(AuditLog.actor_id == actor_id)
    if entity_type:
        statement = statement.where(AuditLog.entity_type == entity_type)
    if entity_id:
        statement = statement.where(AuditLog.entity_id == entity_id)
    if action:
        # "user." matches every user action; "user.created" matches exactly one.
        if action.endswith("."):
            statement = statement.where(AuditLog.action.startswith(action))
        else:
            statement = statement.where(AuditLog.action == action)

    if cursor:
        try:
            statement = statement.where(AuditLog.id < uuid.UUID(cursor))
        except ValueError as exc:
            raise BadRequestError("Malformed cursor.") from exc

    # Fetch one extra row to discover whether another page exists, without a
    # second COUNT query over a table that only grows.
    result = await session.execute(statement.limit(limit + 1))
    rows = list(result.scalars())

    has_more = len(rows) > limit
    page = rows[:limit]

    return CursorPage[AuditLogOut](
        items=[_to_out(entry) for entry in page],
        next_cursor=str(page[-1].id) if page and has_more else None,
        has_more=has_more,
    )
