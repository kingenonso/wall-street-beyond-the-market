"""Run Your Own Fund on the website (the talent and funds stage, Part 2).

Anybody: the list of funds, a fund's factsheet (its price day by day against its benchmark, its stars, its fees and rules,
and what it held at the end of the quarter before last), and putting money in or asking it back at the next closing bell.
A manager (an Asset Manager of Level 20 or above): launching a fund, and running it: dealing in shares and bonds, the gate,
fees, closing, merging.

Never sent: what a fund holds now (only what it held two quarter ends ago); who else holds a fund or how much; anybody's
orders but the viewer's own; the fund's books (a false cost is seen only by the regulator's audit).
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
from simulation import funds
from simulation.money import naira

KOBO = {"amount", "worth", "value", "least_in", "cash", "shares_value", "bonds_value", "owed", "worth_now", "waiting_in", "costs_limit",
        "costs_used", "paid", "in", "out", "registration", "seed", "unit_price", "high_water", "least_in_limits", "price", "limit_price",
        "reserved", "limit", "used"}


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


def _act(conn: Connection, player: dict, action, attempts: int = 30):
    limits.allow("funds", str(player["id"]), attempts=attempts, per_seconds=60)
    try:
        with conn.transaction():
            return _wire({"result": action(_exchange_time(conn))})
    except funds.FundError as refused:
        raise HTTPException(status.HTTP_409_CONFLICT, str(refused)) from None
    except (DeadlockDetected, UniqueViolation, CheckViolation):
        raise HTTPException(status.HTTP_409_CONFLICT, "Somebody else changed this at the same moment. Please try again.") from None


def _ready(conn: Connection) -> None:
    if not funds.ready(conn):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Funds are not open in this world yet.")


# ---------------------------------------------------------------------------
# Anybody
# ---------------------------------------------------------------------------

@app.get("/api/funds")
def funds_page(player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    _ready(conn)
    now = _exchange_time(conn)
    out = funds.listing(conn, player["id"], now)
    out["mine"] = funds.mine(conn, player["id"], now)
    out["managing"] = funds.manager_view(conn, player["id"], now)
    return _wire(out)


@app.get("/api/funds/alerts")
def fund_alerts(after: int | None = Query(default=None, ge=0), player: dict = Depends(current_player),
                conn: Connection = Depends(get_connection)):
    if not funds.ready(conn):
        return {"mark": after or 0, "alerts": []}
    return _wire(funds.alerts_for(conn, player["id"], after, _exchange_time(conn)))


@app.get("/api/funds/{fund_id}")
def fund_factsheet(fund_id: int = FastPath(ge=1), player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    _ready(conn)
    try:
        return _wire(funds.factsheet(conn, fund_id, player["id"], _exchange_time(conn)))
    except funds.FundError as missing:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(missing)) from None


class InvestRequest(Request):
    amount_naira: int = Field(gt=0, le=100_000_000_000, strict=True)
    for_empire: bool = False


class LeaveRequest(Request):
    units: int | None = Field(default=None, gt=0, le=10**15, strict=True)        # None: every unit
    for_empire: bool = False


class FollowRequest(Request):
    on: bool


@app.post("/api/funds/{fund_id}/invest")
def fund_invest(body: InvestRequest, fund_id: int = FastPath(ge=1), player: dict = Depends(current_player),
                conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: funds.invest(conn, player["id"], fund_id, naira(body.amount_naira), now, for_empire=body.for_empire))


@app.post("/api/funds/{fund_id}/leave")
def fund_leave(body: LeaveRequest, fund_id: int = FastPath(ge=1), player: dict = Depends(current_player),
               conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: funds.leave(conn, player["id"], fund_id, body.units, now, for_empire=body.for_empire))


@app.post("/api/funds/orders/{order_id}/cancel")
def fund_order_cancel(order_id: int = FastPath(ge=1), player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: funds.cancel(conn, player["id"], order_id, now))


@app.post("/api/funds/{fund_id}/follow")
def fund_follow(body: FollowRequest, fund_id: int = FastPath(ge=1), player: dict = Depends(current_player),
                conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: funds.follow(conn, player["id"], fund_id, body.on, now))


# ---------------------------------------------------------------------------
# A manager
# ---------------------------------------------------------------------------

class LaunchRequest(Request):
    name: str = Field(min_length=3, max_length=60)
    strategy: str = Field(pattern="^(shares|banks|bonds|balanced|anything|index)$")
    fee_bps: int = Field(ge=0, le=200, strict=True)
    perf_fee_bps: int = Field(ge=0, le=2000, strict=True)
    least_in_naira: int = Field(gt=0, le=1_000_000_000, strict=True)
    seed_naira: int = Field(gt=0, le=100_000_000_000, strict=True)
    words: str = Field(default="", max_length=400)
    index_code: str | None = Field(default=None, pattern="^[A-Z0-9]{2,10}$")      # Part 3: an index fund's index...
    method: str = Field(default="full", pattern="^(full|sample)$")                # ...copied in full or by sampling


class ShareDeal(Request):
    ticker: str = Field(pattern="^[A-Z]{3}$")
    side: str = Field(pattern="^(buy|sell)$")
    quantity: int = Field(gt=0, le=10**12, strict=True)
    limit_price_kobo: int = Field(gt=0, le=10**12, strict=True)


class BondDeal(Request):
    code: str = Field(pattern="^[A-Z0-9-]{2,24}$")
    side: str = Field(pattern="^(buy|sell)$")
    units: int = Field(gt=0, le=10**12, strict=True)


class GateRequest(Request):
    on: bool


class FeesRequest(Request):
    fee_bps: int = Field(ge=0, le=200, strict=True)
    perf_fee_bps: int = Field(ge=0, le=2000, strict=True)


class MergeRequest(Request):
    into: int = Field(ge=1, strict=True)


class MergeAnswer(Request):
    accept: bool


class CostsRequest(Request):
    amount_naira: int = Field(gt=0, le=100_000_000_000, strict=True)


@app.post("/api/funds/launch")
def fund_launch(body: LaunchRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: funds.launch(conn, player["id"], name=body.name, strategy=body.strategy, fee_bps=body.fee_bps,
                                                       perf_fee_bps=body.perf_fee_bps, least_in=naira(body.least_in_naira),
                                                       seed=naira(body.seed_naira), now=now, words=body.words, index_code=body.index_code,
                                                       method=body.method), attempts=5)


@app.post("/api/funds/manage/shares")
def fund_deal_shares(body: ShareDeal, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: funds.trade_shares(conn, player["id"], ticker=body.ticker, side=body.side, quantity=body.quantity,
                                                             limit_price=body.limit_price_kobo, now=now))


@app.post("/api/funds/manage/shares/{order_id}/cancel")
def fund_cancel_deal(order_id: int = FastPath(ge=1), player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: funds.cancel_trade(conn, player["id"], order_id, now))


@app.post("/api/funds/manage/bonds")
def fund_deal_bonds(body: BondDeal, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: funds.trade_bonds(conn, player["id"], code=body.code, side=body.side, units=body.units, now=now))


@app.post("/api/funds/manage/gate")
def fund_gate(body: GateRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: funds.set_gate(conn, player["id"], body.on, now))


@app.post("/api/funds/manage/fees")
def fund_fees(body: FeesRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: funds.lower_fees(conn, player["id"], body.fee_bps, body.perf_fee_bps, now))


@app.post("/api/funds/manage/close")
def fund_close(player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: funds.close(conn, player["id"], now))


@app.post("/api/funds/manage/merge")
def fund_merge(body: MergeRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: funds.propose_merge(conn, player["id"], body.into, now))


@app.post("/api/funds/manage/merges/{merge_id}")
def fund_merge_answer(body: MergeAnswer, merge_id: int = FastPath(ge=1), player: dict = Depends(current_player),
                      conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: funds.answer_merge(conn, player["id"], merge_id, body.accept, now))


@app.post("/api/funds/manage/costs")
def fund_costs(body: CostsRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: funds.take_costs(conn, player["id"], naira(body.amount_naira), now), attempts=5)
