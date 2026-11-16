"""The Floor, slice 1 (owner, 16 November 2026: "build"): the multiplayer home and its trading floor screen.

Promises: the bar adds up (realised and unrealised profit, the fees paid, what the shares are worth, the account's value);
positions carry their average price; the blotter lists every trade of the account with its side and fee, newest first;
the intraday chart puts the last price of each few minutes in order, falls back to the last day that traded, and shows
the best prices waiting; the Auction House lists every open auction of every kind.

Loopholes: another player's trades or holdings on someone's screen; a seller's secret lowest price, or another bidder's
limit or name, in the Auction House; the screen without logging in; a chart for a share that does not exist.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from psycopg.rows import dict_row

from simulation import floor, ledger
from tests.test_market import OPEN, place, sound, trader


def test_the_bar_positions_and_blotter_add_up_for_the_players_own_account_only(db):
    seller = trader(db, "seller", shares=10_000)
    buyer = trader(db, "buyer", cash_naira=2_000_000)
    other = trader(db, "other", cash_naira=1_000_000)
    place(db, seller, "sell", 3_000, 2_000)
    place(db, buyer, "buy", 3_000, 2_000, now=OPEN + timedelta(minutes=1))
    place(db, seller, "buy", 1_000, 1_950, now=OPEN + timedelta(minutes=2))
    place(db, buyer, "sell", 1_000, 1_950, now=OPEN + timedelta(minutes=3))          # sells a third at a loss
    sound(db)
    s = floor.screen(db, buyer, OPEN + timedelta(minutes=4))
    assert [(t["side"], t["quantity"], t["price"]) for t in s["blotter"]] == [("sell", 1_000, 1_950), ("buy", 3_000, 2_000)]
    fees = sum(t["fee"] for t in s["blotter"])
    assert fees > 0 and s["bar"]["fees"] == fees
    (p,) = s["positions"]
    assert p["shares"] == 2_000 and 2_000 <= p["average_price"] <= 2_010            # the price, and its share of the fee
    assert s["bar"]["realised"] < 0                                                   # the third sold at a loss, after fees
    assert s["bar"]["unrealised"] == p["gain"] and s["bar"]["total"] == s["bar"]["realised"] + s["bar"]["unrealised"]
    assert s["bar"]["exposure"] == p["value"] == p["shares"] * p["price"]
    assert s["bar"]["value"] == s["bar"]["cash"] + s["bar"]["held_for_orders"] + s["bar"]["exposure"]
    assert s["bar"]["cash"] == ledger.balance(db, buyer)
    # Somebody else's screen shows none of it.
    nobody = floor.screen(db, other, OPEN + timedelta(minutes=4))
    assert nobody["positions"] == [] and nobody["blotter"] == [] and nobody["bar"]["fees"] == 0


def test_the_chart_takes_the_last_price_of_each_few_minutes_and_falls_back_to_the_last_day_that_traded(db):
    seller = trader(db, "seller", shares=10_000)
    buyer = trader(db, "buyer", cash_naira=5_000_000)
    for minute, price in ((0, 2_000), (2, 2_020), (7, 2_040), (31, 1_980)):
        place(db, seller, "sell", 100, price, now=OPEN + timedelta(minutes=minute))
        place(db, buyer, "buy", 100, price, now=OPEN + timedelta(minutes=minute, seconds=5))
    place(db, seller, "sell", 50, 2_100, now=OPEN + timedelta(minutes=40))           # waiting: the best offer
    c = floor.intraday(db, "IDC", OPEN + timedelta(minutes=45), 5)
    assert c["today"] and [p["price"] for p in c["points"]] == [2_020, 2_040, 1_980]
    assert [p["volume"] for p in c["points"]] == [200, 100, 100]
    assert c["best_offer"] == 2_100 and c["last_price"] == 1_980
    assert [p["price"] for p in floor.intraday(db, "IDC", OPEN + timedelta(minutes=45), 60)["points"]] == [1_980]
    assert floor.intraday(db, "IDC", OPEN + timedelta(minutes=45), 7)["minutes"] == 5         # only the zooms on offer
    # The next day, before its first trade: yesterday's line, said to be yesterday's.
    later = floor.intraday(db, "IDC", OPEN + timedelta(days=1), 5)
    assert not later["today"] and len(later["points"]) == 3
    assert floor.intraday(db, "ZZZ", OPEN, 5) is None


@pytest.mark.world("eight")
def test_the_auction_house_lists_every_open_lot_and_never_a_secret(db):
    from simulation import auctions
    from tests.test_builds import pro
    from tests.test_careers import NOW9
    later = NOW9 + timedelta(hours=1)
    me, mine_account = pro(db, "asset_manager", "bidder", level=10, cash_naira=900_000_000)
    rival, rival_account = pro(db, "asset_manager", "rival", level=10, cash_naira=900_000_000)
    with db.cursor(row_factory=dict_row) as cur:
        a = cur.execute("SELECT * FROM auctions WHERE status = 'open' AND property_id IS NOT NULL AND opens_at <= %s ORDER BY fair LIMIT 1",
                        (NOW9,)).fetchone()
    auctions.place_bid(db, rival_account, a["id"], a["fair"] * 2 + 7_777, later, player_id=rival)
    auctions.place_bid(db, mine_account, a["id"], a["fair"], later, player_id=me)
    seen = floor.auction_house(db, mine_account, later)
    lot = next(x for x in seen if x["id"] == a["id"])
    assert lot["kind"] == "property" and lot["where"] == "#/property/auctions" and lot["bidders"] == 2
    assert lot["your_limit"] == a["fair"] and not lot["you_lead"] and lot["status"] == "open"
    assert isinstance(lot["lowest_price_met"], bool)
    flat = repr(seen)
    assert "reserve" not in flat
    assert "rival" not in flat
    assert str(a["fair"] * 2 + 7_777) not in flat
    assert str(a["reserve"]) not in repr(lot)
    assert {x["kind"] for x in seen} <= {"property", "title", "bank"}
    assert all(x["status"] == "open" for x in seen[: sum(1 for y in seen if y["status"] == "open")])     # open ones first


def test_the_floor_needs_a_login_and_a_real_share(client):
    from tests.conftest import ADULT, join
    for path in ("/api/floor", "/api/floor/chart/IDC", "/api/floor/auctions"):
        assert client.get(path).status_code == 401
    assert join(client, ADULT).status_code == 201
    body = client.get("/api/floor").json()
    assert set(body["bar"]) >= {"realised", "unrealised", "total", "fees", "exposure", "cash", "value"}
    assert isinstance(body["bar"]["cash"], str) and body["positions"] == [] and body["blotter"] == []
    assert client.get("/api/floor/chart/ZZZ").status_code == 404
    assert client.get("/api/floor/chart/idc").status_code == 422
    assert client.get("/api/floor/auctions").status_code == 200
