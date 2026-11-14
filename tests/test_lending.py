"""Stage 9, Part A: the stochastic engine, risk figures, "What could happen?", borrowing and short selling."""

from __future__ import annotations

import math
from datetime import timedelta

import pytest
from psycopg.rows import dict_row

from simulation import investors, ledger, lending, lending_empire, montecarlo, quarters, risk, stochastic
from simulation import world_data as data
from simulation.money import BPS, naira
from tests.conftest import after_quarters
from tests.test_builds import pro
from tests.test_careers import NOW9, sound
from tests.test_firm import firm_of
from tests.test_objectives import give_cash, give_shares

pytestmark = pytest.mark.world("eight")
LATER = NOW9 + timedelta(hours=1)


def _dicts(db, sql, params=()):
    with db.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def _one(db, sql, params=()):
    rows = _dicts(db, sql, params)
    return rows[0] if rows else None


def price_of(db, ticker):
    return _one(db, "SELECT coalesce(m.last_price, m.reference_price) AS p FROM market_instruments m JOIN companies c ON c.id = m.company_id"
                    " WHERE c.ticker = %s", (ticker,))["p"]


def set_price(db, ticker, price):
    """Test set-up: the share's price moves (as if it had traded there)."""
    db.execute("UPDATE market_instruments SET last_price = %s, reference_price = %s FROM companies c WHERE c.id = company_id AND c.ticker = %s",
               (price, price, ticker))


def bank_id(db):
    return _one(db, "SELECT id FROM companies WHERE sector = 'banking' AND status = 'trading' ORDER BY ticker LIMIT 1")["id"]


def ring(db, day_offset=1):
    """Ring the Closing Bell for a trading day after NOW9."""
    return lending.at_bell(db, NOW9 + timedelta(days=day_offset, hours=-1), (NOW9 + timedelta(days=day_offset - 1)).date())


# ---------------------------------------------------------------------------
# The stochastic engine
# ---------------------------------------------------------------------------

def test_draws_have_the_old_typical_spread_fat_tails_and_shared_forces():
    seed = "x" * 32
    plain = [stochastic.fat_tailed(seed, "s", n) for n in range(4000)]
    spread = math.sqrt(sum(v * v for v in plain) / len(plain))
    assert 0.9 < spread < 1.1
    # Fat tails: far more draws beyond three spreads than a bell curve's 0.27%.
    assert sum(1 for v in plain if abs(v) > 3) / len(plain) > 0.006
    # The same inputs always give the same answer.
    assert stochastic.shock_bps(seed, "AAA", 5, "sales", 300) == stochastic.shock_bps(seed, "AAA", 5, "sales", 300)
    # Two oil companies lean on energy together; an oil company and a farm do not.
    oil = [stochastic.shock(seed, "o1", p, "d", stochastic.sector_loadings("oil_gas")) for p in range(1, 1500)]
    oil2 = [stochastic.shock(seed, "o2", p, "d", stochastic.sector_loadings("oil_gas")) for p in range(1, 1500)]
    farm = [stochastic.shock(seed, "f", p, "d", stochastic.sector_loadings("agriculture")) for p in range(1, 1500)]

    def corr(a, b):
        ma, mb = sum(a) / len(a), sum(b) / len(b)
        cov = sum((x - ma) * (y - mb) for x, y in zip(a, b))
        return cov / math.sqrt(sum((x - ma) ** 2 for x in a) * sum((y - mb) ** 2 for y in b))
    assert corr(oil, oil2) > 0.5 and abs(corr(oil, farm)) < 0.1
    # Never beyond 2.5 times the old limit.
    assert all(abs(stochastic.shock_bps(seed, "t", p, "x", 1000)) <= 2500 for p in range(3000))
    assert all(sum(w * w for w in row.values()) < 1 for row in data.SECTOR_FACTOR_LOADINGS.values())


def test_the_quarters_forces_are_recorded_and_never_sent(db, client):
    assert db.execute("SELECT count(*) FROM stochastic_factors WHERE period = 8").fetchone()[0] == len(stochastic.FACTORS)
    from tests.conftest import ADULT, join
    join(client, ADULT)
    for path in ("/api/market", "/api/economy", "/api/borrowing", "/api/share-risk"):
        text = client.get(path).text
        assert "stochastic" not in text and "factor" not in text.lower(), path


# ---------------------------------------------------------------------------
# Risk figures and "What could happen?"
# ---------------------------------------------------------------------------

def test_every_traded_share_has_a_volatility_and_a_beta(db):
    found = risk.share_risk(db)
    assert found
    assert all(r["volatility_bps"] > 0 for r in found.values())
    assert any(r["enough"] for r in found.values()) or all(r["volatility_bps"] == round(risk.USUAL_DAILY * math.sqrt(28) * BPS) for r in found.values())


def test_what_could_happen_uses_public_figures_and_charges_after_the_free_run(db):
    player, account = pro(db, "risk_manager", "tester", cash_naira=1_000_000)
    give_shares(db, account, "IDC", 5_000)
    give_shares(db, account, "GGM", 5_000)
    first = montecarlo.run(db, player, "portfolio", LATER)
    assert first["fee"] == 0 and first["paths"] == data.MONTE_CARLO_PATHS and len(first["fan"]) == data.MONTE_CARLO_HORIZONS["quarter"]
    assert first["worst_likely"] <= first["median"] <= first["best_likely"]
    assert 0 <= first["chance_of_loss_bps"] <= BPS and first["value_at_risk"] >= 0
    before = ledger.balance(db, account)
    second = montecarlo.run(db, player, "share", LATER, ticker="IDC", horizon="year")
    assert second["fee"] == naira(data.MONTE_CARLO_FEE_NAIRA) and ledger.balance(db, account) == before - second["fee"]
    assert len(second["fan"]) == 28
    # The world's secret seed is never read by the tool.
    import inspect
    assert "fortune_seed" not in inspect.getsource(montecarlo) and "stochastic" not in inspect.getsource(montecarlo)
    with pytest.raises(montecarlo.MonteCarloError):
        broke, _ = pro(db, "investment_banker", "onlycash", cash_naira=1)
        montecarlo.run(db, broke, "portfolio", LATER)
    sound(db)


# ---------------------------------------------------------------------------
# Personal loans
# ---------------------------------------------------------------------------

def test_a_personal_loan_is_limited_by_salary_and_repaid_over_two_years(db):
    player, account = pro(db, "asset_manager", "borrower", level=10, cash_naira=0)
    most = lending.personal_limit(db, player, NOW9)
    assert most > 0
    with pytest.raises(lending.LendingError, match="at most"):
        lending.take_personal(db, player, most + 1, NOW9)
    taken = lending.take_personal(db, player, most, NOW9)
    assert ledger.balance(db, account) == most
    assert lending.personal_limit(db, player, NOW9) == 0
    quarters.close_due_quarters(db, after_quarters(9))
    loan = _one(db, "SELECT * FROM player_loans WHERE id = %s", (taken["loan_id"],))
    assert loan["outstanding"] == most - most // data.PERSONAL_LOAN_TERM_QUARTERS and loan["missed"] == 0
    assert db.execute("SELECT count(*) FROM ledger_transactions WHERE kind = 'player_loan_interest'").fetchone()[0] >= 1
    sound(db)


def test_two_missed_payments_put_a_loan_in_default_and_stop_more_borrowing(db):
    from simulation import careers
    player, account = pro(db, "asset_manager", "late", level=10, cash_naira=0)
    taken = lending.take_personal(db, player, naira(100_000), NOW9)
    ledger.transfer(db, payer=account, receiver=ledger.account_id(db, ledger.TREASURY), amount=ledger.balance(db, account),
                    kind="test_cash", memo="Test: spent")
    careers.leave_job(db, player, NOW9)
    quarters.close_due_quarters(db, after_quarters(10))
    loan = _one(db, "SELECT * FROM player_loans WHERE id = %s", (taken["loan_id"],))
    assert loan["status"] == "default"
    with pytest.raises(lending.LendingError, match="default"):
        lending.take_margin(db, account, bank_id(db), 100, after_quarters(10) + timedelta(hours=2))
    sound(db)


# ---------------------------------------------------------------------------
# Loans against shares
# ---------------------------------------------------------------------------

def test_a_margin_loan_is_half_the_shares_and_a_fall_brings_a_call_then_a_forced_sale(db):
    player, account = pro(db, "asset_manager", "geared", level=10, cash_naira=0)
    held = give_shares(db, account, "IDC", 2_000_000)
    price = price_of(db, "IDC")
    worth = held * price
    assert lending.margin_limit(db, account, NOW9) == worth // 2
    with pytest.raises(lending.LendingError, match="half"):
        lending.take_margin(db, account, bank_id(db), worth // 2 + 1, NOW9)
    lending.take_margin(db, account, bank_id(db), worth // 2, NOW9)
    # The cash borrowed is spent elsewhere: the loan is now against the shares alone.
    ledger.transfer(db, payer=account, receiver=ledger.account_id(db, ledger.TREASURY), amount=worth // 2, kind="test_cash", memo="Test: spent")
    set_price(db, "IDC", price * 68 // 100)               # the loan is now 73% of what is held: a margin call
    assert ring(db, 1)["calls"] == 1
    loan = _one(db, "SELECT * FROM player_loans WHERE borrower = %s", (account,))
    assert loan["call_since"] is not None
    ring(db, 2)                                            # not met by the next bell: shares are sold
    loan = _one(db, "SELECT * FROM player_loans WHERE borrower = %s", (account,))
    assert loan["call_since"] is None and loan["outstanding"] < worth // 2
    held = lending.holdings_value(db, account, NOW9)
    assert loan["outstanding"] * BPS // held["total"] <= data.MARGIN_LOAN_MOST_BPS + 300
    assert _one(db, "SELECT count(*) AS n FROM lending_events WHERE account = %s AND kind = 'forced_sale'", (account,))["n"] == 1
    sound(db)


def test_all_borrowing_together_is_at_most_twice_what_a_player_is_worth(db):
    player, account = pro(db, "asset_manager", "stretched", level=20, cash_naira=0)
    held = give_shares(db, account, "IDC", 2_000_000)
    worth = held * price_of(db, "IDC")
    lending.take_margin(db, account, bank_id(db), worth // 2, NOW9)
    # Borrowed shares sold short add to it; past twice the player's worth, no more. (Collateral is cash: give enough.)
    give_cash(db, account, 50_000_000)
    equity = lending._equity(db, account, NOW9)
    too_many = (2 * equity - worth // 2) // price_of(db, "GGM") + 10
    with pytest.raises(lending.LendingError, match="times"):
        lending.open_short(db, account, "GGM", too_many, NOW9)
    # A personal loan is limited by salary, not by worth.
    assert lending.personal_limit(db, player, NOW9) > 0


# ---------------------------------------------------------------------------
# Short selling
# ---------------------------------------------------------------------------

def test_a_short_borrows_from_the_pension_funds_holds_150_percent_and_closes_with_a_profit_when_the_price_falls(db):
    player, account = pro(db, "asset_manager", "bear", level=10, cash_naira=50_000_000)
    price = price_of(db, "GGM")
    shares = 10_000
    assert lending.lendable(db, _one(db, "SELECT id FROM companies WHERE ticker = 'GGM'")["id"]) >= shares
    before = ledger.balance(db, account)
    s = lending.open_short(db, account, "GGM", shares, NOW9)
    assert s["collateral"] == shares * price * 3 // 2
    assert ledger.balance(db, account) == before - s["collateral"]
    asset = _one(db, "SELECT share_asset FROM companies WHERE ticker = 'GGM'")["share_asset"]
    assert ledger.balance(db, account, asset) == shares
    # The player sells the borrowed shares; the price falls; they buy them back cheaper (here: a test transfer) and close.
    ledger.post(db, kind="test_cash", memo="Test: sold the borrowed shares", legs=[
        ledger.Leg(account, -shares, asset), ledger.Leg(ledger.account_id(db, ledger.INVESTORS_PUBLIC), shares, asset),
        ledger.Leg(ledger.account_id(db, ledger.INVESTORS_PUBLIC), -shares * price), ledger.Leg(account, shares * price)])
    low = price * 80 // 100
    ledger.post(db, kind="test_cash", memo="Test: bought them back", legs=[
        ledger.Leg(ledger.account_id(db, ledger.INVESTORS_PUBLIC), -shares, asset), ledger.Leg(account, shares, asset),
        ledger.Leg(account, -shares * low), ledger.Leg(ledger.account_id(db, ledger.INVESTORS_PUBLIC), shares * low)])
    lending.close_short(db, account, s["short_id"], LATER)
    fee = lending.accrued(shares * price, data.SHORT_FEE_BPS, NOW9, LATER)          # the lending fee, for the hour it was held
    assert fee > 0
    assert ledger.balance(db, account) == before + shares * (price - low) - fee
    assert ledger.balance(db, ledger.account_id(db, lending.COLLATERAL)) == 0
    sound(db)


def test_a_rising_price_brings_a_call_and_then_a_forced_buy_in(db):
    player, account = pro(db, "asset_manager", "squeezed", level=10, cash_naira=50_000_000)
    price = price_of(db, "GGM")
    s = lending.open_short(db, account, "GGM", 10_000, NOW9)
    set_price(db, "GGM", price * 125 // 100)              # collateral now 120% of value: a call
    assert ring(db, 1)["calls"] == 1
    set_price(db, "GGM", price * 140 // 100)              # 107%: bought back by force
    assert ring(db, 2)["buy_ins"] == 1
    row = _one(db, "SELECT * FROM short_positions WHERE id = %s", (s["short_id"],))
    assert row["status"] == "bought_in" and row["collateral"] == 0
    assert ledger.balance(db, ledger.account_id(db, lending.COLLATERAL)) == 0
    sound(db)


def test_the_lender_is_paid_the_dividend_and_a_fee_and_short_interest_is_published_without_names(db, client):
    player, account = pro(db, "asset_manager", "payer", level=10, cash_naira=50_000_000)
    s = lending.open_short(db, account, "GGM", 10_000, NOW9)
    lender = ledger.account_id(db, lending.LENDER)
    quarters.close_due_quarters(db, after_quarters(9))
    fees = _one(db, "SELECT fees_paid FROM short_positions WHERE id = %s", (s["short_id"],))["fees_paid"]
    assert fees > 0
    paid_dividend = _one(db, "SELECT coalesce(sum(e.amount), 0)::bigint AS d FROM ledger_entries e JOIN ledger_transactions t ON t.id = e.transaction_id"
                             " WHERE t.kind = 'lent_dividend' AND e.account_id = %s", (lender,))["d"]
    ggm_paid = _one(db, "SELECT dividends_paid FROM company_results r JOIN companies c ON c.id = r.company_id WHERE c.ticker = 'GGM' AND r.period = 9")
    if ggm_paid["dividends_paid"] > 0:
        assert paid_dividend > 0
    interest = lending.short_interest(db)
    assert interest and all(v > 0 for v in interest.values())
    sound(db)


def test_the_pension_funds_lend_at_most_three_tenths_and_recall_when_they_hold_too_few(db):
    company = _one(db, "SELECT id, share_asset FROM companies WHERE ticker = 'GGM'")
    lender = ledger.account_id(db, lending.LENDER)
    held = ledger.balance(db, lender, company["share_asset"])
    most = lending.lendable(db, company["id"])
    assert most == held * data.LENDING_POOL_BPS // BPS
    player, account = pro(db, "asset_manager", "big", level=10, cash_naira=200_000_000_000)
    with pytest.raises(lending.LendingError, match="lend only"):
        lending.open_short(db, account, "GGM", most + 1, NOW9)
    s = lending.open_short(db, account, "GGM", most, NOW9)
    # The pension funds sell most of what they still hold: they have now lent too much, and recall.
    ledger.transfer(db, payer=lender, receiver=ledger.account_id(db, ledger.INVESTORS_PUBLIC), amount=ledger.balance(db, lender, company["share_asset"]) // 2,
                    asset=company["share_asset"], kind="test_cash", memo="Test: the funds sold")
    quarters.close_due_quarters(db, after_quarters(9))
    assert _one(db, "SELECT recalled_period FROM short_positions WHERE id = %s", (s["short_id"],))["recalled_period"] == 9
    quarters.close_due_quarters(db, after_quarters(10))
    assert _one(db, "SELECT status FROM short_positions WHERE id = %s", (s["short_id"],))["status"] == "bought_in"
    sound(db)


# ---------------------------------------------------------------------------
# Empires
# ---------------------------------------------------------------------------

def signed(db, team, borrow_naira, short_naira, now, derivatives_naira=None):
    """The Risk Manager raises the limits; raising them needs the head, who approves."""
    from simulation import firm
    asked = lending_empire.set_limits(db, team["risk_manager"], borrow_naira, short_naira, now, derivatives_naira=derivatives_naira)
    if asked.get("waiting"):
        firm.decide(db, team["head"], asked["approval_id"], True, "", now)
    from simulation import empires
    return lending_empire.limits(db, empires._empire(db, empires.seat_of(db, team["head"])["empire_id"]))


def test_an_empire_borrows_and_shorts_inside_the_risk_managers_limits_and_above_them_the_head_decides(db):
    from simulation import firm
    empire, team = firm_of(db)
    give_shares(db, empire["account_id"], "IDC", 50_000_000)
    with pytest.raises(Exception, match="Risk Manager"):
        lending_empire.set_limits(db, team["asset_manager"], 1_000_000, 0, NOW9)
    asked = lending_empire.set_limits(db, team["risk_manager"], 1_000_000, 0, NOW9)
    assert asked["waiting"] and asked["borrow_limit_naira"] == 0            # raising a limit needs the head
    signed(db, team, 1_000_000, 0, NOW9)
    member_of_am = None
    from tests.test_firm import member
    member_of_am = member(db, empire, team["head"], "asset_manager", "trader")
    from tests.test_derivatives import ready
    ready(db, member_of_am)
    inside = lending_empire.borrow(db, member_of_am, bank_id(db), naira(500_000), NOW9)
    assert "loan_id" in inside
    above = lending_empire.borrow(db, member_of_am, bank_id(db), naira(900_000), NOW9)
    assert above["waiting"]
    approval = _one(db, "SELECT * FROM empire_approvals WHERE id = %s", (above["approval_id"],))
    assert approval["desk"] == "head" and approval["kind"] == "empire_borrow"
    firm.decide(db, team["head"], approval["id"], True, "", LATER)
    assert lending.margin_owed(db, empire["account_id"]) == naira(1_400_000)
    with pytest.raises(Exception):
        lending_empire.short(db, team["investment_banker"], "GGM", 100, NOW9)
    sound(db)


def test_the_computer_investors_have_tempers_and_bid_up_a_rising_heavily_shorted_share():
    assert investors.temper_bps("investors:public", [1000, 1100], 0) == 300            # +10%: chases it, capped at 3%
    assert investors.temper_bps("investors:institutions", [1000, 1100], 0) == -150      # leans against it
    assert investors.temper_bps("investors:public", [1000, 1050], 1000) > investors.temper_bps("investors:public", [1000, 1050], 0)
    assert investors.temper_bps("investors:public", [1000, 950], 1000) == investors.temper_bps("investors:public", [1000, 950], 0)
