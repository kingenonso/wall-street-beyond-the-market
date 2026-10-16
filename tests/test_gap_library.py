"""The gap stage, Part 3: the work library brought to the design's 350, with the higher bands (Levels 41 to 100) and the
Stage 8 and 9 subjects; every new piece in three settings, with "How to do this", judged right and wrong."""

from __future__ import annotations

import pytest

from simulation import careers, empires, objectives, objectives_gap
from tests.test_builds import pro
from tests.test_careers import NOW9
from tests.test_mastery import FRIDAY9, computer_empire

pytestmark = pytest.mark.world("eight")
TRACKS = (*careers.BUILDS, "ceo")


def test_the_library_holds_at_least_350_pieces_and_every_new_one_comes_three_ways():
    assert len(objectives.TEMPLATES) >= 350
    assert len(objectives_gap.NEW) >= 62
    for t in objectives_gap.NEW:
        settings = {x.setting for x in objectives.TEMPLATES.values() if x.root == t.code}
        assert settings == {"solo", "empire", "live"}, t.code
        assert 41 <= t.level <= 100, t.code
        assert objectives.how_to(t) and objectives.how_to(objectives.TEMPLATES[t.code + "_e"]) == objectives.how_to(t)
    # Every track has work in each of the higher bands.
    for track in careers.BUILDS:
        levels = [t.level for t in objectives_gap.NEW if t.build == track]
        assert min(levels) <= 45 and max(levels) >= 94 and any(55 <= x < 80 for x in levels), track
    ceo = [t.level for t in objectives_gap.NEW if t.build == "ceo"]
    assert min(ceo) >= 60 and max(ceo) >= 95
    # The Stage 8 and 9 subjects are covered.
    words = " ".join(f"{t.module} {t.title}" for t in objectives_gap.NEW).lower()
    for subject in ("property", "zoning", "swap", "hedg", "mezzanine", "earn-out", "preferred", "mortgage", "development", "lease"):
        assert subject in words, subject


def test_every_new_piece_is_offered_judged_right_when_right_and_wrong_when_blank(db):
    """For a player at Level 100 of each track: the piece is on offer; the right answers pass; a blank sheet fails."""
    from psycopg.rows import dict_row
    checked = 0
    for index, track in enumerate(TRACKS):
        player, _ = pro(db, "accountant" if track == "ceo" else track, f"lib{index}", level=20, cash_naira=1_000_000)
        db.execute("UPDATE careers SET rank = 4, experience = %s WHERE player_id = %s", (careers.experience_for(100), player))
        ctx = objectives._context(db, player, NOW9)
        for t in [x for x in objectives_gap.NEW if x.build == track]:
            terms = t.offer(ctx)
            assert terms and terms["fields"] and terms["given"], t.code
            objective = {"terms": terms, "progress": {}}
            blank = t.submit(ctx, objective, {})
            assert blank["state"] == "failed", t.code
            right = {k: v for k, v in blank["answers"].items()}
            verdict = t.submit(ctx, objective, right)
            assert verdict["state"] == "passed", (t.code, verdict["summary"])
            assert verdict["debrief"]["plain"] and verdict["debrief"]["maths"], t.code
            checked += 1
    assert checked == len(objectives_gap.NEW)
    _ = dict_row


def test_new_work_is_locked_below_its_level_and_on_the_board_above_it(db):
    player, _ = pro(db, "accountant", "lowlevel", level=10, cash_naira=1_000_000)
    with pytest.raises(objectives.ObjectiveError, match="opens at Level 41"):
        objectives.accept(db, player, "ac_income_value", NOW9)
    high, _ = pro(db, "accountant", "highlevel", level=20, cash_naira=1_000_000)
    db.execute("UPDATE careers SET rank = 4, experience = %s WHERE player_id = %s", (careers.experience_for(60), high))
    taken = objectives.accept(db, high, "ac_income_value", NOW9)
    assert taken["state"] == "active" and "figures" not in taken["terms"]          # the figures behind the answers stay on the server
    empires.apply(db, high, computer_empire(db)["id"], NOW9)
    board = objectives.board(db, high, FRIDAY9)
    assert any(o["template"] == "ac_dilution_w" and o["available"] for o in board["offers"])
