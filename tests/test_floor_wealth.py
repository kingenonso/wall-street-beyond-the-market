"""Floor extras, slice 3 (owner, 17 November 2026: "Ok go ahead"): the wealth desk.

Promises: a client arrives with a sum, a goal and limits; asset managers pitch a fee; the client picks on cost and record,
and its money goes into its own account, which only its manager trades (never in an industry it will not hold). Its limits
are looked at: each breach is recorded once a day and costs its satisfaction, and three in a quarter and it leaves with its
money. At the quarter's close it pays its fees and stays, adds money, warns, or leaves. A manager may hand a client back.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from psycopg.rows import dict_row

from simulation import floor, floor_wealth, ledger
from simulation import world_data as data
from tests.test_builds import pro
from tests.test_careers import sound
from tests.test_floor_extras import _open_time

pytestmark = pytest.mark.world("eight")


def _q(db, sql, params=()):
    with db.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def _managed(db, now, kind="retired couple", fee=100, perf=1000, name="wealth manager"):
    manager, account = pro(db, "asset_manager", name, level=5)
    client = floor_wealth.arrive(db, now, kind=kind, key=f"test-{name}")
    floor_wealth.pitch(db, manager, client["id"], fee, perf, now)
    floor_wealth.tick(db, client["pitches_until"] + timedelta(seconds=1))
    client = _q(db, "SELECT * FROM wealth_clients WHERE id = %s", (client["id"],))[0]
    assert client["status"] == "managed"
    return manager, account, client


def test_a_client_arrives_takes_pitches_and_picks_on_cost_and_record(db):
    now = _open_time()
    cheap, _a = pro(db, "asset_manager", "cheap manager", level=5)
    dear, _b = pro(db, "asset_manager", "dear manager", level=5)
    client = floor_wealth.arrive(db, now, kind="family office", key="t1")
    assert client["status"] == "seeking" and client["most_shares_bps"] == 9000
    assert any(n["kind"] == "wealth" and client["name"] in n["words"] for n in floor.notes(db, now))
    seen = floor_wealth.view(db, cheap, now)["seeking"]
    assert seen[0]["id"] == client["id"] and seen[0]["goal"]
    floor_wealth.pitch(db, cheap, client["id"], 50, 1000, now)
    floor_wealth.pitch(db, dear, client["id"], 200, 2000, now)
    public = ledger.account_id(db, ledger.INVESTORS_PUBLIC)
    public_cash = ledger.balance(db, public)
    floor_wealth.tick(db, client["pitches_until"] + timedelta(seconds=1))
    row = _q(db, "SELECT * FROM wealth_clients WHERE id = %s", (client["id"],))[0]
    assert row["status"] == "managed" and row["manager_id"] == cheap and row["fee_bps"] == 50
    assert ledger.balance(db, row["account_id"]) == client["amount"] and ledger.balance(db, public) == public_cash - client["amount"]
    with pytest.raises(floor.FloorError, match="no longer taking pitches"):
        floor_wealth.pitch(db, dear, client["id"], 10, 0, client["pitches_until"] + timedelta(seconds=2))
    # A record of clients lost outweighs a small saving in fees.
    other = floor_wealth.arrive(db, now, kind="family office", key="t2")
    db.execute("INSERT INTO wealth_clients (name, kind, goal, amount, most_shares_bps, least_cash_bps, most_drop_bps, goal_bps, arrived_at,"
               " pitches_until, status, manager_id) VALUES ('Gone', 'family office', 'x', 100, 1, 1, 1, 1, %s, %s, 'left', %s)", (now, now, cheap))
    floor_wealth.pitch(db, cheap, other["id"], 50, 1000, now)
    floor_wealth.pitch(db, dear, other["id"], 100, 1000, now)
    floor_wealth.tick(db, other["pitches_until"] + timedelta(seconds=1))
    assert _q(db, "SELECT manager_id FROM wealth_clients WHERE id = %s", (other["id"],))[0]["manager_id"] == dear
    # With no pitch, a client goes elsewhere.
    lonely = floor_wealth.arrive(db, now, kind="retired couple", key="t3")
    floor_wealth.tick(db, lonely["pitches_until"] + timedelta(seconds=1))
    assert _q(db, "SELECT status FROM wealth_clients WHERE id = %s", (lonely["id"],))[0]["status"] == "went_elsewhere"
    sound(db)


def test_pitches_are_an_asset_managers_within_the_fee_limits_and_three_clients(db, monkeypatch):
    now = _open_time()
    client = floor_wealth.arrive(db, now, kind="retired couple", key="p1")
    banker, _ = pro(db, "investment_banker", "not a manager", level=5)
    with pytest.raises(floor.FloorError, match="asset manager's"):
        floor_wealth.pitch(db, banker, client["id"], 100, 0, now)
    manager, _ = pro(db, "asset_manager", "greedy", level=5)
    with pytest.raises(floor.FloorError, match="yearly fee may be nought to 2.0%"):
        floor_wealth.pitch(db, manager, client["id"], 300, 0, now)
    with pytest.raises(floor.FloorError, match="share of the gain"):
        floor_wealth.pitch(db, manager, client["id"], 100, 2500, now)
    monkeypatch.setattr(data, "WEALTH_MOST_CLIENTS", 0)
    with pytest.raises(floor.FloorError, match="the most one manager may"):
        floor_wealth.pitch(db, manager, client["id"], 100, 0, now)


def test_the_manager_trades_the_clients_own_account_but_never_in_a_banned_industry(db):
    now = _open_time()
    manager, manager_account, client = _managed(db, now, kind="church foundation")
    banned = _q(db, "SELECT ticker FROM companies c JOIN market_instruments m ON m.company_id = c.id WHERE c.sector = 'consumer'"
                    " AND m.halted_reason IS NULL LIMIT 1")[0]["ticker"]
    allowed = _q(db, "SELECT ticker FROM companies c JOIN market_instruments m ON m.company_id = c.id WHERE c.sector = 'banking'"
                     " AND m.halted_reason IS NULL LIMIT 1")[0]["ticker"]
    share = floor._share(db, allowed, now)
    price = share["last_price"] or share["reference_price"]
    with pytest.raises(floor.FloorError, match="will not hold consumer goods"):
        floor_wealth.trade(db, manager, client["id"], banned, "buy", 100, price, now)
    placed = floor_wealth.trade(db, manager, client["id"], allowed, "buy", 100, share["lowest_today"], now)
    order = _q(db, "SELECT account_id FROM market_orders WHERE id = %s", (placed["order"]["id"],))[0]
    assert order["account_id"] == client["account_id"] != manager_account
    stranger, _ = pro(db, "asset_manager", "stranger", level=5)
    with pytest.raises(floor.FloorError, match="not a client you look after"):
        floor_wealth.trade(db, stranger, client["id"], allowed, "buy", 100, price, now)
    view = floor_wealth.view(db, manager, now)["clients"][0]
    assert view["orders"] and view["orders"][0]["ticker"] == allowed
    floor_wealth.cancel(db, manager, client["id"], placed["order"]["id"], now)
    assert not floor_wealth.view(db, manager, now)["clients"][0]["orders"]
    sound(db)


def test_breaches_are_recorded_once_a_day_and_three_in_a_quarter_and_the_client_leaves(db):
    now = _open_time()
    manager, _a, client = _managed(db, now, kind="retired couple")
    t = _q(db, "SELECT c.ticker, c.share_asset FROM companies c JOIN market_instruments m ON m.company_id = c.id"
               " WHERE m.halted_reason IS NULL AND c.sector = 'banking' LIMIT 1")[0]
    share = floor._share(db, t["ticker"], now)
    price = share["last_price"] or share["reference_price"]
    public = ledger.account_id(db, ledger.INVESTORS_PUBLIC)
    # Most of the money ends up in shares: past the client's 30%.
    shares = client["amount"] * 6 // 10 // price
    ledger.transfer(db, payer=public, receiver=client["account_id"], amount=shares, asset=t["share_asset"], kind="test_shares", memo="Test")
    ledger.transfer(db, payer=client["account_id"], receiver=public, amount=shares * price, kind="test_cash", memo="Test")
    assert floor_wealth.check(db, client, now) == ["shares"]
    assert floor_wealth.check(db, client, now + timedelta(minutes=11)) == []        # once a day
    sat = _q(db, "SELECT satisfaction_bps FROM wealth_clients WHERE id = %s", (client["id"],))[0]["satisfaction_bps"]
    assert sat == data.WEALTH_START_SATISFACTION_BPS - data.WEALTH_BREACH_COST_BPS
    # Then too little cash and a fall from its high: three, and it leaves at once with everything.
    ledger.transfer(db, payer=client["account_id"], receiver=public, amount=ledger.balance(db, client["account_id"]) - 1_000, kind="test_cash", memo="Test")
    later = now + timedelta(days=1)
    row = _q(db, "SELECT * FROM wealth_clients WHERE id = %s", (client["id"],))[0]
    broken = floor_wealth.check(db, row, later)
    assert "cash" in broken and "drop" in broken
    row = _q(db, "SELECT * FROM wealth_clients WHERE id = %s", (client["id"],))[0]
    assert row["status"] == "left" and "broken" in row["left_why"]
    assert not _q(db, "SELECT 1 FROM ledger_balances WHERE account_id = %s AND balance > 0", (client["account_id"],))
    assert any("has left" in n["words"] for n in floor.notes(db, later))
    assert floor_wealth.reputation(db, manager)["left"] == 1
    sound(db)


def test_at_the_quarters_close_the_client_pays_its_fees_and_judges_its_manager(db):
    now = _open_time()
    _manager, manager_account, client = _managed(db, now, kind="family office", fee=200, perf=0)
    before = ledger.balance(db, manager_account)
    floor_wealth.at_close(db, 9, now)
    review = _q(db, "SELECT * FROM wealth_reviews WHERE client_id = %s", (client["id"],))[0]
    fee = client["amount"] * 200 // 10_000 // 4
    assert review["fee"] == fee and ledger.balance(db, manager_account) == before + fee
    assert review["verdict"] in ("stays", "warns") and review["benchmark_bps"] is not None
    floor_wealth.at_close(db, 9, now)                                                 # once a quarter
    assert len(_q(db, "SELECT 1 FROM wealth_reviews WHERE client_id = %s", (client["id"],))) == 1
    # A client already unhappy, after a bad quarter, leaves.
    public = ledger.account_id(db, ledger.INVESTORS_PUBLIC)
    ledger.transfer(db, payer=client["account_id"], receiver=public, amount=ledger.balance(db, client["account_id"]) // 5, kind="test_loss",
                    memo="Test: a bad quarter")
    db.execute("UPDATE wealth_clients SET satisfaction_bps = 3500 WHERE id = %s", (client["id"],))
    floor_wealth.at_close(db, 10, now + timedelta(days=7))
    assert _q(db, "SELECT verdict FROM wealth_reviews WHERE client_id = %s AND period = 10", (client["id"],))[0]["verdict"] == "leaves"
    assert _q(db, "SELECT status FROM wealth_clients WHERE id = %s", (client["id"],))[0]["status"] == "left"
    sound(db)


def test_a_very_happy_client_adds_money_and_a_manager_may_hand_one_back(db):
    now = _open_time()
    manager, _a, client = _managed(db, now, kind="retired couple", fee=0, perf=0)
    public = ledger.account_id(db, ledger.INVESTORS_PUBLIC)
    ledger.transfer(db, payer=public, receiver=client["account_id"], amount=client["amount"] // 10, kind="test_gain", memo="Test: a good quarter")
    db.execute("UPDATE wealth_clients SET satisfaction_bps = 8000 WHERE id = %s", (client["id"],))
    worth = ledger.balance(db, client["account_id"])
    floor_wealth.at_close(db, 9, now)
    assert _q(db, "SELECT verdict FROM wealth_reviews WHERE client_id = %s", (client["id"],))[0]["verdict"] == "adds"
    assert ledger.balance(db, client["account_id"]) == worth + worth * data.WEALTH_ADD_BPS // 10_000
    floor_wealth.hand_back(db, manager, client["id"], now)
    assert _q(db, "SELECT status, left_why FROM wealth_clients WHERE id = %s", (client["id"],))[0]["left_why"] == "its manager handed it back"
    with pytest.raises(floor.FloorError, match="not a client you look after"):
        floor_wealth.hand_back(db, manager, client["id"], now)
    sound(db)


def test_the_wealth_routes_need_a_login_and_good_input(client, player):
    page = client.get("/api/floor/wealth")
    assert page.status_code == 200 and page.json()["ready"]
    assert client.post("/api/floor/wealth/pitch", json={"client_id": 1, "fee_bps": -1, "perf_bps": 0}).status_code == 422
    assert client.post("/api/floor/wealth/trade", json={"client_id": 1, "ticker": "TOOLONG", "side": "buy", "quantity": 1,
                                                        "limit_price": 1}).status_code == 422
    assert client.post("/api/floor/wealth/hand-back", json={"client_id": 999999}).status_code == 409
    client.cookies.clear()
    assert client.get("/api/floor/wealth").status_code == 401
