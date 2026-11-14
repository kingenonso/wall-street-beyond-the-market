"""Competition on the website (part 1): Work → Competition.

A player: this quarter's ranked forecast for their build and the last quarter's results, the mandates open to pitch
(sales of shares, and defences against hostile bids) and what companies decided, the calls empires have made on each
other, the league by what earned each empire its points, and the table of analysts. An empire's Asset Manager or Risk
Manager (or head) may make a call on a rival. They may hand in a forecast, and an empire's Investment Banker or head
may pitch for a mandate. Other players' forecasts and pitches are never sent until they are judged.
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
from simulation import careers, competition

Bps = Annotated[int, Field(ge=0, le=10_000, strict=True)]
MONEY = {"guess", "truth", "amount", "fee_paid"}


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


class PitchRequest(Request):
    mandate_id: int = Field(ge=1, le=9_000_000_000_000_000_000, strict=True)
    fee_bps: Bps
    take_up_bps: Bps


class CallRequest(Request):
    kind: str = Field(pattern="^(overvalued|weak_bank)$")
    company_id: UUID


class ForecastRequest(Request):
    contest_id: int = Field(ge=1, le=9_000_000_000_000_000_000, strict=True)
    guess_kobo: int = Field(ge=-100_000_000_000_000_000, le=100_000_000_000_000_000, strict=True)


def _act(conn: Connection, player: dict, action) -> dict:
    limits.allow("competition", str(player["id"]), attempts=20, per_seconds=60)
    try:
        done = action(_exchange_time(conn))
    except (competition.CompetitionError, careers.CareerError) as refused:
        raise HTTPException(status.HTTP_409_CONFLICT, str(refused)) from None
    except (DeadlockDetected, UniqueViolation):
        raise HTTPException(status.HTTP_409_CONFLICT, "Somebody else changed this at the same moment. Please try again.") from None
    page = competition.view(conn, player["id"], _exchange_time(conn))
    page["result"] = done
    return _wire(page)


@app.get("/api/competition")
def competition_page(player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _wire(competition.view(conn, player["id"], _exchange_time(conn)))


@app.post("/api/competition/pitch")
def competition_pitch(body: PitchRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: competition.pitch(conn, player["id"], body.mandate_id, body.fee_bps,
                                                             body.take_up_bps, now))


@app.post("/api/competition/forecast")
def competition_forecast(body: ForecastRequest, player: dict = Depends(current_player),
                         conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: competition.enter(conn, player["id"], body.contest_id, body.guess_kobo, now))


@app.post("/api/competition/call")
def competition_call(body: CallRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: competition.make_call(conn, player["id"], body.kind, body.company_id, now))
