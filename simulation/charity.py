"""Stage 10, Part 2: charity foundations (owner's suggestion 10).

A player, or an empire (through its head), can found a charity for a cause (education, health, clean water, the arts,
disaster relief) in one of the five cities, with at least ₦1 million of their own. Anyone may give to it. Its trustee
(the founder, or the founding empire's head) makes grants: to the cause, which reaches the city's households, or to a
person (a scholarship, an award).

Giving builds reputation, but only what really goes to the cause: each quarter the founder's reputation rises with what
the charity granted to its cause (an empire, a point for each ₦25 million, at most three a quarter; a player, a point for
each ₦5 million, at most two).

Abuse is possible: grants to people connected to the founder or the donors move money to insiders under a good name. The
Money Watch flags a charity whose grants to connected people pass a quarter of what it grants (a private list), and a
Financial Journalist can investigate it. Prosecution waits for Stages 11 and 12. A charity's totals are public; whether a
grant was to someone connected is not.
"""

from __future__ import annotations

from datetime import datetime

from psycopg import Connection, errors
from psycopg.rows import dict_row

from simulation import careers, clock, ledger, standing
from simulation import world_data as data
from simulation.money import BPS, naira


class CharityError(Exception):
    """Something the rules for charities do not allow. The words are for the player."""


def _rows(conn: Connection, sql: str, params=()) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def _one(conn: Connection, sql: str, params=()) -> dict | None:
    rows = _rows(conn, sql, params)
    return rows[0] if rows else None


def ready(conn: Connection) -> bool:
    return bool(_rows(conn, "SELECT to_regclass('charities') IS NOT NULL AS ok")[0]["ok"])


def _period(conn: Connection, now: datetime) -> int:
    return careers.world_now(conn, now)["period"]


def _money(kobo: int) -> str:
    from simulation import newsroom_facts
    return newsroom_facts.money(kobo)


def _head_empire(conn: Connection, player_id) -> dict:
    e = _one(conn, "SELECT * FROM empires WHERE head_player_id = %s AND status = 'active' AND kind = 'player'", (player_id,))
    if e is None:
        raise CharityError("Only the head of an open empire acts for it.")
    return e


def _empire_spend(conn: Connection, empire: dict, player_id, amount: int, period: int) -> None:
    """The empire's money given away counts against what its head may sign for in a quarter, as any other spending does."""
    from simulation import empires
    seat = empires.seat_of(conn, player_id)
    room = empires.signing_limit(conn, seat) - empires._spent(conn, empire["id"], player_id, period)
    if amount > room:
        raise CharityError(f"That is more of the empire's money than you may sign for this quarter (₦{max(room, 0) // 100:,} left).")


def found(conn: Connection, player_id, name: str, cause: str, city: str, amount: int, now: datetime, *, for_empire: bool = False) -> dict:
    name = " ".join((name or "").split())
    if not 4 <= len(name) <= 60:
        raise CharityError("A charity's name is between 4 and 60 characters.")
    if any(ch.isdigit() for ch in name) or "₦" in name or "%" in name or not all(ch.isprintable() for ch in name):
        raise CharityError("A charity's name is in words, with no figures.")
    if cause not in data.CHARITY_CAUSES:
        raise CharityError("Choose its cause: " + ", ".join(data.CHARITY_CAUSES.values()) + ".")
    if city not in data.CITY_COST_BPS:
        raise CharityError("Choose one of the five cities.")
    if amount < naira(data.CHARITY_LEAST_FOUNDING_NAIRA):
        raise CharityError(f"A charity is founded with at least ₦{data.CHARITY_LEAST_FOUNDING_NAIRA:,}.")
    period = _period(conn, now)
    with conn.transaction():
        empire = _head_empire(conn, player_id) if for_empire else None
        if empire:
            _empire_spend(conn, empire, player_id, amount, period)
        payer = empire["account_id"] if empire else ledger.player_account_id(conn, player_id)
        account = ledger.create_account(conn, kind="charity", name=f"Charity: {name}")
        try:
            with conn.transaction():
                row = _one(conn, "INSERT INTO charities (name, cause, city, founder_player, founder_empire, trustee_id, account_id, period, at)"
                                 " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING *",
                           (name, cause, city, None if empire else player_id, empire["id"] if empire else None, player_id, account, period, now))
        except errors.UniqueViolation:
            raise CharityError("That name is taken, or you (or your empire) already run a charity.") from None
        try:
            ledger.transfer(conn, payer=payer, receiver=account, amount=amount, kind="charity_gift", memo=f"Founding {name}", period=period)
        except ledger.InsufficientFunds:
            raise CharityError("There is not the cash to found it with that much.") from None
        conn.execute("INSERT INTO charity_gifts (charity_id, from_player, from_empire, amount, period, at) VALUES (%s, %s, %s, %s, %s, %s)",
                     (row["id"], None if empire else player_id, empire["id"] if empire else None, amount, period, now))
        if empire:
            from simulation import empires
            empires._book(conn, empire["id"], period, "Charity", f"Founding {name}", amount, True, now, entered_by=player_id)
            empires._log(conn, empire["id"], f"The empire founded a charity, {name}, with {_money(amount)}.", now)
    return view(conn, row["id"], player_id)


def _charity(conn: Connection, charity_id: int, *, lock: bool = False) -> dict:
    c = _one(conn, "SELECT * FROM charities WHERE id = %s" + (" FOR UPDATE" if lock else ""), (charity_id,))
    if c is None or c["status"] != "open":
        raise CharityError("There is no such charity.")
    return c


def give(conn: Connection, player_id, charity_id: int, amount: int, now: datetime, *, from_empire: bool = False) -> dict:
    if amount < naira(data.CHARITY_LEAST_GIFT_NAIRA):
        raise CharityError(f"A gift is at least ₦{data.CHARITY_LEAST_GIFT_NAIRA:,}.")
    period = _period(conn, now)
    with conn.transaction():
        c = _charity(conn, charity_id, lock=True)
        empire = _head_empire(conn, player_id) if from_empire else None
        if empire:
            _empire_spend(conn, empire, player_id, amount, period)
        payer = empire["account_id"] if empire else ledger.player_account_id(conn, player_id)
        try:
            ledger.transfer(conn, payer=payer, receiver=c["account_id"], amount=amount, kind="charity_gift", memo=f"A gift to {c['name']}",
                            period=period)
        except ledger.InsufficientFunds:
            raise CharityError("There is not the cash for that gift.") from None
        conn.execute("INSERT INTO charity_gifts (charity_id, from_player, from_empire, amount, period, at) VALUES (%s, %s, %s, %s, %s, %s)",
                     (charity_id, None if empire else player_id, empire["id"] if empire else None, amount, period, now))
        if empire:
            from simulation import empires
            empires._book(conn, empire["id"], period, "Charity", f"A gift to {c['name']}", amount, True, now, entered_by=player_id)
    return {"words": f"Given {_money(amount)} to {c['name']}."}


def _connected(conn: Connection, c: dict, player_id) -> bool:
    """Whether a person is connected to the charity's founder or donors: the founder, a member of the founding empire, a donor, or a
    member of a donor empire."""
    if c["founder_player"] == player_id:
        return True
    empire_ids = {g["from_empire"] for g in _rows(conn, "SELECT DISTINCT from_empire FROM charity_gifts WHERE charity_id = %s AND from_empire IS NOT NULL",
                                                   (c["id"],))}
    if c["founder_empire"]:
        empire_ids.add(c["founder_empire"])
    donors = {g["from_player"] for g in _rows(conn, "SELECT DISTINCT from_player FROM charity_gifts WHERE charity_id = %s AND from_player IS NOT NULL",
                                               (c["id"],))}
    if player_id in donors:
        return True
    if empire_ids and _one(conn, "SELECT 1 AS x FROM empire_seats WHERE empire_id = ANY(%s) AND player_id = %s", (list(empire_ids), player_id)):
        return True
    for d in donors:            # a donor's fellow members
        if _one(conn, "SELECT 1 AS x FROM empire_seats a JOIN empire_seats b ON a.empire_id = b.empire_id WHERE a.player_id = %s AND b.player_id = %s",
                (d, player_id)):
            return True
    return False


def grant(conn: Connection, player_id, charity_id: int, amount: int, words: str, now: datetime, *, to_name: str | None = None) -> dict:
    """The trustee makes a grant: to the cause (it reaches the city's households), or to a person."""
    words = " ".join((words or "").split())
    if not 5 <= len(words) <= 200:
        raise CharityError("Say what the grant is for, in 5 to 200 characters.")
    if amount < naira(data.CHARITY_LEAST_GRANT_NAIRA):
        raise CharityError(f"A grant is at least ₦{data.CHARITY_LEAST_GRANT_NAIRA:,}.")
    period = _period(conn, now)
    with conn.transaction():
        c = _charity(conn, charity_id, lock=True)
        if c["founder_empire"]:
            # An empire's charity is run by whoever is its head now; a head who has gone no longer decides.
            head = _one(conn, "SELECT head_player_id FROM empires WHERE id = %s AND status = 'active'", (c["founder_empire"],))
            if head and head["head_player_id"] != c["trustee_id"] and head["head_player_id"] is not None:
                conn.execute("UPDATE charities SET trustee_id = %s WHERE id = %s", (head["head_player_id"], c["id"]))
                c = {**c, "trustee_id": head["head_player_id"]}
        if c["trustee_id"] != player_id:
            raise CharityError("Only the charity's trustee makes its grants.")
        to = None
        if to_name:
            to = _one(conn, "SELECT id, display_name FROM players WHERE lower(display_name) = lower(%s)", (to_name.strip(),))
            if to is None:
                raise CharityError("There is no player of that name.")
            if to["id"] == player_id:
                raise CharityError("A trustee never makes a grant to themselves.")
            receiver = ledger.player_account_id(conn, to["id"])
        else:
            receiver = _one(conn, "SELECT account_id FROM households WHERE location = %s", (c["city"],))["account_id"]
        try:
            ledger.transfer(conn, payer=c["account_id"], receiver=receiver, amount=amount, kind="charity_grant",
                            memo=f"{c['name']}: {words}", period=period)
        except ledger.InsufficientFunds:
            raise CharityError("The charity has not that much to give.") from None
        connected = bool(to) and _connected(conn, c, to["id"])
        conn.execute("INSERT INTO charity_grants (charity_id, to_player, amount, words, connected, period, at) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                     (charity_id, to["id"] if to else None, amount, words, connected, period, now))
    return {"words": f"Granted {_money(amount)}" + (f" to {to['display_name']}." if to else f" to its cause in {c['city']}.")}


def at_close(conn: Connection, period: int, now: datetime) -> None:
    """At the close: the founders' reputation rises with what their charities gave to their causes this quarter; the Money Watch
    looks at charities whose grants have gone to connected people."""
    if not ready(conn):
        return
    for c in _rows(conn, "SELECT * FROM charities WHERE status = 'open' ORDER BY id"):
        to_cause = int(_one(conn, "SELECT coalesce(sum(amount), 0) AS n FROM charity_grants WHERE charity_id = %s AND period = %s AND to_player IS NULL",
                            (c["id"], period))["n"])
        if to_cause and c["founder_empire"]:
            points = min(to_cause // naira(data.CHARITY_REPUTATION_PER_NAIRA), data.CHARITY_REPUTATION_MOST)
            if points:
                standing.change(conn, c["founder_empire"], points, f"Its charity, {c['name']}, gave to its cause", period, now)
        elif to_cause and c["founder_player"]:
            points = min(to_cause // naira(data.CHARITY_PLAYER_REPUTATION_PER_NAIRA), data.CHARITY_PLAYER_REPUTATION_MOST)
            if points:
                conn.execute("UPDATE players SET reputation = least(reputation + %s, 100) WHERE id = %s", (points, c["founder_player"]))
        last = _one(conn, "SELECT coalesce(sum(amount), 0)::bigint AS total, coalesce(sum(amount) FILTER (WHERE connected), 0)::bigint AS insiders,"
                          " coalesce(sum(amount) FILTER (WHERE to_player IS NOT NULL), 0)::bigint AS people"
                          " FROM charity_grants WHERE charity_id = %s AND period > %s", (c["id"], period - 4))
        if last["insiders"] >= naira(data.CHARITY_LEAST_FOUNDING_NAIRA) and last["insiders"] * BPS > last["total"] * data.CHARITY_CONNECTED_FLAG_BPS:
            conn.execute("INSERT INTO money_watch_flags (period, account_id, reason) VALUES (%s, %s, %s)",
                         (period, c["account_id"], f"Charity {c['name']}: a large share of its grants went to people connected to it"))
        elif last["people"] >= naira(data.CHARITY_PEOPLE_FLAG_NAIRA) and last["people"] * 2 > last["total"]:
            # Most of its money going to named people, whoever they are, is worth a look too.
            conn.execute("INSERT INTO money_watch_flags (period, account_id, reason) VALUES (%s, %s, %s)",
                         (period, c["account_id"], f"Charity {c['name']}: most of its grants went to named people rather than its cause"))


def view(conn: Connection, charity_id: int, viewer=None) -> dict:
    c = _one(conn, "SELECT * FROM charities WHERE id = %s", (charity_id,))
    if c is None:
        raise CharityError("There is no such charity.")
    founder = (_one(conn, "SELECT display_name AS n FROM players WHERE id = %s", (c["founder_player"],)) if c["founder_player"] else
               _one(conn, "SELECT name AS n FROM empires WHERE id = %s", (c["founder_empire"],)))["n"]
    totals = _one(conn, """
        SELECT (SELECT coalesce(sum(amount), 0) FROM charity_gifts WHERE charity_id = %s)::bigint AS given,
               (SELECT coalesce(sum(amount), 0) FROM charity_grants WHERE charity_id = %s AND to_player IS NULL)::bigint AS to_cause,
               (SELECT coalesce(sum(amount), 0) FROM charity_grants WHERE charity_id = %s AND to_player IS NOT NULL)::bigint AS to_people""",
                  (c["id"], c["id"], c["id"]))
    out = {"id": c["id"], "name": c["name"], "cause": data.CHARITY_CAUSES[c["cause"]], "city": c["city"], "founder": founder,
           "since": clock.period_label(c["period"]), "status": c["status"], "under_a_cloud": c["exposed"],
           "given": totals["given"], "to_cause": totals["to_cause"], "to_people": totals["to_people"],
           "holds": ledger.balance(conn, c["account_id"]), "yours": viewer is not None and c["trustee_id"] == viewer}
    if out["yours"]:
        out["grants"] = _rows(conn, "SELECT g.amount, g.words, g.period, p.display_name AS to_whom FROM charity_grants g"
                                    " LEFT JOIN players p ON p.id = g.to_player WHERE g.charity_id = %s ORDER BY g.id DESC LIMIT 20", (c["id"],))
    return out


def listing(conn: Connection, viewer=None) -> list[dict]:
    return [view(conn, r["id"], viewer) for r in _rows(conn, "SELECT id FROM charities WHERE status = 'open' ORDER BY id DESC LIMIT 60")]
