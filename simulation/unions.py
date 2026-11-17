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
    if _one(conn, "SELECT to_regclass('union_bribes') IS NOT NULL AS ok")["ok"]:
        tell_at_close(conn, period, seed, now)            # part 3: leaders paid this quarter may tell
    conn.execute("UPDATE companies SET union_pay_bps = union_pay_bps - (union_pay_bps * %s / 10000) WHERE union_pay_bps > 0",
                 (data.UNION_PAY_CATCH_UP_BPS,))
    squeeze = _squeeze(conn, period)
    unions = {u["sector"]: u for u in _rows(conn, "SELECT * FROM unions")}
    lodged = []
    # Every company's staff weigh up the quarter first, so that an industry where most are angry at once acts as one.
    by_sector: dict[str, list] = {}
    for company in _rows(conn, "SELECT id, ticker, name, sector, headquarters, listed, union_pay_bps FROM companies c"
                               " WHERE status = 'trading' AND (listed OR EXISTS (SELECT 1 FROM private_profiles p WHERE p.company_id = c.id))"
                               " ORDER BY ticker"):
        union = unions.get(company["sector"])
        if union is None or not decides_strikes(company):
            continue
        points, why = anger(conn, company, period, squeeze, union["militancy_bps"])
        by_sector.setdefault(company["sector"], []).append((company, points, why))
    waves = waves_ready(conn)
    for sector, staffs in by_sector.items():
        union = unions[sector]
        angry = [(c, p, w) for c, p, w in staffs if p >= data.UNION_DISPUTE_AT_BPS]
        wave = None
        if waves and len(angry) >= data.UNION_WAVE_MIN_COMPANIES and len(angry) * BPS >= len(staffs) * data.UNION_WAVE_SHARE_BPS:
            wave = _lodge_wave(conn, union, staffs, angry, period, seed)
        for company, points, why in angry:
            boss = controlling_empire(conn, company["id"])
            if wave and boss is None:
                continue                                  # the wave speaks for it
            demand = wave["demand_bps"] if wave else min(max(points // 5 // 50 * 50, data.UNION_DEMAND_MIN_BPS), data.UNION_DEMAND_MAX_BPS)
            opened = wave["opened_day"] if wave else 2 + int(_unit(seed, period + 1, company["ticker"], "opened") * 60)
            deadline = wave["deadline_day"] if wave else opened + data.UNION_NOTICE_DAYS
            row = _one(conn, "INSERT INTO union_disputes (union_id, company_id, period, opened_day, deadline_day, anger_bps, reasons,"
                             " demand_bps, empire_id, wave_id) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
                             " ON CONFLICT (company_id, period) DO NOTHING RETURNING id",
                       (union["id"], company["id"], period + 1, opened, deadline, points, Jsonb(why), demand, boss and boss["id"],
                        wave and wave["id"]))
            if row is None or wave:
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
    if waves:
        _maybe_general_strike(conn, period, squeeze, seed, now)
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
    if dispute.get("hardline"):
        return dispute["demand_bps"]                      # a rival paid the leader: only the full demand will do
    if dispute.get("softened"):
        need = dispute["demand_bps"] // 2                 # the owner paid the leader: half will do
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
    if waves_ready(conn):                                 # part 4: industry-wide demands and the general strike
        done += _work_waves(conn, period, day, seed, now)
        done += _work_general(conn, period, day, now)
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
            quiet = None
            head = player_id and _one(conn, "SELECT id FROM empires WHERE head_player_id = %s AND kind = 'player' AND status = 'active'",
                                      (player_id,))
            can_settle = any(r["status"] == "open" for r in mine if r["quarter"] == clock.period_label(period))
            if head and boss and ready_bribes(conn) and (boss["id"] != head["id"] or can_settle):
                quiet = {"kind": "calm" if boss["id"] == head["id"] else "strike", "price": bribe_price(conn, c["id"]),
                         "tell_bps": tell_chance(conn, head["id"]), "refuse_bps": data.UNION_BRIBE_REFUSE_BPS}
            member_wave = waves_ready(conn) and _one(
                conn, "SELECT w.id FROM union_wave_members m JOIN union_waves w ON w.id = m.wave_id WHERE m.company_id = %s"
                      " AND w.period = %s AND w.opened_day <= %s", (c["id"], period, day))
            company = {"empire": boss["name"] if boss else None, "ours": ours, "quiet_word": quiet,
                       "wave_id": member_wave["id"] if member_wave else None,
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
        "waves": [{"id": w["id"], "union": w["union_name"], "industry": w["industry"], "quarter": clock.period_label(w["period"]),
                   "opened_day": w["opened_day"], "deadline_day": w["deadline_day"], "demand_bps": w["demand_bps"], "companies": w["companies"],
                   "reasons": w["reasons"], "status": w["status"], "offer_bps": w["offer_bps"] if w["status"] != "open" else None,
                   "settled_bps": w["settled_bps"], "strike_days": w["strike_days"] if w["status"] != "open" else None,
                   "ends_day": w["ends_day"] if w["status"] != "open" else None,
                   "days_left": max(w["deadline_day"] - day, 0) if w["status"] == "open" and w["period"] == period else None,
                   "striking": w["status"] == "struck" and w["period"] == period}
                  for w in (_rows(conn, "SELECT w.*, u.name AS union_name, lower(s.name) AS industry FROM union_waves w JOIN unions u ON u.id = w.union_id"
                                        " JOIN sectors s ON s.code = u.sector WHERE w.period >= %s AND (w.period < %s OR w.opened_day <= %s)"
                                        " ORDER BY w.period DESC, w.opened_day DESC", (period - 4, period, day)) if waves_ready(conn) else [])],
        "general": general_view(conn, player_id, now),
        "exposed": [{"empire": r["empire"], "company": r["company"], "ticker": r["ticker"], "union": r["union_name"], "kind": r["kind"],
                     "how": r["exposed_how"], "quarter": clock.period_label(r["period"])} for r in (_rows(
            conn, "SELECT b.kind, b.exposed_how, b.period, e.name AS empire, c.name AS company, c.ticker, u.name AS union_name"
                  " FROM union_bribes b JOIN empires e ON e.id = b.empire_id JOIN companies c ON c.id = b.company_id JOIN unions u ON u.id = b.union_id"
                  " WHERE b.exposed_how IS NOT NULL ORDER BY b.exposed_at DESC LIMIT 20") if ready_bribes(conn) else [])],
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


# ---------------------------------------------------------------------------
# Part 3: union crimes (owner, 17 November 2026)
# ---------------------------------------------------------------------------

def bribe_price(conn: Connection, company_id) -> int:
    last = _one(conn, "SELECT revenue FROM company_results WHERE company_id = %s ORDER BY period DESC LIMIT 1", (company_id,))
    return max(apply_bps((last or {}).get("revenue", 0) or 0, data.UNION_BRIBE_PRICE_BPS), data.UNION_BRIBE_PRICE_NAIRA * 100)


def tell_chance(conn: Connection, empire_id) -> int:
    """The chance a leader who took this empire's money tells: low the first time, higher with every bribe before."""
    before = _one(conn, "SELECT count(*) AS n FROM union_bribes WHERE empire_id = %s AND NOT refused", (empire_id,))["n"]
    return min(data.UNION_TELL_BASE_BPS + data.UNION_TELL_PER_REPEAT_BPS * before, data.UNION_TELL_MOST_BPS)


def _head_of(conn: Connection, player_id) -> dict:
    empire = _one(conn, "SELECT * FROM empires WHERE head_player_id = %s AND kind = 'player' AND status = 'active'", (player_id,))
    if empire is None:
        raise UnionError("Only the head of an empire run by players can do that.")
    return empire


def bribe(conn: Connection, player_id, ticker: str, kind: str, now: datetime) -> dict:
    """The head pays a union leader in secret: 'strike' to make trouble at a rival empire's company, 'calm' to settle at
    one of their own. A crime, and only between players: never against a company the computer runs."""
    from simulation import ledger
    from simulation.ledger import Leg
    if kind not in ("strike", "calm"):
        raise UnionError("Pay a leader to make trouble or to settle.")
    with conn.transaction():
        period, day, seed = _today(conn, now)
        empire = _head_of(conn, player_id)
        company = _one(conn, "SELECT id, ticker, name, sector, headquarters, listed FROM companies WHERE ticker = %s AND status = 'trading'",
                       ((ticker or "").upper(),))
        if company is None or not decides_strikes(company):
            raise UnionError("There is no union there to pay.")
        boss = controlling_empire(conn, company["id"])
        if kind == "strike" and (boss is None or boss["id"] == empire["id"]):
            raise UnionError("You can only make trouble at a company another empire run by players controls.")
        if kind == "calm" and (boss is None or boss["id"] != empire["id"]):
            raise UnionError("You can only buy calm at a company your empire controls.")
        if _one(conn, "SELECT 1 AS x FROM union_bribes WHERE empire_id = %s AND company_id = %s AND period = %s AND NOT refused",
                (empire["id"], company["id"], period)):
            raise UnionError("You have already paid this leader this quarter.")
        dispute = _one(conn, "SELECT * FROM union_disputes WHERE company_id = %s AND period = %s FOR UPDATE", (company["id"], period))
        if kind == "calm" and (dispute is None or dispute["status"] != "open" or dispute["opened_day"] > day):
            raise UnionError("There is no open demand there to settle.")
        if kind == "strike" and dispute and dispute["status"] != "open":
            raise UnionError("This quarter's dispute there is already over.")
        if kind == "strike" and dispute is None and day > data.UNION_BRIBE_LATEST_DAY:
            raise UnionError("Too late in the quarter to stir up a demand. Try after the close.")
        union = _one(conn, "SELECT * FROM unions WHERE sector = %s", (company["sector"],))
        price = bribe_price(conn, company["id"])
        chance = tell_chance(conn, empire["id"])
        row = _one(conn, "INSERT INTO union_bribes (empire_id, payer_id, union_id, company_id, victim_empire_id, kind, amount, period,"
                         " tell_bps, at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING *",
                   (empire["id"], player_id, union["id"], company["id"], boss["id"] if kind == "strike" else None, kind, price, period, chance, now))
        if _unit(seed, "bribe-refused", row["id"]) * BPS < data.UNION_BRIBE_REFUSE_BPS:
            conn.execute("UPDATE union_bribes SET refused = true WHERE id = %s", (row["id"],))
            _expose(conn, {**row, "refused": True}, "refused", now)
            return {"taken": False, "words": f"{union['leader']} refused the money, and has told the papers."}
        if ledger.balance(conn, empire["account_id"]) < price:
            raise UnionError("The empire's account cannot pay what the leader asks.")
        ledger.post(conn, kind="consultancy", memo=f"Consultancy fee: labour relations, {company['name']}", reference=f"union-bribe:{row['id']}",
                    idempotency_key=f"union-bribe:{row['id']}",
                    legs=[Leg(empire["account_id"], -price), Leg(ledger.account_id(conn, ledger.INVESTORS_PUBLIC), price)])
        if kind == "calm":
            conn.execute("UPDATE union_disputes SET softened = true WHERE id = %s", (dispute["id"],))
            words = f"{union['leader']} took it. The union will settle for half of what it asked."
        elif dispute:
            conn.execute("UPDATE union_disputes SET hardline = true WHERE id = %s", (dispute["id"],))
            words = f"{union['leader']} took it. At {company['name']} only the full {_pct(dispute['demand_bps'])} will do now."
        else:
            demand = max(data.UNION_DEMAND_MAX_BPS * 2 // 3 // 50 * 50, data.UNION_DEMAND_MIN_BPS)
            dispute = _one(conn, "INSERT INTO union_disputes (union_id, company_id, period, opened_day, deadline_day, anger_bps, reasons,"
                                 " demand_bps, empire_id, hardline, told) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, true, false) RETURNING *",
                           (union["id"], company["id"], period, day + 1, day + 1 + data.UNION_NOTICE_DAYS, data.UNION_DISPUTE_AT_BPS,
                            Jsonb(["Its staff say their pay has fallen behind."]), demand, boss["id"]))
            news.publish(conn, period=period, day=day + 1, kind="union_demand", story=f"union:{company['ticker']}:{period}",
                         facts={"union": union["name"], "leader": union["leader"], "company": company["name"], "ticker": company["ticker"],
                                "city": company["headquarters"], "demand": _pct(demand), "days": news.number_word(data.UNION_NOTICE_DAYS),
                                "grievance": "Its staff say their pay has fallen behind."},
                         tickers=[company["ticker"]], sectors=[company["sector"]], locations=[company["headquarters"]])
            words = f"{union['leader']} took it. A demand of {_pct(demand)} goes to {company['name']} tomorrow, and only the full rise will do."
        conn.execute("UPDATE union_bribes SET dispute_id = %s WHERE id = %s", (dispute["id"], row["id"]))
        return {"taken": True, "paid": price, "words": words}


def _expose(conn: Connection, b: dict, how: str, now: datetime) -> None:
    """A bribe comes out: the news, the empire's standing, and a record the tribunal can hear."""
    from simulation import standing
    conn.execute("UPDATE union_bribes SET exposed_how = %s, exposed_at = %s WHERE id = %s AND exposed_how IS NULL", (how, now, b["id"]))
    empire = _one(conn, "SELECT id, name FROM empires WHERE id = %s", (b["empire_id"],))
    company = _one(conn, "SELECT ticker, name, sector, headquarters FROM companies WHERE id = %s", (b["company_id"],))
    union = _one(conn, "SELECT name, leader FROM unions WHERE id = %s", (b["union_id"],))
    from simulation import careers
    world = careers.world_now(conn, now)
    what = {"strike": "to make trouble for its owners", "calm": "to settle cheaply"}[b["kind"]]
    news.publish(conn, period=world["period"], day=world["day"], kind="union_bribe_exposed", story=f"union-bribe:{b['id']}",
                 facts={"empire": empire["name"], "company": company["name"], "ticker": company["ticker"], "city": company["headquarters"],
                        "union": union["name"], "leader": union["leader"], "purpose": what,
                        "exposed_by": {"refused": "refused the money and went public", "leader": "has admitted taking money",
                                "journalist": "was paid, an investigation has found"}[how]},
                 tickers=[company["ticker"]], sectors=[company["sector"]], locations=[company["headquarters"]], boost=12)
    standing.change(conn, empire["id"], -data.UNION_BRIBE_REPUTATION, f"It paid the {union['name']}'s leader", world["period"], now)
    conn.execute("INSERT INTO empire_events (empire_id, words, at) VALUES (%s, %s, %s)",
                 (empire["id"], f"It has come out that the empire paid the {union['name']}'s leader at {company['name']}.", now))


def tell_at_close(conn: Connection, period: int, seed: str, now: datetime) -> int:
    """At the quarter's close the leaders paid in it decide whether to tell: the chance fixed when each was paid."""
    told = 0
    for b in _rows(conn, "SELECT * FROM union_bribes WHERE period = %s AND NOT refused AND exposed_how IS NULL", (period,)):
        if _unit(seed, "bribe-told", b["id"]) * BPS < b["tell_bps"]:
            _expose(conn, b, "leader", now)
            told += 1
    return told


def hidden_bribes(conn: Connection, empire_id) -> list[int]:
    """For a journalist's file: bribes this empire paid that have not come out."""
    return [r["id"] for r in _rows(conn, "SELECT id FROM union_bribes WHERE empire_id = %s AND NOT refused AND exposed_how IS NULL ORDER BY id",
                                  (empire_id,))]


def still_hidden(conn: Connection, bribe_id: int) -> bool:
    return bool(_one(conn, "SELECT 1 AS x FROM union_bribes WHERE id = %s AND exposed_how IS NULL", (bribe_id,)))


def expose_by_journalist(conn: Connection, bribe_id: int, now: datetime) -> dict:
    b = _one(conn, "SELECT * FROM union_bribes WHERE id = %s FOR UPDATE", (bribe_id,))
    _expose(conn, b, "journalist", now)
    union = _one(conn, "SELECT name FROM unions WHERE id = %s", (b["union_id"],))
    company = _one(conn, "SELECT name FROM companies WHERE id = %s", (b["company_id"],))
    return {"union": union["name"], "company": company["name"], "kind": b["kind"]}


def harm(conn: Connection, b: dict) -> int:
    """What a bribe cost its victim, for the tribunal: the lost profit of a strike it hardened, or else what was paid."""
    if b["kind"] == "strike" and b["dispute_id"]:
        d = _one(conn, "SELECT strike_days, company_id FROM union_disputes WHERE id = %s", (b["dispute_id"],))
        if d and d["strike_days"]:
            last = _one(conn, "SELECT revenue FROM company_results WHERE company_id = %s ORDER BY period DESC LIMIT 1", (d["company_id"],))
            lost = apply_bps((last or {}).get("revenue", 0) * d["strike_days"] // clock.GAME_DAYS_PER_QUARTER, data.UNION_MARGIN_BPS)
            return max(lost, b["amount"])
    return b["amount"]


def wrongs(conn: Connection, since: datetime, now: datetime) -> list[dict]:
    """Bribes that have come out, as wrongs the tribunal can hear. The empire that was hit may bring a bribe to make trouble;
    the regulator may bring either kind."""
    if not _one(conn, "SELECT to_regclass('union_bribes') IS NOT NULL AS ok")["ok"]:
        return []
    out = []
    for b in _rows(conn, "SELECT b.*, c.ticker, u.name AS union_name, e.head_player_id AS victim_head FROM union_bribes b"
                         " JOIN companies c ON c.id = b.company_id JOIN unions u ON u.id = b.union_id"
                         " LEFT JOIN empires e ON e.id = b.victim_empire_id"
                         " WHERE NOT b.refused AND b.exposed_how IS NOT NULL AND b.at >= %s ORDER BY b.id", (since,)):
        amount = harm(conn, b)
        out.append({"kind": "union_bribery", "key": f"union_bribery:{b['id']}", "defendant_id": b["payer_id"], "company_id": b["company_id"],
                    "ticker": b["ticker"], "amount": amount, "victim_player": b["victim_head"],
                    "lines": [{"what": f"Paid {b['amount'] // 100:,} naira as a 'consultancy fee' to the leader of the {b['union_name']}"},
                              {"what": "to make trouble at a rival's company" if b["kind"] == "strike" else "to settle a pay demand cheaply"}],
                    "words": f"Paid the {b['union_name']}'s leader in secret, " + ("to make trouble at a rival empire's company."
                                                                                   if b["kind"] == "strike" else "to settle a pay demand cheaply.")})
    return out


def ready_bribes(conn: Connection) -> bool:
    return _one(conn, "SELECT to_regclass('union_bribes') IS NOT NULL AS ok")["ok"]


# ---------------------------------------------------------------------------
# Part 4: strike waves and the general strike (owner, 17 November 2026)
# ---------------------------------------------------------------------------

def waves_ready(conn: Connection) -> bool:
    return _one(conn, "SELECT to_regclass('general_strikes') IS NOT NULL AS ok")["ok"]


def moment_of(conn: Connection, period: int, day: int) -> datetime:
    """The real time a game day of a quarter begins."""
    from datetime import timedelta
    world = _one(conn, "SELECT world_start, weeks_ahead FROM world_state")
    start = clock.effective_start(world["world_start"], world["weeks_ahead"])
    return start + timedelta(weeks=period - 1) + timedelta(weeks=1) * (day - 1) / clock.GAME_DAYS_PER_QUARTER


def _members(conn: Connection, sector: str) -> list[dict]:
    """The employers in an industry the computer runs: every trading company there no player-run empire controls."""
    return [c for c in _rows(conn, "SELECT id, ticker, name, sector, headquarters, listed FROM companies c WHERE sector = %s AND status = 'trading'"
                                   " AND (listed OR EXISTS (SELECT 1 FROM private_profiles p WHERE p.company_id = c.id)) ORDER BY ticker", (sector,))
            if controlling_empire(conn, c["id"]) is None]


def _lodge_wave(conn: Connection, union: dict, staffs: list, angry: list, period: int, seed: str) -> dict | None:
    """Most of an industry's staff are angry at once: one industry-wide demand, answered by the employers together."""
    members = _members(conn, union["sector"])
    if not members:
        return None
    demands = sorted(min(max(p // 5 // 50 * 50, data.UNION_DEMAND_MIN_BPS), data.UNION_DEMAND_MAX_BPS) for _c, p, _w in angry)
    demand = demands[len(demands) // 2]
    opened = 2 + int(_unit(seed, period + 1, union["sector"], "wave") * 50)
    points = sum(p for _c, p, _w in angry) // len(angry)
    why = [f"Staff are angry at {len(angry)} of the industry's {len(staffs)} employers."] + sorted({w[0] for _c, _p, w in angry if w})[:2]
    wave = _one(conn, "INSERT INTO union_waves (union_id, period, opened_day, deadline_day, companies, anger_bps, reasons, demand_bps)"
                      " VALUES (%s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (union_id, period) DO NOTHING RETURNING *",
                (union["id"], period + 1, opened, opened + data.UNION_WAVE_NOTICE_DAYS, len(members), points, Jsonb(why), demand))
    if wave is None:
        return None
    for c in members:
        conn.execute("INSERT INTO union_wave_members (wave_id, company_id) VALUES (%s, %s)", (wave["id"], c["id"]))
    sector = _one(conn, "SELECT name FROM sectors WHERE code = %s", (union["sector"],))["name"]
    news.publish(conn, period=period + 1, day=opened, kind="union_wave_demand", story=f"wave:{union['sector']}:{period + 1}",
                 facts={"union": union["name"], "leader": union["leader"], "industry": sector.lower(), "demand": _pct(demand),
                        "companies": news.number_word(len(members)), "days": news.number_word(data.UNION_WAVE_NOTICE_DAYS)},
                 sectors=[union["sector"]], boost=10)
    return wave


def decide_wave(conn: Connection, wave: dict, seed: str, now: datetime) -> dict:
    """The deadline: the employers the computer runs answer together, each by the board's rule, and the industry's offer is
    the middle one. The union takes it, or the whole industry walks out."""
    union = _one(conn, "SELECT * FROM unions WHERE id = %s", (wave["union_id"],))
    members = _rows(conn, "SELECT c.id, c.ticker, c.name, c.sector, c.headquarters, c.listed FROM union_wave_members m"
                          " JOIN companies c ON c.id = m.company_id WHERE m.wave_id = %s ORDER BY c.ticker", (wave["id"],))
    offers = sorted(_board_offer(conn, wave, c) for c in members) or [0]
    offer = offers[len(offers) // 2]
    sector = _one(conn, "SELECT name FROM sectors WHERE code = %s", (union["sector"],))["name"].lower()
    facts = {"union": union["name"], "leader": union["leader"], "industry": sector, "demand": _pct(wave["demand_bps"]), "offer": _pct(offer),
             "companies": news.number_word(len(members))}
    story = f"wave:{union['sector']}:{wave['period']}"
    if offer >= wave["demand_bps"] or _union_takes(wave, union, offer, seed):
        for c in members:
            _pay_rise(conn, c, offer)
        conn.execute("UPDATE union_waves SET status = 'agreed', offer_bps = %s, settled_bps = %s, decided_at = %s WHERE id = %s",
                     (offer, offer, now, wave["id"]))
        news.publish(conn, period=wave["period"], day=wave["deadline_day"], kind="union_wave_deal", story=story,
                     facts={**facts, "settled": _pct(offer)}, sectors=[union["sector"]])
        return {"status": "agreed", "settled_bps": offer}
    days = _strike_days(seed, wave, union, union["sector"])
    lost = -min(days * BPS // clock.GAME_DAYS_PER_QUARTER, 5000)
    for c in members:
        event = _one(conn, "INSERT INTO events (period, day, kind, location, sector, company_id, sales_bps, facts)"
                           " VALUES (%s, %s, 'company_strike', %s, %s, %s, %s, %s) RETURNING id",
                     (wave["period"], wave["deadline_day"], c["headquarters"], c["sector"], c["id"], lost,
                      Jsonb({"company": c["name"], "ticker": c["ticker"], "location": c["headquarters"], "union": union["name"],
                             "days": days, "wave": wave["id"]})))
        conn.execute("UPDATE union_wave_members SET event_id = %s WHERE wave_id = %s AND company_id = %s", (event["id"], wave["id"], c["id"]))
    conn.execute("UPDATE union_waves SET status = 'struck', offer_bps = %s, strike_days = %s, ends_day = %s, decided_at = %s WHERE id = %s",
                 (offer, days, min(wave["deadline_day"] + days, clock.GAME_DAYS_PER_QUARTER), now, wave["id"]))
    news.publish(conn, period=wave["period"], day=wave["deadline_day"], kind="union_wave_strike", story=story,
                 facts={**facts, "days": news.number_word(days)}, sectors=[union["sector"]], boost=min(days + 5, 20))
    return {"status": "struck", "strike_days": days}


def end_wave(conn: Connection, wave: dict) -> dict:
    union = _one(conn, "SELECT * FROM unions WHERE id = %s", (wave["union_id"],))
    settled = (wave["demand_bps"] + (wave["offer_bps"] or 0)) // 2 // 25 * 25
    for c in _rows(conn, "SELECT c.id, c.listed FROM union_wave_members m JOIN companies c ON c.id = m.company_id WHERE m.wave_id = %s",
                   (wave["id"],)):
        _pay_rise(conn, c, settled)
    conn.execute("UPDATE union_waves SET status = 'ended', settled_bps = %s WHERE id = %s", (settled, wave["id"]))
    sector = _one(conn, "SELECT name FROM sectors WHERE code = %s", (union["sector"],))["name"].lower()
    news.publish(conn, period=wave["period"], day=wave["ends_day"], kind="union_wave_over", story=f"wave:{union['sector']}:{wave['period']}",
                 facts={"union": union["name"], "leader": union["leader"], "industry": sector, "settled": _pct(settled),
                        "days": news.number_word(wave["strike_days"])}, sectors=[union["sector"]])
    return {"status": "ended", "settled_bps": settled}


def _work_waves(conn: Connection, period: int, day: int, seed: str, now: datetime) -> int:
    done = 0
    for wave in _rows(conn, "SELECT * FROM union_waves WHERE period = %s AND status = 'open' AND deadline_day <= %s ORDER BY deadline_day, id"
                            " FOR UPDATE SKIP LOCKED", (period, day)):
        decide_wave(conn, wave, seed, now)
        done += 1
    for wave in _rows(conn, "SELECT * FROM union_waves WHERE period = %s AND status = 'struck' AND ends_day <= %s ORDER BY ends_day, id"
                            " FOR UPDATE SKIP LOCKED", (period, day)):
        end_wave(conn, wave)
        done += 1
    return done


# --- The general strike -------------------------------------------------------

def _household_income(conn: Connection, period: int) -> int:
    row = _one(conn, "SELECT coalesce(sum(income), 0)::bigint AS n FROM household_results WHERE period = %s", (period,))
    return row["n"] if row else 0


def _maybe_general_strike(conn: Connection, period: int, squeeze: int, seed: str, now: datetime) -> dict | None:
    """Rarely: prices have outrun pay hard and several industries are out at once. The federation gives notice."""
    waves = _one(conn, "SELECT count(*) AS n FROM union_waves WHERE period = %s", (period + 1,))["n"]
    if squeeze < data.GENERAL_SQUEEZE_BPS or waves < data.GENERAL_WAVES_AT:
        return None
    if _one(conn, "SELECT 1 AS x FROM general_strikes WHERE period > %s", (period + 1 - data.GENERAL_EVERY_QUARTERS,)):
        return None
    award = max(apply_bps(_household_income(conn, period), data.GENERAL_AWARD_BPS), 100)
    notice = 2 + int(_unit(seed, period + 1, "general") * 6)
    row = _one(conn, "INSERT INTO general_strikes (period, notice_day, deadline_day, squeeze_bps, waves, award) VALUES (%s, %s, %s, %s, %s, %s)"
                     " ON CONFLICT (period) DO NOTHING RETURNING *",
               (period + 1, notice, notice + data.GENERAL_NOTICE_DAYS, squeeze, waves, award))
    if row:
        name, leader = data.GENERAL_FEDERATION
        news.publish(conn, period=period + 1, day=notice, kind="general_strike_notice", story=f"general:{period + 1}",
                     facts={"federation": name, "leader": leader, "squeeze": _pct(squeeze), "award": news.money_words(award),
                            "days": news.number_word(data.GENERAL_NOTICE_DAYS), "industries": news.number_word(waves)}, boost=20)
    return row


def answer_general(conn: Connection, player_id, concede: bool, now: datetime) -> dict:
    """The Government Leader answers the federation: concede (the Treasury pays the award to households) or refuse."""
    from simulation import government
    with conn.transaction():
        period, day, seed = _today(conn, now)
        boss = government.leader(conn, government.year_of(period))
        if boss is None or str(boss["leader_id"]) != str(player_id):
            raise UnionError("Only the Government Leader answers the federation.")
        g = _one(conn, "SELECT * FROM general_strikes WHERE period = %s FOR UPDATE", (period,))
        if g is None or g["notice_day"] > day:
            raise UnionError("There is no notice of a general strike to answer.")
        if g["status"] != "notice":
            raise UnionError("The notice has already been answered.")
        if day > g["deadline_day"]:
            raise UnionError("The deadline has passed.")
        return _settle_general(conn, g, "concede" if concede else "refuse", player_id, day, now)


def _settle_general(conn: Connection, g: dict, answer: str, by, day: int, now: datetime) -> dict:
    from simulation import ledger
    from simulation.ledger import Leg
    name, leader = data.GENERAL_FEDERATION
    treasury = ledger.account_id(conn, ledger.TREASURY)
    if answer in ("concede", "stand_in_concede"):
        award = min(g["award"], max(ledger.balance(conn, treasury), 0))
        shares = _rows(conn, "SELECT location, income FROM household_results WHERE period = %s AND income > 0 ORDER BY location", (g["period"] - 1,))
        total = sum(s["income"] for s in shares) or 1
        legs, paid = [], 0
        for i, s in enumerate(shares):
            part = award - paid if i == len(shares) - 1 else award * s["income"] // total
            if part > 0:
                legs.append(Leg(ledger.account_id(conn, f"households:{s['location'].lower()}"), part))
                paid += part
        if paid > 0:
            ledger.post(conn, kind="cost_of_living_award", memo=f"Cost-of-living award to households, agreed with the {name}",
                        reference=f"general-strike:{g['id']}", idempotency_key=f"general-award:{g['id']}", legs=[Leg(treasury, -paid), *legs])
        conn.execute("UPDATE general_strikes SET status = 'conceded', answer = %s, answered_by = %s, decided_at = %s WHERE id = %s",
                     (answer, by, now, g["id"]))
        news.publish(conn, period=g["period"], day=day, kind="general_strike_called_off", story=f"general:{g['period']}",
                     facts={"federation": name, "leader": leader, "award": news.money_words(paid or g["award"])}, boost=15)
        return {"status": "conceded", "award": paid}
    from datetime import timedelta
    hours = min(data.GENERAL_STRIKE_HOURS, 48)
    until = now + timedelta(hours=hours)
    days = max(hours * clock.GAME_DAYS_PER_QUARTER // (7 * 24), 1)
    lost = -min(apply_bps(days * BPS // clock.GAME_DAYS_PER_QUARTER, data.GENERAL_STRIKE_SALES_BPS), 5000)
    for u in _rows(conn, "SELECT u.sector, u.name FROM unions u ORDER BY u.sector"):
        conn.execute("INSERT INTO events (period, day, kind, location, sector, company_id, sales_bps, facts)"
                     " VALUES (%s, %s, 'sector_strike', NULL, %s, NULL, %s, %s)",
                     (g["period"], day, u["sector"], lost, Jsonb({"sector": u["sector"], "union": name, "general": g["id"], "days": days})))
    conn.execute("UPDATE market_status SET strike_until = %s", (until,))
    conn.execute("UPDATE general_strikes SET status = 'striking', answer = %s, answered_by = %s, decided_at = %s, strike_from = %s,"
                 " strike_until = %s, strike_days = %s WHERE id = %s", (answer, by, now, now, until, days, g["id"]))
    news.publish(conn, period=g["period"], day=day, kind="general_strike", story=f"general:{g['period']}",
                 facts={"federation": name, "leader": leader, "hours": news.number_word(hours), "days": news.number_word(days)}, boost=25)
    return {"status": "striking", "until": until}


def _work_general(conn: Connection, period: int, day: int, now: datetime) -> int:
    g = _one(conn, "SELECT * FROM general_strikes WHERE period = %s FOR UPDATE SKIP LOCKED", (period,))
    if g is None:
        g = _one(conn, "SELECT * FROM general_strikes WHERE status = 'striking' AND strike_until <= %s FOR UPDATE SKIP LOCKED", (now,))
    if g is None:
        return 0
    if g["status"] == "notice" and day >= g["deadline_day"]:
        from simulation import government
        boss = government.leader(conn, government.year_of(period))
        if boss:
            answer = "refuse"                                   # the Leader said nothing: the federation takes that as a no
        else:
            term = government.term(conn, government.year_of(period), now)
            from simulation import ledger
            can_pay = ledger.balance(conn, ledger.account_id(conn, ledger.TREASURY)) >= g["award"]
            answer = "stand_in_concede" if term["stand_in"] != "hawk" and can_pay else "stand_in_refuse"
        _settle_general(conn, g, answer, None, g["deadline_day"], now)
        return 1
    if g["status"] == "striking" and g["strike_until"] <= now:
        conn.execute("UPDATE general_strikes SET status = 'over' WHERE id = %s", (g["id"],))
        name, leader = data.GENERAL_FEDERATION
        from simulation import careers
        world = careers.world_now(conn, now)
        news.publish(conn, period=world["period"], day=world["day"], kind="general_strike_over", story=f"general:{g['period']}",
                     facts={"federation": name, "leader": leader, "days": news.number_word(g["strike_days"])})
        return 1
    return 0


def closed_by_strike(conn: Connection, now: datetime) -> datetime | None:
    """While a general strike is on, the exchange is shut: orders wait in the queue for the next opening auction."""
    if not _one(conn, "SELECT to_regclass('general_strikes') IS NOT NULL AS ok")["ok"]:
        return None
    row = _one(conn, "SELECT strike_until FROM market_status")
    return row["strike_until"] if row and row["strike_until"] and row["strike_until"] > now else None


def general_view(conn: Connection, player_id, now: datetime) -> dict | None:
    """The general strike now, if there is one the public knows of; with what the Government Leader may do."""
    if not waves_ready(conn):
        return None
    from simulation import careers, government
    world = careers.world_now(conn, now)
    g = _one(conn, "SELECT * FROM general_strikes WHERE (period = %s AND notice_day <= %s) OR (status = 'striking') ORDER BY id DESC LIMIT 1",
              (world["period"], world["day"]))
    if g is None:
        return None
    boss = government.leader(conn, government.year_of(world["period"]))
    name, leader = data.GENERAL_FEDERATION
    return {"id": g["id"], "federation": name, "leader": leader, "status": g["status"], "award": g["award"], "squeeze_bps": g["squeeze_bps"],
            "waves": g["waves"], "deadline_day": g["deadline_day"], "days_left": max(g["deadline_day"] - world["day"], 0),
            "strike_until": g["strike_until"].isoformat() if g["strike_until"] else None, "answer": g["answer"],
            "is_leader": bool(boss and player_id and str(boss["leader_id"]) == str(player_id)) and g["status"] == "notice",
            "hours": data.GENERAL_STRIKE_HOURS}
