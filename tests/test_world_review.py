"""Part 4b: the independent review's nine findings, each fixed; each test shows the fix holds."""

from __future__ import annotations

import json
import math
from datetime import timedelta
from decimal import Decimal

import pytest

from simulation import exchange, fx, ledger, world
from simulation import world_data as data
from simulation.money import BPS
from tests.test_fx import TRADING, _one, _rows, empire_head, person
from tests.test_world import NIGHT, _arm, _co, dollars, opened, opened8, sound


def _give_shares(db, account, asset, n):
    public = ledger.account_id(db, ledger.INVESTORS_PUBLIC)
    ledger.transfer(db, payer=public, receiver=account, amount=n, asset=asset, kind="test", memo="bought earlier")


# ---------------------------------------------------------------------------
# 1. A leaving parent's stake is sold at the share's LAST TRADE price, which one share traded between two players sets.
# ---------------------------------------------------------------------------

@pytest.mark.world("eight")
def test_r1_a_one_share_trade_sets_the_price_a_leaving_parent_sells_its_stake_at(db):
    t9 = opened8(db)
    head, _, _ = empire_head(db)
    arm = _arm(db)
    db.execute("UPDATE world_arms SET status = 'leaving', deadline_period = 10 WHERE company_id = %s", (arm["company_id"],))
    fair_price = world.market_price(db, arm["company_id"])               # the reference price: no trade yet today
    # Two players (or a player and a friend) cross ONE share at the lowest price the exchange allows today.
    seller, s_acct = person(db, "seller", cash_naira=10_000_000)
    buyer, b_acct = person(db, "buyer", cash_naira=10_000_000)
    _give_shares(db, s_acct, arm["share_asset"], 1)
    low, _ = exchange.price_limits(fair_price)
    exchange.place_order(db, account=b_acct, ticker="AHP", side="buy", kind="limit", quantity=1, limit_price=low, now=t9)
    exchange.place_order(db, account=s_acct, ticker="AHP", side="sell", kind="limit", quantity=1, limit_price=low, now=t9)
    assert world.market_price(db, arm["company_id"]) == low               # one share moved "the market price" 10%
    issued = ledger.amount_in_existence(db, arm["share_asset"])
    want = issued * 100 // BPS                                            # 1% of the company
    got = world.buy_stake(db, head, "AHP", want, t9)
    # What SHOULD hold: never below the market (test 12's own rule). It is bought ~10% below the reference.
    assert got["price"] >= fair_price, (got["price"], fair_price, f"saved ₦{(fair_price - got['price']) * want / 100:,.0f}")


# ---------------------------------------------------------------------------
# 2. Which empires bought pieces of a parent's stake is broadcast to every player.
# ---------------------------------------------------------------------------

@pytest.mark.world("eight")
def test_r2_the_empires_that_bought_a_parents_stake_are_not_named_to_everybody(db):
    t9 = opened8(db)
    head, _, empire = empire_head(db)
    emp = _one(db, "SELECT * FROM empires WHERE head_player_id = %s", (head,))
    arm = _arm(db)
    db.execute("UPDATE world_arms SET status = 'leaving', deadline_period = 9 WHERE company_id = %s", (arm["company_id"],))
    issued = ledger.amount_in_existence(db, arm["share_asset"])
    world.buy_stake(db, head, "AHP", issued * 100 // BPS, t9)
    world._deadlines(db, 9, t9)
    public = _rows(db, "SELECT headline, words FROM fx_alerts WHERE account_id IS NULL AND kind = 'world_sold'")
    assert public, "the exit was announced"
    assert not any(emp["name"] in (a["headline"] + a["words"]) for a in public), public
    # What one empire holds is its own business (marketview.shareholders); the news names it too.
    stories = _rows(db, "SELECT * FROM news_items WHERE kind = 'world_sold'") if _one(
        db, "SELECT to_regclass('news_items') IS NOT NULL AS ok")["ok"] else []
    assert not any(emp["name"] in json.dumps(s, default=str) for s in stories)


# ---------------------------------------------------------------------------
# 3. The buy price is meant to be rounded UP (in the brokers' favour) but Decimal // truncates, so it is rounded DOWN.
# ---------------------------------------------------------------------------

def test_r3_a_buy_is_never_cheaper_than_the_price_plus_the_spread(db):
    opened(db)
    player, _ = person(db, "ada", cash_naira=800_000_000)
    dollars(db, player, 10_000_000)
    dollars(db, player, 10_000_000, "GBP")
    bad = []
    for ticker in ("MRTA", "HRWB", "SLTM", "TSRN", "PRHF", "LDGR"):
        co = _co(db, ticker)
        mid = world.price_of(db, co, TRADING)
        got = world.deal(db, player, ticker, "buy", 1, TRADING)
        # One share moves the price by nothing to speak of: the buyer should pay at least mid x (1 + 0.15%), rounded up.
        if got["price"] * BPS < mid * (BPS + data.WORLD_SPREAD_BPS):
            bad.append((ticker, float(mid), got["price"], float(mid * (BPS + data.WORLD_SPREAD_BPS) / BPS)))
    assert bad == []


def test_r3b_decimal_floor_division_truncates():
    x = Decimal("2.5") * BPS
    assert -(-x // BPS) == 2                       # what world.deal computes: the intended ceiling would be 3
    assert -(-int(25) // 10) == 3                  # with ints the same idiom does round up


# ---------------------------------------------------------------------------
# 4. Interest rates and growth abroad barely move the pound and the euro: two /BPS too many.
# ---------------------------------------------------------------------------

def _economy_rows(db, period, uk_rate_change):
    db.execute("ALTER TABLE world_economies DISABLE TRIGGER world_economies_permanent")
    db.execute("DELETE FROM world_economies WHERE period = %s", (period,))
    db.execute("INSERT INTO world_economies (country, period, growth_bps, inflation_bps, rate_bps, words, at)"
               " SELECT country, %s, growth_bps, inflation_bps, rate_bps + CASE WHEN country = 'UK' THEN %s ELSE 0 END, words, at"
               " FROM world_economies WHERE period = %s", (period, uk_rate_change, period - 1))
    db.execute("ALTER TABLE world_economies ENABLE TRIGGER world_economies_permanent")


def test_r4_a_point_on_britains_rate_against_americas_lifts_the_pound_about_four_percent(db):
    opened(db)
    p0 = world._closed_period(db)
    _economy_rows(db, p0 + 1, 0)
    same = world.cross_next(db, p0 + 1, 1.25, 1.08)
    _economy_rows(db, p0 + 1, 100)
    higher = world.cross_next(db, p0 + 1, 1.25, 1.08)
    lift = higher[0] / same[0] - 1
    # world_data: "a pound's interest rate rising a point against the dollar's lifts it 4%"
    assert lift > 0.03, f"the pound rose only {lift * 100:.3f}%"


# ---------------------------------------------------------------------------
# 5. Dearer oil barely lifts inflation abroad: a stray /10.
# ---------------------------------------------------------------------------

def test_r5_a_tenth_dearer_oil_adds_about_half_a_point_to_inflation_abroad(db, monkeypatch):
    opened(db)
    p = world._closed_period(db) + 1
    seed = world._seed(db)
    out = {}
    for oil in (0, 1_000):                          # oil 10% dearer than the quarter before
        monkeypatch.setattr(world, "_oil_change_bps", lambda conn, period, oil=oil: oil)
        with db.transaction(force_rollback=True):
            out[oil] = world._economies_close(db, p, NIGHT, seed)["US"]["inflation"]
    added = out[1_000] - out[0]
    # world_data: WORLD_INFLATION_OIL_BPS = 500  "...and with dearer oil (a 10% rise adds half a point)"
    assert added >= 40, f"10% dearer oil added {added} bps to inflation"


# ---------------------------------------------------------------------------
# 7. A parent leaving because the naira fell is announced as "₦0.00 of its dividends wait for dollars".
# ---------------------------------------------------------------------------

def test_r7_no_alert_about_nothing_waiting_for_dollars(db, monkeypatch):
    opened(db)
    monkeypatch.setattr(data, "WORLD_PARENT_LEAVE_CHANCE_BPS", 0)
    p = world._closed_period(db)
    db.execute("INSERT INTO fx_quarters (period, official, market, regime, reserves, cover_bps, gbp_usd, eur_usd, sold, backlog, event, words, at)"
               " SELECT %s, official, market * 2, regime, reserves, cover_bps, gbp_usd, eur_usd, sold, backlog, event, words, at"
               " FROM fx_quarters WHERE period = %s", (p + 8, p))
    for a in _rows(db, "SELECT * FROM world_arms"):
        assert world.trapped(db, a) == 0
    world._decide(db, p + 8, NIGHT, world._seed(db))
    nothing = _rows(db, "SELECT headline FROM fx_alerts WHERE kind = 'world_trapped' AND headline LIKE '₦0.00 %%'")
    assert nothing == []


# ---------------------------------------------------------------------------
# 8. Redeeming units of a foreign ETF for cash: the fund sells a slice of its foreign shares at 0.6% below their price, but
#    raise_cash only sells 0.2% more than needed, so the dealer is paid short (its units are already gone).
# ---------------------------------------------------------------------------

@pytest.mark.world("eight")
def test_r8_a_dealer_redeeming_foreign_etf_units_for_cash_is_paid_in_full(db):
    from simulation import etfs
    t9 = opened8(db)
    head, _, empire = empire_head(db)
    eid = empire["id"] if isinstance(empire, dict) else empire
    db.execute("INSERT INTO etf_dealers (empire_id, approved_at) VALUES (%s, %s)", (eid, t9))
    e = etfs.by_code(db, "HUDX")
    units = data.ETF_CREATION_UNITS * 200                      # about ₦200 million
    etfs.create(db, head, "HUDX", units, "cash", t9)
    got = etfs.redeem(db, head, "HUDX", units, "cash", t9)
    owed = units * got["nav"] - got["fee"]
    print(f"\nowed ₦{owed / 100:,.2f}, paid ₦{got['paid'] / 100:,.2f}, short ₦{(owed - got['paid']) / 100:,.2f}")
    assert got["paid"] == owed
    sound(db)


# ---------------------------------------------------------------------------
# 9. Units made (and unmade) by households and the market makers against cash pay a 0.1% fee, but buying (selling) the
#    foreign shares costs the fund 0.6%: every such flow takes value from everybody already holding the ETF.
# ---------------------------------------------------------------------------

def test_r9_units_made_by_households_do_not_take_value_from_existing_holders(db, monkeypatch):
    from simulation import etfs
    opened(db)
    monkeypatch.setattr(fx, "_move_street", lambda conn, cents: None)      # leave the naira where it is, to see the fund alone
    e = etfs.by_code(db, "THMX")
    households = ledger.account_id(db, etfs.HOUSEHOLDS)
    before = etfs.nav_now(db, e, NIGHT)
    out = etfs.units_out(db, e)
    etfs._create_cash(db, e, households, out, NIGHT, 1, fee_bps=etfs.DEALING_COST_BPS)   # as world._households does
    after = etfs.nav_now(db, etfs.by_code(db, "THMX"), NIGHT)
    print(f"\nNAV {before} -> {after} kobo ({(after - before) * BPS / before:.1f} bps) after households doubled the fund")
    assert after >= before - 1


# ---------------------------------------------------------------------------
# 10. Dealing for an empire abroad skips every guard the Broad Street desk has: the member's trading limit for the quarter,
#     the Risk Manager's freeze, and (in an empire the computer runs) fair dealing. A member of a computer-run empire can
#     spend its money without limit, and front-run it for themselves.
# ---------------------------------------------------------------------------

@pytest.mark.world("eight")
def test_r10_a_member_of_a_computer_run_empire_cannot_deal_abroad_past_their_limit_or_while_frozen(db):
    from simulation import empires
    from tests.test_builds import pro
    from tests.test_empires import computer_empire
    t9 = opened8(db)
    emp = computer_empire(db)
    ib, ib_acct = pro(db, "investment_banker", "frontrunner", cash_naira=1_000_000_000)
    assert empires.apply(db, ib, emp["id"], t9)["status"] == "accepted"
    seat = empires.seat_of(db, ib)
    limit = empires.trade_limit(db, seat, t9)
    # Frozen by the Risk Manager: no currency and no foreign shares for the empire.
    db.execute("UPDATE empire_seats SET frozen = true WHERE player_id = %s", (ib,))
    with pytest.raises(fx.FxError, match="frozen"):
        fx.street_deal(db, ib, "buy", "GBP", 5_000_000, t9, for_empire=True)
    db.execute("UPDATE empire_seats SET frozen = false WHERE player_id = %s", (ib,))
    # Unfrozen: the member's limit for the quarter stops the empire's spending.
    spent = 0
    with pytest.raises(fx.FxError, match="limit"):
        for _ in range(200):
            got = fx.street_deal(db, ib, "buy", "GBP", 5_000_000, t9, for_empire=True)
            spent += got["naira"]
    assert spent <= limit
    # And nobody sells their own shares into the empire's buying: the member bought for themselves, the empire buys, the
    # member's sale is refused.
    fx.street_deal(db, ib, "buy", "GBP", 2_000_000, t9)
    world.deal(db, ib, "ELSM", "buy", 10, t9)
    world.deal(db, ib, "ELSM", "buy", 5, t9, for_empire=True) if ledger.balance(db, emp["account_id"], "GBP") else None
    if _one(db, "SELECT 1 AS x FROM world_trades WHERE account_id = %s", (emp["account_id"],)):
        with pytest.raises(world.WorldError, match="own empire"):
            world.deal(db, ib, "ELSM", "sell", 10, t9)
    sound(db)
