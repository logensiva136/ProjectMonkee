# BUILD PROMPT — "HAYABUSA" Threat & Attack Surface Monitoring Platform

> Paste this whole file as the opening prompt to your coding agent (Claude Code / Cursor / Codex).
> Keep it in the repo root as `SPEC.md` afterwards so the agent can re-read it between sessions.

---

## 0. Role & Objective

You are a senior full-stack engineer with a security-engineering background. Build **HAYABUSA**, a
self-hosted threat intelligence, third-party risk, and external attack surface monitoring platform
for a financial-institution security team.

**The deliverable is a complete, deployable, running system — not a scaffold.**

Rules of engagement:

1. **No pseudocode, no `# TODO: implement`, no stubbed functions.** Every endpoint, worker task, and
   UI screen you create must actually work end to end before you move to the next item.
2. Work in the **phases** defined in §12. Do not start a phase until the previous phase's acceptance
   criteria pass. After each phase, run the stack and report what works.
3. Write migrations as you go (Alembic). The DB must be reproducible from zero with one command.
4. Prefer boring, proven libraries over clever ones.
5. When a design decision is ambiguous and low-stakes, **decide and document it** in `DECISIONS.md`.
   Only stop and ask me when the choice is expensive to reverse.
6. Commit in small, logical commits with meaningful messages.

---

## 1. Definition of Done

- `docker compose up -d` on a clean machine brings up the full stack.
- Browsing to `http://localhost:3000` on a fresh DB shows the **admin onboarding wizard**.
- After onboarding, the operator can: add an RSS source, wait for (or trigger) a collection run,
  see items appear, create a rule, and receive a formatted Telegram message from a bot they
  configured in the UI — **without touching a config file or the database**.
- All of §5–§10 implemented.
- `pytest` suite green; `ruff` and `mypy` clean; frontend `tsc --noEmit` and `eslint` clean.
- `README.md` with setup, architecture diagram, and operations runbook.
- `frontend/FRONTEND_GUIDE.md` per §9.0 Rule 5, and every §9.0 constraint respected — verify this by
  re-reading your own frontend code before declaring the phase complete.

---

## 2. Fixed Technology Stack

**Backend**
- Python 3.12
- FastAPI + Pydantic v2
- SQLAlchemy 2.0 (async, `asyncpg`) + Alembic
- Celery 5 + Redis (broker + result backend); **RedBeat** for a DB/Redis-driven dynamic schedule
- `httpx` (async) for all outbound HTTP, `feedparser` for RSS/Atom, `Jinja2` for templates
- `argon2-cffi` (password hashing), `pyotp` + `qrcode` (TOTP), `python-jose` (JWT),
  `cryptography` (AES-GCM secret encryption), `zxcvbn` (password strength)
- `structlog` for JSON logs

**Frontend**
- React 18 + TypeScript + Vite — **but see §9.0: the maintainer is a Python developer, and the
  TypeScript you write is restricted to a deliberately small subset.**
- Tailwind CSS v3 + shadcn/ui (Radix primitives)
- TanStack Query (server state) + Zustand (small UI state)
- React Router v6, React Hook Form + Zod
- Recharts (charts), lucide-react (icons), `cmdk` (command palette), `sonner` (toasts)

**Infrastructure**
- PostgreSQL 16 — dev instance already exists at `localhost:5432`, user `postgres`, password
  `postgres`. **Create a new database named `hayabusa`.** Ship a `postgres` service in
  `docker-compose.yml` too, but make the host/port fully env-driven so my dev DB can be used.
- Redis 7
- Nginx serving the built frontend and reverse-proxying `/api`
- Docker Compose services: `postgres`, `redis`, `api`, `worker`, `beat`, `web`

---

## 3. Core Architectural Spine

Every monitoring capability must reuse **one pipeline**. Do not build five parallel silos.

```
COLLECT  ->  NORMALIZE  ->  ENRICH  ->  CORRELATE  ->  EVALUATE  ->  DELIVER
(source    (into the      (CVSS,      (vendor /     (rule        (telegram
 adapters)  `signal`       EPSS, KEV,   asset /       engine ->    templates ->
            table)         geo, tech)   component     `alert`)     `delivery`)
                                        matching)
```

- A **source adapter** is a class implementing `fetch() -> list[RawItem]`. Register adapters by
  `source.type`. Adding a new intel source = writing one adapter class, nothing else.
- Everything collected becomes a row in `signal` with a `kind` discriminator
  (`news`, `advisory`, `cve`, `package_event`, `easm_change`) plus a typed detail table.
- The **rule engine** and the **Telegram delivery layer** are domain-agnostic and serve all modules.

---

## 4. Configuration

`.env.example` (all values env-driven, no hardcoded secrets):

```
APP_NAME=HAYABUSA
APP_ENV=development
APP_TIMEZONE=Asia/Kuala_Lumpur
APP_SECRET_KEY=              # JWT signing
APP_ENCRYPTION_KEY=          # 32-byte urlsafe-base64, AES-GCM for bot tokens/API keys at rest

DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/hayabusa
REDIS_URL=redis://localhost:6379/0

DEFAULT_POLL_INTERVAL_SECONDS=10800     # 3 hours
HTTP_USER_AGENT=HAYABUSA-Collector/1.0
HTTP_TIMEOUT_SECONDS=30
COLLECTOR_CONCURRENCY=8

NVD_API_KEY=                 # optional, raises NVD rate limit
GITHUB_TOKEN=                # optional, for releases/advisories

ACCESS_TOKEN_TTL_MINUTES=15
REFRESH_TOKEN_TTL_DAYS=7
```

**Secret handling:** Telegram bot tokens and any source credentials are stored AES-GCM encrypted
using `APP_ENCRYPTION_KEY`. They are **never** returned by the API — return a masked form
(`123456789:AAE••••••••xyz`) plus a `has_token: true` flag.

---

## 5. Data Model

Use UUIDv7 primary keys, `created_at`/`updated_at` on every table, soft delete
(`deleted_at`) where records are referenced historically. All timestamps `timestamptz` in UTC;
render in `APP_TIMEZONE` in the UI.

### 5.1 Identity, RBAC, App

| Table | Key columns |
|---|---|
| `app_setting` | singleton row: `org_name`, `org_logo_path`, `org_initials`, `brand_color`, `timezone`, `setup_completed_at` |
| `user` | `full_name`, `username` (uniq, citext), `email` (uniq, citext), `password_hash`, `is_active`, `must_change_password`, `totp_secret_encrypted`, `totp_enabled`, `last_login_at`, `failed_login_count`, `locked_until` |
| `recovery_code` | `user_id`, `code_hash`, `used_at` |
| `role` | `key`, `name`, `description`, `is_system` |
| `permission` | `key` (`vendor:write`), `resource`, `action`, `description` |
| `role_permission` | `role_id`, `permission_id` |
| `user_role` | `user_id`, `role_id` |
| `panel` | `key`, `name`, `route`, `icon`, `nav_group`, `sort_order` |
| `role_panel` | `role_id`, `panel_key`, `can_view` — drives sidebar visibility |
| `refresh_token` | `user_id`, `token_hash`, `expires_at`, `revoked_at`, `user_agent`, `ip` |
| `audit_log` | `actor_id`, `action`, `entity_type`, `entity_id`, `before` jsonb, `after` jsonb, `ip`, `ua`, `created_at` |

### 5.2 Sources & Collection

| Table | Key columns |
|---|---|
| `source_category` | `name`, `slug`, `color`, `icon`, `parent_id` (self FK, 2 levels max), `sort_order`, `is_system` |
| `source` | `name`, `type` (enum below), `url`, `category_id`, `poll_interval_seconds` (default from env), `enabled`, `config` jsonb (adapter-specific), `credentials_encrypted`, `etag`, `last_modified`, `last_polled_at`, `next_poll_at`, `last_status`, `consecutive_failures`, `health` (`healthy`/`degraded`/`failing`), `default_severity`, `tags[]` |
| `source_run` | `source_id`, `started_at`, `finished_at`, `status`, `http_status`, `items_seen`, `items_new`, `duration_ms`, `error` |
| `signal` | `source_id`, `kind`, `external_id`, `title`, `url`, `summary`, `content`, `author`, `published_at`, `collected_at`, `content_hash`, `raw` jsonb, `severity_hint`, `language` — **UNIQUE(source_id, external_id)**, plus unique index on `content_hash` for cross-source dedupe |
| `signal_tag` | `signal_id`, `tag` |

`source.type` enum: `rss`, `atom`, `json_feed`, `html_advisory`, `nvd`, `cisa_kev`, `epss`,
`osv`, `github_releases`, `github_advisory`, `endoflife`, `crtsh`, `custom_webhook`.

Categories are **fully CRUD-able** including system ones (system categories can be renamed/recoloured
but not deleted while in use). Suggested seed: `Threat Intel`, `Regulatory` (BNM/RMiT, MAS, PCI DSS,
EU DORA), `Vendor Advisory`, `Vulnerability`, `Breach & Incident`, `Malware & Ransomware`,
`Ecosystem/Tech Stack`, `Local (Malaysia)`.

### 5.3 CVE & Vulnerability

| Table | Key columns |
|---|---|
| `cve` | `cve_id` (PK, text), `published_at`, `modified_at`, `description`, `cvss_v31_vector`, `cvss_v31_score`, `cvss_v40_vector`, `cvss_v40_score`, `severity`, `cwe[]`, `references` jsonb, `is_kev`, `kev_added_at`, `kev_due_at`, `kev_ransomware`, `epss_score`, `epss_percentile`, `epss_updated_at`, `has_public_exploit`, `raw` jsonb |
| `cve_cpe` | `cve_id`, `cpe23`, `vendor`, `product`, `version_start_incl/excl`, `version_end_incl/excl` |
| `cve_watchlist` | `name`, `description`, `enabled`, `owner_id`, `min_cvss`, `min_epss`, `kev_only`, `notify_on_modify` |
| `cve_watchlist_criterion` | `watchlist_id`, `match_type` (`vendor`/`product`/`cpe`/`keyword`/`regex`), `value` |
| `cve_watchlist_hit` | `watchlist_id`, `cve_id`, `matched_criteria[]`, `matched_at`, `alerted` |

Collectors: **NVD 2.0** (incremental via `lastModStartDate`, respect rate limits, backoff),
**CISA KEV** (daily JSON), **FIRST EPSS** (daily CSV), **GitHub Security Advisories** (optional).

### 5.4 Vendors / Nth-Party (TPRM)

| Table | Key columns |
|---|---|
| `vendor` | `name`, `legal_name`, `party_tier` (int, 1..n), `parent_vendor_id` (self FK → forms the nth-party chain), `vendor_class` (`service_provider`/`security_tool`/`cloud`/`fintech`/`other`), `criticality` (`critical`/`high`/`medium`/`low`), `status`, `country`, `business_owner`, `contract_ref`, `onboarded_at`, `notes` |
| `vendor_alias` | `vendor_id`, `alias` |
| `vendor_keyword` | `vendor_id`, `keyword`, `is_regex`, `weight`, `require_word_boundary` — **GIN index** on a generated `tsvector`; also a trigram index for fuzzy fallback |
| `vendor_domain` | `vendor_id`, `domain`, `is_primary` |
| `vendor_source` | `vendor_id`, `source_id` — links a vendor to its own advisory/PSIRT feed |
| `vendor_match` | `signal_id`, `vendor_id`, `score`, `matched_terms[]`, `matched_at`, `confirmed_by`, `is_false_positive` |
| `vendor_cve_exposure` | `vendor_id`, `cve_id`, `status`, `assessed_by`, `assessment_notes` |

**Matching engine:** normalize signal text → keyword/alias/domain match with word-boundary
enforcement → score = Σ(weights) with title matches weighted 2×. Persist a `vendor_match` row.
Expose a **false-positive feedback loop**: marking a match FP adds a negative-keyword rule.

**Nth-party visualization:** the vendor register UI must render the parent→child chain as an
expandable tree AND a graph view, so a 4th-party dependency of a critical 1st-party is obvious.

Requirement #4 (F5, Fortinet, Cisco, Palo Alto, Ivanti, Citrix, VMware, Microsoft, Atlassian…) is
**not a separate module** — it is `vendor.vendor_class = 'security_tool'` with a linked PSIRT
`source`. Seed ~20 of these with their real advisory feed URLs.

### 5.5 Tech Stack / Ecosystem Monitoring

| Table | Key columns |
|---|---|
| `tech_component` | `name`, `ecosystem` (`npm`/`pypi`/`golang`/`maven`/`nuget`/`docker`/`github`/`os`/`saas`), `package_name`, `current_version`, `version_constraint`, `environment` (`prod`/`uat`/`dev`), `repository_url`, `eol_product_slug`, `owner`, `criticality`, `enabled` |
| `component_event` | `component_id`, `kind` (`new_release`/`vulnerability`/`eol_announced`/`eol_reached`/`deprecated`/`yanked`), `detail` jsonb, `detected_at`, `alerted` |
| `component_vulnerability` | `component_id`, `cve_id`, `osv_id`, `affected_range`, `fixed_version`, `is_affected` (computed against `current_version`), `status`, `remediated_at` |

Collectors: **OSV.dev** batch query API (primary vuln source for npm/PyPI/Go/etc.),
**GitHub Releases** API, **endoflife.date** API. Version comparison must be ecosystem-aware
(semver for npm, PEP 440 for PyPI) — use `packaging` and a semver lib, don't string-compare.

Seed: `node`, `npm`, `react`, `next`, `python`, `django`, `fastapi`, `celery`, `postgresql`,
`redis`, `nginx`, `docker`, `twingate`.

### 5.6 EASM

| Table | Key columns |
|---|---|
| `asset_scope` | `name`, `description`, `is_authorized` (bool), `authorized_by`, `authorized_at`, `authorization_ref`, `allow_active_scanning` (bool), `rate_limit_rps` |
| `asset` | `scope_id`, `type` (`domain`/`subdomain`/`ip`/`cidr`/`url`/`certificate`/`service`/`asn`/`cloud_bucket`), `value`, `parent_asset_id`, `first_seen_at`, `last_seen_at`, `status` (`active`/`inactive`/`retired`), `discovery_source`, `criticality`, `owner`, `tags[]`, `is_approved` — **UNIQUE(scope_id, type, value)** |
| `asset_snapshot` | `asset_id`, `taken_at`, `data` jsonb, `data_hash` |
| `asset_change` | `asset_id`, `change_type`, `before` jsonb, `after` jsonb, `detected_at`, `severity`, `alerted` |
| `port_service` | `asset_id`, `port`, `protocol`, `state`, `service`, `product`, `version`, `banner`, `tls`, `first_seen_at`, `last_seen_at` |
| `certificate` | `asset_id`, `sha256`, `subject_cn`, `issuer`, `san[]`, `not_before`, `not_after`, `is_wildcard`, `is_self_signed`, `days_to_expiry` (generated) |
| `dns_record` | `asset_id`, `record_type`, `value`, `ttl`, `first_seen_at`, `last_seen_at` |
| `http_probe` | `asset_id`, `url`, `status_code`, `title`, `server_header`, `technologies[]`, `content_hash`, `screenshot_path`, `probed_at` |
| `easm_scan_job` | `scope_id`, `job_type`, `status`, `started_at`, `finished_at`, `stats` jsonb, `error`, `triggered_by` |

`change_type` values: `asset_discovered`, `asset_disappeared`, `port_opened`, `port_closed`,
`service_version_changed`, `dns_record_added/removed/changed`, `certificate_changed`,
`certificate_expiring`, `certificate_expired`, `http_status_changed`, `title_changed`,
`technology_added/removed`, `whois_changed`, `subdomain_takeover_suspected`.

**Authorization gate (mandatory):** any active probing (DNS resolution beyond passive, HTTP probing,
port scanning) is blocked unless `asset_scope.is_authorized AND allow_active_scanning`. Enforce this
in the service layer, not just the UI, and log every scan job with `triggered_by`. Passive discovery
(crt.sh certificate transparency, passive DNS) is allowed on any scope.

**Discovery/probing implementation:** implement in pure Python first (`dnspython`, `httpx`,
`cryptography` for TLS parsing, crt.sh JSON API, `python-whois`). Design a `ProbeAdapter` interface
so ProjectDiscovery binaries (`subfinder`, `httpx`, `naabu`) can be plugged in later via subprocess
if present on PATH — detect availability at runtime and degrade gracefully.

**Change detection:** each scan writes an `asset_snapshot`; diff against the previous snapshot and
emit `asset_change` rows. Changes become `signal` rows with `kind='easm_change'` so the rule engine
sees them like everything else.

### 5.7 Rules & Alerts

| Table | Key columns |
|---|---|
| `rule` | `name`, `description`, `domain` (`signal`/`cve`/`vendor_match`/`component_event`/`easm_change`/`any`), `condition` jsonb (AST), `severity`, `enabled`, `dedupe_window_minutes`, `max_alerts_per_hour`, `priority`, `is_system`, `created_by` |
| `rule_action` | `rule_id`, `action_type` (`telegram`/`webhook`/`tag`/`assign`), `destination_id`, `template_id`, `sort_order` |
| `rule_test_run` | `rule_id`, `sample_input` jsonb, `matched`, `explanation`, `run_at` |
| `alert` | `rule_id`, `severity`, `title`, `context` jsonb, `entity_type`, `entity_id`, `fingerprint` (uniq within dedupe window), `status` (`new`/`acknowledged`/`resolved`/`suppressed`), `created_at`, `acknowledged_by`, `acknowledged_at`, `resolved_at` |
| `alert_note` | `alert_id`, `author_id`, `body` |

**Condition AST** — JSON, serializable, editable both as a visual builder and as raw JSON:

```json
{
  "op": "AND",
  "children": [
    { "op": "OR", "children": [
      { "field": "cve.is_kev",     "operator": "eq",  "value": true },
      { "field": "cve.epss_score", "operator": "gte", "value": 0.5 }
    ]},
    { "field": "cve.cvss_v31_score", "operator": "gte", "value": 8.0 },
    { "field": "vendor.criticality", "operator": "in",  "value": ["critical", "high"] }
  ]
}
```

Operators: `eq`, `neq`, `gt`, `gte`, `lt`, `lte`, `in`, `not_in`, `contains`, `not_contains`,
`starts_with`, `regex`, `exists`, `changed`, `changed_to`, `within_days`.
Ship a **field registry** per domain so the UI builder can offer typed fields with autocomplete.
Ship a **rule tester**: paste/select a real historical entity, see match + per-node evaluation trace.

### 5.8 Telegram Delivery

| Table | Key columns |
|---|---|
| `telegram_bot` | `name`, `token_encrypted`, `bot_username`, `enabled`, `last_verified_at`, `verify_status` |
| `telegram_destination` | `bot_id`, `label`, `chat_id`, `message_thread_id` (nullable, for forum topics), `enabled`, `is_default`, `silent_hours` (jsonb: quiet-hours window in `APP_TIMEZONE`) |
| `message_template` | `name`, `key`, `domain`, `parse_mode` (`HTML`/`MarkdownV2`), `body` (Jinja2), `is_default`, `active_version_id` |
| `message_template_version` | `template_id`, `version`, `body`, `parse_mode`, `created_by`, `created_at`, `change_note` |
| `delivery` | `alert_id`, `destination_id`, `template_id`, `template_version`, `status` (`queued`/`sending`/`sent`/`failed`/`suppressed`), `attempts`, `rendered_body`, `telegram_message_id`, `error`, `queued_at`, `sent_at` |

Requirements:
- **Templates are fully managed in the UI**: Monaco/CodeMirror editor with Jinja2 syntax highlighting,
  a **variable palette** sidebar (click to insert) generated from the domain's field registry,
  **live preview** rendered against a sample or real entity, **version history with diff and
  rollback**, and a **"Send test to destination"** button.
- Sandboxed Jinja2 (`SandboxedEnvironment`), template rendering errors must never kill the worker —
  fall back to a plain-text default template and flag the delivery.
- Provide custom Jinja filters: `severity_emoji`, `truncate_smart`, `tg_escape`, `localtime`,
  `humanize_delta`, `cvss_bar`.
- **Rate limiting & retry**: respect Telegram's ~30 msg/s global and ~20 msg/min per group limits.
  Token-bucket limiter in Redis. On HTTP 429 honour `retry_after`. Exponential backoff, 5 attempts,
  then `failed` with the error persisted and surfaced in the UI.
- Message length > 4096 chars → split intelligently or truncate with a "view in HAYABUSA" deep link.
- Quiet hours: `low`/`medium` alerts queue until the window ends; `critical` always sends immediately.
- Do **not** use a Merge-node-style fan-in pattern; deliveries are independent queued tasks per
  destination.

Ship default templates for each domain, e.g.:

```jinja
{{ alert.severity | severity_emoji }} <b>{{ alert.title | tg_escape }}</b>

<b>Vendor:</b> {{ vendor.name }} (Tier {{ vendor.party_tier }} · {{ vendor.criticality | upper }})
<b>CVE:</b> <code>{{ cve.cve_id }}</code> · CVSS {{ cve.cvss_v31_score }}{% if cve.is_kev %} · <b>KEV</b>{% endif %}
<b>EPSS:</b> {{ '%.1f' | format(cve.epss_score * 100) }}%

{{ cve.description | truncate_smart(400) | tg_escape }}

<a href="{{ signal.url }}">Source</a> · <a href="{{ app.url }}/alerts/{{ alert.id }}">Open in HAYABUSA</a>
<i>{{ alert.created_at | localtime }}</i>
```

---

## 6. Authentication, Onboarding & RBAC

### 6.1 First-run onboarding wizard

`GET /api/v1/setup/status` (unauthenticated) → `{ "needs_setup": true|false }`.
While `needs_setup`, **all other API routes except `/setup/*` and `/health` return 409**, and the
frontend hard-redirects to `/setup`. Once complete, `/setup/*` returns 410 forever.

Wizard steps (single page, stepper UI, state kept client-side until final atomic submit):

1. **Identity** — full name, username (3–32, `^[a-z0-9._-]+$`), email (validated).
2. **Organisation** — company name (optional), logo upload (optional; PNG/JPG/SVG/WebP, ≤2 MB,
   validate magic bytes not just extension, strip EXIF, resize to 512×512).
   - If no logo: **generate a deterministic SVG monogram avatar.** Initials = company abbreviation
     (first letter of each significant word, max 3, ignoring "Sdn Bhd", "Berhad", "Inc", "Ltd") or,
     if no company, the user's initials. Background colour derived from a hash of the name.
3. **Password** — min 12 chars, must contain 3 of 4 character classes, `zxcvbn` score ≥ 3, checked
   against a bundled common-password list, must not contain username/email local part. Live strength
   meter with actionable feedback.
4. **Two-factor (mandatory)** — generate TOTP secret, render QR (`otpauth://totp/HAYABUSA:{username}?issuer=HAYABUSA`),
   show the secret in copyable Base32, **require a valid 6-digit code to proceed**, then display
   **10 single-use recovery codes** with copy/download and a "I have saved these" checkbox.
5. **Review & finish** — atomic transaction: create `user`, assign `super_admin` role, write
   `app_setting`, seed roles/permissions/panels/categories/default templates, set
   `setup_completed_at`, write audit log, auto-login.

### 6.2 Auth

- Argon2id, `time_cost=3, memory_cost=65536, parallelism=4`.
- Login → if `totp_enabled`, return a short-lived (5 min) `mfa_token`, then `POST /auth/mfa/verify`.
- Access JWT 15 min (in memory), refresh token 7 days in an **HttpOnly, Secure, SameSite=Strict**
  cookie, **rotated on every use** with reuse detection (reuse → revoke the whole family + alert).
- Rate limit: 5 failed logins per username per 15 min → 15-minute lockout; per-IP limit as well.
- Recovery codes accepted in place of a TOTP code, single-use, hashed at rest.
- Sessions page: list active sessions, revoke individually or all.

### 6.3 RBAC

- Permissions are `resource:action` strings: `source:read`, `source:write`, `vendor:write`,
  `cve:read`, `easm:scan`, `easm:approve_scope`, `rule:write`, `telegram:write`, `template:write`,
  `alert:acknowledge`, `user:manage`, `role:manage`, `settings:manage`, `audit:read`.
- Seed roles: **Super Admin** (all), **Security Analyst** (read all + acknowledge alerts + manage
  watchlists/rules), **TPRM Officer** (vendor + alerts read/write, no EASM scanning),
  **Viewer** (read-only, dashboards only).
- Custom roles are creatable, with a permission matrix UI (checkbox grid grouped by resource).
- **Panel visibility:** admin toggles `role_panel.can_view` per role. `GET /api/v1/me` returns
  `{ user, roles, permissions[], panels[] }`; the frontend builds the sidebar and route guards
  purely from this. **The backend enforces permissions independently** — hiding a panel is UX, not
  security.
- Every mutating endpoint declares its permission via a FastAPI dependency
  (`Depends(require("vendor:write"))`).

---

## 7. API Surface

Base `/api/v1`. OpenAPI at `/api/docs`. Consistent envelope, cursor pagination
(`?limit=&cursor=`), consistent filter/sort query params, RFC 7807 problem+json errors.

```
/health  /ready  /metrics                  (Prometheus text)
/setup/status  /setup/complete  /setup/logo
/auth/login  /auth/mfa/verify  /auth/refresh  /auth/logout  /auth/sessions
/auth/password/change  /auth/2fa/reset (admin)  /auth/recovery-codes/regenerate
/me
/users  /roles  /permissions  /panels  /audit-logs  /settings
/source-categories                          CRUD + reorder
/sources                                    CRUD + /{id}/test  /{id}/poll  /{id}/runs  /import-opml  /export-opml
/signals                                    list/search/filter, /{id}, /{id}/tags
/cves                                       list/search, /{id}
/cve-watchlists                             CRUD + /{id}/hits  /{id}/preview
/vendors                                    CRUD + /tree  /graph  /{id}/matches  /{id}/exposures  /import (CSV/XLSX)
/vendors/{id}/keywords                      CRUD + bulk
/vendor-matches/{id}/feedback               mark FP / confirm
/tech-components                            CRUD + /import (package.json, requirements.txt, poetry.lock, SBOM/CycloneDX)
/tech-components/{id}/events
/easm/scopes                                CRUD + /{id}/authorize
/easm/assets                                CRUD + bulk import + /{id}/history  /{id}/snapshots
/easm/changes                               list/filter/ack
/easm/scans                                 POST start, GET status, POST cancel
/rules                                      CRUD + /{id}/test  /{id}/enable  /field-registry/{domain}
/alerts                                     list + /{id}  /{id}/acknowledge  /{id}/resolve  /{id}/notes  /bulk
/telegram/bots                              CRUD + /{id}/verify
/telegram/destinations                      CRUD + /{id}/test-send
/templates                                  CRUD + /{id}/preview  /{id}/versions  /{id}/rollback  /{id}/test-send
/deliveries                                 list + /{id}/retry
/dashboard/summary  /dashboard/timeline  /dashboard/top-vendors  /dashboard/severity-breakdown
/ws/events                                  WebSocket: live alerts, scan progress, collection runs
```

---

## 8. Scheduling & Workers

Celery queues: `collect`, `enrich`, `correlate`, `notify`, `easm`.

| Task | Schedule |
|---|---|
| `dispatch_due_sources` | every 60 s — selects sources where `next_poll_at <= now()`, fans out `collect_source` (per-source interval, default 3 h) |
| `collect_source(source_id)` | on demand — conditional GET via ETag/Last-Modified, dedupe, write `signal`, write `source_run`, chain to `enrich` |
| `sync_nvd_incremental` | every 2 h |
| `sync_cisa_kev` | every 6 h |
| `sync_epss` | daily 02:00 |
| `scan_osv_components` | every 6 h |
| `check_github_releases` | every 6 h |
| `check_eol` | daily 03:00 |
| `easm_passive_discovery(scope)` | daily |
| `easm_active_probe(scope)` | every 6 h (authorized scopes only) |
| `easm_cert_expiry_check` | daily 06:00 |
| `evaluate_rules(entity)` | event-driven |
| `deliver(delivery_id)` | event-driven, rate-limited |
| `flush_quiet_hour_queue` | every 15 min |
| `retention_cleanup` | daily 04:00 — configurable retention per table |

Hard rules: idempotent tasks, `acks_late=True`, per-task timeouts, jittered backoff, a Redis lock
per source to prevent overlapping runs, and **circuit breaking** — after 5 consecutive failures a
source flips to `failing`, its interval backs off exponentially (max 24 h), and an internal alert
fires.

---

## 9. Frontend Specification

### 9.0 Constraints — the maintainer is a Python developer

The person maintaining this codebase writes Python daily (FastAPI, Pydantic, Celery) and is **not
fluent in TypeScript or React**. They will have to debug this alone, in production, without you.
Optimise the frontend for *readability by a competent backend engineer*, not for elegance.

**Rule 0 — Never hand-write an API type.**
Generate all request/response types from the FastAPI OpenAPI schema:

```
npx openapi-typescript http://localhost:8000/api/v1/openapi.json -o src/types/api.gen.ts
```

Wire this as `make types` and run it in CI. Everything in `src/types/api.gen.ts` is generated and
never edited by hand. Import types from there; do not re-declare them. This eliminates the majority
of TypeScript a maintainer would otherwise have to write.

**Rule 1 — Allowed TypeScript subset.** Use only:
- `interface Props { name: string; count: number; onSelect: (id: string) => void }`
- Union string literals: `type Severity = 'critical' | 'high' | 'medium' | 'low' | 'info'`
- Optional (`name?: string`) and nullable (`name: string | null`)
- Arrays (`Vendor[]`), simple objects (`Record<string, string>`)
- Function parameter and return annotations
- One-level generics only where a library requires it: `useState<Vendor | null>(null)`,
  `useQuery<Vendor[]>(...)`

**Banned outright** — if you find yourself reaching for these, restructure the code instead:
generics you defined yourself, conditional types, mapped types, `infer`, template literal types,
custom utility types, `enum`, `namespace`, decorators, abstract classes, `satisfies` gymnastics,
deeply nested discriminated unions, barrel files that re-export re-exports.

**Rule 2 — `any` is permitted as an escape hatch.** If satisfying the type checker would take more
than a couple of minutes or would require a banned construct, write `any` with a one-line comment
explaining why. A readable file with three `any`s beats a perfectly typed file nobody can maintain.
Keep `strict: true` otherwise, since that is what makes the compiler catch your mistakes.

**Rule 3 — Component structure rules.** Non-negotiable:
- **One component per file.** File name matches the component name.
- **Props interface declared directly above the component**, in the same file, never imported from
  a shared types file.
- Plain function declarations: `export function VendorTable({ vendors }: Props) { ... }`.
  No `React.FC`, no `forwardRef` unless a Radix primitive demands it, no HOCs, no render props.
- **No custom abstractions over TanStack Query.** Write `useQuery` inline in a
  `features/<domain>/api.ts` hook file, one hook per endpoint, named after the endpoint.
- No clever composition. If a component is used once, keep it in the file that uses it. Extract only
  on the third repetition.
- Max ~200 lines per component file. Split by *screen region* (header / filters / table / drawer),
  never by abstraction level.
- Colocate everything for a feature under `features/<domain>/` — components, hooks, api calls, types.
  A maintainer changing the vendors screen should only ever open `features/vendors/`.

**Rule 4 — Comment for a backend reader.** Every file starts with a 1–3 line header comment saying
what screen or piece of UI it produces and which API endpoints it calls. Comment any React idiom a
Python developer would not recognise on sight — `useEffect` cleanup, dependency arrays, `useMemo`,
event-handler closures, optimistic updates.

**Rule 5 — Deliver `frontend/FRONTEND_GUIDE.md`**, written for a Python developer, containing:
1. A Python → TypeScript/React translation table, e.g.
   `Pydantic BaseModel` → `interface`; `Optional[str]` → `string | null`; `List[Vendor]` →
   `Vendor[]`; `Enum` → union of string literals; `dict` → `Record<string, T>`;
   `f"{x}"` → `` `${x}` ``; list comprehension → `.map()` / `.filter()`;
   `requests.get` → `useQuery`; module-level state → Zustand store.
2. **A "where do I change X" map** — the single most valuable section. A table of ~25 common
   maintenance tasks and the exact file to open. For example:
   | I want to… | Open |
   |---|---|
   | Add a column to the alerts table | `features/alerts/AlertTable.tsx` |
   | Change severity colours | `styles/tokens.css` |
   | Add an item to the sidebar | `components/layout/Sidebar.tsx` + seed a `panel` row in the backend |
   | Add a filter to the vendor list | `features/vendors/VendorFilters.tsx` |
   | Change what a form sends to the API | `features/<domain>/api.ts` |
   | Add a new screen | `features/<domain>/` + register in `router.tsx` + add a `panel` row |
3. The five most common errors a newcomer will hit (stale query cache, missing `key` prop,
   dependency-array bugs, `undefined` before data loads, form/Zod validation mismatch) — with the
   symptom, the cause, and the fix.
4. How to run, build, regenerate types, and debug the frontend.

**Rule 6 — The backend is the source of truth.** Push logic backwards whenever there is a choice:
filtering, sorting, aggregation, permission decisions, severity computation, and formatting of
derived values all happen in Python and arrive as ready-to-render fields. The React layer should be
close to a dumb renderer. When in doubt, add a field to the API response rather than compute it in
a component.

### 9.1 Design language — "senior operator console"

Target: **Bloomberg terminal × Linear × a well-run SOC**. Dense, high-signal, fast, dark-first.
Explicitly **avoid** the neon-cyberpunk cliché — no glowing green Matrix rain, no skull icons, no
`>_` mascot. Restraint reads as senior; decoration reads as junior.

**Tokens (dark, default):**

```
--bg           #0A0B0D    page
--bg-subtle    #101216    sunken areas
--surface      #14171C    cards, panels
--surface-2    #1A1E24    hover, raised
--border       #23272F    hairlines
--border-focus #3A4149
--text         #E4E7EB
--text-muted   #8B93A0
--text-dim     #5B636F
--accent       #22D3EE    single signal colour (cyan) — links, focus, active nav
--accent-fg    #0A0B0D

--sev-critical #F43F5E
--sev-high     #FB923C
--sev-medium   #FBBF24
--sev-low      #38BDF8
--sev-info     #64748B
--ok           #34D399
```

Light theme required as a first-class alternative (same token names, inverted ramp), toggle
persisted per user.

**Typography:** Inter (or Geist Sans) for UI; **JetBrains Mono** for all machine data — CVE IDs,
hashes, IPs, domains, ports, versions, timestamps, JSON. Base 14 px, table text 13 px,
`tabular-nums` on every numeric column.

**Layout:** 4 px spacing grid. `rounded-md` (6 px) max — sharp-ish, not pill-shaped. 1 px hairline
borders instead of drop shadows. No gradients except a barely-visible radial in the top bar.
Density toggle (comfortable / compact) affecting table row height.

**Signature details (subtle, not gimmicky):**
- Severity indicated by a 3 px left border on rows/cards, not a full-colour background.
- A thin animated progress hairline at the top of the viewport during collection/scan runs.
- Monospace "status strip" in the footer: `● collector: healthy   sources 42/44   queue 3   last sync 12:04:11 MYT`
- Command palette on `⌘K` / `Ctrl+K`: jump to any entity, run "poll source", "start scan", "new rule".
- Keyboard shortcuts: `g d` dashboard, `g a` alerts, `g v` vendors, `j/k` row navigation,
  `e` acknowledge, `/` focus search. Show a `?` cheatsheet modal.
- Empty states that teach ("No sources yet — import an OPML or add your first feed") with a CTA.
- Skeleton loaders, never spinners, for table/card content.

**Responsive (mandatory — mobile, tablet, desktop):**
- `<768 px`: bottom tab bar (Dashboard / Alerts / Search / More), sidebar becomes a drawer, data
  tables collapse into stacked cards showing 3–4 key fields with a tap-to-expand detail sheet,
  filters open in a bottom sheet, 44 px minimum touch targets.
- `768–1279 px`: icon-only collapsed sidebar, 2-column grids, tables drop low-priority columns.
- `≥1280 px`: full sidebar, 3–4 column grids, master-detail split panes, all columns.
- Every table must define column priority so column-dropping is deterministic.
- Charts responsive via `ResponsiveContainer`; disable hover-only interactions on touch.

**Accessibility:** WCAG 2.1 AA contrast, visible focus rings, full keyboard operability, ARIA on
all Radix components, `prefers-reduced-motion` respected.

### 9.2 Screens

| Route | Contents |
|---|---|
| `/setup` | Onboarding wizard (§6.1) |
| `/login`, `/login/mfa` | Auth |
| `/` | **Dashboard**: KPI strip (open alerts by severity, new CVEs 24 h, KEV hits, vendors impacted, assets changed, source health); alert timeline (stacked area, 30 d); severity donut; top impacted vendors bar; live alert feed (WebSocket); source health grid; upcoming cert expiries |
| `/alerts` | Virtualized table, saved filter views, bulk ack/resolve, detail drawer with full context + rule trace + delivery status |
| `/feeds/sources` | Source table (health, last run, items, next poll), inline enable/disable, add/edit drawer with **live URL test + parsed-preview**, OPML import/export, bulk actions |
| `/feeds/categories` | Drag-to-reorder tree, colour/icon picker, inline create/rename, delete with reassignment |
| `/feeds/items` | Signal explorer: full-text search, filter by category/source/vendor/date, reader pane, tag, "create rule from this item" |
| `/cve/watchlists` | Watchlist CRUD, criteria builder, **live preview of matching CVEs before saving**, hit history |
| `/cve/explorer` | CVE table with CVSS/EPSS/KEV columns, saved filters, detail page (CPEs, refs, affected vendors, affected components) |
| `/vendors` | Register table + **tree view** + **nth-party graph**; tier and criticality filters; CSV/XLSX import with column mapping; detail tabs: Profile, Keywords, Domains, Advisory Sources, Matches, CVE Exposure, Timeline |
| `/tech-stack` | Component inventory grouped by ecosystem/environment; version vs latest with a drift indicator; vuln badge; EOL countdown; importers for `package.json`, `requirements.txt`, `poetry.lock`, CycloneDX SBOM |
| `/easm/scopes` | Scope list with an explicit **authorization banner**; active scanning disabled and visually locked until authorized |
| `/easm/assets` | Asset inventory, type/tag/criticality filters, tree by parent domain, detail: DNS, ports, TLS, HTTP, technologies, full change history |
| `/easm/changes` | Change feed with before/after JSON diff viewer, severity, ack |
| `/easm/scans` | Job list, live progress via WebSocket, cancel, per-job stats |
| `/rules` | Rule list; **visual condition builder** (nested AND/OR groups, typed field picker) with a raw-JSON toggle; action editor (destination + template); **rule tester** against real historical entities showing a per-node evaluation trace; enable/disable; hit-rate stats |
| `/telegram/bots` | Bot CRUD, masked token, **Verify** button calling `getMe`, health badge |
| `/telegram/destinations` | Destination CRUD, chat/thread ID with a "how to find your chat ID" helper, quiet hours editor, **Test send** |
| `/telegram/templates` | Template list + editor (§5.8): code editor, variable palette, live preview, version diff/rollback, test send |
| `/telegram/deliveries` | Delivery log, status filter, rendered-body view, error detail, retry |
| `/admin/users` | User CRUD, role assignment, force password reset, reset 2FA, lock/unlock, active sessions |
| `/admin/roles` | Role CRUD, **permission matrix**, **panel visibility matrix** |
| `/admin/settings` | Org name/logo/brand colour, timezone, retention policies, default poll interval, notification defaults |
| `/admin/audit` | Audit log with actor/action/entity filters and before/after diff |

---

## 10. Non-Functional Requirements

- **Security:** OWASP ASVS L2 mindset. Parameterized queries only. Strict CORS. Security headers +
  CSP via Nginx. CSRF protection on cookie-auth routes. Rate limiting on all auth endpoints.
  **SSRF protection on every user-supplied URL** (sources, webhooks, EASM targets): block
  RFC1918/loopback/link-local/metadata IPs, validate after DNS resolution, no redirects to private
  ranges, cap response size. Validate uploads by magic bytes. Never log secrets.
- **Performance:** dashboard < 500 ms p95; signal list < 300 ms p95 on 1 M rows. Index every FK and
  every filter/sort column. GIN indexes for full-text and jsonb. Virtualized tables on the frontend
  (`@tanstack/react-virtual`).
- **Reliability:** graceful shutdown, DB connection pooling, `/health` (liveness) and `/ready`
  (DB + Redis reachable) separated.
- **Observability:** structured JSON logs with a request-ID correlation header; Prometheus metrics
  (`hayabusa_collection_runs_total`, `hayabusa_signals_ingested_total`, `hayabusa_alerts_created_total`,
  `hayabusa_deliveries_total{status}`, `hayabusa_source_health`, task duration histograms).
- **Data:** `scripts/backup.sh` (pg_dump), `scripts/restore.sh`, and a `scripts/seed.py` that loads
  ~40 real curated sources, ~20 security-tool vendors with real PSIRT feeds, and demo components.

---

## 11. Repository Layout

```
hayabusa/
├── docker-compose.yml
├── docker-compose.dev.yml
├── .env.example
├── README.md
├── SPEC.md                 # this document
├── DECISIONS.md
├── Makefile                # up, down, logs, migrate, seed, test, lint, fmt
├── backend/
│   ├── pyproject.toml
│   ├── Dockerfile
│   ├── alembic/
│   ├── app/
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── db.py
│   │   ├── core/           # security, crypto, rbac deps, pagination, errors, ssrf, ratelimit
│   │   ├── models/
│   │   ├── schemas/
│   │   ├── api/v1/         # one router per domain
│   │   ├── services/       # business logic — routers stay thin
│   │   ├── collectors/     # base.py + rss.py nvd.py kev.py epss.py osv.py github.py eol.py
│   │   ├── matching/       # vendor matcher, normalizers
│   │   ├── easm/           # discovery, probes, differ, adapters
│   │   ├── rules/          # ast.py evaluator.py registry.py
│   │   ├── notify/         # telegram client, renderer, ratelimiter, dispatcher
│   │   ├── tasks/          # celery app + tasks per domain
│   │   └── seed/
│   └── tests/
└── frontend/
    ├── package.json
    ├── Dockerfile
    ├── nginx.conf
    └── src/
        ├── main.tsx  App.tsx  router.tsx
        ├── lib/          # api client, auth, ws, utils, permissions
        ├── components/   # ui/ (shadcn), layout/, data-table/, charts/, common/
        ├── features/     # auth setup dashboard sources cve vendors techstack easm rules alerts telegram admin
        ├── hooks/
        ├── stores/
        ├── types/
        └── styles/
```

---

## 12. Delivery Phases

Report status after each phase. Do not proceed until acceptance criteria pass.

**Phase 0 — Foundation**
Repo, Docker Compose, FastAPI + SQLAlchemy + Alembic wired to `hayabusa` DB, Celery + Redis + RedBeat,
Vite/React/Tailwind/shadcn shell, Makefile, structured logging, `/health` + `/ready`.
*Accept:* `docker compose up` → API docs load, a hello-world Celery task runs on schedule, frontend serves.

**Phase 1 — Identity**
All §5.1 tables, onboarding wizard, monogram generator, login + TOTP + recovery codes, JWT/refresh
rotation, RBAC, panel visibility, audit log, app shell (sidebar/topbar/theme/command palette),
admin screens.
*Accept:* fresh DB → wizard → 2FA login works → a Viewer role user cannot see or call admin routes.

**Phase 2 — Collection**
Categories, sources, RSS/Atom/JSON adapters, dynamic scheduler, `signal` ingestion + dedupe,
source health/circuit breaker, OPML import/export, source + signal explorer screens, dashboard v1.
*Accept:* add a real RSS feed in the UI → items appear within one cycle → source health accurate →
category CRUD works.

**Phase 3 — Rules & Telegram**
Rule engine (AST, evaluator, field registry), rule builder + tester UI, alerts, Telegram bots,
destinations, template manager with versioning/preview/test-send, delivery queue with rate limiting,
retry, quiet hours, delivery log.
*Accept:* create a rule on feed items → matching item produces an alert → a formatted Telegram
message arrives at the configured destination → editing the template changes the next message.

**Phase 4 — CVE**
NVD/KEV/EPSS collectors, CVE tables, watchlists with criteria builder and live preview, CVE explorer,
rule domain `cve`.
*Accept:* watchlist for a chosen vendor matches real CVEs and alerts on KEV or EPSS ≥ 0.5.

**Phase 5 — Vendors / Nth-party**
Vendor register, aliases/keywords/domains, nth-party parent chain, tree + graph views, matching
engine with scoring, FP feedback, CSV/XLSX import, security-tool vendors with seeded PSIRT sources,
vendor CVE exposure.
*Accept:* import 20 vendors → a news item mentioning one produces a scored `vendor_match` and a
tier-aware Telegram alert; a 4th-party vendor is visibly traceable to its 1st-party parent.

**Phase 6 — Tech Stack**
Component inventory, OSV/GitHub-releases/endoflife collectors, ecosystem-aware version comparison,
importers, drift + EOL + vuln indicators, rule domain `component_event`.
*Accept:* import a `package.json` → known-vulnerable pinned version raises an alert with the fixed
version stated.

**Phase 7 — EASM**
Scopes with the authorization gate, asset model, passive discovery (crt.sh, DNS), active probes
(HTTP, TLS, ports) behind the gate, snapshot/diff change detection, changes feed with JSON diff,
scan jobs with live progress, rule domain `easm_change`, cert-expiry monitoring.
*Accept:* authorize a scope for a domain I own → discovery populates subdomains → a manufactured
change (e.g. new DNS record) produces an `asset_change`, an alert, and a Telegram message.
Unauthorized scope → active scan is refused by the API, not just hidden in the UI.

**Phase 8 — Hardening & Handover**
Test suite (≥70 % backend coverage on services/rules/matching/collectors; Playwright E2E for
onboarding → source → rule → alert → delivery), performance indexes, SSRF/CSP/headers, metrics,
backup/restore scripts, seed data, README + runbook + architecture diagram, mobile/tablet QA pass.
*Accept:* full definition of done in §1 satisfied.

---

## 13. Open Choices You Should Make (and record in DECISIONS.md)

- Graph rendering library for the nth-party view (`reactflow` vs `d3-force`).
- Whether to use `celery-redbeat` or a custom DB-backed beat scheduler.
- Full-text search: Postgres `tsvector` (preferred, keep it simple) vs adding Meilisearch.
- Code editor for templates: CodeMirror 6 (lighter) vs Monaco.

## 14. Ask Me Before Deciding

- Anything requiring an external paid API.
- Anything that changes the Postgres connection contract in §2.
- Adding a message broker or datastore beyond Postgres + Redis.

---

**Start with Phase 0. Print the plan for Phase 0, then build it, then show me the running stack.**
