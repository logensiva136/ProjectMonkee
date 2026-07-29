"""Alembic environment, wired to the application's async engine.

The database URL always comes from `app.config`, never from `alembic.ini`, so
migrations cannot accidentally run against a different database than the app.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from sqlalchemy import pool, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context
from app.config import get_settings

# Importing the model package registers every table on Base.metadata.
# Without this, autogenerate would compare the live database against an empty
# schema and cheerfully generate a migration that drops everything.
from app.models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.database_url)

target_metadata = Base.metadata

# Arbitrary but fixed key identifying the "schema migration" advisory lock.
# The api container runs `alembic upgrade head` on start (DECISIONS.md D-002);
# if it is ever scaled past one replica, they would otherwise race to apply the
# same revision. Any process that takes this lock waits instead.
MIGRATION_LOCK_KEY = 0x48415941  # "HAYA"


def _include_object(
    obj: object,  # noqa: ARG001 - part of Alembic's callback signature
    name: str | None,
    type_: str,
    reflected: bool,  # noqa: ARG001 - part of Alembic's callback signature
    compare_to: object,  # noqa: ARG001 - part of Alembic's callback signature
) -> bool:
    """Keep extension-owned objects out of autogenerate.

    `pg_trgm` and friends create their own operator classes and indexes; without
    this filter Alembic proposes dropping them on every revision.
    """
    return not (type_ == "table" and name in {"spatial_ref_sys"})


def run_migrations_offline() -> None:
    """Emit SQL to stdout instead of executing it (`alembic upgrade head --sql`)."""
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
        include_object=_include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def _do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        # Detect column type and server-default drift, not just added/removed
        # columns — otherwise a widened varchar never produces a migration.
        compare_type=True,
        compare_server_default=True,
        include_object=_include_object,
        # Render Postgres-specific types (JSONB, UUID, ARRAY) with their real
        # names in generated migrations rather than the generic fallbacks.
        render_as_batch=False,
    )
    with context.begin_transaction():
        # `pg_advisory_xact_lock` blocks until the lock is free and releases
        # automatically when this transaction ends — including on failure, so a
        # crashed migration cannot leave the lock stuck.
        connection.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": MIGRATION_LOCK_KEY})
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,  # a migration run is short-lived; no pool needed
    )
    async with connectable.connect() as connection:
        await connection.run_sync(_do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
