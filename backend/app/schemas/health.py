"""Response models for the liveness and readiness probes (SPEC §10)."""

from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Liveness: the process is up and serving. Deliberately checks nothing else.

    A liveness probe that touched the database would make an orchestrator restart
    a perfectly healthy API during a brief DB blip — which is exactly when
    restarting helps least.
    """

    status: Literal["ok"] = "ok"
    app: str = Field(examples=["HAYABUSA"])
    version: str = Field(examples=["0.1.0"])
    environment: str = Field(examples=["development"])
    time: dt.datetime


class DependencyCheck(BaseModel):
    name: str
    ok: bool
    latency_ms: float | None = None
    detail: str | None = None


class HeartbeatInfo(BaseModel):
    """Last run of the scheduled `heartbeat` task (SPEC §12 Phase 0).

    `age_seconds` growing past roughly twice the 30 s schedule means beat or the
    worker has stopped, and therefore that collection has stopped.
    """

    at: dt.datetime
    count: int
    worker: str
    age_seconds: float
    stale: bool


class ReadyResponse(BaseModel):
    """Readiness: every dependency needed to serve traffic is reachable."""

    status: Literal["ready", "degraded"]
    checks: list[DependencyCheck]
    heartbeat: HeartbeatInfo | None = None
    database_version: str | None = None
