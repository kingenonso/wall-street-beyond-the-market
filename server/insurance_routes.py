"""Insurance on the website: a page under Money (owner, 9 November 2026).

A player: the four policies with what each would cost on their own record today, the cover they hold, the losses on
their record in the last year and what was decided on each claim, and what their cover does for a personal loan. They
may buy a policy, cancel one, and claim against a loss on their record.

Every figure on the page is the server's: the premium, its parts, the most cover, the loss and the payout. The page
names a policy and a cover; it never names an amount to be paid, and a claim names a recorded loss, never a sum.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, status
from psycopg import Connection
from psycopg.errors import DeadlockDetected, UniqueViolation
from pydantic import Field

from server import limits
from server.db import get_connection
from server.main import _exchange_time, app, current_player
from server.schemas import Request
from simulation import careers, insurance

Money = Annotated[int, Field(ge=0, le=1_000_000_000_000_000, strict=True)]
KIND = Field(pattern="^(property|directors|income|umbrella)$")

# Money in kobo, sent as text so no figure is ever rounded on the way.
MONEY = {"cover", "excess", "premium", "expected_loss", "loading", "on_cover", "discount", "most_cover", "loss",
         "payable", "paid", "shortfall", "debt", "pool"}


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


class BuyRequest(Request):
    kind: str = KIND
    cover_kobo: Money
    excess_kobo: Money = 0


class CancelRequest(Request):
    kind: str = KIND


class ClaimRequest(Request):
    loss: str = Field(min_length=1, max_length=80, pattern=r"^(property:\d+:\d+|job:\d+|case:\d+)$")


def _act(conn: Connection, player: dict, action):
    limits.allow("insurance", str(player["id"]), attempts=20, per_seconds=60)
    try:
        action(_exchange_time(conn))
    except (insurance.InsuranceError, careers.CareerError) as refused:
        raise HTTPException(status.HTTP_409_CONFLICT, str(refused)) from None
    except (DeadlockDetected, UniqueViolation):
        raise HTTPException(status.HTTP_409_CONFLICT, "Somebody else changed this at the same moment. Please try again.") from None


def _page(conn: Connection, player: dict, extra: dict | None = None) -> dict:
    page = insurance.view(conn, player["id"], _exchange_time(conn))
    if extra is not None:
        page["result"] = extra
    return _wire(page)


@app.get("/api/insurance")
def insurance_page(player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _page(conn, player)


@app.post("/api/insurance/buy")
def insurance_buy(body: BuyRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    done: dict = {}
    _act(conn, player, lambda now: done.update(insurance.buy(conn, player["id"], body.kind, body.cover_kobo, body.excess_kobo, now)))
    return _page(conn, player, done)


@app.post("/api/insurance/cancel")
def insurance_cancel(body: CancelRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    done: dict = {}
    _act(conn, player, lambda now: done.update(insurance.cancel(conn, player["id"], body.kind, now)))
    return _page(conn, player, done)


@app.post("/api/insurance/claim")
def insurance_claim(body: ClaimRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    done: dict = {}
    _act(conn, player, lambda now: done.update(insurance.claim(conn, player["id"], body.loss, now)))
    return _page(conn, player, done)
