"""The empire as a working firm: the frame every desk works inside.

An empire used to have one task a quarter and a chat. Here each build runs a desk with work
that comes round every quarter, and the desks depend on one another:

  titles         a deputy head, and a lead for each desk
  approvals      one desk must say yes before something happens; a request never waits for ever
  resolutions    what the members vote on, and the empire's own rules that come of it
  duties         each desk's standing work for the quarter, marked by the server, and its scorecard
  documents      papers the Legal Counsel reads before the head signs; some clauses are traps
  opinions       what a member put their name to, checked later against what happened
  the record     what a head did, kept for good

The other parts of the firm (its money, its people, its tasks and events, each desk's duties)
are in the modules named firm_*; each adds itself to the lists at the foot of this one.

Nothing here makes money. Nothing here shows a member what only an audit should find.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from psycopg import Connection, errors
from psycopg.types.json import Jsonb

from simulation import careers, empires, leagues
from simulation import world_data as data
from simulation.empires import (
    BUILD_NAMES,
    EmpireError,
    _log,
    _one,
    _open,
    _roll,
    _rows,
    _text,
)
from simulation.money import BPS

APPROVAL_HOURS = 24                 # a desk has this long; then the request passes to the head
DEPUTY_HOURS = 48                   # ...and after this long to the deputy as well
LAPSE_HOURS = 72                    # a request nobody at all has decided by now is dropped
OVERRULE_HOURS = 48                 # how long after a refusal the head may still overrule it
VOTE_HOURS = 48                     # how long a vote stays open
STAFF_DUTY_SCORE = 70               # computer-run staff do a duty reliably, and no better than this
STAFF_CATCHES_BPS = 7000            # the staff's chance of catching each trap in a paper
DUTY_PASS = 60                      # a duty done at this score or better was done well
DUTY_EXPERIENCE = 50                # what a duty done perfectly teaches, before rank
OVERRULE_DESKS = ("risk_manager", "lawyer")
REASON_KINDS = ("trade", "bond_trade", "deal", "legal", "venture")       # a yes to these needs a written reason, as a no always does
LEAGUE = {"duty_missed": -1, "well_run": 3}
DESKS = (*data.EMPIRE_BUILDS, "head")
DESK_NAMES = {**BUILD_NAMES, "head": "Head of the empire"}
# How each desk is headed on the screen. The Financial Journalist's place in an empire is its Intelligence desk.
DESK_LABELS = {**DESK_NAMES, "journalist": "Intelligence desk (Financial Journalist)"}


def _json(value):
    return Jsonb(value)


def _hours(since: datetime, now: datetime) -> float:
    return (now - since).total_seconds() / 3600


def player_run(empire: dict) -> bool:
    return empire["head_player_id"] is not None


def _active(conn: Connection, player_id, *, lock: bool = False) -> tuple[dict, dict]:
    """The seat a player holds in an open empire, and that empire."""
    seat = empires.seat_of(conn, player_id, lock=lock)
    if seat is None or seat["empire_status"] != "active" or seat["empire_kind"] == "pension":
        raise EmpireError("You hold no seat in an open empire.")
    return seat, empires._empire(conn, seat["empire_id"])


def _name(conn: Connection, player_id) -> str:
    row = _one(conn, "SELECT display_name FROM players WHERE id = %s", (player_id,)) if player_id else None
    return row["display_name"] if row else "The staff"


def _whole(value, least: int = 0, most: int | None = None) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= least and (most is None or value <= most)


# ---------------------------------------------------------------------------
# Who sits where
# ---------------------------------------------------------------------------

def seat_holder(conn: Connection, seat_id) -> dict:
    """The player in a seat, and the seat. The website names colleagues by their seat, never by their player number."""
    if not _whole(seat_id, 1):
        raise EmpireError("There is nobody in that seat.")
    row = _one(conn, "SELECT s.*, p.display_name FROM empire_seats s JOIN players p ON p.id = s.player_id WHERE s.id = %s", (seat_id,))
    if row is None:
        raise EmpireError("There is nobody in that seat.")
    return row


def roster(conn: Connection, empire_id, me) -> list[dict]:
    """Who sits at each desk, by seat: what every member of the empire sees."""
    return [{"seat_id": r["id"], "name": r["display_name"], "build": r["build"], "build_name": BUILD_NAMES[r["build"]], "you": r["player_id"] == me,
             "is_head": r["is_head"]}
            for r in _rows(conn, "SELECT s.id, s.build, s.player_id, p.display_name, (e.head_player_id = s.player_id) AS is_head FROM empire_seats s"
                                 " JOIN players p ON p.id = s.player_id JOIN empires e ON e.id = s.empire_id WHERE s.empire_id = %s"
                                 " ORDER BY s.build, s.slot", (empire_id,))]


def seats_view(conn: Connection, empire: dict, me) -> list[dict]:
    """Every seat in the empire, held or empty: two for each build, and those a headquarters adds (Stage 8),
    frozen while the headquarters is down."""
    return [{"build": r["build"], "build_name": BUILD_NAMES[r["build"]], "slot": r["slot"], "held": r["player_id"] is not None,
             "name": r["display_name"], "you": r["player_id"] == me, "is_head": r["player_id"] is not None and r["player_id"] == empire["head_player_id"],
             "from_headquarters": r["slot"] >= 3, "frozen": r["hq_frozen"]}
            for r in _rows(conn, "SELECT s.build, s.slot, s.player_id, s.hq_frozen, p.display_name FROM empire_seats s LEFT JOIN players p"
                                 " ON p.id = s.player_id WHERE s.empire_id = %s ORDER BY s.slot, s.build", (empire["id"],))]


def desk_members(conn: Connection, empire_id, build: str) -> list:
    """The players on a desk. The head's desk is the head alone."""
    if build == "head":
        head = _one(conn, "SELECT head_player_id FROM empires WHERE id = %s", (empire_id,))["head_player_id"]
        return [head] if head else []
    return [r["player_id"] for r in _rows(conn, "SELECT player_id FROM empire_seats WHERE empire_id = %s AND build = %s AND player_id IS NOT NULL"
                                                " ORDER BY slot", (empire_id, build))]


def desk_staffed(conn: Connection, empire_id, build: str) -> bool:
    """Whether computer-run staff work on a desk. A computer-run empire's head is its staff."""
    if build == "head":
        return _one(conn, "SELECT head_player_id FROM empires WHERE id = %s", (empire_id,))["head_player_id"] is None
    return bool(_one(conn, "SELECT 1 FROM empire_seats WHERE empire_id = %s AND build = %s AND player_id IS NULL AND staffed", (empire_id, build)))


def deputy_of(conn: Connection, empire_id):
    row = _one(conn, "SELECT t.player_id FROM empire_titles t JOIN empire_seats s ON s.player_id = t.player_id AND s.empire_id = t.empire_id"
                     " WHERE t.empire_id = %s AND t.title = 'deputy'", (empire_id,))
    return row["player_id"] if row else None


def lead_of(conn: Connection, empire_id, build: str):
    """The lead of a desk: whoever the head named, or else its senior member."""
    row = _one(conn, "SELECT t.player_id FROM empire_titles t JOIN empire_seats s ON s.player_id = t.player_id AND s.empire_id = t.empire_id"
                     " AND s.build = t.build WHERE t.empire_id = %s AND t.title = 'lead' AND t.build = %s", (empire_id, build))
    if row:
        return row["player_id"]
    held = [h for h in empires.humans(conn, empire_id) if h["build"] == build]
    return max(held, key=lambda h: (careers.level_for(h["experience"] or 0, h["rank"] or 0), -h["slot"]))["player_id"] if held else None


def name_title(conn: Connection, head_id, member_id, title: str, now: datetime) -> None:
    """The head names a deputy, or the lead of a desk. A deputy decides what waits too long for the
    head, and becomes Acting Head if the head goes. A lead shares out the desk's duties."""
    with conn.transaction():
        state = _open(conn, now)
        empire = empires._head(conn, head_id)
        seat = empires.seat_of(conn, member_id)
        if seat is None or seat["empire_id"] != empire["id"]:
            raise EmpireError("They are not a member of your empire.")
        if title == "deputy":
            if member_id == head_id:
                raise EmpireError("The head cannot be their own deputy.")
            build = ""
        elif title == "lead":
            build = seat["build"]
        else:
            raise EmpireError("There is no such title.")
        conn.execute("INSERT INTO empire_titles (empire_id, title, build, player_id, since) VALUES (%s, %s, %s, %s, %s)"
                     " ON CONFLICT (empire_id, title, build) DO UPDATE SET player_id = excluded.player_id, since = excluded.since",
                     (empire["id"], title, build, member_id, now))
        what = "deputy head" if title == "deputy" else f"lead of the {BUILD_NAMES[build]} desk"
        _log(conn, empire["id"], f"{_name(conn, member_id)} was named {what}.", now)
        careers._event(conn, member_id, seat["build"], "promoted", f"Named {what} of {empire['name']}.", now)
        for hook in PROMOTED:
            hook(conn, empire, member_id, title, state, now)


def on_vacate(conn: Connection, seat: dict, now: datetime) -> None:
    """A member has left their seat: their titles go with them, and what they had in hand goes back."""
    conn.execute("DELETE FROM empire_titles WHERE empire_id = %s AND player_id = %s", (seat["empire_id"], seat["player_id"]))
    conn.execute("UPDATE desk_duties SET assigned_to = NULL WHERE empire_id = %s AND assigned_to = %s AND status = 'due'",
                 (seat["empire_id"], seat["player_id"]))
    conn.execute("DELETE FROM empire_resolution_votes v USING empire_resolutions r WHERE r.id = v.resolution_id AND r.empire_id = %s"
                 " AND r.status = 'open' AND v.player_id = %s", (seat["empire_id"], seat["player_id"]))
    conn.execute("UPDATE empire_seats SET frozen = false WHERE id = %s", (seat["id"],))
    for hook in VACATED:
        hook(conn, seat, now)


def successor(conn: Connection, empire_id, leaving_id):
    """Who leads when the head goes: the deputy, if there is one who may."""
    deputy = deputy_of(conn, empire_id)
    if deputy and deputy != leaving_id and not _one(conn, "SELECT 1 FROM empire_cases WHERE empire_id = %s AND player_id = %s AND status = 'open'",
                                                    (empire_id, deputy)):
        return deputy
    return None


# ---------------------------------------------------------------------------
# Approvals: one desk must say yes, and nothing waits for ever
# ---------------------------------------------------------------------------
EXECUTORS: dict[str, Callable] = {}        # kind -> (conn, approval, now) -> None : carry out what was approved
REFUSERS: dict[str, Callable] = {}         # kind -> (conn, approval, now) -> None : tidy up after a refusal
STAFF_RULES: dict[str, Callable] = {}      # kind -> (conn, approval, now) -> (yes, reason) : how the staff decide
VIEWERS: dict[str, Callable] = {}          # kind -> (conn, approval, viewer_id, now) -> dict : what a decider is shown
OVERRULE_SETTLERS: dict[str, Callable] = {}   # kind -> (conn, approval, period) -> True/False/None : did the overrule turn out well?


def ask(conn: Connection, empire: dict, *, kind: str, desk: str, asked_by, title: str, amount: int = 0, payload: dict | None = None,
        period: int, now: datetime) -> dict:
    """Put a request in front of a desk. Called inside the asker's own transaction."""
    return _one(conn, "INSERT INTO empire_approvals (empire_id, kind, desk, asked_by, title, amount, payload, period, asked_at)"
                      " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING *",
                (empire["id"], kind, desk, asked_by, title[:200], amount, _json(payload or {}), period, now))


def concerned(approval: dict) -> set:
    """Everybody a request is about: whoever asked, and whoever it would pay or name. None of them decides it."""
    p = approval.get("payload") or {}
    out = {str(approval["asked_by"])} if approval.get("asked_by") else set()
    out |= {str(k) for k in (p.get("shares") or {})}
    for key in ("member_id", "subject_id"):
        if p.get(key):
            out.add(str(p[key]))
    return out


def deciders(conn: Connection, approval: dict, now: datetime) -> dict:
    """Who may decide a request at this moment, and in what capacity. Nobody decides their own, or one that pays them.

    The desk's own members may decide it at any time. Once the desk has had its day, or when the
    desk has nobody who may, the head may. After two days the deputy may as well."""
    empire = empires._empire(conn, approval["empire_id"])
    barred, waited = concerned(approval), _hours(approval["asked_at"], now)
    who: dict = {}
    if approval["desk"] != "head":
        for member in desk_members(conn, empire["id"], approval["desk"]):
            if str(member) not in barred:
                who[member] = "desk"
    head, deputy = empire["head_player_id"], deputy_of(conn, empire["id"])
    staff_will = approval["desk"] != "head" and desk_staffed(conn, empire["id"], approval["desk"])
    head_turn = approval["desk"] == "head" or waited >= APPROVAL_HOURS or (not who and not staff_will)
    head_may = head is not None and str(head) not in barred
    if head_may and head_turn:
        who.setdefault(head, "head")
    if deputy and str(deputy) not in barred and (waited >= DEPUTY_HOURS or (head_turn and not head_may)):
        who.setdefault(deputy, "deputy")
    return who


def _approval(conn: Connection, approval_id: int, empire_id) -> dict:
    approval = _one(conn, "SELECT * FROM empire_approvals WHERE id = %s AND empire_id = %s FOR UPDATE", (approval_id, empire_id))
    if approval is None:
        raise EmpireError("There is no such request in your empire.")
    return approval


def _carry_out(conn: Connection, approval: dict, now: datetime) -> None:
    executor = EXECUTORS.get(approval["kind"])
    if executor:
        executor(conn, approval, now)


def decide(conn: Connection, player_id, approval_id: int, approve: bool, reason: str, now: datetime) -> dict:
    """Say yes or no to a request that has come to you. A no always carries a written reason; so
    does a yes to a trade, a deal, a paper or a new venture. What is approved is carried out at once."""
    with conn.transaction():
        _open(conn, now)
        seat, empire = _active(conn, player_id)
        conn.execute("SELECT 1 FROM empires WHERE id = %s FOR UPDATE", (empire["id"],))
        approval = _approval(conn, approval_id, empire["id"])
        if approval["status"] != "waiting":
            raise EmpireError("That request has already been decided.")
        role = deciders(conn, approval, now).get(player_id)
        if role is None:
            raise EmpireError("Nobody decides their own request, or one that pays them." if str(player_id) in concerned(approval)
                              else "That request is not yours to decide.")
        reason = _text(reason or "")[:400]
        if not reason and (not approve or approval["kind"] in REASON_KINDS):
            raise EmpireError("Give your reason in writing. It is kept on the record.")
        if approve:
            _carry_out(conn, approval, now)
        elif approval["kind"] in REFUSERS:
            REFUSERS[approval["kind"]](conn, approval, now)
        conn.execute("UPDATE empire_approvals SET status = %s, reason = %s, decided_by = %s, decided_as = %s, decided_at = %s WHERE id = %s",
                     ("approved" if approve else "refused", reason or None, player_id, role, now, approval_id))
        for hook in DECIDED:
            hook(conn, {**approval, "status": "approved" if approve else "refused", "reason": reason, "decided_by": player_id,
                        "decided_as": role}, seat, now)
        return {"approved": approve, "as": role}


def overrule(conn: Connection, head_id, approval_id: int, reason: str, now: datetime) -> None:
    """The head overrules the Risk Manager's or the Legal Counsel's refusal. It is carried out, and it goes
    on the head's record for good: if it turns out badly, it counts against the head, not the desk."""
    with conn.transaction():
        state = _open(conn, now)
        empire = empires._head(conn, head_id)
        approval = _approval(conn, approval_id, empire["id"])
        if approval["status"] != "refused" or approval["desk"] not in OVERRULE_DESKS or approval["decided_as"] not in ("desk", "staff"):
            raise EmpireError("Only a refusal by the Risk Manager's or the Legal Counsel's desk can be overruled.")
        if _hours(approval["decided_at"], now) > OVERRULE_HOURS:
            raise EmpireError("That refusal has stood for two days. It is too late to overrule it; ask again.")
        reason = _text(reason or "")[:400]
        if not reason:
            raise EmpireError("Give your reason in writing. An overrule is kept on your record for good.")
        _carry_out(conn, approval, now)
        conn.execute("UPDATE empire_approvals SET status = 'overruled', overruled_by = %s, overruled_at = %s, overrule_reason = %s WHERE id = %s",
                     (head_id, now, reason, approval_id))
        desk = DESK_NAMES[approval["desk"]]
        ceo_note(conn, head_id, empire["id"], "overrule", f"Overruled the {desk}'s refusal of: {approval['title']}. The {desk} had written: "
                                                        f"\"{(approval['reason'] or '')[:200]}\"", state["period"], now,
                 reference=f"approval:{approval_id}")
        _log(conn, empire["id"], f"The head overruled the {desk}'s desk: {approval['title']}.", now)


def _staff_decisions(conn: Connection, now: datetime) -> None:
    """At each Closing Bell: the staff decide what falls to them, and what nobody has decided is dropped."""
    for waiting in _rows(conn, "SELECT a.id FROM empire_approvals a JOIN empires e ON e.id = a.empire_id WHERE a.status = 'waiting'"
                               " AND e.status = 'active' ORDER BY a.id"):
        with conn.transaction():
            approval = _one(conn, "SELECT * FROM empire_approvals WHERE id = %s AND status = 'waiting' FOR UPDATE", (waiting["id"],))
            if approval is None:
                continue
            waited = _hours(approval["asked_at"], now)
            humans = deciders(conn, approval, now)
            desk_humans = [p for p, role in humans.items() if role == "desk"]
            staff = desk_staffed(conn, approval["empire_id"], approval["desk"])
            if staff and (not desk_humans or waited >= APPROVAL_HOURS) and not (approval["desk"] == "head" and humans):
                rule = STAFF_RULES.get(approval["kind"])
                yes, reason = rule(conn, approval, now) if rule else (True, "Within the empire's rules.")
                if yes:
                    try:
                        with conn.transaction():
                            _carry_out(conn, approval, now)
                    except EmpireError as refused:
                        yes, reason = False, str(refused)
                if not yes and approval["kind"] in REFUSERS:
                    REFUSERS[approval["kind"]](conn, approval, now)
                conn.execute("UPDATE empire_approvals SET status = %s, reason = %s, decided_as = 'staff', decided_at = %s WHERE id = %s",
                             ("approved" if yes else "refused", reason[:400], now, approval["id"]))
            elif waited >= LAPSE_HOURS:
                if approval["kind"] in REFUSERS:
                    REFUSERS[approval["kind"]](conn, approval, now)
                conn.execute("UPDATE empire_approvals SET status = 'lapsed', reason = 'Nobody decided it in three days.', decided_at = %s"
                             " WHERE id = %s", (now, approval["id"]))


def _approval_public(conn: Connection, approval: dict, viewer_id, now: datetime, may: dict | None = None) -> dict:
    out = {"id": approval["id"], "kind": approval["kind"], "desk": approval["desk"], "desk_name": DESK_NAMES.get(approval["desk"], approval["desk"]),
           "title": approval["title"], "amount": approval["amount"], "status": approval["status"], "reason": approval["reason"],
           "asked_by": _name(conn, approval["asked_by"]) if approval["asked_by"] else "The empire", "yours": approval["asked_by"] == viewer_id,
           "asked_at": approval["asked_at"], "decided_at": approval["decided_at"], "decided_as": approval["decided_as"],
           "passes_to_head_at": approval["asked_at"] + timedelta(hours=APPROVAL_HOURS),
           "lapses_at": approval["asked_at"] + timedelta(hours=LAPSE_HOURS), "overrule_reason": approval["overrule_reason"],
           "needs_reason": approval["kind"] in REASON_KINDS}
    if may is not None:
        out["you_decide_as"] = may.get(viewer_id)
    viewer = VIEWERS.get(approval["kind"])
    out["detail"] = viewer(conn, approval, viewer_id, now) if viewer else {}
    return out


def approvals_view(conn: Connection, seat: dict, empire: dict, now: datetime) -> dict:
    """What a member sees of the empire's requests: those they may decide now, their own, and (for
    the head) refusals that may still be overruled. A request is shown to nobody else."""
    me, is_head = seat["player_id"], empire["head_player_id"] == seat["player_id"]
    yours, asked, overrulable = [], [], []
    for approval in _rows(conn, "SELECT * FROM empire_approvals WHERE empire_id = %s AND (status = 'waiting' OR decided_at > %s)"
                                " ORDER BY id DESC LIMIT 200", (empire["id"], now - timedelta(days=7))):
        if approval["status"] == "waiting":
            may = deciders(conn, approval, now)
            if me in may:
                yours.append(_approval_public(conn, approval, me, now, may))
                continue
        if approval["asked_by"] == me:
            asked.append(_approval_public(conn, approval, me, now))
        elif (is_head and approval["status"] == "refused" and approval["desk"] in OVERRULE_DESKS
              and approval["decided_as"] in ("desk", "staff") and _hours(approval["decided_at"], now) <= OVERRULE_HOURS):
            overrulable.append(_approval_public(conn, approval, me, now))
    return {"to_decide": yours, "asked": asked[:20], "can_overrule": overrulable, "hours": APPROVAL_HOURS}


# ---------------------------------------------------------------------------
# Resolutions: what the members vote on
# ---------------------------------------------------------------------------
@dataclass
class Resolution:
    kind: str
    name: str
    who: Callable                      # (seat, is_head) -> may this member propose it?
    check: Callable                    # (conn, empire, payload, now) -> the payload, made safe; raises EmpireError
    carry: Callable                    # (conn, empire, resolution, now) -> words about what was done
    words: Callable                    # (payload) -> one plain line saying what is proposed
    big: bool = False                  # needs two-thirds when the empire's rules say big items do


RESOLUTIONS: dict[str, Resolution] = {}
FAILED: dict[str, Callable] = {}           # kind -> (conn, resolution, now) : what follows when a vote fails


def propose(conn: Connection, player_id, kind: str, payload: dict, now: datetime) -> dict:
    """Put something to the members' vote. Only an empire led by a player votes: an empire the
    computer runs keeps to its published rules."""
    with conn.transaction():
        state = _open(conn, now)
        seat, empire = _active(conn, player_id)
        if not player_run(empire):
            raise EmpireError("An empire run by the computer keeps to its published rules. Its members do not vote on them.")
        rule = RESOLUTIONS.get(kind)
        if rule is None:
            raise EmpireError("There is nothing of that kind to vote on.")
        if not rule.who(seat, empire["head_player_id"] == player_id):
            raise EmpireError("That is not yours to propose.")
        payload = rule.check(conn, empire, dict(payload or {}), now)
        try:
            with conn.transaction():
                resolution = _one(conn, "INSERT INTO empire_resolutions (empire_id, kind, title, payload, proposed_by, period, opened_at, closes_at)"
                                        " VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING *",
                                  (empire["id"], kind, rule.words(payload)[:200], _json(payload), player_id, state["period"], now,
                                   now + timedelta(hours=VOTE_HOURS)))
        except errors.UniqueViolation:
            raise EmpireError("A vote of that kind is already open. Let it finish first.") from None
        conn.execute("INSERT INTO empire_resolution_votes (resolution_id, player_id, yes, at) VALUES (%s, %s, true, %s)",
                     (resolution["id"], player_id, now))
        _log(conn, empire["id"], f"{_name(conn, player_id)} put to the vote: {resolution['title']}", now)
        _count(conn, resolution, now)
        return resolution


def call_vote(conn: Connection, empire: dict, kind: str, title: str, payload: dict, period: int, now: datetime) -> dict | None:
    """A vote the rules themselves call (the yearly vote of confidence, for one)."""
    if not player_run(empire) or _one(conn, "SELECT 1 FROM empire_resolutions WHERE empire_id = %s AND kind = %s AND status = 'open'",
                                      (empire["id"], kind)):
        return None
    resolution = _one(conn, "INSERT INTO empire_resolutions (empire_id, kind, title, payload, period, opened_at, closes_at)"
                            " VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING *",
                      (empire["id"], kind, title[:200], _json(payload), period, now, now + timedelta(hours=VOTE_HOURS)))
    _log(conn, empire["id"], f"A vote was called: {title}", now)
    return resolution


def vote(conn: Connection, player_id, resolution_id: int, yes: bool, now: datetime) -> dict:
    with conn.transaction():
        _open(conn, now)
        seat, empire = _active(conn, player_id)
        conn.execute("SELECT 1 FROM empires WHERE id = %s FOR UPDATE", (empire["id"],))
        resolution = _one(conn, "SELECT * FROM empire_resolutions WHERE id = %s AND empire_id = %s FOR UPDATE", (resolution_id, empire["id"]))
        if resolution is None or resolution["status"] != "open":
            raise EmpireError("There is no such vote open in your empire.")
        subject = resolution["payload"].get("subject_id")
        if subject and str(subject) == str(player_id):
            raise EmpireError("You do not vote on a question about yourself.")
        conn.execute("INSERT INTO empire_resolution_votes (resolution_id, player_id, yes, at) VALUES (%s, %s, %s, %s)"
                     " ON CONFLICT (resolution_id, player_id) DO UPDATE SET yes = excluded.yes, at = excluded.at",
                     (resolution_id, player_id, bool(yes), now))
        return {"status": _count(conn, resolution, now)}


def withdraw(conn: Connection, player_id, resolution_id: int, now: datetime) -> None:
    with conn.transaction():
        _open(conn, now)
        done = conn.execute("UPDATE empire_resolutions SET status = 'withdrawn', decided_at = %s WHERE id = %s AND proposed_by = %s"
                            " AND status = 'open'", (now, resolution_id, player_id)).rowcount
        if not done:
            raise EmpireError("There is no vote of yours open to withdraw.")


def _voters(conn: Connection, resolution: dict) -> list:
    subject = resolution["payload"].get("subject_id")
    return [h["player_id"] for h in empires.humans(conn, resolution["empire_id"]) if str(h["player_id"]) != str(subject)]


def _count(conn: Connection, resolution: dict, now: datetime, final: bool = False) -> str:
    """Count a vote. It passes as soon as enough members have said yes, and fails as soon as that
    cannot happen. When its time is up, more yes than no carries it; on a tie the head's vote decides."""
    empire = empires._empire(conn, resolution["empire_id"])
    voters = _voters(conn, resolution)
    cast = {r["player_id"]: r["yes"] for r in _rows(conn, "SELECT player_id, yes FROM empire_resolution_votes WHERE resolution_id = %s",
                                                    (resolution["id"],)) if r["player_id"] in voters}
    yes, no = sum(1 for v in cast.values() if v), sum(1 for v in cast.values() if not v)
    rule = RESOLUTIONS.get(resolution["kind"])
    two_thirds = bool(rule and rule.big and article(conn, empire["id"], "big_votes") == "two_thirds")
    needed = (len(voters) * 2 + 2) // 3 if two_thirds else len(voters) // 2 + 1
    passed = None
    if voters and yes >= needed:
        passed = True
    elif not voters or no > len(voters) - needed:
        passed = False
    elif final:
        if resolution["kind"] == "confidence":
            passed = yes >= no                 # a head keeps the members' confidence unless more say no than yes: silence is not a vote against
        elif two_thirds:
            passed = yes * 3 >= (yes + no) * 2 and yes > 0
        elif yes != no:
            passed = yes > no
        else:
            passed = bool(cast.get(empire["head_player_id"], False)) and yes > 0
    if passed is None:
        return "open"
    outcome = "Not enough of the members were for it."
    if passed and rule:
        try:
            with conn.transaction():
                outcome = rule.carry(conn, empire, resolution, now) or "Carried."
        except EmpireError as refused:
            passed, outcome = False, f"It was voted through, but could not be carried out: {refused}"
    conn.execute("UPDATE empire_resolutions SET status = %s, decided_at = %s, outcome = %s WHERE id = %s",
                 ("passed" if passed else "failed", now, outcome[:400], resolution["id"]))
    if not passed and resolution["kind"] in FAILED:
        FAILED[resolution["kind"]](conn, resolution, now)
    _log(conn, empire["id"], f"The vote on \"{resolution['title']}\" {'passed' if passed else 'failed'}: {yes} for, {no} against. {outcome}", now)
    return "passed" if passed else "failed"


def _count_due(conn: Connection, now: datetime) -> None:
    for due in _rows(conn, "SELECT id FROM empire_resolutions WHERE status = 'open' AND closes_at <= %s ORDER BY id", (now,)):
        with conn.transaction():
            resolution = _one(conn, "SELECT * FROM empire_resolutions WHERE id = %s AND status = 'open' FOR UPDATE", (due["id"],))
            if resolution:
                _count(conn, resolution, now, final=True)


def resolutions_view(conn: Connection, seat: dict, empire: dict, now: datetime) -> dict:
    is_head = empire["head_player_id"] == seat["player_id"]
    rows = _rows(conn, "SELECT r.*, p.display_name AS proposer FROM empire_resolutions r LEFT JOIN players p ON p.id = r.proposed_by"
                       " WHERE r.empire_id = %s ORDER BY (r.status = 'open') DESC, r.id DESC LIMIT 20", (empire["id"],))
    out = []
    for r in rows:
        votes = _rows(conn, "SELECT player_id, yes FROM empire_resolution_votes WHERE resolution_id = %s", (r["id"],))
        mine = next((v["yes"] for v in votes if v["player_id"] == seat["player_id"]), None)
        out.append({"id": r["id"], "kind": r["kind"], "kind_name": RESOLUTIONS[r["kind"]].name if r["kind"] in RESOLUTIONS else r["kind"],
                    "title": r["title"], "status": r["status"], "proposer": r["proposer"] or "The empire's rules",
                    "yours": r["proposed_by"] == seat["player_id"], "opened_at": r["opened_at"], "closes_at": r["closes_at"],
                    "for": sum(1 for v in votes if v["yes"]), "against": sum(1 for v in votes if not v["yes"]),
                    "voters": len(_voters(conn, r)) if r["status"] == "open" else None, "your_vote": mine, "outcome": r["outcome"],
                    "about_you": str(r["payload"].get("subject_id")) == str(seat["player_id"])})
    return {"votes": out, "open": player_run(empire),
            "can_propose": [{"kind": k, "name": rule.name} for k, rule in RESOLUTIONS.items() if player_run(empire) and rule.who(seat, is_head)]}


# ---------------------------------------------------------------------------
# Articles: the empire's own rules
# ---------------------------------------------------------------------------
ARTICLE_DEFAULTS: dict[str, object] = {
    "big_votes": "majority",                     # 'majority' or 'two_thirds', for the big items
}


def article(conn: Connection, empire_id, key: str):
    """The rule in force in an empire: what its members last voted, or else the usual rule."""
    row = _one(conn, "SELECT value FROM empire_articles WHERE empire_id = %s AND key = %s ORDER BY id DESC LIMIT 1", (empire_id, key))
    return row["value"] if row else ARTICLE_DEFAULTS.get(key)


def set_article(conn: Connection, empire_id, key: str, value, period: int, now: datetime, resolution_id=None) -> None:
    conn.execute("INSERT INTO empire_articles (empire_id, key, value, resolution_id, period, at) VALUES (%s, %s, %s, %s, %s, %s)",
                 (empire_id, key, _json(value), resolution_id, period, now))


def articles_of(conn: Connection, empire_id) -> dict:
    return {key: article(conn, empire_id, key) for key in ARTICLE_DEFAULTS}


# ---------------------------------------------------------------------------
# Duties: each desk's standing work, every quarter
# ---------------------------------------------------------------------------
@dataclass
class Duty:
    code: str
    build: str                         # the desk it falls to: a build, or 'head'
    title: str
    why: str                           # one plain sentence: why the empire needs it
    prepare: Callable                  # (ctx) -> terms {brief, given: [...], asks: [...], _truth: {...}} or None if it does not arise
    mark: Callable                     # (ctx, terms, answers) -> {score, lines: [...], words}
    after: Callable | None = None      # (ctx, duty, result) : what follows from its being done by a player
    staff: Callable | None = None      # (ctx, duty) : what follows from the staff doing it
    applies: Callable | None = None    # (conn, empire, period) -> bool
    player_run_only: bool = False


DUTIES: dict[str, Duty] = {}


def duty_ctx(conn: Connection, empire: dict, period: int, now: datetime, player_id=None) -> dict:
    return {"conn": conn, "empire": empire, "period": period, "now": now, "player_id": player_id}


def ensure_duties(conn: Connection, empire: dict, period: int) -> None:
    """Set out the quarter's duties for every desk of an empire, once."""
    for duty in DUTIES.values():
        if duty.player_run_only and not player_run(empire):
            continue
        if duty.applies and not duty.applies(conn, empire, period):
            continue
        conn.execute("INSERT INTO desk_duties (empire_id, build, period, code) VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING",
                     (empire["id"], duty.build, period, duty.code))


def _public_terms(terms: dict | None) -> dict | None:
    return None if terms is None else {k: v for k, v in terms.items() if not k.startswith("_")}


def _duty_for(conn: Connection, player_id, duty_id: int) -> tuple[dict, dict, dict]:
    seat, empire = _active(conn, player_id)
    duty = _one(conn, "SELECT * FROM desk_duties WHERE id = %s AND empire_id = %s FOR UPDATE", (duty_id, empire["id"]))
    if duty is None or duty["code"] not in DUTIES:
        raise EmpireError("There is no such duty in your empire.")
    mine = "head" if duty["build"] == "head" else seat["build"]
    if duty["build"] != mine or (duty["build"] == "head" and empire["head_player_id"] != player_id):
        raise EmpireError(f"That duty falls to the {DESK_NAMES[duty['build']]}'s desk.")
    return seat, empire, duty


def open_duty(conn: Connection, player_id, duty_id: int, now: datetime) -> dict:
    """Open one of your desk's duties. What it asks is fixed from the figures of this moment, and
    whoever opens it is the one who does it."""
    with conn.transaction():
        state = _open(conn, now)
        seat, empire, duty = _duty_for(conn, player_id, duty_id)
        if duty["status"] != "due":
            raise EmpireError("That duty is no longer waiting.")
        if duty["period"] != state["period"]:
            raise EmpireError("That duty belonged to a quarter that has closed.")
        if duty["assigned_to"] not in (None, player_id):
            raise EmpireError(f"That duty has been given to {_name(conn, duty['assigned_to'])}.")
        if duty["terms"] is None:
            terms = DUTIES[duty["code"]].prepare(duty_ctx(conn, empire, state["period"], now, player_id))
            if terms is None:
                raise EmpireError("There is nothing to do on that duty at this moment. Look again later in the quarter.")
            conn.execute("UPDATE desk_duties SET terms = %s, assigned_to = %s WHERE id = %s", (_json(terms), player_id, duty_id))
            duty = {**duty, "terms": terms}
        elif duty["assigned_to"] is None:
            # Whoever opened it has left the desk: a colleague picks it up, as it was set.
            conn.execute("UPDATE desk_duties SET assigned_to = %s WHERE id = %s", (player_id, duty_id))
        return {"id": duty_id, "code": duty["code"], "title": DUTIES[duty["code"]].title, "terms": _public_terms(duty["terms"])}


def hand_in(conn: Connection, player_id, duty_id: int, answers: dict, now: datetime) -> dict:
    """Hand in a duty. It is marked by the server against the empire's own figures, once."""
    with conn.transaction():
        state = _open(conn, now)
        seat, empire, duty = _duty_for(conn, player_id, duty_id)
        if duty["status"] != "due" or duty["terms"] is None or duty["assigned_to"] != player_id:
            raise EmpireError("Open the duty first. It can be handed in once, by whoever opened it.")
        if duty["period"] != state["period"]:
            raise EmpireError("That duty belonged to a quarter that has closed.")
        if not isinstance(answers, dict):
            raise EmpireError("The answers did not arrive in a form that can be read.")
        rule = DUTIES[duty["code"]]
        ctx = duty_ctx(conn, empire, state["period"], now, player_id)
        result = rule.mark(ctx, duty["terms"], answers)
        score = max(0, min(100, int(result["score"])))
        conn.execute("UPDATE desk_duties SET status = 'done', score = %s, done_by = %s, answers = %s, result = %s, done_at = %s WHERE id = %s",
                     (score, player_id, _json(answers), _json(result), now, duty_id))
        mine = careers.career(conn, player_id, seat["build"])
        gained = DUTY_EXPERIENCE * score // 100 * (1 + (mine["rank"] if mine else 0))
        from simulation import (
            headquarters,  # a fine headquarters teaches more (Stage 8)
        )
        gained = gained * (BPS + headquarters.bonus_bps(conn, empire["id"])) // BPS
        if gained and mine:
            careers.add_experience(conn, player_id, seat["build"], gained, now)
        done = {**duty, "status": "done", "score": score, "done_by": player_id, "answers": answers, "result": result}
        if rule.after:
            rule.after(ctx, done, result)
        for hook in DUTY_DONE:
            hook(conn, empire, done, seat, gained, now)
        _log(conn, empire["id"], f"{_name(conn, player_id)} did the {DESK_NAMES[duty['build']]} desk's duty: {rule.title.lower()} "
                                 f"(marked {score} out of 100).", now)
        return {"score": score, "experience": gained, "result": result, "well_done": score >= DUTY_PASS}


def assign_duty(conn: Connection, player_id, duty_id: int, member_id, now: datetime) -> None:
    """The head, or the lead of a desk, gives a duty to one member of that desk (or takes it back)."""
    with conn.transaction():
        _open(conn, now)
        seat, empire = _active(conn, player_id)
        duty = _one(conn, "SELECT * FROM desk_duties WHERE id = %s AND empire_id = %s FOR UPDATE", (duty_id, empire["id"]))
        if duty is None or duty["status"] != "due" or duty["terms"] is not None:
            raise EmpireError("That duty cannot be given out: it is done, or already opened.")
        if empire["head_player_id"] != player_id and lead_of(conn, empire["id"], duty["build"]) != player_id:
            raise EmpireError("Only the head, or the lead of that desk, gives out its duties.")
        if member_id is not None and member_id not in desk_members(conn, empire["id"], duty["build"]):
            raise EmpireError("They are not on that desk.")
        conn.execute("UPDATE desk_duties SET assigned_to = %s WHERE id = %s", (member_id, duty_id))


def _close_duties(conn: Connection, empire: dict, period: int, now: datetime) -> None:
    """As a quarter closes: the staff do what no player did, where there are staff; the rest is
    missed. Then each desk's scorecard is written down for good."""
    cards: dict[str, dict] = {}
    for duty in _rows(conn, "SELECT * FROM desk_duties WHERE empire_id = %s AND period = %s ORDER BY id FOR UPDATE", (empire["id"], period)):
        rule = DUTIES.get(duty["code"])
        if duty["status"] == "due" and duty["terms"] is None and rule and rule.prepare(duty_ctx(conn, empire, period, now)) is None:
            conn.execute("DELETE FROM desk_duties WHERE id = %s", (duty["id"],))      # it never arose this quarter
            continue
        card = cards.setdefault(duty["build"], {"duties": 0, "done": 0, "by_staff": 0, "missed": 0, "total": 0, "notes": []})
        if duty["status"] == "due":
            humans = desk_members(conn, empire["id"], duty["build"])
            if rule and desk_staffed(conn, empire["id"], duty["build"]):
                conn.execute("UPDATE desk_duties SET status = 'done', score = %s, by_staff = true, done_at = %s WHERE id = %s",
                             (STAFF_DUTY_SCORE, now, duty["id"]))
                duty = {**duty, "status": "done", "score": STAFF_DUTY_SCORE, "by_staff": True}
                if rule.staff:
                    rule.staff(duty_ctx(conn, empire, period, now), duty)
            else:
                conn.execute("UPDATE desk_duties SET status = 'missed', score = 0, done_at = %s WHERE id = %s", (now, duty["id"]))
                duty = {**duty, "status": "missed", "score": 0}
                card["notes"].append(f"Missed: {rule.title if rule else duty['code']}")
                if humans:
                    leagues.award(conn, empire["id"], LEAGUE["duty_missed"], f"A duty was missed: {rule.title if rule else duty['code']}",
                                  period, now, reference=f"duty:{duty['id']}")
                for hook in DUTY_MISSED:
                    hook(conn, empire, duty, humans, period, now)
        card["duties"] += 1
        card["total"] += duty["score"] or 0
        card["done" if duty["status"] == "done" and not duty["by_staff"] else "by_staff" if duty["status"] == "done" else "missed"] += 1
    for build, card in cards.items():
        extra = {"budget": 0, "spent": 0}
        for hook in SCORECARD:
            extra.update(hook(conn, empire, build, period, card) or {})
        conn.execute("INSERT INTO desk_scores (empire_id, build, period, duties, done, by_staff, missed, score, budget, spent, notes)"
                     " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
                     (empire["id"], build, period, card["duties"], card["done"], card["by_staff"], card["missed"],
                      max(0, min(100, card["total"] // max(card["duties"], 1) + int(extra.get("adjust", 0)))),
                      extra["budget"], extra["spent"], _json(card["notes"] + list(extra.get("notes", [])))))
    if cards and empires.humans(conn, empire["id"]) and all(c["missed"] == 0 and c["total"] // max(c["duties"], 1) >= STAFF_DUTY_SCORE
                                                           for c in cards.values()):
        leagues.award(conn, empire["id"], LEAGUE["well_run"], "A well-run firm: every desk did its duties", period, now,
                      reference=f"well_run:{empire['id']}:{period}")


def duties_view(conn: Connection, seat: dict, empire: dict, state: dict, now: datetime) -> dict:
    """Every desk's duties for the quarter (all members see who is doing what), and each desk's scorecards."""
    with conn.transaction():
        ensure_duties(conn, empire, state["period"])
    me, is_head = seat["player_id"], empire["head_player_id"] == seat["player_id"]
    desks = []
    for build in DESKS:
        rows = _rows(conn, "SELECT d.*, p.display_name AS doer, q.display_name AS given_to FROM desk_duties d"
                           " LEFT JOIN players p ON p.id = d.done_by LEFT JOIN players q ON q.id = d.assigned_to"
                           " WHERE d.empire_id = %s AND d.build = %s AND d.period = %s ORDER BY d.id", (empire["id"], build, state["period"]))
        mine = (build == "head" and is_head) or (build != "head" and build == seat["build"])
        lead = lead_of(conn, empire["id"], build) if build != "head" else empire["head_player_id"]
        duties = []
        for d in rows:
            rule = DUTIES.get(d["code"])
            if rule is None:
                continue
            duties.append({"id": d["id"], "code": d["code"], "title": rule.title, "why": rule.why, "status": d["status"], "score": d["score"],
                           "done_by": d["doer"] or ("The staff" if d["by_staff"] else None), "given_to": d["given_to"],
                           "yours": mine and d["status"] == "due" and d["assigned_to"] in (None, me),
                           "opened": d["terms"] is not None and d["assigned_to"] == me,
                           "terms": _public_terms(d["terms"]) if mine and d["assigned_to"] == me and d["status"] == "due" else None,
                           "result": d["result"] if mine and d["done_by"] == me else None,
                           "can_assign": d["status"] == "due" and d["terms"] is None and (is_head or lead == me) and build != "head"})
        cards = _rows(conn, "SELECT period, duties, done, by_staff, missed, score, budget, spent, notes FROM desk_scores"
                            " WHERE empire_id = %s AND build = %s ORDER BY period DESC LIMIT 4", (empire["id"], build))
        members = desk_members(conn, empire["id"], build)
        desks.append({"build": build, "name": DESK_LABELS[build], "yours": mine, "duties": duties, "scorecards": cards,
                      "lead": _name(conn, lead) if lead else None, "you_lead": lead == me,
                      "members": [{"seat_id": _one(conn, "SELECT id FROM empire_seats WHERE player_id = %s", (m,))["id"], "name": _name(conn, m)}
                                  for m in members],
                      "staffed": desk_staffed(conn, empire["id"], build), "empty": not members and not desk_staffed(conn, empire["id"], build)})
    return {"desks": desks, "pass_mark": DUTY_PASS, "staff_score": STAFF_DUTY_SCORE}


# ---------------------------------------------------------------------------
# Documents: the Legal Counsel reads before the head signs
# ---------------------------------------------------------------------------
STRIKE_COST_WORDS = "Each fair clause struck out is one the other side charges for."


def draw_clauses(conn: Connection, pool: list[dict], count: int, traps: tuple[int, int], *seed) -> list[dict]:
    """Draw the clauses of a paper from a pool: `count` in all, of which between traps[0] and
    traps[1] are traps. Each clause is {code, words, trap, plain}. The draw hangs on the world's
    secret, so nobody can know in advance which paper will hide what."""
    bad = [c for c in pool if c["trap"]]
    fair = [c for c in pool if not c["trap"]]
    want = min(len(bad), traps[0] + _roll(conn, "traps", *seed) % (traps[1] - traps[0] + 1))
    chosen = []
    for group, n, tag in ((bad, want, "bad"), (fair, max(count - want, 0), "fair")):
        left = list(group)
        for i in range(min(n, len(left))):
            chosen.append(left.pop(_roll(conn, "clause", tag, i, *seed) % len(left)))
    order = sorted(range(len(chosen)), key=lambda i: _roll(conn, "order", chosen[i]["code"], *seed))
    return [chosen[i] for i in order]


def draft_document(conn: Connection, empire: dict, *, kind: str, title: str, ref: str | None, clauses: list[dict], period: int,
                   now: datetime) -> dict:
    return _one(conn, "INSERT INTO empire_documents (empire_id, kind, title, ref, clauses, period, at) VALUES (%s, %s, %s, %s, %s, %s, %s)"
                      " RETURNING *", (empire["id"], kind, title[:200], ref, _json(clauses), period, now))


def document_public(doc: dict) -> dict:
    """A paper as its readers see it. Which clauses are traps is shown only once it has been read."""
    read = doc["status"] in ("reviewed", "signed")
    return {"id": doc["id"], "kind": doc["kind"], "title": doc["title"], "status": doc["status"], "at": doc["at"],
            "by_staff": doc["by_staff"], "reviewed_at": doc["reviewed_at"],
            "clauses": [{"code": c["code"], "words": c["words"], **({"trap": c["trap"], "plain": c["plain"], "struck": c["code"] in doc["struck"]}
                                                                    if read else {})} for c in doc["clauses"]],
            "kept_traps": len(doc["kept_traps"]) if read else None, "wrongly_struck": len(doc["wrongly_struck"]) if read else None}


def _finish_review(conn: Connection, doc: dict, struck: list[str], reviewer, by_staff: bool, now: datetime) -> dict:
    traps = {c["code"] for c in doc["clauses"] if c["trap"]}
    codes = {c["code"] for c in doc["clauses"]}
    struck = [code for code in dict.fromkeys(struck) if code in codes]
    kept = sorted(traps - set(struck))
    wrong = sorted(set(struck) - traps)
    conn.execute("UPDATE empire_documents SET status = 'reviewed', struck = %s, kept_traps = %s, wrongly_struck = %s, reviewed_by = %s,"
                 " by_staff = %s, reviewed_at = %s WHERE id = %s", (struck, kept, wrong, reviewer, by_staff, now, doc["id"]))
    return {**doc, "status": "reviewed", "struck": struck, "kept_traps": kept, "wrongly_struck": wrong, "reviewed_by": reviewer,
            "by_staff": by_staff, "reviewed_at": now}


def review_document(conn: Connection, player_id, document_id: int, struck: list[str], now: datetime) -> dict:
    """The Legal Counsel reads a paper and strikes out the clauses that would hurt the empire. A trap left
    in stays in force. A fair clause struck out is one the other side charges for.

    When the Legal Counsel's desk has had a day and done nothing, the head may read it instead (and after
    two days the deputy): a head with no Legal Counsel signs at their own risk."""
    with conn.transaction():
        state = _open(conn, now)
        seat, empire = _active(conn, player_id)
        doc = _one(conn, "SELECT * FROM empire_documents WHERE id = %s AND empire_id = %s FOR UPDATE", (document_id, empire["id"]))
        if doc is None or doc["status"] != "draft":
            raise EmpireError("There is no such paper waiting to be read.")
        waited = _hours(doc["at"], now)
        lawyers = desk_members(conn, empire["id"], "lawyer")
        is_head, is_deputy = empire["head_player_id"] == player_id, deputy_of(conn, empire["id"]) == player_id
        late_head = is_head and (waited >= APPROVAL_HOURS or (not lawyers and not desk_staffed(conn, empire["id"], "lawyer")))
        if seat["build"] != "lawyer" and not late_head and not (is_deputy and waited >= DEPUTY_HOURS):
            raise EmpireError("A paper is read by the empire's Legal Counsel. If they have not read it in a day, the head may.")
        if not isinstance(struck, list) or any(not isinstance(code, str) for code in struck) or len(struck) > 40:
            raise EmpireError("Mark the clauses to strike out.")
        done = _finish_review(conn, doc, struck, player_id, False, now)
        if seat["build"] == "lawyer":
            clean = not done["kept_traps"] and not done["wrongly_struck"]
            opinion = sign_opinion(conn, player_id, "lawyer", empire["id"], "paper_read", doc["title"], {"struck": done["struck"]},
                                   state["period"], None, now)
            settle_opinion(conn, opinion, "right" if clean else "wrong",
                           "Every trap was struck out and nothing fair was." if clean else
                           f"{len(done['kept_traps'])} trap(s) were left in; {len(done['wrongly_struck'])} fair clause(s) were struck out.", now)
        for hook in DOCUMENT_READ:
            hook(conn, empire, done, now)
        _log(conn, empire["id"], f"{_name(conn, player_id)} read the paper \"{doc['title']}\".", now)
        return document_public(done)


def _staff_reviews(conn: Connection, now: datetime) -> None:
    """At each Closing Bell the staff read the papers that fall to them. They catch most traps, not all."""
    for waiting in _rows(conn, "SELECT d.id FROM empire_documents d JOIN empires e ON e.id = d.empire_id WHERE d.status = 'draft'"
                               " AND e.status = 'active' ORDER BY d.id"):
        with conn.transaction():
            doc = _one(conn, "SELECT * FROM empire_documents WHERE id = %s AND status = 'draft' FOR UPDATE", (waiting["id"],))
            if doc is None:
                continue
            empire = empires._empire(conn, doc["empire_id"])
            lawyers, waited = desk_members(conn, empire["id"], "lawyer"), _hours(doc["at"], now)
            if desk_staffed(conn, empire["id"], "lawyer") and (not lawyers or waited >= APPROVAL_HOURS):
                struck = [c["code"] for c in doc["clauses"] if c["trap"] and _roll(conn, "staff_reads", doc["id"], c["code"]) < STAFF_CATCHES_BPS]
            elif not player_run(empire) and waited >= APPROVAL_HOURS:
                struck = []                                 # nobody to read it: the computer-run head signs it as it stands
            elif waited >= LAPSE_HOURS:
                conn.execute("UPDATE empire_documents SET status = 'dropped' WHERE id = %s", (doc["id"],))
                for hook in DOCUMENT_DROPPED:
                    hook(conn, empire, doc, now)
                continue
            else:
                continue
            done = _finish_review(conn, doc, struck, None, True, now)
            for hook in DOCUMENT_READ:
                hook(conn, empire, done, now)


def read_document(conn: Connection, document_id) -> dict:
    """A paper that has been read, for the code that acts on it. Raises if nobody has read it yet."""
    doc = _one(conn, "SELECT * FROM empire_documents WHERE id = %s FOR UPDATE", (document_id,))
    if doc is None or doc["status"] not in ("reviewed", "signed"):
        raise EmpireError("The paper has not been read yet. It is with the Legal Counsel's desk.")
    return doc


def documents_view(conn: Connection, seat: dict, empire: dict, now: datetime) -> dict:
    is_head = empire["head_player_id"] == seat["player_id"]
    docs = _rows(conn, "SELECT * FROM empire_documents WHERE empire_id = %s AND status <> 'dropped' ORDER BY (status = 'draft') DESC, id DESC LIMIT 12",
                 (empire["id"],))
    out = []
    for doc in docs:
        waited = _hours(doc["at"], now)
        may = doc["status"] == "draft" and (seat["build"] == "lawyer" or (is_head and (
            waited >= APPROVAL_HOURS or (not desk_members(conn, empire["id"], "lawyer") and not desk_staffed(conn, empire["id"], "lawyer"))))
            or (deputy_of(conn, empire["id"]) == seat["player_id"] and waited >= DEPUTY_HOURS))
        out.append({**document_public(doc), "yours_to_read": bool(may)})
    return {"papers": out, "strike_cost": STRIKE_COST_WORDS}


# ---------------------------------------------------------------------------
# Opinions: what a member put their name to
# ---------------------------------------------------------------------------
OPINION_SETTLERS: dict[str, Callable] = {}     # kind -> (conn, opinion, period, now) -> (outcome, words) or None
OPINION_NAMES: dict[str, str] = {"paper_read": "Papers read for traps"}


def sign_opinion(conn: Connection, player_id, build: str, empire_id, kind: str, subject: str, call: dict, period: int,
                 check_period: int | None, now: datetime) -> int:
    return _one(conn, "INSERT INTO signed_opinions (player_id, build, empire_id, kind, subject, call, period, check_period, at)"
                      " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
                (player_id, build, empire_id, kind, subject[:200], _json(call), period, check_period, now))["id"]


def settle_opinion(conn: Connection, opinion_id: int, outcome: str, words: str, now: datetime) -> None:
    conn.execute("UPDATE signed_opinions SET outcome = %s, outcome_words = %s, settled_at = %s WHERE id = %s AND outcome IS NULL",
                 (outcome, words[:400], now, opinion_id))


def _settle_opinions(conn: Connection, period: int, now: datetime) -> None:
    for opinion in _rows(conn, "SELECT * FROM signed_opinions WHERE outcome IS NULL AND check_period IS NOT NULL AND check_period <= %s"
                               " ORDER BY id", (period,)):
        settler = OPINION_SETTLERS.get(opinion["kind"])
        verdict = settler(conn, opinion, period, now) if settler else ("void", "It could not be checked.")
        if verdict:
            settle_opinion(conn, opinion["id"], verdict[0], verdict[1], now)
            if verdict[0] == "right":
                # A call that turned out right teaches, as a duty done well does.
                mine = careers.career(conn, opinion["player_id"], opinion["build"]) if opinion["build"] in BUILD_NAMES else None
                if mine:
                    careers.add_experience(conn, opinion["player_id"], opinion["build"], DUTY_EXPERIENCE * (1 + mine["rank"]), now)


def track_record(conn: Connection, player_id) -> dict:
    """A member's public record: of everything they signed, how much turned out right."""
    kinds = _rows(conn, "SELECT kind, count(*) FILTER (WHERE outcome = 'right') AS right, count(*) FILTER (WHERE outcome = 'wrong') AS wrong,"
                        " count(*) FILTER (WHERE outcome IS NULL) AS waiting FROM signed_opinions WHERE player_id = %s GROUP BY kind ORDER BY kind",
                  (player_id,))
    latest = _rows(conn, "SELECT kind, subject, period, outcome, outcome_words FROM signed_opinions WHERE player_id = %s ORDER BY id DESC LIMIT 10",
                   (player_id,))
    return {"kinds": [{**k, "name": OPINION_NAMES.get(k["kind"], k["kind"])} for k in kinds],
            "latest": [{**o, "name": OPINION_NAMES.get(o["kind"], o["kind"])} for o in latest],
            "right": sum(k["right"] for k in kinds), "wrong": sum(k["wrong"] for k in kinds)}


# ---------------------------------------------------------------------------
# The head's record
# ---------------------------------------------------------------------------

def ceo_note(conn: Connection, player_id, empire_id, kind: str, words: str, period: int, now: datetime, *, good: bool | None = None,
             reference: str | None = None) -> None:
    conn.execute("INSERT INTO ceo_records (player_id, empire_id, kind, words, good, reference, period, at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"
                 " ON CONFLICT DO NOTHING", (player_id, empire_id, kind, words[:600], good, reference, period, now))


def ceo_record(conn: Connection, player_id) -> dict:
    """A head's record: every empire they have led and what they did there. It is public."""
    rows = _rows(conn, "SELECT r.kind, r.words, r.good, r.period, r.at, e.name AS empire FROM ceo_records r JOIN empires e ON e.id = r.empire_id"
                       " WHERE r.player_id = %s ORDER BY r.id DESC LIMIT 40", (player_id,))
    return {"entries": rows, "good": sum(1 for r in rows if r["good"] is True), "bad": sum(1 for r in rows if r["good"] is False),
            "overrules": sum(1 for r in rows if r["kind"] in ("overrule", "unfreeze")),
            "empires": sorted({r["empire"] for r in rows})}


def _settle_overrules(conn: Connection, period: int, now: datetime) -> None:
    """Did what the head overruled turn out well? Looked at as each quarter closes, once it can be known."""
    for note in _rows(conn, "SELECT r.id, r.reference FROM ceo_records r WHERE r.kind = 'overrule' AND r.good IS NULL AND r.period < %s"
                            " AND r.reference LIKE 'approval:%%'", (period,)):
        approval = _one(conn, "SELECT * FROM empire_approvals WHERE id = %s", (int(note["reference"].split(":")[1]),))
        settler = OVERRULE_SETTLERS.get(approval["kind"]) if approval else None
        good = settler(conn, approval, period) if settler else None
        if good is not None:
            conn.execute("UPDATE ceo_records SET good = %s WHERE id = %s", (good, note["id"]))


# ---------------------------------------------------------------------------
# What an empire owes
# ---------------------------------------------------------------------------

def debt_of(conn: Connection, empire_id) -> int:
    """What an empire owes to its lenders and to the holders of its bonds."""
    return _one(conn, "SELECT coalesce(sum(outstanding), 0)::bigint AS owed FROM empire_debts WHERE empire_id = %s"
                      " AND status IN ('open', 'called', 'defaulted')", (empire_id,))["owed"]


# ---------------------------------------------------------------------------
# The parts of the firm add themselves to these
# ---------------------------------------------------------------------------
BELL: list[Callable] = []              # (conn, now)
CLOSE: list[Callable] = []             # (conn, empire, period, now) : once for each active empire, in the order added
CLOSED: list[Callable] = []            # (conn, period, now) : once, after every empire's close
VIEW: dict[str, Callable] = {}         # key -> (conn, seat, empire, state, now) -> what the member sees
WAITING: list[Callable] = []           # (conn, seat, empire, now) -> how many things wait for this member
VACATED: list[Callable] = []           # (conn, seat, now)
PROMOTED: list[Callable] = []          # (conn, empire, member_id, title, state, now)
DECIDED: list[Callable] = []           # (conn, approval, decider_seat, now)
DUTY_DONE: list[Callable] = []         # (conn, empire, duty, seat, experience, now)
DUTY_MISSED: list[Callable] = []       # (conn, empire, duty, humans, period, now)
SCORECARD: list[Callable] = []         # (conn, empire, build, period, card) -> {budget, spent, adjust, notes}
DOCUMENT_READ: list[Callable] = []     # (conn, empire, document, now)
DOCUMENT_DROPPED: list[Callable] = []  # (conn, empire, document, now)
RAISE_DESIGNED: list[Callable] = []    # (conn, empire, approval, now) : the Investment Banker has designed a way to raise money
RAISED: list[Callable] = []            # (conn, empire, {kind, amount, debt_id?}, now) : money has come in


def at_bell(conn: Connection, now: datetime) -> None:
    """At each Closing Bell: the staff decide and read what falls to them, and votes whose time is up are counted."""
    _staff_decisions(conn, now)
    _staff_reviews(conn, now)
    _count_due(conn, now)
    for hook in BELL:
        hook(conn, now)


def after_close(conn: Connection, period: int, now: datetime) -> None:
    """As a quarter closes, for every open empire: its desks' duties are closed and scored, and the
    next quarter's are set out; what was signed is checked against what happened."""
    for row in _rows(conn, "SELECT id FROM empires WHERE status = 'active' AND kind <> 'pension' ORDER BY id"):
        with conn.transaction():
            empire = empires._empire(conn, row["id"], lock=True)
            for hook in CLOSE:
                hook(conn, empire, period, now)
            _close_duties(conn, empire, period, now)
            ensure_duties(conn, empire, period + 1)
    _settle_opinions(conn, period, now)
    _settle_overrules(conn, period, now)
    _count_due(conn, now)
    for hook in CLOSED:
        hook(conn, period, now)


def waiting(conn: Connection, seat: dict, now: datetime) -> int:
    """How many things in the firm wait for this member: for the badge in the sections menu."""
    empire = empires._empire(conn, seat["empire_id"])
    if empire["status"] != "active" or empire["kind"] == "pension":
        return 0
    me = seat["player_id"]
    count = sum(1 for a in _rows(conn, "SELECT * FROM empire_approvals WHERE empire_id = %s AND status = 'waiting'", (empire["id"],))
                if me in deciders(conn, a, now))
    count += _one(conn, "SELECT count(*) AS n FROM empire_resolutions r WHERE r.empire_id = %s AND r.status = 'open' AND NOT EXISTS"
                        " (SELECT 1 FROM empire_resolution_votes v WHERE v.resolution_id = r.id AND v.player_id = %s)", (empire["id"], me))["n"]
    if seat["build"] == "lawyer":
        count += _one(conn, "SELECT count(*) AS n FROM empire_documents WHERE empire_id = %s AND status = 'draft'", (empire["id"],))["n"]
    for hook in WAITING:
        count += hook(conn, seat, empire, now)
    return count


def view(conn: Connection, player_id, now: datetime) -> dict | None:
    """Everything a member sees of the firm they sit in."""
    seat = empires.seat_of(conn, player_id)
    if seat is None or seat["empire_status"] != "active" or seat["empire_kind"] == "pension":
        return None
    state = careers.world_now(conn, now)
    empire = empires._empire(conn, seat["empire_id"])
    is_head = empire["head_player_id"] == player_id
    deputy = deputy_of(conn, empire["id"])
    out = {
        "empire_id": empire["id"], "name": empire["name"], "player_run": player_run(empire), "is_head": is_head,
        "is_deputy": deputy == player_id, "deputy": _name(conn, deputy) if deputy else None, "your_build": seat["build"],
        "period": state["period"], "quarter_ends_at": state.get("ends_at"),
        "roster": roster(conn, empire["id"], player_id),
        "seats": seats_view(conn, empire, player_id),
        "approvals": approvals_view(conn, seat, empire, now),
        "resolutions": resolutions_view(conn, seat, empire, now),
        "duties": duties_view(conn, seat, empire, state, now),
        "papers": documents_view(conn, seat, empire, now),
        "articles": articles_of(conn, empire["id"]),
        "record": track_record(conn, player_id),
        "head_record": ceo_record(conn, empire["head_player_id"]) if empire["head_player_id"] else None,
    }
    for key, part in VIEW.items():
        out[key] = part(conn, seat, empire, state, now)
    return out


# The parts of the firm, each adding itself to the lists above.
from simulation import (  # noqa: F401  # noqa: E402,F401  (registers their hooks)
    firm_clients,
    firm_dealmaking,
    firm_deals,
    firm_duties,
    firm_money,
    firm_owned,
    firm_people,
    firm_practice,
    firm_risk,
    firm_tasks,
)
