"""The Floor on the website (owner, 16 November 2026): the multiplayer home. This slice serves the trading floor screen:
the profit-and-loss bar, positions, the blotter and the intraday chart, all of the player's own trading account. Nobody
else's account is ever read here.
"""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from fastapi import Depends, HTTPException, Query, status
from fastapi import Path as FastPath
from psycopg import Connection

from server.db import get_connection
from server.main import _exchange_time, _trading_account, app, current_player
from simulation import floor

MONEY = {"realised", "unrealised", "total", "dividends", "fees", "exposure", "cash", "held_for_orders", "value", "price",
         "average_price", "gain", "reference_price", "last_price", "lowest_today", "highest_today", "best_bid", "best_offer",
         "start_price", "minimum", "fair", "your_limit"}


def _wire(value, key: str | None = None):
    if isinstance(value, dict):
        return {k: _wire(v, k) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_wire(v, key) for v in value]
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if key in MONEY and isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    return value


@app.get("/api/floor")
def the_floor(player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _wire(floor.screen(conn, _trading_account(conn, player), _exchange_time(conn)))


@app.get("/api/floor/chart/{ticker}")
def the_floor_chart(ticker: str = FastPath(pattern="^[A-Z]{3}$"), minutes: int = Query(default=5, ge=1, le=60),
                    _: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    found = floor.intraday(conn, ticker, _exchange_time(conn), minutes)
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "There is no share with that code on the exchange.")
    return _wire(found)


@app.get("/api/floor/auctions")
def the_auction_house(player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _wire({"now": _exchange_time(conn), "auctions": floor.auction_house(conn, _trading_account(conn, player), _exchange_time(conn))})
