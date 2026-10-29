"""Test a crisis in a sealed copy of the world, without touching the live one (design document, section 14).

Run from the project root, by an administrator:

    python -m simulation.crisis_test KCB --loss 12 --days 20
    python -m simulation.crisis_test OTB --fear 30

It opens the world inside one database transaction, gives a bank a shock, works through the game days that follow
with the same rules the game uses, prints what happened day by day, and then throws the whole copy away (the
transaction is rolled back). Nothing it does is ever kept: no saver's money moves, no news is printed, no crisis is
recorded in the real world.

  --loss P   the bank discovers losses of P% of its loans (its owners' funds fall by that much)
  --fear N   the bank's trust drops to N of 100 at once (a rumour, a scandal)
  --days D   how many game days to work through (at most 90; 30 if not said)
"""

from __future__ import annotations

import argparse
import os
from datetime import datetime, timezone

import psycopg
from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from simulation import clock, crisis, deposits


class Rollback(Exception):
    """Raised on purpose at the end, so the sealed copy is thrown away."""


def run(conn: Connection, ticker: str, *, loss_pct: float = 0, fear: int | None = None, days: int = 30, now: datetime | None = None) -> dict:
    """The test itself. Returns what happened; leaves nothing behind (the caller rolls back)."""
    now = now or datetime.now(timezone.utc)
    deposits.setup(conn, 0, now)
    b = deposits.bank(conn, ticker)
    if b is None:
        raise SystemExit(f"No bank with the code {ticker}.")
    from simulation import careers
    w = careers.world_now(conn, now)
    period = w["period"]
    last = crisis._last_day(conn)
    start = last[1] + 1 if last[0] == period else 1
    if loss_pct:
        filed = crisis._filed(conn, b["id"])
        cut = int(crisis.loans_of(filed) * loss_pct / 100)
        # Filed accounts are permanent; inside the sealed copy only, the losses are written into them for the test.
        conn.execute("SET LOCAL session_replication_role = replica")
        conn.execute("UPDATE company_results SET total_equity = total_equity - %s, retained_earnings = retained_earnings - %s,"
                     " customer_loans = customer_loans - %s, total_assets = total_assets - %s, loan_losses = loan_losses + %s"
                     " WHERE company_id = %s AND period = %s", (cut, cut, cut, cut, cut, b["id"], filed["period"]))
        conn.execute("SET LOCAL session_replication_role = origin")
    if fear is not None:
        conn.execute("INSERT INTO bank_confidence (company_id, period, day, score, state, parts, withdrawn, at) VALUES (%s, %s, %s, %s, %s, %s, 0, %s)"
                     " ON CONFLICT (company_id, period, day) DO UPDATE SET score = EXCLUDED.score, state = EXCLUDED.state",
                     (b["id"], period, max(start - 1, 0), fear, crisis.state_of(fear), Jsonb({"news": fear - 70}), now))
    through = min(start + days - 1, clock.GAME_DAYS_PER_QUARTER)
    crisis.run_days(conn, period, through, now)
    log = []
    with conn.cursor(row_factory=dict_row) as cur:
        for r in cur.execute("SELECT c.ticker, f.day, f.score, f.state, f.withdrawn FROM bank_confidence f JOIN companies c ON c.id = f.company_id"
                             " WHERE f.period = %s AND f.day >= %s ORDER BY f.day, c.ticker", (period, start)).fetchall():
            log.append(r)
        support = cur.execute("SELECT c.ticker, s.day, s.amount FROM central_bank_support s JOIN companies c ON c.id = s.company_id"
                              " WHERE s.period = %s AND s.day >= %s ORDER BY s.day", (period, start)).fetchall()
        closures = cur.execute("SELECT c.ticker, r.day, r.words FROM bank_resolutions r JOIN companies c ON c.id = r.company_id"
                               " WHERE r.period = %s AND r.day >= %s ORDER BY r.id", (period, start)).fetchall()
        blanket = cur.execute("SELECT from_day, reason FROM blanket_guarantees WHERE from_period = %s AND from_day >= %s", (period, start)).fetchall()
        crises = cur.execute("SELECT title, status, step, steps FROM economic_crises WHERE started_period = %s ORDER BY id", (period,)).fetchall()
    return {"bank": b["name"], "period": period, "from_day": start, "to_day": through, "days": log, "support": support,
            "closures": closures, "blanket": blanket, "crises": crises}


def main() -> None:
    parser = argparse.ArgumentParser(description="Test a crisis in a sealed copy of the world.")
    parser.add_argument("ticker")
    parser.add_argument("--loss", type=float, default=0)
    parser.add_argument("--fear", type=int, default=None)
    parser.add_argument("--days", type=int, default=30)
    args = parser.parse_args()
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("Set DATABASE_URL first. See README.md.")
    with psycopg.connect(url) as conn:
        found = None
        try:
            with conn.transaction():
                found = run(conn, args.ticker.upper(), loss_pct=args.loss, fear=args.fear, days=max(1, min(args.days, 90)))
                raise Rollback()
        except Rollback:
            pass
    print(f"Crisis test on {found['bank']}: days {found['from_day']} to {found['to_day']} of {clock.period_label(found['period'])}.")
    by_day: dict = {}
    for r in found["days"]:
        by_day.setdefault(r["day"], []).append(f"{r['ticker']} {r['score']:>3} {r['state']:<7}")
    for day, rows in by_day.items():
        print(f"day {day:>2}: " + " | ".join(rows))
    for s in found["support"]:
        print(f"  Central Bank lent {s['ticker']} {crisis.money(s['amount'])} on day {s['day']}")
    for b in found["blanket"]:
        print(f"  The Government guaranteed every saving on day {b['from_day']}: {b['reason']}")
    for c in found["closures"]:
        print(f"  Day {c['day']}: {c['words']}")
    for c in found["crises"]:
        print(f"  {c['title']}: {c['status']}, step {c['step']} ({crisis.STEPS[c['step']]})")
    print("Nothing was kept: the copy was thrown away.")


if __name__ == "__main__":
    main()
