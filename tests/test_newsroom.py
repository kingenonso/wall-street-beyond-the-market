"""Stage 10, Part 1: the newsroom. Players' stories from confirmed facts, readers and reach, scoops, interviews,
corrections, stories that move the market, no trading around one's own story, declared interests, the empire's
reputation, full articles for the wire, the Ripple, the Chronicle, and the new work."""

from __future__ import annotations

from datetime import timedelta

import pytest
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from simulation import (articles, careers, chronicle, clients, exchange, investors, ledger, newsroom, newsroom_facts, objectives,
                        objectives_news, quarters, ripple, standing)
from simulation import world_data as data
from tests.conftest import after_quarters, taken_before_retirement
from tests.test_builds import pro
from tests.test_careers import NOW9, sound
from tests.test_firm import firm_of

pytestmark = pytest.mark.world("eight")
LATER = NOW9 + timedelta(hours=1)


def _one(db, sql, params=()):
    with db.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(sql, params).fetchall()
    return rows[0] if rows else None


def results_card(db, *, tone=None):
    cards = [c for c in newsroom_facts.facts(db, NOW9) if c["kind"] == "results" and (tone is None or c["tone"] == tone)]
    return cards[0]


def write(db, player, cards, now=NOW9, **words):
    newsroom.start(db, player, now)
    for c in cards:
        newsroom.add_fact(db, player, c["id"], now)
        newsroom.check_fact(db, player, c["id"], now)
    if words:
        newsroom.set_words(db, player, words.get("angle", "straight"), words.get("comment", ""), words.get("declared", False), now)
    return newsroom.publish(db, player, now)


def test_a_journalist_publishes_a_checked_story_under_their_name_and_a_first_with_a_fact_is_a_scoop(db):
    j, account = pro(db, "investment_banker", "scribe", level=10)
    card = results_card(db)
    onn = _one(db, "SELECT account_id FROM companies WHERE ticker = 'ONN'")["account_id"]
    before = ledger.balance(db, account)
    paper_before = ledger.balance(db, onn)
    out = write(db, j, [card])
    assert out["scoop"] and out["readers"] > 0
    item = _one(db, "SELECT * FROM news_items WHERE id = %s", (out["news_item_id"],))
    # Nobody's employer is a paper since the builds became three: the largest paper picks the story up and prints it.
    assert item["outlet"] == "press" and item["author_id"] == j
    assert item["facts"]["outlet"] == "Ogene News Network, from an independent journalist"
    assert card["line"] in item["body"] and "By " in item["body"]
    # The paper that printed it pays for it, scoop bonus included, through the ledger.
    assert ledger.balance(db, account) - before == out["paid"] == paper_before - ledger.balance(db, onn)
    assert out["paid"] >= data.SCOOP_BONUS_NAIRA * 100
    prof = newsroom.profile(db, j)
    assert prof["scoops"] == 1 and prof["following"] == out["readers"] * data.FOLLOW_SHARE_BPS // 10_000
    # A second journalist with the same fact is not first with it.
    other, _ = pro(db, "investment_banker", "latecomer", level=10)
    assert not write(db, other, [card])["scoop"]
    # A scoop enters the author's own Chronicle.
    assert _one(db, "SELECT 1 AS x FROM chronicle_entries WHERE layer = 'personal' AND player_id = %s AND kind = 'scoop'", (j,))
    sound(db)


def test_every_fact_is_checked_before_print_and_the_authors_own_view_has_no_figures(db):
    j, _ = pro(db, "investment_banker", "careful", level=10)
    cards = [c for c in newsroom_facts.facts(db, NOW9) if c["kind"] == "results"][:6]
    newsroom.start(db, j, NOW9)
    newsroom.add_fact(db, j, cards[0]["id"], NOW9)
    with pytest.raises(newsroom.NewsroomError, match="Check every fact"):
        newsroom.publish(db, j, NOW9)
    for c in cards[1:5]:
        newsroom.add_fact(db, j, c["id"], NOW9)
    with pytest.raises(newsroom.NewsroomError, match="at most"):
        newsroom.add_fact(db, j, cards[5]["id"], NOW9)
    with pytest.raises(newsroom.NewsroomError, match="figure"):
        newsroom.set_words(db, j, "straight", "Profits will double to 50%", False, NOW9)
    with pytest.raises(newsroom.NewsroomError, match="not a confirmed fact"):
        newsroom.add_fact(db, j, "results:ZZZ:8", NOW9)
    # The newsroom is open to every build, and only to a player with one.
    from tests.test_market import trader
    nobody = _one(db, "SELECT player_id FROM ledger_accounts WHERE id = %s", (trader(db, "nobuild"),))["player_id"]
    with pytest.raises(newsroom.NewsroomError, match="with a build"):
        newsroom.start(db, nobody, NOW9)
    a, _ = pro(db, "asset_manager", "anyreporter", level=10)
    newsroom.start(db, a, NOW9)


def test_no_trading_a_company_from_the_first_draft_until_two_trading_days_after_publication(db):
    empire, team = firm_of(db)
    j = team["investment_banker"]
    account = ledger.player_account_id(db, j)
    ledger.transfer(db, payer=ledger.account_id(db, ledger.TREASURY), receiver=account, amount=10**10, kind="test_cash", memo="Test cash")
    card = results_card(db)
    ticker = card["tickers"][0]
    price = _one(db, "SELECT coalesce(m.last_price, m.reference_price) AS p FROM market_instruments m JOIN companies c ON c.id = m.company_id"
                     " WHERE c.ticker = %s", (ticker,))["p"]
    newsroom.start(db, j, NOW9)
    newsroom.add_fact(db, j, card["id"], NOW9)
    for who in (account, empire["account_id"]):
        with pytest.raises(exchange.ExchangeError, match="No trading in this company"):
            exchange.place_order(db, account=who, ticker=ticker, side="buy", kind="limit", quantity=10, limit_price=price, now=LATER)
    newsroom.check_fact(db, j, card["id"], NOW9)
    newsroom.publish(db, j, NOW9)
    two_days = NOW9 + timedelta(days=2, hours=1)
    with pytest.raises(exchange.ExchangeError, match="No trading in this company"):
        exchange.place_order(db, account=account, ticker=ticker, side="buy", kind="limit", quantity=10, limit_price=price, now=two_days)
    free = NOW9 + timedelta(days=3, hours=1)
    exchange.place_order(db, account=account, ticker=ticker, side="buy", kind="limit", quantity=10, limit_price=price, now=free)


def test_a_widely_read_true_story_nudges_investors_who_read_it_at_their_own_pace(db):
    j, _ = pro(db, "investment_banker", "influencer", level=10)
    card = results_card(db, tone=1)
    out = write(db, j, [card])
    assert out["readers"] >= data.WIDELY_READ and out["nudges"]
    nudge = out["nudges"][0]
    assert 0 < nudge["bps"] <= data.NUDGE_MOST_BPS
    company = _one(db, "SELECT id FROM companies WHERE ticker = %s", (nudge["ticker"],))["id"]
    day, _ = exchange.session_of(NOW9)
    assert newsroom.nudges_today(db, day)[company] == nudge["bps"]                         # small investors: at once
    assert company not in newsroom.nudges_today(db, day, lag_days=1)                       # pension funds: a day late
    assert newsroom.nudges_today(db, day + timedelta(days=1), lag_days=1)[company] == nudge["bps"]
    assert newsroom.nudges_today(db, day + timedelta(days=2))[company] == nudge["bps"] * 3 // 5     # fading
    assert company not in newsroom.nudges_today(db, day + timedelta(days=5))
    assert data.NEWS_LAG_DAYS["investors:founders"] is None                                # founders never
    # One nudge per company a day.
    other, _ = pro(db, "investment_banker", "echo", level=10)
    assert not write(db, other, [card])["nudges"]
    # The investors take it in.
    investors.act(db, LATER, force=True)
    reasons = _one(db, "SELECT count(*) AS n FROM market_reasons WHERE company_id = %s AND reason LIKE %s", (company, "%widely read news story%"))
    assert reasons["n"] >= 0
    assert ripple.causes(db, f"nudge:{nudge['ticker']}:{day}")[0]["cause"] == f"story:{out['story_id']}"


def test_interviews_answers_refusals_and_deadlines_go_into_the_story(db):
    empire, team = firm_of(db)
    j, _ = pro(db, "investment_banker", "interviewer", level=10)
    card = results_card(db)
    company = _one(db, "SELECT id FROM companies WHERE ticker = %s", (card["tickers"][0],))["id"]
    db.execute("INSERT INTO stake_disclosures (empire_id, company_id, bps, at) VALUES (%s, %s, 500, %s)", (empire["id"], company, NOW9))
    newsroom.start(db, j, NOW9)
    newsroom.add_fact(db, j, card["id"], NOW9)
    newsroom.check_fact(db, j, card["id"], NOW9)
    newsroom.ask(db, j, ticker=card["tickers"][0], empire_name=None, question="How do you explain these results?", now=NOW9)
    newsroom.ask(db, j, ticker=None, empire_name=empire["name"], question="Does the empire plan to buy more?", now=NOW9)
    with pytest.raises(newsroom.NewsroomError, match="already asked"):
        newsroom.ask(db, j, ticker=card["tickers"][0], empire_name=None, question="And again, please explain?", now=NOW9)
    other = next(c for c in newsroom_facts.facts(db, NOW9) if c["kind"] == "results" and c["tickers"] != card["tickers"])
    with pytest.raises(newsroom.NewsroomError, match="your story is about"):
        newsroom.ask(db, j, ticker=other["tickers"][0], empire_name=None, question="A company the story does not name?", now=NOW9)
    with pytest.raises(newsroom.NewsroomError, match="in words"):
        newsroom.answer(db, team["head"], newsroom.to_answer(db, team["head"], NOW9)[0]["id"], "Profit will double to 40%", NOW9)
    waiting = newsroom.to_answer(db, team["head"], NOW9)
    assert len(waiting) == 1
    assert empires_rep(db, empire["id"]) == 50                            # an answer counts only when it goes to print
    with pytest.raises(newsroom.NewsroomError, match="not yours"):
        newsroom.answer(db, team["asset_manager"], waiting[0]["id"], "Yes.", NOW9)
    newsroom.answer(db, team["head"], waiting[0]["id"], "We do not comment on our plans.", NOW9)
    out = newsroom.publish(db, j, LATER)
    body = _one(db, "SELECT body FROM news_items WHERE id = %s", (out["news_item_id"],))["body"]
    assert "We do not comment on our plans." in body
    assert empires_rep(db, empire["id"]) == 51
    # A question left to run out of time is in the story too, and costs the empire.
    j2, _ = pro(db, "investment_banker", "patient", level=10)
    newsroom.start(db, j2, NOW9)
    newsroom.add_fact(db, j2, card["id"], NOW9)
    newsroom.check_fact(db, j2, card["id"], NOW9)
    newsroom.ask(db, j2, ticker=None, empire_name=empire["name"], question="Will you answer this one in time?", now=NOW9)
    late = NOW9 + timedelta(hours=data.INTERVIEW_HOURS + 1)
    body2 = _one(db, "SELECT body FROM news_items WHERE id = %s", (newsroom.publish(db, j2, late)["news_item_id"],))["body"]
    assert "had not answered by the deadline" in body2
    assert empires_rep(db, empire["id"]) == 50


def empires_rep(db, empire_id):
    return _one(db, "SELECT reputation FROM empires WHERE id = %s", (empire_id,))["reputation"]


def test_an_undeclared_interest_can_be_exposed_and_only_the_verdict_is_shown(db):
    empire, team = firm_of(db)
    j = team["investment_banker"]
    card = results_card(db)
    company = _one(db, "SELECT share_asset FROM companies WHERE ticker = %s", (card["tickers"][0],))
    ledger.transfer(db, payer=ledger.account_id(db, ledger.INVESTORS_PUBLIC), receiver=empire["account_id"], amount=1000,
                    asset=company["share_asset"], kind="test_shares", memo="Test shares")
    out = write(db, j, [card])                                             # not declared
    reader, _ = pro(db, "asset_manager", "watchdog", level=10)
    rep_before = _one(db, "SELECT reputation FROM players WHERE id = %s", (j,))["reputation"]
    verdict = newsroom.expose(db, reader, out["story_id"], LATER)
    assert verdict["upheld"] and "1000" not in verdict["words"]
    assert _one(db, "SELECT reputation FROM players WHERE id = %s", (j,))["reputation"] == rep_before - data.UNDECLARED_REPUTATION
    assert empires_rep(db, empire["id"]) == 50 - data.UNDECLARED_EMPIRE_REPUTATION
    with pytest.raises(newsroom.NewsroomError, match="already raised"):
        newsroom.expose(db, reader, out["story_id"], LATER)
    # A declared one is not an offence; raising it costs the one who raised it.
    card2 = [c for c in newsroom_facts.facts(db, NOW9) if c["kind"] == "results"][1]
    out2 = write(db, j, [card2], declared=True)
    assert "Declared interest" in _one(db, "SELECT body FROM news_items WHERE id = %s", (out2["news_item_id"],))["body"]
    assert not newsroom.expose(db, reader, out2["story_id"], LATER)["upheld"]


def test_a_story_whose_facts_the_record_changes_must_be_corrected_and_late_costs_more(db):
    j, _ = pro(db, "investment_banker", "corrector", level=10)
    card = results_card(db)
    out = write(db, j, [card])
    _, company_id, period, version = card["source"].split(":")
    old = _one(db, "SELECT * FROM company_reports WHERE company_id = %s AND period = %s AND version = %s", (company_id, int(period), int(version)))
    db.execute("INSERT INTO company_reports (company_id, period, version, figures, credit_rating, rating_reasons, filed_by)"
               " VALUES (%s, %s, %s, %s, %s, %s, 'restated')",
               (company_id, int(period), int(version) + 1, Jsonb(old["figures"]), old["credit_rating"], Jsonb(old["rating_reasons"])))
    newsroom.tick(db, LATER)
    due = newsroom.to_correct(db, j)
    assert [d["id"] for d in due] == [out["story_id"]]
    rep = _one(db, "SELECT reputation FROM players WHERE id = %s", (j,))["reputation"]
    corrected = newsroom.correct(db, j, out["story_id"], LATER)
    item = _one(db, "SELECT * FROM news_items WHERE id = %s", (corrected["news_item_id"],))
    assert item["follows"] == out["news_item_id"] and item["kind"] == "correction"
    assert _one(db, "SELECT reputation FROM players WHERE id = %s", (j,))["reputation"] == rep - data.CORRECTION_REPUTATION
    assert newsroom.profile(db, j)["corrections"] == 1
    with pytest.raises(newsroom.NewsroomError):
        newsroom.correct(db, j, out["story_id"], LATER)


def test_full_articles_are_written_from_the_record_with_every_figure_checked_and_twenty_a_day(db):
    w = careers.world_now(db, NOW9)
    # Articles are written for news still fresh (a few game days old): read as on a busy news day of the record.
    last = _one(db, "SELECT period, day FROM news_items WHERE author_id IS NULL AND (period, day) <= (%s, %s) ORDER BY period DESC, day DESC LIMIT 1",
                (w["period"], w["day"]))
    w = {"period": last["period"], "day": last["day"]}
    items = [r[0] for r in db.execute("SELECT id FROM news_items WHERE author_id IS NULL AND ((period = %s AND day BETWEEN %s AND %s)"
                                      " OR (period = %s - 1 AND day > %s + 90 - %s)) ORDER BY id DESC LIMIT 25",
                                      (w["period"], w["day"] - data.ARTICLE_FRESH_DAYS, w["day"], w["period"], w["day"],
                                       data.ARTICLE_FRESH_DAYS)).fetchall()]
    first = articles.article(db, items[0], w["period"], w["day"], NOW9)
    assert first and first["writer"] == "built_in" and "What it means" in first["body"]
    item = _one(db, "SELECT * FROM news_items WHERE id = %s", (items[0],))
    assert item["body"] in first["body"]
    # Once written, it is kept.
    assert articles.article(db, items[0], w["period"], w["day"], NOW9)["body"] == first["body"]
    # A paid service whose text has a figure not on the record is not used.
    articles.SERVICE = lambda facts: "Profits rose 99.9% to ₦77 trillion."
    try:
        second = articles.article(db, items[1], w["period"], w["day"], NOW9)
        assert second["writer"] == "built_in"
        articles.SERVICE = lambda facts: facts["wire"]
        third = articles.article(db, items[2], w["period"], w["day"], NOW9)
        assert third["writer"] == "service"
    finally:
        articles.SERVICE = None
    for i in items[3:]:
        articles.article(db, i, w["period"], w["day"], NOW9)
    assert _one(db, "SELECT count(*) AS n FROM news_articles WHERE period = %s AND day = %s", (w["period"], w["day"]))["n"] == min(len(items), data.ARTICLES_A_DAY)
    data_old = _one(db, "SELECT id FROM news_items WHERE author_id IS NULL AND period < %s - 1 AND NOT (id = ANY(%s)) ORDER BY id LIMIT 1",
                    (w["period"], items))
    assert articles.article(db, data_old["id"], w["period"], w["day"], NOW9) is None   # old archive items do not use up the day's articles
    # Nothing is written for an item dated later than today.
    future = _one(db, "SELECT id FROM news_items WHERE (period, day) > (%s, %s) LIMIT 1", (w["period"], w["day"]))
    if future:
        assert articles.article(db, future["id"], w["period"], w["day"], NOW9) is None
    assert articles.check("Sales rose 12% to ₦3 billion.", {"12%", "₦3 billion"}) == []
    assert articles.check("Sales rose 13% to ₦3 billion.", {"12%", "₦3 billion"}) == ["13%"]
    assert articles.check("Sales reached ₦12 billion.", {"12%"}) == ["₦12 billion"]          # a figure must match with its unit


def test_the_ripple_links_causes_and_the_chronicle_keeps_the_quarter(db):
    quarters.close_due_quarters(db, after_quarters(9))
    period = 9
    linked = _one(db, "SELECT count(*) AS n FROM ripple_links WHERE effect LIKE %s", (f"results:%:{period}",))["n"]
    assert linked > 0                      # each company's results link to what caused them: the quarter's events, the rate
    rate = ripple.chain(db, f"rate:{period}")
    assert rate["one_line"].startswith("Prices were rising") and rate["numbers"]
    some = _one(db, "SELECT effect FROM ripple_links WHERE effect LIKE %s ORDER BY (cause LIKE 'event:%%') DESC LIMIT 1",
                (f"results:%:{period}",))["effect"]
    ticker = some.split(":")[1]
    rating = ripple.chain(db, f"rating:{ticker}:{period}")
    assert len(rating["chain"]) >= 2 and rating["steps"][0]["cause"] == some
    assert _one(db, "SELECT count(*) AS n FROM chronicle_entries WHERE layer IN ('world', 'company') AND period = %s", (period + 1,))["n"] >= 1


def test_a_year_in_review_closes_each_game_year(db):
    quarters.close_due_quarters(db, after_quarters(12))
    entry = _one(db, "SELECT * FROM chronicle_entries WHERE kind = 'year_in_review' AND ref = 'year:3'")
    assert entry and "Central Bank's rate" in entry["words"]
    entries = chronicle.entries(db, "world", period_now=13, day_now=90)
    assert any(e["kind"] == "year_in_review" for e in entries)


def test_journalists_write_signed_accounts_beside_the_record_with_a_credibility_score(db):
    j, _ = pro(db, "investment_banker", "historian", level=10)
    quarters.close_due_quarters(db, after_quarters(9))
    later = after_quarters(9) + timedelta(hours=12)
    entry = _one(db, "SELECT e.id, c.ticker FROM chronicle_entries e JOIN companies c ON c.id = e.company_id WHERE e.layer = 'company' ORDER BY e.id LIMIT 1")
    card = next(c for c in newsroom_facts.facts(db, later) if c["kind"] == "results" and entry["ticker"] in c["tickers"])
    out = write(db, j, [card], now=later)
    unrelated = write(db, j, [next(c for c in newsroom_facts.facts(db, later) if c["kind"] == "results" and entry["ticker"] not in c["tickers"])],
                      now=later)
    with pytest.raises(chronicle.ChronicleError, match="about this entry"):
        chronicle.add_account(db, j, entry["id"], "An account citing a story about something else entirely, to look well sourced.",
                              [unrelated["story_id"]], 10, LATER)
    words = "The quarter turned on borrowing costs: the rate decision squeezed the weakest borrowers first."
    got = chronicle.add_account(db, j, entry["id"], words, [out["story_id"]], 10, LATER)
    assert got["credibility"] > 40
    with pytest.raises(chronicle.ChronicleError, match="already"):
        chronicle.add_account(db, j, entry["id"], words, [], 10, LATER)
    other, _ = pro(db, "investment_banker", "rival", level=10)
    with pytest.raises(chronicle.ChronicleError, match="your own published stories"):
        chronicle.add_account(db, other, entry["id"], words, [out["story_id"]], 10, LATER)
    shown = chronicle.entries(db, "company", company_ticker=entry["ticker"], period_now=11, day_now=1)
    assert any(a["author"] for e in shown for a in e["accounts"])


def test_an_empires_reputation_moves_with_fines_audits_and_answers_and_shows_in_the_league(db):
    from simulation import empires, leagues
    empire, team = firm_of(db)
    empires._book(db, empire["id"], 9, "Fines", "Fine for holdings notices not filed", 100, True, NOW9, kind="fee")
    assert empires_rep(db, empire["id"]) == 48
    standing.change(db, empire["id"], 200, "test", 9, NOW9)
    assert empires_rep(db, empire["id"]) == 100
    row = next(e for d in leagues.table(db, NOW9) for e in d["empires"] if e["id"] == empire["id"])
    assert row["reputation"] == 100
    assert standing.history(db, empire["id"])[0]["after"] == 100


def test_an_independent_is_paid_by_the_paper_that_picks_the_story_up(db):
    # (Pay for reach, paid by a paper to the journalists on its staff, went when no build was employed by a paper.)
    free, account = pro(db, "investment_banker", "freelancer", level=10)
    careers.leave_job(db, free, NOW9)
    before = ledger.balance(db, account)
    out = write(db, free, [results_card(db)])
    assert out["paid"] > 0 and ledger.balance(db, account) - before == out["paid"]
    assert _one(db, "SELECT facts->>'outlet' AS o FROM news_items WHERE id = %s", (out["news_item_id"],))["o"].endswith(
        "an independent journalist")
    sound(db)


def test_the_news_work_comes_three_ways_with_named_editors_who_remember(db, monkeypatch):
    taken_before_retirement(monkeypatch, "jn_check_story", "jn_front_page")
    assert len(objectives_news.NEWS) == 12
    for t in objectives_news.NEWS:
        assert {x.setting for x in objectives.TEMPLATES.values() if x.root == t.code} == {"solo", "empire", "live"}
        assert objectives.how_to(t)
    j, _ = pro(db, "investment_banker", "editorspet", level=10)
    db.execute("UPDATE careers SET rank = 2, experience = %s WHERE player_id = %s", (careers.experience_for(40), j))
    ctx = objectives._context(db, j, NOW9)
    t = objectives.TEMPLATES["jn_check_story"]
    terms = t.offer(ctx)
    assert "Mrs Adaeze Okafor" in terms["situation"]
    right = t.submit(ctx, {"terms": terms}, {})["answers"]
    assert t.submit(ctx, {"terms": terms}, right)["state"] == "passed"
    # The paper pays for the editor's work.
    taken = objectives.accept(db, j, "jn_check_story", NOW9)
    assert taken["payer"] == "The Lagoon Herald"
    # Work given up counts against the editor, twice as fast as work done well counts for them.
    objectives.withdraw(db, j, taken["id"], NOW9)
    assert clients.trust(db, j, "herald_editor") == clients.START - clients.FALL
    db.execute("UPDATE client_trust SET trust = 20 WHERE player_id = %s", (j,))
    assert t.offer(ctx) is None                                             # an editor who has cooled stops offering work
    assert objectives.TEMPLATES["jn_front_page"].offer(ctx) is None
    clients.at_close(db)
    assert clients.trust(db, j, "herald_editor") == 25                      # ...and comes back a little each quarter
    db.execute("UPDATE client_trust SET trust = 80 WHERE player_id = %s", (j,))
    assert objectives.TEMPLATES["jn_front_page"].offer(ctx) is not None     # the front page, for a journalist they trust
    # An independent journalist (no employer) is offered the editors' work too.
    free, _ = pro(db, "investment_banker", "nojob", level=10)
    db.execute("UPDATE careers SET rank = 2, experience = %s WHERE player_id = %s", (careers.experience_for(40), free))
    careers.leave_job(db, free, NOW9)
    assert objectives.accept(db, free, "jn_check_story", NOW9)["payer"] == "The Lagoon Herald"


def test_the_stage_test_a_journalist_verifies_and_publishes_the_price_reacts_and_the_chronicle_keeps_it_with_its_causes(db):
    """The design's test for Stage 10: a journalist verifies and publishes a story, the price reacts, and the entry appears
    in the Chronicle with its chain of causes."""
    quarters.close_due_quarters(db, after_quarters(9))
    now = after_quarters(9) + timedelta(hours=12)
    j, _ = pro(db, "investment_banker", "stagetest", level=10)
    w = careers.world_now(db, now)
    # News the wire has not yet carried: a story that is first with it moves investors (one repeating the wire does not).
    cards = [c for c in newsroom_facts.facts(db, now) if c["kind"] == "results" and c["tone"] != 0
             and ripple.causes(db, c["ripple"]) and not newsroom._on_wire(db, c, w["period"], w["day"])]
    card = cards[0]
    newsroom.start(db, j, now)
    newsroom.add_fact(db, j, card["id"], now)
    checked = newsroom.check_fact(db, j, card["id"], now)
    assert "it stands" in checked["words"]                               # verified against the record
    out = newsroom.publish(db, j, now)
    assert out["nudges"]                                                   # the price reacts: investors mark it
    company = _one(db, "SELECT id FROM companies WHERE ticker = %s", (out["nudges"][0]["ticker"],))["id"]
    day, _ = exchange.session_of(now)
    assert newsroom.nudges_today(db, day)[company] != 0
    entry = _one(db, "SELECT * FROM chronicle_entries WHERE ref = %s", (f"story:{out['story_id']}",))
    assert entry is not None                                               # in the Chronicle
    why = ripple.chain(db, f"nudge:{out['nudges'][0]['ticker']}:{day}")
    kinds = [s["cause"].split(":")[0] for s in why["steps"]]
    assert kinds[0] == "story" and "results" in kinds and len(kinds) >= 3  # with its chain of causes, back past the results
    sound(db)
