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
# Slice 2: price requests between clients and banks
# ---------------------------------------------------------------------------

class FloorError(Exception):
    """A request, a quote or a deal the Floor refuses, with a message for the player."""


SIDE_WORDS = {"buy": "buy", "sell": "sell", "two_way": "a price both ways"}


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


def _desk_account(conn: Connection, desk: str):
    if desk.startswith("computer:"):
        from simulation import ledger
        return ledger.account_id(conn, ledger.INVESTORS_INSTITUTIONS)
    from simulation import ledger
    return ledger.player_account_id(conn, desk.split(":", 1)[1])


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


def _share(conn: Connection, ticker: str, now: datetime) -> dict:
    found = exchange.quote(conn, ticker, now, depth=1)
    if found is None:
        raise FloorError("There is no share with that code on the exchange.")
    company = _one(conn, "SELECT c.id, c.ticker, c.name, c.share_asset, m.halted_reason,"
                         " (SELECT r.shares_in_issue FROM company_results r WHERE r.company_id = c.id ORDER BY r.period DESC LIMIT 1) AS shares_in_issue"
                         " FROM companies c JOIN market_instruments m ON m.company_id = c.id WHERE c.ticker = %s", (ticker,))
    return {**company, **found}


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


def desks_for(conn: Connection, player_id) -> list[dict]:
    """The banks a client may ask: the computer banks and every open player desk but their own."""
    out = [{"key": f"computer:{c['code']}", "name": c["name"], "kind": "computer", "failed": 0} for c in COMPUTER.values()]
    for d in _rows(conn, "SELECT d.player_id, d.failed, p.display_name FROM floor_desks d JOIN players p ON p.id = d.player_id"
                         " WHERE d.open AND p.build = 'investment_banker' AND d.player_id <> %s ORDER BY p.display_name", (player_id,)):
        out.append({"key": f"player:{d['player_id']}", "name": f"{d['display_name']}'s desk", "kind": "player", "failed": d["failed"]})
    return out


def _computer_quote(conn: Connection, request: dict, share: dict, code: str, now: datetime) -> None:
    """A computer bank's price: the middle of the market, less or plus half its spread, wider for a big deal."""
    desk = COMPUTER[code]
    bid, offer = share["bids"][0]["price"] if share["bids"] else None, share["offers"][0]["price"] if share["offers"] else None
    mid = (bid + offer) // 2 if bid and offer else (share["last_price"] or share["reference_price"])
    value = mid * request["quantity"]
    size = min(value // 1_000_000_000 * data.FLOOR_SIZE_SPREAD_BPS, data.FLOOR_SIZE_SPREAD_MOST_BPS)
    jitter = round(_unit(_seed(conn), "floor-quote", request["id"], code) * 20) - 10
    half = max(desk["spread_bps"] // 2 + size + jitter, 5)
    low, high = share["lowest_today"], share["highest_today"]
    q_bid = max(low, mid * (10_000 - half) // 10_000)
    q_offer = min(high, max(mid * (10_000 + half) // 10_000, q_bid + 1))
    if q_offer <= q_bid:
        return
    shown = now + timedelta(seconds=desk["delay"] + round(_unit(_seed(conn), "floor-delay", request["id"], code) * 4))
    conn.execute("INSERT INTO floor_quotes (request_id, desk, bid, offer, created_at, shown_at, valid_until) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                 (request["id"], f"computer:{code}", q_bid if request["side"] != "buy" else None,
                  q_offer if request["side"] != "sell" else None, now, shown,
                  shown + timedelta(seconds=data.FLOOR_COMPUTER_QUOTE_SECONDS)))


def _open_request(conn: Connection, *, account, player_id, client_name, share: dict, side: str, quantity: int, seconds: int,
                  desks: list[str], now: datetime) -> dict:
    request = _one(conn, "INSERT INTO floor_requests (client_account, client_player, client_name, company_id, side, quantity, created_at, quotes_until)"
                         " VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING *",
                   (account, player_id, client_name, share["id"], side, quantity, now, now + timedelta(seconds=seconds)))
    for desk in desks:
        player = desk.split(":", 1)[1] if desk.startswith("player:") else None
        conn.execute("INSERT INTO floor_request_desks (request_id, desk, desk_player) VALUES (%s, %s, %s)", (request["id"], desk, player))
        if player:
            _ping_player(conn, player)
        else:
            _computer_quote(conn, request, share, desk.split(":", 1)[1], now)
    return request


def ask(conn: Connection, player_id, ticker: str, side: str, quantity: int, seconds: int, desks: list[str], now: datetime) -> dict:
    """A client's request for prices: a share, buy or sell (or a price both ways, not saying which), how many, how long the
    banks have, and which banks (one to five)."""
    from simulation import ledger
    if side not in SIDE_WORDS:
        raise FloorError("Ask to buy, to sell, or for a price both ways.")
    if not isinstance(quantity, int) or isinstance(quantity, bool) or quantity <= 0:
        raise FloorError("Ask for a whole number of shares, above nought.")
    least, most = data.FLOOR_WINDOW_SECONDS
    if not isinstance(seconds, int) or not least <= seconds <= most:
        raise FloorError(f"Give the banks {least} to {most} seconds.")
    chosen = list(dict.fromkeys(desks))
    if not 1 <= len(chosen) <= data.FLOOR_MOST_DESKS:
        raise FloorError(f"Ask one to {data.FLOOR_MOST_DESKS} banks.")
    _market_open(now)
    account = ledger.player_account_id(conn, player_id)
    if account is None:
        raise FloorError("Your account is not open yet.")
    with conn.transaction():
        share = _share(conn, ticker, now)
        if share.get("halted_reason"):
            raise FloorError(f"No trading in this share: {share['halted_reason']}.")
        if quantity * 10_000 > share["shares_in_issue"] * data.FLOOR_MOST_SHARES_BPS:
            raise FloorError(f"One request is at most {data.FLOOR_MOST_SHARES_BPS / 100:g}% of the company's shares.")
        waiting = _one(conn, "SELECT count(*)::int AS n FROM floor_requests WHERE client_account = %s AND status = 'open' AND quotes_until > %s",
                       (account, now))["n"]
        if waiting >= data.FLOOR_MOST_OPEN_REQUESTS:
            raise FloorError(f"You have {waiting} requests waiting. Take or pass one first.")
        allowed = {d["key"] for d in desks_for(conn, player_id)}
        for desk in chosen:
            if desk not in allowed:
                raise FloorError("One of those banks is not taking requests now.")
        request = _open_request(conn, account=account, player_id=player_id, client_name=None, share=share, side=side,
                                quantity=quantity, seconds=seconds, desks=chosen, now=now)
    return {"request_id": request["id"]}


def quote(conn: Connection, player_id, request_id: int, bid: int | None, offer: int | None, valid_seconds: int, now: datetime) -> dict:
    """A banker's prices for a request sent to their desk. A new quote replaces the desk's last one."""
    least, most = data.FLOOR_QUOTE_SECONDS
    if not isinstance(valid_seconds, int) or not least <= valid_seconds <= most:
        raise FloorError(f"A price holds for {least} to {most} seconds.")
    for p in (bid, offer):
        if p is not None and (not isinstance(p, int) or isinstance(p, bool) or p <= 0):
            raise FloorError("A price is a sum above nought.")
    desk = f"player:{player_id}"
    with conn.transaction():
        request = _one(conn, "SELECT r.*, c.ticker FROM floor_requests r JOIN companies c ON c.id = r.company_id WHERE r.id = %s FOR UPDATE", (request_id,))
        if request is None or not _one(conn, "SELECT 1 AS x FROM floor_request_desks WHERE request_id = %s AND desk = %s", (request_id, desk)):
            raise FloorError("That request was not sent to your desk.")
        if request["status"] != "open" or now >= request["quotes_until"]:
            raise FloorError("Too late: the client's countdown has run out.")
        needs = {"buy": ("offer",), "sell": ("bid",), "two_way": ("bid", "offer")}[request["side"]]
        given = {"bid": bid, "offer": offer}
        for word in needs:
            if given[word] is None:
                raise FloorError("The client asked for a price both ways: give a buying and a selling price." if request["side"] == "two_way"
                                 else f"Give the price you would {'sell' if word == 'offer' else 'buy'} at.")
        if bid is not None and offer is not None and bid >= offer:
            raise FloorError("Your buying price must be below your selling price.")
        share = _share(conn, request["ticker"], now)
        for p in (bid, offer):
            if p is not None and not share["lowest_today"] <= p <= share["highest_today"]:
                raise FloorError(f"Today this share can trade only between {_money(share['lowest_today'])} and {_money(share['highest_today'])}.")
        conn.execute("UPDATE floor_quotes SET status = 'replaced' WHERE request_id = %s AND desk = %s AND status = 'live'", (request_id, desk))
        row = _one(conn, "INSERT INTO floor_quotes (request_id, desk, bid, offer, created_at, shown_at, valid_until) VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id",
                   (request_id, desk, bid if "bid" in needs else None, offer if "offer" in needs else None, now, now, now + timedelta(seconds=valid_seconds)))
        if request["client_player"]:
            _ping_player(conn, request["client_player"])
    return {"quote_id": row["id"]}


def _settle(conn: Connection, request: dict, q: dict, client_buys: bool, now: datetime) -> dict:
    """The shares and the money change hands at once, away from the exchange. Refused (and nothing moves) if either side
    cannot: a desk that cannot deliver is marked for it."""
    from simulation import corporate, courts, ledger, newsroom
    from simulation.ledger import Leg
    company = _one(conn, "SELECT id, name, ticker, share_asset FROM companies WHERE id = %s", (request["company_id"],))
    desk_account = _desk_account(conn, q["desk"])
    price = q["offer"] if client_buys else q["bid"]
    if price is None:
        raise FloorError("That bank gave no price on that side.")
    buyer, seller = (request["client_account"], desk_account) if client_buys else (desk_account, request["client_account"])
    if buyer == seller:
        raise FloorError("A desk cannot deal with itself.")
    cost = price * request["quantity"]
    for account in (buyer, seller):
        kind = _one(conn, "SELECT kind FROM ledger_accounts WHERE id = %s", (account,))["kind"]
        if kind in ("player", "empire"):
            newsroom.check_trade(conn, account, company["id"], now)
            courts.check_trade(conn, account, now)
    desk_short = (ledger.balance(conn, desk_account, company["share_asset"]) < request["quantity"]) if client_buys else (ledger.balance(conn, desk_account) < cost)
    if desk_short:
        if q["desk"].startswith("player:"):
            conn.execute("UPDATE floor_desks SET failed = failed + 1 WHERE player_id = %s", (q["desk"].split(":", 1)[1],))
        conn.execute("UPDATE floor_quotes SET status = 'failed' WHERE id = %s", (q["id"],))
        return {"failed": f"{_desk_name(conn, q['desk'])} could not deliver: it has not the {'shares' if client_buys else 'cash'}. Its price is withdrawn; take another."}
    if client_buys and ledger.balance(conn, buyer) < cost:
        raise FloorError(f"The deal costs {_money(cost)}. You have not that much cash.")
    if not client_buys and ledger.balance(conn, seller, company["share_asset"]) < request["quantity"]:
        raise FloorError("You do not hold that many free shares (shares held for orders on the exchange are not free).")
    tx = ledger.post(conn, kind="floor_trade", memo=f"{request['quantity']:,} {company['name']} shares at {_money(price)} on the Floor",
                     reference=f"floor:{request['id']}",
                     legs=[Leg(seller, -request["quantity"], company["share_asset"]), Leg(buyer, request["quantity"], company["share_asset"]),
                           Leg(buyer, -cost), Leg(seller, cost)])
    after = corporate._after_trade(conn)
    for account, shares in ((seller, -request["quantity"]), (buyer, request["quantity"])):
        conn.execute("INSERT INTO holding_events (account_id, company_id, kind, shares, amount, after_trade_id) VALUES (%s, %s, 'floor', %s, %s, %s)",
                     (account, company["id"], shares, cost, after))
    trade = _one(conn, "INSERT INTO floor_trades (request_id, quote_id, company_id, buyer_account, seller_account, price, quantity, desk, at)"
                       " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
                 (request["id"], q["id"], company["id"], buyer, seller, price, request["quantity"], q["desk"], now))
    conn.execute("UPDATE floor_quotes SET status = CASE WHEN id = %s THEN 'taken' ELSE 'lost' END WHERE request_id = %s AND status = 'live'",
                 (q["id"], request["id"]))
    conn.execute("UPDATE floor_requests SET status = 'done', done_at = %s WHERE id = %s", (now, request["id"]))
    for d in _rows(conn, "SELECT desk_player FROM floor_request_desks WHERE request_id = %s AND desk_player IS NOT NULL", (request["id"],)):
        _ping_player(conn, d["desk_player"])
    return {"trade_id": trade["id"], "price": price, "quantity": request["quantity"], "cost": cost, "ticker": company["ticker"],
            "bought": client_buys, "desk": _desk_name(conn, q["desk"]), "ledger": tx}


def take(conn: Connection, player_id, request_id: int, quote_id: int, side: str, now: datetime) -> dict:
    """The client takes a bank's price: buys at its selling price, or sells at its buying price."""
    from simulation import ledger
    if side not in ("buy", "sell"):
        raise FloorError("Take the price to buy or to sell.")
    account = ledger.player_account_id(conn, player_id)
    with conn.transaction():
        request = _one(conn, "SELECT * FROM floor_requests WHERE id = %s AND client_account = %s FOR UPDATE", (request_id, account))
        if request is None:
            raise FloorError("There is no such request of yours.")
        if request["status"] != "open":
            raise FloorError("That request is closed.")
        if request["side"] != "two_way" and request["side"] != side:
            raise FloorError(f"You asked to {request['side']}.")
        q = _one(conn, "SELECT * FROM floor_quotes WHERE id = %s AND request_id = %s FOR UPDATE", (quote_id, request_id))
        if q is None or q["status"] != "live" or q["shown_at"] > now:
            raise FloorError("That price is not on offer.")
        if now >= q["valid_until"]:
            raise FloorError("Too late: that price has expired.")
        done = _settle(conn, request, q, side == "buy", now)
    if "failed" in done:
        raise FloorError(done["failed"])
    return done


def pass_on(conn: Connection, player_id, request_id: int, now: datetime) -> dict:
    from simulation import ledger
    account = ledger.player_account_id(conn, player_id)
    with conn.transaction():
        n = conn.execute("UPDATE floor_requests SET status = 'passed', done_at = %s WHERE id = %s AND client_account = %s AND status = 'open'",
                         (now, request_id, account)).rowcount
        if not n:
            raise FloorError("There is no such open request of yours.")
        conn.execute("UPDATE floor_quotes SET status = 'lost' WHERE request_id = %s AND status = 'live'", (request_id,))
        for d in _rows(conn, "SELECT desk_player FROM floor_request_desks WHERE request_id = %s AND desk_player IS NOT NULL", (request_id,)):
            _ping_player(conn, d["desk_player"])
    return {"passed": request_id}


def _ends(conn: Connection, request: dict) -> datetime:
    """A request is over when the banks' countdown and every price it drew have run out."""
    last = _one(conn, "SELECT max(valid_until) AS t FROM floor_quotes WHERE request_id = %s AND status = 'live'", (request["id"],))["t"]
    return max(request["quotes_until"], last) if last else request["quotes_until"]


# ---------------------------------------------------------------------------
# The computer clients, and tidying up
# ---------------------------------------------------------------------------

def _computer_decides(conn: Connection, request: dict, now: datetime) -> None:
    """At its countdown's end a computer client takes the best price that was live then, if it beats the exchange after
    the exchange's fee; otherwise it passes."""
    share = _one(conn, "SELECT ticker FROM companies WHERE id = %s", (request["company_id"],))
    market = _share(conn, share["ticker"], now)
    at = request["quotes_until"]
    live = _rows(conn, "SELECT * FROM floor_quotes WHERE request_id = %s AND status = 'live' AND shown_at <= %s AND valid_until > %s",
                 (request["id"], at, at))
    fee = data.EXCHANGE_FEE_BPS + data.STAMP_DUTY_BPS
    client_buys = request["side"] == "buy"
    if client_buys:
        best = min((q for q in live if q["offer"]), key=lambda q: (q["offer"], q["shown_at"]), default=None)
        beat = market["offers"][0]["price"] * (10_000 + fee) // 10_000 if market["offers"] else None
        good = best is not None and (beat is None or best["offer"] <= beat)
    else:
        best = max((q for q in live if q["bid"]), key=lambda q: (q["bid"], -q["shown_at"].timestamp()), default=None)
        beat = market["bids"][0]["price"] * (10_000 - fee) // 10_000 if market["bids"] else None
        good = best is not None and (beat is None or best["bid"] >= beat)
    with conn.transaction():
        if good:
            from simulation import ledger
            try:
                with conn.transaction():            # a deal that cannot be done leaves nothing behind
                    done = _settle(conn, request, best, client_buys, now)
            except (FloorError, exchange.ExchangeError, ledger.LedgerError):
                done = {"failed": True}             # the client's own side failed: it simply passes
            if "failed" not in done:
                return
        conn.execute("UPDATE floor_requests SET status = 'passed', done_at = %s WHERE id = %s AND status = 'open'", (now, request["id"]))
        conn.execute("UPDATE floor_quotes SET status = 'lost' WHERE request_id = %s AND status = 'live'", (request["id"],))
        for d in _rows(conn, "SELECT desk_player FROM floor_request_desks WHERE request_id = %s AND desk_player IS NOT NULL", (request["id"],)):
            _ping_player(conn, d["desk_player"])


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
    made = 0
    for d in open_desks:
        if _unit(seed, "floor-call", slot, d["player_id"]) * data.FLOOR_CLIENT_CALL_CHANCE >= 1:
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
            _open_request(conn, account=account, player_id=None, client_name=name, share=share, side=side, quantity=int(quantity),
                          seconds=seconds, desks=[f"player:{d['player_id']}"] + [f"computer:{c}" for c in rivals], now=now)
        made += 1
    return made


def tick(conn: Connection, now: datetime) -> None:
    """Every few seconds of the server's loop: computer clients decide and call; requests whose time is up are closed."""
    if not _one(conn, "SELECT to_regclass('floor_requests') IS NOT NULL AS ok")["ok"]:
        return
    for r in _rows(conn, "SELECT * FROM floor_requests WHERE status = 'open' AND client_player IS NULL AND quotes_until <= %s ORDER BY id", (now,)):
        _computer_decides(conn, r, now)
    for r in _rows(conn, "SELECT * FROM floor_requests WHERE status = 'open' AND client_player IS NOT NULL AND quotes_until <= %s ORDER BY id", (now,)):
        if _ends(conn, r) <= now:
            with conn.transaction():
                conn.execute("UPDATE floor_requests SET status = 'expired', done_at = %s WHERE id = %s AND status = 'open'", (now, r["id"]))
                conn.execute("UPDATE floor_quotes SET status = 'lost' WHERE request_id = %s AND status = 'live'", (r["id"],))
    if clock.market_state(now).value == "open":
        _computer_calls(conn, now)


# ---------------------------------------------------------------------------
# What each side sees
# ---------------------------------------------------------------------------

def _name_of_client(r: dict) -> str:
    return r.get("client_display") or r.get("client_name") or "A client"


def requests_view(conn: Connection, player_id, now: datetime) -> dict:
    """A client sees their own requests with every price sent to them; a banker sees the requests sent to their desk with
    only their own price (never another bank's), and the market and their own holdings to price from."""
    from simulation import ledger
    account = ledger.player_account_id(conn, player_id)
    desk = _one(conn, "SELECT open, failed FROM floor_desks WHERE player_id = %s", (player_id,))
    mine = []
    for r in _rows(conn, "SELECT r.*, c.ticker, c.name FROM floor_requests r JOIN companies c ON c.id = r.company_id"
                         " WHERE r.client_account = %s ORDER BY r.status = 'open' DESC, r.id DESC LIMIT 12", (account,)):
        quotes = [{"id": q["id"], "desk": _desk_name(conn, q["desk"]), "kind": q["desk"].split(":", 1)[0],
                   "failed": (_one(conn, "SELECT failed FROM floor_desks WHERE player_id = %s", (q["desk"].split(":", 1)[1],)) or {"failed": 0})["failed"]
                   if q["desk"].startswith("player:") else 0,
                   "bid": q["bid"], "offer": q["offer"], "valid_until": q["valid_until"], "status": q["status"]}
                  for q in _rows(conn, "SELECT * FROM floor_quotes WHERE request_id = %s AND shown_at <= %s AND status <> 'replaced' ORDER BY id",
                                 (r["id"], now))]
        asked = [_desk_name(conn, d["desk"]) for d in _rows(conn, "SELECT desk FROM floor_request_desks WHERE request_id = %s ORDER BY desk", (r["id"],))]
        trade = _one(conn, "SELECT price, quantity, desk FROM floor_trades WHERE request_id = %s", (r["id"],))
        mine.append({"id": r["id"], "ticker": r["ticker"], "name": r["name"], "side": r["side"], "quantity": r["quantity"],
                     "created_at": r["created_at"], "quotes_until": r["quotes_until"], "status": r["status"], "asked": asked,
                     "quotes": quotes, "deal": {"price": trade["price"], "quantity": trade["quantity"], "desk": _desk_name(conn, trade["desk"])} if trade else None})
    incoming = []
    if desk is not None:
        holdings = {}
        for r in _rows(conn, "SELECT r.*, c.ticker, c.name, c.share_asset, p.display_name AS client_display FROM floor_requests r"
                             " JOIN floor_request_desks k ON k.request_id = r.id AND k.desk_player = %s"
                             " JOIN companies c ON c.id = r.company_id LEFT JOIN players p ON p.id = r.client_player"
                             " ORDER BY r.status = 'open' DESC, r.id DESC LIMIT 15", (player_id,)):
            own = _one(conn, "SELECT bid, offer, valid_until, status FROM floor_quotes WHERE request_id = %s AND desk = %s AND status <> 'replaced'"
                             " ORDER BY id DESC LIMIT 1", (r["id"], f"player:{player_id}"))
            trade = _one(conn, "SELECT desk, price FROM floor_trades WHERE request_id = %s", (r["id"],))
            if r["ticker"] not in holdings and account:
                holdings[r["ticker"]] = ledger.balance(conn, account, r["share_asset"])
            market = exchange.quote(conn, r["ticker"], now, depth=1) if r["status"] == "open" else None
            incoming.append({
                "id": r["id"], "client": _name_of_client(r), "computer_client": r["client_player"] is None,
                "ticker": r["ticker"], "name": r["name"], "side": r["side"], "quantity": r["quantity"],
                "created_at": r["created_at"], "quotes_until": r["quotes_until"], "status": r["status"],
                "your_quote": own,
                "outcome": None if r["status"] == "open" else ("won" if trade and trade["desk"] == f"player:{player_id}" else
                                                               "traded away" if trade else "passed" if r["status"] == "passed" else "no deal"),
                "you_hold": holdings.get(r["ticker"], 0),
                "market": {"best_bid": market["bids"][0]["price"] if market and market["bids"] else None,
                           "best_offer": market["offers"][0]["price"] if market and market["offers"] else None,
                           "last": market["last_price"] if market else None,
                           "reference": market["reference_price"] if market else None,
                           "low": market["lowest_today"] if market else None, "high": market["highest_today"] if market else None},
            })
    deals = _rows(conn, "SELECT t.id, t.at, c.ticker, t.price, t.quantity, t.desk, t.buyer_account = %s AS bought, r.client_player, r.client_name,"
                        " p.display_name AS client_display FROM floor_trades t JOIN companies c ON c.id = t.company_id"
                        " JOIN floor_requests r ON r.id = t.request_id LEFT JOIN players p ON p.id = r.client_player"
                        " WHERE t.buyer_account = %s OR t.seller_account = %s ORDER BY t.id DESC LIMIT 15", (account, account, account))
    return {
        "now": now, "market_state": clock.market_state(now).value,
        "is_banker": _is_banker(conn, player_id), "desk_open": bool(desk and desk["open"]), "desk_failed": desk["failed"] if desk else 0,
        "desks": desks_for(conn, player_id),
        "limits": {"window": list(data.FLOOR_WINDOW_SECONDS), "quote": list(data.FLOOR_QUOTE_SECONDS), "most_desks": data.FLOOR_MOST_DESKS},
        "mine": mine, "incoming": incoming,
        "deals": [{"id": t["id"], "at": t["at"], "ticker": t["ticker"], "price": t["price"], "quantity": t["quantity"],
                   "bought": t["bought"], "with": _desk_name(conn, t["desk"]) if str(t["client_player"]) == str(player_id) else _name_of_client(t),
                   "as": "client" if str(t["client_player"]) == str(player_id) else "bank"} for t in deals],
    }
