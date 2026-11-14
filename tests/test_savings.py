"""Stage 6: retirement savings with a bad side to every fund, rewards for saving more, a date for
retirement, and pension funds run by players."""

from __future__ import annotations

from datetime import timedelta

import pytest
from psycopg.rows import dict_row

from simulation import bonds, careers, empires, ledger, pensionfunds, quarters
from simulation import world_data as data
from simulation.money import BPS, apply_bps, naira
from tests.conftest import after_quarters
from tests.test_builds import pro
from tests.test_careers import NOW9, pass_one, professional, sound
from tests.test_empires import always, founded
from tests.test_objectives import give_cash

pytestmark = pytest.mark.world("eight")


def _dicts(db, sql, params=()):
    with db.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def savings(db, player, value_naira: int) -> None:
    """Give a player retirement savings, with the cash behind them in the pension funds' hands."""
    db.execute("INSERT INTO retirement_accounts (player_id, value) VALUES (%s, %s) ON CONFLICT (player_id) DO UPDATE SET value = EXCLUDED.value",
               (player, naira(value_naira)))
    ledger.transfer(db, payer=ledger.account_id(db, ledger.TREASURY), receiver=ledger.account_id(db, ledger.INVESTORS_INSTITUTIONS),
                    amount=naira(value_naira), kind="test_cash", memo="Test: contributions already paid in")


# ---------------------------------------------------------------------------
# Every fund has a bad side
# ---------------------------------------------------------------------------

def test_every_fund_has_a_stated_weakness_and_can_have_a_bad_quarter(db):
    for fund in data.PENSION_FUNDS.values():
        assert fund["good"] and fund["bad"]
    level = _dicts(db, "SELECT index_level FROM pension_fund_results WHERE period = 8 LIMIT 1")[0]["index_level"]
    rate = _dicts(db, "SELECT policy_rate_bps FROM economy_results WHERE period = 8")[0]["policy_rate_bps"]
    calm = careers.fund_returns(db, 8, level, rate)
    # Shares fall by a fifth: Growth is hit hardest, Income not at all.
    crash = careers.fund_returns(db, 8, level * 80 // 100, rate)
    assert crash["growth"]["return_bps"] < crash["balanced"]["return_bps"] < crash["cautious"]["return_bps"] < 0
    assert crash["income"]["return_bps"] == calm["income"]["return_bps"] > 0
    # The Central Bank raises its rate by two points: bonds already held are worth less. Cautious and Income lose.
    squeeze = careers.fund_returns(db, 8, level, rate + 200)
    assert squeeze["cautious"]["return_bps"] < 0 and squeeze["income"]["return_bps"] < 0
    assert squeeze["cautious"]["return_bps"] < squeeze["growth"]["return_bps"]
    assert squeeze["growth"]["bonds_part_bps"] < calm["growth"]["bonds_part_bps"]
    # And every quarter of the first two years has been written down, with what made it up.
    past = _dicts(db, "SELECT fund, return_bps FROM pension_fund_results")
    assert len(past) == 32


def test_the_career_page_shows_each_funds_best_and_worst_quarter_and_its_growth_after_prices(db):
    player, _ = professional(db, now=NOW9)
    db.execute("INSERT INTO retirement_accounts (player_id) VALUES (%s) ON CONFLICT DO NOTHING", (player,))
    shown = careers.profile(db, player, NOW9)["retirement"]
    for fund in shown["funds"]:
        assert fund["bad"] and fund["worst_bps"] <= fund["last_return_bps"] <= fund["best_bps"]
        assert fund["year_bps"] is not None and fund["year_after_prices_bps"] < fund["year_bps"]


# ---------------------------------------------------------------------------
# Saving more is rewarded
# ---------------------------------------------------------------------------

def test_extra_saving_lowers_the_tax_and_the_employer_matches_part_of_it():
    gross = careers.salary_per_quarter(5)
    plain, more = careers.split_salary(gross), careers.split_salary(gross, 1000)
    assert more["extra_saving"] == gross // 10 and more["employer_match"] == apply_bps(gross, data.EMPLOYER_MATCH_MOST_BPS)
    assert more["tax"] == apply_bps(gross - gross // 10, data.SALARY_TAX_BPS) < plain["tax"]
    assert more["pension_yours"] + more["tax"] + more["living_costs"] + more["take_home"] == gross
    # Every naira saved costs less than a naira of take-home pay, and brings the employer's match with it.
    assert plain["take_home"] - more["take_home"] < more["extra_saving"]
    assert (more["pension_yours"] + more["pension_employer"]) - (plain["pension_yours"] + plain["pension_employer"]) \
        == more["extra_saving"] + more["employer_match"]
    assert careers.split_salary(gross, 100)["employer_match"] == gross // 100          # matched naira for naira below the limit
    assert careers.split_salary(gross, 9_999)["extra_saving"] == apply_bps(gross, data.EXTRA_SAVING_MOST_BPS)


def test_extra_saving_is_paid_on_pay_day_by_the_employer_to_the_pension_funds_and_nothing_is_made(db):
    player, account = professional(db, now=NOW9)
    for bad in (-100, 2100, 550, 99_999):
        with pytest.raises(careers.CareerError):
            careers.set_extra_saving(db, player, bad, NOW9)
    careers.set_extra_saving(db, player, 1000, NOW9)
    pass_one(db, player, NOW9)
    funds = ledger.account_id(db, ledger.INVESTORS_INSTITUTIONS)
    assert quarters.close_due_quarters(db, after_quarters(9)) == [9]
    slip = _dicts(db, "SELECT * FROM payslips WHERE player_id = %s", (player,))[0]
    assert slip["extra_saving"] > 0 and slip["employer_match"] > 0 and slip["paid"] == slip["take_home"]
    paid = _dicts(db, "SELECT sum(l.amount)::bigint AS amount FROM ledger_entries l JOIN ledger_transactions t ON t.id = l.transaction_id"
                      " WHERE t.reference = %s AND l.account_id = %s", (f"salary:{player}:9", funds))[0]["amount"]
    assert paid == slip["extra_saving"] + slip["employer_match"]
    entry = _dicts(db, "SELECT * FROM retirement_entries WHERE player_id = %s", (player,))[0]
    assert entry["paid_in_by_you"] == slip["pension_yours"] and entry["paid_in_by_employer"] == slip["pension_employer"]
    sound(db)


def test_the_sound_finances_mark_comes_from_savings_worth_two_quarters_of_salary(db):
    player, _ = professional(db, now=NOW9)
    assert careers.sound_finances(db, player) is False
    savings(db, player, 1_799_999)
    assert careers.sound_finances(db, player) is False
    savings(db, player, 1_800_000)                                               # two quarters of a Level 1 salary at the start of the game
    assert careers.sound_finances(db, player) is True
    wages = careers.world_now(db, NOW9)["wage_index_bps"]                        # the mark keeps pace with wages
    assert careers.profile(db, player, NOW9)["retirement"]["sound_finances"] is (wages <= BPS)
    savings(db, player, 1_800_000 * wages // BPS + 1)
    assert careers.profile(db, player, NOW9)["retirement"]["sound_finances"] is True


def test_the_one_early_withdrawal_is_for_founding_an_empire_takes_at_most_half_and_goes_straight_into_the_empire(db):
    head, account = pro(db, "asset_manager", "chief", level=20, cash_naira=30_000_000)
    savings(db, head, 10_000_000)
    with pytest.raises(empires.EmpireError, match="up to half"):
        empires.found(db, head, "Lagoon House", naira(1_000_000), naira(5_000_001), NOW9)
    assert empires.seat_of(db, head) is None                                   # the refused founding left nothing behind
    before = ledger.balance(db, account)
    empire = empires.found(db, head, "Lagoon House", naira(29_000_000), naira(5_000_000), NOW9)
    assert ledger.balance(db, account) == before - naira(29_000_000)           # the withdrawal never passes through the player's hands
    assert ledger.balance(db, empire["account_id"]) == naira(34_000_000)
    assert _dicts(db, "SELECT value FROM retirement_accounts WHERE player_id = %s", (head,))[0]["value"] == naira(5_000_000)
    with pytest.raises(empires.EmpireError, match="already been made"):
        empires.put_in(db, head, naira(1_000), naira(1_000), NOW9)
    assert careers.profile(db, head, NOW9)["retirement"]["early_withdrawal_used"] is True
    # If the founding is cancelled, the savings go back where they came from: the withdrawal cannot be used to get at the cash.
    empires.cancel_founding(db, head, NOW9)
    assert ledger.balance(db, account) == before
    after = _dicts(db, "SELECT value, early_withdrawn_period FROM retirement_accounts WHERE player_id = %s", (head,))[0]
    assert after == {"value": naira(10_000_000), "early_withdrawn_period": None}
    sound(db)


# ---------------------------------------------------------------------------
# Retirement
# ---------------------------------------------------------------------------

def test_retirement_opens_after_ten_game_years_of_work_and_a_pension_is_then_paid_every_quarter(db, monkeypatch):
    player, account = professional(db, now=NOW9)
    savings(db, player, 4_000_000)
    assert data.RETIREMENT_AFTER_QUARTERS == 40 and data.RETIREMENT_LEVEL == 50
    assert careers.retirement_opens(db, player, 9)["quarters_to_go"] == 40
    with pytest.raises(careers.CareerError, match="40 quarters to go"):
        careers.retire(db, player, NOW9)
    # Only quarters the player was paid for count: holding a job without working does not.
    pass_one(db, player, NOW9)
    assert quarters.close_due_quarters(db, after_quarters(9)) == [9]
    now = after_quarters(9) + timedelta(hours=12)
    assert careers.retirement_opens(db, player, 10)["quarters_worked"] == 1
    monkeypatch.setattr(data, "RETIREMENT_AFTER_QUARTERS", 1)                  # as if the ten years had passed
    assert careers.profile(db, player, now)["retirement"]["can_retire"] is True
    careers.retire(db, player, now)
    with pytest.raises(careers.CareerError, match="already being paid"):
        careers.retire(db, player, now)
    before = ledger.balance(db, account)
    assert quarters.close_due_quarters(db, after_quarters(10)) == [10]
    entry = _dicts(db, "SELECT * FROM retirement_entries WHERE player_id = %s AND period = 10", (player,))[0]
    assert entry["paid_out"] == apply_bps(entry["opening"] + entry["growth"] + entry["paid_in_by_you"] + entry["paid_in_by_employer"],
                                          data.PENSION_PAID_BPS) > 0
    assert entry["closing"] == entry["opening"] + entry["growth"] + entry["paid_in_by_you"] + entry["paid_in_by_employer"] - entry["paid_out"]
    got = _dicts(db, "SELECT sum(l.amount)::bigint AS amount FROM ledger_entries l JOIN ledger_transactions t ON t.id = l.transaction_id"
                     " WHERE t.kind = 'pension_to_player' AND l.account_id = %s", (account,))[0]["amount"]
    assert got == entry["paid_out"] and ledger.balance(db, account) >= before + got
    sound(db)


# ---------------------------------------------------------------------------
# Pension funds run by players
# ---------------------------------------------------------------------------

def a_fund(db, fee_bps=25):
    manager, account = pro(db, "asset_manager", "steward", level=20, cash_naira=8_000_000)
    return pensionfunds.open_fund(db, manager, "Harmattan Pensions", fee_bps, NOW9), manager, account


def test_only_a_level_twenty_asset_manager_may_open_a_pension_fund_once_for_a_fee(db):
    junior, _ = pro(db, "asset_manager", "junior", level=19, cash_naira=8_000_000)
    counsel, _ = pro(db, "investment_banker", "counsel", level=20, cash_naira=8_000_000)
    for who in (junior, counsel):
        with pytest.raises(pensionfunds.FundError, match="Level 20"):
            pensionfunds.open_fund(db, who, "Too Soon Pensions", 10, NOW9)
    poor, _ = pro(db, "asset_manager", "poor", level=20, cash_naira=1_000_000)
    with pytest.raises(pensionfunds.FundError, match="costs"):
        pensionfunds.open_fund(db, poor, "Poor Pensions", 10, NOW9)
    assert not _dicts(db, "SELECT 1 FROM empires WHERE kind = 'pension'")
    pool = ledger.balance(db, ledger.account_id(db, ledger.PRIZE_POOL))
    fund, manager, _ = a_fund(db)
    assert ledger.balance(db, ledger.account_id(db, ledger.PRIZE_POOL)) == pool + naira(data.FUND_REGISTRATION_NAIRA)
    for fee in (51, -1, 2.5):
        with pytest.raises(pensionfunds.FundError):
            pensionfunds.open_fund(db, poor, "Greedy Pensions", fee, NOW9)
    with pytest.raises(pensionfunds.FundError, match="once"):
        pensionfunds.open_fund(db, manager, "Second Pensions", 10, NOW9)
    # The fee can be lowered, never raised. A fund is not an empire: nobody takes a seat in it or sees it in the league.
    with pytest.raises(pensionfunds.FundError, match="never raised"):
        pensionfunds.set_fee(db, manager, 30, NOW9)
    pensionfunds.set_fee(db, manager, 20, NOW9)
    with pytest.raises(empires.EmpireError):
        empires.apply(db, junior, fund["id"], NOW9)
    assert fund["id"] not in {e["id"] for e in empires.league(db, NOW9)}
    sound(db)


def joined(db, saver, fund) -> None:
    """A saver asks to join, and the quarter's close carries it out."""
    pensionfunds.join(db, saver, fund["id"], NOW9)
    pensionfunds._carry_out_joins(db, pensionfunds._fund(db, fund["id"]), 9, NOW9)


def test_a_saver_moves_real_money_into_a_fund_owns_units_and_can_always_get_out(db):
    fund, manager, _ = a_fund(db)
    saver, _ = professional(db, "saver", now=NOW9)
    db.execute("UPDATE retirement_accounts SET value = 0 WHERE player_id = %s", (saver,))
    with pytest.raises(pensionfunds.FundError, match="at least"):
        pensionfunds.join(db, saver, fund["id"], NOW9)
    savings(db, saver, 2_000_000)
    with pytest.raises(pensionfunds.FundError, match="own pension"):
        pensionfunds.join(db, manager, fund["id"], NOW9)
    # Asking to join moves nothing yet: it is carried out as the quarter closes, like any change of fund.
    pensionfunds.join(db, saver, fund["id"], NOW9)
    assert ledger.balance(db, fund["account_id"]) == 0
    assert {f["id"]: f for f in pensionfunds.listing(db, saver, NOW9)["funds"]}[fund["id"]]["joining"] is True
    with pytest.raises(pensionfunds.FundError, match="on their way"):
        pensionfunds.join(db, saver, fund["id"], NOW9)
    with pytest.raises(careers.CareerError, match="on their way"):
        careers.choose_fund(db, saver, "growth", NOW9)
    pensionfunds._carry_out_joins(db, fund, 9, NOW9)
    assert ledger.balance(db, fund["account_id"]) == naira(2_000_000)
    assert careers.profile(db, saver, NOW9)["retirement"]["value"] == naira(2_000_000)
    # The manager invests it. A second saver joins at the value of a unit then, and takes nothing from the first.
    bill = next(b for b in bonds.listing(db, NOW9) if b["kind"] == "bill")
    pensionfunds.trade_bonds(db, manager, code=bill["code"], side="buy", units=1500, now=NOW9)
    worth = pensionfunds.worth(db, pensionfunds._fund(db, fund["id"]), NOW9)["total"]
    second, _ = professional(db, "second", now=NOW9)
    savings(db, second, 1_000_000)
    joined(db, second, fund)
    shown = {f["id"]: f for f in pensionfunds.listing(db, saver, NOW9)["funds"]}[fund["id"]]
    assert shown["savers"] == 2 and worth - 2 <= shown["your_value"] <= worth + 100
    # Somebody who is not the manager cannot touch the fund.
    for attempt in (lambda: pensionfunds.trade_bonds(db, saver, code=bill["code"], side="sell", units=1, now=NOW9),
                    lambda: pensionfunds.divert(db, saver, naira(1), NOW9)):
        with pytest.raises(pensionfunds.FundError, match="manage no pension fund"):
            attempt()
    # The first saver asks for the savings back. They are paid as the quarter closes; until then the manager can
    # buy nothing more, and the regulator sells bonds if the fund has too little cash.
    assert pensionfunds.leave(db, saver, NOW9)["done"] is False
    with pytest.raises(pensionfunds.FundError, match="can buy nothing"):
        pensionfunds.trade_bonds(db, manager, code=bill["code"], side="buy", units=1, now=NOW9)
    assert quarters.close_due_quarters(db, after_quarters(9)) == [9]
    after = _dicts(db, "SELECT * FROM retirement_accounts WHERE player_id = %s", (saver,))[0]
    assert after["managed_fund_id"] is None and after["units"] == 0 and not after["leaving"]
    assert naira(1_900_000) < after["value"] < naira(2_200_000)
    assert _dicts(db, "SELECT savers FROM fund_prices WHERE fund_id = %s AND period = 9", (fund["id"],))[0]["savers"] == 1
    sound(db)


def test_a_manager_who_takes_savers_money_is_found_repays_with_a_fine_and_is_struck_off(db, monkeypatch):
    fund, manager, account = a_fund(db)
    saver, _ = professional(db, "saver", now=NOW9)
    savings(db, saver, 10_000_000)
    joined(db, saver, fund)
    with pytest.raises(pensionfunds.FundError, match="can sign for"):
        pensionfunds.divert(db, manager, naira(100_001), NOW9)                 # 1% of the fund in a quarter
    pensionfunds.divert(db, manager, naira(100_000), NOW9)
    assert ledger.balance(db, fund["account_id"]) == naira(9_900_000)
    books = pensionfunds.manager_view(db, manager, NOW9)["books"]
    assert books[0]["category"] == "Custody and dealing costs" and "genuine" not in books[0] and "kind" not in books[0]
    always(monkeypatch, True)
    before = ledger.balance(db, account)
    pensionfunds.after_close(db, 9, NOW9)                                      # the regulator's audit, as the quarter closes
    assert ledger.balance(db, account) == before - naira(200_000)
    after = pensionfunds._fund(db, fund["id"])
    assert after["struck_off"] and after["head_player_id"] is None and after["fee_bps"] == 0
    assert pensionfunds.worth(db, after, NOW9)["total"] == naira(10_100_000)   # the savers got it back, and the fine with it
    assert len(_dicts(db, "SELECT 1 FROM career_events WHERE kind = 'struck_off'")) == 1
    with pytest.raises(pensionfunds.FundError, match="manage no pension fund"):
        pensionfunds.divert(db, manager, naira(1), NOW9)
    with pytest.raises(pensionfunds.FundError):
        pensionfunds.open_fund(db, manager, "Second Chance Pensions", 10, NOW9)
    newcomer, _ = professional(db, "newcomer", now=NOW9)
    savings(db, newcomer, 1_000_000)
    with pytest.raises(pensionfunds.FundError, match="not taking savers"):
        pensionfunds.join(db, newcomer, fund["id"], NOW9)
    pensionfunds.leave(db, saver, NOW9)
    pensionfunds._settle(db, pensionfunds._fund(db, fund["id"]), NOW9)         # as the next close would
    assert _dicts(db, "SELECT value FROM retirement_accounts WHERE player_id = %s", (saver,))[0]["value"] == naira(10_100_000)
    sound(db)


def test_a_saver_can_hire_the_ai_audit_of_their_fund_in_an_audit_season(db, monkeypatch):
    fund, manager, account = a_fund(db, fee_bps=50)
    saver, saver_account = professional(db, "saver", now=NOW9, cash_naira=2_000_000)
    savings(db, saver, 10_000_000)
    joined(db, saver, fund)
    pensionfunds.divert(db, manager, naira(50_000), NOW9)
    with pytest.raises(pensionfunds.FundError, match="only in an audit season"):
        pensionfunds.ai_audit(db, saver, NOW9)
    monkeypatch.setattr(data, "AUDIT_SEASON_EVERY", 3)
    always(monkeypatch, True)
    cash = ledger.balance(db, saver_account)
    done = pensionfunds.ai_audit(db, saver, NOW9)
    assert done["found"] == 1 and done["fee"] == naira(data.FUND_AI_AUDIT_LEAST_NAIRA) == cash - ledger.balance(db, saver_account)
    assert pensionfunds._fund(db, fund["id"])["struck_off"]
    sound(db)


def test_the_managers_fee_is_paid_from_the_fund_each_quarter_and_contributions_buy_units(db, monkeypatch):
    fund, manager, account = a_fund(db, fee_bps=50)
    saver, _ = professional(db, "saver", now=NOW9)
    savings(db, saver, 10_000_000)
    joined(db, saver, fund)
    pass_one(db, saver, NOW9)
    before = ledger.balance(db, account)
    always(monkeypatch, False)
    assert quarters.close_due_quarters(db, after_quarters(9)) == [9]
    assert ledger.balance(db, account) - before >= naira(50_000)              # half of one percent of ₦10 million, and the manager's own salary
    entry = _dicts(db, "SELECT * FROM retirement_entries WHERE player_id = %s AND period = 9", (saver,))[0]
    assert entry["fund"] == "managed" and entry["paid_in_by_you"] > 0
    assert entry["closing"] == entry["opening"] + entry["growth"] + entry["paid_in_by_you"] + entry["paid_in_by_employer"]
    assert naira(10_000_000) < entry["closing"] < naira(10_400_000)
    assert _dicts(db, "SELECT category FROM empire_books WHERE empire_id = %s", (fund["id"],))[0]["category"] == "Manager's fee"
    sound(db)
