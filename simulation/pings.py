"""Telling open screens that something changed (live events, part 2 of the owner's 16 November 2026 "build": updates
that appear the moment something happens, and an empire chat on the Live events page).

A ping carries no figures and no words: only what kind of thing changed, and for which empire. A screen that hears it
asks the server for its page again, and the page shows that player only what they may see. So a ping can never leak a
sealed prediction or a rival empire's chat, even if it reached the wrong screen.

The ping goes out through the database, inside the same transaction as the change, so it is heard only once the change
is saved, and every server process hears it.
"""

from __future__ import annotations

import json

from psycopg import Connection

CHANNEL = "wsbm_live"

# What a ping can say. "event": a bell rang, a plan acted, or an event was scored. "prediction": an empire sealed one (the
# count is public). "chat": a message in an empire's War Room. "plan": an empire's standing plan changed.
FOR_EVERYBODY = {"event", "prediction"}
FOR_THE_EMPIRE = {"chat", "plan"}
# The Floor (16 November 2026): "floor" goes to one player: a request reached their desk, a price reached them, or a deal
# they were part of was done.
FOR_THE_PLAYER = {"floor"}
KINDS = FOR_EVERYBODY | FOR_THE_EMPIRE | FOR_THE_PLAYER


def ping(conn: Connection, what: str, empire_id: int | None = None, *, player: str | None = None) -> None:
    if what not in KINDS:
        raise ValueError(f"Not a kind of ping: {what}")
    if (what in FOR_THE_PLAYER) != (player is not None):
        raise ValueError("A floor ping names its player; no other ping does.")
    heard = {"what": what, "empire": empire_id}
    if player is not None:
        heard["player"] = str(player)
    conn.execute("SELECT pg_notify(%s, %s)", (CHANNEL, json.dumps(heard)))


def read(payload: str) -> dict | None:
    """A ping as heard; None for anything that is not one."""
    try:
        heard = json.loads(payload)
    except ValueError:
        return None
    if not isinstance(heard, dict) or heard.get("what") not in KINDS:
        return None
    empire = heard.get("empire")
    if empire is not None and (not isinstance(empire, int) or isinstance(empire, bool)):
        return None
    if heard["what"] in FOR_THE_EMPIRE and empire is None:
        return None
    if heard["what"] in FOR_THE_PLAYER:
        player = heard.get("player")
        if not isinstance(player, str) or not player:
            return None
        return {"what": heard["what"], "empire": None, "player": player}
    return {"what": heard["what"], "empire": empire}
