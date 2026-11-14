"""Stage 12: the goods themselves — gold, oil, farm produce and building materials.

The exchange has listed futures on these four since Stage 9 and settled them in cash. What
never existed is the goods: no player has ever owned a gram of gold or a barrel of oil. This
file adds them, and it adds them honestly.

Three rules make the rest of it work:

  * The price of a good is not a number somebody chose. It is the value of the contract the
    exchange already lists, divided by the units in a contract. The price of the goods and the
    price of a future therefore cannot drift apart, and nobody can buy one and sell the other
    for nothing.

  * Goods are not money. They are counted in their own unit (a gram, a barrel, a bag, a tonne)
    and they belong to a ledger account, but they are not a ledger asset. Every trade moves
    naira through the ledger and units through these tables in one database transaction, so a
    player can never be paid without being delivered, or delivered without being charged.

  * The other side of every trade is the market's dealers, an escrow account. What they sell
    they must hold; what they buy they must be able to pay for. They start with a stock of
    goods (the world's producers made them) and a float put behind them by the pension funds,
    recorded as a real transfer. No naira is ever created here.

And goods do not sit in the air. Every unit is held in leased space — a vault, a tank farm, a
silo, a yard — which is paid for by the quarter. A holder who cannot pay has goods sold at the
bid to cover it, and a lease whose rent still cannot be paid is lost. Uninsured goods can be
lost to fire, a leak, rats or thieves; insured goods are paid for out of a pool fed by the
premiums.

Delivery is the seam between the two halves of the game: a long futures contract in one of
these four goods can ask for the goods instead of the cash, and at that quarter's close they
arrive in the holder's space.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime

from psycopg import Connection
from psycopg.rows import dict_row

from simulation import derivatives, ledger
from simulation import world_data as data
from simulation.money import BPS

log = logging.getLogger("wsbm.commodities")

MARKET = "commodity:market"            # the dealers: the other side of every trade
INSURANCE = "commodity:insurance"      # premiums in, claims out
FLOAT_BY = ledger.INVESTORS_INSTITUTIONS

GOODS = ("GOLD", "OIL", "FARM", "MATERIALS")


class CommodityError(Exception):
    """A request about goods, space or delivery the rules do not allow. The words are for the player."""


def _rows(conn: Connection, sql: str, params=()) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def _one(conn: Connection, sql: str, params=()) -> dict | None:
    rows = _rows(conn, sql, params)
    return rows[0] if rows else None


def money(kobo: int) -> str:
    return f"₦{kobo / 100:,.0f}"


def _whole(value, least: int = 1) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= least


# ---------------------------------------------------------------------------
# The catalogue
# ---------------------------------------------------------------------------

def goods(conn: Connection) -> list[dict]:
    return _rows(conn, "SELECT * FROM commodity_goods ORDER BY array_position(ARRAY['GOLD','OIL','FARM','MATERIALS'], code)")


def good(conn: Connection, code: str) -> dict:
    g = _one(conn, "SELECT * FROM commodity_goods WHERE code = %s", (code,))
    if g is None:
        raise CommodityError("There is no such good.")
    return g


def _series(g: dict) -> dict:
    """The exchange's own description of the contract this good's price is fixed to."""
    return {"underlying": g["underlying"], "company_id": None, "kind": "future"}


# ---------------------------------------------------------------------------
# Prices: the contract, divided by the units
# ---------------------------------------------------------------------------

def spot(conn: Connection, code: str, now: datetime) -> int:
    """Today's price of one unit of a good, in kobo."""
    g = good(conn, code)
    series = _series(g)
    try:
        level = derivatives.spot(conn, series, now)
        whole = derivatives.value_of(conn, series, level)
    except Exception:                       # (a world whose economy has not started yet)
        log.debug("no price for %s yet", code, exc_info=True)
        return 0
    return max(whole // int(g["units_per_contract"]), 1)


def quote(conn: Connection, code: str, now: datetime) -> dict:
    """What the dealers will sell at, what they will buy at, and what they think it is worth."""
    g = good(conn, code)
    mid = spot(conn, code, now)
    half = max(mid * int(g["spread_bps"]) // BPS, 1)
    return {"spot": mid, "bid": max(mid - half, 1), "ask": mid + half}


def price_for(conn: Connection, code: str, side: str, now: datetime) -> int:
    q = quote(conn, code, now)
    return q["ask"] if side == "buy" else q["bid"]


def value_of(conn: Connection, code: str, units: int, now: datetime, *, side: str = "sell") -> int:
    """What a number of units is worth to the person holding them: the bid, since that is what they would get."""
    return int(units) * price_for(conn, code, side, now)


def curve(conn: Connection, now: datetime) -> dict:
    """The four goods, with today's price and the futures curves the exchange lists for each.

    Contango is where the far month is dearer than the near one, because it costs money to keep
    the goods safe in between; backwardation is where the goods are scarce now and expected to be
    easier later, and the near month is dearer."""
    out = {}
    for g in goods(conn):
        rows = _rows(conn, """
            SELECT s.expiry_period, s.mark, s.id,
                   (SELECT t.price FROM derivative_trades t WHERE t.series_id = s.id
                    ORDER BY t.at DESC, t.id DESC LIMIT 1) AS last
            FROM derivative_series s
            WHERE s.kind = 'future' AND s.underlying = %s AND s.status = 'open'
            ORDER BY s.expiry_period""", (g["underlying"],))
        points = []
        for r in rows:
            price = r["last"] or r["mark"]
            if price:
                points.append({"expiry": r["expiry_period"], "series_id": r["id"], "price": int(price)})
        shaped = "flat"
        if len(points) >= 2:
            shaped = "contango" if points[-1]["price"] > points[0]["price"] else (
                "backwardation" if points[-1]["price"] < points[0]["price"] else "flat")
        out[g["code"]] = {"good": g, **quote(conn, g["code"], now), "points": points, "shape": shaped}
    return out


# ---------------------------------------------------------------------------
# The dealers' stock, and their account
# ---------------------------------------------------------------------------

def _escrow(conn: Connection, code: str, name: str):
    row = _one(conn, "SELECT id FROM ledger_accounts WHERE code = %s", (code,))
    if row:
        return row["id"]
    account = ledger.create_account(conn, kind="escrow", name=name, code=code)
    return account


def market_account(conn: Connection):
    """The dealers. On first use the pension funds put a float behind them, as a real transfer, so the
    market can bid for goods from its first day instead of waiting for somebody to sell to it."""
    row = _one(conn, "SELECT id FROM ledger_accounts WHERE code = %s", (MARKET,))
    if row:
        return row["id"]
    account = ledger.create_account(conn, kind="escrow", name="The goods market's dealers",
                                    code=MARKET)
    funds = _one(conn, "SELECT id FROM ledger_accounts WHERE code = %s", (FLOAT_BY,))
    if funds:
        available = max(ledger.balance(conn, funds["id"]), 0)
        amount = min(data.COMMODITY_MARKET_FLOAT, available // 10)
        if amount > 0:
            ledger.transfer(conn, payer=funds["id"], receiver=account, amount=amount, kind="commodity_float",
                            memo="The pension funds stand behind the goods market: a float for the dealers")
    return account


def insurance_account(conn: Connection):
    return _escrow(conn, INSURANCE, "The goods insurance pool")


def stock(conn: Connection, code: str) -> int:
    row = _one(conn, "SELECT stock FROM commodity_market WHERE good = %s", (code,))
    return int(row["stock"]) if row else 0


# ---------------------------------------------------------------------------
# Space
# ---------------------------------------------------------------------------

def leases(conn: Connection, account, code: str | None = None, *, open_only: bool = True) -> list[dict]:
    sql = ("SELECT * FROM commodity_storage WHERE account = %s"
           + (" AND status = 'open'" if open_only else "")
           + (" AND good = %s" if code else "")
           + " ORDER BY id")
    params = [account, code] if code else [account]
    out = _rows(conn, sql, params)
    for lease in out:
        lease["held"] = held_in(conn, lease["id"])
    return out


def held_in(conn: Connection, storage_id) -> int:
    row = _one(conn, "SELECT coalesce(sum(units), 0)::bigint AS n FROM commodity_holdings WHERE storage_id = %s", (storage_id,))
    return int(row["n"])


def held(conn: Connection, account, code: str) -> int:
    row = _one(conn, "SELECT coalesce(sum(units), 0)::bigint AS n FROM commodity_holdings WHERE account = %s AND good = %s",
               (account, code))
    return int(row["n"])


def room(conn: Connection, account, code: str) -> int:
    """How many more units of a good the account could put in the space it has."""
    total = 0
    for lease in leases(conn, account, code):
        total += max(int(lease["capacity"]) - int(lease["held"]), 0)
    return total


def lease_cost(conn: Connection, code: str, spaces: int, now: datetime) -> dict:
    """What it costs to take a lease: one quarter's rent on the space, paid up front."""
    g = good(conn, code)
    if not _whole(spaces):
        raise CommodityError("A lease is taken in whole units of space.")
    units = spaces * int(g["units_per_space"])
    value = units * spot(conn, code, now)
    lease = value * int(g["rent_bps"]) // BPS
    return {"spaces": spaces, "units": units, "value": value, "lease": max(lease, 1)}


def open_lease(conn: Connection, account, code: str, spaces: int, insured: bool, period: int, now: datetime) -> dict:
    """Lease space for a good. The lease is paid for once, and rented by the quarter after that."""
    g = good(conn, code)
    cost = lease_cost(conn, code, spaces, now)
    with conn.transaction():
        if ledger.balance(conn, account) < cost["lease"]:
            raise CommodityError(f"A lease on {spaces} x {g['space_name']} costs {money(cost['lease'])}, "
                                 f"and you do not have it.")
        ledger.transfer(conn, payer=account, receiver=market_account(conn), amount=cost["lease"],
                        kind="commodity_lease", memo=f"A lease on {spaces} x {g['space_name']} for {g['name']}", period=period)
        row = _one(conn, """INSERT INTO commodity_storage (account, good, capacity, insured, lease_paid, opened_period, opened_at)
                            VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING *""",
                   (account, code, cost["units"], bool(insured), cost["lease"], period, now))
    return row


def set_insured(conn: Connection, account, storage_id: int, insured: bool) -> dict:
    lease = _one(conn, "SELECT * FROM commodity_storage WHERE id = %s AND account = %s AND status = 'open'", (storage_id, account))
    if lease is None:
        raise CommodityError("There is no such lease of yours.")
    conn.execute("UPDATE commodity_storage SET insured = %s WHERE id = %s", (bool(insured), storage_id))
    lease["insured"] = bool(insured)
    return lease


def close_lease(conn: Connection, account, storage_id: int, now: datetime, *, reason: str = "given up") -> dict:
    """Give up a lease. Only an empty one: goods are sold, not thrown away."""
    lease = _one(conn, "SELECT * FROM commodity_storage WHERE id = %s AND account = %s AND status = 'open'",
                 (storage_id, account))
    if lease is None:
        raise CommodityError("There is no such lease of yours.")
    if held_in(conn, storage_id):
        raise CommodityError("That space still holds goods. Sell them first; nothing is thrown away.")
    conn.execute("UPDATE commodity_storage SET status = 'closed', close_reason = %s, closed_at = %s WHERE id = %s",
                 (reason, now, storage_id))
    return lease


# ---------------------------------------------------------------------------
# What is held
# ---------------------------------------------------------------------------

def holdings(conn: Connection, account, code: str | None = None) -> list[dict]:
    sql = ("SELECT h.*, s.insured, s.capacity, g.name, g.unit, g.unit_plural, g.unit_word, g.units_per_contract"
           " FROM commodity_holdings h JOIN commodity_storage s ON s.id = h.storage_id"
           " JOIN commodity_goods g ON g.code = h.good WHERE h.account = %s")
    params: list = [account]
    if code:
        sql += " AND h.good = %s"
        params.append(code)
    return _rows(conn, sql + " ORDER BY h.id", params)


def book_value(conn: Connection, account, now: datetime) -> int:
    """What the account's goods are worth now, at the bid — what they would fetch today."""
    total = 0
    prices: dict = {}
    for row in _rows(conn, "SELECT good, sum(units)::bigint AS units FROM commodity_holdings WHERE account = %s GROUP BY good",
                     (account,)):
        code = row["good"]
        if code not in prices:
            prices[code] = quote(conn, code, now)["bid"]
        total += int(row["units"]) * prices[code]
    return total


def position(conn: Connection, account, now: datetime) -> dict:
    """Everything a player's goods amount to, in one shape a screen can draw."""
    prices = {g["code"]: quote(conn, g["code"], now) for g in goods(conn)}
    lines = []
    total_now = total_cost = 0
    for row in _rows(conn, """SELECT h.good, sum(h.units)::bigint AS units, sum(h.cost)::bigint AS cost
                              FROM commodity_holdings h WHERE h.account = %s GROUP BY h.good ORDER BY h.good""", (account,)):
        q = prices[row["good"]]
        now_value = int(row["units"]) * q["bid"]
        total_now += now_value
        total_cost += int(row["cost"])
        lines.append({**row, "bid": q["bid"], "ask": q["ask"], "spot": q["spot"], "value": now_value,
                      "change": now_value - int(row["cost"])})
    return {"lines": lines, "value": total_now, "cost": total_cost, "change": total_now - total_cost,
            "prices": prices, "leases": leases(conn, account)}


# ---------------------------------------------------------------------------
# Buying and selling
# ---------------------------------------------------------------------------

def _space_for(conn: Connection, account, code: str, units: int, now: datetime) -> dict:
    """The lease the goods go into: the one with the most room. Raises if there is not enough."""
    for lease in sorted(leases(conn, account, code),
                        key=lambda l: int(l["capacity"]) - int(l["held"]), reverse=True):
        free = int(lease["capacity"]) - int(lease["held"])
        if free >= units:
            return lease
    g = good(conn, code)
    needed = -(-units // int(g["units_per_space"]))          # rounded up
    cost = lease_cost(conn, code, needed, now)
    have = room(conn, account, code)
    raise CommodityError(
        f"You have room for {have:,} {g['unit_plural']} and this is {units:,}. "
        f"Lease {needed:,} x {g['space_name']} for {money(cost['lease'])} a quarter first.")


def buy(conn: Connection, account, code: str, units: int, period: int, now: datetime, *, player_id=None) -> dict:
    """Buy goods from the dealers at their ask, into the space already leased for them."""
    g = good(conn, code)
    units = int(units)
    if units < int(g["least_units"]):
        raise CommodityError(f"The smallest purchase of {g['name']} is {g['least_units']:,} {g['unit_plural']}.")
    with conn.transaction():
        dealers = market_account(conn)
        row = _one(conn, "SELECT stock FROM commodity_market WHERE good = %s FOR UPDATE", (code,))
        available = int(row["stock"]) if row else 0
        if available < units:
            raise CommodityError(f"The market has only {available:,} {g['unit_plural']} of {g['name']} left to sell. "
                                 f"The dealers are out until somebody sells some.")
        lease = _space_for(conn, account, code, units, now)
        price = price_for(conn, code, "buy", now)
        cost = units * price
        if ledger.balance(conn, account) < cost:
            raise CommodityError(f"That is {units:,} {g['unit_plural']} of {g['name']} at {money(price)} each: "
                                 f"{money(cost)}, and you do not have it.")
        try:
            ledger.transfer(conn, payer=account, receiver=dealers, amount=cost, kind="commodity_buy",
                            memo=f"{units:,} {g['unit_plural']} of {g['name']} at {money(price)}", period=period)
        except ledger.InsufficientFunds as error:
            raise CommodityError("You cannot pay for that.") from error
        conn.execute("UPDATE commodity_market SET stock = stock - %s, updated_at = %s WHERE good = %s", (units, now, code))
        holding = _one(conn, """INSERT INTO commodity_holdings (account, good, storage_id, units, cost, bought_period, bought_at)
                                VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING *""",
                       (account, code, lease["id"], units, cost, period, now))
        conn.execute("INSERT INTO commodity_trades (account, good, side, units, price, storage_id, period, at)"
                     " VALUES (%s, %s, 'buy', %s, %s, %s, %s, %s)", (account, code, units, price, lease["id"], period, now))
    return {"holding": holding, "units": units, "price": price, "cost": cost, "lease": lease["id"]}


def sell(conn: Connection, account, code: str, units: int, period: int, now: datetime, *, player_id=None) -> dict:
    """Sell goods back to the dealers at their bid, oldest lot first."""
    g = good(conn, code)
    units = int(units)
    if not _whole(units):
        raise CommodityError("You sell whole units.")
    with conn.transaction():
        have = held(conn, account, code)
        if units > have:
            raise CommodityError(f"You hold {have:,} {g['unit_plural']} of {g['name']}, not {units:,}.")
        price = price_for(conn, code, "sell", now)
        proceeds = units * price
        dealers = market_account(conn)
        if ledger.balance(conn, dealers) < proceeds:
            raise CommodityError("The dealers have no cash to bid with just now. Try again later, or sell less.")
        left = units
        sold_from = []
        for lot in _rows(conn, "SELECT * FROM commodity_holdings WHERE account = %s AND good = %s ORDER BY id FOR UPDATE",
                         (account, code)):
            if left <= 0:
                break
            take = min(int(lot["units"]), left)
            if take <= 0:
                continue
            left -= take
            sold_from.append({"storage_id": lot["storage_id"], "units": take})
            if take == int(lot["units"]):
                conn.execute("DELETE FROM commodity_holdings WHERE id = %s", (lot["id"],))
            else:
                cost = int(lot["cost"]) - int(lot["cost"]) * take // int(lot["units"])
                conn.execute("UPDATE commodity_holdings SET units = units - %s, cost = %s WHERE id = %s",
                             (take, cost, lot["id"]))
        try:
            ledger.transfer(conn, payer=dealers, receiver=account, amount=proceeds, kind="commodity_sell",
                            memo=f"{units:,} {g['unit_plural']} of {g['name']} at {money(price)}", period=period)
        except ledger.InsufficientFunds as error:                  # (the balance was checked under lock above)
            raise CommodityError("The dealers could not pay for that just now.") from error
        conn.execute("UPDATE commodity_market SET stock = stock + %s, updated_at = %s WHERE good = %s", (units, now, code))
        conn.execute("INSERT INTO commodity_trades (account, good, side, units, price, period, at)"
                     " VALUES (%s, %s, 'sell', %s, %s, %s, %s)", (account, code, units, price, period, now))
    return {"units": units, "price": price, "proceeds": proceeds, "from": sold_from}


# ---------------------------------------------------------------------------
# Delivery: when a future stops being a bet
# ---------------------------------------------------------------------------

def ask_delivery(conn: Connection, account, position_id: int, now: datetime) -> dict:
    """Ask for the goods instead of the cash when this contract's quarter closes."""
    p = _one(conn, "SELECT p.*, s.kind, s.underlying, s.expiry_period FROM derivative_positions p"
                   " JOIN derivative_series s ON s.id = p.series_id WHERE p.id = %s AND p.account = %s AND p.status = 'open'",
             (position_id, account))
    if p is None:
        raise CommodityError("There is no such open contract of yours.")
    g = _good_for(conn, p["underlying"])
    if g is None:
        raise CommodityError("Only gold, oil, farm produce and building materials can be delivered against.")
    if p["kind"] != "future" or p["side"] != "long":
        raise CommodityError("Delivery is taken by a long futures contract: a contract to buy the goods.")
    conn.execute("UPDATE derivative_positions SET take_delivery = true WHERE id = %s", (position_id,))
    return {"position_id": position_id, "good": g["code"], "units": int(p["contracts"]) * int(g["units_per_contract"])}


def withdraw_delivery(conn: Connection, account, position_id: int) -> dict:
    p = _one(conn, "SELECT * FROM derivative_positions WHERE id = %s AND account = %s AND status = 'open'",
             (position_id, account))
    if p is None:
        raise CommodityError("There is no such open contract of yours.")
    conn.execute("UPDATE derivative_positions SET take_delivery = false WHERE id = %s", (position_id,))
    return {"position_id": position_id}


def _good_for(conn: Connection, underlying: str) -> dict | None:
    return _one(conn, "SELECT * FROM commodity_goods WHERE underlying = %s", (underlying,))


def deliver(conn: Connection, period: int, now: datetime) -> dict:
    """At the quarter's close, the goods asked for arrive. The contract has already settled its last night's
    move in cash, so the holder pays the full value of the goods now, and their net cost is the price they
    took the contract at. A delivery that cannot be paid for, or has nowhere to go, is settled in cash after
    all, and the holder is told why."""
    if _one(conn, "SELECT to_regclass('commodity_holdings') IS NOT NULL AS ok")["ok"] is not True:
        return {"delivered": 0, "refused": 0}
    done = refused = 0
    # (derivatives.close has already settled every position and marked it expired; what is left is the goods.)
    for p in _rows(conn, """SELECT p.id, p.account, p.contracts, p.realised, p.status, s.underlying
                            FROM derivative_positions p JOIN derivative_series s ON s.id = p.series_id
                            WHERE p.take_delivery AND p.delivered_units = 0 AND s.expiry_period <= %s
                              AND s.kind = 'future' AND p.side = 'long' ORDER BY p.id""", (period,)):
        g = _good_for(conn, p["underlying"])
        if g is None:
            continue
        units = int(p["contracts"]) * int(g["units_per_contract"])
        try:
            with conn.transaction():
                _deliver_one(conn, p, g, units, period, now)
            done += 1
        except CommodityError as error:
            refused += 1
            conn.execute("""INSERT INTO commodity_events (account, good, kind, units, words, period, at)
                            VALUES (%s, %s, 'delivery_refused', %s, %s, %s, %s)""",
                         (p["account"], g["code"], units, str(error), period, now))
    return {"delivered": done, "refused": refused}


def _deliver_one(conn: Connection, p: dict, g: dict, units: int, period: int, now: datetime) -> None:
    price = price_for(conn, g["code"], "buy", now)
    cost = units * price
    if room(conn, p["account"], g["code"]) < units:
        raise CommodityError(
            f"No room for the {units:,} {g['unit_plural']} of {g['name']} you asked to be delivered. "
            f"The contract was settled in cash instead.")
    if ledger.balance(conn, p["account"]) < cost:
        raise CommodityError(
            f"The {units:,} {g['unit_plural']} of {g['name']} you asked for cost {money(cost)} and you do not have it. "
            f"The contract was settled in cash instead.")
    lease = _space_for(conn, p["account"], g["code"], units, now)
    dealers = market_account(conn)
    stock = _one(conn, "SELECT stock FROM commodity_market WHERE good = %s FOR UPDATE", (g["code"],))
    if int(stock["stock"]) < units:
        raise CommodityError(f"The dealers have no {g['name']} to deliver. The contract was settled in cash instead.")
    ledger.transfer(conn, payer=p["account"], receiver=dealers, amount=cost, kind="commodity_delivery",
                    memo=f"{units:,} {g['unit_plural']} of {g['name']} delivered at {money(price)}", period=period)
    conn.execute("UPDATE commodity_market SET stock = stock - %s, updated_at = %s WHERE good = %s", (units, now, g["code"]))
    conn.execute("""INSERT INTO commodity_holdings (account, good, storage_id, units, cost, bought_period, bought_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                 (p["account"], g["code"], lease["id"], units, cost, period, now))
    conn.execute("INSERT INTO commodity_trades (account, good, side, units, price, storage_id, period, at)"
                 " VALUES (%s, %s, 'buy', %s, %s, %s, %s, %s)", (p["account"], g["code"], units, price, lease["id"], period, now))
    conn.execute("UPDATE derivative_positions SET delivered_units = %s WHERE id = %s", (units, p["id"]))
    conn.execute("""INSERT INTO commodity_events (account, good, kind, units, amount, words, period, at)
                    VALUES (%s, %s, 'delivery', %s, %s, %s, %s, %s)""",
                 (p["account"], g["code"], units, cost,
                  f"Delivered: {units:,} {g['unit_plural']} of {g['name']} at {money(price)} each", period, now))


# ---------------------------------------------------------------------------
# The quarter: prices on the record, rent, insurance, and what nobody chose
# ---------------------------------------------------------------------------

def _chance(salt: str, period: int, lease_id) -> int:
    """A number from nothing, the same every time it is asked: no two quarters get the same luck, and a
    quarter closed twice cannot be lucky twice."""
    digest = hashlib.blake2b(f"{salt}:{period}:{lease_id}".encode(), digest_size=8).digest()
    return int.from_bytes(digest, "big") % BPS


def record_prices(conn: Connection, period: int, now: datetime) -> int:
    """Read the four prices onto the permanent record, with the quarter before beside them."""
    written = 0
    for g in goods(conn):
        q = quote(conn, g["code"], now)
        if q["spot"] <= 0:
            continue
        before = _one(conn, "SELECT spot FROM commodity_prices WHERE good = %s AND period < %s ORDER BY period DESC LIMIT 1",
                      (g["code"], period))
        conn.execute("""INSERT INTO commodity_prices (period, good, spot, bid, ask, previous, recorded_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s) ON CONFLICT (period, good) DO NOTHING""",
                     (period, g["code"], q["spot"], q["bid"], q["ask"], before["spot"] if before else None, now))
        written += 1
    return written


def charge_space(conn: Connection, period: int, now: datetime) -> dict:
    """Rent and insurance for the quarter, at the quarter's prices.

    Rent is charged on the space leased, whether it is full or not: empty space costs money too. A holder
    who cannot pay has goods sold at the bid to cover it; if that is still not enough, the lease is lost and
    the goods in it go to the dealers."""
    taken = insured = lost = 0
    dealers = market_account(conn)
    pool = insurance_account(conn)
    for lease in _rows(conn, "SELECT * FROM commodity_storage WHERE status = 'open' ORDER BY id"):
        g = good(conn, lease["good"])
        price = spot(conn, lease["good"], now)
        if price <= 0:
            continue
        with conn.transaction():
            lease = _one(conn, "SELECT * FROM commodity_storage WHERE id = %s AND status = 'open' FOR UPDATE", (lease["id"],))
            if lease is None:
                continue
            rent = int(lease["capacity"]) * price * int(g["rent_bps"]) // BPS
            paid = ledger.pay_up_to(conn, payer=lease["account"], receiver=dealers, wanted=rent,
                                    kind="commodity_rent", memo=f"Rent on {g['space_name']}, {period}: {g['name']}",
                                    period=period)
            taken += paid
            conn.execute("""INSERT INTO commodity_events (account, good, kind, amount, units, words, period, at)
                            VALUES (%s, %s, 'rent', %s, 0, %s, %s, %s)""",
                         (lease["account"], lease["good"], paid, f"Rent on the space: {money(paid)}", period, now))
            if paid < rent:
                _cover_rent(conn, lease, g, price, rent - paid, period, now)
                still = _one(conn, "SELECT status FROM commodity_storage WHERE id = %s", (lease["id"],))["status"]
                if still == "lost":
                    lost += 1
                    continue
            if lease["insured"]:
                units = held_in(conn, lease["id"])
                premium = 0
                if units:
                    premium = units * price * int(g["insurance_bps"]) // BPS
                    paid_ins = ledger.pay_up_to(conn, payer=lease["account"], receiver=pool, wanted=premium,
                                                kind="commodity_insurance", memo=f"Insurance on {g['name']}, {period}",
                                                period=period)
                    insured += paid_ins
                    conn.execute("""INSERT INTO commodity_events (account, good, kind, amount, units, words, period, at)
                                    VALUES (%s, %s, 'insurance', %s, 0, %s, %s, %s)""",
                                 (lease["account"], lease["good"], paid_ins,
                                  f"Insurance on the goods: {money(paid_ins)}", period, now))
                    if paid_ins < premium:                  # (unpaid insurance is no insurance)
                        conn.execute("UPDATE commodity_storage SET insured = false WHERE id = %s", (lease["id"],))
    return {"rent": taken, "insurance": insured, "lost": lost}


def _cover_rent(conn: Connection, lease: dict, g: dict, price: int, short: int, period: int, now: datetime) -> None:
    """Sell the holder's goods at the bid to pay rent that could not be paid, and lose the lease if it is still not enough."""
    dealers = market_account(conn)
    left = short
    for lot in _rows(conn, "SELECT * FROM commodity_holdings WHERE storage_id = %s ORDER BY id FOR UPDATE", (lease["id"],)):
        if left <= 0:
            break
        bid = price_for(conn, lease["good"], "sell", now)
        need_units = min(int(lot["units"]), -(-left // max(bid, 1)))
        if need_units <= 0:
            continue
        pay = min(need_units * bid, left)
        # Goods are only taken against money: if the dealers cannot pay, the goods stay where they are.
        if pay <= 0 or ledger.balance(conn, dealers) < pay:
            break
        ledger.transfer(conn, payer=dealers, receiver=lease["account"], amount=pay, kind="commodity_sell",
                        memo=f"Goods sold to pay the rent on {g['name']}", period=period)
        left -= pay
        if need_units == int(lot["units"]):
            conn.execute("DELETE FROM commodity_holdings WHERE id = %s", (lot["id"],))
        else:
            cost = int(lot["cost"]) - int(lot["cost"]) * need_units // int(lot["units"])
            conn.execute("UPDATE commodity_holdings SET units = units - %s, cost = %s WHERE id = %s",
                         (need_units, cost, lot["id"]))
        conn.execute("UPDATE commodity_market SET stock = stock + %s, updated_at = %s WHERE good = %s",
                     (need_units, now, lease["good"]))
    if left > 0:
        seized = held_in(conn, lease["id"])
        if seized:
            conn.execute("UPDATE commodity_market SET stock = stock + %s, updated_at = %s WHERE good = %s",
                         (seized, now, lease["good"]))
            conn.execute("DELETE FROM commodity_holdings WHERE storage_id = %s", (lease["id"],))
        conn.execute("UPDATE commodity_storage SET status = 'lost', close_reason = %s, closed_at = %s WHERE id = %s",
                     (f"Rent of {money(left)} could not be paid", now, lease["id"]))
        conn.execute("""INSERT INTO commodity_events (account, good, kind, amount, units, words, period, at)
                        VALUES (%s, %s, 'seized', %s, %s, %s, %s, %s)""",
                     (lease["account"], lease["good"], left, seized,
                      f"The lease was lost: rent of {money(left)} could not be paid, and {seized:,} {g['unit_plural']} went with it",
                      period, now))


def damage(conn: Connection, period: int, now: datetime) -> dict:
    """What nobody chose: fire in a vault, a leaking tank, rats in a silo, thieves in a yard. Insured goods are
    paid for out of the pool the premiums built; uninsured goods are simply gone."""
    hurt = paid_out = 0
    pool = insurance_account(conn)
    for lease in _rows(conn, "SELECT * FROM commodity_storage WHERE status = 'open' ORDER BY id"):
        g = good(conn, lease["good"])
        if _chance("damage", period, lease["id"]) >= int(g["loss_bps"]):
            continue
        with conn.transaction():
            units = held_in(conn, lease["id"])
            if not units:
                continue
            gone = max(units * int(g["lost_share_bps"]) // BPS, 1)
            price = spot(conn, lease["good"], now)
            # what goes is taken from the newest lot first, so an older purchase keeps its own history
            left = gone
            for lot in _rows(conn, "SELECT * FROM commodity_holdings WHERE storage_id = %s ORDER BY id DESC FOR UPDATE", (lease["id"],)):
                if left <= 0:
                    break
                take = min(int(lot["units"]), left)
                left -= take
                if take == int(lot["units"]):
                    conn.execute("DELETE FROM commodity_holdings WHERE id = %s", (lot["id"],))
                else:
                    cost = int(lot["cost"]) - int(lot["cost"]) * take // int(lot["units"])
                    conn.execute("UPDATE commodity_holdings SET units = units - %s, cost = %s WHERE id = %s",
                                 (take, cost, lot["id"]))
            hurt += 1
            value = gone * price
            claim = 0
            if lease["insured"]:
                claim = ledger.pay_up_to(conn, payer=pool, receiver=lease["account"], wanted=value,
                                         kind="commodity_claim", memo=f"A claim for {g['name']} lost, {period}",
                                         period=period)
                paid_out += claim
            conn.execute("""INSERT INTO commodity_events (account, good, kind, amount, units, words, period, at)
                            VALUES (%s, %s, 'loss', %s, %s, %s, %s, %s)""",
                         (lease["account"], lease["good"], claim, gone,
                          (f"{gone:,} {g['unit_plural']} of {g['name']} lost, and the insurance paid {money(claim)}"
                           if lease["insured"] else
                           f"{gone:,} {g['unit_plural']} of {g['name']} lost, uninsured"), period, now))
            if lease["insured"] and claim < value:
                conn.execute("UPDATE commodity_storage SET insured = false WHERE id = %s", (lease["id"],))
    return {"hurt": hurt, "paid": paid_out}


def close(conn: Connection, period: int, now: datetime) -> dict:
    """The quarter's close for goods: the prices onto the record, delivery, rent and insurance, then the damage."""
    if _one(conn, "SELECT to_regclass('commodity_goods') IS NOT NULL AS ok")["ok"] is not True:
        return {}
    done = deliver(conn, period, now)
    space = charge_space(conn, period, now)
    harm = damage(conn, period, now)
    record_prices(conn, period, now)
    return {**done, **space, **harm}


def check_books(conn: Connection) -> list[str]:
    """Anything the goods have done that does not add up."""
    if _one(conn, "SELECT to_regclass('commodity_goods') IS NOT NULL AS ok")["ok"] is not True:
        return []
    out: list[str] = []
    for row in _rows(conn, """SELECT h.good, sum(h.units)::bigint AS units FROM commodity_holdings h
                              GROUP BY h.good"""):
        if int(row["units"]) <= 0:
            out.append(f"Goods: {row['good']} is held as {row['units']} units.")
    for row in _rows(conn, "SELECT good, stock FROM commodity_market WHERE stock < 0"):
        out.append(f"Goods: the dealers' stock of {row['good']} has gone below zero ({row['stock']}).")
    for row in _rows(conn, """SELECT s.id, s.capacity, coalesce(sum(h.units), 0)::bigint AS units
                              FROM commodity_storage s LEFT JOIN commodity_holdings h ON h.storage_id = s.id
                              WHERE s.status = 'open' GROUP BY s.id, s.capacity HAVING coalesce(sum(h.units), 0) > s.capacity"""):
        out.append(f"Goods: lease {row['id']} holds {row['units']} in space for {row['capacity']}.")
    for row in _rows(conn, """SELECT h.id FROM commodity_holdings h LEFT JOIN commodity_storage s ON s.id = h.storage_id
                              WHERE s.id IS NULL OR s.status <> 'open'"""):
        out.append(f"Goods: a holding ({row['id']}) sits in space that is not open.")
    return out


# ---------------------------------------------------------------------------
# What the rest of the game asks about goods
# ---------------------------------------------------------------------------

def held_value(conn: Connection, account, now: datetime) -> int:
    if _one(conn, "SELECT to_regclass('commodity_holdings') IS NOT NULL AS ok")["ok"] is not True:
        return 0
    return book_value(conn, account, now)


def _players_goods(conn: Connection) -> dict:
    out = {}
    if _one(conn, "SELECT to_regclass('commodity_holdings') IS NOT NULL AS ok")["ok"] is not True:
        return out
    now = _one(conn, "SELECT now() AS n")["n"]
    for r in _rows(conn, "SELECT DISTINCT h.account FROM commodity_holdings h"):
        out[r["account"]] = (0, held_value(conn, r["account"], now))
    return out


def _register() -> None:
    from simulation import marketview
    if _players_goods not in marketview._OTHER_HOLDINGS:
        marketview._OTHER_HOLDINGS.append(_players_goods)


_register()
