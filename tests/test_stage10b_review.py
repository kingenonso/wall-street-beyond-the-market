"""Stage 10, Part 2: the independent review's findings, each fixed and tested."""

from __future__ import annotations

from datetime import timedelta

import pytest
from psycopg.rows import dict_row

from simulation import (
    auctions,
    careers,
    charity,
    empires,
    intel,
    ledger,
    media,
    newsroom,
    press,
)
from simulation import world_data as data
from simulation.money import naira
from simulation.property import PropertyError
from tests.test_builds import pro
from tests.test_careers import NOW9
from tests.test_firm import firm_of

pytestmark = pytest.mark.world("eight")
DAY = timedelta(days=1)


def _one(db, sql, params=()):
    with db.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(sql, params).fetchall()
    return rows[0] if rows else None


def _rep(db, empire_id):
    return _one(db, "SELECT reputation FROM empires WHERE id = %s", (empire_id,))["reputation"]


def _company(db):
    return _one(db, "SELECT id, name, ticker, sector, headquarters FROM companies WHERE listed ORDER BY ticker LIMIT 1")


# 1. A crisis must not give away whether a hidden thing is so.
def test_r1_a_computer_empire_says_nothing_and_a_reports_answer_counts_only_once_the_report_is_settled(db):
    computer = _one(db, "SELECT * FROM empires WHERE kind = 'computer' ORDER BY id LIMIT 1")
    before = _rep(db, computer["id"])
    for n, truth in enumerate(("true", "false")):
        press.open_crisis(db, computer["id"], "report", f"story:{8100 + n}", "A report.", truth, NOW9)
    rows = db.execute("SELECT stance, change, statement FROM crises WHERE empire_id = %s", (computer["id"],)).fetchall()
    assert all(r == (None, 0, None) for r in rows)                                  # the same whatever is so
    assert _rep(db, computer["id"]) == before
    assert _one(db, "SELECT 1 AS x FROM news_items WHERE kind = 'statement' AND story LIKE 'crisis:%%'") is None
    # A player empire's answer to a report waits for the report: and the lawyer's feed never lists what came of it.
    empire, team = firm_of(db)
    w = careers.world_now(db, NOW9)
    item = intel.make(db, kind="rumour", topic="theft", truth="true", basis="none", period=w["period"], day=w["day"], now=NOW9,
                      empire_id=empire["id"], words="Someone at the empire may be taking its money.")
    c = press.open_crisis(db, empire["id"], "report", "story:8200", "A report.", "true", NOW9, item_id=item["id"])
    out = press.answer_crisis(db, team["head"], c["id"], "deny", "There is nothing in this at all, we are sure.", NOW9)
    assert "when the report is borne out" in out["words"]
    assert next(x for x in press.desk(db, team["head"], NOW9)["crises"] if x["id"] == c["id"])["change"] is None
    intel._settle(db, item, "true", NOW9 + DAY)
    lawyer = pro(db, "lawyer", "feedreader", level=10)[0]
    assert "Denied" not in repr(intel.desk_feed(db, lawyer, NOW9 + DAY))


# 2. Starting a rumour reads nothing hidden, cannot be checked by its starter, and does not help an investigation.
def test_r2_a_planted_rumour_reads_nothing_hidden_and_cannot_be_used_to_probe(db):
    empire, team = firm_of(db)
    w = careers.world_now(db, NOW9)
    other = _one(db, "SELECT * FROM empires WHERE kind = 'computer' ORDER BY id LIMIT 1")
    db.execute("INSERT INTO empire_books (empire_id, period, category, description, amount, genuine, entered_by, thief_level, at)"
               " VALUES (%s, %s, 'supplies', 'Supplies', %s, false, %s, 4, %s)", (other["id"], w["period"], naira(1_000_000), team["accountant"], NOW9))
    planted = press.plant(db, team["journalist"], ticker=None, empire_name=other["name"], tone=-1, now=NOW9)
    row = _one(db, "SELECT truth, basis FROM intel_items WHERE ref = %s", (planted["ref"],))
    assert row == {"truth": "unknown", "basis": "planted"}
    with pytest.raises(intel.IntelError, match="started this rumour"):
        intel.check(db, team["journalist"], planted["ref"], NOW9)
    # Passed to the head and checked by the desk that started it: still refused.
    intel.hold(db, _one(db, "SELECT id FROM intel_items WHERE ref = %s", (planted["ref"],))["id"], team["head"], "given", NOW9)
    with pytest.raises(press.PressError, match="started this rumour"):
        press.fact_check(db, team["journalist"], "chief", planted["ref"], NOW9)


# 3. Dropping and reopening a file gives no extra searches.
def test_r3_one_search_a_day_on_a_target_whatever_the_file(db):
    empire, team = firm_of(db)
    j = pro(db, "journalist", "redigger", level=40)[0]
    f = press.open_file(db, j, empire["name"], None, NOW9)
    press.dig(db, j, f["id"], NOW9)
    press.drop_file(db, j, f["id"])
    g = press.open_file(db, j, empire["name"], None, NOW9)
    with pytest.raises(press.PressError, match="searched today"):
        press.dig(db, j, g["id"], NOW9 + timedelta(hours=1))
    assert press.dig(db, j, g["id"], NOW9 + DAY)["status"] == "open"


# 4. An empire's money given away or spent on a title stays within what its head may sign for.
def test_r4_charity_gifts_and_title_bids_stay_within_the_heads_limit_and_the_trustee_is_the_head(db):
    empire, team = firm_of(db)
    seat = empires.seat_of(db, team["head"])
    room = empires.signing_limit(db, seat)
    with pytest.raises(charity.CharityError, match="sign for"):
        charity.found(db, team["head"], "Lagoon Gives", "education", "Lagos", room + naira(1), NOW9, for_empire=True)
    c = charity.found(db, team["head"], "Lagoon Gives", "education", "Lagos", naira(2_000_000), NOW9, for_empire=True)
    with pytest.raises(charity.CharityError, match="sign for"):
        charity.give(db, team["head"], c["id"], room, NOW9, from_empire=True)
    # A new head takes over the charity's grants.
    db.execute("UPDATE empires SET head_player_id = %s WHERE id = %s", (team["accountant"], empire["id"]))
    with pytest.raises(charity.CharityError, match="trustee"):
        charity.grant(db, team["head"], c["id"], naira(100_000), "Books for a school", NOW9)
    charity.grant(db, team["accountant"], c["id"], naira(100_000), "Books for a school", NOW9)
    db.execute("UPDATE empires SET head_player_id = %s WHERE id = %s", (team["head"], empire["id"]))
    # Titles: an owner's lowest price, and an empire's bid, are at most twice what a title is worth.
    owner, account = pro(db, "accountant", "titleowner", level=10, cash_naira=10_000_000)
    t = _one(db, "SELECT * FROM media_titles ORDER BY id DESC LIMIT 1")
    if _one(db, "SELECT 1 AS x FROM auctions WHERE title_id = %s AND status = 'open'", (t["id"],)):
        db.execute("UPDATE auctions SET status = 'cancelled' WHERE title_id = %s AND status = 'open'", (t["id"],))
    db.execute("UPDATE media_titles SET owner_account = %s, owner_player = %s, owner_empire = NULL WHERE id = %s", (account, owner, t["id"]))
    value = media.fair(t)
    with pytest.raises(PropertyError, match="twice"):
        media.owner_list(db, owner, t["id"], value * 3, NOW9)
    a = media.owner_list(db, owner, t["id"], value, NOW9)
    with pytest.raises(PropertyError, match="twice"):
        auctions.empire_bid(db, team["head"], a, value * 3, NOW9 + timedelta(minutes=1))


# 5. The leaker cannot use up the hunt for their own leak.
def test_r5_a_leakers_hunt_of_their_own_leak_leaves_the_hunt_for_the_head(db, monkeypatch):
    empire, team = firm_of(db)
    j = pro(db, "journalist", "outsidedesk", level=10)[0]
    from tests.test_objectives import give_shares
    company = _company(db)
    give_shares(db, empire["account_id"], company["ticker"], 1000)
    press.leak(db, team["journalist"], "holding", "outsidedesk", NOW9, ticker=company["ticker"])
    piece = intel.mine(db, j, NOW9)[0]
    newsroom.start(db, j, NOW9)
    newsroom.add_lead(db, j, piece["ref"], NOW9)
    newsroom.publish(db, j, NOW9)
    leak = press.leaks_of(db, empire["id"])[0]
    assert not press.hunt(db, team["journalist"], leak["id"], NOW9)["found"]
    monkeypatch.setattr(data, "LEAK_HUNT_RANGE_BPS", (10_000, 10_000))
    assert press.hunt(db, team["head"], leak["id"], NOW9)["found"]


# 6 and 10. A piece the record has already borne out is old news: no push on the price, and marked borne out at once.
def test_r6_r10_a_report_already_borne_out_is_old_news_and_settled_at_once(db):
    j = pro(db, "journalist", "stale", level=30)[0]
    db.execute("INSERT INTO journalist_profiles (player_id, following) VALUES (%s, 500000) ON CONFLICT (player_id) DO UPDATE SET following = 500000", (j,))
    w = careers.world_now(db, NOW9)
    company = _company(db)
    item = intel.make(db, kind="tip", topic="company", truth="worthless", basis="public", period=w["period"], day=w["day"], now=NOW9,
                      company_id=company["id"], tone=1, status="verified", resolved=True, useful_until=NOW9 + timedelta(hours=4),
                      words=f"{company['name']} has had good news this quarter.")
    intel.hold(db, item["id"], j, "found", NOW9)
    newsroom.start(db, j, NOW9)
    newsroom.add_lead(db, j, item["ref"], NOW9)
    out = newsroom.publish(db, j, NOW9)
    assert out["nudges"] == []
    assert _one(db, "SELECT lead_outcome FROM stories WHERE id = %s", (out["story_id"],))["lead_outcome"] == "confirmed"


# 7. A wrong report needs its own correction, even when the story was corrected before.
def test_r7_a_wrong_report_needs_a_correction_even_after_an_earlier_one(db):
    j = pro(db, "journalist", "twicewrong", level=30)[0]
    w = careers.world_now(db, NOW9)
    company = _company(db)
    item = intel.make(db, kind="tip", topic="company", truth="false", basis="none", period=w["period"], day=w["day"], now=NOW9,
                      company_id=company["id"], tone=1, useful_until=NOW9 + timedelta(hours=4), resolves=(w["period"], 90),
                      words=f"Word around {company['name']}: good news is coming before the quarter is out.")
    intel.hold(db, item["id"], j, "found", NOW9)
    newsroom.start(db, j, NOW9)
    newsroom.add_lead(db, j, item["ref"], NOW9)
    out = newsroom.publish(db, j, NOW9)
    db.execute("UPDATE stories SET correction_due = true, correct_by = %s WHERE id = %s", (NOW9 + DAY, out["story_id"]))
    newsroom.correct(db, j, out["story_id"], NOW9 + timedelta(hours=1))
    intel._settle(db, item, "false", NOW9 + timedelta(hours=2))
    assert [s["id"] for s in newsroom.to_correct(db, j)] == [out["story_id"]]
    newsroom.correct(db, j, out["story_id"], NOW9 + timedelta(hours=3))
    assert newsroom.to_correct(db, j) == []


# 8. A forecast cannot be checked before it is settled: the check is a coin toss, and nobody's check changes what others see.
def test_r8_a_forecast_is_unknown_until_settled(db):
    j = pro(db, "journalist", "forecaster", level=30)[0]
    db.execute("INSERT INTO sources (journalist_id, kind, started_period, ready_period, reliability_bps, status, at)"
               " VALUES (%s, 'ministry', 1, 3, 8000, 'active', %s)", (j, NOW9))
    s = _one(db, "SELECT id FROM sources WHERE journalist_id = %s", (j,))
    hint = intel.ask_source(db, j, s["id"], NOW9)
    assert _one(db, "SELECT truth FROM intel_items WHERE ref = %s", (hint["ref"],))["truth"] == "unknown"
    from tests.test_objectives import give_cash
    give_cash(db, ledger.player_account_id(db, j), 1_000_000)
    intel.check(db, j, hint["ref"], NOW9)
    assert _one(db, "SELECT status FROM intel_items WHERE ref = %s", (hint["ref"],))["status"] == "lead"


# 11. A charity's name is in words.
def test_r11_a_charitys_name_has_no_figures(db):
    p = pro(db, "accountant", "namer", level=10, cash_naira=5_000_000)[0]
    with pytest.raises(charity.CharityError, match="no figures"):
        charity.found(db, p, "Give 100 Percent", "arts", "Aba", naira(1_000_000), NOW9)


# Minor: before buying, a pact or theft piece shows only what it is about, not the names that are the claim.
def test_minor_a_pact_or_theft_piece_shows_no_names_until_bought(db):
    seller = pro(db, "lawyer", "pactseller", level=10, cash_naira=1_000_000)[0]
    buyer = pro(db, "asset_manager", "pactbuyer", level=10, cash_naira=1_000_000)[0]
    w = careers.world_now(db, NOW9)
    a, b = db.execute("SELECT name, id FROM empires WHERE kind = 'computer' ORDER BY id LIMIT 2").fetchall()
    item = intel.make(db, kind="tip", topic="pact", truth="false", basis="none", period=w["period"], day=w["day"], now=NOW9,
                      empire_id=a[1], other_empire_id=b[1], useful_until=NOW9 + timedelta(hours=4),
                      words=f"{a[0]} and {b[0]} are said to have a private understanding.")
    intel.hold(db, item["id"], seller, "found", NOW9)
    intel.offer(db, seller, item["ref"], naira(20_000), NOW9)
    seen = next(m for m in intel.market(db, buyer, NOW9) if m["ref"] == item["ref"])
    assert seen["about"] == {"topic": "pact"} and a[0] not in repr(seen)


# Found by the ten-year run: a check or a purchase without the cash is refused plainly, not a crash.
def test_run_a_check_or_a_purchase_without_the_cash_is_refused(db):
    poor = pro(db, "risk_manager", "pennyless", level=10, cash_naira=0)[0]
    account = ledger.player_account_id(db, poor)
    left = ledger.balance(db, account)
    if left:
        ledger.transfer(db, payer=account, receiver=ledger.account_id(db, ledger.TREASURY), amount=left, kind="test_cash", memo="Test: empty")
    w = careers.world_now(db, NOW9)
    company = _company(db)
    item = intel.make(db, kind="tip", topic="company", truth="true", basis="none", period=w["period"], day=w["day"], now=NOW9,
                      company_id=company["id"], tone=1, useful_until=NOW9 + timedelta(hours=4), words=f"Word around {company['name']}: good news.")
    intel.hold(db, item["id"], poor, "found", NOW9)
    with pytest.raises(intel.IntelError, match="not the cash"):
        intel.check(db, poor, item["ref"], NOW9)
    seller = pro(db, "accountant", "richseller", level=10, cash_naira=1_000_000)[0]
    other = intel.make(db, kind="tip", topic="company", truth="true", basis="none", period=w["period"], day=w["day"], now=NOW9,
                       company_id=company["id"], tone=1, useful_until=NOW9 + timedelta(hours=4), words=f"Word around {company['name']}: more.")
    intel.hold(db, other["id"], seller, "found", NOW9)
    listing = intel.offer(db, seller, other["ref"], naira(20_000), NOW9)["listing_id"]
    with pytest.raises(intel.IntelError, match="not the cash"):
        intel.buy(db, poor, listing, NOW9)
