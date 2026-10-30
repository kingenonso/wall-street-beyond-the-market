"""The talent and funds stage, Part 4a: the currency desk and money from abroad.

Two rates for the naira:
  * the official rate, set by the Central Bank at each quarter's close. While it manages the naira it moves the rate a
    little towards the market each quarter, sells dollars from its reserves to hold the street close, and devalues when
    the gap grows too wide; when its reserves run too low it lets the naira float, and manages it again once they recover;
  * the street rate, where anybody can buy or sell at once: the market's rate, plus what a shortage of dollars adds, moved
    by the day's buying and selling. The gap between the two is public.

Dollars, pounds and euros are real money in the ledger. They come into existence only from the rest of the world (the
street's dollars are its dollars; families abroad send them home), and the Central Bank's reserves are the dollars it holds.
When it sells dollars it takes the naira paid for them out of existence; when it buys them it makes the naira.

Players and empires keep dollar, pound and euro balances, buy and sell them on the street at once, or ask the official
window for dollars, which are handed out in turn from a daily allocation, up to a limit a quarter. Dollars from the window
cannot be sold on the street for two quarters (buying cheap at the official rate to sell dear on the street is blocked:
crimes against the game are not allowed). Empires may run a bureau de change, or a company carrying money sent home.

Companies borrow in dollars too: their dollar debts are revalued every quarter at the official rate, and the loss (or gain)
is a line in their accounts. The Government and the largest companies issue Eurobonds, which players buy with dollars.
When dollars are short, foreign investors leaving wait in a backlog, which makes the rest more nervous.

Never sent to players: the Central Bank's next move, the street's secret daily swing, other players' balances and requests.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

from psycopg import Connection
from psycopg.rows import dict_row

from simulation import abroad, careers, clock, empires, ledger, stochastic
from simulation import world_data as data
from simulation.ledger import Leg
from simulation.money import BPS, apply_bps, naira

log = logging.getLogger(__name__)

CURRENCIES = tuple(c for c, _, _ in data.FX_CURRENCIES)
NAMES = {c: n for c, n, _ in data.FX_CURRENCIES}
SYMBOLS = {c: s for c, _, s in data.FX_CURRENCIES}
AGENT = "fx:agent"              # pays Eurobond holders
HELD = "fx:held"                # naira held for requests waiting at the official window
REMIT = "fx:remitters"          # the computer's money-transfer companies
BELLS_PER_QUARTER = data.INVEST_FUND_SESSIONS_PER_YEAR // 4


class FxError(Exception):
    pass


def _rows(conn: Connection, sql: str, params=()) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def _one(conn: Connection, sql: str, params=()) -> dict | None:
    rows = _rows(conn, sql, params)
    return rows[0] if rows else None


def ready(conn: Connection) -> bool:
    return bool(_one(conn, "SELECT to_regclass('fx_quarters') IS NOT NULL AS ok")["ok"])


def opened(conn: Connection) -> bool:
    return ready(conn) and _one(conn, "SELECT 1 AS x FROM fx_quarters LIMIT 1") is not None


def _seed(conn: Connection) -> str:
    return _one(conn, "SELECT fortune_seed FROM world_state")["fortune_seed"]


def _money(kobo: int) -> str:
    return f"₦{kobo / 100:,.2f}"


def _cash(cents: int, currency: str = "USD") -> str:
    return f"{SYMBOLS[currency]}{cents / 100:,.2f}"


def _rate_words(kobo: int) -> str:
    return f"₦{kobo / 100:,.2f}"


def to_naira(cents: int, rate: int) -> int:
    """Kobo for an amount of foreign currency (cents) at a rate (kobo for one unit)."""
    return cents * rate // 100


def to_cents(kobo: int, rate: int) -> int:
    return kobo * 100 // max(rate, 1)


# ---------------------------------------------------------------------------
# Opening the desk
# ---------------------------------------------------------------------------

def _account(conn: Connection, code: str, kind: str, name: str):
    row = _one(conn, "SELECT id FROM ledger_accounts WHERE code = %s", (code,))
    return row["id"] if row else ledger.create_account(conn, kind=kind, name=name, code=code)


def _quarter_imports(conn: Connection) -> int:
    """What companies buy abroad in a quarter (kobo): the last close's figure, or the opening one."""
    row = _one(conn, "SELECT imports, export_base FROM abroad_results ORDER BY period DESC LIMIT 1")
    return max((row["imports"] or row["export_base"]) if row else 1, 1)


def imports_usd(conn: Connection) -> int:
    """A quarter's imports in dollars (cents): the measure of the economy everything on the desk is sized against."""
    q = current(conn)
    rate = q["market"] if q else (_one(conn, "SELECT fx FROM abroad_results ORDER BY period DESC LIMIT 1") or {"fx": data.FX_START})["fx"]
    return max(to_cents(_quarter_imports(conn), rate), 1)


def setup(conn: Connection, now: datetime) -> bool:
    """The desk opens the first time the world meets it: the currencies, the Central Bank's reserves, the official rate,
    the money-transfer companies, the Government's first Eurobond and the largest companies' dollar debts."""
    if not ready(conn) or opened(conn):
        return False
    world_abroad, _ = abroad.accounts(conn)
    for code, name, _ in data.FX_CURRENCIES:
        if not _one(conn, "SELECT 1 AS x FROM assets WHERE code = %s", (code,)):
            ledger.create_asset(conn, code=code, kind="currency", name=name, unit="cent", issuer_account_id=world_abroad)
    _account(conn, AGENT, "escrow", "Eurobond paying agent")
    _account(conn, HELD, "escrow", "Naira held at the official window")
    _account(conn, REMIT, "npc_investors", "The computer's money-transfer companies")
    closed = _one(conn, "SELECT last_closed_period AS p FROM world_state")["p"]
    market = _one(conn, "SELECT fx FROM abroad_results ORDER BY period DESC LIMIT 1")["fx"]
    cb = ledger.account_id(conn, ledger.CENTRAL_BANK)
    imports_usd = to_cents(_quarter_imports(conn), market)
    reserves = imports_usd * data.FX_RESERVES_START_QUARTERS
    ledger.post(conn, kind="fx_abroad", memo="The Central Bank's dollar reserves", period=closed,
                legs=[Leg(world_abroad, -reserves, "USD"), Leg(cb, reserves, "USD")])
    conn.execute("INSERT INTO fx_quarters (period, official, market, regime, reserves, cover_bps, gbp_usd, eur_usd, words, at)"
                 " VALUES (%s, %s, %s, 'managed', %s, %s, %s, %s, %s, %s)",
                 (closed, market, market, reserves, reserves * BPS // max(imports_usd, 1), data.FX_GBP_USD_START, data.FX_EUR_USD_START,
                  "The currency desk opens: the Central Bank manages the naira at the market's rate.", now))
    for name, fee, days in data.FX_COMPUTER_REMITTERS:
        conn.execute("INSERT INTO remitters (name, fee_bps, days, licensed_at) VALUES (%s, %s, %s, %s)", (name, fee, days, now))
    _issue_government(conn, closed, now, first=True)
    _issue_companies(conn, closed, now)
    return True


# ---------------------------------------------------------------------------
# The rates
# ---------------------------------------------------------------------------

def current(conn: Connection) -> dict | None:
    return _one(conn, "SELECT * FROM fx_quarters ORDER BY period DESC LIMIT 1")


def _last_day(conn: Connection) -> dict | None:
    return _one(conn, "SELECT * FROM fx_days ORDER BY session_date DESC LIMIT 1")


def official(conn: Connection) -> int:
    """Kobo for one dollar at the official window now. A floating naira's official rate follows the street each day."""
    q = current(conn)
    if q is None:
        return data.FX_START
    if q["regime"] == "float":
        d = _last_day(conn)
        if d and d["at"] >= q["at"]:
            return d["official"]
    return q["official"]


def official_for(conn: Connection, period: int) -> int:
    """The official rate in force during a quarter (set at the close before it), for settling currency forwards."""
    row = _one(conn, "SELECT official FROM fx_quarters WHERE period = %s", (period - 1,)) or current(conn)
    return row["official"] if row else data.FX_START


def expected_official(conn: Connection) -> int:
    """Where the official rate is heading at the coming close, by the Central Bank's published rules and the figures everybody
    can see: a bank prices a currency forward from this, not from today's rate."""
    q = current(conn)
    if q is None:
        return data.FX_START
    cover = ledger.balance(conn, ledger.account_id(conn, ledger.CENTRAL_BANK), "USD") * BPS // imports_usd(conn)   # (as it stands today)
    if q["regime"] == "float" or cover < data.FX_FLOAT_COVER_BPS:
        return street(conn)
    gap = q["market"] * BPS // max(q["official"], 1) - BPS
    if gap >= data.FX_DEVALUE_GAP_BPS and cover < data.FX_COMFORT_COVER_BPS:
        return q["market"]
    return q["official"] + (q["market"] - q["official"]) * data.FX_CRAWL_BPS // BPS


def _impact(conn: Connection) -> int:
    row = _one(conn, "SELECT impact_bps FROM fx_street WHERE id = 1")
    return row["impact_bps"] if row else 0


def _shortage_bps(q: dict) -> int:
    return max(data.FX_COMFORT_COVER_BPS - q["cover_bps"], 0) * data.FX_SHORTAGE_PREMIUM_BPS // BPS


def _backlog_bps(conn: Connection, q: dict) -> int:
    if q["backlog"] <= 0:
        return 0
    usual = max(abs(_one(conn, "SELECT coalesce(avg(abs(foreign_inflow)), 0)::bigint AS a FROM abroad_results WHERE period >= 1")["a"]), 1)
    return min(q["backlog"] * data.FX_BACKLOG_PREMIUM_BPS // usual, data.FX_BACKLOG_PREMIUM_BPS)


def _street_base(conn: Connection, q: dict, noise_bps: int) -> int:
    """The street's middle rate before today's deals move it."""
    if q["regime"] == "float":
        return q["market"] * (BPS + data.FX_FLOAT_PREMIUM_BPS + noise_bps) // BPS
    return max(q["market"], q["official"]) * (BPS + _shortage_bps(q) + _backlog_bps(conn, q) + noise_bps) // BPS


def street(conn: Connection) -> int:
    """The street's middle rate now (kobo for one dollar): the last bell's, moved by the deals made since."""
    d = _last_day(conn)
    q = current(conn)
    if q is None:
        return data.FX_START
    base = d["street"] if d and d["at"] >= q["at"] else _street_base(conn, q, 0)
    return max(base * (BPS + _impact(conn)) // BPS, 1)


def cross(conn: Connection, currency: str) -> float:
    """Dollars for one unit of the currency."""
    if currency == "USD":
        return 1.0
    d = _last_day(conn)
    q = current(conn)
    src = d if d and q and d["at"] >= q["at"] else q
    if src is None:
        return data.FX_GBP_USD_START if currency == "GBP" else data.FX_EUR_USD_START
    return float(src["gbp_usd"] if currency == "GBP" else src["eur_usd"])


def quote(conn: Connection, currency: str) -> dict:
    """The street's prices for a currency: its middle rate, what it sells at, what it buys at (kobo for one unit)."""
    if currency not in CURRENCIES:
        raise FxError("Choose dollars, pounds or euros.")
    mid = round(street(conn) * cross(conn, currency))
    return {"currency": currency, "mid": mid, "sell": mid * (BPS + data.FX_STREET_SPREAD_BPS) // BPS,
            "buy": mid * (BPS - data.FX_STREET_SPREAD_BPS) // BPS}


def _move_street(conn: Connection, cents_usd: int) -> None:
    """Buying dollars on the street pushes it up; selling pushes it down."""
    move = cents_usd * 100 // max(apply_bps(imports_usd(conn), data.FX_STREET_DEPTH_BPS), 1)
    conn.execute("UPDATE fx_street SET impact_bps = greatest(least(impact_bps + %s, %s), %s) WHERE id = 1",
                 (move, data.FX_STREET_MOST_IMPACT_BPS, -data.FX_STREET_MOST_IMPACT_BPS))


# ---------------------------------------------------------------------------
# Who is dealing
# ---------------------------------------------------------------------------

def _acting(conn: Connection, player_id, for_empire: bool) -> tuple:
    """(account, empire or None). For an empire, its head or its Investment Banker deals."""
    if not for_empire:
        account = ledger.player_account_id(conn, player_id)
        if account is None:
            raise FxError("You need an account first.")
        return account, None
    seat = empires.seat_of(conn, player_id)
    if seat is None or seat["empire_status"] != "active" or seat["empire_kind"] == "pension":
        raise FxError("You hold no seat in an open empire.")
    empire = empires._empire(conn, seat["empire_id"])
    if empire["head_player_id"] != player_id and seat["build"] != "investment_banker":
        raise FxError("The head or the Investment Banker deals in currencies for the empire.")
    return empire["account_id"], empire


def _whole(value, least: int = 1, most: int | None = None) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= least and (most is None or value <= most)


def _period(conn: Connection, now: datetime) -> int:
    return careers.world_now(conn, now)["period"]


def _record(conn: Connection, account, venue: str, side: str, currency: str, amount: int, rate: int, kobo: int, period: int,
            now: datetime, bdc_id=None) -> int:
    return _one(conn, "INSERT INTO fx_trades (account_id, venue, bdc_id, side, currency, amount, rate, naira, period, at)"
                      " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
                (account, venue, bdc_id, side, currency, amount, rate, max(kobo, 1), period, now))["id"]


def kept_from_window(conn: Connection, account, period: int) -> int:
    """Dollars an account bought at the official window in this quarter and the one before, less what it sold back to it:
    these may not be sold on the street (or to a bureau)."""
    row = _one(conn, "SELECT coalesce(sum(CASE WHEN side = 'buy' THEN amount ELSE -amount END), 0)::bigint AS n FROM fx_trades"
                     " WHERE account_id = %s AND venue = 'window' AND period > %s", (account, period - data.FX_WINDOW_KEEP_QUARTERS))
    return max(row["n"], 0)


def _sellable(conn: Connection, account, currency: str, period: int) -> int:
    have = ledger.balance(conn, account, currency)
    return max(have - kept_from_window(conn, account, period), 0) if currency == "USD" else have


# ---------------------------------------------------------------------------
# The street: at once, at the street's prices
# ---------------------------------------------------------------------------

def street_deal(conn: Connection, player_id, side: str, currency: str, amount: int, now: datetime, *, for_empire: bool = False) -> dict:
    """Buy or sell foreign currency on the street at once."""
    if side not in ("buy", "sell"):
        raise FxError("Buy or sell.")
    if not _whole(amount, data.FX_LEAST_CENTS, data.FX_STREET_MOST_DEAL_CENTS):
        raise FxError(f"Deal between {_cash(data.FX_LEAST_CENTS)} and {_cash(data.FX_STREET_MOST_DEAL_CENTS)} at a time.")
    with conn.transaction():
        if not opened(conn):
            raise FxError("The currency desk opens at the next closing bell.")
        account, _ = _acting(conn, player_id, for_empire)
        period = _period(conn, now)
        conn.execute("SELECT id FROM fx_street WHERE id = 1 FOR UPDATE")
        q = quote(conn, currency)
        world_abroad, _ = abroad.accounts(conn)
        usd = round(amount * cross(conn, currency))
        if side == "buy":
            rate = q["sell"]
            cost = -(-amount * rate // 100)
            if ledger.balance(conn, account) < cost:
                raise FxError(f"That costs {_money(cost)}.")
            ledger.post(conn, kind="fx_abroad", memo=f"Bought {_cash(amount, currency)} on the street", period=period,
                        legs=[Leg(account, -cost), Leg(world_abroad, cost), Leg(world_abroad, -amount, currency), Leg(account, amount, currency)])
            _move_street(conn, usd)
            kobo = cost
        else:
            if _sellable(conn, account, currency, period) < amount:
                kept = kept_from_window(conn, account, period) if currency == "USD" else 0
                raise FxError("You do not have that much to sell" + (f" ({_cash(kept)} came from the official window in the last two quarters"
                                                                     " and may only be sold back to it)" if kept else "") + ".")
            rate = q["buy"]
            kobo = amount * rate // 100
            if ledger.balance(conn, world_abroad) < kobo:
                raise FxError("The street has no naira for that much today.")
            ledger.post(conn, kind="fx_abroad", memo=f"Sold {_cash(amount, currency)} on the street", period=period,
                        legs=[Leg(account, -amount, currency), Leg(world_abroad, amount, currency), Leg(world_abroad, -kobo), Leg(account, kobo)])
            _move_street(conn, -usd)
        _record(conn, account, "street", side, currency, amount, rate, kobo, period, now)
        return {"side": side, "currency": currency, "amount": amount, "rate": rate, "naira": kobo}


# ---------------------------------------------------------------------------
# The official window: dollars at the official rate, in turn, up to a limit a quarter
# ---------------------------------------------------------------------------

def _window_limit(empire) -> int:
    return data.FX_WINDOW_LIMIT_EMPIRE_CENTS if empire else data.FX_WINDOW_LIMIT_PLAYER_CENTS


def _window_used(conn: Connection, account, period: int) -> int:
    """What counts against the quarter's limit: every request still open or filled, and what was filled of any withdrawn."""
    return _one(conn, "SELECT coalesce(sum(CASE WHEN status = 'cancelled' THEN filled ELSE amount END), 0)::bigint AS n FROM fx_window"
                      " WHERE account_id = %s AND period = %s", (account, period))["n"]


def _runs_bdc(conn: Connection, account) -> bool:
    return _one(conn, "SELECT 1 AS x FROM bdcs b JOIN empires e ON e.id = b.empire_id WHERE e.account_id = %s AND b.status = 'open'",
                (account,)) is not None


def window_ask(conn: Connection, player_id, amount: int, now: datetime, *, for_empire: bool = False) -> dict:
    """Ask the official window for dollars. The naira for them (and a tenth more, in case the rate moves) is held until
    the request is filled, in turn, from the Central Bank's daily allocation."""
    if not _whole(amount, data.FX_LEAST_CENTS):
        raise FxError(f"Ask for at least {_cash(data.FX_LEAST_CENTS)}.")
    with conn.transaction():
        if not opened(conn):
            raise FxError("The currency desk opens at the next closing bell.")
        account, empire = _acting(conn, player_id, for_empire)
        conn.execute("SELECT id FROM ledger_accounts WHERE id = %s FOR UPDATE", (account,))   # one request at a time per account
        if _runs_bdc(conn, account):
            raise FxError("A bureau de change buys its dollars on the street, not at the official window.")
        period = _period(conn, now)
        used = _window_used(conn, account, period)
        limit = _window_limit(empire)
        if used + amount > limit:
            raise FxError(f"The official window gives at most {_cash(limit)} a quarter ({_cash(max(limit - used, 0))} is left this quarter).")
        hold = -(-to_naira(amount, official(conn)) * (BPS + data.FX_WINDOW_HOLD_EXTRA_BPS) // BPS)
        if ledger.balance(conn, account) < hold:
            raise FxError(f"Asking for that holds {_money(hold)} until it is filled.")
        ledger.transfer(conn, payer=account, receiver=ledger.account_id(conn, HELD), amount=hold, kind="fx_window_hold",
                        memo=f"Held for {_cash(amount)} asked of the official window", period=period)
        row = _one(conn, "INSERT INTO fx_window (account_id, amount, held, period, placed_at) VALUES (%s, %s, %s, %s, %s) RETURNING id",
                   (account, amount, hold, period, now))
        ahead = _one(conn, "SELECT count(*) AS n FROM fx_window WHERE status = 'waiting' AND id < %s", (row["id"],))["n"]
        return {"request_id": row["id"], "held": hold, "place": ahead + 1}


def _release_window(conn: Connection, req: dict, status: str, now: datetime, period: int) -> None:
    if req["held"] > 0:
        ledger.transfer(conn, payer=ledger.account_id(conn, HELD), receiver=req["account_id"], amount=req["held"], kind="fx_window_release",
                        memo="Naira handed back from the official window", period=period)
    conn.execute("UPDATE fx_window SET status = %s, held = 0, closed_at = %s WHERE id = %s", (status, now, req["id"]))


def window_cancel(conn: Connection, player_id, request_id: int, now: datetime, *, for_empire: bool = False) -> dict:
    with conn.transaction():
        account, _ = _acting(conn, player_id, for_empire)
        req = _one(conn, "SELECT * FROM fx_window WHERE id = %s AND account_id = %s FOR UPDATE", (request_id, account))
        if req is None or req["status"] != "waiting":
            raise FxError("There is no waiting request of yours by that number.")
        _release_window(conn, req, "cancelled", now, _period(conn, now))
        return {"cancelled": request_id}


def _fill_window(conn: Connection, now: datetime, period: int) -> int:
    """At a bell: the Central Bank hands out its daily allocation to the requests waiting, oldest first."""
    q = current(conn)
    cb = ledger.account_id(conn, ledger.CENTRAL_BANK)
    if q["regime"] == "float":
        allocation = 10 ** 15                           # a floating naira: the window sells whatever is asked, at the street's rate
    else:
        allocation = apply_bps(ledger.balance(conn, cb, "USD"), data.FX_WINDOW_DAILY_BPS)
    rate = official(conn)
    paid = 0
    held = ledger.account_id(conn, HELD)
    for req in _rows(conn, "SELECT * FROM fx_window WHERE status = 'waiting' ORDER BY id FOR UPDATE"):
        if allocation <= 0:
            break
        give = min(req["amount"] - req["filled"], allocation, ledger.balance(conn, cb, "USD"))
        cost = -(-to_naira(give, rate) // 1)
        if cost > req["held"]:
            give = req["held"] * 100 // rate
            cost = to_naira(give, rate)
        if give <= 0:
            continue
        ledger.post(conn, kind="fx_reserves", memo=f"{_cash(give)} from the official window", period=period,
                    legs=[Leg(held, -cost), Leg(cb, cost), Leg(cb, -give, "USD"), Leg(req["account_id"], give, "USD")])
        _record(conn, req["account_id"], "window", "buy", "USD", give, rate, cost, period, now)
        filled = req["filled"] + give
        conn.execute("UPDATE fx_window SET filled = %s, held = held - %s WHERE id = %s", (filled, cost, req["id"]))
        allocation -= give
        paid += give
        if filled >= req["amount"]:
            _release_window(conn, {**req, "held": req["held"] - cost}, "filled", now, period)
            _alert(conn, kind="window", account=req["account_id"], now=now, headline=f"Your {_cash(req['amount'])} from the official window is ready",
                   words=f"The Central Bank handed it out at {_rate_words(rate)} a dollar. Dollars from the window may not be sold on the street"
                         " for two quarters.")
    return paid


def window_sell(conn: Connection, player_id, amount: int, now: datetime, *, for_empire: bool = False) -> dict:
    """Sell dollars to the Central Bank at the official rate, at once (it always buys)."""
    if not _whole(amount, data.FX_LEAST_CENTS):
        raise FxError(f"Sell at least {_cash(data.FX_LEAST_CENTS)}.")
    with conn.transaction():
        if not opened(conn):
            raise FxError("The currency desk opens at the next closing bell.")
        account, _ = _acting(conn, player_id, for_empire)
        if ledger.balance(conn, account, "USD") < amount:
            raise FxError("You do not have that many dollars.")
        period = _period(conn, now)
        rate = official(conn) * (BPS - data.FX_WINDOW_BUYBACK_BPS) // BPS
        kept = kept_from_window(conn, account, period)
        if kept > 0:
            # Dollars the window sold in the last two quarters come back no dearer than they were bought (no bet on a devaluation
            # through the window).
            paid = _one(conn, "SELECT coalesce(sum(naira), 0)::bigint AS k, coalesce(sum(amount), 0)::bigint AS c FROM fx_trades"
                              " WHERE account_id = %s AND venue = 'window' AND side = 'buy' AND period > %s",
                        (account, period - data.FX_WINDOW_KEEP_QUARTERS))
            if paid["c"] > 0:
                rate = min(rate, paid["k"] * 100 // paid["c"])
        kobo = to_naira(amount, rate)
        cb = ledger.account_id(conn, ledger.CENTRAL_BANK)
        ledger.post(conn, kind="fx_reserves", memo=f"Sold {_cash(amount)} to the official window", period=period,
                    legs=[Leg(account, -amount, "USD"), Leg(cb, amount, "USD"), Leg(cb, -kobo), Leg(account, kobo)])
        _record(conn, account, "window", "sell", "USD", amount, rate, kobo, period, now)
        return {"amount": amount, "rate": rate, "naira": kobo}


# ---------------------------------------------------------------------------
# Bureaux de change, run by empires
# ---------------------------------------------------------------------------

def _head_empire(conn: Connection, player_id) -> dict:
    seat = empires.seat_of(conn, player_id)
    if seat is None or seat["empire_status"] != "active" or seat["empire_kind"] == "pension":
        raise FxError("You hold no seat in an open empire.")
    empire = empires._empire(conn, seat["empire_id"])
    if empire["head_player_id"] != player_id:
        raise FxError("Only the head of the empire can do that.")
    return empire


def _spreads_ok(buy_bps, sell_bps) -> None:
    if not _whole(buy_bps, 0, 1000) or not _whole(sell_bps, 0, 1000):
        raise FxError("Set how far below and above the street's middle rate you buy and sell: 0% to 10%.")


def open_bdc(conn: Connection, player_id, name: str, buy_bps: int, sell_bps: int, now: datetime) -> dict:
    name = " ".join((name or "").split())[:60]
    if len(name) < 3:
        raise FxError("Give the bureau a name.")
    _spreads_ok(buy_bps, sell_bps)
    with conn.transaction():
        if not opened(conn):
            raise FxError("The currency desk opens at the next closing bell.")
        empire = _head_empire(conn, player_id)
        if _one(conn, "SELECT 1 AS x FROM bdcs WHERE empire_id = %s AND status = 'open'", (empire["id"],)):
            raise FxError("Your empire already runs a bureau de change.")
        if _one(conn, "SELECT 1 AS x FROM fx_window WHERE account_id = %s AND status = 'waiting'", (empire["account_id"],)):
            raise FxError("Withdraw the empire's requests at the official window first: a bureau buys on the street.")
        if kept_from_window(conn, empire["account_id"], _period(conn, now)) > 0:
            raise FxError("The empire holds dollars from the official window. A bureau may not sell those: sell them back to the window first,"
                          " or wait two quarters.")
        fee = naira(data.FX_BDC_LICENCE_NAIRA)
        if ledger.balance(conn, empire["account_id"]) < naira(data.FX_BDC_LEAST_CAPITAL_NAIRA) + fee:
            raise FxError(f"A bureau needs {_money(naira(data.FX_BDC_LEAST_CAPITAL_NAIRA))} behind it, and {_money(fee)} for its licence.")
        period = _period(conn, now)
        ledger.transfer(conn, payer=empire["account_id"], receiver=ledger.account_id(conn, ledger.TREASURY), amount=fee, kind="fx_licence",
                        memo=f"{name}: licence of a bureau de change", period=period)
        row = _one(conn, "INSERT INTO bdcs (empire_id, name, buy_bps, sell_bps, licensed_at) VALUES (%s, %s, %s, %s, %s) RETURNING id",
                   (empire["id"], name, buy_bps, sell_bps, now))
        empires._log(conn, empire["id"], f"Opened {name}, a bureau de change.", now)
        return {"bdc_id": row["id"]}


def price_bdc(conn: Connection, player_id, buy_bps: int, sell_bps: int, now: datetime) -> dict:
    _spreads_ok(buy_bps, sell_bps)
    with conn.transaction():
        empire = _head_empire(conn, player_id)
        row = _one(conn, "UPDATE bdcs SET buy_bps = %s, sell_bps = %s WHERE empire_id = %s AND status = 'open' RETURNING id",
                   (buy_bps, sell_bps, empire["id"]))
        if row is None:
            raise FxError("Your empire runs no bureau de change.")
        return {"bdc_id": row["id"]}


def close_bdc(conn: Connection, player_id, now: datetime) -> dict:
    with conn.transaction():
        empire = _head_empire(conn, player_id)
        row = _one(conn, "UPDATE bdcs SET status = 'closed', closed_at = %s WHERE empire_id = %s AND status = 'open' RETURNING id",
                   (now, empire["id"]))
        if row is None:
            raise FxError("Your empire runs no bureau de change.")
        return {"bdc_id": row["id"]}


def _bdc_prices(conn: Connection, b: dict) -> dict:
    mid = street(conn)
    return {"buy": mid * (BPS - b["buy_bps"]) // BPS, "sell": mid * (BPS + b["sell_bps"]) // BPS}


def _report(conn: Connection, bdc_id, trade_id, customer: str, amount: int, kobo: int, now: datetime) -> None:
    if amount >= data.FX_BDC_REPORT_CENTS:
        conn.execute("INSERT INTO bdc_reports (bdc_id, trade_id, customer, amount, naira, at) VALUES (%s, %s, %s, %s, %s, %s)",
                     (bdc_id, trade_id, customer, amount, kobo, now))


def bdc_deal(conn: Connection, player_id, bdc_id: int, side: str, amount: int, now: datetime, *, for_empire: bool = False) -> dict:
    """Buy dollars from (or sell them to) a player's bureau, at its prices. Every deal of $10,000 or more is reported."""
    if side not in ("buy", "sell"):
        raise FxError("Buy or sell.")
    if not _whole(amount, data.FX_LEAST_CENTS, data.FX_BDC_MOST_DEAL_CENTS):
        raise FxError(f"A bureau deals between {_cash(data.FX_LEAST_CENTS)} and {_cash(data.FX_BDC_MOST_DEAL_CENTS)} at a time.")
    with conn.transaction():
        account, _ = _acting(conn, player_id, for_empire)
        b = _one(conn, "SELECT b.*, e.account_id AS bdc_account FROM bdcs b JOIN empires e ON e.id = b.empire_id WHERE b.id = %s"
                       " AND b.status = 'open' FOR UPDATE OF b", (bdc_id,))
        if b is None:
            raise FxError("That bureau is not open.")
        if b["bdc_account"] == account or _one(conn, "SELECT 1 AS x FROM empire_seats s JOIN ledger_accounts a ON a.player_id = s.player_id"
                                                      " WHERE s.empire_id = %s AND a.id = %s", (b["empire_id"], account)):
            raise FxError("A bureau does not deal with its own empire or its members.")
        period = _period(conn, now)
        prices = _bdc_prices(conn, b)
        refused = "That bureau cannot take that deal now. Try a smaller amount, or another bureau."
        if side == "buy":
            rate = prices["sell"]
            cost = -(-amount * rate // 100)
            if _sellable(conn, b["bdc_account"], "USD", period) < amount:
                raise FxError(refused)
            if ledger.balance(conn, account) < cost:
                raise FxError(f"That costs {_money(cost)}.")
            ledger.post(conn, kind="fx_bdc", memo=f"Bought {_cash(amount)} from {b['name']}", period=period,
                        legs=[Leg(account, -cost), Leg(b["bdc_account"], cost), Leg(b["bdc_account"], -amount, "USD"), Leg(account, amount, "USD")])
            kobo = cost
        else:
            if _sellable(conn, account, "USD", period) < amount:
                raise FxError("You do not have that many dollars to sell (dollars from the official window may only be sold back to it).")
            rate = prices["buy"]
            kobo = amount * rate // 100
            if ledger.balance(conn, b["bdc_account"]) < kobo:
                raise FxError(refused)
            ledger.post(conn, kind="fx_bdc", memo=f"Sold {_cash(amount)} to {b['name']}", period=period,
                        legs=[Leg(account, -amount, "USD"), Leg(b["bdc_account"], amount, "USD"), Leg(b["bdc_account"], -kobo), Leg(account, kobo)])
        trade = _record(conn, account, "bdc", side, "USD", amount, rate, kobo, period, now, bdc_id=b["id"])
        kind = _one(conn, "SELECT kind FROM ledger_accounts WHERE id = %s", (account,))["kind"]
        _report(conn, b["id"], trade, "an empire" if kind == "empire" else "a player", amount, kobo, now)
        return {"side": side, "amount": amount, "rate": rate, "naira": kobo}


def _retail(conn: Connection, day: date, now: datetime, period: int) -> int:
    """At a bell: households' own dealing in dollars, through the street's bureaux. Players' bureaux win the share their
    prices earn (at most 60%); the rest goes to the street. Returns the dollars households bought, net."""
    bdcs = _rows(conn, "SELECT b.*, e.account_id AS bdc_account FROM bdcs b JOIN empires e ON e.id = b.empire_id WHERE b.status = 'open'"
                       " ORDER BY b.id")
    if not bdcs:
        return 0
    households = ledger.account_id(conn, "households:lagos")
    each_side = apply_bps(imports_usd(conn), data.FX_RETAIL_DAILY_BPS) // 2
    street_score = 1 / (data.FX_STREET_SPREAD_BPS + 20)
    for side, spread_key in (("buy", "sell_bps"), ("sell", "buy_bps")):
        scores = [1 / (b[spread_key] + 20) for b in bdcs]
        total = sum(scores) + street_score
        players_share = min(sum(scores) / total, data.FX_RETAIL_TO_PLAYERS_MOST_BPS / BPS)
        for b, sc in zip(bdcs, scores):
            amount = int(each_side * players_share * sc / max(sum(scores), 1e-9))
            if amount < data.FX_LEAST_CENTS:
                continue
            prices = _bdc_prices(conn, b)
            if side == "buy":                         # households buy dollars from the bureau (never dollars from the official window)
                amount = min(amount, _sellable(conn, b["bdc_account"], "USD", period))
                kobo = amount * prices["sell"] // 100
                if amount < data.FX_LEAST_CENTS or ledger.balance(conn, households) < kobo:
                    continue
                world_abroad, _ = abroad.accounts(conn)
                ledger.post(conn, kind="fx_abroad", memo=f"Households bought dollars from {b['name']}", period=period,
                            legs=[Leg(households, -kobo), Leg(b["bdc_account"], kobo), Leg(b["bdc_account"], -amount, "USD"),
                                  Leg(world_abroad, amount, "USD")])
                rate = prices["sell"]
            else:                                     # families sell dollars sent from abroad to the bureau
                kobo = amount * prices["buy"] // 100
                if ledger.balance(conn, b["bdc_account"]) < kobo:
                    amount = ledger.balance(conn, b["bdc_account"]) * 100 // max(prices["buy"], 1)
                    kobo = amount * prices["buy"] // 100
                if amount < data.FX_LEAST_CENTS:
                    continue
                world_abroad, _ = abroad.accounts(conn)
                ledger.post(conn, kind="fx_abroad", memo=f"Households sold dollars to {b['name']}", period=period,
                            legs=[Leg(world_abroad, -amount, "USD"), Leg(b["bdc_account"], amount, "USD"), Leg(b["bdc_account"], -kobo),
                                  Leg(households, kobo)])
                rate = prices["buy"]
            _report(conn, b["id"], None, "households", amount, kobo, now)
            conn.execute("INSERT INTO fx_trades (account_id, venue, bdc_id, side, currency, amount, rate, naira, period, at)"
                         " VALUES (%s, 'bdc', %s, %s, 'USD', %s, %s, %s, %s, %s)", (households, b["id"], side, amount, rate, max(kobo, 1), period, now))
    return 0


# ---------------------------------------------------------------------------
# Money sent home from abroad, carried by money-transfer companies
# ---------------------------------------------------------------------------

def open_remitter(conn: Connection, player_id, name: str, fee_bps: int, days: int, now: datetime) -> dict:
    name = " ".join((name or "").split())[:60]
    if len(name) < 3:
        raise FxError("Give the company a name.")
    if not _whole(fee_bps, 0, 1500) or not _whole(days, 0, 5):
        raise FxError("Set a fee of 0% to 15% and a speed of 0 to 5 days.")
    with conn.transaction():
        if not opened(conn):
            raise FxError("The currency desk opens at the next closing bell.")
        empire = _head_empire(conn, player_id)
        if _one(conn, "SELECT 1 AS x FROM remitters WHERE empire_id = %s AND status = 'open'", (empire["id"],)):
            raise FxError("Your empire already runs a money-transfer company.")
        fee = naira(data.FX_REMIT_LICENCE_NAIRA)
        if ledger.balance(conn, empire["account_id"]) < fee:
            raise FxError(f"The licence costs {_money(fee)}.")
        ledger.transfer(conn, payer=empire["account_id"], receiver=ledger.account_id(conn, ledger.TREASURY), amount=fee, kind="fx_licence",
                        memo=f"{name}: licence to carry money from abroad", period=_period(conn, now))
        row = _one(conn, "INSERT INTO remitters (empire_id, name, fee_bps, days, licensed_at) VALUES (%s, %s, %s, %s, %s) RETURNING id",
                   (empire["id"], name, fee_bps, days, now))
        empires._log(conn, empire["id"], f"Opened {name}, carrying money sent home from abroad.", now)
        return {"remitter_id": row["id"]}


def set_remitter(conn: Connection, player_id, fee_bps: int, days: int, now: datetime) -> dict:
    if not _whole(fee_bps, 0, 1500) or not _whole(days, 0, 5):
        raise FxError("Set a fee of 0% to 15% and a speed of 0 to 5 days.")
    with conn.transaction():
        empire = _head_empire(conn, player_id)
        row = _one(conn, "UPDATE remitters SET fee_bps = %s, days = %s WHERE empire_id = %s AND status = 'open' RETURNING id",
                   (fee_bps, days, empire["id"]))
        if row is None:
            raise FxError("Your empire runs no money-transfer company.")
        return {"remitter_id": row["id"]}


def close_remitter(conn: Connection, player_id, now: datetime) -> dict:
    with conn.transaction():
        empire = _head_empire(conn, player_id)
        row = _one(conn, "UPDATE remitters SET status = 'closed', closed_at = %s WHERE empire_id = %s AND status = 'open' RETURNING id",
                   (now, empire["id"]))
        if row is None:
            raise FxError("Your empire runs no money-transfer company.")
        return {"remitter_id": row["id"]}


def _remitter_score(r: dict) -> float:
    """How families choose: cheap first, then fast."""
    return 1 / (r["fee_bps"] + 50 + r["days"] * 40)


def remitted_today(conn: Connection, period: int, premium_bps: int) -> int:
    """Dollars sent home at one bell: the quarter's usual amount spread over its days, more at Easter and Christmas, more
    when the street pays more naira for them, and growing each year."""
    _, quarter = clock.period_to_date(max(period, 1))
    years = max(period - 1, 0) / 4
    base = apply_bps(imports_usd(conn), data.FX_REMIT_IMPORTS_BPS) / BELLS_PER_QUARTER
    festive = data.FX_REMIT_FESTIVE.get(quarter, 1.0)
    cheap = 1 + max(premium_bps, 0) * data.FX_REMIT_CHEAP_BPS / BPS / BPS
    growth = (1 + data.FX_REMIT_GROWTH_BPS / BPS) ** years
    return int(base * festive * cheap * growth)


def _remit(conn: Connection, day: date, now: datetime, period: int, premium_bps: int) -> int:
    """At a bell: what families abroad sent, carried by the money-transfer companies (split by fee and speed) and paid out
    in naira at the street's rate. The dollars stay with the street, so they ease it."""
    total = remitted_today(conn, period, premium_bps)
    open_ = _rows(conn, "SELECT r.*, e.account_id AS empire_account FROM remitters r LEFT JOIN empires e ON e.id = r.empire_id"
                        " WHERE r.status = 'open' ORDER BY r.id")
    if not open_ or total <= 0:
        return 0
    scores = [_remitter_score(r) for r in open_]
    whole = sum(scores)
    world_abroad, _ = abroad.accounts(conn)
    households = ledger.account_id(conn, "households:lagos")
    computer = ledger.account_id(conn, REMIT)
    mid = street(conn)
    sent = 0
    for r, sc in zip(open_, scores):
        dollars = int(total * sc / whole)
        kobo = dollars * mid // 100
        fee = apply_bps(kobo, r["fee_bps"])
        cost = apply_bps(kobo, max(5 - r["days"], 0) * data.FX_REMIT_COST_PER_FAST_DAY_BPS)
        if kobo <= 0 or ledger.balance(conn, world_abroad) < kobo:
            continue
        carrier = r["empire_account"] or computer
        ledger.post(conn, kind="remittance", memo=f"Money sent home from abroad through {r['name']}", period=period,
                    legs=[Leg(world_abroad, -kobo), Leg(households, kobo - fee), Leg(carrier, fee)])
        if cost > 0:
            ledger.pay_up_to(conn, payer=carrier, receiver=world_abroad, wanted=cost, kind="remittance_cost",
                             memo=f"{r['name']}: what its speed cost", period=period)
        conn.execute("INSERT INTO remittances (remitter_id, session_date, dollars, naira, fee, cost) VALUES (%s, %s, %s, %s, %s, %s)"
                     " ON CONFLICT DO NOTHING", (r["id"], day, dollars, kobo - fee, fee, cost))
        sent += dollars
    _move_street(conn, -sent)
    return sent


# ---------------------------------------------------------------------------
# Eurobonds: the Government's and the largest companies' dollar bonds
# ---------------------------------------------------------------------------

def _eurobond_asset(conn: Connection, prefix: str) -> str:
    n = _one(conn, "SELECT count(*) AS n FROM eurobonds")["n"] + 1
    return f"EUB-{prefix}{n}"


def _new_eurobond(conn: Connection, *, name: str, issuer: str, company: dict | None, amount: int, coupon_bps: int, period: int,
                  debt_id=None) -> dict:
    agent = ledger.account_id(conn, AGENT)
    world_abroad, _ = abroad.accounts(conn)
    asset = _eurobond_asset(conn, company["ticker"] if company else "FGN")
    ledger.create_asset(conn, code=asset, kind="bond", name=name, unit="bond", issuer_account_id=agent)
    units = amount // data.FX_EUROBOND_FACE_CENTS
    eb = _one(conn, "INSERT INTO eurobonds (asset, name, issuer, company_id, debt_id, face, coupon_bps, issued_period, maturity_period, units)"
                    " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING *",
              (asset, name, issuer, company["id"] if company else None, debt_id, data.FX_EUROBOND_FACE_CENTS, coupon_bps, period,
               period + data.FX_EUROBOND_TERM_QUARTERS, units))
    # Foreign investors buy the whole issue (players buy from them later, with dollars).
    ledger.post(conn, kind="eurobond_issue", memo=f"{name}: issued", period=period,
                legs=[Leg(agent, -units, asset), Leg(world_abroad, units, asset)])
    return eb


def _sell_dollars_to_reserves(conn: Connection, account, cents: int, rate: int, period: int, memo: str) -> int:
    """An issuer sells the dollars it borrowed to the Central Bank, for naira the Central Bank makes."""
    cb = ledger.account_id(conn, ledger.CENTRAL_BANK)
    kobo = to_naira(cents, rate)
    ledger.post(conn, kind="fx_reserves", memo=memo, period=period,
                legs=[Leg(account, -cents, "USD"), Leg(cb, cents, "USD"), Leg(cb, -kobo), Leg(account, kobo)])
    return kobo


def _country_spread(conn: Connection) -> int:
    q = current(conn)
    cover = q["cover_bps"] if q else data.FX_COMFORT_COVER_BPS
    return data.FX_EUROBOND_SPREAD_BPS + max(data.FX_COMFORT_COVER_BPS - cover, 0) * data.FX_EUROBOND_SHORT_SPREAD_BPS // BPS


def _issue_government(conn: Connection, period: int, now: datetime, *, first: bool = False) -> dict:
    treasury = ledger.account_id(conn, ledger.TREASURY)
    world_abroad, _ = abroad.accounts(conn)
    amount = max(apply_bps(imports_usd(conn), data.FX_GOVERNMENT_EUROBOND_BPS) // data.FX_EUROBOND_FACE_CENTS, 1) * data.FX_EUROBOND_FACE_CENTS
    coupon = data.WORLD_RATE_BPS + _country_spread(conn)
    year, _ = clock.period_to_date(max(period, 1) + data.FX_EUROBOND_TERM_QUARTERS)
    eb = _new_eurobond(conn, name=f"Federal Government {coupon / 100:.2f}% dollar Eurobond, due Year {year}", issuer="government",
                       company=None, amount=amount, coupon_bps=coupon, period=period)
    ledger.post(conn, kind="fx_abroad", memo=f"{eb['name']}: dollars raised", period=period,
                legs=[Leg(world_abroad, -eb["units"] * eb["face"], "USD"), Leg(treasury, eb["units"] * eb["face"], "USD")])
    _sell_dollars_to_reserves(conn, treasury, eb["units"] * eb["face"], official(conn) if not first else
                              _one(conn, "SELECT official FROM fx_quarters ORDER BY period DESC LIMIT 1")["official"], period,
                              f"{eb['name']}: dollars sold to the Central Bank")
    if not first:
        _alert(conn, kind="eurobond", now=now, headline=f"The Government borrows {_cash(eb['units'] * eb['face'])} abroad",
               words=f"It sold a dollar Eurobond paying {coupon / 100:.2f}% a year. The dollars go into the Central Bank's reserves. Players can"
                     " buy it with dollars on the currency desk.")
        _news(conn, "fx_eurobond", now, {"issuer": "The Federal Government", "amount": _cash(eb["units"] * eb["face"]), "coupon": f"{coupon / 100:.2f}%"})
    return eb


def _issue_companies(conn: Connection, period: int, now: datetime) -> None:
    rate = _one(conn, "SELECT official FROM fx_quarters ORDER BY period DESC LIMIT 1")["official"]
    agent = ledger.account_id(conn, AGENT)
    world_abroad, _ = abroad.accounts(conn)
    for sector, how_many in data.FX_COMPANY_EUROBONDS:
        for c in _rows(conn, """
                SELECT c.*, r.revenue FROM companies c JOIN LATERAL (SELECT greatest(revenue, base_revenue) AS revenue FROM company_results WHERE company_id = c.id
                ORDER BY period DESC LIMIT 1) r ON true WHERE c.sector = %s AND c.listed AND c.status = 'trading'
                ORDER BY r.revenue DESC, c.ticker LIMIT %s""", (sector, how_many)):
            cents = min(to_cents(apply_bps(c["revenue"] * 4, data.FX_COMPANY_EUROBOND_SHARE_BPS), rate),
                        apply_bps(imports_usd(conn), data.FX_COMPANY_EUROBOND_MOST_BPS))
            cents = cents // data.FX_EUROBOND_FACE_CENTS * data.FX_EUROBOND_FACE_CENTS
            if cents <= 0:
                continue
            coupon = data.WORLD_RATE_BPS + _country_spread(conn) + data.FX_EUROBOND_COMPANY_EXTRA_BPS
            year, _ = clock.period_to_date(max(period, 1) + data.FX_EUROBOND_TERM_QUARTERS)
            name = f"{c['name']} {coupon / 100:.2f}% dollar Eurobond, due Year {year}"
            kobo = to_naira(cents, rate)
            debt = _one(conn, "INSERT INTO company_debts (company_id, lender_account_id, kind, name, original_principal, principal_outstanding,"
                              " annual_rate_bps, start_period, maturity_period, repayment, currency, fx_rate)"
                              " VALUES (%s, %s, 'bank_loan', %s, %s, %s, %s, %s, %s, 'bullet', 'USD', %s) RETURNING id",
                        (c["id"], agent, name, kobo, kobo, coupon, period, period + data.FX_EUROBOND_TERM_QUARTERS, rate))
            eb = _new_eurobond(conn, name=name, issuer="company", company=c, amount=cents, coupon_bps=coupon, period=period, debt_id=debt["id"])
            ledger.post(conn, kind="fx_abroad", memo=f"{name}: dollars raised", period=period,
                        legs=[Leg(world_abroad, -cents, "USD"), Leg(c["account_id"], cents, "USD")])
            _sell_dollars_to_reserves(conn, c["account_id"], cents, rate, period, f"{name}: dollars sold to the Central Bank")
            _hedge(conn, c, period + 1, now)
            del eb


def _yield_bps(conn: Connection, eb: dict) -> int:
    extra = data.FX_EUROBOND_COMPANY_EXTRA_BPS if eb["issuer"] == "company" else 0
    return data.WORLD_RATE_BPS + _country_spread(conn) + extra


def _elapsed(conn: Connection, now: datetime | None) -> float:
    """How much of the running quarter has passed (0 to 1): a bond's price includes the interest built up so far."""
    if now is None:
        now = _one(conn, "SELECT now() AS t")["t"]
    return min(max((careers.world_now(conn, now)["day"] - 1) / clock.GAME_DAYS_PER_QUARTER, 0.0), 1.0)


def fair_price(conn: Connection, eb: dict, period: int, elapsed: float = 0.0) -> int:
    """Cents for one bond: its remaining interest and its repayment, at the yield dollar lenders ask of Nigeria now,
    including the interest built up since the last payment (so nobody gains by buying just before a payment). A bond in
    default is priced the same way at a distressed yield."""
    if eb["redeemed_period"] is not None:
        return 0
    left = max(eb["maturity_period"] - period + 1, 1)          # payments still to come, the first at this quarter's close
    y = (_yield_bps(conn, eb) + (data.FX_EUROBOND_DISTRESS_BPS if eb["defaulted"] else 0)) / BPS / 4
    c = eb["face"] * eb["coupon_bps"] / BPS / 4
    pv = sum(c / (1 + y) ** (k - elapsed) for k in range(1, left + 1)) + eb["face"] / (1 + y) ** (left - elapsed)
    if eb["defaulted"]:
        pv = max(pv * data.FX_EUROBOND_RECOVERY_BPS / BPS, eb["face"] * 2 / 10)
    return max(int(pv), 1)


def eurobond_deal(conn: Connection, player_id, eurobond_id: int, side: str, units: int, now: datetime, *, for_empire: bool = False) -> dict:
    """Buy or sell Eurobonds with dollars, from the dealers, at the fair price less or plus half a percent."""
    if side not in ("buy", "sell"):
        raise FxError("Buy or sell.")
    if not _whole(units, 1, 1_000_000):
        raise FxError("Deal in whole bonds.")
    with conn.transaction():
        account, _ = _acting(conn, player_id, for_empire)
        eb = _one(conn, "SELECT * FROM eurobonds WHERE id = %s FOR UPDATE", (eurobond_id,))
        if eb is None or eb["redeemed_period"] is not None:
            raise FxError("There is no such Eurobond still to be repaid.")
        period = _period(conn, now)
        fair = fair_price(conn, eb, period, _elapsed(conn, now))
        world_abroad, _ = abroad.accounts(conn)
        if side == "buy":
            price = -(-fair * (BPS + data.FX_EUROBOND_DEAL_BPS) // BPS)
            cost = price * units
            if ledger.balance(conn, world_abroad, eb["asset"]) < units:
                raise FxError("The dealers have no more of that bond to sell.")
            if ledger.balance(conn, account, "USD") < cost:
                raise FxError(f"That costs {_cash(cost)}. Buy dollars first.")
            ledger.post(conn, kind="fx_abroad", memo=f"Bought {units:,} of {eb['name']}", period=period,
                        legs=[Leg(account, -cost, "USD"), Leg(world_abroad, cost, "USD"), Leg(world_abroad, -units, eb["asset"]), Leg(account, units, eb["asset"])])
        else:
            if ledger.balance(conn, account, eb["asset"]) < units:
                raise FxError("You do not hold that many.")
            price = fair * (BPS - data.FX_EUROBOND_DEAL_BPS) // BPS
            cost = price * units
            ledger.post(conn, kind="fx_abroad", memo=f"Sold {units:,} of {eb['name']}", period=period,
                        legs=[Leg(account, -units, eb["asset"]), Leg(world_abroad, units, eb["asset"]), Leg(world_abroad, -cost, "USD"), Leg(account, cost, "USD")])
        return {"side": side, "units": units, "price": price, "dollars": cost}


def _holders(conn: Connection, asset: str) -> list[dict]:
    agent = ledger.account_id(conn, AGENT)
    return _rows(conn, "SELECT account_id, balance::bigint AS units FROM ledger_balances WHERE asset = %s AND balance > 0 AND account_id <> %s"
                       " ORDER BY account_id", (asset, agent))


def _buy_dollars(conn: Connection, payer, cents: int, receiver_legs: list, period: int, memo: str, most: int | None = None) -> int:
    """A payer turns naira into dollars for others: from the Central Bank's reserves at the official rate while it has them,
    otherwise from the street. Returns the dollars paid (fewer if the payer's naira run short)."""
    if cents <= 0:
        return 0
    cb = ledger.account_id(conn, ledger.CENTRAL_BANK)
    world_abroad, _ = abroad.accounts(conn)
    budget = max(ledger.balance(conn, payer) if most is None else min(most, ledger.balance(conn, payer)), 0)
    rate = official(conn)
    want = min(cents, budget * 100 // max(rate, 1))
    from_cb = current(conn)["regime"] == "managed" and ledger.balance(conn, cb, "USD") >= want
    if not from_cb:
        rate = street(conn)
        want = min(cents, budget * 100 // max(rate, 1))
    cents = want
    if cents <= 0:
        return 0
    kobo = to_naira(cents, rate)
    seller = cb if from_cb else world_abroad
    total = sum(n for _, n in receiver_legs)
    legs = [Leg(payer, -kobo), Leg(seller, kobo), Leg(seller, -cents, "USD")]
    paid = 0
    for i, (acct, n) in enumerate(receiver_legs):
        share = cents - paid if i == len(receiver_legs) - 1 else cents * n // max(total, 1)
        if share > 0:
            legs.append(Leg(acct, share, "USD"))
            paid += share
    if paid != cents:
        legs.append(Leg(receiver_legs[-1][0], cents - paid, "USD"))
    ledger.post(conn, kind="fx_reserves" if from_cb else "fx_abroad", memo=memo, period=period, legs=legs)
    return cents


def _pay_eurobonds(conn: Connection, period: int, now: datetime) -> None:
    """At the close: each Eurobond's interest (and its face, when it is due) is paid to its holders in dollars. The
    Government pays from the Treasury; a company's bond passes on in dollars whatever the company paid the paying agent this
    quarter (interest, and any repayment). A bond that reaches its end is repaid once and taken in, whatever was short; a
    shortfall is a default, and the bond is then priced as one."""
    agent = ledger.account_id(conn, AGENT)
    treasury = ledger.account_id(conn, ledger.TREASURY)
    for eb in _rows(conn, "SELECT * FROM eurobonds WHERE redeemed_period IS NULL AND issued_period < %s ORDER BY id FOR UPDATE", (period,)):
        if _one(conn, "SELECT 1 AS x FROM eurobond_payments WHERE eurobond_id = %s AND period = %s", (eb["id"], period)):
            continue
        holders = _holders(conn, eb["asset"])
        out = sum(h["units"] for h in holders)
        if out <= 0:
            continue
        legs = [(h["account_id"], h["units"]) for h in holders]
        coupon = eb["face"] * eb["coupon_bps"] // BPS // 4
        if eb["issuer"] == "government":
            ends = period >= eb["maturity_period"]
            due = (coupon + (eb["face"] if ends else 0)) * out
            paid = _buy_dollars(conn, treasury, due, legs, period, f"{eb['name']}: interest{' and repayment' if ends else ''}")
        else:
            debt = _one(conn, "SELECT * FROM company_debts WHERE id = %s", (eb["debt_id"],))
            got = _one(conn, "SELECT coalesce(sum(e.amount), 0)::bigint AS n FROM ledger_entries e JOIN ledger_transactions t ON t.id = e.transaction_id"
                             " WHERE e.account_id = %s AND e.asset = 'NGN' AND e.amount > 0 AND t.period = %s AND t.reference = %s",
                       (agent, period, f"debt:{eb['debt_id']}"))["n"]
            ends = debt is None or debt["principal_outstanding"] == 0
            due = (coupon + (eb["face"] if ends else 0)) * out
            # Everything the company paid in goes out to the holders, in dollars (interest, and a part repayment too).
            paid = _buy_dollars(conn, agent, 10 ** 15, legs, period, f"{eb['name']}: what the company paid", most=got) if got > 0 else 0
            if debt is not None and debt["maturity_period"] > eb["maturity_period"]:
                conn.execute("UPDATE eurobonds SET maturity_period = %s WHERE id = %s", (debt["maturity_period"], eb["id"]))
        short = max(due - paid, 0)
        conn.execute("INSERT INTO eurobond_payments (eurobond_id, period, per_bond, paid, short, at) VALUES (%s, %s, %s, %s, %s, %s)",
                     (eb["id"], period, paid // out, paid, short, now))
        if ends:
            ledger.post(conn, kind="eurobond_redemption", memo=f"{eb['name']}: repaid", period=period,
                        legs=[*[Leg(h["account_id"], -h["units"], eb["asset"]) for h in holders], Leg(agent, out, eb["asset"])])
            conn.execute("UPDATE eurobonds SET redeemed_period = %s, defaulted = defaulted OR %s WHERE id = %s", (period, short > 0, eb["id"]))
        if short > due // 10 and not eb["defaulted"]:
            if not ends:
                conn.execute("UPDATE eurobonds SET defaulted = true WHERE id = %s", (eb["id"],))
            _alert(conn, kind="eurobond", now=now, headline=f"Default on {eb['name']}",
                   words=f"Its holders were paid {_cash(paid)} of the {_cash(due)} due"
                         + (". It has been taken in: what was short is lost." if ends else ". It now trades as a bond in default."))
    # Whatever naira the paying agent still holds (rounding, or a company paying when no bond is left) go back to the Treasury.
    left = ledger.balance(conn, agent)
    if left > 0:
        ledger.transfer(conn, payer=agent, receiver=treasury, amount=left, kind="fx_agent_sweep", memo="The paying agent's naira left over",
                        period=period)


# ---------------------------------------------------------------------------
# Companies' dollar debts: revalued every quarter; part of the interest hedged
# ---------------------------------------------------------------------------

def before_companies(conn: Connection, period: int, now: datetime) -> None:
    """Before the companies close: each dollar debt is revalued at the official rate, and the difference is a loss (or a
    gain) in its accounts."""
    if not opened(conn):
        return
    rate = official(conn)
    for d in _rows(conn, "SELECT * FROM company_debts WHERE currency = 'USD' AND principal_outstanding > 0 FOR UPDATE"):
        if _one(conn, "SELECT 1 AS x FROM fx_revaluations WHERE debt_id = %s AND period = %s", (d["id"], period)):
            continue
        new = d["principal_outstanding"] * rate // d["fx_rate"]
        delta = new - d["principal_outstanding"]
        conn.execute("UPDATE company_debts SET principal_outstanding = %s, original_principal = greatest(original_principal, %s), fx_rate = %s"
                     " WHERE id = %s", (new, new, rate, d["id"]))
        conn.execute("INSERT INTO fx_revaluations (company_id, debt_id, period, amount, rate) VALUES (%s, %s, %s, %s, %s)",
                     (d["company_id"], d["id"], period, delta, rate))


def currency_loss(conn: Connection, company_id, period: int) -> int:
    """What a company's dollar debts grew by in naira this quarter (a loss; negative: a gain)."""
    if not ready(conn):
        return 0
    return _one(conn, "SELECT coalesce(sum(amount), 0)::bigint AS n FROM fx_revaluations WHERE company_id = %s AND period = %s",
                (company_id, period))["n"]


def _hedge(conn: Connection, company: dict, first_period: int, now: datetime) -> None:
    """A company with dollar debts hedges part of a year's interest with a currency forward from a bank."""
    if _one(conn, "SELECT 1 AS x FROM swaps WHERE kind = 'fx' AND fixed_payer = %s AND status = 'active' AND last_period >= %s",
            (company["account_id"], first_period)):
        return                                          # (still hedged for the quarter coming)
    usd = _one(conn, "SELECT coalesce(sum(principal_outstanding * 100 / fx_rate * annual_rate_bps / 40000), 0)::bigint AS q"
                     " FROM company_debts WHERE company_id = %s AND currency = 'USD' AND principal_outstanding > 0", (company["id"],))["q"]
    notional = apply_bps(usd, data.FX_HEDGE_SHARE_BPS)
    bank = _one(conn, "SELECT id, account_id FROM companies WHERE sector = 'banking' AND status = 'trading' AND id <> %s ORDER BY ticker LIMIT 1",
                (company["id"],))
    if notional <= 0 or bank is None:
        return
    fixed = official(conn) * (BPS + data.SWAP_BANK_FX_SPREAD_BPS) // BPS
    conn.execute("INSERT INTO swaps (kind, fixed_payer, float_payer, proposer, proposer_side, counterparty, bank_company_id, notional, fixed_price,"
                 " quarters, first_period, last_period, status, at, active_at) VALUES ('fx', %s, %s, %s, 'pay_fixed', %s, %s, %s, %s, 4, %s, %s,"
                 " 'active', %s, %s)", (company["account_id"], bank["account_id"], company["account_id"], bank["account_id"], bank["id"], notional,
                                        fixed, first_period, first_period + 3, now, now))


# ---------------------------------------------------------------------------
# Foreign investors leaving need dollars
# ---------------------------------------------------------------------------

def exit_room(conn: Connection, wanted: int, rate: int) -> int:
    """Of the naira foreign investors want to take out this quarter, how much can leave: while the Central Bank manages
    the naira, only as many dollars as it can spare; the rest waits (the backlog). A floating naira clears."""
    if not opened(conn) or wanted <= 0:
        return wanted
    q = current(conn)
    if q["regime"] == "float":
        return wanted
    cb = ledger.account_id(conn, ledger.CENTRAL_BANK)
    spare = apply_bps(ledger.balance(conn, cb, "USD"), data.FX_EXIT_FROM_RESERVES_BPS)
    return min(wanted, to_naira(spare, rate))


# ---------------------------------------------------------------------------
# At the close: the Central Bank's reserves and its next move
# ---------------------------------------------------------------------------

def after_abroad(conn: Connection, period: int, now: datetime, row: dict, imports: int) -> dict | None:
    """After the market's rate for next quarter is set: Eurobonds paid; the quarter's dollars in and out of the reserves;
    the Government borrows abroad when they run low; the Central Bank sets the official rate (and how it runs it); requests
    still waiting at the window are handed back."""
    if not opened(conn):
        return None                                     # the desk opens at a closing bell
    if _one(conn, "SELECT 1 AS x FROM fx_quarters WHERE period = %s", (period,)):
        return None
    q = current(conn)
    seed = _seed(conn)
    cb = ledger.account_id(conn, ledger.CENTRAL_BANK)
    world_abroad, _ = abroad.accounts(conn)
    _pay_eurobonds(conn, period, now)
    # 1. The quarter's dollars: oil sold abroad brings most of them; the window pays for part of what companies buy abroad;
    #    foreign investors' money coming in (or going out) passes through the reserves; loans and aid pull towards usual.
    rate_q = q["market"]
    imports_usd = to_cents(imports or _quarter_imports(conn), rate_q)
    usual = imports_usd * data.FX_COMFORT_COVER_BPS // BPS
    reserves = ledger.balance(conn, cb, "USD")
    net = (apply_bps(to_cents(row["oil_exports"], rate_q), data.FX_OIL_TO_RESERVES_BPS)
           - apply_bps(imports_usd, data.FX_IMPORTS_FROM_RESERVES_BPS)
           + to_cents(row["foreign_inflow"], rate_q)
           + (usual - reserves) * data.FX_RESERVES_OTHER_BPS // BPS)
    if net > 0:
        ledger.post(conn, kind="fx_abroad", memo=f"Dollars into the reserves, {clock.period_label(period)}", period=period,
                    legs=[Leg(world_abroad, -net, "USD"), Leg(cb, net, "USD")])
    elif net < 0:
        out = min(-net, ledger.balance(conn, cb, "USD"))
        if out > 0:
            ledger.post(conn, kind="fx_abroad", memo=f"Dollars out of the reserves, {clock.period_label(period)}", period=period,
                        legs=[Leg(cb, -out, "USD"), Leg(world_abroad, out, "USD")])
    market = row["fx"]
    imports_usd = to_cents(imports or _quarter_imports(conn), market)
    cover = ledger.balance(conn, cb, "USD") * BPS // max(imports_usd, 1)
    # 2. Low reserves: the Government borrows dollars abroad (at most once a year).
    issued_lately = _one(conn, "SELECT 1 AS x FROM eurobonds WHERE issuer = 'government' AND issued_period > %s", (period - 4,))
    if cover < data.FX_DEFEND_COVER_BPS and not issued_lately:
        _issue_government(conn, period, now)
        cover = ledger.balance(conn, cb, "USD") * BPS // max(imports_usd, 1)
    # 3. The Central Bank's move.
    off, regime, event, sold = q["official"], q["regime"], None, 0
    gap = market * BPS // max(off, 1) - BPS
    if regime == "managed":
        if cover < data.FX_FLOAT_COVER_BPS:
            regime, off, event = "float", market, "floated"
        elif gap >= data.FX_DEVALUE_GAP_BPS and cover < data.FX_COMFORT_COVER_BPS:
            off, event = market, "devalued"
        else:
            off = off + (market - off) * data.FX_CRAWL_BPS // BPS
            gap = market * BPS // max(off, 1) - BPS
            if gap >= data.FX_DEFEND_GAP_BPS and cover >= data.FX_DEFEND_COVER_BPS:
                sold = min(apply_bps(ledger.balance(conn, cb, "USD"), data.FX_DEFEND_MOST_BPS), imports_usd * gap // BPS)
                event = "defended" if sold > 0 else None
    else:
        off = market
        if cover >= data.FX_REPEG_COVER_BPS:
            regime, event = "managed", "repegged"
    gbp = float(q["gbp_usd"]) * (1 + stochastic.normal(seed, "fx", "gbp", period) * data.FX_CROSS_SWING_BPS / BPS)
    eur = float(q["eur_usd"]) * (1 + stochastic.normal(seed, "fx", "eur", period) * data.FX_CROSS_SWING_BPS / BPS)
    words = _move_words(event, q["official"], off, market, cover, sold)
    conn.execute("INSERT INTO fx_quarters (period, official, market, regime, reserves, cover_bps, gbp_usd, eur_usd, sold, backlog, event, words, at)"
                 " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                 (period, max(off, 1), market, regime, ledger.balance(conn, cb, "USD"), cover, round(min(max(gbp, 0.8), 2.0), 6),
                  round(min(max(eur, 0.7), 1.6), 6), sold, row.get("fx_backlog", 0), event, words, now))
    # 4. Requests still waiting at the window are handed back: a new quarter, a new line.
    for req in _rows(conn, "SELECT * FROM fx_window WHERE status = 'waiting' AND period <= %s ORDER BY id FOR UPDATE", (period,)):
        _release_window(conn, req, "expired", now, period)
    # 5. Companies with dollar debts renew their hedges.
    for c in _rows(conn, "SELECT DISTINCT c.* FROM companies c JOIN company_debts d ON d.company_id = c.id WHERE d.currency = 'USD'"
                         " AND d.principal_outstanding > 0 AND c.status = 'trading' ORDER BY c.ticker"):
        _hedge(conn, c, period + 1, now)
    _announce(conn, period, now, q, event, off, market, cover, sold, row.get("fx_backlog", 0))
    return current(conn)


def _move_words(event, before: int, after: int, market: int, cover: int, sold: int) -> str:
    quarters = f"{cover / BPS:.1f} quarters of imports"
    if event == "floated":
        return f"With reserves down to {quarters}, the Central Bank let the naira float: the official rate is now the market's, {_rate_words(after)}."
    if event == "devalued":
        return (f"The Central Bank devalued the naira from {_rate_words(before)} to {_rate_words(after)} a dollar, closing the gap with the market."
                f" Reserves: {quarters}.")
    if event == "repegged":
        return f"With reserves back to {quarters}, the Central Bank manages the naira again, at {_rate_words(after)}."
    if event == "defended":
        return (f"The Central Bank will sell {_cash(sold)} of its reserves on the street this quarter to hold the naira near"
                f" {_rate_words(after)}. Reserves: {quarters}.")
    return f"The official rate is {_rate_words(after)} a dollar; the market's is {_rate_words(market)}. Reserves: {quarters}."


def _announce(conn: Connection, period: int, now: datetime, q: dict, event, off: int, market: int, cover: int, sold: int, backlog: int) -> None:
    label = clock.period_label(period + 1)
    if event in ("devalued", "floated", "repegged", "defended"):
        headline = {"devalued": f"The naira is devalued to {_rate_words(off)} a dollar",
                    "floated": "The Central Bank lets the naira float",
                    "repegged": "The Central Bank manages the naira again",
                    "defended": "The Central Bank steps in to defend the naira"}[event]
        _alert(conn, kind=event, now=now, headline=headline, words=_move_words(event, q["official"], off, market, cover, sold))
        _news(conn, f"fx_{event}", now, {"rate": _rate_words(off), "before": _rate_words(q["official"]), "cover": f"{cover / BPS:.1f}",
                                         "amount": _cash(sold), "quarter": label})
    if cover < data.FX_DEFEND_COVER_BPS <= q["cover_bps"]:
        _alert(conn, kind="reserves", now=now, headline="The Central Bank's reserves are running low",
               words=f"They would pay for {cover / BPS:.1f} quarters of imports. Dollars at the official window will be scarcer.")
        _news(conn, "fx_reserves_low", now, {"cover": f"{cover / BPS:.1f}"})
    if backlog > 0 and q["backlog"] == 0:
        _alert(conn, kind="backlog", now=now, headline="Foreign investors are stuck waiting for dollars",
               words=f"{_money(backlog)} of their money could not leave this quarter. The waiting scares new investors away.")
        _news(conn, "fx_backlog", now, {"amount": _money(backlog)})


# ---------------------------------------------------------------------------
# At each closing bell
# ---------------------------------------------------------------------------

def tick(conn: Connection, now: datetime) -> int:
    """After each closing bell: the Central Bank's defence, the window's allocation, money sent home, households at the
    bureaux, and the day's rates written down for good."""
    if not ready(conn) or not _one(conn, "SELECT 1 AS x FROM world_state"):
        return 0
    progress = _one(conn, "SELECT dealt_through FROM fx_progress")["dealt_through"]
    bells = _rows(conn, "SELECT session_date, rung_at FROM closing_bells WHERE (%s::date IS NULL OR session_date > %s) AND rung_at <= %s"
                        " ORDER BY session_date", (progress, progress, now))
    for bell in bells:
        try:
            with conn.transaction():
                if not opened(conn):
                    setup(conn, bell["rung_at"])
                _at_bell(conn, bell["session_date"], bell["rung_at"])
                conn.execute("UPDATE fx_progress SET dealt_through = %s", (bell["session_date"],))
        except Exception:
            log.exception("The currency desk's work at the bell failed")
            break
    return len(bells)


def _defend(conn: Connection, q: dict, period: int) -> int:
    """The Central Bank sells part of the quarter's planned defence on the street: its dollars for naira it takes out of
    existence, so the street eases (and the naira the rest of the world holds fall, which strengthens the market's rate)."""
    if q["sold"] <= 0 or q["regime"] != "managed":
        return 0
    cb = ledger.account_id(conn, ledger.CENTRAL_BANK)
    done = _one(conn, "SELECT coalesce(sum(-e.amount), 0)::bigint AS n FROM ledger_entries e JOIN ledger_transactions t ON t.id = e.transaction_id"
                      " WHERE e.account_id = %s AND e.asset = 'USD' AND e.amount < 0 AND t.kind = 'fx_defence' AND t.period = %s", (cb, period))["n"]
    today = min(q["sold"] - done, -(-q["sold"] // 5), ledger.balance(conn, cb, "USD"))
    world_abroad, _ = abroad.accounts(conn)
    kobo = min(to_naira(today, street(conn)), ledger.balance(conn, world_abroad))
    today = to_cents(kobo, street(conn))
    if today <= 0:
        return 0
    kobo = to_naira(today, street(conn))
    ledger.post(conn, kind="fx_defence", memo="The Central Bank sells dollars on the street", period=period,
                legs=[Leg(cb, -today, "USD"), Leg(world_abroad, today, "USD"), Leg(world_abroad, -kobo), Leg(cb, kobo)])
    _move_street(conn, -today)
    return today


def _at_bell(conn: Connection, day: date, now: datetime) -> None:
    if _one(conn, "SELECT 1 AS x FROM fx_days WHERE session_date = %s", (day,)):
        return
    q = current(conn)
    period = careers.world_now(conn, now)["period"]
    seed = _seed(conn)
    cb = ledger.account_id(conn, ledger.CENTRAL_BANK)
    # Yesterday's buying and selling fade by half overnight.
    conn.execute("UPDATE fx_street SET impact_bps = impact_bps / 2 WHERE id = 1")
    _defend(conn, q, period)
    paid = _fill_window(conn, now, period)
    premium = street(conn) * BPS // max(official(conn), 1) - BPS
    remitted = _remit(conn, day, now, period, premium)
    _retail(conn, day, now, period)
    noise = int(stochastic.normal(seed, "fx", "street", day.isoformat()) * data.FX_STREET_NOISE_BPS)
    mid = max(_street_base(conn, q, noise) * (BPS + _impact(conn)) // BPS, 1)
    off = mid * (BPS - data.FX_FLOAT_PREMIUM_BPS) // BPS if q["regime"] == "float" else q["official"]
    net = _one(conn, "SELECT coalesce(sum(CASE WHEN side = 'buy' THEN amount ELSE -amount END), 0)::bigint AS n FROM fx_trades"
                     " WHERE venue = 'street' AND currency = 'USD' AND at > %s - interval '1 day' AND at <= %s", (now, now))["n"]
    gbp = float(q["gbp_usd"]) * (1 + stochastic.normal(seed, "fx", "gbp-day", day.isoformat()) * 20 / BPS)
    eur = float(q["eur_usd"]) * (1 + stochastic.normal(seed, "fx", "eur-day", day.isoformat()) * 20 / BPS)
    conn.execute("INSERT INTO fx_days (session_date, official, street, premium_bps, street_net, window_paid, remitted, reserves, gbp_usd, eur_usd, at)"
                 " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                 (day, off, mid, mid * BPS // max(off, 1) - BPS, net, paid, remitted, ledger.balance(conn, cb, "USD"), round(gbp, 6), round(eur, 6), now))
    conn.execute("UPDATE fx_street SET impact_bps = 0, session_date = %s WHERE id = 1", (day,))
    gap = mid * BPS // max(off, 1) - BPS
    if gap >= 2_000 and not _one(conn, "SELECT 1 AS x FROM fx_alerts WHERE kind = 'gap' AND at > %s", (q["at"],)):
        _alert(conn, kind="gap", now=now, headline=f"The street pays {gap / 100:.0f}% more than the official rate",
               words=f"A dollar costs {_rate_words(mid)} on the street against {_rate_words(off)} at the official window.")
        _news(conn, "fx_gap", now, {"gap": f"{gap / 100:.0f}%", "street": _rate_words(mid), "official": _rate_words(off)})


# ---------------------------------------------------------------------------
# Pop-ups and news
# ---------------------------------------------------------------------------

def _alert(conn: Connection, *, kind: str, headline: str, words: str, now: datetime, account=None) -> None:
    conn.execute("INSERT INTO fx_alerts (kind, account_id, headline, words, at) VALUES (%s, %s, %s, %s, %s)",
                 (kind, account, headline[:160], words[:600], now))


def _news(conn: Connection, kind: str, now: datetime, facts: dict) -> None:
    from simulation import news
    if kind not in news.BY_NAME:
        return
    w = careers.world_now(conn, now)
    news.publish(conn, period=w["period"], day=w["day"], kind=kind, story=f"fx:{kind}:{w['period']}:{w['day']}", facts=facts)


def alerts_for(conn: Connection, player_id, after: int | None, now: datetime) -> dict:
    accounts = [ledger.player_account_id(conn, player_id)]
    seat = empires.seat_of(conn, player_id)
    if seat and seat["empire_kind"] != "pension":
        accounts.append(seat["account_id"])
    since = after if after is not None else _one(conn, "SELECT coalesce(max(id), 0) AS m FROM fx_alerts WHERE at < %s",
                                                 (now - timedelta(hours=24),))["m"]
    found = _rows(conn, "SELECT id, kind, headline, words, at FROM fx_alerts WHERE id > %s AND (account_id IS NULL OR account_id = ANY(%s))"
                        " ORDER BY id LIMIT 20", (since, accounts))
    mark = _one(conn, "SELECT coalesce(max(id), 0) AS m FROM fx_alerts")["m"]
    return {"mark": mark, "alerts": [{"id": a["id"], "kind": a["kind"], "headline": a["headline"], "words": a["words"], "at": a["at"]} for a in found]}


# ---------------------------------------------------------------------------
# What it is all worth, and the books
# ---------------------------------------------------------------------------

def held_value(conn: Connection, account) -> int:
    """What an account's foreign currency, Eurobonds and naira held at the window are worth now (kobo), at what the street
    would pay for them."""
    if not opened(conn):
        return 0
    total = 0
    for c in CURRENCIES:
        n = ledger.balance(conn, account, c)
        if n > 0:
            total += n * quote(conn, c)["buy"] // 100
    period = _one(conn, "SELECT last_closed_period AS p FROM world_state")["p"] + 1
    bid = quote(conn, "USD")["buy"]
    for eb in _rows(conn, "SELECT e.*, b.balance::bigint AS held FROM eurobonds e JOIN ledger_balances b ON b.asset = e.asset"
                          " WHERE b.account_id = %s AND b.balance > 0", (account,)):
        total += eb["held"] * fair_price(conn, eb, period, _elapsed(conn, None)) * bid // 100
    total += _one(conn, "SELECT coalesce(sum(held), 0)::bigint AS n FROM fx_window WHERE account_id = %s AND status = 'waiting'", (account,))["n"]
    return total


def _players_fx(conn: Connection) -> dict:
    out: dict = {}
    if not opened(conn):
        return out
    for r in _rows(conn, "SELECT DISTINCT b.account_id FROM ledger_balances b JOIN ledger_accounts a ON a.id = b.account_id"
                         " WHERE a.kind = 'player' AND b.balance > 0 AND (b.asset IN ('USD', 'GBP', 'EUR') OR b.asset LIKE 'EUB-%%')"
                         " UNION SELECT account_id FROM fx_window WHERE status = 'waiting'"):
        out[r["account_id"]] = (0, held_value(conn, r["account_id"]))
    return out


def _register() -> None:
    from simulation import marketview
    if _players_fx not in marketview._OTHER_HOLDINGS:
        marketview._OTHER_HOLDINGS.append(_players_fx)


_register()


def check_books(conn: Connection) -> list[str]:
    if not opened(conn):
        return []
    problems = []
    held = ledger.balance(conn, ledger.account_id(conn, HELD))
    waiting = _one(conn, "SELECT coalesce(sum(held), 0)::bigint AS n FROM fx_window WHERE status = 'waiting'")["n"]
    if held != waiting:
        problems.append(f"The official window holds {held} kobo against {waiting} for the requests waiting.")
    for eb in _rows(conn, "SELECT * FROM eurobonds"):
        out = -ledger.balance(conn, ledger.account_id(conn, AGENT), eb["asset"])
        expected = 0 if eb["redeemed_period"] is not None else eb["units"]
        if out != expected:
            problems.append(f"{eb['name']}: {out} bonds out against {expected}.")
    return problems


# ---------------------------------------------------------------------------
# What players see
# ---------------------------------------------------------------------------

def public(conn: Connection) -> dict:
    """The rates, the Central Bank's record and the street's days: public to everybody (never its next move)."""
    q = current(conn)
    if q is None:
        return {"open": False}
    quarters = _rows(conn, "SELECT period, official, market, regime, reserves, cover_bps, sold, backlog, event, words FROM fx_quarters ORDER BY period")
    days = list(reversed(_rows(conn, "SELECT session_date, official, street, premium_bps, reserves, remitted FROM fx_days"
                                     " ORDER BY session_date DESC LIMIT 60")))
    off = official(conn)
    mid = street(conn)
    return {
        "open": True, "regime": q["regime"], "official": off, "street": mid, "gap_bps": mid * BPS // max(off, 1) - BPS,
        "reserves": ledger.balance(conn, ledger.account_id(conn, ledger.CENTRAL_BANK), "USD"), "cover_bps": q["cover_bps"],
        "backlog": q["backlog"], "words": q["words"],
        "quotes": [quote(conn, c) for c in CURRENCIES], "names": NAMES,
        "quarters": [{**r, "label": clock.period_label(r["period"] + 1)} for r in quarters],
        "days": days,
    }


def page(conn: Connection, player_id, now: datetime) -> dict:
    out = public(conn)
    if not out["open"]:
        return out
    period = _period(conn, now)
    me = ledger.player_account_id(conn, player_id)
    seat = empires.seat_of(conn, player_id)
    empire = empires._empire(conn, seat["empire_id"]) if seat and seat["empire_status"] == "active" and seat["empire_kind"] != "pension" else None
    can_empire = bool(empire and (empire["head_player_id"] == player_id or seat["build"] == "investment_banker"))

    def wallet(account, is_empire: bool) -> dict:
        used = _window_used(conn, account, period)
        return {
            "naira": ledger.balance(conn, account),
            "balances": {c: ledger.balance(conn, account, c) for c in CURRENCIES},
            "kept": kept_from_window(conn, account, period),
            "window_limit": _window_limit(is_empire), "window_used": used,
            "requests": _rows(conn, "SELECT id, amount, filled, held, status, placed_at FROM fx_window WHERE account_id = %s ORDER BY id DESC LIMIT 10",
                              (account,)),
            "trades": _rows(conn, "SELECT venue, side, currency, amount, rate, naira, at FROM fx_trades WHERE account_id = %s ORDER BY id DESC LIMIT 15",
                            (account,)),
            "worth": held_value(conn, account),
        }

    out["mine"] = wallet(me, False)
    out["empire"] = {"name": empire["name"], **wallet(empire["account_id"], True)} if can_empire else None
    out["is_head"] = bool(empire and empire["head_player_id"] == player_id)
    ahead = {}
    for acct in [me] + ([empire["account_id"]] if can_empire else []):
        first = _one(conn, "SELECT min(id) AS i FROM fx_window WHERE account_id = %s AND status = 'waiting'", (acct,))["i"]
        if first:
            ahead[str(acct)] = _one(conn, "SELECT count(*) AS n FROM fx_window WHERE status = 'waiting' AND id < %s", (first,))["n"] + 1
    out["window_ahead"] = ahead
    out["bdcs"] = [{"id": b["id"], "name": b["name"], "empire": b["empire_name"], **_bdc_prices(conn, b)}
                   for b in _rows(conn, "SELECT b.*, e.name AS empire_name FROM bdcs b JOIN empires e ON e.id = b.empire_id WHERE b.status = 'open' ORDER BY b.id")]
    last = _one(conn, "SELECT max(session_date) AS d FROM remittances")["d"]
    shares = {r["remitter_id"]: r["dollars"] for r in _rows(conn, "SELECT remitter_id, dollars FROM remittances WHERE session_date = %s", (last,))} if last else {}
    total = sum(shares.values()) or 1
    out["remitters"] = [{"id": r["id"], "name": r["name"], "computer": r["empire_id"] is None, "fee_bps": r["fee_bps"], "days": r["days"],
                         "share_bps": shares.get(r["id"], 0) * BPS // total}
                        for r in _rows(conn, "SELECT * FROM remitters WHERE status = 'open' ORDER BY id")]
    mine_b = _one(conn, "SELECT * FROM bdcs WHERE empire_id = %s AND status = 'open'", (empire["id"],)) if out["is_head"] else None
    out["my_bdc"] = None
    if mine_b:
        out["my_bdc"] = {"id": mine_b["id"], "name": mine_b["name"], "buy_bps": mine_b["buy_bps"], "sell_bps": mine_b["sell_bps"], **_bdc_prices(conn, mine_b),
                         "dollars": ledger.balance(conn, empire["account_id"], "USD"), "naira": ledger.balance(conn, empire["account_id"]),
                         "reports": _rows(conn, "SELECT customer, amount, naira, at FROM bdc_reports WHERE bdc_id = %s ORDER BY id DESC LIMIT 10", (mine_b["id"],))}
    mine_r = _one(conn, "SELECT * FROM remitters WHERE empire_id = %s AND status = 'open'", (empire["id"],)) if out["is_head"] else None
    out["my_remitter"] = None
    if mine_r:
        out["my_remitter"] = {"id": mine_r["id"], "name": mine_r["name"], "fee_bps": mine_r["fee_bps"], "days": mine_r["days"],
                              "days_record": _rows(conn, "SELECT session_date, dollars, fee, cost FROM remittances WHERE remitter_id = %s"
                                                         " ORDER BY session_date DESC LIMIT 10", (mine_r["id"],))}
    world_abroad, _ = abroad.accounts(conn)
    out["eurobonds"] = []
    for eb in _rows(conn, "SELECT * FROM eurobonds WHERE redeemed_period IS NULL ORDER BY id"):
        fair = fair_price(conn, eb, period, _elapsed(conn, now))
        out["eurobonds"].append({
            "id": eb["id"], "name": eb["name"], "issuer": eb["issuer"], "coupon_bps": eb["coupon_bps"], "maturity": clock.period_label(eb["maturity_period"]),
            "face": eb["face"], "yield_bps": _yield_bps(conn, eb), "defaulted": eb["defaulted"],
            "buy": -(-fair * (BPS + data.FX_EUROBOND_DEAL_BPS) // BPS), "sell": fair * (BPS - data.FX_EUROBOND_DEAL_BPS) // BPS,
            "available": ledger.balance(conn, world_abroad, eb["asset"]),
            "mine": ledger.balance(conn, me, eb["asset"]), "empire": ledger.balance(conn, empire["account_id"], eb["asset"]) if can_empire else 0})
    out["licences"] = {"bdc": naira(data.FX_BDC_LICENCE_NAIRA), "bdc_capital": naira(data.FX_BDC_LEAST_CAPITAL_NAIRA),
                       "remitter": naira(data.FX_REMIT_LICENCE_NAIRA), "report": data.FX_BDC_REPORT_CENTS}
    return out
