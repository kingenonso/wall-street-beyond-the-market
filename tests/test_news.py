"""The automatic news wire (design document, section 12).

Headlines come only from things that really happened. A player sees an item
only once its day has come. The wire does not repeat itself.
"""

from __future__ import annotations

import importlib
import re

import pytest
from psycopg.rows import dict_row

from simulation import clock, events, news, quarters
from simulation import world_data as data
from simulation.news_kinds import BY_NAME, KINDS, OUTLETS
from simulation.news_wordings import PER_OUTLET, check
from tests.conftest import after_quarters

MODULES = ("places", "happenings", "economy", "results", "capital", "deals", "dealmaking", "abroad", "property", "property2", "media", "banks", "funds", "etfs", "fx", "world")


def _dicts(db, sql, params=()):
    with db.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


# --- The wordings themselves ---

def test_every_kind_of_news_has_three_wordings_in_each_papers_voice_and_each_fills_in_cleanly():
    covered = []
    for name in MODULES:
        module = importlib.import_module(f"simulation.news_wordings.{name}")
        assert check(module.WORDINGS, module.KINDS) == [], name
        covered += module.KINDS
    assert sorted(covered) == sorted(kind.name for kind in KINDS) and len(covered) == len(set(covered)) == 146
    assert set(news.WORDINGS) == set(BY_NAME)
    total = sum(len(options) for kind in news.WORDINGS.values() for options in kind.values())
    assert total == 146 * 3 * PER_OUTLET == 1314
    # Every kind of event the world can produce has news to go with it.
    assert {kind.name for kind in events.KINDS} <= set(BY_NAME)


def test_no_wording_is_used_twice_anywhere():
    headlines = [h for kind in news.WORDINGS.values() for options in kind.values() for h, _ in options]
    bodies = [b for kind in news.WORDINGS.values() for options in kind.values() for _, b in options]
    assert len(set(headlines)) == len(headlines) and len(set(bodies)) == len(bodies)


def test_wordings_invent_nothing_and_name_no_real_thing():
    text = " ".join(part for kind in news.WORDINGS.values() for options in kind.values() for pair in options for part in pair)
    for banned in (r"\bAI\b", r"\bsimulation\b", r"\bplayers?\b", r"\bgame\b", r"\bsources? (say|said)\b", r"\bdead\b", r"\bkilled\b",
                   r"\binjur", r"\bhurt\b", r"\barrest", r"\bspokes", r"\b20\d\d\b", r"\bNaira\b(?! Ledger)", "—", ";"):
        assert not re.search(banned, text), banned
    # A wording carries no figure of its own: every number in a headline comes from the facts.
    for kind in news.WORDINGS.values():
        for options in kind.values():
            for headline, _ in options:
                assert not re.search(r"\d", re.sub(r"\{[a-z_]+\}", "", headline)), headline


# --- Only what really happened ---

@pytest.mark.world("eight")
def test_every_event_is_reported_on_its_day_and_nothing_is_reported_that_did_not_happen(db):
    happened = {(e["period"], e["day"], e["kind"]) for e in _dicts(db, "SELECT period, day, kind FROM events")}
    event_kinds = {kind.name for kind in events.KINDS}
    reported = {(n["period"], n["day"], n["kind"]) for n in _dicts(db, "SELECT period, day, kind FROM news_items") if n["kind"] in event_kinds}
    assert reported == happened and len(happened) >= 12


@pytest.mark.world("eight")
def test_figures_in_the_news_are_the_recorded_figures(db):
    rate = _dicts(db, "SELECT n.period, n.facts FROM news_items n WHERE kind LIKE 'rate_%%' AND outlet = 'ledger'")
    assert rate
    for item in rate:
        state = _dicts(db, "SELECT * FROM economy_results WHERE period = %s", (item["period"] - 1,))[0]
        assert item["facts"]["rate"] == news.percent(state["next_policy_rate_bps"])
        assert item["facts"]["old_rate"] == news.percent(state["policy_rate_bps"])
        assert item["facts"]["inflation"] == news.percent(state["inflation_bps"])
    losses = _dicts(db, "SELECT n.period, n.tickers, n.facts FROM news_items n WHERE kind = 'company_loss'")
    assert losses
    for item in losses:
        result = _dicts(db, "SELECT r.net_profit, r.revenue FROM company_results r JOIN companies c ON c.id = r.company_id"
                            " WHERE c.ticker = %s AND r.period = %s", (item["tickers"][0], item["period"] - 1))[0]
        assert result["net_profit"] < 0 and item["facts"]["profit"] == news.money_words(result["net_profit"])
        assert item["facts"]["sales"] == news.money_words(result["revenue"])
    for item in _dicts(db, "SELECT period, tickers, facts FROM news_items WHERE kind IN ('rating_upgrade', 'rating_downgrade')"):
        filed = dict(db.execute(
            "SELECT DISTINCT ON (r.period) r.period, r.credit_rating FROM company_reports r JOIN companies c ON c.id = r.company_id"
            " WHERE c.ticker = %s AND r.period IN (%s, %s) ORDER BY r.period, r.version DESC",
            (item["tickers"][0], item["period"] - 2, item["period"] - 1)).fetchall())
        assert (item["facts"]["old_rating"], item["facts"]["rating"]) == (filed[item["period"] - 2], filed[item["period"] - 1])


def test_a_flood_is_followed_by_its_bill_under_the_same_story(db):
    db.execute("INSERT INTO events (period, day, kind, location, sales_bps, damage_bps, mood_bps, severe)"
               " VALUES (1, 40, 'flood', %s, -700, 120, -300, true)", (data.LAGOS,))
    news.for_events(db, [e for e in events.load(db, 1) if e["kind"] == "flood" and e["location"] == data.LAGOS and e["day"] == 40])
    quarters.close_due_quarters(db, after_quarters(1))
    told = _dicts(db, "SELECT * FROM news_items WHERE kind IN ('flood', 'event_aftermath') AND %s = ANY(locations)"
                      " AND (kind = 'event_aftermath' OR day = 40) ORDER BY id", (data.LAGOS,))
    first, after = [t for t in told if t["kind"] == "flood"], [t for t in told if t["kind"] == "event_aftermath"]
    assert first and after and {t["story"] for t in first} == {t["story"] for t in after}
    assert all(t["period"] == 1 and t["day"] == 40 for t in first) and all(t["period"] == 2 for t in after)
    assert all("Lagos" in t["headline"] + t["body"] for t in first)
    # The bill printed is the bill in the ledger.
    paid = db.execute("SELECT sum(e.amount) FROM ledger_entries e JOIN ledger_transactions t ON t.id = e.transaction_id"
                      " JOIN companies c ON c.account_id = e.account_id WHERE t.kind = 'insurance_claim' AND e.amount > 0"
                      " AND c.headquarters = %s AND c.listed", (data.LAGOS,)).fetchone()[0]       # private companies' losses are not reported
    assert after[0]["facts"]["paid"] == news.money_words(int(paid))
    assert _dicts(db, "SELECT 1 FROM news_items WHERE kind = 'insurance_claims' AND period = 2")


# --- Nothing is seen before its day ---

def test_news_of_an_event_is_out_of_sight_until_its_day(db):
    made = _dicts(db, "SELECT period, day, headline FROM news_items ORDER BY day")
    assert made and all(item["period"] == 1 for item in made)          # the first quarter's events are already decided
    day = made[0]["day"]
    assert all(item["day"] >= day for item in made)
    assert [n["headline"] for n in news.visible(db, 1, day - 1)] == []
    seen = news.visible(db, 1, day)
    assert seen and all(n["day"] <= day for n in seen)
    assert len(news.visible(db, 2, 1, limit=120)) == len(made)          # once the quarter is over, all of it


@pytest.mark.world("eight")
def test_the_news_page_never_shows_the_future(client, player, monkeypatch):
    from server import main

    def on(year, quarter, day):
        monkeypatch.setattr(main.clock, "game_date", lambda *_: clock.GameDate(year=year, quarter=quarter, day_of_quarter=day))
        return client.get("/api/news?limit=120").json()["items"]

    # Quarter 9 (Year 3 Q1) is running. Its events are decided and stored, with their news.
    early, later = on(3, 1, 2), on(3, 1, 90)
    assert early and all((item["period"], item["day"]) <= (9, 2) for item in early)
    assert len(later) >= len(early)
    assert not any(item["period"] > 9 for item in later)
    # Nothing in the answer says how many items are still to come, or carries the stored facts.
    raw = client.get("/api/news").text
    for hidden in ('"id"', '"facts"', '"wording"', "sales_bps", "damage_bps", "fortune"):
        assert hidden not in raw
    # Before the world's first day there is no news at all.
    monkeypatch.setattr(main.clock, "game_date", lambda *_: None)
    assert client.get("/api/news").json()["items"] == []


@pytest.mark.world("eight")
def test_the_news_page_can_be_read_by_paper_and_by_company_and_only_when_logged_in(client, player, monkeypatch):
    from server import main
    monkeypatch.setattr(main.clock, "game_date", lambda *_: clock.GameDate(year=3, quarter=1, day_of_quarter=30))
    everything = client.get("/api/news?limit=120").json()
    assert everything["outlets"] == list(OUTLETS.values())
    assert {item["outlet"] for item in everything["items"]} == set(OUTLETS.values())
    ledger_only = client.get("/api/news", params={"outlet": "The Naira Ledger"}).json()["items"]
    assert ledger_only and {item["outlet"] for item in ledger_only} == {"The Naira Ledger"}
    ticker = next(item["tickers"][0] for item in everything["items"] if len(item["tickers"]) == 1)
    about = client.get("/api/news", params={"ticker": ticker}).json()["items"]
    assert about and all(ticker in item["tickers"] for item in about)
    ordered = [(item["period"], item["day"]) for item in everything["items"]]
    assert ordered == sorted(ordered, reverse=True)                       # newest first
    assert client.get("/api/news", params={"outlet": "The Daily Nothing"}).status_code == 404
    for bad in ({"ticker": "idc'; DROP TABLE news_items;--"}, {"limit": 100000}, {"limit": 0}, {"ticker": "x" * 500}):
        assert client.get("/api/news", params=bad).status_code == 422
    client.cookies.clear()
    assert client.get("/api/news").status_code == 401


def test_news_cannot_be_written_by_a_player(client, player):
    for method in ("POST", "PUT", "PATCH", "DELETE"):
        assert client.request(method, "/api/news", json={"headline": "Buy IDC now"}).status_code == 405


# --- It does not repeat itself ---

@pytest.mark.world("eight")
def test_a_paper_never_uses_the_same_wording_twice_running_for_one_kind_of_news(db):
    last: dict = {}
    for item in _dicts(db, "SELECT kind, outlet, facts->>'wording' AS wording FROM news_items ORDER BY period, day, id"):
        key = (item["kind"], item["outlet"])
        assert last.get(key) != item["wording"], key
        last[key] = item["wording"]


@pytest.mark.world("eight")
def test_headlines_are_varied_and_the_bigger_the_story_the_more_papers_carry_it(db):
    items = _dicts(db, "SELECT * FROM news_items")
    assert len(items) > 200
    assert len({item["headline"] for item in items}) > len(items) * 9 // 10
    assert len({item["kind"] for item in items}) >= 30
    coverage: dict = {}
    for item in items:
        coverage.setdefault((item["story"], item["kind"], item["period"], item["day"], item["importance"]), set()).add(item["outlet"])
    for (_, _, _, _, importance), papers in coverage.items():
        assert len(papers) == (3 if importance >= 80 else 2 if importance >= 60 else 1)
    assert all(0 <= item["importance"] <= 100 and 1 <= item["day"] <= 90 for item in items)


@pytest.mark.world("eight")
def test_small_items_are_gathered_and_seasonal_swings_do_not_flood_the_page(db):
    for period in range(3, 10):
        count = dict(db.execute("SELECT kind, count(DISTINCT story) FROM news_items WHERE period = %s GROUP BY kind", (period,)).fetchall())
        assert count.get("results_strong", 0) <= news.MOST_RESULT_STORIES and count.get("results_weak", 0) <= news.MOST_RESULT_STORIES
        assert count.get("roundup_results", 0) <= 1 and count.get("roundup_jobs", 0) <= 1
    assert _dicts(db, "SELECT 1 FROM news_items WHERE kind = 'roundup_results'")


def test_helpers_write_figures_the_way_a_newspaper_would():
    assert news.money_words(340_000_000_000) == "₦3.4 billion" and news.money_words(-120_000_000_00) == "₦120 million"
    assert news.percent(650) == "6.5%" and news.percent(-1200) == "12%"
    assert news.people(1234) == "about 1,200" and news.people(-87_400) == "about 87,000"
    assert news.names(["A"], "others") == "A" and news.names(["A", "B", "C"], "others") == "A, B and C"
    assert news.names(["A", "B", "C", "D", "E"], "other companies", " based there") == "A, B and 3 other companies based there"
    assert news.number_word(6) == "six" and news.number_word(39) == "39" and news.ordinal(3) == "third"
    assert [news.ordinal(n) for n in (11, 12, 13, 21, 22, 23, 24, 101, 111)] == \
           ["11th", "12th", "13th", "21st", "22nd", "23rd", "24th", "101st", "111th"]
    assert news.signed_percent(-475) == "-4.8%" and news.signed_percent(475) == "4.8%"
    with pytest.raises(ValueError):
        news.publish(None, period=1, day=1, kind="flood", story="x", facts={"location": "Lagos"})      # a fact is missing


# --- Found by the independent review of Part B ---

@pytest.mark.world("eight")
def test_what_is_visible_today_never_depends_on_what_is_still_hidden(db):
    """The review inferred coming events from which wording a visible item used: the rule
    'never the same wording twice running' looked at items dated later. Now it looks only backwards."""
    event_kinds = tuple(kind.name for kind in events.KINDS)
    items = _dicts(db, "SELECT id, period, day, kind, outlet FROM news_items WHERE kind = ANY(%s) ORDER BY id", (list(event_kinds),))
    by_period: dict = {}
    for item in items:
        by_period.setdefault(item["period"], []).append(item["day"])
    assert all(days == sorted(days) for days in by_period.values())          # each quarter's event news is written in date order
    # No story name carries an internal id.
    stories = [s for (s,) in db.execute("SELECT DISTINCT story FROM news_items").fetchall()]
    assert not any(re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-", story) for story in stories)


def test_a_fall_in_prices_is_never_printed_as_a_rise_of_the_same_size(db):
    assert news.signed_percent(-475) == "-4.8%"
    quarters.close_due_quarters(db, after_quarters(2))
    for item in _dicts(db, "SELECT period, facts FROM news_items WHERE kind LIKE 'rate_%%'"):
        recorded = db.execute("SELECT inflation_bps FROM economy_results WHERE period = %s", (item["period"] - 1,)).fetchone()[0]
        assert item["facts"]["inflation"] == news.signed_percent(recorded)
