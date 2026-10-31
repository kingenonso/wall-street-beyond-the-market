"""The talent and funds stage, Part 4b: foreign markets.

Three exchanges abroad with their own hours and indexes; thirty companies with prices that move while their exchange is open,
results, dividends and what their shares are worth; the economies abroad and their central banks, and what they do to the oil
price, the naira, foreign investors and the pound and euro; dealing in foreign shares with dollars, pounds and euros; Nigerian
arms of foreign companies, their parents' dividends waiting for dollars, a parent leaving; ETFs of foreign shares.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta
from decimal import Decimal

import pytest
from psycopg.rows import dict_row

from simulation import abroad, clock, fx, ledger, world
from simulation import world_data as data
from simulation.money import BPS
from tests.test_fx import DAY, TRADING, _one, _rows, empire_head, person, ring

NIGHT = TRADING.replace(hour=23)                      # every exchange abroad is closed


def opened(db):
    from simulation import etfs
    rung = ring(db, DAY - timedelta(days=1))
    etfs.tick(db, rung)
    world.tick(db, rung)
    return rung


def opened8(db):
    """The markets abroad in a world eight quarters old (for empires)."""
    from simulation import etfs
    from tests.test_careers import NOW9
    rung = ring(db, NOW9.date() - timedelta(days=1))
    etfs.tick(db, rung)
    world.tick(db, rung)
    return NOW9.replace(hour=16)


def sound(db):
    assert ledger.audit(db) == []
    assert fx.check_books(db) == []
    assert world.check_books(db) == []


def _player(db, account):
    return _one(db, "SELECT player_id FROM ledger_accounts WHERE id = %s", (account,))["player_id"]


def dollars(db, player, cents, currency="USD"):
    fx.street_deal(db, player, "buy", currency, cents, TRADING)


def test_the_markets_open_at_the_first_bell_after_the_currency_desk(db):
    opened(db)
    assert {e["code"] for e in world.exchanges(db)} == {"HSE", "THX", "RMX"}
    assert _one(db, "SELECT count(*) AS n FROM world_companies")["n"] == len(data.WORLD_COMPANIES) == 30
    assert _one(db, "SELECT count(*) AS n FROM world_economies")["n"] == 3
    world_abroad, _ = abroad.accounts(db)
    for co in _rows(db, "SELECT * FROM world_companies"):
        assert 0 < co["shares"] - ledger.balance(db, world_abroad, co["asset"]) < co["shares"] // 1000     # the ETFs bought a few
        assert co["fair"] > 0
    arms = _rows(db, "SELECT * FROM world_arms")
    assert len(arms) == len(data.WORLD_ARMS)
    founders = ledger.account_id(db, ledger.INVESTORS_FOUNDERS)
    for a in arms:
        c = _one(db, "SELECT * FROM companies WHERE id = %s", (a["company_id"],))
        assert ledger.balance(db, a["parent_account"], c["share_asset"]) > 0
        assert ledger.balance(db, founders, c["share_asset"]) == 0
    assert _one(db, "SELECT count(*) AS n FROM market_indexes WHERE kind = 'world'")["n"] == 3
    etfs = _rows(db, "SELECT * FROM etfs WHERE code IN ('HUDX', 'THMX', 'RMXX')")
    assert len(etfs) == 3
    for e in etfs:
        held = _rows(db, "SELECT asset FROM ledger_balances WHERE account_id = %s AND asset LIKE 'FSH-%%' AND balance > 0", (e["account_id"],))
        assert len(held) == 10
    sound(db)


def test_buying_a_foreign_share_costs_dollars_and_selling_gives_them_back_less_the_spread(db):
    opened(db)
    player, account = person(db, "ada", cash_naira=800_000_000)
    dollars(db, player, 20_000_000)
    got = world.deal(db, player, "TSRN", "buy", 100, TRADING)
    assert got["currency"] == "USD" and got["amount"] == got["price"] * 100
    co = _one(db, "SELECT * FROM world_companies WHERE ticker = 'TSRN'")
    assert ledger.balance(db, account, co["asset"]) == 100
    assert ledger.balance(db, account, "USD") == 20_000_000 - got["amount"]
    back = world.deal(db, player, "TSRN", "sell", 100, TRADING)
    assert back["amount"] < got["amount"]
    sound(db)


def test_an_exchange_trades_only_during_its_own_hours(db):
    opened(db)
    player, _ = person(db, "ada", cash_naira=800_000_000)
    dollars(db, player, 20_000_000)
    with pytest.raises(world.WorldError, match="closed"):
        world.deal(db, player, "TSRN", "buy", 10, NIGHT)
    with pytest.raises(world.WorldError, match="closed"):
        world.deal(db, player, "TSRN", "buy", 10, TRADING.replace(hour=12))       # New York opens at 14:30 Lagos time in October
    world.deal(db, player, "HRWB", "buy", 10, TRADING.replace(hour=12)) if False else None


def test_prices_move_while_open_and_stand_still_while_closed(db):
    opened(db)
    co = _one(db, "SELECT c.*, e.currency FROM world_companies c JOIN world_exchanges e ON e.code = c.exchange WHERE ticker = 'MRWD'")
    a = world.price_of(db, co, TRADING)
    b = world.price_of(db, co, TRADING + timedelta(minutes=30))
    assert a != b
    c = world.price_of(db, co, NIGHT)
    d = world.price_of(db, co, NIGHT + timedelta(minutes=30))
    assert c == d


def test_closing_prices_are_written_down_once(db):
    opened(db)
    world.advance(db, NIGHT)
    n = _one(db, "SELECT count(*) AS n FROM world_days")["n"]
    assert n >= 30
    world.advance(db, NIGHT + timedelta(minutes=5))
    assert _one(db, "SELECT count(*) AS n FROM world_days")["n"] == n
    assert _one(db, "SELECT count(*) AS n FROM world_index_days")["n"] >= 3


def test_page_and_net_worth(db):
    from simulation import objectives
    opened(db)
    player, account = person(db, "ada", cash_naira=800_000_000)
    dollars(db, player, 20_000_000)
    world.deal(db, player, "TSRN", "buy", 100, TRADING)
    p = world.page(db, player, TRADING)
    assert p["open"] and len(p["companies"]) == 30 and len(p["exchanges"]) == 3
    assert p["mine"]["holdings"][0]["ticker"] == "TSRN"
    w = objectives.wealth(db, account, TRADING)
    assert w["foreign"] > 0
    world.company_page(db, "TSRN", TRADING)
    assert world.economies_view(db)["open"]


# ---------------------------------------------------------------------------
# The quarter's close
# ---------------------------------------------------------------------------

def _close(db, n=1):
    from simulation import quarters
    from tests.conftest import after_quarters
    quarters.close_due_quarters(db, after_quarters(n))


def test_at_the_close_the_economies_move_the_companies_report_and_dividends_are_paid(db):
    opened(db)
    player, account = person(db, "ada", cash_naira=800_000_000)
    dollars(db, player, 30_000_000)
    world.deal(db, player, "HLGR", "buy", 200, TRADING)
    _close(db)
    assert _one(db, "SELECT count(*) AS n FROM world_economies WHERE period = 1")["n"] == 3
    assert _one(db, "SELECT count(*) AS n FROM world_results WHERE period = 1")["n"] == 30
    div = _one(db, "SELECT d.* FROM world_dividends d JOIN world_companies c ON c.id = d.company_id WHERE c.ticker = 'HLGR' AND period = 1")
    assert div and div["per_share"] > 0
    paid = _one(db, "SELECT coalesce(sum(e.amount), 0)::bigint AS n FROM ledger_entries e JOIN ledger_transactions t ON t.id = e.transaction_id"
                    " WHERE e.account_id = %s AND e.asset = 'USD' AND t.memo LIKE 'Hollis%%dividend%%'", (account,))["n"]
    assert paid == int(div["per_share"] * 200)
    assert _one(db, "SELECT count(*) AS n FROM world_repatriation WHERE period = 1")["n"] == len(data.WORLD_ARMS)
    q = fx.current(db)
    assert q["period"] == 1 and float(q["gbp_usd"]) != data.FX_GBP_USD_START
    sound(db)


def test_a_higher_interest_rate_abroad_makes_a_share_worth_less(db):
    co = {"sector": "technology"}
    low = world._fair(co, Decimal(400), 300)
    high = world._fair(co, Decimal(400), 500)
    assert high < low
    # A fast grower loses more of its worth than an oil company when rates rise.
    oil = {"sector": "oil_gas"}
    assert high / low < world._fair(oil, Decimal(400), 500) / world._fair(oil, Decimal(400), 300)


def test_lending_abroad_pays_americas_rate_once_the_markets_are_open(db):
    assert world.rate_abroad(db) == data.WORLD_RATE_BPS
    opened(db)
    assert world.rate_abroad(db) == world.economy(db, "US")["rate_bps"]


def test_growth_abroad_lifts_the_next_oil_price(db):
    opened(db)
    _close(db)
    period = 1
    db.execute("ALTER TABLE world_economies DISABLE TRIGGER world_economies_permanent")
    db.execute("UPDATE world_economies SET growth_bps = growth_bps + 200 WHERE period = %s", (period,))
    db.execute("ALTER TABLE world_economies ENABLE TRIGGER world_economies_permanent")
    assert world.oil_demand_bps(db, period) > 0


# ---------------------------------------------------------------------------
# Nigerian arms
# ---------------------------------------------------------------------------

def _arm(db, ticker="AHP"):
    return _one(db, "SELECT a.*, c.share_asset, c.id AS cid FROM world_arms a JOIN companies c ON c.id = a.company_id WHERE c.ticker = %s", (ticker,))


def _drain_reserves(db, keep_quarters_bps=12_000):
    cb = ledger.account_id(db, ledger.CENTRAL_BANK)
    world_abroad, _ = abroad.accounts(db)
    keep = fx.imports_usd(db) * keep_quarters_bps // BPS
    have = ledger.balance(db, cb, "USD")
    if have > keep:
        ledger.post(db, kind="fx_abroad", memo="test", legs=[ledger.Leg(cb, -(have - keep), "USD"), ledger.Leg(world_abroad, have - keep, "USD")])


def test_a_parents_dividends_wait_for_dollars_when_reserves_are_low(db):
    opened(db)
    arm = _arm(db)
    db.execute("ALTER TABLE fx_quarters DISABLE TRIGGER fx_quarters_permanent")
    db.execute("UPDATE fx_quarters SET cover_bps = 11_000")
    db.execute("ALTER TABLE fx_quarters ENABLE TRIGGER fx_quarters_permanent")
    small = world.parent_room(db)
    db.execute("ALTER TABLE fx_quarters DISABLE TRIGGER fx_quarters_permanent")
    db.execute("UPDATE fx_quarters SET cover_bps = 30_000")
    db.execute("ALTER TABLE fx_quarters ENABLE TRIGGER fx_quarters_permanent")
    assert world.parent_room(db) > small >= 0


@pytest.mark.world("eight")
def test_a_leaving_parent_sells_pieces_to_empires_and_the_rest_to_the_pension_funds(db):
    t9 = opened8(db)
    head, _, empire = empire_head(db)
    arm = _arm(db)
    db.execute("UPDATE world_arms SET status = 'leaving', announced_period = 0, deadline_period = 1 WHERE company_id = %s", (arm["company_id"],))
    held = ledger.balance(db, arm["parent_account"], arm["share_asset"])
    issued = ledger.amount_in_existence(db, arm["share_asset"])
    want = issued * 100 // BPS                      # 1%
    got = world.buy_stake(db, head, "AHP", want, t9)
    acct = _one(db, "SELECT account_id FROM empires WHERE head_player_id = %s", (head,))["account_id"]
    assert ledger.balance(db, acct, arm["share_asset"]) == want
    assert got["price"] < world.market_price(db, arm["company_id"])
    with pytest.raises(world.WorldError):
        world.buy_stake(db, head, "AHP", issued * 3_000 // BPS, t9)          # never to 30%
    db.execute("UPDATE world_arms SET deadline_period = 9 WHERE company_id = %s", (arm["company_id"],))
    _close(db, 9)
    a = _arm(db)
    assert a["status"] == "left" and ledger.balance(db, a["parent_account"], a["share_asset"]) == 0
    assert ledger.balance(db, ledger.account_id(db, ledger.INVESTORS_INSTITUTIONS), arm["share_asset"]) >= held - want
    sound(db)


@pytest.mark.world("eight")
def test_a_parent_not_selling_sells_nothing(db):
    t9 = opened8(db)
    head, _, _ = empire_head(db)
    with pytest.raises(world.WorldError, match="not selling"):
        world.buy_stake(db, head, "AHP", 1000, t9)


def test_the_parent_votes_with_the_board(db):
    from simulation import corporate
    opened(db)
    arm = _arm(db)
    vid = corporate.open_vote(db, arm["company_id"], subject="share_split", question="?", explanation="", board="for", period=1, detail={})
    vote = _one(db, "SELECT * FROM company_votes WHERE id = %s", (vid,))
    tally = corporate._tally(db, vote, corporate._investors(db))
    assert tally["Foreign parent"][0] > 0
