"""The work for three builds (owner, 14 November 2026: "approve the tasks").

106 kinds of work on the board: the Asset Manager 32, the Investment Banker 30, the Risk Manager 20, the newsroom 10
(open to every build) and the head's 14. Thirty-eight kinds that repeated others are retired: never offered again, but
work in hand finishes and every record stays. See docs/TASKS_TRIM_AND_COMPETITION_PLAN_2026-11-14.md.
"""

from __future__ import annotations

from collections import Counter

import pytest
from psycopg.rows import dict_row

from simulation import careers, objectives, ranks
from tests.conftest import taken_before_retirement
from tests.test_builds import pro, right_answers
from tests.test_careers import NOW9

pytestmark = pytest.mark.world("eight")


def _one(db, sql, params=()):
    with db.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(sql, params).fetchall()
    return rows[0] if rows else None


def offered():
    return [t for t in objectives.TEMPLATES.values() if t.listed and t.setting == "solo" and not t.retired]


def test_there_are_106_kinds_of_work_balanced_across_the_three_builds():
    count = Counter(t.build for t in offered())
    assert count == {"asset_manager": 32, "investment_banker": 30, "risk_manager": 20, "newsroom": 10, "ceo": 14}
    assert len(objectives.RETIRED) == 38
    assert not objectives.RETIRED & objectives.NEWSROOM
    # Every retired kind still exists, in all three settings, so work in hand can be marked.
    for code in objectives.RETIRED:
        assert objectives.TEMPLATES[code].retired and objectives.TEMPLATES[code + "_e"].retired


def test_retired_work_is_never_offered_and_cannot_be_taken(db):
    player, _ = pro(db, "asset_manager", "trimmed", level=10, cash_naira=1_000_000)
    board = objectives.board(db, player, NOW9)
    shown = {o["template"] for o in board["offers"]}
    assert not shown & {code for t in objectives.RETIRED for code in (t, t + "_e", t + "_w")}
    with pytest.raises(objectives.ObjectiveError, match="no longer offered"):
        objectives.accept(db, player, "ac_forecast", NOW9)
    assert all(m["template"] not in objectives.RETIRED for m in objectives.modules("asset_manager"))


def test_work_taken_before_it_was_retired_still_finishes_and_pays(db, monkeypatch):
    player, _ = pro(db, "asset_manager", "inhand", level=10, cash_naira=1_000_000)
    taken_before_retirement(monkeypatch, "ac_bills")
    taken = objectives.accept(db, player, "ac_bills", NOW9)
    monkeypatch.undo()                                   # retired again, with the work still in hand
    assert objectives.TEMPLATES["ac_bills"].retired
    answers = right_answers(db, taken["id"])
    done = objectives.submit(db, player, taken["id"], answers, NOW9)
    assert done["state"] in ("passed", "submitted")      # marked now, or judged when the company files


@pytest.mark.parametrize("build", ["asset_manager", "investment_banker", "risk_manager"])
def test_the_newsroom_is_open_to_every_build_and_its_experience_goes_to_their_own(db, build):
    player, _ = pro(db, build, f"reporter-{build}", level=5, cash_naira=1_000_000)
    board = objectives.board(db, player, NOW9)
    assert "newsroom" in [t["track"] for t in board["tracks"]]
    assert {o["template"] for o in board["offers"] if o["track"] == "newsroom"} >= set(objectives.NEWSROOM)
    before = careers.career(db, player)["experience"]
    taken = objectives.accept(db, player, "jr_economy", NOW9)
    assert _one(db, "SELECT track, build FROM objectives WHERE id = %s", (taken["id"],)) == {"track": "newsroom", "build": build}
    done = objectives.submit(db, player, taken["id"], right_answers(db, taken["id"]), NOW9)
    assert done["state"] == "passed"
    assert careers.career(db, player)["experience"] > before


def test_each_build_has_its_own_rank_case():
    # A dictionary keeps the last of two entries under one name: the retired builds' cases had overwritten two of these.
    assert set(ranks.CASES) == {"asset_manager", "investment_banker", "risk_manager", "ceo"}
    assert ranks.CASES["asset_manager"][0].startswith("A client's portfolio")
    assert ranks.CASES["investment_banker"][0].startswith("A full company valuation")
    for _title, parts in ranks.CASES.values():
        assert all(not objectives.TEMPLATES[code].retired for code, _ in parts)
