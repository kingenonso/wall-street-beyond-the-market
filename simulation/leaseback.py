"""The gap stage, Part 1: sale-and-leaseback (the owner's suggestion 14).

An owner (a player, or an empire through its head) sells a building it owns outright to a property company in the
same city, at a little below its value, and rents it back for four to twenty quarters. It keeps the use of the
building: a headquarters stays where it is. The rent (the yield investors want, plus two points) is paid at each
quarter's close. Two quarters missed and the lease is broken: the use is lost, and what was not paid is owed. When the
lease ends, the use ends with it: an empire must move its headquarters.
"""

from __future__ import annotations

from datetime import datetime

from psycopg import Connection
from psycopg.rows import dict_row

from simulation import clock, ledger
from simulation import property as prop
from simulation import world_data as data
from simulation.money import BPS
from simulation.property import PropertyError


def _rows(conn: Connection, sql: str, params=()) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def _one(conn: Connection, sql: str, params=()) -> dict | None:
    rows = _rows(conn, sql, params)
    return rows[0] if rows else None


def _seller(conn: Connection, player_id, for_empire: bool) -> tuple:
    """(account, empire or None)."""
    if not for_empire:
        return ledger.player_account_id(conn, player_id), None
    from simulation import empires
    empire = empires._head(conn, player_id)
    return empire["account_id"], empire


def terms(conn: Connection, property_id: int, quarters: int) -> dict:
    p = prop._property(conn, property_id)
    d = prop.districts(conn)[p["district_id"]]
    rate = prop.policy_rate(conn)
    worth = prop.value(p, d, rate)
    price = worth * (BPS - data.LEASEBACK_DISCOUNT_BPS) // BPS
    rent = price * (prop.yield_bps(rate) + data.LEASEBACK_EXTRA_YIELD_BPS) // BPS // 4
    return {"worth": worth, "price": price, "rent": rent, "quarters": quarters, "city": p["city"]}


def sell_and_lease_back(conn: Connection, player_id, property_id: int, quarters: int, now: datetime, *, for_empire: bool = False) -> dict:
    from simulation import careers
    with conn.transaction():
        state = careers.world_now(conn, now)
        account, empire = _seller(conn, player_id, for_empire)
        if not isinstance(quarters, int) or isinstance(quarters, bool) or not data.LEASEBACK_LEAST_QUARTERS <= quarters <= data.LEASEBACK_MOST_QUARTERS:
            raise PropertyError(f"A lease runs {data.LEASEBACK_LEAST_QUARTERS} to {data.LEASEBACK_MOST_QUARTERS} quarters.")
        p = prop._property(conn, property_id, lock=True)
        if prop.share_of(conn, property_id, account) < BPS:
            raise PropertyError("Only a building owned outright can be sold and leased back.")
        if p["status"] != "standing" or p["kind"] in ("land", "farmland"):
            raise PropertyError("Only a building can be leased back.")
        if prop.mortgage_on(conn, property_id):
            raise PropertyError("Repay the mortgage on it first.")
        if _one(conn, "SELECT 1 FROM auctions WHERE property_id = %s AND status = 'open'", (property_id,)):
            raise PropertyError("It is up for auction.")
        t = terms(conn, property_id, quarters)
        buyer = _one(conn, "SELECT c.id, c.name, c.account_id FROM companies c JOIN ledger_balances b ON b.account_id = c.account_id AND b.asset = 'NGN'"
                           " WHERE c.sector = 'real_estate' AND c.status = 'trading' AND b.balance >= %s ORDER BY (c.headquarters = %s) DESC,"
                           " b.balance DESC, c.ticker LIMIT 1", (t["price"] * 2, t["city"]))
        if buyer is None:
            raise PropertyError("No property company has the cash to buy it now.")
        ledger.transfer(conn, payer=buyer["account_id"], receiver=account, amount=t["price"], kind="capital_spending",
                        memo=f"{buyer['name']} buys {p['name']} and leases it back to its owner", period=state["period"])
        conn.execute("DELETE FROM property_holdings WHERE property_id = %s", (property_id,))
        conn.execute("INSERT INTO property_holdings (property_id, account_id, share_bps, since_period, paid) VALUES (%s, %s, %s, %s, %s)",
                     (property_id, buyer["account_id"], BPS, state["period"], t["price"]))
        row = _one(conn, "INSERT INTO property_leases (property_id, tenant, landlord, rent, first_period, last_period, at)"
                         " VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id",
                   (property_id, account, buyer["account_id"], t["rent"], state["period"], state["period"] + quarters - 1, now))
        if empire is not None:
            from simulation import empires
            empires._log(conn, empire["id"], f"The empire sold {p['name']} to {buyer['name']} for {prop.money(t['price'])} and leased it back "
                                             f"for {quarters} quarters at {prop.money(t['rent'])} a quarter. It keeps the use of it.", now)
        return {"lease_id": row["id"], **t, "landlord": buyer["name"]}


def leased_to(conn: Connection, property_id: int, account) -> bool:
    """Does this account have the use of the building under a running lease?"""
    if _one(conn, "SELECT to_regclass('property_leases') IS NOT NULL AS ok")["ok"] is not True:
        return False
    return bool(_one(conn, "SELECT 1 FROM property_leases WHERE property_id = %s AND tenant = %s AND status = 'running'", (property_id, account)))


def close(conn: Connection, period: int, now: datetime) -> dict:
    """At each quarter's close: the rent, and leases that end or are broken."""
    if _one(conn, "SELECT to_regclass('property_leases') IS NOT NULL AS ok")["ok"] is not True:
        return {}
    from simulation import headquarters, lending
    label = clock.period_label(period)
    paid_all = 0
    for lease in _rows(conn, "SELECT l.*, p.name FROM property_leases l JOIN properties p ON p.id = l.property_id WHERE l.status = 'running'"
                             " AND l.first_period <= %s ORDER BY l.id FOR UPDATE OF l", (period,)):
        paid = ledger.pay_up_to(conn, payer=lease["tenant"], receiver=lease["landlord"], wanted=lease["rent"], kind="lease_rent",
                                memo=f"Rent for {lease['name']}, {label}", period=period)
        paid_all += paid
        missed = lease["missed"] + (1 if paid < lease["rent"] else 0)
        if paid < lease["rent"]:
            lending.record_shortfall(conn, lease["tenant"], lease["landlord"], lease["rent"] - paid, f"The rent on {lease['name']}", period, now)
        status = "running"
        if missed >= data.LEASEBACK_MISSES_TO_BREAK:
            status = "broken"
            headquarters.lost_building(conn, lease["property_id"], lease["landlord"], period, now,
                                       why=f"The lease on {lease['name']} was broken after two missed rents.")
        elif period >= lease["last_period"]:
            status = "ended"
            headquarters.lost_building(conn, lease["property_id"], lease["landlord"], period, now,
                                       why=f"The lease on {lease['name']} has ended.")
        conn.execute("UPDATE property_leases SET missed = %s, status = %s WHERE id = %s", (missed, status, lease["id"]))
    return {"rent": paid_all}


def view(conn: Connection, account) -> list[dict]:
    if _one(conn, "SELECT to_regclass('property_leases') IS NOT NULL AS ok")["ok"] is not True:
        return []
    return [{"id": r["id"], "property_id": r["property_id"], "name": r["name"], "rent": r["rent"], "landlord": r["landlord_name"],
             "until": clock.period_label(r["last_period"]), "missed": r["missed"], "status": r["status"]}
            for r in _rows(conn, "SELECT l.*, p.name, a.name AS landlord_name FROM property_leases l JOIN properties p ON p.id = l.property_id"
                                 " JOIN ledger_accounts a ON a.id = l.landlord WHERE l.tenant = %s AND l.status = 'running' ORDER BY l.id", (account,))]
