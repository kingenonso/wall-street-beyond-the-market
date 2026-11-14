"""The starting grant, paid in parts.

₦100,000 on joining; four further parts of ₦100,000, each for a real thing the player has
done, and never more than one part in twenty hours. No part can be paid twice.
"""

from __future__ import annotations

import threading
from datetime import UTC, datetime, timedelta

import psycopg
import pytest
from psycopg import errors
from psycopg.rows import dict_row

from simulation import bonds, corporate, grants, ledger, quarters
from simulation import world_data as data
from simulation.money import naira
from tests.conftest import ADULT, TEST_DATABASE_URL, after_quarters, join
from tests.test_market import place, reference, trader

OPEN = datetime.fromisoformat("2026-10-06T13:00:00+01:00")
GAP = timedelta(hours=data.GRANT_STEP_GAP_HOURS)


def _dicts(db, sql, params=()):
    with db.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def joined(db, client) -> tuple:
    assert join(client, ADULT).status_code == 201
    row = _dicts(db, "SELECT a.id AS account, a.player_id FROM ledger_accounts a WHERE a.kind = 'player'")[0]
    return row["account"], row["player_id"]


def test_the_parts_add_up_to_the_whole_grant():
    assert data.GRANT_ON_JOINING_NAIRA + len(grants.STEPS) * data.GRANT_STEP_NAIRA == data.STARTING_GRANT_NAIRA == 500_000


def test_a_new_player_receives_the_first_part_only(db, client):
    account, player = joined(db, client)
    assert ledger.balance(db, account) == naira(100_000)
    seen = grants.review(db, player, OPEN)
    assert seen["received"] == naira(100_000) and seen["total"] == naira(500_000)
    assert [s["earned"] for s in seen["steps"]] == [False] * 4 and ledger.balance(db, account) == naira(100_000)


def test_a_first_trade_earns_a_part_but_it_is_paid_only_after_the_wait(db, client):
    account, player = joined(db, client)
    seller = trader(db, "seller", shares=1_000)
    price = reference(db)
    place(db, seller, "sell", 10, price)
    place(db, account, "buy", 10, price)
    cash = ledger.balance(db, account)
    joined_at = _dicts(db, "SELECT max(t.created_at) AS at FROM ledger_transactions t WHERE t.kind = 'starting_grant'")[0]["at"]

    early = grants.review(db, player, joined_at + GAP - timedelta(minutes=1))
    assert early["steps"][0] == {"step": "first_trade", "what": grants.STEPS["first_trade"], "earned": True, "paid": False}
    assert ledger.balance(db, account) == cash and early["next_payment_at"] == joined_at + GAP

    paid = grants.review(db, player, joined_at + GAP)
    assert paid["steps"][0]["paid"] and ledger.balance(db, account) == cash + naira(100_000) and paid["received"] == naira(200_000)
    # Asking again pays nothing more.
    for _ in range(3):
        grants.review(db, player, joined_at + 10 * GAP)
    assert ledger.balance(db, account) == cash + naira(100_000)
    # It came from the Treasury: no money was made.
    from tests.test_market import sound
    sound(db)


def test_trading_with_yourself_earns_nothing(db, client):
    account, player = joined(db, client)
    ledger.transfer(db, payer=ledger.account_id(db, ledger.INVESTORS_PUBLIC), receiver=account, amount=100, asset="SHR-IDC",
                    kind="test_shares", memo="Test: shares")
    price = reference(db)
    place(db, account, "sell", 10, price)
    place(db, account, "buy", 10, price)
    assert grants.review(db, player, OPEN + 5 * GAP)["steps"][0]["earned"] is False


def test_holding_a_share_and_a_government_bill_through_a_close_each_earn_a_part_one_at_a_time(db, client):
    account, player = joined(db, client)
    seller = trader(db, "seller", shares=1_000)
    price = reference(db)
    place(db, seller, "sell", 10, price)
    place(db, account, "buy", 10, price)
    bill = next(b for b in bonds.listing(db, OPEN) if b["kind"] == "bill")
    bonds.trade(db, account=account, code=bill["code"], side="buy", units=5, now=OPEN)
    quarters.close_due_quarters(db, after_quarters(1))
    earned = {r["step"] for r in _dicts(db, "SELECT step FROM grant_steps WHERE player_id = %s", (player,))}
    assert earned == {"held_through_results", "lent_to_government"}

    # (The joining grant is stamped by the database's real clock: judge from after both it and the close.)
    now = max(after_quarters(1), datetime.now(UTC)) + 2 * GAP
    before = ledger.balance(db, account)
    first = grants.review(db, player, now)
    assert sum(s["paid"] for s in first["steps"]) == 1 and ledger.balance(db, account) == before + naira(100_000)
    assert first["next_payment_at"] == now + GAP                                   # two more are waiting, one at a time
    assert sum(s["paid"] for s in grants.review(db, player, now + GAP - timedelta(seconds=1))["steps"]) == 1
    assert sum(s["paid"] for s in grants.review(db, player, now + GAP)["steps"]) == 2
    assert sum(s["paid"] for s in grants.review(db, player, now + 2 * GAP)["steps"]) == 3
    assert ledger.balance(db, account) == before + naira(300_000)


def test_taking_part_in_a_company_decision_earns_a_part(db, client):
    account, player = joined(db, client)
    company = _dicts(db, "SELECT c.*, s.name AS sector_name FROM companies c JOIN sectors s ON s.code = c.sector WHERE ticker = 'IDC'")[0]
    with db.transaction():
        corporate.announce_offer(db, company, kind="rights", price=reference(db) * 70 // 100,
                                 shares=ledger.amount_in_existence(db, "SHR-IDC") // 3, period=0, reason="A test.", now=OPEN, rights=(1, 3))
    assert grants.review(db, player, OPEN)["steps"][3]["earned"] is False
    ledger.transfer(db, payer=ledger.account_id(db, ledger.INVESTORS_PUBLIC), receiver=account, amount=10, asset="SHR-IDC",
                    kind="test_shares", memo="Test: shares, so that there is a vote to cast")
    corporate.cast_vote(db, account=account, vote_id=_dicts(db, "SELECT id FROM company_votes")[0]["id"], choice="for", now=OPEN)
    assert grants.review(db, player, OPEN)["steps"][3]["earned"] is True


def test_two_requests_at_the_same_moment_pay_a_part_once(db, client):
    account, player = joined(db, client)
    seller = trader(db, "seller", shares=1_000)
    price = reference(db)
    place(db, seller, "sell", 10, price)
    place(db, account, "buy", 10, price)
    cash = ledger.balance(db, account)
    # The joining grant is stamped with the real time, so the next part is due a full gap after now, whatever day the test runs.
    when = datetime.now(UTC) + timedelta(hours=data.GRANT_STEP_GAP_HOURS + 1)
    problems = []

    def ask():
        try:
            with psycopg.connect(TEST_DATABASE_URL, autocommit=True, row_factory=dict_row) as conn:
                grants.review(conn, player, when)
        except Exception as problem:  # noqa: BLE001
            problems.append(problem)

    threads = [threading.Thread(target=ask) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert problems == [] and ledger.balance(db, account) == cash + naira(100_000)


def test_the_database_itself_refuses_a_second_payment_of_the_same_part(db, client):
    account, _ = joined(db, client)
    treasury = ledger.account_id(db, ledger.TREASURY)
    ledger.transfer(db, payer=treasury, receiver=account, amount=1, kind="grant_step", memo="x", reference=f"{account}:first_trade")
    with pytest.raises(errors.UniqueViolation):
        ledger.transfer(db, payer=treasury, receiver=account, amount=1, kind="grant_step", memo="x", reference=f"{account}:first_trade")
    with pytest.raises(errors.CheckViolation):
        db.execute("INSERT INTO grant_steps (player_id, step, earned_at) SELECT id, 'made_up', now() FROM players")


def test_the_grant_through_the_server(db, client):
    assert client.post("/api/me/grant", content="{}").status_code == 401
    assert join(client, ADULT).status_code == 201
    seen = client.post("/api/me/grant", content="{}").json()
    assert seen["received_kobo"] == "10000000" and seen["total_kobo"] == "50000000" and len(seen["steps"]) == 4
    assert client.get("/api/me").json()["cash"]["amount_kobo"] == "10000000"
