"""Empires (design document, sections 6, 13 and 15).

An empire has thirteen seats: a head, and two for each of the six builds. It has its own
account in the ledger. Seats nobody holds can be filled by computer-run staff, who work at a
fixed Level 40, reliably and slowly, and are paid by the empire. Five empires run by the
computer exist from the first day, so that every player can be in one.

What is here:
  joining, leaving and founding            a player holds one seat in one empire at a time
  the chain of command                     the head sets limits, approves, pays bonuses, sacks
  trading for the empire                   Asset Managers place the empire's orders, within a limit
  tasks and handoffs                       work that needs five builds, passed from one to the next
  the shadow feature                       a member can take the empire's money, disguised in its books
  audits                                   an Accountant's audit, the staff's audit, and the paid AI audit
  secret pacts                             hidden agreements between empires, drafted by a Lawyer
  the War Room                             chat, the tracker, the decision log

Nothing here makes money: every naira is moved from one account to another through the ledger.
A thief takes from an empire and nobody else; what an audit proves is paid back to the empire.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta

from psycopg import Connection, errors
from psycopg.rows import dict_row

from simulation import bonds, careers, clock, exchange, ledger, marketview, objectives
from simulation import leagues
from simulation import world_data as data
from simulation.money import BPS, apply_bps, naira

BUILD_NAMES = {code: build["name"] for code, build in careers.BUILDS.items()}


class EmpireError(Exception):
    """A request about an empire that the rules do not allow. The words are for the player."""


def _rows(conn: Connection, sql: str, params=()) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def _one(conn: Connection, sql: str, params=()) -> dict | None:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchone()


def _log(conn: Connection, empire_id, words: str, now: datetime) -> None:
    conn.execute("INSERT INTO empire_events (empire_id, words, at) VALUES (%s, %s, %s)", (empire_id, words, now))


def _roll(conn: Connection, *parts) -> int:
    """A draw from 0 to 9,999 that nobody can know in advance: it hangs on the world's secret."""
    seed = _one(conn, "SELECT fortune_seed FROM world_state")["fortune_seed"]
    digest = hashlib.sha256(":".join([seed, *(str(p) for p in parts)]).encode()).digest()
    return int.from_bytes(digest[:8], "big") % BPS


def _open(conn: Connection, now: datetime) -> dict:
    """Refuse a change while a quarter's books are being closed; otherwise give the state of the world."""
    try:
        careers.books_open(conn, now)
    except careers.CareerError as closing:
        raise EmpireError(str(closing)) from None
    return careers.world_now(conn, now)


def _money(kobo: int) -> str:
    return objectives._money(kobo)


def _text(words: str) -> str:
    """Words a player typed, made safe to keep: one line, no control characters."""
    if not isinstance(words, str) or any(ord(ch) < 32 or ord(ch) == 127 for ch in words.replace("\n", " ").replace("\t", " ")):
        raise EmpireError("That text has characters in it that cannot be kept.")
    return " ".join(words.split())


# ---------------------------------------------------------------------------
# Setting up: the five computer-run empires
# ---------------------------------------------------------------------------

def _create(conn: Connection, name: str, kind: str, status: str, head, now: datetime, period: int | None) -> dict:
    account = ledger.create_account(conn, kind="empire", name=name)
    empire = _one(conn, "INSERT INTO empires (name, kind, status, account_id, head_player_id, founded_period, created_at)"
                        " VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING *", (name, kind, status, account, head, period, now))
    for build in data.EMPIRE_BUILDS:
        for slot in (1, 2):
            conn.execute("INSERT INTO empire_seats (empire_id, build, slot, staffed) VALUES (%s, %s, %s, %s)",
                         (empire["id"], build, slot, kind == "computer"))
    return empire


def setup(conn: Connection, now: datetime) -> None:
    """Create the five computer-run empires, once. Each has its home in one of the five cities, and
    its founding capital is put up by the households of that city out of their savings: it is
    moved, not made."""
    with conn.transaction():
        conn.execute("SELECT 1 FROM world_state FOR UPDATE")
        if _one(conn, "SELECT 1 FROM empires WHERE kind = 'computer'"):
            return
        period = _one(conn, "SELECT last_closed_period FROM world_state")["last_closed_period"]
        cities = _rows(conn, "SELECT account_id, location FROM households ORDER BY location")
        for index, name in enumerate(data.COMPUTER_EMPIRES):
            city = cities[index % len(cities)] if cities else None
            empire = _create(conn, name, "computer", "active", None, now, period)
            each = 0
            if city:
                # Never more than a hundredth of what the city's households hold.
                each = min(naira(data.COMPUTER_EMPIRE_CAPITAL_NAIRA), max(ledger.balance(conn, city["account_id"]), 0) // 100)
            if each > 0:
                ledger.transfer(conn, payer=city["account_id"], receiver=empire["account_id"], amount=each, kind="empire_capital",
                                memo=f"{name}: founding capital from the households of {city['location'].title()}",
                                reference=f"empire:{empire['id']}")
            _log(conn, empire["id"], f"{name} was founded with {_money(each)} of capital"
                                     + (f", put up by the households of {city['location'].title()}" if city else "")
                                     + ". Its seats are held by computer-run staff until players take them.", now)


# ---------------------------------------------------------------------------
# Who is who
# ---------------------------------------------------------------------------

def seat_of(conn: Connection, player_id, *, lock: bool = False) -> dict | None:
    """The seat a player holds, with its empire."""
    return _one(conn, "SELECT s.*, e.name AS empire_name, e.kind AS empire_kind, e.status AS empire_status, e.account_id,"
                      " e.head_player_id, e.expense_limit, e.trade_limit_bps, e.trust FROM empire_seats s"
                      " JOIN empires e ON e.id = s.empire_id WHERE s.player_id = %s" + (" FOR UPDATE OF s" if lock else ""), (player_id,))


def empire_of(conn: Connection, player_id) -> dict | None:
    seat = seat_of(conn, player_id)
    return _one(conn, "SELECT * FROM empires WHERE id = %s", (seat["empire_id"],)) if seat else None


def _empire(conn: Connection, empire_id, *, lock: bool = False) -> dict:
    empire = _one(conn, "SELECT * FROM empires WHERE id = %s" + (" FOR UPDATE" if lock else ""), (empire_id,))
    if empire is None:
        raise EmpireError("There is no such empire.")
    return empire


def _head(conn: Connection, player_id, *, lock: bool = True) -> dict:
    """The empire this player heads. Raises if they head none."""
    seat = seat_of(conn, player_id)
    if seat is None or seat["head_player_id"] != player_id:
        raise EmpireError("Only the head of the empire can do that.")
    return _empire(conn, seat["empire_id"], lock=lock)


def humans(conn: Connection, empire_id) -> list[dict]:
    return _rows(conn, "SELECT s.player_id, s.build, s.slot, p.display_name, p.ceo_since, c.experience, c.rank FROM empire_seats s"
                       " JOIN players p ON p.id = s.player_id LEFT JOIN careers c ON c.player_id = s.player_id AND c.build = s.build"
                       " WHERE s.empire_id = %s AND s.player_id IS NOT NULL ORDER BY s.build, s.slot", (empire_id,))


def worth(conn: Connection, empire: dict, now: datetime) -> dict:
    """What an empire owns: cash, shares and bonds at today's prices."""
    return objectives.wealth(conn, empire["account_id"], now)


def league(conn: Connection, now: datetime) -> list[dict]:
    """Every active empire, ranked by what it is worth. The table is public."""
    table = []
    for empire in _rows(conn, "SELECT * FROM empires WHERE status = 'active' AND kind <> 'pension' ORDER BY id"):
        have = worth(conn, empire, now)
        table.append({"id": empire["id"], "name": empire["name"], "kind": empire["kind"], "worth": have["total"],
                      "trust": empire["trust"], "members": len(humans(conn, empire["id"]))})
    table.sort(key=lambda e: (-e["worth"], e["id"]))
    for place, entry in enumerate(table, 1):
        entry["place"] = place
    return table


# ---------------------------------------------------------------------------
# Joining and leaving
# ---------------------------------------------------------------------------

def _take_seat(conn: Connection, empire: dict, player_id, build: str, now: datetime, period: int) -> dict:
    seat = _one(conn, "SELECT * FROM empire_seats WHERE empire_id = %s AND build = %s AND player_id IS NULL ORDER BY slot LIMIT 1 FOR UPDATE",
                (empire["id"], build))
    if seat is None:
        raise EmpireError(f"Both {BUILD_NAMES[build]} seats in {empire['name']} are held by players.")
    try:
        with conn.transaction():
            conn.execute("UPDATE empire_seats SET player_id = %s, since = %s, signing_limit = NULL WHERE id = %s", (player_id, now, seat["id"]))
            conn.execute("INSERT INTO empire_members (empire_id, player_id, build, joined_at, joined_period) VALUES (%s, %s, %s, %s, %s)",
                         (empire["id"], player_id, build, now, period))
    except errors.UniqueViolation:
        raise EmpireError("You already hold a seat in an empire. Leave it first.") from None
    name = _one(conn, "SELECT display_name FROM players WHERE id = %s", (player_id,))["display_name"]
    _log(conn, empire["id"], f"{name} took a seat as {careers._a(BUILD_NAMES[build])}.", now)
    careers._event(conn, player_id, build, "joined_empire", f"Joined {empire['name']} as {careers._a(BUILD_NAMES[build])}.", now)
    return seat


def _may_join(conn: Connection, empire: dict, player: dict, period: int) -> None:
    if player["build"] is None:
        raise EmpireError("Choose a build first: a seat in an empire is a seat for a build.")
    if seat_of(conn, player["id"]):
        raise EmpireError("You already hold a seat in an empire. Leave it first.")
    if player["reputation"] < data.JOIN_LEAST_REPUTATION:
        raise EmpireError(f"An empire will not take somebody whose reputation is below {data.JOIN_LEAST_REPUTATION}.")
    sacked = _one(conn, "SELECT max(p) AS period FROM (SELECT left_period AS p FROM empire_members WHERE empire_id = %s AND player_id = %s"
                        " AND left_reason = 'sacked' UNION ALL SELECT decided_period FROM empire_cases WHERE empire_id = %s AND player_id = %s"
                        " AND status = 'punished') x", (empire["id"], player["id"], empire["id"], player["id"]))["period"]
    if sacked is not None and period - sacked < data.SACKED_BAN_QUARTERS:
        raise EmpireError(f"{empire['name']} sacked you. It will not have you back before "
                          f"{clock.period_label(sacked + data.SACKED_BAN_QUARTERS)}.")


def apply(conn: Connection, player_id, empire_id: int, now: datetime) -> dict:
    """Ask for a seat. An empire run by the computer takes anybody it has a seat for; in an empire
    run by a player, the head decides."""
    with conn.transaction():
        state = _open(conn, now)
        player = _one(conn, "SELECT id, build, reputation, display_name FROM players WHERE id = %s FOR UPDATE", (player_id,))
        empire = _empire(conn, empire_id, lock=True)
        if empire["status"] == "closed" or empire["kind"] == "pension":
            raise EmpireError("That empire has closed.")
        _may_join(conn, empire, player, state["period"])
        if empire["head_player_id"] is None:
            if empire["status"] != "active":
                raise EmpireError("That empire is not open yet.")
            _take_seat(conn, empire, player_id, player["build"], now, state["period"])
            return {"status": "accepted", "empire": empire["name"]}
        if not _one(conn, "SELECT 1 FROM empire_seats WHERE empire_id = %s AND build = %s AND player_id IS NULL", (empire_id, player["build"])):
            raise EmpireError(f"Both {BUILD_NAMES[player['build']]} seats in {empire['name']} are held by players.")
        try:
            with conn.transaction():
                conn.execute("INSERT INTO empire_applications (empire_id, player_id, build, at) VALUES (%s, %s, %s, %s)",
                             (empire_id, player_id, player["build"], now))
        except errors.UniqueViolation:
            raise EmpireError("You already have an application waiting. Withdraw it first.") from None
        return {"status": "waiting", "empire": empire["name"]}


def withdraw_application(conn: Connection, player_id) -> None:
    conn.execute("UPDATE empire_applications SET status = 'withdrawn' WHERE player_id = %s AND status = 'waiting'", (player_id,))


def decide_application(conn: Connection, head_id, application_id: int, accept: bool, now: datetime) -> None:
    with conn.transaction():
        state = _open(conn, now)
        empire = _head(conn, head_id)
        asked = _one(conn, "SELECT * FROM empire_applications WHERE id = %s AND empire_id = %s AND status = 'waiting' FOR UPDATE",
                     (application_id, empire["id"]))
        if asked is None:
            raise EmpireError("There is no such application waiting.")
        if accept:
            player = _one(conn, "SELECT id, build, reputation FROM players WHERE id = %s FOR UPDATE", (asked["player_id"],))
            if player["build"] != asked["build"]:
                raise EmpireError("They have changed build since they applied.")
            _may_join(conn, empire, player, state["period"])
            _take_seat(conn, empire, player["id"], player["build"], now, state["period"])
        conn.execute("UPDATE empire_applications SET status = %s WHERE id = %s", ("accepted" if accept else "refused", application_id))


def _vacate(conn: Connection, seat: dict, now: datetime, period: int, reason: str) -> None:
    """Take a player out of their seat. Work of theirs for the empire that is still in hand goes back to the staff."""
    for step in _rows(conn, "SELECT s.id, s.objective_id FROM empire_task_steps s JOIN objectives o ON o.id = s.objective_id"
                            " WHERE o.player_id = %s AND o.state = 'active' AND s.status = 'current'", (seat["player_id"],)):
        objectives.withdraw(conn, seat["player_id"], step["objective_id"], now)
    conn.execute("UPDATE empire_seats SET player_id = NULL, since = NULL, signing_limit = NULL WHERE id = %s", (seat["id"],))
    conn.execute("UPDATE empire_resignations SET status = CASE WHEN %s::text IN ('left', 'released') THEN %s::text ELSE 'overtaken' END, ended_at = %s"
                 " WHERE player_id = %s AND status = 'waiting'", (reason, reason, now, seat["player_id"]))
    conn.execute("DELETE FROM empire_head_votes WHERE empire_id = %s AND (voter_id = %s OR candidate_id = %s)",
                 (seat["empire_id"], seat["player_id"], seat["player_id"]))
    conn.execute("UPDATE empire_members SET left_at = %s, left_period = %s, left_reason = %s WHERE player_id = %s AND left_at IS NULL",
                 (now, period, reason, seat["player_id"]))


def _succession(conn: Connection, empire_id, leaving_id, now: datetime) -> None:
    """The head has gone. The most experienced member with no proved theft waiting to be decided
    becomes Acting Head. If there is nobody, the staff run the empire, and every case still open
    is decided as an empire run by the computer decides it: in full."""
    accused = {r["player_id"] for r in _rows(conn, "SELECT player_id FROM empire_cases WHERE empire_id = %s AND status = 'open'", (empire_id,))}
    others = [h for h in humans(conn, empire_id) if h["player_id"] != leaving_id and h["player_id"] not in accused]
    if others:
        successor = max(others, key=lambda h: h["experience"] or 0)
        conn.execute("UPDATE empires SET head_player_id = %s WHERE id = %s", (successor["player_id"], empire_id))
        _log(conn, empire_id, f"{successor['display_name']} became Acting Head.", now)
        return
    conn.execute("UPDATE empires SET head_player_id = NULL WHERE id = %s", (empire_id,))
    _log(conn, empire_id, "The empire has no player to lead it. It is run by its staff until a player takes a seat.", now)
    empire = _empire(conn, empire_id)
    for case in _rows(conn, "SELECT * FROM empire_cases WHERE empire_id = %s AND status = 'open' ORDER BY id FOR UPDATE", (empire_id,)):
        _punish(conn, empire, case, now)


def _go(conn: Connection, seat: dict, now: datetime, period: int, reason: str = "left") -> None:
    """A member leaves: the seat is given up, it is written down, and a head is followed by a successor."""
    _vacate(conn, seat, now, period, reason)
    name = _one(conn, "SELECT display_name FROM players WHERE id = %s", (seat["player_id"],))["display_name"]
    _log(conn, seat["empire_id"], f"{name} left." if reason == "left" else f"{name} was released from their notice and left.", now)
    careers._event(conn, seat["player_id"], seat["build"], "left_empire", f"Left {seat['empire_name']}.", now)
    if seat["head_player_id"] == seat["player_id"]:
        _succession(conn, seat["empire_id"], seat["player_id"], now)


def leave(conn: Connection, player_id, now: datetime) -> None:
    """Give up a seat at once. Players do not do this directly: they hand in a resignation letter
    (see `resign`), and this is what happens when the notice has run."""
    with conn.transaction():
        state = _open(conn, now)
        seat = seat_of(conn, player_id, lock=True)
        if seat is None:
            raise EmpireError("You hold no seat in an empire.")
        conn.execute("SELECT 1 FROM empires WHERE id = %s FOR UPDATE", (seat["empire_id"],))
        if seat["head_player_id"] == player_id and seat["empire_status"] == "forming":
            raise EmpireError("Cancel the founding instead: everybody's money is then handed back.")
        _go(conn, seat, now, state["period"])


# ---------------------------------------------------------------------------
# Leaving: a resignation letter, a counter-offer, and a notice period
# ---------------------------------------------------------------------------

def _resignation(conn: Connection, player_id, *, lock: bool = True) -> dict | None:
    return _one(conn, "SELECT * FROM empire_resignations WHERE player_id = %s AND status = 'waiting'" + (" FOR UPDATE" if lock else ""),
                (player_id,))


def resign(conn: Connection, player_id, letter: str, now: datetime) -> dict:
    """Hand in a resignation letter.

    In an empire run by players the member works out a notice of fourteen real days, is paid as
    usual, and may withdraw the letter; the head is told, and may make a counter-offer or let them
    go early. In an empire run by the computer there is nobody to make an offer: the member leaves
    as the quarter ends. A partner in an empire that is still being founded leaves at once, and
    what they put in is handed back."""
    with conn.transaction():
        state = _open(conn, now)
        seat = seat_of(conn, player_id, lock=True)
        if seat is None:
            raise EmpireError("You hold no seat in an empire.")
        empire = _empire(conn, seat["empire_id"], lock=True)
        if _resignation(conn, player_id):
            raise EmpireError("You have already handed in a resignation letter.")
        letter = _text(letter or "")[:600]
        if empire["status"] == "forming":
            if empire["head_player_id"] == player_id:
                raise EmpireError("Cancel the founding instead: everybody's money is then handed back.")
            _hand_back(conn, empire, player_id, now, state["period"], "a partner left before it opened")
            _go(conn, seat, now, state["period"])
            return {"left": True, "leaves_at": None, "leaves_period": None}
        run_by_players = empire["head_player_id"] is not None
        leaves_at = now + timedelta(days=data.NOTICE_DAYS) if run_by_players else None
        leaves_period = None if run_by_players else state["period"]
        conn.execute("INSERT INTO empire_resignations (empire_id, player_id, letter, given_at, given_period, leaves_at, leaves_period)"
                     " VALUES (%s, %s, %s, %s, %s, %s, %s)", (empire["id"], player_id, letter, now, state["period"], leaves_at, leaves_period))
        name = _one(conn, "SELECT display_name FROM players WHERE id = %s", (player_id,))["display_name"]
        when = (f"on {clock.to_lagos(leaves_at):%d %B %Y}" if run_by_players else f"when {clock.period_label(state['period'])} ends")
        _log(conn, empire["id"], f"{name} handed in a resignation letter and leaves {when} unless it is withdrawn.", now)
        careers._event(conn, player_id, seat["build"], "resigned", f"Handed in a resignation letter to {empire['name']}: leaving {when}.", now)
        return {"left": False, "leaves_at": leaves_at, "leaves_period": leaves_period}


def withdraw_resignation(conn: Connection, player_id, now: datetime) -> None:
    with conn.transaction():
        _open(conn, now)
        letter = _resignation(conn, player_id)
        if letter is None:
            raise EmpireError("You have no resignation letter waiting.")
        conn.execute("UPDATE empire_resignations SET status = 'withdrawn', ended_at = %s WHERE id = %s", (now, letter["id"]))
        name = _one(conn, "SELECT display_name FROM players WHERE id = %s", (player_id,))["display_name"]
        _log(conn, letter["empire_id"], f"{name} withdrew their resignation letter.", now)


def _letter_for_head(conn: Connection, head_id, resignation_id: int) -> tuple[dict, dict]:
    empire = _head(conn, head_id)
    letter = _one(conn, "SELECT * FROM empire_resignations WHERE id = %s AND empire_id = %s AND status = 'waiting' FOR UPDATE",
                  (resignation_id, empire["id"]))
    if letter is None:
        raise EmpireError("There is no such resignation letter waiting.")
    if letter["player_id"] == head_id:
        raise EmpireError("That is your own letter.")
    return empire, letter


def counter_offer(conn: Connection, head_id, resignation_id: int, bonus: int, signing_limit_kobo: int | None, words: str, now: datetime) -> None:
    """The head answers a resignation letter with an offer to stay: a bonus, a higher signing limit,
    or both. Nothing is paid until the member accepts. A new offer replaces the last."""
    with conn.transaction():
        _open(conn, now)
        empire, letter = _letter_for_head(conn, head_id, resignation_id)
        whole = lambda v: isinstance(v, int) and not isinstance(v, bool) and v >= 0          # noqa: E731
        if not whole(bonus) or (signing_limit_kobo is not None and not whole(signing_limit_kobo)):
            raise EmpireError("An offer is a bonus, a signing limit, or both: amounts of nought or more.")
        if bonus == 0 and signing_limit_kobo is None:
            raise EmpireError("An offer needs a bonus, a higher signing limit, or both.")
        most = apply_bps(worth(conn, empire, now)["total"], data.COUNTER_OFFER_MOST_BPS)
        if bonus > most:
            raise EmpireError(f"A counter-offer's bonus may be up to {_money(most)}: {data.COUNTER_OFFER_MOST_BPS // 100}% of the empire's worth.")
        if signing_limit_kobo is not None and signing_limit_kobo > naira(10_000_000_000):
            raise EmpireError("That is not a sensible limit.")
        conn.execute("UPDATE empire_resignations SET offer_bonus = %s, offer_limit = %s, offer_words = %s, offered_at = %s WHERE id = %s",
                     (bonus, signing_limit_kobo, _text(words or "")[:400], now, letter["id"]))
        member = _one(conn, "SELECT display_name, build FROM players WHERE id = %s", (letter["player_id"],))
        _log(conn, empire["id"], f"The head made {member['display_name']} an offer to stay.", now)
        careers._event(conn, letter["player_id"], member["build"], "counter_offer",
                       f"{empire['name']} made you an offer to stay" + (f": a bonus of {_money(bonus)}" if bonus else "")
                       + (f"{' and' if bonus else ':'} a signing limit of {_money(signing_limit_kobo)} a quarter" if signing_limit_kobo is not None else "")
                       + ".", now)


def accept_offer(conn: Connection, player_id, now: datetime) -> dict:
    """The member accepts the counter-offer and stays. What was promised is paid, and set, at this
    moment: if the empire cannot pay the bonus in full, the acceptance does not go through and
    the letter stands."""
    with conn.transaction():
        state = _open(conn, now)
        seat = seat_of(conn, player_id, lock=True)
        letter = _resignation(conn, player_id)
        if seat is None or letter is None or letter["offered_at"] is None:
            raise EmpireError("There is no offer waiting for you.")
        empire = _empire(conn, seat["empire_id"], lock=True)
        if empire["head_player_id"] is None or empire["head_player_id"] == player_id:
            raise EmpireError("The head who made that offer no longer leads the empire. The offer has lapsed.")
        bonus = letter["offer_bonus"] or 0
        if bonus:
            most = bonus_limit(conn, empire, now)
            paid = _one(conn, "SELECT coalesce(sum(amount), 0)::bigint AS total FROM empire_books WHERE empire_id = %s AND period = %s"
                              " AND kind = 'bonus'", (empire["id"], state["period"]))["total"]
            if paid + bonus > most:
                raise EmpireError("The empire has reached the most it may pay in bonuses this quarter. Ask the head for a new offer, or accept next quarter.")
            try:
                ledger.transfer(conn, payer=empire["account_id"], receiver=ledger.player_account_id(conn, player_id), amount=bonus,
                                kind="empire_bonus", memo=f"{empire['name']}: bonus for staying", period=state["period"])
            except ledger.InsufficientFunds:
                raise EmpireError("The empire has not the cash to pay the bonus it offered. Your letter stands.") from None
            _book(conn, empire["id"], state["period"], "Bonuses", "Bonus to a member for staying", bonus, True, now,
                  entered_by=empire["head_player_id"], kind="bonus")
        if letter["offer_limit"] is not None:
            conn.execute("UPDATE empire_seats SET signing_limit = %s WHERE id = %s", (letter["offer_limit"], seat["id"]))
        conn.execute("UPDATE empire_resignations SET status = 'stayed', ended_at = %s WHERE id = %s", (now, letter["id"]))
        name = _one(conn, "SELECT display_name FROM players WHERE id = %s", (player_id,))["display_name"]
        _log(conn, empire["id"], f"{name} accepted the head's offer and stays.", now)
        return {"bonus": bonus, "signing_limit": letter["offer_limit"]}


def release(conn: Connection, head_id, resignation_id: int, now: datetime) -> None:
    """The head lets a member who has resigned go at once, without waiting out the notice."""
    with conn.transaction():
        state = _open(conn, now)
        _empire_, letter = _letter_for_head(conn, head_id, resignation_id)
        seat = seat_of(conn, letter["player_id"], lock=True)
        if seat is None or seat["empire_id"] != letter["empire_id"]:
            conn.execute("UPDATE empire_resignations SET status = 'overtaken', ended_at = %s WHERE id = %s", (now, letter["id"]))
            return
        _go(conn, seat, now, state["period"], "released")


def run_notices(conn: Connection, now: datetime, closed_period: int | None = None) -> int:
    """Carry out the resignation letters whose notice has run: fourteen real days in an empire run
    by players; the end of the quarter in one run by the computer. Returns how many left."""
    period = careers.world_now(conn, now)["period"]
    count = 0
    for letter in _rows(conn, "SELECT id, player_id FROM empire_resignations WHERE status = 'waiting' AND ((leaves_at IS NOT NULL AND leaves_at <= %s)"
                              " OR (leaves_period IS NOT NULL AND leaves_period <= %s)) ORDER BY id",
                        (now, closed_period if closed_period is not None else period - 1)):
        with conn.transaction():
            seat = seat_of(conn, letter["player_id"], lock=True)
            waiting = _one(conn, "SELECT * FROM empire_resignations WHERE id = %s AND status = 'waiting' FOR UPDATE", (letter["id"],))
            if waiting is None:
                continue
            if seat is None or seat["empire_id"] != waiting["empire_id"]:
                conn.execute("UPDATE empire_resignations SET status = 'overtaken', ended_at = %s WHERE id = %s", (now, waiting["id"]))
                continue
            conn.execute("SELECT 1 FROM empires WHERE id = %s FOR UPDATE", (seat["empire_id"],))
            _go(conn, seat, now, period)
            count += 1
    return count


# ---------------------------------------------------------------------------
# Electing a head. Any member who has earned the CEO rank can be voted in by the empire.
# ---------------------------------------------------------------------------

def vote_head(conn: Connection, voter_id, candidate_id, now: datetime) -> dict:
    """Vote for a member who holds the CEO rank to lead the empire. Each member has one vote and may
    change it. When more than half of the empire's players have voted for the same member, that
    member becomes head at once. Only an empire founded by players elects its head."""
    with conn.transaction():
        _open(conn, now)
        seat = seat_of(conn, voter_id, lock=True)
        if seat is None or seat["empire_status"] != "active" or seat["empire_kind"] != "player":
            raise EmpireError("Only a member of an open empire founded by players can vote for its head.")
        empire = _empire(conn, seat["empire_id"], lock=True)
        other = seat_of(conn, candidate_id)
        if other is None or other["empire_id"] != empire["id"]:
            raise EmpireError("They are not a member of your empire.")
        if not is_ceo(conn, candidate_id):
            raise EmpireError("Only a member who has earned the CEO rank can be voted in as head.")
        if empire["head_player_id"] == candidate_id:
            raise EmpireError("They lead the empire already.")
        if _one(conn, "SELECT 1 FROM empire_cases WHERE empire_id = %s AND player_id = %s AND status = 'open'", (empire["id"], candidate_id)):
            raise EmpireError("A proved theft of theirs is waiting to be decided. They cannot be voted in until it is.")
        conn.execute("INSERT INTO empire_head_votes (empire_id, voter_id, candidate_id, at) VALUES (%s, %s, %s, %s)"
                     " ON CONFLICT (empire_id, voter_id) DO UPDATE SET candidate_id = EXCLUDED.candidate_id, at = EXCLUDED.at",
                     (empire["id"], voter_id, candidate_id, now))
        members = len(humans(conn, empire["id"]))
        votes = _one(conn, "SELECT count(*) AS n FROM empire_head_votes WHERE empire_id = %s AND candidate_id = %s", (empire["id"], candidate_id))["n"]
        elected = votes * 2 > members
        if elected:
            name = _one(conn, "SELECT display_name FROM players WHERE id = %s", (candidate_id,))["display_name"]
            conn.execute("UPDATE empires SET head_player_id = %s WHERE id = %s", (candidate_id, empire["id"]))
            conn.execute("DELETE FROM empire_head_votes WHERE empire_id = %s", (empire["id"],))
            _log(conn, empire["id"], f"{name} was voted in as CEO by {votes} of the empire's {members} players.", now)
        return {"votes": votes, "members": members, "needed": members // 2 + 1, "elected": elected}


def vote_for_seat(conn: Connection, voter_id, build: str, slot: int, now: datetime) -> dict:
    """Vote for whoever holds a seat in the voter's own empire. (A member is not given their
    colleagues' identifiers, so the website names the seat.)"""
    mine = seat_of(conn, voter_id)
    held = _one(conn, "SELECT player_id FROM empire_seats WHERE empire_id = %s AND build = %s AND slot = %s",
                (mine["empire_id"], build, slot)) if mine else None
    if held is None or held["player_id"] is None:
        raise EmpireError("Nobody holds that seat in your empire.")
    return vote_head(conn, voter_id, held["player_id"], now)


# ---------------------------------------------------------------------------
# Founding an empire
# ---------------------------------------------------------------------------

def _name_ok(conn: Connection, name: str) -> str:
    name = " ".join(name.split()) if isinstance(name, str) else ""
    if not 3 <= len(name) <= 40 or not all((ch.isascii() and ch.isalnum()) or ch in " &'-." for ch in name) or not name[0].isalpha():
        raise EmpireError("An empire's name is 3 to 40 letters, numbers and spaces.")
    key = "".join(ch for ch in name.lower() if ch.isalnum())
    taken = _rows(conn, "SELECT name FROM companies UNION ALL SELECT name FROM empires")
    if any("".join(ch for ch in row["name"].lower() if ch.isalnum()) == key for row in taken) or any(
            word in key for word in ("centralbank", "federalgovernment", "treasury", "broadstreetexchange", "prizepool")):
        raise EmpireError("That name is taken, or is too close to an institution's.")
    return name


def found(conn: Connection, player_id, name: str, amount: int, from_savings: int, now: datetime) -> dict:
    """Begin founding an empire. The founder must be Level 20 or above. Their money, and their
    partners', is pooled in the empire's own account; nothing is spent until the empire opens."""
    with conn.transaction():
        state = _open(conn, now)
        player = _one(conn, "SELECT id, build, reputation, display_name FROM players WHERE id = %s FOR UPDATE", (player_id,))
        mine = careers.career(conn, player_id)
        if mine is None or mine["level"] < data.EMPIRE_FOUNDING_LEVEL:
            raise EmpireError(f"Founding an empire needs Level {data.EMPIRE_FOUNDING_LEVEL}. You are Level {mine['level'] if mine else 1}.")
        if seat_of(conn, player_id):
            raise EmpireError("Leave the empire you are in before founding your own.")
        if player["reputation"] < data.JOIN_LEAST_REPUTATION:
            raise EmpireError(f"Nobody will found an empire with somebody whose reputation is below {data.JOIN_LEAST_REPUTATION}.")
        empire = _create(conn, _name_ok(conn, name), "player", "forming", player_id, now, None)
        _take_seat(conn, empire, player_id, player["build"], now, state["period"])
        _pledge(conn, empire, player_id, amount, from_savings, now)
        _log(conn, empire["id"], f"{player['display_name']} began founding {empire['name']}.", now)
        return empire


def _pledge(conn: Connection, empire: dict, player_id, amount: int, from_savings: int, now: datetime) -> None:
    """Put money into an empire: cash of the player's own, and (while it is being founded) the one
    early withdrawal from their retirement savings, which the pension funds pay straight to the empire."""
    whole = lambda v: isinstance(v, int) and not isinstance(v, bool) and v >= 0          # noqa: E731
    if not whole(amount) or not whole(from_savings) or amount + from_savings <= 0:
        raise EmpireError("Put in an amount above nought.")
    drawn = 0
    if from_savings:
        try:
            drawn = careers.early_withdrawal(conn, player_id, from_savings, now, f"to found {empire['name']}", receiver=empire["account_id"])
        except careers.CareerError as refused:
            raise EmpireError(str(refused)) from None
    if amount:
        try:
            ledger.transfer(conn, payer=ledger.player_account_id(conn, player_id), receiver=empire["account_id"], amount=amount,
                            kind="empire_capital", memo=f"{empire['name']}: capital put in", reference=f"empire:{empire['id']}")
        except ledger.InsufficientFunds:
            raise EmpireError("You do not have that much cash.") from None
    conn.execute("INSERT INTO empire_capital (empire_id, player_id, amount, from_savings, at, period) VALUES (%s, %s, %s, %s, %s, %s)",
                 (empire["id"], player_id, amount + drawn, drawn, now, careers.world_now(conn, now)["period"]))


def put_in(conn: Connection, player_id, amount: int, from_savings: int, now: datetime) -> None:
    """A member puts money into their empire: a partner pooling money to found it, or more capital later."""
    with conn.transaction():
        _open(conn, now)
        seat = seat_of(conn, player_id, lock=True)
        if seat is None or seat["empire_kind"] != "player":
            raise EmpireError("Only a member of an empire run by players can put money into it.")
        empire = _empire(conn, seat["empire_id"], lock=True)
        if empire["status"] == "closed":
            raise EmpireError("That empire has closed.")
        if from_savings and empire["status"] != "forming":
            raise EmpireError("The early withdrawal is for founding an empire. This one is already open.")
        _pledge(conn, empire, player_id, amount, from_savings, now)
        _log(conn, empire["id"], f"{_money(amount + from_savings)} of capital was put in.", now)


def open_empire(conn: Connection, head_id, now: datetime) -> dict:
    """Open a founded empire: it needs three players and the registration fee, which is paid
    into the prize pool."""
    with conn.transaction():
        state = _open(conn, now)
        empire = _head(conn, head_id)
        if empire["status"] != "forming":
            raise EmpireError("The empire is already open.")
        if len(humans(conn, empire["id"])) < data.EMPIRE_LEAST_HUMANS:
            raise EmpireError(f"An empire needs at least {data.EMPIRE_LEAST_HUMANS} players. Invite partners first.")
        fee = naira(data.EMPIRE_REGISTRATION_NAIRA)
        if ledger.balance(conn, empire["account_id"]) < fee:
            raise EmpireError(f"The registration fee is {_money(fee)}. The partners have pooled {_money(ledger.balance(conn, empire['account_id']))}.")
        ledger.transfer(conn, payer=empire["account_id"], receiver=ledger.account_id(conn, ledger.PRIZE_POOL), amount=fee,
                        kind="empire_registration", memo=f"{empire['name']}: registration fee", reference=f"empire:{empire['id']}",
                        period=state["period"])
        conn.execute("UPDATE empires SET status = 'active', founded_period = %s WHERE id = %s", (state["period"], empire["id"]))
        division = leagues.place_new(conn, empire["id"])
        _log(conn, empire["id"], f"{empire['name']} entered the league in Division {division}.", now)
        _log(conn, empire["id"], f"{empire['name']} opened. The registration fee of {_money(fee)} was paid into the prize pool.", now)
        careers._event(conn, head_id, None, "founded_empire", f"Founded {empire['name']}.", now)
        return _empire(conn, empire["id"])


def _hand_back(conn: Connection, empire: dict, player_id, now: datetime, period: int, why: str) -> None:
    """Hand back what was pooled to found an empire that is not yet open: to one partner, or (with
    no player named) to all of them. What was drawn early from retirement savings goes back to the
    pension funds, and the withdrawal is as if never made."""
    pension_funds = ledger.account_id(conn, ledger.INVESTORS_INSTITUTIONS)
    for row in _rows(conn, "SELECT player_id, sum(amount)::bigint AS amount, sum(from_savings)::bigint AS from_savings FROM empire_capital"
                           " WHERE empire_id = %s AND (player_id = %s OR %s) GROUP BY player_id HAVING sum(amount) > 0",
                     (empire["id"], player_id, player_id is None)):
        back = ledger.pay_up_to(conn, payer=empire["account_id"], receiver=pension_funds, wanted=row["from_savings"], kind="pension_withdrawal",
                                memo=f"{empire['name']}: {why}, retirement savings handed back")
        if row["from_savings"]:
            conn.execute("UPDATE retirement_accounts SET value = value + %s, early_withdrawn_period = NULL WHERE player_id = %s",
                         (back, row["player_id"]))
        cash = ledger.pay_up_to(conn, payer=empire["account_id"], receiver=ledger.player_account_id(conn, row["player_id"]),
                                wanted=row["amount"] - row["from_savings"], kind="empire_capital",
                                memo=f"{empire['name']}: {why}, capital handed back")
        conn.execute("INSERT INTO empire_capital (empire_id, player_id, amount, from_savings, at, period) VALUES (%s, %s, %s, %s, %s, %s)",
                     (empire["id"], row["player_id"], -row["amount"], -row["from_savings"], now, period))
        assert back + cash == row["amount"] or ledger.balance(conn, empire["account_id"]) == 0


def cancel_founding(conn: Connection, head_id, now: datetime) -> None:
    """Abandon a founding: every naira put in goes back to whoever put it in. What was drawn early
    from retirement savings goes back to the pension funds, and the withdrawal is as if never made."""
    with conn.transaction():
        state = _open(conn, now)
        empire = _head(conn, head_id)
        if empire["status"] != "forming":
            raise EmpireError("An open empire cannot be cancelled.")
        _hand_back(conn, empire, None, now, state["period"], "founding cancelled")
        for seat in _rows(conn, "SELECT * FROM empire_seats WHERE empire_id = %s AND player_id IS NOT NULL", (empire["id"],)):
            _vacate(conn, seat, now, state["period"], "founding cancelled")
        conn.execute("UPDATE empires SET status = 'closed', head_player_id = NULL WHERE id = %s", (empire["id"],))
        conn.execute("UPDATE empire_applications SET status = 'refused' WHERE empire_id = %s AND status = 'waiting'", (empire["id"],))
        _log(conn, empire["id"], "The founding was cancelled and every naira handed back.", now)


# ---------------------------------------------------------------------------
# The chain of command: what the head decides
# ---------------------------------------------------------------------------

def set_limits(conn: Connection, head_id, *, expense_limit: int | None = None, trade_limit_bps: int | None = None,
               member_id=None, signing_limit: int | None = None, now: datetime | None = None) -> None:
    """The head sets what members may spend in a quarter (for everybody, or for one member), and
    how much of the empire an Asset Manager may trade in a quarter."""
    with conn.transaction():
        if now is not None:
            _open(conn, now)
        empire = _head(conn, head_id)
        if expense_limit is not None:
            if expense_limit < 0 or expense_limit > naira(10_000_000_000):
                raise EmpireError("That is not a sensible limit.")
            conn.execute("UPDATE empires SET expense_limit = %s WHERE id = %s", (expense_limit, empire["id"]))
        if trade_limit_bps is not None:
            if not 0 <= trade_limit_bps <= BPS:
                raise EmpireError("The trading limit is a share of the empire, from 0% to 100%.")
            conn.execute("UPDATE empires SET trade_limit_bps = %s WHERE id = %s", (trade_limit_bps, empire["id"]))
        if member_id is not None:
            if signing_limit is None or signing_limit < 0 or signing_limit > naira(10_000_000_000):
                raise EmpireError("That is not a sensible limit.")
            done = conn.execute("UPDATE empire_seats SET signing_limit = %s WHERE empire_id = %s AND player_id = %s",
                                (signing_limit, empire["id"], member_id)).rowcount
            if not done:
                raise EmpireError("They are not a member of your empire.")


def _staff_salary(conn: Connection, now: datetime) -> int:
    return careers.salary_per_quarter(data.STAFF_LEVEL, careers.world_now(conn, now)["wage_index_bps"])


def _pay_staff(conn: Connection, empire: dict, build: str, seats: int, salary: int, period: int, now: datetime, why: str) -> int:
    """Pay the staff of one build. It is entered in the books under that build's ordinary heading."""
    households = _one(conn, "SELECT account_id FROM households ORDER BY location LIMIT 1")
    if households is None or seats <= 0:
        return 0
    paid = ledger.pay_up_to(conn, payer=empire["account_id"], receiver=households["account_id"], wanted=seats * salary,
                            kind="empire_staff_pay", memo=f"{empire['name']}: {why}, {clock.period_label(period)}", period=period)
    if paid:
        category, description = data.DISGUISES[build]
        _book(conn, empire["id"], period, category, description, paid, True, now, kind="staff_pay")
    return paid


def staff_seat(conn: Connection, head_id, build: str, slot: int, staffed: bool, now: datetime) -> None:
    """Hire computer-run staff for an empty seat, or let them go. Staff are paid by the empire each
    quarter. Staff who are let go are paid for the quarter they were working in."""
    with conn.transaction():
        state = _open(conn, now)
        empire = _head(conn, head_id)
        if empire["status"] != "active":
            raise EmpireError("The empire is not open yet.")
        seat = _one(conn, "SELECT * FROM empire_seats WHERE empire_id = %s AND build = %s AND slot = %s FOR UPDATE", (empire["id"], build, slot))
        if seat is None:
            raise EmpireError("There is no such seat.")
        if seat["staffed"] == staffed:
            return
        if not staffed and seat["player_id"] is None:
            salary = _staff_salary(conn, now)
            if _pay_staff(conn, empire, build, 1, salary, state["period"], now, "pay of staff let go") < salary:
                raise EmpireError(f"Staff who are let go are paid for the quarter: {_money(salary)}. The empire has not the cash.")
        conn.execute("UPDATE empire_seats SET staffed = %s, staffed_in_period = CASE WHEN %s THEN %s ELSE staffed_in_period END WHERE id = %s",
                     (staffed, staffed, state["period"], seat["id"]))
        _log(conn, empire["id"], f"Computer-run staff were {'hired for' if staffed else 'let go from'} {careers._a(BUILD_NAMES.get(build, build))} seat.", now)


def _spent(conn: Connection, empire_id, player_id, period: int) -> int:
    """What a member has signed for this quarter. It is counted across every empire: moving from
    one empire to the next does not start the limit again. (A pension fund is counted on its own.)"""
    fund = _one(conn, "SELECT kind FROM empires WHERE id = %s", (empire_id,))["kind"] == "pension"
    return _one(conn, "SELECT coalesce(sum(b.amount), 0)::bigint AS total FROM empire_books b JOIN empires e ON e.id = b.empire_id"
                      " WHERE b.entered_by = %s AND b.period = %s AND b.kind = 'taken' AND (e.kind = 'pension') = %s"
                      " AND (b.empire_id = %s OR NOT %s)", (player_id, period, fund, empire_id, fund))["total"]


def is_ceo(conn: Connection, player_id) -> bool:
    """Whether a player has earned the CEO rank (Level 60, the CEO rank case, reputation of 75)."""
    row = _one(conn, "SELECT ceo_since FROM players WHERE id = %s", (player_id,)) if player_id else None
    return bool(row and row["ceo_since"])


def signing_limit(conn: Connection, seat: dict) -> int:
    """What a member may spend of the empire's money in a quarter without anybody else.

    A head: a share of the empire's cash (2% as Acting Head, 5% once CEO). Everybody else: the
    same flat figure at every level, unless the head has set one for the empire or for them."""
    if seat["head_player_id"] == seat["player_id"]:
        share = data.CEO_LIMIT_BPS if is_ceo(conn, seat["player_id"]) else data.HEAD_LIMIT_BPS
        return apply_bps(max(ledger.balance(conn, seat["account_id"]), 0), share)
    if seat["signing_limit"] is not None:
        return seat["signing_limit"]
    if seat["empire_kind"] == "computer" or seat["head_player_id"] is None:
        return naira(data.SIGNING_LIMIT_NAIRA)
    return seat["expense_limit"]


def bonus_limit(conn: Connection, empire: dict, now: datetime) -> int:
    """What a head may pay out in bonuses in a quarter: a tenth of the empire's worth as Acting Head, a quarter once CEO."""
    share = data.CEO_BONUS_BPS if is_ceo(conn, empire["head_player_id"]) else data.HEAD_BONUS_BPS
    return apply_bps(worth(conn, empire, now)["total"], share)


def _book(conn: Connection, empire_id, period: int, category: str, description: str, amount: int, genuine: bool, now: datetime,
          entered_by=None, thief_level: int | None = None, kind: str = "cost") -> int:
    return _one(conn, "INSERT INTO empire_books (empire_id, period, category, description, amount, genuine, entered_by, thief_level, at, kind)"
                      " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
                (empire_id, period, category, description, amount, genuine, entered_by, thief_level, now,
                 "taken" if not genuine else kind))["id"]


def pay_bonus(conn: Connection, head_id, member_id, amount: int, why: str, now: datetime) -> None:
    """The head pays a member a bonus out of the empire's cash. A head cannot pay one to themselves."""
    with conn.transaction():
        state = _open(conn, now)
        empire = _head(conn, head_id)
        if member_id == head_id:
            raise EmpireError("A head cannot pay themselves a bonus.")
        if empire["status"] != "active":
            raise EmpireError("The empire is not open yet. The money pooled to found it cannot be spent.")
        seat = seat_of(conn, member_id)
        if seat is None or seat["empire_id"] != empire["id"]:
            raise EmpireError("They are not a member of your empire.")
        if not isinstance(amount, int) or isinstance(amount, bool) or amount <= 0:
            raise EmpireError("A bonus is an amount above nought.")
        most = bonus_limit(conn, empire, now)
        paid = _one(conn, "SELECT coalesce(sum(amount), 0)::bigint AS total FROM empire_books WHERE empire_id = %s AND period = %s AND kind = 'bonus'",
                    (empire["id"], state["period"]))["total"]
        if paid + amount > most:
            raise EmpireError(f"A head may pay bonuses of up to {_money(most)} in a quarter (a tenth of the empire's worth; a quarter for a CEO), of which "
                              f"{_money(paid)} is paid.")
        try:
            ledger.transfer(conn, payer=empire["account_id"], receiver=ledger.player_account_id(conn, member_id), amount=amount,
                            kind="empire_bonus", memo=f"{empire['name']}: bonus", period=state["period"])
        except ledger.InsufficientFunds:
            raise EmpireError("The empire does not have that much cash.") from None
        _book(conn, empire["id"], state["period"], "Bonuses", _text(why or "Bonus to a member")[:120], amount, True, now, entered_by=head_id, kind="bonus")


def sack(conn: Connection, head_id, member_id, now: datetime) -> None:
    with conn.transaction():
        state = _open(conn, now)
        empire = _head(conn, head_id)
        seat = seat_of(conn, member_id, lock=True)
        if seat is None or seat["empire_id"] != empire["id"] or member_id == head_id:
            raise EmpireError("They are not a member you can remove.")
        _vacate(conn, seat, now, state["period"], "removed")
        name = _one(conn, "SELECT display_name FROM players WHERE id = %s", (member_id,))["display_name"]
        _log(conn, empire["id"], f"{name} was removed from the empire by its head.", now)


# ---------------------------------------------------------------------------
# Trading for the empire
# ---------------------------------------------------------------------------

def _trader(conn: Connection, player_id, now: datetime) -> tuple[dict, dict]:
    state = _open(conn, now)
    seat = seat_of(conn, player_id, lock=True)
    if seat is None or seat["empire_status"] != "active":
        raise EmpireError("You hold no seat in an open empire.")
    if seat["build"] != "asset_manager" and seat["head_player_id"] != player_id:
        raise EmpireError("Only the empire's Asset Managers, and its head, place its trades.")
    conn.execute("SELECT 1 FROM empires WHERE id = %s FOR UPDATE", (seat["empire_id"],))
    return seat, state


def trade_limit(conn: Connection, seat: dict, now: datetime) -> int:
    """What a member may trade for the empire in a quarter. In an empire the computer runs it is a
    small sum for each level the player holds; in an empire run by players the head sets it."""
    if seat["head_player_id"] is None:
        mine = careers.career(conn, seat["player_id"], seat["build"])
        return naira(data.COMPUTER_EMPIRE_TRADE_NAIRA) * (mine["level"] if mine else 1)
    return apply_bps(worth(conn, _empire(conn, seat["empire_id"]), now)["total"], seat["trade_limit_bps"])


def _task_purchase(conn: Connection, seat: dict, company_id) -> int:
    """Shares this member has still to buy to finish the empire's task: those are outside their limit."""
    step = _one(conn, "SELECT o.terms, t.* FROM empire_task_steps s JOIN empire_tasks t ON t.id = s.task_id JOIN objectives o ON o.id = s.objective_id"
                      " WHERE t.empire_id = %s AND t.status = 'open' AND s.status = 'current' AND s.template = 'em_execute' AND o.player_id = %s"
                      " AND o.state = 'active' AND t.company_id = %s", (seat["empire_id"], seat["player_id"], company_id))
    if step is None:
        return 0
    waiting = _one(conn, "SELECT coalesce(sum(remaining), 0)::bigint AS n FROM market_orders WHERE account_id = %s AND company_id = %s"
                         " AND side = 'buy' AND status = 'open'", (seat["account_id"], company_id))["n"]
    return max(step["terms"]["need"] - _bought(conn, step) - waiting, 0)


def _within_trade_limit(conn: Connection, seat: dict, state: dict, value: int, now: datetime) -> None:
    if seat["head_player_id"] == seat["player_id"]:
        return
    limit = trade_limit(conn, seat, now)
    used = _one(conn, "SELECT coalesce(sum(value), 0)::bigint AS total FROM empire_trades WHERE empire_id = %s AND player_id = %s AND period = %s",
                (seat["empire_id"], seat["player_id"], state["period"]))["total"]
    if used + value > limit:
        raise EmpireError(f"That would pass your trading limit for the quarter: {_money(limit)}, of which {_money(used)} is used.")


def fair_dealing(share: dict, side: str, kind: str, limit_price: int | None, whose: str) -> None:
    """Somebody dealing with money that is not theirs, and that no player watches over, must deal
    close to the market: within 2% of the last session's price, and never at "the best price
    available". Otherwise the money could be handed to a friend through one bad trade."""
    if kind != "limit" or limit_price is None:
        raise EmpireError(f"{whose} deals only at a price you name.")
    reference = share["reference"]
    if side == "buy" and limit_price > apply_bps(reference, BPS + data.FAIR_DEALING_BPS):
        raise EmpireError(f"{whose} may not pay more than 2% above the last session's price of {_money(reference)}.")
    if side == "sell" and limit_price < apply_bps(reference, BPS - data.FAIR_DEALING_BPS):
        raise EmpireError(f"{whose} may not sell for more than 2% below the last session's price of {_money(reference)}.")


def no_dealing_with_yourself(conn: Connection, account, company_id, side: str, insiders: list, whose: str) -> None:
    """An empire's or a fund's order must not meet an order of one of its own people in the same share."""
    if not insiders:
        return
    if _one(conn, "SELECT 1 FROM market_orders WHERE account_id = ANY(%s) AND company_id = %s AND side <> %s AND status = 'open' LIMIT 1",
            (insiders, company_id, side)):
        raise EmpireError(f"Somebody in {whose} has an order of their own waiting in this share on the other side. "
                          f"{whose[0].upper() + whose[1:]} cannot deal with its own people.")


def _insiders(conn: Connection, empire_id) -> list:
    return [r["id"] for r in _rows(conn, "SELECT a.id FROM empire_seats s JOIN ledger_accounts a ON a.player_id = s.player_id"
                                         " WHERE s.empire_id = %s", (empire_id,))]


def own_order_allowed(conn: Connection, account, company_id, side: str) -> None:
    """Before a player's own order is placed: refuse it if the empire they sit in, or the pension
    fund they manage, has an order waiting in the same share on the other side."""
    theirs = [r["account_id"] for r in _rows(
        conn, "SELECT e.account_id FROM ledger_accounts a JOIN empire_seats s ON s.player_id = a.player_id JOIN empires e ON e.id = s.empire_id"
              " WHERE a.id = %s UNION SELECT e.account_id FROM ledger_accounts a JOIN empires e ON e.head_player_id = a.player_id"
              " AND e.kind = 'pension' WHERE a.id = %s", (account, account))]
    if theirs and _one(conn, "SELECT 1 FROM market_orders WHERE account_id = ANY(%s) AND company_id = %s AND side <> %s AND status = 'open' LIMIT 1",
                       (theirs, company_id, side)):
        raise EmpireError("Your empire, or the pension fund you manage, has an order waiting in this share on the other side. "
                          "You cannot deal with it yourself.")


def trade_shares(conn: Connection, player_id, *, ticker: str, side: str, kind: str, quantity: int, limit_price: int | None,
                 now: datetime) -> dict:
    """Place an order on the exchange for the empire, with the empire's money."""
    with conn.transaction():
        seat, state = _trader(conn, player_id, now)
        share = next((s for s in marketview._shares(conn, exchange.session_of(now)[0]) if s["ticker"] == ticker), None)
        if share is None:
            raise EmpireError("There is no share with that code.")
        if not isinstance(quantity, int) or isinstance(quantity, bool) or quantity <= 0:
            raise EmpireError("The number of shares must be a whole number above zero.")
        if seat["head_player_id"] is None:
            fair_dealing(share, side, kind, limit_price, "An empire run by the computer")
        no_dealing_with_yourself(conn, seat["account_id"], share["id"], side, _insiders(conn, seat["empire_id"]), "the empire")
        value = (limit_price or share["price"]) * quantity
        for_task = _task_purchase(conn, seat, share["id"]) if side == "buy" else 0
        counted = value if quantity > for_task else 0                      # buying what the task calls for is outside the limit
        _within_trade_limit(conn, seat, state, counted, now)
        try:
            done = exchange.place_order(conn, account=seat["account_id"], ticker=ticker, side=side, kind=kind, quantity=quantity,
                                        limit_price=limit_price, now=now)
        except exchange.ExchangeError as refused:
            raise EmpireError(str(refused)) from None
        conn.execute("INSERT INTO empire_trades (empire_id, player_id, period, what, value, at) VALUES (%s, %s, %s, %s, %s, %s)",
                     (seat["empire_id"], player_id, state["period"], f"{side} {quantity:,} {ticker}", counted, now))
        return done


def cancel_order(conn: Connection, player_id, order_id: int, now: datetime) -> dict:
    with conn.transaction():
        seat, _ = _trader(conn, player_id, now)
        try:
            return exchange.cancel_order(conn, account=seat["account_id"], order_id=order_id, now=now)
        except exchange.ExchangeError as refused:
            raise EmpireError(str(refused)) from None


def trade_bonds(conn: Connection, player_id, *, code: str, side: str, units: int, now: datetime) -> dict:
    with conn.transaction():
        seat, state = _trader(conn, player_id, now)
        try:
            done = bonds.trade(conn, account=seat["account_id"], code=code, side=side, units=units, now=now)
        except bonds.BondError as refused:
            raise EmpireError(str(refused)) from None
        # The limit is checked against what the trade really came to. If it is passed, the trade is undone.
        _within_trade_limit(conn, seat, state, done["value"], now)
        conn.execute("INSERT INTO empire_trades (empire_id, player_id, period, what, value, at) VALUES (%s, %s, %s, %s, %s, %s)",
                     (seat["empire_id"], player_id, state["period"], f"{side} {units:,} of {code}", done["value"], now))
        return done


# ---------------------------------------------------------------------------
# The shadow feature: taking the empire's money
# ---------------------------------------------------------------------------

def divert(conn: Connection, player_id, amount: int, now: datetime) -> dict:
    """Take money from the empire for yourself, written into its books as an ordinary cost.

    Each build writes it its own way. The money moves through the ledger from the empire to the
    player, so it leaves a trail: an audit may find it. Nobody can take more in a quarter than
    their signing limit, or more than the empire has."""
    with conn.transaction():
        state = _open(conn, now)
        seat = seat_of(conn, player_id, lock=True)
        if seat is None or seat["empire_status"] != "active":
            raise EmpireError("You hold no seat in an open empire.")
        if not isinstance(amount, int) or amount <= 0:
            raise EmpireError("An amount above nought.")
        conn.execute("SELECT 1 FROM empires WHERE id = %s FOR UPDATE", (seat["empire_id"],))
        limit = signing_limit(conn, seat)
        used = _spent(conn, seat["empire_id"], player_id, state["period"])
        if used + amount > limit:
            raise EmpireError(f"Your signing limit for the quarter is {_money(limit)}, of which {_money(used)} is used.")
        category, description = data.DISGUISES["head" if seat["head_player_id"] == player_id else seat["build"]]
        try:
            ledger.transfer(conn, payer=seat["account_id"], receiver=ledger.player_account_id(conn, player_id), amount=amount,
                            kind="empire_expense", memo=f"{seat['empire_name']}: {category.lower()}", period=state["period"])
        except ledger.InsufficientFunds:
            raise EmpireError("The empire does not have that much cash.") from None
        mine = careers.career(conn, player_id, seat["build"])
        book = _book(conn, seat["empire_id"], state["period"], category, description, amount, False, now, entered_by=player_id,
                     thief_level=mine["level"] if mine else 1)
        return {"book_id": book, "category": category, "amount": amount, "limit": limit, "used": used + amount}


def _prove(conn: Connection, empire: dict, book: dict, audit_id: int, now: datetime, reward_to=None) -> dict:
    """An audit has proved an entry false. A case is opened; in an empire the computer runs, or
    when the thief is the head, the consequences follow at once."""
    conn.execute("UPDATE empire_books SET found = true WHERE id = %s", (book["id"],))
    case = _one(conn, "INSERT INTO empire_cases (empire_id, book_id, player_id, amount, audit_id, reward_to, at)"
                      " VALUES (%s, %s, %s, %s, %s, %s, %s) ON CONFLICT (book_id) DO NOTHING RETURNING *",
                (empire["id"], book["id"], book["entered_by"], book["amount"], audit_id, reward_to, now))
    if case is None:
        return {}
    name = _one(conn, "SELECT display_name FROM players WHERE id = %s", (book["entered_by"],))["display_name"]
    _log(conn, empire["id"], f"An audit proved that {_money(book['amount'])} entered as \"{book['category']}\" in "
                             f"{clock.period_label(book['period'])} was taken by {name}.", now)
    if empire["head_player_id"] is None or empire["head_player_id"] == book["entered_by"]:
        _punish(conn, empire, case, now)
    return case


def _punish(conn: Connection, empire: dict, case: dict, now: datetime) -> None:
    """The consequences of a proved theft: the money is paid back with a fine of the same amount
    again; what cannot be paid becomes a debt taken from future salary; the thief loses their seat
    and reputation, and it goes on their legal record."""
    thief = case["player_id"]
    period = careers.world_now(conn, now)["period"]
    fine = apply_bps(case["amount"], data.THEFT_FINE_BPS)
    owed = case["amount"] + fine
    paid = ledger.pay_up_to(conn, payer=ledger.player_account_id(conn, thief), receiver=empire["account_id"], wanted=owed,
                            kind="theft_repayment", memo=f"{empire['name']}: money taken, repaid with a fine", period=period,
                            reference=f"case:{case['id']}")
    reward = 0
    if case["reward_to"] and case["reward_to"] != thief and paid > 0:
        reward = ledger.pay_up_to(conn, payer=empire["account_id"], receiver=ledger.player_account_id(conn, case["reward_to"]),
                                  wanted=apply_bps(min(paid, case["amount"]), data.REPORT_REWARD_BPS), kind="empire_bonus",
                                  memo=f"{empire['name']}: reward for reporting a theft", period=period)
        if reward:
            _book(conn, empire["id"], period, "Bonuses", "Reward for reporting a theft that was proved", reward, True, now, kind="fee")
    conn.execute("UPDATE empire_cases SET status = 'punished', repaid = %s, fine = %s, debt_left = %s, reward_paid = %s, decided_at = %s,"
                 " decided_period = %s WHERE id = %s", (paid, fine, owed - paid, reward, now, period, case["id"]))
    conn.execute("UPDATE players SET reputation = greatest(reputation - %s, 0) WHERE id = %s", (data.THEFT_REPUTATION, thief))
    words = (f"Proved to have taken {_money(case['amount'])} from {empire['name']}. Ordered to repay it with a fine of {_money(fine)}"
             + (f"; {_money(owed - paid)} is still owed and is taken from salary." if owed > paid else "."))
    conn.execute("INSERT INTO legal_records (player_id, kind, words, at) VALUES (%s, 'theft', %s, %s)", (thief, words, now))
    if empire["kind"] == "pension":
        from simulation import pensionfunds
        fresh = _empire(conn, empire["id"])
        if fresh["head_player_id"] == thief:
            pensionfunds.strike_off(conn, fresh, now)
        name = _one(conn, "SELECT display_name, build FROM players WHERE id = %s", (thief,))
        careers._event(conn, thief, name["build"], "theft_proved", words, now)
        _log(conn, empire["id"], f"{name['display_name']} repaid {_money(paid)}"
                                 + (f", still owes {_money(owed - paid)}" if owed > paid else "") + ".", now)
        return
    seat = seat_of(conn, thief, lock=True)
    name = _one(conn, "SELECT display_name, build FROM players WHERE id = %s", (thief,))
    careers._event(conn, thief, name["build"], "theft_proved", words, now)
    if seat and seat["empire_id"] == empire["id"]:
        _vacate(conn, seat, now, period, "sacked")
        careers._event(conn, thief, seat["build"], "sacked", f"Sacked by {empire['name']}.", now)
        if _empire(conn, empire["id"])["head_player_id"] == thief:
            _succession(conn, empire["id"], thief, now)
    _log(conn, empire["id"], f"{name['display_name']} repaid {_money(paid)}"
                             + (f", still owes {_money(owed - paid)}" if owed > paid else "") + ", and was sacked.", now)


def decide_case(conn: Connection, head_id, case_id: int, punish: bool, now: datetime) -> None:
    """The head decides what follows a proved theft: the full consequences, or forgiveness.
    Nobody decides their own case: a head's own theft is punished in full."""
    with conn.transaction():
        _open(conn, now)
        empire = _head(conn, head_id)
        case = _one(conn, "SELECT * FROM empire_cases WHERE id = %s AND empire_id = %s AND status = 'open' FOR UPDATE", (case_id, empire["id"]))
        if case is None:
            raise EmpireError("There is no such case waiting for your decision.")
        if punish or case["player_id"] == head_id:
            _punish(conn, empire, case, now)
        else:
            period = careers.world_now(conn, now)["period"]
            conn.execute("UPDATE empire_cases SET status = 'forgiven', decided_at = %s, decided_period = %s WHERE id = %s", (now, period, case_id))
            _log(conn, empire["id"], f"The head forgave a proved theft of {_money(case['amount'])}.", now)


def collect_debts(conn: Connection, player_id, account, take_home_paid: int, period: int) -> None:
    """On pay day: a quarter of the take-home pay of somebody who owes an empire goes to that empire."""
    left = apply_bps(take_home_paid, data.DEBT_FROM_SALARY_BPS)
    for case in _rows(conn, "SELECT c.id, c.debt_left, e.account_id, e.name FROM empire_cases c JOIN empires e ON e.id = c.empire_id"
                            " WHERE c.player_id = %s AND c.debt_left > 0 ORDER BY c.id FOR UPDATE OF c", (player_id,)):
        if left <= 0:
            break
        paid = ledger.pay_up_to(conn, payer=account, receiver=case["account_id"], wanted=min(left, case["debt_left"]),
                                kind="theft_repayment", memo=f"{case['name']}: debt for money taken, from salary", period=period,
                                reference=f"case:{case['id']}")
        conn.execute("UPDATE empire_cases SET debt_left = debt_left - %s, repaid = repaid + %s WHERE id = %s", (paid, paid, case["id"]))
        left -= paid


# ---------------------------------------------------------------------------
# Audits
# ---------------------------------------------------------------------------

def audit_season(period: int) -> bool:
    """The AI audit can be hired in one quarter in four: the last quarter of each game year."""
    return period % data.AUDIT_SEASON_EVERY == 0


def _unfound(conn: Connection, empire_id, from_period: int, to_period: int) -> list[dict]:
    return _rows(conn, "SELECT * FROM empire_books WHERE empire_id = %s AND period BETWEEN %s AND %s AND NOT found ORDER BY id",
                 (empire_id, from_period, to_period))


def _auditor_finds_bps(auditor_level: int, thief_level: int) -> int:
    low, high = data.AUDITOR_RANGE_BPS
    return min(max(data.AUDITOR_BASE_BPS + data.AUDITOR_PER_LEVEL_BPS * (auditor_level - thief_level), low), high)


def accountant_audit(conn: Connection, player_id, now: datetime) -> dict:
    """An Accountant with a seat audits the empire's books for the last two quarters. What they find
    is shown to them alone; they then decide what goes in the report (see file_audit). How much an
    audit finds depends on the Accountant's level against the level of whoever disguised the entry.
    One audit a quarter."""
    with conn.transaction():
        state = _open(conn, now)
        seat = seat_of(conn, player_id, lock=True)
        if seat is None or seat["build"] != "accountant" or seat["empire_status"] != "active":
            raise EmpireError("Only an Accountant with a seat in the empire can audit its books.")
        level = careers.career(conn, player_id, "accountant")["level"]
        try:
            with conn.transaction():
                audit = _one(conn, "INSERT INTO empire_audits (empire_id, kind, auditor_id, period, from_period, to_period, status, at)"
                                   " VALUES (%s, 'accountant', %s, %s, %s, %s, 'open', %s) RETURNING *",
                             (seat["empire_id"], player_id, state["period"], state["period"] - 1, state["period"], now))
        except errors.UniqueViolation:
            raise EmpireError("You have already audited the books this quarter.") from None
        entries = _unfound(conn, seat["empire_id"], audit["from_period"], audit["to_period"])
        findings = [e["id"] for e in entries if not e["genuine"]
                    and _roll(conn, "audit", audit["id"], e["id"]) < _auditor_finds_bps(level, e["thief_level"] or 1)]
        conn.execute("UPDATE empire_audits SET findings = %s, examined = %s WHERE id = %s", (findings, len(entries), audit["id"]))
        return {"id": audit["id"], "examined": len(entries),
                "findings": [{"book_id": e["id"], "period": e["period"], "category": e["category"], "amount": e["amount"],
                              "yours": e["entered_by"] == player_id} for e in entries if e["id"] in findings]}


def file_audit(conn: Connection, player_id, audit_id: int, report: list[int], now: datetime) -> dict:
    """The Accountant files the audit report, naming the entries they stand behind. Anything they
    found and leave out stays hidden: an auditor can look away, and that is on them."""
    with conn.transaction():
        _open(conn, now)
        audit = _one(conn, "SELECT * FROM empire_audits WHERE id = %s AND auditor_id = %s AND status = 'open' FOR UPDATE", (audit_id, player_id))
        if audit is None:
            raise EmpireError("You have no audit waiting to be filed.")
        seat = seat_of(conn, player_id)
        if seat is None or seat["empire_id"] != audit["empire_id"] or seat["build"] != "accountant":
            # They no longer hold the seat they audited from: the audit lapses, with nothing reported.
            conn.execute("UPDATE empire_audits SET reported = '{}', status = 'filed' WHERE id = %s", (audit_id,))
            return {"examined": audit["examined"], "reported": 0}
        named = [book_id for book_id in audit["findings"] if book_id in set(report)]
        conn.execute("UPDATE empire_audits SET reported = %s, status = 'filed' WHERE id = %s", (named, audit_id))
        empire = _empire(conn, audit["empire_id"], lock=True)
        for book in _rows(conn, "SELECT * FROM empire_books WHERE id = ANY(%s) AND NOT found ORDER BY id", (named,)):
            _prove(conn, empire, book, audit_id, now)
        _log(conn, empire["id"], f"An Accountant's audit of {clock.period_label(audit['from_period'])} and "
                                 f"{clock.period_label(audit['to_period'])} was filed: {audit['examined']} entries looked at, {len(named)} called false.", now)
        return {"examined": audit["examined"], "reported": len(named)}


def _staff_audit(conn: Connection, empire: dict, period: int, now: datetime) -> int:
    """The empire's computer-run Accountant audits the quarter just closed, and reports everything it finds."""
    if not _one(conn, "SELECT 1 FROM empire_seats WHERE empire_id = %s AND build = 'accountant' AND ((player_id IS NULL AND staffed)"
                      " OR staffed_in_period >= %s)", (empire["id"], period)):
        return 0
    entries = _unfound(conn, empire["id"], period, period)
    if not any(not e["genuine"] for e in entries):
        return 0
    audit = _one(conn, "INSERT INTO empire_audits (empire_id, kind, period, from_period, to_period, examined, at)"
                       " VALUES (%s, 'staff', %s, %s, %s, %s, %s) RETURNING id", (empire["id"], period, period, period, len(entries), now))["id"]
    found = [e for e in entries if not e["genuine"]
             and _roll(conn, "staff", audit, e["id"]) < _auditor_finds_bps(data.STAFF_LEVEL, (e["thief_level"] or 1) + 30)]
    conn.execute("UPDATE empire_audits SET findings = %s, reported = %s WHERE id = %s", ([e["id"] for e in found], [e["id"] for e in found], audit))
    for entry in found:
        _prove(conn, empire, entry, audit, now)
    return len(found)


def worth_auditing(conn: Connection, empire: dict, period: int, now: datetime) -> bool:
    """Whether a computer-run head, or the regulator, would pay for the AI audit: only when the
    costs players have signed for in the quarters it looks at come to more than its fee."""
    signed = _one(conn, "SELECT coalesce(sum(amount), 0)::bigint AS total FROM empire_books WHERE empire_id = %s AND entered_by IS NOT NULL"
                        " AND kind IN ('taken', 'step', 'cost') AND NOT found AND period > %s",
                  (empire["id"], period - data.AI_AUDIT_LOOKS_BACK))["total"]
    return signed > ai_audit_fee(conn, empire, now)


def ai_audit_fee(conn: Connection, empire: dict, now: datetime) -> int:
    least = data.FUND_AI_AUDIT_LEAST_NAIRA if empire["kind"] == "pension" else data.AI_AUDIT_LEAST_NAIRA
    return max(apply_bps(worth(conn, empire, now)["total"], data.AI_AUDIT_FEE_BPS), naira(least))


def ai_audit(conn: Connection, player_id, now: datetime) -> dict:
    """Hire the AI audit: an outside firm that checks every entry in the empire's books for the last
    four quarters against every member's own statement. It is right 95 times in 100. It can be
    hired only in an audit season, once, and its fee is large. The head hires it with the empire's
    money; any other member may hire it with their own."""
    with conn.transaction():
        state = _open(conn, now)
        seat = seat_of(conn, player_id, lock=True)
        if seat is None or seat["empire_status"] != "active":
            raise EmpireError("You hold no seat in an open empire.")
        empire = _empire(conn, seat["empire_id"], lock=True)
        payer = empire["account_id"] if empire["head_player_id"] == player_id else ledger.player_account_id(conn, player_id)
        return _ai_audit(conn, empire, state["period"], now, payer=payer, hired_by=player_id)


def _ai_audit(conn: Connection, empire: dict, period: int, now: datetime, *, payer, hired_by) -> dict:
    if not audit_season(period):
        next_season = (period // data.AUDIT_SEASON_EVERY + 1) * data.AUDIT_SEASON_EVERY
        raise EmpireError(f"The AI audit can be hired only in an audit season. The next is {clock.period_label(next_season)}.")
    fee = ai_audit_fee(conn, empire, now)
    if ledger.balance(conn, payer) < fee:
        raise EmpireError(f"The AI audit costs {_money(fee)}. There is not that much cash to pay for it.")
    from_period = period - data.AI_AUDIT_LOOKS_BACK + 1
    try:
        with conn.transaction():
            audit = _one(conn, "INSERT INTO empire_audits (empire_id, kind, hired_by, period, from_period, to_period, fee, at)"
                               " VALUES (%s, 'ai', %s, %s, %s, %s, %s, %s) RETURNING id",
                         (empire["id"], hired_by, period, from_period, period, fee, now))["id"]
    except errors.UniqueViolation:
        raise EmpireError("The AI audit has already been hired this season.") from None
    ledger.transfer(conn, payer=payer, receiver=ledger.account_id(conn, ledger.PRIZE_POOL), amount=fee, kind="audit_fee",
                    memo=f"{empire['name']}: AI audit", period=period, reference=f"audit:{audit}")
    if payer == empire["account_id"]:
        _book(conn, empire["id"], period, "Audit fees", "The AI audit", fee, True, now, kind="fee")
    entries = _unfound(conn, empire["id"], from_period, period)
    found = [e for e in entries if not e["genuine"] and _roll(conn, "ai", audit, e["id"]) < data.AI_AUDIT_FINDS_BPS]
    conn.execute("UPDATE empire_audits SET findings = %s, reported = %s, examined = %s WHERE id = %s",
                 ([e["id"] for e in found], [e["id"] for e in found], len(entries), audit))
    _log(conn, empire["id"], f"The AI audit looked at {len(entries)} entries from {clock.period_label(from_period)} to "
                             f"{clock.period_label(period)} and called {len(found)} false. Its fee was {_money(fee)}.", now)
    for entry in found:
        _prove(conn, empire, entry, audit, now)
    return {"id": audit, "fee": fee, "examined": len(entries), "found": len(found)}


def report_entry(conn: Connection, player_id, book_id: int, now: datetime) -> dict:
    """A member reports an entry in the books that they believe is false. It is looked at; if it is
    proved, the reporter is rewarded with a tenth of what is recovered. A report that proves
    groundless costs the reporter a little reputation. Three reports a quarter."""
    with conn.transaction():
        state = _open(conn, now)
        seat = seat_of(conn, player_id, lock=True)
        book = _one(conn, "SELECT * FROM empire_books WHERE id = %s FOR UPDATE", (book_id,))
        if seat is None or book is None or book["empire_id"] != seat["empire_id"]:
            raise EmpireError("There is no such entry in your empire's books.")
        if book["found"]:
            raise EmpireError("That entry has already been proved false.")
        made = _one(conn, "SELECT count(*) AS n FROM empire_audits WHERE kind = 'report' AND hired_by = %s AND period = %s",
                    (player_id, state["period"]))["n"]
        if made >= data.REPORTS_A_QUARTER:
            raise EmpireError(f"A member may report {data.REPORTS_A_QUARTER} entries a quarter.")
        if _one(conn, "SELECT 1 FROM empire_audits WHERE kind = 'report' AND %s = ANY(findings || coalesce(reported, '{}'))"
                      " AND empire_id = %s", (book_id, seat["empire_id"])):
            raise EmpireError("That entry has already been looked at.")
        empire = _empire(conn, seat["empire_id"], lock=True)
        audit = _one(conn, "INSERT INTO empire_audits (empire_id, kind, hired_by, period, from_period, to_period, examined, reported, at)"
                           " VALUES (%s, 'report', %s, %s, %s, %s, 1, %s, %s) RETURNING id",
                     (empire["id"], player_id, state["period"], book["period"], book["period"], [book_id], now))["id"]
        proved = not book["genuine"] and _roll(conn, "report", audit, book_id) < data.REPORT_FINDS_BPS
        if proved:
            conn.execute("UPDATE empire_audits SET findings = %s WHERE id = %s", ([book_id], audit))
            _prove(conn, empire, book, audit, now, reward_to=player_id)
        else:
            conn.execute("UPDATE players SET reputation = greatest(reputation - 1, 0) WHERE id = %s", (player_id,))
        return {"proved": proved}


# ---------------------------------------------------------------------------
# Tasks: work that needs five builds, handed from one to the next
# ---------------------------------------------------------------------------
INVESTMENT_STEPS = (
    ("journalist", "jr_results", "Research the company: file the facts of its last results",
     "A research note on the company, to the Accountant"),
    ("accountant", "ac_ratios", "Review its accounts: the lender's four figures",
     "A review of the accounts, to the Investment Banker"),
    ("investment_banker", "ib_multiples", "Value it: what are companies like it worth?",
     "A valuation, to the Risk Manager"),
    ("risk_manager", "rm_stress", "Stress its sales: what would a bad quarter do?",
     "A risk assessment, to the Lawyer"),
    ("lawyer", "lw_control", "Check who controls it, and what a buyer would be bound by",
     "A legal opinion, to the head for approval"),
    ("head", None, "Approve the investment and its size", "An approved order, to the Asset Manager"),
    ("asset_manager", "em_execute", "Buy the shares for the empire", "The shares, in the empire's account"),
)


def _target_for(conn: Connection, empire: dict, period: int, now: datetime):
    """A company every step of the task can be done on, drawn for this empire and quarter."""
    ctx = {"conn": conn, "now": now, "period": period, "player_id": f"empire:{empire['id']}", "wage_index_bps": BPS}
    held = {row["company_id"] for row in _rows(conn, "SELECT company_id FROM share_owners WHERE account_id = %s", (empire["account_id"],))}
    fits = []
    for company in sorted(objectives._filed(conn, period - 1), key=lambda c: c["ticker"]):
        probe = {**ctx, "target": company["company_id"]}
        if company["company_id"] not in held and all(
                objectives.TEMPLATES[code].offer(probe) for _b, code, _w, _h in INVESTMENT_STEPS if code and code != "em_execute"):
            fits.append(company)
    return fits[_roll(conn, "task", empire["id"], period) % len(fits)] if fits else None


def start_task(conn: Connection, head_id, now: datetime) -> dict:
    """The head starts an investment task. The server chooses the company to be looked at."""
    with conn.transaction():
        state = _open(conn, now)
        empire = _head(conn, head_id)
        return _start_task(conn, empire, state["period"], now, started_by=head_id)


def _start_task(conn: Connection, empire: dict, period: int, now: datetime, started_by=None) -> dict:
    if empire["status"] != "active":
        raise EmpireError("The empire is not open yet.")
    if _one(conn, "SELECT 1 FROM empire_tasks WHERE empire_id = %s AND status = 'open'", (empire["id"],)):
        raise EmpireError("The empire already has a task in hand. Finish it first.")
    if _one(conn, "SELECT 1 FROM empire_tasks WHERE empire_id = %s AND period = %s", (empire["id"], period)):
        raise EmpireError("The empire has already started a task this quarter. One task a quarter.")
    target = _target_for(conn, empire, period, now)
    if target is None:
        raise EmpireError("There is no company to look at this quarter.")
    most = data.CEO_TASK_MOST_NAIRA if is_ceo(conn, empire["head_player_id"]) else data.TASK_MOST_NAIRA
    amount = min(apply_bps(ledger.balance(conn, empire["account_id"]), data.TASK_SHARE_OF_CASH_BPS), naira(most))
    if amount < naira(100_000):
        raise EmpireError("The empire has too little cash to make an investment worth the work.")
    task = _one(conn, "INSERT INTO empire_tasks (empire_id, kind, company_id, period, amount, started_by, at)"
                      " VALUES (%s, 'investment', %s, %s, %s, %s, %s) RETURNING *",
                (empire["id"], target["company_id"], period, amount, started_by, now))
    for position, (build, template, what, hands_on) in enumerate(INVESTMENT_STEPS, 1):
        conn.execute("INSERT INTO empire_task_steps (task_id, position, build, what, hands_on, template, status, ready_at)"
                     " VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                     (task["id"], position, build, what, hands_on, template, "current" if position == 1 else "waiting",
                      now if position == 1 else None))
    _log(conn, empire["id"], f"A task was started: to look at {target['name']} ({target['ticker']}) and, if it stands up, invest "
                             f"up to {_money(amount)}. It needs all six builds.", now)
    return task


def _step(conn: Connection, step_id: int, *, lock: bool = True) -> dict | None:
    return _one(conn, "SELECT s.*, t.empire_id, t.company_id, t.amount, t.status AS task_status, t.period AS task_period FROM empire_task_steps s"
                      " JOIN empire_tasks t ON t.id = s.task_id WHERE s.id = %s" + (" FOR UPDATE OF s" if lock else ""), (step_id,))


def take_step(conn: Connection, player_id, step_id: int, now: datetime) -> dict:
    """A member takes the step of a task that falls to their build. It becomes a piece of their own
    work, judged like any other, and paid for by the empire."""
    with conn.transaction():
        seat = seat_of(conn, player_id, lock=True)
        step = _step(conn, step_id)
        if seat is None or step is None or step["empire_id"] != seat["empire_id"] or step["task_status"] != "open":
            raise EmpireError("There is no such step in your empire's work.")
        if step["status"] != "current" or step["template"] is None:
            raise EmpireError("That step is not waiting to be taken.")
        if step["build"] != seat["build"]:
            raise EmpireError(f"That step falls to {careers._a(BUILD_NAMES[step['build']])}.")
        if step["objective_id"] and _one(conn, "SELECT 1 FROM objectives WHERE id = %s AND state = 'active'", (step["objective_id"],)):
            raise EmpireError("A colleague has already taken that step.")
        if _one(conn, "SELECT 1 FROM objectives WHERE terms ->> 'step_id' = %s", (str(step_id),)):
            # Whoever tried it has seen how it was marked. Nobody may now take it with that knowledge.
            raise EmpireError("That step was already tried and not passed. It now falls to the staff.")
        state = _open(conn, now)
        if _one(conn, "SELECT 1 FROM objectives WHERE player_id = %s AND template = %s AND period = %s AND terms ? 'step_id'",
                (player_id, step["template"], state["period"])):
            raise EmpireError("You have already done this kind of step for an empire this quarter. One of each kind a quarter.")
        if step["template"] == "em_execute":
            # The count of what is bought starts now, and any order the staff had waiting is withdrawn:
            # the member is paid for what they buy, not for what was already on its way.
            for order in _rows(conn, "SELECT id FROM market_orders WHERE account_id = %s AND company_id = %s AND side = 'buy' AND status = 'open'",
                               (seat["account_id"], step["company_id"])):
                try:
                    with conn.transaction():
                        exchange.cancel_order(conn, account=seat["account_id"], order_id=order["id"], now=now)
                except exchange.ExchangeError:
                    pass
            held = _one(conn, "SELECT coalesce(sum(shares), 0)::bigint AS shares FROM share_owners WHERE account_id = %s AND company_id = %s",
                        (seat["account_id"], step["company_id"]))["shares"]
            conn.execute("UPDATE empire_tasks SET shares_before = %s WHERE id = %s", (held, step["task_id"]))
        try:
            taken = objectives.accept(conn, player_id, step["template"], now,
                                      step={"step_id": step_id, "target": step["company_id"], "payer": seat["account_id"],
                                            "payer_name": seat["empire_name"], "empire_id": seat["empire_id"], "task_id": step["task_id"]})
        except objectives.ObjectiveError as refused:
            raise EmpireError(str(refused)) from None
        conn.execute("UPDATE empire_task_steps SET objective_id = %s WHERE id = %s", (taken["id"], step_id))
        return taken


def step_result(conn: Connection, step_id: int, state: str, player_id, now: datetime) -> None:
    """Called when a piece of work that was a step in a task has been judged."""
    step = _step(conn, step_id)
    if step is None or step["status"] != "current":
        return
    if state == "passed":
        # What the empire paid for the step goes in its books, under that build's ordinary heading.
        work = _one(conn, "SELECT paid, period FROM objectives WHERE player_id = %s AND terms ->> 'step_id' = %s", (player_id, str(step_id)))
        if work and work["paid"] > 0 and step["build"] in data.DISGUISES:
            category, description = data.DISGUISES[step["build"]]
            _book(conn, step["empire_id"], careers.world_now(conn, now)["period"], category, description, work["paid"], True, now,
                  entered_by=player_id, kind="step")
        _finish_step(conn, step, now, done_by=player_id)
    else:
        # Not passed: the step goes back, for a colleague or the staff to do.
        conn.execute("UPDATE empire_task_steps SET objective_id = NULL, ticks = %s WHERE id = %s", (data.STAFF_WAITS_TICKS, step_id))


def _finish_step(conn: Connection, step: dict, now: datetime, done_by=None) -> None:
    conn.execute("UPDATE empire_task_steps SET status = 'done', done_by = %s, done_by_staff = %s, done_at = %s WHERE id = %s",
                 (done_by, done_by is None, now, step["id"]))
    who = _one(conn, "SELECT display_name FROM players WHERE id = %s", (done_by,))["display_name"] if done_by else "The staff"
    _log(conn, step["empire_id"], f"{who} finished a step: {step['what'].lower()}. Handed on: {step['hands_on'].lower()}.", now)
    following = _one(conn, "SELECT * FROM empire_task_steps WHERE task_id = %s AND position = %s FOR UPDATE", (step["task_id"], step["position"] + 1))
    if following is None:
        conn.execute("UPDATE empire_tasks SET status = 'done', done_at = %s WHERE id = %s", (now, step["task_id"]))
        _log(conn, step["empire_id"], "The task is complete: all six builds each did their part.", now)
        leagues.award(conn, step["empire_id"], data.LEAGUE_POINTS["task"], "A task finished: all six builds did their part",
                      careers.world_now(conn, now)["period"], now, reference=f"task:{step['task_id']}")
        return
    conn.execute("UPDATE empire_task_steps SET status = 'current', ready_at = %s WHERE id = %s", (now, following["id"]))
    if following["template"] == "em_execute":
        # From this moment the Asset Manager's purchases are counted.
        task = _one(conn, "SELECT * FROM empire_tasks WHERE id = %s", (step["task_id"],))
        account = _one(conn, "SELECT account_id FROM empires WHERE id = %s", (task["empire_id"],))["account_id"]
        held = _one(conn, "SELECT coalesce(sum(shares), 0)::bigint AS shares FROM share_owners WHERE account_id = %s AND company_id = %s",
                    (account, task["company_id"]))["shares"]
        conn.execute("UPDATE empire_tasks SET shares_before = %s WHERE id = %s", (held, task["id"]))


def approve_step(conn: Connection, head_id, step_id: int, now: datetime) -> None:
    """The head approves the investment, after the research, the accounts and the risk have been done."""
    with conn.transaction():
        empire = _head(conn, head_id)
        _open(conn, now)
        step = _step(conn, step_id)
        if step is None or step["empire_id"] != empire["id"] or step["build"] != "head" or step["status"] != "current":
            raise EmpireError("There is nothing waiting for your approval.")
        _finish_step(conn, step, now, done_by=head_id)


def shares_needed(conn: Connection, task: dict, now: datetime) -> int:
    price = next((s["price"] for s in marketview._shares(conn, exchange.session_of(now)[0]) if s["id"] == task["company_id"]), None)
    if not price:
        raise EmpireError("That company's shares are no longer listed.")
    return max(task["amount"] * 9 // 10 // price, 1)


def _bought(conn: Connection, task: dict) -> int:
    account = _one(conn, "SELECT account_id FROM empires WHERE id = %s", (task["empire_id"],))["account_id"]
    held = _one(conn, "SELECT coalesce(sum(shares), 0)::bigint AS shares FROM share_owners WHERE account_id = %s AND company_id = %s",
                (account, task["company_id"]))["shares"]
    return held - (task["shares_before"] or 0)


def tick(conn: Connection, now: datetime) -> None:
    """The staff's working day: once at each Closing Bell and once as each quarter closes. They do
    the steps no player holds a seat for, and those players have left waiting; the computer-run
    heads give their approvals; the staff's share purchases are checked.

    In an empire with players in it the staff do one step a day: slow, and reliable. An empire with
    no players at all works through its steps without waiting for anybody."""
    for task in _rows(conn, "SELECT id, empire_id FROM empire_tasks WHERE status = 'open' ORDER BY id"):
        alone = not humans(conn, task["empire_id"])
        for _ in range(len(INVESTMENT_STEPS) if alone else 1):
            step = _one(conn, "SELECT id FROM empire_task_steps WHERE task_id = %s AND status = 'current'", (task["id"],))
            if step is None or not _work_step(conn, step["id"], now):
                break
    # A task nobody finishes is closed after two quarters, so that the empire can begin another.
    period = careers.world_now(conn, now)["period"]
    for task in _rows(conn, "SELECT id, empire_id, company_id FROM empire_tasks WHERE status = 'open' AND period < %s", (period - 2,)):
        conn.execute("UPDATE empire_tasks SET status = 'failed', done_at = %s WHERE id = %s", (now, task["id"]))
        _log(conn, task["empire_id"], "A task was left unfinished for two quarters and was closed.", now)
        empire = _empire(conn, task["empire_id"])
        if empire["head_player_id"] is None:
            # The staff's order for it is withdrawn, and the cash held for it comes back.
            for order in _rows(conn, "SELECT id FROM market_orders WHERE account_id = %s AND company_id = %s AND side = 'buy' AND status = 'open'",
                               (empire["account_id"], task["company_id"])):
                try:
                    with conn.transaction():
                        exchange.cancel_order(conn, account=empire["account_id"], order_id=order["id"], now=now)
                except exchange.ExchangeError:
                    pass


def _work_step(conn: Connection, step_id: int, now: datetime) -> bool:
    """Have the staff, or a computer-run head, do one step if it falls to them. True if it was finished."""
    with conn.transaction():
        step = _step(conn, step_id)
        if step is None or step["status"] != "current":
            return False
        empire = _empire(conn, step["empire_id"], lock=True)
        task = _one(conn, "SELECT * FROM empire_tasks WHERE id = %s", (step["task_id"],))
        if step["build"] == "head":
            if empire["head_player_id"] is None:
                _finish_step(conn, step, now)
                return True
            return False
        if step["objective_id"] and _one(conn, "SELECT 1 FROM objectives WHERE id = %s AND state = 'active'", (step["objective_id"],)):
            return False                                   # a player has it in hand
        seats = _rows(conn, "SELECT player_id, staffed FROM empire_seats WHERE empire_id = %s AND build = %s", (empire["id"], step["build"]))
        staff = any(s["player_id"] is None and s["staffed"] for s in seats)
        players = any(s["player_id"] is not None for s in seats)
        if players and step["ticks"] < data.STAFF_WAITS_TICKS:
            conn.execute("UPDATE empire_task_steps SET ticks = ticks + 1 WHERE id = %s", (step["id"],))
            return False
        if not staff:
            return False                                   # nobody to do it: the empire must recruit, or hire staff
        if step["template"] != "em_execute":
            _finish_step(conn, step, now)
            return True
        try:
            need = shares_needed(conn, task, now) - _bought(conn, task)
        except EmpireError:
            return False
        if need <= 0:
            _finish_step(conn, step, now)
            return True
        share = next((s for s in marketview._shares(conn, exchange.session_of(now)[0]) if s["id"] == task["company_id"]), None)
        waiting = _one(conn, "SELECT 1 FROM market_orders WHERE account_id = %s AND company_id = %s AND side = 'buy' AND status = 'open'",
                       (empire["account_id"], task["company_id"]))
        if share and not waiting:
            low, high = exchange.price_limits(share["reference"])
            try:
                with conn.transaction():
                    # The staff buy patiently: a quarter of what is needed at a time, a kobo above the best buyer already waiting,
                    # so that one empire's purchase does not sweep every seller out of a small company's shares.
                    bids = exchange.quote(conn, share["ticker"], now)["bids"]
                    # Never above what the company is thought to be worth (the figure on its own page).
                    thought = _one(conn, "SELECT value_per_share FROM company_valuations WHERE company_id = %s ORDER BY period DESC LIMIT 1",
                                   (task["company_id"],))
                    ceiling = min(share["price"], thought["value_per_share"] if thought else share["price"]) * 99 // 100
                    wanted = min(bids[0]["price"] + 1, ceiling) if bids else ceiling
                    exchange.place_order(conn, account=empire["account_id"], ticker=share["ticker"], side="buy", kind="limit",
                                         quantity=max(need // 4, 1), limit_price=min(max(wanted, low), high), now=now)
            except (exchange.ExchangeError, ledger.LedgerError):
                pass
    return False


# The Asset Manager's step: buy the shares, with the empire's money. Judged on what the empire holds.
def _execute_offer(ctx):
    step = ctx.get("step")
    if not step:
        return None
    conn = ctx["conn"]
    task = _one(conn, "SELECT * FROM empire_tasks WHERE id = %s", (step["task_id"],))
    company = _one(conn, "SELECT id, name, ticker FROM companies WHERE id = %s", (task["company_id"],))
    need = shares_needed(conn, task, ctx["now"])
    return {
        "client": {"ticker": company["ticker"], "name": company["name"]},
        "situation": f"The research, the accounts, the valuation, the risk and the law on {company['name']} have been done and the head has approved an "
                     f"investment of up to {_money(task['amount'])}. It falls to you to buy.",
        "task": [f"Buy at least {need:,} {company['ticker']} shares for the empire, with the empire's money, on the Empire page.",
                 "Choose your price and your moment: you are spending your colleagues' money."],
        "pass_when": f"The empire holds {need:,} more {company['ticker']} shares than it did when the approval was given, at a Closing Bell.",
        "deadline": "5 Closing Bells from now.", "given": [], "fields": [],
        "company_id": str(company["id"]), "need": need, "task_id": task["id"],
    }


def _execute_bell(ctx, objective, day):
    task = _one(ctx["conn"], "SELECT * FROM empire_tasks WHERE id = %s", (objective["terms"]["task_id"],))
    bought = _bought(ctx["conn"], task)
    progress = objective["progress"]
    progress["bells"] = progress.get("bells", 0) + 1
    progress["last"] = {"bought": bought, "need": objective["terms"]["need"]}
    done = bought >= objective["terms"]["need"]
    if not done and progress["bells"] < 5:
        return None
    return objectives._verdict(
        "passed" if done else "failed" if bought > 0 else "not_done",
        f"The empire holds {bought:,} more shares than at the approval; {objective['terms']['need']:,} were needed.",
        [objectives._milestone("Bought the shares for the empire", 100, done)],
        plain="Buying for somebody else is different from buying for yourself: the decision was made by six people, and your "
              "part is to carry it out well, at a fair price, without moving the market against the empire.",
        method="Split a large order, use a price limit, and report what was paid. An order that waits unfilled is a decision "
               "not yet carried out.",
        maths=f"{bought:,} bought against {objective['terms']['need']:,} needed.")


def _pact_offer(ctx):
    seat = seat_of(ctx["conn"], ctx["player_id"])
    if seat is None or seat["build"] != "lawyer" or seat["empire_status"] != "active":
        return None
    return {
        "situation": f"{seat['empire_name']} wants an agreement with another empire, on paper, that will hold. Drafting it is "
                     f"yours.",
        "task": ["Draft a pact on the Empire page: choose the other empire, the kind of agreement and its terms.",
                 "Have your head sign it, and the other side accept it.",
                 "Some agreements are lawful; some (fixing prices, rigging bids, dividing a market) are offences. Drafting one "
                 "of those is your choice, and your risk."],
        "pass_when": "A pact you drafted is signed by both empires before the next quarter ends.",
        "deadline": "The end of next quarter.", "given": [], "fields": [], "for_period": ctx["period"], "empire_id": seat["empire_id"],
    }


def _pact_close(ctx, objective, period):
    t = objective["terms"]
    signed = _one(ctx["conn"], "SELECT kind, legal FROM empire_pacts WHERE drafted_by = %s AND signed_period >= %s AND status IN ('signed', 'broken', 'ended')"
                               " ORDER BY id LIMIT 1", (objective["player_id"], t["for_period"]))
    if signed is None and period < t["for_period"] + 1:
        return None
    drafted = _one(ctx["conn"], "SELECT 1 FROM empire_pacts WHERE drafted_by = %s AND period >= %s", (objective["player_id"], t["for_period"]))
    if signed is None:
        return objectives._verdict("failed" if drafted else "not_done", "No pact you drafted was signed by both empires.",
                                   [objectives._milestone("Drafted a pact", 40, bool(drafted)), objectives._milestone("Signed by both empires", 60, False)],
                                   plain="A draft is not an agreement. It becomes one when both sides have signed.", method="", maths="")
    return objectives._verdict(
        "passed", f"Your pact ({data.PACT_KINDS[signed['kind']][0].split(':')[0].lower()}) was signed by both empires.",
        [objectives._milestone("Drafted a pact", 40, True), objectives._milestone("Signed by both empires", 60, True)],
        plain="A contract is a promise the other side can rely on. This one is hidden, and either side can break it: what holds "
              "it is each side's wish to be trusted next time."
              + ("" if signed["legal"] else " This pact is an offence. If it is uncovered, both empires lose trust, and the law stage will add penalties."),
        method="Say exactly what each side must do and must not do, and what follows if they do not. Check that what is agreed "
               "is lawful: an agreement to fix prices or rig bids cannot be enforced and exposes everybody who signed it.",
        maths="")


objectives.TEMPLATES.update({t.code: t for t in (
    objectives.Template("em_execute", "asset_manager", "Dealing for a client", "Buy for the empire", 1, 60_000, 100, "market",
                        "Carrying out a decision made by others, at a fair price.", "empire", _execute_offer, bell=_execute_bell, listed=False, setting="empire"),
    objectives.Template("lw_pact", "lawyer", "Contracts", "Draft a pact and have it signed", 3, 100_000, 150, "market",
                        "A contract is a promise the other side can rely on.", "empire", _pact_offer, close=_pact_close, setting="empire", base="lw_contract"),
)})


# ---------------------------------------------------------------------------
# Secret pacts
# ---------------------------------------------------------------------------

def draft_pact(conn: Connection, player_id, to_empire: int, kind: str, terms: str, now: datetime) -> dict:
    """A Lawyer with a seat drafts a pact with another empire. (Where the empire has no player as
    Lawyer but has staff in the seat, its head may have the staff draft it.)"""
    with conn.transaction():
        state = _open(conn, now)
        seat = seat_of(conn, player_id, lock=True)
        if seat is None or seat["empire_status"] != "active":
            raise EmpireError("You hold no seat in an open empire.")
        staff_lawyer = _one(conn, "SELECT 1 FROM empire_seats WHERE empire_id = %s AND build = 'lawyer' AND player_id IS NULL AND staffed",
                            (seat["empire_id"],))
        human_lawyer = _one(conn, "SELECT 1 FROM empire_seats WHERE empire_id = %s AND build = 'lawyer' AND player_id IS NOT NULL",
                            (seat["empire_id"],))
        is_head = seat["head_player_id"] == player_id
        if seat["build"] != "lawyer" and not (is_head and staff_lawyer and not human_lawyer):
            raise EmpireError("A pact is drafted by a Lawyer. Recruit one, or hire staff for the seat.")
        if kind not in data.PACT_KINDS:
            raise EmpireError("Choose one of the kinds of pact.")
        other = _empire(conn, to_empire)
        if other["id"] == seat["empire_id"] or other["status"] != "active" or other["kind"] == "pension":
            raise EmpireError("Choose another open empire.")
        terms = _text(terms or "")[:400]
        if len(terms) < 10:
            raise EmpireError("Write the terms: what each side must do.")
        if _one(conn, "SELECT 1 FROM empire_pacts WHERE kind = %s AND status IN ('drafted', 'proposed', 'signed')"
                      " AND ((from_empire = %s AND to_empire = %s) OR (from_empire = %s AND to_empire = %s))",
                (kind, seat["empire_id"], to_empire, to_empire, seat["empire_id"])):
            raise EmpireError("The two empires already have a pact of that kind, or one waiting to be signed.")
        legal = data.PACT_KINDS[kind][1]
        mine = _empire(conn, seat["empire_id"])
        if mine["head_player_id"] is None and not legal:
            raise EmpireError(f"{mine['name']} is run by the computer, and its head will not sign an unlawful pact.")
        pact = _one(conn, "INSERT INTO empire_pacts (kind, legal, from_empire, to_empire, drafted_by, terms, period, at)"
                          " VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING *",
                    (kind, legal, seat["empire_id"], to_empire, player_id if seat["build"] == "lawyer" else None, terms, state["period"], now))
        if mine["head_player_id"] is None:
            # An empire the computer runs signs its Lawyer's lawful draft at once, and sends it to the other side.
            _propose(conn, pact, mine, state["period"], now)
            pact = _one(conn, "SELECT * FROM empire_pacts WHERE id = %s", (pact["id"],))
        return pact


def _propose(conn: Connection, pact: dict, sender: dict, period: int, now: datetime) -> None:
    """A signed draft goes to the other side. An empire run by the computer answers at once: it signs
    a lawful pact with anybody it has reason to trust, and an unlawful one only now and then."""
    conn.execute("UPDATE empire_pacts SET status = 'proposed' WHERE id = %s", (pact["id"],))
    other = _empire(conn, pact["to_empire"])
    if other["head_player_id"] is None:
        agrees = sender["trust"] >= 40 if pact["legal"] else (sender["trust"] >= 50 and _roll(conn, "pact", pact["id"]) < 3300)
        _answer(conn, pact, other, agrees, period, now)


def _pact(conn: Connection, pact_id: int) -> dict:
    pact = _one(conn, "SELECT * FROM empire_pacts WHERE id = %s FOR UPDATE", (pact_id,))
    if pact is None:
        raise EmpireError("There is no such pact.")
    return pact


def sign_pact(conn: Connection, head_id, pact_id: int, now: datetime) -> dict:
    """The head signs. If it is their own empire's draft it goes to the other side; if it is the
    other side's proposal, it is now agreed. An empire run by the computer answers at once."""
    with conn.transaction():
        state = _open(conn, now)
        empire = _head(conn, head_id)
        pact = _pact(conn, pact_id)
        if pact["from_empire"] == empire["id"] and pact["status"] == "drafted":
            _propose(conn, pact, empire, state["period"], now)
        elif pact["to_empire"] == empire["id"] and pact["status"] == "proposed":
            _answer(conn, pact, empire, True, state["period"], now)
        else:
            raise EmpireError("That pact is not waiting for your signature.")
        return _one(conn, "SELECT * FROM empire_pacts WHERE id = %s", (pact_id,))


def _answer(conn: Connection, pact: dict, answering: dict, agrees: bool, period: int, now: datetime) -> None:
    conn.execute("UPDATE empire_pacts SET status = %s, signed_period = %s WHERE id = %s",
                 ("signed" if agrees else "refused", period if agrees else None, pact["id"]))
    words = f"A pact with {{other}} was {'signed' if agrees else 'refused'}: {data.PACT_KINDS[pact['kind']][0].lower()}."
    names = {e["id"]: e["name"] for e in _rows(conn, "SELECT id, name FROM empires WHERE id IN (%s, %s)", (pact["from_empire"], pact["to_empire"]))}
    _log(conn, pact["from_empire"], words.format(other=names[pact["to_empire"]]), now)
    _log(conn, pact["to_empire"], words.format(other=names[pact["from_empire"]]), now)


def refuse_pact(conn: Connection, head_id, pact_id: int, now: datetime) -> None:
    with conn.transaction():
        _open(conn, now)
        empire = _head(conn, head_id)
        pact = _pact(conn, pact_id)
        if pact["to_empire"] != empire["id"] or pact["status"] != "proposed":
            raise EmpireError("That pact is not waiting for your answer.")
        _answer(conn, pact, empire, False, 0, now)


def _trust(conn: Connection, empire_id, change: int) -> None:
    conn.execute("UPDATE empires SET trust = least(greatest(trust + %s, 0), 100) WHERE id = %s", (change, empire_id))


def break_pact(conn: Connection, head_id, pact_id: int, now: datetime) -> None:
    """Either side can break a pact at any moment. Whoever breaks it loses trust."""
    with conn.transaction():
        _open(conn, now)
        empire = _head(conn, head_id)
        pact = _pact(conn, pact_id)
        if empire["id"] not in (pact["from_empire"], pact["to_empire"]) or pact["status"] != "signed":
            raise EmpireError("You have no such pact in force.")
        conn.execute("UPDATE empire_pacts SET status = 'broken', broken_by = %s WHERE id = %s", (empire["id"], pact_id))
        _trust(conn, empire["id"], -data.PACT_BREAK_TRUST)
        other = pact["to_empire"] if pact["from_empire"] == empire["id"] else pact["from_empire"]
        _log(conn, empire["id"], "The empire broke a pact. It has lost trust.", now)
        _log(conn, other, f"{empire['name']} broke its pact with us.", now)


def report_pact(conn: Connection, head_id, pact_id: int, now: datetime) -> None:
    """A party to an unlawful pact can report it, and is treated more lightly for doing so."""
    with conn.transaction():
        _open(conn, now)
        empire = _head(conn, head_id)
        pact = _pact(conn, pact_id)
        if empire["id"] not in (pact["from_empire"], pact["to_empire"]) or pact["status"] != "signed" or pact["legal"]:
            raise EmpireError("Only an unlawful pact in force can be reported.")
        other = pact["to_empire"] if pact["from_empire"] == empire["id"] else pact["from_empire"]
        conn.execute("UPDATE empire_pacts SET status = 'ended', reported_by = %s, exposed_at = %s WHERE id = %s", (empire["id"], now, pact_id))
        _trust(conn, empire["id"], -data.PACT_EXPOSED_TRUST // 3)
        _trust(conn, other, -data.PACT_EXPOSED_TRUST - 5)
        _log(conn, empire["id"], "The empire reported an unlawful pact it was party to. It is treated more lightly for coming forward.", now)
        _log(conn, other, f"{empire['name']} reported our unlawful pact. It is now public.", now)
        leagues.award(conn, other, data.LEAGUE_POINTS["theft"], "An unlawful pact came to light", careers.world_now(conn, now)["period"],
                      now, reference=f"pact:{pact_id}")


def investigate(conn: Connection, player_id, empire_id: int, now: datetime) -> dict:
    """A Journalist looks into an empire for hidden pacts: once a quarter. The chance of finding one
    rises with level. An uncovered pact becomes public; an unlawful one costs both empires trust."""
    with conn.transaction():
        state = _open(conn, now)
        player = _one(conn, "SELECT build FROM players WHERE id = %s FOR UPDATE", (player_id,))
        if player["build"] != "journalist":
            raise EmpireError("Only a Journalist can investigate an empire.")
        target = _empire(conn, empire_id)
        if target["kind"] == "pension":
            raise EmpireError("There is no such empire.")
        mine = seat_of(conn, player_id)
        if mine and mine["empire_id"] == empire_id:
            raise EmpireError("A Journalist does not investigate the empire they sit in.")
        level = careers.career(conn, player_id, "journalist")["level"]
        try:
            with conn.transaction():
                conn.execute("INSERT INTO empire_investigations (journalist_id, period, empire_id, at) VALUES (%s, %s, %s, %s)",
                             (player_id, state["period"], empire_id, now))
        except errors.UniqueViolation:
            raise EmpireError("You have already investigated an empire this quarter.") from None
        # A pact the Journalist's own empire is party to is not theirs to "uncover".
        hidden = _rows(conn, "SELECT * FROM empire_pacts WHERE status = 'signed' AND exposed_at IS NULL AND %s IN (from_empire, to_empire)"
                             " AND NOT (%s IN (from_empire, to_empire)) ORDER BY legal, id FOR UPDATE",
                       (empire_id, mine["empire_id"] if mine else -1))
        chance = min(data.EXPOSE_BASE_BPS + data.EXPOSE_PER_LEVEL_BPS * level, 5500)
        if not hidden or _roll(conn, "expose", player_id, state["period"], empire_id) >= chance:
            return {"found": False, "words": f"You found nothing on {target['name']} this quarter."}
        pact = hidden[0]
        conn.execute("UPDATE empire_pacts SET exposed_at = %s, exposed_by = %s WHERE id = %s", (now, player_id, pact["id"]))
        conn.execute("UPDATE empire_investigations SET found_pact = %s WHERE journalist_id = %s AND period = %s", (pact["id"], player_id, state["period"]))
        if not pact["legal"]:
            _trust(conn, pact["from_empire"], -data.PACT_EXPOSED_TRUST)
            _trust(conn, pact["to_empire"], -data.PACT_EXPOSED_TRUST)
            for side in (pact["from_empire"], pact["to_empire"]):
                leagues.award(conn, side, data.LEAGUE_POINTS["theft"], "An unlawful pact came to light", state["period"], now,
                              reference=f"pact:{pact['id']}")
        if not pact["legal"]:
            # Uncovering an offence is a story. A lawful agreement coming to light is only news.
            careers.add_experience(conn, player_id, "journalist", 100, now)
            conn.execute("UPDATE players SET reputation = least(reputation + 2, 100) WHERE id = %s", (player_id,))
        for side in (pact["from_empire"], pact["to_empire"]):
            _log(conn, side, "A journalist uncovered one of the empire's pacts. It is now public.", now)
        return {"found": True, "words": f"You uncovered a hidden pact: {data.PACT_KINDS[pact['kind']][0].lower()}."}


# ---------------------------------------------------------------------------
# The War Room
# ---------------------------------------------------------------------------

def say(conn: Connection, player_id, body: str, now: datetime) -> None:
    seat = seat_of(conn, player_id)
    if seat is None:
        raise EmpireError("You hold no seat in an empire.")
    body = _text(body or "")
    if not 1 <= len(body) <= 500:
        raise EmpireError("A message is 1 to 500 characters.")
    conn.execute("INSERT INTO empire_messages (empire_id, player_id, body, at) VALUES (%s, %s, %s, %s)", (seat["empire_id"], player_id, body, now))


# ---------------------------------------------------------------------------
# The quarter's end, and the Closing Bell
# ---------------------------------------------------------------------------

def at_bell(conn: Connection, now: datetime) -> None:
    run_notices(conn, now)
    tick(conn, now)
    from simulation import pensionfunds
    pensionfunds.at_bell(conn, now)


def after_close(conn: Connection, period: int, now: datetime) -> None:
    """After a quarter has closed: empires pay their staff; the empires the computer runs audit
    their books, put idle cash to work and begin a new task; then the staff do their work."""
    households = _one(conn, "SELECT account_id FROM households ORDER BY location LIMIT 1")
    wage = _one(conn, "SELECT wage_index_bps FROM economy_results WHERE period = %s", (period,))
    salary = careers.salary_per_quarter(data.STAFF_LEVEL, wage["wage_index_bps"] if wage else BPS)
    for empire in _rows(conn, "SELECT * FROM empires WHERE status = 'active' AND kind <> 'pension' ORDER BY id"):
        with conn.transaction():
            empire = _empire(conn, empire["id"], lock=True)
            staffed = _rows(conn, "SELECT build, count(*) AS n FROM empire_seats WHERE empire_id = %s AND player_id IS NULL AND staffed"
                                  " GROUP BY build ORDER BY build", (empire["id"],))
            short = False
            for group in staffed if households else []:
                short = _pay_staff(conn, empire, group["build"], group["n"], salary, period, now, "pay of computer-run staff") < group["n"] * salary or short
            if short:
                conn.execute("UPDATE empire_seats SET staffed = false WHERE empire_id = %s AND player_id IS NULL", (empire["id"],))
                _log(conn, empire["id"], "The empire could not pay its staff in full. They have left.", now)
            conn.execute("UPDATE empire_seats SET staffed_in_period = %s WHERE empire_id = %s AND player_id IS NULL AND staffed",
                         (period + 1, empire["id"]))
            _staff_audit(conn, empire, period, now)
            if empire["head_player_id"] is None:
                _computer_head(conn, empire, period, now)
    tick(conn, now)
    # What each empire is worth as the quarter closes, written down for good: the line on the head's screen.
    for empire in _rows(conn, "SELECT * FROM empires WHERE status = 'active' AND kind <> 'pension' ORDER BY id"):
        have = worth(conn, empire, now)
        conn.execute("INSERT INTO empire_worth (empire_id, period, worth, cash) VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING",
                     (empire["id"], period, have["total"], have["cash"]))
    run_notices(conn, now, closed_period=period)
    leagues.after_close(conn, period, now)
    from simulation import pensionfunds
    pensionfunds.after_close(conn, period, now)


def _computer_head(conn: Connection, empire: dict, period: int, now: datetime) -> None:
    """What an empire run by the computer does as a quarter closes."""
    # In an audit season it hires the AI audit about one year in two, if anything was spent by a player.
    if audit_season(period) and _roll(conn, "season", empire["id"], period) < 5000 and worth_auditing(conn, empire, period, now):
        try:
            with conn.transaction():
                _ai_audit(conn, empire, period, now, payer=empire["account_id"], hired_by=None)
        except EmpireError:
            pass
    # Idle cash above a fifth of what it is worth is lent to the Government for three months.
    have = worth(conn, empire, now)
    spare = have["cash"] - apply_bps(have["total"], data.COMPUTER_EMPIRE_CASH_KEPT_BPS)
    bill = next((b for b in bonds.listing(conn, now) if b["kind"] == "bill"), None)
    if bill and spare > bill["ask"]:
        try:
            with conn.transaction():
                bonds.trade(conn, account=empire["account_id"], code=bill["code"], side="buy", units=spare // bill["ask"], now=now)
        except (bonds.BondError, ledger.LedgerError):
            pass
    if not _one(conn, "SELECT 1 FROM empire_tasks WHERE empire_id = %s AND status = 'open'", (empire["id"],)):
        try:
            with conn.transaction():
                _start_task(conn, empire, period + 1, now)
        except EmpireError:
            pass


# ---------------------------------------------------------------------------
# What players see
# ---------------------------------------------------------------------------

def badge(conn: Connection, player_id, now: datetime) -> dict | None:
    """The line about a player's empire in the sections menu: its name, its place in the league,
    and how many things are waiting for this player in the War Room."""
    seat = seat_of(conn, player_id)
    if seat is None:
        return None
    is_head = seat["head_player_id"] == player_id
    waiting = _one(conn, "SELECT count(*) AS n FROM empire_task_steps s JOIN empire_tasks t ON t.id = s.task_id"
                         " WHERE t.empire_id = %s AND t.status = 'open' AND s.status = 'current' AND ((s.template IS NOT NULL AND s.build = %s"
                         " AND NOT EXISTS (SELECT 1 FROM objectives o WHERE o.id = s.objective_id AND o.state = 'active')"
                         " AND NOT EXISTS (SELECT 1 FROM objectives o WHERE o.player_id = %s AND o.terms ->> 'step_id' = s.id::text))"
                         " OR (s.build = 'head' AND %s))", (seat["empire_id"], seat["build"], player_id, is_head))["n"]
    waiting += _one(conn, "SELECT count(*) AS n FROM empire_audits WHERE empire_id = %s AND auditor_id = %s AND status = 'open'",
                    (seat["empire_id"], player_id))["n"]
    if is_head:
        waiting += _one(conn, "SELECT (SELECT count(*) FROM empire_applications WHERE empire_id = %s AND status = 'waiting')"
                              " + (SELECT count(*) FROM empire_cases WHERE empire_id = %s AND status = 'open')"
                              " + (SELECT count(*) FROM empire_pacts WHERE (to_empire = %s AND status = 'proposed')"
                              "    OR (from_empire = %s AND status = 'drafted')) AS n", (seat["empire_id"],) * 4)["n"]
        waiting += _one(conn, "SELECT count(*) AS n FROM empire_resignations WHERE empire_id = %s AND status = 'waiting' AND player_id <> %s"
                              " AND offered_at IS NULL", (seat["empire_id"], player_id))["n"]
    waiting += _one(conn, "SELECT count(*) AS n FROM empire_resignations WHERE player_id = %s AND status = 'waiting' AND offered_at IS NOT NULL",
                    (player_id,))["n"]
    place = next((e["place"] for e in league(conn, now) if e["id"] == seat["empire_id"]), None)
    return {"name": seat["empire_name"], "place": place, "is_head": is_head, "waiting": waiting, "forming": seat["empire_status"] == "forming"}


def directory(conn: Connection, player_id, now: datetime) -> dict:
    """Every empire, the league table, and where this player could sit."""
    player = _one(conn, "SELECT build FROM players WHERE id = %s", (player_id,))
    mine = seat_of(conn, player_id)
    table = league(conn, now)
    waiting = _one(conn, "SELECT empire_id FROM empire_applications WHERE player_id = %s AND status = 'waiting'", (player_id,))
    for entry in table:
        seats = _rows(conn, "SELECT build, player_id FROM empire_seats WHERE empire_id = %s", (entry["id"],))
        entry["seats_open"] = sum(1 for s in seats if s["build"] == player["build"] and s["player_id"] is None) if player["build"] else 0
        entry["run_by"] = "the computer" if entry["kind"] == "computer" and not _one(
            conn, "SELECT head_player_id FROM empires WHERE id = %s", (entry["id"],))["head_player_id"] else "players"
        entry["yours"] = bool(mine and mine["empire_id"] == entry["id"])
        entry["applied"] = bool(waiting and waiting["empire_id"] == entry["id"])
    forming = _rows(conn, "SELECT e.id, e.name, p.display_name AS founder FROM empires e JOIN players p ON p.id = e.head_player_id"
                          " WHERE e.status = 'forming' ORDER BY e.id")
    exposed = _rows(conn, "SELECT p.kind, p.legal, p.exposed_at, a.name AS one, b.name AS other FROM empire_pacts p"
                          " JOIN empires a ON a.id = p.from_empire JOIN empires b ON b.id = p.to_empire WHERE p.exposed_at IS NOT NULL"
                          " ORDER BY p.exposed_at DESC LIMIT 20")
    career = careers.career(conn, player_id)
    divisions = leagues.table(conn, now)
    mine_id = mine["empire_id"] if mine else None
    for division in divisions:
        for row in division["empires"]:
            row["yours"] = row["id"] == mine_id
    return {"league": table, "forming": forming, "in_empire": mine is not None, "divisions": divisions,
            "seasons": leagues.past_seasons(conn), "season": leagues.season_of(careers.world_now(conn, now)["period"]),
            "division_size": data.DIVISION_SIZE, "league_points": data.LEAGUE_POINTS,
            "build_table": leagues.build_table(conn, player["build"], player_id) if player["build"] else None,
            "exposed_pacts": [{**e, "kind": data.PACT_KINDS[e["kind"]][0]} for e in exposed],
            "can_found": bool(career and career["level"] >= data.EMPIRE_FOUNDING_LEVEL and mine is None),
            "founding_level": data.EMPIRE_FOUNDING_LEVEL, "registration_fee": naira(data.EMPIRE_REGISTRATION_NAIRA)}


def _legal(conn: Connection, player_id) -> list[dict]:
    """A player's legal record: thefts proved against them, wherever they happened."""
    return _rows(conn, "SELECT words, at FROM legal_records WHERE player_id = %s ORDER BY id DESC LIMIT 5", (player_id,))


def _letter_public(letter: dict, period: int) -> dict:
    return {"letter": letter["letter"], "given_at": letter["given_at"], "leaves_at": letter["leaves_at"],
            "leaves_when_quarter_ends": letter["leaves_period"] is not None,
            "leaves_label": clock.period_label(letter["leaves_period"]) if letter["leaves_period"] is not None else None,
            "offer": None if letter["offered_at"] is None else {
                "bonus": letter["offer_bonus"] or 0, "signing_limit": letter["offer_limit"], "words": letter["offer_words"],
                "at": letter["offered_at"]}}


def war_room(conn: Connection, player_id, now: datetime) -> dict | None:
    """Everything a member sees of their own empire. Who entered an entry in the books, and whether
    it is what it says, is not here: that is for an audit to find."""
    seat = seat_of(conn, player_id)
    if seat is None:
        return None
    state = careers.world_now(conn, now)
    empire = _empire(conn, seat["empire_id"])
    is_head = empire["head_player_id"] == player_id
    have = worth(conn, empire, now)
    table = league(conn, now)
    place = next((e["place"] for e in table if e["id"] == empire["id"]), None)
    letters = _rows(conn, "SELECT r.*, p.display_name FROM empire_resignations r JOIN players p ON p.id = r.player_id"
                          " WHERE r.empire_id = %s AND r.status = 'waiting' ORDER BY r.id", (empire["id"],))
    leaving = {r["player_id"] for r in letters}
    own_letter = next((r for r in letters if r["player_id"] == player_id), None)
    votes = _rows(conn, "SELECT v.candidate_id, v.voter_id, p.display_name FROM empire_head_votes v JOIN players p ON p.id = v.candidate_id"
                        " WHERE v.empire_id = %s", (empire["id"],))
    seats = []
    for s in _rows(conn, "SELECT s.*, p.display_name, p.ceo_since, c.experience, c.rank FROM empire_seats s LEFT JOIN players p ON p.id = s.player_id"
                         " LEFT JOIN careers c ON c.player_id = s.player_id AND c.build = s.build WHERE s.empire_id = %s ORDER BY s.build, s.slot",
                   (empire["id"],)):
        level = careers.level_for(s["experience"] or 0, s["rank"] or 0) if s["player_id"] else (data.STAFF_LEVEL if s["staffed"] else None)
        seats.append({"build": s["build"], "build_name": BUILD_NAMES[s["build"]], "slot": s["slot"], "held": s["player_id"] is not None,
                      "player_id": str(s["player_id"]) if s["player_id"] and (is_head or s["player_id"] == player_id) else None,
                      "name": s["display_name"] if s["player_id"] else ("Computer-run staff" if s["staffed"] else "Empty"),
                      "level": level, "staffed": s["staffed"] and s["player_id"] is None, "you": s["player_id"] == player_id,
                      "head": s["player_id"] is not None and s["player_id"] == empire["head_player_id"],
                      "signing_limit": s["signing_limit"] if is_head else None,
                      "ceo": bool(s["player_id"] and s["ceo_since"]),
                      "resigning": bool(s["player_id"] and (is_head or s["player_id"] == player_id) and s["player_id"] in leaving),
                      # What the head sees before deciding whether to keep somebody: their legal record.
                      "legal": _legal(conn, s["player_id"]) if is_head and s["player_id"] and s["player_id"] != player_id else []})
    # The senior player in each build is its lead: the executive team.
    for build in data.EMPIRE_BUILDS:
        held = [s for s in seats if s["build"] == build and s["held"]]
        if held:
            max(held, key=lambda s: s["level"] or 0)["lead"] = True
    task = _one(conn, "SELECT t.*, c.name, c.ticker FROM empire_tasks t JOIN companies c ON c.id = t.company_id"
                      " WHERE t.empire_id = %s ORDER BY (t.status = 'open') DESC, t.id DESC LIMIT 1", (empire["id"],))
    steps = []
    if task:
        for step in _rows(conn, "SELECT s.*, p.display_name FROM empire_task_steps s LEFT JOIN players p ON p.id = s.done_by"
                                " WHERE s.task_id = %s ORDER BY s.position", (task["id"],)):
            taken_by = _one(conn, "SELECT p.display_name, o.player_id FROM objectives o JOIN players p ON p.id = o.player_id"
                                  " WHERE o.id = %s AND o.state = 'active'", (step["objective_id"],)) if step["objective_id"] else None
            steps.append({
                "id": step["id"], "position": step["position"], "build": step["build"],
                "build_name": "Head of the empire" if step["build"] == "head" else BUILD_NAMES[step["build"]],
                "what": step["what"], "hands_on": step["hands_on"], "status": step["status"],
                "done_by": step["display_name"] or ("The staff" if step["done_by_staff"] else None),
                "taken_by": taken_by and taken_by["display_name"],
                "yours_to_take": step["status"] == "current" and step["template"] is not None and step["build"] == seat["build"] and taken_by is None,
                "yours_to_approve": step["status"] == "current" and step["build"] == "head" and is_head,
            })
    books = _rows(conn, "SELECT b.id, b.period, b.category, b.description, b.amount, b.found FROM empire_books b WHERE b.empire_id = %s"
                        " AND b.period >= %s ORDER BY b.id DESC LIMIT 60", (empire["id"], state["period"] - data.AI_AUDIT_LOOKS_BACK))
    mine = _rows(conn, "SELECT id, period, category, amount, found FROM empire_books WHERE empire_id = %s AND entered_by = %s AND NOT genuine"
                       " ORDER BY id DESC LIMIT 20", (empire["id"], player_id))
    cases = _rows(conn, "SELECT c.id, c.amount, c.status, c.repaid, c.fine, c.debt_left, c.at, p.display_name AS who, b.category, b.period"
                        " FROM empire_cases c JOIN players p ON p.id = c.player_id JOIN empire_books b ON b.id = c.book_id"
                        " WHERE c.empire_id = %s ORDER BY c.id DESC LIMIT 20", (empire["id"],))
    audits = _rows(conn, "SELECT a.id, a.kind, a.period, a.from_period, a.to_period, a.fee, a.examined, a.status,"
                         " coalesce(cardinality(a.reported), 0) AS reported, a.auditor_id FROM empire_audits a WHERE a.empire_id = %s"
                         " AND a.kind <> 'report' ORDER BY a.id DESC LIMIT 10", (empire["id"],))
    open_audit = _one(conn, "SELECT id, findings FROM empire_audits WHERE empire_id = %s AND auditor_id = %s AND status = 'open'",
                      (empire["id"], player_id))
    findings = _rows(conn, "SELECT id AS book_id, period, category, amount, entered_by = %s AS yours FROM empire_books WHERE id = ANY(%s) ORDER BY id",
                     (player_id, open_audit["findings"])) if open_audit else []
    pacts = _rows(conn, "SELECT p.*, a.name AS from_name, b.name AS to_name FROM empire_pacts p JOIN empires a ON a.id = p.from_empire"
                        " JOIN empires b ON b.id = p.to_empire WHERE %s IN (p.from_empire, p.to_empire) AND (p.status <> 'drafted' OR p.from_empire = %s)"
                        " ORDER BY p.id DESC LIMIT 20", (empire["id"], empire["id"]))
    shared = []
    for pact in pacts:
        if pact["kind"] == "share_information" and pact["status"] == "signed":
            other = _empire(conn, pact["to_empire"] if pact["from_empire"] == empire["id"] else pact["from_empire"])
            theirs = worth(conn, other, now)
            shared.append({"name": other["name"], "cash": theirs["cash"], "shares_value": theirs["shares"], "bonds_value": theirs["bonds"],
                           "lines": [{"ticker": line["ticker"], "value": line["value"]} for line in theirs["lines"]]})
    limit = signing_limit(conn, seat)
    may_trade = trade_limit(conn, seat, now)
    return {
        "id": empire["id"], "name": empire["name"], "kind": empire["kind"], "status": empire["status"], "trust": empire["trust"],
        "run_by_computer": empire["head_player_id"] is None, "is_head": is_head, "your_build": seat["build"], "place": place,
        "empires": len(table), "worth": have["total"], "cash": have["cash"], "shares_value": have["shares"], "bonds_value": have["bonds"],
        "holdings": [{"ticker": line["ticker"], "shares": line["shares"], "value": line["value"]} for line in have["lines"]],
        "bond_holdings": [{"code": b["code"], "name": b["name"], "units": b["units"], "value": b["value"]} for b in have["bond_lines"]],
        "orders": exchange.orders_of(conn, empire["account_id"], limit=10),
        "seats": seats, "humans": sum(1 for s in seats if s["held"]),
        "can_trade": seat["build"] == "asset_manager" or is_head, "trade_limit": may_trade, "fair_dealing": empire["head_player_id"] is None,
        "bonus_limit": bonus_limit(conn, empire, now),
        "trade_used": _one(conn, "SELECT coalesce(sum(value), 0)::bigint AS total FROM empire_trades WHERE empire_id = %s AND player_id = %s"
                                 " AND period = %s", (empire["id"], player_id, state["period"]))["total"],
        "signing_limit": limit, "signing_used": _spent(conn, empire["id"], player_id, state["period"]),
        "disguise": data.DISGUISES["head" if is_head else seat["build"]][0],
        "task": task and {"id": task["id"], "company": task["name"], "ticker": task["ticker"], "amount": task["amount"],
                          "status": task["status"], "steps": steps},
        "books": books, "your_entries": mine, "cases": cases,
        "audits": [{**a, "yours": a["auditor_id"] == player_id, "auditor_id": None} for a in audits],
        "open_audit": open_audit and {"id": open_audit["id"], "findings": findings},
        "can_audit": seat["build"] == "accountant", "audit_season": audit_season(state["period"]),
        "ai_audit_fee": ai_audit_fee(conn, empire, now), "ai_audit_done": bool(_one(
            conn, "SELECT 1 FROM empire_audits WHERE empire_id = %s AND kind = 'ai' AND period = %s", (empire["id"], state["period"]))),
        "next_audit_season": clock.period_label((state["period"] // data.AUDIT_SEASON_EVERY + (0 if audit_season(state["period"]) else 1))
                                                * data.AUDIT_SEASON_EVERY or data.AUDIT_SEASON_EVERY),
        "pacts": [{"id": p["id"], "kind": data.PACT_KINDS[p["kind"]][0], "legal": p["legal"], "terms": p["terms"], "status": p["status"],
                   "with": p["to_name"] if p["from_empire"] == empire["id"] else p["from_name"], "ours": p["from_empire"] == empire["id"],
                   "exposed": p["exposed_at"] is not None} for p in pacts],
        "pact_kinds": [{"code": code, "label": label, "legal": legal} for code, (label, legal) in data.PACT_KINDS.items()],
        "can_draft": seat["build"] == "lawyer" or is_head, "shared": shared,
        "others": [{"id": e["id"], "name": e["name"]} for e in table if e["id"] != empire["id"]],
        "applications": [{"id": a["id"], "display_name": a["display_name"], "build": a["build"], "legal": _legal(conn, a["player_id"])}
                         for a in _rows(conn, "SELECT a.id, a.player_id, p.display_name, a.build FROM empire_applications a"
                                              " JOIN players p ON p.id = a.player_id WHERE a.empire_id = %s AND a.status = 'waiting' ORDER BY a.id",
                                        (empire["id"],))] if is_head else [],
        "head_is_ceo": is_ceo(conn, empire["head_player_id"]), "you_are_ceo": is_ceo(conn, player_id),
        "notice_days": data.NOTICE_DAYS,
        "resignation": own_letter and _letter_public(own_letter, state["period"]),
        "resignations": [{**_letter_public(r, state["period"]), "id": r["id"], "name": r["display_name"]}
                         for r in letters if r["player_id"] != player_id] if is_head else [],
        "counter_offer_most": apply_bps(have["total"], data.COUNTER_OFFER_MOST_BPS),
        "division": leagues.standing(conn, empire["id"], now), "league_points": leagues.history(conn, empire["id"], state["period"]),
        "election": {"open": empire["kind"] == "player" and empire["status"] == "active",
                     "needed": sum(1 for s in seats if s["held"]) // 2 + 1,
                     "your_vote": next((v["display_name"] for v in votes if v["voter_id"] == player_id), None),
                     "tally": sorted(({"name": name, "votes": sum(1 for v in votes if v["display_name"] == name)}
                                      for name in {v["display_name"] for v in votes}), key=lambda t: -t["votes"])},
        "capital": _rows(conn, "SELECT p.display_name, sum(c.amount)::bigint AS amount FROM empire_capital c JOIN players p ON p.id = c.player_id"
                               " WHERE c.empire_id = %s GROUP BY p.display_name HAVING sum(c.amount) > 0 ORDER BY 2 DESC", (empire["id"],)),
        "expense_limit": empire["expense_limit"], "trade_limit_bps": empire["trade_limit_bps"],
        "registration_fee": naira(data.EMPIRE_REGISTRATION_NAIRA), "least_humans": data.EMPIRE_LEAST_HUMANS,
        "messages": list(reversed(_rows(conn, "SELECT m.id, p.display_name AS who, m.body, m.at, m.player_id = %s AS yours FROM empire_messages m"
                                              " JOIN players p ON p.id = m.player_id WHERE m.empire_id = %s ORDER BY m.id DESC LIMIT 50",
                                        (player_id, empire["id"])))),
        "events": _rows(conn, "SELECT words, at FROM empire_events WHERE empire_id = %s ORDER BY id DESC LIMIT 25", (empire["id"],)),
        "legal_record": _rows(conn, "SELECT words, at FROM legal_records WHERE player_id = %s ORDER BY id DESC LIMIT 5", (player_id,)),
    }
