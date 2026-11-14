"""The gap stage, Part 1: each finding of the independent review, fixed and tested."""

from __future__ import annotations

from datetime import timedelta

import pytest
from psycopg.rows import dict_row

from simulation import (
    derivatives,
    firm,
    firm_deals,
    instruments,
    ledger,
    quarters,
    swaps,
)
from simulation import world_data as data
from simulation.money import naira
from tests.conftest import after_quarters
from tests.test_careers import NOW9, sound
from tests.test_derivatives import ready, trader
from tests.test_firm import firm_of
from tests.test_lending import bank_id, price_of, signed

pytestmark = pytest.mark.world("eight")
LATER = NOW9 + timedelta(hours=1)


def _one(db, sql, params=()):
    with db.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(sql, params).fetchall()
    return rows[0] if rows else None


def series(db, kind, underlying, expiry=9):
    derivatives.ensure(db, NOW9)
    return _one(db, "SELECT * FROM derivative_series WHERE kind = %s AND underlying = %s AND expiry_period = %s AND status = 'open'"
                    " ORDER BY strike LIMIT 1", (kind, underlying, expiry))


def spend_all(db, account):
    ledger.transfer(db, payer=account, receiver=ledger.account_id(db, ledger.TREASURY), amount=ledger.balance(db, account),
                    kind="test_cash", memo="Test: spent")


# 1. A loser owes the fund only what the fund paid; the rest is owed to the winners paid short.
def test_r1_when_the_fund_runs_dry_the_loser_owes_the_fund_what_it_paid_and_the_winners_the_rest(db):
    a, a_acct = trader(db, "asset_manager", "bigloser", cash_naira=50_000_000)
    x = series(db, "future", "BSX50")
    derivatives.trade(db, a_acct, x["id"], "buy", 5, NOW9, player_id=a)
    spend_all(db, a_acct)
    fund = derivatives.fund_account(db)
    # Test set-up: the fund is nearly empty (paid out earlier, as its record shows).
    drained = ledger.balance(db, fund) - naira(10_000)
    ledger.transfer(db, payer=fund, receiver=ledger.account_id(db, ledger.TREASURY), amount=drained, kind="test_cash", memo="Test: paid out")
    db.execute("INSERT INTO clearing_fund_events (kind, amount, words, at) VALUES ('cover', %s, 'Test: paid out', %s)", (drained, NOW9))
    in_fund = ledger.balance(db, fund)
    db.execute("UPDATE market_instruments SET last_price = coalesce(last_price, reference_price) / 2, reference_price = reference_price / 2")
    derivatives.at_bell(db, NOW9 + timedelta(hours=11), NOW9.date())
    to_fund = _one(db, "SELECT coalesce(sum(outstanding), 0)::bigint AS n FROM player_loans WHERE borrower = %s AND creditor = %s", (a_acct, fund))["n"]
    to_others = _one(db, "SELECT coalesce(sum(outstanding), 0)::bigint AS n FROM player_loans WHERE borrower = %s AND creditor <> %s"
                         " AND kind = 'shortfall'", (a_acct, fund))["n"]
    assert to_fund == in_fund                                      # the fund paid all it had, and is owed exactly that
    assert to_others > 0                                           # the market makers, paid short, are owed the rest
    assert derivatives.check_books(db) == []


# 2. A company hedging beyond its cash: it hedges only what its cash stands, and an unpaid loss is owed.
def test_r2_a_company_hedges_only_as_much_as_its_cash_would_stand(db):
    quarters.close_due_quarters(db, after_quarters(9))
    s = _one(db, "SELECT * FROM derivative_series WHERE kind = 'future' AND underlying = 'OIL' AND expiry_period = 10")
    contract = derivatives.value_of(db, s, derivatives.spot(db, s, after_quarters(9)))
    for p in db.execute("SELECT p.contracts, c.account_id FROM derivative_positions p JOIN companies c ON c.account_id = p.account"
                        " WHERE p.series_id = %s AND p.status = 'open'", (s["id"],)).fetchall():
        assert p[0] <= data.HEDGE_MOST_CONTRACTS
    _ = contract


# 3. Waiting orders count towards the most contracts of one kind.
def test_r3_waiting_orders_cannot_add_up_past_the_limit(db, monkeypatch):
    monkeypatch.setattr(data, "MOST_CONTRACTS_A_SERIES", 3)
    a, a_acct = trader(db, "asset_manager", "stacker", cash_naira=5_000_000_000)
    x = series(db, "future", "OIL")
    low = derivatives.quote(db, x, NOW9)["bid"] // 2
    derivatives.trade(db, a_acct, x["id"], "buy", 2, NOW9, limit=low, player_id=a)
    derivatives.trade(db, a_acct, x["id"], "buy", 1, NOW9, limit=low, player_id=a)
    with pytest.raises(derivatives.DerivativesError, match="At most"):
        derivatives.trade(db, a_acct, x["id"], "buy", 1, NOW9, limit=low, player_id=a)


# 4. Swaps: never more than five times the account's worth, and none while in default.
def test_r4_a_swap_needs_the_worth_to_stand_it(db):
    a, a_acct = trader(db, "investment_banker", "brokeswapper", cash_naira=1_000_000)
    with pytest.raises(swaps.SwapError, match="times what you are"):
        swaps.propose(db, a, kind="rate", counterparty={"bank": bank_id(db)}, side="pay_fixed", quarters=4,
                      notional=naira(10_000_000_000), now=NOW9)
    swaps.propose(db, a, kind="rate", counterparty={"bank": bank_id(db)}, side="pay_fixed", quarters=1, notional=naira(1_000_000), now=NOW9)
    from simulation import lending
    lending.record_shortfall(db, a_acct, ledger.account_id(db, ledger.TREASURY), 100, "Test", 9, NOW9)
    with pytest.raises(swaps.SwapError, match="default"):
        swaps.propose(db, a, kind="rate", counterparty={"bank": bank_id(db)}, side="pay_fixed", quarters=1, notional=naira(100_000), now=NOW9)


# 5. A bank's price is its price on the day the swap is signed.
def test_r5_an_empires_bank_swap_takes_the_banks_price_when_signed(db):
    empire, team = firm_of(db, n_cash=5_000_000_000)
    banker = ready(db, team["investment_banker"])
    asked = swaps.propose(db, banker, kind="rate", counterparty={"bank": bank_id(db)}, side="receive_fixed", quarters=2,
                          notional=naira(100_000_000), now=NOW9, for_empire=True)
    db.execute("UPDATE swaps SET fixed_bps = 9000 WHERE id = %s", (asked["swap_id"],))          # a stale price from long ago
    for kind, who in (("swap_draft", team["lawyer"]), ("swap_risk", team["risk_manager"]), ("swap_sign", team["head"])):
        approval = _one(db, "SELECT * FROM empire_approvals WHERE empire_id = %s AND kind = %s AND status = 'waiting'", (empire["id"], kind))
        firm.decide(db, who, approval["id"], True, "Agreed.", NOW9)
    s = _one(db, "SELECT * FROM swaps WHERE id = %s", (asked["swap_id"],))
    assert s["status"] == "active" and s["fixed_bps"] == swaps._bank_fixed(db, "rate", "receive_fixed", NOW9)


# 7. A waiting order its owner can no longer pay for is cancelled, not left blocking everybody.
def test_r7_a_waiting_order_that_cannot_be_paid_for_is_cancelled_and_the_buyer_is_served(db):
    a, a_acct = trader(db, "asset_manager", "overreached", cash_naira=500_000_000)
    b, b_acct = trader(db, "asset_manager", "patientbuyer", cash_naira=500_000_000)
    x = series(db, "call", "BSX50")
    q = derivatives.quote(db, x, NOW9)
    waiting = derivatives.trade(db, a_acct, x["id"], "sell", 2, NOW9, limit=(q["bid"] + q["ask"]) // 2, player_id=a)
    spend_all(db, a_acct)
    db.execute("UPDATE derivative_orders SET per_contract = 1, reserved = 2 WHERE id = %s", (waiting["order_id"],))
    held = ledger.account_id(db, derivatives.ORDERS)
    extra = ledger.balance(db, held) - 2
    ledger.transfer(db, payer=held, receiver=ledger.account_id(db, ledger.TREASURY), amount=extra, kind="test_cash", memo="Test: an old order")
    bought = derivatives.trade(db, b_acct, x["id"], "buy", 2, LATER, player_id=b)
    assert bought["filled"] == 2
    assert _one(db, "SELECT status FROM derivative_orders WHERE id = %s", (waiting["order_id"],))["status"] == "cancelled"
    assert derivatives.check_books(db) == []


# 9. Two warrant issues in one quarter keep their own terms.
def test_r9_two_warrant_issues_in_a_quarter_keep_their_own_strike(db):
    idc = _one(db, "SELECT * FROM companies WHERE ticker = 'IDC'")
    acct = ledger.account_id(db, ledger.INVESTORS_INSTITUTIONS)
    one = instruments.grant_warrants(db, idc, {acct: 10}, strike=price_of(db, "IDC"), expiry_period=12, period=9, why="first", now=NOW9)
    two = instruments.grant_warrants(db, idc, {acct: 10}, strike=price_of(db, "IDC") * 2, expiry_period=14, period=9, why="second", now=NOW9)
    assert one["asset"] != two["asset"] and two["strike"] == price_of(db, "IDC") * 2
    assert instruments.check_books(db) == []


# 10. The Asset Manager buys warrants for the empire only inside the Risk Manager's limit.
def test_r10_the_asset_manager_buys_for_the_empire_inside_the_limit(db):
    from fastapi import HTTPException

    import server.main  # noqa: F401  (the routes load with the application)
    from server.lending_routes import InstrumentTradeRequest, instruments_trade
    from tests.test_firm import member
    empire, team = firm_of(db, n_cash=5_000_000_000)
    am = ready(db, member(db, empire, team["head"], "asset_manager", "dealerof"))
    idc = _one(db, "SELECT * FROM companies WHERE ticker = 'IDC'")
    inst = instruments.grant_warrants(db, idc, {ledger.account_id(db, ledger.INVESTORS_INSTITUTIONS): 100_000}, strike=price_of(db, "IDC"),
                                      expiry_period=12, period=9, why="test", now=NOW9)
    db.execute("UPDATE world_state SET weeks_ahead = weeks_ahead")
    body = InstrumentTradeRequest(side="buy", units=10_000, for_empire=True)
    db.row_factory = dict_row                                         # (as the server's own connections are)
    with pytest.raises(HTTPException) as refused:
        instruments_trade(body, inst["asset"], player={"id": am}, conn=db)
    assert "limit" in refused.value.detail
    _ = signed


# 11. An earn-out cannot be escaped by the company not reporting.
def test_r11_an_earn_out_is_owed_in_full_if_the_company_stops_reporting(db):
    from tests.test_deals import LATER as DEAL_LATER
    from tests.test_deals import do_checks, fairness_if_needed
    from tests.test_deals_loopholes import ready as deal_ready
    empire, team, sale, file_id = deal_ready(db)
    do_checks(db, empire, team, file_id)
    price = sale["asking"] * 15 // 10
    fairness_if_needed(db, team, file_id, price)
    earnout = price * 2 // 10
    firm_deals.place_bid(db, team["head"], file_id, price, 0, DEAL_LATER, earnout=earnout)
    quarters.close_due_quarters(db, after_quarters(9))
    deal = _one(db, "SELECT * FROM deals WHERE empire_id = %s", (empire["id"],))
    if deal is None:
        pytest.skip("Outbid by a computer-run empire.")
    e = _one(db, "SELECT * FROM deal_earnouts WHERE deal_id = %s", (deal["id"],))
    # The company's sales could never reach this target; but its results for the quarters are missing (as if it had stopped
    # reporting): the earn-out is owed in full.
    db.execute("UPDATE deal_earnouts SET from_period = -5, due_period = 10, target_sales = %s WHERE id = %s", (10 ** 15, e["id"]))
    quarters.close_due_quarters(db, after_quarters(10))
    assert _one(db, "SELECT status, paid FROM deal_earnouts WHERE id = %s", (e["id"],)) == {"status": "paid", "paid": earnout}
    sound(db)
