"""Public, read-only API — a FastAPI sub-app mounted at ``/api``.

Authenticated per request with an API key (Bearer). It serves only already-stored data
(a list's ``components`` and its latest resolved parts list), so it makes **zero DigiKey
calls** and is fully decoupled from the DigiKey rate limit. A key grants read access to
its owner's own lists plus every publicly shared list.
"""
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from webapp.apikeys import require_api_key
from webapp.db import get_db
from webapp.models import ComponentList, User

API_DESCRIPTION = """\
Read-only access to component lists and their resolved DigiKey bulk-order parts lists.

**Authentication.** Every request needs an API key. Create one on your account page
(`/account`) and send it as a bearer token:

    Authorization: Bearer cap_xxxxxxxx...

A key grants read access to your own lists plus every publicly shared list.
"""

api_app = FastAPI(
    title="capinator API",
    version="1",
    description=API_DESCRIPTION,
    docs_url="/docs",
    redoc_url="/redoc",
)


class ResolutionOut(BaseModel):
    generated_at: datetime
    digikey_calls: int
    output: str  # DigiKey-ready bulk-order lines ("qty, part_number, spec")


class ListSummary(BaseModel):
    id: int
    name: str
    component_type: str
    device_make: Optional[str] = None
    device_model: Optional[str] = None
    board_reference: Optional[str] = None
    is_public: bool
    updated_at: datetime
    latest_generated_at: Optional[datetime] = None


class ListDetail(ListSummary):
    notes: Optional[str] = None
    components: List[Dict[str, Any]]
    result: Optional[ResolutionOut] = None


def _summary(cl: ComponentList) -> ListSummary:
    latest = cl.latest_resolution
    return ListSummary(
        id=cl.id,
        name=cl.name,
        component_type=cl.component_type,
        device_make=cl.device_make,
        device_model=cl.device_model,
        board_reference=cl.board_reference,
        is_public=cl.is_public,
        updated_at=cl.updated_at,
        latest_generated_at=latest.generated_at if latest else None,
    )


def _detail(cl: ComponentList) -> ListDetail:
    latest = cl.latest_resolution
    result = (
        ResolutionOut(
            generated_at=latest.generated_at,
            digikey_calls=latest.digikey_calls,
            output=latest.output,
        )
        if latest
        else None
    )
    return ListDetail(
        **_summary(cl).model_dump(),
        notes=cl.notes,
        components=cl.components or [],
        result=result,
    )


def _visible(user: User):
    """Lists the key's owner may read: their own, plus anything publicly shared."""
    return (ComponentList.owner_id == user.id) | (ComponentList.is_public.is_(True))


v1 = APIRouter(prefix="/v1", tags=["lists"])


@v1.get("/lists", response_model=List[ListSummary], summary="List accessible component lists")
def list_lists(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(require_api_key),
):
    rows = db.scalars(
        select(ComponentList)
        .where(_visible(user))
        .order_by(ComponentList.updated_at.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return [_summary(cl) for cl in rows]


@v1.get(
    "/lists/{list_id}",
    response_model=ListDetail,
    summary="Get one component list with its latest resolved parts list",
)
def get_list(
    list_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_api_key),
):
    cl = db.scalar(
        select(ComponentList).where(ComponentList.id == list_id, _visible(user))
    )
    if cl is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "List not found.")
    return _detail(cl)


api_app.include_router(v1)
