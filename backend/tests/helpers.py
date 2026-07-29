"""Helpers that drive the real API, rather than reaching into the database.

Tests that onboard through `POST /setup/complete` and sign in through
`POST /auth/login` exercise the same code path an operator does. Creating a user
row directly would skip the password policy, the TOTP requirement and the
seeding — precisely the things worth testing.
"""

from __future__ import annotations

from typing import Any

import pyotp
from httpx import AsyncClient

# Passes the SPEC §6.1 policy: 12+ chars, three character classes, zxcvbn >= 3,
# not in the denylist, and unrelated to the username below.
STRONG_PASSWORD = "Tumbler-Quartz-91!"
OTHER_PASSWORD = "Lantern-Kestrel-42?"


async def onboard(
    client: AsyncClient,
    *,
    username: str = "operator",
    email: str = "operator@example.com",
    full_name: str = "Test Operator",
    org_name: str | None = "Test Bank Sdn Bhd",
    password: str = STRONG_PASSWORD,
) -> dict[str, Any]:
    """Run the whole wizard. Returns the setup response plus the TOTP secret."""
    enrol = await client.post("/api/v1/setup/totp", params={"username": username})
    enrol.raise_for_status()
    secret = enrol.json()["secret"]

    response = await client.post(
        "/api/v1/setup/complete",
        json={
            "full_name": full_name,
            "username": username,
            "email": email,
            "org_name": org_name,
            "password": password,
            "totp_secret": secret,
            "totp_code": pyotp.TOTP(secret).now(),
            "recovery_codes_acknowledged": True,
        },
    )
    response.raise_for_status()

    payload: dict[str, Any] = response.json()
    payload["totp_secret"] = secret
    payload["password"] = password
    return payload


async def sign_in(client: AsyncClient, username: str, password: str, totp_secret: str) -> str:
    """Complete both auth steps. Returns an access token."""
    login = await client.post(
        "/api/v1/auth/login", json={"username": username, "password": password}
    )
    login.raise_for_status()
    body = login.json()

    if body["status"] == "authenticated":
        return str(body["access_token"])

    verify = await client.post(
        "/api/v1/auth/mfa/verify",
        json={"mfa_token": body["mfa_token"], "code": pyotp.TOTP(totp_secret).now()},
    )
    verify.raise_for_status()
    return str(verify.json()["access_token"])


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def create_user(
    client: AsyncClient,
    admin_token: str,
    *,
    username: str,
    role_keys: list[str],
    password: str = OTHER_PASSWORD,
    email: str | None = None,
) -> dict[str, Any]:
    response = await client.post(
        "/api/v1/users",
        headers=auth(admin_token),
        json={
            "full_name": f"User {username}",
            "username": username,
            "email": email or f"{username}@example.com",
            "password": password,
            "role_keys": role_keys,
            "must_change_password": False,
        },
    )
    response.raise_for_status()
    result: dict[str, Any] = response.json()
    result["password"] = password
    return result
