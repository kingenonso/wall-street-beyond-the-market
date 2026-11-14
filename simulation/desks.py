"""What the build screens show (design document, section 18).

The Asset Manager's screen is built on what the player owns. The Accountant's screen is built
on companies' filed accounts. Nothing here is hidden knowledge: an Accountant sees the same
filings as everybody else, laid out the way the Asset Manager works with the accounts.
"""

from __future__ import annotations

from datetime import datetime

from psycopg import Connection
from psycopg.rows import dict_row

from simulation import clock, objectives
from simulation.money import BPS

GAME_YEAR_SESSIONS = 28            # four real weeks of trading days are one game year


def _rows(conn: Connection, sql: str, params=()) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def asset_desk(conn: Connection, player_id, account, now: datetime) -> dict:
    """The Asset Manager's figures: what the player owns, how it is divided, and how it has done."""
    have = objectives.wealth(conn, account, now)
    total = have["total"]
    share = lambda value: value * BPS // total if total else 0            # noqa: E731
    bond_groups: dict[str, int] = {}
    for bond in have["bond_lines"]:
        label = ("Government bills" if bond["kind"] == "bill" else "Government bonds") if bond["issuer"] == "Federal Government" \
            else "Company bonds"
        bond_groups[label] = bond_groups.get(label, 0) + bond["value"]
    allocation = [{"label": "Shares", "group": "shares", "value": have["shares"], "share_bps": share(have["shares"])}]
    allocation += [{"label": label, "group": "bonds", "value": value, "share_bps": share(value)} for label, value in bond_groups.items()]
    allocation.append({"label": "Property", "group": "property", "value": have.get("property", 0), "share_bps": share(have.get("property", 0))})
    allocation.append({"label": "Cash", "group": "cash", "value": have["cash"], "share_bps": share(have["cash"])})
    by_sector: dict[str, int] = {}
    for line in have["lines"]:
        by_sector[line["sector"]] = by_sector.get(line["sector"], 0) + line["value"]
    sectors = [{"label": name, "group": "shares", "value": value, "share_bps": value * BPS // have["shares"] if have["shares"] else 0}
               for name, value in sorted(by_sector.items(), key=lambda item: -item[1])]
    days = _rows(conn, "SELECT session_date, cash + investments AS total FROM net_worth_days WHERE account_id = %s"
                       " AND session_date < %s ORDER BY session_date DESC LIMIT %s", (account, have["day"], GAME_YEAR_SESSIONS))
    today = year = index_year = None
    if days and days[0]["total"] > 0:
        today = (total - days[0]["total"]) * BPS // days[0]["total"]
    if days and days[-1]["total"] > 0:
        year = (total - days[-1]["total"]) * BPS // days[-1]["total"]
        was = _rows(conn, "SELECT level FROM index_days WHERE session_date = %s", (days[-1]["session_date"],))
        if was and was[0]["level"]:
            index_year = (objectives.index_now(conn, now) - was[0]["level"]) * BPS // was[0]["level"]
    largest = max((line["value"] for line in have["lines"]), default=0)
    savings = _rows(conn, "SELECT value FROM retirement_accounts WHERE player_id = %s", (player_id,))
    return {
        "total": total, "cash": have["cash"], "shares": have["shares"], "bonds": have["bonds"],
        "change_today_bps": today, "change_year_bps": year, "index_change_year_bps": index_year,
        "allocation": [a for a in allocation if a["value"] > 0], "sectors": sectors,
        "largest_bps": largest * BPS // have["shares"] if have["shares"] else 0,
        "companies_held": sum(1 for line in have["lines"] if line["value"] > 0), "industries_held": len(by_sector),
        "retirement": savings[0]["value"] if savings else 0,
    }


def _ratios(figures: dict) -> dict:
    """The ratios an accountant reads first. None where a ratio has no meaning (nothing to divide by)."""
    income, sheet = figures["income_statement"], figures["balance_sheet"]
    over = lambda a, b: round(a / b, 2) if b else None                    # noqa: E731
    ebitda = income.get("ebitda", income["operating_profit"] + income["depreciation"])
    return {
        "Profit after tax ÷ sales (%)": over(income["net_profit"] * 100, income["revenue"]),
        "EBITDA ÷ sales (%)": over(ebitda * 100, income["revenue"]),
        "Debt ÷ a year's EBITDA (times)": over(sheet["borrowings"], 4 * ebitda) if ebitda > 0 else None,
        "Interest cover (times)": over(income["operating_profit"], income["interest_expense"]),
        "Return on owners' money, yearly (%)": over(income["net_profit"] * 400, sheet["total_equity"]) if sheet["total_equity"] > 0 else None,
        "Cash ÷ a quarter's costs (times)": over(sheet["cash"], income["cost_of_sales"] + income["operating_expenses"] + income["interest_expense"]),
    }


def asset_manager_accounts_desk(conn: Connection, player_id, ticker: str | None, now: datetime) -> dict | None:
    """The Accountant's workspace on one company: its filed statements quarter by quarter, the
    ratios, its tax, and the list of companies behind on what they owe."""
    job = _rows(conn, "SELECT c.ticker FROM employments e JOIN companies c ON c.id = e.company_id"
                      " WHERE e.player_id = %s AND e.ended_at IS NULL", (player_id,))
    employer = job[0]["ticker"] if job else None
    companies = _rows(conn, "SELECT c.ticker, c.name, s.name AS sector FROM companies c JOIN sectors s ON s.code = c.sector WHERE c.listed ORDER BY c.name")
    ticker = ticker or employer or (companies[0]["ticker"] if companies else None)
    company = _rows(conn, "SELECT c.id, c.ticker, c.name, s.name AS sector FROM companies c JOIN sectors s ON s.code = c.sector"
                          " WHERE c.ticker = %s AND c.listed", (ticker,))
    if not company:
        return None
    company = company[0]
    filed = _rows(conn, "SELECT * FROM (SELECT DISTINCT ON (period) period, figures, credit_rating FROM company_reports"
                        " WHERE company_id = %s ORDER BY period, version DESC) latest ORDER BY period DESC LIMIT 8", (company["id"],))
    tax_owed = _rows(conn, "SELECT coalesce(sum(amount_outstanding), 0)::bigint AS owed FROM company_payables"
                           " WHERE company_id = %s AND kind = 'company_tax'", (company["id"],))[0]["owed"]
    quarters = []
    for index, report in enumerate(filed):
        figures = report["figures"]
        notes = figures.get("notes", {})
        quarters.append({
            "period": report["period"], "period_label": clock.period_label(report["period"]), "credit_rating": report["credit_rating"],
            "income_statement": figures["income_statement"], "cash_flow": figures["cash_flow"], "balance_sheet": figures["balance_sheet"],
            "notes": list(notes.get("management_notes", [])), "ratios": _ratios(figures),
            "tax_owed": tax_owed if index == 0 else 0, "staff": notes.get("staff"),
        })
    watch = _rows(
        conn,
        "SELECT c.ticker, c.name, r.credit_rating, (r.figures->'balance_sheet'->>'payables')::bigint AS unpaid,"
        "   coalesce((r.figures->'notes'->>'principal_overdue')::bigint, 0) AS overdue, (r.figures->'balance_sheet'->>'cash')::bigint AS cash"
        " FROM (SELECT DISTINCT ON (company_id) company_id, figures, credit_rating FROM company_reports ORDER BY company_id, period DESC, version DESC) r"
        " JOIN companies c ON c.id = r.company_id"
        " WHERE (r.figures->'balance_sheet'->>'payables')::bigint > 0 OR coalesce((r.figures->'notes'->>'principal_overdue')::bigint, 0) > 0"
        "    OR r.credit_rating IN ('CCC', 'D') ORDER BY c.name")
    tax_rate = _rows(conn, "SELECT company_tax_bps FROM world_state")[0]["company_tax_bps"]
    return {"ticker": company["ticker"], "name": company["name"], "sector": company["sector"],
            "is_employer": company["ticker"] == employer, "quarters": quarters, "companies": companies, "watch": watch,
            "tax_rate_bps": tax_rate}


def accountant_desk(conn, player_id, ticker, now):
    return asset_manager_accounts_desk(conn, player_id, ticker, now)
