"""API-key generation, hashing, verification, and the ``require_api_key`` dependency
for the public read-only API.

Only an HMAC-SHA256 digest of each token is stored (keyed by ``settings.secret_key``),
never the plaintext. Tokens are high-entropy random strings, so a fast keyed hash is the
right choice — bcrypt would needlessly slow every request, and HMAC-with-secret means a
DB leak alone can't forge or look keys up. The plaintext ``cap_…`` token is shown to the
user exactly once, at creation.
"""
import hashlib
import hmac
import secrets
import time
from datetime import timedelta
from typing import Dict, List, Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from webapp.config import settings
from webapp.db import get_db
from webapp.models import ApiKey, User, utcnow

TOKEN_PREFIX = "cap_"

# Declaring the scheme (rather than reading the header by hand) is what makes the Swagger
# UI at /api/docs render an "Authorize" button so tokens can be entered in "Try it out".
# auto_error=False so we keep our own 401 messages instead of HTTPBearer's generic 403.
bearer_scheme = HTTPBearer(
    auto_error=False,
    description="Your `cap_…` API key (create one on your account page).",
)
# The non-secret slice stored/displayed and used for O(1) lookup ("cap_" + 8 chars).
PREFIX_LEN = 12
# Don't write last_used_at on every request; only when it's this stale.
_TOUCH_INTERVAL = timedelta(minutes=1)


def hash_token(token: str) -> str:
    return hmac.new(
        settings.secret_key.encode(), token.encode(), hashlib.sha256
    ).hexdigest()


def generate() -> tuple[str, str, str]:
    """Return ``(token, prefix, key_hash)`` for a fresh key."""
    token = TOKEN_PREFIX + secrets.token_urlsafe(32)
    return token, token[:PREFIX_LEN], hash_token(token)


def create_key(db: Session, user: User, name: str) -> tuple[ApiKey, str]:
    """Create and persist a key; return the row and the one-time plaintext token."""
    token, prefix, key_hash = generate()
    key = ApiKey(user_id=user.id, name=name.strip() or "API key", prefix=prefix, key_hash=key_hash)
    db.add(key)
    db.commit()
    db.refresh(key)
    return key, token


def verify(db: Session, presented: str) -> Optional[ApiKey]:
    """Return the matching active ApiKey for a presented token, else None. Pure lookup —
    no writes (``require_api_key`` records usage)."""
    if not presented or not presented.startswith(TOKEN_PREFIX):
        return None
    candidates = db.scalars(
        select(ApiKey).where(ApiKey.prefix == presented[:PREFIX_LEN])
    ).all()
    computed = hash_token(presented)
    for key in candidates:
        if hmac.compare_digest(key.key_hash, computed) and key.is_active:
            return key
    return None


# --- per-key rate limiting (fixed 60s window; single-process, so in-memory is fine) ---
_rate_state: Dict[int, List[float]] = {}  # key_id -> [window_start, count]


def _within_rate_limit(key_id: int) -> bool:
    now = time.monotonic()
    state = _rate_state.get(key_id)
    if state is None or now - state[0] >= 60:
        _rate_state[key_id] = [now, 1]
        return True
    if state[1] >= settings.api_rate_limit_per_min:
        return False
    state[1] += 1
    return True


def reset_rate_limits() -> None:
    """Clear the in-memory rate-limit state (used by tests)."""
    _rate_state.clear()


def _touch_last_used(db: Session, key: ApiKey) -> None:
    now = utcnow()
    if key.last_used_at is None or now - key.last_used_at > _TOUCH_INTERVAL:
        key.last_used_at = now
        db.commit()


def require_api_key(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """FastAPI dependency: authenticate via ``Authorization: Bearer <token>`` (declared as
    an OpenAPI bearer scheme so Swagger's "Authorize" works), enforce the per-key rate
    limit, and return the owning user."""
    token = credentials.credentials.strip() if credentials else ""
    if not token:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Missing or malformed Authorization header (use 'Bearer <api-key>').",
            headers={"WWW-Authenticate": "Bearer"},
        )
    key = verify(db, token)
    if key is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Invalid or revoked API key.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not _within_rate_limit(key.id):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Rate limit exceeded.",
            headers={"Retry-After": "60"},
        )
    _touch_last_used(db, key)
    return key.user
