"""Private equity stage, part 1: the empire as a working firm.

Every request acts as the logged-in player and nobody else: the server works out their empire and
desk from its own records. Amounts of money arrive as whole kobo; amounts the server sends are
text, so that no figure is ever rounded on the way.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi import Path as FastPath
from psycopg import Connection
from psycopg.errors import DeadlockDetected
from pydantic import Field

from server import limits
from server.db import get_connection
from server.empire_routes import Words
from server.main import _exchange_time, app, current_player
from server.schemas import Request
from simulation import careers, empires, exchange, firm
from simulation import firm_clients, firm_money, firm_people, firm_risk, firm_tasks

MONEY = {"owned", "owed", "borrow_room", "principal", "outstanding", "interest_a_quarter", "value", "unit_price", "wanted", "raised", "opening",
         "closing", "cash", "shares", "bonds", "debt", "capital_in", "paid_out", "total_costs", "income_received", "profit", "dividend_room",
         "budget", "spent", "expense_threshold", "loan_least", "bond_least", "total", "amount", "cost", "covered", "cover", "claimed", "premium",
         "most", "bonus", "matched", "fee", "to_empire", "fee_least", "fee_most", "owed_now", "owed_after", "offer", "price", "loss", "reference", "worth", "paid", "start_worth", "payout"}
BUILD = Literal["investment_banker", "asset_manager", "risk_manager"]
DESK = Literal["investment_banker", "asset_manager", "risk_manager", "head"]
Kobo = Annotated[int, Field(gt=0, le=1_000_000_000_000_000, strict=True)]


def _id():
    return FastPath(ge=1, le=9_000_000_000_000_000_000)


def wire(value, key: str | None = None):
    if isinstance(value, dict):
        if {"label", "value", "kind"} <= set(value) and isinstance(value["value"], int) and not isinstance(value["value"], bool):
            return {**value, "value": str(value["value"])}
        out = {}
        for k, item in value.items():
            if k == "costs" and isinstance(item, dict):
                out[k] = {c: str(a) for c, a in item.items()}
            else:
                out[k] = wire(item, k)
        return out
    if isinstance(value, (list, tuple)):
        return [wire(item, key) for item in value]
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if key in MONEY and isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    return value


def _view(conn: Connection, player: dict) -> dict:
    now = _exchange_time(conn)
    return {"firm": wire(firm.view(conn, player["id"], now)), "stake_offers": wire(firm_money.stake_offers(conn, now)),
            "bookkeeping": wire(firm_clients.view(conn, player["id"], now))}


def _do(conn: Connection, player: dict, action, bucket: str = "firm", attempts: int = 40) -> dict:
    limits.allow(bucket, str(player["id"]), attempts=attempts, per_seconds=60)
    try:
        result = action(_exchange_time(conn))
    except (empires.EmpireError, careers.CareerError) as refused:
        raise HTTPException(status.HTTP_409_CONFLICT, str(refused)) from None
    except exchange.EngineFailure:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "The exchange cannot take orders at this moment. Nothing was changed.") from None
    except DeadlockDetected:
        raise HTTPException(status.HTTP_409_CONFLICT, "Somebody else changed this at the same moment. Nothing was changed. Please try again.") from None
    view = _view(conn, player)
    view["result"] = wire(result) if isinstance(result, dict) else None
    return view


# ---------------------------------------------------------------------------
# What the website sends
# ---------------------------------------------------------------------------

Seat = Annotated[int, Field(ge=1, le=9_000_000_000_000_000_000, strict=True)]


def _member(conn: Connection, seat_id: int | None):
    return firm.seat_holder(conn, seat_id)["player_id"] if seat_id is not None else None


class TitleRequest(Request):
    seat_id: Seat
    title: Literal["deputy", "lead"]


class DecisionRequest(Request):
    approve: bool
    reason: Words = Field(default="", max_length=400)


class ReasonRequest(Request):
    reason: Words = Field(min_length=1, max_length=400)


class ProposalRequest(Request):
    kind: Literal["dividend", "treasury", "risk_appetite", "constitution", "conduct", "pension_plan"]
    amount_kobo: int | None = Field(default=None, gt=0, le=1_000_000_000_000_000, strict=True)
    cash_least_bps: int | None = Field(default=None, ge=0, le=5000, strict=True)
    shares_most_bps: int | None = Field(default=None, ge=0, le=10_000, strict=True)
    worst_year_bps: int | None = Field(default=None, ge=100, le=5000, strict=True)
    big_votes: Literal["majority", "two_thirds"] | None = None
    member_signing_naira: int | None = Field(default=None, ge=0, le=100_000_000, strict=True)
    leaver_units: Literal["keep", "buy_back"] | None = None
    theft: Literal["head_decides", "always_punish"] | None = None
    missed_duty_fine_naira: int | None = Field(default=None, ge=0, le=1_000_000, strict=True)
    fund_id: int | None = Field(default=None, ge=1, le=9_000_000_000_000_000_000, strict=True)


class VoteRequest(Request):
    yes: bool


class AnswersRequest(Request):
    answers: dict[str, int | float | str | list[str]] = Field(max_length=12)


class AssignRequest(Request):
    seat_id: Seat | None = None


class StrikeRequest(Request):
    struck: list[Annotated[str, Field(max_length=40)]] = Field(max_length=40)


class RaiseRequest(Request):
    kind: Literal["loan", "bond", "stake"]
    amount_kobo: Kobo
    quarters: Literal[0, 4, 8] = 0


class StakeRequest(Request):
    amount_kobo: Kobo


class BudgetsRequest(Request):
    budgets: dict[DESK, Annotated[int, Field(ge=0, le=1_000_000_000_000_000, strict=True)]] = Field(min_length=1, max_length=7)


class TrainingRequest(Request):
    amount_kobo: Kobo
    seat_id: Seat | None = None


class BonusPoolRequest(Request):
    shares: dict[str, Kobo] = Field(min_length=1, max_length=12)          # seat number -> amount


class ContractRequest(Request):
    seat_id: Seat
    notice_days: int = Field(ge=0, le=14, strict=True)
    bonus_bps: int = Field(ge=0, le=2000, strict=True)
    non_compete: int = Field(ge=0, le=2, strict=True)


class SignRequest(Request):
    sign: bool


class MemberRequest(Request):
    seat_id: Seat


class PoachRequest(Request):
    seat_id: Seat
    bonus_kobo: Kobo
    words: Words = Field(default="", max_length=400)


class MatchRequest(Request):
    bonus_kobo: Kobo


class GoRequest(Request):
    go: bool


class HireRequest(Request):
    adviser_key: str = Field(pattern=r"^[0-9]{8}$")
    fee_kobo: Kobo


class DeliverRequest(Request):
    net_kobo: int = Field(ge=-1_000_000_000_000_000, le=1_000_000_000_000_000, strict=True)
    biggest: Words = Field(min_length=1, max_length=60)
    note: Words = Field(default="", max_length=400)


class RatingRequest(Request):
    stars: int = Field(ge=1, le=5, strict=True)


class StrategyRequest(Request):
    choice: Literal["grow", "income", "takeovers", "safe"]
    growth_bps: int = Field(ge=-5000, le=20000, strict=True)
    payout_kobo: int = Field(ge=0, le=1_000_000_000_000_000, strict=True)
    tasks: int = Field(ge=0, le=12, strict=True)


class TaskRequest(Request):
    kind: Literal["investment", "rescue", "defend", "raise_money"]
    priority: int = Field(ge=1, le=3, strict=True)


class PriorityRequest(Request):
    priority: int = Field(ge=1, le=3, strict=True)


class DefenceRequest(Request):
    choice: Literal["hold", "sell"]
    reason: Words = Field(min_length=1, max_length=300)


class PickRequest(Request):
    company_id: UUID


class RivalRequest(Request):
    empire_id: int = Field(ge=1, le=9_000_000_000_000_000_000, strict=True)


class EventAnswerRequest(Request):
    desk: DESK
    choice: str | int = Field(union_mode="left_to_right")


class CoverRequest(Request):
    kind: Literal["holding_collapse", "inspection"]
    insurer_id: UUID
    cover_kobo: Kobo


class TradeLimitRequest(Request):
    limit_naira: int | None = Field(default=None, gt=0, le=100_000_000_000, strict=True)


class FreezeRequest(Request):
    seat_id: Seat
    frozen: bool
    reason: Words = Field(min_length=1, max_length=300)


# ---------------------------------------------------------------------------
# The firm
# ---------------------------------------------------------------------------

@app.get("/api/firm")
def my_firm(player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    limits.allow("firm-read", str(player["id"]), attempts=120, per_seconds=60)
    return _view(conn, player)


@app.put("/api/firm/titles")
def name_a_title(body: TitleRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _do(conn, player, lambda now: firm.name_title(conn, player["id"], _member(conn, body.seat_id), body.title, now))


@app.put("/api/firm/requests/{approval_id}")
def decide_a_request(body: DecisionRequest, approval_id: int = _id(), player: dict = Depends(current_player),
                     conn: Connection = Depends(get_connection)):
    return _do(conn, player, lambda now: firm.decide(conn, player["id"], approval_id, body.approve, body.reason, now))


@app.post("/api/firm/requests/{approval_id}/overrule")
def overrule_a_refusal(body: ReasonRequest, approval_id: int = _id(), player: dict = Depends(current_player),
                       conn: Connection = Depends(get_connection)):
    return _do(conn, player, lambda now: firm.overrule(conn, player["id"], approval_id, body.reason, now))


@app.post("/api/firm/votes", status_code=status.HTTP_201_CREATED)
def put_to_the_vote(body: ProposalRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    payload = {k: v for k, v in body.model_dump().items() if k != "kind" and v is not None}
    if "amount_kobo" in payload:
        payload["amount"] = payload.pop("amount_kobo")
    return _do(conn, player, lambda now: firm.propose(conn, player["id"], body.kind, payload, now) and None, "firm-vote", 10)


@app.put("/api/firm/votes/{resolution_id}")
def cast_a_vote(body: VoteRequest, resolution_id: int = _id(), player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _do(conn, player, lambda now: firm.vote(conn, player["id"], resolution_id, body.yes, now), "firm-vote", 20)


@app.delete("/api/firm/votes/{resolution_id}")
def withdraw_a_vote(resolution_id: int = _id(), player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _do(conn, player, lambda now: firm.withdraw(conn, player["id"], resolution_id, now), "firm-vote", 10)


@app.post("/api/firm/duties/{duty_id}/open")
def open_a_duty(duty_id: int = _id(), player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _do(conn, player, lambda now: firm.open_duty(conn, player["id"], duty_id, now))


@app.post("/api/firm/duties/{duty_id}/hand-in")
def hand_in_a_duty(body: AnswersRequest, duty_id: int = _id(), player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    answers = {k: v for k, v in body.answers.items()}
    for key, value in answers.items():
        if isinstance(value, float) and not (-1_000_000 < value < 1_000_000):
            raise HTTPException(422, "A percentage must be a sensible figure.")
        if isinstance(value, str) and (len(value) > 600 or any(ord(c) < 32 for c in value)):
            raise HTTPException(422, "That text cannot be kept.")
        if isinstance(value, list) and (len(value) > 40 or any(len(v) > 60 for v in value)):
            raise HTTPException(422, "Too many picks.")
    return _do(conn, player, lambda now: firm.hand_in(conn, player["id"], duty_id, answers, now), "firm-duty", 20)


@app.put("/api/firm/duties/{duty_id}/given-to")
def give_a_duty(body: AssignRequest, duty_id: int = _id(), player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _do(conn, player, lambda now: firm.assign_duty(conn, player["id"], duty_id, _member(conn, body.seat_id), now))


@app.put("/api/firm/papers/{document_id}")
def read_a_paper(body: StrikeRequest, document_id: int = _id(), player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _do(conn, player, lambda now: firm.review_document(conn, player["id"], document_id, body.struck, now))


# Money
@app.post("/api/firm/raisings", status_code=status.HTTP_201_CREATED)
def design_a_raising(body: RaiseRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _do(conn, player, lambda now: firm_money.design_raising(conn, player["id"], body.kind, body.amount_kobo, body.quarters, now), "firm-money", 10)


@app.post("/api/firm/debts/{debt_id}/repayment")
def repay_a_debt(debt_id: int = _id(), player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _do(conn, player, lambda now: firm_money.repay(conn, player["id"], debt_id, now), "firm-money", 10)


@app.post("/api/stake-offers/{offer_id}")
def buy_a_stake(body: StakeRequest, offer_id: int = _id(), player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _do(conn, player, lambda now: firm_money.buy_stake(conn, player["id"], offer_id, body.amount_kobo, now), "firm-money", 10)


@app.put("/api/firm/budgets")
def set_the_budgets(body: BudgetsRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _do(conn, player, lambda now: firm_money.set_budgets(conn, player["id"], dict(body.budgets), now))


@app.post("/api/firm/training", status_code=status.HTTP_201_CREATED)
def sign_for_training(body: TrainingRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _do(conn, player, lambda now: firm_money.sign_cost(conn, player["id"], "training", body.amount_kobo, _member(conn, body.seat_id), now), "firm-money", 10)


@app.post("/api/firm/bonus-pool", status_code=status.HTTP_201_CREATED)
def propose_the_bonus_pool(body: BonusPoolRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    def act(now):
        shares = {}
        for seat, amount in body.shares.items():
            if not seat.isdigit() or len(seat) > 18:
                raise empires.EmpireError("Name each member by their seat.")
            shares[str(_member(conn, int(seat)))] = amount
        return firm_money.propose_bonuses(conn, player["id"], shares, now)
    return _do(conn, player, act, "firm-money", 10)


# People
@app.post("/api/firm/contracts", status_code=status.HTTP_201_CREATED)
def offer_a_contract(body: ContractRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _do(conn, player, lambda now: firm_people.offer_contract(conn, player["id"], _member(conn, body.seat_id), body.notice_days, body.bonus_bps,
                                                                    body.non_compete, now))


@app.put("/api/firm/contracts/{contract_id}/offer")
def offer_a_drafted_contract(body: SignRequest, contract_id: int = _id(), player: dict = Depends(current_player),
                             conn: Connection = Depends(get_connection)):
    return _do(conn, player, lambda now: firm_people.send_contract(conn, player["id"], contract_id, body.sign, now))


@app.put("/api/firm/contracts/{contract_id}")
def answer_a_contract(body: SignRequest, contract_id: int = _id(), player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _do(conn, player, lambda now: firm_people.answer_contract(conn, player["id"], contract_id, body.sign, now))


@app.post("/api/firm/apprentices", status_code=status.HTTP_201_CREATED)
def take_an_apprentice(body: MemberRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _do(conn, player, lambda now: firm_people.take_apprentice(conn, player["id"], _member(conn, body.seat_id), now))


@app.delete("/api/firm/apprentices")
def end_the_apprenticeship(player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _do(conn, player, lambda now: firm_people.end_apprenticeship(conn, player["id"], now))


@app.post("/api/firm/approaches", status_code=status.HTTP_201_CREATED)
def approach_a_member(body: PoachRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _do(conn, player, lambda now: firm_people.poach(conn, player["id"], _member(conn, body.seat_id), body.bonus_kobo, body.words, now), "firm-poach", 10)


@app.put("/api/firm/approaches/{offer_id}/match")
def match_an_approach(body: MatchRequest, offer_id: int = _id(), player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _do(conn, player, lambda now: firm_people.match(conn, player["id"], offer_id, body.bonus_kobo, now), "firm-poach", 10)


@app.put("/api/firm/approaches/{offer_id}")
def answer_an_approach(body: GoRequest, offer_id: int = _id(), player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _do(conn, player, lambda now: firm_people.answer_poach(conn, player["id"], offer_id, body.go, now), "firm-poach", 10)


@app.delete("/api/firm/approaches/{offer_id}")
def withdraw_an_approach(offer_id: int = _id(), player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _do(conn, player, lambda now: firm_people.withdraw_poach(conn, player["id"], offer_id, now), "firm-poach", 10)


@app.put("/api/firm/strategy")
def set_the_strategy(body: StrategyRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _do(conn, player, lambda now: firm_people.set_strategy(conn, player["id"], body.choice, body.growth_bps, body.payout_kobo, body.tasks, now))


# Work and events
@app.post("/api/firm/tasks", status_code=status.HTTP_201_CREATED)
def start_a_task(body: TaskRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _do(conn, player, lambda now: firm_tasks.start(conn, player["id"], body.kind, body.priority, now) and None)


@app.put("/api/firm/tasks/{task_id}/priority")
def set_a_priority(body: PriorityRequest, task_id: int = _id(), player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _do(conn, player, lambda now: firm_tasks.set_priority(conn, player["id"], task_id, body.priority, now))


@app.put("/api/firm/steps/{step_id}/given-to")
def give_a_step(body: AssignRequest, step_id: int = _id(), player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _do(conn, player, lambda now: firm_tasks.assign_step(conn, player["id"], step_id, _member(conn, body.seat_id), now))


@app.put("/api/firm/steps/{step_id}/defence")
def decide_a_defence(body: DefenceRequest, step_id: int = _id(), player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _do(conn, player, lambda now: firm_tasks.decide_defence(conn, player["id"], step_id, body.choice, body.reason, now))


@app.put("/api/firm/shortlists/{approval_id}")
def pick_from_the_shortlist(body: PickRequest, approval_id: int = _id(), player: dict = Depends(current_player),
                            conn: Connection = Depends(get_connection)):
    return _do(conn, player, lambda now: firm_tasks.pick(conn, player["id"], approval_id, body.company_id, now))


@app.put("/api/firm/rival")
def choose_the_rival(body: RivalRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _do(conn, player, lambda now: firm_tasks.choose_rival(conn, player["id"], body.empire_id, now))


@app.post("/api/firm/events/{happening_id}")
def answer_an_event(body: EventAnswerRequest, happening_id: int = _id(), player: dict = Depends(current_player),
                    conn: Connection = Depends(get_connection)):
    return _do(conn, player, lambda now: firm_tasks.answer(conn, player["id"], happening_id, body.desk, body.choice, now), "firm-event", 20)


@app.post("/api/firm/cover", status_code=status.HTTP_201_CREATED)
def buy_cover(body: CoverRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _do(conn, player, lambda now: firm_tasks.buy_cover(conn, player["id"], body.kind, body.insurer_id, body.cover_kobo, now), "firm-money", 10)


# Risk
@app.put("/api/firm/trade-limit")
def set_the_trade_limit(body: TradeLimitRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _do(conn, player, lambda now: firm_risk.set_trade_limit(conn, player["id"], body.limit_naira, now))


@app.put("/api/firm/freeze")
def freeze_trading(body: FreezeRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _do(conn, player, lambda now: firm_risk.freeze(conn, player["id"], _member(conn, body.seat_id), body.frozen, body.reason, now))


# Bookkeeping for outside clients
@app.post("/api/bookkeeping", status_code=status.HTTP_201_CREATED)
def hire_a_bookkeeper(body: HireRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _do(conn, player, lambda now: firm_clients.hire(conn, player["id"], body.adviser_key, body.fee_kobo, now), "firm-clients", 10)


@app.delete("/api/bookkeeping/{engagement_id}")
def cancel_a_bookkeeper(engagement_id: int = _id(), player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _do(conn, player, lambda now: firm_clients.cancel(conn, player["id"], engagement_id, now), "firm-clients", 10)


@app.post("/api/bookkeeping/{engagement_id}/open")
def open_a_clients_figures(engagement_id: int = _id(), player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _do(conn, player, lambda now: firm_clients.open_work(conn, player["id"], engagement_id, now), "firm-clients", 20)


@app.post("/api/bookkeeping/{engagement_id}/report")
def deliver_a_report(body: DeliverRequest, engagement_id: int = _id(), player: dict = Depends(current_player),
                     conn: Connection = Depends(get_connection)):
    return _do(conn, player, lambda now: firm_clients.deliver(conn, player["id"], engagement_id, body.net_kobo, body.biggest, body.note, now),
               "firm-clients", 10)


@app.put("/api/bookkeeping/{engagement_id}/rating")
def rate_a_report(body: RatingRequest, engagement_id: int = _id(), player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _do(conn, player, lambda now: firm_clients.rate(conn, player["id"], engagement_id, body.stars, now), "firm-clients", 10)


@app.get("/api/people/{player_id}/record")
def a_public_record(player_id: UUID, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    """Anybody's public record: what they signed and how it turned out, and what they did as a head."""
    limits.allow("firm-read", str(player["id"]), attempts=120, per_seconds=60)
    return wire({"signed": firm.track_record(conn, player_id), "as_head": firm.ceo_record(conn, player_id)})
