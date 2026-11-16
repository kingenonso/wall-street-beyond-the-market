"""Live events, part 2 (owner, 16 November 2026: "build", for updates that appear the moment something changes): every
open Live events page, and the desk's live strip, keeps one quiet line open to the server, and is told at once when a
bell rings, a member seals a prediction, the empire's chat has a new message, the standing plan changes, or an event is
scored. The screen then asks for its page again, as it always did.

What is sent down the line is only the kind of change ("event", "prediction", "chat", "plan"), never a figure or a
message: everything the player sees still comes from the page, which shows them only what they may see. A chat or plan
ping goes only to that empire's members.

How it works inside: the database carries each ping (simulation/pings.py) once the change is saved; one listener per
server process hears them all and hands each one to the open lines that should hear it. Waiting costs no database
connection: a line uses one only for a moment when it opens and once every half minute to check that the player is still
logged in.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from itertools import count

import psycopg
from fastapi import Cookie, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from server import limits, security
from server.config import get_settings
from server.db import connection
from simulation import empires, pings

log = logging.getLogger("wsbm.live")

KEEPALIVE_SECONDS = 25            # a quiet line says it is still there, and checks the player is still logged in
LINE_SECONDS = 20 * 60            # a line is closed after twenty minutes; the browser opens a fresh one by itself
RETRY_MS = 3_000                  # how soon the browser tries again after a line drops
MOST_LINES_EACH = 4               # one player's open tabs
MOST_LINES = 5_000                # the whole server
QUEUE_SIZE = 32                   # pings waiting for one slow screen; beyond that they are dropped (one is enough)


@dataclass(eq=False)
class Line:
    player_id: str
    empire_id: int | None
    loop: asyncio.AbstractEventLoop
    queue: asyncio.Queue = field(default_factory=lambda: asyncio.Queue(QUEUE_SIZE))
    key: int = 0


class Hub:
    """The open lines, and who should hear each ping."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._lines: dict[int, Line] = {}
        self._keys = count(1)

    def _full(self, player_id: str) -> bool:
        return len(self._lines) >= MOST_LINES or sum(1 for x in self._lines.values() if x.player_id == player_id) >= MOST_LINES_EACH

    def has_room(self, player_id: str) -> bool:
        with self._lock:
            return not self._full(player_id)

    def open(self, player_id: str, empire_id: int | None, loop: asyncio.AbstractEventLoop) -> Line | None:
        with self._lock:
            if self._full(player_id):
                return None
            line = Line(player_id, empire_id, loop, key=next(self._keys))
            self._lines[line.key] = line
            return line

    def close(self, line: Line) -> None:
        with self._lock:
            self._lines.pop(line.key, None)

    def size(self) -> int:
        with self._lock:
            return len(self._lines)

    @staticmethod
    def hears(line: Line, heard: dict) -> bool:
        if heard["what"] in pings.FOR_EVERYBODY:
            return True
        return line.empire_id is not None and line.empire_id == heard["empire"]

    def deliver(self, heard: dict) -> int:
        """Hand a ping to every line that should hear it (called from the listener's thread). How many heard it."""
        with self._lock:
            lines = [x for x in self._lines.values() if self.hears(x, heard)]
        for line in lines:
            try:
                line.loop.call_soon_threadsafe(_offer, line.queue, heard["what"])
            except RuntimeError:                 # that line's loop has closed: it is going away
                pass
        return len(lines)


def _offer(queue: asyncio.Queue, what: str) -> None:
    try:
        queue.put_nowait(what)
    except asyncio.QueueFull:
        pass


hub = Hub()


# ---------------------------------------------------------------------------
# The listener: one per server process
# ---------------------------------------------------------------------------

class Listener:
    def __init__(self) -> None:
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.listening = threading.Event()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="live-pushes", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
        self.listening.clear()

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                with psycopg.connect(get_settings().database_url, autocommit=True) as conn:
                    conn.execute(f"LISTEN {pings.CHANNEL}")
                    if self.listening.is_set():
                        # Back after a dropped connection: something may have happened meanwhile, so every screen looks again.
                        hub.deliver({"what": "event", "empire": None})
                    self.listening.set()
                    while not self._stop.is_set():
                        for note in conn.notifies(timeout=1.0):
                            heard = pings.read(note.payload)
                            if heard:
                                hub.deliver(heard)
            except Exception:                    # the database went away for a moment: try again shortly
                log.exception("The live pushes lost the database; trying again.")
                self._stop.wait(3)


listener = Listener()


# ---------------------------------------------------------------------------
# The line itself
# ---------------------------------------------------------------------------

def _who(session: str | None) -> tuple[str, int | None] | None:
    """The logged-in player and the empire run by players they belong to, or None if the pass is not good."""
    named = security.read_session_token(session) if session else None
    if not named:
        return None
    with connection() as conn:
        row = conn.execute("SELECT id FROM players WHERE id = %s AND session_version = %s", named).fetchone()
        if row is None:
            return None
        seat = empires.seat_of(conn, row["id"])
    empire_id = seat["empire_id"] if seat and seat["empire_status"] == "active" and seat["empire_kind"] == "player" else None
    return str(row["id"]), empire_id


def _say(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


async def _flow(request: Request, session: str | None, who: tuple[str, int | None]) -> AsyncIterator[str]:
    loop = asyncio.get_running_loop()
    ends = loop.time() + LINE_SECONDS
    yield f"retry: {RETRY_MS}\n\n"
    # The line is opened here, once the browser is reading, so it is always closed again in `finally`.
    line = hub.open(who[0], who[1], loop)
    if line is None:
        yield _say("bye", {"why": "Too many live pages are open."})
        return
    try:
        yield _say("hello", {})
        while loop.time() < ends:
            try:
                what = await asyncio.wait_for(line.queue.get(), timeout=KEEPALIVE_SECONDS)
            except TimeoutError:
                if await request.is_disconnected():
                    return
                again = await asyncio.to_thread(_who, session)
                if again is None or again[0] != line.player_id:
                    yield _say("bye", {})        # logged out: the screen stops listening
                    return
                line.empire_id = again[1]        # joined or left an empire meanwhile
                yield ": still here\n\n"
                continue
            # A burst of pings (many members sealing at once) becomes one: the screen loads its page once.
            kinds = {what}
            while not line.queue.empty():
                kinds.add(line.queue.get_nowait())
            yield _say("changed", {"what": sorted(kinds)})
    finally:
        hub.close(line)


async def live_stream(request: Request, session: str | None = Cookie(default=None, alias=security.SESSION_COOKIE)):
    who = await asyncio.to_thread(_who, session)
    if who is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Please log in.")
    limits.allow("live-stream", who[0], attempts=30, per_seconds=60)
    if not hub.has_room(who[0]):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many live pages are open. Close one and try again.")
    return StreamingResponse(_flow(request, session, who), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
