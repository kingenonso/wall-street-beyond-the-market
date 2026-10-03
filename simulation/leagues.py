"""Leagues (design document, section 9).

Empires compete in divisions of five. Points are earned through a game year by finishing work
together; as the year ends the top of each division goes up and the bottom goes down. Every
player is also ranked within their build. The tables are public.

Points come only from things the game itself records: a finished task, work passed for the
empire, a weekend challenge passed by a member, an offence uncovered, and how the empire's worth
grew over the year (money put in by its members is taken out first, so growth cannot be bought).
"""

from __future__ import annotations

from datetime import datetime

from psycopg import Connection
from psycopg.rows import dict_row

from simulation import careers, clock
from simulation import world_data as data


def _rows(conn: Connection, sql: str, params=()) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def _one(conn: Connection, sql: str, params=()) -> dict | None:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchone()


def season_of(period: int) -> int:
    """The game year a quarter belongs to."""
    return (max(period, 1) - 1) // clock.QUARTERS_PER_YEAR + 1


def award(conn: Connection, empire_id, points: int, why: str, period: int, now: datetime, reference: str | None = None) -> bool:
    """Add (or take) league points. The same thing is never counted twice."""
    if points == 0:
        return False
    done = conn.execute(
        "INSERT INTO league_points (empire_id, season, period, points, why, reference, at) VALUES (%s, %s, %s, %s, %s, %s, %s)"
        " ON CONFLICT DO NOTHING", (empire_id, season_of(period), period, points, why[:200], reference, now)).rowcount
    return bool(done)


def work_passed(conn: Connection, objective: dict, period: int, now: datetime) -> None:
    """A member passed work for their empire, or a weekend challenge: the empire they sit in gains points."""
    seat = _one(conn, "SELECT s.empire_id FROM empire_seats s JOIN empires e ON e.id = s.empire_id"
                      " WHERE s.player_id = %s AND e.status = 'active' AND e.kind <> 'pension'", (objective["player_id"],))
    if seat is None:
        return
    if objective["setting"] == "empire":
        if str(objective["terms"].get("empire_id", seat["empire_id"])) != str(seat["empire_id"]):
            return                                   # the work was for an empire they have since left
        award(conn, seat["empire_id"], data.LEAGUE_POINTS["work"], f"Work passed for the empire: {objective['title']}", period, now,
              reference=f"objective:{objective['id']}")
    else:
        award(conn, seat["empire_id"], data.LEAGUE_POINTS["challenge"], f"A member passed a weekend challenge: {objective['title']}",
              period, now, reference=f"objective:{objective['id']}")


def place_new(conn: Connection, empire_id) -> int:
    """A newly opened empire enters the bottom division, or a new one below it if that is full."""
    bottom = _one(conn, "SELECT coalesce(max(division), 1) AS d FROM empires WHERE status = 'active' AND kind <> 'pension' AND id <> %s",
                  (empire_id,))["d"]
    there = _one(conn, "SELECT count(*) AS n FROM empires WHERE status = 'active' AND kind <> 'pension' AND division = %s AND id <> %s",
                 (bottom, empire_id))["n"]
    division = bottom if there < data.DIVISION_SIZE else bottom + 1
    conn.execute("UPDATE empires SET division = %s WHERE id = %s", (division, empire_id))
    return division


def _worth_now(conn: Connection, empire: dict, now: datetime) -> int:
    from simulation import empires
    return empires.worth(conn, empire, now)["total"]


def table(conn: Connection, now: datetime, period: int | None = None) -> list[dict]:
    """Every division, top first, with each empire's points this game year."""
    if period is None:
        period = careers.world_now(conn, now)["period"]
    season = season_of(period)
    points = {r["empire_id"]: r for r in _rows(
        conn, "SELECT empire_id, sum(points)::int AS points, count(*) AS entries FROM league_points WHERE season = %s GROUP BY empire_id", (season,))}
    divisions: dict[int, list] = {}
    for empire in _rows(conn, "SELECT e.*, (SELECT count(*) FROM empire_seats s WHERE s.empire_id = e.id AND s.player_id IS NOT NULL) AS members"
                              " FROM empires e WHERE e.status = 'active' AND e.kind <> 'pension' ORDER BY e.id"):
        divisions.setdefault(empire["division"], []).append({
            "id": empire["id"], "name": empire["name"], "kind": empire["kind"], "division": empire["division"],
            "run_by": "players" if empire["head_player_id"] else "the computer", "members": empire["members"], "trust": empire["trust"],
            "points": points.get(empire["id"], {}).get("points", 0), "worth": _worth_now(conn, empire, now)})
    out = []
    lowest = max(divisions) if divisions else 1
    for number in sorted(divisions):
        rows = sorted(divisions[number], key=lambda e: (-e["points"], -e["worth"], e["id"]))
        for place, row in enumerate(rows, 1):
            row["place"] = place
            row["zone"] = ("up" if number > 1 and place <= data.DIVISION_MOVES
                           else "down" if number < lowest and place > len(rows) - data.DIVISION_MOVES else None)
        out.append({"division": number, "empires": rows})
    return out


def standing(conn: Connection, empire_id, now: datetime) -> dict | None:
    for division in table(conn, now):
        for row in division["empires"]:
            if row["id"] == empire_id:
                return {**row, "of": len(division["empires"])}
    return None


def history(conn: Connection, empire_id, period: int) -> list[dict]:
    """Why an empire's points changed this game year, newest first."""
    return _rows(conn, "SELECT points, why, period, at FROM league_points WHERE empire_id = %s AND season = %s ORDER BY id DESC LIMIT 40",
                 (empire_id, season_of(period)))


def _growth_points(conn: Connection, empire: dict, period: int) -> tuple[int, str] | None:
    """Points for how the empire's worth grew over the game year, with money its members put in
    (or took back) during the year left out."""
    first = period - clock.QUARTERS_PER_YEAR
    start = _one(conn, "SELECT worth, period FROM empire_worth WHERE empire_id = %s AND period >= %s ORDER BY period LIMIT 1",
                 (empire["id"], first))
    end = _one(conn, "SELECT worth FROM empire_worth WHERE empire_id = %s AND period = %s", (empire["id"], period))
    if start is None or end is None or start["period"] >= period or start["worth"] <= 0:
        return None
    put_in = _one(conn, "SELECT coalesce(sum(amount), 0)::bigint AS total FROM empire_capital WHERE empire_id = %s AND period > %s"
                        " AND period <= %s", (empire["id"], start["period"], period))["total"]
    # Money taken from the empire and then paid back with a fine is not growth either: it is left out both ways, so that a
    # staged theft and its fine cannot buy a place in the league.
    fines = _one(conn, "SELECT coalesce(sum(repaid), 0)::bigint AS total FROM empire_cases WHERE empire_id = %s AND decided_period > %s"
                       " AND decided_period <= %s", (empire["id"], start["period"], period))["total"]
    taken = _one(conn, "SELECT coalesce(sum(amount), 0)::bigint AS total FROM empire_books WHERE empire_id = %s AND kind = 'taken'"
                       " AND period > %s AND period <= %s", (empire["id"], start["period"], period))["total"]
    put_in += max(fines - taken, 0)
    grew = (end["worth"] - put_in - start["worth"]) / start["worth"] * 100
    most = data.LEAGUE_POINTS["growth_most"]
    points = max(-most, min(most, round(grew)))
    return points, f"Worth {'grew' if grew >= 0 else 'fell'} {abs(grew):.1f}% over the game year (money put in by members left out)"


def end_season(conn: Connection, period: int, now: datetime) -> list[dict]:
    """As a game year ends: count growth, write the final table down, and move the top of each
    division up and the bottom down. Returns what moved."""
    season = season_of(period)
    with conn.transaction():
        conn.execute("SELECT 1 FROM world_state FOR UPDATE")
        if _one(conn, "SELECT 1 FROM league_seasons WHERE season = %s LIMIT 1", (season,)):
            return []
        for empire in _rows(conn, "SELECT * FROM empires WHERE status = 'active' AND kind <> 'pension' ORDER BY id"):
            growth = _growth_points(conn, empire, period)
            if growth:
                award(conn, empire["id"], growth[0], growth[1], period, now, reference=f"growth:{season}")
        final = table(conn, now, period)
        moves = {}
        for upper, lower in zip(final, final[1:]):
            if upper["division"] + 1 != lower["division"]:
                continue
            count = min(data.DIVISION_MOVES, len(lower["empires"]), max(len(upper["empires"]) - 1, 0))
            for row in upper["empires"][len(upper["empires"]) - count:]:
                moves[row["id"]] = ("down", lower["division"])
            for row in lower["empires"][:count]:
                moves[row["id"]] = ("up", upper["division"])
        moved = []
        for division in final:
            for row in division["empires"]:
                way, to = moves.get(row["id"], ("stayed", division["division"]))
                conn.execute("INSERT INTO league_seasons (season, empire_id, division, place, points, moved) VALUES (%s, %s, %s, %s, %s, %s)",
                             (season, row["id"], division["division"], row["place"], row["points"], way))
                if way != "stayed":
                    conn.execute("UPDATE empires SET division = %s WHERE id = %s", (to, row["id"]))
                    conn.execute("INSERT INTO empire_events (empire_id, words, at) VALUES (%s, %s, %s)",
                                 (row["id"], f"Game year {season} ended. The empire finished {_place(row['place'])} in Division "
                                             f"{division['division']} with {row['points']} points and moves {way} to Division {to}.", now))
                    moved.append({"empire_id": row["id"], "name": row["name"], "moved": way, "to": to})
        return moved


def _place(n: int) -> str:
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def after_close(conn: Connection, period: int, now: datetime) -> None:
    if period >= clock.QUARTERS_PER_YEAR and period % clock.QUARTERS_PER_YEAR == 0:
        end_season(conn, period, now)


def past_seasons(conn: Connection, limit: int = 3) -> list[dict]:
    seasons = [r["season"] for r in _rows(conn, "SELECT DISTINCT season FROM league_seasons ORDER BY season DESC LIMIT %s", (limit,))]
    return [{"season": season, "rows": _rows(
        conn, "SELECT s.division, s.place, s.points, s.moved, e.name FROM league_seasons s JOIN empires e ON e.id = s.empire_id"
              " WHERE s.season = %s ORDER BY s.division, s.place", (season,))} for season in seasons]


def build_table(conn: Connection, build: str, player_id=None, limit: int = 20) -> dict:
    """Every player ranked within their build: by level, then by experience. Public."""
    rows = _rows(conn, "SELECT p.id, p.display_name, c.experience, c.rank, p.reputation FROM careers c JOIN players p ON p.id = c.player_id"
                       " WHERE c.build = %s AND p.build = %s", (build, build))
    for row in rows:
        row["level"] = careers.level_for(row["experience"], row["rank"])
    rows.sort(key=lambda r: (-r["level"], -r["experience"], r["display_name"].lower()))
    yours = next((n for n, r in enumerate(rows, 1) if r["id"] == player_id), None)
    return {"build": build, "name": careers.BUILDS[build]["name"], "players": len(rows), "your_place": yours,
            "top": [{"place": n, "name": r["display_name"], "level": r["level"], "rank_name": careers.rank_name(r["rank"]),
                     "you": r["id"] == player_id} for n, r in enumerate(rows[:limit], 1)]}
