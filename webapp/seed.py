"""Flat-file (YAML) seed catalog — the durable source of truth for component lists on
Render's ephemeral disk.

Pure, session-in / data-in functions shared by the startup auto-seed, the admin UI
endpoints, and tests. No CLI or filesystem is required to import lists — that keeps the
whole flow usable on a shell-less container.
"""
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from capinator.bom import REQUIRED_FIELDS
from capinator.resolvers import DEFAULT_COMPONENT_TYPE
from webapp.auth import UNUSABLE_PASSWORD, get_user_by_email
from webapp.config import settings
from webapp.models import ComponentList, User, utcnow

_META_FIELDS = ("name", "device_make", "device_model", "board_reference", "notes")


@dataclass
class ImportSummary:
    created: int = 0
    updated: int = 0


def parse_yaml(text: str) -> List[Dict[str, Any]]:
    data = yaml.safe_load(text) or []
    if not isinstance(data, list):
        raise ValueError("Seed YAML must be a list of component-list entries.")
    return data


def load_seed_file(path: str) -> List[Dict[str, Any]]:
    with open(path, encoding="utf-8") as f:
        return parse_yaml(f.read())


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (value or "").lower()).strip("-")
    return slug or "list"


def _normalize_components(raw: Any, component_type: str) -> List[Dict[str, str]]:
    """Coerce YAML component values to strings (YAML may read '100' as an int) and
    validate required fields so malformed seed data fails at import, not at resolve."""
    if not isinstance(raw, list) or not raw:
        raise ValueError("each entry needs a non-empty 'components' list")
    components: List[Dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("each component must be a mapping of field -> value")
        comp = {str(k): str(v) for k, v in item.items() if v is not None and v != ""}
        if component_type == DEFAULT_COMPONENT_TYPE:
            missing = [f for f in REQUIRED_FIELDS if not comp.get(f)]
            if missing:
                raise ValueError(f"component missing required field(s): {', '.join(missing)}")
        components.append(comp)
    return components


def _resolve_owner(db: Session, email: Optional[str]) -> User:
    email = (email or settings.seed_owner_email).strip().lower()
    user = get_user_by_email(db, email)
    if user is None:
        user = User(email=email, password_hash=UNUSABLE_PASSWORD)
        db.add(user)
        db.flush()  # assign an id for the FK
    return user


def import_lists(db: Session, data: List[Dict[str, Any]]) -> ImportSummary:
    """Idempotent upsert keyed on ``seed_key``. Update in place if present, else insert."""
    summary = ImportSummary()
    for entry in data:
        if not isinstance(entry, dict):
            raise ValueError("each seed entry must be a mapping")
        component_type = entry.get("component_type", DEFAULT_COMPONENT_TYPE)
        key = entry.get("key") or slugify(entry.get("name", ""))
        components = _normalize_components(entry.get("components"), component_type)
        owner = _resolve_owner(db, entry.get("owner_email"))

        existing = db.scalar(select(ComponentList).where(ComponentList.seed_key == key))
        target = existing or ComponentList(seed_key=key)
        target.owner_id = owner.id
        target.component_type = component_type
        target.components = components
        target.is_public = bool(entry.get("is_public", False))
        for field in _META_FIELDS:
            if field in entry:
                setattr(target, field, entry[field])
        if not target.name:
            target.name = key
        target.updated_at = utcnow()

        if existing is None:
            db.add(target)
            summary.created += 1
        else:
            summary.updated += 1

    db.commit()
    return summary


def export_lists(db: Session) -> str:
    """Serialize all component lists to YAML. Fills a stable ``seed_key`` for any list
    that lacks one (persisted), so the export round-trips through ``import_lists``."""
    lists = db.scalars(select(ComponentList).order_by(ComponentList.id)).all()
    changed = False
    entries: List[Dict[str, Any]] = []
    for cl in lists:
        if not cl.seed_key:
            cl.seed_key = slugify(cl.name) + f"-{cl.id}"
            changed = True
        entry: Dict[str, Any] = {
            "key": cl.seed_key,
            "name": cl.name,
            "component_type": cl.component_type,
        }
        for field in ("device_make", "device_model", "board_reference", "notes"):
            value = getattr(cl, field)
            if value:
                entry[field] = value
        entry["owner_email"] = cl.owner.email
        entry["is_public"] = cl.is_public
        entry["components"] = [dict(c) for c in (cl.components or [])]
        entries.append(entry)
    if changed:
        db.commit()
    return yaml.safe_dump(entries, sort_keys=False, allow_unicode=True)


def seed_from_file_if_present(db: Session) -> Optional[ImportSummary]:
    """Startup hook: auto-seed from the configured file if it exists."""
    import os

    if not settings.seed_on_startup or not os.path.exists(settings.seed_file):
        return None
    return import_lists(db, load_seed_file(settings.seed_file))
