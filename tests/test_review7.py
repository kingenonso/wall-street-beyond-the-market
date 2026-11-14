"""Stage 7: what the independent reviewer and the two independent answer checkers found, each closed and kept closed.

The reviewer's own tests showed each loophole working. Here each is turned round: it must not work."""

from __future__ import annotations

from datetime import timedelta

import pytest
from psycopg.rows import dict_row

from simulation import careers, empires, ledger, objectives, quarters, ranks
from simulation import world_data as data
from simulation.money import naira
from tests.conftest import ADULT, after_quarters, join
from tests.test_builds import pro
from tests.test_careers import NOW9, sound
from tests.test_empires import always, computer_empire, countersigned, founded
from tests.test_mastery import FRIDAY9, answers_for, master, right_case
from tests.test_objectives import bell, give_cash, government

pytestmark = pytest.mark.world("eight")


def _dicts(db, sql, params=()):
    with db.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def _seat_with(db, head, empire, player, now=NOW9):
    empires.apply(db, player, empire["id"], now)
    asked = _dicts(db, "SELECT id FROM empire_applications WHERE player_id = %s AND status = 'waiting'", (player,))[0]["id"]
    empires.decide_application(db, head, asked, True, now)


# 1. The three settings of a module were often the same work: answers seen once, or one purchase, counted three times.
@pytest.mark.parametrize("build, code", [("journalist", "jr_economy"), ("risk_manager", "rm_inflation"), ("asset_manager", "am_idle"),
                                         ("risk_manager", "rm_shock"), ("accountant", "ac_ratios")])
def test_a_module_is_worked_in_one_setting_a_quarter_whichever_is_taken_first(db, build, code):
    player, _ = pro(db, build, level=20, cash_naira=200_000)
    empires.apply(db, player, computer_empire(db)["id"], NOW9)
    for first in ("", "_e", "_w"):
        with db.transaction(force_rollback=True):
            objectives.accept(db, player, code + first, FRIDAY9)
            for other in ("", "_e", "_w"):
                with pytest.raises(objectives.ObjectiveError, match="another setting|already taken|in hand already"):
                    objectives.accept(db, player, code + other, FRIDAY9)
    # The database itself refuses a second setting, whatever the code above it does.
    objectives.accept(db, player, code, FRIDAY9)
    with pytest.raises(Exception, match="objectives_one_setting_a_quarter"):
        db.execute("INSERT INTO objectives (player_id, build, template, module, period, payer_account_id, payer_name, title, terms, reward,"
                   " experience, accepted_at, setting, root) SELECT player_id, build, template || '_e', module, period, payer_account_id,"
                   " payer_name, title, terms, reward, experience, accepted_at, 'empire', root FROM objectives WHERE player_id = %s", (player,))


def test_one_purchase_is_not_learned_practised_and_proven_at_once(db):
    from simulation import bonds
    player, account = pro(db, "asset_manager", level=10, cash_naira=120_000)
    empires.apply(db, player, computer_empire(db)["id"], NOW9)
    objectives.accept(db, player, "am_idle", FRIDAY9)
    bonds.trade(db, account=account, code=government(db, "bill")["code"], side="buy", units=60, now=FRIDAY9)
    for day in (5, 6, 7):
        bell(db, day)
    quarters.close_due_quarters(db, after_quarters(9))
    skill = next(s for s in objectives.board(db, player, after_quarters(9) + timedelta(hours=12))["skills"] if s["template"] == "am_idle")
    assert skill["learned"] and not skill["practised"] and not skill["proven"]


# 2. A failed rank case showed its answers, and parts not drawn on a company were the same on the retry and for a friend.
def test_a_judged_case_does_not_show_its_answers_while_the_quarter_runs_and_a_retry_is_a_different_case(db):
    first, _ = pro(db, "journalist", "first", level=20, cash_naira=5_000_000)
    master(db, first, "journalist")
    case = ranks.begin(db, first, "journalist", NOW9)
    failed = ranks.hand_in(db, first, case["id"], {}, NOW9)
    assert failed["state"] == "failed" and not any("answers" in part for part in failed["result"]["parts"])
    assert all(part["debrief"]["plain"] == "" and part["debrief"]["maths"] == "" for part in failed["result"]["parts"])
    assert not any("answers" in part for part in ranks.standing(db, first, NOW9)["past"][0]["result"]["parts"])
    # The economy part, which was the same paper for everybody, is no longer in the case.
    assert "jr_economy" not in [p["template"] for p in case["parts"]]


@pytest.mark.parametrize("track", ["risk_manager", "asset_manager", "investment_banker"])
def test_the_bond_in_a_case_is_priced_at_the_cases_own_return_not_the_one_ordinary_work_shows(db, track):
    code = "ib_bond" if track == "investment_banker" else "rm_shock"
    seen = set()
    for n in range(6):
        player, _ = pro(db, track, f"sitter{n}", level=20, cash_naira=5_000_000)
        master(db, player, track)
        case = ranks.begin(db, player, track, NOW9)
        part = next(p for p in case["parts"] if p["template"] == code)
        seen.add((part["terms"]["given"][0]["text"], next(g["text"] for g in part["terms"]["given"] if "Return lenders want" in g["label"])))
        assert any("as set for this case" in g["label"] for g in part["terms"]["given"])
        # The right answers still pass: the judge prices at the return the case set.
        right = right_case(db, player, case["id"], NOW9)
        assert ranks.hand_in(db, player, case["id"], right, NOW9)["state"] == "passed"
    assert len(seen) >= 3


def test_a_rank_case_is_never_set_on_a_bank_or_an_insurer(db):
    for n in range(12):
        player, _ = pro(db, "accountant", f"a{n}", level=20, cash_naira=2_000_000)
        master(db, player, "accountant")
        ticker = ranks.begin(db, player, "accountant", NOW9)["company"]["ticker"]
        assert _dicts(db, "SELECT sector FROM companies WHERE ticker = %s", (ticker,))[0]["sector"] not in ("banking", "insurance")


# 3. A counter-offer outlived the head who made it.
def test_an_offer_lapses_when_the_head_who_made_it_no_longer_leads(db):
    empire, (old_head, _), partners = founded(db)
    scribe, scribe_account = partners["journalist"]
    new_head = partners["accountant"][0]
    empires.resign(db, scribe, "Going.", NOW9)
    letter = empires.war_room(db, old_head, NOW9)["resignations"][0]["id"]
    empires.counter_offer(db, old_head, letter, naira(500_000), naira(10_000_000), "Stay.", NOW9)
    db.execute("UPDATE players SET ceo_since = %s WHERE id = %s", (NOW9, new_head))
    empires.vote_head(db, new_head, new_head, NOW9)
    assert empires.vote_head(db, scribe, new_head, NOW9)["elected"]
    # The member is no longer shown the old head's offer, and cannot take it.
    assert empires.war_room(db, scribe, NOW9)["resignation"]["offer"] is None
    before, pot = ledger.balance(db, scribe_account), ledger.balance(db, empire["account_id"])
    assert empires.accept_offer(db, scribe, NOW9)["lapsed"]
    assert ledger.balance(db, scribe_account) == before and ledger.balance(db, empire["account_id"]) == pot
    assert empires.war_room(db, scribe, NOW9)["signing_limit"] == naira(500_000)
    assert _dicts(db, "SELECT count(*) AS n FROM empire_books WHERE empire_id = %s AND kind = 'bonus'", (empire["id"],))[0]["n"] == 0
    with pytest.raises(empires.EmpireError, match="no offer"):
        empires.accept_offer(db, scribe, NOW9)
    # The new head can make an offer of their own.
    empires.counter_offer(db, new_head, letter, naira(100_000), None, "", NOW9)
    assert empires.accept_offer(db, scribe, NOW9) == {"bonus": naira(100_000), "signing_limit": None}
    sound(db)


# 4. One character made the server fail when work or a case was handed in.
def test_a_character_that_cannot_be_kept_is_refused_not_a_fault(db, client):
    assert join(client, ADULT).status_code == 201
    assert client.put("/api/career/build", json={"build": "accountant"}).status_code == 200
    me = client.get("/api/me").json()["id"]
    careers.add_experience(db, me, "accountant", careers.experience_for(20), NOW9)
    master(db, me, "accountant")
    give_cash(db, ledger.player_account_id(db, me), 1_000_000)
    case = client.post("/api/ranks/cases", json={"track": "accountant"}).json()["active"]
    for bad in ({"ac_ratios": {"ebitda": "\u0000"}}, {"ac_ratios": {"ebitda": {"a": "\u0000"}}}, {"ac_ratios": {"ebi\u0000tda": 1}},
                {"ac\u0000": {"ebitda": 1}}, {"ac_ratios": {"ebitda": {"a\u0007": "x"}}}):
        assert client.post(f"/api/ranks/cases/{case['id']}/hand-in", json={"answers": bad}).status_code == 422
    assert _dicts(db, "SELECT state FROM rank_cases WHERE id = %s", (case["id"],))[0]["state"] == "active"
    for bad in ({"ebitda": "\u0000"}, {"headings": {"a": "\u0000"}}, {"eb\u0000": 1}):
        assert client.post("/api/objectives/1/hand-in", json={"answers": bad}).status_code == 422


# 5. League points for growth could be bought with a staged theft, repaid with its fine.
def test_money_taken_and_paid_back_with_a_fine_is_not_growth(db, monkeypatch):
    empire, (head, _), partners = founded(db)
    auditor = partners["accountant"][0]
    quarters.close_due_quarters(db, after_quarters(9))
    now = after_quarters(9) + timedelta(hours=12)
    start = _dicts(db, "SELECT worth FROM empire_worth WHERE empire_id = %s AND period = 9", (empire["id"],))[0]["worth"]
    friend, _ = pro(db, "lawyer", "friend", level=4, cash_naira=4_000_000)
    _seat_with(db, head, empire, friend, now)
    take = start * 22 // 100
    empires.set_limits(db, head, member_id=friend, signing_limit=take, now=now)
    countersigned(db, empires.divert(db, friend, take, now), auditor, now)
    always(monkeypatch, True)
    audit = empires.accountant_audit(db, auditor, now)
    empires.file_audit(db, auditor, audit["id"], [f["book_id"] for f in audit["findings"]], now)
    empires.decide_case(db, head, _dicts(db, "SELECT id FROM empire_cases WHERE player_id = %s", (friend,))[0]["id"], True, now)
    monkeypatch.undo()
    for n in (10, 11, 12):
        quarters.close_due_quarters(db, after_quarters(n))
    growth = _dicts(db, "SELECT points FROM league_points WHERE empire_id = %s AND reference = 'growth:3'", (empire["id"],))
    assert sum(g["points"] for g in growth) <= 2
    sound(db)


# 6. The leadership track was opened with one kobo: begin a founding, take the work, cancel the founding.
def test_beginning_a_founding_does_not_open_the_leadership_track(db):
    player, _ = pro(db, "accountant", level=20, cash_naira=1)
    empires.found(db, player, "Paper House", 1, 0, NOW9)
    assert [t["track"] for t in objectives.board(db, player, NOW9)["tracks"]] == ["accountant"]
    with pytest.raises(objectives.ObjectiveError, match="not open"):
        objectives.accept(db, player, "ce_return", NOW9)
    with pytest.raises(ranks.RankError, match="not open"):
        ranks.begin(db, player, "ceo", NOW9)


# 7. Every member was told who had resigned, and that an offer was made.
def test_a_resignation_and_an_offer_are_between_the_member_and_the_head(db):
    empire, (head, _), partners = founded(db)
    scribe, colleague = partners["journalist"][0], partners["accountant"][0]
    empires.resign(db, scribe, "A private reason.", NOW9)
    letter = empires.war_room(db, head, NOW9)["resignations"][0]["id"]
    empires.counter_offer(db, head, letter, naira(100_000), None, "Please stay.", NOW9)
    room = empires.war_room(db, colleague, NOW9)
    text = str(room)
    assert "resign" not in " ".join(e["words"] for e in room["events"]).lower() and "offer" not in " ".join(e["words"] for e in room["events"]).lower()
    assert "A private reason" not in text and "Please stay" not in text and room["resignations"] == []
    empires.accept_offer(db, scribe, NOW9)
    assert "offer" not in " ".join(e["words"] for e in empires.war_room(db, colleague, NOW9)["events"]).lower()
    # When somebody actually leaves, that is written down for all to see.
    empires.resign(db, scribe, "", NOW9)
    empires.release(db, head, empires.war_room(db, head, NOW9)["resignations"][0]["id"], NOW9)
    assert "scribe was released from their notice and left." in [e["words"] for e in empires.war_room(db, colleague, NOW9)["events"]]


# 8. A member working out their notice could be voted in as head.
def test_somebody_who_is_leaving_cannot_be_voted_in_to_lead(db):
    empire, (head, _), partners = founded(db)
    scribe, colleague = partners["journalist"][0], partners["accountant"][0]
    db.execute("UPDATE players SET ceo_since = %s WHERE id = %s", (NOW9, scribe))
    empires.resign(db, scribe, "", NOW9)
    with pytest.raises(empires.EmpireError, match="leaving cannot be voted in"):
        empires.vote_head(db, colleague, scribe, NOW9)
    empires.withdraw_resignation(db, scribe, NOW9)
    assert empires.vote_head(db, colleague, scribe, NOW9)["votes"] == 1
    # A vote is cast for a seat, because a member is not given colleagues' identifiers.
    assert empires.vote_for_seat(db, scribe, "journalist", 1, NOW9)["elected"]
    with pytest.raises(empires.EmpireError, match="Nobody holds that seat"):
        empires.vote_for_seat(db, colleague, "lawyer", 2, NOW9)


# 9. Reporting one's own unlawful pact cost the other side league points and the reporter none.
def test_both_sides_of_an_unlawful_pact_lose_league_points_whoever_reports_it(db, monkeypatch):
    empire, (head, _), _ = founded(db)
    rival = computer_empire(db)
    lawyer, _ = pro(db, "lawyer", "counsel", level=4)
    _seat_with(db, head, empire, lawyer)
    unlawful = next(code for code, (_label, legal) in data.PACT_KINDS.items() if not legal)
    always(monkeypatch, True)
    pact = empires.draft_pact(db, lawyer, rival["id"], unlawful, "We agree to rig the price between us.", NOW9)
    empires.sign_pact(db, head, pact["id"], NOW9)
    empires.report_pact(db, head, pact["id"], NOW9)
    points = lambda e: sum(p["points"] for p in _dicts(db, "SELECT points FROM league_points WHERE empire_id = %s AND period = 9", (e,)))
    assert points(rival["id"]) == points(empire["id"]) == data.LEAGUE_POINTS["theft"] == -5


# 10. Somebody who had left, or been removed, was still paid by the empire for work in hand.
def test_work_in_hand_for_an_empire_ends_with_the_seat(db):
    empire, (head, _), partners = founded(db)
    ledgerman, account = partners["accountant"]
    taken = objectives.accept(db, ledgerman, "ac_ratios_e", NOW9)
    right = answers_for(db, taken["id"], NOW9)
    empires.sack(db, head, ledgerman, NOW9)
    assert _dicts(db, "SELECT state FROM objectives WHERE id = %s", (taken["id"],))[0]["state"] == "withdrawn"
    before = ledger.balance(db, account)
    with pytest.raises(objectives.ObjectiveError, match="finished"):
        objectives.submit(db, ledgerman, taken["id"], right, NOW9)
    assert ledger.balance(db, account) == before
    skill = next(s for s in objectives.board(db, ledgerman, NOW9)["skills"] if s["template"] == "ac_ratios")
    assert not skill["practised"]


def test_a_build_cannot_be_changed_with_a_rank_case_in_hand(db):
    player, _ = pro(db, "accountant", level=20, cash_naira=2_000_000)
    master(db, player, "accountant")
    ranks.begin(db, player, "accountant", NOW9)
    db.execute("UPDATE players SET build_changed_at = %s WHERE id = %s", (NOW9 - timedelta(days=40), player))
    with pytest.raises(careers.CareerError, match="rank case in hand"):
        careers.choose_build(db, player, "lawyer", NOW9)


# From the two independent answer checks.
def test_a_contract_or_a_mandate_is_never_decided_on_a_rounding(db):
    """A limit is never set within a tenth of the company's own figure, and the judge tests the exact figure."""
    for n in range(25):
        player, _ = pro(db, "lawyer", f"l{n}", level=6)
        t = _dicts(db, "SELECT terms FROM objectives WHERE id = %s", (objectives.accept(db, player, "lw_contract", NOW9)["id"],))[0]["terms"]
        ratio, cover = t["debt"] / (4 * t["ebitda"]), t["operating"] / t["interest"]
        assert abs(ratio - t["most"] / 10) >= 0.1 and abs(cover - t["least"] / 10) >= 0.1
    paper = {"terms": {"debt": 404, "ebitda": 25, "operating": 30, "interest": 10, "most": 40, "least": 25}}
    marked = objectives.TEMPLATES["lw_contract"].submit({}, paper, {"ratio": 4.0, "cover": 3.0, "broken": "yes"})
    assert marked["state"] == "passed" and marked["answers"]["broken"] == "yes"            # 4.04 is over a limit of 4.0
    review = {"terms": {"lines": [[3000, 2000], [2996, 2001], [1997, 2001], [999, 2001]], "cash": 2_000_000}}
    marked = objectives.TEMPLATES["am_review"].submit({}, review, {})
    assert marked["answers"]["inside"] == "no"                                             # 30.015% is above 30%
    close = {"terms": {"operating": 1364, "interest": 678, "equity": 20_000, "debt": 20_000}}
    assert objectives.TEMPLATES["ce_return"].submit({}, close, {})["answers"]["earns"] == "yes"


def test_a_saving_from_a_takeover_is_counted_after_tax_and_a_dividend_must_leave_room_for_debt_falling_due(db):
    buy = {"terms": {"value": 1_000_000, "premium": 30, "saving": 3, "sales": 2_000_000, "profit": 100_000, "tax_bps": 3000, "debt": 0}}
    marked = objectives.TEMPLATES["ce_buy"].submit({}, buy, {})
    assert marked["answers"]["payback"] == 13.0 and marked["answers"]["payback_with"] == round(1_300_000 / (100_000 + 60_000 * 0.7), 2)
    payout = {"terms": {"profit": 1_000_000, "share": 50, "cash": 900_000, "bills": 100_000, "due": 400_000, "shares": 1000}}
    marked = objectives.TEMPLATES["ce_payout"].submit({}, payout, {})
    assert marked["answers"]["afford"] == "no" and "short" in marked["debrief"]["plain"] and "less than nothing" not in marked["debrief"]["plain"]
    # In the live world the test now bites for some companies and not for others.
    calls = set()
    for n in range(30):
        player, _ = pro(db, "accountant", f"c{n}", level=20)
        db.execute("UPDATE careers SET rank = 1, experience = %s WHERE player_id = %s", (careers.experience_for(40), player))
        taken = objectives.accept(db, player, "ce_payout", NOW9)
        assert any(g["label"] == "Debt reaching its end date within a year" for g in taken["terms"]["given"])
        calls.add(answers_for(db, taken["id"], NOW9)["afford"])
    assert calls == {"yes", "no"}


def test_an_overdue_loan_is_said_to_be_overdue_and_the_wording_matches_the_marking(db):
    seen = ""
    for n in range(30):
        player, _ = pro(db, "lawyer", f"d{n}", level=6)
        taken = objectives.accept(db, player, "lw_debts", NOW9)
        seen += " ".join(g["text"] for g in taken["terms"]["given"])
        assert "counts as ending within a year" in " ".join(taken["terms"]["task"])
    assert "ends Opening" not in seen
    player, _ = pro(db, "lawyer", "control", level=6)
    assert "largest holder's share is one of them" in objectives.accept(db, player, "lw_control", NOW9)["terms"]["pass_when"]
    player, _ = pro(db, "accountant", "income", level=6)
    assert "count interest earned" in " ".join(objectives.accept(db, player, "ac_income", NOW9)["terms"]["task"])


def test_the_new_records_are_permanent(db):
    empire, (head, _), partners = founded(db)
    scribe = partners["journalist"][0]
    from simulation import leagues
    leagues.award(db, empire["id"], 10, "A task finished", 9, NOW9, reference="task:1")
    empires.resign(db, scribe, "", NOW9)
    empires.withdraw_resignation(db, scribe, NOW9)
    player, _ = pro(db, "accountant", level=20, cash_naira=2_000_000)
    master(db, player, "accountant")
    case = ranks.begin(db, player, "accountant", NOW9)
    ranks.hand_in(db, player, case["id"], {}, NOW9)
    ranks.report(db, player, "I believe the cover is wrong here.", NOW9, case_id=case["id"])
    for sql in ("UPDATE league_points SET points = 99", "DELETE FROM league_points", "UPDATE rank_cases SET state = 'passed'",
                "DELETE FROM rank_cases", "UPDATE empire_resignations SET status = 'waiting'", "DELETE FROM empire_resignations",
                "UPDATE work_reports SET words = 'changed my mind entirely'", "DELETE FROM work_reports"):
        with pytest.raises(Exception, match="cannot be changed|permanent|forbid"):
            db.execute(sql)
