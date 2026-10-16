"""The gap stage, Part 2: zoning and rezoning (a rule-based planning office, until the Government stage).

Every plot and building has a zone: residential, commercial, industrial, agricultural, resource (oil and gas) or
mixed use. What is built must fit the zone. An owner may ask the planning office to rezone a plot: it is decided at the
quarter's close, by rule, and granted when the city needs more of the new use (its district for that use is nearly
full). The planners also rezone a plot themselves when a district stays very full. Every rezoning is in the news, and a
rezoned plot's land is worth what land for its new use is worth.
"""

from __future__ import annotations

from datetime import datetime

from psycopg import Connection
from psycopg.rows import dict_row

from simulation import clock, ledger
from simulation import world_data as data
from simulation.money import BPS, naira


def _rows(conn: Connection, sql: str, params=()) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def _one(conn: Connection, sql: str, params=()) -> dict | None:
    rows = _rows(conn, sql, params)
    return rows[0] if rows else None


def ready(conn: Connection) -> bool:
    return _one(conn, "SELECT to_regclass('rezonings') IS NOT NULL AS ok")["ok"] is True


def first_zones(conn: Connection) -> None:
    """A new world: zones from each district's character, a few mixed-use plots, Port Harcourt's oil land, and a hotel
    and a mall in each city (the same rule as the migration that brought zoning to older worlds)."""
    conn.execute("""UPDATE properties p SET zone = CASE d.kind WHEN 'business' THEN 'commercial' WHEN 'homes' THEN 'residential'
                    WHEN 'shops' THEN 'commercial' WHEN 'industry' THEN 'industrial' ELSE 'agricultural' END
                    FROM districts d WHERE d.id = p.district_id""")
    conn.execute("UPDATE properties p SET zone = 'mixed' FROM districts d WHERE d.id = p.district_id AND d.kind IN ('business', 'shops')"
                 " AND p.name LIKE 'Plot 2,%%'")
    conn.execute("UPDATE properties p SET zone = 'resource' FROM districts d WHERE d.id = p.district_id AND d.kind = 'farmland'"
                 " AND d.city = ANY(%s) AND p.kind = 'land'", (list(data.RESOURCE_CITIES),))
    conn.execute("UPDATE properties p SET kind = 'hotel' FROM districts d WHERE d.id = p.district_id AND d.kind = 'business'"
                 " AND p.kind = 'office' AND p.name LIKE '%% Plaza'")
    conn.execute("UPDATE properties p SET kind = 'mall' FROM districts d WHERE d.id = p.district_id AND d.kind = 'shops'"
                 " AND p.kind = 'shop' AND p.name LIKE '%% Mall'")


def allows(zone: str, kind: str) -> bool:
    return kind in data.ZONE_ALLOWS.get(zone, ())


def default_kind(p: dict) -> str:
    """What is built on a plot when the owner does not say: the district's own kind of building, if the zone allows it."""
    usual = data.DISTRICT_BUILDINGS[p["district_kind"]][0]
    return usual if allows(p["zone"], usual) else data.ZONE_ALLOWS[p["zone"]][0]


def check_build(p: dict, kind: str | None) -> str:
    from simulation.property import PropertyError
    kind = kind or default_kind(p)
    if kind not in data.RENT_KIND_TIMES_BPS or kind == "land":
        raise PropertyError("Name what to build: homes, offices, shops, a hotel, a mall, a factory, a warehouse or farmland.")
    if not allows(p["zone"], kind):
        allowed = ", ".join(data.PROPERTY_KIND_NAMES[k].lower() for k in data.ZONE_ALLOWS[p["zone"]])
        raise PropertyError(f"This plot is zoned {data.ZONE_NAMES[p['zone']].lower()}: only {allowed} may be built here. "
                            f"Ask the planning office to rezone it first.")
    return kind


# ---------------------------------------------------------------------------
# Asking to rezone
# ---------------------------------------------------------------------------

def ask(conn: Connection, account, property_id: int, to_zone: str, now: datetime) -> dict:
    """An owner of the whole of a plot asks the planning office to rezone it. A fee to the Government; decided at the
    quarter's close."""
    from simulation import careers
    from simulation import property as prop
    with conn.transaction():
        state = careers.world_now(conn, now)
        p = prop._property(conn, property_id, lock=True)
        if prop.share_of(conn, property_id, account) < BPS:
            raise prop.PropertyError("Only the owner of the whole of a plot asks for it to be rezoned.")
        if to_zone not in data.ZONES:
            raise prop.PropertyError("Name a zone: residential, commercial, industrial, agricultural, resource or mixed.")
        if to_zone == p["zone"]:
            raise prop.PropertyError("It is zoned that way already.")
        if p["frozen"]:
            raise prop.PropertyError("A dispute over it must be settled first.")
        if p["status"] == "standing" and p["kind"] != "land" and not allows(to_zone, p["kind"]):
            raise prop.PropertyError("What stands on it would not fit that zone. Only an empty plot, or a zone the building fits, can be asked for.")
        if _one(conn, "SELECT 1 FROM rezonings WHERE property_id = %s AND status = 'asked'", (property_id,)):
            raise prop.PropertyError("A request for it is already with the planning office.")
        fee = naira(data.REZONE_FEE_NAIRA)
        try:
            ledger.transfer(conn, payer=account, receiver=ledger.account_id(conn, ledger.TREASURY), amount=fee, kind="property_tax",
                            memo=f"Planning office: a request to rezone {p['name']}", period=state["period"])
        except ledger.InsufficientFunds:
            raise prop.PropertyError(f"The planning office's fee is {prop.money(fee)}.") from None
        row = _one(conn, "INSERT INTO rezonings (property_id, from_zone, to_zone, asked_by, fee, period, at) VALUES (%s, %s, %s, %s, %s, %s, %s)"
                         " RETURNING id", (property_id, p["zone"], to_zone, account, fee, state["period"], now))
        return {"rezoning_id": row["id"], "fee": fee, "decided": f"at the close of {clock.period_label(state['period'])}"}


def _needed(conn: Connection, city: str, zone: str) -> bool:
    """Does the city need more land for this use? Its district for the use is nearly full."""
    kinds = {"residential": ("homes",), "commercial": ("business", "shops"), "industrial": ("industry",), "agricultural": ("farmland",),
             "resource": ("farmland",), "mixed": ("homes", "business", "shops")}[zone]
    row = _one(conn, "SELECT max(occupancy_bps) AS o FROM districts WHERE city = %s AND kind = ANY(%s)", (city, list(kinds)))
    if zone == "resource":
        return city in data.RESOURCE_CITIES
    return bool(row and row["o"] is not None and row["o"] >= data.REZONE_STRONG_OCCUPANCY_BPS)


def _rezone(conn: Connection, p: dict, to_zone: str) -> None:
    """The plot's land is now worth land for its new use."""
    before = data.ZONE_LAND_TIMES_BPS[p["zone"]]
    after = data.ZONE_LAND_TIMES_BPS[to_zone]
    conn.execute("UPDATE properties SET zone = %s, land_value = land_value * %s / %s WHERE id = %s", (to_zone, after, max(before, 1), p["id"]))


def close(conn: Connection, period: int, now: datetime) -> dict:
    """At the quarter's close: requests are decided, and the planners rezone a plot where a district has stayed full."""
    if not ready(conn):
        return {}
    from simulation import news
    granted = refused = 0
    for r in _rows(conn, "SELECT z.*, p.name, p.zone, p.land_value, d.city FROM rezonings z JOIN properties p ON p.id = z.property_id"
                         " JOIN districts d ON d.id = p.district_id WHERE z.status = 'asked' AND z.period <= %s ORDER BY z.id FOR UPDATE OF z",
                   (period,)):
        if r["zone"] != r["from_zone"]:
            ok, words = False, "It had been rezoned already."
        elif _needed(conn, r["city"], r["to_zone"]):
            ok, words = True, f"{r['city']} needs more land for {data.ZONE_NAMES[r['to_zone']].lower()} use."
        else:
            ok, words = False, f"{r['city']} has room enough for {data.ZONE_NAMES[r['to_zone']].lower()} use already."
        if ok:
            _rezone(conn, {"id": r["property_id"], "zone": r["zone"]}, r["to_zone"])
            granted += 1
            news.publish(conn, period=period + 1, day=2, kind="rezoning", story=f"rezone:{r['id']}",
                         facts={"property": r["name"], "city": r["city"], "zone": data.ZONE_NAMES[r["to_zone"]].lower()},
                         locations=[r["city"]], sectors=["real_estate"])
        else:
            refused += 1
        conn.execute("UPDATE rezonings SET status = %s, decided_period = %s, words = %s WHERE id = %s",
                     ("granted" if ok else "refused", period, words, r["id"]))
    # The planners: where a district has been very full for two quarters, the city's emptiest district gives up a plot.
    for d in _rows(conn, """
            SELECT d.* FROM districts d
            WHERE d.occupancy_bps >= %s AND EXISTS (SELECT 1 FROM district_results r WHERE r.district_id = d.id AND r.period = %s
                                                    AND r.occupancy_bps >= %s)
            ORDER BY d.id""", (data.REZONE_PLANNER_OCCUPANCY_BPS, period - 1, data.REZONE_PLANNER_OCCUPANCY_BPS)):
        zone = data.DISTRICT_ZONE[d["kind"]]
        plot = _one(conn, """
            SELECT p.*, d2.city FROM properties p JOIN districts d2 ON d2.id = p.district_id
            WHERE d2.city = %s AND d2.id <> %s AND p.kind = 'land' AND p.zone <> %s AND p.zone NOT IN ('mixed', 'resource')
              AND NOT EXISTS (SELECT 1 FROM rezonings z WHERE z.property_id = p.id AND z.period >= %s)
            ORDER BY d2.occupancy_bps, p.id LIMIT 1""", (d["city"], d["id"], zone, period - 4))
        if plot is None:
            continue
        _rezone(conn, plot, zone)
        row = _one(conn, "INSERT INTO rezonings (property_id, from_zone, to_zone, status, period, decided_period, words, at)"
                         " VALUES (%s, %s, %s, 'granted', %s, %s, %s, %s) RETURNING id",
                   (plot["id"], plot["zone"], zone, period, period, f"{d['name']} is full: the planners made room.", now))
        news.publish(conn, period=period + 1, day=2, kind="rezoning", story=f"rezone:{row['id']}",
                     facts={"property": plot["name"], "city": plot["city"], "zone": data.ZONE_NAMES[zone].lower()},
                     locations=[plot["city"]], sectors=["real_estate"])
        granted += 1
    return {"granted": granted, "refused": refused}


def view(conn: Connection, account) -> list[dict]:
    if not ready(conn):
        return []
    return [{"id": r["id"], "property_id": r["property_id"], "name": r["name"], "from": data.ZONE_NAMES[r["from_zone"]],
             "to": data.ZONE_NAMES[r["to_zone"]], "status": r["status"], "words": r["words"]}
            for r in _rows(conn, "SELECT z.*, p.name FROM rezonings z JOIN properties p ON p.id = z.property_id WHERE z.asked_by = %s"
                                 " ORDER BY z.id DESC LIMIT 10", (account,))]
