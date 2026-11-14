"""Stage 6: the holes an independent reviewer found, each kept closed by a test.

The reviewer did not write the code. It attacked Stage 6 with 39 tests of its own and found 21
holes and a handful of smaller things. None made or destroyed money. Each is closed here."""

from __future__ import annotations

from datetime import timedelta

import psycopg
import pytest
from psycopg.rows import dict_row

from simulation import bonds, careers, desks_more, empires, exchange, ledger, marketview, objectives, pensionfunds, quarters
from simulation import world_data as data
from simulation.money import apply_bps, naira
from tests.conftest import ADULT, WORLD_START, after_quarters, join
from tests.test_builds import pro
from tests.test_careers import NOW9, professional, sound
from tests.test_empires import countersigned, always, computer_empire, founded, thief_in
from tests.test_objectives import bell, give_cash, give_shares, state_of
from tests.test_savings import a_fund, joined, savings

pytestmark = pytest.mark.world("eight")
LATE9 = WORLD_START + timedelta(weeks=9) - timedelta(minutes=30)
GAP9 = after_quarters(9) + timedelta(minutes=1)


def _d(db, sql, p=()):
    with db.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, p).fetchall()


def _share(db, ticker):
    return next(s for s in marketview._shares(db, exchange.session_of(NOW9)[0]) if s["ticker"] == ticker)


# 1. An Asset Manager sold their own shares to a computer-run empire at the top of the day's price band.
def test_a_member_cannot_deal_with_their_own_empire_and_a_computer_run_empire_deals_near_the_market(db):
    empire = _d(db, "SELECT e.*, c.ticker FROM empires e JOIN empire_tasks t ON t.empire_id = e.id JOIN companies c ON c.id = t.company_id"
                    " WHERE t.status = 'open' ORDER BY e.id LIMIT 1")[0]
    ticker = empire["ticker"]
    am, account = pro(db, "asset_manager", "dealer", level=1)
    shares = give_shares(db, account, ticker, 50_000_000)
    share = _share(db, ticker)
    low, high = exchange.price_limits(share["reference"])
    empires.apply(db, am, empire["id"], NOW9)
    # What a player may trade for an empire the computer runs is a small share of it, and goes by their rank.
    room = empires.war_room(db, am, NOW9)
    assert abs(room["trade_limit"] - room["worth"] * data.COMPUTER_EMPIRE_TRADE_BPS[0] // 10_000) <= 1
    # The staff's own purchase is waiting in this share: the member cannot sell into it themselves.
    with pytest.raises(empires.EmpireError, match="cannot deal with it yourself"):
        empires.own_order_allowed(db, account, share["id"], "sell")
    for order in _d(db, "SELECT id FROM market_orders WHERE account_id = %s AND status = 'open'", (empire["account_id"],)):
        exchange.cancel_order(db, account=empire["account_id"], order_id=order["id"], now=NOW9)
    exchange.place_order(db, account=account, ticker=ticker, side="sell", kind="limit", quantity=shares, limit_price=high, now=NOW9)
    with pytest.raises(empires.EmpireError, match="2% above"):
        empires.trade_shares(db, am, ticker=ticker, side="buy", kind="limit", quantity=10, limit_price=high, now=NOW9)
    with pytest.raises(empires.EmpireError, match="price you name"):
        empires.trade_shares(db, am, ticker=ticker, side="buy", kind="market", quantity=10, limit_price=None, now=NOW9)
    with pytest.raises(empires.EmpireError, match="cannot deal with its own people"):
        empires.trade_shares(db, am, ticker=ticker, side="buy", kind="limit", quantity=10, limit_price=share["reference"], now=NOW9)
    assert ledger.balance(db, account) == 0
    sound(db)


def test_the_website_refuses_a_players_own_order_against_their_empires(db, client):
    assert join(client, ADULT).status_code == 201
    client.put("/api/career/build", json={"build": "asset_manager"})
    task = _d(db, "SELECT e.id, e.account_id, c.ticker FROM empires e JOIN empire_tasks t ON t.empire_id = e.id JOIN companies c ON c.id = t.company_id"
                  " WHERE t.status = 'open' ORDER BY e.id LIMIT 1")[0]
    client.post(f"/api/empires/{task['id']}/applications")
    price = _share(db, task["ticker"])["reference"]
    refused = client.post("/api/market/orders", json={"ticker": task["ticker"], "side": "sell", "kind": "limit", "quantity": 1, "limit_price_kobo": price})
    assert refused.status_code == 409 and "empire" in refused.json()["detail"]


# 2. A locked pension was turned into cash by trading between a fund and its manager.
def test_a_pension_fund_deals_near_the_market_never_with_its_manager_and_is_not_churned(db):
    fund, manager, account = a_fund(db, fee_bps=0)
    saver, _ = professional(db, "saver", now=NOW9)
    savings(db, saver, 10_000_000)
    joined(db, saver, fund)
    share = _share(db, "ABA")
    low, high = exchange.price_limits(share["reference"])
    give_shares(db, account, "ABA", 9_000_000)
    exchange.place_order(db, account=account, ticker="ABA", side="sell", kind="limit", quantity=100, limit_price=share["reference"], now=NOW9)
    with pytest.raises(pensionfunds.FundError, match="2% above"):
        pensionfunds.trade_shares(db, manager, ticker="ABA", side="buy", kind="limit", quantity=100, limit_price=high, now=NOW9)
    with pytest.raises(pensionfunds.FundError, match="cannot deal with its own people"):
        pensionfunds.trade_shares(db, manager, ticker="ABA", side="buy", kind="limit", quantity=100, limit_price=share["reference"], now=NOW9)
    with pytest.raises(pensionfunds.FundError, match="price you name"):
        pensionfunds.trade_shares(db, manager, ticker="ABA", side="buy", kind="market", quantity=100, limit_price=None, now=NOW9)
    # And the other way round: with the fund's order waiting, the manager's own order is refused.
    for order in _d(db, "SELECT id FROM market_orders WHERE account_id = %s AND status = 'open'", (account,)):
        exchange.cancel_order(db, account=account, order_id=order["id"], now=NOW9)
    pensionfunds.trade_shares(db, manager, ticker="ABA", side="buy", kind="limit", quantity=100, limit_price=apply_bps(share["reference"], 9_900), now=NOW9)
    with pytest.raises(empires.EmpireError, match="cannot deal with it yourself"):
        empires.own_order_allowed(db, account, share["id"], "sell")
    # A fund may trade its own worth once in a quarter.
    bill = next(b for b in bonds.listing(db, NOW9) if b["kind"] == "bill")
    with pytest.raises(pensionfunds.FundError, match="once in a quarter"):
        for _ in range(4):
            pensionfunds.trade_bonds(db, manager, code=bill["code"], side="buy", units=4_000, now=NOW9)
            pensionfunds.trade_bonds(db, manager, code=bill["code"], side="sell", units=4_000, now=NOW9)
    sound(db)


# 3. One kobo taken made a computer-run empire pay tens of millions for an AI audit.
def test_the_computer_pays_for_the_ai_audit_only_when_there_is_more_at_stake_than_its_fee(db, monkeypatch):
    monkeypatch.setattr(data, "AUDIT_SEASON_EVERY", 3)
    empire, pool = computer_empire(db), ledger.account_id(db, ledger.PRIZE_POOL)
    always(monkeypatch, True)
    thief, _ = thief_in(db, empire, cash=1)
    empires.divert(db, thief, 1, NOW9)
    before = ledger.balance(db, pool)
    empires._computer_head(db, empire, 9, NOW9)
    assert ledger.balance(db, pool) == before and not _d(db, "SELECT 1 FROM empire_audits WHERE kind = 'ai'")
    fund, manager, _ = a_fund(db)
    saver, _ = professional(db, "saver", now=NOW9)
    savings(db, saver, 10_000_000)
    joined(db, saver, fund)
    always(monkeypatch, False)
    pensionfunds.divert(db, manager, 1, NOW9)
    cash = ledger.balance(db, fund["account_id"])
    pensionfunds._regulator_audit(db, pensionfunds._fund(db, fund["id"]), 9, NOW9)
    assert ledger.balance(db, fund["account_id"]) == cash
    sound(db)


# 4. The signing limit was multiplied by moving from empire to empire.
def test_a_signing_limit_is_the_players_for_the_quarter_wherever_they_sit(db):
    thief, account = thief_in(db, computer_empire(db))
    empires.divert(db, thief, naira(500_000), NOW9)
    for n in range(1, 5):
        empires.leave(db, thief, NOW9)
        empires.apply(db, thief, computer_empire(db, n)["id"], NOW9)
        with pytest.raises(empires.EmpireError, match="signing limit"):
            empires.divert(db, thief, naira(1), NOW9)
    assert ledger.balance(db, account) == naira(500_000)


# 5. Joining or leaving a player's fund on the last day picked the quarter's return after seeing it.
def test_moving_into_or_out_of_a_players_fund_takes_effect_as_the_quarter_closes(db):
    fund, manager, _ = a_fund(db, fee_bps=0)
    saver, _ = professional(db, "saver", now=NOW9)
    dodger, _ = professional(db, "dodger", now=NOW9)
    savings(db, saver, 10_000_000)
    savings(db, dodger, 10_000_000)
    joined(db, saver, fund)
    assert pensionfunds.leave(db, saver, LATE9)["done"] is False                 # asked on the last day: still in the fund for this quarter
    pensionfunds.join(db, dodger, fund["id"], LATE9)
    assert quarters.close_due_quarters(db, after_quarters(9)) == [9]
    left = _d(db, "SELECT * FROM retirement_entries WHERE player_id = %s AND period = 9", (saver,))[0]
    assert left["fund"] == "managed" and abs(left["growth"]) <= 100              # the fund sat in cash: that is the quarter they had
    came = _d(db, "SELECT * FROM retirement_entries WHERE player_id = %s AND period = 9", (dodger,))[0]
    earned = _d(db, "SELECT return_bps FROM pension_fund_results WHERE period = 9 AND fund = 'balanced'")[0]["return_bps"]
    assert came["fund"] == "balanced" and came["growth"] == apply_bps(came["opening"], earned) != 0
    assert _d(db, "SELECT managed_fund_id FROM retirement_accounts WHERE player_id = %s", (dodger,))[0]["managed_fund_id"] == fund["id"]
    assert _d(db, "SELECT managed_fund_id FROM retirement_accounts WHERE player_id = %s", (saver,))[0]["managed_fund_id"] is None
    sound(db)


# 6. The early withdrawal was cashed by founding and cancelling: see test_savings (it now goes into the empire, and back).
def test_a_partners_early_withdrawal_also_goes_back_to_their_savings_when_the_founding_is_cancelled(db):
    empire, (head, _), partners = founded(db, open_it=False, put_in=20_000_000)
    scribe, scribe_account = partners["investment_banker"]
    savings(db, scribe, 4_000_000)
    before = ledger.balance(db, scribe_account)
    empires.put_in(db, scribe, 0, naira(2_000_000), NOW9)
    assert ledger.balance(db, scribe_account) == before
    empires.cancel_founding(db, head, NOW9)
    assert ledger.balance(db, scribe_account) == before
    assert _d(db, "SELECT value FROM retirement_accounts WHERE player_id = %s", (scribe,))[0]["value"] == naira(4_000_000)
    sound(db)


# 7. A thief who left before the audit was never "sacked", and walked straight back in.
def test_a_thief_who_left_before_the_audit_is_still_kept_out(db, monkeypatch):
    empire = computer_empire(db)
    thief, _ = thief_in(db, empire, cash=2_000_000)
    empires.divert(db, thief, naira(300_000), NOW9)
    empires.leave(db, thief, NOW9)
    always(monkeypatch, True)
    assert empires._staff_audit(db, empire, 9, NOW9) == 1
    with pytest.raises(empires.EmpireError, match="sacked you"):
        empires.apply(db, thief, empire["id"], NOW9)


# 8. A thief who became head forgave their own case.
def test_nobody_decides_their_own_case_and_an_accused_member_does_not_become_head(db, monkeypatch):
    empire, (head, _), partners = founded(db)
    scribe, ledgerman = partners["investment_banker"][0], partners["asset_manager"][0]
    careers.add_experience(db, scribe, "investment_banker", 5000, NOW9)
    empires.set_limits(db, head, expense_limit=naira(500_000))
    countersigned(db, empires.divert(db, scribe, naira(400_000), NOW9), ledgerman, NOW9)
    always(monkeypatch, True)
    audit = empires.accountant_audit(db, ledgerman, NOW9)
    empires.file_audit(db, ledgerman, audit["id"], [f["book_id"] for f in audit["findings"]], NOW9)
    empires.leave(db, head, NOW9)
    assert _d(db, "SELECT head_player_id FROM empires WHERE id = %s", (empire["id"],))[0]["head_player_id"] == ledgerman
    # And if the accused is the only one left, the case is decided in full, as a computer-run empire decides it.
    empires.leave(db, ledgerman, NOW9)
    assert _d(db, "SELECT status FROM empire_cases")[0]["status"] == "punished" and empires.seat_of(db, scribe) is None
    assert _d(db, "SELECT kind FROM legal_records WHERE player_id = %s", (scribe,))


# 9 and 10. A bonus could be paid out of an empire still being founded, and a head could empty an open one with a single bonus.
def test_pooled_money_cannot_be_spent_before_the_empire_opens_and_bonuses_are_capped(db):
    empire, (head, _), partners = founded(db, open_it=False, put_in=20_000_000)
    scribe = partners["investment_banker"][0]
    with pytest.raises(empires.EmpireError, match="not open yet"):
        empires.pay_bonus(db, head, scribe, naira(1_000), "thanks", NOW9)
    with pytest.raises(empires.EmpireError, match="not open yet"):
        empires.staff_seat(db, head, "investment_banker", 1, True, NOW9)
    empires.cancel_founding(db, head, NOW9)
    sound(db)


def test_a_head_cannot_empty_the_empire_through_bonuses(db):
    empire, (head, _), partners = founded(db)
    scribe = partners["investment_banker"][0]
    cash = ledger.balance(db, empire["account_id"])
    with pytest.raises(empires.EmpireError, match="a tenth of the empire's worth"):
        empires.pay_bonus(db, head, scribe, cash, "for services", NOW9)
    empires.pay_bonus(db, head, scribe, cash // 10, "for services", NOW9)
    with pytest.raises(empires.EmpireError, match="a tenth of the empire's worth"):
        empires.pay_bonus(db, head, scribe, cash // 100, "again", NOW9)


# 11. The heading alone said which entries were false, and whose.
def test_genuine_costs_and_false_ones_share_their_headings(db):
    empire = computer_empire(db)
    thief, _ = thief_in(db, empire, "investment_banker", "mallam", cash=1_000_000)
    watcher, _ = thief_in(db, empire, "investment_banker", "watcher")
    empires.divert(db, thief, naira(200_000), NOW9)
    room = empires.war_room(db, watcher, NOW9)
    legal = [b for b in room["books"] if b["category"] == "Advisory and legal fees"]
    truth = {r["id"] for r in _d(db, "SELECT id FROM empire_books WHERE empire_id = %s AND NOT genuine", (empire["id"],))}
    assert len(legal) > len(truth) == 1 and len({b["description"] for b in legal}) == 1
    assert "kind" not in room["books"][0]
    # Colleagues' identifiers are for the head alone.
    assert [s["player_id"] for s in room["seats"] if s["held"] and not s["you"]] == [None]


# 12. Staff worked all quarter and were let go before pay day.
def test_staff_who_are_let_go_are_paid_for_the_quarter_and_the_audit_still_happens(db, monkeypatch):
    empire, (head, _), partners = founded(db)
    scribe = partners["investment_banker"][0]
    empires.staff_seat(db, head, "asset_manager", 2, True, NOW9)
    empires.set_limits(db, head, expense_limit=naira(500_000))
    empires.divert(db, scribe, naira(100_000), NOW9)
    cash = ledger.balance(db, empire["account_id"])
    empires.staff_seat(db, head, "asset_manager", 2, False, LATE9)
    salary = empires._staff_salary(db, LATE9)
    assert ledger.balance(db, empire["account_id"]) == cash - salary
    always(monkeypatch, True)
    assert quarters.close_due_quarters(db, after_quarters(9)) == [9]
    assert _d(db, "SELECT 1 FROM empire_cases WHERE empire_id = %s", (empire["id"],))      # the staff Accountant's audit was not dodged
    sound(db)


# 13. Pacts without limit, and a colleague "uncovering" one for experience and reputation.
def test_one_pact_of_a_kind_between_two_empires_and_no_reward_for_uncovering_your_own_or_a_lawful_one(db, monkeypatch):
    empire, (head, _), partners = founded(db)
    scribe = partners["investment_banker"][0]
    other = computer_empire(db)
    empires.staff_seat(db, head, "investment_banker", 1, True, NOW9)
    pact = empires.draft_pact(db, head, other["id"], "alliance", "We stand together against all comers.", NOW9)
    assert empires.sign_pact(db, head, pact["id"], NOW9)["status"] == "signed"
    with pytest.raises(empires.EmpireError, match="already have a pact of that kind"):
        empires.draft_pact(db, head, other["id"], "alliance", "We stand together against all comers.", NOW9)
    always(monkeypatch, True)
    with pytest.raises(empires.EmpireError, match="does not investigate the empire they sit in"):
        empires.investigate(db, scribe, empire["id"], NOW9)
    assert empires.investigate(db, scribe, other["id"], NOW9)["found"] is False            # their own empire's pact is not theirs to uncover
    reporter, _ = pro(db, "investment_banker", "reporter")
    before = careers.career(db, reporter, "investment_banker")["experience"]
    assert empires.investigate(db, reporter, other["id"], NOW9)["found"] is True
    assert careers.career(db, reporter, "investment_banker")["experience"] == before               # a lawful pact coming to light is only news


# 14. An Asset Manager hopped between computer-run empires and was paid for the same step in each.
def test_one_step_of_each_kind_a_quarter_and_the_staffs_order_does_not_count_as_the_players_purchase(db):
    am, account = pro(db, "asset_manager", "hopper", level=1)
    first, second = computer_empire(db, 0), computer_empire(db, 1)
    empires.apply(db, am, first["id"], NOW9)
    step = next(s for s in empires.war_room(db, am, NOW9)["task"]["steps"] if s["status"] == "current")
    taken = empires.take_step(db, am, step["id"], NOW9)
    assert not _d(db, "SELECT 1 FROM market_orders WHERE account_id = %s AND status = 'open'", (first["account_id"],))
    # Buying what the task calls for is outside the member's own limit, but still near the market.
    terms = state_of(db, taken["id"])["terms"]
    share = _share(db, terms["client"]["ticker"])
    empires.trade_shares(db, am, ticker=share["ticker"], side="buy", kind="limit", quantity=terms["need"], limit_price=share["reference"], now=NOW9)
    with pytest.raises(empires.EmpireError, match="trading limit"):
        empires.trade_shares(db, am, ticker=share["ticker"], side="buy", kind="limit", quantity=terms["need"], limit_price=share["reference"], now=NOW9)
    objectives.withdraw(db, am, taken["id"], NOW9)
    empires.leave(db, am, NOW9)
    empires.apply(db, am, second["id"], NOW9)
    step = next(s for s in empires.war_room(db, am, NOW9)["task"]["steps"] if s["status"] == "current")
    with pytest.raises(empires.EmpireError, match="One of each kind a quarter"):
        empires.take_step(db, am, step["id"], NOW9)
    sound(db)


# 15. A bond priced above its face value passed the trading limit.
def test_the_trading_limit_is_checked_against_what_a_bond_trade_really_comes_to(db):
    empire, (head, _), partners = founded(db, cash=400_000_000, put_in=300_000_000)
    trader, _ = pro(db, "asset_manager", "dealer", level=4)
    empires.apply(db, trader, empire["id"], NOW9)
    empires.decide_application(db, head, _d(db, "SELECT id FROM empire_applications WHERE status = 'waiting'")[0]["id"], True, NOW9)
    bond = max((b for b in bonds.listing(db, NOW9) if b["ask"] > bonds.FACE), key=lambda b: b["ask"])
    empires.set_limits(db, head, trade_limit_bps=100)
    limit = empires.war_room(db, trader, NOW9)["trade_limit"]
    cash = ledger.balance(db, empire["account_id"])
    with pytest.raises(empires.EmpireError, match="trading limit"):
        empires.trade_bonds(db, trader, code=bond["code"], side="buy", units=limit // bonds.FACE, now=NOW9)
    assert ledger.balance(db, empire["account_id"]) == cash                               # and the trade was undone
    sound(db)


# 16. The fine for robbing savers was stranded once they had left.
def test_what_is_recovered_for_a_fund_nobody_is_left_in_goes_to_the_pension_funds(db, monkeypatch):
    fund, manager, account = a_fund(db)
    saver, _ = professional(db, "saver", now=NOW9)
    savings(db, saver, 10_000_000)
    joined(db, saver, fund)
    pensionfunds.divert(db, manager, naira(100_000), NOW9)
    pensionfunds.leave(db, saver, NOW9)
    pensionfunds._settle(db, pensionfunds._fund(db, fund["id"]), NOW9)
    always(monkeypatch, True)
    pensionfunds.after_close(db, 9, NOW9)
    after = pensionfunds._fund(db, fund["id"])
    assert after["struck_off"] and after["units"] == 0 and ledger.balance(db, after["account_id"]) == 0
    sound(db)


# 17. A character that cannot be kept, in chat or a pact's terms, was a server fault.
def test_text_that_cannot_be_kept_is_refused_not_a_fault(db):
    from fastapi.testclient import TestClient
    from server.main import app
    with TestClient(app, raise_server_exceptions=False) as api:
        join(api, ADULT)
        api.put("/api/career/build", json={"build": "investment_banker"})
        api.post("/api/empires/1/applications")
        assert api.post("/api/empire/messages", json={"body": "hello\u0000world"}).status_code == 422
        assert api.post("/api/empire/pacts", json={"to_empire": 2, "kind": "alliance", "terms": "We stand together\u0000 always."}).status_code == 422
        assert api.post("/api/empire/messages", json={"body": "hello world"}).status_code == 201
    ada, _ = thief_in(db, computer_empire(db, 2), "asset_manager", "ada2")
    with pytest.raises(empires.EmpireError):
        empires.say(db, ada, "hello\x00", NOW9)


# 18. Several actions worked in the gap between a quarter's end and its close.
def test_more_is_refused_between_a_quarters_end_and_its_close(db, monkeypatch):
    empire, (head, _), partners = founded(db)
    scribe, ledgerman = partners["investment_banker"][0], partners["asset_manager"][0]
    empires.set_limits(db, head, expense_limit=naira(500_000), now=NOW9)
    empires.divert(db, scribe, naira(100_000), NOW9)
    always(monkeypatch, True)
    audit = empires.accountant_audit(db, ledgerman, NOW9)
    fund, manager, _ = a_fund(db, fee_bps=50)
    for attempt in (lambda: empires.file_audit(db, ledgerman, audit["id"], [], GAP9),
                    lambda: empires.staff_seat(db, head, "investment_banker", 1, True, GAP9),
                    lambda: empires.set_limits(db, head, trade_limit_bps=10_000, now=GAP9),
                    lambda: empires.decide_case(db, head, 1, True, GAP9),
                    lambda: empires.break_pact(db, head, 1, GAP9), lambda: empires.report_pact(db, head, 1, GAP9),
                    lambda: empires.refuse_pact(db, head, 1, GAP9), lambda: empires.approve_step(db, head, 1, GAP9)):
        with pytest.raises(empires.EmpireError, match="books are being closed"):
            attempt()
    with pytest.raises(pensionfunds.FundError, match="books are being closed"):
        pensionfunds.set_fee(db, manager, 0, GAP9)


# 19. A look-alike of a computer-run empire's name was accepted.
def test_an_empires_name_is_plain_letters_so_that_it_cannot_pass_for_another(db):
    head, _ = pro(db, "asset_manager", "chief", level=20, cash_naira=60_000_000)
    for name in ("Savаnnah Crown Holdings", "Lagoon​House", "Lagöon House"):
        with pytest.raises(empires.EmpireError):
            empires.found(db, head, name, naira(1_000), 0, NOW9)
    with pytest.raises(pensionfunds.FundError):
        pensionfunds.open_fund(db, head, "Savаnnah Pensions", 10, NOW9)


# 20. The "Others" line on the Legal Counsel's screen showed one fund's or empire's whole holding.
def test_what_one_fund_or_empire_holds_is_not_shown_on_its_own_line(db):
    fund, manager, _ = a_fund(db)
    give_shares(db, fund["account_id"], "ADF", 3_000_000)
    outsider, _ = pro(db, "investment_banker", "outsider")
    seen = desks_more.lawyer_desk(db, outsider, "ADF", NOW9)
    assert "Others" not in {h["holder"] for h in seen["holders"]}


# 21. The database let ended memberships, book entries and decided cases be rewritten.
def test_memberships_books_and_cases_are_guarded_in_the_database(db, monkeypatch):
    empire = computer_empire(db)
    thief, _ = thief_in(db, empire)
    empires.divert(db, thief, naira(100_000), NOW9)
    always(monkeypatch, True)
    empires._staff_audit(db, empire, 9, NOW9)
    for sql in ("UPDATE empire_members SET left_reason = 'left' WHERE left_reason = 'sacked'",
                "UPDATE empire_books SET genuine = true WHERE NOT genuine", "UPDATE empire_books SET amount = 1 WHERE NOT genuine",
                "UPDATE empire_books SET found = false WHERE found", "UPDATE empire_cases SET status = 'forgiven'",
                "UPDATE empire_cases SET debt_left = debt_left + 1", "DELETE FROM empire_cases", "DELETE FROM empire_audits",
                "UPDATE empire_cases SET player_id = player_id, amount = 1"):
        with pytest.raises(psycopg.errors.RestrictViolation):
            db.execute(sql)


# The smaller things.
def test_smaller_things_the_reviewer_found(db, monkeypatch):
    # A Legal Counsel in a computer-run empire can have a lawful pact signed: its head signs the draft at once. An unlawful one is refused.
    one, two = computer_empire(db, 0), computer_empire(db, 1)
    counsel, _ = thief_in(db, one, "investment_banker", "counsel")
    assert empires.draft_pact(db, counsel, two["id"], "alliance", "We stand together against all comers.", NOW9)["status"] == "signed"
    with pytest.raises(empires.EmpireError, match="will not sign an unlawful pact"):
        empires.draft_pact(db, counsel, two["id"], "rig_bids", "We take turns to win every contract.", NOW9)
    # An Accountant who has left cannot have their audit acted on.
    thief, _ = thief_in(db, one, "investment_banker", "thief", cash=1_000_000)
    auditor, _ = thief_in(db, one, "asset_manager", "auditor")
    empires.divert(db, thief, naira(50_000), NOW9)
    always(monkeypatch, True)
    audit = empires.accountant_audit(db, auditor, NOW9)
    empires.leave(db, auditor, NOW9)
    assert empires.file_audit(db, auditor, audit["id"], [f["book_id"] for f in audit["findings"]], NOW9)["reported"] == 0
    assert not _d(db, "SELECT 1 FROM empire_cases")
    # Somebody whose reputation is too low to join an empire cannot found one either.
    rogue, _ = pro(db, "asset_manager", "rogue", level=20, cash_naira=60_000_000)
    db.execute("UPDATE players SET reputation = 0 WHERE id = %s", (rogue,))
    with pytest.raises(empires.EmpireError, match="reputation"):
        empires.found(db, rogue, "Rogue House", naira(30_000_000), 0, NOW9)
    # A seat is for a build: it is given up before the build is changed.
    db.execute("UPDATE players SET build_changed_at = build_changed_at - interval '40 days' WHERE id = %s", (thief,))
    with pytest.raises(careers.CareerError, match="Leave the empire"):
        careers.choose_build(db, thief, "investment_banker", NOW9)
    # A step that was tried and not passed goes to the staff: a colleague in the same build cannot take it with the answers in hand.
    empire, (head, _), partners = founded(db)
    scribe = partners["investment_banker"][0]
    second, _ = pro(db, "investment_banker", "second")
    empires.apply(db, second, empire["id"], NOW9)
    empires.decide_application(db, head, _d(db, "SELECT id FROM empire_applications WHERE status = 'waiting'")[0]["id"], True, NOW9)
    empires.start_task(db, head, NOW9)
    step = empires.war_room(db, scribe, NOW9)["task"]["steps"][0]
    taken = empires.take_step(db, scribe, step["id"], NOW9)
    objectives.submit(db, scribe, taken["id"], {}, NOW9)
    with pytest.raises(empires.EmpireError, match="already tried"):
        empires.take_step(db, second, step["id"], NOW9)
    sound(db)
