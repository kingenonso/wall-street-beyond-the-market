"""Stage 4, Part A, slice 2: what a company is worth, the computer-run investors, prices
that move for a reason, and the "Why?" record.

The stage test is here: two players trade a share, buying pressure raises the price,
and "Why?" shows the cause.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from psycopg import errors
from psycopg.rows import dict_row

from simulation import economy, exchange, investors, ledger, quarters, valuation
from simulation import world_data as data
from simulation.money import BPS, naira
from tests.conftest import government_budget, after_quarters, money_accounted_for
from tests.test_market import place as _place
from tests.test_market import sound, trader

# The "eight" world's eighth quarter ends on Monday 30 November 2026. The next day, in trading hours:
OPEN = datetime.fromisoformat("2026-12-01T13:00:00+01:00")
BEFORE_OPEN = datetime.fromisoformat("2026-12-01T09:00:00+01:00")
T = "IDC"


def _dicts(db, sql, params=()):
    with db.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def place(db, account, side, quantity, price=None, *, now=OPEN, ticker=T):
    return _place(db, account, side, quantity, price, now=now, ticker=ticker)


def best(db, ticker=T, now=OPEN):
    quote = exchange.quote(db, ticker, now)
    return quote["bids"][0]["price"], quote["offers"][0]["price"]


# ---------------------------------------------------------------------------
# What a company is worth
# ---------------------------------------------------------------------------

def _filed(profit: int, equity: int = 1_000_000_00, shares: int = 1_000, quarters_filed: int = 4, sales: int = 10_000_000_00):
    return [{"period": p, "net_profit": profit if p else 0, "revenue": sales if p else 0, "total_equity": equity,
             "shares_in_issue": shares} for p in range(quarters_filed + 1)]


def test_a_company_is_worth_the_value_today_of_its_future_profits():
    base = valuation.assess(_filed(100_000_00), "BBB", 1300, 600)
    assert base["method"] == "profits" and base["yearly_profit"] == 400_000_00
    # By hand: five years of growth, then growth at the long-run rate for ever, each year counted for less.
    g, r, t = base["growth_bps"] / BPS, base["discount_bps"] / BPS, base["long_run_bps"] / BPS
    profit, total = 400_000_00.0, 0.0
    for year in range(1, 6):
        profit *= 1 + g
        total += profit / (1 + r) ** year
    total += profit * (1 + t) / (r - t) / (1 + r) ** 5
    assert base["value_per_share"] == int(total) // 1_000
    assert (base["growth_bps"], base["discount_bps"], base["long_run_bps"]) == (800, 1300 + 550 + 300, 600)

    more_profit = valuation.assess(_filed(150_000_00), "BBB", 1300, 600)
    dearer_money = valuation.assess(_filed(100_000_00), "BBB", 1600, 600)
    riskier = valuation.assess(_filed(100_000_00), "CCC", 1300, 600)
    safer = valuation.assess(_filed(100_000_00), "AAA", 1300, 600)
    assert more_profit["value_per_share"] > base["value_per_share"] > dearer_money["value_per_share"]
    assert safer["value_per_share"] > base["value_per_share"] > riskier["value_per_share"]


def test_a_loss_maker_is_valued_on_what_is_left_of_its_owners_funds_and_never_below_one_naira():
    losing = valuation.assess(_filed(-50_000_00, equity=1_000_000_00), "CCC", 1300, 600)
    assert losing["method"] == "assets" and losing["value_per_share"] == 1_000_000_00 // 2 // 1_000
    assert valuation.assess(_filed(-50_000_00, equity=-9_000_000_00), "D", 1300, 600)["value_per_share"] == data.LOWEST_LISTING_PRICE_KOBO
    # Before any results are filed there are no profits to go on: it is worth its owners' funds.
    new = valuation.assess(_filed(0, quarters_filed=0), "BBB", 1300, 600)
    assert new["method"] == "assets" and new["value_per_share"] == 1_000_000_00 // 1_000
    # However high the Central Bank's rate or low the rating, the sum never divides by zero or goes negative.
    for rate in (400, 3000):
        for rating in data.LOAN_SPREAD_BPS:
            assert valuation.assess(_filed(100_000_00), rating, rate, -500)["value_per_share"] > 0
    assert valuation.discount_bps(0, "AAA") >= data.INFLATION_TARGET_BPS + data.LEAST_DISCOUNT_ABOVE_GROWTH_BPS


@pytest.mark.world("eight")
def test_every_company_is_valued_at_every_filing_from_public_figures_alone(db):
    assert db.execute("SELECT count(*) FROM company_valuations").fetchone()[0] == 50 * 9
    # Anybody can reach the same figure from the filed reports, the rating, the interest rate and inflation.
    state = _dicts(db, "SELECT next_policy_rate_bps, inflation_bps FROM economy_results WHERE period = 8")[0]
    for company in _dicts(db, "SELECT id, ticker FROM companies ORDER BY ticker"):
        filed = _dicts(
            db,
            "SELECT DISTINCT ON (period) period, credit_rating,"
            " (figures->'income_statement'->>'net_profit')::bigint AS net_profit,"
            " (figures->'income_statement'->>'revenue')::bigint AS revenue,"
            " (figures->'balance_sheet'->>'total_equity')::bigint AS total_equity,"
            " (figures->'notes'->>'shares_in_issue')::bigint AS shares_in_issue"
            " FROM company_reports WHERE company_id = %s ORDER BY period, version DESC", (company["id"],))
        mine = valuation.assess(filed, filed[-1]["credit_rating"], state["next_policy_rate_bps"], state["inflation_bps"])
        stored = _dicts(db, "SELECT * FROM company_valuations WHERE company_id = %s AND period = 8", (company["id"],))[0]
        assert {k: stored[k] for k in mine} == mine, company["ticker"]
    methods = dict(db.execute("SELECT method, count(*) FROM company_valuations WHERE period = 8 GROUP BY 1").fetchall())
    assert methods["profits"] >= 30 and methods.get("assets", 0) >= 3            # the loss-makers are there too
    reasons = [r for (r,) in db.execute("SELECT jsonb_array_elements_text(reasons) FROM company_valuations WHERE period = 8").fetchall()]
    assert any("profit over the past year" in r for r in reasons) and any("credit rating" in r for r in reasons)
    for statement in ("UPDATE company_valuations SET value_per_share = 1", "DELETE FROM company_valuations",
                      "TRUNCATE company_valuations"):
        with pytest.raises(errors.Error):
            db.execute(statement)


# ---------------------------------------------------------------------------
# The computer-run investors
# ---------------------------------------------------------------------------

def test_the_prices_an_investor_quotes():
    bids, offers = investors.ladder(2_000, 50, 3, 1_800, 2_200)
    assert bids == [1_990, 1_980, 1_970] and offers == [2_010, 2_020, 2_030]
    # Nothing outside the day's limits, and a buying price is never at or above a selling price.
    assert investors.ladder(2_195, 50, 3, 1_800, 2_200) == ([2_184, 2_173, 2_162], [])
    assert investors.ladder(1_802, 50, 3, 1_800, 2_200)[0] == []
    for centre in (100, 101, 137, 150, 199):
        bids, offers = investors.ladder(centre, 40, 3, 90, 220)
        assert not bids or not offers or max(bids) < min(offers)
    assert investors.order_value(1) == naira(500_000) and investors.order_value(10**20) == naira(20_000_000)


@pytest.mark.world("eight")
def test_investors_keep_orders_waiting_in_every_share_on_both_sides(db):
    placed = investors.act(db, OPEN)
    assert placed > 500
    worth = valuation.latest(db)
    for share in _dicts(db, "SELECT m.*, c.ticker FROM market_instruments m JOIN companies c ON c.id = m.company_id"):
        quote = exchange.quote(db, share["ticker"], OPEN)
        assert quote["bids"] and quote["offers"], share["ticker"]
        assert quote["bids"][0]["price"] < quote["offers"][0]["price"]              # nothing left crossed
        assert quote["lowest_today"] <= quote["bids"][-1]["price"] and quote["offers"][-1]["price"] <= quote["highest_today"]
        # A share that had never traded was listed at what it is thought to be worth.
        value = worth[share["company_id"]]["value_per_share"]
        if share["last_price"] is None:
            assert share["reference_price"] == value
        assert abs(quote["bids"][0]["price"] - value) <= value * 15 // 100
    # Only the three investors' own shares and cash are behind those orders.
    owners = {a for (a,) in db.execute("SELECT DISTINCT account_id FROM market_orders").fetchall()}
    assert owners == set(investors.accounts(db).values())
    assert db.execute("SELECT count(*) FROM market_trades").fetchone()[0] > 0     # where their views overlapped, they traded
    sound(db)


@pytest.mark.world("eight")
def test_investors_look_again_only_every_five_minutes_and_once_before_the_open(db):
    assert investors.act(db, BEFORE_OPEN) > 0
    assert investors.act(db, BEFORE_OPEN + timedelta(hours=1)) == 0                # before the open, once is enough
    assert db.execute("SELECT count(*) FROM market_trades").fetchone()[0] == 0     # the market is closed: nothing trades
    investors.act(db, OPEN)                                                        # the open: the auction runs
    auction = db.execute("SELECT count(*), count(*) FILTER (WHERE in_auction) FROM market_trades").fetchone()
    assert auction[0] > 0 and auction[0] == auction[1]
    assert investors.act(db, OPEN + timedelta(minutes=2)) == 0                     # too soon to look again
    orders = db.execute("SELECT count(*) FROM market_orders").fetchone()[0]
    investors.act(db, OPEN + timedelta(minutes=6))
    investors.act(db, OPEN + timedelta(minutes=12))
    # With nothing happening they leave their orders where they are: no churn.
    assert db.execute("SELECT count(*) FROM market_orders").fetchone()[0] - orders < 60
    sound(db)


# ---------------------------------------------------------------------------
# THE STAGE TEST: two players trade a share; buying pressure raises the price; "Why?" shows the cause
# ---------------------------------------------------------------------------

@pytest.mark.world("eight")
def test_two_players_trade_buying_pressure_raises_the_price_and_why_shows_the_cause(db):
    investors.act(db, OPEN)
    ada = trader(db, "ada", cash_naira=60_000_000)
    bola = trader(db, "bola", cash_naira=1_000_000)
    bid, offer = best(db)
    assert exchange.why(db, T, OPEN)["move_bps"] in range(-300, 300)

    # 1. Two players trade a share with each other.
    first = place(db, ada, "buy", 1_000, offer)                                     # Ada buys from an investor...
    assert first["order"]["status"] == "filled"
    place(db, ada, "sell", 400, offer - 1)                                          # ...and offers 400 a little cheaper than anyone
    bought = place(db, bola, "buy", 400)                                            # Bola buys at the best price available
    assert [(t["seller_account_id"], t["buyer_account_id"], t["quantity"]) for t in bought["trades"]] == [(ada, bola, 400)]
    assert ledger.balance(db, bola, "SHR-IDC") == 400 and ledger.balance(db, ada, "SHR-IDC") == 600

    # 2. Buying pressure raises the price.
    before = exchange.quote(db, T, OPEN)
    price_before = before["last_price"]
    wave = place(db, ada, "buy", sum(level["quantity"] for level in before["offers"][:3]))     # takes three price levels of offers
    paid = [t["price"] for t in wave["trades"]]
    assert paid == sorted(paid) and paid[-1] > paid[0] >= price_before
    after = exchange.quote(db, T, OPEN)
    assert after["last_price"] == paid[-1] > price_before
    assert after["offers"][0]["price"] >= paid[-1]                                  # the cheap offers are gone

    # 3. "Why?" shows the cause.
    why = exchange.why(db, T, OPEN)
    assert why["move_bps"] > 0 and why["last_price"] == paid[-1]
    assert "more buying than selling" in why["summary"] and f"paying up to ₦{paid[-1] / 100:,.2f}" in why["summary"]
    assert why["bought_in_a_hurry"] > why["sold_in_a_hurry"]

    # 4. And the price stays up: the investors who sold now ask more.
    investors.act(db, OPEN + timedelta(minutes=6))
    later_bid, later_offer = best(db, now=OPEN + timedelta(minutes=6))
    assert later_bid > bid and later_offer > offer
    reasons = exchange.why(db, T, OPEN + timedelta(minutes=6))["reasons"]
    assert any("more shares than they bought today, and raised their prices" in r for r in reasons), reasons
    sound(db)


@pytest.mark.world("eight")
def test_selling_pressure_lowers_the_price_and_why_says_so(db):
    investors.act(db, OPEN)
    seller = trader(db, "seller", shares=3_000_000)
    bid, offer = best(db)
    quote = exchange.quote(db, T, OPEN)
    wave = place(db, seller, "sell", sum(level["quantity"] for level in quote["bids"][:3]))
    assert [t["price"] for t in wave["trades"]] == sorted((t["price"] for t in wave["trades"]), reverse=True)
    why = exchange.why(db, T, OPEN)
    assert why["move_bps"] < 0 and "more selling than buying" in why["summary"]
    investors.act(db, OPEN + timedelta(minutes=6))
    assert best(db, now=OPEN + timedelta(minutes=6))[0] < bid
    assert any("and lowered their prices" in r for r in exchange.why(db, T, OPEN + timedelta(minutes=6))["reasons"])
    sound(db)


# ---------------------------------------------------------------------------
# The loophole check: the investors cannot be milked
# ---------------------------------------------------------------------------

@pytest.mark.world("eight")
@pytest.mark.parametrize("levels, wait_days", [(1, 0), (3, 0), (6, 0), (3, 1), (6, 2), (9, 3)])
def test_pushing_a_price_up_and_selling_back_loses_money(db, levels, wait_days):
    """Loophole question 9. Buy enough to move the investors' prices, let them react, sell it all
    back: at once, or days later after the push has faded. It never pays."""
    investors.act(db, OPEN)
    account = trader(db, "pumper", cash_naira=500_000_000)
    start = ledger.balance(db, account)
    offers = exchange.quote(db, T, OPEN, depth=20)["offers"]
    quantity = sum(level["quantity"] for level in offers[:levels])
    place(db, account, "buy", quantity)
    held = ledger.balance(db, account, "SHR-IDC")
    assert held > 0
    now = OPEN
    for step in range(1, 4):                                                        # the investors react, and react again
        now = OPEN + timedelta(minutes=6 * step)
        investors.act(db, now)
    for day in range(wait_days):
        now = OPEN + timedelta(days=day + 1)
        investors.act(db, now, force=True)
    while ledger.balance(db, account, "SHR-IDC") > 0:                               # sell everything, at whatever the bids are
        left = ledger.balance(db, account, "SHR-IDC")
        sold = place(db, account, "sell", left, now=now)
        if not sold["trades"]:
            now += timedelta(minutes=6)
            investors.act(db, now)
            assert (now - OPEN).days < 12, "could not sell"
    assert ledger.balance(db, account) < start
    sound(db)


@pytest.mark.world("eight")
def test_two_players_trading_with_each_other_at_a_silly_price_do_not_move_the_investors(db):
    """Painting a price. While investors' orders are in the book it cannot be done at all: a buyer
    is always given the cheapest shares on offer first. So the attack is tried when the book is
    empty (as it is for a moment after each quarter's reports): two accounts trade a few shares at
    the day's upper limit. The last price jumps, but the investors go by what the company is worth
    and by what they themselves have sold and bought, never by the last price."""
    investors.act(db, OPEN)
    investors.withdraw_all(db, OPEN)                                                 # the book is empty, as at a quarter's end
    assert exchange.quote(db, T, OPEN)["offers"] == []
    a = trader(db, "a", cash_naira=1_000_000, shares=10_000)
    b = trader(db, "b", cash_naira=1_000_000)
    high = exchange.quote(db, T, OPEN)["highest_today"]
    place(db, a, "sell", 100, high)
    place(db, b, "buy", 100, high)
    assert exchange.quote(db, T, OPEN)["last_price"] == high                         # the last price is painted
    assert investors.act(db, OPEN + timedelta(minutes=1)) > 0                        # back at the very next look, not five minutes on
    value = valuation.latest(db)[db.execute("SELECT id FROM companies WHERE ticker = %s", (T,)).fetchone()[0]]["value_per_share"]
    centres = [c for (c,) in db.execute("SELECT b.centre FROM investor_books b JOIN companies c ON c.id = b.company_id"
                                        " WHERE c.ticker = %s", (T,)).fetchall()]
    assert len(centres) == 3 and all(abs(c - value) <= value * 3 // 100 for c in centres)   # their views sit at its worth
    assert best(db, now=OPEN + timedelta(minutes=1))[0] < value * 102 // 100 < high
    # And with their orders back, a buyer at the upper limit is simply given their cheaper shares.
    cheap = place(db, b, "buy", 100, high, now=OPEN + timedelta(minutes=2))
    assert all(t["price"] < value * 105 // 100 for t in cheap["trades"])
    sound(db)


@pytest.mark.world("eight")
def test_investors_take_their_orders_off_at_the_instant_new_reports_are_filed(db):
    """Loophole question 5: nobody can read the new filings and trade against prices the
    investors set before they had read them."""
    investors.act(db, OPEN)
    assert db.execute("SELECT count(*) FROM market_orders WHERE status = 'open'").fetchone()[0] > 500
    assert quarters.close_due_quarters(db, after_quarters(9)) == [9]
    assert db.execute("SELECT count(*) FROM market_orders WHERE status = 'open'").fetchone()[0] == 0
    assert db.execute("SELECT count(*) FROM company_valuations WHERE period = 9").fetchone()[0] == 50
    held = ledger.account_id(db, exchange.ESCROW)
    assert ledger.balance(db, held) == 0
    # They come back with prices built on the new filings, and "Why?" says so.
    later = after_quarters(9) + timedelta(days=1, hours=12)
    investors.act(db, later, force=True)
    assert set(db.execute("SELECT DISTINCT period FROM investor_books").fetchall()) == {(9,)}
    told = [r for (r,) in db.execute("SELECT reason FROM market_reasons").fetchall()]
    assert any("after the company's Year 3 Q1 results were filed" in r for r in told)
    sound(db)


@pytest.mark.world("eight")
def test_small_investors_react_to_news_that_has_happened_and_never_to_news_still_to_come(db):
    companies = _dicts(db, "SELECT id, ticker, sector, headquarters FROM companies ORDER BY ticker")
    idc = next(c for c in companies if c["ticker"] == T)
    db.execute("INSERT INTO events (period, day, kind, company_id, location, sales_bps) VALUES (9, 40, 'company_strike', %s, 'Lagos', -1500)",
               (idc["id"],))
    before = investors._mood_from_todays_news(db, companies, 9, 39).get(idc["id"], (0, None))
    after = investors._mood_from_todays_news(db, companies, 9, 40)[idc["id"]]
    assert after[0] < before[0] and after[0] >= -data.MOST_EVENT_MOOD_BPS            # marked down, by no more than 3%
    assert after[1] == "company_strike"
    assert investors._mood_from_todays_news(db, companies, 9, 0) == {}               # nothing has happened yet on day 0
    # Other companies are untouched by it.
    others_before = {k: v for k, v in investors._mood_from_todays_news(db, companies, 9, 39).items() if k != idc["id"]}
    others_after = {k: v for k, v in investors._mood_from_todays_news(db, companies, 9, 40).items() if k != idc["id"]}
    assert others_before == others_after


@pytest.mark.world("eight")
def test_nothing_about_an_investors_own_view_reaches_a_player(db, client, player, monkeypatch):
    from server import main
    monkeypatch.setattr(main, "_exchange_time", lambda conn: OPEN)
    investors.act(db, OPEN)
    for path in (f"/api/market/{T}", f"/api/market/{T}/why", "/api/market/orders", "/api/market/holdings", "/api/economy"):
        text = client.get(path).text
        for hidden in ("centre", "carried", "own_view", "fortune", "investor_books", "account_id", "seed"):
            assert hidden not in text, (path, hidden)
    why = client.get(f"/api/market/{T}/why").json()
    assert why["valuation_label"] == "Year 2 Q4" and isinstance(why["valuation_reasons"], list) and why["summary"]
    assert client.get("/api/market/ZZZ/why").status_code == 404
    client.cookies.clear()
    assert client.get(f"/api/market/{T}/why").status_code == 401


# ---------------------------------------------------------------------------
# The pause after a sharp fall across the whole market
# ---------------------------------------------------------------------------

@pytest.mark.world("eight")
def test_trading_pauses_for_half_an_hour_when_the_whole_market_falls_five_percent(db):
    investors.act(db, OPEN)
    account = trader(db, "ada", cash_naira=10_000_000, shares=10_000)
    waiting = place(db, account, "buy", 10, best(db)[0] - 5)["order"]
    place(db, account, "sell", 5)                                                  # an ordinary trade: no pause
    assert exchange.paused_until(db, OPEN) is None and exchange.market_move_bps(db) > -data.MARKET_PAUSE_FALL_BPS

    # Every share is marked down 9% (as after a morning of heavy selling everywhere).
    db.execute("UPDATE market_instruments SET last_price = reference_price - reference_price * 9 / 100 WHERE company_id <>"
               " (SELECT id FROM companies WHERE ticker = %s)", (T,))
    assert exchange.market_move_bps(db) <= -data.MARKET_PAUSE_FALL_BPS
    assert place(db, account, "sell", 5)["trades"]                                 # the next trade trips the pause
    assert exchange.paused_until(db, OPEN) == OPEN + timedelta(minutes=data.MARKET_PAUSE_MINUTES)

    with pytest.raises(exchange.ExchangeError, match="Trading is paused until 13:30 Lagos time"):
        place(db, account, "buy", 10)
    assert investors.act(db, OPEN + timedelta(minutes=10), force=True) == 0        # the investors wait too
    exchange.cancel_order(db, account=account, order_id=waiting["id"], now=OPEN + timedelta(minutes=5))   # cancelling still works
    told = [r for (r,) in db.execute("SELECT reason FROM market_reasons WHERE company_id IS NULL").fetchall()]
    assert told == ["The whole market fell more than 5% in a day. Trading was paused for 30 minutes so that everybody could take stock."]
    assert "Trading was paused" in " ".join(exchange.why(db, T, OPEN)["reasons"])

    after = OPEN + timedelta(minutes=31)
    assert exchange.paused_until(db, after) is None
    assert place(db, account, "sell", 5, now=after)["trades"]                      # the market is still down, and trades again
    assert exchange.paused_until(db, after) is None                                # at most one pause in a day
    sound(db)


# ---------------------------------------------------------------------------
# Money: fees go round again, and a long run stays sound
# ---------------------------------------------------------------------------

@pytest.mark.world("eight")
def test_stamp_duty_and_the_exchanges_fees_are_spent_by_the_government(db):
    fees = ledger.account_id(db, exchange.FEES)
    treasury = ledger.account_id(db, ledger.TREASURY)
    buyer = trader(db, "buyer", cash_naira=50_000_000)
    reserve = ledger.balance(db, treasury)
    investors.act(db, OPEN)
    place(db, buyer, "buy", 100_000)
    earned = ledger.balance(db, fees)
    assert earned > 0 and ledger.balance(db, treasury) > reserve                    # stamp duty arrives with each trade
    assert quarters.close_due_quarters(db, after_quarters(9)) == [9]
    assert ledger.balance(db, fees) == 0                                           # handed to the Government at the quarter's end
    received = dict(db.execute(
        "SELECT t.kind, sum(e.amount) FROM ledger_entries e JOIN ledger_transactions t ON t.id = e.transaction_id"
        " WHERE e.account_id = %s AND e.amount > 0 AND t.period = 9 GROUP BY 1", (treasury,)).fetchall())
    assert received["exchange_surplus"] == earned and received["share_trade"] > 0
    collected = government_budget(db, 9)
    spent = db.execute(
        "SELECT -sum(e.amount) FROM ledger_entries e JOIN ledger_transactions t ON t.id = e.transaction_id"
        " WHERE e.account_id = %s AND e.amount < 0 AND t.period = 9 AND t.kind IN ('government_purchase', 'government_wages')",
        (treasury,)).fetchone()[0]
    assert collected - 100 <= spent <= collected and ledger.balance(db, treasury) >= reserve - 100
    sound(db)


@pytest.mark.world("eight")
def test_a_year_of_trading_days_and_quarter_ends_leaves_everything_accounted_for(db):
    players = [trader(db, f"p{n}", cash_naira=5_000_000) for n in range(3)]
    for quarter in range(9, 13):
        start = after_quarters(quarter - 1)
        for day in range(1, 6):
            now = start.replace(hour=13, minute=0) + timedelta(days=day)
            investors.act(db, now, force=True)
            for n, account in enumerate(players):                                   # players buy and sell a little each day
                ticker = ["IDC", "OTB", "KTX"][n]
                try:
                    if day % 2:
                        exchange.place_order(db, account=account, ticker=ticker, side="buy", kind="market", quantity=2_000 * (n + 1),
                                             limit_price=None, now=now)
                    elif ledger.balance(db, account, f"SHR-{ticker}") > 0:
                        exchange.place_order(db, account=account, ticker=ticker, side="sell", kind="market",
                                             quantity=ledger.balance(db, account, f"SHR-{ticker}") // 2 + 1, limit_price=None, now=now)
                except exchange.ExchangeError:
                    pass
            investors.act(db, now + timedelta(minutes=6))
        assert quarters.close_due_quarters(db, after_quarters(quarter)) == [quarter]
        sound(db)
    assert db.execute("SELECT count(*) FROM market_trades").fetchone()[0] > 300
    # Nobody went below zero, the investors still have cash and shares, and no price ran away.
    for account in investors.accounts(db).values():
        assert ledger.balance(db, account) > 0
    worth = valuation.latest(db)
    for share in _dicts(db, "SELECT * FROM market_instruments WHERE last_price IS NOT NULL"):
        value = worth[share["company_id"]]["value_per_share"]
        assert value * 4 // 10 <= share["last_price"] <= value * 25 // 10
    assert ledger.amount_in_existence(db) == money_accounted_for(db)
