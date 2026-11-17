"""Floor extras, slice 1 (owner, 17 November 2026: "build"): flash storms and the risk engine.

Promises: a storm is drawn from the world's secret for a slot of an open market (never in the floor hour or a closed
market); during it the clients call more, bigger, quicker and mostly in its share; afterwards its best are named. A desk
has three limits; a price past the deal or share limit is refused; a day's loss past the limit freezes the desk until the
next trading day; only the empire's Risk Manager or head sets limits, and only up to five times the Floor's own.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from psycopg.rows import dict_row

from simulation import clock, floor, floor_extras, ledger
from simulation import world_data as data
from tests.test_builds import pro
from tests.test_careers import NOW9, sound
from tests.test_floor import _ticker

pytestmark = pytest.mark.world("eight")


def _q(db, sql, params=()):
    with db.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def _open_time():
    """A time in the ninth quarter when the market is open, and it is not the floor hour."""
    for i in range(200):
        t = NOW9 + timedelta(minutes=10 * i)
        if clock.market_state(t).value == "open" and floor.floor_hour(t) is None:
            return t
    raise AssertionError("no open market found")


def test_a_flash_storm_floods_the_open_desks_and_names_its_best(db, monkeypatch):
    now = _open_time()
    banker, _account = pro(db, "investment_banker", "storm banker", level=5, cash_naira=900_000_000)
    floor.set_desk(db, banker, True, now)
    monkeypatch.setattr(data, "FLOOR_STORM_CHANCE", 1)
    monkeypatch.setattr(data, "FLOOR_STORM_FOCUS_BPS", 10_000)
    monkeypatch.setattr(data, "FLOOR_CLIENT_CALL_CHANCE", data.FLOOR_STORM_CALL_FACTOR)     # with the storm: a call every check
    floor.tick(db, now)
    storm = floor_extras.storm_now(db, now)
    assert storm is not None and storm["ends_at"] - storm["starts_at"] == timedelta(minutes=data.FLOOR_STORM_MINUTES)
    assert any(n["kind"] == "storm" and "Flash storm" in n["words"] for n in floor.notes(db, now))
    call = floor.requests_view(db, banker, now)["incoming"][0]
    assert call["ticker"] == storm["ticker"]
    row = _q(db, "SELECT created_at, quotes_until FROM floor_requests WHERE id = %s", (call["id"],))[0]
    assert row["quotes_until"] - row["created_at"] == timedelta(seconds=data.FLOOR_STORM_SECONDS)
    assert floor_extras.view(db, banker, now)["storm"]["ticker"] == storm["ticker"]
    # Afterwards it is scored once, and the Floor is told.
    after = storm["ends_at"] + timedelta(seconds=5)
    monkeypatch.setattr(data, "FLOOR_STORM_CHANCE", 10**9)
    floor.tick(db, after)
    assert _q(db, "SELECT scored FROM floor_storms WHERE id = %s", (storm["id"],))[0]["scored"]
    assert any("flash storm has passed" in n["words"] for n in floor.notes(db, after))


def test_no_storm_in_the_floor_hour_or_a_closed_market(db, monkeypatch):
    monkeypatch.setattr(data, "FLOOR_STORM_CHANCE", 1)
    lagos = clock.to_lagos(NOW9)
    for t in (lagos.replace(hour=18, minute=5), lagos.replace(hour=23, minute=5)):
        floor_extras.storms_tick(db, t)
        assert floor_extras.storm_now(db, t) is None


def test_a_price_past_the_deal_or_share_limit_is_refused(db, monkeypatch):
    now = _open_time()
    banker, _account = pro(db, "investment_banker", "limited banker", level=5, cash_naira=900_000_000)
    client, _c = pro(db, "asset_manager", "big client", level=5, cash_naira=900_000_000)
    floor.set_desk(db, banker, True, now)
    t = _ticker(db)
    share = floor._share(db, t, now)
    price = share["last_price"] or share["reference_price"]
    monkeypatch.setattr(data, "FLOOR_LIMITS", {"deal_most": price * 1_000 // 100, "name_most": price * 600 // 100, "day_loss_most": 25_000_000})
    rid = floor.ask(db, client, t, "sell", 2_000, 30, [f"player:{banker}"], now)["request_id"]
    with pytest.raises(floor.FloorError, match="limit of .* for one deal"):
        floor.quote(db, banker, rid, price, None, 20, now)
    rid = floor.ask(db, client, t, "sell", 800, 30, [f"player:{banker}"], now + timedelta(seconds=40))["request_id"]
    with pytest.raises(floor.FloorError, match="long 800 .* in one share"):
        floor.quote(db, banker, rid, price, None, 20, now + timedelta(seconds=41))


def test_a_days_loss_past_the_limit_freezes_the_desk_until_tomorrow(db, monkeypatch):
    now = _open_time()
    banker, _bank_account = pro(db, "investment_banker", "losing banker", level=5, cash_naira=900_000_000)
    client, client_account = pro(db, "asset_manager", "lucky client", level=5, cash_naira=10_000_000)
    floor.set_desk(db, banker, True, now)
    t = _ticker(db)
    share = floor._share(db, t, now)
    asset = _q(db, "SELECT share_asset FROM companies WHERE ticker = %s", (t,))[0]["share_asset"]
    ledger.transfer(db, payer=ledger.account_id(db, ledger.INVESTORS_PUBLIC), receiver=client_account, amount=1_000, asset=asset,
                    kind="test_shares", memo="Test: shares to sell")
    rid = floor.ask(db, client, t, "sell", 1_000, 30, [f"player:{banker}"], now)["request_id"]
    floor.quote(db, banker, rid, share["highest_today"], None, 20, now + timedelta(seconds=1))      # buys at the top of the day's band
    q = floor.requests_view(db, client, now + timedelta(seconds=2))["mine"][0]["quotes"][0]
    floor.take(db, client, rid, q["id"], "sell", now + timedelta(seconds=2))
    loss = -floor_extras.day_pnl(db, banker, now + timedelta(seconds=3))
    assert loss > 0
    monkeypatch.setattr(data, "FLOOR_LIMITS", {**data.FLOOR_LIMITS, "day_loss_most": max(loss // 100 - 1, 1)})
    assert floor_extras.freeze_tick(db, now + timedelta(seconds=3)) == 1
    assert not _q(db, "SELECT open FROM floor_desks WHERE player_id = %s", (banker,))[0]["open"]
    with pytest.raises(floor.FloorError, match="frozen"):
        floor.set_desk(db, banker, True, now + timedelta(seconds=4))
    assert any(n["kind"] == "risk" and "frozen" in n["words"] for n in floor.notes(db, now + timedelta(seconds=4)))
    assert floor_extras.view(db, banker, now + timedelta(seconds=4))["mine"]["frozen"]
    # The next trading day it may open again.
    floor.set_desk(db, banker, True, now + timedelta(days=1))
    sound(db)


def test_only_the_empires_risk_manager_or_head_sets_limits_up_to_five_times_the_floors(db):
    from tests.test_firm import firm_of
    _empire, team = firm_of(db)
    team = {k: v[0] if isinstance(v, tuple) else v for k, v in team.items()}
    banker, rm = team["investment_banker"], team["risk_manager"]
    base = floor_extras.floor_limits()
    done = floor_extras.set_limits(db, rm, banker, base["deal_most"] * 2, base["name_most"], base["day_loss_most"] // 2, NOW9)
    assert done["deal_most"] == base["deal_most"] * 2 and done["set_by"]
    with pytest.raises(floor.FloorError, match="at most 5 times"):
        floor_extras.set_limits(db, rm, banker, base["deal_most"] * 6, base["name_most"], base["day_loss_most"], NOW9)
    with pytest.raises(floor.FloorError, match="Risk Manager or the head"):
        floor_extras.set_limits(db, team["asset_manager"], banker, base["deal_most"], base["name_most"], base["day_loss_most"], NOW9)
    outsider, _ = pro(db, "risk_manager", "outside risk", level=5)
    with pytest.raises(floor.FloorError, match="own empire"):
        floor_extras.set_limits(db, outsider, banker, base["deal_most"], base["name_most"], base["day_loss_most"], NOW9)
    team_view = floor_extras.view(db, rm, NOW9)["team"]
    assert [b["name"] for b in team_view] and team_view[0]["limits"]["deal_most"] == base["deal_most"] * 2


def test_the_risk_routes_need_a_login_and_good_input(client, player):
    assert client.get("/api/floor/risk").status_code == 200
    assert client.post("/api/floor/limits", json={"banker_id": "not-an-id", "deal_most": 1, "name_most": 1, "day_loss_most": 1}).status_code == 422
    assert client.post("/api/floor/limits", json={"banker_id": "00000000-0000-0000-0000-000000000000", "deal_most": -1,
                                                  "name_most": 1, "day_loss_most": 1}).status_code == 422
    client.cookies.clear()
    assert client.get("/api/floor/risk").status_code == 401
