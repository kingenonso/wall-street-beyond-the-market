"""Unions and strikes on the website (16 and 17 November 2026). The unions, the disputes the public knows of, and the pay
deals in force, or one company's union for its page. Part 2: at a company a player-run empire controls, its head answers
the union (agree, offer less, refuse), may ask once for more time and may hire a mediator; its members may advise.
Nothing is shown before its day."""

from __future__ import annotations

from fastapi import Depends, HTTPException, Query, status
from psycopg import Connection
from pydantic import Field

from server import limits
from server.db import get_connection
from server.floor_routes import ID
from server.main import _exchange_time, app, current_player
from server.schemas import Request
from simulation import unions

MONEY = {"price", "paid", "wages_quarter", "sales_quarter", "strike_short", "strike_middle", "strike_long", "rise_two_years", "fair_two_years",
         "value", "profit_quarter", "stake_cost", "mediator_fee", "mediator_quote", "fee"}


def _wire(value, key: str | None = None):
    if isinstance(value, dict):
        return {k: _wire(v, k) for k, v in value.items()}
    if isinstance(value, list):
        return [_wire(v, key) for v in value]
    if key in MONEY and isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    return value


@app.get("/api/unions")
def the_unions(ticker: str | None = Query(None, pattern=r"^[A-Za-z]{2,6}$"), player: dict = Depends(current_player),
               conn: Connection = Depends(get_connection)):
    return _wire(unions.view(conn, _exchange_time(conn), ticker, player["id"]))


class UnionAnswer(Request):
    dispute_id: int = ID
    choice: str = Field(pattern="^(agree|offer|refuse)$")
    offer_bps: int | None = Field(None, ge=1, le=10_000, strict=True)


class UnionAsk(Request):
    dispute_id: int = ID


class UnionAdvice(Request):
    dispute_id: int = ID
    advice: str = Field(pattern="^(agree|offer|refuse)$")
    offer_bps: int | None = Field(None, ge=1, le=10_000, strict=True)
    note: str = Field("", max_length=300)


def _act(player: dict, conn: Connection, ticker_of: int, act):
    limits.allow("unions", str(player["id"]), attempts=30, per_seconds=60)
    try:
        done = act()
    except unions.UnionError as refused:
        raise HTTPException(status.HTTP_409_CONFLICT, str(refused)) from None
    row = conn.execute("SELECT c.ticker FROM union_disputes d JOIN companies c ON c.id = d.company_id WHERE d.id = %s", (ticker_of,)).fetchone()
    page = unions.view(conn, _exchange_time(conn), row["ticker"] if row else None, player["id"])
    page["result"] = done
    return _wire(page)


@app.post("/api/unions/answer")
def answer_the_union(body: UnionAnswer, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _act(player, conn, body.dispute_id,
                lambda: unions.answer(conn, player["id"], body.dispute_id, body.choice, body.offer_bps, _exchange_time(conn)))


@app.post("/api/unions/more-time")
def ask_for_more_time(body: UnionAsk, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _act(player, conn, body.dispute_id, lambda: unions.more_time(conn, player["id"], body.dispute_id, _exchange_time(conn)))


@app.post("/api/unions/mediator")
def hire_a_mediator(body: UnionAsk, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _act(player, conn, body.dispute_id, lambda: unions.hire_mediator(conn, player["id"], body.dispute_id, _exchange_time(conn)))


@app.post("/api/unions/advise")
def advise_the_head(body: UnionAdvice, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _act(player, conn, body.dispute_id, lambda: unions.advise(conn, player["id"], body.dispute_id, body.advice, body.offer_bps,
                                                                     body.note, _exchange_time(conn)))


class UnionBribe(Request):
    ticker: str = Field(pattern=r"^[A-Za-z]{2,6}$")
    kind: str = Field(pattern="^(strike|calm)$")


@app.post("/api/unions/quiet-word")
def pay_a_union_leader(body: UnionBribe, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    """Part 3 (17 November 2026): the head pays a union leader in secret. A crime, between players only."""
    limits.allow("unions", str(player["id"]), attempts=30, per_seconds=60)
    try:
        done = unions.bribe(conn, player["id"], body.ticker, body.kind, _exchange_time(conn))
    except unions.UnionError as refused:
        raise HTTPException(status.HTTP_409_CONFLICT, str(refused)) from None
    page = unions.view(conn, _exchange_time(conn), body.ticker, player["id"])
    page["result"] = done
    return _wire(page)
