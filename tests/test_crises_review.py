"""The crises stage, Part 1: each finding of the independent review, fixed, with its test."""

from __future__ import annotations

from datetime import timedelta

import pytest
from psycopg.rows import dict_row

from simulation import auctions, banking, crisis, deposits, economy, exchange, firm_money, ledger, lending, quarters
from simulation.money import naira
from tests.conftest import after_quarters
from tests.test_builds import pro
from tests.test_careers import NOW9
from tests.test_crises import P, days, unlocked, weaken
from tests.test_firm import firm_of

pytestmark = pytest.mark.world("eight")


def _rows(db, sql, params=()):
    with db.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def _one(db, sql, params=()):
    with db.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(sql, params).fetchall()
    return rows[0] if rows else None


def _rescue(db, ticker, capital_bps=-200, day=10):
    b = weaken(db, ticker, capital_bps)
    rid = crisis.cannot_pay(db, b, P, day, NOW9)
    a = _one(db, "SELECT * FROM auctions WHERE bank_id = %s AND status = 'open'", (b["id"],))
    auctions.run(db, a["ends_at"] + timedelta(minutes=1))
    return b, rid


def test_r1_ordinary_central_bank_lending_never_touches_the_emergency_loan(db):
    b = deposits.bank(db, "KCB")
    crisis._emergency_loan(db, b, naira(5_000_000_000), P, 3, NOW9)
    emergency = _one(db, "SELECT * FROM company_debts WHERE company_id = %s AND name LIKE 'emergency%%'", (b["id"],))
    world = economy.load_world(db)
    bank = next(x for x in banking.banks(db, P) if x["id"] == b["id"])
    banking.ensure_cash(db, world, bank, ledger.balance(db, b["account_id"]) * 3, P, crisis._policy_rate(db))
    after = _one(db, "SELECT * FROM company_debts WHERE id = %s", (emergency["id"],))
    assert after["principal_outstanding"] == emergency["principal_outstanding"] and after["annual_rate_bps"] == emergency["annual_rate_bps"]
    assert ledger.audit(db) == []
    # Repaying, the dearer emergency lending goes first.
    banking.repay_central_bank(db, world, {**bank, "customer_funds": 0}, P)      # (as if it needed no reserve: all its cash is spare)
    assert _one(db, "SELECT principal_outstanding FROM company_debts WHERE id = %s", (emergency["id"],))["principal_outstanding"] < \
        emergency["principal_outstanding"]


def test_r2_a_rescued_bank_is_judged_on_where_it_stands_now_and_is_not_closed_again_for_the_same_hole(db):
    b, rid = _rescue(db, "KCB")
    r = _one(db, "SELECT * FROM bank_resolutions WHERE id = %s", (rid,))
    assert r["status"] in ("sold", "public") and r["reopened_day"] is not None
    assert crisis.figures(db, b)["equity"] > 0                    # the hole filled and the new money count at once
    assert crisis.emergency_room(db, b) > 0
    days(db, 60)
    second = _one(db, "SELECT * FROM bank_resolutions WHERE company_id = %s AND id <> %s", (b["id"], rid))
    assert second is None or second["bail_in"] == 0
    assert ledger.audit(db) == [] and crisis.check_books(db) == []


def test_r3_what_filled_a_closed_banks_hole_is_not_profit_and_pays_no_tax_or_dividend(db):
    b, rid = _rescue(db, "OTB")
    r = _one(db, "SELECT * FROM bank_resolutions WHERE id = %s", (rid,))
    quarters.close_due_quarters(db, after_quarters(9))
    now_ = _one(db, "SELECT * FROM company_results WHERE company_id = %s AND period = %s", (b["id"], P))
    before = _one(db, "SELECT * FROM company_results WHERE company_id = %s AND period = %s", (b["id"], P - 1))
    filled = r["bail_in"] + r["covered"]
    assert now_["retained_earnings"] - before["retained_earnings"] == now_["net_profit"] - now_["dividends_paid"] \
        - _one(db, "SELECT coalesce(sum(-e.amount), 0)::bigint AS t FROM ledger_entries e JOIN ledger_transactions t ON t.id = e.transaction_id"
                   " WHERE e.account_id = %s AND t.kind = 'preferred_dividend' AND t.period = %s", (b["account_id"], P))["t"] + filled
    assert "not profit" in " ".join(now_["drivers"]["notes"])
    assert ledger.audit(db) == [] and crisis.check_books(db) == []


def test_r4_a_closed_banks_shares_cannot_be_shorted_pledged_or_traded(db):
    p, account = pro(db, "asset_manager", "shorter", level=40, cash_naira=100_000_000)
    b = weaken(db, "ZCB", -100)
    crisis.cannot_pay(db, b, P, 10, NOW9)
    assert b["id"] not in lending.prices(db)
    with pytest.raises(lending.LendingError):
        lending.open_short(db, account, "ZCB", 100, NOW9, player_id=p)
    with pytest.raises(exchange.ExchangeError, match="No trading"):
        exchange.place_order(db, account=account, ticker="ZCB", side="sell", kind="limit", quantity=1, limit_price=100, now=NOW9)


def test_r5_a_closure_set_off_by_a_withdrawal_stands(db):
    p, account = pro(db, "accountant", "lastone", cash_naira=40_000_000)
    deposits.put_in(db, p, "HMB", naira(30_000_000), NOW9)
    b = weaken(db, "HMB", -100)                                      # no emergency lending for a bank with no owners' funds
    # Its cash is all gone (lent out), so it cannot pay.
    ledger.transfer(db, payer=b["account_id"], receiver=ledger.account_id(db, ledger.TREASURY), amount=ledger.balance(db, b["account_id"]),
                    kind="test_cash", memo="Test: its cash lent out")
    with pytest.raises(deposits.SavingsError, match="closed"):
        deposits.take_out(db, p, "HMB", naira(30_000_000), NOW9)
    assert deposits.closed(db, b["id"])
    assert _one(db, "SELECT 1 AS x FROM auctions WHERE bank_id = %s AND status = 'open'", (b["id"],))


def test_r6_companies_drawing_their_savings_at_their_close_is_not_read_as_savers_leaving(db):
    quarters.close_due_quarters(db, after_quarters(9))
    for b in deposits.banks(db):
        assert crisis._withdrawn_recently(db, b["id"], P + 1, 1) == 0
    # The savings are spread over the trusted banks, not all at one.
    held = _one(db, "SELECT count(DISTINCT b.asset) AS n FROM ledger_balances b JOIN bank_deposits d ON d.asset = b.asset"
                    " JOIN ledger_accounts a ON a.id = b.account_id WHERE a.kind = 'company' AND b.balance > 0")["n"]
    assert held >= 3


def test_r7_an_empires_savings_go_to_its_creditor_before_its_shares(db):
    empire, team = firm_of(db, n_cash=50_000_000)
    b = deposits.bank(db, "IKB")
    deposits._place(db, empire["account_id"], b, naira(20_000_000), "savings_placed", "Test: the empire's savings", P)
    ledger.transfer(db, payer=empire["account_id"], receiver=ledger.account_id(db, ledger.TREASURY),
                    amount=ledger.balance(db, empire["account_id"]), kind="test_cash", memo="Test: its cash spent")
    lender = ledger.account_id(db, ledger.TREASURY)
    debt = {"id": -1, "kind": "loan", "traps": [], "principal": naira(10_000_000), "lender_account": lender, "lender_name": "a bank",
            "status": "defaulted", "signed_by": None}
    firm_money._default(db, empire, debt, naira(10_000_000), P, NOW9, interest=False)
    assert deposits.saved(db, empire["account_id"], b["asset"]) == naira(10_000_000)


def test_r8_a_solvent_bank_that_ran_out_of_cash_is_not_handed_over_for_its_reserve(db):
    b = weaken(db, "OBB", 2_500)                                     # plenty of owners' funds
    rid = crisis.cannot_pay(db, b, P, 12, NOW9)
    r = _one(db, "SELECT * FROM bank_resolutions WHERE id = %s", (rid,))
    asset = _one(db, "SELECT share_asset FROM companies WHERE id = %s", (b["id"],))["share_asset"]
    old = ledger.amount_in_existence(db, asset)
    a = _one(db, "SELECT * FROM auctions WHERE bank_id = %s AND status = 'open'", (b["id"],))
    auctions.run(db, a["ends_at"] + timedelta(minutes=1))
    r = _one(db, "SELECT * FROM bank_resolutions WHERE id = %s", (rid,))
    # The old owners keep a share in proportion to the funds that were already there.
    kept = old * 10_000 // ledger.amount_in_existence(db, asset)
    assert kept >= r["equity"] * 10_000 // (r["equity"] + r["price"]) - 1 > 500


def test_r9_a_bank_closed_at_the_quarters_close_is_booked_in_the_next_quarter(db):
    b = weaken(db, "KCB", 900)
    quarters.close_due_quarters(db, after_quarters(9))
    filed = crisis._filed(db, b["id"])
    unlocked(db, "UPDATE company_results SET total_equity = -1000, retained_earnings = retained_earnings - total_equity - 1000,"
                 " customer_loans = customer_loans - total_equity - 1000, total_assets = total_assets - total_equity - 1000"
                 " WHERE company_id = %s AND period = %s", (b["id"], filed["period"]))
    crisis.at_close(db, P, after_quarters(9))
    r = _one(db, "SELECT * FROM bank_resolutions WHERE company_id = %s", (b["id"],))
    assert r and r["period"] == P + 1
    assert _one(db, "SELECT count(*) AS n FROM deposit_flows WHERE kind = 'bail_in' AND period = %s", (P,))["n"] == 0


def test_r10_a_bank_auction_that_cannot_settle_leaves_the_bank_in_public_hands_not_frozen(db, monkeypatch):
    b = weaken(db, "ZCB", -100)
    rid = crisis.cannot_pay(db, b, P, 10, NOW9)
    a = _one(db, "SELECT * FROM auctions WHERE bank_id = %s AND status = 'open'", (b["id"],))
    monkeypatch.setattr(auctions, "_settle_bank", lambda *args, **kw: (_ for _ in ()).throw(RuntimeError("broken")))
    auctions.run(db, a["ends_at"] + timedelta(minutes=1))
    assert _one(db, "SELECT status FROM bank_resolutions WHERE id = %s", (rid,))["status"] == "public"
    assert not deposits.closed(db, b["id"])


def test_r11_no_savings_move_between_a_quarters_end_and_its_close(db):
    p, _ = pro(db, "accountant", "latecomer", cash_naira=5_000_000)
    with pytest.raises(deposits.SavingsError, match="books"):
        deposits.put_in(db, p, "IKB", naira(1_000_000), after_quarters(9) + timedelta(minutes=1))


def test_minor_everything_can_be_taken_out_to_the_last_kobo(db):
    p, account = pro(db, "accountant", "tidy", cash_naira=5_000_000)
    deposits.put_in(db, p, "IKB", naira(1_000_000), NOW9)
    b = deposits.bank(db, "IKB")
    deposits.take_out(db, p, "IKB", naira(999_990), NOW9)
    assert deposits.saved(db, account, b["asset"]) == naira(10)
    deposits.take_out(db, p, "IKB", 0, NOW9, everything=True)
    assert deposits.saved(db, account, b["asset"]) == 0


def test_companies_spread_their_savings_by_bank_size_and_the_same_world_always_repeats(db):
    """Found while testing Part 3: a company with no lender picked a bank by its random id, so one build in seven handed a
    large insurer's spare cash to the smallest microfinance bank, whose interest on it pushed the bank into a crisis."""
    companies = _rows(db, "SELECT * FROM companies WHERE sector <> 'banking' AND listed ORDER BY ticker")
    picks = {c["ticker"]: deposits._company_bank(db, c)["ticker"] for c in companies}
    assert picks == {c["ticker"]: deposits._company_bank(db, c)["ticker"] for c in companies}   # fixed, not a fresh draw
    sizes = {b["ticker"]: ledger.amount_in_existence(db, b["asset"]) for b in deposits.banks(db)}
    smallest, largest = min(sizes, key=sizes.get), max(sizes, key=sizes.get)
    no_lender = [c for c in companies if not _one(db, "SELECT 1 AS x FROM company_debts WHERE company_id = %s AND principal_outstanding > 0",
                                                  (c["id"],))]
    at_small = sum(1 for c in no_lender if picks[c["ticker"]] == smallest)
    at_large = sum(1 for c in no_lender if picks[c["ticker"]] == largest)
    assert at_small <= at_large                      # the biggest bank takes more of them than the smallest
