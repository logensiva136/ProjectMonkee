# HAYABUSA backend — serves the API, and runs the Celery worker and beat.
#
# One image for all three roles (api / worker / beat); the compose `command`
# decides which. They share every dependency, so three images would mean three
# builds and three chances for them to drift apart.

# ---------------------------------------------------------------- builder ----
FROM python:3.12-slim-bookworm AS builder

# uv resolves and installs an order of magnitude faster than pip, which matters
# across a build loop this size (DECISIONS.md D-004).
COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /build

# Dependencies are installed from pyproject.toml alone, before the source is
# copied. Docker caches that layer, so editing application code does not
# reinstall asyncpg and friends on every build.
COPY pyproject.toml ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv venv /opt/venv && \
    VIRTUAL_ENV=/opt/venv uv pip install -r pyproject.toml

# ---------------------------------------------------------------- runtime ----
FROM python:3.12-slim-bookworm AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH" \
    VIRTUAL_ENV=/opt/venv

# curl is used by the compose healthcheck; tini reaps zombie processes and
# forwards SIGTERM so Celery and uvicorn shut down gracefully (SPEC §10).
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl tini && \
    rm -rf /var/lib/apt/lists/*

# Run as an unprivileged user: a collector that fetches arbitrary attacker-
# influenced URLs should not be root inside its container.
RUN groupadd --system --gid 1001 hayabusa && \
    useradd --system --uid 1001 --gid hayabusa --create-home hayabusa

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
COPY --chown=hayabusa:hayabusa alembic.ini ./
COPY --chown=hayabusa:hayabusa alembic ./alembic
COPY --chown=hayabusa:hayabusa app ./app
COPY --chown=hayabusa:hayabusa docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# The uploads directory must exist and be writable by the unprivileged user
# before the volume is mounted. A named volume mounts over this path with the
# same ownership if the directory already exists; without it, Docker creates it
# as root and logo writes fail (DECISIONS.md D-009).
RUN mkdir -p /app/uploads && chown -R hayabusa:hayabusa /app/uploads

USER hayabusa

EXPOSE 8000

ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
