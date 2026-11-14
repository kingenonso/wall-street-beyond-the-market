"""Stage 4, Part A, slice 3: the market screens.

The Market page and the BSX 50 index, price history, the portfolio, the watchlist with
price alerts, and on each company's page: valuation, NPV, the advisory summary and the
shares in circulation.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from psycopg.rows import dict_row

from simulation import exchange, investors, ledger, marketview, quarters, valuation
from simulation.money import BPS, naira
from tests.conftest import ADULT, after_quarters, join
from tests.test_market import place as _place
from tests.test_market import sound, trader

# The "eight" world's eighth quarter ends on Monday 30 November 2026. The next day, in trading hours:
OPEN = datetime.fromisoformat("2026-12-01T13:00:00+01:00")
T = "IDC"


def _dicts(db, sql, params=()):
    with db.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def place(db, account, side, quantity, price=None, *, now=OPEN, ticker=T):
    return _place(db, account, side, quantity, price, now=now, ticker=ticker)


def price_of(db, ticker=T, now=OPEN) -> int:
    quote = exchange.quote(db, ticker, now)
    return quote["last_price"] or quote["reference_price"]


@pytest.fixture
def trading_hours(monkeypatch):
    from server import main
    monkeypatch.setattr(main, "_exchange_time", lambda conn: OPEN)


# ---------------------------------------------------------------------------
# The Market page and the BSX 50
# ---------------------------------------------------------------------------

@pytest.mark.world("eight")
def test_the_market_page_lists_every_share_and_the_index_starts_at_one_thousand(db):
    investors.act(db, OPEN, force=True)
    seen = marketview.overview(db, OPEN)
    assert len(seen["shares"]) == 70 and seen["state"] == "open"
    assert {"ticker", "name", "sector", "price", "change_bps", "volume", "market_value", "rating"} <= set(seen["shares"][0])
    for share in seen["shares"]:
        assert share["price"] > 0 and share["market_value"] == share["price"] * share["shares"]
    # The index is every company at its present price against its listing price, counted by size.
    # (Once companies have issued new shares, the base is kept on record so that new shares alone never move it.)
    base = marketview.index_base(db) or sum(s["listing_price"] * s["shares"] for s in seen["shares"])
    by_hand = sum(s["price"] * s["shares"] for s in seen["shares"]) * 100_000 // base
    assert seen["index"] == by_hand
    assert 90_000 <= seen["index"] <= 110_000                         # about 1,000 on its first day
    assert seen["market_value"] == sum(s["market_value"] for s in seen["shares"])
    assert seen["volume"] == db.execute("SELECT coalesce(sum(quantity), 0) FROM market_trades").fetchone()[0]


@pytest.mark.world("eight")
def test_the_index_rises_when_a_large_companys_price_rises_and_a_large_one_moves_it_more(db):
    investors.act(db, OPEN, force=True)
    before = marketview.overview(db, OPEN)
    sizes = sorted(before["shares"], key=lambda s: s["market_value"])
    small, large = sizes[0], sizes[-1]

    def lifted(ticker: str) -> int:
        with db.transaction(force_rollback=True):
            db.execute("UPDATE market_instruments m SET last_price = (coalesce(m.last_price, m.reference_price) * 105) / 100"
                       " FROM companies c WHERE c.id = m.company_id AND c.ticker = %s", (ticker,))
            return marketview.overview(db, OPEN)["index"]

    # The smallest company is so small that a 5% rise barely shows; the largest moves the index visibly.
    assert lifted(large["ticker"]) > lifted(small["ticker"]) >= before["index"]
    assert lifted(large["ticker"]) - before["index"] > 10 * (lifted(small["ticker"]) - before["index"])
    assert lifted(large["ticker"]) - before["index"] > 100             # more than one point


@pytest.mark.world("eight")
def test_price_history_and_index_history_are_the_trades_day_by_day(db):
    seller = trader(db, "seller", shares=10_000)
    buyer = trader(db, "buyer", cash_naira=50_000_000)
    days = []
    for n in range(3):
        now = OPEN + timedelta(days=n)
        price = exchange.price_limits(price_of(db, now=now))[1] - 3 * n          # near the day's top, a different price each day
        place(db, seller, "sell", 100 + n, price, now=now)
        place(db, buyer, "buy", 60, price, now=now)
        place(db, buyer, "buy", 40 + n, price, now=now + timedelta(minutes=5))
        days.append((exchange.session_of(now)[0], price, 100 + n))
    history = marketview.history(db, T)
    assert [(d["session_date"], d["close"], d["volume"]) for d in history] == days
    assert all(d["low"] <= d["open"] <= d["high"] and d["low"] <= d["close"] <= d["high"] for d in history)
    assert marketview.history(db, "ZZZ") is None
    index = marketview.overview(db, OPEN + timedelta(days=2))["index_history"]
    assert [p["session_date"] for p in index] == [d[0] for d in days]
    assert index[0]["level"] < index[1]["level"] < index[2]["level"]              # one share rising, the rest unchanged
    assert index[-1]["level"] == marketview.overview(db, OPEN + timedelta(days=2))["index"]
    sound(db)


# ---------------------------------------------------------------------------
# The portfolio
# ---------------------------------------------------------------------------

@pytest.mark.world("eight")
def test_a_portfolio_shows_what_was_paid_what_it_is_worth_and_the_gain(db):
    seller = trader(db, "seller", shares=10_000)
    ada = trader(db, "ada", cash_naira=1_000_000)
    price = price_of(db)
    place(db, seller, "sell", 300, price)
    place(db, seller, "sell", 200, price + 40)
    place(db, ada, "buy", 500, price + 40)                             # 300 at the lower price, 200 at the higher
    cost = price * 300 + (price + 40) * 200
    fees = exchange.fee_due(cost)
    mine = marketview.portfolio(db, ada, OPEN)
    holding = mine["holdings"][0]
    assert (holding["ticker"], holding["shares"], holding["cost"]) == (T, 500, cost + fees)
    assert holding["value"] == (price + 40) * 500 and holding["gain"] == holding["value"] - holding["cost"]
    assert mine["cash"] == naira(1_000_000) - cost - fees and mine["held_for_orders"] == 0
    assert mine["total"] == mine["cash"] + holding["value"]

    # Sell 200: the average cost of those 200 comes off, and the gain on them is counted as made.
    buyer = trader(db, "buyer", cash_naira=1_000_000)
    place(db, buyer, "buy", 200, price + 60)
    place(db, ada, "sell", 200, price + 60)
    after = marketview.portfolio(db, ada, OPEN)
    left = after["holdings"][0]
    cost_of_sold = (cost + fees) * 200 // 500
    assert (left["shares"], left["cost"]) == (300, cost + fees - cost_of_sold)
    proceeds = (price + 60) * 200
    assert after["realised"] == proceeds - exchange.fee_due(proceeds) - cost_of_sold
    # A waiting buy order's cash is shown as held, and still counts as the player's.
    low = exchange.price_limits(price)[0]
    order = place(db, ada, "buy", 100, low)["order"]
    waiting = marketview.portfolio(db, ada, OPEN)
    assert waiting["held_for_orders"] == order["reserved"] and waiting["total"] == after["total"]
    # A waiting sell order's shares still count as owned.
    place(db, ada, "sell", 100, exchange.price_limits(price)[1])
    assert marketview.portfolio(db, ada, OPEN)["holdings"][0]["shares"] == 300
    sound(db)


@pytest.mark.world("eight")
def test_dividends_received_show_in_the_portfolio_by_company(db):
    ada = trader(db, "ada", shares=5_000_000)                           # a holding large enough to be paid whole kobo
    assert quarters.close_due_quarters(db, after_quarters(9)) == [9]
    mine = marketview.portfolio(db, ada, OPEN)
    paid = db.execute("SELECT coalesce(sum(e.amount), 0) FROM ledger_entries e JOIN ledger_transactions t ON t.id = e.transaction_id"
                      " WHERE t.kind = 'dividend' AND e.account_id = %s AND e.amount > 0", (ada,)).fetchone()[0]
    assert paid > 0 and mine["dividends"] == paid and mine["holdings"][0]["dividends"] == paid
    assert mine["cash"] == paid                                         # it arrived as cash


# ---------------------------------------------------------------------------
# The company page: valuation, NPV, advisory summary, shares in circulation
# ---------------------------------------------------------------------------

@pytest.mark.world("eight")
def test_the_investors_page_gives_valuation_npv_advice_and_who_owns_the_shares(db):
    investors.act(db, OPEN, force=True)
    a = marketview.analysis(db, T, OPEN)
    worth = valuation.latest(db)[db.execute("SELECT id FROM companies WHERE ticker = %s", (T,)).fetchone()[0]]

    # Shares in circulation: the number, and who holds them, adding up to all of them.
    assert a["shares_in_issue"] == ledger.amount_in_existence(db, f"SHR-{T}") == sum(h["shares"] for h in a["shareholders"])
    assert {h["holder"] for h in a["shareholders"]} == {"Founders", "Pension funds", "Small investors"}
    assert 9_990 <= sum(h["share_bps"] for h in a["shareholders"]) <= BPS

    # Valuation: the whole company at today's price, against its profit, sales and owners' funds.
    assert a["market_value"] == a["price"] * a["shares_in_issue"]
    filed = _dicts(db, "SELECT DISTINCT ON (period) (figures->'income_statement'->>'net_profit')::bigint AS profit,"
                       " (figures->'income_statement'->>'revenue')::bigint AS sales,"
                       " (figures->'cash_flow'->>'dividends_paid')::bigint AS dividends FROM company_reports r"
                       " JOIN companies c ON c.id = r.company_id WHERE c.ticker = %s AND period BETWEEN 5 AND 8"
                       " ORDER BY period, version DESC", (T,))
    assert a["yearly_profit"] == sum(f["profit"] for f in filed) == worth["yearly_profit"]
    assert a["yearly_sales"] == sum(f["sales"] for f in filed)
    assert a["price_to_profit"] == a["market_value"] * 100 // a["yearly_profit"]
    assert a["price_to_sales"] == a["market_value"] * 100 // a["yearly_sales"]
    assert a["dividend_yield_bps"] == sum(f["dividends"] for f in filed) * BPS // a["market_value"] > 0

    # NPV: the public figure, with the sum behind it adding up to it.
    assert a["npv_per_share"] == worth["value_per_share"] and a["npv_method"] == "profits"
    assert len(a["schedule"]) == 6 and a["schedule"][-1]["label"] == "Every year after that"
    total = sum(year["value_today"] for year in a["schedule"])
    assert abs(total - valuation.present_value(worth["yearly_profit"], worth["growth_bps"], worth["discount_bps"], worth["long_run_bps"])) <= 6
    assert abs(total // a["shares_in_issue"] - a["npv_per_share"]) <= 1
    assert a["npv_gap_bps"] == (a["price"] - a["npv_per_share"]) * BPS // a["npv_per_share"]

    # The advisory summary: a view, its reasons and its risks, in plain words.
    assert a["verdict"] in ("looks cheap", "looks about fairly priced", "looks expensive")
    assert len(a["reasons"]) >= 2 and len(a["risks"]) >= 1 and "₦" in a["reasons"][0]
    assert all(text.endswith(".") for text in a["reasons"] + a["risks"])


@pytest.mark.world("eight")
def test_the_advice_follows_the_price_and_never_says_buy_or_sell(db):
    investors.act(db, OPEN, force=True)
    verdicts = {}
    for label, percent in (("cheap", 70), ("fair", 100), ("dear", 140)):
        with db.transaction(force_rollback=True):
            db.execute("UPDATE market_instruments m SET last_price = v.value_per_share * %s / 100 FROM company_valuations v, companies c"
                       " WHERE v.company_id = m.company_id AND v.period = 8 AND c.id = m.company_id AND c.ticker = %s", (percent, T))
            verdicts[label] = marketview.analysis(db, T, OPEN)
    assert [verdicts[k]["verdict"] for k in ("cheap", "fair", "dear")] == ["looks cheap", "looks about fairly priced", "looks expensive"]
    assert "below" in verdicts["cheap"]["reasons"][0] and "above" in verdicts["dear"]["reasons"][0]
    for a in (marketview.analysis(db, s["ticker"], OPEN) for s in marketview.overview(db, OPEN)["shares"]):
        text = " ".join(a["reasons"] + a["risks"] + [a["verdict"]]).lower()
        for word in (" buy ", " sell ", "guarantee", "will rise", "will fall", "should "):
            assert word not in f" {text} ", (a["ticker"], word)


@pytest.mark.world("eight")
def test_a_troubled_company_is_judged_on_its_assets_and_its_risks_are_named(db):
    investors.act(db, OPEN, force=True)
    worst = _dicts(db, "SELECT c.ticker, p.credit_rating FROM company_reports p JOIN companies c ON c.id = p.company_id"
                       " JOIN company_valuations v ON v.company_id = c.id AND v.period = 8"
                       " WHERE p.period = 8 AND v.method = 'assets' AND c.listed ORDER BY p.credit_rating DESC LIMIT 1")
    assert worst, "expected at least one loss-making company after eight quarters"
    a = marketview.analysis(db, worst[0]["ticker"], OPEN)
    assert a["npv_method"] == "assets" and a["schedule"] == [] and a["price_to_profit"] is None
    assert a["verdict"] == "judged on its assets" and "cannot be valued on its profits" in a["reasons"][0]
    assert len(a["risks"]) >= 2
    assert a["npv_per_share"] >= 100                                    # never below one naira


@pytest.mark.world("eight")
def test_with_few_players_no_line_shows_what_one_player_holds(db):
    ada = trader(db, "ada", shares=123_457)
    holders = {h["holder"]: h["shares"] for h in marketview.analysis(db, T, OPEN)["shareholders"]}
    assert "Players" not in holders and 123_457 not in holders.values()
    assert sum(holders.values()) == ledger.amount_in_existence(db, f"SHR-{T}")
    # Shares held by the exchange for a sell order are still counted as their seller's.
    place(db, ada, "sell", 100_000, exchange.price_limits(price_of(db))[1])
    again = {h["holder"]: h["shares"] for h in marketview.analysis(db, T, OPEN)["shareholders"]}
    assert again == holders
    # Once there are twenty players, they have a line of their own.
    for n in range(20):
        trader(db, f"p{n}")
    assert {h["holder"]: h["shares"] for h in marketview.analysis(db, T, OPEN)["shareholders"]}["Players"] == 123_457


# ---------------------------------------------------------------------------
# The watchlist and price alerts
# ---------------------------------------------------------------------------

def _player_id(db, name: str):
    return db.execute("SELECT id FROM players WHERE display_name = %s", (name,)).fetchone()[0]


@pytest.mark.world("eight")
def test_a_watched_share_raises_an_alert_when_it_reaches_the_players_price(db):
    seller = trader(db, "seller", shares=10_000)
    buyer = trader(db, "buyer", cash_naira=50_000_000)
    ada = _player_id(db, "buyer")
    price = price_of(db)
    low, high = exchange.price_limits(price)
    marketview.watch(db, ada, T, alert_above=price + 50, alert_below=low)
    marketview.watch(db, ada, "KTX", None, None)
    watched = {w["ticker"]: w for w in marketview.watchlist(db, ada, OPEN)}
    assert watched[T]["reached"] is None and watched["KTX"]["reached"] is None and watched[T]["price"] == price

    place(db, seller, "sell", 100, price + 60)
    place(db, buyer, "buy", 100, price + 60)                           # the price rises past the alert
    assert {w["ticker"]: w["reached"] for w in marketview.watchlist(db, ada, OPEN)} == {T: "above", "KTX": None}
    place(db, buyer, "buy", 100, low)
    place(db, seller, "sell", 100, low)                                # and falls to the lower one
    assert marketview.watchlist(db, ada, OPEN)[0]["reached"] == "below"

    marketview.watch(db, ada, T, None, None)                           # changing the alert clears it
    assert marketview.watchlist(db, ada, OPEN)[0]["reached"] is None
    marketview.unwatch(db, ada, T)
    assert [w["ticker"] for w in marketview.watchlist(db, ada, OPEN)] == ["KTX"]


@pytest.mark.world("eight")
def test_a_watchlist_has_its_limits(db):
    trader(db, "ada")
    ada = _player_id(db, "ada")
    with pytest.raises(marketview.WatchlistError, match="no share with that code"):
        marketview.watch(db, ada, "ZZZ", None, None)
    with pytest.raises(marketview.WatchlistError, match="must be above"):
        marketview.watch(db, ada, T, alert_above=1000, alert_below=2000)
    tickers = [t for (t,) in db.execute("SELECT ticker FROM companies WHERE listed ORDER BY ticker").fetchall()]
    for ticker in tickers[:marketview.MOST_WATCHED]:
        marketview.watch(db, ada, ticker, None, None)
    with pytest.raises(marketview.WatchlistError, match="at most 30"):
        marketview.watch(db, ada, tickers[marketview.MOST_WATCHED], None, None)
    marketview.watch(db, ada, tickers[0], alert_above=5000, alert_below=None)       # changing one already there is fine
    assert db.execute("SELECT count(*) FROM watchlist").fetchone()[0] == marketview.MOST_WATCHED


# ---------------------------------------------------------------------------
# Through the website's door
# ---------------------------------------------------------------------------

@pytest.mark.world("eight")
def test_the_market_screens_through_the_website(client, player, db, trading_hours):
    investors.act(db, OPEN, force=True)
    market = client.get("/api/market").json()
    assert len(market["shares"]) == 70 and market["market_state"] == "open" and 900 <= market["index"] <= 1100
    assert {"ticker", "name", "sector", "price_kobo", "traded", "change_bps", "volume", "market_value_kobo", "credit_rating",
            "closes"} == set(market["shares"][0])          # the last five closes: the small trend lines (redesign)

    analysis = client.get(f"/api/market/{T}/analysis").json()
    assert analysis["verdict"] and analysis["schedule"] and analysis["shareholders"] and analysis["filing_label"] == "Year 2 Q4"
    assert int(analysis["market_value_kobo"]) == int(analysis["price_kobo"]) * analysis["shares_in_issue"]
    assert client.get(f"/api/market/{T}/history").json() == []

    # Buy some shares, then the portfolio shows them.
    price = int(client.get(f"/api/market/{T}").json()["offers"][0]["price_kobo"])
    bought = client.post("/api/market/orders", json={"ticker": T, "side": "buy", "kind": "limit", "quantity": 100, "limit_price_kobo": price})
    assert bought.status_code == 201 and bought.json()["order"]["status"] == "filled", bought.text
    portfolio = client.get("/api/market/portfolio").json()
    holding = portfolio["holdings"][0]
    assert (holding["ticker"], holding["shares"]) == (T, 100)
    assert int(holding["cost_kobo"]) == price * 100 + exchange.fee_due(price * 100)
    assert int(portfolio["total_kobo"]) == int(portfolio["cash_kobo"]) + int(portfolio["shares_value_kobo"])
    assert len(client.get(f"/api/market/{T}/history").json()) == 1

    # Watch it, with an alert already reached.
    watched = client.put(f"/api/market/watchlist/{T}", json={"alert_below_kobo": price * 2})
    assert watched.status_code == 200 and watched.json()[0]["reached"] == "below"
    assert client.get("/api/market/watchlist").json()[0]["ticker"] == T
    assert client.delete(f"/api/market/watchlist/{T}").json() == []
    sound(db)


@pytest.mark.world("eight")
def test_a_players_portfolio_and_watchlist_are_theirs_alone(client, player, db, trading_hours):
    from fastapi.testclient import TestClient

    from server.main import app
    other = TestClient(app)
    assert join(other, {**ADULT, "email": "bola@example.com", "display_name": "Bola"}).status_code == 201
    client.put(f"/api/market/watchlist/{T}", json={"alert_above_kobo": 9_000})
    assert other.get("/api/market/watchlist").json() == []                  # not visible to anybody else
    assert other.delete(f"/api/market/watchlist/{T}").json() == []          # and nobody else can remove it
    assert [w["ticker"] for w in client.get("/api/market/watchlist").json()] == [T]
    assert other.get("/api/market/portfolio").json()["holdings"] == []
    # Nothing on the shared pages names a player or an account.
    for path in ("/api/market", f"/api/market/{T}/analysis", f"/api/market/{T}/history"):
        text = other.get(path).text
        for hidden in ("account", "Ada", "Bola", "player_id", "fortune", "centre", "carried"):
            assert hidden not in text, (path, hidden)


@pytest.mark.world("eight")
@pytest.mark.parametrize("body", [
    {"alert_above_kobo": -5}, {"alert_above_kobo": 0}, {"alert_below_kobo": 1.5}, {"alert_above_kobo": "100"},
    {"alert_above_kobo": 10**30}, {"alert_above_kobo": 100, "alert_below_kobo": 200}, {"player_id": "someone-else"},
    {"alert_above_kobo": 100, "reached": "above"},
])
def test_a_made_up_watchlist_request_is_refused(client, player, db, trading_hours, body):
    assert client.put(f"/api/market/watchlist/{T}", json=body).status_code in (409, 422)
    assert db.execute("SELECT count(*) FROM watchlist").fetchone()[0] == 0


@pytest.mark.world("eight")
def test_the_market_screens_refuse_strangers_and_bad_addresses(client, player, trading_hours):
    assert client.put("/api/market/watchlist/ZZZ", json={}).status_code == 409
    assert client.put("/api/market/watchlist/idc", json={}).status_code == 422
    assert client.get("/api/market/ZZZ/analysis").status_code == 404
    assert client.get("/api/market/ZZZ/history").status_code == 404
    client.cookies.clear()
    for method, path in (("GET", "/api/market"), ("GET", "/api/market/portfolio"), ("GET", "/api/market/watchlist"),
                         ("PUT", f"/api/market/watchlist/{T}"), ("DELETE", f"/api/market/watchlist/{T}"),
                         ("GET", f"/api/market/{T}/analysis"), ("GET", f"/api/market/{T}/history")):
        assert client.request(method, path, json={}).status_code == 401, (method, path)


@pytest.mark.world("eight")
def test_the_company_page_never_lists_one_players_shares_or_the_exchange_as_an_owner(client, player, db, trading_hours):
    """Before this slice the company page listed every account holding the share, one line each."""
    account = db.execute("SELECT id FROM ledger_accounts WHERE kind = 'player'").fetchone()[0]
    ledger.transfer(db, payer=ledger.account_id(db, ledger.INVESTORS_PUBLIC), receiver=account, amount=54_321,
                    asset=f"SHR-{T}", kind="test_shares", memo="Test: shares to hold")
    investors.act(db, OPEN, force=True)                                 # investors' sell orders are held by the exchange
    body = client.get(f"/api/companies/{T}").json()
    names = [o["name"] for o in body["owners"]]
    assert set(names) == {"Founders", "Pension funds", "Small investors"}
    assert "54321" not in str(client.get(f"/api/companies/{T}").json()["owners"])       # (the filed figures are long numbers; only the owners matter here)
    assert int(body["shares_in_issue"]) == sum(int(o["shares"]) for o in body["owners"]) == ledger.amount_in_existence(db, f"SHR-{T}")
