"""Stage 6: empires, the War Room, pension funds run by players, and the savings choices.

Every request here acts as the logged-in player and nobody else: the server works out which
empire or fund they belong to from its own records, never from anything the website sends.
Amounts of money arrive as whole kobo and leave as text, like everywhere else.
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import Depends, HTTPException, Query, status
from fastapi import Path as FastPath
from psycopg import Connection
from psycopg.errors import DeadlockDetected
from pydantic import AfterValidator, Field
from typing import Annotated

from server import limits
from server.db import get_connection
from server.main import _exchange_time, app, current_player
from server.schemas import Request
from simulation import careers, clock, desks_more, empires, exchange, pensionfunds



def _plain(words: str) -> str:
    """Text a player typed is kept as one plain line: characters that cannot be shown are refused."""
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in words):
        raise ValueError("That text has characters in it that cannot be kept.")
    return words


Words = Annotated[str, AfterValidator(_plain)]
router = app          # the routes are added to the one application, so that every route is in one list

MONEY = {"worth", "cash", "shares_value", "bonds_value", "amount", "value", "fee", "repaid", "fine", "debt_left", "signing_limit",
         "signing_used", "trade_limit", "trade_used", "expense_limit", "registration_fee", "ai_audit_fee", "your_value",
         "limit_price", "reserved", "value_filled", "fees_paid", "limit", "used", "moved", "reward", "bonus_limit", "bonus",
         "counter_offer_most"}
PERIODS = {"period", "from_period", "to_period", "since"}


def _id():
    return FastPath(ge=1, le=9_000_000_000_000_000_000)

Amount = Field(gt=0, le=1_000_000_000_000_000, strict=True)


def wire(value):
    """Turn what the simulation returns into what the website receives: amounts of money as text
    with `_kobo` on the name, quarters with their labels, and identifiers as text."""
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            if key in MONEY and isinstance(item, int) and not isinstance(item, bool):
                out[f"{key}_kobo"] = str(item)
            elif key in PERIODS and isinstance(item, int) and not isinstance(item, bool):
                out[key] = item
                out[f"{key}_label"] = clock.period_label(item) if item >= 0 else "the start of the game"
            else:
                out[key] = wire(item)
        return out
    if isinstance(value, (list, tuple)):
        return [wire(item) for item in value]
    if isinstance(value, UUID):
        return str(value)
    return value


def _view(conn: Connection, player: dict) -> dict:
    now = _exchange_time(conn)
    return wire({"room": empires.war_room(conn, player["id"], now), "directory": empires.directory(conn, player["id"], now)})


def _do(conn: Connection, player: dict, action, bucket: str = "empire", attempts: int = 40) -> dict:
    limits.allow(bucket, str(player["id"]), attempts=attempts, per_seconds=60)
    try:
        result = action(_exchange_time(conn))
    except (empires.EmpireError, pensionfunds.FundError, careers.CareerError) as refused:
        raise HTTPException(status.HTTP_409_CONFLICT, str(refused)) from None
    except exchange.EngineFailure:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "The exchange cannot take orders at this moment. Nothing was changed. Please try again.") from None
    except DeadlockDetected:
        raise HTTPException(status.HTTP_409_CONFLICT, "Somebody else changed this at the same moment. Nothing was changed. Please try again.") from None
    view = _view(conn, player)
    if isinstance(result, dict) and "words" in result:
        view["notice"] = result["words"]
    return view


# ---------------------------------------------------------------------------
# What the website sends
# ---------------------------------------------------------------------------

class FoundRequest(Request):
    name: Words = Field(min_length=3, max_length=40)
    amount_kobo: int = Field(default=0, ge=0, le=1_000_000_000_000_000, strict=True)
    from_savings_kobo: int = Field(default=0, ge=0, le=1_000_000_000_000_000, strict=True)


class CapitalRequest(Request):
    amount_kobo: int = Field(default=0, ge=0, le=1_000_000_000_000_000, strict=True)
    from_savings_kobo: int = Field(default=0, ge=0, le=1_000_000_000_000_000, strict=True)


class LetterRequest(Request):
    letter: Words = Field(default="", max_length=600)


class OfferRequest(Request):
    bonus_kobo: int = Field(default=0, ge=0, le=1_000_000_000_000_000, strict=True)
    signing_limit_kobo: int | None = Field(default=None, ge=0, le=1_000_000_000_000, strict=True)
    words: Words = Field(default="", max_length=400)


class VoteRequest(Request):
    build: Literal["investment_banker", "asset_manager", "risk_manager", "accountant", "lawyer", "journalist"]
    slot: Literal[1, 2]


class DecideRequest(Request):
    accept: bool


class LimitsRequest(Request):
    expense_limit_kobo: int | None = Field(default=None, ge=0, le=1_000_000_000_000, strict=True)
    trade_limit_bps: int | None = Field(default=None, ge=0, le=10_000, strict=True)
    member_id: UUID | None = None
    signing_limit_kobo: int | None = Field(default=None, ge=0, le=1_000_000_000_000, strict=True)


class StaffRequest(Request):
    build: Literal["investment_banker", "asset_manager", "risk_manager", "accountant", "lawyer", "journalist"]
    slot: Literal[1, 2]
    staffed: bool


class BonusRequest(Request):
    member_id: UUID
    amount_kobo: int = Amount
    why: Words = Field(default="", max_length=120)


class AmountRequest(Request):
    amount_kobo: int = Amount


class EmpireOrderRequest(Request):
    ticker: str = Field(pattern=r"^[A-Z]{3}$")
    side: Literal["buy", "sell"]
    kind: Literal["limit", "market"]
    quantity: int = Field(gt=0, le=100_000_000_000, strict=True)
    limit_price_kobo: int | None = Field(default=None, gt=0, le=1_000_000_000_000, strict=True)


class EmpireBondRequest(Request):
    code: str = Field(pattern=r"^[A-Z0-9]{3,12}$")
    side: Literal["buy", "sell"]
    units: int = Field(gt=0, le=1_000_000_000_000, strict=True)


class AuditReportRequest(Request):
    report: list[int] = Field(max_length=200)


class BookRequest(Request):
    book_id: int = Field(ge=1, le=9_000_000_000_000_000_000, strict=True)


class CaseRequest(Request):
    punish: bool


class PactRequest(Request):
    to_empire: int = Field(ge=1, le=9_000_000_000_000_000_000, strict=True)
    kind: Literal["alliance", "truce", "joint_bid", "share_information", "same_candidate", "stay_out", "divide_market", "fix_prices", "rig_bids"]
    terms: Words = Field(min_length=10, max_length=400)


class PactAnswerRequest(Request):
    action: Literal["sign", "refuse", "break", "report"]


class InvestigateRequest(Request):
    empire_id: int = Field(ge=1, le=9_000_000_000_000_000_000, strict=True)


class MessageRequest(Request):
    body: Words = Field(min_length=1, max_length=500)


class OpenFundRequest(Request):
    name: Words = Field(min_length=3, max_length=40)
    fee_bps: int = Field(ge=0, le=50, strict=True)


class FeeRequest(Request):
    fee_bps: int = Field(ge=0, le=50, strict=True)


class ExtraSavingRequest(Request):
    extra_bps: int = Field(ge=0, le=2000, multiple_of=100, strict=True)


def _priced(body: EmpireOrderRequest) -> None:
    if (body.kind == "limit") != (body.limit_price_kobo is not None):
        raise HTTPException(422, "Give a price for an order at your own price, and none for an order at the best price available.")


# ---------------------------------------------------------------------------
# Empires
# ---------------------------------------------------------------------------

@router.get("/api/empires")
def the_empires(player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    """Every empire and the league table, and (for a member) their own War Room."""
    limits.allow("empire-read", str(player["id"]), attempts=90, per_seconds=60)
    return _view(conn, player)


@router.post("/api/empires", status_code=status.HTTP_201_CREATED)
def found_an_empire(body: FoundRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _do(conn, player, lambda now: empires.found(conn, player["id"], body.name, body.amount_kobo, body.from_savings_kobo, now), "empire-found", 6)


@router.post("/api/empires/{empire_id}/applications", status_code=status.HTTP_201_CREATED)
def ask_for_a_seat(empire_id: int = _id(), player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _do(conn, player, lambda now: empires.apply(conn, player["id"], empire_id, now))


@router.delete("/api/empire/application")
def withdraw_my_application(player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _do(conn, player, lambda now: empires.withdraw_application(conn, player["id"]))


# Leaving is by resignation letter: a notice period, during which the head may make a counter-offer.

@router.post("/api/empire/resignation", status_code=status.HTTP_201_CREATED)
def hand_in_my_resignation(body: LetterRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    def act(now):
        done = empires.resign(conn, player["id"], body.letter, now)
        if done["left"]:
            return {"words": "You have left, and what you put in has been handed back."}
        return {"words": "Your letter has been handed in. You are still a member, and paid as usual, until the notice has run."}
    return _do(conn, player, act, "empire-resign", 6)


@router.delete("/api/empire/resignation")
def withdraw_my_resignation(player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _do(conn, player, lambda now: empires.withdraw_resignation(conn, player["id"], now), "empire-resign", 6)


@router.post("/api/empire/resignation/acceptance")
def accept_the_offer_to_stay(player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _do(conn, player, lambda now: empires.accept_offer(conn, player["id"], now), "empire-resign", 6)


@router.put("/api/empire/resignations/{resignation_id}/offer")
def make_a_counter_offer(body: OfferRequest, resignation_id: int = _id(), player: dict = Depends(current_player),
                         conn: Connection = Depends(get_connection)):
    return _do(conn, player, lambda now: empires.counter_offer(conn, player["id"], resignation_id, body.bonus_kobo, body.signing_limit_kobo,
                                                              body.words, now))


@router.delete("/api/empire/resignations/{resignation_id}")
def let_them_go_early(resignation_id: int = _id(), player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _do(conn, player, lambda now: empires.release(conn, player["id"], resignation_id, now))


@router.post("/api/empire/head-votes", status_code=status.HTTP_201_CREATED)
def vote_for_a_head(body: VoteRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    def act(now):
        done = empires.vote_for_seat(conn, player["id"], body.build, body.slot, now)
        return {"words": "They have been voted in and now lead the empire." if done["elected"]
                else f"Your vote is in: {done['votes']} of the {done['needed']} needed."}
    return _do(conn, player, act, "empire-vote", 10)


@router.post("/api/empire/capital")
def put_money_in(body: CapitalRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _do(conn, player, lambda now: empires.put_in(conn, player["id"], body.amount_kobo, body.from_savings_kobo, now))


@router.post("/api/empire/opening")
def open_my_empire(player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _do(conn, player, lambda now: empires.open_empire(conn, player["id"], now))


@router.delete("/api/empire/founding")
def cancel_the_founding(player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _do(conn, player, lambda now: empires.cancel_founding(conn, player["id"], now))


@router.put("/api/empire/applications/{application_id}")
def decide_an_application(body: DecideRequest, application_id: int = _id(), player: dict = Depends(current_player),
                          conn: Connection = Depends(get_connection)):
    return _do(conn, player, lambda now: empires.decide_application(conn, player["id"], application_id, body.accept, now))


@router.put("/api/empire/limits")
def set_the_limits(body: LimitsRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _do(conn, player, lambda now: empires.set_limits(
        conn, player["id"], expense_limit=body.expense_limit_kobo, trade_limit_bps=body.trade_limit_bps,
        member_id=body.member_id, signing_limit=body.signing_limit_kobo, now=now))


@router.put("/api/empire/staff")
def hire_or_release_staff(body: StaffRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _do(conn, player, lambda now: empires.staff_seat(conn, player["id"], body.build, body.slot, body.staffed, now))


@router.post("/api/empire/bonuses")
def pay_a_bonus(body: BonusRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _do(conn, player, lambda now: empires.pay_bonus(conn, player["id"], body.member_id, body.amount_kobo, body.why, now))


@router.delete("/api/empire/members/{member_id}")
def remove_a_member(member_id: UUID, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _do(conn, player, lambda now: empires.sack(conn, player["id"], member_id, now))


@router.post("/api/empire/orders", status_code=status.HTTP_201_CREATED)
def trade_for_the_empire(body: EmpireOrderRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    _priced(body)
    return _do(conn, player, lambda now: empires.trade_shares(
        conn, player["id"], ticker=body.ticker, side=body.side, kind=body.kind, quantity=body.quantity,
        limit_price=body.limit_price_kobo, now=now), "empire-trade", 60)


@router.delete("/api/empire/orders/{order_id}")
def cancel_an_empire_order(order_id: int = _id(), player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _do(conn, player, lambda now: empires.cancel_order(conn, player["id"], order_id, now), "empire-trade", 60)


@router.post("/api/empire/bonds", status_code=status.HTTP_201_CREATED)
def trade_bonds_for_the_empire(body: EmpireBondRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _do(conn, player, lambda now: empires.trade_bonds(conn, player["id"], code=body.code, side=body.side, units=body.units, now=now),
               "empire-trade", 60)


@router.post("/api/empire/expenses", status_code=status.HTTP_201_CREATED)
def sign_for_an_expense(body: AmountRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    """The shadow feature: the member signs for a cost, and the money comes to them."""
    return _do(conn, player, lambda now: empires.divert(conn, player["id"], body.amount_kobo, now), "empire-expense", 10)


@router.post("/api/empire/audits", status_code=status.HTTP_201_CREATED)
def audit_the_books(player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _do(conn, player, lambda now: empires.accountant_audit(conn, player["id"], now))


@router.put("/api/empire/audits/{audit_id}")
def file_the_audit(body: AuditReportRequest, audit_id: int = _id(), player: dict = Depends(current_player),
                   conn: Connection = Depends(get_connection)):
    return _do(conn, player, lambda now: empires.file_audit(conn, player["id"], audit_id, body.report, now))


@router.post("/api/empire/ai-audit", status_code=status.HTTP_201_CREATED)
def hire_the_ai_audit(player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _do(conn, player, lambda now: empires.ai_audit(conn, player["id"], now), "empire-audit", 6)


@router.post("/api/empire/reports", status_code=status.HTTP_201_CREATED)
def report_an_entry(body: BookRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    def act(now):
        proved = empires.report_entry(conn, player["id"], body.book_id, now)["proved"]
        return {"words": "The entry was looked at and proved false. A case has been opened." if proved
                else "The entry was looked at and nothing was proved. A groundless report costs a little reputation."}
    return _do(conn, player, act, "empire-audit", 6)


@router.put("/api/empire/cases/{case_id}")
def decide_a_case(body: CaseRequest, case_id: int = _id(), player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _do(conn, player, lambda now: empires.decide_case(conn, player["id"], case_id, body.punish, now))


@router.post("/api/empire/tasks", status_code=status.HTTP_201_CREATED)
def start_a_task(player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _do(conn, player, lambda now: empires.start_task(conn, player["id"], now))


@router.post("/api/empire/steps/{step_id}/take", status_code=status.HTTP_201_CREATED)
def take_a_step(step_id: int = _id(), player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _do(conn, player, lambda now: empires.take_step(conn, player["id"], step_id, now))


@router.post("/api/empire/steps/{step_id}/approve")
def approve_a_step(step_id: int = _id(), player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _do(conn, player, lambda now: empires.approve_step(conn, player["id"], step_id, now))


@router.post("/api/empire/pacts", status_code=status.HTTP_201_CREATED)
def draft_a_pact(body: PactRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _do(conn, player, lambda now: empires.draft_pact(conn, player["id"], body.to_empire, body.kind, body.terms, now), "empire-pact", 10)


@router.put("/api/empire/pacts/{pact_id}")
def answer_a_pact(body: PactAnswerRequest, pact_id: int = _id(), player: dict = Depends(current_player),
                  conn: Connection = Depends(get_connection)):
    act = {"sign": empires.sign_pact, "refuse": empires.refuse_pact, "break": empires.break_pact, "report": empires.report_pact}[body.action]
    return _do(conn, player, lambda now: act(conn, player["id"], pact_id, now), "empire-pact", 10)


@router.post("/api/empire/investigations", status_code=status.HTTP_201_CREATED)
def investigate_an_empire(body: InvestigateRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _do(conn, player, lambda now: empires.investigate(conn, player["id"], body.empire_id, now), "empire-pact", 10)


@router.post("/api/empire/messages", status_code=status.HTTP_201_CREATED)
def say_in_the_war_room(body: MessageRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _do(conn, player, lambda now: empires.say(conn, player["id"], body.body, now), "empire-chat", 20)


# ---------------------------------------------------------------------------
# Pension funds run by players
# ---------------------------------------------------------------------------

def _funds(conn: Connection, player: dict) -> dict:
    return wire(pensionfunds.listing(conn, player["id"], _exchange_time(conn)))


def _fund_do(conn: Connection, player: dict, action, bucket: str = "fund", attempts: int = 30) -> dict:
    limits.allow(bucket, str(player["id"]), attempts=attempts, per_seconds=60)
    try:
        action(_exchange_time(conn))
    except (pensionfunds.FundError, empires.EmpireError, careers.CareerError) as refused:
        raise HTTPException(status.HTTP_409_CONFLICT, str(refused)) from None
    except DeadlockDetected:
        raise HTTPException(status.HTTP_409_CONFLICT, "Somebody else changed this at the same moment. Nothing was changed. Please try again.") from None
    except exchange.EngineFailure:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "The exchange cannot take orders at this moment. Nothing was changed. Please try again.") from None
    return _funds(conn, player)


@router.get("/api/pension-funds")
def the_pension_funds(player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    limits.allow("fund-read", str(player["id"]), attempts=90, per_seconds=60)
    return _funds(conn, player)


@router.post("/api/pension-funds", status_code=status.HTTP_201_CREATED)
def open_a_pension_fund(body: OpenFundRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _fund_do(conn, player, lambda now: pensionfunds.open_fund(conn, player["id"], body.name, body.fee_bps, now), "fund-open", 6)


@router.put("/api/pension-fund/fee")
def lower_the_fee(body: FeeRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _fund_do(conn, player, lambda now: pensionfunds.set_fee(conn, player["id"], body.fee_bps, now))


@router.put("/api/pension-funds/{fund_id}/savings")
def move_my_savings_in(fund_id: int = _id(), player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _fund_do(conn, player, lambda now: pensionfunds.join(conn, player["id"], fund_id, now))


@router.delete("/api/pension-fund/savings")
def ask_for_my_savings_back(player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _fund_do(conn, player, lambda now: pensionfunds.leave(conn, player["id"], now))


@router.post("/api/pension-fund/orders", status_code=status.HTTP_201_CREATED)
def trade_for_the_fund(body: EmpireOrderRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    _priced(body)
    return _fund_do(conn, player, lambda now: pensionfunds.trade_shares(
        conn, player["id"], ticker=body.ticker, side=body.side, kind=body.kind, quantity=body.quantity,
        limit_price=body.limit_price_kobo, now=now), "fund-trade", 60)


@router.delete("/api/pension-fund/orders/{order_id}")
def cancel_a_fund_order(order_id: int = _id(), player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _fund_do(conn, player, lambda now: pensionfunds.cancel_order(conn, player["id"], order_id, now), "fund-trade", 60)


@router.post("/api/pension-fund/bonds", status_code=status.HTTP_201_CREATED)
def trade_bonds_for_the_fund(body: EmpireBondRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _fund_do(conn, player, lambda now: pensionfunds.trade_bonds(conn, player["id"], code=body.code, side=body.side,
                                                                       units=body.units, now=now), "fund-trade", 60)


@router.post("/api/pension-fund/costs", status_code=status.HTTP_201_CREATED)
def sign_for_a_fund_cost(body: AmountRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _fund_do(conn, player, lambda now: pensionfunds.divert(conn, player["id"], body.amount_kobo, now), "empire-expense", 10)


@router.post("/api/pension-fund/ai-audit", status_code=status.HTTP_201_CREATED)
def hire_the_ai_audit_of_my_fund(player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _fund_do(conn, player, lambda now: pensionfunds.ai_audit(conn, player["id"], now), "empire-audit", 6)


# ---------------------------------------------------------------------------
# The screens of the Investment Banker, the Risk Manager, the Legal Counsel and the head of an empire
# ---------------------------------------------------------------------------

DESK_MONEY = {"price", "market_value", "revenue", "net_profit", "ebitda", "borrowings", "equity", "total", "at_risk", "var", "shortfall",
              "worst", "loss", "staff_pay", "total_owed", "liquid", "government"}


def _desk_wire(value):
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            if key == "implied" and isinstance(item, dict):
                out["implied_kobo"] = {k: (None if v is None else str(v)) for k, v in item.items()}
            elif (key in DESK_MONEY or key in MONEY) and isinstance(item, int) and not isinstance(item, bool):
                out[f"{key}_kobo"] = str(item)
            else:
                out[key] = _desk_wire(item)
        return out
    if isinstance(value, (list, tuple)):
        return [_desk_wire(item) for item in value]
    return wire(value) if isinstance(value, UUID) else value


def _account(conn: Connection, player: dict):
    from simulation import ledger
    return ledger.player_account_id(conn, player["id"])


@router.get("/api/desk/investment-banker")
def investment_banker_desk(ticker: str | None = Query(default=None, pattern="^[A-Z]{3}$"), player: dict = Depends(current_player),
                           conn: Connection = Depends(get_connection)):
    limits.allow("desk-read", str(player["id"]), attempts=90, per_seconds=60)
    seen = desks_more.banker_desk(conn, player["id"], _account(conn, player), ticker, _exchange_time(conn))
    if seen is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "There is no company with that code.")
    return _desk_wire(seen)


@router.get("/api/desk/risk-manager")
def risk_manager_desk(book: Literal["auto", "own"] = "auto", player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    limits.allow("desk-read", str(player["id"]), attempts=90, per_seconds=60)
    return _desk_wire(desks_more.risk_desk(conn, player["id"], _account(conn, player), book, _exchange_time(conn)))


@router.get("/api/desk/lawyer")
def lawyer_desk(ticker: str | None = Query(default=None, pattern="^[A-Z]{3}$"), player: dict = Depends(current_player),
                conn: Connection = Depends(get_connection)):
    limits.allow("desk-read", str(player["id"]), attempts=90, per_seconds=60)
    seen = desks_more.lawyer_desk(conn, player["id"], ticker, _exchange_time(conn))
    if seen is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "There is no company with that code.")
    return _desk_wire(seen)


@router.get("/api/desk/head")
def head_of_empire_desk(player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    limits.allow("desk-read", str(player["id"]), attempts=90, per_seconds=60)
    seen = desks_more.head_desk(conn, player["id"], _exchange_time(conn))
    if seen is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "You hold no seat in an empire.")
    return _desk_wire(seen)
