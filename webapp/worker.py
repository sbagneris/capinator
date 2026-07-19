"""Standalone background worker.

Runs as its OWN process — `python -m webapp.worker`; the web app no longer starts it. It
polls the jobs table and runs queued jobs one at a time (this serialization *is* the
DigiKey rate-limit throttle), backs off when the shared key's remaining quota runs low,
sweeps expired guest jobs, and persists its rate-limit state to the DB (``WorkerState``) so
the web tier — a different process — can display it via ``quota_snapshot``. Exactly ONE
worker instance must run (the simple claim below is race-free only with a single worker;
more would need ``FOR UPDATE SKIP LOCKED``).
"""
import logging
import signal
import threading
import time
from typing import Any, Dict, Optional

from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError, ProgrammingError

from capinator.resolvers import get_resolver
from webapp.config import settings
from webapp.db import SessionLocal
from webapp.models import Job, WorkerState, utcnow
from webapp.services import purge_expired_guest_jobs

log = logging.getLogger("capinator.worker")

POLL_SECONDS = 1.0
BACKOFF_SECONDS = 60.0
PURGE_INTERVAL_SECONDS = 3600.0  # sweep unclaimed expired guest jobs at most hourly
READINESS_RETRY_SECONDS = 2.0    # wait between DB-readiness attempts (app runs migrations)


def save_worker_state(db, *, limit: int, remaining: Optional[int], backing_off: bool) -> None:
    """Upsert the singleton WorkerState row (id=1)."""
    state = db.get(WorkerState, 1)
    if state is None:
        state = WorkerState(id=1)
        db.add(state)
    state.rate_limit_limit = limit
    state.rate_limit_remaining = remaining
    state.backing_off = backing_off
    db.commit()


def quota_snapshot(db) -> Dict[str, Any]:
    """Live usage snapshot for GET /quota: the worker's persisted rate-limit state plus
    queue depth. Reads the DB (the worker is a different process), not worker memory."""
    state = db.get(WorkerState, 1)
    queued = db.scalar(select(func.count()).select_from(Job).where(Job.status == "queued"))
    running = db.scalar(select(func.count()).select_from(Job).where(Job.status == "running"))
    return {
        "rate_limit_limit": state.rate_limit_limit if state else 0,
        "rate_limit_remaining": state.rate_limit_remaining if state else None,
        "backing_off": state.backing_off if state else False,
        "queued": queued or 0,
        "running": running or 0,
    }


class Worker:
    def __init__(self) -> None:
        self._stop = threading.Event()
        self._clients: Dict[str, Any] = {}   # component_type -> API client singleton
        self._last_purge: float = 0.0
        # Latest usage, mirrored to the DB (WorkerState) for the web tier.
        self.rate_limit_limit: int = 0
        self.rate_limit_remaining: Optional[int] = None
        self.backing_off: bool = False

    # ---- lifecycle (standalone process) ---------------------------------
    def run_forever(self) -> None:
        """Foreground entry point for `python -m webapp.worker`."""
        self._await_db_ready()      # the app runs migrations; wait until the schema exists
        self._requeue_orphans()
        self._persist_state()
        self._run()

    def stop(self) -> None:
        self._stop.set()

    def _await_db_ready(self) -> None:
        """Block until the DB is reachable and migrated (a jobs-table read succeeds)."""
        while not self._stop.is_set():
            db = SessionLocal()
            try:
                db.scalar(select(func.count()).select_from(Job))
                return
            except (OperationalError, ProgrammingError) as e:
                log.warning("database not ready (%s) — retrying in %ss",
                            type(e).__name__, READINESS_RETRY_SECONDS)
                self._stop.wait(READINESS_RETRY_SECONDS)
            finally:
                db.close()

    def _requeue_orphans(self) -> None:
        """A job left 'running' means the process died mid-job — reset it to queued."""
        db = SessionLocal()
        try:
            orphans = db.scalars(select(Job).where(Job.status == "running")).all()
            for job in orphans:
                job.status = "queued"
            if orphans:
                db.commit()
        finally:
            db.close()

    # ---- main loop -------------------------------------------------------
    def _maybe_purge(self) -> None:
        """Sweep unclaimed expired guest jobs, at most once per PURGE_INTERVAL_SECONDS."""
        now = time.monotonic()
        if now - self._last_purge < PURGE_INTERVAL_SECONDS:
            return
        self._last_purge = now
        db = SessionLocal()
        try:
            purge_expired_guest_jobs(db)
        finally:
            db.close()

    def _run(self) -> None:
        while not self._stop.is_set():
            self._maybe_purge()
            if self._should_backoff():
                if not self.backing_off:
                    self.backing_off = True
                    self._persist_state()
                self._stop.wait(BACKOFF_SECONDS)
                # Force a fresh reading on the next real query after the window resets.
                self.rate_limit_remaining = None
                continue
            self.backing_off = False

            job_id = self._claim_next_job()
            if job_id is None:
                self._stop.wait(POLL_SECONDS)
                continue
            self._process(job_id)

    def _should_backoff(self) -> bool:
        return (
            self.rate_limit_remaining is not None
            and self.rate_limit_remaining <= settings.quota_low_water
        )

    def _claim_next_job(self) -> Optional[int]:
        """Atomically pick the oldest queued job and mark it running; return its id."""
        db = SessionLocal()
        try:
            job = db.scalars(
                select(Job).where(Job.status == "queued").order_by(Job.created_at).limit(1)
            ).first()
            if job is None:
                return None
            job.status = "running"
            db.commit()
            return job.id
        finally:
            db.close()

    def _get_client(self, component_type: str) -> Any:
        client = self._clients.get(component_type)
        if client is None:
            client = get_resolver(component_type).new_client()
            self._clients[component_type] = client
        return client

    def _process(self, job_id: int) -> None:
        db = SessionLocal()
        try:
            job = db.get(Job, job_id)
            if job is None:
                return
            try:
                resolver = get_resolver(job.component_type)
                api = self._get_client(job.component_type)
                result = resolver.resolve(list(job.input_components or []), api)
                job.result = result.output
                job.digikey_calls = result.digikey_calls
                job.error = "\n".join(result.errors) if result.errors else None
                job.status = "done"
                self._snapshot_from_client(api)
                job.remaining_quota = self.rate_limit_remaining
            except Exception as e:  # missing creds, API failure, unknown type, ...
                job.status = "error"
                job.error = str(e)
            finally:
                job.finished_at = utcnow()
                db.commit()
        finally:
            db.close()
        self._persist_state()  # mirror the latest rate-limit state to the DB for the web tier

    def _snapshot_from_client(self, api: Any) -> None:
        self.rate_limit_limit = getattr(api, "rate_limit_limit", self.rate_limit_limit)
        self.rate_limit_remaining = getattr(api, "rate_limit_remaining", self.rate_limit_remaining)

    def _persist_state(self) -> None:
        db = SessionLocal()
        try:
            save_worker_state(
                db, limit=self.rate_limit_limit,
                remaining=self.rate_limit_remaining, backing_off=self.backing_off,
            )
        finally:
            db.close()


# Process-wide singleton (also reused by tests, which call `_process` directly).
worker = Worker()


def main() -> None:
    """`python -m webapp.worker`: run the worker until SIGTERM/SIGINT."""
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )

    def _handle(signum, _frame):
        log.info("received signal %s — shutting down", signum)
        worker.stop()

    signal.signal(signal.SIGTERM, _handle)
    signal.signal(signal.SIGINT, _handle)
    log.info("capinator worker starting")
    worker.run_forever()
    log.info("capinator worker stopped")


if __name__ == "__main__":
    main()
