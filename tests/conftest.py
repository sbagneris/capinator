"""Shared fixtures. Everything here is tiny and hand-crafted — no real facet
cache, no network — so tests are fast and don't change meaning when the live
DigiKey data drifts."""
import copy

import pytest

import libs.digikey as dk
from facet_loader import FacetTables


@pytest.fixture
def sample_response():
    """A minimal search response's FilterOptions, crafted to exercise the loader's
    edge cases: the '-' sentinel, a parameter-name alias, a trailing-period name,
    and a non-string ValueId."""
    return {
        "FilterOptions": {
            "ParametricFilters": [
                {
                    "ParameterName": "Operating Temperature",
                    "ParameterId": 252,
                    "FilterValues": [
                        {"ValueId": "242904", "ValueName": "-55°C ~ 105°C"},
                        {"ValueId": "900001", "ValueName": "85°C"},   # no range
                        {"ValueId": "1", "ValueName": "-"},                # sentinel -> dropped
                    ],
                },
                {
                    "ParameterName": "Height - Seated (Max)",  # alias -> "Height"
                    "ParameterId": 1500,
                    "FilterValues": [{"ValueId": 42, "ValueName": '0.394" (10.00mm)'}],  # int id
                },
                {
                    "ParameterName": "Lifetime @ Temp.",  # trailing period stripped
                    "ParameterId": 725,
                    "FilterValues": [{"ValueId": "68143", "ValueName": "1000 Hrs @ 105°C"}],
                },
            ],
            "Manufacturers": [{"Id": 493, "Value": "Nichicon", "ProductCount": 10}],
            "Packaging": [{"Id": 3, "Value": "Bulk", "ProductCount": 5}],
        }
    }


# Small lookup tables covering exactly what the Utils/make_payload tests reference.
_TABLES = {
    "PARAMETER_IDS": {
        "Capacitance": 2049,
        "Voltage - Rated": 2079,
        "Package / Case": 16,
        "Mounting Type": 69,
        "Polarization": 52,
        "Operating Temperature": 252,
        "Lifetime @ Temp": 725,
    },
    "FILTER_VALS": {
        "Package / Case": {"Axial": "a", "Axial, Can": "ac", "Radial": "r", "Radial, Can": "rc"},
        "Mounting Type": {"Through Hole": "TH", "Surface Mount": "SM"},
        "Polarization": {"Polar": "POL", "Bi-Polar": "BIP"},
        "Packaging": {"Bulk": "3", "Cut Tape (CT)": "2"},
        "Operating Temperature": {"-55°C ~ 105°C": "OT_OK", "85°C": "OT_BAD"},
    },
    "MANUFACTURER_IDS": {"Nichicon": 493, "Rubycon": 1189},
}


@pytest.fixture
def facets():
    return FacetTables(copy.deepcopy(_TABLES))


@pytest.fixture
def util(facets):
    return dk.DigiKeyV4.Utils(facets)


@pytest.fixture
def bare_api(facets):
    """A DigiKeyV4 with facets/util wired up but WITHOUT running __init__ (so no
    OAuth, no network) — lets us unit-test make_payload in isolation."""
    api = object.__new__(dk.DigiKeyV4)
    api.facets = facets
    api.util = dk.DigiKeyV4.Utils(facets)
    return api
