"""The gap stage, Part 2: valuing a property three ways, as a valuer does.

  * Comparable sales: what like property in the same district sold for at the Auction House or privately, over the last
    year, a square metre, times its size (with a building's condition allowed for).
  * Income: a year's rent when full, less tax and upkeep, over the yield investors want.
  * Cost: what its land is worth plus what it would cost to build it again, less wear.

The three seldom agree. All of them use only public figures.
"""

from __future__ import annotations

from psycopg import Connection
from psycopg.rows import dict_row

from simulation import world_data as data
from simulation.money import BPS


def _rows(conn: Connection, sql: str, params=()) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def three_ways(conn: Connection, property_id: int) -> dict:
    from simulation import property as prop
    p = prop._property(conn, property_id)
    d = prop.districts(conn)[p["district_id"]]
    rate = prop.policy_rate(conn)
    period = _rows(conn, "SELECT last_closed_period AS p FROM world_state")[0]["p"]
    building = p["status"] == "standing" and p["kind"] != "land"
    # Comparable sales: the same kind in the same district, sold in the last four quarters.
    sales = _rows(conn, """
        SELECT a.price, q.size_m2 FROM auctions a JOIN properties q ON q.id = a.property_id
        WHERE a.status = 'sold' AND q.district_id = %s AND q.kind = %s AND q.id <> %s AND a.period >= %s
        UNION ALL
        SELECT s.price, q.size_m2 FROM property_sales s JOIN properties q ON q.id = s.property_id
        WHERE s.status = 'done' AND q.district_id = %s AND q.kind = %s AND q.id <> %s AND s.period >= %s""",
                  (p["district_id"], p["kind"], p["id"], period - 3, p["district_id"], p["kind"], p["id"], period - 3)) \
        if _rows(conn, "SELECT to_regclass('property_sales') IS NOT NULL AS ok")[0]["ok"] else []
    if sales:
        per_metre = sum(s["price"] for s in sales) // max(sum(s["size_m2"] for s in sales), 1)
        comparables = per_metre * p["size_m2"]
        comparable_note = f"{len(sales)} sale{'s' if len(sales) != 1 else ''} of like property in {d['name']} over the last year"
    else:
        comparables = prop.value(p, d, rate)
        comparable_note = f"no recent sales of like property in {d['name']}: the district's price level instead"
    if building:
        condition = BPS // 2 + p["condition"] * BPS // 200
        comparables = comparables * condition // BPS if sales else comparables
    # Income: a year's rent when full, less tax and upkeep, over the yield.
    yearly = prop.rent_due({**p, "condition": max(p["condition"], data.POOR_CONDITION)}, d) * 4 if building else 0
    worth = prop.value(p, d, rate)
    costs = worth * (data.PROPERTY_TAX_BPS + data.LAND_TAX_BPS + data.UPKEEP_BPS * 4) // BPS
    income = max(yearly - costs, 0) * BPS // prop.yield_bps(rate) if building else 0
    # Cost: the land, plus building it again less wear.
    land = p["land_value"] * d["rent_bps"] // BPS
    rebuild = prop.build_cost({**p, "city": d["city"]}) * p["condition"] // 100 if building else 0
    cost = land + rebuild
    return {"comparables": comparables, "income": income, "cost": cost, "comparable_note": comparable_note,
            "yield_bps": prop.yield_bps(rate), "yearly_rent": yearly, "land": land, "rebuild": rebuild}
