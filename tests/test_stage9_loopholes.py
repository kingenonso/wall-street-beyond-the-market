"""Stage 9: the ten-question loophole check, each question with its test.

 1. Can borrowing against shares be looped (borrow, buy more shares, borrow again) without end?   No: half of what is held, and
                                                                                                at most twice the borrower's worth.
 2. Can a short seller escape the lending fee or the dividend owed by holding no cash?            No: they come out of the collateral.
 3. Can opening and closing at once (a short, an option, a future) make money?                     No: nothing, or the desk's spread lost.
 4. Can a player write options or take futures without the cash for the margin?                    No.
 5. Can "What could happen?" be run for free again and again?                                      No: one free run a day, then a fee.
 6. Can anyone see who is short, or anybody else's loans, shorts or contracts?                     No: only totals, never names.
 7. Can an empire's Asset Manager slip past the Risk Manager's limit by splitting a trade?          No: what is already committed counts.
 8. Can an empire join the crash fund once a fall is under way and be paid for it?                 No: only cover paid for before the quarter.
 9. Can a member who is not the Asset Manager, Risk Manager or head act for the empire?           No.
10. Can money be made or lost by the books: escrow left behind, a kobo out of place?               No: every escrow ends at what its records say.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from psycopg.rows import dict_row

from simulation import crashfund, derivatives, ledger, lending, lending_empire, montecarlo, quarters
from simulation import world_data as data
from simulation.money import BPS, naira
from tests.conftest import ADULT, after_quarters, join
from tests.test_builds import pro  # noqa: F401
from tests.test_derivatives import ready, trader
from tests.test_careers import NOW9, sound
from tests.test_firm import firm_of, member
from tests.test_derivatives import seed_fund
from tests.test_lending import bank_id, price_of, signed
from tests.test_objectives import give_cash, give_shares

pytestmark = pytest.mark.world("eight")
LATER = NOW9 + timedelta(hours=1)


def _one(db, sql, params=()):
    with db.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(sql, params).fetchall()
    return rows[0] if rows else None


def series(db, kind, underlying, expiry=9):
    derivatives.ensure(db, NOW9)
    return _one(db, "SELECT * FROM derivative_series WHERE kind = %s AND underlying = %s AND expiry_period = %s ORDER BY strike LIMIT 1",
                (kind, underlying, expiry))


def test_1_borrowing_against_shares_cannot_be_looped_without_end(db):
    player, account = trader(db, "asset_manager", "looper", level=10, cash_naira=0)
    held = give_shares(db, account, "IDC", 10_000_000)
    price = price_of(db, "IDC")
    asset = "SHR-IDC"
    for _ in range(12):
        room = lending.margin_limit(db, account, LATER)
        if room < 1000:
            break
        lending.take_margin(db, account, bank_id(db), room, LATER)
        # Spend the loan on more of the same shares (a test transfer at the price).
        cash = ledger.balance(db, account)
        more = cash // price
        ledger.post(db, kind="test_cash", memo="Test: bought more", legs=[
            ledger.Leg(account, -more * price), ledger.Leg(ledger.account_id(db, ledger.INVESTORS_PUBLIC), more * price),
            ledger.Leg(ledger.account_id(db, ledger.INVESTORS_PUBLIC), -more, asset), ledger.Leg(account, more, asset)])
    owed = lending.margin_owed(db, account)
    equity = lending._equity(db, account, LATER)
    assert owed <= data.MOST_DEBT_TIMES_EQUITY * equity
    assert owed <= held * price * 11 // 10                        # the loop converges: at most about the first holding's worth
    sound(db)


def test_2_the_fee_and_the_dividend_come_out_of_the_collateral_when_there_is_no_cash(db):
    player, account = trader(db, "asset_manager", "penniless", level=10, cash_naira=0)
    give_cash(db, account, 10_000_000)
    s = lending.open_short(db, account, "GGM", 10_000, NOW9)
    ledger.transfer(db, payer=account, receiver=ledger.account_id(db, ledger.TREASURY), amount=ledger.balance(db, account),
                    kind="test_cash", memo="Test: spent")
    quarters.close_due_quarters(db, after_quarters(9))
    row = _one(db, "SELECT * FROM short_positions WHERE id = %s", (s["short_id"],))
    assert row["fees_paid"] > 0 and row["collateral"] < s["collateral"]
    sound(db)


def test_3_opening_and_closing_at_once_makes_nothing_or_loses_the_spread(db):
    player, account = trader(db, "asset_manager", "flipper", level=10, cash_naira=500_000_000)
    start = ledger.balance(db, account)
    s = lending.open_short(db, account, "GGM", 1_000, NOW9)
    lending.close_short(db, account, s["short_id"], NOW9)
    assert ledger.balance(db, account) == start
    for kind, underlying in (("call", "BSX50"), ("future", "OIL")):
        x = series(db, kind, underlying)
        p = derivatives.open_position(db, account, x["id"], "long", 2, NOW9, player_id=player)
        derivatives.close_position(db, account, p["position_id"], NOW9)
        assert ledger.balance(db, account) <= start
    sound(db)


def test_4_no_writing_or_futures_without_the_cash_for_the_margin(db):
    player, account = trader(db, "asset_manager", "empty", level=10, cash_naira=1)
    for kind, underlying, side in (("call", "BSX50", "short"), ("future", "BSX50", "long"), ("future", "NAIRA", "short")):
        x = series(db, kind, underlying)
        with pytest.raises(derivatives.DerivativesError, match="needs|not the cash"):
            derivatives.open_position(db, account, x["id"], side, 1, NOW9, player_id=player)
    with pytest.raises(lending.LendingError, match="150%|at most 2 times"):
        lending.open_short(db, account, "GGM", 1_000, NOW9)


def test_5_one_free_run_a_day_and_two_at_once_cannot_both_be_free(db):
    player, account = trader(db, "risk_manager", "curious", cash_naira=1_000_000)
    give_shares(db, account, "IDC", 1_000)
    runs = [montecarlo.run(db, player, "portfolio", LATER + timedelta(seconds=n)) for n in range(3)]
    assert [r["fee"] for r in runs] == [0, naira(data.MONTE_CARLO_FEE_NAIRA), naira(data.MONTE_CARLO_FEE_NAIRA)]
    assert montecarlo.run(db, player, "portfolio", LATER + timedelta(days=1))["fee"] == 0          # a new day, a new free run


def test_6_nobody_sees_who_is_short_or_anybody_elses_book(db, client):
    bear, bear_account = trader(db, "asset_manager", "secretbear", level=10, cash_naira=500_000_000)
    lending.open_short(db, bear_account, "GGM", 10_000, NOW9)
    lending.take_personal(db, bear, naira(10_000), NOW9)
    assert join(client, ADULT).status_code == 201
    for path in ("/api/borrowing", "/api/share-risk", "/api/derivatives?underlying=GGM", "/api/market"):
        text = client.get(path).text.lower()
        assert "secretbear" not in text and str(bear_account) not in text, path
    mine = client.get("/api/borrowing").json()
    assert mine["shorts"] == [] and mine["loans"] == []
    risky = client.get("/api/share-risk")
    assert risky.status_code == 200, risky.text
    assert any(r["short_interest_bps"] > 0 for r in risky.json()["shares"])


def test_7_splitting_a_trade_does_not_slip_past_the_risk_managers_limit(db):
    empire, team = firm_of(db, n_cash=5_000_000_000)
    for who in ("head", "risk_manager"):
        ready(db, team[who])
    am = member(db, empire, team["head"], "asset_manager", "splitter")
    ready(db, am)
    x = series(db, "future", "BSX50")
    one = derivatives.value_of(db, x, derivatives.spot(db, x, NOW9)) * data.FUTURE_MARGIN_BPS // BPS
    signed(db, team, 0, 0, NOW9, derivatives_naira=(one * 3 // 2) // 100)
    first = lending_empire.trade(db, am, x["id"], "long", 1, NOW9)
    assert "position_id" in first
    second = lending_empire.trade(db, am, x["id"], "long", 1, NOW9)
    assert second.get("waiting")
    sound(db)


def test_8_joining_the_crash_fund_once_a_fall_is_under_way_buys_nothing_for_it(db):
    empire, team = firm_of(db, n_cash=5_000_000_000)
    for who in ("head", "risk_manager"):
        ready(db, team[who])
    quarters.close_due_quarters(db, after_quarters(9))            # the index is noted at the close
    # The market falls hard during quarter 10; the head joins late.
    db.execute("UPDATE market_instruments SET last_price = coalesce(last_price, reference_price) * 75 / 100,"
               " reference_price = coalesce(last_price, reference_price) * 75 / 100")
    crashfund.ask_cover(db, team["head"], naira(1_000_000), after_quarters(9) + timedelta(hours=12))
    seed_fund(db, naira(50_000_000))
    quarters.close_due_quarters(db, after_quarters(10))
    q = _one(db, "SELECT * FROM crash_fund_quarters WHERE period = 10")
    assert q["triggered"] and q["paid_out"] == 0
    assert _one(db, "SELECT paid_out FROM crash_fund_members WHERE empire_id = %s", (empire["id"],))["paid_out"] == 0
    sound(db)


def test_9_only_the_asset_manager_the_risk_manager_or_the_head_acts_for_the_empire(db):
    empire, team = firm_of(db, n_cash=5_000_000_000)
    for who in ("head", "risk_manager"):
        ready(db, team[who])
    x = series(db, "call", "BSX50")
    for who in ("accountant", "journalist", "lawyer"):
        with pytest.raises(Exception):
            lending_empire.trade(db, team[who], x["id"], "long", 1, NOW9)
        with pytest.raises(Exception):
            lending_empire.borrow(db, team[who], bank_id(db), 100, NOW9)
        with pytest.raises(Exception):
            lending_empire.short(db, team[who], "GGM", 10, NOW9)


def test_10_every_escrow_matches_its_records_after_a_busy_quarter(db):
    player, account = trader(db, "asset_manager", "busy", level=10, cash_naira=2_000_000_000)
    give_shares(db, account, "IDC", 50_000_000)
    lending.take_margin(db, account, bank_id(db), naira(1_000_000), NOW9)
    lending.open_short(db, account, "GGM", 5_000, NOW9)
    for kind, underlying, side in (("call", "BSX50", "long"), ("put", "BSX50", "short"), ("future", "OIL", "long"), ("future", "NAIRA", "short")):
        derivatives.open_position(db, account, series(db, kind, underlying)["id"], side, 3, NOW9, player_id=player)
    quarters.close_due_quarters(db, after_quarters(9))
    assert lending.check_books(db) == [] and derivatives.check_books(db) == []
    assert ledger.balance(db, ledger.account_id(db, derivatives.MARGIN)) == _one(
        db, "SELECT coalesce(sum(margin), 0)::bigint AS m FROM derivative_positions WHERE status = 'open'")["m"]
    sound(db)
