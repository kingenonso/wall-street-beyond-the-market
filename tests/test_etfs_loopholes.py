"""Index funds and ETFs: ten ways a player might try to cheat, and why each fails."""

from __future__ import annotations

from datetime import timedelta

import pytest

from simulation import etfs, funds, indexes, ledger
from simulation import world_data as data
from simulation.money import naira
from tests.test_etfs import (
    DAY,
    OPEN,
    TRADING,
    _one,
    as_dealer,
    move_shares,
    person,
    ring,
    sound,
    started,
)


def test_1_units_cannot_be_conjured_outside_a_dealer_s_making(db):
    """The ledger refuses new ETF units for any reason but their making by a dealer."""
    started(db)
    topx = etfs.by_code(db, "TOPX")
    p, acc = person(db, "forger")
    with pytest.raises(Exception, match="cannot be brought into existence"):
        with db.transaction():
            ledger.post(db, kind="test_cash", memo="Test: units from nowhere",
                        legs=[ledger.Leg(topx["account_id"], -100, topx["asset"]), ledger.Leg(acc, 100, topx["asset"])])


def test_2_a_seller_cannot_sell_units_already_promised_to_another_order(db):
    started(db)
    p, acc = person(db, "bola")
    q = etfs.maker_quote(db, etfs.by_code(db, "TOPX"), TRADING)
    etfs.place_order(db, p, "TOPX", side="buy", quantity=1_000, limit_price=q["ask"], now=TRADING)
    etfs.place_order(db, p, "TOPX", side="sell", quantity=1_000, limit_price=q["ask"] * 105 // 100, now=TRADING)   # waits
    with pytest.raises(etfs.EtfError, match="hold only 0"):
        etfs.place_order(db, p, "TOPX", side="sell", quantity=1_000, limit_price=q["bid"], now=TRADING)
    sound(db)


def test_3_a_player_s_own_buy_and_sell_never_meet_each_other(db):
    """Painting the tape: one account's orders on both sides do not trade together."""
    started(db)
    p, acc = person(db, "painter")
    q = etfs.maker_quote(db, etfs.by_code(db, "TOPX"), TRADING)
    etfs.place_order(db, p, "TOPX", side="buy", quantity=2_000, limit_price=q["ask"], now=TRADING)
    mid = (q["bid"] + q["ask"]) // 2
    etfs.place_order(db, p, "TOPX", side="sell", quantity=500, limit_price=mid, now=TRADING)
    done = etfs.place_order(db, p, "TOPX", side="buy", quantity=500, limit_price=mid, now=TRADING)
    assert done["trades"] == []
    sound(db)


def test_4_the_premium_cannot_be_pushed_without_limit_the_game_s_dealers_step_in(db):
    started(db)
    p, _ = person(db, "pusher", cash_naira=5_000_000_000)
    for _ in range(25):
        q = etfs.maker_quote(db, etfs.by_code(db, "TOPX"), TRADING)
        etfs.place_order(db, p, "TOPX", side="buy", quantity=q["depth"], limit_price=q["ask"], now=TRADING)
    assert etfs.by_code(db, "TOPX")["premium_bps"] <= data.ETF_PREMIUM_MOST_BPS
    sound(db)


def test_5_a_dealer_cannot_unmake_units_it_does_not_hold_or_make_part_blocks(db, monkeypatch):
    started(db)
    p, acc = person(db, "dealer", cash_naira=500_000_000)
    as_dealer(monkeypatch, acc)
    with pytest.raises(etfs.EtfError, match="does not hold"):
        etfs.redeem(db, p, "TOPX", data.ETF_CREATION_UNITS, "cash", TRADING)
    with pytest.raises(etfs.EtfError, match="blocks"):
        etfs.create(db, p, "TOPX", data.ETF_CREATION_UNITS + 1, "cash", TRADING)


def test_6_making_and_unmaking_straight_away_costs_the_fees_and_gains_nothing(db, monkeypatch):
    started(db)
    p, acc = person(db, "churner", cash_naira=500_000_000)
    as_dealer(monkeypatch, acc)
    start = ledger.balance(db, acc)
    etfs.create(db, p, "TOPX", 5 * data.ETF_CREATION_UNITS, "cash", TRADING)
    etfs.redeem(db, p, "TOPX", 5 * data.ETF_CREATION_UNITS, "cash", TRADING)
    assert ledger.balance(db, acc) < start
    sound(db)


def test_7_the_2x_level_gate_cannot_be_passed_by_buying_for_an_empire(db, monkeypatch):
    started(db)
    p, _ = person(db, "junior", level=5)
    etfs.accept_warning(db, p, TRADING)
    from simulation import empires
    seat = {"empire_kind": "player", "empire_status": "active", "head_player_id": p, "account_id": ledger.player_account_id(db, p), "empire_id": 1}
    monkeypatch.setattr(empires, "seat_of", lambda conn, pid, **kw: seat)
    q = etfs.maker_quote(db, etfs.by_code(db, "TOPI"), TRADING)
    with pytest.raises(etfs.EtfError, match="Level 15"):
        etfs.place_order(db, p, "TOPI", side="buy", quantity=10, limit_price=q["ask"], now=TRADING, for_empire=True)


def test_8_an_index_change_is_not_known_before_it_is_announced_to_everybody(db, client, player):
    """The review is worked out as the quarter closes and announced at once to all; nothing about it exists before."""
    started(db)
    assert _one(db, "SELECT count(*) AS n FROM index_changes")["n"] == 0
    page = client.get("/api/indexes/TOP30").json()
    assert page["changes"] == []
    changes = indexes.review(db, 1, OPEN)
    assert all(c["announced_at"] == OPEN for c in changes)
    page = client.get("/api/indexes/TOP30").json()
    assert len(page["changes"]) == 1


def test_9_a_manager_s_own_index_cannot_be_changed_overnight(db):
    """A manager who owns an index and the ETF copying it cannot swap the members to suit themselves without notice."""
    started(db)
    ada, _ = person(db, "ada", build="asset_manager", level=20)
    picks = [r["ticker"] for r in _rows_tickers(db)][:6]
    indexes.create_custom(db, ada, code="ADA", name="Ada's Picks", tickers=picks, weighting="equal", now=TRADING)
    indexes.change_custom(db, ada, "ADA", picks[1:], TRADING)
    with pytest.raises(indexes.IndexError_, match="already announced"):
        indexes.change_custom(db, ada, "ADA", picks[:5], TRADING)
    ring(db, DAY)
    assert len(indexes.members(db, "ADA")) == 6                         # still the old members until the third bell
    ring(db, DAY + timedelta(days=1))
    ring(db, DAY + timedelta(days=2))
    assert len(indexes.members(db, "ADA")) == 5


def _rows_tickers(db):
    from tests.test_etfs import _rows
    return _rows(db, "SELECT ticker FROM companies WHERE listed ORDER BY ticker")


def test_10_an_index_fund_s_leavers_are_paid_from_a_slice_of_everything_not_by_starving_the_others(db):
    started(db)
    ada, _ = person(db, "ada", build="asset_manager", level=20)
    fund = funds.launch(db, ada, name="Ikoyi Index Fund", strategy="index", index_code="TOP30", fee_bps=20, perf_fee_bps=0, least_in=naira(10_000),
                        seed=naira(10_000_000), now=TRADING)
    b, b_acc = person(db, "bola", cash_naira=100_000_000)
    funds.invest(db, b, fund["id"], naira(40_000_000), TRADING)
    ring(db, DAY)
    funds.leave(db, b, fund["id"], None, TRADING + timedelta(days=1))
    move_shares(db, [], 0)
    ring(db, DAY + timedelta(days=1))
    order = _one(db, "SELECT * FROM fund_orders WHERE fund_id = %s AND side = 'out'", (fund["id"],))
    assert order["status"] == "dealt"                                   # paid in full at the bell, no loan, no gate
    assert _one(db, "SELECT count(*) AS n FROM fund_loans WHERE fund_id = %s", (fund["id"],))["n"] == 0
    left = etfs.holdings_value(db, fund["account_id"], TRADING + timedelta(days=1))
    assert len(left["lines"]) == 30                                     # still copying the whole index
    sound(db)
