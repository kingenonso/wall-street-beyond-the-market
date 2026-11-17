"""Prediction markets (owner, 16 November 2026: "build").

Players buy YES or NO on things the game itself decides. A winning share pays ₦100; the price of YES is the crowd's
chance that it happens. The computer makes the market by the logarithmic market scoring rule: the cost of the shares
sold so far is b·ln(e^(yes/b) + e^(no/b)) (in ₦100 units), a buyer pays the difference that their shares make, and the
price of YES is e^(yes/b) / (e^(yes/b) + e^(no/b)). There is always a price, every purchase moves it, and the most the
market maker can lose on one question is b·ln 2 shares' worth. Money moves between the player and the computer's
public investors (who are the market maker), so none is made or lost.

The questions, made by the game:
  rate_rise    will the Central Bank's rate rise at the close of this quarter?
  profit_beat  will this company's profit this quarter beat last quarter's? (the largest companies)
  live_kind    will the next live event be a run on a bank?
  live_fall    will the live event's featured share fall more than 3% by its end? (open for its first ten minutes)
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta

from psycopg import Connection
from psycopg.rows import dict_row

from simulation import careers, clock, ledger
from simulation import world_data as data
from simulation.ledger import Leg

BPS = 10_000
KIND_WORDS = {"rate_rise": "Interest rates", "profit_beat": "Company results", "live_kind": "Live events", "live_fall": "Live events",
              "union_wave": "Strikes", "general_strike": "Strikes"}


class PredictionError(Exception):
    """A bet the rules do not allow, with a message for the player."""


def _rows(conn: Connection, sql: str, params=()) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def _one(conn: Connection, sql: str, params=()) -> dict | None:
    rows = _rows(conn, sql, params)
    return rows[0] if rows else None


def ready(conn: Connection) -> bool:
    return bool(_one(conn, "SELECT to_regclass('prediction_markets') IS NOT NULL AS ok")["ok"])


# ---------------------------------------------------------------------------
# The market maker's rule
# ---------------------------------------------------------------------------

def _cost(q_yes: float, q_no: float, b: float) -> float:
    """b·ln(e^(yes/b) + e^(no/b)), worked out without overflowing."""
    top = max(q_yes, q_no) / b
    return b * (top + math.log(math.exp(q_yes / b - top) + math.exp(q_no / b - top)))


def chance_bps(m: dict) -> int:
    """The price of YES: the crowd's chance that it happens, in hundredths of a percent."""
    a, c = m["q_yes"] / m["b"], m["q_no"] / m["b"]
    return round(BPS / (1 + math.exp(c - a)))


def quote(m: dict, side: str, shares: int) -> int:
    """What buying (above nought) or selling back (below nought) so many shares of a side costs, in kobo: rounded up for a
    buyer and down for a seller, so the rounding never makes money for anybody."""
    yes, no = m["q_yes"], m["q_no"]
    after = (yes + shares, no) if side == "yes" else (yes, no + shares)
    exact = (_cost(*after, m["b"]) - _cost(yes, no, m["b"])) * data.PREDICT_PAYOUT
    return math.ceil(exact) if shares > 0 else math.floor(exact)


# ---------------------------------------------------------------------------
# Trading
# ---------------------------------------------------------------------------

def _house(conn: Connection):
    return ledger.account_id(conn, ledger.INVESTORS_PUBLIC)


def _decides(conn: Connection, player_id, m: dict, now: datetime) -> bool:
    """The one who decides an answer may not bet on it: the Government Leader, who can set the rate by decree and answers the
    federation's notice of a general strike."""
    if m["kind"] not in ("rate_rise", "general_strike") or not _one(conn, "SELECT to_regclass('government_terms') IS NOT NULL AS ok")["ok"]:
        return False
    from simulation import government
    leader = government.leader(conn, government.year_of(careers.world_now(conn, now)["period"]))
    return bool(leader and str(leader["leader_id"]) == str(player_id))


def trade(conn: Connection, player_id, market_id: int, side: str, shares: int, now: datetime) -> dict:
    """Buy shares of YES or NO (shares above nought), or sell some back (below nought) at the market maker's price."""
    if side not in ("yes", "no"):
        raise PredictionError("Buy YES or NO.")
    if not isinstance(shares, int) or isinstance(shares, bool) or shares == 0 or abs(shares) > data.PREDICT_MOST_SHARES:
        raise PredictionError(f"Trade 1 to {data.PREDICT_MOST_SHARES:,} shares at a time.")
    account = ledger.player_account_id(conn, player_id)
    if account is None:
        raise PredictionError("Your account is not open yet.")
    with conn.transaction():
        m = _one(conn, "SELECT * FROM prediction_markets WHERE id = %s FOR UPDATE", (market_id,))
        if m is None:
            raise PredictionError("There is no such question.")
        if m["status"] != "open" or now >= m["closes_at"]:
            raise PredictionError("Betting on that question has closed.")
        if _decides(conn, player_id, m, now):
            raise PredictionError("The Government Leader can set the rate by decree, so may not bet on it.")
        pos = _one(conn, "SELECT * FROM prediction_positions WHERE market_id = %s AND account_id = %s FOR UPDATE", (market_id, account)) \
            or {"yes": 0, "no": 0, "paid": 0}
        if pos[side] + shares < 0:
            raise PredictionError(f"You hold only {pos[side]:,} {side.upper()} shares.")
        amount = quote(m, side, shares)
        if amount > 0:
            if pos["paid"] + amount > data.PREDICT_MOST_STAKE_NAIRA * 100:
                raise PredictionError(f"One player may have at most ₦{data.PREDICT_MOST_STAKE_NAIRA:,} in one question.")
            if ledger.balance(conn, account) < amount:
                raise PredictionError(f"That costs ₦{amount / 100:,.2f}. You have not that much cash.")
            ledger.post(conn, kind="prediction", memo=f"{shares:,} {side.upper()}: {m['question'][:120]}", reference=f"prediction:{market_id}",
                        legs=[Leg(account, -amount), Leg(_house(conn), amount)])
        elif amount < 0:
            ledger.post(conn, kind="prediction", memo=f"{-shares:,} {side.upper()} sold back: {m['question'][:110]}", reference=f"prediction:{market_id}",
                        legs=[Leg(_house(conn), amount), Leg(account, -amount)])
        column = "q_yes" if side == "yes" else "q_no"
        conn.execute(f"UPDATE prediction_markets SET {column} = {column} + %s WHERE id = %s", (shares, market_id))
        if "market_id" in pos:
            conn.execute(f"UPDATE prediction_positions SET {side} = {side} + %s, paid = paid + %s WHERE market_id = %s AND account_id = %s",
                         (shares, amount, market_id, account))
        else:
            conn.execute(f"INSERT INTO prediction_positions (market_id, account_id, {side}, paid) VALUES (%s, %s, %s, %s)",
                         (market_id, account, shares, amount))
        m = _one(conn, "SELECT * FROM prediction_markets WHERE id = %s", (market_id,))
        conn.execute("INSERT INTO prediction_trades (market_id, account_id, side, shares, amount, price_after, at) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                     (market_id, account, side, shares, amount, chance_bps(m), now))
    return {"amount": amount, "chance_bps": chance_bps(m)}


# ---------------------------------------------------------------------------
# Making the questions, and answering them
# ---------------------------------------------------------------------------

def _make(conn: Connection, key: str, kind: str, question: str, details: str, now: datetime, closes_at: datetime, **extra) -> None:
    cols = ["key", "kind", "question", "details", "opened_at", "closes_at", "b", *extra]
    vals = [key, kind, question, details, now, closes_at, data.PREDICT_DEPTH, *extra.values()]
    conn.execute(f"INSERT INTO prediction_markets ({', '.join(cols)}) VALUES ({', '.join(['%s'] * len(vals))}) ON CONFLICT (key) DO NOTHING", vals)


def _create(conn: Connection, now: datetime) -> None:
    from simulation import bonds, liveevents
    world = careers.world_now(conn, now)
    if not world["started"]:
        return
    period = world["period"]
    far = now + timedelta(days=60)                  # a quarter's question closes when the quarter does (see _answer)
    rate = bonds._policy(conn)
    _make(conn, f"rate:{period}", "rate_rise", "Will the Central Bank raise its rate at the close of this quarter?",
          f"The rate is {rate / 100:.2f}% now. YES if the rate it sets at this quarter's close is higher.", now, far, period=period, baseline=rate)
    for c in _rows(conn, "SELECT c.id, c.name, r.net_profit FROM companies c JOIN company_results r ON r.company_id = c.id AND r.period = %s"
                         " JOIN market_instruments m ON m.company_id = c.id ORDER BY coalesce(m.last_price, m.reference_price) * r.shares_in_issue DESC"
                         " LIMIT %s", (period - 1, data.PREDICT_PROFIT_COMPANIES)):
        _make(conn, f"profit:{period}:{c['id']}", "profit_beat", f"Will {c['name']} make more profit this quarter than last?",
              f"Last quarter it made ₦{c['net_profit'] / 100:,.0f}. YES if this quarter's profit is higher.", now, far,
              period=period, company_id=c["id"], baseline=c["net_profit"])
    from simulation import unions                       # strikes (unions, part 4, 17 November 2026)
    if unions.waves_ready(conn):
        for w in _rows(conn, "SELECT w.*, u.name AS union_name, s.name AS industry FROM union_waves w JOIN unions u ON u.id = w.union_id"
                             " JOIN sectors s ON s.code = u.sector WHERE w.period = %s AND w.status = 'open' AND w.opened_day <= %s",
                       (period, world["day"])):
            _make(conn, f"wave:{w['id']}", "union_wave", f"Will the {w['union_name']} strike across {w['industry'].lower()}?",
                  f"It asks {w['demand_bps'] / 100:g}% of {w['companies']} employers at once, who answer together on day {w['deadline_day']}."
                  " YES if they walk out.", now, unions.moment_of(conn, period, w["deadline_day"]), period=period, baseline=w["id"])
        g = _one(conn, "SELECT * FROM general_strikes WHERE period = %s AND status = 'notice' AND notice_day <= %s", (period, world["day"]))
        if g:
            _make(conn, f"general:{g['id']}", "general_strike", "Will the general strike go ahead?",
                  f"The {data.GENERAL_FEDERATION[0]} wants a cost-of-living award of ₦{g['award'] / 100:,.0f} by day {g['deadline_day']}."
                  " YES if the Government refuses and the country stops.", now, unions.moment_of(conn, period, g["deadline_day"]),
                  period=period, baseline=g["id"])
    if liveevents.ready(conn):
        bell = liveevents.next_slot(now)
        when = clock.to_lagos(bell).strftime("%A at %H:%M")
        _make(conn, f"live-kind:{bell.isoformat()}", "live_kind", f"Will the next live event ({when}) be a run on a bank?",
              "One of five kinds happens at each bell, chosen from the world's secret, never the same twice in a row. "
              "YES if it is a bank run.", now, bell, bell=bell)
        event = _one(conn, "SELECT * FROM live_events WHERE status = 'open' AND predict_until > %s ORDER BY starts_at DESC LIMIT 1", (now,))
        if event:
            ticker = _one(conn, "SELECT ticker FROM companies WHERE id = %s", (event["featured_company_id"],))["ticker"]
            _make(conn, f"live-fall:{event['id']}", "live_fall",
                  f"Will {ticker} fall more than {data.PREDICT_LIVE_FALL_BPS / 100:g}% in this live event?",
                  f"{event['headline']} YES if {ticker} ends the event more than {data.PREDICT_LIVE_FALL_BPS / 100:g}% below its price at the bell.",
                  now, event["predict_until"], bell=event["starts_at"], company_id=event["featured_company_id"], baseline=event["start_price"])


def _answer(conn: Connection, m: dict, now: datetime) -> bool | str | None:
    """The answer, if the game has decided it yet: True, False, "void", or None (not yet)."""
    if m["kind"] == "rate_rise":
        row = _one(conn, "SELECT next_policy_rate_bps AS r FROM economy_results WHERE period = %s", (m["period"],))
        return None if row is None else row["r"] > m["baseline"]
    if m["kind"] == "profit_beat":
        row = _one(conn, "SELECT net_profit FROM company_results WHERE company_id = %s AND period = %s", (m["company_id"], m["period"]))
        return None if row is None else row["net_profit"] > m["baseline"]
    if m["kind"] == "union_wave":
        w = _one(conn, "SELECT status FROM union_waves WHERE id = %s", (m["baseline"],))
        return None if w is None or w["status"] == "open" else w["status"] in ("struck", "ended")
    if m["kind"] == "general_strike":
        g = _one(conn, "SELECT status FROM general_strikes WHERE id = %s", (m["baseline"],))
        return None if g is None or g["status"] == "notice" else g["status"] in ("striking", "over")
    if m["kind"] == "live_kind":
        event = _one(conn, "SELECT kind FROM live_events WHERE starts_at = %s", (m["bell"],))
        if event:
            return event["kind"] == "bank_run"
        return "void" if now > m["bell"] + timedelta(hours=1) else None
    event = _one(conn, "SELECT * FROM live_events WHERE starts_at = %s", (m["bell"],))
    if event is None or event["status"] != "scored" or not event["end_price"]:
        return None
    return (event["end_price"] - m["baseline"]) * BPS < -data.PREDICT_LIVE_FALL_BPS * m["baseline"]


def _settle(conn: Connection, m: dict, answer, now: datetime) -> None:
    house = _house(conn)
    with conn.transaction():
        for p in _rows(conn, "SELECT * FROM prediction_positions WHERE market_id = %s FOR UPDATE", (m["id"],)):
            if answer == "void":
                owed = max(p["paid"], 0)                 # a question that came to nothing hands back what was put in
            else:
                owed = (p["yes"] if answer else p["no"]) * data.PREDICT_PAYOUT
            if owed > 0:
                ledger.post(conn, kind="prediction", memo=f"{'Refund' if answer == 'void' else 'Winnings'}: {m['question'][:120]}",
                            reference=f"prediction-paid:{m['id']}", legs=[Leg(house, -owed), Leg(p["account_id"], owed)])
                conn.execute("UPDATE prediction_positions SET paid_out = %s WHERE market_id = %s AND account_id = %s", (owed, m["id"], p["account_id"]))
        conn.execute("UPDATE prediction_markets SET status = %s, outcome = %s, resolved_at = %s WHERE id = %s",
                     ("void" if answer == "void" else "resolved", None if answer == "void" else answer, now, m["id"]))


def tick(conn: Connection, now: datetime) -> None:
    """Make the questions that are due, stop betting on those whose time is up, and answer what the game has decided."""
    if not ready(conn):
        return
    _create(conn, now)
    for m in _rows(conn, "SELECT * FROM prediction_markets WHERE status IN ('open', 'closed') ORDER BY id"):
        answer = _answer(conn, m, now)
        if answer is not None:
            _settle(conn, m, answer, now)
        elif m["status"] == "open" and now >= m["closes_at"]:
            conn.execute("UPDATE prediction_markets SET status = 'closed' WHERE id = %s", (m["id"],))
    # A quarter's questions close the moment the quarter does, before its answer is worked out.
    period = careers.world_now(conn, now)["period"]
    conn.execute("UPDATE prediction_markets SET status = 'closed', closes_at = %s WHERE status = 'open' AND period IS NOT NULL AND period < %s",
                 (now, period))


# ---------------------------------------------------------------------------
# What the player sees
# ---------------------------------------------------------------------------

def view(conn: Connection, player_id, now: datetime) -> dict:
    if not ready(conn):
        return {"ready": False}
    account = ledger.player_account_id(conn, player_id)
    out = []
    for m in _rows(conn, "SELECT * FROM prediction_markets WHERE status IN ('open', 'closed') OR resolved_at > %s"
                         " ORDER BY status = 'open' DESC, closes_at, id DESC LIMIT 40", (now - timedelta(days=3),)):
        pos = _one(conn, "SELECT yes, no, paid, paid_out FROM prediction_positions WHERE market_id = %s AND account_id = %s", (m["id"], account)) \
            if account else None
        history = [r["price_after"] for r in _rows(conn, "SELECT price_after FROM (SELECT id, price_after FROM prediction_trades WHERE market_id = %s"
                                                         " ORDER BY id DESC LIMIT 30) t ORDER BY id", (m["id"],))]
        worth = None
        if pos and m["status"] == "open":
            worth = -(quote(m, "yes", -pos["yes"]) if pos["yes"] else 0) - (quote(m, "no", -pos["no"]) if pos["no"] else 0)
        out.append({
            "id": m["id"], "kind": m["kind"], "area": KIND_WORDS[m["kind"]], "question": m["question"], "details": m["details"],
            "status": m["status"], "closes_at": m["closes_at"] if m["status"] == "open" and m["closes_at"] < now + timedelta(days=30) else None,
            "outcome": m["outcome"], "chance_bps": chance_bps(m), "history": history,
            "volume": _one(conn, "SELECT coalesce(sum(abs(shares)), 0)::bigint AS n FROM prediction_trades WHERE market_id = %s", (m["id"],))["n"],
            "cost_10_yes": quote(m, "yes", 10) if m["status"] == "open" else None, "cost_10_no": quote(m, "no", 10) if m["status"] == "open" else None,
            "yours": {"yes": pos["yes"], "no": pos["no"], "paid": pos["paid"], "paid_out": pos["paid_out"], "worth_now": worth} if pos and (pos["yes"] or pos["no"] or pos["paid_out"]) else None,
            "barred": _decides(conn, player_id, m, now),
        })
    return {"ready": True, "now": now, "markets": out, "payout": data.PREDICT_PAYOUT, "most_stake": data.PREDICT_MOST_STAKE_NAIRA * 100,
            "most_shares": data.PREDICT_MOST_SHARES}
