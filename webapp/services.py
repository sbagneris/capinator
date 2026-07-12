"""Shared job/resolution helpers used by the routers (and reusable by a future API)."""
import hashlib
import json
from datetime import timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from webapp.config import settings
from webapp.models import Job, Resolution, utcnow

DEDUPE_WINDOW = timedelta(hours=1)


def hash_components(components: List[Dict[str, Any]]) -> str:
    canonical = json.dumps(components, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def guest_jobs_last_24h(db: Session, guest_id: str) -> int:
    since = utcnow() - timedelta(days=1)
    return db.scalar(
        select(func.count())
        .select_from(Job)
        .where(Job.guest_id == guest_id, Job.created_at >= since)
    ) or 0


def guest_over_limit(db: Session, guest_id: str) -> bool:
    return guest_jobs_last_24h(db, guest_id) >= settings.guest_job_limit


def find_recent_done(db: Session, input_hash: str, component_type: str) -> Optional[Job]:
    since = utcnow() - DEDUPE_WINDOW
    return db.scalars(
        select(Job)
        .where(
            Job.input_hash == input_hash,
            Job.component_type == component_type,
            Job.status == "done",
            Job.created_at >= since,
        )
        .order_by(Job.created_at.desc())
        .limit(1)
    ).first()


def create_job(
    db: Session,
    *,
    components: List[Dict[str, Any]],
    component_type: str,
    user_id: Optional[int] = None,
    guest_id: Optional[str] = None,
    component_list_id: Optional[int] = None,
) -> Job:
    """Insert a job, reusing a recent identical result (dedupe) to spare the API."""
    input_hash = hash_components(components)
    job = Job(
        user_id=user_id,
        guest_id=guest_id,
        component_list_id=component_list_id,
        component_type=component_type,
        input_components=components,
        input_hash=input_hash,
        status="queued",
    )

    dupe = find_recent_done(db, input_hash, component_type)
    if dupe is not None:
        # Reuse the cached result: mark done immediately, no worker/API round-trip.
        job.status = "done"
        job.result = dupe.result
        job.error = dupe.error
        job.digikey_calls = 0
        job.remaining_quota = dupe.remaining_quota
        job.finished_at = utcnow()

    db.add(job)
    db.commit()
    return job


def ensure_resolution(db: Session, job: Job) -> Optional[Resolution]:
    """If a done job is tied to a ComponentList and has no Resolution yet, create one.

    Lets the generic worker stay unaware of ComponentLists: the Resolution for a
    regenerate is materialized lazily when the result is first observed.
    """
    if job.status != "done" or job.component_list_id is None:
        return None
    existing = db.scalar(select(Resolution).where(Resolution.job_id == job.id))
    if existing is not None:
        return existing
    resolution = Resolution(
        component_list_id=job.component_list_id,
        job_id=job.id,
        output=job.result or "",
        digikey_calls=job.digikey_calls,
    )
    db.add(resolution)
    db.commit()
    return resolution
