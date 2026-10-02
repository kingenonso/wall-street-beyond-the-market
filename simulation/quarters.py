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

from simulation import (banking, clock, companies, economy, events, exchange, investors, ledger, macro, mindsets,
                        moneywatch, news, valuation)
from simulation.money import BPS
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
            due = clock.periods_completed(now, clock.effective_start(world["world_start"], world["weeks_ahead"]))
            period = world["last_closed_period"] + 1
            if period > due:
                return closed
            _close_period(conn, period, world["company_tax_bps"], world["fortune_seed"], now)
            # Re-add the whole ledger before the quarter is allowed to close. If anything
            # is out, the quarter is not closed and the fault is reported loudly.
            problems = ledger.audit(conn) + exchange.check_books(conn)
            if problems:
                raise ledger.LedgerError("The ledger failed its end-of-quarter check: " + " ".join(problems))
            conn.execute("UPDATE world_state SET last_closed_period = %s", (period,))
        closed.append(period)
        log.info("Closed %s", clock.period_label(period))


def _close_period(conn: Connection, period: int, tax_bps: int, fortune_seed: str, now: datetime) -> None:
    """One quarter of the whole economy, in order.

      1. Loans are brought to this quarter's interest rate.
      2. Households pay interest, repay and borrow; then they spend at the companies.
      3. Companies buy what they need from each other.
      4. Insurers pay for what this quarter's events destroyed.
      5. Each company closes its quarter: counts its sales, pays its people, its
         interest, its tax and its owners.
      6. The Government spends what it collected. Pension funds pay pensions.
      7. The economy is measured: prices, wages, commodities. The Money Watch takes
         its reading, and the Central Bank sets the next interest rate.
      8. Every company files its report, the news of the quarter is written, and next
         quarter's events are decided.

    What households earn in one quarter, they spend in the next.
    """
    if len(fortune_seed) < 32:
        raise ledger.LedgerError("The world has no secret. Quarters cannot be closed without one.")
    world = economy.load_world(conn)
    all_companies = companies.load_companies(conn)
    before = macro.state(conn, period - 1)
    if before is None:
        raise economy.WorldTooOld("This world was created before prices and lending existed. Start a new world.")
    policy_rate = before["next_policy_rate_bps"]            # the rate the Central Bank set for this quarter
    happening = events.load(conn, period)
    moods, severe = events.location_moods(happening)
    lending_factor = moneywatch.lending_factor_bps(conn, period)

    banking.reprice_loans(conn, period, policy_rate)
    lasting_pull = economy.set_market_pulls(conn, world, all_companies, period, fortune_seed, happening)
    sector_weights, sector_fortune = economy.household_sector_weights(world, period, fortune_seed, before)

    signals = economy.household_signals(conn, world, period, before, severe)
    responses = {
        location: mindsets.location_response(world.mindset_mix.get(location, {}), signals[location])
        for location in world.households
    }
    borrowed, debt_service = banking.household_credit(
        conn, world, period, policy_rate, {loc: r["borrow_bps"] for loc, r in responses.items()}, lending_factor,
    )
    spent = economy.households_spend(conn, world, period, sector_weights, fortune_seed, responses, moods, borrowed, debt_service)
    economy.companies_buy_inputs(conn, world, all_companies, period, fortune_seed, before)
    damages, claims_paid = economy.pay_claims(conn, world, all_companies, period, happening, spent)

    ratings = {
        r["company_id"]: r["credit_rating"]
        for r in _dicts(conn, "SELECT DISTINCT ON (company_id) company_id, credit_rating FROM company_reports"
                              " ORDER BY company_id, period DESC, version DESC")
    }
    lenders = {}
    for bank in banking.banks(conn, period):
        lenders[bank["account_id"]] = {**bank, "room": banking.lending_room(bank), "rating": ratings.get(bank["id"])}
    ctx = companies.Context(
        world=world, tax_bps=tax_bps, fortune_seed=fortune_seed,
        lasting_pull=lasting_pull, sector_fortune=sector_fortune,
        policy_rate_bps=policy_rate, wage_index_bps=before["wage_index_bps"], lending_factor_bps=lending_factor,
        damages=damages, ratings=ratings, banks=lenders,
    )
    results = [(company, companies.close_company_quarter(conn, company, period, ctx)) for company in all_companies]

    # TEMPORARY STAND-IN (until the exchange is an institution with owners of its own):
    # the Broad Street Exchange hands the fees it earned this quarter to the Government.
    earned = ledger.balance(conn, ledger.account_id(conn, exchange.FEES))
    if earned > 0:
        ledger.transfer(conn, payer=ledger.account_id(conn, exchange.FEES), receiver=world.treasury, amount=earned,
                        kind="exchange_surplus", memo=f"Broad Street Exchange: fees earned, {clock.period_label(period)}",
                        period=period)
    economy.government_spends(conn, world, period)
    economy.pensions_paid(conn, world, period)
    economy.record_households(conn, world, period, spent, results)

    # Measure the economy, take the Money Watch's reading, and let the Central Bank decide.
    company_sales = sum(result["revenue"] for _, result in results)
    household_spending = sum(spent.values())
    money = ledger.amount_in_existence(conn)
    watch = moneywatch.measure(
        conn, period, money=money,
        money_growth_bps=macro.yearly_change_bps(conn, "money", period, money, scale_up=False),
        output_growth_bps=macro.yearly_change_bps(conn, "company_sales", period, company_sales, scale_up=False),
        inflation_bps=before["inflation_bps"],
    )
    population = {loc["name"]: loc["population_bps"] for loc in world.locations}
    confidence = sum(
        population[location] * (response["spend_bps"] + moods.get(location, 0)) for location, response in responses.items()
    ) // BPS
    measured = macro.close_quarter(
        conn, period, fortune_seed, company_sales=company_sales, household_spending=household_spending,
        money=money, commodity_events=events.commodity_moves(happening),
        premium_index_bps=economy.premium_index_bps(conn, period, claims_paid),
        confidence_bps=confidence, rate_extra_bps=watch["rate_extra_bps"],
    )

    for company, result in results:
        companies.file_report(conn, company, result)

    # What each company is now worth, from what it has just filed. The computer-run investors
    # take their orders off the exchange at the same instant the reports appear, so nobody can
    # trade against prices set before the investors had read them. They return with new prices.
    valuation.value_all(conn, period)
    investors.withdraw_all(conn, now)

    # The news of the quarter just closed, then next quarter's events and the news of them
    # (each dated the day it happens, and out of sight until then).
    news.for_results(
        conn, period, before=before, now=measured, watch=watch, happening=happening, companies=all_companies,
        results=results, damages=damages, claims_paid=claims_paid, policy_rate_bps=policy_rate,
    )
    news.for_events(conn, events.generate(conn, period + 1, fortune_seed))


def _dicts(conn: Connection, sql: str, params=()) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()
