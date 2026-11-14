"""The courts on the website (Stage 11).

Anybody: the docket (every open case, its claim, its number and the lines that prove it), the regulator's budget and
what it has brought, and the compensation fund. A player: the cases they are defending and the ones they brought, their
legal record, and whether they are banned from trading. A player may bring a case, and a defendant may answer one by
settling it or by fighting it.

Never sent: anything about a case that is not on the docket or the player's own; the regulator's reasoning; the world's
secret, which decides which recorded wrongs become cases.
"""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi import Path as FastPath
from psycopg import Connection
from psycopg.errors import CheckViolation, DeadlockDetected, UniqueViolation
from pydantic import Field

from server import limits
from server.db import get_connection
from server.main import _exchange_time, app, current_player
from server.schemas import Request
from simulation import courts, ledger
from simulation import world_data as data

# Money in kobo, sent as text so no figure is ever rounded on the way.
MONEY = {"amount", "bond", "settle_price", "disgorgement", "damages", "fine", "costs", "paid", "owed", "budget",
         "fund", "cost", "price", "total", "value", "premium", "profit"}

KINDS = (
    {"kind": "insider", "name": "Dealing on confidential information",
     "who": "The regulator, or somebody who traded the other side of the dealing."},
    {"kind": "manipulation", "name": "Manipulation: ramping and wash trading",
     "who": "The regulator only."},
    {"kind": "undisclosed_stake", "name": "Failure to disclose a stake",
     "who": "The regulator, or a shareholder of the company."},
    {"kind": "naked_short", "name": "Naked short selling and failure to deliver",
     "who": "The regulator only."},
    {"kind": "insurance_fraud", "name": "Insurance fraud: a claim on a loss of the claimant's own making",
     "who": "The insurer refers it, when it refuses the claim."},
)


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


def _act(conn: Connection, player: dict, action, attempts: int = 20):
    limits.allow("court", str(player["id"]), attempts=attempts, per_seconds=60)
    try:
        with conn.transaction():
            return action(_exchange_time(conn))
    except courts.CourtError as refused:
        raise HTTPException(status.HTTP_409_CONFLICT, str(refused)) from None
    except (DeadlockDetected, UniqueViolation, CheckViolation):
        raise HTTPException(status.HTTP_409_CONFLICT, "Somebody else changed this at the same moment. Please try again.") from None


def _page(conn: Connection, player: dict, now: datetime) -> dict:
    if not courts.ready(conn):
        return {"ready": False}
    return _wire({
        "ready": True,
        "docket": courts.docket(conn),
        "claims": courts.claims(conn, player["id"], _period(conn, now), now),
        "mine": courts.my_cases(conn, player["id"]),
        "regulator": courts.regulator(conn),
        "fund": ledger.balance(conn, ledger.account_id(conn, courts.COMPENSATION_FUND)),
        "kinds": list(KINDS),
        "rules": {
            "bond_bps": data.COURT_BOND_BPS,
            "bond_floor": data.COURT_BOND_FLOOR_NAIRA * 100,
            "settle_bps": data.COURT_SETTLE_BPS,
            "costs_bps": data.COURT_COSTS_BPS,
            "min_claim": data.COURT_MIN_CLAIM_NAIRA * 100,
            "case_cost": data.COURT_CASE_COST_NAIRA * 100,
            "fines": {kind: bps for kind, bps in data.COURT_FINE_BPS.items()},
            "bans": {kind: quarters for kind, quarters in data.COURT_BAN_QUARTERS.items()},
            "reputation": data.COURT_REPUTATION,
        },
    })


class BringRequest(Request):
    kind: str = Field(pattern="^(insider|manipulation|undisclosed_stake|naked_short)$")
    defendant_id: UUID
    company_id: UUID | None = None


class AnswerRequest(Request):
    choice: str = Field(pattern="^(settle|fight)$")


@app.get("/api/court")
def court_page(player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _page(conn, player, _exchange_time(conn))


@app.post("/api/court/cases", status_code=status.HTTP_201_CREATED)
def court_bring(body: BringRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    _act(conn, player, lambda now: courts.bring(
        conn, player["id"], kind=body.kind, defendant_id=body.defendant_id, company_id=body.company_id,
        period=_period(conn, now), now=now))
    return _page(conn, player, _exchange_time(conn))


@app.post("/api/court/cases/{case_id}/answer")
def court_answer(body: AnswerRequest, case_id: int = FastPath(ge=1, le=9_000_000_000_000_000_000),
                 player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    _act(conn, player, lambda now: courts.respond(
        conn, player["id"], case_id, body.choice, _period(conn, now), now))
    return _page(conn, player, _exchange_time(conn))


def _period(conn: Connection, now: datetime) -> int:
    from simulation import careers
    return careers.world_now(conn, now)["period"]
