"""The gap stage, Part 3: ten ways a player might try to get round the head's approval and the new work, each closed."""

from __future__ import annotations

from datetime import timedelta

import pytest
from psycopg.rows import dict_row

from simulation import careers, firm, firm_money, objectives, objectives_gap, quarters
from simulation.money import naira
from tests.conftest import ADULT, after_quarters, join
from tests.test_builds import pro
from tests.test_careers import NOW9, sound
from tests.test_firm import firm_of

pytestmark = pytest.mark.world("eight")


def _one(db, sql, params=()):
    with db.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(sql, params).fetchall()
    return rows[0] if rows else None


def tight(db):
    """An empire whose Accountant's desk has almost no budget left."""
    empire, team = firm_of(db, n_cash=5_000_000_000)
    db.execute("UPDATE careers SET rank = 4, experience = %s WHERE player_id = %s", (careers.experience_for(100), team["accountant"]))
    firm_money.set_budgets(db, team["head"], {"accountant": naira(1)}, NOW9)
    return empire, team


def high(db, build, name):
    player, account = pro(db, build, name, level=20, cash_naira=1_000_000)
    db.execute("UPDATE careers SET rank = 4, experience = %s WHERE player_id = %s", (careers.experience_for(100), player))
    return player, account


# 1. Can a member approve their own request, or have another member of their desk do it?
def test_l1_only_the_head_or_deputy_decides_a_request_over_budget(db):
    empire, team = tight(db)
    asked = objectives.accept(db, team["accountant"], "ac_ratios_e", NOW9)
    for who in (team["accountant"], team["lawyer"], team["risk_manager"]):
        with pytest.raises(Exception):
            firm.decide(db, who, asked["approval_id"], True, "Fine.", NOW9)
    assert _one(db, "SELECT status FROM empire_approvals WHERE id = %s", (asked["approval_id"],))["status"] == "waiting"


# 2. Can an approval granted after the quarter closes slip past the next quarter's budget?
def test_l2_an_approval_from_a_closed_quarter_takes_nothing_on(db):
    empire, team = tight(db)
    asked = objectives.accept(db, team["accountant"], "ac_ratios_e", NOW9)
    quarters.close_due_quarters(db, after_quarters(9))
    later = after_quarters(9) + timedelta(hours=13)
    with pytest.raises(Exception, match="closed"):
        firm.decide(db, team["head"], asked["approval_id"], True, "Late.", later)
    assert not _one(db, "SELECT 1 FROM objectives WHERE player_id = %s AND template = 'ac_ratios_e'", (team["accountant"],))


# 3. Can a member pile up requests to get round the limit of empire work a quarter?
def test_l3_the_quarterly_limit_of_empire_work_still_holds(db, monkeypatch):
    from simulation import world_data as data
    empire, team = tight(db)
    db.execute("DELETE FROM empire_budgets WHERE empire_id = %s", (empire["id"],))
    monkeypatch.setattr(data, "EMPIRE_WORK_A_QUARTER", 1)
    objectives.accept(db, team["accountant"], "ac_ratios_e", NOW9)
    with pytest.raises(objectives.ObjectiveError, match="for their empire in a quarter"):
        objectives.accept(db, team["accountant"], "ac_income_e", NOW9)


# 4. Can the same work be taken twice in a quarter by going through the head?
def test_l4_approved_work_is_still_once_a_quarter(db):
    empire, team = tight(db)
    asked = objectives.accept(db, team["accountant"], "ac_ratios_e", NOW9)
    firm.decide(db, team["head"], asked["approval_id"], True, "Yes.", NOW9)
    with pytest.raises(objectives.ObjectiveError, match="already"):
        objectives.accept(db, team["accountant"], "ac_ratios_e", NOW9)


# 5. Does the website ever send the figures the answers are worked out from, or the answers?
def test_l5_new_work_sends_no_answers(db, client):
    assert join(client, ADULT).status_code == 201
    player = _one(db, "SELECT id FROM players WHERE display_name = 'Ada'")["id"]
    client.put("/api/career/build", json={"build": "accountant"})
    client.put("/api/career/bank", json={"ticker": "IKB"})
    client.put("/api/career/job", json={"ticker": "IDC"})
    db.execute("UPDATE careers SET rank = 4, experience = %s WHERE player_id = %s", (careers.experience_for(60), player))
    taken = client.post("/api/objectives", json={"template": "ac_dilution"})
    assert taken.status_code == 201, taken.text
    text = taken.text + client.get("/api/objectives").text
    assert '"figures":' not in text and '"answers"' not in text


# 6. Can a player below the level take a high-band piece by naming it?
def test_l6_high_band_work_is_locked_below_its_level(db):
    low, _ = pro(db, "risk_manager", "junior", level=30, cash_naira=1_000_000)
    for code in ("rm_crisis", "rm_crisis_e", "rm_crisis_w"):
        with pytest.raises(objectives.ObjectiveError):
            objectives.accept(db, low, code, NOW9)


# 7. Does an answer in the wrong unit pass?
def test_l7_an_answer_in_the_wrong_unit_fails(db):
    player, _ = high(db, "investment_banker", "unitslip")
    ctx = objectives._context(db, player, NOW9)
    t = objectives.TEMPLATES["ib_residual"]
    terms = t.offer(ctx)
    right = t.submit(ctx, {"terms": terms}, {})["answers"]
    wrong = {k: v * 1_000_000 if isinstance(v, float) else v for k, v in right.items()}           # naira, not millions
    assert t.submit(ctx, {"terms": terms}, wrong)["state"] == "failed"
    assert t.submit(ctx, {"terms": terms}, right)["state"] == "passed"


# 8. Do two players, or two settings, get the same numbers to copy from?
def test_l8_numbers_differ_between_players_and_settings(db):
    a, _ = high(db, "accountant", "copierone")
    b, _ = high(db, "accountant", "copiertwo")
    ta, tb = objectives.TEMPLATES["ac_lease"], objectives.TEMPLATES["ac_lease"]
    fa = ta.offer(objectives._context(db, a, NOW9))["figures"]
    fb = tb.offer(objectives._context(db, b, NOW9))["figures"]
    assert fa != fb
    fw = objectives.TEMPLATES["ac_lease_w"].offer(objectives._context(db, a, NOW9 + timedelta(days=4, hours=8)))
    if fw is not None:
        assert fw["figures"] != fa


# 9. Is a late weekend hand-in still marked?
def test_l9_a_late_weekend_paper_does_not_pass(db):
    from tests.test_mastery import FRIDAY9
    player, _ = high(db, "journalist", "latecomer")
    t = objectives.TEMPLATES["jn_breadth_w"]
    ctx = objectives._context(db, player, FRIDAY9)
    terms = t.offer(ctx)
    right = objectives.TEMPLATES["jn_breadth"].submit(ctx, {"terms": terms}, {})["answers"]
    late_ctx = {**ctx, "now": FRIDAY9 + timedelta(hours=10)}
    assert t.submit(late_ctx, {"terms": terms}, right)["state"] == "not_done"


# 10. Does the head's own work wait, and does a request show the desk's budget to the head?
def test_l10_the_heads_own_work_never_waits_and_the_request_shows_the_budget(db):
    empire, team = tight(db)
    db.execute("UPDATE careers SET rank = 4, experience = %s WHERE player_id = %s", (careers.experience_for(100), team["head"]))
    asked = objectives.accept(db, team["accountant"], "ac_ratios_e", NOW9)
    approval = _one(db, "SELECT * FROM empire_approvals WHERE id = %s", (asked["approval_id"],))
    shown = firm.VIEWERS["empire_work"](db, approval, team["head"], NOW9)
    assert any("budget" in line for line in shown["why"])
    head_build = _one(db, "SELECT build FROM players WHERE id = %s", (team["head"],))["build"]
    piece = next((t.code for t in objectives_gap.NEW if t.build == head_build), None)
    if piece:
        taken = objectives.accept(db, team["head"], piece + "_e", NOW9)
        assert "waiting" not in taken
    sound(db)
