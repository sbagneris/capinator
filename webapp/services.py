"""Shared job/resolution helpers used by the routers (and reusable by a future API)."""
import hashlib
import json
from datetime import timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from webapp.config import settings
from webapp.models import ComponentList, Job, Resolution, User, utcnow

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


def list_jobs(
    db: Session, *, user_id: Optional[int] = None, guest_id: Optional[str] = None,
    limit: int = 50,
) -> List[Job]:
    """Recent jobs for one identity (a user, or a guest cookie), newest first."""
    stmt = select(Job)
    if user_id is not None:
        stmt = stmt.where(Job.user_id == user_id)
    elif guest_id is not None:
        stmt = stmt.where(Job.guest_id == guest_id, Job.user_id.is_(None))
    else:
        return []
    return list(db.scalars(stmt.order_by(Job.created_at.desc()).limit(limit)).all())


def _default_list_name(job: Job, device_make: str = "", device_model: str = "") -> str:
    label = " ".join(p for p in (device_make.strip(), device_model.strip()) if p).strip()
    return label or f"Untitled list · {job.created_at:%Y-%m-%d %H:%M}"


def _new_resolution(job: Job) -> Resolution:
    """A Resolution snapshotting a done job's output into its ComponentList."""
    return Resolution(
        component_list_id=job.component_list_id,
        job_id=job.id,
        output=job.result or "",
        digikey_calls=job.digikey_calls,
    )


def promote_job_to_list(
    db: Session, job: Job, user: User, *,
    name: str = "", device_make: str = "", device_model: str = "",
    board_reference: str = "", notes: str = "",
) -> Optional[ComponentList]:
    """Save-by-default: ensure a done job is backed by one of ``user``'s ComponentLists.

    Idempotent. An identical input (same ``input_hash``) that already maps to one of the
    user's lists **appends** a Resolution to that list instead of creating a duplicate.
    """
    if job.status != "done":
        return None
    if job.component_list_id is not None:
        return db.get(ComponentList, job.component_list_id)

    # Reuse an existing list whose input matches (dedupe via a prior promoted job).
    target: Optional[ComponentList] = None
    prior = db.scalars(
        select(Job)
        .where(
            Job.user_id == user.id,
            Job.input_hash == job.input_hash,
            Job.component_list_id.is_not(None),
            Job.id != job.id,
        )
        .order_by(Job.created_at.desc())
        .limit(1)
    ).first()
    if prior is not None:
        cl = db.get(ComponentList, prior.component_list_id)
        if cl is not None and cl.owner_id == user.id:
            target = cl

    if target is None:
        target = ComponentList(
            owner_id=user.id,
            name=name.strip() or _default_list_name(job, device_make, device_model),
            component_type=job.component_type,
            device_make=device_make or None,
            device_model=device_model or None,
            board_reference=board_reference or None,
            notes=notes or None,
            components=list(job.input_components or []),
        )
        db.add(target)
        db.flush()

    job.component_list_id = target.id
    if db.scalar(select(Resolution).where(Resolution.job_id == job.id)) is None:
        db.add(_new_resolution(job))
    db.commit()
    return target


def claim_guest_jobs(db: Session, *, guest_id: Optional[str], user: User) -> int:
    """On register/login, reassign a guest's jobs to the account and promote done ones."""
    if not guest_id:
        return 0
    jobs = list(db.scalars(
        select(Job).where(Job.guest_id == guest_id, Job.user_id.is_(None))
    ).all())
    for job in jobs:
        job.user_id = user.id
        job.guest_id = None
    db.commit()
    for job in jobs:
        if job.status == "done":
            promote_job_to_list(db, job, user)
    return len(jobs)


def purge_expired_guest_jobs(db: Session, *, now=None) -> int:
    """Delete unclaimed guest jobs older than the retention window. Returns the count."""
    cutoff = (now or utcnow()) - timedelta(hours=settings.guest_retention_hours)
    expired = list(db.scalars(
        select(Job).where(
            Job.user_id.is_(None),
            Job.guest_id.is_not(None),
            Job.created_at < cutoff,
        )
    ).all())
    for job in expired:
        db.delete(job)
    db.commit()
    return len(expired)


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
    resolution = _new_resolution(job)
    db.add(resolution)
    db.commit()
    return resolution
