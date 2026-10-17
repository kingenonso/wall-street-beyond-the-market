"""Stage 10, Part 2: charities and media titles on the website. (Bids for a title use the Auction House's own routes.)

Never sent: whether a charity's grant went to someone connected to it (only its totals are public), the Money Watch's
private list, a title auction's lowest price, or anyone's bid limit but the viewer's own.
"""

from __future__ import annotations

from typing import Literal

from fastapi import Depends, HTTPException, status
from psycopg import Connection
from psycopg.errors import DeadlockDetected
from pydantic import Field

from server import limits
from server.db import get_connection
from server.firm_routes import wire
from server.main import _exchange_time, app, current_player
from server.schemas import Request
from simulation import auctions, charity, media, newsroom, press
from simulation.money import naira
from simulation.property import PropertyError

KOBO = {"given", "to_cause", "to_people", "holds", "revenue", "start_price", "minimum", "fair", "your_limit"}


def _money(value):
    """Money as text (a kobo figure can be larger than a browser counts exactly), for the keys these pages use."""
    if isinstance(value, dict):
        return {k: (str(v) if k in KOBO and isinstance(v, int) and not isinstance(v, bool) else _money(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [_money(v) for v in value]
    return value


def _act(conn: Connection, player: dict, action, bucket: str = "society", attempts: int = 20) -> dict:
    limits.allow(bucket, str(player["id"]), attempts=attempts, per_seconds=60)
    try:
        result = action(_exchange_time(conn))
    except (charity.CharityError, PropertyError, newsroom.NewsroomError, press.PressError) as refused:
        raise HTTPException(status.HTTP_409_CONFLICT, str(refused)) from None
    except DeadlockDetected:
        raise HTTPException(status.HTTP_409_CONFLICT, "Somebody else changed this at the same moment. Please try again.") from None
    return {"result": wire(result) if isinstance(result, (dict, list)) else result}


class FoundRequest(Request):
    name: str = Field(min_length=4, max_length=60)
    cause: Literal["education", "health", "water", "arts", "relief"]
    city: str = Field(min_length=3, max_length=20)
    amount_naira: int = Field(ge=1_000_000, le=10_000_000_000, strict=True)
    for_empire: bool = False


class GiftRequest(Request):
    amount_naira: int = Field(ge=10_000, le=10_000_000_000, strict=True)
    from_empire: bool = False


class GrantRequest(Request):
    amount_naira: int = Field(ge=10_000, le=10_000_000_000, strict=True)
    words: str = Field(min_length=5, max_length=200)
    to: str | None = Field(default=None, min_length=2, max_length=40)


class SellRequest(Request):
    reserve_naira: int = Field(ge=0, le=100_000_000_000, strict=True)
    for_empire: bool = False


class TitleRequest(Request):
    title_id: int | None = Field(default=None, gt=0)


class CharityFileRequest(Request):
    charity: str = Field(min_length=4, max_length=60)


@app.get("/api/charities")
def charities(player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return {"charities": wire(_money(charity.listing(conn, player["id"])))}


@app.post("/api/charities", status_code=201)
def charity_found(body: FoundRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: charity.found(conn, player["id"], body.name, body.cause, body.city, naira(body.amount_naira), now,
                                                         for_empire=body.for_empire))


@app.post("/api/charities/{charity_id}/give")
def charity_give(charity_id: int, body: GiftRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: charity.give(conn, player["id"], charity_id, naira(body.amount_naira), now, from_empire=body.from_empire))


@app.post("/api/charities/{charity_id}/grant")
def charity_grant(charity_id: int, body: GrantRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: charity.grant(conn, player["id"], charity_id, naira(body.amount_naira), body.words, now, to_name=body.to))


@app.get("/api/media")
def media_titles(player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    now = _exchange_time(conn)
    return wire(_money({"titles": media.view(conn, player["id"]),
                        "auctions": auctions.title_view(conn, now, viewer=_viewer_account(conn, player))}))


def _viewer_account(conn: Connection, player: dict):
    from simulation import ledger
    return ledger.player_account_id(conn, player["id"])


@app.post("/api/media/{title_id}/sell", status_code=201)
def media_sell(title_id: int, body: SellRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: {"auction_id": media.owner_list(conn, player["id"], title_id, naira(body.reserve_naira), now,
                                                                         for_empire=body.for_empire)})


@app.post("/api/newsroom/title")
def newsroom_title(body: TitleRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: newsroom.set_title(conn, player["id"], body.title_id, now), bucket="newsroom", attempts=40)


@app.post("/api/investigations/charity", status_code=201)
def investigation_charity(body: CharityFileRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: press.open_file(conn, player["id"], None, None, now, charity_name=body.charity), bucket="press")
