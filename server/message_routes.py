"""Quick fixes: messages between players, blocking and reporting, and the quiet news pop-ups.

Every request acts as the logged-in player and nobody else. A player sees only messages they sent
or received, never who has blocked or reported them, and never a story dated later than today.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import Depends, HTTPException, Query, status
from psycopg import Connection
from pydantic import Field

from server import limits
from server.db import get_connection
from server.main import _exchange_time, _player_response, _world, app, current_player
from server.schemas import PlayerResponse, Request
from simulation import clock, messages, news, news_kinds
from simulation import world_data as data

NAME = Field(min_length=1, max_length=40)


class NewsAlertsRequest(Request):
    on: bool


class SendRequest(Request):
    to: str = NAME
    body: str = Field(min_length=1, max_length=data.MESSAGE_MAX_CHARS * 2)


class NameRequest(Request):
    name: str = NAME


class ReportRequest(Request):
    message_id: int = Field(ge=1)
    reason: str | None = Field(default=None, max_length=data.MESSAGE_REPORT_MAX_CHARS)
    block: bool = False


def _refused(error: Exception):
    raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from None


def _when(m: dict) -> dict:
    return {**m, "sent_at": m["sent_at"].isoformat()}


# --- the quiet news pop-ups ---------------------------------------------------------------------

@app.patch("/api/me/news-alerts", response_model=PlayerResponse)
def set_news_alerts(body: NewsAlertsRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    row = conn.execute("UPDATE players SET news_alerts = %s WHERE id = %s RETURNING *", (body.on, player["id"])).fetchone()
    return _player_response(conn, row)


@app.get("/api/news/alerts")
def news_alerts(
    period: int | None = Query(default=None, ge=0, le=100_000),
    day: int | None = Query(default=None, ge=0, le=90),
    top: int | None = Query(default=None, ge=0),
    player: dict = Depends(current_player),
    conn: Connection = Depends(get_connection),
):
    """New stories since the mark the last look returned. Empty when the player has muted the pop-ups."""
    world = _world(conn)
    today = world and clock.game_date(datetime.now(timezone.utc), clock.effective_start(world["world_start"], world["weeks_ahead"]))
    if today is None:
        return {"items": [], "more": 0, "mark": None}
    period_now = (today.year - 1) * clock.QUARTERS_PER_YEAR + today.quarter
    after = (period, day, top) if None not in (period, day, top) else None
    found = news.alerts(conn, period_now, today.day_of_quarter, after)
    if not player.get("news_alerts", True):
        found = {**found, "items": [], "more": 0}
    p, d, t = found["mark"]
    return {
        "items": [{"headline": r["headline"], "outlet": news_kinds.outlet_name(r["outlet"]), "period_label": clock.period_label(r["period"]),
                   "day": r["day"], "important": r["importance"] >= 80, "tickers": r["tickers"]} for r in found["items"]],
        "more": found["more"], "mark": {"period": p, "day": d, "top": t},
    }


# --- messages -------------------------------------------------------------------------------------

@app.get("/api/messages")
def my_conversations(player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    seen = messages.conversations(conn, player["id"])
    return {**seen, "conversations": [_when(c) for c in seen["conversations"]], "unread": messages.unread_count(conn, player["id"])}


@app.get("/api/messages/with")
def my_thread(name: str = Query(min_length=1, max_length=40), player: dict = Depends(current_player),
              conn: Connection = Depends(get_connection)):
    try:
        seen = messages.thread(conn, player["id"], name, _exchange_time(conn))
    except messages.MessageError as refused:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(refused)) from None
    return {**seen, "messages": [_when(m) for m in seen["messages"]]}


@app.post("/api/messages", status_code=status.HTTP_201_CREATED)
def send_message(body: SendRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    limits.allow("message", str(player["id"]), attempts=data.MESSAGES_PER_HOUR, per_seconds=600)
    try:
        return _when(messages.send(conn, player["id"], body.to, body.body, _exchange_time(conn)))
    except messages.MessageError as refused:
        _refused(refused)


def _then_list(conn: Connection, player: dict, action) -> dict:
    limits.allow("message-settings", str(player["id"]), attempts=30, per_seconds=60)
    try:
        action(_exchange_time(conn))
    except messages.MessageError as refused:
        _refused(refused)
    return my_conversations(player, conn)


@app.post("/api/messages/block")
def block_player(body: NameRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _then_list(conn, player, lambda now: messages.block(conn, player["id"], body.name, now))


@app.post("/api/messages/unblock")
def unblock_player(body: NameRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _then_list(conn, player, lambda now: messages.unblock(conn, player["id"], body.name))


@app.post("/api/messages/report")
def report_message(body: ReportRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _then_list(conn, player, lambda now: messages.report(conn, player["id"], body.message_id, body.reason, now,
                                                                and_block=body.block))


@app.post("/api/messages/clear")
def clear_conversation(body: NameRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _then_list(conn, player, lambda now: messages.hide_conversation(conn, player["id"], body.name, now))
