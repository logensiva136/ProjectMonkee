"""Prometheus metrics (SPEC §10).

Metric objects are defined at import time so they appear in `/metrics` with a
zero value before the first event — a counter that only materialises after its
first increment cannot be alerted on, because `rate()` over a missing series is
missing rather than zero.

Note on scaling: these live in the default in-process registry, which assumes one
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
