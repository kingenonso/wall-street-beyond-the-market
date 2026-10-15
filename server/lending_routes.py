"""Stage 9, Part A: borrowing, short selling, every share's risk figures, and "What could happen?".

Every request acts as the logged-in player, for their own account, or (when they are its head or its Asset
Manager) for their empire. A loan's or a short's details go only to its own borrower.
"""

from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi import Path as FastPath
from psycopg import Connection
from psycopg.errors import DeadlockDetected
from pydantic import Field

from server import limits
from server.db import get_connection
from server.firm_routes import MONEY, wire
from server.main import _exchange_time, app, current_player
from server.schemas import Request
from simulation import empires, firm, ledger, lending, lending_empire, montecarlo, risk
from simulation import world_data as data

MONEY.update({"principal", "outstanding", "collateral", "fees_paid", "gain", "limit", "owed", "personal_limit", "equity", "debts",
              "start", "median", "best_likely", "worst_likely", "value_at_risk", "p5", "p25", "p50", "p75", "p95", "fee", "opened_price",
              "price", "value", "shares_value", "cash"})
Money = Annotated[int, Field(gt=0, le=1_000_000_000_000_000, strict=True)]
Count = Annotated[int, Field(gt=0, le=10_000_000_000, strict=True)]


def _id():
    return FastPath(ge=1, le=9_000_000_000_000_000_000)


def _act(conn: Connection, player: dict, action, bucket: str = "borrowing", attempts: int = 30):
    limits.allow(bucket, str(player["id"]), attempts=attempts, per_seconds=60)
    try:
        result = action(_exchange_time(conn))
    except (lending.LendingError, empires.EmpireError, montecarlo.MonteCarloError) as refused:
        raise HTTPException(status.HTTP_409_CONFLICT, str(refused)) from None
    except DeadlockDetected:
        raise HTTPException(status.HTTP_409_CONFLICT, "Somebody else changed this at the same moment. Nothing was changed. Please try again.") from None
    return {"result": wire(result) if isinstance(result, dict) else result}


def _account(conn: Connection, player: dict, for_empire: bool):
    if not for_empire:
        return ledger.player_account_id(conn, player["id"])
    seat, empire = firm._active(conn, player["id"])
    if empire["head_player_id"] != player["id"] and seat["build"] != "asset_manager":
        raise empires.EmpireError("The Asset Manager (or the head) borrows and sells short for the empire.")
    return empire["account_id"]


class ForRequest(Request):
    for_empire: bool = False


class PersonalRequest(Request):
    amount_kobo: Money


class MarginRequest(ForRequest):
    bank: UUID
    amount_kobo: Money


class RepayRequest(ForRequest):
    amount_kobo: Money


class ShortRequest(ForRequest):
    ticker: str = Field(min_length=1, max_length=12)
    shares: Count


class CollateralRequest(ForRequest):
    amount_kobo: Money


class LimitsRequest(Request):
    borrow_naira: int = Field(ge=0, le=10_000_000_000_000, strict=True)
    short_naira: int = Field(ge=0, le=10_000_000_000_000, strict=True)


class WhatRequest(Request):
    what: Literal["portfolio", "empire", "share", "property"]
    horizon: Literal["quarter", "year"] = "quarter"
    ticker: str | None = Field(default=None, max_length=12)
    property_id: int | None = Field(default=None, ge=1)


@app.get("/api/borrowing")
def borrowing(player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    """The player's loans and shorts, what they may borrow, the shares that can be borrowed, and their empire's (if they act for it)."""
    from simulation import banking, careers
    now = _exchange_time(conn)
    account = ledger.player_account_id(conn, player["id"])
    period = careers.world_now(conn, now)["period"]
    out = {
        **lending.view(conn, account, now, player_id=player["id"]),
        "lendable": lending.lendable_view(conn),
        "banks": [{"id": str(b["id"]), "name": b["name"]} for b in banking.banks(conn, max(period, 1))],
        "my_bank": (careers.current_bank(conn, player["id"]) or {}).get("name"),
        "rules": {"personal_salary_quarters": data.PERSONAL_LOAN_SALARY_QUARTERS, "margin_most_bps": data.MARGIN_LOAN_MOST_BPS,
                  "margin_call_bps": data.MARGIN_CALL_BPS, "margin_sell_bps": data.MARGIN_SELL_BPS,
                  "short_collateral_bps": data.SHORT_COLLATERAL_BPS, "short_call_bps": data.SHORT_CALL_BPS,
                  "short_buy_in_bps": data.SHORT_BUY_IN_BPS, "lending_pool_bps": data.LENDING_POOL_BPS},
        "empire": None,
    }
    seat = empires.seat_of(conn, player["id"])
    if seat is not None and seat.get("empire_status") == "active" and seat.get("empire_kind") != "pension":
        empire = empires._empire(conn, seat["empire_id"])
        acts = empire["head_player_id"] == player["id"] or seat["build"] == "asset_manager"
        sets = seat["build"] == "risk_manager" or (empire["head_player_id"] == player["id"]
                                                   and not firm.desk_members(conn, empire["id"], "risk_manager"))
        out["empire"] = {"name": empire["name"], "acts": acts, "sets_limits": sets, "limits": lending_empire.limits(conn, empire),
                         **({"book": lending.view(conn, empire["account_id"], now)} if acts or sets else {})}
    return wire(out)


@app.post("/api/borrowing/personal")
def borrow_personal(body: PersonalRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: lending.take_personal(conn, player["id"], body.amount_kobo, now))


@app.post("/api/borrowing/margin")
def borrow_margin(body: MarginRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    if body.for_empire:
        return _act(conn, player, lambda now: lending_empire.borrow(conn, player["id"], body.bank, body.amount_kobo, now))
    return _act(conn, player, lambda now: lending.take_margin(conn, ledger.player_account_id(conn, player["id"]), body.bank, body.amount_kobo, now))


@app.post("/api/borrowing/loans/{loan_id}/repay")
def borrow_repay(body: RepayRequest, loan_id: int = _id(), player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: lending.repay(conn, _account(conn, player, body.for_empire), loan_id, body.amount_kobo, now))


@app.post("/api/shorts")
def short_open(body: ShortRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    ticker = body.ticker.upper()
    if body.for_empire:
        return _act(conn, player, lambda now: lending_empire.short(conn, player["id"], ticker, body.shares, now), bucket="short")
    return _act(conn, player, lambda now: lending.open_short(conn, ledger.player_account_id(conn, player["id"]), ticker, body.shares, now),
                bucket="short")


@app.post("/api/shorts/{short_id}/close")
def short_close(body: ForRequest, short_id: int = _id(), player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: lending.close_short(conn, _account(conn, player, body.for_empire), short_id, now), bucket="short")


@app.post("/api/shorts/{short_id}/collateral")
def short_collateral(body: CollateralRequest, short_id: int = _id(), player: dict = Depends(current_player),
                     conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: lending.add_collateral(conn, _account(conn, player, body.for_empire), short_id, body.amount_kobo, now),
                bucket="short")


@app.post("/api/empire/limits")
def empire_limits(body: LimitsRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: lending_empire.set_limits(conn, player["id"], body.borrow_naira, body.short_naira, now))


@app.get("/api/market/risk")
def market_risk(_: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    """Every share's volatility, beta and short interest: public figures anybody could work out."""
    found = risk.share_risk(conn)
    interest = lending.short_interest(conn)
    rows = conn.execute("SELECT c.id, c.ticker, c.name FROM companies c JOIN market_instruments m ON m.company_id = c.id ORDER BY c.ticker").fetchall()
    return {"shares": [{"ticker": r["ticker"], "name": r["name"], **(found.get(r["id"]) or {"volatility_bps": None, "beta": None, "sessions": 0,
                                                                                          "enough": False}),
                        "short_interest_bps": interest.get(r["id"], 0)} for r in rows],
            "year_sessions": risk.YEAR_SESSIONS}


@app.post("/api/what-could-happen")
def what_could_happen(body: WhatRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: montecarlo.run(conn, player["id"], body.what, now, horizon=body.horizon,
                                                         ticker=(body.ticker or "").upper() or None, property_id=body.property_id),
                bucket="montecarlo", attempts=10)
