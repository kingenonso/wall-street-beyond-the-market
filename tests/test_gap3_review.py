"""The gap stage, Part 3: each finding of the independent review, fixed and tested."""

from __future__ import annotations

import pytest
from psycopg.rows import dict_row

from simulation import careers, empires, firm, firm_money, objectives, objectives_gap
from simulation.money import naira
from tests.test_builds import pro
from tests.test_careers import NOW9
from tests.test_firm import firm_of

pytestmark = pytest.mark.world("eight")


def _one(db, sql, params=()):
    with db.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(sql, params).fetchall()
    return rows[0] if rows else None


def tight(db):
    empire, team = firm_of(db, n_cash=5_000_000_000)
    db.execute("UPDATE careers SET rank = 4, experience = %s WHERE player_id = %s", (careers.experience_for(100), team["asset_manager"]))
    firm_money.set_budgets(db, team["head"], {"asset_manager": naira(1)}, NOW9)
    return empire, team


# 1. An approval lapses if the member has left the desk or the empire.
def test_r1_an_approval_lapses_when_the_member_is_no_longer_at_the_desk(db):
    empire, team = tight(db)
    asked = objectives.accept(db, team["asset_manager"], "ac_ratios_e", NOW9)
    db.execute("UPDATE empire_seats SET player_id = NULL WHERE player_id = %s", (team["asset_manager"],))          # (the member has left)
    with pytest.raises(Exception, match="no longer sits"):
        firm.decide(db, team["head"], asked["approval_id"], True, "Yes.", NOW9)


# 3. The staff never approve work past a budget on their own.
def test_r3_the_staff_refuse_work_past_a_budget(db):
    empire, team = tight(db)
    asked = objectives.accept(db, team["asset_manager"], "ac_ratios_e", NOW9)
    approval = _one(db, "SELECT * FROM empire_approvals WHERE id = %s", (asked["approval_id"],))
    yes, why = firm.STAFF_RULES["empire_work"](db, approval, NOW9)
    assert not yes and "head" in why


# 4 and 6. The head sees the desk's other waiting requests; a refused request is not asked for again this quarter.
def test_r4_r6_the_head_sees_every_waiting_request_and_a_refusal_stands_for_the_quarter(db):
    empire, team = tight(db)
    first = objectives.accept(db, team["asset_manager"], "ac_ratios_e", NOW9)
    objectives.accept(db, team["asset_manager"], "ac_income_e", NOW9)
    approval = _one(db, "SELECT * FROM empire_approvals WHERE id = %s", (first["approval_id"],))
    shown = firm.VIEWERS["empire_work"](db, approval, team["head"], NOW9)["why"]
    assert any("1 other request" in line for line in shown)
    firm.decide(db, team["head"], first["approval_id"], False, "No.", NOW9)
    with pytest.raises(objectives.ObjectiveError, match="refused"):
        objectives.accept(db, team["asset_manager"], "ac_ratios_e", NOW9)


# 7. A desk's spending this quarter still counts after the member who spent it has left.
def test_r7_work_taken_counts_against_the_desk_after_its_member_leaves(db):
    empire, team = firm_of(db, n_cash=5_000_000_000)
    firm_money.set_budgets(db, team["head"], {"asset_manager": naira(1_000_000_000)}, NOW9)
    taken = objectives.accept(db, team["asset_manager"], "ac_ratios_e", NOW9)
    before = firm_money.committed_to_work(db, empires._empire(db, empire["id"]), 9, "asset_manager")
    assert before == taken["reward"] or before >= taken["reward"]
    db.execute("DELETE FROM empire_seats WHERE player_id = %s", (team["asset_manager"],))
    assert firm_money.committed_to_work(db, empires._empire(db, empire["id"]), 9, "asset_manager") == before


# 8 to 10. The library's figures are always possible, and no answer is the same whatever the figures.
def test_r8_r10_no_impossible_figures_and_no_fixed_answers(db):
    seen: dict = {}
    for n in range(12):
        player, _ = pro(db, "asset_manager", f"drawer{n}", level=20, cash_naira=1_000)
        ctx = objectives._context(db, player, NOW9)
        for code in ("am_covered_call", "ib_earnout", "ce_incentives", "ib_swap_rate", "am_immunise", "jn_breadth"):
            t = objectives.TEMPLATES[code]
            terms = t.offer(ctx)
            f = terms["figures"]
            answers = t.submit(ctx, {"terms": terms}, {})["answers"]
            if code == "am_covered_call":
                assert f["end"] >= 1
            if code == "jn_breadth":
                assert f["u"] != 25 and f["i"] != 0
            for key, value in answers.items():
                seen.setdefault((code, key), set()).add(str(value))
    for code, key in (("ib_earnout", "wins"), ("ce_incentives", "worth"), ("ib_swap_rate", "margin"), ("am_immunise", "price")):
        assert len(seen[(code, key)]) > 1, (code, key)
    _ = objectives_gap
