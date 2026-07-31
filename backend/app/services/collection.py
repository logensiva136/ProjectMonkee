"""The collection pipeline: fetch a source, persist what's new, record the run
(SPEC §3 COLLECT, §8 circuit breaking).

`run_collection` is the one function every entry point calls — the scheduled
`collect_source` task, the operator's "poll now" button, and the "test source"
preview all go through it, so health, backoff and accounting stay consistent
regardless of what triggered the run.

Concurrency note: this function assumes its caller already holds the per-source
Redis lock described in SPEC §8. It does not take the lock itself, so it can be
unit tested without Redis — locking is an orchestration concern, handled by the
Celery task in `app.tasks.collect`.
"""

from __future__ import annotations

import datetime as dt
import time
import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.collectors import get_adapter
from app.collectors.base import AdapterResult, RawItem, UnknownSourceTypeError
from app.core.logging import get_logger
from app.core.metrics import COLLECTION_RUNS, SIGNALS_INGESTED, SOURCE_HEALTH
from app.core.ssrf import FetchTooLargeError, SSRFBlockedError
from app.models.base import utcnow
from app.models.collection import Signal, Source, SourceRun
from app.models.enums import RunStatus, SignalKind, SourceHealth
from app.services.normalize import compute_content_hash

log = get_logger(__name__)

# SPEC §8: after 5 consecutive failures a source is "failing" and its interval
# backs off exponentially to a ceiling of 24h. 1-4 failures is "degraded" —
# worth showing an operator, not yet worth treating as broken.
FAILING_THRESHOLD = 5
MAX_BACKOFF_SECONDS = 24 * 60 * 60


@dataclass
class CollectionOutcome:
    run: SourceRun
    items_seen: int
    items_new: int


def _health_for(consecutive_failures: int) -> str:
    if consecutive_failures == 0:
        return SourceHealth.HEALTHY
    if consecutive_failures < FAILING_THRESHOLD:
        return SourceHealth.DEGRADED
    return SourceHealth.FAILING


def _next_poll_delay_seconds(source: Source, *, failed: bool) -> int:
    """Backoff schedule (SPEC §8): normal interval on success, exponential
    on failure, capped so a source that has been down for days is still
    re-tried at most once a day rather than never."""
    if not failed:
        return source.poll_interval_seconds

    # 2^1, 2^2, ... — the failure that just happened is already reflected in
    # consecutive_failures by the time this is called.
    exponent = min(source.consecutive_failures, 10)  # cap the exponent, not just the result
    multiplier = int(2**exponent)
    return min(source.poll_interval_seconds * multiplier, MAX_BACKOFF_SECONDS)


def _signal_kind_for(source: Source) -> str:
    """Which `signal.kind` a source's items become.

    Defaults to `news`; a source can override it via `config.signal_kind` (an
    operator setting up a vendor PSIRT feed sets this to `advisory`, for
    example) — validated against the enum so a typo in the config JSON fails
    loudly at collection time rather than writing an unrecognised kind.
    """
    configured = source.config.get("signal_kind") if source.config else None
    if configured:
        try:
            return str(SignalKind(configured))
        except ValueError:
            log.warning(
                "invalid_signal_kind_config",
                source_id=str(source.id),
                configured=configured,
            )
    return SignalKind.NEWS


async def _persist_item(
    session: AsyncSession, source: Source, item: RawItem
) -> bool:
    """Insert one item as a `signal` row. Returns True if it was new.

    Both dedupe keys are real unique constraints, not pre-checks, because a
    pre-check-then-insert has a race: two overlapping runs (a manual "poll now"
    racing the scheduler) could both pass the check and then both insert. A
    savepoint around each insert lets the database be the single source of
    truth for "does this already exist" — a race becomes a caught
    `IntegrityError` instead of a crashed task or a duplicate row.
    """
    content_hash = compute_content_hash(item)

    signal = Signal(
        source_id=source.id,
        kind=_signal_kind_for(source),
        external_id=item.external_id,
        title=item.title,
        url=item.url,
        summary=item.summary,
        content=item.content,
        author=item.author,
        published_at=item.published_at,
        content_hash=content_hash,
        raw=item.raw,
        severity_hint=source.default_severity,
        collected_at=utcnow(),
    )

    try:
        async with session.begin_nested():
            session.add(signal)
            await session.flush()
    except IntegrityError:
        # Expected and frequent: the common case on every poll after the first
        # is "everything already exists". Not logged per-item — it would drown
        # the run summary in noise for a healthy, quiet feed.
        return False

    return True


async def run_collection(
    session: AsyncSession,
    source: Source,
    *,
    triggered_by: uuid.UUID | None = None,
) -> CollectionOutcome:
    """Fetch `source`, persist new items, and record a `source_run`.

    Commits internally at well-defined points (see inline notes) rather than
    leaving everything to the caller's transaction, so a crash partway through
    a large feed does not roll back items that were already durably new.
    """
    run = SourceRun(source_id=source.id, status=RunStatus.RUNNING, triggered_by=triggered_by)
    session.add(run)
    await session.flush()
    # The run row is visible to `GET /sources/{id}/runs` as "in progress" for
    # the duration of a slow fetch, which is the honest state of the world.
    await session.commit()

    started = time.perf_counter()
    outcome_status = RunStatus.FAILED
    error_message: str | None = None
    http_status: int | None = None
    result: AdapterResult | None = None

    try:
        adapter = get_adapter(source)
        result = await adapter.fetch()
        http_status = result.http_status
        outcome_status = RunStatus.NOT_MODIFIED if result.not_modified else RunStatus.SUCCESS
    except UnknownSourceTypeError as exc:
        error_message = str(exc)
    except SSRFBlockedError as exc:
        error_message = f"blocked target: {exc.reason}"
    except FetchTooLargeError as exc:
        error_message = str(exc)
    except Exception as exc:
        error_message = f"{type(exc).__name__}: {exc}"
        log.error(
            "collection_failed",
            source_id=str(source.id),
            source_type=source.type,
            error=error_message,
            exc_info=exc,
        )

    items_seen = len(result.items) if result else 0
    items_new = 0

    if result is not None and not result.not_modified:
        for item in result.items:
            if await _persist_item(session, source, item):
                items_new += 1
        await session.commit()

    failed = error_message is not None
    duration_ms = round((time.perf_counter() - started) * 1000)

    # --- update the source: health, backoff, conditional-GET state ---
    source.last_polled_at = utcnow()
    source.last_status = outcome_status
    source.last_error = error_message

    if failed:
        source.consecutive_failures += 1
    else:
        source.consecutive_failures = 0
        if result is not None:
            # `None` from the adapter means "unchanged, keep what's stored" —
            # true on a 304, and also true for adapters that do not use
            # conditional GET at all.
            if result.etag is not None:
                source.etag = result.etag
            if result.last_modified is not None:
                source.last_modified = result.last_modified

    source.health = _health_for(source.consecutive_failures)
    source.next_poll_at = utcnow() + dt.timedelta(
        seconds=_next_poll_delay_seconds(source, failed=failed)
    )

    if source.consecutive_failures == FAILING_THRESHOLD:
        # Edge-triggered: fires once on the transition into "failing", not on
        # every failed run after it — an operator does not need the same
        # warning every three hours for a feed that has been down all week.
        #
        # This becomes a real `alert` row once the rule engine exists (Phase
        # 3); for now it is a structured log line an operator's log pipeline
        # can already alert on.
        log.warning(
            "source_circuit_open",
            source_id=str(source.id),
            source_name=source.name,
            consecutive_failures=source.consecutive_failures,
        )

    # --- finish the run row ---
    run.status = outcome_status
    run.http_status = http_status
    run.items_seen = items_seen
    run.items_new = items_new
    run.duration_ms = duration_ms
    run.error = error_message
    run.finished_at = utcnow()

    await session.commit()

    COLLECTION_RUNS.labels(source.type, outcome_status).inc()
    if items_new:
        SIGNALS_INGESTED.labels(_signal_kind_for(source), source.type).inc(items_new)
    await _refresh_source_health_gauge(session)

    log.info(
        "collection_run_finished",
        source_id=str(source.id),
        status=outcome_status,
        items_seen=items_seen,
        items_new=items_new,
        duration_ms=duration_ms,
        health=source.health,
    )

    return CollectionOutcome(run=run, items_seen=items_seen, items_new=items_new)


async def _refresh_source_health_gauge(session: AsyncSession) -> None:
    """Recompute the `hayabusa_source_health` gauge from the database.

    A gauge set relative to its previous value (increment here, decrement
    there) drifts the moment any code path updates `source.health` without
    going through this module — a direct SQL fix during an incident, for
    instance. Recomputing from source-of-truth on every run costs one grouped
    COUNT and cannot drift.
    """
    result = await session.execute(
        select(Source.health, func.count())
        .where(Source.deleted_at.is_(None))
        .group_by(Source.health)
    )
    rows = result.all()
    counts: dict[str, int] = {row[0]: row[1] for row in rows}
    for state in (SourceHealth.HEALTHY, SourceHealth.DEGRADED, SourceHealth.FAILING):
        SOURCE_HEALTH.labels(state).set(counts.get(state, 0))
