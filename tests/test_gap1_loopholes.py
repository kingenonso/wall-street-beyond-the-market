"""The gap stage, Part 1: ten ways a player might try to get round the new rules, each shown to be closed."""

from __future__ import annotations

from datetime import timedelta

import pytest
from psycopg.rows import dict_row

from simulation import (
    derivatives,
    firm_deals,
    instruments,
    leaseback,
    ledger,
    lending,
    swaps,
)
from simulation import property as prop
from simulation.money import naira
from tests.conftest import ADULT, join
from tests.test_builds import pro
from tests.test_careers import NOW9, sound
from tests.test_deals import LATER as DEAL_LATER
from tests.test_deals import do_checks, fairness_if_needed
from tests.test_deals_loopholes import ready as deal_ready
from tests.test_derivatives import trader
from tests.test_firm import firm_of
from tests.test_lending import bank_id, price_of

pytestmark = pytest.mark.world("eight")
LATER = NOW9 + timedelta(hours=1)


def _one(db, sql, params=()):
    with db.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(sql, params).fetchall()
    return rows[0] if rows else None


def series(db, kind, underlying, expiry=9):
    derivatives.ensure(db, NOW9)
    return _one(db, "SELECT * FROM derivative_series WHERE kind = %s AND underlying = %s AND expiry_period = %s AND status = 'open'"
                    " ORDER BY strike LIMIT 1", (kind, underlying, expiry))


def name_of(db, player):
    return _one(db, "SELECT display_name FROM players WHERE id = %s", (player,))["display_name"]


# 1. Can a player trade with themselves to print a price (a "wash trade") on the clearing house?
def test_l1_a_players_own_waiting_order_is_never_matched_against_them(db):
    a, acct = trader(db, "asset_manager", "washer", cash_naira=500_000_000)
    x = series(db, "call", "BSX50")
    q = derivatives.quote(db, x, NOW9)
    inside = (q["bid"] + q["ask"]) // 2
    derivatives.trade(db, acct, x["id"], "sell", 2, NOW9, limit=inside, player_id=a)
    ask_then = derivatives.quote(db, x, LATER)["ask"]
    bought = derivatives.trade(db, acct, x["id"], "buy", 2, LATER, player_id=a)
    assert bought["price"] == ask_then != inside                                   # from the market makers, not from their own order
    assert not _one(db, "SELECT 1 FROM derivative_trades WHERE buyer = %s AND seller = %s", (acct, acct))
    assert derivatives.check_books(db) == []


# 2. Can a player cancel somebody else's waiting order, or take back what it holds?
def test_l2_nobody_cancels_anothers_order(db):
    a, a_acct = trader(db, "asset_manager", "owner", cash_naira=500_000_000)
    b, b_acct = trader(db, "asset_manager", "meddler", cash_naira=1)
    x = series(db, "future", "OIL")
    order = derivatives.trade(db, a_acct, x["id"], "buy", 2, NOW9, limit=derivatives.quote(db, x, NOW9)["bid"] // 2, player_id=a)
    with pytest.raises(derivatives.DerivativesError, match="no such"):
        derivatives.cancel_order(db, b_acct, order["order_id"], LATER)
    assert _one(db, "SELECT status FROM derivative_orders WHERE id = %s", (order["order_id"],))["status"] == "open"
    assert derivatives.check_books(db) == []


# 3. Can a beginner skip the unlocks: borrow before Level 10, buy options before 15, write or use futures before 25?
def test_l3_each_instrument_waits_for_its_level(db):
    young, y_acct = pro(db, "asset_manager", "fresh", level=5, cash_naira=100_000_000)
    x = series(db, "call", "BSX50")
    f = series(db, "future", "BSX50")
    with pytest.raises(lending.LendingError, match="Level 10"):
        lending.take_margin(db, y_acct, bank_id(db), naira(1_000), NOW9, player_id=young)
    with pytest.raises(derivatives.DerivativesError, match="Level 15"):
        derivatives.open_position(db, y_acct, x["id"], "long", 1, NOW9, player_id=young)
    mid, m_acct = pro(db, "asset_manager", "middling", level=20, cash_naira=100_000_000)
    derivatives.open_position(db, m_acct, x["id"], "long", 1, NOW9, player_id=mid)          # buying an option is open
    other = _one(db, "SELECT * FROM derivative_series WHERE kind = 'call' AND underlying = 'BSX50' AND expiry_period = 9 AND id <> %s"
                     " ORDER BY strike DESC LIMIT 1", (x["id"],))
    with pytest.raises(derivatives.DerivativesError, match="Level 25"):
        derivatives.open_position(db, m_acct, other["id"], "short", 1, NOW9, player_id=mid)
    with pytest.raises(derivatives.DerivativesError, match="Level 25"):
        derivatives.open_position(db, m_acct, f["id"], "long", 1, NOW9, player_id=mid)
    # Even at Level 30, futures need the build's risk module learned.
    from simulation import careers
    db.execute("UPDATE careers SET rank = 1, experience = %s WHERE player_id = %s", (careers.experience_for(30), mid))
    with pytest.raises(derivatives.DerivativesError, match="learned"):
        derivatives.open_position(db, m_acct, f["id"], "long", 1, NOW9, player_id=mid)


# 4. Can a short seller slip in a new short while the Securities Regulator's ban stands?
def test_l4_no_new_short_during_a_ban_but_closing_is_allowed(db):
    a, acct = trader(db, "asset_manager", "bear", cash_naira=500_000_000)
    s = lending.open_short(db, acct, "GGM", 1_000, NOW9, player_id=a)
    company = _one(db, "SELECT id FROM companies WHERE ticker = 'GGM'")["id"]
    db.execute("INSERT INTO short_bans (company_id, from_day, until_day, reason, at) VALUES (%s, %s, %s, 'test', %s)",
               (company, NOW9.date(), NOW9.date() + timedelta(days=2), NOW9))
    with pytest.raises(lending.LendingError, match="[Bb]an|Regulator"):
        lending.open_short(db, acct, "GGM", 1_000, LATER, player_id=a)
    lending.close_short(db, acct, s["short_id"], LATER)
    sound(db)


# 5. Can a player use a swap to move money between themselves and their own empire, or with themselves?
def test_l5_no_swap_with_yourself_or_between_an_empire_and_its_members(db):
    empire, team = firm_of(db, n_cash=5_000_000_000)
    from tests.test_derivatives import ready
    banker = ready(db, team["investment_banker"])
    with pytest.raises(swaps.SwapError, match="two different sides"):
        swaps.propose(db, banker, kind="rate", counterparty={"player": name_of(db, banker)}, side="pay_fixed", quarters=1,
                      notional=naira(10_000_000), fixed=2_000, now=NOW9)
    with pytest.raises(swaps.SwapError, match="own empire"):
        swaps.propose(db, banker, kind="rate", counterparty={"empire": empire["name"]}, side="pay_fixed", quarters=1,
                      notional=naira(10_000_000), fixed=2_000, now=NOW9)
    with pytest.raises(swaps.SwapError, match="own members"):
        swaps.propose(db, banker, kind="rate", counterparty={"player": name_of(db, team["head"])}, side="pay_fixed", quarters=1,
                      notional=naira(10_000_000), fixed=9_999, now=NOW9, for_empire=True)
    # And an offer made to one player cannot be accepted by another.
    a, _ = trader(db, "investment_banker", "offerer", cash_naira=10_000_000)
    b, _ = trader(db, "investment_banker", "intended", cash_naira=10_000_000)
    c, _ = trader(db, "investment_banker", "interloper", cash_naira=10_000_000)
    offer = swaps.propose(db, a, kind="oil", counterparty={"player": name_of(db, b)}, side="pay_fixed", quarters=1, barrels=100,
                          fixed=swaps.oil_for(db), now=NOW9)
    with pytest.raises(swaps.SwapError, match="no such swap"):
        swaps.accept(db, c, offer["swap_id"], NOW9)


# 6. Can a warrant be used twice, used after it lapses, or someone else's handed-in warrants taken back?
def test_l6_warrants_are_used_once_and_only_by_their_holder(db):
    holder, h_acct = pro(db, "asset_manager", "holder", cash_naira=50_000_000)
    other, o_acct = pro(db, "asset_manager", "thief", cash_naira=50_000_000)
    idc = _one(db, "SELECT * FROM companies WHERE ticker = 'IDC'")
    inst = instruments.grant_warrants(db, idc, {h_acct: 100}, strike=price_of(db, "IDC"), expiry_period=12, period=9, why="test", now=NOW9)
    asked = instruments.ask_to_exercise(db, h_acct, inst["asset"], 100, NOW9)
    with pytest.raises(instruments.InstrumentError):
        instruments.ask_to_exercise(db, h_acct, inst["asset"], 1, NOW9)                    # none left to hand in
    with pytest.raises(instruments.InstrumentError, match="no such"):
        instruments.cancel_exercise(db, o_acct, asked["id"], NOW9)
    with pytest.raises(instruments.InstrumentError):
        instruments.ask_to_exercise(db, o_acct, inst["asset"], 1, NOW9)                    # holds none
    db.execute("UPDATE instruments SET status = 'expired' WHERE id = %s", (inst["id"],))
    instruments.cancel_exercise(db, h_acct, asked["id"], NOW9)
    with pytest.raises(instruments.InstrumentError, match="lapsed"):
        instruments.ask_to_exercise(db, h_acct, inst["asset"], 100, NOW9)
    assert instruments.check_books(db) == []


# 7. Can a player sell preferred shares they do not hold, or buy more than the desk has?
def test_l7_the_desk_sells_only_what_it_has_and_buys_only_what_you_hold(db):
    made = 0
    for period in (9, 10, 11, 12):
        made += instruments.issue_preferred(db, period, NOW9)
        if made:
            break
    inst = _one(db, "SELECT * FROM instruments WHERE kind = 'preferred' LIMIT 1")
    player, acct = pro(db, "asset_manager", "shorter", cash_naira=1_000_000_000)
    with pytest.raises(instruments.InstrumentError, match="hold"):
        instruments.trade(db, acct, inst["asset"], "sell", 1, NOW9)
    dealer = ledger.account_id(db, ledger.INVESTORS_INSTITUTIONS)
    with pytest.raises(instruments.InstrumentError, match="to sell"):
        instruments.trade(db, acct, inst["asset"], "buy", ledger.balance(db, dealer, inst["asset"]) + 1, NOW9)
    with pytest.raises(instruments.InstrumentError):
        instruments.trade(db, acct, inst["asset"], "buy", 1, NOW9.replace(hour=23))         # the desk is shut at night
    assert instruments.check_books(db) == []


# 8. Can a player lease back a building that is not theirs, or one mortgaged, or for a silly term?
def test_l8_only_an_unencumbered_building_owned_outright_is_leased_back(db):
    player, acct = pro(db, "asset_manager", "landlord", cash_naira=1_000_000)
    theirs = _one(db, "SELECT p.id FROM properties p JOIN property_holdings h ON h.property_id = p.id WHERE p.status = 'standing'"
                      " AND p.kind = 'office' ORDER BY p.id LIMIT 1")["id"]
    with pytest.raises(prop.PropertyError, match="owned outright"):
        leaseback.sell_and_lease_back(db, player, theirs, 8, NOW9)
    db.execute("DELETE FROM property_holdings WHERE property_id = %s", (theirs,))
    db.execute("INSERT INTO property_holdings (property_id, account_id, share_bps, since_period, paid) VALUES (%s, %s, 10000, 8, 0)",
               (theirs, acct))
    for bad in (3, 21, 0):
        with pytest.raises(prop.PropertyError, match="quarters"):
            leaseback.sell_and_lease_back(db, player, theirs, bad, NOW9)
    db.execute("INSERT INTO mortgages (property_id, borrower, bank_company_id, principal, outstanding, rate_bps, taken_period, term_quarters, at)"
               " VALUES (%s, %s, %s, 100, 100, 1000, 8, 20, %s)", (theirs, acct, bank_id(db), NOW9))
    with pytest.raises(prop.PropertyError, match="mortgage"):
            leaseback.sell_and_lease_back(db, player, theirs, 8, NOW9)


# 9. Can a bidder pad a bid with an earn-out or mezzanine beyond the limits, or offer an earn-out to a player seller?
def test_l9_mezzanine_and_earn_out_stay_inside_their_limits(db):
    empire, team, sale, file_id = deal_ready(db)
    do_checks(db, empire, team, file_id)
    price = sale["asking"] * 12 // 10
    fairness_if_needed(db, team, file_id, price)
    with pytest.raises(Exception, match="later"):
        firm_deals.place_bid(db, team["head"], file_id, price, 0, DEAL_LATER, earnout=price * 31 // 100)
    with pytest.raises(Exception):
        firm_deals.place_bid(db, team["head"], file_id, price, 0, DEAL_LATER, earnout=-1)
    with pytest.raises(Exception):
        firm_deals.place_bid(db, team["head"], file_id, price, 0, DEAL_LATER, mezzanine=-1)
    mq = firm_deals.mezzanine_quote(db, sale, price, 0)
    with pytest.raises(Exception, match="at most"):
        firm_deals.place_bid(db, team["head"], file_id, price, 0, DEAL_LATER, mezzanine=mq["most"] + 1)
    # The whole price cannot be made of other people's money and promises.
    loan = min(firm_deals.loan_quote(db, sale, price, 9)["most"], price // 2)
    mezz = firm_deals.mezzanine_quote(db, sale, price, loan)["most"]
    earnout = min(price - loan - mezz, price * 3 // 10)
    if price - loan - mezz - earnout < price // 10:
        with pytest.raises(Exception, match="at least 10%"):
            firm_deals.place_bid(db, team["head"], file_id, price, loan, DEAL_LATER, mezzanine=mezz, earnout=earnout)
    with pytest.raises(Exception, match="No bank"):
        firm_deals.place_bid(db, team["head"], file_id, price, price, DEAL_LATER)
    sound(db)


# 10. Can the public pages show who is waiting to trade, who holds what, or anybody else's swaps and leases?
def test_l10_the_public_pages_show_no_one_elses_orders_holdings_or_contracts(db, client):
    a, acct = trader(db, "asset_manager", "secretive", cash_naira=500_000_000)
    x = series(db, "call", "BSX50")
    q = derivatives.quote(db, x, NOW9)
    derivatives.trade(db, acct, x["id"], "sell", 2, NOW9, limit=(q["bid"] + q["ask"]) // 2, player_id=a)
    swaps.propose(db, a, kind="rate", counterparty={"bank": bank_id(db)}, side="pay_fixed", quarters=1, notional=naira(10_000_000), now=NOW9)
    assert join(client, ADULT).status_code == 201
    pages = [client.get(path) for path in ("/api/derivatives?underlying=BSX50", "/api/swaps", "/api/instruments", "/api/property")]
    assert all(p.status_code == 200 for p in pages)
    words = " ".join(p.text for p in pages)
    assert "secretive" not in words and str(acct) not in words
    board = pages[0].json()
    assert board["my_orders"] == [] and pages[1].json()["swaps"] == []
    land = _one(db, "SELECT id FROM properties WHERE kind = 'land' LIMIT 1")
    if land:
        assert client.get(f"/api/property/{land['id']}/leaseback").status_code == 404
    assert client.get("/api/property/999999999/leaseback").status_code == 404
