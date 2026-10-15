"""Stage 9: what the independent review found, each with the test that shows it is fixed.

 1. A share split did not touch lent shares or options on the company: a short seller kept half the shares, an
    option holder was paid on the old strike.                                     Now both are adjusted by the ratio.
 2. Oil and naira futures settled at a level known all quarter (set after they settled): a riskless trade.
                                                                                 Now they settle after the new level is set.
 3. Interest and the lending fee were charged only on what was owed at the close: borrow after a close, repay
    before the next, and pay nothing.                                            Now both build up by the time held.
 4. Losses beyond the margin or collateral vanished; missed interest was forgiven; a loan in default took only cash.
                                                                                 Now a shortfall is owed (in default), missed
                                                                                 interest is owed with a 5% late charge, and
                                                                                 shares and bonds are sold for a default.
 5. Options were priced and settled on the single last trade (one small trade near the bell could move it).
                                                                                 Now the session's volume-weighted price.
 6. The quarter close worked from unlocked copies of rows a player could change at the same moment.
                                                                                 Now the rows are locked for the close.
 7. A margin loan backed by bonds could never be brought down (only shares were sold), and a forced sale cleared a
    default.                                                                     Now bonds are sold too; a default stays.
 8. The Risk Manager could sign itself any limit and speculate under it; two requests at once could both slip under
    a limit.                                                                     Now raising a limit needs the head, the Risk
                                                                                 Manager only buys options, and each check is
                                                                                 made under the empire's lock.
 9. Borrowed shares counted as security for a loan against shares.               Now they are taken off.
10. The crash fund's cash was never checked against its records.                 Now it is, at every close.
11. Smaller: the derivatives board worked out every share's risk hundreds of times; a future could be listed twice;
    net worth used the computer's clock, not the exchange's; a pension fund's seat could test the fund.
"""

from __future__ import annotations

import inspect
from datetime import timedelta

import psycopg
import pytest
from psycopg.rows import dict_row

from simulation import bonds, corporate, crashfund, derivatives, firm, ledger, lending, lending_empire, montecarlo, quarters, risk
from simulation import world_data as data
from simulation.money import BPS, naira
from tests.conftest import after_quarters
from tests.test_builds import pro
from tests.test_careers import NOW9, sound
from tests.test_firm import firm_of
from tests.test_lending import bank_id, price_of, set_price
from tests.test_objectives import give_shares

pytestmark = pytest.mark.world("eight")
LATER = NOW9 + timedelta(hours=1)


def _one(db, sql, params=()):
    with db.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(sql, params).fetchall()
    return rows[0] if rows else None


def _series(db, kind, underlying, expiry=9, nearest=None):
    derivatives.ensure(db, NOW9)
    with db.cursor(row_factory=dict_row) as cur:
        rows = cur.execute("SELECT * FROM derivative_series WHERE kind = %s AND underlying = %s AND expiry_period = %s AND status = 'open'"
                           " ORDER BY strike", (kind, underlying, expiry)).fetchall()
    return rows[0] if nearest is None else min(rows, key=lambda r: abs(r["strike"] - nearest))


def _split(db, ticker, ratio):
    company = _one(db, "SELECT id FROM companies WHERE ticker = %s", (ticker,))
    db.execute("INSERT INTO company_votes (company_id, subject, question, explanation, board, detail, opens_period, closes_period, status)"
               " VALUES (%s, 'share_split', 'Split?', 'Test', 'for', %s, 8, 9, 'passed')", (company["id"], psycopg.types.json.Jsonb({"ratio": ratio})))
    corporate._complete_splits(db, 9, LATER)


def test_1_a_split_adjusts_lent_shares_and_options_so_nobody_gains(db):
    player, account = pro(db, "asset_manager", "splitter", level=10, cash_naira=2_000_000_000)
    s = lending.open_short(db, account, "IDC", 10_000, NOW9)
    x = _series(db, "put", "IDC", nearest=price_of(db, "IDC"))
    p = derivatives.open_position(db, account, x["id"], "long", 10, NOW9, player_id=player)
    strike, entry = x["strike"], p["price"]
    _split(db, "IDC", 2)
    short = _one(db, "SELECT * FROM short_positions WHERE id = %s", (s["short_id"],))
    held = _one(db, "SELECT * FROM derivative_positions WHERE id = %s", (p["position_id"],))
    after = _one(db, "SELECT * FROM derivative_series WHERE id = %s", (x["id"],))
    assert short["shares"] == 20_000 and ledger.balance(db, account, "SHR-IDC") == 20_000
    assert held["contracts"] == 20 and after["strike"] == round(strike / 2) and held["entry_price"] == entry // 2
    # Closing the short takes back every share the split made of the borrowed ones: the player keeps none.
    lending.close_short(db, account, s["short_id"], LATER)
    assert ledger.balance(db, account, "SHR-IDC") == 0
    sound(db)


def test_2_oil_and_naira_futures_settle_at_the_new_level_not_one_known_all_quarter(db):
    player, account = pro(db, "asset_manager", "oilman", level=10, cash_naira=2_000_000_000)
    for u in ("OIL", "NAIRA"):
        derivatives.open_position(db, account, _series(db, "future", u)["id"], "short", 3, NOW9, player_id=player)
    before = _one(db, "SELECT oil_cents, fx FROM abroad_results ORDER BY period DESC LIMIT 1")
    quarters.close_due_quarters(db, after_quarters(9))
    new = _one(db, "SELECT period, oil_cents, fx FROM abroad_results ORDER BY period DESC LIMIT 1")
    assert new["period"] == 9
    oil = _one(db, "SELECT settled_spot FROM derivative_series WHERE kind = 'future' AND underlying = 'OIL' AND expiry_period = 9")
    fx = _one(db, "SELECT settled_spot FROM derivative_series WHERE kind = 'future' AND underlying = 'NAIRA' AND expiry_period = 9")
    assert oil["settled_spot"] == new["oil_cents"] and fx["settled_spot"] == new["fx"]
    assert (new["oil_cents"], new["fx"]) != (before["oil_cents"], before["fx"])          # (it was not known when they were sold)
    sound(db)


def test_3_interest_and_the_lending_fee_build_up_by_the_time_held(db):
    player, account = pro(db, "asset_manager", "inandout", level=10, cash_naira=10_000_000)
    loan = lending.take_personal(db, player, naira(1_000_000), NOW9)
    two_days = NOW9 + timedelta(days=2)
    start = ledger.balance(db, account)
    lending.repay(db, account, loan["loan_id"], naira(1_000_000), two_days)
    interest = lending.accrued(naira(1_000_000), loan["rate_bps"], NOW9, two_days)
    assert interest > 0 and ledger.balance(db, account) == start - naira(1_000_000) - interest
    assert _one(db, "SELECT status FROM player_loans WHERE id = %s", (loan["loan_id"],))["status"] == "repaid"
    # A short opened and closed inside a quarter pays the fee for the days it was held.
    s = lending.open_short(db, account, "GGM", 1_000, NOW9)
    lending.close_short(db, account, s["short_id"], two_days)
    assert _one(db, "SELECT fees_paid FROM short_positions WHERE id = %s", (s["short_id"],))["fees_paid"] == \
        lending.accrued(1_000 * price_of(db, "GGM"), data.SHORT_FEE_BPS, NOW9, two_days)
    sound(db)


def test_4_a_loss_beyond_the_collateral_is_owed_missed_interest_carries_a_late_charge_and_a_default_sells_holdings(db):
    player, account = pro(db, "asset_manager", "underwater", level=10, cash_naira=100_000_000)
    lending.open_short(db, account, "GGM", 10_000, NOW9)
    ledger.transfer(db, payer=account, receiver=ledger.account_id(db, ledger.TREASURY), amount=ledger.balance(db, account),
                    kind="test_cash", memo="Test: spent")
    set_price(db, "GGM", price_of(db, "GGM") * 3)                       # the price trebles: the collateral covers half
    lending.at_bell(db, LATER, NOW9.date())
    owed = _one(db, "SELECT * FROM player_loans WHERE borrower = %s AND kind = 'shortfall'", (account,))
    assert owed and owed["status"] == "default" and owed["outstanding"] > 0 and owed["creditor"] is not None
    with pytest.raises(lending.LendingError, match="default"):
        lending.open_short(db, account, "IDC", 10, LATER)
    with pytest.raises(derivatives.DerivativesError, match="default"):
        derivatives.open_position(db, account, _series(db, "call", "BSX50")["id"], "long", 1, LATER, player_id=player)
    # Shares held are sold at the close to pay it.
    given = give_shares(db, account, "IDC", 1_000_000)
    quarters.close_due_quarters(db, after_quarters(9))
    assert ledger.balance(db, account, "SHR-IDC") < given
    assert _one(db, "SELECT outstanding FROM player_loans WHERE id = %s", (owed["id"],))["outstanding"] < owed["outstanding"]
    sound(db)


def test_4b_interest_missed_at_the_close_is_owed_with_the_late_charge(db):
    player, account = pro(db, "asset_manager", "late", level=10, cash_naira=0)
    loan = lending.take_personal(db, player, naira(1_000_000), NOW9)
    ledger.transfer(db, payer=account, receiver=ledger.account_id(db, ledger.TREASURY), amount=ledger.balance(db, account),
                    kind="test_cash", memo="Test: spent")
    quarters.close_due_quarters(db, after_quarters(9))
    row = _one(db, "SELECT * FROM player_loans WHERE id = %s", (loan["loan_id"],))
    due = lending.accrued(naira(1_000_000), loan["rate_bps"], NOW9, lending._quarter_end(db, 9))
    # (Salary may have arrived at the close and paid part; what was not paid is owed, 5% more.)
    assert row["arrears"] > 0 and row["arrears"] <= due + due * data.LOAN_LATE_PENALTY_BPS // BPS
    assert row["missed"] == 1
    sound(db)


def test_5_options_are_priced_on_the_sessions_volume_weighted_price_not_the_last_trade(db):
    x = _series(db, "call", "IDC")
    before = derivatives.spot(db, x, NOW9)
    db.execute("UPDATE market_instruments SET last_price = last_price * 3 FROM companies c WHERE c.id = company_id AND c.ticker = 'IDC'"
               " AND last_price IS NOT NULL")
    assert derivatives.spot(db, x, NOW9) == before
    assert "market_trades" in inspect.getsource(derivatives.share_level)


def test_6_the_quarter_close_locks_the_rows_it_changes():
    assert "FOR UPDATE OF l" in inspect.getsource(lending.close) and "FOR UPDATE OF s" in inspect.getsource(lending.close)
    assert "outstanding = outstanding - %s" in inspect.getsource(lending.close)
    assert "FOR UPDATE OF p" in inspect.getsource(derivatives.close)
    assert "FOR UPDATE OF m" in inspect.getsource(crashfund.close)


def test_7_a_loan_backed_by_bonds_is_brought_down_by_selling_bonds_and_a_default_stays_a_default(db):
    player, account = pro(db, "asset_manager", "bondholder", level=10, cash_naira=200_000_000)
    line = next(b for b in bonds.listing(db, NOW9) if b["issuer"] == "Federal Government" and b["ask"] > 0 and b["kind"] != "bill")
    code, units = line["code"], naira(100_000_000) // line["ask"]
    bonds.trade(db, account=account, code=code, side="buy", units=units, now=NOW9)
    asset = bonds.find(db, code)["asset"]
    held_before = ledger.balance(db, account, asset)
    ledger.transfer(db, payer=account, receiver=ledger.account_id(db, ledger.TREASURY), amount=ledger.balance(db, account),
                    kind="test_cash", memo="Test: spent")
    room = lending.margin_limit(db, account, NOW9)
    loan = lending.take_margin(db, account, bank_id(db), room, NOW9)
    ledger.transfer(db, payer=account, receiver=ledger.account_id(db, ledger.TREASURY), amount=ledger.balance(db, account),
                    kind="test_cash", memo="Test: spent the loan")
    db.execute("UPDATE player_loans SET outstanding = outstanding * 9 / 5, status = 'default' WHERE id = %s", (loan["loan_id"],))
    owed = _one(db, "SELECT outstanding FROM player_loans WHERE id = %s", (loan["loan_id"],))["outstanding"]
    lending.at_bell(db, LATER, NOW9.date())
    row = _one(db, "SELECT * FROM player_loans WHERE id = %s", (loan["loan_id"],))
    assert ledger.balance(db, account, asset) < held_before            # bonds were sold
    assert row["outstanding"] < owed and row["status"] == "default"   # the loan came down; the default stands
    sound(db)


def test_8_the_risk_manager_cannot_sign_itself_room_or_write_options_and_two_requests_cannot_both_slip_under(db):
    empire, team = firm_of(db, n_cash=5_000_000_000)
    asked = lending_empire.set_limits(db, team["risk_manager"], 0, 0, NOW9, derivatives_naira=1_000_000_000)
    assert asked["waiting"] and asked["derivatives_limit_naira"] == 0
    firm.decide(db, team["head"], asked["approval_id"], True, "", NOW9)
    assert lending_empire.limits(db, empire)["derivatives_limit_naira"] == 1_000_000_000
    lowered = lending_empire.set_limits(db, team["risk_manager"], 0, 0, NOW9, derivatives_naira=500_000_000)
    assert "waiting" not in lowered and lowered["derivatives_limit_naira"] == 500_000_000      # lowering is at once
    for kind, side in (("future", "long"), ("call", "short")):
        with pytest.raises(Exception, match="buys protection"):
            lending_empire.trade(db, team["risk_manager"], _series(db, kind, "BSX50")["id"], side, 1, NOW9)
    for f in (lending_empire.borrow, lending_empire.short, lending_empire.trade):
        assert "_lock(conn" in inspect.getsource(f)
    sound(db)


def test_9_borrowed_shares_are_not_security_for_a_loan(db):
    player, account = pro(db, "asset_manager", "pledger", level=10, cash_naira=100_000_000)
    lending.open_short(db, account, "GGM", 20_000, NOW9)
    assert ledger.balance(db, account, "SHR-GGM") == 20_000
    assert lending.margin_limit(db, account, NOW9) == 0
    with pytest.raises(lending.LendingError):
        lending.take_margin(db, account, bank_id(db), naira(1_000), NOW9)


def test_10_the_crash_fund_is_checked_against_its_records(db):
    empire, team = firm_of(db, n_cash=5_000_000_000)
    crashfund.ask_cover(db, team["head"], naira(10_000_000), NOW9)
    quarters.close_due_quarters(db, after_quarters(9))
    assert crashfund.check_books(db) == []
    ledger.transfer(db, payer=ledger.account_id(db, ledger.TREASURY), receiver=crashfund._fund(db), amount=1, kind="test_cash", memo="Test: stray")
    assert crashfund.check_books(db)


def test_11_the_board_works_out_risk_once_futures_are_listed_once_and_the_clock_and_seats_are_right(db, monkeypatch):
    calls = []
    real = risk.share_risk
    monkeypatch.setattr(risk, "share_risk", lambda conn: calls.append(1) or real(conn))
    derivatives.board(db, NOW9)
    assert len(calls) == 1
    x = _series(db, "future", "OIL")
    with pytest.raises(psycopg.errors.UniqueViolation):
        with db.transaction():
            db.execute("INSERT INTO derivative_series (kind, underlying, strike, expiry_period, listed_period) VALUES ('future', 'OIL', NULL, %s, 8)",
                       (x["expiry_period"],))
    assert "datetime.now" not in inspect.getsource(derivatives._players_derivatives)
    assert "pension" in inspect.getsource(montecarlo.run)
