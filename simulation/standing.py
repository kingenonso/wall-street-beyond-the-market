"""Stage 10: an empire's public reputation (A10).

Every empire has a public reputation from 0 to 100, starting at 50, shown on its page and in the league. What moves
it is public: what the press writes about it, its audits, a fine, an undeclared interest that is exposed, how it
handles a crisis and its charity (Part 2). Every change is kept with its reason.
"""

from __future__ import annotations

from datetime import datetime

from psycopg import Connection
from psycopg.rows import dict_row

MOST_A_DAY = 6                        # press can move an empire at most this far in one game day, either way


def _rows(conn: Connection, sql: str, params=()) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def change(conn: Connection, empire_id, by: int, why: str, period: int, now: datetime) -> int:
    """Move an empire's reputation, within 0 to 100. Returns the new figure."""
    row = _rows(conn, "SELECT reputation FROM empires WHERE id = %s FOR UPDATE", (empire_id,))
    if not row or by == 0:
        return row[0]["reputation"] if row else 0
    after = min(max(row[0]["reputation"] + by, 0), 100)
    if after == row[0]["reputation"]:
        return after
    conn.execute("UPDATE empires SET reputation = %s WHERE id = %s", (after, empire_id))
    conn.execute("INSERT INTO empire_reputation (empire_id, change, after, why, period, at) VALUES (%s, %s, %s, %s, %s, %s)",
                 (empire_id, after - row[0]["reputation"], after, why[:200], period, now))
    return after


def history(conn: Connection, empire_id, limit: int = 20) -> list[dict]:
    return _rows(conn, "SELECT change, after, why, period, at FROM empire_reputation WHERE empire_id = %s ORDER BY id DESC LIMIT %s",
                 (empire_id, limit))
