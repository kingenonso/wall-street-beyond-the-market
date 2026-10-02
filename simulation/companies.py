"""The company engine: it owns every company's accounts.

Once per game quarter, for each company, it:

  1. counts the quarter's sales: what households, other companies and the
     Government actually paid it,
  2. pays any old bills still owed,
  3. pays its people, its interest and its tax,
  4. repays the debt that is due,
  5. spends on upkeep and expansion and pays a dividend, if it can afford to,
  6. writes the three statements (income, cash flow, balance sheet) into the TRUE record,
  7. files a report for the public into the REPORTED record.

Every naira moves through the ledger, so every payment has a payer and a
receiver. If a company cannot pay a bill, it pays what it can and owes the rest.

A company's sales are no longer set by a trend. They are whatever its customers
chose to spend with it this quarter (see simulation/economy.py).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from uuid import UUID

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from simulation import clock, credit, economy, ledger
from simulation import world_data as data
from simulation.fortune import fortune_bps  # noqa: F401  (also used by tests through this module)
from simulation.ledger import NGN, Leg
from simulation.money import BPS, apply_bps

# What a ledger movement means for the cash flow statement.
_SALES = ("customer_revenue", "business_purchase", "government_purchase", "capital_spending")
_OPERATING = {"customer_revenue", "business_purchase", "government_purchase", "cost_of_sales", "wages",
              "debt_interest", "company_tax"}
_FINANCING = {"dividend"}
# 'capital_spending' is investing for the company that spends it and a sale for the company that receives it.
# 'debt_repayment' is financing for the borrower (money out) and investing for the lender (money in).

INCOME_LINES = (
    "revenue", "interest_income", "cost_of_sales", "operating_expenses", "depreciation",
    "operating_profit", "interest_expense", "profit_before_tax", "tax", "net_profit",
)
CASH_FLOW_LINES = (
    "cash_opening", "cash_from_operations", "cash_from_investing", "cash_from_financing", "cash_closing",
    "capital_spending", "debt_repaid", "dividends_paid",
)
BALANCE_SHEET_LINES = (
    "cash", "customer_loans", "loans_to_companies", "fixed_assets", "total_assets",
    "borrowings", "payables", "customer_funds", "total_liabilities",
    "share_capital", "retained_earnings", "total_equity",
)


class BooksDoNotBalance(Exception):
    """A company's accounts failed a consistency check. The quarter is not closed."""


@dataclass
class Context:
    """What every company's quarter needs to know about the world around it."""
    world: economy.World
    tax_bps: int
    fortune_seed: str
    lasting_pull: dict            # company id -> the pull on customers it carries into next quarter
    sector_fortune: dict          # sector -> this quarter's good or bad fortune


def _rows(conn: Connection, sql: str, params=()) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def _row(conn: Connection, sql: str, params=()) -> dict | None:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchone()


def quarterly_interest(principal: int, annual_rate_bps: int) -> int:
    """One quarter's interest: a quarter of the yearly rate, to the nearest kobo."""
    return (principal * annual_rate_bps + 2 * BPS) // (4 * BPS)


def principal_due(outstanding: int, repayment: str, maturity_period: int, period: int) -> int:
    """How much of a debt must be repaid this quarter."""
    if outstanding <= 0:
        return 0
    if period >= maturity_period:
        return outstanding                      # the end date has arrived: all of it
    if repayment == "bullet":
        return 0                                # nothing until the end date
    quarters_left = maturity_period - period + 1
    return -(-outstanding // quarters_left)     # equal slices, rounded up


def _pay_or_owe(conn, company, payee, amount, *, kind, memo, period, reference=None) -> int:
    """Pay a bill. Whatever cannot be paid is recorded as owed. Returns the amount paid."""
    paid = ledger.pay_up_to(
        conn, payer=company["account_id"], receiver=payee, wanted=amount,
        kind=kind, memo=memo, period=period, reference=reference,
    )
    if paid < amount:
        _owe(conn, company, payee, kind, amount - paid, period)
    return paid


def _owe(conn, company, payee, kind, amount, period) -> None:
    conn.execute(
        "INSERT INTO company_payables (company_id, payee_account_id, kind, amount_outstanding, incurred_period)"
        " VALUES (%s, %s, %s, %s, %s)",
        (company["id"], payee, kind, amount, period),
    )


def _pay_people(conn, company, ctx, amount, *, kind, memo, period, pension: int = 0) -> int:
    """Pay a company's people, spread over the locations where they work.

    `pension` is the part that goes to the pension funds instead of into pockets.
    Whatever cannot be paid is owed to the households of its head-office location.
    """
    world = ctx.world
    amounts = economy.split(amount - pension, world.staff_spread(company["headquarters"]))
    if pension > 0:
        amounts[world.institutions] = pension
    due = sum(amounts.values())
    paid = ledger.pay_split_up_to(
        conn, payer=company["account_id"], amounts=amounts, kind=kind, memo=memo, period=period,
    )
    if paid < due:
        home = world.households[company["headquarters"]]["account_id"]
        _owe(conn, company, home, kind, due - paid, period)
    return due


def _settle_old_bills(conn, company, period) -> None:
    """Pay bills left unpaid in earlier quarters, oldest first, as far as cash allows."""
    owed = _rows(
        conn,
        "SELECT id, payee_account_id, kind, amount_outstanding, incurred_period FROM company_payables"
        " WHERE company_id = %s AND amount_outstanding > 0 ORDER BY incurred_period, created_at, id",
        (company["id"],),
    )
    for bill in owed:
        paid = ledger.pay_up_to(
            conn, payer=company["account_id"], receiver=bill["payee_account_id"],
            wanted=bill["amount_outstanding"], kind=bill["kind"],
            memo=f"{company['name']}: late payment of a bill from {clock.period_label(bill['incurred_period'])}",
            period=period,
        )
        if paid:
            conn.execute(
                "UPDATE company_payables SET amount_outstanding = amount_outstanding - %s WHERE id = %s",
                (paid, bill["id"]),
            )


def _pay_dividend(conn, company, amount, period) -> int:
    """Share a dividend among the owners in proportion to their shares. Returns what was paid."""
    holders = _rows(
        conn,
        "SELECT account_id, balance FROM ledger_balances WHERE asset = %s AND balance > 0 ORDER BY account_id",
        (company["share_asset"],),
    )
    shares = sum(h["balance"] for h in holders)
    if shares == 0 or amount <= 0:
        return 0
    # Each owner gets their exact proportion, rounded down to the kobo. The few
    # kobo of rounding stay with the company.
    legs = [Leg(h["account_id"], amount * h["balance"] // shares) for h in holders]
    legs = [leg for leg in legs if leg.amount > 0]
    total = sum(leg.amount for leg in legs)
    if total == 0:
        return 0
    ledger.post(
        conn, kind="dividend", memo=f"{company['name']}: dividend for {clock.period_label(period)}",
        legs=[Leg(company["account_id"], -total), *legs], period=period,
    )
    return total


def ledger_totals(conn, account) -> dict[str, dict[str, int]]:
    """Everything an account has ever received and paid in naira, by reason, read from the ledger."""
    rows = _rows(
        conn,
        "SELECT t.kind,"
        "       coalesce(sum(e.amount) FILTER (WHERE e.amount > 0), 0)::bigint AS received,"
        "       coalesce(-sum(e.amount) FILTER (WHERE e.amount < 0), 0)::bigint AS paid"
        " FROM ledger_entries e JOIN ledger_transactions t ON t.id = e.transaction_id"
        " WHERE e.account_id = %s AND e.asset = %s GROUP BY t.kind",
        (account, NGN),
    )
    return {r["kind"]: {"received": r["received"], "paid": r["paid"]} for r in rows}


def _movements_since(conn, account, earlier: dict) -> dict[str, dict[str, int]]:
    """An account's cash movements since an earlier reading of its totals, by reason.

    Working from running totals means every movement lands in exactly one
    quarter, whenever it happened and in whatever order it was saved.
    """
    moves = {}
    for kind, now in ledger_totals(conn, account).items():
        before = earlier.get(kind, {"received": 0, "paid": 0})
        change = {"received": now["received"] - before["received"], "paid": now["paid"] - before["paid"]}
        if change["received"] or change["paid"]:
            moves[kind] = change
    return moves


def _percent(bps: int) -> str:
    return f"{bps / 100:.1f}".rstrip("0").rstrip(".") + "%"


def close_company_quarter(conn: Connection, company: dict, period: int, ctx: Context) -> dict:
    """Run one company through one quarter and write its true record. Returns that record."""
    prev = _row(
        conn, "SELECT * FROM company_results WHERE company_id = %s AND period = %s",
        (company["id"], period - 1),
    )
    if prev is None:
        raise BooksDoNotBalance(f"{company['name']} has no record for the quarter before {period}.")
    world = ctx.world
    account = company["account_id"]
    name = company["name"]
    label = clock.period_label(period)
    notes: list[str] = []

    # Hold the company's cash still while its quarter is closed: any other payment
    # touching this account waits until the close is saved.
    conn.execute("SELECT 1 FROM ledger_balances WHERE account_id = %s AND asset = %s FOR UPDATE", (account, NGN))

    # 1. Sales: what customers actually paid since the last quarter closed, read from the ledger.
    counted = prev["ledger_totals"]
    moves = _movements_since(conn, account, counted)

    def received(kind: str) -> int:
        return moves.get(kind, {}).get("received", 0)

    sales_households = received("customer_revenue")
    sales_business = received("business_purchase") + received("capital_spending")
    sales_government = received("government_purchase")
    revenue = sales_households + sales_business + sales_government
    supplies_bought = moves.get("business_purchase", {}).get("paid", 0)

    # 2. Old bills come before new spending.
    _settle_old_bills(conn, company, period)

    # 3. This quarter's costs. Direct labour follows what was sold; this quarter's
    #    good or bad fortune with costs shows here.
    cost_fortune = fortune_bps(ctx.fortune_seed, company["ticker"], period, "costs", company["volatility_bps"] // 3)
    labour_rate = min(max(company["labour_bps"] + cost_fortune, 0), BPS)
    direct_labour = _pay_people(
        conn, company, ctx, apply_bps(revenue, labour_rate), kind="cost_of_sales",
        memo=f"{name}: pay for the people who make and deliver what it sells, {label}", period=period,
    )
    cost_of_sales = supplies_bought + direct_labour
    if cost_fortune >= 100:
        notes.append(f"Its costs ran {_percent(cost_fortune)} of sales higher than usual this quarter.")
    elif cost_fortune <= -100:
        notes.append(f"Its costs ran {_percent(-cost_fortune)} of sales lower than usual this quarter.")

    # Running costs are mostly staff. They move part of the way, each quarter, towards
    # what sales justify: a growing company hires, a shrinking one lets people go.
    # A company in trouble cuts harder.
    target = apply_bps(revenue, company["opex_bps"])
    operating_expenses = prev["base_opex"] + apply_bps(target - prev["base_opex"], data.OPEX_ADJUST_BPS)
    in_trouble = prev["payables"] > 0 or prev["principal_overdue"] > 0 or (prev["period"] >= 1 and prev["net_profit"] < 0)
    if in_trouble:
        operating_expenses = apply_bps(operating_expenses, BPS - data.DISTRESS_CUT_BPS)
    operating_expenses = max(operating_expenses, 1)
    # Of the running costs, the employer's pension contribution sits on top of the wage,
    # and the employee's contribution is taken out of it.
    wages = operating_expenses * BPS // (BPS + data.PENSION_EMPLOYER_BPS)
    pension = operating_expenses - wages + apply_bps(wages, data.PENSION_EMPLOYEE_BPS)
    # (Sharing pay out over five locations in whole kobo can leave a few kobo
    # unshared; the cost recorded is exactly what was due.)
    operating_expenses = _pay_people(
        conn, company, ctx, operating_expenses, kind="wages", pension=pension,
        memo=f"{name}: wages and pension contributions, {label}", period=period,
    )
    wage_here = next(loc["quarterly_wage"] for loc in world.locations if loc["name"] == company["headquarters"])
    staff = max(wages // wage_here, 1)
    if prev["staff"] > 0:
        change = staff - prev["staff"]
        if change * 50 <= -prev["staff"]:                      # two percent or more
            notes.append(f"It cut about {_round_people(-change)} jobs this quarter.")
        elif change * 50 >= prev["staff"]:
            notes.append(f"It took on about {_round_people(change)} more staff this quarter.")
    depreciation = apply_bps(prev["fixed_assets"], company["depreciation_bps"])

    # 4. Interest on what it has borrowed.
    debts = _rows(
        conn,
        "SELECT * FROM company_debts WHERE company_id = %s AND principal_outstanding > 0"
        " ORDER BY start_period, id FOR UPDATE",
        (company["id"],),
    )
    interest_expense = 0
    for debt in debts:
        due = quarterly_interest(debt["principal_outstanding"], debt["annual_rate_bps"])
        interest_expense += due
        _pay_or_owe(conn, company, debt["lender_account_id"], due, kind="debt_interest",
                    memo=f"{name}: interest on {debt['name']}, {label}",
                    period=period, reference=f"debt:{debt['id']}")

    # Interest it has received as a lender this quarter, read from the ledger.
    interest_income = _movements_since(conn, account, counted).get("debt_interest", {}).get("received", 0)

    operating_profit = revenue + interest_income - cost_of_sales - operating_expenses - depreciation
    profit_before_tax = operating_profit - interest_expense
    tax = apply_bps(profit_before_tax, ctx.tax_bps) if profit_before_tax > 0 else 0
    _pay_or_owe(conn, company, world.treasury, tax, kind="company_tax",
                memo=f"{name}: company tax, {label}", period=period)
    net_profit = profit_before_tax - tax

    # 5. Repay the debt that is due.
    principal_overdue = 0
    repayments_missed = 0
    # TEMPORARY STAND-IN (Stage 3 Part B: banks decide their own lending; Stage 4: the
    # bond market). A lender renews the debt of a borrower in good health instead of
    # taking the money back, so sound companies stay financed and money keeps moving.
    # A borrower that is losing money, behind on its bills or already late must repay.
    renewable = (
        net_profit > 0 and prev["payables"] == 0 and prev["principal_overdue"] == 0
        and ledger.balance(conn, account) > 0
        and _row(conn, "SELECT coalesce(sum(amount_outstanding), 0)::bigint AS owed FROM company_payables"
                       " WHERE company_id = %s", (company["id"],))["owed"] == 0
    )
    for debt in debts:
        due = principal_due(debt["principal_outstanding"], debt["repayment"], debt["maturity_period"], period)
        if due > 0 and renewable and debt["maturity_period"] > 0:
            term = data.BOND_TERM_QUARTERS if debt["repayment"] == "bullet" else 1
            conn.execute("UPDATE company_debts SET maturity_period = maturity_period + %s WHERE id = %s",
                         (term, debt["id"]))
            continue
        paid = ledger.pay_up_to(
            conn, payer=account, receiver=debt["lender_account_id"], wanted=due,
            kind="debt_repayment", memo=f"{name}: repayment of {debt['name']}, {label}",
            period=period, reference=f"debt:{debt['id']}",
        )
        if paid:
            conn.execute(
                "UPDATE company_debts SET principal_outstanding = principal_outstanding - %s WHERE id = %s",
                (paid, debt["id"]),
            )
        if period >= debt["maturity_period"]:
            principal_overdue += debt["principal_outstanding"] - paid
        if paid < due:
            repayments_missed += due - paid
            notes.append(f"It could not repay all of the debt due this quarter on its {debt['name']}.")

    payables = _row(
        conn, "SELECT coalesce(sum(amount_outstanding), 0)::bigint AS owed FROM company_payables WHERE company_id = %s",
        (company["id"],),
    )["owed"]
    if payables > 0:
        notes.append("It could not pay all of its bills this quarter. The unpaid part is still owed.")

    # 6. Optional spending, only when nothing is owed and a cash cushion remains.
    #    Buildings and machines are bought from other companies, so this spending
    #    is somebody else's sale.
    cushion = operating_expenses              # keep one quarter of running costs in hand
    in_good_standing = payables == 0 and principal_overdue == 0 and repayments_missed == 0
    comfortable = data.CASH_TARGET_QUARTERS * (operating_expenses + interest_expense)
    investment_weights = {sector: row["investment_bps"] for sector, row in world.demand.items()}

    def spare_above(level: int) -> int:
        return max(ledger.balance(conn, account) - level, 0) if in_good_standing else 0

    upkeep = min(depreciation, spare_above(cushion))
    # A company holding more cash than it needs puts part of it to work.
    lends = company["is_lender"] or prev["customer_funds"] > 0       # banks and insurers do not build factories
    expansion = 0
    if net_profit > 0 and not lends:
        expansion = apply_bps(max(spare_above(comfortable) - upkeep, 0), data.SPARE_CASH_TO_EXPANSION_BPS)
    capital_spending = ledger.pay_split_up_to(
        conn, payer=account,
        amounts=economy.allocate(world, upkeep + expansion, investment_weights,
                                 location=company["headquarters"], exclude=account),
        kind="capital_spending", memo=f"{name}: buildings and machines, {label}", period=period,
    )
    if capital_spending < depreciation * 99 // 100:
        notes.append("It cut back on upkeep of its buildings and machines to protect its cash.")
    elif expansion > 0 and capital_spending > depreciation * 3 // 2:
        notes.append("It put spare cash into expanding the business.")

    dividends_paid = 0
    if net_profit > 0:
        wanted = apply_bps(net_profit, company["payout_bps"])
        # An extra dividend from spare cash, but never more than a small part of the
        # past profits kept in the business: owners cannot strip a company bare.
        extra = min(
            apply_bps(spare_above(comfortable), data.SPARE_CASH_TO_OWNERS_BPS * (2 if lends else 1)),
            apply_bps(max(prev["retained_earnings"], 0), data.EXTRA_DIVIDEND_LIMIT_BPS),
        )
        dividends_paid = _pay_dividend(conn, company, min(wanted + extra, spare_above(cushion)), period)
        if dividends_paid < wanted * 99 // 100:
            notes.append("It held back part of its dividend to protect its cash.")

    # 7. The cash flow statement is read straight from the ledger, not assumed.
    # A new kind of company payment added in a later stage must be given its place
    # here; until then the engine refuses to guess, and the quarter is not closed.
    moves = _movements_since(conn, account, counted)
    unknown = set(moves) - _OPERATING - _FINANCING - {"debt_repayment", "capital_spending"}
    if unknown:
        raise BooksDoNotBalance(f"{name} has cash movements the company engine does not recognise: {sorted(unknown)}")

    def net(kind: str) -> int:
        move = moves.get(kind, {"received": 0, "paid": 0})
        return move["received"] - move["paid"]

    repay = moves.get("debt_repayment", {"received": 0, "paid": 0})
    built = moves.get("capital_spending", {"received": 0, "paid": 0})
    cash_from_operations = sum(net(kind) for kind in _OPERATING) + built["received"]
    cash_from_investing = repay["received"] - built["paid"]
    cash_from_financing = sum(net(kind) for kind in _FINANCING) - repay["paid"]
    cash_opening = prev["cash"]
    cash_closing = ledger.balance(conn, account)

    # Sales that arrived while this quarter was being closed belong to this quarter too.
    late = sum(moves.get(kind, {}).get("received", 0) for kind in _SALES) - revenue
    if late:
        raise BooksDoNotBalance(f"{name}: sales arrived while its quarter was being closed.")

    # 8. The balance sheet, each figure taken from where it is truly kept.
    borrowings = _row(
        conn, "SELECT coalesce(sum(principal_outstanding), 0)::bigint AS total FROM company_debts WHERE company_id = %s",
        (company["id"],),
    )["total"]
    loans_to_companies = _row(
        conn, "SELECT coalesce(sum(principal_outstanding), 0)::bigint AS total FROM company_debts WHERE lender_account_id = %s",
        (account,),
    )["total"]
    fixed_assets = prev["fixed_assets"] + capital_spending - depreciation
    retained_earnings = prev["retained_earnings"] + net_profit - dividends_paid
    total_assets = cash_closing + prev["customer_loans"] + loans_to_companies + fixed_assets
    total_liabilities = borrowings + payables + prev["customer_funds"]
    total_equity = prev["share_capital"] + retained_earnings
    shares_in_issue = ledger.amount_in_existence(conn, company["share_asset"])

    # Guards. If any of these fail, something moved money in a way the books cannot
    # explain, and the whole quarter is refused. (The database repeats these checks.)
    if cash_closing != cash_opening + cash_from_operations + cash_from_investing + cash_from_financing:
        raise BooksDoNotBalance(f"{name}: cash does not reconcile with the ledger for {label}.")
    if total_assets != total_liabilities + total_equity:
        raise BooksDoNotBalance(f"{name}: the balance sheet does not balance for {label}.")

    # Expanding wins customers: the pull it carries into next quarter grows with
    # what it added to its buildings and machines beyond upkeep.
    lasting_pull = ctx.lasting_pull[company["id"]]
    added = max(capital_spending - depreciation, 0)
    if added > 0 and prev["fixed_assets"] > 0:
        growth = min(added * data.EXPANSION_PULL_BPS // prev["fixed_assets"], 500)       # at most 5% a quarter
        lasting_pull = apply_bps(lasting_pull, BPS + growth)

    drivers = {
        "revenue": _revenue_causes(company, world, period, ctx.sector_fortune.get(company["sector"], 0),
                                   revenue, prev, sales_households, sales_business, sales_government),
        "notes": notes,
        "repayments_missed": repayments_missed,
    }

    result = {
        "company_id": company["id"], "period": period,
        "revenue": revenue, "interest_income": interest_income, "cost_of_sales": cost_of_sales,
        "operating_expenses": operating_expenses, "depreciation": depreciation,
        "operating_profit": operating_profit, "interest_expense": interest_expense,
        "profit_before_tax": profit_before_tax, "tax": tax, "net_profit": net_profit,
        "cash_opening": cash_opening, "cash_from_operations": cash_from_operations,
        "cash_from_investing": cash_from_investing, "cash_from_financing": cash_from_financing,
        "cash_closing": cash_closing, "capital_spending": capital_spending,
        "debt_repaid": repay["paid"], "dividends_paid": dividends_paid,
        "cash": cash_closing, "customer_loans": prev["customer_loans"],
        "loans_to_companies": loans_to_companies, "fixed_assets": fixed_assets,
        "total_assets": total_assets, "borrowings": borrowings, "payables": payables,
        "customer_funds": prev["customer_funds"], "total_liabilities": total_liabilities,
        "share_capital": prev["share_capital"], "retained_earnings": retained_earnings,
        "total_equity": total_equity, "principal_overdue": principal_overdue,
        "shares_in_issue": shares_in_issue, "base_revenue": lasting_pull,
        "base_opex": operating_expenses, "ledger_totals": ledger_totals(conn, account), "drivers": drivers,
        "staff": staff, "wages": wages, "sales_households": sales_households,
        "sales_business": sales_business, "sales_government": sales_government,
    }
    insert_result(conn, result)
    return result


def _round_people(count: int) -> str:
    """A head count the way a newspaper would give it: 1,240 becomes "1,200"."""
    if count >= 1000:
        count = round(count, -2)
    elif count >= 100:
        count = round(count, -1)
    return f"{count:,}"


def _revenue_causes(company: dict, world, period: int, sector_fortune: int, revenue: int, prev: dict,
                    to_households: int, to_business: int, to_government: int) -> list[str]:
    """The causes behind this quarter's sales, in plain words, in order."""
    sector = company["sector_name"].lower()
    name = company["name"]
    causes = []
    if revenue > 0:
        biggest = max((to_households, "households"), (to_business, "other companies"), (to_government, "the Government"))
        causes.append(f"{_percent(biggest[0] * BPS // revenue)} of its sales were to {biggest[1]}")
    season = world.seasons[company["sector"]][(period - 1) % 4]
    if season > BPS:
        causes.append(f"This is a strong season for {sector}: about {_percent(season - BPS)} above an average quarter")
    elif season < BPS:
        causes.append(f"This is a weak season for {sector}: about {_percent(BPS - season)} below an average quarter")
    if sector_fortune >= 100:
        causes.append(f"Households spent more on {sector} this quarter: {_percent(sector_fortune)} above their usual share")
    elif sector_fortune <= -100:
        causes.append(f"Households spent less on {sector} this quarter: {_percent(-sector_fortune)} below their usual share")
    own = company.get("own_fortune_bps", 0)
    if own >= 100:
        causes.append(f"{name} won customers from its rivals: its pull was {_percent(own)} above its usual")
    elif own <= -100:
        causes.append(f"{name} lost customers to its rivals: its pull was {_percent(-own)} below its usual")
    trend = company["revenue_growth_bps"]
    if trend >= 50:
        causes.append(f"It has been gaining ground on its rivals by about {_percent(trend)} a quarter")
    elif trend <= -50:
        causes.append(f"It has been losing ground to its rivals by about {_percent(-trend)} a quarter")
    return causes


def insert_result(conn: Connection, result: dict) -> None:
    columns = list(result)
    values = [Jsonb(v) if c in ("drivers", "ledger_totals") else v for c, v in result.items()]
    conn.execute(
        f"INSERT INTO company_results ({', '.join(columns)}) VALUES ({', '.join(['%s'] * len(columns))})",
        values,
    )


# ---------------------------------------------------------------------------
# The reported record.
# ---------------------------------------------------------------------------

def build_figures(conn: Connection, company: dict, result: dict) -> dict:
    """Turn a true record into the document a company files.

    Today every company files honestly, so the filed figures are a faithful copy.
    """
    debts = _rows(
        conn,
        "SELECT d.name, d.kind, a.name AS lender, d.principal_outstanding, d.annual_rate_bps,"
        "       d.maturity_period, d.repayment"
        " FROM company_debts d JOIN ledger_accounts a ON a.id = d.lender_account_id"
        " WHERE d.company_id = %s AND d.principal_outstanding > 0 ORDER BY d.start_period, d.name",
        (company["id"],),
    )
    return {
        "income_statement": {
            **{line: result[line] for line in INCOME_LINES},
            # EBITDA: profit before interest paid, tax, and the wear on buildings and
            # machines. It shows what the business itself produces.
            "ebitda": result["operating_profit"] + result["depreciation"],
        },
        "cash_flow": {line: result[line] for line in CASH_FLOW_LINES},
        "balance_sheet": {line: result[line] for line in BALANCE_SHEET_LINES},
        "notes": {
            "shares_in_issue": result["shares_in_issue"],
            "principal_overdue": result["principal_overdue"],
            # Scheduled loan repayments it failed to make this quarter.
            "repayments_missed": result["drivers"].get("repayments_missed", 0),
            "borrowings": debts,
            # Who it sold to, how many people it employs and what it paid them.
            "sales_to": {
                "households": result["sales_households"], "other_companies": result["sales_business"],
                "government": result["sales_government"],
            },
            "staff": result["staff"],
            "wages": result["wages"],
            "why_revenue": result["drivers"]["revenue"],
            "management_notes": result["drivers"]["notes"],
        },
    }


def file_report(conn: Connection, company: dict, result: dict, *, filed_by: str = "Company management") -> None:
    """File a company's report for one quarter into the reported record, with its credit rating."""
    figures = build_figures(conn, company, result)
    earlier = _rows(
        conn,
        "SELECT DISTINCT ON (period) figures FROM company_reports"
        " WHERE company_id = %s AND period BETWEEN %s AND %s AND period >= 1"
        " ORDER BY period, version DESC",
        (company["id"], result["period"] - 3, result["period"] - 1),
    )
    trailing = [r["figures"] for r in earlier]
    if result["period"] >= 1:
        trailing.append(figures)
    rating, reasons = credit.rate(figures, trailing)
    conn.execute(
        "INSERT INTO company_reports (company_id, period, version, figures, credit_rating, rating_reasons, filed_by)"
        " VALUES (%s, %s, 1, %s, %s, %s, %s)",
        (company["id"], result["period"], Jsonb(figures), rating, Jsonb(reasons), filed_by),
    )


def load_companies(conn: Connection) -> list[dict]:
    """Every company, ordered so that borrowers are handled before their lenders.

    A lender's interest income for the quarter is what its borrowers actually paid it,
    so the borrowers must go first.
    """
    return _rows(
        conn,
        "SELECT c.*, s.name AS sector_name,"
        "       EXISTS (SELECT 1 FROM company_debts d WHERE d.lender_account_id = c.account_id) AS is_lender"
        " FROM companies c JOIN sectors s ON s.code = c.sector"
        " ORDER BY is_lender, c.ticker",
    )
