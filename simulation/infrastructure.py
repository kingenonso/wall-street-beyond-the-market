"""The gap stage, Part 2: infrastructure projects.

About once a game year the Government announces a big project beside one district: an expressway, a rail line, or (in a
port city) a port terminal. The land beside it is marked. While it is built the Government pays the cement, steel and
building companies for the works each quarter, and the district's prices rise as it goes ahead: a quarter of the
eventual gain on the announcement, the rest as the works progress. Land beside the works gains twice as much. All of it
is in the news. (Until the Government stage, the choice is made by rule: the city whose demand has grown most.)
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
    return _one(conn, "SELECT to_regclass('infrastructure_projects') IS NOT NULL AS ok")["ok"] is True


def _uplift_now(project: dict, period: int) -> int:
    """What the project adds to its district's prices at this point: a quarter on the announcement, then in step with the
    works, all of it when done."""
    if project["status"] == "done" or period >= project["finish_period"]:
        return project["uplift_bps"]
    length = max(project["finish_period"] - project["announced_period"], 1)
    done = max(period - project["announced_period"], 0)
    return project["uplift_bps"] // 4 + project["uplift_bps"] * 3 // 4 * done // length


def _choose(conn: Connection, period: int, seed: str) -> tuple[dict, str] | None:
    """The district: in the city whose households' spending has grown most over the last year, the district not yet served
    whose land is cheapest against its city's best (the most to gain); the kind by the city."""
    import hashlib
    grown = _rows(conn, """
        SELECT a.location, a.spending * 10000 / greatest(b.spending, 1) AS g FROM household_results a
        JOIN household_results b ON b.location = a.location AND b.period = greatest(%s - 4, 0)
        WHERE a.period = %s ORDER BY g DESC, a.location""", (period, period))
    for city_row in grown:
        city = city_row["location"]
        d = _one(conn, """
            SELECT d.* FROM districts d WHERE d.city = %s
              AND NOT EXISTS (SELECT 1 FROM infrastructure_projects i WHERE i.district_id = d.id)
            ORDER BY d.rent_bps, d.id LIMIT 1""", (city,))
        if d is None:
            continue
        pick = int.from_bytes(hashlib.sha256(f"{seed}:infra:{period}".encode()).digest()[:4], "big")
        kinds = ["road", "rail"] + (["port"] if city in data.INFRA_PORT_CITIES and d["kind"] == "industry" else [])
        return d, kinds[pick % len(kinds)]
    return None


def close(conn: Connection, period: int, now: datetime, seed: str) -> dict:
    """At the quarter's close: the works are paid for and progress, a finished project is opened, and about once a game
    year a new one is announced. The districts' infrastructure gains are set."""
    if not ready(conn):
        return {}
    from simulation import news
    from simulation import property as prop
    treasury = ledger.account_id(conn, ledger.TREASURY)
    label = clock.period_label(period)
    spent = 0
    for p in _rows(conn, "SELECT i.*, d.city, d.name AS district FROM infrastructure_projects i JOIN districts d ON d.id = i.district_id"
                         " WHERE i.status = 'building' ORDER BY i.id"):
        cost = naira(data.INFRA_COST_A_QUARTER_NAIRA) * data.CITY_COST_BPS[p["city"]] // BPS
        paid = 0
        for part, sectors in ((data.DEVELOPMENT_SPLIT_BPS["cement"], ("cement",)), (data.DEVELOPMENT_SPLIT_BPS["steel"], (data.STEEL_SECTOR,)),
                              (data.DEVELOPMENT_SPLIT_BPS["works"], ("real_estate",))):
            paid += buy_from(conn, treasury, cost * part // BPS, sectors, p["city"], f"Government: works on the {p['name']}, {label}",
                             period, kind="government_purchase")
        spent += paid
        done = period >= p["finish_period"]
        conn.execute("UPDATE infrastructure_projects SET spent = spent + %s, status = %s WHERE id = %s",
                     (paid, "done" if done else "building", p["id"]))
        if done:
            news.publish(conn, period=period + 1, day=1, kind="infrastructure_done", story=f"infra-done:{p['id']}",
                         facts={"project": p["name"], "district": p["district"], "city": p["city"]}, locations=[p["city"]],
                         sectors=["real_estate", "cement"])
    if period % data.INFRA_EVERY_QUARTERS == 1:
        chosen = _choose(conn, period, seed)
        if chosen is not None:
            d, kind = chosen
            word, quarters, uplift = data.INFRA_KINDS[kind]
            name = f"{d['name']} {word}"
            row = _one(conn, "INSERT INTO infrastructure_projects (kind, name, district_id, announced_period, finish_period, uplift_bps, at)"
                             " VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id", (kind, name, d["id"], period, period + quarters, uplift, now))
            # The land beside it: the district's empty plots.
            conn.execute("UPDATE properties SET beside_project = %s WHERE district_id = %s AND kind = 'land'", (row["id"], d["id"]))
            news.publish(conn, period=period + 1, day=1, kind="infrastructure_announced", story=f"infra:{row['id']}",
                         facts={"project": name, "district": d["name"], "city": d["city"],
                                "finish": clock.period_label(period + quarters)},
                         locations=[d["city"]], sectors=["real_estate", "cement"])
    # The districts' gains from the projects beside them.
    for d in prop.districts(conn).values():
        gain = sum(_uplift_now(p, period) for p in _rows(conn, "SELECT * FROM infrastructure_projects WHERE district_id = %s", (d["id"],)))
        if gain != d["infra_bps"]:
            conn.execute("UPDATE districts SET infra_bps = %s WHERE id = %s", (gain, d["id"]))
    return {"spent": spent}


def buy_from(conn: Connection, payer, amount: int, sectors: tuple, city: str, why: str, period: int, *, kind: str = "capital_spending",
             up_to: bool = True) -> int:
    """Pay for work or materials from the companies of these sectors, those in the city first, shared equally."""
    if amount <= 0:
        return 0
    sellers = _rows(conn, "SELECT account_id, headquarters FROM companies WHERE sector = ANY(%s) AND status = 'trading' ORDER BY ticker",
                    (list(sectors),))
    local = [s for s in sellers if s["headquarters"] == city] or sellers
    if not local:
        return 0
    each = amount // len(local)
    amounts = {s["account_id"]: each for s in local}
    amounts[local[0]["account_id"]] += amount - each * len(local)
    if up_to:
        return ledger.pay_split_up_to(conn, payer=payer, amounts=amounts, kind=kind, memo=why, period=period)
    for account, part in amounts.items():
        ledger.transfer(conn, payer=payer, receiver=account, amount=part, kind=kind, memo=why, period=period)
    return amount


def view(conn: Connection) -> list[dict]:
    if not ready(conn):
        return []
    period = _one(conn, "SELECT last_closed_period AS p FROM world_state")["p"]
    return [{"id": p["id"], "kind": p["kind"], "name": p["name"], "district": p["district"], "city": p["city"],
             "announced": clock.period_label(p["announced_period"]), "finish": clock.period_label(p["finish_period"]),
             "status": p["status"], "uplift_bps": p["uplift_bps"], "gain_now_bps": _uplift_now(p, period)}
            for p in _rows(conn, "SELECT i.*, d.name AS district, d.city FROM infrastructure_projects i JOIN districts d ON d.id = i.district_id"
                                 " ORDER BY i.id DESC LIMIT 12")]
