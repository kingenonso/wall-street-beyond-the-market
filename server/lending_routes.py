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
from simulation import crashfund, derivatives, empires, firm, ledger, lending, lending_empire, montecarlo, risk, swaps
from simulation import world_data as data

MONEY.update({"principal", "outstanding", "collateral", "fees_paid", "gain", "limit", "owed", "personal_limit", "equity", "debts",
              "start", "median", "best_likely", "worst_likely", "value_at_risk", "p5", "p25", "p50", "p75", "p95", "fee", "opened_price",
              "price", "value", "shares_value", "cash", "bid", "ask", "spot", "entry_price", "margin", "margin_long", "margin_short",
              "cover", "paid_in", "paid_out", "fund", "result"})
Money = Annotated[int, Field(gt=0, le=1_000_000_000_000_000, strict=True)]
Count = Annotated[int, Field(gt=0, le=10_000_000_000, strict=True)]


def _id():
    return FastPath(ge=1, le=9_000_000_000_000_000_000)


def _act(conn: Connection, player: dict, action, bucket: str = "borrowing", attempts: int = 30):
    limits.allow(bucket, str(player["id"]), attempts=attempts, per_seconds=60)
    try:
        result = action(_exchange_time(conn))
    except (lending.LendingError, empires.EmpireError, montecarlo.MonteCarloError, derivatives.DerivativesError,
            swaps.SwapError) as refused:
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
    derivatives_naira: int | None = Field(default=None, ge=0, le=10_000_000_000_000, strict=True)


class TradeRequest(ForRequest):
    side: Literal["long", "short"]
    contracts: int = Field(gt=0, le=1_000, strict=True)
    purpose: str | None = Field(default=None, max_length=120)
    limit_kobo: int | None = Field(default=None, gt=0, le=1_000_000_000_000, strict=True)


class CoverRequest(Request):
    cover_kobo: int = Field(ge=0, le=1_000_000_000_000_000, strict=True)


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
    return _act(conn, player, lambda now: lending_empire.set_limits(conn, player["id"], body.borrow_naira, body.short_naira, now,
                                                                    body.derivatives_naira))


@app.get("/api/share-risk")
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


# ---------------------------------------------------------------------------
# Part B: options, futures, the hedging desk and the crash fund
# ---------------------------------------------------------------------------

def _empire_for(conn: Connection, player: dict):
    seat = empires.seat_of(conn, player["id"])
    if seat is None or seat.get("empire_status") != "active" or seat.get("empire_kind") == "pension":
        return None, None
    return seat, empires._empire(conn, seat["empire_id"])


@app.get("/api/derivatives")
def derivatives_board(underlying: str | None = None, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    """The option chains and futures with the market makers' prices (public), the player's own positions, and their empire's."""
    now = _exchange_time(conn)
    account = ledger.player_account_id(conn, player["id"])
    out = {**derivatives.board(conn, now, (underlying or "").upper() or None), "mine": derivatives.positions_of(conn, account, now),
           "my_orders": derivatives.orders_of(conn, account), "empire": None}
    seat, empire = _empire_for(conn, player)
    if empire is not None:
        head = empire["head_player_id"] == player["id"]
        acts = head or seat["build"] in ("asset_manager", "risk_manager")
        out["empire"] = {"name": empire["name"], "acts": acts, "head": head, "build": seat["build"],
                         "limit_naira": lending_empire.limits(conn, empire)["derivatives_limit_naira"],
                         "committed": lending_empire.committed(conn, empire["account_id"]),
                         "positions": derivatives.positions_of(conn, empire["account_id"], now) if acts else [],
                         "orders": derivatives.orders_of(conn, empire["account_id"]) if acts else [],
                         "crash_fund": crashfund.view(conn, empire)}
    return wire(out)


@app.post("/api/derivatives/{series_id}/trade")
def derivatives_trade(body: TradeRequest, series_id: int = _id(), player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    if body.for_empire:
        return _act(conn, player, lambda now: lending_empire.trade(conn, player["id"], series_id, body.side, body.contracts, now, body.purpose,
                                                                   limit=body.limit_kobo), bucket="derivatives")
    return _act(conn, player, lambda now: derivatives.open_position(conn, ledger.player_account_id(conn, player["id"]), series_id, body.side,
                                                                    body.contracts, now, player_id=player["id"], limit=body.limit_kobo),
                bucket="derivatives")


@app.post("/api/derivatives/orders/{order_id}/cancel")
def derivatives_cancel(body: ForRequest, order_id: int = _id(), player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    def act(now):
        if body.for_empire:
            seat, empire = firm._active(conn, player["id"])
            if empire["head_player_id"] != player["id"] and seat["build"] not in ("asset_manager", "risk_manager", "investment_banker"):
                raise empires.EmpireError("Only the members who trade for the empire cancel its orders.")
            return derivatives.cancel_order(conn, empire["account_id"], order_id, now)
        return derivatives.cancel_order(conn, ledger.player_account_id(conn, player["id"]), order_id, now)
    return _act(conn, player, act, bucket="derivatives")


@app.get("/api/derivatives/{series_id}/explain")
def derivatives_explain(series_id: int = _id(), _: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    """A contract's fair value at three depths, from public prices only."""
    try:
        return wire(derivatives.explain(conn, series_id, _exchange_time(conn)))
    except derivatives.DerivativesError as missing:
        raise HTTPException(status_code=404, detail=str(missing)) from None


@app.post("/api/derivatives/positions/{position_id}/close")
def derivatives_close(body: ForRequest, position_id: int = _id(), player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    if body.for_empire:
        return _act(conn, player, lambda now: lending_empire.close_derivative(conn, player["id"], position_id, now), bucket="derivatives")
    return _act(conn, player, lambda now: derivatives.close_position(conn, ledger.player_account_id(conn, player["id"]), position_id, now),
                bucket="derivatives")


@app.post("/api/derivatives/positions/{position_id}/margin")
def derivatives_margin(body: CollateralRequest, position_id: int = _id(), player: dict = Depends(current_player),
                       conn: Connection = Depends(get_connection)):
    def act(now):
        if body.for_empire:
            seat, empire = firm._active(conn, player["id"])
            if empire["head_player_id"] != player["id"] and seat["build"] not in ("asset_manager", "risk_manager"):
                raise empires.EmpireError("The Asset Manager or the Risk Manager looks after the empire's options and futures.")
            account = empire["account_id"]
        else:
            account = ledger.player_account_id(conn, player["id"])
        return derivatives.add_margin(conn, account, position_id, body.amount_kobo, now)
    return _act(conn, player, act, bucket="derivatives")


@app.post("/api/empire/crash-fund")
def empire_crash_fund(body: CoverRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: crashfund.ask_cover(conn, player["id"], body.cover_kobo, now))


# ---------------------------------------------------------------------------
# The gap stage: swaps
# ---------------------------------------------------------------------------

class SwapRequest(ForRequest):
    kind: Literal["rate", "oil"]
    side: Literal["pay_fixed", "receive_fixed"]
    quarters: int = Field(ge=1, le=8, strict=True)
    notional_kobo: int | None = Field(default=None, gt=0, le=1_000_000_000_000, strict=True)
    barrels: int | None = Field(default=None, gt=0, le=100_000, strict=True)
    fixed: int | None = Field(default=None, gt=0, le=1_000_000_000_000, strict=True)
    bank: UUID | None = None
    player: str | None = Field(default=None, max_length=80)
    empire: str | None = Field(default=None, max_length=80)


@app.get("/api/swaps")
def swaps_list(player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    """The player's own swaps, and their empire's if they sit in one. Each swap is shown only to its two sides."""
    accounts = [ledger.player_account_id(conn, player["id"])]
    seat = empires.seat_of(conn, player["id"])
    empire_name = None
    if seat is not None and seat.get("empire_status") == "active" and seat.get("empire_kind") != "pension":
        accounts.append(seat["account_id"])
        empire_name = seat["empire_name"]
    banks = conn.execute("SELECT id, name FROM companies WHERE sector = 'banking' AND status = 'trading' ORDER BY name").fetchall()
    return wire({"swaps": swaps.view(conn, accounts), "empire": empire_name, "banks": [{"id": str(b["id"]), "name": b["name"]} for b in banks],
                 "rate_now": swaps.rate_for(conn, 10 ** 6), "oil_now": swaps.oil_for(conn), "unlock_level": derivatives.data.UNLOCK_ADVANCED_LEVEL})


@app.post("/api/swaps")
def swaps_propose(body: SwapRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    other = {"bank": str(body.bank)} if body.bank else {"player": body.player} if body.player else {"empire": body.empire} if body.empire else {}
    return _act(conn, player, lambda now: swaps.propose(conn, player["id"], kind=body.kind, counterparty=other, side=body.side,
                                                         quarters=body.quarters, notional=body.notional_kobo, barrels=body.barrels,
                                                         fixed=body.fixed, now=now, for_empire=body.for_empire), bucket="derivatives")


@app.post("/api/swaps/{swap_id}/accept")
def swaps_accept(body: ForRequest, swap_id: int = _id(), player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: swaps.accept(conn, player["id"], swap_id, now, for_empire=body.for_empire), bucket="derivatives")


@app.post("/api/swaps/{swap_id}/decline")
def swaps_decline(body: ForRequest, swap_id: int = _id(), player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: swaps.decline(conn, player["id"], swap_id, now, for_empire=body.for_empire), bucket="derivatives")
