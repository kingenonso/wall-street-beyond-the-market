"""The economy upgrade: the ten-question loophole check, one test (or more) for each question.

Players may commit crimes against each other's empires, but never against the game: no money from
nowhere, no seeing what is hidden, no acting as somebody else, no beating the clock.
"""

from __future__ import annotations

import psycopg
import pytest
from psycopg.rows import dict_row

from simulation import abroad, consumers, economy, exchange, ledger, news, quarters
from simulation import world_data as data
from tests.conftest import ADULT, after_quarters, join, money_accounted_for
from tests.test_market import OPEN, trader

pytestmark = pytest.mark.world("eight")


def _dicts(db, sql, params=()):
    with db.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def _closed(db) -> int:
    return db.execute("SELECT last_closed_period FROM world_state").fetchone()[0]


# 1. Can a player see one consumer group's own figures (its savings, debts, taste, or where one family moved)?
def test_q1_no_page_shows_one_group(db, client):
    assert join(client, ADULT).status_code == 201
    body = client.get("/api/economy").json()
    text = str(body)
    # Only totals: by income level (hundreds of groups each), by mindset, and moves counted by place.
    assert all(b["groups"] >= 50 for b in body["consumers"]["bands"])
    assert "tastes" not in text and "earns_bps" not in text and "moved_period" not in text
    for path in ("/api/economy", "/api/me", "/api/market", "/api/news"):
        assert "consumer_groups" not in client.get(path).text
    # No route reads the groups' table except through the added-up summary.
    import pathlib
    for source in pathlib.Path("server").glob("*.py"):
        assert "consumer_groups" not in source.read_text().replace("SELECT 1 FROM consumer_groups LIMIT 1", ""), source


# 2. Can money appear or vanish through the groups, a move, trade abroad or foreign investors?
def test_q2_every_naira_is_still_counted_once(db):
    assert ledger.audit(db) == []
    assert ledger.amount_in_existence(db) == money_accounted_for(db)
    # Moves, imports, exports, royalties and foreign money: each one only moves naira from one account to another.
    for kind in ("household_move", "imports", "exports", "oil_royalty", "foreign_investment", "foreign_withdrawal"):
        net = db.execute("SELECT coalesce(sum(e.amount), 0) FROM ledger_entries e JOIN ledger_transactions t ON t.id = e.transaction_id"
                         " WHERE t.kind = %s AND e.asset = 'NGN'", (kind,)).fetchone()[0]
        assert net == 0, kind
    # The rest of the world was given its naira once, when the world began, like everybody else.
    abroad_account = ledger.account_id(db, abroad.ABROAD)
    opening = db.execute("SELECT coalesce(sum(e.amount), 0) FROM ledger_entries e JOIN ledger_transactions t ON t.id = e.transaction_id"
                         " WHERE e.account_id = %s AND t.kind = 'opening_balance'", (abroad_account,)).fetchone()[0]
    assert opening == abroad.opening_reserve(_dicts(db, "SELECT export_base FROM abroad_results WHERE period = 0")[0]["export_base"])


# 3. Can anybody learn next quarter's oil price or exchange rate before the close that sets it?
def test_q3_the_next_oil_price_and_rate_are_unknown_until_the_close(db, client):
    assert join(client, ADULT).status_code == 201
    body = client.get("/api/economy").json()["abroad"]
    closed = _closed(db)
    # Exactly one row per closed quarter exists: nothing about any later quarter is stored anywhere.
    assert db.execute("SELECT max(period) FROM abroad_results").fetchone()[0] == closed
    assert body["history"][-1]["period"] == closed + 1
    # The secret behind the oil price is the world's own, which is never sent.
    assert "fortune_seed" not in str(body) and db.execute("SELECT fortune_seed FROM world_state").fetchone()[0] not in str(body)
    # Closing the next quarter writes the next row: until then there was none.
    quarters.close_due_quarters(db, after_quarters(closed + 1))
    assert db.execute("SELECT max(period) FROM abroad_results").fetchone()[0] == closed + 1


# 4. Can foreign investors set a price, or get shares, other than by trading on the exchange?
def test_q4_foreign_investors_only_trade_through_orders(db):
    foreign = ledger.account_id(db, abroad.FOREIGN)
    kinds = {r["kind"] for r in _dicts(db, "SELECT DISTINCT t.kind FROM ledger_entries e JOIN ledger_transactions t ON t.id = e.transaction_id"
                                           " WHERE e.account_id = %s AND e.asset LIKE 'SHR-%%'", (foreign,))}
    assert kinds <= {"share_trade", "order_reserve", "order_release", "share_split", "rights_issue", "takeover_payment",
                     "tender_hold", "tender_release"}
    # Their account is an ordinary computer-run investor: the same rules, the same limits.
    kind = db.execute("SELECT kind FROM ledger_accounts WHERE id = %s", (foreign,)).fetchone()[0]
    assert kind == "npc_investors" and kind in exchange.TRADER_KINDS


# 5. Can a player milk the foreign investors by buying from them and selling straight back?
def test_q5_buying_from_foreign_investors_always_costs_more_than_selling_back(db):
    from simulation import investors
    investors.act(db, OPEN, force=True)
    foreign = ledger.account_id(db, abroad.FOREIGN)
    for company in {r["company_id"] for r in _dicts(db, "SELECT company_id FROM market_orders WHERE account_id = %s AND status = 'open'", (foreign,))}:
        bids = [r["limit_price"] for r in _dicts(db, "SELECT limit_price FROM market_orders WHERE account_id = %s AND company_id = %s"
                                                     " AND status = 'open' AND side = 'buy'", (foreign, company))]
        asks = [r["limit_price"] for r in _dicts(db, "SELECT limit_price FROM market_orders WHERE account_id = %s AND company_id = %s"
                                                     " AND status = 'open' AND side = 'sell'", (foreign, company))]
        if bids and asks:
            # A round trip with them loses at least their margin, before the exchange's fee both ways.
            assert min(asks) > max(bids)
            margin = data.INVESTORS[abroad.FOREIGN][2]
            assert (min(asks) - max(bids)) * 10_000 >= max(bids) * 2 * margin * 99 // 100
            # Buying one share at their asking price and selling it straight back to them always loses money.
            assert max(bids) - exchange.fee_due(max(bids)) - (min(asks) + exchange.fee_due(min(asks))) < 0


# 6. Can the foreign investors swamp the market?
def test_q6_foreign_investors_stop_pushing_once_they_have_traded_their_share_of_the_day(db, monkeypatch):
    foreign = ledger.account_id(db, abroad.FOREIGN)
    day, _ = exchange.session_of(OPEN)
    assert abroad.day_budget_left(db, foreign, day) == data.FOREIGN_DAY_LEAST_NAIRA * 100          # a market with no history
    # A pretend day of heavy foreign trading uses the budget up: from then on they only wait.
    from simulation import investors
    monkeypatch.setattr(abroad, "day_budget_left", lambda conn, account, d: 0)
    monkeypatch.setattr(abroad, "tilt_now", lambda conn: data.FOREIGN_MOST_TILT_BPS)
    investors.act(db, OPEN, force=True)
    mine = db.execute("SELECT count(*) FROM market_trades WHERE buyer_account_id = %s OR seller_account_id = %s", (foreign, foreign)).fetchone()[0]
    centres = _dicts(db, "SELECT b.centre, v.value_per_share FROM investor_books b JOIN LATERAL (SELECT value_per_share FROM company_valuations"
                         " WHERE company_id = b.company_id ORDER BY period DESC LIMIT 1) v ON true WHERE b.account_id = %s", (foreign,))
    # With the budget used up, their prices are not marked up by their keenness (only their own small daily view).
    assert centres and all(c["centre"] * 10_000 <= c["value_per_share"] * (10_000 + data.INVESTORS[abroad.FOREIGN][1] + 1) for c in centres)
    assert mine == 0


# 7. Can a player pay money to, or take money from, the rest of the world's account?
def test_q7_nobody_can_trade_as_or_with_the_rest_of_the_world(db):
    abroad_account = ledger.account_id(db, abroad.ABROAD)
    assert db.execute("SELECT kind FROM ledger_accounts WHERE id = %s", (abroad_account,)).fetchone()[0] not in exchange.TRADER_KINDS
    with pytest.raises(exchange.ExchangeError):
        exchange.place_order(db, account=abroad_account, ticker="IKB", side="buy", kind="limit", quantity=1,
                             limit_price=2000, now=OPEN)
    # And it can never be overdrawn: the ledger refuses.
    player = trader(db, "ada", cash_naira=0)
    with pytest.raises(ledger.InsufficientFunds):
        ledger.transfer(db, payer=abroad_account, receiver=player, amount=ledger.balance(db, abroad_account) + 1,
                        kind="exports", memo="too much")


# 8. Can the groups' savings or debts drift away from the ledger, a kobo at a time?
def test_q8_the_groups_line_up_with_the_ledger_exactly(db):
    world = economy.load_world(db)
    groups = consumers.load(db)
    consumers.budgets(db, groups, world, _closed(db) + 1, borrowed={}, debt_service={}, moods={}, seed="x" * 32,
                      base_weights={"consumer": 1})
    for place, household in world.households.items():
        assert sum(g["cash"] for g in groups if g["location"] == place) == ledger.balance(db, household["account_id"])
    debts = {r["location"]: r["t"] for r in _dicts(db, "SELECT location, sum(principal)::bigint AS t FROM household_debts GROUP BY location")}
    for place in world.households:
        assert sum(g["debt"] for g in groups if g["location"] == place) == debts.get(place, 0)
    assert all(g["cash"] >= 0 and g["debt"] >= 0 for g in groups)


# 9. Can a world made before this upgrade be run by it, half-working and quietly wrong?
def test_q9_an_old_world_is_refused_plainly(db, monkeypatch):
    db.execute("DELETE FROM consumer_groups")
    with pytest.raises(economy.WorldTooOld, match="Start a new world"):
        consumers.load(db)
    with pytest.raises(economy.WorldTooOld):
        quarters.close_due_quarters(db, after_quarters(_closed(db) + 1))


def test_q9_a_world_without_the_rest_of_the_world_is_refused_plainly_too(db, monkeypatch):
    monkeypatch.setattr(abroad, "state", lambda conn, period: None)
    with pytest.raises(economy.WorldTooOld, match="rest of the world"):
        quarters.close_due_quarters(db, after_quarters(_closed(db) + 1))


# 10. Can news of the oil price or the naira be read before the figures it reports are public?
def test_q10_oil_and_naira_news_comes_out_with_the_figures_and_not_before(db):
    closed = _closed(db)
    was = _dicts(db, "SELECT * FROM abroad_results WHERE period = %s", (closed - 1,))[0]
    row = {**_dicts(db, "SELECT * FROM abroad_results WHERE period = %s", (closed,))[0],
           "oil_cents": was["oil_cents"] * 13 // 10, "fx": was["fx"] * 94 // 100, "reason": "The naira moved mostly on dearer oil."}
    news._abroad_news(db, closed, row, {"next_policy_rate_bps": 1300})
    # Dated in the quarter the figures belong to, after its first days: invisible on day 1, readable from its day.
    early = news.visible(db, closed + 1, news.DAY_ECONOMY - 1, limit=500)
    later = news.visible(db, closed + 1, news.DAY_ECONOMY, limit=500)
    assert not any(i["kind"] in ("oil_up", "naira_stronger") and i["period"] == closed + 1 for i in early)
    assert {"oil_up", "naira_stronger"} <= {i["kind"] for i in later if i["period"] == closed + 1}
    # Every oil or naira story ever printed reports the figures of the close before it.
    rows = {r["period"]: r for r in _dicts(db, "SELECT * FROM abroad_results")}
    for item in _dicts(db, "SELECT period, kind, facts FROM news_items WHERE kind IN ('oil_up', 'oil_down') AND period <= %s", (closed,)):
        assert item["facts"]["price"].startswith(f"${rows[item['period'] - 1]['oil_cents'] / 100:,.2f}")
