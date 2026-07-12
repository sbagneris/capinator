"""Job endpoints: create (with guest-limit + dedupe), poll, save-as-list, regenerate,
and the live DigiKey quota fragment."""
from typing import Optional

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.orm import Session

from capinator.resolvers import DEFAULT_COMPONENT_TYPE, get_resolver
from webapp.auth import current_user, get_or_create_guest_id
from webapp.config import settings
from webapp.db import get_db
from webapp.models import ComponentList, Job, Resolution, User
from webapp.services import create_job, ensure_resolution, guest_over_limit
from webapp.templating import render
from webapp.worker import quota_snapshot

router = APIRouter()


def _meta_key(job_id: int) -> str:
    return f"job_meta_{job_id}"


def _render_job(request: Request, db: Session, job: Job, user: Optional[User]) -> HTMLResponse:
    ensure_resolution(db, job)  # materialize a Resolution for a regenerate, if applicable
    meta = request.session.get(_meta_key(job.id), {})
    return render(
        "fragments/job.html",
        {"request": request, "job": job, "user": user, "meta": meta},
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

    # Stash the metadata typed on the home form so the Save step can prefill it.
    request.session[_meta_key(job.id)] = {
        "name": name, "device_make": device_make, "device_model": device_model,
        "board_reference": board_reference, "notes": notes,
    }
    return _render_job(request, db, job, user)


@router.get("/jobs/{job_id}")
def get_job_endpoint(
    request: Request,
    job_id: int,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(current_user),
):
    job = db.get(Job, job_id)
    if job is None:
        return _error_fragment(request, "Job not found.", status_code=404)
    return _render_job(request, db, job, user)


@router.get("/quota")
def quota_endpoint(request: Request, db: Session = Depends(get_db)):
    return render(
        "fragments/quota.html",
        {"request": request, "q": quota_snapshot(db)},
    )


@router.post("/lists")
def save_list_endpoint(
    request: Request,
    job_id: int = Form(...),
    name: str = Form(""),
    device_make: str = Form(""),
    device_model: str = Form(""),
    board_reference: str = Form(""),
    notes: str = Form(""),
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(current_user),
):
    if user is None:
        return _error_fragment(request, "Please log in to save lists.", status_code=401)
    job = db.get(Job, job_id)
    if job is None or job.status != "done":
        return _error_fragment(request, "Nothing to save yet.", status_code=400)

    component_list = ComponentList(
        owner_id=user.id,
        name=name.strip() or "Untitled list",
        component_type=job.component_type,
        device_make=device_make or None,
        device_model=device_model or None,
        board_reference=board_reference or None,
        notes=notes or None,
        components=list(job.input_components or []),
    )
    db.add(component_list)
    db.flush()

    # Persist both sides: the input list AND its first resolved output.
    db.add(Resolution(
        component_list_id=component_list.id,
        job_id=job.id,
        output=job.result or "",
        digikey_calls=job.digikey_calls,
    ))
    job.component_list_id = component_list.id
    db.commit()

    request.session.pop(_meta_key(job.id), None)
    # Tell HTMX to navigate to the new list's detail page.
    return Response(status_code=204, headers={"HX-Redirect": f"/lists/{component_list.id}"})


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
    return _render_job(request, db, job, user)
