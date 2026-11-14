"""The gap stage, Part 2: each finding of the independent review, fixed and tested."""

from __future__ import annotations

from datetime import timedelta

import pytest
from psycopg.rows import dict_row

from simulation import (
    auctions,
    conveyancing,
    development,
    ledger,
    propfunds,
    quarters,
    zoning,
)
from simulation import property as prop
from simulation import world_data as data
from simulation.money import BPS, naira
from tests.conftest import after_quarters
from tests.test_builds import pro
from tests.test_careers import NOW9, sound
from tests.test_gap_property import clean, name_of, stray
from tests.test_lending import bank_id
from tests.test_property import hand_over

pytestmark = pytest.mark.world("eight")
CONSENTED = NOW9 + timedelta(days=data.CONSENT_DAYS, minutes=5)


def _one(db, sql, params=()):
    with db.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(sql, params).fetchall()
    return rows[0] if rows else None


def mortgaged_buyer(db, name, cash_naira=200_000_000):
    """A buyer with a job and a salary, so a bank will lend."""
    from tests.test_careers import professional
    player, account = professional(db, name, cash_naira=cash_naira)
    return player, account


# 1. The seller's sale money never pays off the buyer's new mortgage.
def test_r1_a_buyers_new_mortgage_is_not_repaid_from_the_sellers_money(db):
    seller, s_acct = pro(db, "asset_manager", "cleanseller", cash_naira=1_000_000)
    buyer, b_acct = mortgaged_buyer(db, "borrowingbuyer")
    unit = clean(db, kind="home")
    hand_over(db, unit["id"], s_acct)
    price = naira(20_000_000)
    sale = conveyancing.offer(db, s_acct, unit["id"], {"player": name_of(db, buyer)}, price, NOW9)
    loan = min(prop.mortgage_limit(db, b_acct, price, NOW9), price // 2)
    assert loan > 0
    conveyancing.accept(db, b_acct, sale["sale_id"], NOW9, mortgage_bank=bank_id(db), mortgage=loan)
    conveyancing.ask_consent(db, b_acct, sale["sale_id"], NOW9)
    before = ledger.balance(db, s_acct)
    assert conveyancing.sign(db, b_acct, sale["sale_id"], CONSENTED)["status"] == "done"
    assert ledger.balance(db, s_acct) - before == price
    m = _one(db, "SELECT * FROM mortgages WHERE property_id = %s AND borrower = %s", (unit["id"], b_acct))
    assert m["status"] == "open" and m["outstanding"] == loan
    assert conveyancing.check_books(db) == []


# 2. A fund's manager never buys the fund's buildings, and they are never sold for nothing.
def test_r2_a_fund_manager_cannot_buy_the_funds_building(db):
    from simulation import careers
    later = NOW9 + timedelta(hours=1)
    manager, m_acct = pro(db, "asset_manager", "fundboss", level=22, cash_naira=500_000_000)
    db.execute("UPDATE careers SET rank = 1, experience = %s WHERE player_id = %s", (careers.experience_for(22), manager))
    opened = propfunds.open_fund(db, manager, "Fundboss Property", 100, later)
    fund = _one(db, "SELECT * FROM property_funds WHERE id = %s", (opened["fund_id"],))
    unit = clean(db, kind="shop")
    hand_over(db, unit["id"], fund["account_id"])
    with pytest.raises(propfunds.FundError, match="nine tenths"):
        propfunds.sell(db, manager, unit["id"], 0, later)
    worth = prop.value(_one(db, "SELECT * FROM properties WHERE id = %s", (unit["id"],)), prop.districts(db)[unit["district_id"]], prop.policy_rate(db))
    listed = propfunds.sell(db, manager, unit["id"], worth, later)
    a = _one(db, "SELECT * FROM auctions WHERE id = %s", (listed,))
    with pytest.raises(prop.PropertyError, match="manager never buys"):
        auctions.place_bid(db, m_acct, listed, a["start_price"] * 2, max(later, a["opens_at"] + timedelta(minutes=1)), player_id=manager)


# 3 and 4. The trust's purchases and old-loan payoffs leave nothing unexplained in the companies' accounts.
def test_r3_r4_trust_purchases_and_old_loans_are_explained_in_the_companies_accounts(db):
    player, account = pro(db, "asset_manager", "oldloanowner", cash_naira=5_000_000_000)
    p = _one(db, "SELECT p.* FROM properties p JOIN property_claims c ON c.property_id = p.id AND c.kind = 'old_loan' AND c.status = 'hidden'"
                 " WHERE p.status = 'standing' AND p.kind <> 'land' ORDER BY p.size_m2 LIMIT 1")
    hand_over(db, p["id"], account)
    quarters.close_due_quarters(db, after_quarters(10))
    assert _one(db, "SELECT count(*) AS n FROM company_asset_sales WHERE proceeds > 0 AND property_id IS NOT NULL")["n"] >= 1
    assert stray(db, 9) == 0
    sound(db)


# 5. One salary cannot back mortgages on two private purchases at once.
def test_r5_one_salary_cannot_back_two_private_mortgages(db):
    s1, a1 = pro(db, "asset_manager", "sellerone", cash_naira=1_000_000)
    s2, a2 = pro(db, "asset_manager", "sellertwo", cash_naira=1_000_000)
    buyer, b_acct = mortgaged_buyer(db, "greedybuyer", cash_naira=500_000_000)
    one, two = clean(db, kind="home"), clean(db, city="Abuja", kind="home")
    hand_over(db, one["id"], a1)
    hand_over(db, two["id"], a2)
    price = naira(400_000_000)
    most = prop.mortgage_limit(db, b_acct, price, NOW9)
    first = conveyancing.offer(db, a1, one["id"], {"player": name_of(db, buyer)}, price, NOW9)
    second = conveyancing.offer(db, a2, two["id"], {"player": name_of(db, buyer)}, price, NOW9)
    conveyancing.accept(db, b_acct, first["sale_id"], NOW9, mortgage_bank=bank_id(db), mortgage=most)
    with pytest.raises(prop.PropertyError, match="at most"):
        conveyancing.accept(db, b_acct, second["sale_id"], NOW9, mortgage_bank=bank_id(db), mortgage=most)


# 6. A claim the registry has found comes to bear whoever owns the property at the next close.
def test_r6_a_found_claim_cannot_be_dodged_by_a_quick_sale(db):
    searcher, s_acct = pro(db, "asset_manager", "searcher", cash_naira=5_000_000)
    p = _one(db, "SELECT p.* FROM properties p JOIN property_claims c ON c.property_id = p.id AND c.kind = 'right_of_way' AND c.status = 'hidden'"
                 " ORDER BY p.size_m2 LIMIT 1")
    conveyancing.claims_search(db, s_acct, p["id"], NOW9)
    assert _one(db, "SELECT status FROM property_claims WHERE property_id = %s AND kind = 'right_of_way'", (p["id"],))["status"] == "found"
    quarters.close_due_quarters(db, after_quarters(9))                      # (still owned by a property company)
    assert _one(db, "SELECT value_cut_bps FROM properties WHERE id = %s", (p["id"],))["value_cut_bps"] == data.CLAIM_RIGHT_OF_WAY_CUT_BPS


# 7. A hotel or a mall costs more to build than an office of the same size.
def test_r7_hotels_and_malls_cost_more_to_build(db):
    plot = clean(db, district_kind="business", standing=False)
    p = {**plot, "city": plot["city"]}
    assert prop.build_cost(p, "mall") == prop.build_cost(p, "office") * data.BUILD_KIND_BPS["mall"] // BPS
    assert development.budget_for(p, "hotel") > development.budget_for(p, "office")


# 8. Farmland cannot be rezoned on request, and a rezoning granted pays a betterment levy.
def test_r8_no_farmland_rezoning_on_request_and_a_levy_on_the_gain(db):
    player, account = pro(db, "asset_manager", "speculator", cash_naira=50_000_000_000)
    farm = clean(db, city="Port Harcourt", district_kind="farmland", standing=False)
    hand_over(db, farm["id"], account)
    with pytest.raises(prop.PropertyError, match="planners alone"):
        zoning.ask(db, account, farm["id"], "residential", NOW9)
    plot = clean(db, district_kind="industry", standing=False)
    hand_over(db, plot["id"], account)
    zoning.ask(db, account, plot["id"], "residential", NOW9)
    db.execute("UPDATE districts SET occupancy_bps = 9800 WHERE city = 'Lagos' AND kind = 'homes'")
    treasury = ledger.account_id(db, ledger.TREASURY)
    before = ledger.balance(db, treasury)
    zoning.close(db, 9, NOW9)
    assert ledger.balance(db, treasury) > before
    assert "betterment levy" in _one(db, "SELECT words FROM rezonings WHERE property_id = %s", (plot["id"],))["words"]


# 10. No private sale of a plot being developed, and a dispute stops the building.
def test_r10_no_sale_during_development_and_a_dispute_stops_the_work(db):
    owner, account = pro(db, "asset_manager", "devowner", cash_naira=60_000_000_000)
    buyer, _ = pro(db, "asset_manager", "devbuyer", cash_naira=1_000_000)
    plot = clean(db, district_kind="homes", standing=False)
    hand_over(db, plot["id"], account)
    started = development.start(db, account, plot["id"], "home", NOW9)
    with pytest.raises(prop.PropertyError, match="developed"):
        conveyancing.offer(db, account, plot["id"], {"player": name_of(db, buyer)}, naira(1_000_000), NOW9)
    db.execute("UPDATE developments SET status = 'building', permit_delayed = false WHERE id = %s", (started["development_id"],))
    db.execute("UPDATE properties SET frozen = true WHERE id = %s", (plot["id"],))
    quarters.close_due_quarters(db, after_quarters(9))
    dev = _one(db, "SELECT * FROM developments WHERE id = %s", (started["development_id"],))
    assert dev["phase"] == 0 and "dispute" in str(dev["log"])


# 11. The seller does not see which checks the buyer ran.
def test_r11_the_seller_does_not_see_the_buyers_checks(db):
    seller, s_acct = pro(db, "asset_manager", "curious", cash_naira=1_000_000)
    buyer, b_acct = pro(db, "asset_manager", "discreet", cash_naira=1_000_000_000)
    unit = clean(db, kind="office")
    hand_over(db, unit["id"], s_acct)
    sale = conveyancing.offer(db, s_acct, unit["id"], {"player": name_of(db, buyer)}, naira(10_000_000), NOW9)
    conveyancing.check(db, b_acct, sale["sale_id"], "title", NOW9)
    seen = conveyancing.view(db, s_acct, NOW9)[0]
    assert not {st["step"] for st in seen["steps"]} & set(data.SALE_CHECK_STEPS)
