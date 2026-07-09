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
./capinator.py <input.csv>                           # run the tool -> writes bulk.csv
.venv/bin/pip install -r requirements-dev.txt        # install pytest
.venv/bin/python -m pytest -q                        # run all tests (hermetic; no network/creds)
.venv/bin/python -m pytest tests/test_filters.py::test_is_temp_in_range_within   # single test
```

There is no build or lint step. Python 3.13, deps live in `.venv` (no runtime
requirements file yet; runtime deps are `requests`, `requests-oauthlib`, `oauthlib`).

## Architecture

Three layers:

1. **`capinator.py`** — CLI. Reads the input CSV with `DictReader`, builds a params
   dict per row (dropping empty cells), calls `DigiKeyV4.find_digikey_pn_by_moq`, and
   appends `qty, part_number, spec` to `bulk.csv`. CSV column names map **directly** to
   `make_payload` kwargs.
2. **`libs/digikey.py`** — `DigiKeyV4`: OAuth2 client-credentials auth, `make_payload`
   (translates kwargs → the v4 search request body), search + pagination, and the nested
   `Utils` class of spec-string parsers + fudge math that decide which facet values
   satisfy a requested temp / lifetime / dimension.
3. **`facet_loader.py`** — turns a search response's `FilterOptions` block into the
   lookup tables (`PARAMETER_IDS`, `FILTER_VALS`, `MANUFACTURER_IDS`) `make_payload`
   needs, and disk-caches them.

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
class in `libs/digikey_data.py` is now dead — only its `Regexes` and `CATEGORY_IDS`
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

pytest, configured in `pytest.ini` (`pythonpath = .` so `libs.digikey`/`facet_loader`
import). Fixtures in `tests/conftest.py` are tiny hand-crafted dicts (not the ~1 MB real
cache) so they're fast and don't change meaning when live data drifts. `bare_api` builds
a `DigiKeyV4` via `object.__new__` so `make_payload` is testable without auth/network.
Coverage targets the parsing/cache logic and the payload-shaping gotchas above.

## Known deferred issues

`main.py` is untouched FastAPI tutorial boilerplate (not wired to anything). CSV columns
that would need a list (e.g. `manufacturers`) aren't reliably passable through the
single-string CSV cells. These aren't blockers for the CLI's core use.
