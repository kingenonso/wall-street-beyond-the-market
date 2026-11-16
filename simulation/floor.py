"""The Floor (owner, 16 November 2026: "build"): the game's multiplayer home, with a trading floor modelled on the
simulation the owner played in the investing challenge (his screenshots of 16 November): a profit-and-loss bar along the
top, positions, a blotter of every trade, a news feed, an exchange box that shows a deal's value and fee before it is
done, and an intraday chart. Price requests between asset managers and banks come in the next slice.

This module reads; it never moves money. The screen is the player's own trading account.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID

from psycopg import Connection
from psycopg.rows import dict_row

from simulation import clock, exchange, marketview
from simulation import world_data as data

BLOTTER_TRADES = 40            # the newest trades on the blotter
CHART_MINUTES = (1, 5, 15, 30, 60)       # a point every so many minutes (the screen asks for one a minute)


def _rows(conn: Connection, sql: str, params=()) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def screen(conn: Connection, account: UUID | str, now: datetime) -> dict:
    """The bar, the positions and the blotter of one trading account."""
    mine = marketview.portfolio(conn, account, now)
    fees = _rows(conn, "SELECT coalesce(sum(CASE WHEN buyer_account_id = %s THEN buyer_fee ELSE 0 END"
                       " + CASE WHEN seller_account_id = %s THEN seller_fee ELSE 0 END), 0)::bigint AS f FROM market_trades"
                       " WHERE buyer_account_id = %s OR seller_account_id = %s", (account, account, account, account))[0]["f"]
    unrealised = sum(h["gain"] for h in mine["holdings"])
    positions = [{
        "ticker": h["ticker"], "name": h["name"], "shares": h["shares"], "price": h["price"], "change_bps": h["change_bps"],
        "average_price": h["cost"] // h["shares"] if h["shares"] else 0, "value": h["value"], "gain": h["gain"],
    } for h in sorted(mine["holdings"], key=lambda h: -h["value"])]
    blotter = _rows(
        conn,
        "SELECT t.id, t.traded_at, c.ticker, t.price, t.quantity,"
        " CASE WHEN t.buyer_account_id = t.seller_account_id THEN 'both' WHEN t.buyer_account_id = %s THEN 'buy' ELSE 'sell' END AS side,"
        " (CASE WHEN t.buyer_account_id = %s THEN t.buyer_fee ELSE 0 END + CASE WHEN t.seller_account_id = %s THEN t.seller_fee ELSE 0 END)::bigint AS fee"
        " FROM market_trades t JOIN companies c ON c.id = t.company_id"
        " WHERE t.buyer_account_id = %s OR t.seller_account_id = %s ORDER BY t.id DESC LIMIT %s",
        (account, account, account, account, account, BLOTTER_TRADES))
    for t in blotter:
        t["venue"] = "exchange"
    # Deals done on the Floor, away from the exchange (slice 2): no exchange fee.
    if _one(conn, "SELECT to_regclass('floor_trades') IS NOT NULL AS ok")["ok"]:
        blotter += [{**t, "venue": "floor", "fee": 0} for t in _rows(
            conn,
            "SELECT -t.id AS id, t.at AS traded_at, c.ticker, t.price, t.quantity,"
            " CASE WHEN t.buyer_account = %s THEN 'buy' ELSE 'sell' END AS side FROM floor_trades t JOIN companies c ON c.id = t.company_id"
            " WHERE t.buyer_account = %s OR t.seller_account = %s ORDER BY t.id DESC LIMIT %s", (account, account, account, BLOTTER_TRADES))]
        blotter = sorted(blotter, key=lambda t: t["traded_at"], reverse=True)[:BLOTTER_TRADES]
    for t in blotter:
        t["value"] = t["price"] * t["quantity"]
    return {
        "now": now, "market_state": clock.market_state(now).value,
        "bar": {
            "realised": mine["realised"], "unrealised": unrealised, "total": mine["realised"] + unrealised,
            "dividends": mine["dividends"], "fees": fees, "exposure": mine["shares_value"],
            "cash": mine["cash"], "held_for_orders": mine["held_for_orders"], "value": mine["total"],
        },
        "positions": positions,
        "blotter": blotter,
        "fee_bps": data.EXCHANGE_FEE_BPS + data.STAMP_DUTY_BPS,
        # Slice 4: the game's words on the Floor, the live event's figure for this account, and the floor hour.
        "notes": notes(conn, now),
        "event": event_pnl(conn, account, now) if _one(conn, "SELECT to_regclass('floor_trades') IS NOT NULL AS ok")["ok"] else None,
        "floor_hour": {"starts_at": h[0], "ends_at": h[1]} if (h := floor_hour(now)) else None,
        "hour_at": f"{data.FLOOR_HOUR}:00",
        "tape": tape(conn, now),
    }


def intraday(conn: Connection, ticker: str, now: datetime, minutes: int = 5) -> dict | None:
    """One share's trading day, a point for each few minutes (the last price in each), with the day's reference price and
    the best prices waiting on the exchange."""
    if minutes not in CHART_MINUTES:
        minutes = 5
    found = exchange.quote(conn, ticker, now, depth=1)
    if found is None:
        return None
    day, _ = exchange.session_of(now)
    # Today's trading; before the first trade of the day, the last day that had any (the chart says which day it is).
    last = _rows(conn, "SELECT max(t.session_date) AS d FROM market_trades t JOIN companies c ON c.id = t.company_id"
                       " WHERE c.ticker = %s AND t.session_date <= %s", (ticker, day))[0]["d"]
    shown = last or day
    points = _rows(
        conn,
        "SELECT DISTINCT ON (slot) slot, price, volume FROM ("
        "  SELECT to_timestamp(floor(extract(epoch FROM t.traded_at) / %s) * %s) AS slot, t.price, t.id,"
        "         sum(t.quantity) OVER (PARTITION BY floor(extract(epoch FROM t.traded_at) / %s)) AS volume"
        "  FROM market_trades t JOIN companies c ON c.id = t.company_id"
        "  WHERE c.ticker = %s AND t.session_date = %s AND t.traded_at <= %s"
        ") s ORDER BY slot, id DESC",
        (minutes * 60, minutes * 60, minutes * 60, ticker, shown, now))
    return {
        "ticker": found["ticker"], "name": found["name"], "minutes": minutes, "state": found["state"],
        "session_date": shown, "today": shown == day,
        "reference_price": found["reference_price"], "last_price": found["last_price"],
        "lowest_today": found["lowest_today"], "highest_today": found["highest_today"],
        "best_bid": found["bids"][0]["price"] if found["bids"] else None,
        "best_offer": found["offers"][0]["price"] if found["offers"] else None,
        "points": [{"at": p["slot"], "price": p["price"], "volume": int(p["volume"])} for p in points],
    }


# ---------------------------------------------------------------------------
# The Auction House tab: every auction running, in one place
# ---------------------------------------------------------------------------

AUCTIONS_SHOWN = 60             # open ones first, then the recently settled
KIND_NAMES = {"property": "Property", "title": "Media title", "bank": "Bank"}


def auction_house(conn: Connection, viewer, now: datetime) -> list[dict]:
    """Every open auction (property, media titles, banks) and those settled in the last two days, soonest ending first.
    Public figures only: never a reserve (only whether it has been met), and never anybody's limit but the viewer's own,
    nor any bidder's name. Each says where it is bid on."""
    from simulation import auctions
    out = []
    for a in _rows(conn, """
        SELECT a.*, p.name AS property_name, p.kind AS property_kind, d.name AS district, d.city,
               t.name AS title_name, t.kind AS title_kind, t.city AS title_city, b.name AS bank_name, b.ticker AS bank_ticker
        FROM auctions a
        LEFT JOIN properties p ON p.id = a.property_id LEFT JOIN districts d ON d.id = p.district_id
        LEFT JOIN media_titles t ON t.id = a.title_id LEFT JOIN companies b ON b.id = a.bank_id
        WHERE a.opens_at <= %s AND (a.status = 'open' OR a.settled_at > %s)
        ORDER BY a.status = 'open' DESC, a.ends_at LIMIT %s""", (now, now - timedelta(days=2), AUCTIONS_SHOWN)):
        if a["property_id"] is not None:
            kind, lot = "property", f"{a['property_name']} ({a['property_kind']}), {a['city']}"
            where = "#/property/auctions"
        elif a["title_id"] is not None:
            kind, lot, where = "title", f"{a['title_name']} ({a['title_kind']}, {a['title_city']})", "#/intel"
        else:
            kind, lot, where = "bank", a["bank_name"], f"#/companies/{a['bank_ticker']}"
        mine = _rows(conn, "SELECT id, limit_price, status FROM auction_bids WHERE auction_id = %s AND bidder = %s ORDER BY id DESC LIMIT 1",
                     (a["id"], viewer))
        mine = mine[0] if mine else None
        out.append({
            "id": a["id"], "kind": kind, "kind_name": KIND_NAMES[kind], "lot": lot, "where": where, "reason": a["reason"],
            "status": a["status"], "opens_at": a["opens_at"], "ends_at": a["ends_at"],
            "start_price": a["start_price"], "price": a["price"], "minimum": auctions.minimum(a),
            "fair": a["fair"] if kind != "bank" else None,
            "lowest_price_met": auctions._reserve_met(conn, a),
            "bidders": _rows(conn, "SELECT count(DISTINCT bidder)::int AS n FROM auction_bids WHERE auction_id = %s", (a["id"],))[0]["n"],
            "you_lead": bool(mine and a["leader"] == mine["id"]),
            "your_limit": mine["limit_price"] if mine else None, "your_status": mine["status"] if mine else None,
        })
    return out


# ---------------------------------------------------------------------------
# Slices 2 and 3: price requests between clients and banks
# ---------------------------------------------------------------------------

class FloorError(Exception):
    """A request, a quote or a deal the Floor refuses, with a message for the player."""


class _Held(Exception):
    """The empire's Risk Manager would have to approve the trade first."""


SIDE_WORDS = {"buy": "buy", "sell": "sell", "two_way": "a price both ways"}
BPS = 10_000


def _one(conn: Connection, sql: str, params=()) -> dict | None:
    rows = _rows(conn, sql, params)
    return rows[0] if rows else None


def _unit(*key) -> float:
    import hashlib
    digest = hashlib.sha256("|".join(str(k) for k in key).encode()).digest()
    return int.from_bytes(digest[:8], "big") / 2**64


def _seed(conn: Connection) -> str:
    row = _one(conn, "SELECT fortune_seed FROM world_state")
    return row["fortune_seed"] if row else "no-world"


def _money(kobo: int) -> str:
    return f"₦{kobo / 100:,.2f}"


COMPUTER = {code: {"code": code, "name": name, "spread_bps": spread, "delay": delay}
            for code, name, spread, delay in data.FLOOR_COMPUTER_DESKS}


def _desk_account(conn: Connection, desk: str, kind: str = "share"):
    from simulation import ledger
    if desk.startswith("computer:"):
        # The computer banks deal from the institutions' books; in bonds, from the pension funds' (who make that market).
        from simulation import bonds
        return ledger.account_id(conn, bonds.DEALER if kind == "bond" else ledger.INVESTORS_INSTITUTIONS)
    return ledger.player_account_id(conn, desk.split(":", 1)[1])


def _desk_player(desk: str) -> str | None:
    return desk.split(":", 1)[1] if desk.startswith("player:") else None


def _desk_name(conn: Connection, desk: str) -> str:
    if desk.startswith("computer:"):
        found = COMPUTER.get(desk.split(":", 1)[1])
        return found["name"] if found else "A computer bank"
    row = _one(conn, "SELECT display_name FROM players WHERE id = %s", (desk.split(":", 1)[1],))
    return f"{row['display_name']}'s desk" if row else "A desk"


def _is_banker(conn: Connection, player_id) -> bool:
    row = _one(conn, "SELECT build FROM players WHERE id = %s", (player_id,))
    return bool(row and row["build"] == "investment_banker")


def _ping_player(conn: Connection, player_id) -> None:
    from simulation import pings
    pings.ping(conn, "floor", player=str(player_id))


def _ping_desks(conn: Connection, request_id: int) -> None:
    for d in _rows(conn, "SELECT desk_player FROM floor_request_desks WHERE request_id = %s AND desk_player IS NOT NULL", (request_id,)):
        _ping_player(conn, d["desk_player"])


def _share(conn: Connection, ticker: str, now: datetime) -> dict:
    found = exchange.quote(conn, ticker, now, depth=1)
    if found is None:
        raise FloorError(f"There is no share with the code {ticker} on the exchange.")
    company = _one(conn, "SELECT c.id, c.ticker, c.name, c.share_asset, m.halted_reason,"
                         " (SELECT r.shares_in_issue FROM company_results r WHERE r.company_id = c.id ORDER BY r.period DESC LIMIT 1) AS shares_in_issue"
                         " FROM companies c JOIN market_instruments m ON m.company_id = c.id WHERE c.ticker = %s", (ticker,))
    return {**company, **found}


def _mid(share: dict) -> int:
    bid = share["bids"][0]["price"] if share["bids"] else None
    offer = share["offers"][0]["price"] if share["offers"] else None
    return (bid + offer) // 2 if bid and offer else (share["last_price"] or share["reference_price"])


def _fast(share: dict) -> bool:
    """A fast market: the share has moved more than the computer banks will hold a firm price through."""
    last = share["last_price"] or share["reference_price"]
    return abs(last - share["reference_price"]) * BPS > share["reference_price"] * data.FLOOR_FAST_MARKET_BPS


def _bond(conn: Connection, code: str, now: datetime) -> dict:
    from simulation import bonds
    bond = bonds.find(conn, code)
    if bond is None or bond["redeemed_period"] is not None:
        raise FloorError("There is no such bond trading.")
    state = bonds.market(conn, now)
    day, _ = exchange.session_of(now)
    return {**bond, "state": state, **bonds.prices(conn, bond, state, day)}


def yield_at(bond: dict, price: int) -> int:
    """The yield a buyer at `price` earns, in hundredths of a percent a year (found by halving the range)."""
    from simulation import bonds
    flows = bonds.payments(bond, bond["state"])
    low, high = -0.5, 3.0
    for _ in range(60):
        mid = (low + high) / 2
        value = sum(amount / (1 + mid) ** years for years, amount in flows)
        low, high = (mid, high) if value > price else (low, mid)
    return round((low + high) / 2 * BPS)


def price_at_yield(bond: dict, yield_bps: int) -> int:
    from simulation import bonds
    return max(int(sum(amount / (1 + yield_bps / BPS) ** years for years, amount in bonds.payments(bond, bond["state"]))), 1)


def _market_open(now: datetime) -> None:
    if clock.market_state(now).value != "open":
        raise FloorError("Price requests are made while the market is open, 12:00 to 22:00 Lagos time.")


def set_desk(conn: Connection, player_id, open_it: bool, now: datetime) -> dict:
    """An investment banker opens their desk to take requests, or closes it."""
    if not _is_banker(conn, player_id):
        raise FloorError("A desk is an investment banker's: choose that build to make prices for clients.")
    conn.execute("INSERT INTO floor_desks (player_id, open, changed_at) VALUES (%s, %s, %s)"
                 " ON CONFLICT (player_id) DO UPDATE SET open = EXCLUDED.open, changed_at = EXCLUDED.changed_at",
                 (player_id, bool(open_it), now))
    return {"open": bool(open_it)}


def set_axe(conn: Connection, player_id, ticker: str, side: str | None, quantity: int, now: datetime) -> dict:
    """A banker advertises what their desk wants to buy or sell, for the rest of the trading day (or takes it down)."""
    if not _is_banker(conn, player_id):
        raise FloorError("Only a bank's desk advertises what it wants.")
    share = _share(conn, ticker, now)
    if side is None:
        conn.execute("DELETE FROM floor_axes WHERE player_id = %s AND company_id = %s", (player_id, share["id"]))
        return {"cleared": ticker}
    if side not in ("buy", "sell") or not isinstance(quantity, int) or isinstance(quantity, bool) or quantity <= 0:
        raise FloorError("Say whether you want to buy or sell, and how many.")
    lagos = clock.to_lagos(now)
    until = lagos.replace(hour=clock.MARKET_CLOSE.hour, minute=0, second=0, microsecond=0)
    if until <= lagos:
        until += timedelta(days=1)
    conn.execute("INSERT INTO floor_axes (player_id, company_id, side, quantity, created_at, until) VALUES (%s, %s, %s, %s, %s, %s)"
                 " ON CONFLICT (player_id, company_id) DO UPDATE SET side = EXCLUDED.side, quantity = EXCLUDED.quantity,"
                 " created_at = EXCLUDED.created_at, until = EXCLUDED.until", (player_id, share["id"], side, quantity, now, until))
    return {"axe": ticker}


def _record(conn: Connection, player_id) -> dict:
    row = _one(conn, "SELECT failed, backed_away FROM floor_desks WHERE player_id = %s", (player_id,))
    return row or {"failed": 0, "backed_away": 0}


def desks_for(conn: Connection, player_id, now: datetime | None = None) -> list[dict]:
    """The banks a client may ask: the computer banks and every open player desk but their own, with what each wants."""
    out = [{"key": f"computer:{c['code']}", "name": c["name"], "kind": "computer", "failed": 0, "backed_away": 0, "axes": []}
           for c in COMPUTER.values()]
    for d in _rows(conn, "SELECT d.player_id, d.failed, d.backed_away, p.display_name FROM floor_desks d JOIN players p ON p.id = d.player_id"
                         " WHERE d.open AND p.build = 'investment_banker' AND d.player_id <> %s ORDER BY p.display_name", (player_id,)):
        axes = _rows(conn, "SELECT c.ticker, a.side, a.quantity FROM floor_axes a JOIN companies c ON c.id = a.company_id"
                           " WHERE a.player_id = %s AND a.until > %s ORDER BY c.ticker", (d["player_id"], now)) if now else []
        out.append({"key": f"player:{d['player_id']}", "name": f"{d['display_name']}'s desk", "kind": "player",
                    "failed": d["failed"], "backed_away": d["backed_away"], "axes": axes})
    return out


# ---------------------------------------------------------------------------
# The computer banks' prices
# ---------------------------------------------------------------------------

def _computer_half(conn: Connection, request: dict, code: str, value: int) -> int:
    desk = COMPUTER[code]
    size = min(value // 1_000_000_000 * data.FLOOR_SIZE_SPREAD_BPS, data.FLOOR_SIZE_SPREAD_MOST_BPS)
    jitter = round(_unit(_seed(conn), "floor-quote", request["id"], code) * 20) - 10
    half = max(desk["spread_bps"] // 2 + size + jitter, 5)
    if request.get("client_player") and fishing(conn, request["client_player"])["fishing"]:
        half *= data.FLOOR_FISHING_SPREAD                # a client who asks and never deals gets worse prices
    return max(half // 4, 3) if request["kind"] == "bond" else half      # bonds trade far tighter than shares


def _computer_quote(conn: Connection, request: dict, code: str, now: datetime) -> None:
    """A computer bank's price: the middle of the market, less or plus half its spread, wider for a big deal; in a fast
    market only an indicative one."""
    desk = COMPUTER[code]
    firm, bid, offer, margin = True, None, None, None
    if request["kind"] == "share":
        share = _share(conn, request["ticker"], now)
        mid = _mid(share)
        half = _computer_half(conn, request, code, mid * request["quantity"])
        bid = max(share["lowest_today"], mid * (BPS - half) // BPS)
        offer = min(share["highest_today"], max(mid * (BPS + half) // BPS, bid + 1))
        if offer <= bid:
            return
        firm = not _fast(share)
    elif request["kind"] == "bond":
        bond = _bond(conn, request["code"], now)
        half = _computer_half(conn, request, code, bond["fair"] * request["quantity"])
        bid, offer = max(bond["fair"] * (BPS - half) // BPS, 1), max(bond["fair"] * (BPS + half) // BPS, 2)
    else:
        value = sum(leg["mid"] * leg["quantity"] for leg in request["legs"])
        margin = _computer_half(conn, request, code, value) + data.FLOOR_BASKET_EXTRA_BPS
    if request["side"] == "buy":
        bid = None
    elif request["side"] == "sell":
        offer = None
    # A computer bank never offers what it does not hold.
    if request["kind"] != "basket" and offer is not None:
        from simulation import ledger
        asset = _one(conn, "SELECT asset FROM bonds WHERE id = %s", (request["bond_id"],))["asset"] if request["kind"] == "bond" \
            else _one(conn, "SELECT share_asset FROM companies WHERE id = %s", (request["company_id"],))["share_asset"]
        if ledger.balance(conn, _desk_account(conn, f"computer:{code}", request["kind"]), asset) < request["quantity"]:
            offer = None
    if bid is None and offer is None and margin is None:
        return
    shown = now + timedelta(seconds=desk["delay"] + round(_unit(_seed(conn), "floor-delay", request["id"], code) * 4))
    conn.execute("INSERT INTO floor_quotes (request_id, desk, bid, offer, margin_bps, firm, created_at, shown_at, valid_until)"
                 " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                 (request["id"], f"computer:{code}", bid, offer, margin, firm, now, shown, shown + timedelta(seconds=data.FLOOR_COMPUTER_QUOTE_SECONDS)))


# ---------------------------------------------------------------------------
# Asking
# ---------------------------------------------------------------------------

def _client(conn: Connection, player_id, for_empire: bool, now: datetime) -> tuple:
    """The account a request deals for: the player's own, or their empire's (its head and its Asset Managers)."""
    from simulation import empires, ledger
    if not for_empire:
        account = ledger.player_account_id(conn, player_id)
        if account is None:
            raise FloorError("Your account is not open yet.")
        return account, None
    try:
        seat, _ = empires._trader(conn, player_id, now)
    except empires.EmpireError as refused:
        raise FloorError(str(refused)) from None
    return seat["account_id"], seat["empire_id"]


def _check_desks(conn: Connection, player_id, chosen: list[str], now: datetime) -> None:
    if not 1 <= len(chosen) <= data.FLOOR_MOST_DESKS:
        raise FloorError(f"Ask one to {data.FLOOR_MOST_DESKS} banks.")
    allowed = {d["key"] for d in desks_for(conn, player_id)}
    for desk in chosen:
        if desk not in allowed:
            raise FloorError("One of those banks is not taking requests now.")


def _check_window(seconds: int) -> None:
    least, most = data.FLOOR_WINDOW_SECONDS
    if not isinstance(seconds, int) or isinstance(seconds, bool) or not least <= seconds <= most:
        raise FloorError(f"Give the banks {least} to {most} seconds.")


def _check_waiting(conn: Connection, account, now: datetime) -> None:
    waiting = _one(conn, "SELECT count(*)::int AS n FROM floor_requests WHERE client_account = %s AND status = 'open' AND quotes_until > %s",
                   (account, now))["n"]
    if waiting >= data.FLOOR_MOST_OPEN_REQUESTS:
        raise FloorError(f"You have {waiting} requests waiting. Take or pass one first.")


def _whole(n) -> bool:
    return isinstance(n, int) and not isinstance(n, bool) and n > 0


def _load_request(conn: Connection, request_id: int, *, lock: bool = False) -> dict | None:
    r = _one(conn, "SELECT r.*, c.ticker, c.name AS company_name, substr(b.asset, 5) AS code, b.name AS bond_name FROM floor_requests r"
                   " LEFT JOIN companies c ON c.id = r.company_id LEFT JOIN bonds b ON b.id = r.bond_id WHERE r.id = %s"
                   + (" FOR UPDATE OF r" if lock else ""), (request_id,))
    if r is not None:
        r["legs"] = _rows(conn, "SELECT l.*, c.ticker, c.name, c.share_asset FROM floor_request_legs l JOIN companies c ON c.id = l.company_id"
                                " WHERE l.request_id = %s ORDER BY c.ticker", (request_id,))
    return r


def _open_request(conn: Connection, *, account, player_id, client_name, kind: str, company_id=None, bond_id=None, side: str,
                  quantity: int, seconds: int, desks: list[str], now: datetime, legs: list[dict] | None = None, block: bool = False,
                  for_empire=None, exchange_bid=None, exchange_offer=None) -> dict:
    row = _one(conn, "INSERT INTO floor_requests (client_account, client_player, client_name, kind, company_id, bond_id, side, quantity,"
                     " created_at, quotes_until, block, for_empire, exchange_bid, exchange_offer)"
                     " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
               (account, player_id, client_name, kind, company_id, bond_id, side, quantity, now, now + timedelta(seconds=seconds), block,
                for_empire, exchange_bid, exchange_offer))
    for leg in legs or []:
        conn.execute("INSERT INTO floor_request_legs (request_id, company_id, quantity, mid) VALUES (%s, %s, %s, %s)",
                     (row["id"], leg["company_id"], leg["quantity"], leg["mid"]))
    request = _load_request(conn, row["id"])
    for desk in desks:
        player = _desk_player(desk)
        conn.execute("INSERT INTO floor_request_desks (request_id, desk, desk_player) VALUES (%s, %s, %s)", (row["id"], desk, player))
        if player:
            _ping_player(conn, player)
        else:
            _computer_quote(conn, request, desk.split(":", 1)[1], now)
    return request


def ask(conn: Connection, player_id, ticker: str, side: str, quantity: int, seconds: int, desks: list[str], now: datetime, *,
        for_empire: bool = False, block: bool = False) -> dict:
    """A client's request for prices on a share: buy or sell (or a price both ways, not saying which), how many, how long the
    banks have, and which banks (one to five). A block is a very large deal, reported to the market afterwards."""
    if side not in SIDE_WORDS:
        raise FloorError("Ask to buy, to sell, or for a price both ways.")
    if not _whole(quantity):
        raise FloorError("Ask for a whole number of shares, above nought.")
    _check_window(seconds)
    chosen = list(dict.fromkeys(desks))
    _market_open(now)
    with conn.transaction():
        account, empire_id = _client(conn, player_id, for_empire, now)
        share = _share(conn, ticker, now)
        if share.get("halted_reason"):
            raise FloorError(f"No trading in this share: {share['halted_reason']}.")
        most = data.FLOOR_BLOCK_MOST_BPS if block else data.FLOOR_MOST_SHARES_BPS
        if quantity * BPS > share["shares_in_issue"] * most:
            raise FloorError(f"One {'block' if block else 'request'} is at most {most / 100:g}% of the company's shares."
                             + ("" if block else " A bigger deal is a block."))
        if block and _mid(share) * quantity < data.FLOOR_BLOCK_LEAST_NAIRA * 100:
            raise FloorError(f"A block is a deal of at least {_money(data.FLOOR_BLOCK_LEAST_NAIRA * 100)}.")
        _check_waiting(conn, account, now)
        _check_desks(conn, player_id, chosen, now)
        request = _open_request(conn, account=account, player_id=player_id, client_name=None, kind="share", company_id=share["id"], side=side,
                                quantity=quantity, seconds=seconds, desks=chosen, now=now, block=block, for_empire=empire_id,
                                exchange_bid=share["bids"][0]["price"] if share["bids"] else None,
                                exchange_offer=share["offers"][0]["price"] if share["offers"] else None)
    return {"request_id": request["id"]}


def ask_basket(conn: Connection, player_id, legs: list[tuple[str, int]], side: str, seconds: int, desks: list[str], now: datetime, *,
               for_empire: bool = False) -> dict:
    """Several shares at once, all bought or all sold, priced by each bank as one margin over (or under) the market."""
    if side not in ("buy", "sell"):
        raise FloorError("A basket is all bought or all sold.")
    tickers = [t for t, _ in legs]
    if not 2 <= len(legs) <= data.FLOOR_BASKET_MOST or len(set(tickers)) != len(tickers):
        raise FloorError(f"A basket is two to {data.FLOOR_BASKET_MOST} different shares.")
    if not all(_whole(q) for _, q in legs):
        raise FloorError("Ask for a whole number of each share, above nought.")
    _check_window(seconds)
    chosen = list(dict.fromkeys(desks))
    _market_open(now)
    with conn.transaction():
        account, empire_id = _client(conn, player_id, for_empire, now)
        rows = []
        for ticker, quantity in legs:
            share = _share(conn, ticker, now)
            if share.get("halted_reason"):
                raise FloorError(f"No trading in {ticker}: {share['halted_reason']}.")
            if quantity * BPS > share["shares_in_issue"] * data.FLOOR_MOST_SHARES_BPS:
                raise FloorError(f"{ticker}: one request is at most {data.FLOOR_MOST_SHARES_BPS / 100:g}% of the company's shares.")
            rows.append({"company_id": share["id"], "quantity": quantity, "mid": _mid(share)})
        _check_waiting(conn, account, now)
        _check_desks(conn, player_id, chosen, now)
        request = _open_request(conn, account=account, player_id=player_id, client_name=None, kind="basket", side=side,
                                quantity=sum(q for _, q in legs), seconds=seconds, desks=chosen, now=now, legs=rows, for_empire=empire_id)
    return {"request_id": request["id"]}


def ask_bond(conn: Connection, player_id, code: str, side: str, units: int, seconds: int, desks: list[str], now: datetime, *,
             for_empire: bool = False) -> dict:
    """A request for prices on a bond, quoted as a price and the yield it gives."""
    if side not in SIDE_WORDS:
        raise FloorError("Ask to buy, to sell, or for a price both ways.")
    if not _whole(units) or units > data.FLOOR_BOND_MOST_UNITS:
        raise FloorError(f"Ask for 1 to {data.FLOOR_BOND_MOST_UNITS:,} bonds.")
    _check_window(seconds)
    chosen = list(dict.fromkeys(desks))
    _market_open(now)
    with conn.transaction():
        account, empire_id = _client(conn, player_id, for_empire, now)
        bond = _bond(conn, code, now)
        _check_waiting(conn, account, now)
        _check_desks(conn, player_id, chosen, now)
        request = _open_request(conn, account=account, player_id=player_id, client_name=None, kind="bond", bond_id=bond["id"], side=side,
                                quantity=units, seconds=seconds, desks=chosen, now=now, for_empire=empire_id,
                                exchange_bid=bond["bid"] or None, exchange_offer=bond["ask"])
    return {"request_id": request["id"]}


# ---------------------------------------------------------------------------
# Quoting
# ---------------------------------------------------------------------------

def quote(conn: Connection, player_id, request_id: int, bid: int | None, offer: int | None, valid_seconds: int, now: datetime, *,
          firm: bool = True, margin_bps: int | None = None, bid_yield_bps: int | None = None, offer_yield_bps: int | None = None) -> dict:
    """A banker's prices for a request sent to their desk: firm (the client may take it at once) or indicative (taking it asks
    the banker to confirm). A bond may be quoted by yield; a basket by one margin. A new quote replaces the desk's last."""
    least, most = data.FLOOR_QUOTE_SECONDS
    if not isinstance(valid_seconds, int) or isinstance(valid_seconds, bool) or not least <= valid_seconds <= most:
        raise FloorError(f"A price holds for {least} to {most} seconds.")
    for p in (bid, offer):
        if p is not None and not _whole(p):
            raise FloorError("A price is a sum above nought.")
    desk = f"player:{player_id}"
    with conn.transaction():
        request = _load_request(conn, request_id, lock=True)
        if request is None or not _one(conn, "SELECT 1 AS x FROM floor_request_desks WHERE request_id = %s AND desk = %s", (request_id, desk)):
            raise FloorError("That request was not sent to your desk.")
        if request["status"] != "open" or now >= request["quotes_until"]:
            raise FloorError("Too late: the client's countdown has run out.")
        if request["kind"] == "basket":
            if not isinstance(margin_bps, int) or isinstance(margin_bps, bool) or not -500 <= margin_bps <= 500:
                raise FloorError("Price a basket as one margin over the market, between −5% and +5%.")
            bid = offer = None
        else:
            if request["kind"] == "bond":
                bond = _bond(conn, request["code"], now)
                bid = price_at_yield(bond, bid_yield_bps) if bid_yield_bps is not None else bid
                offer = price_at_yield(bond, offer_yield_bps) if offer_yield_bps is not None else offer
            needs = {"buy": ("offer",), "sell": ("bid",), "two_way": ("bid", "offer")}[request["side"]]
            given = {"bid": bid, "offer": offer}
            for word in needs:
                if given[word] is None:
                    raise FloorError("The client asked for a price both ways: give a buying and a selling price." if request["side"] == "two_way"
                                     else f"Give the price you would {'sell' if word == 'offer' else 'buy'} at.")
            bid, offer = (bid if "bid" in needs else None), (offer if "offer" in needs else None)
            if bid is not None and offer is not None and bid >= offer:
                raise FloorError("Your buying price must be below your selling price.")
            if request["kind"] == "share":
                share = _share(conn, request["ticker"], now)
                for p in (bid, offer):
                    if p is not None and not share["lowest_today"] <= p <= share["highest_today"]:
                        raise FloorError(f"Today this share can trade only between {_money(share['lowest_today'])} and {_money(share['highest_today'])}.")
            else:
                for p in (bid, offer):
                    if p is not None and abs(p - bond["fair"]) * BPS > bond["fair"] * data.FLOOR_BOND_BAND_BPS:
                        raise FloorError(f"A bond's price on the Floor stays within {data.FLOOR_BOND_BAND_BPS / 100:g}% of its fair value, {_money(bond['fair'])}.")
        conn.execute("UPDATE floor_quotes SET status = 'replaced' WHERE request_id = %s AND desk = %s AND status = 'live'", (request_id, desk))
        row = _one(conn, "INSERT INTO floor_quotes (request_id, desk, bid, offer, margin_bps, firm, created_at, shown_at, valid_until)"
                         " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
                   (request_id, desk, bid, offer, margin_bps if request["kind"] == "basket" else None, bool(firm), now, now,
                    now + timedelta(seconds=valid_seconds)))
        if request["client_player"]:
            _ping_player(conn, request["client_player"])
    return {"quote_id": row["id"]}


# ---------------------------------------------------------------------------
# Settling a deal
# ---------------------------------------------------------------------------

def _price_of(q: dict, client_buys: bool) -> int | None:
    return q["offer"] if client_buys else q["bid"]


def _cover(conn: Connection, request: dict, winner_id: int, client_buys: bool) -> int | None:
    """The second-best price on the side the client dealt: what the winner beat."""
    others = _rows(conn, "SELECT bid, offer, margin_bps FROM floor_quotes WHERE request_id = %s AND id <> %s AND status IN ('live', 'lost')",
                   (request["id"], winner_id))
    if request["kind"] == "basket":
        found = [o["margin_bps"] for o in others if o["margin_bps"] is not None]
        return min(found) if found else None
    found = [o["offer"] if client_buys else o["bid"] for o in others if (o["offer"] if client_buys else o["bid"])]
    return (min(found) if client_buys else max(found)) if found else None


def _empire_checks(conn: Connection, request: dict, legs: list[dict], client_buys: bool, now: datetime) -> None:
    """A deal for an empire meets every limit an order for the empire would: the member's trading limit, the 30% rule,
    no dealing with its own people, fair dealing for an empire the computer runs, and the Risk Manager's gate (a deal
    that would have to wait for the Risk Manager cannot be done on the Floor, where prices hold for seconds)."""
    from simulation import empires, firm_dealmaking, firm_risk
    try:
        seat, state = empires._trader(conn, request["client_player"], now)
        if seat["empire_id"] != request["for_empire"]:
            raise FloorError("You no longer trade for that empire.")
        side = "buy" if client_buys else "sell"
        total = sum(leg["price"] * leg["quantity"] for leg in legs)
        for leg in legs:
            if leg.get("company_id") is None:
                continue
            if seat["head_player_id"] is None:
                empires.fair_dealing({"reference": leg["reference"]}, side, "limit", leg["price"], "An empire run by the computer")
            empires.no_dealing_with_yourself(conn, seat["account_id"], leg["company_id"], side, empires._insiders(conn, seat["empire_id"]), "the empire")
            if client_buys and seat["empire_kind"] == "player":
                firm_dealmaking.buying_guard(conn, seat["empire_id"], leg["company_id"], leg["quantity"])
        empires._within_trade_limit(conn, seat, state, total, now)
        try:
            with conn.transaction():
                for leg in legs:
                    if leg.get("company_id") is not None:
                        held = firm_risk.gate_trade(conn, seat, {"id": leg["company_id"], "ticker": leg["ticker"]}, side, "limit",
                                                    leg["quantity"], leg["price"], leg["price"] * leg["quantity"], state, now)
                    else:
                        held = firm_risk.gate_bond(conn, seat, leg["code"], side, leg["quantity"], leg["price"] * leg["quantity"], state, now)
                    if held is not None:
                        raise _Held(held["why"])
        except _Held as held:
            raise FloorError("This needs the empire's Risk Manager to approve it first (" + "; ".join(held.args[0])
                             + "), and a price on the Floor holds only seconds. Ask for a smaller deal, or trade it on the exchange.") from None
        conn.execute("INSERT INTO empire_trades (empire_id, player_id, period, what, value, at) VALUES (%s, %s, %s, %s, %s, %s)",
                     (seat["empire_id"], request["client_player"], state["period"],
                      f"{side} on the Floor: " + ", ".join(f"{leg['quantity']:,} {leg['ticker'] or leg['code']}" for leg in legs), total, now))
    except empires.EmpireError as refused:
        raise FloorError(str(refused)) from None


def _legs(conn: Connection, request: dict, q: dict, client_buys: bool, price: int | None, margin: int | None) -> list[dict]:
    if request["kind"] == "share":
        share = _one(conn, "SELECT share_asset, (SELECT reference_price FROM market_instruments WHERE company_id = c.id) AS reference"
                           " FROM companies c WHERE id = %s", (request["company_id"],))
        return [{"company_id": request["company_id"], "bond_id": None, "ticker": request["ticker"], "code": None, "asset": share["share_asset"],
                 "quantity": request["quantity"], "price": price, "reference": share["reference"]}]
    if request["kind"] == "bond":
        bond = _one(conn, "SELECT asset FROM bonds WHERE id = %s", (request["bond_id"],))
        return [{"company_id": None, "bond_id": request["bond_id"], "ticker": None, "code": request["code"], "asset": bond["asset"],
                 "quantity": request["quantity"], "price": price, "reference": price}]
    sign = 1 if client_buys else -1
    return [{"company_id": leg["company_id"], "bond_id": None, "ticker": leg["ticker"], "code": None, "asset": leg["share_asset"],
             "quantity": leg["quantity"], "price": max(leg["mid"] * (BPS + sign * margin) // BPS, 1), "reference": leg["mid"]}
            for leg in request["legs"]]


def _settle(conn: Connection, request: dict, q: dict, client_buys: bool, now: datetime, *, price: int | None = None,
            margin: int | None = None) -> dict:
    """The shares (or bonds) and the money change hands at once, away from the exchange. Refused (and nothing moves) if either
    side cannot: a desk that cannot deliver is marked for it."""
    from simulation import corporate, courts, ledger, newsroom
    from simulation.ledger import Leg
    if request["kind"] == "basket":
        margin = q["margin_bps"] if margin is None else margin
    else:
        price = _price_of(q, client_buys) if price is None else price
        if price is None:
            raise FloorError("That bank gave no price on that side.")
    desk_account = _desk_account(conn, q["desk"], request["kind"])
    if desk_account is None:
        raise FloorError("That desk has no account.")
    buyer, seller = (request["client_account"], desk_account) if client_buys else (desk_account, request["client_account"])
    if buyer == seller:
        raise FloorError("A desk cannot deal with itself.")
    player = _desk_player(q["desk"])
    if player and request["for_empire"] and _one(conn, "SELECT 1 AS x FROM empire_seats WHERE empire_id = %s AND player_id = %s",
                                                 (request["for_empire"], player)):
        raise FloorError("A banker cannot deal with an empire they sit in.")
    legs = _legs(conn, request, q, client_buys, price, margin)
    cost = sum(leg["price"] * leg["quantity"] for leg in legs)
    for account in (buyer, seller):
        kind = _one(conn, "SELECT kind FROM ledger_accounts WHERE id = %s", (account,))["kind"]
        if kind in ("player", "empire"):
            for leg in legs:
                if leg["company_id"]:
                    newsroom.check_trade(conn, account, leg["company_id"], now)
            courts.check_trade(conn, account, now)
    short = any(ledger.balance(conn, desk_account, leg["asset"]) < leg["quantity"] for leg in legs) if client_buys \
        else ledger.balance(conn, desk_account) < cost
    if short:
        if player:
            conn.execute("UPDATE floor_desks SET failed = failed + 1 WHERE player_id = %s", (player,))
        conn.execute("UPDATE floor_quotes SET status = 'failed' WHERE id = %s", (q["id"],))
        return {"failed": f"{_desk_name(conn, q['desk'])} could not deliver: it has not the {'holdings' if client_buys else 'cash'}. Its price is withdrawn; take another."}
    if client_buys and ledger.balance(conn, buyer) < cost:
        raise FloorError(f"The deal costs {_money(cost)}. {'The empire has' if request['for_empire'] else 'You have'} not that much cash.")
    if not client_buys and any(ledger.balance(conn, seller, leg["asset"]) < leg["quantity"] for leg in legs):
        raise FloorError("You do not hold that many free (holdings waiting in orders on the exchange are not free).")
    if request["for_empire"]:
        _empire_checks(conn, request, legs, client_buys, now)
    cover = _cover(conn, request, q["id"], client_buys)
    exchange_price = request["exchange_offer"] if client_buys else request["exchange_bid"]
    what = ", ".join(f"{leg['quantity']:,} {leg['ticker'] or leg['code']}" for leg in legs)
    tx = ledger.post(conn, kind="floor_trade", memo=f"{what} on the Floor", reference=f"floor:{request['id']}",
                     legs=[x for leg in legs for x in (Leg(seller, -leg["quantity"], leg["asset"]), Leg(buyer, leg["quantity"], leg["asset"]))]
                     + [Leg(buyer, -cost), Leg(seller, cost)])
    after = corporate._after_trade(conn)
    day, _ = exchange.session_of(now)
    for leg in legs:
        value = leg["price"] * leg["quantity"]
        if leg["company_id"]:
            for account, shares in ((seller, -leg["quantity"]), (buyer, leg["quantity"])):
                conn.execute("INSERT INTO holding_events (account_id, company_id, kind, shares, amount, after_trade_id) VALUES (%s, %s, 'floor', %s, %s, %s)",
                             (account, leg["company_id"], shares, value, after))
        else:
            for account, side, other in ((buyer, "buy", seller), (seller, "sell", buyer)):
                conn.execute("INSERT INTO bond_trades (bond_id, account_id, side, units, price, counterparty, session_date, ledger_transaction, traded_at)"
                             " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)", (leg["bond_id"], account, side, leg["quantity"], leg["price"], other, day, tx, now))
        conn.execute("INSERT INTO floor_trades (request_id, quote_id, company_id, bond_id, buyer_account, seller_account, price, quantity, desk, at,"
                     " cover, exchange_price, client_bought, block) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                     (request["id"], q["id"], leg["company_id"], leg["bond_id"], buyer, seller, leg["price"], leg["quantity"], q["desk"], now,
                      cover if request["kind"] != "basket" else None, exchange_price if request["kind"] != "basket" else None, client_buys, request["block"]))
    conn.execute("UPDATE floor_quotes SET status = CASE WHEN id = %s THEN 'taken' ELSE 'lost' END WHERE request_id = %s AND status = 'live'",
                 (q["id"], request["id"]))
    conn.execute("UPDATE floor_counters SET status = 'expired', answered_at = %s WHERE request_id = %s AND status = 'open'", (now, request["id"]))
    conn.execute("UPDATE floor_requests SET status = 'done', done_at = %s WHERE id = %s", (now, request["id"]))
    _ping_desks(conn, request["id"])
    if request["client_player"]:
        _ping_player(conn, request["client_player"])
    return {"price": price, "margin_bps": margin, "quantity": request["quantity"], "cost": cost, "what": what,
            "bought": client_buys, "desk": _desk_name(conn, q["desk"]), "cover": cover, "ledger": tx}


def _live_quote(conn: Connection, request_id: int, quote_id: int, now: datetime) -> dict:
    q = _one(conn, "SELECT * FROM floor_quotes WHERE id = %s AND request_id = %s FOR UPDATE", (quote_id, request_id))
    if q is None or q["status"] != "live" or q["shown_at"] > now:
        raise FloorError("That price is not on offer.")
    if now >= q["valid_until"]:
        raise FloorError("Too late: that price has expired.")
    return q


def _my_request(conn: Connection, player_id, request_id: int) -> dict:
    request = _load_request(conn, request_id, lock=True)
    if request is None or str(request["client_player"]) != str(player_id):
        raise FloorError("There is no such request of yours.")
    if request["status"] != "open":
        raise FloorError("That request is closed.")
    return request


def take(conn: Connection, player_id, request_id: int, quote_id: int, side: str, now: datetime) -> dict:
    """The client takes a bank's price: buys at its selling price, or sells at its buying price. A firm price is done at
    once; an indicative one goes back to the bank to confirm."""
    if side not in ("buy", "sell"):
        raise FloorError("Take the price to buy or to sell.")
    with conn.transaction():
        request = _my_request(conn, player_id, request_id)
        if request["side"] != "two_way" and request["side"] != side:
            raise FloorError(f"You asked to {request['side']}.")
        q = _live_quote(conn, request_id, quote_id, now)
        if not q["firm"]:
            return _ask_bank(conn, request, q, "confirm", side, q["offer"] if side == "buy" else q["bid"], q["margin_bps"], now)
        done = _settle(conn, request, q, side == "buy", now)
    if "failed" in done:
        raise FloorError(done["failed"])
    return done


def counter(conn: Connection, player_id, request_id: int, quote_id: int, side: str, now: datetime, *, price: int | None = None,
            margin_bps: int | None = None) -> dict:
    """The client haggles: "can you do 226?". The price must be better for the client than the bank's; the bank accepts
    (the deal is done at it) or declines while its price holds."""
    if side not in ("buy", "sell"):
        raise FloorError("Counter to buy or to sell.")
    with conn.transaction():
        request = _my_request(conn, player_id, request_id)
        if request["side"] != "two_way" and request["side"] != side:
            raise FloorError(f"You asked to {request['side']}.")
        q = _live_quote(conn, request_id, quote_id, now)
        if _one(conn, "SELECT 1 AS x FROM floor_counters WHERE quote_id = %s AND status = 'open'", (quote_id,)):
            raise FloorError("You are already waiting for that bank's answer.")
        if request["kind"] == "basket":
            if not isinstance(margin_bps, int) or isinstance(margin_bps, bool) or not -500 <= margin_bps < q["margin_bps"]:
                raise FloorError("Counter a basket with a smaller margin than the bank's.")
            price = None
        else:
            theirs = _price_of(q, side == "buy")
            if theirs is None:
                raise FloorError("That bank gave no price on that side.")
            if not _whole(price) or (side == "buy" and price >= theirs) or (side == "sell" and price <= theirs):
                raise FloorError(f"A counter must be better for you than the bank's {_money(theirs)}.")
            margin_bps = None
        return _ask_bank(conn, request, q, "counter", side, price, margin_bps, now)


def _ask_bank(conn: Connection, request: dict, q: dict, kind: str, side: str, price: int | None, margin: int | None, now: datetime) -> dict:
    row = _one(conn, "INSERT INTO floor_counters (request_id, quote_id, kind, side, price, margin_bps, created_at) VALUES (%s, %s, %s, %s, %s, %s, %s)"
                     " RETURNING id", (request["id"], q["id"], kind, side, price, margin, now))
    if q["desk"].startswith("computer:"):
        return _computer_answers(conn, request, q, row["id"], side, price, margin, now)
    _ping_player(conn, _desk_player(q["desk"]))
    return {"waiting": True, "counter_id": row["id"]}


def _computer_answers(conn: Connection, request: dict, q: dict, counter_id: int, side: str, price: int | None, margin: int | None,
                      now: datetime) -> dict:
    """A computer bank accepts a counter (or confirms its indicative price) if it still keeps enough of its spread against
    the market now; otherwise it declines."""
    code = q["desk"].split(":", 1)[1]
    client_buys = side == "buy"
    if request["kind"] == "basket":
        full = _computer_half(conn, request, code, 1) + data.FLOOR_BASKET_EXTRA_BPS
        ok = margin * BPS >= full * data.FLOOR_COMPUTER_KEEPS_BPS
    else:
        mid = _mid(_share(conn, request["ticker"], now)) if request["kind"] == "share" else _bond(conn, request["code"], now)["fair"]
        half = _computer_half(conn, request, code, mid * request["quantity"])
        edge = (price - mid) if client_buys else (mid - price)
        ok = edge * BPS * BPS >= mid * half * data.FLOOR_COMPUTER_KEEPS_BPS
    if not ok:
        conn.execute("UPDATE floor_counters SET status = 'declined', answered_at = %s WHERE id = %s", (now, counter_id))
        return {"declined": True, "desk": _desk_name(conn, q["desk"])}
    done = _settle(conn, request, q, client_buys, now, price=price, margin=margin)
    if "failed" in done:
        raise FloorError(done["failed"])
    conn.execute("UPDATE floor_counters SET status = 'accepted', answered_at = %s WHERE id = %s", (now, counter_id))
    return done


def answer(conn: Connection, player_id, counter_id: int, accept: bool, now: datetime) -> dict:
    """A banker answers a counter, or confirms (or backs away from) an indicative price a client took. Backing away is
    counted, and shown to every client."""
    with conn.transaction():
        c = _one(conn, "SELECT * FROM floor_counters WHERE id = %s FOR UPDATE", (counter_id,))
        q = _one(conn, "SELECT * FROM floor_quotes WHERE id = %s FOR UPDATE", (c["quote_id"],)) if c else None
        if c is None or q["desk"] != f"player:{player_id}":
            raise FloorError("There is no such question for your desk.")
        if c["status"] != "open":
            raise FloorError("That has been answered already, or it has run out.")
        request = _load_request(conn, c["request_id"], lock=True)
        if request["status"] != "open" or q["status"] != "live" or now >= q["valid_until"] + timedelta(seconds=data.FLOOR_CONFIRM_SECONDS):
            conn.execute("UPDATE floor_counters SET status = 'expired', answered_at = %s WHERE id = %s", (now, counter_id))
            if c["kind"] == "confirm":
                conn.execute("UPDATE floor_desks SET backed_away = backed_away + 1 WHERE player_id = %s", (player_id,))
            raise FloorError("Too late: your price ran out before you answered.")
        if not accept:
            conn.execute("UPDATE floor_counters SET status = 'declined', answered_at = %s WHERE id = %s", (now, counter_id))
            if c["kind"] == "confirm":
                conn.execute("UPDATE floor_desks SET backed_away = backed_away + 1 WHERE player_id = %s", (player_id,))
            if request["client_player"]:
                _ping_player(conn, request["client_player"])
            return {"declined": True}
        done = _settle(conn, request, q, c["side"] == "buy", now, price=c["price"], margin=c["margin_bps"])
        if "failed" in done:
            conn.execute("UPDATE floor_counters SET status = 'declined', answered_at = %s WHERE id = %s", (now, counter_id))
            return {"failed": done["failed"]}
        conn.execute("UPDATE floor_counters SET status = 'accepted', answered_at = %s WHERE id = %s", (now, counter_id))
        return done


def pass_on(conn: Connection, player_id, request_id: int, now: datetime) -> dict:
    with conn.transaction():
        request = _load_request(conn, request_id, lock=True)
        if request is None or str(request["client_player"]) != str(player_id) or request["status"] != "open":
            raise FloorError("There is no such open request of yours.")
        conn.execute("UPDATE floor_requests SET status = 'passed', done_at = %s WHERE id = %s", (now, request_id))
        conn.execute("UPDATE floor_quotes SET status = 'lost' WHERE request_id = %s AND status = 'live'", (request_id,))
        conn.execute("UPDATE floor_counters SET status = 'expired', answered_at = %s WHERE request_id = %s AND status = 'open'", (now, request_id))
        _ping_desks(conn, request_id)
    return {"passed": request_id}


def _ends(conn: Connection, request: dict) -> datetime:
    """A request is over when the banks' countdown and every price it drew have run out."""
    last = _one(conn, "SELECT max(valid_until) AS t FROM floor_quotes WHERE request_id = %s AND status = 'live'", (request["id"],))["t"]
    end = max(request["quotes_until"], last) if last else request["quotes_until"]
    return end + timedelta(seconds=data.FLOOR_CONFIRM_SECONDS)


# ---------------------------------------------------------------------------
# Chat, and deal tickets
# ---------------------------------------------------------------------------

def _may_chat(conn: Connection, a, b) -> bool:
    """A client may write to any bank's desk; a banker to any client who has asked their desk for a price."""
    if _one(conn, "SELECT 1 AS x FROM floor_desks d JOIN players p ON p.id = d.player_id WHERE d.player_id = %s AND p.build = 'investment_banker'", (b,)):
        return True
    return bool(_one(conn, "SELECT 1 AS x FROM floor_requests r JOIN floor_request_desks k ON k.request_id = r.id"
                           " WHERE k.desk_player = %s AND r.client_player = %s LIMIT 1", (a, b)))


def say(conn: Connection, player_id, to_name: str, body: str, now: datetime) -> dict:
    """A line in the Floor chat. Kept for good."""
    body = " ".join((body or "").split())
    if not 1 <= len(body) <= 300:
        raise FloorError("A message is 1 to 300 characters.")
    other = _one(conn, "SELECT id FROM players WHERE display_name_key = lower(%s)", (to_name,))
    if other is None or str(other["id"]) == str(player_id):
        raise FloorError("There is nobody of that name to write to.")
    if not (_may_chat(conn, player_id, other["id"]) or _may_chat(conn, other["id"], player_id)):
        raise FloorError("On the Floor you write to a bank's desk, or to a client who asked your desk for a price.")
    conn.execute("INSERT INTO floor_chat (from_player, to_player, body, at) VALUES (%s, %s, %s, %s)", (player_id, other["id"], body, now))
    _ping_player(conn, other["id"])
    return {"to": to_name}


def propose_ticket(conn: Connection, player_id, to_name: str, ticker: str, side: str, quantity: int, price: int, now: datetime) -> dict:
    """An agreed chat line made into a deal ticket: the other side has a minute to confirm it."""
    if side not in ("buy", "sell") or not _whole(quantity) or not _whole(price):
        raise FloorError("A ticket says buy or sell, how many and at what price.")
    _market_open(now)
    with conn.transaction():
        other = _one(conn, "SELECT id FROM players WHERE display_name_key = lower(%s)", (to_name,))
        if other is None or str(other["id"]) == str(player_id):
            raise FloorError("There is nobody of that name.")
        if not _one(conn, "SELECT 1 AS x FROM floor_chat WHERE (from_player = %s AND to_player = %s) OR (from_player = %s AND to_player = %s) LIMIT 1",
                    (player_id, other["id"], other["id"], player_id)):
            raise FloorError("A ticket comes from a conversation: agree it in the chat first.")
        share = _share(conn, ticker, now)
        if not share["lowest_today"] <= price <= share["highest_today"]:
            raise FloorError(f"Today this share can trade only between {_money(share['lowest_today'])} and {_money(share['highest_today'])}.")
        if quantity * BPS > share["shares_in_issue"] * data.FLOOR_MOST_SHARES_BPS:
            raise FloorError(f"A ticket is at most {data.FLOOR_MOST_SHARES_BPS / 100:g}% of the company's shares.")
        row = _one(conn, "INSERT INTO floor_tickets (from_player, to_player, company_id, side, quantity, price, created_at, valid_until)"
                         " VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
                   (player_id, other["id"], share["id"], side, quantity, price, now, now + timedelta(seconds=data.FLOOR_TICKET_SECONDS)))
        _ping_player(conn, other["id"])
    return {"ticket_id": row["id"]}


def answer_ticket(conn: Connection, player_id, ticket_id: int, accept: bool, now: datetime) -> dict:
    """The other side confirms the ticket (the deal is done, between the two players' own accounts) or declines it. The
    proposer may withdraw it."""
    from simulation import corporate, courts, ledger, newsroom
    from simulation.ledger import Leg
    with conn.transaction():
        t = _one(conn, "SELECT t.*, c.ticker, c.share_asset, c.name FROM floor_tickets t JOIN companies c ON c.id = t.company_id"
                       " WHERE t.id = %s FOR UPDATE OF t", (ticket_id,))
        if t is None or str(player_id) not in (str(t["to_player"]), str(t["from_player"])):
            raise FloorError("There is no such ticket.")
        if t["status"] != "open":
            raise FloorError("That ticket is closed.")
        if now >= t["valid_until"]:
            conn.execute("UPDATE floor_tickets SET status = 'expired', done_at = %s WHERE id = %s", (now, ticket_id))
            raise FloorError("Too late: the ticket ran out.")
        if str(player_id) == str(t["from_player"]):
            if accept:
                raise FloorError("The other side confirms a ticket.")
            conn.execute("UPDATE floor_tickets SET status = 'withdrawn', done_at = %s WHERE id = %s", (now, ticket_id))
            _ping_player(conn, t["to_player"])
            return {"withdrawn": ticket_id}
        if not accept:
            conn.execute("UPDATE floor_tickets SET status = 'declined', done_at = %s WHERE id = %s", (now, ticket_id))
            _ping_player(conn, t["from_player"])
            return {"declined": ticket_id}
        _market_open(now)
        proposer, other = ledger.player_account_id(conn, t["from_player"]), ledger.player_account_id(conn, t["to_player"])
        buyer, seller = (proposer, other) if t["side"] == "buy" else (other, proposer)
        cost = t["price"] * t["quantity"]
        for account in (buyer, seller):
            newsroom.check_trade(conn, account, t["company_id"], now)
            courts.check_trade(conn, account, now)
        if ledger.balance(conn, buyer) < cost:
            raise FloorError(f"The buyer has not {_money(cost)} in cash.")
        if ledger.balance(conn, seller, t["share_asset"]) < t["quantity"]:
            raise FloorError("The seller does not hold that many free shares.")
        ledger.post(conn, kind="floor_trade", memo=f"{t['quantity']:,} {t['name']} shares at {_money(t['price'])}: a ticket on the Floor",
                    reference=f"floor-ticket:{ticket_id}",
                    legs=[Leg(seller, -t["quantity"], t["share_asset"]), Leg(buyer, t["quantity"], t["share_asset"]), Leg(buyer, -cost), Leg(seller, cost)])
        after = corporate._after_trade(conn)
        for account, shares in ((seller, -t["quantity"]), (buyer, t["quantity"])):
            conn.execute("INSERT INTO holding_events (account_id, company_id, kind, shares, amount, after_trade_id) VALUES (%s, %s, 'floor', %s, %s, %s)",
                         (account, t["company_id"], shares, cost, after))
        conn.execute("INSERT INTO floor_trades (ticket_id, quote_id, company_id, buyer_account, seller_account, price, quantity, desk, at)"
                     " VALUES (%s, NULL, %s, %s, %s, %s, %s, %s, %s)",
                     (ticket_id, t["company_id"], buyer, seller, t["price"], t["quantity"], f"player:{t['from_player']}", now))
        conn.execute("UPDATE floor_tickets SET status = 'done', done_at = %s WHERE id = %s", (now, ticket_id))
        _ping_player(conn, t["from_player"])
    return {"done": ticket_id, "ticker": t["ticker"], "quantity": t["quantity"], "price": t["price"]}


def chat_view(conn: Connection, player_id, now: datetime) -> dict:
    """The player's Floor conversations, newest first, and the tickets open between them."""
    lines = _rows(conn, "SELECT f.id, f.body, f.at, f.from_player = %s AS yours, p.display_name AS other FROM floor_chat f"
                        " JOIN players p ON p.id = CASE WHEN f.from_player = %s THEN f.to_player ELSE f.from_player END"
                        " WHERE f.from_player = %s OR f.to_player = %s ORDER BY f.id DESC LIMIT 80", (player_id, player_id, player_id, player_id))
    talks: dict = {}
    for line in reversed(lines):
        talks.setdefault(line["other"], []).append({"id": line["id"], "body": line["body"], "at": line["at"], "yours": line["yours"]})
    tickets = _rows(conn, "SELECT t.id, t.side, t.quantity, t.price, t.created_at, t.valid_until, t.status, c.ticker, t.from_player = %s AS yours,"
                          " p.display_name AS other FROM floor_tickets t JOIN companies c ON c.id = t.company_id"
                          " JOIN players p ON p.id = CASE WHEN t.from_player = %s THEN t.to_player ELSE t.from_player END"
                          " WHERE (t.from_player = %s OR t.to_player = %s) ORDER BY t.id DESC LIMIT 12", (player_id, player_id, player_id, player_id))
    for t in tickets:
        if t["status"] == "open" and now >= t["valid_until"]:
            t["status"] = "expired"
    return {"talks": [{"with": name, "lines": ls} for name, ls in sorted(talks.items(), key=lambda kv: -kv[1][-1]["id"])],
            "tickets": tickets}


# ---------------------------------------------------------------------------
# The computer clients, and tidying up
# ---------------------------------------------------------------------------

def _computer_decides(conn: Connection, request: dict, now: datetime) -> None:
    """At its countdown's end a computer client takes the best firm price that was live then, if it beats the exchange
    after the exchange's fee; otherwise it passes."""
    from simulation import ledger
    market = _share(conn, request["ticker"], now)
    at = request["quotes_until"]
    live = _rows(conn, "SELECT * FROM floor_quotes WHERE request_id = %s AND status = 'live' AND firm AND shown_at <= %s AND valid_until > %s",
                 (request["id"], at, at))
    fee = data.EXCHANGE_FEE_BPS + data.STAMP_DUTY_BPS
    client_buys = request["side"] == "buy"
    if client_buys:
        best = min((q for q in live if q["offer"]), key=lambda q: (q["offer"], q["shown_at"]), default=None)
        beat = market["offers"][0]["price"] * (BPS + fee) // BPS if market["offers"] else None
        good = best is not None and (beat is None or best["offer"] <= beat)
    else:
        best = max((q for q in live if q["bid"]), key=lambda q: (q["bid"], -q["shown_at"].timestamp()), default=None)
        beat = market["bids"][0]["price"] * (BPS - fee) // BPS if market["bids"] else None
        good = best is not None and (beat is None or best["bid"] >= beat)
    with conn.transaction():
        if good:
            try:
                with conn.transaction():            # a deal that cannot be done leaves nothing behind
                    done = _settle(conn, request, best, client_buys, now)
            except (FloorError, exchange.ExchangeError, ledger.LedgerError):
                done = {"failed": True}             # the client's own side failed: it simply passes
            if "failed" not in done:
                return
        conn.execute("UPDATE floor_requests SET status = 'passed', done_at = %s WHERE id = %s AND status = 'open'", (now, request["id"]))
        conn.execute("UPDATE floor_quotes SET status = 'lost' WHERE request_id = %s AND status = 'live'", (request["id"],))
        _ping_desks(conn, request["id"])


def _computer_calls(conn: Connection, now: datetime) -> int:
    """Computer clients ask the players' open desks for prices (with two computer banks, so the desk has competition)."""
    from simulation import ledger
    open_desks = _rows(conn, "SELECT d.player_id FROM floor_desks d JOIN players p ON p.id = d.player_id"
                             " WHERE d.open AND p.build = 'investment_banker' ORDER BY d.player_id")
    if not open_desks:
        return 0
    seed, slot = _seed(conn), int(now.timestamp()) // 30
    listed = _rows(conn, "SELECT c.ticker FROM companies c JOIN market_instruments m ON m.company_id = c.id"
                         " WHERE m.halted_reason IS NULL ORDER BY c.ticker")
    if not listed:
        return 0
    account = ledger.account_id(conn, ledger.INVESTORS_INSTITUTIONS)
    busy = _busy(conn, now)
    made = 0
    for d in open_desks:
        chance = data.FLOOR_CLIENT_CALL_CHANCE / (data.FLOOR_HOUR_CALL_FACTOR if busy else 1)
        if _unit(seed, "floor-call", slot, d["player_id"]) * chance >= 1:
            continue
        if _one(conn, "SELECT 1 AS x FROM floor_requests r JOIN floor_request_desks k ON k.request_id = r.id"
                      " WHERE k.desk_player = %s AND r.client_player IS NULL AND r.status = 'open'", (d["player_id"],)):
            continue                                # one computer call at a time to each desk
        name, _style, seconds = data.FLOOR_COMPUTER_CLIENTS[int(_unit(seed, "floor-client", slot, d["player_id"]) * len(data.FLOOR_COMPUTER_CLIENTS))]
        ticker = listed[int(_unit(seed, "floor-ticker", slot, d["player_id"]) * len(listed))]["ticker"]
        share = _share(conn, ticker, now)
        price = share["last_price"] or share["reference_price"]
        low, high = data.FLOOR_CLIENT_DEAL_NAIRA
        value = (low + round(_unit(seed, "floor-size", slot, d["player_id"]) * (high - low))) * 100
        quantity = max(value // max(price, 1) // 100 * 100, 100)
        side = "buy" if _unit(seed, "floor-side", slot, d["player_id"]) < 0.5 else "sell"
        rivals = sorted(COMPUTER, key=lambda c: _unit(seed, "floor-rival", slot, d["player_id"], c))[:2]
        with conn.transaction():
            _open_request(conn, account=account, player_id=None, client_name=name, kind="share", company_id=share["id"], side=side,
                          quantity=int(quantity), seconds=seconds, desks=[f"player:{d['player_id']}"] + [f"computer:{c}" for c in rivals], now=now,
                          exchange_bid=share["bids"][0]["price"] if share["bids"] else None,
                          exchange_offer=share["offers"][0]["price"] if share["offers"] else None)
        made += 1
    return made


def tick(conn: Connection, now: datetime) -> None:
    """Every few seconds of the server's loop: computer clients decide and call; requests whose time is up are closed; a
    banker who never answered a client taking their indicative price has backed away from it."""
    if not _one(conn, "SELECT to_regclass('floor_requests') IS NOT NULL AS ok")["ok"]:
        return
    for r in _rows(conn, "SELECT id FROM floor_requests WHERE status = 'open' AND client_player IS NULL AND quotes_until <= %s ORDER BY id", (now,)):
        _computer_decides(conn, _load_request(conn, r["id"]), now)
    for r in _rows(conn, "SELECT * FROM floor_requests WHERE status = 'open' AND client_player IS NOT NULL AND quotes_until <= %s ORDER BY id", (now,)):
        if _ends(conn, r) <= now:
            with conn.transaction():
                for c in _rows(conn, "SELECT c.id, c.kind, q.desk FROM floor_counters c JOIN floor_quotes q ON q.id = c.quote_id"
                                     " WHERE c.request_id = %s AND c.status = 'open'", (r["id"],)):
                    conn.execute("UPDATE floor_counters SET status = 'expired', answered_at = %s WHERE id = %s", (now, c["id"]))
                    if c["kind"] == "confirm" and _desk_player(c["desk"]):
                        conn.execute("UPDATE floor_desks SET backed_away = backed_away + 1 WHERE player_id = %s", (_desk_player(c["desk"]),))
                conn.execute("UPDATE floor_requests SET status = 'expired', done_at = %s WHERE id = %s AND status = 'open'", (now, r["id"]))
                conn.execute("UPDATE floor_quotes SET status = 'lost' WHERE request_id = %s AND status = 'live'", (r["id"],))
    conn.execute("UPDATE floor_tickets SET status = 'expired', done_at = %s WHERE status = 'open' AND valid_until <= %s", (now, now))
    if _one(conn, "SELECT to_regclass('floor_notes') IS NOT NULL AS ok")["ok"]:
        notes_tick(conn, now)
        hour_tick(conn, now)
    mandates_tick(conn, now)
    from simulation import prime  # the Archegos moment
    prime.tick(conn, now)
    if clock.market_state(now).value == "open":
        _computer_calls(conn, now)


# ---------------------------------------------------------------------------
# What each side sees
# ---------------------------------------------------------------------------

def _what(r: dict) -> dict:
    if r["kind"] == "bond":
        return {"label": r["code"], "name": r["bond_name"]}
    if r["kind"] == "basket":
        return {"label": " + ".join(leg["ticker"] for leg in r["legs"]), "name": "A basket of shares"}
    return {"label": r["ticker"], "name": r["company_name"]}


def client_record(conn: Connection, account, client_name: str | None) -> dict:
    """What a bank may know of a client: how many deals it has done on the Floor, and how often the share moved its way in
    the half hour after (a client who is usually right is priced more carefully)."""
    deals = _rows(conn, "SELECT t.company_id, t.price, t.at, t.client_bought FROM floor_trades t JOIN floor_requests r ON r.id = t.request_id"
                        " WHERE r.client_account = %s AND r.client_name IS NOT DISTINCT FROM %s AND t.company_id IS NOT NULL"
                        " ORDER BY t.id DESC LIMIT 30", (account, client_name))
    right = judged = 0
    for d in deals:
        later = _one(conn, "SELECT price FROM market_trades WHERE company_id = %s AND traded_at BETWEEN %s AND %s ORDER BY id DESC LIMIT 1",
                     (d["company_id"], d["at"], d["at"] + timedelta(minutes=30)))
        if later and later["price"] != d["price"]:
            judged += 1
            right += (later["price"] > d["price"]) == bool(d["client_bought"])
    return {"deals": len(deals), "judged": judged, "right_bps": right * BPS // judged if judged else None}


def _client_record(conn: Connection, r: dict) -> dict:
    out = client_record(conn, r["client_account"], r["client_name"])
    out.update(fishing(conn, r["client_player"]) if r["client_player"] else {"asked": 0, "dealt": 0, "fishing": False})
    return out


def scorecard(conn: Connection, account) -> dict:
    """Best execution: each of the client's deals against the exchange's best price when it asked, and against the
    second-best price it was given. Positive is money saved."""
    rows = _rows(conn, "SELECT t.id, t.at, t.price, t.quantity, t.cover, t.exchange_price, t.client_bought, c.ticker, substr(b.asset, 5) AS code"
                       " FROM floor_trades t JOIN floor_requests r ON r.id = t.request_id LEFT JOIN companies c ON c.id = t.company_id"
                       " LEFT JOIN bonds b ON b.id = t.bond_id WHERE r.client_account = %s ORDER BY t.id DESC LIMIT 20", (account,))
    fee = data.EXCHANGE_FEE_BPS + data.STAMP_DUTY_BPS
    out, saved = [], []
    for t in rows:
        sign = 1 if t["client_bought"] else -1
        vs_exchange = sign * (t["exchange_price"] - t["price"]) * BPS // t["exchange_price"] if t["exchange_price"] else None
        vs_cover = sign * (t["cover"] - t["price"]) * BPS // t["cover"] if t["cover"] else None
        if vs_exchange is not None and t["code"] is None:
            vs_exchange += fee                         # the exchange would also have charged its fee
        out.append({"id": t["id"], "at": t["at"], "what": t["ticker"] or t["code"], "price": t["price"], "quantity": t["quantity"],
                    "bought": t["client_bought"], "vs_exchange_bps": vs_exchange, "vs_cover_bps": vs_cover})
        if vs_exchange is not None:
            saved.append(vs_exchange)
    return {"deals": out, "average_vs_exchange_bps": sum(saved) // len(saved) if saved else None}


def blocks_reported(conn: Connection, now: datetime) -> list[dict]:
    """Block deals are reported to the whole market once done: the share, the size and the price, never who."""
    return _rows(conn, "SELECT t.at, c.ticker, t.quantity, t.price FROM floor_trades t JOIN companies c ON c.id = t.company_id"
                       " WHERE t.block AND t.at > %s ORDER BY t.at DESC LIMIT 10", (now - timedelta(days=3),))


def requests_view(conn: Connection, player_id, now: datetime) -> dict:
    """A client sees their own requests with every price sent to them; a banker sees the requests sent to their desk with
    only their own price (never another bank's until the deal is done, and then only the price that beat them), the
    client's record, the market and their own holdings to price from."""
    from simulation import empires, ledger
    account = ledger.player_account_id(conn, player_id)
    seat = empires.seat_of(conn, player_id)
    empire_account = seat["account_id"] if seat and seat["empire_status"] == "active" and (
        seat["build"] == "asset_manager" or seat["head_player_id"] == player_id) else None
    desk = _one(conn, "SELECT open, failed, backed_away FROM floor_desks WHERE player_id = %s", (player_id,))
    mine = []
    for row in _rows(conn, "SELECT id FROM floor_requests WHERE client_player = %s ORDER BY status = 'open' DESC, id DESC LIMIT 12", (player_id,)):
        r = _load_request(conn, row["id"])
        counters = {c["quote_id"]: c for c in _rows(conn, "SELECT * FROM floor_counters WHERE request_id = %s ORDER BY id", (r["id"],))}
        quotes = []
        for q in _rows(conn, "SELECT * FROM floor_quotes WHERE request_id = %s AND shown_at <= %s AND status <> 'replaced' ORDER BY id", (r["id"], now)):
            rec = _record(conn, _desk_player(q["desk"])) if _desk_player(q["desk"]) else {"failed": 0, "backed_away": 0}
            c = counters.get(q["id"])
            quotes.append({"id": q["id"], "desk": _desk_name(conn, q["desk"]), "kind": q["desk"].split(":", 1)[0], **rec,
                           "bid": q["bid"], "offer": q["offer"], "margin_bps": q["margin_bps"], "firm": q["firm"],
                           "bid_yield_bps": yield_at(_bond(conn, r["code"], now), q["bid"]) if r["kind"] == "bond" and q["bid"] else None,
                           "offer_yield_bps": yield_at(_bond(conn, r["code"], now), q["offer"]) if r["kind"] == "bond" and q["offer"] else None,
                           "valid_until": q["valid_until"], "status": q["status"],
                           "asked": {"kind": c["kind"], "price": c["price"], "margin_bps": c["margin_bps"], "status": c["status"]} if c else None})
        asked = [_desk_name(conn, d["desk"]) for d in _rows(conn, "SELECT desk FROM floor_request_desks WHERE request_id = %s ORDER BY desk", (r["id"],))]
        trades = _rows(conn, "SELECT price, quantity, desk, cover FROM floor_trades WHERE request_id = %s ORDER BY id", (r["id"],))
        mine.append({"id": r["id"], "kind": r["kind"], **_what(r), "ticker": r["ticker"], "side": r["side"], "quantity": r["quantity"],
                     "legs": [{"ticker": leg["ticker"], "quantity": leg["quantity"], "mid": leg["mid"]} for leg in r["legs"]],
                     "block": r["block"], "for_empire": r["for_empire"] is not None,
                     "created_at": r["created_at"], "quotes_until": r["quotes_until"], "status": r["status"], "asked": asked, "quotes": quotes,
                     "deal": {"price": trades[0]["price"], "quantity": r["quantity"], "desk": _desk_name(conn, trades[0]["desk"]),
                              "cover": trades[0]["cover"]} if trades else None})
    incoming = []
    if desk is not None:
        held: dict = {}
        for row in _rows(conn, "SELECT r.id FROM floor_requests r JOIN floor_request_desks k ON k.request_id = r.id AND k.desk_player = %s"
                               " ORDER BY r.status = 'open' DESC, r.id DESC LIMIT 15", (player_id,)):
            r = _load_request(conn, row["id"])
            own = _one(conn, "SELECT id, bid, offer, margin_bps, firm, valid_until, status FROM floor_quotes WHERE request_id = %s AND desk = %s"
                             " AND status <> 'replaced' ORDER BY id DESC LIMIT 1", (r["id"], f"player:{player_id}"))
            ask_me = _one(conn, "SELECT id, kind, side, price, margin_bps, status, created_at FROM floor_counters WHERE quote_id = %s AND status = 'open'",
                          (own["id"],)) if own else None
            trade = _one(conn, "SELECT desk, price, cover FROM floor_trades WHERE request_id = %s ORDER BY id LIMIT 1", (r["id"],))
            client = _one(conn, "SELECT display_name FROM players WHERE id = %s", (r["client_player"],)) if r["client_player"] else None
            if r["kind"] == "share":
                if r["ticker"] not in held and account:
                    held[r["ticker"]] = ledger.balance(conn, account, _one(conn, "SELECT share_asset FROM companies WHERE id = %s", (r["company_id"],))["share_asset"])
                market = exchange.quote(conn, r["ticker"], now, depth=1) if r["status"] == "open" else None
                info = {"best_bid": market["bids"][0]["price"] if market and market["bids"] else None,
                        "best_offer": market["offers"][0]["price"] if market and market["offers"] else None,
                        "last": market["last_price"] if market else None, "reference": market["reference_price"] if market else None,
                        "low": market["lowest_today"] if market else None, "high": market["highest_today"] if market else None}
                you_hold = held.get(r["ticker"], 0)
            elif r["kind"] == "bond":
                bond = _bond(conn, r["code"], now)
                info = {"best_bid": bond["bid"], "best_offer": bond["ask"], "last": None, "reference": bond["fair"], "low": None, "high": None,
                        "fair_yield_bps": yield_at(bond, bond["fair"])}
                you_hold = ledger.balance(conn, account, bond["asset"]) if account else 0
            else:
                info = {"best_bid": None, "best_offer": None, "last": None, "reference": None, "low": None, "high": None}
                you_hold = 0
            incoming.append({
                "id": r["id"], "kind": r["kind"], **_what(r), "ticker": r["ticker"], "side": r["side"], "quantity": r["quantity"],
                "legs": [{"ticker": leg["ticker"], "quantity": leg["quantity"], "mid": leg["mid"]} for leg in r["legs"]], "block": r["block"],
                "client": client["display_name"] if client else (r["client_name"] or "A client"), "computer_client": r["client_player"] is None,
                "for_empire": r["for_empire"] is not None,
                "record": _client_record(conn, r),
                "created_at": r["created_at"], "quotes_until": r["quotes_until"], "status": r["status"],
                "your_quote": {k: own[k] for k in ("bid", "offer", "margin_bps", "firm", "valid_until", "status")} if own else None,
                "asked_you": ask_me,
                "outcome": None if r["status"] == "open" else ("won" if trade and trade["desk"] == f"player:{player_id}" else
                                                               "traded away" if trade else "passed" if r["status"] == "passed" else "no deal"),
                # Once it is done, the losers see the price that beat them, and the winner the one it beat.
                "done_at_price": trade["price"] if trade and r["kind"] != "basket" else None,
                "cover": trade["cover"] if trade and trade["desk"] == f"player:{player_id}" else None,
                "you_hold": you_hold, "market": info,
            })
    deals = _rows(conn, "SELECT t.id, t.at, coalesce(c.ticker, substr(b.asset, 5)) AS what, t.price, t.quantity, t.desk, t.buyer_account IN (%s, %s) AS bought,"
                        " r.client_player, r.client_name, t.ticket_id, p.display_name AS client_display FROM floor_trades t"
                        " LEFT JOIN companies c ON c.id = t.company_id LEFT JOIN bonds b ON b.id = t.bond_id"
                        " LEFT JOIN floor_requests r ON r.id = t.request_id LEFT JOIN players p ON p.id = r.client_player"
                        " WHERE t.buyer_account IN (%s, %s) OR t.seller_account IN (%s, %s) ORDER BY t.id DESC LIMIT 15",
                  (account, empire_account, account, empire_account, account, empire_account))
    return {
        "now": now, "market_state": clock.market_state(now).value,
        "is_banker": _is_banker(conn, player_id), "desk_open": bool(desk and desk["open"]),
        "desk_failed": desk["failed"] if desk else 0, "desk_backed_away": desk["backed_away"] if desk else 0,
        "can_trade_for_empire": empire_account is not None,
        "your_axes": _rows(conn, "SELECT c.ticker, a.side, a.quantity FROM floor_axes a JOIN companies c ON c.id = a.company_id"
                                 " WHERE a.player_id = %s AND a.until > %s ORDER BY c.ticker", (player_id, now)),
        "desks": desks_for(conn, player_id, now),
        "limits": {"window": list(data.FLOOR_WINDOW_SECONDS), "quote": list(data.FLOOR_QUOTE_SECONDS), "most_desks": data.FLOOR_MOST_DESKS,
                   "basket_most": data.FLOOR_BASKET_MOST, "block_least": data.FLOOR_BLOCK_LEAST_NAIRA * 100},
        "mine": mine, "incoming": incoming,
        "deals": [{"id": t["id"], "at": t["at"], "ticker": t["what"], "price": t["price"], "quantity": t["quantity"], "bought": t["bought"],
                   "with": "a ticket from the chat" if t["ticket_id"] else
                           _desk_name(conn, t["desk"]) if str(t["client_player"]) == str(player_id) else (t["client_display"] or t["client_name"] or "a client"),
                   "as": "ticket" if t["ticket_id"] else "client" if str(t["client_player"]) == str(player_id) else "bank"} for t in deals],
        "scorecard": scorecard(conn, account),
        "blocks": blocks_reported(conn, now),
        "chat": chat_view(conn, player_id, now),
        "mandates": mandates_view(conn, player_id, now),
        "swaps": _prime_view(conn, player_id, now),
    }


# ---------------------------------------------------------------------------
# Slice 4: the Floor in live events, the floor hour, fishing, and the Floor's wrongs
# ---------------------------------------------------------------------------

def floor_hour(now: datetime) -> tuple[datetime, datetime] | None:
    """The floor hour running at `now`, if one is: every trading day, an hour of busier client calls."""
    lagos = clock.to_lagos(now)
    starts = lagos.replace(hour=data.FLOOR_HOUR, minute=0, second=0, microsecond=0)
    if starts <= lagos < starts + timedelta(hours=1) and clock.market_state(now).value == "open":
        return starts, starts + timedelta(hours=1)
    return None


def _live_event(conn: Connection) -> dict | None:
    if not _one(conn, "SELECT to_regclass('live_events') IS NOT NULL AS ok")["ok"]:
        return None
    return _one(conn, "SELECT * FROM live_events WHERE status = 'open' ORDER BY starts_at DESC LIMIT 1")


def _busy(conn: Connection, now: datetime) -> bool:
    event = _live_event(conn)
    return floor_hour(now) is not None or bool(event and event["starts_at"] <= now < event["ends_at"])


def _note(conn: Connection, key: str, kind: str, words: str, now: datetime, ticker: str | None = None) -> None:
    conn.execute("INSERT INTO floor_notes (key, at, kind, words, ticker) VALUES (%s, %s, %s, %s, %s) ON CONFLICT (key) DO NOTHING",
                 (key, now, kind, words[:300], ticker))


def notes_tick(conn: Connection, now: datetime) -> None:
    """The game's words on the Floor during a live event (at the bell, halfway, five minutes before the end, and when the
    featured share has moved) and at the floor hour's start and end."""
    if not _one(conn, "SELECT to_regclass('floor_notes') IS NOT NULL AS ok")["ok"]:
        return
    event = _live_event(conn)
    if event and event["starts_at"] <= now < event["ends_at"]:
        e = event["id"]
        minutes = (now - event["starts_at"]).total_seconds() / 60
        featured = _one(conn, "SELECT ticker FROM companies WHERE id = %s", (event["featured_company_id"],))["ticker"]
        _note(conn, f"live:{e}:bell", "nudge", f"Live: {event['headline']} Banks: make sure you give fast and competitive prices to your "
              "clients. Asset managers: make sure you get your cash working.", now, featured)
        if minutes >= 15:
            _note(conn, f"live:{e}:half", "nudge", "We are now halfway through the live event: fifteen minutes left.", now)
        if minutes >= 25:
            _note(conn, f"live:{e}:last", "nudge", "Five minutes left in the live event. Deals done after the end do not count.", now)
        price = _share(conn, featured, now)
        last = price["last_price"] or price["reference_price"]
        move = (last - event["start_price"]) * BPS // event["start_price"]
        for step in (200, 400, 600):                 # each 2% the featured share moves from the bell is called out once
            if abs(move) >= step:
                _note(conn, f"live:{e}:move:{'up' if move > 0 else 'down'}:{step}", "drop",
                      f"{featured} is {'up' if move > 0 else 'down'} {abs(move) / 100:.1f}% since the bell.", now, featured)
    hour = floor_hour(now)
    if hour:
        day = hour[0].date().isoformat()
        _note(conn, f"hour:{day}:start", "hour", "The floor hour has begun: the clients call twice as often until 19:00. "
              "The best banks and the best-dealing clients of the hour are named at the end.", now)


def _window_scores(conn: Connection, since: datetime, until: datetime, *, companies: list | None = None) -> dict:
    """In a window of time: what each player's desk earned from the gap in its prices (against the market's middle when
    asked), and what each client saved against the exchange (with its fee)."""
    fee = data.EXCHANGE_FEE_BPS + data.STAMP_DUTY_BPS
    banks: dict = {}
    clients: dict = {}
    for t in _rows(conn, "SELECT t.*, r.exchange_bid, r.exchange_offer, r.client_player FROM floor_trades t JOIN floor_requests r ON r.id = t.request_id"
                         " WHERE t.at >= %s AND t.at < %s AND t.company_id IS NOT NULL" + (" AND t.company_id = ANY(%s)" if companies else ""),
                   (since, until, companies) if companies else (since, until)):
        mid = (t["exchange_bid"] + t["exchange_offer"]) // 2 if t["exchange_bid"] and t["exchange_offer"] else None
        desk = _desk_player(t["desk"])
        if desk and mid:
            edge = (t["price"] - mid) if t["client_bought"] else (mid - t["price"])
            banks[desk] = banks.get(desk, 0) + edge * t["quantity"]
        if t["client_player"]:
            if t["client_bought"] and t["exchange_offer"]:
                saved = t["exchange_offer"] * (BPS + fee) // BPS - t["price"]
            elif not t["client_bought"] and t["exchange_bid"]:
                saved = t["price"] - t["exchange_bid"] * (BPS - fee) // BPS
            else:
                continue
            key = str(t["client_player"])
            clients[key] = clients.get(key, 0) + saved * t["quantity"]
    return {"bank": banks, "client": clients}


def _rank(conn: Connection, key: str, scores: dict, now: datetime, award=None) -> list[dict]:
    out = []
    for role, table in scores.items():
        best = sorted(((p, a) for p, a in table.items() if a > 0), key=lambda pa: -pa[1])[:len(data.FLOOR_PLACES)]
        for place, (player, amount) in enumerate(best, 1):
            points = award(player, role, place) if award else 0
            conn.execute("INSERT INTO floor_scores (window_key, player_id, role, amount, place, points, at) VALUES (%s, %s, %s, %s, %s, %s, %s)"
                         " ON CONFLICT DO NOTHING", (key, player, role, amount, place, points, now))
            out.append({"player": player, "role": role, "place": place, "points": points})
    return out


def live_scores(conn: Connection, event: dict, now: datetime) -> list[dict]:
    """When a live event is scored: the best three banks and clients on the Floor during it, in the shares it touched,
    earn their empires league points (5, 3, 1)."""
    from simulation import careers, empires, leagues
    if not _one(conn, "SELECT to_regclass('floor_scores') IS NOT NULL AS ok")["ok"]:
        return []
    touched = [t["company_id"] for t in event["touched"]]
    scores = _window_scores(conn, event["starts_at"], event["ends_at"], companies=touched)
    period = careers.world_now(conn, now)["period"]

    def award(player, role, place):
        seat = empires.seat_of(conn, player)
        if not seat or seat["empire_status"] != "active" or seat["empire_kind"] != "player":
            return 0
        points = data.FLOOR_PLACES[place - 1]
        leagues.award(conn, seat["empire_id"], points, f"Live event on the Floor: one of the best {'banks' if role == 'bank' else 'clients'}",
                      period, now, reference=f"live:{event['id']}:floor_{role}:{place}")
        return points
    ranked = _rank(conn, f"live:{event['id']}", scores, now, award)
    if ranked:
        _note(conn, f"live:{event['id']}:floor", "nudge", "The live event is over. The Floor's best: " + "; ".join(
            f"{_one(conn, 'SELECT display_name FROM players WHERE id = %s', (r['player'],))['display_name']} ({'bank' if r['role'] == 'bank' else 'client'}, {r['place']})"
            for r in ranked) + ".", now)
    return ranked


def hour_tick(conn: Connection, now: datetime) -> None:
    """After each floor hour: its best three banks and clients are named on the Floor."""
    lagos = clock.to_lagos(now)
    starts = lagos.replace(hour=data.FLOOR_HOUR, minute=0, second=0, microsecond=0)
    ends = starts + timedelta(hours=1)
    if not ends <= lagos < ends + timedelta(hours=3):
        return
    key = f"hour:{starts.date().isoformat()}"
    if _one(conn, "SELECT 1 AS x FROM floor_notes WHERE key = %s", (f"{key}:end",)):
        return
    ranked = _rank(conn, key, _window_scores(conn, starts, ends), now)
    names = {str(r["player"]): _one(conn, "SELECT display_name FROM players WHERE id = %s", (r["player"],))["display_name"] for r in ranked}
    _note(conn, f"{key}:end", "hour", "The floor hour is over. " + ("Best: " + "; ".join(
        f"{names[str(r['player'])]} ({'bank' if r['role'] == 'bank' else 'client'}, {r['place']})" for r in ranked) + "."
        if ranked else "No deals were scored."), now)


def fishing(conn: Connection, client_player) -> dict:
    """A client's last ten requests: how many were dealt. One who asks and asks and never deals is fishing for prices."""
    rows = _rows(conn, "SELECT status FROM floor_requests WHERE client_player = %s AND status <> 'open' ORDER BY id DESC LIMIT 10", (client_player,))
    dealt = sum(1 for r in rows if r["status"] == "done")
    return {"asked": len(rows), "dealt": dealt, "fishing": len(rows) >= data.FLOOR_FISHING_ASKS and dealt == 0}


def notes(conn: Connection, now: datetime, limit: int = 12) -> list[dict]:
    if not _one(conn, "SELECT to_regclass('floor_notes') IS NOT NULL AS ok")["ok"]:
        return []
    return _rows(conn, "SELECT at, kind, words, ticker FROM floor_notes WHERE at > %s AND at <= %s ORDER BY at DESC, id DESC LIMIT %s",
                 (now - timedelta(hours=6), now, limit))


def event_pnl(conn: Connection, account, now: datetime) -> dict | None:
    """During a live event: what the shares it touched have done to the account since the bell (on what it holds now)."""
    from simulation import ledger
    event = _live_event(conn)
    if not event or not event["starts_at"] <= now < event["ends_at"]:
        return None
    total = 0
    for t in event["touched"]:
        asset = _one(conn, "SELECT share_asset, ticker FROM companies WHERE id = %s", (t["company_id"],))
        held = ledger.balance(conn, account, asset["share_asset"])
        if held:
            share = _share(conn, asset["ticker"], now)
            total += held * ((share["last_price"] or share["reference_price"]) - t["price"])
    return {"name": event["headline"], "pnl": total, "ends_at": event["ends_at"]}


# ---------------------------------------------------------------------------
# The Floor's wrongs, for the tribunal
# ---------------------------------------------------------------------------

def wrongs(conn: Connection, since: datetime, now: datetime) -> list[dict]:
    """Wrongs a banker can do on the Floor, found in the books:
      * trading ahead: while a client's request was open to their desk, the banker traded the share on the exchange on the
        client's side, then dealt with the client;
      * passing on an order: while a client's request was open to their desk, the banker wrote the share's code in the
        Floor chat to somebody else, who then traded it on the client's side;
      * agreeing prices: two banks that both priced the same request wrote to each other while it was open."""
    from simulation import ledger
    if not _one(conn, "SELECT to_regclass('floor_requests') IS NOT NULL AS ok")["ok"]:
        return []
    out = []
    for r in _rows(conn, "SELECT r.*, c.ticker, k.desk_player FROM floor_requests r JOIN floor_request_desks k ON k.request_id = r.id"
                         " JOIN companies c ON c.id = r.company_id WHERE k.desk_player IS NOT NULL AND r.kind = 'share' AND r.created_at >= %s"
                         " AND r.side <> 'two_way' ORDER BY r.id", (since,)):
        closes = r["done_at"] or r["quotes_until"]
        desk_account = ledger.player_account_id(conn, r["desk_player"])
        client_buys = r["side"] == "buy"
        deal = _one(conn, "SELECT price, quantity FROM floor_trades WHERE request_id = %s AND desk = %s LIMIT 1", (r["id"], f"player:{r['desk_player']}"))
        ahead = _rows(conn, "SELECT price, quantity, traded_at FROM market_trades WHERE company_id = %s AND traded_at >= %s AND traded_at <= %s"
                            " AND " + ("buyer_account_id" if client_buys else "seller_account_id") + " = %s",
                      (r["company_id"], r["created_at"], closes, desk_account))
        if deal and ahead:
            shares = min(sum(a["quantity"] for a in ahead), deal["quantity"])
            average = sum(a["price"] * a["quantity"] for a in ahead) // max(sum(a["quantity"] for a in ahead), 1)
            gain = shares * ((deal["price"] - average) if client_buys else (average - deal["price"]))
            if gain > 0:
                out.append({"kind": "front_running", "key": f"front_running:{r['id']}", "defendant_id": r["desk_player"],
                            "victim_account": r["client_account"], "company_id": r["company_id"], "ticker": r["ticker"], "amount": gain,
                            "lines": [{"what": f"Traded {shares:,} {r['ticker']} on the exchange at about {_money(average)} while a client's request was open",
                                       "side": "bought" if client_buys else "sold"},
                                      {"what": f"Then dealt them to the client at {_money(deal['price'])}"}],
                            "words": f"Traded {r['ticker']} ahead of a client's request on the Floor, and dealt with the client at a worse price."})
        for line in _rows(conn, "SELECT f.to_player, f.at, f.body FROM floor_chat f WHERE f.from_player = %s AND f.at >= %s AND f.at <= %s",
                          (r["desk_player"], r["created_at"], closes)):
            if str(line["to_player"]) == str(r["client_player"]) or r["ticker"].lower() not in line["body"].lower():
                continue
            other = ledger.player_account_id(conn, line["to_player"])
            used = _rows(conn, "SELECT price, quantity FROM market_trades WHERE company_id = %s AND traded_at >= %s AND traded_at <= %s"
                               " AND " + ("buyer_account_id" if client_buys else "seller_account_id") + " = %s",
                         (r["company_id"], line["at"], closes + timedelta(minutes=30), other))
            if used:
                value = sum(u["price"] * u["quantity"] for u in used)
                out.append({"kind": "order_leak", "key": f"order_leak:{r['id']}:{line['to_player']}", "defendant_id": r["desk_player"],
                            "victim_account": r["client_account"], "company_id": r["company_id"], "ticker": r["ticker"],
                            "amount": value * data.FLOOR_LEAK_BPS // BPS,
                            "lines": [{"what": f"Wrote about {r['ticker']} to another player while a client's request in it was open"},
                                      {"what": f"That player then traded {_money(value)} of it on the client's side"}],
                            "words": f"Passed a client's order in {r['ticker']} on the Floor to another player, who traded on it."})
    for pair in _rows(conn, "SELECT r.id, r.company_id, c.ticker, r.quantity, r.exchange_bid, r.exchange_offer, r.created_at,"
                            " coalesce(r.done_at, r.quotes_until) AS closes, a.desk_player AS a, b.desk_player AS b"
                            " FROM floor_requests r JOIN companies c ON c.id = r.company_id"
                            " JOIN floor_request_desks a ON a.request_id = r.id AND a.desk_player IS NOT NULL"
                            " JOIN floor_request_desks b ON b.request_id = r.id AND b.desk_player IS NOT NULL AND b.desk_player > a.desk_player"
                            " WHERE r.created_at >= %s AND r.kind = 'share'", (since,)):
        quoted = _one(conn, "SELECT count(DISTINCT desk)::int AS n FROM floor_quotes WHERE request_id = %s AND desk IN (%s, %s)",
                      (pair["id"], f"player:{pair['a']}", f"player:{pair['b']}"))["n"]
        talked = _one(conn, "SELECT 1 AS x FROM floor_chat WHERE ((from_player = %s AND to_player = %s) OR (from_player = %s AND to_player = %s))"
                            " AND at >= %s AND at <= %s LIMIT 1", (pair["a"], pair["b"], pair["b"], pair["a"], pair["created_at"], pair["closes"]))
        if quoted == 2 and talked:
            mid = ((pair["exchange_bid"] or 0) + (pair["exchange_offer"] or 0)) // 2 or 1
            for who in (pair["a"], pair["b"]):
                out.append({"kind": "collusion", "key": f"collusion:{pair['id']}:{who}", "defendant_id": who, "victim_account": None,
                            "company_id": pair["company_id"], "ticker": pair["ticker"], "amount": mid * pair["quantity"] * data.FLOOR_COLLUSION_BPS // BPS,
                            "lines": [{"what": f"Both banks priced the same request in {pair['ticker']}, and wrote to each other while it was open"}],
                            "words": f"Agreed prices with another bank on a client's request in {pair['ticker']} on the Floor."})
    return out


# ---------------------------------------------------------------------------
# Big client orders (mandates), and the deal tape
# ---------------------------------------------------------------------------

def _offer_mandate(conn: Connection, player_id, company: dict, quantity: int, client: str, now: datetime, event_id=None) -> int:
    row = _one(conn, "INSERT INTO floor_mandates (player_id, client_name, company_id, quantity, offered_at, answer_by, event_id)"
                     " VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id",
               (player_id, client, company["id"], quantity, now, now + timedelta(minutes=data.FLOOR_MANDATE_ANSWER_MINUTES), event_id))
    _ping_player(conn, player_id)
    return row["id"]


def _mandate_size(conn: Connection, player_id, price: int) -> int:
    from simulation import ledger
    cash = ledger.balance(conn, ledger.player_account_id(conn, player_id))
    low, high = data.FLOOR_MANDATE_NAIRA
    value = min(max(cash * data.FLOOR_MANDATE_CASH_BPS // BPS, low * 100), high * 100)
    return max(value // max(price, 1) // 100 * 100, 100)


def _free_managers(conn: Connection) -> list[dict]:
    return _rows(conn, "SELECT p.id FROM players p WHERE p.build = 'asset_manager' AND NOT EXISTS (SELECT 1 FROM floor_mandates m"
                       " WHERE m.player_id = p.id AND m.status IN ('offered', 'working')) ORDER BY p.id")


def mandates_tick(conn: Connection, now: datetime) -> None:
    """Offers lapse; mandates whose time is up are delivered and scored; free asset managers are offered new ones (each one
    at a live event's bell, in its featured share)."""
    if not _one(conn, "SELECT to_regclass('floor_mandates') IS NOT NULL AS ok")["ok"]:
        return
    conn.execute("UPDATE floor_mandates SET status = 'lapsed' WHERE status = 'offered' AND answer_by <= %s", (now,))
    for m in _rows(conn, "SELECT id FROM floor_mandates WHERE status = 'working' AND deadline <= %s ORDER BY id", (now,)):
        settle_mandate(conn, m["id"], now)
    if clock.market_state(now).value != "open":
        return
    seed, slot = _seed(conn), int(now.timestamp()) // 30
    event = _live_event(conn)
    listed = _rows(conn, "SELECT c.id, c.ticker FROM companies c JOIN market_instruments m ON m.company_id = c.id WHERE m.halted_reason IS NULL ORDER BY c.ticker")
    for p in _free_managers(conn):
        if event and event["starts_at"] <= now < event["ends_at"] - timedelta(minutes=10):
            if _one(conn, "SELECT 1 AS x FROM floor_mandates WHERE player_id = %s AND event_id = %s", (p["id"], event["id"])):
                continue
            company = _one(conn, "SELECT id, ticker FROM companies WHERE id = %s", (event["featured_company_id"],))
        else:
            if not listed or _unit(seed, "mandate", slot, p["id"]) * data.FLOOR_MANDATE_CHANCE >= 1:
                continue
            company = listed[int(_unit(seed, "mandate-share", slot, p["id"]) * len(listed))]
        share = _share(conn, company["ticker"], now)
        client = data.FLOOR_COMPUTER_CLIENTS[int(_unit(seed, "mandate-client", slot, p["id"]) * len(data.FLOOR_COMPUTER_CLIENTS))][0]
        with conn.transaction():
            _offer_mandate(conn, p["id"], company, _mandate_size(conn, p["id"], share["last_price"] or share["reference_price"]), client, now,
                           event["id"] if event and event["starts_at"] <= now < event["ends_at"] else None)


def answer_mandate(conn: Connection, player_id, mandate_id: int, accept: bool, now: datetime) -> dict:
    """The asset manager takes the order on (the clock starts) or turns it down."""
    from simulation import ledger
    with conn.transaction():
        m = _one(conn, "SELECT m.*, c.share_asset FROM floor_mandates m JOIN companies c ON c.id = m.company_id WHERE m.id = %s FOR UPDATE OF m", (mandate_id,))
        if m is None or str(m["player_id"]) != str(player_id):
            raise FloorError("There is no such order for you.")
        if m["status"] != "offered" or now >= m["answer_by"]:
            raise FloorError("That order is no longer on offer.")
        if not accept:
            conn.execute("UPDATE floor_mandates SET status = 'declined' WHERE id = %s", (mandate_id,))
            return {"declined": mandate_id}
        event = _one(conn, "SELECT ends_at FROM live_events WHERE id = %s", (m["event_id"],)) if m["event_id"] else None
        deadline = event["ends_at"] if event else now + timedelta(minutes=data.FLOOR_MANDATE_MINUTES)
        held = ledger.balance(conn, ledger.player_account_id(conn, player_id), m["share_asset"])
        conn.execute("UPDATE floor_mandates SET status = 'working', started_at = %s, deadline = %s, held_before = %s WHERE id = %s",
                     (now, deadline, held, mandate_id))
    return {"working": mandate_id, "deadline": deadline}


def _benchmark(conn: Connection, company_id, since: datetime, until: datetime, fallback: int) -> int:
    """The market's average price over the window: every trade on the exchange and on the Floor, weighted by size."""
    row = _one(conn, "SELECT sum(price * quantity)::numeric AS v, sum(quantity)::numeric AS q FROM ("
                     " SELECT price, quantity FROM market_trades WHERE company_id = %s AND traded_at >= %s AND traded_at < %s"
                     " UNION ALL SELECT price, quantity FROM floor_trades WHERE company_id = %s AND at >= %s AND at < %s) t",
               (company_id, since, until, company_id, since, until))
    return int(row["v"] // row["q"]) if row and row["q"] else fallback


def settle_mandate(conn: Connection, mandate_id: int, now: datetime) -> dict:
    """At the deadline the fund takes what the manager bought for it (never more than it asked for), at the market's
    average price over the window, and pays its commission. Scored on the manager's average price against that average."""
    from simulation import corporate, ledger
    from simulation.ledger import Leg
    with conn.transaction():
        m = _one(conn, "SELECT m.*, c.share_asset, c.ticker, c.name FROM floor_mandates m JOIN companies c ON c.id = m.company_id"
                       " WHERE m.id = %s FOR UPDATE OF m", (mandate_id,))
        if m is None or m["status"] != "working":
            return {}
        account = ledger.player_account_id(conn, m["player_id"])
        fund = ledger.account_id(conn, ledger.INVESTORS_INSTITUTIONS)
        bought = _rows(conn, "SELECT price, quantity FROM market_trades WHERE company_id = %s AND buyer_account_id = %s AND seller_account_id <> %s"
                             " AND traded_at >= %s AND traded_at < %s UNION ALL SELECT price, quantity FROM floor_trades WHERE company_id = %s"
                             " AND buyer_account = %s AND at >= %s AND at < %s",
                       (m["company_id"], account, account, m["started_at"], m["deadline"], m["company_id"], account, m["started_at"], m["deadline"]))
        got = sum(b["quantity"] for b in bought)
        average = sum(b["price"] * b["quantity"] for b in bought) // got if got else None
        held = ledger.balance(conn, account, m["share_asset"])
        delivered = max(min(m["quantity"], got, held - (m["held_before"] or 0) if held > (m["held_before"] or 0) else 0, held), 0)
        share = _share(conn, m["ticker"], now)
        benchmark = _benchmark(conn, m["company_id"], m["started_at"], m["deadline"], share["last_price"] or share["reference_price"])
        value = delivered * benchmark
        commission = value * data.FLOOR_MANDATE_COMMISSION_BPS // BPS
        if delivered > 0 and ledger.balance(conn, fund) >= value + commission:
            ledger.post(conn, kind="floor_mandate", memo=f"{delivered:,} {m['name']} shares delivered to {m['client_name']}, at the market's average",
                        reference=f"mandate:{mandate_id}",
                        legs=[Leg(account, -delivered, m["share_asset"]), Leg(fund, delivered, m["share_asset"]),
                              Leg(fund, -(value + commission)), Leg(account, value + commission)])
            conn.execute("INSERT INTO holding_events (account_id, company_id, kind, shares, amount, after_trade_id) VALUES (%s, %s, 'floor', %s, %s, %s)",
                         (account, m["company_id"], -delivered, value + commission, corporate._after_trade(conn)))
        else:
            delivered = 0
        score = (benchmark - average) * BPS // benchmark if average and benchmark else None
        conn.execute("UPDATE floor_mandates SET status = 'done', delivered = %s, benchmark = %s, average_paid = %s, commission = %s, score_bps = %s,"
                     " done_at = %s WHERE id = %s", (delivered, benchmark, average, commission if delivered else 0, score, now, mandate_id))
        _ping_player(conn, m["player_id"])
    return {"delivered": delivered, "benchmark": benchmark, "score_bps": score}


def mandates_view(conn: Connection, player_id, now: datetime) -> list[dict]:
    from simulation import ledger
    if not _one(conn, "SELECT to_regclass('floor_mandates') IS NOT NULL AS ok")["ok"]:
        return []
    account = ledger.player_account_id(conn, player_id)
    out = []
    for m in _rows(conn, "SELECT m.*, c.ticker, c.name, c.share_asset FROM floor_mandates m JOIN companies c ON c.id = m.company_id"
                         " WHERE m.player_id = %s ORDER BY m.status IN ('offered', 'working') DESC, m.id DESC LIMIT 8", (player_id,)):
        row = {k: m[k] for k in ("id", "client_name", "ticker", "name", "quantity", "offered_at", "answer_by", "status", "started_at",
                                 "deadline", "delivered", "benchmark", "average_paid", "commission", "score_bps")}
        row["live_event"] = m["event_id"] is not None
        if m["status"] == "working" and account:
            row["bought_so_far"] = max(ledger.balance(conn, account, m["share_asset"]) - (m["held_before"] or 0), 0)
        out.append(row)
    return out


def mandate_record(conn: Connection, player_id) -> dict:
    rows = _rows(conn, "SELECT score_bps, delivered, quantity FROM floor_mandates WHERE player_id = %s AND status = 'done'", (player_id,)) \
        if _one(conn, "SELECT to_regclass('floor_mandates') IS NOT NULL AS ok")["ok"] else []
    scored = [r["score_bps"] for r in rows if r["score_bps"] is not None]
    return {"mandates": len(rows), "completed": sum(1 for r in rows if r["delivered"] and r["delivered"] >= r["quantity"]),
            "average_score_bps": sum(scored) // len(scored) if scored else None}


def tape(conn: Connection, now: datetime) -> list[dict]:
    """The deal tape: every deal on the Floor and every big trade on the exchange, newest first. A computer bank is named;
    a player's desk is "a desk"; a client never."""
    items = []
    if _one(conn, "SELECT to_regclass('floor_trades') IS NOT NULL AS ok")["ok"]:
        for t in _rows(conn, "SELECT t.at, coalesce(c.ticker, substr(b.asset, 5)) AS what, t.price, t.quantity, t.desk, t.client_bought, t.block, t.ticket_id"
                             " FROM floor_trades t LEFT JOIN companies c ON c.id = t.company_id LEFT JOIN bonds b ON b.id = t.bond_id"
                             " WHERE t.at > %s AND t.at <= %s ORDER BY t.at DESC LIMIT 25", (now - timedelta(hours=6), now)):
            who = "A chat ticket" if t["ticket_id"] else _desk_name(conn, t["desk"]) if t["desk"].startswith("computer:") else "A desk"
            verb = "sells" if t["client_bought"] else "buys"
            items.append({"at": t["at"], "venue": "block" if t["block"] else "floor", "words": f"{who} {verb if not t['ticket_id'] else 'trades'}",
                          "what": t["what"], "quantity": t["quantity"], "price": t["price"]})
    for t in _rows(conn, "SELECT t.traded_at AS at, c.ticker, t.price, t.quantity FROM market_trades t JOIN companies c ON c.id = t.company_id"
                         " WHERE t.traded_at > %s AND t.traded_at <= %s AND t.price * t.quantity >= %s ORDER BY t.traded_at DESC LIMIT 15",
                   (now - timedelta(hours=6), now, data.FLOOR_TAPE_EXCHANGE_NAIRA * 100)):
        items.append({"at": t["at"], "venue": "exchange", "words": "Exchange", "what": t["ticker"], "quantity": t["quantity"], "price": t["price"]})
    return sorted(items, key=lambda x: x["at"], reverse=True)[:30]


def _prime_view(conn: Connection, player_id, now: datetime) -> list[dict]:
    from simulation import prime
    return prime.view(conn, player_id, now)
