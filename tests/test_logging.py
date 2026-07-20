"""Logging is parametrized (LOG_LEVEL) and the worker reports its job lifecycle.

Hermetic: a stubbed DigiKey client, no network. These assert on *behaviour* (which events
are logged at which level), not on exact message formatting.
"""
import logging

import pytest

from capinator.resolvers import DEFAULT_COMPONENT_TYPE
from webapp.db import Base, SessionLocal, engine
from webapp.logging_setup import configure_logging
from webapp.models import Job
from webapp.worker import worker


class FakeApi:
    def __init__(self):
        self.call_count = 0
        self.rate_limit_limit = 1000
        self.rate_limit_remaining = 990

    def find_digikey_pn_by_moq(self, params):
        self.call_count += 1
        self.rate_limit_remaining -= 1
        return "PN-" + params.get("capacitance", "x")


class BoomApi(FakeApi):
    def find_digikey_pn_by_moq(self, params):
        raise RuntimeError("digikey exploded")


@pytest.fixture
def db():
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def restore_log_levels():
    """configure_logging mutates global logger levels — put them back afterwards."""
    names = ["", "capinator", "webapp"]
    saved = {n: logging.getLogger(n).level for n in names}
    yield
    for name, level in saved.items():
        logging.getLogger(name).setLevel(level)


def _queued_job(db):
    job = Job(
        component_type=DEFAULT_COMPONENT_TYPE,
        input_components=[{"qty": "1", "capacitance": "100", "voltage": "50"}],
        input_hash="h", status="queued",
    )
    db.add(job)
    db.commit()
    return job.id


def test_configure_logging_raises_our_namespaces_but_leaves_root_quiet(restore_log_levels):
    configure_logging("DEBUG")
    assert logging.getLogger("capinator").level == logging.DEBUG
    assert logging.getLogger("webapp").level == logging.DEBUG
    # The anti-flood guarantee: root stays quiet, so urllib3/requests DEBUG chatter on
    # every DigiKey call doesn't drown the log.
    assert logging.getLogger().level == logging.WARNING


def test_worker_logs_job_claimed_and_done(db, caplog):
    worker._clients[DEFAULT_COMPONENT_TYPE] = FakeApi()
    job_id = _queued_job(db)
    try:
        with caplog.at_level(logging.INFO, logger="capinator.worker"):
            worker._process(job_id)
    finally:
        worker._clients.clear()

    text = caplog.text
    assert f"job {job_id}" in text
    assert "done" in text
    assert "DigiKey call" in text          # the completion line reports the call count


def test_row_level_error_still_completes_with_a_note(db, caplog):
    """build_bom continues on error, so a bad row is a *note*, not a job failure —
    the completion line surfaces the note count."""
    worker._clients[DEFAULT_COMPONENT_TYPE] = BoomApi()
    job_id = _queued_job(db)
    try:
        with caplog.at_level(logging.INFO, logger="capinator.worker"):
            worker._process(job_id)
    finally:
        worker._clients.clear()

    assert "done" in caplog.text and "row note" in caplog.text
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]


def test_worker_logs_job_level_failure_at_error(db, caplog):
    """A failure *outside* the row loop (here: an unknown component type) fails the job."""
    job = Job(
        component_type="no_such_component_type",
        input_components=[{"qty": "1", "capacitance": "100", "voltage": "50"}],
        input_hash="h", status="queued",
    )
    db.add(job)
    db.commit()
    job_id = job.id

    with caplog.at_level(logging.INFO, logger="capinator.worker"):
        worker._process(job_id)

    errors = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert errors, "a job-level failure should log at ERROR"
    assert f"job {job_id}" in caplog.text and "failed" in caplog.text
