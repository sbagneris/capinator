"""SQLAlchemy 2.0 models.

The per-component search parameters are stored as a single JSON column
(``ComponentList.components`` / ``Job.input_components``) — an array of objects whose
keys are the CSV header — not a child table and not fixed columns, so the schema
generalizes to any component type. CSV is a derived view (see ``capinator.bom.to_csv``).
"""
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from capinator.resolvers import DEFAULT_COMPONENT_TYPE
from webapp.db import Base


def utcnow() -> datetime:
    # Naive UTC: SQLite's DateTime stores naive datetimes, so we keep everything naive
    # to make range comparisons (e.g. guest-limit windows) consistent.
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    lists: Mapped[List["ComponentList"]] = relationship(
        back_populates="owner", cascade="all, delete-orphan"
    )
    api_keys: Mapped[List["ApiKey"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        order_by="ApiKey.created_at.desc()",
    )


class ComponentList(Base):
    __tablename__ = "component_lists"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(String(255))
    component_type: Mapped[str] = mapped_column(String(64), default=DEFAULT_COMPONENT_TYPE)
    device_make: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    device_model: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    board_reference: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Canonical, structured store of the per-component search parameters.
    components: Mapped[list] = mapped_column(JSON, default=list)

    is_public: Mapped[bool] = mapped_column(Boolean, default=False)
    # Stable id for flat-file (YAML) upsert; NULL for lists created via the web UI.
    seed_key: Mapped[Optional[str]] = mapped_column(String(255), unique=True, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    owner: Mapped["User"] = relationship(back_populates="lists")
    resolutions: Mapped[List["Resolution"]] = relationship(
        back_populates="component_list",
        cascade="all, delete-orphan",
        order_by="Resolution.generated_at.desc()",
    )

    @property
    def latest_resolution(self) -> Optional["Resolution"]:
        return self.resolutions[0] if self.resolutions else None


class Resolution(Base):
    """A resolved parts list (output) for a ComponentList. History is kept; the current
    parts list is the newest by ``generated_at``."""
    __tablename__ = "resolutions"

    id: Mapped[int] = mapped_column(primary_key=True)
    component_list_id: Mapped[int] = mapped_column(ForeignKey("component_lists.id"))
    job_id: Mapped[Optional[int]] = mapped_column(ForeignKey("jobs.id"), nullable=True)
    output: Mapped[str] = mapped_column(Text, default="")
    generated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    digikey_calls: Mapped[int] = mapped_column(Integer, default=0)

    component_list: Mapped["ComponentList"] = relationship(back_populates="resolutions")


class ApiKey(Base):
    """A hashed key for the read-only public API. Only an HMAC-SHA256 digest is stored;
    the plaintext token (``cap_…``) is shown to the user exactly once at creation.
    ``prefix`` is a non-secret slice used for O(1) lookup and UI display."""
    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    prefix: Mapped[str] = mapped_column(String(16), index=True)
    key_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    user: Mapped["User"] = relationship(back_populates="api_keys")

    @property
    def is_active(self) -> bool:
        if self.revoked_at is not None:
            return False
        return self.expires_at is None or self.expires_at > utcnow()


class Job(Base):
    """A resolve job. Guests are identified by ``guest_id``; registered users by
    ``user_id``. ``input_components`` is the only stored form of the input."""
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    guest_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    component_list_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("component_lists.id"), nullable=True
    )

    component_type: Mapped[str] = mapped_column(String(64), default=DEFAULT_COMPONENT_TYPE)
    input_components: Mapped[list] = mapped_column(JSON, default=list)
    input_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)

    status: Mapped[str] = mapped_column(String(16), default="queued", index=True)
    result: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    digikey_calls: Mapped[int] = mapped_column(Integer, default=0)
    remaining_quota: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
