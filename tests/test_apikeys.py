"""Unit tests for the API-key module: generation, hashing, verification, revocation."""
from datetime import timedelta

import pytest

from webapp.apikeys import TOKEN_PREFIX, create_key, generate, hash_token, verify
from webapp.auth import hash_password
from webapp.db import Base, SessionLocal, engine
from webapp.models import User, utcnow


@pytest.fixture
def db():
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def _user(db, email="u@x.com"):
    u = User(email=email, password_hash=hash_password("pw"))
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def test_generate_shape():
    token, prefix, key_hash = generate()
    assert token.startswith(TOKEN_PREFIX)
    assert prefix == token[:12]
    assert key_hash == hash_token(token)
    assert len(key_hash) == 64  # sha256 hex digest


def test_create_stores_hash_not_plaintext(db):
    user = _user(db)
    key, token = create_key(db, user, "laptop")
    assert key.key_hash != token                # never store the plaintext
    assert key.key_hash == hash_token(token)
    assert token not in (key.prefix, key.key_hash)  # not recoverable from the row


def test_verify_roundtrip(db):
    user = _user(db)
    _, token = create_key(db, user, "k")
    matched = verify(db, token)
    assert matched is not None and matched.user_id == user.id


def test_verify_rejects_unknown_tampered_and_unprefixed(db):
    user = _user(db)
    _, token = create_key(db, user, "k")
    assert verify(db, "cap_not-a-real-key-value") is None
    assert verify(db, token + "x") is None          # same prefix, wrong hash
    assert verify(db, "no-bearer-prefix") is None    # missing cap_ prefix


def test_verify_rejects_revoked(db):
    user = _user(db)
    key, token = create_key(db, user, "k")
    key.revoked_at = utcnow()
    db.commit()
    assert verify(db, token) is None


def test_verify_rejects_expired(db):
    user = _user(db)
    key, token = create_key(db, user, "k")
    key.expires_at = utcnow() - timedelta(seconds=1)
    db.commit()
    assert verify(db, token) is None
