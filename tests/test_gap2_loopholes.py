"""The gap stage, Part 2: ten ways a player might try to get round the new property rules, each shown to be closed."""

from __future__ import annotations

from datetime import timedelta

import pytest
from psycopg.rows import dict_row

from simulation import auctions, conveyancing, development, ledger, propfunds, quarters, zoning
from simulation import property as prop
from simulation import world_data as data
from simulation.money import BPS, naira
from tests.conftest import ADULT, after_quarters, join
from tests.test_builds import pro
from tests.test_careers import NOW9, sound
from tests.test_firm import firm_of
from tests.test_gap_property import clean, name_of
from tests.test_lending import bank_id
from tests.test_property import hand_over

pytestmark = pytest.mark.world("eight")
LATER = NOW9 + timedelta(hours=1)
CONSENTED = NOW9 + timedelta(days=data.CONSENT_DAYS, minutes=5)


def _one(db, sql, params=()):
    with db.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(sql, params).fetchall()
    return rows[0] if rows else None


def claimed(db, kind):
    return _one(db, "SELECT p.* FROM properties p JOIN property_claims c ON c.property_id = p.id AND c.kind = %s"
                    " WHERE p.status = 'standing' AND p.kind <> 'land' ORDER BY p.size_m2 LIMIT 1", (kind,))


# 1. Can a member move money in or out of their empire through a private sale at a made-up price?
def test_l1_no_private_sale_between_an_empire_and_its_own_members(db):
    empire, team = firm_of(db, n_cash=5_000_000_000)
    head_acct = ledger.player_account_id(db, team["head"])
    unit = clean(db, kind="office")
    hand_over(db, unit["id"], head_acct)
    with pytest.raises(prop.PropertyError, match="own empire"):
        conveyancing.offer(db, head_acct, unit["id"], {"empire": empire["name"]}, naira(1), NOW9)
    other = clean(db, kind="shop")
    hand_over(db, other["id"], empire["account_id"])
    with pytest.raises(prop.PropertyError, match="own empire"):
        conveyancing.offer(db, empire["account_id"], other["id"], {"player": name_of(db, team["accountant"])}, naira(10**9), NOW9)


# 2. Can the seller, or anybody else, see what the buyer's checks found?
def test_l2_the_buyers_checks_are_the_buyers_alone(db):
    seller, s_acct = pro(db, "asset_manager", "keeper", cash_naira=1_000_000)
    buyer, b_acct = pro(db, "asset_manager", "checker", cash_naira=1_000_000_000)
    p = claimed(db, "right_of_way")
    hand_over(db, p["id"], s_acct)
    sale = conveyancing.offer(db, s_acct, p["id"], {"player": name_of(db, buyer)}, naira(10_000_000), NOW9)
    found = conveyancing.check(db, b_acct, sale["sale_id"], "claims", NOW9)
    assert "right of way" in found["words"]
    seen = conveyancing.view(db, s_acct, NOW9)[0]
    assert seen["role"] == "seller" and all(step["words"] is None for step in seen["steps"])
    assert "right of way" in " ".join(str(st["words"]) for st in conveyancing.view(db, b_acct, NOW9)[0]["steps"])
    with pytest.raises(prop.PropertyError, match="no such sale"):
        conveyancing.check(db, s_acct, sale["sale_id"], "claims", NOW9)


# 3. Do the public pages give away a hidden claim, a title flaw, or a property company's book value?
def test_l3_no_hidden_claim_or_flaw_leaves_the_server(db, client):
    assert join(client, ADULT).status_code == 201
    text = client.get("/api/property").text
    for secret in ("old_loan", "title_flaw", "book_value", "dispute", "lender"):
        assert secret not in text, secret
    p = claimed(db, "old_loan")
    v = client.get(f"/api/property/{p['id']}/valuation")
    assert v.status_code == 200 and "loan" not in v.text and "claim" not in v.text
    assert client.get("/api/property/999999999/valuation").status_code == 404


# 4. Can the buyer sign before the Governor's consent comes, or the seller sell the same property twice?
def test_l4_no_signing_early_and_no_selling_twice(db):
    seller, s_acct = pro(db, "asset_manager", "doubler", cash_naira=1_000_000)
    one, one_acct = pro(db, "asset_manager", "firstbuyer", cash_naira=2_000_000_000)
    two, _ = pro(db, "asset_manager", "secondbuyer", cash_naira=2_000_000_000)
    unit = clean(db, kind="office")
    hand_over(db, unit["id"], s_acct)
    sale = conveyancing.offer(db, s_acct, unit["id"], {"player": name_of(db, one)}, naira(50_000_000), NOW9)
    with pytest.raises(prop.PropertyError, match="under way"):
        conveyancing.offer(db, s_acct, unit["id"], {"player": name_of(db, two)}, naira(60_000_000), NOW9)
    with pytest.raises(prop.PropertyError, match="private sale"):
        auctions.owner_list(db, s_acct, unit["id"], 0, LATER)
    conveyancing.accept(db, one_acct, sale["sale_id"], NOW9)
    conveyancing.ask_consent(db, one_acct, sale["sale_id"], NOW9)
    with pytest.raises(prop.PropertyError, match="not come yet"):
        conveyancing.sign(db, one_acct, sale["sale_id"], NOW9 + timedelta(hours=20))
    conveyancing.sign(db, one_acct, sale["sale_id"], CONSENTED)
    with pytest.raises(prop.PropertyError, match="consent first"):
        conveyancing.sign(db, one_acct, sale["sale_id"], CONSENTED)
    assert conveyancing.check_books(db) == []


# 5. If the seller no longer owns it all at the signing, does the buyer's money come back?
def test_l5_a_sale_that_fails_at_the_signing_leaves_nothing_held(db):
    seller, s_acct = pro(db, "asset_manager", "slippery", cash_naira=1_000_000)
    buyer, b_acct = pro(db, "asset_manager", "careful", cash_naira=2_000_000_000)
    unit = clean(db, kind="office")
    hand_over(db, unit["id"], s_acct)
    sale = conveyancing.offer(db, s_acct, unit["id"], {"player": name_of(db, buyer)}, naira(50_000_000), NOW9)
    conveyancing.accept(db, b_acct, sale["sale_id"], NOW9)
    conveyancing.ask_consent(db, b_acct, sale["sale_id"], NOW9)
    before = ledger.balance(db, b_acct)
    hand_over(db, unit["id"], s_acct, share=5000)                      # (half of it was not the seller's after all)
    done = conveyancing.sign(db, b_acct, sale["sale_id"], CONSENTED)
    assert done["status"] == "failed" and ledger.balance(db, b_acct) == before
    assert conveyancing.check_books(db) == []


# 6. Can a non-owner rezone, or a building be rezoned to a use it does not fit?
def test_l6_rezoning_is_for_owners_and_must_fit_what_stands(db):
    player, acct = pro(db, "asset_manager", "planner", cash_naira=50_000_000)
    other = clean(db, kind="home")
    with pytest.raises(prop.PropertyError, match="owner"):
        zoning.ask(db, acct, other["id"], "commercial", NOW9)
    hand_over(db, other["id"], acct)
    with pytest.raises(prop.PropertyError, match="would not fit"):
        zoning.ask(db, acct, other["id"], "industrial", NOW9)
    zoning.ask(db, acct, other["id"], "mixed", NOW9)                    # homes fit mixed use
    with pytest.raises(prop.PropertyError, match="already with"):
        zoning.ask(db, acct, other["id"], "mixed", NOW9)


# 7. Can a plot be developed twice, borrowed against beyond 70%, or sold from under its development?
def test_l7_a_development_is_one_at_a_time_within_its_loan(db):
    player, acct = pro(db, "asset_manager", "overbuilder", cash_naira=60_000_000_000)
    plot = clean(db, district_kind="homes", standing=False)
    hand_over(db, plot["id"], acct)
    budget = development.budget_for({**plot}, "home")
    with pytest.raises(prop.PropertyError, match="70%"):
        development.start(db, acct, plot["id"], "home", NOW9, loan_bank=bank_id(db), loan=budget * 8 // 10)
    development.start(db, acct, plot["id"], "home", NOW9)
    with pytest.raises(prop.PropertyError, match="already"):
        development.start(db, acct, plot["id"], "home", NOW9)
    with pytest.raises(prop.PropertyError, match="developed"):
        auctions.owner_list(db, acct, plot["id"], 0, LATER)
    with pytest.raises(prop.PropertyError, match="developed"):
        prop.build(db, acct, plot["id"], NOW9)


# 8. Can a unitholder make money by buying and selling straight back, or a manager deal with their own fund?
def test_l8_property_fund_units_cannot_be_flipped_and_a_manager_does_not_deal_with_the_fund(db):
    quarters.close_due_quarters(db, after_quarters(9))
    later = after_quarters(9) + timedelta(hours=13)
    trust = _one(db, "SELECT * FROM property_funds WHERE manager IS NULL")
    p, acct = pro(db, "accountant", "flipper", cash_naira=100_000_000)
    start = ledger.balance(db, acct)
    got = propfunds.buy_units(db, acct, trust["id"], naira(5_000_000), later)
    propfunds.sell_units(db, acct, trust["id"], got["units"], later)
    assert ledger.balance(db, acct) < start
    with pytest.raises(propfunds.FundError, match="own units"):
        propfunds.buy_units(db, trust["account_id"], trust["id"], naira(1_000), later)
    manager, m_acct = pro(db, "asset_manager", "selfdealer", level=22, cash_naira=100_000_000)
    from simulation import careers
    db.execute("UPDATE careers SET rank = 1, experience = %s WHERE player_id = %s", (careers.experience_for(22), manager))
    propfunds.open_fund(db, manager, "Selfdealer Property", 100, later)
    mine = clean(db, kind="shop")
    hand_over(db, mine["id"], m_acct)
    listed = auctions.owner_list(db, m_acct, mine["id"], 0, later)
    with pytest.raises(propfunds.FundError, match="never buys from its manager"):
        propfunds.bid(db, manager, listed, naira(1_000_000), later)
    with pytest.raises(propfunds.FundError, match="0% to 2%"):
        propfunds.open_fund(db, pro(db, "asset_manager", "greedy", level=22)[0], "Greedy Property", 500, later)
    assert propfunds.check_books(db) == []


# 9. Does a dispute really freeze everything until the owner settles it?
def test_l9_a_frozen_property_cannot_be_sold_built_rezoned_or_settled_by_a_stranger(db):
    player, acct = pro(db, "asset_manager", "frozenowner", cash_naira=5_000_000_000)
    stranger, s_acct = pro(db, "asset_manager", "stranger", cash_naira=5_000_000_000)
    p = claimed(db, "dispute")
    hand_over(db, p["id"], acct)
    quarters.close_due_quarters(db, after_quarters(9))
    later = after_quarters(9) + timedelta(hours=13)
    with pytest.raises(prop.PropertyError, match="dispute"):
        conveyancing.offer(db, acct, p["id"], {"player": name_of(db, stranger)}, naira(1_000_000), later)
    with pytest.raises(prop.PropertyError, match="dispute"):
        zoning.ask(db, acct, p["id"], "mixed", later)
    with pytest.raises(prop.PropertyError, match="dispute"):
        prop.renovate(db, acct, p["id"], later)
    with pytest.raises(prop.PropertyError, match="owner"):
        conveyancing.settle_dispute(db, s_acct, p["id"], later)
    conveyancing.settle_dispute(db, acct, p["id"], later)
    sound(db)


# 10. Is every transfer registered and its fee paid, and are the consent and registration fees what they say?
def test_l10_every_transfer_is_registered_and_its_fees_are_exact(db):
    seller, s_acct = pro(db, "asset_manager", "registrant", cash_naira=1_000_000)
    buyer, b_acct = pro(db, "asset_manager", "registered", cash_naira=2_000_000_000)
    unit = clean(db, kind="office")
    hand_over(db, unit["id"], s_acct)
    price = naira(80_000_000)
    treasury = ledger.account_id(db, ledger.TREASURY)
    t0 = ledger.balance(db, treasury)
    sale = conveyancing.offer(db, s_acct, unit["id"], {"player": name_of(db, buyer)}, price, NOW9)
    conveyancing.accept(db, b_acct, sale["sale_id"], NOW9)
    conveyancing.ask_consent(db, b_acct, sale["sale_id"], NOW9)
    conveyancing.sign(db, b_acct, sale["sale_id"], CONSENTED)
    fees = price * (data.CONSENT_FEE_BPS + data.REGISTRATION_FEE_BPS) // BPS
    assert ledger.balance(db, treasury) - t0 >= fees                     # (plus any tax the seller owed on it)
    regs = _one(db, "SELECT count(*) AS n FROM land_register WHERE property_id = %s AND how = 'private'", (unit["id"],))["n"]
    assert regs == 1
    # An auction sale is registered too, and its buyer pays the fee.
    lot = auctions.owner_list(db, b_acct, unit["id"], 0, CONSENTED)
    assert lot
    sound(db)
