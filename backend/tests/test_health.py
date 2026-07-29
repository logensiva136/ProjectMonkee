"""Probe endpoints and the cross-cutting HTTP behaviour they exercise."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.core.middleware import REQUEST_ID_HEADER


class TestHealth:
    async def test_reports_ok_without_touching_dependencies(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/health")

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert body["environment"] == "test"
        assert body["version"]

    async def test_is_also_served_unprefixed_for_container_probes(
        self, client: AsyncClient
    ) -> None:
        assert (await client.get("/health")).status_code == 200

    async def test_unprefixed_alias_is_absent_from_the_openapi_schema(
        self, client: AsyncClient
    ) -> None:
        # The frontend generates its types from this document (SPEC §9.0 Rule 0),
        # so the duplicate probe routes must not appear in it.
        paths = (await client.get("/api/v1/openapi.json")).json()["paths"]

        assert "/api/v1/health" in paths
        assert "/health" not in paths


class TestReady:
    async def test_returns_503_and_names_the_failing_dependency(
        self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def _down() -> bool:
            return False

        monkeypatch.setattr("app.api.v1.health.ping_db", _down)
        monkeypatch.setattr("app.api.v1.health.ping_redis", _down)

        response = await client.get("/api/v1/ready")

        assert response.status_code == 503
        body = response.json()
        assert body["status"] == "degraded"
        assert {check["name"] for check in body["checks"]} == {"database", "redis"}
        assert all(check["ok"] is False for check in body["checks"])

    async def test_reports_ready_when_both_dependencies_answer(
        self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def _up() -> bool:
            return True

        async def _no_heartbeat() -> None:
            return None

        async def _version() -> str:
            return "16.4"

        monkeypatch.setattr("app.api.v1.health.ping_db", _up)
        monkeypatch.setattr("app.api.v1.health.ping_redis", _up)
        monkeypatch.setattr("app.api.v1.health._read_heartbeat", _no_heartbeat)
        monkeypatch.setattr("app.api.v1.health.db_server_version", _version)

        response = await client.get("/api/v1/ready")

        assert response.status_code == 200
        assert response.json()["status"] == "ready"
        assert response.json()["database_version"] == "16.4"


class TestMetrics:
    async def test_exposes_the_declared_metric_families(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/metrics")

        assert response.status_code == 200
        assert "text/plain" in response.headers["content-type"]
        body = response.text
        # SPEC §10 names these explicitly. They must exist before their first
        # event, or `rate()` over them is undefined rather than zero.
        for metric in (
            "hayabusa_collection_runs_total",
            "hayabusa_signals_ingested_total",
            "hayabusa_alerts_created_total",
            "hayabusa_deliveries_total",
            "hayabusa_source_health",
            "hayabusa_task_duration_seconds",
        ):
            assert metric in body, f"{metric} missing from /metrics"

    async def test_records_http_request_latency(self, client: AsyncClient) -> None:
        await client.get("/api/v1/health")

        body = (await client.get("/api/v1/metrics")).text

        assert "hayabusa_http_request_duration_seconds" in body
        # Labelled by route template, not by raw path, to bound cardinality.
        assert 'route="/api/v1/health"' in body


class TestRequestCorrelation:
    async def test_generates_a_request_id_when_none_is_supplied(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/health")

        assert response.headers.get(REQUEST_ID_HEADER)

    async def test_propagates_an_inbound_request_id(self, client: AsyncClient) -> None:
        response = await client.get(
            "/api/v1/health", headers={REQUEST_ID_HEADER: "trace-from-nginx"}
        )

        assert response.headers[REQUEST_ID_HEADER] == "trace-from-nginx"

    async def test_rejects_an_oversized_inbound_id(self, client: AsyncClient) -> None:
        # An unbounded header echoed into logs is a log-injection vector.
        response = await client.get("/api/v1/health", headers={REQUEST_ID_HEADER: "x" * 200})

        assert response.headers[REQUEST_ID_HEADER] != "x" * 200


class TestErrorEnvelope:
    async def test_unknown_route_returns_problem_json(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/does-not-exist")

        assert response.status_code == 404
        assert response.headers["content-type"].startswith("application/problem+json")
        body = response.json()
        assert body["status"] == 404
        assert body["title"] == "Not Found"
        assert body["instance"] == "/api/v1/does-not-exist"
        assert body["request_id"]

    async def test_security_headers_are_applied(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/health")

        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["X-Frame-Options"] == "DENY"
