"""Settings, read from the environment so no secret is ever written in the code."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache


@dataclass(frozen=True)
class Settings:
    database_url: str
    secret_key: str
    world_start: datetime
    cookie_secure: bool
    session_days: int = 7
    minimum_age: int = 18


@lru_cache
def get_settings() -> Settings:
    database_url = os.environ.get("DATABASE_URL")
    secret_key = os.environ.get("SECRET_KEY")
    if not database_url:
        raise RuntimeError("DATABASE_URL is not set. See README.md.")
    if not secret_key or len(secret_key) < 32:
        raise RuntimeError("SECRET_KEY must be set and at least 32 characters. See README.md.")

    # The moment the game world begins. Must include a time zone.
    world_start = datetime.fromisoformat(os.environ.get("WORLD_START", "2026-10-05T00:00:00+01:00"))
    if world_start.tzinfo is None:
        raise RuntimeError("WORLD_START must include a time zone, for example +01:00.")

    return Settings(
        database_url=database_url,
        secret_key=secret_key,
        world_start=world_start,
        # Cookies are sent over secure connections only, unless switched off for local work.
        cookie_secure=os.environ.get("COOKIE_SECURE", "true").lower() != "false",
    )
