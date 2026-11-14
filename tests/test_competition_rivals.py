"""Competition, part 2: work aimed at rival empires, and the league as the scoreboard. A test for each promise and each
loophole.

Promises: an empire's Asset Manager calls a rival's company overvalued, its Risk Manager calls a rival's bank weak; the
record judges each call, right or wrong, and the league moves both ways. A company facing a hostile bid puts its defence
out to pitch; the defender is paid only if the bid fails. The league shows what earned each empire its points.

Loopholes: no call on your own empire's company, or on a company no rival holds enough of; no call by the wrong build or
a beginner; one open call a company and two at once; a call cannot be changed; selling the shares yourself (or a
friendly "rival" selling them) to make the fall voids the call; nobody defends a company against their own empire's bid.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from psycopg.rows import dict_row

from simulation import competition, empires, ledger
from simulation import world_data as data
from simulation.money import BPS
from tests.test_careers import NOW9, sound
from tests.test_competition import member
from tests.test_empires import computer_empire
from tests.test_market import place
from tests.test_objectives import give_cash

pytestmark = pytest.mark.world("eight")

P = 9


def _one(db, sql, params=()):
    with db.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(sql, params).fetchall()
    return rows[0] if rows else None


def company(db, ticker):
    return _one(db, "SELECT * FROM companies WHERE ticker = %s", (ticker,))


def stake(db, empire, ticker, bps=600):
    """Give an empire a stake of `bps` in a company, from the public's shares."""
    c = company(db, ticker)
    issued = _one(db, "SELECT sum(balance) AS s FROM ledger_balances WHERE asset = %s AND balance > 0", (c["share_asset"],))["s"]
    ledger.transfer(db, payer=ledger.account_id(db, ledger.INVESTORS_PUBLIC), receiver=empire["account_id"],
                    amount=issued * bps // (BPS - bps) + 1, asset=c["share_asset"], kind="test_shares", memo="Test: a stake")
    return c


def points(db, empire_id, prefix):
    return _one(db, "SELECT coalesce(sum(points), 0)::int AS p FROM league_points WHERE empire_id = %s AND reference LIKE %s",
                (empire_id, prefix + "%"))["p"]


def test_an_overvalued_call_on_a_rivals_company_is_judged_by_the_price_and_moves_the_league_both_ways(db):
    rival = computer_empire(db, 1)
    target = stake(db, rival, "IDC")
    caller = member(db, "asset_manager", "caller", 0)
    mine = empires.seat_of(db, caller)["empire_id"]
    listed = competition.call_targets(db, mine, "overvalued")
    assert any(t["ticker"] == "IDC" and t["rival_id"] == rival["id"] for t in listed)
    made = competition.make_call(db, caller, "overvalued", target["id"], NOW9)
    call = _one(db, "SELECT * FROM rival_calls WHERE id = %s", (made["call_id"],))
    assert call["ends_period"] == P + data.CALL_QUARTERS - 1 and call["from_price"] > 0
    # Public at once: the rival sees it coming.
    seen = competition.view(db, member(db, "asset_manager", "watcher", 1), NOW9)["calls"]
    assert any(c["id"] == call["id"] and c["against_us"] for c in seen)
    db.execute("UPDATE market_instruments SET last_price = %s WHERE company_id = %s", (call["from_price"] * 8 // 10, target["id"]))
    assert competition.judge_calls(db, call["ends_period"], NOW9) == 1
    assert _one(db, "SELECT status FROM rival_calls WHERE id = %s", (call["id"],))["status"] == "right"
    assert points(db, mine, "call:") == data.LEAGUE_POINTS["call_right"]
    assert points(db, rival["id"], "call_exposed:") == -data.LEAGUE_POINTS["call_exposed"]
    board = {b["empire"]: b for b in competition.scoreboard(db, NOW9)}
    assert board[rival["name"]]["call_exposed"] == -data.LEAGUE_POINTS["call_exposed"]
    sound(db)


def test_a_wrong_call_costs_the_caller(db):
    rival = computer_empire(db, 1)
    target = stake(db, rival, "IDC")
    caller = member(db, "asset_manager", "wrong", 0)
    made = competition.make_call(db, caller, "overvalued", target["id"], NOW9)
    competition.judge_calls(db, P + data.CALL_QUARTERS - 1, NOW9)
    assert _one(db, "SELECT status FROM rival_calls WHERE id = %s", (made["call_id"],))["status"] == "wrong"
    assert points(db, empires.seat_of(db, caller)["empire_id"], "call:") == -data.LEAGUE_POINTS["call_wrong"]
    assert points(db, rival["id"], "call_exposed:") == 0


def test_a_weak_bank_call_is_judged_by_the_banks_rating(db):
    rival = computer_empire(db, 1)
    bank = stake(db, rival, "IKB")
    risk = member(db, "risk_manager", "risk", 0)
    with pytest.raises(competition.CompetitionError, match="Asset Manager"):
        competition.make_call(db, risk, "overvalued", bank["id"], NOW9)                 # the wrong build for this call
    other = stake(db, rival, "IDC")
    with pytest.raises(competition.CompetitionError, match="must be a bank"):
        competition.make_call(db, risk, "weak_bank", other["id"], NOW9)
    made = competition.make_call(db, risk, "weak_bank", bank["id"], NOW9)
    call = _one(db, "SELECT * FROM rival_calls WHERE id = %s", (made["call_id"],))
    assert call["from_rating"] == competition._rating(db, bank["id"])
    # A later filing with a lower rating makes the call right.
    latest = _one(db, "SELECT * FROM company_reports WHERE company_id = %s ORDER BY period DESC, version DESC LIMIT 1", (bank["id"],))
    lower = competition.RATINGS[competition.RATINGS.index(latest["credit_rating"]) + 1]
    db.execute("INSERT INTO company_reports (company_id, period, version, figures, credit_rating, rating_reasons, filed_by)"
               " VALUES (%s, %s, 1, %s, %s, '[]', 'test')", (bank["id"], latest["period"] + 1,
                                                              __import__("json").dumps(latest["figures"]), lower))
    competition.judge_calls(db, call["ends_period"], NOW9)
    assert _one(db, "SELECT status FROM rival_calls WHERE id = %s", (call["id"],))["status"] == "right"


def test_who_may_call_on_what_and_how_often(db):
    rival = computer_empire(db, 1)
    caller = member(db, "asset_manager", "busy", 0)
    mine = empires.seat_of(db, caller)["empire_id"]
    own = stake(db, computer_empire(db, 0), "GGM", bps=900)                          # its own empire holds most of this one
    assert not any(t["ticker"] == "GGM" for t in competition.call_targets(db, mine, "overvalued"))
    with pytest.raises(competition.CompetitionError, match="rival empire holds"):
        competition.make_call(db, caller, "overvalued", own["id"], NOW9)
    beginner = member(db, "asset_manager", "fresh", 2, level=5)
    a, b, c = stake(db, rival, "IDC"), stake(db, rival, "EKC"), stake(db, rival, "DFL")
    with pytest.raises(competition.CompetitionError, match="marked alone"):
        competition.make_call(db, beginner, "overvalued", a["id"], NOW9)
    competition.make_call(db, caller, "overvalued", a["id"], NOW9)
    with pytest.raises(competition.CompetitionError, match="already has a call open"):
        competition.make_call(db, caller, "overvalued", a["id"], NOW9)
    competition.make_call(db, caller, "overvalued", b["id"], NOW9)
    with pytest.raises(competition.CompetitionError, match="calls open at once"):
        competition.make_call(db, caller, "overvalued", c["id"], NOW9)
    with pytest.raises(Exception, match="cannot be changed"):
        db.execute("UPDATE rival_calls SET from_price = from_price * 2 WHERE empire_id = %s", (mine,))


def test_selling_the_shares_to_make_the_fall_voids_the_call(db):
    rival = computer_empire(db, 1)
    target = stake(db, rival, "IDC")
    caller = member(db, "asset_manager", "dumper", 0)
    made = competition.make_call(db, caller, "overvalued", target["id"], NOW9)
    # The "rival" sells some of its stake while the call is open (a friendly rival handing over the points).
    buyer = ledger.account_id(db, ledger.INVESTORS_PUBLIC)
    price = _one(db, "SELECT from_price FROM rival_calls WHERE id = %s", (made["call_id"],))["from_price"]
    give_cash(db, buyer, 10_000_000)
    place(db, rival["account_id"], "sell", 100, price * 8 // 10, now=NOW9 + timedelta(hours=1), ticker="IDC")
    place(db, buyer, "buy", 100, price * 8 // 10, now=NOW9 + timedelta(hours=1), ticker="IDC")
    db.execute("UPDATE market_instruments SET last_price = %s WHERE company_id = %s", (price * 8 // 10, target["id"]))
    competition.judge_calls(db, P + data.CALL_QUARTERS - 1, NOW9 + timedelta(days=1))
    row = _one(db, "SELECT status, outcome FROM rival_calls WHERE id = %s", (made["call_id"],))
    traded = _one(db, "SELECT count(*) AS n FROM market_trades WHERE seller_account_id = %s", (rival["account_id"],))["n"]
    if traded:
        assert row["status"] == "void" and "rival empire itself" in row["outcome"]
        assert points(db, empires.seat_of(db, caller)["empire_id"], "call:") == 0


def a_hostile_bid(db, bidder_ticker="EKC", target_ticker="IDC"):
    bidder, target = company(db, bidder_ticker), company(db, target_ticker)
    price = _one(db, "SELECT coalesce(last_price, reference_price) AS p FROM market_instruments WHERE company_id = %s",
                 (target["id"],))["p"] * 13 // 10
    bid = _one(db, "INSERT INTO takeovers (bidder_company_id, target_company_id, price, shares_sought, hostile, premium_bps, reserved,"
                   " opens_period, closes_period) VALUES (%s, %s, %s, 1000000, true, 3000, 0, 8, 9) RETURNING id",
               (bidder["id"], target["id"], price))
    competition.open_mandates(db, 8, NOW9)
    return _one(db, "SELECT * FROM mandates WHERE takeover_id = %s", (bid["id"],)), bid, bidder, target


def test_a_company_facing_a_hostile_bid_puts_its_defence_out_to_pitch_and_pays_only_if_the_bid_fails(db):
    mandate, bid, bidder, target = a_hostile_bid(db)
    assert mandate["kind"] == "defence" and mandate["period"] == P
    defender = member(db, "investment_banker", "defender", 0)
    competition.pitch(db, defender, mandate["id"], 200, 3000, NOW9)
    competition.award(db, P, NOW9)
    db.execute("UPDATE takeovers SET status = 'failed', accepted = 250000 WHERE id = %s", (bid["id"],))
    give_cash(db, target["account_id"], 10_000_000)
    before = ledger.balance(db, empires._empire(db, empires.seat_of(db, defender)["empire_id"])["account_id"])
    competition.settle(db, P, NOW9)
    done = _one(db, "SELECT * FROM mandates WHERE id = %s", (mandate["id"],))
    assert done["status"] == "settled" and done["taken_up_bps"] == 2500
    bid_price = _one(db, "SELECT price FROM takeovers WHERE id = %s", (bid["id"],))["price"]
    assert done["fee_paid"] == bid_price * 1_000_000 * 200 // BPS > 0           # on what the bid was worth
    assert ledger.balance(db, empires._empire(db, empires.seat_of(db, defender)["empire_id"])["account_id"]) == before + done["fee_paid"]
    assert points(db, empires.seat_of(db, defender)["empire_id"], "defence:") == data.LEAGUE_POINTS["defence"]
    assert _one(db, "SELECT error_bps FROM mandate_pitches WHERE mandate_id = %s", (mandate["id"],))["error_bps"] == 500
    sound(db)


def test_a_bid_that_succeeds_pays_the_defender_nothing(db):
    mandate, bid, bidder, target = a_hostile_bid(db)
    defender = member(db, "investment_banker", "unlucky", 0)
    competition.pitch(db, defender, mandate["id"], 200, 3000, NOW9)
    competition.award(db, P, NOW9)
    db.execute("UPDATE takeovers SET status = 'won', accepted = 900000 WHERE id = %s", (bid["id"],))
    competition.settle(db, P, NOW9)
    done = _one(db, "SELECT * FROM mandates WHERE id = %s", (mandate["id"],))
    assert done["fee_paid"] == 0 and "no fee" in done["words"]
    assert points(db, empires.seat_of(db, defender)["empire_id"], "defence:") == 0


def test_nobody_defends_a_company_against_their_own_empires_bid(db):
    mandate, bid, bidder, target = a_hostile_bid(db)
    behind = computer_empire(db, 0)
    stake(db, behind, "EKC", bps=900)
    banker = member(db, "investment_banker", "insider", 0)
    with pytest.raises(competition.CompetitionError, match="own bid"):
        competition.pitch(db, banker, mandate["id"], 200, 3000, NOW9)
