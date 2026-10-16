"""Private equity stage, part 2A: the rest of running a company, trouble, and the ways out."""

from __future__ import annotations

from datetime import timedelta

import pytest
from psycopg.types.json import Jsonb

from simulation import empires, firm_deals, firm_money, firm_owned, ledger, private, quarters
from simulation.money import BPS, million_naira
from tests.conftest import after_quarters
from tests.test_builds import pro
from tests.test_careers import NOW9
from tests.test_deals import LATER, _dicts, _one, do_checks, open_a_sale
from tests.test_firm import firm_of, member
from tests.test_objectives import give_cash

pytestmark = pytest.mark.world("eight")
AFTER9 = after_quarters(9) + timedelta(hours=2)


def own(db, empire, ticker, *, cost=million_naira(1_000)):
    """Hand an empire a private company outright (as if bought), for tests of running one."""
    company = _one(db, "SELECT * FROM companies WHERE ticker = %s", (ticker,))
    founders = ledger.account_id(db, ledger.INVESTORS_FOUNDERS)
    with db.transaction():
        ledger.transfer(db, payer=founders, receiver=empire["account_id"], amount=ledger.balance(db, founders, company["share_asset"]),
                        asset=company["share_asset"], kind="company_sale", memo="test", period=9)
        db.execute("INSERT INTO company_stakes (company_id, empire_id, cost, since_period) VALUES (%s, %s, %s, 9)", (company["id"], empire["id"], cost))
        db.execute("INSERT INTO owned_companies (company_id, empire_id, bought_period, cost, since) VALUES (%s, %s, 9, %s, %s)",
                   (company["id"], empire["id"], cost, NOW9))
    return company


def test_partners_put_in_money_and_own_their_share_of_the_company(db):
    lead, team = firm_of(db, n_cash=60_000_000_000)
    other_head, _ = pro(db, "asset_manager", "partner_head", level=20, cash_naira=60_000_000)
    other = empires.found(db, other_head, "Partner House", million_naira(40), 0, after_quarters(8) + timedelta(hours=3))
    for build, name in (("journalist", "p1"), ("accountant", "p2")):
        member(db, other, other_head, build, name)
    other = empires.open_empire(db, other_head, after_quarters(8) + timedelta(hours=3))
    give_cash(db, other["account_id"], 30_000_000_000)
    sale = open_a_sale(db, "KGO")
    file_id = firm_deals.open_file(db, team["investment_banker"], sale["id"], LATER)["file_id"]
    firm_deals.sign_nda(db, team["lawyer"], file_id, LATER)
    do_checks(db, lead, team, file_id)
    pledge = sale["asking"] // 4
    invite = firm_deals.invite_partner(db, team["head"], file_id, other["id"], pledge, LATER)
    with pytest.raises(empires.EmpireError, match="head"):
        firm_deals.answer_partner(db, team["journalist"], invite["partner_id"], True, LATER)
    cash = ledger.balance(db, other["account_id"])
    firm_deals.answer_partner(db, other_head, invite["partner_id"], True, LATER)
    assert ledger.balance(db, other["account_id"]) == cash - pledge and firm_deals.check_books(db) == []
    bid = firm_deals.place_bid(db, team["head"], file_id, sale["asking"] * 13 // 10, 0, LATER)
    assert bid["partners"] == pledge and bid["equity"] == bid["price"] - pledge
    assert quarters.close_due_quarters(db, after_quarters(9)) == [9]
    deal = _one(db, "SELECT * FROM deals WHERE empire_id = %s", (lead["id"],))
    assert deal is not None
    company = _one(db, "SELECT * FROM companies WHERE id = %s", (sale["company_id"],))
    theirs = ledger.balance(db, other["account_id"], company["share_asset"])
    assert theirs == sale["shares"] * pledge // deal["price"] > 0
    assert ledger.balance(db, lead["account_id"], company["share_asset"]) == sale["shares"] - theirs
    assert _one(db, "SELECT empire_id FROM owned_companies WHERE company_id = %s", (company["id"],))["empire_id"] == lead["id"]
    assert firm_deals.check_books(db) == [] and ledger.audit(db) == []


def test_the_bank_tests_its_promises_calls_the_loan_and_takes_the_company(db):
    empire, team = firm_of(db, n_cash=60_000_000_000)
    company = own(db, empire, "SSC")
    bank = firm_money._lender_bank(db, 9, million_naira(100))
    with db.transaction():
        ledger.transfer(db, payer=bank["account_id"], receiver=empire["account_id"], amount=million_naira(100), kind="empire_borrowing",
                        memo="test buyout loan", period=9)
        debt = _one(db, "INSERT INTO empire_debts (empire_id, kind, lender_account, lender_name, principal, outstanding, rate_bps, taken_period,"
                        " due_period, company_id, covenants, signed_by, at) VALUES (%s, 'buyout', %s, %s, %s, %s, 2500, 9, 29, %s, %s, %s, now())"
                        " RETURNING *", (empire["id"], bank["account_id"], bank["name"], million_naira(100) * 1000, million_naira(100) * 1000,
                                         company["id"], Jsonb(firm_deals.COVENANTS), team["head"]))
    # A loan a thousand times what was lent is far above five years' earnings: the promise is broken.
    assert firm_deals.covenant_test(db, debt)
    assert quarters.close_due_quarters(db, after_quarters(9)) == [9]
    assert _one(db, "SELECT status FROM empire_debts WHERE id = %s", (debt["id"],))["status"] == "called"
    funds = ledger.account_id(db, ledger.INVESTORS_INSTITUTIONS)
    bank_cash = ledger.balance(db, bank["account_id"])
    assert quarters.close_due_quarters(db, after_quarters(10)) == [10]
    # The empire could not repay: the bank took the company it lent against and sold it to the pension funds.
    assert ledger.balance(db, empire["account_id"], company["share_asset"]) == 0
    assert ledger.balance(db, funds, company["share_asset"]) > 0
    assert ledger.balance(db, bank["account_id"]) != bank_cash
    assert not _one(db, "SELECT 1 FROM owned_companies WHERE company_id = %s AND empire_id = %s", (company["id"], empire["id"]))
    assert _one(db, "SELECT * FROM deal_exits WHERE empire_id = %s", (empire["id"],))["kind"] == "to_buyer"
    assert ledger.audit(db) == []


def test_a_company_that_cannot_pay_its_way_is_wound_up_and_its_creditors_paid_in_order(db):
    c = _one(db, "SELECT * FROM companies WHERE ticker = 'CCS'")
    # The rule: behind on its bills or loans at the last two closes, and owing more than it owns.
    behind, fine = {"payables": 1, "principal_overdue": 0, "total_equity": -1}, {"payables": 0, "principal_overdue": 0, "total_equity": 5}
    assert firm_owned.in_trouble([behind, {**behind, "total_equity": 9}])
    assert not firm_owned.in_trouble([behind, fine]) and not firm_owned.in_trouble([{**behind, "total_equity": 0}, behind])
    assert not firm_owned.in_trouble([behind])
    founders = ledger.account_id(db, ledger.INVESTORS_FOUNDERS)
    owners_cash = ledger.balance(db, founders)
    last = _one(db, "SELECT * FROM company_results WHERE company_id = %s ORDER BY period DESC LIMIT 1", (c["id"],))
    with db.transaction():
        firm_owned._wind_up(db, c, last, 8, AFTER9)
    c = _one(db, "SELECT * FROM companies WHERE id = %s", (c["id"],))
    assert c["status"] == "wound_up"
    record = _one(db, "SELECT * FROM administrations WHERE company_id = %s", (c["id"],))
    ranks = [line["rank"] for line in record["paid"]]
    assert ranks == sorted(ranks)                                  # lenders, then staff, then tax, then the rest, then owners
    assert all(a["status"] == "sold" for a in private.assets(db, c["id"], all_=True))
    assert ledger.balance(db, c["account_id"]) == 0 or record["paid"][-1]["who"] != "its owners"
    assert ledger.balance(db, founders) != owners_cash
    # It no longer trades: the next close leaves it out, and the ledger still balances.
    assert c["id"] not in {x["id"] for x in quarters.companies.load_companies(db)}
    assert quarters.close_due_quarters(db, after_quarters(9)) == [9]
    assert not _one(db, "SELECT 1 FROM company_results WHERE company_id = %s AND period = 9", (c["id"],))
    assert ledger.audit(db) == []


def test_the_100_day_plan_costs_money_at_once_and_may_fail(db):
    empire, team = firm_of(db, n_cash=60_000_000_000)
    company = own(db, empire, "MTH")
    cash = ledger.balance(db, company["account_id"])
    with pytest.raises(empires.EmpireError, match="head"):
        firm_owned.start_plan(db, team["accountant"], company["id"], "suppliers", LATER)
    started = firm_owned.start_plan(db, team["head"], company["id"], "suppliers", LATER)
    assert ledger.balance(db, company["account_id"]) == cash - started["cost"]
    with pytest.raises(empires.EmpireError, match="already under way"):
        firm_owned.start_plan(db, team["head"], company["id"], "suppliers", LATER)
    firm_owned.start_plan(db, team["head"], company["id"], "rebrand", LATER)
    firm_owned.start_plan(db, team["head"], company["id"], "pricing", LATER)
    with pytest.raises(empires.EmpireError, match="at most three"):
        firm_owned.start_plan(db, team["head"], company["id"], "systems", LATER)
    assert quarters.close_due_quarters(db, after_quarters(9)) == [9]
    plan = _one(db, "SELECT * FROM company_plans WHERE company_id = %s AND code = 'suppliers'", (company["id"],))
    assert plan["status"] in ("done", "failed") and plan["outcome"]
    p = private.profile(db, company["id"])
    assert (plan["status"] == "done") == (p["labour_adj_bps"] <= -300)
    assert ledger.audit(db) == []


def test_a_company_doctor_is_paid_only_if_the_rescue_works(db):
    failing = next(c for c in _dicts(db, "SELECT * FROM companies WHERE NOT listed AND status = 'trading' ORDER BY ticker")
                   if firm_owned.failing(db, c["id"]))
    doctor, account = pro(db, "accountant", "doctor")
    stranger, _ = pro(db, "journalist", "stranger")
    with pytest.raises(empires.EmpireError, match="Accountant"):
        firm_owned.propose_rescue(db, stranger, failing["id"], ["cut_costs"], 0, LATER)
    sales = firm_owned._quarter_sales(db, failing["id"])
    with pytest.raises(empires.EmpireError, match="5%"):
        firm_owned.propose_rescue(db, doctor, failing["id"], ["cut_costs"], sales, LATER)
    # (Asking the bank for time is offered only where there is a bank loan to extend.)
    has_loans = _one(db, "SELECT count(*) AS n FROM company_debts WHERE company_id = %s AND principal_outstanding > 0", (failing["id"],))["n"] > 0
    try:
        plan = firm_owned.propose_rescue(db, doctor, failing["id"], ["cut_costs", "extend_loans"] if has_loans else ["cut_costs"], sales * 2 // 100, LATER)
    except empires.EmpireError as e:
        assert "would change nothing" in str(e)
        plan = firm_owned.propose_rescue(db, doctor, failing["id"], ["cut_costs"], sales * 2 // 100, LATER)
    row = _one(db, "SELECT * FROM company_plans WHERE id = %s", (plan["id"],))
    assert row["status"] == "running"                               # the founders accept a sensible fee at once
    before = ledger.balance(db, account)
    for q in (9, 10, 11, 12):
        assert quarters.close_due_quarters(db, after_quarters(q)) == [q]
    row = _one(db, "SELECT * FROM company_plans WHERE id = %s", (plan["id"],))
    assert row["status"] in ("done", "failed")
    paid = ledger.balance(db, account) - before
    owed = _one(db, "SELECT coalesce(sum(amount_outstanding), 0)::bigint AS n FROM company_payables WHERE company_id = %s AND payee_account_id = %s",
                (failing["id"], account))["n"]
    # Paid (or owed) only if it worked, and then exactly the fee, once.
    assert (paid + owed == row["fee"]) if row["status"] == "done" else (paid == 0 and owed == 0)
    assert row["fee_paid"] == (row["status"] == "done")
    assert ledger.audit(db) == []


def test_selling_to_another_empire_and_listing_on_the_exchange(db):
    empire, team = firm_of(db, n_cash=60_000_000_000)
    seller = own(db, empire, "IGH")
    worth = private.value_of(db, seller["id"])
    with pytest.raises(empires.EmpireError, match="lowest price"):
        firm_owned.sell_to_empire(db, team["head"], seller["id"], worth, worth * 2, "sealed", LATER)
    firm_owned.sell_to_empire(db, team["head"], seller["id"], worth, worth * 9 // 10, "auction", LATER)
    sale = _one(db, "SELECT * FROM sale_processes WHERE company_id = %s AND status = 'open'", (seller["id"],))
    assert sale["seller_empire_id"] == empire["id"] and sale["seller_account"] == empire["account_id"]
    with pytest.raises(empires.EmpireError, match="seller"):
        firm_deals.open_file(db, team["investment_banker"], sale["id"], LATER)
    # A company that pays its way can be listed: new shares go to the public at the next close.
    listed = own(db, empire, "OPS")
    if firm_owned.failing(db, listed["id"]) or _one(db, "SELECT net_profit FROM company_results WHERE company_id = %s ORDER BY period DESC LIMIT 1",
                                                     (listed["id"],))["net_profit"] <= 0:
        pytest.skip("OPS is not profitable in this world.")
    firm_owned.list_on_exchange(db, team["head"], listed["id"], LATER)
    assert quarters.close_due_quarters(db, after_quarters(9)) == [9]
    assert quarters.close_due_quarters(db, after_quarters(10)) == [10]
    now_listed = _one(db, "SELECT listed FROM companies WHERE id = %s", (listed["id"],))["listed"]
    if now_listed:
        assert _one(db, "SELECT 1 FROM market_instruments WHERE company_id = %s", (listed["id"],))
        assert _one(db, "SELECT kind FROM deal_exits WHERE company_id = %s", (listed["id"],))["kind"] == "listing"
    assert ledger.audit(db) == []


def test_a_start_up_is_founded_with_the_founders_own_money_and_trades_at_once(db):
    founders = ledger.account_id(db, ledger.INVESTORS_FOUNDERS)
    money_before = ledger.amount_in_existence(db)
    cash = ledger.balance(db, founders)
    with db.transaction():
        made = private.found_startup(db, 9, private._seed(db), LATER)
    assert made is not None and not made["listed"]
    put_in = cash - ledger.balance(db, founders)
    assert put_in > 0 and ledger.amount_in_existence(db) == money_before          # nothing created: moved from the founders
    assert ledger.balance(db, founders, made["share_asset"]) == ledger.amount_in_existence(db, made["share_asset"])
    assert private.assets(db, made["id"]) and private.manager(db, made["id"])
    assert quarters.close_due_quarters(db, after_quarters(9)) == [9]
    r = _one(db, "SELECT * FROM company_results WHERE company_id = %s AND period = 9", (made["id"],))
    assert r and r["total_assets"] == r["total_liabilities"] + r["total_equity"]
    assert ledger.audit(db) == []


def test_pay_that_falls_behind_prices_brings_slow_work_and_then_a_walkout(db):
    empire, team = firm_of(db)
    company = own(db, empire, "ENI")
    calm = next(c for c in quarters.companies.load_companies(db) if c["id"] == company["id"])
    with db.transaction():
        private.before_close(db, [calm], 9, BPS)
    db.execute("UPDATE private_profiles SET morale_bps = 6000, last_pull_bps = %s WHERE company_id = %s", (calm["pull_bps"], company["id"]))
    loaded = next(c for c in quarters.companies.load_companies(db) if c["id"] == company["id"])
    with db.transaction():
        private.before_close(db, [loaded], 9, BPS)
    assert loaded["walkout"] and loaded["pull_bps"] < calm["pull_bps"] * 8 // 10          # customers go elsewhere
    db.execute("UPDATE private_profiles SET morale_bps = 8000 WHERE company_id = %s", (company["id"],))
    slow = next(c for c in quarters.companies.load_companies(db) if c["id"] == company["id"])
    labour = slow["labour_bps"]
    with db.transaction():
        private.before_close(db, [slow], 9, BPS)
    assert not slow.get("walkout") and slow["labour_bps"] > labour - 1000
    # While the founders owned it, its pay kept up with the going rate; now only the owners' pay rises keep it up.
    assert private.profile(db, company["id"])["pay_index_bps"] == _one(db, "SELECT wage_index_bps FROM economy_results WHERE period = 8")["wage_index_bps"]


def test_a_tax_bill_the_founders_hid_falls_due_as_tax_and_the_books_still_balance(db):
    c = _one(db, "SELECT * FROM companies WHERE ticker = 'UGS'")
    secrets = [{"code": "hidden_debt", "bps": 0, "amount": million_naira(500), "from_period": 9, "done": False}]
    db.execute("UPDATE private_profiles SET secrets = %s WHERE company_id = %s", (Jsonb(secrets), c["id"]))
    assert quarters.close_due_quarters(db, after_quarters(9)) == [9]
    r = _one(db, "SELECT * FROM company_results WHERE company_id = %s AND period = 9", (c["id"],))
    assert r["tax"] >= million_naira(500) and r["total_assets"] == r["total_liabilities"] + r["total_equity"]
    assert private.profile(db, c["id"])["secrets"][0]["done"]
    assert ledger.audit(db) == []


def test_rivals_answer_an_owned_companys_price_cut(db):
    empire, team = firm_of(db)
    company = own(db, empire, "MPK")
    firm_owned.set_dials(db, team["head"], company["id"], {"price_bps": 8500, "staff_bps": 10_000, "pay_rise_bps": 0, "marketing": 0, "technology": 0,
                                                           "maintenance_bps": 10_000, "payout_bps": 4000, "borrow": 0, "buy_assets": 0}, LATER)
    assert quarters.close_due_quarters(db, after_quarters(9)) == [9]
    rivals = _dicts(db, "SELECT price_bps FROM companies WHERE sector = 'consumer' AND id <> %s AND status = 'trading'", (company["id"],))
    sales = _dicts(db, "SELECT company_id, revenue FROM company_results r JOIN companies c ON c.id = r.company_id WHERE r.period = 9"
                       " AND c.sector = 'consumer' AND c.status = 'trading'")
    weight = min(max(next(r["revenue"] for r in sales if r["company_id"] == company["id"]), 0) * BPS * 2 // max(sum(max(r["revenue"], 0) for r in sales), 1), BPS)
    if weight >= private.RIVAL_NOTICE_BPS:
        assert all(r["price_bps"] < BPS for r in rivals)              # a company big enough is answered: half way towards the cut
    else:
        assert all(r["price_bps"] == BPS for r in rivals)             # a small one is not worth answering
    assert ledger.audit(db) == []


def test_the_league_tables_are_public_and_name_players_only_by_display_name(db, client):
    from tests.conftest import ADULT, join
    assert join(client, ADULT).status_code == 201
    seen = client.get("/api/deals/league").json()
    assert set(seen) == {"year", "biggest", "exits", "bankers"}
    assert "player_id" not in str(seen)
