"""Stage 6: empires, the chain of command, tasks that need every build, the shadow feature,
audits and their consequences, secret pacts, and the War Room."""

from __future__ import annotations

from datetime import timedelta

import pytest
from psycopg.rows import dict_row

from simulation import bonds, careers, empires, exchange, ledger, marketview, objectives, quarters
from simulation import world_data as data
from simulation.money import apply_bps, naira
from tests.conftest import after_quarters
from tests.test_builds import pro, right_answers
from tests.test_careers import NOW9, sound
from tests.test_objectives import bell, give_cash, give_shares, state_of

pytestmark = pytest.mark.world("eight")


def _dicts(db, sql, params=()):
    with db.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def computer_empire(db, index=0) -> dict:
    return _dicts(db, "SELECT * FROM empires WHERE kind = 'computer' ORDER BY id")[index]


def founded(db, *, open_it=True, cash=60_000_000, put_in=40_000_000):
    """An empire founded by a Level 20 Asset Manager with a Journalist and an Accountant as partners."""
    head, head_account = pro(db, "asset_manager", "chief", level=20, cash_naira=cash)
    empire = empires.found(db, head, "Lagoon House", naira(put_in), 0, NOW9)
    partners = {}
    for build, name in (("journalist", "scribe"), ("accountant", "ledgerman")):
        player, account = pro(db, build, name, level=4, cash_naira=100_000)
        assert empires.apply(db, player, empire["id"], NOW9)["status"] == "waiting"
        asked = _dicts(db, "SELECT id FROM empire_applications WHERE player_id = %s AND status = 'waiting'", (player,))[0]["id"]
        empires.decide_application(db, head, asked, True, NOW9)
        partners[build] = (player, account)
    if open_it:
        empire = empires.open_empire(db, head, NOW9)
    return empire, (head, head_account), partners


def always(monkeypatch, found: bool):
    """Make every draw of chance come out one way, so that a test does not hang on luck."""
    monkeypatch.setattr(empires, "_roll", lambda conn, *parts: 0 if found else 9999)


def ratios(db, objective_id) -> dict:
    terms = state_of(db, objective_id)["terms"]
    figures = _dicts(db, "SELECT figures FROM company_reports WHERE company_id = %s AND period = %s ORDER BY version DESC LIMIT 1",
                     (terms["company_id"], terms["filed_period"]))[0]["figures"]
    income, sheet = figures["income_statement"], figures["balance_sheet"]
    ebitda = income["operating_profit"] + income["depreciation"]
    return {"ebitda": ebitda / 1e8, "margin": income["net_profit"] / income["revenue"] * 100,
            "debt_to_ebitda": sheet["borrowings"] / (4 * ebitda), "interest_cover": income["operating_profit"] / income["interest_expense"]}


# ---------------------------------------------------------------------------
# The five empires the computer runs
# ---------------------------------------------------------------------------

def test_five_empires_exist_from_the_first_day_with_thirteen_places_and_money_that_was_moved_not_made(db):
    made = _dicts(db, "SELECT * FROM empires WHERE kind = 'computer' ORDER BY id")
    assert [e["name"] for e in made] == list(data.COMPUTER_EMPIRES)
    for empire in made:
        seats = _dicts(db, "SELECT build, slot, staffed, player_id FROM empire_seats WHERE empire_id = %s", (empire["id"],))
        assert len(seats) == 12 and {s["build"] for s in seats} == set(data.EMPIRE_BUILDS)            # and the head makes thirteen
        assert all(s["staffed"] and s["player_id"] is None for s in seats)
        assert empire["head_player_id"] is None and empire["status"] == "active"
        assert empires.worth(db, empire, NOW9)["total"] > naira(1_000_000_000)
    # Setting up twice changes nothing.
    empires.setup(db, NOW9)
    assert len(_dicts(db, "SELECT 1 FROM empires")) == 5
    sound(db)


def test_staff_are_paid_by_the_empire_each_quarter_and_the_computer_puts_idle_cash_to_work(db):
    empire = computer_empire(db)
    paid = _dicts(db, "SELECT period, amount FROM empire_books WHERE empire_id = %s AND category = 'Staff pay' ORDER BY period", (empire["id"],))
    assert len(paid) >= 7
    wage = _dicts(db, "SELECT wage_index_bps FROM economy_results WHERE period = 8")[0]["wage_index_bps"]
    assert paid[-1]["amount"] == 12 * careers.salary_per_quarter(data.STAFF_LEVEL, wage)
    have = empires.worth(db, empire, NOW9)
    assert have["bonds"] > have["cash"] > 0
    # And each has an investment task in hand, or has finished one.
    assert _dicts(db, "SELECT 1 FROM empire_tasks WHERE empire_id = %s", (empire["id"],))


def test_a_player_can_join_a_computer_run_empire_at_once_and_holds_one_seat_only(db):
    empire, other = computer_empire(db, 0), computer_empire(db, 1)
    ada, _ = pro(db, "accountant", "ada")
    assert empires.apply(db, ada, empire["id"], NOW9)["status"] == "accepted"
    assert empires.seat_of(db, ada)["empire_id"] == empire["id"]
    with pytest.raises(empires.EmpireError, match="already hold a seat"):
        empires.apply(db, ada, other["id"], NOW9)
    ben, _ = pro(db, "accountant", "ben")
    cy, _ = pro(db, "accountant", "cy")
    empires.apply(db, ben, empire["id"], NOW9)
    with pytest.raises(empires.EmpireError, match="held by players"):
        empires.apply(db, cy, empire["id"], NOW9)
    # The database itself refuses a second seat.
    with pytest.raises(Exception):
        db.execute("UPDATE empire_seats SET player_id = %s WHERE empire_id = %s AND build = 'lawyer' AND slot = 1", (ada, other["id"]))
    empires.leave(db, ada, NOW9)
    assert empires.seat_of(db, ada) is None
    assert empires.apply(db, cy, empire["id"], NOW9)["status"] == "accepted"
    # Somebody without a build, or with a poor reputation, is not taken.
    db.execute("UPDATE players SET reputation = 10 WHERE id = %s", (ada,))
    with pytest.raises(empires.EmpireError, match="reputation"):
        empires.apply(db, ada, other["id"], NOW9)


# ---------------------------------------------------------------------------
# Founding
# ---------------------------------------------------------------------------

def test_founding_needs_level_twenty_three_players_and_the_fee_which_goes_to_the_prize_pool(db):
    junior, _ = pro(db, "asset_manager", "junior", level=19, cash_naira=60_000_000)
    with pytest.raises(empires.EmpireError, match="Level 20"):
        empires.found(db, junior, "Too Soon", naira(30_000_000), 0, NOW9)
    company = _dicts(db, "SELECT name FROM companies ORDER BY ticker LIMIT 1")[0]["name"]
    for index, name in enumerate(("Savannah Crown holdings", "Central Bank Group", "x", company.upper())):
        with pytest.raises(empires.EmpireError):
            empires.found(db, pro(db, "lawyer", f"l{index}", level=20, cash_naira=1_000_000)[0], name, naira(1_000), 0, NOW9)
    empire, (head, head_account), partners = founded(db, open_it=False, put_in=20_000_000)
    assert empire["status"] == "forming"
    with pytest.raises(empires.EmpireError, match="registration fee"):
        empires.open_empire(db, head, NOW9)
    # A partner pools money; then it opens.
    scribe, scribe_account = partners["journalist"]
    give_cash(db, scribe_account, 6_000_000)
    empires.put_in(db, scribe, naira(6_000_000), 0, NOW9)
    pool = ledger.balance(db, ledger.account_id(db, ledger.PRIZE_POOL))
    opened = empires.open_empire(db, head, NOW9)
    assert opened["status"] == "active"
    assert ledger.balance(db, ledger.account_id(db, ledger.PRIZE_POOL)) == pool + naira(data.EMPIRE_REGISTRATION_NAIRA)
    assert ledger.balance(db, opened["account_id"]) == naira(1_000_000)
    with pytest.raises(empires.EmpireError):
        empires.open_empire(db, head, NOW9)
    sound(db)


def test_an_empire_with_fewer_than_three_players_cannot_open_and_cancelling_hands_every_naira_back(db):
    head, head_account = pro(db, "asset_manager", "chief", level=20, cash_naira=60_000_000)
    before = ledger.balance(db, head_account)
    empires.found(db, head, "Lagoon House", naira(40_000_000), 0, NOW9)
    with pytest.raises(empires.EmpireError, match="at least 3 players"):
        empires.open_empire(db, head, NOW9)
    with pytest.raises(empires.EmpireError, match="Cancel the founding"):
        empires.leave(db, head, NOW9)
    empires.cancel_founding(db, head, NOW9)
    assert ledger.balance(db, head_account) == before and empires.seat_of(db, head) is None
    sound(db)


def test_the_founder_is_acting_head_with_capped_powers(db):
    empire, (head, head_account), partners = founded(db)
    room = empires.war_room(db, head, NOW9)
    assert room["is_head"] and room["humans"] == 3
    # A head cannot pay themselves a bonus, and cannot spend more than a small part of the empire alone.
    with pytest.raises(empires.EmpireError, match="cannot pay themselves"):
        empires.pay_bonus(db, head, head, naira(1_000), "for me", NOW9)
    cash = ledger.balance(db, empire["account_id"])
    assert room["signing_limit"] == apply_bps(cash, data.HEAD_LIMIT_BPS)
    with pytest.raises(empires.EmpireError, match="signing limit"):
        empires.divert(db, head, room["signing_limit"] + 1, NOW9)
    # Only the head decides: a member cannot.
    scribe, _ = partners["journalist"]
    for attempt in (lambda: empires.set_limits(db, scribe, expense_limit=naira(1)),
                    lambda: empires.pay_bonus(db, scribe, head, naira(1), "x", NOW9),
                    lambda: empires.sack(db, scribe, head, NOW9),
                    lambda: empires.start_task(db, scribe, NOW9),
                    lambda: empires.staff_seat(db, scribe, "lawyer", 1, True, NOW9)):
        with pytest.raises(empires.EmpireError, match="Only the head"):
            attempt()
    # The head pays a bonus out of the empire's cash, and it is in the books.
    empires.pay_bonus(db, head, scribe, naira(50_000), "A good story", NOW9)
    assert _dicts(db, "SELECT category FROM empire_books WHERE empire_id = %s", (empire["id"],))[0]["category"] == "Bonuses"
    # If the head leaves, the most experienced member becomes Acting Head.
    empires.leave(db, head, NOW9)
    assert _dicts(db, "SELECT head_player_id FROM empires WHERE id = %s", (empire["id"],))[0]["head_player_id"] in {p for p, _ in partners.values()}
    sound(db)


# ---------------------------------------------------------------------------
# The stage test
# ---------------------------------------------------------------------------

def test_an_empire_of_three_humans_plus_staff_completes_a_task_that_needs_five_builds(db):
    empire, (head, _), partners = founded(db)
    scribe, ledgerman = partners["journalist"][0], partners["accountant"][0]
    for build in ("investment_banker", "risk_manager", "lawyer"):
        empires.staff_seat(db, head, build, 1, True, NOW9)
    task = empires.start_task(db, head, NOW9)
    with pytest.raises(empires.EmpireError, match="already has a task"):
        empires.start_task(db, head, NOW9)

    def step(player):
        steps = empires.war_room(db, player, NOW9)["task"]["steps"]
        return next(s for s in steps if s["status"] == "current")

    # A step cannot be taken out of turn, or by the wrong build.
    with pytest.raises(empires.EmpireError, match="falls to a Journalist"):
        empires.take_step(db, ledgerman, step(ledgerman)["id"], NOW9)
    # 1. The Journalist researches the company the server chose.
    taken = empires.take_step(db, scribe, step(scribe)["id"], NOW9)
    assert state_of(db, taken["id"])["client_company_id"] == task["company_id"] and taken["payer"] == "Lagoon House"
    cash = ledger.balance(db, empire["account_id"])
    assert objectives.submit(db, scribe, taken["id"], right_answers(db, taken["id"]), NOW9)["state"] == "passed"
    assert ledger.balance(db, empire["account_id"]) == cash - taken["reward"]              # the empire pays for its own work
    # 2. The Accountant reviews its accounts.
    assert step(ledgerman)["build"] == "accountant" and step(ledgerman)["yours_to_take"]
    taken = empires.take_step(db, ledgerman, step(ledgerman)["id"], NOW9)
    assert objectives.submit(db, ledgerman, taken["id"], ratios(db, taken["id"]), NOW9)["state"] == "passed"
    # 3 to 5. Nobody holds the Investment Banker, Risk Manager or Lawyer seats: the staff do those steps, one each working day.
    for build in ("investment_banker", "risk_manager", "lawyer"):
        assert step(head)["build"] == build
        empires.tick(db, NOW9)
    # 6. The head approves.
    waiting = step(head)
    assert waiting["build"] == "head" and waiting["yours_to_approve"]
    with pytest.raises(empires.EmpireError, match="Only the head"):
        empires.approve_step(db, scribe, waiting["id"], NOW9)
    empires.approve_step(db, head, waiting["id"], NOW9)
    # 7. The Asset Manager buys, with the empire's money.
    taken = empires.take_step(db, head, step(head)["id"], NOW9)
    need = state_of(db, taken["id"])["terms"]["need"]
    ticker = _dicts(db, "SELECT ticker FROM companies WHERE id = %s", (task["company_id"],))[0]["ticker"]
    give_shares(db, empire["account_id"], ticker, 0)                         # a first share, to show the count is of new shares
    price = next(s["price"] for s in marketview._shares(db, exchange.session_of(NOW9)[0]) if s["ticker"] == ticker)
    ledger.transfer(db, payer=ledger.account_id(db, ledger.INVESTORS_PUBLIC), receiver=empire["account_id"], amount=need,
                    asset=f"SHR-{ticker}", kind="test_shares", memo="Test: the purchase, completed")
    ledger.transfer(db, payer=empire["account_id"], receiver=ledger.account_id(db, ledger.INVESTORS_PUBLIC), amount=need * price,
                    kind="test_cash", memo="Test: the purchase, paid for")
    bell(db, 1)
    done = _dicts(db, "SELECT * FROM empire_tasks WHERE id = %s", (task["id"],))[0]
    assert done["status"] == "done"
    steps = _dicts(db, "SELECT build, done_by, done_by_staff FROM empire_task_steps WHERE task_id = %s ORDER BY position", (task["id"],))
    assert len({s["build"] for s in steps} - {"head"}) == 6 >= 5
    assert {s["done_by"] for s in steps if s["done_by"]} == {head, scribe, ledgerman}
    assert [s["build"] for s in steps if s["done_by_staff"]] == ["investment_banker", "risk_manager", "lawyer"]
    log = " ".join(e["words"] for e in empires.war_room(db, head, NOW9)["events"])
    assert "The task is complete" in log and "Handed on" in log
    # One task a quarter: finished work cannot be started again for the experience.
    with pytest.raises(empires.EmpireError, match="One task a quarter"):
        empires.start_task(db, head, NOW9)
    sound(db)


def test_a_step_can_be_tried_once_and_a_failed_step_goes_to_a_colleague_or_the_staff(db):
    empire, (head, _), partners = founded(db)
    scribe = partners["journalist"][0]
    empires.start_task(db, head, NOW9)
    first = empires.war_room(db, scribe, NOW9)["task"]["steps"][0]
    taken = empires.take_step(db, scribe, first["id"], NOW9)
    assert objectives.submit(db, scribe, taken["id"], {}, NOW9)["state"] == "failed"
    # They have now seen the answers. They cannot take the same step again.
    with pytest.raises(empires.EmpireError, match="already tried"):
        empires.take_step(db, scribe, first["id"], NOW9)
    # With nobody else in the seat and no staff, the step waits: the head must recruit or hire.
    empires.tick(db, NOW9)
    assert empires.war_room(db, head, NOW9)["task"]["steps"][0]["status"] == "current"
    empires.staff_seat(db, head, "journalist", 2, True, NOW9)
    empires.tick(db, NOW9)
    steps = empires.war_room(db, head, NOW9)["task"]["steps"]
    assert steps[0]["status"] == "done" and steps[0]["done_by"] == "The staff"
    # A step taken as part of a task does not use up the player's own piece of that work for the quarter.
    assert objectives.accept(db, scribe, "jr_results", NOW9)["state"] == "active"


def test_work_that_exists_only_inside_an_empire_is_never_on_the_ordinary_board(db):
    manager, _ = pro(db, "asset_manager", "solo")
    assert "em_execute" not in {o["template"] for o in objectives.board(db, manager, NOW9)["offers"]}
    with pytest.raises(objectives.ObjectiveError):
        objectives.accept(db, manager, "em_execute", NOW9)


# ---------------------------------------------------------------------------
# Trading the empire's money
# ---------------------------------------------------------------------------

def test_asset_managers_trade_the_empires_money_within_the_limit_the_head_set(db):
    empire, (head, _), partners = founded(db)
    scribe = partners["journalist"][0]
    bill = next(b for b in bonds.listing(db, NOW9) if b["kind"] == "bill")
    with pytest.raises(empires.EmpireError, match="Only the empire's Asset Managers"):
        empires.trade_bonds(db, scribe, code=bill["code"], side="buy", units=1, now=NOW9)
    trader, trader_account = pro(db, "asset_manager", "dealer", level=4)
    with pytest.raises(empires.EmpireError, match="no seat"):
        empires.trade_bonds(db, trader, code=bill["code"], side="buy", units=1, now=NOW9)
    asked = empires.apply(db, trader, empire["id"], NOW9)
    assert asked["status"] == "waiting"
    empires.decide_application(db, head, _dicts(db, "SELECT id FROM empire_applications WHERE status = 'waiting'")[0]["id"], True, NOW9)
    empires.set_limits(db, head, trade_limit_bps=1000)
    own = ledger.balance(db, trader_account)
    cash = ledger.balance(db, empire["account_id"])
    done = empires.trade_bonds(db, trader, code=bill["code"], side="buy", units=5, now=NOW9)
    assert ledger.balance(db, empire["account_id"]) == cash - done["value"] and ledger.balance(db, trader_account) == own
    assert empires.war_room(db, trader, NOW9)["bond_holdings"][0]["units"] == 5
    with pytest.raises(empires.EmpireError, match="trading limit"):
        empires.trade_bonds(db, trader, code=bill["code"], side="buy", units=10_000, now=NOW9)
    sound(db)


# ---------------------------------------------------------------------------
# The shadow feature, audits, and what follows
# ---------------------------------------------------------------------------

def thief_in(db, empire, build="lawyer", name="mallam", level=4, cash=0):
    player, account = pro(db, build, name, level=level, cash_naira=cash)
    empires.apply(db, player, empire["id"], NOW9)
    return player, account


def test_a_member_can_take_the_empires_money_disguised_in_its_books_within_their_signing_limit(db):
    empire = computer_empire(db)
    thief, account = thief_in(db, empire)
    before, empire_before = ledger.balance(db, account), ledger.balance(db, empire["account_id"])
    limit = naira(data.COMPUTER_EMPIRE_LIMIT_NAIRA) * 4
    assert empires.war_room(db, thief, NOW9)["signing_limit"] == limit
    taken = empires.divert(db, thief, naira(300_000), NOW9)
    assert taken["category"] == "Legal fees and filings"
    assert ledger.balance(db, account) == before + naira(300_000)
    assert ledger.balance(db, empire["account_id"]) == empire_before - naira(300_000)
    with pytest.raises(empires.EmpireError, match="signing limit"):
        empires.divert(db, thief, naira(100_001), NOW9)
    for bad in (0, -5, 1.5, "9"):
        with pytest.raises(empires.EmpireError):
            empires.divert(db, thief, bad, NOW9)
    # Each build writes it its own way.
    assert len({v[0] for v in data.DISGUISES.values()}) == 7
    # A colleague sees the entry, but not who made it or whether it is genuine.
    mate, _ = thief_in(db, empire, "accountant", "mate")
    room = empires.war_room(db, mate, NOW9)
    entry = next(b for b in room["books"] if b["amount"] == naira(300_000))
    assert set(entry) == {"id", "period", "category", "description", "amount", "found"} and room["your_entries"] == []
    assert "mallam" not in str(room["books"]) and str(thief) not in str(room["books"]) and "genuine" not in str(room)
    assert empires.war_room(db, thief, NOW9)["your_entries"][0]["amount"] == naira(300_000)
    # Somebody outside the empire cannot touch its money at all.
    outsider, _ = pro(db, "lawyer", "outsider")
    with pytest.raises(empires.EmpireError, match="no seat"):
        empires.divert(db, outsider, naira(1), NOW9)
    sound(db)


def test_an_accountants_audit_finds_it_and_the_thief_repays_with_a_fine_is_sacked_and_loses_reputation(db, monkeypatch):
    empire = computer_empire(db)
    thief, account = thief_in(db, empire, cash=1_000_000)
    auditor, _ = thief_in(db, empire, "accountant", "auditor", level=10)
    empires.divert(db, thief, naira(300_000), NOW9)
    with pytest.raises(empires.EmpireError, match="Only an Accountant"):
        empires.accountant_audit(db, thief, NOW9)
    always(monkeypatch, True)
    audit = empires.accountant_audit(db, auditor, NOW9)
    assert [f["amount"] for f in audit["findings"]] == [naira(300_000)]
    with pytest.raises(empires.EmpireError, match="already audited"):
        empires.accountant_audit(db, auditor, NOW9)
    before, empire_before = ledger.balance(db, account), ledger.balance(db, empire["account_id"])
    reputation = _dicts(db, "SELECT reputation FROM players WHERE id = %s", (thief,))[0]["reputation"]
    empires.file_audit(db, auditor, audit["id"], [f["book_id"] for f in audit["findings"]], NOW9)
    # In an empire the computer runs, the consequences follow at once: repaid, with a fine of the same again.
    assert ledger.balance(db, account) == before - naira(600_000)
    assert ledger.balance(db, empire["account_id"]) == empire_before + naira(600_000)
    assert empires.seat_of(db, thief) is None
    assert _dicts(db, "SELECT reputation FROM players WHERE id = %s", (thief,))[0]["reputation"] == reputation - data.THEFT_REPUTATION
    assert _dicts(db, "SELECT kind FROM legal_records WHERE player_id = %s", (thief,)) == [{"kind": "theft"}]
    with pytest.raises(empires.EmpireError, match="sacked you"):
        empires.apply(db, thief, empire["id"], NOW9)
    # The same entry cannot be proved, or punished, twice.
    assert len(_dicts(db, "SELECT 1 FROM empire_cases")) == 1
    with pytest.raises(empires.EmpireError):
        empires.file_audit(db, auditor, audit["id"], [], NOW9)
    sound(db)


def test_an_auditor_can_look_away_and_a_weak_audit_can_miss_it(db, monkeypatch):
    empire = computer_empire(db)
    thief, _ = thief_in(db, empire)
    auditor, _ = thief_in(db, empire, "accountant", "auditor")
    empires.divert(db, thief, naira(100_000), NOW9)
    always(monkeypatch, True)
    audit = empires.accountant_audit(db, auditor, NOW9)
    empires.file_audit(db, auditor, audit["id"], [], NOW9)                    # found it, and left it out of the report
    assert empires.seat_of(db, thief) is not None and not _dicts(db, "SELECT 1 FROM empire_cases")
    # An entry cannot be put in a report unless the audit found it.
    genuine = _dicts(db, "SELECT id FROM empire_books WHERE empire_id = %s AND genuine LIMIT 1", (empire["id"],))[0]["id"]
    other = thief_in(db, computer_empire(db, 1), "accountant", "other")[0]
    audit2 = empires.accountant_audit(db, other, NOW9)
    empires.file_audit(db, other, audit2["id"], [genuine], NOW9)
    assert not _dicts(db, "SELECT 1 FROM empire_cases")
    # How much an audit finds depends on the auditor's level against the thief's.
    assert empires._auditor_finds_bps(1, 1) == 5000 and empires._auditor_finds_bps(20, 1) == 9000 and empires._auditor_finds_bps(1, 20) == 2000


def test_in_a_players_empire_the_head_decides_what_follows(db, monkeypatch):
    empire, (head, _), partners = founded(db)
    scribe, scribe_account = partners["journalist"]
    ledgerman = partners["accountant"][0]
    empires.set_limits(db, head, expense_limit=naira(500_000))
    empires.set_limits(db, head, member_id=scribe, signing_limit=naira(200_000))
    with pytest.raises(empires.EmpireError, match="signing limit"):
        empires.divert(db, scribe, naira(200_001), NOW9)
    empires.divert(db, scribe, naira(150_000), NOW9)
    empires.divert(db, ledgerman, naira(400_000), NOW9)
    always(monkeypatch, True)
    audit = empires.accountant_audit(db, ledgerman, NOW9)
    assert {f["yours"] for f in audit["findings"]} == {True, False}
    mine = [f["book_id"] for f in audit["findings"] if not f["yours"]]
    empires.file_audit(db, ledgerman, audit["id"], mine, NOW9)                # the auditor reports the other thief, and not themselves
    cases = empires.war_room(db, head, NOW9)["cases"]
    assert len(cases) == 1 and cases[0]["status"] == "open" and cases[0]["who"] == "scribe"
    assert empires.seat_of(db, scribe) is not None
    with pytest.raises(empires.EmpireError, match="Only the head"):
        empires.decide_case(db, scribe, cases[0]["id"], False, NOW9)
    before = ledger.balance(db, scribe_account)
    empires.decide_case(db, head, cases[0]["id"], True, NOW9)
    # The thief had too little cash: what they had was taken, and the rest is a debt against their salary.
    case = _dicts(db, "SELECT * FROM empire_cases")[0]
    assert case["repaid"] == before and case["debt_left"] == naira(300_000) - before > 0 and ledger.balance(db, scribe_account) == 0
    assert empires.seat_of(db, scribe) is None
    # On pay day a quarter of take-home pay goes to the empire, until the debt is cleared.
    give_cash(db, scribe_account, 400_000)
    empire_cash = ledger.balance(db, empire["account_id"])
    empires.collect_debts(db, scribe, scribe_account, naira(100_000), 9)                 # a quarter of ₦100,000 is ₦25,000
    assert ledger.balance(db, empire["account_id"]) == empire_cash + naira(25_000)
    assert _dicts(db, "SELECT debt_left FROM empire_cases")[0]["debt_left"] == case["debt_left"] - naira(25_000) == naira(25_000)
    empires.collect_debts(db, scribe, scribe_account, naira(400_000), 9)                 # and never more than is owed
    assert ledger.balance(db, empire["account_id"]) == empire_cash + naira(50_000)
    assert _dicts(db, "SELECT debt_left FROM empire_cases")[0]["debt_left"] == 0
    with pytest.raises(empires.EmpireError):
        empires.decide_case(db, head, case["id"], True, NOW9)
    sound(db)


def test_the_head_may_forgive_and_a_head_who_steals_is_dealt_with_without_being_asked(db, monkeypatch):
    empire, (head, head_account), partners = founded(db)
    ledgerman = partners["accountant"][0]
    scribe = partners["journalist"][0]
    empires.set_limits(db, head, expense_limit=naira(500_000))
    empires.divert(db, scribe, naira(100_000), NOW9)
    empires.divert(db, head, naira(200_000), NOW9)
    always(monkeypatch, True)
    audit = empires.accountant_audit(db, ledgerman, NOW9)
    empires.file_audit(db, ledgerman, audit["id"], [f["book_id"] for f in audit["findings"]], NOW9)
    cases = {c["amount"]: c for c in _dicts(db, "SELECT * FROM empire_cases")}
    # The head's own theft was not left for the head to decide.
    assert cases[naira(200_000)]["status"] == "punished" and empires.seat_of(db, head) is None
    new_head = _dicts(db, "SELECT head_player_id FROM empires WHERE id = %s", (empire["id"],))[0]["head_player_id"]
    assert new_head in (ledgerman, scribe)
    empires.decide_case(db, new_head, cases[naira(100_000)]["id"], False, NOW9) if new_head != scribe else None
    sound(db)


def test_the_ai_audit_can_be_hired_only_in_an_audit_season_for_a_large_fee_and_looks_back_four_quarters(db, monkeypatch):
    empire, (head, _), partners = founded(db, cash=400_000_000, put_in=300_000_000)
    scribe, scribe_account = partners["journalist"]
    empires.set_limits(db, head, expense_limit=naira(500_000))
    empires.divert(db, scribe, naira(100_000), NOW9)
    # An old theft, from before the audit looks.
    old = empires._book(db, empire["id"], 9 - data.AI_AUDIT_LOOKS_BACK, "Research and sources", "old", naira(50_000), False, NOW9,
                        entered_by=scribe, thief_level=4)
    assert not empires.audit_season(9) and empires.audit_season(12) and not any(empires.audit_season(p) for p in (9, 10, 11))
    with pytest.raises(empires.EmpireError, match="only in an audit season"):
        empires.ai_audit(db, head, NOW9)
    monkeypatch.setattr(data, "AUDIT_SEASON_EVERY", 3)                        # as if this were the last quarter of a game year
    pool = ledger.balance(db, ledger.account_id(db, ledger.PRIZE_POOL))
    fee = empires.ai_audit_fee(db, empire, NOW9)
    assert fee == max(apply_bps(empires.worth(db, empire, NOW9)["total"], data.AI_AUDIT_FEE_BPS), naira(data.AI_AUDIT_LEAST_NAIRA)) >= naira(5_000_000)
    always(monkeypatch, True)
    done = empires.ai_audit(db, head, NOW9)
    assert done["fee"] == fee and done["found"] == 1
    assert ledger.balance(db, ledger.account_id(db, ledger.PRIZE_POOL)) == pool + fee
    assert not _dicts(db, "SELECT found FROM empire_books WHERE id = %s", (old,))[0]["found"]            # the old one got away
    assert _dicts(db, "SELECT status FROM empire_cases")[0]["status"] == "open"                         # a foul is called; the head decides
    with pytest.raises(empires.EmpireError, match="already been hired"):
        empires.ai_audit(db, head, NOW9)
    # A member who is not the head pays for it out of their own pocket, and cannot if they have not the cash.
    other = computer_empire(db)
    poor, _ = thief_in(db, other, "lawyer", "poor")
    with pytest.raises(empires.EmpireError, match="not that much cash"):
        empires.ai_audit(db, poor, NOW9)
    sound(db)


def test_the_ai_audit_is_right_about_ninety_five_times_in_a_hundred(db):
    found = sum(1 for n in range(4000) if empires._roll(db, "ai", 1, n) < data.AI_AUDIT_FINDS_BPS)
    assert 0.935 < found / 4000 < 0.965
    # The draw hangs on the world's secret: without it, nobody can know which entries will be missed.
    assert empires._roll(db, "ai", 1, 1) == empires._roll(db, "ai", 1, 1) != empires._roll(db, "ai", 1, 2)


def test_reporting_a_theft_that_is_proved_is_rewarded_and_a_groundless_report_costs_reputation(db, monkeypatch):
    empire = computer_empire(db)
    thief, _ = thief_in(db, empire, cash=1_000_000)
    watcher, watcher_account = thief_in(db, empire, "journalist", "watcher")
    empires.divert(db, thief, naira(200_000), NOW9)
    room = empires.war_room(db, watcher, NOW9)
    false = next(b["id"] for b in room["books"] if b["amount"] == naira(200_000))
    genuine = next(b["id"] for b in room["books"] if b["category"] == "Staff pay")
    reputation = _dicts(db, "SELECT reputation FROM players WHERE id = %s", (watcher,))[0]["reputation"]
    always(monkeypatch, True)
    assert empires.report_entry(db, watcher, genuine, NOW9) == {"proved": False}
    assert _dicts(db, "SELECT reputation FROM players WHERE id = %s", (watcher,))[0]["reputation"] == reputation - 1
    with pytest.raises(empires.EmpireError, match="already been looked at"):
        empires.report_entry(db, watcher, genuine, NOW9)
    before = ledger.balance(db, watcher_account)
    assert empires.report_entry(db, watcher, false, NOW9) == {"proved": True}
    assert ledger.balance(db, watcher_account) == before + naira(20_000)                     # a tenth of what was taken
    # Three reports a quarter, and none on another empire's books.
    other_entry = _dicts(db, "SELECT id FROM empire_books WHERE empire_id <> %s LIMIT 1", (empire["id"],))[0]["id"]
    with pytest.raises(empires.EmpireError, match="no such entry"):
        empires.report_entry(db, watcher, other_entry, NOW9)
    more = [b["id"] for b in empires.war_room(db, watcher, NOW9)["books"] if b["category"] == "Staff pay" and b["id"] != genuine]
    empires.report_entry(db, watcher, more[0], NOW9)
    with pytest.raises(empires.EmpireError, match="3 entries a quarter"):
        empires.report_entry(db, watcher, more[1], NOW9)
    # A thief cannot report their own theft for the reward.
    assert _dicts(db, "SELECT reward_paid FROM empire_cases")[0]["reward_paid"] == naira(20_000)
    sound(db)


def test_a_thief_cannot_profit_by_reporting_themselves(db, monkeypatch):
    empire = computer_empire(db)
    thief, account = thief_in(db, empire, cash=1_000_000)
    before = ledger.balance(db, account)
    taken = empires.divert(db, thief, naira(200_000), NOW9)
    always(monkeypatch, True)
    empires.report_entry(db, thief, taken["book_id"], NOW9)
    assert ledger.balance(db, account) == before - naira(200_000)             # repaid, fined, and no reward


def test_the_staff_accountant_audits_each_quarter_and_the_whole_thing_adds_up_over_a_quarter(db, monkeypatch):
    empire = computer_empire(db)
    thief, account = thief_in(db, empire, cash=2_000_000)
    empires.divert(db, thief, naira(250_000), NOW9)
    always(monkeypatch, True)
    assert quarters.close_due_quarters(db, after_quarters(9)) == [9]
    case = _dicts(db, "SELECT * FROM empire_cases")[0]
    assert case["status"] == "punished" and case["repaid"] == naira(500_000)
    assert empires.seat_of(db, thief) is None
    sound(db)


# ---------------------------------------------------------------------------
# Secret pacts
# ---------------------------------------------------------------------------

def test_a_lawyer_drafts_a_pact_the_heads_sign_it_and_it_stays_hidden(db, monkeypatch):
    empire, (head, _), partners = founded(db)
    other = computer_empire(db)
    scribe = partners["journalist"][0]
    with pytest.raises(empires.EmpireError, match="drafted by a Lawyer"):
        empires.draft_pact(db, scribe, other["id"], "alliance", "We stand together against all comers.", NOW9)
    counsel, _ = pro(db, "lawyer", "counsel", level=4)
    empires.apply(db, counsel, empire["id"], NOW9)
    empires.decide_application(db, head, _dicts(db, "SELECT id FROM empire_applications WHERE status = 'waiting'")[0]["id"], True, NOW9)
    work = objectives.accept(db, counsel, "lw_pact", NOW9)
    for kind, terms in (("nonsense", "We stand together against all comers."), ("alliance", "short")):
        with pytest.raises(empires.EmpireError):
            empires.draft_pact(db, counsel, other["id"], kind, terms, NOW9)
    pact = empires.draft_pact(db, counsel, other["id"], "alliance", "We stand together against all comers.", NOW9)
    with pytest.raises(empires.EmpireError, match="Only the head"):
        empires.sign_pact(db, counsel, pact["id"], NOW9)
    assert empires.sign_pact(db, head, pact["id"], NOW9)["status"] == "signed"
    assert empires.war_room(db, head, NOW9)["pacts"][0]["status"] == "signed"
    # Nobody outside the two empires can see it.
    outsider, _ = pro(db, "lawyer", "outsider")
    empires.apply(db, outsider, computer_empire(db, 2)["id"], NOW9)
    assert empires.war_room(db, outsider, NOW9)["pacts"] == [] and empires.directory(db, outsider, NOW9)["exposed_pacts"] == []
    # An unlawful pact can be drafted; a computer-run empire usually refuses it.
    always(monkeypatch, False)
    bad = empires.draft_pact(db, counsel, computer_empire(db, 1)["id"], "fix_prices", "We both hold our prices at the same level.", NOW9)
    assert bad["legal"] is False and empires.sign_pact(db, head, bad["id"], NOW9)["status"] == "refused"
    # Either side can break a pact, and loses trust for it.
    trust = _dicts(db, "SELECT trust FROM empires WHERE id = %s", (empire["id"],))[0]["trust"]
    empires.break_pact(db, head, pact["id"], NOW9)
    assert _dicts(db, "SELECT trust FROM empires WHERE id = %s", (empire["id"],))[0]["trust"] == trust - data.PACT_BREAK_TRUST
    with pytest.raises(empires.EmpireError):
        empires.break_pact(db, head, pact["id"], NOW9)
    # The Lawyer's work is judged when the quarter closes: the pact was signed by both.
    assert quarters.close_due_quarters(db, after_quarters(9)) == [9]
    assert state_of(db, work["id"])["state"] == "passed"
    sound(db)


def test_a_journalist_can_uncover_a_pact_once_a_quarter_and_an_unlawful_one_costs_both_empires_trust(db, monkeypatch):
    empire, (head, _), partners = founded(db)
    scribe = partners["journalist"][0]
    one, two = computer_empire(db, 0), computer_empire(db, 1)
    pact = _dicts(db, "INSERT INTO empire_pacts (kind, legal, from_empire, to_empire, terms, status, period, signed_period, at)"
                      " VALUES ('rig_bids', false, %s, %s, 'We take turns to win.', 'signed', 9, 9, %s) RETURNING id", (one["id"], two["id"], NOW9))[0]
    always(monkeypatch, False)
    assert empires.investigate(db, scribe, one["id"], NOW9)["found"] is False
    with pytest.raises(empires.EmpireError, match="already investigated"):
        empires.investigate(db, scribe, two["id"], NOW9)
    always(monkeypatch, True)
    reporter, _ = pro(db, "journalist", "reporter")
    assert empires.investigate(db, reporter, two["id"], NOW9)["found"] is True
    assert [e["trust"] for e in _dicts(db, "SELECT trust FROM empires WHERE id IN (%s, %s)", (one["id"], two["id"]))] == [50 - data.PACT_EXPOSED_TRUST] * 2
    shown = empires.directory(db, head, NOW9)["exposed_pacts"]
    assert len(shown) == 1 and shown[0]["legal"] is False and pact["id"]
    with pytest.raises(empires.EmpireError, match="Only a Journalist"):
        empires.investigate(db, head, one["id"], NOW9)


# ---------------------------------------------------------------------------
# The War Room
# ---------------------------------------------------------------------------

def test_the_war_room_is_for_members_only(db):
    empire = computer_empire(db)
    ada, _ = thief_in(db, empire, "accountant", "ada")
    outsider, _ = pro(db, "lawyer", "outsider")
    assert empires.war_room(db, outsider, NOW9) is None
    with pytest.raises(empires.EmpireError, match="no seat"):
        empires.say(db, outsider, "hello", NOW9)
    for body in ("", " ", "x" * 501):
        with pytest.raises(empires.EmpireError):
            empires.say(db, ada, body, NOW9)
    empires.say(db, ada, "  The accounts   are in. ", NOW9)
    room = empires.war_room(db, ada, NOW9)
    assert room["messages"][-1]["body"] == "The accounts are in." and room["messages"][-1]["yours"]
    spy, _ = thief_in(db, computer_empire(db, 1), "accountant", "spy")
    assert empires.war_room(db, spy, NOW9)["messages"] == []
    # The league table is public; what an empire holds is not.
    table = empires.directory(db, outsider, NOW9)["league"]
    assert [e["place"] for e in table] == [1, 2, 3, 4, 5] and "holdings" not in table[0] and "cash" not in table[0]


def test_nothing_can_be_done_in_the_gap_between_a_quarter_ending_and_its_books_being_closed(db):
    empire = computer_empire(db)
    ada, _ = thief_in(db, empire, "lawyer", "ada")
    gap = after_quarters(9) + timedelta(minutes=1)
    for attempt in (lambda: empires.divert(db, ada, naira(1_000), gap), lambda: empires.leave(db, ada, gap),
                    lambda: empires.report_entry(db, ada, 1, gap), lambda: empires.ai_audit(db, ada, gap)):
        with pytest.raises(empires.EmpireError, match="books are being closed"):
            attempt()


def test_ten_quarters_of_empires_never_make_or_lose_a_kobo(db):
    assert quarters.close_due_quarters(db, after_quarters(10)) == [9, 10]
    sound(db)
    # With no players, each computer-run empire has worked its task through to the purchase and has an order waiting.
    for task in _dicts(db, "SELECT t.id, t.empire_id, t.company_id, e.account_id FROM empire_tasks t JOIN empires e ON e.id = t.empire_id"
                           " WHERE t.status = 'open'"):
        steps = _dicts(db, "SELECT build, status, done_by_staff FROM empire_task_steps WHERE task_id = %s ORDER BY position", (task["id"],))
        assert [s["status"] for s in steps] == ["done"] * 6 + ["current"] and all(s["done_by_staff"] for s in steps[:6])
        assert _dicts(db, "SELECT 1 FROM market_orders WHERE account_id = %s AND company_id = %s AND side = 'buy' AND status = 'open'",
                      (task["account_id"], task["company_id"]))
    assert len(_dicts(db, "SELECT 1 FROM empire_tasks WHERE status = 'open'")) == 5


def test_the_staff_finish_the_purchase_once_the_shares_have_arrived(db):
    task = _dicts(db, "SELECT t.*, e.account_id, c.ticker FROM empire_tasks t JOIN empires e ON e.id = t.empire_id"
                      " JOIN companies c ON c.id = t.company_id WHERE t.status = 'open' ORDER BY t.id LIMIT 1")[0]
    need = empires.shares_needed(db, task, NOW9)
    ledger.transfer(db, payer=ledger.account_id(db, ledger.INVESTORS_PUBLIC), receiver=task["account_id"], amount=need,
                    asset=f"SHR-{task['ticker']}", kind="test_shares", memo="Test: the order was filled")
    empires.tick(db, NOW9)
    assert _dicts(db, "SELECT status FROM empire_tasks WHERE id = %s", (task["id"],))[0]["status"] == "done"
