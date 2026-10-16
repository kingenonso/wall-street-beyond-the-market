"""Stage 10: named clients who come back (the owner's loose ends, 12 October 2026, starting with the Journalist).

Each media house has an editor who gives a journalist work. An editor remembers: work done well raises their trust,
work done badly lowers it twice as fast. An editor whose trust falls below 30 stops offering work; one whose trust
reaches 70 offers the front-page piece kept for the people they rely on.
"""

from __future__ import annotations

from psycopg import Connection
from psycopg.rows import dict_row

CLIENTS = {
    "herald_editor": ("Mrs Adaeze Okafor", "the editor of The Lagoon Herald"),
    "ledger_editor": ("Mr Tunde Bakare", "the editor of The Naira Ledger"),
    "ogene_editor": ("Ms Halima Sani", "the news editor at Ogene News Network"),
}
PAPER = {"herald_editor": "TLH", "ledger_editor": "TNL", "ogene_editor": "ONN"}    # the paper that pays for the editor's work
PIECES: dict[str, str] = {}             # piece of work -> the editor who gives it (filled in by objectives_gap.piece)
START, RISE, FALL = 50, 5, 10
HEALS = 5                               # each quarter's close, an editor who has cooled comes back towards 50
STOPS_BELOW, TRUSTED = 30, 70
PREMIUM_LEVELS = (36,)                 # the front-page piece: offered only by an editor who trusts the player


def _rows(conn: Connection, sql: str, params=()) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def trust(conn: Connection, player_id, client: str) -> int:
    row = _rows(conn, "SELECT trust FROM client_trust WHERE player_id = %s AND client = %s", (player_id, client))
    return row[0]["trust"] if row else START


def introduce(client: str) -> str:
    name, role = CLIENTS[client]
    return f"{name}, {role}, has work for you."


def offers(conn: Connection, player_id, client: str, level: int) -> bool:
    t = trust(conn, player_id, client)
    if t < STOPS_BELOW:
        return False
    return t >= TRUSTED if level in PREMIUM_LEVELS else True


def judged(conn: Connection, player_id, client: str, passed: bool) -> int:
    change = RISE if passed else -FALL
    row = _rows(conn, "INSERT INTO client_trust (player_id, client, trust, pieces) VALUES (%s, %s, %s, 1)"
                      " ON CONFLICT (player_id, client) DO UPDATE SET trust = least(greatest(client_trust.trust + %s, 0), 100),"
                      " pieces = client_trust.pieces + 1 RETURNING trust",
                (player_id, client, min(max(START + change, 0), 100), change))
    return row[0]["trust"]


def at_close(conn: Connection) -> None:
    """Time heals: an editor below the middle comes back a little each quarter, so a player can win them round again."""
    conn.execute("UPDATE client_trust SET trust = least(trust + %s, %s) WHERE trust < %s", (HEALS, START, START))


def view(conn: Connection, player_id) -> list[dict]:
    return [{"client": code, "name": name, "role": role, "trust": trust(conn, player_id, code),
             "offering": trust(conn, player_id, code) >= STOPS_BELOW} for code, (name, role) in CLIENTS.items()]
