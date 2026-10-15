"""The gap stage, Part 1: the clearing house, the default fund, fair value at three depths, unlocking by level and
mastery, and the Securities Regulator's short-sale bans."""

from __future__ import annotations

from datetime import timedelta

import pytest
from psycopg.rows import dict_row

from simulation import careers, derivatives, ledger, lending, quarters
from simulation import world_data as data
from simulation.money import BPS, naira
from tests.conftest import after_quarters
from tests.test_builds import pro
from tests.test_careers import NOW9, sound
from tests.test_derivatives import learn, trader
from tests.test_lending import set_price

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


def test_two_players_trade_with_each_other_inside_the_market_makers_prices(db):
    a, a_acct = trader(db, "asset_manager", "seller", cash_naira=500_000_000)
    b, b_acct = trader(db, "asset_manager", "buyer", cash_naira=500_000_000)
    x = series(db, "call", "BSX50")
    q = derivatives.quote(db, x, NOW9)
    inside = (q["bid"] + q["ask"]) // 2
    # A writes two calls at a price between the market makers' two prices: nobody takes it yet, so it waits.
    waiting = derivatives.trade(db, a_acct, x["id"], "sell", 2, NOW9, limit=inside, player_id=a)
    assert waiting["filled"] == 0 and waiting["order_id"] and waiting["waiting"] == 2
    held = ledger.balance(db, ledger.account_id(db, derivatives.ORDERS))
    assert held == _one(db, "SELECT reserved FROM derivative_orders WHERE id = %s", (waiting["order_id"],))["reserved"] > 0
    # B buys at the market: A's waiting price is better than the market makers' ask, so B buys from A.
    bought = derivatives.trade(db, b_acct, x["id"], "buy", 2, LATER, player_id=b)
    assert bought["filled"] == 2 and bought["price"] == inside
    trade = _one(db, "SELECT * FROM derivative_trades WHERE series_id = %s ORDER BY id DESC LIMIT 1", (x["id"],))
    assert trade["buyer"] == b_acct and trade["seller"] == a_acct and not trade["with_makers"]
    assert _one(db, "SELECT status FROM derivative_orders WHERE id = %s", (waiting["order_id"],))["status"] == "filled"
    # The board shows the trade's price beside the fair value, and never who traded.
    board = derivatives.board(db, LATER, "BSX50")
    row = next(r for r in board["series"] if r["id"] == x["id"])
    assert row["last_trade"] == inside and row["fair"] > 0
    assert derivatives.check_books(db) == []
    sound(db)


def test_a_waiting_order_can_be_cancelled_and_the_bell_hands_back_what_is_left(db):
    a, a_acct = trader(db, "asset_manager", "patient", cash_naira=500_000_000)
    x = series(db, "future", "OIL")
    start = ledger.balance(db, a_acct)
    low = derivatives.quote(db, x, NOW9)["bid"] // 2
    one = derivatives.trade(db, a_acct, x["id"], "buy", 3, NOW9, limit=low, player_id=a)
    two = derivatives.trade(db, a_acct, x["id"], "buy", 1, NOW9, limit=low, player_id=a)
    assert ledger.balance(db, a_acct) < start
    derivatives.cancel_order(db, a_acct, one["order_id"], LATER)
    derivatives.at_bell(db, NOW9 + timedelta(hours=11), NOW9.date())
    assert _one(db, "SELECT status FROM derivative_orders WHERE id = %s", (two["order_id"],))["status"] == "expired"
    assert ledger.balance(db, a_acct) == start
    with pytest.raises(derivatives.DerivativesError, match="no such"):
        derivatives.cancel_order(db, a_acct, two["order_id"], LATER)
    assert derivatives.check_books(db) == []


def test_every_contract_has_two_sides_and_a_loss_beyond_the_margin_is_covered_by_the_fund_and_owed_to_it(db):
    a, a_acct = trader(db, "asset_manager", "longoil", cash_naira=50_000_000)
    x = series(db, "future", "BSX50")
    done = derivatives.trade(db, a_acct, x["id"], "buy", 5, NOW9, player_id=a)
    fund = derivatives.fund_account(db)
    fees_in = ledger.balance(db, fund)
    assert fees_in > 0                                                  # a tenth of the fee went to the default fund
    sides = _one(db, "SELECT sum(CASE side WHEN 'long' THEN contracts ELSE -contracts END) AS net FROM derivative_positions"
                     " WHERE series_id = %s AND status = 'open'", (x["id"],))["net"]
    assert sides == 0                                                   # the market makers hold the other side
    # The player spends their cash; the market halves; the night's loss is far beyond the margin.
    ledger.transfer(db, payer=a_acct, receiver=ledger.account_id(db, ledger.TREASURY), amount=ledger.balance(db, a_acct),
                    kind="test_cash", memo="Test: spent")
    ledger.transfer(db, payer=ledger.account_id(db, ledger.TREASURY), receiver=fund, amount=naira(5_000_000), kind="test_cash",
                    memo="Test: a deeper fund")
    db.execute("INSERT INTO clearing_fund_events (kind, amount, words, at) VALUES ('fee', %s, 'Test: a deeper fund', %s)", (naira(5_000_000), NOW9))
    db.execute("UPDATE market_instruments SET last_price = coalesce(last_price, reference_price) / 2, reference_price = reference_price / 2")
    derivatives.at_bell(db, NOW9 + timedelta(hours=11), NOW9.date())
    owed = _one(db, "SELECT * FROM player_loans WHERE borrower = %s AND kind = 'shortfall'", (a_acct,))
    assert owed and owed["creditor"] == fund and owed["status"] == "default"
    cover = _one(db, "SELECT sum(amount) AS c FROM clearing_fund_events WHERE kind = 'cover'")["c"]
    assert cover == owed["outstanding"]
    assert derivatives.check_books(db) == [] and lending.check_books(db) == []
    # The player repays from new cash: the fund is made whole and its record says so.
    ledger.transfer(db, payer=ledger.account_id(db, ledger.TREASURY), receiver=a_acct, amount=owed["outstanding"], kind="test_cash",
                    memo="Test: cash")
    lending.repay(db, a_acct, owed["id"], owed["outstanding"], LATER)
    assert derivatives.check_books(db) == []
    _ = done
    sound(db)


def test_fair_value_is_explained_at_three_depths_from_public_figures(db):
    for kind, underlying in (("call", "IDC"), ("future", "NAIRA")):
        x = series(db, kind, underlying)
        told = derivatives.explain(db, x["id"], NOW9)
        assert told["plain"] and told["method"] and told["maths"]
        assert derivatives.money(told["fair"]) in told["maths"]
        assert "fortune" not in str(told).lower()


def test_instruments_open_by_level_and_by_module_mastery(db):
    young, young_acct = pro(db, "asset_manager", "young", level=9, cash_naira=500_000_000)
    with pytest.raises(lending.LendingError, match="Level 10"):
        lending.open_short(db, young_acct, "GGM", 100, NOW9)
    db.execute("UPDATE careers SET experience = %s WHERE player_id = %s", (careers.experience_for(14), young))
    lending.open_short(db, young_acct, "GGM", 100, NOW9)                        # Level 14: shorts and loans are open...
    call = series(db, "call", "BSX50")
    with pytest.raises(derivatives.DerivativesError, match="Level 15"):     # ...options not yet
        derivatives.trade(db, young_acct, call["id"], "buy", 1, NOW9, player_id=young)
    db.execute("UPDATE careers SET experience = %s WHERE player_id = %s", (careers.experience_for(20), young))
    derivatives.trade(db, young_acct, call["id"], "buy", 1, NOW9, player_id=young)
    future = series(db, "future", "OIL")
    with pytest.raises(derivatives.DerivativesError, match="Level 25"):
        derivatives.trade(db, young_acct, future["id"], "buy", 1, NOW9, player_id=young)
    db.execute("UPDATE careers SET rank = 1, experience = %s WHERE player_id = %s", (careers.experience_for(30), young))
    with pytest.raises(derivatives.DerivativesError, match="Leverage and margin"):
        derivatives.trade(db, young_acct, future["id"], "buy", 1, NOW9, player_id=young)
    learn(db, young, "asset_manager")
    derivatives.trade(db, young_acct, future["id"], "buy", 1, NOW9, player_id=young)
    # Closing what one holds is always allowed.
    db.execute("UPDATE careers SET rank = 0, experience = 0 WHERE player_id = %s", (young,))
    derivatives.trade(db, young_acct, future["id"], "sell", 1, LATER, player_id=young)
    sound(db)


def test_the_securities_regulator_stops_new_short_sales_after_a_hard_fall(db):
    a, a_acct = trader(db, "asset_manager", "bear", cash_naira=500_000_000)
    day = NOW9.date()
    company = _one(db, "SELECT id FROM companies WHERE ticker = 'GGM'")["id"]
    db.execute("INSERT INTO short_bans (company_id, from_day, until_day, reason, at) VALUES (%s, %s, %s, 'Test: a 20%% fall', %s)",
               (company, day, day + timedelta(days=2), NOW9))
    with pytest.raises(lending.LendingError, match="Securities Regulator"):
        lending.open_short(db, a_acct, "GGM", 100, NOW9)
    lending.open_short(db, a_acct, "IDC", 100, NOW9)                     # other shares are free
    db.execute("INSERT INTO short_bans (company_id, from_day, until_day, reason, at) VALUES (NULL, %s, %s, 'Test: the market fell', %s)",
               (day, day, NOW9))
    with pytest.raises(lending.LendingError, match="Securities Regulator"):
        lending.open_short(db, a_acct, "IDC", 100, NOW9)
    assert lending.short_ban(db, company, day + timedelta(days=3)) is None


def test_the_regulator_sees_a_fall_at_the_bell(db):
    ended = NOW9.date()
    level = _one(db, "SELECT level FROM index_days ORDER BY session_date DESC LIMIT 1")
    before = level["level"] if level else 100_000
    db.execute("DELETE FROM index_days WHERE session_date >= %s", (ended - timedelta(days=1),))
    db.execute("INSERT INTO index_days (session_date, level) VALUES (%s, %s), (%s, %s)",
               (ended - timedelta(days=1), before, ended, before * 89 // 100))      # the BSX 50 falls 11% in a day
    assert lending._regulator(db, NOW9, ended) >= 1
    ban = lending.short_ban(db, None, ended + timedelta(days=1))
    assert ban and ban["company_id"] is None and ban["until_day"] == ended + timedelta(days=data.SHORT_BAN_DAYS)


def test_settlement_through_the_clearing_house_leaves_every_escrow_at_its_record(db):
    a, a_acct = trader(db, "asset_manager", "mixer", cash_naira=2_000_000_000)
    b, b_acct = trader(db, "risk_manager", "hedger", cash_naira=2_000_000_000)
    for kind, under, side_a in (("future", "OIL", "buy"), ("future", "NAIRA", "sell"), ("call", "BSX50", "buy"), ("put", "BSX50", "sell")):
        x = series(db, kind, under)
        q = derivatives.quote(db, x, NOW9)
        mid = max((q["bid"] + q["ask"]) // 2, 1)
        derivatives.trade(db, a_acct, x["id"], side_a, 4, NOW9, limit=mid, player_id=a)
        derivatives.trade(db, b_acct, x["id"], "sell" if side_a == "buy" else "buy", 3, LATER, player_id=b)
    set_price(db, "IDC", price_of_idc(db) * 9 // 10)
    derivatives.at_bell(db, NOW9 + timedelta(hours=11), NOW9.date())
    quarters.close_due_quarters(db, after_quarters(9))
    assert derivatives.check_books(db) == [] and lending.check_books(db) == []
    sound(db)


def price_of_idc(db):
    return _one(db, "SELECT coalesce(last_price, reference_price) AS p FROM market_instruments m JOIN companies c ON c.id = m.company_id"
                    " WHERE c.ticker = 'IDC'")["p"]


_ = (BPS, data)
