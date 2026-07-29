"""Prometheus metrics (SPEC §10).

Declaring a metric at import time registers its *family*, so `/metrics` carries
the HELP and TYPE lines immediately. It does **not** create any sample: a
labelled collector cannot know its label values in advance, so each series
appears only once that label combination is first observed.

That matters, because `rate()` over a series that does not exist yet is missing
rather than zero — so an alert on it silently never fires. Where the label values
are a known, finite set, `_prime()` at the bottom of this module instantiates
them up front so they read zero from boot. Where they are open-ended
(`source_type`, task names), priming is impossible and alerts must be written to
tolerate absence, e.g. `rate(...) or vector(0)`.

Note on scaling: these live in a single in-process registry, which assumes one
uvicorn worker per container. That is how `docker-compose.yml` runs the api. If
the api is ever scaled to multiple workers *inside* one container, switch to
`prometheus_client.multiprocess`.
"""

from __future__ import annotations

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, Info

from app import __version__

REGISTRY = CollectorRegistry(auto_describe=True)

BUILD_INFO = Info("hayabusa_build", "Build metadata", registry=REGISTRY)
BUILD_INFO.info({"version": __version__})

# --------------------------------------------------------------------- HTTP --

HTTP_REQUESTS = Counter(
    "hayabusa_http_requests_total",
    "HTTP requests handled by the API",
    labelnames=("method", "route", "status"),
    registry=REGISTRY,
)

HTTP_REQUEST_DURATION = Histogram(
    "hayabusa_http_request_duration_seconds",
    "HTTP request latency",
    labelnames=("method", "route"),
    # Bucketed around the SPEC §10 targets: dashboard < 500 ms, lists < 300 ms.
    buckets=(0.01, 0.025, 0.05, 0.1, 0.2, 0.3, 0.5, 1.0, 2.5, 5.0, 10.0),
    registry=REGISTRY,
)

# --------------------------------------------------------------- collection --

COLLECTION_RUNS = Counter(
    "hayabusa_collection_runs_total",
    "Source collection runs",
    labelnames=("source_type", "status"),
    registry=REGISTRY,
)

SIGNALS_INGESTED = Counter(
    "hayabusa_signals_ingested_total",
    "Signals written to the pipeline, after dedupe",
    labelnames=("kind", "source_type"),
    registry=REGISTRY,
)

SOURCE_HEALTH = Gauge(
    "hayabusa_source_health",
    "Number of sources in each health state",
    labelnames=("health",),
    registry=REGISTRY,
)

# -------------------------------------------------------- alerts & delivery --

ALERTS_CREATED = Counter(
    "hayabusa_alerts_created_total",
    "Alerts created by the rule engine",
    labelnames=("severity", "domain"),
    registry=REGISTRY,
)

DELIVERIES = Counter(
    "hayabusa_deliveries_total",
    "Notification delivery attempts by terminal status",
    labelnames=("status",),
    registry=REGISTRY,
)

# -------------------------------------------------------------------- tasks --

TASK_DURATION = Histogram(
    "hayabusa_task_duration_seconds",
    "Celery task execution time",
    labelnames=("task", "status"),
    buckets=(0.05, 0.1, 0.5, 1.0, 5.0, 15.0, 30.0, 60.0, 300.0, 900.0),
    registry=REGISTRY,
)

TASK_RUNS = Counter(
    "hayabusa_task_runs_total",
    "Celery task executions",
    labelnames=("task", "status"),
    registry=REGISTRY,
)

# ------------------------------------------------------------------ priming --

# Label values that form a closed set, mirroring the enums in SPEC §5.2 and §5.8.
SOURCE_HEALTH_STATES = ("healthy", "degraded", "failing")
DELIVERY_STATUSES = ("queued", "sending", "sent", "failed", "suppressed")


def _prime() -> None:
    """Materialise the series an operator is expected to alert on.

    Without this, `hayabusa_deliveries_total{status="failed"}` does not exist
    until the first delivery actually fails — so an alert watching for it would
    stay silent through the entire period where nothing has failed yet, and
    would look identical to a healthy system with a broken exporter.
    """
    for state in SOURCE_HEALTH_STATES:
        SOURCE_HEALTH.labels(state).set(0)
    for status in DELIVERY_STATUSES:
        DELIVERIES.labels(status)


_prime()
