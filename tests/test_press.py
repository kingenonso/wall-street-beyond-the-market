"""Stage 10, Part 2: investigations, crises, the press office, counter-investigation, leaks and the leak hunt, spin or refuse,
fact-checking, planted rumours, and what the press does to an empire's reputation."""

from __future__ import annotations

from datetime import timedelta

import pytest
from psycopg.rows import dict_row

from simulation import careers, chronicle, empires, intel, ledger, newsroom, press, quarters, standing
from simulation import world_data as data
from simulation.money import naira
from tests.conftest import after_quarters
from tests.test_builds import pro
from tests.test_careers import NOW9
from tests.test_firm import firm_of
from tests.test_newsroom import results_card, write

pytestmark = pytest.mark.world("eight")
DAY = timedelta(days=1)


def _one(db, sql, params=()):
    with db.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(sql, params).fetchall()
    return rows[0] if rows else None


def _rows(db, sql, params=()):
    with db.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def _reporter(db, name="digger", level=40):
    p, _ = pro(db, "investment_banker", name, level=level, cash_naira=5_000_000)
    return p


def _theft(db, empire, thief):
    w = careers.world_now(db, NOW9)
    return _one(db, "INSERT INTO empire_books (empire_id, period, category, description, amount, genuine, entered_by, thief_level, at)"
                    " VALUES (%s, %s, 'supplies', 'Office supplies', %s, false, %s, 4, %s) RETURNING *",
                (empire["id"], w["period"], naira(3_000_000), thief, NOW9))


def _pact(db, a, b, legal=False):
    w = careers.world_now(db, NOW9)
    return _one(db, "INSERT INTO empire_pacts (kind, legal, from_empire, to_empire, terms, status, period, signed_period, at)"
                    " VALUES ('price_fixing', %s, %s, %s, 'We will not undercut each other.', 'signed', %s, %s, %s) RETURNING *",
                (legal, a, b, w["period"], w["period"], NOW9))


def _rep(db, empire_id):
    return _one(db, "SELECT reputation FROM empires WHERE id = %s", (empire_id,))["reputation"]


def _investigate(db, j, empire, *, days=60, ref=None, start=NOW9):
    f = press.open_file(db, j, empire["name"], ref, start)
    t = start
    for _ in range(days):
        f = press.dig(db, j, f["id"], t)
        if f["documents"] >= 2 and not f["confirmed"]:
            f = press.second_source(db, j, f["id"], t)
        if f["can_publish"]:
            return f, t
        t += DAY
    return f, t


def test_an_investigation_finds_documents_only_where_there_is_something_and_its_expose_proves_the_theft(db):
    empire, team = firm_of(db)
    j = _reporter(db)
    # An empire with nothing to hide: the searches never find anything.
    clean, _ = _investigate(db, j, empire, days=8)
    assert clean["documents"] == 0 and not clean["can_publish"]
    with pytest.raises(press.PressError, match="documents and a second source"):
        press.publish_expose(db, j, clean["id"], NOW9 + 9 * DAY)
    with pytest.raises(press.PressError, match="searched today"):
        press.dig(db, j, clean["id"], NOW9 + 7 * DAY)
    press.drop_file(db, j, clean["id"])
    # Money taken and dressed up in the books: the documents point at it, one by one.
    book = _theft(db, empire, team["asset_manager"])
    f, when = _investigate(db, j, empire, start=NOW9 + 9 * DAY)
    assert f["can_publish"] and f["documents"] == data.DOCUMENTS_NEEDED
    assert "basis" not in f and not any("Office supplies" in n for n in f["notes"])     # the file never names the entry
    rep_before = _rep(db, empire["id"])
    out = press.publish_expose(db, j, f["id"], when)
    assert out["headline"].startswith("Investigation:") and out["readers"] > 0 and out["paid"] == naira(data.EXPOSE_BONUS_NAIRA)
    assert _one(db, "SELECT found FROM empire_books WHERE id = %s", (book["id"],))["found"]
    assert _one(db, "SELECT 1 AS x FROM empire_cases WHERE book_id = %s", (book["id"],))
    assert _rep(db, empire["id"]) < rep_before
    crisis = _one(db, "SELECT * FROM crises WHERE empire_id = %s AND kind = 'theft'", (empire["id"],))
    assert crisis and crisis["status"] == "open"
    assert _one(db, "SELECT 1 AS x FROM chronicle_entries WHERE layer = 'world' AND kind = 'scandal'")
    assert newsroom.profile(db, j)["credibility"] == 50 + data.EXPOSE_CREDIBILITY
    # It cannot be run twice.
    with pytest.raises(press.PressError, match="closed"):
        press.publish_expose(db, j, f["id"], when)


def test_a_pact_investigation_started_from_a_true_tip_goes_faster_and_the_expose_brings_the_pact_to_light(db):
    empire, team = firm_of(db)
    rival = _one(db, "SELECT * FROM empires WHERE kind = 'computer' ORDER BY id LIMIT 1")
    pact = _pact(db, empire["id"], rival["id"])
    j = _reporter(db)
    w = careers.world_now(db, NOW9)
    tip = intel.make(db, kind="tip", topic="pact", truth="true", basis=f"pact:{pact['id']}", period=w["period"], day=w["day"], now=NOW9,
                     empire_id=empire["id"], other_empire_id=rival["id"], words=f"{empire['name']} and {rival['name']} are said to have a private understanding.")
    intel.hold(db, tip["id"], j, "found", NOW9)
    f, when = _investigate(db, j, empire, ref=tip["ref"])
    assert f["can_publish"]
    press.publish_expose(db, j, f["id"], when)
    assert _one(db, "SELECT exposed_at FROM empire_pacts WHERE id = %s", (pact["id"],))["exposed_at"] is not None
    # Both empires must answer for it; the computer-run one answers at once.
    assert _one(db, "SELECT status FROM crises WHERE empire_id = %s AND kind = 'pact'", (empire["id"],))["status"] == "open"
    assert _one(db, "SELECT status FROM crises WHERE empire_id = %s AND kind = 'pact'", (rival["id"],))["status"] == "answered"
    # The true tip was borne out.
    intel.tick(db, when)
    assert _one(db, "SELECT status FROM intel_items WHERE id = %s", (tip["id"],))["status"] == "verified"


def test_a_crisis_answered_honestly_and_quickly_costs_least_denial_of_a_truth_costs_most(db):
    empire, team = firm_of(db)
    cases = {}
    w = careers.world_now(db, NOW9)
    for n, (truth, stance) in enumerate((("true", "admit"), ("true", "deny"), ("true", None), ("false", "deny"), ("false", "admit"))):
        # A report about the empire: what answering it does waits until the report is borne out or proved wrong.
        item = intel.make(db, kind="rumour", topic="theft", truth=truth, basis="none", period=w["period"], day=w["day"], now=NOW9,
                          empire_id=empire["id"], words="Someone at the empire may be taking its money.")
        c = press.open_crisis(db, empire["id"], "report", f"story:{9000 + n}", "A report says something about the empire.", truth, NOW9,
                              item_id=item["id"])
        before = _rep(db, empire["id"])
        if stance:
            press.answer_crisis(db, team["investment_banker"], c["id"], stance, "We have looked into this and here is our answer.", NOW9)
        else:
            press.tick(db, NOW9 + timedelta(hours=data.CRISIS_HOURS + 1))
        assert _rep(db, empire["id"]) == before                                       # nothing yet: the truth is not out
        intel._settle(db, item, truth, NOW9 + timedelta(hours=30))
        cases[(truth, stance)] = _rep(db, empire["id"]) - before
    for key, change in cases.items():
        assert change == data.CRISIS_OUTCOMES[key], key
    # A theft that came to light is known to be so: its answer counts at once.
    c = press.open_crisis(db, empire["id"], "theft", "book:31337", "Money was taken.", "true", NOW9)
    before = _rep(db, empire["id"])
    press.answer_crisis(db, team["head"], c["id"], "admit", "We found it and we are putting it right.", NOW9)
    assert _rep(db, empire["id"]) - before == data.CRISIS_OUTCOMES[("true", "admit")]
    # Only the head or the empire's journalist speaks for it; a closed matter cannot be answered; no figures.
    c = press.open_crisis(db, empire["id"], "report", "story:9999", "Another report.", "true", NOW9)
    with pytest.raises(press.PressError, match="speaks for it"):
        press.answer_crisis(db, team["asset_manager"], c["id"], "admit", "We have looked into this matter.", NOW9)
    with pytest.raises(press.PressError, match="in words"):
        press.answer_crisis(db, team["head"], c["id"], "admit", "We lost 5 million naira.", NOW9)
    with pytest.raises(press.PressError, match="closed"):
        press.answer_crisis(db, team["head"], c["id"], "admit", "We have looked into this matter.", NOW9 + timedelta(hours=30))
    statement = _one(db, "SELECT * FROM news_items WHERE kind = 'statement' ORDER BY id LIMIT 1")
    assert statement["headline"].startswith("Statement from")
    # What was really so is never on the press desk.
    assert "truth" not in repr(press.desk(db, team["head"], NOW9))


def test_the_press_office_answers_for_the_empire_and_sees_who_has_been_looking_from_public_traces_only(db):
    empire, team = firm_of(db)
    j = _reporter(db, "outsider")
    card = results_card(db)
    company = _one(db, "SELECT id FROM companies WHERE ticker = %s", (card["tickers"][0],))["id"]
    db.execute("INSERT INTO stake_disclosures (empire_id, company_id, bps, at) VALUES (%s, %s, 500, %s)", (empire["id"], company, NOW9))
    newsroom.start(db, j, NOW9)
    newsroom.add_fact(db, j, card["id"], NOW9)
    newsroom.ask(db, j, ticker=None, empire_name=empire["name"], question="Will the empire buy more of this company?", now=NOW9)
    waiting = newsroom.to_answer(db, team["investment_banker"], NOW9)
    assert len(waiting) == 1                                                     # the empire's journalist sees it
    assert newsroom.to_answer(db, team["asset_manager"], NOW9) == []
    with pytest.raises(newsroom.NewsroomError, match="not yours"):
        newsroom.answer(db, team["asset_manager"], waiting[0]["id"], "No comment.", NOW9)
    newsroom.answer(db, team["investment_banker"], waiting[0]["id"], "We do not comment on our plans.", NOW9)
    newsroom.check_fact(db, j, card["id"], NOW9)
    newsroom.publish(db, j, NOW9)
    # A private investigation file leaves no trace the empire can see.
    press.open_file(db, _reporter(db, "quiet"), empire["name"], None, NOW9)
    looking = press.who_is_looking(db, empire["id"], NOW9 + timedelta(hours=1))
    names = [r["investment_banker"] for r in looking]
    assert names == ["outsider"]
    assert any(t.startswith("Asked:") for t in looking[0]["traces"]) and any(t.startswith("Wrote:") for t in looking[0]["traces"])


def test_a_member_can_leak_only_what_is_so_the_empire_suffers_the_leak_and_may_hunt_the_leaker(db):
    empire, team = firm_of(db)
    j = _reporter(db, "receiver", level=30)
    company = _one(db, "SELECT id, ticker, share_asset FROM companies WHERE listed ORDER BY ticker LIMIT 1")
    with pytest.raises(press.PressError, match="holds no shares"):
        press.leak(db, team["asset_manager"], "holding", "receiver", NOW9, ticker=company["ticker"])
    from tests.test_objectives import give_shares
    give_shares(db, empire["account_id"], company["ticker"], 1000)
    with pytest.raises(press.PressError, match="head speaks"):
        press.leak(db, team["head"], "holding", "receiver", NOW9, ticker=company["ticker"])
    with pytest.raises(press.PressError, match="Financial Journalist"):
        press.leak(db, team["asset_manager"], "holding", "warden", NOW9, ticker=company["ticker"])
    press.leak(db, team["asset_manager"], "holding", "receiver", NOW9, ticker=company["ticker"])
    with pytest.raises(press.PressError, match="this quarter already"):
        press.leak(db, team["asset_manager"], "holding", "receiver", NOW9, ticker=company["ticker"])
    held = intel.mine(db, j, NOW9)[0]
    assert held["how"] == "leaked" and held["confidential"] and "asset_manager" not in repr(held).lower()
    assert "ledgerman" not in repr(held)                                         # the leaker's name is not on it
    # Printed: a leak to the press, and a crisis to answer.
    newsroom.start(db, j, NOW9)
    newsroom.add_lead(db, j, held["ref"], NOW9)
    newsroom.publish(db, j, NOW9)
    assert _one(db, "SELECT kind FROM crises WHERE empire_id = %s", (empire["id"],))["kind"] == "leak"
    leaks = press.leaks_of(db, empire["id"])
    assert len(leaks) == 1 and "member" not in repr(leaks)
    # The hunt: once, by the head or the empire's journalist; the result goes to the hunter.
    with pytest.raises(press.PressError, match="speaks for it"):
        press.hunt(db, team["investment_banker"], leaks[0]["id"], NOW9)
    got = press.hunt(db, team["head"], leaks[0]["id"], NOW9)
    assert got["found"] in (True, False)
    if got["found"]:
        assert "ledgerman" in got["words"]
    with pytest.raises(press.PressError, match="already"):
        press.hunt(db, team["investment_banker"], leaks[0]["id"], NOW9)


def test_a_leaked_pact_comes_to_light_when_printed_and_a_hidden_pact_can_leak_on_its_own(db, monkeypatch):
    empire, team = firm_of(db)
    rival = _one(db, "SELECT * FROM empires WHERE kind = 'computer' ORDER BY id LIMIT 1")
    pact = _pact(db, empire["id"], rival["id"])
    j = _reporter(db, "pactreceiver")
    press.leak(db, team["investment_banker"], "pact", "pactreceiver", NOW9, pact_id=pact["id"])
    held = intel.mine(db, j, NOW9)[0]
    newsroom.start(db, j, NOW9)
    newsroom.add_lead(db, j, held["ref"], NOW9)
    newsroom.publish(db, j, NOW9)
    assert _one(db, "SELECT exposed_at FROM empire_pacts WHERE id = %s", (pact["id"],))["exposed_at"] is not None
    assert _one(db, "SELECT 1 AS x FROM crises WHERE empire_id = %s AND kind = 'pact'", (empire["id"],))
    # A second hidden pact leaks on its own at a close.
    other = _one(db, "SELECT * FROM empires WHERE kind = 'computer' ORDER BY id DESC LIMIT 1")
    second = _pact(db, empire["id"], other["id"])
    monkeypatch.setattr(data, "RANDOM_LEAK_BPS", 10_000)
    w = careers.world_now(db, NOW9)
    assert press.random_leaks(db, w["period"], NOW9) == 1
    assert _one(db, "SELECT exposed_at FROM empire_pacts WHERE id = %s", (second["id"],))["exposed_at"] is not None
    assert _one(db, "SELECT 1 AS x FROM news_items WHERE kind = 'leak'")
    with pytest.raises(press.PressError, match="nobody inside"):
        lk = _one(db, "SELECT id FROM leaks WHERE kind = 'random'")
        press.hunt(db, team["head"], lk["id"], NOW9)


def test_spin_or_refuse_refusing_keeps_a_clean_name_and_spin_can_come_out(db, monkeypatch):
    empire, team = firm_of(db)
    j = _reporter(db, "critic")
    card = results_card(db)
    company = _one(db, "SELECT id FROM companies WHERE ticker = %s", (card["tickers"][0],))["id"]
    db.execute("INSERT INTO stake_disclosures (empire_id, company_id, bps, at) VALUES (%s, %s, 500, %s)", (empire["id"], company, NOW9))
    story = write(db, j, [card])
    with pytest.raises(press.PressError, match="Only the head"):
        press.ask_spin(db, team["investment_banker"], story["story_id"], NOW9)
    req = press.ask_spin(db, team["head"], story["story_id"], NOW9)["request_id"]
    rep = _one(db, "SELECT reputation FROM players WHERE id = %s", (team["investment_banker"],))["reputation"]
    press.decide_spin(db, team["investment_banker"], req, False, None, NOW9)
    assert _one(db, "SELECT reputation FROM players WHERE id = %s", (team["investment_banker"],))["reputation"] == rep + data.SPIN_REFUSED_REPUTATION
    # Going along: the reply goes out and helps the empire, for now.
    db.execute("DELETE FROM spin_requests WHERE id = %s", (req,))
    req = press.ask_spin(db, team["head"], story["story_id"], NOW9)["request_id"]
    before = _rep(db, empire["id"])
    press.decide_spin(db, team["investment_banker"], req, True, "The company is doing far better than this story would have you think.", NOW9)
    assert _rep(db, empire["id"]) == before + data.SPIN_REPUTATION
    reply = _one(db, "SELECT * FROM news_items WHERE kind = 'reply'")
    # Somebody raises it: upheld, and it costs the empire and the journalist.
    raiser = _reporter(db, "watchdog")
    cred = newsroom.profile(db, team["investment_banker"])["credibility"]
    assert press.raise_spin(db, raiser, reply["id"], NOW9)["upheld"]
    assert newsroom.profile(db, team["investment_banker"])["credibility"] == cred - data.SPIN_EXPOSED_CREDIBILITY
    assert _rep(db, empire["id"]) == before + data.SPIN_REPUTATION - data.SPIN_EXPOSED_EMPIRE_REPUTATION
    with pytest.raises(press.PressError, match="already raised"):
        press.raise_spin(db, raiser, reply["id"], NOW9)
    # An honest reply raised as spin is not upheld, and costs the one who raised it.
    press.reply(db, team["head"], story["story_id"], "We stand by our record and will say more when we next file.", NOW9 + DAY)
    honest = _one(db, "SELECT * FROM news_items WHERE kind = 'reply' AND id <> %s", (reply["id"],))
    assert not press.raise_spin(db, raiser, honest["id"], NOW9 + DAY)["upheld"]


def test_spin_not_raised_may_still_come_out_at_a_close(db, monkeypatch):
    empire, team = firm_of(db)
    j = _reporter(db, "critic2")
    card = results_card(db)
    company = _one(db, "SELECT id FROM companies WHERE ticker = %s", (card["tickers"][0],))["id"]
    db.execute("INSERT INTO stake_disclosures (empire_id, company_id, bps, at) VALUES (%s, %s, 500, %s)", (empire["id"], company, NOW9))
    story = write(db, j, [card])
    req = press.ask_spin(db, team["head"], story["story_id"], NOW9)["request_id"]
    press.decide_spin(db, team["investment_banker"], req, True, "The company is doing far better than this story would have you think.", NOW9)
    monkeypatch.setattr(data, "SPIN_COMES_OUT_BPS", 10_000)
    press.at_close(db, careers.world_now(db, NOW9)["period"], NOW9)
    assert _one(db, "SELECT exposed FROM spin_requests WHERE id = %s", (req,))["exposed"]
    assert _one(db, "SELECT 1 AS x FROM news_items WHERE kind = 'spin_exposed'")


def test_the_fact_checking_desk_checks_a_members_tip_and_rumours_can_be_planted_but_who_planted_them_is_never_shown(db):
    empire, team = firm_of(db)
    w = careers.world_now(db, NOW9)
    company = _one(db, "SELECT id, name FROM companies WHERE listed ORDER BY ticker LIMIT 1")
    item = intel.make(db, kind="tip", topic="company", truth="false", basis="none", period=w["period"], day=w["day"], now=NOW9,
                      company_id=company["id"], tone=1, words=f"Word around {company['name']}: good news is coming.",
                      useful_until=NOW9 + timedelta(hours=4))
    intel.hold(db, item["id"], team["head"], "found", NOW9)
    from tests.test_objectives import give_cash
    give_cash(db, ledger.player_account_id(db, team["investment_banker"]), 1_000_000)
    before = ledger.balance(db, ledger.player_account_id(db, team["investment_banker"]))
    got = press.fact_check(db, team["investment_banker"], "chief", item["ref"], NOW9)
    assert got["verdict"] in ("holds", "fails")
    assert ledger.balance(db, ledger.player_account_id(db, team["investment_banker"])) == before - naira(data.CHECK_FEE_NAIRA)
    mine = next(i for i in intel.mine(db, team["head"], NOW9) if i["ref"] == item["ref"])
    assert mine["check"] in intel.VERDICTS.values()
    with pytest.raises(press.PressError, match="no member"):
        press.fact_check(db, team["investment_banker"], "nobody", item["ref"], NOW9)
    # A planted rumour: its truth is decided by the world, and who planted it is kept but never sent.
    planted = press.plant(db, team["investment_banker"], ticker=None, empire_name=_one(db, "SELECT name FROM empires WHERE kind = 'computer' LIMIT 1")["name"],
                          tone=-1, now=NOW9)
    assert "planted" not in repr(planted) and "truth" not in repr(planted)
    row = _one(db, "SELECT planted_by, truth FROM intel_items WHERE ref = %s", (planted["ref"],))
    assert row["planted_by"] == team["investment_banker"] and row["truth"] == "unknown"      # nothing hidden was read to start it
    with pytest.raises(press.PressError, match="One rumour a day"):
        press.plant(db, team["investment_banker"], ticker=_one(db, "SELECT ticker FROM companies WHERE listed LIMIT 1")["ticker"], empire_name=None,
                    tone=1, now=NOW9 + timedelta(hours=2))


def test_a_widely_read_story_moves_the_reputation_of_the_empire_it_names(db):
    empire, team = firm_of(db)
    j = _reporter(db, "bigreach")
    db.execute("INSERT INTO journalist_profiles (player_id, following) VALUES (%s, 500000) ON CONFLICT (player_id) DO UPDATE SET following = 500000", (j,))
    company = _one(db, "SELECT id, ticker FROM companies WHERE listed ORDER BY ticker LIMIT 1")
    w = careers.world_now(db, NOW9)
    # A takeover bid by the empire that failed is bad news for it.
    db.execute("INSERT INTO stake_disclosures (empire_id, company_id, bps, at) VALUES (%s, %s, 1000, %s)", (empire["id"], company["id"], NOW9))
    from simulation import newsroom_facts
    card = next((c for c in newsroom_facts.facts(db, NOW9) if c.get("empire_id") == empire["id"]), None)
    assert card is not None
    before = _rep(db, empire["id"])
    out = write(db, j, [card])
    change = _rep(db, empire["id"]) - before
    assert out["readers"] >= data.WIDELY_READ
    assert change == (data.PRESS_TONE_REPUTATION * card["tone"] if card["tone"] else 0)
    assert w["period"] >= 9
