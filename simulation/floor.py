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
