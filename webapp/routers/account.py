"""Account page: create, view, and revoke the user's read-only API keys (HTMX)."""
from typing import List, Optional

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from webapp.apikeys import create_key
from webapp.auth import current_user, require_user
from webapp.db import get_db
from webapp.models import ApiKey, User, utcnow
from webapp.templating import render

router = APIRouter(prefix="/account")


def _active_keys(db: Session, user: User) -> List[ApiKey]:
    return list(
        db.scalars(
            select(ApiKey)
            .where(ApiKey.user_id == user.id, ApiKey.revoked_at.is_(None))
            .order_by(ApiKey.created_at.desc())
        ).all()
    )


@router.get("")
def account_home(
    request: Request,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(current_user),
):
    if user is None:  # match /lists: send anonymous visitors to log in
        return RedirectResponse("/login", status_code=303)
    return render(
        "account.html",
        {"request": request, "user": user, "keys": _active_keys(db, user), "new_token": None},
    )


@router.post("/api-keys")
def create_key_route(
    request: Request,
    name: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    _, token = create_key(db, user, name)
    # The plaintext token is returned exactly once, in the reveal box.
    return render(
        "fragments/account_body.html",
        {"request": request, "user": user, "keys": _active_keys(db, user), "new_token": token},
    )


@router.post("/api-keys/{key_id}/revoke")
def revoke_key_route(
    request: Request,
    key_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    key = db.get(ApiKey, key_id)
    if key is not None and key.user_id == user.id and key.revoked_at is None:
        key.revoked_at = utcnow()
        db.commit()
    return render(
        "fragments/account_body.html",
        {"request": request, "user": user, "keys": _active_keys(db, user), "new_token": None},
    )
