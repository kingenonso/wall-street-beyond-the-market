"""Private equity stage, part 2A: running a company an empire bought, trouble, and getting out.

  dials          each quarter: prices, staff numbers, pay rises, marketing, technology, upkeep,
                 dividends, borrowing and new assets
  assets         bought, kept up, repaired, sold; worn out if neglected
  managers       a better managing director costs more and runs it better
  the airline    routes between the five cities, a fare on each set against rivals, planes on routes
  100-day plan   improvements after a purchase: each has a cost, a time, and a chance of failing
  company doctor an Accountant's plan to save a failing company, paid only if it works
  administration a company that cannot pay its way is wound up: its assets are sold and those it
                 owes are paid in the order the law sets; its owners may get nothing
  getting out    sell to another empire (a sale like any other), to a computer-run buyer (the pension
                 funds), or list it on the exchange
  the gain       shared among the owners by their shares; the empire pays deal fees to those who did
                 the work; league tables, and the Deal of the Year

Every naira moves through the ledger.
"""

from __future__ import annotations

from datetime import datetime

from psycopg import Connection

from simulation import careers, clock, empires, firm, leagues, ledger, private
from simulation.empires import EmpireError, _log, _money, _one, _open, _rows
from simulation.money import BPS, apply_bps

PLAN_WINDOW = 2                    # quarters after buying in which the 100-day plan may be set out
PLANS_MOST = 3
PLANS = {   # code -> (title, cost as hundredths of a percent of a quarter's sales, quarters, chance, effect words)
    "suppliers": ("Renegotiate with suppliers", 200, 1, 7500, "Costs of making what it sells fall three points."),
    "head_office": ("Cut the head office", 100, 1, 8000, "Running costs fall 8%, but staff morale suffers."),
    "rebrand": ("Refresh the brand", 400, 2, 6500, "It wins customers: its pull rises 8%."),
    "systems": ("New systems", 500, 2, 6000, "Costs of making what it sells fall five points."),
    "fix_assets": ("Fix the plant", 300, 1, 9000, "Every asset is brought back towards good order, and the grounded ones work again."),
    "pricing": ("Pricing review", 100, 1, 7000, "A little more pull, and costs a point lower."),
}
RESCUE = {   # code -> (title, words)
    "cut_costs": ("Cut costs hard", "Running costs fall 10%; staff morale falls."),
    "sell_grounded": ("Sell assets that are not working", "Grounded assets are sold for cash."),
    "skip_dividends": ("Stop dividends", "No dividend for two quarters."),
    "extend_loans": ("Ask the bank for time", "Loans due soon are put back a year, if the bank sees the company still earns."),
}
RESCUE_FEE_MOST_BPS = 500          # a doctor's fee is at most 5% of a quarter's sales
RESCUE_QUARTERS = 2
RESCUE_EVERY = 4                   # one rescue a year at most, for any company
FOUNDERS_ACCEPT_FEE_BPS = 300      # the founders accept a rescue whose fee is no more than 3% of a quarter's sales
TROUBLE_QUARTERS = 2               # behind on bills or loans for two closes running, and owing more than it owns: administration
DEAL_FEE_BRING_BPS = 100           # of a gain: to the banker who brought the deal
DEAL_FEE_CHECK_BPS = 25            # of a gain: to each player who did a check
BUYER_DISCOUNT_BPS = 9500          # the computer-run buyer pays 95% of the valuation
LISTING_DISCOUNT_BPS = 9000        # new shares at a listing are priced a tenth below the valuation
LISTING_NEW_BPS = 2500             # a listing sells new shares of a quarter of those in issue
COMPUTER_HOLD = 8                  # a computer-run empire sells a company it has owned this many quarters
ASSET_SALE_BPS = (6000, 3000)      # a used asset fetches 60% of its book value, and up to 30% more for good condition
ADMIN_ASSET_BPS = 6000             # in administration, assets fetch 60% of book value
SALE_FLOOR_BPS = 8000              # a head may not sell the empire's company for less than 80% of its valuation


def _owned(conn: Connection, player_id, company_id, *, runner: bool = True) -> tuple[dict, dict, dict]:
    """The company, controlled by the player's empire, and the player's seat. Run by the head, the deputy
    or the Asset Manager's desk."""
    seat, empire = firm._active(conn, player_id)
    if not firm.player_run(empire):
        raise EmpireError("A company owned by an empire the computer runs is run by the computer.")
    company = _one(conn, "SELECT c.*, o.empire_id, o.bought_period, o.cost FROM companies c JOIN owned_companies o ON o.company_id = c.id"
                         " WHERE c.id = %s FOR UPDATE OF c", (company_id,))
    if company is None or company["empire_id"] != empire["id"]:
        raise EmpireError("Your empire does not control that company.")
    if company["status"] != "trading":
        raise EmpireError("That company is no longer trading.")
    if runner and not (empire["head_player_id"] == player_id or firm.deputy_of(conn, empire["id"]) == player_id
                       or seat["build"] == "asset_manager"):
        raise EmpireError("A company the empire owns is run by the head, the deputy or the Asset Manager's desk.")
    return seat, empire, company


def _whole(value, least: int, most: int) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and least <= value <= most


def _quarter_sales(conn: Connection, company_id) -> int:
    r = _one(conn, "SELECT revenue, base_revenue, period FROM company_results WHERE company_id = %s ORDER BY period DESC LIMIT 1", (company_id,))
    return max(r["revenue"] if r and r["period"] >= 1 else (r or {}).get("base_revenue", 1), 1)


# ---------------------------------------------------------------------------
# The dials
# ---------------------------------------------------------------------------

def set_dials(conn: Connection, player_id, company_id, dials: dict, now: datetime) -> dict:
    """Set the company's dials for the running quarter. They stay as set until changed."""
    with conn.transaction():
        state = _open(conn, now)
        seat, empire, company = _owned(conn, player_id, company_id)
        sales = _quarter_sales(conn, company_id)
        ranges = {"price_bps": (7000, 14000), "staff_bps": (7000, 13000), "pay_rise_bps": (0, 3000), "maintenance_bps": (0, 20000),
                  "payout_bps": (0, 10000), "buy_assets": (0, 10)}
        for key, (low, high) in ranges.items():
            if not _whole(dials.get(key), low, high):
                raise EmpireError(f"{key.replace('_', ' ')}: a whole number from {low} to {high}.")
        for key in ("marketing", "technology", "borrow"):
            if not _whole(dials.get(key), 0, sales * 4):
                raise EmpireError(f"{key}: from nothing up to a year's sales.")
        conn.execute("INSERT INTO company_dials (company_id, period, price_bps, staff_bps, pay_rise_bps, marketing, technology, maintenance_bps,"
                     " payout_bps, borrow, buy_assets, set_by, at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
                     " ON CONFLICT (company_id, period) DO UPDATE SET price_bps = excluded.price_bps, staff_bps = excluded.staff_bps,"
                     " pay_rise_bps = excluded.pay_rise_bps, marketing = excluded.marketing, technology = excluded.technology,"
                     " maintenance_bps = excluded.maintenance_bps, payout_bps = excluded.payout_bps, borrow = excluded.borrow,"
                     " buy_assets = excluded.buy_assets, set_by = excluded.set_by, at = excluded.at",
                     (company_id, state["period"], dials["price_bps"], dials["staff_bps"], dials["pay_rise_bps"], dials["marketing"],
                      dials["technology"], dials["maintenance_bps"], dials["payout_bps"], dials["borrow"], dials["buy_assets"], player_id, now))
        conn.execute("UPDATE companies SET price_bps = %s WHERE id = %s", (dials["price_bps"], company_id))
        _log(conn, empire["id"], f"{firm._name(conn, player_id)} set the dials of {company['name']} for {clock.period_label(state['period'])}.", now)
        return {"period": state["period"]}


# ---------------------------------------------------------------------------
# Assets, managers, routes
# ---------------------------------------------------------------------------

def book_values(conn: Connection, company_id) -> dict:
    """Each asset's share of the company's buildings and machines on its balance sheet, weighted by cost and condition."""
    fixed = _one(conn, "SELECT fixed_assets FROM company_results WHERE company_id = %s ORDER BY period DESC LIMIT 1", (company_id,))["fixed_assets"]
    pending = _one(conn, "SELECT coalesce(sum(book), 0)::bigint AS b FROM company_asset_sales s WHERE company_id = %s AND period >"
                         " (SELECT max(period) FROM company_results WHERE company_id = %s)", (company_id, company_id))["b"]
    rows = private.assets(conn, company_id)
    weights = {a["id"]: a["cost"] * (a["condition_bps"] + 1000) // BPS for a in rows}
    total = sum(weights.values()) or 1
    left = max(fixed - pending, 0)
    return {asset_id: left * w // total for asset_id, w in weights.items()}


def sell_asset(conn: Connection, player_id, asset_id: int, now: datetime) -> dict:
    """Sell one asset. A used-asset buyer (the founders' and insiders' money) pays for it at its book value,
    less a discount that is smaller the better its condition. The gain or loss shows in the quarter's accounts."""
    with conn.transaction():
        state = _open(conn, now)
        asset = _one(conn, "SELECT * FROM company_assets WHERE id = %s FOR UPDATE", (asset_id,))
        if asset is None or asset["status"] not in ("working", "grounded"):
            raise EmpireError("There is no such asset to sell.")
        seat, empire, company = _owned(conn, player_id, asset["company_id"])
        book = book_values(conn, company["id"]).get(asset_id, 0)
        proceeds = apply_bps(book, ASSET_SALE_BPS[0] + ASSET_SALE_BPS[1] * asset["condition_bps"] // BPS)
        buyer = ledger.account_id(conn, ledger.INVESTORS_FOUNDERS)
        if proceeds > ledger.balance(conn, buyer):
            raise EmpireError("No buyer has the cash for it this quarter.")
        if proceeds:
            ledger.transfer(conn, payer=buyer, receiver=company["account_id"], amount=proceeds, kind="asset_sale",
                            memo=f"{company['name']}: {asset['name']} sold", period=state["period"], reference=f"asset:{asset_id}")
        conn.execute("INSERT INTO company_asset_sales (company_id, asset_id, period, book, proceeds, at) VALUES (%s, %s, %s, %s, %s, %s)",
                     (company["id"], asset_id, state["period"], book, proceeds, now))
        conn.execute("UPDATE company_assets SET status = 'sold', route_id = NULL, ended_period = %s WHERE id = %s", (state["period"], asset_id))
        _log(conn, empire["id"], f"{company['name']} sold {asset['name']} for {_money(proceeds)} (its book value was {_money(book)}).", now)
        return {"proceeds": proceeds, "book": book}


def _supplier(conn: Connection, sector: str) -> dict:
    return _one(conn, "SELECT c.* FROM companies c JOIN LATERAL (SELECT base_revenue FROM company_results WHERE company_id = c.id"
                      " ORDER BY period DESC LIMIT 1) r ON true WHERE c.sector = %s AND c.status = 'trading' ORDER BY r.base_revenue DESC, c.ticker LIMIT 1",
                (sector,))


def repair(conn: Connection, player_id, asset_id: int, now: datetime) -> dict:
    """Repair a worn or grounded asset: the work is bought from a manufacturer, and the asset is back in fair order."""
    with conn.transaction():
        state = _open(conn, now)
        asset = _one(conn, "SELECT * FROM company_assets WHERE id = %s FOR UPDATE", (asset_id,))
        if asset is None or asset["status"] not in ("working", "grounded") or asset["condition_bps"] >= 6000:
            raise EmpireError("Only an asset in poor condition needs repair.")
        seat, empire, company = _owned(conn, player_id, asset["company_id"])
        cost = apply_bps(apply_bps(asset["cost"], private.REPAIR_COST_BPS), private._price_index(conn, state["period"] - 1))
        maker = _supplier(conn, "manufacturing")
        try:
            ledger.transfer(conn, payer=company["account_id"], receiver=maker["account_id"], amount=cost, kind="business_purchase",
                            memo=f"{company['name']}: repairs to {asset['name']}", period=state["period"], reference=f"asset:{asset_id}")
        except ledger.InsufficientFunds:
            raise EmpireError(f"The repair costs {_money(cost)}; the company has not the cash.") from None
        conn.execute("UPDATE company_assets SET condition_bps = 6000, status = 'working' WHERE id = %s", (asset_id,))
        _log(conn, empire["id"], f"{company['name']} repaired {asset['name']} for {_money(cost)}.", now)
        return {"cost": cost}


def candidates(conn: Connection, company_id, period: int) -> list[dict]:
    """Three managing directors who would take the job this quarter: the better, the dearer."""
    seed = private._seed(conn)
    ticker = _one(conn, "SELECT ticker FROM companies WHERE id = %s", (company_id,))["ticker"]
    sales = _quarter_sales(conn, company_id)
    out = []
    for n in range(3):
        quality = 2 + private.roll(seed, ticker, "candidate", period, n) % 4
        pay = apply_bps(apply_bps(sales, private.MANAGER_PAY_BPS[quality]), 9000 + private.roll(seed, ticker, "cpay", period, n) % 3000)
        out.append({"n": n, "name": private._manager_name(seed, ticker, period * 10 + n + 1), "quality": quality, "pay": pay})
    return out


def hire_manager(conn: Connection, player_id, company_id, n: int, now: datetime) -> dict:
    with conn.transaction():
        state = _open(conn, now)
        seat, empire, company = _owned(conn, player_id, company_id)
        if empire["head_player_id"] != player_id:
            raise EmpireError("The head hires a company's managing director.")
        pick = next((c for c in candidates(conn, company_id, state["period"]) if c["n"] == n), None)
        if pick is None:
            raise EmpireError("There is no such candidate.")
        conn.execute("UPDATE company_managers SET left_period = %s WHERE company_id = %s AND left_period IS NULL", (state["period"], company_id))
        conn.execute("INSERT INTO company_managers (company_id, name, quality, pay, hired_period) VALUES (%s, %s, %s, %s, %s)",
                     (company_id, pick["name"], pick["quality"], pick["pay"], state["period"]))
        _log(conn, empire["id"], f"{company['name']} has a new managing director, {pick['name']}, paid {_money(pick['pay'])} a quarter.", now)
        return pick


def _airline(conn: Connection, player_id, company_id) -> tuple[dict, dict, dict]:
    seat, empire, company = _owned(conn, player_id, company_id)
    if company["sector"] != "aviation":
        raise EmpireError("Only an airline flies routes.")
    return seat, empire, company


def open_route(conn: Connection, player_id, company_id, city_a: str, city_b: str, now: datetime) -> dict:
    with conn.transaction():
        state = _open(conn, now)
        seat, empire, company = _airline(conn, player_id, company_id)
        pair = tuple(sorted((city_a, city_b)))
        if pair not in private.route_pairs():
            raise EmpireError("A route joins two of the five cities.")
        try:
            with conn.transaction():
                route = _one(conn, "INSERT INTO airline_routes (company_id, city_a, city_b, opened_period) VALUES (%s, %s, %s, %s) RETURNING id",
                             (company_id, pair[0], pair[1], state["period"]))
        except Exception:
            raise EmpireError("The airline already flies that route.") from None
        _log(conn, empire["id"], f"{company['name']} opened a route between {pair[0]} and {pair[1]}.", now)
        return route


def close_route(conn: Connection, player_id, route_id: int, now: datetime) -> None:
    with conn.transaction():
        state = _open(conn, now)
        route = _one(conn, "SELECT * FROM airline_routes WHERE id = %s AND closed_period IS NULL FOR UPDATE", (route_id,))
        if route is None:
            raise EmpireError("There is no such route open.")
        _airline(conn, player_id, route["company_id"])
        conn.execute("UPDATE company_assets SET route_id = NULL WHERE route_id = %s", (route_id,))
        conn.execute("UPDATE airline_routes SET closed_period = %s WHERE id = %s", (state["period"], route_id))


def set_fare(conn: Connection, player_id, route_id: int, fare_bps: int, now: datetime) -> None:
    with conn.transaction():
        _open(conn, now)
        route = _one(conn, "SELECT * FROM airline_routes WHERE id = %s AND closed_period IS NULL FOR UPDATE", (route_id,))
        if route is None:
            raise EmpireError("There is no such route open.")
        _airline(conn, player_id, route["company_id"])
        if not _whole(fare_bps, 6000, 16000):
            raise EmpireError("A fare from 60% to 160% of the usual.")
        conn.execute("UPDATE airline_routes SET fare_bps = %s WHERE id = %s", (fare_bps, route_id))


def assign_plane(conn: Connection, player_id, asset_id: int, route_id, now: datetime) -> None:
    """Put a plane on a route (or take it off). A plane flies from the city of its route's first end."""
    with conn.transaction():
        _open(conn, now)
        asset = _one(conn, "SELECT * FROM company_assets WHERE id = %s AND kind = 'plane' AND status IN ('working', 'grounded') FOR UPDATE", (asset_id,))
        if asset is None:
            raise EmpireError("There is no such plane.")
        _airline(conn, player_id, asset["company_id"])
        base = asset["base"]
        if route_id is not None:
            route = _one(conn, "SELECT * FROM airline_routes WHERE id = %s AND company_id = %s AND closed_period IS NULL", (route_id, asset["company_id"]))
            if route is None:
                raise EmpireError("The airline does not fly that route.")
            base = route["city_a"] if base not in (route["city_a"], route["city_b"]) else base
        conn.execute("UPDATE company_assets SET route_id = %s, base = %s WHERE id = %s", (route_id, base, asset_id))


# ---------------------------------------------------------------------------
# The 100-day plan, and the company doctor
# ---------------------------------------------------------------------------

def start_plan(conn: Connection, player_id, company_id, code: str, now: datetime) -> dict:
    """In the first quarters after buying, the head sets out improvements. Each is paid for at once; it may fail."""
    with conn.transaction():
        state = _open(conn, now)
        seat, empire, company = _owned(conn, player_id, company_id)
        if empire["head_player_id"] != player_id:
            raise EmpireError("The head sets out the 100-day plan.")
        if code not in PLANS:
            raise EmpireError("There is no such improvement.")
        if state["period"] > company["bought_period"] + PLAN_WINDOW:
            raise EmpireError("The 100-day plan is set out in the first two quarters after buying.")
        if _one(conn, "SELECT count(*) AS n FROM company_plans WHERE company_id = %s AND kind = 'hundred_days' AND empire_id = %s"
                      " AND started_period >= %s", (company_id, empire["id"], company["bought_period"]))["n"] >= PLANS_MOST:
            raise EmpireError("A 100-day plan has at most three parts.")
        title, cost_bps, quarters, chance, _effect = PLANS[code]
        cost = apply_bps(_quarter_sales(conn, company_id), cost_bps)
        if code == "fix_assets":
            cost = apply_bps(sum(a["cost"] for a in private.assets(conn, company_id)), cost_bps)
        boss = private.manager(conn, company_id)
        chance = min(chance + ((boss["quality"] if boss else 3) - 3) * 500, 9500)
        sector = "manufacturing" if code in ("fix_assets", "systems") else "media"
        try:
            ledger.transfer(conn, payer=company["account_id"], receiver=_supplier(conn, sector)["account_id"], amount=cost, kind="business_purchase",
                            memo=f"{company['name']}: {title.lower()}", period=state["period"])
        except ledger.InsufficientFunds:
            raise EmpireError(f"It costs {_money(cost)}; the company has not the cash.") from None
        try:
            with conn.transaction():
                plan = _one(conn, "INSERT INTO company_plans (company_id, empire_id, kind, code, cost, chance_bps, started_period, due_period, status, at)"
                                  " VALUES (%s, %s, 'hundred_days', %s, %s, %s, %s, %s, 'running', %s) RETURNING *",
                            (company_id, empire["id"], code, cost, chance, state["period"], state["period"] + quarters - 1, now))
        except Exception:
            raise EmpireError("That improvement is already under way.") from None
        _log(conn, empire["id"], f"{company['name']}: \"{title}\" is under way, at a cost of {_money(cost)}.", now)
        return {"id": plan["id"], "cost": cost, "chance_bps": chance}


def failing(conn: Connection, company_id) -> bool:
    r = _rows(conn, "SELECT payables, principal_overdue, net_profit FROM company_results WHERE company_id = %s AND period >= 1 ORDER BY period DESC LIMIT 2",
              (company_id,))
    if not r:
        return False
    return r[0]["payables"] > 0 or r[0]["principal_overdue"] > 0 or (len(r) == 2 and r[0]["net_profit"] < 0 and r[1]["net_profit"] < 0)


def propose_rescue(conn: Connection, player_id, company_id, measures: list, fee: int, now: datetime) -> dict:
    """An Accountant offers a failing private company a rescue plan, for a fee paid only if it works."""
    with conn.transaction():
        state = _open(conn, now)
        if careers.career(conn, player_id, "accountant") is None:
            raise EmpireError("A rescue plan is drawn up by an Accountant.")
        company = _one(conn, "SELECT * FROM companies WHERE id = %s AND NOT listed AND status = 'trading' FOR UPDATE", (company_id,))
        if company is None or not failing(conn, company_id):
            raise EmpireError("Only a private company in trouble needs a rescue.")
        if not isinstance(measures, list) or not measures or len(set(measures)) != len(measures) or any(m not in RESCUE for m in measures):
            raise EmpireError("Choose the measures of the plan.")
        if not _whole(fee, 0, apply_bps(_quarter_sales(conn, company_id), RESCUE_FEE_MOST_BPS)):
            raise EmpireError("A fee of at most 5% of a quarter's sales.")
        if _one(conn, "SELECT 1 FROM company_plans WHERE company_id = %s AND kind = 'rescue' AND (status IN ('proposed', 'running')"
                      " OR (status IN ('done', 'failed') AND started_period > %s))", (company_id, state["period"] - RESCUE_EVERY)):
            raise EmpireError("A company has one rescue a year at most, and one is proposed, under way, or was tried within the year.")
        owner = private.controller(conn, company_id)
        seat = empires.seat_of(conn, player_id)
        if owner and seat and seat["empire_id"] == owner["empire_id"]:
            raise EmpireError("A member of the empire that owns the company cannot be paid to rescue it: the doctor comes from outside.")
        for measure in measures:
            if not _measure_applies(conn, company_id, measure, state["period"]):
                raise EmpireError(f"\"{RESCUE[measure][0]}\" would change nothing at this company. A plan is paid for what it does.")
        plan = _one(conn, "INSERT INTO company_plans (company_id, empire_id, kind, code, fee, doctor_id, started_period, due_period, status, at)"
                          " VALUES (%s, %s, 'rescue', %s, %s, %s, %s, %s, 'proposed', %s) RETURNING *",
                    (company_id, owner["empire_id"] if owner else None, ",".join(sorted(measures)), fee, player_id, state["period"],
                     state["period"] + RESCUE_QUARTERS, now))
        if owner is None or owner["empire_kind"] != "player":
            # The founders (or a computer-run owner) accept a sensible plan at once.
            if fee <= apply_bps(_quarter_sales(conn, company_id), FOUNDERS_ACCEPT_FEE_BPS):
                _start_rescue(conn, plan, state["period"], now)
            else:
                conn.execute("UPDATE company_plans SET status = 'refused', outcome = 'The owners would not pay so much.' WHERE id = %s", (plan["id"],))
        else:
            _log(conn, owner["empire_id"], f"An Accountant has offered a rescue plan for {company['name']}, for a fee of {_money(fee)} if it works.", now)
        return {"id": plan["id"]}


def _measure_applies(conn: Connection, company_id, measure: str, period: int) -> bool:
    if measure == "sell_grounded":
        return any(a["status"] == "grounded" for a in private.assets(conn, company_id))
    if measure == "extend_loans":
        return _one(conn, "SELECT 1 FROM company_debts WHERE company_id = %s AND kind = 'bank_loan' AND principal_outstanding > 0"
                          " AND maturity_period <= %s", (company_id, period + 2)) is not None
    if measure == "skip_dividends":
        return _one(conn, "SELECT dividends_paid FROM company_results WHERE company_id = %s ORDER BY period DESC LIMIT 1", (company_id,))["dividends_paid"] > 0 \
            or _one(conn, "SELECT payout_bps FROM companies WHERE id = %s", (company_id,))["payout_bps"] > 0
    return True


def answer_rescue(conn: Connection, head_id, plan_id: int, accept: bool, now: datetime) -> None:
    with conn.transaction():
        state = _open(conn, now)
        empire = empires._head(conn, head_id)
        plan = _one(conn, "SELECT * FROM company_plans WHERE id = %s AND empire_id = %s AND kind = 'rescue' AND status = 'proposed' FOR UPDATE",
                    (plan_id, empire["id"]))
        if plan is None:
            raise EmpireError("There is no such rescue plan waiting.")
        if not accept:
            conn.execute("UPDATE company_plans SET status = 'refused', outcome = 'The owners said no.' WHERE id = %s", (plan_id,))
            return
        _start_rescue(conn, plan, state["period"], now)


def _start_rescue(conn: Connection, plan: dict, period: int, now: datetime) -> None:
    company = _one(conn, "SELECT * FROM companies WHERE id = %s", (plan["company_id"],))
    for code in plan["code"].split(","):
        if code == "cut_costs":
            conn.execute("UPDATE private_profiles SET opex_adj_bps = greatest(opex_adj_bps - 1000, -3000), morale_bps = morale_bps - 1500"
                         " WHERE company_id = %s", (company["id"],))
        elif code == "sell_grounded":
            for asset in private.assets(conn, company["id"]):
                if asset["status"] == "grounded":
                    _sell_quietly(conn, company, asset, period, now)
        elif code == "skip_dividends":
            conn.execute("UPDATE private_profiles SET no_dividend_until = %s WHERE company_id = %s", (period + 1, company["id"]))
        elif code == "extend_loans":
            rows = _rows(conn, "SELECT operating_profit, depreciation FROM company_results WHERE company_id = %s AND period >= 1 ORDER BY period DESC LIMIT 4",
                         (company["id"],))
            if sum(r["operating_profit"] + r["depreciation"] for r in rows) > 0:
                conn.execute("UPDATE company_debts SET maturity_period = greatest(maturity_period, %s) + 4 WHERE company_id = %s AND kind = 'bank_loan'"
                             " AND principal_outstanding > 0 AND maturity_period <= %s", (period, company["id"], period + 2))
    conn.execute("UPDATE company_plans SET status = 'running', started_period = %s, due_period = %s WHERE id = %s",
                 (period, period + RESCUE_QUARTERS, plan["id"]))


def _sell_quietly(conn: Connection, company: dict, asset: dict, period: int, now: datetime) -> int:
    book = book_values(conn, company["id"]).get(asset["id"], 0)
    proceeds = min(apply_bps(book, ASSET_SALE_BPS[0] + ASSET_SALE_BPS[1] * asset["condition_bps"] // BPS),
                   ledger.balance(conn, ledger.account_id(conn, ledger.INVESTORS_FOUNDERS)))
    if proceeds:
        ledger.transfer(conn, payer=ledger.account_id(conn, ledger.INVESTORS_FOUNDERS), receiver=company["account_id"], amount=proceeds,
                        kind="asset_sale", memo=f"{company['name']}: {asset['name']} sold", period=period, reference=f"asset:{asset['id']}")
    conn.execute("INSERT INTO company_asset_sales (company_id, asset_id, period, book, proceeds, at) VALUES (%s, %s, %s, %s, %s, %s)",
                 (company["id"], asset["id"], period, book, proceeds, now))
    conn.execute("UPDATE company_assets SET status = 'sold', route_id = NULL, ended_period = %s WHERE id = %s", (period, asset["id"]))
    return proceeds


# ---------------------------------------------------------------------------
# After every company has closed its quarter
# ---------------------------------------------------------------------------

def after_companies(conn: Connection, period: int, seed: str, now: datetime) -> None:
    _judge_plans(conn, period, seed, now)
    _administrations(conn, period, now)
    _listings(conn, period, now)
    _computer_resales(conn, period, seed, now)
    if period % clock.QUARTERS_PER_YEAR == 0:
        _deal_of_the_year(conn, period, now)


def _judge_plans(conn: Connection, period: int, seed: str, now: datetime) -> None:
    for plan in _rows(conn, "SELECT * FROM company_plans WHERE status = 'running' AND due_period <= %s ORDER BY id FOR UPDATE", (period,)):
        company = _one(conn, "SELECT * FROM companies WHERE id = %s", (plan["company_id"],))
        if company["status"] != "trading":
            conn.execute("UPDATE company_plans SET status = 'failed', outcome = 'The company failed first.' WHERE id = %s", (plan["id"],))
            continue
        if plan["kind"] == "hundred_days":
            works = private.roll(seed, "plan", plan["id"]) < plan["chance_bps"]
            if works:
                effect = {"suppliers": ("labour_adj_bps", -300), "systems": ("labour_adj_bps", -500), "head_office": ("opex_adj_bps", -800),
                          "rebrand": ("pull_adj_bps", 800), "pricing": ("pull_adj_bps", 200)}.get(plan["code"])
                if effect:
                    conn.execute(f"UPDATE private_profiles SET {effect[0]} = {effect[0]} + %s WHERE company_id = %s", (effect[1], company["id"]))
                if plan["code"] == "pricing":
                    conn.execute("UPDATE private_profiles SET labour_adj_bps = labour_adj_bps - 100 WHERE company_id = %s", (company["id"],))
                if plan["code"] == "head_office":
                    conn.execute("UPDATE private_profiles SET morale_bps = morale_bps - 1000 WHERE company_id = %s", (company["id"],))
                if plan["code"] == "fix_assets":
                    conn.execute("UPDATE company_assets SET condition_bps = least(condition_bps + 3000, 10000), status = 'working'"
                                 " WHERE company_id = %s AND status IN ('working', 'grounded')", (company["id"],))
            words = f"{PLANS[plan['code']][0]}: " + (PLANS[plan["code"]][4] if works else "it did not work. The money is spent.")
            conn.execute("UPDATE company_plans SET status = %s, outcome = %s WHERE id = %s", ("done" if works else "failed", words, plan["id"]))
            if plan["empire_id"]:
                _log(conn, plan["empire_id"], f"{company['name']}: {words}", now)
        else:
            r = _one(conn, "SELECT payables, principal_overdue, net_profit FROM company_results WHERE company_id = %s ORDER BY period DESC LIMIT 1",
                     (company["id"],))
            saved = r["payables"] == 0 and r["principal_overdue"] == 0 and r["net_profit"] > 0
            # The fee is the company's cost in its next quarter's accounts: paid then, or owed if it has not the cash.
            words = (f"The rescue of {company['name']} worked. The Accountant's fee of {_money(plan['fee'])} is paid with its next quarter's bills."
                     if saved else f"The rescue of {company['name']} did not work. No fee is paid.")
            conn.execute("UPDATE company_plans SET status = %s, outcome = %s WHERE id = %s", ("done" if saved else "failed", words, plan["id"]))
            mine = careers.career(conn, plan["doctor_id"], "accountant")
            careers._event(conn, plan["doctor_id"], "accountant", "rescue", words, now)
            if saved and mine:
                careers.add_experience(conn, plan["doctor_id"], "accountant", firm.DUTY_EXPERIENCE * 2 * (1 + mine["rank"]), now)
            if plan["empire_id"]:
                _log(conn, plan["empire_id"], words, now)


def _administrations(conn: Connection, period: int, now: datetime) -> None:
    """A private company behind on its bills or loans for two closes running, and owing more than it owns, is
    wound up. Its assets are sold, and those it owes are paid in order: secured lenders, staff, tax, other
    creditors; what is left, if anything, goes to its owners."""
    for c in _rows(conn, "SELECT c.* FROM companies c WHERE NOT c.listed AND c.status = 'trading' ORDER BY c.ticker FOR UPDATE"):
        rows = _rows(conn, "SELECT * FROM company_results WHERE company_id = %s AND period >= 1 ORDER BY period DESC LIMIT %s",
                     (c["id"], TROUBLE_QUARTERS))
        if not in_trouble(rows):
            continue
        if _one(conn, "SELECT 1 FROM company_plans WHERE company_id = %s AND kind = 'rescue' AND status = 'running'", (c["id"],)):
            continue                                         # a rescue under way is given its time
        _wind_up(conn, c, rows[0], period, now)


def in_trouble(rows: list[dict]) -> bool:
    """Behind on its bills or loans at each of the last two closes, and owing more than it owns at the last."""
    return (len(rows) >= TROUBLE_QUARTERS and all(r["payables"] > 0 or r["principal_overdue"] > 0 for r in rows[:TROUBLE_QUARTERS])
            and rows[0]["total_equity"] < 0)


def _wind_up(conn: Connection, c: dict, last: dict, period: int, now: datetime) -> None:
    conn.execute("UPDATE companies SET status = 'administration' WHERE id = %s", (c["id"],))
    for sale in _rows(conn, "SELECT * FROM sale_processes WHERE company_id = %s AND status = 'open' FOR UPDATE", (c["id"],)):
        from simulation import firm_deals
        for bid in _rows(conn, "SELECT * FROM deal_bids WHERE process_id = %s AND status IN ('pending', 'live') FOR UPDATE", (sale["id"],)):
            firm_deals._release(conn, bid, "lost", period)
        conn.execute("UPDATE sale_processes SET status = 'withdrawn', outcome = 'The company went into administration.' WHERE id = %s", (sale["id"],))
        conn.execute("UPDATE deal_files SET status = 'lost' WHERE process_id = %s AND status = 'open'", (sale["id"],))
    raised = 0
    books = book_values(conn, c["id"])
    buyer = ledger.account_id(conn, ledger.INVESTORS_FOUNDERS)
    for asset in private.assets(conn, c["id"]):
        price = min(apply_bps(books.get(asset["id"], 0), ADMIN_ASSET_BPS), ledger.balance(conn, buyer))
        if price > 0:
            ledger.transfer(conn, payer=buyer, receiver=c["account_id"], amount=price, kind="asset_sale",
                            memo=f"{c['name']} in administration: {asset['name']} sold", period=period)
            raised += price
        conn.execute("UPDATE company_assets SET status = 'sold', route_id = NULL, ended_period = %s WHERE id = %s", (period, asset["id"]))
    owed_total = 0
    paid_list = []
    treasury = ledger.account_id(conn, ledger.TREASURY)

    def pay(to, wanted: int, kind: str, who: str, rank: int) -> int:
        got = ledger.pay_up_to(conn, payer=c["account_id"], receiver=to, wanted=wanted, kind=kind,
                               memo=f"{c['name']} in administration: paid to {who}", period=period) if wanted > 0 else 0
        paid_list.append({"who": who, "rank": rank, "owed": wanted, "paid": got})
        return got

    for d in _rows(conn, "SELECT * FROM company_debts WHERE company_id = %s AND principal_outstanding > 0 ORDER BY kind, id FOR UPDATE", (c["id"],)):
        owed_total += d["principal_outstanding"]
        if d["kind"] == "bond":
            continue
        receiver = treasury if d["kind"] == "central_bank_loan" else d["lender_account_id"]
        got = pay(receiver, d["principal_outstanding"], "debt_repayment", d["name"], 1)
        conn.execute("UPDATE company_debts SET principal_outstanding = principal_outstanding - %s, maturity_period = least(maturity_period, %s)"
                     " WHERE id = %s", (got, period, d["id"]))
    for rank, kinds, who in ((2, ("wages",), "its staff"), (3, ("company_tax",), "the tax office"), (4, None, "other creditors")):
        for p in _rows(conn, "SELECT * FROM company_payables WHERE company_id = %s AND amount_outstanding > 0 ORDER BY incurred_period, id FOR UPDATE",
                       (c["id"],)):
            if (kinds and p["kind"] not in kinds) or (kinds is None and p["kind"] in ("wages", "company_tax")):
                continue
            owed_total += p["amount_outstanding"]
            got = pay(p["payee_account_id"], p["amount_outstanding"], p["kind"], who, rank)
            conn.execute("UPDATE company_payables SET amount_outstanding = amount_outstanding - %s WHERE id = %s", (got, p["id"]))
    for d in _rows(conn, "SELECT * FROM company_debts WHERE company_id = %s AND kind = 'bond' AND principal_outstanding > 0 FOR UPDATE", (c["id"],)):
        got = pay(d["lender_account_id"], d["principal_outstanding"], "debt_repayment", d["name"], 5)
        conn.execute("UPDATE company_debts SET principal_outstanding = principal_outstanding - %s WHERE id = %s", (got, d["id"]))
    left = ledger.balance(conn, c["account_id"])
    to_owners: dict = {}
    if left > 0:
        owners = {r["account_id"]: r["balance"] for r in _rows(conn, "SELECT account_id, balance FROM ledger_balances WHERE asset = %s AND balance > 0"
                                                                        " AND account_id <> %s", (c["share_asset"], c["account_id"]))}
        total = sum(owners.values()) or 1
        amounts = {a: left * s // total for a, s in owners.items()}
        ledger.pay_split_up_to(conn, payer=c["account_id"], amounts=amounts, kind="dividend", memo=f"{c['name']}: what was left for its owners",
                               period=period)
        to_owners = amounts
        paid_list.append({"who": "its owners", "rank": 6, "owed": 0, "paid": sum(amounts.values())})
    conn.execute("INSERT INTO administrations (company_id, started_period, ended_period, raised, paid, words) VALUES (%s, %s, %s, %s, %s, %s)",
                 (c["id"], period, period, raised, empires_json(paid_list),
                  f"Assets fetched {_money(raised)} against {_money(owed_total)} owed."))
    conn.execute("UPDATE companies SET status = 'wound_up' WHERE id = %s", (c["id"],))
    private._news(conn, period + 1, 3, "administration", f"administration:{c['ticker']}",
                  {"company": c["name"], "city": c["headquarters"], "owed": _money(owed_total), "recovered": _money(raised)})
    for stake in _rows(conn, "SELECT s.empire_id, e.account_id FROM company_stakes s JOIN empires e ON e.id = s.empire_id WHERE s.company_id = %s",
                       (c["id"],)):
        exited(conn, stake["empire_id"], c["id"], "administration", to_owners.get(stake["account_id"], 0), period, now, forced=True)
    conn.execute("DELETE FROM owned_companies WHERE company_id = %s", (c["id"],))


def empires_json(value):
    from psycopg.types.json import Jsonb
    return Jsonb(value)


def _listings(conn: Connection, period: int, now: datetime) -> None:
    """A company an empire controlled that is now listed: the empire's stake is counted out at the listing price."""
    for row in _rows(conn, "SELECT s.*, c.share_asset, m.listing_price, e.account_id FROM company_stakes s JOIN companies c ON c.id = s.company_id"
                           " JOIN market_instruments m ON m.company_id = c.id JOIN empires e ON e.id = s.empire_id WHERE c.listed"):
        held = ledger.balance(conn, row["account_id"], row["share_asset"])
        exited(conn, row["empire_id"], row["company_id"], "listing", held * row["listing_price"], period, now)
    conn.execute("DELETE FROM owned_companies o USING companies c WHERE c.id = o.company_id AND c.listed")


def _computer_resales(conn: Connection, period: int, seed: str, now: datetime) -> None:
    for row in _rows(conn, "SELECT o.*, e.account_id, c.share_asset FROM owned_companies o JOIN empires e ON e.id = o.empire_id"
                           " JOIN companies c ON c.id = o.company_id WHERE e.kind = 'computer' AND c.status = 'trading' AND NOT c.listed"
                           " AND o.bought_period <= %s AND NOT EXISTS (SELECT 1 FROM sale_processes s WHERE s.company_id = o.company_id"
                           " AND s.status = 'open')", (period - COMPUTER_HOLD,)):
        shares = ledger.balance(conn, row["account_id"], row["share_asset"])
        if shares > 0 and private.roll(seed, "resale", row["company_id"], period) < 3000:
            private.start_sale(conn, row["company_id"], row["account_id"], row["empire_id"], shares, period, seed, now)


# ---------------------------------------------------------------------------
# Getting out
# ---------------------------------------------------------------------------

def sell_to_empire(conn: Connection, head_id, company_id, asking: int, reserve: int, mode: str, now: datetime) -> dict:
    """Put the empire's stake up for sale, by sealed bids or at auction. Other empires, and the computer-run
    ones, bid as for any company. Partners keep their shares, with the new owner."""
    with conn.transaction():
        state = _open(conn, now)
        seat, empire, company = _owned(conn, head_id, company_id)
        if empire["head_player_id"] != head_id:
            raise EmpireError("The head decides to sell.")
        if mode not in ("sealed", "auction") or not _whole(asking, 1, 10**17) or not _whole(reserve, 1, asking):
            raise EmpireError("Name the way of selling, an asking price, and a lowest price at or below it.")
        held_value = private.value_of(conn, company_id) * ledger.balance(conn, empire["account_id"], company["share_asset"]) // max(
            ledger.amount_in_existence(conn, company["share_asset"]), 1)
        if reserve * BPS < held_value * SALE_FLOOR_BPS:
            raise EmpireError(f"A head may not sell the empire's company for less than {SALE_FLOOR_BPS // 100}% of what it is worth "
                              f"({_money(apply_bps(held_value, SALE_FLOOR_BPS))}): that would be giving the members' money away.")
        if company["listed"] or _one(conn, "SELECT 1 FROM sale_processes WHERE company_id = %s AND status = 'open'", (company_id,)) or \
                _one(conn, "SELECT 1 FROM share_offers WHERE company_id = %s AND status = 'open'", (company_id,)):
            raise EmpireError("That company is already on sale, or its listing is under way.")
        shares = ledger.balance(conn, empire["account_id"], company["share_asset"])
        sale_id = private.start_sale(conn, company_id, empire["account_id"], empire["id"], shares, state["period"], private._seed(conn), now,
                                     asking=asking, reserve=reserve, mode=mode)
        _log(conn, empire["id"], f"The head put {company['name']} up for sale {'by sealed bids' if mode == 'sealed' else 'at auction'}, asking {_money(asking)}.", now)
        return {"sale_id": sale_id}


def buyer_offer(conn: Connection, company_id) -> dict:
    """What the computer-run buyer (the pension funds) would pay for every share the owners in empires hold."""
    company = _one(conn, "SELECT * FROM companies WHERE id = %s", (company_id,))
    in_issue = ledger.amount_in_existence(conn, company["share_asset"])
    # The lower of its valuation now and its average over the last year: a quarter's profit pumped up does not sell.
    year = _rows(conn, "SELECT value_per_share FROM company_valuations WHERE company_id = %s ORDER BY period DESC LIMIT 4", (company_id,))
    average = sum(max(r["value_per_share"], 0) for r in year) // max(len(year), 1) * in_issue
    per_share = apply_bps(min(private.value_of(conn, company_id), average), BUYER_DISCOUNT_BPS) // max(in_issue, 1)
    return {"per_share": per_share, "cash": ledger.balance(conn, ledger.account_id(conn, ledger.INVESTORS_INSTITUTIONS))}


def sell_to_buyer(conn: Connection, head_id, company_id, now: datetime) -> dict:
    """Sell to the computer-run buyer at once. Partners sell alongside, at the same price a share."""
    with conn.transaction():
        state = _open(conn, now)
        seat, empire, company = _owned(conn, head_id, company_id)
        if empire["head_player_id"] != head_id:
            raise EmpireError("The head decides to sell.")
        if _one(conn, "SELECT 1 FROM sale_processes WHERE company_id = %s AND status = 'open'", (company_id,)) or \
                _one(conn, "SELECT 1 FROM share_offers WHERE company_id = %s AND status = 'open'", (company_id,)):
            raise EmpireError("That company is on sale, or its listing is under way, already.")
        offer = buyer_offer(conn, company_id)
        if offer["per_share"] <= 0:
            raise EmpireError("No buyer will pay anything for it.")
        holders = _rows(conn, "SELECT b.account_id, b.balance, e.id AS empire_id FROM ledger_balances b JOIN empires e ON e.account_id = b.account_id"
                              " WHERE b.asset = %s AND b.balance > 0 ORDER BY e.id", (company["share_asset"],))
        total = sum(h["balance"] for h in holders) * offer["per_share"]
        if total > offer["cash"]:
            raise EmpireError("The buyer has not the cash for it this quarter.")
        funds = ledger.account_id(conn, ledger.INVESTORS_INSTITUTIONS)
        for h in holders:
            ledger.transfer(conn, payer=h["account_id"], receiver=funds, amount=h["balance"], asset=company["share_asset"], kind="company_sale",
                            memo=f"{company['name']}: shares sold to the pension funds", period=state["period"])
            ledger.transfer(conn, payer=funds, receiver=h["account_id"], amount=h["balance"] * offer["per_share"], kind="company_sale",
                            memo=f"The price of {company['name']} shares", period=state["period"])
            if h["empire_id"] != empire["id"]:
                _log(conn, h["empire_id"], f"Its shares in {company['name']} were sold alongside the controlling empire's, for "
                                           f"{_money(h['balance'] * offer['per_share'])}.", now)
        mine = next(h for h in holders if h["empire_id"] == empire["id"])["balance"] * offer["per_share"]
        for h in holders:
            exited(conn, h["empire_id"], company_id, "to_buyer", h["balance"] * offer["per_share"], state["period"], now)
        from simulation import firm_deals
        firm_deals._take_control(conn, company_id, state["period"], now)
        return {"proceeds": mine}


def list_on_exchange(conn: Connection, head_id, company_id, now: datetime) -> dict:
    """List the company: new shares (a quarter more) are sold to the public at a tenth below its valuation, and
    from the next close its shares trade on the exchange. The empire keeps its shares, and can sell them there."""
    from simulation import corporate
    with conn.transaction():
        state = _open(conn, now)
        seat, empire, company = _owned(conn, head_id, company_id)
        if empire["head_player_id"] != head_id:
            raise EmpireError("The head decides to list a company.")
        last = _one(conn, "SELECT * FROM company_results WHERE company_id = %s ORDER BY period DESC LIMIT 1", (company_id,))
        if last["total_equity"] <= 0 or last["net_profit"] <= 0 or failing(conn, company_id):
            raise EmpireError("Only a company that is profitable and paying its way can be listed.")
        if _one(conn, "SELECT 1 FROM share_offers WHERE company_id = %s AND status = 'open'", (company_id,)):
            raise EmpireError("Its listing is already announced.")
        if _one(conn, "SELECT 1 FROM sale_processes WHERE company_id = %s AND status = 'open'", (company_id,)):
            raise EmpireError("It is on sale. A company is sold or listed, not both at once.")
        in_issue = ledger.amount_in_existence(conn, company["share_asset"])
        price = apply_bps(private.value_of(conn, company_id), LISTING_DISCOUNT_BPS) // max(in_issue, 1)
        if price <= 0:
            raise EmpireError("It has no value to list at.")
        shares = apply_bps(in_issue, LISTING_NEW_BPS)
        corporate.announce_offer(conn, {**company, "sector_name": company["sector"]}, kind="ipo", price=price, shares=shares,
                                 period=state["period"], reason=f"Its owners, {empire['name']}, are bringing it to the exchange.", now=now)
        _log(conn, empire["id"], f"The head announced the listing of {company['name']}: {shares:,} new shares at {_money(price)} each.", now)
        return {"price": price, "shares": shares}


def exited(conn: Connection, empire_id, company_id, kind: str, proceeds: int, period: int, now: datetime, *, forced: bool = False) -> None:
    """An empire has got out of a company. Its gain is worked out against what it paid; those who did the
    work on the deal are paid their fees out of a gain; the deal goes into the league tables."""
    owned = _one(conn, "SELECT * FROM owned_companies WHERE company_id = %s AND empire_id = %s", (company_id, empire_id))
    deal = _one(conn, "SELECT * FROM deals WHERE company_id = %s AND empire_id = %s AND status = 'held' ORDER BY id DESC LIMIT 1", (company_id, empire_id))
    stake = _one(conn, "SELECT cost FROM company_stakes WHERE company_id = %s AND empire_id = %s", (company_id, empire_id))
    cost = stake["cost"] if stake else (owned["cost"] if owned else 0)
    gain = proceeds - cost
    empire = empires._empire(conn, empire_id)
    fees = []
    if gain > 0 and not forced and deal and empire["kind"] == "player":
        bid = _one(conn, "SELECT * FROM deal_bids WHERE id = %s", (deal["bid_id"],))
        f = _one(conn, "SELECT * FROM deal_files WHERE id = %s", (bid["file_id"],)) if bid and bid["file_id"] else None
        team = []
        if f and f["brought_by"]:
            team.append((f["brought_by"], "investment_banker", DEAL_FEE_BRING_BPS, "bringing the deal"))
        if f:
            for s in _rows(conn, "SELECT * FROM deal_steps WHERE file_id = %s AND done_by IS NOT NULL", (f["id"],)):
                team.append((s["done_by"], s["build"], DEAL_FEE_CHECK_BPS, s["step"]))
        state = careers.world_now(conn, now)
        for player_id, build, bps, why in team:
            fee = apply_bps(gain, bps)
            paid = ledger.pay_up_to(conn, payer=empire["account_id"], receiver=ledger.player_account_id(conn, player_id), wanted=fee,
                                    kind="deal_fee", memo=f"{empire['name']}: deal fee for {why}", period=period, reference=f"deal:{deal['id']}")
            if paid:
                empires._book(conn, empire_id, state["period"], "Deal fees", f"Deal fee for {why}", paid, True, now, kind="fee", desk=build)
                careers._event(conn, player_id, build, "deal_fee", f"Paid {_money(paid)} as a deal fee for {why}.", now)
                fees.append({"build": build, "why": why, "paid": paid})
    conn.execute("INSERT INTO deal_exits (company_id, empire_id, kind, proceeds, cost, gain, fees, forced, period, at)"
                 " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                 (company_id, empire_id, kind, proceeds, cost, gain, empires_json(fees), forced, period, now))
    if deal:
        conn.execute("UPDATE deals SET status = %s WHERE id = %s", ("failed" if forced else "exited", deal["id"]))
    # Only this empire's own rows go: another holder's stake, and its control, are untouched.
    conn.execute("DELETE FROM company_stakes WHERE company_id = %s AND empire_id = %s", (company_id, empire_id))
    if owned:
        conn.execute("DELETE FROM owned_companies WHERE company_id = %s AND empire_id = %s", (company_id, empire_id))
    if empire["kind"] == "player":
        points = 5 if gain > 0 and not forced else -3
        leagues.award(conn, empire_id, points, ("A gain" if gain > 0 else "A loss") + f" of {_money(abs(gain))} on a company", period, now,
                      reference=f"exit:{company_id}:{period}:{kind}")
        if empire["head_player_id"]:
            firm.ceo_note(conn, empire["head_player_id"], empire_id, "exit", f"Got out of a company ({kind.replace('_', ' ')}): "
                          f"{'gain' if gain >= 0 else 'loss'} of {_money(abs(gain))}.", period, now, good=gain > 0, reference=f"exit:{company_id}:{period}")
        _log(conn, empire_id, f"The empire got out of a company: {_money(proceeds)} against {_money(cost)} paid, "
                              f"{'a gain' if gain >= 0 else 'a loss'} of {_money(abs(gain))}.", now)


# ---------------------------------------------------------------------------
# League tables, and the Deal of the Year
# ---------------------------------------------------------------------------

def league_tables(conn: Connection, year: int | None = None) -> dict:
    """Public: the year's deals by size, exits by gain, and bankers by what they brought. Players are named
    by their display names, never by their numbers."""
    def in_year(column: str) -> str:
        return f"({column} - 1) / {clock.QUARTERS_PER_YEAR} + 1 = %s" if year else "true"
    params = (year,) if year else ()
    biggest = _rows(conn, "SELECT c.name AS company, e.name AS empire, s.price, s.opened_period FROM sale_processes s JOIN companies c ON c.id = s.company_id"
                          " LEFT JOIN deals d ON d.process_id = s.id LEFT JOIN empires e ON e.id = d.empire_id"
                          f" WHERE s.status = 'sold' AND {in_year('s.closes_period')} ORDER BY s.price DESC LIMIT 10", params)
    exits = _rows(conn, f"SELECT c.name AS company, e.name AS empire, x.kind, x.gain, x.proceeds FROM deal_exits x JOIN companies c ON c.id = x.company_id"
                        f" JOIN empires e ON e.id = x.empire_id WHERE e.kind = 'player' AND NOT x.forced AND {in_year('x.period')} ORDER BY x.gain DESC LIMIT 10", params)
    bankers = _rows(conn, "SELECT p.display_name AS banker, count(*) AS deals, sum(d.price)::bigint AS value FROM deals d"
                          " JOIN deal_bids b ON b.id = d.bid_id JOIN deal_files f ON f.id = b.file_id JOIN players p ON p.id = f.brought_by"
                          f" WHERE {in_year('d.period')} GROUP BY p.display_name ORDER BY value DESC LIMIT 10", params)
    return {"year": year, "biggest": biggest, "exits": exits, "bankers": bankers}


def _deal_of_the_year(conn: Connection, period: int, now: datetime) -> None:
    year = (period - 1) // clock.QUARTERS_PER_YEAR + 1
    best = _one(conn, "SELECT x.*, c.name AS company, e.name AS empire FROM deal_exits x JOIN companies c ON c.id = x.company_id JOIN empires e ON e.id = x.empire_id"
                      " WHERE e.kind = 'player' AND x.gain > 0 AND NOT x.forced AND (x.period - 1) / %s + 1 = %s ORDER BY x.gain DESC, x.id LIMIT 1",
                (clock.QUARTERS_PER_YEAR, year))
    if best is None:
        return
    if leagues.award(conn, best["empire_id"], 10, f"Deal of the Year: {best['company']}", period, now, reference=f"deal_of_the_year:{year}"):
        private._news(conn, period + 1, 4, "deal_of_the_year", f"deal_of_the_year:{year}",
                      {"empire": best["empire"], "company": best["company"], "gain": _money(best["gain"]), "year": f"Year {year}"})
        for member in empires.humans(conn, best["empire_id"]):
            careers._event(conn, member["player_id"], member["build"], "deal", f"Deal of the Year {year}: {best['company']}.", now)


# ---------------------------------------------------------------------------
# What a member sees
# ---------------------------------------------------------------------------

def view(conn: Connection, seat: dict, empire: dict, state: dict, now: datetime) -> dict:
    me = seat["player_id"]
    is_head = empire["head_player_id"] == me
    runs = is_head or firm.deputy_of(conn, empire["id"]) == me or seat["build"] == "asset_manager"
    out = []
    for c in _rows(conn, "SELECT c.*, o.bought_period, o.cost, s.name AS sector_name FROM owned_companies o JOIN companies c ON c.id = o.company_id"
                         " JOIN sectors s ON s.code = c.sector WHERE o.empire_id = %s ORDER BY c.name", (empire["id"],)):
        p = private.profile(conn, c["id"])
        results = list(reversed(_rows(conn, "SELECT period, revenue, operating_profit, net_profit, cash, borrowings, payables, total_equity, staff,"
                                            " dividends_paid FROM company_results WHERE company_id = %s AND period >= 1 ORDER BY period DESC LIMIT 4",
                                            (c["id"],))))
        for r in results:
            r["label"] = clock.period_label(r["period"])
        dials = private.dials_for(conn, c["id"], state["period"])
        loan = _one(conn, "SELECT * FROM empire_debts WHERE empire_id = %s AND company_id = %s AND status IN ('open', 'called', 'defaulted')",
                    (empire["id"], c["id"]))
        from simulation import firm_deals
        boss = private.manager(conn, c["id"])
        item = {
            "id": str(c["id"]), "name": c["name"], "sector": c["sector_name"], "is_airline": c["sector"] == "aviation", "city": c["headquarters"],
            "bought": clock.period_label(c["bought_period"]), "cost": c["cost"], "value": private.value_of(conn, c["id"]),
            "price_bps": c["price_bps"], "results": results, "dials": {k: dials[k] for k in ("price_bps", "staff_bps", "pay_rise_bps", "marketing",
                                                                                              "technology", "maintenance_bps", "payout_bps", "borrow",
                                                                                              "buy_assets")} if dials else None,
            "morale_bps": p["morale_bps"] if p else None, "pay_ratio_bps": p["pay_index_bps"] * BPS // max(state["wage_index_bps"], 1) if p else None,
            "manager": {"name": boss["name"], "quality": boss["quality"], "pay": boss["pay"]} if boss else None,
            "assets": private.asset_register(conn, c["id"], true=True), "unit_cost": private._unit_cost(conn, c["id"], state["period"]),
            "capacity": private.capacity(conn, c["id"], state["period"]), "routes": firm_deals._routes(conn, c["id"]),
            "plans": [{"id": r["id"], "kind": r["kind"], "code": r["code"], "status": r["status"], "outcome": r["outcome"], "cost": r["cost"],
                       "fee": r["fee"], "due": clock.period_label(r["due_period"])}
                      for r in _rows(conn, "SELECT * FROM company_plans WHERE company_id = %s ORDER BY id DESC LIMIT 8", (c["id"],))],
            "plan_open": state["period"] <= c["bought_period"] + PLAN_WINDOW,
            "loan": {"outstanding": loan["outstanding"], "rate_bps": loan["rate_bps"], "status": loan["status"], "lender": loan["lender_name"],
                     "broken": firm_deals.covenant_test(conn, loan)} if loan else None,
            "found": firm_deals.finds(conn, empire["id"], c["id"]),
            "on_sale": _one(conn, "SELECT 1 FROM sale_processes WHERE company_id = %s AND status = 'open'", (c["id"],)) is not None,
            "failing": failing(conn, c["id"]), "runs": runs,
        }
        if is_head:
            item["candidates"] = candidates(conn, c["id"], state["period"])
            item["buyer_offer"] = buyer_offer(conn, c["id"])["per_share"] * ledger.balance(conn, empire["account_id"], c["share_asset"])
        out.append(item)
    rescues = [{"id": r["id"], "company": r["company"], "fee": r["fee"], "measures": r["code"].split(",")}
               for r in _rows(conn, "SELECT p.*, c.name AS company FROM company_plans p JOIN companies c ON c.id = p.company_id WHERE p.empire_id = %s"
                                    " AND p.kind = 'rescue' AND p.status = 'proposed'", (empire["id"],))] if is_head else []
    return {"companies": out, "plans": {k: {"title": v[0], "cost_bps": v[1], "quarters": v[2], "chance_bps": v[3], "effect": v[4]} for k, v in PLANS.items()},
            "rescue_measures": {k: {"title": v[0], "words": v[1]} for k, v in RESCUE.items()}, "rescues_waiting": rescues,
            "league": league_tables(conn, (state["period"] - 1) // clock.QUARTERS_PER_YEAR + 1)}


def doctor_view(conn: Connection, player_id) -> list[dict]:
    """For an Accountant: private companies in trouble that could use a rescue, by name and the bare fact of trouble."""
    if careers.career(conn, player_id, "accountant") is None:
        return []
    out = []
    for c in _rows(conn, "SELECT c.id, c.name, c.headquarters, s.name AS sector FROM companies c JOIN sectors s ON s.code = c.sector"
                         " WHERE NOT c.listed AND c.status = 'trading' ORDER BY c.name"):
        if failing(conn, c["id"]) and not _one(conn, "SELECT 1 FROM company_plans WHERE company_id = %s AND kind = 'rescue' AND status IN ('proposed', 'running')",
                                               (c["id"],)):
            out.append({"id": str(c["id"]), "name": c["name"], "sector": c["sector"], "city": c["headquarters"]})
    return out


firm.VIEW["owned"] = lambda conn, seat, empire, state, now: view(conn, seat, empire, state, now) if firm.player_run(empire) else None
firm.WAITING.append(lambda conn, seat, empire, now: (_one(conn, "SELECT count(*) AS n FROM company_plans WHERE empire_id = %s AND kind = 'rescue'"
                                                             " AND status = 'proposed'", (empire["id"],))["n"]
                                                     if empire["head_player_id"] == seat["player_id"] else 0))
