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


# ---------------------------------------------------------------------------
# Slice 2: price requests
# ---------------------------------------------------------------------------

def _q(db, sql, params=()):
    with db.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def _ticker(db):
    """A share the computer banks hold plenty of, with a price."""
    from simulation import ledger
    inst = ledger.account_id(db, ledger.INVESTORS_INSTITUTIONS)
    return _q(db, "SELECT c.ticker FROM companies c JOIN market_instruments m ON m.company_id = c.id"
                  " JOIN ledger_balances b ON b.account_id = %s AND b.asset = c.share_asset"
                  " WHERE m.halted_reason IS NULL AND b.balance > 10000000 ORDER BY c.ticker LIMIT 1", (inst,))[0]["ticker"]


@pytest.mark.world("eight")
def test_a_client_asks_the_computer_banks_and_takes_the_best_price_away_from_the_exchange(db):
    from simulation import ledger
    from tests.test_builds import pro
    from tests.test_careers import NOW9, sound
    me, account = pro(db, "asset_manager", "client", level=5, cash_naira=50_000_000)
    t = _ticker(db)
    asked = floor.ask(db, me, t, "buy", 1_000, 30, ["computer:goldbridge", "computer:coral", "computer:sahel"], NOW9)
    rid = asked["request_id"]
    # The computer banks take a few seconds to answer: nothing is on show at once.
    assert floor.requests_view(db, me, NOW9)["mine"][0]["quotes"] == []
    later = NOW9 + timedelta(seconds=22)
    quotes = floor.requests_view(db, me, later)["mine"][0]["quotes"]
    assert len(quotes) == 3 and all(q["offer"] and q["bid"] is None for q in quotes)          # asked to buy: only selling prices
    best = min(quotes, key=lambda q: q["offer"])
    assert best["desk"] == "Goldbridge Securities"                                            # the tightest spread
    cash, held = ledger.balance(db, account), ledger.balance(db, account, f"SHR-{t}")
    with pytest.raises(floor.FloorError, match="You asked to buy"):
        floor.take(db, me, rid, best["id"], "sell", later)
    done = floor.take(db, me, rid, best["id"], "buy", later)
    assert done["price"] == best["offer"] and done["quantity"] == 1_000
    assert ledger.balance(db, account) == cash - best["offer"] * 1_000                        # no exchange fee
    assert ledger.balance(db, account, f"SHR-{t}") == held + 1_000
    statuses = {q["desk"]: q["status"] for q in floor.requests_view(db, me, later)["mine"][0]["quotes"]}
    assert statuses["Goldbridge Securities"] == "taken" and set(statuses.values()) == {"taken", "lost"}
    # It is on the blotter, from the Floor, and the position's cost includes it.
    s = floor.screen(db, account, later)
    assert s["blotter"][0]["venue"] == "floor" and s["blotter"][0]["fee"] == 0 and s["blotter"][0]["side"] == "buy"
    assert next(p for p in s["positions"] if p["ticker"] == t)["average_price"] == best["offer"]
    with pytest.raises(floor.FloorError, match="closed"):
        floor.take(db, me, rid, best["id"], "buy", later)                                     # once only
    sound(db)


@pytest.mark.world("eight")
def test_a_banker_opens_a_desk_quotes_and_wins_or_fails_to_deliver(db):
    from simulation import ledger
    from tests.test_builds import pro
    from tests.test_careers import NOW9, sound
    banker, bank_account = pro(db, "investment_banker", "banker", level=5, cash_naira=20_000_000)
    client, client_account = pro(db, "asset_manager", "client", level=5, cash_naira=80_000_000)
    with pytest.raises(floor.FloorError, match="investment banker"):
        floor.set_desk(db, client, True, NOW9)
    t = _ticker(db)
    with pytest.raises(floor.FloorError, match="not taking"):                                 # a closed desk is not offered
        floor.ask(db, client, t, "two_way", 500, 20, [f"player:{banker}"], NOW9)
    floor.set_desk(db, banker, True, NOW9)
    assert f"player:{banker}" in {d["key"] for d in floor.desks_for(db, client)}
    assert f"player:{banker}" not in {d["key"] for d in floor.desks_for(db, banker)}          # never your own
    rid = floor.ask(db, client, t, "two_way", 500, 20, [f"player:{banker}", "computer:atlas"], NOW9)["request_id"]
    seen = floor.requests_view(db, banker, NOW9)["incoming"][0]
    assert seen["id"] == rid and seen["side"] == "two_way" and seen["client"] == "client" and seen["your_quote"] is None
    market = seen["market"]
    mid = (market["best_bid"] + market["best_offer"]) // 2 if market["best_bid"] and market["best_offer"] else market["last"] or market["reference"]
    with pytest.raises(floor.FloorError, match="both ways"):
        floor.quote(db, banker, rid, None, mid + 5, 30, NOW9)
    with pytest.raises(floor.FloorError, match="below your selling"):
        floor.quote(db, banker, rid, mid + 5, mid - 5, 30, NOW9)
    with pytest.raises(floor.FloorError, match="only between"):
        floor.quote(db, banker, rid, 1, mid + 5, 30, NOW9)
    floor.quote(db, banker, rid, mid - 9, mid + 9, 30, NOW9 + timedelta(seconds=3))
    floor.quote(db, banker, rid, mid - 2, mid + 2, 30, NOW9 + timedelta(seconds=4))           # a new price replaces the last
    with pytest.raises(floor.FloorError, match="Too late"):
        floor.quote(db, banker, rid, mid - 1, mid + 1, 30, NOW9 + timedelta(seconds=21))
    # The banker never sees another bank's price; the client sees both.
    assert "atlas" not in repr(floor.requests_view(db, banker, NOW9 + timedelta(seconds=15))["incoming"]).lower()
    mine = floor.requests_view(db, client, NOW9 + timedelta(seconds=15))["mine"][0]
    desk_quote = next(q for q in mine["quotes"] if q["kind"] == "player")
    assert (desk_quote["bid"], desk_quote["offer"]) == (mid - 2, mid + 2)
    # The client buys from the banker, who holds no shares: the desk cannot deliver, is marked for it, and nothing moves.
    cash = ledger.balance(db, client_account)
    with pytest.raises(floor.FloorError, match="could not deliver"):
        floor.take(db, client, rid, desk_quote["id"], "buy", NOW9 + timedelta(seconds=15))
    assert ledger.balance(db, client_account) == cash
    assert floor.requests_view(db, client, NOW9)["desks"][-1]["failed"] == 1
    # The client sells to the banker instead, on a fresh request: the banker pays and holds the shares.
    give = _q(db, "SELECT share_asset FROM companies WHERE ticker = %s", (t,))[0]["share_asset"]
    ledger.transfer(db, payer=ledger.account_id(db, ledger.INVESTORS_PUBLIC), receiver=client_account, amount=500, asset=give,
                    kind="test_shares", memo="Test: shares to sell")
    rid2 = floor.ask(db, client, t, "sell", 500, 30, [f"player:{banker}"], NOW9 + timedelta(seconds=30))["request_id"]
    floor.quote(db, banker, rid2, mid - 3, None, 20, NOW9 + timedelta(seconds=32))
    q2 = floor.requests_view(db, client, NOW9 + timedelta(seconds=33))["mine"][0]["quotes"][0]
    bank_cash = ledger.balance(db, bank_account)
    floor.take(db, client, rid2, q2["id"], "sell", NOW9 + timedelta(seconds=33))
    assert ledger.balance(db, bank_account) == bank_cash - (mid - 3) * 500
    assert ledger.balance(db, bank_account, give) == 500
    won = next(r for r in floor.requests_view(db, banker, NOW9 + timedelta(seconds=40))["incoming"] if r["id"] == rid2)
    assert won["outcome"] == "won"
    sound(db)


@pytest.mark.world("eight")
def test_the_floor_refuses_the_loopholes(db):
    from tests.test_builds import pro
    from tests.test_careers import NOW9
    client, _ = pro(db, "asset_manager", "client", level=5, cash_naira=50_000_000)
    other, _ = pro(db, "asset_manager", "other", level=5, cash_naira=50_000_000)
    t = _ticker(db)
    with pytest.raises(floor.FloorError, match="one to 5"):
        floor.ask(db, client, t, "buy", 100, 30, [f"computer:{c}" for c in floor.COMPUTER], NOW9)
    with pytest.raises(floor.FloorError, match="15 to 60"):
        floor.ask(db, client, t, "buy", 100, 5, ["computer:atlas"], NOW9)
    with pytest.raises(floor.FloorError, match="1% of the company"):
        floor.ask(db, client, t, "buy", 10**10, 30, ["computer:atlas"], NOW9)
    with pytest.raises(floor.FloorError, match="while the market is open"):
        floor.ask(db, client, t, "buy", 100, 30, ["computer:atlas"], NOW9 + timedelta(hours=10))
    with pytest.raises(floor.FloorError, match="not taking"):
        floor.ask(db, client, t, "buy", 100, 30, ["computer:nobody"], NOW9)
    ids = [floor.ask(db, client, t, "buy", 100, 30, ["computer:atlas"], NOW9)["request_id"] for _ in range(3)]
    with pytest.raises(floor.FloorError, match="3 requests waiting"):
        floor.ask(db, client, t, "buy", 100, 30, ["computer:atlas"], NOW9)
    q = _q(db, "SELECT * FROM floor_quotes WHERE request_id = %s", (ids[0],))[0]
    with pytest.raises(floor.FloorError, match="not on offer"):                    # not yet shown
        floor.take(db, client, ids[0], q["id"], "buy", NOW9)
    with pytest.raises(floor.FloorError, match="no such request"):                 # somebody else's
        floor.take(db, other, ids[0], q["id"], "buy", NOW9 + timedelta(seconds=20))
    with pytest.raises(floor.FloorError, match="expired"):
        floor.take(db, client, ids[0], q["id"], "buy", q["valid_until"])
    floor.pass_on(db, client, ids[1], NOW9 + timedelta(seconds=20))
    with pytest.raises(floor.FloorError, match="no such open request"):
        floor.pass_on(db, client, ids[1], NOW9 + timedelta(seconds=21))
    # Requests whose time is up close by themselves.
    floor.tick(db, NOW9 + timedelta(minutes=5))
    assert {r["status"] for r in _q(db, "SELECT status FROM floor_requests WHERE id = ANY(%s)", (ids,))} == {"expired", "passed"}


@pytest.mark.world("eight")
def test_computer_clients_call_an_open_desk_and_take_a_good_price(db, monkeypatch):
    from simulation import ledger
    from tests.test_builds import pro
    from tests.test_careers import NOW9, sound
    banker, bank_account = pro(db, "investment_banker", "banker", level=5, cash_naira=900_000_000)
    floor.set_desk(db, banker, True, NOW9)
    monkeypatch.setattr(floor.data, "FLOOR_CLIENT_CALL_CHANCE", 1)                  # call at once
    floor.tick(db, NOW9)
    call = floor.requests_view(db, banker, NOW9)["incoming"][0]
    assert call["computer_client"] and call["status"] == "open" and call["side"] in ("buy", "sell")
    floor.tick(db, NOW9 + timedelta(seconds=1))                                     # one computer call at a time
    assert len(floor.requests_view(db, banker, NOW9)["incoming"]) == 1
    # The banker gives a price far better than the market: the client takes it at its countdown's end.
    asset = _q(db, "SELECT share_asset FROM companies WHERE ticker = %s", (call["ticker"],))[0]["share_asset"]
    if call["side"] == "buy":
        ledger.transfer(db, payer=ledger.account_id(db, ledger.INVESTORS_PUBLIC), receiver=bank_account, amount=call["quantity"],
                        asset=asset, kind="test_shares", memo="Test: shares to sell")
        floor.quote(db, banker, call["id"], None, call["market"]["low"], 60, NOW9 + timedelta(seconds=2))
    else:
        floor.quote(db, banker, call["id"], call["market"]["high"], None, 60, NOW9 + timedelta(seconds=2))
    before = ledger.balance(db, bank_account, asset)
    ends = _q(db, "SELECT quotes_until FROM floor_requests WHERE id = %s", (call["id"],))[0]["quotes_until"]
    monkeypatch.setattr(floor.data, "FLOOR_CLIENT_CALL_CHANCE", 10**9)
    floor.tick(db, ends + timedelta(seconds=1))
    done = next(r for r in floor.requests_view(db, banker, ends)["incoming"] if r["id"] == call["id"])
    assert done["outcome"] == "won"
    assert ledger.balance(db, bank_account, asset) == before + (call["quantity"] if call["side"] == "sell" else -call["quantity"])
    sound(db)


def test_a_floor_ping_reaches_only_its_player():
    import asyncio

    from server import live_stream
    from simulation import pings
    assert pings.read('{"what": "floor", "player": "p1"}') == {"what": "floor", "empire": None, "player": "p1"}
    assert pings.read('{"what": "floor"}') is None
    with pytest.raises(ValueError):
        pings.ping(None, "floor")
    hub = live_stream.Hub()

    async def run():
        loop = asyncio.get_running_loop()
        hub.open("p1", 3, loop), hub.open("p2", 3, loop)
        assert hub.deliver({"what": "floor", "empire": None, "player": "p1"}) == 1
    asyncio.run(run())


def test_the_request_routes_need_a_login(client):
    for path, body in (("/api/floor/desk", {"open": True}), ("/api/floor/pass", {"request_id": 1}),
                       ("/api/floor/ask", {"ticker": "IDC", "side": "buy", "quantity": 1, "seconds": 30, "desks": ["computer:atlas"]}),
                       ("/api/floor/quote", {"request_id": 1, "bid_kobo": 1, "valid_seconds": 30}),
                       ("/api/floor/take", {"request_id": 1, "quote_id": 1, "side": "buy"})):
        assert client.post(path, json=body).status_code == 401
    assert client.get("/api/floor/requests").status_code == 401
