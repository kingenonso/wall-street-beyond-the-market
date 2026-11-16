"""The Archegos moment (owner, 16 November 2026: "ok build"): computer hedge funds ask the players' bank desks to hold
shares for them on a swap; most close quietly and pay interest; now and then one blows up, the banks keep its margin and
its shares, the share falls twice, ten minutes apart, and the banks race to sell. The last out is counted.

Promises: an open desk is offered a swap; taking it on buys the shares and receives the margin; a quiet close buys them
back at the market price, takes the margin back and pays the interest; a blow-up keeps the margin with the banks, falls
12% then 20% then bounces, and records who got out before which fall. Loopholes: another bank's swap; a swap after its
time; a bank seeing how much the fund asked of anybody else; money made or lost by the books.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from psycopg.rows import dict_row

from simulation import floor, ledger, prime
from tests.test_builds import pro
from tests.test_careers import NOW9, sound
from tests.test_market import place

pytestmark = pytest.mark.world("eight")


def _q(db, sql, params=()):
    with db.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def _start(db, monkeypatch, blows: bool):
    banker, bank = pro(db, "investment_banker", "banker", level=5, cash_naira=50_000_000)
    other, other_bank = pro(db, "investment_banker", "other", level=5, cash_naira=50_000_000)
    for b in (banker, other):
        floor.set_desk(db, b, True, NOW9)
    monkeypatch.setattr(prime.data, "FLOOR_FUND_CHANCE", 1)
    prime.tick(db, NOW9)
    monkeypatch.setattr(prime.data, "FLOOR_FUND_CHANCE", 10**9)
    fund = _q(db, "SELECT * FROM floor_funds ORDER BY id DESC LIMIT 1")[0]
    db.execute("UPDATE floor_funds SET blows_up = %s WHERE id = %s", (blows, fund["id"]))
    return fund, (banker, bank), (other, other_bank)


def test_a_swap_is_taken_on_and_closes_quietly_with_interest(db, monkeypatch):
    fund, (banker, bank), (other, _) = _start(db, monkeypatch, False)
    mine = prime.view(db, banker, NOW9)[0]
    assert mine["status"] == "offered" and "blows" not in repr(mine) and mine["fund"] == fund["name"]
    with pytest.raises(prime.PrimeError, match="no such swap"):
        prime.answer(db, other, mine["id"], True, NOW9)
    cash = ledger.balance(db, bank)
    done = prime.answer(db, banker, mine["id"], True, NOW9 + timedelta(minutes=1))
    asset = _q(db, "SELECT share_asset FROM companies WHERE id = %s", (fund["company_id"],))[0]["share_asset"]
    assert ledger.balance(db, bank, asset) == mine["shares"]
    assert ledger.balance(db, bank) == cash - done["price"] * mine["shares"] + done["margin"]
    theirs = prime.view(db, other, NOW9 + timedelta(minutes=1))[0]
    with pytest.raises(prime.PrimeError, match="no longer on offer"):
        prime.answer(db, other, theirs["id"], True, NOW9 + timedelta(minutes=11))
    prime.tick(db, fund["ends_at"] + timedelta(seconds=1))
    closed = prime.view(db, banker, fund["ends_at"] + timedelta(seconds=2))[0]
    assert closed["status"] == "closed" and int(closed["interest"]) == done["price"] * mine["shares"] * 300 // 10_000
    assert ledger.balance(db, bank, asset) == 0
    sound(db)


def test_a_blow_up_leaves_the_banks_racing_to_sell(db, monkeypatch):
    fund, (banker, bank), (other, _other_bank) = _start(db, monkeypatch, True)
    swaps = {s["player_id"]: s for s in _q(db, "SELECT * FROM floor_swaps WHERE fund_id = %s", (fund["id"],))}
    for who in (banker, other):
        prime.answer(db, who, swaps[who]["id"], True, NOW9 + timedelta(minutes=1))
    ticker = _q(db, "SELECT ticker, share_asset FROM companies WHERE id = %s", (fund["company_id"],))[0]
    before = prime._price(db, ticker["ticker"], fund["ends_at"])
    prime.tick(db, fund["ends_at"] + timedelta(seconds=1))
    first = prime._price(db, ticker["ticker"], fund["ends_at"] + timedelta(seconds=2))
    assert first == before * (10_000 - 1200) // 10_000
    seen = prime.view(db, banker, fund["ends_at"] + timedelta(seconds=2))[0]
    assert seen["status"] == "defaulted" and seen["held_now"] == swaps[banker]["shares"] and seen["stage"] == 1
    # The banker sells everything at once on the exchange; the other holds on.
    _buyer, buyer_account = pro(db, "asset_manager", "bargain", level=5, cash_naira=900_000_000)
    when = fund["ends_at"] + timedelta(minutes=2)
    place(db, buyer_account, "buy", swaps[banker]["shares"], first, now=when, ticker=ticker["ticker"])
    place(db, bank, "sell", swaps[banker]["shares"], first, now=when + timedelta(seconds=1), ticker=ticker["ticker"])
    prime.tick(db, fund["ends_at"] + timedelta(minutes=11))
    rows = {r["player_id"]: r for r in _q(db, "SELECT * FROM floor_swaps WHERE fund_id = %s", (fund["id"],))}
    assert rows[banker]["out_before"] == 2 and rows[other]["out_before"] is None          # the other is the last out
    assert any("last out" in n["words"] for n in floor.notes(db, fund["ends_at"] + timedelta(minutes=11)))
    prime.tick(db, fund["ends_at"] + timedelta(minutes=31))
    assert _q(db, "SELECT stage FROM floor_funds WHERE id = %s", (fund["id"],))[0]["stage"] == 3
    # The banks kept the margin; nothing was made or lost by the books.
    assert int(prime.view(db, other, fund["ends_at"] + timedelta(minutes=31))[0]["margin"]) > 0
    sound(db)
