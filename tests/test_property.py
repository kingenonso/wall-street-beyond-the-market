"""Stage 8: land and property, the Auction House, and empire headquarters (owner, 12 October 2026).

Districts in five cities, buildings, small units and plots; rents from the households and companies of the
city; bubbles; mortgages limited by salary; repossession; property and land tax; building, renovating and
wear; live timed auctions extended by late bids, with partners, mortgages and rival computer bidders; the
desks' checks before an empire bids; and headquarters with levels, seats, upkeep, warnings and collapse.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from psycopg.rows import dict_row

from simulation import auctions, careers, empires, firm_tasks, headquarters, ledger, quarters
from simulation import property as prop
from simulation import world_data as data
from simulation.money import BPS, naira
from tests.conftest import after_quarters
from tests.test_builds import pro
from tests.test_careers import NOW9, sound
from tests.test_firm import firm_of
from tests.test_objectives import give_cash

pytestmark = pytest.mark.world("eight")
LATER = NOW9 + timedelta(hours=1)


def _dicts(db, sql, params=()):
    with db.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def _one(db, sql, params=()):
    rows = _dicts(db, sql, params)
    return rows[0] if rows else None


def hand_over(db, property_id, account, share=BPS):
    """Test set-up: the property simply belongs to this account (no money moves)."""
    db.execute("DELETE FROM property_holdings WHERE property_id = %s", (property_id,))
    db.execute("INSERT INTO property_holdings (property_id, account_id, share_bps, since_period) VALUES (%s, %s, %s, 8)",
               (property_id, account, share))


def a_unit(db, city="Lagos", kind=None, *, flawless=True, standing=True, claims_free=True):
    """A small, cheap building (or a plot) in a city."""
    rows = _dicts(db, "SELECT p.* FROM properties p JOIN districts d ON d.id = p.district_id WHERE d.city = %s"
                      " AND (%s::text IS NULL OR p.kind = %s) AND (NOT %s OR p.title_flaw_bps = 0)"
                      " AND ((%s AND p.status = 'standing' AND p.kind <> 'land') OR (NOT %s AND p.kind = 'land'))"
                      " AND NOT EXISTS (SELECT 1 FROM auctions a WHERE a.property_id = p.id AND a.status = 'open')"
                      " AND (NOT %s OR to_regclass('property_claims') IS NULL OR NOT EXISTS (SELECT 1 FROM property_claims c WHERE c.property_id = p.id))"
                      " ORDER BY p.size_m2, p.id", (city, kind, kind, flawless, standing, standing, flawless and claims_free))
    return rows[0]


def worth(db, property_id):
    p = _one(db, "SELECT * FROM properties WHERE id = %s", (property_id,))
    return prop.value(p, prop.districts(db)[p["district_id"]], prop.policy_rate(db))


def a_bank(db):
    return prop.lending_banks(db, 9)[0]


def lot(db, property_id, reserve=0, now=NOW9):
    """A company's building put up by the test as an owner's sale (by a holding account that is not a company)."""
    seller = ledger.account_id(db, ledger.INVESTORS_FOUNDERS)
    hand_over(db, property_id, seller)
    with db.transaction():
        auction = auctions._open_auction(db, property_id, seller, "owner", reserve, auctions._fair(db, property_id) // 2,
                                         auctions._fair(db, property_id), now, 9)
    return auctions._auction(db, auction)


def end(db, auction):
    a = auctions._auction(db, auction["id"] if isinstance(auction, dict) else auction)
    return auctions.run(db, a["ends_at"] + timedelta(seconds=1))


# ---------------------------------------------------------------------------
# Part A: the property market
# ---------------------------------------------------------------------------

@pytest.mark.world("fresh")
def test_a_new_world_has_districts_in_all_five_cities_owned_by_the_property_companies(db):
    ds = prop.districts(db)
    assert len(ds) == 25
    assert {d["city"] for d in ds.values()} == {"Lagos", "Abuja", "Port Harcourt", "Kano", "Aba"}
    props = _dicts(db, "SELECT * FROM properties")
    assert len(props) == 300
    kinds = {p["kind"] for p in props}
    assert "land" in kinds and len(kinds) >= 5
    companies = prop.company_accounts(db)
    owners = _dicts(db, "SELECT property_id, account_id, share_bps FROM property_holdings")
    assert len(owners) == 300 and all(o["account_id"] in companies and o["share_bps"] == BPS for o in owners)
    # Some titles are flawed (a secret); every building is in its owner's books at no more than four fifths of its fixed assets.
    assert 0 < sum(1 for p in props if p["title_flaw_bps"]) < 60
    assert all(p["book_value"] >= 0 for p in props)
    # Lagos is dearer than Kano, a building on Victoria Island dearer than one in Epe.
    rate = prop.policy_rate(db)
    by_city = {}
    for p in props:
        if p["status"] == "standing":
            by_city.setdefault(ds[p["district_id"]]["city"], []).append(prop.value(p, ds[p["district_id"]], rate) / p["size_m2"])
    assert sum(by_city["Lagos"]) / len(by_city["Lagos"]) > sum(by_city["Kano"]) / len(by_city["Kano"])
    sound(db)


def test_the_eight_quarter_world_has_its_listings_open_at_the_auction_house_staggered_over_the_week(db):
    open_ = _dicts(db, "SELECT * FROM auctions WHERE status = 'open' AND property_id IS NOT NULL ORDER BY opens_at")
    assert len(open_) == data.AUCTION_LISTINGS_A_QUARTER
    assert open_[-1]["opens_at"] - open_[0]["opens_at"] > timedelta(days=5)
    assert all(a["ends_at"] < after_quarters(9) - timedelta(hours=1) for a in open_)
    assert all(a["ends_at"] - a["opens_at"] == timedelta(hours=24) for a in open_)
    assert all(a["fair"] * 85 // 100 <= a["reserve"] <= a["fair"] * 95 // 100 for a in open_)
    # A record for every quarter, for every district and every property.
    assert db.execute("SELECT count(*) FROM district_results WHERE period = 8").fetchone()[0] == 25
    assert db.execute("SELECT count(*) FROM property_results WHERE period = 8").fetchone()[0] == 300


def test_a_property_company_that_still_owns_everything_earns_its_rent_inside_its_business(db):
    """No money moves for buildings the companies own: the economy runs as before Stage 8."""
    # (The gap stage: the Nigeria Property Trust bought some buildings from them; only it is paid rent.)
    assert db.execute("SELECT count(*) FROM ledger_entries e JOIN ledger_transactions t ON t.id = e.transaction_id JOIN ledger_accounts a"
                      " ON a.id = e.account_id WHERE t.kind = 'rent' AND e.amount > 0 AND a.kind <> 'fund'").fetchone()[0] == 0
    assert ledger.balance(db, ledger.account_id(db, prop.RENTS)) == 0
    sound(db)


# ---------------------------------------------------------------------------
# Part B: the Auction House
# ---------------------------------------------------------------------------

def test_a_player_buys_a_listed_unit_with_a_mortgage_and_owns_it_after_the_countdown(db):
    player, account = pro(db, "asset_manager", "buyer", level=10, cash_naira=200_000_000)
    a = _one(db, "SELECT a.* FROM auctions a WHERE a.status = 'open' AND a.property_id IS NOT NULL AND a.opens_at <= %s ORDER BY a.fair LIMIT 1", (NOW9,))
    company_before = ledger.balance(db, a["seller"])
    bank = a_bank(db)
    limit = a["fair"]
    room = prop.mortgage_limit(db, account, limit, LATER)
    share = min(room * BPS // limit, 8000) // 100 * 100
    assert share > 0
    # Below the seller's lowest price, one bidder alone does not buy it.
    low = auctions.place_bid(db, account, a["id"], a["reserve"] - 1, LATER, player_id=player, mortgage_bank=bank["id"], mortgage_bps=share)
    assert low["leading"] and low["price"] == a["start_price"]
    assert not auctions._reserve_met(db, auctions._auction(db, a["id"]))
    # A top price that reaches the lowest price meets it: "lowest price met" shows (never the price), and it sells at it.
    bid = auctions.place_bid(db, account, a["id"], limit, LATER, player_id=player, mortgage_bank=bank["id"], mortgage_bps=share)
    assert bid["leading"] and bid["price"] == a["start_price"] and auctions._reserve_met(db, auctions._auction(db, a["id"]))
    held = ledger.balance(db, ledger.account_id(db, prop.HELD))
    assert held == limit * (BPS - share) // BPS
    end(db, a)
    assert auctions._auction(db, a["id"])["status"] == "sold"
    assert prop.share_of(db, a["property_id"], account) == BPS
    assert ledger.balance(db, a["seller"]) == company_before + a["reserve"]
    assert ledger.balance(db, ledger.account_id(db, prop.HELD)) == 0
    sound(db)


def test_a_lone_bid_below_the_sellers_lowest_price_does_not_buy(db):
    player, account = pro(db, "asset_manager", "buyer", level=10, cash_naira=200_000_000)
    a = _one(db, "SELECT a.* FROM auctions a WHERE a.status = 'open' AND a.property_id IS NOT NULL AND a.opens_at <= %s ORDER BY a.fair LIMIT 1", (NOW9,))
    before = ledger.balance(db, account)
    auctions.place_bid(db, account, a["id"], a["reserve"] - 1, LATER, player_id=player)
    end(db, a)
    assert auctions._auction(db, a["id"])["status"] == "unsold"
    assert ledger.balance(db, account) == before
    assert ledger.balance(db, ledger.account_id(db, prop.HELD)) == 0
    sound(db)


def test_a_bid_at_or_above_the_reserve_buys_it_and_the_company_books_the_sale(db):
    player, account = pro(db, "asset_manager", "buyer", level=10, cash_naira=200_000_000)
    rival, rival_account = pro(db, "investment_banker", "rival", level=10, cash_naira=200_000_000)
    a = _one(db, "SELECT a.* FROM auctions a WHERE a.status = 'open' AND a.property_id IS NOT NULL AND a.opens_at <= %s ORDER BY a.fair LIMIT 1", (NOW9,))
    seller_before = ledger.balance(db, a["seller"])
    bank = a_bank(db)
    auctions.place_bid(db, rival_account, a["id"], a["reserve"], LATER, player_id=rival)
    room = prop.mortgage_limit(db, account, a["fair"], LATER)
    share = min(room * BPS // a["fair"], 8000) // 100 * 100
    mine = auctions.place_bid(db, account, a["id"], a["fair"], LATER, player_id=player, mortgage_bank=bank["id"], mortgage_bps=share)
    assert mine["leading"]
    price = auctions._auction(db, a["id"])["price"]
    step = max(a["reserve"] * data.AUCTION_STEP_BPS // BPS, 100)
    assert price == min(a["fair"], a["reserve"] + step)              # the second-highest limit and one step: no more
    # The beaten bidder's cash came back at once.
    assert _one(db, "SELECT * FROM auction_bids WHERE bidder = %s", (rival_account,))["held"] == 0
    end(db, a)
    sold = auctions._auction(db, a["id"])
    assert sold["status"] == "sold"
    assert prop.share_of(db, a["property_id"], account) == BPS
    m = prop.mortgage_on(db, a["property_id"])
    assert m["borrower"] == account and m["principal"] == price * share // BPS
    assert ledger.balance(db, a["seller"]) == seller_before + price
    sale = _one(db, "SELECT * FROM company_asset_sales WHERE property_id = %s", (a["property_id"],))
    assert sale["proceeds"] == price and sale["book"] >= 0
    assert ledger.balance(db, ledger.account_id(db, prop.HELD)) == 0
    # The buyer's net worth counts the property, less the mortgage on it.
    eq = prop.equity_of(db, account)
    assert eq["owed"] == m["outstanding"] and eq["equity"] == eq["value"] - eq["owed"]
    sound(db)


def test_a_late_bid_adds_five_minutes_and_a_leading_bid_cannot_be_withdrawn(db):
    p = a_unit(db, "Aba")
    a = lot(db, p["id"])
    one, one_account = pro(db, "asset_manager", "one", cash_naira=500_000_000)
    two, two_account = pro(db, "investment_banker", "two", cash_naira=500_000_000)
    first = auctions.place_bid(db, one_account, a["id"], a["start_price"] * 2, LATER, player_id=one)
    with pytest.raises(prop.PropertyError, match="cannot be withdrawn"):
        auctions.withdraw(db, one_account, first["bid_id"], LATER)
    late = a["ends_at"] - timedelta(minutes=2)
    second = auctions.place_bid(db, two_account, a["id"], a["start_price"] * 3, late, player_id=two)
    assert second["leading"]
    assert auctions._auction(db, a["id"])["ends_at"] == a["ends_at"] + timedelta(minutes=5)
    # Nobody can bid once it has ended; it is settled to the leader.
    with pytest.raises(prop.PropertyError):
        auctions.place_bid(db, one_account, a["id"], a["start_price"] * 4, a["ends_at"] + timedelta(minutes=6), player_id=one)
    end(db, a)
    assert prop.share_of(db, p["id"], two_account) == BPS
    sound(db)


def test_computer_bidders_join_a_forced_sale_and_an_outbid_player_gets_their_cash_back(db):
    p = a_unit(db, "Lagos")
    owner, owner_account = pro(db, "asset_manager", "owner", cash_naira=0)
    hand_over(db, p["id"], owner_account)
    with db.transaction():
        auction = auctions.force_sale(db, p["id"], "tax", 9, NOW9)
    computers = _dicts(db, "SELECT * FROM auction_bids WHERE auction_id = %s AND computer", (auction,))
    assert computers, "property companies bid at a forced sale"
    a = auctions._auction(db, auction)
    assert a["reserve"] == 0 and a["leader"] is not None
    bidder, bidder_account = pro(db, "investment_banker", "bargain", cash_naira=500_000_000)
    before = ledger.balance(db, bidder_account)
    low = auctions.minimum(a)
    done = auctions.place_bid(db, bidder_account, auction, low, LATER, player_id=bidder)
    if not done["leading"]:
        assert ledger.balance(db, bidder_account) == before          # beaten at once by a computer's higher limit: cash back
    end(db, a)
    assert auctions._auction(db, auction)["status"] == "sold"
    assert prop.share_of(db, p["id"], owner_account) == 0
    sound(db)


def test_partners_share_a_bid_and_then_the_property(db):
    p = a_unit(db, "Abuja")
    a = lot(db, p["id"])
    lead, lead_account = pro(db, "asset_manager", "lead", cash_naira=500_000_000)
    friend, friend_account = pro(db, "investment_banker", "friend", cash_naira=500_000_000)
    ask = auctions.ask_partner(db, lead_account, a["id"], friend_account, 4000, LATER)
    with pytest.raises(prop.PropertyError):
        auctions.place_bid(db, lead_account, a["id"], a["start_price"], LATER, player_id=lead, partner=ask)
    most = a["start_price"] * 3
    auctions.answer_partner(db, friend_account, ask, True, most, LATER)
    with pytest.raises(prop.PropertyError, match="only as far"):
        auctions.place_bid(db, lead_account, a["id"], most + 1, LATER, player_id=lead, partner=ask)
    auctions.place_bid(db, lead_account, a["id"], most, LATER, player_id=lead, partner=ask)
    end(db, a)
    assert prop.share_of(db, p["id"], lead_account) == 6000
    assert prop.share_of(db, p["id"], friend_account) == 4000
    assert ledger.balance(db, ledger.account_id(db, prop.HELD)) == 0
    sound(db)


def test_a_mortgage_is_limited_to_four_years_of_salary_and_needs_a_fifth_paid_down(db):
    player, account = pro(db, "asset_manager", "salaried", level=5, cash_naira=0)
    salary = careers.salary_per_quarter(careers.career(db, player)["level"], careers.world_now(db, NOW9)["wage_index_bps"])
    huge = naira(10_000_000_000)
    assert prop.mortgage_limit(db, account, huge, NOW9) == salary * 16
    assert prop.mortgage_limit(db, account, naira(1_000_000), NOW9) == naira(800_000)
    # Somebody who already owes on a mortgage can borrow only the rest.
    db.execute("INSERT INTO mortgages (property_id, borrower, bank_company_id, principal, outstanding, rate_bps, taken_period, term_quarters, at)"
               " VALUES (1, %s, %s, %s, %s, 1000, 8, 40, %s)", (account, a_bank(db)["id"], salary * 10, salary * 10, NOW9))
    assert prop.mortgage_limit(db, account, huge, NOW9) == salary * 6
    # No job, no mortgage.
    jobless, jobless_account = pro(db, "investment_banker", "idle", cash_naira=0)
    careers.leave_job(db, jobless, NOW9)
    assert prop.mortgage_limit(db, jobless_account, naira(1_000_000), NOW9) == 0


# ---------------------------------------------------------------------------
# Rent, tax, upkeep, wear, repossession, title, bubbles
# ---------------------------------------------------------------------------

def test_an_owner_is_paid_rent_and_pays_tax_and_upkeep_at_the_close(db):
    p = a_unit(db, "Lagos")
    owner, owner_account = pro(db, "asset_manager", "landlord", cash_naira=50_000_000)
    hand_over(db, p["id"], owner_account)
    before = ledger.balance(db, owner_account)
    quarters.close_due_quarters(db, after_quarters(9))
    rent = _one(db, "SELECT coalesce(sum(e.amount), 0)::bigint AS r FROM ledger_entries e JOIN ledger_transactions t ON t.id = e.transaction_id"
                    " WHERE e.account_id = %s AND t.kind = 'rent'", (owner_account,))["r"]
    tax = _one(db, "SELECT coalesce(-sum(e.amount), 0)::bigint AS r FROM ledger_entries e JOIN ledger_transactions t ON t.id = e.transaction_id"
                   " WHERE e.account_id = %s AND t.kind = 'property_tax'", (owner_account,))["r"]
    assert rent > 0 and tax > 0
    row = _one(db, "SELECT * FROM property_results WHERE property_id = %s AND period = 9", (p["id"],))
    assert row["rent_paid"] == rent and row["tax"] == tax and row["upkeep"] > 0
    assert ledger.balance(db, ledger.account_id(db, prop.RENTS)) == 0
    assert before != ledger.balance(db, owner_account)
    sound(db)


def test_without_upkeep_a_building_wears_five_times_faster_and_renovation_restores_it(db):
    p = a_unit(db, "Kano")
    owner, owner_account = pro(db, "asset_manager", "landlord", cash_naira=50_000_000)
    hand_over(db, p["id"], owner_account)
    prop.set_upkeep(db, owner_account, p["id"], False)
    quarters.close_due_quarters(db, after_quarters(9))
    after = _one(db, "SELECT condition FROM properties WHERE id = %s", (p["id"],))["condition"]
    assert after == p["condition"] - data.WEAR_WITHOUT_UPKEEP
    done = prop.renovate(db, owner_account, p["id"], after_quarters(9) + timedelta(hours=2))
    assert done["cost"] > 0
    assert _one(db, "SELECT condition FROM properties WHERE id = %s", (p["id"],))["condition"] == min(after + data.RENOVATION_POINTS, 100)
    sound(db)


def test_two_missed_mortgage_payments_and_the_bank_sells_the_property(db):
    p = a_unit(db, "Port Harcourt", standing=False)        # a plot: no rent comes in to meet the payments
    owner, owner_account = pro(db, "asset_manager", "borrower", level=10, cash_naira=0)
    hand_over(db, p["id"], owner_account)
    bank = a_bank(db)
    with db.transaction():
        prop.take_mortgage(db, owner_account, bank["id"], p["id"], worth(db, p["id"]) // 2, 8, NOW9)
    # The borrower spends the loan elsewhere and has nothing left to pay with.
    ledger.transfer(db, payer=owner_account, receiver=ledger.account_id(db, ledger.TREASURY), amount=ledger.balance(db, owner_account),
                    kind="test_cash", memo="Test: spent")
    careers.leave_job(db, owner, NOW9)                    # no pay arrives to meet the payments
    quarters.close_due_quarters(db, after_quarters(9))
    m = _one(db, "SELECT * FROM mortgages WHERE borrower = %s ORDER BY id DESC LIMIT 1", (owner_account,))
    assert m["missed"] == 1 and m["status"] == "open"
    assert _one(db, "SELECT * FROM auctions WHERE property_id = %s AND reason = 'repossession'", (p["id"],)) is None
    quarters.close_due_quarters(db, after_quarters(10))
    forced = _one(db, "SELECT * FROM auctions WHERE property_id = %s AND reason = 'repossession'", (p["id"],))
    assert forced is not None and forced["reserve"] == 0
    end(db, forced)
    m = _one(db, "SELECT * FROM mortgages WHERE id = %s", (m["id"],))
    assert m["status"] in ("repossessed", "shortfall")
    assert prop.share_of(db, p["id"], owner_account) == 0
    sound(db)


def test_a_flawed_title_costs_the_buyer_part_of_the_property_and_a_title_search_shows_it(db):
    flawed = _one(db, "SELECT * FROM properties WHERE title_flaw_bps > 0 AND status = 'standing' ORDER BY size_m2 LIMIT 1")
    buyer, buyer_account = pro(db, "investment_banker", "careful", cash_naira=10_000_000)
    found = prop.title_search(db, buyer_account, flawed["id"], NOW9)
    assert not found["clean"] and found["fee"] > 0
    hand_over(db, flawed["id"], buyer_account)
    quarters.close_due_quarters(db, after_quarters(9))
    assert prop.share_of(db, flawed["id"], buyer_account) == BPS * (BPS - flawed["title_flaw_bps"]) // BPS
    assert _one(db, "SELECT title_flaw_bps FROM properties WHERE id = %s", (flawed["id"],))["title_flaw_bps"] == 0
    assert db.execute("SELECT count(*) FROM news_stories WHERE kind = 'title_dispute'").fetchone()[0] >= 1 \
        if _one(db, "SELECT to_regclass('news_stories') IS NOT NULL AS ok")["ok"] else True
    sound(db)


def test_buyers_who_overpay_inflate_a_bubble_that_then_fades(db):
    p = a_unit(db, "Abuja")
    a = lot(db, p["id"])
    one, one_account = pro(db, "asset_manager", "keen", cash_naira=900_000_000)
    two, two_account = pro(db, "investment_banker", "keener", cash_naira=900_000_000)
    auctions.place_bid(db, one_account, a["id"], a["fair"] * 2, LATER, player_id=one)
    auctions.place_bid(db, two_account, a["id"], a["fair"] * 3, LATER, player_id=two)
    end(db, a)
    district = p["district_id"]
    before = prop.districts(db)[district]["premium_bps"]
    quarters.close_due_quarters(db, after_quarters(9))
    up = prop.districts(db)[district]["premium_bps"]
    assert up > before
    quarters.close_due_quarters(db, after_quarters(10))
    assert prop.districts(db)[district]["premium_bps"] < up
    sound(db)


def test_building_on_a_plot_makes_a_building_that_earns_rent(db):
    plot = a_unit(db, "Aba", standing=False)
    owner, owner_account = pro(db, "asset_manager", "builder", cash_naira=0)
    hand_over(db, plot["id"], owner_account)
    cost = prop.build_cost({**plot, "city": "Aba"})
    with pytest.raises(prop.PropertyError, match="costs"):
        prop.build(db, owner_account, plot["id"], NOW9)
    give_cash(db, owner_account, cost // 100 + 1)
    done = prop.build(db, owner_account, plot["id"], NOW9)
    built = _one(db, "SELECT * FROM properties WHERE id = %s", (plot["id"],))
    assert built["status"] == "standing" and built["kind"] == done["kind"] != "land" and built["base_rent"] > 0
    sound(db)


def test_a_world_made_before_stage_8_gets_its_property_at_its_next_close(db):
    db.execute("SET session_replication_role = replica")          # (test set-up: the permanent records' guard is set aside)
    for table in ("property_results", "district_results", "auction_events", "auction_bids", "auctions", "property_holdings",
                  "property_company_base", "properties", "districts"):
        db.execute(f"DELETE FROM {table}")
    db.execute("SET session_replication_role = DEFAULT")
    quarters.close_due_quarters(db, after_quarters(9))
    assert db.execute("SELECT count(*) FROM properties").fetchone()[0] == 300
    assert db.execute("SELECT count(*) FROM auctions WHERE status = 'open' AND property_id IS NOT NULL").fetchone()[0] == data.AUCTION_LISTINGS_A_QUARTER
    sound(db)


# ---------------------------------------------------------------------------
# An empire bids: the desks' checks
# ---------------------------------------------------------------------------

def test_an_empire_bids_only_after_every_desk_has_checked_the_lot_and_not_above_the_risk_managers_price(db):
    empire, team = firm_of(db)
    p = a_unit(db, "Lagos")
    a = lot(db, p["id"])
    with pytest.raises(prop.PropertyError, match="Still to do"):
        auctions.empire_bid(db, team["head"], a["id"], a["start_price"], LATER)
    with pytest.raises(prop.PropertyError, match="desk"):
        auctions.check(db, team["asset_manager"], a["id"], "title", {}, LATER)
    before = ledger.balance(db, empire["account_id"])
    title = auctions.check(db, team["investment_banker"], a["id"], "title", {}, LATER)
    assert title["clean"] and ledger.balance(db, empire["account_id"]) < before
    auctions.check(db, team["asset_manager"], a["id"], "valuation", {"value": a["fair"]}, LATER)
    auctions.check(db, team["risk_manager"], a["id"], "limit", {"limit": a["fair"]}, LATER)
    auctions.check(db, team["investment_banker"], a["id"], "money", {"mortgage_bps": 0}, LATER)
    with pytest.raises(prop.PropertyError, match="top price"):
        auctions.empire_bid(db, team["head"], a["id"], a["fair"] + 1, LATER)
    with pytest.raises(prop.PropertyError, match="head"):
        auctions.empire_bid(db, team["asset_manager"], a["id"], a["fair"], LATER)
    auctions.empire_bid(db, team["head"], a["id"], a["fair"], LATER)
    end(db, a)
    assert prop.share_of(db, p["id"], empire["account_id"]) == BPS
    assert empires.worth(db, empire, after_quarters(8) + timedelta(days=2))["property"] > 0
    sound(db)


# ---------------------------------------------------------------------------
# Part C: headquarters
# ---------------------------------------------------------------------------

def _hq_empire(db):
    empire, team = firm_of(db, n_cash=50_000_000_000)
    p = a_unit(db, "Lagos", kind=None)
    hand_over(db, p["id"], empire["account_id"])
    return empire, team, p


def test_the_cost_of_a_level_grows_so_each_level_is_dearer_and_level_120_is_far_off():
    lagos = [headquarters.level_cost(n, "Lagos") for n in (1, 2, 10, 20, 60, 120)]
    assert lagos == sorted(lagos) and len(set(lagos)) == len(lagos)
    assert headquarters.cost_to(0, 120, "Lagos") > 50 * headquarters.cost_to(0, 20, "Lagos")
    assert headquarters.level_cost(10, "Kano") < headquarters.level_cost(10, "Lagos")
    assert headquarters.extra_seats(9) == 0 and headquarters.extra_seats(10) == 1 and headquarters.extra_seats(120) == 12


def test_a_headquarters_adds_seats_as_it_rises_and_teaches_more(db):
    empire, team, p = _hq_empire(db)
    with pytest.raises(prop.PropertyError, match="head"):
        headquarters.establish(db, team["asset_manager"], p["id"], NOW9)
    headquarters.establish(db, team["head"], p["id"], NOW9)
    assert headquarters.bonus_bps(db, empire["id"]) == data.HQ_BONUS_PER_ROOT_BPS
    assert headquarters.recruit_points(db, empire["id"]) == data.LAGOS_RECRUIT_POINTS
    seats_before = db.execute("SELECT count(*) FROM empire_seats WHERE empire_id = %s", (empire["id"],)).fetchone()[0]
    done = headquarters.raise_level(db, team["head"], 19, NOW9)
    assert done["level"] == 20 and done["cost"] == headquarters.cost_to(1, 20, "Lagos")
    extra = _dicts(db, "SELECT * FROM empire_seats WHERE empire_id = %s AND slot >= 3 ORDER BY slot, build", (empire["id"],))
    assert len(extra) == 2 and db.execute("SELECT count(*) FROM empire_seats WHERE empire_id = %s", (empire["id"],)).fetchone()[0] == seats_before + 2
    assert {s["build"] for s in extra} == set(data.EMPIRE_BUILDS[:2])
    # The money went to the builders, and into the empire's books.
    assert _one(db, "SELECT * FROM empire_books WHERE empire_id = %s AND what LIKE 'Headquarters raised%%'", (empire["id"],)) is not None \
        if _one(db, "SELECT 1 AS ok FROM information_schema.columns WHERE table_name = 'empire_books' AND column_name = 'what'") else True
    sound(db)


def test_a_neglected_headquarters_is_warned_and_then_collapses_and_the_insurance_pays(db, monkeypatch):
    empire, team, p = _hq_empire(db)
    headquarters.establish(db, team["head"], p["id"], NOW9)
    headquarters.raise_level(db, team["head"], 9, NOW9)
    with pytest.raises(prop.PropertyError, match="Risk Manager"):
        headquarters.ask_upkeep(db, team["asset_manager"], NOW9)
    db.execute("UPDATE headquarters SET condition = 20 WHERE empire_id = %s", (empire["id"],))
    rep = {r["id"]: r["reputation"] for r in _dicts(db, "SELECT id, reputation FROM players WHERE id = ANY(%s)",
                                                    ([team["head"], team["risk_manager"], team["asset_manager"]],))}
    monkeypatch.setattr(headquarters, "_uniform", lambda *args: 0.0)
    quarters.close_due_quarters(db, after_quarters(9))
    hq = headquarters.of(db, empire["id"])
    assert hq["collapsed_period"] == 9 and hq["warnings"] >= 1
    assert not headquarters.standing(hq) and headquarters.bonus_bps(db, empire["id"]) == 0
    assert all(s["hq_frozen"] for s in _dicts(db, "SELECT * FROM empire_seats WHERE empire_id = %s AND slot >= 3", (empire["id"],)))
    after = {r["id"]: r["reputation"] for r in _dicts(db, "SELECT id, reputation FROM players WHERE id = ANY(%s)",
                                                      ([team["head"], team["risk_manager"], team["asset_manager"]],))}
    # Nobody asked for the upkeep: the Risk Manager, whose desk it is, is blamed. Other members are unharmed.
    assert after[team["risk_manager"]] < rep[team["risk_manager"]] or rep[team["risk_manager"]] == 0
    assert after[team["head"]] == rep[team["head"]] and after[team["asset_manager"]] == rep[team["asset_manager"]]
    # Rebuilding brings it back.
    headquarters.rebuild(db, team["head"], after_quarters(9) + timedelta(hours=2))
    assert headquarters.standing(headquarters.of(db, empire["id"]))
    sound(db)


def test_an_approved_upkeep_keeps_the_headquarters_standing(db):
    empire, team, p = _hq_empire(db)
    headquarters.establish(db, team["head"], p["id"], NOW9)
    headquarters.ask_upkeep(db, team["risk_manager"], NOW9)
    headquarters.approve_upkeep(db, team["head"], True, NOW9)
    quarters.close_due_quarters(db, after_quarters(9))
    hq = headquarters.of(db, empire["id"])
    assert hq["condition"] == 99 and hq["warnings"] == 0
    sound(db)


def test_a_headquarters_whose_building_is_sold_at_a_forced_sale_must_move(db):
    empire, team, p = _hq_empire(db)
    headquarters.establish(db, team["head"], p["id"], NOW9)
    headquarters.raise_level(db, team["head"], 10, NOW9)
    with db.transaction():
        auction = auctions.force_sale(db, p["id"], "tax", 9, NOW9)
    buyer, buyer_account = pro(db, "investment_banker", "buyer", cash_naira=900_000_000)
    auctions.place_bid(db, buyer_account, auction, auctions._auction(db, auction)["fair"] * 2, LATER, player_id=buyer)
    end(db, auction)
    hq = headquarters.of(db, empire["id"])
    assert hq["homeless"] and not headquarters.standing(hq)
    with pytest.raises(prop.PropertyError, match="no longer owns"):
        headquarters.rebuild(db, team["head"], LATER)
    other = a_unit(db, "Abuja")
    hand_over(db, other["id"], empire["account_id"])
    headquarters.establish(db, team["head"], other["id"], LATER)
    hq = headquarters.of(db, empire["id"])
    assert headquarters.standing(hq) and hq["level"] == 11 and hq["city"] == "Abuja"
    sound(db)


def test_insurance_for_the_headquarters_is_one_of_the_empires_covers():
    assert "headquarters" in firm_tasks.COVER


def test_a_property_company_that_buys_at_auction_books_it_as_capital_spending_and_the_close_balances(db):
    """Found by the ten-year run: a company's purchase at the Auction House during the quarter must count in its accounts."""
    p = a_unit(db, "Lagos")
    owner, owner_account = pro(db, "asset_manager", "seller", cash_naira=0)
    hand_over(db, p["id"], owner_account)
    with db.transaction():
        auction = auctions.force_sale(db, p["id"], "tax", 9, NOW9)
    a = auctions._auction(db, auction)
    assert a["leader"] is not None
    end(db, a)
    buyer = _one(db, "SELECT c.id, c.name FROM property_holdings h JOIN companies c ON c.account_id = h.account_id WHERE h.property_id = %s", (p["id"],))
    assert buyer is not None
    quarters.close_due_quarters(db, after_quarters(9))
    row = _one(db, "SELECT capital_spending, drivers FROM company_results WHERE company_id = %s AND period = 9", (buyer["id"],))
    assert row["capital_spending"] >= auctions._auction(db, auction)["price"]
    assert any("Auction House" in n for n in row["drivers"]["notes"])
    sound(db)
