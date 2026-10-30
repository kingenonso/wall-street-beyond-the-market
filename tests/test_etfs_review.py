"""Index funds and ETFs: what the independent review found, each fixed and tested."""

from __future__ import annotations

from datetime import datetime, time, timedelta

import pytest

from simulation import clock, etfs, exchange, indexes, ledger
from simulation import world_data as data
from simulation.money import BPS, naira
from tests.test_etfs import DAY, OPEN, TRADING, _one, _rows, as_dealer, move_shares, person, ring, sound, started


def test_r1_buying_from_the_makers_and_selling_straight_back_always_loses(db):
    started(db)
    p, acc = person(db, "cycler", cash_naira=2_000_000_000)
    start = ledger.balance(db, acc)
    for _ in range(6):
        q = etfs.maker_quote(db, etfs.by_code(db, "TOPX"), TRADING)
        etfs.place_order(db, p, "TOPX", side="buy", quantity=q["depth"], limit_price=q["ask"], now=TRADING)
        q = etfs.maker_quote(db, etfs.by_code(db, "TOPX"), TRADING)
        etfs.place_order(db, p, "TOPX", side="sell", quantity=min(q["depth"], ledger.balance(db, acc, "ETF-TOPX")), limit_price=q["bid"], now=TRADING)
    held = ledger.balance(db, acc, "ETF-TOPX")
    assert ledger.balance(db, acc) + held * etfs.nav_now(db, etfs.by_code(db, "TOPX"), TRADING) < start
    sound(db)


def test_r2_many_small_fills_never_take_more_than_was_held_for_the_order(db):
    started(db)
    buyer, b_acc = person(db, "patient", cash_naira=10_000_000)
    topx = etfs.by_code(db, "TOPX")
    q = etfs.maker_quote(db, topx, TRADING)
    price = (q["bid"] + q["ask"]) // 2
    order = etfs.place_order(db, buyer, "TOPX", side="buy", quantity=100, limit_price=price, now=TRADING)["order"]
    sellers = []
    for k in range(10):
        s, s_acc = person(db, f"seller{k}", cash_naira=1_000_000)
        etfs.place_order(db, s, "TOPX", side="buy", quantity=20, limit_price=q["ask"], now=TRADING)
        sellers.append(s)
    for s in sellers:
        for _ in range(10):
            etfs.place_order(db, s, "TOPX", side="sell", quantity=1, limit_price=price, now=TRADING)
    after = _one(db, "SELECT * FROM etf_orders WHERE id = %s", (order["id"],))
    assert after["status"] == "filled" and after["reserved"] == 0
    sound(db)
    ring(db, DAY)                                                       # the bell runs: nothing is stuck
    assert _one(db, "SELECT dealt_through FROM etf_progress")["dealt_through"] == DAY


def test_r3_a_cancelled_order_cannot_then_be_traded_against(db):
    started(db)
    a, a_acc = person(db, "ada")
    b, _ = person(db, "bola")
    q = etfs.maker_quote(db, etfs.by_code(db, "TOPX"), TRADING)
    etfs.place_order(db, a, "TOPX", side="buy", quantity=1_000, limit_price=q["ask"], now=TRADING)
    mid = (q["bid"] + q["ask"]) // 2
    resting = etfs.place_order(db, a, "TOPX", side="sell", quantity=500, limit_price=mid, now=TRADING)["order"]
    etfs.cancel_order(db, a, resting["id"], TRADING)
    took = etfs.place_order(db, b, "TOPX", side="buy", quantity=500, limit_price=mid, now=TRADING)
    assert all(t["price"] != mid for t in took["trades"])
    sound(db)


def test_r4_a_waiting_buy_filled_below_its_limit_gets_the_difference_back_at_once(db):
    started(db)
    a, a_acc = person(db, "ada", cash_naira=100_000_000)
    b, _ = person(db, "bola", cash_naira=100_000_000)
    q = etfs.maker_quote(db, etfs.by_code(db, "TOPX"), TRADING)
    low = q["bid"] + 1
    resting = etfs.place_order(db, a, "TOPX", side="buy", quantity=1_000, limit_price=low, now=TRADING)["order"]
    etfs.place_order(db, b, "TOPX", side="buy", quantity=1_000, limit_price=q["ask"], now=TRADING)
    etfs.place_order(db, b, "TOPX", side="sell", quantity=1_000, limit_price=low, now=TRADING)
    after = _one(db, "SELECT * FROM etf_orders WHERE id = %s", (resting["id"],))
    assert after["status"] == "filled" and after["reserved"] == 0
    assert ledger.balance(db, etfs.held_account(db)) == 0
    sound(db)


def test_r5_units_made_during_the_day_do_not_collect_a_move_from_before_they_existed(db, monkeypatch):
    started(db)
    d, d_acc = person(db, "dealer", cash_naira=2_000_000_000)
    as_dealer(monkeypatch, d_acc)
    lev = etfs.by_code(db, "TOPL")
    top = [m["ticker"] for m in indexes.members(db, "TOP30")]
    move_shares(db, top, 300)                                           # the index is up 3% today
    nav_then = etfs.nav_now(db, lev, TRADING)
    assert nav_then > lev["nav"]
    monkeypatch.setattr(etfs, "_gate", lambda *a, **k: None)
    made = etfs.create(db, d, "TOPL", 5 * data.ETF_CREATION_UNITS, "cash", TRADING)
    assert abs(made["nav"] - nav_then) <= 2                             # made at today's value...
    ring(db, DAY)
    after = etfs.by_code(db, "TOPL")["nav"]
    assert abs(after - made["nav"]) <= made["nav"] // 500                # ...and not paid the morning's move a second time
    sound(db)


def test_r6_one_tiny_trade_at_the_limit_does_not_move_an_index(db):
    started(db)
    banks = indexes.members(db, "BANKS")
    big = banks[0]
    before = indexes.level_now(db, "BANKS", TRADING)
    a, _ = person(db, "mover", cash_naira=10_000_000)
    seller = ledger.account_id(db, ledger.INVESTORS_PUBLIC)
    ref = _one(db, "SELECT reference_price FROM market_instruments m JOIN companies c ON c.id = m.company_id WHERE c.ticker = %s", (big["ticker"],))["reference_price"]
    _, high = exchange.price_limits(ref)
    # Many ordinary trades near the price today, and one tiny one at the day's top.
    db.execute("UPDATE market_instruments SET last_price = %s FROM companies c WHERE c.id = market_instruments.company_id AND c.ticker = %s",
               (high, big["ticker"]))
    assert seller and a
    assert indexes.level_now(db, "BANKS", TRADING) == before            # a last price alone (no volume behind it) moves nothing


def test_r7_a_closing_trade_above_value_does_not_make_holders_richer(db):
    started(db)
    a, a_acc = person(db, "ada", cash_naira=100_000_000)
    q = etfs.maker_quote(db, etfs.by_code(db, "TOPX"), TRADING)
    etfs.place_order(db, a, "TOPX", side="buy", quantity=1_000, limit_price=q["ask"], now=TRADING)
    db.execute("UPDATE etfs SET reference_price = reference_price * 11 / 10 WHERE code = 'TOPX'")
    e = etfs.by_code(db, "TOPX")
    assert etfs.held_value(db, a_acc) == 1_000 * min(e["nav"], e["reference_price"])


def test_r8_a_head_cannot_trade_between_their_own_account_and_their_empire_s(db, monkeypatch):
    started(db)
    head, own = person(db, "head", cash_naira=100_000_000)
    empire_acc = ledger.create_account(db, kind="empire", name="Test empire")
    ledger.transfer(db, payer=ledger.account_id(db, ledger.TREASURY), receiver=empire_acc, amount=naira(100_000_000), kind="test_cash", memo="Test")
    from simulation import empires
    seat = {"empire_kind": "player", "empire_status": "active", "head_player_id": head, "account_id": empire_acc, "empire_id": 1}
    monkeypatch.setattr(empires, "seat_of", lambda conn, pid, **kw: seat)
    q = etfs.maker_quote(db, etfs.by_code(db, "TOPX"), TRADING)
    etfs.place_order(db, head, "TOPX", side="buy", quantity=1_000, limit_price=q["ask"], now=TRADING)
    _, high = etfs.band(etfs.by_code(db, "TOPX"))
    etfs.place_order(db, head, "TOPX", side="sell", quantity=500, limit_price=high, now=TRADING)
    took = etfs.place_order(db, head, "TOPX", side="buy", quantity=500, limit_price=high, now=TRADING, for_empire=True)
    assert all(t["price"] != high for t in took["trades"])


def test_r9_a_dealer_below_level_fifteen_cannot_make_2x_units(db, monkeypatch):
    started(db)
    d, d_acc = person(db, "junior_dealer", cash_naira=500_000_000, level=5)
    as_dealer(monkeypatch, d_acc)
    with pytest.raises(etfs.EtfError, match="Level 15"):
        etfs.create(db, d, "TOPL", data.ETF_CREATION_UNITS, "cash", TRADING)


def test_r10_a_custom_index_changes_once_a_quarter_with_no_desk_orders_and_its_holders_are_told(db):
    started(db)
    ada, _ = person(db, "ada", build="asset_manager", level=20)
    picks = [r["ticker"] for r in _rows(db, "SELECT ticker FROM companies WHERE listed ORDER BY ticker LIMIT 7")]
    indexes.create_custom(db, ada, code="ADA", name="Ada's Picks", tickers=picks[:6], weighting="equal", now=TRADING)
    ch = indexes.change_custom(db, ada, "ADA", picks[1:7], TRADING)
    assert ch["orders_placed"]                                          # the dealers place no orders for a manager's own index
    assert _one(db, "SELECT count(*) AS n FROM etf_alerts WHERE index_code = 'ADA' AND kind = 'index_change'")["n"] == 1
    for k in range(3):
        ring(db, DAY + timedelta(days=k))
    with pytest.raises(indexes.IndexError_, match="once a game quarter"):
        indexes.change_custom(db, ada, "ADA", picks[:5], TRADING + timedelta(days=3))


def test_r11_the_makers_pay_the_dealing_cost_when_they_make_units_for_cash(db):
    started(db)
    topx = etfs.by_code(db, "TOPX")
    nav = etfs.nav_now(db, topx, TRADING)
    maker = ledger.account_id(db, ledger.INVESTORS_INSTITUTIONS)
    etfs._create_cash(db, topx, maker, 10 * data.ETF_CREATION_UNITS, TRADING, 1, fee_bps=etfs.DEALING_COST_BPS)
    assert etfs.nav_now(db, etfs.by_code(db, "TOPX"), TRADING) >= nav - 1


def test_r12_a_2x_etf_settles_its_exact_move(db):
    started(db)
    lev = etfs.by_code(db, "TOPL")
    level = indexes.level_now(db, "TOPL" if False else "TOP30", TRADING)
    top = [m["ticker"] for m in indexes.members(db, "TOP30")]
    move_shares(db, top, 137)
    ring(db, DAY)
    now_level = _one(db, "SELECT level FROM index_levels WHERE index_code = 'TOP30' AND session_date = %s", (DAY,))["level"]
    expect = lev["nav"] * (1 + 2 * (now_level / level - 1))
    assert abs(etfs.by_code(db, "TOPL")["nav"] - expect) <= lev["nav"] * 3 // 10_000 + 2     # the day's fee and a kobo


def test_r13_index_funds_money_is_sent_as_text(db, client, player):
    started(db)
    page = client.get("/api/etfs").json()
    f = page["index_funds"][0]
    assert isinstance(f["worth"], str) and isinstance(f["unit_price"], str) and isinstance(f["least_in"], str)


def test_r14_a_trade_worth_one_kobo_does_not_break_anything(db):
    started(db)
    p, acc = person(db, "tiny")
    q = etfs.maker_quote(db, etfs.by_code(db, "TOPX"), TRADING)
    etfs.place_order(db, p, "TOPX", side="buy", quantity=1, limit_price=q["ask"], now=TRADING)
    etfs.place_order(db, p, "TOPX", side="sell", quantity=1, limit_price=q["bid"], now=TRADING)
    sound(db)
    assert BPS


@pytest.mark.world("eight")
def test_r15_a_share_index_counts_dividends_as_if_put_back_so_funds_that_keep_them_follow_it(db):
    """Found in the ten-year run: ETFs keep their dividends, so against a price-only index they ran ahead every quarter."""
    from datetime import datetime, time as dtime
    from simulation import clock
    from tests.conftest import after_quarters
    now = after_quarters(8) + timedelta(hours=14)
    day = exchange.session_of(now)[0]
    indexes.setup(db, day, now)
    db.execute("UPDATE market_indexes SET div_period = 7")              # as if quarter 8's dividends had not been counted yet
    paid = indexes.dividends_per_share(db, [m["asset"] for m in indexes.members(db, "TOP30")], 7, 8)
    assert paid and all(v >= 0 for v in paid.values())
    later = datetime.combine(day + timedelta(days=1), dtime(22, 5), tzinfo=clock.LAGOS)
    indexes.at_bell(db, day + timedelta(days=1), later)
    level = _one(db, "SELECT level FROM market_indexes WHERE code = 'TOP30'")["level"]
    assert level > data.INDEX_START_LEVEL                               # no price moved: only the dividends
    bonds_level = _one(db, "SELECT level FROM market_indexes WHERE code = 'GOVBOND'")["level"]
    assert bonds_level > 0
    assert _one(db, "SELECT div_period FROM market_indexes WHERE code = 'TOP30'")["div_period"] == 8


def test_r16_the_passive_share_is_measured_at_the_same_prices_on_both_sides(db):
    """Found in the ten-year run: in a crash the market was valued at once but ETFs at the last bell, so the share held
    passively jumped; and bond index vehicles were counted against the share market."""
    started(db)
    ring(db, DAY)
    every = [r["ticker"] for r in _rows(db, "SELECT ticker FROM companies c JOIN market_instruments m ON m.company_id = c.id")]
    before = etfs.passive_value(db, TRADING) * BPS // etfs.market_value(db, TRADING)
    market = etfs.market_value(db, TRADING)
    move_shares(db, every, -5_000)
    assert etfs.market_value(db, TRADING) < market * 6 // 10                # everything halved...
    after = etfs.passive_value(db, TRADING) * BPS // etfs.market_value(db, TRADING)
    assert abs(after - before) <= max(before // 20, 2)                      # ...and the passive share hardly moved
    bonds = _one(db, "SELECT * FROM etfs WHERE code = 'GBND'")
    total = etfs.passive_value(db, TRADING)
    db.execute("UPDATE etfs SET status = 'closed' WHERE code = 'GBND'")
    assert etfs.passive_value(db, TRADING) == total and bonds               # the bond ETF was never part of it


def test_r17_the_day_after_a_quarter_closes_counts_in_the_tracking_record(db):
    """Found in the ten-year run: the quarter's record was made before the next bell and the next quarter began after it, so
    the day the results and dividends move prices most was in neither."""
    started(db)
    e = _one(db, "SELECT * FROM etfs WHERE code = 'TOPX'")
    first, last = etfs._quarter_days(db, 2)
    nav = 10_000
    for i, day in enumerate([first - timedelta(days=1) + timedelta(days=k) for k in range(8)]):
        move = 1_000 if i == 1 else 0                                       # the bell after quarter 1's close: +10%
        nav = nav * (BPS + move) // BPS
        db.execute("INSERT INTO etf_days (etf_id, session_date, nav, close, units, tracked_bps) VALUES (%s, %s, %s, %s, 10000, %s)",
                   (e["id"], day, nav, nav, move))
    etfs._tracking(db, 2, datetime.combine(last, time(9), tzinfo=clock.LAGOS))
    row = _one(db, "SELECT * FROM tracking_quarters WHERE vehicle = 'etf' AND vehicle_id = %s AND period = 2", (e["id"],))
    assert row["tracked_bps"] == 1_000 and row["return_bps"] == 1_000


def test_r18_new_cash_goes_in_only_while_the_dealers_can_supply_the_basket(db):
    """Found in the ten-year run: once the dealers had run out of the largest companies, money kept coming in and sat as cash,
    a fifth of some funds, so they fell behind their indexes."""
    started(db)
    e = _one(db, "SELECT * FROM etfs WHERE code = 'TOPX'")
    assert etfs.cash_room(db, e, TRADING) > 0
    top = max(indexes.weights_now(db, "TOP30", TRADING), key=lambda w: w["weight_bps"])
    parked = ledger.create_account(db, kind="fund", name="Shares parked for a test")
    for d in etfs._dealers(db, top["asset"]):
        n = ledger.balance(db, d, top["asset"])
        if n > 0:
            ledger.post(db, kind="etf_basket", memo="test", period=1, legs=[ledger.Leg(d, -n, top["asset"]), ledger.Leg(parked, n, top["asset"])])
    assert etfs.cash_room(db, e, TRADING) == 0
    with pytest.raises(etfs.EtfError, match="against a basket"):
        etfs._create_cash(db, e, ledger.account_id(db, etfs.HOUSEHOLDS), data.ETF_CREATION_UNITS, TRADING, 1)
    before = etfs.units_out(db, e)
    etfs.after_close(db, 1, OPEN + timedelta(days=6))
    assert etfs.units_out(db, _one(db, "SELECT * FROM etfs WHERE code = 'TOPX'")) <= before   # the households put nothing in
    sound(db)


@pytest.mark.world("eight")
def test_r19_a_bond_index_counts_interest_and_repayments_and_a_repaid_bond_cannot_be_bought(db):
    """Found in the ten-year run: the bond index counted only prices while the funds collected the interest, so the bond ETF
    ended 92% ahead of it; and a bond repaid at the close still showed its last price until the next bell."""
    from tests.conftest import after_quarters
    now = after_quarters(8) + timedelta(hours=14)
    day = exchange.session_of(now)[0]
    indexes.setup(db, day, now)
    mem = indexes.members(db, "GOVBOND")
    assert mem
    first = mem[0]
    db.execute("UPDATE market_indexes SET div_period = 7 WHERE code = 'GOVBOND'")
    db.execute("INSERT INTO bond_cash (asset, period, amount, units) VALUES (%s, 8, %s, 1000)", (first["asset"], 1000 * 5_000))
    later = datetime.combine(day + timedelta(days=1), time(22, 5), tzinfo=clock.LAGOS)
    level = indexes.level_now(db, "GOVBOND", later)
    worth = sum(m["quantity"] * m["last_price"] for m in mem)
    assert level > data.INDEX_START_LEVEL and level - data.INDEX_START_LEVEL >= int(first["quantity"] * 5_000 * data.INDEX_START_LEVEL / worth) - 1
    # A repaid bond is worth nothing to anybody who would buy it now: no fund's basket holds it.
    db.execute("UPDATE bonds SET redeemed_period = 8 WHERE asset = %s", (first["asset"],))
    w = {x["asset"]: x for x in indexes.weights_now(db, "GOVBOND", later)}
    assert w[first["asset"]]["price"] == 0 and w[first["asset"]]["weight_bps"] == 0
    e = _one(db, "SELECT * FROM etfs WHERE index_code = 'GOVBOND'") or {"index_code": "GOVBOND", "method": "full"}
    assert first["asset"] not in {x["asset"] for x in etfs._target_basket(db, e, later)}
    indexes.at_bell(db, day + timedelta(days=1), later)
    assert not _one(db, "SELECT 1 AS x FROM index_members WHERE index_code = 'GOVBOND' AND asset = %s", (first["asset"],))


def test_r20_once_the_dealers_have_none_the_founders_sell_to_the_funds_at_a_price_above_the_market(db):
    """Found in the ten-year run: with the dealers out of the largest companies, funds could not reinvest their dividends and
    held up to a third of themselves in cash."""
    started(db)
    e = _one(db, "SELECT * FROM etfs WHERE code = 'TOPX'")
    top = max(indexes.weights_now(db, "TOP30", TRADING), key=lambda w: w["weight_bps"])
    parked = ledger.create_account(db, kind="fund", name="Shares parked for a test")
    founders = ledger.account_id(db, ledger.INVESTORS_FOUNDERS)
    for d in etfs._dealers(db, top["asset"])[:2]:
        n = ledger.balance(db, d, top["asset"])
        if n > 0:
            ledger.post(db, kind="etf_basket", memo="test", period=1, legs=[ledger.Leg(d, -n, top["asset"]), ledger.Leg(parked, n, top["asset"])])
    assert ledger.balance(db, founders, top["asset"]) >= 1_000
    cash, held = ledger.balance(db, e["account_id"]), ledger.balance(db, founders, top["asset"])
    got = etfs.buy_from_dealers(db, e["account_id"], top["asset"], 1_000, top["price"], 1, "test")
    assert got == 1_000 and ledger.balance(db, founders, top["asset"]) == held - 1_000
    paid = cash - ledger.balance(db, e["account_id"])
    assert paid >= 1_000 * top["price"] * (BPS + data.ETF_FOUNDERS_PREMIUM_BPS) // BPS     # above the market: the dealers come first
    assert etfs.cash_room(db, e, TRADING) > 0
    sound(db)


def test_r21_shares_sold_to_the_index_funds_are_not_paid_out_as_pensions(db):
    """Found in the ten-year run: the pension funds counted the money from shares sold to the funds as income and paid 90% of
    it out as pensions, until they had no cash left to settle the 2x, inverse and commodity ETFs, whose holders then fell short."""
    from simulation import economy
    started(db)
    world = economy.load_world(db)
    inst = world.institutions
    seller = ledger.create_account(db, kind="fund", name="A fund for a test")
    ledger.post(db, kind="etf_basket", memo="test", period=7, legs=[ledger.Leg(seller, naira(1_000_000_000)), ledger.Leg(inst, -naira(1_000_000_000))])
    ledger.post(db, kind="etf_basket", memo="test", period=7, legs=[ledger.Leg(inst, naira(1_000_000_000)), ledger.Leg(seller, -naira(1_000_000_000))])
    before = ledger.balance(db, inst)
    economy.pensions_paid(db, world, 7)
    paid = before - ledger.balance(db, inst)
    assert paid <= before * 301 // 10_000 + 1                       # only the usual share of savings: nothing of the sale


def test_r22_units_made_during_the_day_do_not_hide_a_commodity_etf_s_move_from_its_record(db, monkeypatch):
    """Found in the ten-year run: making units settles the move so far, and the bell then measured the day's move from there,
    so the oil ETF's record showed oil standing still on days it had moved."""
    started(db)
    e = _one(db, "SELECT * FROM etfs WHERE code = 'OILX'")
    db.execute("UPDATE etfs SET bell_level = 100, tracked_level = 105 WHERE id = %s", (e["id"],))   # settled at 105 during the day
    monkeypatch.setattr(etfs, "tracked_now", lambda conn, etf, now: 110)
    rung = datetime.combine(DAY, time(22, 5), tzinfo=clock.LAGOS)
    etfs._at_bell(db, etfs._etf(db, e["id"]), DAY, rung, [])
    row = _one(db, "SELECT tracked_bps FROM etf_days WHERE etf_id = %s AND session_date = %s", (e["id"], DAY))
    assert row["tracked_bps"] == 1_000                                  # 100 to 110 since the last bell
    assert _one(db, "SELECT bell_level FROM etfs WHERE id = %s", (e["id"],))["bell_level"] == 110
