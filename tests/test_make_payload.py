"""Tests for make_payload — guards the payload-shaping bugs fixed this session
(packaging, polarization, default manufacturers, offset, keywords)."""
import capinator.digikey as dk


def _param_filters(payload):
    return payload["FilterOptionsRequest"]["ParameterFilterRequest"]["ParameterFilters"]


def _filter_by_pid(payload, pid):
    return [f for f in _param_filters(payload) if f["ParameterId"] == pid]


def test_packaging_uses_packaging_filter_with_int_id(bare_api):
    p = bare_api.make_payload(packaging="Bulk")
    assert p["FilterOptionsRequest"]["PackagingFilter"] == [{"Id": 3}]  # int, not "3"


def test_packaging_never_uses_parameterfilters_or_negative_id(bare_api):
    p = bare_api.make_payload(packaging="Bulk")
    # the old bug put Packaging in ParameterFilters under a bogus ParameterId -5
    assert all(f["ParameterId"] >= 0 for f in _param_filters(p))


def test_polarization_defaults_to_polar_when_absent(bare_api):
    pol = _filter_by_pid(bare_api.make_payload(), 52)[0]
    assert pol["FilterValues"] == [{"Id": "POL"}]


def test_polarization_non_np_bp_does_not_crash(bare_api):
    # value that isn't NP/BP used to raise NameError (polarization unbound)
    pol = _filter_by_pid(bare_api.make_payload(polarization="Polar"), 52)[0]
    assert pol["FilterValues"] == [{"Id": "POL"}]


def test_polarization_np_selects_bipolar(bare_api):
    pol = _filter_by_pid(bare_api.make_payload(polarization="NP"), 52)[0]
    assert pol["FilterValues"] == [{"Id": "BIP"}]


def test_default_manufacturers_by_stable_id(bare_api):
    p = bare_api.make_payload()
    assert p["FilterOptionsRequest"]["ManufacturerFilter"] == [
        {"Id": m} for m in dk.DEFAULT_MANUFACTURER_IDS
    ]


def test_offset_written_to_payload(bare_api):
    assert bare_api.make_payload(offset=50)["Offset"] == 50


def test_keywords_accepts_str_and_list(bare_api):
    assert bare_api.make_payload(keywords="low esr")["Keywords"] == "low esr"
    assert bare_api.make_payload(keywords=["low", "esr"])["Keywords"] == "low esr"
