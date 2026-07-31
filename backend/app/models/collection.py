"""Sources, collection runs and collected signals (SPEC §5.2).

This is the spine every later phase hangs off: CVEs, vendor matches, component
events and EASM changes all arrive as `signal` rows with a different `kind`, so
the rule engine sees one table rather than five silos (SPEC §3).

Two dedupe keys, doing different jobs:

* `UNIQUE (source_id, external_id)` — the same feed re-serving the same entry.
  This is the common case and it fires on nearly every poll.
* `UNIQUE (content_hash)` — the same story arriving from two different sources.
  This is what stops one advisory reposted by four outlets producing four alerts.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Computed,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import RunStatus, SignalKind, SourceHealth, SourceType

if TYPE_CHECKING:
    pass


class SourceCategory(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A grouping for sources — "Threat Intel", "Regulatory", and so on.

    Two levels only (SPEC §5.2). The constraint is enforced in the service
    layer rather than by the schema, because expressing "a parent may not itself
    have a parent" in SQL needs a trigger, and a trigger is a worse thing to
    debug than a check in one place.

    Fully CRUD-able including the seeded ones: a system category may be renamed
    and recoloured, but not deleted while sources still reference it.
    """

    __tablename__ = "source_category"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    color: Mapped[str] = mapped_column(String(9), nullable=False, server_default="#64748B")
    icon: Mapped[str] = mapped_column(String(50), nullable=False, server_default="folder")
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("source_category.id", ondelete="SET NULL"), nullable=True, index=True
    )
    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0"), index=True
    )
    is_system: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )

    parent: Mapped[SourceCategory | None] = relationship(
        remote_side="SourceCategory.id", back_populates="children"
    )
    children: Mapped[list[SourceCategory]] = relationship(back_populates="parent")
    sources: Mapped[list[Source]] = relationship(back_populates="category")


class Source(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    """A place items are collected from (SPEC §5.2).

    Scheduling is driven by `next_poll_at`, not by a per-source RedBeat entry:
    one fixed 60-second `dispatch_due_sources` task selects everything due and
    fans out. That keeps the schedule in Postgres where it can be queried and
    edited, and keeps RedBeat holding a handful of entries rather than hundreds.
    """

    __tablename__ = "source"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("source_category.id", ondelete="SET NULL"), nullable=True, index=True
    )

    poll_interval_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("10800")
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true"), index=True
    )

    #: Adapter-specific settings — which JSON field holds the id, a CSS selector
    #: for an HTML advisory page, and so on.
    config: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    #: AES-GCM ciphertext for sources behind an API key. Never returned by the API.
    credentials_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- conditional GET (SPEC §8) ---
    # Sending these back means a well-behaved server answers 304 with no body,
    # which is the difference between polling 40 feeds hourly and being
    # rate-limited by them.
    etag: Mapped[str | None] = mapped_column(String(400), nullable=True)
    last_modified: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # --- scheduling and health ---
    last_polled_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    next_poll_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    last_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    consecutive_failures: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    health: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=SourceHealth.HEALTHY,
        server_default="healthy",
        index=True,
    )

    default_severity: Mapped[str | None] = mapped_column(String(16), nullable=True)
    tags: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False, default=list, server_default=text("'{}'::varchar[]")
    )

    category: Mapped[SourceCategory | None] = relationship(back_populates="sources")
    runs: Mapped[list[SourceRun]] = relationship(
        back_populates="source", cascade="all, delete-orphan"
    )

    __table_args__ = (
        # The dispatcher's hot query: "enabled, not deleted, and due". A partial
        # index keeps it off disabled and removed rows entirely.
        Index(
            "ix_source_due",
            "next_poll_at",
            postgresql_where=text("enabled IS TRUE AND deleted_at IS NULL"),
        ),
        CheckConstraint("poll_interval_seconds >= 60", name="min_poll_interval"),
    )


class SourceRun(UUIDPrimaryKeyMixin, Base):
    """One collection attempt (SPEC §5.2).

    The operational record behind the source health screen: what was tried,
    what came back, how long it took, and why it failed.
    """

    __tablename__ = "source_run"

    source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("source.id", ondelete="CASCADE"), nullable=False, index=True
    )
    started_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    finished_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=RunStatus.RUNNING)
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)

    items_seen: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    items_new: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: Whether an operator triggered this run rather than the scheduler.
    triggered_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )

    source: Mapped[Source] = relationship(back_populates="runs")

    __table_args__ = (
        # The run history panel: this source's runs, newest first.
        Index("ix_source_run_source_started", "source_id", "started_at"),
    )


class Signal(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Anything collected, from any source (SPEC §3, §5.2)."""

    __tablename__ = "signal"

    source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("source.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(
        String(24), nullable=False, default=SignalKind.NEWS, server_default="news", index=True
    )

    #: The source's own identifier — an RSS <guid>, a CVE id, a release tag.
    external_id: Mapped[str] = mapped_column(String(500), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    author: Mapped[str | None] = mapped_column(String(300), nullable=True)

    published_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    collected_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"), index=True
    )

    #: SHA-256 over normalised title + url + summary. Nullable so a signal with
    #: nothing hashable does not collide with every other such signal — in
    #: Postgres, NULLs never conflict in a unique index.
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    raw: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    severity_hint: Mapped[str | None] = mapped_column(String(16), nullable=True)
    language: Mapped[str | None] = mapped_column(String(12), nullable=True)

    #: Generated by Postgres, never written by the application. Weighted so a
    #: term in the title outranks the same term buried in the body
    #: (DECISIONS.md D-011: Postgres FTS, no second datastore).
    search_vector: Mapped[str | None] = mapped_column(
        TSVECTOR,
        Computed(
            "setweight(to_tsvector('english', coalesce(title, '')), 'A') || "
            "setweight(to_tsvector('english', coalesce(summary, '')), 'B') || "
            "setweight(to_tsvector('english', coalesce(content, '')), 'C')",
            persisted=True,
        ),
        nullable=True,
    )

    tags: Mapped[list[SignalTag]] = relationship(
        back_populates="signal", cascade="all, delete-orphan"
    )

    __table_args__ = (
        # Re-serving the same entry on the next poll — the common case.
        UniqueConstraint("source_id", "external_id", name="uq_signal_source_external"),
        # The same story from two different sources (SPEC §5.2).
        Index("uq_signal_content_hash", "content_hash", unique=True),
        # Full-text search (SPEC §9.2 signal explorer).
        Index("ix_signal_search", "search_vector", postgresql_using="gin"),
        # The explorer's default view: newest first, optionally by source.
        Index("ix_signal_source_published", "source_id", "published_at"),
    )


class SignalTag(TimestampMixin, Base):
    """A label on a signal, applied by an operator or by a rule action."""

    __tablename__ = "signal_tag"

    signal_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("signal.id", ondelete="CASCADE"), primary_key=True
    )
    tag: Mapped[str] = mapped_column(String(64), primary_key=True)

    signal: Mapped[Signal] = relationship(back_populates="tags")

    __table_args__ = (
        # "Show me everything tagged X" scans by tag, not by signal.
        Index("ix_signal_tag_tag", "tag"),
    )


__all__ = [
    "Signal",
    "SignalTag",
    "Source",
    "SourceCategory",
    "SourceRun",
    "SourceType",
]
