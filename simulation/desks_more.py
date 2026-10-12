"""What the screens of the Investment Banker, the Risk Manager and the Legal Counsel show (design
document, section 18), and the figures behind the CEO's screen.

Everything here is worked out from what is public (filed accounts, market prices, notices) or
from what the player may already see (their own holdings; their own empire's, if they hold a
seat). Nothing hidden is read: not the true record of a company, not another empire's books.
"""

from __future__ import annotations

from datetime import datetime
from statistics import median

from psycopg import Connection
from psycopg.rows import dict_row

from simulation import careers, clock, corporate, empires, exchange, marketview, objectives
from simulation.money import BPS

STRONG = ("AAA", "AA", "A")
MIDDLE = ("BBB", "BB")


def _rows(conn: Connection, sql: str, params=()) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def _latest(conn: Connection) -> dict:
    """Every company's latest filed accounts, by company."""
    return {r["company_id"]: r for r in _rows(
        conn, "SELECT DISTINCT ON (r.company_id) r.company_id, r.period, r.figures, r.credit_rating FROM company_reports r"
              " ORDER BY r.company_id, r.period DESC, r.version DESC")}


def _risk_level(rating: str | None) -> str:
    return "low" if rating in STRONG else "medium" if rating in MIDDLE else "high"


# ---------------------------------------------------------------------------
# Investment Banker
# ---------------------------------------------------------------------------

def _multiples(share: dict, figures: dict) -> dict:
    """The three figures a banker compares companies by. None where there is nothing to divide by."""
    income, sheet = figures["income_statement"], figures["balance_sheet"]
    value = share["market_value"]
    ebitda = income.get("ebitda", income["operating_profit"] + income["depreciation"])
    over = lambda a, b: round(a / b, 2) if b > 0 else None                # noqa: E731
    return {
        "earnings": over(value, 4 * income["net_profit"]),                               # price ÷ a year's profit
        "book": over(value, sheet["total_equity"]),                                      # price ÷ owners' money
        "ebitda": over(value + sheet["borrowings"] - sheet["cash"], 4 * ebitda),         # whole business ÷ a year's EBITDA
    }


def banker_desk(conn: Connection, player_id, account, ticker: str | None, now: datetime) -> dict | None:
    """The Investment Banker's workspace: the deals open in the market, and one company set
    against the companies like it."""
    state = careers.world_now(conn, now)
    shares = {s["id"]: s for s in marketview._shares(conn, exchange.session_of(now)[0])}
    filed = _latest(conn)
    companies = _rows(conn, "SELECT c.id, c.ticker, c.name, c.sector AS sector_code, s.name AS sector, c.headquarters FROM companies c"
                            " JOIN sectors s ON s.code = c.sector WHERE c.listed ORDER BY c.name")
    job = _rows(conn, "SELECT c.ticker FROM employments e JOIN companies c ON c.id = e.company_id WHERE e.player_id = %s AND e.ended_at IS NULL",
                (player_id,))
    listed = [c for c in companies if c["id"] in shares and c["id"] in filed]
    ticker = ticker or (listed[0]["ticker"] if listed else None)
    company = next((c for c in listed if c["ticker"] == ticker), None)
    if company is None:
        return None
    share, report = shares[company["id"]], filed[company["id"]]
    figures = report["figures"]
    mine = _multiples(share, figures)
    peers = []
    for other in listed:
        if other["sector_code"] != company["sector_code"]:
            continue
        other_share, other_report = shares[other["id"]], filed[other["id"]]
        peers.append({"ticker": other["ticker"], "name": other["name"], "rating": other_report["credit_rating"],
                      "price": other_share["price"], "market_value": other_share["market_value"],
                      "multiples": _multiples(other_share, other_report["figures"]), "this": other["id"] == company["id"]})
    others = [p for p in peers if not p["this"]]
    middle = {key: (median(vals) if (vals := [p["multiples"][key] for p in others if p["multiples"][key] is not None]) else None)
              for key in ("earnings", "book", "ebitda")}
    income, sheet = figures["income_statement"], figures["balance_sheet"]
    ebitda = income.get("ebitda", income["operating_profit"] + income["depreciation"])
    count = share["shares"]
    implied = {
        "earnings": int(middle["earnings"] * 4 * income["net_profit"] / count) if middle["earnings"] and income["net_profit"] > 0 else None,
        "book": int(middle["book"] * sheet["total_equity"] / count) if middle["book"] and sheet["total_equity"] > 0 else None,
        "ebitda": int((middle["ebitda"] * 4 * ebitda - sheet["borrowings"] + sheet["cash"]) / count) if middle["ebitda"] and ebitda > 0 else None,
    }
    implied = {k: (v if v is None or v > 0 else None) for k, v in implied.items()}
    notes = figures.get("notes", {})
    tax_owed = _rows(conn, "SELECT coalesce(sum(amount_outstanding), 0)::bigint AS owed FROM company_payables WHERE company_id = %s"
                           " AND kind = 'company_tax'", (company["id"],))[0]["owed"]
    control = corporate.control(conn, company["id"])
    bid = corporate.bid_for(conn, company["id"])
    cover = income["operating_profit"] / income["interest_expense"] if income["interest_expense"] else None
    diligence = [
        {"label": "Accounts filed for the last quarter", "ok": report["period"] >= state["period"] - 1,
         "words": f"Latest accounts: {clock.period_label(report['period'])}."},
        {"label": "Credit rating of BBB or better", "ok": report["credit_rating"] in STRONG + ("BBB",),
         "words": f"Rated {report['credit_rating']}."},
        {"label": "No debt past its date", "ok": not notes.get("principal_overdue"),
         "words": "Nothing overdue." if not notes.get("principal_overdue") else "It has debt it has not repaid on time."},
        {"label": "Suppliers and staff paid up to date", "ok": sheet.get("payables", 0) == 0,
         "words": "No unpaid bills." if sheet.get("payables", 0) == 0 else "It has bills it has not paid."},
        {"label": "No tax owed", "ok": tax_owed == 0, "words": "Up to date with the tax office." if tax_owed == 0 else "It owes the tax office."},
        {"label": "Profit covers interest at least twice", "ok": cover is None or cover >= 2,
         "words": "It has no interest to pay." if cover is None else f"Operating profit is {cover:.1f} times the interest."},
        {"label": "Who controls it is known", "ok": True, "words": control["summary"]},
        {"label": "No other offer already open", "ok": bid is None,
         "words": "No takeover offer is open." if bid is None else "A takeover offer is already open for it."},
    ]
    board = corporate.board(conn, account, state["period"])
    pipeline = []
    for bid_row in board["takeovers"]:
        pipeline.append({"kind": "Takeover", "stage": "Offer open" if bid_row["status"] == "open" else ("Completed" if bid_row["status"] == "won" else "Failed"),
                         "open": bid_row["status"] == "open", "ticker": bid_row["ticker"],
                         "title": f"{bid_row['bidder']} for {bid_row['target']}", "price": bid_row["price"],
                         "deadline": f"closes with {clock.period_label(bid_row['closes_period'])}",
                         "words": ("A hostile offer: the board rejected it. " if bid_row["hostile"] else "Recommended by the board. ")
                                  + f"{bid_row['premium_bps'] / 100:.0f}% above the price before it."})
    for offer in board["offers"]:
        kind = {"ipo": "First sale of shares", "public": "Sale of new shares", "rights": "Rights issue"}[offer["kind"]]
        pipeline.append({"kind": kind, "stage": "Open" if offer["status"] == "open" else ("Completed" if offer["status"] == "done" else "Withdrawn"),
                         "open": offer["status"] == "open", "ticker": offer["ticker"], "title": f"{offer['name']}: {offer['shares']:,} new shares",
                         "price": offer["price"], "deadline": f"closes with {clock.period_label(offer['closes_period'])}", "words": offer["reason"]})
    for vote in board["votes"]:
        if vote["status"] == "open":
            pipeline.append({"kind": "Shareholder vote", "stage": "Voting", "open": True, "ticker": vote["ticker"], "title": f"{vote['name']}: {vote['subject'].replace('_', ' ')}",
                             "price": None, "deadline": f"closes with {clock.period_label(vote['closes_period'])}", "words": vote["question"]})
    pipeline.sort(key=lambda d: not d["open"])
    return {
        "ticker": company["ticker"], "name": company["name"], "sector": company["sector"], "headquarters": company["headquarters"],
        "is_employer": bool(job and job[0]["ticker"] == company["ticker"]),
        "companies": [{"ticker": c["ticker"], "name": c["name"], "sector": c["sector"]} for c in listed],
        "price": share["price"], "change_bps": share["change_bps"], "market_value": share["market_value"], "shares_in_issue": count,
        "rating": report["credit_rating"], "period_label": clock.period_label(report["period"]),
        "revenue": income["revenue"], "net_profit": income["net_profit"], "ebitda": ebitda, "borrowings": sheet["borrowings"],
        "cash": sheet["cash"], "equity": sheet["total_equity"],
        "multiples": mine, "peer_median": middle, "peers": sorted(peers, key=lambda p: -p["market_value"]), "implied": implied,
        "diligence": diligence, "control": control["summary"], "pipeline": pipeline[:12],
    }


# ---------------------------------------------------------------------------
# Risk Manager
# ---------------------------------------------------------------------------

def risk_desk(conn: Connection, player_id, account, book: str, now: datetime) -> dict:
    """The Risk Manager's figures on one book: the empire's, if the player holds a seat in one,
    or their own."""
    seat = empires.seat_of(conn, player_id)
    in_empire = seat is not None and seat["empire_status"] == "active"
    use_empire = in_empire and book != "own"
    have = objectives.wealth(conn, seat["account_id"] if use_empire else account, now)
    total = have["total"]
    part = lambda value: value * BPS // total if total else 0             # noqa: E731
    facts = {c["ticker"]: c for c in _rows(conn, "SELECT c.ticker, c.name, c.headquarters, s.name AS sector FROM companies c"
                                                 " JOIN sectors s ON s.code = c.sector")}
    ratings = {s["ticker"]: s["rating"] for s in marketview._shares(conn, have["day"])}
    exposures, by_sector, by_city = [], {}, {}
    for line in have["lines"]:
        fact = facts[line["ticker"]]
        by_sector[fact["sector"]] = by_sector.get(fact["sector"], 0) + line["value"]
        by_city[fact["headquarters"]] = by_city.get(fact["headquarters"], 0) + line["value"]
        exposures.append({"name": fact["name"], "what": f"{line['ticker']} shares", "value": line["value"], "share_bps": part(line["value"]),
                          "rating": ratings.get(line["ticker"]), "level": _risk_level(ratings.get(line["ticker"]))})
    government = company_bonds = 0
    rate_loss = 0
    for bond in have["bond_lines"]:
        state_bond = bond["issuer"] == "Federal Government"
        if state_bond:
            government += bond["value"]
        else:
            company_bonds += bond["value"]
        years = max(bond.get("quarters_left", 1), 1) / 4
        # A rise of two points in interest rates takes about two per cent off a bond for each year it has left to run.
        rate_loss += min(bond["value"] * 2 * 80 // 100 * round(years * 100) // 10_000, bond["value"] // 2)
        exposures.append({"name": bond["name"], "what": "bill" if bond["kind"] == "bill" else "bond", "value": bond["value"],
                          "share_bps": part(bond["value"]), "rating": None if state_bond else bond.get("rating"),
                          "level": "low" if state_bond else _risk_level(bond.get("rating"))})
    exposures.sort(key=lambda e: -e["value"])
    # How the BSX 50 has moved, day by day: the measure of what a normal and a bad day look like.
    levels = [r["level"] for r in _rows(conn, "SELECT level FROM index_days ORDER BY session_date DESC LIMIT 120")][::-1]
    moves = sorted((b - a) * BPS // a for a, b in zip(levels, levels[1:]))
    var_bps = shortfall_bps = worst_bps = None
    if len(moves) >= 10:
        tail = moves[:max(len(moves) // 20, 1)]
        var_bps = max(-tail[-1], 0)
        shortfall_bps = max(-sum(tail) // len(tail), 0)
        worst_bps = max(-moves[0], 0)
    at_risk = lambda bps: None if bps is None else have["shares"] * bps // BPS       # noqa: E731
    largest = max(have["lines"], key=lambda line: line["value"], default=None)
    scenarios = [
        {"name": "Shares fall by a fifth", "loss": have["shares"] * 20 // 100,
         "words": "A market-wide fall of 20%, about what a bad year brings. Bonds and cash are untouched."},
        {"name": "The Central Bank raises its rate by two points", "loss": rate_loss,
         "words": "Bonds already held are worth less when new ones pay more. The longer a bond has to run, the more it loses."},
        {"name": "The largest holding fails", "loss": largest["value"] * 80 // 100 if largest else 0,
         "words": (f"{facts[largest['ticker']]['name']} goes into default and its shares lose four fifths of their value."
                   if largest else "No shares are held.")},
        {"name": "The worst day on record, again", "loss": at_risk(worst_bps) or 0,
         "words": "The largest one-day fall the BSX 50 has had, applied to the shares held."
                  if worst_bps is not None else "Needs ten Closing Bells of history."},
    ]
    alerts = []
    if largest and part(largest["value"]) > 3000:
        alerts.append(f"{largest['ticker']} is {part(largest['value']) / 100:.0f}% of the book: one company's trouble would be felt at once.")
    if by_sector and have["shares"] and max(by_sector.values()) * 2 > have["shares"] and len(by_sector) > 1:
        top = max(by_sector, key=by_sector.get)
        alerts.append(f"More than half of the shares are in one industry: {top}.")
    if total and part(have["cash"]) < 500:
        alerts.append("Less than 5% of the book is cash: little to meet a sudden bill without selling.")
    for exposure in exposures:
        if exposure["rating"] in ("CCC", "D"):
            alerts.append(f"{exposure['name']} is rated {exposure['rating']}: lenders doubt it will pay.")
    staff_pay = None
    if use_empire:
        staff = _rows(conn, "SELECT count(*) AS n FROM empire_seats WHERE empire_id = %s AND player_id IS NULL AND staffed", (seat["empire_id"],))[0]["n"]
        staff_pay = staff * careers.salary_per_quarter(40, careers.world_now(conn, now)["wage_index_bps"])
    return {
        "book": "empire" if use_empire else "own", "book_name": seat["empire_name"] if use_empire else "Your own holdings",
        "in_empire": in_empire, "total": total, "cash": have["cash"], "shares_value": have["shares"], "bonds_value": have["bonds"],
        "at_risk": have["shares"] + company_bonds,
        "var_bps": var_bps, "var": at_risk(var_bps), "shortfall_bps": shortfall_bps, "shortfall": at_risk(shortfall_bps),
        "worst_bps": worst_bps, "worst": at_risk(worst_bps), "days_of_history": len(moves),
        "categories": [c for c in (
            {"label": "Shares", "group": "shares", "value": have["shares"], "share_bps": part(have["shares"])},
            {"label": "Company bonds", "group": "bonds", "value": company_bonds, "share_bps": part(company_bonds)},
            {"label": "Government bonds and bills", "group": "bonds", "value": government, "share_bps": part(government)},
            {"label": "Cash", "group": "cash", "value": have["cash"], "share_bps": part(have["cash"])}) if c["value"] > 0],
        "sectors": [{"label": k, "value": v, "share_bps": v * BPS // have["shares"]} for k, v in sorted(by_sector.items(), key=lambda i: -i[1])],
        "cities": [{"label": k, "value": v, "share_bps": v * BPS // have["shares"]} for k, v in sorted(by_city.items(), key=lambda i: -i[1])],
        "exposures": exposures[:10], "scenarios": scenarios, "alerts": alerts,
        "cash_share_bps": part(have["cash"]), "staff_pay": staff_pay,
        "quarters_of_staff_pay": round(have["cash"] / staff_pay, 1) if staff_pay else None,
    }


# ---------------------------------------------------------------------------
# Legal Counsel
# ---------------------------------------------------------------------------

def lawyer_desk(conn: Connection, player_id, ticker: str | None, now: datetime) -> dict | None:
    """The Legal Counsel's workspace on one company: who controls it, who would be paid first if it
    failed, and the list of companies the rules are closing in on."""
    filed = _latest(conn)
    companies = _rows(conn, "SELECT c.id, c.ticker, c.name, c.share_asset, s.name AS sector, c.headquarters FROM companies c"
                            " JOIN sectors s ON s.code = c.sector WHERE c.listed ORDER BY c.name")
    ticker = ticker or (companies[0]["ticker"] if companies else None)
    company = next((c for c in companies if c["ticker"] == ticker and c["id"] in filed), None)
    if company is None:
        return None
    report = filed[company["id"]]
    sheet, notes = report["figures"]["balance_sheet"], report["figures"].get("notes", {})
    owed = {r["kind"]: r["owed"] for r in _rows(
        conn, "SELECT kind, sum(amount_outstanding)::bigint AS owed FROM company_payables WHERE company_id = %s AND amount_outstanding > 0"
              " GROUP BY kind", (company["id"],))}
    # A company's bonds are public: they are listed on the bond desk.
    bonds_out = min(_rows(conn, "SELECT coalesce(sum(principal_outstanding), 0)::bigint AS owed FROM company_debts WHERE company_id = %s"
                                " AND kind = 'bond'", (company["id"],))[0]["owed"], sheet["borrowings"])
    staff = owed.get("salary", 0) + owed.get("wages", 0)
    tax = owed.get("company_tax", 0)
    suppliers = max(sheet.get("payables", 0) - staff - tax, 0)
    loans = max(sheet["borrowings"] - bonds_out, 0)
    ranking = [
        {"rank": 1, "who": "Staff, for pay owed", "amount": staff, "why": "Wages come first."},
        {"rank": 2, "who": "The tax office", "amount": tax, "why": "Tax owed ranks ahead of ordinary lenders."},
        {"rank": 3, "who": "Banks, for their loans", "amount": loans, "why": "A bank loan is secured on what the company owns."},
        {"rank": 4, "who": "Holders of its bonds", "amount": bonds_out, "why": "Bondholders rank after secured lenders."},
        {"rank": 5, "who": "Suppliers, for unpaid bills", "amount": suppliers, "why": "Ordinary creditors share what is left."},
        {"rank": 6, "who": "Shareholders", "amount": max(sheet["total_equity"], 0), "why": "Owners are paid last, and only if anything remains."},
    ]
    bid = corporate.bid_for(conn, company["id"])
    watch = []
    for other in companies:
        latest = filed.get(other["id"])
        if latest is None:
            continue
        other_notes = latest["figures"].get("notes", {})
        reasons = []
        if latest["credit_rating"] == "D":
            reasons.append("in default")
        if other_notes.get("principal_overdue"):
            reasons.append("debt past its date")
        if corporate.bid_for(conn, other["id"]):
            reasons.append("takeover offer open")
        if reasons:
            watch.append({"ticker": other["ticker"], "name": other["name"], "rating": latest["credit_rating"], "reasons": reasons})
    exposed = _rows(conn, "SELECT p.kind, p.legal, a.name AS one, b.name AS other FROM empire_pacts p JOIN empires a ON a.id = p.from_empire"
                          " JOIN empires b ON b.id = p.to_empire WHERE p.exposed_at IS NOT NULL ORDER BY p.exposed_at DESC LIMIT 10")
    from simulation import world_data as data
    record = _rows(conn, "SELECT words, at FROM legal_records WHERE player_id = %s ORDER BY id DESC LIMIT 5", (player_id,))
    return {
        "ticker": company["ticker"], "name": company["name"], "sector": company["sector"], "headquarters": company["headquarters"],
        "companies": [{"ticker": c["ticker"], "name": c["name"], "sector": c["sector"]} for c in companies if c["id"] in filed],
        "rating": report["credit_rating"], "period_label": clock.period_label(report["period"]),
        "control": corporate.control(conn, company["id"])["summary"],
        "holders": marketview.shareholders(conn, company["id"], company["share_asset"]),
        "ranking": ranking, "total_owed": staff + tax + loans + bonds_out + suppliers,
        "overdue": bool(notes.get("principal_overdue")),
        "bid": bid and {"price": bid["price"], "hostile": bid["hostile"], "closes_label": clock.period_label(bid["closes_period"])},
        "watch": watch,
        "exposed_pacts": [{"kind": data.PACT_KINDS[p["kind"]][0], "legal": p["legal"], "one": p["one"], "other": p["other"]} for p in exposed],
        "your_record": record,
    }


# ---------------------------------------------------------------------------
# The head of an empire
# ---------------------------------------------------------------------------

def head_desk(conn: Connection, player_id, now: datetime) -> dict | None:
    """The figures behind the CEO's screen, for whoever heads an empire: what it owns by type and
    by city, its worth over time, and what is waiting for the head's decision."""
    seat = empires.seat_of(conn, player_id)
    if seat is None:
        return None
    empire = empires._empire(conn, seat["empire_id"])
    have = empires.worth(conn, empire, now)
    facts = {c["ticker"]: c for c in _rows(conn, "SELECT c.ticker, c.name, c.headquarters, s.name AS sector FROM companies c"
                                                 " JOIN sectors s ON s.code = c.sector")}
    by_city: dict = {}
    for line in have["lines"]:
        city = facts[line["ticker"]]["headquarters"]
        by_city[city] = by_city.get(city, 0) + line["value"]
    government = sum(b["value"] for b in have["bond_lines"] if b["issuer"] == "Federal Government")
    total = have["total"]
    part = lambda value: value * BPS // total if total else 0             # noqa: E731
    history = _rows(conn, "SELECT period, worth FROM empire_worth WHERE empire_id = %s ORDER BY period DESC LIMIT 12", (empire["id"],))[::-1]
    seats = _rows(conn, "SELECT count(*) FILTER (WHERE player_id IS NOT NULL) AS players, count(*) FILTER (WHERE player_id IS NULL AND staffed) AS staff"
                        " FROM empire_seats WHERE empire_id = %s", (empire["id"],))[0]
    return {
        "worth": total, "liquid": have["cash"] + government, "companies": len(have["lines"]), "players": seats["players"], "staff": seats["staff"],
        "history": [{"label": clock.period_label(h["period"]), "worth": h["worth"]} for h in history],
        "assets": [a for a in (
            {"label": "Shares", "group": "shares", "value": have["shares"], "share_bps": part(have["shares"])},
            {"label": "Government bonds and bills", "group": "bonds", "value": government, "share_bps": part(government)},
            {"label": "Company bonds", "group": "bonds", "value": have["bonds"] - government, "share_bps": part(have["bonds"] - government)},
            {"label": "Property", "group": "property", "value": have.get("property", 0), "share_bps": part(have.get("property", 0))},
            {"label": "Cash", "group": "cash", "value": have["cash"], "share_bps": part(have["cash"])}) if a["value"] > 0],
        "holdings": [{"ticker": line["ticker"], "name": facts[line["ticker"]]["name"], "sector": facts[line["ticker"]]["sector"],
                      "city": facts[line["ticker"]]["headquarters"], "value": line["value"], "share_bps": part(line["value"])}
                     for line in sorted(have["lines"], key=lambda line: -line["value"])[:8]],
        "cities": [{"city": city, "value": value} for city, value in sorted(by_city.items(), key=lambda i: -i[1])],
        "government": government, "government_bps": part(government),
    }
