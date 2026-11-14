"""Rank cases and the CEO rank (design document, sections 6 and 9).

A career stops at Levels 20, 40, 60 and 80. To go past, a player must have reached the required
mastery across their build's modules and then pass a rank case: one large piece of practical
work in several parts, all on the live world. It carries a fee in naira which leaves the economy
(it is paid into the prize pool), and a failed case can be sat again after three real days.

Each case is made at the moment it is begun, from the world as it then stands: the company is
drawn for that player and that attempt, and a company already used for a case this quarter is
avoided, so no two cases are alike and answers cannot be passed on.

The CEO rank is earned the same way on the leadership track: Level 60, the CEO rank case, and a
reputation of 75.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from simulation import careers, clock, ledger
from simulation import objectives as o
from simulation import world_data as data
from simulation.money import apply_bps, naira

# The parts of each track's case. Those marked True are done on the one company the case is about.
CASES = {
    "asset_manager": ("A full review of a company's accounts",
                   (("ac_ratios", True), ("ac_cash_flow", True), ("ac_income", True))),
    "asset_manager": ("A client's portfolio, a valuation and the risk in its bonds",
                      (("am_review", False), ("ib_multiples", True), ("rm_shock", False))),
    "investment_banker": ("A full company valuation and how to finance it",
                          (("ib_multiples", True), ("ib_capacity", True), ("ib_rights", True), ("ib_bond", False))),
    "risk_manager": ("A full risk review: cash, a bad quarter and a rate shock",
                     (("rm_liquidity", True), ("rm_stress", True), ("rm_shock", False))),
    "investment_banker": ("A contested transfer of a company: who controls it, what it owes, and whether its promises hold",
               (("lw_control", True), ("lw_debts", True), ("lw_contract", True), ("lw_rules", False))),
    "investment_banker": ("A published investigation: the results, the claims made about them, and the industry around them",
                   (("jr_results", True), ("jr_verify", True), ("jr_league", False))),
    "ceo": ("The board's review of a business: its return, its costs, its dividend and a takeover",
            (("ce_return", True), ("ce_breakeven", True), ("ce_payout", True), ("ce_buy", True))),
}
PUBLIC_TERMS = ("client", "situation", "task", "pass_when", "given", "fields")


class RankError(Exception):
    """A request about a rank case that the rules do not allow. The words are for the player."""


def _rows(conn: Connection, sql: str, params=()) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def _one(conn: Connection, sql: str, params=()) -> dict | None:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchone()


# ---------------------------------------------------------------------------
# What is needed
# ---------------------------------------------------------------------------

def _needs(track: str, gate: int, rows: list[dict]) -> list[dict]:
    """The mastery a case asks for, against what the player has."""
    wanted = data.RANK_MASTERY[20 if track == "ceo" else gate]
    words = {"learned": "learned (passed on your own)", "practised": "practised (passed with your empire)",
             "proven": "proven (passed in a weekend challenge)"}
    out = []
    for stage in ("learned", "practised", "proven"):
        need = len(rows) if wanted[stage] == "all" else min(wanted[stage], len(rows))
        have = sum(1 for r in rows if r[stage])
        out.append({"stage": stage, "words": words[stage], "need": need, "have": have, "met": have >= need,
                    "missing": [r["module"] for r in rows if not r[stage]]})
    return out


def _fee(gate: int, track: str, wage_index_bps: int) -> int:
    start = data.CEO_CASE_FEE_NAIRA if track == "ceo" else data.RANK_CASE_FEE_NAIRA[gate]
    return apply_bps(naira(start), wage_index_bps) // 100_000 * 100_000          # it keeps pace with wages; to the nearest ₦1,000


HELD_BACK = ("The worked answers and the arithmetic are shown when this quarter has closed, so that they cannot be carried "
             "into another case.")


def _public(case: dict, period: int) -> dict:
    """A case as its own player may see it. Before it is judged, nothing here gives an answer away;
    and after it, the worked answers are held back until the quarter the case was made from has
    closed, so that they cannot be handed to somebody sitting a case from the same figures."""
    terms = case["terms"]
    result = case["result"]
    if result is not None and period <= case["period"]:
        result = {**result, "held_back": HELD_BACK,
                  "parts": [{**{k: v for k, v in part.items() if k != "answers"},
                             "debrief": {"plain": "", "method": part["debrief"]["method"], "maths": ""}} for part in result["parts"]]}
    return {
        "id": case["id"], "track": case["track"], "track_name": o.track_name(case["track"]), "gate": case["gate"], "title": terms["title"],
        "fee": case["fee"], "state": case["state"], "started_at": case["started_at"], "due_at": case["due_at"],
        "judged_at": case["judged_at"], "pass_mark": terms["pass_mark"], "company": terms.get("company"),
        "parts": [{"template": part["template"], "title": part["title"], "module": part["module"], "idea": part["idea"],
                   "terms": {k: part["terms"][k] for k in PUBLIC_TERMS if part["terms"].get(k) is not None}} for part in terms["parts"]],
        "submission": case["submission"], "result": result,
    }


def standing(conn: Connection, player_id, now: datetime) -> dict:
    """Where a player stands on ranks: the gate ahead in their build, what it needs, the case in
    hand if any, and the same for the CEO rank once the leadership track is open to them."""
    state = careers.world_now(conn, now)
    mine = careers.career(conn, player_id)
    active = _one(conn, "SELECT * FROM rank_cases WHERE player_id = %s AND state = 'active'", (player_id,))
    past = _rows(conn, "SELECT * FROM rank_cases WHERE player_id = %s AND state <> 'active' ORDER BY id DESC LIMIT 6", (player_id,))
    out = {"active": active and _public(active, state["period"]), "past": [_public(c, state["period"]) for c in past], "tracks": [],
           "retry_days": data.RANK_CASE_RETRY_DAYS, "hours": data.RANK_CASE_HOURS, "gates": list(data.RANK_GATES)}
    if mine is None:
        return out
    out["tracks"].append(_track_standing(conn, player_id, mine, mine["build"], state, now, active))
    if o.ceo_open(conn, player_id, mine):
        out["tracks"].append(_track_standing(conn, player_id, mine, "ceo", state, now, active))
    return out


def waiting(conn: Connection, player_id, mine: dict, now: datetime) -> bool:
    """True when the player has a rank case in hand, or could begin their build's case (or the CEO case) now. Shown as a dot
    on the profile picture. Cheap when the player is short of the gate, which is most of the time."""
    if _one(conn, "SELECT 1 FROM rank_cases WHERE player_id = %s AND state = 'active'", (player_id,)):
        return True
    state = None
    if mine["rank"] < len(data.RANK_GATES) and mine["level"] >= careers.level_cap(mine["rank"]):
        state = careers.world_now(conn, now)
        if _track_standing(conn, player_id, mine, mine["build"], state, now, None)["can_begin"]:
            return True
    if o.ceo_open(conn, player_id, mine):
        return _track_standing(conn, player_id, mine, "ceo", state or careers.world_now(conn, now), now, None)["can_begin"]
    return False


def _retry_at(conn: Connection, player_id, track: str) -> datetime | None:
    last = _one(conn, "SELECT judged_at FROM rank_cases WHERE player_id = %s AND track = %s AND state IN ('failed', 'not_done')"
                      " ORDER BY id DESC LIMIT 1", (player_id, track))
    return last["judged_at"] + timedelta(days=data.RANK_CASE_RETRY_DAYS) if last else None


def _track_standing(conn, player_id, mine: dict, track: str, state: dict, now: datetime, active) -> dict:
    rows = o.mastery(conn, player_id, track)
    retry = _retry_at(conn, player_id, track)
    if track == "ceo":
        player = _one(conn, "SELECT reputation, ceo_since FROM players WHERE id = %s", (player_id,))
        passed = bool(_one(conn, "SELECT 1 FROM rank_cases WHERE player_id = %s AND track = 'ceo' AND state = 'passed'", (player_id,)))
        gate, done = data.CEO_LEVEL, player["ceo_since"] is not None
        needs = _needs(track, gate, [r for r in rows if r["level"] <= gate])
        why = ("You hold the CEO rank." if done else "You have passed the CEO rank case." if passed else None)
        extra = {"ceo": {"earned": done, "since": player["ceo_since"], "case_passed": passed,
                         "level": {"need": data.CEO_LEVEL, "have": mine["level"], "met": mine["level"] >= data.CEO_LEVEL},
                         "reputation": {"need": data.CEO_REPUTATION, "have": player["reputation"], "met": player["reputation"] >= data.CEO_REPUTATION}}}
        finished = passed
        title = "The CEO rank case"
        at_gate = True
    else:
        gate = careers.level_cap(mine["rank"])
        finished = mine["rank"] >= len(data.RANK_GATES)
        # (A gate asks for the modules that open at or below it: the higher bands come after it.)
        needs = [] if finished else _needs(track, gate, [r for r in rows if r["level"] <= gate])
        at_gate = mine["level"] >= gate
        why = "You have passed every rank case. The road to Level 100 is open." if finished else None
        extra = {}
        title = None if finished else f"The rank case at Level {gate}"
    if why is None:
        if not at_gate:
            why = f"Reach Level {gate} first. You are at Level {mine['level']}."
        elif not all(n["met"] for n in needs):
            lacking = next(n for n in needs if not n["met"])
            why = f"{lacking['need']} modules must be {lacking['words']}. You have {lacking['have']}."
        elif active:
            why = "You have a rank case in hand. Hand it in first."
        elif retry and now < retry:
            why = f"A case that was not passed can be sat again after {data.RANK_CASE_RETRY_DAYS} real days: from {clock.to_lagos(retry):%A %d %B, %H:%M} (Lagos time)."
    fee = None if finished else _fee(gate, track, state["wage_index_bps"])
    return {"track": track, "name": o.track_name(track), "title": title, "gate": None if finished else gate, "level": mine["level"],
            "rank": mine["rank"], "rank_name": careers.rank_name(mine["rank"]), "at_gate": at_gate, "needs": needs,
            "fee": fee, "pass_mark": None if finished else _pass_mark(track, gate), "what": CASES[track][0],
            "parts": [o.TEMPLATES[code].module for code, _ in CASES[track][1]], "retry_at": retry if retry and now < retry else None,
            "can_begin": why is None, "why_not": why, "modules": rows, **extra}


def _pass_mark(track: str, gate: int) -> int:
    return data.CEO_CASE_PASS if track == "ceo" else data.RANK_CASE_PASS[gate]


# ---------------------------------------------------------------------------
# Beginning a case
# ---------------------------------------------------------------------------

def _order(seed: str, items: list, key) -> list:
    return sorted(items, key=lambda item: hashlib.sha256(f"{seed}:{key(item)}".encode()).digest())


def _compose(conn: Connection, ctx: dict, track: str, salt: str) -> tuple[dict | None, list[dict]] | None:
    """Draw the company and make the parts. Returns None when the world cannot furnish a case at this moment."""
    parts = CASES[track][1]
    used = {r["company"] for r in _rows(conn, "SELECT terms -> 'company' ->> 'ticker' AS company FROM rank_cases WHERE period = %s AND track = %s",
                                         (ctx["period"], track))}
    # A case is set on a company that makes or sells things: a bank's or an insurer's accounts read differently.
    companies = _rows(conn, "SELECT DISTINCT c.id AS company_id, c.ticker, c.name FROM companies c JOIN company_reports r ON r.company_id = c.id"
                            " WHERE r.period = %s AND c.listed AND c.sector NOT IN ('banking', 'insurance')", (ctx["period"] - 1,))
    ordered = _order(salt + str(ctx["player_id"]), companies, lambda c: c["ticker"])
    ordered.sort(key=lambda c: c["ticker"] in used)             # a company not yet used for a case this quarter comes first
    token = o.SALT.set(salt)
    try:
        loose = []
        for code, on_company in parts:
            if not on_company:
                terms = o.TEMPLATES[code].offer({**ctx})
                if terms is None:
                    return None
                loose.append((code, terms))
        if not any(on_company for _c, on_company in parts):
            return None, [_part(code, terms) for code, terms in loose]
        for company in ordered:
            made = []
            for code, on_company in parts:
                if on_company:
                    terms = o.TEMPLATES[code].offer({**ctx, "target": company["company_id"]})
                    if terms is None:
                        break
                    made.append((code, terms))
            else:
                both = dict(made + loose)
                return ({"ticker": company["ticker"], "name": company["name"]}, [_part(code, both[code]) for code, _ in parts])
        return None
    finally:
        o.SALT.reset(token)


def _part(code: str, terms: dict) -> dict:
    template = o.TEMPLATES[code]
    return {"template": code, "title": template.title, "module": template.module, "idea": template.idea, "terms": terms}


def begin(conn: Connection, player_id, track: str, now: datetime) -> dict:
    """Begin a rank case. The fee is paid at this moment, into the prize pool; it is not returned."""
    with conn.transaction():
        try:
            careers.books_open(conn, now)
        except careers.CareerError as closing:
            raise RankError(str(closing)) from None
        _one(conn, "SELECT id FROM players WHERE id = %s FOR UPDATE", (player_id,))
        mine = careers.career(conn, player_id, lock=True)
        if mine is None or track not in (mine["build"], "ceo") or (track == "ceo" and not o.ceo_open(conn, player_id, mine)):
            raise RankError("That rank case is not open to you.")
        state = careers.world_now(conn, now)
        active = _one(conn, "SELECT * FROM rank_cases WHERE player_id = %s AND state = 'active'", (player_id,))
        where = _track_standing(conn, player_id, mine, track, state, now, active)
        if not where["can_begin"]:
            raise RankError(where["why_not"])
        gate = where["gate"]
        attempt = _one(conn, "SELECT count(*) AS n FROM rank_cases WHERE player_id = %s AND track = %s", (player_id, track))["n"] + 1
        salt = f":case:{track}:{gate}:{attempt}"
        ctx = o._context(conn, player_id, now)
        made = _compose(conn, ctx, track, salt)
        if made is None:
            raise RankError("A case cannot be set at this point in the quarter: the figures it needs are not all there. "
                            "Nothing has been charged. Try again after the next Closing Bell.")
        company, parts = made
        world = _one(conn, "SELECT world_start, weeks_ahead FROM world_state")
        quarter_end = clock.next_quarter_end(now, clock.effective_start(world["world_start"], world["weeks_ahead"]))
        due = min(now + timedelta(hours=data.RANK_CASE_HOURS), quarter_end)
        fee = where["fee"]
        try:
            ledger.transfer(conn, payer=ctx["account"], receiver=ledger.account_id(conn, ledger.PRIZE_POOL), amount=fee, kind="rank_case_fee",
                            memo=f"Rank case fee: {where['title']} ({o.track_name(track)})", period=state["period"])
        except ledger.InsufficientFunds:
            raise RankError(f"The fee for this case is ₦{fee / 100:,.0f}, and you do not have that much cash.") from None
        terms = {"title": CASES[track][0], "company": company, "parts": parts, "salt": salt, "pass_mark": where["pass_mark"],
                 "attempt": attempt}
        case = _one(conn, "INSERT INTO rank_cases (player_id, track, gate, period, fee, terms, started_at, due_at)"
                          " VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING *",
                    (player_id, track, gate, state["period"], fee, Jsonb(terms), now, due))
        careers._event(conn, player_id, mine["build"], "rank_case",
                       f"Began {where['title'].lower()} ({o.track_name(track)}). Fee paid: ₦{fee / 100:,.0f}.", now)
        return _public(case, state["period"])


# ---------------------------------------------------------------------------
# Handing a case in
# ---------------------------------------------------------------------------

def _close(conn: Connection, case: dict, state: str, result: dict, submission, now: datetime) -> None:
    conn.execute("UPDATE rank_cases SET state = %s, result = %s, submission = %s, judged_at = %s WHERE id = %s AND state = 'active'",
                 (state, Jsonb(result), Jsonb(submission) if submission is not None else None, now, case["id"]))


def hand_in(conn: Connection, player_id, case_id: int, answers: dict, now: datetime) -> dict:
    """Hand a rank case in: every part at once, once. It is judged on the result and on the working:
    every figure in every part carries marks."""
    with conn.transaction():
        case = _one(conn, "SELECT * FROM rank_cases WHERE id = %s AND player_id = %s FOR UPDATE", (case_id, player_id))
        if case is None:
            raise RankError("There is no such rank case.")
        if case["state"] != "active":
            raise RankError("That rank case has been judged already. It can be handed in once.")
        ctx = o._context(conn, player_id, now)
        if now > case["due_at"] or ctx["period"] > case["period"]:
            _close(conn, case, "not_done", {"score": 0, "pass_mark": case["terms"]["pass_mark"], "parts": [],
                                           "summary": "It was handed in after the time allowed."}, None, now)
            return _public(_one(conn, "SELECT * FROM rank_cases WHERE id = %s", (case_id,)), ctx["period"])
        token = o.SALT.set(case["terms"]["salt"])
        try:
            parts, earned, possible, kept = [], 0, 0, {}
            for part in case["terms"]["parts"]:
                template = o.TEMPLATES[part["template"]]
                fields = {f["key"] for f in part["terms"].get("fields", [])}
                given = answers.get(part["template"]) if isinstance(answers.get(part["template"]), dict) else {}
                given = {k: v for k, v in given.items() if k in fields}
                kept[part["template"]] = given
                paper = {"id": case["id"], "terms": part["terms"], "progress": {}, "player_id": player_id, "submission": None,
                         "period": case["period"], "build": ctx["career"]["build"], "title": part["title"], "module": part["module"]}
                verdict = template.submit(ctx, paper, given)
                points = sum(m["points"] for m in verdict["milestones"])
                got = sum(m["points"] for m in verdict["milestones"] if m["earned"])
                earned, possible = earned + got, possible + points
                parts.append({"template": part["template"], "title": part["title"], "module": part["module"],
                              "score": round(100 * got / points) if points else 0, "summary": verdict["summary"],
                              "milestones": verdict["milestones"], "debrief": verdict["debrief"], "answers": verdict.get("answers")})
        finally:
            o.SALT.reset(token)
        score = 100 * earned // possible if possible else 0
        passed = score >= case["terms"]["pass_mark"]
        result = {"score": score, "pass_mark": case["terms"]["pass_mark"], "parts": parts,
                  "summary": f"{score} marks in the hundred; {case['terms']['pass_mark']} were needed."}
        _close(conn, case, "passed" if passed else "failed", result, kept, now)
        build = ctx["career"]["build"]
        if passed:
            _passed(conn, player_id, case, build, now)
        else:
            careers._event(conn, player_id, build, "rank_case",
                           f"Rank case not passed: {score} marks in the hundred, {case['terms']['pass_mark']} needed. It can be sat again "
                           f"after {data.RANK_CASE_RETRY_DAYS} real days.", now)
        return _public(_one(conn, "SELECT * FROM rank_cases WHERE id = %s", (case_id,)), ctx["period"])


def _passed(conn: Connection, player_id, case: dict, build: str, now: datetime) -> None:
    if case["track"] == "ceo":
        careers._event(conn, player_id, build, "rank_passed", "Passed the CEO rank case.", now)
        ceo_check(conn, player_id, now)
        return
    mine = careers.career(conn, player_id, case["track"], lock=True)
    # A case passes its own gate only: nothing is gained by a case for a gate already passed.
    if careers.level_cap(mine["rank"]) != case["gate"]:
        return
    before = mine["level"]
    conn.execute("UPDATE careers SET rank = rank + 1 WHERE player_id = %s AND build = %s", (player_id, case["track"]))
    after = careers.level_for(mine["experience"], mine["rank"] + 1)
    careers._event(conn, player_id, case["track"], "rank_passed",
                   f"Passed the rank case at Level {case['gate']}: now {careers._a(careers.rank_name(mine['rank'] + 1))} "
                   f"{careers.BUILDS[case['track']]['name']}. Levels up to {careers.level_cap(mine['rank'] + 1)} are open.", now)
    for level in range(before + 1, after + 1):
        careers._event(conn, player_id, case["track"], "level_up", f"Reached Level {level} as {careers._a(careers.BUILDS[case['track']]['name'])}.", now)
    conn.execute("UPDATE players SET reputation = least(reputation + 3, 100) WHERE id = %s", (player_id,))
    ceo_check(conn, player_id, now)


def ceo_check(conn: Connection, player_id, now: datetime) -> bool:
    """Grant the CEO rank the moment all three conditions hold: Level 60, the CEO rank case passed,
    and a reputation of 75 or above. Once earned it is kept."""
    player = _one(conn, "SELECT reputation, ceo_since, build FROM players WHERE id = %s", (player_id,))
    if player is None or player["ceo_since"] is not None or player["build"] is None or player["reputation"] < data.CEO_REPUTATION:
        return False
    mine = careers.career(conn, player_id)
    if mine is None or mine["level"] < data.CEO_LEVEL:
        return False
    if not _one(conn, "SELECT 1 FROM rank_cases WHERE player_id = %s AND track = 'ceo' AND state = 'passed'", (player_id,)):
        return False
    conn.execute("UPDATE players SET ceo_since = %s WHERE id = %s AND ceo_since IS NULL", (now, player_id))
    careers._event(conn, player_id, player["build"], "ceo",
                   "Earned the CEO rank: Level 60, the CEO rank case and a reputation of 75. An empire you lead is led by a CEO, "
                   "not an Acting Head, and any empire founded by players may vote you in.", now)
    seat = _one(conn, "SELECT e.id, e.name FROM empires e WHERE e.head_player_id = %s AND e.kind <> 'pension'", (player_id,))
    if seat:
        conn.execute("INSERT INTO empire_events (empire_id, words, at) VALUES (%s, %s, %s)",
                     (seat["id"], "The Acting Head has earned the CEO rank and now leads the empire as its CEO.", now))
    return True


def at_close(conn: Connection, period: int, now: datetime) -> None:
    """A case still in hand when its quarter closes was not handed in. The fee is not returned."""
    for case in _rows(conn, "SELECT * FROM rank_cases WHERE state = 'active' AND period <= %s ORDER BY id", (period,)):
        with conn.transaction():
            locked = _one(conn, "SELECT * FROM rank_cases WHERE id = %s AND state = 'active' FOR UPDATE", (case["id"],))
            if locked:
                _close(conn, locked, "not_done", {"score": 0, "pass_mark": locked["terms"]["pass_mark"], "parts": [],
                                                 "summary": "The case was not handed in before the quarter ended."}, None, now)


# ---------------------------------------------------------------------------
# Reporting a mark the player believes is wrong
# ---------------------------------------------------------------------------

def report(conn: Connection, player_id, words: str, now: datetime, objective_id: int | None = None, case_id: int | None = None) -> None:
    """A player reports a piece of work, or a rank case, whose marking they believe is wrong. It is
    kept for the people who run the game to look at; nothing changes at once."""
    words = " ".join((words or "").split())
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in words) or not 10 <= len(words) <= 600:
        raise RankError("Say what you believe is wrong, in ten to six hundred characters.")
    with conn.transaction():
        if objective_id is not None:
            row = _one(conn, "SELECT template, state FROM objectives WHERE id = %s AND player_id = %s", (objective_id, player_id))
        else:
            row = _one(conn, "SELECT track AS template, state FROM rank_cases WHERE id = %s AND player_id = %s", (case_id, player_id))
        if row is None or row["state"] == "active":
            raise RankError("Only work that has been judged can be reported.")
        done = conn.execute("INSERT INTO work_reports (player_id, objective_id, rank_case_id, template, words, at) VALUES (%s, %s, %s, %s, %s, %s)"
                            " ON CONFLICT DO NOTHING", (player_id, objective_id, case_id, row["template"], words, now)).rowcount
        if not done:
            raise RankError("You have already reported this.")
