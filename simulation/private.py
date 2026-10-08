"""Private companies: owned by their founders (or, once bought, by an empire), never traded on the exchange.

They are real companies in the same economy as the listed ones: households and other companies buy
from them, they pay wages, tax and interest, and every naira moves through the ledger. What makes
them different:

  * their accounts are not published. An empire sees them only in a data room, after signing a
    confidentiality agreement, and the founders' papers do not always tell the truth (`secrets`);
  * they own assets that are bought, kept up, worn out and sold: planes, hotels, vessels, plant;
  * a company an empire controls is run by that empire's dials: prices, staff and pay, marketing,
    technology, upkeep, dividends, borrowing and new assets. Rival companies react to its prices;
  * an airline flies routes between the five cities, at fares set against its rivals'.

This module holds the world's side of it: the setup at the world's start, what the dials do to a
company's quarter, wear and morale, the founders putting companies up for sale, start-ups, and
administration. Buying, running and selling them is the empire's side (firm_deals, firm_owned).
"""

from __future__ import annotations

import hashlib
from datetime import datetime

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from simulation import clock, ledger
from simulation import world_data as data
from simulation.ledger import Leg
from simulation.money import BPS, apply_bps, million_naira, naira

CITIES = (data.LAGOS, data.ABUJA, data.PORT_HARCOURT, data.ABA, data.KANO)

# What each industry's assets are called, and how many quarters one lasts when kept up.
ASSETS: dict[str, tuple[str, str, int]] = {
    "aviation": ("plane", "planes", 60), "hospitality": ("hotel", "hotels", 120), "shipping": ("vessel", "vessels", 80),
    "consumer": ("kitchen line", "kitchen lines", 48), "oil_gas": ("fuel depot", "fuel depots", 80),
    "telecoms": ("data hall", "data halls", 60), "cement": ("kiln", "kilns", 80), "agriculture": ("farm", "farms", 100),
    "real_estate": ("estate", "estates", 120), "manufacturing": ("factory line", "factory lines", 60),
    "media": ("studio", "studios", 60), "power": ("mini-grid", "mini-grids", 80), "transport": ("truck fleet", "truck fleets", 40),
    "banking": ("branch", "branches", 120), "insurance": ("office", "offices", 120),
}
HANGAR_LIFE = 120
HANGAR_SHARE_BPS = 1500           # an airline's hangars: this share of what it owns
SPARE_CAPACITY_BPS = 12_500       # on day one, its assets could serve a quarter of a fifth more than it sells
GROUNDED_BELOW_BPS = 2000         # an asset in worse condition than this stops working until repaired
REPAIR_COST_BPS = 1500            # repairing a grounded asset costs this share of its price
WEAR_UNKEPT_BPS = 2               # an asset not kept up wears this many times faster
SALE_CHANCE_BPS = 1500            # each quarter, the chance the founders put a company up for sale...
SALES_A_QUARTER = 3               # ...and no more than this many new sales at once
STARTUP_EVERY = 4                 # a start-up is founded once a year
MANAGER_PAY_BPS = {1: 30, 2: 45, 3: 60, 4: 90, 5: 140}    # a managing director's pay a quarter, in hundredths of a percent of sales
MANAGER_COST_BPS = {1: 150, 2: 75, 3: 0, 4: -75, 5: -150}  # ...and what each does to the cost of making what it sells
MANAGER_PULL_BPS = {1: -300, 2: -150, 3: 0, 4: 150, 5: 300}
MORALE_SLOW_BPS = 8500            # below this, the staff work slowly and customers notice
MORALE_WALKOUT_BPS = 6500         # below this, the staff walk out for part of the quarter
MARKETING_PULL_LIMIT_BPS = 1500   # marketing can add at most this much to a company's pull
MARKETING_FADE_BPS = 2000         # what marketing won fades by a fifth each quarter
TECH_SAVING_LIMIT_BPS = 1500      # technology can take at most this many points of sales off its costs
ROUTE_PULL_BPS = 10_000
RIVAL_NOTICE_BPS = 1000           # rivals answer an owned company's price cut only once it has 5% of the industry (weighted twice)

SECRET_NAMES = {
    "dressed_revenue": "Its accounts overstate its sales",
    "hidden_debt": "A tax bill it has not disclosed is coming",
    "customer_leaving": "Its largest customer is about to leave",
    "worn_assets": "Its assets are in far worse condition than its papers say",
    "ownership_claim": "A former partner claims part of the company",
    "contract_coming": "A large new contract is about to be signed",
    "underpriced": "It is offered for well below what it is worth",
}
TRAPS = ("dressed_revenue", "hidden_debt", "customer_leaving", "worn_assets", "ownership_claim")

# Start-ups founded during the game: one a year, while the founders have the money.
STARTUPS: tuple[data.Company, ...] = (
    data.Company("YBK", "Yaba Bike Couriers", "transport", data.LAGOS, 3_000, lender="OTB", listed=False, trend_bps=500),
    data.Company("WSE", "Wuse Solar Estates", "power", data.ABUJA, 2_500, lender="HMB", listed=False, trend_bps=500),
    data.Company("AFT", "Ariaria Fashion Tech", "manufacturing", data.ABA, 2_000, lender="KCB", listed=False, trend_bps=600),
    data.Company("NCS", "Nupe Cold Storage", "agriculture", data.KANO, 3_500, lender="ZCB", listed=False, trend_bps=400),
    data.Company("BSP", "Bonny Sea Ports", "shipping", data.PORT_HARCOURT, 4_000, lender="OBB", listed=False, trend_bps=400),
    data.Company("LGA", "Lagoon Air Charter", "aviation", data.LAGOS, 4_500, lender="IKB", listed=False, trend_bps=500),
    data.Company("TBH", "Tinapa Boutique Hotels", "hospitality", data.PORT_HARCOURT, 2_000, lender="OBB", listed=False, trend_bps=500),
    data.Company("KDS", "Kaduna Dairy Startups", "consumer", data.KANO, 2_500, lender="ZCB", listed=False, trend_bps=500),
    data.Company("LPS", "Lekki Pay Systems", "telecoms", data.LAGOS, 3_000, lender="IKB", listed=False, trend_bps=700),
    data.Company("ABP", "Abuja Podcasts", "media", data.ABUJA, 1_500, lender="HMB", listed=False, trend_bps=600),
)


def _rows(conn: Connection, sql: str, params=()) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def _one(conn: Connection, sql: str, params=()) -> dict | None:
    rows = _rows(conn, sql, params)
    return rows[0] if rows else None


def roll(seed: str, *parts) -> int:
    """A number from 0 to 9999, fixed by the world's secret and what it is for."""
    digest = hashlib.sha256(":".join([seed, *map(str, parts)]).encode()).digest()
    return int.from_bytes(digest[:4], "big") % BPS


def _seed(conn: Connection) -> str:
    return _one(conn, "SELECT fortune_seed FROM world_state")["fortune_seed"]


def money(kobo: int) -> str:
    amount = kobo / 100
    for size, word in ((1e12, "trillion"), (1e9, "billion"), (1e6, "million")):
        if abs(amount) >= size:
            return f"₦{amount / size:,.1f} {word}"
    return f"₦{amount:,.0f}"


# ---------------------------------------------------------------------------
# The world's start, and start-ups
# ---------------------------------------------------------------------------

def _pair_weight(a: str, b: str) -> int:
    """How much travel there is between two cities: their populations multiplied."""
    population = {loc.name: loc.population_bps for loc in data.LOCATIONS}
    return population[a] * population[b] // 100


def route_pairs() -> list[tuple[str, str]]:
    return [tuple(sorted((a, b))) for i, a in enumerate(CITIES) for b in CITIES[i + 1:]]


def _profile(conn: Connection, company: dict, seed: str, period: int, *, startup: bool = False) -> None:
    """Set out a private company: how well it is run, its assets, its managing director, its routes and its secrets."""
    ticker = company["ticker"]
    result = _one(conn, "SELECT * FROM company_results WHERE company_id = %s ORDER BY period DESC LIMIT 1", (company["id"],))
    quarter_sales = max(result["base_revenue"], 1)
    management = 1 + roll(seed, ticker, "management") % 5
    secrets = [] if startup else _draw_secrets(seed, ticker, quarter_sales)
    worn = any(s["code"] == "worn_assets" for s in secrets)
    conn.execute("INSERT INTO private_profiles (company_id, management, appeared_period, secrets) VALUES (%s, %s, %s, %s)",
                 (company["id"], management, period, Jsonb(secrets)))
    conn.execute("INSERT INTO company_managers (company_id, name, quality, pay, hired_period) VALUES (%s, %s, %s, %s, %s)",
                 (company["id"], _manager_name(seed, ticker, 0), management, apply_bps(quarter_sales, MANAGER_PAY_BPS[management]), period))
    kind, plural, life = ASSETS.get(company["sector"], ("plant", "plants", 60))
    fixed = result["fixed_assets"]
    count = 4 + roll(seed, ticker, "units") % 5 + (2 if company["sector"] == "aviation" else 0)
    hangars = 0
    if company["sector"] == "aviation":
        hangars = 1 + roll(seed, ticker, "hangars") % 2
        hangar_cost = max(apply_bps(fixed, HANGAR_SHARE_BPS) // hangars, 1)
        bases = [company["headquarters"]] + [c for c in CITIES if c != company["headquarters"]]
        for h in range(hangars):
            conn.execute("INSERT INTO company_assets (company_id, kind, name, base, cost, capacity, condition_bps, stated_bps, life_quarters,"
                         " age_quarters, bought_period) VALUES (%s, 'hangar', %s, %s, %s, 0, %s, %s, %s, %s, %s)",
                         (company["id"], f"Hangar at {bases[h]}", bases[h], hangar_cost, 9000, 9000, HANGAR_LIFE, 10, period))
        fixed -= hangar_cost * hangars
    cost = max(fixed // count, 1)
    capacity = apply_bps(quarter_sales, SPARE_CAPACITY_BPS) // count
    routes = []
    if company["sector"] == "aviation":
        pairs = [p for p in route_pairs() if company["headquarters"] in p]
        others = [p for p in route_pairs() if company["headquarters"] not in p]
        pairs = pairs[:3 + roll(seed, ticker, "routes") % 2] + others[:roll(seed, ticker, "routes2") % 2]
        for a, b in pairs:
            routes.append(_one(conn, "INSERT INTO airline_routes (company_id, city_a, city_b, opened_period) VALUES (%s, %s, %s, %s) RETURNING id",
                               (company["id"], a, b, period))["id"])
    for n in range(count):
        if startup:
            condition = BPS
        else:
            condition = 7000 + roll(seed, ticker, "condition", n) % 2600
        stated = condition
        if worn:
            condition = 3500 + roll(seed, ticker, "worn", n) % 1500
            stated = 8500 + roll(seed, ticker, "stated", n) % 1000
        age = life * (BPS - condition) // BPS
        conn.execute("INSERT INTO company_assets (company_id, kind, name, base, cost, capacity, condition_bps, stated_bps, life_quarters,"
                     " age_quarters, route_id, bought_period) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                     (company["id"], kind, f"{kind.capitalize()} {n + 1}", company["headquarters"], cost, capacity, condition, stated, life,
                      age, routes[n % len(routes)] if routes else None, period))
    if routes:
        conn.execute("UPDATE private_profiles SET route_base = %s WHERE company_id = %s",
                     (max(_route_score(conn, company["id"], {}), 1), company["id"]))


def _manager_name(seed: str, ticker: str, n: int) -> str:
    first = ("Adaeze", "Babatunde", "Chinedu", "Damilola", "Emeka", "Funmilayo", "Garba", "Halima", "Ifeanyi", "Jumoke",
             "Kelechi", "Lami", "Musa", "Ngozi", "Olumide", "Oluchi", "Rabiu", "Sade", "Tamuno", "Uche", "Yetunde", "Zainab")
    last = ("Adeyemi", "Bello", "Chukwu", "Danjuma", "Eze", "Fashola", "Ibrahim", "Johnson", "Kalu", "Lawal", "Mohammed",
            "Nwosu", "Okafor", "Ogunleye", "Pepple", "Sani", "Uzor", "Yusuf")
    return f"{first[roll(seed, ticker, 'mf', n) % len(first)]} {last[roll(seed, ticker, 'ml', n) % len(last)]}"


def _draw_secrets(seed: str, ticker: str, quarter_sales: int) -> list[dict]:
    """What a private company's papers do not say. Fixed by the world's secret, so nobody can know it in advance."""
    out = []
    for slot in range(2):
        r = roll(seed, ticker, "secret", slot)
        if slot == 1 and r % 10 >= 3:
            break
        pick = r % 10
        code = {0: "dressed_revenue", 1: "dressed_revenue", 2: "hidden_debt", 3: "customer_leaving", 4: "worn_assets",
                5: "ownership_claim", 6: "contract_coming", 7: "underpriced"}.get(pick)
        if code is None or any(s["code"] == code for s in out):
            continue
        size = roll(seed, ticker, "size", slot)
        secret = {"code": code, "bps": 0, "amount": 0, "from_period": None, "done": False}
        if code == "dressed_revenue":
            secret["bps"] = 1000 + size % 1500                       # sales shown 10% to 25% higher than they were
        elif code == "hidden_debt":
            secret["amount"] = apply_bps(quarter_sales, 3000 + size % 5000)
        elif code == "customer_leaving":
            secret["bps"] = -(1500 + size % 1000)
        elif code == "contract_coming":
            secret["bps"] = 1200 + size % 800
        elif code == "ownership_claim":
            secret["bps"] = 500 + size % 700                         # the share of the company the former partner claims
        elif code == "underpriced":
            secret["bps"] = 2000 + size % 1000                       # asked for 20% to 30% below its worth
        out.append(secret)
    return out


def setup(conn: Connection, seed: str) -> None:
    """At the world's start: every private company is set out."""
    for company in _rows(conn, "SELECT c.* FROM companies c WHERE NOT c.listed AND NOT EXISTS"
                               " (SELECT 1 FROM private_profiles p WHERE p.company_id = c.id) ORDER BY c.ticker"):
        _profile(conn, company, seed, 0)


def found_startup(conn: Connection, period: int, seed: str, now: datetime) -> dict | None:
    """Once a year the founders put their own money into a new company. It buys its first assets from
    other companies at once. Nothing is created: every naira comes from the founders' cash."""
    from simulation import companies, genesis
    taken = {r["ticker"] for r in _rows(conn, "SELECT ticker FROM companies")}
    choices = [s for s in STARTUPS if s.ticker not in taken]
    if not choices:
        return None
    spec = choices[roll(seed, "startup", period) % len(choices)]
    sector = next(s for s in data.SECTORS if s.code == spec.sector)
    shape = genesis._company_shape(len(taken), spec, sector)
    shape = {k: apply_bps(v, _price_index(conn, period - 1)) if k in ("base_revenue", "base_opex", "wages", "cash", "fixed_assets") else v
             for k, v in shape.items()}
    founders = ledger.account_id(conn, ledger.INVESTORS_FOUNDERS)
    needed = shape["cash"] + shape["fixed_assets"]
    if ledger.balance(conn, founders) < needed * 3:
        return None
    account = ledger.create_account(conn, kind="company", name=spec.name, code=f"company:{spec.ticker}")
    asset = f"SHR-{spec.ticker}"
    ledger.create_asset(conn, code=asset, kind="share", name=f"{spec.name} ordinary shares", unit="share", issuer_account_id=account)
    company_id = _one(conn, "INSERT INTO companies (ticker, name, sector, headquarters, account_id, share_asset, revenue_growth_bps, season_bps,"
                            " cost_of_sales_bps, opex_growth_bps, depreciation_bps, payout_bps, volatility_bps, location_cost_bps, opex_bps,"
                            " labour_bps, listed) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, false) RETURNING id",
                      (spec.ticker, spec.name, spec.sector, spec.headquarters, account, asset, shape["revenue_growth_bps"],
                       list(sector.season_bps), shape["cost_of_sales_bps"], shape["revenue_growth_bps"], data.DEPRECIATION_BPS,
                       sector.payout_bps, shape["volatility_bps"], shape["location_cost_bps"], shape["opex_bps"], shape["labour_bps"]))["id"]
    shares = max(round(needed / naira(data.BOOK_VALUE_PER_SHARE_NAIRA) / data.SHARE_LOT), 1) * data.SHARE_LOT
    ledger.post(conn, kind="share_issue", memo=f"{spec.name}: founded, its founders putting in {money(needed)}", period=period - 1,
                legs=[Leg(account, -shares, asset), Leg(founders, shares, asset), Leg(founders, -needed), Leg(account, needed)])
    world = _economy().load_world(conn)
    world.members = {}
    for row in _rows(conn, "SELECT c.account_id, c.headquarters, c.sector, r.base_revenue FROM companies c JOIN company_results r"
                           " ON r.company_id = c.id AND r.period = %s WHERE c.status = 'trading'", (period - 1,)):
        world.members.setdefault(row["sector"], []).append({"account_id": row["account_id"], "headquarters": row["headquarters"],
                                                            "pull": max(row["base_revenue"], 1)})
    weights = {sector: row["investment_bps"] for sector, row in world.demand.items()}
    bought = ledger.pay_split_up_to(conn, payer=account, amounts=_economy().allocate(world, shape["fixed_assets"], weights,
                                                                                   location=spec.headquarters, exclude=account),
                                    kind="capital_spending", memo=f"{spec.name}: its first buildings and machines", period=period - 1)
    cash = ledger.balance(conn, account)
    result = {
        "company_id": company_id, "period": period - 1, "revenue": 0, "interest_income": 0, "cost_of_sales": 0, "operating_expenses": 0,
        "depreciation": 0, "operating_profit": 0, "interest_expense": 0, "profit_before_tax": 0, "tax": 0, "net_profit": 0,
        "cash_opening": cash, "cash_from_operations": 0, "cash_from_investing": 0, "cash_from_financing": 0, "cash_closing": cash,
        "capital_spending": 0, "debt_repaid": 0, "dividends_paid": 0, "cash": cash, "customer_loans": 0, "loans_to_companies": 0,
        "fixed_assets": bought, "investments": 0, "total_assets": cash + bought, "borrowings": 0, "payables": 0, "customer_funds": 0,
        "total_liabilities": 0, "share_capital": cash + bought, "retained_earnings": 0, "total_equity": cash + bought,
        "principal_overdue": 0, "shares_in_issue": shares, "base_revenue": shape["base_revenue"], "base_opex": shape["base_opex"],
        "ledger_totals": companies.ledger_totals(conn, account), "drivers": {"revenue": [], "notes": ["A new company, founded this quarter."]},
        "staff": shape["staff"], "wages": shape["wages"], "sales_households": 0, "sales_business": 0, "sales_government": 0,
    }
    companies.insert_result(conn, result)
    company = _one(conn, "SELECT * FROM companies WHERE id = %s", (company_id,))
    companies.file_report(conn, company, result)
    _profile(conn, company, seed, period, startup=True)
    _news(conn, period, 3, "startup", f"startup:{spec.ticker}",
          {"company": spec.name, "sector": _sector_words(spec.sector), "city": spec.headquarters, "amount": money(needed)})
    return company


def _news(conn: Connection, period: int, day: int, kind: str, story: str, facts: dict) -> None:
    from simulation import news
    news.publish(conn, period=period, day=day, kind=kind, story=story, facts=facts)


def _sector_words(code: str) -> str:
    from simulation import news
    return news.SECTOR_WORDS.get(code, code)


def _economy():
    from simulation import economy
    return economy


def _price_index(conn: Connection, period: int) -> int:
    row = _one(conn, "SELECT price_index_bps FROM economy_results WHERE period <= %s ORDER BY period DESC LIMIT 1", (period,))
    return row["price_index_bps"] if row else BPS


# ---------------------------------------------------------------------------
# Who controls a company
# ---------------------------------------------------------------------------

def controller(conn: Connection, company_id) -> dict | None:
    """The empire that controls a company it bought, if any."""
    return _one(conn, "SELECT o.*, e.name AS empire_name, e.kind AS empire_kind, e.head_player_id FROM owned_companies o"
                      " JOIN empires e ON e.id = o.empire_id WHERE o.company_id = %s", (company_id,))


def profile(conn: Connection, company_id) -> dict | None:
    return _one(conn, "SELECT * FROM private_profiles WHERE company_id = %s", (company_id,))


def dials_for(conn: Connection, company_id, period: int) -> dict | None:
    """The dials in force for a quarter: the latest set for it or before, by the empire that controls it now
    (a new owner does not inherit the last owner's dials)."""
    return _one(conn, "SELECT d.* FROM company_dials d JOIN owned_companies o ON o.company_id = d.company_id AND d.at >= o.since"
                      " WHERE d.company_id = %s AND d.period <= %s ORDER BY d.period DESC LIMIT 1", (company_id, period))


def manager(conn: Connection, company_id) -> dict | None:
    return _one(conn, "SELECT * FROM company_managers WHERE company_id = %s AND left_period IS NULL", (company_id,))


def assets(conn: Connection, company_id, *, all_: bool = False) -> list[dict]:
    return _rows(conn, "SELECT * FROM company_assets WHERE company_id = %s" + ("" if all_ else " AND status IN ('working', 'grounded')")
                       + " ORDER BY kind, id", (company_id,))


def capacity(conn: Connection, company_id, period: int) -> int:
    """What its working assets could serve this quarter, in today's money. Worn assets serve less."""
    index = _price_index(conn, period - 1)
    total = 0
    for asset in assets(conn, company_id):
        if asset["status"] != "working" or asset["capacity"] == 0:
            continue
        if asset["route_id"] is None and _is_airline(conn, company_id):
            continue                                   # a plane with no route earns nothing
        total += apply_bps(apply_bps(asset["capacity"], 5000 + asset["condition_bps"] // 2), index)
    return total


def _is_airline(conn: Connection, company_id) -> bool:
    return _one(conn, "SELECT sector FROM companies WHERE id = %s", (company_id,))["sector"] == "aviation"


def _route_score(conn: Connection, company_id, fares: dict) -> int:
    """An airline's pull from its routes: travel between the cities it flies, at its fares against its rivals'."""
    score = 0
    for route in _rows(conn, "SELECT r.*, (SELECT count(*) FROM company_assets a WHERE a.route_id = r.id AND a.status = 'working') AS planes"
                             " FROM airline_routes r WHERE r.company_id = %s AND r.closed_period IS NULL", (company_id,)):
        if route["planes"] == 0:
            continue
        pair = (route["city_a"], route["city_b"])
        rivals = [f for (cid, p), f in fares.items() if p == pair and cid != company_id]
        against = sum(rivals) // len(rivals) if rivals else BPS
        own = fares.get((company_id, pair), route["fare_bps"])
        fare_factor = max(BPS - 15_000 * (own - against) // BPS, 2000)
        score += _pair_weight(*pair) * fare_factor // BPS * min(route["planes"], 3)
    return score


def _fares(conn: Connection) -> dict:
    return {(r["company_id"], (r["city_a"], r["city_b"])): r["fare_bps"]
            for r in _rows(conn, "SELECT company_id, city_a, city_b, fare_bps FROM airline_routes WHERE closed_period IS NULL")}


# ---------------------------------------------------------------------------
# A quarter: what the dials, the assets, the managers and the staff do to a company
# ---------------------------------------------------------------------------

def elasticity_bps(mix: dict[str, int]) -> int:
    """How much a location's customers move when prices change: bargain-hunters and the restless move
    more, loyal and cautious customers less."""
    moves = mix.get("opportunistic", 0) + mix.get("risk_seeking", 0) + mix.get("sceptical", 0)
    stays = mix.get("loyal", 0) + mix.get("risk_averse", 0)
    return max(15_000 + moves - stays, 5000)


def price_factor(price_bps: int, elasticity: int) -> int:
    """A company's pull on customers at its prices, against prices in line with its rivals (10000)."""
    if price_bps == BPS:
        return BPS
    return max(BPS - elasticity * (price_bps - BPS) // BPS, 1000)


def before_close(conn: Connection, companies: list[dict], period: int, wage_index_bps: int) -> None:
    """Put this quarter's dials, managers, assets, routes, staff morale and secrets into each company's
    figures before the economy runs. A listed company is changed only by its own prices."""
    fares = _fares(conn)
    profiles = {r["company_id"]: r for r in _rows(conn, "SELECT * FROM private_profiles")}
    controlled = {r["company_id"] for r in _rows(conn, "SELECT company_id FROM owned_companies")}
    lasts = {r["company_id"]: r for r in _rows(conn, "SELECT company_id, revenue, base_revenue, period FROM company_results WHERE period = %s",
                                                     (period - 1,))}
    for company in companies:
        price = company["price_bps"]
        if price != BPS:
            # Dearer goods sell fewer for the same money: the cost of making them falls as a share of sales.
            company["labour_bps"] = company["labour_bps"] * BPS // price
        p = profiles.get(company["id"])
        if p is None or company["listed"]:
            continue                                   # a listed company (even one that was private) is run by its own board
        # Only an empire that controls the company sets its dials; the founders run it as it has always been run.
        dials = dials_for(conn, company["id"], period) if company["id"] in controlled else None
        boss = manager(conn, company["id"])
        quality = boss["quality"] if boss else 3
        company["labour_bps"] = max(company["labour_bps"] + p["labour_adj_bps"] + MANAGER_COST_BPS[quality], 0)
        opex = apply_bps(company["opex_bps"], BPS + p["opex_adj_bps"])
        ratio = p["pay_index_bps"] * BPS // max(wage_index_bps, 1)          # its pay against the going rate
        if dials:
            opex = apply_bps(opex, dials["staff_bps"])
            company["payout_bps"] = dials["payout_bps"]
            company["upkeep_bps"] = dials["maintenance_bps"]
            if dials["period"] == period:                       # borrowing and new assets are for the quarter they were set for
                company["borrow_wanted"] = dials["borrow"]
            if dials["buy_assets"] and dials["period"] == period:
                unit = _unit_cost(conn, company["id"], period)
                company["extra_capex"] = unit * dials["buy_assets"]
                company["assets_ordered"] = dials["buy_assets"]
        if p["no_dividend_until"] and period <= p["no_dividend_until"]:
            company["payout_bps"] = 0                             # a rescue stopped the dividend
        company["opex_bps"] = apply_bps(opex, ratio)
        company["pay_ratio_bps"] = ratio
        last = lasts.get(company["id"])
        quarter_sales = (last["revenue"] if last and last["period"] >= 1 else (last or {}).get("base_revenue", 0)) or 0
        original = apply_bps(max(quarter_sales, 1), MANAGER_PAY_BPS[p["management"]])
        company["extra_opex"] = max((boss["pay"] if boss else original) - original, -original // 2)
        # Pull: plans and marketing that last, the manager, the staff, what its secrets bring, its routes.
        pull = BPS + p["pull_adj_bps"] + MANAGER_PULL_BPS[quality]
        if p["morale_bps"] < MORALE_WALKOUT_BPS:
            pull = apply_bps(pull, 7000)
            company["walkout"] = True
        elif p["morale_bps"] < MORALE_SLOW_BPS:
            pull = apply_bps(pull, BPS - (MORALE_SLOW_BPS - p["morale_bps"]))
            company["labour_bps"] += (MORALE_SLOW_BPS - p["morale_bps"]) // 4
        for secret in p["secrets"]:
            if secret["code"] in ("customer_leaving", "contract_coming") and secret["from_period"] and secret["from_period"] <= period:
                pull = apply_bps(pull, BPS + secret["bps"])
            if secret["code"] == "hidden_debt" and not secret["done"] and secret["from_period"] and secret["from_period"] <= period:
                company["tax_bill"] = secret["amount"]          # the tax office's assessment falls due in this quarter's accounts
        if company["sector"] == "aviation" and p["route_base"]:
            pull = pull * _route_score(conn, company["id"], fares) // p["route_base"]
            routes = _rows(conn, "SELECT fare_bps FROM airline_routes WHERE company_id = %s AND closed_period IS NULL", (company["id"],))
            if routes:
                fare = sum(r["fare_bps"] for r in routes) // len(routes)
                if fare != BPS:
                    company["labour_bps"] = company["labour_bps"] * BPS // fare
        pull = max(pull, 500)
        # A company doctor whose rescue worked is paid in this quarter's accounts.
        company["doctor_fees"] = [(r["id"], r["doctor_id"], r["fee"]) for r in _rows(
            conn, "SELECT id, doctor_id, fee FROM company_plans WHERE company_id = %s AND kind = 'rescue' AND status = 'done'"
                  " AND NOT fee_paid AND fee > 0", (company["id"],))]
        # What its assets can serve caps what it can sell: customers turned away go to its rivals.
        can_serve = capacity(conn, company["id"], period)
        demand = quarter_sales * pull // max(p["last_pull_bps"], 1)
        if demand > 0 and can_serve < demand:
            pull = max(pull * can_serve // demand, 100)
            company["turned_away"] = demand - can_serve
        company["pull_bps"] = pull
        conn.execute("UPDATE private_profiles SET last_pull_bps = %s WHERE company_id = %s", (pull, company["id"]))


def _unit_cost(conn: Connection, company_id, period: int) -> int:
    """What one more of its assets costs today: what its assets cost, brought to today's prices."""
    rows = [a for a in assets(conn, company_id, all_=True) if a["capacity"] > 0]
    if not rows:
        return million_naira(500)
    return apply_bps(sum(a["cost"] for a in rows) // len(rows), _price_index(conn, period - 1))


def pay_spending(conn: Connection, world, companies: list[dict], period: int) -> None:
    """What an owned company spends on marketing and technology this quarter: bought from media houses
    and telecoms companies, so it is their sale. Its effect lasts."""
    label = clock.period_label(period)
    for company in companies:
        dials = dials_for(conn, company["id"], period) if company.get("pull_bps") is not None and controller(conn, company["id"]) else None
        if not dials or dials["period"] != period:
            continue
        last = _one(conn, "SELECT revenue, base_revenue, period FROM company_results WHERE company_id = %s AND period = %s",
                    (company["id"], period - 1))
        sales = max(last["revenue"] if last["period"] >= 1 else last["base_revenue"], 1)
        for what, sector, cap in (("marketing", "media", MARKETING_PULL_LIMIT_BPS), ("technology", "telecoms", TECH_SAVING_LIMIT_BPS)):
            wanted = dials[what]
            if wanted <= 0:
                continue
            paid = ledger.pay_split_up_to(conn, payer=company["account_id"],
                                          amounts=_economy().allocate(world, wanted, {sector: 1}, location=company["headquarters"],
                                                                      exclude=company["account_id"]),
                                          kind="business_purchase", memo=f"{company['name']}: {what}, {label}", period=period)
            gain = min(paid * BPS // sales // 2, cap)     # spending half a quarter's sales buys the most there is
            if what == "marketing":
                conn.execute("UPDATE private_profiles SET pull_adj_bps = least(pull_adj_bps + %s, %s) WHERE company_id = %s",
                             (gain, MARKETING_PULL_LIMIT_BPS * 2, company["id"]))
            else:
                conn.execute("UPDATE private_profiles SET labour_adj_bps = greatest(labour_adj_bps - %s, %s) WHERE company_id = %s",
                             (gain // 3, -TECH_SAVING_LIMIT_BPS, company["id"]))


def after_close(conn: Connection, period: int, results: list[tuple[dict, dict]], wage_index_bps: int, seed: str, now: datetime) -> None:
    """After every company has closed its quarter: assets wear, staff morale moves, secrets come true,
    rivals answer prices, failing companies go into administration, and the founders sell and found."""
    controlled = {r["company_id"]: r for r in _rows(conn, "SELECT * FROM owned_companies")}
    for company, result in results:
        p = profile(conn, company["id"])
        if p is None:
            continue
        _wear(conn, company, result, period, seed)
        for plan_id, _doctor, _fee in company.get("doctor_fees", []):
            conn.execute("UPDATE company_plans SET fee_paid = true WHERE id = %s", (plan_id,))
        # Morale follows pay against the going rate, and cuts in staff.
        ratio = company.get("pay_ratio_bps", BPS)
        dials = dials_for(conn, company["id"], period) if company["id"] in controlled else None
        target = BPS + 2 * (ratio - BPS)
        if dials and dials["staff_bps"] < 9000:
            target -= 9000 - dials["staff_bps"]
        target = max(min(target, 11_000), 3000)
        morale = p["morale_bps"] + (target - p["morale_bps"]) // 2
        pay = p["pay_index_bps"]
        if company["id"] not in controlled or controlled[company["id"]]["empire_id"] in _computer_empires(conn):
            pay = wage_index_bps                          # founders and computer-run owners keep pay at the going rate
        elif dials and dials["period"] == period and dials["pay_rise_bps"]:
            pay = apply_bps(pay, BPS + dials["pay_rise_bps"])
        conn.execute("UPDATE private_profiles SET morale_bps = %s, pay_index_bps = %s,"
                     " pull_adj_bps = pull_adj_bps - (pull_adj_bps * %s / 10000) WHERE company_id = %s",
                     (morale, pay, MARKETING_FADE_BPS if p["pull_adj_bps"] > 0 else 0, company["id"]))
        if company.get("walkout"):
            _news(conn, period + 1, 2, "walkout", f"walkout:{company['ticker']}:{period}",
                  {"company": company["name"], "city": company["headquarters"]})
        _secrets_come_true(conn, company, p, period, now)
    _rivals_answer_prices(conn, period)
    from simulation import firm_owned               # administration and plans are judged with the owners in view
    firm_owned.after_companies(conn, period, seed, now)
    open_sales(conn, period, seed, now)
    if period % STARTUP_EVERY == 2:
        found_startup(conn, period + 1, seed, now)


def _computer_empires(conn: Connection) -> set:
    return {r["id"] for r in _rows(conn, "SELECT id FROM empires WHERE kind <> 'player'")}


def _wear(conn: Connection, company: dict, result: dict, period: int, seed: str) -> None:
    """Assets age. Kept up, they hold their condition; left unkept, they wear, break down and must be
    repaired or replaced. A plane based where its airline has no hangar wears twice as fast."""
    depreciation = max(result["depreciation"], 1)
    bought = company.get("assets_paid", 0)
    upkeep_spent = max(result["capital_spending"] - bought, 0)
    kept = upkeep_spent * BPS // depreciation                # 10000 = its assets were kept up exactly; more restores them a little
    hangar_cities = {a["base"] for a in assets(conn, company["id"]) if a["kind"] == "hangar" and a["status"] == "working"}
    for asset in assets(conn, company["id"]):
        wear = BPS // asset["life_quarters"]
        if asset["kind"] == "plane" and asset["base"] not in hangar_cities:
            wear *= 2
        if asset["age_quarters"] >= asset["life_quarters"]:
            wear *= 3                                       # past its life: no upkeep holds it
            lost = wear
        else:
            lost = wear * WEAR_UNKEPT_BPS * (BPS - min(kept, BPS)) // BPS - wear * max(kept - BPS, 0) // BPS
        condition = max(min(asset["condition_bps"] - lost, BPS), 0)
        status = asset["status"]
        if status == "working" and condition < GROUNDED_BELOW_BPS:
            status = "grounded"
        conn.execute("UPDATE company_assets SET condition_bps = %s, age_quarters = age_quarters + 1, status = %s WHERE id = %s",
                     (condition, status, asset["id"]))
    ordered = company.get("assets_ordered", 0)
    if ordered:
        unit = company["extra_capex"] // ordered
        got = min(ordered, bought // max(unit, 1))
        template = next((a for a in assets(conn, company["id"]) if a["capacity"] > 0), None)
        kind, _plural, life = ASSETS.get(company["sector"], ("plant", "plants", 60))
        count = _one(conn, "SELECT count(*) AS n FROM company_assets WHERE company_id = %s AND kind = %s", (company["id"], kind))["n"]
        for n in range(got):
            conn.execute("INSERT INTO company_assets (company_id, kind, name, base, cost, capacity, condition_bps, stated_bps, life_quarters,"
                         " bought_period) VALUES (%s, %s, %s, %s, %s, %s, 10000, 10000, %s, %s)",
                         (company["id"], kind, f"{kind.capitalize()} {count + n + 1}", company["headquarters"], unit,
                          template["capacity"] if template else apply_bps(result["revenue"], SPARE_CAPACITY_BPS) // 6, life, period))


def _secrets_come_true(conn: Connection, company: dict, p: dict, period: int, now: datetime) -> None:
    """A secret that was set to bite does so now: a tax bill falls due, a customer is gone or a contract signed."""
    changed = False
    secrets = p["secrets"]
    for secret in secrets:
        if secret["done"] or not secret["from_period"] or secret["from_period"] > period:
            continue
        if secret["code"] == "hidden_debt":
            secret["done"] = company.get("tax_bill") == secret["amount"]     # booked as tax in the quarter just closed
            changed = changed or secret["done"]
        elif secret["code"] in ("customer_leaving", "contract_coming"):
            secret["done"] = True                          # it now shows in its sales, and goes on doing so
            changed = True
        if secret["done"]:
            owner = controller(conn, company["id"])
            if owner:
                conn.execute("INSERT INTO deal_finds (empire_id, company_id, code, how, at) VALUES (%s, %s, %s, 'surfaced', %s)"
                             " ON CONFLICT DO NOTHING", (owner["empire_id"], company["id"], secret["code"], now))
    if changed:
        conn.execute("UPDATE private_profiles SET secrets = %s WHERE company_id = %s", (Jsonb(secrets), company["id"]))


def _rivals_answer_prices(conn: Connection, period: int) -> None:
    """Rival companies answer an owned company's prices. A company run by the computer moves half way
    towards the cheapest owned rival in its industry that undercuts it, and otherwise back towards usual prices."""
    owned = {r["company_id"] for r in _rows(conn, "SELECT o.company_id FROM owned_companies o JOIN empires e ON e.id = o.empire_id"
                                                  " WHERE e.kind = 'player'")}
    by_sector: dict[str, list[dict]] = {}
    for c in _rows(conn, "SELECT c.id, c.sector, c.price_bps, r.revenue FROM companies c JOIN company_results r ON r.company_id = c.id"
                         " AND r.period = %s WHERE c.status = 'trading'", (period,)):
        by_sector.setdefault(c["sector"], []).append(c)
    for sector, members in by_sector.items():
        total = sum(max(c["revenue"], 0) for c in members) or 1
        # An undercutter counts for its share of the industry: a small one barely moves its rivals.
        cutters = [(c["price_bps"], max(c["revenue"], 0) * BPS // total) for c in members if c["id"] in owned and c["price_bps"] < BPS]
        cheapest, weight = min(cutters, default=(None, 0))
        weight = min(weight * 2, BPS) if cheapest is not None else 0
        for c in members:
            if c["id"] in owned:
                continue
            target = BPS
            if cheapest is not None and weight >= RIVAL_NOTICE_BPS and cheapest < c["price_bps"] - 300:
                target = c["price_bps"] + (cheapest - c["price_bps"]) * weight // BPS
            new = c["price_bps"] + (target - c["price_bps"]) // 2
            if new != c["price_bps"]:
                conn.execute("UPDATE companies SET price_bps = %s WHERE id = %s", (max(min(new, 20_000), 5000), c["id"]))


# ---------------------------------------------------------------------------
# The founders put companies up for sale
# ---------------------------------------------------------------------------

def value_of(conn: Connection, company_id) -> int:
    """What the whole company is worth on the latest valuation (never below nothing)."""
    row = _one(conn, "SELECT v.value_per_share, r.shares_in_issue, r.total_equity FROM companies c"
                     " JOIN LATERAL (SELECT * FROM company_results WHERE company_id = c.id ORDER BY period DESC LIMIT 1) r ON true"
                     " LEFT JOIN LATERAL (SELECT value_per_share FROM company_valuations WHERE company_id = c.id ORDER BY period DESC LIMIT 1) v ON true"
                     " WHERE c.id = %s AND c.status = 'trading'", (company_id,))
    if row is None:
        return 0                                       # a company wound up is worth nothing
    if row["value_per_share"] is not None:
        return max(row["value_per_share"] * row["shares_in_issue"], 0)
    return max(row["total_equity"], 0)


def open_sales(conn: Connection, period: int, seed: str, now: datetime) -> list[int]:
    """The founders (or the pension funds, once they have owned a company two years) put a few companies up
    for sale. The asking price is near what the company is worth; a gem is asked for well below it. Half are
    sold by sealed bids, half by auction."""
    founders = ledger.account_id(conn, ledger.INVESTORS_FOUNDERS)
    funds = ledger.account_id(conn, ledger.INVESTORS_INSTITUTIONS)
    opened = []
    candidates = _rows(conn, "SELECT c.id, c.ticker, c.name, c.share_asset FROM companies c JOIN private_profiles p ON p.company_id = c.id"
                             " WHERE NOT c.listed AND c.status = 'trading' AND NOT EXISTS (SELECT 1 FROM owned_companies o WHERE o.company_id = c.id)"
                             " AND NOT EXISTS (SELECT 1 FROM sale_processes s WHERE s.company_id = c.id AND s.status = 'open') ORDER BY c.ticker")
    first = period == 0
    for c in candidates:
        if len(opened) >= (SALES_A_QUARTER + 1 if first else SALES_A_QUARTER):
            break
        if roll(seed, c["ticker"], "sale", period) >= (3000 if first else SALE_CHANCE_BPS):
            continue
        seller = founders
        if ledger.balance(conn, founders, c["share_asset"]) <= 0:
            bought = _one(conn, "SELECT max(closes_period) AS p FROM sale_processes WHERE company_id = %s AND status = 'sold'", (c["id"],))
            if bought["p"] is not None and bought["p"] > period - 8:
                continue                                   # the pension funds hold what they buy for two years at least
            seller = funds
        shares = ledger.balance(conn, seller, c["share_asset"])
        if shares <= 0:
            continue
        opened.append(start_sale(conn, c["id"], seller, None, shares, period, seed, now))
    return opened


def start_sale(conn: Connection, company_id, seller_account, seller_empire_id, shares: int, period: int, seed: str, now: datetime,
               *, asking: int | None = None, reserve: int | None = None, mode: str | None = None) -> int:
    """Open a sale. It is decided as the next quarter closes. Secrets set to bite after a sale are timed from now."""
    company = _one(conn, "SELECT * FROM companies WHERE id = %s", (company_id,))
    in_issue = ledger.amount_in_existence(conn, company["share_asset"])
    worth = value_of(conn, company_id) * shares // max(in_issue, 1)
    p = profile(conn, company_id)
    cheap = next((s for s in (p["secrets"] if p else []) if s["code"] == "underpriced"), None)
    if asking is None:
        asking = max(apply_bps(worth, 9500 + roll(seed, company["ticker"], "asking", period) % 2000), million_naira(100))
        if cheap and seller_empire_id is None:
            asking = apply_bps(worth, BPS - cheap["bps"])
    if reserve is None:
        reserve = apply_bps(asking, 8500)
    mode = mode or ("sealed" if roll(seed, company["ticker"], "mode", period) % 2 == 0 else "auction")
    if p:
        secrets = p["secrets"]
        for s in secrets:
            if not s["done"] and s["code"] in ("customer_leaving", "contract_coming", "hidden_debt") and s["from_period"] is None:
                s["from_period"] = period + 2
        conn.execute("UPDATE private_profiles SET secrets = %s WHERE company_id = %s", (Jsonb(secrets), company_id))
    sale = _one(conn, "INSERT INTO sale_processes (company_id, seller_account, seller_empire_id, shares, mode, asking, reserve, opened_period,"
                      " closes_period, at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
                (company_id, seller_account, seller_empire_id, shares, mode, asking, max(min(reserve, asking), 1), period, period + 1, now))
    _news(conn, period + 1, 1, "company_for_sale", f"sale:{sale['id']}",
          {"company": company["name"], "sector": _sector_words(company["sector"]), "how": "by sealed bids" if mode == "sealed" else "at auction",
           "amount": money(asking)})
    return sale["id"]


# ---------------------------------------------------------------------------
# What the founders' papers say: the data room
# ---------------------------------------------------------------------------

def dressed_bps(conn: Connection, company_id) -> int:
    """How far the founders' papers overstate its sales (0 if they are honest)."""
    p = profile(conn, company_id)
    if p is None or controller(conn, company_id):
        return 0
    return next((s["bps"] for s in p["secrets"] if s["code"] == "dressed_revenue"), 0)


def papers(conn: Connection, company_id, quarters: int = 4) -> list[dict]:
    """The management accounts the seller shows, quarter by quarter. Sales may be dressed up; the
    profit is dressed up with them. The cash at the bank is not: it is what the bank says."""
    lift = dressed_bps(conn, company_id)
    out = []
    for r in reversed(_rows(conn, "SELECT * FROM company_results WHERE company_id = %s AND period >= 1 ORDER BY period DESC LIMIT %s",
                            (company_id, quarters))):
        extra = apply_bps(r["revenue"], lift)
        out.append({"period": r["period"], "label": clock.period_label(r["period"]), "revenue": r["revenue"] + extra,
                    "operating_profit": r["operating_profit"] + extra, "net_profit": r["net_profit"] + extra,
                    "depreciation": r["depreciation"], "interest_expense": r["interest_expense"], "cash": r["cash"],
                    "borrowings": r["borrowings"], "payables": r["payables"], "total_equity": r["total_equity"] + extra,
                    "fixed_assets": r["fixed_assets"], "staff": r["staff"]})
    return out


def bank_receipts(conn: Connection, company_id, quarters: int = 4) -> list[dict]:
    """What the company's bank statements say it received from customers, quarter by quarter: the truth."""
    return [{"period": r["period"], "label": clock.period_label(r["period"]),
             "households": r["sales_households"], "business": r["sales_business"], "government": r["sales_government"],
             "total": r["sales_households"] + r["sales_business"] + r["sales_government"]}
            for r in reversed(_rows(conn, "SELECT * FROM company_results WHERE company_id = %s AND period >= 1 ORDER BY period DESC LIMIT %s",
                                    (company_id, quarters)))]


def asset_register(conn: Connection, company_id, *, true: bool) -> list[dict]:
    """The assets, with their condition as the seller states it, or as it truly is."""
    return [{"id": a["id"], "kind": a["kind"], "name": a["name"], "base": a["base"], "age_quarters": a["age_quarters"],
             "life_quarters": a["life_quarters"], "status": a["status"],
             "condition_bps": a["condition_bps"] if true else (a["stated_bps"] or a["condition_bps"]),
             "cost": a["cost"], "route_id": a["route_id"]} for a in assets(conn, company_id)]


def registry(conn: Connection, company_id, seed: str) -> list[dict]:
    """What the companies registry and the courts hold on the company: charges over its assets, claims
    and judgments. Some are live, some long discharged. A hidden tax bill or a partner's claim shows here
    for whoever reads it closely."""
    company = _one(conn, "SELECT * FROM companies WHERE id = %s", (company_id,))
    p = profile(conn, company_id)
    lines = []
    for d in _rows(conn, "SELECT * FROM company_debts WHERE company_id = %s AND principal_outstanding > 0 ORDER BY id", (company_id,)):
        lines.append({"entry": f"Charge over its assets in favour of the lender of its {d['name']}", "amount": d["principal_outstanding"],
                      "live": True, "kind": "charge"})
    for i in range(2):
        lines.append({"entry": "Charge over a former site, satisfied and discharged", "kind": "charge", "live": False,
                      "amount": apply_bps(million_naira(100), 1000 + roll(seed, company["ticker"], "old", i) % 9000)})
    for s in (p["secrets"] if p else []):
        if s["code"] == "hidden_debt" and not s["done"]:
            lines.append({"entry": "Notice of a tax assessment by the Federal Inland Revenue, under appeal", "amount": s["amount"],
                          "live": True, "kind": "claim"})
        if s["code"] == "ownership_claim" and not s["done"]:
            worth = value_of(conn, company_id)
            lines.append({"entry": "Suit by a former partner claiming a share of the company, set down for hearing",
                          "amount": apply_bps(worth, s["bps"]), "live": True, "kind": "claim"})
    lines.append({"entry": "Suit by a supplier over an unpaid invoice, settled out of court", "kind": "claim", "live": False,
                  "amount": apply_bps(million_naira(10), 1000 + roll(seed, company["ticker"], "settled") % 9000)})
    lines.sort(key=lambda line: roll(seed, company["ticker"], "order", line["entry"], line["amount"]))
    return lines
