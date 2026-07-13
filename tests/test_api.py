"""Public API tests: Bearer auth, own+public visibility, detail access, rate limiting.
Hermetic — the read-only API makes no DigiKey/network calls."""
import pytest
from fastapi.testclient import TestClient

from webapp import apikeys
from webapp.apikeys import create_key
from webapp.auth import hash_password
from webapp.db import Base, SessionLocal, engine
from webapp.main import app
from webapp.models import ComponentList, Resolution, User


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.create_all(bind=engine)
    apikeys.reset_rate_limits()
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    return TestClient(app)


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _seed():
    """Users A and B, each with a private and a public list; A's public list has a
    resolution. Returns (A's token, {list-name: id})."""
    db = SessionLocal()
    try:
        a = User(email="a@x.com", password_hash=hash_password("pw"))
        b = User(email="b@x.com", password_hash=hash_password("pw"))
        db.add_all([a, b])
        db.commit()
        db.refresh(a)
        db.refresh(b)

        lists = {
            "a_priv": ComponentList(owner_id=a.id, name="A private",
                                    components=[{"qty": "1", "capacitance": "100", "voltage": "50"}]),
            "a_pub": ComponentList(owner_id=a.id, name="A public", is_public=True,
                                   components=[{"qty": "2", "capacitance": "220", "voltage": "35"}]),
            "b_priv": ComponentList(owner_id=b.id, name="B private",
                                    components=[{"qty": "1", "capacitance": "10", "voltage": "16"}]),
            "b_pub": ComponentList(owner_id=b.id, name="B public", is_public=True,
                                   components=[{"qty": "3", "capacitance": "470", "voltage": "25"}]),
        }
        db.add_all(lists.values())
        db.commit()
        ids = {name: cl.id for name, cl in lists.items()}

        db.add(Resolution(component_list_id=ids["a_pub"], output="2, PN-220, 220uF 35V\n", digikey_calls=1))
        db.commit()

        _, token = create_key(db, a, "test")
        return token, ids
    finally:
        db.close()


def test_openapi_declares_bearer_security_for_swagger(client):
    schema = client.get("/api/openapi.json").json()
    schemes = schema.get("components", {}).get("securitySchemes", {})
    # a declared HTTP bearer scheme is what makes Swagger UI render the Authorize button
    assert any(
        s.get("type") == "http" and s.get("scheme") == "bearer" for s in schemes.values()
    ), "no HTTP bearer security scheme -> Swagger has no way to enter the token"
    # and the protected endpoints must reference it
    assert schema["paths"]["/v1/lists"]["get"].get("security"), \
        "protected endpoint doesn't require the security scheme"


def test_requires_valid_key(client):
    assert client.get("/api/v1/lists").status_code == 401
    assert client.get("/api/v1/lists", headers=_auth("cap_bogus")).status_code == 401


def test_lists_returns_own_and_public_but_not_others_private(client):
    token, ids = _seed()
    r = client.get("/api/v1/lists", headers=_auth(token))
    assert r.status_code == 200
    got = {row["id"] for row in r.json()}
    assert {ids["a_priv"], ids["a_pub"], ids["b_pub"]} <= got
    assert ids["b_priv"] not in got


def test_detail_public_ok_others_private_404(client):
    token, ids = _seed()
    ok = client.get(f"/api/v1/lists/{ids['a_pub']}", headers=_auth(token))
    assert ok.status_code == 200
    body = ok.json()
    assert body["components"]
    assert body["result"]["output"].startswith("2, PN-220")
    # another user's private list is invisible -> 404 (don't leak existence)
    assert client.get(f"/api/v1/lists/{ids['b_priv']}", headers=_auth(token)).status_code == 404


def test_rate_limit_returns_429(client, monkeypatch):
    token, _ = _seed()
    monkeypatch.setattr(apikeys.settings, "api_rate_limit_per_min", 2)
    apikeys.reset_rate_limits()
    assert client.get("/api/v1/lists", headers=_auth(token)).status_code == 200
    assert client.get("/api/v1/lists", headers=_auth(token)).status_code == 200
    assert client.get("/api/v1/lists", headers=_auth(token)).status_code == 429
