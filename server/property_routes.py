"""Stage 8: land, property, the Auction House and empire headquarters.

Every request acts as the logged-in player only, for their own account, or (when they are its head, or
the desk asked for) for their empire. A property's title flaw, a property company's book value, a
seller's lowest price and other bidders' limits never leave the server.
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
from simulation import auctions, empires, firm, headquarters, ledger, property as prop

MONEY.update({"rent_due", "build_cost", "tax_owed", "last_rent", "last_tax", "equity", "start_price", "minimum", "fair",
              "your_limit", "next_cost", "rebuild_cost", "upkeep", "held", "limit", "spent"})
Money = Annotated[int, Field(gt=0, le=1_000_000_000_000_000, strict=True)]
Reserve = Annotated[int, Field(ge=0, le=1_000_000_000_000_000, strict=True)]
Share = Annotated[int, Field(ge=0, le=10_000, strict=True)]


def _id():
    return FastPath(ge=1, le=9_000_000_000_000_000_000)


def _account(conn: Connection, player: dict):
    return ledger.player_account_id(conn, player["id"])


def _empire_account(conn: Connection, player: dict, *, head: bool = True):
    seat, empire = firm._active(conn, player["id"])
    if head and empire["head_player_id"] != player["id"]:
        raise prop.PropertyError("The head decides what the empire does with its property.")
    return empire


def _act(conn: Connection, player: dict, action, bucket: str = "property", attempts: int = 30) -> dict:
    limits.allow(bucket, str(player["id"]), attempts=attempts, per_seconds=60)
    try:
        result = action(_exchange_time(conn))
    except (prop.PropertyError, empires.EmpireError) as refused:
        raise HTTPException(status.HTTP_409_CONFLICT, str(refused)) from None
    except DeadlockDetected:
        raise HTTPException(status.HTTP_409_CONFLICT, "Somebody else changed this at the same moment. Nothing was changed. Please try again.") from None
    return {"result": wire(result) if isinstance(result, dict) else result}


def _who(conn: Connection, player: dict, for_empire: bool):
    return _empire_account(conn, player)["account_id"] if for_empire else _account(conn, player)


class ForRequest(Request):
    for_empire: bool = False


class UpkeepRequest(ForRequest):
    on: bool


class SellRequest(ForRequest):
    reserve_kobo: Reserve


class RepayRequest(ForRequest):
    amount_kobo: Money


class BidRequest(Request):
    limit_kobo: Money
    mortgage_bank: UUID | None = None
    mortgage_bps: Share = 0
    partner_id: int | None = Field(default=None, ge=1)


class PartnerRequest(ForRequest):
    partner_empire_id: int | None = Field(default=None, ge=1)
    partner_player_name: str | None = Field(default=None, min_length=1, max_length=60)
    partner_bps: int = Field(ge=500, le=9000, strict=True)


class PartnerAnswer(ForRequest):
    agree: bool
    most_kobo: int = Field(default=0, ge=0, le=1_000_000_000_000_000, strict=True)


class CheckRequest(Request):
    step: Literal["title", "valuation", "limit", "money"]
    value_kobo: int | None = Field(default=None, gt=0, le=1_000_000_000_000_000, strict=True)
    limit_kobo: int | None = Field(default=None, gt=0, le=1_000_000_000_000_000, strict=True)
    bank: UUID | None = None
    mortgage_bps: Share = 0


class EmpireBidRequest(Request):
    limit_kobo: Money
    partner_id: int | None = Field(default=None, ge=1)


class HqRequest(Request):
    property_id: int = Field(ge=1, strict=True)


class LevelsRequest(Request):
    levels: int = Field(ge=1, le=120, strict=True)


class ApproveRequest(Request):
    approve: bool


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------

@app.get("/api/property")
def property_market(player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    """Every district and its property, the Auction House, and what the player (and their empire) own."""
    now = _exchange_time(conn)
    auctions.run(conn, now)
    account = _account(conn, player)
    seat = empires.seat_of(conn, player["id"])
    empire = None
    if seat is not None and seat.get("empire_status") == "active":
        empire = empires._empire(conn, seat["empire_id"])
    market = prop.market_view(conn, viewer=account)
    out = {
        **market,
        "auctions": auctions.view(conn, now, viewer=account, empire_id=empire["id"] if empire else None)["auctions"],
        "mine": prop.mine_view(conn, account, now),
        "mortgage_limit_note": "A bank lends a player at most four years of their salary, and wants a fifth of the price paid up front.",
        "banks": [{"id": str(b["id"]), "name": b["name"]} for b in prop.lending_banks(conn, max(_period(conn, now), 1))],
        "empire": None,
    }
    if empire is not None:
        out["empire"] = {"id": empire["id"], "name": empire["name"], "head": empire["head_player_id"] == player["id"],
                         "build": seat["build"], "property": prop.mine_view(conn, empire["account_id"], now),
                         "auctions": auctions.view(conn, now, viewer=empire["account_id"], empire_id=empire["id"])["auctions"],
                         "checks": {str(a_id): checks for a_id, checks in _empire_checks(conn, empire["id"]).items()}}
    return wire(out)


def _period(conn: Connection, now) -> int:
    from simulation import careers
    return careers.world_now(conn, now)["period"]


def _empire_checks(conn: Connection, empire_id: int) -> dict:
    out: dict = {}
    for r in conn.execute("SELECT auction_id, step, answer FROM property_checks WHERE empire_id = %s", (empire_id,)).fetchall():
        out.setdefault(r["auction_id"], {})[r["step"]] = r["answer"]
    return out


# ---------------------------------------------------------------------------
# Owners
# ---------------------------------------------------------------------------

@app.post("/api/property/{property_id}/upkeep")
def property_upkeep(body: UpkeepRequest, property_id: int = _id(), player: dict = Depends(current_player),
                    conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: prop.set_upkeep(conn, _who(conn, player, body.for_empire), property_id, body.on))


@app.post("/api/property/{property_id}/renovate")
def property_renovate(body: ForRequest, property_id: int = _id(), player: dict = Depends(current_player),
                      conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: prop.renovate(conn, _who(conn, player, body.for_empire), property_id, now))


@app.post("/api/property/{property_id}/build")
def property_build(body: ForRequest, property_id: int = _id(), player: dict = Depends(current_player),
                   conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: prop.build(conn, _who(conn, player, body.for_empire), property_id, now))


@app.post("/api/property/{property_id}/title-search")
def property_title(body: ForRequest, property_id: int = _id(), player: dict = Depends(current_player),
                   conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: prop.title_search(conn, _who(conn, player, body.for_empire), property_id, now))


@app.post("/api/property/{property_id}/sell")
def property_sell(body: SellRequest, property_id: int = _id(), player: dict = Depends(current_player),
                  conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: {"auction_id": auctions.owner_list(conn, _who(conn, player, body.for_empire), property_id,
                                                                             body.reserve_kobo, now)})


@app.post("/api/property/mortgages/{mortgage_id}/repay")
def property_repay(body: RepayRequest, mortgage_id: int = _id(), player: dict = Depends(current_player),
                   conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: prop.repay_mortgage(conn, _who(conn, player, body.for_empire), mortgage_id, body.amount_kobo, now))


# ---------------------------------------------------------------------------
# The Auction House
# ---------------------------------------------------------------------------

@app.post("/api/auctions/{auction_id}/bid")
def auction_bid(body: BidRequest, auction_id: int = _id(), player: dict = Depends(current_player),
                conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: auctions.place_bid(
        conn, _account(conn, player), auction_id, body.limit_kobo, now, player_id=player["id"], partner=body.partner_id,
        mortgage_bank=body.mortgage_bank, mortgage_bps=body.mortgage_bps), bucket="bid")


@app.post("/api/auctions/bids/{bid_id}/withdraw")
def auction_withdraw(body: ForRequest, bid_id: int = _id(), player: dict = Depends(current_player),
                     conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: auctions.withdraw(conn, _who(conn, player, body.for_empire), bid_id, now), bucket="bid")


def _partner_account(conn: Connection, body: PartnerRequest):
    if body.partner_empire_id:
        row = conn.execute("SELECT account_id FROM empires WHERE id = %s AND status = 'active'", (body.partner_empire_id,)).fetchone()
    elif body.partner_player_name:
        row = conn.execute("SELECT a.id AS account_id FROM players p JOIN ledger_accounts a ON a.player_id = p.id WHERE lower(p.display_name) = lower(%s)",
                           (body.partner_player_name,)).fetchone()
    else:
        row = None
    if row is None:
        raise prop.PropertyError("Name a player or an empire to ask.")
    return row["account_id"]


@app.post("/api/auctions/{auction_id}/partners")
def auction_partner(body: PartnerRequest, auction_id: int = _id(), player: dict = Depends(current_player),
                    conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: {"ask_id": auctions.ask_partner(conn, _who(conn, player, body.for_empire), auction_id,
                                                                           _partner_account(conn, body), body.partner_bps, now)})


@app.get("/api/auctions/partners")
def auction_partner_requests(player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    """Requests to share a bid, made to the player (or to their empire, if they are its head)."""
    accounts = [_account(conn, player)]
    seat = empires.seat_of(conn, player["id"])
    if seat is not None:
        empire = empires._empire(conn, seat["empire_id"])
        if empire["head_player_id"] == player["id"]:
            accounts.append(empire["account_id"])
    rows = conn.execute("SELECT p.id, p.auction_id, p.partner_bps, p.status, p.partner, a.name AS asked_by, pr.name AS property"
                        " FROM auction_partners p JOIN ledger_accounts a ON a.id = p.bidder JOIN auctions au ON au.id = p.auction_id"
                        " JOIN properties pr ON pr.id = au.property_id WHERE p.partner = ANY(%s) ORDER BY p.id DESC LIMIT 30",
                        (accounts,)).fetchall()
    return wire({"requests": [{"id": r["id"], "auction_id": r["auction_id"], "partner_bps": r["partner_bps"], "status": r["status"],
                               "property": r["property"], "for_empire": r["partner"] != accounts[0],
                               "asked_by": r["asked_by"] if not r["asked_by"].startswith("Player") else "A player"} for r in rows]})


@app.post("/api/auctions/partners/{ask_id}/answer")
def auction_partner_answer(body: PartnerAnswer, ask_id: int = _id(), player: dict = Depends(current_player),
                           conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: auctions.answer_partner(conn, _who(conn, player, body.for_empire), ask_id, body.agree,
                                                                  body.most_kobo, now))


@app.post("/api/empire/auctions/{auction_id}/check")
def empire_auction_check(body: CheckRequest, auction_id: int = _id(), player: dict = Depends(current_player),
                         conn: Connection = Depends(get_connection)):
    answer = {"value": body.value_kobo, "limit": body.limit_kobo, "bank": str(body.bank) if body.bank else None, "mortgage_bps": body.mortgage_bps}
    return _act(conn, player, lambda now: auctions.check(conn, player["id"], auction_id, body.step, answer, now))


@app.post("/api/empire/auctions/{auction_id}/bid")
def empire_auction_bid(body: EmpireBidRequest, auction_id: int = _id(), player: dict = Depends(current_player),
                       conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: auctions.empire_bid(conn, player["id"], auction_id, body.limit_kobo, now, partner=body.partner_id),
                bucket="bid")


# ---------------------------------------------------------------------------
# Headquarters
# ---------------------------------------------------------------------------

@app.get("/api/empire/headquarters")
def empire_headquarters(player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    try:
        seat, empire = firm._active(conn, player["id"])
    except empires.EmpireError as refused:
        raise HTTPException(status.HTTP_409_CONFLICT, str(refused)) from None
    view = headquarters.view(conn, empire, _exchange_time(conn))
    return wire({**view, "head": empire["head_player_id"] == player["id"], "build": seat["build"]})


@app.post("/api/empire/headquarters")
def empire_headquarters_set(body: HqRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: headquarters.establish(conn, player["id"], body.property_id, now))


@app.post("/api/empire/headquarters/raise")
def empire_headquarters_raise(body: LevelsRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: headquarters.raise_level(conn, player["id"], body.levels, now))


@app.post("/api/empire/headquarters/upkeep/ask")
def empire_headquarters_ask(_: Request, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: headquarters.ask_upkeep(conn, player["id"], now))


@app.post("/api/empire/headquarters/upkeep/approve")
def empire_headquarters_approve(body: ApproveRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: headquarters.approve_upkeep(conn, player["id"], body.approve, now))


@app.post("/api/empire/headquarters/rebuild")
def empire_headquarters_rebuild(_: Request, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: headquarters.rebuild(conn, player["id"], now))
