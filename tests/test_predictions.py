"""Prediction markets (owner, 16 November 2026: "build"): YES or NO on things the game itself decides, priced by the
computer's market maker; a winning share pays ₦100.

Promises: the price starts at an even chance and moves with every purchase; buying and selling back never makes money
from nothing; questions are made on the rate, the largest companies' profits and the live events; each is answered from
the game's own books and paid once; a question that comes to nothing hands back what was put in. Loopholes: selling
shares one does not hold; betting past the limit or after the close; the Government Leader betting on the rate; money
made or lost by the books.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from psycopg.rows import dict_row

from simulation import ledger, predictions
from tests.test_builds import pro
from tests.test_careers import NOW9, sound
from tests.test_live_events import BELL, ring

pytestmark = pytest.mark.world("eight")


def _q(db, sql, params=()):
    with db.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def test_the_market_makers_rule_is_fair_and_cannot_be_milked():
    m = {"q_yes": 0, "q_no": 0, "b": 2_000}
    assert predictions.chance_bps(m) == 5_000
    ten = predictions.quote(m, "yes", 10)
    assert 50_000 <= ten <= 50_200                                  # ten shares at about ₦50 each
    after = {"q_yes": 1_000, "q_no": 0, "b": 2_000}
    assert predictions.chance_bps(after) > 6_000
    bought = predictions.quote(m, "yes", 1_000)
    sold = predictions.quote(after, "yes", -1_000)
    assert bought + sold >= 0                                       # buying and selling straight back never pays
    worst = predictions.quote(m, "yes", 200_000)                    # the most the market maker can lose is depth × ln 2
    assert 200_000 * 10_000 - worst <= 2_000 * 0.6932 * 10_000


def test_questions_are_made_bet_on_and_paid_from_the_books(db, monkeypatch):
    me, account = pro(db, "asset_manager", "punter", level=5, cash_naira=10_000_000)
    other, other_account = pro(db, "asset_manager", "other", level=5, cash_naira=10_000_000)
    predictions.tick(db, NOW9)
    kinds = {m["kind"] for m in predictions.view(db, me, NOW9)["markets"]}
    assert {"rate_rise", "profit_beat", "live_kind"} <= kinds
    rate = next(m for m in predictions.view(db, me, NOW9)["markets"] if m["kind"] == "rate_rise")
    cash = ledger.balance(db, account)
    done = predictions.trade(db, me, rate["id"], "yes", 1_000, NOW9)
    assert ledger.balance(db, account) == cash - done["amount"] and done["chance_bps"] > 5_000
    predictions.trade(db, other, rate["id"], "no", 500, NOW9)
    with pytest.raises(predictions.PredictionError, match="hold only"):
        predictions.trade(db, other, rate["id"], "yes", -10, NOW9)
    back = predictions.trade(db, me, rate["id"], "yes", -200, NOW9)
    assert back["amount"] < 0
    monkeypatch.setattr(predictions.data, "PREDICT_MOST_STAKE_NAIRA", 100_000)
    with pytest.raises(predictions.PredictionError, match="at most"):
        predictions.trade(db, me, rate["id"], "yes", 5_000, NOW9)
    # The answer: YES. The holders of YES are paid ₦100 a share, once; NO gets nothing.
    m = _q(db, "SELECT * FROM prediction_markets WHERE id = %s", (rate["id"],))[0]
    before = ledger.balance(db, account), ledger.balance(db, other_account)
    predictions._settle(db, m, True, NOW9 + timedelta(minutes=1))
    assert ledger.balance(db, account) == before[0] + 800 * 10_000 and ledger.balance(db, other_account) == before[1]
    with pytest.raises(predictions.PredictionError, match="closed"):
        predictions.trade(db, me, rate["id"], "yes", 10, NOW9 + timedelta(minutes=2))
    seen = next(x for x in predictions.view(db, me, NOW9 + timedelta(minutes=2))["markets"] if x["id"] == rate["id"])
    assert seen["status"] == "resolved" and seen["outcome"] is True and seen["yours"]["paid_out"] == 800 * 10_000
    sound(db)


def test_a_live_event_question_is_answered_at_the_bell_and_a_void_one_refunded(db, monkeypatch):
    me, account = pro(db, "asset_manager", "punter", level=5, cash_naira=10_000_000)
    predictions.tick(db, NOW9)
    live = next(m for m in predictions.view(db, me, NOW9)["markets"] if m["kind"] == "live_kind")
    predictions.trade(db, me, live["id"], "yes", 300, NOW9)
    ring(db, monkeypatch, "bank_run")
    cash = ledger.balance(db, account)
    predictions.tick(db, BELL + timedelta(minutes=1))
    assert ledger.balance(db, account) == cash + 300 * 10_000
    # The question on the featured share opens for the event's first ten minutes, and closes after.
    fall = next(m for m in predictions.view(db, me, BELL + timedelta(minutes=1))["markets"] if m["kind"] == "live_fall")
    predictions.tick(db, BELL + timedelta(minutes=11))
    with pytest.raises(predictions.PredictionError, match="closed"):
        predictions.trade(db, me, fall["id"], "no", 10, BELL + timedelta(minutes=11))
    # A question that comes to nothing hands back what was put in.
    nxt = next(m for m in predictions.view(db, me, BELL + timedelta(minutes=11))["markets"] if m["kind"] == "live_kind" and m["status"] == "open")
    paid = predictions.trade(db, me, nxt["id"], "no", 100, BELL + timedelta(minutes=12))["amount"]
    m = _q(db, "SELECT * FROM prediction_markets WHERE id = %s", (nxt["id"],))[0]
    cash = ledger.balance(db, account)
    predictions._settle(db, m, "void", BELL + timedelta(minutes=13))
    assert ledger.balance(db, account) == cash + paid
    sound(db)


def test_the_government_leader_may_not_bet_on_the_rate(db, monkeypatch):
    from simulation import government
    leader, _ = pro(db, "asset_manager", "leader", level=5, cash_naira=1_000_000)
    monkeypatch.setattr(government, "leader", lambda conn, year: {"leader_id": leader})
    predictions.tick(db, NOW9)
    rate = next(m for m in predictions.view(db, leader, NOW9)["markets"] if m["kind"] == "rate_rise")
    assert rate["barred"]
    with pytest.raises(predictions.PredictionError, match="Government Leader"):
        predictions.trade(db, leader, rate["id"], "yes", 10, NOW9)
