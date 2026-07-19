# capinator

A CLI that builds bulk BOM CSVs for ordering electrolytic capacitors from DigiKey —
handy when recapping vintage electronics that need dozens of replacement electrolytics.
It queries the DigiKey Product Information **Search API v4** directly and selects
optimal *in-stock* parts using fine-grained filters (voltage, capacitance, operating
temperature, rated lifetime, lead spacing, dimensions, height, mounting, polarization,
package, packaging), with a configurable **fudge** factor that allows ± deviation so
filtering isn't too strict.

## Setup

Requires DigiKey API credentials (a free DigiKey developer app):

```bash
export DIGIKEY_CLIENT_ID=...
export DIGIKEY_CLIENT_SECRET=...
```

(see `secrets.sh`). Runtime dependencies: `requests`, `requests-oauthlib`, `oauthlib`.

## Usage

```bash
python -m capinator.cli input.csv
```

Reads `input.csv` and writes matched part numbers to `bulk.csv`
(one line per part: `qty, part_number, <cap>uF <volt>V`).

The input CSV has a header row; each row is one capacitor. `qty`, `capacitance` (µF)
and `voltage` (V) are **required**; the rest are optional filters:

| column | meaning |
|--------|---------|
| `qty` | quantity needed (also the maximum acceptable MOQ) |
| `capacitance` | capacitance in µF |
| `voltage` | rated voltage in V |
| `temp` | operating temperature, °C |
| `lifetime` | rated lifetime in hours @ `temp` |
| `lead_spacing` | mm |
| `height` | mm |
| `dimensions` | `W x L` in mm (e.g. `8 x 12`) |
| `package` | `A` (axial), `R` (radial), or an exact package name |
| `packaging` | `Bulk`, `Cut Tape (CT)`, `Tape & Reel (TR)`, … |
| `mounting` | `THT` or `SMD` (defaults to through-hole) |
| `polarization` | blank = polarized; `NP`/`BP` = bipolar |
| `fudge` | ± percent tolerance applied to the fuzzy filters |

Example:

```csv
qty,capacitance,voltage,temp,lifetime,fudge
3,100,25,105,5000,10
```

If no manufacturers are specified, results are restricted to a default set of
reputable makers (Nichicon, Panasonic, Rubycon, Chemi-Con).

### Filter cache

On the first run (and at most weekly thereafter) the tool makes **one** broad query to
build a cache of DigiKey's filter IDs (`facet_cache.json`); later runs read it from
disk. The DigiKey API is rate-limited, so the tool is built to minimize calls.

## Testing

```bash
pip install -r requirements-dev.txt   # installs pytest
python -m pytest -q
```

Tests are **hermetic** — no network or credentials required. Run a single test:

```bash
python -m pytest tests/test_filters.py::test_is_temp_in_range_within
```

## Web app

A multi-user web front-end wraps the same resolver: paste a CSV list, get the resolved
bulk-order lines back, and (when registered) save/curate lists and regenerate them.

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
export DIGIKEY_CLIENT_ID=...  DIGIKEY_CLIENT_SECRET=...  SECRET_KEY=$(openssl rand -hex 32)
.venv/bin/uvicorn webapp.main:app --workers 1        # http://127.0.0.1:8000
```

Key points:

- **One process, one worker.** A single background **thread** runs jobs one at a time —
  this serialization is the DigiKey rate-limit throttle. Always run with **`--workers 1`**;
  more uvicorn workers would spawn parallel threads that race the shared API key.
- **Rate-limit aware.** Every response's `X-RateLimit-*` headers are captured; the header
  badge shows remaining daily quota and the worker pauses when it runs low.
- **Guests** get a small daily job limit (`GUEST_JOB_LIMIT`); registering lifts it and
  lets you save lists.

### Component-list catalog (seed file)

Saved lists live in the SQL DB, but the **durable source of truth is a committed YAML
file** (`seed/component_lists.yaml`) — this survives Render's ephemeral disk, which resets
the SQLite DB on every deploy. On startup the app auto-seeds from that file. To persist
changes made in the app: an admin opens **`/admin`**, clicks **Export**, and commits the
downloaded YAML. (There's no shell on the Render free tier, so export/import is UI-driven.)

### Deployment (self-hosted: Docker Compose + Postgres + Caddy)

The recommended production setup for a VPS (e.g. DigitalOcean). One command brings up
Postgres, the app, and Caddy (automatic Let's Encrypt HTTPS):

```bash
cp .env.example .env     # then edit: DOMAIN, POSTGRES_PASSWORD, SECRET_KEY, DIGIKEY_*
docker compose up -d --build
```

- **Postgres** is the durable store (a `pgdata` volume) — no more ephemeral disk. Back it up.
- **App** runs `alembic upgrade head` on start, then a single uvicorn worker; the in-process
  background thread stays the sole DigiKey-serializing worker, so **never scale this service**.
- **Caddy** obtains and auto-renews a Let's Encrypt cert for `DOMAIN` (ports 80/443 must be
  open on the droplet). Before DNS is pointed, set `DOMAIN=localhost` for self-signed TLS,
  then switch to the real hostname once the A record resolves and re-run `docker compose up -d`.

**`SECRET_KEY` must be set once and kept stable** — it signs sessions *and* keys the
API-token HMAC, so rotating it logs everyone out and invalidates every issued API key.

### Deployment (Render free tier)

`render.yaml` describes a single free web service. The SQLite DB is ephemeral; for durable
live writes set `DATABASE_URL` to a Postgres instance (schema via `alembic upgrade head` —
SQLite→Postgres is just a URL change).

## Layout

| path | purpose |
|------|---------|
| `capinator/cli.py` | CLI entry point (`python -m capinator.cli <csv>` → `bulk.csv`) |
| `capinator/bom.py` | CSV parse/build/round-trip, decoupled from I/O (shared by CLI + web) |
| `capinator/resolvers.py` | resolver protocol + registry (capacitor resolver for the MVP) |
| `capinator/digikey.py` | DigiKey v4 API client, request building, spec parsers |
| `capinator/facet_loader.py` | builds & disk-caches filter lookup tables from API responses |
| `capinator/digikey_data.py` | filter regexes + category IDs |
| `webapp/` | FastAPI app: models, worker, routers, templates, seed import/export |
| `seed/component_lists.yaml` | durable, committed component-list catalog |
| `alembic/` | database migrations (SQLite dev → Postgres prod) |
| `tests/` | pytest suite (hermetic; no network/credentials) |
| `Dockerfile`, `entrypoint.sh` | app image (migrate → single uvicorn worker) |
| `docker-compose.yml`, `Caddyfile` | self-hosted stack: Postgres + app + Caddy (auto HTTPS) |
