"""Alerts (owner, 18 November 2026: "one more good feature in the floor that makes it Bloomberg like" → "Alerts").

As on a Bloomberg terminal, a player sets alerts, and the moment one is hit it appears in their alerts with a sound of
its own on the Floor, and on their "Needs you now" until they have seen it.

  above, below   a share's last price at or above (below) a price. Once hit, it is spent.
  move           a share moving so much (up or down) from yesterday's close. At most once a trading day; it stays set.
  news           each story that names a company, as it is published. It stays set.
  storm          each flash storm on the Floor, as it starts. It stays set.
  wealth         each new wealth client looking for a manager. It stays set.

A player keeps at most twenty alerts set. Alerts are looked at every few seconds while the server runs; nothing here
touches money, and an alert never shows anything its player could not see anyway.
"""

from __future__ import annotations

from datetime import datetime

from psycopg import Connection
from psycopg.rows import dict_row

from simulation import careers, exchange, pings

MOST = 20
KINDS = ("above", "below", "move", "news", "storm", "wealth")
NOTE_MOST = 80


class AlertError(Exception):
    """An alert that cannot be set. The text is shown to the player."""


def _rows(conn: Connection, sql: str, params=()) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def _one(conn: Connection, sql: str, params=()) -> dict | None:
    rows = _rows(conn, sql, params)
    return rows[0] if rows else None


def ready(conn: Connection) -> bool:
    return _one(conn, "SELECT to_regclass('alerts') IS NOT NULL AS ok")["ok"]


def _naira(kobo: int) -> str:
    return f"₦{kobo / 100:,.2f}"


def _share(conn: Connection, ticker: str) -> dict | None:
    return _one(conn, "SELECT c.ticker, c.name, m.last_price, m.reference_price FROM companies c JOIN market_instruments m ON m.company_id = c.id"
                      " WHERE c.ticker = %s", (ticker,))


def _latest(conn: Connection, kind: str) -> int:
    table = {"news": "news_items", "storm": "floor_storms", "wealth": "wealth_clients"}[kind]
    if not _one(conn, "SELECT to_regclass(%s) IS NOT NULL AS ok", (table,))["ok"]:
        return 0
    return _one(conn, f"SELECT coalesce(max(id), 0)::bigint AS n FROM {table}")["n"]


def describe(a: dict, name: str | None = None) -> str:
    who = name or a.get("ticker")
    if a["kind"] == "above":
        return f"{who} at or above {_naira(a['level'])}"
    if a["kind"] == "below":
        return f"{who} at or below {_naira(a['level'])}"
    if a["kind"] == "move":
        return f"{who} moving {a['level'] / 100:g}% or more in a day"
    if a["kind"] == "news":
        return f"any story naming {who}"
    if a["kind"] == "storm":
        return "a flash storm on the Floor"
    return "a new wealth client looking for a manager"


def add(conn: Connection, player_id, kind: str, ticker: str | None, level: int | None, note: str | None, now: datetime) -> dict:
    if kind not in KINDS:
        raise AlertError("An alert is on a price (above or below), a day's move, the news, a flash storm or a new wealth client.")
    ticker = (ticker or "").strip().upper() or None
    needs_share = kind in ("above", "below", "move", "news")
    share = None
    if needs_share:
        if not ticker:
            raise AlertError("Name the company, such as HMB.")
        share = _share(conn, ticker)
        if share is None:
            raise AlertError(f"{ticker} is not a share on the exchange.")
    else:
        ticker = None
    if kind in ("above", "below"):
        if not isinstance(level, int) or isinstance(level, bool) or level <= 0:
            raise AlertError("Give the price in naira, such as 9.50.")
    elif kind == "move":
        if not isinstance(level, int) or isinstance(level, bool) or not 50 <= level <= 5_000:
            raise AlertError("A day's move from 0.5% to 50%.")
    else:
        level = None
    note = (note or "").strip()[:NOTE_MOST] or None
    count = _one(conn, "SELECT count(*)::int AS n FROM alerts WHERE player_id = %s AND active", (player_id,))["n"]
    if count >= MOST:
        raise AlertError(f"You have {MOST} alerts set, the most one player may. Remove one first.")
    if _one(conn, "SELECT 1 AS x FROM alerts WHERE player_id = %s AND active AND kind = %s AND ticker IS NOT DISTINCT FROM %s"
                  " AND level IS NOT DISTINCT FROM %s", (player_id, kind, ticker, level)):
        raise AlertError("You already have that alert set.")
    seen = _latest(conn, kind) if kind in ("news", "storm", "wealth") else 0
    row = _one(conn, "INSERT INTO alerts (player_id, kind, ticker, level, note, created_at, seen_up_to) VALUES (%s, %s, %s, %s, %s, %s, %s)"
                     " RETURNING *", (player_id, kind, ticker, level, note, now, seen))
    out = {"id": row["id"], "words": describe(row, share["name"] if share else None)}
    if kind in ("above", "below") and share and share["last_price"]:
        price = share["last_price"]
        if (kind == "above" and price >= level) or (kind == "below" and price <= level):
            out["warning"] = f"{ticker} is already there ({_naira(price)}): it will be hit straight away."
    return out


def remove(conn: Connection, player_id, alert_id: int) -> None:
    row = _one(conn, "UPDATE alerts SET active = false WHERE id = %s AND player_id = %s AND active RETURNING id", (alert_id, player_id))
    if row is None:
        raise AlertError("That is not one of your alerts.")


def mark_seen(conn: Connection, player_id) -> int:
    rows = _rows(conn, "UPDATE alert_hits SET seen = true WHERE player_id = %s AND NOT seen RETURNING id", (player_id,))
    return len(rows)


def unseen(conn: Connection, player_id) -> int:
    if not ready(conn):
        return 0
    return _one(conn, "SELECT count(*)::int AS n FROM alert_hits WHERE player_id = %s AND NOT seen", (player_id,))["n"]


# ---------------------------------------------------------------------------
# Looking at them
# ---------------------------------------------------------------------------

def _hit(conn: Connection, a: dict, words: str, now: datetime, *, ticker: str | None = None, spend: bool = False, **changes) -> None:
    if a["note"]:
        words = f"{words} Your note: {a['note']}"
    conn.execute("INSERT INTO alert_hits (alert_id, player_id, at, ticker, words) VALUES (%s, %s, %s, %s, %s)",
                 (a["id"], a["player_id"], now, ticker or a["ticker"], words))
    sets = ["hits = hits + 1"] + (["active = false"] if spend else []) + [f"{k} = %s" for k in changes]
    conn.execute(f"UPDATE alerts SET {', '.join(sets)} WHERE id = %s", (*changes.values(), a["id"]))
    pings.ping(conn, "floor", player=a["player_id"])


def tick(conn: Connection, now: datetime) -> int:
    """Look at every alert set; returns how many were hit."""
    if not ready(conn):
        return 0
    hit = 0
    alerts = _rows(conn, "SELECT * FROM alerts WHERE active ORDER BY id")
    if not alerts:
        return 0
    day, _ = exchange.session_of(now)
    tickers = sorted({a["ticker"] for a in alerts if a["ticker"]})
    shares = {s["ticker"]: s for s in _rows(conn, "SELECT c.ticker, c.name, m.last_price, m.reference_price FROM companies c"
                                                  " JOIN market_instruments m ON m.company_id = c.id WHERE c.ticker = ANY(%s)", (tickers,))}
    world = careers.world_now(conn, now)
    for a in alerts:
        with conn.transaction():
            s = shares.get(a["ticker"]) if a["ticker"] else None
            if a["kind"] in ("above", "below") and s and s["last_price"]:
                price = s["last_price"]
                if (a["kind"] == "above" and price >= a["level"]) or (a["kind"] == "below" and price <= a["level"]):
                    _hit(conn, a, f"{s['name']} ({s['ticker']}) is at {_naira(price)}: {describe(a)}.", now, spend=True)
                    hit += 1
            elif a["kind"] == "move" and s and s["last_price"] and s["reference_price"] and a["last_day"] != day:
                move = (s["last_price"] - s["reference_price"]) * 10_000 // s["reference_price"]
                if abs(move) >= a["level"]:
                    _hit(conn, a, f"{s['name']} ({s['ticker']}) is {'up' if move > 0 else 'down'} {abs(move) / 100:.1f}% today, at "
                                  f"{_naira(s['last_price'])}.", now, last_day=day)
                    hit += 1
            elif a["kind"] == "news":
                stories = _rows(conn, "SELECT id, headline FROM news_items WHERE id > %s AND %s = ANY(tickers)"
                                      " AND (period < %s OR (period = %s AND day <= %s)) ORDER BY id LIMIT 5",
                                (a["seen_up_to"], a["ticker"], world["period"], world["period"], world["day"]))
                for story in stories:
                    _hit(conn, a, f"News on {a['ticker']}: {story['headline']}", now, seen_up_to=story["id"])
                    a = {**a, "seen_up_to": story["id"]}
                    hit += 1
            elif a["kind"] == "storm" and _latest(conn, "storm") > a["seen_up_to"]:
                for storm in _rows(conn, "SELECT f.id, c.ticker, c.name FROM floor_storms f JOIN companies c ON c.id = f.company_id"
                                         " WHERE f.id > %s AND f.starts_at <= %s ORDER BY f.id", (a["seen_up_to"], now)):
                    _hit(conn, a, f"A flash storm has hit the Floor, mostly in {storm['name']} ({storm['ticker']}): the clients are calling.",
                         now, ticker=storm["ticker"], seen_up_to=storm["id"])
                    a = {**a, "seen_up_to": storm["id"]}
                    hit += 1
            elif a["kind"] == "wealth" and _latest(conn, "wealth") > a["seen_up_to"]:
                for client in _rows(conn, "SELECT id, name, amount FROM wealth_clients WHERE id > %s AND arrived_at <= %s ORDER BY id",
                                    (a["seen_up_to"], now)):
                    _hit(conn, a, f"{client['name']} has come to the Floor with {_naira(client['amount'])} to be looked after.", now,
                         seen_up_to=client["id"])
                    a = {**a, "seen_up_to": client["id"]}
                    hit += 1
    return hit


def view(conn: Connection, player_id) -> dict:
    if not ready(conn):
        return {"ready": False}
    names = {r["ticker"]: r["name"] for r in _rows(conn, "SELECT ticker, name FROM companies")}
    set_ = [{"id": a["id"], "kind": a["kind"], "ticker": a["ticker"], "level": a["level"], "note": a["note"], "hits": a["hits"],
             "created_at": a["created_at"], "words": describe(a, names.get(a["ticker"]))}
            for a in _rows(conn, "SELECT * FROM alerts WHERE player_id = %s AND active ORDER BY id", (player_id,))]
    hits = _rows(conn, "SELECT id, at, ticker, words, seen FROM alert_hits WHERE player_id = %s ORDER BY id DESC LIMIT 30", (player_id,))
    return {"ready": True, "alerts": set_, "hits": hits, "unseen": unseen(conn, player_id), "most": MOST}
