"""The redesign: the ten-question loophole check, one test (or more) for each question.

Players may commit crimes against each other's empires, but never against the game: no money from
nowhere, no seeing what is hidden, no acting as somebody else, no beating the clock.
"""

from __future__ import annotations

from datetime import timedelta

import psycopg
import pytest

from simulation import careers, clock, ledger, marketview, messages, news, objectives
from simulation import world_data as data
from tests.conftest import ADULT, join, money_accounted_for
from tests.test_careers import NOW9, professional
from tests.test_redesign import _dicts, trade_days

pytestmark = pytest.mark.world("eight")


# 1. Can the settings route change anything but the player's own look, sound and tour, or anybody else's?
def test_q1_settings_reach_only_the_players_own_four_columns(db, client):
    other, _ = professional(db, "other", now=NOW9)
    assert join(client, ADULT).status_code == 201
    for sneaky in ({"theme": "light", "cash": 1}, {"theme": "light", "reputation": 100}, {"theme": "light", "id": str(other)},
                   {"theme": "light", "build": "investment_banker"}, {"theme": "light", "news_alerts": False}):
        assert client.patch("/api/me/settings", json=sneaky).status_code == 422
    before = ledger.amount_in_existence(db)
    assert client.patch("/api/me/settings", json={"theme": "light"}).status_code == 200
    assert ledger.amount_in_existence(db) == before == money_accounted_for(db)
    assert _dicts(db, "SELECT theme FROM players WHERE id = %s", (other,))[0]["theme"] == "dark"


# 2. Can "How to do this" give away an answer before the work is done?
def test_q2_the_method_is_the_same_for_everybody_and_holds_no_figures_of_the_work(db):
    a, _ = professional(db, "alpha", now=NOW9)
    b, _ = professional(db, "bravo", employer="OTB", now=NOW9)
    for code in ("ac_ratios", "ac_cash_flow"):
        one = objectives.accept(db, a, code, NOW9)
        two = objectives.accept(db, b, code, NOW9)
        how_a = next(o for o in objectives.board(db, a, NOW9)["active"] if o["id"] == one["id"])["how"]
        how_b = next(o for o in objectives.board(db, b, NOW9)["active"] if o["id"] == two["id"])["how"]
        assert how_a == how_b == objectives.how_to(objectives.TEMPLATES[code])
        for row in _dicts(db, "SELECT terms FROM objectives WHERE id = ANY(%s)", ([one["id"], two["id"]],)):
            truth = row["terms"].get("_truth", {})
            for value in (truth.values() if isinstance(truth, dict) else []):
                if isinstance(value, (int, float)) and abs(value) >= 10:
                    assert f"{value:,.2f}" not in how_a and f"{value:.1f}" not in how_a
    # Methods are read only from fixed words in the judging code: a method built from a piece of work's own
    # figures (an f-string) is never offered before the work is done.
    assert objectives.how_to(objectives.TEMPLATES["ce_buy"]) is None


# 3. Can the price move shown beside a story come from a story that is not out yet, or from hidden prices?
def test_q3_moves_come_only_with_stories_already_out_and_from_public_prices(db, client):
    traded = trade_days(db)
    assert join(client, ADULT).status_code == 201
    seen = client.get("/api/news", params={"limit": 120}).json()["items"]
    assert all(set(i["moves"]) <= set(i["tickers"]) for i in seen)
    # Every company named with a move is listed on the exchange: no private company's worth leaks out.
    listed = {r["ticker"] for r in _dicts(db, "SELECT c.ticker FROM companies c JOIN market_instruments m ON m.company_id = c.id")}
    assert {t for i in seen for t in i["moves"]} <= listed
    # Directly: a story dated tomorrow shows no move, and a private company named in a story never does.
    world = _dicts(db, "SELECT world_start, weeks_ahead FROM world_state")[0]
    start = clock.effective_start(world["world_start"], world["weeks_ahead"])
    # (A fixed moment just after the test's trading days, not today's date: with today's date the test stopped working
    # once the trades it makes fell more than a fortnight before the running quarter.)
    from tests.test_market import OPEN
    now = OPEN + timedelta(days=6)
    quarter = timedelta(days=clock.REAL_DAYS_PER_QUARTER)
    elapsed = now - start
    period = elapsed // quarter + 1
    today = int((elapsed - (period - 1) * quarter) / quarter * clock.GAME_DAYS_PER_QUARTER) + 1
    tomorrow = {"period": period, "day": today + 2, "tickers": [traded]}
    assert news.price_moves(db, [tomorrow], start, now) == {}
    later = now + timedelta(days=3650)
    assert news.price_moves(db, [tomorrow], start, later)                      # the same story, once out, does show one
    private = [r["ticker"] for r in _dicts(db, "SELECT ticker FROM companies WHERE NOT listed")]
    assert private
    assert news.price_moves(db, [{**tomorrow, "tickers": private[:6]}], start, later) == {}


# 4. Can the command bar's list of companies show a private company, or anything but public facts?
def test_q4_the_ticker_shows_only_listed_companies_and_public_facts(db, client):
    assert join(client, ADULT).status_code == 201
    shares = client.get("/api/market/ticker").json()["shares"]
    listed = {r["ticker"] for r in _dicts(db, "SELECT c.ticker FROM companies c JOIN market_instruments m ON m.company_id = c.id")}
    assert {s["ticker"] for s in shares} == listed
    private = {r["ticker"] for r in _dicts(db, "SELECT ticker FROM companies WHERE NOT listed")}
    assert private and not private & {s["ticker"] for s in shares}
    assert set(shares[0]) == {"ticker", "name", "sector", "price_kobo", "change_bps", "traded_today"}


# 5. Can the faster early levels carry a player past the Level 20 gate, or to more pay sooner than before above Level 10?
def test_q5_the_gate_holds_and_nothing_above_level_ten_comes_cheaper_than_before_at_level_twenty(db):
    player, _ = professional(db, now=NOW9)
    careers.add_experience(db, player, "asset_manager", 10**8, NOW9)
    assert careers.career(db, player)["level"] == 20                                   # the rank case is still needed
    for level in range(20, 101):
        assert careers.experience_for(level) == data.LEVEL_EXPERIENCE * level * (level - 1)
    for level in range(2, 20):
        assert careers.experience_for(level) <= data.LEVEL_EXPERIENCE * level * (level - 1)


# 6. Can the counts behind the dots (work in hand, a rank case, messages) tell a player about anybody else?
def test_q6_the_dots_count_only_the_players_own_things(db, client):
    other, _ = professional(db, "other", now=NOW9)
    objectives.accept(db, other, "ac_ratios", NOW9)
    assert join(client, ADULT).status_code == 201
    me = client.get("/api/me").json()
    assert me["work_in_hand"] == 0 and me["rank_waiting"] is False and me["unread_messages"] == 0


# 7. Can a bad value reach the database by another way than the route (volume out of range, a made-up theme)?
def test_q7_the_database_itself_refuses_settings_out_of_range(db):
    player, _ = professional(db, now=NOW9)
    for sql in ("UPDATE players SET sound_volume = 101 WHERE id = %s", "UPDATE players SET sound_volume = -1 WHERE id = %s",
                "UPDATE players SET theme = 'neon' WHERE id = %s"):
        with pytest.raises(psycopg.errors.CheckViolation):
            db.execute(sql, (player,))


# 8. Can the small trend lines show a price that has not happened, or a private company's?
def test_q8_the_trend_lines_are_only_real_closes_of_listed_shares(db):
    trade_days(db)
    closes = marketview.recent_closes(db)
    listed = {r["id"] for r in _dicts(db, "SELECT company_id AS id FROM market_instruments")}
    assert set(closes) <= listed
    for company, prices in closes.items():
        real = [r["price"] for r in _dicts(db, "SELECT DISTINCT ON (session_date) session_date, price / split_factor(company_id, id) AS price"
                                               " FROM market_trades WHERE company_id = %s ORDER BY session_date DESC, id DESC LIMIT 5", (company,))]
        assert prices == [int(p) for p in reversed(real)]


# 9. Can the one-question-at-a-time screen hand a piece of work in twice, or answer somebody else's?
def test_q9_a_piece_of_work_is_handed_in_once_and_only_by_its_owner(db, client):
    assert join(client, ADULT).status_code == 201
    other, _ = professional(db, "other", now=NOW9)
    theirs = objectives.accept(db, other, "ac_ratios", NOW9)
    refused = client.post(f"/api/objectives/{theirs['id']}/hand-in", json={"answers": {"ebitda": 1, "margin": 1, "debt_to_ebitda": 1, "interest_cover": 1}})
    assert refused.status_code in (404, 409)
    assert _dicts(db, "SELECT state, submission FROM objectives WHERE id = %s", (theirs["id"],))[0] == {"state": "active", "submission": None}


# 10. Can anybody see another player's settings (their look, sound or whether they took the tour)?
def test_q10_settings_are_never_shown_to_anybody_else(db, client):
    other, _ = professional(db, "otherplayer", now=NOW9)
    db.execute("UPDATE players SET theme = 'light', tour_done = true WHERE id = %s", (other,))
    assert join(client, ADULT).status_code == 201
    me = client.get("/api/me").json()
    messages.send(db, other, "Ada", "Hello", NOW9)
    for path in ("/api/messages", "/api/messages/with?name=otherplayer", "/api/ranks", "/api/empires", "/api/firms",
                 "/api/deals/league", "/api/market", "/api/corporate/ownership"):
        body = client.get(path)
        assert body.status_code == 200, path            # every page looked at really answered
        text = body.text
        assert '"theme"' not in text and '"tour_done"' not in text and '"sound_volume"' not in text, path
    assert me["theme"] == "dark"
