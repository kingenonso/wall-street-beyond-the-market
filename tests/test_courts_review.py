"""Stage 11: each finding of the independent review, fixed, with its test.

The review read the court as a player would: it looked for a number that was too high or too low, a case that could be
charged twice, a bond that vanished, and money that moved without the ledger. Three findings were real and are fixed
here; the rest are the invariants the court must keep.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from psycopg import errors
from psycopg.rows import dict_row

from simulation import courts, ledger
from simulation import world_data as data
from simulation.money import naira
from tests.test_careers import NOW9
from tests.test_courts import (INSIDER_SHARES, P, T, company, fees_of, insider_wrong, open_regulator_case, player_of,
                                stake_wrong, wash_wrong)
from tests.test_market import trader
from tests.test_objectives import give_cash

pytestmark = pytest.mark.world("eight")


def _one(db, sql, params=()):
    with db.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(sql, params).fetchall()
    return rows[0] if rows else None


def _rows(db, sql, params=()):
    with db.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


# R1. The insider's number charged the other side's fee as well as its own, so the profit was understated.
def test_r1_the_insider_profit_is_charged_only_the_fees_the_account_itself_paid(db):
    found = insider_wrong(db)
    wrong, base, high = found["wrong"], found["base"], found["high"]
    own = fees_of(db, found["insider"], found["company"]["id"], NOW9 - timedelta(hours=1))
    both = sum(r["buyer_fee"] + r["seller_fee"] for r in _rows(
        db, "SELECT buyer_fee, seller_fee FROM market_trades WHERE company_id = %s"
            " AND (buyer_account_id = %s OR seller_account_id = %s) AND traded_at >= %s",
        (found["company"]["id"], found["insider"], found["insider"], NOW9 - timedelta(hours=1))))
    assert wrong["amount"] == (high - base) * INSIDER_SHARES - own
    assert wrong["amount"] > (high - base) * INSIDER_SHARES - both


# R2. A wash trade was also charged as a ramp, so one course of conduct could fill the docket twice.
def test_r2_wash_trading_is_one_wrong_and_not_also_a_ramp(db):
    wash = wash_wrong(db)
    mine = [w for w in courts._wrongs(db, P, NOW9)
            if w["kind"] == "manipulation" and str(w["defendant_id"]) == str(wash["pid"])]
    assert len(mine) == 1
    assert mine[0]["key"].startswith("manipulation:")


# R3. A player's bond was kept by the Treasury even when the claim was proved, though the rule says it is returned.
def test_r3_the_bond_comes_back_when_the_claim_is_proved(db):
    c = company(db)
    stake = stake_wrong(db)
    claimant = trader(db, "claimant", cash_naira=100_000_000_000)     # a tenth of a large stake is a large bond
    claimant_pid = player_of(db, claimant)
    ledger.transfer(db, payer=ledger.account_id(db, ledger.INVESTORS_PUBLIC), receiver=claimant, amount=1_000,
                    asset=f"SHR-{T}", kind="test_shares", memo="Test: a shareholding")
    case = courts.bring(db, claimant_pid, kind="undisclosed_stake", defendant_id=stake["team"]["head"],
                        company_id=c["id"], period=P, now=NOW9)
    give_cash(db, ledger.player_account_id(db, stake["team"]["head"]), 1_000_000_000)
    courts.respond(db, stake["team"]["head"], case["id"], "fight", P, NOW9)
    returned = _one(db, "SELECT amount FROM ledger_transactions t JOIN ledger_entries e ON e.transaction_id = t.id"
                        " WHERE t.kind = 'court_bond_return' AND t.memo LIKE %s AND e.amount > 0",
                    (f"%{case['id']}%",))
    assert returned and returned["amount"] == case["bond"]


# R4. A settlement the defendant cannot afford must not half-happen: the case stays open to be judged.
def test_r4_a_settlement_that_cannot_be_paid_leaves_the_case_open(db):
    c = company(db)
    defendant = trader(db, "defendant", cash_naira=1_000)
    pid = player_of(db, defendant)
    case_id = open_regulator_case(db, defendant_id=pid, company_id=c["id"])
    with pytest.raises(courts.CourtError):
        courts.respond(db, pid, case_id, "settle", P, NOW9)
    assert courts.case(db, case_id)["status"] == "open"
    assert _one(db, "SELECT count(*) AS n FROM court_payments WHERE case_id = %s", (case_id,))["n"] == 0


# R5. Every naira the court moves is a ledger transaction, and the books balance after every step.
def test_r5_the_courts_books_balance_after_every_step(db):
    c = company(db)
    defendant = trader(db, "defendant", cash_naira=100_000_000)
    pid = player_of(db, defendant)
    courts.ensure(db)
    assert ledger.audit(db) == []
    case_id = open_regulator_case(db, kind="insider", defendant_id=pid, company_id=c["id"])
    assert ledger.audit(db) == []
    courts.judge(db, case_id, P, NOW9)
    assert ledger.audit(db) == []
    give_cash(db, defendant, 100_000_000)
    courts.pay(db, case_id, P + 1, NOW9)
    assert ledger.audit(db) == []


# R6. A case, once opened, is not rewritten: its claim and its evidence stay as they were.
def test_r6_a_cases_claim_and_evidence_are_permanent(db):
    c = company(db)
    defendant = trader(db, "defendant", cash_naira=1_000_000)
    pid = player_of(db, defendant)
    case_id = open_regulator_case(db, defendant_id=pid, company_id=c["id"])
    other = player_of(db, trader(db, "other", cash_naira=1_000_000))
    for column, value in (("amount", 1), ("evidence", "{}"), ("kind", "manipulation"), ("defendant_id", other)):
        with pytest.raises(errors.RestrictViolation):
            db.execute(f"UPDATE court_cases SET {column} = %s WHERE id = %s", (value, case_id))


# R7. A judgment is paid once: paying a case already paid moves nothing.
def test_r7_a_judgment_is_not_paid_twice(db):
    c = company(db)
    defendant = trader(db, "defendant", cash_naira=100_000_000)
    pid = player_of(db, defendant)
    case_id = open_regulator_case(db, kind="insider", defendant_id=pid, company_id=c["id"])
    courts.ensure(db)
    case = courts.judge(db, case_id, P, NOW9)
    assert case["owed"] == 0
    before = ledger.balance(db, defendant)
    assert courts.pay(db, case_id, P + 1, NOW9) == 0
    assert ledger.balance(db, defendant) == before


# R9. A judgment paid in parts left a few kobo owed for ever, because each receiver's share was rounded down.
def test_r9_a_judgment_paid_in_parts_leaves_no_kobo_behind(db):
    c = company(db)
    defendant = trader(db, "defendant", cash_naira=1_000_000)
    pid = player_of(db, defendant)
    case_id = open_regulator_case(db, kind="insider", defendant_id=pid, company_id=c["id"])
    courts.ensure(db)
    case = courts.judge(db, case_id, P, NOW9)
    owed = case["disgorgement"] + case["fine"] + case["costs"]
    give_cash(db, defendant, 100_000_000)
    assert courts.pay(db, case_id, P + 1, NOW9) == owed - naira(1_000_000)
    assert courts.case(db, case_id)["owed"] == 0


# R8. The regulator's budget is a ledger account, and the cost of proving a case is a ledger transaction.
def test_r8_the_regulators_budget_and_its_spending_are_in_the_ledger(db):
    c = company(db)
    defendant = trader(db, "defendant", cash_naira=1_000_000)
    pid = player_of(db, defendant)
    wrong = {"kind": "insider", "key": "insider:test", "defendant_id": pid, "company_id": c["id"], "ticker": T,
             "amount": naira(10_000_000), "lines": [{"what": "trade"}], "words": "Dealt on confidential information."}
    courts.ensure(db)
    budget = ledger.account_id(db, courts.REGULATOR)
    before = ledger.balance(db, budget)
    courts._regulator_brings(db, wrong, P, NOW9)
    assert ledger.balance(db, budget) == before - naira(data.COURT_CASE_COST_NAIRA)
    spent = _one(db, "SELECT sum(-e.amount)::bigint AS spent FROM ledger_entries e JOIN ledger_transactions t"
                     " ON t.id = e.transaction_id WHERE e.account_id = %s AND t.kind = 'court_cost'", (budget,))
    assert spent["spent"] == naira(data.COURT_CASE_COST_NAIRA)
    assert ledger.audit(db) == []
