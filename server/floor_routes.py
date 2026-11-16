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
from simulation import duels, exchange, floor, prime

MONEY = {"realised", "unrealised", "total", "dividends", "fees", "exposure", "cash", "held_for_orders", "value", "price",
         "average_price", "gain", "reference_price", "last_price", "lowest_today", "highest_today", "best_bid", "best_offer",
         "start_price", "minimum", "fair", "your_limit", "pnl", "benchmark", "average_paid", "commission", "price_now", "margin", "interest", "offer_value", "bid", "offer", "last", "low", "high", "cost", "reference", "mid", "cover", "done_at_price"}


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
    for_empire: bool = Field(default=False, strict=True)
    block: bool = Field(default=False, strict=True)


class BasketLeg(Request):
    ticker: str = Field(pattern="^[A-Z]{3}$")
    quantity: int = Field(ge=1, le=10_000_000_000, strict=True)


class BasketRequest(Request):
    legs: list[BasketLeg] = Field(min_length=1, max_length=10)
    side: str = Field(pattern="^(buy|sell)$")
    seconds: int = Field(ge=1, le=600, strict=True)
    desks: list[str] = Field(min_length=1, max_length=10)
    for_empire: bool = Field(default=False, strict=True)


class BondAskRequest(Request):
    code: str = Field(min_length=2, max_length=40, pattern="^[A-Za-z0-9-]+$")
    side: str = Field(pattern="^(buy|sell|two_way)$")
    units: int = Field(ge=1, le=10_000_000_000, strict=True)
    seconds: int = Field(ge=1, le=600, strict=True)
    desks: list[str] = Field(min_length=1, max_length=10)
    for_empire: bool = Field(default=False, strict=True)


class QuoteRequest(Request):
    request_id: int = ID
    bid_kobo: int | None = KOBO
    offer_kobo: int | None = KOBO
    valid_seconds: int = Field(ge=1, le=600, strict=True)
    firm: bool = Field(default=True, strict=True)
    margin_bps: int | None = Field(default=None, ge=-500, le=500, strict=True)
    bid_yield_bps: int | None = Field(default=None, ge=-5000, le=30000, strict=True)
    offer_yield_bps: int | None = Field(default=None, ge=-5000, le=30000, strict=True)


class CounterRequest(Request):
    request_id: int = ID
    quote_id: int = ID
    side: str = Field(pattern="^(buy|sell)$")
    price_kobo: int | None = KOBO
    margin_bps: int | None = Field(default=None, ge=-500, le=500, strict=True)


class AnswerRequest(Request):
    counter_id: int = ID
    accept: bool = Field(strict=True)


class AxeRequest(Request):
    ticker: str = Field(pattern="^[A-Z]{3}$")
    side: str | None = Field(default=None, pattern="^(buy|sell)$")
    quantity: int = Field(default=0, ge=0, le=10_000_000_000, strict=True)


class ChatRequest(Request):
    to: str = Field(min_length=1, max_length=40)
    body: str = Field(min_length=1, max_length=300)


class TicketRequest(Request):
    to: str = Field(min_length=1, max_length=40)
    ticker: str = Field(pattern="^[A-Z]{3}$")
    side: str = Field(pattern="^(buy|sell)$")
    quantity: int = Field(ge=1, le=10_000_000_000, strict=True)
    price_kobo: int = Field(ge=1, le=100_000_000_000_000, strict=True)


class TicketAnswer(Request):
    ticket_id: int = ID
    accept: bool = Field(strict=True)


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
    except (floor.FloorError, exchange.ExchangeError, prime.PrimeError) as refused:
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
    return _act(conn, player, lambda now: floor.ask(conn, player["id"], body.ticker, body.side, body.quantity, body.seconds, body.desks, now,
                                                     for_empire=body.for_empire, block=body.block), "floor-ask", 12)


@app.post("/api/floor/ask-basket")
def ask_for_a_basket(body: BasketRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: floor.ask_basket(conn, player["id"], [(leg.ticker, leg.quantity) for leg in body.legs], body.side,
                                                            body.seconds, body.desks, now, for_empire=body.for_empire), "floor-ask", 12)


@app.post("/api/floor/ask-bond")
def ask_for_a_bond(body: BondAskRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: floor.ask_bond(conn, player["id"], body.code, body.side, body.units, body.seconds, body.desks, now,
                                                          for_empire=body.for_empire), "floor-ask", 12)


@app.post("/api/floor/quote")
def quote_a_price(body: QuoteRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: floor.quote(conn, player["id"], body.request_id, body.bid_kobo, body.offer_kobo, body.valid_seconds, now,
                                                       firm=body.firm, margin_bps=body.margin_bps, bid_yield_bps=body.bid_yield_bps,
                                                       offer_yield_bps=body.offer_yield_bps))


@app.post("/api/floor/counter")
def counter_a_price(body: CounterRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: floor.counter(conn, player["id"], body.request_id, body.quote_id, body.side, now,
                                                         price=body.price_kobo, margin_bps=body.margin_bps))


@app.post("/api/floor/answer")
def answer_a_counter(body: AnswerRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: floor.answer(conn, player["id"], body.counter_id, body.accept, now))


@app.post("/api/floor/axe")
def advertise_an_axe(body: AxeRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: floor.set_axe(conn, player["id"], body.ticker, body.side, body.quantity, now), "floor-desk", 20)


@app.post("/api/floor/chat")
def write_on_the_floor(body: ChatRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: floor.say(conn, player["id"], body.to, body.body, now), "floor-chat", 30)


@app.post("/api/floor/ticket")
def propose_a_ticket(body: TicketRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: floor.propose_ticket(conn, player["id"], body.to, body.ticker, body.side, body.quantity,
                                                                body.price_kobo, now), "floor-chat", 30)


@app.post("/api/floor/ticket/answer")
def answer_a_ticket(body: TicketAnswer, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: floor.answer_ticket(conn, player["id"], body.ticket_id, body.accept, now))


@app.get("/api/floor/bonds")
def bonds_for_the_floor(_: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    from simulation import bonds
    return _wire({"bonds": [{"code": b["code"], "name": b["name"], "fair": b["fair"]} for b in bonds.listing(conn, _exchange_time(conn))]})


@app.post("/api/floor/take")
def take_a_price(body: TakeRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: floor.take(conn, player["id"], body.request_id, body.quote_id, body.side, now))


@app.post("/api/floor/pass")
def pass_on_a_request(body: PassRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: floor.pass_on(conn, player["id"], body.request_id, now))



# ---------------------------------------------------------------------------
# Duels on the Floor (16 November 2026)
# ---------------------------------------------------------------------------

class ChallengeRequest(Request):
    empire_id: int = ID


class DuelAnswer(Request):
    duel_id: int = ID
    accept: bool = Field(strict=True)


class DuelWithdraw(Request):
    duel_id: int = ID


def _duel(conn: Connection, player: dict, action) -> dict:
    limits.allow("floor-duel", str(player["id"]), attempts=20, per_seconds=60)
    try:
        done = action(_exchange_time(conn))
    except duels.DuelError as refused:
        raise HTTPException(status.HTTP_409_CONFLICT, str(refused)) from None
    page = duels.view(conn, player["id"], _exchange_time(conn))
    page["result"] = done
    return _wire(page)


@app.get("/api/floor/duels")
def the_duels(player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _wire(duels.view(conn, player["id"], _exchange_time(conn)))


@app.post("/api/floor/duels/challenge")
def challenge_an_empire(body: ChallengeRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _duel(conn, player, lambda now: duels.challenge(conn, player["id"], body.empire_id, now))


@app.post("/api/floor/duels/answer")
def answer_a_challenge(body: DuelAnswer, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _duel(conn, player, lambda now: duels.answer(conn, player["id"], body.duel_id, body.accept, now))


@app.post("/api/floor/duels/withdraw")
def withdraw_a_challenge(body: DuelWithdraw, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _duel(conn, player, lambda now: duels.withdraw(conn, player["id"], body.duel_id, now))



# ---------------------------------------------------------------------------
# Big client orders (16 November 2026)
# ---------------------------------------------------------------------------

class MandateAnswer(Request):
    mandate_id: int = ID
    accept: bool = Field(strict=True)


@app.post("/api/floor/mandate")
def answer_a_mandate(body: MandateAnswer, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: floor.answer_mandate(conn, player["id"], body.mandate_id, body.accept, now), "floor-desk", 20)



class SwapAnswer(Request):
    swap_id: int = ID
    accept: bool = Field(strict=True)


@app.post("/api/floor/swap")
def answer_a_swap(body: SwapAnswer, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: prime.answer(conn, player["id"], body.swap_id, body.accept, now), "floor-desk", 20)
