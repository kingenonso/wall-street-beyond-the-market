"""Live events, part 1: three evenings a week, something happens in the shared world at once for everybody, and every empire
competes on how it reads and handles it for thirty minutes. A test for each promise and each loophole.

Promises: the bell rings on Monday, Wednesday and Friday at 20:00 Lagos time, once; each kind is a real thing with a real
effect (a scandal in the quarter's accounts, an energy price jump, savers' trust falling, the Central Bank's next rate,
a takeover bid); investors who read the news at once mark the touched shares within minutes, the institutions a day
later; the empires are scored on their sealed prediction and on what the event did to their money, and the league gets
the points once; a head's standing plan is carried out at the bell; the news reports the bell and the result.

Loopholes: a prediction after the first ten minutes, a second prediction, a changed prediction, a prediction for an empire
the player is not in, or for an empire not in the field at the bell; seeing a rival's prediction before the end; a plan
set by anyone but the head; scoring twice; a bell rung late after a long outage; the same kind twice in a row.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from psycopg.rows import dict_row

from simulation import clock, crisis, exchange, ledger, liveevents
from simulation import world_data as data
from simulation.money import BPS
from tests.test_careers import NOW9, sound
from tests.test_empires import founded
from tests.test_market import place
from tests.test_objectives import give_cash

pytestmark = pytest.mark.world("eight")

BELL = NOW9 + timedelta(hours=7)          # NOW9 is a Monday at 13:00 in Lagos: the bell is at 20:00 the same day


def _one(db, sql, params=()):
    with db.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(sql, params).fetchall()
    return rows[0] if rows else None


def _all(db, sql, params=()):
    with db.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def ring(db, monkeypatch, kind: str, at=BELL):
    """Ring the bell with the kind chosen for the test (the world's secret would otherwise choose)."""
    monkeypatch.setattr(liveevents, "_plan_kind", lambda conn, seed, bell: [kind] + [k for k in liveevents.KINDS if k != kind])
    return liveevents.open_event(db, at, at)


def stake(db, empire, ticker, shares):
    c = _one(db, "SELECT * FROM companies WHERE ticker = %s", (ticker,))
    ledger.transfer(db, payer=ledger.account_id(db, ledger.INVESTORS_PUBLIC), receiver=empire["account_id"], amount=shares,
                    asset=c["share_asset"], kind="test_shares", memo="Test: a stake")
    return c


def points(db, empire_id, part):
    return _one(db, "SELECT coalesce(sum(points), 0)::int AS p FROM league_points WHERE empire_id = %s AND reference LIKE %s",
                (empire_id, f"live:%:{part}"))["p"]


def test_the_bell_rings_on_monday_wednesday_and_friday_at_eight_in_the_evening_lagos_time():
    assert clock.to_lagos(BELL).strftime("%A %H:%M") == "Monday 20:00"
    assert liveevents.slot_now(BELL) == BELL and liveevents.slot_now(BELL + timedelta(minutes=29)) == BELL
    assert liveevents.slot_now(BELL + timedelta(minutes=30)) is None and liveevents.slot_now(BELL - timedelta(minutes=1)) is None
    assert liveevents.next_slot(BELL) == BELL + timedelta(days=2)                     # Wednesday
    assert liveevents.next_slot(BELL + timedelta(days=2)) == BELL + timedelta(days=4)  # Friday
    assert liveevents.next_slot(BELL + timedelta(days=4)) == BELL + timedelta(days=7)  # Monday again
    assert liveevents.slot_now(BELL + timedelta(days=1)) is None                      # never on a Tuesday


def test_the_bell_rings_once_and_takes_a_snapshot_of_every_empire_in_the_field(db, monkeypatch):
    empire, _, _ = founded(db)
    event = ring(db, monkeypatch, "fraud")
    assert event is not None and event["kind"] == "fraud" and event["status"] == "open"
    assert event["ends_at"] - event["starts_at"] == timedelta(minutes=30)
    assert event["predict_until"] - event["starts_at"] == timedelta(minutes=10)
    field = _all(db, "SELECT * FROM live_event_entries WHERE event_id = %s", (event["id"],))
    active = _all(db, "SELECT id FROM empires WHERE status = 'active' AND kind <> 'pension'")
    assert {f["empire_id"] for f in field} == {e["id"] for e in active} and empire["id"] in {f["empire_id"] for f in field}
    # The computer-run empires' analysts have predicted; the players' empire has not yet.
    assert all(f["prediction_bps"] is not None for f in field if not f["run_by_players"])
    assert next(f for f in field if f["empire_id"] == empire["id"])["prediction_bps"] is None
    # Once for each bell, however many servers ring it.
    assert liveevents.open_event(db, BELL, BELL + timedelta(minutes=1)) is None
    assert liveevents.tick(db, BELL + timedelta(minutes=2)) is False
    assert _one(db, "SELECT count(*) AS n FROM live_events")["n"] == 1
    # The news has it, at once.
    assert _one(db, "SELECT count(*) AS n FROM news_items WHERE kind = 'live_event_open'")["n"] >= 1
    sound(db)


def test_a_fraud_is_a_scandal_in_the_quarter_and_investors_mark_the_share_down_at_once_the_institutions_a_day_later(db, monkeypatch):
    empire, _, _ = founded(db)
    target = stake(db, empire, "IDC", 10_000)                 # the drama is where the players are
    event = ring(db, monkeypatch, "fraud")
    assert str(event["featured_company_id"]) == str(target["id"])
    scandal = _one(db, "SELECT * FROM events WHERE id = %s", (event["world_event_id"],))
    assert scandal["kind"] == "scandal" and scandal["company_id"] == target["id"] and scandal["sales_bps"] < 0
    assert scandal["period"] == event["period"] and scandal["day"] == event["day"]
    day = exchange.session_of(BELL)[0]
    assert liveevents.shocks_today(db, day, lag_days=0)[target["id"]] == -data.LIVE_SHOCK_BPS["fraud"]
    assert target["id"] not in liveevents.shocks_today(db, day, lag_days=1)             # the institutions read it tomorrow
    assert liveevents.shocks_today(db, day + timedelta(days=1), lag_days=1)[target["id"]] == -data.LIVE_SHOCK_BPS["fraud"]
    # Fading: two thirds of it the next day, nothing after three trading days.
    assert liveevents.shocks_today(db, day + timedelta(days=1), lag_days=0)[target["id"]] == -data.LIVE_SHOCK_BPS["fraud"] * 2 // 3
    assert target["id"] not in liveevents.shocks_today(db, day + timedelta(days=3), lag_days=0)
    # The investors who read the news at once quote lower after the bell.
    exchange.open_market(db, BELL)
    from simulation import investors
    investors.act(db, BELL, force=True)
    public = ledger.account_id(db, ledger.INVESTORS_PUBLIC)
    book = _one(db, "SELECT centre FROM investor_books WHERE account_id = %s AND company_id = %s", (public, target["id"]))
    founders = _one(db, "SELECT centre FROM investor_books WHERE account_id = %s AND company_id = %s",
                    (ledger.account_id(db, "investors:founders"), target["id"]))
    assert book is not None and founders is not None and book["centre"] < founders["centre"]
    sound(db)


def test_a_fuel_crisis_raises_energy_prices_and_marks_oil_up_and_fuel_users_down(db, monkeypatch):
    event = ring(db, monkeypatch, "oil_spike")
    jump = _one(db, "SELECT * FROM events WHERE id = %s", (event["world_event_id"],))
    assert jump["kind"] == "energy_price_jump" and jump["commodity"] == "energy" and jump["price_bps"] > 0
    sectors = {t["ticker"]: (_one(db, "SELECT sector FROM companies WHERE ticker = %s", (t["ticker"],))["sector"], t["bps"]) for t in event["touched"]}
    assert all(bps > 0 for sector, bps in sectors.values() if sector == "oil_gas")
    assert all(bps < 0 for sector, bps in sectors.values() if sector in data.LIVE_FUEL_USERS)
    assert _one(db, "SELECT sector FROM companies WHERE id = %s", (event["featured_company_id"],))["sector"] == "oil_gas"


def test_a_bank_run_lowers_savers_trust_for_some_days_so_they_really_take_their_money_out(db, monkeypatch):
    event = ring(db, monkeypatch, "bank_run")
    bank = _one(db, "SELECT c.*, c.id AS id FROM companies c WHERE id = %s", (event["featured_company_id"],))
    assert bank["sector"] == "banking"
    p, d = event["period"], event["day"]
    assert liveevents.trust_hit(db, bank["id"], p, d) == -data.LIVE_RUN_TRUST_POINTS
    assert liveevents.trust_hit(db, bank["id"], p, d + data.LIVE_RUN_GAME_DAYS + 1) == 0
    score, parts = crisis.target(db, dict(bank), p, d, {}, {}, False)
    assert parts["live_event"] == -data.LIVE_RUN_TRUST_POINTS
    others = [t for t in event["touched"] if t["ticker"] != bank["ticker"]]
    assert all(t["bps"] < 0 for t in others)                              # other banks are marked down a little too


def test_an_emergency_rate_move_changes_the_central_banks_next_decision(db, monkeypatch):
    event = ring(db, monkeypatch, "rate_move")
    inflation = _one(db, "SELECT inflation_bps FROM economy_results ORDER BY period DESC LIMIT 1")["inflation_bps"]
    hike = inflation > data.INFLATION_TARGET_BPS
    assert event["rate_bps"] == (data.LIVE_RATE_MOVE_BPS if hike else -data.LIVE_RATE_MOVE_BPS)
    assert liveevents.rate_extra_bps(db, event["period"]) == event["rate_bps"]
    assert liveevents.rate_extra_bps(db, event["period"] + 1) == 0
    banks = [t for t in event["touched"] if _one(db, "SELECT sector FROM companies WHERE ticker = %s", (t["ticker"],))["sector"] == "banking"]
    assert banks and all((t["bps"] > 0) == hike for t in banks)


def test_a_takeover_bid_is_real_or_another_kind_happens_and_nothing_is_left_behind(db, monkeypatch):
    before = _one(db, "SELECT count(*) AS n FROM takeovers")["n"]
    event = ring(db, monkeypatch, "takeover")
    if event["kind"] == "takeover":
        bid = _one(db, "SELECT * FROM takeovers WHERE id = %s", (event["takeover_id"],))
        assert bid["status"] == "open" and bid["target_company_id"] == event["featured_company_id"]
        assert bid["closes_period"] == event["period"]                     # it is settled when this quarter closes
    else:
        assert event["takeover_id"] is None and _one(db, "SELECT count(*) AS n FROM takeovers")["n"] == before
    sound(db)


def test_never_the_same_kind_twice_in_a_row_and_the_choice_comes_from_the_worlds_secret(db):
    seed = _one(db, "SELECT fortune_seed FROM world_state")["fortune_seed"]
    first = liveevents.open_event(db, BELL, BELL)
    order = liveevents._plan_kind(db, seed, BELL + timedelta(days=2))
    assert order[0] != first["kind"]
    # The same world and bell always choose the same way; a different secret chooses its own way.
    assert liveevents._plan_kind(db, seed, BELL + timedelta(days=2)) == order
    assert any(liveevents._plan_kind(db, "x" * 64, BELL + timedelta(days=2 * n)) != liveevents._plan_kind(db, seed, BELL + timedelta(days=2 * n))
               for n in range(1, 6))


def test_one_sealed_prediction_for_each_empire_in_the_first_ten_minutes(db, monkeypatch):
    empire, (head, _), partners = founded(db)
    banker = partners["investment_banker"][0]
    event = ring(db, monkeypatch, "fraud")
    liveevents.predict(db, banker, event["id"], -400, BELL + timedelta(minutes=3))
    with pytest.raises(liveevents.LiveEventError, match="already"):
        liveevents.predict(db, head, event["id"], -200, BELL + timedelta(minutes=4))
    with pytest.raises(Exception, match="cannot be changed"):
        with db.transaction():
            db.execute("UPDATE live_event_entries SET prediction_bps = 0 WHERE event_id = %s AND empire_id = %s", (event["id"], empire["id"]))
    # Too late, and from nobody's empire.
    with pytest.raises(liveevents.LiveEventError, match="first ten minutes"):
        liveevents.predict(db, head, event["id"], 100, BELL + timedelta(minutes=11))
    from tests.test_builds import pro
    loner, _ = pro(db, "asset_manager", "loner", level=10)
    with pytest.raises(liveevents.LiveEventError, match="Join one"):
        liveevents.predict(db, loner, event["id"], 100, BELL + timedelta(minutes=2))
    # An empire that joined the field after the bell has no entry to predict for.
    with db.transaction(force_rollback=True):
        db.execute("ALTER TABLE live_event_entries DISABLE TRIGGER live_event_entries_sealed")
        db.execute("DELETE FROM live_event_entries WHERE event_id = %s AND empire_id = %s", (event["id"], empire["id"]))
        db.execute("ALTER TABLE live_event_entries ENABLE TRIGGER live_event_entries_sealed")
        with pytest.raises(liveevents.LiveEventError, match="not in the field"):
            liveevents.predict(db, head, event["id"], 100, BELL + timedelta(minutes=2))
    # Sealed: a rival sees only that the empire has predicted, not the figure, until the event is scored.
    seen = liveevents.view(db, loner, BELL + timedelta(minutes=5))["live"]["table"]
    row = next(r for r in seen if r["empire"] == empire["name"])
    assert row["predicted"] and row["prediction_bps"] is None and row["result_kobo"] is None
    mine = liveevents.view(db, banker, BELL + timedelta(minutes=5))
    assert next(r for r in mine["live"]["table"] if r["yours"])["prediction_bps"] == -400 and not mine["can_predict"]


def test_the_head_sets_a_standing_plan_and_it_is_carried_out_at_the_bell(db, monkeypatch):
    empire, (head, _), partners = founded(db)
    with pytest.raises(liveevents.LiveEventError, match="Only the head"):
        liveevents.set_plan(db, partners["asset_manager"][0], "cut", 0, NOW9)
    target = stake(db, empire, "IDC", 10_000)
    liveevents.set_plan(db, head, "cut", 0, NOW9)
    event = ring(db, monkeypatch, "fraud")
    assert str(event["featured_company_id"]) == str(target["id"])
    actions = _all(db, "SELECT * FROM live_event_actions WHERE event_id = %s AND empire_id = %s", (event["id"], empire["id"]))
    assert len(actions) == 1 and "Sell 5,000 IDC" in actions[0]["what"]
    if actions[0]["done"]:
        assert _one(db, "SELECT count(*) AS n FROM market_orders WHERE account_id = %s AND side = 'sell'", (empire["account_id"],))["n"] == 1
    else:
        assert "refused" in actions[0]["what"]                          # in words, if a limit stood in the way
    # A plan cannot be changed while the event runs: it was carried out at the bell.
    with pytest.raises(liveevents.LiveEventError, match="running"):
        liveevents.set_plan(db, head, "hold", 0, BELL + timedelta(minutes=5))
    sound(db)


def test_scoring_ranks_the_predictions_and_the_money_and_gives_the_league_its_points_once(db, monkeypatch):
    empire, (head, _), partners = founded(db)
    target = stake(db, empire, "IDC", 20_000)
    event = ring(db, monkeypatch, "fraud")
    start = event["start_price"]
    # Two traders deal in the featured share at a higher price inside the window: the last price is the end price.
    from tests.test_builds import pro
    seller, seller_account = pro(db, "asset_manager", "seller", level=10, cash_naira=0)
    buyer, buyer_account = pro(db, "asset_manager", "buyer", level=10, cash_naira=0)
    ledger.transfer(db, payer=ledger.account_id(db, ledger.INVESTORS_PUBLIC), receiver=seller_account, amount=1_000,
                    asset=target["share_asset"], kind="test_shares", memo="Test: shares")
    give_cash(db, buyer_account, 1_000_000)
    up = start * 105 // 100
    place(db, seller_account, "sell", 1_000, up, now=BELL + timedelta(minutes=12), ticker="IDC")
    placed = place(db, buyer_account, "buy", 1_000, up, now=BELL + timedelta(minutes=12), ticker="IDC")
    last = _one(db, "SELECT price FROM market_trades WHERE company_id = %s ORDER BY id DESC LIMIT 1", (target["id"],))["price"]
    assert placed["trades"] and start < last
    move = (last - start) * BPS // start
    # The players' empire predicts exactly; the computer-run analysts guessed a fall.
    liveevents.predict(db, partners["asset_manager"][0], event["id"], move, BELL + timedelta(minutes=9))
    # Nothing is scored before the end.
    liveevents.tick(db, BELL + timedelta(minutes=20))
    assert _one(db, "SELECT status FROM live_events WHERE id = %s", (event["id"],))["status"] == "open"
    liveevents.tick(db, BELL + timedelta(minutes=31))
    done = _one(db, "SELECT * FROM live_events WHERE id = %s", (event["id"],))
    assert done["status"] == "scored" and done["end_price"] == start * (BPS + move) // BPS
    entry = _one(db, "SELECT * FROM live_event_entries WHERE event_id = %s AND empire_id = %s", (event["id"], empire["id"]))
    assert entry["miss_bps"] == 0 and entry["result_kobo"] == 20_000 * (last - start)
    assert points(db, empire["id"], "prediction") == data.LIVE_PLACES[0]
    assert points(db, empire["id"], "money") == data.LIVE_PLACES[0]          # the only empire whose money the event raised
    assert points(db, empire["id"], "took_part") == data.LIVE_TOOK_PART
    assert entry["points"] == 2 * data.LIVE_PLACES[0] + data.LIVE_TOOK_PART
    # Once only.
    liveevents.score(db, event["id"], BELL + timedelta(minutes=40))
    assert points(db, empire["id"], "prediction") == data.LIVE_PLACES[0]
    # Now everyone may see every prediction and the points; the news reports the winner.
    table = liveevents.view(db, buyer, BELL + timedelta(minutes=41))["past"][0]["table"]
    assert all(r["prediction_bps"] is not None for r in table if r["predicted"]) and table[0]["empire"] == empire["name"]
    result = _one(db, "SELECT facts FROM news_items WHERE kind = 'live_event_result' LIMIT 1")["facts"]
    assert result["winner"] == empire["name"]
    sound(db)


def test_a_bell_missed_by_a_long_outage_is_not_rung_late_and_an_event_is_scored_whenever_the_server_comes_back(db, monkeypatch):
    assert liveevents.tick(db, BELL + timedelta(minutes=15)) is False                 # too late to ring it now
    assert _one(db, "SELECT count(*) AS n FROM live_events")["n"] == 0
    assert liveevents.tick(db, BELL + timedelta(days=2, minutes=4)) is True           # Wednesday's, four minutes late: rung
    assert liveevents.tick(db, BELL + timedelta(days=3)) is False
    assert _one(db, "SELECT status FROM live_events")["status"] == "scored"


def test_the_page_says_when_the_next_bell_is(client, db):
    from tests.conftest import ADULT, join
    assert join(client, ADULT).status_code == 201
    body = client.get("/api/live").json()
    assert body["ready"] and body["next_at"] and body["minutes"] == 30 and len(body["kinds"]) == 5 and body["live"] is None
