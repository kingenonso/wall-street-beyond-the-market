"""Stage 9: every share's risk, from its own price history (public figures anybody could work out).

  volatility   how much the share swings: the spread of its daily moves, scaled to a game year
               (28 trading days), in hundredths of a percent.
  beta         how much it moves with the BSX 50: 1 moves with the market, above 1 more, below 1 less.

Worked out from the last RISK_SESSIONS trading days. A share with too short a history gets the
market's usual figures and is marked as such.
"""

from __future__ import annotations

import math

from psycopg import Connection
from psycopg.rows import dict_row

from simulation import world_data as data

YEAR_SESSIONS = data.GAME_YEAR_REAL_DAYS          # one real day is one trading day; 28 make a game year
LEAST_SESSIONS = 8                                # fewer than this and the figures are not to be trusted
USUAL_DAILY = 0.02                                # a share with no history is taken to swing 2% a day...
USUAL_CORRELATION = 0.3                           # ...and to move a little with every other


def _rows(conn: Connection, sql: str, params=()) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def closes(conn: Connection, sessions: int = data.RISK_SESSIONS) -> dict:
    """Each share's closing prices on its last trading days, oldest first, with the dates: {company: [(date, price)]}."""
    rows = _rows(conn, """
        SELECT DISTINCT ON (company_id, session_date) company_id, session_date, price / split_factor(company_id, id) AS price
        FROM market_trades
        WHERE session_date >= (SELECT min(d) FROM (SELECT DISTINCT session_date AS d FROM market_trades ORDER BY d DESC LIMIT %s) last_days)
        ORDER BY company_id, session_date, id DESC""", (sessions,))
    out: dict = {}
    for r in rows:
        out.setdefault(r["company_id"], []).append((r["session_date"], int(r["price"])))
    return out


def index_closes(conn: Connection, sessions: int = data.RISK_SESSIONS) -> list[tuple]:
    rows = _rows(conn, "SELECT session_date, level FROM index_days ORDER BY session_date DESC LIMIT %s", (sessions,))
    return [(r["session_date"], int(r["level"])) for r in reversed(rows)]


def returns(series: list[tuple]) -> dict:
    """Day-to-day moves (as fractions), keyed by the later day."""
    out = {}
    for (_, before), (day, now) in zip(series, series[1:]):
        if before > 0:
            out[day] = now / before - 1
    return out


def _spread(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    return math.sqrt(sum((v - mean) ** 2 for v in values) / (len(values) - 1))


def share_risk(conn: Connection) -> dict:
    """{company_id: {"volatility_bps", "beta", "sessions", "enough"}} for every listed share (the usual figures
    where its history is too short)."""
    market = returns(index_closes(conn))
    market_values = list(market.values())
    market_var = _spread(market_values) ** 2
    out = {}
    history = closes(conn)
    listed = [r["company_id"] for r in _rows(conn, "SELECT company_id FROM market_instruments")]
    for company in listed:
        moves = returns(history.get(company, []))
        enough = len(moves) >= LEAST_SESSIONS
        daily = _spread(list(moves.values())) if enough else USUAL_DAILY
        beta = 1.0
        common = [d for d in moves if d in market]
        if enough and len(common) >= LEAST_SESSIONS and market_var > 0:
            a = [moves[d] for d in common]
            b = [market[d] for d in common]
            ma, mb = sum(a) / len(a), sum(b) / len(b)
            beta = sum((x - ma) * (y - mb) for x, y in zip(a, b)) / (len(a) - 1) / market_var
        out[company] = {"volatility_bps": round(daily * math.sqrt(YEAR_SESSIONS) * 10_000), "beta": round(beta, 2),
                        "sessions": len(moves), "enough": enough}
    return out
