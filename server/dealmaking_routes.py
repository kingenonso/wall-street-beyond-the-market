"""Private equity stage, part 2B: firms players found, and the deal-making between empires.

Every request acts as the logged-in player only; the server works out their empire, desk and firm. The
truth behind a job or a defence, and other empires' private figures, never leave the server.
"""

from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from fastapi import Depends
from psycopg import Connection
from pydantic import Field

from server import limits
from server.db import get_connection
from server.deal_routes import AcceptRequest, AnswersRequest
from server.firm_routes import MONEY, Kobo, _do, _id, wire
from server.main import app, current_player
from server.schemas import Request
from simulation import firm, firm_dealmaking, firm_practice

MONEY.update({"capital", "bank_capital_least", "most_price", "defence_value", "cash"})
Id = Annotated[int, Field(ge=1, le=9_000_000_000_000_000_000, strict=True)]
Count = Annotated[int, Field(gt=0, le=1_000_000_000_000_000, strict=True)]


class FoundRequest(Request):
    kind: Literal["audit", "risk", "advisory", "bank"]
    name: str = Field(min_length=3, max_length=60)
    capital_kobo: int = Field(default=0, ge=0, le=1_000_000_000_000_000, strict=True)


class SendRequest(Request):
    firm_id: Id
    fee_kobo: Kobo


class RestructureRequest(Request):
    company_id: UUID
    fee_kobo: int = Field(ge=0, le=1_000_000_000_000_000, strict=True)


class LoanOfferRequest(Request):
    empire_id: Id
    amount_kobo: Kobo
    rate_bps: int = Field(ge=1, le=6000, strict=True)
    quarters: int = Field(ge=1, le=20, strict=True)


class AmountRequest(Request):
    amount_kobo: Kobo


class OfferRequest(Request):
    company_id: UUID
    price_kobo: Kobo
    shares: Count


class TenderRequest(Request):
    shares: int = Field(ge=0, le=1_000_000_000_000_000, strict=True)


class StakeRequest(Request):
    company_id: UUID
    target_bps: int = Field(ge=100, le=2999, strict=True)
    most_price_kobo: Kobo


class BlockRequest(Request):
    buyer_empire_id: Id
    company_id: UUID
    shares: Count
    price_kobo: Kobo


class MergerRequest(Request):
    other_empire_id: Id


class JoinRequest(Request):
    combination_id: Id


class SpinoffRequest(Request):
    company_id: UUID
    new_name: str = Field(min_length=3, max_length=40)
    new_head: UUID
    cash_kobo: int = Field(default=0, ge=0, le=1_000_000_000_000_000, strict=True)


# --- Firms players found ------------------------------------------------------

@app.get("/api/firms")
def the_firms(player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    limits.allow("firm-read", str(player["id"]), attempts=120, per_seconds=60)
    return wire({"firms": firm_practice.firms(conn)})


@app.post("/api/firms", status_code=201)
def found_a_firm(body: FoundRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _do(conn, player, lambda now: firm_practice.found(conn, player["id"], body.kind, body.name, body.capital_kobo, now), "firms", 5)


@app.post("/api/firms/jobs/{job_id}/open")
def open_a_job(job_id: int = _id(), player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _do(conn, player, lambda now: firm_practice.open_job(conn, player["id"], job_id, now), "firms", 30)


@app.post("/api/firms/jobs/{job_id}/hand-in")
def hand_in_a_job(body: AnswersRequest, job_id: int = _id(), player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _do(conn, player, lambda now: firm_practice.hand_in_job(conn, player["id"], job_id, body.answers, now), "firms", 20)


@app.post("/api/firms/jobs/{job_id}/accept")
def stand_behind_a_listing(job_id: int = _id(), player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _do(conn, player, lambda now: firm_practice.accept_underwriting(conn, player["id"], job_id, now), "firms", 10)


@app.post("/api/deals/steps/{step_id}/send")
def send_a_check_out(body: SendRequest, step_id: int = _id(), player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _do(conn, player, lambda now: firm_practice.send_step(conn, player["id"], step_id, body.firm_id, body.fee_kobo, now), "firms", 10)


@app.post("/api/owned/{company_id}/audit")
def have_a_company_audited(company_id: UUID, body: SendRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _do(conn, player, lambda now: firm_practice.commission_audit(conn, player["id"], company_id, body.firm_id, body.fee_kobo, now), "firms", 10)


@app.post("/api/firms/restructurings")
def offer_a_restructuring(body: RestructureRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _do(conn, player, lambda now: firm_practice.propose_restructuring(conn, player["id"], body.company_id, body.fee_kobo, now), "firms", 10)


@app.post("/api/firms/loans")
def offer_a_loan(body: LoanOfferRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _do(conn, player, lambda now: firm_practice.offer_loan(conn, player["id"], body.empire_id, body.amount_kobo, body.rate_bps, body.quarters, now),
               "firms", 10)


@app.put("/api/firms/loans/{offer_id}")
def answer_a_loan(body: AcceptRequest, offer_id: int = _id(), player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _do(conn, player, lambda now: firm_practice.answer_loan(conn, player["id"], offer_id, body.accept, now), "firms", 10)


@app.post("/api/firms/pay-out")
def pay_out_a_banks_profit(body: AmountRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _do(conn, player, lambda now: firm_practice.pay_out(conn, player["id"], body.amount_kobo, now), "firms", 5)


# --- Takeovers, stakes and blocks ---------------------------------------------

@app.post("/api/takeovers", status_code=201)
def draft_a_takeover_offer(body: OfferRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _do(conn, player, lambda now: firm_dealmaking.draft_offer(conn, player["id"], body.company_id, body.price_kobo, body.shares, now), "deals", 10)


@app.put("/api/takeovers/{takeover_id}/tender")
def offer_the_empires_shares(body: TenderRequest, takeover_id: int = _id(), player: dict = Depends(current_player),
                             conn: Connection = Depends(get_connection)):
    return _do(conn, player, lambda now: firm_dealmaking.tender(conn, player["id"], takeover_id, body.shares, now), "deals", 20)


@app.post("/api/takeovers/{takeover_id}/defence/open")
def open_the_defence(takeover_id: int = _id(), player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _do(conn, player, lambda now: firm_dealmaking.open_defence(conn, player["id"], takeover_id, now), "deals", 20)


@app.post("/api/takeovers/{takeover_id}/defence/hand-in")
def hand_in_the_defence(body: AnswersRequest, takeover_id: int = _id(), player: dict = Depends(current_player),
                        conn: Connection = Depends(get_connection)):
    return _do(conn, player, lambda now: firm_dealmaking.hand_in_defence(conn, player["id"], takeover_id, body.answers, now), "deals", 10)


@app.post("/api/stakes", status_code=201)
def build_a_stake(body: StakeRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _do(conn, player, lambda now: firm_dealmaking.start_stake(conn, player["id"], body.company_id, body.target_bps, body.most_price_kobo, now),
               "deals", 10)


@app.delete("/api/stakes/{programme_id}")
def stop_building_a_stake(programme_id: int = _id(), player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _do(conn, player, lambda now: firm_dealmaking.stop_stake(conn, player["id"], programme_id, now), "deals", 10)


@app.post("/api/blocks", status_code=201)
def offer_a_block(body: BlockRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _do(conn, player, lambda now: firm_dealmaking.offer_block(conn, player["id"], body.buyer_empire_id, body.company_id, body.shares,
                                                                     body.price_kobo, now), "deals", 10)


@app.put("/api/blocks/{block_id}")
def answer_a_block(body: AcceptRequest, block_id: int = _id(), player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _do(conn, player, lambda now: firm_dealmaking.answer_block(conn, player["id"], block_id, body.accept, now), "deals", 10)


@app.delete("/api/blocks/{block_id}")
def withdraw_a_block(block_id: int = _id(), player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _do(conn, player, lambda now: firm_dealmaking.withdraw_block(conn, player["id"], block_id, now), "deals", 10)


@app.post("/api/owned/{company_id}/consulting")
def pay_yourself_consulting_fees(company_id: UUID, body: AmountRequest, player: dict = Depends(current_player),
                                 conn: Connection = Depends(get_connection)):
    return _do(conn, player, lambda now: firm_dealmaking.take_from_company(conn, player["id"], company_id, body.amount_kobo, now), "shadow", 10)


# --- Mergers and spin-offs (put to the members' vote) ------------------------

@app.post("/api/combinations/merger", status_code=201)
def propose_a_merger(body: MergerRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _do(conn, player, lambda now: firm.propose(conn, player["id"], "merger", {"other_empire_id": body.other_empire_id}, now) and None,
               "firm-vote", 5)


@app.post("/api/combinations/join", status_code=201)
def propose_joining(body: JoinRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _do(conn, player, lambda now: firm.propose(conn, player["id"], "merger_join", {"combination_id": body.combination_id}, now) and None,
               "firm-vote", 5)


@app.post("/api/combinations/spinoff", status_code=201)
def propose_a_spinoff(body: SpinoffRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    payload = {"company_id": str(body.company_id), "new_name": body.new_name, "new_head": str(body.new_head), "cash": body.cash_kobo}
    return _do(conn, player, lambda now: firm.propose(conn, player["id"], "spinoff", payload, now) and None, "firm-vote", 5)


class SellRequest(Request):
    quantity: Count
    limit_price_kobo: Kobo


@app.post("/api/firms/holdings/{company_id}/sell")
def sell_a_banks_shares(company_id: UUID, body: SellRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _do(conn, player, lambda now: firm_practice.sell_holding(conn, player["id"], company_id, body.quantity, body.limit_price_kobo, now) and None,
               "firms", 20)
