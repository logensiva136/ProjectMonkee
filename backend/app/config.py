"""Application configuration, loaded from the environment (SPEC §4).

Every value is env-driven; nothing here carries a usable secret default. The
settings object is built once and cached, so importing `get_settings()` from
anywhere — API, worker, Alembic — sees the same configuration.
"""

from __future__ import annotations

import base64
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---------------------------------------------------------------- app ---
    app_name: str = "HAYABUSA"
    app_env: Literal["development", "staging", "production", "test"] = "development"
    app_timezone: str = "Asia/Kuala_Lumpur"
    app_public_url: str = "http://localhost:3000"

    app_secret_key: str = Field(min_length=32, description="JWT signing key")
    app_encryption_key: str = Field(description="32-byte urlsafe-base64 AES-GCM key")

    # -------------------------------------------------------------- stores ---
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/hayabusa"
    redis_url: str = "redis://localhost:6379/0"

    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_pool_timeout_seconds: int = 30
    db_pool_recycle_seconds: int = 1800
    db_echo: bool = False

    # ----------------------------------------------------------- collector ---
    default_poll_interval_seconds: int = 10_800
    http_user_agent: str = "HAYABUSA-Collector/1.0"
    http_timeout_seconds: int = 30
    collector_concurrency: int = 8

    nvd_api_key: str = ""
    github_token: str = ""

    # ---------------------------------------------------------------- auth ---
    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 7

    # SPEC §6.2 lockout policy.
    max_failed_logins: int = 5
    lockout_minutes: int = 15

    # -------------------------------------------------------------- uploads ---
    #: Where organisation logos are written. Must be a mounted volume in
    #: production, or the logo vanishes when the container is replaced.
    upload_dir: Path = Path("uploads")

    # -------------------------------------------------------- observability ---
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    log_format: Literal["json", "console"] = "json"

    # ---------------------------------------------------------------- http ---
    # `NoDecode` is required: without it pydantic-settings sees a `list[str]`
    # field and tries to `json.loads` the raw environment value, so the plain
    # comma-separated form documented in .env.example raises a SettingsError
    # before the validator below ever runs.
    cors_origins: Annotated[list[str], NoDecode] = Field(default_factory=list)

    # -------------------------------------------------------------- deploy ---
    auto_migrate: bool = True

    # ------------------------------------------------------------ validators ---

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        """Accept `a,b,c` from the environment as well as a real list."""
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("app_timezone")
    @classmethod
    def _known_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:  # pragma: no cover - config error path
            raise ValueError(f"unknown APP_TIMEZONE {value!r}") from exc
        return value

    @field_validator("app_encryption_key")
    @classmethod
    def _valid_aes_key(cls, value: str) -> str:
        """AES-256-GCM needs exactly 32 bytes; fail at boot, not at first encrypt."""
        try:
            raw = base64.urlsafe_b64decode(value)
        except (ValueError, TypeError) as exc:
            raise ValueError("APP_ENCRYPTION_KEY must be urlsafe-base64") from exc
        if len(raw) != 32:
            raise ValueError(f"APP_ENCRYPTION_KEY must decode to 32 bytes, got {len(raw)}")
        return value

    @field_validator("database_url")
    @classmethod
    def _async_driver(cls, value: str) -> str:
        if not value.startswith("postgresql+asyncpg://"):
            raise ValueError("DATABASE_URL must use the postgresql+asyncpg:// driver")
        return value

    # --------------------------------------------------------------- derived ---

    @property
    def timezone(self) -> ZoneInfo:
        return ZoneInfo(self.app_timezone)

    @property
    def encryption_key_bytes(self) -> bytes:
        return base64.urlsafe_b64decode(self.app_encryption_key)

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def sync_database_url(self) -> str:
        """Same database, psycopg-free sync driver — used only by offline tooling."""
        return self.database_url.replace("postgresql+asyncpg://", "postgresql://", 1)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Process-wide settings singleton.

    Cached so that config validation runs once per process and every module
    observes identical values.
    """
    return Settings()
