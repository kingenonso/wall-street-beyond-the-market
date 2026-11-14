"""The firm's people: contracts, apprentices, poaching, the empire's own rules, and the head's year.

  contracts        notice, a promised share of the desk's pool, and a non-compete: drafted by the
                   Legal Counsel, offered by the head, signed by the member, enforced by the game
  apprentices      a senior member takes a junior of the same build; both gain when the junior does well
  poaching         another empire's head offers a member a bonus to come over; the home empire has two
                   days to match; a member under contract moves only for a transfer fee
  the constitution what the members vote: how big votes are carried, the members' signing limit, and
                   what happens to a leaving partner's units
  code of conduct  how hard the empire is on theft and on missed duties, voted by the members
  the head's year  the strategy and its targets, the yearly vote of confidence, the scorecard

Nothing here makes money: every payment is from one account to another.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from psycopg import Connection, errors

from simulation import careers, clock, empires, firm, leagues, ledger
from simulation import world_data as data
from simulation.empires import (
    BUILD_NAMES,
    EmpireError,
    _log,
    _money,
    _one,
    _open,
    _rows,
    _text,
)
from simulation.money import BPS, apply_bps, naira

MATCH_HOURS = 48                    # the home empire has this long to match a poaching offer
POACH_LAPSE_DAYS = 4                # an offer nobody has answered is dropped after this
APPRENTICE_GAP = 10                 # a mentor is at least this many levels above the apprentice
MENTOR_SHARE_BPS = 2000             # a mentor gains a fifth of the experience their apprentice earns, on top
APPRENTICE_EXTRA_BPS = 1000         # an apprentice earns a tenth more experience on their desk's duties
CONFIDENCE_EVERY = 4                # the vote of confidence is held as each game year closes
STRATEGIES = {
    "grow": "Grow fast: the empire's worth up by a good margin over the year",
    "income": "Steady income: pay the partners regular dividends",
    "takeovers": "Takeovers: finish tasks and build holdings in companies",
    "safe": "Play safe: keep losses small and the books clean",
}


# ---------------------------------------------------------------------------
# Employment contracts
# ---------------------------------------------------------------------------

def offer_contract(conn: Connection, player_id, member_id, notice_days: int, bonus_bps: int, non_compete: int, now: datetime) -> dict:
    """The Legal Counsel drafts a member's contract (or the head, when the empire has no Legal Counsel). The head
    offers it. Here both happen at once when the head drafts; a Legal Counsel's draft goes to the head."""
    with conn.transaction():
        _open(conn, now)
        seat, empire = firm._active(conn, player_id)
        if not firm.player_run(empire):
            raise EmpireError("An empire run by the computer offers no contracts.")
        is_head, lawyers = empire["head_player_id"] == player_id, firm.desk_members(conn, empire["id"], "investment_banker")
        if seat["build"] != "investment_banker" and not (is_head and not lawyers):
            raise EmpireError("Contracts are drafted by the empire's Legal Counsel (by the head only when there is no Legal Counsel).")
        member = empires.seat_of(conn, member_id)
        if member is None or member["empire_id"] != empire["id"] or member_id == empire["head_player_id"]:
            raise EmpireError("A contract is for a member of your empire (not the head).")
        if member_id == player_id:
            raise EmpireError("A Legal Counsel does not draft their own contract.")
        if not firm._whole(notice_days, 0, data.NOTICE_DAYS) or not firm._whole(bonus_bps, 0, 2000) or not firm._whole(non_compete, 0, 2):
            raise EmpireError(f"Notice of 0 to {data.NOTICE_DAYS} days; a share of the desk's pool of 0% to 20%; a non-compete of 0 to 2 quarters.")
        status = "offered" if is_head else "drafted"           # a Legal Counsel's draft goes to the head, who decides whether to offer it
        try:
            with conn.transaction():
                contract = _one(conn, "INSERT INTO member_contracts (empire_id, player_id, notice_days, bonus_bps, non_compete, status, offered_by,"
                                      " drafted_by, offered_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING *",
                                (empire["id"], member_id, notice_days, bonus_bps, non_compete, status, player_id if is_head else None, player_id, now))
        except errors.UniqueViolation:
            raise EmpireError("That member already has a contract drafted, offered or signed. It must end first.") from None
        if is_head:
            careers._event(conn, member_id, member["build"], "contract", f"{empire['name']} offered you a contract.", now)
        return {"id": contract["id"], "status": status}


def send_contract(conn: Connection, head_id, contract_id: int, offer: bool, now: datetime) -> None:
    """The head offers a contract the Legal Counsel drafted, or tears it up."""
    with conn.transaction():
        _open(conn, now)
        empire = empires._head(conn, head_id)
        contract = _one(conn, "SELECT * FROM member_contracts WHERE id = %s AND empire_id = %s FOR UPDATE", (contract_id, empire["id"]))
        if contract is None or contract["status"] != "drafted":
            raise EmpireError("There is no draft contract waiting for you.")
        if contract["player_id"] == head_id:
            raise EmpireError("A head does not offer a contract to themselves.")
        conn.execute("UPDATE member_contracts SET status = %s, offered_by = %s, offered_at = %s WHERE id = %s",
                     ("offered" if offer else "refused", head_id, now, contract_id))
        if offer:
            careers._event(conn, contract["player_id"], None, "contract", f"{empire['name']} offered you a contract.", now)


def answer_contract(conn: Connection, player_id, contract_id: int, sign: bool, now: datetime) -> None:
    with conn.transaction():
        _open(conn, now)
        contract = _one(conn, "SELECT * FROM member_contracts WHERE id = %s AND player_id = %s FOR UPDATE", (contract_id, player_id))
        if contract is None or contract["status"] != "offered":
            raise EmpireError("There is no contract waiting for you.")
        seat = empires.seat_of(conn, player_id)
        if seat is None or seat["empire_id"] != contract["empire_id"]:
            raise EmpireError("You are no longer in that empire.")
        if sign:
            conn.execute("UPDATE member_contracts SET status = 'ended', ended_at = %s WHERE empire_id = %s AND player_id = %s AND status = 'signed'",
                         (now, contract["empire_id"], player_id))
        conn.execute("UPDATE member_contracts SET status = %s, signed_at = %s WHERE id = %s",
                     ("signed" if sign else "refused", now if sign else None, contract_id))
        _log(conn, contract["empire_id"], f"{firm._name(conn, player_id)} {'signed' if sign else 'turned down'} a contract.", now)


def contract_of(conn: Connection, empire_id, player_id) -> dict | None:
    return _one(conn, "SELECT * FROM member_contracts WHERE empire_id = %s AND player_id = %s AND status = 'signed'", (empire_id, player_id))


def notice_days(conn: Connection, empire_id, player_id) -> int:
    contract = contract_of(conn, empire_id, player_id)
    return contract["notice_days"] if contract else data.NOTICE_DAYS


def _vacated(conn: Connection, seat: dict, now: datetime) -> None:
    """A member leaves: a signed contract ends, and a non-compete starts to run."""
    contract = contract_of(conn, seat["empire_id"], seat["player_id"])
    period = careers.world_now(conn, now)["period"]
    if contract:
        rival = _one(conn, "SELECT rival_id FROM empires WHERE id = %s", (seat["empire_id"],))["rival_id"]
        conn.execute("UPDATE member_contracts SET status = 'ended', ended_at = %s, bars_until = %s, bars_empire = %s WHERE id = %s",
                     (now, period + contract["non_compete"] if contract["non_compete"] else None, rival if contract["non_compete"] else None,
                      contract["id"]))
    conn.execute("UPDATE member_contracts SET status = 'refused' WHERE empire_id = %s AND player_id = %s AND status IN ('drafted', 'offered')",
                 (seat["empire_id"], seat["player_id"]))
    conn.execute("UPDATE empire_apprentices SET ended_at = %s WHERE empire_id = %s AND (mentor_id = %s OR apprentice_id = %s) AND ended_at IS NULL",
                 (now, seat["empire_id"], seat["player_id"], seat["player_id"]))
    _leaver_units(conn, seat, now)


def barred(conn: Connection, empire: dict, player_id, period: int) -> None:
    """A non-compete: a member who left may not join their old empire's rival until it has run."""
    row = _one(conn, "SELECT c.bars_until, e.name FROM member_contracts c JOIN empires e ON e.id = c.empire_id WHERE c.player_id = %s"
                     " AND c.bars_empire = %s AND c.bars_until >= %s ORDER BY c.bars_until DESC LIMIT 1", (player_id, empire["id"], period))
    if row:
        raise EmpireError(f"Your contract with {row['name']} bars you from its rival until {clock.period_label(row['bars_until'])} has ended.")


# ---------------------------------------------------------------------------
# Apprentices
# ---------------------------------------------------------------------------

def take_apprentice(conn: Connection, mentor_id, apprentice_id, now: datetime) -> None:
    with conn.transaction():
        state = _open(conn, now)
        seat, empire = firm._active(conn, mentor_id)
        other = empires.seat_of(conn, apprentice_id)
        if other is None or other["empire_id"] != empire["id"] or other["build"] != seat["build"] or apprentice_id == mentor_id:
            raise EmpireError("An apprentice is a member of your empire in your own build.")
        mine, theirs = careers.career(conn, mentor_id, seat["build"]), careers.career(conn, apprentice_id, seat["build"])
        if not mine or not theirs or mine["level"] < theirs["level"] + APPRENTICE_GAP:
            raise EmpireError(f"A mentor is at least {APPRENTICE_GAP} levels above their apprentice.")
        if _one(conn, "SELECT 1 FROM empire_apprentices WHERE mentor_id = %s AND ended_at IS NULL", (mentor_id,)):
            raise EmpireError("You already have an apprentice.")
        try:
            with conn.transaction():
                conn.execute("INSERT INTO empire_apprentices (empire_id, mentor_id, apprentice_id, build, since_period, at) VALUES (%s, %s, %s, %s, %s, %s)",
                             (empire["id"], mentor_id, apprentice_id, seat["build"], state["period"], now))
        except errors.UniqueViolation:
            raise EmpireError("They already have a mentor.") from None
        careers._event(conn, apprentice_id, seat["build"], "apprentice", f"{firm._name(conn, mentor_id)} took you on as their apprentice.", now)
        _log(conn, empire["id"], f"{firm._name(conn, mentor_id)} took {firm._name(conn, apprentice_id)} on as an apprentice.", now)


def end_apprenticeship(conn: Connection, player_id, now: datetime) -> None:
    with conn.transaction():
        _open(conn, now)
        if not conn.execute("UPDATE empire_apprentices SET ended_at = %s WHERE (mentor_id = %s OR apprentice_id = %s) AND ended_at IS NULL",
                            (now, player_id, player_id)).rowcount:
            raise EmpireError("You have no apprenticeship to end.")


def apprentice_gain(conn: Connection, player_id, build: str, gained: int, now: datetime) -> None:
    """The apprentice has earned experience on their own work: the mentor earns a fifth of it on top.
    It is new experience for the mentor, taken from nobody."""
    if gained <= 0:
        return
    row = _one(conn, "SELECT mentor_id FROM empire_apprentices WHERE apprentice_id = %s AND build = %s AND ended_at IS NULL", (player_id, build))
    if row:
        careers.add_experience(conn, row["mentor_id"], build, apply_bps(gained, MENTOR_SHARE_BPS), now)


def _duty_done(conn: Connection, empire: dict, duty: dict, seat: dict, gained: int, now: datetime) -> None:
    if not gained:
        return
    row = _one(conn, "SELECT mentor_id FROM empire_apprentices WHERE apprentice_id = %s AND ended_at IS NULL", (seat["player_id"],))
    if row:
        careers.add_experience(conn, seat["player_id"], seat["build"], apply_bps(gained, APPRENTICE_EXTRA_BPS), now)
        apprentice_gain(conn, seat["player_id"], seat["build"], gained, now)


# ---------------------------------------------------------------------------
# Poaching
# ---------------------------------------------------------------------------

def poach(conn: Connection, head_id, member_id, bonus: int, words: str, now: datetime) -> dict:
    """A head offers another empire's member a bonus to come over, into a free seat of their build."""
    with conn.transaction():
        _open(conn, now)
        empire = empires._head(conn, head_id)
        if empire["status"] != "active":
            raise EmpireError("Your empire is not open yet.")
        their = empires.seat_of(conn, member_id)
        if their is None or their["empire_id"] == empire["id"] or their["empire_status"] != "active" or their["empire_kind"] == "pension":
            raise EmpireError("You can approach a member of another open empire.")
        if their["head_player_id"] == member_id:
            raise EmpireError("A head is not poached. Talk to them as one head to another.")
        if empires.in_truce(conn, empire["id"], their["empire_id"]):
            raise EmpireError("Your empire has a truce with theirs: no poaching while it stands. Break the truce first, and pay for it in trust.")
        if not firm._whole(bonus, naira(100_000)):
            raise EmpireError("A bonus of at least ₦100,000.")
        if not _one(conn, "SELECT 1 FROM empire_seats WHERE empire_id = %s AND build = %s AND player_id IS NULL", (empire["id"], their["build"])):
            raise EmpireError(f"Your empire has no free {BUILD_NAMES[their['build']]} seat.")
        if ledger.balance(conn, empire["account_id"]) < bonus:
            raise EmpireError("Your empire has not the cash for that bonus.")
        room = _bonus_room(conn, empire, now)
        if bonus > room:
            raise EmpireError(f"A joining bonus is inside your bonus limit for the quarter: {_money(room)} is left.")
        try:
            with conn.transaction():
                offer = _one(conn, "INSERT INTO poach_offers (from_empire, to_empire, player_id, build, bonus, words, at, match_by)"
                                   " VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING *",
                             (empire["id"], their["empire_id"], member_id, their["build"], bonus, _text(words or "")[:400] or None, now,
                              now + timedelta(hours=MATCH_HOURS)))
        except errors.UniqueViolation:
            raise EmpireError("You already have an offer open to that member.") from None
        careers._event(conn, member_id, their["build"], "poached", f"{empire['name']} offered you {_money(bonus)} to join them.", now)
        return {"id": offer["id"]}


def _bonus_room(conn: Connection, empire: dict, now: datetime) -> int:
    period = careers.world_now(conn, now)["period"]
    paid = _one(conn, "SELECT coalesce(sum(amount), 0)::bigint AS n FROM empire_books WHERE empire_id = %s AND period = %s AND kind IN ('bonus')",
                (empire["id"], period))["n"]
    fees = _one(conn, "SELECT coalesce(sum(amount), 0)::bigint AS n FROM empire_books WHERE empire_id = %s AND period = %s AND category = 'Transfer fees'",
                (empire["id"], period))["n"]
    return max(empires.bonus_limit(conn, empire, now) - paid - fees, 0)


def match(conn: Connection, head_id, offer_id: int, bonus: int, now: datetime) -> None:
    """The home empire's head offers the member a bonus to stay."""
    with conn.transaction():
        _open(conn, now)
        empire = empires._head(conn, head_id)
        offer = _one(conn, "SELECT * FROM poach_offers WHERE id = %s AND to_empire = %s FOR UPDATE", (offer_id, empire["id"]))
        if offer is None or offer["status"] != "open":
            raise EmpireError("There is no such approach to one of your members waiting.")
        if now > offer["match_by"]:
            raise EmpireError("The two days to match have passed.")
        if not firm._whole(bonus, 1) or ledger.balance(conn, empire["account_id"]) < bonus:
            raise EmpireError("A bonus the empire has the cash for.")
        if bonus > _bonus_room(conn, empire, now):
            raise EmpireError(f"A bonus to stay is inside your bonus limit for the quarter: {_money(_bonus_room(conn, empire, now))} is left.")
        conn.execute("UPDATE poach_offers SET status = 'matched', matched = %s WHERE id = %s", (bonus, offer_id))


def answer_poach(conn: Connection, player_id, offer_id: int, go: bool, now: datetime) -> dict:
    """The member decides: go, or stay (taking the match, if there is one). While the home empire's
    two days to match are running, and it has not matched, the member may stay but not yet go."""
    with conn.transaction():
        state = _open(conn, now)
        offer = _one(conn, "SELECT * FROM poach_offers WHERE id = %s AND player_id = %s FOR UPDATE", (offer_id, player_id))
        if offer is None or offer["status"] not in ("open", "matched"):
            raise EmpireError("There is no such offer waiting for you.")
        seat = empires.seat_of(conn, player_id, lock=True)
        if seat is None or seat["empire_id"] != offer["to_empire"]:
            conn.execute("UPDATE poach_offers SET status = 'lapsed', decided_at = %s WHERE id = %s", (now, offer_id))
            raise EmpireError("You are no longer in the empire it was made to.")
        home = empires._empire(conn, offer["to_empire"], lock=True)
        new = empires._empire(conn, offer["from_empire"], lock=True)
        if not go:
            note = ""
            if offer["status"] == "matched" and offer["matched"]:
                from simulation import firm_money
                try:
                    with conn.transaction():
                        firm_money._pay_bonus_inside(conn, home, player_id, offer["matched"], "Bonus to stay, matching another empire's offer", now)
                except EmpireError as short:
                    note = f" The bonus to stay could not be paid: {short}"
            if note:
                _log(conn, home["id"], note.strip(), now)
            conn.execute("UPDATE poach_offers SET status = 'declined', decided_at = %s WHERE id = %s", (now, offer_id))
            _log(conn, home["id"], f"{firm._name(conn, player_id)} was approached by {new['name']} and stayed.", now)
            return {"moved": False}
        if offer["status"] == "open" and now < offer["match_by"]:
            raise EmpireError(f"Your empire has until {clock.to_lagos(offer['match_by']):%d %B %H:%M} to match. You may stay now, or go after that.")
        player = _one(conn, "SELECT id, build, reputation, display_name FROM players WHERE id = %s FOR UPDATE", (player_id,))
        if seat["head_player_id"] == player_id:
            raise EmpireError("A head is not poached.")
        if _one(conn, "SELECT 1 FROM empire_cases WHERE player_id = %s AND status = 'open'", (player_id,)):
            raise EmpireError("A member with a theft case waiting cannot move until it is decided.")
        fee = offer["bonus"] if contract_of(conn, home["id"], player_id) else 0
        if ledger.balance(conn, new["account_id"]) < offer["bonus"] + fee or offer["bonus"] + fee > _bonus_room(conn, new, now):
            conn.execute("UPDATE poach_offers SET status = 'lapsed', decided_at = %s WHERE id = %s", (now, offer_id))
            return {"moved": False, "lapsed": f"{new['name']} can no longer pay its offer (and any transfer fee) inside its cash and bonus limit."}
        empires._go(conn, seat, now, state["period"], "left")
        empires._may_join(conn, new, player, state["period"])
        barred(conn, new, player_id, state["period"])
        empires._take_seat(conn, new, player_id, offer["build"], now, state["period"])
        ledger.transfer(conn, payer=new["account_id"], receiver=ledger.player_account_id(conn, player_id), amount=offer["bonus"],
                        kind="empire_bonus", memo=f"{new['name']}: a bonus for joining", period=state["period"])
        empires._book(conn, new["id"], state["period"], "Bonuses", "A bonus for joining", offer["bonus"], True, now, kind="bonus")
        if fee:
            ledger.transfer(conn, payer=new["account_id"], receiver=home["account_id"], amount=fee, kind="empire_transfer_fee",
                            memo=f"{new['name']}: transfer fee to {home['name']}", period=state["period"])
            empires._book(conn, new["id"], state["period"], "Transfer fees", f"Transfer fee to {home['name']}", fee, True, now, kind="fee")
        conn.execute("UPDATE poach_offers SET status = 'accepted', decided_at = %s WHERE id = %s", (now, offer_id))
        conn.execute("UPDATE empire_resignations SET status = 'overtaken', ended_at = %s WHERE player_id = %s AND status = 'waiting'", (now, player_id))
        _log(conn, home["id"], f"{player['display_name']} left for {new['name']}" + (f", which paid a transfer fee of {_money(fee)}." if fee else "."), now)
        return {"moved": True, "fee": fee}


def withdraw_poach(conn: Connection, head_id, offer_id: int, now: datetime) -> None:
    with conn.transaction():
        empire = empires._head(conn, head_id)
        if not conn.execute("UPDATE poach_offers SET status = 'withdrawn', decided_at = %s WHERE id = %s AND from_empire = %s"
                            " AND status IN ('open', 'matched')", (now, offer_id, empire["id"])).rowcount:
            raise EmpireError("There is no offer of yours open.")


def _lapse_poaching(conn: Connection, now: datetime) -> None:
    with conn.transaction():
        conn.execute("UPDATE poach_offers SET status = 'lapsed', decided_at = %s WHERE status IN ('open', 'matched') AND at < %s",
                     (now, now - timedelta(days=POACH_LAPSE_DAYS)))


# ---------------------------------------------------------------------------
# The constitution and the code of conduct
# ---------------------------------------------------------------------------
CONSTITUTION_DEFAULT = {"big_votes": "majority", "member_signing_naira": None, "leaver_units": "keep"}
CONDUCT_DEFAULT = {"theft": "head_decides", "missed_duty_fine_naira": 0}


def _constitution_check(conn: Connection, empire: dict, payload: dict, now: datetime) -> dict:
    out = {}
    if "big_votes" in payload:
        if payload["big_votes"] not in ("majority", "two_thirds"):
            raise EmpireError("Big votes are carried by a majority or by two-thirds.")
        out["big_votes"] = payload["big_votes"]
    if "member_signing_naira" in payload:
        if not firm._whole(payload["member_signing_naira"], 0, data.SIGNING_LIMIT_NAIRA * 20):
            raise EmpireError("A member's signing limit from ₦0 to twenty times the usual figure.")
        out["member_signing_naira"] = payload["member_signing_naira"]
    if "leaver_units" in payload:
        if payload["leaver_units"] not in ("keep", "buy_back"):
            raise EmpireError("A leaving partner keeps their units, or the empire buys them back.")
        out["leaver_units"] = payload["leaver_units"]
    if not out:
        raise EmpireError("Say which rule to change.")
    return out


def _constitution_carry(conn: Connection, empire: dict, resolution: dict, now: datetime) -> str:
    said = []
    for key, value in resolution["payload"].items():
        firm.set_article(conn, empire["id"], key, value, resolution["period"], now, resolution["id"])
        if key == "member_signing_naira":
            conn.execute("UPDATE empires SET expense_limit = %s WHERE id = %s", (naira(value), empire["id"]))
        said.append({"big_votes": "how big votes are carried", "member_signing_naira": "the members' signing limit",
                     "leaver_units": "what happens to a leaving partner's units"}[key])
    return "The constitution was changed: " + ", ".join(said) + "."


def _conduct_check(conn: Connection, empire: dict, payload: dict, now: datetime) -> dict:
    theft, fine = payload.get("theft"), payload.get("missed_duty_fine_naira")
    if theft not in ("head_decides", "always_punish") or not firm._whole(fine, 0, 1_000_000):
        raise EmpireError("Theft: the head decides, or always punished. A fine for a missed duty from ₦0 to ₦1,000,000.")
    return {"theft": theft, "missed_duty_fine_naira": fine}


def _conduct_carry(conn: Connection, empire: dict, resolution: dict, now: datetime) -> str:
    firm.set_article(conn, empire["id"], "conduct", resolution["payload"], resolution["period"], now, resolution["id"])
    p = resolution["payload"]
    return (f"The code of conduct: theft is {'always punished' if p['theft'] == 'always_punish' else 'decided by the head'}; "
            f"a missed duty costs whoever it was given to {_money(naira(p['missed_duty_fine_naira']))}.")


def conduct(conn: Connection, empire_id) -> dict:
    return {**CONDUCT_DEFAULT, **(firm.article(conn, empire_id, "conduct") or {})}


def _missed(conn: Connection, empire: dict, duty: dict, humans: list, period: int, now: datetime) -> None:
    """The code of conduct: a member who was given a duty and let it be missed pays the fine to the empire."""
    fine = naira(conduct(conn, empire["id"])["missed_duty_fine_naira"])
    who = duty.get("assigned_to")
    if fine and who and empires.seat_of(conn, who) and empires.seat_of(conn, who)["empire_id"] == empire["id"]:
        took = ledger.pay_up_to(conn, payer=ledger.player_account_id(conn, who), receiver=empire["account_id"], wanted=fine,
                                kind="empire_fine", memo=f"{empire['name']}: fine for a missed duty, under its code of conduct", period=period)
        if took:
            _log(conn, empire["id"], f"{firm._name(conn, who)} paid {_money(took)} under the code of conduct for a missed duty.", now)


def _leaver_units(conn: Connection, seat: dict, now: datetime) -> None:
    """When the constitution says so, the empire buys a leaving partner's units back at today's price, as far as its cash allows."""
    empire = empires._empire(conn, seat["empire_id"])
    if empire["kind"] != "player" or empire["status"] != "active" or firm.article(conn, empire["id"], "leaver_units") != "buy_back":
        return
    from simulation import firm_money
    held = _one(conn, "SELECT units FROM empire_units WHERE empire_id = %s AND player_id = %s", (empire["id"], seat["player_id"]))
    if not held or not held["units"]:
        return
    if _one(conn, "SELECT 1 FROM empire_cases WHERE empire_id = %s AND player_id = %s AND status = 'open'", (empire["id"], seat["player_id"])):
        return                                              # a member with a theft case waiting keeps their units until it is decided
    value = firm_money.value_of(conn, empire, held["units"], now)
    if value <= 0:
        return
    period = careers.world_now(conn, now)["period"]
    # What a proved thief still owes the empire comes out of what their units are worth, before anything is paid.
    owed = _one(conn, "SELECT coalesce(sum(debt_left), 0)::bigint AS n FROM empire_cases WHERE empire_id = %s AND player_id = %s AND status = 'punished'",
                (empire["id"], seat["player_id"]))["n"]
    kept = min(owed, value)
    if kept:
        for case in _rows(conn, "SELECT id, debt_left FROM empire_cases WHERE empire_id = %s AND player_id = %s AND status = 'punished' AND debt_left > 0"
                                " ORDER BY id FOR UPDATE", (empire["id"], seat["player_id"])):
            take = min(case["debt_left"], kept)
            conn.execute("UPDATE empire_cases SET debt_left = debt_left - %s WHERE id = %s", (take, case["id"]))
            kept -= take
        kept = min(owed, value)
    want = value - kept
    paid = ledger.pay_up_to(conn, payer=empire["account_id"], receiver=ledger.player_account_id(conn, seat["player_id"]),
                            wanted=want, kind="empire_buy_back", memo=f"{empire['name']}: units bought back from a leaving partner",
                            period=period) if want > 0 else 0
    # The units bought back are those the cash (and the debt set against them) actually paid for, exactly.
    bought = held["units"] if paid >= want else held["units"] * (paid + kept) // value
    conn.execute("UPDATE empire_units SET units = units - %s WHERE empire_id = %s AND player_id = %s", (bought, empire["id"], seat["player_id"]))
    if paid or kept:
        _log(conn, empire["id"], f"Under the constitution, the empire bought back {firm._name(conn, seat['player_id'])}'s units for {_money(paid)}"
                                 + (f", after {_money(kept)} they owed the empire was set against them" if kept else "") + ".", now)


# ---------------------------------------------------------------------------
# The head's year: strategy, the vote of confidence, the scorecard
# ---------------------------------------------------------------------------

def set_strategy(conn: Connection, head_id, choice: str, growth_bps: int, payout: int, tasks: int, now: datetime) -> None:
    """The head sets the year's direction and three targets. It can be set once in a game year, and
    the partners judge the head against the targets the head chose."""
    with conn.transaction():
        state = _open(conn, now)
        empire = empires._head(conn, head_id)
        if choice not in STRATEGIES:
            raise EmpireError("Choose one of the four directions.")
        if not firm._whole(growth_bps, -5000, 20000) or not firm._whole(payout, 0) or not firm._whole(tasks, 0, 12):
            raise EmpireError("Targets: growth in worth from -50% to 200%; dividends paid, in kobo; tasks finished, 0 to 12.")
        season = leagues.season_of(state["period"])
        try:
            with conn.transaction():
                conn.execute("INSERT INTO empire_strategies (empire_id, season, choice, targets, set_by, at) VALUES (%s, %s, %s, %s, %s, %s)",
                             (empire["id"], season, choice, firm._json({"growth_bps": growth_bps, "payout": payout, "tasks": tasks,
                                                                         "start_worth": empires.worth(conn, empire, now)["total"],
                                                                         "from_period": state["period"]}), head_id, now))
        except errors.UniqueViolation:
            raise EmpireError("The year's strategy is already set. It stands until the year ends.") from None
        firm.ceo_note(conn, head_id, empire["id"], "strategy", f"Set the year's strategy: {STRATEGIES[choice]}. Targets: worth up "
                                                               f"{growth_bps / 100:.0f}%, {_money(payout)} in dividends, {tasks} tasks.",
                      state["period"], now, reference=f"strategy:{empire['id']}:{season}")
        _log(conn, empire["id"], f"The head set the year's strategy: {STRATEGIES[choice]}.", now)


def _judge_strategy(conn: Connection, empire: dict, period: int, now: datetime) -> None:
    season = leagues.season_of(period)
    row = _one(conn, "SELECT * FROM empire_strategies WHERE empire_id = %s AND season = %s AND result IS NULL FOR UPDATE", (empire["id"], season))
    if row is None:
        return
    t = row["targets"]
    worth = empires.worth(conn, empire, now)["total"]
    capital = _one(conn, "SELECT coalesce(sum(amount), 0)::bigint AS n FROM empire_capital WHERE empire_id = %s AND period >= %s",
                   (empire["id"], t["from_period"]))["n"]
    paid = _one(conn, "SELECT coalesce(sum(amount), 0)::bigint AS n FROM empire_payouts WHERE empire_id = %s AND period >= %s",
                (empire["id"], t["from_period"]))["n"]
    growth = (worth - capital + paid - t["start_worth"]) * BPS // t["start_worth"] if t["start_worth"] else 0
    tasks = _one(conn, "SELECT count(*) AS n FROM empire_tasks WHERE empire_id = %s AND status = 'done' AND period >= %s",
                 (empire["id"], t["from_period"]))["n"]
    met = {"growth": growth >= t["growth_bps"], "payout": paid >= t["payout"], "tasks": tasks >= t["tasks"]}
    hit = sum(met.values())
    result = {"growth_bps": growth, "paid": paid, "tasks": tasks, "met": met, "hit": hit}
    conn.execute("UPDATE empire_strategies SET result = %s WHERE empire_id = %s AND season = %s", (firm._json(result), empire["id"], season))
    if row["set_by"]:
        firm.ceo_note(conn, row["set_by"], empire["id"], "season", f"The year's targets: {hit} of 3 met (worth {growth / 100:+.1f}%, "
                                                                   f"{_money(paid)} paid out, {tasks} tasks).", period, now, good=hit >= 2,
                      reference=f"season:{empire['id']}:{season}")


def _confidence(conn: Connection, empire: dict, period: int, now: datetime) -> None:
    """As each game year closes, the members vote on whether they still have confidence in the head."""
    if period % CONFIDENCE_EVERY or not firm.player_run(empire) or len(empires.humans(conn, empire["id"])) < 2:
        return
    head = empire["head_player_id"]
    firm.call_vote(conn, empire, "confidence", f"Do the members have confidence in {firm._name(conn, head)} as head?",
                   {"subject_id": str(head)}, period + 1, now)


def _confidence_carry(conn: Connection, empire: dict, resolution: dict, now: datetime) -> str:
    head = resolution["payload"]["subject_id"]
    firm.ceo_note(conn, head, empire["id"], "confidence", "Won the yearly vote of confidence.", resolution["period"], now, good=True,
                  reference=f"confidence:{resolution['id']}")
    return "The head keeps the members' confidence."


def _confidence_failed(conn: Connection, resolution: dict, now: datetime) -> None:
    """Lost: the head steps down, and the deputy (or the most experienced member) leads, until the members elect a head."""
    empire = empires._empire(conn, resolution["empire_id"], lock=True)
    head = resolution["payload"]["subject_id"]
    if str(empire["head_player_id"]) != str(head):
        return
    firm.ceo_note(conn, head, empire["id"], "confidence", "Lost the yearly vote of confidence and stepped down as head.", resolution["period"], now,
                  good=False, reference=f"confidence:{resolution['id']}")
    accused = {r["player_id"] for r in _rows(conn, "SELECT player_id FROM empire_cases WHERE empire_id = %s AND status = 'open'", (empire["id"],))}
    others = [h for h in empires.humans(conn, empire["id"]) if str(h["player_id"]) != str(head) and h["player_id"] not in accused]
    if not others:
        return
    named = firm.successor(conn, empire["id"], head)
    successor = next((h for h in others if h["player_id"] == named), None) or max(others, key=lambda h: h["experience"] or 0)
    # The old head keeps a seat if there is one for their build; otherwise they leave.
    conn.execute("UPDATE empires SET head_player_id = %s WHERE id = %s", (successor["player_id"], empire["id"]))
    _log(conn, empire["id"], f"The members lost confidence in the head. {successor['display_name']} became Acting Head until the members elect one."
                             f" {firm._name(conn, head)} remains a member.", now)


def scorecard(conn: Connection, empire: dict, now: datetime) -> dict:
    """The head's public scorecard: growth, members kept, audits clean, promises met."""
    head = empire["head_player_id"]
    if head is None:
        return {}
    joined = _rows(conn, "SELECT left_reason FROM empire_members WHERE empire_id = %s", (empire["id"],))
    kept = sum(1 for j in joined if j["left_reason"] is None)
    cases = _one(conn, "SELECT count(*) AS n FROM empire_cases WHERE empire_id = %s", (empire["id"],))["n"]
    seasons = _rows(conn, "SELECT season, choice, result FROM empire_strategies WHERE empire_id = %s ORDER BY season DESC LIMIT 4", (empire["id"],))
    growth = _rows(conn, "SELECT period, worth FROM empire_worth WHERE empire_id = %s ORDER BY period DESC LIMIT 5", (empire["id"],))
    change = ((growth[0]["worth"] - growth[-1]["worth"]) * BPS // growth[-1]["worth"]) if len(growth) > 1 and growth[-1]["worth"] else None
    return {"members_kept": kept, "members_ever": len(joined), "thefts_proved": cases,
            "worth_change_bps": change, "quarters": len(growth) - 1 if growth else 0,
            "seasons": [{"season": s["season"], "choice": STRATEGIES[s["choice"]], "hit": (s["result"] or {}).get("hit")} for s in seasons],
            "record": firm.ceo_record(conn, head)}


# ---------------------------------------------------------------------------
# What a member sees
# ---------------------------------------------------------------------------

def view(conn: Connection, seat: dict, empire: dict, state: dict, now: datetime) -> dict:
    me = seat["player_id"]
    is_head = empire["head_player_id"] == me
    contracts = _rows(conn, "SELECT c.*, p.display_name FROM member_contracts c JOIN players p ON p.id = c.player_id WHERE c.empire_id = %s"
                            " AND c.status IN ('drafted', 'offered', 'signed') ORDER BY c.id", (empire["id"],))
    mine = [c for c in contracts if c["player_id"] == me and c["status"] != "drafted"]
    may_see_all = is_head or seat["build"] == "investment_banker"
    approaches_in = _rows(conn, "SELECT o.*, e.name AS from_name FROM poach_offers o JOIN empires e ON e.id = o.from_empire WHERE o.player_id = %s"
                                " AND o.status IN ('open', 'matched') ORDER BY o.id", (me,))
    to_match = _rows(conn, "SELECT o.*, e.name AS from_name, p.display_name FROM poach_offers o JOIN empires e ON e.id = o.from_empire"
                           " JOIN players p ON p.id = o.player_id WHERE o.to_empire = %s AND o.status = 'open' ORDER BY o.id", (empire["id"],)) if is_head else []
    ours = _rows(conn, "SELECT o.*, p.display_name FROM poach_offers o JOIN players p ON p.id = o.player_id WHERE o.from_empire = %s"
                       " AND o.status IN ('open', 'matched') ORDER BY o.id", (empire["id"],)) if is_head else []
    apprentices = _rows(conn, "SELECT a.*, m.display_name AS mentor, p.display_name AS apprentice FROM empire_apprentices a"
                              " JOIN players m ON m.id = a.mentor_id JOIN players p ON p.id = a.apprentice_id WHERE a.empire_id = %s AND a.ended_at IS NULL",
                        (empire["id"],))
    strategy = _one(conn, "SELECT * FROM empire_strategies WHERE empire_id = %s AND season = %s", (empire["id"], leagues.season_of(state["period"])))

    def contract_public(c):
        return {"id": c["id"], "name": c["display_name"], "status": c["status"], "notice_days": c["notice_days"], "bonus_bps": c["bonus_bps"],
                "non_compete": c["non_compete"], "yours": c["player_id"] == me, "to_offer": is_head and c["status"] == "drafted"}
    others = _rows(conn, "SELECT s.id AS seat_id, s.build, p.display_name, e.name AS empire FROM empire_seats s JOIN players p ON p.id = s.player_id"
                         " JOIN empires e ON e.id = s.empire_id WHERE e.status = 'active' AND e.kind <> 'pension' AND e.id <> %s"
                         " AND (e.head_player_id IS NULL OR e.head_player_id <> s.player_id) ORDER BY e.name, s.build", (empire["id"],)) if is_head else []
    return {
        "elsewhere": [{"seat_id": o["seat_id"], "name": o["display_name"], "build_name": BUILD_NAMES[o["build"]], "empire": o["empire"]} for o in others],
        "contracts": [contract_public(c) for c in (contracts if may_see_all else mine)],
        "can_draft": seat["build"] == "investment_banker" or (is_head and not firm.desk_members(conn, empire["id"], "investment_banker")),
        "approaches": [{"id": o["id"], "from": o["from_name"], "bonus": o["bonus"], "words": o["words"], "status": o["status"],
                        "matched": o["matched"], "may_go_at": o["match_by"] if o["status"] == "open" else None} for o in approaches_in],
        "to_match": [{"id": o["id"], "from": o["from_name"], "member": o["display_name"], "bonus": o["bonus"], "match_by": o["match_by"]}
                     for o in to_match],
        "our_approaches": [{"id": o["id"], "member": o["display_name"], "bonus": o["bonus"], "status": o["status"]} for o in ours],
        "apprentices": [{"mentor": a["mentor"], "apprentice": a["apprentice"], "build": BUILD_NAMES[a["build"]],
                         "you": me in (a["mentor_id"], a["apprentice_id"])} for a in apprentices],
        "constitution": {k: firm.article(conn, empire["id"], k) for k in CONSTITUTION_DEFAULT},
        "conduct": conduct(conn, empire["id"]),
        "strategy": {"choice": strategy["choice"], "words": STRATEGIES[strategy["choice"]], "targets": strategy["targets"], "result": strategy["result"]}
        if strategy else None,
        "strategies": STRATEGIES,
        "scorecard": scorecard(conn, empire, now),
        "rules": {"match_hours": MATCH_HOURS, "apprentice_gap": APPRENTICE_GAP, "notice_most": data.NOTICE_DAYS},
    }


def _close(conn: Connection, empire: dict, period: int, now: datetime) -> None:
    if period % CONFIDENCE_EVERY == 0:
        _judge_strategy(conn, empire, period, now)
    _confidence(conn, empire, period, now)


def _bell(conn: Connection, now: datetime) -> None:
    _lapse_poaching(conn, now)


firm.VACATED.append(_vacated)
firm.DUTY_DONE.append(_duty_done)
firm.DUTY_MISSED.append(_missed)
firm.CLOSE.append(_close)
firm.BELL.append(_bell)
firm.VIEW["people"] = view
firm.FAILED["confidence"] = _confidence_failed
firm.ARTICLE_DEFAULTS.update({**CONSTITUTION_DEFAULT, "conduct": CONDUCT_DEFAULT})
firm.RESOLUTIONS.update({
    "constitution": firm.Resolution("constitution", "Change the constitution", lambda seat, head: head or seat["build"] == "investment_banker",
                                    _constitution_check, _constitution_carry,
                                    lambda p: "Change the constitution: " + ", ".join(f"{k.replace('_', ' ')} to {v}" for k, v in p.items()), big=True),
    "conduct": firm.Resolution("conduct", "Set the code of conduct", lambda seat, head: head or seat["build"] == "investment_banker",
                               _conduct_check, _conduct_carry,
                               lambda p: f"Code of conduct: theft {p['theft'].replace('_', ' ')}; a missed duty fined ₦{p['missed_duty_fine_naira']:,}"),
    "confidence": firm.Resolution("confidence", "Vote of confidence in the head", lambda seat, head: False, lambda c, e, p, n: p,
                                  _confidence_carry, lambda p: "Confidence in the head"),
})
