"""A health check of a running world, in plain words. It only reads: nothing is changed.

Run it with the game up:

    docker compose exec server python -m simulation.check_world

It checks:

  * the books: the whole ledger re-added, and every part of the game checking its own, as at each quarter's close;
  * the empires: every player-run empire's head in their own chair, and no build holding more members than it has seats
    (the seven places of the three builds, 14 November 2026);
  * the database changes: every one applied;
  * the Government: who governs this year, and the tax rates in force.
"""

from __future__ import annotations

import os
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

from simulation import quarters


def _rows(conn, sql: str, params=()) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def check(conn) -> list[str]:
    """Every fault found, in words. An empty list means the world is sound."""
    faults: list[str] = []

    world = _rows(conn, "SELECT last_closed_period FROM world_state")
    if not world:
        return ["There is no world yet."]
    print(f"The world has closed {world[0]['last_closed_period']} quarters.")

    # The database changes.
    wanted = sorted(p.name for p in (Path(__file__).resolve().parent.parent / "database" / "migrations").glob("*.sql"))
    done = {r["name"] for r in _rows(conn, "SELECT name FROM schema_migrations")} if _rows(
        conn, "SELECT to_regclass('schema_migrations') IS NOT NULL AS ok")[0]["ok"] else set()
    missing = [m for m in wanted if m not in done]
    if missing:
        faults.append(f"Database changes not yet applied: {', '.join(missing)}. Restart the server to apply them.")
    else:
        print(f"Database changes: all {len(wanted)} applied.")

    # The books.
    problems = quarters.book_problems(conn)
    if problems:
        faults.append("The books do not add up: " + " ".join(problems))
    else:
        print("The books: the ledger re-adds to zero, every balance matches its entries, and every part's own books agree.")

    # The empires.
    empires = _rows(conn, "SELECT id, name, head_player_id FROM empires WHERE kind = 'player' AND status IN ('active', 'forming')"
                          " ORDER BY name")
    print(f"Empires run by players: {len(empires)}.")
    for e in empires:
        seats = _rows(conn, "SELECT build, slot, player_id FROM empire_seats WHERE empire_id = %s", (e["id"],))
        if e["head_player_id"]:
            chair = [s for s in seats if s["player_id"] == e["head_player_id"]]
            if not chair:
                faults.append(f"{e['name']}: its head holds no seat.")
            elif chair[0]["slot"] != 0:
                faults.append(f"{e['name']}: its head sits in an ordinary seat (slot {chair[0]['slot']}), not the head's chair.")
        held = {}
        for s in seats:
            if s["player_id"] and s["slot"] > 0:
                held[s["build"]] = held.get(s["build"], 0) + 1
        for build, n in held.items():
            room = sum(1 for s in seats if s["build"] == build and s["slot"] > 0)
            if n > room:
                faults.append(f"{e['name']}: {n} members in {room} {build.replace('_', ' ')} seats.")
        chairs = sum(1 for s in seats if s["slot"] == 0)
        if chairs > 1:
            faults.append(f"{e['name']}: {chairs} head's chairs; there should be one.")
    if empires and not any(f.split(":")[0] in {e["name"] for e in empires} for f in faults):
        print("Every empire's head is in the head's chair, and no build has more members than seats.")

    # The Government.
    terms = _rows(conn, "SELECT t.year, t.stand_in, p.display_name FROM government_terms t LEFT JOIN players p ON p.id = t.leader_id"
                        " ORDER BY t.year DESC LIMIT 1") if _rows(
        conn, "SELECT to_regclass('government_terms') IS NOT NULL AS ok")[0]["ok"] else []
    if terms:
        t = terms[0]
        who = t["display_name"] or f"the stand-in ({t['stand_in']})"
        rates = {r["kind"]: r["bps"] for r in _rows(conn, "SELECT kind, bps FROM tax_rates")}
        print(f"Government, game year {t['year']}: {who}. Taxes: " +
              ", ".join(f"{k} {v / 100:.2f}%" for k, v in sorted(rates.items())) + ".")
    return faults


def main() -> None:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL is not set.")
    with psycopg.connect(url) as conn:
        conn.read_only = True
        faults = check(conn)
    if faults:
        print("\nFOUND:")
        for f in faults:
            print(f"  - {f}")
        raise SystemExit(1)
    print("\nAll is well.")


if __name__ == "__main__":
    main()
