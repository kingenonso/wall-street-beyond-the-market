"""Duels on the Floor (owner, 16 November 2026: chose "Duel on the Floor"): an empire's head challenges another empire for
the next live event; both are scored on the event's result for their money plus what their bankers earned on the Floor,
against their worth at the bell; the higher wins league points, once.

Promises: an empire the computer runs accepts at once; a player-run empire's head accepts or declines; a challenge not
answered by the bell lapses and counts as declined; three declines in a season are shown; the score runs live during
the event; the winner (or both, on a draw) gets its points once when the event is scored.

Loopholes: a challenge by someone who is not the head; two duels for one empire at one bell; a challenge too close to
the bell; answering a challenge meant for another empire; answering after the bell.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from psycopg.rows import dict_row

from simulation import duels, empires, liveevents
from simulation.money import naira
from tests.test_builds import pro
from tests.test_careers import NOW9
from tests.test_empires import founded
from tests.test_live_events import BELL, ring

pytestmark = pytest.mark.world("eight")


def _q(db, sql, params=()):
    with db.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def second_empire(db):
    head, _ = pro(db, "asset_manager", "rivalhead", level=20, cash_naira=60_000_000)
    empire = empires.found(db, head, "Harbour Row", naira(40_000_000), 0, NOW9)
    for build, name in (("investment_banker", "rb"), ("asset_manager", "ra"), ("risk_manager", "rr")):
        player, _ = pro(db, build, name, level=4, cash_naira=100_000)
        empires.apply(db, player, empire["id"], NOW9)
        asked = _q(db, "SELECT id FROM empire_applications WHERE player_id = %s AND status = 'waiting'", (player,))[0]["id"]
        empires.decide_application(db, head, asked, True, NOW9)
    return empires.open_empire(db, head, NOW9), head


def computer_empire(db):
    return _q(db, "SELECT * FROM empires WHERE status = 'active' AND kind <> 'pension' AND head_player_id IS NULL ORDER BY id LIMIT 1")[0]


def test_a_computer_run_empire_accepts_at_once_and_the_rules_hold(db):
    empire, (head, _), partners = founded(db)
    rival = computer_empire(db)
    with pytest.raises(duels.DuelError, match="head"):
        duels.challenge(db, partners["asset_manager"][0], rival["id"], NOW9)
    with pytest.raises(duels.DuelError, match="close 10 minutes"):
        duels.challenge(db, head, rival["id"], BELL - timedelta(minutes=5))
    done = duels.challenge(db, head, rival["id"], NOW9)
    assert done["accepted"] and done["bell"] == BELL
    with pytest.raises(duels.DuelError, match="already has a duel"):
        duels.challenge(db, head, computer_empire(db)["id"], NOW9)
    with pytest.raises(duels.DuelError, match="no such empire"):
        duels.challenge(db, head, empire["id"], NOW9)
    seen = duels.view(db, head, NOW9)
    assert seen["duels"][0]["status"] == "accepted" and seen["duels"][0]["rival"] == rival["name"]
    assert next(r for r in seen["rivals"] if r["id"] == rival["id"])["free"] is False


def test_a_player_run_empire_answers_and_declines_are_counted(db):
    _empire, (head, _), _partners = founded(db)
    rival, rival_head = second_empire(db)
    for day in range(3):
        bell = BELL + timedelta(days=2 * day)
        d = duels.challenge(db, head, rival["id"], bell - timedelta(hours=2))
        with pytest.raises(duels.DuelError, match="no such challenge"):
            duels.answer(db, head, d["duel_id"], True, bell - timedelta(hours=1))
        if day < 2:
            duels.answer(db, rival_head, d["duel_id"], False, bell - timedelta(hours=1))
        else:
            duels.tick(db, bell)                                        # not answered by the bell: lapsed
            with pytest.raises(duels.DuelError, match="no longer open"):
                duels.answer(db, rival_head, d["duel_id"], True, bell + timedelta(minutes=1))
    season = duels._season(db, NOW9)
    assert duels.declines(db, rival["id"], season) == 3
    shown = next(r for r in duels.view(db, head, BELL + timedelta(days=5))["rivals"] if r["id"] == rival["id"])
    assert shown["declines"] == 3


def test_the_duel_is_scored_live_and_the_winner_gets_its_points_once(db, monkeypatch):
    _empire, (head, _), _partners = founded(db)
    rival, rival_head = second_empire(db)
    d = duels.challenge(db, head, rival["id"], NOW9)
    duels.answer(db, rival_head, d["duel_id"], True, NOW9 + timedelta(minutes=1))
    event = ring(db, monkeypatch, "fraud")
    duels.tick(db, BELL + timedelta(minutes=1))
    live = duels.view(db, head, BELL + timedelta(minutes=5))["duels"][0]
    assert live["status"] == "accepted" and live["live"] is not None and set(live["live"]["you"]) == {"bps", "event_bps", "floor_bps"}
    liveevents.score(db, event["id"], BELL + timedelta(minutes=30))
    row = _q(db, "SELECT * FROM floor_duels WHERE id = %s", (d["duel_id"],))[0]
    assert row["status"] == "scored" and row["challenger_bps"] is not None
    refs = [r["reference"] for r in _q(db, "SELECT reference FROM league_points WHERE reference LIKE %s", (f"duel:{d['duel_id']}:%",))]
    assert refs == [f"duel:{d['duel_id']}:won"] if row["winner"] else len(refs) == 2
    liveevents.score(db, event["id"], BELL + timedelta(minutes=31))                 # once only
    assert len(_q(db, "SELECT 1 FROM league_points WHERE reference LIKE %s", (f"duel:{d['duel_id']}:%",))) == len(refs)
    past = duels.view(db, rival_head, BELL + timedelta(minutes=32))["duels"][0]
    assert past["status"] == "scored" and past["you_bps"] == row["challenged_bps"]
