"""Configuration validation.

These guard the boot path: a bad `APP_ENCRYPTION_KEY` must fail at start-up with
a clear message, not at 3 a.m. the first time a Telegram token is encrypted.
"""

from __future__ import annotations

import base64
import secrets

import pytest
from pydantic import ValidationError

from app.config import Settings

VALID_KEY = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()
VALID_SECRET = secrets.token_urlsafe(48)


def build(**overrides: object) -> Settings:
    """Construct Settings in isolation.

    `_env_file=None` stops pydantic-settings reading the developer's real `.env`,
    which would otherwise leak local values into assertions about defaults.
    """
    values: dict[str, object] = {
        "app_secret_key": VALID_SECRET,
        "app_encryption_key": VALID_KEY,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)  # type: ignore[arg-type]


class TestEncryptionKey:
    def test_accepts_a_32_byte_urlsafe_base64_key(self) -> None:
        assert len(build().encryption_key_bytes) == 32

    @pytest.mark.parametrize(
        "bad_key",
        [
            base64.urlsafe_b64encode(secrets.token_bytes(16)).decode(),  # AES-128 length
            base64.urlsafe_b64encode(secrets.token_bytes(64)).decode(),  # too long
            "not-base64-at-all!!",
        ],
        ids=["16-bytes", "64-bytes", "not-base64"],
    )
    def test_rejects_anything_aes_256_gcm_cannot_use(self, bad_key: str) -> None:
        with pytest.raises(ValidationError):
            build(app_encryption_key=bad_key)


class TestSecretKey:
    def test_rejects_a_short_signing_key(self) -> None:
        with pytest.raises(ValidationError):
            build(app_secret_key="too-short")


class TestDatabaseUrl:
    def test_requires_the_async_driver(self) -> None:
        # A sync URL would work under Alembic and then fail at the first request.
        with pytest.raises(ValidationError):
            build(database_url="postgresql://postgres:postgres@localhost:5432/hayabusa")

    def test_derives_a_sync_url_for_offline_tooling(self) -> None:
        settings = build(database_url="postgresql+asyncpg://postgres:postgres@db:5432/hayabusa")

        assert settings.sync_database_url == "postgresql://postgres:postgres@db:5432/hayabusa"


class TestTimezone:
    def test_accepts_the_spec_default(self) -> None:
        assert build(app_timezone="Asia/Kuala_Lumpur").timezone.key == "Asia/Kuala_Lumpur"

    def test_rejects_an_unknown_zone(self) -> None:
        with pytest.raises(ValidationError):
            build(app_timezone="Mars/Olympus_Mons")


class TestCorsOrigins:
    def test_splits_a_comma_separated_environment_value(self) -> None:
        settings = build(cors_origins="http://localhost:3000, http://localhost:5173")

        assert settings.cors_origins == ["http://localhost:3000", "http://localhost:5173"]

    def test_defaults_to_empty(self) -> None:
        assert build().cors_origins == []

    def test_reads_the_comma_separated_form_from_a_dotenv_file(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        # Regression test: a `list[str]` settings field is JSON-decoded by
        # pydantic-settings before validators run, so without `NoDecode` the
        # documented `A,B` form in .env raises SettingsError at import time.
        env_file = tmp_path / ".env"
        env_file.write_text(
            f"APP_SECRET_KEY={VALID_SECRET}\n"
            f"APP_ENCRYPTION_KEY={VALID_KEY}\n"
            "CORS_ORIGINS=http://localhost:3000,http://localhost:5173\n",
            encoding="utf-8",
        )

        settings = Settings(_env_file=str(env_file))  # type: ignore[call-arg]

        assert settings.cors_origins == ["http://localhost:3000", "http://localhost:5173"]
