"""The redesign: a player's own settings for the look and the sound, and the first-time tour.

Every request changes only the logged-in player's own settings. Nothing here touches money.
"""

from __future__ import annotations

from typing import Literal

from fastapi import Depends, HTTPException, status
from psycopg import Connection
from pydantic import Field

from server import limits
from server.db import get_connection
from server.main import _player_response, app, current_player
from server.schemas import PlayerResponse, Request


class SettingsRequest(Request):
    theme: Literal["dark", "light"] | None = None
    sound_on: bool | None = None
    sound_volume: int | None = Field(default=None, ge=0, le=100, strict=True)
    tour_done: bool | None = None


@app.patch("/api/me/settings", response_model=PlayerResponse)
def change_my_settings(body: SettingsRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    limits.allow("settings", str(player["id"]), attempts=60, per_seconds=60)
    changes = {k: v for k, v in body.model_dump().items() if v is not None}
    if not changes:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Nothing to change.")
    # Column names come only from the fixed fields above, never from what was sent.
    allowed = ("theme", "sound_on", "sound_volume", "tour_done")
    columns = [c for c in allowed if c in changes]
    sql = "UPDATE players SET " + ", ".join(f"{c} = %s" for c in columns) + " WHERE id = %s RETURNING *"
    row = conn.execute(sql, [changes[c] for c in columns] + [player["id"]]).fetchone()
    return _player_response(conn, row)
