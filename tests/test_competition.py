"""Competition, part 1: contested mandates and ranked work, each promise and each loophole a test.

Promises: a company selling shares puts the sale out to pitch; it chooses the pitch best for it, from the record; the
winner is paid its fee on what was raised and earns league points; every forecast is scored against what happened. Each
quarter each build forecasts one figure about one company; the closest are ranked and their empires earn points.

Loopholes: a beginner (to Level 5) is not thrown in; a pitch or forecast is sealed (others cannot see it, and nobody can
change it); one pitch for each empire; one forecast each; nothing after the deadline; a second account in the same
empire buys no extra points; the company never chooses by who asked first.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from psycopg.rows import dict_row

from simulation import competition, corporate, empires, ledger, quarters
from simulation import world_data as data
from simulation.money import BPS
from tests.conftest import after_quarters
from tests.test_builds import pro
from tests.test_careers import NOW9, sound
from tests.test_empires import computer_empire

pytestmark = pytest.mark.world("eight")

P = 9


def _one(db, sql, params=()):
    with db.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(sql, params).fetchall()
    return rows[0] if rows else None


def _rows(db, sql, params=()):
    with db.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def member(db, build, name, empire_index, level=10):
    player, account = pro(db, build, name, level=min(level, 19), cash_naira=1_000_000)
    if level > 19:                                    # past the rank cases, as test_derivatives' traders are
        from simulation import careers
        db.execute("UPDATE careers SET rank = %s, experience = %s WHERE player_id = %s AND build = %s",
                   (level // 20, careers.experience_for(level), player, build))
    assert empires.apply(db, player, computer_empire(db, empire_index)["id"], NOW9)["status"] == "accepted"
    return player


def a_sale(db, ticker="IDC"):
    """A company announces a small sale of new shares as the eighth quarter closed; it settles when the ninth closes."""
    company = _one(db, "SELECT * FROM companies WHERE ticker = %s", (ticker,))
    held = ledger.amount_in_existence(db, company["share_asset"])
    price = _one(db, "SELECT coalesce(last_price, reference_price) AS p FROM market_instruments WHERE company_id = %s",
                 (company["id"],))["p"]
    offer_id = corporate.announce_offer(db, company, kind="public", price=price * 9 // 10, shares=max(held // 200, 1), period=8,
                                        reason="It wants money to grow.", now=NOW9)
    competition.open_mandates(db, 8, NOW9)
    return _one(db, "SELECT * FROM mandates WHERE offer_id = %s", (offer_id,)), company


def test_a_sale_of_shares_is_put_out_to_pitch_and_the_company_chooses_the_best_pitch_for_it(db):
    mandate, company = a_sale(db)
    assert mandate["status"] == "open" and mandate["period"] == P
    cheap = member(db, "investment_banker", "cheap", 0, level=10)
    dear = member(db, "investment_banker", "dear", 1, level=10)
    competition.pitch(db, cheap, mandate["id"], 100, 8000, NOW9)
    competition.pitch(db, dear, mandate["id"], 300, 5000, NOW9)
    # Sealed: each empire sees its own pitch and nobody else's.
    seen = next(m for m in competition.view(db, dear, NOW9)["mandates"] if m["id"] == mandate["id"])
    assert seen["ours"]["fee_bps"] == 300 and seen["winner"] is None and seen["pitches"] == 2
    quarters.close_due_quarters(db, after_quarters(9))
    done = _one(db, "SELECT * FROM mandates WHERE id = %s", (mandate["id"],))
    assert done["status"] == "settled"
    winner = _one(db, "SELECT * FROM mandate_pitches WHERE id = %s", (done["winner_id"],))
    assert winner["player_id"] == cheap                      # same trust, lower fee
    offer = _one(db, "SELECT * FROM share_offers WHERE id = %s", (mandate["offer_id"],))
    assert done["fee_paid"] == (offer["raised"] or 0) * 100 // BPS
    taken = (offer["shares_sold"] or 0) * BPS // offer["shares"]
    assert done["taken_up_bps"] == taken
    assert all(p["error_bps"] == abs(p["take_up_bps"] - taken)
               for p in _rows(db, "SELECT * FROM mandate_pitches WHERE mandate_id = %s", (mandate["id"],)))
    points = _one(db, "SELECT points FROM league_points WHERE reference = %s", (f"mandate:{mandate['id']}",))
    assert points["points"] == data.LEAGUE_POINTS["mandate"]
    sound(db)


def test_a_banker_the_company_trusts_more_can_win_at_a_higher_fee(db):
    mandate, _ = a_sale(db)
    senior = member(db, "investment_banker", "senior", 0, level=60)
    junior = member(db, "investment_banker", "junior", 1, level=6)
    assert competition.trust_bps(db, senior, empires.seat_of(db, senior)["empire_id"]) == 60 * data.MANDATE_TRUST_PER_LEVEL_BPS
    competition.pitch(db, senior, mandate["id"], 120, 9000, NOW9)        # 1.2% from someone it trusts 30%: 0.84%
    competition.pitch(db, junior, mandate["id"], 100, 9000, NOW9)        # 1.0% from someone it trusts 3%: 0.97%
    competition.award(db, P, after_quarters(9))
    winner = _one(db, "SELECT p.player_id FROM mandates m JOIN mandate_pitches p ON p.id = m.winner_id WHERE m.id = %s",
                  (mandate["id"],))
    assert winner["player_id"] == senior


def test_one_sealed_pitch_for_each_empire_from_its_banker_or_head_and_only_before_the_deadline(db):
    mandate, _ = a_sale(db)
    banker = member(db, "investment_banker", "banker", 0)
    colleague = member(db, "investment_banker", "colleague", 0)
    analyst = member(db, "asset_manager", "analyst", 1)
    beginner = member(db, "investment_banker", "beginner", 2, level=5)
    competition.pitch(db, banker, mandate["id"], 100, 7000, NOW9)
    with pytest.raises(competition.CompetitionError, match="already pitched"):
        competition.pitch(db, colleague, mandate["id"], 50, 7000, NOW9)          # nobody pitches against their own empire
    with pytest.raises(competition.CompetitionError, match="Investment Banker"):
        competition.pitch(db, analyst, mandate["id"], 100, 7000, NOW9)
    with pytest.raises(competition.CompetitionError, match="marked alone"):
        competition.pitch(db, beginner, mandate["id"], 100, 7000, NOW9)
    late = member(db, "investment_banker", "late", 3)
    with pytest.raises(competition.CompetitionError, match="Pitches close"):
        competition.pitch(db, late, mandate["id"], 100, 7000, NOW9 + timedelta(days=4))
    with pytest.raises(competition.CompetitionError, match="between"):
        competition.pitch(db, late, mandate["id"], 1, 7000, NOW9)                # below the least fee
    with pytest.raises(Exception, match="sealed"):
        db.execute("UPDATE mandate_pitches SET fee_bps = 30 WHERE mandate_id = %s", (mandate["id"],))


def test_a_tie_is_decided_by_lot_never_by_who_pitched_first(db):
    mandate, _ = a_sale(db)
    first = member(db, "investment_banker", "first", 0)
    second = member(db, "investment_banker", "second", 1)
    competition.pitch(db, first, mandate["id"], 100, 7000, NOW9)
    competition.pitch(db, second, mandate["id"], 100, 7000, NOW9 + timedelta(hours=1))
    expected = min(_rows(db, "SELECT * FROM mandate_pitches WHERE mandate_id = %s", (mandate["id"],)),
                   key=lambda p: competition._hash("mandate", mandate["id"], p["empire_id"]))
    competition.award(db, P, after_quarters(9))
    assert _one(db, "SELECT winner_id FROM mandates WHERE id = %s", (mandate["id"],))["winner_id"] == expected["id"]


def _contest(db, build="asset_manager"):
    competition.open_contests(db, 8, "a-test-seed", NOW9)
    return _one(db, "SELECT * FROM contests WHERE period = %s AND build = %s", (P, build))


def test_each_build_forecasts_one_figure_and_the_closest_are_ranked_when_the_quarter_closes(db):
    c = _contest(db)
    assert {r["build"] for r in _rows(db, "SELECT build FROM contests WHERE period = %s", (P,))} == set(competition.MEASURES)
    price = _one(db, "SELECT coalesce(last_price, reference_price) AS p FROM market_instruments WHERE company_id = %s",
                 (c["company_id"],))["p"]
    near = member(db, "asset_manager", "near", 0)
    far = member(db, "asset_manager", "far", 1)
    twin = member(db, "asset_manager", "twin", 0)                 # a second account in near's empire
    competition.enter(db, near, c["id"], price, NOW9)
    competition.enter(db, far, c["id"], price * 3, NOW9)
    competition.enter(db, twin, c["id"], price * 101 // 100, NOW9)
    # Sealed: before the close a player sees only their own forecast.
    seen = next(x for x in competition.view(db, far, NOW9)["contests"] if x["id"] == c["id"])
    assert seen["entry"]["guess"] == price * 3 and seen["top"] == [] and seen["truth"] is None
    quarters.close_due_quarters(db, after_quarters(9))
    judged = _one(db, "SELECT * FROM contests WHERE id = %s", (c["id"],))
    assert judged["status"] == "judged" and judged["truth"] > 0
    rows = {r["player_id"]: r for r in _rows(db, "SELECT * FROM contest_entries WHERE contest_id = %s", (c["id"],))}
    assert all(r["error_bps"] == abs(r["guess"] - judged["truth"]) * BPS // judged["truth"] for r in rows.values())
    # Only the best entry of each empire earns points: the twin earns its empire nothing more.
    best_of_zero = min((rows[near], rows[twin]), key=lambda r: r["error_bps"])
    other = rows[twin] if best_of_zero is rows[near] else rows[near]
    assert other["points"] == 0
    if best_of_zero["error_bps"] <= data.CONTEST_MOST_ERROR_BPS:
        assert best_of_zero["points"] == data.CONTEST_POINTS[best_of_zero["place"]]
    assert rows[far]["points"] == 0                                # a miss of more than a quarter earns nothing
    after = next(x for x in competition.view(db, far, after_quarters(9) + timedelta(hours=2))["contests"] if x["id"] == c["id"])
    assert after["truth"] == judged["truth"] and len(after["top"]) == 3
    sound(db)


def test_one_sealed_forecast_each_for_your_own_build_before_the_deadline(db):
    c = _contest(db)
    me = member(db, "asset_manager", "forecaster", 0)
    banker = member(db, "investment_banker", "otherbuild", 1)
    beginner = member(db, "asset_manager", "newcomer", 2, level=5)
    competition.enter(db, me, c["id"], 1_000, NOW9)
    with pytest.raises(competition.CompetitionError, match="sealed"):
        competition.enter(db, me, c["id"], 2_000, NOW9)
    with pytest.raises(competition.CompetitionError, match="another build"):
        competition.enter(db, banker, c["id"], 1_000, NOW9)
    with pytest.raises(competition.CompetitionError, match="marked alone"):
        competition.enter(db, beginner, c["id"], 1_000, NOW9)
    late = member(db, "asset_manager", "latecomer", 3)
    with pytest.raises(competition.CompetitionError, match="Forecasts close"):
        competition.enter(db, late, c["id"], 1_000, NOW9 + timedelta(days=3))
    with pytest.raises(Exception, match="sealed"):
        db.execute("UPDATE contest_entries SET guess = 5 WHERE contest_id = %s", (c["id"],))


def test_points_need_two_empires_taking_part(db):
    c = _contest(db, "risk_manager")
    alone = member(db, "risk_manager", "alone", 0)
    truth = competition._truth(db, {**c, "period": 8})            # last quarter's profit: a fair guess
    competition.enter(db, alone, c["id"], truth or 1, NOW9)
    quarters.close_due_quarters(db, after_quarters(9))
    assert _one(db, "SELECT points FROM contest_entries WHERE contest_id = %s", (c["id"],))["points"] == 0


def test_the_page_never_takes_a_figure_it_should_not(db):
    from pydantic import ValidationError
    from server.competition_routes import ForecastRequest, PitchRequest
    with pytest.raises(ValidationError):
        PitchRequest(mandate_id=1, fee_bps=100, take_up_bps=5000, empire_id=3)
    with pytest.raises(ValidationError):
        PitchRequest(mandate_id=1, fee_bps=100, take_up_bps=20_000)
    with pytest.raises(ValidationError):
        ForecastRequest(contest_id=1, guess_kobo=100, points=6)
