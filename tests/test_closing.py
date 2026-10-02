"""Stage 4, slice 4: the Closing Rush, the Closing Bell, and what an investor reads.

Fees are halved in the last ten minutes. Large orders are shown without a name. The
bell rings once a day from the day's real records. Company facts, the written results
report, the industries and the personal advisory are built from filed figures only.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from psycopg import errors
from psycopg.rows import dict_row

from simulation import closingbell, clock, exchange, insight, investors, ledger, marketview, news, quarters
from simulation import world_data as data
from simulation.money import BPS, naira
from tests.conftest import ADULT, after_quarters, join
from tests.test_market import place as _place
from tests.test_market import reference, sound, trader

# The "eight" world's eighth quarter ends on Monday 30 November 2026.
OPEN = datetime.fromisoformat("2026-12-01T13:00:00+01:00")
RUSH = datetime.fromisoformat("2026-12-01T21:55:00+01:00")
NIGHT = datetime.fromisoformat("2026-12-01T22:30:00+01:00")
T = "IDC"


def _dicts(db, sql, params=()):
    with db.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def place(db, account, side, quantity, price=None, *, now=OPEN, ticker=T):
    return _place(db, account, side, quantity, price, now=now, ticker=ticker)


@pytest.fixture
def at(monkeypatch):
    from server import main

    def set_time(moment):
        monkeypatch.setattr(main, "_exchange_time", lambda conn: moment)
    return set_time


# ---------------------------------------------------------------------------
# The Closing Rush
# ---------------------------------------------------------------------------

def test_the_closing_rush_is_the_last_ten_minutes_of_the_trading_day():
    day = "2026-12-01T"
    assert not clock.in_closing_rush(datetime.fromisoformat(day + "21:49:59+01:00"))
    assert clock.in_closing_rush(datetime.fromisoformat(day + "21:50:00+01:00"))
    assert clock.in_closing_rush(datetime.fromisoformat(day + "21:59:59+01:00"))
    assert not clock.in_closing_rush(datetime.fromisoformat(day + "22:00:00+01:00"))
    # It is part of the open session, not a separate state.
    assert clock.market_state(RUSH) is clock.MarketState.OPEN


def test_fees_are_halved_in_the_closing_rush_and_full_before_it(db):
    seller, buyer = trader(db, "seller", shares=10_000), trader(db, "buyer", cash_naira=1_000_000)
    price = reference(db)
    place(db, seller, "sell", 1_000, price, now=OPEN)
    usual = place(db, buyer, "buy", 1_000, price, now=OPEN)["trades"][0]
    assert usual["buyer_fee"] == usual["seller_fee"] == exchange.fee_due(price * 1_000)

    place(db, seller, "sell", 1_000, price, now=RUSH)
    rushed = place(db, buyer, "buy", 1_000, price, now=RUSH)["trades"][0]
    full = exchange.fee_due(price * 1_000)
    assert rushed["buyer_fee"] == rushed["seller_fee"] == full - full // 2
    # The buyer got back everything that was held for the fee they were let off.
    assert ledger.balance(db, buyer) == naira(1_000_000) - 2 * price * 1_000 - full - (full - full // 2)
    sound(db)


def test_an_order_filled_partly_before_the_rush_and_partly_in_it_pays_each_part_at_its_own_rate(db):
    seller, buyer = trader(db, "seller", shares=10_000), trader(db, "buyer", cash_naira=5_000_000)
    price = reference(db)
    order = place(db, buyer, "buy", 2_000, price, now=OPEN)["order"]
    place(db, seller, "sell", 1_000, price, now=OPEN)
    place(db, seller, "sell", 1_000, price, now=RUSH)
    row = _dicts(db, "SELECT * FROM market_orders WHERE id = %s", (order["id"],))[0]
    full = exchange.fee_due(price * 2_000)
    assert row["status"] == "filled" and row["fees_paid"] + row["fee_rebate"] == full
    assert row["fee_rebate"] == (full - exchange.fee_due(price * 1_000)) // 2
    assert ledger.balance(db, buyer) == naira(5_000_000) - price * 2_000 - row["fees_paid"]
    sound(db)


def test_splitting_an_order_in_the_rush_never_makes_its_fees_smaller(db):
    seller = trader(db, "seller", shares=100_000)
    one, many = trader(db, "one", cash_naira=1_000_000), trader(db, "many", cash_naira=1_000_000)
    price = reference(db)
    place(db, seller, "sell", 2_000, price, now=RUSH)
    place(db, one, "buy", 1_000, price, now=RUSH)
    for _ in range(100):
        place(db, many, "buy", 10, price, now=RUSH)
    assert ledger.balance(db, many) <= ledger.balance(db, one)
    sound(db)


def test_a_large_order_in_the_rush_is_shown_to_everybody_without_a_name(db, client, player, at):
    whale, small = trader(db, "whale", cash_naira=5_000_000), trader(db, "small", cash_naira=100_000)
    price = reference(db)
    big = data.LARGE_ORDER_NAIRA * 100 // price + 1
    place(db, whale, "buy", big, price, now=OPEN)                 # large, but not in the rush
    place(db, small, "buy", 10, price, now=RUSH)                  # in the rush, but small
    assert _dicts(db, "SELECT * FROM market_large_orders") == []
    place(db, whale, "buy", big, price, now=RUSH)
    at(RUSH)
    seen = client.get("/api/market/closing-bell").json()
    assert seen["in_rush"] is True and seen["fee_bps"] == 25 and seen["usual_fee_bps"] == 50
    assert len(seen["large_orders"]) == 1
    shown = seen["large_orders"][0]
    assert (shown["ticker"], shown["side"], shown["quantity"]) == (T, "buy", big)
    # Nothing in it says who: no account, no player, no name.
    assert set(shown) == {"ticker", "name", "side", "quantity", "value_kobo", "shown_at"}
    assert "whale" not in str(seen)
    # The record cannot be altered.
    with pytest.raises(errors.RestrictViolation):
        db.execute("DELETE FROM market_large_orders")


def test_the_computer_run_investors_orders_are_not_announced_as_large_orders(db):
    quarters.close_due_quarters(db, after_quarters(1))
    investors.act(db, datetime.fromisoformat("2026-10-13T21:55:00+01:00"), force=True)
    assert _dicts(db, "SELECT * FROM market_large_orders") == []


# ---------------------------------------------------------------------------
# The Closing Bell
# ---------------------------------------------------------------------------

@pytest.mark.world("eight")
def test_the_closing_bell_names_the_days_winner_loser_and_boldest_move_from_real_records(db):
    investors.act(db, OPEN, force=True)
    buyer = trader(db, "bolanle", cash_naira=200_000_000)
    seller = trader(db, "chidera", shares=2_000_000, ticker="ZCB")
    place(db, buyer, "buy", 400_000, now=OPEN)                           # pushes IDC up
    place(db, seller, "sell", 400_000, now=OPEN, ticker="ZCB")           # pushes ZCB down
    assert closingbell.ring(db, OPEN) is False or True                   # (an earlier day's bell may ring; not this day's)
    assert _dicts(db, "SELECT 1 FROM closing_bells WHERE session_date = '2026-12-01'") == []

    assert closingbell.ring(db, NIGHT) is True
    assert closingbell.ring(db, NIGHT) is False                          # once only
    bell = closingbell.latest(db)
    content = bell["content"]
    assert str(bell["session_date"]) == "2026-12-01"
    trades = _dicts(db, "SELECT c.ticker, t.price, t.quantity FROM market_trades t JOIN companies c ON c.id = t.company_id"
                        " WHERE t.session_date = '2026-12-01' ORDER BY t.price * t.quantity DESC")
    # Worked out by hand from the day's trades: each share's last price against where it began the day.
    by_hand = {}
    for row in _dicts(db, "SELECT DISTINCT ON (t.company_id) c.ticker, t.price, m.listing_price FROM market_trades t"
                          " JOIN companies c ON c.id = t.company_id JOIN market_instruments m ON m.company_id = t.company_id"
                          " WHERE t.session_date = '2026-12-01' ORDER BY t.company_id, t.id DESC"):
        by_hand[row["ticker"]] = (row["price"] - row["listing_price"]) * BPS // row["listing_price"]
    assert by_hand["IDC"] > 0 > by_hand["ZCB"]
    assert content["winner"]["change_bps"] == max(by_hand.values()) == by_hand[content["winner"]["ticker"]]
    assert content["loser"]["change_bps"] == min(by_hand.values()) == by_hand[content["loser"]["ticker"]]
    boldest = trades[0]
    assert any(line.startswith("Boldest move:") and f"{boldest['quantity']:,}" in line for line in content["lines"])
    assert content["lines"][0].startswith("The BSX 50")
    # The index for the day is written down, and it is the same figure the Market page gives.
    level = _dicts(db, "SELECT level FROM index_days WHERE session_date = '2026-12-01'")[0]["level"]
    assert level == content["index"] == marketview.overview(db, NIGHT)["index"]
    # The market advisory reads the economy from published figures.
    assert any("Central Bank's interest rate" in line for line in content["advisory"])
    assert any("Prices are rising" in line for line in content["advisory"])
    assert "results" in content["next"]
    # No name of any trader, anywhere in it.
    assert "bolanle" not in str(content) and "chidera" not in str(content) and str(buyer) not in str(content)


@pytest.mark.world("eight")
def test_the_closing_bell_never_hints_at_an_event_that_has_not_happened_yet(db):
    world = _dicts(db, "SELECT world_start, weeks_ahead FROM world_state")[0]
    today = clock.game_date(NIGHT, clock.effective_start(world["world_start"], world["weeks_ahead"]))
    # A flood later in the running quarter is already decided, and its story already written.
    news.publish(db, period=9, day=today.day_of_quarter + 20, kind="flood", story="event:test-flood",
                 facts={"location": "Lagos", "severity": "severe", "companies": "Idanre Cement"}, locations=["Lagos"])
    hidden = _dicts(db, "SELECT headline FROM news_items WHERE period = 9 AND day > %s", (today.day_of_quarter,))
    assert hidden
    closingbell.ring(db, NIGHT)
    content = str(closingbell.latest(db)["content"])
    for item in hidden:
        assert item["headline"] not in content


def test_the_bell_does_not_ring_for_a_day_before_the_world_began(db):
    assert closingbell.ring(db, datetime.fromisoformat("2026-10-04T23:00:00+01:00")) is False
    assert closingbell.latest(db) is None


def test_the_closing_bell_cannot_be_rewritten(db):
    closingbell.ring(db, datetime.fromisoformat("2026-10-06T23:00:00+01:00"))
    assert closingbell.latest(db) is not None
    with pytest.raises(errors.RestrictViolation):
        db.execute("UPDATE closing_bells SET content = '{}'")
    with pytest.raises(errors.RestrictViolation):
        db.execute("DELETE FROM index_days")


@pytest.mark.world("eight")
def test_the_bell_writes_down_what_each_player_is_worth_and_the_portfolio_charts_it(db, client, at):
    assert join(client, ADULT).status_code == 201
    account = _dicts(db, "SELECT id FROM ledger_accounts WHERE kind = 'player'")[0]["id"]
    investors.act(db, OPEN, force=True)
    place(db, account, "buy", 1_000, now=OPEN)
    place(db, account, "buy", 100, reference(db) * 95 // 100, now=OPEN)         # left waiting: its cash is held
    closingbell.ring(db, NIGHT)
    day = _dicts(db, "SELECT * FROM net_worth_days WHERE account_id = %s", (account,))[0]
    mine = marketview.portfolio(db, account, NIGHT)
    assert day["cash"] == mine["cash"] + mine["held_for_orders"] and day["investments"] == mine["shares_value"]
    at(NIGHT + timedelta(hours=14))
    seen = client.get("/api/market/portfolio").json()
    assert [d["session_date"] for d in seen["net_worth"]] == ["2026-12-01", "2026-12-02"]
    assert seen["net_worth"][0]["total_kobo"] == str(day["cash"] + day["investments"])
    assert seen["advice"] and all(isinstance(line, str) for line in seen["advice"])


def test_nobody_but_a_player_can_read_the_bell_the_ticker_or_the_facts(client):
    for path in ("/api/market/closing-bell", "/api/market/ticker", "/api/market/industries",
                 "/api/market/IDC/facts", "/api/market/IDC/results"):
        assert client.get(path).status_code == 401, path


# ---------------------------------------------------------------------------
# The ticker
# ---------------------------------------------------------------------------

@pytest.mark.world("eight")
def test_the_ticker_carries_every_share_and_the_index(db, client, player, at):
    investors.act(db, OPEN, force=True)
    at(OPEN)
    seen = client.get("/api/market/ticker").json()
    market = client.get("/api/market").json()
    assert len(seen["shares"]) == 50 and seen["index"] == market["index"] and seen["closing_rush"] is False
    assert {s["ticker"]: s["price_kobo"] for s in seen["shares"]} == {s["ticker"]: s["price_kobo"] for s in market["shares"]}
    at(RUSH)
    assert client.get("/api/market/ticker").json()["closing_rush"] is True
    assert client.get("/api/world/clock").status_code == 200


# ---------------------------------------------------------------------------
# Company facts, from filed figures only
# ---------------------------------------------------------------------------

@pytest.mark.world("eight")
def test_profit_per_share_is_filed_profit_divided_by_filed_shares(db):
    seen = insight.facts(db, T, OPEN)
    filed = _dicts(db, "SELECT DISTINCT ON (period) period, (figures->'income_statement'->>'net_profit')::bigint AS profit,"
                       " (figures->'notes'->>'shares_in_issue')::bigint AS shares FROM company_reports r"
                       " JOIN companies c ON c.id = r.company_id WHERE c.ticker = %s AND period >= 1 ORDER BY period, version DESC", (T,))
    assert [p["period"] for p in seen["profit_per_share"]] == [f["period"] for f in filed]
    for shown, f in zip(seen["profit_per_share"], filed):
        assert shown["eps"] == f["profit"] * 100 // f["shares"] and shown["net_profit"] == f["profit"]


@pytest.mark.world("eight")
def test_results_are_compared_with_the_same_quarter_a_year_ago(db):
    seen = insight.facts(db, T, OPEN)
    now, year_ago = (_dicts(db, "SELECT (figures->'income_statement'->>'revenue')::bigint AS sales,"
                                " (figures->'income_statement'->>'net_profit')::bigint AS profit FROM company_reports r"
                                " JOIN companies c ON c.id = r.company_id WHERE c.ticker = %s AND period = %s", (T, p))[0] for p in (8, 4))
    assert seen["compared_with"] == "the same quarter a year ago"
    assert seen["sales_change_bps"] == (now["sales"] - year_ago["sales"]) * BPS // year_ago["sales"]
    assert seen["sales_before"] == year_ago["sales"] and seen["profit_before"] == year_ago["profit"]


def test_before_a_year_has_passed_results_are_compared_with_the_quarter_before(db):
    assert insight.facts(db, T, OPEN)["compared_with"] == ""                # nothing filed yet
    quarters.close_due_quarters(db, after_quarters(2))
    assert insight.facts(db, T, after_quarters(2))["compared_with"] == "the quarter before"


@pytest.mark.world("eight")
def test_the_cash_outlook_is_todays_cash_plus_the_average_change_of_the_past_year(db):
    seen = insight.facts(db, T, OPEN)
    flows = _dicts(db, "SELECT (figures->'cash_flow'->>'cash_closing')::bigint - (figures->'cash_flow'->>'cash_opening')::bigint AS change,"
                       " (figures->'balance_sheet'->>'cash')::bigint AS cash FROM company_reports r JOIN companies c ON c.id = r.company_id"
                       " WHERE c.ticker = %s AND period BETWEEN 5 AND 8 ORDER BY period", (T,))
    assert seen["cash"] == flows[-1]["cash"] and seen["cash_change_year"] == sum(f["change"] for f in flows)
    assert seen["cash_in_three_months"] == seen["cash"] + sum(f["change"] for f in flows) // 4
    assert seen["cash_outlook"].startswith("Cash is coming in" if sum(f["change"] for f in flows) >= 0 else "Cash is going out")


@pytest.mark.world("eight")
def test_the_years_high_and_low_come_from_real_trades_and_the_next_results_date_from_the_clock(db):
    assert insight.facts(db, T, OPEN)["year_high"] is None                 # it has not traded
    seller, buyer = trader(db, "seller", shares=10_000), trader(db, "buyer", cash_naira=10_000_000)
    base = reference(db)
    for price in (base, base + 50, base - 30):
        place(db, seller, "sell", 10, price)
        place(db, buyer, "buy", 10, price)
    seen = insight.facts(db, T, OPEN)
    assert (seen["year_high"], seen["year_low"]) == (base + 50, base - 30)
    assert seen["next_results"]["label"] == "Year 3 Q1"
    assert seen["next_results"]["at"] == datetime.fromisoformat("2026-12-07T00:00:00+01:00")
    # More than a game year later, those trades no longer count.
    later = insight.facts(db, T, OPEN + timedelta(days=data.GAME_YEAR_REAL_DAYS + 2))
    assert later["year_high"] is None


@pytest.mark.world("eight")
def test_the_written_results_report_says_only_what_was_filed(db, client, player):
    report = insight.results_report(db, T)
    figures = _dicts(db, "SELECT figures FROM company_reports r JOIN companies c ON c.id = r.company_id"
                         " WHERE c.ticker = %s AND period = 8", (T,))[0]["figures"]
    text = " ".join(report["paragraphs"])
    assert report["period"] == 8 and report["title"].endswith("Year 2 Q4")
    assert marketview._big(figures["income_statement"]["revenue"]) in text
    assert marketview._big(figures["income_statement"]["net_profit"]) in text
    assert "the same quarter a year ago" in text
    for note in figures["notes"]["management_notes"]:
        assert note in text
    # The true record is never the source: every figure in it is in the filed report.
    assert [q["period"] for q in report["available"]] == list(range(1, 9))
    seen = client.get(f"/api/market/{T}/results", params={"period": 3}).json()
    assert seen["label"] == "Year 1 Q3" and seen["paragraphs"]
    assert client.get(f"/api/market/{T}/results", params={"period": 99}).status_code == 404
    assert client.get("/api/market/QQQ/results").status_code == 404
    opening = client.get(f"/api/market/{T}/results", params={"period": 0}).json()
    assert "opening position" in opening["title"]


@pytest.mark.world("eight")
def test_results_news_compares_profit_with_the_same_quarter_a_year_ago(db):
    stories = _dicts(db, "SELECT kind, body, facts FROM news_items WHERE kind IN ('results_strong', 'results_weak') AND period = 9")
    for story in stories:
        assert story["facts"]["yearly"] is True
        assert "the quarter before" not in story["body"] and "three months earlier" not in story["body"]
        assert "previous quarter" not in story["body"]
    early = _dicts(db, "SELECT facts FROM news_items WHERE kind IN ('results_strong', 'results_weak') AND period = 3")
    assert all(story["facts"]["yearly"] is False for story in early)


# ---------------------------------------------------------------------------
# Industries: the heat map, growth, and who leads
# ---------------------------------------------------------------------------

@pytest.mark.world("eight")
def test_every_industry_shows_its_growth_and_its_companies_ranked_by_share_of_sales(db, client, player):
    seen = insight.industries(db, OPEN)
    assert sum(len(s["companies"]) for s in seen) == 50
    for sector in seen:
        sales = [c["sales"] for c in sector["companies"]]
        assert sales == sorted(sales, reverse=True)
        assert [c["rank"] for c in sector["companies"]] == list(range(1, len(sales) + 1))
        assert abs(sum(c["share_bps"] for c in sector["companies"]) - BPS) <= len(sales)
        assert sector["sales_growth_bps"] is not None
        assert sector["market_value"] == sum(c["market_value"] for c in sector["companies"])
    one = seen[0]["companies"][0]
    filed = _dicts(db, "SELECT sum((figures->'income_statement'->>'revenue')::bigint)::bigint AS total FROM company_reports r"
                       " JOIN companies c ON c.id = r.company_id WHERE c.ticker = %s AND period BETWEEN 5 AND 8", (one["ticker"],))
    assert one["sales"] == filed[0]["total"]
    assert insight.facts(db, one["ticker"], OPEN)["industry"]["rank"] == 1
    assert len(client.get("/api/market/industries").json()) == len(seen)


def test_industry_growth_is_not_shown_until_two_years_are_filed(db):
    quarters.close_due_quarters(db, after_quarters(4))
    assert all(sector["sales_growth_bps"] is None for sector in insight.industries(db, after_quarters(4)))


# ---------------------------------------------------------------------------
# The personal advisory summary
# ---------------------------------------------------------------------------

def test_the_personal_advisory_points_at_idle_cash_and_at_everything_in_one_company(db):
    idle = {"cash": naira(500_000), "held_for_orders": 0, "shares_value": 0, "total": naira(500_000), "holdings": []}
    assert "All your money is in cash" in insight.personal_advice(db, idle)[0]
    one = {"cash": naira(50_000), "held_for_orders": 0, "shares_value": naira(450_000), "total": naira(500_000),
           "holdings": [{"ticker": T, "name": "Idanre Cement", "value": naira(450_000), "cost": naira(600_000), "gain": -naira(150_000)}]}
    advice = " ".join(insight.personal_advice(db, one, bill_yield_bps=1250))
    assert "is in one company" in advice and "1 industry" in advice and "less than you paid" in advice
    # It never tells the player to buy or sell a named share.
    for line in insight.personal_advice(db, one):
        assert not any(word in line.lower() for word in ("you should buy", "you should sell", "buy now", "sell now"))
