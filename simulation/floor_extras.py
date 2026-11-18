"""Floor extras, slice 1 (owner, 17 November 2026: "build"): flash storms and the risk engine.

A flash storm. Without warning, for ten minutes, the computer clients flood the open player desks: calls come four times
as often, three times as big, with fifteen-second countdowns, and seven in ten are in one share (the day's biggest mover,
which is why the clients are rushing). It is drawn for each ten-minute slot of an open market from the world's secret, so
nobody can know it in advance. Its best three banks and clients are named on the Floor and earn their empires league
points (3, 2, 1).

The risk engine. A bank's desk has three limits, as at a real bank:

  * the largest single deal it may price;
  * the most it may hold in one share from the Floor today (what it has bought from clients, less what it has sold);
  * the most it may lose in a day (today's Floor deals, marked to the market's price now).

The Risk Manager (or the head) of the banker's empire sets them, up to five times the Floor's own; a banker with no empire
works to the Floor's own. A price that would break the deal or share limit is refused, with the reason (a block is cleared on its own, and a
basket is many small deals: neither meets those two limits, but both count towards the day's loss). A day's loss past
the limit freezes the desk: it closes and cannot reopen until the next trading day, and the Floor is told.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from psycopg import Connection

from simulation import clock, exchange
from simulation import floor as fl
from simulation import world_data as data
from simulation.floor import BPS, FloorError, _money, _one, _rows, _unit


def ready(conn: Connection) -> bool:
    return _one(conn, "SELECT to_regclass('floor_storms') IS NOT NULL AS ok")["ok"]


# ---------------------------------------------------------------------------
# Flash storms
# ---------------------------------------------------------------------------

SLOT_SECONDS = 600


def storm_now(conn: Connection, now: datetime) -> dict | None:
    if not ready(conn):
        return None
    return _one(conn, "SELECT s.*, c.ticker, c.name AS company FROM floor_storms s JOIN companies c ON c.id = s.company_id"
                      " WHERE s.starts_at <= %s AND s.ends_at > %s ORDER BY s.id DESC LIMIT 1", (now, now))


def _mover(conn: Connection, seed: str, slot: int) -> tuple[dict, str]:
    """The share the storm is about: the day's biggest mover, or (on a quiet day) one drawn from the listed shares."""
    rows = _rows(conn, "SELECT c.id, c.ticker, c.name, m.last_price, m.reference_price FROM companies c"
                       " JOIN market_instruments m ON m.company_id = c.id WHERE m.halted_reason IS NULL ORDER BY c.ticker")
    moved = [(abs((r["last_price"] - r["reference_price"]) * BPS // r["reference_price"]), r) for r in rows
             if r["last_price"] and r["reference_price"]]
    moved.sort(key=lambda m: (-m[0], m[1]["ticker"]))
    if moved and moved[0][0] >= 200:
        move, r = moved[0]
        up = r["last_price"] > r["reference_price"]
        return r, f"{r['ticker']} is {'up' if up else 'down'} {move / 100:.1f}% today, and the clients are rushing to {'buy' if up else 'sell'}."
    r = rows[int(_unit(seed, "storm-share", slot) * len(rows))]
    return r, f"A rumour about {r['name']} has the clients calling every desk at once."


def storms_tick(conn: Connection, now: datetime) -> None:
    """Draw a storm for this ten-minute slot (if one falls in it), and score any storm that has ended."""
    if not ready(conn):
        return
    seed = fl._seed(conn)
    slot = int(now.timestamp()) // SLOT_SECONDS
    if clock.market_state(now).value == "open" and fl.floor_hour(now) is None \
            and not _one(conn, "SELECT 1 AS x FROM floor_storms WHERE slot = %s", (slot,)) \
            and _unit(seed, "storm", slot) * data.FLOOR_STORM_CHANCE < 1:
        company, reason = _mover(conn, seed, slot)
        starts = datetime.fromtimestamp(slot * SLOT_SECONDS, tz=now.tzinfo)
        ends = starts + timedelta(minutes=data.FLOOR_STORM_MINUTES)
        if ends > now:
            row = _one(conn, "INSERT INTO floor_storms (slot, starts_at, ends_at, company_id, reason) VALUES (%s, %s, %s, %s, %s)"
                             " ON CONFLICT (slot) DO NOTHING RETURNING id", (slot, starts, ends, company["id"], reason))
            if row:
                fl._note(conn, f"storm:{row['id']}:start", "storm", f"Flash storm! {reason} For the next {data.FLOOR_STORM_MINUTES} minutes the "
                         "clients call every open desk, four times as often and three times as big. Price fast.", now, company["ticker"])
                for d in _rows(conn, "SELECT player_id FROM floor_desks WHERE open"):
                    fl._ping_player(conn, d["player_id"])         # every open desk hears the storm at once
    for s in _rows(conn, "SELECT * FROM floor_storms WHERE NOT scored AND ends_at <= %s ORDER BY id FOR UPDATE SKIP LOCKED", (now,)):
        _score(conn, s, now)


def _score(conn: Connection, storm: dict, now: datetime) -> list[dict]:
    from simulation import careers, empires, leagues
    period = careers.world_now(conn, now)["period"]

    def award(player, role, place):
        seat = empires.seat_of(conn, player)
        if not seat or seat["empire_status"] != "active" or seat["empire_kind"] != "player":
            return 0
        points = data.FLOOR_STORM_PLACES[place - 1]
        leagues.award(conn, seat["empire_id"], points, f"A flash storm on the Floor: one of the best {'banks' if role == 'bank' else 'clients'}",
                      period, now, reference=f"storm:{storm['id']}:{role}:{place}")
        return points
    ranked = fl._rank(conn, f"storm:{storm['id']}", fl._window_scores(conn, storm["starts_at"], storm["ends_at"]), now, award)
    conn.execute("UPDATE floor_storms SET scored = true WHERE id = %s", (storm["id"],))
    names = {str(r["player"]): _one(conn, "SELECT display_name FROM players WHERE id = %s", (r["player"],))["display_name"] for r in ranked}
    fl._note(conn, f"storm:{storm['id']}:end", "storm", "The flash storm has passed. " + ("Best: " + "; ".join(
        f"{names[str(r['player'])]} ({'bank' if r['role'] == 'bank' else 'client'}, {r['place']})" for r in ranked) + "."
        if ranked else "Nobody dealt in it."), now)
    return ranked


def storm_call(conn: Connection, now: datetime, seed: str, slot: int, player_id, ticker: str, value: int, seconds: int) -> tuple:
    """How a storm changes one computer client's call: more likely, in the storm's share, bigger and quicker."""
    storm = storm_now(conn, now)
    if storm is None:
        return 1, ticker, value, seconds
    if _unit(seed, "storm-focus", slot, player_id) * BPS < data.FLOOR_STORM_FOCUS_BPS:
        ticker = storm["ticker"]
    return data.FLOOR_STORM_CALL_FACTOR, ticker, value * data.FLOOR_STORM_SIZE_FACTOR, data.FLOOR_STORM_SECONDS


# ---------------------------------------------------------------------------
# The risk engine
# ---------------------------------------------------------------------------

def floor_limits() -> dict:
    return {k: v * 100 for k, v in data.FLOOR_LIMITS.items()}


def limits_of(conn: Connection, banker) -> dict:
    row = _one(conn, "SELECT l.*, p.display_name AS set_by_name FROM floor_limits l JOIN players p ON p.id = l.set_by WHERE l.player_id = %s",
               (banker,)) if ready(conn) else None
    if row:
        return {"deal_most": row["deal_most"], "name_most": row["name_most"], "day_loss_most": row["day_loss_most"],
                "set_by": row["set_by_name"], "set_at": row["set_at"]}
    return {**floor_limits(), "set_by": None, "set_at": None}


def _today(now: datetime):
    return exchange.session_of(now)[0]


def _day_start(now: datetime) -> datetime:
    """When the trading day `now` belongs to began: the last close (22:00 Lagos)."""
    lagos = clock.to_lagos(now)
    close = lagos.replace(hour=clock.MARKET_CLOSE.hour, minute=0, second=0, microsecond=0)
    return close if close <= lagos else close - timedelta(days=1)


def _desk_trades(conn: Connection, banker, now: datetime) -> list[dict]:
    return _rows(conn, "SELECT t.*, c.ticker FROM floor_trades t JOIN companies c ON c.id = t.company_id"
                       " WHERE t.desk = %s AND t.at >= %s AND t.at <= %s AND t.company_id IS NOT NULL ORDER BY t.id",
                 (f"player:{banker}", _day_start(now), now))


def positions(conn: Connection, banker, now: datetime) -> dict:
    """What the desk holds in each share from today's Floor deals: bought from clients, less sold to them."""
    out: dict = {}
    for t in _desk_trades(conn, banker, now):
        out[t["ticker"]] = out.get(t["ticker"], 0) + (-t["quantity"] if t["client_bought"] else t["quantity"])
    return out


def day_pnl(conn: Connection, banker, now: datetime) -> int:
    """Today's Floor deals, marked to the market's price now: what the desk has made or lost on them."""
    marks: dict = {}
    total = 0
    for t in _desk_trades(conn, banker, now):
        if t["ticker"] not in marks:
            share = fl._share(conn, t["ticker"], now)
            marks[t["ticker"]] = share["last_price"] or share["reference_price"]
        mark = marks[t["ticker"]]
        total += (t["price"] - mark) * t["quantity"] if t["client_bought"] else (mark - t["price"]) * t["quantity"]
    from simulation import (
        floor_bank,  # loans closed today: interest earned, less what failed clients did not repay
    )
    return total + floor_bank.day_result(conn, banker, _day_start(now), now)


def frozen(conn: Connection, banker, now: datetime) -> dict | None:
    if not ready(conn):
        return None
    return _one(conn, "SELECT * FROM floor_freezes WHERE player_id = %s AND day = %s", (banker, _today(now)))


def check_quote(conn: Connection, banker, request: dict, bid: int | None, offer: int | None, now: datetime) -> None:
    """Called before a banker's price is accepted: a frozen desk prices nothing; a price that would break the deal or share
    limit is refused, with which limit and by how much."""
    if not ready(conn):
        return
    if frozen(conn, banker, now):
        raise FloorError("Your desk is frozen for the rest of the trading day: today's losses passed your limit. It may open again "
                         "tomorrow.")
    if request["kind"] == "basket" or request["block"]:
        return                                    # a basket is many small deals; a block is cleared on its own, as at a real bank
    limits = limits_of(conn, banker)
    price = max(p for p in (bid, offer) if p is not None)
    value = price * request["quantity"]
    if value > limits["deal_most"]:
        raise FloorError(f"That deal would be worth {_money(value)}, above your desk's limit of {_money(limits['deal_most'])} for one deal.")
    if request["kind"] != "share":
        return
    held = positions(conn, banker, now).get(request["ticker"], 0)
    for side, p in (("bid", bid), ("offer", offer)):
        if p is None:
            continue
        after = held + request["quantity"] if side == "bid" else held - request["quantity"]
        if abs(after) * p > limits["name_most"] and abs(after) > abs(held):
            raise FloorError(f"{'Buying' if side == 'bid' else 'Selling'} that would leave your desk {'long' if after > 0 else 'short'} "
                             f"{abs(after):,} {request['ticker']} from today's Floor deals, worth {_money(abs(after) * p)}: above your limit of "
                             f"{_money(limits['name_most'])} in one share.")


def freeze_tick(conn: Connection, now: datetime) -> int:
    """A desk whose day's loss has passed its limit is frozen until the next trading day."""
    if not ready(conn):
        return 0
    frozen_now = 0
    for d in _rows(conn, "SELECT DISTINCT substr(t.desk, 8)::uuid AS player_id FROM floor_trades t WHERE t.desk LIKE 'player:%%' AND t.at >= %s",
                   (_day_start(now),)):
        banker = d["player_id"]
        if frozen(conn, banker, now):
            continue
        loss = -day_pnl(conn, banker, now)
        limit = limits_of(conn, banker)["day_loss_most"]
        if loss > limit:
            conn.execute("INSERT INTO floor_freezes (player_id, day, loss, limit_was, at) VALUES (%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
                         (banker, _today(now), loss, limit, now))
            conn.execute("UPDATE floor_desks SET open = false, changed_at = %s WHERE player_id = %s", (now, banker))
            conn.execute("UPDATE floor_quotes q SET status = 'replaced' FROM floor_requests r WHERE r.id = q.request_id"
                         " AND q.desk = %s AND q.status = 'live' AND r.status = 'open'", (f"player:{banker}",))
            name = _one(conn, "SELECT display_name FROM players WHERE id = %s", (banker,))["display_name"]
            fl._note(conn, f"freeze:{banker}:{_today(now)}", "risk", f"Risk: {name}'s desk is frozen for the day. It lost {_money(loss)} "
                     f"on today's Floor deals, past its limit of {_money(limit)}.", now)
            fl._ping_player(conn, banker)
            frozen_now += 1
    return frozen_now


def _who_sets(conn: Connection, setter, banker) -> dict:
    from simulation import empires
    mine, theirs = empires.seat_of(conn, setter), empires.seat_of(conn, banker)
    if not mine or not theirs or mine["empire_id"] != theirs["empire_id"]:
        raise FloorError("Only the Risk Manager or the head of the banker's own empire sets their limits.")
    if mine["build"] != "risk_manager" and mine["head_player_id"] != setter:
        raise FloorError("Only the Risk Manager or the head of the empire sets a banker's limits.")
    if theirs["build"] != "investment_banker":
        raise FloorError("Limits are set for the empire's investment bankers.")
    return mine


def set_limits(conn: Connection, setter, banker, deal_most: int, name_most: int, day_loss_most: int, now: datetime) -> dict:
    """The Risk Manager (or the head) sets a banker's three limits, each above nought and at most five times the Floor's own."""
    _who_sets(conn, setter, banker)
    base = floor_limits()
    for key, value in (("deal_most", deal_most), ("name_most", name_most), ("day_loss_most", day_loss_most)):
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            raise FloorError("Each limit is a sum above nought.")
        if value > base[key] * data.FLOOR_LIMITS_MOST_FACTOR:
            raise FloorError(f"A limit may be at most {data.FLOOR_LIMITS_MOST_FACTOR} times the Floor's own ({_money(base[key] * data.FLOOR_LIMITS_MOST_FACTOR)}).")
    conn.execute("INSERT INTO floor_limits (player_id, deal_most, name_most, day_loss_most, set_by, set_at) VALUES (%s, %s, %s, %s, %s, %s)"
                 " ON CONFLICT (player_id) DO UPDATE SET deal_most = EXCLUDED.deal_most, name_most = EXCLUDED.name_most,"
                 " day_loss_most = EXCLUDED.day_loss_most, set_by = EXCLUDED.set_by, set_at = EXCLUDED.set_at",
                 (banker, deal_most, name_most, day_loss_most, setter, now))
    fl._ping_player(conn, banker)
    return limits_of(conn, banker)


def _usage(conn: Connection, banker, now: datetime) -> dict:
    limits = limits_of(conn, banker)
    held = positions(conn, banker, now)
    biggest = None
    for ticker, shares in held.items():
        if shares:
            share = fl._share(conn, ticker, now)
            worth = abs(shares) * (share["last_price"] or share["reference_price"])
            if biggest is None or worth > biggest["worth"]:
                biggest = {"ticker": ticker, "shares": shares, "worth": worth}
    pnl = day_pnl(conn, banker, now)
    f = frozen(conn, banker, now)
    return {"limits": limits, "biggest": biggest, "day_pnl": pnl, "frozen": bool(f), "frozen_loss": f["loss"] if f else None,
            "loss_used_bps": min(max(-pnl, 0) * BPS // limits["day_loss_most"], BPS * 2),
            "name_used_bps": min(biggest["worth"] * BPS // limits["name_most"], BPS * 2) if biggest else 0}


def view(conn: Connection, player_id, now: datetime) -> dict:
    """The storm now (if any), the banker's own limits and use of them, and for a Risk Manager or a head, the empire's bankers."""
    if not ready(conn):
        return {"ready": False}
    from simulation import empires
    storm = storm_now(conn, now)
    me = _one(conn, "SELECT build FROM players WHERE id = %s", (player_id,))
    out: dict = {"ready": True, "base": floor_limits(), "most_factor": data.FLOOR_LIMITS_MOST_FACTOR,
                 "storm": {"ticker": storm["ticker"], "company": storm["company"], "reason": storm["reason"], "ends_at": storm["ends_at"]}
                 if storm else None,
                 "storms_today": _rows(conn, "SELECT s.starts_at, c.ticker, s.reason FROM floor_storms s JOIN companies c ON c.id = s.company_id"
                                             " WHERE s.starts_at >= %s AND s.starts_at <= %s ORDER BY s.starts_at DESC", (_day_start(now), now))}
    if me and me["build"] == "investment_banker":
        out["mine"] = _usage(conn, player_id, now)
    seat = empires.seat_of(conn, player_id)
    if seat and seat["empire_kind"] == "player" and (seat["build"] == "risk_manager" or seat["head_player_id"] == player_id):
        out["team"] = [{"player_id": str(b["player_id"]), "name": b["display_name"], **_usage(conn, b["player_id"], now)}
                       for b in _rows(conn, "SELECT s.player_id, p.display_name FROM empire_seats s JOIN players p ON p.id = s.player_id"
                                            " WHERE s.empire_id = %s AND s.build = 'investment_banker' ORDER BY p.display_name", (seat["empire_id"],))]
    return out
