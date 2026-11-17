"""The tribunal's juries, part 1 (owner, 17 November 2026: "build tribunal first").

Promises: a defendant who fights may ask for a jury of players; five are drawn with no tie to either side; each votes
once on how much of the claim the record proves and on the penalty; the middle vote decides; a jury may find part of a
claim proved, or acquit; every juror who votes is paid by the Treasury, and a vote that matches the verdict earns
reputation; with too few votes by the deadline, or too few players who may sit, the judge decides. Loopholes: voting
twice, voting on a jury you are not on, sitting on a case you are tied to, changing the claim.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from psycopg.rows import dict_row

from simulation import courts, ledger
from simulation import world_data as data
from simulation.money import BPS, apply_bps, naira
from tests.test_builds import pro
from tests.test_careers import NOW9, sound

pytestmark = pytest.mark.world("eight")
CLAIM = naira(10_000_000)


def _q(db, sql, params=()):
    with db.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def _case(db, *, claimant=None, bond=0, jurors=6):
    defendant, account = pro(db, "asset_manager", "The Defendant", cash_naira=50_000_000)
    pool = [pro(db, "risk_manager", f"Juror {i}", level=4)[0] for i in range(jurors)]
    case_id = courts.open_case(db, kind="insider", defendant_id=defendant, claimant_id=claimant, company_id=None, amount=CLAIM,
                               evidence={"key": "test", "total": CLAIM, "lines": [{"what": "Bought before the news"}]},
                               words="Dealt on news before it was public.", period=9, now=NOW9, bond=bond)
    return case_id, defendant, account, pool


def _vote_all(db, case_id, votes):
    seats = _q(db, "SELECT player_id FROM jurors WHERE case_id = %s ORDER BY seat", (case_id,))
    for seat, (proved, penalty) in zip(seats, votes, strict=False):
        courts.vote(db, seat["player_id"], case_id, proved, penalty, "", NOW9 + timedelta(hours=1))
    return seats


def test_a_jury_of_five_with_no_tie_to_either_side_is_summoned(db):
    case_id, defendant, _account, _pool = _case(db)
    done = courts.respond(db, defendant, case_id, "jury", 9, NOW9, "I bought on my own research.")
    assert done["status"] == "jury" and done["defence"] == "I bought on my own research."
    seats = _q(db, "SELECT player_id FROM jurors WHERE case_id = %s", (case_id,))
    assert len(seats) == data.JURY_SIZE and defendant not in {s["player_id"] for s in seats}
    j = done["jury"]
    assert j["sitting"] and j["seats"] == data.JURY_SIZE and j["voted"] == 0 and j["until"] == done["jury_until"] and j["round"] == 1
    assert case_id in {c["id"] for c in courts.docket(db)}
    duty = courts.jury_duty(db, seats[0]["player_id"], NOW9)
    assert [c["id"] for c in duty["sitting"]] == [case_id] and duty["sitting"][0]["my_vote"] is None


def test_the_middle_vote_decides_part_proved_and_jurors_are_paid(db):
    case_id, defendant, _account, _pool = _case(db)
    courts.respond(db, defendant, case_id, "jury", 9, NOW9)
    treasury = ledger.account_id(db, ledger.TREASURY)
    before = ledger.balance(db, treasury)
    seats = _vote_all(db, case_id, [(10_000, "harsh"), (5000, "standard"), (5000, "lenient"), (2500, "standard"), (5000, "standard")])
    row = _q(db, "SELECT * FROM court_cases WHERE id = %s", (case_id,))[0]
    assert row["status"] == "verdict" and row["fine"] == 0                     # it waits a day for an appeal (part 2)
    assert courts.juries_due(db, NOW9 + timedelta(hours=data.JURY_APPEAL_HOURS + 2)) == 1
    row = _q(db, "SELECT * FROM court_cases WHERE id = %s", (case_id,))[0]
    assert row["status"] == "judged" and row["decided_by"] == "jury" and row["proved_bps"] == 5000 and row["penalty"] == "standard"
    proved = apply_bps(CLAIM, 5000)
    assert row["disgorgement"] == proved and row["fine"] == apply_bps(proved, data.COURT_FINE_BPS["insider"])
    fee = naira(data.JURY_FEE_NAIRA)
    agreed = _q(db, "SELECT agreed, fee FROM jurors WHERE case_id = %s ORDER BY seat", (case_id,))
    assert [a["agreed"] for a in agreed] == [False, True, False, False, True] and all(a["fee"] == fee for a in agreed)
    assert ledger.balance(db, treasury) <= before - 5 * fee + row["fine"]        # the fees left the Treasury (fines may come in)
    # A vote cannot be cast twice, and only a juror votes.
    with pytest.raises(courts.CourtError, match="finished sitting|already voted"):
        courts.vote(db, seats[0]["player_id"], case_id, 0, "standard", "", NOW9 + timedelta(hours=2))
    sound(db)


def test_a_jury_may_acquit_and_the_claimant_loses_the_bond_to_the_defendant(db):
    claimant, claimant_account = pro(db, "investment_banker", "The Claimant", cash_naira=20_000_000)
    bond = naira(1_000_000)
    ledger.transfer(db, payer=claimant_account, receiver=ledger.account_id(db, ledger.TREASURY), amount=bond, kind="court_bond",
                    memo="A bond for a test case", period=9)
    case_id, defendant, account, _pool = _case(db, claimant=claimant, bond=bond)
    courts.respond(db, defendant, case_id, "jury", 9, NOW9, "Nothing in the record shows I knew.")
    courts.claimant_note(db, claimant, case_id, "The timing speaks for itself.")
    with pytest.raises(courts.CourtError, match="Only the player who brought"):
        courts.claimant_note(db, defendant, case_id, "Me too.")
    before = ledger.balance(db, account)
    _vote_all(db, case_id, [(0, "standard"), (0, "standard"), (2500, "lenient"), (0, "standard"), (10_000, "harsh")])
    courts.juries_due(db, NOW9 + timedelta(hours=data.JURY_APPEAL_HOURS + 2))
    row = _q(db, "SELECT * FROM court_cases WHERE id = %s", (case_id,))[0]
    assert row["outcome"] == "acquitted" and row["fine"] == 0 and row["disgorgement"] == 0
    assert ledger.balance(db, account) == before + bond
    sound(db)


def test_too_few_votes_or_too_few_jurors_and_the_judge_decides(db):
    case_id, defendant, _account, _pool = _case(db)
    courts.respond(db, defendant, case_id, "jury", 9, NOW9)
    _vote_all(db, case_id, [(0, "standard"), (0, "standard")])                  # two votes: no quorum
    assert courts.juries_due(db, NOW9 + timedelta(hours=data.JURY_HOURS - 1)) == 0
    assert courts.juries_due(db, NOW9 + timedelta(hours=data.JURY_HOURS + 1)) == 1
    row = _q(db, "SELECT * FROM court_cases WHERE id = %s", (case_id,))[0]
    assert row["decided_by"] == "judge" and row["outcome"] == "judged" and row["disgorgement"] == CLAIM
    # Two jurors who voted are paid even so; the three who did not are not.
    assert sorted(r["fee"] for r in _q(db, "SELECT fee FROM jurors WHERE case_id = %s", (case_id,))) == [0, 0, 0] + [naira(data.JURY_FEE_NAIRA)] * 2
    sound(db)


def test_votes_must_be_one_of_the_choices_and_outsiders_cannot_vote(db):
    case_id, defendant, _account, _pool = _case(db)
    courts.respond(db, defendant, case_id, "jury", 9, NOW9)
    juror = _q(db, "SELECT player_id FROM jurors WHERE case_id = %s ORDER BY seat LIMIT 1", (case_id,))[0]["player_id"]
    with pytest.raises(courts.CourtError, match="three quarters"):
        courts.vote(db, juror, case_id, 3333, "standard", "", NOW9)
    with pytest.raises(courts.CourtError, match="lenient"):
        courts.vote(db, juror, case_id, BPS, "brutal", "", NOW9)
    with pytest.raises(courts.CourtError, match="not on that jury"):
        courts.vote(db, defendant, case_id, 0, "standard", "", NOW9)


def test_the_jury_routes_need_a_login_and_good_input(client, player):
    assert client.post("/api/court/cases/1/vote", json={"proved_bps": 5000, "penalty": "cruel"}).status_code == 422
    assert client.post("/api/court/cases/1/answer", json={"choice": "pray"}).status_code == 422
    assert client.post("/api/court/cases/1/vote", json={"proved_bps": 5000, "penalty": "standard"}).status_code == 409
    client.cookies.clear()
    assert client.post("/api/court/cases/1/vote", json={"proved_bps": 5000, "penalty": "standard"}).status_code == 401


def test_with_too_few_who_may_sit_the_judge_decides_at_once(db, monkeypatch):
    case_id, defendant, _account, _pool = _case(db, jurors=0)
    monkeypatch.setattr(courts, "_eligible", lambda conn, row: [])
    done = courts.respond(db, defendant, case_id, "jury", 9, NOW9)
    assert done["status"] == "judged" and done["decided_by"] == "judge"



# ---------------------------------------------------------------------------
# Part 2: challenges, appeals and tampering (owner, 17 November 2026)
# ---------------------------------------------------------------------------

def test_each_side_may_challenge_one_juror_early_and_another_is_drawn(db):
    case_id, defendant, _account, _pool = _case(db, jurors=8)
    courts.respond(db, defendant, case_id, "jury", 9, NOW9)
    mine = next(c for c in courts.my_cases(db, defendant)["defending"] if c["id"] == case_id)
    assert len(mine["panel"]["jurors"]) == data.JURY_SIZE and all(j["name"] for j in mine["panel"]["jurors"])
    first = mine["panel"]["jurors"][0]["seat"]
    courts.challenge(db, defendant, case_id, first, NOW9 + timedelta(hours=1))
    live = _q(db, "SELECT seat FROM jurors WHERE case_id = %s AND struck_by IS NULL", (case_id,))
    assert len(live) == data.JURY_SIZE and first not in {r["seat"] for r in live}
    with pytest.raises(courts.CourtError, match="one juror"):
        courts.challenge(db, defendant, case_id, live[0]["seat"], NOW9 + timedelta(hours=1))
    # The public sees no names: only how many sit and how many were challenged.
    public = courts.case(db, case_id)["jury"]
    assert public["struck"] == 1 and "jurors" not in public


def test_an_appeal_brings_a_fresh_jury_whose_verdict_is_final_and_a_winning_appeal_is_refunded(db):
    case_id, defendant, account, _pool = _case(db, jurors=12)
    courts.respond(db, defendant, case_id, "jury", 9, NOW9)
    first = _vote_all(db, case_id, [(10_000, "harsh")] * 5)
    with pytest.raises(courts.CourtError, match="Only the two sides"):
        courts.appeal(db, first[0]["player_id"], case_id, NOW9 + timedelta(hours=2))
    before = ledger.balance(db, account)
    courts.appeal(db, defendant, case_id, NOW9 + timedelta(hours=2))
    fee = max(apply_bps(CLAIM, data.JURY_APPEAL_FEE_BPS), naira(data.JURY_APPEAL_FEE_NAIRA))
    assert ledger.balance(db, account) == before - fee
    second = _q(db, "SELECT player_id FROM jurors WHERE case_id = %s AND round = 2 ORDER BY seat", (case_id,))
    assert len(second) == data.JURY_SIZE and not {r["player_id"] for r in second} & {r["player_id"] for r in first}
    for juror in second:
        courts.vote(db, juror["player_id"], case_id, 5000, "lenient", "", NOW9 + timedelta(hours=3))
    row = _q(db, "SELECT * FROM court_cases WHERE id = %s", (case_id,))[0]
    assert row["status"] == "judged" and row["proved_bps"] == 5000 and row["penalty"] == "lenient" and row["first_proved_bps"] == BPS
    assert courts.case(db, case_id)["jury"]["first_votes"]                   # the first jury's votes stay in the open
    assert _q(db, "SELECT 1 AS x FROM ledger_transactions WHERE kind = 'court_appeal_refund' LIMIT 1")
    sound(db)


def test_offering_a_juror_money_is_a_crime_that_the_juror_may_report(db):
    case_id, defendant, account, _pool = _case(db)
    courts.respond(db, defendant, case_id, "jury", 9, NOW9)
    juror = _q(db, "SELECT player_id, seat FROM jurors WHERE case_id = %s ORDER BY seat LIMIT 1", (case_id,))[0]
    with pytest.raises(courts.CourtError, match="two sides"):
        courts.offer(db, juror["player_id"], case_id, juror["seat"], naira(1_000_000), "acquit", NOW9)
    courts.offer(db, defendant, case_id, juror["seat"], naira(2_000_000), "acquit", NOW9)
    with pytest.raises(courts.CourtError, match="already approached"):
        courts.offer(db, defendant, case_id, juror["seat"], naira(2_000_000), "acquit", NOW9)
    offers = courts.jury_duty(db, juror["player_id"], NOW9)["sitting"][0]["offers"]
    assert offers and offers[0]["amount"] == naira(2_000_000)
    before = ledger.balance(db, account)
    courts.answer_offer(db, juror["player_id"], offers[0]["id"], False, NOW9)
    assert ledger.balance(db, account) == before                              # reported: no money moved
    wrong = courts.tampering_wrongs(db, NOW9 - timedelta(days=1))
    assert len(wrong) == 1 and str(wrong[0]["defendant_id"]) == str(defendant) and wrong[0]["amount"] == naira(2_000_000)


def test_a_juror_who_takes_money_is_paid_and_both_may_be_found_out(db, monkeypatch):
    case_id, defendant, account, _pool = _case(db)
    courts.respond(db, defendant, case_id, "jury", 9, NOW9)
    juror = _q(db, "SELECT player_id, seat FROM jurors WHERE case_id = %s ORDER BY seat LIMIT 1", (case_id,))[0]
    courts.offer(db, defendant, case_id, juror["seat"], naira(1_000_000), "acquit", NOW9)
    offer = courts.jury_duty(db, juror["player_id"], NOW9)["sitting"][0]["offers"][0]
    before = ledger.balance(db, account)
    courts.answer_offer(db, juror["player_id"], offer["id"], True, NOW9)
    assert ledger.balance(db, account) == before - naira(1_000_000)
    assert not courts.tampering_wrongs(db, NOW9 - timedelta(days=1))          # hidden until somebody tells
    db.execute("UPDATE jury_offers SET tell_bps = 10000 WHERE id = %s", (offer["id"],))
    _vote_all(db, case_id, [(0, "standard")] * 5)
    wrongs = courts.tampering_wrongs(db, NOW9 - timedelta(days=1))
    assert {str(w["defendant_id"]) for w in wrongs} == {str(defendant), str(juror["player_id"])}
    sound(db)
