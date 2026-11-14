"""Insurance: what each policy promises, one test each.

Four policies, sold under Money: property and premises, directors' and officers', income protection and the personal
umbrella. The premium is the expected loss from the game's own record, a loading, and a charge on the cover. A claim is
made against a loss the game recorded, and every naira goes through the insurers' policy account.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from psycopg.rows import dict_row

from simulation import careers, courts, insurance, lending, ledger, quarters
from simulation import world_data as data
from simulation.money import BPS, naira
from tests.conftest import after_quarters
from tests.test_builds import pro
from tests.test_careers import NOW9, sound
from tests.test_property import a_unit, hand_over

pytestmark = pytest.mark.world("eight")

P = 9
LATER = after_quarters(9) + timedelta(hours=2)        # the tenth quarter, just after the ninth has closed


def _one(db, sql, params=()):
    with db.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(sql, params).fetchall()
    return rows[0] if rows else None


def books(db):
    assert insurance.check_books(db) == []
    sound(db)


def landlord(db, name="landlord", cash_naira=50_000_000, city="Lagos"):
    p = a_unit(db, city)
    player, account = pro(db, "asset_manager", name, cash_naira=cash_naira)
    hand_over(db, p["id"], account)
    return p, player, account


def close_nine(db):
    quarters.close_due_quarters(db, after_quarters(9))


def test_a_policy_is_priced_from_the_record_and_its_premium_goes_into_the_policy_account(db):
    p, player, account = landlord(db)
    most = insurance.most_cover(db, player, "property", NOW9)
    assert most > 0
    priced = insurance.quote(db, player, "property", most, 0, NOW9)
    assert priced["loading"] == priced["expected_loss"] * data.INSURANCE_LOADING_BPS // BPS
    assert priced["on_cover"] == most * data.INSURANCE_RATE_ON_COVER_BPS // BPS
    assert priced["premium"] == priced["expected_loss"] + priced["loading"] + priced["on_cover"]
    assert priced["expected_loss"] > 0               # the record shows buildings wear
    before = ledger.balance(db, account)
    bought = insurance.buy(db, player, "property", most, 0, NOW9)
    assert bought["premium"] == priced["premium"]
    assert ledger.balance(db, account) == before - priced["premium"]
    assert ledger.balance(db, insurance.pool(db)) == naira(data.INSURANCE_POOL_CAPITAL_NAIRA) + priced["premium"]
    books(db)


def test_cover_is_never_more_than_there_is_to_lose(db):
    p, player, account = landlord(db)
    most = insurance.most_cover(db, player, "property", NOW9)
    with pytest.raises(insurance.InsuranceError, match="at most"):
        insurance.buy(db, player, "property", most + 1, 0, NOW9)
    with pytest.raises(insurance.InsuranceError, match="tops up"):
        insurance.buy(db, player, "umbrella", naira(1_000), 0, NOW9)
    jobless, _ = pro(db, "risk_manager", "jobless", cash_naira=1_000_000)
    careers.leave_job(db, jobless, NOW9)
    with pytest.raises(insurance.InsuranceError, match="in work"):
        insurance.buy(db, jobless, "income", naira(1_000), 0, NOW9)
    with pytest.raises(insurance.InsuranceError, match="no buildings"):
        insurance.buy(db, jobless, "property", naira(1_000), 0, NOW9)
    insurance.buy(db, player, "property", most, 0, NOW9)
    with pytest.raises(insurance.InsuranceError, match="already hold"):
        insurance.buy(db, player, "property", most, 0, NOW9)


def test_wear_on_a_kept_up_building_is_paid_less_the_excess_and_the_record_starts_again(db):
    p, player, account = landlord(db)
    excess = naira(1_000)
    insurance.buy(db, player, "property", insurance.most_cover(db, player, "property", NOW9), excess, NOW9)
    close_nine(db)
    loss = next(x for x in insurance.losses(db, player, LATER) if x["key"] == f"property:{p['id']}:{P}")
    assert not loss["caused"] and loss["loss"] > excess
    pool_before = ledger.balance(db, insurance.pool(db))
    paid = insurance.claim(db, player, loss["key"], LATER)
    assert paid["decision"] == "paid"
    assert paid["paid"] == loss["loss"] - excess
    assert ledger.balance(db, insurance.pool(db)) == pool_before - paid["paid"]
    assert _one(db, "SELECT clean_quarters FROM insurance_records WHERE player_id = %s AND kind = 'property'",
                (player,))["clean_quarters"] == 0
    with pytest.raises(insurance.InsuranceError, match="already been claimed"):
        insurance.claim(db, player, loss["key"], LATER)
    books(db)


def test_next_quarters_premium_is_charged_at_the_close_and_unpaid_cover_lapses(db):
    p, player, account = landlord(db)
    insurance.buy(db, player, "property", insurance.most_cover(db, player, "property", NOW9), 0, NOW9)
    poor, poor_account = pro(db, "risk_manager", "poor", cash_naira=1_000_000)
    careers.leave_job(db, poor, NOW9)                                     # no pay will come in at the close
    insurance.buy(db, poor, "directors", naira(1_000_000), 0, NOW9)
    # Leave the poor player nothing for next quarter's premium.
    ledger.transfer(db, payer=poor_account, receiver=account, amount=ledger.balance(db, poor_account), kind="gift",
                    memo="test")
    close_nine(db)
    mine = _one(db, "SELECT * FROM insurance_policies WHERE player_id = %s", (player,))
    assert mine["ended_at"] is None and mine["paid_through"] == P + 1
    assert _one(db, "SELECT clean_quarters FROM insurance_records WHERE player_id = %s AND kind = 'property'",
                (player,))["clean_quarters"] == 1
    theirs = _one(db, "SELECT * FROM insurance_policies WHERE player_id = %s", (poor,))
    assert theirs["ended_reason"] == "lapsed"
    books(db)


def test_each_clean_year_takes_a_twentieth_off_the_premium(db):
    p, player, account = landlord(db)
    cover = insurance.most_cover(db, player, "property", NOW9)
    full = insurance.quote(db, player, "property", cover, 0, NOW9)["premium"]
    db.execute("INSERT INTO insurance_records (player_id, kind, clean_quarters, counted_period) VALUES (%s, 'property', 8, 8)",
               (player,))
    two_years = insurance.quote(db, player, "property", cover, 0, NOW9)
    assert two_years["no_claims_bps"] == 2 * data.INSURANCE_NO_CLAIMS_STEP_BPS
    assert two_years["premium"] == full - full * 2 * data.INSURANCE_NO_CLAIMS_STEP_BPS // BPS


def test_cover_in_force_and_paid_makes_a_personal_loan_cheaper(db):
    player, account = pro(db, "investment_banker", "borrower", cash_naira=5_000_000)
    assert insurance.personal_spread_bps(db, player) == data.PERSONAL_LOAN_SPREAD_BPS
    cover = insurance.most_cover(db, player, "income", NOW9)
    insurance.buy(db, player, "income", cover, 0, NOW9)
    step = data.INSURED_SPREAD_STEP_BPS
    assert insurance.personal_spread_bps(db, player, borrowing=cover) == data.PERSONAL_LOAN_SPREAD_BPS - 2 * step
    assert insurance.personal_spread_bps(db, player, borrowing=cover * 2) == data.PERSONAL_LOAN_SPREAD_BPS - step
    assert insurance.personal_spread_bps(db, player, borrowing=cover * 2 + 1) == data.PERSONAL_LOAN_SPREAD_BPS
    amount = min(cover, lending.personal_limit(db, player, NOW9))
    loan = lending.take_personal(db, player, amount, NOW9)
    assert loan["rate_bps"] == lending.policy_rate(db) + data.PERSONAL_LOAN_SPREAD_BPS - 2 * step
    # The benefit is worth more than the loading: a year's saving on the loan beats a year's premium.
    premium = _one(db, "SELECT premium FROM insurance_policies WHERE player_id = %s", (player,))["premium"]
    assert amount * 2 * step // BPS > premium * 4


def test_income_protection_pays_half_the_salary_each_quarter_while_out_of_work(db):
    player, account = pro(db, "risk_manager", "reporter", cash_naira=5_000_000)
    salary = insurance._salary(db, player, NOW9)
    insurance.buy(db, player, "income", insurance.most_cover(db, player, "income", NOW9), 0, NOW9)
    careers._leave(db, player, NOW9 + timedelta(hours=1), "dismissed: repeated reckless reporting")
    loss = next(x for x in insurance.losses(db, player, NOW9 + timedelta(hours=2)) if x["kind"] == "income")
    accepted = insurance.claim(db, player, loss["key"], NOW9 + timedelta(hours=2))
    assert accepted["decision"] == "paying"
    assert accepted["payable"] == salary * data.INSURANCE_INCOME_SHARE_BPS // BPS * data.INSURANCE_INCOME_QUARTERS
    before = ledger.balance(db, account)
    close_nine(db)
    row = _one(db, "SELECT * FROM insurance_claims WHERE id = %s", (accepted["claim_id"],))
    assert row["paid"] == accepted["payable"] // data.INSURANCE_INCOME_QUARTERS
    assert row["instalments"] == data.INSURANCE_INCOME_QUARTERS - 1
    assert ledger.balance(db, account) >= before          # the instalment came in (and any premium went out)
    books(db)


def test_directors_cover_pays_the_tribunals_costs_and_never_the_fine_or_the_disgorgement(db):
    player, account = pro(db, "investment_banker", "director", cash_naira=50_000_000)
    insurance.buy(db, player, "directors", naira(10_000_000), 0, NOW9)
    # The cover began long enough ago for a case opened now to be covered.
    db.execute("UPDATE insurance_policies SET started_period = 1, started_at = started_at - interval '60 days'"
               " WHERE player_id = %s", (player,))
    courts.ensure(db)
    amount = naira(20_000_000)
    case_id = courts.open_case(db, kind="insider", defendant_id=player, claimant_id=None, company_id=None, amount=amount,
                               evidence={"key": "insider:insured", "total": amount, "lines": []},
                               words="A test case of insider dealing.", period=P, now=NOW9)
    judged = courts.judge(db, case_id, P, NOW9 + timedelta(hours=1))
    loss = next(x for x in insurance.losses(db, player, NOW9 + timedelta(hours=2)) if x["key"] == f"case:{case_id}")
    assert loss["loss"] == judged["costs"] + judged["damages"]
    assert loss["uninsurable"] == judged["fine"] + judged["disgorgement"]
    paid = insurance.claim(db, player, loss["key"], NOW9 + timedelta(hours=2))
    assert paid["decision"] == "paid" and paid["paid"] == judged["costs"] + judged["damages"]
    books(db)


def test_the_umbrella_pays_what_is_beyond_the_policy_that_answers(db):
    p, player, account = landlord(db, cash_naira=100_000_000)
    insurance.buy(db, player, "property", naira(1_000), 0, NOW9)          # far less than one quarter's wear
    insurance.buy(db, player, "umbrella", naira(1_000), 0, NOW9)
    close_nine(db)
    db.execute("UPDATE insurance_policies SET cover = %s WHERE player_id = %s AND kind = 'umbrella'",
               (naira(100_000_000), player))                              # (as if bought over more cover)
    loss = next(x for x in insurance.losses(db, player, LATER) if x["key"] == f"property:{p['id']}:{P}")
    paid = insurance.claim(db, player, loss["key"], LATER)
    assert paid["paid"] == loss["loss"]
    row = _one(db, "SELECT * FROM insurance_claims WHERE id = %s", (paid["claim_id"],))
    assert row["umbrella"] == loss["loss"] - naira(1_000)
    books(db)


def test_the_page_shows_the_policies_the_losses_and_the_loan_rate(db):
    p, player, account = landlord(db)
    page = insurance.view(db, player, NOW9)
    assert page["ready"] and [x["kind"] for x in page["policies"]] == list(insurance.KINDS)
    assert page["borrowing"]["spread_bps"] == data.PERSONAL_LOAN_SPREAD_BPS
    assert "loses you money" in page["honest"]
