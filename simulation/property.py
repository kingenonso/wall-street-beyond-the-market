"""Land and property (Stage 8, owner, 12 October 2026).

Every city has five districts: a business district, homes, shops, industry and farmland. Each
district has big buildings, small units and empty plots. At the start the property companies own
them all: their buildings are part of their own business, and the rent their tenants pay is part
of their sales.

When anybody else owns a building (a player, an empire, a pension fund), its rent comes to them
instead. The money is real: the households and companies of that city spend on property as they
always did, and the share that is rent on buildings owned outside the property companies is paid
into one rent account, then shared out to the owners at the quarter's close, building by building,
by the rent each was due. The property companies that sold those buildings earn that much less.

  * Rent follows demand: a district's rent moves towards what its tenants can pay (the spending of
    its city's households, or its jobs, or farm prices), a quarter of the way each quarter.
  * Tenants fill a district's buildings when demand is strong, and leave when it is weak or when
    a building is run down.
  * A property is worth its yearly rent divided by the yield investors want (the Central Bank's
    rate less four points). On top of that, buyers who pay more than that in a district push its
    prices above what rents justify: a bubble. It shrinks by a fifth each quarter, as rents pull
    prices back. An empty plot is worth its land, which follows the district's prices.
  * Owners pay property and land tax to the Government each quarter, keep their buildings up (or
    let them wear), and may renovate. Unpaid tax grows, and at a tenth of the value the Government
    sells the property.
  * Banks lend against property: a mortgage. A player may borrow at most four years of their
    salary and must put down a fifth; an empire at most 60% of the price. Two quarters missed and
    the bank takes the property and sells it.

Every naira moves through the ledger.
"""

from __future__ import annotations

import hashlib
import math
from collections import defaultdict
from datetime import datetime, timedelta

from psycopg import Connection
from psycopg.rows import dict_row

from simulation import clock, ledger
from simulation import world_data as data
from simulation.money import BPS, apply_bps, naira

RENTS = "property:rents"          # where rent for buildings owned outside the property companies gathers each quarter
HELD = "auction:held"             # cash held for bids at the Auction House

TAX_KINDS = ("property_tax",)


class PropertyError(Exception):
    """A property action that is not allowed, in plain words."""


def _rows(conn: Connection, sql: str, params=()) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def _one(conn: Connection, sql: str, params=()) -> dict | None:
    rows = _rows(conn, sql, params)
    return rows[0] if rows else None


def _uniform(seed: str, subject: str, period: int) -> float:
    digest = hashlib.sha256(f"{seed}:{subject}:{period}:property".encode()).digest()
    return int.from_bytes(digest[:8], "big") / 2**64


def money(kobo: int) -> str:
    return f"₦{kobo / 100:,.0f}"


# ---------------------------------------------------------------------------
# The world's property, made once when the world is created
# ---------------------------------------------------------------------------

_BIG_NAMES = {"office": ("Tower", "House", "Plaza", "Centre"), "home": ("Court", "Gardens", "Estate", "Heights"),
              "shop": ("Mall", "Market Hall", "Arcade", "Plaza"), "factory": ("Works", "Mill", "Plant", "Works Two"),
              "farmland": ("Farm", "Estate Farm", "Ranch", "Plantation")}
_SMALL_NAMES = {"office": "Office suite", "home": "Flat", "shop": "Shop", "warehouse": "Store", "farmland": "Smallholding"}
_SIZES = {"office": (2_000, 8_000), "home": (1_500, 6_000), "shop": (1_000, 4_000), "factory": (4_000, 15_000),
          "warehouse": (300, 1_200), "farmland": (50_000, 300_000)}
_SMALL_SIZES = {"office": (60, 250), "home": (50, 180), "shop": (25, 120), "warehouse": (300, 1_200), "farmland": (5_000, 20_000)}
_PLOT_SIZES = {"business": (800, 3_000), "homes": (500, 2_500), "shops": (500, 2_000), "industry": (2_000, 8_000), "farmland": (20_000, 100_000)}


def base_rent(city: str, kind: str, size_m2: int) -> int:
    """A quarter's rent for a building when full, at the start, in kobo."""
    return apply_bps(naira(data.RENT_A_METRE_NAIRA[city]) * size_m2, data.RENT_KIND_TIMES_BPS[kind])


def land_value(city: str, district_kind: str, size_m2: int) -> int:
    return apply_bps(naira(data.LAND_A_METRE_NAIRA[city]) * size_m2, data.LAND_KIND_TIMES_BPS[district_kind])


def yield_bps(policy_rate_bps: int) -> int:
    return max(policy_rate_bps - data.PROPERTY_YIELD_BELOW_RATE_BPS, data.PROPERTY_LEAST_YIELD_BPS)


def create(conn: Connection, seed: str, policy_rate_bps: int) -> None:
    """Make the districts and their property, owned by the property companies (those based in the city first)."""
    for code, kind, name in ((RENTS, "escrow", "Rent gathered for property owners"), (HELD, "escrow", "Auction House: held for bids")):
        if _one(conn, "SELECT 1 FROM ledger_accounts WHERE code = %s", (code,)) is None:
            ledger.create_account(conn, kind=kind, name=name, code=code)
    owners = _rows(conn, "SELECT c.id, c.account_id, c.headquarters, r.fixed_assets FROM companies c JOIN company_results r"
                         " ON r.company_id = c.id AND r.period = 0 WHERE c.sector = 'real_estate' ORDER BY c.ticker")
    if not owners:
        return
    pid = 0
    did = 0
    made: list[tuple] = []
    for city, districts in data.DISTRICTS.items():
        local = [o for o in owners if o["headquarters"] == city] or owners
        for name, kind in districts:
            did += 1
            conn.execute("INSERT INTO districts (id, city, name, kind) VALUES (%s, %s, %s, %s)", (did, city, name, kind))
            big_kind, small_kind = data.DISTRICT_BUILDINGS[kind]
            big, small, plots = data.DISTRICT_STOCK
            for i in range(big + small + plots):
                pid += 1
                draw = _uniform(seed, f"size:{pid}", 0)
                if i < big:
                    pkind = big_kind
                    low, high = _SIZES[pkind]
                    label = f"{name} {_BIG_NAMES.get(pkind, ('Block',) * 4)[i % 4]}"
                elif i < big + small:
                    pkind = small_kind
                    low, high = _SMALL_SIZES[pkind]
                    label = f"{_SMALL_NAMES[pkind]} {i - big + 1}, {name}"
                else:
                    pkind = "land"
                    low, high = _PLOT_SIZES[kind]
                    label = f"Plot {i - big - small + 1}, {name}"
                size = int(low + (high - low) * draw)
                rent = 0 if pkind == "land" else base_rent(city, pkind, size)
                plot_share = 1 if pkind == "land" else 0.3          # a building stands on part of a bigger plot's worth of land
                land = int(land_value(city, kind, size) * plot_share)
                flaw = 0
                if _uniform(seed, f"title:{pid}", 0) < data.TITLE_FLAW_BPS / BPS:
                    low_f, high_f = data.TITLE_FLAW_LOSS_BPS
                    flaw = int(low_f + (high_f - low_f) * _uniform(seed, f"flaw:{pid}", 0))
                condition = 70 + int(25 * _uniform(seed, f"condition:{pid}", 0)) if pkind != "land" else 100
                owner = local[int(_uniform(seed, f"owner:{pid}", 0) * len(local))]
                conn.execute("INSERT INTO properties (id, district_id, kind, name, size_m2, base_rent, land_value, condition, title_flaw_bps,"
                             " status) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                             (pid, did, pkind, label, size, rent, land, condition, flaw, "plot" if pkind == "land" else "standing"))
                conn.execute("INSERT INTO property_holdings (property_id, account_id, share_bps, since_period) VALUES (%s, %s, 10000, 0)",
                             (pid, owner["account_id"]))
                made.append((pid, owner["id"], rent, land))
    # Each building in a property company's books at what it is worth today; never more than four fifths of what
    # the company's buildings and machines are in its books altogether.
    y = yield_bps(policy_rate_bps)
    worth = {pid: (rent * 4 * BPS // y if rent else land) for pid, _, rent, land in made}
    by_company = defaultdict(int)
    for pid, company, _, _ in made:
        by_company[company] += worth[pid]
    fixed = {o["id"]: o["fixed_assets"] for o in owners}
    for pid, company, _, _ in made:
        scale = min(1.0, fixed[company] * 0.8 / by_company[company]) if by_company[company] else 0
        conn.execute("UPDATE properties SET book_value = %s WHERE id = %s", (int(worth[pid] * scale), pid))
    for company, total in _rows_to_dict(made).items():
        conn.execute("INSERT INTO property_company_base (company_id, base_rent) VALUES (%s, %s)", (company, total))
    # The gap stage: zones, a hotel and a mall in each city, and the claims hidden on some property.
    from simulation import conveyancing, zoning
    if zoning.ready(conn):
        zoning.first_zones(conn)
        conveyancing.first_claims(conn)
    record(conn, 0, policy_rate_bps)


def _rows_to_dict(made: list[tuple]) -> dict:
    out = defaultdict(int)
    for _, company, rent, _ in made:
        out[company] += rent
    return out


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------

def districts(conn: Connection) -> dict[int, dict]:
    """Every district, with how hotels and malls are doing (the same in every district)."""
    kinds = {}
    if _one(conn, "SELECT to_regclass('property_kind_index') IS NOT NULL AS ok")["ok"]:
        kinds = {r["kind"]: r["bps"] for r in _rows(conn, "SELECT kind, bps FROM property_kind_index")}
    return {d["id"]: {**d, "kind_bps": kinds} for d in _rows(conn, "SELECT * FROM districts ORDER BY id")}


def _kind_bps(prop: dict, district: dict) -> int:
    return (district.get("kind_bps") or {}).get(prop["kind"], BPS)


def company_accounts(conn: Connection) -> set:
    return {r["account_id"] for r in _rows(conn, "SELECT account_id FROM companies")}


def policy_rate(conn: Connection) -> int:
    row = _one(conn, "SELECT next_policy_rate_bps FROM economy_results ORDER BY period DESC LIMIT 1")
    return row["next_policy_rate_bps"] if row else data.NEUTRAL_RATE_BPS


def rent_due(prop: dict, district: dict) -> int:
    """This quarter's rent for a building: its rent at the start, moved with its district, times how full it
    is (a run-down building loses tenants)."""
    if prop["status"] != "standing" or prop["kind"] == "land" or prop.get("frozen"):
        return 0                                      # (a disputed property's rent is held back until the dispute is settled)
    occupancy = district["occupancy_bps"]
    if prop["condition"] < data.POOR_CONDITION:
        occupancy = occupancy * prop["condition"] // data.POOR_CONDITION
    return prop["base_rent"] * district["rent_bps"] // BPS * occupancy // BPS * _kind_bps(prop, district) // BPS


def value(prop: dict, district: dict, policy_rate_bps: int) -> int:
    """What a property is worth today: a building, its yearly rent (when full) over the yield investors want,
    less for being run down; a plot, or a fallen building, its land. Both carry the district's bubble."""
    infra = district.get("infra_bps", 0)
    premium = BPS + district["premium_bps"] + infra
    beside = infra * (data.INFRA_BESIDE_TIMES - 1) if prop.get("beside_project") else 0      # land right beside the works gains more
    cut = BPS - min(prop.get("value_cut_bps", 0), BPS)                                         # a known right of way
    land = prop["land_value"] * district["rent_bps"] // BPS * (premium + beside) // BPS * cut // BPS
    if prop["status"] != "standing" or prop["kind"] == "land":
        return max(land, 0)
    full = prop["base_rent"] * district["rent_bps"] // BPS * district["occupancy_bps"] // BPS * _kind_bps(prop, district) // BPS
    condition = BPS // 2 + prop["condition"] * BPS // 200
    building = full * 4 * BPS // yield_bps(policy_rate_bps) * condition // BPS * premium // BPS * cut // BPS
    return max(building, land)


def holdings(conn: Connection, property_id: int) -> list[dict]:
    return _rows(conn, "SELECT h.*, a.kind AS account_kind, a.name AS account_name FROM property_holdings h"
                       " JOIN ledger_accounts a ON a.id = h.account_id WHERE h.property_id = %s ORDER BY h.share_bps DESC", (property_id,))


def owned_by_company(conn: Connection, property_id: int) -> bool:
    return bool(_one(conn, "SELECT 1 FROM property_holdings h JOIN companies c ON c.account_id = h.account_id WHERE h.property_id = %s",
                     (property_id,)))


def mortgage_on(conn: Connection, property_id: int) -> dict | None:
    return _one(conn, "SELECT * FROM mortgages WHERE property_id = %s AND status = 'open'", (property_id,))


def equity_of(conn: Connection, account) -> dict:
    """What an account's property is worth at today's prices, and what it owes on it."""
    rate = policy_rate(conn)
    ds = districts(conn)
    worth = 0
    for p in _rows(conn, "SELECT p.*, h.share_bps FROM properties p JOIN property_holdings h ON h.property_id = p.id WHERE h.account_id = %s",
                   (account,)):
        worth += value(p, ds[p["district_id"]], rate) * p["share_bps"] // BPS
    owed = _one(conn, "SELECT coalesce(sum(outstanding), 0)::bigint AS o FROM mortgages WHERE borrower = %s AND status IN ('open', 'shortfall')",
                (account,))["o"]
    tax = _one(conn, "SELECT coalesce(sum(p.tax_owed * h.share_bps / 10000), 0)::bigint AS t FROM properties p JOIN property_holdings h"
                     " ON h.property_id = p.id WHERE h.account_id = %s", (account,))["t"]
    return {"value": worth, "owed": owed + tax, "equity": worth - owed - tax}


# ---------------------------------------------------------------------------
# During the quarter close: rent comes through the households' and companies' spending
# ---------------------------------------------------------------------------

def ensure(conn: Connection, seed: str) -> None:
    """A world made before Stage 8 gets its districts and property at its next close."""
    if _one(conn, "SELECT 1 FROM districts LIMIT 1") is None:
        create(conn, seed, policy_rate(conn))


def add_rent_to_market(conn: Connection, world, seed: str) -> None:
    """Make rent part of the property market the city's spending goes to. Buildings owned outside the
    property companies draw rent in proportion to what they are due; the property companies that sold
    them draw that much less."""
    ensure(conn, seed)
    members = world.members.get("real_estate")
    if members is None:
        return
    ds = districts(conn)
    companies_ = company_accounts(conn)
    due_by_city: dict[str, int] = defaultdict(int)
    for p in _rows(conn, "SELECT p.*, h.account_id, h.share_bps FROM properties p JOIN property_holdings h ON h.property_id = p.id"
                         " WHERE p.status = 'standing'"):
        if p["account_id"] in companies_:
            continue
        due_by_city[ds[p["district_id"]]["city"]] += rent_due(p, ds[p["district_id"]]) * p["share_bps"] // BPS
    # The property companies: six tenths of their business is rent, in proportion to the buildings they still hold.
    held = {r["account_id"]: int(r["rent"]) for r in _rows(conn, """
        SELECT h.account_id, coalesce(sum(p.base_rent * h.share_bps / 10000), 0) AS rent FROM property_holdings h
        JOIN properties p ON p.id = h.property_id JOIN companies c ON c.account_id = h.account_id
        WHERE p.status = 'standing' GROUP BY h.account_id""")}
    base = {r["account_id"]: r["base_rent"] for r in _rows(conn, "SELECT c.account_id, b.base_rent FROM property_company_base b"
                                                                 " JOIN companies c ON c.id = b.company_id")}
    for member in members:
        start = base.get(member["account_id"])
        if start:
            share = min(held.get(member["account_id"], 0) / start, 2.0)
            factor = 1 - data.PROPERTY_RENT_SHARE_OF_COMPANY_BPS / BPS * (1 - share)
            member["pull"] = max(int(member["pull"] * max(factor, 0.2)), 1)
    rents = ledger.account_id(conn, RENTS)
    for city, due in due_by_city.items():
        if due > 0:
            members.append({"account_id": rents, "headquarters": city, "pull": due, "price": BPS})


# ---------------------------------------------------------------------------
# At the quarter's close
# ---------------------------------------------------------------------------

def _city_demand(conn: Connection, period: int) -> dict:
    """How strong demand is in each city against the first quarter: households' spending, and jobs."""
    out = {}
    first = {r["location"]: r for r in _rows(conn, "SELECT location, spending, jobs FROM household_results WHERE period = 1")}
    now = {r["location"]: r for r in _rows(conn, "SELECT location, spending, jobs FROM household_results WHERE period = %s", (period,))}
    for city, row in now.items():
        f = first.get(city) or row
        out[city] = {"spending": row["spending"] * BPS // max(f["spending"], 1), "jobs": row["jobs"] * BPS // max(f["jobs"], 1)}
    return out


def _update_districts(conn: Connection, period: int, prices_bps: int, farm_bps: int) -> None:
    """Rent moves a quarter of the way towards what demand says; tenants follow demand after prices; a bubble
    shrinks by a fifth and grows with what buyers paid above fair value."""
    demand = _city_demand(conn, period)
    overpaid = {r["district_id"]: (int(r["over"]), int(r["fair"])) for r in _rows(conn, """
        SELECT p.district_id, coalesce(sum(a.price - a.fair), 0) AS over, coalesce(sum(a.fair), 0) AS fair
        FROM auctions a JOIN properties p ON p.id = a.property_id WHERE a.status = 'sold' AND a.period = %s GROUP BY p.district_id""", (period,))}
    for d in _rows(conn, "SELECT * FROM districts ORDER BY id"):
        city = demand.get(d["city"], {"spending": BPS, "jobs": BPS})
        if d["kind"] in ("homes", "shops"):
            target = city["spending"]
        elif d["kind"] == "farmland":
            target = farm_bps
        else:
            target = city["jobs"] * prices_bps // BPS
        rent = d["rent_bps"] + (target - d["rent_bps"]) * data.RENT_FOLLOWS_DEMAND_BPS // BPS
        real = target * BPS // max(prices_bps, 1)
        low, high = data.OCCUPANCY_LIMITS_BPS
        occupancy = int(min(max(9000 * math.sqrt(max(real, 1) / BPS), low), high))
        over, fair = overpaid.get(d["id"], (0, 0))
        premium = d["premium_bps"] * (BPS - data.PREMIUM_DECAY_BPS) // BPS
        if fair > 0:
            premium += over * BPS // fair * data.PREMIUM_FROM_OVERPAYING_BPS // BPS
        premium = min(max(premium, data.PREMIUM_LIMITS_BPS[0]), data.PREMIUM_LIMITS_BPS[1])
        conn.execute("UPDATE districts SET rent_bps = %s, occupancy_bps = %s, premium_bps = %s WHERE id = %s",
                     (max(rent, 1000), occupancy, premium, d["id"]))


def _update_kinds(conn: Connection, period: int, prices_bps: int) -> None:
    """Hotels follow the hospitality companies' sales; malls the cities' shopping, with a big mall's swings larger.
    Both against the first quarter, after prices."""
    if _one(conn, "SELECT to_regclass('property_kind_index') IS NOT NULL AS ok")["ok"] is not True:
        return
    def total(sql: str, p: int) -> int:
        row = _one(conn, sql, (p,))
        return int(row["v"] or 0) if row else 0
    hosp = "SELECT sum(r.revenue) AS v FROM company_results r JOIN companies c ON c.id = r.company_id WHERE c.sector = 'hospitality' AND r.period = %s"
    shop = "SELECT sum(spending) AS v FROM household_results WHERE period = %s"
    for kind, sql, swing in (("hotel", hosp, 1), ("mall", shop, 2)):
        first, now = total(sql, 1), total(sql, period)
        if first <= 0 or now <= 0:
            continue
        real = now * BPS // first * BPS // max(prices_bps, 1)
        bps = min(max(BPS + (real - BPS) * swing, 5000), 20_000)
        conn.execute("UPDATE property_kind_index SET bps = %s WHERE kind = %s", (bps, kind))


def _pay_builders(conn: Connection, payer, amount: int, city: str, why: str, period: int) -> int:
    """Building work and upkeep are bought from the property and construction companies, those in the city first."""
    if amount <= 0:
        return 0
    builders = _rows(conn, "SELECT c.account_id, c.headquarters FROM companies c WHERE c.sector IN ('real_estate', 'cement')"
                           " AND c.status = 'trading' ORDER BY c.ticker")
    local = [b for b in builders if b["headquarters"] == city] or builders
    if not local:
        return 0
    each = amount // len(local)
    amounts = {b["account_id"]: each for b in local}
    amounts[local[0]["account_id"]] += amount - each * len(local)
    return ledger.pay_split_up_to(conn, payer=payer, amounts=amounts, kind="capital_spending", memo=why, period=period)


def close(conn: Connection, world, period: int, now: datetime, seed: str, measured: dict) -> dict:
    """The property market's quarter: districts, rent shared out, tax, upkeep and wear, mortgages, title claims,
    the headquarters, new listings at the Auction House, and the record."""
    from simulation import auctions, headquarters
    # Auctions whose time ran out before the close are settled first, so the quarter's owners are the right ones.
    auctions.run(conn, now)
    _update_districts(conn, period, measured["price_index_bps"], measured.get("agriculture_bps", BPS))
    _update_kinds(conn, period, measured["price_index_bps"])
    # The gap stage: infrastructure works and the districts' gains from them; households' home loans, defaults and
    # repossessions (which move the homes districts' prices); the planning office's decisions.
    from simulation import homes, infrastructure, zoning
    infrastructure.close(conn, period, now, seed)
    homes.close(conn, world, period, now)
    zoning.close(conn, period, now)
    rate = measured["next_policy_rate_bps"]
    ds = districts(conn)
    companies_ = company_accounts(conn)
    label = clock.period_label(period)
    treasury = ledger.account_id(conn, ledger.TREASURY)
    props = {p["id"]: p for p in _rows(conn, "SELECT * FROM properties ORDER BY id")}
    owners_of: dict[int, list[dict]] = defaultdict(list)
    for h in _rows(conn, "SELECT * FROM property_holdings ORDER BY property_id, account_id"):
        owners_of[h["property_id"]].append(h)

    # 1. Rent gathered this quarter is shared out by what each building was due.
    rents = ledger.account_id(conn, RENTS)
    pot = ledger.balance(conn, rents)
    due: dict[tuple[int, object], int] = {}
    for pid, p in props.items():
        for h in owners_of[pid]:
            if h["account_id"] in companies_:
                continue
            amount = rent_due(p, ds[p["district_id"]]) * h["share_bps"] // BPS
            if amount > 0:
                due[(pid, h["account_id"])] = amount
    total_due = sum(due.values())
    paid_rent: dict[int, int] = defaultdict(int)
    if pot > 0 and total_due > 0:
        ordered = sorted(due.items(), key=lambda kv: (kv[0][0], str(kv[0][1])))
        shared = 0
        for n, ((pid, account), amount) in enumerate(ordered):
            # (The last owner takes what rounding leaves, so the rent account keeps not a kobo.)
            part = pot * amount // total_due if n < len(ordered) - 1 else pot - shared
            shared += part
            if part > 0:
                ledger.transfer(conn, payer=rents, receiver=account, amount=part, kind="rent",
                                memo=f"Rent from the tenants of {props[pid]['name']}, {label}", period=period)
                paid_rent[pid] += part

    # 2. Tax, upkeep and wear, for property owned outside the property companies.
    taxed: dict[int, int] = defaultdict(int)
    kept: dict[int, int] = defaultdict(int)
    seize = []
    for pid, p in props.items():
        owners = [h for h in owners_of[pid] if h["account_id"] not in companies_]
        d = ds[p["district_id"]]
        worth = value(p, d, rate)
        if not owners:
            # A property company keeps its own buildings up as part of its business.
            if p["status"] == "standing" and p["condition"] > 60:
                conn.execute("UPDATE properties SET condition = greatest(condition - %s, 60) WHERE id = %s", (data.WEAR_WITH_UPKEEP, pid))
            continue
        tax = worth * (data.PROPERTY_TAX_BPS + data.LAND_TAX_BPS) // BPS // 4
        owed_before = p["tax_owed"] + p["tax_owed"] * data.TAX_ARREARS_PENALTY_BPS // BPS
        wanted = tax + owed_before
        got = 0
        for h in owners:
            part = wanted * h["share_bps"] // BPS
            if part > 0:
                got += ledger.pay_up_to(conn, payer=h["account_id"], receiver=treasury, wanted=part, kind="property_tax",
                                        memo=f"Property and land tax on {p['name']}, {label}", period=period)
        taxed[pid] = got
        conn.execute("UPDATE properties SET tax_owed = %s WHERE id = %s", (max(wanted - got, 0), pid))
        if wanted - got > 0 and wanted - got >= worth * data.TAX_ARREARS_SEIZE_BPS // BPS:
            seize.append(pid)
        if p["status"] == "standing" and p["kind"] != "land":
            wear = data.WEAR_WITHOUT_UPKEEP
            if p["upkeep"]:
                upkeep = worth * data.UPKEEP_BPS // BPS
                spent = 0
                for h in owners:
                    part = upkeep * h["share_bps"] // BPS
                    spent += _pay_builders(conn, h["account_id"], part, d["city"], f"Upkeep of {p['name']}, {label}", period)
                kept[pid] = spent
                if spent * 10 >= upkeep * 9:
                    wear = data.WEAR_WITH_UPKEEP
            conn.execute("UPDATE properties SET condition = greatest(condition - %s, 0) WHERE id = %s", (wear, pid))

    # 3. Mortgages: interest and repayment; two quarters missed and the bank takes the property.
    repossess = _mortgages(conn, period, rate, label)

    # 4. A flawed title: the true owner of part of a property bought outside the property companies comes forward.
    _title_claims(conn, period, label, companies_)

    # 4b. Sale-and-leaseback (the gap stage): the rent, and leases that end or are broken.
    from simulation import conveyancing, development, leaseback, propfunds
    leaseback.close(conn, period, now)
    # 4c. Claims besides a bad title come to light; developments build a phase; property funds pay fees and rebalance.
    conveyancing.close_claims(conn, period, now)
    development.close(conn, period, now, seed)
    propfunds.close(conn, period, now)

    # 5. The headquarters: upkeep, wear, warnings and collapse.
    headquarters.close(conn, period, now, seed)

    # 6. The Auction House: forced sales, and the property companies' new listings for the coming week.
    for pid in seize:
        auctions.force_sale(conn, pid, "tax", period, now)
    for pid in repossess:
        auctions.force_sale(conn, pid, "repossession", period, now)
    # (Listings run from the moment the quarter ended, so a world catching up on several closes lists each
    # quarter's lots in that quarter's own week, and those whose week has passed are settled at the next close.)
    world_row = _one(conn, "SELECT world_start, weeks_ahead FROM world_state")
    ended = clock.effective_start(world_row["world_start"], world_row["weeks_ahead"]) + timedelta(days=clock.REAL_DAYS_PER_QUARTER * period)
    auctions.list_for_quarter(conn, period + 1, min(ended, now), seed)

    _district_news(conn, period)
    record(conn, period, rate, paid_rent=paid_rent, taxed=taxed, kept=kept)
    return {"rent": sum(paid_rent.values()), "tax": sum(taxed.values()), "repossessed": len(repossess), "seized": len(seize)}


def _mortgages(conn: Connection, period: int, rate: int, label: str) -> list[int]:
    repossess = []
    for m in _rows(conn, "SELECT m.*, c.account_id AS bank_account, c.name AS bank_name FROM mortgages m JOIN companies c ON c.id = m.bank_company_id"
                         " WHERE m.status IN ('open', 'shortfall') ORDER BY m.id"):
        if m["status"] == "shortfall":
            got = ledger.pay_up_to(conn, payer=m["borrower"], receiver=m["bank_account"], wanted=m["outstanding"], kind="mortgage_repayment",
                                   memo=f"Repaying what is still owed to {m['bank_name']} after a repossession, {label}", period=period)
            left = m["outstanding"] - got
            conn.execute("UPDATE mortgages SET outstanding = %s, status = %s WHERE id = %s",
                         (left, "repaid" if left == 0 else "shortfall", m["id"]))
            continue
        new_rate = rate + data.MORTGAGE_SPREAD_BPS
        interest = m["outstanding"] * new_rate // BPS // 4
        principal = min(max(m["principal"] // m["term_quarters"], 1), m["outstanding"])
        paid_interest = ledger.pay_up_to(conn, payer=m["borrower"], receiver=m["bank_account"], wanted=interest, kind="mortgage_interest",
                                         memo=f"Mortgage interest to {m['bank_name']}, {label}", period=period)
        paid_principal = 0
        if paid_interest == interest:
            paid_principal = ledger.pay_up_to(conn, payer=m["borrower"], receiver=m["bank_account"], wanted=principal,
                                              kind="mortgage_repayment", memo=f"Mortgage repayment to {m['bank_name']}, {label}", period=period)
        missed = 0 if (paid_interest == interest and paid_principal == principal) else m["missed"] + 1
        left = m["outstanding"] - paid_principal
        conn.execute("UPDATE mortgages SET outstanding = %s, rate_bps = %s, missed = %s, status = %s WHERE id = %s",
                     (left, new_rate, missed, "repaid" if left == 0 else "open", m["id"]))
        if left > 0 and missed >= data.MORTGAGE_MISSES_TO_REPOSSESS:
            repossess.append(m["property_id"])
    return repossess


def _title_claims(conn: Connection, period: int, label: str, companies_: set) -> None:
    """Somebody bought a property whose seller did not truly own all of it. At the next close the true owner
    comes forward and takes their part. (Legal Counsel's title check, or a title search, would have shown it.)"""
    claimant = ledger.account_id(conn, ledger.INVESTORS_FOUNDERS)
    for p in _rows(conn, "SELECT * FROM properties WHERE title_flaw_bps > 0"):
        owners = holdings(conn, p["id"])
        if not owners or any(h["account_id"] in companies_ for h in owners):
            continue
        bought = max(h["since_period"] for h in owners)
        if bought >= period:
            continue                                      # it comes to light at the first close after the purchase
        flaw = p["title_flaw_bps"]
        for h in owners:
            keep = h["share_bps"] * (BPS - flaw) // BPS
            if keep > 0:
                conn.execute("UPDATE property_holdings SET share_bps = %s WHERE property_id = %s AND account_id = %s",
                             (keep, p["id"], h["account_id"]))
            else:
                conn.execute("DELETE FROM property_holdings WHERE property_id = %s AND account_id = %s", (p["id"], h["account_id"]))
        rest = BPS - sum(h["share_bps"] * (BPS - flaw) // BPS for h in owners)
        if rest > 0:
            conn.execute("INSERT INTO property_holdings (property_id, account_id, share_bps, since_period) VALUES (%s, %s, %s, %s)"
                         " ON CONFLICT (property_id, account_id) DO UPDATE SET share_bps = property_holdings.share_bps + EXCLUDED.share_bps",
                         (p["id"], claimant, rest, period))
        conn.execute("UPDATE properties SET title_flaw_bps = 0 WHERE id = %s", (p["id"],))
        from simulation import headquarters
        headquarters.lost_building(conn, p["id"], None, period, _close_moment(conn, period),
                                   why="A claim at the lands registry took part of the headquarters' building: the empire no longer owns all of it.")
        from simulation import news
        news.publish(conn, period=period + 1, day=5, kind="title_dispute", story=f"title:{p['id']}",
                     facts={"property": p["name"], "share": f"{flaw / 100:.0f}%"})


DISTRICT_NEWS_BPS = 1000          # a district's prices 10% up or down on the quarter


def _district_news(conn: Connection, period: int) -> None:
    from simulation import news
    before = {r["district_id"]: r["price_bps"] for r in _rows(conn, "SELECT district_id, price_bps FROM district_results WHERE period = %s",
                                                               (period - 1,))}
    for d in districts(conn).values():
        was = before.get(d["id"])
        if not was:
            continue
        now = d["rent_bps"] * (BPS + d["premium_bps"]) // BPS
        change = (now - was) * BPS // was
        if abs(change) >= DISTRICT_NEWS_BPS:
            news.publish(conn, period=period + 1, day=3, kind="property_up" if change > 0 else "property_down", story=f"district:{d['id']}",
                         facts={"district": d["name"], "city": d["city"], "change": news.percent(abs(change))}, locations=[d["city"]],
                         sectors=["real_estate"])


def record(conn: Connection, period: int, rate: int, *, paid_rent=None, taxed=None, kept=None) -> None:
    ds = districts(conn)
    sold = {r["district_id"]: (r["n"], int(r["v"])) for r in _rows(conn, """
        SELECT p.district_id, count(*) AS n, coalesce(sum(a.price), 0) AS v FROM auctions a JOIN properties p ON p.id = a.property_id
        WHERE a.status = 'sold' AND a.period = %s GROUP BY p.district_id""", (period,))}
    for d in ds.values():
        n, v = sold.get(d["id"], (0, 0))
        conn.execute("INSERT INTO district_results (period, district_id, rent_bps, occupancy_bps, premium_bps, price_bps, sold, sold_value)"
                     " VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                     (period, d["id"], d["rent_bps"], d["occupancy_bps"], d["premium_bps"],
                      d["rent_bps"] * (BPS + d["premium_bps"]) // BPS, n, v))
    with conn.cursor() as cur:
        rows = []
        for p in _rows(conn, "SELECT * FROM properties ORDER BY id"):
            d = ds[p["district_id"]]
            occupancy = d["occupancy_bps"] if p["condition"] >= data.POOR_CONDITION else d["occupancy_bps"] * p["condition"] // data.POOR_CONDITION
            rows.append((period, p["id"], value(p, d, rate), rent_due(p, d), (paid_rent or {}).get(p["id"], 0),
                         occupancy if p["status"] == "standing" and p["kind"] != "land" else 0, p["condition"],
                         (taxed or {}).get(p["id"], 0), (kept or {}).get(p["id"], 0)))
        cur.executemany("INSERT INTO property_results (period, property_id, value, rent_due, rent_paid, occupancy_bps, condition, tax, upkeep)"
                        " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)", rows)


# ---------------------------------------------------------------------------
# What owners do
# ---------------------------------------------------------------------------

def _state(conn: Connection, now: datetime) -> dict:
    from simulation import careers
    return careers.world_now(conn, now)


def share_of(conn: Connection, property_id: int, account) -> int:
    row = _one(conn, "SELECT share_bps FROM property_holdings WHERE property_id = %s AND account_id = %s", (property_id, account))
    return row["share_bps"] if row else 0


def _property(conn: Connection, property_id: int, *, lock: bool = False) -> dict:
    p = _one(conn, "SELECT p.*, d.city, d.kind AS district_kind, d.name AS district FROM properties p JOIN districts d ON d.id = p.district_id"
                   " WHERE p.id = %s" + (" FOR UPDATE OF p" if lock else ""), (property_id,))
    if p is None:
        raise PropertyError("There is no such property.")
    return p


def set_upkeep(conn: Connection, account, property_id: int, on: bool) -> None:
    with conn.transaction():
        p = _property(conn, property_id, lock=True)
        if share_of(conn, property_id, account) < 5000:
            raise PropertyError("Only an owner of at least half of a property decides its upkeep.")
        conn.execute("UPDATE properties SET upkeep = %s WHERE id = %s", (on, p["id"]))


def renovate(conn: Connection, account, property_id: int, now: datetime) -> dict:
    """Renovate a building: 5% of its value, paid to the builders, for 25 points of condition."""
    with conn.transaction():
        state = _state(conn, now)
        p = _property(conn, property_id, lock=True)
        if share_of(conn, property_id, account) < 5000:
            raise PropertyError("Only an owner of at least half of a property orders building work.")
        if p["status"] != "standing" or p["kind"] == "land":
            raise PropertyError("There is no building here to renovate. Build first.")
        if p.get("frozen"):
            raise PropertyError("A family dispute over it freezes it: nothing may be done with it until the owner settles it.")
        if p["condition"] >= 100:
            raise PropertyError("It is already in perfect condition.")
        d = districts(conn)[p["district_id"]]
        cost = value(p, d, policy_rate(conn)) * data.RENOVATION_BPS // BPS
        if ledger.balance(conn, account) < cost:
            raise PropertyError(f"A renovation costs {money(cost)}. There is not the cash.")
        paid = _pay_builders(conn, account, cost, p["city"], f"Renovating {p['name']}", state["period"])
        conn.execute("UPDATE properties SET condition = least(condition + %s, 100) WHERE id = %s", (data.RENOVATION_POINTS, p["id"]))
        return {"cost": paid}


def wear_without_upkeep(conn: Connection, property_id: int, periods: int = 1) -> None:
    """Reduce a property's condition as if it went periods without upkeep."""
    wear = 10 * periods
    conn.execute("UPDATE properties SET condition = greatest(condition - %s, 0) WHERE id = %s", (wear, property_id))


def build_cost(p: dict, kind: str | None = None) -> int:
    """What a building costs to put up: by its size and the city, and (the gap stage) more for a hotel or a mall."""
    return apply_bps(apply_bps(naira(data.BUILD_A_METRE_NAIRA) * p["size_m2"], data.CITY_COST_BPS[p["city"]]),
                     data.BUILD_KIND_BPS.get(kind or "", BPS))


def build(conn: Connection, account, property_id: int, now: datetime, *, kind: str | None = None) -> dict:
    """Put up a building on an empty plot (or rebuild a fallen one), at a builder's turnkey price: of the kind named,
    or the district's own kind, as the plot's zone allows."""
    from simulation import conveyancing, zoning
    with conn.transaction():
        state = _state(conn, now)
        p = _property(conn, property_id, lock=True)
        if share_of(conn, property_id, account) < BPS:
            raise PropertyError("Only the sole owner of a plot may build on it.")
        if p["status"] == "standing" and p["kind"] != "land":
            raise PropertyError("A building already stands here.")
        conveyancing.not_frozen(p)
        if _one(conn, "SELECT to_regclass('developments') IS NOT NULL AS ok")["ok"] and \
                _one(conn, "SELECT 1 FROM developments WHERE property_id = %s AND status IN ('permit', 'building')", (property_id,)):
            raise PropertyError("It is being developed already.")
        chosen = zoning.check_build(p, kind) if "zone" in p else (kind or data.DISTRICT_BUILDINGS[p["district_kind"]][0])
        cost = build_cost(p, chosen)
        if ledger.balance(conn, account) < cost:
            raise PropertyError(f"Building here costs {money(cost)}. There is not the cash.")
        _pay_builders(conn, account, cost, p["city"], f"Building on {p['name']}", state["period"])
        kind = chosen if (kind or p["kind"] == "land") else p["kind"]
        if "zone" in p and not zoning.allows(p["zone"], kind):
            kind = chosen
        conn.execute("UPDATE properties SET kind = %s, status = 'standing', condition = 100, base_rent = %s, built_period = %s WHERE id = %s",
                     (kind, base_rent(p["city"], kind, p["size_m2"]), state["period"], p["id"]))
        return {"cost": cost, "kind": kind}


def title_search(conn: Connection, account, property_id: int, now: datetime) -> dict:
    """The lands registry's search: whether the seller truly owns all of the property. A fee to the Government."""
    with conn.transaction():
        state = _state(conn, now)
        p = _property(conn, property_id)
        fee = max(p["land_value"] // 500, naira(20_000))
        try:
            ledger.transfer(conn, payer=account, receiver=ledger.account_id(conn, ledger.TREASURY), amount=fee, kind="property_tax",
                            memo=f"Title search at the lands registry: {p['name']}", period=state["period"])
        except ledger.InsufficientFunds:
            raise PropertyError(f"A title search costs {money(fee)}.") from None
        flaw = p["title_flaw_bps"]
        return {"fee": fee, "clean": flaw == 0,
                "words": ("The registry's records show the seller owns all of it." if flaw == 0 else
                          f"The registry shows another claim on {flaw / 100:.0f}% of it: the seller does not truly own that part.")}


# ---------------------------------------------------------------------------
# Mortgages
# ---------------------------------------------------------------------------

def mortgage_limit(conn: Connection, account, price: int, now: datetime, *, except_auction: int | None = None,
                   except_sale: int | None = None) -> int:
    """The most a bank will lend this account against a property at this price."""
    from simulation import careers
    kind = _one(conn, "SELECT kind FROM ledger_accounts WHERE id = %s", (account,))["kind"]
    if kind == "player":
        player = _one(conn, "SELECT player_id FROM ledger_accounts WHERE id = %s", (account,))["player_id"]
        job = careers.current_job(conn, player)
        mine = careers.career(conn, player)
        if job is None or mine is None:
            return 0
        state = careers.world_now(conn, now)
        salary = careers.salary_per_quarter(mine["level"], state["wage_index_bps"])
        owed = _one(conn, "SELECT coalesce(sum(outstanding), 0)::bigint AS o FROM mortgages WHERE borrower = %s AND status IN ('open', 'shortfall')",
                    (account,))["o"]
        # A mortgage promised behind a bid still standing counts too: one salary cannot back many bids at once.
        owed += _one(conn, "SELECT coalesce(sum(limit_price * mortgage_bps / 10000), 0)::bigint AS o FROM auction_bids"
                           " WHERE bidder = %s AND status = 'live' AND mortgage_bps > 0 AND auction_id IS DISTINCT FROM %s",
                     (account, except_auction))["o"]
        # ...and one promised on a private purchase agreed but not yet signed (the gap stage).
        if _one(conn, "SELECT to_regclass('property_sales') IS NOT NULL AS ok")["ok"]:
            owed += _one(conn, "SELECT coalesce(sum(mortgage), 0)::bigint AS o FROM property_sales WHERE buyer = %s"
                               " AND status IN ('agreed', 'consent') AND id IS DISTINCT FROM %s", (account, except_sale))["o"]
        return max(min(salary * data.MORTGAGE_SALARY_QUARTERS - owed, price * (BPS - data.MORTGAGE_DEPOSIT_BPS) // BPS), 0)
    if kind == "empire":
        return price * data.EMPIRE_MORTGAGE_MOST_BPS // BPS
    return 0


def lending_banks(conn: Connection, period: int) -> list[dict]:
    from simulation import banking
    # (A bank's mortgages count with its other lending against the limit its owners' funds set.)
    return [{**b, "room": banking.lending_room(b)} for b in banking.banks(conn, period)]


def take_mortgage(conn: Connection, borrower, bank_company_id, property_id: int, amount: int, period: int, now: datetime) -> int:
    """The bank lends against a property just bought (inside the purchase's own transaction)."""
    bank = _one(conn, "SELECT id, account_id, name FROM companies WHERE id = %s", (bank_company_id,))
    rate = policy_rate(conn) + data.MORTGAGE_SPREAD_BPS
    ledger.transfer(conn, payer=bank["account_id"], receiver=borrower, amount=amount, kind="mortgage_loan",
                    memo=f"A mortgage from {bank['name']}", period=period)
    conn.execute("INSERT INTO mortgages (property_id, borrower, bank_company_id, principal, outstanding, rate_bps, taken_period, term_quarters, at)"
                 " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                 (property_id, borrower, bank_company_id, amount, amount, rate, period, data.MORTGAGE_TERM_QUARTERS, now))
    return amount


def repay_mortgage(conn: Connection, account, mortgage_id: int, amount: int, now: datetime) -> dict:
    with conn.transaction():
        state = _state(conn, now)
        m = _one(conn, "SELECT m.*, c.account_id AS bank_account, c.name AS bank_name FROM mortgages m JOIN companies c ON c.id = m.bank_company_id"
                       " WHERE m.id = %s AND m.borrower = %s AND m.status IN ('open', 'shortfall') FOR UPDATE OF m", (mortgage_id, account))
        if m is None:
            raise PropertyError("There is no such mortgage of yours.")
        if not isinstance(amount, int) or amount <= 0:
            raise PropertyError("Name an amount to repay.")
        amount = min(amount, m["outstanding"])
        try:
            ledger.transfer(conn, payer=account, receiver=m["bank_account"], amount=amount, kind="mortgage_repayment",
                            memo=f"Mortgage repaid early to {m['bank_name']}", period=state["period"])
        except ledger.InsufficientFunds:
            raise PropertyError("There is not the cash.") from None
        left = m["outstanding"] - amount
        conn.execute("UPDATE mortgages SET outstanding = %s, status = %s, missed = 0 WHERE id = %s",
                     (left, "repaid" if left == 0 else m["status"], m["id"]))
        return {"left": left}


# ---------------------------------------------------------------------------
# What players see
# ---------------------------------------------------------------------------

def public_property(conn: Connection, p: dict, d: dict, rate: int, *, viewer=None) -> dict:
    """A property as anybody may see it. Never its title's flaw, nor a property company's book value."""
    owners = holdings(conn, p["id"])
    names = []
    for h in owners:
        if h["account_kind"] == "company":
            names.append(h["account_name"])
        elif h["account_kind"] == "empire":
            names.append(h["account_name"])
        elif h["account_kind"] == "player":
            names.append("A player" if h["account_id"] != viewer else "You")
        else:
            names.append(h["account_name"])
    mine = next((h["share_bps"] for h in owners if h["account_id"] == viewer), 0) if viewer else 0
    return {"id": p["id"], "name": p["name"], "kind": p["kind"], "kind_name": data.PROPERTY_KIND_NAMES[p["kind"]],
            "district_id": p["district_id"], "district": d["name"], "city": d["city"], "size_m2": p["size_m2"],
            "condition": p["condition"], "status": p["status"], "value": value(p, d, rate), "rent_due": rent_due(p, d),
            "owners": names, "my_share_bps": mine, "upkeep": p["upkeep"],
            "build_cost": build_cost({**p, "city": d["city"]}) if p["status"] != "standing" or p["kind"] == "land" else None,
            "zone": p.get("zone"), "zone_name": data.ZONE_NAMES.get(p.get("zone"), ""),
            "may_build": list(data.ZONE_ALLOWS.get(p.get("zone"), ())), "frozen": bool(p.get("frozen")),
            "beside_works": bool(p.get("beside_project")), "right_of_way": bool(p.get("value_cut_bps"))}


def market_view(conn: Connection, viewer=None) -> dict:
    rate = policy_rate(conn)
    ds = districts(conn)
    history = defaultdict(list)
    for r in _rows(conn, "SELECT * FROM district_results ORDER BY period, district_id"):
        history[r["district_id"]].append({"period": r["period"], "label": clock.period_label(r["period"]) if r["period"] else "Start",
                                          "price_bps": r["price_bps"], "rent_bps": r["rent_bps"], "occupancy_bps": r["occupancy_bps"]})
    out = []
    for d in ds.values():
        props = _rows(conn, "SELECT * FROM properties WHERE district_id = %s ORDER BY id", (d["id"],))
        out.append({"id": d["id"], "name": d["name"], "city": d["city"], "kind": d["kind"], "kind_name": data.DISTRICT_KIND_NAMES[d["kind"]],
                    "rent_bps": d["rent_bps"], "occupancy_bps": d["occupancy_bps"], "price_bps": d["rent_bps"] * (BPS + d["premium_bps"]) // BPS,
                    "infra_bps": d.get("infra_bps", 0),
                    "history": history[d["id"]][-13:],
                    "properties": [public_property(conn, p, d, rate, viewer=viewer) for p in props]})
    from simulation import homes, infrastructure
    return {"districts": out, "yield_bps": yield_bps(rate), "mortgage_rate_bps": rate + data.MORTGAGE_SPREAD_BPS,
            "tax_bps": data.PROPERTY_TAX_BPS + data.LAND_TAX_BPS, "infrastructure": infrastructure.view(conn),
            "home_loans": homes.summary(conn), "zones": [{"zone": z, "name": data.ZONE_NAMES[z], "allows": list(data.ZONE_ALLOWS[z])}
                                                         for z in data.ZONES]}


def mine_view(conn: Connection, account, now: datetime) -> dict:
    rate = policy_rate(conn)
    ds = districts(conn)
    props = []
    for p in _rows(conn, "SELECT p.*, h.share_bps, h.paid FROM properties p JOIN property_holdings h ON h.property_id = p.id"
                         " WHERE h.account_id = %s ORDER BY p.id", (account,)):
        d = ds[p["district_id"]]
        last = _one(conn, "SELECT * FROM property_results WHERE property_id = %s ORDER BY period DESC LIMIT 1", (p["id"],))
        props.append({**public_property(conn, p, d, rate, viewer=account), "share_bps": p["share_bps"], "paid": p["paid"],
                      "tax_owed": p["tax_owed"] * p["share_bps"] // BPS,
                      "last_rent": last["rent_paid"] if last else 0, "last_tax": last["tax"] if last else 0})
    mortgages = [{"id": m["id"], "property_id": m["property_id"], "bank": m["bank"], "principal": m["principal"], "outstanding": m["outstanding"],
                  "rate_bps": m["rate_bps"], "missed": m["missed"], "status": m["status"]}
                 for m in _rows(conn, "SELECT m.*, c.name AS bank FROM mortgages m JOIN companies c ON c.id = m.bank_company_id"
                                      " WHERE m.borrower = %s AND m.status IN ('open', 'shortfall') ORDER BY m.id", (account,))]
    eq = equity_of(conn, account)
    from simulation import conveyancing, development, leaseback, zoning
    for p in props:
        p["claims"] = conveyancing.known_claims(conn, p["id"])
    return {"properties": props, "mortgages": mortgages, "leases": leaseback.view(conn, account), "sales": conveyancing.view(conn, account, now),
            "developments": development.view(conn, account), "rezonings": zoning.view(conn, account), **eq}


def summary(conn: Connection) -> dict:
    """For the Economy page: property prices and rents by city."""
    rows = _rows(conn, """
        SELECT d.city, r.period, avg(r.price_bps)::int AS price_bps, avg(r.rent_bps)::int AS rent_bps, avg(r.occupancy_bps)::int AS occupancy_bps,
               sum(r.sold)::int AS sold, sum(r.sold_value)::bigint AS sold_value
        FROM district_results r JOIN districts d ON d.id = r.district_id GROUP BY d.city, r.period ORDER BY d.city, r.period""")
    by_city = defaultdict(list)
    for r in rows:
        by_city[r["city"]].append({"period": r["period"], "label": clock.period_label(r["period"]) if r["period"] else "Start",
                                   "price_bps": r["price_bps"], "rent_bps": r["rent_bps"], "occupancy_bps": r["occupancy_bps"],
                                   "sold": r["sold"], "sold_value": r["sold_value"]})
    return {"cities": [{"city": c, "history": h[-13:]} for c, h in by_city.items()]}


def _players_property(conn: Connection) -> dict:
    """For players' net worth: property at today's prices less what is owed on it, and cash held for bids."""
    out = {}
    if _one(conn, "SELECT to_regclass('property_holdings') IS NOT NULL AS ok")["ok"] is not True:
        return out
    accounts = {r["account_id"] for r in _rows(conn, "SELECT DISTINCT h.account_id FROM property_holdings h JOIN ledger_accounts a ON a.id = h.account_id"
                                                     " WHERE a.kind = 'player' UNION SELECT DISTINCT borrower FROM mortgages WHERE status IN ('open', 'shortfall')")}
    for account in accounts:
        out[account] = (0, equity_of(conn, account)["equity"])
    for r in _rows(conn, "SELECT bidder, sum(held)::bigint AS held FROM auction_bids WHERE status = 'live' GROUP BY bidder"):
        cash, inv = out.get(r["bidder"], (0, 0))
        out[r["bidder"]] = (cash + int(r["held"]), inv)
    for r in _rows(conn, "SELECT partner, sum(held)::bigint AS held FROM auction_partners WHERE status = 'agreed' GROUP BY partner"):
        cash, inv = out.get(r["partner"], (0, 0))
        out[r["partner"]] = (cash + int(r["held"]), inv)
    return out


def _register() -> None:
    from simulation import marketview
    if _players_property not in marketview._OTHER_HOLDINGS:
        marketview._OTHER_HOLDINGS.append(_players_property)


_register()


def _close_moment(conn: Connection, period: int) -> datetime:
    """The moment a quarter ended, by the world's own calendar."""
    w = _one(conn, "SELECT world_start, weeks_ahead FROM world_state")
    return clock.effective_start(w["world_start"], w["weeks_ahead"]) + timedelta(days=clock.REAL_DAYS_PER_QUARTER * period)
