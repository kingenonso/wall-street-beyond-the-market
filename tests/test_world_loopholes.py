"""Part 4b: attempts to make money from foreign markets that the rules must not allow."""

from __future__ import annotations

import json
from datetime import timedelta
from decimal import Decimal

import pytest

from simulation import fx, ledger, world
from simulation import world_data as data
from simulation.money import BPS
from tests.test_fx import DAY, TRADING, _one, empire_head, person, ring
from tests.test_world import NIGHT, _arm, _co, dollars, opened, opened8, sound


def test_1_nobody_deals_while_an_exchange_is_closed_not_even_a_minute_after_its_close(db):
    opened(db)
    player, _ = person(db, "ada", cash_naira=800_000_000)
    dollars(db, player, 20_000_000)
    ex = world._exchange(db, "THX")
    _, end = world.session(ex, world.local_day(ex, TRADING))
    with pytest.raises(world.WorldError, match="closed"):
        world.deal(db, player, "SLTM", "buy", 10, end)
    with pytest.raises(world.WorldError, match="closed"):
        world.deal(db, player, "SLTM", "buy", 10, end + timedelta(minutes=1))


def test_2_buying_and_selling_straight_back_always_loses(db):
    opened(db)
    player, account = person(db, "ada", cash_naira=1_600_000_000)
    dollars(db, player, 100_000_000)
    start = ledger.balance(db, account, "USD")
    for ticker in ("OSTM", "TSRN", "CPFM"):
        co = _co(db, ticker)
        n = int(Decimal(30_000_000) / world.price_of(db, co, TRADING))          # about $300,000's worth, to push the price
        n = min(n, co["shares"] * data.WORLD_DAY_MOST_SHARES_BPS // BPS // 2)
        world.deal(db, player, ticker, "buy", n, TRADING)
        world.deal(db, player, ticker, "sell", n, TRADING)
    assert ledger.balance(db, account, "USD") < start
    sound(db)


def test_3_buying_before_a_dividend_and_selling_after_does_not_pay(db):
    opened(db)
    player, account = person(db, "ada", cash_naira=800_000_000)
    dollars(db, player, 30_000_000)
    co = _co(db, "PRHF")
    path = world._Path(db)
    world.deal(db, player, "PRHF", "buy", 1_000, TRADING)
    spent = 30_000_000 - ledger.balance(db, account, "USD")
    world._pay_dividend(db, co, Decimal(40), 0, TRADING, path)
    got = world.deal(db, player, "PRHF", "sell", 1_000, TRADING)
    assert ledger.balance(db, account, "USD") - (30_000_000 - spent) < spent and got["amount"] + 1_000 * 40 * 85 // 100 < spent


def test_4_dollars_from_the_official_window_stay_kept_through_a_foreign_share(db):
    opened(db)
    player, account = person(db, "ada", cash_naira=500_000_000)
    fx.window_ask(db, player, 5_000_000, TRADING)
    ring(db, DAY)
    t = TRADING + timedelta(days=1)
    have = ledger.balance(db, account, "USD")
    assert have > 0
    co = _co(db, "TSRN")
    n = int(Decimal(have) / world.price_of(db, co, t) / 2)
    world.deal(db, player, "TSRN", "buy", n, t)
    world.deal(db, player, "TSRN", "sell", n, t)
    with pytest.raises(fx.FxError, match="official window"):
        fx.street_deal(db, player, "sell", "USD", ledger.balance(db, account, "USD"), t)


def test_5_no_deal_over_two_million_dollars_and_no_more_than_a_tenth_of_a_percent_of_a_company_a_day(db):
    opened(db)
    player, _ = person(db, "ada", cash_naira=3_000_000_000)
    dollars(db, player, 100_000_000)
    co = _co(db, "MSQR")
    big = int(Decimal(data.WORLD_MOST_DEAL_CENTS) / world.price_of(db, co, TRADING)) + 10
    with pytest.raises(world.WorldError, match="at most"):
        world.deal(db, player, "MSQR", "buy", big, TRADING)
    small = _co(db, "HNSF")
    cap = small["shares"] * data.WORLD_DAY_MOST_SHARES_BPS // BPS
    each = min(cap // 3, int(Decimal(30_000_000) / world.price_of(db, small, TRADING)))
    bought = 0
    with pytest.raises(world.WorldError):
        for _ in range(200):
            world.deal(db, player, "HNSF", "buy", each, TRADING)
            bought += each
    assert bought <= cap


@pytest.mark.world("eight")
def test_6_a_dealer_cannot_make_foreign_etf_units_against_a_basket(db):
    from simulation import etfs
    t9 = opened8(db)
    head, _, empire = empire_head(db)
    db.execute("INSERT INTO etf_dealers (empire_id, approved_at) VALUES (%s, %s)", (empire["id"] if isinstance(empire, dict) else empire, t9))
    with pytest.raises(etfs.EtfError, match="cash only"):
        etfs.create(db, head, "HUDX", data.ETF_CREATION_UNITS, "basket", t9)


@pytest.mark.world("eight")
def test_7_only_the_head_banker_or_asset_manager_deals_for_an_empire(db):
    from simulation import empires
    from tests.test_builds import pro
    t9 = opened8(db)
    head, _, empire = empire_head(db)
    emp = empires._empire(db, empire["id"] if isinstance(empire, dict) else empire)
    fx.street_deal(db, head, "buy", "USD", 10_000_000, t9, for_empire=True)
    world.deal(db, head, "TSRN", "buy", 10, t9, for_empire=True)
    outsider, _ = pro(db, "accountant", "outsider")
    with pytest.raises(world.WorldError):
        world.deal(db, outsider, "TSRN", "sell", 10, t9, for_empire=True)
    assert ledger.balance(db, emp["account_id"], _co(db, "TSRN")["asset"]) == 10


@pytest.mark.world("eight")
def test_8_a_parents_stake_is_never_bought_to_thirty_percent_nor_while_it_stays_nor_by_anyone_but_a_head(db):
    from tests.test_builds import pro
    t9 = opened8(db)
    head, _, _ = empire_head(db)
    arm = _arm(db)
    with pytest.raises(world.WorldError, match="not selling"):
        world.buy_stake(db, head, "AHP", 1_000, t9)
    db.execute("UPDATE world_arms SET status = 'leaving', deadline_period = 10 WHERE company_id = %s", (arm["company_id"],))
    issued = ledger.amount_in_existence(db, arm["share_asset"])
    with pytest.raises(world.WorldError, match="30%"):
        world.buy_stake(db, head, "AHP", issued * 3_000 // BPS, t9)
    other, _ = pro(db, "investment_banker", "notahead")
    with pytest.raises(world.WorldError, match="head"):
        world.buy_stake(db, other, "AHP", 1_000, t9)
    for bad in (0, -5, 1.5, True):
        with pytest.raises(world.WorldError):
            world.buy_stake(db, head, "AHP", bad, t9)


def test_9_odd_requests_are_refused(db):
    opened(db)
    player, _ = person(db, "ada", cash_naira=800_000_000)
    dollars(db, player, 10_000_000)
    for shares in (0, -1, 2.5, True, "10", 10 ** 10):
        with pytest.raises(world.WorldError):
            world.deal(db, player, "TSRN", "buy", shares, TRADING)
    for ticker in ("ZZZZ", "TSR'; --", "", "SHR-TSRN"):
        with pytest.raises(world.WorldError):
            world.deal(db, player, ticker, "buy", 1, TRADING)
    with pytest.raises(world.WorldError):
        world.deal(db, player, "TSRN", "short", 1, TRADING)
    with pytest.raises(world.WorldError, match="hold"):
        world.deal(db, player, "TSRN", "sell", 1, TRADING)
    with pytest.raises(world.WorldError, match="costs"):
        world.deal(db, player, "VCLX", "buy", 10, TRADING)          # euros it does not have


def test_10_a_player_sees_only_their_own_holdings_and_never_a_secret(db):
    opened(db)
    ada, _ = person(db, "ada", cash_naira=800_000_000)
    bola, _ = person(db, "bola", cash_naira=800_000_000)
    dollars(db, ada, 20_000_000)
    world.deal(db, ada, "TSRN", "buy", 100, TRADING)
    seen = world.page(db, bola, TRADING)
    assert seen["mine"]["holdings"] == [] and seen["empire"] is None
    text = json.dumps(seen, default=str)
    seed = _one(db, "SELECT fortune_seed FROM world_state")["fortune_seed"]
    assert seed not in text and "fortune" not in text and "base_at" not in text


def test_11_nothing_is_dealt_in_the_moments_after_a_quarter_ends_before_it_is_closed(db):
    from tests.conftest import after_quarters
    opened(db)
    player, _ = person(db, "ada", cash_naira=800_000_000)
    dollars(db, player, 10_000_000)
    end = after_quarters(1)
    with pytest.raises(world.WorldError, match="books"):
        world.deal(db, player, "TSRN", "buy", 1, end + timedelta(minutes=1))


@pytest.mark.world("eight")
def test_12_a_leaving_parents_shares_are_never_sold_below_the_market(db):
    """Found by these tests: at 10% below the market, an empire could buy the stake and sell it straight back on the exchange."""
    t9 = opened8(db)
    head, _, _ = empire_head(db)
    arm = _arm(db)
    db.execute("UPDATE world_arms SET status = 'leaving', deadline_period = 10 WHERE company_id = %s", (arm["company_id"],))
    got = world.buy_stake(db, head, "AHP", 1_000, t9)
    assert got["price"] >= world.market_price(db, arm["company_id"])


def test_13_a_quarters_news_is_mostly_in_the_price_at_once(db):
    """Found by these tests: with half of the news priced at once, the rest came in day after day for anyone to collect."""
    opened(db)
    co = _co(db, "QLNT")
    path = world._Path(db)
    db.execute("UPDATE world_quotes SET base = %s, base_at = %s, impact_bps = 0 WHERE company_id = %s", (co["fair"], NIGHT, co["id"]))
    p0 = world.price_of(db, co, NIGHT, path=path, with_impact=False)
    db.execute("UPDATE world_companies SET fair = fair * 1.2 WHERE id = %s", (co["id"],))
    co = _co(db, "QLNT")
    world._rebase(db, co, NIGHT, 1.2 ** (data.WORLD_NEWS_PRICED_BPS / BPS), path)
    p1 = world.price_of(db, co, NIGHT, path=path, with_impact=False)
    left = float(co["fair"]) / float(p1) - 1
    # What is left to come is small against what a round trip costs, day by day.
    assert left * data.WORLD_FAIR_PULL_BPS / BPS < 2 * data.WORLD_SPREAD_BPS / BPS
    assert float(p1 / p0) > 1.14
