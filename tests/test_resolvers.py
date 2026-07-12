"""Tests for the resolver registry and the capacitor resolver's call-counting."""
import pytest

from capinator.resolvers import (
    DEFAULT_COMPONENT_TYPE,
    AluminumElectrolyticResolver,
    ResolveResult,
    get_resolver,
)


class FakeApi:
    """Fake client whose call_count advances one per query, like DigiKeyV4."""
    def __init__(self):
        self.call_count = 0

    def find_digikey_pn_by_moq(self, params):
        self.call_count += 1
        return "PN-" + params["capacitance"]


def test_registry_has_default_capacitor_resolver():
    r = get_resolver(DEFAULT_COMPONENT_TYPE)
    assert isinstance(r, AluminumElectrolyticResolver)
    assert r.component_type == "aluminum_electrolytic_capacitor"


def test_get_resolver_unknown_type_raises():
    with pytest.raises(KeyError):
        get_resolver("unobtainium")


def test_resolver_parse_then_resolve_counts_calls():
    r = get_resolver(DEFAULT_COMPONENT_TYPE)
    components = r.parse("qty,capacitance,voltage\n1,100,50\n2,220,35\n")
    api = FakeApi()
    result = r.resolve(components, api)
    assert isinstance(result, ResolveResult)
    assert result.output == "1, PN-100, 100uF 50V\n2, PN-220, 220uF 35V"
    assert result.digikey_calls == 2  # one query per row, read from api.call_count
    assert result.errors == []
