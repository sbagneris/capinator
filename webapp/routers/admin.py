"""Admin UI for the flat-file seed catalog — the only way to get the YAML off the
shell-less Render container. Gated to ``ADMIN_EMAILS``."""
from typing import Optional

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from webapp.auth import current_user, is_admin, require_admin
from webapp.db import get_db
from webapp.models import User
from webapp.seed import export_lists, import_lists, parse_yaml
from webapp.templating import render

router = APIRouter(prefix="/admin")


@router.get("")
def admin_home(
    request: Request,
    user: Optional[User] = Depends(current_user),
    _: User = Depends(require_admin),
):
    return render(
        "admin.html", {"request": request, "user": user, "summary": None, "error": None}
    )


@router.get("/export")
def admin_export(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    yaml_text = export_lists(db)
    return Response(
        content=yaml_text,
        media_type="text/yaml",
        headers={"Content-Disposition": 'attachment; filename="component_lists.yaml"'},
    )


@router.post("/import")
def admin_import(
    request: Request,
    yaml_text: str = Form(""),
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(current_user),
    _: User = Depends(require_admin),
):
    summary = None
    error = None
    try:
        summary = import_lists(db, parse_yaml(yaml_text))
    except Exception as e:
        db.rollback()
        error = str(e)
    return render(
        "admin.html",
        {"request": request, "user": user, "summary": summary, "error": error},
        status_code=200 if error is None else 400,
    )
