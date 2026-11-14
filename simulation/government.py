"""Government, part 1: an elected Government Leader, the year's budget, the Assembly, and the stand-in.

Each game year the players elect a leader. Candidates stand in the last quarter of a year (a reputation of 80 and Level
20 or more, and no tribunal ban); every player past the protected start has one vote; the votes are counted as the year
closes, and the winner governs the year that follows.

The leader's power in part 1 is the budget: the rates of income tax, company tax, property tax and land tax, each within
fixed limits, put to the Assembly in the first quarter of the year. The Assembly is the head of every empire run by
players, one vote each, beside computer-run members whose leanings are published (some will not vote for a rise, some
not for a cut, some not for a big change either way). A budget the Assembly passes takes effect as that quarter closes;
one it throws out leaves the rates as they were.

The Assembly can remove a leader by a vote of no confidence, tabled by any head and counted when the quarter closes.

When nobody governs (nobody stood, nobody voted, the leader was removed, or put no budget by the deadline) a stand-in run
by rules does, with a personality drawn by lot when the year begins and published: steady keeps the rates, a hawk raises
them when the Treasury has been running down, a dove cuts them when it has been filling up.

Every rate the game charges is read here, so the budget changes what everybody pays.
"""

from __future__ import annotations

import hashlib
from datetime import datetime

from psycopg import Connection
from psycopg.rows import dict_row

from simulation import careers, clock, ledger
from simulation import world_data as data
from simulation.money import BPS, naira

KINDS = ("income", "company", "property", "land")
NAMES = {"income": "Income tax", "company": "Company tax", "property": "Property tax", "land": "Land tax"}
STAND_INS = {
    "steady": "Steady: keeps the rates as they are.",
    "hawk": "A hawk: raises every rate by a step when the Treasury has been running down.",
    "dove": "A dove: cuts every rate by a step when the Treasury has been filling up.",
}
LEANINGS = {
    "low_tax": "vote against any budget that raises a rate",
    "high_tax": "vote against any budget that cuts a rate",
    "steady": "vote against any budget that moves a rate by more than a step",
}


class GovernmentError(Exception):
    """A request the rules refuse, in words for the player."""


def _rows(conn: Connection, sql: str, params=()) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def _one(conn: Connection, sql: str, params=()) -> dict | None:
    rows = _rows(conn, sql, params)
    return rows[0] if rows else None


def ready(conn: Connection) -> bool:
    return _one(conn, "SELECT to_regclass('tax_rates') IS NOT NULL AS ok")["ok"] is True


def year_of(period: int) -> int:
    return (max(period, 1) - 1) // clock.QUARTERS_PER_YEAR + 1


def quarter_of(period: int) -> int:
    return (max(period, 1) - 1) % clock.QUARTERS_PER_YEAR + 1


def _lot(*parts) -> int:
    return int.from_bytes(hashlib.blake2b(":".join(str(p) for p in parts).encode(), digest_size=8).digest(), "big")


# ---------------------------------------------------------------------------
# The rates
# ---------------------------------------------------------------------------

def _defaults(conn: Connection) -> dict:
    return {"income": data.SALARY_TAX_BPS, "company": _one(conn, "SELECT company_tax_bps FROM world_state")["company_tax_bps"],
            "property": data.PROPERTY_TAX_BPS, "land": data.LAND_TAX_BPS}


def rates(conn: Connection) -> dict:
    """The rates in force. Before anybody has set one, the rates the world began with."""
    found = _defaults(conn)
    if ready(conn):
        for r in _rows(conn, "SELECT kind, bps FROM tax_rates"):
            found[r["kind"]] = r["bps"]
    return found


def tax_bps(conn: Connection, kind: str) -> int:
    return rates(conn)[kind]


def _set_rates(conn: Connection, new: dict, period: int, set_by: str) -> None:
    for kind, bps in new.items():
        conn.execute("INSERT INTO tax_rates (kind, bps, since_period, set_by) VALUES (%s, %s, %s, %s)"
                     " ON CONFLICT (kind) DO UPDATE SET bps = EXCLUDED.bps, since_period = EXCLUDED.since_period,"
                     " set_by = EXCLUDED.set_by WHERE tax_rates.bps <> EXCLUDED.bps",
                     (kind, bps, period + 1, set_by))
    # Company tax is read by the quarter close from the world itself.
    conn.execute("UPDATE world_state SET company_tax_bps = %s", (new["company"],))


def _check_rates(proposed: dict) -> dict:
    out = {}
    for kind in KINDS:
        value = proposed.get(kind)
        low, high = data.TAX_LIMITS_BPS[kind]
        if not isinstance(value, int) or isinstance(value, bool) or not low <= value <= high:
            raise GovernmentError(f"{NAMES[kind]} must be between {low / 100:.2f}% and {high / 100:.2f}%.")
        out[kind] = value
    if set(proposed) - set(KINDS):
        raise GovernmentError("A budget sets income tax, company tax, property tax and land tax, and nothing else.")
    return out


# ---------------------------------------------------------------------------
# Who governs
# ---------------------------------------------------------------------------

def _seed(conn: Connection) -> str:
    return _one(conn, "SELECT fortune_seed FROM world_state")["fortune_seed"]


def term(conn: Connection, year: int, now: datetime) -> dict:
    """This year's government. Made the first time it is needed, with the stand-in it would fall back on."""
    row = _one(conn, "SELECT * FROM government_terms WHERE year = %s", (year,))
    if row:
        return row
    stand_in = tuple(STAND_INS)[_lot("stand-in", _seed(conn), year) % len(STAND_INS)]
    conn.execute("INSERT INTO government_terms (year, stand_in, words, at) VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING",
                 (year, stand_in, "Nobody was elected: the stand-in governs.", now))
    return _one(conn, "SELECT * FROM government_terms WHERE year = %s", (year,))


def leader(conn: Connection, year: int) -> dict | None:
    row = _one(conn, "SELECT t.*, p.display_name FROM government_terms t JOIN players p ON p.id = t.leader_id"
                     " WHERE t.year = %s AND t.removed_period IS NULL", (year,))
    return row


def assembly(conn: Connection, year: int) -> list[dict]:
    """The Assembly: the head of every empire run by players (one vote each), and the computer-run members."""
    seed = _seed(conn)
    members = [{"kind": "head", "empire_id": e["id"], "empire": e["name"], "player_id": e["head_player_id"],
                "name": e["head_name"]}
               for e in _rows(conn, "SELECT e.id, e.name, e.head_player_id, p.display_name AS head_name FROM empires e"
                                    " JOIN players p ON p.id = e.head_player_id WHERE e.status = 'active' AND e.kind = 'player'"
                                    " ORDER BY e.id")]
    for n in range(data.ASSEMBLY_COMPUTER_SEATS):
        leaning = tuple(LEANINGS)[_lot("assembly", seed, year, n) % len(LEANINGS)]
        members.append({"kind": "computer", "seat": n + 1, "name": f"Member {n + 1}", "leaning": leaning,
                        "words": LEANINGS[leaning]})
    return members


def _computer_backs_budget(leaning: str, old: dict, new: dict) -> bool:
    moves = [new[k] - old[k] for k in KINDS]
    step = data.TAX_STEP_BPS
    if leaning == "low_tax":
        return all(m <= 0 for m in moves)
    if leaning == "high_tax":
        return all(m >= 0 for m in moves)
    return all(abs(m) <= step for m in moves)


# ---------------------------------------------------------------------------
# Elections
# ---------------------------------------------------------------------------

def _protected(conn: Connection, player_id) -> bool:
    mine = careers.career(conn, player_id)
    return mine is None or mine["level"] <= data.COMPETITION_PROTECTED_LEVEL


def stand(conn: Connection, player_id, pitch: str, now: datetime) -> dict:
    """Stand for next year's leadership, in the last quarter of a year, before the vote opens."""
    with conn.transaction():
        careers.books_open(conn, now)
        state = careers.world_now(conn, now)
        if quarter_of(state["period"]) != clock.QUARTERS_PER_YEAR or state["day"] > data.ELECTION_STAND_LAST_DAY:
            raise GovernmentError(f"Candidates stand in the last quarter of a game year, up to day {data.ELECTION_STAND_LAST_DAY}.")
        player = _one(conn, "SELECT reputation FROM players WHERE id = %s FOR UPDATE", (player_id,))
        mine = careers.career(conn, player_id)
        if player["reputation"] < data.LEADER_LEAST_REPUTATION or mine is None or mine["level"] < data.LEADER_LEAST_LEVEL:
            raise GovernmentError(f"A candidate needs a reputation of {data.LEADER_LEAST_REPUTATION} and Level "
                                  f"{data.LEADER_LEAST_LEVEL} or more.")
        from simulation import courts
        banned = courts.banned_until(conn, player_id) if courts.ready(conn) else None
        if banned is not None and banned >= state["period"]:
            raise GovernmentError("Nobody under a tribunal's ban may stand.")
        pitch = (pitch or "").strip()
        if not 1 <= len(pitch) <= 400:
            raise GovernmentError("Say in a few words what you would do (up to 400 letters).")
        year = year_of(state["period"]) + 1
        done = conn.execute("INSERT INTO government_candidates (year, player_id, pitch, at) VALUES (%s, %s, %s, %s)"
                            " ON CONFLICT DO NOTHING", (year, player_id, pitch, now)).rowcount
        if not done:
            raise GovernmentError("You are already standing.")
        return {"year": year}


def vote(conn: Connection, voter_id, candidate_id, now: datetime) -> dict:
    """One vote each, cast in the last quarter of a year after candidates have stood, and kept."""
    with conn.transaction():
        careers.books_open(conn, now)
        state = careers.world_now(conn, now)
        if quarter_of(state["period"]) != clock.QUARTERS_PER_YEAR or state["day"] <= data.ELECTION_STAND_LAST_DAY:
            raise GovernmentError(f"The vote opens on day {data.ELECTION_STAND_LAST_DAY + 1} of the last quarter of a game year.")
        conn.execute("SELECT 1 FROM players WHERE id = %s FOR UPDATE", (voter_id,))
        if _protected(conn, voter_id):
            raise GovernmentError(f"Voting opens at Level {data.COMPETITION_PROTECTED_LEVEL + 1}.")
        year = year_of(state["period"]) + 1
        if not _one(conn, "SELECT 1 AS x FROM government_candidates WHERE year = %s AND player_id = %s", (year, candidate_id)):
            raise GovernmentError("That player is not standing.")
        done = conn.execute("INSERT INTO government_votes (year, voter_id, candidate_id, at) VALUES (%s, %s, %s, %s)"
                            " ON CONFLICT DO NOTHING", (year, voter_id, candidate_id, now)).rowcount
        if not done:
            raise GovernmentError("You have voted. A vote is cast once.")
        return {"year": year}


def _count(conn: Connection, year: int, now: datetime) -> dict:
    """As a year closes: the votes for next year are counted. A tie goes by lot, never by who stood first."""
    t = term(conn, year, now)
    if t["leader_id"] is not None:
        return t
    tally = _rows(conn, "SELECT candidate_id, count(*) AS n FROM government_votes WHERE year = %s GROUP BY candidate_id", (year,))
    if not tally:
        return t
    seed = _seed(conn)
    best = max(tally, key=lambda r: (r["n"], _lot("election", seed, year, r["candidate_id"])))
    name = _one(conn, "SELECT display_name FROM players WHERE id = %s", (best["candidate_id"],))["display_name"]
    conn.execute("UPDATE government_terms SET leader_id = %s, votes = %s, words = %s WHERE year = %s",
                 (best["candidate_id"], best["n"], f"{name} was elected with {best['n']} of "
                  f"{sum(r['n'] for r in tally)} votes.", year))
    return _one(conn, "SELECT * FROM government_terms WHERE year = %s", (year,))


# ---------------------------------------------------------------------------
# The budget
# ---------------------------------------------------------------------------

def propose_budget(conn: Connection, player_id, proposed: dict, now: datetime) -> dict:
    """The leader puts the year's budget to the Assembly, in the first quarter of the year, by the deadline."""
    with conn.transaction():
        careers.books_open(conn, now)
        state = careers.world_now(conn, now)
        year = year_of(state["period"])
        boss = leader(conn, year)
        if boss is None or boss["leader_id"] != player_id:
            raise GovernmentError("Only the Government Leader puts a budget.")
        if quarter_of(state["period"]) != 1 or state["day"] > data.BUDGET_LAST_DAY:
            raise GovernmentError(f"The budget is put in the first quarter of the year, by day {data.BUDGET_LAST_DAY}.")
        new = _check_rates(proposed)
        done = conn.execute("INSERT INTO budgets (year, period, proposed_by, rates, at) VALUES (%s, %s, %s, %s, %s)"
                            " ON CONFLICT DO NOTHING", (year, state["period"], player_id,
                                                        __import__("json").dumps(new), now)).rowcount
        if not done:
            raise GovernmentError("This year's budget has been put. There is one a year.")
        return {"year": year, "rates": new}


def _seat_of_head(conn: Connection, player_id) -> dict | None:
    return _one(conn, "SELECT id, name FROM empires WHERE head_player_id = %s AND status = 'active' AND kind = 'player'",
                (player_id,))


def assembly_vote(conn: Connection, player_id, subject: str, aye: bool, now: datetime) -> dict:
    """The head of an empire votes on the budget or a motion, for their empire's seat. Once, and kept."""
    with conn.transaction():
        careers.books_open(conn, now)
        seat = _seat_of_head(conn, player_id)
        if seat is None:
            raise GovernmentError("The Assembly is the heads of the empires run by players. Lead one to vote in it.")
        kind, _, ident = subject.partition(":")
        table = {"budget": "budgets", "motion": "motions"}.get(kind)
        if table is None or not ident.isdigit():
            raise GovernmentError("There is no such vote.")
        row = _one(conn, f"SELECT status FROM {table} WHERE id = %s", (int(ident),))
        if row is None or row["status"] != "voting":
            raise GovernmentError("That vote is closed.")
        if not isinstance(aye, bool):
            raise GovernmentError("Vote for or against.")
        done = conn.execute("INSERT INTO assembly_votes (subject, player_id, empire_id, vote, at) VALUES (%s, %s, %s, %s, %s)"
                            " ON CONFLICT DO NOTHING", (subject, player_id, seat["id"], aye, now)).rowcount
        if not done:
            raise GovernmentError("Your empire's seat has voted. A vote is cast once.")
        return {"subject": subject, "vote": aye}


def no_confidence(conn: Connection, player_id, now: datetime) -> dict:
    """A head tables a vote of no confidence in the leader. Counted as the quarter closes."""
    with conn.transaction():
        careers.books_open(conn, now)
        if _seat_of_head(conn, player_id) is None:
            raise GovernmentError("A motion is tabled by the head of an empire run by players.")
        state = careers.world_now(conn, now)
        year = year_of(state["period"])
        if leader(conn, year) is None:
            raise GovernmentError("There is no elected leader to remove: the stand-in governs.")
        done = conn.execute("INSERT INTO motions (year, period, kind, proposed_by, at) VALUES (%s, %s, 'no_confidence', %s, %s)"
                            " ON CONFLICT DO NOTHING", (year, state["period"], player_id, now)).rowcount
        if not done:
            raise GovernmentError("A vote of no confidence is already before the Assembly.")
        return {"year": year}


def _tally(conn: Connection, subject: str, computer_aye) -> tuple[int, int]:
    """Heads' votes as cast, and the computer-run members' worked out from their leanings."""
    cast = _rows(conn, "SELECT vote FROM assembly_votes WHERE subject = %s", (subject,))
    ayes = sum(1 for v in cast if v["vote"])
    noes = len(cast) - ayes
    lobbied = {}
    if _one(conn, "SELECT to_regclass('lobbying') IS NOT NULL AS ok")["ok"]:
        lobbied = {r["seat"]: r["vote"] for r in _rows(conn, "SELECT seat, vote FROM lobbying WHERE subject = %s", (subject,))}
    for m in (m for m in assembly(conn, _subject_year(conn, subject)) if m["kind"] == "computer"):
        if m["seat"] in lobbied:                     # won over, in the open, by an empire's lobbying
            if lobbied[m["seat"]]:
                ayes += 1
            else:
                noes += 1
        elif computer_aye(m):
            ayes += 1
        else:
            noes += 1
    return ayes, noes


def _subject_year(conn: Connection, subject: str) -> int:
    kind, _, ident = subject.partition(":")
    table = "budgets" if kind == "budget" else "motions"
    return _one(conn, f"SELECT year FROM {table} WHERE id = %s", (int(ident),))["year"]


def _treasury_trend(conn: Connection, period: int) -> int:
    """How the Treasury's cash moved over the last year: above nought, it filled up."""
    acct = ledger.account_id(conn, ledger.TREASURY)
    row = _one(conn, "SELECT coalesce(sum(l.amount), 0)::bigint AS moved FROM ledger_entries l"
                     " JOIN ledger_transactions t ON t.id = l.transaction_id WHERE l.account_id = %s AND l.asset = 'NGN'"
                     " AND t.period BETWEEN %s AND %s", (acct, period - clock.QUARTERS_PER_YEAR + 1, period))
    return row["moved"] if row else 0


def _stand_in_budget(conn: Connection, year: int, period: int, now: datetime) -> dict:
    t = term(conn, year, now)
    old = rates(conn)
    trend = _treasury_trend(conn, period)
    step = data.TAX_STEP_BPS
    new = dict(old)
    if t["stand_in"] == "hawk" and trend < 0:
        new = {k: v + step for k, v in old.items()}
    elif t["stand_in"] == "dove" and trend > 0:
        new = {k: v - step for k, v in old.items()}
    return {k: min(max(v, data.TAX_LIMITS_BPS[k][0]), data.TAX_LIMITS_BPS[k][1]) for k, v in new.items()}


# ---------------------------------------------------------------------------
# The quarter close
# ---------------------------------------------------------------------------

def at_close(conn: Connection, period: int, now: datetime) -> dict:
    """As a quarter closes: the budget and any motion are counted; a year's last quarter counts the election for the
    next; and a first quarter with no budget put gets the stand-in's."""
    if not ready(conn):
        return {}
    out: dict = {}
    year = year_of(period)
    term(conn, year, now)
    if quarter_of(period) == 1 and not _one(conn, "SELECT 1 AS x FROM budgets WHERE year = %s", (year,)):
        # No leader, or a leader who put nothing by the deadline: the stand-in's budget, which needs no vote.
        new = _stand_in_budget(conn, year, period, now)
        conn.execute("INSERT INTO budgets (year, period, rates, status, words, at) VALUES (%s, %s, %s, 'passed', %s, %s)",
                     (year, period, __import__("json").dumps(new), "The stand-in's budget: no leader put one.", now))
        _set_rates(conn, new, period, "the stand-in")
        out["budget"] = "stand-in"
    for b in _rows(conn, "SELECT * FROM budgets WHERE status = 'voting' AND period <= %s ORDER BY id", (period,)):
        old = rates(conn)
        ayes, noes = _tally(conn, f"budget:{b['id']}", lambda m: _computer_backs_budget(m["leaning"], old, b["rates"]))
        passed = ayes > noes
        conn.execute("UPDATE budgets SET status = %s, votes_for = %s, votes_against = %s, words = %s WHERE id = %s",
                     ("passed" if passed else "rejected", ayes, noes,
                      f"The Assembly {'passed' if passed else 'threw out'} the budget, {ayes} to {noes}.", b["id"]))
        if passed:
            _set_rates(conn, {k: int(v) for k, v in b["rates"].items()}, period, "the Government Leader's budget")
        out["budget"] = "passed" if passed else "rejected"
    for m in _rows(conn, "SELECT * FROM motions WHERE status = 'voting' AND period <= %s AND kind = 'levy' ORDER BY id",
                   (period,)) if _has_powers(conn) else []:
        out["levy"] = _count_levy(conn, m, period, now)
    for m in _rows(conn, "SELECT * FROM motions WHERE status = 'voting' AND period <= %s AND kind = 'no_confidence' ORDER BY id",
                   (period,)):
        # Computer-run members back the leader unless the leader's budget went against their leaning.
        budget = _one(conn, "SELECT * FROM budgets WHERE year = %s AND proposed_by IS NOT NULL", (m["year"],))
        before = _one(conn, "SELECT rates FROM budgets WHERE year = %s", (m["year"] - 1,))
        old = {k: int(v) for k, v in before["rates"].items()} if before else _defaults(conn)
        ayes, noes = _tally(conn, f"motion:{m['id']}", lambda c: budget is not None and budget["status"] == "passed"
                            and not _computer_backs_budget(c["leaning"], old, {k: int(v) for k, v in budget["rates"].items()}))
        passed = ayes > noes
        conn.execute("UPDATE motions SET status = %s, votes_for = %s, votes_against = %s WHERE id = %s",
                     ("passed" if passed else "failed", ayes, noes, m["id"]))
        if passed:
            conn.execute("UPDATE government_terms SET removed_period = %s, words = %s WHERE year = %s",
                         (period, f"Removed by the Assembly, {ayes} to {noes}: the stand-in governs for the rest of the year.",
                          m["year"]))
        out["motion"] = "passed" if passed else "failed"
    if _has_powers(conn):
        boss = leader(conn, year)
        if boss is not None:
            # The leader's pay for the quarter, from the Treasury.
            ledger.pay_up_to(conn, payer=ledger.account_id(conn, ledger.TREASURY),
                             receiver=ledger.player_account_id(conn, boss["leader_id"]), wanted=naira(data.LEADER_PAY_NAIRA),
                             kind="leader_pay", memo=f"The Government Leader's pay, {clock.period_label(period)}", period=period)
    if quarter_of(period) == clock.QUARTERS_PER_YEAR:
        t = _count(conn, year + 1, now)
        out["elected"] = str(t["leader_id"]) if t["leader_id"] else None
    return out


# ---------------------------------------------------------------------------
# Part 2: the leader's other powers, and lobbying
# ---------------------------------------------------------------------------

def _has_powers(conn: Connection) -> bool:
    return _one(conn, "SELECT to_regclass('decrees') IS NOT NULL AS ok")["ok"] is True


def _the_leader(conn: Connection, player_id, now: datetime) -> tuple[dict, int]:
    state = careers.world_now(conn, now)
    boss = leader(conn, year_of(state["period"]))
    if boss is None or boss["leader_id"] != player_id:
        raise GovernmentError("Only the Government Leader may do that.")
    return boss, state["period"]


def decree(conn: Connection, player_id, rate_bps: int, now: datetime) -> dict:
    """Set next quarter's Central Bank rate by decree. Once a quarter. The close holds it within three points of the
    Central Bank's own rule, and it costs prices and confidence."""
    with conn.transaction():
        careers.books_open(conn, now)
        _boss, period = _the_leader(conn, player_id, now)
        if not isinstance(rate_bps, int) or isinstance(rate_bps, bool) or not 0 <= rate_bps <= 5000:
            raise GovernmentError("Name a rate between 0% and 50%.")
        done = conn.execute("INSERT INTO decrees (period, leader_id, rate_bps, at) VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING",
                            (period, player_id, rate_bps, now)).rowcount
        if not done:
            raise GovernmentError("There has been a decree this quarter. One a quarter.")
        return {"period": period, "rate_bps": rate_bps}


def decreed_rate(conn: Connection, period: int) -> int | None:
    if not ready(conn) or not _has_powers(conn):
        return None
    row = _one(conn, "SELECT rate_bps FROM decrees WHERE period = %s", (period,))
    return row["rate_bps"] if row else None


def apply_decree(conn: Connection, period: int, rule_bps: int, decreed: int, reason: str) -> tuple[int, str]:
    """At the close: the decree sets the rate, held within the limit of the Central Bank's own."""
    final = min(max(decreed, rule_bps - data.DECREE_MOST_BPS, 0), rule_bps + data.DECREE_MOST_BPS)
    conn.execute("UPDATE decrees SET applied_bps = %s, rule_bps = %s WHERE period = %s", (final, rule_bps, period))
    return final, (f"By decree of the Government Leader: {final / 100:.2f}%. The Central Bank's own rule would have set "
                   f"{rule_bps / 100:.2f}% ({reason}). A decree costs: prices rose faster and confidence fell.")


def propose_levy(conn: Connection, player_id, empire_id: int, bps: int, reason: str, now: datetime) -> dict:
    """Ask the Assembly to take up to two per cent of one empire's cash for the Treasury. Counted at the close."""
    with conn.transaction():
        careers.books_open(conn, now)
        _boss, period = _the_leader(conn, player_id, now)
        target = _one(conn, "SELECT id, name FROM empires WHERE id = %s AND status = 'active'", (empire_id,))
        if target is None:
            raise GovernmentError("There is no such empire.")
        if not isinstance(bps, int) or isinstance(bps, bool) or not 1 <= bps <= data.LEVY_MOST_BPS:
            raise GovernmentError(f"A levy takes between 0.01% and {data.LEVY_MOST_BPS / 100:.0f}% of an empire's cash.")
        reason = (reason or "").strip()
        if not 1 <= len(reason) <= 300:
            raise GovernmentError("Give the Assembly a reason (up to 300 letters).")
        done = conn.execute("INSERT INTO motions (year, period, kind, proposed_by, payload, at) VALUES (%s, %s, 'levy', %s, %s, %s)"
                            " ON CONFLICT DO NOTHING",
                            (year_of(period), period, player_id,
                             __import__("json").dumps({"empire_id": target["id"], "empire": target["name"], "bps": bps,
                                                       "reason": reason}), now)).rowcount
        if not done:
            raise GovernmentError("A levy is already before the Assembly.")
        return {"empire": target["name"], "bps": bps}


def _count_levy(conn: Connection, m: dict, period: int, now: datetime) -> str:
    # Computer-run members who favour high taxes back a levy; the rest protect the empires.
    ayes, noes = _tally(conn, f"motion:{m['id']}", lambda c: c["leaning"] == "high_tax")
    passed = ayes > noes
    collected = None
    if passed:
        target = _one(conn, "SELECT account_id, name FROM empires WHERE id = %s", (m["payload"]["empire_id"],))
        wanted = ledger.balance(conn, target["account_id"]) * int(m["payload"]["bps"]) // BPS
        collected = ledger.pay_up_to(conn, payer=target["account_id"], receiver=ledger.account_id(conn, ledger.TREASURY),
                                     wanted=wanted, kind="levy", memo=f"A levy on {target['name']}, passed by the Assembly",
                                     period=period) if wanted > 0 else 0
    conn.execute("UPDATE motions SET status = %s, votes_for = %s, votes_against = %s, collected = %s WHERE id = %s",
                 ("passed" if passed else "failed", ayes, noes, collected, m["id"]))
    return "passed" if passed else "failed"


def lobby(conn: Connection, player_id, subject: str, seat: int, now: datetime) -> dict:
    """The head of an empire pays the Treasury, in the open, to win over one computer-run member's vote. The member then
    votes as the head did, so the head must vote first."""
    with conn.transaction():
        careers.books_open(conn, now)
        empire = _one(conn, "SELECT id, name, account_id FROM empires WHERE head_player_id = %s AND status = 'active'"
                            " AND kind = 'player' FOR UPDATE", (player_id,))
        if empire is None:
            raise GovernmentError("Lobbying is done by the head of an empire run by players.")
        kind, _, ident = subject.partition(":")
        table = {"budget": "budgets", "motion": "motions"}.get(kind)
        row = _one(conn, f"SELECT status, year FROM {table} WHERE id = %s", (int(ident),)) if table and ident.isdigit() else None
        if row is None or row["status"] != "voting":
            raise GovernmentError("That vote is closed.")
        mine = _one(conn, "SELECT vote FROM assembly_votes WHERE subject = %s AND empire_id = %s", (subject, empire["id"]))
        if mine is None:
            raise GovernmentError("Vote first: a member you win over votes as your seat did.")
        if not isinstance(seat, int) or not 1 <= seat <= data.ASSEMBLY_COMPUTER_SEATS:
            raise GovernmentError("There is no such member.")
        if _one(conn, "SELECT count(*) AS n FROM lobbying WHERE subject = %s AND empire_id = %s",
                (subject, empire["id"]))["n"] >= data.LOBBY_MOST:
            raise GovernmentError(f"An empire may win over {data.LOBBY_MOST} members on one vote.")
        if _one(conn, "SELECT 1 AS x FROM lobbying WHERE subject = %s AND seat = %s", (subject, seat)):
            raise GovernmentError("Somebody has already won that member over on this vote.")
        cost = naira(data.LOBBY_NAIRA)
        try:
            ledger.transfer(conn, payer=empire["account_id"], receiver=ledger.account_id(conn, ledger.TREASURY), amount=cost,
                            kind="lobbying", memo=f"{empire['name']} lobbied Member {seat} on {subject}",
                            period=careers.world_now(conn, now)["period"])
        except ledger.InsufficientFunds:
            raise GovernmentError(f"Lobbying a member costs {cost / 100:,.0f} naira, which the empire does not have.") from None
        conn.execute("INSERT INTO lobbying (subject, seat, empire_id, vote, paid, at) VALUES (%s, %s, %s, %s, %s, %s)",
                     (subject, seat, empire["id"], mine["vote"], cost, now))
        return {"subject": subject, "seat": seat, "vote": mine["vote"], "paid": cost}


# ---------------------------------------------------------------------------
# The page
# ---------------------------------------------------------------------------

def view(conn: Connection, player_id, now: datetime) -> dict:
    if not ready(conn):
        return {"ready": False}
    state = careers.world_now(conn, now)
    period, year = state["period"], year_of(state["period"])
    t = _one(conn, "SELECT * FROM government_terms WHERE year = %s", (year,))
    boss = leader(conn, year)
    stand_in = t["stand_in"] if t else tuple(STAND_INS)[_lot("stand-in", _seed(conn), year) % len(STAND_INS)]
    in_force = rates(conn)
    budget = _one(conn, "SELECT * FROM budgets WHERE year = %s", (year,))
    motion = _one(conn, "SELECT * FROM motions WHERE year = %s AND kind = 'no_confidence' ORDER BY id DESC LIMIT 1", (year,))
    seat = _seat_of_head(conn, player_id)
    voted = {r["subject"] for r in _rows(conn, "SELECT subject FROM assembly_votes WHERE empire_id = %s", (seat["id"],))} if seat else set()
    in_election = quarter_of(period) == clock.QUARTERS_PER_YEAR
    candidates = [{"player_id": str(c["player_id"]), "name": c["display_name"], "pitch": c["pitch"], "reputation": c["reputation"]}
                  for c in _rows(conn, "SELECT c.*, p.display_name, p.reputation FROM government_candidates c JOIN players p"
                                       " ON p.id = c.player_id WHERE c.year = %s ORDER BY c.at", (year + 1,))]
    my_vote = _one(conn, "SELECT candidate_id FROM government_votes WHERE year = %s AND voter_id = %s", (year + 1, player_id))
    player = _one(conn, "SELECT reputation FROM players WHERE id = %s", (player_id,))
    mine = careers.career(conn, player_id)
    return {
        "ready": True, "quarter": clock.period_label(period), "day": state["day"], "year": year,
        "leader": None if boss is None else {"player_id": str(boss["leader_id"]), "name": boss["display_name"], "votes": boss["votes"],
                                              "is_you": boss["leader_id"] == player_id},
        "term_words": t["words"] if t else None,
        "stand_in": {"kind": stand_in, "words": STAND_INS[stand_in]},
        "rates": [{"kind": k, "name": NAMES[k], "bps": in_force[k], "least_bps": data.TAX_LIMITS_BPS[k][0],
                   "most_bps": data.TAX_LIMITS_BPS[k][1]} for k in KINDS],
        "budget": None if budget is None else {
            "id": budget["id"], "rates": budget["rates"], "status": budget["status"], "votes_for": budget["votes_for"],
            "votes_against": budget["votes_against"], "words": budget["words"], "by_stand_in": budget["proposed_by"] is None,
            "voted": f"budget:{budget['id']}" in voted},
        "can_propose": bool(boss and boss["leader_id"] == player_id and budget is None and quarter_of(period) == 1
                            and state["day"] <= data.BUDGET_LAST_DAY),
        "budget_last_day": data.BUDGET_LAST_DAY,
        "motion": None if motion is None else {"id": motion["id"], "status": motion["status"], "votes_for": motion["votes_for"],
                                               "votes_against": motion["votes_against"], "voted": f"motion:{motion['id']}" in voted},
        "assembly": [{k: (str(v) if k == "player_id" and v is not None else v) for k, v in m.items()} for m in assembly(conn, year)],
        "your_seat": seat["name"] if seat else None,
        **(_powers_view(conn, player_id, period, year, seat, boss) if _has_powers(conn) else {}),
        "election": {
            "open": in_election, "for_year": year + 1, "stand_last_day": data.ELECTION_STAND_LAST_DAY,
            "candidates": candidates, "your_vote": str(my_vote["candidate_id"]) if my_vote else None,
            "can_stand": bool(in_election and state["day"] <= data.ELECTION_STAND_LAST_DAY and mine
                              and mine["level"] >= data.LEADER_LEAST_LEVEL and player["reputation"] >= data.LEADER_LEAST_REPUTATION),
            "can_vote": bool(in_election and state["day"] > data.ELECTION_STAND_LAST_DAY and not _protected(conn, player_id)
                             and my_vote is None),
            "least_reputation": data.LEADER_LEAST_REPUTATION, "least_level": data.LEADER_LEAST_LEVEL,
        },
    }


def _powers_view(conn: Connection, player_id, period: int, year: int, seat: dict | None, boss: dict | None) -> dict:
    decree_now = _one(conn, "SELECT rate_bps FROM decrees WHERE period = %s", (period,))
    last = _one(conn, "SELECT * FROM decrees WHERE applied_bps IS NOT NULL ORDER BY period DESC LIMIT 1")
    levies = [{"id": m["id"], "empire": m["payload"]["empire"], "bps": int(m["payload"]["bps"]), "reason": m["payload"]["reason"],
               "status": m["status"], "votes_for": m["votes_for"], "votes_against": m["votes_against"],
               "collected": m["collected"]}
              for m in _rows(conn, "SELECT * FROM motions WHERE kind = 'levy' AND year = %s ORDER BY id DESC", (year,))]
    lobbied = [{"subject": r["subject"], "seat": r["seat"], "empire": r["name"], "vote": r["vote"], "paid": r["paid"]}
               for r in _rows(conn, "SELECT l.*, e.name FROM lobbying l JOIN empires e ON e.id = l.empire_id"
                                    " ORDER BY l.at DESC LIMIT 30")]
    is_leader = bool(boss and boss["leader_id"] == player_id)
    return {
        "powers": {
            "is_leader": is_leader, "can_decree": is_leader and decree_now is None,
            "decree_now_bps": decree_now["rate_bps"] if decree_now else None,
            "last_decree": None if last is None else {"quarter": clock.period_label(last["period"]), "rate_bps": last["applied_bps"],
                                                       "rule_bps": last["rule_bps"]},
            "decree_most_bps": data.DECREE_MOST_BPS, "decree_price_bps": data.DECREE_PRICE_PUSH_BPS,
            "decree_confidence_bps": data.DECREE_CONFIDENCE_BPS, "levy_most_bps": data.LEVY_MOST_BPS,
            "leader_pay": naira(data.LEADER_PAY_NAIRA), "lobby_cost": naira(data.LOBBY_NAIRA), "lobby_most": data.LOBBY_MOST,
            "empires": [{"id": e["id"], "name": e["name"]} for e in _rows(conn, "SELECT id, name FROM empires WHERE status = 'active'"
                                                                                 " ORDER BY name")] if is_leader else [],
            "levies": levies, "lobbied": lobbied, "can_lobby": seat is not None,
        },
    }
