"""Stage 10, Part 2: media titles bought and sold at the Auction House (owner's suggestion 1).

Five small titles, one in each city, begin in the Government's hands: The Garden City Courier, The Harmattan Post, Capital
Bulletin, The Evening Drum and Aba Market Voice (a radio station). The Government sells them one at a time at the
Auction House; an owner (a player or an empire) may sell theirs on the same way.

An owner earns from readers. Each quarter a title brings in ₦40 for each regular reader (its sales and advertising, paid
by its city's households), and ₦2 more for each reader of the stories printed in it that quarter. Its staff, paper and
print take three-fifths; the rest is paid to the owner. A Financial Journalist who owns a title, or sits in the empire that
owns it, may print their stories in it: the title's audience reads them, and each story's readers grow its audience a
little (up to three times where it began); with nothing printed in it, the audience drifts back.

The big media houses bid for a title the Government sells, up to what they think it is worth (about five years' profit),
so there is always a buyer at some price. Every naira moves through the ledger.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from psycopg import Connection
from psycopg.rows import dict_row

from simulation import clock, ledger
from simulation import world_data as data
from simulation.money import BPS


def _rows(conn: Connection, sql: str, params=()) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def _one(conn: Connection, sql: str, params=()) -> dict | None:
    rows = _rows(conn, sql, params)
    return rows[0] if rows else None


def ready(conn: Connection) -> bool:
    return bool(_rows(conn, "SELECT to_regclass('media_titles') IS NOT NULL AS ok")[0]["ok"])


def setup(conn: Connection, period: int, now: datetime) -> None:
    """The five titles, in the Government's hands (run once, at a close, if they are not there yet)."""
    if not ready(conn) or _one(conn, "SELECT 1 AS x FROM media_titles LIMIT 1"):
        return
    government = ledger.account_id(conn, ledger.TREASURY)
    for name, kind, city, audience in data.MEDIA_TITLES:
        account = ledger.create_account(conn, kind="media", name=f"Title: {name}")
        conn.execute("INSERT INTO media_titles (name, kind, city, audience, base_audience, account_id, owner_account, since_period, at)"
                     " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)", (name, kind, city, audience, audience, account, government, period, now))


def title(conn: Connection, title_id: int, *, lock: bool = False) -> dict | None:
    return _one(conn, "SELECT * FROM media_titles WHERE id = %s" + (" FOR UPDATE" if lock else ""), (title_id,))


def quarter_profit(t: dict, story_readers: int = 0) -> tuple[int, int, int]:
    revenue = t["audience"] * data.MEDIA_KOBO_PER_READER + story_readers * data.MEDIA_STORY_KOBO_PER_READER
    costs = revenue * data.MEDIA_COST_BPS // BPS
    return revenue, costs, revenue - costs


def fair(t: dict) -> int:
    """What a title is worth: about five years of its profit at today's audience."""
    _, _, profit = quarter_profit(t)
    return max(profit * 4 * data.MEDIA_VALUE_TIMES, 100)


def owner_name(conn: Connection, t: dict) -> str:
    if t["owner_player"]:
        return _one(conn, "SELECT display_name AS n FROM players WHERE id = %s", (t["owner_player"],))["n"]
    if t["owner_empire"]:
        return _one(conn, "SELECT name AS n FROM empires WHERE id = %s", (t["owner_empire"],))["n"]
    company = _one(conn, "SELECT name AS n FROM companies WHERE account_id = %s", (t["owner_account"],))
    return company["n"] if company else "the Government"


def title_for(conn: Connection, player_id, title_id: int) -> dict | None:
    """The title, if this journalist may print in it: they own it, or sit in the empire that owns it."""
    t = title(conn, title_id)
    if t is None:
        return None
    if t["owner_player"] == player_id:
        return t
    if t["owner_empire"] and _one(conn, "SELECT 1 AS x FROM empire_seats WHERE empire_id = %s AND player_id = %s", (t["owner_empire"], player_id)):
        return t
    return None


def mine(conn: Connection, player_id) -> list[dict]:
    """The titles this player may print in."""
    return [t for t in _rows(conn, "SELECT * FROM media_titles ORDER BY id") if title_for(conn, player_id, t["id"])]


def close(conn: Connection, period: int, now: datetime) -> None:
    """At the close: each title's quarter. Its readers pay, its costs are paid to its city's households, the rest goes to its owner.
    Its audience grows with the stories printed in it, or drifts back. The Government puts one title it still holds up for sale."""
    if not ready(conn):
        return
    setup(conn, period, now)
    for t in _rows(conn, "SELECT * FROM media_titles ORDER BY id FOR UPDATE"):
        story_readers = int(_one(conn, "SELECT coalesce(sum(readers), 0) AS n FROM stories WHERE title_id = %s AND status = 'published' AND period = %s",
                                 (t["id"], period))["n"])
        households = _one(conn, "SELECT account_id FROM households WHERE location = %s", (t["city"],))["account_id"]
        revenue, costs, profit = quarter_profit(t, story_readers)
        got = ledger.pay_up_to(conn, payer=households, receiver=t["account_id"], wanted=revenue, kind="title_revenue",
                               memo=f"{t['name']}: its readers and advertisers, {clock.period_label(period)}", period=period)
        paid_costs = ledger.pay_up_to(conn, payer=t["account_id"], receiver=households, wanted=got * data.MEDIA_COST_BPS // BPS,
                                      kind="wages", memo=f"{t['name']}: its staff, paper and print", period=period) if got else 0
        left = ledger.balance(conn, t["account_id"])
        to_owner = 0
        if left > 0 and t["owner_account"] != t["account_id"]:
            to_owner = ledger.pay_up_to(conn, payer=t["account_id"], receiver=t["owner_account"], wanted=left, kind="dividend",
                                        memo=f"{t['name']}: the owner's profit, {clock.period_label(period)}", period=period)
        grown = story_readers * data.MEDIA_GROWTH_BPS // BPS
        audience = t["audience"] + grown if grown else t["audience"] - max((t["audience"] - t["base_audience"]) * data.MEDIA_DRIFT_BPS // BPS, 0)
        audience = min(max(audience, t["base_audience"] // 2), t["base_audience"] * data.MEDIA_AUDIENCE_MOST_TIMES)
        conn.execute("UPDATE media_titles SET audience = %s, last_profit = %s WHERE id = %s", (audience, got - paid_costs, t["id"]))
        conn.execute("INSERT INTO media_results (title_id, period, audience, story_readers, revenue, costs, profit, to_owner)"
                     " VALUES (%s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
                     (t["id"], period, t["audience"], story_readers, got, paid_costs, got - paid_costs, to_owner))
    _government_sells(conn, period, now)


def _government_sells(conn: Connection, period: int, now: datetime) -> None:
    from simulation import auctions
    government = ledger.account_id(conn, ledger.TREASURY)
    if _one(conn, "SELECT 1 AS x FROM auctions WHERE title_id IS NOT NULL AND status = 'open' AND seller = %s", (government,)):
        return
    t = _one(conn, "SELECT * FROM media_titles WHERE owner_account = %s AND NOT EXISTS (SELECT 1 FROM auctions a WHERE a.title_id = media_titles.id"
                   " AND a.status = 'open') ORDER BY id LIMIT 1", (government,))
    if t is None:
        return
    seed = _one(conn, "SELECT fortune_seed FROM world_state")["fortune_seed"]
    value = fair(t)
    low, high = data.MEDIA_RESERVE_BPS
    reserve = value * int(low + (high - low) * auctions._uniform(seed, f"title-reserve:{t['id']}", period)) // BPS
    # (A day after the close, so everybody can see it coming; it ends before the next close.)
    opens = now + timedelta(hours=12)
    auction = auctions.open_title_auction(conn, t["id"], government, "listing", reserve, value * 6 // 10, value, opens, period)
    from simulation import news
    news.publish(conn, period=period + 1, day=2, kind="title_for_sale", story=f"title-sale:{auction}",
                 facts={"title": t["name"], "city": t["city"]})


def owner_list(conn: Connection, player_id, title_id: int, reserve: int, now: datetime, *, for_empire: bool = False) -> int:
    """The owner puts their title up for auction, with a lowest price nobody else sees."""
    from simulation import auctions, careers
    from simulation.property import PropertyError
    with conn.transaction():
        t = title(conn, title_id, lock=True)
        if t is None:
            raise PropertyError("There is no such title.")
        if for_empire:
            e = _one(conn, "SELECT * FROM empires WHERE head_player_id = %s AND status = 'active'", (player_id,))
            if e is None or t["owner_empire"] != e["id"]:
                raise PropertyError("Your empire does not own that title.")
        elif t["owner_player"] != player_id:
            raise PropertyError("You do not own that title.")
        if _one(conn, "SELECT 1 AS x FROM auctions WHERE title_id = %s AND status = 'open'", (title_id,)):
            raise PropertyError("It is already up for auction.")
        if not isinstance(reserve, int) or reserve < 0:
            raise PropertyError("Name your lowest price.")
        value = fair(t)
        period = careers.world_now(conn, now)["period"]
        return auctions.open_title_auction(conn, title_id, t["owner_account"], "owner", reserve, max(value // 2, 100), value, now, period)


def sold(conn: Connection, title_id: int, buyer_account, price: int, period: int) -> None:
    """The title changes hands (called by the Auction House when a sale settles)."""
    owner = _one(conn, "SELECT player_id FROM ledger_accounts WHERE id = %s", (buyer_account,))
    empire = _one(conn, "SELECT id FROM empires WHERE account_id = %s", (buyer_account,))
    conn.execute("UPDATE media_titles SET owner_account = %s, owner_player = %s, owner_empire = %s, since_period = %s, paid = %s WHERE id = %s",
                 (buyer_account, owner["player_id"] if owner else None, empire["id"] if empire else None, period, price, title_id))


def view(conn: Connection, viewer=None) -> list[dict]:
    out = []
    for t in _rows(conn, "SELECT * FROM media_titles ORDER BY id"):
        last = _rows(conn, "SELECT period, audience, revenue, profit FROM media_results WHERE title_id = %s ORDER BY period DESC LIMIT 4", (t["id"],))
        out.append({"id": t["id"], "name": t["name"], "kind": t["kind"], "city": t["city"], "audience": t["audience"],
                    "owner": owner_name(conn, t), "since": clock.period_label(t["since_period"]), "worth": fair(t),
                    "last": [{"quarter": clock.period_label(r["period"]), "audience": r["audience"], "revenue": r["revenue"], "profit": r["profit"]}
                             for r in last],
                    "yours": bool(viewer and title_for(conn, viewer, t["id"])),
                    "for_sale": bool(_one(conn, "SELECT 1 AS x FROM auctions WHERE title_id = %s AND status = 'open'", (t["id"],)))})
    return out
