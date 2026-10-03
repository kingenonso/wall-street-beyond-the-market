"""Stage 7: the syllabus maps, the three settings of work, mastery, rank cases, levels above 20,
the CEO rank, and the coverage tracker."""

from __future__ import annotations

from datetime import timedelta

import pytest
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from simulation import careers, empires, ledger, objectives, quarters, ranks
from simulation import world_data as data
from simulation.money import naira
from tests.conftest import after_quarters
from tests.test_builds import EMPLOYER, pro
from tests.test_careers import NOW9, sound
from tests.test_empires import computer_empire, founded
from tests.test_objectives import give_cash

pytestmark = pytest.mark.world("eight")
FRIDAY9 = after_quarters(8) + timedelta(days=4, hours=18)            # Friday 19:00 in the ninth quarter: the challenge is open
TRACKS = ("accountant", "asset_manager", "investment_banker", "risk_manager", "lawyer", "journalist")


def _dicts(db, sql, params=()):
    with db.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def answers_for(db, objective_id, now) -> dict:
    """The right answers, read back from a paper marked with nothing on it (in a twin of the moment)."""
    row = _dicts(db, "SELECT player_id FROM objectives WHERE id = %s", (objective_id,))[0]
    with db.transaction(force_rollback=True):
        return objectives.submit(db, row["player_id"], objective_id, {}, now)["result"]["answers"]


def do(db, player, code, now) -> dict:
    """Take a piece of hand-in work on and hand in the right answers."""
    taken = objectives.accept(db, player, code, now)
    return objectives.submit(db, player, taken["id"], answers_for(db, taken["id"], now), now)


def master(db, player, track, stages=("solo", "empire", "live"), modules=None, period=None) -> None:
    """Write passed work straight into the record, so that a test about ranks need not do forty pieces of work.
    (Each setting in a quarter of its own, as the rules require.)"""
    build = _dicts(db, "SELECT build FROM players WHERE id = %s", (player,))[0]["build"]
    account = ledger.player_account_id(db, player)
    for m in objectives.modules(track)[:modules]:
        for stage in stages:
            code = m["template"] + {"solo": "", "empire": "_e", "live": "_w"}[stage]
            when = period if period is not None else {"solo": 1, "empire": 2, "live": 3}[stage]
            db.execute("INSERT INTO objectives (player_id, build, template, module, period, payer_account_id, payer_name, title, terms, reward,"
                       " experience, accepted_at, state, judged_at, judged_period, judged_seq, setting, track, root) VALUES (%s, %s, %s, %s, %s, %s,"
                       " 'Test', %s, %s, 0, 0, %s, 'passed', %s, %s, nextval('objectives_judged_seq'), %s, %s, %s) ON CONFLICT DO NOTHING",
                       (player, build, code, m["module"], when, account, m["title"], Jsonb({}), NOW9, NOW9, when, stage, track, m["template"]))


def right_case(db, player, case_id, now) -> dict:
    """The right answers to a case, read from the server's own record of a blank paper (in a twin of the moment).
    A player is never shown them while the quarter runs."""
    with db.transaction(force_rollback=True):
        ranks.hand_in(db, player, case_id, {}, now)
        marked = _dicts(db, "SELECT result FROM rank_cases WHERE id = %s", (case_id,))[0]["result"]
    return {part["template"]: part["answers"] for part in marked["parts"]}


# ---------------------------------------------------------------------------
# The library and the syllabus maps
# ---------------------------------------------------------------------------

def test_every_module_has_work_alone_with_the_empire_and_as_a_weekend_challenge():
    assert len([t for t in objectives.TEMPLATES.values() if t.listed]) >= 120
    for track in (*TRACKS, "ceo"):
        modules = objectives.modules(track)
        assert len(modules) == 6 and len({m["module"] for m in modules}) == 6
        for m in modules:
            versions = {t.setting for t in objectives.TEMPLATES.values() if t.build == track and t.module == m["module"] and t.listed}
            assert versions == {"solo", "empire", "live"}, (track, m["module"])
    # Every piece of work is tagged with its module and its track; nothing is left untagged.
    assert all(t.module and t.build in (*TRACKS, "ceo") for t in objectives.TEMPLATES.values())


def test_the_names_of_exam_bodies_appear_nowhere_in_the_library():
    banned = ("CFA", "FRM", "ICAN", "ACCA", "CPA", "CRM", "Bar final", "Chartered")
    for t in objectives.TEMPLATES.values():
        text = " ".join((t.module, t.title, t.idea))
        assert not any(name in text for name in banned), t.code
    for track in (*TRACKS, "ceo"):
        assert not any(name in objectives.track_name(track) for name in banned)


def test_every_piece_of_work_in_every_setting_can_really_be_offered(db):
    """No module is left without work that can be taken. Checked for each track, in the weekend
    window, for a member of an empire."""
    never = []
    empire = computer_empire(db)
    for index, track in enumerate(TRACKS):
        player, _ = pro(db, track, f"p{index}", level=20, cash_naira=500_000)
        empires.apply(db, player, empire["id"], NOW9)
        board = objectives.board(db, player, FRIDAY9)
        assert {o["track"] for o in board["offers"]} == {track}
        for offer in board["offers"]:
            if not offer["available"] and offer["template"] not in ("lw_pact",):
                never.append((offer["template"], offer["why_not"]))
    # Work that waits on something in the world (a bid in progress, a company in difficulty) may not be on offer at
    # every moment; everything else must be.
    waits = {"ib_outcome", "ac_bills", "lw_claims", "lw_default", "ac_rating", "rm_credit", "jr_scoop", "ib_bid"}
    assert [n for n in never if n[0].split("_e")[0].split("_w")[0] not in waits] == []


def test_the_three_settings_draw_their_own_client_or_numbers(db):
    player, _ = pro(db, "accountant", level=6)
    empires.apply(db, player, computer_empire(db)["id"], NOW9)
    ctx = objectives._context(db, player, FRIDAY9)
    seen = {}
    for code in ("ac_ratios", "ac_ratios_e", "ac_ratios_w", "ac_income", "ac_income_e", "ac_income_w", "ac_cash_flow", "ac_cash_flow_e",
                 "ac_cash_flow_w"):
        seen[code] = objectives.TEMPLATES[code].offer(ctx)["client"]["ticker"]
    # Across three pieces of work, the three settings are not all on the same company.
    assert any(len({seen[base], seen[base + "_e"], seen[base + "_w"]}) > 1 for base in ("ac_ratios", "ac_income", "ac_cash_flow"))
    # And the draw for one setting is the same every time it is asked for.
    assert objectives.TEMPLATES["ac_ratios_e"].offer(ctx)["client"]["ticker"] == seen["ac_ratios_e"]


# ---------------------------------------------------------------------------
# Mastery: learned, practised, proven
# ---------------------------------------------------------------------------

def test_a_module_is_learned_alone_practised_with_the_empire_and_proven_in_a_weekend_challenge(db):
    player, account = pro(db, "accountant", level=6)
    empire = computer_empire(db)

    def stage(now):
        return next(s for s in objectives.board(db, player, now)["skills"] if s["module"] == "Reading financial statements")

    assert stage(NOW9)["stage"] == "not yet"
    # With the empire: needs a seat.
    with pytest.raises(objectives.ObjectiveError, match="members of an open empire"):
        objectives.accept(db, player, "ac_ratios_e", NOW9)
    assert do(db, player, "ac_ratios", NOW9)["state"] == "passed"
    assert stage(NOW9)["stage"] == "learned" and stage(NOW9)["learned"] and not stage(NOW9)["practised"]
    empires.apply(db, player, empire["id"], NOW9)
    # One setting of each module a quarter: the same answers cannot be handed in three times.
    for code in ("ac_ratios_e", "ac_ratios_w"):
        with pytest.raises(objectives.ObjectiveError, match="another setting"):
            objectives.accept(db, player, code, FRIDAY9)
        offer = next(o for o in objectives.board(db, player, FRIDAY9)["offers"] if o["template"] == code)
        assert not offer["available"] and "another setting" in offer["why_not"]
    # The next quarter: with the empire.
    quarters.close_due_quarters(db, after_quarters(9))
    now10, friday10 = after_quarters(9) + timedelta(hours=12), after_quarters(9) + timedelta(days=4, hours=18)
    before, empire_before = ledger.balance(db, account), ledger.balance(db, empire["account_id"])
    done = do(db, player, "ac_ratios_e", now10)
    assert done["state"] == "passed" and done["setting"] == "empire" and done["payer"] == empire["name"]
    # The empire paid, out of its own cash.
    assert ledger.balance(db, account) - before == done["reward"] == empire_before - ledger.balance(db, empire["account_id"])
    assert stage(now10)["stage"] == "practised"
    # The weekend challenge is closed on a Monday, and open on Friday evening.
    quarters.close_due_quarters(db, after_quarters(10))
    now11, friday11 = after_quarters(10) + timedelta(hours=12), after_quarters(10) + timedelta(days=4, hours=18)
    with pytest.raises(objectives.ObjectiveError, match="Friday"):
        objectives.accept(db, player, "ac_ratios_w", now11)
    offer = next(o for o in objectives.board(db, player, now11)["offers"] if o["template"] == "ac_ratios_w")
    assert not offer["available"] and "Weekend challenges open on Friday" in offer["why_not"]
    solo = next(o for o in objectives.board(db, player, friday11)["offers"] if o["template"] == "ac_ratios")
    live = next(o for o in objectives.board(db, player, friday11)["offers"] if o["template"] == "ac_ratios_w")
    assert live["available"] and live["reward"] == solo["reward"] * 3 // 2 and live["experience"] == solo["experience"] * 3 // 2
    # The clock starts when a challenge is taken on, so its client and figures are not shown before.
    assert live["client"] is None and "the moment you take the challenge on" in live["situation"]
    won = do(db, player, "ac_ratios_w", friday11)
    assert won["state"] == "passed" and won["setting"] == "live"
    assert stage(friday11)["stage"] == "proven" and stage(friday11)["stage_number"] == 3
    tracker = objectives.board(db, player, friday11)["tracks"][0]
    assert (tracker["learned"], tracker["practised"], tracker["proven"], tracker["modules"]) == (1, 1, 1, 6)
    assert tracker["learned_pct"] == 17 and tracker["name"] == "Accountant"
    # The empire gained league points for both.
    points = _dicts(db, "SELECT points, why FROM league_points WHERE empire_id = %s AND period IN (10, 11) AND reference LIKE 'objective:%%'"
                        " ORDER BY id", (empire["id"],))
    assert [p["points"] for p in points] == [data.LEAGUE_POINTS["work"], data.LEAGUE_POINTS["challenge"]]
    sound(db)


def test_practised_before_learned_shows_as_not_yet_and_each_setting_is_once_a_quarter(db):
    player, _ = pro(db, "accountant", level=6)
    empires.apply(db, player, computer_empire(db)["id"], NOW9)
    do(db, player, "ac_ratios_e", NOW9)
    skill = next(s for s in objectives.board(db, player, NOW9)["skills"] if s["module"] == "Reading financial statements")
    assert skill["practised"] and not skill["learned"] and skill["stage"] == "not yet"
    with pytest.raises(objectives.ObjectiveError, match="already taken"):
        objectives.accept(db, player, "ac_ratios_e", NOW9)


def test_a_weekend_challenge_is_timed_and_a_late_paper_does_not_pass(db):
    player, account = pro(db, "accountant", level=6)
    taken = objectives.accept(db, player, "ac_ratios_w", FRIDAY9)
    assert taken["terms"]["hand_in_by"] and "3 hours" in taken["terms"]["deadline"]
    right = answers_for(db, taken["id"], FRIDAY9)
    before = ledger.balance(db, account)
    late = objectives.submit(db, player, taken["id"], right, FRIDAY9 + timedelta(hours=3, minutes=1))
    assert late["state"] == "not_done" and ledger.balance(db, account) == before
    # Taken near the end of the window, the time allowed stops when the window closes.
    other, _ = pro(db, "accountant", "late", level=6)
    sunday = FRIDAY9 + timedelta(days=2, hours=2, minutes=30)           # Sunday 21:30
    assert objectives.weekend(sunday)["open"] and not objectives.weekend(sunday + timedelta(minutes=31))["open"]
    last = objectives.accept(db, other, "ac_ratios_w", sunday)
    assert last["terms"]["hand_in_by"] == objectives.weekend(sunday)["closes"].isoformat()


def test_one_member_cannot_draw_pay_from_their_empire_without_end(db, monkeypatch):
    player, _ = pro(db, "accountant", level=6)
    empires.apply(db, player, computer_empire(db)["id"], NOW9)
    assert data.EMPIRE_WORK_A_QUARTER == 8
    monkeypatch.setattr(data, "EMPIRE_WORK_A_QUARTER", 1)
    do(db, player, "ac_ratios_e", NOW9)
    with pytest.raises(objectives.ObjectiveError, match="pieces of work for their empire"):
        objectives.accept(db, player, "ac_income_e", NOW9)
    offer = next(o for o in objectives.board(db, player, NOW9)["offers"] if o["template"] == "ac_income_e")
    assert not offer["available"] and "most one member may" in offer["why_not"]


# ---------------------------------------------------------------------------
# Levels above 20 and rank cases
# ---------------------------------------------------------------------------

def test_a_career_stops_at_each_gate_until_its_rank_case_is_passed():
    lots = careers.experience_for(100) * 2
    assert [careers.level_for(lots, rank) for rank in range(5)] == [20, 40, 60, 80, 100]
    assert careers.level_for(careers.experience_for(35), 1) == 35 and careers.level_for(careers.experience_for(35), 0) == 20
    assert careers.level_for(careers.experience_for(50), 2) == 50 == data.RETIREMENT_LEVEL
    assert data.RANK_GATES == (20, 40, 60, 80) and data.TOP_LEVEL == 100


def test_a_rank_case_needs_the_level_and_the_mastery_and_its_fee_leaves_the_economy(db):
    player, account = pro(db, "accountant", level=19, cash_naira=1_000_000)
    where = ranks.standing(db, player, NOW9)["tracks"][0]
    assert where["gate"] == 20 and not where["can_begin"] and "Reach Level 20" in where["why_not"]
    with pytest.raises(ranks.RankError, match="Reach Level 20"):
        ranks.begin(db, player, "accountant", NOW9)
    careers.add_experience(db, player, "accountant", careers.experience_for(25), NOW9)
    assert careers.career(db, player)["level"] == 20                       # held at the gate; the experience is kept
    with pytest.raises(ranks.RankError, match="must be learned"):
        ranks.begin(db, player, "accountant", NOW9)
    master(db, player, "accountant", stages=("solo",))
    with pytest.raises(ranks.RankError, match="3 modules must be practised"):
        ranks.begin(db, player, "accountant", NOW9)
    master(db, player, "accountant", stages=("empire",), modules=3)
    master(db, player, "accountant", stages=("live",), modules=1)
    where = ranks.standing(db, player, NOW9)["tracks"][0]
    assert where["can_begin"] and where["fee"] > 0 and [n["met"] for n in where["needs"]] == [True, True, True]
    # Somebody without the fee cannot begin, and nothing is taken.
    poor, poor_account = pro(db, "accountant", "poor", level=20)
    master(db, poor, "accountant")
    assert ledger.balance(db, poor_account) < naira(200_000)
    with pytest.raises(ranks.RankError, match="do not have that much cash"):
        ranks.begin(db, poor, "accountant", NOW9)
    assert _dicts(db, "SELECT count(*) AS n FROM rank_cases WHERE player_id = %s", (poor,))[0]["n"] == 0
    pool = ledger.account_id(db, ledger.PRIZE_POOL)
    before, pool_before = ledger.balance(db, account), ledger.balance(db, pool)
    case = ranks.begin(db, player, "accountant", NOW9)
    assert before - ledger.balance(db, account) == case["fee"] == ledger.balance(db, pool) - pool_before
    assert len(case["parts"]) == 3 and case["company"]["ticker"] and case["state"] == "active" and case["result"] is None
    # Nothing a player is shown before judging gives an answer away.
    assert "answers" not in str(case) and "filed_period" not in str(case) and "salt" not in str(case)
    with pytest.raises(ranks.RankError, match="in hand"):
        ranks.begin(db, player, "accountant", NOW9)
    # Another player's case is not theirs to hand in or see.
    with pytest.raises(ranks.RankError, match="no such"):
        ranks.hand_in(db, poor, case["id"], {}, NOW9)
    sound(db)


def test_a_failed_case_can_be_sat_again_after_three_real_days_on_a_fresh_case(db):
    player, account = pro(db, "accountant", level=20, cash_naira=2_000_000)
    master(db, player, "accountant")
    case = ranks.begin(db, player, "accountant", NOW9)
    failed = ranks.hand_in(db, player, case["id"], {"ac_ratios": {"ebitda": 1}}, NOW9)
    assert failed["state"] == "failed" and failed["result"]["score"] < failed["pass_mark"] == 80
    assert careers.career(db, player)["rank"] == 0
    with pytest.raises(ranks.RankError, match="judged already"):
        ranks.hand_in(db, player, case["id"], right_case(db, player, case["id"], NOW9) if False else {}, NOW9)
    with pytest.raises(ranks.RankError, match="after 3 real days"):
        ranks.begin(db, player, "accountant", NOW9 + timedelta(days=2, hours=23))
    again = ranks.begin(db, player, "accountant", NOW9 + timedelta(days=3, minutes=1))
    # The fee is paid again, and the case is a different one.
    assert again["company"]["ticker"] != case["company"]["ticker"]
    assert _dicts(db, "SELECT count(*) AS n FROM ledger_transactions WHERE kind = 'rank_case_fee'")[0]["n"] == 2


def test_passing_the_case_opens_the_levels_above_and_work_then_teaches_more(db):
    player, account = pro(db, "accountant", level=20, cash_naira=2_000_000)
    careers.add_experience(db, player, "accountant", careers.experience_for(23), NOW9)
    master(db, player, "accountant")
    case = ranks.begin(db, player, "accountant", NOW9)
    done = ranks.hand_in(db, player, case["id"], right_case(db, player, case["id"], NOW9), NOW9)
    assert done["state"] == "passed" and done["result"]["score"] == 100
    # The debrief: every figure is marked and the method is given at once...
    assert all(part["milestones"] and part["debrief"]["method"] for part in done["result"]["parts"])
    # ...but the worked answers are held back until the quarter has closed, so that they cannot be carried into another case.
    assert "held_back" in done["result"] and not any("answers" in part or part["debrief"]["maths"] for part in done["result"]["parts"])
    mine = careers.career(db, player)
    assert mine["rank"] == 1 and mine["level"] > 20                       # the experience held at the gate now counts
    events = [e["kind"] for e in _dicts(db, "SELECT kind FROM career_events WHERE player_id = %s ORDER BY id", (player,))]
    assert "rank_passed" in events and events.count("level_up") >= mine["level"] - 20
    profile = careers.profile(db, player, NOW9)["career"]
    assert profile["rank_name"] == "Professional" and profile["gate"] == 40 and not profile["at_cap"]
    quarters.close_due_quarters(db, after_quarters(9))
    later = ranks.standing(db, player, after_quarters(9) + timedelta(hours=12))["past"][0]
    assert "held_back" not in later["result"] and all(p["answers"] and p["debrief"]["plain"] and p["debrief"]["maths"] for p in later["result"]["parts"])
    # The next gate is Level 40, and asks for more.
    nxt = ranks.standing(db, player, NOW9)["tracks"][0]
    assert nxt["gate"] == 40 and nxt["fee"] > case["fee"] and nxt["pass_mark"] == 85
    # Work now teaches twice as much.
    offer = next(o for o in objectives.board(db, player, NOW9)["offers"] if o["template"] == "ac_income")
    assert offer["experience"] == 2 * objectives.TEMPLATES["ac_income"].experience
    sound(db)


def test_a_case_not_handed_in_lapses_and_a_late_one_is_not_marked(db):
    player, _ = pro(db, "accountant", level=20, cash_naira=2_000_000)
    master(db, player, "accountant")
    case = ranks.begin(db, player, "accountant", NOW9)
    right = right_case(db, player, case["id"], NOW9)
    late = ranks.hand_in(db, player, case["id"], right, NOW9 + timedelta(hours=data.RANK_CASE_HOURS, minutes=1))
    assert late["state"] == "not_done" and careers.career(db, player)["rank"] == 0
    other, _ = pro(db, "accountant", "other", level=20, cash_naira=2_000_000)
    master(db, other, "accountant")
    waiting = ranks.begin(db, other, "accountant", after_quarters(8) + timedelta(days=6))
    assert waiting["due_at"] == after_quarters(9) - timedelta(hours=1)         # never past the end of the quarter
    quarters.close_due_quarters(db, after_quarters(9))
    assert _dicts(db, "SELECT state FROM rank_cases WHERE id = %s", (waiting["id"],))[0]["state"] == "not_done"


@pytest.mark.parametrize("track", TRACKS)
def test_every_build_has_a_rank_case_made_from_the_live_world_that_can_be_passed(db, track):
    player, _ = pro(db, track, level=20, cash_naira=2_000_000)
    master(db, player, track)
    case = ranks.begin(db, player, track, NOW9)
    assert len(case["parts"]) >= 3 and all(part["terms"]["fields"] and part["terms"]["situation"] for part in case["parts"])
    right = right_case(db, player, case["id"], NOW9)
    assert all(right.values())
    done = ranks.hand_in(db, player, case["id"], right, NOW9)
    assert done["state"] == "passed" and done["result"]["score"] == 100, done["result"]
    assert careers.career(db, player)["rank"] == 1
    # A second player's case in the same quarter is on a different company.
    second, _ = pro(db, track, "second", level=20, cash_naira=2_000_000)
    master(db, second, track)
    other = ranks.begin(db, second, track, NOW9)
    if case["company"]:
        assert other["company"]["ticker"] != case["company"]["ticker"]


def test_the_later_gates_ask_for_every_module_proven(db):
    player, _ = pro(db, "accountant", level=20, cash_naira=9_000_000)
    db.execute("UPDATE careers SET rank = 2, experience = %s WHERE player_id = %s", (careers.experience_for(60), player))
    assert careers.career(db, player)["level"] == 60
    master(db, player, "accountant", stages=("solo", "empire"))
    master(db, player, "accountant", stages=("live",), modules=5)
    where = ranks.standing(db, player, NOW9)["tracks"][0]
    assert where["gate"] == 60 and not where["can_begin"] and "6 modules must be proven" in where["why_not"]
    assert where["needs"][2]["missing"] == ["Credit analysis"]
    master(db, player, "accountant", stages=("live",))
    assert ranks.standing(db, player, NOW9)["tracks"][0]["can_begin"]


def test_retirement_at_level_fifty_can_now_be_reached(db):
    player, _ = pro(db, "accountant", level=20)
    assert not careers.retirement_opens(db, player, 9)["eligible"]
    db.execute("UPDATE careers SET rank = 2, experience = %s WHERE player_id = %s", (careers.experience_for(50), player))
    assert careers.career(db, player)["level"] == 50 and careers.retirement_opens(db, player, 9)["eligible"]
    # Experience alone is not enough: without the rank cases the career stays at the gate.
    db.execute("UPDATE careers SET rank = 0 WHERE player_id = %s", (player,))
    assert not careers.retirement_opens(db, player, 9)["eligible"]


def test_a_player_can_report_marking_they_believe_is_wrong_once(db):
    player, _ = pro(db, "accountant", level=6)
    done = do(db, player, "ac_ratios", NOW9)
    with pytest.raises(ranks.RankError, match="ten to six hundred"):
        ranks.report(db, player, "wrong", NOW9, objective_id=done["id"])
    ranks.report(db, player, "The margin should be on operating profit.", NOW9, objective_id=done["id"])
    with pytest.raises(ranks.RankError, match="already reported"):
        ranks.report(db, player, "The margin should be on operating profit.", NOW9, objective_id=done["id"])
    stranger, _ = pro(db, "accountant", "stranger")
    with pytest.raises(ranks.RankError, match="judged"):
        ranks.report(db, stranger, "This is not my work at all.", NOW9, objective_id=done["id"])


# ---------------------------------------------------------------------------
# The leadership track and the CEO rank
# ---------------------------------------------------------------------------

def test_the_leadership_track_opens_to_a_head_or_at_level_forty_and_its_experience_goes_to_the_players_build(db):
    junior, _ = pro(db, "accountant", level=20)
    assert [t["track"] for t in objectives.board(db, junior, NOW9)["tracks"]] == ["accountant"]
    with pytest.raises(objectives.ObjectiveError, match="not open"):
        objectives.accept(db, junior, "ce_return", NOW9)
    db.execute("UPDATE careers SET rank = 1, experience = %s WHERE player_id = %s", (careers.experience_for(40), junior))
    board = objectives.board(db, junior, NOW9)
    assert [t["track"] for t in board["tracks"]] == ["accountant", "ceo"] and board["tracks"][1]["name"] == "Leadership"
    before = careers.career(db, junior)["experience"]
    done = do(db, junior, "ce_return", NOW9)
    assert done["state"] == "passed" and done["track"] == "ceo"
    assert careers.career(db, junior)["experience"] == before + done["experience"]
    skill = next(s for s in objectives.board(db, junior, NOW9)["skills"] if s["track"] == "ceo" and s["module"] == "Return on capital")
    assert skill["stage"] == "learned"
    # A head has it from the day they lead.
    _empire, (head, _), _ = founded(db)
    assert "ceo" in [t["track"] for t in objectives.board(db, head, NOW9)["tracks"]]


@pytest.mark.parametrize("code", ["ce_return", "ce_payout", "ce_breakeven", "ce_allocate", "ce_buy", "ce_people", "lw_contract"])
def test_the_new_work_is_marked_against_the_record(db, code):
    build = "lawyer" if code == "lw_contract" else "accountant"
    player, account = pro(db, build, level=20)
    db.execute("UPDATE careers SET rank = 1, experience = %s WHERE player_id = %s", (careers.experience_for(40), player))
    taken = objectives.accept(db, player, code, NOW9)
    right = answers_for(db, taken["id"], NOW9)
    assert set(right) == {f["key"] for f in taken["terms"]["fields"]}
    # A paper with every figure wrong does not pass, and pays nothing.
    twin, _ = pro(db, build, "twin", level=20)
    db.execute("UPDATE careers SET rank = 1, experience = %s WHERE player_id = %s", (careers.experience_for(40), twin))
    other = objectives.accept(db, twin, code, NOW9)
    wrong = {f["key"]: ("zzz" if f["kind"] == "choice" else -12345.6) for f in other["terms"]["fields"]}
    assert objectives.submit(db, twin, other["id"], wrong, NOW9)["state"] == "failed"
    before = ledger.balance(db, account)
    done = objectives.submit(db, player, taken["id"], right, NOW9)
    assert done["state"] == "passed" and ledger.balance(db, account) - before == done["paid"] > 0
    assert done["result"]["debrief"]["plain"] and done["result"]["debrief"]["maths"]
    sound(db)


def test_the_ceo_rank_needs_level_sixty_the_case_and_a_reputation_of_seventy_five(db):
    empire, (head, account), partners = founded(db)
    give_cash(db, account, 5_000_000)
    assert not empires.is_ceo(db, head)
    room = empires.war_room(db, head, NOW9)
    cash = ledger.balance(db, empire["account_id"])
    assert not room["head_is_ceo"] and room["signing_limit"] == cash * data.HEAD_LIMIT_BPS // 10_000
    master(db, head, "ceo", stages=("solo",))
    master(db, head, "ceo", stages=("empire",), modules=3)
    master(db, head, "ceo", stages=("live",), modules=1)
    where = next(t for t in ranks.standing(db, head, NOW9)["tracks"] if t["track"] == "ceo")
    assert where["can_begin"] and not where["ceo"]["earned"] and not where["ceo"]["level"]["met"]
    case = ranks.begin(db, head, "ceo", NOW9)
    done = ranks.hand_in(db, head, case["id"], right_case(db, head, case["id"], NOW9), NOW9)
    assert done["state"] == "passed"
    # The case alone is not the rank: Level 60 and the reputation are needed too.
    assert not empires.is_ceo(db, head)
    db.execute("UPDATE careers SET rank = 3, experience = %s WHERE player_id = %s", (careers.experience_for(60), head))
    db.execute("UPDATE players SET reputation = 74 WHERE id = %s", (head,))
    assert not ranks.ceo_check(db, head, NOW9)
    db.execute("UPDATE players SET reputation = 75 WHERE id = %s", (head,))
    assert ranks.ceo_check(db, head, NOW9) and empires.is_ceo(db, head)
    # The caps of an Acting Head lift.
    room = empires.war_room(db, head, NOW9)
    assert room["head_is_ceo"] and room["signing_limit"] == ledger.balance(db, empire["account_id"]) * data.CEO_LIMIT_BPS // 10_000
    assert room["bonus_limit"] == room["worth"] * data.CEO_BONUS_BPS // 10_000
    # It cannot be passed twice.
    with pytest.raises(ranks.RankError, match="passed the CEO rank case|hold the CEO rank"):
        ranks.begin(db, head, "ceo", NOW9)


def test_a_member_who_holds_the_ceo_rank_can_be_voted_in_by_the_empire(db):
    empire, (head, _), partners = founded(db)
    scribe, ledgerman = partners["journalist"][0], partners["accountant"][0]
    with pytest.raises(empires.EmpireError, match="earned the CEO rank"):
        empires.vote_head(db, head, scribe, NOW9)
    db.execute("UPDATE players SET ceo_since = %s WHERE id = %s", (NOW9, scribe))
    first = empires.vote_head(db, ledgerman, scribe, NOW9)
    assert first == {"votes": 1, "members": 3, "needed": 2, "elected": False}
    assert empires.war_room(db, ledgerman, NOW9)["election"]["tally"] == [{"name": "scribe", "votes": 1}]
    # Voting again changes nothing: one member, one vote.
    assert empires.vote_head(db, ledgerman, scribe, NOW9)["votes"] == 1
    won = empires.vote_head(db, scribe, scribe, NOW9)
    assert won["elected"] and empires.war_room(db, scribe, NOW9)["is_head"] and empires.war_room(db, scribe, NOW9)["head_is_ceo"]
    assert not empires.war_room(db, head, NOW9)["is_head"]
    # An outsider has no vote, and an empire the computer runs does not elect.
    outsider, _ = pro(db, "lawyer", "outsider")
    with pytest.raises(empires.EmpireError):
        empires.vote_head(db, outsider, scribe, NOW9)
    empires.apply(db, outsider, computer_empire(db)["id"], NOW9)
    db.execute("UPDATE players SET ceo_since = %s WHERE id = %s", (NOW9, outsider))
    with pytest.raises(empires.EmpireError, match="founded by players"):
        empires.vote_head(db, outsider, outsider, NOW9)


def test_stage_seven_every_module_has_three_kinds_of_work_and_level_twenty_is_a_gate(db):
    """The stage test, from the design: every module on every syllabus map has a solo, an empire and a
    live-event objective; a player at Level 20 cannot advance until the required modules are mastered
    and the rank case is passed."""
    for track in (*TRACKS, "ceo"):
        for m in objectives.modules(track):
            assert {t.setting for t in objectives.TEMPLATES.values() if t.build == track and t.module == m["module"] and t.listed} \
                == {"solo", "empire", "live"}
    player, _ = pro(db, "lawyer", level=20, cash_naira=2_000_000)
    careers.add_experience(db, player, "lawyer", careers.experience_for(30), NOW9)
    assert careers.career(db, player)["level"] == 20                           # any amount of experience: still Level 20
    with pytest.raises(ranks.RankError, match="must be learned"):              # not mastered: the case cannot even be sat
        ranks.begin(db, player, "lawyer", NOW9)
    master(db, player, "lawyer")
    assert careers.career(db, player)["level"] == 20                           # mastered, but the case not passed: still Level 20
    case = ranks.begin(db, player, "lawyer", NOW9)
    assert ranks.hand_in(db, player, case["id"], right_case(db, player, case["id"], NOW9), NOW9)["state"] == "passed"
    assert careers.career(db, player)["level"] == 35                           # the experience held at the gate now counts
