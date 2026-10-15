"""Private equity stage, part 2A: one test for each finding of the independent review, fixed."""

from __future__ import annotations

from datetime import timedelta

import pytest
from psycopg.types.json import Jsonb

from simulation import empires, firm_deals, firm_money, firm_owned, ledger, objectives, private, quarters
from simulation.money import BPS, million_naira
from tests.conftest import after_quarters
from tests.test_builds import pro
from tests.test_careers import NOW9
from tests.test_deals import LATER, _dicts, _one, do_checks, fairness_if_needed, open_a_sale
from tests.test_deals_more import own
from tests.test_firm import firm_of, member
from tests.test_objectives import give_cash

pytestmark = pytest.mark.world("eight")
AFTER9 = after_quarters(9) + timedelta(hours=2)


def second_empire(db, name="Second House", head_name="second", cash=30_000_000_000):
    head, _ = pro(db, "asset_manager", head_name, level=20, cash_naira=60_000_000)
    other = empires.found(db, head, name, million_naira(40), 0, NOW9)
    for build, who in (("journalist", f"{head_name}_j"), ("accountant", f"{head_name}_a")):
        member(db, other, head, build, who)
    other = empires.open_empire(db, head, NOW9)
    give_cash(db, other["account_id"], cash)
    return empires._empire(db, other["id"]), head


def filed(db, team, empire, ticker=None, mode="sealed", *, badly=()):
    sale = open_a_sale(db, ticker, mode=mode)
    file_id = firm_deals.open_file(db, team["investment_banker"], sale["id"], LATER)["file_id"]
    firm_deals.sign_nda(db, team["lawyer"], file_id, LATER)
    do_checks(db, empire, team, file_id, badly=badly)
    return sale, file_id


# f01: an auction re-bid counts the partners' pledges, so escrow holds exactly what it should.
def test_f01_a_rebid_at_auction_still_counts_the_partners(db):
    lead, team = firm_of(db, n_cash=60_000_000_000)
    other, other_head = second_empire(db)
    sale, file_id = filed(db, team, lead, mode="auction")
    pledge = sale["asking"] // 5
    invite = firm_deals.invite_partner(db, team["head"], file_id, other["id"], pledge, LATER)
    firm_deals.answer_partner(db, other_head, invite["partner_id"], True, LATER)
    first = firm_deals.place_bid(db, team["head"], file_id, sale["asking"], 0, LATER)
    again = firm_deals.place_bid(db, team["head"], file_id, sale["asking"] * 105 // 100, 0, LATER)
    assert first["partners"] == again["partners"] == pledge and again["equity"] == again["price"] - pledge
    assert firm_deals.check_books(db) == []
    assert quarters.close_due_quarters(db, after_quarters(9)) == [9]
    assert firm_deals.check_books(db) == [] and ledger.audit(db) == []


# f02: a resale keeps the new owner's cost; each holder's cost is its own.
def test_f02_the_buyers_cost_survives_the_sellers_exit(db):
    seller, team = firm_of(db, n_cash=60_000_000_000)
    company = own(db, seller, "ENI")
    buyer, buyer_head = second_empire(db, "Buyer House", "buyerhead")
    worth = private.value_of(db, company["id"])
    firm_owned.sell_to_empire(db, team["head"], company["id"], worth, worth * 8 // 10, "sealed", LATER)
    sale = _one(db, "SELECT * FROM sale_processes WHERE company_id = %s AND status = 'open'", (company["id"],))
    # The buying empire's bid, placed straight in (its checks are tested elsewhere).
    with db.transaction():
        db.execute("SELECT 1")
        offer = worth * 13 // 10
        bid = _one(db, "INSERT INTO deal_bids (process_id, empire_id, amount, equity, held, status, at) VALUES (%s, %s, %s, %s, %s, 'live', %s) RETURNING *",
                   (sale["id"], buyer["id"], offer, offer, offer, LATER))
        ledger.transfer(db, payer=buyer["account_id"], receiver=firm_deals.escrow_account(db), amount=offer, kind="deal_escrow", memo="test", period=9)
    assert quarters.close_due_quarters(db, after_quarters(10)) == [9, 10]          # a sale opened in a quarter is decided as the next closes
    if _one(db, "SELECT status FROM deal_bids WHERE id = %s", (bid["id"],))["status"] != "won":
        pytest.skip("A computer-run empire outbid the buyer.")
    owned = _one(db, "SELECT * FROM owned_companies WHERE company_id = %s", (company["id"],))
    assert owned["empire_id"] == buyer["id"] and owned["cost"] == offer
    assert _one(db, "SELECT cost FROM company_stakes WHERE company_id = %s AND empire_id = %s", (company["id"], buyer["id"]))["cost"] == offer
    x = _one(db, "SELECT * FROM deal_exits WHERE empire_id = %s", (seller["id"],))
    assert x["cost"] == million_naira(1_000) and x["kind"] == "to_empire"


# f03: answering a check wrongly on purpose does not let a buyer claim for what the check showed.
def test_f03_what_a_check_showed_is_known_even_if_answered_wrongly(db):
    empire, team = firm_of(db, n_cash=60_000_000_000)
    dressed = _one(db, "SELECT c.ticker FROM private_profiles p JOIN companies c ON c.id = p.company_id WHERE p.secrets @> '[{\"code\": \"dressed_revenue\"}]'"
                       " AND c.status = 'trading' ORDER BY c.ticker LIMIT 1")
    sale, file_id = filed(db, team, empire, dressed["ticker"], badly=("accounts",))
    assert _one(db, "SELECT 1 FROM deal_shown WHERE empire_id = %s AND code = 'dressed_revenue'", (empire["id"],))
    fairness_if_needed(db, team, file_id, sale["asking"] * 13 // 10)
    firm_deals.place_bid(db, team["head"], file_id, sale["asking"] * 13 // 10, 0, LATER)
    assert quarters.close_due_quarters(db, after_quarters(9)) == [9]
    deal = _one(db, "SELECT * FROM deals WHERE empire_id = %s", (empire["id"],))
    if deal is None:
        pytest.skip("Outbid.")
    with pytest.raises(empires.EmpireError, match="priced in"):
        firm_deals.claim(db, team["lawyer"], deal["id"], "dressed_revenue", AFTER9)


# f04: a worn-assets claim is measured at the sale, not after the buyer's own neglect.
def test_f04_the_worn_assets_claim_is_fixed_at_the_sale(db):
    deal = {"conditions": {"1": 4000}, "company_id": None, "period": 9}
    secret = {"code": "worn_assets"}
    rows = [{"id": 1, "cost": 1_000_000, "stated_bps": 9000, "condition_bps": 100, "bought_period": 0}]
    original = private.assets
    private.assets = lambda conn, company_id, all_=False: rows
    try:
        assert firm_deals._harm(db, deal, secret) == 1_000_000 * 5000 // BPS
    finally:
        private.assets = original


# f05: an ownership claim made good under the indemnity cannot be claimed again.
def test_f05_no_second_payment_for_an_ownership_claim(db):
    empire, team = firm_of(db, n_cash=60_000_000_000)
    company = _one(db, "SELECT * FROM companies WHERE ticker = 'JPG'")
    secrets = [{"code": "ownership_claim", "bps": 800, "amount": 0, "from_period": None, "done": True}]
    db.execute("UPDATE private_profiles SET secrets = %s WHERE company_id = %s", (Jsonb(secrets), company["id"]))
    sale = open_a_sale(db, "JPG")
    with db.transaction():
        bid = _one(db, "INSERT INTO deal_bids (process_id, empire_id, amount, status, at) VALUES (%s, %s, 1, 'won', %s) RETURNING id",
                   (sale["id"], empire["id"], LATER))
        deal = _one(db, "INSERT INTO deals (process_id, bid_id, company_id, empire_id, seller_account, price, shares, escrow, escrow_until, terms, period, at)"
                        " VALUES (%s, %s, %s, %s, %s, %s, %s, 0, 13, %s, 9, %s) RETURNING *",
                    (sale["id"], bid["id"], company["id"], empire["id"], sale["seller_account"], million_naira(1000), sale["shares"],
                     Jsonb({"title_warranty": True, "title_indemnity": True}), LATER))
        db.execute("INSERT INTO deal_finds (empire_id, company_id, code, how, at) VALUES (%s, %s, 'ownership_claim', 'Came to court', %s)",
                   (empire["id"], company["id"], LATER + timedelta(hours=1)))
    out = firm_deals.claim(db, team["lawyer"], deal["id"], "ownership_claim", LATER + timedelta(hours=2))
    assert out["paid"] == 0 and "already made good" in out["words"]


# f06: a wound-up company is worth nothing, and its shares cannot be sold to anyone for cash.
def test_f06_a_company_wound_up_is_worth_nothing(db):
    empire, team = firm_of(db)
    company = own(db, empire, "KNP")
    last = _one(db, "SELECT * FROM company_results WHERE company_id = %s ORDER BY period DESC LIMIT 1", (company["id"],))
    with db.transaction():
        firm_owned._wind_up(db, _one(db, "SELECT * FROM companies WHERE id = %s", (company["id"],)), last, 9, AFTER9)
    assert private.value_of(db, company["id"]) == 0
    assert objectives.private_share(db, company["id"])["price"] == 0
    debt = {"company_id": company["id"], "outstanding": 1, "rate_bps": 0, "covenants": {}}
    assert firm_deals.covenant_test(db, debt) == ["The company that secured the loan has failed."]
    funds = ledger.account_id(db, ledger.INVESTORS_INSTITUTIONS)
    cash = ledger.balance(db, funds)
    with db.transaction():
        took = firm_deals.enforce_security(db, empire, {**debt, "lender_account": funds, "lender_name": "x"}, 10**9, 9, AFTER9)
    assert took == 0 and ledger.balance(db, funds) == cash


# f07: a player in a computer-run empire cannot run that empire's companies.
def test_f07_computer_run_empires_companies_are_run_by_the_computer(db):
    computer = _one(db, "SELECT * FROM empires WHERE kind = 'computer' ORDER BY id LIMIT 1")
    company = own(db, computer, "ACL")
    player, _ = pro(db, "asset_manager", "joiner", level=4)
    empires.apply(db, player, computer["id"], NOW9)
    with pytest.raises(empires.EmpireError, match="computer"):
        firm_owned.set_dials(db, player, company["id"], {"price_bps": 7000}, LATER)


# f08: borrowing and new assets apply to the quarter they were set for; a new owner does not inherit dials.
def test_f08_one_off_dials_do_not_repeat_and_are_not_inherited(db):
    empire, team = firm_of(db)
    company = own(db, empire, "OJH")
    dials = {"price_bps": 10_000, "staff_bps": 10_000, "pay_rise_bps": 0, "marketing": 0, "technology": 0, "maintenance_bps": 10_000,
             "payout_bps": 4000, "borrow": million_naira(10), "buy_assets": 2}
    firm_owned.set_dials(db, team["head"], company["id"], dials, LATER)
    for period, expect in ((9, True), (10, False)):
        c = next(x for x in quarters.companies.load_companies(db) if x["id"] == company["id"])
        with db.transaction():
            private.before_close(db, [c], period, BPS)
        assert bool(c.get("borrow_wanted")) == expect and bool(c.get("extra_capex")) == expect
    db.execute("UPDATE owned_companies SET since = %s WHERE company_id = %s", (LATER + timedelta(minutes=5), company["id"]))
    assert private.dials_for(db, company["id"], 9) is None


# f09: no hidden figure in a refusal, the bank's offer, or the data room.
def test_f09_refusals_and_offers_do_not_reveal_the_private_figures(db):
    empire, team = firm_of(db, n_cash=60_000_000_000)
    sale, file_id = filed(db, team, empire)
    with pytest.raises(empires.EmpireError) as refused:
        firm_deals.place_bid(db, team["head"], file_id, sale["asking"] * 10, 0, LATER)
    assert "₦" not in str(refused.value)
    with pytest.raises(empires.EmpireError) as too_much:
        firm_deals.place_bid(db, team["head"], file_id, sale["asking"], sale["asking"], LATER)
    assert "₦" not in str(too_much.value)
    papers = private.papers(db, sale["company_id"])
    quote = firm_deals.loan_quote(db, sale, sale["asking"], 9)
    from_papers = sum(p["operating_profit"] + p["depreciation"] for p in papers) * 4 // len(papers)
    assert quote["most"] in (0, min(sale["asking"] * 6 // 10, from_papers * 4))


# f10: a lender's forced sale is at the buyer's usual price; with no buyer, the bank keeps the shares.
def test_f10_a_forced_sale_gets_no_better_price_than_a_willing_one(db):
    empire, team = firm_of(db)
    company = own(db, empire, "OPO")
    offer = firm_owned.buyer_offer(db, company["id"])
    held = ledger.balance(db, empire["account_id"], company["share_asset"])
    bank = firm_money._lender_bank(db, 9, 1)
    debt = {"company_id": company["id"], "lender_account": bank["account_id"], "lender_name": bank["name"]}
    with db.transaction():
        took = firm_deals.enforce_security(db, empire, debt, 10**15, 9, AFTER9)
    assert took == offer["per_share"] * held or (offer["per_share"] * held > offer["cash"] and took == 0)
    x = _one(db, "SELECT * FROM deal_exits WHERE empire_id = %s", (empire["id"],))
    assert x["forced"] and x["kind"] == "to_buyer"


# f11: one rescue a year; no do-nothing measures; nobody from the owning empire is the doctor.
def test_f11_rescues_cannot_be_farmed(db):
    empire, team = firm_of(db)
    trouble = next((c for c in _dicts(db, "SELECT * FROM companies WHERE NOT listed AND status = 'trading' ORDER BY ticker")
                    if firm_owned.failing(db, c["id"])), None)
    assert trouble is not None, "the world should have a private company in trouble"
    company = own(db, empire, trouble["ticker"])
    with pytest.raises(empires.EmpireError, match="from outside"):
        firm_owned.propose_rescue(db, team["accountant"], company["id"], ["cut_costs"], 0, LATER)
    doctor, _ = pro(db, "accountant", "outside_doctor")
    if not firm_owned._measure_applies(db, company["id"], "sell_grounded", 9):
        with pytest.raises(empires.EmpireError, match="change nothing"):
            firm_owned.propose_rescue(db, doctor, company["id"], ["sell_grounded"], 0, LATER)
    firm_owned.propose_rescue(db, doctor, company["id"], ["cut_costs"], 0, LATER)
    firm_owned.answer_rescue(db, team["head"], _one(db, "SELECT id FROM company_plans WHERE company_id = %s AND kind = 'rescue'", (company["id"],))["id"],
                             True, LATER)
    with pytest.raises(empires.EmpireError, match="one rescue a year"):
        firm_owned.propose_rescue(db, doctor, company["id"], ["cut_costs"], 0, LATER)


# f12: a small owned company's price cut barely moves the industry.
def test_f12_rivals_answer_in_proportion_to_the_undercutters_size(db):
    empire, team = firm_of(db)
    small = own(db, empire, "ABP") if _one(db, "SELECT 1 FROM companies WHERE ticker = 'ABP'") else own(db, empire, "OWR")
    firm_owned.set_dials(db, team["head"], small["id"], {"price_bps": 7000, "staff_bps": 10_000, "pay_rise_bps": 0, "marketing": 0, "technology": 0,
                                                         "maintenance_bps": 10_000, "payout_bps": 4000, "borrow": 0, "buy_assets": 0}, LATER)
    with db.transaction():
        private._rivals_answer_prices(db, 8)
    rivals = _dicts(db, "SELECT price_bps FROM companies WHERE sector = %s AND id <> %s", (small["sector"], small["id"]))
    assert all(r["price_bps"] >= 9500 for r in rivals)


# f13: a computer-run seller answers the buyer's changes at once, as the founders do.
def test_f13_a_computer_run_seller_answers_at_once(db):
    empire, team = firm_of(db, n_cash=60_000_000_000)
    computer = _one(db, "SELECT * FROM empires WHERE kind = 'computer' ORDER BY id LIMIT 1")
    company = own(db, computer, "MPH")
    with db.transaction():
        sale_id = private.start_sale(db, company["id"], computer["account_id"], computer["id"],
                                     ledger.balance(db, computer["account_id"], company["share_asset"]), 8, private._seed(db), NOW9)
    file_id = firm_deals.open_file(db, team["investment_banker"], sale_id, LATER)["file_id"]
    firm_deals.sign_nda(db, team["lawyer"], file_id, LATER)
    firm_deals.mark_terms(db, team["lawyer"], file_id, {"escrow": "ask"}, LATER)
    assert firm_deals.in_force(db, sale_id, empire["id"]).get("escrow")


# f14: a company is listed or sold, never both at once.
def test_f14_no_listing_while_on_sale(db):
    empire, team = firm_of(db)
    company = own(db, empire, "BID")
    worth = private.value_of(db, company["id"])
    firm_owned.sell_to_empire(db, team["head"], company["id"], worth, worth, "sealed", LATER)
    with pytest.raises(empires.EmpireError, match="sold or listed|profitable"):
        firm_owned.list_on_exchange(db, team["head"], company["id"], LATER)
    with pytest.raises(empires.EmpireError, match="on sale"):
        firm_owned.sell_to_buyer(db, team["head"], company["id"], LATER)


# f15: loans promised in other live bids count against what the empire may borrow.
def test_f15_two_bids_cannot_borrow_twice_the_room(db):
    empire, team = firm_of(db, n_cash=60_000_000_000)
    room = firm_money.gearing_room(db, empire, LATER)
    first, file_one = filed(db, team, empire)
    elsewhere = open_a_sale(db)
    if elsewhere["id"] == first["id"]:
        elsewhere = open_a_sale(db, _one(db, "SELECT c.ticker FROM companies c WHERE NOT c.listed AND c.status = 'trading' AND NOT EXISTS"
                                             " (SELECT 1 FROM sale_processes s WHERE s.company_id = c.id AND s.status = 'open') ORDER BY c.ticker LIMIT 1")["ticker"])
    db.execute("INSERT INTO deal_bids (process_id, empire_id, amount, loan, status, at) VALUES (%s, %s, 1, %s, 'live', %s)",
               (elsewhere["id"], empire["id"], room * 10, LATER))
    quote = firm_deals.loan_quote(db, first, first["asking"], 9)
    if quote["most"] == 0:
        pytest.skip("No bank lends against this company.")
    with pytest.raises(empires.EmpireError, match="owe more"):
        firm_deals.place_bid(db, team["head"], file_one, first["asking"], quote["most"], LATER)


# f16: once a buyer has bid, the selling empire cannot change the agreement it bid on.
def test_f16_no_seller_answers_after_the_bid(db):
    seller, team = firm_of(db, n_cash=60_000_000_000)
    company = own(db, seller, "MTH")
    worth = private.value_of(db, company["id"])
    firm_owned.sell_to_empire(db, team["head"], company["id"], worth, worth, "sealed", LATER)
    sale = _one(db, "SELECT * FROM sale_processes WHERE company_id = %s AND status = 'open'", (company["id"],))
    buyer, _ = second_empire(db, "Bidder House", "bidder")
    db.execute("INSERT INTO deal_terms (process_id, empire_id, code, status, charge_bps, at) VALUES (%s, %s, 'escrow', 'asked', 100, %s)",
               (sale["id"], buyer["id"], LATER))
    db.execute("INSERT INTO deal_bids (process_id, empire_id, amount, status, at) VALUES (%s, %s, %s, 'live', %s)", (sale["id"], buyer["id"], worth, LATER))
    with pytest.raises(empires.EmpireError, match="settled"):
        firm_deals.answer_terms(db, team["head"], sale["id"], buyer["id"], {"escrow": True}, LATER)


# f17: upkeep is read once; assets ordered and paid for arrive.
def test_f17_ordered_assets_arrive_and_upkeep_is_not_counted_twice(db):
    c = _one(db, "SELECT * FROM companies WHERE NOT listed AND status = 'trading' ORDER BY ticker LIMIT 1")
    unit = private._unit_cost(db, c["id"], 9)
    before = len(private.assets(db, c["id"]))
    company = {**c, "upkeep_bps": 0, "assets_ordered": 2, "extra_capex": unit * 2, "assets_paid": unit * 2}
    with db.transaction():
        private._wear(db, company, {"depreciation": 1000, "capital_spending": unit * 2, "revenue": 1}, 9, private._seed(db))
    assert len(private.assets(db, c["id"])) == before + 2


# f18: a rescue's dividend stop is a flag, not dial rows a buyer would inherit.
def test_f18_the_dividend_stop_leaves_no_dial_rows(db):
    c = _one(db, "SELECT * FROM companies WHERE ticker = 'KRF'")
    plan = {"id": 0, "company_id": c["id"], "code": "skip_dividends"}
    db.execute("INSERT INTO company_plans (id, company_id, kind, code, started_period, due_period, status, at) OVERRIDING SYSTEM VALUE"
               " VALUES (0, %s, 'rescue', 'skip_dividends', 9, 11, 'proposed', %s)", (c["id"], LATER))
    with db.transaction():
        firm_owned._start_rescue(db, plan, 9, LATER)
    assert not _one(db, "SELECT 1 FROM company_dials WHERE company_id = %s", (c["id"],))
    assert private.profile(db, c["id"])["no_dividend_until"] == 10
    loaded = next(x for x in quarters.companies.load_companies(db) if x["id"] == c["id"])
    with db.transaction():
        private.before_close(db, [loaded], 9, BPS)
    assert loaded["payout_bps"] == 0


# f19: money held back and paid on later counts in the selling empire's gain.
def test_f19_escrow_released_later_is_part_of_the_gain(db):
    seller, team = firm_of(db)
    company = own(db, seller, "EFD")
    pot = firm_deals.escrow_account(db)
    with db.transaction():
        firm_owned.exited(db, seller["id"], company["id"], "to_empire", million_naira(900), 9, LATER)
        ledger.transfer(db, payer=ledger.account_id(db, ledger.INVESTORS_FOUNDERS), receiver=pot, amount=million_naira(100), kind="test", memo="t", period=9)
        sale = _one(db, "SELECT * FROM sale_processes ORDER BY id LIMIT 1")
        bid = _one(db, "INSERT INTO deal_bids (process_id, empire_id, amount, status, at) VALUES (%s, %s, 1, 'won', %s) RETURNING id",
                   (sale["id"], seller["id"], LATER))
        db.execute("INSERT INTO deals (process_id, bid_id, company_id, empire_id, seller_account, price, shares, escrow_account, escrow, escrow_until,"
                   " period, at) VALUES (%s, %s, %s, %s, %s, 1, 1, %s, %s, 9, 9, %s)",
                   (sale["id"], bid["id"], company["id"], seller["id"], seller["account_id"], pot, million_naira(100), LATER))
        firm_deals._release_escrow(db, 9, AFTER9)
    x = _one(db, "SELECT * FROM deal_exits WHERE empire_id = %s", (seller["id"],))
    assert x["proceeds"] == million_naira(1_000) and x["gain"] == 0
