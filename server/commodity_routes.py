"""The commodities page on the website (Stage 12): Markets → Commodities.

A player: the four goods with the dealers' prices, the space they lease to keep goods in, what they hold, their trades
and what happened to their goods at the close, and, for someone at a firm, the firm's commodities desk. They may buy
and sell goods (into and out of space already leased), take a lease, give one up, and insure one.

Every price and amount is the server's. The page names a good and a number of units or spaces; never a price.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi import Path as FastPath
from psycopg import Connection
from psycopg.errors import DeadlockDetected, UniqueViolation
from psycopg.rows import dict_row
from pydantic import Field

from server import limits
from server.db import get_connection
from server.main import _exchange_time, app, current_player
from server.schemas import Request
from simulation import careers, commodities, commoditydesk, ledger

Count = Annotated[int, Field(gt=0, le=10_000_000_000, strict=True)]
GOOD = Field(pattern="^(GOLD|OIL|FARM|MATERIALS)$")


def _wire(value):
    if isinstance(value, dict):
        return {k: _wire(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_wire(v) for v in value]
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return int(value)
    return value


def _rows(conn: Connection, sql: str, params=()) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


class TradeRequest(Request):
    good: str = GOOD
    units: Count


class LeaseRequest(Request):
    good: str = GOOD
    spaces: Count
    insured: bool = False


class InsuredRequest(Request):
    insured: bool


def _account(conn: Connection, player: dict):
    return ledger.player_account_id(conn, player["id"])


def _page(conn: Connection, player: dict, result=None) -> dict:
    now = _exchange_time(conn)
    account = _account(conn, player)
    period = careers.world_now(conn, now)["period"]
    prices = []
    for g in commodities.goods(conn):
        q = commodities.quote(conn, g["code"], now)
        before = _rows(conn, "SELECT spot FROM commodity_prices WHERE good = %s AND period < %s ORDER BY period DESC LIMIT 1",
                       (g["code"], period))
        prices.append({"period": period, "good": g["code"], **q, "previous": before[0]["spot"] if before else None})
    desk = commoditydesk.view(conn, player["id"], now)
    quotes = [{**q, "company": {"ticker": q["ticker"], "name": q["company"]}} for q in desk.get("quotes", [])]
    page = {
        "goods": commodities.goods(conn), "prices": prices,
        "leases": commodities.leases(conn, account, open_only=False),
        "holdings": commodities.holdings(conn, account),
        "trades": _rows(conn, "SELECT * FROM commodity_trades WHERE account = %s ORDER BY id DESC LIMIT 40", (account,)),
        "events": _rows(conn, "SELECT * FROM commodity_events WHERE account = %s ORDER BY id DESC LIMIT 40", (account,)),
        "desk": desk.get("desk"), "quotes": quotes, "hedges": desk.get("hedges", []),
    }
    if result is not None:
        page["result"] = result
    return _wire(page)


def _act(conn: Connection, player: dict, action):
    limits.allow("commodities", str(player["id"]), attempts=30, per_seconds=60)
    try:
        now = _exchange_time(conn)
        with conn.transaction():
            careers.books_open(conn, now)
            return action(now, careers.world_now(conn, now)["period"])
    except (commodities.CommodityError, careers.CareerError) as refused:
        raise HTTPException(status.HTTP_409_CONFLICT, str(refused)) from None
    except (DeadlockDetected, UniqueViolation):
        raise HTTPException(status.HTTP_409_CONFLICT, "Somebody else changed this at the same moment. Please try again.") from None


@app.get("/api/commodities")
def commodities_page(player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _page(conn, player)


@app.post("/api/commodities/buy")
def commodities_buy(body: TradeRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    done = _act(conn, player, lambda now, period: commodities.buy(conn, _account(conn, player), body.good, body.units,
                                                                  period, now, player_id=player["id"]))
    return _page(conn, player, done)


@app.post("/api/commodities/sell")
def commodities_sell(body: TradeRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    done = _act(conn, player, lambda now, period: commodities.sell(conn, _account(conn, player), body.good, body.units,
                                                                   period, now, player_id=player["id"]))
    return _page(conn, player, done)


@app.post("/api/commodities/lease")
def commodities_lease(body: LeaseRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    done = _act(conn, player, lambda now, period: commodities.open_lease(conn, _account(conn, player), body.good,
                                                                         body.spaces, body.insured, period, now))
    return _page(conn, player, done)


@app.delete("/api/commodities/lease/{storage_id}")
def commodities_give_up(storage_id: int = FastPath(ge=1, le=9_000_000_000_000_000_000),
                        player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    done = _act(conn, player, lambda now, period: commodities.close_lease(conn, _account(conn, player), storage_id, now))
    return _page(conn, player, done)


@app.patch("/api/commodities/lease/{storage_id}/insured")
def commodities_insure(body: InsuredRequest, storage_id: int = FastPath(ge=1, le=9_000_000_000_000_000_000),
                       player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    done = _act(conn, player, lambda now, period: commodities.set_insured(conn, _account(conn, player), storage_id,
                                                                          body.insured))
    return _page(conn, player, done)
