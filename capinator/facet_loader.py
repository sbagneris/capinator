# Build digikey_data.py's lookup tables dynamically from the `FilterOptions` block
# that every /products/v4/search/keyword response returns, instead of scraping the
# filter UI with Selenium.
#
# A search response carries the whole filter sidebar:
#   FilterOptions.ParametricFilters  -> parametric params (Capacitance, Operating
#                                       Temperature, Lead Spacing, ...) each with a
#                                       ParameterId and a list of {ValueId, ValueName}.
#   FilterOptions.Manufacturers       -> [{Id, Value, ProductCount}]  (non-parametric)
#   FilterOptions.Packaging           -> [{Id, Value, ProductCount}]  (non-parametric)
#
# get_facet_tables() wraps the loader in a disk cache so the (rate-limited) API is
# queried at most once per TTL.

import json
import os
import time
from typing import Any, Callable, Dict

# DigiKey's canonical parameter names -> the friendlier aliases libs/digikey.py
# already references.  Keeps this swap zero-churn for the call sites.
ALIASES = {
    "Size / Dimension": "Dimensions",
    "Height - Seated (Max)": "Height",
    "Surface Mount Land Size": "SMD Land Size",
}

# DigiKey emits a "no value declared" facet (ValueName "-") for parts that don't
# specify a parameter.  It's never a real filter target, so drop it.  Keyed on the
# NAME, not the id: id "1" is a legitimate value elsewhere (e.g. Packaging Tape & Reel).
_SENTINEL_VALUE_NAMES = {"-"}

DEFAULT_CACHE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "facet_cache.json")
DEFAULT_TTL_SECONDS = 7 * 24 * 3600  # refresh at most weekly


def _norm(name: str) -> str:
    """Normalize a parameter name: strip DigiKey's trailing period
    ('Lifetime @ Temp.' -> 'Lifetime @ Temp') and apply the alias map."""
    name = name.strip().rstrip(".").strip()
    return ALIASES.get(name, name)


def load_facets(response: Dict[str, Any]) -> Dict[str, Dict]:
    """Extract lookup tables from one search response's FilterOptions block.

    Returns the same shape as the static ElectrolyticCapacitors maps:
        {
          "PARAMETER_IDS":    {param_name: parameter_id},        # ids are ints
          "FILTER_VALS":      {param_name: {value_name: value_id}},  # ids are strs
          "MANUFACTURER_IDS": {manufacturer_name: id},           # ids are ints
        }
    """
    fo = response.get("FilterOptions", {})

    parameter_ids: Dict[str, Any] = {}
    filter_vals: Dict[str, Dict[str, str]] = {}

    for p in fo.get("ParametricFilters", []) or []:
        name = _norm(p["ParameterName"])
        parameter_ids[name] = p["ParameterId"]
        values = {}
        for v in p.get("FilterValues", []) or []:
            if v["ValueName"] in _SENTINEL_VALUE_NAMES:
                continue
            # FILTER_VALS ids are sent back to the API as strings (matches the
            # original static tables and the payloads that already work).
            values[v["ValueName"]] = str(v["ValueId"])
        filter_vals[name] = values

    # Non-parametric facet group the tool treats as a normal filter.
    if fo.get("Packaging"):
        filter_vals["Packaging"] = {g["Value"]: str(g["Id"]) for g in fo["Packaging"]}

    # Manufacturer ids stay ints to match ManufacturerFilter's existing behaviour.
    manufacturer_ids = {g["Value"]: g["Id"] for g in fo.get("Manufacturers", []) or []}

    return {
        "PARAMETER_IDS": parameter_ids,
        "FILTER_VALS": filter_vals,
        "MANUFACTURER_IDS": manufacturer_ids,
    }


def merge_facets(*table_sets: Dict[str, Dict]) -> Dict[str, Dict]:
    """Merge tables from several responses to widen coverage (used by tests).

    In production one broad category query already returns the complete set, so
    this is only needed when stitching together saved narrow responses."""
    out = {"PARAMETER_IDS": {}, "FILTER_VALS": {}, "MANUFACTURER_IDS": {}}
    for t in table_sets:
        out["PARAMETER_IDS"].update(t["PARAMETER_IDS"])
        out["MANUFACTURER_IDS"].update(t["MANUFACTURER_IDS"])
        for cat, vals in t["FILTER_VALS"].items():
            out["FILTER_VALS"].setdefault(cat, {}).update(vals)
    return out


def broad_query_payload(category_id: str) -> Dict[str, Any]:
    """Minimal category-only search payload: returns the category's complete facet
    set while fetching a single product row."""
    return {
        "Limit": 1,
        "FilterOptionsRequest": {
            "CategoryFilter": [{"Id": category_id}],
            "ParameterFilterRequest": {
                "CategoryFilter": {"Id": category_id},
                "ParameterFilters": [],
            },
        },
    }


class FacetTables:
    """Runtime stand-in for the static ElectrolyticCapacitors maps."""

    def __init__(self, tables: Dict[str, Dict]):
        self.PARAMETER_IDS = dict(tables["PARAMETER_IDS"])
        self.FILTER_VALS = tables["FILTER_VALS"]
        self.MANUFACTURER_IDS = tables["MANUFACTURER_IDS"]


def _read_cache(path: str):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _write_cache(path: str, tables: Dict[str, Dict]) -> None:
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"fetched_at": time.time(), "tables": tables}, f,
                  ensure_ascii=False, indent=1)
    os.replace(tmp, path)  # atomic swap so a crash never leaves a half-written cache


def get_facet_tables(
    fetch_fn: Callable[[], Dict[str, Any]],
    *,
    cache_path: str = DEFAULT_CACHE_PATH,
    ttl: int = DEFAULT_TTL_SECONDS,
    force_refresh: bool = False,
) -> FacetTables:
    """Return FacetTables, hitting the DigiKey API at most once per `ttl`.

    `fetch_fn()` returns a raw search-response dict and is the ONLY thing that costs
    an API call; it runs only on a cold or expired cache.  If a refresh fails but any
    cache (even stale) exists, the stale cache is returned instead of raising — this
    protects the API key's query limit from repeated failed refreshes.
    """
    cache = _read_cache(cache_path)
    is_fresh = bool(cache) and (time.time() - cache.get("fetched_at", 0)) < ttl
    if cache and is_fresh and not force_refresh:
        return FacetTables(cache["tables"])

    try:
        tables = load_facets(fetch_fn())
        _write_cache(cache_path, tables)
        return FacetTables(tables)
    except Exception:
        if cache:  # stale facets beat hammering a rate-limited API or crashing
            return FacetTables(cache["tables"])
        raise
