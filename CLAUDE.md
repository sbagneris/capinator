# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

capinator generates bulk BOM CSVs for ordering electrolytic capacitors from DigiKey
(for recapping old electronics). It calls the DigiKey Product Information **Search API
v4** and picks optimal in-stock replacements using fine-grained parametric filters,
with a "fudge" factor allowing ± % deviation. See `README.md` for user-facing usage.

## Commands

```bash
source secrets.sh                                   # exports DIGIKEY_CLIENT_ID/SECRET (needed to RUN, not to TEST)
python -m capinator.cli <input.csv>                  # run the CLI -> writes bulk.csv
.venv/bin/uvicorn webapp.main:app --workers 1        # run the web app (http://127.0.0.1:8000)
.venv/bin/pip install -r requirements.txt -r requirements-dev.txt   # install deps + pytest
.venv/bin/python -m pytest -q                        # run all tests (hermetic; no network/creds)
.venv/bin/python -m pytest tests/test_filters.py::test_is_temp_in_range_within   # single test
```

There is no lint step. Runtime deps are in `requirements.txt`; the web app **must** run
with `--workers 1` (a single background worker thread serializes DigiKey calls).

## Architecture

Core library (`capinator/`) + a web app (`webapp/`). The library layers:

1. **`capinator/cli.py`** + **`capinator/bom.py`** — CLI + reusable BOM logic.
   `bom.parse_spec` reads CSV text into per-component dicts (keys from the header);
   `bom.build_bom` builds a params dict per row (dropping empty cells), calls
   `DigiKeyV4.find_digikey_pn_by_moq`, and formats `qty, part_number, spec` lines;
   `bom.to_csv` is the inverse of `parse_spec`. CSV column names map **directly** to
   `make_payload` kwargs. The web worker reuses `build_bom` via a resolver.
2. **`capinator/digikey.py`** — `DigiKeyV4`: OAuth2 client-credentials auth, `make_payload`
   (translates kwargs → the v4 search request body), search + pagination, the nested
   `Utils` spec-string parsers + fudge math, and `call_count` / `rate_limit_*`
   instrumentation captured from each response's `X-RateLimit-*` headers.
3. **`capinator/facet_loader.py`** — turns a search response's `FilterOptions` block into
   the lookup tables (`PARAMETER_IDS`, `FILTER_VALS`, `MANUFACTURER_IDS`) `make_payload`
   needs, and disk-caches them.
4. **`capinator/resolvers.py`** — `Resolver` protocol + registry keyed by
   `component_type`; the generalization seam the web layer talks to.
5. **`webapp/`** — FastAPI app (SQLAlchemy models, one background worker thread, HTMX
   templates, YAML seed import/export). See `README.md` and the plan for details.

### The DigiKey v4 filter model (the crux)

The API has no endpoint to enumerate valid filter values. Instead **every**
`/products/v4/search/keyword` response echoes the whole filter sidebar in
`FilterOptions`:

- `ParametricFilters` — parametric specs, each `{ParameterName, ParameterId,
  FilterValues:[{ValueId, ValueName}]}`. To filter, send
  `ParameterFilterRequest.ParameterFilters: [{ParameterId, FilterValues:[{Id: ValueId}]}]`.
- `Manufacturers`, `Packaging`, `Series`, `Status` — **non-parametric** facet groups
  (`{Id, Value}`) that filter via their **own top-level request fields**
  (`ManufacturerFilter`, `PackagingFilter`, …), *not* via `ParameterFilters`.

`facet_loader.load_facets` harvests these. `get_facet_tables(fetch_fn)` reads the disk
cache (`facet_cache.json`) and only calls `fetch_fn` (one broad category-58 query) on a
cold/expired cache (weekly TTL); on a failed refresh it returns the **stale** cache.
This replaced an older Selenium UI scrape (`ext_data.py`; the `ElectrolyticCapacitors`
class in `capinator/digikey_data.py` is now dead — only its `Regexes` and `CATEGORY_IDS`
are still imported).

## Critical constraints & gotchas (hard-won this project)

- **The API is rate-limited.** Minimizing queries is a design requirement. Never add
  features that fan out many per-item queries; prefer facet data/counts already present
  in a response. The facet cache exists for this — keep the warm path at **zero** extra
  queries.
- **Facet data drifts.** Value IDs and manufacturer *names* change over time (e.g.
  Panasonic vendor Id 10 was "Panasonic Electronic Components", now "Panasonic
  Industry"). Reference manufacturers by **stable ID** (`DEFAULT_MANUFACTURER_IDS`),
  never by name.
- **Packaging is non-parametric.** Filter it via top-level `PackagingFilter:[{Id:<int>}]`.
  A past bug used a synthetic `ParameterId: -5` (lifted from a MUI
  `data-testid="filter-box-group--5"`), which the API ignores and which silently
  returns **zero** products.
- **Spec parsers must tolerate non-conforming facet values.** Dynamic facets legitimately
  contain values the strict parsers can't read (e.g. Operating Temperature `"85°C"` with
  no `~` range). `Utils._select_facet_values` catches `ValueError` and skips; one odd
  value must never abort a query. The `"-"` (unspecified) facet is dropped in
  `load_facets`.
- **Type conventions:** `FILTER_VALS` ids are strings; manufacturer/packaging ids from
  facets are ints (`PackagingFilter` sends int ids). Capacitance/Voltage are sent as
  literal value strings (e.g. `"100 uF"`), not looked up in `FILTER_VALS`.
- **Credentials are in git history** (old hardcoded keys in `libs/digikey.py` /
  `digikey_cart.py`). Rotate before publishing; scrub history if the repo goes public.

## Testing

pytest, configured in `pytest.ini` (`pythonpath = .` so `capinator.digikey`/
`capinator.facet_loader` import). Fixtures in `tests/conftest.py` are tiny hand-crafted dicts (not the ~1 MB real
cache) so they're fast and don't change meaning when live data drifts. `bare_api` builds
a `DigiKeyV4` via `object.__new__` so `make_payload` is testable without auth/network.
Coverage targets the parsing/cache logic and the payload-shaping gotchas above.

## Known deferred issues

Public sharing (global repo browsing), the public REST API, and additional component-type
resolvers are Phase 2 (documented, not built). CSV columns that would need a list (e.g.
`manufacturers`) aren't reliably passable through the single-string CSV cells. These
aren't blockers for the MVP.
