"""Stage 9: "What could happen?" (the Monte Carlo engine).

A player tests what they hold (their portfolio, their empire's, one share or one building) against
1,000 possible futures, a quarter or a game year ahead. Each future is drawn from PUBLIC assumptions
only: how each share has swung over its last trading days and how shares have moved together, the
districts' price records, and today's interest rates. The world's own secret randomness is never
used, so the tool shows what the past suggests, not what will happen.

The answer: a fan of outcomes day by day (the middle, the likely range and the wide range), the chance
of ending below today's value, the worst likely loss in one future out of twenty (value at risk), and,
for a loan against shares, the chance of a margin call. One run a day is free; each further run costs
a small fee paid to the exchange.
"""

from __future__ import annotations

import hashlib
import math
from datetime import datetime

import numpy as np
from psycopg import Connection
from psycopg.rows import dict_row

from simulation import exchange, ledger, risk
from simulation import world_data as data
from simulation.money import BPS, naira

DF = 5                                         # fat tails: a Student's t with five degrees of freedom
BOND_DAILY = 0.003                             # bonds and bills: a small daily swing
PROPERTY_DAILY_LEAST = 0.004


class MonteCarloError(Exception):
    pass


def _rows(conn: Connection, sql: str, params=()) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def _one(conn: Connection, sql: str, params=()) -> dict | None:
    rows = _rows(conn, sql, params)
    return rows[0] if rows else None


def _quotes(conn: Connection) -> dict:
    return {r["company_id"]: r for r in _rows(conn, """
        SELECT m.company_id, c.ticker, c.name, coalesce(m.last_price, m.reference_price) AS price
        FROM market_instruments m JOIN companies c ON c.id = m.company_id WHERE c.status = 'trading'""")}


def _property_daily(conn: Connection) -> float:
    """A building's daily swing, from the districts' quarterly price records (a quarter is seven trading days)."""
    rows = _rows(conn, "SELECT district_id, period, price_bps FROM district_results ORDER BY district_id, period") if _one(
        conn, "SELECT to_regclass('district_results') IS NOT NULL AS ok")["ok"] else []
    moves, last = [], {}
    for r in rows:
        before = last.get(r["district_id"])
        if before and before > 0 and r["period"] > 0:
            moves.append(r["price_bps"] / before - 1)
        last[r["district_id"]] = r["price_bps"]
    if len(moves) < 4:
        return PROPERTY_DAILY_LEAST
    mean = sum(moves) / len(moves)
    quarterly = math.sqrt(sum((m - mean) ** 2 for m in moves) / (len(moves) - 1))
    return max(quarterly / math.sqrt(7), PROPERTY_DAILY_LEAST)


def _covariance(conn: Connection, companies: list) -> np.ndarray:
    """Daily covariance of the shares' moves, from their own history, steadied towards the usual figures."""
    history = risk.closes(conn)
    moves = {c: risk.returns(history.get(c, [])) for c in companies}
    n = len(companies)
    spread = np.zeros(n)
    for i, c in enumerate(companies):
        values = list(moves[c].values())
        spread[i] = (float(np.std(values, ddof=1)) if len(values) >= risk.LEAST_SESSIONS else risk.USUAL_DAILY) or risk.USUAL_DAILY
    corr = np.full((n, n), risk.USUAL_CORRELATION)
    np.fill_diagonal(corr, 1.0)
    for i in range(n):
        for j in range(i + 1, n):
            common = [d for d in moves[companies[i]] if d in moves[companies[j]]]
            if len(common) >= risk.LEAST_SESSIONS:
                a = np.array([moves[companies[i]][d] for d in common])
                b = np.array([moves[companies[j]][d] for d in common])
                if a.std() > 0 and b.std() > 0:
                    found = float(np.corrcoef(a, b)[0, 1])
                    corr[i, j] = corr[j, i] = 0.5 * found + 0.5 * risk.USUAL_CORRELATION      # steadied: half the record, half the usual
    # Keep it a proper covariance (no negative variances).
    values, vectors = np.linalg.eigh(corr)
    corr = vectors @ np.diag(np.clip(values, 1e-6, None)) @ vectors.T
    d = np.sqrt(np.diag(corr))
    corr = corr / np.outer(d, d)
    return corr * np.outer(spread, spread)


def positions(conn: Connection, account, now: datetime) -> dict:
    """What an account holds, for the test: shares (less any borrowed), bonds, buildings, cash and debts."""
    from simulation import bonds, lending
    quotes = _quotes(conn)
    shares: dict = {}
    for r in _rows(conn, "SELECT company_id, shares FROM share_owners WHERE account_id = %s AND shares > 0", (account,)):
        if r["company_id"] in quotes:
            shares[r["company_id"]] = shares.get(r["company_id"], 0) + r["shares"]
    for r in _rows(conn, "SELECT company_id, sum(shares)::bigint AS s FROM short_positions WHERE borrower = %s AND status = 'open'"
                         " GROUP BY company_id", (account,)) if _one(conn, "SELECT to_regclass('short_positions') IS NOT NULL AS ok")["ok"] else []:
        if r["company_id"] in quotes:
            shares[r["company_id"]] = shares.get(r["company_id"], 0) - int(r["s"])
    lines = {c: n * quotes[c]["price"] for c, n in shares.items() if n}
    bond_value = sum(b["value"] for b in bonds.holdings_of(conn, account, now))
    building = 0
    if _one(conn, "SELECT to_regclass('property_holdings') IS NOT NULL AS ok")["ok"]:
        from simulation import property as prop
        eq = prop.equity_of(conn, account)
        building = eq["value"]
        mortgage = eq["owed"]
    else:
        mortgage = 0
    cash = ledger.balance(conn, account) + (lending.collateral_held(conn, account) if _one(
        conn, "SELECT to_regclass('player_loans') IS NOT NULL AS ok")["ok"] else 0)
    loans = lending.loans_owed(conn, account) if _one(conn, "SELECT to_regclass('player_loans') IS NOT NULL AS ok")["ok"] else 0
    margin = lending.margin_owed(conn, account) if loans else 0
    return {"shares": lines, "names": {c: quotes[c]["ticker"] for c in lines}, "bonds": bond_value, "property": building,
            "cash": cash, "owed": loans + mortgage, "margin": margin}


def simulate(conn: Connection, holding: dict, days: int, paths: int, rng: np.random.Generator) -> dict:
    """Run the futures. Returns the fan (by day) and the end figures."""
    companies = list(holding["shares"])
    values = np.array([holding["shares"][c] for c in companies], dtype=float)
    start_assets = float(values.sum()) + holding["bonds"] + holding["property"] + holding["cash"]
    start = start_assets - holding["owed"]
    cov = _covariance(conn, companies) if companies else np.zeros((0, 0))
    chol = np.linalg.cholesky(cov + np.eye(len(companies)) * 1e-12) if companies else None
    scale = math.sqrt((DF - 2) / DF)
    prop_daily = _property_daily(conn) if holding["property"] else 0.0
    rate = (_one(conn, "SELECT next_policy_rate_bps FROM economy_results ORDER BY period DESC LIMIT 1") or {"next_policy_rate_bps": 1200})[
        "next_policy_rate_bps"] / BPS
    daily_interest = holding["owed"] * rate / data.GAME_YEAR_REAL_DAYS          # what debts cost each trading day
    share_v = np.tile(values, (paths, 1))
    bond_v = np.full(paths, float(holding["bonds"]))
    prop_v = np.full(paths, float(holding["property"]))
    owed = np.full(paths, float(holding["owed"]))
    fan = []
    margin_hit = np.zeros(paths, dtype=bool)
    for _ in range(days):
        tail = np.sqrt(rng.chisquare(DF, size=paths) / DF)        # one shared draw a day: bad days hit everything at once
        if companies:
            z = rng.standard_normal((paths, len(companies))) @ chol.T
            share_v = share_v * np.exp(z * scale / tail[:, None])
        bond_v = bond_v * np.exp(rng.standard_normal(paths) * BOND_DAILY * scale / tail)
        prop_v = prop_v * np.exp(rng.standard_normal(paths) * prop_daily * scale / tail)
        owed = owed + daily_interest
        total = share_v.sum(axis=1) + bond_v + prop_v + holding["cash"] - owed
        if holding["margin"]:
            held = share_v.clip(min=0).sum(axis=1) + bond_v + holding["cash"]
            margin_hit |= holding["margin"] >= held * data.MARGIN_CALL_BPS / BPS
        fan.append([float(np.percentile(total, p)) for p in (5, 25, 50, 75, 95)])
    end = total
    p5 = float(np.percentile(end, 5))
    return {
        "start": round(start), "median": round(float(np.median(end))), "best_likely": round(float(np.percentile(end, 95))),
        "worst_likely": round(p5), "value_at_risk": round(max(start - p5, 0)),
        "chance_of_loss_bps": round(float((end < start).mean()) * BPS),
        "chance_of_margin_call_bps": round(float(margin_hit.mean()) * BPS) if holding["margin"] else None,
        "fan": [{"day": n + 1, "p5": round(f[0]), "p25": round(f[1]), "p50": round(f[2]), "p75": round(f[3]), "p95": round(f[4])}
                for n, f in enumerate(fan)],
    }


def _seed(*parts) -> int:
    return int.from_bytes(hashlib.sha256(":".join(str(p) for p in parts).encode()).digest()[:8], "big")


def run(conn: Connection, player_id, what: str, now: datetime, *, horizon: str = "quarter", ticker: str | None = None,
        property_id: int | None = None) -> dict:
    """Run "What could happen?" for a player. Charges the fee after the free run of the day."""
    from simulation import empires
    if horizon not in data.MONTE_CARLO_HORIZONS:
        raise MonteCarloError("Choose a quarter or a year ahead.")
    if what not in ("portfolio", "empire", "share", "property"):
        raise MonteCarloError("Choose what to test.")
    account = ledger.player_account_id(conn, player_id)
    if what == "portfolio":
        holding = positions(conn, account, now)
        title = "What you hold"
    elif what == "empire":
        seat = empires.seat_of(conn, player_id)
        if seat is None or seat.get("empire_status") != "active":
            raise MonteCarloError("You hold no seat in an open empire.")
        holding = positions(conn, seat["account_id"], now)
        title = f"{seat['empire_name']}: what it holds"
    elif what == "share":
        q = _one(conn, "SELECT c.id, c.ticker, coalesce(m.last_price, m.reference_price) AS price FROM companies c"
                       " JOIN market_instruments m ON m.company_id = c.id WHERE c.ticker = %s", (ticker or "",))
        if q is None:
            raise MonteCarloError("There is no such share.")
        holding = {"shares": {q["id"]: naira(1_000_000)}, "names": {q["id"]: q["ticker"]}, "bonds": 0, "property": 0, "cash": 0,
                   "owed": 0, "margin": 0}
        title = f"₦1,000,000 of {q['ticker']}"
    else:
        from simulation import property as prop
        p = _one(conn, "SELECT * FROM properties WHERE id = %s", (property_id,))
        if p is None:
            raise MonteCarloError("There is no such property.")
        worth = prop.value(p, prop.districts(conn)[p["district_id"]], prop.policy_rate(conn))
        holding = {"shares": {}, "names": {}, "bonds": 0, "property": worth, "cash": 0, "owed": 0, "margin": 0}
        title = p["name"]
    if not holding["shares"] and not holding["bonds"] and not holding["property"]:
        raise MonteCarloError("There is nothing here whose value can move: only cash.")
    day, _ = exchange.session_of(now)
    with conn.transaction():
        conn.execute("SELECT 1 FROM players WHERE id = %s FOR UPDATE", (player_id,))
        used = _one(conn, "SELECT count(*) AS n FROM monte_carlo_runs WHERE player_id = %s AND session_date = %s", (player_id, day))["n"]
        fee = 0 if used < data.MONTE_CARLO_FREE_A_DAY else naira(data.MONTE_CARLO_FEE_NAIRA)
        if fee:
            try:
                ledger.transfer(conn, payer=account, receiver=ledger.account_id(conn, exchange.FEES), amount=fee, kind="monte_carlo_fee",
                                memo="\"What could happen?\": a further run today")
            except ledger.InsufficientFunds:
                raise MonteCarloError(f"Today's free run is used. A further run costs ₦{data.MONTE_CARLO_FEE_NAIRA:,}.") from None
        conn.execute("INSERT INTO monte_carlo_runs (player_id, session_date, what, fee, at) VALUES (%s, %s, %s, %s, %s)",
                     (player_id, day, what, fee, now))
    rng = np.random.default_rng(_seed(player_id, now.isoformat(), what, ticker, property_id))
    days = data.MONTE_CARLO_HORIZONS[horizon]
    result = simulate(conn, holding, days, data.MONTE_CARLO_PATHS, rng)
    return {**result, "title": title, "horizon": horizon, "days": days, "paths": data.MONTE_CARLO_PATHS, "fee": fee,
            "free_left": max(data.MONTE_CARLO_FREE_A_DAY - used - 1, 0),
            "assumptions": [
                "Each share swings as much as it has over its last 60 trading days, and moves with the others as it has, "
                "steadied half-way towards the usual (a 2% daily swing, and a little in common).",
                "Bad days come together: one draw a day shakes everything at once, and rare days are far worse than usual.",
                "Bonds and bills swing a little. Buildings swing as the districts' prices have.",
                "Debts cost today's interest rate. Nothing is bought or sold along the way.",
                "Only public figures are used. This shows what the past suggests, not what will happen."]}
