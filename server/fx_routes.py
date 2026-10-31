"""The currency desk on the website (the talent and funds stage, Part 4a).

Anybody: the two naira rates and the gap between them, the Central Bank's reserves and its record, the street's prices for
dollars, pounds and euros, the bureaux de change and money-transfer companies open, the Eurobonds. A player (or an empire's
head or Investment Banker): buying and selling on the street or at a bureau, asking the official window for dollars, selling
dollars back to it, buying and selling Eurobonds. An empire's head: running a bureau de change or a money-transfer company.

Never sent: the Central Bank's next move, the street's secret daily swing, anybody else's balances, requests or trades, a
bureau's stock of money (except to its own empire's head).
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from fastapi import Depends, HTTPException, Query, status
from psycopg import Connection
from psycopg.errors import CheckViolation, DeadlockDetected, UniqueViolation
from pydantic import Field

from server import limits
from server.db import get_connection
from server.main import _exchange_time, app, current_player
from server.schemas import Request
from simulation import fx

# Money in kobo, and foreign money in cents: sent as text, so no figure is ever rounded on the way.
MONEY = {"naira", "held", "rate", "official", "street", "mid", "buy", "sell", "fee", "cost", "backlog", "worth", "market", "bdc", "bdc_capital",
         "remitter", "amount", "filled", "reserves", "sold", "kept", "window_limit", "window_used", "dollars", "face", "available", "report",
         "USD", "GBP", "EUR", "price", "remitted"}


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
    limits.allow("fx", str(player["id"]), attempts=attempts, per_seconds=60)
    try:
        with conn.transaction():
            return _wire({"result": action(_exchange_time(conn))})
    except fx.FxError as refused:
        raise HTTPException(status.HTTP_409_CONFLICT, str(refused)) from None
    except (DeadlockDetected, UniqueViolation, CheckViolation):
        raise HTTPException(status.HTTP_409_CONFLICT, "Somebody else changed this at the same moment. Please try again.") from None


def _ready(conn: Connection) -> None:
    if not fx.ready(conn):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "The currency desk is not open in this world yet.")


class DealRequest(Request):
    side: str = Field(pattern="^(buy|sell)$")
    currency: str = Field(default="USD", pattern="^(USD|GBP|EUR)$")
    amount: int = Field(gt=0, le=10**12)            # cents
    for_empire: bool = False


class WindowRequest(Request):
    amount: int = Field(gt=0, le=10**12)
    for_empire: bool = False


class EmpireOnly(Request):
    for_empire: bool = False


class BdcRequest(Request):
    name: str | None = Field(default=None, max_length=80)
    buy_bps: int = Field(ge=0, le=1000)
    sell_bps: int = Field(ge=0, le=1000)


class RemitterRequest(Request):
    name: str | None = Field(default=None, max_length=80)
    fee_bps: int = Field(ge=0, le=1500)
    days: int = Field(ge=0, le=5)


class BondRequest(Request):
    side: str = Field(pattern="^(buy|sell)$")
    units: int = Field(gt=0, le=1_000_000)
    for_empire: bool = False


@app.get("/api/fx")
def fx_page(player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    _ready(conn)
    return _wire(fx.page(conn, player["id"], _exchange_time(conn)))


@app.get("/api/fx/alerts")
def fx_alerts(after: int | None = Query(default=None, ge=0), player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    if not fx.ready(conn):
        return {"mark": after or 0, "alerts": []}
    return _wire(fx.alerts_for(conn, player["id"], after, _exchange_time(conn)))


@app.post("/api/fx/street")
def fx_street(body: DealRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    _ready(conn)
    return _act(conn, player, lambda now: fx.street_deal(conn, player["id"], body.side, body.currency, body.amount, now, for_empire=body.for_empire))


@app.post("/api/fx/window")
def fx_window(body: WindowRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    _ready(conn)
    return _act(conn, player, lambda now: fx.window_ask(conn, player["id"], body.amount, now, for_empire=body.for_empire), attempts=10)


@app.post("/api/fx/window/{request_id}/cancel")
def fx_window_cancel(request_id: int, body: EmpireOnly, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    _ready(conn)
    return _act(conn, player, lambda now: fx.window_cancel(conn, player["id"], request_id, now, for_empire=body.for_empire))


@app.post("/api/fx/window/sell")
def fx_window_sell(body: WindowRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    _ready(conn)
    return _act(conn, player, lambda now: fx.window_sell(conn, player["id"], body.amount, now, for_empire=body.for_empire))


@app.post("/api/fx/bdcs/{bdc_id}/deal")
def fx_bdc_deal(bdc_id: int, body: DealRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    _ready(conn)
    if body.currency != "USD":
        raise HTTPException(status.HTTP_409_CONFLICT, "Bureaux deal in dollars.")
    return _act(conn, player, lambda now: fx.bdc_deal(conn, player["id"], bdc_id, body.side, body.amount, now, for_empire=body.for_empire))


@app.post("/api/fx/bdc")
def fx_bdc_open(body: BdcRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    _ready(conn)
    return _act(conn, player, lambda now: fx.open_bdc(conn, player["id"], body.name or "", body.buy_bps, body.sell_bps, now), attempts=5)


@app.post("/api/fx/bdc/prices")
def fx_bdc_prices(body: BdcRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    _ready(conn)
    return _act(conn, player, lambda now: fx.price_bdc(conn, player["id"], body.buy_bps, body.sell_bps, now))


@app.post("/api/fx/bdc/close")
def fx_bdc_close(player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    _ready(conn)
    return _act(conn, player, lambda now: fx.close_bdc(conn, player["id"], now), attempts=5)


@app.post("/api/fx/remitter")
def fx_remitter_open(body: RemitterRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    _ready(conn)
    return _act(conn, player, lambda now: fx.open_remitter(conn, player["id"], body.name or "", body.fee_bps, body.days, now), attempts=5)


@app.post("/api/fx/remitter/terms")
def fx_remitter_terms(body: RemitterRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    _ready(conn)
    return _act(conn, player, lambda now: fx.set_remitter(conn, player["id"], body.fee_bps, body.days, now))


@app.post("/api/fx/remitter/close")
def fx_remitter_close(player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    _ready(conn)
    return _act(conn, player, lambda now: fx.close_remitter(conn, player["id"], now), attempts=5)


@app.post("/api/fx/eurobonds/{eurobond_id}")
def fx_eurobond(eurobond_id: int, body: BondRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    _ready(conn)
    return _act(conn, player, lambda now: fx.eurobond_deal(conn, player["id"], eurobond_id, body.side, body.units, now, for_empire=body.for_empire))
