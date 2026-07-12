"""Hermetic web-layer tests: auth, guest limits, the job lifecycle (with a stubbed
DigiKey client injected into the worker), save/regenerate, and admin gating. No network,
no credentials — the worker's client is a fake and jobs are processed synchronously."""
import re

import pytest
from fastapi.testclient import TestClient

from capinator.resolvers import DEFAULT_COMPONENT_TYPE
from webapp.db import Base, SessionLocal, engine
from webapp.main import app
from webapp.models import ComponentList, Resolution
from webapp.worker import worker

SPEC = "qty,capacitance,voltage\n1,100,50\n2,220,35\n"
JOB_ID_RE = re.compile(r'id="job-(\d+)"')


class FakeApi:
    """Stand-in for DigiKeyV4: counts calls, decrements quota, returns a scripted P/N."""
    def __init__(self):
        self.call_count = 0
        self.rate_limit_limit = 1000
        self.rate_limit_remaining = 990

    def find_digikey_pn_by_moq(self, params):
        self.call_count += 1
        self.rate_limit_remaining -= 1
        return "PN-" + params.get("capacitance", "x")


@pytest.fixture(autouse=True)
def fresh_db_and_worker():
    Base.metadata.create_all(bind=engine)
    worker._clients[DEFAULT_COMPONENT_TYPE] = FakeApi()  # no real client / OAuth
    yield
    worker._clients.clear()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    # No context manager => lifespan/worker thread do not start; we drive jobs manually.
    return TestClient(app)


def _job_id(html: str) -> int:
    m = JOB_ID_RE.search(html)
    assert m, f"no job id in fragment: {html[:200]}"
    return int(m.group(1))


def _run_job(job_id: int):
    """Process a queued job synchronously through the worker's logic."""
    worker._process(job_id)


# ---- home / quota --------------------------------------------------------
def test_home_ok(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "Resolve a capacitor list" in r.text


def test_quota_unknown_before_any_job(client):
    r = client.get("/quota")
    assert r.status_code == 200
    assert "unknown" in r.text


# ---- auth ----------------------------------------------------------------
def test_register_login_logout(client):
    r = client.post("/register", data={"email": "a@b.com", "password": "pw"})
    assert r.status_code == 200 and r.url.path == "/"  # followed redirect home
    # logged in => My Lists reachable
    assert client.get("/lists").status_code == 200
    client.post("/logout")
    # after logout, /lists redirects to /login
    assert client.get("/lists").url.path == "/login"


def test_login_rejects_bad_password(client):
    client.post("/register", data={"email": "c@d.com", "password": "right"})
    client.post("/logout")
    r = client.post("/login", data={"email": "c@d.com", "password": "wrong"})
    assert r.status_code == 401


# ---- guest limit ---------------------------------------------------------
def test_guest_limit_blocks_after_two(client):
    # GUEST_JOB_LIMIT=2 (conftest). Distinct specs so nothing dedupes.
    assert client.post("/jobs", data={"spec": "qty,capacitance,voltage\n1,10,50\n"}).status_code == 200
    assert client.post("/jobs", data={"spec": "qty,capacitance,voltage\n1,20,50\n"}).status_code == 200
    third = client.post("/jobs", data={"spec": "qty,capacitance,voltage\n1,30,50\n"})
    assert third.status_code == 429
    assert "free jobs" in third.text


def test_bad_csv_is_400(client):
    r = client.post("/jobs", data={"spec": "not a real csv with no rows"})
    assert r.status_code == 400


# ---- job lifecycle -------------------------------------------------------
def test_job_lifecycle_done(client):
    created = client.post("/jobs", data={"spec": SPEC})
    assert created.status_code == 200
    jid = _job_id(created.text)
    _run_job(jid)
    done = client.get(f"/jobs/{jid}")
    assert "Done" in done.text
    assert "PN-100" in done.text and "PN-220" in done.text
    assert "DigiKey queries" in done.text
    db = SessionLocal()
    try:
        from webapp.models import Job
        assert db.get(Job, jid).digikey_calls == 2  # one query per row
    finally:
        db.close()


# ---- save + regenerate ---------------------------------------------------
def test_save_creates_list_and_resolution_then_regenerate_adds_second(client):
    client.post("/register", data={"email": "user@x.com", "password": "pw"})
    created = client.post("/jobs", data={"spec": SPEC})
    jid = _job_id(created.text)
    _run_job(jid)

    saved = client.post(
        "/lists", data={"job_id": jid, "name": "My recap"}, follow_redirects=False
    )
    assert saved.status_code == 204
    assert saved.headers["HX-Redirect"].startswith("/lists/")

    db = SessionLocal()
    try:
        cl = db.query(ComponentList).one()
        assert cl.name == "My recap"
        assert db.query(Resolution).count() == 1
        list_id = cl.id
    finally:
        db.close()

    regen = client.post(f"/lists/{list_id}/regenerate")
    new_jid = _job_id(regen.text)
    _run_job(new_jid)
    client.get(f"/jobs/{new_jid}")  # observing 'done' materializes the Resolution

    db = SessionLocal()
    try:
        assert db.query(Resolution).count() == 2  # history preserved
    finally:
        db.close()


# ---- admin gating --------------------------------------------------------
def test_admin_requires_admin(client):
    assert client.get("/admin").status_code == 403
    client.post("/register", data={"email": "nobody@x.com", "password": "pw"})
    assert client.get("/admin").status_code == 403


def test_admin_export_and_import_roundtrip(client):
    client.post("/register", data={"email": "admin@test.local", "password": "pw"})
    assert client.get("/admin").status_code == 200

    export = client.get("/admin/export")
    assert export.status_code == 200
    assert "attachment" in export.headers["content-disposition"]

    yaml_text = (
        "- key: t1\n  name: Test list\n  owner_email: admin@test.local\n"
        "  components:\n    - {qty: '1', capacitance: '100', voltage: '50'}\n"
    )
    imported = client.post("/admin/import", data={"yaml_text": yaml_text})
    assert imported.status_code == 200 and "created" in imported.text.lower()

    db = SessionLocal()
    try:
        assert db.query(ComponentList).filter_by(seed_key="t1").count() == 1
    finally:
        db.close()
