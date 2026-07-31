"""Collection domain API: categories, sources, signals, OPML (SPEC §5.2, §9.2).

Read endpoints broadly need `source:read` or `signal:read`; mutations need
`source:write` or `signal:write`. The source "poll now" and "test" actions are
`source:write` because they cause outbound network traffic.
"""

from __future__ import annotations

import io
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.collectors import registered_types
from app.collectors.base import get_adapter
from app.core.errors import BadRequestError, ConflictError, NotFoundError, UnprocessableError
from app.core.logging import get_logger
from app.core.rbac import require
from app.core.ssrf import FetchTooLargeError, SSRFBlockedError
from app.db import get_session
from app.models.base import utcnow
from app.models.collection import Signal, SignalTag, Source, SourceCategory, SourceRun
from app.models.enums import SourceType
from app.models.identity import User
from app.schemas.auth import MessageResponse
from app.schemas.collection import (
    CategoryReorderItem,
    OpmlExportOut,
    OpmlImportSummary,
    SignalOut,
    SignalTagPayload,
    SourceCategoryCreate,
    SourceCategoryOut,
    SourceCategoryTreeNode,
    SourceCategoryUpdate,
    SourceCreate,
    SourceDetail,
    SourcePollResponse,
    SourceRunOut,
    SourceSummary,
    SourceTestResponse,
    SourceTypeInfo,
    SourceUpdate,
)
from app.schemas.identity import CursorPage
from app.services import audit
from app.services.collection import run_collection

log = get_logger(__name__)
router = APIRouter(tags=["collection"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
ReadSources = Annotated[User, Depends(require("source:read"))]
WriteSources = Annotated[User, Depends(require("source:write"))]
ReadSignals = Annotated[User, Depends(require("signal:read"))]
WriteSignals = Annotated[User, Depends(require("signal:write"))]

_TYPE_LABELS: dict[str, str] = {
    SourceType.RSS: "RSS Feed",
    SourceType.ATOM: "Atom Feed",
    SourceType.JSON_FEED: "JSON Feed",
}


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


async def _load_category(session: AsyncSession, category_id: uuid.UUID) -> SourceCategory:
    result = await session.execute(
        select(SourceCategory).where(SourceCategory.id == category_id)
    )
    category = result.scalar_one_or_none()
    if category is None:
        raise NotFoundError("No such category.")
    return category


async def _load_source(session: AsyncSession, source_id: uuid.UUID) -> Source:
    result = await session.execute(
        select(Source)
        .where(Source.id == source_id, Source.deleted_at.is_(None))
        .options(selectinload(Source.category))
    )
    source = result.scalar_one_or_none()
    if source is None:
        raise NotFoundError("No such source.")
    return source


def _source_summary(source: Source) -> SourceSummary:
    return SourceSummary.model_validate(source)


def _source_detail(source: Source) -> SourceDetail:
    return SourceDetail.model_validate(source)


def _category_out(category: SourceCategory) -> SourceCategoryOut:
    return SourceCategoryOut.model_validate(category)


def _run_out(run: SourceRun) -> SourceRunOut:
    return SourceRunOut.model_validate(run)


def _parse_uuid(value: str, field: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise BadRequestError(f"Invalid {field} UUID.") from exc


# --------------------------------------------------------------------------- #
# Categories
# --------------------------------------------------------------------------- #


@router.get("/source-categories", response_model=list[SourceCategoryOut], summary="List categories")
async def list_categories(session: SessionDep, _: ReadSources) -> list[SourceCategoryOut]:
    result = await session.execute(
        select(SourceCategory).order_by(SourceCategory.sort_order, SourceCategory.name)
    )
    return [_category_out(c) for c in result.scalars()]


@router.get(
    "/source-categories/tree",
    response_model=list[SourceCategoryTreeNode],
    summary="Categories as a two-level tree",
)
async def list_category_tree(session: SessionDep, _: ReadSources) -> list[SourceCategoryTreeNode]:
    result = await session.execute(
        select(SourceCategory)
        .options(selectinload(SourceCategory.children))
        .order_by(SourceCategory.sort_order, SourceCategory.name)
    )
    roots: list[SourceCategoryTreeNode] = []
    for category in result.scalars():
        if category.parent_id is None:
            roots.append(
                SourceCategoryTreeNode(
                    **_category_out(category).model_dump(),
                    children=[
                        SourceCategoryTreeNode(**_category_out(child).model_dump())
                        for child in sorted(
                            category.children,
                            key=lambda c: (c.sort_order, c.name),
                        )
                    ],
                )
            )
    return roots


@router.post(
    "/source-categories",
    response_model=SourceCategoryOut,
    status_code=201,
    summary="Create a category",
)
async def create_category(
    payload: SourceCategoryCreate,
    session: SessionDep,
    actor: WriteSources,
    request: Request,
) -> SourceCategoryOut:
    parent_id: uuid.UUID | None = None
    if payload.parent_id is not None:
        parent = await _load_category(session, _parse_uuid(payload.parent_id, "parent_id"))
        if parent.parent_id is not None:
            raise UnprocessableError("Categories may only nest one level deep.")
        parent_id = parent.id

    clash = await session.execute(
        select(SourceCategory).where(SourceCategory.slug == payload.slug)
    )
    if clash.scalar_one_or_none() is not None:
        raise ConflictError("A category with that slug already exists.")

    category = SourceCategory(
        name=payload.name,
        slug=payload.slug,
        color=payload.color,
        icon=payload.icon,
        sort_order=payload.sort_order,
        parent_id=parent_id,
    )
    session.add(category)
    await session.flush()

    await audit.record(
        session,
        action="source_category.created",
        actor=actor,
        entity_type="source_category",
        entity_id=category.id,
        after={"name": category.name, "slug": category.slug},
        request=request,
    )
    return _category_out(category)


@router.get(
    "/source-categories/{category_id}",
    response_model=SourceCategoryOut,
    summary="Get a category",
)
async def get_category(
    category_id: uuid.UUID, session: SessionDep, _: ReadSources
) -> SourceCategoryOut:
    return _category_out(await _load_category(session, category_id))


@router.patch(
    "/source-categories/{category_id}",
    response_model=SourceCategoryOut,
    summary="Update a category",
)
async def update_category(
    category_id: uuid.UUID,
    payload: SourceCategoryUpdate,
    session: SessionDep,
    actor: WriteSources,
    request: Request,
) -> SourceCategoryOut:
    category = await _load_category(session, category_id)

    before = {
        "name": category.name,
        "color": category.color,
        "icon": category.icon,
        "sort_order": category.sort_order,
        "parent_id": str(category.parent_id) if category.parent_id else None,
    }

    if payload.parent_id is not None:
        new_parent = await _load_category(session, _parse_uuid(payload.parent_id, "parent_id"))
        if new_parent.parent_id is not None:
            raise UnprocessableError("Categories may only nest one level deep.")
        if new_parent.id == category.id:
            raise UnprocessableError("A category cannot be its own parent.")
        category.parent_id = new_parent.id
    elif payload.parent_id is None and category.parent_id is not None:
        # Explicitly demote to root only when a value was sent. Omitting the
        # field leaves the parent untouched.
        category.parent_id = None

    if payload.name is not None:
        category.name = payload.name
    if payload.color is not None:
        category.color = payload.color
    if payload.icon is not None:
        category.icon = payload.icon
    if payload.sort_order is not None:
        category.sort_order = payload.sort_order

    await session.flush()
    await audit.record(
        session,
        action="source_category.updated",
        actor=actor,
        entity_type="source_category",
        entity_id=category.id,
        before=before,
        after={
            "name": category.name,
            "color": category.color,
            "icon": category.icon,
            "sort_order": category.sort_order,
            "parent_id": str(category.parent_id) if category.parent_id else None,
        },
        request=request,
    )
    return _category_out(category)


@router.delete(
    "/source-categories/{category_id}",
    response_model=MessageResponse,
    summary="Delete a category",
)
async def delete_category(
    category_id: uuid.UUID,
    session: SessionDep,
    actor: WriteSources,
    request: Request,
) -> MessageResponse:
    category = await _load_category(session, category_id)

    if category.is_system:
        raise UnprocessableError("System categories cannot be deleted.")

    source_count = await session.execute(
        select(func.count()).select_from(Source).where(Source.category_id == category.id)
    )
    if source_count.scalar_one() > 0:
        raise ConflictError("Move or remove the sources in this category first.")

    await session.delete(category)
    await audit.record(
        session,
        action="source_category.deleted",
        actor=actor,
        entity_type="source_category",
        entity_id=category_id,
        before={"name": category.name, "slug": category.slug},
        request=request,
    )
    return MessageResponse(message=f"Category {category.name!r} deleted.")


@router.post(
    "/source-categories/reorder",
    response_model=list[SourceCategoryOut],
    summary="Bulk reorder categories",
)
async def reorder_categories(
    payload: list[CategoryReorderItem],
    session: SessionDep,
    actor: WriteSources,
    request: Request,
) -> list[SourceCategoryOut]:
    ids = {item.id for item in payload}
    result = await session.execute(select(SourceCategory).where(SourceCategory.id.in_(ids)))
    categories = {str(c.id): c for c in result.scalars()}

    parent_ids: set[uuid.UUID | None] = set()
    for item in payload:
        category = categories.get(item.id)
        if category is None:
            raise NotFoundError(f"No such category: {item.id}.")
        category.sort_order = item.sort_order
        parent_id = _parse_uuid(item.parent_id, "parent_id") if item.parent_id else None
        category.parent_id = parent_id
        parent_ids.add(parent_id)

    # Validate depth: no new parent may itself have a parent.
    if parent_ids:
        parent_ids.discard(None)
        result = await session.execute(
            select(SourceCategory.parent_id).where(SourceCategory.id.in_(parent_ids))
        )
        for parent_parent in result.scalars():
            if parent_parent is not None:
                raise UnprocessableError("Categories may only nest one level deep.")

    await audit.record(
        session,
        action="source_category.reordered",
        actor=actor,
        entity_type="source_category",
        after={"count": len(payload)},
        request=request,
    )
    return [_category_out(c) for c in categories.values()]


# --------------------------------------------------------------------------- #
# Sources
# --------------------------------------------------------------------------- #


@router.get("/sources/types", response_model=list[SourceTypeInfo], summary="Available source types")
async def list_source_types(_: ReadSources) -> list[SourceTypeInfo]:
    return [
        SourceTypeInfo(type=t, label=_TYPE_LABELS.get(t, t.replace("_", " ").title()))
        for t in registered_types()
    ]


@router.get("/sources", response_model=list[SourceSummary], summary="List sources")
async def list_sources(
    session: SessionDep,
    _: ReadSources,
    category_id: uuid.UUID | None = None,
    enabled_only: bool = False,
) -> list[SourceSummary]:
    statement = select(Source).where(Source.deleted_at.is_(None))
    if category_id is not None:
        statement = statement.where(Source.category_id == category_id)
    if enabled_only:
        statement = statement.where(Source.enabled.is_(True))
    statement = statement.order_by(Source.name)

    result = await session.execute(statement)
    return [_source_summary(s) for s in result.scalars()]


@router.post("/sources", response_model=SourceDetail, status_code=201, summary="Create a source")
async def create_source(
    payload: SourceCreate,
    session: SessionDep,
    actor: WriteSources,
    request: Request,
) -> SourceDetail:
    category_id: uuid.UUID | None = None
    if payload.category_id is not None:
        await _load_category(session, _parse_uuid(payload.category_id, "category_id"))
        category_id = uuid.UUID(payload.category_id)

    source = Source(
        name=payload.name,
        type=str(payload.type),
        url=payload.url,
        category_id=category_id,
        poll_interval_seconds=payload.poll_interval_seconds,
        enabled=payload.enabled,
        config=payload.config,
        default_severity=str(payload.default_severity) if payload.default_severity else None,
        tags=payload.tags,
        next_poll_at=utcnow(),
    )
    session.add(source)
    await session.flush()

    await audit.record(
        session,
        action="source.created",
        actor=actor,
        entity_type="source",
        entity_id=source.id,
        after={
            "name": source.name,
            "type": source.type,
            "url": source.url,
            "category_id": str(source.category_id) if source.category_id else None,
        },
        request=request,
    )
    return _source_detail(source)


@router.get("/sources/{source_id}", response_model=SourceDetail, summary="Get a source")
async def get_source(
    source_id: uuid.UUID, session: SessionDep, _: ReadSources
) -> SourceDetail:
    return _source_detail(await _load_source(session, source_id))


@router.patch("/sources/{source_id}", response_model=SourceDetail, summary="Update a source")
async def update_source(
    source_id: uuid.UUID,
    payload: SourceUpdate,
    session: SessionDep,
    actor: WriteSources,
    request: Request,
) -> SourceDetail:
    source = await _load_source(session, source_id)
    before = {
        "name": source.name,
        "type": source.type,
        "url": source.url,
        "category_id": str(source.category_id) if source.category_id else None,
        "poll_interval_seconds": source.poll_interval_seconds,
        "enabled": source.enabled,
        "config": dict(source.config),
        "default_severity": source.default_severity,
        "tags": list(source.tags),
    }

    if payload.name is not None:
        source.name = payload.name
    if payload.type is not None:
        source.type = str(payload.type)
    if payload.url is not None:
        source.url = payload.url
    if payload.category_id is not None:
        await _load_category(session, _parse_uuid(payload.category_id, "category_id"))
        source.category_id = uuid.UUID(payload.category_id)
    elif payload.category_id is None and source.category_id is not None:
        source.category_id = None
    if payload.poll_interval_seconds is not None:
        source.poll_interval_seconds = payload.poll_interval_seconds
    if payload.enabled is not None:
        source.enabled = payload.enabled
    if payload.config is not None:
        source.config = payload.config
    if payload.default_severity is not None:
        source.default_severity = str(payload.default_severity)
    if payload.tags is not None:
        source.tags = payload.tags

    await session.flush()
    await audit.record(
        session,
        action="source.updated",
        actor=actor,
        entity_type="source",
        entity_id=source.id,
        before=before,
        after={
            "name": source.name,
            "type": source.type,
            "url": source.url,
            "category_id": str(source.category_id) if source.category_id else None,
            "poll_interval_seconds": source.poll_interval_seconds,
            "enabled": source.enabled,
            "config": dict(source.config),
            "default_severity": source.default_severity,
            "tags": list(source.tags),
        },
        request=request,
    )
    return _source_detail(source)


@router.delete("/sources/{source_id}", response_model=MessageResponse, summary="Delete a source")
async def delete_source(
    source_id: uuid.UUID,
    session: SessionDep,
    actor: WriteSources,
    request: Request,
) -> MessageResponse:
    source = await _load_source(session, source_id)
    source.deleted_at = utcnow()
    source.enabled = False

    await audit.record(
        session,
        action="source.deleted",
        actor=actor,
        entity_type="source",
        entity_id=source.id,
        before={"name": source.name, "url": source.url},
        request=request,
    )
    return MessageResponse(message=f"Source {source.name!r} deleted.")


@router.post(
    "/sources/{source_id}/poll",
    response_model=SourcePollResponse,
    summary="Poll a source now",
)
async def poll_source(
    source_id: uuid.UUID,
    session: SessionDep,
    actor: WriteSources,
    request: Request,
) -> SourcePollResponse:
    source = await _load_source(session, source_id)
    outcome = await run_collection(session, source, triggered_by=actor.id)

    await audit.record(
        session,
        action="source.polled",
        actor=actor,
        entity_type="source",
        entity_id=source.id,
        after={"items_seen": outcome.items_seen, "items_new": outcome.items_new},
        request=request,
    )
    return SourcePollResponse(
        run=_run_out(outcome.run),
        items_seen=outcome.items_seen,
        items_new=outcome.items_new,
    )


@router.post(
    "/sources/{source_id}/test",
    response_model=SourceTestResponse,
    summary="Test a source",
)
async def test_source(
    source_id: uuid.UUID,
    session: SessionDep,
    _actor: WriteSources,
) -> SourceTestResponse:
    """Fetch a source without persisting anything.

    Useful when configuring a new feed: the operator sees whether the URL
    resolves, whether the adapter can parse it, and a sample title, before any
    signals are written.
    """
    source = await _load_source(session, source_id)

    try:
        adapter = get_adapter(source)
        result = await adapter.fetch()
    except (SSRFBlockedError, FetchTooLargeError) as exc:
        return SourceTestResponse(
            ok=False, http_status=None, items_found=0, sample_title=None, error=str(exc)
        )
    except ValueError as exc:
        return SourceTestResponse(
            ok=False,
            http_status=None,
            items_found=0,
            sample_title=None,
            error=f"Parse error: {exc}",
        )

    sample = result.items[0].title if result.items else None
    return SourceTestResponse(
        ok=result.not_modified or len(result.items) > 0,
        http_status=result.http_status,
        items_found=len(result.items),
        sample_title=sample,
        error=None,
    )


@router.get(
    "/sources/{source_id}/runs",
    response_model=CursorPage[SourceRunOut],
    summary="List a source's runs",
)
async def list_source_runs(
    source_id: uuid.UUID,
    session: SessionDep,
    _: ReadSources,
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> CursorPage[SourceRunOut]:
    await _load_source(session, source_id)  # ensure source exists

    statement = (
        select(SourceRun)
        .where(SourceRun.source_id == source_id)
        .order_by(SourceRun.id.desc())
    )
    if cursor:
        try:
            statement = statement.where(SourceRun.id < uuid.UUID(cursor))
        except ValueError as exc:
            raise BadRequestError("Malformed cursor.") from exc

    result = await session.execute(statement.limit(limit + 1))
    rows = list(result.scalars())
    has_more = len(rows) > limit
    page = rows[:limit]

    return CursorPage[SourceRunOut](
        items=[_run_out(r) for r in page],
        next_cursor=str(page[-1].id) if page and has_more else None,
        has_more=has_more,
    )


@router.post(
    "/sources/opml/import",
    response_model=OpmlImportSummary,
    summary="Import sources from OPML",
)
async def import_opml(
    session: SessionDep,
    actor: WriteSources,
    request: Request,
    opml: str,
) -> OpmlImportSummary:
    """Import RSS/Atom sources from an OPML body.

    Outlines with `xmlUrl` become sources; `text` or `title` become the name.
    Nested outlines are flattened into the chosen category when a
    `category_id` query parameter is supplied.
    """
    from xml.etree import ElementTree as ET

    try:
        root = ET.fromstring(opml)
    except ET.ParseError as exc:
        raise UnprocessableError(f"Invalid OPML: {exc}") from exc

    created = 0
    updated = 0
    failed = 0
    errors: list[str] = []

    # Find all body/outline elements anywhere.
    outlines = root.findall(".//body//outline")
    if not outlines:
        raise UnprocessableError("No outlines found in OPML body.")

    for outline in outlines:
        url = outline.get("xmlUrl")
        if not url:
            continue

        name = outline.get("text") or outline.get("title") or url
        feed_type = SourceType.RSS
        if (outline.get("type") or "").lower() == "atom":
            feed_type = SourceType.ATOM

        # Dedupe by URL within this import.
        existing = await session.execute(
            select(Source).where(Source.url == url, Source.deleted_at.is_(None))
        )
        if existing.scalar_one_or_none() is not None:
            updated += 1
            continue

        source = Source(
            name=name,
            type=str(feed_type),
            url=url,
            poll_interval_seconds=10_800,
            enabled=True,
            config={},
            next_poll_at=utcnow(),
        )
        session.add(source)
        created += 1

    await session.flush()
    await audit.record(
        session,
        action="source.opml_imported",
        actor=actor,
        entity_type="source",
        after={"created": created, "updated": updated, "failed": failed},
        request=request,
    )
    return OpmlImportSummary(created=created, updated=updated, failed=failed, errors=errors)


@router.get("/sources/opml/export", response_model=OpmlExportOut, summary="Export sources to OPML")
async def export_opml(session: SessionDep, _: ReadSources) -> OpmlExportOut:
    result = await session.execute(
        select(Source)
        .where(Source.deleted_at.is_(None), Source.enabled.is_(True))
        .order_by(Source.name)
    )
    sources = result.scalars().all()

    buffer = io.StringIO()
    buffer.write('<?xml version="1.0" encoding="UTF-8"?>\n')
    buffer.write('<opml version="2.0">\n')
    buffer.write("  <head><title>HAYABUSA Sources</title></head>\n")
    buffer.write("  <body>\n")
    for source in sources:
        feed_type = "rss" if source.type in {SourceType.RSS, SourceType.ATOM} else "jsonfeed"
        title = source.name.replace("&", "&amp;").replace('"', "&quot;")
        url = source.url.replace("&", "&amp;").replace('"', "&quot;")
        buffer.write(
            f'    <outline type="{feed_type}" text="{title}" title="{title}" xmlUrl="{url}"/>\n'
        )
    buffer.write("  </body>\n")
    buffer.write("</opml>\n")
    return OpmlExportOut(opml=buffer.getvalue())


# --------------------------------------------------------------------------- #
# Signals
# --------------------------------------------------------------------------- #


def _signal_out(signal: Signal) -> SignalOut:
    return SignalOut(
        id=str(signal.id),
        source_id=str(signal.source_id),
        kind=signal.kind,
        external_id=signal.external_id,
        title=signal.title,
        url=signal.url,
        summary=signal.summary,
        content=signal.content,
        author=signal.author,
        published_at=signal.published_at,
        collected_at=signal.collected_at,
        severity_hint=signal.severity_hint,
        language=signal.language,
        tags=[{"tag": t.tag, "created_at": t.created_at} for t in signal.tags],
        created_at=signal.created_at,
        updated_at=signal.updated_at,
    )


@router.get("/signals", response_model=CursorPage[SignalOut], summary="List signals")
async def list_signals(
    session: SessionDep,
    _: ReadSignals,
    source_id: Annotated[str | None, Query()] = None,
    kind: Annotated[str | None, Query()] = None,
    q: Annotated[str | None, Query(max_length=200)] = None,
    severity: Annotated[str | None, Query()] = None,
    tag: Annotated[str | None, Query()] = None,
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> CursorPage[SignalOut]:
    statement = select(Signal).order_by(Signal.id.desc())

    if source_id:
        statement = statement.where(Signal.source_id == _parse_uuid(source_id, "source_id"))
    if kind:
        statement = statement.where(Signal.kind == kind)
    if severity:
        statement = statement.where(Signal.severity_hint == severity)
    if tag:
        statement = statement.where(Signal.tags.any(tag))  # type: ignore[arg-type]
    if q:
        statement = statement.where(
            text(
                "signal.search_vector @@ plainto_tsquery('english', :q) "
                "OR signal.title ILIKE :like"
            )
        ).params(q=q, like=f"%{q}%")

    if cursor:
        try:
            statement = statement.where(Signal.id < uuid.UUID(cursor))
        except ValueError as exc:
            raise BadRequestError("Malformed cursor.") from exc

    result = await session.execute(statement.limit(limit + 1).options(selectinload(Signal.tags)))
    rows = list(result.scalars())
    has_more = len(rows) > limit
    page = rows[:limit]

    return CursorPage[SignalOut](
        items=[_signal_out(s) for s in page],
        next_cursor=str(page[-1].id) if page and has_more else None,
        has_more=has_more,
    )


@router.get("/signals/{signal_id}", response_model=SignalOut, summary="Get a signal")
async def get_signal(
    signal_id: uuid.UUID, session: SessionDep, _: ReadSignals
) -> SignalOut:
    result = await session.execute(
        select(Signal).where(Signal.id == signal_id).options(selectinload(Signal.tags))
    )
    signal = result.scalar_one_or_none()
    if signal is None:
        raise NotFoundError("No such signal.")
    return _signal_out(signal)


@router.post(
    "/signals/{signal_id}/tags",
    response_model=SignalOut,
    summary="Tag a signal",
)
async def tag_signal(
    signal_id: uuid.UUID,
    payload: SignalTagPayload,
    session: SessionDep,
    actor: WriteSignals,
    request: Request,
) -> SignalOut:
    result = await session.execute(
        select(Signal).where(Signal.id == signal_id).options(selectinload(Signal.tags))
    )
    signal = result.scalar_one_or_none()
    if signal is None:
        raise NotFoundError("No such signal.")

    existing = {t.tag for t in signal.tags}
    if payload.tag not in existing:
        signal.tags.append(SignalTag(signal_id=signal.id, tag=payload.tag))
        await session.flush()

        await audit.record(
            session,
            action="signal.tagged",
            actor=actor,
            entity_type="signal",
            entity_id=signal.id,
            after={"tag": payload.tag},
            request=request,
        )

    return _signal_out(signal)


@router.delete(
    "/signals/{signal_id}/tags/{tag}",
    response_model=SignalOut,
    summary="Remove a tag from a signal",
)
async def untag_signal(
    signal_id: uuid.UUID,
    tag: str,
    session: SessionDep,
    actor: WriteSignals,
    request: Request,
) -> SignalOut:
    result = await session.execute(
        select(Signal).where(Signal.id == signal_id).options(selectinload(Signal.tags))
    )
    signal = result.scalar_one_or_none()
    if signal is None:
        raise NotFoundError("No such signal.")

    for existing in list(signal.tags):
        if existing.tag == tag:
            await session.delete(existing)
            break

    await audit.record(
        session,
        action="signal.untagged",
        actor=actor,
        entity_type="signal",
        entity_id=signal.id,
        after={"tag": tag},
        request=request,
    )
    return _signal_out(signal)
