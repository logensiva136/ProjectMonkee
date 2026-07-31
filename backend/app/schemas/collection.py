"""Collection domain request/response models (SPEC §5.2, §9.2).

These shapes are what the OpenAPI schema exposes and what the frontend's
`api.gen.ts` is generated from (SPEC §9.0 Rule 0). Field names and optionality
are therefore user-facing decisions.
"""

from __future__ import annotations

import datetime as dt
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import Severity, SignalKind, SourceType

# --------------------------------------------------------------------------- #
# Source categories
# --------------------------------------------------------------------------- #


class SourceCategoryBase(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=100)]
    slug: Annotated[str, Field(min_length=1, max_length=100)]
    color: Annotated[str, Field(pattern=r"^#[0-9A-Fa-f]{6}$")] = "#64748B"
    icon: Annotated[str, Field(max_length=50)] = "folder"
    sort_order: int = 0


class SourceCategoryCreate(SourceCategoryBase):
    parent_id: str | None = None


class SourceCategoryUpdate(BaseModel):
    name: Annotated[str | None, Field(min_length=1, max_length=100)] = None
    color: Annotated[str | None, Field(pattern=r"^#[0-9A-Fa-f]{6}$")] = None
    icon: Annotated[str | None, Field(max_length=50)] = None
    sort_order: int | None = None
    parent_id: str | None = None


class SourceCategoryOut(SourceCategoryBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    parent_id: str | None
    is_system: bool
    created_at: dt.datetime
    updated_at: dt.datetime


class SourceCategoryTreeNode(SourceCategoryOut):
    """A category with its immediate children nested."""

    children: list[SourceCategoryTreeNode] = []


SourceCategoryTreeNode.model_rebuild()


class CategoryReorderItem(BaseModel):
    id: str
    sort_order: int
    parent_id: str | None = None


# --------------------------------------------------------------------------- #
# Sources
# --------------------------------------------------------------------------- #


class SourceBase(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=200)]
    type: SourceType
    url: Annotated[str, Field(min_length=1, max_length=4000)]
    category_id: str | None = None
    poll_interval_seconds: Annotated[int, Field(ge=60, le=86400)] = 10_800
    enabled: bool = True
    config: dict[str, Any] = {}
    default_severity: Severity | None = None
    tags: list[str] = []


class SourceCreate(SourceBase):
    pass


class SourceUpdate(BaseModel):
    name: Annotated[str | None, Field(min_length=1, max_length=200)] = None
    type: SourceType | None = None
    url: Annotated[str | None, Field(min_length=1, max_length=4000)] = None
    category_id: str | None = None
    poll_interval_seconds: Annotated[int | None, Field(ge=60, le=86400)] = None
    enabled: bool | None = None
    config: dict[str, Any] | None = None
    default_severity: Severity | None = None
    tags: list[str] | None = None


class SourceSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    type: str
    url: str
    enabled: bool
    health: str
    category_id: str | None
    last_polled_at: dt.datetime | None
    next_poll_at: dt.datetime | None
    consecutive_failures: int
    tags: list[str]
    created_at: dt.datetime
    updated_at: dt.datetime


class SourceDetail(SourceSummary):
    config: dict[str, Any]
    default_severity: str | None
    poll_interval_seconds: int
    last_status: str | None
    last_error: str | None


class SourceRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    source_id: str
    started_at: dt.datetime
    finished_at: dt.datetime | None
    status: str
    http_status: int | None
    items_seen: int
    items_new: int
    duration_ms: int | None
    error: str | None


class SourcePollResponse(BaseModel):
    """Result of an on-demand collection run."""

    run: SourceRunOut
    items_seen: int
    items_new: int


class SourceTestResponse(BaseModel):
    """Result of a dry-run fetch that does not persist signals."""

    ok: bool
    http_status: int | None
    items_found: int
    sample_title: str | None
    error: str | None


class SourceTypeInfo(BaseModel):
    """One registered adapter, for the source form dropdown."""

    type: str
    label: str


# --------------------------------------------------------------------------- #
# Signals
# --------------------------------------------------------------------------- #


class SignalTagOut(BaseModel):
    tag: str
    created_at: dt.datetime


class SignalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    source_id: str
    kind: str
    external_id: str
    title: str
    url: str | None
    summary: str | None
    content: str | None
    author: str | None
    published_at: dt.datetime | None
    collected_at: dt.datetime
    severity_hint: str | None
    language: str | None
    tags: list[SignalTagOut]
    created_at: dt.datetime
    updated_at: dt.datetime


class SignalTagPayload(BaseModel):
    tag: Annotated[str, Field(min_length=1, max_length=64)]


class SignalListParams(BaseModel):
    """Query parameters for the signal explorer.

    Kept as a Pydantic model so the generated schema is explicit.
    """

    source_id: str | None = None
    kind: SignalKind | None = None
    q: Annotated[str | None, Field(max_length=200)] = None
    severity: Severity | None = None
    tag: str | None = None
    cursor: str | None = None
    limit: Annotated[int, Field(ge=1, le=200)] = 50


# --------------------------------------------------------------------------- #
# OPML
# --------------------------------------------------------------------------- #


class OpmlImportSummary(BaseModel):
    created: int
    updated: int
    failed: int
    errors: list[str]


class OpmlExportOut(BaseModel):
    opml: str
