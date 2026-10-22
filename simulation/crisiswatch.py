"""The Crisis Watch (the crises stage; design document, section 14).

A public page of warning signs, read at each quarter's close: what the game watches for a crisis growing out of real
conditions. Each sign is green, amber or red, with the figure and why. It changes nothing by itself: it is what a
careful player, and the Central Bank, would look at.

  * Company debt: what companies owe against a year of their sales.
  * Household debt: what households owe against a year of their income.
  * Bank cash: the lowest cash any bank holds against what its savers have with it.
  * Bad loans: loans written off over the quarter, as a yearly share of what the banks have lent.
  * Lending in one place: the biggest bank's share of all bank lending.
  * Jobs: how many more or fewer than a year before.
  * Prices: inflation over the year.
  * House prices against incomes: how far home prices have outrun wages over two years.
  * Shortages: the biggest rise in a commodity's price over the year.
  * Government debt: what the Government owes against a year of what it collects.
  * Confidence: trust in the banks taken together.
"""

from __future__ import annotations

from datetime import datetime

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from simulation import clock
from simulation.money import BPS

# Each sign: (amber from, red from, higher is worse?)
LEVELS = {
    "company_debt": (8_000, 12_000, True),
    "household_debt": (12_000, 18_000, True),
    "bank_cash": (700, 400, False),
    "bad_loans": (300, 600, True),
    "concentration": (3_500, 5_000, True),
    "jobs": (-200, -500, False),
    "inflation": (900, 1_500, True),
    "house_prices": (2_000, 4_500, True),
    "shortages": (2_500, 5_000, True),
    "government_debt": (25_000, 40_000, True),
    "confidence": (55, 45, False),
}
NAMES = {
    "company_debt": "Company debt", "household_debt": "Household debt", "bank_cash": "Bank cash", "bad_loans": "Bad loans",
    "concentration": "Lending in one place", "jobs": "Jobs", "inflation": "Prices", "house_prices": "House prices against incomes",
    "shortages": "Shortages", "government_debt": "Government debt", "confidence": "Confidence in the banks",
}


def _rows(conn: Connection, sql: str, params=()) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def _one(conn: Connection, sql: str, params=()) -> dict | None:
    rows = _rows(conn, sql, params)
    return rows[0] if rows else None


def _pct(bps: int) -> str:
    return f"{bps / 100:.1f}%".replace(".0%", "%")


def level(name: str, value: int | None) -> str:
    if value is None:
        return "green"
    amber, red, worse_high = LEVELS[name]
    if worse_high:
        return "red" if value >= red else "amber" if value >= amber else "green"
    return "red" if value <= red else "amber" if value <= amber else "green"


def readings(conn: Connection, period: int) -> dict:
    """Every warning sign at a quarter's close: {name: {value, level, words}}."""
    out: dict = {}
    sales = _one(conn, "SELECT coalesce(sum(revenue), 0)::bigint AS s FROM company_results r JOIN companies c ON c.id = r.company_id"
                       " WHERE r.period = %s AND c.sector <> 'banking'", (period,))["s"]
    owed = _one(conn, "SELECT coalesce(sum(borrowings), 0)::bigint AS s FROM company_results r JOIN companies c ON c.id = r.company_id"
                      " WHERE r.period = %s AND c.sector <> 'banking'", (period,))["s"]
    v = owed * BPS // (4 * sales) if sales > 0 else None
    out["company_debt"] = (v, f"Companies owe {_pct(v)} of a year's sales." if v is not None else "No sales yet.")
    hh = _one(conn, "SELECT coalesce(sum(debt), 0)::bigint AS d, coalesce(sum(income), 0)::bigint AS i FROM household_results WHERE period = %s", (period,))
    v = hh["d"] * BPS // (4 * hh["i"]) if hh and hh["i"] > 0 else None
    out["household_debt"] = (v, f"Households owe {_pct(v)} of a year's income." if v is not None else "No income yet.")
    lowest = None
    for b in _rows(conn, "SELECT r.cash, r.customer_funds, c.name FROM company_results r JOIN companies c ON c.id = r.company_id"
                         " WHERE r.period = %s AND c.sector = 'banking' AND r.customer_funds > 0", (period,)):
        ratio = b["cash"] * BPS // b["customer_funds"]
        if lowest is None or ratio < lowest[0]:
            lowest = (ratio, b["name"])
    out["bank_cash"] = (lowest[0] if lowest else None,
                        f"{lowest[1]} holds cash of {_pct(lowest[0])} of its savers' money, the least of any bank." if lowest else "No banks.")
    lent = _one(conn, "SELECT coalesce(sum(customer_loans + loans_to_companies), 0)::bigint AS l, coalesce(sum(loan_losses), 0)::bigint AS x,"
                      " coalesce(max(customer_loans + loans_to_companies), 0)::bigint AS top FROM company_results r JOIN companies c ON c.id = r.company_id"
                      " WHERE r.period = %s AND c.sector = 'banking'", (period,))
    v = max(lent["x"], 0) * 4 * BPS // lent["l"] if lent["l"] > 0 else None
    out["bad_loans"] = (v, f"Banks wrote off loans at {_pct(v)} a year." if v is not None else "No lending yet.")
    v = lent["top"] * BPS // lent["l"] if lent["l"] > 0 else None
    out["concentration"] = (v, f"The biggest bank holds {_pct(v)} of all bank lending." if v is not None else "No lending yet.")
    jobs_now = _one(conn, "SELECT coalesce(sum(jobs), 0)::bigint AS j FROM household_results WHERE period = %s", (period,))["j"]
    jobs_then = _one(conn, "SELECT coalesce(sum(jobs), 0)::bigint AS j FROM household_results WHERE period = %s", (period - 4,))["j"]
    v = (jobs_now - jobs_then) * BPS // jobs_then if jobs_then > 0 else None
    out["jobs"] = (v, (f"{_pct(abs(v))} {'more' if v >= 0 else 'fewer'} jobs than a year before." if v is not None else "Not a year of jobs yet."))
    e = _one(conn, "SELECT * FROM economy_results WHERE period = %s", (period,))
    v = e["inflation_bps"] if e else None
    out["inflation"] = (v, f"Prices rose {_pct(v)} over the year." if v is not None else "Not measured yet.")
    out["house_prices"] = _house_prices(conn, period)
    out["shortages"] = _shortages(conn, period)
    out["government_debt"] = _government(conn, period)
    from simulation import crisis
    nat = crisis.national(conn)
    out["confidence"] = (nat, f"Trust in the banks taken together stands at {nat} of 100.")
    return {name: {"name": NAMES[name], "value": value, "level": level(name, value), "words": words} for name, (value, words) in out.items()}


def _house_prices(conn: Connection, period: int) -> tuple:
    price = {r["period"]: r["p"] for r in _rows(conn, "SELECT r.period, avg(r.price_bps)::bigint AS p FROM district_results r JOIN districts d"
                                                      " ON d.id = r.district_id WHERE d.kind = 'homes' AND r.period IN (%s, %s) GROUP BY r.period",
                                                (period, period - 8))} if _one(conn, "SELECT to_regclass('district_results') IS NOT NULL AS ok")["ok"] else {}
    wage = {r["period"]: r["wage_index_bps"] for r in _rows(conn, "SELECT period, wage_index_bps FROM economy_results WHERE period IN (%s, %s)",
                                                           (period, period - 8))}
    if period not in price or period - 8 not in price or period not in wage or period - 8 not in wage or not price[period - 8]:
        return None, "Not two years of house prices yet."
    homes = (price[period] - price[period - 8]) * BPS // price[period - 8]
    wages = (wage[period] - wage[period - 8]) * BPS // wage[period - 8]
    gap = homes - wages
    return gap, f"Over two years home prices moved {_pct(homes)} and wages {_pct(wages)}: a gap of {_pct(gap)}."


def _shortages(conn: Connection, period: int) -> tuple:
    now = _one(conn, "SELECT * FROM economy_results WHERE period = %s", (period,))
    then = _one(conn, "SELECT * FROM economy_results WHERE period = %s", (period - 4,))
    if not now or not then:
        return None, "Not a year of commodity prices yet."
    rises = {}
    for name, col in (("energy", "energy_bps"), ("metals", "metals_bps"), ("farm produce", "agriculture_bps"), ("building materials", "materials_bps")):
        if then[col]:
            rises[name] = (now[col] - then[col]) * BPS // then[col]
    if not rises:
        return None, "No commodity prices yet."
    top = max(rises, key=lambda k: rises[k])
    return rises[top], f"The biggest rise over the year was {top}, {_pct(rises[top])}."


def _government(conn: Connection, period: int) -> tuple:
    from simulation import bonds, economy, ledger
    owed = bonds.government_debt(conn) or 0
    treasury = ledger.account_id(conn, ledger.TREASURY)
    quarters = list(range(max(period - 3, 1), period + 1))
    collected = sum(ledger.received_in_period(conn, treasury, p, kinds=economy.GOVERNMENT_INCOME) for p in quarters)
    if collected <= 0:
        return None, "Not a year of Government income yet."
    v = owed * BPS * len(quarters) // (4 * collected)       # against a full year, however many quarters there have been
    return v, f"The Government owes {_pct(v)} of a year of what it collects."


def measure(conn: Connection, period: int, now: datetime) -> dict:
    """Take the Crisis Watch's reading at a close (once), and print the news when a sign turns red."""
    if not _one(conn, "SELECT to_regclass('crisis_watch') IS NOT NULL AS ok")["ok"]:
        return {}
    done = _one(conn, "SELECT readings FROM crisis_watch WHERE period = %s", (period,))
    if done:
        return done["readings"]
    found = readings(conn, period)
    before = _one(conn, "SELECT readings FROM crisis_watch WHERE period = %s", (period - 1,))
    conn.execute("INSERT INTO crisis_watch (period, readings, at) VALUES (%s, %s, %s)", (period, Jsonb(found), now))
    was = (before or {}).get("readings") or {}
    for name, r in found.items():
        if r["level"] == "red" and (was.get(name) or {}).get("level") != "red":
            from simulation import news, ripple
            news.publish(conn, period=period + 1, day=2, kind="crisis_watch_red", story=f"watch-red:{name}:{period}",
                         facts={"sign": r["name"].lower(), "words": r["words"]})
            ripple.link(conn, f"crisiswatch:{name}:{period}", f"prices:{period}" if name == "inflation" else f"watch:{period}",
                        f"The Crisis Watch turned red on {r['name'].lower()}: {r['words']}", period, now)
    return found


def view(conn: Connection, now: datetime) -> dict:
    """The latest reading, and the run of each sign's level over the last two years. All public."""
    if not _one(conn, "SELECT to_regclass('crisis_watch') IS NOT NULL AS ok")["ok"]:
        return {"period": None, "signs": []}
    rows = _rows(conn, "SELECT * FROM crisis_watch ORDER BY period DESC LIMIT 8")
    if not rows:
        return {"period": None, "label": None, "signs": []}
    latest = rows[0]
    signs = []
    for name in LEVELS:
        r = latest["readings"].get(name)
        if r is None:
            continue
        signs.append({**r, "sign": name, "history": [{"period": x["period"], "level": (x["readings"].get(name) or {}).get("level", "green")}
                                                     for x in reversed(rows)]})
    return {"period": latest["period"], "label": clock.period_label(latest["period"]), "signs": signs}
