"""Hermetic tests for the YAML seed import/export core (no HTTP, no network)."""
import pytest

from webapp.db import Base, SessionLocal, engine
from webapp.models import ComponentList, User
from webapp.seed import export_lists, import_lists, parse_yaml

DATA = [
    {
        "key": "amp-recap",
        "name": "Amp recap",
        "owner_email": "curator@test.local",
        "device_make": "Marantz",
        "is_public": True,
        "components": [
            {"qty": 2, "capacitance": 1000, "voltage": 50},   # YAML ints -> coerced to str
            {"qty": 4, "capacitance": 470, "voltage": 35},
        ],
    }
]


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


def test_import_creates_list_and_owner_and_coerces_strings(db):
    summary = import_lists(db, DATA)
    assert summary.created == 1 and summary.updated == 0
    cl = db.query(ComponentList).one()
    assert cl.seed_key == "amp-recap"
    assert db.query(User).filter_by(email="curator@test.local").count() == 1
    # values are strings, matching the CSV/JSON convention
    assert cl.components[0] == {"qty": "2", "capacitance": "1000", "voltage": "50"}


def test_import_is_idempotent_upsert(db):
    import_lists(db, DATA)
    summary = import_lists(db, DATA)
    assert summary.created == 0 and summary.updated == 1
    assert db.query(ComponentList).count() == 1  # no duplicate


def test_import_rejects_missing_required_field(db):
    bad = [{"key": "b", "name": "bad", "components": [{"qty": "1", "capacitance": "100"}]}]
    with pytest.raises(ValueError):
        import_lists(db, bad)


def test_export_roundtrips_through_import(db):
    import_lists(db, DATA)
    yaml_text = export_lists(db)

    # fresh DB reproduces the same list
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db2 = SessionLocal()
    try:
        import_lists(db2, parse_yaml(yaml_text))
        cl = db2.query(ComponentList).filter_by(seed_key="amp-recap").one()
        assert cl.name == "Amp recap"
        assert cl.is_public is True
        assert cl.components[0]["capacitance"] == "1000"
    finally:
        db2.close()
