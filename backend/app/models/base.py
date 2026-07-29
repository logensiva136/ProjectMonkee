"""Declarative base and the mixins every table in SPEC §5 is built from.

SPEC §5 requires UUIDv7 primary keys, `created_at`/`updated_at` everywhere, and
`deleted_at` on records referenced historically. Rather than repeat those columns
about sixty times, they live here as mixins.

Why UUIDv7: it is time-ordered, so rows insert at the right-hand edge of the
B-tree instead of scattering across it the way UUIDv4 does — which keeps index
writes cheap at the volumes SPEC §10 targets — and an ID sorts chronologically
without a join. Postgres 16 has no native `uuidv7()`, so IDs are generated in
Python (see DECISIONS.md D-003).
"""

from __future__ import annotations

import datetime as dt
import re
import uuid
from typing import Any, ClassVar

from sqlalchemy import DateTime, MetaData, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column
from uuid6 import uuid7

# Deterministic constraint names. Without these, Postgres invents names for
# indexes and constraints, and Alembic autogenerate then produces spurious
# drop/create pairs because the name it computes never matches the live one.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

_CAMEL_BOUNDARY = re.compile(r"(?<!^)(?=[A-Z])")


class Base(DeclarativeBase):
    """Root of every ORM model."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)

    # Maps Python annotations to column types, so models can write
    # `Mapped[dict[str, Any]]` and get JSONB without repeating the type.
    type_annotation_map: ClassVar[dict[Any, Any]] = {
        dict[str, Any]: JSONB,
        list[str]: JSONB,
        uuid.UUID: UUID(as_uuid=True),
        dt.datetime: DateTime(timezone=True),
    }

    @declared_attr.directive
    def __tablename__(cls) -> str:  # noqa: N805
        """Default table name: `VendorKeyword` -> `vendor_keyword`.

        SPEC §5 names tables in singular snake_case. Models may override; a few
        must, because `user` collides with a Postgres reserved word (SQLAlchemy
        quotes it, but the explicit declaration documents the intent).
        """
        return _CAMEL_BOUNDARY.sub("_", cls.__name__).lower()

    def __repr__(self) -> str:
        identifier = getattr(self, "id", None)
        return f"<{type(self).__name__} {identifier}>"


class UUIDPrimaryKeyMixin:
    """Time-ordered UUIDv7 primary key, generated client-side."""

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid7,
        sort_order=-100,  # keep `id` the first column in CREATE TABLE
    )


class TimestampMixin:
    """`created_at` / `updated_at`, maintained by the database clock.

    `server_default`/`onupdate` use the *database* clock rather than the
    application's, so rows written by different processes — API, worker, a manual
    psql fix — remain comparable.
    """

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        sort_order=100,
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        sort_order=101,
    )


class SoftDeleteMixin:
    """`deleted_at` for records other rows point at historically.

    Deleting a vendor must not orphan the `vendor_match` rows that explain why an
    alert fired last month, so those tables mark instead of delete. Queries must
    filter `deleted_at IS NULL` explicitly — there is deliberately no global
    filter, because a hidden one makes "why is this row missing" very hard to
    debug.
    """

    deleted_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
        sort_order=102,
    )

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None


def utcnow() -> dt.datetime:
    """Timezone-aware UTC now.

    `datetime.utcnow()` returns a *naive* datetime, which compares wrongly
    against the `timestamptz` columns SPEC §5 mandates. Always use this.
    """
    return dt.datetime.now(dt.UTC)
