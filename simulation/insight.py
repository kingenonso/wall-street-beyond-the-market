"""What the figures say, in plain words (design document, sections 11 and 18).

Everything here only reads, and everything about a company comes from what it
has FILED and from prices on the exchange. Nothing is invented and nothing is
taken from the true record:

  * a company's quick facts: profit per share quarter by quarter, results against
    the same quarter a year ago, where its cash is heading, its highest and lowest
    price over the past game year, and when it next reports;
  * a written report on a quarter's results;
  * every industry: how fast it is growing and who leads it;
  * a player's own advisory summary: a reading of how their money is placed.

The advisory never names a share to buy or sell. It points at what a careful
investor would look at, and leaves the decision to the player.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from psycopg import Connection
from psycopg.rows import dict_row

from simulation import clock, exchange, marketview
from simulation import world_data as data
from simulation.money import BPS


def _rows(conn: Connection, sql: str, params=()) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


_percent = marketview._percent
_naira = marketview._naira
_big = marketview._big


def _change(now: int, before: int) -> int | None:
    """The change from one figure to another, in hundredths of a percent. Empty when there is nothing to compare with."""
    return (now - before) * BPS // abs(before) if before else None


def _filed(conn: Connection, company_id, upto: int | None = None) -> list[dict]:
    """A company's filed reports, oldest first: the latest version of each quarter's."""
    rows = _rows(
        conn,
        "SELECT DISTINCT ON (period) period, credit_rating, figures FROM company_reports"
        " WHERE company_id = %s AND period <= %s ORDER BY period, version DESC", (company_id, upto if upto is not None else 10**9))
    for row in rows:
        f = row["figures"]
        row.update(income=f["income_statement"], cash=f["cash_flow"], sheet=f["balance_sheet"], notes=f["notes"])
    return rows


def _restate(conn: Connection, company_id, reports: list[dict]) -> None:
    """Profit per share for each report, in hundredths of a kobo, counted in today's shares."""
    splits = _rows(conn, "SELECT period, ratio FROM share_splits WHERE company_id = %s", (company_id,))
    for report in reports:
        factor = 1
        for split in splits:
            if split["period"] > report["period"]:
                factor *= split["ratio"]
        shares = report["notes"]["shares_in_issue"] * factor
        report["shares"] = shares
        report["eps"] = report["income"]["net_profit"] * 100 // shares if shares else 0


def _against(reports: list[dict], report: dict) -> tuple[dict | None, str]:
    """What a quarter is compared with: the same quarter a year ago, or failing that the quarter before."""
    by_period = {r["period"]: r for r in reports}
    year_ago = by_period.get(report["period"] - 4)
    if year_ago and year_ago["period"] >= 1:
        return year_ago, "the same quarter a year ago"
    before = by_period.get(report["period"] - 1)
    if before and before["period"] >= 1:
        return before, "the quarter before"
    return None, ""


def facts(conn: Connection, ticker: str, now: datetime) -> dict | None:
    """One company's quick facts for an investor."""
    found = _rows(conn, "SELECT c.id, c.name, c.ticker, c.sector FROM companies c WHERE c.ticker = %s AND c.listed", (ticker,))
    if not found:
        return None
    company = found[0]
    reports = _filed(conn, company["id"])
    _restate(conn, company["id"], reports)
    trading = [r for r in reports if r["period"] >= 1]
    latest = reports[-1]
    compared, with_what = _against(reports, latest) if latest["period"] >= 1 else (None, "")

    # Cash: what came in or went out each quarter, and where that leaves it in three months.
    year = trading[-4:]
    flows = [r["cash"]["cash_closing"] - r["cash"]["cash_opening"] for r in year]
    cash_now = latest["sheet"]["cash"]
    average = sum(flows) // len(flows) if flows else 0
    ahead = cash_now + average
    if not flows:
        outlook = "It has not filed a trading quarter yet, so there is nothing to judge its cash by."
    elif average >= 0:
        outlook = (f"Cash is coming in: about {_big(average)} a quarter over the past {'year' if len(flows) == 4 else 'quarters filed'}. "
                   f"At that pace it would hold about {_big(ahead)} in three months.")
    elif ahead > 0:
        quarters = cash_now // -average
        outlook = (f"Cash is going out: about {_big(-average)} a quarter. At that pace it would hold about {_big(ahead)} in "
                   f"three months, and its cash would last about {quarters} more quarter{'s' if quarters != 1 else ''}.")
    else:
        outlook = (f"Cash is going out: about {_big(-average)} a quarter, more than the {_big(cash_now)} it holds. Unless "
                   "that changes it will need to borrow, raise money from its owners, or leave bills unpaid.")

    # The highest and lowest price over the past game year (four real weeks), in today's shares.
    since = exchange.session_of(now)[0] - timedelta(days=data.GAME_YEAR_REAL_DAYS)
    days = [d for d in (marketview.history(conn, ticker) or []) if d["session_date"] >= since]
    world = _rows(conn, "SELECT world_start, weeks_ahead FROM world_state")
    next_results = None
    if world:
        start = clock.effective_start(world[0]["world_start"], world[0]["weeks_ahead"])
        if now >= start:
            next_results = {"at": clock.next_quarter_end(now, start),
                            "label": clock.period_label(clock.periods_completed(now, start) + 1)}

    return {
        "ticker": ticker, "name": company["name"], "period": latest["period"],
        "profit_per_share": [
            {"period": r["period"], "label": clock.period_label(r["period"]), "eps": r["eps"],
             "net_profit": r["income"]["net_profit"]} for r in trading[-12:]],
        "yearly_profit_per_share": sum(r["eps"] for r in year) * 4 // len(year) if year else 0,
        "compared_with": with_what,
        "sales_change_bps": _change(latest["income"]["revenue"], compared["income"]["revenue"]) if compared else None,
        "profit_change_bps": _change(latest["income"]["net_profit"], compared["income"]["net_profit"]) if compared else None,
        "profit_before": compared["income"]["net_profit"] if compared else None,
        "sales_before": compared["income"]["revenue"] if compared else None,
        "cash": cash_now, "cash_change_quarter": flows[-1] if flows else 0, "cash_change_year": sum(flows),
        "cash_in_three_months": ahead, "cash_outlook": outlook,
        "year_high": max((d["high"] for d in days), default=None), "year_low": min((d["low"] for d in days), default=None),
        "next_results": next_results,
        "industry": _place_in_industry(conn, company),
    }


def _yearly_sales(conn: Connection) -> list[dict]:
    """Every company's sales over the past four filed quarters and over the four before those."""
    return _rows(
        conn,
        "WITH latest AS (SELECT max(period) AS p FROM company_reports),"
        " filed AS (SELECT DISTINCT ON (company_id, period) company_id, period,"
        "     (figures->'income_statement'->>'revenue')::bigint AS revenue FROM company_reports, latest"
        "     WHERE period >= 1 AND period > latest.p - 8 ORDER BY company_id, period, version DESC)"
        " SELECT c.id, c.ticker, c.name, c.sector, s.name AS sector_name, s.sort_order,"
        "   coalesce(sum(f.revenue) FILTER (WHERE f.period > latest.p - 4), 0)::bigint AS sales,"
        "   coalesce(sum(f.revenue) FILTER (WHERE f.period <= latest.p - 4), 0)::bigint AS sales_before,"
        "   count(*) FILTER (WHERE f.period > latest.p - 4) AS quarters,"
        "   count(*) FILTER (WHERE f.period <= latest.p - 4) AS quarters_before"
        " FROM companies c JOIN sectors s ON s.code = c.sector CROSS JOIN latest"
        " LEFT JOIN filed f ON f.company_id = c.id WHERE c.listed GROUP BY c.id, c.ticker, c.name, c.sector, s.name, s.sort_order")


def _place_in_industry(conn: Connection, company: dict) -> dict:
    rivals = sorted((r for r in _yearly_sales(conn) if r["sector"] == company["sector"]), key=lambda r: (-r["sales"], r["ticker"]))
    total = sum(r["sales"] for r in rivals)
    place = next(i for i, r in enumerate(rivals, 1) if r["ticker"] == company["ticker"])
    mine = rivals[place - 1]
    return {"sector": mine["sector_name"], "rank": place, "of": len(rivals),
            "share_bps": mine["sales"] * BPS // total if total else 0}


def industries(conn: Connection, now: datetime) -> list[dict]:
    """Every industry: its size on the exchange, today's move, how fast its sales are growing,
    and its companies ranked by their share of the industry's sales."""
    day, _ = exchange.session_of(now)
    prices = {s["ticker"]: s for s in marketview._shares(conn, day)}
    sectors: dict = {}
    for row in _yearly_sales(conn):
        share = prices.get(row["ticker"])
        sector = sectors.setdefault(row["sector"], {"code": row["sector"], "name": row["sector_name"], "order": row["sort_order"],
                                                    "companies": []})
        sector["companies"].append({
            "ticker": row["ticker"], "name": row["name"], "sales": row["sales"], "sales_before": row["sales_before"],
            "full_years": row["quarters"] == 4 and row["quarters_before"] == 4,
            "price": share["price"] if share else None, "change_bps": share["change_bps"] if share else 0,
            "market_value": share["market_value"] if share else 0,
            "reference_value": share["reference"] * share["shares"] if share else 0,
        })
    out = []
    for sector in sorted(sectors.values(), key=lambda s: s["order"]):
        firms = sorted(sector["companies"], key=lambda c: (-c["sales"], c["ticker"]))
        sales = sum(c["sales"] for c in firms)
        before = sum(c["sales_before"] for c in firms)
        value, reference = sum(c["market_value"] for c in firms), sum(c["reference_value"] for c in firms)
        for place, firm in enumerate(firms, 1):
            firm["rank"] = place
            firm["share_bps"] = firm["sales"] * BPS // sales if sales else 0
            firm["sales_growth_bps"] = _change(firm["sales"], firm["sales_before"]) if firm["full_years"] else None
        out.append({
            "code": sector["code"], "name": sector["name"], "market_value": value,
            "change_bps": (value - reference) * BPS // reference if reference else 0, "sales": sales,
            "sales_growth_bps": _change(sales, before) if all(c["full_years"] for c in firms) else None,
            "companies": firms,
        })
    return out


# ---------------------------------------------------------------------------
# A written report on one quarter's results
# ---------------------------------------------------------------------------

def results_report(conn: Connection, ticker: str, period: int | None = None) -> dict | None:
    """One quarter's results in words, built only from what the company filed."""
    found = _rows(conn, "SELECT id, name, ticker FROM companies WHERE ticker = %s AND listed", (ticker,))
    if not found:
        return None
    company = found[0]
    reports = _filed(conn, company["id"])
    _restate(conn, company["id"], reports)
    report = reports[-1] if period is None else next((r for r in reports if r["period"] == period), None)
    if report is None:
        return None
    name, label = company["name"], clock.period_label(report["period"])
    available = [{"period": r["period"], "label": clock.period_label(r["period"])} for r in reports if r["period"] >= 1][-12:]
    if report["period"] < 1:
        sheet = report["sheet"]
        return {"ticker": ticker, "name": name, "period": 0, "label": label, "title": f"{name}: opening position",
                "available": available, "paragraphs": [
                    f"{name} has not yet traded a full quarter. It opened with {_big(sheet['total_assets'])} of assets, "
                    f"{_big(sheet['total_liabilities'])} of debts and bills, and {_big(sheet['total_equity'])} of owners' funds."]}

    income, cash, sheet, notes = report["income"], report["cash"], report["sheet"], report["notes"]
    compared, with_what = _against(reports, report)
    profit, sales = income["net_profit"], income["revenue"]

    def moved(now_value: int, key: str) -> str:
        if not compared:
            return ""
        before = compared["income"][key]
        change = _change(now_value, before)
        if change is None or (before < 0) != (now_value < 0):
            return f", against {_big(before) if before >= 0 else 'a loss of ' + _big(before)} in {with_what}"
        if now_value < 0:                 # a loss both times: say whether it is smaller or larger
            return f", a {'smaller' if change >= 0 else 'larger'} loss than the {_big(before)} lost in {with_what}"
        return f", {'up' if change >= 0 else 'down'} {_percent(change)} on {with_what} ({_big(before)})"

    paragraphs = []
    if profit >= 0:
        paragraphs.append(f"{name} made a profit after tax of {_big(profit)} in {label}{moved(profit, 'net_profit')}.")
    else:
        paragraphs.append(f"{name} made a loss after tax of {_big(profit)} in {label}{moved(profit, 'net_profit')}.")
    to = notes.get("sales_to", {})
    split = ""
    if sales > 0 and to:
        parts = [(to.get("households", 0), "households"), (to.get("other_companies", 0), "other companies"),
                 (to.get("government", 0), "the Government")]
        split = " " + ", ".join(f"{_percent(amount * BPS // sales)} to {who}" for amount, who in parts if amount > 0) + "."
    paragraphs.append(f"Sales were {_big(sales)}{moved(sales, 'revenue')}.{split}")
    why = [w for w in notes.get("why_revenue", []) if "of its sales were to" not in w]
    if why:
        paragraphs.append("Behind the sales figure: " + ". ".join(why) + ".")
    eps = report["eps"]
    per_share = f"That profit is {eps / 100:,.2f} kobo for each of its {report['shares']:,} shares" if abs(eps) < 10_000 else \
        f"That profit is {_naira(eps // 100)} for each of its {report['shares']:,} shares"
    if profit < 0:
        per_share = per_share.replace("That profit is", "That loss is").replace("-", "")
    if compared:
        before_eps = compared["eps"]
        per_share += (f", against {before_eps / 100:,.2f} kobo" if abs(before_eps) < 10_000 else f", against {_naira(before_eps // 100)}") \
            + f" in {with_what}"
    paragraphs.append(per_share + ".")
    if sales > 0:
        of_100 = lambda amount: f"₦{amount * 100 / sales:.0f}"            # noqa: E731
        paragraphs.append(
            f"Of every ₦100 of sales, {of_100(income['cost_of_sales'])} went on making and delivering what it sells, "
            f"{of_100(income['operating_expenses'])} on running the business, {of_100(income['depreciation'])} on wear of "
            f"buildings and machines, {of_100(income['interest_expense'])} on interest and {of_100(income['tax'])} on tax.")
    change = cash["cash_closing"] - cash["cash_opening"]
    paragraphs.append(
        f"Its cash {'rose' if change >= 0 else 'fell'} by {_big(change)} to {_big(cash['cash_closing'])}. Trading brought in "
        f"{_big(cash['cash_from_operations'])}" if cash["cash_from_operations"] >= 0 else
        f"Its cash {'rose' if change >= 0 else 'fell'} by {_big(change)} to {_big(cash['cash_closing'])}. Trading took out "
        f"{_big(cash['cash_from_operations'])}")
    paragraphs[-1] += (f"; it spent {_big(cash['capital_spending'])} on buildings and machines and paid its owners "
                       f"{_big(cash['dividends_paid'])} in dividends"
                       + (f" ({cash['dividends_paid'] / report['shares']:,.1f} kobo a share)" if cash["dividends_paid"] and report["shares"] else "")
                       + ".")
    owed = sheet["borrowings"]
    debt = f"It owes lenders {_big(owed)}" if owed else "It has no borrowings"
    if notes.get("principal_overdue", 0) > 0:
        debt += f", of which {_big(notes['principal_overdue'])} is past its repayment date and unpaid"
    if sheet["payables"] > 0:
        debt += f", and has {_big(sheet['payables'])} of unpaid bills"
    paragraphs.append(f"{debt}. Owners' funds stand at {_big(sheet['total_equity'])}"
                      f"{'' if sheet['total_equity'] >= 0 else ' below zero'}. Its credit rating is {report['credit_rating']}.")
    if notes.get("staff"):
        paragraphs.append(f"It employs about {notes['staff']:,} people.")
    if notes.get("management_notes"):
        paragraphs.append("Management's notes: " + " ".join(notes["management_notes"]))
    return {"ticker": ticker, "name": name, "period": report["period"], "label": label,
            "title": f"{name}: results for {label}", "available": available, "paragraphs": paragraphs}


# ---------------------------------------------------------------------------
# A player's own advisory summary
# ---------------------------------------------------------------------------

def personal_advice(conn: Connection, portfolio: dict, *, bill_yield_bps: int | None = None) -> list[str]:
    """A reading of how a player's money is placed. Observations with their reasons; never a tip."""
    total = portfolio["total"]
    if total <= 0:
        return ["You have nothing to invest yet."]
    lines = []
    cash = portfolio["cash"]
    inflation = _rows(conn, "SELECT inflation_bps FROM economy_results ORDER BY period DESC LIMIT 1")
    rising = inflation[0]["inflation_bps"] if inflation else data.INFLATION_TARGET_BPS
    idle = cash * BPS // total
    investments = portfolio["shares_value"] + portfolio.get("bonds_value", 0)
    if investments == 0 and not portfolio["held_for_orders"]:
        lines.append("All your money is in cash. Cash is safe from a falling market, but it earns nothing and buys less each "
                     f"year as prices rise ({_percent(rising)} a year at present).")
    elif idle >= 5000:
        lines.append(f"{_naira(cash)} of what you are worth, {_percent(idle)}, is idle cash. It earns nothing, and prices are "
                     f"rising {_percent(rising)} a year.")
    if bill_yield_bps and idle >= 2500:
        lines.append(f"Government bills pay about {_percent(bill_yield_bps)} a year on cash you do not need for a few weeks, "
                     "with the Government's promise to repay behind them.")
    holdings = portfolio["holdings"]
    shares_value = portfolio["shares_value"]
    if holdings and shares_value > 0:
        largest = max(holdings, key=lambda h: h["value"])
        part = largest["value"] * BPS // total
        if part >= 4000:
            lines.append(f"{_percent(part)} of what you are worth is in one company, {largest['name']}. One bad quarter there "
                         "would hit all of it at once.")
        sectors = {r["ticker"]: r["sector"] for r in _rows(conn, "SELECT ticker, sector FROM companies")}
        spread = {sectors[h["ticker"]] for h in holdings if h["value"] > 0}
        if len(spread) <= 2 and len(holdings) >= 1:
            lines.append(f"Your shares are in {len(spread)} industr{'y' if len(spread) == 1 else 'ies'}. A strike, a flood or a "
                         "weak season hits one industry at a time, so spreading across several steadies the whole.")
        for holding in holdings:
            if holding["cost"] > 0 and holding["gain"] * BPS // holding["cost"] <= -1500:
                lines.append(f"{holding['name']} is worth {_percent(holding['gain'] * BPS // holding['cost'])} less than you paid. "
                             "Its company page shows what changed; \"Why?\" on its trading panel shows what moved the price.")
    if portfolio["held_for_orders"] > 0:
        lines.append(f"{_naira(portfolio['held_for_orders'])} is held by the exchange for orders of yours still waiting.")
    if not lines:
        lines.append("Your money is spread across cash and several investments, with no single holding carrying most of the weight.")
    return lines
