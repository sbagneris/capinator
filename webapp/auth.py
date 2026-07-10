"""Authentication: password hashing, the ``current_user`` dependency, guest identity,
and the admin gate for the seed UI. Sessions are signed cookies (Starlette
``SessionMiddleware``); we store only ``user_id`` / ``guest_id`` in them.
"""
import uuid
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.orm import Session

from webapp.config import settings
from webapp.db import get_db
from webapp.models import User

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# A hash that no password can ever verify against — used for seed/curator accounts that
# must own lists but not be logged into (unless a real password is set later).
UNUSABLE_PASSWORD = "!"


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    if not password_hash or password_hash == UNUSABLE_PASSWORD:
        return False
    try:
        return pwd_context.verify(password, password_hash)
    except ValueError:
        return False


def get_user_by_email(db: Session, email: str) -> Optional[User]:
    return db.scalar(select(User).where(User.email == email.strip().lower()))


def current_user(
    request: Request, db: Session = Depends(get_db)
) -> Optional[User]:
    """Return the logged-in User, or None for a guest."""
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    return db.get(User, user_id)


def require_user(user: Optional[User] = Depends(current_user)) -> User:
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Login required")
    return user


def is_admin(user: Optional[User]) -> bool:
    return user is not None and user.email.strip().lower() in settings.admin_email_set


def require_admin(user: Optional[User] = Depends(current_user)) -> User:
    if not is_admin(user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin access required")
    return user


def get_or_create_guest_id(request: Request) -> str:
    """Stable per-browser guest id, stored in the signed session cookie."""
    guest_id = request.session.get("guest_id")
    if not guest_id:
        guest_id = uuid.uuid4().hex
        request.session["guest_id"] = guest_id
    return guest_id


def login_user(request: Request, user: User) -> None:
    request.session["user_id"] = user.id


def logout_user(request: Request) -> None:
    request.session.pop("user_id", None)
