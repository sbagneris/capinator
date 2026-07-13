"""Job endpoints: create (guest-limit + dedupe), the Activity list, a full job-detail
page, the live poll fragment, regenerate, and the DigiKey quota fragment.

Save-by-default: a done job owned by a logged-in user is lazily promoted to a
ComponentList wherever it is rendered (``_promote_if_owner``), so nothing is ever lost by
navigating away. Guests keep a cookie-scoped Activity view; their runs are purged after
``settings.guest_retention_hours`` unless they register (which claims them)."""
from typing import Optional

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse

from sqlalchemy.orm import Session

from capinator.bom import to_csv
from capinator.resolvers import DEFAULT_COMPONENT_TYPE, get_resolver
from webapp.auth import current_user
from webapp.config import settings
from webapp.db import get_db
from webapp.models import ComponentList, Job, User
from webapp.services import (
    create_job,
    ensure_resolution,
    guest_over_limit,
    list_jobs,
    promote_job_to_list,
)
from webapp.auth import get_or_create_guest_id
from webapp.templating import render
from webapp.worker import quota_snapshot

router = APIRouter()

_META_FIELDS = ("name", "device_make", "device_model", "board_reference", "notes")


def _meta_key(job_id: int) -> str:
    return f"job_meta_{job_id}"


def _can_view(job: Job, user: Optional[User], request: Request) -> bool:
    """A job is visible to its owning user, or to the guest whose cookie created it."""
    if user is not None:
        return job.user_id == user.id
    guest_id = request.session.get("guest_id")
    return bool(guest_id) and job.guest_id == guest_id


def _promote_if_owner(
    request: Request, db: Session, job: Job, user: Optional[User]
) -> Optional[ComponentList]:
    """Save-by-default: a done job owned by a logged-in user becomes (or joins) a List."""
    if user is None or job.status != "done" or job.user_id != user.id:
        return None
    if job.component_list_id is not None:
        return db.get(ComponentList, job.component_list_id)
    meta = request.session.get(_meta_key(job.id), {})
    return promote_job_to_list(db, job, user, **{k: meta.get(k, "") for k in _META_FIELDS})


def _render_job_fragment(
    request: Request, db: Session, job: Job, user: Optional[User]
) -> HTMLResponse:
    ensure_resolution(db, job)  # materialize a Resolution for a regenerate, if applicable
    component_list = _promote_if_owner(request, db, job, user)
    return render(
        "fragments/job.html",
        {
            "request": request, "job": job, "user": user,
            "component_list": component_list,
            "guest_retention_hours": settings.guest_retention_hours,
        },
    )


def _error_fragment(request: Request, message: str, status_code: int = 400) -> HTMLResponse:
    return render(
        "fragments/error.html",
        {"request": request, "message": message},
        status_code=status_code,
    )


@router.post("/jobs")
def create_job_endpoint(
    request: Request,
    spec: str = Form(""),
    name: str = Form(""),
    device_make: str = Form(""),
    device_model: str = Form(""),
    board_reference: str = Form(""),
    notes: str = Form(""),
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(current_user),
):
    component_type = DEFAULT_COMPONENT_TYPE
    resolver = get_resolver(component_type)

    try:
        components = resolver.parse(spec)
    except Exception as e:
        return _error_fragment(request, f"Could not parse the list: {e}")
    if not components:
        return _error_fragment(request, "No components found — paste a CSV with a header row.")
    if len(components) > settings.max_spec_rows:
        return _error_fragment(
            request,
            f"Too many rows ({len(components)}); the limit is {settings.max_spec_rows}.",
        )

    guest_id = None
    if user is None:
        guest_id = get_or_create_guest_id(request)
        if guest_over_limit(db, guest_id):
            return render(
                "fragments/guest_limit.html",
                {"request": request, "limit": settings.guest_job_limit},
                status_code=429,
            )

    job = create_job(
        db,
        components=components,
        component_type=component_type,
        user_id=user.id if user else None,
        guest_id=guest_id,
    )

    # Stash the metadata typed on the home form so the auto-save can name/label the List.
    request.session[_meta_key(job.id)] = {
        "name": name, "device_make": device_make, "device_model": device_model,
        "board_reference": board_reference, "notes": notes,
    }
    return _render_job_fragment(request, db, job, user)


@router.get("/jobs")
def activity_endpoint(
    request: Request,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(current_user),
):
    """The current identity's run history (users by account, guests by cookie)."""
    if user is not None:
        jobs = list_jobs(db, user_id=user.id)
    else:
        guest_id = request.session.get("guest_id")
        jobs = list_jobs(db, guest_id=guest_id) if guest_id else []
    any_active = any(j.status in ("queued", "running") for j in jobs)
    return render(
        "activity.html",
        {
            "request": request, "user": user, "jobs": jobs, "any_active": any_active,
            "guest_retention_hours": settings.guest_retention_hours,
        },
    )


@router.get("/jobs/{job_id}/status")
def job_status_endpoint(
    request: Request,
    job_id: int,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(current_user),
):
    """The HTMX poll fragment used while a job is queued/running (and its final result)."""
    job = db.get(Job, job_id)
    if job is None or not _can_view(job, user, request):
        return _error_fragment(request, "Job not found.", status_code=404)
    return _render_job_fragment(request, db, job, user)


@router.get("/jobs/{job_id}")
def job_detail_endpoint(
    request: Request,
    job_id: int,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(current_user),
):
    """Full, shareable job page: the input component list plus the resolved parts list."""
    job = db.get(Job, job_id)
    if job is None or not _can_view(job, user, request):
        return _error_fragment(request, "Job not found.", status_code=404)
    ensure_resolution(db, job)
    component_list = _promote_if_owner(request, db, job, user)
    return render(
        "job_detail.html",
        {
            "request": request, "user": user, "job": job,
            "component_list": component_list,
            "source_csv": to_csv(job.input_components or []),
            "guest_retention_hours": settings.guest_retention_hours,
        },
    )


@router.get("/quota")
def quota_endpoint(request: Request, db: Session = Depends(get_db)):
    return render(
        "fragments/quota.html",
        {"request": request, "q": quota_snapshot(db)},
    )


@router.post("/lists/{list_id}/regenerate")
def regenerate_endpoint(
    request: Request,
    list_id: int,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(current_user),
):
    if user is None:
        return _error_fragment(request, "Please log in.", status_code=401)
    component_list = db.get(ComponentList, list_id)
    if component_list is None or component_list.owner_id != user.id:
        return _error_fragment(request, "List not found.", status_code=404)

    job = create_job(
        db,
        components=list(component_list.components or []),
        component_type=component_list.component_type,
        user_id=user.id,
        component_list_id=component_list.id,
    )
    return _render_job_fragment(request, db, job, user)
