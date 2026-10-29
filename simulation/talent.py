"""Proven Talent (the talent and funds stage, Part 1): a record of what each player has really done.

The record is worked out from the game's own books and nothing else, so nobody can type it in, edit it or buy it:

  investing    how the player's money did: worked out day by day from what they were worth at each closing bell,
               with money that came from outside investing (salary, fees, gifts, an empire's pay-outs) taken out
               first, so earning more is never mistaken for investing well. Shown against the market index, with
               how much it swung, the worst fall it lived through and how many quarters it beat the market.
  work         levels and ranks reached, and professional work passed and failed.
  calls        what the player put their name to in an empire, and how much of it turned out right.
  audits       audits filed: people rightly named, people wrongly named, and wrongdoing missed that was proved later.
  journalism   stories published, leads that held up and leads that did not, corrections.
  leadership   empires led, and the decisions as head that turned out well or badly.
  crisis       banks that closed while the player had savings there, money pulled out in time, savings lost,
               bank rescues won.
  conduct      wrongdoing proved against the player. It is always shown when a record is shared: it cannot be hidden.
  challenges   challenges set by firms: entered, places and wins.

Only percentages and counts are shown, never how much money a player has.

Badges are earned from the record, never bought; a few (a clean record) are lost again if it stops being true.

Keeping it honest:
  * a trade between two accounts run by players (their own, their empires', the funds they manage) at a price far from
    the market's hands value from one to the other: shares at a price far from what the market paid that day, options
    and futures far from the dealers' own price, a building sold privately far from its value. The value handed over is
    taken out of the receiver's record as if it were a gift.
  * players who deal like that with each other again and again, or who deal at odd prices with each other from one
    device, are "linked": they are kept off the talent board and out of challenge places until an administrator has
    looked. Once cleared, a pair can be linked again by what they do afterwards.
  * none of these checks, and none of their results, is ever shown to a player.
"""

from __future__ import annotations

import hashlib
import hmac
import math
import secrets
from datetime import date, datetime, time, timedelta

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

import logging

from simulation import careers, clock, ledger
from simulation.money import naira

log = logging.getLogger("wsbm.talent")

# Money that moves because of investing: it is part of the return. Anything else that reaches a player's cash is
# money from outside (pay, fees, gifts) and is taken out before the return is worked out. A kind that is not listed
# here counts as money from outside, so a new way of being paid can never be mistaken for a good investment.
INVESTING_KINDS = frozenset({
    "trade", "share_trade", "order_reserve", "order_release", "block_trade", "exchange",
    "bond", "bond_trade", "bond_coupon", "bond_redemption", "conversion_hold", "conversion_release",
    "dividend", "preferred_dividend", "lent_dividend", "share_return", "share_split", "share_offer", "share_sale",
    "offer_hold", "offer_release", "offer_result", "offer_topped", "rights", "rights_issue", "tender_hold", "tender_release",
    "takeover_payment", "takeover_refund", "takeover_reserve", "warrant_hold",
    "instrument_trade", "future_trade", "option_premium", "variation_margin",
    "derivative_fee", "derivative_margin", "derivative_margin_release", "derivative_order", "derivative_order_release",
    "swap_payment", "monte_carlo_fee", "intel_check",
    "savings_interest", "savings_placed", "savings_withdrawn", "deposit_interest", "deposit_placed", "deposit_withdrawn",
    "bail_in", "fund_units", "buy_in", "share_issue", "preferred_issue", "bond_issue",
    "margin_loan", "personal_loan", "loan_repayment", "player_loan_interest", "lending_fee", "share_loan",
    "short_collateral", "short_release", "shortfall_repayment", "forced_sale",
    "auction_hold", "auction_release", "property_sale", "property_forced_sale", "rent", "lease_rent", "property_tax",
    "land_registration", "mortgage_loan", "mortgage_interest", "mortgage_repayment", "capital_spending",
    "crash_premium", "crash_payout", "crash_cover",
})
# Money of these kinds is part of the return when the player pays it, but pay for work when they receive it: a fund's fee
# paid to its manager is earned by managing, not by investing.
PAID_IS_INVESTING = frozenset({"fund_fee"})

MIN_BASE = naira(100_000)            # a day is not counted when the player had less than this to invest
SESSIONS_PER_YEAR = 28               # a trading day each real day; seven to a game quarter
DAY_CLAMP = (-0.95, 3.0)             # one day's return is never taken as more extreme than this
BOARD_MIN_DAYS = 14                  # two game quarters of counted days before a record can be on the board
OFF_MARKET_BPS = 500                 # a trade 5% or more away from what everybody else paid that day
OFF_VALUE_BPS = 2_000                # an option, future or building dealt 20% or more away from its value
MARKS_KEPT_DAYS = 2                  # device marks are kept this long
LINKED_TRADES = 3                    # ...this many times between the same two players: they are linked
CRISIS_WINDOW_DAYS = 15              # money pulled out in the fifteen game days before a bank closed
SECTIONS = ("investing", "work", "calls", "audits", "journalism", "leadership", "crisis", "challenges")
SECTION_NAMES = {"investing": "Investing", "work": "Work and levels", "calls": "Calls put in writing", "audits": "Audits",
                 "journalism": "Journalism", "leadership": "Leadership", "crisis": "Bank crises", "challenges": "Firm challenges",
                 "conduct": "Conduct"}


class TalentError(Exception):
    """A request about Proven Talent the rules do not allow. The words are for the player."""


def _rows(conn: Connection, sql: str, params=()) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def _one(conn: Connection, sql: str, params=()) -> dict | None:
    rows = _rows(conn, sql, params)
    return rows[0] if rows else None


def ready(conn: Connection) -> bool:
    return bool(_one(conn, "SELECT to_regclass('talent_records') IS NOT NULL AS ok")["ok"])


def _bps(x: float | None) -> int | None:
    return None if x is None else round(x * 10_000)


# ---------------------------------------------------------------------------
# Which game quarter a trading day belongs to
# ---------------------------------------------------------------------------

def _start(conn: Connection) -> datetime | None:
    world = _one(conn, "SELECT world_start, weeks_ahead FROM world_state")
    return clock.effective_start(world["world_start"], world["weeks_ahead"]) if world else None


def period_of_day(start: datetime, day: date) -> int:
    moment = datetime.combine(day, time(21, 0), tzinfo=clock.LAGOS)
    return clock.periods_completed(moment, start) + 1


def _bell(day: date, rung: dict) -> datetime:
    return rung.get(day) or datetime.combine(day, clock.MARKET_CLOSE, tzinfo=clock.LAGOS)


# ---------------------------------------------------------------------------
# Investing
# ---------------------------------------------------------------------------

def _price_then(conn: Connection, asset: str, at: datetime) -> int:
    """What one unit of an asset was worth at a moment, for valuing shares or savings that arrived from outside."""
    if asset.startswith("DEP-"):
        return 1
    found = _one(conn, "SELECT t.price FROM market_trades t JOIN market_instruments m ON m.company_id = t.company_id"
                       " WHERE m.asset = %s AND t.traded_at <= %s ORDER BY t.traded_at DESC LIMIT 1", (asset, at))
    if found:
        return found["price"]
    found = _one(conn, "SELECT coalesce(last_price, reference_price, listing_price) AS price FROM market_instruments WHERE asset = %s",
                 (asset,))
    if found and found["price"]:
        return found["price"]
    if asset.startswith("BND-"):
        from simulation import bonds
        found = bonds._load(conn, "b.asset = %s", (asset,))
        if found:
            return bonds.fair_value(found[0], bonds.market(conn, at))
    return 0


def outside_money(conn: Connection, account, since: datetime | None = None) -> list[tuple[datetime, int]]:
    """Every movement of value into (+) or out of (-) an account that did not come from investing, with its moment."""
    rows = _rows(conn, "SELECT t.created_at, t.kind, e.asset, sum(e.amount)::bigint AS amount FROM ledger_entries e"
                       " JOIN ledger_transactions t ON t.id = e.transaction_id"
                       " WHERE e.account_id = %s AND NOT (t.kind = ANY(%s)) AND (%s::timestamptz IS NULL OR t.created_at > %s)"
                       " GROUP BY t.id, t.created_at, t.kind, e.asset ORDER BY t.created_at", (account, list(INVESTING_KINDS), since, since))
    out = []
    for r in rows:
        if r["amount"] == 0 or (r["kind"] in PAID_IS_INVESTING and r["amount"] < 0):
            continue
        value = r["amount"] if r["asset"] == ledger.NGN else r["amount"] * _price_then(conn, r["asset"], r["created_at"])
        if value:
            out.append((r["created_at"], value))
    return out


def daily_returns(conn: Connection, player_id) -> tuple[list[tuple[date, float, float | None]], date | None, date | None]:
    """Each counted trading day: (day, the player's return, the market index's return), and the first and last day recorded."""
    account = ledger.player_account_id(conn, player_id)
    if account is None:
        return [], None, None
    days = _rows(conn, "SELECT session_date, cash + investments AS worth FROM net_worth_days WHERE account_id = %s ORDER BY session_date",
                 (account,))
    if len(days) < 2:
        return [], days[0]["session_date"] if days else None, days[0]["session_date"] if days else None
    dates = [d["session_date"] for d in days]
    rung = {r["session_date"]: r["rung_at"] for r in _rows(conn, "SELECT session_date, rung_at FROM closing_bells WHERE session_date"
                                                                 " BETWEEN %s AND %s", (dates[0], dates[-1]))}
    levels = {r["session_date"]: r["level"] for r in _rows(conn, "SELECT session_date, level FROM index_days WHERE session_date"
                                                                 " BETWEEN %s AND %s", (dates[0], dates[-1]))}
    cutoffs = [_bell(d, rung) for d in dates]
    # Money from outside, day by day, and how much of each day it was there for. Money arriving just before the bell was
    # invested for almost none of the day, so it barely counts in the day's base: it cannot water down a losing day.
    flows = [0] * len(days)
    weighted = [0.0] * len(days)
    i = 0
    for at, value in outside_money(conn, account, cutoffs[0]):
        while i < len(cutoffs) and cutoffs[i] < at:
            i += 1
        if i >= len(cutoffs):
            break
        flows[i] += value
        span = (cutoffs[i] - cutoffs[i - 1]).total_seconds() if i else 0
        weighted[i] += value * (max(0.0, min(1.0, (cutoffs[i] - at).total_seconds() / span)) if span > 0 else 0.0)
    # Value handed over in trades at odd prices is a gift, not a return (counted as arriving at the day's end).
    gifts = {r["session_date"]: r["amount"] for r in _rows(
        conn, "SELECT session_date, sum(amount)::bigint AS amount FROM talent_flags WHERE player_id = %s AND kind = 'off_market_trade'"
              " AND cleared_at IS NULL GROUP BY session_date", (player_id,))}
    for k, d in enumerate(dates):
        flows[k] += gifts.get(d, 0)
    returns: list[tuple[date, float, float | None]] = []
    for k in range(1, len(days)):
        before, now_, flow = days[k - 1]["worth"], days[k]["worth"], flows[k]
        base = before + weighted[k]
        if before < MIN_BASE or base < MIN_BASE // 2:
            continue
        r = (now_ - before - flow) / base
        r = min(max(r, DAY_CLAMP[0]), DAY_CLAMP[1])
        a, b = levels.get(dates[k - 1]), levels.get(dates[k])
        returns.append((dates[k], r, (b / a - 1) if a and b else None))
    return returns, dates[0], dates[-1]


def window_return_bps(conn: Connection, player_id, first: date, last: date, *, least_days: int = 3) -> int | None:
    """The return over the trading days from `first` to `last`, or None with fewer than `least_days` counted."""
    returns, _, _ = daily_returns(conn, player_id)
    inside = [r for d, r, _ in returns if first <= d <= last]
    if len(inside) < least_days:
        return None
    return _bps(math.prod(1 + r for r in inside) - 1)


def investing(conn: Connection, player_id, *, start: datetime | None = None) -> dict:
    """The player's investing record, day by day from the closing bells."""
    empty = {"days_counted": 0, "first_day": None, "last_day": None, "total_bps": None, "index_bps": None, "versus_index_bps": None,
             "annual_bps": None, "swing_bps": None, "risk_ratio": None, "worst_fall_bps": None, "last_year_bps": None,
             "quarters": [], "beat_streak": 0, "best_streak": 0, "quarters_counted": 0, "quarters_beaten": 0, "chart": []}
    returns, first, last = daily_returns(conn, player_id)
    if not returns:
        return {**empty, "first_day": first, "last_day": last}
    start = start or _start(conn)
    growth = index_growth = 1.0
    peak, worst = 1.0, 0.0
    chart = []
    for d, r, x in returns:
        growth *= 1 + r
        index_growth *= 1 + (x or 0.0)
        peak = max(peak, growth)
        worst = min(worst, growth / peak - 1)
        chart.append({"day": d, "you_bps": _bps(growth - 1), "index_bps": _bps(index_growth - 1)})
    n = len(returns)
    mean = sum(r for _, r, _ in returns) / n
    spread = math.sqrt(sum((r - mean) ** 2 for _, r, _ in returns) / (n - 1)) if n > 1 else 0.0
    swing = spread * math.sqrt(SESSIONS_PER_YEAR)
    annual = growth ** (SESSIONS_PER_YEAR / n) - 1 if n >= 7 and growth > 0 else None
    last = returns[-SESSIONS_PER_YEAR:]
    last_year = math.prod(1 + r for _, r, _ in last) - 1 if n >= SESSIONS_PER_YEAR else None

    # Quarter by quarter, against the index over the same counted days.
    quarters: dict[int, list] = {}
    if start:
        for d, r, x in returns:
            quarters.setdefault(period_of_day(start, d), []).append((r, x))
    q_rows = []
    streak = best = beaten = counted = 0
    last_counted = None
    for period in sorted(quarters):
        items = quarters[period]
        if len(items) < 3:
            continue
        mine = math.prod(1 + r for r, _ in items) - 1
        market = math.prod(1 + (x or 0.0) for _, x in items) - 1
        counted += 1
        beat = mine > market
        beaten += beat
        # "Running" means quarter after quarter: a quarter sat out (too little invested to count) breaks the run.
        if last_counted is not None and period != last_counted + 1:
            streak = 0
        last_counted = period
        streak = streak + 1 if beat else 0
        best = max(best, streak)
        q_rows.append({"period": period, "label": clock.period_label(period), "you_bps": _bps(mine), "index_bps": _bps(market), "beat": beat})
    step = max(1, len(chart) // 120)
    thin = chart[::step] + ([chart[-1]] if (len(chart) - 1) % step else [])
    return {
        "days_counted": n, "first_day": returns[0][0], "last_day": returns[-1][0],
        "total_bps": _bps(growth - 1), "index_bps": _bps(index_growth - 1), "versus_index_bps": _bps((growth - 1) - (index_growth - 1)),
        "annual_bps": _bps(annual), "swing_bps": _bps(swing),
        "risk_ratio": round(annual / swing, 2) if annual is not None and swing > 0 else None,
        "worst_fall_bps": _bps(worst), "last_year_bps": _bps(last_year),
        "quarters": q_rows[-12:], "beat_streak": streak, "best_streak": best, "quarters_counted": counted, "quarters_beaten": beaten,
        "chart": thin,
    }


# ---------------------------------------------------------------------------
# The rest of the record, from the game's registers
# ---------------------------------------------------------------------------

def work(conn: Connection, player_id) -> dict:
    builds = []
    for c in _rows(conn, "SELECT build, experience, rank, started_at FROM careers WHERE player_id = %s ORDER BY experience DESC", (player_id,)):
        level = careers.level_for(c["experience"], c["rank"])
        builds.append({"build": c["build"], "name": careers.BUILDS.get(c["build"], {}).get("name", c["build"]), "level": level,
                       "rank": careers.rank_name(c["rank"]), "since": c["started_at"]})
    judged = {(r["build"], r["state"]): r["n"] for r in _rows(
        conn, "SELECT build, state, count(*) AS n FROM objectives WHERE player_id = %s AND state IN ('passed', 'failed') GROUP BY build, state",
        (player_id,))}
    for b in builds:
        b["passed"], b["failed"] = judged.get((b["build"], "passed"), 0), judged.get((b["build"], "failed"), 0)
    return {"builds": builds, "passed": sum(b["passed"] for b in builds), "failed": sum(b["failed"] for b in builds)}


def calls(conn: Connection, player_id) -> dict:
    from simulation import firm
    kinds = _rows(conn, "SELECT kind, count(*) FILTER (WHERE outcome = 'right') AS right, count(*) FILTER (WHERE outcome = 'wrong') AS wrong"
                        " FROM signed_opinions WHERE player_id = %s AND outcome IN ('right', 'wrong') GROUP BY kind ORDER BY kind", (player_id,))
    right, wrong = sum(k["right"] for k in kinds), sum(k["wrong"] for k in kinds)
    return {"kinds": [{**k, "name": firm.OPINION_NAMES.get(k["kind"], k["kind"].replace("_", " ").capitalize())} for k in kinds],
            "right": right, "wrong": wrong, "right_bps": right * 10_000 // (right + wrong) if right + wrong else None}


def audits(conn: Connection, player_id) -> dict:
    """Audits the player filed. Wrongdoing they missed counts only once somebody else has proved it, so the record never
    hints at wrongdoing nobody has proved."""
    rows = _rows(conn, "SELECT id, findings, reported FROM empire_audits WHERE auditor_id = %s AND status = 'filed'", (player_id,))
    right = wrong = missed = 0
    for a in rows:
        found, named = set(a["findings"] or []), set(a["reported"] or [])
        right += len(found & named)
        wrong += len(named - found)
        unnamed = list(found - named)
        if unnamed:
            missed += _one(conn, "SELECT count(*) AS n FROM empire_cases WHERE book_id = ANY(%s) AND status = 'punished'"
                                 " AND audit_id IS DISTINCT FROM %s", (unnamed, a["id"]))["n"]
    return {"filed": len(rows), "rightly_named": right, "wrongly_named": wrong, "missed_proved_later": missed}


def journalism(conn: Connection, player_id) -> dict:
    p = _one(conn, "SELECT * FROM journalist_profiles WHERE player_id = %s", (player_id,))
    leads = {r["lead_outcome"]: r["n"] for r in _rows(
        conn, "SELECT lead_outcome, count(*) AS n FROM stories WHERE author_id = %s AND status = 'published' AND lead_outcome IS NOT NULL"
              " GROUP BY lead_outcome", (player_id,))}
    published = _one(conn, "SELECT count(*) AS n, count(*) FILTER (WHERE correction_late) AS late FROM stories WHERE author_id = %s"
                           " AND status = 'published'", (player_id,))
    return {"published": published["n"], "scoops": p["scoops"] if p else 0, "corrections": p["corrections"] if p else 0,
            "late_corrections": published["late"], "credibility": p["credibility"] if p else None,
            "leads_held": leads.get("confirmed", 0), "leads_failed": leads.get("disproved", 0)}


def leadership(conn: Connection, player_id) -> dict:
    rows = _rows(conn, "SELECT r.good, e.name FROM ceo_records r JOIN empires e ON e.id = r.empire_id WHERE r.player_id = %s", (player_id,))
    led = sorted({r["name"] for r in rows} | {r["name"] for r in _rows(
        conn, "SELECT name FROM empires WHERE head_player_id = %s", (player_id,))})
    return {"empires": led, "good": sum(1 for r in rows if r["good"] is True), "bad": sum(1 for r in rows if r["good"] is False)}


def crisis_conduct(conn: Connection, player_id) -> dict:
    account = ledger.player_account_id(conn, player_id)
    out = {"banks_closed_with_savings": 0, "pulled_out_in_time": 0, "lost_savings": False, "rescues_won": 0, "crises_lived_through": 0}
    if account is None or not _one(conn, "SELECT to_regclass('bank_resolutions') IS NOT NULL AS ok")["ok"]:
        return out
    joined = _one(conn, "SELECT created_at FROM players WHERE id = %s", (player_id,))["created_at"]
    for r in _rows(conn, "SELECT company_id, period, day, at FROM bank_resolutions ORDER BY id"):
        moment = r["period"] * 1000 + r["day"]
        flows = _rows(conn, "SELECT kind, amount, period * 1000 + day AS moment FROM deposit_flows WHERE account_id = %s AND company_id = %s"
                            " AND period * 1000 + day <= %s", (account, r["company_id"], moment))
        if not flows:
            continue
        kept = sum(f["amount"] if f["kind"] == "placed" else -f["amount"] for f in flows if f["kind"] in ("placed", "withdrawn"))
        pulled = [f for f in flows if f["kind"] == "withdrawn" and moment - f["moment"] <= CRISIS_WINDOW_DAYS
                  and f["moment"] // 1000 == r["period"]]
        if pulled:
            out["pulled_out_in_time"] += 1
        if kept > 0:
            out["banks_closed_with_savings"] += 1
    out["lost_savings"] = bool(_one(conn, "SELECT 1 AS x FROM deposit_flows WHERE account_id = %s AND kind = 'bail_in' LIMIT 1", (account,)))
    mine = [account] + [r["account_id"] for r in _rows(conn, "SELECT account_id FROM empires WHERE head_player_id = %s", (player_id,))]
    out["rescues_won"] = _one(conn, "SELECT count(*) AS n FROM bank_resolutions WHERE new_owner = ANY(%s) AND status IN ('sold', 'resold')",
                              (mine,))["n"]
    out["crises_lived_through"] = _one(conn, "SELECT count(*) AS n FROM economic_crises WHERE at >= %s OR status = 'open'", (joined,))["n"] \
        if _one(conn, "SELECT to_regclass('economic_crises') IS NOT NULL AS ok")["ok"] else 0
    return out


CONDUCT_NAMES = {"theft": "Proved to have taken money from an empire"}


def conduct(conn: Connection, player_id) -> dict:
    """Wrongdoing proved. Only what it was and when: never the sums, the fines or what is still owed."""
    rows = _rows(conn, "SELECT kind, at FROM legal_records WHERE player_id = %s ORDER BY id DESC", (player_id,))
    return {"proved": len(rows), "entries": [{"kind": r["kind"], "words": CONDUCT_NAMES.get(r["kind"], "Wrongdoing proved"), "at": r["at"]}
                                             for r in rows[:10]]}


def challenge_record(conn: Connection, player_id) -> dict:
    rows = _rows(conn, "SELECT c.id, c.title, f.name AS firm, e.place, c.results->>'entrants' AS entrants FROM challenge_entries e"
                       " JOIN talent_challenges c ON c.id = e.challenge_id JOIN talent_firms f ON f.id = c.firm_id"
                       " WHERE e.player_id = %s AND c.status = 'scored' ORDER BY c.ends_at DESC", (player_id,))
    for r in rows:
        r["entrants"] = int(r["entrants"] or 0)
    return {"entered": len(rows), "wins": sum(1 for r in rows if r["place"] == 1),
            "top_tenth": sum(1 for r in rows if r["place"] and r["entrants"] and r["place"] * 10 <= max(r["entrants"], 10)),
            "results": rows[:10]}


def work_out(conn: Connection, player_id, now: datetime) -> dict:
    """The whole record, worked out afresh from the books."""
    inv = investing(conn, player_id)
    return {"investing": inv, "work": work(conn, player_id), "calls": calls(conn, player_id), "audits": audits(conn, player_id),
            "journalism": journalism(conn, player_id), "leadership": leadership(conn, player_id),
            "crisis": crisis_conduct(conn, player_id), "conduct": conduct(conn, player_id),
            "challenges": challenge_record(conn, player_id), "worked_at": now}


# ---------------------------------------------------------------------------
# Badges
# ---------------------------------------------------------------------------

def badges_from(rec: dict) -> list[tuple[str, str, str]]:
    """(code, label, why) for every badge the record has earned now."""
    out = []
    inv = rec["investing"]
    if inv["best_streak"] >= 4:
        out.append(("beat_market_4", "Beat the market 4 quarters running", "Did better than the market index four game quarters in a row."))
    elif inv["best_streak"] >= 2:
        out.append(("beat_market_2", "Beat the market twice running", "Did better than the market index two game quarters in a row."))
    if inv["quarters_counted"] >= 4 and (inv["total_bps"] or 0) > 0 and inv["worst_fall_bps"] is not None and inv["worst_fall_bps"] > -1000:
        out.append(("steady_hand", "Steady hand", "Made money over at least a game year without ever falling 10% from a high."))
    if inv["quarters_counted"] >= 4 and (inv["total_bps"] or 0) >= 5000:
        out.append(("grew_half", "Grew money by half", "Grew invested money by 50% or more, outside money taken out."))
    c = rec["calls"]
    if c["right"] + c["wrong"] >= 10 and (c["right_bps"] or 0) >= 7000:
        out.append(("sharp_calls", "Sharp calls", "At least ten calls put in writing, seven in ten of them right."))
    a = rec["audits"]
    if a["filed"] >= 3 and a["rightly_named"] >= 1 and a["wrongly_named"] == 0 and a["missed_proved_later"] == 0:
        out.append(("clean_audits", "Clean audit record", "Three or more audits filed: nobody wrongly named, nothing missed."))
    j = rec["journalism"]
    if j["leads_held"] >= 3 and j["leads_failed"] == 0:
        out.append(("leads_held", "Stories that held up", "Three or more leads proved true, none proved false."))
    lead = rec["leadership"]
    if lead["good"] >= 4 and lead["good"] > 2 * lead["bad"]:
        out.append(("trusted_head", "Trusted head", "Decisions as an empire's head that turned out well, far more often than not."))
    cr = rec["crisis"]
    if not cr["lost_savings"] and (cr["pulled_out_in_time"] or (cr["crises_lived_through"] and cr["banks_closed_with_savings"])):
        out.append(("came_through_crisis", "Came through a bank crisis", "Had savings at a bank that closed, and lost nothing."))
    if cr["rescues_won"]:
        out.append(("bank_rescuer", "Bank rescuer", "Won the sale of a closed bank and put new money into it."))
    if inv["days_counted"] >= 4 * 7 * 2 and rec["conduct"]["proved"] == 0:
        out.append(("clean_record", "Clean record", "Two game years of record with no wrongdoing proved."))
    for b in rec["work"]["builds"]:
        top = max((t for t in (20, 40, 60, 80, 100) if b["level"] >= t), default=None)
        if top:
            out.append((f"level_{b['build']}_{top}", f"Level {top} {b['name']}", f"Reached Level {top} as {b['name']}."))
    for r in rec["challenges"]["results"]:
        if r["place"] == 1:
            out.append((f"won_challenge_{r['id']}", f"Won: {r['title']}"[:80], f"Came first in a challenge set by {r['firm']}."))
    return out


LOSABLE = {"clean_record", "clean_audits", "leads_held"}


def badge_section(code: str) -> str:
    """The part of the record a badge comes from: it is shown only where that part is shown."""
    if code.startswith(("beat_market", "steady_hand", "grew_half")):
        return "investing"
    if code.startswith("level_"):
        return "work"
    if code.startswith("won_challenge_"):
        return "challenges"
    return {"sharp_calls": "calls", "clean_audits": "audits", "leads_held": "journalism", "trusted_head": "leadership",
            "came_through_crisis": "crisis", "bank_rescuer": "crisis", "clean_record": "conduct"}.get(code, "conduct")


def _keep_badges(conn: Connection, player_id, earned: list[tuple[str, str, str]], now: datetime) -> None:
    codes = {code for code, _, _ in earned}
    for code, label, words in earned:
        conn.execute("INSERT INTO talent_badges (player_id, code, label, words, earned_at) VALUES (%s, %s, %s, %s, %s)"
                     " ON CONFLICT (player_id, code) DO UPDATE SET lost_at = NULL, label = EXCLUDED.label"
                     " WHERE talent_badges.lost_at IS NOT NULL OR talent_badges.label <> EXCLUDED.label",
                     (player_id, code, label, words, now))
    for b in _rows(conn, "SELECT code FROM talent_badges WHERE player_id = %s AND lost_at IS NULL", (player_id,)):
        if b["code"] in LOSABLE and b["code"] not in codes:
            conn.execute("UPDATE talent_badges SET lost_at = %s WHERE player_id = %s AND code = %s", (now, player_id, b["code"]))


def badges(conn: Connection, player_id) -> list[dict]:
    return _rows(conn, "SELECT code, label, words, earned_at FROM talent_badges WHERE player_id = %s AND lost_at IS NULL"
                       " ORDER BY earned_at, code", (player_id,))


# ---------------------------------------------------------------------------
# Keeping the latest working-out
# ---------------------------------------------------------------------------

def _summary(rec: dict, codes: list[str]) -> dict:
    inv = rec["investing"]
    return {"days": inv["days_counted"], "total_bps": inv["total_bps"], "versus_index_bps": inv["versus_index_bps"],
            "worst_fall_bps": inv["worst_fall_bps"], "risk_ratio": inv["risk_ratio"], "best_streak": inv["best_streak"],
            "calls_right_bps": rec["calls"]["right_bps"], "calls": rec["calls"]["right"] + rec["calls"]["wrong"],
            "proved": rec["conduct"]["proved"], "wins": rec["challenges"]["wins"], "badges": codes,
            "builds": [{"build": b["build"], "level": b["level"]} for b in rec["work"]["builds"]]}


def refresh(conn: Connection, player_id, now: datetime) -> dict:
    rec = work_out(conn, player_id, now)
    _keep_badges(conn, player_id, badges_from(rec), now)
    codes = [b["code"] for b in badges(conn, player_id)]
    stored = _plain(rec)
    conn.execute("INSERT INTO talent_records (player_id, worked_on, worked_at, record, summary) VALUES (%s, %s, %s, %s, %s)"
                 " ON CONFLICT (player_id) DO UPDATE SET worked_on = EXCLUDED.worked_on, worked_at = EXCLUDED.worked_at,"
                 " record = EXCLUDED.record, summary = EXCLUDED.summary",
                 (player_id, rec["investing"]["last_day"], now, Jsonb(stored), Jsonb(_summary(rec, codes))))
    return rec


def _plain(value):
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if hasattr(value, "hex") and type(value).__name__ == "UUID":
        return str(value)
    return value


def stored(conn: Connection, player_id, now: datetime) -> dict:
    """The latest working-out; worked out now if there is none yet."""
    row = _one(conn, "SELECT record FROM talent_records WHERE player_id = %s", (player_id,))
    return row["record"] if row else _plain(refresh(conn, player_id, now))


# ---------------------------------------------------------------------------
# The player's own page, and sharing
# ---------------------------------------------------------------------------

def settings(conn: Connection, player_id) -> dict:
    conn.execute("INSERT INTO talent_settings (player_id) VALUES (%s) ON CONFLICT DO NOTHING", (player_id,))
    return _one(conn, "SELECT * FROM talent_settings WHERE player_id = %s", (player_id,))


def held_back(conn: Connection, player_id) -> bool:
    """Kept off the board and out of challenge results until an administrator has looked."""
    return bool(_one(conn, "SELECT 1 AS x FROM talent_flags WHERE player_id = %s AND kind = 'linked' AND cleared_at IS NULL LIMIT 1",
                     (player_id,)))


def board_ready(conn: Connection, player_id) -> tuple[bool, str]:
    row = _one(conn, "SELECT summary FROM talent_records WHERE player_id = %s", (player_id,))
    days = row["summary"]["days"] if row else 0
    if days < BOARD_MIN_DAYS:
        return False, (f"Your record needs at least {BOARD_MIN_DAYS} counted trading days (two game quarters) before firms can see it"
                       f" on the board. It has {days}.")
    if held_back(conn, player_id):
        return False, "Your record is held back from the board while a routine check is made."
    return True, "Firms can find you on the board."


def share(conn: Connection, player_id, on: bool, now: datetime) -> dict:
    s = settings(conn, player_id)
    slug = s["slug"] or secrets.token_urlsafe(18)
    conn.execute("UPDATE talent_settings SET shared = %s, slug = %s, updated_at = %s WHERE player_id = %s", (on, slug, now, player_id))
    return settings(conn, player_id)


def new_link(conn: Connection, player_id, now: datetime) -> dict:
    """A new address for the shared page: the old one stops working at once."""
    settings(conn, player_id)
    conn.execute("UPDATE talent_settings SET slug = %s, updated_at = %s WHERE player_id = %s", (secrets.token_urlsafe(18), now, player_id))
    return settings(conn, player_id)


def choose_sections(conn: Connection, player_id, sections: list[str], now: datetime) -> dict:
    bad = [s for s in sections if s not in SECTIONS]
    if bad:
        raise TalentError(f"There is no part of the record called {bad[0]!r}.")
    settings(conn, player_id)
    conn.execute("UPDATE talent_settings SET show = %s, updated_at = %s WHERE player_id = %s",
                 ([s for s in SECTIONS if s in sections], now, player_id))
    return settings(conn, player_id)


def set_board(conn: Connection, player_id, on: bool, headline: str, now: datetime) -> dict:
    headline = " ".join(headline.split())[:140]
    settings(conn, player_id)
    if on:
        ok, words = board_ready(conn, player_id)
        if not ok and not held_back(conn, player_id):
            raise TalentError(words)
    conn.execute("UPDATE talent_settings SET on_board = %s, headline = %s, updated_at = %s WHERE player_id = %s",
                 (on, headline, now, player_id))
    return settings(conn, player_id)


def _identity(conn: Connection, player_id) -> dict:
    p = _one(conn, "SELECT display_name, profile_icon, created_at, build FROM players WHERE id = %s", (player_id,))
    return {"name": p["display_name"], "icon": p["profile_icon"], "since": p["created_at"].date().isoformat(),
            "build": careers.BUILDS.get(p["build"], {}).get("name") if p["build"] else None}


def public_view(conn: Connection, slug: str) -> dict | None:
    """The shared page. Only the parts the player chose, and always their conduct."""
    s = _one(conn, "SELECT * FROM talent_settings WHERE slug = %s AND shared", (slug,))
    if s is None:
        return None
    return _shown(conn, s["player_id"], s["show"], s["headline"])


def _shown(conn: Connection, player_id, show: list[str], headline: str) -> dict:
    row = _one(conn, "SELECT record, worked_at FROM talent_records WHERE player_id = %s", (player_id,))
    rec = row["record"] if row else {}
    parts = {k: rec.get(k) for k in show if k in rec}
    parts["conduct"] = rec.get("conduct", {"proved": 0, "entries": []})
    shown = [b for b in badges(conn, player_id) if badge_section(b["code"]) in parts]
    who = _identity(conn, player_id)
    if "work" not in parts:
        who["build"] = None
    return {"who": who, "headline": headline, "sections": [k for k in (*SECTIONS, "conduct") if k in parts],
            "names": SECTION_NAMES, "record": parts, "badges": _plain(shown),
            "worked_at": row["worked_at"].isoformat() if row else None,
            "how": "Worked out by the game from its own books: nobody, the player included, can type in or change any of it."
                   " Only percentages and counts are shown, never how much money anybody has."}


def own_view(conn: Connection, player_id, now: datetime) -> dict:
    rec = stored(conn, player_id, now)
    s = settings(conn, player_id)
    ok, words = board_ready(conn, player_id)
    worked = _one(conn, "SELECT worked_at FROM talent_records WHERE player_id = %s", (player_id,))
    return {"who": _identity(conn, player_id), "record": rec, "badges": _plain(badges(conn, player_id)), "names": SECTION_NAMES,
            "sections": list(SECTIONS), "worked_at": worked["worked_at"].isoformat() if worked else None,
            "settings": {"shared": s["shared"], "slug": s["slug"] if s["shared"] else None, "show": s["show"], "on_board": s["on_board"],
                         "headline": s["headline"], "board_ready": ok, "board_words": words}}


# ---------------------------------------------------------------------------
# Keeping it honest
# ---------------------------------------------------------------------------

def visitor_mark(secret_key: str, address: str, browser: str) -> str:
    """A keyed one-way mark of the device: the address itself is never kept."""
    return hmac.new(secret_key.encode(), f"{address}|{browser[:200]}".encode(), hashlib.sha256).hexdigest()[:32]


def note_visit(conn: Connection, player_id, mark: str, now: datetime) -> None:
    day = clock.to_lagos(now).date()
    added = conn.execute("INSERT INTO visitor_marks (player_id, mark, day) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING RETURNING player_id",
                         (player_id, mark, day)).fetchone()
    if added is None:
        return                                   # seen from this device today already: nothing new to check
    for other in _rows(conn, "SELECT DISTINCT player_id FROM visitor_marks WHERE mark = %s AND day = %s AND player_id <> %s",
                       (mark, day, player_id)):
        new = False
        for a, b in ((player_id, other["player_id"]), (other["player_id"], player_id)):
            new |= _flag(conn, a, "shared_device", b, f"device:{b}:{day.isoformat()}", 0, day, {"day": day.isoformat()}, now)
        if new:
            _maybe_linked(conn, player_id, other["player_id"], now)


def _flag(conn: Connection, player_id, kind: str, other, reference: str, amount: int, day, detail: dict, now: datetime) -> bool:
    row = conn.execute("INSERT INTO talent_flags (player_id, kind, other_id, reference, amount, session_date, detail, at)"
                       " VALUES (%s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (player_id, kind, reference) DO NOTHING RETURNING id",
                       (player_id, kind, other, reference, amount, day, Jsonb(_plain(detail)), now)).fetchone()
    return row is not None


def _maybe_linked(conn: Connection, a, b, now: datetime) -> None:
    """Two players are linked when they dealt with each other at odd prices again and again, or at all from one device. A
    shared device alone is not wrong (families share them), and nor is meeting on the open order book at the market's price.
    Only what happened since an administrator last cleared the pair counts."""
    if a == b:
        return
    since = _one(conn, "SELECT max(cleared_at) AS t FROM talent_flags WHERE kind = 'linked' AND player_id = %s AND other_id = %s",
                 (a, b))["t"]
    odd = _one(conn, "SELECT count(DISTINCT reference) AS n FROM talent_flags WHERE kind = 'off_market_trade' AND player_id = ANY(%s)"
                     " AND other_id = ANY(%s) AND player_id <> other_id AND cleared_at IS NULL AND (%s::timestamptz IS NULL OR at > %s)",
               ([a, b], [a, b], since, since))["n"]
    shared = _one(conn, "SELECT 1 AS x FROM talent_flags WHERE kind = 'shared_device' AND player_id = %s AND other_id = %s"
                        " AND cleared_at IS NULL AND (%s::timestamptz IS NULL OR at > %s) LIMIT 1", (a, b, since, since))
    if odd >= LINKED_TRADES or (shared and odd):
        why = {"odd_deals": odd, "one_device": bool(shared)}
        for p, q in ((a, b), (b, a)):
            if not _one(conn, "SELECT 1 AS x FROM talent_flags WHERE kind = 'linked' AND player_id = %s AND other_id = %s AND cleared_at IS NULL",
                        (p, q)):
                _flag(conn, p, "linked", q, f"linked:{q}:{now.isoformat()}", 0, None, why, now)


# Accounts run by players: their own, their empires' and the funds they manage. A trade between two of these is not the
# market setting a price, and value handed from one to the other at an odd price is a gift.
PLAYER_RUN = ("player", "empire", "fund")


def _fair_price(conn: Connection, company_id, day: date) -> int | None:
    """What the market paid for the share that day: trades with the computer-run investors and institutions on at least one
    side (a trade between two accounts run by players never sets the fair price). If there were none that day, the last such
    trade before; failing that, the exchange's reference price."""
    market = (" FROM market_trades t JOIN ledger_accounts x ON x.id = t.buyer_account_id JOIN ledger_accounts y ON y.id = t.seller_account_id"
              " WHERE t.company_id = %s AND (x.kind <> ALL(%s) OR y.kind <> ALL(%s))")
    run = list(PLAYER_RUN)
    row = _one(conn, "SELECT sum(t.price * t.quantity)::numeric / nullif(sum(t.quantity), 0) AS p" + market + " AND t.session_date = %s",
               (company_id, run, run, day))
    if row and row["p"]:
        return int(row["p"])
    row = _one(conn, "SELECT t.price AS p" + market + " AND t.session_date < %s ORDER BY t.traded_at DESC LIMIT 1", (company_id, run, run, day))
    if row:
        return row["p"]
    row = _one(conn, "SELECT reference_price AS p FROM market_instruments WHERE company_id = %s", (company_id,))
    return row["p"] if row else None


def _runner(conn: Connection, account: dict):
    """The player behind an account run by players: the player themselves, an empire's head, a fund's manager."""
    if account["player_id"]:
        return account["player_id"]
    if account["kind"] == "empire":
        row = _one(conn, "SELECT head_player_id FROM empires WHERE account_id = %s", (account["id"],))
        return row["head_player_id"] if row else None
    return None


def check_trades(conn: Connection, day: date, now: datetime) -> int:
    """Look at one trading day's trades between accounts run by players, at least one of them a player's own (an empire
    selling to its head cheaply hands value from the empire to the head). Returns how many were at odd prices."""
    run = list(PLAYER_RUN)
    trades = _rows(conn, "SELECT t.*, x.player_id AS buyer, y.player_id AS seller, x.kind AS buyer_kind, y.kind AS seller_kind FROM market_trades t"
                         " JOIN ledger_accounts x ON x.id = t.buyer_account_id JOIN ledger_accounts y ON y.id = t.seller_account_id"
                         " WHERE t.session_date = %s AND x.kind = ANY(%s) AND y.kind = ANY(%s) AND t.buyer_account_id <> t.seller_account_id"
                         " AND (x.player_id IS NOT NULL OR y.player_id IS NOT NULL) ORDER BY t.id", (day, run, run))
    found = 0
    pairs = set()
    for t in trades:
        fair = _fair_price(conn, t["company_id"], day)
        if not fair or abs(t["price"] - fair) * 10_000 < OFF_MARKET_BPS * fair:
            continue
        handed = abs(fair - t["price"]) * t["quantity"]
        buyer = _runner(conn, {"id": t["buyer_account_id"], "player_id": t["buyer"], "kind": t["buyer_kind"]})
        seller = _runner(conn, {"id": t["seller_account_id"], "player_id": t["seller"], "kind": t["seller_kind"]})
        detail = {"trade": t["id"], "price": t["price"], "fair": fair, "quantity": t["quantity"], "buyer_kind": t["buyer_kind"],
                  "seller_kind": t["seller_kind"]}
        # Only a player's own account carries a record: the flag goes to whichever side is a player's own.
        cheap = t["price"] < fair
        if t["buyer"]:
            _flag(conn, t["buyer"], "off_market_trade", seller, f"trade:{t['id']}", handed if cheap else -handed, day, detail, now)
        if t["seller"]:
            _flag(conn, t["seller"], "off_market_trade", buyer, f"trade:{t['id']}", -handed if cheap else handed, day, detail, now)
        if t["buyer"] and t["seller"] and t["buyer"] != t["seller"]:
            pairs.add((t["buyer"], t["seller"]))
        found += 1
    for a, b in pairs:
        _maybe_linked(conn, a, b, now)
    return found


def _gift(conn: Connection, day: date, reference: str, buyer_acc: dict, seller_acc: dict, price: int, fair: int, detail: dict,
          now: datetime) -> bool:
    """Flag a deal at an odd price between two accounts run by players. Returns True when it was odd."""
    if not fair or abs(price - fair) * 10_000 < OFF_VALUE_BPS * fair:
        return False
    handed = abs(price - fair)
    buyer, seller = _runner(conn, buyer_acc), _runner(conn, seller_acc)
    cheap = price < fair
    if buyer_acc["player_id"]:
        _flag(conn, buyer_acc["player_id"], "off_market_trade", seller, reference, handed if cheap else -handed, day, detail, now)
    if seller_acc["player_id"]:
        _flag(conn, seller_acc["player_id"], "off_market_trade", buyer, reference, -handed if cheap else handed, day, detail, now)
    if buyer_acc["player_id"] and seller_acc["player_id"]:
        _maybe_linked(conn, buyer_acc["player_id"], seller_acc["player_id"], now)
    return True


def _account(conn: Connection, account_id) -> dict:
    return _one(conn, "SELECT id, kind, player_id FROM ledger_accounts WHERE id = %s", (account_id,))


def check_other_deals(conn: Connection, day: date, now: datetime) -> int:
    """Options and futures dealt between players far from the dealers' own price, and buildings sold privately between
    players far from their value, on one trading day. Returns how many were at odd prices."""
    start = datetime.combine(day, time(0, 0), tzinfo=clock.LAGOS)
    end = datetime.combine(day, time(23, 59, 59), tzinfo=clock.LAGOS)
    found = 0
    run = list(PLAYER_RUN)
    if _one(conn, "SELECT to_regclass('derivative_trades') IS NOT NULL AS ok")["ok"]:
        from simulation import derivatives
        for t in _rows(conn, "SELECT t.* FROM derivative_trades t JOIN ledger_accounts x ON x.id = t.buyer JOIN ledger_accounts y ON y.id = t.seller"
                             " WHERE t.at BETWEEN %s AND %s AND NOT t.with_makers AND x.kind = ANY(%s) AND y.kind = ANY(%s) AND t.buyer <> t.seller"
                             " AND (x.player_id IS NOT NULL OR y.player_id IS NOT NULL) ORDER BY t.id", (start, end, run, run)):
            series = _one(conn, "SELECT * FROM derivative_series WHERE id = %s", (t["series_id"],))
            try:
                fair = derivatives.fair(conn, series, t["at"])
            except Exception:                                   # a contract that can no longer be priced: nothing to compare
                continue
            found += _gift(conn, day, f"derivative:{t['id']}", _account(conn, t["buyer"]), _account(conn, t["seller"]), t["price"] * t["contracts"],
                           fair * t["contracts"], {"trade": t["id"], "price": t["price"], "fair": fair, "contracts": t["contracts"]}, now)
    if _one(conn, "SELECT to_regclass('property_sales') IS NOT NULL AS ok")["ok"]:
        from simulation import property as prop
        sales = _rows(conn, "SELECT s.*, p.district_id FROM property_sales s JOIN properties p ON p.id = s.property_id"
                            " JOIN ledger_accounts x ON x.id = s.buyer JOIN ledger_accounts y ON y.id = s.seller WHERE s.status = 'done'"
                            " AND s.done_at BETWEEN %s AND %s AND x.kind = ANY(%s) AND y.kind = ANY(%s)"
                            " AND (x.player_id IS NOT NULL OR y.player_id IS NOT NULL) ORDER BY s.id", (start, end, run, run))
        if sales:
            districts, rate = prop.districts(conn), prop.policy_rate(conn)
            for sale in sales:
                p = _one(conn, "SELECT * FROM properties WHERE id = %s", (sale["property_id"],))
                fair = prop.value(p, districts[p["district_id"]], rate)
                found += _gift(conn, day, f"property:{sale['id']}", _account(conn, sale["buyer"]), _account(conn, sale["seller"]), sale["price"],
                               fair, {"sale": sale["id"], "price": sale["price"], "fair": fair}, now)
    return found


def clear_flag(conn: Connection, flag_id: int, why: str, now: datetime) -> None:
    """An administrator has looked and found nothing wrong."""
    conn.execute("UPDATE talent_flags SET cleared_at = %s, cleared_why = %s WHERE id = %s AND cleared_at IS NULL", (now, why[:300], flag_id))


# ---------------------------------------------------------------------------
# The heartbeat: after each closing bell
# ---------------------------------------------------------------------------

def tick(conn: Connection, now: datetime) -> int:
    """After each closing bell: check the day's trades, then work every record out afresh. Returns records worked out."""
    if not ready(conn):
        return 0
    with conn.transaction():
        conn.execute("DELETE FROM visitor_marks WHERE day < %s", (clock.to_lagos(now).date() - timedelta(days=MARKS_KEPT_DAYS),))
    progress = _one(conn, "SELECT checked_through FROM talent_progress")
    days = [r["session_date"] for r in _rows(conn, "SELECT session_date FROM closing_bells WHERE %s::date IS NULL OR session_date > %s"
                                                   " ORDER BY session_date", (progress["checked_through"], progress["checked_through"]))]
    if not days:
        from simulation import challenges
        challenges.tick(conn, now)
        return 0
    for day in days:
        with conn.transaction():
            check_trades(conn, day, now)
            check_other_deals(conn, day, now)
            conn.execute("UPDATE talent_progress SET checked_through = %s", (day,))
    done = 0
    for p in _rows(conn, "SELECT id FROM players ORDER BY created_at"):
        try:
            with conn.transaction():
                refresh(conn, p["id"], now)
            done += 1
        except Exception:                                # one record that cannot be worked out never stops the rest
            log.exception("Proven Talent: a record could not be worked out")
    from simulation import challenges
    challenges.tick(conn, now)
    return done
