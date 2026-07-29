# HAYABUSA

Self-hosted threat intelligence, third-party risk, and external attack surface monitoring for a
financial-institution security team.

**Build status: Phase 0 (Foundation) complete.** See [SPEC.md](SPEC.md) §12 for the phase plan and
[DECISIONS.md](DECISIONS.md) for design decisions and their rationale.

---

## Quick start

```bash
python scripts/gen_secrets.py
```

```bash
docker compose up -d
```

| Service | URL |
|---|---|
| Web console | http://localhost:3000 |
| API docs (Swagger) | http://localhost:8000/api/docs |
| API docs (ReDoc) | http://localhost:8000/api/redoc |
| OpenAPI schema | http://localhost:8000/api/v1/openapi.json |
| Liveness / readiness | http://localhost:8000/health · http://localhost:8000/ready |
| Prometheus metrics | http://localhost:8000/metrics |

`gen_secrets.py` copies `.env.example` to `.env` and generates `APP_SECRET_KEY` and
`APP_ENCRYPTION_KEY`. It never overwrites an existing `.env`.

### Using an existing Postgres instead of the shipped one

The compose file ships a `postgres` service on host port **5433** (not 5432 — see
[DECISIONS.md](DECISIONS.md) D-001). To use a Postgres already running on the host, create the
database and repoint one variable in `.env`:

```bash
psql -U postgres -c "CREATE DATABASE hayabusa;"
```

```
DATABASE_URL=postgresql+asyncpg://postgres:postgres@host.docker.internal:5432/hayabusa
```

Use `localhost` rather than `host.docker.internal` when running the API outside Docker.

---

## Architecture

Every monitoring capability shares one pipeline (SPEC §3). Adding an intel source means writing a
single adapter class — not a new subsystem.

```
                    ┌──────────────────────────────────────────────────────┐
  Browser ──────────▶  web (nginx)                                         │
                    │    • serves the built React SPA                      │
                    │    • reverse-proxies /api and /ws  ── same origin    │
                    └───────────────────────┬──────────────────────────────┘
                                            │
                    ┌───────────────────────▼──────────────────────────────┐
                    │  api (FastAPI + uvicorn)                             │
                    │    routers → services → models                       │
                    └───────┬──────────────────────────────┬───────────────┘
                            │                              │
              ┌─────────────▼────────────┐    ┌────────────▼──────────────┐
              │  postgres 16             │    │  redis 7                  │
              │   • all durable state    │    │   • Celery broker         │
              │   • tsvector full-text   │    │   • RedBeat schedule      │
              │   • pg_trgm fuzzy match  │    │   • rate limits, locks    │
              └─────────────▲────────────┘    └────────────▲──────────────┘
                            │                              │
                    ┌───────┴──────────────────────────────┴───────────────┐
                    │  worker (Celery)          beat (Celery + RedBeat)    │
                    │  queues: collect, enrich, correlate, notify, easm    │
                    └──────────────────────────────────────────────────────┘

  Pipeline:  COLLECT ─▶ NORMALIZE ─▶ ENRICH ─▶ CORRELATE ─▶ EVALUATE ─▶ DELIVER
             adapters    signal      CVSS/EPSS  vendor /     rule        telegram
                         table       KEV, geo   asset match  engine      templates
```

### Repository layout

```
backend/
  app/
    main.py        FastAPI application factory
    config.py      env-driven settings (SPEC §4)
    db.py          async engine, session dependency
    core/          logging, errors, metrics, middleware, redis, context
    models/        SQLAlchemy models — base.py holds the shared mixins
    schemas/       Pydantic request/response models (the frontend's contract)
    api/v1/        one router per domain
    tasks/         Celery app, base task, scheduled tasks
  alembic/         migrations — the DB builds from zero with `alembic upgrade head`
  tests/
frontend/
  src/
    lib/           api client, query client, utils
    components/    ui/ (primitives), layout/ (chrome)
    features/      one folder per screen domain — see FRONTEND_GUIDE.md
    stores/        Zustand stores
    styles/        tokens.css is the ONLY place a colour is defined
    types/         api.gen.ts — generated, never hand-edited
```

Frontend maintenance starts at [frontend/FRONTEND_GUIDE.md](frontend/FRONTEND_GUIDE.md), which is
written for a Python developer and includes a "where do I change X" map.

---

## Development

`make` targets exist for Linux and CI. On Windows, `./make.ps1 <target>` runs the same commands
(DECISIONS.md D-005).

| Task | Command |
|---|---|
| Start the stack | `docker compose up -d` |
| Follow logs | `docker compose logs -f` (add a service name to narrow) |
| Run backend tests | `cd backend && uv run pytest` |
| Lint + typecheck backend | `cd backend && uv run ruff check . && uv run mypy app` |
| Typecheck + lint frontend | `cd frontend && npm run typecheck && npm run lint` |
| Regenerate API types | `cd frontend && npm run types` (API must be running) |
| Apply migrations | `docker compose run --rm api alembic upgrade head` |
| New migration | `docker compose run --rm api alembic revision --autogenerate -m "..."` |

### Hot-reload development

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up
```

Source is bind-mounted, uvicorn runs with `--reload`, and the frontend is served by Vite with HMR
on port 5173 instead of nginx.

### After changing an API schema

The frontend never hand-writes an API type (SPEC §9.0 Rule 0). When a Pydantic schema changes:

```bash
cd frontend && npm run types && npm run typecheck
```

`tsc` will then point at every screen the change affected. That diff is the review signal for a
breaking API change, which is why `src/types/api.gen.ts` is committed.

---

## Operations runbook

### Health and readiness

`/health` is liveness — the process is up. It deliberately touches no dependency, so a database
blip does not cause an orchestrator to restart a healthy API.

`/ready` is readiness — Postgres and Redis are reachable. Returns **503** when either is down, and
reports the last Celery heartbeat.

```bash
curl -s http://localhost:8000/ready
```

### "Collection has stopped"

The scheduler heartbeat is the first thing to check. `/ready` reports it, and the web console shows
it on the system status screen.

| Symptom | Meaning | Action |
|---|---|---|
| `heartbeat: null` | Nothing has ever run | Is `beat` running? `docker compose ps beat` |
| `stale: true`, age climbing | Beat or worker stalled | `docker compose logs beat worker --tail=50` |
| `count` not incrementing | Worker not consuming | Check the `collect` queue depth in Redis |

```bash
docker compose exec redis redis-cli LLEN collect
```

RedBeat keeps the schedule in Redis under `hayabusa:beat:*`. To inspect it:

```bash
docker compose exec redis redis-cli KEYS "hayabusa:beat:*"
```

Beat holds a lock (`hayabusa:beat::lock`) so two beat processes cannot double-fire. If beat was
killed uncleanly, the lock expires on its own within `redbeat_lock_timeout` (60 s).

### Tracing a request through the logs

Every log line carries a `request_id`. It is returned on the `X-Request-ID` response header and
embedded in every problem+json error body, and Celery tasks reuse their task ID as the correlation
ID — so a collection run traces from the HTTP call that triggered it to the delivery it produced.

```bash
docker compose logs api worker | grep '"request_id": "<id>"'
```

Logs are JSON by default. Set `LOG_FORMAT=console` in `.env` for colourised local output.

### Migrations

The api container applies migrations on start (`AUTO_MIGRATE=true`, DECISIONS.md D-002), guarded by
a Postgres advisory lock so replicas cannot race. To gate them behind a release step instead, set
`AUTO_MIGRATE=false` and run them explicitly.

To rebuild the database from zero:

```bash
docker compose down -v && docker compose up -d
```

That deletes the volumes — **all data is destroyed**.

### Metrics

`/metrics` serves Prometheus text. Metric families are declared at import time so they read zero
before their first event rather than being absent (an absent series cannot be alerted on).

| Metric | Use |
|---|---|
| `hayabusa_source_health` | Sources by health state — alert on `failing > 0` |
| `hayabusa_collection_runs_total` | Collection throughput and failure rate |
| `hayabusa_signals_ingested_total` | Post-dedupe ingestion volume |
| `hayabusa_alerts_created_total` | Alert volume by severity |
| `hayabusa_deliveries_total` | Telegram delivery outcomes — alert on `status="failed"` |
| `hayabusa_task_duration_seconds` | Celery task latency |
| `hayabusa_http_request_duration_seconds` | API latency against the SPEC §10 targets |

### Secrets

Telegram bot tokens and source credentials are AES-GCM encrypted at rest with
`APP_ENCRYPTION_KEY` and are never returned by the API — only a masked form plus `has_token`.

**Rotating `APP_ENCRYPTION_KEY` invalidates every stored secret.** There is no re-encryption path
yet; bots and credentials would need re-entering.

The logging pipeline redacts values whose key looks sensitive as a backstop, but that is a safety
net, not permission to log a credential.

---

## Technology

Python 3.12 · FastAPI · Pydantic v2 · SQLAlchemy 2.0 (async, asyncpg) · Alembic · Celery 5 ·
RedBeat · PostgreSQL 16 · Redis 7 · React 18 · TypeScript · Vite · Tailwind CSS v3 · TanStack
Query · nginx · Docker Compose.

Full stack rationale in [SPEC.md](SPEC.md) §2.
