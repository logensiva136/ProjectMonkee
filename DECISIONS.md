# DECISIONS

Design decisions taken while building HAYABUSA, per `SPEC.md` §0 rule 5 and §13.
Newest phase last. Each entry states the choice, the alternatives, and the reason.

---

## Phase 0 — Foundation

### D-001 · Postgres: ship the service, default it to host port 5433

**Choice.** `docker-compose.yml` ships a `postgres:16` service that starts by default, but
publishes to `${POSTGRES_HOST_PORT:-5433}` rather than 5432.

**Why.** SPEC §2 requires both that a shipped `postgres` service exists *and* that the
maintainer's existing dev instance on `localhost:5432` can be used instead. The dev machine
already runs a `postgres:16` container bound to 5432, so publishing the shipped service to the
same port would make `docker compose up` fail outright on a bind conflict — which would break
the §1 definition of done. Defaulting to 5433 keeps "clean machine → `docker compose up -d`"
true while leaving the existing instance untouched. Pointing the stack at the host DB instead is
a one-line `DATABASE_URL` change, documented in `.env.example` and the README.

### D-002 · `AUTO_MIGRATE=true`: the api container runs `alembic upgrade head` on start

**Choice.** The api entrypoint applies migrations before starting uvicorn, guarded by an
advisory lock so concurrent replicas cannot race. Settable to `false`.

**Why.** SPEC §1 requires a single `docker compose up -d` to bring up a working stack on a clean
machine, and §0 rule 3 requires the DB be reproducible from zero with one command. An explicit
`make migrate` step would satisfy neither. The advisory lock (`pg_advisory_lock`) makes it safe
if the api is ever scaled beyond one replica; `AUTO_MIGRATE=false` is available for deployments
that gate schema changes behind a separate release step.

### D-003 · UUIDv7 primary keys via the `uuid6` library, generated in Python

**Choice.** Use the `uuid6` package's `uuid7()` and generate IDs application-side, storing them
in native Postgres `uuid` columns.

**Why.** SPEC §5 mandates UUIDv7. Postgres 16 has no built-in `uuidv7()` (it lands in 18), so
the alternatives were a hand-written PL/pgSQL function or client-side generation. Client-side
wins: the ORM knows the ID before flush (needed for building parent/child graphs and audit rows
in one transaction), it keeps the migration free of stored procedures, and it stays portable if
the DB is ever upgraded. `uuid6` is a small, pure-Python, widely-used implementation — the
"boring library" §0 rule 4 asks for. `uuid-utils` (Rust) is faster but ID generation is nowhere
near a bottleneck here.

### D-004 · `uv` for Python dependency management

**Choice.** `uv` with a locked `pyproject.toml`, in both the Docker build and host-side tooling.

**Why.** It is already installed on the dev machine, it resolves and installs an order of
magnitude faster than pip (materially shortens the Docker build loop across eight phases), and
it can provision the Python 3.12 required by SPEC §2 — the host has only 3.11 and 3.14. It reads
a standard `pyproject.toml`, so nothing about the project is uv-specific and pip remains a
fallback.

**Interpreter pin.** `backend/.python-version` declares `3.12`, and the interpreter is a uv-managed
CPython 3.12.13 rather than anything on the host. Without the pin file the right version was being
chosen incidentally, so a fresh clone could silently land on a different interpreter — plausibly
3.14, which is the host default and an unwise target for a stack resting on asyncpg, greenlet and
Celery. `uv python install` provisions it; no system Python is involved at any point. 3.12 rather
than 3.13 because SPEC §2 fixes it as part of the stack.

### D-005 · Ship `make.ps1` alongside the `Makefile`

**Choice.** Keep the `Makefile` required by SPEC §11, and add a PowerShell script exposing the
same targets.

**Why.** `make` is not installed on the Windows dev machine, so the Makefile alone would be
decorative there. The Makefile remains the canonical definition for CI and Linux; `make.ps1` is
a thin parity wrapper. Both call the same underlying commands, so they cannot drift far.

### D-006 · `/health` and `/ready` are served at the root *and* under `/api/v1`

**Choice.** Register the probe routes at `/health`, `/ready`, `/metrics` (excluded from the
OpenAPI schema) and at `/api/v1/...` (documented).

**Why.** SPEC §7 lists them under the `/api/v1` base, but container healthchecks, nginx and
future load balancers conventionally probe the root path. Serving both costs nothing. The
root-path copies are marked `include_in_schema=False` so the OpenAPI document — which frontend
types are generated from, per §9.0 Rule 0 — stays free of duplicate operations.

### D-007 · `/ready` reports the last Celery heartbeat

**Choice.** The RedBeat-scheduled `heartbeat` task stamps a Redis key each run; `/ready`
surfaces its age as `last_heartbeat`.

**Why.** SPEC §12 Phase 0 requires proof that "a hello-world Celery task runs on schedule". A
task that only logs proves it to whoever reads the logs; stamping Redis makes the beat→broker→
worker loop observable over HTTP and gives the Phase 0 acceptance check a real assertion. It
also becomes a genuine liveness signal for the collector once §8's scheduled tasks land — a
stalled beat is otherwise silent.

### D-008 · Structured logging with `structlog`, request-ID correlation via middleware

**Choice.** `structlog` renders JSON in all environments by default (`LOG_FORMAT=console` for
local readability). A middleware assigns each request a UUIDv7 request ID, honours an inbound
`X-Request-ID`, binds it to a `contextvar`, and echoes it on the response.

**Why.** SPEC §2 fixes structlog and §10 requires "structured JSON logs with a request-ID
correlation header". Using a contextvar means the ID reaches log lines emitted deep in the
service layer without threading a parameter through every call — and the same binding mechanism
works for Celery tasks, so a collection run can be traced end to end.

### D-009 · Frontend `.env`-free API base URL

**Choice.** The frontend always calls the relative path `/api/v1`; nginx proxies it to the api
service. Vite's dev server proxies the same path.

**Why.** Baking an absolute API URL into the bundle at build time means the same image cannot be
promoted between environments, and it needs CORS. A relative path is same-origin in every
deployment, removes CORS from the critical path, and keeps the browser's cookie — which §6.2
requires be `SameSite=Strict` — working without exception. This is also the simplest thing for a
Python maintainer to reason about (§9.0).

### D-014 · Security headers live in an included nginx snippet, repeated per location

**Choice.** `frontend/security-headers.conf` holds the header set; `nginx.conf` includes it in the
server block *and* in every location block that defines an `add_header` of its own.

**Why.** Found by testing rather than by design. nginx inherits `add_header` into a nested block
only if that block declares no `add_header` itself — one `add_header Cache-Control ...` inside a
location silently discards every header from the parent. Because `try_files ... /index.html`
re-matches locations internally, the main HTML document was being served from
`location = /index.html` with **no Content-Security-Policy at all** — the one response where CSP
matters most. nginx offers no inheritance mechanism that avoids the repetition, so the snippet is
included explicitly and the reason is documented at the top of the file so nobody "tidies it away".

### D-015 · One `tsconfig.json`, not the Vite starter's two

**Choice.** A single `tsconfig.json` covering `src/` and `vite.config.ts`, with `@types/node`.

**Why.** The Vite React-TS starter splits config into `tsconfig.json` + `tsconfig.node.json` joined
by a project reference. That combination fails under TypeScript 5.7 with TS6310 ("referenced
project may not disable emit"), because a composite project cannot set `noEmit`. The fixes are
either emitting declarations nobody consumes, or collapsing to one file. One config file is less
machinery for a maintainer who does not work in TypeScript daily (SPEC §9.0), so it collapsed.

### D-016 · `src/types/api.gen.ts` is committed, not gitignored

**Choice.** The generated API types are tracked in git.

**Why.** `tsc`, `eslint` and CI must run without a live backend, which a generated-at-build-time
file would prevent. More usefully, the diff on that file is the review signal for a breaking API
change: a renamed or newly-optional field shows up in the pull request instead of surfacing as a
runtime error later. It is regenerated with `npm run types` and never edited by hand.

---

## Phase 1 — Identity

### D-017 · Security state written on a failure path is committed explicitly

**Choice.** `authenticate` and `rotate_refresh_token` call `session.commit()` *before* raising.

**Why.** Found by testing, and it disarmed two controls completely. The `get_session`
dependency rolls back when a handler raises — correct for ordinary writes, catastrophic here. The
failed-login counter was incremented and then rolled back along with the 401, so it reset on every
attempt and no account could ever lock. The identical fault silently defeated refresh-token replay
detection: the family revocation was undone by the very error that reported it, leaving the stolen
session working. Both now commit before raising, with the reason stated at each site so nobody
"tidies away" what looks like a stray commit.

### D-018 · Permissions are read from the database per request, not embedded in the JWT

**Choice.** The access token carries only a subject. Roles and permissions are loaded on each
request.

**Why.** Embedding them makes revocation lag by the token lifetime: removing someone's role would
leave it working for up to 15 minutes. Loading costs one indexed query against rows already cached
by Postgres, and makes revocation immediate — which is what an operator expects when they strip
access during an incident. Revisit only if profiling shows it matters.

### D-019 · The setup gate is middleware, not a router dependency

**Choice.** SPEC §6.1's "all other routes return 409" is enforced by middleware.

**Why.** A dependency must be remembered on every new router, and the one time it is forgotten is
the time an un-onboarded instance exposes an endpoint. Middleware covers routes that do not exist
yet — including the seven phases still to come. Testing also caught that a bare `/api/v1/setup`
prefix match exempted `/api/v1/setupx`; the exemption is now a path-segment match.

### D-020 · Silent token refresh is deduplicated to a single in-flight request

**Choice.** `refreshAccessToken()` in `frontend/src/lib/api.ts` shares one promise across callers.

**Why.** Not an optimisation — a correctness requirement created by D-017's replay detection. A
screen firing six queries at once would send six refreshes; the first rotates the token and the
other five present the now-revoked one, which the backend correctly reads as theft and responds to
by revoking the family. The user would be signed out at random by their own dashboard.

### D-021 · Recovery codes are shown after completion, not inside wizard step 4

**Choice.** Step 4 gates on a valid TOTP code via `POST /setup/verify-totp`; the ten codes are
displayed on a final screen after `/setup/complete` returns them, behind an acknowledgement
checkbox.

**Why.** SPEC §6.1 step 4 asks for both a verified code and the codes displayed with an
acknowledgement. The codes can only be generated server-side — letting the client supply them
would let it choose its own — and nothing is persisted until the atomic submit. Splitting the two
keeps the code gate real (a bad code cannot advance) without either weakening code generation or
persisting a half-enrolled account. `/setup/verify-totp` stores nothing; `/setup/complete`
re-verifies a fresh code before storing the secret, so it remains the enforcement point.

---

## §13 open choices

These are the four choices SPEC §13 explicitly delegates. Recorded now; each is revisited in the
phase that first needs it.

### D-010 · Nth-party graph rendering: **React Flow** (`@xyflow/react`) — *decided, used in Phase 5*

Over `d3-force`. The vendor graph is a directed acyclic parent→child hierarchy of maybe tens to
low hundreds of nodes, not an organic force cluster. React Flow gives pan/zoom, node selection,
edge routing, and a minimap declaratively, as React components — whereas `d3-force` would mean
imperative DOM manipulation inside a `useEffect`, which is exactly the React idiom SPEC §9.0
says the Python-fluent maintainer will struggle to debug. Deterministic layout also makes a
4th-party's path to its 1st-party parent stable between renders, which §5.4 requires be obvious.

### D-011 · Full-text search: **Postgres `tsvector`** — *decided, used from Phase 2*

Over Meilisearch. SPEC §14 requires asking before adding a datastore beyond Postgres + Redis, and
the §10 target (signal list < 300 ms p95 at 1 M rows) is comfortably within reach of a GIN index
on a generated `tsvector` column. Avoiding a second datastore also avoids an index-sync problem
and a second backup surface. Revisit only if measured p95 misses the target.

### D-012 · Scheduler: **`celery-redbeat`** — *decided, used in Phase 0*

Over a custom DB-backed beat scheduler. SPEC §2 already fixes RedBeat, and it stores the schedule
in Redis where it can be mutated at runtime — which is what §8's `dispatch_due_sources` and
per-source intervals need. A custom scheduler would be new code on the critical path for every
collection, against §0 rule 4. Note that per-source polling is driven by `next_poll_at` in
Postgres and dispatched by a fixed 60 s RedBeat entry, so RedBeat holds few entries and Redis
being non-durable for the schedule is not a data-loss risk.

### D-013 · Template editor: **CodeMirror 6** — *decided, used in Phase 3*

Over Monaco. Monaco is roughly 2 MB gzipped and pulls in a web-worker build setup that
complicates the Vite config; CodeMirror 6 is ~200 KB, has first-class Jinja-ish highlighting via
its StreamLanguage legacy modes, and mounts as a plain React component. The template editor needs
syntax highlighting, a variable palette insert, and bracket matching — not IntelliSense. The
lighter build also keeps the §9.0 maintainability bar: less Vite configuration to debug.
