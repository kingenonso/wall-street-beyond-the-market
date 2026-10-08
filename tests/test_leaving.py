"""Stage 7: leagues with divisions; leaving an empire by resignation letter; the flat signing
limit; and prosecution for theft after the thief has left."""

from __future__ import annotations

from datetime import timedelta

import pytest
from psycopg.rows import dict_row

from simulation import careers, empires, leagues, ledger, quarters
from simulation import world_data as data
from simulation.money import apply_bps, naira
from tests.conftest import after_quarters
from tests.test_builds import pro
from tests.test_careers import NOW9, sound
from tests.test_empires import countersigned, always, computer_empire, founded, thief_in
from tests.test_objectives import give_cash

pytestmark = pytest.mark.world("eight")


def _dicts(db, sql, params=()):
    with db.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def seat(db, player):
    return empires.seat_of(db, player)


# ---------------------------------------------------------------------------
# The flat signing limit
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("level", [1, 4, 20])
def test_the_signing_limit_is_the_same_flat_figure_at_every_level(db, level):
    empire = computer_empire(db)
    member, _ = thief_in(db, empire, level=level)
    assert empires.war_room(db, member, NOW9)["signing_limit"] == naira(500_000) == naira(data.SIGNING_LIMIT_NAIRA)
    empires.divert(db, member, naira(500_000), NOW9)
    with pytest.raises(empires.EmpireError, match="signing limit"):
        empires.divert(db, member, 1, NOW9)


def test_a_player_run_empire_starts_at_the_same_figure_until_its_head_sets_another(db):
    empire, (head, _), partners = founded(db)
    scribe = partners["journalist"][0]
    assert empires.war_room(db, scribe, NOW9)["signing_limit"] == naira(500_000)
    assert empires.war_room(db, head, NOW9)["expense_limit"] == naira(500_000)
    empires.set_limits(db, head, expense_limit=naira(50_000))
    assert empires.war_room(db, scribe, NOW9)["signing_limit"] == naira(50_000)


# ---------------------------------------------------------------------------
# Leaving: the resignation letter
# ---------------------------------------------------------------------------

def test_in_a_player_run_empire_a_letter_starts_fourteen_real_days_of_notice(db):
    empire, (head, _), partners = founded(db)
    scribe, scribe_account = partners["journalist"]
    done = empires.resign(db, scribe, "I have had an offer I cannot refuse.", NOW9)
    assert not done["left"] and done["leaves_at"] == NOW9 + timedelta(days=14)
    assert seat(db, scribe) is not None                                         # still a member, still working
    with pytest.raises(empires.EmpireError, match="already handed in"):
        empires.resign(db, scribe, "Again.", NOW9)
    # The head is told; other members are not shown the letter.
    room = empires.war_room(db, head, NOW9)
    assert [r["name"] for r in room["resignations"]] == ["scribe"] and room["resignations"][0]["letter"].startswith("I have had")
    assert empires.badge(db, head, NOW9)["waiting"] >= 1
    other = empires.war_room(db, partners["accountant"][0], NOW9)
    assert other["resignations"] == [] and other["resignation"] is None
    assert not any(s["resigning"] for s in other["seats"])
    assert empires.war_room(db, scribe, NOW9)["resignation"]["leaves_at"] == done["leaves_at"]
    # The member keeps working through the notice: they can still do what a member does.
    empires.say(db, scribe, "Still here.", NOW9)
    # Thirteen days on, nothing has happened. On the fourteenth, the next Closing Bell carries it out.
    assert empires.run_notices(db, NOW9 + timedelta(days=13, hours=23)) == 0 and seat(db, scribe) is not None
    assert empires.run_notices(db, NOW9 + timedelta(days=14, minutes=1)) == 1
    assert seat(db, scribe) is None
    letter = _dicts(db, "SELECT status FROM empire_resignations WHERE player_id = %s", (scribe,))[0]
    assert letter["status"] == "left"
    assert _dicts(db, "SELECT left_reason FROM empire_members WHERE player_id = %s", (scribe,))[0]["left_reason"] == "left"
    sound(db)


def test_a_letter_can_be_withdrawn_and_the_head_can_let_somebody_go_early(db):
    empire, (head, _), partners = founded(db)
    scribe, ledgerman = partners["journalist"][0], partners["accountant"][0]
    empires.resign(db, scribe, "", NOW9)
    empires.withdraw_resignation(db, scribe, NOW9)
    assert empires.run_notices(db, NOW9 + timedelta(days=20)) == 0 and seat(db, scribe) is not None
    with pytest.raises(empires.EmpireError, match="no resignation letter"):
        empires.withdraw_resignation(db, scribe, NOW9)
    empires.resign(db, ledgerman, "Going.", NOW9)
    letter = empires.war_room(db, head, NOW9)["resignations"][0]["id"]
    # Only the head can release, and not a stranger's letter.
    with pytest.raises(empires.EmpireError, match="Only the head"):
        empires.release(db, scribe, letter, NOW9)
    empires.release(db, head, letter, NOW9)
    assert seat(db, ledgerman) is None
    assert _dicts(db, "SELECT status FROM empire_resignations WHERE player_id = %s", (ledgerman,))[0]["status"] == "released"


def test_the_head_can_make_a_counter_offer_and_it_is_paid_and_set_only_when_accepted(db):
    empire, (head, _), partners = founded(db)
    scribe, scribe_account = partners["journalist"]
    empires.resign(db, scribe, "The pay is too low.", NOW9)
    letter = empires.war_room(db, head, NOW9)["resignations"][0]["id"]
    worth = empires.war_room(db, head, NOW9)["worth"]
    with pytest.raises(empires.EmpireError, match="bonus may be up to"):
        empires.counter_offer(db, head, letter, worth * data.COUNTER_OFFER_MOST_BPS // 10_000 + 1, None, "", NOW9)
    for bad in (-1, 1.5, "9", True):
        with pytest.raises(empires.EmpireError):
            empires.counter_offer(db, head, letter, bad, None, "", NOW9)
    with pytest.raises(empires.EmpireError, match="needs a bonus"):
        empires.counter_offer(db, head, letter, 0, None, "", NOW9)
    # A member cannot make themselves an offer, and a member who is not the head cannot make one at all.
    with pytest.raises(empires.EmpireError, match="Only the head"):
        empires.counter_offer(db, scribe, letter, naira(1_000_000), None, "", NOW9)
    before, empire_before = ledger.balance(db, scribe_account), ledger.balance(db, empire["account_id"])
    empires.counter_offer(db, head, letter, naira(300_000), naira(900_000), "Stay: more pay and more trust.", NOW9)
    # Nothing moves until the member accepts.
    assert ledger.balance(db, scribe_account) == before
    offer = empires.war_room(db, scribe, NOW9)["resignation"]["offer"]
    assert offer["bonus"] == naira(300_000) and offer["signing_limit"] == naira(900_000) and "more trust" in offer["words"]
    took = empires.accept_offer(db, scribe, NOW9)
    assert took == {"bonus": naira(300_000), "signing_limit": naira(900_000)}
    assert ledger.balance(db, scribe_account) - before == naira(300_000) == empire_before - ledger.balance(db, empire["account_id"])
    assert empires.war_room(db, scribe, NOW9)["signing_limit"] == naira(900_000)
    assert empires.war_room(db, scribe, NOW9)["resignation"] is None
    # They stay: the notice no longer runs.
    assert empires.run_notices(db, NOW9 + timedelta(days=30)) == 0 and seat(db, scribe) is not None
    # The bonus is in the books as a bonus, and it cannot be taken twice.
    assert _dicts(db, "SELECT count(*) AS n FROM empire_books WHERE empire_id = %s AND kind = 'bonus'", (empire["id"],))[0]["n"] == 1
    with pytest.raises(empires.EmpireError, match="no offer"):
        empires.accept_offer(db, scribe, NOW9)
    sound(db)


def test_an_offer_the_empire_cannot_pay_does_not_go_through_and_the_letter_stands(db):
    empire, (head, _), partners = founded(db)
    scribe, _ = partners["journalist"]
    empires.resign(db, scribe, "", NOW9)
    letter = empires.war_room(db, head, NOW9)["resignations"][0]["id"]
    empires.counter_offer(db, head, letter, naira(500_000), None, "", NOW9)
    cash = ledger.balance(db, empire["account_id"])
    ledger.transfer(db, payer=empire["account_id"], receiver=ledger.account_id(db, ledger.TREASURY), amount=cash - naira(100),
                    kind="test", memo="Test: the empire is nearly out of cash")
    with pytest.raises(empires.EmpireError, match="has not the cash|most it may pay"):
        empires.accept_offer(db, scribe, NOW9)
    assert empires.war_room(db, scribe, NOW9)["resignation"] is not None


def test_in_a_computer_run_empire_the_member_leaves_when_the_quarter_ends(db):
    empire = computer_empire(db)
    member, _ = thief_in(db, empire)
    done = empires.resign(db, member, "Time to move on.", NOW9)
    assert not done["left"] and done["leaves_at"] is None and done["leaves_period"] == 9
    room = empires.war_room(db, member, NOW9)
    assert room["resignation"]["leaves_when_quarter_ends"] and room["resignation"]["leaves_label"] == "Year 3 Q1"
    # A Closing Bell in the same quarter does not carry it out.
    assert empires.run_notices(db, NOW9 + timedelta(days=3)) == 0 and seat(db, member) is not None
    quarters.close_due_quarters(db, after_quarters(9))
    assert seat(db, member) is None
    sound(db)


def test_a_partner_leaves_a_forming_empire_at_once_and_takes_their_money_back(db):
    empire, (head, _), partners = founded(db, open_it=False)
    scribe, scribe_account = partners["journalist"]
    empires.put_in(db, scribe, naira(80_000), 0, NOW9)
    before, pot = ledger.balance(db, scribe_account), ledger.balance(db, empire["account_id"])
    assert empires.resign(db, scribe, "", NOW9)["left"]
    assert seat(db, scribe) is None
    assert ledger.balance(db, scribe_account) - before == naira(80_000) == pot - ledger.balance(db, empire["account_id"])
    with pytest.raises(empires.EmpireError, match="Cancel the founding"):
        empires.resign(db, head, "", NOW9)
    sound(db)


def test_a_head_who_resigns_serves_the_same_notice_and_is_then_followed_by_a_successor(db):
    empire, (head, _), partners = founded(db)
    empires.resign(db, head, "Stepping down.", NOW9)
    assert empires.war_room(db, head, NOW9)["is_head"]
    assert empires.war_room(db, head, NOW9)["resignations"] == []               # a head cannot answer their own letter
    empires.run_notices(db, NOW9 + timedelta(days=15))
    assert seat(db, head) is None
    fresh = _dicts(db, "SELECT head_player_id FROM empires WHERE id = %s", (empire["id"],))[0]
    assert fresh["head_player_id"] in (partners["journalist"][0], partners["accountant"][0])


def test_being_sacked_overtakes_a_letter(db):
    empire, (head, _), partners = founded(db)
    scribe = partners["journalist"][0]
    empires.resign(db, scribe, "", NOW9)
    empires.sack(db, head, scribe, NOW9)
    assert _dicts(db, "SELECT status FROM empire_resignations WHERE player_id = %s", (scribe,))[0]["status"] == "overtaken"
    assert empires.run_notices(db, NOW9 + timedelta(days=20)) == 0


# ---------------------------------------------------------------------------
# A thief who leaves can still be prosecuted
# ---------------------------------------------------------------------------

def test_a_theft_found_after_the_thief_has_left_is_still_punished_and_their_new_seat_is_for_the_new_head_to_decide(db, monkeypatch):
    old, (old_head, _), old_partners = founded(db)
    auditor = old_partners["accountant"][0]
    thief, thief_account = thief_in(db, old, "lawyer", "mallam", cash=2_000_000)
    asked = _dicts(db, "SELECT id FROM empire_applications WHERE player_id = %s AND status = 'waiting'", (thief,))[0]["id"]
    empires.decide_application(db, old_head, asked, True, NOW9)
    countersigned(db, empires.divert(db, thief, naira(400_000), NOW9), auditor, NOW9)
    # The thief hands in a letter, is let go, and takes a seat somewhere else.
    empires.resign(db, thief, "Thank you for everything.", NOW9)
    empires.release(db, old_head, empires.war_room(db, old_head, NOW9)["resignations"][0]["id"], NOW9)
    new = computer_empire(db)
    empires.apply(db, thief, new["id"], NOW9)
    assert seat(db, thief)["empire_id"] == new["id"]
    # Moving on does not start the signing limit again.
    assert empires.war_room(db, thief, NOW9)["signing_used"] == naira(400_000)
    # The old empire's Accountant audits, and finds it.
    always(monkeypatch, True)
    audit = empires.accountant_audit(db, auditor, NOW9)
    empires.file_audit(db, auditor, audit["id"], [f["book_id"] for f in audit["findings"]], NOW9)
    case = _dicts(db, "SELECT * FROM empire_cases WHERE player_id = %s", (thief,))[0]
    assert case["status"] == "open" and case["empire_id"] == old["id"]
    before, reputation = ledger.balance(db, thief_account), _dicts(db, "SELECT reputation FROM players WHERE id = %s", (thief,))[0]["reputation"]
    empires.decide_case(db, old_head, case["id"], True, NOW9)
    # Repaid with the fine, reputation lost, on the legal record: all of it, though they are no longer a member.
    assert before - ledger.balance(db, thief_account) == naira(800_000)
    assert _dicts(db, "SELECT reputation FROM players WHERE id = %s", (thief,))[0]["reputation"] == reputation - data.THEFT_REPUTATION
    record = _dicts(db, "SELECT words FROM legal_records WHERE player_id = %s", (thief,))
    assert len(record) == 1 and "Lagoon House" in record[0]["words"]
    # The new seat is not lost automatically.
    assert seat(db, thief)["empire_id"] == new["id"]
    # The old empire will not have them back for a game year.
    empires.leave(db, thief, NOW9)
    with pytest.raises(empires.EmpireError, match="will not have you back"):
        empires.apply(db, thief, old["id"], NOW9)
    sound(db)


def test_a_new_head_sees_the_legal_record_and_decides(db, monkeypatch):
    old = computer_empire(db)
    thief, _ = thief_in(db, old, "lawyer", "mallam", cash=2_000_000)
    empires.divert(db, thief, naira(300_000), NOW9)
    empires.leave(db, thief, NOW9)
    new, (new_head, _), partners = founded(db)
    empires.apply(db, thief, new["id"], NOW9)
    # Before the theft is proved the record is clean: an unproved crime leaves no mark.
    room = empires.war_room(db, new_head, NOW9)
    assert room["applications"][0]["legal"] == []
    empires.decide_application(db, new_head, room["applications"][0]["id"], True, NOW9)
    # The old empire's staff audit as the quarter closes, and prove it. A computer-run empire punishes at once.
    always(monkeypatch, True)
    quarters.close_due_quarters(db, after_quarters(9))
    now = after_quarters(9) + timedelta(hours=12)
    assert _dicts(db, "SELECT status FROM empire_cases WHERE player_id = %s", (thief,))[0]["status"] == "punished"
    assert seat(db, thief)["empire_id"] == new["id"]                           # still in the new empire
    room = empires.war_room(db, new_head, now)
    held = next(s for s in room["seats"] if s["name"] == "mallam")
    assert len(held["legal"]) == 1 and "Savannah Crown Holdings" in held["legal"][0]["words"]
    # A colleague who is not the head is not shown it.
    mate = empires.war_room(db, partners["accountant"][0], now)
    assert next(s for s in mate["seats"] if s["name"] == "mallam")["legal"] == []
    # The head decides: here, to remove them.
    empires.sack(db, new_head, thief, now)
    assert seat(db, thief) is None


# ---------------------------------------------------------------------------
# Leagues
# ---------------------------------------------------------------------------

def test_the_five_computer_run_empires_fill_division_one_and_a_new_empire_enters_below(db):
    table = leagues.table(db, NOW9)
    assert [d["division"] for d in table] == [1] and len(table[0]["empires"]) == data.DIVISION_SIZE == 5
    empire, (head, _), _ = founded(db)
    table = leagues.table(db, NOW9)
    assert [d["division"] for d in table] == [1, 2] and [e["name"] for e in table[1]["empires"]] == ["Lagoon House"]
    assert empires.war_room(db, head, NOW9)["division"]["division"] == 2
    assert empires.directory(db, head, NOW9)["divisions"][1]["empires"][0]["yours"]


def test_points_are_counted_once_and_the_top_goes_up_and_the_bottom_goes_down_as_the_year_ends(db):
    empire, (head, _), _ = founded(db)
    assert leagues.award(db, empire["id"], 10, "A task finished", 9, NOW9, reference="task:1")
    assert not leagues.award(db, empire["id"], 10, "A task finished", 9, NOW9, reference="task:1")
    assert leagues.standing(db, empire["id"], NOW9)["points"] == 10
    bottom = leagues.table(db, NOW9)[0]["empires"][-1]
    # The game year ends when quarter twelve closes.
    for n in (9, 10, 11):
        assert quarters.close_due_quarters(db, after_quarters(n)) == [n]
        assert leagues.table(db, after_quarters(n))[1]["empires"][0]["division"] == 2
    bottom = leagues.table(db, after_quarters(11) + timedelta(days=6))[0]["empires"][-1]
    assert bottom["zone"] == "down" and leagues.table(db, after_quarters(11))[1]["empires"][0]["zone"] == "up"
    quarters.close_due_quarters(db, after_quarters(12))
    now = after_quarters(12) + timedelta(hours=12)
    table = leagues.table(db, now)
    assert "Lagoon House" in [e["name"] for e in table[0]["empires"]]
    assert [e["name"] for e in table[1]["empires"]] == [bottom["name"]]
    season = _dicts(db, "SELECT e.name, s.moved, s.division FROM league_seasons s JOIN empires e ON e.id = s.empire_id WHERE s.season = 3")
    assert {r["name"]: r["moved"] for r in season}["Lagoon House"] == "up" and {r["name"]: r["moved"] for r in season}[bottom["name"]] == "down"
    assert len(season) == 6 and sum(1 for r in season if r["moved"] == "stayed") == 4
    # A new game year starts everybody from nought.
    assert all(e["points"] == 0 for d in table for e in d["empires"])
    # It is counted once, however often the close is looked at again.
    assert leagues.end_season(db, 12, now) == []
    sound(db)


def test_growth_is_measured_with_money_put_in_by_members_left_out(db):
    empire, (head, account), _ = founded(db)
    quarters.close_due_quarters(db, after_quarters(9))
    now = after_quarters(9) + timedelta(hours=12)
    give_cash(db, account, 500_000_000)
    empires.put_in(db, head, naira(400_000_000), 0, now)                     # the empire is suddenly worth many times more...
    for n in (10, 11, 12):
        quarters.close_due_quarters(db, after_quarters(n))
    growth = _dicts(db, "SELECT points, why FROM league_points WHERE empire_id = %s AND reference = 'growth:3'", (empire["id"],))
    worth = {r["period"]: r["worth"] for r in _dicts(db, "SELECT period, worth FROM empire_worth WHERE empire_id = %s", (empire["id"],))}
    assert worth[12] > 5 * worth[9]
    assert sum(g["points"] for g in growth) <= 5                            # ...and gains nothing in the league for it


def test_every_player_is_ranked_within_their_build(db):
    top, _ = pro(db, "lawyer", "top", level=12)
    low, _ = pro(db, "lawyer", "low", level=3)
    pro(db, "journalist", "elsewhere", level=19)
    table = leagues.build_table(db, "lawyer", low)
    assert [(p["name"], p["place"]) for p in table["top"]] == [("top", 1), ("low", 2)] and table["your_place"] == 2
    assert table["top"][1]["you"] and "id" not in table["top"][0]


# ---------------------------------------------------------------------------
# Trading for a computer-run empire: a share of the empire that grows with rank (the owner, 3 October 2026)
# ---------------------------------------------------------------------------

def test_what_an_asset_manager_may_trade_for_a_computer_run_empire_grows_with_rank(db):
    from simulation import bonds
    assert data.COMPUTER_EMPIRE_TRADE_BPS == (50, 200, 500, 1000, 2000)
    empire = computer_empire(db)
    manager, _ = pro(db, "asset_manager", "dealer", level=4)
    empires.apply(db, manager, empire["id"], NOW9)
    worth = empires.war_room(db, manager, NOW9)["worth"]
    for rank, share in enumerate(data.COMPUTER_EMPIRE_TRADE_BPS):
        db.execute("UPDATE careers SET rank = %s WHERE player_id = %s", (rank, manager))
        assert empires.war_room(db, manager, NOW9)["trade_limit"] == apply_bps(worth, share)
    # Level alone changes nothing: it is the rank that counts.
    db.execute("UPDATE careers SET rank = 0, experience = %s WHERE player_id = %s", (careers.experience_for(20), manager))
    limit = empires.war_room(db, manager, NOW9)["trade_limit"]
    assert limit == apply_bps(worth, 50)
    # The limit holds, and it is the player's for the quarter wherever they sit.
    bill = next(b for b in bonds.listing(db, NOW9) if b["kind"] == "bill")
    units = limit // bill["ask"]
    empires.trade_bonds(db, manager, code=bill["code"], side="buy", units=units, now=NOW9)
    with pytest.raises(empires.EmpireError, match="trading limit"):
        empires.trade_bonds(db, manager, code=bill["code"], side="buy", units=units, now=NOW9)
    empires.leave(db, manager, NOW9)
    other = computer_empire(db, 1)
    empires.apply(db, manager, other["id"], NOW9)
    assert empires.war_room(db, manager, NOW9)["trade_used"] >= units * bill["bid"]
    with pytest.raises(empires.EmpireError, match="trading limit"):
        empires.trade_bonds(db, manager, code=bill["code"], side="buy", units=units, now=NOW9)
    # In an empire run by players the head still sets it.
    house, (head, _), _ = founded(db)
    empires.set_limits(db, head, trade_limit_bps=1000)
    assert empires.war_room(db, head, NOW9)["trade_limit"] == empires.war_room(db, head, NOW9)["worth"] // 10
    sound(db)
