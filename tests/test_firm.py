"""Private equity stage, part 1: the empire becomes a working firm.

Desks and their duties, requests that never wait for ever, votes and the empire's own rules, papers
with traps, borrowing with promises attached, dividends, budgets, expense approval, the quarterly
accounts, contracts, apprentices, poaching, the head's year, more kinds of task, rivals, events,
insurance, and the Risk Manager's limits."""

from __future__ import annotations

from datetime import timedelta

import pytest
from psycopg.rows import dict_row

from simulation import careers, empires, firm, firm_money, firm_people, firm_risk, firm_tasks, ledger, leagues, quarters
from simulation import world_data as data
from simulation.money import naira
from tests.conftest import after_quarters
from tests.test_builds import pro
from tests.test_careers import NOW9, sound
from tests.test_empires import founded
from tests.test_objectives import give_cash, give_shares

pytestmark = pytest.mark.world("eight")
LATER = NOW9 + timedelta(hours=1)
DAY2 = NOW9 + timedelta(days=1)
DAY3 = NOW9 + timedelta(days=2, hours=1)
DAY4 = NOW9 + timedelta(days=3, hours=1)


def _dicts(db, sql, params=()):
    with db.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def _one(db, sql, params=()):
    rows = _dicts(db, sql, params)
    return rows[0] if rows else None


def member(db, empire, head, build, name, level=4, cash=1_000_000):
    player, account = pro(db, build, name, level=level, cash_naira=cash)
    empires.apply(db, player, empire["id"], NOW9)
    asked = _one(db, "SELECT id FROM empire_applications WHERE player_id = %s AND status = 'waiting'", (player,))["id"]
    empires.decide_application(db, head, asked, True, NOW9)
    return player


def firm_of(db, n_cash=2_000_000_000):
    """Lagoon House, with a member at every desk, and some cash and shares to work with."""
    empire, (head, _), partners = founded(db)
    team = {"head": head, "journalist": partners["journalist"][0], "accountant": partners["accountant"][0]}
    for build, name in (("risk_manager", "warden"), ("lawyer", "counsel"), ("investment_banker", "dealer")):
        team[build] = member(db, empire, head, build, name)
    give_cash(db, empire["account_id"], n_cash)
    return empires._empire(db, empire["id"]), team


def waiting(db, empire_id, kind):
    return _one(db, "SELECT * FROM empire_approvals WHERE empire_id = %s AND kind = %s AND status = 'waiting' ORDER BY id DESC", (empire_id, kind))


def duty_of(db, empire_id, code):
    firm.ensure_duties(db, empires._empire(db, empire_id), careers.world_now(db, NOW9)["period"])
    return _one(db, "SELECT * FROM desk_duties WHERE empire_id = %s AND code = %s ORDER BY period DESC", (empire_id, code))


def right(db, duty_id):
    return _one(db, "SELECT terms FROM desk_duties WHERE id = %s", (duty_id,))["terms"]["_truth"]


# ---------------------------------------------------------------------------
# The stage test
# ---------------------------------------------------------------------------

def test_the_stage_test_every_desk_has_standing_work_that_is_marked_and_the_desks_depend_on_one_another(db):
    """Each build's desk has duties that come round every quarter, marked from the empire's own figures; a
    raising of money goes through four desks before the money arrives; the quarter's close scores every desk."""
    empire, team = firm_of(db)
    give_shares(db, empire["account_id"], "GGM", 50_000_000)
    view = firm.view(db, team["head"], NOW9)
    desks = {d["build"]: d for d in view["duties"]["desks"]}
    assert set(desks) == set(firm.DESKS)
    assert all(desks[b]["duties"] for b in data.EMPIRE_BUILDS)
    # The Accountant closes the books from the empire's figures.
    duty = duty_of(db, empire["id"], "ac_close")
    opened = firm.open_duty(db, team["accountant"], duty["id"], LATER)
    assert "_truth" not in opened["terms"] and opened["terms"]["asks"]
    done = firm.hand_in(db, team["accountant"], duty["id"], right(db, duty["id"]), LATER)
    assert done["score"] == 100 and done["experience"] > 0
    # Raising money: the banker designs it, the Accountant checks, the Risk Manager approves, the Legal Counsel reads, the head signs.
    asked = firm_money.design_raising(db, team["investment_banker"], "bond", naira(60_000_000), 4, LATER)
    firm.decide(db, team["accountant"], asked["approval_id"], True, "", LATER)
    risk = waiting(db, empire["id"], "raise_risk")
    firm.decide(db, team["risk_manager"], risk["id"], True, "The empire can carry it.", LATER)
    paper = _one(db, "SELECT * FROM empire_documents WHERE empire_id = %s AND status = 'draft'", (empire["id"],))
    traps = [c["code"] for c in paper["clauses"] if c["trap"]]
    firm.review_document(db, team["lawyer"], paper["id"], traps, LATER)
    sign = waiting(db, empire["id"], "raise_sign")
    before = ledger.balance(db, empire["account_id"])
    firm.decide(db, team["head"], sign["id"], True, "", LATER)
    assert ledger.balance(db, empire["account_id"]) == before + naira(60_000_000)
    debt = _one(db, "SELECT * FROM empire_debts WHERE empire_id = %s", (empire["id"],))
    assert debt["traps"] == [] and debt["lender_name"] == "The pension funds"
    # The Closing Bells ring (the rival is named, the risk report written); the quarter closes: every desk is scored,
    # interest is paid, the accounts are kept.
    firm.at_bell(db, DAY2)
    assert _one(db, "SELECT 1 FROM empire_risk_reports WHERE empire_id = %s", (empire["id"],))
    quarters.close_due_quarters(db, after_quarters(9))
    cards = _dicts(db, "SELECT build, score, missed FROM desk_scores WHERE empire_id = %s AND period = 9", (empire["id"],))
    assert {c["build"] for c in cards} >= set(data.EMPIRE_BUILDS)
    assert _one(db, "SELECT 1 FROM empire_accounts WHERE empire_id = %s AND period = 9", (empire["id"],))
    assert _one(db, "SELECT amount FROM empire_books WHERE empire_id = %s AND category = 'Interest'", (empire["id"],))
    assert _dicts(db, "SELECT 1 FROM desk_duties WHERE empire_id = %s AND period = 10", (empire["id"],))
    sound(db)


# ---------------------------------------------------------------------------
# Requests, votes, papers
# ---------------------------------------------------------------------------

def test_a_request_passes_to_the_head_after_a_day_and_to_the_deputy_after_two_and_lapses_after_three(db):
    empire, team = firm_of(db)
    firm.name_title(db, team["head"], team["journalist"], "deputy", NOW9)
    request = firm.ask(db, empire, kind="note", desk="lawyer", asked_by=team["accountant"], title="A question", period=9, now=NOW9)
    assert set(firm.deciders(db, request, LATER)) == {team["lawyer"]}
    assert firm.deciders(db, request, NOW9 + timedelta(hours=25))[team["head"]] == "head"
    assert firm.deciders(db, request, NOW9 + timedelta(hours=49))[team["journalist"]] == "deputy"
    with pytest.raises(empires.EmpireError, match="not yours"):
        firm.decide(db, team["investment_banker"], request["id"], True, "", LATER)
    firm.at_bell(db, NOW9 + timedelta(hours=73))
    assert _one(db, "SELECT status FROM empire_approvals WHERE id = %s", (request["id"],))["status"] == "lapsed"


def test_nobody_decides_their_own_request_and_a_refusal_needs_a_reason(db):
    empire, team = firm_of(db)
    mine = firm.ask(db, empire, kind="note", desk="accountant", asked_by=team["accountant"], title="Mine", period=9, now=NOW9)
    with pytest.raises(empires.EmpireError, match="own request"):
        firm.decide(db, team["accountant"], mine["id"], True, "", LATER)
    theirs = firm.ask(db, empire, kind="trade", desk="risk_manager", asked_by=team["head"], title="A trade", period=9, now=NOW9,
                      payload={"why": []})
    with pytest.raises(empires.EmpireError, match="reason"):
        firm.decide(db, team["risk_manager"], theirs["id"], False, "", LATER)


def test_the_head_overrules_the_risk_managers_refusal_on_the_record(db):
    empire, team = firm_of(db)
    asked = firm_money.design_raising(db, team["investment_banker"], "bond", naira(60_000_000), 4, LATER)
    firm.decide(db, team["accountant"], asked["approval_id"], True, "", LATER)
    risk = waiting(db, empire["id"], "raise_risk")
    firm.decide(db, team["risk_manager"], risk["id"], False, "Too much debt for a young firm.", LATER)
    firm.overrule(db, team["head"], risk["id"], "We need the money for the task.", LATER)
    assert _one(db, "SELECT status FROM empire_approvals WHERE id = %s", (risk["id"],))["status"] == "overruled"
    record = firm.ceo_record(db, team["head"])
    assert record["overrules"] == 1 and "Too much debt" in record["entries"][0]["words"]
    with pytest.raises(empires.EmpireError):
        firm.overrule(db, team["head"], risk["id"], "Again", LATER)


def test_members_vote_the_treasury_policy_and_the_head_breaks_a_tie(db):
    empire, team = firm_of(db)
    vote = firm.propose(db, team["risk_manager"], "treasury", {"cash_least_bps": 2000, "shares_most_bps": 5000}, LATER)
    assert vote["status"] == "open"
    for who in ("head", "journalist", "accountant"):
        firm.vote(db, team[who], vote["id"], True, LATER)
    assert _one(db, "SELECT status FROM empire_resolutions WHERE id = %s", (vote["id"],))["status"] == "passed"
    assert firm_money.policy(db, empire["id"]) == {"cash_least_bps": 2000, "shares_most_bps": 5000}
    with pytest.raises(empires.EmpireError, match="not yours"):
        firm.propose(db, team["journalist"], "treasury", {"cash_least_bps": 0, "shares_most_bps": 10000}, LATER)
    # A computer-run empire's members do not vote on its rules.
    other = _one(db, "SELECT * FROM empires WHERE kind = 'computer' ORDER BY id")
    ada, _ = pro(db, "risk_manager", "ada")
    empires.apply(db, ada, other["id"], NOW9)
    with pytest.raises(empires.EmpireError, match="computer"):
        firm.propose(db, ada, "treasury", {"cash_least_bps": 0, "shares_most_bps": 10000}, LATER)


def test_a_paper_hides_which_clauses_are_traps_until_it_has_been_read_and_a_trap_left_in_stays_in_force(db):
    empire, team = firm_of(db)
    asked = firm_money.design_raising(db, team["investment_banker"], "loan", naira(20_000_000), 4, LATER)
    firm.decide(db, team["accountant"], asked["approval_id"], True, "", LATER)
    firm.decide(db, team["risk_manager"], waiting(db, empire["id"], "raise_risk")["id"], True, "Fine.", LATER)
    paper = _one(db, "SELECT * FROM empire_documents WHERE empire_id = %s AND status = 'draft'", (empire["id"],))
    shown = firm.view(db, team["lawyer"], LATER)["papers"]["papers"][0]
    assert all(set(c) == {"code", "words"} for c in shown["clauses"])
    traps = [c["code"] for c in paper["clauses"] if c["trap"]]
    fair = [c["code"] for c in paper["clauses"] if not c["trap"]]
    read = firm.review_document(db, team["lawyer"], paper["id"], traps[1:] + fair[:1], LATER)
    assert read["kept_traps"] == 1 and read["wrongly_struck"] == 1
    firm.decide(db, team["head"], waiting(db, empire["id"], "raise_sign")["id"], True, "", LATER)
    debt = _one(db, "SELECT * FROM empire_debts WHERE empire_id = %s", (empire["id"],))
    if debt:                                           # a bank had the room to lend
        assert debt["traps"] == [traps[0]]
        assert debt["rate_bps"] == careers.world_now(db, NOW9)["policy_rate_bps"] + firm_money.LOAN_SPREAD_BPS + firm_money.STRUCK_FAIR_BPS
    record = firm.track_record(db, team["lawyer"])
    assert record["wrong"] == 1


# ---------------------------------------------------------------------------
# Money
# ---------------------------------------------------------------------------

def test_an_empire_may_not_owe_more_than_half_of_what_it_owns(db):
    empire, team = firm_of(db, n_cash=100_000_000)
    owned = firm_money._owned(db, empire, NOW9)
    asked = firm_money.design_raising(db, team["investment_banker"], "bond", owned * 6 // 10, 4, LATER)
    with pytest.raises(empires.EmpireError, match="half"):
        firm.decide(db, team["accountant"], asked["approval_id"], True, "", LATER)


def test_a_broken_promise_lets_the_lender_call_the_debt_and_an_unpaid_debt_is_a_default(db):
    empire, team = firm_of(db)
    asked = firm_money.design_raising(db, team["investment_banker"], "bond", naira(200_000_000), 4, LATER)
    firm.decide(db, team["accountant"], asked["approval_id"], True, "", LATER)
    firm.decide(db, team["risk_manager"], waiting(db, empire["id"], "raise_risk")["id"], True, "Fine.", LATER)
    paper = _one(db, "SELECT * FROM empire_documents WHERE empire_id = %s AND status = 'draft'", (empire["id"],))
    firm.review_document(db, team["lawyer"], paper["id"], [c["code"] for c in paper["clauses"] if c["trap"]], LATER)
    firm.decide(db, team["head"], waiting(db, empire["id"], "raise_sign")["id"], True, "", LATER)
    # The cash goes: the empire now has less than a quarter's interest.
    ledger.transfer(db, payer=empire["account_id"], receiver=ledger.account_id(db, ledger.TREASURY), amount=ledger.balance(db, empire["account_id"]) - 1,
                    kind="test_cash", memo="Test: the cash is gone")
    quarters.close_due_quarters(db, after_quarters(9))
    debt = _one(db, "SELECT * FROM empire_debts WHERE empire_id = %s", (empire["id"],))
    assert debt["status"] == "defaulted"
    assert _one(db, "SELECT points FROM league_points WHERE empire_id = %s AND reference = %s", (empire["id"], f"default:{debt['id']}"))["points"] == -5
    sound(db)


def test_a_dividend_is_paid_to_the_partners_by_their_units_and_never_more_than_half_the_profit(db):
    empire, team = firm_of(db)
    with pytest.raises(empires.EmpireError, match="profit"):
        firm.propose(db, team["head"], "dividend", {"amount": naira(1_000_000)}, LATER)
    db.execute("INSERT INTO empire_accounts (empire_id, period, figures) VALUES (%s, 8, %s)", (empire["id"], firm._json({"profit": naira(10_000_000)})))
    with pytest.raises(empires.EmpireError, match="half"):
        firm.propose(db, team["head"], "dividend", {"amount": naira(6_000_000)}, LATER)
    vote = firm.propose(db, team["accountant"], "dividend", {"amount": naira(4_000_000)}, LATER)
    head_cash = ledger.balance(db, ledger.player_account_id(db, team["head"]))
    for who in ("head", "journalist", "risk_manager"):
        firm.vote(db, team[who], vote["id"], True, LATER)
    assert _one(db, "SELECT status FROM empire_resolutions WHERE id = %s", (vote["id"],))["status"] == "passed"
    # Only the founder put money in, so the founder holds every unit and receives all of it.
    assert ledger.balance(db, ledger.player_account_id(db, team["head"])) == head_cash + naira(4_000_000)
    sound(db)


def test_new_capital_and_a_stake_buy_units_at_todays_price_so_nobody_is_diluted(db):
    empire, team = firm_of(db)
    firm_money.ensure_units(db, empire)
    price = firm_money.unit_price(db, empire, LATER)
    founder_value = firm_money.partners(db, empire, LATER)[0]["value"]
    give_cash(db, ledger.player_account_id(db, team["journalist"]), 10_000_000)
    empires.put_in(db, team["journalist"], naira(10_000_000), 0, LATER)
    after = {p["player_id"]: p for p in firm_money.partners(db, empire, LATER)}
    assert abs(after[team["head"]]["value"] - founder_value) <= price
    assert abs(after[team["journalist"]]["value"] - naira(10_000_000)) <= price * 2
    sound(db)


def test_a_cost_above_the_threshold_waits_for_the_accountant_who_sees_only_its_heading(db):
    empire, team = firm_of(db)
    db.execute("UPDATE empires SET expense_limit = %s WHERE id = %s", (naira(5_000_000), empire["id"]))
    taken = empires.divert(db, team["journalist"], naira(400_000), LATER)
    assert taken["waiting"] is True
    view = firm.view(db, team["accountant"], LATER)["approvals"]["to_decide"][0]
    assert view["detail"]["heading"] == "Research and sources" and "genuine" not in str(view) and "diverted" not in str(view)
    cash = ledger.balance(db, ledger.player_account_id(db, team["journalist"]))
    firm.decide(db, team["accountant"], taken["approval_id"], True, "", LATER)
    assert ledger.balance(db, ledger.player_account_id(db, team["journalist"])) == cash + naira(400_000)
    book = _one(db, "SELECT * FROM empire_books WHERE empire_id = %s AND entered_by = %s", (empire["id"], team["journalist"]))
    assert book["genuine"] is False and book["desk"] == "journalist"
    # Below the threshold it goes through at once, as before.
    assert empires.divert(db, team["journalist"], naira(100_000), LATER)["waiting"] is False
    sound(db)


def test_a_desk_under_budget_that_did_its_duties_earns_a_pool_for_its_members(db):
    empire, team = firm_of(db)
    firm_money.set_budgets(db, team["head"], {"accountant": naira(2_000_000)}, LATER)
    duty = duty_of(db, empire["id"], "ac_close")
    firm.open_duty(db, team["accountant"], duty["id"], LATER)
    firm.hand_in(db, team["accountant"], duty["id"], right(db, duty["id"]), LATER)
    cash = ledger.balance(db, ledger.player_account_id(db, team["accountant"]))
    quarters.close_due_quarters(db, after_quarters(9))
    gained = ledger.balance(db, ledger.player_account_id(db, team["accountant"])) - cash
    assert gained >= naira(2_000_000) * firm_money.POOL_SHARE_BPS // 10_000 - naira(1)
    sound(db)


def test_training_is_a_genuine_cost_that_teaches_a_member(db):
    empire, team = firm_of(db)
    before = careers.career(db, team["lawyer"], "lawyer")["experience"]
    firm_money.sign_cost(db, team["head"], "training", naira(200_000), team["lawyer"], LATER)
    assert careers.career(db, team["lawyer"], "lawyer")["experience"] == before + 20
    sound(db)


# ---------------------------------------------------------------------------
# People
# ---------------------------------------------------------------------------

def test_a_contract_drafted_by_the_lawyer_sets_the_notice_and_its_non_compete_bars_the_rival(db):
    empire, team = firm_of(db)
    contract = firm_people.offer_contract(db, team["lawyer"], team["journalist"], 3, 500, 1, LATER)
    firm_people.answer_contract(db, team["journalist"], contract["id"], True, LATER)
    gone = empires.resign(db, team["journalist"], "Off I go.", LATER)
    assert gone["leaves_at"] == LATER + timedelta(days=3)
    rival = _one(db, "SELECT * FROM empires WHERE kind = 'computer' ORDER BY id")
    db.execute("UPDATE empires SET rival_id = %s WHERE id = %s", (rival["id"], empire["id"]))
    empires.release(db, team["head"], _one(db, "SELECT id FROM empire_resignations WHERE player_id = %s", (team["journalist"],))["id"], LATER)
    with pytest.raises(empires.EmpireError, match="bars you"):
        empires.apply(db, team["journalist"], rival["id"], LATER)


def test_a_mentor_gains_when_their_apprentice_does_good_work(db):
    empire, team = firm_of(db)
    junior = member(db, empire, team["head"], "investment_banker", "junior", level=2)
    db.execute("UPDATE careers SET experience = %s WHERE player_id = %s", (careers.experience_for(20), team["investment_banker"]))
    with pytest.raises(empires.EmpireError, match="levels above"):
        firm_people.take_apprentice(db, junior, team["investment_banker"], LATER)
    firm_people.take_apprentice(db, team["investment_banker"], junior, LATER)
    before = careers.career(db, team["investment_banker"], "investment_banker")["experience"]
    firm_people.apprentice_gain(db, junior, "investment_banker", 100, LATER)
    assert careers.career(db, team["investment_banker"], "investment_banker")["experience"] == before + 20


def test_poaching_gives_the_home_empire_two_days_to_match_and_a_member_under_contract_moves_for_a_transfer_fee(db):
    empire, team = firm_of(db)
    rival_head, _ = pro(db, "asset_manager", "raider", level=20, cash_naira=60_000_000)
    rival = empires.found(db, rival_head, "Raider House", naira(40_000_000), 0, NOW9)
    for build, name in (("journalist", "r1"), ("accountant", "r2")):
        member(db, rival, rival_head, build, name)
    rival = empires.open_empire(db, rival_head, NOW9)
    give_cash(db, rival["account_id"], 50_000_000)
    firm_people.offer_contract(db, team["lawyer"], team["risk_manager"], 7, 0, 0, LATER)
    firm_people.answer_contract(db, team["risk_manager"], _one(db, "SELECT id FROM member_contracts WHERE player_id = %s", (team["risk_manager"],))["id"],
                                True, LATER)
    offer = firm_people.poach(db, rival_head, team["risk_manager"], naira(2_000_000), "Come to us.", LATER)
    with pytest.raises(empires.EmpireError, match="to match"):
        firm_people.answer_poach(db, team["risk_manager"], offer["id"], True, LATER)
    home_cash = ledger.balance(db, empire["account_id"])
    moved = firm_people.answer_poach(db, team["risk_manager"], offer["id"], True, DAY3)
    assert moved == {"moved": True, "fee": naira(2_000_000)}
    assert empires.seat_of(db, team["risk_manager"])["empire_id"] == rival["id"]
    assert ledger.balance(db, empire["account_id"]) == home_cash + naira(2_000_000)
    sound(db)


def test_the_head_loses_the_yearly_vote_of_confidence_and_the_deputy_leads(db):
    empire, team = firm_of(db)
    firm.name_title(db, team["head"], team["lawyer"], "deputy", NOW9)
    vote = firm.call_vote(db, empire, "confidence", "Confidence?", {"subject_id": str(team["head"])}, 9, LATER)
    with pytest.raises(empires.EmpireError, match="about yourself"):
        firm.vote(db, team["head"], vote["id"], True, LATER)
    for who in ("journalist", "accountant", "risk_manager"):
        firm.vote(db, team[who], vote["id"], False, LATER)          # of five voters, three are needed: three against and it cannot pass
    assert _one(db, "SELECT status FROM empire_resolutions WHERE id = %s", (vote["id"],))["status"] == "failed"
    assert empires._empire(db, empire["id"])["head_player_id"] == team["lawyer"]
    assert firm.ceo_record(db, team["head"])["bad"] == 1


def test_the_strategy_is_set_once_a_year_and_judged_against_its_own_targets(db):
    empire, team = firm_of(db)
    firm_people.set_strategy(db, team["head"], "safe", -1000, 0, 0, LATER)
    with pytest.raises(empires.EmpireError, match="already set"):
        firm_people.set_strategy(db, team["head"], "grow", 5000, 0, 1, LATER)
    for n in range(9, 13):
        quarters.close_due_quarters(db, after_quarters(n))
    result = _one(db, "SELECT result FROM empire_strategies WHERE empire_id = %s", (empire["id"],))["result"]
    assert result is not None and result["met"]["payout"] and result["met"]["tasks"]


# ---------------------------------------------------------------------------
# Work, rivals, events, insurance
# ---------------------------------------------------------------------------

def test_up_to_three_tasks_of_different_kinds_and_the_head_gives_each_step_to_a_member(db):
    empire, team = firm_of(db)
    first = firm_tasks.start(db, team["head"], "investment", 1, LATER)
    firm_tasks.start(db, team["head"], "raise_money", 2, LATER)
    with pytest.raises(empires.EmpireError, match="One of each kind"):
        firm_tasks.start(db, team["head"], "investment", 3, LATER)
    step = _one(db, "SELECT id FROM empire_task_steps WHERE task_id = %s AND position = 1", (first["id"],))
    other = member(db, empire, team["head"], "journalist", "second")
    firm_tasks.assign_step(db, team["head"], step["id"], other, LATER)
    with pytest.raises(empires.EmpireError, match="given that step"):
        empires.take_step(db, team["journalist"], step["id"], LATER)
    # Raising money as a task: the desks' real decisions move it on.
    asked = firm_money.design_raising(db, team["investment_banker"], "bond", naira(60_000_000), 4, LATER)
    raising = _one(db, "SELECT * FROM empire_tasks WHERE empire_id = %s AND kind = 'raise_money'", (empire["id"],))
    assert _one(db, "SELECT status FROM empire_task_steps WHERE task_id = %s AND position = 1", (raising["id"],))["status"] == "done"
    firm.decide(db, team["accountant"], asked["approval_id"], True, "", LATER)
    assert _one(db, "SELECT status FROM empire_task_steps WHERE task_id = %s AND position = 2", (raising["id"],))["status"] == "done"


def test_the_bankers_shortlist_decides_the_next_investment_and_is_judged_against_the_market(db):
    empire, team = firm_of(db)
    duty = duty_of(db, empire["id"], "ib_shortlist")
    terms = firm.open_duty(db, team["investment_banker"], duty["id"], LATER)["terms"]
    picks = terms["asks"][0]["choices"][:3]
    firm.hand_in(db, team["investment_banker"], duty["id"], {"targets": picks, "case": "Cheap, sound and growing."}, LATER)
    shortlist = waiting(db, empire["id"], "shortlist")
    task = firm_tasks.pick(db, team["head"], shortlist["id"], shortlist["payload"]["targets"][1], LATER)
    chosen = _one(db, "SELECT c.ticker FROM empire_tasks t JOIN companies c ON c.id = t.company_id WHERE t.id = %s", (task["task_id"],))
    assert chosen["ticker"] == picks[1]
    assert _one(db, "SELECT 1 FROM signed_opinions WHERE player_id = %s AND kind = 'shortlist'", (team["investment_banker"],))


def test_every_empire_has_a_rival_and_a_head_to_head_score(db):
    empire, team = firm_of(db)
    firm.at_bell(db, DAY2)
    rival = empires._empire(db, empire["id"])["rival_id"]
    assert rival and rival != empire["id"]
    leagues.award(db, empire["id"], 50, "Test", 9, LATER, reference="t1")
    seen = firm_tasks.head_to_head(db, empires._empire(db, empire["id"]))
    this = next(q for q in seen["quarters"] if q["label"] == careers.clock.period_label(9))
    assert this["ours"] > this["theirs"] and seen["won"] >= 1


def test_an_inspection_is_answered_by_three_desks_and_a_failed_one_is_fined_unless_insured(db, monkeypatch):
    empire, team = firm_of(db)
    insurer = firm_tasks._insurers(db)[0]
    firm_tasks.buy_cover(db, team["risk_manager"], "inspection", insurer["id"], naira(5_000_000), LATER)
    monkeypatch.setattr(firm_tasks, "_roll", lambda conn, *parts: 0)
    firm.at_bell(db, DAY2)
    event = _one(db, "SELECT * FROM empire_happenings WHERE empire_id = %s", (empire["id"],))
    assert event is not None
    shown = firm.view(db, team["accountant"], DAY2)["work"]["events"][0]
    assert all(not k.startswith("_") for k in shown["facts"])
    if event["kind"] == "inspection":
        firm_tasks.answer(db, team["lawyer"], event["id"], "lawyer", "none", DAY2)
        with pytest.raises(empires.EmpireError, match="already answered"):
            firm_tasks.answer(db, team["lawyer"], event["id"], "lawyer", "holdings", DAY2)
        with pytest.raises(empires.EmpireError, match="falls to"):
            firm_tasks.answer(db, team["lawyer"], event["id"], "accountant", 5, DAY2)
    firm.at_bell(db, DAY4)
    settled = _one(db, "SELECT * FROM empire_happenings WHERE id = %s", (event["id"],))
    assert settled["status"] == "settled"
    if event["kind"] == "inspection":
        assert settled["cost"] > 0 and settled["covered"] == min(settled["cost"], naira(5_000_000))
    sound(db)


# ---------------------------------------------------------------------------
# The Risk Manager's teeth
# ---------------------------------------------------------------------------

def test_a_trade_above_the_risk_managers_limit_waits_for_approval_and_a_frozen_member_cannot_trade(db):
    empire, team = firm_of(db)
    trader = member(db, empire, team["head"], "asset_manager", "trader")
    db.execute("UPDATE empires SET trade_limit_bps = 10000 WHERE id = %s", (empire["id"],))
    firm_risk.set_trade_limit(db, team["risk_manager"], 1_000_000, LATER)
    held = empires.trade_shares(db, trader, ticker="GGM", side="buy", kind="limit", quantity=100_000, limit_price=10_000, now=LATER)
    assert held["waiting"] is True and "limit" in held["why"][0]
    firm_risk.freeze(db, team["risk_manager"], trader, True, "Too many large orders.", LATER)
    with pytest.raises(empires.EmpireError, match="frozen"):
        empires.trade_shares(db, trader, ticker="GGM", side="buy", kind="limit", quantity=10, limit_price=10_000, now=LATER)
    with pytest.raises(empires.EmpireError, match="frozen"):
        empires.trade_bonds(db, trader, code="X", side="buy", units=1, now=LATER)
    firm_risk.freeze(db, team["head"], trader, False, "I will watch them myself.", LATER)
    assert firm.ceo_record(db, team["head"])["overrules"] == 1


def test_a_missed_filing_is_a_fine_and_the_staff_file_correctly(db):
    empire, team = firm_of(db)
    give_shares(db, empire["account_id"], "GGM", 0)
    issued = _one(db, "SELECT r.shares_in_issue FROM company_results r JOIN companies c ON c.id = r.company_id WHERE c.ticker = 'GGM'"
                      " ORDER BY r.period DESC LIMIT 1")["shares_in_issue"]
    ledger.transfer(db, payer=ledger.account_id(db, ledger.INVESTORS_PUBLIC), receiver=empire["account_id"], amount=issued // 15,
                    asset="SHR-GGM", kind="test_shares", memo="Test: shares")
    treasury = ledger.balance(db, ledger.account_id(db, ledger.TREASURY))
    quarters.close_due_quarters(db, after_quarters(9))
    fine = _one(db, "SELECT amount FROM empire_books WHERE empire_id = %s AND category = 'Fines'", (empire["id"],))
    assert fine and fine["amount"] > 0
    assert ledger.balance(db, ledger.account_id(db, ledger.TREASURY)) > treasury
    sound(db)


def test_a_duty_is_fixed_once_opened_handed_in_once_by_whoever_opened_it_and_its_answers_never_shown_before(db):
    empire, team = firm_of(db)
    duty = duty_of(db, empire["id"], "rm_liquidity")
    with pytest.raises(empires.EmpireError, match="falls to"):
        firm.open_duty(db, team["lawyer"], duty["id"], LATER)
    opened = firm.open_duty(db, team["risk_manager"], duty["id"], LATER)
    assert "_truth" not in str(opened)
    seen = firm.view(db, team["risk_manager"], LATER)
    assert "_truth" not in str(seen)
    with pytest.raises(Exception):
        db.execute("UPDATE desk_duties SET terms = '{}' WHERE id = %s", (duty["id"],))
    firm.hand_in(db, team["risk_manager"], duty["id"], {"stressed": 1, "can_pay": "no"}, LATER)
    with pytest.raises(empires.EmpireError, match="once"):
        firm.hand_in(db, team["risk_manager"], duty["id"], right(db, duty["id"]), LATER)
    with pytest.raises(Exception):
        db.execute("DELETE FROM desk_duties WHERE id = %s", (duty["id"],))


def test_a_duty_nobody_does_is_done_by_the_staff_or_missed_and_a_missed_one_costs_a_league_point(db):
    empire, team = firm_of(db)
    staffed = _one(db, "SELECT * FROM empires WHERE kind = 'computer' ORDER BY id")
    firm.view(db, team["head"], LATER)                     # the quarter's duties are set out when first looked at
    quarters.close_due_quarters(db, after_quarters(9))
    assert _dicts(db, "SELECT 1 FROM desk_duties WHERE empire_id = %s AND period = 9 AND by_staff", (staffed["id"],))
    assert not _dicts(db, "SELECT 1 FROM desk_duties WHERE empire_id = %s AND period = 9 AND status = 'missed'", (staffed["id"],))
    missed = _dicts(db, "SELECT id FROM desk_duties WHERE empire_id = %s AND period = 9 AND status = 'missed'", (empire["id"],))
    assert missed
    points = _one(db, "SELECT sum(points)::int AS p FROM league_points WHERE empire_id = %s AND reference LIKE 'duty:%%'", (empire["id"],))["p"]
    assert points == -len(missed)


# ---------------------------------------------------------------------------
# After the independent review
# ---------------------------------------------------------------------------

def test_a_bookkeeper_reports_on_a_clients_money_and_the_fee_is_shared_with_their_empire(db):
    empire, team = firm_of(db)
    client, client_account = pro(db, "lawyer", "client", cash_naira=2_000_000)
    ledger.transfer(db, payer=ledger.account_id(db, ledger.TREASURY), receiver=client_account, amount=naira(500_000), kind="test_cash",
                    memo="Test: money in", period=9)
    ledger.transfer(db, payer=client_account, receiver=ledger.account_id(db, ledger.TREASURY), amount=naira(120_000), kind="test_spend",
                    memo="Test: money out", period=9)
    from simulation import firm_clients
    quarters.close_due_quarters(db, after_quarters(9))
    now = after_quarters(9) + timedelta(hours=12)
    seen = firm_clients.view(db, client, now)
    key = next(a["key"] for a in seen["advisers"] if a["name"] == "ledgerman")
    assert str(team["accountant"]) not in str(seen)
    hired = firm_clients.hire(db, client, key, naira(100_000), now)
    with pytest.raises(empires.EmpireError, match="already hired"):
        firm_clients.hire(db, client, key, naira(100_000), now)
    shown = firm_clients.open_work(db, team["accountant"], hired["id"], now)
    assert "_truth" not in shown and shown["given"]
    truth = _one(db, "SELECT report FROM client_engagements WHERE id = %s", (hired["id"],))["report"]["_truth"]
    empire_cash = ledger.balance(db, empire["account_id"])
    done = firm_clients.deliver(db, team["accountant"], hired["id"], truth["net"], truth["biggest"], "Spend less on shares.", now)
    assert done["score"] == 100 and done["to_empire"] == naira(60_000)
    assert ledger.balance(db, empire["account_id"]) == empire_cash + naira(60_000)
    firm_clients.rate(db, client, hired["id"], 5, now)
    with pytest.raises(empires.EmpireError):
        firm_clients.rate(db, client, hired["id"], 1, now)
    sound(db)


def test_a_lawyers_draft_contract_waits_for_the_head_to_offer_it(db):
    empire, team = firm_of(db)
    draft = firm_people.offer_contract(db, team["lawyer"], team["journalist"], 0, 2000, 0, LATER)
    assert draft["status"] == "drafted"
    with pytest.raises(empires.EmpireError, match="no contract waiting"):
        firm_people.answer_contract(db, team["journalist"], draft["id"], True, LATER)
    firm_people.send_contract(db, team["head"], draft["id"], True, LATER)
    firm_people.answer_contract(db, team["journalist"], draft["id"], True, LATER)
    with pytest.raises(Exception):
        db.execute("UPDATE member_contracts SET notice_days = 14 WHERE id = %s", (draft["id"],))


def test_a_head_keeps_the_members_confidence_on_a_tie_or_when_nobody_votes(db):
    empire, team = firm_of(db)
    vote = firm.call_vote(db, empire, "confidence", "Confidence?", {"subject_id": str(team["head"])}, 9, LATER)
    firm.vote(db, team["journalist"], vote["id"], False, LATER)
    firm.vote(db, team["accountant"], vote["id"], True, LATER)
    firm.at_bell(db, NOW9 + timedelta(hours=49))
    assert _one(db, "SELECT status FROM empire_resolutions WHERE id = %s", (vote["id"],))["status"] == "passed"
    assert empires._empire(db, empire["id"])["head_player_id"] == team["head"]


def test_a_duty_opened_by_a_member_who_leaves_is_picked_up_by_a_colleague(db):
    empire, team = firm_of(db)
    other = member(db, empire, team["head"], "accountant", "second")
    duty = duty_of(db, empire["id"], "ac_close")
    firm.open_duty(db, team["accountant"], duty["id"], LATER)
    empires.sack(db, team["head"], team["accountant"], LATER)
    firm.open_duty(db, other, duty["id"], LATER)
    assert firm.hand_in(db, other, duty["id"], right(db, duty["id"]), LATER)["score"] == 100


def test_under_a_cheap_units_clause_the_organiser_takes_units_at_half_their_worth(db):
    empire, team = firm_of(db)
    asked = firm_money.design_raising(db, team["investment_banker"], "stake", naira(10_000_000), 0, LATER)
    firm.decide(db, team["accountant"], asked["approval_id"], True, "", LATER)
    firm.decide(db, team["risk_manager"], waiting(db, empire["id"], "raise_risk")["id"], True, "Fine.", LATER)
    paper = _one(db, "SELECT * FROM empire_documents WHERE empire_id = %s AND status = 'draft'", (empire["id"],))
    left_in = [c["code"] for c in paper["clauses"] if c["trap"] and c["code"] == "cheap_units"]
    firm.review_document(db, team["lawyer"], paper["id"], [c["code"] for c in paper["clauses"] if c["trap"] and c["code"] != "cheap_units"], LATER)
    firm.decide(db, team["head"], waiting(db, empire["id"], "raise_sign")["id"], True, "", LATER)
    offer = _one(db, "SELECT * FROM empire_stake_offers WHERE empire_id = %s", (empire["id"],))
    buyer, buyer_account = pro(db, "journalist", "investor", cash_naira=20_000_000)
    firm_money.buy_stake(db, buyer, offer["id"], naira(10_000_000), LATER)
    firm.at_bell(db, NOW9 + timedelta(days=4))
    outsiders = _one(db, "SELECT units FROM empire_units WHERE empire_id = %s AND player_id IS NULL", (empire["id"],))
    assert bool(outsiders) == bool(left_in)
    sound(db)
