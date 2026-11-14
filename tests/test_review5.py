"""Stage 5: what the independent review found, each kept as a test so it cannot come back.

A second reviewer, who did not write Stage 5, attacked it. Nothing they found made or lost
money; what they found was pay for nothing, timing tricks at the quarter's end, an answer that
could never be judged, and records without a guard. Each is closed, and tested here.
"""

from __future__ import annotations

from datetime import timedelta

import psycopg
import pytest
from psycopg.rows import dict_row

from simulation import careers, ledger, objectives, quarters
from simulation.money import naira
from tests.conftest import ADULT, after_quarters, join
from tests.test_careers import NOW9, OPEN, pass_one, professional, sound
from tests.test_objectives import accountant, bell, give_shares, manager, state_of


def _dicts(db, sql, params=()):
    with db.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


GAP9 = after_quarters(9) - timedelta(minutes=59)          # the ninth quarter has ended by the clock; it is not closed yet


# 1. A last-minute bank move must not earn a quarter's interest.
def test_moving_bank_on_the_last_day_earns_no_interest_for_the_quarter(db):
    mover, mover_account = professional(db, "mover", employer=None, bank="IKB")
    loyal, loyal_account = professional(db, "loyal", employer=None, bank="IKB")
    quarters.close_due_quarters(db, after_quarters(1))
    for account in (mover_account, loyal_account):
        ledger.transfer(db, payer=ledger.account_id(db, ledger.TREASURY), receiver=account, amount=naira(50_000_000),
                        kind="test_cash", memo="Test: cash arrives a minute before the quarter ends")
    careers.choose_bank(db, mover, "ZCB", after_quarters(2) - timedelta(hours=1, minutes=1))
    quarters.close_due_quarters(db, after_quarters(2))
    paid = {r["player_id"]: r["amount"] for r in _dicts(db, "SELECT player_id, amount FROM deposit_interest WHERE period = 2")}
    assert paid.get(mover, 0) == 0 and paid[loyal] == 0            # the cash was not there through the quarter either
    quarters.close_due_quarters(db, after_quarters(3))
    third = {r["player_id"]: r["amount"] for r in _dicts(db, "SELECT player_id, amount FROM deposit_interest WHERE period = 3")}
    assert third[mover] > 0 and third[loyal] > 0                   # a whole quarter with the bank, and the cash stayed
    sound(db)


# 2. A blank sheet is not work.
@pytest.mark.world("eight")
def test_a_blank_hand_in_is_not_work_and_earns_no_salary(db):
    blank, _ = accountant(db, "blank")
    tried, _ = accountant(db, "tried")
    first = objectives.accept(db, blank, "ac_ratios", NOW9)
    assert objectives.submit(db, blank, first["id"], {}, NOW9)["state"] == "failed"
    second = objectives.accept(db, tried, "ac_ratios", NOW9)
    terms = state_of(db, second["id"])["terms"]
    income = _dicts(db, "SELECT figures FROM company_reports WHERE company_id = %s AND period = %s",
                    (terms["company_id"], terms["filed_period"]))[0]["figures"]["income_statement"]
    half = objectives.submit(db, tried, second["id"], {"ebitda": (income["operating_profit"] + income["depreciation"]) / 1e8,
                                                       "margin": income["net_profit"] / income["revenue"] * 100}, NOW9)
    assert half["state"] == "failed" and half["result"]["score"] == 50
    quarters.close_due_quarters(db, after_quarters(9))
    slips = {s["player_id"]: s for s in _dicts(db, "SELECT * FROM payslips")}
    assert slips[blank]["gross"] == 0 and not slips[blank]["worked"]
    assert slips[tried]["gross"] > 0 and slips[tried]["worked"]     # an honest attempt is still work


# 3 and 9. Nothing can be taken on, joined, left or moved in the moments between a quarter's end and its close.
@pytest.mark.world("eight")
def test_nothing_can_be_changed_between_the_end_of_a_quarter_and_its_close(db):
    player, _ = manager(db, level=2)
    newcomer, _ = professional(db, "new", build="asset_manager", employer=None, bank=None, now=NOW9)
    quarters.close_due_quarters(db, after_quarters(9) - timedelta(days=1)) == []
    for code in ("am_rates", "am_spread", "am_mandate"):
        with pytest.raises(objectives.ObjectiveError, match="books are being closed"):
            objectives.accept(db, player, code, GAP9)
    for change in (lambda: careers.take_job(db, player, "ZCB", GAP9), lambda: careers.leave_job(db, player, GAP9),
                   lambda: careers.choose_bank(db, player, "ZCB", GAP9), lambda: careers.choose_fund(db, player, "growth", GAP9),
                   lambda: careers.choose_bank(db, newcomer, "IKB", GAP9), lambda: careers.choose_build(db, newcomer, "accountant", GAP9)):
        with pytest.raises(careers.CareerError, match="books are being closed"):
            change()
    # A minute after the close, all of it works again.
    quarters.close_due_quarters(db, after_quarters(9))
    assert objectives.accept(db, player, "am_rates", after_quarters(9))["state"] == "active"
    assert careers.choose_bank(db, newcomer, "IKB", after_quarters(9))["ticker"] == "IKB"


# 4. A fund chosen during a quarter does not earn for that quarter.
@pytest.mark.world("eight")
def test_a_fund_chosen_during_the_quarter_takes_effect_from_the_next(db):
    switcher, _ = accountant(db, "switcher")
    stayer, _ = accountant(db, "stayer")
    for player in (switcher, stayer):
        db.execute("UPDATE retirement_accounts SET value = %s WHERE player_id = %s", (naira(1_000_000), player))
    quarters.close_due_quarters(db, after_quarters(9))
    careers.choose_fund(db, switcher, "income", after_quarters(10) - timedelta(hours=2))        # near the end of the tenth quarter
    quarters.close_due_quarters(db, after_quarters(10))
    entries = {e["player_id"]: e for e in _dicts(db, "SELECT * FROM retirement_entries WHERE period = 10")}
    assert entries[switcher]["fund"] == entries[stayer]["fund"] == "balanced"
    assert entries[switcher]["growth"] == entries[stayer]["growth"]
    quarters.close_due_quarters(db, after_quarters(11))
    assert _dicts(db, "SELECT fund FROM retirement_entries WHERE period = 11 AND player_id = %s", (switcher,))[0]["fund"] == "income"


# 5 and 6. Answers that are not ordinary numbers are refused at the door, and never reach the books.
@pytest.mark.world("eight")
def test_answers_that_are_not_ordinary_numbers_are_refused(db, client):
    player, _ = accountant(db, "zed", level=2)
    taken = objectives.accept(db, player, "ac_forecast", NOW9)
    for bad in ("nan", "inf", "-inf", "1e999", float("nan"), float("inf"), -5, 0):
        with pytest.raises(objectives.ObjectiveError):
            objectives.submit(db, player, taken["id"], {"revenue": bad}, NOW9)
    assert state_of(db, taken["id"])["submission"] is None
    objectives.submit(db, player, taken["id"], {"revenue": "1234.5"}, NOW9)
    assert state_of(db, taken["id"])["submission"] == {"revenue": 1234.5}
    assert quarters.close_due_quarters(db, after_quarters(9)) == [9]                           # and the quarter closes
    assert state_of(db, taken["id"])["state"] in ("passed", "failed")
    # Through the website: never a server error.
    assert join(client, ADULT).status_code == 201
    for body in ('{"answers": {"operating": NaN}}', '{"answers": {"operating": Infinity}}', '{"answers": {"operating": 1e999}}',
                 '{"answers": {"operating": -1e999}}'):
        answer = client.post("/api/objectives/1/hand-in", content=body, headers={"Content-Type": "application/json"})
        assert answer.status_code == 422, body
    assert not objectives._close_enough(float("nan"), 1.0) and not objectives._close_enough("inf", 1.0)


# 7. Nobody moves employer with work in hand that the old employer would then pay for.
@pytest.mark.world("eight")
def test_work_in_hand_must_be_finished_before_moving_employer(db):
    player, account = manager(db)
    quarters.close_due_quarters(db, after_quarters(9))
    later = after_quarters(9) + timedelta(hours=12)
    objectives.accept(db, player, "am_spread", later)
    with pytest.raises(careers.CareerError, match="before moving"):
        careers.take_job(db, player, "ZCB", later)
    assert careers.current_job(db, player)["ticker"] == "IKB"


# 8. Work handed in while the Closing Bell is being rung is not overwritten by the bell.
@pytest.mark.world("eight")
def test_the_bell_reads_each_objective_afresh_under_lock(db, monkeypatch):
    player, account = manager(db, level=3)
    taken = objectives.accept(db, player, "am_value", NOW9)
    give_shares(db, account, "IDC", 60_000)
    real = objectives._judge
    handed_in = []

    def hand_in_just_before(conn, objective, now, judged_period, step, arg):
        if not handed_in:                       # the hand-in lands after the bell has listed the work and before it reaches it
            handed_in.append(objectives.submit(db, player, taken["id"], {"ticker": "IDC"}, NOW9))
        return real(conn, objective, now, judged_period, step, arg)

    monkeypatch.setattr(objectives, "_judge", hand_in_just_before)
    bell(db, 1)
    row = state_of(db, taken["id"])
    assert row["submission"] == {"ticker": "IDC"} and row["progress"]["pick"]["ticker"] == "IDC"
    assert row["progress"]["bell_day"] and row["state"] == "active"


# 10. More of the record is guarded in the database itself.
@pytest.mark.world("eight")
def test_more_of_the_record_is_guarded_in_the_database(db):
    player, _ = accountant(db)
    taken = objectives.accept(db, player, "ac_ratios", NOW9)
    for change in ("payer_name = 'Somebody else'", "title = 'x'", "module = 'x'", "client_company_id = NULL"):
        with pytest.raises(psycopg.errors.RestrictViolation):
            db.execute(f"UPDATE objectives SET {change} WHERE id = %s", (taken["id"],))
    for table in ("employments", "bank_customers", "career_events", "payslips"):
        if table != "payslips":                                                                # there is no payslip yet to delete
            with pytest.raises(psycopg.errors.RestrictViolation):
                db.execute(f"DELETE FROM {table}")
        with pytest.raises(psycopg.errors.RestrictViolation):
            db.execute(f"TRUNCATE {table} CASCADE")


# 11. Retirement saving is credited in full for the quarter it was earned in, even when the employer paid late.
@pytest.mark.world("eight")
def test_the_saving_is_credited_even_when_the_employer_pays_late(db):
    company = _dicts(db, "SELECT ticker, account_id, id FROM companies WHERE ticker = 'KTX'")[0]
    player, _ = professional(db, employer="KTX", now=NOW9)
    pass_one(db, player, NOW9)                 # the work is done first: its client may be this very company
    cash = ledger.balance(db, company["account_id"])
    if cash:
        ledger.transfer(db, payer=company["account_id"], receiver=ledger.account_id(db, ledger.TREASURY), amount=cash,
                        kind="test_drain", memo="Test: the company has no cash")
    quarters.close_due_quarters(db, after_quarters(9))
    slip = _dicts(db, "SELECT * FROM payslips WHERE player_id = %s", (player,))[0]
    entry = _dicts(db, "SELECT * FROM retirement_entries WHERE player_id = %s", (player,))[0]
    assert entry["paid_in_by_you"] == slip["pension_yours"] > 0 and entry["paid_in_by_employer"] == slip["pension_employer"]


# Found while walking through the screens: the same work could be held twice, once from each of two quarters.
@pytest.mark.world("eight")
def test_the_same_work_cannot_be_in_hand_twice(db):
    player, _ = manager(db, level=4)
    objectives.accept(db, player, "am_beat", NOW9)                      # runs for seven Closing Bells, into the next quarter
    quarters.close_due_quarters(db, after_quarters(9))
    with pytest.raises(objectives.ObjectiveError, match="in hand already"):
        objectives.accept(db, player, "am_beat", after_quarters(9))
    offer = next(o for o in objectives.board(db, player, after_quarters(9))["offers"] if o["template"] == "am_beat")
    assert not offer["available"] and "in hand" in offer["why_not"]


def test_the_first_test_time_is_in_the_first_quarter():
    assert OPEN < after_quarters(1)
