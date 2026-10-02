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

from simulation import clock, companies, ledger
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
            _close_period(conn, period, world["company_tax_bps"])
            conn.execute("UPDATE world_state SET last_closed_period = %s", (period,))
        closed.append(period)
        log.info("Closed %s", clock.period_label(period))


def _received(conn: Connection, account, period: int) -> int:
    row = conn.execute(
        "SELECT coalesce(sum(e.amount), 0)::bigint FROM ledger_entries e"
        " JOIN ledger_transactions t ON t.id = e.transaction_id"
        " WHERE e.account_id = %s AND e.asset = %s AND t.period = %s AND e.amount > 0",
        (account, NGN, period),
    ).fetchone()
    return ledger._first(row)


def _close_period(conn: Connection, period: int, tax_bps: int) -> None:
    label = clock.period_label(period)
    public = ledger.account_id(conn, ledger.PUBLIC)
    treasury = ledger.account_id(conn, ledger.TREASURY)
    ctx = companies.Context(public=public, treasury=treasury, tax_bps=tax_bps)

    all_companies = companies.load_companies(conn)
    results = [(company, companies.close_company_quarter(conn, company, period, ctx)) for company in all_companies]

    # TEMPORARY STAND-INS (replaced in Stage 3 by a real government budget and real
    # households). Without them, money would pile up in the Treasury and with
    # investors and never return to the customers who buy from the companies.
    ledger.pay_up_to(
        conn, payer=treasury, receiver=public, wanted=_received(conn, treasury, period),
        kind="government_spending", period=period,
        memo=f"Government spends the tax it collected in {label} on salaries and services",
    )
    for code in (ledger.INVESTORS_FOUNDERS, ledger.INVESTORS_INSTITUTIONS, ledger.INVESTORS_PUBLIC):
        investors = ledger.account_id(conn, code)
        ledger.pay_up_to(
            conn, payer=investors, receiver=public, wanted=_received(conn, investors, period),
            kind="investor_spending", period=period,
            memo=f"Investors spend the dividends and interest they received in {label}",
        )

    for company, result in results:
        companies.file_report(conn, company, result)
