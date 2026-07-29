"""Permissions, panel visibility and the /me contract (SPEC §6.3).

The Phase 1 acceptance criterion lives here: *a Viewer role user cannot see or
call admin routes*. "Cannot see" is panel visibility; "cannot call" is the
backend refusing them. The second is the one that matters, and the tests below
check it independently of the first.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests.helpers import OTHER_PASSWORD, auth, create_user, onboard, sign_in

# Every admin route, with the method that reaches it. A Viewer must be refused
# all of them by the API itself.
ADMIN_ROUTES = [
    ("GET", "/api/v1/users"),
    ("POST", "/api/v1/users"),
    ("GET", "/api/v1/roles"),
    ("POST", "/api/v1/roles"),
    ("GET", "/api/v1/audit-logs"),
    ("PATCH", "/api/v1/settings"),
]


@pytest.fixture
async def admin_token(client: AsyncClient) -> str:
    result = await onboard(client, username="admin")
    return await sign_in(client, "admin", result["password"], result["totp_secret"])


@pytest.fixture
async def viewer_token(client: AsyncClient, admin_token: str) -> str:
    await create_user(client, admin_token, username="viewer", role_keys=["viewer"])
    return await sign_in(client, "viewer", OTHER_PASSWORD, totp_secret="")


class TestAcceptanceCriterion:
    """SPEC §12 Phase 1: a Viewer cannot see or call admin routes."""

    @pytest.mark.parametrize(("method", "path"), ADMIN_ROUTES)
    async def test_viewer_is_refused_every_admin_route(
        self, client: AsyncClient, viewer_token: str, method: str, path: str
    ) -> None:
        response = await client.request(method, path, headers=auth(viewer_token), json={})

        assert response.status_code == 403, f"{method} {path} should be forbidden for a Viewer"
        assert response.json()["title"] == "Forbidden"

    async def test_viewer_sees_only_the_dashboard_panel(
        self, client: AsyncClient, viewer_token: str
    ) -> None:
        me = (await client.get("/api/v1/me", headers=auth(viewer_token))).json()

        assert [panel["key"] for panel in me["panels"]] == ["dashboard"]

    async def test_admin_can_reach_the_same_routes(
        self, client: AsyncClient, admin_token: str
    ) -> None:
        for method, path in ADMIN_ROUTES:
            if method != "GET":
                continue
            response = await client.request(method, path, headers=auth(admin_token))
            assert response.status_code == 200, f"{method} {path} should be allowed for an admin"


class TestEnforcementIsIndependentOfTheUI:
    async def test_granting_a_panel_does_not_grant_the_permission(
        self, client: AsyncClient, admin_token: str, viewer_token: str
    ) -> None:
        """The point of SPEC §6.3: hiding a panel is UX, showing one is not access.

        Give the Viewer role the admin_users *panel* — the sidebar link — and it
        must still be refused the endpoint behind it.
        """
        roles = (await client.get("/api/v1/roles", headers=auth(admin_token))).json()
        viewer = next(role for role in roles if role["key"] == "viewer")

        granted = await client.patch(
            f"/api/v1/roles/{viewer['id']}",
            headers=auth(admin_token),
            json={"panel_keys": ["dashboard", "admin_users"]},
        )
        assert granted.status_code == 200

        me = (await client.get("/api/v1/me", headers=auth(viewer_token))).json()
        assert "admin_users" in [panel["key"] for panel in me["panels"]]

        # Link visible, endpoint still closed.
        response = await client.get("/api/v1/users", headers=auth(viewer_token))
        assert response.status_code == 403

    async def test_revoking_a_role_takes_effect_immediately(
        self, client: AsyncClient, admin_token: str
    ) -> None:
        """Permissions are read per request, not baked into the access token."""
        analyst = await create_user(
            client, admin_token, username="analyst", role_keys=["security_analyst"]
        )
        token = await sign_in(client, "analyst", OTHER_PASSWORD, totp_secret="")

        assert (await client.get("/api/v1/permissions", headers=auth(token))).status_code == 200

        await client.patch(
            f"/api/v1/users/{analyst['id']}",
            headers=auth(admin_token),
            json={"role_keys": []},
        )

        # Same still-valid access token, but the roles behind it are gone.
        me = (await client.get("/api/v1/me", headers=auth(token))).json()
        assert me["permissions"] == []


class TestAuthentication:
    @pytest.mark.parametrize(("method", "path"), ADMIN_ROUTES)
    async def test_unauthenticated_requests_are_rejected(
        self, client: AsyncClient, onboarded: object, method: str, path: str
    ) -> None:
        response = await client.request(method, path, json={})

        assert response.status_code == 401

    async def test_a_garbage_token_is_rejected(
        self, client: AsyncClient, onboarded: object
    ) -> None:
        response = await client.get("/api/v1/me", headers=auth("not-a-real-token"))

        assert response.status_code == 401

    async def test_a_deactivated_user_loses_access_immediately(
        self, client: AsyncClient, admin_token: str
    ) -> None:
        target = await create_user(
            client, admin_token, username="analyst", role_keys=["security_analyst"]
        )
        token = await sign_in(client, "analyst", OTHER_PASSWORD, totp_secret="")

        await client.patch(
            f"/api/v1/users/{target['id']}",
            headers=auth(admin_token),
            json={"is_active": False},
        )

        assert (await client.get("/api/v1/me", headers=auth(token))).status_code == 401


class TestMeContract:
    async def test_returns_everything_the_frontend_renders_from(
        self, client: AsyncClient, admin_token: str
    ) -> None:
        me = (await client.get("/api/v1/me", headers=auth(admin_token))).json()

        assert me["user"]["username"] == "admin"
        assert "super_admin" in [role["key"] for role in me["roles"]]
        assert "user:manage" in me["permissions"]
        assert me["panels"]
        assert me["org_name"] == "Test Bank Sdn Bhd"
        assert me["org_initials"] == "TB"
        assert me["brand_color"].startswith("#")

    async def test_super_admin_sees_every_panel(
        self, client: AsyncClient, admin_token: str
    ) -> None:
        me = (await client.get("/api/v1/me", headers=auth(admin_token))).json()
        panels = (await client.get("/api/v1/panels", headers=auth(admin_token))).json()

        assert len(me["panels"]) == len(panels)


class TestRoleAdministration:
    async def test_super_admin_permissions_cannot_be_narrowed(
        self, client: AsyncClient, admin_token: str
    ) -> None:
        roles = (await client.get("/api/v1/roles", headers=auth(admin_token))).json()
        super_admin = next(role for role in roles if role["key"] == "super_admin")

        response = await client.patch(
            f"/api/v1/roles/{super_admin['id']}",
            headers=auth(admin_token),
            json={"permission_keys": ["alert:read"]},
        )

        # Otherwise an administrator can lock the whole instance out of itself.
        assert response.status_code == 403

    async def test_system_roles_cannot_be_deleted(
        self, client: AsyncClient, admin_token: str
    ) -> None:
        roles = (await client.get("/api/v1/roles", headers=auth(admin_token))).json()
        viewer = next(role for role in roles if role["key"] == "viewer")

        response = await client.delete(f"/api/v1/roles/{viewer['id']}", headers=auth(admin_token))

        assert response.status_code == 403

    async def test_a_role_still_held_by_someone_cannot_be_deleted(
        self, client: AsyncClient, admin_token: str
    ) -> None:
        created = await client.post(
            "/api/v1/roles",
            headers=auth(admin_token),
            json={"key": "auditor", "name": "Auditor", "permission_keys": ["audit:read"]},
        )
        role_id = created.json()["id"]
        await create_user(client, admin_token, username="auditor", role_keys=["auditor"])

        response = await client.delete(f"/api/v1/roles/{role_id}", headers=auth(admin_token))

        assert response.status_code == 409

    async def test_a_custom_role_grants_exactly_what_it_lists(
        self, client: AsyncClient, admin_token: str
    ) -> None:
        await client.post(
            "/api/v1/roles",
            headers=auth(admin_token),
            json={
                "key": "auditor",
                "name": "Auditor",
                "permission_keys": ["audit:read"],
                "panel_keys": ["admin_audit"],
            },
        )
        await create_user(client, admin_token, username="auditor", role_keys=["auditor"])
        token = await sign_in(client, "auditor", OTHER_PASSWORD, totp_secret="")

        assert (await client.get("/api/v1/audit-logs", headers=auth(token))).status_code == 200
        assert (await client.get("/api/v1/users", headers=auth(token))).status_code == 403

    async def test_unknown_permission_keys_are_rejected(
        self, client: AsyncClient, admin_token: str
    ) -> None:
        response = await client.post(
            "/api/v1/roles",
            headers=auth(admin_token),
            json={"key": "bogus", "name": "Bogus", "permission_keys": ["does:notexist"]},
        )

        assert response.status_code == 422


class TestSelfProtection:
    async def test_cannot_deactivate_yourself(self, client: AsyncClient, admin_token: str) -> None:
        me = (await client.get("/api/v1/me", headers=auth(admin_token))).json()

        response = await client.patch(
            f"/api/v1/users/{me['user']['id']}",
            headers=auth(admin_token),
            json={"is_active": False},
        )

        assert response.status_code == 403

    async def test_cannot_remove_your_own_super_admin_role(
        self, client: AsyncClient, admin_token: str
    ) -> None:
        me = (await client.get("/api/v1/me", headers=auth(admin_token))).json()

        response = await client.patch(
            f"/api/v1/users/{me['user']['id']}",
            headers=auth(admin_token),
            json={"role_keys": ["viewer"]},
        )

        assert response.status_code == 403

    async def test_cannot_delete_yourself(self, client: AsyncClient, admin_token: str) -> None:
        me = (await client.get("/api/v1/me", headers=auth(admin_token))).json()

        response = await client.delete(
            f"/api/v1/users/{me['user']['id']}", headers=auth(admin_token)
        )

        assert response.status_code == 403
