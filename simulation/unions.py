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
from simulation.private import MORALE_SLOW_BPS

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
    """Whether a union, rather than chance, decides this company's strikes: every company outside finance, listed or
    private (part 2: a private company's walkout is now the union's call too)."""
    return company["sector"] not in FINANCIAL and company["sector"] in data.UNIONS


def controlling_empire(conn: Connection, company_id) -> dict | None:
    """The empire run by players that controls this company, whose head answers its union. None for a company run by
    its own board, its founders, or an empire the computer runs."""
    return _one(conn, "SELECT e.id, e.name, e.head_player_id, e.account_id FROM owned_companies o JOIN empires e ON e.id = o.empire_id"
                      " WHERE o.company_id = %s AND e.kind = 'player' AND e.status = 'active' AND e.head_player_id IS NOT NULL", (company_id,))


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
    private = _one(conn, "SELECT pay_index_bps, morale_bps FROM private_profiles WHERE company_id = %s", (company["id"],)) \
        if not company.get("listed", True) else None
    if private:
        wage = _one(conn, "SELECT wage_index_bps FROM economy_results WHERE period = %s", (period,))
        ratio = private["pay_index_bps"] * BPS // max(wage["wage_index_bps"] if wage else BPS, 1)
        if ratio < BPS:
            points += (BPS - ratio) * data.UNION_PRIVATE_PAY_WEIGHT
            why.append(f"It pays {_pct(BPS - ratio)} below the going rate.")
        elif ratio > BPS:
            points -= (ratio - BPS) * 2
            why.append(f"It pays {_pct(ratio - BPS)} above the going rate.")
        if private["morale_bps"] < MORALE_SLOW_BPS:
            points += MORALE_SLOW_BPS - private["morale_bps"]
            why.append("Its staff's morale is low.")
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
    for company in _rows(conn, "SELECT id, ticker, name, sector, headquarters, listed, union_pay_bps FROM companies c"
                               " WHERE status = 'trading' AND (listed OR EXISTS (SELECT 1 FROM private_profiles p WHERE p.company_id = c.id))"
                               " ORDER BY ticker"):
        union = unions.get(company["sector"])
        if union is None or not decides_strikes(company):
            continue
        points, why = anger(conn, company, period, squeeze, union["militancy_bps"])
        if points < data.UNION_DISPUTE_AT_BPS:
            continue
        demand = min(max(points // 5 // 50 * 50, data.UNION_DEMAND_MIN_BPS), data.UNION_DEMAND_MAX_BPS)
        opened = 2 + int(_unit(seed, period + 1, company["ticker"], "opened") * 60)
        deadline = opened + data.UNION_NOTICE_DAYS
        boss = controlling_empire(conn, company["id"])
        row = _one(conn, "INSERT INTO union_disputes (union_id, company_id, period, opened_day, deadline_day, anger_bps, reasons, demand_bps,"
                         " empire_id) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (company_id, period) DO NOTHING RETURNING id",
                   (union["id"], company["id"], period + 1, opened, deadline, points, Jsonb(why), demand, boss and boss["id"]))
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


def need_bps(dispute: dict, union: dict, seed: str) -> int:
    """The least the leader takes: a calm one half the demand, the most militant the full rise. A mediator who talks the
    union round (most of the time, not always) brings that down."""
    need = dispute["demand_bps"] * (5000 + union["militancy_bps"] // 2) // BPS
    if dispute.get("mediator_fee") and mediator_works(dispute, seed):
        need -= dispute["demand_bps"] * data.UNION_MEDIATOR_EASES_BPS // BPS
    return max(need, 0)


def mediator_works(dispute: dict, seed: str) -> bool:
    return _unit(seed, "mediator", dispute["id"]) * BPS < data.UNION_MEDIATOR_WORKS_BPS


def _union_takes(dispute: dict, union: dict, offer: int, seed: str = "") -> bool:
    return offer > 0 and offer >= need_bps(dispute, union, seed)


def _strike_days(seed: str, dispute: dict, union: dict, ticker: str) -> int:
    low, high = data.UNION_STRIKE_DAYS
    spread = (high - low) * (dispute["anger_bps"] + union["militancy_bps"]) // (dispute["anger_bps"] + 10_000)
    return min(low + int(_unit(seed, dispute["period"], ticker, "length") * max(spread, 1)), high)


def _story(company: dict, dispute: dict) -> str:
    return f"union:{company['ticker']}:{dispute['period']}"


def decide(conn: Connection, dispute: dict, seed: str, now: datetime, *, offer: int | None = None, answer: str | None = None,
           by=None, day: int | None = None) -> dict:
    """The union hears the company's answer and takes it or strikes. With no offer given, the deadline has come: a board
    run by the computer answers by its rule; at a company a player-run empire controls, silence is a refusal."""
    union = _one(conn, "SELECT * FROM unions WHERE id = %s", (dispute["union_id"],))
    company = _one(conn, "SELECT id, ticker, name, sector, headquarters, listed, union_pay_bps FROM companies WHERE id = %s",
                   (dispute["company_id"],))
    day = day or dispute["deadline_day"]
    if offer is None:
        boss = dispute.get("empire_id") and controlling_empire(conn, company["id"])
        if boss and boss["id"] == dispute["empire_id"]:
            offer, answer = 0, "none"                        # nobody answered for the empire: the staff take that as a no
        else:
            offer, answer = _board_offer(conn, dispute, company), "board"
    worked = bool(dispute.get("mediator_fee")) and mediator_works(dispute, seed)
    facts = {"union": union["name"], "leader": union["leader"], "company": company["name"], "ticker": company["ticker"],
             "city": company["headquarters"], "demand": _pct(dispute["demand_bps"]), "offer": _pct(offer)}
    where = {"tickers": [company["ticker"]], "sectors": [company["sector"]], "locations": [company["headquarters"]]}
    if offer >= dispute["demand_bps"] or _union_takes(dispute, union, offer, seed):
        _pay_rise(conn, company, offer, dispute)
        conn.execute("UPDATE union_disputes SET status = 'agreed', offer_bps = %s, settled_bps = %s, decided_at = %s, decided_day = %s,"
                     " answer = %s, answered_by = %s, mediator_worked = %s WHERE id = %s",
                     (offer, offer, now, day, answer, by, worked if dispute.get("mediator_fee") else None, dispute["id"]))
        news.publish(conn, period=dispute["period"], day=day, kind="union_deal", story=_story(company, dispute),
                     facts={**facts, "settled": _pct(offer)}, **where)
        _tell(conn, dispute, f"Deal at {company['name']}: the {union['name']} took {_pct(offer)}. No strike.", now)
        return {"status": "agreed", "settled_bps": offer}
    days = _strike_days(seed, dispute, union, company["ticker"])
    ends = min(day + days, clock.GAME_DAYS_PER_QUARTER)
    lost = -min(days * BPS // clock.GAME_DAYS_PER_QUARTER, 5000)
    event = _one(conn, "INSERT INTO events (period, day, kind, location, sector, company_id, sales_bps, facts)"
                       " VALUES (%s, %s, 'company_strike', %s, %s, %s, %s, %s) RETURNING id",
                 (dispute["period"], day, company["headquarters"], company["sector"], company["id"], lost,
                  Jsonb({"company": company["name"], "ticker": company["ticker"], "location": company["headquarters"],
                         "union": union["name"], "days": days})))
    conn.execute("UPDATE union_disputes SET status = 'struck', offer_bps = %s, strike_days = %s, ends_day = %s, event_id = %s,"
                 " decided_at = %s, decided_day = %s, answer = %s, answered_by = %s, mediator_worked = %s WHERE id = %s",
                 (offer, days, ends, event["id"], now, day, answer, by, worked if dispute.get("mediator_fee") else None, dispute["id"]))
    news.publish(conn, period=dispute["period"], day=day, kind="union_strike", story=_story(company, dispute),
                 facts={**facts, "days": news.number_word(days)}, boost=min(days, 15), **where)
    why = "Nobody answered by the deadline, so" if answer == "none" else f"The company offered {_pct(offer)}, so" if offer else "The company refused, so"
    _tell(conn, dispute, f"Strike at {company['name']}. {why} the {union['name']} walked out for about {days} game days.", now)
    return {"status": "struck", "strike_days": days}


def _tell(conn: Connection, dispute: dict, words: str, now: datetime) -> None:
    """Put it in the controlling empire's decision log, and wake its open screens."""
    if dispute.get("empire_id"):
        conn.execute("INSERT INTO empire_events (empire_id, words, at) VALUES (%s, %s, %s)", (dispute["empire_id"], words, now))
        from simulation import pings
        pings.ping(conn, "chat", dispute["empire_id"])


def _pay_rise(conn: Connection, company: dict, bps: int, dispute: dict | None = None) -> None:
    """A settlement. At a private company a player-run empire controls, it raises the pay the empire already sets, so
    its own pay dial and the union agree on one figure; everywhere else it is a deal above the going rate."""
    if bps <= 0:
        return
    if dispute and dispute.get("empire_id") and not company.get("listed", True) and conn.execute(
            "UPDATE private_profiles SET pay_index_bps = pay_index_bps + (pay_index_bps * %s / 10000) WHERE company_id = %s",
            (bps, company["id"])).rowcount:
        return
    conn.execute("UPDATE companies SET union_pay_bps = least(union_pay_bps + %s, %s) WHERE id = %s",
                 (bps, data.UNION_PAY_LIMIT_BPS, company["id"]))


def end_strike(conn: Connection, dispute: dict, now: datetime) -> dict:
    """A strike's last day: the two sides settle halfway between the demand and the offer."""
    union = _one(conn, "SELECT * FROM unions WHERE id = %s", (dispute["union_id"],))
    company = _one(conn, "SELECT id, ticker, name, sector, headquarters, listed FROM companies WHERE id = %s", (dispute["company_id"],))
    settled = (dispute["demand_bps"] + (dispute["offer_bps"] or 0)) // 2 // 25 * 25
    _pay_rise(conn, company, settled, dispute)
    conn.execute("UPDATE union_disputes SET status = 'ended', settled_bps = %s WHERE id = %s", (settled, dispute["id"]))
    news.publish(conn, period=dispute["period"], day=dispute["ends_day"], kind="union_strike_over", story=_story(company, dispute),
                 facts={"union": union["name"], "leader": union["leader"], "company": company["name"], "ticker": company["ticker"],
                        "city": company["headquarters"], "settled": _pct(settled), "days": news.number_word(dispute["strike_days"])},
                 tickers=[company["ticker"]], sectors=[company["sector"]], locations=[company["headquarters"]])
    _tell(conn, dispute, f"The strike at {company['name']} is over after {dispute['strike_days']} game days, settled at {_pct(settled)}.",
          now)
    return {"status": "ended", "settled_bps": settled}


def _work_through(conn: Connection, period: int, day: int, seed: str, now: datetime) -> int:
    """Everything due by this game day of this quarter: deadlines answered and strikes ended. Returns how many."""
    done = 0
    for dispute in _rows(conn, "SELECT d.*, c.name AS company, u.name AS union_name FROM union_disputes d JOIN companies c ON c.id = d.company_id"
                               " JOIN unions u ON u.id = d.union_id WHERE d.period = %s AND d.empire_id IS NOT NULL AND NOT d.told"
                               " AND d.opened_day <= %s ORDER BY d.opened_day, d.id", (period, day)):
        conn.execute("UPDATE union_disputes SET told = true WHERE id = %s", (dispute["id"],))
        _tell(conn, dispute, f"The {dispute['union_name']} demands {_pct(dispute['demand_bps'])} more pay at {dispute['company']}. The head must"
                             f" answer by day {dispute['deadline_day']}, or the staff walk out. See the company's page.", now)
    for dispute in _rows(conn, "SELECT * FROM union_disputes WHERE period = %s AND status = 'open' AND deadline_day <= %s"
                               " ORDER BY deadline_day, id FOR UPDATE SKIP LOCKED", (period, day)):
        decide(conn, dispute, seed, now)
        done += 1
    for dispute in _rows(conn, "SELECT * FROM union_disputes WHERE period = %s AND status = 'struck' AND ends_day <= %s"
                               " ORDER BY ends_day, id FOR UPDATE SKIP LOCKED", (period, day)):
        end_strike(conn, dispute, now)
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


def view(conn: Connection, now: datetime, ticker: str | None = None, player_id=None) -> dict:
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
        striking = d["status"] == "struck" and now_here and (d["decided_day"] or d["deadline_day"]) <= day
        return {"id": d["id"], "union": d["union_name"], "company": d["company"], "ticker": d["ticker"], "city": d["city"],
                "quarter": clock.period_label(d["period"]), "opened_day": d["opened_day"], "deadline_day": d["deadline_day"],
                "demand_bps": d["demand_bps"], "reasons": d["reasons"],
                "offer_bps": d["offer_bps"] if d["status"] != "open" else None,
                "settled_bps": d["settled_bps"], "strike_days": d["strike_days"] if d["status"] != "open" else None,
                "ends_day": d["ends_day"] if d["status"] != "open" else None,
                "status": d["status"], "status_words": "on strike now" if striking else STATUS_WORDS[d["status"]],
                "days_left": max(d["deadline_day"] - day, 0) if d["status"] == "open" and now_here else None,
                "answer": d["answer"], "more_time": d["more_time"], "mediator": bool(d["mediator_fee"]),
                "mediator_worked": d["mediator_worked"] if d["status"] != "open" else None}

    rows = [row(d) for d in shown]
    company = None
    if ticker:
        # One company's union, for its own page (owner, 17 November 2026: no Unions tab; it lives where people look).
        c = _one(conn, "SELECT c.id, c.ticker, c.sector, c.listed, c.union_pay_bps, u.name, u.leader, u.militancy_bps FROM companies c"
                       " LEFT JOIN unions u ON u.sector = c.sector WHERE c.ticker = %s", (ticker.upper(),))
        if c and c["name"]:
            mine = [r for r in rows if r["ticker"] == c["ticker"]]
            boss = controlling_empire(conn, c["id"])
            seat = player_id and _one(conn, "SELECT empire_id FROM empire_seats WHERE player_id = %s", (player_id,))
            ours = bool(boss and seat and seat["empire_id"] == boss["id"])
            for r in mine:
                d = next(x for x in shown if x["id"] == r["id"])
                if ours and d["status"] == "open" and d["period"] == period and d["empire_id"] == boss["id"]:
                    r["table"] = table(conn, d, player_id)
            company = {"empire": boss["name"] if boss else None, "ours": ours,
                       "ticker": c["ticker"], "union": c["name"], "leader": c["leader"], "militancy_bps": c["militancy_bps"],
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


# ---------------------------------------------------------------------------
# Part 2: the empire at the table (owner, 17 November 2026)
# ---------------------------------------------------------------------------

class UnionError(Exception):
    """Something a player asked for that cannot be done, in plain words."""


def _today(conn: Connection, now: datetime) -> tuple[int, int, str]:
    from simulation import careers
    world = careers.world_now(conn, now)
    state = _one(conn, "SELECT last_closed_period, fortune_seed FROM world_state")
    if not world["started"] or state is None or world["period"] != state["last_closed_period"] + 1:
        raise UnionError("The quarter is closing. Try again once it has closed.")
    return world["period"], world["day"], state["fortune_seed"]


def _at_the_table(conn: Connection, player_id, dispute_id: int, now: datetime, *, head: bool = True) -> tuple[dict, int, str]:
    """The open dispute a player may act on: made public, before its deadline, at a company their empire controls."""
    period, day, seed = _today(conn, now)
    dispute = _one(conn, "SELECT * FROM union_disputes WHERE id = %s FOR UPDATE", (dispute_id,))
    if dispute is None or dispute["period"] != period or dispute["opened_day"] > day:
        raise UnionError("There is no such demand.")
    boss = controlling_empire(conn, dispute["company_id"])
    seat = _one(conn, "SELECT empire_id, build FROM empire_seats WHERE player_id = %s", (player_id,))
    if boss is None or boss["id"] != dispute["empire_id"] or seat is None or seat["empire_id"] != boss["id"]:
        raise UnionError("Only the empire that controls this company sits at this table.")
    if head and boss["head_player_id"] != player_id:
        raise UnionError("Only the empire's head answers the union.")
    if dispute["status"] != "open":
        raise UnionError("This demand has already been answered.")
    if day > dispute["deadline_day"]:
        raise UnionError("The deadline has passed.")
    return {**dispute, "seat_build": seat["build"]}, day, seed


def answer(conn: Connection, player_id, dispute_id: int, choice: str, offer_bps: int | None, now: datetime) -> dict:
    """The head answers: agree to the full demand, offer less, or refuse. The union replies at once."""
    with conn.transaction():
        dispute, day, seed = _at_the_table(conn, player_id, dispute_id, now)
        if choice == "agree":
            offer = dispute["demand_bps"]
        elif choice == "refuse":
            offer = 0
        elif choice == "offer":
            if offer_bps is None or not 0 < offer_bps < dispute["demand_bps"]:
                raise UnionError(f"An offer is more than nothing and less than the {_pct(dispute['demand_bps'])} asked. To give it all, agree.")
            offer = offer_bps // 5 * 5
        else:
            raise UnionError("Agree, offer less, or refuse.")
        return decide(conn, dispute, seed, now, offer=offer, answer=choice, by=player_id, day=day)


def more_time(conn: Connection, player_id, dispute_id: int, now: datetime) -> dict:
    """The head asks the union for a few more days, once a dispute. A leader quick to strike may say no."""
    with conn.transaction():
        dispute, _day, seed = _at_the_table(conn, player_id, dispute_id, now)
        if dispute["more_time"]:
            raise UnionError("You have already asked for more time on this demand.")
        union = _one(conn, "SELECT * FROM unions WHERE id = %s", (dispute["union_id"],))
        later = dispute["deadline_day"] + data.UNION_MORE_TIME_DAYS
        refuses = _unit(seed, "more-time", dispute["id"]) * BPS < union["militancy_bps"] - 5000
        if later > data.UNION_LAST_DEADLINE_DAY or refuses:
            conn.execute("UPDATE union_disputes SET more_time = 'refused' WHERE id = %s", (dispute["id"],))
            words = f"{union['leader']} refused more time. The deadline stays day {dispute['deadline_day']}."
            _tell(conn, dispute, words, now)
            return {"granted": False, "deadline_day": dispute["deadline_day"], "words": words}
        conn.execute("UPDATE union_disputes SET more_time = 'granted', deadline_day = %s WHERE id = %s", (later, dispute["id"]))
        words = f"{union['leader']} gave {data.UNION_MORE_TIME_DAYS} more game days. The deadline is now day {later}."
        _tell(conn, dispute, words, now)
        return {"granted": True, "deadline_day": later, "words": words}


def mediator_fee(conn: Connection, company_id) -> int:
    last = _one(conn, "SELECT revenue FROM company_results WHERE company_id = %s ORDER BY period DESC LIMIT 1", (company_id,))
    low, high = data.UNION_MEDIATOR_FEE_NAIRA
    return min(max(apply_bps((last or {}).get("revenue", 0) or 0, data.UNION_MEDIATOR_FEE_BPS), low * 100), high * 100)


def hire_mediator(conn: Connection, player_id, dispute_id: int, now: datetime) -> dict:
    """The head hires an outside mediator, paid from the empire's account. Most of the time the mediator talks the union
    into taking less than it would alone; not always. Whether it worked shows when the union answers."""
    from simulation import ledger
    from simulation.ledger import Leg
    with conn.transaction():
        dispute, _day, _seed = _at_the_table(conn, player_id, dispute_id, now)
        if dispute["mediator_fee"]:
            raise UnionError("A mediator is already working on this demand.")
        boss = controlling_empire(conn, dispute["company_id"])
        fee = mediator_fee(conn, dispute["company_id"])
        if ledger.balance(conn, boss["account_id"]) < fee:
            raise UnionError("The empire's account cannot pay the mediator's fee.")
        ledger.post(conn, kind="union_mediator", memo=f"Mediator's fee: the pay demand at dispute {dispute_id}",
                    reference=f"union:{dispute_id}", idempotency_key=f"union-mediator:{dispute_id}",
                    legs=[Leg(boss["account_id"], -fee), Leg(ledger.account_id(conn, ledger.INVESTORS_PUBLIC), fee)])
        conn.execute("UPDATE union_disputes SET mediator_fee = %s WHERE id = %s", (fee, dispute["id"]))
        _tell(conn, dispute, f"The head hired a mediator for the pay demand ({_pct(dispute['demand_bps'])}), for a fee of {fee // 100:,} naira.", now)
        return {"fee": fee}


def advise(conn: Connection, player_id, dispute_id: int, advice: str, offer_bps: int | None, note: str, now: datetime) -> None:
    """A member of the empire puts their advice on record for the head."""
    if advice not in ("agree", "offer", "refuse"):
        raise UnionError("Advise agree, offer, or refuse.")
    note = " ".join((note or "").split())
    if len(note) > 300:
        raise UnionError("A note is at most 300 characters.")
    with conn.transaction():
        dispute, _day, _seed = _at_the_table(conn, player_id, dispute_id, now, head=False)
        if advice == "offer" and (offer_bps is None or not 0 < offer_bps < dispute["demand_bps"]):
            raise UnionError(f"An offer is more than nothing and less than the {_pct(dispute['demand_bps'])} asked.")
        conn.execute("INSERT INTO union_advice (dispute_id, player_id, build, advice, offer_bps, note, at) VALUES (%s, %s, %s, %s, %s, %s, %s)"
                     " ON CONFLICT (dispute_id, player_id) DO UPDATE SET build = excluded.build, advice = excluded.advice,"
                     " offer_bps = excluded.offer_bps, note = excluded.note, at = excluded.at",
                     (dispute_id, player_id, dispute["seat_build"], advice, offer_bps if advice == "offer" else None, note or None, now))
        from simulation import pings
        pings.ping(conn, "chat", dispute["empire_id"])


BUILD_WORDS = {"risk_manager": "Risk Manager", "investment_banker": "Investment Banker", "asset_manager": "Asset Manager"}


def table(conn: Connection, dispute: dict, player_id) -> dict:
    """What the empire sees at the table: the trade-off in naira, and each build's view."""
    company = _one(conn, "SELECT id, ticker, name, listed, union_pay_bps FROM companies WHERE id = %s", (dispute["company_id"],))
    union = _one(conn, "SELECT * FROM unions WHERE id = %s", (dispute["union_id"],))
    last = _one(conn, "SELECT revenue, wages, net_profit FROM company_results WHERE company_id = %s ORDER BY period DESC LIMIT 1",
                (company["id"],)) or {"revenue": 0, "wages": 0, "net_profit": 0}
    low, high = data.UNION_STRIKE_DAYS
    middle = (low + high) // 2

    def strike(days: int) -> int:
        return apply_bps(last["revenue"] * days // clock.GAME_DAYS_PER_QUARTER, data.UNION_MARGIN_BPS)

    def two_years(bps: int) -> int:
        return apply_bps(last["wages"], bps) * data.UNION_TWO_YEARS_QUARTERS // 10

    fair = _board_offer(conn, dispute, company)
    from simulation import private
    value = private.value_of(conn, company["id"])
    stake = _one(conn, "SELECT cost FROM company_stakes WHERE company_id = %s AND empire_id = %s", (company["id"], dispute["empire_id"]))
    wage = _one(conn, "SELECT wage_index_bps FROM economy_results ORDER BY period DESC LIMIT 1")
    profile = _one(conn, "SELECT pay_index_bps, morale_bps FROM private_profiles WHERE company_id = %s", (company["id"],))
    ratio = profile["pay_index_bps"] * BPS // max(wage["wage_index_bps"], 1) if profile and wage else BPS + (company["union_pay_bps"] or 0)
    history = _one(conn, "SELECT count(*) AS disputes, count(*) FILTER (WHERE strike_days IS NOT NULL) AS strikes FROM union_disputes"
                         " WHERE union_id = %s AND period >= %s", (union["id"], dispute["period"] - 4))
    advice = _rows(conn, "SELECT a.*, p.display_name FROM union_advice a JOIN players p ON p.id = a.player_id WHERE a.dispute_id = %s"
                         " ORDER BY a.at", (dispute["id"],))
    boss = controlling_empire(conn, company["id"])
    return {
        "is_head": bool(boss and boss["head_player_id"] == player_id),
        "wages_quarter": last["wages"], "sales_quarter": last["revenue"],
        "risk": {"strike_short": strike(low), "strike_middle": strike(middle), "strike_long": strike(high),
                 "rise_two_years": two_years(dispute["demand_bps"]), "fair_bps": fair, "fair_two_years": two_years(fair),
                 "days": [low, middle, high]},
        "banker": {"value": value, "strike_share_bps": strike(middle) * BPS // value if value > 0 else None,
                   "profit_quarter": last["net_profit"]},
        "asset": {"pay_vs_going_bps": ratio - BPS, "morale_bps": profile["morale_bps"] if profile else None,
                  "stake_cost": stake["cost"] if stake else None, "union_disputes": history["disputes"], "union_strikes": history["strikes"],
                  "temper_bps": union["militancy_bps"]},
        "more_time": dispute["more_time"], "can_more_time": dispute["more_time"] is None,
        "mediator_fee": dispute["mediator_fee"], "mediator_quote": mediator_fee(conn, company["id"]),
        "advice": [{"name": a["display_name"], "build": BUILD_WORDS.get(a["build"], a["build"]), "advice": a["advice"],
                    "offer_bps": a["offer_bps"], "note": a["note"], "mine": a["player_id"] == player_id} for a in advice],
    }


def waiting(conn: Connection, player_id, now: datetime) -> list[dict]:
    """The demands this player must answer as an empire's head: made public, not yet answered, before the deadline."""
    from simulation import careers
    world = careers.world_now(conn, now)
    if not world["started"]:
        return []
    return [{"ticker": r["ticker"], "company": r["name"], "demand_bps": r["demand_bps"], "days_left": max(r["deadline_day"] - world["day"], 0)}
            for r in _rows(conn, "SELECT c.ticker, c.name, d.demand_bps, d.deadline_day FROM union_disputes d JOIN companies c ON c.id = d.company_id"
                                 " JOIN empires e ON e.id = d.empire_id JOIN owned_companies o ON o.company_id = d.company_id AND o.empire_id = e.id"
                                 " WHERE e.head_player_id = %s AND e.kind = 'player' AND d.status = 'open' AND d.period = %s"
                                 " AND d.opened_day <= %s AND d.deadline_day >= %s ORDER BY d.deadline_day",
                           (player_id, world["period"], world["day"], world["day"]))]
