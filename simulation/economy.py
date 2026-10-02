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

from simulation import clock, ledger
from simulation import world_data as data
from simulation.fortune import fortune_bps
from simulation.money import BPS, apply_bps

# Reasons money reaches households, for their income record.
_WAGE_KINDS = ("wages", "cost_of_sales")
_GOVERNMENT_KINDS = ("government_wages",)
_PENSION_KINDS = ("pension_payment",)


class WorldTooOld(ledger.LedgerError):
    """The world was created before households existed and cannot be run by this version."""


@dataclass
class World:
    """The parts of the economy every step needs, read once per quarter."""
    treasury: UUID
    founders: UUID
    institutions: UUID          # the pension funds
    small_investors: UUID
    locations: list[dict]                      # name, population_bps, running_cost_bps, quarterly_wage
    households: dict[str, dict]                # location -> account_id and spending habits
    demand: dict[str, dict]                    # sector -> household_bps, government_bps, investment_bps
    inputs: dict[str, dict[str, int]]          # buyer sector -> supplier sector -> share of sales
    seasons: dict[str, list[int]]              # sector -> the four seasons
    members: dict[str, list[dict]] = field(default_factory=dict)   # sector -> companies with this quarter's pull

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
    return World(
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
             location: str | None = None, exclude: UUID | None = None) -> dict[UUID, int]:
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
            local = data.LOCAL_PREFERENCE_BPS if company["headquarters"] == location else BPS
            pulls[company["account_id"]] = company["pull"] * local
        for account, part in split(sector_amount, pulls).items():
            shares[account] = shares.get(account, 0) + part
    return shares


def set_market_pulls(conn: Connection, world: World, companies: list[dict], period: int, seed: str) -> dict[UUID, int]:
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
    carried: dict[UUID, int] = {}
    world.members = {}
    for company in companies:
        lasting = max(apply_bps(previous[company["id"]], BPS + company["revenue_growth_bps"]), 1)
        own = fortune_bps(seed, company["ticker"], period, "sales", company["volatility_bps"])
        carried[company["id"]] = lasting
        company["own_fortune_bps"] = own
        world.members.setdefault(company["sector"], []).append({
            "account_id": company["account_id"], "headquarters": company["headquarters"],
            "pull": max(apply_bps(lasting, BPS + own), 1),
        })
    return carried


def household_sector_weights(world: World, period: int, seed: str) -> tuple[dict[str, int], dict[str, int]]:
    """How households divide their spending between sectors this quarter.

    The usual shares, moved by the season and by each sector's good or bad
    quarter. Returns the weights, and each sector's fortune for the record.
    """
    weights, fortunes = {}, {}
    for sector, row in world.demand.items():
        season = world.seasons[sector][(period - 1) % 4]
        fortunes[sector] = fortune_bps(seed, sector, period, "demand", data.SECTOR_VOLATILITY_BPS)
        weights[sector] = row["household_bps"] * season // BPS * (BPS + fortunes[sector]) // BPS
    return weights, fortunes


def households_spend(conn: Connection, world: World, period: int, sector_weights: dict[str, int]) -> dict[str, int]:
    """Households and private investors spend at the companies. Returns spending by location."""
    label = clock.period_label(period)
    spent: dict[str, int] = {}
    last = {r["location"]: r for r in _rows(conn, "SELECT * FROM household_results WHERE period = %s", (period - 1,))}
    for location, household in world.households.items():
        cash = ledger.balance(conn, household["account_id"])
        budget = (
            apply_bps(last[location]["income"], household["spend_from_income_bps"])
            + apply_bps(cash, household["spend_from_savings_bps"])
        )
        spent[location] = ledger.pay_split_up_to(
            conn, payer=household["account_id"],
            amounts=allocate(world, min(budget, cash), sector_weights, location=location),
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


def companies_buy_inputs(conn: Connection, world: World, companies: list[dict], period: int) -> None:
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
    for company in companies:
        orders: dict[UUID, int] = {}
        for supplier_sector, share in world.inputs.get(company["sector"], {}).items():
            wanted = apply_bps(last[company["id"]], share)
            placed = allocate(world, wanted, {supplier_sector: 1},
                              location=company["headquarters"], exclude=company["account_id"])
            for account, amount in placed.items():
                orders[account] = orders.get(account, 0) + amount
        ledger.pay_split_up_to(
            conn, payer=company["account_id"], amounts=orders, kind="business_purchase",
            memo=f"{company['name']}: purchases from suppliers, {label}", period=period,
        )


def government_spends(conn: Connection, world: World, period: int) -> None:
    """TEMPORARY STAND-IN (Stage 12 gives the Government a real budget).

    The Government spends the tax it collected this quarter: part on purchases
    from companies, the rest on public-sector pay. Its reserve is not touched.
    """
    label = clock.period_label(period)
    collected = ledger.received_in_period(conn, world.treasury, period, kinds=("company_tax",))
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
    budget = (
        apply_bps(ledger.received_in_period(conn, world.institutions, period), data.PENSION_PAY_FROM_INFLOW_BPS)
        + apply_bps(cash, data.PENSION_PAY_FROM_SAVINGS_BPS)
    )
    ledger.pay_split_up_to(
        conn, payer=world.institutions, amounts=split(min(budget, cash), world.population),
        kind="pension_payment", memo=f"Pensions paid, {clock.period_label(period)}", period=period,
    )


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
        income = ledger.received_in_period(conn, account, period)
        conn.execute(
            "INSERT INTO household_results (location, period, wages, government, pensions, income, spending, cash, jobs)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (location, period,
             ledger.received_in_period(conn, account, period, _WAGE_KINDS),
             ledger.received_in_period(conn, account, period, _GOVERNMENT_KINDS),
             ledger.received_in_period(conn, account, period, _PENSION_KINDS),
             income, spent.get(location, 0), ledger.balance(conn, account), jobs[location]),
        )
