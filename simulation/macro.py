"""Prices, wages, commodities and the Central Bank (Stage 3, Part B).

Once a quarter this module measures the economy and writes one permanent row:
the level of prices and how fast they are rising, what workers are paid, what
commodities cost, and the interest rate the Central Bank sets for the quarter
ahead.

How prices move, in plain words: when households spend more naira than the
economy has grown able to supply, prices rise. When a commodity gets dearer,
prices rise a little too. Prices move part of the way each quarter, not all at once.

The Central Bank follows a published rule (design document, section 10): when
prices rise faster than its target it raises the interest rate, which makes
borrowing dearer and slows lending and spending; when they rise slower, it cuts.
"""

from __future__ import annotations

from psycopg import Connection
from psycopg.rows import dict_row

from simulation import stochastic
from simulation import world_data as data
from simulation.money import BPS, apply_bps

COMMODITY_COLUMNS = {"energy": "energy_bps", "metals": "metals_bps",
                     "agriculture": "agriculture_bps", "materials": "materials_bps"}


def _row(conn: Connection, sql: str, params=()) -> dict | None:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchone()


def state(conn: Connection, period: int) -> dict | None:
    """The economy's recorded state at the end of a quarter."""
    return _row(conn, "SELECT * FROM economy_results WHERE period = %s", (period,))


def write_opening_state(conn: Connection, money: int) -> None:
    """The economy on the day the world begins: every index at its starting point."""
    conn.execute(
        "INSERT INTO economy_results (period, price_index_bps, inflation_bps, wage_index_bps, capacity_index_bps,"
        " policy_rate_bps, next_policy_rate_bps, rate_reason, company_sales, household_spending, money,"
        " energy_bps, metals_bps, agriculture_bps, materials_bps, premium_index_bps, confidence_bps)"
        " VALUES (0, 10000, %s, 10000, 10000, %s, %s, %s, 0, 0, %s, 10000, 10000, 10000, 10000, 10000, 10000)",
        (data.INFLATION_TARGET_BPS, data.OPENING_RATE_BPS, data.OPENING_RATE_BPS,
         "The Central Bank's opening rate.", money),
    )


def loan_rate_bps(policy_rate_bps: int, rating: str, already_overdue: bool = False) -> int:
    """What a company pays on a bank loan: the Central Bank's rate plus an amount for its risk."""
    return policy_rate_bps + data.LOAN_SPREAD_BPS[rating] + (400 if already_overdue else 0)


def credit_appetite_bps(policy_rate_bps: int) -> int:
    """How keen people and companies are to borrow at this interest rate (10000 = the usual).

    Each point the rate sits below neutral makes borrowing a quarter more attractive;
    each point above, a quarter less.
    """
    points_below = (data.NEUTRAL_RATE_BPS - policy_rate_bps) / 100
    low, high = data.CREDIT_APPETITE_LIMITS_BPS
    return int(min(max(BPS + points_below * data.CREDIT_RATE_SENSITIVITY_BPS, low), high))


def _percent(bps: int) -> str:
    return f"{bps / 100:.1f}".rstrip("0").rstrip(".") + "%"


def decide_rate(rate_now_bps: int, inflation_bps: int, extra_bps: int = 0, demand_gap_bps: int = 0) -> tuple[int, str]:
    """The Central Bank's published rule. Returns the next rate and the reason, in plain words."""
    wanted = (
        data.NEUTRAL_RATE_BPS
        + (inflation_bps - data.INFLATION_TARGET_BPS) * data.RATE_RESPONSE_BPS // BPS
        + demand_gap_bps * data.RATE_DEMAND_RESPONSE_BPS // BPS
        + extra_bps
    )
    wanted = min(max(wanted, data.RATE_FLOOR_BPS), data.RATE_CEILING_BPS)
    # It does not chase small differences: within half a point of where its rule points, it holds.
    # Otherwise it moves towards that level in quarter points, at most half a point a quarter.
    gap = wanted - rate_now_bps
    step = 0 if abs(gap) < data.RATE_HOLD_WITHIN_BPS else min(max(gap, -data.RATE_STEP_BPS), data.RATE_STEP_BPS)
    step = round(step / 25) * 25
    new_rate = rate_now_bps + step
    target = _percent(data.INFLATION_TARGET_BPS)
    if inflation_bps > data.INFLATION_TARGET_BPS + 50:
        seen = f"Prices rose {_percent(inflation_bps)} over the year, above the {target} target"
    elif inflation_bps < data.INFLATION_TARGET_BPS - 50:
        if inflation_bps >= 0:
            seen = f"Prices rose {_percent(inflation_bps)} over the year, below the {target} target"
        else:
            seen = f"Prices fell {_percent(-inflation_bps)} over the year, against a target of a {target} rise"
    else:
        seen = f"Prices rose {_percent(inflation_bps)} over the year, close to the {target} target"
    if demand_gap_bps >= 200:
        seen += ", and spending is running ahead of what the economy can supply"
    elif demand_gap_bps <= -200:
        seen += ", and spending is running short of what the economy can supply"
    if extra_bps > 0:
        seen += ", and the Money Watch has raised a warning"
    elif extra_bps < 0:
        seen += ", and with the banks in a crisis it leans towards a lower rate"
    if step > 0:
        reason = f"{seen}, so the Central Bank raised its rate from {_percent(rate_now_bps)} to {_percent(new_rate)}."
    elif step < 0:
        reason = f"{seen}, so the Central Bank cut its rate from {_percent(rate_now_bps)} to {_percent(new_rate)}."
    else:
        reason = f"{seen}. The Central Bank held its rate at {_percent(rate_now_bps)}."
    return new_rate, reason


def yearly_change_bps(conn: Connection, column: str, period: int, now: int, *, scale_up: bool = True) -> int:
    """How much a recorded figure has changed over the last year, in hundredths of a percent.

    In the first year there is less than a year to look back on. The change so far is
    scaled up to a yearly pace, unless `scale_up` is off: then it is given as it stands
    (scaling one quarter up to a year makes an ordinary quarter look like a runaway).
    """
    back = max(period - 4, 1 if column in ("company_sales", "household_spending") else 0)
    earlier = _row(conn, f"SELECT {column} AS value FROM economy_results WHERE period = %s", (back,))
    if earlier is None or not earlier["value"] or period <= back:
        return data.INFLATION_TARGET_BPS if column == "price_index_bps" else 0
    quarters = period - back
    ratio = now / earlier["value"]
    if not scale_up:
        return round((ratio - 1) * BPS)
    if column == "price_index_bps" and quarters < 4:
        # Before the game began, prices are taken to have been rising at the target pace.
        return round((ratio * (1 + data.INFLATION_TARGET_BPS / BPS) ** ((4 - quarters) / 4) - 1) * BPS)
    return round((ratio ** (4 / quarters) - 1) * BPS)


def close_quarter(conn: Connection, period: int, seed: str, *, company_sales: int, household_spending: int,
                  money: int, commodity_events: dict[str, int], premium_index_bps: int,
                  confidence_bps: int, rate_extra_bps: int, energy_bps: int | None = None, import_push_bps: int = 0) -> dict:
    """Measure the economy at the end of a quarter, set the next interest rate, and record both."""
    prev = state(conn, period - 1)
    first = state(conn, 1)
    reference = max(first["household_spending"] if first else household_spending, 1)
    capacity = apply_bps(prev["capacity_index_bps"], BPS + data.CAPACITY_GROWTH_BPS)

    # Commodities: each drifts back towards the general price level, swings a
    # little by itself, and jumps when an event hits its supply.
    commodities, push = {}, 0
    for name, (_, weight) in data.COMMODITIES.items():
        before = prev[COMMODITY_COLUMNS[name]]
        drifted = before + apply_bps(prev["price_index_bps"] - before, data.COMMODITY_RETURN_BPS)
        swing = stochastic.shock_bps(seed, f"commodity:{name}", period, "price", data.COMMODITY_SWING_BPS,
                                     data.COMMODITY_LOADINGS.get(name))
        now = max(apply_bps(apply_bps(drifted, BPS + swing), BPS + commodity_events.get(name, 0)), 1000)
        if name == "energy" and energy_bps is not None:
            now = energy_bps                   # energy is the world oil price in naira (the economy upgrade)
        commodities[name] = now
        push += (now - before) * BPS // before * weight // BPS       # its share of the general price level

    # The general price level: what households spent, against what the economy can supply.
    justified = household_spending * BPS * BPS // (reference * capacity) if reference else BPS
    # Sellers expect prices to rise at the Central Bank's target and mark up accordingly;
    # they go faster when demand outruns supply and slower when it falls short.
    expected = apply_bps(prev["price_index_bps"], data.INFLATION_TARGET_BPS // 4)
    prices = prev["price_index_bps"] + expected + apply_bps(justified - prev["price_index_bps"], data.PRICE_ADJUST_BPS)
    # A weaker naira makes what is bought abroad dearer (the economy upgrade).
    push += import_push_bps
    prices = max(prices + apply_bps(prev["price_index_bps"], push), 1000)

    quarter_rise = (prices - prev["price_index_bps"]) * BPS // prev["price_index_bps"]
    # Wages follow prices up, most of the way. They do not fall.
    wages = max(apply_bps(prev["wage_index_bps"], BPS + apply_bps(quarter_rise, data.WAGE_FOLLOWS_PRICES_BPS)),
                prev["wage_index_bps"])

    inflation = yearly_change_bps(conn, "price_index_bps", period, prices)
    rate_now = prev["next_policy_rate_bps"]
    demand_gap = (justified - prev["price_index_bps"]) * BPS // prev["price_index_bps"]
    next_rate, reason = decide_rate(rate_now, inflation, rate_extra_bps, demand_gap)

    row = {
        "period": period, "price_index_bps": prices, "inflation_bps": inflation, "wage_index_bps": wages,
        "capacity_index_bps": capacity, "policy_rate_bps": rate_now, "next_policy_rate_bps": next_rate,
        "rate_reason": reason, "company_sales": company_sales, "household_spending": household_spending,
        "money": money, "energy_bps": commodities["energy"], "metals_bps": commodities["metals"],
        "agriculture_bps": commodities["agriculture"], "materials_bps": commodities["materials"],
        "premium_index_bps": premium_index_bps, "confidence_bps": confidence_bps,
        "demand_gap_bps": demand_gap,
    }
    columns = list(row)
    conn.execute(
        f"INSERT INTO economy_results ({', '.join(columns)}) VALUES ({', '.join(['%s'] * len(columns))})",
        list(row.values()),
    )
    return row
