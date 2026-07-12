"""Single in-process background worker.

One daemon thread, in the same process as the web app, runs queued jobs one at a time —
this serialization *is* the DigiKey rate-limit throttle. It holds one long-lived client
per component_type (built lazily on first use, so the app boots without creds and a warm
facet cache costs zero extra queries), requeues orphaned ``running`` jobs on startup, and
backs off when the shared key's remaining quota runs low.
"""
import threading
from typing import Any, Dict, Optional

from sqlalchemy import func, select

from capinator.resolvers import get_resolver
from webapp.config import settings
from webapp.db import SessionLocal
from webapp.models import Job, utcnow

POLL_SECONDS = 1.0
BACKOFF_SECONDS = 60.0


class Worker:
    def __init__(self) -> None:
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._clients: Dict[str, Any] = {}   # component_type -> API client singleton
        # Latest usage snapshot, surfaced to the UI via GET /quota.
        self.rate_limit_limit: int = 0
        self.rate_limit_remaining: Optional[int] = None
        self.backing_off: bool = False

    # ---- lifecycle -------------------------------------------------------
    def start(self) -> None:
        self._requeue_orphans()
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="capinator-worker", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)

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
    def _run(self) -> None:
        while not self._stop.is_set():
            if self._should_backoff():
                self.backing_off = True
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

    def _snapshot_from_client(self, api: Any) -> None:
        self.rate_limit_limit = getattr(api, "rate_limit_limit", self.rate_limit_limit)
        self.rate_limit_remaining = getattr(api, "rate_limit_remaining", self.rate_limit_remaining)


# Process-wide singleton.
worker = Worker()


def quota_snapshot(db) -> Dict[str, Any]:
    """Live usage snapshot for GET /quota: worker rate-limit state + queue depth."""
    queued = db.scalar(select(func.count()).select_from(Job).where(Job.status == "queued"))
    running = db.scalar(select(func.count()).select_from(Job).where(Job.status == "running"))
    return {
        "rate_limit_limit": worker.rate_limit_limit,
        "rate_limit_remaining": worker.rate_limit_remaining,
        "backing_off": worker.backing_off,
        "queued": queued or 0,
        "running": running or 0,
    }
