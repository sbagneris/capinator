"""Tests for the Utils spec parsers and the facet-selection loop that must skip
values it can't parse (the '85°C' regression)."""
import pytest


def test_is_temp_in_range_within(util):
    assert util.is_temp_in_range("-55°C ~ 105°C", 25) is True


def test_is_temp_in_range_outside(util):
    assert util.is_temp_in_range("-55°C ~ 105°C", 150) is False


def test_is_temp_in_range_fudge_widens_bounds(util):
    assert util.is_temp_in_range("-40°C ~ 105°C", 110, fudge=0) is False
    assert util.is_temp_in_range("-40°C ~ 105°C", 110, fudge=10) is True


def test_is_temp_in_range_raises_on_non_range(util):
    with pytest.raises(ValueError):
        util.is_temp_in_range("85°C", 85)


def test_make_temperature_filter_skips_unparseable(util):
    # Operating Temperature facet contains both a valid range and a bare "85°C".
    ids = util.make_temperture_filter(25, 0)
    assert {"Id": "OT_OK"} in ids
    assert {"Id": "OT_BAD"} not in ids   # '85°C' skipped, not crashed on


def test_make_temperature_filter_no_match_is_empty(util):
    assert util.make_temperture_filter(150, 0) == []


def test_does_rating_meets_lifetime_and_temp(util):
    assert util.does_rating_meets_lifetime_and_temp("1000 Hrs @ 105°C", 500, 85) is True
    assert util.does_rating_meets_lifetime_and_temp("1000 Hrs @ 105°C", 2000, 85) is False


def test_is_dim_close_enough(util):
    assert util.is_dim_close_enough('0.300" (7.62mm)', 7.62) is True
    assert util.is_dim_close_enough('0.300" (7.62mm)', 9.0) is False
