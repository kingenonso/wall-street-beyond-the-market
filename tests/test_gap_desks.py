"""The gap stage, Part 1: the Investment Banker's deal protection and the Accountant's quarterly valuation of positions."""

from __future__ import annotations

import pytest
from psycopg.rows import dict_row

from simulation import derivatives, empires, firm, lending_empire
from simulation.empires import EmpireError
from tests.test_careers import sound
from tests.test_deals import LATER
from tests.test_deals_loopholes import ready as deal_ready
from tests.test_derivatives import ready, series
from tests.test_firm import duty_of, right
from tests.test_lending import signed

pytestmark = pytest.mark.world("eight")


def _one(db, sql, params=()):
    with db.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(sql, params).fetchall()
    return rows[0] if rows else None


def test_the_investment_banker_buys_protection_only_while_a_deal_is_open(db):
    empire, team, sale, file_id = deal_ready(db)
    banker = ready(db, team["investment_banker"])
    ready(db, team["risk_manager"])
    signed(db, team, 0, 0, LATER, derivatives_naira=500_000_000)
    put = series(db, "put", "BSX50", nearest=derivatives.index_now(db, LATER))
    future = series(db, "future", "BSX50")
    with pytest.raises(EmpireError, match="options bought"):
        lending_empire.trade(db, banker, future["id"], "long", 1, LATER)
    with pytest.raises(EmpireError, match="options bought"):
        lending_empire.trade(db, banker, put["id"], "short", 1, LATER)
    done = lending_empire.trade(db, banker, put["id"], "long", 2, LATER)
    p = _one(db, "SELECT * FROM derivative_positions WHERE id = %s", (done["position_id"],))
    assert p["account"] == empire["account_id"] and "protection for the deal" in p["purpose"]
    # The deal is dropped: the banker can close what was bought, but buys no more.
    db.execute("UPDATE deal_files SET status = 'dropped' WHERE id = %s", (file_id,))
    with pytest.raises(EmpireError, match="deal open"):
        lending_empire.trade(db, banker, put["id"], "long", 1, LATER)
    lending_empire.close_derivative(db, banker, done["position_id"], LATER)
    assert derivatives.check_books(db) == []
    sound(db)


def test_the_accountant_values_the_empires_positions_and_is_marked_against_the_truth(db):
    empire, team, sale, file_id = deal_ready(db)
    am = ready(db, team["head"])
    signed(db, team, 0, 0, LATER, derivatives_naira=500_000_000)
    put = series(db, "put", "BSX50", nearest=derivatives.index_now(db, LATER))
    future = series(db, "future", "BSX50")
    lending_empire.trade(db, am, put["id"], "long", 3, LATER)
    lending_empire.trade(db, am, future["id"], "short", 1, LATER)
    db.execute("DELETE FROM desk_duties WHERE empire_id = %s AND code = 'ac_positions'", (empire["id"],))
    duty = duty_of(db, empire["id"], "ac_positions")
    assert duty is not None
    opened = firm.open_duty(db, team["accountant"], duty["id"], LATER)
    assert "_truth" not in opened["terms"] and opened["terms"]["asks"][0]["key"] == "value"
    truth = right(db, duty["id"])
    assert truth["value"] == derivatives.held_value(db, empire["account_id"], LATER)
    with pytest.raises(EmpireError):
        firm.open_duty(db, team["investment_banker"], duty["id"], LATER)                # another desk's duty
    done = firm.hand_in(db, team["accountant"], duty["id"], truth, LATER)
    assert done["score"] == 100
    _ = empires
    sound(db)
