"""Stage 9, Part B: options and futures with the market makers' desk, the hedging desk and the crash fund."""

from __future__ import annotations

from datetime import timedelta

import pytest
from psycopg.rows import dict_row

from simulation import crashfund, derivatives, ledger, lending_empire, quarters
from simulation import world_data as data
from simulation.money import BPS, naira
from tests.conftest import after_quarters
from tests.test_builds import pro
from tests.test_careers import NOW9, sound
from tests.test_firm import firm_of
from tests.test_lending import set_price, signed

pytestmark = pytest.mark.world("eight")
OPEN = NOW9                       # the ninth quarter's first trading day, with the market open
LATER = OPEN + timedelta(hours=1)


def _dicts(db, sql, params=()):
    with db.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def _one(db, sql, params=()):
    rows = _dicts(db, sql, params)
    return rows[0] if rows else None


def series(db, kind, underlying, expiry=9, nearest=None):
    derivatives.ensure(db, OPEN)
    rows = _dicts(db, "SELECT * FROM derivative_series WHERE kind = %s AND underlying = %s AND expiry_period = %s ORDER BY strike",
                  (kind, underlying, expiry))
    if nearest is None:
        return rows[0]
    return min(rows, key=lambda r: abs(r["strike"] - nearest))


def test_options_and_futures_are_listed_for_this_quarter_and_the_next(db):
    derivatives.ensure(db, OPEN)
    expiries = {r["expiry_period"] for r in _dicts(db, "SELECT DISTINCT expiry_period FROM derivative_series WHERE status = 'open'")}
    assert expiries == {9, 10}
    futures = {r["underlying"] for r in _dicts(db, "SELECT underlying FROM derivative_series WHERE kind = 'future'")}
    assert futures == set(derivatives.FUTURES)
    shares = {r["underlying"] for r in _dicts(db, "SELECT underlying FROM derivative_series WHERE company_id IS NOT NULL")}
    assert 0 < len(shares) <= 50
    per = _dicts(db, "SELECT count(*) AS n FROM derivative_series WHERE underlying = %s AND expiry_period = 9", (sorted(shares)[0],))[0]["n"]
    assert per == len(data.OPTION_STRIKES_BPS) * 2
    derivatives.ensure(db, OPEN)                             # asking again adds nothing
    assert db.execute("SELECT count(*) FROM derivative_series").fetchone()[0] == len(_dicts(db, "SELECT id FROM derivative_series"))


def test_prices_follow_the_model_calls_rise_with_the_share_and_the_desk_keeps_a_spread(db):
    s = series(db, "call", "IDC", nearest=None)
    q = derivatives.quote(db, s, OPEN)
    assert q["bid"] < q["fair"] < q["ask"]
    # A call is worth more when the share is higher; a put less.
    low = derivatives.fair(db, s, OPEN, s["strike"] * 9 // 10)
    high = derivatives.fair(db, s, OPEN, s["strike"] * 11 // 10)
    assert high > low
    # Put-call parity holds (within a kobo or so per share): call - put = S - K e^(-rt).
    put = series(db, "put", "IDC")
    put = next(p for p in _dicts(db, "SELECT * FROM derivative_series WHERE kind = 'put' AND underlying = 'IDC' AND expiry_period = 9")
               if p["strike"] == s["strike"])
    level = derivatives.spot(db, s, OPEN)
    import math
    t = derivatives.years_left(db, s, OPEN)
    r = derivatives.policy_rate(db) / BPS
    lhs = derivatives.fair(db, s, OPEN) - derivatives.fair(db, put, OPEN)
    rhs = (level - s["strike"] * math.exp(-r * t)) * derivatives.multiplier(s)
    assert abs(lhs - rhs) <= 200
    # The value of what a contract is on, in each kind.
    f = series(db, "future", "NAIRA")
    assert derivatives.value_of(db, f, derivatives.spot(db, f, OPEN)) == derivatives.spot(db, f, OPEN) * 1000


def test_a_bought_call_pays_out_at_the_close_when_the_share_rises(db):
    player, account = pro(db, "asset_manager", "bull", cash_naira=50_000_000)
    s = series(db, "call", "IDC", nearest=derivatives.spot(db, series(db, "call", "IDC"), OPEN))
    before = ledger.balance(db, account)
    done = derivatives.open_position(db, account, s["id"], "long", 10, OPEN, player_id=player)
    assert ledger.balance(db, account) == before - done["price"] * 10
    set_price(db, "IDC", s["strike"] * 13 // 10)            # 30% above the strike at the close
    quarters.close_due_quarters(db, after_quarters(9))
    p = _one(db, "SELECT * FROM derivative_positions WHERE id = %s", (done["position_id"],))
    assert p["status"] == "expired"
    payoff = (s["strike"] * 13 // 10 - s["strike"]) * 100 * 10
    assert ledger.balance(db, account) >= before - done["price"] * 10 + payoff - 1000
    assert p["result"] == payoff - done["price"] * 10
    sound(db)


def test_writing_an_option_needs_margin_and_a_rise_brings_a_call_then_a_forced_close(db):
    player, account = pro(db, "asset_manager", "writer", cash_naira=50_000_000)
    s = series(db, "call", "IDC", nearest=derivatives.spot(db, series(db, "call", "IDC"), OPEN))
    done = derivatives.open_position(db, account, s["id"], "short", 10, OPEN, player_id=player)
    assert done["margin"] == derivatives.writer_margin(db, s, OPEN) * 10
    held = ledger.account_id(db, derivatives.MARGIN)
    assert ledger.balance(db, held) == done["margin"]
    set_price(db, "IDC", s["strike"] * 15 // 10)
    first = derivatives.at_bell(db, OPEN + timedelta(hours=10), OPEN.date())
    assert first["calls"] == 1
    second = derivatives.at_bell(db, OPEN + timedelta(days=1, hours=10), (OPEN + timedelta(days=1)).date())
    assert second["closed"] == 1
    assert _one(db, "SELECT status FROM derivative_positions WHERE id = %s", (done["position_id"],))["status"] == "closed_by_force"
    assert ledger.balance(db, held) == 0
    sound(db)


def test_a_future_is_settled_every_night_and_its_margin_moves_with_the_price(db):
    player, account = pro(db, "asset_manager", "futures", cash_naira=50_000_000)
    f = series(db, "future", "BSX50")
    done = derivatives.open_position(db, account, f["id"], "long", 2, OPEN, player_id=player)
    margin0 = done["margin"]
    assert margin0 == derivatives.value_of(db, f, derivatives.spot(db, f, OPEN)) * data.FUTURE_MARGIN_BPS // BPS * 2
    # Every share up 5%: the index rises, the long future gains, and its margin grows by the gain.
    db.execute("UPDATE market_instruments SET last_price = coalesce(last_price, reference_price) * 105 / 100,"
               " reference_price = coalesce(last_price, reference_price) * 105 / 100")
    derivatives.at_bell(db, OPEN + timedelta(hours=10), OPEN.date())
    p = _one(db, "SELECT * FROM derivative_positions WHERE id = %s", (done["position_id"],))
    assert p["margin"] > margin0 and p["mark"] > done["price"]
    result = derivatives.close_position(db, account, done["position_id"], OPEN + timedelta(days=1))
    assert result["result"] > 0
    assert ledger.balance(db, ledger.account_id(db, derivatives.MARGIN)) == 0
    sound(db)


def test_every_future_settles_at_the_quarters_close_and_the_next_are_listed(db):
    player, account = pro(db, "asset_manager", "macro", cash_naira=500_000_000)
    ids = []
    for u in derivatives.FUTURES:
        f = series(db, "future", u)
        ids.append(derivatives.open_position(db, account, f["id"], "short", 1, OPEN, player_id=player)["position_id"])
    quarters.close_due_quarters(db, after_quarters(9))
    assert all(_one(db, "SELECT status FROM derivative_positions WHERE id = %s", (i,))["status"] == "expired" for i in ids)
    assert {r["expiry_period"] for r in _dicts(db, "SELECT DISTINCT expiry_period FROM derivative_series WHERE status = 'open'")} == {10, 11}
    sound(db)


def test_the_desk_deals_only_while_the_market_is_open_and_limits_contracts(db):
    player, account = pro(db, "asset_manager", "night", cash_naira=500_000_000)
    s = series(db, "future", "OIL")
    with pytest.raises(derivatives.DerivativesError, match="market is open"):
        derivatives.open_position(db, account, s["id"], "long", 1, OPEN.replace(hour=23), player_id=player)
    with pytest.raises(derivatives.DerivativesError, match="At most"):
        derivatives.open_position(db, account, s["id"], "long", data.MOST_CONTRACTS_A_SERIES + 1, OPEN, player_id=player)


def test_the_risk_manager_buys_protection_inside_the_limit_and_the_hedge_is_scored(db):
    empire, team = firm_of(db, n_cash=5_000_000_000)
    put = series(db, "put", "BSX50", nearest=derivatives.index_now(db, OPEN))
    with pytest.raises(Exception):
        lending_empire.trade(db, team["journalist"], put["id"], "long", 1, OPEN)
    # No limit signed: above it, the head decides.
    waiting = lending_empire.trade(db, team["risk_manager"], put["id"], "long", 2, OPEN)
    assert waiting["waiting"]
    signed(db, team, 0, 0, OPEN, derivatives_naira=50_000_000)
    done = lending_empire.trade(db, team["risk_manager"], put["id"], "long", 2, OPEN)
    p = _one(db, "SELECT * FROM derivative_positions WHERE id = %s", (done["position_id"],))
    assert p["purpose"] and p["account"] == empire["account_id"]
    quarters.close_due_quarters(db, after_quarters(9))
    assert _one(db, "SELECT count(*) AS n FROM empire_events WHERE empire_id = %s AND words LIKE 'The hedge%%'", (empire["id"],))["n"] == 1
    sound(db)


def seed_fund(db, amount):
    """Premiums other empires paid in an earlier quarter, so the fund can pay (recorded, as the fund's check requires)."""
    fund = crashfund._fund(db)
    ledger.transfer(db, payer=ledger.account_id(db, ledger.TREASURY), receiver=fund, amount=amount, kind="test_cash", memo="Test: other premiums")
    db.execute("INSERT INTO crash_fund_quarters (period, index_start, index_end, triggered, premiums, paid_out) VALUES (-1, 1, 1, false, %s, 0)"
               " ON CONFLICT (period) DO UPDATE SET premiums = crash_fund_quarters.premiums + EXCLUDED.premiums", (amount,))


def test_the_crash_fund_pays_cover_when_the_market_falls_fifteen_percent_in_a_quarter(db):
    from simulation import firm
    empire, team = firm_of(db, n_cash=5_000_000_000)
    asked = crashfund.ask_cover(db, team["risk_manager"], naira(10_000_000), OPEN)
    assert asked["waiting"]
    firm.decide(db, team["head"], asked["approval_id"], True, "", LATER)
    assert _one(db, "SELECT cover FROM crash_fund_members WHERE empire_id = %s", (empire["id"],))["cover"] == naira(10_000_000)
    with pytest.raises(Exception, match="half"):
        crashfund.ask_cover(db, team["head"], naira(10_000_000_000_000), OPEN)
    quarters.close_due_quarters(db, after_quarters(9))               # the first premium is paid; the starting level is noted
    fund = ledger.account_id(db, crashfund.FUND)
    assert ledger.balance(db, fund) == naira(10_000_000) * data.CRASH_PREMIUM_BPS // BPS
    # Another empire's premiums are in the pot too (so the fund can pay); the market then falls 20% over the quarter.
    seed_fund(db, naira(20_000_000))
    before = ledger.balance(db, empire["account_id"])
    db.execute("UPDATE market_instruments SET last_price = coalesce(last_price, reference_price) * 80 / 100,"
               " reference_price = coalesce(last_price, reference_price) * 80 / 100")
    quarters.close_due_quarters(db, after_quarters(10))
    q = _one(db, "SELECT * FROM crash_fund_quarters WHERE period = 10")
    assert q["triggered"] and q["paid_out"] == naira(10_000_000)
    assert _one(db, "SELECT paid_out FROM crash_fund_members WHERE empire_id = %s", (empire["id"],))["paid_out"] == naira(10_000_000)
    sound(db)
