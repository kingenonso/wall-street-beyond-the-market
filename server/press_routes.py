"""Stage 10, Part 2: investigations and the empire's press desk, on the website.

Never sent: what an empire holds, who leaked (except to the hunter who traces it), whether a crisis or a rumour is true,
what an investigation's documents point at, or anyone's private searches.
"""

from __future__ import annotations

from typing import Literal

from fastapi import Depends, HTTPException, status
from psycopg import Connection
from psycopg.errors import DeadlockDetected
from pydantic import Field

from server import limits
from server.db import get_connection
from server.firm_routes import wire
from server.main import _exchange_time, app, current_player, news_by_ref
from server.schemas import Request
from simulation import intel, newsroom, press

REF = r"^[A-Za-z0-9_-]{8,20}$"


def _act(conn: Connection, player: dict, action, bucket: str = "press", attempts: int = 30) -> dict:
    limits.allow(bucket, str(player["id"]), attempts=attempts, per_seconds=60)
    try:
        result = action(_exchange_time(conn))
    except (press.PressError, intel.IntelError, newsroom.NewsroomError) as refused:
        raise HTTPException(status.HTTP_409_CONFLICT, str(refused)) from None
    except DeadlockDetected:
        raise HTTPException(status.HTTP_409_CONFLICT, "Somebody else changed this at the same moment. Please try again.") from None
    return {"result": wire(result) if isinstance(result, (dict, list)) else result}


class FileRequest(Request):
    empire: str = Field(min_length=3, max_length=40)
    ref: str | None = Field(default=None, pattern=REF)


class CrisisRequest(Request):
    stance: Literal["admit", "regret", "deny"]
    statement: str = Field(min_length=10, max_length=300)


class StoryRequest(Request):
    story_id: int = Field(gt=0)


class SpinRequest(Request):
    comply: bool
    words: str | None = Field(default=None, max_length=300)


class ReplyRequest(Request):
    story_id: int = Field(gt=0)
    words: str = Field(min_length=20, max_length=300)


class FactCheckRequest(Request):
    member: str = Field(min_length=2, max_length=40)
    ref: str = Field(pattern=REF)


class PlantRequest(Request):
    ticker: str | None = Field(default=None, pattern=r"^[A-Z]{2,5}$")
    empire: str | None = Field(default=None, min_length=3, max_length=40)
    tone: Literal[1, -1] = -1


class LeakRequest(Request):
    kind: Literal["holding", "plan", "pact"]
    to: str = Field(min_length=2, max_length=40)
    ticker: str | None = Field(default=None, pattern=r"^[A-Z]{2,5}$")
    pact_id: int | None = Field(default=None, gt=0)


class RaiseRequest(Request):
    ref: str = Field(min_length=8, max_length=400, pattern=r"^[A-Za-z0-9_-]+$")


@app.get("/api/investigations")
def investigations(player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    if player.get("build") != "investment_banker":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Investigations are for Financial Journalists.")
    return {"files": wire(press.files(conn, player["id"], _exchange_time(conn)))}


@app.post("/api/investigations", status_code=201)
def investigation_open(body: FileRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: press.open_file(conn, player["id"], body.empire, body.ref, now))


@app.post("/api/investigations/{file_id}/dig")
def investigation_dig(file_id: int, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: press.dig(conn, player["id"], file_id, now))


@app.post("/api/investigations/{file_id}/second-source")
def investigation_second(file_id: int, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: press.second_source(conn, player["id"], file_id, now))


@app.post("/api/investigations/{file_id}/publish")
def investigation_publish(file_id: int, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: press.publish_expose(conn, player["id"], file_id, now), bucket="press-publish", attempts=6)


@app.post("/api/investigations/{file_id}/drop")
def investigation_drop(file_id: int, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: press.drop_file(conn, player["id"], file_id))


@app.get("/api/press")
def press_desk(player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    try:
        return wire(press.desk(conn, player["id"], _exchange_time(conn)))
    except press.PressError as refused:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(refused)) from None


@app.post("/api/press/crises/{crisis_id}")
def press_crisis(crisis_id: int, body: CrisisRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: press.answer_crisis(conn, player["id"], crisis_id, body.stance, body.statement, now))


@app.post("/api/press/leaks/{leak_id}/hunt")
def press_hunt(leak_id: int, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: press.hunt(conn, player["id"], leak_id, now))


@app.post("/api/press/spin", status_code=201)
def press_ask_spin(body: StoryRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: press.ask_spin(conn, player["id"], body.story_id, now))


@app.post("/api/press/spin/{request_id}")
def press_decide_spin(request_id: int, body: SpinRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: press.decide_spin(conn, player["id"], request_id, body.comply, body.words, now))


@app.post("/api/press/reply")
def press_reply(body: ReplyRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: press.reply(conn, player["id"], body.story_id, body.words, now))


@app.post("/api/press/fact-check")
def press_fact_check(body: FactCheckRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: press.fact_check(conn, player["id"], body.member, body.ref, now), bucket="intel-check", attempts=10)


@app.post("/api/press/plant", status_code=201)
def press_plant(body: PlantRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    if bool(body.ticker) == bool(body.empire):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Name a company or a rival empire.")
    return _act(conn, player, lambda now: press.plant(conn, player["id"], ticker=body.ticker, empire_name=body.empire, tone=body.tone, now=now))


@app.post("/api/leak")
def leak(body: LeakRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _act(conn, player, lambda now: press.leak(conn, player["id"], body.kind, body.to, now, ticker=body.ticker, pact_id=body.pact_id),
                bucket="leak", attempts=5)


@app.post("/api/replies/raise")
def raise_spin(body: RaiseRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    item = news_by_ref(conn, body.ref)
    if item is None or item["kind"] != "reply":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "There is no such reply.")
    return _act(conn, player, lambda now: press.raise_spin(conn, player["id"], item["id"], now))
