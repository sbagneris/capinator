"""Full-page routes: home, auth (register/login/logout), and the user's saved lists."""
from typing import Optional

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from capinator.bom import to_csv
from webapp.auth import (
    current_user,
    get_or_create_guest_id,
    get_user_by_email,
    hash_password,
    login_user,
    logout_user,
    verify_password,
)
from webapp.config import settings
from webapp.db import get_db
from webapp.models import ComponentList, User
from webapp.services import guest_jobs_last_24h
from webapp.templating import render

router = APIRouter()


@router.get("/")
def home(
    request: Request,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(current_user),
):
    guest_used = None
    if user is None:
        guest_id = get_or_create_guest_id(request)
        guest_used = guest_jobs_last_24h(db, guest_id)
    return render(
        "index.html",
        {
            "request": request,
            "user": user,
            "guest_used": guest_used,
            "guest_limit": settings.guest_job_limit,
        },
    )


# ---- auth ----------------------------------------------------------------
@router.get("/register")
def register_form(request: Request, user: Optional[User] = Depends(current_user)):
    return render("register.html", {"request": request, "user": user})


@router.post("/register")
def register_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    email = email.strip().lower()
    if not email or not password:
        return render(
            "register.html",
            {"request": request, "error": "Email and password are required.", "user": None},
            status_code=400,
        )
    if get_user_by_email(db, email) is not None:
        return render(
            "register.html",
            {"request": request, "error": "That email is already registered.", "user": None},
            status_code=400,
        )
    user = User(email=email, password_hash=hash_password(password))
    db.add(user)
    db.commit()
    login_user(request, user)
    return RedirectResponse("/", status_code=303)


@router.get("/login")
def login_form(request: Request, user: Optional[User] = Depends(current_user)):
    return render("login.html", {"request": request, "user": user})


@router.post("/login")
def login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = get_user_by_email(db, email)
    if user is None or not verify_password(password, user.password_hash):
        return render(
            "login.html",
            {"request": request, "error": "Invalid email or password.", "user": None},
            status_code=401,
        )
    login_user(request, user)
    return RedirectResponse("/", status_code=303)


@router.post("/logout")
def logout(request: Request):
    logout_user(request)
    return RedirectResponse("/", status_code=303)


# ---- saved lists ---------------------------------------------------------
@router.get("/lists")
def my_lists(
    request: Request,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(current_user),
):
    if user is None:
        return RedirectResponse("/login", status_code=303)
    lists = db.scalars(
        select(ComponentList)
        .where(ComponentList.owner_id == user.id)
        .order_by(ComponentList.updated_at.desc())
    ).all()
    return render(
        "lists.html", {"request": request, "user": user, "lists": lists}
    )


@router.get("/lists/{list_id}")
def list_detail(
    request: Request,
    list_id: int,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(current_user),
):
    component_list = db.get(ComponentList, list_id)
    if component_list is None:
        return render(
            "fragments/error.html",
            {"request": request, "message": "List not found."},
            status_code=404,
        )
    # MVP: only the owner may view (public sharing is Phase 2).
    if user is None or component_list.owner_id != user.id:
        return RedirectResponse("/login", status_code=303)
    return render(
        "list_detail.html",
        {
            "request": request,
            "user": user,
            "cl": component_list,
            "source_csv": to_csv(component_list.components or []),
        },
    )
