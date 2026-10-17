"""Stage 10, Part 2: charity foundations, and media titles bought and sold at the Auction House."""

from __future__ import annotations

from datetime import timedelta

import pytest
from psycopg.rows import dict_row

from simulation import auctions, careers, charity, ledger, media, newsroom, press, quarters
from simulation import world_data as data
from simulation.money import naira
from simulation.property import PropertyError
from tests.conftest import after_quarters
from tests.test_builds import pro
from tests.test_careers import NOW9
from tests.test_firm import firm_of
from tests.test_newsroom import results_card

pytestmark = pytest.mark.world("eight")
DAY = timedelta(days=1)


def _one(db, sql, params=()):
    with db.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(sql, params).fetchall()
    return rows[0] if rows else None


def _rows(db, sql, params=()):
    with db.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def _rep(db, empire_id):
    return _one(db, "SELECT reputation FROM empires WHERE id = %s", (empire_id,))["reputation"]


def _player_rep(db, player):
    return _one(db, "SELECT reputation FROM players WHERE id = %s", (player,))["reputation"]


# ---------------------------------------------------------------------------
# Media titles
# ---------------------------------------------------------------------------

def _open_title_auction(db):
    a = _one(db, "SELECT * FROM auctions WHERE title_id IS NOT NULL AND status = 'open' ORDER BY id LIMIT 1")
    if a is None:
        government = ledger.account_id(db, ledger.TREASURY)
        t = _one(db, "SELECT * FROM media_titles WHERE owner_account = %s ORDER BY id LIMIT 1", (government,))
        value = media.fair(t)
        auctions.open_title_auction(db, t["id"], government, "listing", value * 9 // 10, value * 6 // 10, value, NOW9, 9)
        a = _one(db, "SELECT * FROM auctions WHERE title_id IS NOT NULL AND status = 'open' ORDER BY id LIMIT 1")
    return a


def test_five_titles_begin_with_the_government_which_sells_them_one_at_a_time_and_the_big_houses_bid(db):
    titles = _rows(db, "SELECT * FROM media_titles ORDER BY id")
    assert len(titles) == len(data.MEDIA_TITLES)
    assert {t["city"] for t in titles} == {c for _, _, c, _ in data.MEDIA_TITLES}
    sold = _rows(db, "SELECT * FROM auctions WHERE title_id IS NOT NULL ORDER BY id")
    assert sold, "the Government has put titles up for sale"
    assert _one(db, "SELECT 1 AS x FROM news_items WHERE kind = 'title_for_sale'")
    # Where an auction has ended, the big houses bought at no more than they thought it worth.
    for a in sold:
        if a["status"] == "sold":
            t = media.title(db, a["title_id"])
            assert _one(db, "SELECT sector FROM companies WHERE account_id = %s", (t["owner_account"],))["sector"] == "media"
            assert a["price"] <= a["fair"]
    # Nobody but a bidder sees their own limit, and the lowest price is never shown.
    view = auctions.title_view(db, NOW9)
    assert all("reserve" not in v and "limit_price" not in repr(v) for v in view)


def test_a_player_wins_a_title_at_auction_and_earns_from_its_readers(db):
    p, account = pro(db, "journalist", "publisher", level=20, cash_naira=200_000_000)
    a = _open_title_auction(db)
    when = max(a["opens_at"], NOW9) + timedelta(minutes=1)
    with pytest.raises(PropertyError, match="outright"):
        auctions.place_bid(db, account, a["id"], a["fair"] * 2, when, player_id=p, mortgage_bank=None, mortgage_bps=5000)
    auctions.place_bid(db, account, a["id"], a["fair"] * 2, when, player_id=p)
    auctions.run(db, a["ends_at"] + timedelta(minutes=1))
    settled = _one(db, "SELECT * FROM auctions WHERE id = %s", (a["id"],))
    assert settled["status"] == "sold"
    t = media.title(db, a["title_id"])
    assert t["owner_player"] == p and t["owner_account"] == account and t["paid"] == settled["price"]
    assert _one(db, "SELECT 1 AS x FROM news_items WHERE kind = 'title_sold'")
    # The owner prints a story in it: its audience reads it.
    newsroom.start(db, p, NOW9 + DAY)
    newsroom.set_title(db, p, t["id"], NOW9 + DAY)
    card = results_card(db)
    newsroom.add_fact(db, p, card["id"], NOW9 + DAY)
    newsroom.check_fact(db, p, card["id"], NOW9 + DAY)
    out = newsroom.publish(db, p, NOW9 + DAY)
    story = _one(db, "SELECT * FROM stories WHERE id = %s", (out["story_id"],))
    assert story["title_id"] == t["id"] and t["name"] in story["body"]
    # A quarter on, the owner is paid the profit; the title's audience has grown with the story.
    before = ledger.balance(db, account)
    quarters.close_due_quarters(db, after_quarters(9))
    result = _one(db, "SELECT * FROM media_results WHERE title_id = %s AND period = 9", (t["id"],))
    assert result["revenue"] > 0 and result["costs"] == result["revenue"] * data.MEDIA_COST_BPS // 10_000
    assert result["to_owner"] == result["profit"] and ledger.balance(db, account) >= before + result["to_owner"]
    assert media.title(db, t["id"])["audience"] >= t["audience"]
    # Someone outside cannot print in it.
    other, _ = pro(db, "journalist", "outsider", level=10)
    newsroom.start(db, other, after_quarters(9) + timedelta(hours=2))
    with pytest.raises(newsroom.NewsroomError, match="own"):
        newsroom.set_title(db, other, t["id"], after_quarters(9) + timedelta(hours=2))
    # The owner may sell it on, with a lowest price nobody sees.
    auction = media.owner_list(db, p, t["id"], naira(1_000_000), after_quarters(9) + timedelta(hours=2))
    assert _one(db, "SELECT reserve, reason FROM auctions WHERE id = %s", (auction,)) == {"reserve": naira(1_000_000), "reason": "owner"}
    with pytest.raises(PropertyError, match="already up"):
        media.owner_list(db, p, t["id"], naira(1_000_000), after_quarters(9) + timedelta(hours=2))


def test_an_empire_bids_for_a_title_without_the_property_checks_and_its_journalist_prints_in_it(db):
    empire, team = firm_of(db)
    a = _open_title_auction(db)
    when = max(a["opens_at"], NOW9) + timedelta(minutes=1)
    auctions.empire_bid(db, team["head"], a["id"], a["fair"] * 2, when)
    auctions.run(db, a["ends_at"] + timedelta(minutes=1))
    t = media.title(db, a["title_id"])
    assert t["owner_empire"] == empire["id"]
    assert [x["id"] for x in media.mine(db, team["journalist"])] == [t["id"]]
    assert media.mine(db, team["head"]) and media.title_for(db, team["journalist"], t["id"])


# ---------------------------------------------------------------------------
# Charities
# ---------------------------------------------------------------------------

def test_a_charity_is_founded_given_to_and_grants_to_its_cause_and_giving_builds_reputation(db):
    p, account = pro(db, "accountant", "giver", level=10, cash_naira=50_000_000)
    with pytest.raises(charity.CharityError, match="at least"):
        charity.found(db, p, "Small Hands", "education", "Lagos", naira(500_000), NOW9)
    c = charity.found(db, p, "Bright Futures", "education", "Lagos", naira(12_000_000), NOW9)
    assert c["given"] == naira(12_000_000) and c["yours"]
    friend, _ = pro(db, "lawyer", "friend", level=4, cash_naira=1_000_000)
    charity.give(db, friend, c["id"], naira(100_000), NOW9)
    households = _one(db, "SELECT account_id FROM households WHERE location = 'Lagos'")["account_id"]
    before = ledger.balance(db, households)
    with pytest.raises(charity.CharityError, match="trustee"):
        charity.grant(db, friend, c["id"], naira(1_000_000), "School books for Surulere", NOW9)
    with pytest.raises(charity.CharityError, match="themselves"):
        charity.grant(db, p, c["id"], naira(1_000_000), "A prize for me", NOW9, to_name="giver")
    charity.grant(db, p, c["id"], naira(11_000_000), "School books and fees across Lagos", NOW9)
    assert ledger.balance(db, households) == before + naira(11_000_000)
    rep = _player_rep(db, p)
    charity.at_close(db, careers.world_now(db, NOW9)["period"], NOW9)
    assert _player_rep(db, p) == rep + data.CHARITY_PLAYER_REPUTATION_MOST         # ₦11m to the cause: two points, the most a quarter
    public = charity.view(db, c["id"])
    assert public["to_cause"] == naira(11_000_000) and "connected" not in repr(public) and "grants" not in public


def test_an_empires_charity_builds_its_reputation_and_grants_to_insiders_are_flagged_and_can_be_exposed(db):
    empire, team = firm_of(db)
    c = charity.found(db, team["head"], "Lagoon Relief", "relief", "Port Harcourt", naira(60_000_000), NOW9, for_empire=True)
    assert _one(db, "SELECT 1 AS x FROM empire_books WHERE empire_id = %s AND category = 'Charity'", (empire["id"],))
    rep = _rep(db, empire["id"])
    charity.grant(db, team["head"], c["id"], naira(50_000_000), "Flood relief in the river towns", NOW9)
    period = careers.world_now(db, NOW9)["period"]
    charity.at_close(db, period, NOW9)
    assert _rep(db, empire["id"]) == rep + 2                                         # ₦50m: two points
    # Grants to its own members: insiders. The Money Watch flags it, privately.
    charity.give(db, team["head"], c["id"], naira(40_000_000), NOW9, from_empire=True)
    charity.grant(db, team["head"], c["id"], naira(20_000_000), "A study award", NOW9, to_name="scribe")
    charity.grant(db, team["head"], c["id"], naira(15_000_000), "A study award", NOW9, to_name="ledgerman")
    assert _rows(db, "SELECT connected FROM charity_grants WHERE to_player IS NOT NULL") == [{"connected": True}, {"connected": True}]
    charity.at_close(db, period, NOW9 + timedelta(hours=1))
    account = _one(db, "SELECT account_id FROM charities WHERE id = %s", (c["id"],))["account_id"]
    flagged = _one(db, "SELECT reason FROM money_watch_flags WHERE account_id = %s", (account,))
    assert flagged and "connected" in flagged["reason"]
    # A journalist investigates the charity: three documents, a second source, and the exposé.
    j, _ = pro(db, "journalist", "charitywatch", level=40, cash_naira=1_000_000)
    f = press.open_file(db, j, None, None, NOW9, charity_name="Lagoon Relief")
    t = NOW9
    for _ in range(60):
        f = press.dig(db, j, f["id"], t)
        if f["documents"] >= 2 and not f["confirmed"]:
            f = press.second_source(db, j, f["id"], t)
        if f["can_publish"]:
            break
        t += DAY
    assert f["can_publish"]
    rep = _rep(db, empire["id"])
    out = press.publish_expose(db, j, f["id"], t)
    assert "Lagoon Relief" in out["headline"]
    assert _one(db, "SELECT exposed FROM charities WHERE id = %s", (c["id"],))["exposed"]
    assert charity.view(db, c["id"])["under_a_cloud"]
    assert _rep(db, empire["id"]) == rep - data.CHARITY_EXPOSED_REPUTATION
    assert _one(db, "SELECT 1 AS x FROM crises WHERE empire_id = %s AND ref = %s", (empire["id"], f"charity:{c['id']}"))


def test_a_clean_charity_gives_an_investigator_nothing(db):
    p, _ = pro(db, "accountant", "cleangiver", level=10, cash_naira=20_000_000)
    c = charity.found(db, p, "Clean Water Kano", "water", "Kano", naira(5_000_000), NOW9)
    charity.grant(db, p, c["id"], naira(4_000_000), "Boreholes in three villages", NOW9)
    j, _ = pro(db, "journalist", "cleanwatch", level=40)
    f = press.open_file(db, j, None, None, NOW9, charity_name="Clean Water Kano")
    t = NOW9
    for _ in range(10):
        f = press.dig(db, j, f["id"], t)
        t += DAY
    assert f["documents"] == 0
    # A journalist does not investigate their own charity.
    own, _ = pro(db, "journalist", "owncharity", level=20, cash_naira=5_000_000)
    charity.found(db, own, "Arts for Aba", "arts", "Aba", naira(1_000_000), NOW9)
    with pytest.raises(press.PressError, match="own charity"):
        press.open_file(db, own, None, None, NOW9, charity_name="Arts for Aba")
