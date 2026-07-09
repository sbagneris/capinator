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
./capinator.py input.csv
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

## Layout

| path | purpose |
|------|---------|
| `capinator.py` | CLI entry point (CSV in → `bulk.csv` out) |
| `libs/digikey.py` | DigiKey v4 API client, request building, spec parsers |
| `facet_loader.py` | builds & disk-caches filter lookup tables from API responses |
| `libs/digikey_data.py` | filter regexes + category IDs |
| `tests/` | pytest suite |
