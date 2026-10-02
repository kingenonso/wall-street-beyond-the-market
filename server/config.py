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
    run_quarter_closer: bool = True
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    email_from: str = "no-reply@localhost"
    rate_limits: bool = True
    database_pool_size: int = 20
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
    if secret_key.startswith("change-me") or len(set(secret_key)) < 10:
        raise RuntimeError("SECRET_KEY is still the example value. Replace it with your own random text.")

    # The moment the game world begins. Must include a time zone. This is read only
    # when the world is first created; after that the world remembers its own start.
    world_start = datetime.fromisoformat(os.environ.get("WORLD_START", "2026-10-05T00:00:00+01:00"))
    if world_start.tzinfo is None:
        raise RuntimeError("WORLD_START must include a time zone, for example +01:00.")

    # The service that sends confirmation emails. Left empty on your own computer,
    # where the code is shown on screen instead. A real website must have one:
    # without it anybody could open accounts with addresses they do not own.
    smtp_host = os.environ.get("SMTP_HOST") or None
    cookie_secure = os.environ.get("COOKIE_SECURE", "true").lower() != "false"
    if cookie_secure and smtp_host is None:
        raise RuntimeError(
            "SMTP_HOST is not set. A real website must be able to send confirmation emails. See README.md."
        )

    return Settings(
        database_url=database_url,
        smtp_host=smtp_host,
        smtp_port=int(os.environ.get("SMTP_PORT", "587")),
        smtp_user=os.environ.get("SMTP_USER") or None,
        smtp_password=os.environ.get("SMTP_PASSWORD") or None,
        email_from=os.environ.get("EMAIL_FROM", "no-reply@localhost"),
        secret_key=secret_key,
        world_start=world_start,
        # Cookies are sent over secure connections only, unless switched off for local work.
        cookie_secure=cookie_secure,
        # The server closes each game quarter when it ends. Switched off in automated tests.
        run_quarter_closer=os.environ.get("RUN_QUARTER_CLOSER", "true").lower() != "false",
        # Limits on how fast one address may try to log in or sign up. Switched off in most tests.
        rate_limits=os.environ.get("RATE_LIMITS", "true").lower() != "false",
        database_pool_size=int(os.environ.get("DATABASE_POOL_SIZE", "20")),
    )
