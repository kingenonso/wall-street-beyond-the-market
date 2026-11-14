"""The gap stage, Part 1: preferred shares, warrants, mezzanine debt, earn-outs and sale-and-leaseback."""

from __future__ import annotations

from datetime import timedelta

import psycopg
import pytest
from psycopg.rows import dict_row

from simulation import (
    corporate,
    firm_deals,
    headquarters,
    instruments,
    leaseback,
    ledger,
    quarters,
)
from simulation import world_data as data
from simulation.money import BPS, naira
from tests.conftest import after_quarters
from tests.test_builds import pro
from tests.test_careers import NOW9, sound
from tests.test_deals import LATER, do_checks, fairness_if_needed
from tests.test_deals_loopholes import ready
from tests.test_firm import firm_of
from tests.test_lending import price_of

pytestmark = pytest.mark.world("eight")


def _one(db, sql, params=()):
    with db.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(sql, params).fetchall()
    return rows[0] if rows else None


def company(db, ticker):
    return _one(db, "SELECT * FROM companies WHERE ticker = %s", (ticker,))


def test_sound_companies_sell_preferred_shares_which_trade_at_the_desk_and_are_paid_first(db):
    made = 0
    for period in (9, 10, 11, 12):
        made += instruments.issue_preferred(db, period, NOW9)
        if made:
            break
    assert made >= 1
    inst = _one(db, "SELECT i.*, c.ticker FROM instruments i JOIN companies c ON c.id = i.company_id WHERE i.kind = 'preferred' LIMIT 1")
    assert inst["dividend_bps"] > 0 and inst["par"] == data.PREFERRED_PAR
    player, account = pro(db, "asset_manager", "income", cash_naira=50_000_000)
    bought = instruments.trade(db, account, inst["asset"], "buy", 1_000, NOW9)
    q = instruments.quote(db, inst, NOW9)
    assert bought["price"] == q["ask"] > q["bid"] and ledger.balance(db, account, inst["asset"]) == 1_000
    with pytest.raises(instruments.InstrumentError, match="hold that many"):
        instruments.trade(db, account, inst["asset"], "sell", 2_000, NOW9)
    quarters.close_due_quarters(db, after_quarters(9))
    result = _one(db, "SELECT net_profit FROM company_results WHERE company_id = %s AND period = 9", (inst["company_id"],))
    got = _one(db, "SELECT coalesce(sum(e.amount), 0)::bigint AS n FROM ledger_entries e JOIN ledger_transactions t ON t.id = e.transaction_id"
                   " WHERE e.account_id = %s AND t.kind = 'preferred_dividend' AND e.asset = 'NGN'", (account,))["n"]
    if result["net_profit"] > 0:
        assert got == 1_000 * inst["par"] * inst["dividend_bps"] // BPS // 4
    stray = _one(db, "SELECT count(*) AS n FROM company_results WHERE period = 9 AND drivers::text LIKE '%%outside its normal business%%'")
    assert stray["n"] == 0
    assert instruments.check_books(db) == []
    sound(db)


def test_warrants_are_used_at_the_close_for_new_shares_and_the_company_receives_the_money(db):
    player, account = pro(db, "asset_manager", "warrantholder", cash_naira=50_000_000)
    idc = company(db, "IDC")
    strike = price_of(db, "IDC") * 8 // 10
    inst = instruments.grant_warrants(db, idc, {account: 1_000}, strike=strike, expiry_period=12, period=9, why="test", now=NOW9)
    assert ledger.balance(db, account, inst["asset"]) == 1_000
    asked = instruments.ask_to_exercise(db, account, inst["asset"], 600, NOW9)
    assert asked["cash"] == 600 * strike and ledger.balance(db, account, inst["asset"]) == 400
    company_cash = ledger.balance(db, idc["account_id"])
    shares_before = ledger.balance(db, account, idc["share_asset"])
    assert instruments.check_books(db) == []
    quarters.close_due_quarters(db, after_quarters(9))
    assert ledger.balance(db, account, idc["share_asset"]) == shares_before + 600
    assert _one(db, "SELECT status FROM warrant_exercises WHERE id = %s", (asked["id"],))["status"] == "done"
    assert ledger.balance(db, idc["account_id"]) != company_cash                # the money went to the company (with its quarter)
    assert instruments.check_books(db) == []
    # A split: each warrant then buys two shares at half the price.
    instruments.after_split(db, idc["id"], 2)
    after = _one(db, "SELECT * FROM instruments WHERE id = %s", (inst["id"],))
    assert after["shares_per"] == 2 and after["strike"] == strike // 2
    # They lapse after their last quarter's close.
    db.execute("UPDATE instruments SET expiry_period = 10 WHERE id = %s", (inst["id"],))
    quarters.close_due_quarters(db, after_quarters(10))
    assert _one(db, "SELECT status FROM instruments WHERE id = %s", (inst["id"],))["status"] == "expired"
    with pytest.raises(instruments.InstrumentError, match="lapsed|not lapsed"):
        instruments.ask_to_exercise(db, account, inst["asset"], 100, after_quarters(10) + timedelta(hours=13))
    stray = _one(db, "SELECT count(*) AS n FROM company_results WHERE period >= 9 AND drivers::text LIKE '%%outside its normal business%%'")
    assert stray["n"] == 0
    sound(db)


def test_a_buyout_can_add_mezzanine_after_the_bank_and_its_lender_takes_five_percent(db):
    empire, team, sale, file_id = ready(db)
    do_checks(db, empire, team, file_id)
    price = sale["asking"] * 12 // 10
    fairness_if_needed(db, team, file_id, price)
    quote = firm_deals.loan_quote(db, sale, price, 9)
    loan = min(quote["most"], price // 2)
    mezz = firm_deals.mezzanine_quote(db, sale, price, loan)
    assert mezz["rate_bps"] > quote["rate_bps"]
    with pytest.raises(Exception, match="at most"):
        firm_deals.place_bid(db, team["head"], file_id, price, loan, LATER, mezzanine=mezz["most"] + naira(1))
    bid = firm_deals.place_bid(db, team["head"], file_id, price, loan, LATER, mezzanine=mezz["most"])
    assert bid["equity"] == bid["price"] - loan - mezz["most"]
    quarters.close_due_quarters(db, after_quarters(9))
    deal = _one(db, "SELECT * FROM deals WHERE empire_id = %s", (empire["id"],))
    if deal is None:
        pytest.skip("Outbid by a computer-run empire.")
    debts = _rows(db, empire["id"])
    assert "mezzanine" in debts and debts["mezzanine"]["outstanding"] == mezz["most"]
    asset = _one(db, "SELECT share_asset FROM companies WHERE id = %s", (sale["company_id"],))["share_asset"]
    funds = ledger.account_id(db, ledger.INVESTORS_INSTITUTIONS)
    kicker = sale["shares"] * data.MEZZ_EQUITY_BPS // BPS
    assert ledger.balance(db, funds, asset) >= kicker
    assert ledger.balance(db, empire["account_id"], asset) == sale["shares"] - kicker
    assert firm_deals.check_books(db) == []
    sound(db)


def _rows(db, empire_id):
    with db.cursor(row_factory=dict_row) as cur:
        return {r["kind"]: r for r in cur.execute("SELECT * FROM empire_debts WHERE empire_id = %s", (empire_id,)).fetchall()}


def test_an_earn_out_is_paid_only_if_the_company_reaches_its_target(db):
    empire, team, sale, file_id = ready(db)
    do_checks(db, empire, team, file_id)
    price = sale["asking"] * 15 // 10                      # (a seller counts the earn-out at 60%, so the headline is higher)
    fairness_if_needed(db, team, file_id, price)
    earnout = price * 2 // 10
    with pytest.raises(Exception, match="later"):
        firm_deals.place_bid(db, team["head"], file_id, price, 0, LATER, earnout=price * 4 // 10)
    bid = firm_deals.place_bid(db, team["head"], file_id, price, 0, LATER, earnout=earnout)
    assert bid["equity"] == bid["price"] - earnout
    quarters.close_due_quarters(db, after_quarters(9))
    deal = _one(db, "SELECT * FROM deals WHERE empire_id = %s", (empire["id"],))
    if deal is None:
        pytest.skip("Outbid by a computer-run empire.")
    e = _one(db, "SELECT * FROM deal_earnouts WHERE deal_id = %s", (deal["id"],))
    assert e and e["amount"] == earnout and e["status"] == "running"
    # Test set-up: the earn-out falls due at the next close, against a target the company is sure to reach.
    db.execute("UPDATE deal_earnouts SET due_period = 10, target_sales = 0 WHERE id = %s", (e["id"],))
    quarters.close_due_quarters(db, after_quarters(10))
    assert _one(db, "SELECT status, paid FROM deal_earnouts WHERE id = %s", (e["id"],)) == {"status": "paid", "paid": earnout}
    assert firm_deals.check_books(db) == []
    sound(db)


def test_a_building_sold_and_leased_back_keeps_the_headquarters_until_the_lease_is_broken(db):
    empire, team = firm_of(db, n_cash=60_000_000_000)
    building = _one(db, "SELECT p.id FROM properties p JOIN districts d ON d.id = p.district_id JOIN property_holdings h ON h.property_id = p.id"
                        " JOIN companies c ON c.account_id = h.account_id WHERE d.city = 'Lagos' AND p.status = 'standing' AND p.kind = 'office'"
                        " AND p.title_flaw_bps = 0 AND NOT EXISTS (SELECT 1 FROM auctions a WHERE a.property_id = p.id AND a.status = 'open')"
                        " ORDER BY p.id LIMIT 1")["id"]
    db.execute("DELETE FROM property_holdings WHERE property_id = %s", (building,))
    db.execute("INSERT INTO property_holdings (property_id, account_id, share_bps, since_period, paid) VALUES (%s, %s, 10000, 8, 0)",
               (building, empire["account_id"]))
    headquarters.establish(db, team["head"], building, NOW9)
    cash_before = ledger.balance(db, empire["account_id"])
    with pytest.raises(Exception):
        leaseback.sell_and_lease_back(db, team["accountant"], building, 8, NOW9, for_empire=True)      # the head's to decide
    done = leaseback.sell_and_lease_back(db, team["head"], building, 8, NOW9, for_empire=True)
    assert ledger.balance(db, empire["account_id"]) == cash_before + done["price"]
    assert done["price"] < done["worth"] and done["rent"] > 0
    owner = _one(db, "SELECT h.account_id, c.sector FROM property_holdings h JOIN companies c ON c.account_id = h.account_id WHERE h.property_id = %s",
                 (building,))
    assert owner["sector"] == "real_estate"
    quarters.close_due_quarters(db, after_quarters(9))
    hq = headquarters.of(db, empire["id"])
    assert not hq["homeless"]
    assert _one(db, "SELECT missed FROM property_leases WHERE id = %s", (done["lease_id"],))["missed"] == 0
    # Two rents missed: the lease is broken and the headquarters loses the building.
    db.execute("UPDATE property_leases SET missed = 1 WHERE id = %s", (done["lease_id"],))
    ledger.transfer(db, payer=empire["account_id"], receiver=ledger.account_id(db, ledger.TREASURY), amount=ledger.balance(db, empire["account_id"]),
                    kind="test_cash", memo="Test: spent")
    quarters.close_due_quarters(db, after_quarters(10))
    assert _one(db, "SELECT status FROM property_leases WHERE id = %s", (done["lease_id"],))["status"] == "broken"
    assert headquarters.of(db, empire["id"])["homeless"]
    stray = _one(db, "SELECT count(*) AS n FROM company_results WHERE period >= 9 AND drivers::text LIKE '%%outside its normal business%%'")
    assert stray["n"] == 0
    sound(db)


_ = (psycopg, corporate)
