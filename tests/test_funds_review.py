"""Run Your Own Fund: what the independent review found, each fixed and tested."""

from __future__ import annotations

from datetime import timedelta

import pytest

from simulation import empires, exchange, funds, ledger
from simulation import world_data as data
from simulation.money import naira
from tests.test_funds import (
    DAY,
    OPEN,
    _invested_in_shares,
    _one,
    dealers_have_cash,
    investor,
    launch,
    manager,
    ring,
    sound,
)
from tests.test_market import trader


def _f(db, fund_id):
    return _one(db, "SELECT * FROM investment_funds WHERE id = %s", (fund_id,))


def _idc(db):
    return _one(db, "SELECT reference_price FROM market_instruments m JOIN companies c ON c.id = m.company_id WHERE c.ticker = 'IDC'")["reference_price"]


def test_r1_money_coming_in_at_the_same_bell_as_leavers_buys_units_at_a_fair_price(db):
    ada, _ = manager(db)
    fund = launch(db, ada)
    bola, _ = investor(db, "bola", cash_naira=20_000_000)
    funds.invest(db, bola, fund["id"], naira(10_000_000), OPEN)
    ring(db, DAY)
    funds.leave(db, bola, fund["id"], None, OPEN + timedelta(days=1))           # half the fund leaves...
    chidi, chidi_account = investor(db, "chidi")
    funds.invest(db, chidi, fund["id"], naira(2_000_000), OPEN + timedelta(days=1))  # ...as somebody new comes in
    ring(db, DAY + timedelta(days=1))
    worth = funds.worth(db, _f(db, fund["id"]), OPEN + timedelta(days=2))
    mine = _one(db, "SELECT units FROM fund_units WHERE fund_id = %s AND account_id = %s", (fund["id"], chidi_account))["units"]
    value = mine * worth // _f(db, fund["id"])["units"]
    assert naira(1_990_000) < value <= naira(2_000_000)                          # not half of it, as before the fix
    sound(db)


def test_r2_closing_a_fund_does_not_escape_the_regulators_audit(db, monkeypatch):
    ada, _ = manager(db)
    fund = launch(db, ada)
    funds.take_costs(db, ada, naira(50_000), OPEN)
    funds.close(db, ada, OPEN)
    monkeypatch.setattr(data, "INVEST_FUND_AUDIT_FINDS_BPS", 10_000)
    ring(db, DAY)
    assert _one(db, "SELECT kind FROM legal_records WHERE player_id = %s", (ada,))["kind"] == "theft"
    assert _f(db, fund["id"])["status"] == "closed" and _f(db, fund["id"])["regulator_run"]
    sound(db)


def test_r3_a_manager_cannot_sell_their_own_shares_into_the_funds_waiting_order(db):
    ada, ada_account = manager(db)
    launch(db, ada)
    price = _idc(db)
    funds.trade_shares(db, ada, ticker="IDC", side="buy", quantity=100, limit_price=price, now=OPEN)   # rests: nobody sells
    ledger.transfer(db, payer=ledger.account_id(db, ledger.INVESTORS_PUBLIC), receiver=ada_account, amount=500, asset="SHR-IDC",
                    kind="test_shares", memo="Test: shares")
    with pytest.raises(empires.EmpireError, match="a fund you manage"):
        empires.own_order_allowed(db, ada_account, _one(db, "SELECT id FROM companies WHERE ticker = 'IDC'")["id"], "sell")


def test_r4_waiting_buy_orders_count_against_the_ten_percent_limit(db):
    ada, _ = manager(db)
    launch(db, ada)
    price = _idc(db)
    qty = naira(10_000_000) * 45 // 1000 // price                                 # 45% of the limit each
    funds.trade_shares(db, ada, ticker="IDC", side="buy", quantity=qty, limit_price=price, now=OPEN)
    funds.trade_shares(db, ada, ticker="IDC", side="buy", quantity=qty, limit_price=price, now=OPEN)
    with pytest.raises(funds.FundError, match="10%"):
        funds.trade_shares(db, ada, ticker="IDC", side="buy", quantity=qty, limit_price=price, now=OPEN)


def test_r5_a_gate_cannot_go_straight_back_up(db):
    ada, _ = manager(db)
    launch(db, ada)
    funds.set_gate(db, ada, True, OPEN)
    funds.set_gate(db, ada, False, OPEN + timedelta(minutes=1))
    with pytest.raises(funds.FundError, match="again only"):
        funds.set_gate(db, ada, True, OPEN + timedelta(minutes=2))


def test_r6_a_merger_hands_back_waiting_money_refuses_new_money_and_keeps_strategies_apart(db):
    ada, _ = manager(db)
    fund = launch(db, ada)
    tola, _ = manager(db, "tola")
    bonds_fund = launch(db, tola, name="Lekki Bond Fund", strategy="bonds")
    with pytest.raises(funds.FundError, match="same strategy"):
        funds.propose_merge(db, ada, bonds_fund["id"], OPEN)
    kemi, _ = manager(db, "kemi")
    other = launch(db, kemi, name="Lekki Anything Fund", strategy="anything")
    merge = funds.propose_merge(db, ada, other["id"], OPEN)
    bola, account = investor(db, "bola")
    funds.invest(db, bola, fund["id"], naira(1_000_000), OPEN)
    funds.answer_merge(db, kemi, merge["id"], True, OPEN)
    late, _ = investor(db, "late")
    with pytest.raises(funds.FundError, match="merge"):
        funds.invest(db, late, fund["id"], naira(1_000_000), OPEN + timedelta(minutes=5))
    # Bola's order was placed before the merger was agreed: it is dealt at the first bell; then the merger takes effect.
    for k in range(5):
        ring(db, DAY + timedelta(days=k))
    assert _f(db, fund["id"])["status"] == "merged"
    assert ledger.balance(db, funds.dealing_account(db)) == 0
    sound(db)


def test_r7_a_closing_fund_does_not_sell_a_halted_share_at_its_old_price(db):
    ada, _ = manager(db)
    fund = launch(db, ada)
    ring(db, DAY)
    dealers_have_cash(db)
    _invested_in_shares(db, ada, _f(db, fund["id"]))
    db.execute("UPDATE market_instruments SET halted_reason = 'Test: bad news' WHERE company_id = (SELECT id FROM companies WHERE ticker = 'IDC')")
    funds.close(db, ada, OPEN + timedelta(days=1))
    ring(db, DAY + timedelta(days=1))
    f = _f(db, fund["id"])
    assert f["status"] == "closing" and ledger.balance(db, f["account_id"], "SHR-IDC") > 0      # it waits for the share to trade again
    db.execute("UPDATE market_instruments SET halted_reason = NULL")
    exchange.withdraw(db, [f["account_id"]], OPEN + timedelta(days=2), "test")
    ring(db, DAY + timedelta(days=2))
    assert _f(db, fund["id"])["status"] == "closed"
    sound(db)


def test_r8_a_bond_fund_short_of_cash_sells_its_bonds_to_pay_leavers(db):
    ada, _ = manager(db)
    fund = launch(db, ada, strategy="bonds")
    dealers_have_cash(db)
    bola, _ = investor(db, "bola", cash_naira=40_000_000)
    funds.invest(db, bola, fund["id"], naira(30_000_000), OPEN)
    ring(db, DAY)
    bill = _one(db, "SELECT substr(asset, 5) AS code FROM bonds WHERE issuer = 'government' AND kind = 'bill' AND redeemed_period IS NULL"
                    " ORDER BY maturity_period LIMIT 1")["code"]
    f = _f(db, fund["id"])
    from simulation import bonds
    b = bonds.find(db, bill)
    units = ledger.balance(db, f["account_id"]) * 85 // 100 // bonds.fair_value(b, bonds.market(db, OPEN))
    funds.trade_bonds(db, ada, code=bill, side="buy", units=units, now=OPEN + timedelta(days=1))
    funds.leave(db, bola, fund["id"], None, OPEN + timedelta(days=1))
    ring(db, DAY + timedelta(days=1))
    assert _one(db, "SELECT count(*) AS n FROM ledger_transactions WHERE kind = 'fund_bond_sale'")["n"] >= 1
    ring(db, DAY + timedelta(days=2))
    assert _one(db, "SELECT status FROM fund_orders WHERE fund_id = %s AND side = 'out'", (fund["id"],))["status"] == "dealt"
    sound(db)


def test_r9_orders_placed_after_the_market_closes_wait_and_cannot_be_taken_back_once_it_has(db):
    ada, _ = manager(db)
    fund = launch(db, ada)
    bola, _ = investor(db, "bola")
    before = funds.invest(db, bola, fund["id"], naira(1_000_000), OPEN.replace(hour=21, minute=50))
    with pytest.raises(funds.FundError, match="no longer be taken back"):
        funds.cancel(db, bola, before["id"], OPEN.replace(hour=22, minute=1))
    after = funds.invest(db, bola, fund["id"], naira(1_000_000), OPEN.replace(hour=22, minute=1))
    ring(db, DAY)
    assert _one(db, "SELECT status FROM fund_orders WHERE id = %s", (before["id"],))["status"] == "dealt"
    assert _one(db, "SELECT status FROM fund_orders WHERE id = %s", (after["id"],))["status"] == "waiting"


def test_r10_a_factsheet_does_not_show_the_days_money_in_and_out(db):
    ada, _ = manager(db)
    fund = launch(db, ada)
    sheet = funds.factsheet(db, fund["id"], ada, OPEN)
    assert "flows" not in sheet and "money_in" not in str(sheet)


def test_r11_holders_paid_out_as_a_fund_closes_see_what_they_were_paid(db):
    ada, _ = manager(db)
    fund = launch(db, ada)
    bola, _ = investor(db, "bola")
    funds.invest(db, bola, fund["id"], naira(2_000_000), OPEN)
    ring(db, DAY)
    funds.set_gate(db, ada, True, OPEN + timedelta(days=1))
    funds.leave(db, bola, fund["id"], None, OPEN + timedelta(days=1))
    funds.close(db, ada, OPEN + timedelta(days=1))
    ring(db, DAY + timedelta(days=1))
    order = _one(db, "SELECT * FROM fund_orders WHERE fund_id = %s AND side = 'out'", (fund["id"],))
    assert order["status"] == "dealt" and order["paid"] > naira(1_900_000)


def test_r12_the_least_a_new_investor_puts_in_is_judged_by_the_account_investing(db):
    ada, _ = manager(db)
    fund = launch(db, ada, least_in=naira(500_000))
    # The manager personally holds units; that does not let anybody else put in less than the least.
    bola, _ = investor(db, "bola")
    with pytest.raises(funds.FundError, match="least"):
        funds.invest(db, bola, fund["id"], naira(100_000), OPEN)
    funds.invest(db, ada, fund["id"], naira(100_000), OPEN)                     # the manager already holds units: a top-up


def test_r13_a_run_counts_as_survived_only_when_the_fund_lasted_a_quarter_after_it(db):
    ada, _ = manager(db)
    fund = launch(db, ada)
    db.execute("INSERT INTO fund_alerts (fund_id, kind, everyone, headline, words, at) VALUES (%s, 'run', true, 'x', 'y', %s)", (fund["id"], OPEN))
    assert funds.track_record(db, ada)["runs_survived"] == 0
    ring(db, DAY + timedelta(days=8))
    assert funds.track_record(db, ada)["runs_survived"] == 1
    db.execute("UPDATE investment_funds SET status = 'closed', closed_at = %s WHERE id = %s", (OPEN + timedelta(days=2), fund["id"]))
    assert funds.track_record(db, ada)["runs_survived"] == 0
    assert trader
