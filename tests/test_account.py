"""Account page tests: keys require login, the token is shown exactly once, and revoking
a key both hides it and disables it for the API."""
import re

import pytest
from fastapi.testclient import TestClient

from webapp import apikeys
from webapp.db import Base, SessionLocal, engine
from webapp.main import app
from webapp.models import ApiKey

TOKEN_RE = re.compile(r"cap_[A-Za-z0-9_-]+")


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.create_all(bind=engine)
    apikeys.reset_rate_limits()
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    return TestClient(app)


def _register(client, email="acct@x.com"):
    client.post("/register", data={"email": email, "password": "pw"})


def test_account_requires_login(client):
    # anonymous visitors are redirected to /login (same as /lists)
    assert client.get("/account").url.path == "/login"


def test_create_key_reveals_token_once_then_masked(client):
    _register(client)
    r = client.post("/account/api-keys", data={"name": "laptop"})
    assert r.status_code == 200 and "won't be shown again" in r.text
    token = TOKEN_RE.search(r.text).group(0)

    page = client.get("/account")           # revisit: full token must NOT reappear
    assert token not in page.text
    assert "laptop" in page.text            # key still listed by name
    assert token[:12] in page.text          # ...and by its non-secret prefix


def test_revoke_hides_and_disables_key(client):
    _register(client)
    created = client.post("/account/api-keys", data={"name": "k"})
    token = TOKEN_RE.search(created.text).group(0)

    db = SessionLocal()
    try:
        key_id = db.query(ApiKey).one().id
    finally:
        db.close()

    revoked = client.post(f"/account/api-keys/{key_id}/revoke")
    assert revoked.status_code == 200
    assert token[:12] not in revoked.text   # no longer listed

    # the revoked key no longer authenticates the API
    assert client.get("/api/v1/lists", headers={"Authorization": f"Bearer {token}"}).status_code == 401
