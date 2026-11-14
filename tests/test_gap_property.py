"""The gap stage, Part 2: zoning, infrastructure, the twelve-step purchase and the Land Registry, claims, development,
hotels and malls, households' home loans (a rate rise brings defaults and falling prices), valuation and property funds."""

from __future__ import annotations

from datetime import timedelta

import pytest
from psycopg.rows import dict_row

from simulation import (
    careers,
    conveyancing,
    development,
    homes,
    ledger,
    propfunds,
    propvalue,
    quarters,
    zoning,
)
from simulation import property as prop
from simulation import world_data as data
from simulation.money import BPS, naira
from tests.conftest import after_quarters
from tests.test_builds import pro
from tests.test_careers import NOW9, sound
from tests.test_lending import bank_id
from tests.test_property import hand_over

pytestmark = pytest.mark.world("eight")
LATER = NOW9 + timedelta(hours=1)


def _rows(db, sql, params=()):
    with db.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def _one(db, sql, params=()):
    rows = _rows(db, sql, params)
    return rows[0] if rows else None


def clean(db, *, city="Lagos", kind=None, district_kind=None, standing=True):
    """A property with no flaw and no claim of any kind, not up for auction."""
    return _one(db, """
        SELECT p.*, d.city, d.kind AS district_kind FROM properties p JOIN districts d ON d.id = p.district_id
        WHERE d.city = %s AND (%s::text IS NULL OR p.kind = %s) AND (%s::text IS NULL OR d.kind = %s)
          AND p.title_flaw_bps = 0 AND NOT EXISTS (SELECT 1 FROM property_claims c WHERE c.property_id = p.id)
          AND ((%s AND p.status = 'standing' AND p.kind <> 'land') OR (NOT %s AND p.kind = 'land'))
          AND NOT EXISTS (SELECT 1 FROM auctions a WHERE a.property_id = p.id AND a.status = 'open')
        ORDER BY p.size_m2, p.id LIMIT 1""", (city, kind, kind, district_kind, district_kind, standing, standing))


def name_of(db, player):
    return _one(db, "SELECT display_name FROM players WHERE id = %s", (player,))["display_name"]


def stray(db, since=9):
    return _one(db, "SELECT count(*) AS n FROM company_results WHERE period >= %s AND drivers::text LIKE '%%outside its normal business%%'",
                (since,))["n"]


def test_every_plot_has_a_zone_and_what_is_built_must_fit_it(db):
    zones = {r["zone"] for r in _rows(db, "SELECT DISTINCT zone FROM properties")}
    assert {"residential", "commercial", "industrial", "agricultural", "resource", "mixed"} <= zones
    assert _one(db, "SELECT count(*) AS n FROM properties WHERE kind = 'hotel'")["n"] == 5
    assert _one(db, "SELECT count(*) AS n FROM properties WHERE kind = 'mall'")["n"] == 5
    player, account = pro(db, "asset_manager", "builder", cash_naira=50_000_000_000)
    plot = clean(db, district_kind="homes", standing=False)
    hand_over(db, plot["id"], account)
    with pytest.raises(prop.PropertyError, match="zoned residential"):
        prop.build(db, account, plot["id"], NOW9, kind="office")
    done = prop.build(db, account, plot["id"], NOW9)
    assert done["kind"] == "home"
    shops = clean(db, district_kind="business", standing=False)
    hand_over(db, shops["id"], account)
    assert prop.build(db, account, shops["id"], NOW9, kind="hotel")["kind"] == "hotel"


def test_a_rezoning_is_decided_by_rule_at_the_close_and_is_in_the_news(db):
    player, account = pro(db, "asset_manager", "rezoner", cash_naira=50_000_000_000)
    plot = clean(db, district_kind="industry", standing=False)
    hand_over(db, plot["id"], account)
    with pytest.raises(prop.PropertyError, match="already"):
        zoning.ask(db, account, plot["id"], "industrial", NOW9)
    asked = zoning.ask(db, account, plot["id"], "residential", NOW9)
    assert asked["fee"] == naira(data.REZONE_FEE_NAIRA)
    # Lagos needs homes: its homes district is full.
    db.execute("UPDATE districts SET occupancy_bps = 9800 WHERE city = 'Lagos' AND kind = 'homes'")
    land_before = plot["land_value"]
    zoning.close(db, 9, NOW9)
    after = _one(db, "SELECT zone, land_value FROM properties WHERE id = %s", (plot["id"],))
    assert after["zone"] == "residential" and after["land_value"] > land_before
    assert _one(db, "SELECT status FROM rezonings WHERE id = %s", (asked["rezoning_id"],))["status"] == "granted"
    assert _one(db, "SELECT 1 FROM news_items WHERE kind = 'rezoning'")
    # Refused when the city has room.
    other = clean(db, city="Kano", district_kind="industry", standing=False)
    hand_over(db, other["id"], account)
    db.execute("UPDATE districts SET occupancy_bps = 7000 WHERE city = 'Kano'")
    second = zoning.ask(db, account, other["id"], "commercial", NOW9)
    zoning.close(db, 9, NOW9)
    assert _one(db, "SELECT status FROM rezonings WHERE id = %s", (second["rezoning_id"],))["status"] == "refused"


def test_infrastructure_is_announced_paid_for_and_lifts_the_land_beside_it(db):
    quarters.close_due_quarters(db, after_quarters(9))           # quarter 9 closes: about once a game year, a project
    assert _one(db, "SELECT count(*) AS n FROM infrastructure_projects WHERE announced_period IN (1, 5)")["n"] == 2   # the world's first two years
    project = _one(db, "SELECT * FROM infrastructure_projects WHERE announced_period = 9")
    assert project is not None
    d = _one(db, "SELECT * FROM districts WHERE id = %s", (project["district_id"],))
    others = sum(r["uplift_bps"] for r in _rows(db, "SELECT * FROM infrastructure_projects WHERE district_id = %s AND id <> %s",
                                                 (project["district_id"], project["id"])))
    assert d["infra_bps"] == project["uplift_bps"] // 4 + others
    beside = _one(db, "SELECT * FROM properties WHERE beside_project = %s LIMIT 1", (project["id"],))
    ds = prop.districts(db)
    rate = prop.policy_rate(db)
    if beside:
        plain = prop.value({**beside, "beside_project": None}, ds[beside["district_id"]], rate)
        assert prop.value(beside, ds[beside["district_id"]], rate) > plain
    quarters.close_due_quarters(db, after_quarters(10))
    project = _one(db, "SELECT * FROM infrastructure_projects WHERE id = %s", (project["id"],))
    assert project["spent"] > 0
    assert _one(db, "SELECT infra_bps FROM districts WHERE id = %s", (project["district_id"],))["infra_bps"] > d["infra_bps"]
    assert stray(db, 10) == 0
    sound(db)


def test_the_twelve_step_purchase_ends_registered_with_the_seller_paid_and_the_fees_to_the_government(db):
    seller, s_acct = pro(db, "asset_manager", "vendor", cash_naira=1_000_000)
    buyer, b_acct = pro(db, "asset_manager", "purchaser", cash_naira=20_000_000_000)
    unit = clean(db, kind="office")
    hand_over(db, unit["id"], s_acct)
    price = propvalue.three_ways(db, unit["id"])["income"] or naira(100_000_000)
    with pytest.raises(prop.PropertyError, match="not the seller"):
        conveyancing.offer(db, s_acct, unit["id"], {"player": name_of(db, seller)}, price, NOW9)
    sale = conveyancing.offer(db, s_acct, unit["id"], {"player": name_of(db, buyer)}, price, NOW9)
    for step in data.SALE_CHECK_STEPS:
        found = conveyancing.check(db, b_acct, sale["sale_id"], step, NOW9)
        assert found["words"]
    with pytest.raises(prop.PropertyError, match="terms first"):
        conveyancing.ask_consent(db, b_acct, sale["sale_id"], NOW9)
    conveyancing.accept(db, b_acct, sale["sale_id"], NOW9)
    asked = conveyancing.ask_consent(db, b_acct, sale["sale_id"], NOW9)
    with pytest.raises(prop.PropertyError, match="not come yet"):
        conveyancing.sign(db, b_acct, sale["sale_id"], NOW9 + timedelta(hours=3))
    seller_before = ledger.balance(db, s_acct)
    done = conveyancing.sign(db, b_acct, sale["sale_id"], NOW9 + timedelta(days=data.CONSENT_DAYS, minutes=1))
    assert done["status"] == "done" and done["fee"] == price * data.REGISTRATION_FEE_BPS // BPS
    assert ledger.balance(db, s_acct) == seller_before + price
    assert prop.share_of(db, unit["id"], b_acct) == BPS and prop.share_of(db, unit["id"], s_acct) == 0
    assert _one(db, "SELECT how FROM land_register WHERE property_id = %s ORDER BY id DESC LIMIT 1", (unit["id"],))["how"] == "private"
    steps = _one(db, "SELECT steps FROM property_sales WHERE id = %s", (sale["sale_id"],))["steps"]
    assert set(steps) == set(data.SALE_STEPS)
    assert asked["fee"] == price * data.CONSENT_FEE_BPS // BPS
    assert conveyancing.check_books(db) == []
    sound(db)


def test_a_claim_skipped_at_purchase_comes_to_light_and_an_old_loan_must_be_paid(db):
    player, account = pro(db, "asset_manager", "careless", cash_naira=5_000_000_000)
    p = _one(db, "SELECT p.* FROM properties p JOIN property_claims c ON c.property_id = p.id AND c.kind = 'old_loan'"
                 " WHERE p.status = 'standing' AND p.kind <> 'land' ORDER BY p.size_m2 LIMIT 1")
    found = conveyancing.claims_search(db, account, p["id"], NOW9)
    assert not found["clean"] and "old loan" in found["words"]
    hand_over(db, p["id"], account)                              # bought without asking for the search's answer to matter
    claim = _one(db, "SELECT * FROM property_claims WHERE property_id = %s AND kind = 'old_loan'", (p["id"],))
    bank = _one(db, "SELECT account_id FROM companies WHERE id = %s", (claim["lender"],))["account_id"]
    before = ledger.balance(db, bank)
    quarters.close_due_quarters(db, after_quarters(9))
    assert _one(db, "SELECT status FROM property_claims WHERE id = %s", (claim["id"],))["status"] == "settled"
    assert ledger.balance(db, bank) != before
    paid = _one(db, "SELECT coalesce(sum(e.amount), 0)::bigint AS n FROM ledger_entries e JOIN ledger_transactions t ON t.id = e.transaction_id"
                    " WHERE e.account_id = %s AND t.memo LIKE 'An old loan%%' AND e.asset = 'NGN'", (bank,))["n"]
    assert paid == claim["amount"]
    sound(db)


def test_a_dispute_freezes_a_property_until_it_is_settled(db):
    player, account = pro(db, "asset_manager", "disputant", cash_naira=5_000_000_000)
    p = _one(db, "SELECT p.* FROM properties p JOIN property_claims c ON c.property_id = p.id AND c.kind = 'dispute'"
                 " WHERE p.status = 'standing' AND p.kind <> 'land' ORDER BY p.size_m2 LIMIT 1")
    hand_over(db, p["id"], account)
    quarters.close_due_quarters(db, after_quarters(9))
    frozen = _one(db, "SELECT * FROM properties WHERE id = %s", (p["id"],))
    assert frozen["frozen"]
    assert prop.rent_due(frozen, prop.districts(db)[frozen["district_id"]]) == 0
    from simulation import auctions, leaseback
    later = after_quarters(9) + timedelta(hours=13)
    with pytest.raises(prop.PropertyError, match="dispute"):
        auctions.owner_list(db, account, p["id"], 0, later)
    with pytest.raises(prop.PropertyError, match="dispute"):
        leaseback.sell_and_lease_back(db, player, p["id"], 8, later)
    settled = conveyancing.settle_dispute(db, account, p["id"], later)
    assert settled["paid"] > 0 and not _one(db, "SELECT frozen FROM properties WHERE id = %s", (p["id"],))["frozen"]
    sound(db)


def test_a_development_buys_cement_steel_and_work_phase_by_phase_on_a_construction_loan(db):
    player, account = pro(db, "asset_manager", "developer", cash_naira=60_000_000_000)
    plot = clean(db, district_kind="homes", standing=False)
    hand_over(db, plot["id"], account)
    budget = development.budget_for({**plot, "city": plot["city"]}, "home")
    loan = budget * 6 // 10
    with pytest.raises(prop.PropertyError, match="zoned residential"):
        development.start(db, account, plot["id"], "factory", NOW9)
    started = development.start(db, account, plot["id"], "home", NOW9, loan_bank=bank_id(db), loan=loan)
    assert started["budget"] == budget
    cement = _rows(db, "SELECT account_id FROM companies WHERE sector = 'cement' AND status = 'trading'")
    before = sum(ledger.balance(db, c["account_id"]) for c in cement)
    db.execute("UPDATE developments SET permit_delayed = false WHERE id = %s", (started["development_id"],))
    db.execute("UPDATE world_state SET fortune_seed = fortune_seed")            # (no change: strikes come from the seed)
    for q in range(9, 16):
        quarters.close_due_quarters(db, after_quarters(q))
        if _one(db, "SELECT status FROM developments WHERE id = %s", (started["development_id"],))["status"] == "done":
            break
    dev = _one(db, "SELECT * FROM developments WHERE id = %s", (started["development_id"],))
    assert dev["status"] == "done" and dev["phase"] == data.DEVELOPMENT_PHASES and dev["loan_drawn"] > 0
    built = _one(db, "SELECT * FROM properties WHERE id = %s", (plot["id"],))
    assert built["status"] == "standing" and built["kind"] == "home"
    m = _one(db, "SELECT * FROM mortgages WHERE property_id = %s AND borrower = %s", (plot["id"], account))
    assert m and m["principal"] == dev["loan_drawn"]
    assert sum(ledger.balance(db, c["account_id"]) for c in cement) != before
    assert stray(db) == 0 and development.check_books(db) == []
    sound(db)


def test_hotels_follow_travel_and_malls_follow_shopping(db):
    hotel = _one(db, "SELECT * FROM properties WHERE kind = 'hotel' LIMIT 1")
    db.execute("UPDATE property_kind_index SET bps = 10000 WHERE kind = 'hotel'")
    base = prop.rent_due(hotel, prop.districts(db)[hotel["district_id"]])
    db.execute("UPDATE property_kind_index SET bps = 12000 WHERE kind = 'hotel'")
    assert abs(prop.rent_due(hotel, prop.districts(db)[hotel["district_id"]]) - base * 12000 // BPS) <= 1
    quarters.close_due_quarters(db, after_quarters(9))
    kinds = {r["kind"]: r["bps"] for r in _rows(db, "SELECT * FROM property_kind_index")}
    assert set(kinds) == {"hotel", "mall"} and all(5000 <= v <= 20_000 for v in kinds.values())


def test_the_designs_test_a_rate_rise_brings_home_defaults_and_falling_prices(db):
    from simulation import economy
    quarters.close_due_quarters(db, after_quarters(10))
    world = economy.load_world(db)
    db.execute("DELETE FROM home_loan_results WHERE period = 10")      # (the quarter is run again below, two ways)
    homes_d = _rows(db, "SELECT * FROM districts WHERE kind = 'homes' ORDER BY id")
    calm = homes.default_bps(1300, 1300, 0, 2000)
    shock = homes.default_bps(2300, 1300, -200, 4000)
    assert shock > calm * 5
    assert homes.demand_bps(2300, 0) < homes.demand_bps(1300, 0) < homes.demand_bps(900, 0)
    # The same quarter run twice from the same place: once at the usual rate, once after a ten-point rise.
    with db.transaction(force_rollback=True):
        homes.close(db, world, 10, after_quarters(10), rate_bps=1300, year_ago_bps=1300)
        calm_row = {r["location"]: r for r in _rows(db, "SELECT * FROM home_loan_results WHERE period = 10")}
        calm_prices = {d["id"]: d["premium_bps"] for d in _rows(db, "SELECT * FROM districts WHERE kind = 'homes'")}
    homes.close(db, world, 10, after_quarters(10), rate_bps=2300, year_ago_bps=1300)          # ten points up on a year ago
    hard_row = {r["location"]: r for r in _rows(db, "SELECT * FROM home_loan_results WHERE period = 10")}
    hard_prices = {d["id"]: d["premium_bps"] for d in _rows(db, "SELECT * FROM districts WHERE kind = 'homes'")}
    assert sum(r["defaulted"] for r in hard_row.values()) > sum(r["defaulted"] for r in calm_row.values())
    assert sum(r["lent"] for r in hard_row.values()) < sum(r["lent"] for r in calm_row.values())
    assert sum(hard_prices.values()) < sum(calm_prices.values())
    assert _one(db, "SELECT coalesce(sum(amount), 0)::bigint AS n FROM bank_home_losses WHERE period = 10")["n"] > 0
    _ = homes_d
    # The banks' next accounts carry the losses, with nothing unexplained.
    quarters.close_due_quarters(db, after_quarters(11))
    assert _one(db, "SELECT count(*) AS n FROM bank_home_losses WHERE counted_in IS NULL AND period <= 10")["n"] == 0
    assert stray(db, 10) == 0
    sound(db)


def test_a_property_is_valued_three_ways_from_public_figures(db):
    office = clean(db, kind="office")
    v = propvalue.three_ways(db, office["id"])
    assert v["comparables"] > 0 and v["income"] > 0 and v["cost"] > 0 and v["yearly_rent"] > 0
    plot = clean(db, standing=False)
    w = propvalue.three_ways(db, plot["id"])
    assert w["income"] == 0 and w["cost"] == w["land"] > 0


def test_property_funds_the_trust_and_a_managers_own_fund_under_its_rules(db):
    quarters.close_due_quarters(db, after_quarters(9))
    trust = _one(db, "SELECT * FROM property_funds WHERE manager IS NULL")
    assert trust and _one(db, "SELECT count(*) AS n FROM property_holdings WHERE account_id = %s", (trust["account_id"],))["n"] >= 1
    later = after_quarters(9) + timedelta(hours=13)
    investor, i_acct = pro(db, "accountant", "unitholder", cash_naira=100_000_000)
    bought = propfunds.buy_units(db, i_acct, trust["id"], naira(10_000_000), later)
    assert bought["units"] > 0 and bought["cost"] <= naira(10_000_000)
    sold = propfunds.sell_units(db, i_acct, trust["id"], bought["units"], later)
    assert sold["value"] < bought["cost"]                         # the 1% either side stays in the fund
    with pytest.raises(propfunds.FundError, match="hold that many"):
        propfunds.sell_units(db, i_acct, trust["id"], 1, later)
    young, _ = pro(db, "asset_manager", "keen", level=10)
    with pytest.raises(propfunds.FundError, match="Level 20"):
        propfunds.open_fund(db, young, "Keen Property", 100, later)
    manager, m_acct = pro(db, "asset_manager", "landlady", level=22, cash_naira=100_000_000)
    db.execute("UPDATE careers SET rank = 1, experience = %s WHERE player_id = %s", (careers.experience_for(22), manager))
    opened = propfunds.open_fund(db, manager, "Landlady Property", 150, later)
    with pytest.raises(propfunds.FundError, match="before"):
        propfunds.open_fund(db, manager, "Second Property", 150, later)
    fund = _one(db, "SELECT * FROM property_funds WHERE id = %s", (opened["fund_id"],))
    propfunds.buy_units(db, i_acct, fund["id"], naira(50_000_000), later)
    a = _one(db, "SELECT * FROM auctions WHERE status = 'open' AND property_id IS NOT NULL AND opens_at <= %s AND ends_at > %s ORDER BY fair LIMIT 1", (later, later))
    if a:
        with pytest.raises(propfunds.FundError, match="tenth above|more than|in cash"):
            propfunds.bid(db, manager, a["id"], a["fair"] * 2, later)
    assert propfunds.check_books(db) == []
    sound(db)
