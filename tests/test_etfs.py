"""The talent and funds stage, Part 3: index funds and ETFs.

The game's indexes and their rules; ETFs whose units trade on the exchange, made and unmade by approved dealers; the market
makers and the gap between price and value; 2x, inverse and commodity ETFs; players' own ETFs, index funds and indexes;
reviews announced ahead; passive money; tracking records; futures and options on the main indexes.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta

import pytest
from psycopg.rows import dict_row

from simulation import careers, clock, derivatives, etfs, exchange, funds, indexes, ledger, objectives
from simulation import world_data as data
from simulation.money import BPS, naira
from tests.test_careers import professional
from tests.test_market import OPEN, trader

DAY = OPEN.date()
TRADING = OPEN.replace(hour=15)


def _one(db, sql, params=()):
    with db.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(sql, params).fetchall()
    return rows[0] if rows else None


def _rows(db, sql, params=()):
    with db.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def ring(db, day):
    """A closing bell; then the indexes and ETFs, and then the funds, deal at it."""
    rung = datetime.combine(day, time(22, 5), tzinfo=clock.LAGOS)
    db.execute("INSERT INTO closing_bells (session_date, rung_at, content) VALUES (%s, %s, '{}') ON CONFLICT DO NOTHING", (day, rung))
    db.execute("INSERT INTO index_days (session_date, level) VALUES (%s, 100000) ON CONFLICT DO NOTHING", (day,))
    etfs.tick(db, rung + timedelta(minutes=1))
    funds.tick(db, rung + timedelta(minutes=2))
    return rung + timedelta(minutes=2)


def started(db):
    """The world's first bell has rung: the indexes, the computer's ETFs and index funds exist."""
    ring(db, DAY - timedelta(days=1))


def person(db, name, *, cash_naira=50_000_000, level=1, build="accountant"):
    player, account = professional(db, name, build=build, employer=None, now=OPEN, cash_naira=cash_naira)
    if level > 1:
        careers.add_experience(db, player, build, careers.experience_for(level), OPEN)
    return player, account


def sound(db):
    assert ledger.audit(db) == []
    assert etfs.check_books(db) == []
    assert funds.check_books(db) == []
    assert exchange.check_books(db) == []


def move_shares(db, tickers, bps):
    """Every share named moves by `bps`: with no trades today, an index and an ETF's value use the reference price."""
    db.execute("UPDATE market_instruments m SET reference_price = m.reference_price * (10000 + %s) / 10000,"
               " last_price = coalesce(m.last_price, m.reference_price) * (10000 + %s) / 10000"
               " FROM companies c WHERE c.id = m.company_id AND c.ticker = ANY(%s)", (bps, bps, list(tickers)))


def as_dealer(monkeypatch, account):
    monkeypatch.setattr(etfs, "dealer_account", lambda conn, player_id: (account, {}))


# ---------------------------------------------------------------------------
# Indexes
# ---------------------------------------------------------------------------

def test_weights_are_capped_and_the_excess_shared_among_the_rest():
    w = indexes.capped_weights([50, 20, 10, 5, 5, 4, 3, 3], 1500)
    assert sum(w) == BPS and max(w) <= 1500 and w[0] == 1500
    few = indexes.capped_weights([70, 20, 10], 1500)                    # fewer than seven: one and a half times an equal share
    assert sum(few) == BPS and max(few) <= 5000


def test_the_game_s_eight_indexes_start_together_at_one_thousand_with_published_rules(db):
    started(db)
    rows = _rows(db, "SELECT * FROM market_indexes ORDER BY code")
    assert [r["code"] for r in rows] == sorted(c for c, *_ in data.INDEXES)
    for r in rows:
        assert r["level"] == data.INDEX_START_LEVEL and r["rules_words"]
        mem = indexes.members(db, r["code"])
        if r["code"] in ("DIVIDEND", "CORPBOND", "GOVBOND"):
            continue                                                    # a new world has paid no dividends and has no bonds yet
        assert mem and sum(m["weight_bps"] for m in mem) == BPS, r["code"]
    top = indexes.members(db, "TOP30")
    assert len(top) == 30 and max(m["weight_bps"] for m in top) <= data.INDEX_CAP_BPS
    banks = {m["ticker"] for m in indexes.members(db, "BANKS")}
    assert banks == {r["ticker"] for r in _rows(db, "SELECT ticker FROM companies WHERE sector = 'banking' AND listed")}


def test_an_index_moves_with_its_members_prices_and_a_change_of_members_does_not_move_it(db):
    started(db)
    banks = [m["ticker"] for m in indexes.members(db, "BANKS")]
    move_shares(db, banks, 500)                                         # every bank up 5%
    ring(db, DAY)
    level = _one(db, "SELECT level FROM index_levels WHERE index_code = 'BANKS' AND session_date = %s", (DAY,))["level"]
    assert abs(level - 105_000) <= 50
    # A change made at a bell: the level that day is worked out before the members change, and the next day starts from it.
    plan = [{"asset": m["asset"], "ticker": m["ticker"], "weight_bps": BPS // 4} for m in indexes.members(db, "BANKS")[:4]]
    db.execute("INSERT INTO index_changes (index_code, period, announced_at, effective_day, adds, drops, plan) VALUES ('BANKS', 1, %s, %s,"
               " '[]', '[]', %s)", (OPEN, DAY + timedelta(days=1), __import__("json").dumps(plan)))
    ring(db, DAY + timedelta(days=1))
    assert len(indexes.members(db, "BANKS")) == 4
    after = _one(db, "SELECT level FROM index_levels WHERE index_code = 'BANKS' AND session_date = %s", (DAY + timedelta(days=1),))["level"]
    assert after == level                                               # no prices moved: no change in the level
    sound(db)


def test_the_review_announces_changes_three_bells_ahead_and_the_dealers_place_orders_the_bell_before(db):
    started(db)
    # Make the smallest top-30 company huge... no: shrink the 30th and lift the 31st, so they swap places at the review.
    top = {m["ticker"] for m in indexes.members(db, "TOP30")}
    outside = _rows(db, "SELECT c.ticker FROM companies c JOIN market_instruments m ON m.company_id = c.id WHERE c.listed AND c.ticker <> ALL(%s)"
                        " ORDER BY c.ticker LIMIT 1", (list(top),))[0]["ticker"]
    move_shares(db, [outside], 9_000)                                   # nearly doubles
    changes = indexes.review(db, 1, OPEN)
    top30 = next(c for c in changes if c["index_code"] == "TOP30")
    assert any(a["ticker"] == outside for a in top30["adds"]) and top30["drops"]
    assert top30["effective_day"] == DAY + timedelta(days=2)            # the third bell from now, counting today's
    ring(db, DAY)                                                       # nothing yet
    assert outside not in {m["ticker"] for m in indexes.members(db, "TOP30")}
    ring(db, DAY + timedelta(days=1))                                   # the bell before: the dealers' orders go in
    assert _one(db, "SELECT orders_placed FROM index_changes WHERE id = %s", (top30["id"],))["orders_placed"]
    ring(db, DAY + timedelta(days=2))
    assert outside in {m["ticker"] for m in indexes.members(db, "TOP30")}
    # The Top 30 ETF now holds the newcomer.
    topx = etfs.by_code(db, "TOPX")
    asset = _one(db, "SELECT share_asset AS a FROM companies WHERE ticker = %s", (outside,))["a"]
    assert ledger.balance(db, topx["account_id"], asset) > 0
    sound(db)


# ---------------------------------------------------------------------------
# The computer's ETFs and index funds
# ---------------------------------------------------------------------------

def test_the_computer_s_etfs_and_index_funds_start_at_the_first_bell_holding_what_they_copy(db):
    started(db)
    codes = {e["code"] for e in _rows(db, "SELECT code FROM etfs WHERE computer")}
    assert codes == {c for c, *_ in data.COMPUTER_ETFS}
    topx = etfs.by_code(db, "TOPX")
    h = etfs.holdings_value(db, topx["account_id"], OPEN)
    assert len(h["lines"]) == 30 and h["cash"] < h["total"] * 3 // 100
    assert abs(etfs.nav_now(db, topx, OPEN) - data.ETF_FIRST_NAV_KOBO) <= 20       # ₦100 a unit, less the dealing cost
    gold = etfs.by_code(db, "MTLX")
    assert etfs.holdings_value(db, gold["account_id"], OPEN)["lines"] == []          # a daily-reset ETF holds only cash
    idx = _rows(db, "SELECT * FROM investment_funds WHERE strategy = 'index'")
    assert {f["index_code"] for f in idx} == {"TOP30", "GOVBOND"}
    sound(db)


def test_2x_and_inverse_etfs_reset_every_day(db):
    started(db)
    top = [m["ticker"] for m in indexes.members(db, "TOP30")]
    lev, inv, plain = (etfs.by_code(db, c) for c in ("TOPL", "TOPI", "TOPX"))
    move_shares(db, top, 200)                                           # the index rises 2%
    ring(db, DAY)
    lev2, inv2 = etfs.by_code(db, "TOPL"), etfs.by_code(db, "TOPI")
    assert abs(lev2["nav"] - lev["nav"] * 104 // 100) <= lev["nav"] // 500
    assert abs(inv2["nav"] - inv["nav"] * 98 // 100) <= inv["nav"] // 500
    move_shares(db, top, -196)                                          # and falls back to where it began
    ring(db, DAY + timedelta(days=1))
    assert etfs.by_code(db, "TOPL")["nav"] < lev["nav"]                 # up 4% then down 4%: below where it began
    sound(db)


# ---------------------------------------------------------------------------
# Trading ETF units
# ---------------------------------------------------------------------------

def test_a_player_buys_from_the_market_makers_near_value_and_pays_a_small_fee(db):
    started(db)
    p, account = person(db, "bola")
    topx = etfs.by_code(db, "TOPX")
    quote = etfs.maker_quote(db, topx, TRADING)
    assert quote["bid"] < quote["nav"] < quote["ask"]
    fees = ledger.balance(db, ledger.account_id(db, exchange.FEES))
    done = etfs.place_order(db, p, "TOPX", side="buy", quantity=1_000, limit_price=quote["ask"], now=TRADING)
    assert done["trades"] and done["order"]["status"] == "filled"
    assert ledger.balance(db, account, topx["asset"]) == 1_000
    assert ledger.balance(db, ledger.account_id(db, exchange.FEES)) > fees
    assert objectives.wealth(db, account, TRADING)["funds"] == 1_000 * etfs.by_code(db, "TOPX")["reference_price"]
    sold = etfs.place_order(db, p, "TOPX", side="sell", quantity=1_000, limit_price=etfs.maker_quote(db, topx, TRADING)["bid"], now=TRADING)
    assert sold["order"]["status"] == "filled" and ledger.balance(db, account, topx["asset"]) == 0
    assert ledger.balance(db, account) < naira(50_000_000)               # the spread and the fees: a round trip costs a little
    sound(db)


def test_players_orders_meet_each_other_and_what_is_left_expires_at_the_bell(db):
    started(db)
    a, a_acc = person(db, "ada")
    b, b_acc = person(db, "bola")
    topx = etfs.by_code(db, "TOPX")
    q = etfs.maker_quote(db, topx, TRADING)
    etfs.place_order(db, a, "TOPX", side="buy", quantity=2_000, limit_price=q["ask"], now=TRADING)
    mid = (q["bid"] + q["ask"]) // 2
    resting = etfs.place_order(db, a, "TOPX", side="sell", quantity=500, limit_price=mid, now=TRADING)
    assert resting["order"]["status"] == "open"
    took = etfs.place_order(db, b, "TOPX", side="buy", quantity=500, limit_price=mid, now=TRADING)
    assert took["trades"] == [{"price": mid, "quantity": 500}]           # the waiting order inside the makers' quotes is met first
    left = etfs.place_order(db, b, "TOPX", side="buy", quantity=300, limit_price=q["bid"] - 5, now=TRADING)
    assert left["order"]["status"] == "open"
    sound(db)
    ring(db, DAY)
    assert _one(db, "SELECT status FROM etf_orders WHERE id = %s", (left["order"]["id"],))["status"] == "expired"
    assert ledger.balance(db, etfs.held_account(db)) == 0
    sound(db)


def test_an_order_outside_the_day_s_band_or_after_the_close_is_refused(db):
    started(db)
    p, _ = person(db, "bola")
    topx = etfs.by_code(db, "TOPX")
    low, high = etfs.band(topx)
    with pytest.raises(etfs.EtfError, match="trades between"):
        etfs.place_order(db, p, "TOPX", side="buy", quantity=10, limit_price=high + 1, now=TRADING)
    with pytest.raises(etfs.EtfError, match="12:00 to 22:00"):
        etfs.place_order(db, p, "TOPX", side="buy", quantity=10, limit_price=topx["reference_price"], now=OPEN.replace(hour=23))


def test_2x_and_inverse_etfs_need_level_fifteen_and_the_warning_read(db):
    started(db)
    low, _ = person(db, "junior", level=10)
    high, _ = person(db, "senior", level=15)
    q = etfs.maker_quote(db, etfs.by_code(db, "TOPL"), TRADING)
    with pytest.raises(etfs.EtfError, match="Level 15"):
        etfs.place_order(db, low, "TOPL", side="buy", quantity=100, limit_price=q["ask"], now=TRADING)
    with pytest.raises(etfs.EtfError, match="warning"):
        etfs.place_order(db, high, "TOPL", side="buy", quantity=100, limit_price=q["ask"], now=TRADING)
    etfs.accept_warning(db, high, TRADING)
    assert etfs.place_order(db, high, "TOPL", side="buy", quantity=100, limit_price=q["ask"], now=TRADING)["trades"]
    assert "lose" in etfs.factsheet(db, "TOPL", high, TRADING)["warning"]


# ---------------------------------------------------------------------------
# Dealers: making and unmaking units
# ---------------------------------------------------------------------------

def test_only_an_approved_dealer_makes_units_in_blocks_against_a_basket_or_cash(db, monkeypatch):
    started(db)
    p, account = person(db, "dealer", cash_naira=500_000_000)
    with pytest.raises(etfs.EtfError):
        etfs.create(db, p, "TOPX", data.ETF_CREATION_UNITS, "cash", TRADING)
    as_dealer(monkeypatch, account)
    with pytest.raises(etfs.EtfError, match="blocks"):
        etfs.create(db, p, "TOPX", 1_234, "cash", TRADING)
    before = etfs.units_out(db, etfs.by_code(db, "TOPX"))
    made = etfs.create(db, p, "TOPX", data.ETF_CREATION_UNITS, "cash", TRADING)
    assert made["fee"] == made["nav"] * data.ETF_CREATION_UNITS * data.ETF_CASH_FEE_BPS // BPS
    assert etfs.units_out(db, etfs.by_code(db, "TOPX")) == before + data.ETF_CREATION_UNITS
    # Against a basket: the dealer hands over the fund's own shares for that many units.
    topx = etfs.by_code(db, "TOPX")
    b = etfs.basket(db, topx, data.ETF_CREATION_UNITS, TRADING)
    with pytest.raises(etfs.EtfError, match="short of"):
        etfs.create(db, p, "TOPX", data.ETF_CREATION_UNITS, "basket", TRADING)
    public = ledger.account_id(db, ledger.INVESTORS_PUBLIC)
    for x in b["lines"]:
        ledger.transfer(db, payer=public, receiver=account, amount=x["units"], asset=x["asset"], kind="test_shares", memo="Test: shares")
    etfs.create(db, p, "TOPX", data.ETF_CREATION_UNITS, "basket", TRADING)
    assert ledger.balance(db, account, topx["asset"]) == 2 * data.ETF_CREATION_UNITS
    back = etfs.redeem(db, p, "TOPX", data.ETF_CREATION_UNITS, "basket", TRADING)
    assert back["units"] == data.ETF_CREATION_UNITS
    assert all(ledger.balance(db, account, x["asset"]) > 0 for x in b["lines"][:5])
    sound(db)


def test_when_the_price_runs_above_value_a_dealer_makes_units_and_sells_them_at_a_profit(db, monkeypatch):
    started(db)
    buyer, _ = person(db, "crowd", cash_naira=2_000_000_000)
    d, d_acc = person(db, "dealer", cash_naira=500_000_000)
    as_dealer(monkeypatch, d_acc)
    topx = etfs.by_code(db, "TOPX")
    # The crowd buys heavily: the makers raise where they quote.
    for _ in range(8):
        q = etfs.maker_quote(db, etfs.by_code(db, "TOPX"), TRADING)
        etfs.place_order(db, buyer, "TOPX", side="buy", quantity=q["depth"], limit_price=q["ask"], now=TRADING)
    topx = etfs.by_code(db, "TOPX")
    assert topx["premium_bps"] >= 40
    start = ledger.balance(db, d_acc)
    units = 3 * data.ETF_CREATION_UNITS
    etfs.create(db, d, "TOPX", units, "cash", TRADING)
    q = etfs.maker_quote(db, etfs.by_code(db, "TOPX"), TRADING)
    etfs.place_order(db, d, "TOPX", side="sell", quantity=units, limit_price=q["bid"], now=TRADING)
    assert ledger.balance(db, d_acc, topx["asset"]) == 0
    assert ledger.balance(db, d_acc) > start                             # made at value, sold above it
    assert abs(etfs.by_code(db, "TOPX")["premium_bps"]) <= data.ETF_PREMIUM_MOST_BPS
    sound(db)


# ---------------------------------------------------------------------------
# Players' own ETFs, index funds and indexes
# ---------------------------------------------------------------------------

def test_an_asset_manager_of_level_twenty_launches_an_etf_and_earns_its_fee(db):
    started(db)
    junior, _ = person(db, "junior", build="asset_manager", level=19)
    with pytest.raises(etfs.EtfError, match="Level 20"):
        etfs.launch(db, junior, code="JUNX", name="Junior Banks Tracker", index_code="BANKS", method="full", fee_bps=30, seed=naira(10_000_000), now=TRADING)
    ada, ada_acc = person(db, "ada", build="asset_manager", level=20)
    for bad in ({"fee_bps": 101}, {"code": "TOPX"}, {"code": "IDC"}, {"index_code": "NOPE"}, {"seed": naira(1_000_000)},
                {"name": "Broad Street Banks Two"}, {"index_code": "GOVBOND", "method": "sample"}):
        args = {"code": "IKBT", "name": "Ikoyi Banks Tracker", "index_code": "BANKS", "method": "full", "fee_bps": 30, "seed": naira(10_000_000)}
        args.update(bad)
        with pytest.raises(etfs.EtfError):
            etfs.launch(db, ada, now=TRADING, **args)
    etf = etfs.launch(db, ada, code="IKBT", name="Ikoyi Banks Tracker", index_code="BANKS", method="sample", fee_bps=30, seed=naira(10_000_000),
                      now=TRADING)
    assert ledger.balance(db, ada_acc, etf["asset"]) == naira(10_000_000) // data.ETF_FIRST_NAV_KOBO
    assert len(etfs.holdings_value(db, etf["account_id"], TRADING)["lines"]) >= 5
    before = ledger.balance(db, ada_acc)
    ring(db, DAY)
    assert ledger.balance(db, ada_acc) > before                          # the day's fee
    with pytest.raises(etfs.EtfError, match="one ETF"):
        etfs.launch(db, ada, code="IKBU", name="Ikoyi Banks Two", index_code="BANKS", method="full", fee_bps=30, seed=naira(10_000_000), now=TRADING)
    sound(db)


def test_closing_an_etf_pays_every_holder_the_value_of_their_units(db):
    started(db)
    ada, ada_acc = person(db, "ada", build="asset_manager", level=20)
    etf = etfs.launch(db, ada, code="IKBT", name="Ikoyi Banks Tracker", index_code="BANKS", method="full", fee_bps=30, seed=naira(10_000_000), now=TRADING)
    b, b_acc = person(db, "bola")
    q = etfs.maker_quote(db, etf, TRADING)
    etfs.place_order(db, b, "IKBT", side="buy", quantity=2_000, limit_price=q["ask"], now=TRADING)
    etfs.close(db, ada, TRADING)
    with pytest.raises(etfs.EtfError):
        etfs.place_order(db, b, "IKBT", side="buy", quantity=10, limit_price=q["ask"], now=TRADING)
    cash = ledger.balance(db, b_acc)
    ring(db, DAY)
    e = etfs.by_code(db, "IKBT")
    assert e["status"] == "closed" and etfs.units_out(db, e) == 0
    assert ledger.balance(db, b_acc, e["asset"]) == 0 and ledger.balance(db, b_acc) > cash
    sound(db)


def test_an_index_fund_copies_its_index_and_its_manager_cannot_deal_for_it(db):
    started(db)
    ada, _ = person(db, "ada", build="asset_manager", level=20)
    with pytest.raises(funds.FundError, match="performance fee"):
        funds.launch(db, ada, name="Ikoyi Index Fund", strategy="index", index_code="TOP30", fee_bps=20, perf_fee_bps=500, least_in=naira(10_000),
                     seed=naira(10_000_000), now=TRADING)
    fund = funds.launch(db, ada, name="Ikoyi Index Fund", strategy="index", index_code="TOP30", fee_bps=20, perf_fee_bps=0, least_in=naira(10_000),
                        seed=naira(10_000_000), now=TRADING)
    assert len(etfs.holdings_value(db, fund["account_id"], TRADING)["lines"]) == 30
    with pytest.raises(funds.FundError, match="copies its index"):
        funds.trade_shares(db, ada, ticker="IDC", side="buy", quantity=10, limit_price=10_000, now=TRADING)
    top = [m["ticker"] for m in indexes.members(db, "TOP30")]
    move_shares(db, top, 300)
    ring(db, DAY)
    day = _one(db, "SELECT * FROM fund_days WHERE fund_id = %s AND session_date = %s", (fund["id"], DAY))
    idx = _one(db, "SELECT level FROM index_levels WHERE index_code = 'TOP30' AND session_date = %s", (DAY,))
    assert day["benchmark"] == idx["level"]
    assert abs(day["unit_price"] / funds.FIRST_PRICE - idx["level"] / data.INDEX_START_LEVEL) < 0.01
    sound(db)


def test_a_manager_publishes_an_index_of_their_own_and_changes_it_with_notice(db):
    started(db)
    ada, _ = person(db, "ada", build="asset_manager", level=20)
    with pytest.raises(indexes.IndexError_, match="5 to 30"):
        indexes.create_custom(db, ada, code="ADA", name="Ada's Picks", tickers=["IDC", "IKB"], weighting="equal", now=TRADING)
    picks = [r["ticker"] for r in _rows(db, "SELECT ticker FROM companies WHERE listed ORDER BY ticker LIMIT 6")]
    idx = indexes.create_custom(db, ada, code="ADA", name="Ada's Picks", tickers=picks, weighting="equal", now=TRADING)
    assert idx["level"] == data.INDEX_START_LEVEL and len(indexes.members(db, "ADA")) == 6
    other, _ = person(db, "tola", build="asset_manager", level=20)
    with pytest.raises(etfs.EtfError, match="only by that manager"):
        etfs.launch(db, other, code="TOLX", name="Tola Copies Ada", index_code="ADA", method="full", fee_bps=10, seed=naira(10_000_000), now=TRADING)
    ch = indexes.change_custom(db, ada, "ADA", picks[:5], TRADING)
    assert ch["drops"] and ch["effective_day"] == DAY + timedelta(days=2)


# ---------------------------------------------------------------------------
# The quarter's close: passive money, tracking records
# ---------------------------------------------------------------------------

def test_the_households_move_money_into_index_funds_and_etfs_and_the_passive_share_is_recorded(db):
    started(db)
    ring(db, DAY)
    before = etfs.passive_value(db, TRADING)
    etfs.after_close(db, 1, OPEN + timedelta(days=6))
    row = _one(db, "SELECT * FROM passive_quarters WHERE period = 1")
    assert row and row["target_bps"] == data.PASSIVE_START_BPS
    assert row["passive_value"] >= before
    assert _one(db, "SELECT count(*) AS n FROM tracking_quarters WHERE vehicle = 'etf' AND period = 1")["n"] == len(data.COMPUTER_ETFS)
    sound(db)


def test_tracking_figures_measure_the_gap_and_its_swing():
    same = etfs.tracking_figures([(0.01, 0.01), (-0.02, -0.02), (0.005, 0.005)])
    assert same["difference_bps"] == 0 and same["error_bps"] == 0
    off = etfs.tracking_figures([(0.011, 0.01), (-0.021, -0.02), (0.004, 0.005)])
    assert off["error_bps"] > 0


def test_futures_and_options_are_listed_on_the_top_30_banks_and_oil_and_gas_indexes(db):
    started(db)
    derivatives.list_series(db, 0, TRADING)
    rows = _rows(db, "SELECT DISTINCT underlying, kind FROM derivative_series WHERE underlying IN ('TOP30', 'BANKS', 'OILGAS')")
    assert {(r["underlying"], r["kind"]) for r in rows} >= {("TOP30", "future"), ("BANKS", "call"), ("OILGAS", "put")}
    s = _one(db, "SELECT * FROM derivative_series WHERE underlying = 'TOP30' AND kind = 'future' LIMIT 1")
    assert derivatives.spot(db, s, TRADING) == indexes.level_now(db, "TOP30", TRADING)


# ---------------------------------------------------------------------------
# The website
# ---------------------------------------------------------------------------

def test_the_page_lists_indexes_and_etfs_and_never_shows_anybody_else_s_orders_or_holdings(db, client, player):
    started(db)
    a, _ = person(db, "someone")
    topx = etfs.by_code(db, "TOPX")
    q = etfs.maker_quote(db, topx, TRADING)
    etfs.place_order(db, a, "TOPX", side="buy", quantity=300, limit_price=q["bid"] - 3, now=TRADING)
    page = client.get("/api/etfs").json()
    # Every live index is on the page: the four older baskets and Part 4c's six new ones.
    live = {code for (code,) in db.execute("SELECT code FROM market_indexes WHERE status = 'live' AND owner_id IS NULL").fetchall()}
    assert {e["code"] for e in page["etfs"]} >= {"TOPX", "TOPL", "GBND"} and len(page["indexes"]) == len(live)
    assert {"PHARMA", "RETAIL", "TECH", "FILM", "MINING", "FERT"} <= {i["code"] for i in page["indexes"]}
    sheet = client.get("/api/etfs/TOPX").json()
    assert sheet["basket"]["lines"] and sheet["orders"] == [] and sheet["mine"]["units"] == 0
    assert "account" not in str(sheet["book"]) and all(set(b) == {"limit_price", "units"} for b in sheet["book"]["buy"])
    assert client.get("/api/indexes/TOP30").json()["weights"]
    assert client.get("/api/etfs/NOPE").status_code == 404
    assert client.post("/api/etfs/launch", json={"code": "MINE", "name": "My Tracker", "index_code": "TOP30", "method": "full", "fee_bps": 10,
                                                 "seed_naira": 5_000_000}).status_code == 409
    assert client.post("/api/etfs/TOPX/create", json={"units": 10_000, "how": "cash"}).status_code == 409
    assert client.get("/api/etfs/alerts").json()["alerts"] == []
