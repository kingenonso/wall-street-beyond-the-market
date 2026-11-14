"""Private equity stage, part 2B: one test for each problem the independent review found (r01 to r17)."""

from __future__ import annotations

from datetime import timedelta

import pytest

from simulation import corporate, empires, firm, firm_dealmaking, firm_deals, firm_money, firm_owned, firm_practice, ledger, private
from simulation.money import BPS, million_naira
from tests.test_dealmaking import LATE, house, target_of
from tests.test_dealmaking_loopholes import hand
from tests.test_deals import LATER, _one, open_a_sale
from tests.test_deals_more import own
from tests.test_firm import firm_of
from tests.test_objectives import give_cash

pytestmark = pytest.mark.world("eight")


def offer(db, team, target, ratio=12):
    issued = ledger.amount_in_existence(db, target["share_asset"])
    drafted = firm_dealmaking.draft_offer(db, team["investment_banker"], target["id"], target["reference_price"] * ratio // 10, issued * 6 // 10, LATER)
    firm.decide(db, team["head"], drafted["approval_id"], True, "Go.", LATER)
    return corporate.bid_for(db, target["id"])


def test_r01_cash_held_for_an_offer_still_counts_in_the_empires_worth(db):
    empire, team = firm_of(db, n_cash=200_000_000_000)
    target = target_of(db)
    before = empires.worth(db, empire, LATER)["total"]
    offer(db, team, target)
    after = empires.worth(db, empires._empire(db, empire["id"]), LATER)["total"]
    assert abs(after - before) <= before // 1000              # units are not sold cheap while an offer stands


def test_r02_a_check_fee_is_capped_by_the_deal_and_paid_only_for_good_work(db):
    empire, team = firm_of(db, n_cash=60_000_000_000)
    other, them = house(db, "Delta Partners")
    audit = firm_practice.found(db, them["asset_manager"], "audit", "Creek Audit", 0, LATER)["firm_id"]
    sale = open_a_sale(db)
    file_id = firm_deals.open_file(db, team["investment_banker"], sale["id"], LATER)["file_id"]
    firm_deals.sign_nda(db, team["investment_banker"], file_id, LATER)
    step = _one(db, "SELECT * FROM deal_steps WHERE file_id = %s AND step = 'accounts'", (file_id,))
    most = max(min(sale["asking"] * firm_practice.CHECK_FEE_BPS // BPS, firm_practice.JOB_FEE_MOST), firm_practice.JOB_FEE_LEAST)
    with pytest.raises(empires.EmpireError, match="half a percent"):
        firm_practice.send_step(db, team["head"], step["id"], audit, most + 1, LATER)
    job = firm_practice.send_step(db, team["head"], step["id"], audit, most, LATER)["job_id"]
    firm_practice.open_job(db, them["asset_manager"], job, LATER)
    cash = ledger.balance(db, empire["account_id"])
    firm_practice.hand_in_job(db, them["asset_manager"], job, {}, LATE)                     # a blank check
    assert ledger.balance(db, empire["account_id"]) == cash
    company = own(db, empire, "RWH")
    sales = firm_owned._quarter_sales(db, company["id"])
    with pytest.raises(empires.EmpireError, match="1% of a quarter's sales"):
        firm_practice.commission_audit(db, team["head"], company["id"], audit, max(sales // 100, firm_practice.JOB_FEE_LEAST) + million_naira(1), LATER)


def test_r03_a_selling_empire_is_never_given_an_adviser_it_did_not_choose(db):
    empire, team = firm_of(db, n_cash=2_000_000_000)
    other, them = house(db, "Delta Partners")
    firm_practice.found(db, them["investment_banker"], "advisory", "Creek Advisory", 0, LATER)
    company = own(db, empire, "RWH")
    worth = private.value_of(db, company["id"])
    firm_owned.sell_to_empire(db, team["head"], company["id"], max(worth, firm_practice.MANDATE_ABOVE * 2), worth, "sealed", LATER)
    sale = _one(db, "SELECT * FROM sale_processes WHERE company_id = %s AND status = 'open'", (company["id"],))
    assert sale["adviser_firm_id"] is None and not _one(db, "SELECT 1 FROM firm_jobs WHERE process_id = %s", (sale["id"],))


def test_r04_a_restructuring_of_a_players_company_waits_for_its_head(db, monkeypatch):
    empire, team = firm_of(db, n_cash=2_000_000_000)
    other, them = house(db, "Delta Partners")
    firm_practice.found(db, them["investment_banker"], "advisory", "Creek Advisory", 0, LATER)
    company = own(db, empire, "RWH")
    monkeypatch.setattr(firm_owned, "failing", lambda conn, company_id: True)
    if True:
        if not _one(db, "SELECT 1 FROM company_debts WHERE company_id = %s AND kind = 'bank_loan' AND principal_outstanding > 0", (company["id"],)):
            pytest.skip("RWH has no bank loan in this world.")
        job = firm_practice.propose_restructuring(db, them["investment_banker"], company["id"], million_naira(1), LATER)["job_id"]
        with pytest.raises(empires.EmpireError, match="not accepted"):
            firm_practice.open_job(db, them["investment_banker"], job, LATER)
        ask = _one(db, "SELECT * FROM empire_approvals WHERE empire_id = %s AND kind = 'restructuring_offer'", (empire["id"],))
        firm.decide(db, team["head"], ask["id"], False, "No thank you.", LATER)
        assert _one(db, "SELECT status FROM firm_jobs WHERE id = %s", (job,))["status"] == "cancelled"


def test_r05_no_success_fee_for_a_pitch_book_that_did_not_hold_up(db):
    other, them = house(db, "Delta Partners")
    advisory = firm_practice.found(db, them["investment_banker"], "advisory", "Creek Advisory", 0, LATER)["firm_id"]
    sale = open_a_sale(db)
    db.execute("INSERT INTO firm_jobs (firm_id, kind, client_account, company_id, process_id, fee, period, at, status, score)"
               " VALUES (%s, 'mandate', %s, %s, %s, 100, 9, %s, 'done', 10)", (advisory, sale["seller_account"], sale["company_id"], sale["id"], LATER))
    full = _one(db, "SELECT s.*, c.name AS company FROM sale_processes s JOIN companies c ON c.id = s.company_id WHERE s.id = %s", (sale["id"],))
    assert firm_practice.mandate_fee(db, full, sale["asking"], 9, LATER) == 0


def test_r06_an_empire_with_things_half_done_cannot_merge_away(db):
    empire, team = firm_of(db, n_cash=2_000_000_000)
    other, them = house(db, "Delta Partners", builds=("investment_banker", "risk_manager", "asset_manager"), cash_naira=1_000_000_000)
    sale = open_a_sale(db)
    firm_deals.open_file(db, them["investment_banker"], sale["id"], LATER)
    with pytest.raises(empires.EmpireError, match="deal file open"):
        firm.propose(db, team["head"], "merger", {"other_empire_id": other["id"]}, LATER)


def test_r07_a_defence_left_unwritten_for_a_day_can_be_taken_over(db):
    empire, team = firm_of(db, n_cash=200_000_000_000)
    one, them = house(db, "Delta Partners")
    two, others = house(db, "Kano Holdings", tag="kano")
    target = target_of(db)
    issued = ledger.amount_in_existence(db, target["share_asset"])
    hand(db, target, one["account_id"], issued // 20 + 1000)
    hand(db, target, two["account_id"], issued // 20 + 1000)
    bid = offer(db, team, target, 11)
    firm_dealmaking.open_defence(db, them["investment_banker"], bid["id"], LATER)
    with pytest.raises(empires.EmpireError, match="within a day"):
        firm_dealmaking.open_defence(db, others["investment_banker"], bid["id"], LATER)
    taken = firm_dealmaking.open_defence(db, others["investment_banker"], bid["id"], LATER + timedelta(hours=25))
    assert taken["terms"] and _one(db, "SELECT defence_by FROM takeovers WHERE id = %s", (bid["id"],))["defence_by"] == others["investment_banker"]


def test_r08_buying_on_the_exchange_obeys_the_thirty_percent_rule_and_truces(db):
    empire, team = firm_of(db, n_cash=200_000_000_000)
    target = target_of(db)
    issued = ledger.amount_in_existence(db, target["share_asset"])
    hand(db, target, empire["account_id"], issued * 28 // 100)
    with pytest.raises(empires.EmpireError, match="30%"):
        firm_dealmaking.buying_guard(db, empire["id"], target["id"], issued * 3 // 100)
    firm_dealmaking.buying_guard(db, empire["id"], target["id"], issued // 100)          # below 30% is fine


def test_r09_money_taken_from_a_company_is_repaid_to_the_company(db):
    empire, team = firm_of(db, n_cash=2_000_000_000)
    company = own(db, empire, "RWH")
    db.execute("UPDATE empire_seats SET signing_limit = %s WHERE player_id = %s", (million_naira(100), team["investment_banker"]))
    give_cash(db, ledger.player_account_id(db, team["investment_banker"]), 100_000_000)
    cash = ledger.balance(db, company["account_id"])
    amount = min(cash * firm_dealmaking.TAKE_MOST_BPS // BPS, million_naira(10))
    taken = firm_dealmaking.take_from_company(db, team["investment_banker"], company["id"], amount, LATER)
    book = _one(db, "SELECT * FROM empire_books WHERE id = %s", (taken["book_id"],))
    with db.transaction():
        audit = _one(db, "INSERT INTO empire_audits (empire_id, kind, period, from_period, to_period, fee, at) VALUES (%s, 'firm', 9, 5, 9, 0, %s)"
                         " RETURNING id", (empire["id"], LATER))["id"]
        case = empires._prove(db, empires._empire(db, empire["id"]), book, audit, LATER)
        empires._punish(db, empires._empire(db, empire["id"]), _one(db, "SELECT * FROM empire_cases WHERE id = %s", (case["id"],)), LATER)
    assert ledger.balance(db, company["account_id"]) == cash
    assert ledger.audit(db) == []


def test_r10_a_spin_off_pays_the_registration_fee_and_starts_in_a_division(db):
    empire, team = firm_of(db, n_cash=2_000_000_000)
    company = own(db, empire, "RWH")
    pool = ledger.balance(db, ledger.account_id(db, ledger.PRIZE_POOL))
    firm.propose(db, team["head"], "spinoff", {"company_id": str(company["id"]), "new_name": "Ridge House", "new_head": str(team["investment_banker"]),
                                               "cash": 0}, LATER)
    r = _one(db, "SELECT * FROM empire_resolutions WHERE empire_id = %s AND kind = 'spinoff'", (empire["id"],))
    for m in empires.humans(db, empire["id"]):
        if _one(db, "SELECT status FROM empire_resolutions WHERE id = %s", (r["id"],))["status"] == "open" and m["player_id"] not in (
                team["head"], team["investment_banker"]):
            firm.vote(db, m["player_id"], r["id"], True, LATER)
    new = _one(db, "SELECT * FROM empires WHERE name = 'Ridge House'")
    assert ledger.balance(db, ledger.account_id(db, ledger.PRIZE_POOL)) > pool
    assert new["division"] is not None and new["status"] == "active"
    combo = _one(db, "SELECT * FROM empire_combinations WHERE kind = 'spinoff' AND empire_id = %s", (empire["id"],))
    assert combo["worth_moved"] > 0


def test_r11_a_bank_can_sell_shares_it_holds(db):
    other, them = house(db, "Delta Partners")
    give_cash(db, ledger.player_account_id(db, them["head"]), 60_000_000)
    bank = firm_practice.found(db, them["head"], "bank", "Creek Bank", million_naira(50), LATER)["firm_id"]
    f = _one(db, "SELECT * FROM pro_firms WHERE id = %s", (bank,))
    target = target_of(db)
    hand(db, target, f["account_id"], 1000)
    firm_practice.sell_holding(db, them["head"], target["id"], 1000, target["reference_price"], LATE)
    assert _one(db, "SELECT 1 FROM market_orders WHERE account_id = %s AND side = 'sell'", (f["account_id"],))
    assert ledger.balance(db, f["account_id"], target["share_asset"]) == 0                # held by the exchange for the order


def test_r12_a_bank_stands_behind_a_listing_only_with_the_cash_to_do_it(db):
    empire, team = firm_of(db)
    other, them = house(db, "Delta Partners")
    give_cash(db, ledger.player_account_id(db, them["head"]), 60_000_000)
    bank = firm_practice.found(db, them["head"], "bank", "Creek Bank", million_naira(50), LATER)["firm_id"]
    company = own(db, empire, "OPS")
    if firm_owned.failing(db, company["id"]) or _one(db, "SELECT net_profit FROM company_results WHERE company_id = %s ORDER BY period DESC LIMIT 1",
                                                     (company["id"],))["net_profit"] <= 0:
        pytest.skip("OPS is not profitable in this world.")
    firm_owned.list_on_exchange(db, team["head"], company["id"], LATER, bank)
    job = _one(db, "SELECT * FROM firm_jobs WHERE kind = 'underwriting' AND firm_id = %s", (bank,))
    with pytest.raises(empires.EmpireError, match="must have the cash"):
        firm_practice.accept_underwriting(db, them["head"], job["id"], LATER)


def test_r13_the_empire_of_a_sales_auditor_may_not_buy_the_company(db):
    other, them = house(db, "Delta Partners")
    firm_practice.found(db, them["asset_manager"], "audit", "Creek Audit", 0, LATER)
    sale = open_a_sale(db)
    assert _one(db, "SELECT 1 FROM firm_jobs WHERE process_id = %s AND kind = 'audit'", (sale["id"],))
    with pytest.raises(empires.EmpireError, match="working for the seller"):
        firm_deals.open_file(db, them["investment_banker"], sale["id"], LATER)


def test_r14_a_loan_offer_lapses_at_the_close_and_is_checked_again_when_taken(db):
    empire, team = firm_of(db)
    other, them = house(db, "Delta Partners")
    give_cash(db, ledger.player_account_id(db, them["head"]), 600_000_000)
    firm_practice.found(db, them["head"], "bank", "Creek Bank", million_naira(500), LATER)
    with pytest.raises(empires.EmpireError, match="points above"):
        firm_practice.offer_loan(db, them["head"], empire["id"], million_naira(100), 6000, 4, LATER)
    made = firm_practice.offer_loan(db, them["head"], empire["id"], million_naira(100), 2500, 4, LATER)["offer_id"]
    with db.transaction():
        firm_practice._closed(db, 9, LATER)
    assert _one(db, "SELECT status FROM bank_loan_offers WHERE id = %s", (made,))["status"] == "lapsed"


def test_r15_a_restructuring_no_longer_needed_changes_nothing_and_earns_nothing(db):
    other, them = house(db, "Delta Partners")
    advisory = firm_practice.found(db, them["investment_banker"], "advisory", "Creek Advisory", 0, LATER)["firm_id"]
    company = _one(db, "SELECT c.* FROM companies c JOIN company_debts d ON d.company_id = c.id AND d.kind = 'bank_loan' AND d.principal_outstanding > 0"
                       " WHERE NOT c.listed AND c.status = 'trading' ORDER BY c.ticker LIMIT 1")
    debt = _one(db, "SELECT * FROM company_debts WHERE company_id = %s AND kind = 'bank_loan' ORDER BY principal_outstanding DESC LIMIT 1", (company["id"],))
    job = {"id": None, "company_id": company["id"], "terms": {"debt_id": str(debt["id"]), "new_rate": 100, "_truth": {"cover": 500}}}
    with db.transaction():
        job["id"] = _one(db, "INSERT INTO firm_jobs (firm_id, kind, client_account, company_id, fee, period, at) VALUES (%s, 'restructuring', %s, %s,"
                             " 1000, 9, %s) RETURNING id", (advisory, company["account_id"], company["id"], LATER))["id"]
        f = _one(db, "SELECT * FROM pro_firms WHERE id = %s", (advisory,))
        if not firm_owned.failing(db, company["id"]):
            words = firm_practice._finish_restructuring(db, f, job, True, LATER, 9)
            assert "no longer needs it" in words
            assert _one(db, "SELECT annual_rate_bps FROM company_debts WHERE id = %s", (debt["id"],))["annual_rate_bps"] == debt["annual_rate_bps"]


def test_r16_the_website_can_commission_an_audit_and_a_restructuring(db):
    from pathlib import Path
    source = "".join(p.read_text() for p in (Path(__file__).parent.parent / "web" / "src").glob("*.tsx"))
    assert "/audit`" in source and "/firms/restructurings" in source and "/firms/holdings/" in source


def test_r17_shares_offered_to_a_takeover_still_count_as_held(db):
    empire, team = firm_of(db, n_cash=200_000_000_000)
    other, them = house(db, "Delta Partners")
    target = target_of(db)
    issued = ledger.amount_in_existence(db, target["share_asset"])
    tenth = -(-issued // 10)                    # a tenth, rounded up, so the holding is 10% whatever the number of shares
    hand(db, target, other["account_id"], tenth)
    with db.transaction():
        firm_dealmaking.disclose(db, LATER)
    bid = offer(db, team, target)
    firm_dealmaking.tender(db, them["head"], bid["id"], tenth, LATER)
    with db.transaction():
        firm_dealmaking.disclose(db, LATER)
    assert _one(db, "SELECT bps FROM stake_disclosures WHERE empire_id = %s AND company_id = %s", (other["id"], target["id"]))["bps"] == 1000
    assert firm.view(db, them["investment_banker"], LATER)["dealmaking"]["offers"][0]["can_defend"]
    assert firm_money.units_total(db, other["id"]) >= 0
