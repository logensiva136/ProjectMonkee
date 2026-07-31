"""Turning a `RawItem` into the fields a `signal` row needs (SPEC §3 NORMALIZE).

Isolated from the pipeline that persists rows so it can be unit tested with
plain data — no database, no adapter, no network.
"""

from __future__ import annotations

import hashlib
import re

from app.collectors.base import RawItem

_WHITESPACE = re.compile(r"\s+")


def _normalize_text(value: str | None) -> str:
    """Collapse whitespace and case, so trivial formatting differences between
    two copies of the same story do not produce different hashes."""
    if not value:
        return ""
    return _WHITESPACE.sub(" ", value).strip().lower()


def compute_content_hash(item: RawItem) -> str | None:
    """SHA-256 over normalised title + URL, for cross-source dedupe.

    This catches **literal** republication — the same wire story or advisory
    mirrored by several outlets with an unchanged title and link — which is the
    common case among the source types Phase 2 ships. It is not fuzzy or
    semantic matching: two outlets that paraphrase the same event produce
    different hashes and both are kept. That is a deliberate scope line, not an
    oversight — near-duplicate detection is a different, much harder problem.

    Returns `None` when there is nothing stable to hash (no title and no URL),
    so the row gets no cross-source dedupe rather than colliding with every
    other title-less, url-less item — the unique index treats NULL as
    "no constraint", never as a match.
    """
    title = _normalize_text(item.title)
    url = _normalize_text(item.url)

    if not title and not url:
        return None

    digest = hashlib.sha256(f"{title}|{url}".encode()).hexdigest()
    return digest
