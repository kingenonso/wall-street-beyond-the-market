"""The economy around the companies (Stage 3, Part A).

Who earns, who spends, and where the spending goes:

  * Households in each of the five locations earn wages, public-sector pay and
    pensions, and spend most of it at the companies.
  * Companies buy what they need from other companies.
  * The Government spends the tax it collects on pay and on purchases.
  * Pension funds collect contributions from every wage and pay pensions.

Every naira here moves through the ledger. Nothing is created: one party's
spending is another's income, so money goes round and round.

Stand-ins still in place are marked TEMPORARY STAND-IN with the stage that
replaces them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from psycopg import Connection
from psycopg.rows import dict_row

from simulation import clock, events, ledger, mindsets
from simulation import world_data as data
from simulation.fortune import fortune_bps
from simulation.money import BPS, apply_bps

# Reasons money reaches households, for their income record.
_WAGE_KINDS = ("wages", "cost_of_sales", "salary")      # "salary": what players' living costs pay to local households
_GOVERNMENT_KINDS = ("government_wages",)
_PENSION_KINDS = ("pension_payment",)


class WorldTooOld(ledger.LedgerError):
    """The world was created before households existed and cannot be run by this version."""


@dataclass
class World:
    """The parts of the economy every step needs, read once per quarter."""
    treasury: UUID
    central_bank: UUID
    founders: UUID
    institutions: UUID          # the pension funds
    small_investors: UUID
    locations: list[dict]                      # name, population_bps, running_cost_bps, quarterly_wage
    households: dict[str, dict]                # location -> account_id and spending habits
    demand: dict[str, dict]                    # sector -> household_bps, government_bps, investment_bps
    inputs: dict[str, dict[str, int]]          # buyer sector -> supplier sector -> share of sales
    seasons: dict[str, list[int]]              # sector -> the four seasons
    members: dict[str, list[dict]] = field(default_factory=dict)   # sector -> companies with this quarter's pull
    mindset_mix: dict[str, dict[str, int]] = field(default_factory=dict)   # location -> mindset -> share

    @property
    def population(self) -> dict[UUID, int]:
        """Each household account's share of the people."""
        return {self.households[loc["name"]]["account_id"]: loc["population_bps"] for loc in self.locations}

    def staff_spread(self, headquarters: str) -> dict[UUID, int]:
        """Where a company's pay goes: half to its head-office location, the rest by population."""
        spread = {
            account: share * (BPS - data.HOME_STAFF_BPS) // BPS for account, share in self.population.items()
        }
        home = self.households[headquarters]["account_id"]
        spread[home] += data.HOME_STAFF_BPS
        return spread


def _rows(conn: Connection, sql: str, params=()) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def load_world(conn: Connection) -> World:
    households = {r["location"]: r for r in _rows(conn, "SELECT * FROM households")}
    if not households:
        raise WorldTooOld(
            "This world was created before households existed. Start a new world to run this version."
        )
    inputs: dict[str, dict[str, int]] = {}
    for r in _rows(conn, "SELECT * FROM sector_inputs"):
        inputs.setdefault(r["buyer"], {})[r["supplier"]] = r["bps"]
    seasons = {
        r["sector"]: r["season_bps"]
        for r in _rows(conn, "SELECT DISTINCT ON (sector) sector, season_bps FROM companies ORDER BY sector")
    }
    mix: dict[str, dict[str, int]] = {}
    for r in _rows(conn, "SELECT * FROM household_mindsets"):
        mix.setdefault(r["location"], {})[r["mindset"]] = r["share_bps"]
    return World(
        mindset_mix=mix,
        central_bank=ledger.account_id(conn, ledger.CENTRAL_BANK),
        treasury=ledger.account_id(conn, ledger.TREASURY),
        founders=ledger.account_id(conn, ledger.INVESTORS_FOUNDERS),
        institutions=ledger.account_id(conn, ledger.INVESTORS_INSTITUTIONS),
        small_investors=ledger.account_id(conn, ledger.INVESTORS_PUBLIC),
        locations=_rows(conn, "SELECT * FROM locations ORDER BY sort_order"),
        households=households,
        demand={r["sector"]: r for r in _rows(conn, "SELECT * FROM sector_demand")},
        inputs=inputs,
        seasons=seasons,
    )


def split(amount: int, weights: dict) -> dict:
    """Share an amount out in proportion to weights, in whole kobo.

    Each share is rounded down, so the shares never add up to more than the amount.
    """
    total = sum(weights.values())
    if amount <= 0 or total <= 0:
        return {}
    return {key: amount * weight // total for key, weight in weights.items() if weight > 0}


def allocate(world: World, amount: int, sector_weights: dict[str, int], *,
             location: str | None = None, exclude: UUID | None = None,
             local_preference_bps: int = data.LOCAL_PREFERENCE_BPS) -> dict[UUID, int]:
    """Decide which companies an amount of spending goes to.

    First by sector, in proportion to `sector_weights`. Then, inside each sector,
    companies compete: each gets a share in proportion to its pull on customers,
    and a buyer favours companies based in its own location.
    """
    shares: dict[UUID, int] = {}
    for sector, sector_amount in split(amount, sector_weights).items():
        pulls = {}
        for company in world.members.get(sector, []):
            if company["account_id"] == exclude:
                continue
            local = local_preference_bps if company["headquarters"] == location else BPS
            pulls[company["account_id"]] = company["pull"] * local
        for account, part in split(sector_amount, pulls).items():
            shares[account] = shares.get(account, 0) + part
    return shares


def set_market_pulls(conn: Connection, world: World, companies: list[dict], period: int, seed: str,
                     happening: list[dict] | None = None) -> dict[UUID, int]:
    """Work out each company's pull on customers this quarter.

    A company's pull carries over from quarter to quarter, drifts with its own
    trend, and grows when it expands. On top of that, each quarter brings the
    company a little good or bad fortune of its own. Because customers' spending
    is shared out by pull, one company's gain is its rivals' loss.

    Returns each company's lasting pull, to be carried into the next quarter.
    """
    previous = {
        r["company_id"]: r["base_revenue"]
        for r in _rows(conn, "SELECT company_id, base_revenue FROM company_results WHERE period = %s", (period - 1,))
    }
    opening = {
        r["company_id"]: r["base_revenue"]
        for r in _rows(conn, "SELECT company_id, base_revenue FROM company_results WHERE period = 0")
    }
    carried: dict[UUID, int] = {}
    world.members = {}
    for company in companies:
        drifted = apply_bps(previous[company["id"]], BPS + company["revenue_growth_bps"])
        # Part of the way back towards where it began. A company can pull well ahead
        # of its rivals or fall well behind, but none can swallow the whole market
        # simply by trending for long enough.
        lasting = max(drifted + apply_bps(opening[company["id"]] - drifted, data.PULL_RETURN_BPS), 1)
        # Most of a quarter's ups and downs now have a real cause: this quarter's
        # events. A smaller part is still the ordinary run of business.
        own = fortune_bps(seed, company["ticker"], period, "sales", company["volatility_bps"] // 2)
        effects = events.company_effects(happening or [], company)
        carried[company["id"]] = lasting
        company["own_fortune_bps"] = own
        company["event_effects"] = effects
        world.members.setdefault(company["sector"], []).append({
            "account_id": company["account_id"], "headquarters": company["headquarters"],
            "pull": max(apply_bps(apply_bps(lasting, BPS + own), effects["sales_bps"]), 1),
        })
    return carried


def relative_prices(state: dict) -> dict[str, int]:
    """How dear each kind of company's goods are against prices in general (10000 = in line).

    A commodity that has become expensive makes the companies that sell it dearer
    to buy from, and their customers pay more for the same goods. Insurance gets
    dearer after disasters.
    """
    prices = {}
    for name, (sector, _) in data.COMMODITIES.items():
        prices[sector] = state[f"{name}_bps"] * BPS // state["price_index_bps"]
    prices["insurance"] = state["premium_index_bps"]
    return prices


def household_sector_weights(world: World, period: int, seed: str, state: dict) -> tuple[dict[str, int], dict[str, int]]:
    """How households divide their spending between sectors this quarter.

    The usual shares, moved by the season, by each sector's good or bad quarter,
    and by what has become dearer or cheaper. Returns the weights, and each
    sector's fortune for the record.
    """
    weights, fortunes = {}, {}
    dear = relative_prices(state)
    for sector, row in world.demand.items():
        season = world.seasons[sector][(period - 1) % 4]
        fortunes[sector] = fortune_bps(seed, sector, period, "demand", data.SECTOR_VOLATILITY_BPS)
        weight = row["household_bps"] * season // BPS * (BPS + fortunes[sector]) // BPS
        # Households cut back only a little when something they need gets dearer, so
        # they end up spending more on it: half the price change shows in their spending.
        weights[sector] = weight * (BPS + (dear.get(sector, BPS) - BPS) // 2) // BPS
    return weights, fortunes


def household_signals(conn: Connection, world: World, period: int, state: dict, severe: set[str]) -> dict[str, mindsets.Signals]:
    """What each location's households can see when they decide how much to spend and borrow."""
    rows = _rows(conn, "SELECT location, period, income, spending, jobs FROM household_results WHERE period >= %s",
                 (period - 3,))
    by = {(r["location"], r["period"]): r for r in rows}

    def change(location: str, column: str, quarter: int) -> int:
        now, before = by.get((location, quarter)), by.get((location, quarter - 1))
        if not now or not before or not before[column] or quarter - 1 < 1:
            return 0                            # the opening record is an assumption, not a real quarter
        return (now[column] - before[column]) * BPS // before[column]

    def national(quarter: int) -> int:
        return sum(r["spending"] for r in rows if r["period"] == quarter)

    crowd = 0
    if period - 2 >= 1 and national(period - 2):
        crowd = (national(period - 1) - national(period - 2)) * BPS // national(period - 2)
    return {
        location: mindsets.Signals(
            income_change_bps=change(location, "income", period - 1),
            earlier_income_change_bps=change(location, "income", period - 2),
            national_spending_change_bps=crowd,
            rate_above_neutral_bps=state["next_policy_rate_bps"] - data.NEUTRAL_RATE_BPS,
            inflation_bps=state["inflation_bps"],
            jobs_change_bps=change(location, "jobs", period - 1),
            severe_local_event=location in severe,
        )
        for location in world.households
    }


def households_spend(conn: Connection, world: World, period: int, sector_weights: dict[str, int],
                     seed: str, responses: dict[str, dict] | None = None, moods: dict[str, int] | None = None,
                     borrowed: dict[str, int] | None = None, debt_service: dict[str, int] | None = None) -> dict[str, int]:
    """Households and private investors spend at the companies. Returns spending by location.

    Households follow a habit (most of what they earned, a little of what they
    have saved). On top of that: how their mix of mindsets reacts to the news,
    what this quarter's events did to their mood, a little that cannot be
    explained, and whatever they have just borrowed, which they borrowed to spend.
    """
    label = clock.period_label(period)
    spent: dict[str, int] = {}
    last = {r["location"]: r for r in _rows(conn, "SELECT * FROM household_results WHERE period = %s", (period - 1,))}
    for location, household in world.households.items():
        cash = ledger.balance(conn, household["account_id"])
        new_loans = (borrowed or {}).get(location, 0)
        # What they have to live on: last quarter's income, less what the banks have
        # just taken in interest and repayments.
        disposable = max(last[location]["income"] - (debt_service or {}).get(location, 0), 0)
        habit = (
            apply_bps(disposable, household["spend_from_income_bps"])
            + apply_bps(max(cash - new_loans, 0), household["spend_from_savings_bps"])
        )
        response = (responses or {}).get(location, {"spend_bps": BPS, "loyalty_bps": data.LOCAL_PREFERENCE_BPS})
        mood = fortune_bps(seed, f"households:{location}", period, "mood", data.HOUSEHOLD_MOOD_BPS)
        mood += (moods or {}).get(location, 0)
        budget = max(apply_bps(apply_bps(habit, response["spend_bps"]), BPS + mood), 0) + new_loans
        spent[location] = ledger.pay_split_up_to(
            conn, payer=household["account_id"],
            amounts=allocate(world, min(budget, cash), sector_weights, location=location,
                             local_preference_bps=response["loyalty_bps"]),
            kind="customer_revenue", memo=f"Households of {location}: spending in {label}", period=period,
        )
    # TEMPORARY STAND-IN (Stage 4 and 5: investors become players and funds with
    # choices of their own). Founders and small investors spend most of the
    # dividends they received last quarter.
    for investors, who in ((world.founders, "Founders and company insiders"), (world.small_investors, "Small investors")):
        cash = ledger.balance(conn, investors)
        budget = (
            apply_bps(ledger.received_in_period(conn, investors, period - 1), data.INVESTOR_SPEND_FROM_INCOME_BPS)
            + apply_bps(cash, data.INVESTOR_SPEND_FROM_SAVINGS_BPS)
        )
        ledger.pay_split_up_to(
            conn, payer=investors, amounts=allocate(world, min(budget, cash), sector_weights),
            kind="customer_revenue", memo=f"{who}: spending in {label}", period=period,
        )
    return spent


def companies_buy_inputs(conn: Connection, world: World, companies: list[dict], period: int, seed: str,
                         state: dict | None = None) -> None:
    """Each company buys what it needs from other companies.

    How much it orders follows what it sold last quarter. Which supplier gets
    the order is decided by the suppliers' pull, with a preference for one
    based in the buyer's own location.
    """
    label = clock.period_label(period)
    last = {
        r["company_id"]: (r["revenue"] if r["period"] >= 1 else r["base_revenue"])
        for r in _rows(conn, "SELECT company_id, period, revenue, base_revenue FROM company_results WHERE period = %s",
                       (period - 1,))
    }
    dear = relative_prices(state) if state else {}
    for company in companies:
        orders: dict[UUID, int] = {}
        for supplier_sector, share in world.inputs.get(company["sector"], {}).items():
            # Roughly in step with last quarter's sales, but each company orders a
            # little more or less than that, as its managers judge the quarter ahead.
            judgement = fortune_bps(seed, company["ticker"], period, f"orders:{supplier_sector}",
                                    company["volatility_bps"] // 2 + 100)
            wanted = max(apply_bps(apply_bps(last[company["id"]], share), BPS + judgement), 0)
            # A company cannot do without its supplies: when they get dearer, it pays more.
            wanted = apply_bps(wanted, dear.get(supplier_sector, BPS))
            placed = allocate(world, wanted, {supplier_sector: 1},
                              location=company["headquarters"], exclude=company["account_id"])
            for account, amount in placed.items():
                orders[account] = orders.get(account, 0) + amount
        ledger.pay_split_up_to(
            conn, payer=company["account_id"], amounts=orders, kind="business_purchase",
            memo=f"{company['name']}: purchases from suppliers, {label}", period=period,
        )


CAPITAL_RETURNED = ("bond_redemption", "bond_trade", "bond_issue", "takeover_payment", "takeover_refund")
GOVERNMENT_INCOME = ("company_tax", "debt_interest", "share_trade", "exchange_surplus", "salary")   # "salary": the income tax taken from players' pay


def government_spends(conn: Connection, world: World, period: int, *, borrowed: int = 0, debt_cost: int = 0) -> None:
    """TEMPORARY STAND-IN (Stage 12 gives the Government a real budget).

    The Government spends the tax it collected this quarter: part on purchases
    from companies, the rest on public-sector pay. Its reserve is not touched.
    """
    label = clock.period_label(period)
    # Tax, and the interest banks pay on what they have borrowed from the Central Bank.
    # ...and the stamp duty on share trades, and what the exchange earned in fees.
    collected = ledger.received_in_period(conn, world.treasury, period, kinds=GOVERNMENT_INCOME)
    # It spends what it collected, plus what it borrowed to spend, less what its borrowing cost it.
    collected = max(collected + borrowed - debt_cost, 0)
    purchases = apply_bps(collected, data.GOVERNMENT_PURCHASE_BPS)
    weights = {sector: row["government_bps"] for sector, row in world.demand.items()}
    ledger.pay_split_up_to(
        conn, payer=world.treasury, amounts=allocate(world, purchases, weights, location=data.ABUJA),
        kind="government_purchase", memo=f"Government purchases from companies, {label}", period=period,
    )
    ledger.pay_split_up_to(
        conn, payer=world.treasury, amounts=split(collected - purchases, world.population),
        kind="government_wages", memo=f"Public-sector pay, {label}", period=period,
    )


def pensions_paid(conn: Connection, world: World, period: int) -> None:
    """Pension funds pay pensions to households.

    TEMPORARY STAND-IN (Stage 4 opens the market the funds will invest in): until
    then the funds keep what they already own and pay out at about the rate money
    comes in.
    """
    cash = ledger.balance(conn, world.institutions)
    # Money that came back from investments sold or repaid is savings changing form, not new income.
    income = _rows(conn, "SELECT coalesce(sum(e.amount), 0)::bigint AS total FROM ledger_entries e JOIN ledger_transactions t"
                         " ON t.id = e.transaction_id WHERE e.account_id = %s AND e.asset = 'NGN' AND t.period = %s AND e.amount > 0"
                         " AND t.kind <> ALL(%s)", (world.institutions, period, list(CAPITAL_RETURNED)))[0]["total"]
    budget = (
        apply_bps(income, data.PENSION_PAY_FROM_INFLOW_BPS)
        + apply_bps(cash, data.PENSION_PAY_FROM_SAVINGS_BPS)
    )
    ledger.pay_split_up_to(
        conn, payer=world.institutions, amounts=split(min(budget, cash), world.population),
        kind="pension_payment", memo=f"Pensions paid, {clock.period_label(period)}", period=period,
    )


def pay_claims(conn: Connection, world: World, companies: list[dict], period: int, happening: list[dict],
               spent: dict[str, int]) -> tuple[dict, int]:
    """Work out what this quarter's events destroyed, and have the insurers pay.

    Returns each company's destroyed buildings and machines, and the total the
    insurers paid out. Insurers pay 70% of a company's damage, and a small sum
    to the households of a location struck by something severe. They pay in
    proportion to their size, and only what they can afford.
    """
    label = clock.period_label(period)
    assets = {
        r["company_id"]: r["fixed_assets"]
        for r in _rows(conn, "SELECT company_id, fixed_assets FROM company_results WHERE period = %s", (period - 1,))
    }
    insurers = world.members.get("insurance", [])
    damages: dict = {}
    owed: dict[UUID, int] = {}
    for company in companies:
        share = (company.get("event_effects") or {}).get("damage_bps", 0)
        if share <= 0 or company["sector"] == "insurance":
            continue
        destroyed = apply_bps(assets[company["id"]], share)
        damages[company["id"]] = destroyed
        owed[company["account_id"]] = apply_bps(destroyed, data.INSURED_SHARE_BPS)
    _, severe = events.location_moods(happening)
    for location in severe:
        owed[world.households[location]["account_id"]] = apply_bps(spent.get(location, 0), data.HOUSEHOLD_CLAIM_BPS)

    paid = 0
    total_pull = sum(i["pull"] for i in insurers)
    for insurer in insurers:
        if not owed or not total_pull:
            break
        mine = {receiver: amount * insurer["pull"] // total_pull for receiver, amount in owed.items()}
        paid += ledger.pay_split_up_to(
            conn, payer=insurer["account_id"], amounts=mine, kind="insurance_claim",
            memo=f"Insurance claims paid after the events of {label}", period=period,
        )
    return damages, paid


def premium_index_bps(conn: Connection, period: int, paid_now: int) -> int:
    """The price of insurance. It rises after disasters: the more insurers have paid in
    claims over the last year against what they earned, the dearer cover becomes."""
    claims = _rows(
        conn,
        "SELECT coalesce(sum(e.amount), 0)::bigint AS total FROM ledger_entries e"
        " JOIN ledger_transactions t ON t.id = e.transaction_id"
        " WHERE t.kind = 'insurance_claim' AND e.amount > 0 AND t.period BETWEEN %s AND %s", (period - 3, period),
    )[0]["total"]
    earned = _rows(
        conn,
        # (The opening record has no sales yet, so the sales the company began with stand in for it.)
        "SELECT coalesce(sum(CASE WHEN r.period = 0 THEN r.base_revenue ELSE r.revenue END), 0)::bigint AS total"
        " FROM company_results r JOIN companies c ON c.id = r.company_id"
        " WHERE c.sector = 'insurance' AND r.period BETWEEN %s AND %s", (period - 4, period - 1),
    )[0]["total"]
    if earned <= 0:
        return BPS
    return BPS + min(2 * claims * BPS // earned, 5000)             # at most half as dear again


def record_households(conn: Connection, world: World, period: int, spent: dict[str, int],
                      results: list[tuple[dict, dict]]) -> None:
    """Write down what happened to each location's households this quarter."""
    jobs = {loc["name"]: 0 for loc in world.locations}
    by_account = {household["account_id"]: location for location, household in world.households.items()}
    for company, result in results:
        for account, share in world.staff_spread(company["headquarters"]).items():
            jobs[by_account[account]] += result["staff"] * share // BPS
    for location, household in world.households.items():
        account = household["account_id"]
        wages = ledger.received_in_period(conn, account, period, _WAGE_KINDS)
        government = ledger.received_in_period(conn, account, period, _GOVERNMENT_KINDS)
        pensions = ledger.received_in_period(conn, account, period, _PENSION_KINDS)
        claims = ledger.received_in_period(conn, account, period, ("insurance_claim",))
        # Borrowed money is not income: it is recorded beside it.
        conn.execute(
            "INSERT INTO household_results (location, period, wages, government, pensions, income, spending, cash, jobs,"
            " claims, borrowed, debt) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (location, period, wages, government, pensions, wages + government + pensions + claims,
             spent.get(location, 0), ledger.balance(conn, account), jobs[location], claims,
             ledger.received_in_period(conn, account, period, ("household_loan",)),
             _rows(conn, "SELECT coalesce(sum(principal), 0)::bigint AS total FROM household_debts WHERE location = %s",
                   (location,))[0]["total"]),
        )
