"""Stage 9, Part B and the gap stage: options and futures, cleared by the game's clearing house.

What is offered, listed at every quarter's close to run to the end of this quarter and the next:
  * calls and puts on the 50 largest shares (the BSX 50's members), on 100 shares each, at 90%, 100% and 110%
    of the price when listed; and on the BSX 50 itself (₦100 a point), at five strikes;
  * futures on the BSX 50, on oil (ten barrels, in naira at the day's exchange rate), on the naira (,000), and on
    the indices of farm produce, metals and building materials (₦10,000 a point).

All are European and settled in cash at their quarter's close. Players' orders are matched with each other by the
order-matching engine; the market makers (the pension funds' desk) always stand behind them with two prices (options
from the Black-Scholes model, futures from today's value carried to the quarter's end). A limit order not filled waits
in the book until the Closing Bell. Each contract shows the price of its last matched trade beside its fair value.

The clearing house stands between the two sides of every contract: the two sides always add up to nothing, every
settlement passes through it, and losses beyond a trader's margin are covered by a default fund (a tenth of every
fee), which the trader then owes. Buying an option costs its price; writing one brings in its price and needs margin:
20% of the underlying value plus the option's own value. A futures position holds 15% of its value as margin and is
settled every night. Below the maintenance level a margin call; not met by the next bell, the position is closed by
force. Every naira moves through the ledger.
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
        return share_level(conn, series["company_id"], now)
    if u == INDEX:
        return index_now(conn, now)
    if u == "OIL":
        return _abroad(conn)["oil_cents"]
    if u == "NAIRA":
        return _abroad(conn)["fx"]
    row = _one(conn, f"SELECT {COMMODITY_COLUMN[u]} AS v FROM economy_results ORDER BY period DESC LIMIT 1")
    return row["v"] if row else BPS


def share_level(conn: Connection, company_id, now: datetime) -> int:
    """A share's level for its options: the volume-weighted price of the latest session's trades (so one small trade
    near the bell cannot move it), or the reference price when nothing traded."""
    row = _one(conn, """
        SELECT (SELECT sum(t.price * t.quantity) / nullif(sum(t.quantity), 0) FROM market_trades t
                WHERE t.company_id = m.company_id AND t.session_date = (SELECT max(session_date) FROM market_trades x
                                                                        WHERE x.company_id = m.company_id AND x.traded_at <= %s))::bigint AS vwap,
               m.reference_price, m.last_price
        FROM market_instruments m WHERE m.company_id = %s""", (now, company_id))
    if row is None:
        return 0
    return row["vwap"] or row["reference_price"] or row["last_price"] or 0


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


_RISK_MEMO: dict = {}


def volatility(conn: Connection, series: dict) -> float:
    if series.get("company_id"):
        table = _RISK_MEMO.get(id(conn))
        found = (table if table is not None else risk.share_risk(conn)).get(series["company_id"])
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


ORDERS = "derivatives:orders"            # cash held for orders waiting in a book
FUND = "clearing:default_fund"            # the clearing house's default fund
MAKER = -1                                # the market makers' standing quote, as an order the engine can match


def _escrow(conn: Connection, code: str, name: str):
    if _one(conn, "SELECT 1 FROM ledger_accounts WHERE code = %s", (code,)) is None:
        ledger.create_account(conn, kind="escrow", name=name, code=code)
    return ledger.account_id(conn, code)


def _orders_account(conn: Connection):
    return _escrow(conn, ORDERS, "The exchange: cash held for options and futures orders")


def fund_account(conn: Connection):
    return _escrow(conn, FUND, "The clearing house's default fund")


def _desk(conn: Connection):
    return ledger.account_id(conn, DESK)


def _fees_account(conn: Connection):
    return _escrow(conn, "exchange:fees", "The exchange: fees")


# ---------------------------------------------------------------------------
# Who may trade what: advanced instruments open by level and by module mastery
# ---------------------------------------------------------------------------

def unlock(conn: Connection, player_id, what: str) -> None:
    """`what` is "options" (buying options) or "advanced" (futures, writing options, swaps)."""
    if player_id is None:
        return
    from simulation import careers, objectives
    player = _one(conn, "SELECT build FROM players WHERE id = %s", (player_id,))
    mine = careers.career(conn, player_id) if player and player["build"] else None
    level = mine["level"] if mine else 0
    if what == "options":
        if level < data.UNLOCK_OPTIONS_LEVEL:
            raise DerivativesError(f"Buying options opens at Level {data.UNLOCK_OPTIONS_LEVEL}.")
        return
    if level < data.UNLOCK_ADVANCED_LEVEL:
        raise DerivativesError(f"Futures, writing options and swaps open at Level {data.UNLOCK_ADVANCED_LEVEL}.")
    module = data.STAGE9_MODULE.get(player["build"])
    if module and not any(m["module"] == module and m["learned"] for m in objectives.mastery(conn, player_id, player["build"])):
        raise DerivativesError(f"Futures, writing options and swaps open once you have learned \"{module}\": pass that work on your own first.")


# ---------------------------------------------------------------------------
# The clearing house: books, matching, and the two sides of every contract
# ---------------------------------------------------------------------------

def series_mark(conn: Connection, s: dict, now: datetime) -> int:
    """A future's settlement price: every open position in the series is marked to it. Set at the first trade, then at
    every Closing Bell."""
    if s.get("mark") is None:
        s["mark"] = fair(conn, s, now)
        conn.execute("UPDATE derivative_series SET mark = %s WHERE id = %s", (s["mark"], s["id"]))
        # (Positions from before the clearing house carry their own marks: bring them all to the series' mark.)
        if _one(conn, "SELECT 1 FROM derivative_positions WHERE series_id = %s AND status = 'open' AND mark <> %s", (s["id"], s["mark"])):
            _settle_series(conn, s, s["mark"], _state(conn, now)["period"], now, "the clearing house's first mark")
    return s["mark"]


def _maker_prices(conn: Connection, s: dict, now: datetime) -> dict:
    q = quote(conn, s, now)
    return {"buy": q["bid"] if q["bid"] > 0 else None, "sell": q["ask"], "fair": q["fair"]}


def _book(conn: Connection, s: dict, side: str, account, now: datetime) -> list[dict]:
    """What an order on `side` can be matched against: players' orders on the other side (never the trader's own),
    and the market makers' standing quote, which waits behind any player's order at the same price."""
    other = "sell" if side == "buy" else "buy"
    rows = _rows(conn, "SELECT id, limit_price, remaining FROM derivative_orders WHERE series_id = %s AND side = %s AND status = 'open'"
                       " AND account <> %s ORDER BY id", (s["id"], other, account))
    book = [{"id": r["id"], "limit_price": r["limit_price"], "remaining": r["remaining"], "seq": r["id"]} for r in rows]
    maker = _maker_prices(conn, s, now)[other]
    if maker:
        book.append({"id": MAKER, "limit_price": maker, "remaining": data.MOST_CONTRACTS_A_SERIES, "seq": data.MAKER_SEQUENCE})
    return book


def _per_contract(conn: Connection, s: dict, side: str, limit: int, now: datetime) -> int:
    """The cash an order holds for each contract while it waits (as if every contract opened a new position)."""
    level = spot(conn, s, now)
    fee = _fee(conn, s, 1, level)
    if s["kind"] == "future":
        mark = series_mark(conn, s, now)
        over = max(limit - mark, 0) if side == "buy" else max(mark - limit, 0)
        return value_of(conn, s, level) * data.FUTURE_MARGIN_BPS // BPS + over + fee
    if side == "buy":
        return limit + fee
    return max(writer_margin(conn, s, now, level) - limit, 0) + fee


def _fee(conn: Connection, s: dict, contracts: int, level: int) -> int:
    return -(-value_of(conn, s, level) * contracts * data.DERIVATIVE_FEE_BPS // BPS)


def trade(conn: Connection, account, series_id: int, side: str, contracts: int, now: datetime, *, limit: int | None = None,
          player_id=None, purpose: str | None = None, forced: bool = False, prefer: int | None = None, company: bool = False) -> dict:
    """Buy or sell contracts. The order meets players' waiting orders and the market makers' quote through the
    order-matching engine; what is left of a limit order waits in the book until the Closing Bell. Buying closes the
    account's own short positions first, selling its long positions; the rest opens new ones."""
    with conn.transaction():
        if not forced and not company:
            _desk_open(now)
        state = _state(conn, now)
        conn.execute("SELECT pg_advisory_xact_lock(hashtext('borrower:' || %s::text))", (str(account),))
        s = _series(conn, series_id, lock=True)
        if s["status"] != "open" or s["expiry_period"] < state["period"]:
            raise DerivativesError("That contract has settled.")
        if s.get("company_id") and _one(conn, "SELECT halted_reason FROM market_instruments WHERE company_id = %s", (s["company_id"],))["halted_reason"]:
            raise DerivativesError("Trading in this company's shares is stopped: the Central Bank closed the bank.")
        if not forced and not company and s.get("company_id"):
            from simulation import exchange as _exchange
            from simulation import newsroom
            try:
                newsroom.check_trade(conn, account, s["company_id"], now)
            except _exchange.ExchangeError as e:
                raise DerivativesError(str(e)) from e
        if side not in ("buy", "sell"):
            raise DerivativesError("Buy or sell.")
        if not isinstance(contracts, int) or isinstance(contracts, bool) or contracts <= 0:
            raise DerivativesError("Name how many contracts.")
        if limit is not None and (not isinstance(limit, int) or isinstance(limit, bool) or limit <= 0):
            raise DerivativesError("A limit is a price in kobo, above nought.")
        closing = _one(conn, "SELECT coalesce(sum(contracts), 0)::bigint AS n FROM derivative_positions WHERE account = %s AND series_id = %s"
                             " AND status = 'open' AND side = %s", (account, series_id, "short" if side == "buy" else "long"))["n"]
        opening = max(contracts - closing, 0)
        if opening and not forced and not company:
            if _one(conn, "SELECT 1 FROM player_loans WHERE borrower = %s AND status = 'default'", (account,)):
                raise DerivativesError("A debt of yours is in default. Nothing new can be opened for you until it is paid.")
            unlock(conn, player_id, "options" if s["kind"] != "future" and side == "buy" else "advanced")
            # (Orders still waiting count too: five waiting orders cannot each pass the limit and then all fill.)
            held = _one(conn, "SELECT coalesce(sum(contracts), 0)::bigint AS n FROM derivative_positions WHERE account = %s AND series_id = %s"
                              " AND status = 'open'", (account, series_id))["n"] \
                + _one(conn, "SELECT coalesce(sum(remaining), 0)::bigint AS n FROM derivative_orders WHERE account = %s AND series_id = %s"
                             " AND status = 'open'", (account, series_id))["n"]
            if held + opening > data.MOST_CONTRACTS_A_SERIES:
                raise DerivativesError(f"At most {data.MOST_CONTRACTS_A_SERIES:,} contracts of one kind.")
        if s["kind"] == "future":
            series_mark(conn, s, now)
        result = {"filled": 0, "value": 0, "position_id": None, "order_id": None, "margin": 0}
        me = {"maker": False, "player_id": player_id, "purpose": purpose, "prefer": prefer, "forced": forced, "company": company}
        while True:
            book = _book(conn, s, side, account, now)
            fills, left = exchange.engine.match(side, limit, contracts - result["filled"], book, 1, 10 ** 15)
            if not fills and limit is None and not result["filled"]:
                raise DerivativesError("Nobody is selling that now." if side == "buy" else "The market makers will not buy an option worth "
                                       "nothing, and nobody else is buying it now.")
            again = False
            for f in fills:
                if f["order_id"] == MAKER:
                    other, other_meta = _desk(conn), {"maker": True}
                    buyer, seller = ((account, me), (other, other_meta)) if side == "buy" else ((other, other_meta), (account, me))
                    done = _fill(conn, s, f["price"], f["quantity"], buyer, seller, state["period"], now)
                else:
                    order = _one(conn, "SELECT * FROM derivative_orders WHERE id = %s FOR UPDATE", (f["order_id"],))
                    other, other_meta = order["account"], {"maker": False, "player_id": order["placed_by"], "purpose": order["purpose"]}
                    buyer, seller = ((account, me), (other, other_meta)) if side == "buy" else ((other, other_meta), (account, me))
                    try:
                        with conn.transaction():
                            _release_order(conn, order, f["quantity"], state["period"])
                            done = _fill(conn, s, f["price"], f["quantity"], buyer, seller, state["period"], now)
                    except DerivativesError as failed:
                        if getattr(failed, "account", None) != other:
                            raise
                        # The waiting order's owner can no longer pay for it at today's prices: it is cancelled (what it
                        # held goes back), and the matching starts again without it.
                        _cancel(conn, order, state["period"], "cancelled")
                        again = True
                        break
                mine = done["buyer"] if side == "buy" else done["seller"]
                result["filled"] += f["quantity"]
                result["value"] += f["price"] * f["quantity"]
                result["position_id"] = mine["position_id"] or result["position_id"]
                result["margin"] += mine["margin"]
            if not again:
                break
        if left and limit is not None and not forced:
            per = _per_contract(conn, s, side, limit, now)
            try:
                ledger.transfer(conn, payer=account, receiver=_orders_account(conn), amount=per * left, kind="derivative_order",
                                memo=f"Held for an order: {left:,} {describe(s)}", period=state["period"])
            except ledger.InsufficientFunds:
                raise DerivativesError(f"That order needs {money(per * left)} of cash held while it waits.") from None
            row = _one(conn, "INSERT INTO derivative_orders (account, series_id, side, limit_price, contracts, remaining, per_contract,"
                             " reserved, placed_by, purpose, at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
                       (account, series_id, side, limit, left, left, per, per * left, player_id, purpose, now))
            result["order_id"] = row["id"]
        result["price"] = result["value"] // result["filled"] if result["filled"] else None
        result["contracts"] = result["filled"]
        result["waiting"] = left if result["order_id"] else 0
        return result


def _release_order(conn: Connection, order: dict, filled: int, period: int) -> None:
    """Hand back the cash an order held for the contracts just filled (the fill then takes what it really needs)."""
    back = order["per_contract"] * filled
    left = order["remaining"] - filled
    if back:
        ledger.transfer(conn, payer=_orders_account(conn), receiver=order["account"], amount=back, kind="derivative_order_release",
                        memo="Cash held for an order, handed back as it filled", period=period)
    conn.execute("UPDATE derivative_orders SET remaining = %s, reserved = reserved - %s, status = %s, closed_at = CASE WHEN %s = 0 THEN now() END"
                 " WHERE id = %s", (left, back, "filled" if left == 0 else "open", left, order["id"]))


def cancel_order(conn: Connection, account, order_id: int, now: datetime, *, why: str = "cancelled") -> dict:
    with conn.transaction():
        order = _one(conn, "SELECT * FROM derivative_orders WHERE id = %s AND account = %s AND status = 'open' FOR UPDATE", (order_id, account))
        if order is None:
            raise DerivativesError("There is no such waiting order of yours.")
        _cancel(conn, order, _state(conn, now)["period"], why)
        return {"cancelled": order["remaining"]}


def _cancel(conn: Connection, order: dict, period: int, status: str) -> None:
    if order["reserved"]:
        ledger.transfer(conn, payer=_orders_account(conn), receiver=order["account"], amount=order["reserved"],
                        kind="derivative_order_release", memo="Cash held for an order, handed back", period=period)
    conn.execute("UPDATE derivative_orders SET status = %s, reserved = 0, closed_at = now() WHERE id = %s",
                 ("expired" if status == "expired" else "cancelled", order["id"]))


def _fill(conn: Connection, s: dict, price: int, n: int, buyer: tuple, seller: tuple, period: int, now: datetime) -> dict:
    """One matched trade. The cash between the two sides moves at once: an option's price from buyer to seller; for a
    future, the difference between the trade's price and the series' mark (so every position in the series carries the
    same mark, and the two sides of every contract always add up to nothing). Players pay the fee; a tenth goes to the
    default fund. Then each side's positions are brought up to date.

    A forced close (a margin call not met) never fails for want of cash: the position's margin is handed back first,
    and what the trader still cannot pay is owed to the other side as a shortfall."""
    label = describe(s)
    level = spot(conn, s, now)
    (b_acct, b_meta), (s_acct, s_meta) = buyer, seller
    forced = bool(b_meta.get("forced") or s_meta.get("forced"))
    done = {}
    if forced:
        done = {"buyer": _apply(conn, s, b_acct, +1, n, price, period, now, b_meta, level),
                "seller": _apply(conn, s, s_acct, -1, n, price, period, now, s_meta, level)}

    def pay(payer, payer_meta, receiver, amount, kind, memo):
        if amount <= 0:
            return
        if payer_meta.get("forced"):
            got = ledger.pay_up_to(conn, payer=payer, receiver=receiver, wanted=amount, kind=kind, memo=memo, period=period)
            if got < amount and kind != "derivative_fee":
                from simulation import lending
                lending.record_shortfall(conn, payer, receiver, amount - got, f"The forced close of your {label}", period, now)
            return
        try:
            ledger.transfer(conn, payer=payer, receiver=receiver, amount=amount, kind=kind, memo=memo, period=period)
        except ledger.InsufficientFunds:
            failed = DerivativesError("There is not the cash for that trade and its fee.")
            failed.account = payer
            raise failed from None

    try:
        if s["kind"] == "future":
            diff = (price - s["mark"]) * n
            if diff > 0:
                pay(b_acct, b_meta, s_acct, diff, "future_trade", f"{n:,} {label}: bought above the mark")
            elif diff < 0:
                pay(s_acct, s_meta, b_acct, -diff, "future_trade", f"{n:,} {label}: sold below the mark")
        else:
            pay(b_acct, b_meta, s_acct, price * n, "option_premium", f"{n:,} {label} at {money(price)}")
        for acct, meta in ((b_acct, b_meta), (s_acct, s_meta)):
            if not meta.get("maker"):
                fee = _fee(conn, s, n, level)
                to_fund = fee * data.DEFAULT_FUND_SHARE_BPS // BPS
                if meta.get("forced"):
                    to_fund = ledger.pay_up_to(conn, payer=acct, receiver=fund_account(conn), wanted=to_fund, kind="derivative_fee",
                                               memo=f"The default fund's share of the fee: {n:,} {label}", period=period)
                    pay(acct, meta, _fees_account(conn), fee - fee * data.DEFAULT_FUND_SHARE_BPS // BPS, "derivative_fee",
                        f"The exchange's fee: {n:,} {label}")
                else:
                    pay(acct, meta, _fees_account(conn), fee - to_fund, "derivative_fee", f"The exchange's fee: {n:,} {label}")
                    pay(acct, meta, fund_account(conn), to_fund, "derivative_fee", f"The default fund's share of the fee: {n:,} {label}")
                if to_fund:
                    conn.execute("INSERT INTO clearing_fund_events (kind, amount, account, words, at) VALUES ('fee', %s, %s, %s, %s)",
                                 (to_fund, acct, f"A share of the fee on {n:,} {label}", now))
    except ledger.InsufficientFunds:
        raise DerivativesError("There is not the cash for that trade and its fee.") from None
    conn.execute("INSERT INTO derivative_trades (series_id, price, contracts, buyer, seller, with_makers, at) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                 (s["id"], price, n, b_acct, s_acct, bool(b_meta.get("maker") or s_meta.get("maker")), now))
    if forced:
        return done
    return {"buyer": _apply(conn, s, b_acct, +1, n, price, period, now, b_meta, level),
            "seller": _apply(conn, s, s_acct, -1, n, price, period, now, s_meta, level)}


def _apply(conn: Connection, s: dict, account, direction: int, n: int, price: int, period: int, now: datetime, meta: dict,
           level: int) -> dict:
    """Bring one side's positions up to date after a fill: close its opposite positions first, then open the rest."""
    maker = bool(meta.get("maker"))
    cash_settled = maker or bool(meta.get("company"))
    margin_acct = _margin_account(conn)
    label = describe(s)
    left = n
    position_id = None
    added = 0
    # The cash of the fill for this side: an option's price (paid or received); a future's trade price against the mark.
    per_cash = (-price if direction > 0 else price) if s["kind"] != "future" else (-(price - s["mark"]) if direction > 0 else price - s["mark"])
    opposite = "short" if direction > 0 else "long"
    for p in _rows(conn, "SELECT p.*, s.kind, s.underlying, s.company_id, s.strike, s.expiry_period FROM derivative_positions p"
                         " JOIN derivative_series s ON s.id = p.series_id WHERE p.account = %s AND p.series_id = %s AND p.status = 'open'"
                         " AND p.side = %s ORDER BY (p.id = %s) DESC, p.id FOR UPDATE OF p",
                   (account, s["id"], opposite, meta.get("prefer") or 0)):
        if left <= 0:
            break
        k = min(p["contracts"], left)
        release = p["margin"] * k // p["contracts"]
        if release:
            ledger.transfer(conn, payer=margin_acct, receiver=account, amount=release, kind="derivative_margin_release",
                            memo=f"Margin handed back: {k:,} {label} closed", period=period)
        realised = p["realised"] + per_cash * k
        if k == p["contracts"]:
            conn.execute("UPDATE derivative_positions SET status = %s, margin = margin - %s, realised = %s, result = %s, closed_at = %s,"
                         " call_since = NULL WHERE id = %s", ("closed_by_force" if meta.get("forced") else "closed", release, realised,
                                                             realised, now, p["id"]))
            if p.get("purpose"):
                _score_hedge(conn, p, realised, now)
        else:
            conn.execute("UPDATE derivative_positions SET contracts = contracts - %s, margin = margin - %s, realised = %s WHERE id = %s",
                         (k, release, p["realised"] * (p["contracts"] - k) // p["contracts"], p["id"]))
            # (The closed part's result is kept in a closed row of its own, so nothing made or lost is forgotten.)
            closed_part = p["realised"] - p["realised"] * (p["contracts"] - k) // p["contracts"] + per_cash * k
            conn.execute("INSERT INTO derivative_positions (account, series_id, side, contracts, entry_price, mark, margin, purpose, opened_by,"
                         " status, result, realised, by_makers, opened_at, closed_at) VALUES (%s, %s, %s, %s, %s, %s, 0, %s, %s, 'closed', %s,"
                         " %s, %s, %s, %s)", (account, s["id"], p["side"], k, p["entry_price"], p["mark"], p["purpose"], p["opened_by"],
                                              closed_part, closed_part, p["by_makers"], p["opened_at"], now))
        position_id = p["id"]
        left -= k
    if left > 0:
        margin = 0
        if not cash_settled:
            if s["kind"] == "future":
                margin = value_of(conn, s, level) * data.FUTURE_MARGIN_BPS // BPS * left
            elif direction < 0:
                margin = writer_margin(conn, s, now, level) * left
            if margin:
                try:
                    ledger.transfer(conn, payer=account, receiver=margin_acct, amount=margin, kind="derivative_margin",
                                    memo=f"Margin for {left:,} {label}", period=period)
                except ledger.InsufficientFunds:
                    failed = DerivativesError(f"That needs {money(margin)} of cash as margin.")
                    failed.account = account
                    raise failed from None
        row = _one(conn, "INSERT INTO derivative_positions (account, series_id, side, contracts, entry_price, mark, margin, purpose, opened_by,"
                         " opened_at, realised, by_makers, cash_settled) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
                   (account, s["id"], "long" if direction > 0 else "short", left, price, s["mark"] if s["kind"] == "future" else price,
                    margin, None if maker else meta.get("purpose"), None if maker else meta.get("player_id"), now, per_cash * left, maker,
                    cash_settled))
        position_id = row["id"]
        added = margin
    return {"position_id": position_id, "margin": added}


# The names used before the clearing house, kept for the empire's desk and the screens.
def open_position(conn: Connection, account, series_id: int, side: str, contracts: int, now: datetime, *, player_id=None,
                  purpose: str | None = None, limit: int | None = None) -> dict:
    if side not in ("long", "short"):
        raise DerivativesError("Buy or sell.")
    return trade(conn, account, series_id, "buy" if side == "long" else "sell", contracts, now, limit=limit, player_id=player_id,
                 purpose=purpose)


def _position(conn: Connection, account, position_id: int) -> dict:
    p = _one(conn, "SELECT p.*, s.kind, s.underlying, s.company_id, s.strike, s.expiry_period FROM derivative_positions p"
                   " JOIN derivative_series s ON s.id = p.series_id WHERE p.id = %s AND p.account = %s AND p.status = 'open'",
             (position_id, account))
    if p is None:
        raise DerivativesError("There is no such open position of yours.")
    return p


def close_position(conn: Connection, account, position_id: int, now: datetime, *, forced: bool = False) -> dict:
    """Close a position at the best price on offer: a long one is sold, a short one bought back."""
    p = _position(conn, account, position_id)
    done = trade(conn, account, p["series_id"], "sell" if p["side"] == "long" else "buy", p["contracts"], now, forced=forced,
                 prefer=p["id"])
    after = _one(conn, "SELECT result FROM derivative_positions WHERE id = %s", (p["id"],))
    return {"price": done["price"], "result": after["result"] if after else None}


def add_margin(conn: Connection, account, position_id: int, amount: int, now: datetime) -> dict:
    with conn.transaction():
        state = _state(conn, now)
        p = _one(conn, "SELECT * FROM derivative_positions WHERE id = %s AND account = %s AND status = 'open' FOR UPDATE", (position_id, account))
        if p is None:
            raise DerivativesError("There is no such open position of yours.")
        if not isinstance(amount, int) or isinstance(amount, bool) or amount <= 0:
            raise DerivativesError("Name an amount.")
        try:
            ledger.transfer(conn, payer=account, receiver=_margin_account(conn), amount=amount, kind="derivative_margin",
                            memo="More margin", period=state["period"])
        except ledger.InsufficientFunds:
            raise DerivativesError("There is not the cash.") from None
        conn.execute("UPDATE derivative_positions SET margin = margin + %s, call_since = NULL WHERE id = %s", (amount, p["id"]))
        return {"margin": p["margin"] + amount}


# ---------------------------------------------------------------------------
# Settlement: every position in a series settled together, through the clearing house
# ---------------------------------------------------------------------------

def _settle_series(conn: Connection, s: dict, level_or_payoff: int, period: int, now: datetime, why: str, *,
                   payoff: bool = False) -> dict:
    """Settle every open position in a series at once. For a future, each moves from its mark to `level_or_payoff`;
    at an option's expiry, each long is owed `level_or_payoff` a contract and each short owes it.

    Losers pay first: from their margin, the market makers from their cash, and what a player cannot pay from the
    default fund (the player then owes the fund). What was collected is shared among the winners: in full, as the two
    sides of every contract add up to nothing; less only if the default fund itself ran dry."""
    margin_acct = _margin_account(conn)
    fund = fund_account(conn)
    label = describe(s)
    positions = _rows(conn, "SELECT p.*, s.kind, s.underlying, s.company_id, s.strike, s.expiry_period FROM derivative_positions p"
                            " JOIN derivative_series s ON s.id = p.series_id WHERE p.series_id = %s AND p.status = 'open' ORDER BY p.id"
                            " FOR UPDATE OF p", (s["id"],))
    moves = {}
    for p in positions:
        sign = 1 if p["side"] == "long" else -1
        moves[p["id"]] = (level_or_payoff * p["contracts"] * sign) if payoff else (level_or_payoff - p["mark"]) * p["contracts"] * sign
    pot = 0
    unpaid: list[tuple] = []          # (loser, what it could not pay, what the fund covered of it)
    for p in positions:
        loss = -moves[p["id"]]
        if loss <= 0:
            continue
        if p["cash_settled"]:
            got = ledger.pay_up_to(conn, payer=p["account"], receiver=margin_acct, wanted=loss, kind="variation_margin",
                                   memo=f"{label}: {why}", period=period)
        else:
            got = min(loss, p["margin"])
            p["margin"] -= got
            conn.execute("UPDATE derivative_positions SET margin = margin - %s, realised = realised - %s WHERE id = %s",
                         (got, got, p["id"]))
        short = loss - got
        if short:
            cover = ledger.pay_up_to(conn, payer=fund, receiver=margin_acct, wanted=short, kind="default_fund_cover",
                                     memo=f"The default fund covers a loss beyond the margin: {label}", period=period)
            if cover:
                conn.execute("INSERT INTO clearing_fund_events (kind, amount, account, words, at) VALUES ('cover', %s, %s, %s, %s)",
                             (cover, p["account"], f"Covered a loss beyond the margin on {label}", now))
            if not p["cash_settled"]:
                conn.execute("UPDATE derivative_positions SET realised = realised - %s WHERE id = %s", (short, p["id"]))
            unpaid.append((p, short, cover))
            got += cover
        pot += got
    gains = {pid: m for pid, m in moves.items() if m > 0}
    wanted = sum(gains.values())
    paid_total = 0
    winners = [p for p in positions if p["id"] in gains]
    paid_to: dict = {}
    for i, p in enumerate(winners):
        g = gains[p["id"]] if pot >= wanted else (pot - paid_total if i == len(winners) - 1 else gains[p["id"]] * pot // wanted)
        paid_total += g
        paid_to[p["id"]] = max(g, 0)
        if g <= 0:
            continue
        if p["cash_settled"]:
            ledger.transfer(conn, payer=margin_acct, receiver=p["account"], amount=g, kind="variation_margin", memo=f"{label}: {why}",
                            period=period)
        else:
            p["margin"] += g
            conn.execute("UPDATE derivative_positions SET margin = margin + %s, realised = realised + %s WHERE id = %s", (g, g, p["id"]))
    # What a loser could not pay is owed: what the fund covered, to the fund; the rest (when the fund ran dry), to the
    # winners who were paid short, in proportion to what each is still owed.
    if unpaid:
        from simulation import lending
        still = {p["id"]: gains[p["id"]] - paid_to.get(p["id"], 0) for p in winners if gains[p["id"]] > paid_to.get(p["id"], 0)}
        still_total = sum(still.values())
        for loser, short, cover in unpaid:
            if cover:
                lending.record_shortfall(conn, loser["account"], fund, cover, f"Your {label}", period, now)
            rest = short - cover
            if rest > 0 and still_total > 0:
                shared = 0
                owed_to = [w for w in winners if w["id"] in still]
                for j, w in enumerate(owed_to):
                    part = rest - shared if j == len(owed_to) - 1 else rest * still[w["id"]] // still_total
                    shared += part
                    if part > 0 and w["account"] != loser["account"]:
                        lending.record_shortfall(conn, loser["account"], w["account"], part, f"Your {label}", period, now)
            if not loser["cash_settled"]:
                _note(conn, loser, f"Your {label} lost {money(short)} more than its margin. "
                                   + ("The default fund paid it; you owe the fund." if cover == short else
                                      "The default fund paid what it could; you owe the fund and the other side the rest."), now)
    if pot > paid_total:                                   # (only if nobody won: nothing is left behind in the escrow)
        ledger.transfer(conn, payer=margin_acct, receiver=fund, amount=pot - paid_total, kind="default_fund_cover",
                        memo=f"Left over from settling {label}", period=period)
        conn.execute("INSERT INTO clearing_fund_events (kind, amount, account, words, at) VALUES ('repaid', %s, NULL, %s, %s)",
                     (pot - paid_total, f"Left over from settling {label}", now))
    if not payoff:
        conn.execute("UPDATE derivative_positions SET mark = %s WHERE series_id = %s AND status = 'open'", (level_or_payoff, s["id"]))
        conn.execute("UPDATE derivative_series SET mark = %s WHERE id = %s", (level_or_payoff, s["id"]))
        s["mark"] = level_or_payoff
    return {"positions": len(positions), "moved": wanted, "short": max(wanted - pot, 0)}


def at_bell(conn: Connection, now: datetime, ended) -> dict:
    """Every night: waiting orders are handed back; futures are settled to the night's price; margin calls; positions
    not made good are closed by force."""
    if _one(conn, "SELECT to_regclass('derivative_orders') IS NOT NULL AS ok")["ok"] is not True:
        return {}
    period = _state(conn, now)["period"]
    done = {"settled": 0, "calls": 0, "closed": 0, "orders": 0}
    for order in _rows(conn, "SELECT * FROM derivative_orders WHERE status = 'open' ORDER BY id"):
        with conn.transaction():
            order = _one(conn, "SELECT * FROM derivative_orders WHERE id = %s AND status = 'open' FOR UPDATE", (order["id"],))
            if order:
                _cancel(conn, order, period, "expired")
                done["orders"] += 1
    for s in _rows(conn, "SELECT * FROM derivative_series WHERE status = 'open' AND kind = 'future' AND EXISTS (SELECT 1 FROM"
                         " derivative_positions p WHERE p.series_id = derivative_series.id AND p.status = 'open') ORDER BY id"):
        with conn.transaction():
            s = _series(conn, s["id"], lock=True)
            _settle_series(conn, s, fair(conn, s, now), period, now, "tonight's settlement")
            done["settled"] += 1
    for p in _rows(conn, "SELECT p.id FROM derivative_positions p JOIN derivative_series s ON s.id = p.series_id"
                         " WHERE p.status = 'open' AND NOT p.cash_settled AND (s.kind = 'future' OR p.side = 'short') ORDER BY p.id"):
        with conn.transaction():
            p = _one(conn, "SELECT p.*, s.kind, s.underlying, s.company_id, s.strike, s.expiry_period FROM derivative_positions p"
                           " JOIN derivative_series s ON s.id = p.series_id WHERE p.id = %s AND p.status = 'open' FOR UPDATE OF p", (p["id"],))
            if p is None:
                continue
            level = spot(conn, p, now)
            if p["kind"] == "future":
                needed = value_of(conn, p, level) * data.FUTURE_MAINTENANCE_BPS // BPS * p["contracts"]
            else:
                needed = writer_margin(conn, p, now, level) * p["contracts"] * data.WRITER_CALL_SHARE_BPS // BPS
            unmet = p["call_since"] is not None and p["call_since"] < ended
            if p["margin"] < needed and (unmet or p["margin"] == 0):
                result = close_position(conn, p["account"], p["id"], now, forced=True)
                _note(conn, p, f"Margin call not met: your {describe(p)} was closed at {money(result['price'] or 0)} a contract.", now)
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
    if p.get("by_makers") or p.get("cash_settled"):
        return
    conn.execute("INSERT INTO lending_events (account, kind, words, at) VALUES (%s, 'derivatives', %s, %s)", (p["account"], words, now))


def close(conn: Connection, period: int, now: datetime) -> dict:
    """At the quarter's close: every contract that runs to it is settled in cash; new ones are listed."""
    if _one(conn, "SELECT to_regclass('derivative_series') IS NOT NULL AS ok")["ok"] is not True:
        return {}
    settled = 0
    margin_acct = _margin_account(conn)
    for s in _rows(conn, "SELECT * FROM derivative_series WHERE status = 'open' AND expiry_period <= %s ORDER BY id FOR UPDATE", (period,)):
        level = spot(conn, s, now)
        for order in _rows(conn, "SELECT * FROM derivative_orders WHERE series_id = %s AND status = 'open' FOR UPDATE", (s["id"],)):
            _cancel(conn, order, period, "expired")
        if s["kind"] == "future":
            _settle_series(conn, s, value_of(conn, s, level), period, now, "the final settlement")
        else:
            intrinsic = (level - s["strike"]) if s["kind"] == "call" else (s["strike"] - level)
            _settle_series(conn, s, max(intrinsic, 0) * multiplier(s), period, now, "settled at expiry", payoff=True)
        for p in _rows(conn, "SELECT p.*, s.kind, s.underlying, s.company_id, s.strike, s.expiry_period FROM derivative_positions p"
                             " JOIN derivative_series s ON s.id = p.series_id WHERE p.series_id = %s AND p.status = 'open' ORDER BY p.id"
                             " FOR UPDATE OF p", (s["id"],)):
            if p["margin"]:
                ledger.transfer(conn, payer=margin_acct, receiver=p["account"], amount=p["margin"], kind="derivative_margin_release",
                                memo=f"Margin handed back: {describe(p)} settled", period=period)
            # (What it made or lost is already in `realised`: premiums, settlements and the payout. The margin handed
            # back is the trader's own deposit.)
            conn.execute("UPDATE derivative_positions SET status = 'expired', margin = 0, result = realised, closed_at = %s,"
                         " call_since = NULL WHERE id = %s", (now, p["id"]))
            if p.get("purpose"):
                _score_hedge(conn, p, p["realised"], now)
            settled += 1
        conn.execute("UPDATE derivative_series SET status = 'settled', settled_spot = %s WHERE id = %s", (level, s["id"]))
    conn.execute("SELECT pg_advisory_xact_lock(hashtext('derivatives:listing'))")
    added = list_series(conn, period, now)
    hedged = hedge_companies(conn, period, now)
    return {"settled": settled, "listed": added, "hedged": hedged}


def hedge_companies(conn: Connection, period: int, now: datetime) -> int:
    """Oil and gas producers sell oil futures for part of next quarter's output; the big users of fuel (airlines,
    transport, shipping, power) buy them. Each hedges in proportion to its last quarter's sales, settled in cash every
    night on its bank's credit (no margin held), and the gain or loss runs through its own accounts."""
    s = _one(conn, "SELECT * FROM derivative_series WHERE kind = 'future' AND underlying = 'OIL' AND status = 'open'"
                   " AND expiry_period = %s", (period + 1,))
    if s is None:
        return 0
    contract = value_of(conn, s, spot(conn, s, now))
    if contract <= 0:
        return 0
    done = 0
    for c in _rows(conn, "SELECT c.id, c.ticker, c.account_id, c.sector, (SELECT r.revenue FROM company_results r WHERE r.company_id = c.id"
                         " ORDER BY r.period DESC LIMIT 1) AS sales FROM companies c WHERE c.status = 'trading'"
                         " AND (c.ticker = ANY(%s) OR c.sector = ANY(%s)) ORDER BY c.ticker",
                   (list(data.HEDGE_SELLERS), list(data.HEDGE_BUYERS_SECTORS))):
        seller = c["ticker"] in data.HEDGE_SELLERS
        share = data.HEDGE_SELL_SHARE_BPS if seller else data.HEDGE_BUY_SHARE_BPS
        n = min((c["sales"] or 0) * share // BPS // contract, data.HEDGE_MOST_CONTRACTS)
        # Only as much as its cash would stand as margin (it settles from its cash each night), and not while it owes for
        # an earlier loss it could not pay.
        n = min(n, ledger.balance(conn, c["account_id"]) // max(contract * data.FUTURE_MARGIN_BPS // BPS, 1))
        if _one(conn, "SELECT 1 FROM player_loans WHERE borrower = %s AND status = 'default'", (c["account_id"],)):
            continue
        if n <= 0 or _one(conn, "SELECT 1 FROM derivative_positions WHERE account = %s AND series_id = %s AND status = 'open'",
                          (c["account_id"], s["id"])):
            continue
        try:
            trade(conn, c["account_id"], s["id"], "sell" if seller else "buy", int(n), now, company=True)
            done += 1
        except DerivativesError:
            continue                                     # (a company short of cash for the fee simply does not hedge)
    return done


def check_books(conn: Connection) -> list[str]:
    if _one(conn, "SELECT to_regclass('derivative_orders') IS NOT NULL AS ok")["ok"] is not True:
        return []
    out = []
    for code, sql, what in ((MARGIN, "SELECT coalesce(sum(margin), 0)::bigint AS m FROM derivative_positions WHERE status = 'open'",
                             "Options and futures margin"),
                            (ORDERS, "SELECT coalesce(sum(reserved), 0)::bigint AS m FROM derivative_orders WHERE status = 'open'",
                             "Cash held for options and futures orders"),
                            (FUND, "SELECT coalesce(sum(CASE kind WHEN 'cover' THEN -amount ELSE amount END), 0)::bigint AS m"
                                   " FROM clearing_fund_events", "The default fund")):
        row = _one(conn, "SELECT id FROM ledger_accounts WHERE code = %s", (code,))
        held = ledger.balance(conn, row["id"]) if row else 0
        recorded = _one(conn, sql)["m"]
        if held != recorded:
            out.append(f"{what}: {held} held against {recorded} recorded.")
    for r in _rows(conn, "SELECT series_id, sum(CASE side WHEN 'long' THEN contracts ELSE -contracts END)::bigint AS net"
                         " FROM derivative_positions WHERE status = 'open' GROUP BY series_id HAVING sum(CASE side WHEN 'long' THEN contracts"
                         " ELSE -contracts END) <> 0"):
        out.append(f"Options and futures: series {r['series_id']} has {r['net']} more contracts on one side than the other.")
    return out


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


def explain(conn: Connection, series_id: int, now: datetime) -> dict:
    """A contract's fair value at three depths: plain words, the professional method, and the mathematics with the
    numbers. Every figure comes from public prices and the published rate."""
    s = _series(conn, series_id)
    level = spot(conn, s, now)
    t = years_left(conn, s, now)
    r = policy_rate(conn) / BPS
    value = fair(conn, s, now, level)
    last = _one(conn, "SELECT price FROM derivative_trades WHERE series_id = %s ORDER BY id DESC LIMIT 1", (series_id,))
    out = {"name": describe(s), "fair": value, "last_trade": last["price"] if last else None}
    if s["kind"] == "future":
        carry = r - data.WORLD_RATE_BPS / BPS if s["underlying"] == "NAIRA" else r
        underlying = value_of(conn, s, level)
        out["plain"] = (f"A future fixes today the price of something you will settle at the quarter's end. Holding the thing itself "
                        f"until then would tie up money that could earn interest, so the future costs a little more than today's "
                        f"value: about {money(underlying)} now, {money(value)} for the end of the quarter.")
        out["method"] = ("The cost of carry: the futures price is today's value grown at the interest you give up (for the naira, "
                         "our rate less the rate abroad) for the time left.")
        out["maths"] = (f"F = S × (1 + r × T) = {money(underlying)} × (1 + {carry:.4f} × {t:.3f}) = {money(value)}. "
                        f"S is one contract's value today, r the yearly rate, T the years left (a game year is "
                        f"{data.GAME_YEAR_REAL_DAYS} real days).")
        return out
    sigma = volatility(conn, s)
    k = s["strike"]
    if t > 0 and sigma > 0 and level > 0:
        d1 = (math.log(level / k) + (r + sigma * sigma / 2) * t) / (sigma * math.sqrt(t))
        d2 = d1 - sigma * math.sqrt(t)
    else:
        d1 = d2 = float("nan")
    unit = "a share" if s.get("company_id") else "a point"
    out["plain"] = (f"A {s['kind']} pays {'what the price ends above' if s['kind'] == 'call' else 'what the price ends below'} "
                    f"{describe(s).split(' at ')[1].split(',')[0]} at the quarter's end. Its value is the average of what it could "
                    f"pay, over every way the price might move, brought back to today. The more the price swings and the longer "
                    f"there is to go, the more it is worth: {money(value)} a contract now.")
    out["method"] = ("The Black-Scholes model: the price today, the strike, the time left, the interest rate and the share's "
                     "swing (its volatility, from the last 60 trading days) give the option's value. The market makers quote "
                     "a little either side of it.")
    out["maths"] = (f"{'C = S·N(d1) − K·e^(−rT)·N(d2)' if s['kind'] == 'call' else 'P = K·e^(−rT)·N(−d2) − S·N(−d1)'}, with "
                    f"d1 = [ln(S/K) + (r + σ²/2)T] / (σ√T) = {d1:.3f} and d2 = d1 − σ√T = {d2:.3f}; "
                    f"S = {level / 100:,.2f} {unit}, K = {k / 100:,.2f}, r = {r:.4f}, σ = {sigma:.3f}, T = {t:.3f} years. "
                    f"Times {multiplier(s) if s.get('company_id') else 'the ₦100 a point'} = {money(value)} a contract.")
    return out


def board(conn: Connection, now: datetime, underlying: str | None = None) -> dict:
    """The option chains and futures on offer: the price from matched trades, the market makers' two prices, the fair
    value, and the best waiting orders. Public; never who traded or who is waiting."""
    ensure(conn, now)
    _RISK_MEMO[id(conn)] = risk.share_risk(conn)          # worked out once for the whole board
    try:
        return _board(conn, now, underlying)
    finally:
        _RISK_MEMO.pop(id(conn), None)


def _board(conn: Connection, now: datetime, underlying: str | None) -> dict:
    state = _state(conn, now)
    rows = _rows(conn, "SELECT * FROM derivative_series WHERE status = 'open' AND expiry_period >= %s"
                       + (" AND underlying = %s" if underlying else "") + " ORDER BY expiry_period, underlying, kind, strike",
                 (state["period"], underlying) if underlying else (state["period"],))
    ids = [s["id"] for s in rows]
    last = {r["series_id"]: r for r in _rows(conn, "SELECT DISTINCT ON (series_id) series_id, price, at FROM derivative_trades"
                                                   " WHERE series_id = ANY(%s) ORDER BY series_id, id DESC", (ids,))}
    best = {}
    for r in _rows(conn, "SELECT series_id, side, CASE side WHEN 'buy' THEN max(limit_price) ELSE min(limit_price) END AS price"
                         " FROM derivative_orders WHERE status = 'open' AND series_id = ANY(%s) GROUP BY series_id, side", (ids,)):
        best[(r["series_id"], r["side"])] = r["price"]
    levels: dict = {}
    out = []
    for s in rows:
        key = (s["underlying"], s["company_id"])
        if key not in levels:
            levels[key] = spot(conn, s, now)
        q = quote(conn, s, now)
        out.append({"id": s["id"], "kind": s["kind"], "underlying": s["underlying"], "strike": s["strike"], "expiry_period": s["expiry_period"],
                    "expiry": clock.period_label(s["expiry_period"]), "name": describe(s), "spot": levels[key],
                    "value": value_of(conn, s, levels[key]), "bid": q["bid"], "ask": q["ask"], "fair": q["fair"],
                    "last_trade": last[s["id"]]["price"] if s["id"] in last else None,
                    "best_bid": best.get((s["id"], "buy")), "best_ask": best.get((s["id"], "sell")),
                    "margin_long": value_of(conn, s, levels[key]) * data.FUTURE_MARGIN_BPS // BPS if s["kind"] == "future" else 0,
                    "margin_short": (value_of(conn, s, levels[key]) * data.FUTURE_MARGIN_BPS // BPS if s["kind"] == "future"
                                     else writer_margin(conn, s, now, levels[key]))})
    underlyings = sorted({s["underlying"] for s in _rows(conn, "SELECT DISTINCT underlying FROM derivative_series WHERE status = 'open'")})
    _, market = exchange.session_of(now)
    return {"series": out, "underlyings": underlyings, "open": market is clock.MarketState.OPEN,
            "unlock": {"options_level": data.UNLOCK_OPTIONS_LEVEL, "advanced_level": data.UNLOCK_ADVANCED_LEVEL},
            "default_fund": ledger.balance(conn, fund_account(conn))}


def orders_of(conn: Connection, account) -> list[dict]:
    return [{"id": o["id"], "name": describe(o), "side": o["side"], "limit_price": o["limit_price"], "remaining": o["remaining"],
             "contracts": o["contracts"], "reserved": o["reserved"]}
            for o in _rows(conn, "SELECT o.*, s.kind, s.underlying, s.company_id, s.strike, s.expiry_period FROM derivative_orders o"
                                 " JOIN derivative_series s ON s.id = o.series_id WHERE o.account = %s AND o.status = 'open' ORDER BY o.id",
                           (account,))]


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
    """What the account's options and futures are worth to it now (margin, and cash held for its orders, included)."""
    total = _one(conn, "SELECT coalesce(sum(reserved), 0)::bigint AS r FROM derivative_orders WHERE account = %s AND status = 'open'",
                 (account,))["r"]
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
    now = _one(conn, "SELECT now() AS n")["n"]               # the exchange's clock (the database's), as the server uses
    for r in _rows(conn, "SELECT DISTINCT a.id AS account FROM ledger_accounts a WHERE a.kind = 'player' AND (EXISTS (SELECT 1 FROM"
                         " derivative_positions p WHERE p.account = a.id AND p.status = 'open') OR EXISTS (SELECT 1 FROM derivative_orders o"
                         " WHERE o.account = a.id AND o.status = 'open'))"):
        out[r["account"]] = (0, held_value(conn, r["account"], now))
    return out


def _register() -> None:
    from simulation import marketview
    if _players_derivatives not in marketview._OTHER_HOLDINGS:
        marketview._OTHER_HOLDINGS.append(_players_derivatives)


_register()
