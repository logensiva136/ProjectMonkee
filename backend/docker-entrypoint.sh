#!/bin/sh
# Container entrypoint for the api / worker / beat roles.
#
# Waits for Postgres, then applies migrations when AUTO_MIGRATE is enabled
# (DECISIONS.md D-002), then execs whatever command the compose service asked
# for. `exec` matters: it replaces this shell with the real process so signals
# reach it directly and shutdown stays graceful.

set -eu

ROLE="${HAYABUSA_ROLE:-api}"

wait_for_postgres() {
    # Compose healthchecks already gate start-up, but a database can also be
    # external (SPEC §2 allows pointing at a host instance), where compose has
    # no visibility. Retry rather than crash-loop.
    attempts=0
    max_attempts=30

    while [ "$attempts" -lt "$max_attempts" ]; do
        if python -c "
import asyncio, sys
import asyncpg
from app.config import get_settings

async def main():
    url = get_settings().database_url.replace('postgresql+asyncpg://', 'postgresql://', 1)
    conn = await asyncpg.connect(url, timeout=3)
    await conn.close()

try:
    asyncio.run(main())
except Exception:
    sys.exit(1)
" 2>/dev/null; then
            return 0
        fi
        attempts=$((attempts + 1))
        echo "waiting for postgres ($attempts/$max_attempts)..." >&2
        sleep 2
    done

    echo "postgres did not become reachable in time" >&2
    return 1
}

wait_for_postgres

# Only the api role migrates. If worker and beat also ran `upgrade head` they
# would contend on the advisory lock at every deploy for no benefit.
if [ "$ROLE" = "api" ] && [ "${AUTO_MIGRATE:-true}" = "true" ]; then
    echo "applying database migrations..." >&2
    alembic upgrade head
fi

exec "$@"
