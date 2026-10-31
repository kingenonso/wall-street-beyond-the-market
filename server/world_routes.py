"""Foreign markets on the website (the talent and funds stage, Part 4b).

Anybody: the three exchanges abroad (open or closed, their hours in Lagos time, their indexes), every company listed there
with its price, results and dividends, the economies abroad and their central banks' rates, the Nigerian arms of foreign
companies (what their parents hold, what waits for dollars, a parent leaving). A player (or an empire's head, Investment
Banker or Asset Manager): buying and selling foreign shares with dollars, pounds or euros. An empire's head: buying part of
a leaving parent's stake.

Never sent: each price's secret path, the economies' secret swings, the central banks' next moves, a parent's decision
before it is announced, anybody else's holdings or trades.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi import Path as FastPath
from psycopg import Connection
from psycopg.errors import CheckViolation, DeadlockDetected, UniqueViolation
from pydantic import Field

from server import limits
from server.db import get_connection
from server.main import _exchange_time, app, current_player
from server.schemas import Request
from simulation import world

# Money in kobo, and foreign money in cents: sent as text, so no figure is ever rounded on the way.
MONEY = {"value", "value_naira", "cost", "cost_naira", "share_gain_naira", "currency_gain_naira", "worth", "trapped", "sent_last", "asking",
         "cap", "amount", "USD", "GBP", "EUR", "shares", "most_deal_usd", "level", "close"}


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
    if key in MONEY and isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    return value


def _act(conn: Connection, player: dict, action, attempts: int = 40):
    limits.allow("world", str(player["id"]), attempts=attempts, per_seconds=60)
    try:
        with conn.transaction():
            return _wire({"result": action(_exchange_time(conn))})
    except world.WorldError as refused:
        raise HTTPException(status.HTTP_409_CONFLICT, str(refused)) from None
    except (DeadlockDetected, UniqueViolation, CheckViolation):
        raise HTTPException(status.HTTP_409_CONFLICT, "Somebody else changed this at the same moment. Please try again.") from None


def _ready(conn: Connection) -> None:
    if not world.ready(conn):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "The markets abroad are not open in this world yet.")


class DealRequest(Request):
    side: str = Field(pattern="^(buy|sell)$")
    shares: int = Field(gt=0, le=10**9)
    for_empire: bool = False


class StakeRequest(Request):
    shares: int = Field(gt=0, le=10**12)


@app.get("/api/world")
def world_page(player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    _ready(conn)
    return _wire(world.page(conn, player["id"], _exchange_time(conn)))


@app.get("/api/world/economies")
def world_economies(_: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    if not world.ready(conn):
        return {"open": False}
    return _wire(world.economies_view(conn))


@app.get("/api/world/companies/{ticker}")
def world_company(ticker: str = FastPath(pattern="^[A-Za-z]{4}$"), _: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    _ready(conn)
    try:
        return _wire(world.company_page(conn, ticker, _exchange_time(conn)))
    except world.WorldError as refused:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(refused)) from None


@app.get("/api/world/arms/{ticker}")
def world_arm(ticker: str = FastPath(pattern="^[A-Za-z]{3}$"), _: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    if not world.ready(conn):
        return {"arm": None}
    return _wire({"arm": world.arm_for(conn, ticker, _exchange_time(conn))})


@app.post("/api/world/companies/{ticker}/deal")
def world_deal(body: DealRequest, ticker: str = FastPath(pattern="^[A-Za-z]{4}$"), player: dict = Depends(current_player),
               conn: Connection = Depends(get_connection)):
    _ready(conn)
    return _act(conn, player, lambda now: world.deal(conn, player["id"], ticker, body.side, body.shares, now, for_empire=body.for_empire))


@app.post("/api/world/arms/{ticker}/stake")
def world_stake(body: StakeRequest, ticker: str = FastPath(pattern="^[A-Za-z]{3}$"), player: dict = Depends(current_player),
                conn: Connection = Depends(get_connection)):
    _ready(conn)
    return _act(conn, player, lambda now: world.buy_stake(conn, player["id"], ticker, body.shares, now), attempts=10)
