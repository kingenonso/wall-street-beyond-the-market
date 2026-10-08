"""Private equity stage, part 2A: buying, running and selling private companies.

As with the firm, every request acts as the logged-in player only; the server works out their
empire and desk. Money arrives as whole kobo and leaves as text. The truth behind a check, a
company's secrets and a seller's lowest price never leave the server.
"""

from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from fastapi import Depends, Query
from psycopg import Connection
from pydantic import Field

from server import limits
from server.db import get_connection
from server.firm_routes import MONEY, Kobo, _do, _id, wire
from server.main import app, current_player
from server.schemas import Request
from simulation import firm_deals, firm_owned

MONEY.update({"asking", "highest", "valuation", "equity", "loan", "charge", "held", "proceeds", "book", "escrow", "gain", "revenue",
              "operating_profit", "net_profit", "depreciation", "interest_expense", "borrowings", "payables", "total_equity", "fixed_assets",
              "marketing", "technology", "borrow", "unit_cost", "capacity", "buyer_offer", "households", "business", "government",
              "dividends_paid", "fairness_above", "per_share", "pay", "fee_most"})
Whole = Annotated[int, Field(ge=0, le=1_000_000_000_000_000, strict=True)]
Bps = Annotated[int, Field(ge=0, le=20_000, strict=True)]
CITY = Literal["Lagos", "Abuja", "Port Harcourt", "Aba", "Kano"]


class AnswersRequest(Request):
    answers: dict[Annotated[str, Field(max_length=40)], int | float | str | list[str]] = Field(max_length=10)


class TermsRequest(Request):
    changes: dict[Annotated[str, Field(max_length=40)], Literal["strike", "keep", "ask", "drop"]] = Field(max_length=20)


class SellerAnswersRequest(Request):
    answers: dict[Annotated[str, Field(max_length=40)], bool] = Field(max_length=20)


class PartnerRequest(Request):
    empire_id: int = Field(ge=1, le=9_000_000_000_000_000_000)
    amount_kobo: Kobo


class AcceptRequest(Request):
    accept: bool


class BidRequest(Request):
    amount_kobo: Kobo
    loan_kobo: Whole = 0


class ClaimRequest(Request):
    code: Literal["dressed_revenue", "hidden_debt", "worn_assets", "ownership_claim"]


class DialsRequest(Request):
    price_bps: Bps
    staff_bps: Bps
    pay_rise_bps: Bps
    marketing: Whole
    technology: Whole
    maintenance_bps: Bps
    payout_bps: Bps
    borrow: Whole
    buy_assets: int = Field(ge=0, le=10, strict=True)


class ManagerRequest(Request):
    n: int = Field(ge=0, le=2, strict=True)


class RouteRequest(Request):
    city_a: CITY
    city_b: CITY


class FareRequest(Request):
    fare_bps: Bps


class PlaneRequest(Request):
    route_id: int | None = Field(default=None, ge=1, le=9_000_000_000_000_000_000)


class PlanRequest(Request):
    code: Literal["suppliers", "head_office", "rebrand", "systems", "fix_assets", "pricing"]


class RescueRequest(Request):
    company_id: UUID
    measures: list[Literal["cut_costs", "sell_grounded", "skip_dividends", "extend_loans"]] = Field(min_length=1, max_length=4)
    fee_kobo: Whole


class SaleRequest(Request):
    asking_kobo: Kobo
    reserve_kobo: Kobo
    mode: Literal["sealed", "auction"]
    adviser_firm_id: int | None = Field(default=None, ge=1, le=9_000_000_000_000_000_000, strict=True)


class ListRequest(Request):
    underwriter_firm_id: int | None = Field(default=None, ge=1, le=9_000_000_000_000_000_000, strict=True)


# --- Finding and buying -------------------------------------------------------

@app.post("/api/deals/{process_id}/file", status_code=201)
def bring_a_deal(process_id: int = _id(), player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _do(conn, player, lambda now: firm_deals.open_file(conn, player["id"], process_id, now), "deals", 20)


@app.post("/api/deals/files/{file_id}/nda")
def sign_a_confidentiality_agreement(file_id: int = _id(), player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _do(conn, player, lambda now: firm_deals.sign_nda(conn, player["id"], file_id, now), "deals", 20)


@app.post("/api/deals/steps/{step_id}/open")
def open_a_check(step_id: int = _id(), player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _do(conn, player, lambda now: firm_deals.open_step(conn, player["id"], step_id, now), "deals", 30)


@app.post("/api/deals/steps/{step_id}/hand-in")
def hand_in_a_check(body: AnswersRequest, step_id: int = _id(), player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _do(conn, player, lambda now: firm_deals.hand_in_step(conn, player["id"], step_id, body.answers, now), "deals", 20)


@app.put("/api/deals/files/{file_id}/terms")
def argue_the_agreement(body: TermsRequest, file_id: int = _id(), player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _do(conn, player, lambda now: firm_deals.mark_terms(conn, player["id"], file_id, body.changes, now), "deals", 20)


@app.put("/api/deals/{process_id}/terms/{empire_id}")
def answer_a_buyer(body: SellerAnswersRequest, process_id: int = _id(), empire_id: int = _id(), player: dict = Depends(current_player),
                   conn: Connection = Depends(get_connection)):
    return _do(conn, player, lambda now: firm_deals.answer_terms(conn, player["id"], process_id, empire_id, body.answers, now), "deals", 20)


@app.post("/api/deals/files/{file_id}/partners", status_code=201)
def invite_a_partner(body: PartnerRequest, file_id: int = _id(), player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _do(conn, player, lambda now: firm_deals.invite_partner(conn, player["id"], file_id, body.empire_id, body.amount_kobo, now), "deals", 10)


@app.put("/api/deals/partners/{partner_id}")
def answer_an_invitation(body: AcceptRequest, partner_id: int = _id(), player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _do(conn, player, lambda now: firm_deals.answer_partner(conn, player["id"], partner_id, body.accept, now), "deals", 10)


@app.post("/api/deals/files/{file_id}/bid")
def place_a_bid(body: BidRequest, file_id: int = _id(), player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _do(conn, player, lambda now: firm_deals.place_bid(conn, player["id"], file_id, body.amount_kobo, body.loan_kobo, now), "deals", 10)


@app.delete("/api/deals/files/{file_id}/bid")
def withdraw_a_bid(file_id: int = _id(), player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _do(conn, player, lambda now: firm_deals.withdraw_bid(conn, player["id"], file_id, now), "deals", 10)


@app.post("/api/deals/{deal_id}/claims")
def claim_against_the_seller(body: ClaimRequest, deal_id: int = _id(), player: dict = Depends(current_player),
                             conn: Connection = Depends(get_connection)):
    return _do(conn, player, lambda now: firm_deals.claim(conn, player["id"], deal_id, body.code, now), "deals", 10)


@app.get("/api/deals/league")
def the_deal_league(year: int | None = Query(default=None, ge=1, le=500), player: dict = Depends(current_player),
                    conn: Connection = Depends(get_connection)):
    limits.allow("firm-read", str(player["id"]), attempts=120, per_seconds=60)
    return wire(firm_owned.league_tables(conn, year))


# --- Running a company --------------------------------------------------------

@app.put("/api/owned/{company_id}/dials")
def set_the_dials(company_id: UUID, body: DialsRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _do(conn, player, lambda now: firm_owned.set_dials(conn, player["id"], company_id, body.model_dump(), now), "owned", 20)


@app.post("/api/owned/assets/{asset_id}/sell")
def sell_an_asset(asset_id: int = _id(), player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _do(conn, player, lambda now: firm_owned.sell_asset(conn, player["id"], asset_id, now), "owned", 20)


@app.post("/api/owned/assets/{asset_id}/repair")
def repair_an_asset(asset_id: int = _id(), player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _do(conn, player, lambda now: firm_owned.repair(conn, player["id"], asset_id, now), "owned", 20)


@app.put("/api/owned/assets/{asset_id}/route")
def put_a_plane_on_a_route(body: PlaneRequest, asset_id: int = _id(), player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _do(conn, player, lambda now: firm_owned.assign_plane(conn, player["id"], asset_id, body.route_id, now), "owned", 30)


@app.put("/api/owned/{company_id}/manager")
def hire_a_manager(company_id: UUID, body: ManagerRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _do(conn, player, lambda now: firm_owned.hire_manager(conn, player["id"], company_id, body.n, now), "owned", 10)


@app.post("/api/owned/{company_id}/routes", status_code=201)
def open_a_route(company_id: UUID, body: RouteRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _do(conn, player, lambda now: firm_owned.open_route(conn, player["id"], company_id, body.city_a, body.city_b, now), "owned", 20)


@app.delete("/api/owned/routes/{route_id}")
def close_a_route(route_id: int = _id(), player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _do(conn, player, lambda now: firm_owned.close_route(conn, player["id"], route_id, now), "owned", 20)


@app.put("/api/owned/routes/{route_id}/fare")
def set_a_fare(body: FareRequest, route_id: int = _id(), player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _do(conn, player, lambda now: firm_owned.set_fare(conn, player["id"], route_id, body.fare_bps, now), "owned", 30)


@app.post("/api/owned/{company_id}/plans", status_code=201)
def start_part_of_the_plan(company_id: UUID, body: PlanRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _do(conn, player, lambda now: firm_owned.start_plan(conn, player["id"], company_id, body.code, now), "owned", 10)


@app.post("/api/owned/{company_id}/sell")
def put_a_company_up_for_sale(company_id: UUID, body: SaleRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _do(conn, player, lambda now: firm_owned.sell_to_empire(conn, player["id"], company_id, body.asking_kobo, body.reserve_kobo,
                                                                   body.mode, now, body.adviser_firm_id), "owned", 10)


@app.post("/api/owned/{company_id}/sell-to-buyer")
def sell_to_the_buyer(company_id: UUID, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _do(conn, player, lambda now: firm_owned.sell_to_buyer(conn, player["id"], company_id, now), "owned", 10)


@app.post("/api/owned/{company_id}/list")
def list_a_company(company_id: UUID, body: ListRequest | None = None, player: dict = Depends(current_player),
                   conn: Connection = Depends(get_connection)):
    underwriter = body.underwriter_firm_id if body else None
    return _do(conn, player, lambda now: firm_owned.list_on_exchange(conn, player["id"], company_id, now, underwriter), "owned", 10)


# --- The company doctor -------------------------------------------------------

@app.get("/api/rescues")
def companies_in_trouble(player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    limits.allow("firm-read", str(player["id"]), attempts=120, per_seconds=60)
    return wire({"companies": firm_owned.doctor_view(conn, player["id"]),
                 "measures": {k: {"title": v[0], "words": v[1]} for k, v in firm_owned.RESCUE.items()}})


@app.post("/api/rescues", status_code=201)
def offer_a_rescue(body: RescueRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _do(conn, player, lambda now: firm_owned.propose_rescue(conn, player["id"], body.company_id, list(body.measures), body.fee_kobo, now),
               "rescues", 10)


@app.put("/api/rescues/{plan_id}")
def answer_a_rescue(body: AcceptRequest, plan_id: int = _id(), player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _do(conn, player, lambda now: firm_owned.answer_rescue(conn, player["id"], plan_id, body.accept, now), "rescues", 10)
