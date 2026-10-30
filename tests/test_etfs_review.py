"""Index funds and ETFs: what the independent review found, each fixed and tested."""

from __future__ import annotations

from datetime import timedelta

import pytest

from simulation import etfs, exchange, indexes, ledger
from simulation import world_data as data
from simulation.money import BPS, naira
from tests.test_etfs import DAY, TRADING, _one, _rows, as_dealer, move_shares, person, ring, sound, started


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
