"""Stage 10: the confirmed facts a journalist may build a story from.

Every fact here is public and already on the record: a company's filed results and its credit rating, an open
takeover offer, a stake an empire has disclosed, the Central Bank's decision, an event that has happened, a big
move in a share price, a public works project, homes repossessed in a city. Nothing hidden is ever a fact: no
event still to come this quarter, no private company's secrets, nobody's holdings, no seed.

Each fact is a card: what it says, the figures in it, whether it is good or bad news for the companies it names,
where it is kept in the record (so the journalist can check it), and which kinds of wire news would carry it
(so the game can tell a scoop from old news).
"""

from __future__ import annotations

from datetime import datetime

from psycopg import Connection
from psycopg.rows import dict_row

from simulation import clock, events
from simulation.money import BPS

PRICE_MOVE_BPS = 500                  # a share moving 5% or more in a day is a fact worth a story
RATING_ORDER = ("AAA", "AA", "A", "BBB", "BB", "B", "CCC", "D")


def _rows(conn: Connection, sql: str, params=()) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def money(kobo: int) -> str:
    amount = abs(kobo) / 100
    for size, word in ((1e12, "trillion"), (1e9, "billion"), (1e6, "million")):
        if amount >= size:
            return f"₦{amount / size:.1f} {word}".replace(".0 ", " ")
    return f"₦{amount:,.0f}"


def percent(bps: int) -> str:
    return f"{abs(bps) / 100:.1f}".rstrip("0").rstrip(".") + "%"


def _card(**fields) -> dict:
    fields.setdefault("tickers", [])
    fields.setdefault("empire_id", None)
    fields.setdefault("scoopable", True)
    fields.setdefault("importance", 50)
    return fields


def _now(conn: Connection, now: datetime) -> tuple[int, int]:
    from simulation import careers
    w = careers.world_now(conn, now)
    return w["period"], w["day"]


def _results(conn: Connection, period: int) -> list[dict]:
    """Each listed company's last filed quarter, against the same quarter a year ago (or the quarter before)."""
    from simulation import insight
    out = []
    for c in _rows(conn, "SELECT id, ticker, name, sector FROM companies WHERE listed AND status = 'trading' ORDER BY ticker"):
        reports = insight._filed(conn, c["id"], period - 1)
        if not reports or reports[-1]["period"] != period - 1 or period - 1 < 1:
            continue
        report = reports[-1]
        version = _rows(conn, "SELECT max(version) AS v FROM company_reports WHERE company_id = %s AND period = %s",
                        (c["id"], report["period"]))[0]["v"]
        compared, with_what = insight._against(reports, report)
        profit, sales = report["income"]["net_profit"], report["income"]["revenue"]
        label = clock.period_label(report["period"])
        figures = {"profit": money(profit), "sales": money(sales), "quarter": label}
        line = f"{c['name']} made {'a profit of ' + money(profit) if profit >= 0 else 'a loss of ' + money(profit)} in {label}, on sales of {money(sales)}"
        tone, change = 0, 0
        if compared:
            before = compared["income"]["net_profit"]
            if before and (before > 0) == (profit > 0):
                change = (profit - before) * BPS // abs(before)
                figures["change"] = percent(change)
                line += f": profit {'up' if change >= 0 else 'down'} {percent(change)} on {with_what}"
                tone = 1 if change > 300 else -1 if change < -300 else 0
            elif before <= 0 < profit:
                tone, line = 1, line + f", back in profit after a loss in {with_what}"
            elif before > 0 >= profit:
                tone, line = -1, line + f", after a profit in {with_what}"
        out.append(_card(
            id=f"results:{c['ticker']}:{report['period']}", kind="results",
            title=f"{c['name']}: {label} results", line=line + ".", figures=figures, tone=tone,
            tickers=[c["ticker"]], period=period, day=1, importance=55 + min(abs(change) // 500, 30),
            wire_kinds=["results_strong", "results_weak", "company_loss", "back_in_profit"],
            source=f"report:{c['id']}:{report['period']}:{version}", ripple=f"results:{c['ticker']}:{report['period']}",
            record=f"{c['name']}'s filed accounts for {label} (the Results page)"))
        if len(reports) >= 2 and reports[-2]["credit_rating"] != report["credit_rating"]:
            old, new = reports[-2]["credit_rating"], report["credit_rating"]
            better = RATING_ORDER.index(new) < RATING_ORDER.index(old)
            out.append(_card(
                id=f"rating:{c['ticker']}:{report['period']}", kind="rating",
                title=f"{c['name']}'s credit rating {'raised' if better else 'cut'} to {new}",
                line=f"{c['name']}'s credit rating was {'raised' if better else 'cut'} from {old} to {new} on its {label} accounts.",
                figures={"rating": new, "old_rating": old, "quarter": label}, tone=1 if better else -1,
                tickers=[c["ticker"]], period=period, day=1, importance=65,
                wire_kinds=["rating_upgrade", "rating_downgrade"],
                source=f"report:{c['id']}:{report['period']}:{version}", ripple=f"rating:{c['ticker']}:{report['period']}",
                record=f"{c['name']}'s filed accounts for {label}, the credit rating"))
    return out


def _takeovers(conn: Connection, period: int) -> list[dict]:
    out = []
    for t in _rows(conn, "SELECT t.*, tc.ticker AS target_ticker, tc.name AS target, bc.name AS bidder, e.name AS empire"
                         " FROM takeovers t JOIN companies tc ON tc.id = t.target_company_id"
                         " LEFT JOIN companies bc ON bc.id = t.bidder_company_id LEFT JOIN empires e ON e.id = t.bidder_empire_id"
                         " WHERE t.status = 'open' ORDER BY t.id"):
        who = t["empire"] or t["bidder"] or "A bidder"
        out.append(_card(
            id=f"takeover:{t['id']}", kind="takeover",
            title=f"{who} bids for {t['target']}",
            line=f"{who} has offered ₦{t['price'] / 100:,.2f} a share for {t['target']}, {percent(t['premium_bps'])} above the market price"
                 f"{', against the wishes of its board' if t['hostile'] else ''}.",
            figures={"price": f"₦{t['price'] / 100:,.2f}", "premium": percent(t["premium_bps"])}, tone=1,
            tickers=[t["target_ticker"]], empire_id=t["bidder_empire_id"], period=t["opens_period"], day=1, importance=85,
            wire_kinds=["takeover_bid", "takeover_hostile", "empire_offer"], source=f"takeover:{t['id']}",
            ripple=f"takeover:{t['id']}", record="the offer document on the company's page"))
    return out


def _stakes(conn: Connection, period: int) -> list[dict]:
    world = _rows(conn, "SELECT world_start, weeks_ahead FROM world_state")[0]
    start = clock.effective_start(world["world_start"], world["weeks_ahead"])
    out = []
    for s in _rows(conn, "SELECT s.*, e.name AS empire, c.name AS company, c.ticker FROM stake_disclosures s"
                         " JOIN empires e ON e.id = s.empire_id JOIN companies c ON c.id = s.company_id"
                         " WHERE s.bps > 0 ORDER BY s.at DESC LIMIT 40"):
        when = clock.game_date(s["at"], start)
        said_period = ((when.year - 1) * clock.QUARTERS_PER_YEAR + when.quarter) if when else period
        out.append(_card(
            id=f"stake:{s['empire_id']}:{s['ticker']}:{s['bps']}", kind="stake",
            title=f"{s['empire']} holds {percent(s['bps'])} of {s['company']}",
            line=f"{s['empire']} has disclosed that it holds {percent(s['bps'])} or more of {s['company']}.",
            figures={"stake": percent(s["bps"])}, tone=0, tickers=[s["ticker"]], empire_id=s["empire_id"],
            period=said_period, day=when.day_of_quarter if when else 1, importance=50, wire_kinds=["stake_disclosed"],
            source=f"stake:{s['empire_id']}:{s['company_id']}", ripple=f"stake:{s['empire_id']}:{s['ticker']}",
            record="the disclosures on the company's page"))
    return out


def _rate(conn: Connection, period: int) -> list[dict]:
    row = _rows(conn, "SELECT * FROM economy_results WHERE period = %s", (period - 1,))
    if not row or period - 1 < 1:
        return []
    r = row[0]
    old, new = r["policy_rate_bps"], r["next_policy_rate_bps"]
    word = "raised" if new > old else "cut" if new < old else "held"
    return [_card(
        id=f"rate:{period - 1}", kind="rate", title=f"The Central Bank {word} its rate{'' if word == 'held' else ' to ' + percent(new)}",
        line=f"The Central Bank {word} its rate {'at' if word == 'held' else 'from ' + percent(old) + ' to'} {percent(new)}, with prices rising "
             f"{percent(r['inflation_bps'])} a year.",
        figures={"rate": percent(new), "old_rate": percent(old), "inflation": percent(r["inflation_bps"])},
        tone=-1 if new > old else 1 if new < old else 0, period=period, day=1, importance=90,
        wire_kinds=["rate_rise", "rate_cut", "rate_hold"], source=f"economy:{period - 1}", ripple=f"rate:{period - 1}",
        record="the Central Bank's decision on the Economy page")]


def _events(conn: Connection, period: int, day: int) -> list[dict]:
    from simulation import news
    out = []
    companies = {c["id"]: c for c in _rows(conn, "SELECT id, ticker, name, sector, headquarters FROM companies WHERE listed")}
    for e in events.load(conn, period):
        if e["day"] > day:
            continue                                   # still to come: never a fact
        kind = events.BY_NAME[e["kind"]]
        touched = [c for c in companies.values() if events.touches(e, c)]
        if kind.scope == "company" and e["company_id"] in companies:
            where = companies[e["company_id"]]["name"]
        elif kind.scope == "sector":
            where = news.SECTOR_WORDS.get(e["sector"], e["sector"])
        elif kind.scope == "national":
            where = "the whole country"
        else:
            where = e["location"]
        word, _ = news.severity(e)
        good = e["kind"] in news.GOOD_NEWS
        from simulation import ripple
        key = ripple.event_key(conn, e)
        out.append(_card(
            id=key, kind="event",
            title=f"{e['kind'].replace('_', ' ').capitalize()}: {where}",
            line=f"A {word} {e['kind'].replace('_', ' ')} hit {where} on day {e['day']} of {clock.period_label(period)}.",
            figures={"day": str(e["day"])}, tone=1 if good else -1, tickers=[c["ticker"] for c in touched][:6],
            period=period, day=e["day"], importance=60, wire_kinds=[e["kind"]], source=key,
            ripple=key, record="the news wire for that day"))
    return out


def _price_moves(conn: Connection, period: int, day: int, now: datetime) -> list[dict]:
    from simulation import exchange
    today, _ = exchange.session_of(now)          # only trading days that have closed: today's prices are still moving
    rows = _rows(conn, """
        WITH days AS (SELECT DISTINCT session_date AS d FROM market_trades WHERE session_date < %s ORDER BY d DESC LIMIT 2),
             closes AS (SELECT DISTINCT ON (company_id, session_date) company_id, session_date, price / split_factor(company_id, id) AS price
                        FROM market_trades WHERE session_date IN (SELECT d FROM days) ORDER BY company_id, session_date, id DESC)
        SELECT c.ticker, c.name, a.session_date AS day, a.price AS now, b.price AS before
        FROM closes a JOIN closes b ON b.company_id = a.company_id AND b.session_date < a.session_date
        JOIN companies c ON c.id = a.company_id""", (today,))
    out = []
    for r in rows:
        if not r["before"]:
            continue
        change = (int(r["now"]) - int(r["before"])) * BPS // int(r["before"])
        if abs(change) < PRICE_MOVE_BPS:
            continue
        out.append(_card(
            id=f"price:{r['ticker']}:{r['day']}", kind="price",
            title=f"{r['name']} shares {'jump' if change > 0 else 'slide'} {percent(change)}",
            line=f"{r['name']}'s shares closed {'up' if change > 0 else 'down'} {percent(change)} on {r['day']:%d %B}, at ₦{int(r['now']) / 100:,.2f}.",
            figures={"change": percent(change), "price": f"₦{int(r['now']) / 100:,.2f}"}, tone=1 if change > 0 else -1,
            tickers=[r["ticker"]], period=period, day=day, importance=45, wire_kinds=[], scoopable=False,
            source=f"price:{r['ticker']}:{r['day']}", ripple=f"price:{r['ticker']}:{r['day']}",
            record="the day's closing prices on the Market page"))
    return out


def _property(conn: Connection, period: int) -> list[dict]:
    out = []
    if _rows(conn, "SELECT to_regclass('infrastructure_projects') IS NOT NULL AS ok")[0]["ok"]:
        for p in _rows(conn, "SELECT i.*, d.name AS district, d.city FROM infrastructure_projects i JOIN districts d ON d.id = i.district_id"
                             " WHERE i.announced_period >= %s ORDER BY i.id", (period - 2,)):
            out.append(_card(
                id=f"infra:{p['id']}", kind="infrastructure", title=f"The {p['name']} is to be built",
                line=f"The Government is building the {p['name']} beside {p['district']}, {p['city']}, due in {clock.period_label(p['finish_period'])}.",
                figures={"finish": clock.period_label(p["finish_period"])}, tone=1, period=p["announced_period"] + 1, day=1,
                importance=55, wire_kinds=["infrastructure_announced"], source=f"infra:{p['id']}", ripple=f"infra:{p['id']}",
                record="Public works on the Property page"))
        for h in _rows(conn, "SELECT * FROM home_loan_results WHERE period = %s AND repossessed >= 500 ORDER BY repossessed DESC", (period - 1,)):
            out.append(_card(
                id=f"homes:{h['location']}:{period - 1}", kind="homes",
                title=f"Homes repossessed in {h['location']}",
                line=f"Banks repossessed about {h['repossessed']:,} homes in {h['location']} in {clock.period_label(period - 1)}, with mortgages at {percent(h['rate_bps'])}.",
                figures={"homes": f"{h['repossessed']:,}", "rate": percent(h["rate_bps"])}, tone=-1, period=period, day=1,
                importance=60, wire_kinds=["home_repossessions"], source=f"homes:{h['location']}:{period - 1}",
                ripple=f"homes:{h['location']}:{period - 1}", record="Households' home loans on the Property page"))
    return out


def facts(conn: Connection, now: datetime) -> list[dict]:
    """Every confirmed fact a story may use today, newest and most important first."""
    period, day = _now(conn, now)
    cards = (_rate(conn, period) + _takeovers(conn, period) + _results(conn, period) + _stakes(conn, period)
             + _events(conn, period, day) + _price_moves(conn, period, day, now) + _property(conn, period))
    seen, out = set(), []
    for c in sorted(cards, key=lambda c: (-c["importance"], c["id"])):
        if c["id"] not in seen:
            seen.add(c["id"])
            out.append(c)
    return out


def find(conn: Connection, fact_id: str, now: datetime) -> dict | None:
    return next((c for c in facts(conn, now) if c["id"] == fact_id), None)


def still_true(conn: Connection, card: dict) -> bool:
    """Whether the record still says what the card said. A company that restates its accounts makes its old cards untrue."""
    if card["kind"] in ("results", "rating"):
        _, company_id, period, version = card["source"].split(":")
        latest = _rows(conn, "SELECT max(version) AS v FROM company_reports WHERE company_id = %s AND period = %s",
                       (company_id, int(period)))[0]["v"]
        return latest == int(version)
    return True
