"""Stage 4, Part A, slice 1: the order-matching engine and orders on the Broad Street Exchange.

Two players can trade a share. Cash and shares move only through the ledger. Fees are
paid on every trade. Nothing trades outside the day's price limits.
"""

from __future__ import annotations

import random
import threading
from datetime import datetime, timedelta

import pytest
from psycopg import errors
from psycopg.rows import dict_row

from simulation import exchange, ledger, quarters
from simulation import world_data as data
from simulation.money import naira
from tests.conftest import ADULT, after_quarters, join, money_accounted_for

# Tuesday 6 October 2026, Lagos time.
CLOSED_MORNING = datetime.fromisoformat("2026-10-06T09:00:00+01:00")
AUCTION = datetime.fromisoformat("2026-10-06T11:45:00+01:00")
OPEN = datetime.fromisoformat("2026-10-06T13:00:00+01:00")
NIGHT = datetime.fromisoformat("2026-10-06T23:00:00+01:00")
NEXT_DAY_OPEN = OPEN + timedelta(days=1)
T = "IDC"
ASSET = "SHR-IDC"


def _dicts(db, sql, params=()):
    with db.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def trader(db, name: str, *, cash_naira: int = 0, shares: int = 0, ticker: str = T):
    """A player account with some cash and some shares, for a test."""
    player_id = db.execute(
        "INSERT INTO players (email, email_key, display_name, display_name_key, password_hash, adult_confirmed_at)"
        " VALUES (%s, %s, %s, %s, 'x', now()) RETURNING id",
        (f"{name}@example.com", f"{name}@example.com", name, name)).fetchone()[0]
    account = ledger.create_account(db, kind="player", name="Player account", player_id=player_id)
    if cash_naira:
        ledger.transfer(db, payer=ledger.account_id(db, ledger.TREASURY), receiver=account, amount=naira(cash_naira),
                        kind="test_cash", memo="Test: cash to trade with")
    if shares:
        ledger.transfer(db, payer=ledger.account_id(db, ledger.INVESTORS_PUBLIC), receiver=account, amount=shares,
                        asset=f"SHR-{ticker}", kind="test_shares", memo="Test: shares to trade with")
    return account


def place(db, account, side, quantity, price=None, *, now=OPEN, ticker=T):
    return exchange.place_order(db, account=account, ticker=ticker, side=side, kind="limit" if price else "market",
                                quantity=quantity, limit_price=price, now=now)


def reference(db, ticker=T) -> int:
    return db.execute("SELECT m.reference_price FROM market_instruments m JOIN companies c ON c.id = m.company_id"
                      " WHERE c.ticker = %s", (ticker,)).fetchone()[0]


def sound(db) -> None:
    """Nothing made, nothing lost, and the exchange holds exactly what its open orders say."""
    assert exchange.check_books(db) == []
    assert ledger.audit(db) == []
    assert ledger.amount_in_existence(db) == money_accounted_for(db)


# ---------------------------------------------------------------------------
# The stage test, as far as this slice goes: two players trade a share
# ---------------------------------------------------------------------------

def test_two_players_trade_a_share_and_everything_that_moves_is_in_the_ledger(db):
    seller = trader(db, "seller", shares=1_000)
    buyer = trader(db, "buyer", cash_naira=100_000)
    price = reference(db)
    issued = ledger.amount_in_existence(db, ASSET)
    treasury, fees = ledger.account_id(db, ledger.TREASURY), ledger.account_id(db, exchange.FEES)
    treasury_before = ledger.balance(db, treasury)

    waiting = place(db, seller, "sell", 600, price)
    assert waiting["order"]["status"] == "open" and waiting["trades"] == []
    assert ledger.balance(db, seller, ASSET) == 400                       # the 600 on offer are held by the exchange

    bought = place(db, buyer, "buy", 250, price)
    assert bought["order"]["status"] == "filled" and len(bought["trades"]) == 1
    value = price * 250
    fee = exchange.fee_due(value)
    assert fee == value * 50 // 10_000                                    # half a percent, each side
    assert ledger.balance(db, buyer, ASSET) == 250
    assert ledger.balance(db, buyer) == naira(100_000) - value - fee
    assert ledger.balance(db, seller) == value - fee
    # Fees: three fifths to the exchange, two fifths to the Government as stamp duty.
    assert ledger.balance(db, fees) == 2 * (fee - fee * 20 // 50)
    assert ledger.balance(db, treasury) - treasury_before == 2 * (fee * 20 // 50)
    # The trade is on record, with the ledger transaction that settled it.
    trade = _dicts(db, "SELECT * FROM market_trades")[0]
    assert (trade["price"], trade["quantity"], trade["buyer_account_id"], trade["seller_account_id"]) == (price, 250, buyer, seller)
    assert (trade["buyer_fee"], trade["seller_fee"], trade["same_owner"], trade["in_auction"]) == (fee, fee, False, False)
    moved = _dicts(db, "SELECT account_id, asset, amount FROM ledger_entries WHERE transaction_id = %s", (trade["ledger_transaction"],))
    assert sum(m["amount"] for m in moved if m["asset"] == "NGN") == 0 and sum(m["amount"] for m in moved if m["asset"] == ASSET) == 0
    # No share was made or lost, and the share's last price is the trade's.
    assert ledger.amount_in_existence(db, ASSET) == issued
    assert exchange.quote(db, T, OPEN)["last_price"] == price
    sound(db)


def test_buying_pressure_raises_the_price_and_selling_pressure_lowers_it(db):
    maker = trader(db, "maker", cash_naira=10_000_000, shares=10_000)
    eager = trader(db, "eager", cash_naira=10_000_000, shares=5_000)
    base = reference(db)
    for step in range(1, 6):                                              # sellers wait at rising prices, buyers at falling ones
        place(db, maker, "sell", 100, base + 10 * step)
        place(db, maker, "buy", 100, base - 10 * step)

    bought = place(db, eager, "buy", 450)                                 # "at the best price available"
    prices = [t["price"] for t in bought["trades"]]
    assert prices == [base + 10, base + 20, base + 30, base + 40, base + 50]      # cheapest seller first, then dearer
    assert [t["quantity"] for t in bought["trades"]] == [100, 100, 100, 100, 50]
    assert exchange.quote(db, T, OPEN)["last_price"] == base + 50                 # the price has risen

    sold = place(db, eager, "sell", 300)
    assert [t["price"] for t in sold["trades"]] == [base - 10, base - 20, base - 30]
    assert exchange.quote(db, T, OPEN)["last_price"] == base - 30                 # and fallen
    sound(db)


# ---------------------------------------------------------------------------
# The engine itself, checked against a plain re-statement of the rules
# ---------------------------------------------------------------------------

def _by_the_rules(side, limit, quantity, book, low, high):
    usable = [o for o in book if low <= o["limit_price"] <= high]
    usable.sort(key=lambda o: (o["limit_price"] if side == "buy" else -o["limit_price"], o["id"]))
    fills, left = [], quantity
    for o in usable:
        ok = limit is None or (o["limit_price"] <= limit if side == "buy" else o["limit_price"] >= limit)
        if not ok or left == 0:
            break
        take = min(left, o["remaining"])
        fills.append({"order_id": o["id"], "price": o["limit_price"], "quantity": take})
        left -= take
    return fills, left


def test_the_engine_agrees_with_the_rules_on_a_thousand_random_books():
    rng = random.Random(4)
    for _ in range(1000):
        book = [{"id": i, "limit_price": rng.randint(850, 1150), "remaining": rng.randint(1, 500)}
                for i in rng.sample(range(1, 10_000), rng.randint(0, 40))]
        side = rng.choice(["buy", "sell"])
        limit = rng.choice([None, rng.randint(900, 1100)])
        quantity = rng.randint(1, 5_000)
        assert exchange.engine.match(side, limit, quantity, book, 900, 1100) == _by_the_rules(side, limit, quantity, book, 900, 1100)


def test_the_opening_auction_never_gives_anybody_a_worse_price_than_they_asked(db):
    rng = random.Random(9)
    for _ in range(300):
        orders = [{"id": i, "side": rng.choice(["buy", "sell"]), "limit_price": rng.randint(880, 1120), "remaining": rng.randint(1, 300)}
                  for i in range(1, rng.randint(2, 30))]
        price, pairs = exchange.engine.uncross(orders, 900, 1100, 1000)
        by_id = {o["id"]: o for o in orders}
        traded: dict = {}
        for pair in pairs:
            buy, sell = by_id[pair["buy_id"]], by_id[pair["sell_id"]]
            assert buy["side"] == "buy" and sell["side"] == "sell" and pair["quantity"] > 0
            assert sell["limit_price"] <= price <= buy["limit_price"] and 900 <= price <= 1100
            for order in (buy, sell):
                traded[order["id"]] = traded.get(order["id"], 0) + pair["quantity"]
        assert all(amount <= by_id[i]["remaining"] for i, amount in traded.items())
        # No other single price would have traded more shares.
        def volume(p):
            demand = sum(o["remaining"] for o in orders if o["side"] == "buy" and 900 <= o["limit_price"] <= 1100 and o["limit_price"] >= p)
            supply = sum(o["remaining"] for o in orders if o["side"] == "sell" and 900 <= o["limit_price"] <= 1100 and o["limit_price"] <= p)
            return min(demand, supply)
        best = max((volume(p) for p in range(900, 1101)), default=0)
        assert sum(pair["quantity"] for pair in pairs) == best


def test_the_engine_starts_again_by_itself_if_it_stops():
    book = [{"id": 1, "limit_price": 1000, "remaining": 10}]
    assert exchange.engine.match("buy", None, 5, book, 900, 1100)[1] == 0
    exchange.engine._process.kill()
    exchange.engine._process.wait()
    assert exchange.engine.match("buy", None, 5, book, 900, 1100) == ([{"order_id": 1, "price": 1000, "quantity": 5}], 0)


def test_the_engine_refuses_nonsense_and_carries_on():
    with pytest.raises(exchange.EngineFailure):
        exchange.engine.match("buy", None, 0, [], 900, 1100)
    with pytest.raises(exchange.EngineFailure):
        exchange.engine.match("buy", None, 5, [{"id": 1, "limit_price": -4, "remaining": 10}], 900, 1100)
    with pytest.raises(exchange.EngineFailure):
        exchange.engine._ask("MATCH B - 10 900 1100 2\n1 1000 ten 1\n2 1000 10 2\n")     # one bad line: the whole request is refused
    assert exchange.engine.match("buy", None, 5, [{"id": 1, "limit_price": 1000, "remaining": 10}], 900, 1100)[1] == 0


def test_a_wrong_answer_from_the_engine_is_never_acted_on(db, monkeypatch):
    """The server checks every pairing the engine proposes. If the engine were ever wrong
    (or tampered with), nothing is traded and nothing is left half-done."""
    seller = trader(db, "seller", shares=1_000)
    buyer = trader(db, "buyer", cash_naira=1_000_000)
    price = reference(db)
    resting = place(db, seller, "sell", 100, price)["order"]["id"]
    before = (ledger.balance(db, buyer), ledger.balance(db, seller, ASSET))
    lies = [
        [{"order_id": resting, "price": price, "quantity": 500}],              # more than the waiting order holds
        [{"order_id": resting, "price": price - 100, "quantity": 50}],         # not the waiting order's price
        [{"order_id": resting + 999, "price": price, "quantity": 50}],         # an order that does not exist
        [{"order_id": resting, "price": price, "quantity": 30}] * 2,           # the same order twice
        [{"order_id": resting, "price": price, "quantity": -5}],
    ]
    for lie in lies:
        monkeypatch.setattr(exchange.engine, "match", lambda *a, lie=lie, **k: (lie, 0))
        with pytest.raises(exchange.EngineFailure):
            place(db, buyer, "buy", 60, price)
        assert (ledger.balance(db, buyer), ledger.balance(db, seller, ASSET)) == before
        assert db.execute("SELECT count(*) FROM market_trades").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM market_orders").fetchone()[0] == 1
        sound(db)


# ---------------------------------------------------------------------------
# Reserving: the same cash or shares can never be promised twice
# ---------------------------------------------------------------------------

def test_cash_and_shares_are_held_while_an_order_waits_and_handed_back_when_it_is_cancelled(db):
    account = trader(db, "ada", cash_naira=50_000, shares=500)
    price = reference(db)
    cost = price * 1_000 + exchange.fee_due(price * 1_000)

    buy = place(db, account, "buy", 1_000, price)["order"]
    assert buy["reserved"] == cost and ledger.balance(db, account) == naira(50_000) - cost
    sell = place(db, account, "sell", 500, price + 100)["order"]
    assert ledger.balance(db, account, ASSET) == 0

    # The same cash cannot back a second order, nor the same shares a second sale.
    with pytest.raises(exchange.ExchangeError, match="do not have enough cash"):
        place(db, account, "buy", 2_000, price)
    with pytest.raises(exchange.ExchangeError, match="do not own that many shares"):
        place(db, account, "sell", 1, price + 100)
    sound(db)

    exchange.cancel_order(db, account=account, order_id=buy["id"], now=OPEN)
    exchange.cancel_order(db, account=account, order_id=sell["id"], now=OPEN)
    assert ledger.balance(db, account) == naira(50_000) and ledger.balance(db, account, ASSET) == 500
    assert ledger.balance(db, ledger.account_id(db, exchange.ESCROW)) == 0
    with pytest.raises(exchange.ExchangeError, match="no longer waiting"):
        exchange.cancel_order(db, account=account, order_id=buy["id"], now=OPEN)       # not twice
    assert ledger.balance(db, account) == naira(50_000)
    sound(db)


def test_a_buyer_who_pays_less_than_their_limit_gets_the_difference_back_at_once(db):
    seller = trader(db, "seller", shares=1_000)
    buyer = trader(db, "buyer", cash_naira=1_000_000)
    price = reference(db)
    place(db, seller, "sell", 100, price)
    bought = place(db, buyer, "buy", 300, price + 150)                    # willing to pay more than the seller asks
    assert [(t["price"], t["quantity"]) for t in bought["trades"]] == [(price, 100)]      # trades at the WAITING order's price
    still_wanted = (price + 150) * 200
    paid = price * 100
    order = bought["order"]
    # The exchange keeps only what the 200 shares still wanted could cost, with their fee.
    assert order["reserved"] == still_wanted + exchange.fee_due(paid + still_wanted) - exchange.fee_due(paid)
    assert ledger.balance(db, buyer) == naira(1_000_000) - paid - exchange.fee_due(paid) - order["reserved"]
    sound(db)


def test_splitting_a_trade_into_many_small_ones_does_not_make_the_fee_smaller(db):
    seller = trader(db, "seller", shares=10_000)
    one = trader(db, "one", cash_naira=1_000_000)
    many = trader(db, "many", cash_naira=1_000_000)
    price = reference(db) + 7                                             # an awkward price, so that fees round
    place(db, seller, "sell", 2_000, price)
    place(db, one, "buy", 999, price)
    for _ in range(999):
        place(db, many, "buy", 1, price)
    assert ledger.balance(db, many) <= ledger.balance(db, one)            # 999 single shares cost at least as much as one order of 999
    # The seller's one order was filled in a thousand pieces and paid exactly the fee on the whole.
    order = _dicts(db, "SELECT * FROM market_orders WHERE account_id = %s", (seller,))[0]
    assert order["fees_paid"] == exchange.fee_due(order["value_filled"])
    sound(db)


# ---------------------------------------------------------------------------
# The order book's rules
# ---------------------------------------------------------------------------

def test_best_price_first_then_first_come_first_served(db):
    a, b, c = (trader(db, name, shares=1_000) for name in ("a", "b", "c"))
    buyer = trader(db, "buyer", cash_naira=10_000_000)
    price = reference(db)
    place(db, a, "sell", 100, price + 20)
    place(db, b, "sell", 100, price)
    place(db, c, "sell", 100, price)                                      # the same price as b, but later
    bought = place(db, buyer, "buy", 250, price + 20)
    assert [(t["seller_account_id"], t["price"], t["quantity"]) for t in bought["trades"]] == \
           [(b, price, 100), (c, price, 100), (a, price + 20, 50)]
    sound(db)


def test_an_order_at_the_best_price_available_takes_what_there_is_and_the_rest_is_handed_back(db):
    seller = trader(db, "seller", shares=1_000)
    buyer = trader(db, "buyer", cash_naira=1_000_000)
    price = reference(db)
    place(db, seller, "sell", 100, price)
    bought = place(db, buyer, "buy", 400)
    assert (bought["order"]["status"], bought["order"]["remaining"]) == ("cancelled", 300)
    assert "No more shares were on offer" in bought["order"]["closed_reason"]
    assert ledger.balance(db, buyer) == naira(1_000_000) - price * 100 - exchange.fee_due(price * 100)
    assert ledger.balance(db, ledger.account_id(db, exchange.ESCROW)) == 0
    # With nobody selling at all, the whole order is handed back.
    nothing = place(db, buyer, "buy", 10)
    assert nothing["trades"] == [] and nothing["order"]["status"] == "cancelled"
    sound(db)


def test_trading_with_yourself_is_allowed_recorded_and_costs_fees_twice(db):
    """Making a share look busier than it is harms other players, not the game. It is left
    possible, written down for the law stages, and it is never free."""
    account = trader(db, "solo", cash_naira=1_000_000, shares=1_000)
    price = reference(db)
    place(db, account, "sell", 500, price)
    place(db, account, "buy", 500, price)
    trade = _dicts(db, "SELECT * FROM market_trades")[0]
    assert trade["same_owner"] is True
    assert ledger.balance(db, account, ASSET) == 1_000
    assert ledger.balance(db, account) == naira(1_000_000) - 2 * exchange.fee_due(price * 500)
    sound(db)


# ---------------------------------------------------------------------------
# The daily price limit
# ---------------------------------------------------------------------------

def test_nothing_can_be_ordered_or_traded_more_than_a_tenth_from_yesterdays_last_price(db):
    seller = trader(db, "seller", shares=100_000)
    buyer = trader(db, "buyer", cash_naira=50_000_000)
    base = reference(db)
    low, high = exchange.price_limits(base)
    assert (low, high) == (base - base // 10, base + base // 10)
    for price in (high + 1, low - 1, base * 3, 1):
        with pytest.raises(exchange.ExchangeError, match="can trade only between"):
            place(db, seller, "sell", 10, price)
        with pytest.raises(exchange.ExchangeError, match="can trade only between"):
            place(db, buyer, "buy", 10, price)
    # However much a buyer wants, the price cannot be driven past the limit in one day.
    place(db, seller, "sell", 1_000, high)
    place(db, buyer, "buy", 5_000)
    assert exchange.quote(db, T, OPEN)["last_price"] == high
    with pytest.raises(exchange.ExchangeError):
        place(db, buyer, "buy", 10, high + 1)

    # Next day, the limits are measured from where the price finished.
    place(db, seller, "sell", 10, exchange.price_limits(high)[1], now=NEXT_DAY_OPEN)
    quote = exchange.quote(db, T, NEXT_DAY_OPEN)
    assert quote["reference_price"] == high and (quote["lowest_today"], quote["highest_today"]) == exchange.price_limits(high)
    sound(db)


def test_an_old_order_now_outside_the_limits_cannot_trade_today(db):
    seller = trader(db, "seller", shares=10_000)
    hopeful = trader(db, "hopeful", shares=10_000)
    buyer = trader(db, "buyer", cash_naira=50_000_000)
    base = reference(db)
    low, high = exchange.price_limits(base)
    dear = place(db, hopeful, "sell", 100, high)["order"]                  # asks the day's highest price; nobody pays it
    place(db, buyer, "buy", 100, low)
    place(db, seller, "sell", 100, low)                                    # the price finishes the day at the lower limit
    assert exchange.quote(db, T, OPEN)["last_price"] == low

    low2, high2 = exchange.price_limits(low)
    assert dear["limit_price"] > high2                                     # yesterday's offer is above today's upper limit
    wanted = place(db, buyer, "buy", 50, now=NEXT_DAY_OPEN)                # a buyer at the best price available
    assert wanted["trades"] == [] and wanted["order"]["status"] == "cancelled"
    assert exchange.quote(db, T, NEXT_DAY_OPEN)["offers"] == []            # and it is not shown as on offer today
    assert db.execute("SELECT status FROM market_orders WHERE id = %s", (dear["id"],)).fetchone()[0] == "open"   # it waits
    sound(db)


# ---------------------------------------------------------------------------
# Market hours and the opening auction
# ---------------------------------------------------------------------------

def test_orders_placed_while_the_market_is_closed_wait_for_the_opening_auction(db):
    seller = trader(db, "seller", shares=10_000)
    buyer = trader(db, "buyer", cash_naira=10_000_000)
    price = reference(db)
    for moment in (CLOSED_MORNING, AUCTION):
        assert place(db, seller, "sell", 100, price, now=moment)["trades"] == []
        waiting = place(db, buyer, "buy", 100, price + 20, now=moment)       # these two would trade at once if the market were open
        assert waiting["trades"] == [] and waiting["order"]["status"] == "open"
        with pytest.raises(exchange.ExchangeError, match="only be placed while the market is open"):
            place(db, buyer, "buy", 10, now=moment)
    assert db.execute("SELECT count(*) FROM market_trades").fetchone()[0] == 0
    assert exchange.quote(db, T, AUCTION)["state"] == "opening_auction"

    exchange.open_market(db, OPEN)                                           # the market opens: the auction runs
    trades = _dicts(db, "SELECT * FROM market_trades ORDER BY id")
    assert sum(t["quantity"] for t in trades) == 200 and all(t["in_auction"] for t in trades)
    assert len({t["price"] for t in trades}) == 1                            # everybody in the auction trades at ONE price
    assert price <= trades[0]["price"] <= price + 20
    exchange.open_market(db, OPEN + timedelta(minutes=5))                    # and it runs once a day, not again
    assert db.execute("SELECT count(*) FROM market_trades").fetchone()[0] == len(trades)
    sound(db)


def test_the_auction_also_runs_when_the_first_order_of_the_day_arrives(db):
    seller = trader(db, "seller", shares=10_000)
    buyer = trader(db, "buyer", cash_naira=10_000_000)
    late = trader(db, "late", cash_naira=10_000_000)
    price = reference(db)
    place(db, seller, "sell", 100, price, now=CLOSED_MORNING)
    place(db, buyer, "buy", 100, price, now=CLOSED_MORNING)
    # Nobody has called the market open, but an order arrives after 12:00: the auction is settled first.
    result = place(db, late, "buy", 10, price, now=OPEN)
    assert result["trades"] == [] and ledger.balance(db, buyer, ASSET) == 100
    sound(db)


def test_an_order_placed_after_the_close_belongs_to_the_next_day(db):
    seller = trader(db, "seller", shares=10_000)
    buyer = trader(db, "buyer", cash_naira=10_000_000)
    base = reference(db)
    high = exchange.price_limits(base)[1]
    place(db, seller, "sell", 10, high)
    place(db, buyer, "buy", 10, high)                                        # today's last price: the upper limit
    tomorrow_high = exchange.price_limits(high)[1]
    assert tomorrow_high > high
    # At night, an order may already use tomorrow's limits.
    assert place(db, seller, "sell", 10, tomorrow_high, now=NIGHT)["order"]["status"] == "open"
    assert exchange.session_of(NIGHT)[0] == exchange.session_of(NEXT_DAY_OPEN)[0] != exchange.session_of(OPEN)[0]
    sound(db)


def test_an_order_unmatched_for_seven_days_is_handed_back(db):
    account = trader(db, "patient", cash_naira=100_000, shares=100)
    price = reference(db)
    low, high = exchange.price_limits(price)
    place(db, account, "buy", 10, low)
    place(db, account, "sell", 10, high)
    exchange.open_market(db, OPEN + timedelta(days=6))
    assert db.execute("SELECT count(*) FROM market_orders WHERE status = 'open'").fetchone()[0] == 2
    exchange.open_market(db, OPEN + timedelta(days=8))
    closed = _dicts(db, "SELECT status, closed_reason, reserved FROM market_orders")
    assert all(o["status"] == "expired" and "7 days" in o["closed_reason"] and o["reserved"] == 0 for o in closed)
    assert ledger.balance(db, account) == naira(100_000) and ledger.balance(db, account, ASSET) == 100
    sound(db)


# ---------------------------------------------------------------------------
# The loophole check (design document, section 19)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("bad", [
    {"quantity": 0}, {"quantity": -5}, {"quantity": 2.5}, {"quantity": True}, {"quantity": "100"},
    {"limit_price": 0}, {"limit_price": -1}, {"limit_price": 12.5}, {"side": "steal"}, {"kind": "free"},
])
def test_orders_with_impossible_figures_are_refused(db, bad):
    account = trader(db, "ada", cash_naira=100_000, shares=100)
    order = {"account": account, "ticker": T, "side": "buy", "kind": "limit", "quantity": 10, "limit_price": reference(db), "now": OPEN}
    with pytest.raises(exchange.ExchangeError):
        exchange.place_order(db, **{**order, **bad})
    assert db.execute("SELECT count(*) FROM market_orders").fetchone()[0] == 0
    sound(db)


def test_who_may_trade_and_how_much(db):
    account = trader(db, "ada", cash_naira=10_000_000, shares=100)
    price = reference(db)
    with pytest.raises(exchange.ExchangeError, match="no share with that code"):
        place(db, account, "buy", 1, price, ticker="ZZZ")
    in_issue = ledger.amount_in_existence(db, ASSET)
    with pytest.raises(exchange.ExchangeError, match="more shares than the company has in issue"):
        place(db, account, "buy", in_issue + 1, price)
    # A company, the Treasury and the exchange itself cannot place orders.
    for outsider in ("company:IDC", ledger.TREASURY, exchange.FEES, ledger.CENTRAL_BANK):
        with pytest.raises(exchange.ExchangeError, match="cannot trade"):
            place(db, ledger.account_id(db, outsider), "buy", 1, price)
    # One player may keep at most fifty orders waiting.
    low = exchange.price_limits(price)[0]
    for _ in range(data.MOST_OPEN_ORDERS):
        place(db, account, "buy", 1, low)
    with pytest.raises(exchange.ExchangeError, match="already have 50 orders waiting"):
        place(db, account, "buy", 1, low)
    sound(db)


def test_only_whoever_placed_an_order_can_cancel_it(db):
    ada = trader(db, "ada", cash_naira=100_000)
    eve = trader(db, "eve", cash_naira=100_000)
    order = place(db, ada, "buy", 10, reference(db))["order"]
    with pytest.raises(exchange.ExchangeError, match="You have no order with that number"):
        exchange.cancel_order(db, account=eve, order_id=order["id"], now=OPEN)
    with pytest.raises(exchange.ExchangeError, match="You have no order with that number"):
        exchange.cancel_order(db, account=ada, order_id=order["id"] + 12345, now=OPEN)
    assert db.execute("SELECT status FROM market_orders").fetchone()[0] == "open"
    sound(db)


def test_an_order_cannot_be_altered_and_a_trade_cannot_be_rewritten(db):
    seller = trader(db, "seller", shares=1_000)
    buyer = trader(db, "buyer", cash_naira=1_000_000)
    price = reference(db)
    place(db, seller, "sell", 100, price)
    place(db, buyer, "buy", 40, price)
    for change, rule in (
        ("quantity = 1000000", "market_orders_fixed"), ("limit_price = 1", "market_orders_fixed"),
        (f"account_id = '{buyer}'", "market_orders_fixed"),
        ("side = 'buy'", "market_orders_fixed"), ("remaining = remaining + 50", "market_orders_forwards"),
        ("fees_paid = 0", "market_orders_forwards"), ("value_filled = 0", "market_orders_forwards"),
    ):
        with pytest.raises(errors.Error) as refused:
            db.execute(f"UPDATE market_orders SET {change} WHERE side = 'sell'")         # noqa: S608 (fixed text)
        if rule:
            assert refused.value.diag.constraint_name == rule, change
    with pytest.raises(errors.Error):
        db.execute("UPDATE market_orders SET remaining = 5 WHERE status = 'filled'")      # a closed order never changes
    with pytest.raises(errors.Error):
        db.execute("UPDATE market_orders SET reserved = reserved + 100000 WHERE side = 'buy'")
    for statement in ("DELETE FROM market_orders", "TRUNCATE market_orders CASCADE", "DELETE FROM market_trades",
                      "UPDATE market_trades SET price = 1", "TRUNCATE market_trades"):
        with pytest.raises(errors.Error):
            db.execute(statement)
    sound(db)


def test_two_buyers_at_the_same_instant_cannot_both_take_the_same_shares(db, connect):
    seller = trader(db, "seller", shares=1_000)
    buyers = [trader(db, f"buyer{n}", cash_naira=1_000_000) for n in range(6)]
    price = reference(db)
    place(db, seller, "sell", 100, price)
    start = threading.Barrier(len(buyers))
    results: list = []

    def rush(account):
        conn = connect()
        start.wait()
        results.append(place(conn, account, "buy", 100))

    threads = [threading.Thread(target=rush, args=(account,)) for account in buyers]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sum(t["quantity"] for r in results for t in r["trades"]) == 100            # the 100 shares were sold once
    assert sum(ledger.balance(db, account, ASSET) for account in buyers) == 100
    assert ledger.balance(db, seller) == price * 100 - exchange.fee_due(price * 100)
    sound(db)


def test_one_player_at_the_same_instant_cannot_spend_the_same_cash_twice(db, connect):
    account = trader(db, "ada", cash_naira=10_000)
    price = reference(db)
    quantity = naira(10_000) // (price + price // 100)                                  # nearly all their cash
    start = threading.Barrier(5)
    outcomes: list = []

    def rush(ticker):
        conn = connect()
        start.wait()
        try:
            place(conn, account, "buy", quantity, reference(conn, ticker), ticker=ticker)
            outcomes.append("placed")
        except exchange.ExchangeError:
            outcomes.append("refused")

    tickers = [t for (t,) in db.execute("SELECT ticker FROM companies ORDER BY ticker LIMIT 5").fetchall()]
    prices = {t: reference(db, t) for t in tickers}
    affordable = sum(1 for _ in range(1))                                               # only one such order can be afforded
    threads = [threading.Thread(target=rush, args=(t,)) for t in tickers]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    held = db.execute("SELECT coalesce(sum(reserved), 0) FROM market_orders WHERE status = 'open'").fetchone()[0]
    assert held <= naira(10_000) and ledger.balance(db, account) == naira(10_000) - held >= 0
    assert outcomes.count("placed") >= affordable and "refused" in outcomes and prices
    sound(db)


def test_a_thousand_random_orders_leave_every_naira_and_every_share_accounted_for(db):
    rng = random.Random(11)
    accounts = [trader(db, f"t{n}", cash_naira=2_000_000, shares=20_000) for n in range(6)]
    in_issue = ledger.amount_in_existence(db, ASSET)
    held = ledger.account_id(db, exchange.ESCROW)
    others = db.execute("SELECT sum(balance) FROM ledger_balances WHERE asset = %s AND balance > 0 AND account_id <> ALL(%s)",
                        (ASSET, accounts + [held])).fetchone()[0]
    now = OPEN
    for step in range(1_000):
        now += timedelta(seconds=20)
        account = rng.choice(accounts)
        low, high = exchange.price_limits(reference(db))
        try:
            if rng.random() < 0.15:
                mine = _dicts(db, "SELECT id FROM market_orders WHERE account_id = %s AND status = 'open'", (account,))
                if mine:
                    exchange.cancel_order(db, account=account, order_id=rng.choice(mine)["id"], now=now)
            else:
                price = None if rng.random() < 0.2 else rng.randint(low, high)
                place(db, account, rng.choice(["buy", "sell"]), rng.randint(1, 400), price, now=now)
        except exchange.ExchangeError:
            pass                                                         # short of cash or shares, or too many orders: all fine
        if step % 100 == 0:
            sound(db)
    sound(db)
    # Every share is with a trader, held by the exchange for a sell order, or where it was before.
    with_traders = sum(ledger.balance(db, a, ASSET) for a in accounts) + ledger.balance(db, held, ASSET)
    assert with_traders == 6 * 20_000 and ledger.amount_in_existence(db, ASSET) == in_issue
    assert db.execute("SELECT sum(balance) FROM ledger_balances WHERE asset = %s AND balance > 0 AND account_id <> ALL(%s)",
                      (ASSET, accounts + [held])).fetchone()[0] == others
    # The traders' cash only ever went to each other, the exchange's fees and stamp duty.
    fees = db.execute("SELECT coalesce(sum(buyer_fee + seller_fee), 0) FROM market_trades").fetchone()[0]
    assert sum(ledger.balance(db, a) for a in accounts) + ledger.balance(db, held) == 6 * naira(2_000_000) - fees
    assert db.execute("SELECT count(*) FROM market_trades").fetchone()[0] > 100
    # Cancel everything: the exchange is left holding nothing.
    for order in _dicts(db, "SELECT id, account_id FROM market_orders WHERE status = 'open'"):
        exchange.cancel_order(db, account=order["account_id"], order_id=order["id"], now=now)
    assert ledger.balance(db, held) == 0 and ledger.balance(db, held, ASSET) == 0
    sound(db)


def test_a_quarter_still_closes_with_orders_waiting_and_trades_made(db):
    seller = trader(db, "seller", shares=1_000)
    buyer = trader(db, "buyer", cash_naira=1_000_000)
    price = reference(db)
    place(db, seller, "sell", 100, price)
    place(db, buyer, "buy", 40, price)
    place(db, buyer, "buy", 40, price - 50)
    held = ledger.account_id(db, exchange.ESCROW)
    cash_held = ledger.balance(db, held)
    assert quarters.close_due_quarters(db, after_quarters(2)) == [1, 2]
    sound(db)
    # The dividend on shares held for a sell order goes to whoever is selling them, not to the
    # exchange; and a player who owns shares is paid dividends like any other owner.
    assert ledger.balance(db, held) == cash_held
    paid = dict(db.execute(
        "SELECT e.account_id, sum(e.amount) FROM ledger_entries e JOIN ledger_transactions t ON t.id = e.transaction_id"
        " WHERE t.kind = 'dividend' AND e.amount > 0 AND e.account_id = ANY(%s) GROUP BY 1", ([seller, buyer, held],)).fetchall())
    assert held not in paid and paid[seller] > 0 and paid[buyer] > 0
    assert paid[seller] * 40 // 960 == paid[buyer] or abs(paid[seller] * 40 - paid[buyer] * 960) <= 960 * 4    # in proportion: 960 shares to 40
    # If the exchange's holdings ever stopped matching its open orders, the quarter would refuse to close.
    assert exchange.check_books(db) == []


# ---------------------------------------------------------------------------
# Through the website's door
# ---------------------------------------------------------------------------

@pytest.fixture
def trading_hours(monkeypatch):
    from server import main
    monkeypatch.setattr(main, "_exchange_time", lambda conn: OPEN)


def _second_player(client):
    from fastapi.testclient import TestClient

    from server.main import app
    other = TestClient(app)
    answer = join(other, {**ADULT, "email": "bola@example.com", "display_name": "Bola"})
    assert answer.status_code == 201, answer.text
    return other


def test_two_players_trade_through_the_website(client, player, db, trading_hours):
    other = _second_player(client)
    bola = db.execute("SELECT a.id FROM ledger_accounts a JOIN players p ON p.id = a.player_id WHERE p.display_name = 'Bola'").fetchone()[0]
    ledger.transfer(db, payer=ledger.account_id(db, ledger.INVESTORS_PUBLIC), receiver=bola, amount=500, asset=ASSET,
                    kind="test_shares", memo="Test: shares to trade with")
    quote = client.get(f"/api/market/{T}").json()
    price = int(quote["reference_price_kobo"])
    assert quote["market_state"] == "open" and quote["last_price_kobo"] is None and quote["fee_bps"] == 50

    offer = other.post("/api/market/orders", json={"ticker": T, "side": "sell", "kind": "limit", "quantity": 200, "limit_price_kobo": price})
    assert offer.status_code == 201 and offer.json()["order"]["status"] == "open"
    assert other.get("/api/market/holdings").json() == [
        {"ticker": T, "name": "Idanre Cement", "shares": 300, "held_for_orders": 200, "price_kobo": str(price), "value_kobo": str(price * 500)}]
    book = client.get(f"/api/market/{T}").json()
    assert book["offers"] == [{"price_kobo": str(price), "quantity": 200, "orders": 1}] and book["bids"] == []

    bought = client.post("/api/market/orders", json={"ticker": T, "side": "buy", "kind": "market", "quantity": 50})
    assert bought.status_code == 201, bought.text
    body = bought.json()
    assert body["order"]["status"] == "filled" and body["trades"][0]["quantity"] == 50
    assert int(client.get("/api/me").json()["cash"]["amount_kobo"]) == naira(500_000) - price * 50 - exchange.fee_due(price * 50)
    assert client.get("/api/market/holdings").json()[0]["shares"] == 50
    assert client.get(f"/api/market/{T}").json()["last_price_kobo"] == str(price)
    sound(db)

    # One player cannot cancel, or even see, another's order.
    order_id = offer.json()["order"]["id"]
    assert client.delete(f"/api/market/orders/{order_id}").status_code == 409
    assert [o["id"] for o in client.get("/api/market/orders").json()] == [body["order"]["id"]]
    assert other.delete(f"/api/market/orders/{order_id}").json()["status"] == "cancelled"
    assert other.get("/api/market/holdings").json()[0]["held_for_orders"] == 0
    # Nothing public says who is behind an order or a trade.
    public = client.get(f"/api/market/{T}").text
    for hidden in ("account", "Bola", "Ada", "buyer", "seller", "same_owner", "order_id"):
        assert hidden not in public
    sound(db)


@pytest.mark.parametrize("body", [
    {"ticker": T, "side": "buy", "kind": "limit", "quantity": 10},                                   # no price
    {"ticker": T, "side": "buy", "kind": "market", "quantity": 10, "limit_price_kobo": 2000},        # a price it should not have
    {"ticker": T, "side": "buy", "kind": "limit", "quantity": -10, "limit_price_kobo": 2000},
    {"ticker": T, "side": "buy", "kind": "limit", "quantity": 0, "limit_price_kobo": 2000},
    {"ticker": T, "side": "buy", "kind": "limit", "quantity": 1.5, "limit_price_kobo": 2000},
    {"ticker": T, "side": "buy", "kind": "limit", "quantity": "10", "limit_price_kobo": 2000},
    {"ticker": T, "side": "buy", "kind": "limit", "quantity": 10**30, "limit_price_kobo": 2000},
    {"ticker": T, "side": "buy", "kind": "limit", "quantity": 10, "limit_price_kobo": -2000},
    {"ticker": T, "side": "buy", "kind": "limit", "quantity": 10, "limit_price_kobo": 10**30},
    {"ticker": "idc", "side": "buy", "kind": "limit", "quantity": 10, "limit_price_kobo": 2000},
    {"ticker": T, "side": "give", "kind": "limit", "quantity": 10, "limit_price_kobo": 2000},
    {"ticker": T, "side": "buy", "kind": "limit", "quantity": 10, "limit_price_kobo": 2000, "account": "someone-else"},
    {"ticker": T, "side": "buy", "kind": "limit", "quantity": 10, "limit_price_kobo": 2000, "reserved": 0},
    {"ticker": T, "side": "sell", "kind": "limit", "quantity": 10, "limit_price_kobo": 2000, "fees_paid": 0, "status": "filled"},
])
def test_a_made_up_order_from_a_browser_is_refused(client, player, db, trading_hours, body):
    assert client.post("/api/market/orders", json=body).status_code == 422
    assert db.execute("SELECT count(*) FROM market_orders").fetchone()[0] == 0


def test_the_markets_pages_refuse_strangers_and_explain_refusals_in_plain_words(client, player, db, trading_hours):
    price = int(client.get(f"/api/market/{T}").json()["reference_price_kobo"])
    cannot_afford = client.post("/api/market/orders", json={"ticker": T, "side": "buy", "kind": "limit", "quantity": 10**9, "limit_price_kobo": price})
    assert cannot_afford.status_code == 409 and "do not have enough cash" in cannot_afford.json()["detail"]
    no_shares = client.post("/api/market/orders", json={"ticker": T, "side": "sell", "kind": "limit", "quantity": 5, "limit_price_kobo": price})
    assert no_shares.status_code == 409 and "do not own that many shares" in no_shares.json()["detail"]
    too_dear = client.post("/api/market/orders", json={"ticker": T, "side": "buy", "kind": "limit", "quantity": 5, "limit_price_kobo": price * 2})
    assert too_dear.status_code == 409 and "can trade only between" in too_dear.json()["detail"]
    assert client.get("/api/market/ZZZ").status_code == 404
    assert client.get("/api/market/zzz;drop").status_code in (404, 422)
    assert client.delete("/api/market/orders/0").status_code == 422
    assert client.delete("/api/market/orders/999999").status_code == 409
    client.cookies.clear()
    for method, path in (("GET", f"/api/market/{T}"), ("GET", "/api/market/orders"), ("GET", "/api/market/holdings"),
                         ("POST", "/api/market/orders"), ("DELETE", "/api/market/orders/1")):
        assert client.request(method, path, json={}).status_code == 401, (method, path)
    sound(db)


def test_the_economy_page_still_accounts_for_every_naira_with_cash_held_at_the_exchange(client, player, db, trading_hours):
    price = int(client.get(f"/api/market/{T}").json()["reference_price_kobo"])
    assert client.post("/api/market/orders", json={"ticker": T, "side": "buy", "kind": "limit", "quantity": 100, "limit_price_kobo": price}).status_code == 201
    body = client.get("/api/economy").json()
    lines = {m["holder"]: int(m["amount_kobo"]) for m in body["money"]}
    assert lines["The exchange"] == price * 100 + exchange.fee_due(price * 100)
    assert sum(lines.values()) == int(body["money_in_existence_kobo"])
