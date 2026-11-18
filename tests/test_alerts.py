"""Alerts (owner, 18 November 2026: "Alerts", for a Bloomberg-like Floor).

Promises: a price alert is hit once when the share reaches the price, then spent; a move alert at most once a trading day
and stays set; a news alert for each new story naming the company (never older ones); storm and wealth alerts for each
new storm or client. Hits wait unseen until marked seen. At most twenty set; unknown shares, bad levels and repeats refused.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from psycopg.rows import dict_row

from simulation import alerts, careers, floor_wealth
from tests.test_builds import pro
from tests.test_floor import _ticker
from tests.test_floor_extras import _open_time

pytestmark = pytest.mark.world("eight")


def _q(db, sql, params=()):
    with db.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def _price(db, ticker, last=None, reference=None):
    row = _q(db, "SELECT m.company_id, m.last_price, m.reference_price FROM market_instruments m JOIN companies c ON c.id = m.company_id"
                 " WHERE c.ticker = %s", (ticker,))[0]
    if last is not None or reference is not None:
        db.execute("UPDATE market_instruments SET last_price = %s, reference_price = %s WHERE company_id = %s",
                   (last if last is not None else row["last_price"], reference if reference is not None else row["reference_price"], row["company_id"]))
    return row


def test_a_price_alert_is_hit_once_then_spent_and_waits_unseen(db):
    now = _open_time()
    me, _ = pro(db, "asset_manager", "alert watcher", level=5)
    t = _ticker(db)
    price = _price(db, t)["last_price"] or _price(db, t)["reference_price"]
    _price(db, t, last=price)
    up = alerts.add(db, me, "above", t, price + 100, "time to sell", now)
    down = alerts.add(db, me, "below", t, price // 2, None, now)
    assert "at or above" in up["words"] and "warning" not in up
    assert alerts.tick(db, now) == 0
    _price(db, t, last=price + 150)
    assert alerts.tick(db, now + timedelta(seconds=5)) == 1
    page = alerts.view(db, me)
    assert page["unseen"] == 1 and "time to sell" in page["hits"][0]["words"]
    assert [a["id"] for a in page["alerts"]] == [down["id"]]                       # the price alert is spent
    assert alerts.tick(db, now + timedelta(seconds=10)) == 0
    assert alerts.mark_seen(db, me) == 1 and alerts.unseen(db, me) == 0
    # Already there when set: it says so, and is hit at once.
    again = alerts.add(db, me, "above", t, price, None, now)
    assert "straight away" in again["warning"]


def test_a_move_alert_fires_at_most_once_a_day_and_stays_set(db):
    now = _open_time()
    me, _ = pro(db, "asset_manager", "move watcher", level=5)
    t = _ticker(db)
    _price(db, t, last=10_600, reference=10_000)
    a = alerts.add(db, me, "move", t, 500, None, now)
    assert alerts.tick(db, now) == 1
    assert "up 6.0% today" in alerts.view(db, me)["hits"][0]["words"]
    _price(db, t, last=9_000)
    assert alerts.tick(db, now + timedelta(minutes=5)) == 0                        # once a trading day
    assert alerts.view(db, me)["alerts"][0]["id"] == a["id"]
    assert alerts.tick(db, now + timedelta(days=1)) == 1


def test_news_storm_and_wealth_alerts_fire_for_each_new_one_only(db):
    now = _open_time()
    me, _ = pro(db, "asset_manager", "news watcher", level=5)
    t = _ticker(db)
    world = careers.world_now(db, now)
    db.execute("INSERT INTO news_items (period, day, outlet, kind, story, importance, headline, body, tickers) VALUES"
               " (%s, %s, 'herald', 'test', 'old', 1, 'An old story', 'Old.', %s)", (world["period"], world["day"], [t]))
    alerts.add(db, me, "news", t, None, None, now)
    alerts.add(db, me, "storm", None, None, None, now)
    alerts.add(db, me, "wealth", None, None, None, now)
    assert alerts.tick(db, now) == 0                                               # nothing from before it was set
    db.execute("INSERT INTO news_items (period, day, outlet, kind, story, importance, headline, body, tickers) VALUES"
               " (%s, %s, 'herald', 'test', 'new', 1, 'A fresh story', 'New.', %s)", (world["period"], world["day"], [t]))
    company = _q(db, "SELECT id FROM companies WHERE ticker = %s", (t,))[0]["id"]
    db.execute("INSERT INTO floor_storms (slot, starts_at, ends_at, company_id, reason) VALUES (%s, %s, %s, %s, 'test')",
               (987654321, now, now + timedelta(minutes=10), company))
    floor_wealth.arrive(db, now, kind="family office", key="alert-test")
    assert alerts.tick(db, now + timedelta(seconds=5)) == 3
    words = [h["words"] for h in alerts.view(db, me)["hits"]]
    assert any("A fresh story" in w for w in words) and any("flash storm" in w for w in words) and any("Family Office" in w for w in words)
    assert not any("An old story" in w for w in words)
    assert alerts.tick(db, now + timedelta(seconds=10)) == 0
    assert len(alerts.view(db, me)["alerts"]) == 3                                 # they stay set


def test_alerts_refuse_unknown_shares_bad_levels_repeats_and_more_than_twenty(db, monkeypatch):
    now = _open_time()
    me, _ = pro(db, "asset_manager", "busy watcher", level=5)
    t = _ticker(db)
    with pytest.raises(alerts.AlertError, match="not a share"):
        alerts.add(db, me, "above", "ZZZ", 100, None, now)
    with pytest.raises(alerts.AlertError, match="Name the company"):
        alerts.add(db, me, "news", None, None, None, now)
    with pytest.raises(alerts.AlertError, match="0.5% to 50%"):
        alerts.add(db, me, "move", t, 10, None, now)
    first = alerts.add(db, me, "news", t, None, None, now)
    with pytest.raises(alerts.AlertError, match="already have"):
        alerts.add(db, me, "news", t, None, None, now)
    other, _ = pro(db, "asset_manager", "nosy", level=5)
    with pytest.raises(alerts.AlertError, match="not one of your alerts"):
        alerts.remove(db, other, first["id"])
    monkeypatch.setattr(alerts, "MOST", 1)
    with pytest.raises(alerts.AlertError, match="the most one player may"):
        alerts.add(db, me, "storm", None, None, None, now)
    alerts.remove(db, me, first["id"])
    alerts.add(db, me, "storm", None, None, None, now)


def test_the_alert_routes_need_a_login_and_good_input(client, player):
    assert client.get("/api/alerts").json()["ready"]
    assert client.post("/api/alerts", json={"kind": "sideways"}).status_code == 422
    assert client.post("/api/alerts", json={"kind": "above", "ticker": "ZZZ", "level": 100}).status_code == 409
    made = client.post("/api/alerts", json={"kind": "storm"})
    assert made.status_code == 200 and made.json()["alerts"][0]["kind"] == "storm"
    assert client.post("/api/alerts/remove", json={"alert_id": made.json()["alerts"][0]["id"]}).json()["alerts"] == []
    assert client.post("/api/alerts/seen").status_code == 200
    assert client.get("/api/me").json()["alerts_unseen"] == 0
    client.cookies.clear()
    assert client.get("/api/alerts").status_code == 401
