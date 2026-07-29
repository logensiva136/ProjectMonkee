"""Source adapters (SPEC §3, §8).

Every intel source, regardless of format, becomes a `signal` row through the
same pipeline: **collect** (this package) -> normalize -> enrich -> correlate ->
evaluate -> deliver. A source adapter is a class implementing
`async def fetch(self) -> AdapterResult`, registered against a `source.type`
value. Adding a new intel source is writing one adapter class and registering
it — nothing else in the pipeline changes.

All network access goes through `app.core.ssrf.safe_fetch`. An adapter must
never call `httpx` directly: the URL it is fetching came from an operator typing
it into a form, and SPEC §10 requires every such URL be SSRF-guarded.
"""

from app.collectors.base import (
    AdapterResult,
    RawItem,
    SourceAdapter,
    get_adapter,
    register_adapter,
    registered_types,
)

# Importing each adapter module registers it via the @register_adapter
# decorator. This is the only file that needs to change (plus the SourceType
# enum) to teach the pipeline about a new adapter.
from app.collectors import feed as _feed  # noqa: F401,E402
from app.collectors import json_feed as _json_feed  # noqa: F401,E402

__all__ = [
    "AdapterResult",
    "RawItem",
    "SourceAdapter",
    "get_adapter",
    "register_adapter",
    "registered_types",
]
