"""Tests for capinator.bom: CSV parsing, CSV round-trip, and BOM building against a
fake DigiKey client (no network)."""
from capinator.bom import build_bom, parse_spec, to_csv

CSV = (
    "qty,capacitance,voltage,mounting,package,packaging,fudge,\n"
    "1,100,50,THT,R,Bulk,10\n"
    "10,220,35,THT,R,Bulk,10\n"
)


def test_parse_spec_keys_from_header_and_drops_blanks():
    rows = parse_spec(CSV)
    assert rows[0] == {
        "qty": "1", "capacitance": "100", "voltage": "50",
        "mounting": "THT", "package": "R", "packaging": "Bulk", "fudge": "10",
    }
    # the trailing-comma blank header column is dropped, values stay strings
    assert "" not in rows[0] and None not in rows[0]
    assert all(isinstance(v, str) for v in rows[0].values())


def test_parse_spec_drops_empty_cells():
    rows = parse_spec("qty,capacitance,voltage,package\n1,100,50,\n")
    assert rows[0] == {"qty": "1", "capacitance": "100", "voltage": "50"}


def test_to_csv_round_trips_parse_spec():
    rows = parse_spec(CSV)
    assert parse_spec(to_csv(rows)) == rows


def test_to_csv_ordered_union_header_for_differing_keys():
    components = [{"qty": "1", "capacitance": "100"}, {"qty": "2", "voltage": "25"}]
    # union header preserves first-seen order; round-trip stays stable
    assert to_csv(components).splitlines()[0] == "qty,capacitance,voltage"
    assert parse_spec(to_csv(components)) == components


class FakeApi:
    """Records the params it was asked about and returns a scripted P/N (or None)."""
    def __init__(self, pn="C-123"):
        self.pn = pn
        self.seen = []

    def find_digikey_pn_by_moq(self, params):
        self.seen.append(dict(params))
        return self.pn


def test_build_bom_line_format_matches_cli():
    result = build_bom(parse_spec(CSV), FakeApi(pn="565-1000"))
    assert result.lines == [
        "1, 565-1000, 100uF 50V",
        "10, 565-1000, 220uF 35V",
    ]
    assert result.errors == []


def test_build_bom_no_match_is_error_not_line():
    result = build_bom(parse_spec(CSV), FakeApi(pn=None))
    assert result.lines == []
    assert len(result.errors) == 2 and all("No match" in e for e in result.errors)


def test_build_bom_missing_required_field_is_row_error():
    # voltage missing -> row error, but the run continues to the valid row
    text = "qty,capacitance,voltage\n1,100,\n2,220,35\n"
    result = build_bom(parse_spec(text), FakeApi(pn="X"))
    assert result.lines == ["2, X, 220uF 35V"]
    assert len(result.errors) == 1 and "require qty + capacitance + voltage" in result.errors[0]


def test_build_bom_on_progress_receives_messages():
    msgs = []
    build_bom(parse_spec(CSV), FakeApi(pn="Z"), on_progress=msgs.append)
    assert any(m.startswith("Processing:") for m in msgs)
    assert any(m.startswith("Found P/N:") for m in msgs)
