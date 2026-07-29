"""RSS and Atom (SPEC §5.2).

Both formats parse through the same library — `feedparser` normalises RSS 0.9x
through 2.0 and Atom 0.3/1.0 into one entry shape — so one adapter class handles
both, registered for both `source.type` values.

`feedparser.parse()` is a synchronous, CPU-bound call (XML parsing plus its own
date/encoding normalisation). It runs in a worker thread via `asyncio.to_thread`
so a large or slow-to-parse feed does not block the event loop that every other
concurrent collection is sharing.

Critically, `feedparser` is given raw bytes we already fetched — never a URL.
Handing it a URL would make it perform its own HTTP request, outside
`safe_fetch`, which is exactly the SSRF hole SPEC §10 exists to close.
"""

from __future__ import annotations

import asyncio
import calendar
import datetime as dt
import hashlib
import time
from typing import Any

import feedparser

from app.collectors.base import AdapterResult, RawItem, SourceAdapter, register_adapter
from app.core.logging import get_logger
from app.core.ssrf import FetchTooLargeError, SSRFBlockedError, safe_fetch
from app.models.enums import SourceType

log = get_logger(__name__)


def _struct_time_to_utc(value: time.struct_time | None) -> dt.datetime | None:
    """feedparser normalises every date format it understands to UTC already;
    `calendar.timegm` (not `time.mktime`) is what respects that — `mktime`
    would reinterpret the struct as local time and shift it."""
    if value is None:
        return None
    return dt.datetime.fromtimestamp(calendar.timegm(value), tz=dt.UTC)


def _external_id(entry: Any, index: int) -> str:
    """A stable id even for a feed whose entries have none.

    Preference order: guid/id (the format's own stable identifier) -> link (
    usually stable, occasionally not for feeds that rewrite tracking params) ->
    a hash of title+index (last resort, means edits to that entry look like a
    new one — acceptable only because nothing better exists).
    """
    guid = entry.get("id") or entry.get("guid")
    if guid:
        return str(guid)

    link = entry.get("link")
    if link:
        return str(link)

    fallback = f"{entry.get('title', '')}:{index}"
    return hashlib.sha256(fallback.encode("utf-8")).hexdigest()


def _extract_content(entry: Any) -> str | None:
    content_list = entry.get("content")
    if content_list:
        # Atom entries may carry several representations (text, html, xhtml);
        # the first is what feedparser and most readers treat as canonical.
        first = content_list[0]
        value = first.get("value")
        if value:
            return str(value)
    return None


def parse_feed_bytes(data: bytes) -> list[RawItem]:
    """Pure parsing, no I/O — the part covered directly by unit tests."""
    parsed = feedparser.parse(data)

    if parsed.bozo and not parsed.entries:
        # `bozo` alone is not fatal — many perfectly-usable feeds set it for a
        # minor spec violation. Zero entries alongside it means parsing
        # actually failed to extract anything.
        exc = parsed.get("bozo_exception")
        raise ValueError(f"Feed did not parse: {exc}")

    items: list[RawItem] = []
    for index, entry in enumerate(parsed.entries):
        title = str(entry.get("title") or "(untitled)").strip()
        published = _struct_time_to_utc(
            entry.get("published_parsed") or entry.get("updated_parsed")
        )

        items.append(
            RawItem(
                external_id=_external_id(entry, index),
                title=title,
                url=entry.get("link"),
                summary=entry.get("summary"),
                content=_extract_content(entry),
                author=entry.get("author"),
                published_at=published,
                raw={
                    "tags": [t.get("term") for t in entry.get("tags", []) if t.get("term")],
                },
            )
        )
    return items


@register_adapter(SourceType.RSS, SourceType.ATOM)
class FeedAdapter(SourceAdapter):
    async def fetch(self) -> AdapterResult:
        headers: dict[str, str] = {}
        if self.source.etag:
            headers["If-None-Match"] = self.source.etag
        if self.source.last_modified:
            headers["If-Modified-Since"] = self.source.last_modified

        try:
            result = await safe_fetch(self.source.url, headers=headers)
        except (SSRFBlockedError, FetchTooLargeError):
            # Let these propagate with their specific type — the pipeline logs
            # and records them distinctly from a parse failure.
            raise

        if result.not_modified:
            return AdapterResult(items=[], http_status=304, not_modified=True)

        items = await asyncio.to_thread(parse_feed_bytes, result.body)

        log.info(
            "feed_parsed",
            source_id=str(self.source.id),
            url=self.source.url,
            items=len(items),
        )

        return AdapterResult(
            items=items,
            http_status=result.status_code,
            etag=result.headers.get("etag"),
            last_modified=result.headers.get("last-modified"),
        )
