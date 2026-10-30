"""Index funds and ETFs on the website (the talent and funds stage, Part 3).

Anybody: the indexes (their rules, members, history and changes), the ETFs (price, value through the day, the gap between
them, basket, how closely they copy), buying and selling units, following one. Approved dealers (an empire's head): making
and unmaking units. An Asset Manager of Level 20: launching an ETF, publishing an index of their own.

Never sent: anybody else's orders (only the waiting units at each price), anybody's holdings, the market makers' stock of
units, or the empires approved as dealers.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from fastapi import Depends, HTTPException, Query, status
from fastapi import Path as FastPath
from psycopg import Connection
from psycopg.errors import CheckViolation, DeadlockDetected, UniqueViolation
from pydantic import Field

from server import limits
from server.db import get_connection
from server.main import _exchange_time, app, current_player
from server.schemas import Request
from simulation import etfs, indexes
from simulation.money import naira

KOBO = {"price", "nav", "size", "value", "cash", "bid", "ask", "low", "high", "limit_price", "least_worth", "registration", "seed", "close",
        "paid", "fee", "fees_this_quarter", "level", "worth", "unit_price", "least_in"}
CODE = "^[A-Z0-9]{2,10}$"


def _wire(value, key: str | None = None):
    if isinstance(value, dict):
        return {k: _wire(v, k) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_wire(v, key) for v in value]
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if key in KOBO and isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    return value


def _act(conn: Connection, player: dict, action, attempts: int = 40):
    limits.allow("etfs", str(player["id"]), attempts=attempts, per_seconds=60)
    try:
        with conn.transaction():
            return _wire({"result": action(_exchange_time(conn))})
    except (etfs.EtfError, indexes.IndexError_) as refused:
        raise HTTPException(status.HTTP_409_CONFLICT, str(refused)) from None
    except (DeadlockDetected, UniqueViolation, CheckViolation):
        raise HTTPException(status.HTTP_409_CONFLICT, "Somebody else changed this at the same moment. Please try again.") from None


def _ready(conn: Connection) -> None:
    if not etfs.ready(conn) or not indexes.ready(conn):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Indexes and ETFs are not open in this world yet.")


@app.get("/api/etfs")
def etfs_page(player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    _ready(conn)
    return _wire(etfs.listing(conn, player["id"], _exchange_time(conn)))


@app.get("/api/etfs/alerts")
def etf_alerts(after: int | None = Query(default=None, ge=0), player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    if not etfs.ready(conn):
        return {"mark": after or 0, "alerts": []}
    return _wire(etfs.alerts_for(conn, player["id"], after, _exchange_time(conn)))


@app.get("/api/etfs/{code}")
def etf_factsheet(code: str = FastPath(pattern="^[A-Z]{3,5}$"), player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    _ready(conn)
    try:
        return _wire(etfs.factsheet(conn, code, player["id"], _exchange_time(conn)))
    except etfs.EtfError as missing:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(missing)) from None


@app.get("/api/indexes/{code}")
def index_page(code: str = FastPath(pattern=CODE), _: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    _ready(conn)
    try:
        return _wire(indexes.page(conn, code, _exchange_time(conn)))
    except indexes.IndexError_ as missing:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(missing)) from None


class OrderRequest(Request):
    side: str = Field(pattern="^(buy|sell)$")
    quantity: int = Field(gt=0, le=10**10, strict=True)
    limit_price_kobo: int = Field(gt=0, le=10**10, strict=True)
    for_empire: bool = False


class UnitsRequest(Request):
    units: int = Field(gt=0, le=10**10, strict=True)
    how: str = Field(pattern="^(basket|cash)$")


class FollowRequest(Request):
    on: bool


class LaunchRequest(Request):
    code: str = Field(pattern="^[A-Z]{3,5}$")
    name: str = Field(min_length=3, max_length=60)
    index_code: str = Field(pattern=CODE)
    method: str = Field(pattern="^(full|sample)$")
    fee_bps: int = Field(ge=0, le=100, strict=True)
    seed_naira: int = Field(gt=0, le=100_000_000_000, strict=True)
    words: str = Field(default="", max_length=400)


class FeeRequest(Request):
    fee_bps: int = Field(ge=0, le=100, strict=True)


class IndexRequest(Request):
    code: str = Field(pattern="^[A-Z0-9]{3,8}$")
    name: str = Field(min_length=3, max_length=60)
    tickers: list[str] = Field(min_length=5, max_length=30)
    weighting: str = Field(pattern="^(value|equal)$")


class IndexChange(Request):
    tickers: list[str] = Field(min_length=5, max_length=30)


@app.post("/api/etfs/{code}/orders")
def etf_order(body: OrderRequest, code: str = FastPath(pattern="^[A-Z]{3,5}$"), player: dict = Depends(current_player),
              conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: etfs.place_order(conn, player["id"], code, side=body.side, quantity=body.quantity,
                                                           limit_price=body.limit_price_kobo, now=now, for_empire=body.for_empire))


@app.post("/api/etfs/orders/{order_id}/cancel")
def etf_cancel(order_id: int = FastPath(ge=1), player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: etfs.cancel_order(conn, player["id"], order_id, now))


@app.post("/api/etfs/{code}/create")
def etf_create(body: UnitsRequest, code: str = FastPath(pattern="^[A-Z]{3,5}$"), player: dict = Depends(current_player),
               conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: etfs.create(conn, player["id"], code, body.units, body.how, now))


@app.post("/api/etfs/{code}/redeem")
def etf_redeem(body: UnitsRequest, code: str = FastPath(pattern="^[A-Z]{3,5}$"), player: dict = Depends(current_player),
               conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: etfs.redeem(conn, player["id"], code, body.units, body.how, now))


@app.post("/api/etfs/{code}/follow")
def etf_follow(body: FollowRequest, code: str = FastPath(pattern="^[A-Z]{3,5}$"), player: dict = Depends(current_player),
               conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: etfs.follow(conn, player["id"], code, body.on, now))


@app.post("/api/etfs/dealer")
def etf_dealer(player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: etfs.apply_dealer(conn, player["id"], now), attempts=5)


@app.post("/api/etfs/warning")
def etf_warning(player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: etfs.accept_warning(conn, player["id"], now))


@app.post("/api/etfs/launch")
def etf_launch(body: LaunchRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: etfs.launch(conn, player["id"], code=body.code, name=body.name, index_code=body.index_code,
                                                      method=body.method, fee_bps=body.fee_bps, seed=naira(body.seed_naira), now=now,
                                                      words=body.words), attempts=5)


@app.post("/api/etfs/manage/fee")
def etf_fee(body: FeeRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: etfs.lower_fee(conn, player["id"], body.fee_bps, now))


@app.post("/api/etfs/manage/close")
def etf_close(player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: etfs.close(conn, player["id"], now))


@app.post("/api/indexes")
def index_create(body: IndexRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: indexes.create_custom(conn, player["id"], code=body.code, name=body.name, tickers=body.tickers,
                                                                weighting=body.weighting, now=now), attempts=5)


@app.post("/api/indexes/{code}/change")
def index_change(body: IndexChange, code: str = FastPath(pattern=CODE), player: dict = Depends(current_player),
                 conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: indexes.change_custom(conn, player["id"], code, body.tickers, now), attempts=5)
