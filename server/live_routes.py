"""Live events on the website (part 1, 16 November 2026): Work → Live events.

Everybody sees when the next bell is, what happened at the last one, and the table as the event runs. A member of an
empire run by players hands in the empire's one sealed prediction in the first ten minutes; the head sets the standing
plan for members who cannot be there. Other empires' predictions, and other empires' money, are never sent: only that an
empire has predicted, and how its result compares with what it was worth at the bell. Predictions are shown once scored.
"""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from fastapi import Depends, HTTPException, status
from psycopg import Connection
from psycopg.errors import DeadlockDetected, UniqueViolation
from pydantic import Field

from server import limits
from server.db import get_connection
from server.main import _exchange_time, app, current_player
from server.schemas import Request
from simulation import careers, liveevents

MONEY = {"start_price", "price_now", "result_kobo", "budget"}


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


class PredictRequest(Request):
    event_id: int = Field(ge=1, le=9_000_000_000_000_000_000, strict=True)
    move_bps: int = Field(ge=-5_000, le=5_000, strict=True)


class PlanRequest(Request):
    plan: str = Field(pattern="^(hold|cut|buy_the_fall|ride)$")
    budget_kobo: int = Field(ge=0, le=100_000_000_000_000_000, strict=True)


def _act(conn: Connection, player: dict, action) -> dict:
    limits.allow("live-events", str(player["id"]), attempts=20, per_seconds=60)
    try:
        done = action(_exchange_time(conn))
    except (liveevents.LiveEventError, careers.CareerError) as refused:
        raise HTTPException(status.HTTP_409_CONFLICT, str(refused)) from None
    except (DeadlockDetected, UniqueViolation):
        raise HTTPException(status.HTTP_409_CONFLICT, "Somebody else changed this at the same moment. Please try again.") from None
    page = liveevents.view(conn, player["id"], _exchange_time(conn))
    page["result"] = done
    return _wire(page)


@app.get("/api/live")
def live_page(player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _wire(liveevents.view(conn, player["id"], _exchange_time(conn)))


@app.post("/api/live/predict")
def live_predict(body: PredictRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: liveevents.predict(conn, player["id"], body.event_id, body.move_bps, now))


@app.post("/api/live/plan")
def live_plan(body: PlanRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: liveevents.set_plan(conn, player["id"], body.plan, body.budget_kobo, now))
