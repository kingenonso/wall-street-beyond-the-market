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
from psycopg.errors import DeadlockDetected, UniqueViolation
from pydantic import Field

from server import limits
from server.db import get_connection
from server.main import _exchange_time, _trading_account, app, current_player
from server.schemas import Request
from simulation import exchange, floor

MONEY = {"realised", "unrealised", "total", "dividends", "fees", "exposure", "cash", "held_for_orders", "value", "price",
         "average_price", "gain", "reference_price", "last_price", "lowest_today", "highest_today", "best_bid", "best_offer",
         "start_price", "minimum", "fair", "your_limit", "bid", "offer", "last", "low", "high", "cost", "reference"}


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



# ---------------------------------------------------------------------------
# Slice 2: price requests
# ---------------------------------------------------------------------------

ID = Field(ge=1, le=9_000_000_000_000_000_000, strict=True)
KOBO = Field(default=None, ge=1, le=100_000_000_000_000, strict=True)


class DeskRequest(Request):
    open: bool = Field(strict=True)


class AskRequest(Request):
    ticker: str = Field(pattern="^[A-Z]{3}$")
    side: str = Field(pattern="^(buy|sell|two_way)$")
    quantity: int = Field(ge=1, le=10_000_000_000, strict=True)
    seconds: int = Field(ge=1, le=600, strict=True)
    desks: list[str] = Field(min_length=1, max_length=10)


class QuoteRequest(Request):
    request_id: int = ID
    bid_kobo: int | None = KOBO
    offer_kobo: int | None = KOBO
    valid_seconds: int = Field(ge=1, le=600, strict=True)


class TakeRequest(Request):
    request_id: int = ID
    quote_id: int = ID
    side: str = Field(pattern="^(buy|sell)$")


class PassRequest(Request):
    request_id: int = ID


def _act(conn: Connection, player: dict, action, bucket: str = "floor", attempts: int = 40) -> dict:
    limits.allow(bucket, str(player["id"]), attempts=attempts, per_seconds=60)
    try:
        done = action(_exchange_time(conn))
    except (floor.FloorError, exchange.ExchangeError) as refused:
        raise HTTPException(status.HTTP_409_CONFLICT, str(refused)) from None
    except (DeadlockDetected, UniqueViolation):
        raise HTTPException(status.HTTP_409_CONFLICT, "Somebody else changed this at the same moment. Please try again.") from None
    page = floor.requests_view(conn, player["id"], _exchange_time(conn))
    page["result"] = done
    return _wire(page)


@app.get("/api/floor/requests")
def the_floor_requests(player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _wire(floor.requests_view(conn, player["id"], _exchange_time(conn)))


@app.post("/api/floor/desk")
def open_or_close_the_desk(body: DeskRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: floor.set_desk(conn, player["id"], body.open, now), "floor-desk", 20)


@app.post("/api/floor/ask")
def ask_for_prices(body: AskRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: floor.ask(conn, player["id"], body.ticker, body.side, body.quantity, body.seconds, body.desks, now),
                "floor-ask", 12)


@app.post("/api/floor/quote")
def quote_a_price(body: QuoteRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: floor.quote(conn, player["id"], body.request_id, body.bid_kobo, body.offer_kobo, body.valid_seconds, now))


@app.post("/api/floor/take")
def take_a_price(body: TakeRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: floor.take(conn, player["id"], body.request_id, body.quote_id, body.side, now))


@app.post("/api/floor/pass")
def pass_on_a_request(body: PassRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: floor.pass_on(conn, player["id"], body.request_id, now))
