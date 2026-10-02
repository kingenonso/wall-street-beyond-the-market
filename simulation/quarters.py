"""Closing game quarters.

One real week is one game quarter (design document, section 5). When a quarter
ends, every company's accounts are brought up to date and its report is filed.

`close_due_quarters` is safe to call at any time and from several servers at
once: a quarter is closed exactly once, in order, and never before the clock
says it has ended. If the server was switched off for a while, the missed
quarters are closed one after another when it comes back.
"""

from __future__ import annotations

import logging
from datetime import datetime

from psycopg import Connection
from psycopg.rows import dict_row

from simulation import clock, companies, economy, ledger
from simulation.ledger import NGN

log = logging.getLogger("wsbm.quarters")


def close_due_quarters(conn: Connection, now: datetime) -> list[int]:
    """Close every quarter that has ended and is not yet closed. Returns the quarters closed."""
    closed: list[int] = []
    while True:
        # Each quarter is one all-or-nothing piece of work.
        with conn.transaction():
            with conn.cursor(row_factory=dict_row) as cur:
                # Locking the world's row makes every other server wait its turn here.
                world = cur.execute("SELECT * FROM world_state FOR UPDATE").fetchone()
            if world is None:
                return closed                  # the world has not been created yet
            due = clock.periods_completed(now, world["world_start"])
            period = world["last_closed_period"] + 1
            if period > due:
                return closed
            _close_period(conn, period, world["company_tax_bps"], world["fortune_seed"])
            # Re-add the whole ledger before the quarter is allowed to close. If anything
            # is out, the quarter is not closed and the fault is reported loudly.
            problems = ledger.audit(conn)
            if problems:
                raise ledger.LedgerError("The ledger failed its end-of-quarter check: " + " ".join(problems))
            conn.execute("UPDATE world_state SET last_closed_period = %s", (period,))
        closed.append(period)
        log.info("Closed %s", clock.period_label(period))


def _close_period(conn: Connection, period: int, tax_bps: int, fortune_seed: str) -> None:
    """One quarter of the whole economy, in order.

      1. Households and investors spend at the companies.
      2. Companies buy what they need from each other.
      3. Each company closes its quarter: counts its sales, pays its people, its
         interest, its tax and its owners.
      4. The Government spends the tax it collected.
      5. Pension funds pay pensions.
      6. Each location's households are written up, and every company files its report.

    What households earn in one quarter, they spend in the next.
    """
    if len(fortune_seed) < 32:
        raise ledger.LedgerError("The world has no secret. Quarters cannot be closed without one.")
    world = economy.load_world(conn)
    all_companies = companies.load_companies(conn)

    lasting_pull = economy.set_market_pulls(conn, world, all_companies, period, fortune_seed)
    sector_weights, sector_fortune = economy.household_sector_weights(world, period, fortune_seed)
    spent = economy.households_spend(conn, world, period, sector_weights)
    economy.companies_buy_inputs(conn, world, all_companies, period)

    ctx = companies.Context(
        world=world, tax_bps=tax_bps, fortune_seed=fortune_seed,
        lasting_pull=lasting_pull, sector_fortune=sector_fortune,
    )
    results = [(company, companies.close_company_quarter(conn, company, period, ctx)) for company in all_companies]

    economy.government_spends(conn, world, period)
    economy.pensions_paid(conn, world, period)
    economy.record_households(conn, world, period, spent, results)

    for company, result in results:
        companies.file_report(conn, company, result)
