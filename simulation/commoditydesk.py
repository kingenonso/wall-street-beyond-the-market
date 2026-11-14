"""Stage 12, the firm's door: a commodities desk at a firm.

The companies that already exist in the game have the exposure. Airlines, hauliers, shipping
lines, power stations and factories buy fuel; cement makers and builders buy materials; food
and drink makers and shops buy farm produce; the oil and gas producers sell it. Until now they
simply carried that risk, apart from the little the exchange hedges for them at each close.

A desk changes that by standing in the middle. Each quarter it quotes those companies a price
for their goods, fixed for a quarter. A company that takes the quote pays a fee and gets
certainty. The desk does not carry the risk itself: it hedges on the exchange, through the same
clearing house everything else uses, and what it keeps is the fee and the edge.

What can hurt the desk is the gap. The client's contract is not the exchange's contract: the
hedge is in whole contracts around a quantity that rarely divides by one, the goods the client
means are not always the goods the future is on, and a client that loses can fail before it
pays — and then the desk has paid the exchange and has nothing to collect from the client. That
loss is the desk's own, out of the firm's money, and it is the reason the head sets a limit.

Nobody gets a seat they were not hired into: the desk belongs to the firm, any member of it may
work the book, and the head decides the limit.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime

from psycopg import Connection
from psycopg.rows import dict_row

from simulation import careers, commodities, derivatives, empires, firm, ledger, lending
from simulation import world_data as data
from simulation.money import BPS

log = logging.getLogger("wsbm.commoditydesk")


class DeskError(Exception):
    """Something the desk may not do. The words are for the player."""


def _rows(conn: Connection, sql: str, params=()) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def _one(conn: Connection, sql: str, params=()) -> dict | None:
    rows = _rows(conn, sql, params)
    return rows[0] if rows else None


def money(kobo: int) -> str:
    return f"₦{kobo / 100:,.0f}"


def _whole(value, least: int = 1) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= least


def _note(conn: Connection, empire_id, words: str, now: datetime) -> None:
    conn.execute("INSERT INTO empire_events (empire_id, kind, words, at) VALUES (%s, 'commodity_desk', %s, %s)",
                 (empire_id, words, now))


# ---------------------------------------------------------------------------
# Opening a desk
# ---------------------------------------------------------------------------

def desk_of(conn: Connection, empire_id) -> dict | None:
    return _one(conn, "SELECT * FROM commodity_desks WHERE empire_id = %s", (empire_id,))


def _open_desk(conn: Connection, player_id, now: datetime) -> dict:
    """The desk of the firm the player belongs to, if it has one."""
    seat = empires.seat_of(conn, player_id)
    if seat is None:
        raise DeskError("You do not work at a firm.")
    desk = desk_of(conn, seat["empire_id"])
    if desk is None or desk["status"] != "open":
        raise DeskError("Your firm has no commodities desk. The head opens one.")
    return desk


def open_desk(conn: Connection, player_id, limit_kobo: int, now: datetime) -> dict:
    """The head of a firm opens a commodities desk and says how much risk it may run."""
    seat = empires.seat_of(conn, player_id)
    if seat is None:
        raise DeskError("You do not work at a firm.")
    empire = empires.empire_of(conn, player_id)
    if empire is None:
        raise DeskError("You do not work at a firm.")
    head = empire.get("head_player_id")
    if str(head) != str(player_id):
        raise DeskError("Only the head of the firm opens a desk.")
    if desk_of(conn, empire["id"]):
        raise DeskError("Your firm already has a commodities desk.")
    if not _whole(limit_kobo, data.COMMODITY_DESK_LEAST_LIMIT):
        raise DeskError(f"A desk's limit is at least {money(data.COMMODITY_DESK_LEAST_LIMIT)}.")
    funds = max(ledger.balance(conn, empire["account_id"]), 0)
    most = funds * data.COMMODITY_DESK_MOST_LIMIT_BPS // BPS
    if limit_kobo > max(most, data.COMMODITY_DESK_LEAST_LIMIT):
        raise DeskError(f"The firm's own funds allow a limit of {money(max(most, data.COMMODITY_DESK_LEAST_LIMIT))}.")
    state = careers.world_now(conn, now)
    row = _one(conn, """INSERT INTO commodity_desks (empire_id, limit_kobo, opened_period, opened_at)
                        VALUES (%s, %s, %s, %s) RETURNING *""", (empire["id"], limit_kobo, state["period"], now))
    _note(conn, empire["id"], f"A commodities desk opened, with a limit of {money(limit_kobo)}", now)
    return row


def set_limit(conn: Connection, player_id, limit_kobo: int, now: datetime) -> dict:
    desk = _open_desk(conn, player_id)
    empire = empires.empire_of(conn, player_id)
    if str(empire.get("head_player_id")) != str(player_id):
        raise DeskError("Only the head of the firm sets the desk's limit.")
    used = in_use(conn, desk["id"])
    if not _whole(limit_kobo, max(used, data.COMMODITY_DESK_LEAST_LIMIT)):
        raise DeskError(f"The desk already carries {money(used)} of risk; its limit cannot be below that.")
    funds = max(ledger.balance(conn, empire["account_id"]), 0)
    most = max(funds * data.COMMODITY_DESK_MOST_LIMIT_BPS // BPS, data.COMMODITY_DESK_LEAST_LIMIT)
    if limit_kobo > most:
        raise DeskError(f"The firm's own funds allow a limit of {money(most)}.")
    conn.execute("UPDATE commodity_desks SET limit_kobo = %s WHERE id = %s", (limit_kobo, desk["id"]))
    desk["limit_kobo"] = limit_kobo
    _note(conn, empire["id"], f"The commodities desk's limit is now {money(limit_kobo)}", now)
    return desk


def in_use(conn: Connection, desk_id) -> int:
    """How much risk the desk already carries: what it has quoted and not yet settled."""
    row = _one(conn, """SELECT coalesce(sum(units * price), 0)::bigint AS v FROM commodity_quotes
                        WHERE desk_id = %s AND status IN ('quoted', 'accepted')""", (desk_id,))
    return int(row["v"])


def shut(conn: Connection, player_id, now: datetime) -> dict:
    seat = empires.seat_of(conn, player_id)
    if seat is None:
        raise DeskError("You do not work at a firm.")
    empire = empires.empire_of(conn, player_id)
    if str(empire.get("head_player_id")) != str(player_id):
        raise DeskError("Only the head of the firm shuts the desk.")
    desk = desk_of(conn, empire["id"])
    if desk is None or desk["status"] != "open":
        raise DeskError("Your firm has no open commodities desk.")
    if _one(conn, "SELECT 1 FROM commodity_quotes WHERE desk_id = %s AND status = 'accepted'", (desk["id"],)):
        raise DeskError("The desk still has accepted hedges running. It can shut when they have settled.")
    state = careers.world_now(conn, now)
    conn.execute("UPDATE commodity_desks SET status = 'shut', closed_period = %s WHERE id = %s", (state["period"], desk["id"]))
    _note(conn, empire["id"], "The commodities desk was shut", now)
    return desk_of(conn, empire["id"])


# ---------------------------------------------------------------------------
# Who the desk deals with
# ---------------------------------------------------------------------------

def clients(conn: Connection, good: str | None = None) -> list[dict]:
    """The companies the desk can quote: the ones that actually use or produce the goods."""
    out = []
    for code, pairs in data.COMMODITY_CLIENTS.items():
        if good and code != good:
            continue
        for sector, side in pairs:
            for c in _rows(conn, """SELECT c.id, c.ticker, c.name, c.sector, c.account_id,
                                           (SELECT r.revenue FROM company_results r WHERE r.company_id = c.id
                                            ORDER BY r.period DESC LIMIT 1) AS sales
                                    FROM companies c WHERE c.status = 'trading' AND c.sector = %s ORDER BY c.ticker""", (sector,)):
                out.append({**c, "good": code, "side": side})
    return out


def quote(conn: Connection, player_id, company_id, good: str, side: str, units: int, now: datetime) -> dict:
    """Quote a company a price for its goods, fixed to the end of next quarter."""
    desk = _open_desk(conn, player_id)
    g = commodities.good(conn, good) if isinstance(good, str) and good else None
    if g is None or side not in ("buy", "sell"):
        raise DeskError("A client either buys the goods or sells them.")
    state = careers.world_now(conn, now)
    expiry = state["period"] + 1
    row = _one(conn, """INSERT INTO commodity_quotes (desk_id, company_id, good, side, units, price, fee, expiry_period,
                                                       status, quoted_period, quoted_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'quoted', %s, %s) RETURNING *""",
               (desk["id"], company_id, good, side, units, price, fee, expiry, state["period"], now))
    return row


def decline(conn: Connection, player_id, quote_id: int, now: datetime) -> dict:
    """Take a quote back off the table before the client decides."""
    desk = _open_desk(conn, player_id)
    row = _one(conn, "SELECT * FROM commodity_quotes WHERE id = %s AND desk_id = %s", (quote_id, desk["id"]))
    if row is None:
        raise DeskError("There is no such quote of yours.")
    if row["status"] != "quoted":
        raise DeskError("That quote has already been answered.")
    conn.execute("UPDATE commodity_quotes SET status = 'declined', decided_at = %s WHERE id = %s", (now, quote_id))
    return {**row, "status": "declined"}


# ---------------------------------------------------------------------------
# The client decides, and the desk hedges
# ---------------------------------------------------------------------------

def _takes(conn: Connection, q: dict, period: int) -> bool:
    """Whether the company takes the price. It compares the quote with the market, and it does not take a price
    that is more than so far against it."""
    mid = commodities.quote(conn, q["good"], _now(conn))["spot"]
    if mid <= 0:
        return False
    gap = (q["price"] - mid) * BPS // mid
    if q["side"] == "sell":
        gap = -gap
    if abs(gap) > data.COMMODITY_CLIENT_TAKE_BPS:
        return False
    digest = hashlib.blake2b(f"client:{period}:{q['id']}".encode(), digest_size=8).digest()
    roll = int.from_bytes(digest, "big") % BPS
    # the further in the desk's favour the price is, the less likely the client is to take it
    edge = max(abs(gap) * BPS // max(data.COMMODITY_CLIENT_TAKE_BPS, 1), 0)
    return roll >= edge * 3 // 10


def _now(conn: Connection) -> datetime:
    return _one(conn, "SELECT now() AS n")["n"]


def _hedge_series(conn: Connection, good: str, expiry: int) -> dict | None:
    g = commodities.good(conn, good) if isinstance(good, str) and good else None
    if g is None:
        return None
    return _one(conn, "SELECT * FROM derivative_series WHERE kind = 'future' AND underlying = %s AND expiry_period = %s"
                      " AND status = 'open' ORDER BY id LIMIT 1", (g["underlying"], expiry))


def decide(conn: Connection, period: int, now: datetime) -> dict:
    """At the close: every waiting quote is answered, and what is taken is hedged on the exchange at once."""
    decided = taken = hedged = 0
    for q in _rows(conn, "SELECT * FROM commodity_quotes WHERE status = 'quoted' ORDER BY id"):
        with conn.transaction():
            q = _one(conn, "SELECT * FROM commodity_quotes WHERE id = %s AND status = 'quoted' FOR UPDATE", (q["id"],))
            if q is None:
                continue
            decided += 1
            if not _takes(conn, q, period):
                conn.execute("UPDATE commodity_quotes SET status = 'declined', decided_at = %s WHERE id = %s", (now, q["id"]))
                continue
            desk = _one(conn, "SELECT * FROM commodity_desks WHERE id = %s", (q["desk_id"],))
            empire = _one(conn, "SELECT * FROM empires WHERE id = %s", (desk["empire_id"],))
            series = _hedge_series(conn, q["good"], q["expiry_period"])
            if series is None:                                     # (nothing to hedge with: the desk cannot take it on)
                conn.execute("UPDATE commodity_quotes SET status = 'declined', decided_at = %s WHERE id = %s", (now, q["id"]))
                continue
            paid = ledger.pay_up_to(conn, payer=_company_account(conn, q["company_id"]), receiver=empire["account_id"],
                                    wanted=q["fee"], kind="commodity_fee",
                                    memo=f"The desk's fee on {q['units']:,} units of {q['good']}", period=period)
            conn.execute("UPDATE commodity_quotes SET status = 'accepted', decided_at = %s, client_paid = %s WHERE id = %s",
                         (now, paid, q["id"]))
            taken += 1
            if _place_hedge(conn, desk, q, series, period, now):
                hedged += 1
    return {"decided": decided, "taken": taken, "hedged": hedged}


def _company_account(conn: Connection, company_id):
    return _one(conn, "SELECT account_id FROM companies WHERE id = %s", (company_id,))["account_id"]


def _place_hedge(conn: Connection, desk: dict, q: dict, series: dict, period: int, now: datetime) -> bool:
    """The desk's own side: the exchange contract that offsets what it has promised the client."""
    g = commodities.good(conn, q["good"]) if isinstance(q["good"], str) and q["good"] else None
    if g is None:
        return False
    contracts = max(-(-int(q["units"]) // int(g["units_per_contract"])), 1)
    side = "buy" if q["side"] == "sell" else "sell"
    try:
        result = derivatives.trade(conn, _desk_account(conn, desk), series["id"], side, contracts, now, company=True)
    except Exception as error:                                     # (a hedge that cannot be placed is the desk's problem)
        log.debug("hedge not placed for quote %s: %s", q["id"], error)
        return False
    position_id = (result or {}).get("position_id") or (result or {}).get("position")
    conn.execute("""INSERT INTO commodity_hedges (desk_id, quote_id, series_id, contracts, position_id, placed_at, placed_period)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                 (desk["id"], q["id"], series["id"], contracts, position_id, now, period))
    return True


def _desk_account(conn: Connection, desk: dict):
    return _one(conn, "SELECT account_id FROM empires WHERE id = %s", (desk["empire_id"],))["account_id"]


# ---------------------------------------------------------------------------
# The quarter's end: what the market did, and who paid whom
# ---------------------------------------------------------------------------

def close(conn: Connection, period: int, now: datetime) -> dict:
    """At the close: quotes answered, hedged, and the ones that have run their quarter settled with the client."""
    if _one(conn, "SELECT to_regclass('commodity_desks') IS NOT NULL AS ok")["ok"] is not True:
        return {}
    done = decide(conn, period, now)
    settled = 0
    for q in _rows(conn, "SELECT * FROM commodity_quotes WHERE status = 'accepted' AND expiry_period <= %s ORDER BY id", (period,)):
        with conn.transaction():
            q = _one(conn, "SELECT * FROM commodity_quotes WHERE id = %s AND status = 'accepted' FOR UPDATE", (q["id"],))
            if q is None:
                continue
            desk = _one(conn, "SELECT * FROM commodity_desks WHERE id = %s", (q["desk_id"],))
            empire = _one(conn, "SELECT * FROM empires WHERE id = %s", (desk["empire_id"],))
            spot = commodities.spot(conn, q["good"], now)
            if spot <= 0:
                continue
            # What the quarter did against the price the client was promised. The desk's exchange hedge has already
            # settled its own side through the clearing house; this is only the client's leg.
            move = (spot - q["price"]) * int(q["units"])
            if q["side"] == "buy":
                owed_by_desk = max(move, 0)
                owed_by_client = max(-move, 0)
            else:
                owed_by_desk = max(-move, 0)
                owed_by_client = max(move, 0)
            paid_out = paid_in = 0
            if owed_by_desk:
                paid_out = ledger.pay_up_to(conn, payer=empire["account_id"], receiver=_company_account(conn, q["company_id"]),
                                            wanted=owed_by_desk, kind="commodity_settle",
                                            memo=f"The desk settles {q['units']:,} units of {q['good']} with its client",
                                            period=period)
            if owed_by_client:
                paid_in = ledger.pay_up_to(conn, payer=_company_account(conn, q["company_id"]), receiver=empire["account_id"],
                                           wanted=owed_by_client, kind="commodity_settle",
                                           memo=f"A client settles {q['units']:,} units of {q['good']} with the desk",
                                           period=period)
            short = owed_by_client - paid_in
            if short > 0:
                # A client that cannot pay is in default, and the desk carries what it cannot collect.
                lending.record_shortfall(conn, _company_account(conn, q["company_id"]), empire["account_id"], short,
                                         f"A hedge client's shortfall on {q['good']}", period, now)
            status = "failed" if (owed_by_desk and paid_out < owed_by_desk) or short else "settled"
            conn.execute("""UPDATE commodity_quotes SET status = %s, settled_at = %s, client_paid = client_paid + %s,
                            desk_paid = desk_paid + %s WHERE id = %s""", (status, now, paid_in, paid_out, q["id"]))
            settled += 1
    return {**done, "settled": settled}


def results(conn: Connection, desk_id, period: int) -> None:
    """The desk's quarter onto the permanent record."""
    row = _one(conn, """SELECT count(*) FILTER (WHERE status <> 'quoted') AS quoted,
                               count(*) FILTER (WHERE status IN ('accepted', 'settled', 'failed')) AS accepted,
                               coalesce(sum(fee), 0)::bigint AS fees,
                               coalesce(sum(units), 0)::bigint AS units,
                               coalesce(sum(client_paid), 0)::bigint AS client_paid,
                               coalesce(sum(desk_paid), 0)::bigint AS desk_paid
                        FROM commodity_quotes WHERE desk_id = %s AND quoted_period = %s""", (desk_id, period))
    conn.execute("""INSERT INTO commodity_desk_results (desk_id, period, quoted, accepted, fees, hedged_units, client_paid, desk_paid)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (desk_id, period) DO NOTHING""",
                 (desk_id, period, int(row["quoted"]), int(row["accepted"]), int(row["fees"]), int(row["units"]),
                  int(row["client_paid"]), int(row["desk_paid"])))


def check_books(conn: Connection) -> list[str]:
    """Anything the desks have done that does not add up."""
    if _one(conn, "SELECT to_regclass('commodity_desks') IS NOT NULL AS ok")["ok"] is not True:
        return []
    out: list[str] = []
    for row in _rows(conn, """SELECT q.id, q.status, h.contracts FROM commodity_quotes q
                              LEFT JOIN commodity_hedges h ON h.quote_id = q.id
                              WHERE q.status = 'accepted' AND h.id IS NULL"""):
        out.append(f"Commodity desk: quote {row['id']} is accepted with no hedge behind it.")
    for row in _rows(conn, "SELECT id FROM commodity_quotes WHERE status NOT IN ('quoted','accepted','declined','expired','settled','failed')"):
        out.append(f"Commodity desk: quote {row['id']} has a status nobody can read.")
    for row in _rows(conn, "SELECT id FROM commodity_desks WHERE limit_kobo <= 0"):
        out.append(f"Commodity desk {row['id']} has no limit.")
    return out


# ---------------------------------------------------------------------------
# What the desk's screen shows
# ---------------------------------------------------------------------------

def view(conn: Connection, player_id, now: datetime) -> dict:
    """The desk, for whoever works it. Someone outside a firm sees nothing of it."""
    seat = empires.seat_of(conn, player_id)
    if seat is None:
        return {"desk": None, "reason": "You do not work at a firm."}
    empire = empires.empire_of(conn, player_id)
    desk = desk_of(conn, empire["id"]) if empire else None
    head = bool(empire and str(empire.get("head_player_id")) == str(player_id))
    if desk is None:
        return {"desk": None, "empire": _firm(empire) if empire else None, "head": head,
                "reason": "Your firm has no commodities desk yet.",
                "can_open": head, "least_limit": data.COMMODITY_DESK_LEAST_LIMIT}
    quotes = _rows(conn, """SELECT q.*, c.ticker, c.name AS company, c.sector FROM commodity_quotes q
                            JOIN companies c ON c.id = q.company_id WHERE q.desk_id = %s
                            ORDER BY q.id DESC LIMIT 40""", (desk["id"],))
    hedges = _rows(conn, """SELECT h.*, s.underlying, s.expiry_period FROM commodity_hedges h
                            JOIN derivative_series s ON s.id = h.series_id WHERE h.desk_id = %s ORDER BY h.id DESC""",
                   (desk["id"],))
    gone = _rows(conn, "SELECT * FROM commodity_desk_results WHERE desk_id = %s ORDER BY period DESC LIMIT 8", (desk["id"],))
    prices = {g["code"]: commodities.quote(conn, g["code"], now) for g in commodities.goods(conn)}
    return {"desk": desk, "empire": _firm(empire), "head": head, "quotes": quotes, "hedges": hedges,
            "results": gone, "prices": prices, "in_use": in_use(conn, desk["id"]),
            "clients": clients(conn), "goods": commodities.goods(conn)}


def _firm(empire: dict | None) -> dict | None:
    if not empire:
        return None
    return {"id": empire["id"], "name": empire["name"], "cash": None}
