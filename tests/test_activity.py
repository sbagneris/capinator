"""Tests for the activity / save-by-default service helpers (hermetic, DB-only)."""
from datetime import timedelta

import pytest

from webapp.db import Base, SessionLocal, engine
from webapp.models import ComponentList, Job, Resolution, User, utcnow
from webapp.services import (
    claim_guest_jobs,
    hash_components,
    list_jobs,
    promote_job_to_list,
    purge_expired_guest_jobs,
)


@pytest.fixture
def db():
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def _user(db, email="u@x.com"):
    user = User(email=email, password_hash="x")
    db.add(user)
    db.commit()
    return user


def _job(db, *, user_id=None, guest_id=None, components=None, status="done",
         result="PN-1", created_at=None):
    components = components if components is not None else [
        {"qty": "1", "capacitance": "100", "voltage": "50"}
    ]
    job = Job(
        user_id=user_id, guest_id=guest_id,
        component_type="aluminum_electrolytic_capacitor",
        input_components=components, input_hash=hash_components(components),
        status=status, result=result,
        **({"created_at": created_at} if created_at is not None else {}),
    )
    db.add(job)
    db.commit()
    return job


def test_list_jobs_scopes_to_identity(db):
    u = _user(db)
    other = _user(db, "other@x.com")
    ju = _job(db, user_id=u.id)
    _job(db, user_id=other.id)
    jg = _job(db, guest_id="g1")
    assert [j.id for j in list_jobs(db, user_id=u.id)] == [ju.id]
    assert [j.id for j in list_jobs(db, guest_id="g1")] == [jg.id]


def test_promote_creates_list_and_resolution(db):
    u = _user(db)
    j = _job(db, user_id=u.id, result="PN-1\nPN-2")
    cl = promote_job_to_list(db, j, u, name="Recap")
    assert cl.owner_id == u.id and cl.name == "Recap"
    assert j.component_list_id == cl.id
    res = db.query(Resolution).filter_by(component_list_id=cl.id).all()
    assert len(res) == 1 and res[0].output == "PN-1\nPN-2"


def test_promote_is_idempotent(db):
    u = _user(db)
    j = _job(db, user_id=u.id)
    cl1 = promote_job_to_list(db, j, u)
    cl2 = promote_job_to_list(db, j, u)
    assert cl1.id == cl2.id
    assert db.query(ComponentList).count() == 1
    assert db.query(Resolution).count() == 1


def test_promote_dedupes_identical_rerun_into_existing_list(db):
    u = _user(db)
    comps = [{"qty": "1", "capacitance": "100", "voltage": "50"}]
    j1 = _job(db, user_id=u.id, components=comps)
    cl = promote_job_to_list(db, j1, u)
    j2 = _job(db, user_id=u.id, components=comps)  # identical input
    cl2 = promote_job_to_list(db, j2, u)
    assert cl2.id == cl.id                       # same list, not a duplicate
    assert db.query(ComponentList).count() == 1
    assert db.query(Resolution).count() == 2      # history grows


def test_claim_guest_jobs_reassigns_and_promotes(db):
    u = _user(db)
    jg = _job(db, guest_id="g1", status="done")
    n = claim_guest_jobs(db, guest_id="g1", user=u)
    assert n == 1
    db.refresh(jg)
    assert jg.user_id == u.id and jg.guest_id is None
    assert db.query(ComponentList).filter_by(owner_id=u.id).count() == 1


def test_worker_maybe_purge_runs_on_interval_and_gates(db):
    import time

    from webapp.worker import PURGE_INTERVAL_SECONDS, worker

    old = _job(db, guest_id="g9", created_at=utcnow() - timedelta(hours=49))
    worker._last_purge = time.monotonic() - PURGE_INTERVAL_SECONDS - 1
    worker._maybe_purge()
    check = SessionLocal()
    try:
        assert check.get(Job, old.id) is None            # elapsed => purged
    finally:
        check.close()

    db.expunge_all()  # the worker's session deleted old; drop the stale identity here
    old2 = _job(db, guest_id="g8", created_at=utcnow() - timedelta(hours=49))
    worker._maybe_purge()                                 # interval not elapsed
    check = SessionLocal()
    try:
        assert check.get(Job, old2.id) is not None        # gated => kept
    finally:
        check.close()


def test_purge_expired_guest_jobs(db):
    u = _user(db)
    old_guest = _job(db, guest_id="g1", created_at=utcnow() - timedelta(hours=49))
    fresh_guest = _job(db, guest_id="g2", created_at=utcnow() - timedelta(hours=1))
    old_user = _job(db, user_id=u.id, created_at=utcnow() - timedelta(hours=49))
    deleted = purge_expired_guest_jobs(db)
    assert deleted == 1
    remaining = {j.id for j in db.query(Job).all()}
    assert old_guest.id not in remaining          # unclaimed + old => purged
    assert fresh_guest.id in remaining            # too new
    assert old_user.id in remaining               # claimed (has a user) => kept
