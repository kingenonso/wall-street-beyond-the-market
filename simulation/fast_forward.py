"""Fast-forward, for testing only.

Run from the project root:

    python -m simulation.fast_forward 4        (four quarters: one game year)

It moves a TEST world's calendar ahead by that many weeks and closes the
quarters that have now ended, exactly as if the weeks had passed. The same
rules run in the same order; only the waiting is skipped.

It refuses to touch a live world. A world is a test world only if it was
created on a computer set up for testing (COOKIE_SECURE=false), and that
is fixed for good when the world is created. The database enforces it.
"""

from __future__ import annotations

import os
import sys
from datetime import UTC, datetime

import psycopg
from psycopg import Connection

from simulation import clock, ledger, quarters

MOST_AT_ONCE = 40      # ten game years


class NotATestWorld(ledger.LedgerError):
    pass


def fast_forward(conn: Connection, quarters_ahead: int, now: datetime) -> list[int]:
    """Move a test world ahead and close the quarters that have ended. Returns the quarters closed."""
    if isinstance(quarters_ahead, bool) or not isinstance(quarters_ahead, int) or not 1 <= quarters_ahead <= MOST_AT_ONCE:
        raise ValueError(f"Choose a whole number of quarters from 1 to {MOST_AT_ONCE}.")
    row = conn.execute("SELECT test_world FROM world_state").fetchone()
    if row is None:
        raise NotATestWorld("The world has not been created yet.")
    if not ledger._first(row):
        raise NotATestWorld("This is a live world. Nobody can move its calendar.")
    conn.execute("UPDATE world_state SET weeks_ahead = weeks_ahead + %s", (quarters_ahead,))
    return quarters.close_due_quarters(conn, now)


if __name__ == "__main__":
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("Set DATABASE_URL first. See README.md.")
    try:
        count = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    except ValueError:
        raise SystemExit("Say how many quarters, for example:  python -m simulation.fast_forward 4") from None
    with psycopg.connect(url, autocommit=True) as connection:
        try:
            closed = fast_forward(connection, count, datetime.now(UTC))
        except (NotATestWorld, ValueError) as problem:
            raise SystemExit(str(problem)) from None
    if closed:
        print(f"Moved ahead {count} quarter(s). Closed: {', '.join(clock.period_label(p) for p in closed)}.")
    else:
        print(f"Moved ahead {count} quarter(s). No quarter has ended yet.")
