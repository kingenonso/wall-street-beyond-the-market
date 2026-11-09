"""Take the helm of an empire, for testing only.

Run from the project root, with the game running:

    docker cp simulation/take_the_helm.py wall-street-beyond-the-market-server-1:/app/simulation/
    docker compose exec server python -m simulation.take_the_helm

It makes a player the head of an empire. If they already sit in one, they take
its helm where they are; if they sit in none, they take a seat in the empire
named and its helm with it. Nothing else changes: the empire keeps its name, its
money and its staff. From then on its computer-run staff work one step a day and
wait for the head's approvals, exactly as in an empire founded by players — so
its money stops being spent without somebody saying so.

This is the shortcut round the game's own rule, which asks for Level 20 and
three partners before an empire can be founded and opened. That rule is there
to stop a game world filling with one-player empires; it has no business
standing between the owner and a look at the screens. It refuses a live world.

  --player "Name"   whose helm it is (default: the world's only human player)
  --empire "Name"   which empire (default: the richest open one run by the computer)
"""

from __future__ import annotations

import argparse
import os
from datetime import datetime, timezone

import psycopg
from psycopg import Connection
from psycopg.rows import dict_row

from simulation import empires, ledger


def _one(conn: Connection, query: str, params: tuple = ()):
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(query, params).fetchone()


def _all(conn: Connection, query: str, params: tuple = ()) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(query, params).fetchall()


def _money(kobo: int) -> str:
    return f"₦{kobo / 100:,.2f}"


def the_player(conn: Connection, name: str | None) -> dict:
    rows = _all(conn, "SELECT id, display_name, build FROM players ORDER BY created_at, id")
    if name:
        found = [r for r in rows if r["display_name"].lower() == name.lower()]
        if not found:
            raise SystemExit(f"There is no player called {name}. This world has: "
                             + (", ".join(r["display_name"] for r in rows) or "nobody yet"))
        return found[0]
    if not rows:
        raise SystemExit("There is no player in this world. Sign up on the website first.")
    if len(rows) > 1:
        raise SystemExit("There is more than one player, so say which with --player \"Name\". They are: "
                         + ", ".join(r["display_name"] for r in rows))
    return rows[0]


def the_empire(conn: Connection, name: str | None) -> dict:
    if name:
        row = _one(conn, "SELECT * FROM empires WHERE lower(name) = lower(%s)", (name,))
        if row is None:
            raise SystemExit(f"There is no empire called {name}. This world has: "
                             + ", ".join(e["name"] for e in _all(conn, "SELECT name FROM empires ORDER BY id")))
        return row
    open_ones = _all(conn, "SELECT * FROM empires WHERE status = 'active' ORDER BY id")
    if not open_ones:
        raise SystemExit("This world has no open empire.")
    # The computer's own empires first: taking one of those is a look at the machinery rather than
    # taking somebody's company from them.
    computer = [e for e in open_ones if e["kind"] == "computer"] or open_ones
    return max(computer, key=lambda e: ledger.balance(conn, e["account_id"]))


def helm(conn: Connection, player_name: str | None = None, empire_name: str | None = None) -> dict:
    world = _one(conn, "SELECT world_start, last_closed_period FROM world_state")
    if world is None:
        raise SystemExit("The world has not been created yet.")
    if not ledger._first(conn.execute("SELECT test_world FROM world_state").fetchone()):
        raise SystemExit("This is a live world. Only a test world may be handed an empire like this.")

    player = the_player(conn, player_name)
    if not player["build"]:
        raise SystemExit(f"{player['display_name']} has not chosen a build yet. Choose one on the website first, "
                         "because a seat in an empire is a seat for a build.")

    now = datetime.now(timezone.utc)

    # Somebody who already sits in an empire takes that empire's helm, rather than a second seat.
    seat = empires.seat_of(conn, player["id"])
    if seat is not None:
        if seat["empire_kind"] == "pension":
            raise SystemExit(f"{player['display_name']} sits in {seat['empire_name']}, which is a pension fund. "
                             "A fund answers to the people whose money it holds, not to a head.")
        if empire_name and empire_name.lower() != seat["empire_name"].lower():
            raise SystemExit(f"{player['display_name']} already sits in {seat['empire_name']}. "
                             f"Say --empire \"{seat['empire_name']}\" to take its helm, or leave that empire first.")
        empire = _one(conn, "SELECT * FROM empires WHERE id = %s", (seat["empire_id"],))
        if empire["head_player_id"] == player["id"]:
            return {"already": True, "player": player["display_name"], "empire": empire["name"],
                    "build": player["build"], "cash": ledger.balance(conn, empire["account_id"])}
        try:
            with conn.transaction():
                conn.execute("UPDATE empires SET head_player_id = %s WHERE id = %s", (player["id"], empire["id"]))
                empires._log(conn, empire["id"], f"{player['display_name']} took the helm.", now)
        except empires.EmpireError as refused:
            raise SystemExit(str(refused)) from None
        return {"already": False, "player": player["display_name"], "empire": empire["name"],
                "build": player["build"], "cash": ledger.balance(conn, empire["account_id"])}

    empire = the_empire(conn, empire_name)
    if empire["status"] != "active":
        raise SystemExit(f"{empire['name']} is not open (it is {empire['status']}).")
    if empire["head_player_id"] and empire["head_player_id"] != player["id"]:
        raise SystemExit(f"{empire['name']} already has a head who is a player. Say --empire \"Name\" to pick another.")

    try:
        with conn.transaction():
            empires._take_seat(conn, empire, player["id"], player["build"], now, world["last_closed_period"])
            conn.execute("UPDATE empires SET head_player_id = %s WHERE id = %s", (player["id"], empire["id"]))
            empires._log(conn, empire["id"], f"{player['display_name']} took the helm.", now)
    except empires.EmpireError as refused:
        raise SystemExit(str(refused)) from None

    return {"already": False, "player": player["display_name"], "empire": empire["name"], "build": player["build"],
            "cash": ledger.balance(conn, empire["account_id"])}


def main() -> None:
    parser = argparse.ArgumentParser(description="Make a player the head of an empire, for testing.")
    parser.add_argument("--player", default=None, help="whose helm it is (default: the only human player)")
    parser.add_argument("--empire", default=None, help="which empire (default: the richest open one run by the computer)")
    args = parser.parse_args()

    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("Set DATABASE_URL first. See README.md.")
    with psycopg.connect(url, autocommit=True) as connection:
        done = helm(connection, args.player, args.empire)
    if done.get("already"):
        print(f"{done['player']} already heads {done['empire']}. Nothing to do.")
    else:
        build = done["build"].replace("_", " ")
        print(f"{done['player']} is now the head of {done['empire']}, holding a seat as {'an' if build[0] in 'aeiou' else 'a'} {build}.")
    print(f"The empire's account holds {_money(done['cash'])}.")
    print("Refresh the website: Empire, and the switches marked with its name on the money pages, are yours now.")


if __name__ == "__main__":
    main()
