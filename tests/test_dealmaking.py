"""Private equity stage, part 2B: firms players found, and the deal-making between empires."""

from __future__ import annotations

from datetime import timedelta

import pytest

from simulation import (corporate, empires, firm, firm_dealmaking, firm_deals, firm_money, firm_owned, firm_people, firm_practice, ledger, private,
                        quarters)
from simulation.money import BPS, million_naira, naira
from tests.conftest import after_quarters
from tests.test_builds import pro
from tests.test_careers import NOW9
from tests.test_deals import LATER, _dicts, _one, open_a_sale
from tests.test_deals_more import own
from tests.test_firm import firm_of, member
from tests.test_objectives import give_cash

pytestmark = pytest.mark.world("eight")
LATE = LATER + timedelta(hours=1)


def house(db, name, builds=("asset_manager", "investment_banker", "risk_manager"), cash_naira=20_000_000_000, tag=None):
    """A second empire run by players, with a member at each desk named."""
    tag = tag or name.split()[0].lower()
    head, _ = pro(db, "asset_manager", f"{tag}_head", level=20, cash_naira=60_000_000)
    empire = empires.found(db, head, name, million_naira(40), 0, NOW9)
    team = {"head": head}
    for build in builds:
        team[build] = member(db, empire, head, build, f"{tag}_{build}", level=10)
    empires.open_empire(db, head, NOW9)
    give_cash(db, empire["account_id"], cash_naira)
    return empires._empire(db, empire["id"]), team


def job_truth(db, job_id):
    terms = _one(db, "SELECT terms FROM firm_jobs WHERE id = %s", (job_id,))["terms"]
    return {a["key"]: terms["_truth"][a["key"]] / 100 if a["kind"] == "percent" else terms["_truth"][a["key"]] for a in terms["asks"]}


def cash(db, account):
    return ledger.balance(db, account)


# ---------------------------------------------------------------------------
# Firms players found
# ---------------------------------------------------------------------------

def test_a_firm_is_founded_from_a_seat_by_the_right_build_and_a_bank_needs_capital(db):
    other, team = house(db, "Delta Partners")
    with pytest.raises(empires.EmpireError, match="founded by an Accountant"):
        firm_practice.found(db, team["investment_banker"], "audit", "Wrong Audit", 0, LATER)
    made = firm_practice.found(db, team["asset_manager"], "audit", "Creek Audit", 0, LATER)
    assert made["firm_id"]
    with pytest.raises(empires.EmpireError, match="already run a firm"):
        firm_practice.found(db, team["asset_manager"], "audit", "Creek Audit Two", 0, LATER)
    with pytest.raises(empires.EmpireError, match="capital"):
        firm_practice.found(db, team["head"], "bank", "Creek Bank", naira(1_000_000), LATER)
    loner, _ = pro(db, "risk_manager", "loner", level=10, cash_naira=1_000_000)
    with pytest.raises(empires.EmpireError, match="seat"):
        firm_practice.found(db, loner, "risk", "Loner Risk", 0, LATER)
    before = ledger.amount_in_existence(db)
    give_cash(db, ledger.player_account_id(db, team["head"]), 60_000_000)
    bank = firm_practice.found(db, team["head"], "bank", "Creek Bank", million_naira(50), LATER)
    f = _one(db, "SELECT * FROM pro_firms WHERE id = %s", (bank["firm_id"],))
    assert cash(db, f["account_id"]) == million_naira(50) and f["capital"] == million_naira(50)
    assert ledger.amount_in_existence(db) == before                          # moved from the Treasury, not made
    seen = firm_practice.firms(db)
    assert {x["name"] for x in seen} == {"Creek Audit", "Creek Bank"} and "founder_id" not in str(seen)


def test_an_empire_sends_a_check_to_an_outside_firm_which_does_it_and_is_paid_sixty_forty(db):
    empire, team = firm_of(db, n_cash=60_000_000_000)
    other, them = house(db, "Delta Partners")
    audit = firm_practice.found(db, them["asset_manager"], "audit", "Creek Audit", 0, LATER)["firm_id"]
    sale = open_a_sale(db)
    file_id = firm_deals.open_file(db, team["investment_banker"], sale["id"], LATER)["file_id"]
    step = _one(db, "SELECT * FROM deal_steps WHERE file_id = %s AND step = 'accounts'", (file_id,))
    with pytest.raises(empires.EmpireError, match="confidentiality"):
        firm_practice.send_step(db, team["head"], step["id"], audit, million_naira(5), LATER)
    firm_deals.sign_nda(db, team["investment_banker"], file_id, LATER)
    with pytest.raises(empires.EmpireError, match="head"):
        firm_practice.send_step(db, team["asset_manager"], step["id"], audit, million_naira(5), LATER)
    job = firm_practice.send_step(db, team["head"], step["id"], audit, million_naira(5), LATER)["job_id"]
    with pytest.raises(empires.EmpireError, match="outside firm"):
        firm_deals.open_step(db, team["asset_manager"], step["id"], LATER)
    opened = firm_practice.open_job(db, them["asset_manager"], job, LATER)
    assert "_truth" not in str(opened)
    founder_before, house_before, buyer_before = (cash(db, ledger.player_account_id(db, them["asset_manager"])), cash(db, other["account_id"]),
                                                  cash(db, empire["account_id"]))
    done = firm_practice.hand_in_job(db, them["asset_manager"], job, job_truth(db, job), LATE)
    assert done["score"] == 100
    assert _one(db, "SELECT status, done_by FROM deal_steps WHERE id = %s", (step["id"],))["status"] == "done"
    assert cash(db, empire["account_id"]) == buyer_before - million_naira(5)
    assert cash(db, other["account_id"]) - house_before == million_naira(3)               # 60% to the founder's empire
    assert cash(db, ledger.player_account_id(db, them["asset_manager"])) - founder_before == million_naira(2)
    assert _one(db, "SELECT reputation, jobs_done FROM pro_firms WHERE id = %s", (audit,)) == {"reputation": 51, "jobs_done": 1}
    seen = firm.view(db, team["head"], LATE)["deals"]
    mine = next(s for s in seen["sales"] if s["id"] == sale["id"])
    assert next(s for s in mine["file"]["steps"] if s["step"] == "accounts")["by"] == "Creek Audit (outside firm)"
    assert ledger.audit(db) == []


def test_founders_have_a_company_on_sale_audited_and_buyers_see_the_opinion(db):
    other, them = house(db, "Delta Partners")
    audit = firm_practice.found(db, them["asset_manager"], "audit", "Creek Audit", 0, LATER)["firm_id"]
    dressed = _one(db, "SELECT c.ticker FROM private_profiles p JOIN companies c ON c.id = p.company_id WHERE p.secrets @> '[{\"code\": \"dressed_revenue\"}]'"
                       " AND c.status = 'trading' AND NOT EXISTS (SELECT 1 FROM sale_processes s WHERE s.company_id = c.id AND s.status = 'open')"
                       " ORDER BY c.ticker LIMIT 1")
    sale = open_a_sale(db, dressed["ticker"])
    job = _one(db, "SELECT * FROM firm_jobs WHERE process_id = %s AND kind = 'audit'", (sale["id"],))
    assert job and job["firm_id"] == audit
    firm_practice.open_job(db, them["asset_manager"], job["id"], LATER)
    right = job_truth(db, job["id"])
    assert right["opinion"] == "refused"
    # Signing dressed-up accounts clean is the worst thing an auditor can do: its name suffers badly.
    with db.transaction(force_rollback=True):
        firm_practice.hand_in_job(db, them["asset_manager"], job["id"], {**right, "opinion": "clean"}, LATE)
        assert _one(db, "SELECT reputation FROM pro_firms WHERE id = %s", (audit,))["reputation"] <= 50 - 15
    firm_practice.hand_in_job(db, them["asset_manager"], job["id"], right, LATE)
    empire, team = firm_of(db, n_cash=60_000_000_000)
    file_id = firm_deals.open_file(db, team["investment_banker"], sale["id"], LATE)["file_id"]
    firm_deals.sign_nda(db, team["investment_banker"], file_id, LATE)
    room = firm.view(db, team["head"], LATE)["deals"]
    seen = next(s for s in room["sales"] if s["id"] == sale["id"])["file"]["data_room"]["audit"]
    assert seen == {"firm": "Creek Audit", "reputation": 51, "status": "done", "opinion": "refused"}


def test_an_advisory_firm_runs_a_sale_its_pitch_book_lifts_bids_and_it_is_paid_on_success(db):
    other, them = house(db, "Delta Partners")
    advisory = firm_practice.found(db, them["investment_banker"], "advisory", "Creek Advisory", 0, LATER)["firm_id"]
    big = _one(db, "SELECT c.ticker FROM companies c WHERE NOT c.listed AND c.status = 'trading' AND NOT EXISTS (SELECT 1 FROM sale_processes s"
                   " WHERE s.company_id = c.id AND s.status = 'open') ORDER BY c.ticker LIMIT 1")
    sale = open_a_sale(db, big["ticker"])
    job = _one(db, "SELECT * FROM firm_jobs WHERE process_id = %s AND kind = 'mandate'", (sale["id"],))
    if sale["asking"] < firm_practice.MANDATE_ABOVE:
        assert job is None
        pytest.skip("This sale is too small for the founders to hire an adviser.")
    firm_practice.open_job(db, them["investment_banker"], job["id"], LATER)
    firm_practice.hand_in_job(db, them["investment_banker"], job["id"], job_truth(db, job["id"]), LATE)
    assert _one(db, "SELECT pitch_bps, adviser_firm_id FROM sale_processes WHERE id = %s", (sale["id"],)) == {
        "pitch_bps": firm_practice.PITCH_LIFT_BPS, "adviser_firm_id": advisory}
    founder_before = cash(db, ledger.player_account_id(db, them["investment_banker"]))
    assert quarters.close_due_quarters(db, after_quarters(9)) == [9]
    done = _one(db, "SELECT * FROM sale_processes WHERE id = %s", (sale["id"],))
    if done["status"] == "sold":
        fee = done["price"] * firm_practice.MANDATE_FEE_BPS // BPS
        assert cash(db, ledger.player_account_id(db, them["investment_banker"])) - founder_before >= fee - fee * 6 // 10 - 1
    assert ledger.audit(db) == []


def test_a_small_bank_lends_to_another_empire_and_is_paid_interest(db):
    empire, team = firm_of(db, n_cash=2_000_000_000)
    other, them = house(db, "Delta Partners")
    give_cash(db, ledger.player_account_id(db, them["head"]), 600_000_000)
    bank = firm_practice.found(db, them["head"], "bank", "Creek Bank", million_naira(500), LATER)["firm_id"]
    f = _one(db, "SELECT * FROM pro_firms WHERE id = %s", (bank,))
    with pytest.raises(empires.EmpireError, match="Central Bank"):
        firm_practice.offer_loan(db, them["head"], empire["id"], million_naira(100), 1, 4, LATER)
    with pytest.raises(empires.EmpireError, match="founder sits in"):
        firm_practice.offer_loan(db, them["head"], other["id"], million_naira(100), 2500, 4, LATER)
    offer = firm_practice.offer_loan(db, them["head"], empire["id"], million_naira(100), 2500, 4, LATER)["offer_id"]
    assert firm.view(db, team["head"], LATER)["practice"]["loan_offers"][0]["bank"] == "Creek Bank"
    firm_practice.answer_loan(db, team["head"], offer, True, LATER)
    debt = _one(db, "SELECT * FROM empire_debts WHERE empire_id = %s AND lender_account = %s", (empire["id"], f["account_id"]))
    assert debt["outstanding"] == million_naira(100) and cash(db, f["account_id"]) == million_naira(400)
    assert quarters.close_due_quarters(db, after_quarters(9)) == [9]
    assert cash(db, f["account_id"]) > million_naira(400)                    # interest came in
    assert ledger.audit(db) == []


def test_a_bank_stands_behind_a_listing_and_buys_what_the_public_does_not(db, monkeypatch):
    empire, team = firm_of(db)
    other, them = house(db, "Delta Partners")
    give_cash(db, ledger.player_account_id(db, them["head"]), 60_000_000_000)
    bank = firm_practice.found(db, them["head"], "bank", "Creek Bank", million_naira(50_000), LATER)["firm_id"]
    company = own(db, empire, "OPS")
    if firm_owned.failing(db, company["id"]) or _one(db, "SELECT net_profit FROM company_results WHERE company_id = %s ORDER BY period DESC LIMIT 1",
                                                     (company["id"],))["net_profit"] <= 0:
        pytest.skip("OPS is not profitable in this world.")
    firm_owned.list_on_exchange(db, team["head"], company["id"], LATER, bank)
    job = _one(db, "SELECT * FROM firm_jobs WHERE kind = 'underwriting' AND firm_id = %s", (bank,))
    firm_practice.accept_underwriting(db, them["head"], job["id"], LATER)
    offer = _one(db, "SELECT * FROM share_offers WHERE company_id = %s AND status = 'open'", (company["id"],))
    assert offer["underwriter_firm_id"] == bank
    # Nobody else wants the shares: the bank takes them all.
    monkeypatch.setattr("simulation.world_data.OFFER_FUNDS_SHARE_BPS", 0)
    monkeypatch.setattr("simulation.world_data.OFFER_PUBLIC_SHARE_BPS", 0)
    f = _one(db, "SELECT * FROM pro_firms WHERE id = %s", (bank,))
    assert quarters.close_due_quarters(db, after_quarters(10)) == [9, 10]
    done = _one(db, "SELECT * FROM share_offers WHERE id = %s", (offer["id"],))
    assert done["shares_sold"] == offer["shares"] and ledger.balance(db, f["account_id"], company["share_asset"]) == offer["shares"]
    assert "stood behind the offer" in done["outcome"]
    assert ledger.audit(db) == []


# ---------------------------------------------------------------------------
# Takeovers between empires
# ---------------------------------------------------------------------------

def target_of(db, empire_cash_naira=200_000_000_000):
    """A listed company small enough for a test empire to bid for, and outside banking and insurance."""
    return _one(db, "SELECT c.*, m.reference_price FROM companies c JOIN market_instruments m ON m.company_id = c.id WHERE c.listed"
                    " AND c.sector NOT IN ('banking', 'insurance') AND NOT EXISTS (SELECT 1 FROM takeovers t WHERE t.target_company_id = c.id"
                    " AND t.status = 'open') ORDER BY m.reference_price * (SELECT sum(b.balance) FROM ledger_balances b WHERE b.asset = c.share_asset)"
                    " LIMIT 1")


def test_an_empire_offers_for_a_listed_company_a_rival_tops_it_and_the_cash_is_held_and_handed_back(db):
    empire, team = firm_of(db, n_cash=200_000_000_000)
    other, them = house(db, "Delta Partners", cash_naira=200_000_000_000)
    target = target_of(db)
    issued = ledger.amount_in_existence(db, target["share_asset"])
    price = target["reference_price"] * 12 // 10
    shares = issued * 6 // 10
    before = ledger.amount_in_existence(db)
    drafted = firm_dealmaking.draft_offer(db, team["investment_banker"], target["id"], price, shares, LATER)
    held_before = cash(db, empire["account_id"])
    firm.decide(db, team["head"], drafted["approval_id"], True, "Worth it.", LATER)
    bid = corporate.bid_for(db, target["id"])
    assert bid["bidder_empire_id"] == empire["id"] and bid["reserved"] == price * shares
    assert cash(db, empire["account_id"]) == held_before - price * shares
    with pytest.raises(empires.EmpireError, match="5%"):
        firm_dealmaking.draft_offer(db, them["investment_banker"], target["id"], price + 1, shares, LATER)
    rival = firm_dealmaking.draft_offer(db, them["investment_banker"], target["id"], price * 106 // 100, shares, LATER)
    firm.decide(db, them["head"], rival["approval_id"], True, "We want it more.", LATER)
    assert cash(db, empire["account_id"]) == held_before                                 # handed back
    now_bid = corporate.bid_for(db, target["id"])
    assert now_bid["bidder_empire_id"] == other["id"] and now_bid["topped"] == bid["id"]
    assert _one(db, "SELECT status FROM takeovers WHERE id = %s", (bid["id"],))["status"] == "failed"
    assert ledger.amount_in_existence(db) == before and corporate.check_books(db) == []
    assert quarters.close_due_quarters(db, after_quarters(10)) == [9, 10]
    closed = _one(db, "SELECT * FROM takeovers WHERE id = %s", (now_bid["id"],))
    assert closed["status"] in ("won", "failed") and closed["reserved"] == 0
    if closed["status"] == "won":
        assert ledger.balance(db, other["account_id"], target["share_asset"]) == closed["bought"]
    assert ledger.audit(db) == [] and corporate.check_books(db) == []


def test_a_defence_that_holds_up_makes_the_board_reject_a_low_offer(db):
    empire, team = firm_of(db, n_cash=200_000_000_000)
    other, them = house(db, "Delta Partners")
    target = target_of(db)
    issued = ledger.amount_in_existence(db, target["share_asset"])
    # The defending empire holds 5% of the target.
    holder = _one(db, "SELECT account_id FROM share_owners WHERE company_id = %s ORDER BY shares DESC LIMIT 1", (target["id"],))["account_id"]
    with db.transaction():
        ledger.transfer(db, payer=holder, receiver=other["account_id"], amount=issued // 20 + 1000, asset=target["share_asset"], kind="test", memo="test")
    drafted = firm_dealmaking.draft_offer(db, team["investment_banker"], target["id"], target["reference_price"], issued * 6 // 10, LATER)
    firm.decide(db, team["head"], drafted["approval_id"], True, "A bargain.", LATER)
    bid = corporate.bid_for(db, target["id"])
    with pytest.raises(empires.EmpireError, match="own offer"):
        firm_dealmaking.open_defence(db, team["investment_banker"], bid["id"], LATER)
    opened = firm_dealmaking.open_defence(db, them["investment_banker"], bid["id"], LATER)
    assert "_truth" not in str(opened)
    terms = _one(db, "SELECT defence_terms FROM takeovers WHERE id = %s", (bid["id"],))["defence_terms"]
    done = firm_dealmaking.hand_in_defence(db, them["investment_banker"], bid["id"], {"value": terms["_truth"]["value"]}, LATE)
    assert done["score"] == 100
    after = _one(db, "SELECT * FROM takeovers WHERE id = %s", (bid["id"],))
    assert after["defence_value"] == terms["_truth"]["value"]
    if after["price"] < after["defence_value"]:
        assert after["hostile"]
        offered = corporate._computer_run_acceptances(db, after, corporate._investors(db))
        assert ledger.account_id(db, ledger.INVESTORS_FOUNDERS) not in offered
    with pytest.raises(empires.EmpireError, match="handed in"):
        firm_dealmaking.hand_in_defence(db, them["investment_banker"], bid["id"], {"value": 1}, LATE)


def test_a_stake_is_built_at_the_bell_below_thirty_percent_and_every_five_percent_is_made_public(db):
    empire, team = firm_of(db, n_cash=200_000_000_000)
    target = target_of(db)
    issued = ledger.amount_in_existence(db, target["share_asset"])
    with pytest.raises(empires.EmpireError, match="30%"):
        firm_dealmaking.start_stake(db, team["head"], target["id"], 3000, target["reference_price"], LATER)
    firm_dealmaking.start_stake(db, team["head"], target["id"], 1000, target["reference_price"] * 12 // 10, LATER)
    prog = _one(db, "SELECT * FROM stake_programmes WHERE empire_id = %s", (empire["id"],))
    assert prog["status"] == "running"
    with db.transaction():
        firm_dealmaking._build_stakes(db, LATE)
    order = _one(db, "SELECT * FROM market_orders WHERE account_id = %s AND company_id = %s AND side = 'buy'", (empire["account_id"], target["id"]))
    assert order and order["quantity"] <= issued * firm_dealmaking.STAKE_BELL_BPS // BPS + 1
    # Once 5% is held (here handed over for the test), it is made public at the bell.
    holder = _one(db, "SELECT account_id FROM share_owners WHERE company_id = %s AND account_id <> %s ORDER BY shares DESC LIMIT 1",
                  (target["id"], empire["account_id"]))["account_id"]
    with db.transaction():
        ledger.transfer(db, payer=holder, receiver=empire["account_id"], amount=issued * 6 // 100, asset=target["share_asset"], kind="test", memo="test")
        firm_dealmaking.disclose(db, LATE)
    assert _one(db, "SELECT bps FROM stake_disclosures WHERE empire_id = %s AND company_id = %s", (empire["id"], target["id"]))["bps"] == 500
    assert _one(db, "SELECT 1 FROM market_notices WHERE company_id = %s AND kind = 'stake_disclosed'", (target["id"],))
    assert _one(db, "SELECT 1 FROM news_items WHERE kind = 'stake_disclosed'")


def test_a_block_changes_hands_near_the_market_price_and_never_to_thirty_percent(db):
    empire, team = firm_of(db)
    other, them = house(db, "Delta Partners", cash_naira=200_000_000_000)
    target = target_of(db)
    issued = ledger.amount_in_existence(db, target["share_asset"])
    holder = _one(db, "SELECT account_id FROM share_owners WHERE company_id = %s ORDER BY shares DESC LIMIT 1", (target["id"],))["account_id"]
    with db.transaction():
        ledger.transfer(db, payer=holder, receiver=empire["account_id"], amount=issued // 10, asset=target["share_asset"], kind="test", memo="test")
    market = corporate._market_price(db, target["id"])
    with pytest.raises(empires.EmpireError, match="tenth of the market price"):
        firm_dealmaking.offer_block(db, team["head"], other["id"], target["id"], issued // 10, market * 2, LATER)
    block = firm_dealmaking.offer_block(db, team["head"], other["id"], target["id"], issued // 10, market, LATER)["block_id"]
    with pytest.raises(empires.EmpireError, match="no such block"):
        firm_dealmaking.answer_block(db, team["head"], block, True, LATER)
    before = (cash(db, empire["account_id"]), cash(db, other["account_id"]), ledger.amount_in_existence(db))
    firm_dealmaking.answer_block(db, them["head"], block, True, LATER)
    cost = issued // 10 * market
    assert cash(db, empire["account_id"]) == before[0] + cost and cash(db, other["account_id"]) == before[1] - cost
    assert ledger.balance(db, other["account_id"], target["share_asset"]) == issued // 10 and ledger.amount_in_existence(db) == before[2]
    with db.transaction():
        ledger.transfer(db, payer=holder, receiver=empire["account_id"], amount=issued // 4, asset=target["share_asset"], kind="test", memo="test")
    with pytest.raises(empires.EmpireError, match="30%"):
        firm_dealmaking.offer_block(db, team["head"], other["id"], target["id"], issued // 4, market, LATER)
    assert ledger.audit(db) == []


def test_a_truce_stops_poaching_and_offers_for_each_others_companies(db):
    empire, team = firm_of(db, n_cash=200_000_000_000)
    other, them = house(db, "Delta Partners")
    pact = empires.draft_pact(db, team["investment_banker"], other["id"], "truce", "We leave each other's people and companies alone.", LATER)
    empires.sign_pact(db, team["head"], pact["id"], LATER)
    empires.sign_pact(db, them["head"], pact["id"], LATER)
    assert empires.in_truce(db, empire["id"], other["id"])
    with pytest.raises(empires.EmpireError, match="truce"):
        firm_people.poach(db, team["head"], them["asset_manager"], naira(1_000_000), "Come over.", LATER)
    target = target_of(db)
    issued = ledger.amount_in_existence(db, target["share_asset"])
    holder = _one(db, "SELECT account_id FROM share_owners WHERE company_id = %s ORDER BY shares DESC LIMIT 1", (target["id"],))["account_id"]
    with db.transaction():
        ledger.transfer(db, payer=holder, receiver=other["account_id"], amount=issued // 4, asset=target["share_asset"], kind="test", memo="test")
    with pytest.raises(empires.EmpireError, match="truce"):
        firm_dealmaking.draft_offer(db, team["investment_banker"], target["id"], target["reference_price"] * 12 // 10, issued * 6 // 10, LATER)
    with pytest.raises(empires.EmpireError, match="truce"):
        firm_dealmaking.start_stake(db, team["head"], target["id"], 1000, target["reference_price"], LATER)


# ---------------------------------------------------------------------------
# Mergers, spin-offs, and the shadow side
# ---------------------------------------------------------------------------

def test_two_empires_merge_by_their_members_votes_and_every_owner_keeps_what_their_share_was_worth(db):
    empire, team = firm_of(db, n_cash=2_000_000_000)
    other, them = house(db, "Delta Partners", builds=("investment_banker", "risk_manager", "asset_manager"), cash_naira=1_000_000_000)
    company = own(db, other, "RWH")
    worth_a, worth_b = empires.worth(db, empire, LATER)["total"], empires.worth(db, other, LATER)["total"]
    value_b = {p["player_id"]: p["value"] for p in firm_money.partners(db, other, LATER)}
    money = ledger.amount_in_existence(db)
    firm.propose(db, team["head"], "merger", {"other_empire_id": other["id"]}, LATER)
    for member_id in (m["player_id"] for m in empires.humans(db, empire["id"]) if m["player_id"] != team["head"]):
        r = _one(db, "SELECT id FROM empire_resolutions WHERE empire_id = %s AND kind = 'merger' AND status = 'open'", (empire["id"],))
        if r:
            firm.vote(db, member_id, r["id"], True, LATER)
    combo = _one(db, "SELECT * FROM empire_combinations WHERE empire_id = %s", (empire["id"],))
    assert combo["status"] == "voting"
    firm.propose(db, them["head"], "merger_join", {"combination_id": combo["id"]}, LATER)
    r = _one(db, "SELECT * FROM empire_resolutions WHERE empire_id = %s AND kind = 'merger_join'", (other["id"],))
    if r["status"] == "open":
        firm.vote(db, them["investment_banker"], r["id"], True, LATER)
    assert _one(db, "SELECT status FROM empires WHERE id = %s", (other["id"],))["status"] == "merged"
    merged = empires._empire(db, empire["id"])
    assert cash(db, other["account_id"]) == 0 and ledger.amount_in_existence(db) == money
    assert _one(db, "SELECT empire_id FROM owned_companies WHERE company_id = %s", (company["id"],))["empire_id"] == empire["id"]
    assert empires.seat_of(db, them["head"])["empire_id"] == empire["id"]
    after = empires.worth(db, merged, LATER)["total"]
    assert abs(after - (worth_a + worth_b)) <= 2
    now_worth = {p["player_id"]: p["value"] for p in firm_money.partners(db, merged, LATER)}
    for player, value in value_b.items():
        assert abs(now_worth.get(player, 0) - value) <= max(value // 1000, 2)       # what their part was worth, give or take a rounding
    assert ledger.audit(db) == []


def test_a_company_is_split_off_into_a_new_empire_owned_by_the_same_owners(db):
    empire, team = firm_of(db, n_cash=2_000_000_000)
    company = own(db, empire, "RWH")
    payload = {"company_id": str(company["id"]), "new_name": "Ridge House", "new_head": str(team["investment_banker"]), "cash": million_naira(10)}
    with pytest.raises(empires.EmpireError, match="led by one of your members"):
        firm.propose(db, team["head"], "spinoff", {**payload, "new_head": str(team["head"])}, LATER)
    firm.propose(db, team["head"], "spinoff", payload, LATER)
    r = _one(db, "SELECT * FROM empire_resolutions WHERE empire_id = %s AND kind = 'spinoff'", (empire["id"],))
    for m in empires.humans(db, empire["id"]):
        if r["status"] == "open" and m["player_id"] not in (team["head"], team["investment_banker"]):
            firm.vote(db, m["player_id"], r["id"], True, LATER)
            r = _one(db, "SELECT * FROM empire_resolutions WHERE id = %s", (r["id"],))
    new = _one(db, "SELECT * FROM empires WHERE name = 'Ridge House'")
    assert new and new["head_player_id"] == team["investment_banker"]
    assert _one(db, "SELECT empire_id FROM owned_companies WHERE company_id = %s", (company["id"],))["empire_id"] == new["id"]
    assert cash(db, new["account_id"]) == million_naira(10)
    old_units = {u["holder_account"]: u["units"] for u in _dicts(db, "SELECT * FROM empire_units WHERE empire_id = %s AND units > 0", (empire["id"],))}
    new_units = {u["holder_account"]: u["units"] for u in _dicts(db, "SELECT * FROM empire_units WHERE empire_id = %s", (new["id"],))}
    assert old_units == new_units
    assert ledger.audit(db) == []


def test_money_taken_out_of_an_owned_company_is_found_by_an_audit_firm_and_punished(db):
    empire, team = firm_of(db, n_cash=2_000_000_000)
    other, them = house(db, "Delta Partners")
    audit = firm_practice.found(db, them["asset_manager"], "audit", "Creek Audit", 0, LATER)["firm_id"]
    company = own(db, empire, "RWH")
    db.execute("UPDATE empire_seats SET signing_limit = %s WHERE player_id = %s", (million_naira(100), team["investment_banker"]))
    company_cash = cash(db, company["account_id"])
    amount = min(company_cash * firm_dealmaking.TAKE_MOST_BPS // BPS, million_naira(50))
    with pytest.raises(empires.EmpireError, match="does not control"):
        firm_dealmaking.take_from_company(db, them["investment_banker"], company["id"], amount, LATER)
    taken = firm_dealmaking.take_from_company(db, team["investment_banker"], company["id"], amount, LATER)
    assert cash(db, company["account_id"]) == company_cash - amount
    book = _one(db, "SELECT * FROM empire_books WHERE id = %s", (taken["book_id"],))
    assert not book["genuine"] and book["company_id"] == company["id"]
    job = firm_practice.commission_audit(db, team["head"], company["id"], audit, million_naira(2), LATER)["job_id"]
    firm_practice.open_job(db, them["asset_manager"], job, LATER)
    right = job_truth(db, job)
    assert right["consulting"] == amount and right["opinion"] == "refused"
    firm_practice.hand_in_job(db, them["asset_manager"], job, right, LATE)
    case = _one(db, "SELECT * FROM empire_cases WHERE book_id = %s", (book["id"],))
    assert case and case["player_id"] == team["investment_banker"]
    assert ledger.audit(db) == []


def test_a_head_drafting_at_an_empty_banker_desk_signs_the_offer_at_once(db):
    other, them = house(db, "Delta Partners", builds=("asset_manager", "risk_manager"), cash_naira=200_000_000_000)
    target = target_of(db)
    issued = ledger.amount_in_existence(db, target["share_asset"])
    done = firm_dealmaking.draft_offer(db, them["head"], target["id"], target["reference_price"] * 13 // 10, issued * 6 // 10, LATER)
    assert done["announced"] and corporate.bid_for(db, target["id"])["bidder_empire_id"] == other["id"]
    assert firm.view(db, them["head"], LATER)["dealmaking"]["offers"][0]["ours"]
    assert private.value_of(db, target["id"]) >= 0


def test_an_advisory_firm_restructures_a_failing_companys_loan_and_is_paid_only_if_it_works(db, monkeypatch):
    other, them = house(db, "Delta Partners")
    firm_practice.found(db, them["investment_banker"], "advisory", "Creek Advisory", 0, LATER)
    company = _one(db, "SELECT c.* FROM companies c JOIN company_debts d ON d.company_id = c.id AND d.kind = 'bank_loan' AND d.principal_outstanding > 0"
                       " WHERE NOT c.listed AND c.status = 'trading' AND NOT EXISTS (SELECT 1 FROM owned_companies o WHERE o.company_id = c.id)"
                       " ORDER BY c.ticker LIMIT 1")
    monkeypatch.setattr(firm_owned, "failing", lambda conn, company_id: True)
    job = firm_practice.propose_restructuring(db, them["investment_banker"], company["id"], million_naira(1), LATER)["job_id"]
    firm_practice.open_job(db, them["investment_banker"], job, LATER)
    terms = _one(db, "SELECT terms FROM firm_jobs WHERE id = %s", (job,))["terms"]
    debt = _one(db, "SELECT * FROM company_debts WHERE id = %s", (terms["debt_id"],))
    done = firm_practice.hand_in_job(db, them["investment_banker"], job, job_truth(db, job), LATE)
    after = _one(db, "SELECT * FROM company_debts WHERE id = %s", (terms["debt_id"],))
    if terms["_truth"]["cover"] >= 100:
        assert "accepted" in done["words"] and after["annual_rate_bps"] == terms["new_rate"] <= debt["annual_rate_bps"]
        assert after["maturity_period"] > debt["maturity_period"]
    else:
        assert after["annual_rate_bps"] == debt["annual_rate_bps"]
    assert ledger.audit(db) == []
