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

from simulation import (
    abroad,
    banking,
    bonds,
    careers,
    clock,
    companies,
    consumers,
    conveyancing,
    corporate,
    crashfund,
    derivatives,
    development,
    economy,
    empires,
    events,
    exchange,
    grants,
    instruments,
    investors,
    ledger,
    lending,
    macro,
    marketview,
    moneywatch,
    news,
    objectives,
    private,
    propfunds,
    ranks,
    stochastic,
    swaps,
    valuation,
)
from simulation import property as property_market
from simulation.money import BPS, apply_bps

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
            from simulation import firm_deals
            problems = (ledger.audit(conn) + exchange.check_books(conn) + corporate.check_books(conn) + firm_deals.check_books(conn)
                        + lending.check_books(conn) + derivatives.check_books(conn)
                        + crashfund.check_books(conn) + instruments.check_books(conn)
                        + conveyancing.check_books(conn) + development.check_books(conn) + propfunds.check_books(conn)
                        + _crisis().check_books(conn) + _funds().check_books(conn)
                        + _etfs().check_books(conn) + _fx().check_books(conn) + _world().check_books(conn))
            if problems:
                raise ledger.LedgerError("The ledger failed its end-of-quarter check: " + " ".join(problems))
            conn.execute("UPDATE world_state SET last_closed_period = %s", (period,))
            # With every company's accounts filed and the new interest rate set, the professional
            # work that was waiting for them is judged, and the payers pay.
            objectives.at_close(conn, period, now)
            ranks.at_close(conn, period, now)
            # Empires pay their staff, their books are audited, and their staff do their work.
            empires.after_close(conn, period, now)
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

    # First, settle what was announced when the quarter before closed: votes are counted,
    # shares are split, new shares are issued, bonds are swapped for shares and takeover
    # offers succeed or fail. The computer-run investors take their orders off the exchange
    # first, so that nobody can trade against prices set before all this was known.
    bonds.setup(conn, period - 1)
    investors.withdraw_all(conn, now)
    corporate.settle(conn, period, now)
    happening = events.load(conn, period)
    moods, severe = events.location_moods(happening)
    lending_factor = moneywatch.lending_factor_bps(conn, period)

    # The crises stage: the quarter's last game days are worked through (trust, runs, the Central Bank) before anybody closes.
    from simulation import crisis
    crisis.before_close(conn, period, now)
    banking.reprice_loans(conn, period, policy_rate)
    # Private companies: their owners' dials, their managers, assets, routes and staff shape their quarter.
    private.before_close(conn, all_companies, period, before["wage_index_bps"])
    lasting_pull = economy.set_market_pulls(conn, world, all_companies, period, fortune_seed, happening)
    # Rent on buildings owned outside the property companies is part of what the city's spending goes to (Stage 8).
    property_market.add_rent_to_market(conn, world, fortune_seed)
    sector_weights, sector_fortune = economy.household_sector_weights(world, period, fortune_seed, before)

    signals = economy.household_signals(conn, world, period, before, severe)
    # The 1,000 consumer groups each react to the news in their own way; added up, they are their location.
    groups = consumers.load(conn)
    if abroad.state(conn, period - 1) is None:
        raise economy.WorldTooOld("This world was created before the rest of the world existed. Start a new world to run this version.")
    responses = consumers.respond(groups, signals)
    world.mindset_mix = consumers.mindset_mix(groups)
    borrowed, debt_service = banking.household_credit(
        conn, world, period, policy_rate, {loc: r["borrow_bps"] for loc, r in responses.items()}, lending_factor,
    )
    plans = consumers.budgets(conn, groups, world, period, borrowed=borrowed, debt_service=debt_service, moods=moods,
                              seed=fortune_seed, base_weights=sector_weights)
    spent = economy.households_spend(conn, world, period, sector_weights, fortune_seed, responses, moods, borrowed, debt_service,
                                     plans=plans)
    # Companies buy their supplies, part of them abroad at this quarter's exchange rate; then the rest
    # of the world buys what the country sells abroad (the economy upgrade).
    imported = economy.companies_buy_inputs(conn, world, all_companies, period, fortune_seed, before,
                                            import_factor_bps=abroad.import_factor_bps(conn, period, before["price_index_bps"]))
    trade = abroad.buy_exports(conn, world, period)
    private.pay_spending(conn, world, all_companies, period)
    damages, claims_paid = economy.pay_claims(conn, world, all_companies, period, happening, spent)

    ratings = {
        r["company_id"]: r["credit_rating"]
        for r in _dicts(conn, "SELECT DISTINCT ON (company_id) company_id, credit_rating FROM company_reports"
                              " ORDER BY company_id, period DESC, version DESC")
    }
    lenders = {}
    for bank in banking.banks(conn, period):
        lenders[bank["account_id"]] = {**bank, "room": apply_bps(banking.lending_room(bank), crisis.lending_bps(conn, bank["id"])),
                                       "rating": ratings.get(bank["id"])}
    ctx = companies.Context(
        world=world, tax_bps=tax_bps, fortune_seed=fortune_seed,
        lasting_pull=lasting_pull, sector_fortune=sector_fortune,
        policy_rate_bps=policy_rate, wage_index_bps=before["wage_index_bps"], lending_factor_bps=lending_factor,
        damages=damages, ratings=ratings, banks=lenders,
        integration=corporate.integration_effects(conn, period, fortune_seed, ratings),
    )
    # Part 4a: companies' dollar debts are revalued at the official rate before they close their books.
    from simulation import fx
    fx.before_companies(conn, period, now)
    results = [(company, companies.close_company_quarter(conn, company, period, ctx)) for company in all_companies]

    # TEMPORARY STAND-IN (until the exchange is an institution with owners of its own):
    # the Broad Street Exchange hands the fees it earned this quarter to the Government.
    earned = ledger.balance(conn, ledger.account_id(conn, exchange.FEES))
    if earned > 0:
        ledger.transfer(conn, payer=ledger.account_id(conn, exchange.FEES), receiver=world.treasury, amount=earned,
                        kind="exchange_surplus", memo=f"Broad Street Exchange: fees earned, {clock.period_label(period)}",
                        period=period)
    # The Government pays what it owes on its bonds, borrows a little more than it repays,
    # and spends what it collected plus what it borrowed, less what its borrowing cost.
    debt_cost, repaid = bonds.government_service(conn, world.treasury, period, policy_rate, before["price_index_bps"])
    collected = ledger.received_in_period(conn, world.treasury, period, kinds=economy.GOVERNMENT_INCOME)
    borrowed = bonds.government_borrows(conn, world.treasury, period, collected, repaid)
    economy.government_spends(conn, world, period, borrowed=borrowed, debt_cost=debt_cost)
    economy.pensions_paid(conn, world, period)
    economy.record_households(conn, world, period, spent, results)
    # Each group's quarter is settled against the ledger; a few groups move house.
    consumers.quarter(conn, world, period, fortune_seed, plans, spent, groups)

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
    commodity_events = events.commodity_moves(happening)
    # Part 4b: the economies abroad, their central banks' rates and the companies listed abroad close their quarter first
    # (growth abroad moves the oil price; America's rate is what lending abroad pays).
    from simulation import world as world_markets
    world_markets.at_close(conn, period, now)
    # Next quarter's oil price; energy at home is the oil price in naira.
    oil_next = abroad.next_oil(conn, period, fortune_seed, commodity_events.get("energy", 0))
    measured = macro.close_quarter(
        conn, period, fortune_seed, company_sales=company_sales, household_spending=household_spending,
        money=money, commodity_events=commodity_events,
        premium_index_bps=economy.premium_index_bps(conn, period, claims_paid),
        confidence_bps=confidence, rate_extra_bps=watch["rate_extra_bps"] + crisis.rate_relief_bps(conn),
        energy_bps=abroad.energy_index_bps(oil_next, abroad.state(conn, period - 1)["fx"]),
        import_push_bps=abroad.import_push_bps(conn, period),
    )
    # Land and property: rent shared out, tax, upkeep, mortgages, the headquarters and the Auction House (Stage 8).
    property_market.close(conn, world, period, now, fortune_seed, measured)
    # Loans to players and empires, and short sales: interest, repayments, the lending fee, recalls (Stage 9).
    lending.close(conn, period, now, measured["next_policy_rate_bps"])
    # The quarter's common forces go on the record (never sent to players).
    stochastic.record(conn, period, fortune_seed)
    # The naira's exchange rate for next quarter, and what foreign investors do.
    abroad_now = abroad.close(conn, period, fortune_seed, oil_next=oil_next, inflation_bps=measured["inflation_bps"],
                              next_rate_bps=measured["next_policy_rate_bps"], trade=trade, imports=imported)
    # Options and futures that run to this close are settled in cash, and the next ones listed; the crash fund (Stage 9).
    # (After the oil price and the naira are set for the quarter, so a future settles at the new level, not one known all quarter.)
    # Part 4a: Eurobonds paid, the Central Bank's reserves and its next move (before currency forwards settle).
    fx.after_abroad(conn, period, now, abroad_now, imported)
    # Part 4b: parents abroad send their Nigerian arms' dividends home if there are dollars; some decide to leave.
    world_markets.after_fx(conn, period, now)
    derivatives.close(conn, period, now)
    swaps.close(conn, period, now)
    instruments.issue_preferred(conn, period, now)
    crashfund.close(conn, period, now, derivatives.index_now(conn, now))

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
        results=results, damages=damages, claims_paid=claims_paid, policy_rate_bps=policy_rate, abroad_now=abroad_now,
    )
    # Stage 10: the Ripple links what caused what this quarter, and the Chronicle writes the quarter's record.
    from simulation import chronicle, ripple
    ripple.at_close(conn, period, results, happening, measured, watch, now)
    chronicle.at_close(conn, period, now)
    from simulation import newsroom
    newsroom.at_close(conn, period)
    # Stage 10, Part 2: what was said this quarter is settled against what happened; sources built for two quarters are ready.
    from simulation import intel
    intel.at_close(conn, period, now)
    from simulation import press
    press.at_close(conn, period, now)
    # Charities' giving and the Money Watch's look at them; the media titles' quarter, and the Government's next one for sale.
    from simulation import charity, media
    charity.at_close(conn, period, now)
    media.close(conn, period, now)
    # The crises stage: a bank whose losses ate its owners' funds is closed; the Government's promise is lifted once trust
    # is back; a bank a year in public hands goes on sale again; the Crisis Watch takes its reading.
    crisis.at_close(conn, period, now)
    news.for_events(conn, events.generate(conn, period + 1, fortune_seed))
    # Private companies after the close: wear, morale, secrets, rivals' prices, failures, sales and start-ups.
    private.after_close(conn, period, results, measured["wage_index_bps"], fortune_seed, now)

    # With the results in, companies announce what they will ask of the market next quarter,
    # and players who held through the close earn the parts of their starting grant that depend on it.
    corporate.propose(conn, period, fortune_seed, now, results, lenders, measured["next_policy_rate_bps"])
    if period % clock.QUARTERS_PER_YEAR == 1:
        owed = bonds.government_debt(conn)
        if owed:
            news.publish(conn, period=period + 1, day=6, kind="government_bonds", story=f"government_bonds:{period}",
                         facts={"amount": news.money_words(borrowed), "rate": bonds._percent(bonds.government_yield_bps(measured["next_policy_rate_bps"], 20)),
                                "total": news.money_words(owed)})
    grants.mark_holders(conn, now)
    # Players' retirement savings grow by what their fund earned, and this quarter's saving is added.
    day, _ = exchange.session_of(now)
    careers.close_retirement(conn, period, marketview.index_level(marketview._shares(conn, day), marketview.index_base(conn)),
                             measured["next_policy_rate_bps"])


def _fx():
    from simulation import fx
    return fx


def _world():
    from simulation import world
    return world


def _etfs():
    from simulation import etfs
    return etfs


def _funds():
    from simulation import funds
    return funds


def _crisis():
    from simulation import crisis
    return crisis


def _dicts(conn: Connection, sql: str, params=()) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()
