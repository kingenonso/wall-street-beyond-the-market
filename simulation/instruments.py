"""The gap stage, Part 1: preferred shares and warrants (the owner's suggestion 14).

Preferred shares. A sound company (rated A or better, in banking, insurance, telecoms, power or property) may raise
money by selling preferred shares to the pension funds: ₦100 each, paying a fixed dividend each quarter (the yearly
rate set at issue) before its ordinary shareholders are paid anything, and only in a quarter it made a profit; a
missed dividend is not made up later. They carry no vote. The pension funds' desk deals in them at two prices.

Warrants. The right to buy new shares from the company at a set price until a quarter's close. They come with rights
issues (one warrant for every five new shares taken up) and with high-yield bonds (handed to the bonds' first buyer),
and are dealt at the same desk. A holder may hand them in, with the price, to be used: the new shares are issued as
the quarter closes, the company receives the money, and the share price allows for the new shares. A warrant not used
by its last quarter's close lapses. A share split adjusts every warrant so nobody gains or loses by it.
"""

from __future__ import annotations

import math
from datetime import datetime

from psycopg import Connection
from psycopg.rows import dict_row

from simulation import clock, exchange, ledger
from simulation import world_data as data
from simulation.ledger import Leg
from simulation.money import BPS

HELD = "instruments:held"            # warrants and cash held for warrants waiting to be used


class InstrumentError(Exception):
    pass


def _rows(conn: Connection, sql: str, params=()) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def _one(conn: Connection, sql: str, params=()) -> dict | None:
    rows = _rows(conn, sql, params)
    return rows[0] if rows else None


def money(kobo: int) -> str:
    return f"₦{kobo / 100:,.2f}"


def _held(conn: Connection):
    if _one(conn, "SELECT 1 FROM ledger_accounts WHERE code = %s", (HELD,)) is None:
        ledger.create_account(conn, kind="escrow", name="The exchange: warrants and cash held to be used", code=HELD)
    return ledger.account_id(conn, HELD)


def _dealer(conn: Connection):
    return ledger.account_id(conn, ledger.INVESTORS_INSTITUTIONS)


def _ready(conn: Connection) -> bool:
    return _one(conn, "SELECT to_regclass('instruments') IS NOT NULL AS ok")["ok"] is True


# ---------------------------------------------------------------------------
# Prices at the desk
# ---------------------------------------------------------------------------

def _policy(conn: Connection) -> int:
    row = _one(conn, "SELECT next_policy_rate_bps FROM economy_results ORDER BY period DESC LIMIT 1")
    return row["next_policy_rate_bps"] if row else data.NEUTRAL_RATE_BPS


def _rating(conn: Connection, company_id) -> str:
    row = _one(conn, "SELECT credit_rating FROM company_reports WHERE company_id = %s ORDER BY period DESC, version DESC LIMIT 1",
               (company_id,))
    return row["credit_rating"] if row and row["credit_rating"] else "BBB"


def fair(conn: Connection, inst: dict, now: datetime) -> int:
    """The desk's own price for one unit."""
    if inst["kind"] == "preferred":
        from simulation import bonds
        wanted = bonds.government_yield_bps(_policy(conn), 40) + bonds.credit_spread_bps(_rating(conn, inst["company_id"])) \
            + data.PREFERRED_EXTRA_BPS
        return max(inst["par"] * inst["dividend_bps"] // max(wanted, 1), 1)
    if inst["status"] != "open":
        return 0
    from simulation import derivatives, risk
    s = derivatives.share_level(conn, inst["company_id"], now)
    k = inst["strike"]
    w = _one(conn, "SELECT world_start, weeks_ahead FROM world_state")
    from datetime import timedelta
    expiry = clock.effective_start(w["world_start"], w["weeks_ahead"]) + timedelta(days=clock.REAL_DAYS_PER_QUARTER * inst["expiry_period"])
    t = max((expiry - now).total_seconds() / (data.GAME_YEAR_REAL_DAYS * 86_400), 0.0)
    found = risk.share_risk(conn).get(inst["company_id"])
    sigma = max(found["volatility_bps"] if found else data.OPTION_LEAST_VOLATILITY_BPS, data.OPTION_LEAST_VOLATILITY_BPS) / BPS
    value = derivatives.black_scholes("call", s, k, t, sigma, _policy(conn) / BPS) if s > 0 else 0.0
    return max(int(math.floor(value * inst["shares_per"])), 0)


def quote(conn: Connection, inst: dict, now: datetime) -> dict:
    price = fair(conn, inst, now)
    half = price * (data.PREFERRED_SPREAD_BPS if inst["kind"] == "preferred" else data.WARRANT_SPREAD_BPS) // BPS
    return {"fair": price, "bid": max(price - half, 0), "ask": price + max(half, 1)}


# ---------------------------------------------------------------------------
# Issuing
# ---------------------------------------------------------------------------

def _new_asset(conn: Connection, code: str, kind: str, name: str, company: dict) -> None:
    ledger.create_asset(conn, code=code, kind=kind, name=name, unit=kind, issuer_account_id=company["account_id"])


def issue_preferred(conn: Connection, period: int, now: datetime) -> int:
    """At a quarter's close: sound companies without preferred shares may sell some to the pension funds."""
    if not _ready(conn):
        return 0
    dealer = _dealer(conn)
    issued = 0
    for c in _rows(conn, """
            SELECT c.id, c.ticker, c.name, c.account_id, r.total_assets FROM companies c
            JOIN LATERAL (SELECT total_assets FROM company_results WHERE company_id = c.id ORDER BY period DESC LIMIT 1) r ON true
            WHERE c.status = 'trading' AND c.sector = ANY(%s)
              AND NOT EXISTS (SELECT 1 FROM instruments i WHERE i.company_id = c.id AND i.kind = 'preferred')
            ORDER BY c.ticker""", (list(data.PREFERRED_SECTORS),)):
        rating = _rating(conn, c["id"])
        if rating not in data.PREFERRED_RATINGS or (period + sum(map(ord, c["ticker"]))) % data.PREFERRED_ONE_IN:
            continue
        from simulation import bonds
        rate = bonds.government_yield_bps(_policy(conn), 40) + bonds.credit_spread_bps(rating) + data.PREFERRED_EXTRA_BPS
        units = c["total_assets"] * data.PREFERRED_SIZE_BPS // BPS // data.PREFERRED_PAR
        # The pension funds put at most a tenth of their cash into any one issue: they must still pay pensions and buy.
        units = min(units, ledger.balance(conn, dealer) * data.PREFERRED_DEALER_MOST_BPS // BPS // data.PREFERRED_PAR)
        if units <= 0:
            continue
        code = f"PRF-{c['ticker']}"
        name = f"{c['name']} {rate / 100:.2f}% preferred shares"
        _new_asset(conn, code, "preferred", name, c)
        ledger.post(conn, kind="preferred_issue", memo=f"{c['name']}: {units:,} preferred shares sold to the pension funds", period=period,
                    legs=[Leg(c["account_id"], -units, code), Leg(dealer, units, code),
                          Leg(dealer, -units * data.PREFERRED_PAR), Leg(c["account_id"], units * data.PREFERRED_PAR)])
        conn.execute("INSERT INTO instruments (asset, kind, company_id, name, par, dividend_bps, issued_period, why, at)"
                     " VALUES (%s, 'preferred', %s, %s, %s, %s, %s, %s, %s)",
                     (code, c["id"], name, data.PREFERRED_PAR, rate, period, "Raised from the pension funds", now))
        issued += 1
    return issued


def grant_warrants(conn: Connection, company: dict, holders: dict, *, strike: int, expiry_period: int, period: int, why: str,
                   now: datetime) -> dict | None:
    """Hand warrants to the holders named ({account: warrants}), each for one new share at `strike`."""
    if not _ready(conn):
        return None
    holders = {a: n for a, n in holders.items() if n > 0}
    if not holders or strike <= 0:
        return None
    ticker = _one(conn, "SELECT ticker FROM companies WHERE id = %s", (company["id"],))["ticker"]
    # One code for each issue: the quarter, and a second issue in the same quarter numbered after it (WRT-ABC9, WRT-ABC91...).
    code = f"WRT-{ticker}{period}"
    inst = _one(conn, "SELECT * FROM instruments WHERE asset = %s", (code,))
    n = 0
    while inst is not None and (inst["strike"] != strike or inst["expiry_period"] != expiry_period):
        n += 1
        code = f"WRT-{ticker}{period}{n}"[:12] if len(f"{period}{n}") <= 4 else f"WRT-{ticker}{(period * 10 + n) % 10000}"
        inst = _one(conn, "SELECT * FROM instruments WHERE asset = %s", (code,))
    if inst is None:
        name = f"{company['name']} warrants at {money(strike)}, to {clock.period_label(expiry_period)}"
        _new_asset(conn, code, "warrant", name, company)
        inst = _one(conn, "INSERT INTO instruments (asset, kind, company_id, name, strike, shares_per, expiry_period, issued_period, why, at)"
                          " VALUES (%s, 'warrant', %s, %s, %s, 1, %s, %s, %s, %s) RETURNING *",
                    (code, company["id"], name, strike, expiry_period, period, why, now))
    total = sum(holders.values())
    ledger.post(conn, kind="warrant_issue", memo=f"{company['name']}: {total:,} warrants handed out ({why})", period=period,
                legs=[Leg(company["account_id"], -total, code), *[Leg(a, n, code) for a, n in holders.items()]])
    return inst


# ---------------------------------------------------------------------------
# Dealing at the desk
# ---------------------------------------------------------------------------

def find(conn: Connection, code: str) -> dict:
    inst = _one(conn, "SELECT i.*, c.account_id AS company_account, c.name AS company, c.ticker FROM instruments i"
                      " JOIN companies c ON c.id = i.company_id WHERE i.asset = %s", (code,))
    if inst is None:
        raise InstrumentError("There is no such preferred share or warrant.")
    return inst


def trade(conn: Connection, account, code: str, side: str, units: int, now: datetime) -> dict:
    with conn.transaction():
        _, session = exchange.session_of(now)
        if session is not clock.MarketState.OPEN:
            raise InstrumentError("The desk deals from 12:00 to 22:00 Lagos time.")
        if side not in ("buy", "sell"):
            raise InstrumentError("Buy or sell.")
        if not isinstance(units, int) or isinstance(units, bool) or units <= 0:
            raise InstrumentError("Name how many.")
        inst = find(conn, code)
        if inst["status"] != "open":
            raise InstrumentError("Those warrants have lapsed.")
        from simulation import newsroom
        try:
            newsroom.check_trade(conn, account, inst["company_id"], now)
        except exchange.ExchangeError as e:
            raise InstrumentError(str(e)) from e
        q = quote(conn, inst, now)
        price = q["ask"] if side == "buy" else q["bid"]
        if price <= 0:
            raise InstrumentError("The desk is not buying those today: they are worth next to nothing.")
        dealer = _dealer(conn)
        buyer, seller = (account, dealer) if side == "buy" else (dealer, account)
        if side == "buy" and ledger.balance(conn, dealer, code) < units:
            raise InstrumentError(f"The pension funds have {ledger.balance(conn, dealer, code):,} of those to sell.")
        if side == "sell" and ledger.balance(conn, account, code) < units:
            raise InstrumentError("You do not hold that many.")
        try:
            ledger.post(conn, kind="instrument_trade", memo=f"{units:,} {inst['name']} at {money(price)}",
                        legs=[Leg(seller, -units, code), Leg(buyer, units, code), Leg(buyer, -units * price), Leg(seller, units * price)])
        except ledger.InsufficientFunds:
            raise InstrumentError(f"That costs {money(units * price)}." if side == "buy" else "The pension funds cannot pay for that many today.") from None
        conn.execute("INSERT INTO instrument_trades (instrument_id, account, side, units, price, at) VALUES (%s, %s, %s, %s, %s, %s)",
                     (inst["id"], account, side, units, price, now))
        return {"code": code, "side": side, "units": units, "price": price, "value": units * price}


def ask_to_exercise(conn: Connection, account, code: str, units: int, now: datetime) -> dict:
    """Hand in warrants, with the price of the new shares, to be used at the quarter's close."""
    from simulation import bonds
    with conn.transaction():
        if not bonds.books_open(conn, now):
            raise InstrumentError(bonds.CLOSING)
        inst = find(conn, code)
        if inst["kind"] != "warrant" or inst["status"] != "open":
            raise InstrumentError("Only warrants that have not lapsed can be used.")
        if not isinstance(units, int) or isinstance(units, bool) or units <= 0:
            raise InstrumentError("Name how many.")
        from simulation import newsroom
        try:
            newsroom.check_trade(conn, account, inst["company_id"], now)
        except exchange.ExchangeError as e:
            raise InstrumentError(str(e)) from e
        cash = units * inst["shares_per"] * inst["strike"]
        held = _held(conn)
        try:
            ledger.post(conn, kind="warrant_hold", memo=f"{inst['name']}: {units:,} handed in to be used",
                        legs=[Leg(account, -units, code), Leg(held, units, code), Leg(account, -cash), Leg(held, cash)])
        except ledger.InsufficientFunds:
            raise InstrumentError(f"That needs {units:,} warrants and {money(cash)} for the new shares.") from None
        row = _one(conn, "INSERT INTO warrant_exercises (instrument_id, account, units, cash, at) VALUES (%s, %s, %s, %s, %s) RETURNING id",
                   (inst["id"], account, units, cash, now))
        return {"id": row["id"], "units": units, "cash": cash, "shares": units * inst["shares_per"]}


def cancel_exercise(conn: Connection, account, exercise_id: int, now: datetime) -> dict:
    from simulation import bonds
    with conn.transaction():
        if not bonds.books_open(conn, now):
            raise InstrumentError(bonds.CLOSING)
        row = _one(conn, "SELECT w.*, i.asset, i.name FROM warrant_exercises w JOIN instruments i ON i.id = w.instrument_id"
                         " WHERE w.id = %s AND w.account = %s AND w.status = 'waiting' FOR UPDATE OF w", (exercise_id, account))
        if row is None:
            raise InstrumentError("There is no such request of yours waiting.")
        _hand_back(conn, row)
        return {"cancelled": row["units"]}


def _hand_back(conn: Connection, row: dict, status: str = "cancelled", period: int | None = None) -> None:
    held = _held(conn)
    ledger.post(conn, kind="warrant_hold", memo=f"{row['name']}: handed back", period=period,
                legs=[Leg(held, -row["units"], row["asset"]), Leg(row["account"], row["units"], row["asset"]),
                      Leg(held, -row["cash"]), Leg(row["account"], row["cash"])])
    conn.execute("UPDATE warrant_exercises SET status = %s WHERE id = %s", (status, row["id"]))


# ---------------------------------------------------------------------------
# At the quarter's close
# ---------------------------------------------------------------------------

def exercise_waiting(conn: Connection, period: int, now: datetime) -> dict:
    """Use every warrant handed in: new shares to the holder, the money to the company, the warrants back to it. Then the
    share price allows for the new shares, sold below it."""
    if not _ready(conn):
        return {}
    held = _held(conn)
    done: dict = {}
    for row in _rows(conn, "SELECT w.*, i.asset, i.name, i.shares_per, i.strike, i.company_id, i.expiry_period FROM warrant_exercises w"
                           " JOIN instruments i ON i.id = w.instrument_id WHERE w.status = 'waiting' ORDER BY w.id FOR UPDATE OF w"):
        company = _one(conn, "SELECT id, account_id, share_asset, name, status FROM companies WHERE id = %s", (row["company_id"],))
        if company["status"] != "trading" or row["expiry_period"] < period:
            _hand_back(conn, row, "cancelled", period)
            continue
        shares = row["units"] * row["shares_per"]
        ledger.post(conn, kind="share_issue", memo=f"{row['name']}: {row['units']:,} warrants used for {shares:,} new shares", period=period,
                    legs=[Leg(company["account_id"], -shares, company["share_asset"]), Leg(row["account"], shares, company["share_asset"]),
                          Leg(held, -row["units"], row["asset"]), Leg(company["account_id"], row["units"], row["asset"]),
                          Leg(held, -row["cash"]), Leg(company["account_id"], row["cash"])])
        conn.execute("UPDATE warrant_exercises SET status = 'done', period = %s WHERE id = %s", (period, row["id"]))
        was = done.get(company["id"], (0, 0))
        done[company["id"]] = (was[0] + row["cash"], was[1] + shares)
    for company_id, (raised, shares) in done.items():
        price = _one(conn, "SELECT coalesce(last_price, reference_price) AS p FROM market_instruments WHERE company_id = %s", (company_id,))
        if price and price["p"]:
            company = _one(conn, "SELECT share_asset FROM companies WHERE id = %s", (company_id,))
            in_issue = ledger.amount_in_existence(conn, company["share_asset"]) - shares
            new_price = (in_issue * price["p"] + raised) // max(in_issue + shares, 1)
            exchange.cancel_all_in(conn, company_id, now, "Handed back: new shares were issued for warrants used.")
            exchange.allow_index_for(conn, raised)
            exchange.reprice(conn, company_id, new_price, now,
                             f"{shares:,} new shares were issued for warrants used, at less than the market price. The price was "
                             f"adjusted from {money(price['p'])} to {money(new_price)}.")
    # Warrants whose last quarter has closed lapse; whatever is left of them is worth nothing.
    conn.execute("UPDATE instruments SET status = 'expired' WHERE kind = 'warrant' AND status = 'open' AND expiry_period <= %s", (period,))
    return done


def pay_preferred(conn: Connection, company: dict, most: int, period: int) -> int:
    """The preferred dividend, before the ordinary one, from a quarter's profit (`most` is what may be paid). A missed
    dividend is not made up later. Returns what was paid."""
    if not _ready(conn) or most <= 0:
        return 0
    paid = 0
    for inst in _rows(conn, "SELECT * FROM instruments WHERE company_id = %s AND kind = 'preferred' AND status = 'open'", (company["id"],)):
        holders = _rows(conn, "SELECT b.account_id, b.balance::bigint AS units FROM ledger_balances b WHERE b.asset = %s AND b.balance > 0"
                              " AND b.account_id <> %s ORDER BY b.account_id", (inst["asset"], company["account_id"]))
        units = sum(h["units"] for h in holders)
        due = units * inst["par"] * inst["dividend_bps"] // BPS // 4
        if due <= 0 or due > most - paid:
            continue
        legs = [Leg(h["account_id"], due * h["units"] // units) for h in holders]
        legs = [leg for leg in legs if leg.amount > 0]
        total = sum(leg.amount for leg in legs)
        if total:
            ledger.post(conn, kind="preferred_dividend", memo=f"{company['name']}: preferred dividend for {clock.period_label(period)}",
                        period=period, legs=[Leg(company["account_id"], -total), *legs])
            paid += total
    return paid


def after_split(conn: Connection, company_id, ratio: int) -> None:
    """A share split: each warrant buys as many more shares, at a price as much lower."""
    if _ready(conn):
        conn.execute("UPDATE instruments SET shares_per = shares_per * %s, strike = greatest(strike / %s, 1)"
                     " WHERE company_id = %s AND kind = 'warrant' AND status = 'open'", (ratio, ratio, company_id))


def check_books(conn: Connection) -> list[str]:
    if not _ready(conn):
        return []
    row = _one(conn, "SELECT id FROM ledger_accounts WHERE code = %s", (HELD,))
    if row is None:
        return []
    out = []
    cash = ledger.balance(conn, row["id"])
    owed = _one(conn, "SELECT coalesce(sum(cash), 0)::bigint AS c FROM warrant_exercises WHERE status = 'waiting'")["c"]
    if cash != owed:
        out.append(f"Cash held for warrants: {cash} held against {owed} recorded.")
    for r in _rows(conn, "SELECT i.asset, coalesce(sum(w.units), 0)::bigint AS units FROM instruments i LEFT JOIN warrant_exercises w"
                         " ON w.instrument_id = i.id AND w.status = 'waiting' WHERE i.kind = 'warrant' GROUP BY i.asset"):
        if ledger.balance(conn, row["id"], r["asset"]) != r["units"]:
            out.append(f"Warrants held for {r['asset']}: the records do not match.")
    return out


# ---------------------------------------------------------------------------
# What players see
# ---------------------------------------------------------------------------

def board(conn: Connection, now: datetime, account=None) -> dict:
    out = []
    dealer = _dealer(conn)
    for inst in _rows(conn, "SELECT i.*, c.ticker FROM instruments i JOIN companies c ON c.id = i.company_id WHERE i.status = 'open'"
                            " ORDER BY i.kind, c.ticker"):
        q = quote(conn, inst, now)
        out.append({"code": inst["asset"], "kind": inst["kind"], "ticker": inst["ticker"], "name": inst["name"], "fair": q["fair"],
                    "bid": q["bid"], "ask": q["ask"], "on_offer": ledger.balance(conn, dealer, inst["asset"]),
                    "dividend_bps": inst["dividend_bps"], "par": inst["par"], "strike": inst["strike"], "shares_per": inst["shares_per"],
                    "expiry": clock.period_label(inst["expiry_period"]) if inst["expiry_period"] else None,
                    "held": ledger.balance(conn, account, inst["asset"]) if account else 0})
    waiting = []
    if account:
        waiting = [{"id": w["id"], "name": w["name"], "units": w["units"], "cash": w["cash"]} for w in _rows(
            conn, "SELECT w.*, i.name FROM warrant_exercises w JOIN instruments i ON i.id = w.instrument_id WHERE w.account = %s"
                  " AND w.status = 'waiting' ORDER BY w.id", (account,))]
    return {"instruments": out, "waiting": waiting}


def _players_instruments(conn: Connection) -> dict:
    out: dict = {}
    if not _ready(conn):
        return out
    now = _one(conn, "SELECT now() AS n")["n"]
    for inst in _rows(conn, "SELECT * FROM instruments WHERE status = 'open'"):
        price = fair(conn, inst, now)
        for h in _rows(conn, "SELECT b.account_id, b.balance::bigint AS units FROM ledger_balances b JOIN ledger_accounts a ON a.id = b.account_id"
                             " WHERE b.asset = %s AND b.balance > 0 AND a.kind = 'player'", (inst["asset"],)):
            cash, inv = out.get(h["account_id"], (0, 0))
            out[h["account_id"]] = (cash, inv + h["units"] * price)
    for w in _rows(conn, "SELECT w.account, w.cash FROM warrant_exercises w JOIN ledger_accounts a ON a.id = w.account"
                         " WHERE w.status = 'waiting' AND a.kind = 'player'"):
        cash, inv = out.get(w["account"], (0, 0))
        out[w["account"]] = (cash + w["cash"], inv)
    return out


def _register() -> None:
    from simulation import marketview
    if _players_instruments not in marketview._OTHER_HOLDINGS:
        marketview._OTHER_HOLDINGS.append(_players_instruments)


_register()
