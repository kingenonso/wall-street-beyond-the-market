"""Stage 9, Part B: options and futures, dealt with the market makers' desk.

What is offered, listed at every quarter's close to run to the end of this quarter and the next:
  * calls and puts on the 50 largest shares (the BSX 50's members), on 100 shares each, at 90%, 100% and 110%
    of the price when listed; and on the BSX 50 itself (₦100 a point), at five strikes;
  * futures on the BSX 50, on oil (ten barrels, in naira at the day's exchange rate), on the naira ($1,000), and on
    the indices of farm produce, metals and building materials (₦10,000 a point).

All are European and settled in cash at their quarter's close. The market makers (the pension funds' desk) always
quote two prices: options from the Black-Scholes model, with each share's own swing and today's interest rate;
futures from today's value carried to the end of the quarter. Buying an option costs its price; writing (selling)
one brings in its price and needs margin: 20% of the underlying value plus the option's own value. A futures
position holds 15% of its value as margin and is settled every night at the Closing Bell: gains are added to its
margin and losses taken from it. Below the maintenance level a margin call; not met by the next bell, the position
is closed by force. Every naira moves through the ledger.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta

from psycopg import Connection
from psycopg.rows import dict_row

from simulation import clock, exchange, ledger, risk
from simulation import world_data as data
from simulation.money import BPS

DESK = ledger.INVESTORS_INSTITUTIONS
MARGIN = "derivatives:margin"
INDEX = "BSX50"
FUTURES = ("BSX50", "OIL", "NAIRA", "FARM", "METALS", "MATERIALS")
COMMODITY_COLUMN = {"FARM": "agriculture_bps", "METALS": "metals_bps", "MATERIALS": "materials_bps"}
NAMES = {"BSX50": "the BSX 50", "OIL": "oil", "NAIRA": "the naira (dollars)", "FARM": "farm produce", "METALS": "metals",
         "MATERIALS": "building materials"}


class DerivativesError(Exception):
    pass


def _rows(conn: Connection, sql: str, params=()) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def _one(conn: Connection, sql: str, params=()) -> dict | None:
    rows = _rows(conn, sql, params)
    return rows[0] if rows else None


def money(kobo: int) -> str:
    return f"₦{kobo / 100:,.0f}"


def _margin_account(conn: Connection):
    if _one(conn, "SELECT 1 FROM ledger_accounts WHERE code = %s", (MARGIN,)) is None:
        ledger.create_account(conn, kind="escrow", name="The exchange: margin held for options and futures", code=MARGIN)
    return ledger.account_id(conn, MARGIN)


def _state(conn: Connection, now: datetime) -> dict:
    from simulation import careers
    return careers.world_now(conn, now)


def policy_rate(conn: Connection) -> int:
    row = _one(conn, "SELECT next_policy_rate_bps FROM economy_results ORDER BY period DESC LIMIT 1")
    return row["next_policy_rate_bps"] if row else data.NEUTRAL_RATE_BPS


# ---------------------------------------------------------------------------
# Prices of what the contracts are on
# ---------------------------------------------------------------------------

def index_now(conn: Connection, now: datetime) -> int:
    from simulation import marketview
    day, _ = exchange.session_of(now)
    return marketview.index_level(marketview._shares(conn, day), marketview.index_base(conn))


def _abroad(conn: Connection) -> dict:
    row = _one(conn, "SELECT oil_cents, fx FROM abroad_results ORDER BY period DESC LIMIT 1")
    return row or {"oil_cents": data.OIL_START_CENTS, "fx": data.FX_START}


def spot(conn: Connection, series: dict, now: datetime) -> int:
    """Today's level of what a contract is on, in its own unit."""
    u = series["underlying"]
    if series.get("company_id"):
        row = _one(conn, "SELECT coalesce(last_price, reference_price) AS p FROM market_instruments WHERE company_id = %s", (series["company_id"],))
        return row["p"] if row else 0
    if u == INDEX:
        return index_now(conn, now)
    if u == "OIL":
        return _abroad(conn)["oil_cents"]
    if u == "NAIRA":
        return _abroad(conn)["fx"]
    row = _one(conn, f"SELECT {COMMODITY_COLUMN[u]} AS v FROM economy_results ORDER BY period DESC LIMIT 1")
    return row["v"] if row else BPS


def value_of(conn: Connection, series: dict, level: int) -> int:
    """What one contract is on, in kobo, at a given level of its underlying."""
    u = series["underlying"]
    if series.get("company_id"):
        return level * data.OPTION_SHARES_PER_CONTRACT
    if u == INDEX:
        return level * data.INDEX_KOBO_PER_POINT // 100
    if u == "OIL":
        return level * _abroad(conn)["fx"] * data.OIL_BARRELS_PER_CONTRACT // 100
    if u == "NAIRA":
        return level * data.NAIRA_DOLLARS_PER_CONTRACT
    return level * data.COMMODITY_KOBO_PER_POINT // 100


def multiplier(series: dict) -> int:
    """Kobo per unit of the underlying, for an option's payoff."""
    return data.OPTION_SHARES_PER_CONTRACT if series.get("company_id") else data.INDEX_KOBO_PER_POINT // 100


# ---------------------------------------------------------------------------
# The market makers' prices
# ---------------------------------------------------------------------------

def expiry_moment(conn: Connection, period: int) -> datetime:
    w = _one(conn, "SELECT world_start, weeks_ahead FROM world_state")
    return clock.effective_start(w["world_start"], w["weeks_ahead"]) + timedelta(days=clock.REAL_DAYS_PER_QUARTER * period)


def years_left(conn: Connection, series: dict, now: datetime) -> float:
    """Time to settlement, in game years (a game year is 28 real days)."""
    left = (expiry_moment(conn, series["expiry_period"]) - now).total_seconds()
    return max(left / (data.GAME_YEAR_REAL_DAYS * 86_400), 0.0)


def volatility(conn: Connection, series: dict) -> float:
    if series.get("company_id"):
        found = risk.share_risk(conn).get(series["company_id"])
        vol = found["volatility_bps"] if found else data.OPTION_LEAST_VOLATILITY_BPS
        return max(vol, data.OPTION_LEAST_VOLATILITY_BPS) / BPS
    moves = list(risk.returns(risk.index_closes(conn)).values())
    if len(moves) >= risk.LEAST_SESSIONS:
        mean = sum(moves) / len(moves)
        daily = math.sqrt(sum((m - mean) ** 2 for m in moves) / (len(moves) - 1))
        return max(daily * math.sqrt(risk.YEAR_SESSIONS), data.OPTION_LEAST_VOLATILITY_BPS / BPS)
    return data.INDEX_VOLATILITY_BPS / BPS


def _cdf(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def black_scholes(kind: str, s: float, k: float, t: float, sigma: float, r: float) -> float:
    """An option's value per unit of the underlying (European)."""
    if t <= 0 or sigma <= 0 or s <= 0 or k <= 0:
        return max(s - k, 0.0) if kind == "call" else max(k - s, 0.0)
    d1 = (math.log(s / k) + (r + sigma * sigma / 2) * t) / (sigma * math.sqrt(t))
    d2 = d1 - sigma * math.sqrt(t)
    if kind == "call":
        return s * _cdf(d1) - k * math.exp(-r * t) * _cdf(d2)
    return k * math.exp(-r * t) * _cdf(-d2) - s * _cdf(-d1)


def fair(conn: Connection, series: dict, now: datetime, level: int | None = None) -> int:
    """The market makers' own price for one contract, in kobo."""
    level = spot(conn, series, now) if level is None else level
    t = years_left(conn, series, now)
    r = policy_rate(conn) / BPS
    if series["kind"] == "future":
        carry = r - data.WORLD_RATE_BPS / BPS if series["underlying"] == "NAIRA" else r
        return round(value_of(conn, series, level) * (1 + carry * t))
    per_unit = black_scholes(series["kind"], level, series["strike"], t, volatility(conn, series), r)
    return round(per_unit * multiplier(series))


def quote(conn: Connection, series: dict, now: datetime) -> dict:
    price = fair(conn, series, now)
    if series["kind"] == "future":
        half = max(price * data.FUTURE_SPREAD_BPS // BPS, 1)
    else:
        half = max(price * data.DESK_SPREAD_BPS // BPS, data.DESK_LEAST_SPREAD_KOBO)
    return {"fair": price, "bid": max(price - half, 0), "ask": price + half}


# ---------------------------------------------------------------------------
# Listing
# ---------------------------------------------------------------------------

def _index_members(conn: Connection) -> list[dict]:
    return _rows(conn, """
        SELECT c.id, c.ticker, coalesce(m.last_price, m.reference_price) AS price,
               coalesce(m.last_price, m.reference_price) * (SELECT r.shares_in_issue FROM company_results r WHERE r.company_id = c.id
                                                            ORDER BY r.period DESC LIMIT 1) AS mv
        FROM market_instruments m JOIN companies c ON c.id = m.company_id WHERE c.status = 'trading'
        ORDER BY mv DESC NULLS LAST, c.ticker LIMIT 50""")


def _strike(level: int, bps: int) -> int:
    raw = level * bps // BPS
    step = 10 ** max(len(str(max(raw, 1))) - 3, 0)          # three significant figures
    return max(round(raw / step) * step, 1)


def list_series(conn: Connection, period: int, now: datetime) -> int:
    """Make sure options and futures run to the close of the quarter now running and the one after. Returns how many were added."""
    added = 0
    current = period + 1                                      # the quarter now running (period has just closed, or is the last closed)
    for expiry in range(current, current + data.OPTION_EXPIRIES):
        if _one(conn, "SELECT 1 FROM derivative_series WHERE expiry_period = %s LIMIT 1", (expiry,)):
            continue
        for u in FUTURES:
            added += _add(conn, "future", u, None, None, expiry, period)
        level = index_now(conn, now)
        for bps in data.INDEX_OPTION_STRIKES_BPS:
            for kind in ("call", "put"):
                added += _add(conn, kind, INDEX, None, _strike(level, bps), expiry, period)
        for share in _index_members(conn):
            for bps in data.OPTION_STRIKES_BPS:
                for kind in ("call", "put"):
                    added += _add(conn, kind, share["ticker"], share["id"], _strike(share["price"], bps), expiry, period)
    return added


def _add(conn: Connection, kind: str, underlying: str, company_id, strike, expiry: int, listed: int) -> int:
    row = _one(conn, "INSERT INTO derivative_series (kind, underlying, company_id, strike, expiry_period, listed_period)"
                     " VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING RETURNING id",
               (kind, underlying, company_id, strike, expiry, listed))
    return 1 if row else 0


def ensure(conn: Connection, now: datetime) -> None:
    """A world (or a quarter) without its series gets them now."""
    w = _one(conn, "SELECT last_closed_period FROM world_state")
    if w is None or _one(conn, "SELECT to_regclass('market_instruments') IS NOT NULL AS ok")["ok"] is not True:
        return
    if _one(conn, "SELECT 1 FROM market_instruments LIMIT 1") is None:
        return
    with conn.transaction():
        conn.execute("SELECT pg_advisory_xact_lock(hashtext('derivatives:listing'))")
        list_series(conn, w["last_closed_period"], now)


# ---------------------------------------------------------------------------
# Trading with the desk
# ---------------------------------------------------------------------------

def _series(conn: Connection, series_id: int, *, lock: bool = False) -> dict:
    s = _one(conn, "SELECT * FROM derivative_series WHERE id = %s" + (" FOR UPDATE" if lock else ""), (series_id,))
    if s is None:
        raise DerivativesError("There is no such contract.")
    return s


def _desk_open(now: datetime) -> None:
    _, state = exchange.session_of(now)
    if state is not clock.MarketState.OPEN:
        raise DerivativesError("The options and futures desk deals while the market is open (12:00 to 22:00, Lagos time).")


def writer_margin(conn: Connection, series: dict, now: datetime, level: int | None = None) -> int:
    """What writing one option needs held: 20% of the underlying value, plus the option's own value."""
    level = spot(conn, series, now) if level is None else level
    return value_of(conn, series, level) * data.WRITER_MARGIN_BPS // BPS + fair(conn, series, now, level)


def open_position(conn: Connection, account, series_id: int, side: str, contracts: int, now: datetime, *, player_id=None,
                  purpose: str | None = None) -> dict:
    with conn.transaction():
        _desk_open(now)
        state = _state(conn, now)
        conn.execute("SELECT pg_advisory_xact_lock(hashtext('borrower:' || %s::text))", (str(account),))
        s = _series(conn, series_id)
        if s["status"] != "open" or s["expiry_period"] < state["period"]:
            raise DerivativesError("That contract has settled.")
        if side not in ("long", "short"):
            raise DerivativesError("Buy or sell.")
        if not isinstance(contracts, int) or isinstance(contracts, bool) or contracts <= 0:
            raise DerivativesError("Name how many contracts.")
        held = _one(conn, "SELECT coalesce(sum(contracts), 0)::bigint AS n FROM derivative_positions WHERE account = %s AND series_id = %s"
                          " AND status = 'open'", (account, series_id))["n"]
        if held + contracts > data.MOST_CONTRACTS_A_SERIES:
            raise DerivativesError(f"At most {data.MOST_CONTRACTS_A_SERIES:,} contracts of one kind.")
        q = quote(conn, s, now)
        desk = ledger.account_id(conn, DESK)
        margin_acct = _margin_account(conn)
        price = q["ask"] if side == "long" else q["bid"]
        if s["kind"] != "future" and price <= 0:
            raise DerivativesError("The market makers will not deal in an option worth nothing.")
        margin = 0
        label = describe(s)
        try:
            if s["kind"] == "future":
                margin = value_of(conn, s, spot(conn, s, now)) * data.FUTURE_MARGIN_BPS // BPS * contracts
                ledger.transfer(conn, payer=account, receiver=margin_acct, amount=margin, kind="derivative_margin",
                                memo=f"Margin for {contracts:,} {label}", period=state["period"])
            elif side == "long":
                ledger.transfer(conn, payer=account, receiver=desk, amount=price * contracts, kind="option_premium",
                                memo=f"Bought {contracts:,} {label}", period=state["period"])
            else:
                margin = writer_margin(conn, s, now) * contracts
                ledger.transfer(conn, payer=desk, receiver=account, amount=price * contracts, kind="option_premium",
                                memo=f"Wrote {contracts:,} {label}", period=state["period"])
                ledger.transfer(conn, payer=account, receiver=margin_acct, amount=margin, kind="derivative_margin",
                                memo=f"Margin for writing {contracts:,} {label}", period=state["period"])
        except ledger.InsufficientFunds:
            need = margin if margin else price * contracts
            raise DerivativesError(f"That needs {money(need)} of cash.") from None
        row = _one(conn, "INSERT INTO derivative_positions (account, series_id, side, contracts, entry_price, mark, margin, purpose, opened_by,"
                         " opened_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
                   (account, series_id, side, contracts, price, price, margin, purpose, player_id, now))
        return {"position_id": row["id"], "price": price, "margin": margin, "contracts": contracts}


def _position(conn: Connection, account, position_id: int) -> dict:
    p = _one(conn, "SELECT p.*, s.kind, s.underlying, s.company_id, s.strike, s.expiry_period FROM derivative_positions p"
                   " JOIN derivative_series s ON s.id = p.series_id WHERE p.id = %s AND p.account = %s AND p.status = 'open'"
                   " FOR UPDATE OF p", (position_id, account))
    if p is None:
        raise DerivativesError("There is no such open position of yours.")
    return p


def close_position(conn: Connection, account, position_id: int, now: datetime) -> dict:
    """Close with the desk at its price: a bought option sold back, a written one bought back, a future closed."""
    with conn.transaction():
        _desk_open(now)
        state = _state(conn, now)
        p = _position(conn, account, position_id)
        q = quote(conn, p, now)
        exit_price = q["bid"] if p["side"] == "long" else q["ask"]
        result = _finish(conn, p, exit_price, state["period"], "closed", now)
        return {"price": exit_price, "result": result}


def _finish(conn: Connection, p: dict, exit_price: int, period: int, status: str, now: datetime) -> int:
    """Pay out a position at a price and hand back its margin. Returns what it made or lost in all."""
    desk = ledger.account_id(conn, DESK)
    margin_acct = _margin_account(conn)
    label = describe(p)
    n = p["contracts"]
    margin = p["margin"]
    if p["kind"] == "future":
        gain = (exit_price - p["mark"]) * n * (1 if p["side"] == "long" else -1)
        margin = _settle_variation(conn, p, gain, period, f"{label}: the last settlement")
        if margin:
            ledger.transfer(conn, payer=margin_acct, receiver=p["account"], amount=margin, kind="derivative_margin_release",
                            memo=f"Margin handed back: {label}", period=period)
        result = (exit_price - p["entry_price"]) * n * (1 if p["side"] == "long" else -1)
    elif p["side"] == "long":
        if exit_price:
            ledger.pay_up_to(conn, payer=desk, receiver=p["account"], wanted=exit_price * n, kind="option_premium" if status == "closed" else "option_settlement",
                             memo=f"{label}: {'sold back' if status == 'closed' else 'settled'}", period=period)
        result = (exit_price - p["entry_price"]) * n
    else:
        owed = exit_price * n
        from_margin = min(owed, margin)
        if from_margin:
            ledger.transfer(conn, payer=margin_acct, receiver=desk, amount=from_margin, kind="option_premium" if status == "closed" else "option_settlement",
                            memo=f"{label}: {'bought back' if status == 'closed' else 'settled'}", period=period)
        if owed > from_margin:
            ledger.pay_up_to(conn, payer=p["account"], receiver=desk, wanted=owed - from_margin, kind="option_settlement",
                             memo=f"{label}: the rest", period=period)
        left = margin - from_margin
        if left:
            ledger.transfer(conn, payer=margin_acct, receiver=p["account"], amount=left, kind="derivative_margin_release",
                            memo=f"Margin handed back: {label}", period=period)
        result = (p["entry_price"] - exit_price) * n
    conn.execute("UPDATE derivative_positions SET status = %s, margin = 0, mark = %s, result = %s, closed_at = %s, call_since = NULL WHERE id = %s",
                 (status, exit_price, result, now, p["id"]))
    if p.get("purpose"):
        _score_hedge(conn, p, result, now)
    return result


def _settle_variation(conn: Connection, p: dict, gain: int, period: int, why: str) -> int:
    """Move a future's gain into its margin (from the desk) or its loss out (to the desk). Returns the margin left."""
    desk = ledger.account_id(conn, DESK)
    margin_acct = _margin_account(conn)
    margin = p["margin"]
    if gain > 0:
        got = ledger.pay_up_to(conn, payer=desk, receiver=margin_acct, wanted=gain, kind="variation_margin", memo=why, period=period)
        margin += got
    elif gain < 0:
        loss = -gain
        from_margin = min(loss, margin)
        if from_margin:
            ledger.transfer(conn, payer=margin_acct, receiver=desk, amount=from_margin, kind="variation_margin", memo=why, period=period)
        margin -= from_margin
        if loss > from_margin:
            ledger.pay_up_to(conn, payer=p["account"], receiver=desk, wanted=loss - from_margin, kind="variation_margin",
                             memo=f"{why}: beyond the margin", period=period)
    conn.execute("UPDATE derivative_positions SET margin = %s WHERE id = %s", (margin, p["id"]))
    p["margin"] = margin
    return margin


def add_margin(conn: Connection, account, position_id: int, amount: int, now: datetime) -> dict:
    with conn.transaction():
        state = _state(conn, now)
        p = _position(conn, account, position_id)
        if not isinstance(amount, int) or isinstance(amount, bool) or amount <= 0:
            raise DerivativesError("Name an amount.")
        try:
            ledger.transfer(conn, payer=account, receiver=_margin_account(conn), amount=amount, kind="derivative_margin",
                            memo=f"More margin: {describe(p)}", period=state["period"])
        except ledger.InsufficientFunds:
            raise DerivativesError("There is not the cash.") from None
        conn.execute("UPDATE derivative_positions SET margin = margin + %s, call_since = NULL WHERE id = %s", (amount, p["id"]))
        return {"margin": p["margin"] + amount}


# ---------------------------------------------------------------------------
# Every Closing Bell, and each quarter's close
# ---------------------------------------------------------------------------

def at_bell(conn: Connection, now: datetime, ended) -> dict:
    """Futures are settled to the night's price; margin calls; positions not made good are closed by force."""
    if _one(conn, "SELECT to_regclass('derivative_positions') IS NOT NULL AS ok")["ok"] is not True:
        return {}
    period = _state(conn, now)["period"]
    done = {"settled": 0, "calls": 0, "closed": 0}
    for p in _rows(conn, "SELECT p.*, s.kind, s.underlying, s.company_id, s.strike, s.expiry_period FROM derivative_positions p"
                         " JOIN derivative_series s ON s.id = p.series_id WHERE p.status = 'open' AND (s.kind = 'future' OR p.side = 'short')"
                         " ORDER BY p.id"):
        with conn.transaction():
            p = {**p, **_one(conn, "SELECT margin, mark, call_since, status FROM derivative_positions WHERE id = %s FOR UPDATE", (p["id"],))}
            if p["status"] != "open":
                continue
            level = spot(conn, p, now)
            if p["kind"] == "future":
                price = fair(conn, p, now, level)
                gain = (price - p["mark"]) * p["contracts"] * (1 if p["side"] == "long" else -1)
                _settle_variation(conn, p, gain, period, f"{describe(p)}: tonight's settlement")
                conn.execute("UPDATE derivative_positions SET mark = %s WHERE id = %s", (price, p["id"]))
                p["mark"] = price
                done["settled"] += 1
                needed = value_of(conn, p, level) * data.FUTURE_MAINTENANCE_BPS // BPS * p["contracts"]
            else:
                needed = writer_margin(conn, p, now, level) * p["contracts"] * data.WRITER_CALL_SHARE_BPS // BPS
            unmet = p["call_since"] is not None and p["call_since"] < ended
            if p["margin"] < needed and (unmet or p["margin"] == 0):
                q = quote(conn, p, now)
                exit_price = p["mark"] if p["kind"] == "future" else q["ask"]
                _finish(conn, p, exit_price, period, "closed_by_force", now)
                _note(conn, p, f"Margin call not met: your {describe(p)} was closed at {money(exit_price)} a contract.", now)
                done["closed"] += 1
            elif p["margin"] < needed:
                if p["call_since"] is None:
                    conn.execute("UPDATE derivative_positions SET call_since = %s WHERE id = %s", (ended, p["id"]))
                    _note(conn, p, f"Margin call: your {describe(p)} needs {money(needed - p['margin'])} more margin by the next "
                                   f"Closing Bell, or it will be closed.", now)
                    done["calls"] += 1
            elif p["call_since"] is not None:
                conn.execute("UPDATE derivative_positions SET call_since = NULL WHERE id = %s", (p["id"],))
    return done


def _note(conn: Connection, p: dict, words: str, now: datetime) -> None:
    conn.execute("INSERT INTO lending_events (account, kind, words, at) VALUES (%s, 'derivatives', %s, %s)", (p["account"], words, now))


def close(conn: Connection, period: int, now: datetime) -> dict:
    """At the quarter's close: every contract that runs to it is settled in cash; new ones are listed."""
    if _one(conn, "SELECT to_regclass('derivative_series') IS NOT NULL AS ok")["ok"] is not True:
        return {}
    settled = 0
    for s in _rows(conn, "SELECT * FROM derivative_series WHERE status = 'open' AND expiry_period <= %s ORDER BY id", (period,)):
        level = spot(conn, s, now)
        for p in _rows(conn, "SELECT p.*, s.kind, s.underlying, s.company_id, s.strike, s.expiry_period FROM derivative_positions p"
                             " JOIN derivative_series s ON s.id = p.series_id WHERE p.series_id = %s AND p.status = 'open' ORDER BY p.id",
                       (s["id"],)):
            if s["kind"] == "future":
                final = value_of(conn, s, level)
            else:
                intrinsic = (level - s["strike"]) if s["kind"] == "call" else (s["strike"] - level)
                final = max(intrinsic, 0) * multiplier(s)
            _finish(conn, p, final, period, "expired", now)
            settled += 1
        conn.execute("UPDATE derivative_series SET status = 'settled', settled_spot = %s WHERE id = %s", (level, s["id"]))
    added = list_series(conn, period, now)
    return {"settled": settled, "listed": added}


def check_books(conn: Connection) -> list[str]:
    if _one(conn, "SELECT to_regclass('derivative_positions') IS NOT NULL AS ok")["ok"] is not True:
        return []
    row = _one(conn, "SELECT id FROM ledger_accounts WHERE code = %s", (MARGIN,))
    if row is None:
        return []
    held = ledger.balance(conn, row["id"])
    recorded = _one(conn, "SELECT coalesce(sum(margin), 0)::bigint AS m FROM derivative_positions WHERE status = 'open'")["m"]
    return [] if held == recorded else [f"Options and futures margin: {held} held against {recorded} recorded."]


# ---------------------------------------------------------------------------
# Hedges: an empire's protection, scored when it ends
# ---------------------------------------------------------------------------

def _score_hedge(conn: Connection, p: dict, result: int, now: datetime) -> None:
    empire = _one(conn, "SELECT id FROM empires WHERE account_id = %s", (p["account"],))
    if empire is None:
        return
    from simulation import empires
    words = (f"The hedge \"{p['purpose']}\" ({describe(p)}) ended: it "
             + (f"paid {money(result)} more than it cost." if result > 0 else f"cost {money(-result)} net." if result < 0 else "cost nothing net."))
    empires._log(conn, empire["id"], words, now)


# ---------------------------------------------------------------------------
# What players see
# ---------------------------------------------------------------------------

def describe(s: dict) -> str:
    what = s["underlying"] if s.get("company_id") else NAMES.get(s["underlying"], s["underlying"])
    expiry = clock.period_label(s["expiry_period"])
    if s["kind"] == "future":
        return f"{what} future to {expiry}"
    strike = (f"₦{s['strike'] / 100:,.2f}" if s.get("company_id") else f"{s['strike'] / 100:,.0f}")
    return f"{what} {s['kind']} at {strike}, to {expiry}"


def board(conn: Connection, now: datetime, underlying: str | None = None) -> dict:
    """The option chains and futures on offer, with the desk's two prices. Public."""
    ensure(conn, now)
    state = _state(conn, now)
    rows = _rows(conn, "SELECT * FROM derivative_series WHERE status = 'open' AND expiry_period >= %s"
                       + (" AND underlying = %s" if underlying else "") + " ORDER BY expiry_period, underlying, kind, strike",
                 (state["period"], underlying) if underlying else (state["period"],))
    levels: dict = {}
    out = []
    for s in rows:
        key = (s["underlying"], s["company_id"])
        if key not in levels:
            levels[key] = spot(conn, s, now)
        q = quote(conn, s, now)
        out.append({"id": s["id"], "kind": s["kind"], "underlying": s["underlying"], "strike": s["strike"], "expiry_period": s["expiry_period"],
                    "expiry": clock.period_label(s["expiry_period"]), "name": describe(s), "spot": levels[key],
                    "value": value_of(conn, s, levels[key]), "bid": q["bid"], "ask": q["ask"],
                    "margin_long": value_of(conn, s, levels[key]) * data.FUTURE_MARGIN_BPS // BPS if s["kind"] == "future" else 0,
                    "margin_short": (value_of(conn, s, levels[key]) * data.FUTURE_MARGIN_BPS // BPS if s["kind"] == "future"
                                     else writer_margin(conn, s, now, levels[key]))})
    underlyings = sorted({s["underlying"] for s in _rows(conn, "SELECT DISTINCT underlying FROM derivative_series WHERE status = 'open'")})
    _, market = exchange.session_of(now)
    return {"series": out, "underlyings": underlyings, "open": market is clock.MarketState.OPEN}


def positions_of(conn: Connection, account, now: datetime) -> list[dict]:
    out = []
    for p in _rows(conn, "SELECT p.*, s.kind, s.underlying, s.company_id, s.strike, s.expiry_period FROM derivative_positions p"
                         " JOIN derivative_series s ON s.id = p.series_id WHERE p.account = %s AND p.status = 'open' ORDER BY p.id", (account,)):
        q = quote(conn, p, now)
        now_price = q["bid"] if p["side"] == "long" else q["ask"]
        if p["kind"] == "future":
            gain = (q["fair"] - p["entry_price"]) * p["contracts"] * (1 if p["side"] == "long" else -1)
        elif p["side"] == "long":
            gain = (now_price - p["entry_price"]) * p["contracts"]
        else:
            gain = (p["entry_price"] - now_price) * p["contracts"]
        out.append({"id": p["id"], "name": describe(p), "kind": p["kind"], "side": p["side"], "contracts": p["contracts"],
                    "entry_price": p["entry_price"], "price": now_price, "margin": p["margin"], "gain": gain,
                    "margin_call": p["call_since"] is not None, "purpose": p["purpose"], "expiry": clock.period_label(p["expiry_period"])})
    return out


def held_value(conn: Connection, account, now: datetime) -> int:
    """What the account's options and futures are worth to it now (margin included)."""
    total = 0
    for p in _rows(conn, "SELECT p.*, s.kind, s.underlying, s.company_id, s.strike, s.expiry_period FROM derivative_positions p"
                         " JOIN derivative_series s ON s.id = p.series_id WHERE p.account = %s AND p.status = 'open'", (account,)):
        total += p["margin"]
        if p["kind"] == "future":
            total += (fair(conn, p, now) - p["mark"]) * p["contracts"] * (1 if p["side"] == "long" else -1)
        elif p["side"] == "long":
            total += fair(conn, p, now) * p["contracts"]
        else:
            total -= fair(conn, p, now) * p["contracts"]
    return total


def _players_derivatives(conn: Connection) -> dict:
    out = {}
    if _one(conn, "SELECT to_regclass('derivative_positions') IS NOT NULL AS ok")["ok"] is not True:
        return out
    from datetime import timezone
    now = datetime.now(timezone.utc)
    for r in _rows(conn, "SELECT DISTINCT p.account FROM derivative_positions p JOIN ledger_accounts a ON a.id = p.account"
                         " WHERE p.status = 'open' AND a.kind = 'player'"):
        out[r["account"]] = (0, held_value(conn, r["account"], now))
    return out


def _register() -> None:
    from simulation import marketview
    if _players_derivatives not in marketview._OTHER_HOLDINGS:
        marketview._OTHER_HOLDINGS.append(_players_derivatives)


_register()
