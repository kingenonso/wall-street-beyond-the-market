"""The gap stage, Part 2: property funds.

A property fund owns buildings and cash, and is divided into units. A unit is worth the fund's value (its buildings at
today's prices, plus its cash) divided by the units in issue. Anybody (a player, an empire) may buy units, paying 1% above
their value, or sell them back, getting 1% below; the difference stays in the fund, so nobody joining or leaving takes
from the others. A seller is paid from the fund's cash; when it has not enough, they must wait for the manager to sell a
building.

One fund is run by the computer from the start: the Nigeria Property Trust, seeded by the pension funds, which buys
buildings from the property companies and sells when it needs cash.

An Asset Manager of Level 20 or above may open one fund of their own, under rules like a pension fund's: a fee of at
most 2% of the fund a year, paid to the manager each quarter; no building more than 30% of the fund; at least 10% kept in
cash; the fund buys and sells at the Auction House, and never from or to its manager or the manager's empire.
"""

from __future__ import annotations

from datetime import datetime

from psycopg import Connection
from psycopg.rows import dict_row

from simulation import careers, clock, ledger
from simulation import world_data as data
from simulation.money import BPS, naira

UNIT = 1_000_000                  # unit prices in millionths of a kobo
FIRST_PRICE = 100 * UNIT          # the first unit costs ₦1
TRUST_NAME = "Nigeria Property Trust"


class FundError(Exception):
    """A request about a property fund the rules do not allow."""


def _rows(conn: Connection, sql: str, params=()) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def _one(conn: Connection, sql: str, params=()) -> dict | None:
    rows = _rows(conn, sql, params)
    return rows[0] if rows else None


def ready(conn: Connection) -> bool:
    return _one(conn, "SELECT to_regclass('property_funds') IS NOT NULL AS ok")["ok"] is True


def _money(kobo: int) -> str:
    return f"₦{kobo / 100:,.0f}"


def _state(conn: Connection, now: datetime) -> dict:
    try:
        careers.books_open(conn, now)
    except careers.CareerError as closing:
        raise FundError(str(closing)) from None
    return careers.world_now(conn, now)


def buildings_worth(conn: Connection, account) -> int:
    from simulation import property as prop
    rate = prop.policy_rate(conn)
    ds = prop.districts(conn)
    return sum(prop.value(p, ds[p["district_id"]], rate) * p["share_bps"] // BPS
               for p in _rows(conn, "SELECT p.*, h.share_bps FROM properties p JOIN property_holdings h ON h.property_id = p.id WHERE h.account_id = %s",
                              (account,)))


def worth(conn: Connection, fund: dict) -> dict:
    """The fund's value: its buildings at today's prices, its cash (and cash held behind its bids), less any tax owed."""
    from simulation import property as prop
    cash = ledger.balance(conn, fund["account_id"])
    held = _one(conn, "SELECT coalesce(sum(held), 0)::bigint AS h FROM auction_bids WHERE bidder = %s AND status = 'live'", (fund["account_id"],))["h"]
    eq = prop.equity_of(conn, fund["account_id"])
    return {"cash": cash, "held": held, "buildings": eq["value"], "owed": eq["owed"], "total": cash + held + eq["equity"]}


def unit_price(fund: dict, total: int, *, side: str | None = None) -> int:
    """A unit's value in millionths of a kobo; buying pays 1% more and selling gets 1% less."""
    base = FIRST_PRICE if fund["units"] <= 0 or total <= 0 else max(total * UNIT // fund["units"], 1)
    if side == "buy":
        return base * (BPS + data.PROPERTY_FUND_SPREAD_BPS) // BPS + 1
    if side == "sell":
        return base * (BPS - data.PROPERTY_FUND_SPREAD_BPS) // BPS
    return base


def _fund(conn: Connection, fund_id, *, lock: bool = False) -> dict:
    fund = _one(conn, "SELECT * FROM property_funds WHERE id = %s AND status = 'open'" + (" FOR UPDATE" if lock else ""), (fund_id,))
    if fund is None:
        raise FundError("There is no such property fund.")
    return fund


# ---------------------------------------------------------------------------
# Units
# ---------------------------------------------------------------------------

def buy_units(conn: Connection, account, fund_id: int, amount: int, now: datetime) -> dict:
    with conn.transaction():
        state = _state(conn, now)
        fund = _fund(conn, fund_id, lock=True)
        if not isinstance(amount, int) or isinstance(amount, bool) or amount <= 0:
            raise FundError("Name how much to put in.")
        if account == fund["account_id"]:
            raise FundError("A fund does not buy its own units.")
        total = worth(conn, fund)["total"]
        if fund["units"] <= 0 and total > 0:
            # Value left in a fund nobody holds units in (rent, after the last holder left) belongs to its manager (the
            # pension funds, for the trust): units are issued for it first, so a newcomer cannot take it for nothing.
            owner = ledger.player_account_id(conn, fund["manager"]) if fund["manager"] else ledger.account_id(conn, ledger.INVESTORS_INSTITUTIONS)
            left = total * UNIT // FIRST_PRICE
            conn.execute("INSERT INTO property_fund_units (fund_id, account, units) VALUES (%s, %s, %s) ON CONFLICT (fund_id, account)"
                         " DO UPDATE SET units = property_fund_units.units + EXCLUDED.units", (fund_id, owner, left))
            conn.execute("UPDATE property_funds SET units = units + %s WHERE id = %s", (left, fund_id))
            fund = {**fund, "units": fund["units"] + left}
        price = unit_price(fund, total, side="buy")
        units = amount * UNIT // price
        if units <= 0:
            raise FundError("That is less than one unit.")
        cost = -(-units * price // UNIT)
        try:
            ledger.transfer(conn, payer=account, receiver=fund["account_id"], amount=cost, kind="fund_units",
                            memo=f"{units:,} units of {fund['name']}", period=state["period"])
        except ledger.InsufficientFunds:
            raise FundError(f"That costs {_money(cost)}.") from None
        conn.execute("INSERT INTO property_fund_units (fund_id, account, units) VALUES (%s, %s, %s) ON CONFLICT (fund_id, account)"
                     " DO UPDATE SET units = property_fund_units.units + EXCLUDED.units", (fund_id, account, units))
        conn.execute("UPDATE property_funds SET units = units + %s WHERE id = %s", (units, fund_id))
        return {"units": units, "cost": cost}


def sell_units(conn: Connection, account, fund_id: int, units: int, now: datetime) -> dict:
    with conn.transaction():
        state = _state(conn, now)
        fund = _fund(conn, fund_id, lock=True)
        mine = _one(conn, "SELECT units FROM property_fund_units WHERE fund_id = %s AND account = %s FOR UPDATE", (fund_id, account))
        if not isinstance(units, int) or isinstance(units, bool) or units <= 0:
            raise FundError("Name how many units.")
        if mine is None or mine["units"] < units:
            raise FundError("You do not hold that many units.")
        value = units * unit_price(fund, worth(conn, fund)["total"], side="sell") // UNIT
        cash = ledger.balance(conn, fund["account_id"])
        if value > cash:
            raise FundError(f"The fund has {_money(cash)} in cash today: sell fewer units, or wait for it to sell a building.")
        ledger.transfer(conn, payer=fund["account_id"], receiver=account, amount=value, kind="fund_units",
                        memo=f"{units:,} units of {fund['name']} sold back", period=state["period"])
        conn.execute("UPDATE property_fund_units SET units = units - %s WHERE fund_id = %s AND account = %s", (units, fund_id, account))
        conn.execute("UPDATE property_funds SET units = units - %s WHERE id = %s", (units, fund_id))
        return {"units": units, "value": value}


# ---------------------------------------------------------------------------
# A manager's own fund
# ---------------------------------------------------------------------------

def open_fund(conn: Connection, player_id, name: str, fee_bps: int, now: datetime) -> dict:
    from simulation import empires
    with conn.transaction():
        state = _state(conn, now)
        conn.execute("SELECT 1 FROM players WHERE id = %s FOR UPDATE", (player_id,))
        player = _one(conn, "SELECT build FROM players WHERE id = %s", (player_id,))
        mine = careers.career(conn, player_id, "asset_manager")
        if player["build"] != "asset_manager" or mine is None or mine["level"] < data.PROPERTY_FUND_LEVEL:
            raise FundError(f"Only an Asset Manager of Level {data.PROPERTY_FUND_LEVEL} or above may open a property fund.")
        if _one(conn, "SELECT 1 FROM property_funds WHERE manager = %s", (player_id,)):
            raise FundError("You have opened a property fund before. A manager opens one, once.")
        if _one(conn, "SELECT 1 FROM legal_records WHERE player_id = %s AND kind = 'theft'", (player_id,)):
            raise FundError("Somebody with a proved theft on their record cannot run other people's money.")
        if not isinstance(fee_bps, int) or isinstance(fee_bps, bool) or not 0 <= fee_bps <= data.PROPERTY_FUND_FEE_MOST_BPS:
            raise FundError(f"The fee is from 0% to {data.PROPERTY_FUND_FEE_MOST_BPS / 100:.0f}% of the fund a year.")
        try:
            name = empires._name_ok(conn, name)
        except empires.EmpireError:
            raise FundError("That name is taken, or is not 3 to 40 letters, numbers and spaces.") from None
        if _one(conn, "SELECT 1 FROM property_funds WHERE lower(name) = lower(%s)", (name,)):
            raise FundError("That name is taken.")
        fee = naira(data.FUND_REGISTRATION_NAIRA)
        account = ledger.create_account(conn, kind="fund", name=name)
        try:
            ledger.transfer(conn, payer=ledger.player_account_id(conn, player_id), receiver=ledger.account_id(conn, ledger.PRIZE_POOL),
                            amount=fee, kind="fund_registration", memo=f"{name}: registration of a property fund", period=state["period"])
        except ledger.InsufficientFunds:
            raise FundError(f"Registering a property fund costs {_money(fee)}, from your own cash.") from None
        row = _one(conn, "INSERT INTO property_funds (name, account_id, manager, fee_bps, opened_period, at) VALUES (%s, %s, %s, %s, %s, %s)"
                         " RETURNING *", (name, account, player_id, fee_bps, state["period"], now))
        careers._event(conn, player_id, "asset_manager", "fund_opened", f"Opened the property fund {name}.", now)
        return {"fund_id": row["id"], "name": name}


def _managed(conn: Connection, manager_id) -> dict:
    fund = _one(conn, "SELECT * FROM property_funds WHERE manager = %s AND status = 'open' FOR UPDATE", (manager_id,))
    if fund is None:
        raise FundError("You manage no property fund.")
    return fund


def _manager_sides(conn: Connection, manager_id) -> set:
    """The manager's own account and their empire's: the fund never deals with them."""
    sides = {ledger.player_account_id(conn, manager_id)}
    seat = _one(conn, "SELECT e.account_id FROM empire_seats s JOIN empires e ON e.id = s.empire_id WHERE s.player_id = %s", (manager_id,))
    if seat:
        sides.add(seat["account_id"])
    return sides


def bid(conn: Connection, manager_id, auction_id: int, limit: int, now: datetime) -> dict:
    """The manager bids for a building at the Auction House with the fund's cash, inside the fund's rules."""
    from simulation import auctions
    from simulation import property as prop
    with conn.transaction():
        _state(conn, now)
        fund = _managed(conn, manager_id)
        a = _one(conn, "SELECT * FROM auctions WHERE id = %s", (auction_id,))
        if a is None or a["property_id"] is None:
            raise FundError("There is no such auction of a property.")
        owners = {h["account_id"] for h in prop.holdings(conn, a["property_id"])} | {a["seller"]}
        if owners & _manager_sides(conn, manager_id):
            raise FundError("A fund never buys from its manager or the manager's empire.")
        w = worth(conn, fund)
        if not isinstance(limit, int) or isinstance(limit, bool) or limit <= 0:
            raise FundError("Name the highest price, in kobo.")
        if limit > a["fair"] * 11 // 10:
            raise FundError("A fund pays at most a tenth above what a building is worth.")
        if limit > (w["total"] + limit) * data.PROPERTY_FUND_ONE_BUILDING_BPS // BPS:
            raise FundError(f"No building may be more than {data.PROPERTY_FUND_ONE_BUILDING_BPS // 100}% of the fund.")
        if w["cash"] - limit < (w["total"]) * data.PROPERTY_FUND_LEAST_CASH_BPS // BPS:
            raise FundError(f"The fund must keep {data.PROPERTY_FUND_LEAST_CASH_BPS // 100}% of itself in cash.")
        # (Placed inside the same transaction, with the fund's row locked: two bids at once cannot both pass the checks.)
        try:
            return auctions.place_bid(conn, fund["account_id"], auction_id, limit, now, player_id=manager_id)
        except prop.PropertyError as refused:
            raise FundError(str(refused)) from None


def sell(conn: Connection, manager_id, property_id: int, reserve: int, now: datetime) -> int:
    from simulation import auctions
    from simulation import property as prop
    fund = _one(conn, "SELECT * FROM property_funds WHERE manager = %s AND status = 'open'", (manager_id,))
    if fund is None:
        raise FundError("You manage no property fund.")
    # The unitholders' building is never given away: its lowest price is at least nine tenths of what it is worth.
    p = prop._property(conn, property_id)
    least = prop.value(p, prop.districts(conn)[p["district_id"]], prop.policy_rate(conn)) * 9 // 10
    if not isinstance(reserve, int) or reserve < least:
        raise FundError(f"A fund's building is sold for at least nine tenths of its worth: a lowest price of {_money(least)} or more.")
    try:
        return auctions.owner_list(conn, fund["account_id"], property_id, reserve, now)
    except prop.PropertyError as refused:
        raise FundError(str(refused)) from None


# ---------------------------------------------------------------------------
# The computer's trust, and each quarter's close
# ---------------------------------------------------------------------------

def ensure_trust(conn: Connection, period: int, now: datetime) -> None:
    """The Nigeria Property Trust: the pension funds put money in, and it buys buildings from the property companies."""
    if not ready(conn) or _one(conn, "SELECT 1 FROM property_funds WHERE manager IS NULL"):
        return
    institutions = ledger.account_id(conn, ledger.INVESTORS_INSTITUTIONS)
    seed = min(naira(data.PROPERTY_FUND_SEED_NAIRA), ledger.balance(conn, institutions) // 5)
    if seed <= 0:
        return
    account = ledger.create_account(conn, kind="fund", name=TRUST_NAME)
    fund = _one(conn, "INSERT INTO property_funds (name, account_id, manager, fee_bps, opened_period, at) VALUES (%s, %s, NULL, 50, %s, %s)"
                      " RETURNING *", (TRUST_NAME, account, period, now))
    ledger.transfer(conn, payer=institutions, receiver=account, amount=seed, kind="fund_units", memo=f"The pension funds' stake in {TRUST_NAME}",
                    period=period)
    units = seed * UNIT // FIRST_PRICE
    conn.execute("INSERT INTO property_fund_units (fund_id, account, units) VALUES (%s, %s, %s)", (fund["id"], institutions, units))
    conn.execute("UPDATE property_funds SET units = %s WHERE id = %s", (units, fund["id"]))
    _trust_buys(conn, {**fund, "units": units}, period, now)


def _trust_buys(conn: Connection, fund: dict, period: int, now: datetime) -> None:
    """The trust buys buildings from the property companies at their value, keeping a fifth of itself in cash."""
    from simulation import conveyancing
    from simulation import property as prop
    rate = prop.policy_rate(conn)
    ds = prop.districts(conn)
    w = worth(conn, fund)
    spare = w["cash"] - w["total"] // 5
    for p in _rows(conn, """
            SELECT p.*, c.id AS company_id, c.account_id AS company_account FROM properties p
            JOIN property_holdings h ON h.property_id = p.id AND h.share_bps = 10000 JOIN companies c ON c.account_id = h.account_id
            WHERE p.status = 'standing' AND p.kind IN ('office', 'shop', 'mall', 'warehouse', 'hotel') AND NOT p.frozen
              AND NOT EXISTS (SELECT 1 FROM auctions a WHERE a.property_id = p.id AND a.status = 'open')
              AND NOT EXISTS (SELECT 1 FROM property_leases l WHERE l.property_id = p.id AND l.status = 'running')
              AND NOT EXISTS (SELECT 1 FROM property_claims k WHERE k.property_id = p.id AND k.status IN ('found', 'known'))
              AND p.title_flaw_bps = 0
            ORDER BY p.id"""):
        price = prop.value(p, ds[p["district_id"]], rate)
        if price > spare or price > w["total"] * data.PROPERTY_FUND_ONE_BUILDING_BPS // BPS:
            continue
        ledger.transfer(conn, payer=fund["account_id"], receiver=p["company_account"], amount=price, kind="asset_sale",
                        memo=f"{TRUST_NAME} buys {p['name']}", period=period)
        fixed = _one(conn, "SELECT fixed_assets FROM company_results WHERE company_id = %s ORDER BY period DESC LIMIT 1", (p["company_id"],))
        book = min(p["book_value"], max(fixed["fixed_assets"] * 9 // 10, 0) if fixed else 0)
        # (Recorded for the company's next accounts: the trust buys at a quarter's close, after the companies have filed.)
        conn.execute("INSERT INTO company_asset_sales (company_id, asset_id, property_id, period, book, proceeds, at) VALUES (%s, NULL, %s, %s, %s, %s, %s)",
                     (p["company_id"], p["id"], period + 1, book, price, now))
        conn.execute("UPDATE property_holdings SET account_id = %s, since_period = %s, paid = %s WHERE property_id = %s",
                     (fund["account_id"], period, price, p["id"]))
        conn.execute("UPDATE properties SET book_value = 0, upkeep = true WHERE id = %s", (p["id"],))
        conveyancing.register(conn, p["id"], "fund", price, period, now, payer=fund["account_id"])
        spare -= price
        if spare <= 0:
            break


def close(conn: Connection, period: int, now: datetime) -> dict:
    """Each quarter: the manager's fee; the trust buys or sells to keep its cash right; the record."""
    if not ready(conn):
        return {}
    from simulation import auctions
    ensure_trust(conn, period, now)
    label = clock.period_label(period)
    for fund in _rows(conn, "SELECT * FROM property_funds WHERE status = 'open' ORDER BY id"):
        w = worth(conn, fund)
        fee = max(w["total"], 0) * fund["fee_bps"] // BPS // 4
        if fund["manager"] is not None and fee > 0:
            fee = ledger.pay_up_to(conn, payer=fund["account_id"], receiver=ledger.player_account_id(conn, fund["manager"]), wanted=fee,
                                   kind="fund_fee", memo=f"{fund['name']}: the manager's fee, {label}", period=period)
        elif fee > 0:
            fee = ledger.pay_up_to(conn, payer=fund["account_id"], receiver=ledger.account_id(conn, ledger.INVESTORS_INSTITUTIONS), wanted=fee,
                                   kind="fund_fee", memo=f"{fund['name']}: the trustees' fee, {label}", period=period)
        if fund["manager"] is None:
            w = worth(conn, fund)
            if w["cash"] > w["total"] * 3 // 10:
                _trust_buys(conn, fund, period, now)
            elif w["cash"] < w["total"] // 20:
                p = _one(conn, "SELECT p.id FROM properties p JOIN property_holdings h ON h.property_id = p.id WHERE h.account_id = %s"
                               " AND NOT EXISTS (SELECT 1 FROM auctions a WHERE a.property_id = p.id AND a.status = 'open') ORDER BY p.id LIMIT 1",
                         (fund["account_id"],))
                if p:
                    try:
                        auctions.owner_list(conn, fund["account_id"], p["id"], 0, now)
                    except Exception:  # noqa: BLE001 - tried again next quarter
                        pass
        w = worth(conn, fund)
        conn.execute("INSERT INTO property_fund_results (period, fund_id, value, units, fee) VALUES (%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
                     (period, fund["id"], w["total"], fund["units"], fee))
    return {}


def listing(conn: Connection, account) -> list[dict]:
    if not ready(conn):
        return []
    out = []
    for f in _rows(conn, "SELECT f.*, pl.display_name AS manager_name FROM property_funds f LEFT JOIN players pl ON pl.id = f.manager"
                         " WHERE f.status = 'open' ORDER BY f.manager IS NOT NULL, f.name"):
        w = worth(conn, f)
        held = _one(conn, "SELECT units FROM property_fund_units WHERE fund_id = %s AND account = %s", (f["id"], account)) if account else None
        price = unit_price(f, w["total"])
        history = [{"label": clock.period_label(r["period"]), "value": r["value"], "units": r["units"]}
                   for r in _rows(conn, "SELECT * FROM property_fund_results WHERE fund_id = %s ORDER BY period DESC LIMIT 8", (f["id"],))]
        out.append({"id": f["id"], "name": f["name"], "manager": f["manager_name"] or "Run by the computer", "fee_bps": f["fee_bps"],
                    "value": w["total"], "cash": w["cash"], "buildings_value": w["buildings"],
                    "buildings": _one(conn, "SELECT count(*) AS n FROM property_holdings WHERE account_id = %s", (f["account_id"],))["n"],
                    "unit_price_kobo": price / UNIT, "units": f["units"], "my_units": held["units"] if held else 0,
                    "my_value": (held["units"] * unit_price(f, w["total"], side="sell") // UNIT) if held else 0, "history": history[::-1]})
    return out


def _players_units(conn: Connection) -> dict:
    """For players' net worth: their units at the selling price."""
    out: dict = {}
    if not ready(conn):
        return out
    for f in _rows(conn, "SELECT * FROM property_funds WHERE status = 'open'"):
        w = worth(conn, f)
        price = unit_price(f, w["total"], side="sell")
        for h in _rows(conn, "SELECT u.account, u.units FROM property_fund_units u JOIN ledger_accounts a ON a.id = u.account"
                             " WHERE u.fund_id = %s AND u.units > 0 AND a.kind = 'player'", (f["id"],)):
            cash, inv = out.get(h["account"], (0, 0))
            out[h["account"]] = (cash, inv + h["units"] * price // UNIT)
    return out


def check_books(conn: Connection) -> list[str]:
    if not ready(conn):
        return []
    bad = _rows(conn, "SELECT f.name FROM property_funds f WHERE f.units <> (SELECT coalesce(sum(units), 0) FROM property_fund_units u"
                      " WHERE u.fund_id = f.id)")
    return [f"{r['name']}: its units in issue do not match its holders'." for r in bad]


def _register() -> None:
    from simulation import marketview
    if _players_units not in marketview._OTHER_HOLDINGS:
        marketview._OTHER_HOLDINGS.append(_players_units)


_register()
