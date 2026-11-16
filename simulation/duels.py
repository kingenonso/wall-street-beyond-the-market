"""Duels on the Floor (owner, 16 November 2026: chose "Duel on the Floor" over a private copy of the world).

An empire's head challenges another empire for the next live event. If the other head accepts (an empire the computer
runs always accepts), the two are scored against each other when the event ends: what the event did to each empire's
money (its result, as a share of what it was worth at the bell, which already counts its Floor deals in the touched
shares) plus what its members earned as banks on the Floor during the event, as a share of the same worth. The higher
score wins; both see the score as it runs. League points only (owner, 16 November 2026). Declining is free, but three
declines in a season (not answering by the bell counts) are shown on the empire's record.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from psycopg import Connection
from psycopg.rows import dict_row

from simulation import careers, empires, leagues, liveevents
from simulation import world_data as data

BPS = 10_000


class DuelError(Exception):
    """A challenge the rules do not allow, with a message for the player."""


def _rows(conn: Connection, sql: str, params=()) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def _one(conn: Connection, sql: str, params=()) -> dict | None:
    rows = _rows(conn, sql, params)
    return rows[0] if rows else None


def ready(conn: Connection) -> bool:
    return bool(_one(conn, "SELECT to_regclass('floor_duels') IS NOT NULL AS ok")["ok"])


def _season(conn: Connection, now: datetime) -> int:
    return leagues.season_of(careers.world_now(conn, now)["period"])


def _busy(conn: Connection, empire_id, bell: datetime) -> bool:
    return bool(_one(conn, "SELECT 1 AS x FROM floor_duels WHERE bell = %s AND status IN ('offered', 'accepted')"
                           " AND %s IN (challenger, challenged)", (bell, empire_id)))


def _ping(conn: Connection, empire_id) -> None:
    from simulation import pings
    pings.ping(conn, "plan", empire_id)          # the empire's screens read their page again


def challenge(conn: Connection, head_id, rival_id: int, now: datetime) -> dict:
    """The head challenges another empire to a duel at the next live event."""
    bell = liveevents.next_slot(now)
    if bell - now < timedelta(minutes=data.DUEL_CLOSES_MINUTES):
        raise DuelError(f"Challenges for the next live event close {data.DUEL_CLOSES_MINUTES} minutes before its bell.")
    with conn.transaction():
        try:
            mine = empires._head(conn, head_id)
        except empires.EmpireError as refused:
            raise DuelError(str(refused)) from None
        if mine["status"] != "active" or mine["kind"] != "player":
            raise DuelError("An empire run by players, and open, challenges.")
        rival = _one(conn, "SELECT * FROM empires WHERE id = %s", (rival_id,))
        if rival is None or rival["status"] != "active" or rival["kind"] == "pension" or rival["id"] == mine["id"]:
            raise DuelError("There is no such empire to challenge.")
        for e in (mine["id"], rival["id"]):
            if _busy(conn, e, bell):
                raise DuelError(f"{'Your empire' if e == mine['id'] else rival['name']} already has a duel at that bell.")
        computer = rival["head_player_id"] is None
        row = _one(conn, "INSERT INTO floor_duels (bell, challenger, challenged, season, status, created_at, answered_at)"
                         " VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id",
                   (bell, mine["id"], rival["id"], _season(conn, now), "accepted" if computer else "offered", now, now if computer else None))
        _ping(conn, rival["id"])
    return {"duel_id": row["id"], "accepted": computer, "bell": bell}


def answer(conn: Connection, head_id, duel_id: int, accept: bool, now: datetime) -> dict:
    with conn.transaction():
        try:
            mine = empires._head(conn, head_id)
        except empires.EmpireError as refused:
            raise DuelError(str(refused)) from None
        duel = _one(conn, "SELECT * FROM floor_duels WHERE id = %s FOR UPDATE", (duel_id,))
        if duel is None or duel["challenged"] != mine["id"]:
            raise DuelError("There is no such challenge to your empire.")
        if duel["status"] != "offered" or now >= duel["bell"]:
            raise DuelError("That challenge is no longer open.")
        conn.execute("UPDATE floor_duels SET status = %s, answered_at = %s WHERE id = %s", ("accepted" if accept else "declined", now, duel_id))
        _ping(conn, duel["challenger"])
    return {"accepted": bool(accept)}


def withdraw(conn: Connection, head_id, duel_id: int, now: datetime) -> dict:
    with conn.transaction():
        try:
            mine = empires._head(conn, head_id)
        except empires.EmpireError as refused:
            raise DuelError(str(refused)) from None
        if not conn.execute("UPDATE floor_duels SET status = 'withdrawn', answered_at = %s WHERE id = %s AND challenger = %s"
                            " AND status = 'offered' AND bell > %s", (now, duel_id, mine["id"], now)).rowcount:
            raise DuelError("There is no such challenge of yours still waiting.")
    return {"withdrawn": duel_id}


def tick(conn: Connection, now: datetime) -> None:
    """At the bell: a challenge not answered lapses (it counts as declined), and accepted duels are tied to the event."""
    if not ready(conn):
        return
    conn.execute("UPDATE floor_duels SET status = 'lapsed', answered_at = %s WHERE status = 'offered' AND bell <= %s", (now, now))
    for d in _rows(conn, "SELECT d.id, e.id AS event_id FROM floor_duels d JOIN live_events e ON e.starts_at = d.bell"
                         " WHERE d.status = 'accepted' AND d.event_id IS NULL"):
        conn.execute("UPDATE floor_duels SET event_id = %s WHERE id = %s", (d["event_id"], d["id"]))
    # A duel whose bell was missed (no event that evening) comes to nothing.
    conn.execute("UPDATE floor_duels SET status = 'void' WHERE status = 'accepted' AND event_id IS NULL AND bell < %s", (now - timedelta(hours=1),))


def _scores(conn: Connection, event: dict, duel: dict, until: datetime) -> dict:
    """Each side's score so far: the event's result for its money, plus its members' earnings as banks on the Floor during
    the event, both as a share of its worth at the bell."""
    from simulation import floor
    _, rows = liveevents._results(conn, event, until)
    by_empire = {r["empire_id"]: r for r in rows}
    banks = floor._window_scores(conn, event["starts_at"], min(until, event["ends_at"]))["bank"] \
        if _one(conn, "SELECT to_regclass('floor_trades') IS NOT NULL AS ok")["ok"] else {}
    out = {}
    for side in ("challenger", "challenged"):
        e = duel[side]
        r = by_empire.get(e)
        if r is None or r["worth_at_bell"] <= 0:
            out[side] = {"bps": 0, "event_bps": 0, "floor_bps": 0}
            continue
        members = {str(m["player_id"]) for m in _rows(conn, "SELECT player_id FROM empire_seats WHERE empire_id = %s", (e,))}
        earned = sum(v for p, v in banks.items() if str(p) in members)
        floor_bps = earned * BPS // r["worth_at_bell"]
        out[side] = {"bps": r["result_bps"] + floor_bps, "event_bps": r["result_bps"], "floor_bps": floor_bps}
    return out


def score(conn: Connection, event: dict, now: datetime) -> None:
    """When the live event is scored: each duel fought in it is decided, and the league gets its points (once)."""
    if not ready(conn):
        return
    tick(conn, now)
    period = careers.world_now(conn, now)["period"]
    for duel in _rows(conn, "SELECT * FROM floor_duels WHERE event_id = %s AND status = 'accepted' ORDER BY id", (event["id"],)):
        s = _scores(conn, event, duel, event["ends_at"])
        a, b = s["challenger"]["bps"], s["challenged"]["bps"]
        winner = duel["challenger"] if a > b else duel["challenged"] if b > a else None
        conn.execute("UPDATE floor_duels SET status = 'scored', challenger_bps = %s, challenged_bps = %s, winner = %s WHERE id = %s",
                     (a, b, winner, duel["id"]))
        names = {r["id"]: r["name"] for r in _rows(conn, "SELECT id, name FROM empires WHERE id IN (%s, %s)", (duel["challenger"], duel["challenged"]))}
        if winner:
            loser = duel["challenged"] if winner == duel["challenger"] else duel["challenger"]
            leagues.award(conn, winner, data.DUEL_WIN_POINTS, f"Won a duel on the Floor against {names[loser]}", period, now,
                          reference=f"duel:{duel['id']}:won")
        else:
            for e in (duel["challenger"], duel["challenged"]):
                leagues.award(conn, e, data.DUEL_DRAW_POINTS, "A drawn duel on the Floor", period, now, reference=f"duel:{duel['id']}:draw:{e}")
        for e in (duel["challenger"], duel["challenged"]):
            _ping(conn, e)


def declines(conn: Connection, empire_id, season: int) -> int:
    return _one(conn, "SELECT count(*)::int AS n FROM floor_duels WHERE challenged = %s AND season = %s AND status IN ('declined', 'lapsed')",
                (empire_id, season))["n"]


def view(conn: Connection, player_id, now: datetime) -> dict:
    """The player's empire's duels (offered, accepted, running with the live score, past), the empires it may challenge,
    and every empire's declines this season (shown once there are three)."""
    if not ready(conn):
        return {"ready": False}
    seat = empires.seat_of(conn, player_id)
    mine = seat["empire_id"] if seat and seat["empire_status"] == "active" and seat["empire_kind"] == "player" else None
    season = _season(conn, now)
    bell = liveevents.next_slot(now)
    names = {r["id"]: r for r in _rows(conn, "SELECT id, name, head_player_id IS NULL AS computer FROM empires WHERE status = 'active' AND kind <> 'pension'")}
    out = []
    if mine:
        for d in _rows(conn, "SELECT * FROM floor_duels WHERE %s IN (challenger, challenged) ORDER BY bell DESC, id DESC LIMIT 12", (mine,)):
            other = d["challenged"] if d["challenger"] == mine else d["challenger"]
            row = {"id": d["id"], "bell": d["bell"], "status": d["status"], "you_challenged": d["challenger"] == mine,
                   "rival": names.get(other, {"name": "An empire"})["name"],
                   "you_bps": d["challenger_bps"] if d["challenger"] == mine else d["challenged_bps"],
                   "rival_bps": d["challenged_bps"] if d["challenger"] == mine else d["challenger_bps"],
                   "won": None if d["status"] != "scored" else (d["winner"] == mine if d["winner"] else None),
                   "live": None}
            if d["status"] == "accepted" and d["event_id"]:
                event = _one(conn, "SELECT * FROM live_events WHERE id = %s", (d["event_id"],))
                if event and event["status"] == "open":
                    s = _scores(conn, event, d, min(now, event["ends_at"]))
                    you, rival = (s["challenger"], s["challenged"]) if d["challenger"] == mine else (s["challenged"], s["challenger"])
                    row["live"] = {"you": you, "rival": rival}
            out.append(row)
    is_head = bool(seat and mine and seat["head_player_id"] == player_id)
    taken = {r["e"] for r in _rows(conn, "SELECT challenger AS e FROM floor_duels WHERE bell = %s AND status IN ('offered', 'accepted')"
                                         " UNION SELECT challenged FROM floor_duels WHERE bell = %s AND status IN ('offered', 'accepted')", (bell, bell))}
    return {
        "ready": True, "now": now, "next_bell": bell, "closes_at": bell - timedelta(minutes=data.DUEL_CLOSES_MINUTES),
        "empire": names[mine]["name"] if mine in names else None, "is_head": is_head,
        "points": {"win": data.DUEL_WIN_POINTS, "draw": data.DUEL_DRAW_POINTS},
        "duels": out,
        "rivals": [{"id": e, "name": r["name"], "computer": r["computer"], "free": e not in taken,
                    "declines": declines(conn, e, season)} for e, r in sorted(names.items(), key=lambda kv: kv[1]["name"]) if e != mine],
        "shown_declines": data.DUEL_DECLINES_SHOWN,
    }
