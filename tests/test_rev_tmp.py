"""Independent review of Part 4b (foreign markets): tests that show bugs and loopholes.

Each test asserts what SHOULD hold; a failing test is a finding.
"""

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
    want = issued * 2_500 // BPS                                          # a quarter of the company
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
    player, _ = person(db, "ada", cash_naira=1_600_000_000)
    dollars(db, player, 50_000_000)
    dollars(db, player, 50_000_000, "GBP")
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
# 6. The overnight pull towards "fair" (shown on the company page) is a known move bigger than the round trip's cost.
# ---------------------------------------------------------------------------

def test_r6_the_known_part_of_the_next_open_does_not_pay_more_than_a_round_trip_costs(db):
    opened(db)
    path = world._Path(db)
    cost = 2 * data.WORLD_SPREAD_BPS / BPS
    picked, all_r, known = [], [], []
    for ex in world.exchanges(db):
        cos = [dict(c, currency=ex["currency"]) for c in _rows(db, "SELECT * FROM world_companies WHERE exchange = %s", (ex["code"],))]
        day = world.local_day(ex, ex["opened_at"]) + timedelta(days=1)
        for _ in range(60):
            start, end = world.session(ex, day)
            nstart, _ = world.session(ex, day + timedelta(days=1))
            buy_at, sell_at = end - timedelta(minutes=1), nstart + timedelta(minutes=1)
            world.advance(db, buy_at)
            before = {c["id"]: world.price_of(db, c, buy_at, path=path, ex=ex) for c in cos}
            world.advance(db, sell_at)
            for c in cos:
                closed = world.last_close(db, c["id"])                     # the price at the close (public)
                after = world.price_of(db, c, sell_at, path=path, ex=ex)
                pull = (math.log(float(c["fair"])) - math.log(float(closed))) * data.WORLD_FAIR_PULL_BPS / BPS
                r = float(after) * (1 - data.WORLD_SPREAD_BPS / BPS) / (float(before[c["id"]]) * (1 + data.WORLD_SPREAD_BPS / BPS)) - 1
                all_r.append(r)
                if pull > cost:                                             # known before the close, from public figures
                    picked.append(r)
                    known.append(pull)
            day += timedelta(days=1)
    mean = sum(picked) / max(len(picked), 1)
    print(f"\n{len(picked)} of {len(all_r)} company-nights had a known pull above the round trip's cost;"
          f" their mean known pull {sum(known) / max(len(known), 1) * 100:.2f}%, mean realised return after spreads {mean * 100:.3f}%"
          f" (all nights: {sum(all_r) / len(all_r) * 100:.3f}%)")
    assert len(picked) == 0 or mean <= 0


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
