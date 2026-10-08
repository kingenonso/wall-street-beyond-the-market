"""Private equity stage, part 1: the independent review of the firm.

Twenty-four loopholes were found by a reviewer who did not write the code; each test failed on the code as reviewed
and passes now that the loophole is closed. The numbers follow the review (fNN)."""

from __future__ import annotations

from datetime import timedelta

import pytest
from psycopg.rows import dict_row

from simulation import careers, empires, firm, firm_money, firm_people, firm_risk, firm_tasks, ledger, quarters
from simulation import bonds as bond_desk
from simulation.money import naira
from tests.conftest import after_quarters
from tests.test_builds import pro
from tests.test_careers import NOW9, sound
from tests.test_empires import founded
from tests.test_firm import firm_of, member, waiting
from tests.test_objectives import give_cash, give_shares

pytestmark = pytest.mark.world("eight")
LATER = NOW9 + timedelta(hours=1)
DAY2 = NOW9 + timedelta(days=1)
DAY3 = NOW9 + timedelta(days=2, hours=1)


def _dicts(db, sql, params=()):
    with db.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def _one(db, sql, params=()):
    rows = _dicts(db, sql, params)
    return rows[0] if rows else None


def _cash(db, player):
    return ledger.balance(db, ledger.player_account_id(db, player))


def _borrow(db, empire, team, amount_naira, kind="bond"):
    """The banker designs, the Accountant checks, the Risk Manager agrees, the Legal Counsel strikes every trap, the head signs."""
    asked = firm_money.design_raising(db, team["investment_banker"], kind, naira(amount_naira), 4, LATER)
    firm.decide(db, team["accountant"], asked["approval_id"], True, "", LATER)
    firm.decide(db, team["risk_manager"], waiting(db, empire["id"], "raise_risk")["id"], True, "It can carry it.", LATER)
    paper = _one(db, "SELECT * FROM empire_documents WHERE empire_id = %s AND status = 'draft'", (empire["id"],))
    firm.review_document(db, team["lawyer"], paper["id"], [c["code"] for c in paper["clauses"] if c["trap"]], LATER)
    firm.decide(db, team["head"], waiting(db, empire["id"], "raise_sign")["id"], True, "", LATER)


# ---------------------------------------------------------------------------
# 1. A debt in default is never collected again, and stops counting as owed
# ---------------------------------------------------------------------------

def test_f01_a_defaulted_debt_still_counts_as_owed_and_is_still_collected(db):
    """An empire that keeps its wealth in shares rather than cash cannot pay a quarter's interest from cash:
    it defaults. The debt is then marked 'defaulted', and nothing ever looks at it again: debt_of() no longer
    counts it (so the empire's worth jumps by the whole loan and it may borrow again), and no later close
    collects it, even when the empire has the cash. Money borrowed from the game's lenders is simply kept."""
    empire, team = firm_of(db)
    give_shares(db, empire["account_id"], "GGM", 300_000_000)
    _borrow(db, empire, team, 200_000_000)
    debt = _one(db, "SELECT * FROM empire_debts WHERE empire_id = %s", (empire["id"],))
    worth_before = empires.worth(db, empires._empire(db, empire["id"]), LATER)["total"]
    # The cash goes into something else (here: out of the empire, standing in for buying shares).
    ledger.transfer(db, payer=empire["account_id"], receiver=ledger.account_id(db, ledger.TREASURY),
                    amount=ledger.balance(db, empire["account_id"]) - 1, kind="test_cash", memo="Test: the cash is spent")
    closed = 9
    for closed in (9, 10, 11):
        quarters.close_due_quarters(db, after_quarters(closed))
        after = _one(db, "SELECT * FROM empire_debts WHERE id = %s", (debt["id"],))
        if after["status"] == "defaulted":
            break
    assert after["status"] in ("defaulted", "repaid")
    if after["status"] == "repaid":
        # The fix goes further than the review asked: what cash could not pay, the lender took in the empire's shares.
        assert firm.debt_of(db, empire["id"]) == 0 and _one(db, "SELECT 1 FROM ledger_transactions WHERE kind = 'empire_default'")
        sound(db)
        return
    assert after["outstanding"] > 0
    # Still owed: it must still count against the empire...
    assert firm.debt_of(db, empire["id"]) >= after["outstanding"], (
        f"a defaulted debt of {after['outstanding']} kobo is no longer counted as owed (debt_of = {firm.debt_of(db, empire['id'])})")
    # ...and once the empire has cash again, the lender must be paid at the next close.
    give_cash(db, empire["account_id"], 1_000_000_000)
    quarters.close_due_quarters(db, after_quarters(closed + 1))
    again = _one(db, "SELECT * FROM empire_debts WHERE id = %s", (debt["id"],))
    assert again["outstanding"] < after["outstanding"], "a defaulted debt is never collected, even when the empire has the cash"
    assert worth_before  # (kept for the report)
    sound(db)


# ---------------------------------------------------------------------------
# 2. Units are priced by a whole-kobo floor: new money dilutes the partners
# ---------------------------------------------------------------------------

def test_f02_new_capital_does_not_dilute_the_partners_already_in(db):
    """Units start at one per kobo, and unit_price() is worth // units, rounded DOWN to a whole kobo (and never
    below 1). When a unit is really worth 1.9 kobo, the price is 1 kobo: a member putting money in gets nearly twice
    the units they pay for, and the founder loses the difference."""
    empire, (head, _), partners = founded(db)
    firm_money.ensure_units(db, empire)
    units = firm_money.units_total(db, empire["id"])
    worth = empires.worth(db, empire, LATER)["total"]
    give_cash(db, empire["account_id"], (units * 19 // 10 - worth) // 100)          # a unit is now worth about 1.9 kobo
    empire = empires._empire(db, empire["id"])
    before_worth, before_units = empires.worth(db, empire, LATER)["total"], firm_money.units_total(db, empire["id"])
    founder_units = _one(db, "SELECT units FROM empire_units WHERE empire_id = %s AND player_id = %s", (empire["id"], head))["units"]
    founder_before = before_worth * founder_units // before_units
    journalist = partners["journalist"][0]
    give_cash(db, ledger.player_account_id(db, journalist), 10_000_000)
    empires.put_in(db, journalist, naira(10_000_000), 0, LATER)
    after_worth, after_units = empires.worth(db, empire, LATER)["total"], firm_money.units_total(db, empire["id"])
    founder_after = after_worth * founder_units // after_units
    assert founder_after >= founder_before * 99 // 100, (
        f"the founder's share fell from {founder_before} to {founder_after} kobo when a partner put ₦10m in at a rounded-down price")
    sound(db)


def test_f03_a_leaving_partner_is_bought_back_at_no_more_than_their_share_of_the_worth(db):
    """With 'buy back' in the constitution, a leaving partner is paid units x unit_price(). When the empire is
    worth less than one kobo a unit (always the case at first: the ₦25m registration fee comes out of the
    founders' money; or after any loss; or when it is worth nothing at all), unit_price() is 1 kobo, so the
    leaver is paid back everything they put in and the partners who stay carry the whole loss."""
    empire, (head, _), partners = founded(db)
    journalist, accountant = partners["journalist"][0], partners["accountant"][0]
    give_cash(db, ledger.player_account_id(db, journalist), 10_000_000)
    empires.put_in(db, journalist, naira(10_000_000), 0, LATER)
    vote = firm.propose(db, head, "constitution", {"leaver_units": "buy_back"}, LATER)
    firm.vote(db, accountant, vote["id"], True, LATER)
    assert firm.article(db, empire["id"], "leaver_units") == "buy_back"
    empire = empires._empire(db, empire["id"])
    worth, total = empires.worth(db, empire, LATER)["total"], firm_money.units_total(db, empire["id"])
    held = _one(db, "SELECT units FROM empire_units WHERE empire_id = %s AND player_id = %s", (empire["id"], journalist))["units"]
    fair = worth * held // total
    cash = _cash(db, journalist)
    empires.leave(db, journalist, LATER)
    paid = _cash(db, journalist) - cash
    assert paid <= fair * 101 // 100, f"the leaver was paid {paid} kobo for units whose share of the empire is worth {fair} kobo"
    sound(db)


# ---------------------------------------------------------------------------
# 3. The signing limit: genuine costs are not counted against a divert
# ---------------------------------------------------------------------------

def test_f04_genuine_costs_and_diverted_costs_come_out_of_one_signing_limit(db):
    """_pay_cost counts genuine costs and diverts together (firm_money._signed), but empires.divert counts only
    what was taken (empires._spent, kind = 'taken'). So a member who has signed for their whole limit in
    training can still divert up to the whole limit again, at once, below the expense threshold."""
    empire, team = firm_of(db)
    journalist = team["journalist"]
    seat = empires.seat_of(db, journalist)
    limit = empires.signing_limit(db, seat)
    assert limit == naira(500_000)
    firm_money.sign_cost(db, journalist, "training", naira(250_000), None, LATER)
    firm_money.sign_cost(db, journalist, "training", naira(250_000), None, LATER)
    with pytest.raises(empires.EmpireError, match="signing limit"):
        empires.divert(db, journalist, naira(250_000), LATER)


# ---------------------------------------------------------------------------
# 4. The expense threshold: split costs, and the Accountant's own costs
# ---------------------------------------------------------------------------

def test_f05_a_cost_split_into_pieces_under_the_threshold_still_reaches_the_accountant(db):
    """The threshold is tested on each signature alone. ₦1m taken in four signatures of ₦250,000 never reaches
    the Accountant's desk."""
    empire, team = firm_of(db)
    db.execute("UPDATE empires SET expense_limit = %s WHERE id = %s", (naira(5_000_000), empire["id"]))
    taken = [empires.divert(db, team["journalist"], naira(250_000), LATER) for _ in range(4)]
    assert any(t["waiting"] for t in taken), "₦1,000,000 was taken in one quarter in four pieces, and none of it waited for the Accountant"


def test_f06_the_accountants_own_cost_above_the_threshold_waits_for_somebody(db):
    """divert_needs_approval() lets any cost by an Accountant through at once, whatever its size: the one member
    whose costs nobody looks at is the one who approves everybody else's."""
    empire, team = firm_of(db)
    db.execute("UPDATE empires SET expense_limit = %s WHERE id = %s", (naira(5_000_000), empire["id"]))
    taken = empires.divert(db, team["accountant"], naira(4_000_000), LATER)
    assert taken["waiting"], "the Accountant took ₦4,000,000 at once, with nobody's approval"


def test_f07_a_divert_waiting_for_approval_cannot_be_told_from_a_genuine_cost(db):
    """The only genuine cost a member can sign is training, and its request is headed 'Training' and titled
    'Training for <name>'. A divert's request carries its desk's disguise heading instead. So every expense
    request that is not headed 'Training' is a theft, and the Accountant can see it."""
    empire, team = firm_of(db)
    db.execute("UPDATE empires SET expense_limit = %s WHERE id = %s", (naira(5_000_000), empire["id"]))
    stolen = empires.divert(db, team["journalist"], naira(400_000), LATER)
    honest = firm_money.sign_cost(db, team["journalist"], "training", naira(400_000), team["lawyer"], LATER)
    shown = {a["id"]: a for a in firm.view(db, team["accountant"], LATER)["approvals"]["to_decide"]}
    s, h = shown[stolen["approval_id"]], shown[honest["approval_id"]]
    genuine_headings = {h["detail"]["heading"]}
    assert s["title"].split(":")[0] == h["title"].split(":")[0] and s["detail"] == h["detail"], "the two requests can be told apart"
    assert s["detail"]["heading"] in genuine_headings, (
        f"a divert is headed {s['detail']['heading']!r}; every genuine request is headed {genuine_headings}: the heading gives it away")


# ---------------------------------------------------------------------------
# 5. Poaching pays a joining bonus outside the bonus limit
# ---------------------------------------------------------------------------

def _rival(db, cash_naira=50_000_000):
    rival_head, _ = pro(db, "asset_manager", "raider", level=20, cash_naira=60_000_000)
    rival = empires.found(db, rival_head, "Raider House", naira(40_000_000), 0, NOW9)
    for build, name in (("journalist", "r1"), ("accountant", "r2")):
        member(db, rival, rival_head, build, name)
    rival = empires.open_empire(db, rival_head, NOW9)
    give_cash(db, rival["account_id"], cash_naira)
    return empires._empire(db, rival["id"]), rival_head


def test_f08_a_poaching_bonus_is_inside_the_heads_bonus_limit(db):
    """match() pays its bonus through _pay_bonus_inside (checked against the limit); the poaching empire's
    joining bonus is paid with a bare transfer. A head can pay any member of another empire (a friend, or
    themselves through a partner) any amount of the empire's cash, far past the tenth of its worth allowed."""
    empire, team = firm_of(db)
    rival, rival_head = _rival(db)
    limit = empires.bonus_limit(db, rival, LATER)
    bonus = limit * 4
    assert ledger.balance(db, rival["account_id"]) > bonus
    try:
        offer = firm_people.poach(db, rival_head, team["risk_manager"], bonus, "Come over.", LATER)
        firm_people.answer_poach(db, team["risk_manager"], offer["id"], True, DAY3)
    except empires.EmpireError:
        pass
    paid = _one(db, "SELECT coalesce(sum(amount), 0)::bigint AS n FROM empire_books WHERE empire_id = %s AND kind = 'bonus'", (rival["id"],))["n"]
    assert paid <= limit, f"the poaching empire paid {paid} kobo in bonuses in a quarter; its head's limit is {limit}"
    sound(db)


# ---------------------------------------------------------------------------
# 6. The Risk Manager's freeze is ignored by a trade already waiting
# ---------------------------------------------------------------------------

def _trader_with_a_waiting_trade(db):
    empire, team = firm_of(db)
    trader = member(db, empire, team["head"], "asset_manager", "trader")
    db.execute("UPDATE empires SET trade_limit_bps = 10000 WHERE id = %s", (empire["id"],))
    firm_risk.set_trade_limit(db, team["risk_manager"], 1_000_000, LATER)
    held = empires.trade_shares(db, trader, ticker="GGM", side="buy", kind="limit", quantity=1_000_000, limit_price=2_000, now=LATER)          # about ₦20m, inside the day's price band
    assert held["waiting"]
    return empire, team, trader, held


def _orders(db, empire):
    return _one(db, "SELECT count(*) AS n FROM market_orders WHERE account_id = %s", (empire["account_id"],))["n"]


def test_f09_a_frozen_members_waiting_trade_is_not_carried_out_when_the_head_approves_it(db):
    """gate_trade refuses a frozen member's new trade, but _trade_execute (run when the head or deputy approves a
    trade that was waiting) never looks at the freeze: the kill switch does not stop what is already queued."""
    empire, team, trader, held = _trader_with_a_waiting_trade(db)
    firm_risk.freeze(db, team["risk_manager"], trader, True, "Reckless orders.", LATER)
    before = _orders(db, empire)
    try:
        firm.decide(db, team["head"], held["approval_id"], True, "I like the trade.", NOW9 + timedelta(hours=25))
    except empires.EmpireError:
        pass
    assert _orders(db, empire) == before, "a frozen member's order went to the exchange when the head approved it"


def test_f10_a_frozen_members_refused_trade_is_not_carried_out_by_an_overrule(db):
    empire, team, trader, held = _trader_with_a_waiting_trade(db)
    firm.decide(db, team["risk_manager"], held["approval_id"], False, "Too big.", LATER)
    firm_risk.freeze(db, team["risk_manager"], trader, True, "Reckless orders.", LATER)
    before = _orders(db, empire)
    try:
        firm.overrule(db, team["head"], held["approval_id"], "I like the trade.", LATER)
    except empires.EmpireError:
        pass
    assert _orders(db, empire) == before, "a frozen member's refused order went to the exchange when the head overruled"


def test_f11_a_bond_trade_above_the_risk_managers_limit_waits_like_a_share_trade(db):
    """empires.trade_bonds never calls firm_risk.gate_trade: the Risk Manager's limit for one trade (and the
    treasury policy check) do not apply to bonds at all."""
    empire, team = firm_of(db)
    trader = member(db, empire, team["head"], "asset_manager", "trader")
    db.execute("UPDATE empires SET trade_limit_bps = 10000 WHERE id = %s", (empire["id"],))
    firm_risk.set_trade_limit(db, team["risk_manager"], 1, LATER)                     # ₦1 a trade
    bond = next(b for b in bond_desk.listing(db, LATER) if b["issuer"] == "Federal Government")
    try:
        done = empires.trade_bonds(db, trader, code=bond["code"], side="buy", units=100, now=LATER)
    except empires.EmpireError as refused:
        done = {"refused": str(refused)}
    assert done.get("waiting") or "refused" in done, f"a bond trade far above the ₦1 limit went straight through: {done}"


# ---------------------------------------------------------------------------
# 7. Hidden information: a colleague's player number
# ---------------------------------------------------------------------------

def test_f12_a_raising_request_does_not_show_the_designers_player_number(db):
    """design_raising() puts designed_by = str(player_id) into the request's payload, and _raise_view hands the
    whole payload to every member who decides it (Accountant, Risk Manager, head): a colleague's player number."""
    empire, team = firm_of(db)
    firm_money.design_raising(db, team["investment_banker"], "bond", naira(60_000_000), 4, LATER)
    import server.main  # noqa: F401  (the routes import the app first)
    from server.firm_routes import wire
    seen = str(wire(firm.view(db, team["accountant"], LATER)))
    assert str(team["investment_banker"]) not in seen, "the Accountant's view carries the Investment Banker's player number"


# ---------------------------------------------------------------------------
# 8. A dividend voted on old figures is paid after a loss
# ---------------------------------------------------------------------------

def test_f13_a_dividend_is_not_paid_out_of_a_profit_that_is_no_longer_the_last_quarters(db):
    """_dividend_check tests the cap when the vote is proposed; _dividend_carry pays whatever was proposed when the
    vote passes, up to two days later. Proposed just before a quarter closes, it is paid in the next quarter even
    when that quarter closed with a loss (no profit to pay a dividend out of)."""
    empire, team = firm_of(db)
    db.execute("INSERT INTO empire_accounts (empire_id, period, figures) VALUES (%s, 8, %s)", (empire["id"], firm._json({"profit": naira(10_000_000)})))
    vote = firm.propose(db, team["accountant"], "dividend", {"amount": naira(5_000_000)}, after_quarters(9) - timedelta(hours=24))
    # The quarter closes with a loss (written as the close writes it).
    db.execute("INSERT INTO empire_accounts (empire_id, period, figures) VALUES (%s, 9, %s)", (empire["id"], firm._json({"profit": -naira(50_000_000)})))
    quarters.close_due_quarters(db, after_quarters(9))
    head_cash = _cash(db, team["head"])
    then = after_quarters(9) + timedelta(hours=2)
    try:
        for who in ("head", "journalist", "risk_manager"):
            firm.vote(db, team[who], vote["id"], True, then)
    except empires.EmpireError:
        pass
    assert _cash(db, team["head"]) == head_cash, "a dividend was paid after the last closed quarter made a loss of ₦50m"


# ---------------------------------------------------------------------------
# 9. A raise-money task finished by raising nothing
# ---------------------------------------------------------------------------

def test_f14_a_raise_money_task_is_not_finished_by_raising_one_kobo(db):
    """A stake has no least amount, and the raise-money task's last step is done when the head signs, before a
    single naira arrives. A stake offer of one kobo (which nobody need buy) finishes the task: 10 league points,
    every quarter, for nothing."""
    empire, team = firm_of(db)
    task = firm_tasks.start(db, team["head"], "raise_money", 1, LATER)
    with pytest.raises(empires.EmpireError, match="at least"):
        firm_money.design_raising(db, team["investment_banker"], "stake", 1, 0, LATER)
    asked = firm_money.design_raising(db, team["investment_banker"], "stake", naira(5_000_000), 0, LATER)
    firm.decide(db, team["accountant"], asked["approval_id"], True, "", LATER)
    firm.decide(db, team["risk_manager"], waiting(db, empire["id"], "raise_risk")["id"], True, "Harmless.", LATER)
    paper = _one(db, "SELECT * FROM empire_documents WHERE empire_id = %s AND status = 'draft'", (empire["id"],))
    firm.review_document(db, team["lawyer"], paper["id"], [c["code"] for c in paper["clauses"] if c["trap"]], LATER)
    firm.decide(db, team["head"], waiting(db, empire["id"], "raise_sign")["id"], True, "", LATER)
    points = _one(db, "SELECT coalesce(sum(points), 0)::int AS p FROM league_points WHERE empire_id = %s AND reference = %s",
                  (empire["id"], f"task:{task['id']}"))["p"]
    status = _one(db, "SELECT status FROM empire_tasks WHERE id = %s", (task["id"],))["status"]
    assert status != "done" and points == 0, f"a raise-money task was finished ({points} league points) before any money came in"


# ---------------------------------------------------------------------------
# 10. Deciding a request about yourself
# ---------------------------------------------------------------------------

def test_f15_the_deputy_does_not_approve_a_bonus_pool_that_pays_the_deputy(db):
    """deciders() only keeps out whoever asked. The Accountant proposes a bonus pool that pays the deputy; when
    the head has not answered in two days the deputy approves it, and pays themselves."""
    empire, team = firm_of(db)
    firm.name_title(db, team["head"], team["lawyer"], "deputy", NOW9)
    asked = firm_money.propose_bonuses(db, team["accountant"], {str(team["lawyer"]): naira(1_000_000)}, LATER)
    cash = _cash(db, team["lawyer"])
    try:
        firm.decide(db, team["lawyer"], asked["approval_id"], True, "", NOW9 + timedelta(hours=49))
    except empires.EmpireError:
        pass
    assert _cash(db, team["lawyer"]) == cash, "the deputy approved a bonus pool paying the deputy ₦1,000,000"


def test_f16_an_accountant_does_not_approve_a_cost_paid_for_themselves(db):
    """The head signs training for the Accountant above the threshold; it goes to the Accountant's desk, and the
    Accountant approves the request that is for the Accountant."""
    empire, team = firm_of(db)
    asked = firm_money.sign_cost(db, team["head"], "training", naira(400_000), team["accountant"], LATER)
    assert asked["waiting"]
    may = firm.deciders(db, waiting(db, empire["id"], "expense"), LATER)
    assert team["accountant"] not in may, "the Accountant may decide a request that is for the Accountant"


# ---------------------------------------------------------------------------
# 11. Acting for the head: a Legal Counsel offers a contract the head never saw
# ---------------------------------------------------------------------------

def test_f17_a_lawyers_draft_contract_waits_for_the_head_to_offer_it(db):
    """offer_contract() writes a Legal Counsel's draft straight in as offered by the head (offered_by = the head) and
    the member may sign it at once. The head never sees it: a Legal Counsel can give a colleague a 0-day notice (so they
    can leave for a rival at once) or a 20% share of the desk's pool, in the empire's name."""
    empire, team = firm_of(db)
    contract = firm_people.offer_contract(db, team["lawyer"], team["journalist"], 0, 2000, 0, LATER)
    try:
        firm_people.answer_contract(db, team["journalist"], contract["id"], True, LATER)
    except empires.EmpireError:
        pass
    row = _one(db, "SELECT * FROM member_contracts WHERE id = %s", (contract["id"],))
    assert row["status"] != "signed", "a contract the head never offered was signed, recorded as offered by the head"


# ---------------------------------------------------------------------------
# 12. Permanent records that can still be changed
# ---------------------------------------------------------------------------

def test_f18_a_decided_request_cannot_be_rewritten(db):
    """empire_approvals_guard stops the status changing, but not who decided, in what capacity, why, or the
    payload: a decided request's record can be rewritten after the fact."""
    empire, team = firm_of(db)
    request = firm.ask(db, empire, kind="note", desk="lawyer", asked_by=team["accountant"], title="A question", period=9, now=NOW9)
    firm.decide(db, team["lawyer"], request["id"], False, "No.", LATER)
    with pytest.raises(Exception):
        db.execute("UPDATE empire_approvals SET reason = 'Yes, of course.', decided_by = %s, decided_as = 'head', payload = '{\"x\": 1}' WHERE id = %s",
                   (team["head"], request["id"]))


def test_f19_the_heads_record_cannot_be_rewritten(db):
    """ceo_records is guarded against DELETE only: an overrule on a head's permanent record can be reworded,
    marked good, or moved to another player."""
    empire, team = firm_of(db)
    firm.ceo_note(db, team["head"], empire["id"], "overrule", "Overruled the Risk Manager.", 9, LATER, reference="test:1")
    with pytest.raises(Exception):
        db.execute("UPDATE ceo_records SET words = 'Nothing happened.', good = true, player_id = %s WHERE reference = 'test:1'",
                   (team["journalist"],))


def test_f20_a_counted_vote_cannot_be_rewritten(db):
    """empire_resolutions and empire_resolution_votes have no guard at all: a passed vote, its outcome and the
    votes cast can be changed or deleted."""
    empire, team = firm_of(db)
    vote = firm.propose(db, team["risk_manager"], "treasury", {"cash_least_bps": 2000, "shares_most_bps": 5000}, LATER)
    for who in ("head", "journalist", "accountant"):
        firm.vote(db, team[who], vote["id"], True, LATER)
    assert _one(db, "SELECT status FROM empire_resolutions WHERE id = %s", (vote["id"],))["status"] == "passed"
    with pytest.raises(Exception):
        db.execute("UPDATE empire_resolutions SET status = 'failed', outcome = 'Rewritten.' WHERE id = %s", (vote["id"],))
    with pytest.raises(Exception):
        db.execute("DELETE FROM empire_resolution_votes WHERE resolution_id = %s", (vote["id"],))


# ---------------------------------------------------------------------------
# 13. Insurance pays an intraday paper move, not a loss
# ---------------------------------------------------------------------------

def test_f21_holding_cover_pays_only_a_loss_that_is_still_there_when_the_claim_is_settled(db, monkeypatch):
    """A 'holding collapses' event fixes its 'loss' (shares x the day's fall) when it is drawn. Two days later the
    claim is paid from that figure, without looking again: the price may have come all the way back, and the
    insurer still pays the whole fall in cash."""
    empire, team = firm_of(db)
    held = give_shares(db, empire["account_id"], "GGM", 500_000_000)
    insurer = firm_tasks._insurers(db)[0]
    firm_tasks.buy_cover(db, team["risk_manager"], "holding_collapse", insurer["id"], naira(20_000_000), LATER)
    ggm = _one(db, "SELECT m.* FROM market_instruments m JOIN companies c ON c.id = m.company_id WHERE c.ticker = 'GGM'")
    from simulation import exchange
    day, _ = exchange.session_of(DAY2)
    reference = ggm["last_price"] or ggm["reference_price"]
    # The day's trading takes GGM 10% down ...
    db.execute("UPDATE market_instruments SET reference_price = %s, last_price = %s, session_date = %s WHERE company_id = %s",
               (reference, reference * 9 // 10, day, ggm["company_id"]))
    monkeypatch.setattr(firm_tasks, "_roll", lambda conn, *parts: 0)
    firm_tasks._open_happenings(db, DAY2)
    event = _one(db, "SELECT * FROM empire_happenings WHERE empire_id = %s", (empire["id"],))
    assert event and event["kind"] == "holding_collapse" and event["payload"]["loss"] > 0
    # ... and it comes all the way back before the event is settled. The empire still holds every share.
    db.execute("UPDATE market_instruments SET last_price = %s WHERE company_id = %s", (reference, ggm["company_id"]))
    firm_tasks._settle_happenings(db, DAY2 + timedelta(hours=49))
    settled = _one(db, "SELECT * FROM empire_happenings WHERE id = %s", (event["id"],))
    assert ledger.balance(db, empire["account_id"], f"SHR-GGM") >= held
    assert settled["covered"] == 0, f"the insurer paid {settled['covered']} kobo for a fall that had fully reversed"


# ---------------------------------------------------------------------------
# 14. A sacked thief is paid out their units while still owing the empire
# ---------------------------------------------------------------------------

def test_f22_a_thief_sacked_owing_the_empire_is_not_paid_cash_for_their_units_first(db):
    """_punish takes what the thief has in cash, writes the rest as a debt collected at a quarter of each pay day,
    then vacates the seat; with 'buy back' in the constitution, on_vacate then pays the thief cash for every unit
    (at the rounded-up price). The empire hands the thief cash while the thief still owes it."""
    empire, (head, _), partners = founded(db)
    journalist, accountant = partners["journalist"][0], partners["accountant"][0]
    give_cash(db, ledger.player_account_id(db, journalist), 10_000_000)
    empires.put_in(db, journalist, naira(10_000_000), 0, LATER)
    vote = firm.propose(db, head, "constitution", {"leaver_units": "buy_back"}, LATER)
    firm.vote(db, accountant, vote["id"], True, LATER)
    taken = empires.divert(db, journalist, naira(200_000), LATER)
    book = _one(db, "SELECT * FROM empire_books WHERE id = %s", (taken["book_id"],))
    # The thief spends what they took (and has nothing else in cash).
    ledger.transfer(db, payer=ledger.player_account_id(db, journalist), receiver=ledger.account_id(db, ledger.TREASURY),
                    amount=_cash(db, journalist), kind="test_cash", memo="Test: spent")
    audit = _one(db, "INSERT INTO empire_audits (empire_id, kind, auditor_id, period, from_period, to_period, at) VALUES (%s, 'accountant', %s, 9, 9, 9, %s)"
                     " RETURNING id", (empire["id"], accountant, LATER))["id"]
    case = empires._prove(db, empires._empire(db, empire["id"]), book, audit, LATER)
    empires.decide_case(db, head, case["id"], True, LATER)
    case = _one(db, "SELECT * FROM empire_cases WHERE id = %s", (case["id"],))
    assert empires.seat_of(db, journalist) is None
    paid_out = _cash(db, journalist)
    assert case["debt_left"] == 0 or paid_out == 0, (
        f"the sacked thief still owes {case['debt_left']} kobo, and was paid {paid_out} kobo for their units as they left")
    sound(db)


# ---------------------------------------------------------------------------
# 15. A lost vote of confidence can make a member with a theft case Acting Head
# ---------------------------------------------------------------------------

def test_f23_a_member_with_a_theft_case_waiting_does_not_become_acting_head_after_a_lost_vote(db):
    """empires._succession keeps out members with a theft case waiting; _confidence_failed takes the most
    experienced member whatever is waiting against them."""
    empire, team = firm_of(db)
    db.execute("UPDATE empires SET expense_limit = %s WHERE id = %s", (naira(5_000_000), empire["id"]))
    taken = empires.divert(db, team["journalist"], naira(200_000), LATER)
    book = _one(db, "SELECT * FROM empire_books WHERE id = %s", (taken["book_id"],))
    audit = _one(db, "INSERT INTO empire_audits (empire_id, kind, auditor_id, period, from_period, to_period, at) VALUES (%s, 'accountant', %s, 9, 9, 9, %s)"
                     " RETURNING id", (empire["id"], team["accountant"], LATER))["id"]
    case = empires._prove(db, empires._empire(db, empire["id"]), book, audit, LATER)
    assert _one(db, "SELECT status FROM empire_cases WHERE id = %s", (case["id"],))["status"] == "open"
    db.execute("UPDATE careers SET experience = %s WHERE player_id = %s", (careers.experience_for(45), team["journalist"]))
    vote = firm.call_vote(db, empire, "confidence", "Confidence?", {"subject_id": str(team["head"])}, 9, LATER)
    for who in ("accountant", "risk_manager", "lawyer"):
        firm.vote(db, team[who], vote["id"], False, LATER)
    head = empires._empire(db, empire["id"])["head_player_id"]
    assert head != team["journalist"], "a member with a theft case waiting became Acting Head (and now decides cases)"


# ---------------------------------------------------------------------------
# 16. The head's record: a lifted freeze is judged by somebody else's request
# ---------------------------------------------------------------------------

def test_f24_a_lifted_freeze_on_the_heads_record_is_not_judged_by_an_unrelated_request(db):
    """freeze() writes the head's lifting of a freeze as kind 'overrule' with reference 'unfreeze:<seat id>:<time>'.
    _settle_overrules reads every 'overrule' note's reference as 'approval:<id>' and looks up the request whose id
    is the SEAT id: an unrelated request (of any empire) then decides whether the head's record shows it as good
    or bad, for good."""
    empire, team = firm_of(db)
    trader = member(db, empire, team["head"], "asset_manager", "trader")
    seat_id = empires.seat_of(db, trader)["id"]
    # Requests are numbered from 1; make sure one numbered like the trader's seat exists: a losing trade bet.
    while True:
        asked = firm.ask(db, empire, kind="trade", desk="risk_manager", asked_by=team["head"], title="Somebody else's trade", period=9, now=NOW9,
                         payload={"ticker": "GGM", "side": "buy", "limit_price": 10**9, "why": []})
        if asked["id"] >= seat_id:
            break
    firm_risk.freeze(db, team["risk_manager"], trader, True, "Reckless.", LATER)
    firm_risk.freeze(db, team["head"], trader, False, "I will watch them.", LATER)
    note = _one(db, "SELECT * FROM ceo_records WHERE player_id = %s AND reference LIKE 'unfreeze:%%'", (team["head"],))
    assert note is not None and note["good"] is None
    quarters.close_due_quarters(db, after_quarters(9))
    quarters.close_due_quarters(db, after_quarters(10))
    note = _one(db, "SELECT * FROM ceo_records WHERE id = %s", (note["id"],))
    assert note["good"] is None, f"lifting a freeze was marked good={note['good']} on the head's permanent record, from request {seat_id}"
