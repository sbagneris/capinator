# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

capinator picks optimal in-stock replacement **electrolytic capacitors** from DigiKey (for
recapping old electronics) and emits a bulk-order parts list. It started as a CLI and is now
also a multi-user web app: paste a component list, get DigiKey-ready order lines, save/curate
lists with device metadata, share them publicly, and read them back over a public API.

It calls the DigiKey Product Information **Search API v4** with fine-grained parametric
filters, plus a "fudge" factor allowing ± % deviation. See `README.md` for user-facing usage.

## Commands

```bash
source secrets.sh                                # DIGIKEY_CLIENT_ID/SECRET (to RUN, not to TEST)
python -m capinator.cli <input.csv>              # CLI -> bulk.csv

# Web app = TWO processes (see "Process model" below)
.venv/bin/uvicorn webapp.main:app                # terminal 1 -> http://127.0.0.1:8000
.venv/bin/python -m webapp.worker                # terminal 2 -> resolves queued DigiKey jobs

.venv/bin/pip install -r requirements.txt -r requirements-dev.txt
.venv/bin/python -m pytest -q                    # 84 tests, hermetic (no network/creds)
.venv/bin/python -m pytest tests/test_filters.py::test_is_temp_in_range_within  # single test

alembic upgrade head                             # apply migrations (env.py reads DATABASE_URL)
alembic check                                    # fail if models drift from migrations
docker compose up -d --build                     # full stack: db + app + worker + caddy
```

There is no lint step.

## Process model (read this first)

**The DigiKey worker is its own process** — `python -m webapp.worker`. The web app does NOT
start it (nothing in `main.py`'s lifespan). This is the single most important operational fact:

- **Exactly one worker instance** may run. It is the only process that calls DigiKey, and
  running jobs one at a time *is* the rate-limit throttle. Never scale the `worker` service.
- The job claim (`SELECT queued LIMIT 1; UPDATE running` in `Worker._claim_next_job`) is
  race-free **only** with a single worker. More would need Postgres
  `FOR UPDATE SKIP LOCKED` (not SQLite-compatible).
- **The web tier may scale** — `entrypoint.sh` runs uvicorn with `--workers ${WEB_CONCURRENCY:-1}`.
  (The old `--workers 1` rule was a Render free-tier artifact and no longer applies.)
- The worker also owns the hourly guest-job purge (`Worker._maybe_purge`).
- Because the web tier can't see worker memory, the worker mirrors its rate-limit state to a
  **`WorkerState`** singleton row; `worker.quota_snapshot(db)` reads that row for `GET /quota`.

## Architecture

**`capinator/`** — the DigiKey core library (importable by CLI and web alike):

1. **`cli.py`** + **`bom.py`** — `bom.parse_spec` reads CSV text into per-component dicts
   (keys = the CSV header); `bom.build_bom` builds a params dict per row, resolves it, and
   formats `qty, part_number, spec` lines; `bom.to_csv` is the inverse. **CSV column names map
   directly to `make_payload` kwargs.**
2. **`digikey.py`** — `DigiKeyV4`: OAuth2 client-credentials auth (re-auths once on 401),
   `make_payload` (kwargs → v4 search body), search + pagination, the nested `Utils`
   spec-string parsers + fudge math, and `rate_limit_*` captured from each response's
   `X-RateLimit-*` headers.
3. **`facet_loader.py`** — turns a response's `FilterOptions` into the lookup tables
   (`PARAMETER_IDS`, `FILTER_VALS`, `MANUFACTURER_IDS`) and disk-caches them.
4. **`resolvers.py`** — `Resolver` protocol + registry keyed by `component_type`. The
   generalization seam; only the aluminum-electrolytic resolver exists today.

**`webapp/`** — FastAPI app. `main.py` (app factory, lifespan: `create_all` + seed),
`config.py` (pydantic-settings), `db.py`, `models.py`, `services.py`, `auth.py`, `apikeys.py`,
`api.py` (public read-only API mounted at `/api`), `seed.py` (YAML import/export),
`worker.py`, `templating.py`, and `routers/{pages,jobs,account,admin}.py` with Jinja2 +
HTMX templates.

### The DigiKey v4 filter model (the crux)

The API has no endpoint to enumerate valid filter values. Instead **every**
`/products/v4/search/keyword` response echoes the whole filter sidebar in `FilterOptions`:

- `ParametricFilters` — parametric specs, each `{ParameterName, ParameterId,
  FilterValues:[{ValueId, ValueName}]}`. Filter via
  `ParameterFilterRequest.ParameterFilters: [{ParameterId, FilterValues:[{Id: ValueId}]}]`.
- `Manufacturers`, `Packaging`, `Series`, `Status` — **non-parametric** facet groups
  (`{Id, Value}`) filtered via their **own top-level request fields**
  (`ManufacturerFilter`, `PackagingFilter`, …), *not* via `ParameterFilters`.

`facet_loader.get_facet_tables(fetch_fn)` reads the disk cache (`facet_cache.json`) and only
calls `fetch_fn` (one broad category-58 query) on a cold/expired cache (weekly TTL); a failed
refresh returns the **stale** cache. This replaced an old Selenium UI scrape — the
`ElectrolyticCapacitors` class in `capinator/digikey_data.py` is dead; only its `Regexes` and
`CATEGORY_IDS` are still imported.

### Data model (`webapp/models.py`)

`User`, **`ComponentList`** (the input: `components` JSON + `component_type`, device
make/model/board_reference, `is_public`, `seed_key`), **`Resolution`** (a resolved parts list;
history is kept, newest = current), `ApiKey`, **`Job`** (a resolve run: `user_id` **or**
`guest_id`, `input_components`, `input_hash`, status, result, `digikey_calls`,
`remaining_quota`), and `WorkerState` (singleton, id=1).

Per-component search params are a **single JSON column**, not child tables or fixed columns,
so the schema generalizes to any component type. CSV is a derived view (`bom.to_csv`).

### Key web behaviours

- **Save-by-default:** a logged-in user's *done* job is lazily promoted to a `ComponentList`
  wherever it's rendered (`routers/jobs._promote_if_owner` → `services.promote_job_to_list`).
  Identical re-runs (same `input_hash`) **append a `Resolution`** to the existing list rather
  than duplicating it. Promotion is idempotent.
- **The worker stays ComponentList-unaware** — promotion and `services.ensure_resolution`
  happen lazily in the routers, never in `worker.py`. Preserve this boundary.
- **Guests** are identified by a `guest_id` in the signed session cookie, get
  `GUEST_JOB_LIMIT` jobs/24h, and see their runs on the Activity page. Unclaimed guest jobs
  are **purged after `guest_retention_hours` (48h)**; registering/logging in **claims** them
  (`services.claim_guest_jobs`), which is what rescues them from the purge.
- **Visibility:** `GET /lists/{id}` shows public lists to anyone (read-only — owner controls
  are gated on `is_owner`); private lists **404** for non-owners so their existence isn't
  leaked. `/public` browses shared lists.
- **Public API** (`/api`, docs at `/api/docs`): read-only, API-key auth via `HTTPBearer` (a
  declared OpenAPI security scheme, so Swagger's "Authorize" works), per-key rate limiting.
  It serves only stored data and makes **zero** DigiKey calls.

## Critical constraints & gotchas (hard-won)

- **The API is rate-limited.** Minimizing queries is a design requirement. Never add features
  that fan out many per-item queries; prefer facet data/counts already in a response. Keep the
  warm facet-cache path at **zero** extra queries. `create_job` also dedupes identical inputs
  within an hour.
- **`SECRET_KEY` must be stable.** It signs sessions *and* keys the API-token HMAC
  (`apikeys.hash_token`) — rotating it logs everyone out **and invalidates every API key**.
- **Facet data drifts.** Value IDs and manufacturer *names* change (Panasonic vendor Id 10 was
  "Panasonic Electronic Components", now "Panasonic Industry"). Reference manufacturers by
  **stable ID** (`DEFAULT_MANUFACTURER_IDS`), never by name.
- **Packaging is non-parametric.** Filter via top-level `PackagingFilter:[{Id:<int>}]`. A past
  bug used a synthetic `ParameterId: -5` (lifted from a MUI `data-testid="filter-box-group--5"`)
  which the API ignores and which silently returns **zero** products.
- **Spec parsers must tolerate non-conforming facet values.** Dynamic facets legitimately
  contain values the strict parsers can't read (e.g. Operating Temperature `"85°C"` with no
  `~` range). `Utils._select_facet_values` catches `ValueError` and skips; one odd value must
  never abort a query. The `"-"` (unspecified) facet is dropped in `load_facets`.
- **Type conventions:** `FILTER_VALS` ids are strings; manufacturer/packaging ids from facets
  are ints (`PackagingFilter` sends int ids). Capacitance/Voltage are sent as literal value
  strings (e.g. `"100 uF"`), not looked up in `FILTER_VALS`.
- **Credentials are in git history** (old hardcoded keys in `libs/digikey.py` /
  `digikey_cart.py`). Rotate before publishing; scrub history if the repo goes public.

## Testing

pytest, configured in `pytest.ini` (`pythonpath = .`). **Hermetic — no network or credentials.**
`tests/conftest.py` points the app at a throwaway SQLite DB and disables startup seeding
*before* any webapp import, and provides tiny hand-crafted facet fixtures (not the ~1 MB real
cache) so tests stay fast and don't change meaning when live data drifts.

Patterns to follow:
- `bare_api` builds a `DigiKeyV4` via `object.__new__` so `make_payload` is testable without
  auth/network.
- Web tests use `TestClient(app)` **without** the context manager (no lifespan), and drive jobs
  synchronously via `worker._process(job_id)` with a `FakeApi` injected into `worker._clients`.
- After schema changes, add a migration and confirm `alembic check` reports no drift.

## Deployment

**Self-hosted (preferred):** `docker-compose.yml` runs `db` (postgres:16, `pgdata` volume),
`app` (entrypoint runs `alembic upgrade head` then uvicorn), `worker` (same image, entrypoint
`python -m webapp.worker`, never scaled), and `caddy` (automatic Let's Encrypt for `$DOMAIN`).
The **app owns migrations**; the worker retries until the schema exists. SQLite→Postgres is
just a `DATABASE_URL` change (`webapp/db.py` no-ops its SQLite-only bits on Postgres).

`seed/component_lists.yaml` is a committed catalog auto-seeded on startup (admin can
export/import it at `/admin`) — a durability lifeline from the Render era, now a convenience
since Postgres is durable. `render.yaml` remains for the legacy Render path.

## Known deferred

- Only the aluminum-electrolytic resolver exists; other component types plug into
  `capinator/resolvers.py`'s registry.
- Scaling to more than one worker needs `FOR UPDATE SKIP LOCKED` job claiming.
- CSV columns needing a list (e.g. `manufacturers`) aren't reliably passable through
  single-string CSV cells.
