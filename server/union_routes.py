"""Unions and strikes on the website (16 November 2026): the unions, the disputes the public knows of, and the pay deals
in force. Read only: in part 1 the computer-run boards answer every demand. Nothing is shown before its day."""

from __future__ import annotations

from fastapi import Depends
from psycopg import Connection

from server.db import get_connection
from server.main import _exchange_time, app, current_player
from simulation import unions


@app.get("/api/unions")
def the_unions(_: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return unions.view(conn, _exchange_time(conn))
