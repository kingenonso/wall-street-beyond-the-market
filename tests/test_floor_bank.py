"""Floor extras, slice 2 (owner, 17 November 2026: "go on"): the bank desk.

Promises: a client asks the Floor for money and every bank it chose prices the loan as a yearly rate (a computer bank from
the Central Bank's rate and the client's grade); the client takes one, the lender pays the money over at once, and on the
due day it comes back with the interest. A loan owed counts in the borrower's debts and a loan lent in the lender's worth.
A player who cannot repay owes the rest as a debt in default and may not borrow again on the Floor; a computer client fails
by chance, pays back 40%, and the loss counts towards the desk's day's loss. Limits: amounts, terms, rates, the desk's
one-deal limit, its own cash, and at most what the borrower is worth.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from psycopg.rows import dict_row

from simulation import floor, floor_bank, floor_extras, ledger, lending
from simulation import world_data as data
from tests.test_builds import pro
from tests.test_careers import sound
from tests.test_floor_extras import _open_time

pytestmark = pytest.mark.world("eight")


def _q(db, sql, params=()):
    with db.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def _banker(db, name, now, cash=900_000_000):
    banker, account = pro(db, "investment_banker", name, level=5, cash_naira=cash)
    floor.set_desk(db, banker, True, now)
    return banker, account


def test_a_client_borrows_on_the_floor_and_repays_with_interest_on_the_due_day(db):
    now = _open_time()
    banker, bank_account = _banker(db, "money banker", now)
    client, client_account = pro(db, "asset_manager", "borrower", level=5, cash_naira=80_000_000)
    amount = 30_000_000 * 100
    asked = floor_bank.ask(db, client, amount, 7, 30, [f"player:{banker}", "computer:goldbridge", "computer:atlas"], now)
    assert asked["grade"] == "A"
    ask_id = asked["ask_id"]
    view = floor_bank.view(db, client, now)
    computer = {q["bank"]: q["rate_bps"] for q in view["asks"][0]["quotes"]}
    base = lending.policy_rate(db) + 2 * floor_bank.expected_loss_bps("A") + data.FLOOR_LOAN_BANK_MARGIN_BPS
    assert len(computer) == 2 and all(abs(r - base) <= 100 for r in computer.values())
    # The banker sees the file and undercuts.
    incoming = floor_bank.view(db, banker, now)["incoming"][0]
    assert incoming["client"] == "borrower" and incoming["grade"] == "A" and incoming["file"]["worth"] > 0
    rate = min(computer.values()) - 50
    q = floor_bank.quote(db, banker, ask_id, rate, now + timedelta(seconds=2))
    cash_before = ledger.balance(db, client_account)
    bank_worth_before = floor_bank.lent(db, bank_account) + ledger.balance(db, bank_account)
    taken = floor_bank.take(db, client, ask_id, q["quote_id"], now + timedelta(seconds=5))
    assert ledger.balance(db, client_account) == cash_before + amount
    assert floor_bank.owed(db, client_account) == amount and lending.loans_owed(db, client_account) >= amount
    assert floor_bank.lent(db, bank_account) + ledger.balance(db, bank_account) == bank_worth_before    # lent is still the banker's
    with pytest.raises(floor.FloorError, match="closed"):
        floor_bank.take(db, client, ask_id, q["quote_id"], now + timedelta(seconds=6))
    # On the due day it comes back with the interest.
    due = taken["due_at"]
    assert due - (now + timedelta(seconds=5)) == timedelta(seconds=7 * floor_bank.GAME_DAY_SECONDS)
    bank_cash = ledger.balance(db, bank_account)
    floor_bank.tick(db, due + timedelta(seconds=1))
    loan = _q(db, "SELECT * FROM floor_loans WHERE id = %s", (taken["loan_id"],))[0]
    expected = lending.accrued(amount, rate, loan["starts_at"], loan["due_at"])
    assert loan["status"] == "repaid" and loan["interest"] == expected > 0 and loan["paid"] == amount + expected
    assert ledger.balance(db, bank_account) == bank_cash + amount + expected
    assert floor_bank.owed(db, client_account) == 0
    assert floor_bank.record(db, banker)["earned"] == expected
    sound(db)


def test_a_player_who_cannot_repay_owes_the_rest_in_default_and_may_not_borrow_again(db):
    now = _open_time()
    banker, bank_account = _banker(db, "patient banker", now)
    client, client_account = pro(db, "asset_manager", "spender", level=5, cash_naira=40_000_000)
    ask_id = floor_bank.ask(db, client, 20_000_000 * 100, 1, 30, [f"player:{banker}"], now)["ask_id"]
    q = floor_bank.quote(db, banker, ask_id, 2_000, now + timedelta(seconds=1))
    taken = floor_bank.take(db, client, ask_id, q["quote_id"], now + timedelta(seconds=2))
    # The money is spent elsewhere: only a little is left.
    spend = ledger.balance(db, client_account) - 5_000_000 * 100
    ledger.transfer(db, payer=client_account, receiver=ledger.account_id(db, ledger.INVESTORS_PUBLIC), amount=spend,
                    kind="test_spend", memo="Test: money spent")
    floor_bank.tick(db, taken["due_at"] + timedelta(seconds=1))
    loan = _q(db, "SELECT * FROM floor_loans WHERE id = %s", (taken["loan_id"],))[0]
    assert loan["status"] == "shortfall" and loan["paid"] == 5_000_000 * 100
    debt = _q(db, "SELECT * FROM player_loans WHERE borrower = %s AND kind = 'shortfall'", (client_account,))[0]
    assert debt["status"] == "default" and debt["creditor"] == bank_account
    assert debt["outstanding"] == loan["principal"] + loan["interest"] - loan["paid"]
    with pytest.raises(floor.FloorError, match="in default"):
        floor_bank.ask(db, client, 2_000_000 * 100, 1, 30, ["computer:goldbridge"], taken["due_at"] + timedelta(seconds=5))
    assert floor_bank.credit_file(db, client_account, now)["grade"] == "D"
    sound(db)


def test_a_computer_client_borrows_from_the_cheapest_desk_and_may_fail(db, monkeypatch):
    now = _open_time()
    banker, bank_account = _banker(db, "brave banker", now)
    monkeypatch.setattr(data, "FLOOR_LOAN_CALL_CHANCE", 1)
    floor_bank.tick(db, now)
    incoming = floor_bank.view(db, banker, now)["incoming"]
    assert len(incoming) == 1 and incoming[0]["computer"] and incoming[0]["purpose"]
    ask = incoming[0]
    floor_bank.quote(db, banker, ask["id"], 100, now + timedelta(seconds=1))      # far cheaper than the computer banks
    ends = ask["quotes_until"]
    bank_cash = ledger.balance(db, bank_account)
    monkeypatch.setattr(data, "FLOOR_LOAN_CALL_CHANCE", 10**9)
    floor_bank.tick(db, ends + timedelta(seconds=1))
    loan = _q(db, "SELECT * FROM floor_loans WHERE ask_id = %s", (ask["id"],))[0]
    assert loan["lender_player"] == banker and ledger.balance(db, bank_account) == bank_cash - ask["amount"]
    # It fails for certain: it pays back 40%, and the banker bears the loss, which counts towards the day's loss.
    monkeypatch.setattr(data, "FLOOR_LOAN_GRADES", dict.fromkeys(data.FLOOR_LOAN_GRADES, 360 * 10_000))
    at = loan["due_at"] + timedelta(seconds=1)
    floor_bank.tick(db, at)
    loan = _q(db, "SELECT * FROM floor_loans WHERE id = %s", (loan["id"],))[0]
    assert loan["status"] == "defaulted" and loan["paid"] == loan["principal"] * data.FLOOR_LOAN_RECOVERY_BPS // 10_000
    assert loan["lost"] == loan["principal"] + loan["interest"] - loan["paid"]
    assert any(n["kind"] == "loan" and "failed to repay" in n["words"] for n in floor.notes(db, at))
    if floor_extras._day_start(at) <= loan["starts_at"]:
        assert floor_extras.day_pnl(db, banker, at) <= loan["paid"] - loan["principal"]
    assert floor_bank.record(db, banker)["failed"] == 1
    sound(db)


def test_the_bank_desk_checks_amounts_terms_rates_limits_cash_and_worth(db, monkeypatch):
    now = _open_time()
    banker, _ = _banker(db, "careful banker", now, cash=50_000_000)
    client, _c = pro(db, "asset_manager", "small client", level=5, cash_naira=10_000_000)
    desk = [f"player:{banker}"]
    with pytest.raises(floor.FloorError, match="Ask to borrow"):
        floor_bank.ask(db, client, 100, 7, 30, desk, now)
    with pytest.raises(floor.FloorError, match="Borrow for"):
        floor_bank.ask(db, client, 5_000_000 * 100, 5, 30, desk, now)
    with pytest.raises(floor.FloorError, match="at most what you are worth"):
        floor_bank.ask(db, client, 500_000_000 * 100, 7, 30, desk, now)
    ask_id = floor_bank.ask(db, client, 8_000_000 * 100, 3, 30, desk, now)["ask_id"]
    with pytest.raises(floor.FloorError, match="at most 90%"):
        floor_bank.quote(db, banker, ask_id, 9_500, now)
    outsider, _o = _banker(db, "other banker", now)
    with pytest.raises(floor.FloorError, match="not sent to your desk"):
        floor_bank.quote(db, outsider, ask_id, 1_000, now)
    monkeypatch.setattr(data, "FLOOR_LIMITS", {**data.FLOOR_LIMITS, "deal_most": 1_000_000})
    with pytest.raises(floor.FloorError, match="limit of"):
        floor_bank.quote(db, banker, ask_id, 1_000, now)
    monkeypatch.undo()
    rich_ask = floor_bank.ask(db, client, 8_000_000 * 100, 3, 30, [f"player:{banker}"], now + timedelta(seconds=1))["ask_id"]
    floor_bank.quote(db, banker, rich_ask, 1_000, now + timedelta(seconds=2))
    banker_account = ledger.player_account_id(db, banker)
    ledger.transfer(db, payer=banker_account, receiver=ledger.account_id(db, ledger.INVESTORS_PUBLIC),
                    amount=ledger.balance(db, banker_account) - 100, kind="test_spend", memo="Test: banker's cash spent")
    with pytest.raises(floor.FloorError, match="own cash"):
        floor_bank.quote(db, banker, ask_id, 1_000, now + timedelta(seconds=3))
    quote_id = floor_bank.view(db, client, now + timedelta(seconds=3))["asks"][0]["quotes"][0]["id"]
    with pytest.raises(floor.FloorError, match="no longer has the cash"):
        floor_bank.take(db, client, rich_ask, quote_id, now + timedelta(seconds=4))
    # A request nobody took expires after the taking time.
    floor_bank.tick(db, now + timedelta(seconds=30 + data.FLOOR_LOAN_TAKE_SECONDS + 5))
    assert _q(db, "SELECT status FROM floor_loan_asks WHERE id = %s", (ask_id,))[0]["status"] == "expired"


def test_a_player_repays_early_paying_at_least_a_days_interest(db):
    now = _open_time()
    banker, _bank_account = _banker(db, "early banker", now)
    client, _client_account = pro(db, "asset_manager", "early payer", level=5, cash_naira=60_000_000)
    amount = 10_000_000 * 100
    ask_id = floor_bank.ask(db, client, amount, 14, 30, [f"player:{banker}"], now)["ask_id"]
    q = floor_bank.quote(db, banker, ask_id, 3_600, now)
    taken = floor_bank.take(db, client, ask_id, q["quote_id"], now + timedelta(seconds=1))
    done = floor_bank.repay(db, client, taken["loan_id"], now + timedelta(seconds=60))
    day = lending.accrued(amount, 3_600, now + timedelta(seconds=1), now + timedelta(seconds=1 + floor_bank.GAME_DAY_SECONDS))
    assert done["status"] == "repaid" and done["interest"] == day > 0 and done["paid"] == amount + day
    with pytest.raises(floor.FloorError, match="already closed"):
        floor_bank.repay(db, client, taken["loan_id"], now + timedelta(seconds=61))
    stranger, _s = pro(db, "asset_manager", "stranger", level=5)
    with pytest.raises(floor.FloorError, match="not one of your loans"):
        floor_bank.repay(db, stranger, taken["loan_id"], now + timedelta(seconds=62))
    sound(db)


def test_the_bank_routes_need_a_login_and_good_input(client, player):
    page = client.get("/api/floor/bank")
    assert page.status_code == 200 and page.json()["ready"]
    assert client.post("/api/floor/bank/ask", json={"amount": -1, "days": 7, "seconds": 30, "desks": ["computer:atlas"]}).status_code == 422
    assert client.post("/api/floor/bank/quote", json={"ask_id": 1, "rate_bps": 0}).status_code == 422
    assert client.post("/api/floor/bank/take", json={"ask_id": "x", "quote_id": 1}).status_code == 422
    assert client.post("/api/floor/bank/repay", json={"loan_id": 999999}).status_code == 409
    client.cookies.clear()
    assert client.get("/api/floor/bank").status_code == 401
