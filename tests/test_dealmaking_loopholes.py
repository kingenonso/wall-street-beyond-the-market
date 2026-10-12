"""Private equity stage, part 2B: the ten-question loophole check, one test (or more) for each question.

Players may commit crimes against each other's empires, but never against the game: no money from
nowhere, no seeing what is hidden, no acting as somebody else, no beating the clock.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from simulation import corporate, empires, firm, firm_dealmaking, firm_deals, firm_owned, firm_practice, ledger, private, quarters
from simulation.money import million_naira
from tests.conftest import after_quarters
from tests.test_deals import LATER, _one, open_a_sale
from tests.test_dealmaking import LATE, house, target_of
from tests.test_deals_more import own
from tests.test_firm import firm_of
from tests.test_objectives import give_cash

pytestmark = pytest.mark.world("eight")


def hand(db, company, account, shares):
    holder = _one(db, "SELECT account_id FROM share_owners WHERE company_id = %s AND account_id <> %s ORDER BY shares DESC LIMIT 1",
                  (company["id"], account))["account_id"]
    with db.transaction():
        ledger.transfer(db, payer=holder, receiver=account, amount=shares, asset=company["share_asset"], kind="test", memo="test")


# 1. Can an empire pay a firm run by one of its own members, to move the empire's money to that member?
def test_q1_no_empire_hires_a_firm_run_from_inside_itself(db):
    empire, team = firm_of(db, n_cash=60_000_000_000)
    sale = open_a_sale(db)                     # opened before the firm exists, so it is not the sale's auditor
    own_firm = firm_practice.found(db, team["accountant"], "audit", "Inside Audit", 0, LATER)["firm_id"]
    file_id = firm_deals.open_file(db, team["investment_banker"], sale["id"], LATER)["file_id"]
    firm_deals.sign_nda(db, team["lawyer"], file_id, LATER)
    step = _one(db, "SELECT * FROM deal_steps WHERE file_id = %s AND step = 'accounts'", (file_id,))
    with pytest.raises(empires.EmpireError, match="not an outside firm"):
        firm_practice.send_step(db, team["head"], step["id"], own_firm, million_naira(5), LATER)
    company = own(db, empire, "RWH")
    with pytest.raises(empires.EmpireError, match="independent"):
        firm_practice.commission_audit(db, team["head"], company["id"], own_firm, million_naira(5), LATER)
    banker_firm = firm_practice.found(db, team["investment_banker"], "advisory", "Inside Advisory", 0, LATER)["firm_id"]
    value = private.value_of(db, company["id"])
    with pytest.raises(empires.EmpireError, match="not independent"):
        firm_owned.sell_to_empire(db, team["head"], company["id"], value, value, "sealed", LATER, banker_firm)


# 2. Can a takeover (topped, then closed) create money, or leave cash or shares held that nobody is owed?
def test_q2_offers_topped_and_closed_create_nothing_and_leave_nothing_held(db):
    empire, team = firm_of(db, n_cash=200_000_000_000)
    other, them = house(db, "Delta Partners", cash_naira=200_000_000_000)
    target = target_of(db)
    issued = ledger.amount_in_existence(db, target["share_asset"])
    hand(db, target, other["account_id"], issued // 20 + 1000)
    before = ledger.amount_in_existence(db)
    first = firm_dealmaking.draft_offer(db, team["investment_banker"], target["id"], target["reference_price"] * 12 // 10, issued * 6 // 10, LATER)
    firm.decide(db, team["head"], first["approval_id"], True, "Go.", LATER)
    bid = corporate.bid_for(db, target["id"])
    firm_dealmaking.tender(db, them["head"], bid["id"], issued // 20 + 1000, LATER)
    rival = firm_dealmaking.draft_offer(db, them["investment_banker"], target["id"], target["reference_price"] * 13 // 10, issued * 6 // 10, LATER)
    firm.decide(db, them["head"], rival["approval_id"], True, "Go.", LATER)
    new = corporate.bid_for(db, target["id"])
    # The shares the rival had offered to the first bid come back to it: nobody sells to its own offer.
    assert ledger.balance(db, other["account_id"], target["share_asset"]) == issued // 20 + 1000
    assert not _one(db, "SELECT 1 FROM takeover_tenders WHERE takeover_id = %s AND account_id = %s AND shares > 0", (new["id"], other["account_id"]))
    with pytest.raises(empires.EmpireError, match="own offer"):
        firm_dealmaking.tender(db, them["head"], new["id"], issued // 20, LATER)
    assert ledger.amount_in_existence(db) == before and corporate.check_books(db) == []
    assert quarters.close_due_quarters(db, after_quarters(10)) == [9, 10]
    # (Across a close the Central Bank's lending changes the money in existence; what matters is that every book balances.)
    assert corporate.check_books(db) == [] and ledger.audit(db) == []
    assert ledger.balance(db, corporate.bonds.held_account(db), target["share_asset"]) == 0


# 3. Can an empire offer far above a company's worth, to move its money to whoever holds the shares?
def test_q3_no_offer_far_above_the_market_and_the_companys_worth(db):
    empire, team = firm_of(db, n_cash=200_000_000_000)
    target = target_of(db)
    issued = ledger.amount_in_existence(db, target["share_asset"])
    # (Far above both the market price and what the company is worth, whichever is higher.)
    market = corporate._market_price(db, target["id"])
    ceiling = max(market, firm_dealmaking._worth_per_share(db, target["id"]) or market) * firm_dealmaking.OFFER_MOST_BPS // 10_000
    with pytest.raises(empires.EmpireError, match="moving the members' money out"):
        firm_dealmaking.draft_offer(db, team["investment_banker"], target["id"], ceiling + 100, issued * 6 // 10, LATER)
    with pytest.raises(empires.EmpireError, match="below the market price"):
        firm_dealmaking.draft_offer(db, team["investment_banker"], target["id"], target["reference_price"] // 2, issued * 6 // 10, LATER)


# 4. Can a block trade move money between empires (a price far from the market)?
def test_q4_a_block_is_priced_near_the_market_both_when_offered_and_when_taken(db):
    empire, team = firm_of(db)
    other, them = house(db, "Delta Partners", cash_naira=200_000_000_000)
    target = target_of(db)
    issued = ledger.amount_in_existence(db, target["share_asset"])
    hand(db, target, empire["account_id"], issued // 10)
    market = corporate._market_price(db, target["id"])
    with pytest.raises(empires.EmpireError, match="tenth"):
        firm_dealmaking.offer_block(db, team["head"], other["id"], target["id"], issued // 10, market // 3, LATER)
    block = firm_dealmaking.offer_block(db, team["head"], other["id"], target["id"], issued // 10, market * 109 // 100, LATER)["block_id"]
    db.execute("UPDATE market_instruments SET last_price = %s WHERE company_id = %s", (market // 2, target["id"]))   # the market falls
    with pytest.raises(empires.EmpireError, match="tenth"):
        firm_dealmaking.answer_block(db, them["head"], block, True, LATER)


# 5. Can an empire creep to control without making an offer to every owner?
def test_q5_no_stake_or_block_reaches_thirty_percent(db):
    empire, team = firm_of(db, n_cash=200_000_000_000)
    other, them = house(db, "Delta Partners", cash_naira=200_000_000_000)
    target = target_of(db)
    issued = ledger.amount_in_existence(db, target["share_asset"])
    with pytest.raises(empires.EmpireError, match="30%"):
        firm_dealmaking.start_stake(db, team["head"], target["id"], 3500, target["reference_price"], LATER)
    hand(db, target, empire["account_id"], issued * 2 // 10)
    hand(db, target, other["account_id"], issued * 15 // 100)
    with pytest.raises(empires.EmpireError, match="30%"):
        firm_dealmaking.offer_block(db, them["head"], empire["id"], target["id"], issued * 15 // 100, corporate._market_price(db, target["id"]), LATER)


# 6. Can anybody see what an audit, a pitch book or a defence is marked against, before handing it in?
def test_q6_the_truth_behind_jobs_and_defences_never_leaves_the_server(db, client):
    empire, team = firm_of(db, n_cash=200_000_000_000)
    other, them = house(db, "Delta Partners")
    firm_practice.found(db, them["accountant"], "audit", "Creek Audit", 0, LATER)
    sale = open_a_sale(db)
    job = _one(db, "SELECT * FROM firm_jobs WHERE process_id = %s AND kind = 'audit'", (sale["id"],))
    firm_practice.open_job(db, them["accountant"], job["id"], LATER)
    seen = firm.view(db, them["accountant"], LATER)
    assert "_truth" not in str(seen) and "secrets" not in str(seen["practice"])
    target = target_of(db)
    issued = ledger.amount_in_existence(db, target["share_asset"])
    hand(db, target, other["account_id"], issued // 10)
    done = firm_dealmaking.draft_offer(db, team["investment_banker"], target["id"], target["reference_price"] * 12 // 10, issued * 6 // 10, LATER)
    firm.decide(db, team["head"], done["approval_id"], True, "Go.", LATER)
    bid = corporate.bid_for(db, target["id"])
    firm_dealmaking.open_defence(db, them["investment_banker"], bid["id"], LATER)
    for who in (them["investment_banker"], team["head"], them["head"]):
        assert "_truth" not in str(firm.view(db, who, LATER))


# 7. Can a member act for a desk that is not theirs, a firm that is not theirs, or another empire?
def test_q7_each_act_belongs_to_its_desk_its_firm_and_its_empire(db):
    empire, team = firm_of(db, n_cash=200_000_000_000)
    other, them = house(db, "Delta Partners", cash_naira=200_000_000_000)
    target = target_of(db)
    issued = ledger.amount_in_existence(db, target["share_asset"])
    with pytest.raises(empires.EmpireError, match="Investment Banker"):
        firm_dealmaking.draft_offer(db, team["accountant"], target["id"], target["reference_price"] * 12 // 10, issued * 6 // 10, LATER)
    with pytest.raises(empires.EmpireError, match="Asset Manager"):
        firm_dealmaking.start_stake(db, team["lawyer"], target["id"], 1000, target["reference_price"], LATER)
    audit = firm_practice.found(db, them["accountant"], "audit", "Creek Audit", 0, LATER)["firm_id"]
    sale = open_a_sale(db)
    job = _one(db, "SELECT id FROM firm_jobs WHERE firm_id = %s", (audit,))
    with pytest.raises(empires.EmpireError, match="do not run a firm"):
        firm_practice.open_job(db, team["accountant"], job["id"], LATER)
    hand(db, target, empire["account_id"], issued // 10)
    block = firm_dealmaking.offer_block(db, team["head"], other["id"], target["id"], issued // 20, corporate._market_price(db, target["id"]), LATER)
    with pytest.raises(empires.EmpireError, match="head"):
        firm_dealmaking.answer_block(db, them["investment_banker"], block["block_id"], True, LATER)
    company = own(db, empire, "RWH")
    with pytest.raises(empires.EmpireError, match="does not control"):
        firm_dealmaking.take_from_company(db, them["accountant"], company["id"], million_naira(1), LATER)
    assert sale


# 8. Can anything be done in the minutes after a quarter has ended and before its books are closed?
def test_q8_nothing_is_done_between_the_end_of_a_quarter_and_its_close(db):
    empire, team = firm_of(db, n_cash=200_000_000_000)
    target = target_of(db)
    issued = ledger.amount_in_existence(db, target["share_asset"])
    ended = after_quarters(9) - timedelta(minutes=50)
    with pytest.raises(empires.EmpireError):
        firm_dealmaking.draft_offer(db, team["investment_banker"], target["id"], target["reference_price"] * 12 // 10, issued * 6 // 10, ended)
    with pytest.raises(empires.EmpireError):
        firm_practice.found(db, team["accountant"], "audit", "Late Audit", 0, ended)


# 9. Can an empire escape its debts, or a claim, by merging into another?
def test_q9_an_empire_with_debts_or_things_half_done_cannot_merge_away(db):
    empire, team = firm_of(db, n_cash=2_000_000_000)
    other, them = house(db, "Delta Partners", builds=("investment_banker", "lawyer"), cash_naira=1_000_000_000)
    db.execute("INSERT INTO empire_debts (empire_id, kind, lender_account, lender_name, principal, outstanding, rate_bps, taken_period, due_period, at)"
               " VALUES (%s, 'loan', %s, 'A bank', 100, 100, 1000, 9, 13, %s)", (other["id"], empire["account_id"], LATER))
    with pytest.raises(empires.EmpireError, match="repay its debts first"):
        firm.propose(db, team["head"], "merger", {"other_empire_id": other["id"]}, LATER)


# 10. Can a small bank lend money it does not have, or pay its founder's capital out as profit?
def test_q10_a_bank_lends_only_its_cash_and_pays_out_only_profit(db):
    empire, team = firm_of(db)
    other, them = house(db, "Delta Partners")
    give_cash(db, ledger.player_account_id(db, them["head"]), 60_000_000)
    bank = firm_practice.found(db, them["head"], "bank", "Creek Bank", million_naira(50), LATER)["firm_id"]
    with pytest.raises(empires.EmpireError, match="not that much cash"):
        firm_practice.offer_loan(db, them["head"], empire["id"], million_naira(60), 2500, 4, LATER)
    with pytest.raises(empires.EmpireError, match="profit that can be paid out"):
        firm_practice.pay_out(db, them["head"], million_naira(1), LATE)
    f = _one(db, "SELECT * FROM pro_firms WHERE id = %s", (bank,))
    assert ledger.balance(db, f["account_id"]) == million_naira(50)
