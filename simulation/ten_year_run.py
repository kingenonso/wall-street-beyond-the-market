"""The ten-year run, for testing only.

Run from the project root, with the game's database up but its server stopped:

    docker compose stop server
    docker compose run --rm --no-deps server python -m simulation.ten_year_run
    docker compose start server

The server must be stopped while this runs. The server closes quarters by itself
every thirty seconds, and two closers at once deadlock in the database: this
program holds the world's row through a quarter, while the server's own loop is
in the ledger moving money for the auctions and the computer-run investors. One
closer at a time is the rule, and the server is the one to stop: it finds any
quarter still due the moment it starts again.

It moves a TEST world to forty closed quarters (ten game years), staging the
same shocks Part 4b used:

  * the price of oil up by half for one quarter, in quarter 24;
  * a run on a bank in quarter 17, and another in quarter 29.

Every quarter is closed by the game's own rules, in the game's own order, and
each one ends with the ledger re-added from scratch and every part of the game
checking its own books. If anything is out, the quarter refuses to close and
this program stops with the fault in plain words. So a run that reaches forty
quarters has passed the books check forty times.

It is safe to run again after a stop: it picks up from the last quarter that
closed, and the shocks are tied to quarter numbers, not to how many times the
program has run.

  --quarters N   stop at quarter N instead of 40 (a rehearsal)
  --no-shocks    close the quarters with nothing staged
  --quiet        print only the summary
"""

from __future__ import annotations

import argparse
import os
import time
from datetime import datetime, timezone

import psycopg
from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from simulation import clock, courts, crisis, deposits, fast_forward, ledger

TEN_YEARS = 40

# The shocks, as Part 4b staged them. A quarter is named by its number, counting
# the world's first quarter as 1.
OIL_SHOCK_QUARTER = 24
OIL_SHOCK_BPS = 5000            # the price of oil up by half for that quarter
BANK_SHOCKS = ((17, 35), (29, 30))   # quarter, and the bank's trust out of 100 on its first day


def _one(conn: Connection, query: str, params: tuple = ()):
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(query, params).fetchone()


def _all(conn: Connection, query: str, params: tuple = ()) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(query, params).fetchall()


def last_closed(conn: Connection) -> int:
    row = _one(conn, "SELECT last_closed_period FROM world_state")
    return row["last_closed_period"] if row else 0


def stage_oil_shock(conn: Connection, period: int) -> tuple[int, int] | None:
    """Make the price of oil dearer for one quarter. Returns (before, after) in cents, or None."""
    row = _one(conn, "SELECT oil_cents FROM abroad_results WHERE period = %s", (period,))
    if row is None:
        return None
    before = row["oil_cents"]
    after = int(before * (10000 + OIL_SHOCK_BPS) / 10000)
    # The row is a record, and records are not edited. Inside a test world only, the
    # permanence trigger is stood down for this one change, as the crisis test does.
    with conn.transaction():
        conn.execute("SET LOCAL session_replication_role = replica")
        conn.execute("UPDATE abroad_results SET oil_cents = %s WHERE period = %s", (after, period))
    return before, after


def stage_bank_shock(conn: Connection, period: int, bank: dict, trust: int, now: datetime) -> None:
    """A run on a bank: its savers lose their trust on the quarter's first day."""
    conn.execute(
        "INSERT INTO bank_confidence (company_id, period, day, score, state, parts, withdrawn, at)"
        " VALUES (%s, %s, 0, %s, %s, %s, 0, %s)"
        " ON CONFLICT (company_id, period, day) DO UPDATE SET score = EXCLUDED.score, state = EXCLUDED.state",
        (bank["id"], period, trust, crisis.state_of(trust), Jsonb({"news": trust - 70}), now))


def _shock_banks(conn: Connection) -> list[dict]:
    """The two banks the shocks fall on: the first two by code, so the run repeats exactly."""
    return deposits.banks(conn)[:2]


def run(conn: Connection, target: int = TEN_YEARS, shocks: bool = True, quiet: bool = False) -> dict:
    """Close quarters until `target` have closed. Returns what the run found."""
    started = last_closed(conn)
    if started >= target:
        return {"already": True, "from": started, "to": started, "quarters": [], "problems": []}

    banks = _shock_banks(conn) if shocks else []
    if shocks and len(banks) < 2:
        raise SystemExit("This world has fewer than two banks, so the two bank shocks cannot be staged.")

    timings: list[tuple[int, float]] = []
    staged: list[str] = []
    now = datetime.now(timezone.utc)

    # A world made some weeks ago already has quarters due. They are closed first, with
    # nothing staged, so that from here on each step closes exactly one quarter and the
    # shocks land in the quarter they are meant for.
    world = _one(conn, "SELECT world_start, weeks_ahead, last_closed_period FROM world_state")
    due = clock.periods_completed(now, clock.effective_start(world["world_start"], world["weeks_ahead"]))
    if due > world["last_closed_period"]:
        fast_forward.fast_forward(conn, 1, now)
        started = last_closed(conn)
        if not quiet:
            print(f"  Closed {started - world['last_closed_period']} quarter(s) that were already due.", flush=True)

    for period in range(started + 1, target + 1):
        # The shocks are staged for the quarter that is about to close, before it closes.
        if shocks and period == OIL_SHOCK_QUARTER:
            moved = stage_oil_shock(conn, period)
            if moved:
                staged.append(f"quarter {period}: the price of oil from {moved[0] / 100:.2f} to {moved[1] / 100:.2f} dollars a barrel")
        if shocks:
            for quarter, trust in BANK_SHOCKS:
                if period == quarter:
                    bank = banks[BANK_SHOCKS.index((quarter, trust)) % len(banks)]
                    stage_bank_shock(conn, period, bank, trust, now)
                    staged.append(f"quarter {period}: a run on {bank['name']} (trust {trust} of 100)")

        began = time.monotonic()
        closed = fast_forward.fast_forward(conn, 1, now)
        took = time.monotonic() - began
        if not closed:
            raise SystemExit(f"Quarter {period} did not close. The world's clock is not where this program expects it.")
        timings.append((period, took))
        if not quiet:
            print(f"  quarter {period:>2} closed in {took:6.1f}s", flush=True)

    problems = ledger.audit(conn)
    return {"already": False, "from": started, "to": target, "quarters": timings, "problems": problems, "staged": staged}


def summary(conn: Connection, result: dict) -> None:
    """What the run found, in plain words."""
    print()
    if result.get("already"):
        print(f"The world had already closed {result['to']} quarters. Nothing to do.")
        return
    print(f"Closed quarters {result['from'] + 1} to {result['to']}.")
    for line in result.get("staged", []):
        print(f"  Staged: {line}")
    timings = result["quarters"]
    if timings:
        slowest = max(timings, key=lambda t: t[1])
        total = sum(t for _, t in timings)
        print(f"  Time: {total / 60:.1f} minutes in all; the slowest quarter was {slowest[0]} at {slowest[1] / 60:.1f} minutes.")

    if result["problems"]:
        print()
        print("THE BOOKS DID NOT PASS:")
        for problem in result["problems"]:
            print(f"  - {problem}")
        return
    print("  The books passed: the ledger re-adds to zero, every balance matches its entries, and no account is overdrawn.")

    world = _one(conn, "SELECT last_closed_period FROM world_state")
    economy = _one(conn, "SELECT * FROM economy_results ORDER BY period DESC LIMIT 1")
    abroad = _one(conn, "SELECT * FROM abroad_results ORDER BY period DESC LIMIT 1")
    if economy:
        print(f"  Prices: the price index stands at {economy['price_index_bps'] / 100:.1f} against 100 when the world began.")
    if abroad:
        print(f"  The naira: {abroad['fx'] / 100:.2f} to the dollar; oil at {abroad['oil_cents'] / 100:.2f} dollars a barrel.")
    closed_banks = _all(conn, "SELECT c.name FROM bank_resolutions r JOIN companies c ON c.id = r.company_id")
    crises = _all(conn, "SELECT title, status FROM economic_crises ORDER BY id")
    print(f"  Banks closed in the ten years: {len(closed_banks)}" + (f" ({', '.join(b['name'] for b in closed_banks)})" if closed_banks else ""))
    print(f"  Crises recorded: {len(crises)}" + (f" ({', '.join(c['title'] for c in crises)})" if crises else ""))
    if courts.ready(conn):
        cases = _one(conn, "SELECT count(*) AS n,"
                           " coalesce(sum(disgorgement + damages + fine + costs), 0) AS ordered,"
                           " coalesce(sum(paid), 0) AS paid FROM court_cases")
        bans = _one(conn, "SELECT count(*) AS n FROM court_bans")["n"]
        if cases["n"]:
            print(f"  The court: {cases['n']} case(s) brought, ₦{cases['ordered'] / 100:,.2f} ordered and"
                  f" ₦{cases['paid'] / 100:,.2f} paid; {bans} trading ban(s).")
        else:
            print("  The court: no cases were brought in the ten years.")
    print(f"  The world now stands at quarter {world['last_closed_period']}.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a test world ten game years, with the shocks staged.")
    parser.add_argument("--quarters", type=int, default=TEN_YEARS, help="stop at this quarter (default 40)")
    parser.add_argument("--no-shocks", action="store_true", help="close the quarters with nothing staged")
    parser.add_argument("--quiet", action="store_true", help="print only the summary")
    args = parser.parse_args()
    if not 1 <= args.quarters <= TEN_YEARS:
        raise SystemExit(f"Choose a quarter from 1 to {TEN_YEARS}.")

    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("Set DATABASE_URL first. See README.md.")
    with psycopg.connect(url, autocommit=True) as connection:
        try:
            result = run(connection, args.quarters, shocks=not args.no_shocks, quiet=args.quiet)
        except (fast_forward.NotATestWorld, ledger.LedgerError) as problem:
            raise SystemExit(str(problem)) from None
        summary(connection, result)


if __name__ == "__main__":
    main()
