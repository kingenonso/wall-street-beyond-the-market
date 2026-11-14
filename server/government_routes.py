"""Government on the website (part 1): Economy → Government.

A player: who governs this year and how they came to (or the stand-in, and its published personality), the tax rates in
force and their limits, this year's budget and how the Assembly voted, the Assembly's members, any motion of no
confidence, and the election for next year. A player may stand or vote in the election; the leader may put the budget;
the head of an empire run by players may vote in the Assembly and table a motion of no confidence.
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
from simulation import careers, government

Bps = Annotated[int, Field(ge=0, le=10_000, strict=True)]


def _wire(value):
    if isinstance(value, dict):
        return {k: _wire(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_wire(v) for v in value]
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


class StandRequest(Request):
    pitch: str = Field(min_length=1, max_length=400)


class VoteRequest(Request):
    candidate_id: UUID


class BudgetRequest(Request):
    income_bps: Bps
    company_bps: Bps
    property_bps: Bps
    land_bps: Bps


class AssemblyVoteRequest(Request):
    subject: str = Field(pattern=r"^(budget|motion):\d{1,18}$")
    aye: bool


def _act(conn: Connection, player: dict, action) -> dict:
    limits.allow("government", str(player["id"]), attempts=20, per_seconds=60)
    try:
        done = action(_exchange_time(conn))
    except (government.GovernmentError, careers.CareerError) as refused:
        raise HTTPException(status.HTTP_409_CONFLICT, str(refused)) from None
    except (DeadlockDetected, UniqueViolation):
        raise HTTPException(status.HTTP_409_CONFLICT, "Somebody else changed this at the same moment. Please try again.") from None
    page = government.view(conn, player["id"], _exchange_time(conn))
    page["result"] = done
    return _wire(page)


@app.get("/api/government")
def government_page(player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _wire(government.view(conn, player["id"], _exchange_time(conn)))


@app.post("/api/government/stand")
def government_stand(body: StandRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: government.stand(conn, player["id"], body.pitch, now))


@app.post("/api/government/vote")
def government_vote(body: VoteRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: government.vote(conn, player["id"], body.candidate_id, now))


@app.post("/api/government/budget")
def government_budget(body: BudgetRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    proposed = {"income": body.income_bps, "company": body.company_bps, "property": body.property_bps, "land": body.land_bps}
    return _act(conn, player, lambda now: government.propose_budget(conn, player["id"], proposed, now))


@app.post("/api/government/assembly-vote")
def government_assembly_vote(body: AssemblyVoteRequest, player: dict = Depends(current_player),
                             conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: government.assembly_vote(conn, player["id"], body.subject, body.aye, now))


@app.post("/api/government/no-confidence")
def government_no_confidence(player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: government.no_confidence(conn, player["id"], now))
