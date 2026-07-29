"""JSON Feed (SPEC §5.2) — https://www.jsonfeed.org/version/1.1/.

A JSON Feed is just a document; parsing it is `json.loads` plus a bit of shape
tolerance between the 1.0 and 1.1 versions of the spec (singular `author` in
1.0 became a list, `authors`, in 1.1). No library dependency needed, unlike RSS
and Atom's much messier real-world XML.
"""

from __future__ import annotations

import datetime as dt
import json
from typing import Any

from app.collectors.base import AdapterResult, RawItem, SourceAdapter, register_adapter
from app.core.logging import get_logger
from app.core.ssrf import safe_fetch
from app.models.enums import SourceType

log = get_logger(__name__)


def _parse_date(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    try:
        # `fromisoformat` accepts the trailing "Z" JSON Feed dates use as of
        # Python 3.11; a naive result is impossible here since the spec
        # requires an explicit offset or "Z".
        return dt.datetime.fromisoformat(value)
    except ValueError:
        log.warning("json_feed_unparseable_date", value=value)
        return None


def _author_name(item: dict[str, Any], feed: dict[str, Any]) -> str | None:
    # 1.1: item.authors[]; 1.0: item.author; falls back to the feed-level author
    # when an item does not name its own.
    authors = item.get("authors") or feed.get("authors")
    if authors:
        name = authors[0].get("name")
        if name:
            return str(name)

    author = item.get("author") or feed.get("author")
    if author and author.get("name"):
        return str(author["name"])
    return None


def parse_json_feed_bytes(data: bytes) -> list[RawItem]:
    """Pure parsing, no I/O."""
    document = json.loads(data)

    if "items" not in document:
        raise ValueError("Not a JSON Feed document: no top-level 'items' array")

    items: list[RawItem] = []
    for index, item in enumerate(document["items"]):
        # The spec requires `id`, but real-world feeds are not always
        # compliant; fall back the same way the RSS/Atom adapter does.
        external_id = str(item.get("id") or item.get("url") or f"item-{index}")

        items.append(
            RawItem(
                external_id=external_id,
                title=str(item.get("title") or "(untitled)").strip(),
                url=item.get("url") or item.get("external_url"),
                summary=item.get("summary"),
                content=item.get("content_text") or item.get("content_html"),
                author=_author_name(item, document),
                published_at=_parse_date(item.get("date_published")),
                raw={"tags": item.get("tags", [])},
            )
        )
    return items


@register_adapter(SourceType.JSON_FEED)
class JsonFeedAdapter(SourceAdapter):
    async def fetch(self) -> AdapterResult:
        headers: dict[str, str] = {}
        if self.source.etag:
            headers["If-None-Match"] = self.source.etag
        if self.source.last_modified:
            headers["If-Modified-Since"] = self.source.last_modified

        result = await safe_fetch(self.source.url, headers=headers)

        if result.not_modified:
            return AdapterResult(items=[], http_status=304, not_modified=True)

        try:
            items = parse_json_feed_bytes(result.body)
        except (json.JSONDecodeError, ValueError) as exc:
            raise ValueError(f"Could not parse JSON Feed: {exc}") from exc

        log.info(
            "json_feed_parsed", source_id=str(self.source.id), url=self.source.url, items=len(items)
        )

        return AdapterResult(
            items=items,
            http_status=result.status_code,
            etag=result.headers.get("etag"),
            last_modified=result.headers.get("last-modified"),
        )
