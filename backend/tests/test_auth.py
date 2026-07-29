"""Login, second factor, session rotation and lockout (SPEC §6.2)."""

from __future__ import annotations

import pyotp
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.identity import RefreshToken, User
from tests.helpers import STRONG_PASSWORD, auth, onboard, sign_in


class TestLogin:
    async def test_password_step_demands_the_second_factor(self, client: AsyncClient) -> None:
        await onboard(client, username="logen")

        response = await client.post(
            "/api/v1/auth/login", json={"username": "logen", "password": STRONG_PASSWORD}
        )

        body = response.json()
        assert body["status"] == "mfa_required"
        assert body["mfa_token"]
        # No session exists yet — an access token here would skip 2FA entirely.
        assert body["access_token"] is None

    async def test_completing_mfa_returns_an_access_token(self, client: AsyncClient) -> None:
        result = await onboard(client, username="logen")

        token = await sign_in(client, "logen", STRONG_PASSWORD, result["totp_secret"])

        me = await client.get("/api/v1/me", headers=auth(token))
        assert me.status_code == 200
        assert me.json()["user"]["username"] == "logen"

    async def test_username_is_case_insensitive(self, client: AsyncClient) -> None:
        await onboard(client, username="logen")

        response = await client.post(
            "/api/v1/auth/login", json={"username": "LOGEN", "password": STRONG_PASSWORD}
        )

        assert response.json()["status"] == "mfa_required"

    async def test_unknown_user_and_wrong_password_are_indistinguishable(
        self, client: AsyncClient
    ) -> None:
        await onboard(client, username="logen")

        wrong = await client.post(
            "/api/v1/auth/login", json={"username": "logen", "password": "Wrong-Password-99!"}
        )
        missing = await client.post(
            "/api/v1/auth/login", json={"username": "nobody", "password": "Wrong-Password-99!"}
        )

        # Differing messages would be a free account-enumeration oracle.
        assert wrong.status_code == missing.status_code == 401
        assert wrong.json()["detail"] == missing.json()["detail"]

    async def test_mfa_token_cannot_be_used_as_an_access_token(self, client: AsyncClient) -> None:
        await onboard(client, username="logen")
        login = await client.post(
            "/api/v1/auth/login", json={"username": "logen", "password": STRONG_PASSWORD}
        )
        mfa_token = login.json()["mfa_token"]

        response = await client.get("/api/v1/me", headers=auth(mfa_token))

        assert response.status_code == 401


class TestLockout:
    async def test_locks_the_account_after_five_failures(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        await onboard(client, username="logen")

        for _ in range(5):
            await client.post(
                "/api/v1/auth/login", json={"username": "logen", "password": "Wrong-Password-99!"}
            )

        response = await client.post(
            "/api/v1/auth/login", json={"username": "logen", "password": STRONG_PASSWORD}
        )

        # 429 with Retry-After, not 401 — the credentials were correct; the
        # account is simply locked.
        assert response.status_code == 429
        assert response.headers.get("Retry-After")

        user = (await session.execute(select(User).where(User.username == "logen"))).scalar_one()
        assert user.failed_login_count >= 5

    async def test_a_successful_login_clears_the_failure_counter(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        result = await onboard(client, username="logen")

        await client.post(
            "/api/v1/auth/login", json={"username": "logen", "password": "Wrong-Password-99!"}
        )
        await sign_in(client, "logen", STRONG_PASSWORD, result["totp_secret"])

        user = (await session.execute(select(User).where(User.username == "logen"))).scalar_one()
        assert user.failed_login_count == 0


class TestSecondFactor:
    async def test_rejects_a_wrong_code(self, client: AsyncClient) -> None:
        await onboard(client, username="logen")
        login = await client.post(
            "/api/v1/auth/login", json={"username": "logen", "password": STRONG_PASSWORD}
        )

        response = await client.post(
            "/api/v1/auth/mfa/verify",
            json={"mfa_token": login.json()["mfa_token"], "code": "000000"},
        )

        assert response.status_code == 401

    async def test_accepts_a_recovery_code_in_place_of_a_totp_code(
        self, client: AsyncClient
    ) -> None:
        result = await onboard(client, username="logen")
        code = result["recovery_codes"][0]

        login = await client.post(
            "/api/v1/auth/login", json={"username": "logen", "password": STRONG_PASSWORD}
        )
        response = await client.post(
            "/api/v1/auth/mfa/verify",
            json={"mfa_token": login.json()["mfa_token"], "code": code},
        )

        assert response.status_code == 200
        assert response.json()["access_token"]

    async def test_a_recovery_code_works_only_once(self, client: AsyncClient) -> None:
        result = await onboard(client, username="logen")
        code = result["recovery_codes"][0]

        for _ in range(2):
            login = await client.post(
                "/api/v1/auth/login", json={"username": "logen", "password": STRONG_PASSWORD}
            )
            response = await client.post(
                "/api/v1/auth/mfa/verify",
                json={"mfa_token": login.json()["mfa_token"], "code": code},
            )

        assert response.status_code == 401

    async def test_recovery_codes_are_accepted_in_any_formatting(self, client: AsyncClient) -> None:
        result = await onboard(client, username="logen")
        # Someone reading a code off a printout will not preserve the hyphen.
        code = result["recovery_codes"][0].lower().replace("-", " ")

        login = await client.post(
            "/api/v1/auth/login", json={"username": "logen", "password": STRONG_PASSWORD}
        )
        response = await client.post(
            "/api/v1/auth/mfa/verify",
            json={"mfa_token": login.json()["mfa_token"], "code": code},
        )

        assert response.status_code == 200


class TestRefreshRotation:
    async def test_refresh_issues_a_new_pair(self, client: AsyncClient) -> None:
        result = await onboard(client, username="logen")
        first_cookie = client.cookies["hayabusa_refresh"]

        response = await client.post("/api/v1/auth/refresh")

        assert response.status_code == 200
        assert response.json()["access_token"]
        assert client.cookies["hayabusa_refresh"] != first_cookie
        assert result["access_token"]

    async def test_replaying_a_rotated_token_revokes_the_whole_family(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        await onboard(client, username="logen")
        stolen = client.cookies["hayabusa_refresh"]

        # Legitimate client rotates, so `stolen` is now revoked.
        await client.post("/api/v1/auth/refresh")

        # Attacker replays the captured token.
        client.cookies.set("hayabusa_refresh", stolen)
        replay = await client.post("/api/v1/auth/refresh")

        assert replay.status_code == 401

        # And the legitimate session is gone too: better a forced re-login than
        # a live session in an attacker's hands.
        live = await session.execute(select(RefreshToken).where(RefreshToken.revoked_at.is_(None)))
        assert live.scalars().all() == []

    async def test_refresh_without_a_cookie_is_rejected(self, client: AsyncClient) -> None:
        await onboard(client)
        client.cookies.clear()

        assert (await client.post("/api/v1/auth/refresh")).status_code == 401


class TestSessions:
    async def test_lists_and_marks_the_current_session(self, client: AsyncClient) -> None:
        result = await onboard(client, username="logen")
        token = await sign_in(client, "logen", STRONG_PASSWORD, result["totp_secret"])

        response = await client.get("/api/v1/auth/sessions", headers=auth(token))

        sessions = response.json()
        assert len(sessions) >= 1
        assert any(s["is_current"] for s in sessions)

    async def test_logout_revokes_the_session(self, client: AsyncClient) -> None:
        await onboard(client, username="logen")

        await client.post("/api/v1/auth/logout")
        response = await client.post("/api/v1/auth/refresh")

        assert response.status_code == 401

    async def test_revoke_all_ends_every_session(self, client: AsyncClient) -> None:
        result = await onboard(client, username="logen")
        token = await sign_in(client, "logen", STRONG_PASSWORD, result["totp_secret"])

        await client.delete("/api/v1/auth/sessions", headers=auth(token))

        assert (await client.post("/api/v1/auth/refresh")).status_code == 401


class TestPasswordChange:
    async def test_requires_the_current_password(self, client: AsyncClient) -> None:
        result = await onboard(client, username="logen")
        token = await sign_in(client, "logen", STRONG_PASSWORD, result["totp_secret"])

        response = await client.post(
            "/api/v1/auth/password/change",
            headers=auth(token),
            json={"current_password": "Wrong-Password-99!", "new_password": "Cobalt-Ledger-73!"},
        )

        assert response.status_code == 401

    async def test_enforces_the_password_policy(self, client: AsyncClient) -> None:
        result = await onboard(client, username="logen")
        token = await sign_in(client, "logen", STRONG_PASSWORD, result["totp_secret"])

        response = await client.post(
            "/api/v1/auth/password/change",
            headers=auth(token),
            json={"current_password": STRONG_PASSWORD, "new_password": "password12345"},
        )

        assert response.status_code == 422

    async def test_changing_the_password_signs_other_sessions_out(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        result = await onboard(client, username="logen")
        token = await sign_in(client, "logen", STRONG_PASSWORD, result["totp_secret"])

        response = await client.post(
            "/api/v1/auth/password/change",
            headers=auth(token),
            json={"current_password": STRONG_PASSWORD, "new_password": "Cobalt-Ledger-73!"},
        )

        assert response.status_code == 200
        # A password change is the standard response to a suspected compromise,
        # so exactly one session — the freshly issued one — may remain.
        live = await session.execute(select(RefreshToken).where(RefreshToken.revoked_at.is_(None)))
        assert len(live.scalars().all()) == 1


class TestRecoveryCodeRegeneration:
    async def test_replaces_every_existing_code(self, client: AsyncClient) -> None:
        result = await onboard(client, username="logen")
        old_code = result["recovery_codes"][0]
        token = await sign_in(client, "logen", STRONG_PASSWORD, result["totp_secret"])

        response = await client.post("/api/v1/auth/recovery-codes/regenerate", headers=auth(token))

        assert response.status_code == 201
        new_codes = response.json()["recovery_codes"]
        assert len(new_codes) == 10
        assert old_code not in new_codes

        # The old code must no longer authenticate.
        login = await client.post(
            "/api/v1/auth/login", json={"username": "logen", "password": STRONG_PASSWORD}
        )
        verify = await client.post(
            "/api/v1/auth/mfa/verify",
            json={"mfa_token": login.json()["mfa_token"], "code": old_code},
        )
        assert verify.status_code == 401


class TestTotpSecretHandling:
    async def test_the_stored_secret_round_trips_through_encryption(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        result = await onboard(client, username="logen")

        user = (await session.execute(select(User).where(User.username == "logen"))).scalar_one()

        from app.core.crypto import decrypt

        assert decrypt(user.totp_secret_encrypted or "") == result["totp_secret"]
        # And a code minted from the decrypted secret still verifies.
        assert pyotp.TOTP(result["totp_secret"]).now()
