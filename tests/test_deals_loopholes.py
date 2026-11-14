"""Private equity stage, part 2A: the ten-question loophole check, one test (or more) for each question.

Players may commit crimes against each other's empires, but never against the game: no money from
nowhere, no seeing what is hidden, no acting as somebody else, no beating the clock.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from simulation import empires, exchange, firm, firm_deals, firm_owned, ledger, objectives, private, quarters
from tests.conftest import ADULT, after_quarters, join
from tests.test_deals import LATER, _dicts, _one, do_checks, fairness_if_needed, open_a_sale, truth
from tests.test_deals_more import own
from tests.test_builds import pro
from tests.test_careers import NOW9
from tests.test_firm import firm_of, member
from simulation.money import million_naira

pytestmark = pytest.mark.world("eight")


def ready(db, ticker=None, mode="sealed"):
    empire, team = firm_of(db, n_cash=60_000_000_000)
    sale = open_a_sale(db, ticker, mode=mode)
    file_id = firm_deals.open_file(db, team["investment_banker"], sale["id"], LATER)["file_id"]
    firm_deals.sign_nda(db, team["investment_banker"], file_id, LATER)
    return empire, team, sale, file_id


# 1. Can a player see a private company's accounts, or its secrets, without signing for the data room?
def test_q1_nothing_private_is_seen_without_the_confidentiality_agreement(db, client):
    assert join(client, ADULT).status_code == 201
    hidden = _one(db, "SELECT * FROM companies WHERE NOT listed ORDER BY ticker LIMIT 1")
    assert client.get(f"/api/companies/{hidden['ticker']}").status_code == 404
    assert client.get(f"/api/market/{hidden['ticker']}/facts").status_code == 404
    empire, team = firm_of(db, n_cash=60_000_000_000)
    sale = open_a_sale(db)
    file_id = firm_deals.open_file(db, team["investment_banker"], sale["id"], LATER)["file_id"]
    seen = firm.view(db, team["head"], LATER)["deals"]
    mine = next(s for s in seen["sales"] if s["id"] == sale["id"])
    assert "data_room" not in mine["file"] and "reserve" not in str(mine) and "secrets" not in str(seen)
    step = _one(db, "SELECT id FROM deal_steps WHERE file_id = %s AND step = 'legal'", (file_id,))
    with pytest.raises(empires.EmpireError, match="confidentiality"):
        firm_deals.open_step(db, team["investment_banker"], step["id"], LATER)
    firm_deals.sign_nda(db, team["investment_banker"], file_id, LATER)
    opened = firm_deals.open_step(db, team["investment_banker"], step["id"], LATER)
    assert "_truth" not in str(opened) and "_truth" not in str(firm.view(db, team["investment_banker"], LATER))


# 2. Can a deal create money?
def test_q2_a_whole_purchase_and_sale_moves_money_and_creates_none(db):
    empire, team, sale, file_id = ready(db, "EWT")
    do_checks(db, empire, team, file_id)
    before = ledger.amount_in_existence(db)
    firm_deals.place_bid(db, team["head"], file_id, sale["asking"] * 13 // 10, 0, LATER)
    assert ledger.amount_in_existence(db) == before and firm_deals.check_books(db) == []
    assert quarters.close_due_quarters(db, after_quarters(9)) == [9]
    assert ledger.audit(db) == [] and firm_deals.check_books(db) == []
    deal = _one(db, "SELECT * FROM deals WHERE empire_id = %s", (empire["id"],))
    if deal:
        out = firm_owned.sell_to_buyer(db, team["head"], deal["company_id"], after_quarters(9) + timedelta(hours=2))
        assert out["proceeds"] >= 0 and ledger.audit(db) == []


# 3. Can an empire promise the same cash to two bids?
def test_q3_cash_held_for_one_bid_cannot_be_bid_again(db):
    empire, team, sale, file_id = ready(db)
    cash = ledger.balance(db, empire["account_id"])
    second = open_a_sale(db)
    other_file = firm_deals.open_file(db, team["investment_banker"], second["id"], LATER)["file_id"]
    firm_deals.sign_nda(db, team["investment_banker"], other_file, LATER)
    db.execute("UPDATE sale_processes SET asking = %s WHERE id IN (%s, %s)", (cash * 6 // 10, sale["id"], second["id"]))
    # Deals this large need a fairness opinion as well: every check is done on both files.
    for f in (file_id, other_file):
        db.execute("INSERT INTO deal_steps (file_id, step, build) VALUES (%s, 'fairness', 'investment_banker') ON CONFLICT DO NOTHING", (f,))
    do_checks(db, empire, team, file_id)
    do_checks(db, empire, team, other_file)
    firm_deals.place_bid(db, team["head"], file_id, cash * 6 // 10, 0, LATER)
    with pytest.raises(empires.EmpireError, match="has not the cash"):
        firm_deals.place_bid(db, team["head"], other_file, cash * 6 // 10, 0, LATER)
    assert firm_deals.check_books(db) == []


# 4. Can a head sell the members' company to a friend for next to nothing?
def test_q4_a_head_cannot_sell_the_empires_company_far_below_its_worth(db):
    empire, team = firm_of(db)
    company = own(db, empire, "RWH")
    worth = private.value_of(db, company["id"])
    with pytest.raises(empires.EmpireError, match="giving the members' money away"):
        firm_owned.sell_to_empire(db, team["head"], company["id"], worth, worth // 10, "sealed", LATER)
    with pytest.raises(empires.EmpireError, match="head"):
        firm_owned.sell_to_empire(db, team["investment_banker"], company["id"], worth, worth, "sealed", LATER)


# 5. Can a head pay a seller far more than a company is worth, to move the empire's money out?
def test_q5_no_bid_far_above_the_companys_worth(db):
    empire, team, sale, file_id = ready(db)
    do_checks(db, empire, team, file_id)
    with pytest.raises(empires.EmpireError, match="No board would let a price"):
        firm_deals.place_bid(db, team["head"], file_id, sale["asking"] * 10, 0, LATER)


# 6. Can a buyer claim for a fault it found before it bought?
def test_q6_no_claim_for_what_the_buyer_knew_before_it_bid(db):
    dressed = _one(db, "SELECT c.ticker FROM private_profiles p JOIN companies c ON c.id = p.company_id WHERE p.secrets @> '[{\"code\": \"dressed_revenue\"}]'"
                       " AND c.status = 'trading' AND NOT EXISTS (SELECT 1 FROM sale_processes s WHERE s.company_id = c.id AND s.status = 'open'"
                       " AND s.seller_empire_id IS NOT NULL) ORDER BY c.ticker LIMIT 1")
    empire, team, sale, file_id = ready(db, dressed["ticker"])
    do_checks(db, empire, team, file_id)                                          # the Accountant finds it before the bid
    bid = sale["asking"] * 13 // 10
    fairness_if_needed(db, team, file_id, bid)
    firm_deals.place_bid(db, team["head"], file_id, bid, 0, LATER)
    assert quarters.close_due_quarters(db, after_quarters(9)) == [9]
    deal = _one(db, "SELECT * FROM deals WHERE empire_id = %s", (empire["id"],))
    if deal is None:
        pytest.skip("Outbid by a computer-run empire.")
    with pytest.raises(empires.EmpireError, match="priced in"):
        firm_deals.claim(db, team["investment_banker"], deal["id"], "dressed_revenue", after_quarters(9) + timedelta(hours=2))


# 7. Can a member act for a desk that is not theirs, or another empire's file?
def test_q7_each_part_of_a_deal_is_done_only_by_its_desk_and_only_in_its_own_empire(db):
    empire, team, sale, file_id = ready(db)
    step = {s["step"]: s for s in _dicts(db, "SELECT * FROM deal_steps WHERE file_id = %s", (file_id,))}
    with pytest.raises(empires.EmpireError, match="belongs to the"):
        firm_deals.open_step(db, team["investment_banker"], step["accounts"]["id"], LATER)
    with pytest.raises(empires.EmpireError, match="Legal Counsel"):
        firm_deals.mark_terms(db, team["asset_manager"], file_id, {"as_is": "strike"}, LATER)
    with pytest.raises(empires.EmpireError, match="head"):
        firm_deals.place_bid(db, team["investment_banker"], file_id, sale["asking"], 0, LATER)
    stranger_head, _ = pro(db, "asset_manager", "outsider", level=20, cash_naira=60_000_000)
    outsider = empires.found(db, stranger_head, "Outside House", million_naira(40), 0, NOW9)
    clerk = member(db, outsider, stranger_head, "asset_manager", "outclerk")
    member(db, outsider, stranger_head, "investment_banker", "outscribe")
    empires.open_empire(db, stranger_head, NOW9)
    with pytest.raises(empires.EmpireError, match="no such"):
        firm_deals.open_step(db, clerk, step["accounts"]["id"], LATER)
    with pytest.raises(empires.EmpireError, match="no such deal file"):
        firm_deals.place_bid(db, stranger_head, file_id, sale["asking"], 0, LATER)


# 8. Can a bid be placed in the moments after the quarter ended, knowing how it ended?
def test_q8_no_bid_between_the_end_of_a_quarter_and_its_close(db):
    empire, team, sale, file_id = ready(db)
    do_checks(db, empire, team, file_id)
    ended = after_quarters(9) - timedelta(minutes=50)            # the quarter is over; its books are not closed yet
    with pytest.raises(empires.EmpireError):
        firm_deals.place_bid(db, team["head"], file_id, sale["asking"], 0, ended)


# 9. Can a check done badly tell the empire what it failed to find?
def test_q9_a_check_handed_in_wrong_does_not_show_the_right_answer(db):
    empire, team, sale, file_id = ready(db)
    step = _one(db, "SELECT * FROM deal_steps WHERE file_id = %s AND step = 'accounts'", (file_id,))
    firm_deals.open_step(db, team["asset_manager"], step["id"], LATER)
    right = truth(db, step["id"])["gap"]
    done = firm_deals.hand_in_step(db, team["asset_manager"], step["id"], {"gap": 99.99}, LATER)
    assert done["score"] < 60 and "answer" not in str(done["result"]) and str(right / 100) not in str(done)
    with pytest.raises(empires.EmpireError, match="done"):
        firm_deals.hand_in_step(db, team["asset_manager"], step["id"], {"gap": right / 100}, LATER)


# 10. Can private shares slip onto the exchange, or be counted at nothing (or at a pumped-up value)?
def test_q10_private_shares_are_not_traded_and_are_counted_at_a_fair_value(db):
    empire, team = firm_of(db)
    company = own(db, empire, "OWR")
    with pytest.raises(exchange.ExchangeError, match="no share with that code"):
        exchange.place_order(db, account=empire["account_id"], ticker=company["ticker"], side="sell", kind="limit", quantity=1, limit_price=100,
                             now=LATER)
    have = objectives.wealth(db, empire["account_id"], LATER)
    line = next(x for x in have["lines"] if x["ticker"] == company["ticker"])
    # An empire carries a private stake at what it paid: nothing about the company's private figures shows in its worth.
    held = ledger.balance(db, empire["account_id"], company["share_asset"])
    assert line["value"] > 0 and line["price"] == million_naira(1_000) // held
    # The computer-run buyer pays no more than the year's average valuation, so a quarter pumped up does not sell high.
    offer = firm_owned.buyer_offer(db, company["id"])
    year = _dicts(db, "SELECT value_per_share FROM company_valuations WHERE company_id = %s ORDER BY period DESC LIMIT 4", (company["id"],))
    assert offer["per_share"] <= sum(r["value_per_share"] for r in year) // len(year)
