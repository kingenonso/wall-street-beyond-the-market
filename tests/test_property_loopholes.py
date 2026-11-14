"""Stage 8: the ten-question loophole check, each question with its test.

 1. Can a seller bid up their own lot, or buy it back cheaply at a forced sale?            No: an owner cannot bid on it.
 2. Can anybody see a seller's lowest price, another bidder's limit, a title's flaw, or a
    property company's book value?                                                          No: none of them is ever sent.
 3. Can bidding, walking away and being outbid make or lose a kobo?                        No: every hold comes back; the ledger adds up.
 4. Can one salary back mortgages on many bids at once?                                    No: bids standing count against the limit.
 5. Can an empire bid without its desks' checks, above the Risk Manager's price, or be
    made to bid by somebody other than its head?                                           No.
 6. Can an empire buy a member's property at a price that carries the empire's money out?  No: an empire does not buy from its members.
 7. Can a player build on a plot and sell at once for more than it cost (a money machine)? No: building costs more than it adds.
 8. Can a member take a seat the headquarters added while the headquarters is down?        No: those seats are frozen.
 9. Can a leading bidder walk away, or anybody bid after the countdown ends?               No.
10. Can a partner be held to a bid for ever, or have their cash kept after the auction?    No: it is handed back when the auction ends.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from simulation import auctions, empires, headquarters, ledger
from simulation import property as prop
from simulation import world_data as data
from simulation.money import BPS, naira
from tests.conftest import join
from tests.test_builds import pro
from tests.test_careers import NOW9, sound
from tests.test_firm import firm_of, member
from tests.test_property import LATER, _dicts, _one, a_bank, a_unit, end, hand_over, lot

pytestmark = pytest.mark.world("eight")


def test_1_an_owner_cannot_bid_for_their_own_property_even_at_a_forced_sale(db):
    p = a_unit(db, "Lagos")
    owner, owner_account = pro(db, "asset_manager", "owner", cash_naira=900_000_000)
    hand_over(db, p["id"], owner_account)
    auction = auctions.owner_list(db, owner_account, p["id"], 0, NOW9)
    with pytest.raises(prop.PropertyError, match="your own"):
        auctions.place_bid(db, owner_account, auction, auctions._auction(db, auction)["start_price"], LATER, player_id=owner)
    other = a_unit(db, "Kano")
    hand_over(db, other["id"], owner_account)
    with db.transaction():
        forced = auctions.force_sale(db, other["id"], "tax", 9, NOW9)
    with pytest.raises(prop.PropertyError, match="your own"):
        auctions.place_bid(db, owner_account, forced, auctions.minimum(auctions._auction(db, forced)), LATER, player_id=owner)


def test_2_no_secret_ever_leaves_the_server(client, db):
    assert join(client, {"email": "peek@example.com", "display_name": "Peek", "password": "correct horse battery",
                         "date_of_birth": "1990-01-01", "profile_icon": "male"}).status_code == 201
    rival, rival_account = pro(db, "investment_banker", "rival", cash_naira=900_000_000)
    a = _one(db, "SELECT * FROM auctions WHERE status = 'open' AND property_id IS NOT NULL AND opens_at <= now() ORDER BY id LIMIT 1") or \
        _one(db, "SELECT * FROM auctions WHERE status = 'open' AND property_id IS NOT NULL ORDER BY opens_at LIMIT 1")
    db.execute("UPDATE auctions SET opens_at = now() - interval '1 hour', ends_at = now() + interval '20 hours' WHERE id = %s", (a["id"],))
    auctions.place_bid(db, rival_account, a["id"], a["fair"] * 2, db.execute("SELECT now()").fetchone()[0], player_id=rival)
    text = client.get("/api/property").text
    for secret in ("reserve", "title_flaw", "book_value", "limit_price", "fortune_seed", str(a["fair"] * 2)):
        assert secret not in text, secret
    reserve = str(_one(db, "SELECT reserve FROM auctions WHERE id = %s", (a["id"],))["reserve"])
    assert f'"{reserve}"' not in text
    # A bidder is shown by number, never by name.
    assert "rival" not in text.lower()


def test_3_bidding_walking_away_and_being_outbid_neither_make_nor_lose_a_kobo(db):
    p = a_unit(db, "Abuja")
    a = lot(db, p["id"])
    one, one_account = pro(db, "asset_manager", "one", cash_naira=900_000_000)
    two, two_account = pro(db, "investment_banker", "two", cash_naira=900_000_000)
    start = {one_account: ledger.balance(db, one_account), two_account: ledger.balance(db, two_account)}
    first = auctions.place_bid(db, one_account, a["id"], a["start_price"] * 2, LATER, player_id=one)
    auctions.place_bid(db, one_account, a["id"], a["start_price"] * 3, LATER, player_id=one)       # raises its own bid
    auctions.place_bid(db, two_account, a["id"], a["start_price"] * 4, LATER, player_id=two)       # outbids
    assert ledger.balance(db, one_account) == start[one_account]
    with pytest.raises(prop.PropertyError):
        auctions.withdraw(db, one_account, first["bid_id"], LATER)                                # already beaten, nothing to withdraw
    end(db, a)
    price = auctions._auction(db, a["id"])["price"]
    fee = price * data.REGISTRATION_FEE_BPS // BPS                      # (the gap stage: registering the transfer)
    assert ledger.balance(db, two_account) == start[two_account] - price - fee
    assert ledger.balance(db, ledger.account_id(db, prop.HELD)) == 0
    sound(db)


def test_4_one_salary_cannot_back_mortgages_on_many_bids_at_once(db):
    player, account = pro(db, "asset_manager", "stretch", level=10, cash_naira=900_000_000)
    bank = a_bank(db)
    cap = prop.mortgage_limit(db, account, naira(10**12), NOW9)
    lots = [lot(db, a_unit(db, city)["id"]) for city in ("Lagos", "Abuja", "Port Harcourt")]
    placed = 0
    for a in lots:
        limit = max(a["start_price"], cap * 2)                      # half of it borrowed: the whole salary limit
        try:
            auctions.place_bid(db, account, a["id"], limit, LATER, player_id=player, mortgage_bank=bank["id"], mortgage_bps=5000)
            placed += 1
        except prop.PropertyError as refused:
            assert "at most" in str(refused) or "room" in str(refused)
    assert placed == 1
    # Raising one's own bid on the same lot is not counted twice.
    if placed:
        a = lots[0]
        auctions.place_bid(db, account, a["id"], max(a["start_price"], cap * 2) + naira(1_000), LATER, player_id=player,
                           mortgage_bank=bank["id"], mortgage_bps=4900)
    sound(db)


def test_5_an_empire_bids_only_through_its_head_after_every_check_and_within_the_risk_managers_price(db):
    empire, team = firm_of(db)
    a = lot(db, a_unit(db, "Lagos")["id"])
    for player in (team["asset_manager"], team["risk_manager"], team["investment_banker"]):
        with pytest.raises(prop.PropertyError):
            auctions.empire_bid(db, player, a["id"], a["start_price"], LATER)
    with pytest.raises(prop.PropertyError, match="Still to do"):
        auctions.empire_bid(db, team["head"], a["id"], a["start_price"], LATER)
    auctions.check(db, team["investment_banker"], a["id"], "title", {}, LATER)
    auctions.check(db, team["asset_manager"], a["id"], "valuation", {"value": a["fair"]}, LATER)
    auctions.check(db, team["risk_manager"], a["id"], "limit", {"limit": a["start_price"] * 2}, LATER)
    auctions.check(db, team["investment_banker"], a["id"], "money", {"mortgage_bps": 0}, LATER)
    with pytest.raises(prop.PropertyError, match="top price"):
        auctions.empire_bid(db, team["head"], a["id"], a["start_price"] * 2 + 1, LATER)
    # A desk cannot do another desk's check.
    with pytest.raises(prop.PropertyError):
        auctions.check(db, team["investment_banker"], a["id"], "limit", {"limit": a["fair"] * 10}, LATER)
    # The empire's own account is never used through a player's own bidding door.
    with pytest.raises(prop.PropertyError):
        auctions.check(db, team["investment_banker"], a["id"], "money", {"mortgage_bps": data.EMPIRE_MORTGAGE_MOST_BPS + 100, "bank": a_bank(db)["id"]}, LATER)
    sound(db)


def test_6_an_empire_does_not_buy_from_one_of_its_own_members(db):
    empire, team = firm_of(db)
    p = a_unit(db, "Lagos")
    seller_account = ledger.player_account_id(db, team["asset_manager"])
    hand_over(db, p["id"], seller_account)
    auction = auctions.owner_list(db, seller_account, p["id"], 0, NOW9)
    a = auctions._auction(db, auction)
    auctions.check(db, team["investment_banker"], auction, "title", {}, LATER)
    auctions.check(db, team["asset_manager"], auction, "valuation", {"value": a["fair"] * 5}, LATER)
    auctions.check(db, team["risk_manager"], auction, "limit", {"limit": a["fair"] * 5}, LATER)
    auctions.check(db, team["investment_banker"], auction, "money", {"mortgage_bps": 0}, LATER)
    with pytest.raises(prop.PropertyError, match="own members"):
        auctions.empire_bid(db, team["head"], auction, a["fair"] * 5, LATER)


def test_7_building_on_a_plot_costs_more_than_it_adds_in_every_city(db):
    rate = prop.policy_rate(db)
    ds = prop.districts(db)
    for city in data.DISTRICTS:
        plot = a_unit(db, city, standing=False, claims_free=False)          # (the same plots as before the gap stage)
        d = ds[plot["district_id"]]
        before = prop.value(plot, d, rate)
        kind = data.DISTRICT_BUILDINGS[d["kind"]][0]
        built = {**plot, "kind": kind, "status": "standing", "condition": 100, "base_rent": prop.base_rent(city, kind, plot["size_m2"])}
        plain = {**d, "premium_bps": 0, "infra_bps": 0, "rent_bps": 10000, "occupancy_bps": 9000}   # (at the start's rents: booms and works are real gains)
        added = prop.value(built, plain, rate) - prop.value(plot, plain, rate)
        assert prop.build_cost({**plot, "city": city}) > added, city
        assert before >= 0


def test_8_a_seat_the_headquarters_added_cannot_be_taken_while_it_is_down(db):
    empire, team = firm_of(db, n_cash=50_000_000_000)
    p = a_unit(db, "Lagos")
    hand_over(db, p["id"], empire["account_id"])
    headquarters.establish(db, team["head"], p["id"], NOW9)
    headquarters.raise_level(db, team["head"], 9, NOW9)            # Level 10: one more seat
    extra = _one(db, "SELECT * FROM empire_seats WHERE empire_id = %s AND slot = 3", (empire["id"],))
    assert extra is not None and not extra["hq_frozen"]
    db.execute("UPDATE headquarters SET collapsed_period = 9 WHERE empire_id = %s", (empire["id"],))
    headquarters.sync_seats(db, empire["id"])
    # Fill the build's two ordinary seats, then a newcomer of that build finds no seat.
    build = extra["build"]
    for n in range(4):
        if _one(db, "SELECT 1 FROM empire_seats WHERE empire_id = %s AND build = %s AND player_id IS NULL AND NOT hq_frozen", (empire["id"], build)) is None:
            break
        member(db, empires._empire(db, empire["id"]), team["head"], build, f"filler{n}")
    late, _ = pro(db, build, "late", level=4, cash_naira=1_000_000)
    with pytest.raises(empires.EmpireError):
        empires.apply(db, late, empire["id"], NOW9)
        asked = _one(db, "SELECT id FROM empire_applications WHERE player_id = %s AND status = 'waiting'", (late,))
        empires.decide_application(db, team["head"], asked["id"], True, NOW9)
    assert _one(db, "SELECT player_id FROM empire_seats WHERE empire_id = %s AND slot = 3", (empire["id"],))["player_id"] is None


def test_9_a_leading_bid_cannot_be_withdrawn_and_nobody_bids_after_the_end(db):
    a = lot(db, a_unit(db, "Kano")["id"])
    one, one_account = pro(db, "asset_manager", "one", cash_naira=900_000_000)
    bid = auctions.place_bid(db, one_account, a["id"], a["start_price"] * 2, LATER, player_id=one)
    with pytest.raises(prop.PropertyError, match="cannot be withdrawn"):
        auctions.withdraw(db, one_account, bid["bid_id"], LATER)
    two, two_account = pro(db, "investment_banker", "two", cash_naira=900_000_000)
    with pytest.raises(prop.PropertyError, match="not taking bids"):
        auctions.place_bid(db, two_account, a["id"], a["start_price"] * 5, a["ends_at"] + timedelta(seconds=1), player_id=two)
    with pytest.raises(prop.PropertyError, match="not taking bids"):
        auctions.place_bid(db, two_account, a["id"], a["start_price"] * 5, a["opens_at"] - timedelta(seconds=1), player_id=two)


def test_10_a_partners_cash_comes_back_when_the_auction_ends_whether_or_not_the_bid_won(db):
    a = lot(db, a_unit(db, "Aba")["id"])
    lead, lead_account = pro(db, "asset_manager", "lead", cash_naira=900_000_000)
    friend, friend_account = pro(db, "investment_banker", "friend", cash_naira=900_000_000)
    rich, rich_account = pro(db, "risk_manager", "rich", cash_naira=900_000_000)
    before = ledger.balance(db, friend_account)
    ask = auctions.ask_partner(db, lead_account, a["id"], friend_account, 3000, LATER)
    auctions.answer_partner(db, friend_account, ask, True, a["start_price"] * 2, LATER)
    assert ledger.balance(db, friend_account) < before
    auctions.place_bid(db, lead_account, a["id"], a["start_price"] * 2, LATER, player_id=lead, partner=ask)
    auctions.place_bid(db, rich_account, a["id"], a["start_price"] * 5, LATER, player_id=rich)
    end(db, a)
    assert ledger.balance(db, friend_account) == before
    assert prop.share_of(db, a["property_id"], friend_account) == 0
    assert _one(db, "SELECT status FROM auction_partners WHERE id = %s", (ask,))["status"] == "released"
    # A partner never asked to bid is never held: refusing costs nothing.
    other = lot(db, a_unit(db, "Lagos")["id"])
    ask2 = auctions.ask_partner(db, lead_account, other["id"], friend_account, 3000, LATER)
    auctions.answer_partner(db, friend_account, ask2, False, 0, LATER)
    assert ledger.balance(db, friend_account) == before
    sound(db)
