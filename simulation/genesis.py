"""Genesis: creating the world, once.

Run from the project root, after the database tables exist:

    python -m simulation.genesis

It is safe to run again: if the world already exists it changes nothing
(except to give a ledger account and starting cash to any player who signed
up before the ledger existed).

What it creates (design document, sections 4 and 10):
  * the Central Bank, which issues the opening money,
  * the Federal Government Treasury and the prize pool,
  * stand-in accounts for the public and for NPC investors,
  * the 12 sectors and the 40 companies, each with an opening balance sheet,
    its shares handed to its owners, and its debts.
"""

from __future__ import annotations

import os
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
    """A company's opening figures, in kobo, from its size and its sector's shape.

    Companies in a sector are not identical: each gets a small fixed variation
    in its costs and its debt, set by its position in the catalogue, so that the
    same world is created every time.
    """
    revenue = million_naira(company.yearly_revenue_m)
    cost_tweak = ((index * 37) % 7 - 3) * 50              # between -1.5 and +1.5 points of revenue
    debt_tweak = 10_000 + ((index * 53) % 5 - 2) * 1_000  # between 80% and 120% of the sector's usual debt
    debt = apply_bps(apply_bps(revenue, sector.debt_x), debt_tweak)
    bond = apply_bps(debt, company.bond_share_bps)
    return {
        "cost_of_sales_bps": sector.cost_of_sales_bps + cost_tweak,
        "base_revenue": revenue // 4,
        "base_opex": apply_bps(revenue // 4, sector.opex_bps),
        "cash": apply_bps(revenue, sector.cash_x),
        "fixed_assets": apply_bps(revenue, sector.fixed_assets_x),
        "customer_loans": apply_bps(revenue, sector.customer_loans_x),
        "customer_funds": apply_bps(revenue, sector.customer_funds_x),
        "bank_loan": debt - bond,
        "bond": bond,
    }


def create_world(conn: Connection, world_start: datetime) -> bool:
    """Create the world if it does not exist yet. Returns True if it was created now."""
    if world_start.tzinfo is None:
        raise ValueError("The world's start time must carry its time zone.")
    with conn.transaction():
        conn.execute("SELECT pg_advisory_xact_lock(%s)", (_GENESIS_LOCK,))
        created = conn.execute("SELECT 1 FROM world_state").fetchone() is None
        if created:
            _create(conn, world_start)
        _give_accounts_to_early_players(conn)
    return created


def _create(conn: Connection, world_start: datetime) -> None:
    conn.execute(
        "INSERT INTO world_state (world_start, company_tax_bps) VALUES (%s, %s)",
        (world_start, data.COMPANY_TAX_BPS),
    )

    # --- The institutions and stand-in accounts ---
    central_bank = ledger.create_account(
        conn, kind="central_bank", name="Central Bank of Nigeria (naira issued)", code=ledger.CENTRAL_BANK)
    ledger.create_asset(conn, code=NGN, kind="currency", name="Naira", unit="kobo", issuer_account_id=central_bank)
    treasury = ledger.create_account(
        conn, kind="government", name="Federal Government Treasury", code=ledger.TREASURY)
    ledger.create_account(conn, kind="prize_pool", name="Prize pool", code=ledger.PRIZE_POOL)
    public = ledger.create_account(
        conn, kind="npc_public", name="Households and small businesses of Nigeria", code=ledger.PUBLIC)
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

    # --- The 40 companies ---
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
            " revenue_growth_bps, season_bps, cost_of_sales_bps, opex_growth_bps, depreciation_bps, payout_bps)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
            (company.ticker, company.name, company.sector, company.headquarters, account, share_asset,
             sector.revenue_growth_bps, list(sector.season_bps), shape["cost_of_sales_bps"],
             sector.revenue_growth_bps, data.DEPRECIATION_BPS, sector.payout_bps),
        ).fetchone()
        shapes[company.ticker] = shape
        rows[company.ticker] = {
            "id": ledger._first(company_id), "account_id": account, "share_asset": share_asset,
            "name": company.name, "index": index,
        }

    # --- Opening money: issued by the Central Bank, to each account's opening balance ---
    opening = [
        Leg(treasury, million_naira(data.TREASURY_OPENING_M)),
        Leg(public, million_naira(data.PUBLIC_OPENING_M)),
        *[Leg(rows[t]["account_id"], shapes[t]["cash"]) for t in rows],
    ]
    ledger.post(
        conn, kind="opening_balance", memo="Opening balances: the money in existence when the world began",
        legs=[Leg(central_bank, -sum(leg.amount for leg in opening)), *opening], period=0,
    )

    # --- Debts: who owes whom on day one ---
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
            conn.execute(
                "INSERT INTO company_debts (company_id, lender_account_id, kind, name, original_principal,"
                " principal_outstanding, annual_rate_bps, start_period, maturity_period, repayment)"
                " VALUES (%s, %s, 'bond', %s, %s, %s, %s, 0, %s, 'bullet')",
                (row["id"], institutions, f"{company.name} bond", shape["bond"], shape["bond"],
                 sector.loan_rate_bps - data.BOND_DISCOUNT_BPS, data.BOND_TERM_QUARTERS),
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
        borrowings = shape["bank_loan"] + shape["bond"]
        total_assets = shape["cash"] + shape["customer_loans"] + loans_to_companies + shape["fixed_assets"]
        total_liabilities = borrowings + shape["customer_funds"]
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
            "total_assets": total_assets, "borrowings": borrowings, "payables": 0,
            "customer_funds": shape["customer_funds"], "total_liabilities": total_liabilities,
            "share_capital": share_capital, "retained_earnings": total_equity - share_capital,
            "total_equity": total_equity, "principal_overdue": 0, "shares_in_issue": shares,
            "base_revenue": shape["base_revenue"], "base_opex": shape["base_opex"],
            "ledger_totals": companies.ledger_totals(conn, row["account_id"]),
            "drivers": {"revenue": [], "notes": []},
        }
        companies.insert_result(conn, result)
        companies.file_report(conn, loaded[company.ticker], result)


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
        made = create_world(connection, start)
    print("The world was created." if made else "The world already exists. Nothing was changed.")
