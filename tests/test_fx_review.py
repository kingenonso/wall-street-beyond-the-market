"""The currency desk: what the independent review found, each fixed and tested."""

from __future__ import annotations

from datetime import timedelta

import psycopg
import pytest

from simulation import abroad, fx, ledger, swaps
from simulation import world_data as data
from simulation.money import BPS
from tests.test_fx import DAY, TRADING, _one, empire_head, opened, person, ring, sound


def _devaluation_due(db):
    """The window far below the market, and reserves under comfortable: by the published rules, a devaluation is coming."""
    cb = ledger.account_id(db, ledger.CENTRAL_BANK)
    world_abroad, _ = abroad.accounts(db)
    db.execute("ALTER TABLE fx_quarters DISABLE TRIGGER fx_quarters_permanent")
    db.execute("UPDATE fx_quarters SET official = official * 8 / 10")
    db.execute("ALTER TABLE fx_quarters ENABLE TRIGGER fx_quarters_permanent")
    keep = fx.imports_usd(db) * 2
    have = ledger.balance(db, cb, "USD")
    ledger.post(db, kind="fx_abroad", memo="test", legs=[ledger.Leg(cb, -(have - keep), "USD"), ledger.Leg(world_abroad, have - keep, "USD")])


def test_r1_a_bank_prices_a_forward_from_where_the_official_rate_is_heading(db):
    """Found by the review: a forward fixed at today's official rate paid out 24% on a devaluation anybody could see coming."""
    opened(db)
    _devaluation_due(db)
    assert fx.expected_official(db) == fx.current(db)["market"] > fx.official(db)
    player, _ = person(db, "ada", cash_naira=500_000_000)
    from tests.test_derivatives import ready
    ready(db, player)
    bank = _one(db, "SELECT id FROM companies WHERE sector = 'banking' AND status = 'trading' ORDER BY ticker LIMIT 1")
    got = swaps.propose(db, player, kind="fx", counterparty={"bank": str(bank["id"])}, side="pay_fixed", quarters=1, now=TRADING, notional=1_000_000)
    s = _one(db, "SELECT * FROM swaps WHERE id = %s", (got["swap_id"],))
    assert s["fixed_price"] > fx.expected_official(db)


def test_r1b_the_window_buys_back_its_dollars_no_dearer_than_it_sold_them(db):
    """Found by the review: buy at the window before a devaluation, sell back after, at the new rate."""
    opened(db)
    player, account = person(db, "ada", cash_naira=500_000_000)
    fx.window_ask(db, player, 1_000_000, TRADING)
    ring(db, DAY)
    paid = _one(db, "SELECT rate FROM fx_trades WHERE account_id = %s AND venue = 'window'", (account,))["rate"]
    db.execute("ALTER TABLE fx_quarters DISABLE TRIGGER fx_quarters_permanent")
    db.execute("UPDATE fx_quarters SET official = official * 13 / 10")          # devalued since
    db.execute("ALTER TABLE fx_quarters ENABLE TRIGGER fx_quarters_permanent")
    got = fx.window_sell(db, player, 1_000_000, TRADING + timedelta(days=1))
    assert got["rate"] <= paid
    sound(db)


@pytest.mark.world("eight")
def test_r2_an_empire_holding_window_dollars_cannot_open_a_bureau(db):
    """Found by the review: window dollars handed to households through a new bureau at the street's price."""
    from tests.test_careers import NOW9
    ring(db, NOW9.date() - timedelta(days=1))
    head, _, empire = empire_head(db)
    fx.window_ask(db, head, 2_000_000, NOW9, for_empire=True)
    ring(db, NOW9.date())
    with pytest.raises(fx.FxError, match="official window"):
        fx.open_bdc(db, head, "Round Trip Bureau", 0, 0, NOW9 + timedelta(days=1))


def test_r3_a_government_eurobond_short_at_its_end_is_repaid_once_and_marked_in_default(db):
    """Found by the review: a bond 5% short at maturity paid its face again the quarter after."""
    opened(db)
    player, account = person(db, "ada", cash_naira=500_000_000)
    fx.street_deal(db, player, "buy", "USD", 2_000_000, TRADING)
    eb = _one(db, "SELECT * FROM eurobonds WHERE issuer = 'government'")
    fx.eurobond_deal(db, player, eb["id"], "buy", 10, TRADING)
    db.execute("UPDATE eurobonds SET maturity_period = 1 WHERE id = %s", (eb["id"],))
    treasury = ledger.account_id(db, ledger.TREASURY)
    out = sum(h["units"] for h in fx._holders(db, eb["asset"]))
    per = eb["face"] * eb["coupon_bps"] // BPS // 4 + eb["face"]
    need = fx.to_naira(per * out, fx.official(db))
    park = ledger.create_account(db, kind="escrow", name="park", code="test:park")
    ledger.transfer(db, payer=treasury, receiver=park, amount=ledger.balance(db, treasury) - need * 95 // 100, kind="test", memo="park", period=1)
    before = ledger.balance(db, account, "USD")
    fx._pay_eurobonds(db, 1, TRADING)
    first = ledger.balance(db, account, "USD") - before
    ledger.transfer(db, payer=park, receiver=treasury, amount=ledger.balance(db, park), kind="test", memo="back", period=2)
    fx._pay_eurobonds(db, 2, TRADING)
    assert ledger.balance(db, account, "USD") - before == first <= 10 * per
    e = _one(db, "SELECT * FROM eurobonds WHERE id = %s", (eb["id"],))
    assert e["redeemed_period"] == 1 and e["defaulted"] and ledger.balance(db, account, eb["asset"]) == 0
    sound(db)


def test_r4_two_requests_at_the_same_moment_cannot_both_slip_past_the_limit(db, connect):
    """Found by the review: the limit was read without a lock."""
    opened(db)
    player, account = person(db, "ada", cash_naira=500_000_000)
    other = connect()
    other.execute("BEGIN")
    other.execute("SELECT id FROM ledger_accounts WHERE id = %s FOR UPDATE", (account,))
    db.execute("SET lock_timeout = '1s'")
    with pytest.raises(psycopg.errors.LockNotAvailable):
        fx.window_ask(db, player, 1_000_000, TRADING)                  # it waits its turn for the account
    other.execute("ROLLBACK")
    db.execute("SET lock_timeout = 0")
    fx.window_ask(db, player, 1_000_000, TRADING)


def test_r5_a_bond_in_default_is_priced_from_what_it_still_pays_and_a_part_repayment_reaches_its_holders(db):
    """Found by the review: a defaulted bond was fixed at 30% of its face while it kept paying in full."""
    opened(db)
    eb = _one(db, "SELECT * FROM eurobonds WHERE issuer = 'company' ORDER BY id LIMIT 1")
    sound_price = fx.fair_price(db, eb, 1)
    hurt = fx.fair_price(db, {**eb, "defaulted": True}, 1)
    assert eb["face"] * 2 // 10 <= hurt < sound_price
    assert hurt != eb["face"] * 3 // 10


def test_r6_a_bond_costs_more_as_its_interest_builds_up_so_buying_just_before_a_payment_gains_nothing(db):
    """Found by the review: the price was the same all quarter while the whole coupon went to whoever held it at the close."""
    opened(db)
    eb = _one(db, "SELECT * FROM eurobonds WHERE issuer = 'government'")
    early, late = fx.fair_price(db, eb, 1, 0.0), fx.fair_price(db, eb, 1, 0.95)
    coupon = eb["face"] * eb["coupon_bps"] // BPS // 4
    assert late - early >= coupon * 85 // 100
    after = fx.fair_price(db, eb, 2, 0.0)                               # the next quarter, once the coupon is paid
    assert abs(after - early) < coupon // 2


def test_r7_a_companys_hedge_is_renewed_for_the_quarter_after_its_last(db):
    """Found by the review: the renewal saw the expiring hedge as still active, so one quarter in five went unhedged."""
    opened(db)
    c = _one(db, "SELECT c.* FROM companies c JOIN company_debts d ON d.company_id = c.id WHERE d.currency = 'USD' ORDER BY c.ticker LIMIT 1")
    hedge = _one(db, "SELECT * FROM swaps WHERE kind = 'fx' AND fixed_payer = %s", (c["account_id"],))
    fx._hedge(db, c, hedge["last_period"] + 1, TRADING)
    assert _one(db, "SELECT count(*) AS n FROM swaps WHERE kind = 'fx' AND fixed_payer = %s", (c["account_id"],))["n"] == 2


def test_r8_a_bureaus_refusals_and_the_window_line_give_away_nobodys_money(db):
    """Found by the review: failed deals told anybody a bureau's balances; the line showed the sum others had asked for."""
    opened(db)
    db.execute("INSERT INTO bdcs (empire_id, name, buy_bps, sell_bps, licensed_at) SELECT id, 'Test Bureau', 10, 10, now() FROM empires ORDER BY id LIMIT 1")
    bdc = _one(db, "SELECT id FROM bdcs")
    player, _ = person(db, "ada", cash_naira=500_000_000)
    with pytest.raises(fx.FxError) as refused:
        fx.bdc_deal(db, player, bdc["id"], "buy", data.FX_BDC_MOST_DEAL_CENTS, TRADING)
    assert "dollars" not in str(refused.value) and "naira" not in str(refused.value)
    bola, _ = person(db, "bola", cash_naira=500_000_000)
    fx.window_ask(db, bola, 3_456_700, TRADING)
    got = fx.window_ask(db, player, 1_000_000, TRADING)
    assert got["place"] == 2 and "ahead" not in got
    assert "3456700" not in repr(fx.page(db, player, TRADING))
