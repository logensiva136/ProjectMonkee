"""The first-run wizard (SPEC §6.1)."""

from __future__ import annotations

import pyotp
import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.identity import AuditLog, RecoveryCode, User
from app.models.rbac import Panel, Permission, Role
from tests.helpers import STRONG_PASSWORD, onboard


class TestStatus:
    async def test_reports_setup_needed_on_a_fresh_instance(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/setup/status")

        assert response.status_code == 200
        assert response.json()["needs_setup"] is True

    async def test_reports_complete_afterwards(self, client: AsyncClient) -> None:
        await onboard(client, org_name="Acme Holdings Berhad")

        body = (await client.get("/api/v1/setup/status")).json()

        assert body["needs_setup"] is False
        assert body["org_name"] == "Acme Holdings Berhad"


class TestCompletion:
    async def test_creates_a_super_admin_with_2fa_and_recovery_codes(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        result = await onboard(client, username="logen")

        assert result["username"] == "logen"
        assert result["access_token"]
        assert len(result["recovery_codes"]) == 10
        # Every code distinct, or one lost code would burn several.
        assert len(set(result["recovery_codes"])) == 10

        user = (await session.execute(select(User).where(User.username == "logen"))).scalar_one()
        assert user.totp_enabled is True
        assert user.totp_secret_encrypted is not None
        # Stored encrypted, never as the Base32 secret itself.
        assert result["totp_secret"] not in user.totp_secret_encrypted

        codes = await session.execute(
            select(func.count()).select_from(RecoveryCode).where(RecoveryCode.user_id == user.id)
        )
        assert codes.scalar_one() == 10

    async def test_sets_the_refresh_cookie_so_the_operator_lands_signed_in(
        self, client: AsyncClient
    ) -> None:
        await onboard(client)

        assert "hayabusa_refresh" in client.cookies

    async def test_seeds_roles_permissions_and_panels(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        await onboard(client)

        roles = {r.key for r in (await session.execute(select(Role))).scalars()}
        assert {"super_admin", "security_analyst", "tprm_officer", "viewer"} <= roles

        assert (await session.execute(select(func.count()).select_from(Permission))).scalar_one()
        assert (await session.execute(select(func.count()).select_from(Panel))).scalar_one()

    async def test_super_admin_holds_every_permission(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        await onboard(client)

        result = await session.execute(select(Role).where(Role.key == "super_admin"))
        role = result.scalar_one()
        total = (await session.execute(select(func.count()).select_from(Permission))).scalar_one()

        assert len(role.permissions) == total

    async def test_derives_org_initials_ignoring_corporate_suffixes(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        from app.models.identity import AppSetting

        await onboard(client, org_name="Test Bank Sdn Bhd")

        setting = (await session.execute(select(AppSetting))).scalar_one()
        # "Sdn Bhd" carries no identity, so it must not contribute initials.
        assert setting.org_initials == "TB"

    async def test_records_an_audit_entry(self, client: AsyncClient, session: AsyncSession) -> None:
        await onboard(client, username="logen")

        entry = (
            await session.execute(select(AuditLog).where(AuditLog.action == "setup.completed"))
        ).scalar_one()
        assert entry.actor_username == "logen"


class TestValidation:
    async def test_rejects_a_wrong_totp_code(self, client: AsyncClient) -> None:
        enrol = await client.post("/api/v1/setup/totp")
        secret = enrol.json()["secret"]

        response = await client.post(
            "/api/v1/setup/complete",
            json={
                "full_name": "Test Operator",
                "username": "operator",
                "email": "operator@example.com",
                "password": STRONG_PASSWORD,
                "totp_secret": secret,
                "totp_code": "000000",
                "recovery_codes_acknowledged": True,
            },
        )

        assert response.status_code == 422
        assert "six-digit code" in response.json()["detail"]

    @pytest.mark.parametrize(
        ("password", "reason"),
        [
            ("Short-1a!", "under 12 characters"),
            ("passwordpassword", "common and only one character class"),
            ("Password123!", "on the common-password denylist"),
        ],
    )
    async def test_rejects_weak_passwords(
        self, client: AsyncClient, password: str, reason: str
    ) -> None:
        enrol = await client.post("/api/v1/setup/totp")
        secret = enrol.json()["secret"]

        response = await client.post(
            "/api/v1/setup/complete",
            json={
                "full_name": "Test Operator",
                "username": "operator",
                "email": "operator@example.com",
                "password": password,
                "totp_secret": secret,
                "totp_code": pyotp.TOTP(secret).now(),
                "recovery_codes_acknowledged": True,
            },
        )

        assert response.status_code == 422, f"should reject a password {reason}"

    async def test_requires_the_recovery_codes_to_be_acknowledged(
        self, client: AsyncClient
    ) -> None:
        enrol = await client.post("/api/v1/setup/totp")
        secret = enrol.json()["secret"]

        response = await client.post(
            "/api/v1/setup/complete",
            json={
                "full_name": "Test Operator",
                "username": "operator",
                "email": "operator@example.com",
                "password": STRONG_PASSWORD,
                "totp_secret": secret,
                "totp_code": pyotp.TOTP(secret).now(),
                "recovery_codes_acknowledged": False,
            },
        )

        assert response.status_code == 422

    async def test_normalises_username_case(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        enrol = await client.post("/api/v1/setup/totp")
        secret = enrol.json()["secret"]

        response = await client.post(
            "/api/v1/setup/complete",
            json={
                "full_name": "Test Operator",
                "username": "LogenSiva",
                "email": "Operator@Example.COM",
                "password": STRONG_PASSWORD,
                "totp_secret": secret,
                "totp_code": pyotp.TOTP(secret).now(),
                "recovery_codes_acknowledged": True,
            },
        )

        assert response.status_code == 201
        user = (await session.execute(select(User))).scalar_one()
        assert user.username == "logensiva"
        assert user.email == "operator@example.com"


class TestOneTimeOnly:
    async def test_setup_routes_are_gone_afterwards(self, client: AsyncClient) -> None:
        await onboard(client)

        response = await client.post("/api/v1/setup/complete", json={})

        # 410 Gone, permanently — SPEC §6.1.
        assert response.status_code == 410

    async def test_helper_routes_are_gone_too(self, client: AsyncClient) -> None:
        await onboard(client)

        assert (await client.post("/api/v1/setup/totp")).status_code == 410
        assert (
            await client.post("/api/v1/setup/password-check", json={"password": "x"})
        ).status_code == 410

    async def test_status_still_answers(self, client: AsyncClient) -> None:
        await onboard(client)

        # The frontend polls this on every boot to decide whether to redirect.
        assert (await client.get("/api/v1/setup/status")).status_code == 200


class TestPasswordCheck:
    async def test_agrees_with_what_completion_enforces(self, client: AsyncClient) -> None:
        weak = await client.post("/api/v1/setup/password-check", json={"password": "password123"})
        strong = await client.post(
            "/api/v1/setup/password-check", json={"password": STRONG_PASSWORD}
        )

        assert weak.json()["acceptable"] is False
        assert weak.json()["problems"]
        assert strong.json()["acceptable"] is True
        assert strong.json()["score"] >= 3

    async def test_penalises_a_password_built_from_the_username(self, client: AsyncClient) -> None:
        response = await client.post(
            "/api/v1/setup/password-check",
            json={"password": "Logensiva-2026!", "username": "logensiva"},
        )

        assert response.json()["acceptable"] is False


class TestMonogram:
    async def test_previews_deterministically(self, client: AsyncClient) -> None:
        first = await client.post("/api/v1/setup/monogram-preview", params={"name": "Maybank"})
        second = await client.post("/api/v1/setup/monogram-preview", params={"name": "Maybank"})

        # Must not change between the wizard preview and what renders later.
        assert first.json() == second.json()
        assert first.json()["initials"] == "MA"
        assert "<svg" in first.json()["svg"]
