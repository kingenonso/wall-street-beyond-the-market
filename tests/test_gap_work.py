"""The gap stage, Part 3: work the empire pays for, past what is left of a desk's budget, waits for the head."""

from __future__ import annotations

import pytest
from psycopg.rows import dict_row

from simulation import firm, firm_money, objectives
from simulation.money import naira
from tests.test_careers import NOW9, sound
from tests.test_firm import firm_of

pytestmark = pytest.mark.world("eight")


def _one(db, sql, params=()):
    with db.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(sql, params).fetchall()
    return rows[0] if rows else None


def test_work_past_the_desks_budget_waits_for_the_head_and_is_taken_on_when_approved(db):
    empire, team = firm_of(db, n_cash=5_000_000_000)
    accountant = team["accountant"]
    db.execute("UPDATE careers SET rank = 1, experience = greatest(experience, 2000) WHERE player_id = %s", (accountant,))
    firm_money.set_budgets(db, team["head"], {"accountant": naira(1)}, NOW9)
    waiting = objectives.accept(db, accountant, "ac_ratios_e", NOW9)
    assert waiting["waiting"] and "budget" in waiting["words"]
    assert not _one(db, "SELECT 1 FROM objectives WHERE player_id = %s AND template = 'ac_ratios_e'", (accountant,))
    again = objectives.accept(db, accountant, "ac_ratios_e", NOW9)
    assert again["waiting"] and "already with the head" in again["words"]
    approval = _one(db, "SELECT * FROM empire_approvals WHERE empire_id = %s AND kind = 'empire_work' AND status = 'waiting'", (empire["id"],))
    assert approval and approval["desk"] == "head"
    with pytest.raises(Exception):
        firm.decide(db, accountant, approval["id"], True, "Mine.", NOW9)              # nobody approves their own request
    firm.decide(db, team["head"], approval["id"], True, "Go ahead.", NOW9)
    taken = _one(db, "SELECT * FROM objectives WHERE player_id = %s AND template = 'ac_ratios_e'", (accountant,))
    assert taken and taken["state"] == "active" and taken["payer_account_id"] == empire["account_id"]
    sound(db)


def test_a_refused_request_takes_nothing_on_and_work_inside_the_budget_goes_straight_through(db):
    empire, team = firm_of(db, n_cash=5_000_000_000)
    accountant = team["accountant"]
    db.execute("UPDATE careers SET rank = 1, experience = greatest(experience, 2000) WHERE player_id = %s", (accountant,))
    firm_money.set_budgets(db, team["head"], {"accountant": naira(1)}, NOW9)
    waiting = objectives.accept(db, accountant, "ac_ratios_e", NOW9)
    firm.decide(db, team["head"], waiting["approval_id"], False, "Not this quarter.", NOW9)
    assert not _one(db, "SELECT 1 FROM objectives WHERE player_id = %s AND template = 'ac_ratios_e'", (accountant,))
    # A generous budget: no waiting.
    db.execute("DELETE FROM empire_budgets WHERE empire_id = %s", (empire["id"],))
    firm_money.set_budgets(db, team["head"], {"accountant": naira(1_000_000_000)}, NOW9)
    taken = objectives.accept(db, accountant, "ac_ratios_e", NOW9)
    assert "waiting" not in taken and taken["state"] == "active"
    # The head's own work never waits.
    sound(db)
