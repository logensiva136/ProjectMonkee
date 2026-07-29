"""The first-run gate (SPEC §6.1).

Until onboarding completes, everything except `/setup/*` and the probes must
answer 409 — including routes that do not exist, because the gate runs as
middleware ahead of routing.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.core.setup_gate import path_is_exempt


class TestGateClosed:
    @pytest.mark.parametrize(
        "path",
        ["/api/v1/me", "/api/v1/users", "/api/v1/does-not-exist"],
    )
    async def test_blocks_ordinary_routes_with_409(self, client: AsyncClient, path: str) -> None:
        response = await client.get(path)

        assert response.status_code == 409
        body = response.json()
        assert body["title"] == "Setup Required"
        assert body["type"].endswith("/setup-required")

    @pytest.mark.parametrize("path", ["/health", "/ready", "/api/v1/health", "/api/v1/metrics"])
    async def test_probes_stay_reachable(self, client: AsyncClient, path: str) -> None:
        # A container that cannot answer its healthcheck looks dead to the
        # orchestrator and gets restarted forever.
        assert (await client.get(path)).status_code in (200, 503)

    async def test_openapi_stays_reachable(self, client: AsyncClient) -> None:
        # The frontend generates its types from this document, so it must be
        # fetchable before the instance is onboarded.
        assert (await client.get("/api/v1/openapi.json")).status_code == 200


class TestGateOpen:
    async def test_allows_routes_through_once_onboarded(
        self, client: AsyncClient, onboarded: object
    ) -> None:
        response = await client.get("/api/v1/does-not-exist")

        assert response.status_code == 404  # routed normally, no longer gated

    async def test_protected_route_now_asks_for_authentication(
        self, client: AsyncClient, onboarded: object
    ) -> None:
        # Past the gate, /me is reachable but still demands a token — the gate
        # and authentication are separate concerns.
        response = await client.get("/api/v1/me")

        assert response.status_code == 401


class TestExemptPaths:
    @pytest.mark.parametrize(
        "path",
        [
            "/health",
            "/ready",
            "/metrics",
            "/api/v1/health",
            "/api/docs",
            "/api/v1/openapi.json",
            "/api/v1/setup/status",
            "/api/v1/setup/complete",
        ],
    )
    def test_recognises_exempt_paths(self, path: str) -> None:
        assert path_is_exempt(path)

    @pytest.mark.parametrize("path", ["/api/v1/me", "/api/v1/users", "/", "/api/v1/setupx"])
    def test_everything_else_is_gated(self, path: str) -> None:
        assert not path_is_exempt(path)
