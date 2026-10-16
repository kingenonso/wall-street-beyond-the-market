"""The gap stage, Part 2: zoning, the twelve-step purchase, claims, valuation, development and property funds.

Every request acts for the player, or (with for_empire) for the empire the server knows the player heads. Money moves
only through the ledger. A buyer's checks are the buyer's own: the seller never sees what they found.
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import Depends, HTTPException, status
from psycopg import Connection
from pydantic import Field

from server import limits
from server.db import get_connection
from server.firm_routes import MONEY, wire
from server.main import _exchange_time, app, current_player
from server.property_routes import ForRequest, Money, _act, _id, _who
from simulation import conveyancing, development, propfunds, propvalue, zoning
from simulation import property as prop

MONEY.update({"comparables", "income", "cost", "land", "rebuild", "yearly_rent", "budget", "permit_fee", "loan_most", "loan_drawn",
              "buildings_value", "my_value", "mortgage", "lent", "defaulted", "book"})


class RezoneRequest(ForRequest):
    to_zone: Literal["residential", "commercial", "industrial", "agricultural", "resource", "mixed"]


class BuildKindRequest(ForRequest):
    kind: Literal["office", "home", "shop", "warehouse", "factory", "farmland", "hotel", "mall"] | None = None


class OfferRequest(ForRequest):
    price_kobo: Money
    buyer_player: str | None = Field(default=None, min_length=1, max_length=60)
    buyer_empire: str | None = Field(default=None, min_length=1, max_length=60)


class SaleCheckRequest(ForRequest):
    step: Literal["seller", "title", "claims", "zoning", "valuation"]


class SaleAcceptRequest(ForRequest):
    mortgage_bank: UUID | None = None
    mortgage_kobo: int = Field(default=0, ge=0, le=1_000_000_000_000_000, strict=True)


class DevelopRequest(ForRequest):
    kind: Literal["office", "home", "shop", "warehouse", "factory", "farmland", "hotel", "mall"] | None = None
    loan_bank: UUID | None = None
    loan_kobo: int = Field(default=0, ge=0, le=1_000_000_000_000_000, strict=True)
    then_what: Literal["let", "sell"] = "let"


class FundOpenRequest(ForRequest):
    name: str = Field(min_length=3, max_length=40)
    fee_bps: int = Field(ge=0, le=200, strict=True)


class FundBuyRequest(ForRequest):
    amount_kobo: Money


class FundSellRequest(ForRequest):
    units: int = Field(gt=0, le=10**15, strict=True)


class FundBidRequest(ForRequest):
    auction_id: int = Field(ge=1, strict=True)
    limit_kobo: Money


class FundListRequest(ForRequest):
    property_id: int = Field(ge=1, strict=True)
    reserve_kobo: int = Field(default=0, ge=0, le=1_000_000_000_000_000, strict=True)


def _fund_act(conn: Connection, player: dict, action) -> dict:
    limits.allow("property", str(player["id"]), attempts=30, per_seconds=60)
    try:
        result = action(_exchange_time(conn))
    except propfunds.FundError as refused:
        raise HTTPException(status.HTTP_409_CONFLICT, str(refused)) from None
    except prop.PropertyError as refused:
        raise HTTPException(status.HTTP_409_CONFLICT, str(refused)) from None
    return {"result": wire(result) if isinstance(result, dict) else result}


# ---------------------------------------------------------------------------
# Zoning, building and claims
# ---------------------------------------------------------------------------

@app.post("/api/property/{property_id}/rezone")
def property_rezone(body: RezoneRequest, property_id: int = _id(), player: dict = Depends(current_player),
                    conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: zoning.ask(conn, _who(conn, player, body.for_empire), property_id, body.to_zone, now))


@app.post("/api/property/{property_id}/build-kind")
def property_build_kind(body: BuildKindRequest, property_id: int = _id(), player: dict = Depends(current_player),
                        conn: Connection = Depends(get_connection)):
    """Put up a building at once (a builder's turnkey price), choosing what kind the zone allows."""
    return _act(conn, player, lambda now: prop.build(conn, _who(conn, player, body.for_empire), property_id, now, kind=body.kind))


@app.post("/api/property/{property_id}/claims-search")
def property_claims_search(body: ForRequest, property_id: int = _id(), player: dict = Depends(current_player),
                           conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: conveyancing.claims_search(conn, _who(conn, player, body.for_empire), property_id, now))


@app.post("/api/property/{property_id}/settle-dispute")
def property_settle(body: ForRequest, property_id: int = _id(), player: dict = Depends(current_player),
                    conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: conveyancing.settle_dispute(conn, _who(conn, player, body.for_empire), property_id, now))


@app.get("/api/property/{property_id}/valuation")
def property_valuation(property_id: int = _id(), _: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    """A property valued three ways, from public figures only."""
    try:
        return wire(propvalue.three_ways(conn, property_id))
    except prop.PropertyError:
        raise HTTPException(status_code=404, detail="There is no such property.") from None


# ---------------------------------------------------------------------------
# The twelve-step purchase
# ---------------------------------------------------------------------------

@app.post("/api/property/{property_id}/offer")
def property_offer(body: OfferRequest, property_id: int = _id(), player: dict = Depends(current_player),
                   conn: Connection = Depends(get_connection)):
    who = {"player": body.buyer_player} if body.buyer_player else {"empire": body.buyer_empire} if body.buyer_empire else {}
    return _act(conn, player, lambda now: conveyancing.offer(conn, _who(conn, player, body.for_empire), property_id, who, body.price_kobo, now,
                                                             offered_by=player["id"]))


@app.post("/api/property/sales/{sale_id}/check")
def property_sale_check(body: SaleCheckRequest, sale_id: int = _id(), player: dict = Depends(current_player),
                        conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: conveyancing.check(conn, _who(conn, player, body.for_empire), sale_id, body.step, now))


@app.post("/api/property/sales/{sale_id}/accept")
def property_sale_accept(body: SaleAcceptRequest, sale_id: int = _id(), player: dict = Depends(current_player),
                         conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: conveyancing.accept(conn, _who(conn, player, body.for_empire), sale_id, now,
                                                              mortgage_bank=body.mortgage_bank, mortgage=body.mortgage_kobo))


@app.post("/api/property/sales/{sale_id}/consent")
def property_sale_consent(body: ForRequest, sale_id: int = _id(), player: dict = Depends(current_player),
                          conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: conveyancing.ask_consent(conn, _who(conn, player, body.for_empire), sale_id, now))


@app.post("/api/property/sales/{sale_id}/sign")
def property_sale_sign(body: ForRequest, sale_id: int = _id(), player: dict = Depends(current_player),
                       conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: conveyancing.sign(conn, _who(conn, player, body.for_empire), sale_id, now))


@app.post("/api/property/sales/{sale_id}/decline")
def property_sale_decline(body: ForRequest, sale_id: int = _id(), player: dict = Depends(current_player),
                          conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: conveyancing.decline(conn, _who(conn, player, body.for_empire), sale_id, now))


# ---------------------------------------------------------------------------
# Development
# ---------------------------------------------------------------------------

@app.post("/api/property/{property_id}/develop")
def property_develop(body: DevelopRequest, property_id: int = _id(), player: dict = Depends(current_player),
                     conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: development.start(conn, _who(conn, player, body.for_empire), property_id, body.kind, now,
                                                            loan_bank=body.loan_bank, loan=body.loan_kobo, then_what=body.then_what))


# ---------------------------------------------------------------------------
# Property funds
# ---------------------------------------------------------------------------

@app.get("/api/property-funds")
def property_funds(player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    from simulation import ledger
    account = ledger.player_account_id(conn, player["id"])
    mine = conn.execute("SELECT id FROM property_funds WHERE manager = %s AND status = 'open'", (player["id"],)).fetchone()
    return wire({"funds": propfunds.listing(conn, account), "managed": mine["id"] if mine else None,
                 "open_level": propfunds.data.PROPERTY_FUND_LEVEL, "fee_most_bps": propfunds.data.PROPERTY_FUND_FEE_MOST_BPS})


@app.post("/api/property-funds")
def property_fund_open(body: FundOpenRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _fund_act(conn, player, lambda now: propfunds.open_fund(conn, player["id"], body.name, body.fee_bps, now))


@app.post("/api/property-funds/{fund_id}/buy")
def property_fund_buy(body: FundBuyRequest, fund_id: int = _id(), player: dict = Depends(current_player),
                      conn: Connection = Depends(get_connection)):
    return _fund_act(conn, player, lambda now: propfunds.buy_units(conn, _who(conn, player, body.for_empire), fund_id, body.amount_kobo, now))


@app.post("/api/property-funds/{fund_id}/sell")
def property_fund_sell(body: FundSellRequest, fund_id: int = _id(), player: dict = Depends(current_player),
                       conn: Connection = Depends(get_connection)):
    return _fund_act(conn, player, lambda now: propfunds.sell_units(conn, _who(conn, player, body.for_empire), fund_id, body.units, now))


@app.post("/api/property-funds/managed/bid")
def property_fund_bid(body: FundBidRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _fund_act(conn, player, lambda now: propfunds.bid(conn, player["id"], body.auction_id, body.limit_kobo, now))


@app.post("/api/property-funds/managed/list")
def property_fund_list(body: FundListRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _fund_act(conn, player, lambda now: {"auction_id": propfunds.sell(conn, player["id"], body.property_id, body.reserve_kobo, now)})
