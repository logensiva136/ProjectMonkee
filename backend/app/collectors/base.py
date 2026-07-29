"""The adapter contract and registry (SPEC §3).

`fetch()` returns items and connection metadata; it never writes to the
database. Persisting — dedupe, `signal` rows, `source_run` accounting — is the
ingestion pipeline's job (`app.services.collection`), so an adapter can be unit
tested against fixture bytes with no database at all.
"""

from __future__ import annotations

import datetime as dt
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.models.collection import Source


@dataclass(frozen=True)
class RawItem:
    """One entry as an adapter parsed it, before it becomes a `signal` row.

    `external_id` is what the dedupe constraint `UNIQUE(source_id, external_id)`
    keys on, so an adapter must produce a stable one — the feed's own guid/id
    where the format has one, never a value derived from content that could
    legitimately change (a title gets corrected, a summary gets a typo fixed).
    """

    external_id: str
    title: str
    url: str | None = None
    summary: str | None = None
    content: str | None = None
    author: str | None = None
    published_at: dt.datetime | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AdapterResult:
    """What a collection attempt produced, for the pipeline to persist.

    `not_modified=True` means the server answered 304 to a conditional GET —
    correct behaviour, not a failure, and `items` is empty because there is
    nothing new to report.
    """

    items: list[RawItem]
    http_status: int | None = None
    #: New values to store on `source.etag` / `source.last_modified` for the
    #: next conditional GET. `None` means "unchanged, keep what's stored".
    etag: str | None = None
    last_modified: str | None = None
    not_modified: bool = False


class SourceAdapter(ABC):
    """Base class for every source type.

    Constructed fresh per collection run with the `Source` row it will fetch,
    so an adapter can read `self.source.config`, `.url`, `.etag` and so on
    without them being threaded through every method call.
    """

    def __init__(self, source: Source) -> None:
        self.source = source

    @abstractmethod
    async def fetch(self) -> AdapterResult:
        """Fetch and parse. Must route all network access through `safe_fetch`."""


_REGISTRY: dict[str, type[SourceAdapter]] = {}


def register_adapter(*source_types: str):  # type: ignore[no-untyped-def]
    """Class decorator: `@register_adapter(SourceType.RSS, SourceType.ATOM)`.

    Multiple types may share one adapter class — RSS and Atom both parse
    through `feedparser`, so `FeedAdapter` registers for both.
    """

    def decorator(cls: type[SourceAdapter]) -> type[SourceAdapter]:
        for source_type in source_types:
            _REGISTRY[str(source_type)] = cls
        return cls

    return decorator


class UnknownSourceTypeError(Exception):
    """No adapter is registered for this `source.type`."""


def get_adapter(source: Source) -> SourceAdapter:
    """Instantiate the adapter registered for `source.type`."""
    adapter_cls = _REGISTRY.get(source.type)
    if adapter_cls is None:
        raise UnknownSourceTypeError(
            f"No adapter registered for source type {source.type!r}. "
            f"Known types: {sorted(_REGISTRY)}"
        )
    return adapter_cls(source)


def registered_types() -> list[str]:
    """Every source type with a working adapter — for the /sources form."""
    return sorted(_REGISTRY)
