"""What a company is worth (design document, section 11).

Worked out from public figures only: the accounts the company has filed, its
credit rating, the Central Bank's interest rate and the rate of inflation. A
player with a calculator can reach the same figure. The computer-run investors
start from it, and then each takes its own view.

The method is "net present value":

  1. Take the profit after tax over the past year.
  2. Expect it to grow for five years: by about the rate prices are rising, plus
     a little, adjusted for how the company's own sales have been growing.
  3. After the fifth year, expect it to grow only as fast as the Central Bank's
     inflation target, for ever.
  4. Count each future year's profit for less than a naira today, because a naira
     today can earn interest. The yearly return investors want is the Central
     Bank's rate, plus an amount for the company's credit rating, plus a little
     more because owning a share is riskier than lending.
  5. Add it all up, and divide by the number of shares.

A company making losses cannot be valued on its profits. It is valued at half
the owners' funds left in it, and never below ₦1 a share.
"""

from __future__ import annotations

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from simulation import clock
from simulation import world_data as data
from simulation.money import BPS


def _rows(conn: Connection, sql: str, params=()) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def _percent(bps: int) -> str:
    return f"{abs(bps) / 100:.1f}".rstrip("0").rstrip(".") + "%"


def discount_bps(policy_rate_bps: int, rating: str) -> int:
    """The yearly return investors want from a share of a company with this credit rating."""
    wanted = policy_rate_bps + data.LOAN_SPREAD_BPS[rating] + data.SHARE_RISK_PREMIUM_BPS
    return max(wanted, data.INFLATION_TARGET_BPS + data.LEAST_DISCOUNT_ABOVE_GROWTH_BPS)


def growth_bps(inflation_bps: int, sales_growth_bps: int | None) -> int:
    """How fast profit is expected to grow over the next five years."""
    general = min(max(inflation_bps, 300), 900) + data.REAL_GROWTH_BPS
    if sales_growth_bps is None:
        return general
    own = min(max(sales_growth_bps, -500), 1500)
    return min(max((general + own) // 2, 0), 1500)


def present_value(yearly_profit: int, growth: int, discount: int, long_run: int) -> int:
    """The value today of a profit that grows for five years and then at the long-run rate for ever."""
    if yearly_profit <= 0:
        return 0
    g, r, t = growth / BPS, discount / BPS, long_run / BPS
    total, profit = 0.0, float(yearly_profit)
    for year in range(1, 6):
        profit *= 1 + g
        total += profit / (1 + r) ** year
    total += profit * (1 + t) / (r - t) / (1 + r) ** 5
    return int(total)


def assess(filed: list[dict], rating: str, policy_rate_bps: int, inflation_bps: int) -> dict:
    """Value a company from its filed reports (oldest first; the last is the latest).

    Each report is {"period", "net_profit", "revenue", "total_equity", "shares_in_issue"}.
    """
    latest = filed[-1]
    trading = [f for f in filed if f["period"] >= 1][-8:]
    year = trading[-4:]
    yearly_profit = sum(f["net_profit"] for f in year) * 4 // len(year) if year else 0
    sales_growth = None
    if len(trading) == 8:
        before = sum(f["revenue"] for f in trading[:4])
        if before > 0:
            sales_growth = (sum(f["revenue"] for f in trading[4:]) - before) * BPS // before

    growth = growth_bps(inflation_bps, sales_growth)
    discount = discount_bps(policy_rate_bps, rating)
    long_run = data.INFLATION_TARGET_BPS
    shares = latest["shares_in_issue"]
    book = latest["total_equity"]
    from_profits = present_value(yearly_profit, growth, discount, long_run)
    from_assets = max(book, 0) // 2
    # Before a company has filed any trading results there are no profits to go on:
    # it is worth the owners' funds in it.
    if not year:
        total, method = max(book, 0), "assets"
    elif from_profits >= from_assets:
        total, method = from_profits, "profits"
    else:
        total, method = from_assets, "assets"
    return {
        "period": latest["period"], "value_per_share": max(total // shares, data.LOWEST_LISTING_PRICE_KOBO),
        "method": method, "yearly_profit": yearly_profit, "growth_bps": growth, "discount_bps": discount,
        "long_run_bps": long_run, "book_per_share": book // shares, "shares_in_issue": shares,
    }


def _why_it_changed(now: dict, before: dict | None, rating: str, rating_before: str | None,
                    rate: int, rate_before: int | None) -> list[str]:
    if before is None:
        return []
    reasons = []
    change = (now["value_per_share"] - before["value_per_share"]) * BPS // before["value_per_share"]
    label = clock.period_label(now["period"])
    if now["method"] != before["method"]:
        reasons.append("It is now making a profit, so it is valued on its profits again." if now["method"] == "profits"
                       else "It is making losses, so it is valued on what is left of its owners' funds.")
    if before["yearly_profit"] > 0 and now["yearly_profit"] > 0:
        moved = (now["yearly_profit"] - before["yearly_profit"]) * BPS // before["yearly_profit"]
        if abs(moved) >= 200:
            reasons.append(f"Its profit over the past year {'rose' if moved > 0 else 'fell'} {_percent(moved)} with its {label} results.")
    if rating_before and rating != rating_before:
        order = list(data.LOAN_SPREAD_BPS)
        safer = order.index(rating) < order.index(rating_before)
        reasons.append(f"Its credit rating {'rose' if safer else 'fell'} from {rating_before} to {rating}: investors want "
                       f"{'less' if safer else 'more'} return for the risk.")
    if rate_before is not None and rate != rate_before:
        reasons.append(f"The Central Bank's rate {'rose' if rate > rate_before else 'fell'} from {_percent(rate_before)} to "
                       f"{_percent(rate)}: future profits are worth {'less' if rate > rate_before else 'more'} today.")
    if now["growth_bps"] != before["growth_bps"] and abs(now["growth_bps"] - before["growth_bps"]) >= 100:
        reasons.append(f"Its profits are now expected to grow {_percent(now['growth_bps'])} a year, "
                       f"{'up' if now['growth_bps'] > before['growth_bps'] else 'down'} from {_percent(before['growth_bps'])}.")
    if not reasons and abs(change) >= 100:
        reasons.append(f"Its {label} results changed what it is expected to earn.")
    return reasons


def value_all(conn: Connection, period: int) -> None:
    """Value every company from what it has filed up to `period`, and record it."""
    state = _rows(conn, "SELECT next_policy_rate_bps, inflation_bps FROM economy_results WHERE period = %s", (period,))
    earlier = _rows(conn, "SELECT next_policy_rate_bps FROM economy_results WHERE period = %s", (period - 1,))
    rate = state[0]["next_policy_rate_bps"] if state else data.OPENING_RATE_BPS
    inflation = state[0]["inflation_bps"] if state else data.INFLATION_TARGET_BPS
    rate_before = earlier[0]["next_policy_rate_bps"] if earlier else None

    reports: dict = {}
    for row in _rows(
        conn,
        "SELECT DISTINCT ON (company_id, period) company_id, period, credit_rating,"
        "   (figures->'income_statement'->>'net_profit')::bigint AS net_profit,"
        "   (figures->'income_statement'->>'revenue')::bigint AS revenue,"
        "   (figures->'balance_sheet'->>'total_equity')::bigint AS total_equity,"
        "   (figures->'notes'->>'shares_in_issue')::bigint AS shares_in_issue"
        " FROM company_reports WHERE period BETWEEN %s AND %s ORDER BY company_id, period, version DESC",
        (period - 8, period),
    ):
        reports.setdefault(row["company_id"], []).append(row)
    previous = {r["company_id"]: r for r in _rows(conn, "SELECT * FROM company_valuations WHERE period = %s", (period - 1,))}

    for company_id, filed in reports.items():
        if filed[-1]["period"] != period:
            continue
        rating = filed[-1]["credit_rating"]
        rating_before = filed[-2]["credit_rating"] if len(filed) >= 2 else None
        worth = assess(filed, rating, rate, inflation)
        worth["reasons"] = Jsonb(_why_it_changed(worth, previous.get(company_id), rating, rating_before, rate, rate_before))
        columns = ["company_id", *worth]
        conn.execute(
            f"INSERT INTO company_valuations ({', '.join(columns)}) VALUES ({', '.join(['%s'] * len(columns))})"
            " ON CONFLICT (company_id, period) DO NOTHING",
            [company_id, *worth.values()],
        )


def latest(conn: Connection) -> dict:
    """Each company's latest valuation, by company id."""
    return {r["company_id"]: r for r in _rows(
        conn, "SELECT DISTINCT ON (company_id) * FROM company_valuations ORDER BY company_id, period DESC")}
