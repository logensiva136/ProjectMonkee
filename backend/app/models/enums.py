"""Enumerations shared by the models and the API schemas.

These are `StrEnum`, and the columns that hold them are plain `VARCHAR` rather
than native Postgres enum types. That is deliberate: Postgres enums require an
`ALTER TYPE ... ADD VALUE` migration to gain a member, which cannot run inside a
transaction block — so every new source type in a later phase would need a
bespoke, non-transactional migration. A varchar plus validation in Pydantic gives
the same guarantees at the edge, where bad input actually arrives, and adding a
member becomes a code change.

`StrEnum` members compare equal to their string value, so `source.type == "rss"`
works without conversion, and they serialise to JSON as plain strings.
"""

from __future__ import annotations

from enum import StrEnum


class SourceType(StrEnum):
    """Adapter selector (SPEC §5.2).

    Adding a member here and registering an adapter for it is the whole of
    "add a new intel source" (SPEC §3).
    """

    RSS = "rss"
    ATOM = "atom"
    JSON_FEED = "json_feed"
    HTML_ADVISORY = "html_advisory"
    NVD = "nvd"
    CISA_KEV = "cisa_kev"
    EPSS = "epss"
    OSV = "osv"
    GITHUB_RELEASES = "github_releases"
    GITHUB_ADVISORY = "github_advisory"
    ENDOFLIFE = "endoflife"
    CRTSH = "crtsh"
    CUSTOM_WEBHOOK = "custom_webhook"


class SignalKind(StrEnum):
    """Discriminator on the `signal` table (SPEC §3)."""

    NEWS = "news"
    ADVISORY = "advisory"
    CVE = "cve"
    PACKAGE_EVENT = "package_event"
    EASM_CHANGE = "easm_change"


class SourceHealth(StrEnum):
    """Rolling health, derived from consecutive failures (SPEC §5.2, §8)."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    FAILING = "failing"


class RunStatus(StrEnum):
    """Outcome of one collection run."""

    RUNNING = "running"
    SUCCESS = "success"
    #: Fetched successfully but the server said nothing changed (HTTP 304).
    NOT_MODIFIED = "not_modified"
    FAILED = "failed"
    #: Another worker held the source lock, so this run did not proceed.
    SKIPPED = "skipped"


class Severity(StrEnum):
    """Shared severity ladder, matching the SPEC §9.1 colour tokens."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"
