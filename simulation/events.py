"""Events: the real causes of good and bad quarters (design document, sections 11 and 14).

Floods, strikes, power failures, scandals, harvests and price shocks. Each
event belongs to one quarter and happens on one of its 90 days. The events of
a quarter are decided when the quarter before closes, worked out from the
world's secret so nobody outside the server can know them in advance. They
stay out of sight until their day arrives, then appear in the news; their
effect on companies' accounts shows when the quarter closes.

Nothing here moves money. An event changes how strongly customers are pulled
to a company, what its costs are, and how much of its buildings and machines
is destroyed. The companies' own quarters then play out through the ledger.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from simulation import ledger
from simulation import world_data as data
from simulation.money import BPS


@dataclass(frozen=True)
class Kind:
    """One kind of event: how likely it is each quarter, where, and how hard it hits."""
    name: str
    scope: str                         # 'location', 'sector', 'company' or 'national'
    chance_bps: int                    # likelihood each quarter, for each place, sector or company it can strike
    sales: tuple[int, int] = (0, 0)    # change in the pull of the companies it touches, lowest to highest
    cost: tuple[int, int] = (0, 0)     # extra cost as a share of sales
    damage: tuple[int, int] = (0, 0)   # share of buildings and machines destroyed
    mood: tuple[int, int] = (0, 0)     # change in local households' readiness to spend
    commodity: str | None = None
    price: tuple[int, int] = (0, 0)    # change in that commodity's price
    severe: bool = False
    likelier_in: dict[str, int] | None = None     # locations where it is more (or less) likely: a multiplier in percent
    only_sectors: tuple[str, ...] | None = None   # the kinds of company it can touch
    spares_financial: bool = False


KINDS: tuple[Kind, ...] = (
    # --- Where a company is based ---
    Kind("flood", "location", 200, sales=(-1000, -300), damage=(30, 150), mood=(-500, -150), severe=True,
         likelier_in={data.PORT_HARCOURT: 300, data.LAGOS: 250, data.ABA: 100, data.ABUJA: 50, data.KANO: 50},
         spares_financial=True),
    Kind("power_failure", "location", 350, sales=(-400, -100), cost=(100, 400),
         likelier_in={data.ABA: 250, data.KANO: 250, data.LAGOS: 120, data.PORT_HARCOURT: 120, data.ABUJA: 60},
         only_sectors=("manufacturing", "cement", "telecoms", "consumer", "agriculture", "media", "real_estate")),
    Kind("security_incident", "location", 150, sales=(-500, -200), mood=(-400, -150), severe=True,
         likelier_in={data.PORT_HARCOURT: 250, data.KANO: 200, data.ABA: 100, data.LAGOS: 60, data.ABUJA: 60},
         spares_financial=True),
    Kind("port_disruption", "location", 300, sales=(-700, -200), cost=(100, 300),
         likelier_in={data.LAGOS: 150, data.PORT_HARCOURT: 150, data.ABA: 0, data.ABUJA: 0, data.KANO: 0},
         only_sectors=("transport", "consumer", "manufacturing", "cement", "oil_gas")),
    Kind("pipeline_incident", "location", 500, sales=(-1200, -500), commodity="energy", price=(600, 1800),
         likelier_in={data.PORT_HARCOURT: 100, data.LAGOS: 0, data.ABA: 0, data.ABUJA: 0, data.KANO: 0},
         only_sectors=("oil_gas",)),
    Kind("drought", "location", 500, sales=(-1500, -600), mood=(-300, -100), commodity="agriculture", price=(1000, 2500),
         likelier_in={data.KANO: 100, data.ABUJA: 40, data.LAGOS: 0, data.ABA: 0, data.PORT_HARCOURT: 0},
         only_sectors=("agriculture",)),
    Kind("local_boom", "location", 200, sales=(200, 600), mood=(200, 500)),
    # --- A whole kind of business ---
    Kind("sector_strike", "sector", 150, sales=(-1200, -400), spares_financial=True),
    Kind("sector_demand_surge", "sector", 150, sales=(300, 900)),
    Kind("good_harvest", "sector", 500, sales=(300, 800), commodity="agriculture", price=(-2000, -800),
         only_sectors=("agriculture",)),
    Kind("network_outage", "sector", 300, sales=(-600, -200), only_sectors=("telecoms",)),
    Kind("new_competition", "sector", 120, sales=(-500, -200), spares_financial=True),
    # --- One company ---
    Kind("company_strike", "company", 80, sales=(-1500, -500), spares_financial=True),
    Kind("scandal", "company", 60, sales=(-2000, -800)),
    Kind("contract_win", "company", 100, sales=(500, 1500)),
    Kind("factory_fire", "company", 50, sales=(-1000, -400), damage=(100, 400), spares_financial=True),
    Kind("product_recall", "company", 50, sales=(-900, -300), cost=(200, 500),
         only_sectors=("consumer", "manufacturing", "agriculture")),
    Kind("new_product", "company", 80, sales=(400, 1200), spares_financial=True),
    # --- The whole country ---
    Kind("energy_price_jump", "national", 400, commodity="energy", price=(1000, 2500)),
    Kind("energy_price_fall", "national", 400, commodity="energy", price=(-2000, -800)),
    Kind("metals_price_jump", "national", 300, commodity="metals", price=(800, 2000)),
    Kind("metals_price_fall", "national", 300, commodity="metals", price=(-1800, -700)),
    Kind("materials_shortage", "national", 300, commodity="materials", price=(800, 2000)),
)
BY_NAME = {kind.name: kind for kind in KINDS}
FINANCIAL = ("banking", "insurance")


def _unit(seed: str, *key) -> float:
    """A number from 0 up to (not including) 1, fixed by the world's secret and the key."""
    digest = hashlib.sha256(f"{seed}:event:{':'.join(str(k) for k in key)}".encode()).digest()
    return int.from_bytes(digest[:8], "big") / 2**64


def _between(seed: str, low: int, high: int, *key) -> int:
    return low + round(_unit(seed, *key) * (high - low))


def _rows(conn: Connection, sql: str, params=()) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def generate(conn: Connection, period: int, seed: str) -> list[dict]:
    """Decide the events of a coming quarter and record them. Returns them."""
    if len(seed) < 32:
        raise ValueError("Events cannot be decided without the world's secret.")
    locations = [r["name"] for r in _rows(conn, "SELECT name FROM locations ORDER BY sort_order")]
    sectors = _rows(conn, "SELECT code, name FROM sectors ORDER BY sort_order")
    companies = _rows(conn, "SELECT id, ticker, name, sector, headquarters FROM companies ORDER BY ticker")
    made: list[dict] = []

    def happen(kind: Kind, target: str, **where) -> None:
        def pick(span: tuple[int, int], what: str) -> int:
            return _between(seed, span[0], span[1], period, kind.name, target, what) if span != (0, 0) else 0
        made.append({
            "period": period, "day": _between(seed, 1, 90, period, kind.name, target, "day"), "kind": kind.name,
            "location": where.get("location"), "sector": where.get("sector"), "company_id": where.get("company_id"),
            "sales_bps": pick(kind.sales, "sales"), "cost_bps": pick(kind.cost, "cost"),
            "damage_bps": pick(kind.damage, "damage"), "mood_bps": pick(kind.mood, "mood"),
            "commodity": kind.commodity, "price_bps": pick(kind.price, "price"), "severe": kind.severe,
            "facts": where.get("facts", {}),
        })

    for kind in KINDS:
        if kind.scope == "location":
            for location in locations:
                chance = kind.chance_bps * (kind.likelier_in or {}).get(location, 100) // 100
                if _unit(seed, period, kind.name, location, "happens") * BPS < chance:
                    happen(kind, location, location=location, facts={"location": location})
        elif kind.scope == "sector":
            for sector in sectors:
                if kind.only_sectors and sector["code"] not in kind.only_sectors:
                    continue
                if kind.spares_financial and sector["code"] in FINANCIAL:
                    continue
                if _unit(seed, period, kind.name, sector["code"], "happens") * BPS < kind.chance_bps:
                    happen(kind, sector["code"], sector=sector["code"], facts={"sector": sector["name"]})
        elif kind.scope == "company":
            for company in companies:
                if kind.only_sectors and company["sector"] not in kind.only_sectors:
                    continue
                if kind.spares_financial and company["sector"] in FINANCIAL:
                    continue
                if _unit(seed, period, kind.name, company["ticker"], "happens") * BPS < kind.chance_bps:
                    happen(kind, company["ticker"], company_id=company["id"], location=company["headquarters"],
                           facts={"company": company["name"], "ticker": company["ticker"], "location": company["headquarters"]})
        elif _unit(seed, period, kind.name, "nation", "happens") * BPS < kind.chance_bps:
            happen(kind, "nation")

    for event in made:
        columns = list(event)
        values = [Jsonb(v) if c == "facts" else v for c, v in event.items()]
        event["id"] = ledger._first(conn.execute(
            f"INSERT INTO events ({', '.join(columns)}) VALUES ({', '.join(['%s'] * len(columns))}) RETURNING id",
            values,
        ).fetchone())
    return made


def load(conn: Connection, period: int) -> list[dict]:
    return _rows(conn, "SELECT * FROM events WHERE period = %s ORDER BY day, id", (period,))


def touches(event: dict, company: dict) -> bool:
    """Whether an event reaches a company."""
    kind = BY_NAME[event["kind"]]
    if kind.scope == "national":
        return False
    if kind.only_sectors and company["sector"] not in kind.only_sectors:
        return False
    if kind.spares_financial and company["sector"] in FINANCIAL:
        return False
    if kind.scope == "company":
        return event["company_id"] == company["id"]
    if kind.scope == "sector":
        return event["sector"] == company["sector"]
    return event["location"] == company["headquarters"]


def company_effects(events: list[dict], company: dict) -> dict:
    """Everything this quarter's events do to one company."""
    sales, cost, damage, causes = BPS, 0, 0, []
    for event in events:
        if not touches(event, company):
            continue
        sales = sales * (BPS + event["sales_bps"]) // BPS
        cost += event["cost_bps"]
        damage += event["damage_bps"]
        causes.append(event)
    return {"sales_bps": max(sales, 1000), "cost_bps": cost, "damage_bps": min(damage, 5000), "events": causes}


def location_moods(events: list[dict]) -> tuple[dict[str, int], set[str]]:
    """How this quarter's events change each location's readiness to spend, and where something severe happened."""
    moods: dict[str, int] = {}
    severe: set[str] = set()
    for event in events:
        kind = BY_NAME[event["kind"]]
        if kind.scope == "location" and event["location"]:
            moods[event["location"]] = moods.get(event["location"], 0) + event["mood_bps"]
            if event["severe"]:
                severe.add(event["location"])
    return moods, severe


def commodity_moves(events: list[dict]) -> dict[str, int]:
    moves: dict[str, int] = {}
    for event in events:
        if event["commodity"]:
            moves[event["commodity"]] = moves.get(event["commodity"], 0) + event["price_bps"]
    return {name: max(min(move, 6000), -5000) for name, move in moves.items()}


# How an event reads as a cause in a company's filing.
_CAUSE = {
    "flood": "A flood in {location} cut its sales by about {size}",
    "power_failure": "Power failures in {location} cost it sales of about {size}",
    "security_incident": "A security incident in {location} cut its sales by about {size}",
    "port_disruption": "Disruption at the port in {location} cut its sales by about {size}",
    "pipeline_incident": "A pipeline incident near {location} cut its sales by about {size}",
    "drought": "Drought around {location} cut its sales by about {size}",
    "local_boom": "Business was brisk in {location}: its sales rose about {size}",
    "sector_strike": "A strike across its industry cut its sales by about {size}",
    "sector_demand_surge": "Demand for its whole industry jumped: its sales rose about {size}",
    "good_harvest": "A good harvest lifted its sales by about {size}",
    "network_outage": "A network outage cut its sales by about {size}",
    "new_competition": "New competitors took about {size} of its industry's sales",
    "company_strike": "A strike by its own staff cut its sales by about {size}",
    "scandal": "A scandal drove customers away: its sales fell about {size}",
    "contract_win": "It won a large contract: its sales rose about {size}",
    "factory_fire": "A fire at one of its sites cut its sales by about {size}",
    "product_recall": "It recalled a product: its sales fell about {size}",
    "new_product": "A new product sold well: its sales rose about {size}",
}


def causes_in_words(effects: dict) -> list[str]:
    out = []
    for event in effects["events"]:
        template = _CAUSE.get(event["kind"])
        if template and event["sales_bps"]:
            size = f"{abs(event['sales_bps']) / 100:.0f}%"
            out.append(template.format(location=event["location"], size=size))
    return out
