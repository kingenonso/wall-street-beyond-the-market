"""Alerts on the website (18 November 2026): the alerts a player has set and those hit; set one, remove one, and mark
those hit as seen. Every answer is the whole alerts page again."""

from __future__ import annotations

from fastapi import Depends, HTTPException, status
from psycopg import Connection
from pydantic import Field

from server import limits
from server.db import get_connection
from server.main import _exchange_time, app, current_player
from server.schemas import Request
from simulation import alerts


def _wire(value, key: str | None = None):
    if isinstance(value, dict):
        return {k: _wire(v, k) for k, v in value.items()}
    if isinstance(value, list):
        return [_wire(v, key) for v in value]
    if key == "level" and isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    return value


class AlertRequest(Request):
    kind: str = Field(pattern="^(above|below|move|news|storm|wealth)$")
    ticker: str | None = Field(default=None, pattern="^[A-Za-z]{3}$")
    level: int | None = Field(default=None, gt=0, le=10**12, strict=True)
    note: str | None = Field(default=None, max_length=200)


class AlertIdRequest(Request):
    alert_id: int = Field(gt=0, strict=True)


def _page(conn: Connection, player: dict, done=None) -> dict:
    page = alerts.view(conn, player["id"])
    if done is not None:
        page["result"] = done
    return _wire(page)


@app.get("/api/alerts")
def my_alerts(player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _page(conn, player)


@app.post("/api/alerts")
def set_an_alert(body: AlertRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    limits.allow("alerts", str(player["id"]), attempts=30, per_seconds=60)
    try:
        done = alerts.add(conn, player["id"], body.kind, body.ticker, body.level, body.note, _exchange_time(conn))
    except alerts.AlertError as refused:
        raise HTTPException(status.HTTP_409_CONFLICT, str(refused)) from None
    return _page(conn, player, done)


@app.post("/api/alerts/remove")
def remove_an_alert(body: AlertIdRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    try:
        alerts.remove(conn, player["id"], body.alert_id)
    except alerts.AlertError as refused:
        raise HTTPException(status.HTTP_409_CONFLICT, str(refused)) from None
    return _page(conn, player)


@app.post("/api/alerts/seen")
def alerts_seen(player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    alerts.mark_seen(conn, player["id"])
    return _page(conn, player)
