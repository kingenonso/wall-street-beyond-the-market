"""Passwords and login sessions."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from server.config import get_settings

SESSION_COOKIE = "wsbm_session"
_hasher = PasswordHasher()

# Checked when a login names an account that does not exist, so that a wrong
# email takes as long to reject as a wrong password. Otherwise the response
# time would reveal which emails are registered.
_DUMMY_HASH = _hasher.hash("not-a-real-password")


def hash_password(password: str) -> str:
    """Scramble a password one-way. The original can never be recovered from it."""
    return _hasher.hash(password)


def verify_password(password: str, stored_hash: str | None) -> bool:
    try:
        return _hasher.verify(stored_hash or _DUMMY_HASH, password) and stored_hash is not None
    except (VerificationError, InvalidHashError):
        return False


def create_session_token(player_id: str) -> str:
    """A signed pass proving who the player is. The server can check the
    signature, so the browser cannot forge or alter it."""
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload = {"sub": player_id, "iat": now, "exp": now + timedelta(days=settings.session_days)}
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")


def read_session_token(token: str) -> str | None:
    """Returns the player's id, or None if the pass is missing, altered or expired."""
    try:
        payload = jwt.decode(token, get_settings().secret_key, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None
    return payload.get("sub")
