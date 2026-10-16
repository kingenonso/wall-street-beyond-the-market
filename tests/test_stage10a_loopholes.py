"""Stage 10, Part 1: ten ways a player might try to game the newsroom, each closed."""

from __future__ import annotations

from datetime import timedelta

import pytest
from psycopg.rows import dict_row

from simulation import careers, derivatives, events, exchange, ledger, lending, newsroom, newsroom_facts
from simulation import world_data as data
from tests.conftest import ADULT, join
from tests.test_builds import pro
from tests.test_careers import NOW9
from tests.test_firm import firm_of
from tests.test_newsroom import LATER, results_card, write

pytestmark = pytest.mark.world("eight")


def _one(db, sql, params=()):
    with db.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(sql, params).fetchall()
    return rows[0] if rows else None


def reporter(client, db):
    assert join(client, ADULT).status_code == 201
    player = _one(db, "SELECT id FROM players WHERE display_name = 'Ada'")["id"]
    client.put("/api/career/build", json={"build": "journalist"})
    client.put("/api/career/bank", json={"ticker": "IKB"})
    client.put("/api/career/job", json={"ticker": "ONN"})
    return player


# 1. Can a player put a figure in print that is not on the record?
def test_l1_no_figure_reaches_print_except_from_the_record(db, client):
    reporter(client, db)
    assert client.post("/api/newsroom/story").status_code == 201
    card = results_card(db)
    client.post("/api/newsroom/facts", json={"fact_id": card["id"]})
    refused = client.put("/api/newsroom/words", json={"angle": "straight", "comment": "Profit will triple next year, 300 percent", "declared": False})
    assert refused.status_code == 409 and "figure" in refused.json()["detail"]
    sneaky = client.put("/api/newsroom/words", json={"angle": "straight", "comment": "Fine.", "declared": False, "headline": "₦9 trillion profit"})
    assert sneaky.status_code == 422                      # no headline of one's own
    client.post("/api/newsroom/check", json={"fact_id": card["id"]})
    published = client.post("/api/newsroom/publish").json()["result"]
    assert "news_item_id" not in published                       # no item numbers leave the server
    body = _one(db, "SELECT headline, body FROM news_items WHERE story = %s", (f"story:{published['story_id']}",))
    from simulation import articles
    allowed = {str(v) for v in card["figures"].values()} | {card["line"], card["title"]}
    assert articles.check(body["headline"] + " " + body["body"].split(" By ")[0], allowed) == []


# 2. Can a journalist report something still to come?
def test_l2_no_fact_from_the_future(db):
    j, _ = pro(db, "journalist", "seer", level=10)
    w = careers.world_now(db, NOW9)
    future = [e for e in events.load(db, w["period"]) if e["day"] > w["day"]]
    ids = {c["id"] for c in newsroom_facts.facts(db, NOW9)}
    assert not any(f"event:{e['id']}" in ids for e in future)
    newsroom.start(db, j, NOW9)
    for e in future[:1]:
        with pytest.raises(newsroom.NewsroomError, match="not a confirmed fact"):
            newsroom.add_fact(db, j, f"event:{e['id']}", NOW9)
    with pytest.raises(newsroom.NewsroomError, match="not a confirmed fact"):
        newsroom.add_fact(db, j, f"results:IDC:{w['period']}", NOW9)          # this quarter's results are not filed yet


# 3. Can the author trade around the story another way: options, a short, preferred shares, or through the empire?
def test_l3_no_trading_around_ones_own_story_by_any_route(db):
    empire, team = firm_of(db)
    j = team["journalist"]
    account = ledger.player_account_id(db, j)
    ledger.transfer(db, payer=ledger.account_id(db, ledger.TREASURY), receiver=account, amount=10**10, kind="test_cash", memo="Test cash")
    db.execute("UPDATE careers SET experience = %s WHERE player_id = %s", (careers.experience_for(30), j))
    card = next(c for c in newsroom_facts.facts(db, NOW9) if c["kind"] == "results"
                and _one(db, "SELECT 1 AS x FROM derivative_series s WHERE s.underlying = %s AND s.status = 'open'", (c["tickers"][0],)))
    ticker = card["tickers"][0]
    company = _one(db, "SELECT id FROM companies WHERE ticker = %s", (ticker,))["id"]
    newsroom.start(db, j, NOW9)
    newsroom.add_fact(db, j, card["id"], NOW9)
    series = _one(db, "SELECT id FROM derivative_series WHERE underlying = %s AND status = 'open' LIMIT 1", (ticker,))["id"]
    with pytest.raises(derivatives.DerivativesError, match="No trading in this company"):
        derivatives.trade(db, account, series, "buy", 1, LATER, player_id=j)
    with pytest.raises(lending.LendingError, match="No trading in this company"):
        lending.open_short(db, account, ticker, 10, LATER, player_id=j)
    newsroom.check_trade(db, ledger.player_account_id(db, team["accountant"]), company, LATER)    # a colleague's own account is free
    with pytest.raises(exchange.ExchangeError):
        newsroom.check_trade(db, empire["account_id"], company, LATER)                               # the empire's is not


# 4. Can journalists flood a company with nudges?
def test_l4_nudges_are_capped(db):
    j, _ = pro(db, "journalist", "flooder", level=10)
    cards = [c for c in newsroom_facts.facts(db, NOW9) if c["kind"] == "results" and c["tone"] != 0]
    for c in cards[:data.STORIES_A_DAY]:
        write(db, j, [c])
    newsroom.start(db, j, NOW9)
    newsroom.add_fact(db, j, cards[data.STORIES_A_DAY]["id"], NOW9)
    newsroom.check_fact(db, j, cards[data.STORIES_A_DAY]["id"], NOW9)
    with pytest.raises(newsroom.NewsroomError, match="At most"):
        newsroom.publish(db, j, NOW9)
    # A story about many companies moves none; and the push never passes the cap however many readers.
    k, _ = pro(db, "journalist", "wide", level=10)
    many = write(db, k, cards[4:8])
    assert many["nudges"] == []
    assert all(abs(n) <= data.NUDGE_MOST_BPS for n in newsroom.nudges_today(db, exchange.session_of(NOW9)[0]).values())


# 5. Can a scoop be claimed twice?
def test_l5_one_scoop_per_fact(db):
    j, _ = pro(db, "journalist", "twice", level=10)
    card = results_card(db)
    first = write(db, j, [card])
    assert first["scoop"]
    with pytest.raises(newsroom.NewsroomError, match="already published"):
        write(db, j, [card], now=NOW9)                                        # the same fact again: not news
    newsroom.drop(db, j, NOW9)
    # A second scoop the same game day is a scoop, but its bonus and reputation are paid once a day.
    rep = _one(db, "SELECT reputation FROM players WHERE id = %s", (j,))["reputation"]
    other = [c for c in newsroom_facts.facts(db, NOW9) if c["kind"] == "results"][1]
    second = write(db, j, [other], now=NOW9)
    assert second["scoop"] and first["paid"] > 0 and second["paid"] == 0
    assert _one(db, "SELECT reputation FROM players WHERE id = %s", (j,))["reputation"] == rep


# 6. Can anyone see another journalist's draft, or what an empire held?
def test_l6_drafts_and_holdings_stay_private(db, client):
    empire, team = firm_of(db)
    newsroom.start(db, team["journalist"], NOW9)
    newsroom.add_fact(db, team["journalist"], results_card(db)["id"], NOW9)
    reporter(client, db)
    desk = client.get("/api/newsroom").json()["desk"]
    assert desk["draft"] is None
    stories = client.get("/api/stories").text
    assert "held" not in stories and "story_interests" not in stories
    assert client.get("/api/newsroom/facts").status_code == 200


# 7. Can a question be answered by someone else, or after the deadline?
def test_l7_only_the_head_answers_in_time(db):
    empire, team = firm_of(db)
    j, _ = pro(db, "journalist", "asker", level=10)
    card = results_card(db)
    company = _one(db, "SELECT id FROM companies WHERE ticker = %s", (card["tickers"][0],))["id"]
    db.execute("INSERT INTO stake_disclosures (empire_id, company_id, bps, at) VALUES (%s, %s, 500, %s)", (empire["id"], company, NOW9))
    newsroom.start(db, j, NOW9)
    newsroom.add_fact(db, j, card["id"], NOW9)
    newsroom.ask(db, j, ticker=None, empire_name=empire["name"], question="Is the empire buying more?", now=NOW9)
    q = newsroom.to_answer(db, team["head"], NOW9)[0]
    with pytest.raises(newsroom.NewsroomError, match="not yours"):
        newsroom.answer(db, team["journalist"], q["id"], "Yes.", NOW9)
    with pytest.raises(newsroom.NewsroomError, match="closed"):
        newsroom.answer(db, team["head"], q["id"], "Yes.", NOW9 + timedelta(hours=data.INTERVIEW_HOURS + 1))
    with pytest.raises(newsroom.NewsroomError, match="own empire"):
        newsroom.drop(db, j, NOW9)
        newsroom.start(db, team["journalist"], NOW9)
        newsroom.ask(db, team["journalist"], ticker=None, empire_name=empire["name"], question="Our own plans, please?", now=NOW9)


# 8. Can a correction be dodged?
def test_l8_a_published_story_cannot_be_withdrawn_and_a_late_correction_costs_more(db):
    from psycopg.types.json import Jsonb
    j, _ = pro(db, "journalist", "dodger", level=10)
    card = results_card(db)
    out = write(db, j, [card])
    with pytest.raises(newsroom.NewsroomError, match="no story in hand"):
        newsroom.drop(db, j, NOW9)
    _, company_id, period, version = card["source"].split(":")
    old = _one(db, "SELECT * FROM company_reports WHERE company_id = %s AND period = %s AND version = %s", (company_id, int(period), int(version)))
    db.execute("INSERT INTO company_reports (company_id, period, version, figures, credit_rating, rating_reasons, filed_by)"
               " VALUES (%s, %s, %s, %s, %s, %s, 'restated')",
               (company_id, int(period), int(version) + 1, Jsonb(old["figures"]), old["credit_rating"], Jsonb(old["rating_reasons"])))
    newsroom.tick(db, LATER)
    rep = _one(db, "SELECT reputation FROM players WHERE id = %s", (j,))["reputation"]
    newsroom.tick(db, LATER + timedelta(hours=data.CORRECTION_HOURS + 1))
    assert _one(db, "SELECT reputation FROM players WHERE id = %s", (j,))["reputation"] == rep - data.LATE_CORRECTION_REPUTATION
    newsroom.tick(db, LATER + timedelta(hours=data.CORRECTION_HOURS + 2))          # charged once
    assert _one(db, "SELECT reputation FROM players WHERE id = %s", (j,))["reputation"] == rep - data.LATE_CORRECTION_REPUTATION
    newsroom.correct(db, j, out["story_id"], LATER + timedelta(hours=30))           # still corrected, at no further cost
    assert _one(db, "SELECT reputation FROM players WHERE id = %s", (j,))["reputation"] == rep - data.LATE_CORRECTION_REPUTATION


# 9. Can the archive, an article or "Why?" show what is still to come?
def test_l9_nothing_from_later_in_the_quarter_is_shown(db, client):
    reporter(client, db)
    w = careers.world_now(db, db.execute("SELECT now()").fetchone()[0])            # the server's own clock
    future = _one(db, "SELECT * FROM news_items WHERE (period, day) > (%s, %s) ORDER BY id LIMIT 1", (w["period"], w["day"]))
    if future:
        from server.main import news_ref
        assert client.get("/api/news/article", params={"ref": news_ref(future)}).status_code == 404
        words = future["headline"].split()[0]
        found = client.get("/api/news/archive", params={"q": words}).json()["items"]
        assert all(i["ref"] != news_ref(future) for i in found)
    # No item's number is ever sent: numbers would show how many items are still to come.
    assert '"id"' not in client.get("/api/news/archive").text and '"id"' not in client.get("/api/news").text
    later = _one(db, "SELECT max(period) AS p FROM ripple_links")["p"] or 0
    assert client.get("/api/why", params={"key": "rate:8"}).status_code == 200
    assert later <= w["period"]


# 10. Can exposing be used to farm reputation or to harm an honest journalist?
def test_l10_exposing_is_once_per_story_and_a_false_alarm_costs_the_accuser(db):
    j, _ = pro(db, "journalist", "honest", level=10)
    out = write(db, j, [results_card(db)])
    accuser, _ = pro(db, "accountant", "accuser", level=10)
    rep = _one(db, "SELECT reputation FROM players WHERE id = %s", (accuser,))["reputation"]
    j_rep = _one(db, "SELECT reputation FROM players WHERE id = %s", (j,))["reputation"]
    assert not newsroom.expose(db, accuser, out["story_id"], LATER)["upheld"]
    assert _one(db, "SELECT reputation FROM players WHERE id = %s", (accuser,))["reputation"] == rep - 1
    assert _one(db, "SELECT reputation FROM players WHERE id = %s", (j,))["reputation"] == j_rep
    with pytest.raises(newsroom.NewsroomError, match="already raised"):
        newsroom.expose(db, accuser, out["story_id"], LATER)
    with pytest.raises(newsroom.NewsroomError, match="your own"):
        newsroom.expose(db, j, out["story_id"], LATER)


# Review fix: a story that repeats what the wire already carries is old news, and moves no price.
def test_review_a_story_repeating_the_wire_moves_no_price(db):
    w = careers.world_now(db, NOW9)
    j, _ = pro(db, "journalist", "repeater", level=10)
    on_wire = [c for c in newsroom_facts.facts(db, NOW9) if c["kind"] == "results" and c["tone"] != 0
               and newsroom._on_wire(db, c, w["period"], w["day"])]
    if not on_wire:
        pytest.skip("no results on the wire in this world")
    out = write(db, j, [on_wire[0]])
    assert not out["scoop"] and out["nudges"] == []
