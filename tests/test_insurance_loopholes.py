"""Insurance: the ten loophole questions from docs/INSURANCE_CHECKLIST_2026-11-09.md, one test each.

The one attack that would let a player profit from the fund itself is a badly kept policy account, so several of these
are about the account: a loss is claimed once, by the account that bore it, and the account is never overdrawn.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from psycopg.rows import dict_row
from pydantic import ValidationError

from simulation import careers, courts, insurance, ledger, quarters
from simulation import property as prop
from simulation import world_data as data
from simulation.money import BPS, naira
from tests.conftest import after_quarters
from tests.test_builds import pro
from tests.test_careers import NOW9, sound
from tests.test_property import a_unit, hand_over

pytestmark = pytest.mark.world("eight")

P = 9
LATER = after_quarters(9) + timedelta(hours=2)


def _one(db, sql, params=()):
    with db.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(sql, params).fetchall()
    return rows[0] if rows else None


def books(db):
    assert insurance.check_books(db) == []
    sound(db)


def a_dear_unit(db):
    """The most valuable standing building with a clean title, so a neglected quarter is worth a tribunal case."""
    return _one(db, "SELECT p.* FROM properties p WHERE p.status = 'standing' AND p.kind <> 'land' AND p.title_flaw_bps = 0"
                    " AND NOT EXISTS (SELECT 1 FROM auctions a WHERE a.property_id = p.id AND a.status = 'open')"
                    " AND (to_regclass('property_claims') IS NULL OR NOT EXISTS"
                    " (SELECT 1 FROM property_claims c WHERE c.property_id = p.id))"
                    " ORDER BY p.base_rent DESC, p.id LIMIT 1")


def insured_landlord(db, name="landlord", unit=None, cash_naira=2_000_000_000):
    p = unit or a_unit(db, "Lagos")
    player, account = pro(db, "asset_manager", name, cash_naira=cash_naira)
    hand_over(db, p["id"], account)
    insurance.buy(db, player, "property", insurance.most_cover(db, player, "property", NOW9), 0, NOW9)
    return p, player, account


def test_1_a_claim_on_a_loss_you_caused_is_refused_and_referred_and_the_second_ends_all_cover(db):
    p, player, account = insured_landlord(db, unit=a_dear_unit(db))
    prop.set_upkeep(db, account, p["id"], False)
    insurance.buy(db, player, "income", insurance.most_cover(db, player, "income", NOW9), 0, NOW9)
    quarters.close_due_quarters(db, after_quarters(9))
    neglect = next(x for x in insurance.losses(db, player, LATER) if x["key"] == f"property:{p['id']}:{P}")
    assert neglect["caused"] and neglect["loss"] >= naira(data.COURT_MIN_CLAIM_NAIRA)
    before = ledger.balance(db, account)
    refused = insurance.claim(db, player, neglect["key"], LATER)
    assert refused["decision"] == "refused" and refused["paid"] == 0
    assert ledger.balance(db, account) == before                     # the premium is kept; nothing is paid
    case = courts.case(db, refused["case_id"])
    assert case["kind"] == "insurance_fraud" and case["amount"] == neglect["loss"]
    assert insurance._in_force(db, player)                           # one refusal: the cover goes on
    # The second: resigning, then claiming income protection for the lost job.
    careers.leave_job(db, player, LATER + timedelta(hours=1))
    quit_ = next(x for x in insurance.losses(db, player, LATER + timedelta(hours=2)) if x["kind"] == "income")
    second = insurance.claim(db, player, quit_["key"], LATER + timedelta(hours=2))
    assert second["decision"] == "refused" and "no insurer will write for you again" in second["words"]
    assert insurance._in_force(db, player) == [] and insurance.barred(db, player)
    with pytest.raises(insurance.InsuranceError, match="No insurer"):
        insurance.buy(db, player, "directors", naira(1_000_000), 0, LATER + timedelta(hours=3))
    books(db)


def test_2_a_building_already_run_down_when_the_cover_began_is_not_insured(db):
    p = a_unit(db, "Lagos")
    player, account = pro(db, "asset_manager", "wrecker", cash_naira=50_000_000)
    hand_over(db, p["id"], account)
    db.execute("UPDATE properties SET condition = 40 WHERE id = %s", (p["id"],))
    quarters.close_due_quarters(db, after_quarters(9))                # the record now shows a wreck
    insurance.buy(db, player, "property", insurance.most_cover(db, player, "property", LATER), 0, LATER)
    quarters.close_due_quarters(db, after_quarters(10))
    later = after_quarters(10) + timedelta(hours=2)
    loss = next(x for x in insurance.losses(db, player, later) if x["key"] == f"property:{p['id']}:10")
    assert not loss["caused"]
    declined = insurance.claim(db, player, loss["key"], later)
    assert declined["decision"] == "declined" and "run down" in declined["words"]
    books(db)


def test_3_cover_bought_after_the_loss_does_not_answer_it(db):
    p = a_unit(db, "Lagos")
    player, account = pro(db, "asset_manager", "latecomer", cash_naira=50_000_000)
    hand_over(db, p["id"], account)
    quarters.close_due_quarters(db, after_quarters(9))                # the wear happens, uninsured
    insurance.buy(db, player, "property", insurance.most_cover(db, player, "property", LATER), 0, LATER)
    loss = next(x for x in insurance.losses(db, player, LATER) if x["key"] == f"property:{p['id']}:{P}")
    declined = insurance.claim(db, player, loss["key"], LATER)
    assert declined["decision"] == "declined" and declined["paid"] == 0
    # A dismissal before the cover was bought is not covered either: the job must still be held to buy it.
    worker, _ = pro(db, "risk_manager", "worker", cash_naira=5_000_000)
    careers._leave(db, worker, LATER, "dismissed: test")
    with pytest.raises(insurance.InsuranceError, match="in work"):
        insurance.buy(db, worker, "income", naira(1_000), 0, LATER + timedelta(minutes=1))


def _insured_director(db, name="director", *, years_ago=True):
    player, account = pro(db, "investment_banker", name, cash_naira=50_000_000)
    insurance.buy(db, player, "directors", naira(10_000_000), 0, NOW9)
    if years_ago:
        db.execute("UPDATE insurance_policies SET started_period = 1, started_at = started_at - interval '60 days'"
                   " WHERE player_id = %s", (player,))
    courts.ensure(db)
    amount = naira(20_000_000)
    case_id = courts.open_case(db, kind="insider", defendant_id=player, claimant_id=None, company_id=None, amount=amount,
                               evidence={"key": f"insider:{name}", "total": amount, "lines": []},
                               words="A test case of insider dealing.", period=P, now=NOW9)
    judged = courts.judge(db, case_id, P, NOW9 + timedelta(hours=1))
    return player, account, case_id, judged


def test_4_the_disgorgement_and_the_fine_are_never_insured(db):
    player, account, case_id, judged = _insured_director(db)
    assert judged["disgorgement"] > 0 and judged["fine"] > 0
    paid = insurance.claim(db, player, f"case:{case_id}", NOW9 + timedelta(hours=2))
    assert paid["payable"] == judged["costs"] + judged["damages"]
    assert paid["payable"] < judged["disgorgement"] + judged["fine"]
    books(db)


def test_5_a_wrong_done_before_the_cover_cannot_be_insured(db):
    player, account, case_id, judged = _insured_director(db, "fresh", years_ago=False)
    declined = insurance.claim(db, player, f"case:{case_id}", NOW9 + timedelta(hours=2))
    assert declined["decision"] == "declined" and "two years" in declined["words"]


def test_6_cancelling_and_buying_again_does_not_wipe_a_claim_off_the_record(db):
    player, account = pro(db, "risk_manager", "switcher", cash_naira=5_000_000)
    cover = insurance.most_cover(db, player, "income", NOW9)
    insurance.buy(db, player, "income", cover, 0, NOW9)
    db.execute("UPDATE insurance_records SET clean_quarters = 8 WHERE player_id = %s AND kind = 'income'", (player,))
    insurance.cancel(db, player, "income", NOW9 + timedelta(minutes=1))
    insurance.buy(db, player, "income", cover, 0, NOW9 + timedelta(minutes=2))
    assert insurance.no_claims_bps(db, player, "income") == 2 * data.INSURANCE_NO_CLAIMS_STEP_BPS   # kept, not reset
    insurance._reset_record(db, player, "income", P)                  # a claim paid
    insurance.cancel(db, player, "income", NOW9 + timedelta(minutes=3))
    insurance.buy(db, player, "income", cover, 0, NOW9 + timedelta(minutes=4))
    assert insurance.no_claims_bps(db, player, "income") == 0         # and a claim is not wiped by buying again


def test_7_a_cheaper_loan_needs_cover_in_force_and_paid(db):
    player, account = pro(db, "investment_banker", "lapser", cash_naira=5_000_000)
    insurance.buy(db, player, "income", insurance.most_cover(db, player, "income", NOW9), 0, NOW9)
    assert insurance.personal_spread_bps(db, player) < data.PERSONAL_LOAN_SPREAD_BPS
    db.execute("UPDATE insurance_policies SET paid_through = %s WHERE player_id = %s", (P - 1, player))   # unpaid
    assert insurance.personal_spread_bps(db, player) == data.PERSONAL_LOAN_SPREAD_BPS
    db.execute("UPDATE insurance_policies SET paid_through = %s WHERE player_id = %s", (P, player))
    insurance.cancel(db, player, "income", NOW9 + timedelta(minutes=1))
    assert insurance.personal_spread_bps(db, player) == data.PERSONAL_LOAN_SPREAD_BPS
    # The umbrella alone buys nothing from a lender.
    assert "umbrella" not in insurance.LENDER_COUNTS


def test_8_a_loss_is_claimed_once_and_each_owner_claims_only_their_share(db):
    p = a_unit(db, "Lagos")
    one, one_account = pro(db, "asset_manager", "half-one", cash_naira=50_000_000)
    two, two_account = pro(db, "asset_manager", "half-two", cash_naira=50_000_000)
    hand_over(db, p["id"], one_account, BPS // 2)
    db.execute("INSERT INTO property_holdings (property_id, account_id, share_bps, since_period) VALUES (%s, %s, %s, 8)",
               (p["id"], two_account, BPS // 2))
    for who in (one, two):
        insurance.buy(db, who, "property", insurance.most_cover(db, who, "property", NOW9), 0, NOW9)
    quarters.close_due_quarters(db, after_quarters(9))
    key = f"property:{p['id']}:{P}"
    first = next(x for x in insurance.losses(db, one, LATER) if x["key"] == key)
    second = next(x for x in insurance.losses(db, two, LATER) if x["key"] == key)
    whole = _one(db, "SELECT r.value, prev.condition - r.condition AS points FROM property_results r JOIN property_results prev"
                     " ON prev.property_id = r.property_id AND prev.period = r.period - 1 WHERE r.property_id = %s AND r.period = %s",
                 (p["id"], P))
    assert first["loss"] + second["loss"] <= whole["points"] * whole["value"] * data.RENOVATION_BPS // (data.RENOVATION_POINTS * BPS)
    insurance.claim(db, one, key, LATER)
    with pytest.raises(insurance.InsuranceError, match="already been claimed"):
        insurance.claim(db, one, key, LATER)
    stranger, _ = pro(db, "asset_manager", "stranger", cash_naira=1_000_000)
    with pytest.raises(insurance.InsuranceError, match="not a loss on your record"):
        insurance.claim(db, stranger, key, LATER)
    books(db)


def test_9_a_claim_can_empty_the_policy_account_and_never_overdraw_it(db, monkeypatch):
    monkeypatch.setattr(data, "INSURANCE_POOL_CAPITAL_NAIRA", 0)
    p, player, account = insured_landlord(db, unit=a_dear_unit(db))
    quarters.close_due_quarters(db, after_quarters(9))
    fund = insurance.pool(db)
    # Somebody else's claim has already taken all but a little of what the account holds.
    held = ledger.balance(db, fund)
    ledger.transfer(db, payer=fund, receiver=account, amount=held - 1, kind="insurance_claim", memo="test: drained")
    db.execute("INSERT INTO insurance_claims (player_id, kind, loss_key, loss, payable, paid, decision, reason, period, at)"
               " VALUES (%s, 'property', 'test:drained', %s, %s, %s, 'paid', 'test', %s, %s)",
               (player, held - 1, held - 1, held - 1, P, LATER))
    loss = next(x for x in insurance.losses(db, player, LATER) if x["key"] == f"property:{p['id']}:{P}")
    paid = insurance.claim(db, player, loss["key"], LATER)
    assert paid["paid"] == 1 and paid["shortfall"] == paid["payable"] - 1
    assert ledger.balance(db, fund) == 0
    assert "Paid in part" in paid["words"]
    books(db)


def test_10_the_page_never_names_an_amount_to_be_paid(db):
    from server.insurance_routes import BuyRequest, ClaimRequest
    with pytest.raises(ValidationError):
        ClaimRequest(loss="property:1:9", payable=1_000_000)
    with pytest.raises(ValidationError):
        ClaimRequest(loss="any loss I like")
    with pytest.raises(ValidationError):
        BuyRequest(kind="property", cover_kobo=100, premium=1)
    p, player, account = insured_landlord(db)
    page = insurance.view(db, player, NOW9)
    from server.insurance_routes import _wire
    wired = _wire(page)
    assert all(isinstance(q["most_cover"], str) for q in wired["policies"])
