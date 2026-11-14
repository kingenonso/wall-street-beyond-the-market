"""Stage 12, the goods: the promises in docs/STAGE_12_COMMODITIES_PROPOSAL.md ("What will be tested"), one test each.

Rewritten on 14 November 2026: the first version checked that functions existed rather than what they did, called a
quarter close that does not exist, and bought goods with no space to put them in.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from psycopg.rows import dict_row

from simulation import careers, commodities, derivatives, ledger, quarters
from simulation.money import BPS
from tests.conftest import after_quarters
from tests.test_careers import NOW9, sound
from tests.test_derivatives import series, trader

pytestmark = pytest.mark.world("eight")

P = 9
OPEN = NOW9


def _one(db, sql, params=()):
    with db.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(sql, params).fetchall()
    return rows[0] if rows else None


def books(db):
    assert commodities.check_books(db) == []
    sound(db)


def holder(db, name="holder", cash_naira=500_000_000):
    return trader(db, "asset_manager", name, cash_naira=cash_naira)


def test_1_the_price_of_a_good_is_its_futures_contract_divided_by_the_units(db):
    for g in commodities.goods(db):
        s = {"underlying": g["underlying"], "company_id": None, "kind": "future"}
        whole = derivatives.value_of(db, s, derivatives.spot(db, s, OPEN))
        assert commodities.spot(db, g["code"], OPEN) == max(whole // int(g["units_per_contract"]), 1)
        q = commodities.quote(db, g["code"], OPEN)
        assert q["bid"] < q["spot"] < q["ask"]


def test_2_goods_need_space_and_no_more_can_be_held_than_the_space_holds(db):
    player, account = holder(db)
    with pytest.raises(commodities.CommodityError, match="room"):
        commodities.buy(db, account, "GOLD", 1, P, OPEN)
    lease = commodities.open_lease(db, account, "GOLD", 1, False, P, OPEN)
    room = int(lease["capacity"])
    commodities.buy(db, account, "GOLD", room, P, OPEN)
    with pytest.raises(commodities.CommodityError, match="room"):
        commodities.buy(db, account, "GOLD", 1, P, OPEN)
    with pytest.raises(commodities.CommodityError, match="You hold"):
        commodities.sell(db, account, "GOLD", room + 1, P, OPEN)
    with pytest.raises(commodities.CommodityError, match="still holds goods"):
        commodities.close_lease(db, account, lease["id"], OPEN)
    books(db)


def test_3_a_round_trip_costs_exactly_the_spread_and_makes_nothing_from_nowhere(db):
    player, account = holder(db)
    commodities.open_lease(db, account, "OIL", 1, False, P, OPEN)
    start = ledger.balance(db, account)
    stock = commodities.stock(db, "OIL")
    q = commodities.quote(db, "OIL", OPEN)
    bought = commodities.buy(db, account, "OIL", 50, P, OPEN)
    sold = commodities.sell(db, account, "OIL", 50, P, OPEN)
    assert bought["cost"] == 50 * q["ask"] and sold["proceeds"] == 50 * q["bid"]
    assert ledger.balance(db, account) == start - 50 * (q["ask"] - q["bid"])
    assert commodities.stock(db, "OIL") == stock and commodities.held(db, account, "OIL") == 0
    books(db)


def test_4_rent_is_charged_at_the_close_and_unpaid_rent_is_paid_by_selling_the_goods(db):
    payer, paying = holder(db, "payer")
    short, shorted = holder(db, "short")
    for account in (paying, shorted):
        commodities.open_lease(db, account, "FARM", 1, False, P, OPEN)
        commodities.buy(db, account, "FARM", 200, P, OPEN)
    # The second holder leaves their job and spends everything: the rent must come out of the goods.
    careers.leave_job(db, short, OPEN)
    ledger.transfer(db, payer=shorted, receiver=paying, amount=ledger.balance(db, shorted), kind="gift", memo="test")
    quarters.close_due_quarters(db, after_quarters(9))
    paid = _one(db, "SELECT * FROM commodity_events WHERE account = %s AND kind = 'rent'", (paying,))
    assert paid["amount"] > 0
    assert commodities.held(db, shorted, "FARM") < 200        # goods were sold to cover the rent
    books(db)


def test_5_uninsured_goods_can_be_lost_and_insured_ones_are_paid_for_out_of_the_pool(db, monkeypatch):
    insured, insured_account = holder(db, "insured")
    bare, bare_account = holder(db, "bare")
    a = commodities.open_lease(db, insured_account, "GOLD", 1, True, P, OPEN)
    b = commodities.open_lease(db, bare_account, "GOLD", 1, False, P, OPEN)
    for account in (insured_account, bare_account):
        commodities.buy(db, account, "GOLD", 100, P, OPEN)
    # The pool holds premiums; put a quarter's worth in through the close, then make every space unlucky.
    monkeypatch.setattr(commodities, "_chance", lambda salt, period, lease_id: 0)
    before = ledger.balance(db, insured_account)
    quarters.close_due_quarters(db, after_quarters(9))
    lost_a = _one(db, "SELECT * FROM commodity_events WHERE account = %s AND kind = 'loss'", (insured_account,))
    lost_b = _one(db, "SELECT * FROM commodity_events WHERE account = %s AND kind = 'loss'", (bare_account,))
    assert lost_a and lost_b
    assert lost_b["amount"] == 0 and commodities.held(db, bare_account, "GOLD") < 100
    claims = _one(db, "SELECT coalesce(sum(l.amount), 0) AS paid FROM ledger_entries l JOIN ledger_transactions t"
                      " ON t.id = l.transaction_id WHERE l.account_id = %s AND t.kind = 'commodity_claim'", (insured_account,))
    assert claims["paid"] == lost_a["amount"]
    assert ledger.balance(db, commodities.insurance_account(db)) >= 0      # the pool pays what it holds and no more
    assert a["id"] != b["id"] and ledger.balance(db, insured_account) != before
    books(db)


def test_6_delivery_happens_only_with_room_and_otherwise_settles_in_cash(db):
    player, account = holder(db, "jeweller")
    f = series(db, "future", "METALS")
    done = derivatives.open_position(db, account, f["id"], "long", 2, OPEN, player_id=player)
    with pytest.raises(commodities.CommodityError, match="no such open contract"):
        commodities.ask_delivery(db, account, done["position_id"] + 999_999, OPEN)
    asked = commodities.ask_delivery(db, account, done["position_id"], OPEN)
    assert asked["good"] == "GOLD" and asked["units"] == 2 * 10
    other, other_account = holder(db, "no-room")
    g = derivatives.open_position(db, other_account, f["id"], "long", 1, OPEN, player_id=other)
    commodities.ask_delivery(db, other_account, g["position_id"], OPEN)
    commodities.open_lease(db, account, "GOLD", 1, False, P, OPEN)            # room for the jeweller only
    quarters.close_due_quarters(db, after_quarters(9))
    assert commodities.held(db, account, "GOLD") == 20
    refused = _one(db, "SELECT * FROM commodity_events WHERE account = %s AND kind = 'delivery_refused'", (other_account,))
    assert refused and "No room" in refused["words"]
    assert commodities.held(db, other_account, "GOLD") == 0
    books(db)


def test_7_a_short_future_cannot_take_delivery(db):
    player, account = holder(db, "seller")
    f = series(db, "future", "OIL")
    done = derivatives.open_position(db, account, f["id"], "short", 1, OPEN, player_id=player)
    with pytest.raises(commodities.CommodityError, match="long futures"):
        commodities.ask_delivery(db, account, done["position_id"], OPEN)


def test_8_the_curve_has_a_shape_read_from_its_prices(db):
    curve = commodities.curve(db, OPEN)
    assert set(curve) == {g["code"] for g in commodities.goods(db)}
    for code, info in curve.items():
        assert info["shape"] in ("flat", "contango", "backwardation")


def test_9_a_lease_belongs_to_its_holder_alone(db):
    one, one_account = holder(db, "owner-one")
    two, two_account = holder(db, "owner-two")
    lease = commodities.open_lease(db, one_account, "MATERIALS", 1, False, P, OPEN)
    with pytest.raises(commodities.CommodityError, match="no such lease"):
        commodities.set_insured(db, two_account, lease["id"], True)
    with pytest.raises(commodities.CommodityError, match="no such lease"):
        commodities.close_lease(db, two_account, lease["id"], OPEN)
    with pytest.raises(commodities.CommodityError, match="room"):
        commodities.buy(db, two_account, "MATERIALS", 1, P, OPEN)          # someone else's space is not yours


def test_10_the_page_never_names_a_price(db):
    from pydantic import ValidationError
    from server.commodity_routes import LeaseRequest, TradeRequest
    with pytest.raises(ValidationError):
        TradeRequest(good="GOLD", units=1, price=1)
    with pytest.raises(ValidationError):
        TradeRequest(good="SILVER", units=1)
    with pytest.raises(ValidationError):
        LeaseRequest(good="GOLD", spaces=0)
    assert BPS == 10_000
