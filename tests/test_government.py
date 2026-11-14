"""Government, part 1: the elected leader, the budget, the Assembly and the stand-in. A test for each promise and each
loophole.

Promises: the stand-in governs when nobody else does, by its published personality; the leader puts one budget a year,
within the limits; the Assembly passes it or throws it out (heads as they vote, computer-run members by their published
leanings); a budget passed changes what everybody pays; the election is counted as the year closes; a vote of no
confidence can remove the leader.

Loopholes: nobody but the leader puts a budget, and only one, within limits; one vote each in the election, none for a
beginner, none for a player who is not standing; one Assembly vote for each empire's seat, and only for a head; no
candidate under the reputation, the level or a tribunal ban; a tie goes by lot.
"""

from __future__ import annotations

import pytest
from psycopg.rows import dict_row

from simulation import careers, government
from simulation import world_data as data
from tests.test_builds import pro
from tests.test_careers import NOW9
from tests.test_dealmaking import house

pytestmark = pytest.mark.world("eight")

P = 9                       # the first quarter of game year 3
YEAR = government.year_of(P)


def _one(db, sql, params=()):
    with db.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(sql, params).fetchall()
    return rows[0] if rows else None


def elect(db, player, year=YEAR):
    government.term(db, year, NOW9)
    db.execute("UPDATE government_terms SET leader_id = %s, votes = 3 WHERE year = %s", (player, year))


def test_with_nobody_elected_the_stand_in_puts_the_budget_by_its_published_personality(db):
    assert government.quarter_of(P) == 1
    before = government.rates(db)                    # (the stand-in already put budgets in years 1 and 2)
    assert set(before) == set(government.KINDS)
    assert _one(db, "SELECT count(*) AS n FROM budgets WHERE proposed_by IS NULL")["n"] == YEAR - 1
    page = government.view(db, pro(db, "asset_manager", "citizen")[0], NOW9)
    assert page["leader"] is None and page["stand_in"]["kind"] in government.STAND_INS
    government.at_close(db, P, NOW9)
    budget = _one(db, "SELECT * FROM budgets WHERE year = %s", (YEAR,))
    assert budget["status"] == "passed" and budget["proposed_by"] is None
    stand_in = _one(db, "SELECT stand_in FROM government_terms WHERE year = %s", (YEAR,))["stand_in"]
    after = government.rates(db)
    moved = {k: after[k] - before[k] for k in government.KINDS}
    if stand_in == "steady":
        assert set(moved.values()) == {0}
    else:
        assert all(abs(m) <= data.TAX_STEP_BPS for m in moved.values())


def test_only_the_leader_puts_one_budget_within_the_limits(db):
    boss, _ = pro(db, "investment_banker", "boss", level=20)
    other, _ = pro(db, "asset_manager", "pretender", level=20)
    elect(db, boss)
    same = government.rates(db)
    with pytest.raises(government.GovernmentError, match="Only the Government Leader"):
        government.propose_budget(db, other, same, NOW9)
    with pytest.raises(government.GovernmentError, match="Income tax must be between"):
        government.propose_budget(db, boss, {**same, "income": 9000}, NOW9)
    with pytest.raises(government.GovernmentError, match="nothing else"):
        government.propose_budget(db, boss, {**same, "vat": 500}, NOW9)
    government.propose_budget(db, boss, same, NOW9)
    with pytest.raises(government.GovernmentError, match="one a year"):
        government.propose_budget(db, boss, same, NOW9)


def test_the_assembly_counts_heads_as_they_vote_and_computer_members_by_their_leanings(db):
    boss, _ = pro(db, "investment_banker", "taxer", level=20)
    elect(db, boss)
    old = government.rates(db)
    new = {**old, "income": old["income"] + 5 * data.TAX_STEP_BPS}          # a big rise
    budget = government.propose_budget(db, boss, new, NOW9)
    empire, team = house(db, "Delta Partners")
    bid = _one(db, "SELECT id FROM budgets WHERE year = %s", (YEAR,))["id"]
    government.assembly_vote(db, team["head"], f"budget:{bid}", True, NOW9)
    with pytest.raises(government.GovernmentError, match="seat has voted"):
        government.assembly_vote(db, team["head"], f"budget:{bid}", False, NOW9)
    with pytest.raises(government.GovernmentError, match="Lead one to vote"):
        government.assembly_vote(db, team["investment_banker"], f"budget:{bid}", True, NOW9)
    members = government.assembly(db, YEAR)
    expected_ayes = 1 + sum(1 for m in members if m["kind"] == "computer" and government._computer_backs_budget(m["leaning"], old, new))
    expected_noes = len(members) - expected_ayes
    government.at_close(db, P, NOW9)
    row = _one(db, "SELECT * FROM budgets WHERE id = %s", (bid,))
    assert (row["votes_for"], row["votes_against"]) == (expected_ayes, expected_noes)
    assert row["status"] == ("passed" if expected_ayes > expected_noes else "rejected")
    assert government.rates(db)["income"] == (new["income"] if row["status"] == "passed" else old["income"])
    assert budget["rates"] == new


def test_a_budget_passed_changes_what_everybody_pays(db):
    boss, _ = pro(db, "investment_banker", "cutter", level=20)
    elect(db, boss)
    old = government.rates(db)
    same_but_company = {**old, "company": old["company"] - data.TAX_STEP_BPS}   # a small cut: only the high-tax members object
    government.propose_budget(db, boss, same_but_company, NOW9)
    government.at_close(db, P, NOW9)
    if _one(db, "SELECT status FROM budgets WHERE year = %s", (YEAR,))["status"] == "passed":
        assert _one(db, "SELECT company_tax_bps FROM world_state")["company_tax_bps"] == same_but_company["company"]
    # Income tax is read from the rates in force wherever pay is worked out.
    government._set_rates(db, {**government.rates(db), "income": 2000}, P, "test")
    worker, _ = pro(db, "risk_manager", "payslip")
    gross = 1_000_000
    assert careers.split_salary(gross, 0, careers._income_tax(db))["tax"] == gross * 2000 // 10_000


def test_the_election_is_one_vote_each_counted_as_the_year_closes(db, monkeypatch):
    monkeypatch.setattr(government, "quarter_of", lambda period: 4)          # as if this were a year's last quarter
    star, _ = pro(db, "investment_banker", "star", level=20)
    weak, _ = pro(db, "asset_manager", "weakling", level=20)
    db.execute("UPDATE players SET reputation = 85 WHERE id = %s", (star,))
    government.stand(db, star, "Lower taxes for savers.", NOW9)
    with pytest.raises(government.GovernmentError, match="already standing"):
        government.stand(db, star, "Again.", NOW9)
    with pytest.raises(government.GovernmentError, match="reputation of 80"):
        government.stand(db, weak, "Me too.", NOW9)
    with pytest.raises(government.GovernmentError, match="vote opens"):
        government.vote(db, weak, star, NOW9)
    monkeypatch.setattr(data, "ELECTION_STAND_LAST_DAY", 0)                  # the vote is open
    voter, _ = pro(db, "risk_manager", "voter", level=10)
    beginner, _ = pro(db, "risk_manager", "newbie", level=5)
    government.vote(db, voter, star, NOW9)
    with pytest.raises(government.GovernmentError, match="cast once"):
        government.vote(db, voter, star, NOW9)
    with pytest.raises(government.GovernmentError, match="Level 6"):
        government.vote(db, beginner, star, NOW9)
    with pytest.raises(government.GovernmentError, match="not standing"):
        government.vote(db, weak, weak, NOW9)
    with pytest.raises(Exception, match="cast once and kept"):
        db.execute("UPDATE government_votes SET candidate_id = %s", (weak,))
    government.at_close(db, P, NOW9)                                        # the year's close (by the patch)
    elected = _one(db, "SELECT * FROM government_terms WHERE year = %s", (YEAR + 1,))
    assert elected["leader_id"] == star and elected["votes"] == 1


def test_a_vote_of_no_confidence_can_remove_the_leader(db):
    boss, _ = pro(db, "investment_banker", "unpopular", level=20)
    elect(db, boss)
    old = government.rates(db)
    government.propose_budget(db, boss, {k: data.TAX_LIMITS_BPS[k][1] for k in government.KINDS}, NOW9)   # every rate to its most
    empire, team = house(db, "Delta Partners")
    with pytest.raises(government.GovernmentError, match="head of an empire"):
        government.no_confidence(db, team["investment_banker"], NOW9)
    government.no_confidence(db, team["head"], NOW9)
    with pytest.raises(government.GovernmentError, match="already before"):
        government.no_confidence(db, team["head"], NOW9)
    motion = _one(db, "SELECT id FROM motions WHERE year = %s", (YEAR,))["id"]
    government.assembly_vote(db, team["head"], f"motion:{motion}", True, NOW9)
    government.at_close(db, P, NOW9)
    row = _one(db, "SELECT * FROM motions WHERE id = %s", (motion,))
    budget = _one(db, "SELECT status FROM budgets WHERE year = %s", (YEAR,))["status"]
    if budget == "passed":
        # Every computer member who is not a high-taxer turns on a leader whose passed budget went against them.
        assert row["status"] == "passed"
        assert _one(db, "SELECT removed_period FROM government_terms WHERE year = %s", (YEAR,))["removed_period"] == P
        assert government.leader(db, YEAR) is None
    else:
        assert row["status"] in ("passed", "failed")
    assert old
