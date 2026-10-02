"""Genesis: creating the world, once.

Run from the project root, after the database tables exist:

    python -m simulation.genesis

It is safe to run again: if the world already exists it changes nothing
(except to give a ledger account and starting cash to any player who signed
up before the ledger existed).

What it creates (design document, sections 4 and 10):
  * the Central Bank, which issues the opening money,
  * the Federal Government Treasury and the prize pool,
  * the households of the five locations, and accounts for investors and pension funds,
  * the 12 sectors and the 50 companies, each with an opening balance sheet,
    its shares handed to its owners, and its debts.
"""

from __future__ import annotations

import os
import secrets
from datetime import datetime

import psycopg
from psycopg import Connection
from psycopg.rows import tuple_row
from psycopg.types.json import Jsonb

from simulation import companies, ledger, players
from simulation import world_data as data
from simulation.ledger import NGN, Leg
from simulation.money import apply_bps, million_naira, naira

_GENESIS_LOCK = 4_107_001      # any fixed number; stops two servers creating the world at once


def _company_shape(index: int, company: data.Company, sector: data.Sector) -> dict:
    """A company's opening figures, in kobo, from its size, its sector's shape and
    whatever makes it different from the usual company in that sector.

    Companies in a sector are not identical. Where the catalogue says nothing, each
    gets a small fixed variation of its own, set by its position in the catalogue,
    so that the same world is created every time.
    """
    revenue = million_naira(company.yearly_revenue_m)
    quarter = revenue // 4
    cost_tweak = ((index * 37) % 7 - 3) * 50              # between -1.5 and +1.5 points of revenue
    debt_tweak = 10_000 + ((index * 53) % 5 - 2) * 1_000  # between 80% and 120% of the sector's usual debt
    trend = company.trend_bps if company.trend_bps is not None else ((index * 29) % 7 - 3) * 40
    volatility = company.volatility_bps if company.volatility_bps is not None else 250 + ((index * 41) % 5) * 100
    debt_times = company.debt_times_bps if company.debt_times_bps is not None else debt_tweak

    place = next(loc for loc in data.LOCATIONS if loc.name == company.headquarters)
    location_cost = place.running_cost_bps + data.SECTOR_FIT.get((company.sector, company.headquarters), 0)
    cost_of_sales = min(sector.cost_of_sales_bps + cost_tweak + company.cost_extra_bps, 10_000)
    supplies = sum(data.INPUTS.get(company.sector, {}).values())
    base_opex = apply_bps(apply_bps(apply_bps(quarter, sector.opex_bps), company.opex_times_bps), location_cost)
    wage = naira(place.monthly_wage_naira * 3)

    debt = apply_bps(apply_bps(revenue, sector.debt_x), debt_times)
    bond = apply_bps(debt, company.bond_share_bps)
    overdue = apply_bps(debt - bond, company.overdue_bps)
    return {
        "revenue_growth_bps": trend,                 # its own drift against its rivals
        "volatility_bps": volatility,
        "cost_of_sales_bps": cost_of_sales,
        "labour_bps": max(cost_of_sales - supplies, 0),   # what is left of cost of sales after supplies is pay
        "location_cost_bps": location_cost,
        "opex_bps": base_opex * 10_000 // quarter,
        "base_revenue": quarter,                     # its pull on customers, to begin with
        "base_opex": base_opex,
        "wages": base_opex * 10_000 // (10_000 + data.PENSION_EMPLOYER_BPS),
        "staff": max(base_opex * 10_000 // (10_000 + data.PENSION_EMPLOYER_BPS) // wage, 1),
        "cash": apply_bps(apply_bps(revenue, sector.cash_x), company.cash_times_bps),
        "fixed_assets": apply_bps(revenue, sector.fixed_assets_x),
        "customer_loans": apply_bps(revenue, sector.customer_loans_x),
        "customer_funds": apply_bps(apply_bps(revenue, sector.customer_funds_x), company.funds_times_bps),
        "bank_loan": debt - bond - overdue,
        "overdue_loan": overdue,
        "bond": bond,
        "unpaid_bills": apply_bps(quarter, company.unpaid_bills_bps),
    }


def create_world(conn: Connection, world_start: datetime, fortune_seed: str | None = None) -> bool:
    """Create the world if it does not exist yet. Returns True if it was created now.

    `fortune_seed` is the world's secret, from which each quarter's good and bad
    fortune is worked out. Left empty, a random one is chosen. Tests pass a fixed one.
    """
    if world_start.tzinfo is None:
        raise ValueError("The world's start time must carry its time zone.")
    if fortune_seed is not None and len(fortune_seed) < 32:
        # A short secret could be found by trying every possibility against one
        # quarter of published results. After that, every future quarter is known.
        raise ValueError("The world's secret must be at least 32 characters. Leave it empty for a random one.")
    with conn.transaction():
        conn.execute("SELECT pg_advisory_xact_lock(%s)", (_GENESIS_LOCK,))
        created = conn.execute("SELECT 1 FROM world_state").fetchone() is None
        if created:
            _create(conn, world_start, fortune_seed or secrets.token_hex(16))
        _give_accounts_to_early_players(conn)
    return created


def _create(conn: Connection, world_start: datetime, fortune_seed: str) -> None:
    conn.execute(
        "INSERT INTO world_state (world_start, company_tax_bps, fortune_seed) VALUES (%s, %s, %s)",
        (world_start, data.COMPANY_TAX_BPS, fortune_seed),
    )

    # --- The institutions and stand-in accounts ---
    central_bank = ledger.create_account(
        conn, kind="central_bank", name="Central Bank of Nigeria (naira issued)", code=ledger.CENTRAL_BANK)
    ledger.create_asset(conn, code=NGN, kind="currency", name="Naira", unit="kobo", issuer_account_id=central_bank)
    treasury = ledger.create_account(
        conn, kind="government", name="Federal Government Treasury", code=ledger.TREASURY)
    ledger.create_account(conn, kind="prize_pool", name="Prize pool", code=ledger.PRIZE_POOL)
    households: dict[str, object] = {}
    for order, place in enumerate(data.LOCATIONS):
        conn.execute(
            "INSERT INTO locations (name, sort_order, population_bps, running_cost_bps, quarterly_wage)"
            " VALUES (%s, %s, %s, %s, %s)",
            (place.name, order, place.population_bps, place.running_cost_bps, naira(place.monthly_wage_naira * 3)),
        )
        households[place.name] = ledger.create_account(
            conn, kind="npc_public", name=f"Households of {place.name}", code=f"households:{place.name.lower()}")
    founders = ledger.create_account(
        conn, kind="npc_investors", name="Founders and company insiders", code=ledger.INVESTORS_FOUNDERS)
    institutions = ledger.create_account(
        conn, kind="npc_investors", name="Pension funds and other institutions", code=ledger.INVESTORS_INSTITUTIONS)
    small_investors = ledger.create_account(
        conn, kind="npc_investors", name="Small investors", code=ledger.INVESTORS_PUBLIC)

    for order, sector in enumerate(data.SECTORS):
        conn.execute("INSERT INTO sectors (code, name, sort_order) VALUES (%s, %s, %s)",
                     (sector.code, sector.name, order))
    sectors = {s.code: s for s in data.SECTORS}

    # --- The companies ---
    shapes: dict[str, dict] = {}
    rows: dict[str, dict] = {}
    for index, company in enumerate(data.COMPANIES):
        sector = sectors[company.sector]
        shape = _company_shape(index, company, sector)
        account = ledger.create_account(conn, kind="company", name=company.name, code=f"company:{company.ticker}")
        share_asset = f"SHR-{company.ticker}"
        ledger.create_asset(conn, code=share_asset, kind="share", name=f"{company.name} ordinary shares",
                            unit="share", issuer_account_id=account)
        company_id = conn.execute(
            "INSERT INTO companies (ticker, name, sector, headquarters, account_id, share_asset,"
            " revenue_growth_bps, season_bps, cost_of_sales_bps, opex_growth_bps, depreciation_bps, payout_bps,"
            " volatility_bps, location_cost_bps, opex_bps, labour_bps)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
            (company.ticker, company.name, company.sector, company.headquarters, account, share_asset,
             shape["revenue_growth_bps"], list(sector.season_bps), shape["cost_of_sales_bps"],
             shape["revenue_growth_bps"], data.DEPRECIATION_BPS, sector.payout_bps, shape["volatility_bps"],
             shape["location_cost_bps"], shape["opex_bps"], shape["labour_bps"]),
        ).fetchone()
        shapes[company.ticker] = shape
        rows[company.ticker] = {
            "id": ledger._first(company_id), "account_id": account, "share_asset": share_asset,
            "name": company.name, "index": index,
        }

    household_spending = _describe_the_economy(conn, shapes)
    savings = million_naira(data.HOUSEHOLDS_OPENING_M)
    for place in data.LOCATIONS:
        conn.execute(
            "INSERT INTO households (location, account_id, spend_from_income_bps, spend_from_savings_bps)"
            " VALUES (%s, %s, %s, %s)",
            (place.name, households[place.name], data.HOUSEHOLD_SPEND_FROM_INCOME_BPS,
             (10_000 - data.HOUSEHOLD_SPEND_FROM_INCOME_BPS) * household_spending // savings),
        )

    # --- Opening money: issued by the Central Bank, to each account's opening balance ---
    opening = [
        Leg(treasury, million_naira(data.TREASURY_OPENING_M)),
        *[Leg(households[place.name], apply_bps(savings, place.population_bps)) for place in data.LOCATIONS],
        *[Leg(rows[t]["account_id"], shapes[t]["cash"]) for t in rows],
    ]
    ledger.post(
        conn, kind="opening_balance", memo="Opening balances: the money in existence when the world began",
        legs=[Leg(central_bank, -sum(leg.amount for leg in opening)), *opening], period=0,
    )

    # --- Debts: who owes whom on day one ---
    bonds_issued = -1
    for company in data.COMPANIES:
        shape, row, sector = shapes[company.ticker], rows[company.ticker], sectors[company.sector]
        if shape["bank_loan"] > 0:
            lender = rows[company.lender]
            conn.execute(
                "INSERT INTO company_debts (company_id, lender_account_id, kind, name, original_principal,"
                " principal_outstanding, annual_rate_bps, start_period, maturity_period, repayment)"
                " VALUES (%s, %s, 'bank_loan', %s, %s, %s, %s, 0, %s, 'amortising')",
                (row["id"], lender["account_id"], f"loan from {lender['name']}", shape["bank_loan"],
                 shape["bank_loan"], sector.loan_rate_bps, data.LOAN_TERM_QUARTERS),
            )
        if shape["bond"] > 0:
            bonds_issued += 1
        if shape["overdue_loan"] > 0:
            # A loan that should have been repaid before the world began, and was not.
            lender = rows[company.lender]
            conn.execute(
                "INSERT INTO company_debts (company_id, lender_account_id, kind, name, original_principal,"
                " principal_outstanding, annual_rate_bps, start_period, maturity_period, repayment)"
                " VALUES (%s, %s, 'bank_loan', %s, %s, %s, %s, -8, 0, 'bullet')",
                (row["id"], lender["account_id"], f"overdue loan from {lender['name']}", shape["overdue_loan"],
                 shape["overdue_loan"], sector.loan_rate_bps + 400),
            )
        if shape["unpaid_bills"] > 0:
            conn.execute(
                "INSERT INTO company_payables (company_id, payee_account_id, kind, amount_outstanding, incurred_period)"
                " VALUES (%s, %s, 'wages', %s, 0)",
                (row["id"], households[company.headquarters], shape["unpaid_bills"]),
            )
        if shape["bond"] > 0:
            conn.execute(
                "INSERT INTO company_debts (company_id, lender_account_id, kind, name, original_principal,"
                " principal_outstanding, annual_rate_bps, start_period, maturity_period, repayment)"
                " VALUES (%s, %s, 'bond', %s, %s, %s, %s, 0, %s, 'bullet')",
                (row["id"], institutions, f"{company.name} bond", shape["bond"], shape["bond"],
                 sector.loan_rate_bps - data.BOND_DISCOUNT_BPS,
                 data.BOND_TERM_QUARTERS + bonds_issued * data.BOND_STAGGER_QUARTERS),
            )

    # --- Opening balance sheets, shares and first filings ---
    lent: dict = {}
    with conn.cursor(row_factory=tuple_row) as cur:
        for lender_account, total in cur.execute(
            "SELECT lender_account_id, sum(principal_outstanding)::bigint FROM company_debts GROUP BY lender_account_id"
        ).fetchall():
            lent[lender_account] = total
    loaded = {c["ticker"]: c for c in companies.load_companies(conn)}
    for company in data.COMPANIES:
        shape, row = shapes[company.ticker], rows[company.ticker]
        loans_to_companies = lent.get(row["account_id"], 0)
        borrowings = shape["bank_loan"] + shape["overdue_loan"] + shape["bond"]
        total_assets = shape["cash"] + shape["customer_loans"] + loans_to_companies + shape["fixed_assets"]
        total_liabilities = borrowings + shape["unpaid_bills"] + shape["customer_funds"]
        total_equity = total_assets - total_liabilities
        if total_equity <= 0:
            raise ValueError(f"{company.name} would start out owing more than it owns.")
        share_capital = apply_bps(total_equity, data.SHARE_CAPITAL_BPS)

        # Shares: enough that each starts near ₦20 of owners' funds per share.
        lots = round(total_equity / naira(data.BOOK_VALUE_PER_SHARE_NAIRA) / data.SHARE_LOT)
        shares = max(lots, 1) * data.SHARE_LOT
        to_founders = shares * (3000 + (row["index"] * 700) % 2500) // 10_000
        to_institutions = shares * (3000 + (row["index"] * 500) % 1500) // 10_000
        to_small = shares - to_founders - to_institutions
        ledger.post(
            conn, kind="share_issue", memo=f"{company.name}: shares in issue when the world began",
            legs=[
                Leg(row["account_id"], -shares, row["share_asset"]),
                Leg(founders, to_founders, row["share_asset"]),
                Leg(institutions, to_institutions, row["share_asset"]),
                Leg(small_investors, to_small, row["share_asset"]),
            ],
            period=0,
        )

        result = {
            "company_id": row["id"], "period": 0,
            "revenue": 0, "interest_income": 0, "cost_of_sales": 0, "operating_expenses": 0,
            "depreciation": 0, "operating_profit": 0, "interest_expense": 0, "profit_before_tax": 0,
            "tax": 0, "net_profit": 0,
            "cash_opening": shape["cash"], "cash_from_operations": 0, "cash_from_investing": 0,
            "cash_from_financing": 0, "cash_closing": shape["cash"], "capital_spending": 0,
            "debt_repaid": 0, "dividends_paid": 0,
            "cash": ledger.balance(conn, row["account_id"]), "customer_loans": shape["customer_loans"],
            "loans_to_companies": loans_to_companies, "fixed_assets": shape["fixed_assets"],
            "total_assets": total_assets, "borrowings": borrowings, "payables": shape["unpaid_bills"],
            "customer_funds": shape["customer_funds"], "total_liabilities": total_liabilities,
            "share_capital": share_capital, "retained_earnings": total_equity - share_capital,
            "total_equity": total_equity, "principal_overdue": shape["overdue_loan"], "shares_in_issue": shares,
            "base_revenue": shape["base_revenue"], "base_opex": shape["base_opex"],
            "ledger_totals": companies.ledger_totals(conn, row["account_id"]),
            "drivers": {"revenue": [], "notes": _opening_notes(shape)},
            "staff": shape["staff"], "wages": shape["wages"],
            "sales_households": 0, "sales_business": 0, "sales_government": 0,
        }
        companies.insert_result(conn, result)
        companies.file_report(conn, loaded[company.ticker], result)


def _describe_the_economy(conn: Connection, shapes: dict[str, dict]) -> int:
    """Record what companies buy from each other and where spending goes.

    How households divide their spending is not typed in by hand. It is worked
    out so that the world starts close to balance: each sector's sales to
    households are what is left of its opening sales after what other companies,
    the Government and investment are expected to buy from it.

    Returns the households' total spending in an opening quarter, in kobo.
    """
    for buyer, suppliers in data.INPUTS.items():
        for supplier, bps in suppliers.items():
            conn.execute("INSERT INTO sector_inputs (buyer, supplier, bps) VALUES (%s, %s, %s)", (buyer, supplier, bps))

    sales = {s.code: 0 for s in data.SECTORS}
    upkeep = 0
    for company in data.COMPANIES:
        sales[company.sector] += shapes[company.ticker]["base_revenue"]
        upkeep += apply_bps(shapes[company.ticker]["fixed_assets"], data.DEPRECIATION_BPS)
    total = sum(sales.values())
    government = apply_bps(apply_bps(total, 300), data.GOVERNMENT_PURCHASE_BPS)     # tax runs near 3% of all sales

    to_households = {}
    for sector in sales:
        from_business = sum(apply_bps(sales[buyer], data.INPUTS.get(buyer, {}).get(sector, 0)) for buyer in sales)
        from_government = apply_bps(government, data.GOVERNMENT_BUYS.get(sector, 0))
        from_investment = apply_bps(upkeep, data.INVESTMENT_BUYS.get(sector, 0))
        left = sales[sector] - from_business - from_government - from_investment
        to_households[sector] = max(left, sales[sector] // 50)                      # never less than 2% of its sales
    for sector, amount in to_households.items():
        conn.execute(
            "INSERT INTO sector_demand (sector, household_bps, government_bps, investment_bps) VALUES (%s, %s, %s, %s)",
            (sector, amount // 100_000_000, data.GOVERNMENT_BUYS.get(sector, 0), data.INVESTMENT_BUYS.get(sector, 0)),
        )
    spending = sum(to_households.values())
    # The households' opening record: what they are taken to have earned in the
    # quarter before the game began, so that they have something to spend in the first.
    savings = million_naira(data.HOUSEHOLDS_OPENING_M)
    for place in data.LOCATIONS:
        income = apply_bps(spending, place.population_bps)
        conn.execute(
            "INSERT INTO household_results (location, period, wages, government, pensions, income, spending, cash, jobs)"
            " VALUES (%s, 0, %s, 0, 0, %s, 0, %s, 0)",
            (place.name, income, income, apply_bps(savings, place.population_bps)),
        )
    return spending


def _opening_notes(shape: dict) -> list[str]:
    notes = []
    if shape["overdue_loan"] > 0:
        notes.append("It began the game with a bank loan already past its repayment date and unpaid.")
    if shape["unpaid_bills"] > 0:
        notes.append("It began the game behind on its bills.")
    return notes


def _give_accounts_to_early_players(conn: Connection) -> None:
    early = conn.execute(
        "SELECT p.id FROM players p LEFT JOIN ledger_accounts a ON a.player_id = p.id WHERE a.id IS NULL"
    ).fetchall()
    for row in early:
        players.open_player_account(conn, ledger._first(row))


if __name__ == "__main__":
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("Set DATABASE_URL first. See README.md.")
    start = datetime.fromisoformat(os.environ.get("WORLD_START", "2026-10-05T00:00:00+01:00"))
    with psycopg.connect(url, autocommit=True) as connection:
        made = create_world(connection, start, os.environ.get("WORLD_SEED") or None)
    print("The world was created." if made else "The world already exists. Nothing was changed.")
