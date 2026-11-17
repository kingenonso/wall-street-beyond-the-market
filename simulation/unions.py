"""Unions and strikes, part 1 (owner, 16 November 2026: "build"; the leaders are computer-run).

One union for each industry outside banking and insurance, with a named leader. Strikes are no longer drawn at random
for listed companies; they have causes. At each quarter's close the staff of every listed company weigh up how they
are treated:

  * pay against prices over the year (the squeeze every worker feels);
  * profits up on a year ago while pay stood still;
  * jobs cut in the quarter;
  * dividends paid out while pay fell behind;
  * a recent pay deal calms them, and so does a strike in the last two quarters (nobody is paid on strike).

The leader's temper scales the total. An angry enough workforce lodges a demand for the coming quarter: a pay rise,
with a deadline seven game days after it is made public. On the deadline the board answers. It weighs a year of the
higher wage bill against what a strike would cost, and agrees, offers less, or refuses. The union takes an offer close
enough to its demand (how close depends on the leader); otherwise its members walk out. A strike is a real event of
the quarter: the days lost come off the company's sales when the quarter closes. It ends in a settlement halfway
between the demand and the offer.

A settlement raises the company's wage bill above the going rate (`companies.union_pay_bps`). The going rate catches up
a quarter of the gap each quarter, so a deal fades over about two years.

Nothing here moves money directly. A strike changes the company's sales and a pay deal its costs; the company's own
quarter then plays out through the ledger as always.
"""

from __future__ import annotations

import hashlib
from datetime import datetime

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from simulation import clock, news
from simulation import world_data as data
from simulation.money import BPS, apply_bps

FINANCIAL = ("banking", "insurance")


def _rows(conn: Connection, sql: str, params=()) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def _one(conn: Connection, sql: str, params=()) -> dict | None:
    rows = _rows(conn, sql, params)
    return rows[0] if rows else None


def ready(conn: Connection) -> bool:
    return _one(conn, "SELECT to_regclass('union_disputes') IS NOT NULL AS ok")["ok"]


def _unit(seed: str, *key) -> float:
    """A number from 0 up to 1, fixed by the world's secret and the key: nobody outside the server can know it."""
    digest = hashlib.sha256(f"{seed}:union:{':'.join(str(k) for k in key)}".encode()).digest()
    return int.from_bytes(digest[:8], "big") / 2**64


def _pct(bps: int) -> str:
    return f"{bps / 100:.1f}%".replace(".0%", "%")


def ensure(conn: Connection) -> None:
    """One union for each industry, made the first time it is needed."""
    have = {r["sector"] for r in _rows(conn, "SELECT sector FROM unions")}
    sectors = {r["code"] for r in _rows(conn, "SELECT code FROM sectors")}
    for sector, (name, leader, militancy) in data.UNIONS.items():
        if sector in sectors and sector not in have:
            conn.execute("INSERT INTO unions (sector, name, leader, militancy_bps) VALUES (%s, %s, %s, %s)",
                         (sector, name, leader, militancy))


def decides_strikes(company: dict) -> bool:
    """Whether a union, rather than chance, decides this company's strikes: every listed company outside finance."""
    return bool(company.get("listed", True)) and company["sector"] not in FINANCIAL and company["sector"] in data.UNIONS


# ---------------------------------------------------------------------------
# How angry the staff are
# ---------------------------------------------------------------------------

def _squeeze(conn: Connection, period: int) -> int:
    """How far prices outran pay over the year to this quarter, in hundredths of a percent (never below nothing)."""
    rows = {r["period"]: r for r in _rows(conn, "SELECT period, price_index_bps, wage_index_bps FROM economy_results"
                                                " WHERE period IN (%s, %s)", (period, max(period - 4, 0)))}
    now, then = rows.get(period), rows.get(max(period - 4, 0))
    if not now or not then:
        return 0
    prices = (now["price_index_bps"] - then["price_index_bps"]) * BPS // then["price_index_bps"]
    pay = (now["wage_index_bps"] - then["wage_index_bps"]) * BPS // then["wage_index_bps"]
    return max(prices - pay, 0)


def anger(conn: Connection, company: dict, period: int, squeeze: int, militancy: int) -> tuple[int, list[str]]:
    """How angry a company's staff are at this quarter's close, and why, in plain words."""
    points, why = 0, []
    if squeeze > 0:
        points += squeeze * data.UNION_SQUEEZE_WEIGHT
        why.append(f"Prices rose {_pct(squeeze)} more than pay over the year.")
    results = {r["period"]: r for r in _rows(
        conn, "SELECT period, net_profit, staff, dividends_paid FROM company_results WHERE company_id = %s AND period IN (%s, %s, %s)",
        (company["id"], period, period - 1, period - 4))}
    now, last, year_ago = results.get(period), results.get(period - 1), results.get(period - 4)
    pay = company.get("union_pay_bps") or 0
    if now and year_ago and year_ago["net_profit"] > 0 and now["net_profit"] > 0 and pay < 200 \
            and (now["net_profit"] - year_ago["net_profit"]) * BPS // year_ago["net_profit"] >= data.UNION_PROFIT_RISE_BPS:
        points += data.UNION_PROFIT_ANGER_BPS
        why.append("Profits are well up on a year ago, and pay is not.")
    if now and last and last["staff"] > 0:
        cut = (last["staff"] - now["staff"]) * BPS // last["staff"]
        if cut > data.UNION_JOB_CUT_BPS:
            points += cut * data.UNION_JOB_CUT_WEIGHT
            why.append(f"It cut about {_pct(cut)} of its jobs this quarter.")
    if now and now["dividends_paid"] > 0 and squeeze > 0 and pay < 200:
        points += data.UNION_DIVIDEND_ANGER_BPS
        why.append("It paid its shareholders a dividend while pay fell behind prices.")
    if pay:
        points -= pay * 2
        why.append(f"It already pays {_pct(pay)} above the going rate after a deal.")
    struck = _one(conn, "SELECT 1 AS x FROM union_disputes WHERE company_id = %s AND strike_days IS NOT NULL AND period >= %s LIMIT 1",
                  (company["id"], period - 1))
    if struck:
        points -= data.UNION_RECENT_STRIKE_CALM_BPS
        why.append("Its staff struck lately and lost pay doing it.")
    points = max(points, 0) * militancy // 5000
    return points, why


def at_close(conn: Connection, period: int, seed: str, now: datetime) -> list[dict]:
    """At the quarter's close: a pay deal fades as the going rate catches up, then each listed company's union decides
    whether to lodge a demand for the coming quarter. Returns the demands lodged."""
    if not ready(conn):
        return []
    ensure(conn)
    conn.execute("UPDATE companies SET union_pay_bps = union_pay_bps - (union_pay_bps * %s / 10000) WHERE union_pay_bps > 0",
                 (data.UNION_PAY_CATCH_UP_BPS,))
    squeeze = _squeeze(conn, period)
    unions = {u["sector"]: u for u in _rows(conn, "SELECT * FROM unions")}
    lodged = []
    for company in _rows(conn, "SELECT id, ticker, name, sector, headquarters, listed, union_pay_bps FROM companies"
                               " WHERE listed AND status = 'trading' ORDER BY ticker"):
        union = unions.get(company["sector"])
        if union is None or not decides_strikes(company):
            continue
        points, why = anger(conn, company, period, squeeze, union["militancy_bps"])
        if points < data.UNION_DISPUTE_AT_BPS:
            continue
        demand = min(max(points // 5 // 50 * 50, data.UNION_DEMAND_MIN_BPS), data.UNION_DEMAND_MAX_BPS)
        opened = 2 + int(_unit(seed, period + 1, company["ticker"], "opened") * 60)
        deadline = opened + data.UNION_NOTICE_DAYS
        row = _one(conn, "INSERT INTO union_disputes (union_id, company_id, period, opened_day, deadline_day, anger_bps, reasons, demand_bps)"
                         " VALUES (%s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (company_id, period) DO NOTHING RETURNING id",
                   (union["id"], company["id"], period + 1, opened, deadline, points, Jsonb(why), demand))
        if row is None:
            continue
        lodged.append({"company": company["ticker"], "demand_bps": demand, "anger_bps": points, "day": opened,
                       "news": {"union": union["name"], "leader": union["leader"], "company": company["name"], "ticker": company["ticker"],
                                "city": company["headquarters"], "demand": _pct(demand), "days": news.number_word(data.UNION_NOTICE_DAYS),
                                "grievance": why[0] if why else "Its staff say their pay has fallen behind."},
                       "sector": company["sector"]})
    # In date order, so a paper never tells two demands running in the same words.
    for x in sorted(lodged, key=lambda x: (x["day"], x["company"])):
        f = x.pop("news")
        news.publish(conn, period=period + 1, day=x["day"], kind="union_demand", story=f"union:{f['ticker']}:{period + 1}", facts=f,
                     tickers=[f["ticker"]], sectors=[x.pop("sector")], locations=[f["city"]], boost=min(x["anger_bps"] // 1000, 15))
    return lodged


# ---------------------------------------------------------------------------
# The deadline: the board answers, the union takes it or walks out
# ---------------------------------------------------------------------------

def _board_offer(conn: Connection, dispute: dict, company: dict) -> int:
    """What a computer-run board offers: the rise at which a year of the higher wage bill costs what a strike would."""
    last = _one(conn, "SELECT revenue, wages, cost_of_sales FROM company_results WHERE company_id = %s ORDER BY period DESC LIMIT 1",
                (company["id"],))
    if not last or last["revenue"] <= 0:
        return dispute["demand_bps"] // 2
    pay_bill = max(last["wages"], 1) * 4                                   # a year of wages
    middle = (data.UNION_STRIKE_DAYS[0] + data.UNION_STRIKE_DAYS[1]) // 2
    strike_cost = apply_bps(last["revenue"] * middle // clock.GAME_DAYS_PER_QUARTER, data.UNION_MARGIN_BPS)
    worth = strike_cost * BPS // pay_bill                                  # the rise that costs as much as the strike
    return max(min(worth // 25 * 25, dispute["demand_bps"]), 0)


def _union_takes(dispute: dict, union: dict, offer: int) -> bool:
    """A leader takes an offer close enough to the demand: a calm one at half, the most militant only at the full rise."""
    need = dispute["demand_bps"] * (5000 + union["militancy_bps"] // 2) // BPS
    return offer >= need


def _strike_days(seed: str, dispute: dict, union: dict, ticker: str) -> int:
    low, high = data.UNION_STRIKE_DAYS
    spread = (high - low) * (dispute["anger_bps"] + union["militancy_bps"]) // (dispute["anger_bps"] + 10_000)
    return min(low + int(_unit(seed, dispute["period"], ticker, "length") * max(spread, 1)), high)


def _story(company: dict, dispute: dict) -> str:
    return f"union:{company['ticker']}:{dispute['period']}"


def decide(conn: Connection, dispute: dict, seed: str, now: datetime) -> dict:
    """The deadline has come: the board answers and the union takes the offer or strikes."""
    union = _one(conn, "SELECT * FROM unions WHERE id = %s", (dispute["union_id"],))
    company = _one(conn, "SELECT id, ticker, name, sector, headquarters, union_pay_bps FROM companies WHERE id = %s", (dispute["company_id"],))
    offer = _board_offer(conn, dispute, company)
    facts = {"union": union["name"], "leader": union["leader"], "company": company["name"], "ticker": company["ticker"],
             "city": company["headquarters"], "demand": _pct(dispute["demand_bps"]), "offer": _pct(offer)}
    where = {"tickers": [company["ticker"]], "sectors": [company["sector"]], "locations": [company["headquarters"]]}
    if offer >= dispute["demand_bps"] or _union_takes(dispute, union, offer):
        _pay_rise(conn, company, offer)
        conn.execute("UPDATE union_disputes SET status = 'agreed', offer_bps = %s, settled_bps = %s, decided_at = %s WHERE id = %s",
                     (offer, offer, now, dispute["id"]))
        news.publish(conn, period=dispute["period"], day=dispute["deadline_day"], kind="union_deal", story=_story(company, dispute),
                     facts={**facts, "settled": _pct(offer)}, **where)
        return {"status": "agreed", "settled_bps": offer}
    days = _strike_days(seed, dispute, union, company["ticker"])
    ends = min(dispute["deadline_day"] + days, clock.GAME_DAYS_PER_QUARTER)
    lost = -min(days * BPS // clock.GAME_DAYS_PER_QUARTER, 5000)
    event = _one(conn, "INSERT INTO events (period, day, kind, location, sector, company_id, sales_bps, facts)"
                       " VALUES (%s, %s, 'company_strike', %s, %s, %s, %s, %s) RETURNING id",
                 (dispute["period"], dispute["deadline_day"], company["headquarters"], company["sector"], company["id"], lost,
                  Jsonb({"company": company["name"], "ticker": company["ticker"], "location": company["headquarters"],
                         "union": union["name"], "days": days})))
    conn.execute("UPDATE union_disputes SET status = 'struck', offer_bps = %s, strike_days = %s, ends_day = %s, event_id = %s,"
                 " decided_at = %s WHERE id = %s", (offer, days, ends, event["id"], now, dispute["id"]))
    news.publish(conn, period=dispute["period"], day=dispute["deadline_day"], kind="union_strike", story=_story(company, dispute),
                 facts={**facts, "days": news.number_word(days)}, boost=min(days, 15), **where)
    return {"status": "struck", "strike_days": days}


def _pay_rise(conn: Connection, company: dict, bps: int) -> None:
    if bps > 0:
        conn.execute("UPDATE companies SET union_pay_bps = least(union_pay_bps + %s, %s) WHERE id = %s",
                     (bps, data.UNION_PAY_LIMIT_BPS, company["id"]))


def end_strike(conn: Connection, dispute: dict) -> dict:
    """A strike's last day: the two sides settle halfway between the demand and the offer."""
    union = _one(conn, "SELECT * FROM unions WHERE id = %s", (dispute["union_id"],))
    company = _one(conn, "SELECT id, ticker, name, sector, headquarters FROM companies WHERE id = %s", (dispute["company_id"],))
    settled = (dispute["demand_bps"] + (dispute["offer_bps"] or 0)) // 2 // 25 * 25
    _pay_rise(conn, company, settled)
    conn.execute("UPDATE union_disputes SET status = 'ended', settled_bps = %s WHERE id = %s", (settled, dispute["id"]))
    news.publish(conn, period=dispute["period"], day=dispute["ends_day"], kind="union_strike_over", story=_story(company, dispute),
                 facts={"union": union["name"], "leader": union["leader"], "company": company["name"], "ticker": company["ticker"],
                        "city": company["headquarters"], "settled": _pct(settled), "days": news.number_word(dispute["strike_days"])},
                 tickers=[company["ticker"]], sectors=[company["sector"]], locations=[company["headquarters"]])
    return {"status": "ended", "settled_bps": settled}


def _work_through(conn: Connection, period: int, day: int, seed: str, now: datetime) -> int:
    """Everything due by this game day of this quarter: deadlines answered and strikes ended. Returns how many."""
    done = 0
    for dispute in _rows(conn, "SELECT * FROM union_disputes WHERE period = %s AND status = 'open' AND deadline_day <= %s"
                               " ORDER BY deadline_day, id FOR UPDATE SKIP LOCKED", (period, day)):
        decide(conn, dispute, seed, now)
        done += 1
    for dispute in _rows(conn, "SELECT * FROM union_disputes WHERE period = %s AND status = 'struck' AND ends_day <= %s"
                               " ORDER BY ends_day, id FOR UPDATE SKIP LOCKED", (period, day)):
        end_strike(conn, dispute)
        done += 1
    return done


def tick(conn: Connection, now: datetime) -> int:
    """Answer the deadlines and end the strikes whose day has come in the running quarter."""
    if not ready(conn):
        return 0
    from simulation import careers
    world = careers.world_now(conn, now)
    state = _one(conn, "SELECT last_closed_period, fortune_seed FROM world_state")
    if not world["started"] or state is None or world["period"] != state["last_closed_period"] + 1:
        return 0                      # between a quarter's end and its close, nothing new is decided
    return _work_through(conn, world["period"], world["day"], state["fortune_seed"], now)


def before_close(conn: Connection, period: int, seed: str, now: datetime) -> None:
    """Before the quarter's events are read: every deadline and strike in the quarter is settled, so none is missed."""
    if ready(conn):
        _work_through(conn, period, clock.GAME_DAYS_PER_QUARTER, seed, now)


def apply_pay(companies: list[dict]) -> None:
    """A pay deal makes the company's people dearer: its direct labour and its running costs rise by the deal."""
    for company in companies:
        extra = company.get("union_pay_bps") or 0
        if extra:
            company["labour_bps"] = min(apply_bps(company["labour_bps"], BPS + extra), BPS)
            company["opex_bps"] = apply_bps(company["opex_bps"], BPS + extra)


# ---------------------------------------------------------------------------
# The screen
# ---------------------------------------------------------------------------

STATUS_WORDS = {"open": "demand lodged", "agreed": "agreed", "struck": "on strike", "ended": "strike over, settled"}


def view(conn: Connection, now: datetime, ticker: str | None = None) -> dict:
    """The unions, the disputes the public knows of, and the deals in force. Nothing before its day is shown."""
    if not ready(conn):
        return {"ready": False}
    ensure(conn)
    from simulation import careers
    world = careers.world_now(conn, now)
    period, day = world["period"], world["day"]
    sectors = {r["code"]: r["name"] for r in _rows(conn, "SELECT code, name FROM sectors")}
    unions = _rows(conn, "SELECT * FROM unions ORDER BY name")
    shown = _rows(conn,
                  "SELECT d.*, c.ticker, c.name AS company, c.headquarters AS city, u.name AS union_name"
                  " FROM union_disputes d JOIN companies c ON c.id = d.company_id JOIN unions u ON u.id = d.union_id"
                  " WHERE d.period >= %s AND (d.period < %s OR d.opened_day <= %s) ORDER BY d.period DESC, d.opened_day DESC, d.id DESC",
                  (period - 4, period, day))

    def row(d: dict) -> dict:
        now_here = d["period"] == period
        striking = d["status"] == "struck" and now_here and d["deadline_day"] <= day
        return {"id": d["id"], "union": d["union_name"], "company": d["company"], "ticker": d["ticker"], "city": d["city"],
                "quarter": clock.period_label(d["period"]), "opened_day": d["opened_day"], "deadline_day": d["deadline_day"],
                "demand_bps": d["demand_bps"], "reasons": d["reasons"],
                "offer_bps": d["offer_bps"] if d["status"] != "open" else None,
                "settled_bps": d["settled_bps"], "strike_days": d["strike_days"] if d["status"] != "open" else None,
                "ends_day": d["ends_day"] if d["status"] != "open" else None,
                "status": d["status"], "status_words": "on strike now" if striking else STATUS_WORDS[d["status"]],
                "days_left": max(d["deadline_day"] - day, 0) if d["status"] == "open" and now_here else None}

    rows = [row(d) for d in shown]
    company = None
    if ticker:
        # One company's union, for its own page (owner, 17 November 2026: no Unions tab; it lives where people look).
        c = _one(conn, "SELECT c.ticker, c.sector, c.listed, c.union_pay_bps, u.name, u.leader, u.militancy_bps FROM companies c"
                       " LEFT JOIN unions u ON u.sector = c.sector WHERE c.ticker = %s", (ticker.upper(),))
        if c and c["name"]:
            mine = [r for r in rows if r["ticker"] == c["ticker"]]
            company = {"ticker": c["ticker"], "union": c["name"], "leader": c["leader"], "militancy_bps": c["militancy_bps"],
                       "above_bps": c["union_pay_bps"], "decides": bool(c["listed"]),
                       "now": [r for r in mine if r["status"] == "open" or r["status_words"] == "on strike now"],
                       "past": [r for r in mine if not (r["status"] == "open" or r["status_words"] == "on strike now")][:4]}
    deals = _rows(conn, "SELECT ticker, name, union_pay_bps FROM companies WHERE union_pay_bps > 0 ORDER BY union_pay_bps DESC, ticker")
    counts = {r["union_id"]: r for r in _rows(
        conn, "SELECT union_id, count(*) FILTER (WHERE strike_days IS NOT NULL) AS strikes, count(*) AS disputes,"
              " coalesce(sum(strike_days), 0) AS days FROM union_disputes GROUP BY union_id")}
    return {
        "ready": True, "quarter": clock.period_label(period), "day": day, "squeeze_bps": _squeeze(conn, period - 1), "company": company,
        "unions": [{"name": u["name"], "leader": u["leader"], "industry": sectors.get(u["sector"], u["sector"]),
                    "militancy_bps": u["militancy_bps"],
                    "disputes": (counts.get(u["id"]) or {}).get("disputes", 0), "strikes": (counts.get(u["id"]) or {}).get("strikes", 0),
                    "strike_days": (counts.get(u["id"]) or {}).get("days", 0)} for u in unions],
        "open": [r for r in rows if r["status"] == "open" or r["status_words"] == "on strike now"],
        "past": [r for r in rows if not (r["status"] == "open" or r["status_words"] == "on strike now")][:40],
        "deals": [{"ticker": d["ticker"], "company": d["name"], "above_bps": d["union_pay_bps"]} for d in deals],
        "rules": {"dispute_at_bps": data.UNION_DISPUTE_AT_BPS, "notice_days": data.UNION_NOTICE_DAYS,
                  "strike_days": list(data.UNION_STRIKE_DAYS), "catch_up_bps": data.UNION_PAY_CATCH_UP_BPS,
                  "demand_bps": [data.UNION_DEMAND_MIN_BPS, data.UNION_DEMAND_MAX_BPS]},
    }
