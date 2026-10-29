"""Run Your Own Fund: ten ways a player might try to cheat a fund, its investors or the game, and why each fails."""

from __future__ import annotations

from datetime import timedelta

import pytest

from simulation import empires, exchange, funds, ledger
from simulation import world_data as data
from simulation.money import naira
from tests.test_market import trader
from tests.test_funds import DAY, OPEN, _one, investor, launch, manager, ring, sound


def test_1_money_put_in_after_the_bell_cannot_buy_at_that_bells_price(db):
    """Late trading: the bell has rung and its price can be worked out, but the funds have not dealt yet."""
    ada, _ = manager(db)
    fund = launch(db, ada)
    bola, _ = investor(db, "bola")
    rung = ring(db, DAY) - timedelta(minutes=1)
    late = funds.invest(db, bola, fund["id"], naira(1_000_000), rung + timedelta(seconds=30))
    funds.tick(db, rung + timedelta(minutes=5))
    assert _one(db, "SELECT status FROM fund_orders WHERE id = %s", (late["id"],))["status"] == "waiting"


def test_2_coming_in_and_straight_out_again_costs_money_rather_than_making_it(db):
    """Round trips: the swing on the way in and on the way out stays in the fund."""
    ada, _ = manager(db)
    fund = launch(db, ada)
    bola, account = investor(db, "bola")
    funds.invest(db, bola, fund["id"], naira(5_000_000), OPEN)
    ring(db, DAY)
    funds.leave(db, bola, fund["id"], None, OPEN + timedelta(days=1))
    ring(db, DAY + timedelta(days=1))
    # About half a percent is lost (less the share of it a big holder gets back as part of the fund), never gained.
    assert ledger.balance(db, account) < naira(10_000_000) - naira(15_000)
    sound(db)


def test_3_units_cannot_be_asked_back_twice(db):
    ada, _ = manager(db)
    fund = launch(db, ada)
    bola, _ = investor(db, "bola")
    funds.invest(db, bola, fund["id"], naira(1_000_000), OPEN)
    ring(db, DAY)
    held = _one(db, "SELECT units FROM fund_units WHERE fund_id = %s", (fund["id"],))
    funds.leave(db, bola, fund["id"], None, OPEN + timedelta(days=1))
    with pytest.raises(funds.FundError):
        funds.leave(db, bola, fund["id"], 1, OPEN + timedelta(days=1))
    assert held


def test_4_a_manager_cannot_have_the_fund_buy_from_their_own_sell_order(db):
    ada, ada_account = manager(db)
    launch(db, ada)
    price = _one(db, "SELECT reference_price FROM market_instruments m JOIN companies c ON c.id = m.company_id WHERE c.ticker = 'IDC'")["reference_price"]
    ledger.transfer(db, payer=ledger.account_id(db, ledger.INVESTORS_PUBLIC), receiver=ada_account, amount=1_000, asset="SHR-IDC", kind="test_shares",
                    memo="Test: shares")
    exchange.place_order(db, account=ada_account, ticker="IDC", side="sell", kind="limit", quantity=500, limit_price=price, now=OPEN)
    with pytest.raises(funds.FundError):
        funds.trade_shares(db, ada, ticker="IDC", side="buy", quantity=100, limit_price=price, now=OPEN)


def test_5_a_manager_who_buys_a_share_for_themselves_just_before_the_fund_is_noted_privately(db):
    ada, ada_account = manager(db)
    launch(db, ada)
    price = _one(db, "SELECT reference_price FROM market_instruments m JOIN companies c ON c.id = m.company_id WHERE c.ticker = 'IDC'")["reference_price"]
    seller = trader(db, "seller", shares=1_000)
    exchange.place_order(db, account=seller, ticker="IDC", side="sell", kind="limit", quantity=100, limit_price=price, now=OPEN)
    exchange.place_order(db, account=ada_account, ticker="IDC", side="buy", kind="limit", quantity=100, limit_price=price, now=OPEN)
    funds.trade_shares(db, ada, ticker="IDC", side="buy", quantity=100, limit_price=price, now=OPEN + timedelta(minutes=5))
    assert _one(db, "SELECT count(*) AS n FROM money_watch_flags WHERE account_id = %s AND reason LIKE 'Fund manager%%'", (ada_account,))["n"] == 1
    page = funds.factsheet(db, _one(db, "SELECT id FROM investment_funds")["id"], ada, OPEN)
    assert "Money Watch" not in str(page) and "flag" not in str(page).lower()


def test_6_only_the_head_moves_an_empires_money_into_a_fund_and_never_more_than_they_may_sign_for(db, monkeypatch):
    ada, _ = manager(db)
    fund = launch(db, ada)
    bola, _ = investor(db, "bola")
    with pytest.raises(funds.FundError, match="not in an empire"):
        funds.invest(db, bola, fund["id"], naira(1_000_000), OPEN, for_empire=True)
    seat = {"empire_status": "active", "empire_kind": "player", "head_player_id": "someone-else", "account_id": None}
    monkeypatch.setattr(empires, "seat_of", lambda conn, pid: seat)
    with pytest.raises(funds.FundError, match="Only the head"):
        funds.invest(db, bola, fund["id"], naira(1_000_000), OPEN, for_empire=True)


def test_7_fees_cannot_be_raised_after_investors_have_come_in(db):
    ada, _ = manager(db)
    launch(db, ada, fee_bps=50, perf_fee_bps=0)
    for fee, perf in ((51, 0), (50, 1), (-1, 0)):
        with pytest.raises(funds.FundError):
            funds.lower_fees(db, ada, fee, perf, OPEN)


def test_8_a_fund_cannot_be_named_to_pass_for_the_computers_own_or_an_institution(db):
    ada, _ = manager(db)
    for name in ("Broad Street Equity Fund", "Central Bank Savings", "Federal Government Fund", "Treasury Plus",
                 "The Regulator's Fund"):
        with pytest.raises(funds.FundError):
            launch(db, ada, name=name)
    ring(db, DAY)                                                   # the computer's funds now exist under those names
    with pytest.raises(funds.FundError):
        launch(db, ada, name="Lagoon Banks Fund")


def test_9_what_a_fund_holds_now_is_never_published_only_two_quarter_ends_back(db):
    ada, _ = manager(db)
    fund = launch(db, ada)
    db.execute("INSERT INTO fund_disclosures (fund_id, period, holdings) VALUES (%s, 1, '{\"lines\": [], \"cash_bps\": 10000}')", (fund["id"],))
    assert funds.factsheet(db, fund["id"], ada, OPEN)["holdings"] is None             # period 1 is running
    later = OPEN + timedelta(weeks=1)
    db.execute("UPDATE world_state SET last_closed_period = 1")
    assert funds.factsheet(db, fund["id"], ada, later)["holdings"] is None            # quarter 2 running: quarter 1's waits
    db.execute("UPDATE world_state SET last_closed_period = 2")
    assert funds.factsheet(db, fund["id"], ada, later + timedelta(weeks=1))["holdings"] is not None


def test_10_a_false_cost_is_capped_each_quarter_and_never_shown_on_the_fund_s_pages(db):
    ada, _ = manager(db)
    fund = launch(db, ada)
    limit = naira(10_000_000) * data.INVEST_FUND_COSTS_BPS // 10_000
    funds.take_costs(db, ada, limit, OPEN)
    with pytest.raises(funds.FundError):
        funds.take_costs(db, ada, 1, OPEN)
    sheet = funds.factsheet(db, fund["id"], ada, OPEN)
    assert "Custody" not in str(sheet) and "books" not in sheet
    listing = funds.listing(db, ada, OPEN)
    assert "Custody" not in str(listing)
    sound(db)
