"""Stage 10, Part 2: ten ways a player might try to game information, investigations, the press desk, charities and the media
titles, each closed."""

from __future__ import annotations

from datetime import timedelta

import pytest
from psycopg.rows import dict_row

from simulation import auctions, careers, charity, exchange, intel, ledger, media, newsroom, press
from simulation import world_data as data
from simulation.money import naira
from simulation.property import PropertyError
from tests.conftest import ADULT, join
from tests.test_builds import pro
from tests.test_careers import NOW9
from tests.test_firm import firm_of
from tests.test_stage10a_loopholes import reporter

pytestmark = pytest.mark.world("eight")
SECRET_KEYS = ('"truth"', '"basis"', '"planted_by"', '"resolves_period"', '"resolves_day"', '"member_id"', '"connected"', '"reserve"', '"limit_price"')


def _one(db, sql, params=()):
    with db.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(sql, params).fetchall()
    return rows[0] if rows else None


def _piece(db, holder, *, truth="true", confidential=False, hours=4, company=None, kind="tip", status="rumour"):
    w = careers.world_now(db, NOW9)
    company = company or _one(db, "SELECT id, name, ticker FROM companies WHERE listed ORDER BY ticker LIMIT 1")
    item = intel.make(db, kind=kind, topic="company", truth=truth, basis="none", period=w["period"], day=w["day"], now=NOW9,
                      company_id=company["id"], tone=1, status=status, confidential=confidential, useful_until=NOW9 + timedelta(hours=hours),
                      words=f"Word around {company['name']}: good news is coming before the quarter is out.")
    intel.hold(db, item["id"], holder, "found", NOW9)
    return item


# 1. Can a player learn whether a piece is true, what it was drawn from, or who planted it, from any page?
def test_l1_no_page_sends_a_pieces_truth_basis_or_planter(db, client):
    me = reporter(client, db)
    client.post("/api/intel/tip/open")
    seller = pro(db, "accountant", "secretseller", level=10, cash_naira=1_000_000)[0]
    item = _piece(db, seller)
    intel.offer(db, seller, item["ref"], naira(50_000), NOW9)
    for path in ("/api/intel", "/api/rumours", "/api/investigations", "/api/charities", "/api/media"):
        got = client.get(path)
        assert got.status_code == 200, path
        for key in SECRET_KEYS:
            assert key not in got.text, (path, key)
    market = client.get("/api/intel").json()["market"]
    assert all("words" not in m for m in market if not m["held"])
    assert me


# 2. Can a player get a second Sealed Tip in a day, or buy one?
def test_l2_one_sealed_tip_a_day_and_none_for_sale(db):
    p = pro(db, "asset_manager", "twotips", level=10)[0]
    a = intel.sealed_tip(db, p, NOW9)
    b = intel.sealed_tip(db, p, NOW9 + timedelta(hours=3))
    assert a == b and _one(db, "SELECT count(*) AS n FROM sealed_tips WHERE player_id = %s", (p,))["n"] == 1
    # A sealed tip cannot be passed on or sold before it is opened.
    tip = _one(db, "SELECT i.ref FROM sealed_tips t JOIN intel_items i ON i.id = t.item_id WHERE t.player_id = %s", (p,))
    with pytest.raises(intel.IntelError):
        intel.offer(db, p, tip["ref"], naira(50_000), NOW9)
    from server import intel_routes
    assert not any("buy" in r.path and "tip" in r.path for r in intel_routes.app.routes if hasattr(r, "path"))


# 3. Can a player use a piece they do not hold, or one that has run out of time or been proved wrong?
def test_l3_only_a_holder_uses_a_piece_and_only_while_it_is_useful(db):
    owner = pro(db, "accountant", "holder", level=10, cash_naira=1_000_000)[0]
    j = pro(db, "journalist", "taker", level=10, cash_naira=1_000_000)[0]
    item = _piece(db, owner)
    for action in (lambda: intel.check(db, j, item["ref"], NOW9), lambda: intel.offer(db, j, item["ref"], naira(50_000), NOW9),
                   lambda: intel.give(db, j, item["ref"], "holder", NOW9)):
        with pytest.raises(intel.IntelError, match="do not hold"):
            action()
    newsroom.start(db, j, NOW9)
    with pytest.raises(newsroom.NewsroomError, match="do not hold"):
        newsroom.add_lead(db, j, item["ref"], NOW9)
    intel.give(db, owner, item["ref"], "taker", NOW9)
    with pytest.raises(newsroom.NewsroomError, match="no longer useful"):
        newsroom.add_lead(db, j, item["ref"], NOW9 + timedelta(hours=5))
    newsroom.add_lead(db, j, item["ref"], NOW9)
    db.execute("UPDATE intel_items SET status = 'disproved' WHERE id = %s", (item["id"],))
    with pytest.raises(newsroom.NewsroomError, match="no longer useful"):
        newsroom.publish(db, j, NOW9)


# 4. Can the market be gamed: buy twice, buy one's own, sell what has expired, or list without limit?
def test_l4_the_market_sells_each_buyer_one_copy_never_to_the_seller_and_never_expired(db):
    seller = pro(db, "accountant", "lister", level=10, cash_naira=1_000_000)[0]
    buyer = pro(db, "asset_manager", "copier", level=10, cash_naira=5_000_000)[0]
    items = [_piece(db, seller) for _ in range(data.INTEL_LISTINGS_MOST + 1)]
    for item in items[:-1]:
        intel.offer(db, seller, item["ref"], naira(20_000), NOW9)
    with pytest.raises(intel.IntelError, match="at once"):
        intel.offer(db, seller, items[-1]["ref"], naira(20_000), NOW9)
    listing = _one(db, "SELECT id FROM intel_listings WHERE seller = %s ORDER BY id LIMIT 1", (seller,))["id"]
    intel.buy(db, buyer, listing, NOW9)
    with pytest.raises(intel.IntelError, match="already hold"):
        intel.buy(db, buyer, listing, NOW9)
    with pytest.raises(intel.IntelError, match="your own"):
        intel.buy(db, seller, listing, NOW9)
    with pytest.raises(intel.IntelError, match="between"):
        intel.offer(db, buyer, items[0]["ref"], naira(1), NOW9)
    late = pro(db, "asset_manager", "latecomer", level=10, cash_naira=5_000_000)[0]
    with pytest.raises(intel.IntelError, match="no longer useful"):
        intel.buy(db, late, listing, NOW9 + timedelta(hours=6))


# 5. Can an exposé be made up, run twice, or run after someone else got there first?
def test_l5_an_expose_needs_documents_a_second_source_and_something_still_hidden(db):
    empire, team = firm_of(db)
    j = pro(db, "journalist", "fabricator", level=40)[0]
    f = press.open_file(db, j, empire["name"], None, NOW9)
    db.execute("UPDATE investigations SET documents = 3, confirmed = true WHERE id = %s", (f["id"],))
    with pytest.raises(press.PressError, match="documents and a second source"):
        press.publish_expose(db, j, f["id"], NOW9)                    # nothing was ever found: there is nothing to print
    w = careers.world_now(db, NOW9)
    book = _one(db, "INSERT INTO empire_books (empire_id, period, category, description, amount, genuine, entered_by, thief_level, at)"
                    " VALUES (%s, %s, 'supplies', 'Supplies', %s, false, %s, 4, %s) RETURNING id",
                (empire["id"], w["period"], naira(1_000_000), team["accountant"], NOW9))
    db.execute("UPDATE investigations SET basis = %s WHERE id = %s", (f"book:{book['id']}", f["id"]))
    # An audit gets there first: the trail is cold.
    db.execute("UPDATE empire_books SET found = true WHERE id = %s", (book["id"],))
    with pytest.raises(press.PressError, match="got there first"):
        press.publish_expose(db, j, f["id"], NOW9)
    with pytest.raises(press.PressError, match="investigate the empire they sit in"):
        press.open_file(db, team["journalist"], empire["name"], None, NOW9)


# 6. Can someone answer a crisis for an empire they do not speak for, late, or twice?
def test_l6_only_the_empire_answers_its_crisis_once_and_in_time(db):
    empire, team = firm_of(db)
    c = press.open_crisis(db, empire["id"], "report", "story:424242", "A report about the empire.", "true", NOW9)
    outsider = pro(db, "journalist", "meddler", level=10)[0]
    with pytest.raises(press.PressError, match="do not speak"):
        press.answer_crisis(db, outsider, c["id"], "deny", "That is all nonsense from start to end.", NOW9)
    press.answer_crisis(db, team["journalist"], c["id"], "admit", "We have found the problem and are fixing it.", NOW9)
    with pytest.raises(press.PressError, match="closed"):
        press.answer_crisis(db, team["head"], c["id"], "deny", "We did no such thing at all, ever.", NOW9)
    # A second crisis about the same thing is not opened twice.
    assert press.open_crisis(db, empire["id"], "report", "story:424242", "Again.", "true", NOW9) is None


# 7. Can anyone but the hunter learn who leaked; can a hunt run twice; can a member leak what is not so?
def test_l7_leaks_are_true_and_the_leaker_is_known_only_to_a_successful_hunter(db, monkeypatch):
    empire, team = firm_of(db)
    j = pro(db, "journalist", "leakdesk", level=10)[0]
    with pytest.raises(press.PressError, match="no such hidden pact"):
        press.leak(db, team["lawyer"], "pact", "leakdesk", NOW9, pact_id=999999)
    with pytest.raises(press.PressError, match="no purchase in hand"):
        press.leak(db, team["lawyer"], "plan", "leakdesk", NOW9)
    from tests.test_objectives import give_shares
    company = _one(db, "SELECT ticker FROM companies WHERE listed ORDER BY ticker LIMIT 1")
    give_shares(db, empire["account_id"], company["ticker"], 1000)
    press.leak(db, team["lawyer"], "holding", "leakdesk", NOW9, ticker=company["ticker"])
    piece = intel.mine(db, j, NOW9)[0]
    assert "counsel" not in repr(piece).lower()
    newsroom.start(db, j, NOW9)
    newsroom.add_lead(db, j, piece["ref"], NOW9)
    newsroom.publish(db, j, NOW9)
    leak = press.leaks_of(db, empire["id"])[0]
    assert "counsel" not in repr(press.desk(db, team["head"], NOW9)).lower()
    monkeypatch.setattr(data, "LEAK_HUNT_RANGE_BPS", (10_000, 10_000))
    found = press.hunt(db, team["journalist"], leak["id"], NOW9)
    assert found["found"] and "counsel" in found["words"]
    with pytest.raises(press.PressError, match="already"):
        press.hunt(db, team["head"], leak["id"], NOW9)
    assert "counsel" not in repr(press.desk(db, team["head"], NOW9)).lower()      # the name went to the hunter, not onto the desk


# 8. Can a charity pay its trustee, hide a grant to insiders from the Money Watch, or be founded twice by one person?
def test_l8_a_charity_never_pays_its_trustee_and_insiders_are_on_the_record(db):
    p = pro(db, "accountant", "trusty", level=10, cash_naira=30_000_000)[0]
    c = charity.found(db, p, "Kind Hearts", "health", "Abuja", naira(10_000_000), NOW9)
    with pytest.raises(charity.CharityError, match="already run"):
        charity.found(db, p, "Kind Hearts Two", "health", "Abuja", naira(1_000_000), NOW9)
    with pytest.raises(charity.CharityError, match="themselves"):
        charity.grant(db, p, c["id"], naira(1_000_000), "A salary", NOW9, to_name="trusty")
    donor = pro(db, "lawyer", "donor", level=10, cash_naira=5_000_000)[0]
    charity.give(db, donor, c["id"], naira(2_000_000), NOW9)
    charity.grant(db, p, c["id"], naira(5_000_000), "An award for service", NOW9, to_name="donor")
    assert _one(db, "SELECT connected FROM charity_grants WHERE to_player = %s", (donor,))["connected"]
    assert "connected" not in repr(charity.view(db, c["id"], donor))
    charity.at_close(db, careers.world_now(db, NOW9)["period"], NOW9)
    account = _one(db, "SELECT account_id FROM charities WHERE id = %s", (c["id"],))["account_id"]
    assert _one(db, "SELECT 1 AS x FROM money_watch_flags WHERE account_id = %s", (account,))


# 9. Can a title be bought on borrowed or shared money, by its own owner, or printed in by someone who does not own it?
def test_l9_a_title_is_bought_outright_never_by_its_owner_and_printed_in_only_by_its_owners(db):
    p, account = pro(db, "journalist", "mogul", level=20, cash_naira=200_000_000)
    government = ledger.account_id(db, ledger.TREASURY)
    t = _one(db, "SELECT * FROM media_titles WHERE owner_account = %s ORDER BY id LIMIT 1", (government,)) or \
        _one(db, "SELECT * FROM media_titles ORDER BY id LIMIT 1")
    a = auctions.open_title_auction(db, t["id"], t["owner_account"], "listing", 0, 100, media.fair(t), NOW9, 9) \
        if not _one(db, "SELECT 1 AS x FROM auctions WHERE title_id = %s AND status = 'open'", (t["id"],)) else \
        _one(db, "SELECT id FROM auctions WHERE title_id = %s AND status = 'open'", (t["id"],))["id"]
    row = _one(db, "SELECT * FROM auctions WHERE id = %s", (a,))
    when = max(row["opens_at"], NOW9) + timedelta(minutes=1)
    with pytest.raises(PropertyError, match="outright"):
        auctions.ask_partner(db, account, a, ledger.player_account_id(db, pro(db, "lawyer", "partner", level=4)[0]), 5000, when)
    with pytest.raises(PropertyError, match="your own"):
        auctions.place_bid(db, t["owner_account"], a, row["fair"] * 3, when)
    newsroom.start(db, p, NOW9)
    with pytest.raises(newsroom.NewsroomError, match="own"):
        newsroom.set_title(db, p, t["id"], NOW9)
    # A sale whose seller no longer owns the title does not go through.
    auctions.place_bid(db, account, a, row["fair"] * 3, when, player_id=p)
    db.execute("UPDATE media_titles SET owner_account = %s WHERE id = %s", (account, t["id"]))
    auctions.run(db, row["ends_at"] + timedelta(minutes=1))
    assert _one(db, "SELECT status FROM auctions WHERE id = %s", (a,))["status"] == "unsold"


# 10. Can trading on information from inside a company escape the record: through the empire's account, or after buying it?
def test_l10_dealing_on_confidential_information_is_recorded_however_it_is_done(db):
    empire, team = firm_of(db)
    company = _one(db, "SELECT id, name, ticker FROM companies WHERE listed ORDER BY ticker LIMIT 1")
    seller = pro(db, "accountant", "insiderseller", level=10, cash_naira=1_000_000)[0]
    item = _piece(db, seller, confidential=True, company=company)
    listing = intel.offer(db, seller, item["ref"], naira(20_000), NOW9)["listing_id"]
    from tests.test_objectives import give_cash
    give_cash(db, ledger.player_account_id(db, team["head"]), 1_000_000)
    intel.buy(db, team["head"], listing, NOW9)
    from simulation import empires
    try:
        empires.trade_shares(db, team["head"], ticker=company["ticker"], side="buy", kind="market", quantity=10, limit_price=None, now=NOW9)
    except empires.EmpireError:
        pass
    dealt = _one(db, "SELECT * FROM confidential_dealings WHERE player_id = %s", (team["head"],))
    assert dealt and dealt["account_id"] == empire["account_id"] and dealt["item_id"] == item["id"]
    # Laid only at the door of who placed the order: a member who holds the same piece but did not trade is not recorded.
    intel.hold(db, item["id"], team["accountant"], "given", NOW9, from_player=team["head"])
    try:
        empires.trade_shares(db, team["head"], ticker=company["ticker"], side="buy", kind="market", quantity=5, limit_price=None, now=NOW9)
    except empires.EmpireError:
        pass
    assert _one(db, "SELECT 1 AS x FROM confidential_dealings WHERE player_id = %s", (team["accountant"],)) is None
