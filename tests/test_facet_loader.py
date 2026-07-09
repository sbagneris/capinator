"""Tests for facet_loader: parsing FilterOptions into lookup tables, and the disk
cache that keeps DigiKey API queries to at most one per TTL."""
import json

import pytest

from facet_loader import FacetTables, get_facet_tables, load_facets


def counting_fetch(response):
    """Return a fetch_fn returning `response` and recording how many times it ran."""
    calls = {"n": 0}

    def fetch():
        calls["n"] += 1
        return response

    return fetch, calls


# --- load_facets --------------------------------------------------------------

def test_load_facets_maps_parameter_ids(sample_response):
    t = load_facets(sample_response)
    assert t["PARAMETER_IDS"]["Operating Temperature"] == 252
    assert t["PARAMETER_IDS"]["Lifetime @ Temp"] == 725  # trailing period stripped


def test_load_facets_applies_alias(sample_response):
    t = load_facets(sample_response)
    assert "Height" in t["PARAMETER_IDS"]                 # aliased from canonical name
    assert "Height - Seated (Max)" not in t["PARAMETER_IDS"]


def test_load_facets_drops_dash_sentinel(sample_response):
    ot = load_facets(sample_response)["FILTER_VALS"]["Operating Temperature"]
    assert "-" not in ot
    assert ot == {"-55°C ~ 105°C": "242904", "85°C": "900001"}


def test_load_facets_coerces_filter_val_ids_to_str(sample_response):
    height = load_facets(sample_response)["FILTER_VALS"]["Height"]
    assert height == {'0.394" (10.00mm)': "42"}           # int 42 -> "42"


def test_load_facets_manufacturers_and_packaging(sample_response):
    t = load_facets(sample_response)
    assert t["MANUFACTURER_IDS"] == {"Nichicon": 493}     # manufacturer ids stay int
    assert t["FILTER_VALS"]["Packaging"] == {"Bulk": "3"}  # packaging id -> str


# --- get_facet_tables cache behaviour ----------------------------------------

def test_cold_cache_fetches_once_and_writes(tmp_path, sample_response):
    cache = tmp_path / "c.json"
    fetch, calls = counting_fetch(sample_response)
    tables = get_facet_tables(fetch, cache_path=str(cache), ttl=1000)
    assert calls["n"] == 1
    assert cache.exists()
    assert isinstance(tables, FacetTables)
    assert tables.PARAMETER_IDS["Operating Temperature"] == 252


def test_warm_cache_skips_fetch(tmp_path, sample_response):
    cache = tmp_path / "c.json"
    fetch, calls = counting_fetch(sample_response)
    get_facet_tables(fetch, cache_path=str(cache), ttl=1000)   # cold -> writes
    get_facet_tables(fetch, cache_path=str(cache), ttl=1000)   # warm -> no query
    assert calls["n"] == 1


def test_expired_cache_refetches(tmp_path, sample_response):
    cache = tmp_path / "c.json"
    cache.write_text(json.dumps({"fetched_at": 0, "tables": load_facets(sample_response)}))
    fetch, calls = counting_fetch(sample_response)
    get_facet_tables(fetch, cache_path=str(cache), ttl=1)       # fetched_at=0 -> expired
    assert calls["n"] == 1


def test_stale_cache_used_when_refresh_fails(tmp_path):
    cache = tmp_path / "c.json"
    stale = {"PARAMETER_IDS": {"Marker": 7}, "FILTER_VALS": {}, "MANUFACTURER_IDS": {}}
    cache.write_text(json.dumps({"fetched_at": 0, "tables": stale}))

    def boom():
        raise RuntimeError("rate limited")

    tables = get_facet_tables(boom, cache_path=str(cache), ttl=1)  # expired, refresh fails
    assert tables.PARAMETER_IDS == {"Marker": 7}                    # falls back to stale


def test_cold_cache_fetch_failure_propagates(tmp_path):
    cache = tmp_path / "missing.json"

    def boom():
        raise RuntimeError("no network")

    with pytest.raises(RuntimeError):
        get_facet_tables(boom, cache_path=str(cache), ttl=1000)     # no cache to fall back on


def test_force_refresh_ignores_fresh_cache(tmp_path, sample_response):
    cache = tmp_path / "c.json"
    fetch, calls = counting_fetch(sample_response)
    get_facet_tables(fetch, cache_path=str(cache), ttl=1000)
    get_facet_tables(fetch, cache_path=str(cache), ttl=1000, force_refresh=True)
    assert calls["n"] == 2
