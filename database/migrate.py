"""Applies database changes in order.

Each file in database/migrations is one change. A change is applied once, and
its name is recorded so it is never applied twice.

Run from the project root:  python -m database.migrate
"""

from __future__ import annotations

import os
from pathlib import Path

import psycopg

MIGRATIONS = Path(__file__).parent / "migrations"


def apply_migrations(database_url: str) -> list[str]:
    """Apply every change not yet applied. Returns the names it applied."""
    applied_now: list[str] = []
    with psycopg.connect(database_url) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            " name text PRIMARY KEY,"
            " applied_at timestamptz NOT NULL DEFAULT now())"
        )
        done = {row[0] for row in conn.execute("SELECT name FROM schema_migrations")}
        for path in sorted(MIGRATIONS.glob("*.sql")):
            if path.name in done:
                continue
            # Each change runs inside one transaction: it applies fully or not at all.
            with conn.transaction():
                conn.execute(path.read_text())
                conn.execute("INSERT INTO schema_migrations (name) VALUES (%s)", (path.name,))
            applied_now.append(path.name)
    return applied_now


if __name__ == "__main__":
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("Set DATABASE_URL first. See README.md.")
    names = apply_migrations(url)
    print("Applied: " + ", ".join(names) if names else "Database is already up to date.")
