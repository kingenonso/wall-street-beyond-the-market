"""The talent and funds stage, Part 4b: foreign markets.

Three foreign exchanges, in the style of New York, London and Frankfurt, each trading in its own currency (dollars, pounds,
euros) during its own city's hours. Every name is invented; the countries and cities are real. Ten companies are listed on
each. Their prices move every ten minutes while their exchange is open: with their market as a whole, with their own news,
and back towards what the share is worth. What a share is worth comes from its profits and its country's interest rate:
when rates rise, a share is worth fewer years of its profits (most of all a fast-growing company's).

Each exchange has its economy: growth and inflation every quarter, and a central bank that sets its interest rate by a
rule (it raises rates when inflation runs above 2% and growth runs hot). Those economies now reach Nigeria: growth abroad
moves the oil price; America's interest rate is what lending abroad pays, so foreign investors here want more when it is
low and less when it is high; and the pound and the euro move against the dollar with their own rates and growth.

Players and empires buy foreign shares with their dollars, pounds or euros (from the currency desk) through the brokers
abroad, who sell a little above the price and buy a little below it. A holding gains or loses on the share and on the
currency, and both are shown. Dividends are paid in the currency, after tax kept abroad.

Five Nigerian companies are the Nigerian arms of companies listed abroad: their founders' stake belongs to the parent.
The parent's dividends wait in naira until there are dollars to send them home: when the Central Bank's reserves are low,
they pile up. A parent with years of dividends stuck here, or a naira that has lost much of its value, may decide to leave:
for two quarters empires may buy pieces of its stake at the market price (and any takeover offer gets its shares); what
is left then goes to the pension funds at a deeper discount.

ETFs of foreign shares trade on the Broad Street Exchange in naira: their naira go abroad (through the street) to buy the
shares, so money pouring into them weakens the naira a little.

Never sent to players: the economies' secret swings, the central banks' next moves, each price's secret path, a parent's
decision before it is announced, other players' holdings.
"""

from __future__ import annotations

import logging
import math
from datetime import date, datetime, time, timedelta
from decimal import ROUND_CEILING, Decimal
from zoneinfo import ZoneInfo

from psycopg import Connection
from psycopg.rows import dict_row

from simulation import abroad, careers, clock, empires, fx, ledger, stochastic
from simulation import world_data as data
from simulation.ledger import Leg
from simulation.money import BPS, apply_bps

log = logging.getLogger(__name__)

REGISTRY = "world:registry"
PARENT_PREFIX = "parent:"
SECTORS = data.WORLD_SECTORS
ECONOMIES = {e[0]: e for e in data.WORLD_ECONOMIES}
BIG = 10 ** 18


class WorldError(Exception):
    """A request about foreign markets the rules do not allow. The words are for the player."""


def _rows(conn: Connection, sql: str, params=()) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def _one(conn: Connection, sql: str, params=()) -> dict | None:
    rows = _rows(conn, sql, params)
    return rows[0] if rows else None


def ready(conn: Connection) -> bool:
    return bool(_one(conn, "SELECT to_regclass('world_exchanges') IS NOT NULL AS ok")["ok"])


def opened(conn: Connection) -> bool:
    return ready(conn) and _one(conn, "SELECT 1 AS x FROM world_exchanges LIMIT 1") is not None


def _seed(conn: Connection) -> str:
    return _one(conn, "SELECT fortune_seed FROM world_state")["fortune_seed"]


def _money(kobo: int) -> str:
    return f"₦{kobo / 100:,.2f}"


def _cash(cents, currency: str) -> str:
    return f"{fx.SYMBOLS[currency]}{float(cents) / 100:,.2f}"


def _pct(bps) -> str:
    return f"{bps / 100:.2f}%"


def _closed_period(conn: Connection) -> int:
    return _one(conn, "SELECT last_closed_period AS p FROM world_state")["p"]


# ---------------------------------------------------------------------------
# Hours: each exchange opens and closes at its own city's time
# ---------------------------------------------------------------------------

def exchanges(conn: Connection) -> list[dict]:
    return _rows(conn, "SELECT * FROM world_exchanges ORDER BY array_position(ARRAY['HSE', 'THX', 'RMX'], code), code")


def _exchange(conn: Connection, code: str) -> dict:
    return _one(conn, "SELECT * FROM world_exchanges WHERE code = %s", (code,))


def session(ex: dict, day: date) -> tuple[datetime, datetime]:
    """When the exchange opens and closes on one of its own days."""
    zone = ZoneInfo(ex["zone"])
    return (datetime.combine(day, ex["opens"], tzinfo=zone), datetime.combine(day, ex["closes"], tzinfo=zone))


def local_day(ex: dict, moment: datetime) -> date:
    return moment.astimezone(ZoneInfo(ex["zone"])).date()


def is_open(ex: dict, now: datetime) -> bool:
    start, end = session(ex, local_day(ex, now))
    return start <= now < end


def steps_in_day(ex: dict) -> int:
    start, end = session(ex, date(2026, 1, 15))
    return max(int((end - start).total_seconds() // 60) // data.WORLD_STEP_MINUTES, 1)


def hours_in_lagos(ex: dict, now: datetime) -> tuple[str, str]:
    start, end = session(ex, local_day(ex, now))
    return start.astimezone(clock.LAGOS).strftime("%H:%M"), end.astimezone(clock.LAGOS).strftime("%H:%M")


def next_change(ex: dict, now: datetime) -> datetime:
    """When it next opens (or, while it is open, closes)."""
    day = local_day(ex, now)
    start, end = session(ex, day)
    if now < start:
        return start
    if now < end:
        return end
    return session(ex, day + timedelta(days=1))[0]


# ---------------------------------------------------------------------------
# Prices: a secret path every ten minutes while the exchange is open
# ---------------------------------------------------------------------------

class _Path:
    """The moves of a market and its companies, step by step, worked out from the world's secret (never sent)."""

    def __init__(self, conn: Connection):
        self.seed = _seed(conn)
        self.market: dict = {}

    def market_move(self, ex: dict, day: date, k: int) -> float:
        key = (ex["code"], day, k)
        if key not in self.market:
            self.market[key] = stochastic.normal(self.seed, "world", ex["code"], day.isoformat(), k)
        return self.market[key]

    def own_move(self, co: dict, day: date, k: int) -> float:
        return stochastic.normal(self.seed, "world", co["ticker"], day.isoformat(), k)


def _step_sizes(ex: dict) -> tuple[float, float, float, float]:
    n = steps_in_day(ex)
    over = data.WORLD_OVERNIGHT_SHARE_BPS / BPS
    m, o = data.WORLD_MARKET_DAY_BPS / BPS, data.WORLD_OWN_DAY_BPS / BPS
    return m * math.sqrt(over), o * math.sqrt(over), m * math.sqrt((1 - over) / n), o * math.sqrt((1 - over) / n)


def _walk(path: _Path, ex: dict, co: dict, base: Decimal, base_at: datetime, until: datetime) -> float:
    """The log of the price at `until`, from the price at `base_at`: each step's move in between (the first step of each
    day, at the open, carries the night's move and the day's pull towards what the share is worth)."""
    if until <= base_at:
        return math.log(float(base))
    n = steps_in_day(ex)
    m_night, o_night, m_step, o_step = _step_sizes(ex)
    beta = co["beta_bps"] / BPS
    log_p = math.log(float(base))
    fair = math.log(max(float(co["fair"]), 0.01))
    day = local_day(ex, base_at)
    last = local_day(ex, until)
    step = timedelta(minutes=data.WORLD_STEP_MINUTES)
    while day <= last:
        start, _ = session(ex, day)
        for k in range(n + 1):
            t = start + step * k
            if t <= base_at:
                continue
            if t > until:
                break
            if k == 0:
                pull = (fair - log_p) * data.WORLD_FAIR_PULL_BPS / BPS
                log_p += pull + beta * m_night * path.market_move(ex, day, 0) + o_night * path.own_move(co, day, 0)
            else:
                log_p += beta * m_step * path.market_move(ex, day, k) + o_step * path.own_move(co, day, k)
        day += timedelta(days=1)
    return log_p


def _quote_row(conn: Connection, company_id, *, lock: bool = False) -> dict:
    return _one(conn, "SELECT * FROM world_quotes WHERE company_id = %s" + (" FOR UPDATE" if lock else ""), (company_id,))


def price_of(conn: Connection, co: dict, now: datetime, *, path: _Path | None = None, ex: dict | None = None,
             q: dict | None = None, with_impact: bool = True) -> Decimal:
    """One share's price now, in cents (or pence)."""
    ex = ex or _exchange(conn, co["exchange"])
    q = q or _quote_row(conn, co["id"])
    path = path or _Path(conn)
    log_p = _walk(path, ex, co, q["base"], q["base_at"], now)
    if with_impact:
        log_p += q["impact_bps"] / BPS
    return Decimal(str(round(math.exp(log_p), 4)))


def _rebase(conn: Connection, co: dict, now: datetime, factor: float, path: _Path) -> Decimal:
    """Start the path again from the price now, times `factor` (news at the close, a dividend paid)."""
    q = _quote_row(conn, co["id"], lock=True)
    p = price_of(conn, co, now, path=path, q=q, with_impact=False)
    new = max(Decimal(str(round(float(p) * factor, 4))), Decimal("0.01"))
    conn.execute("UPDATE world_quotes SET base = %s, base_at = %s WHERE company_id = %s", (new, now, co["id"]))
    return new


def advance(conn: Connection, now: datetime) -> int:
    """Write down every closing price (and each index's level) up to now, once each, and start each next day from the close
    (half of the day's buying and selling stays in the price). Returns the closes written."""
    if not opened(conn):
        return 0
    path = _Path(conn)
    written = 0
    for ex in exchanges(conn):
        companies = _rows(conn, "SELECT * FROM world_companies WHERE exchange = %s ORDER BY ticker", (ex["code"],))
        last = _one(conn, "SELECT max(day) AS d FROM world_index_days WHERE exchange = %s", (ex["code"],))["d"]
        day = (last + timedelta(days=1)) if last else local_day(ex, ex["opened_at"])
        today = local_day(ex, now)
        while day <= today:
            start, end = session(ex, day)
            if end > now:
                break
            if end <= ex["opened_at"]:
                day += timedelta(days=1)
                continue
            closes = {}
            for co in companies:
                q = _quote_row(conn, co["id"], lock=True)
                p = price_of(conn, co, end, path=path, ex=ex, q=q)
                closes[co["id"]] = p
                conn.execute("INSERT INTO world_days (company_id, day, close) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING", (co["id"], day, p))
                kept = Decimal(str(round(float(p) * math.exp(-q["impact_bps"] / BPS / 2), 4)))
                conn.execute("UPDATE world_quotes SET base = %s, base_at = %s, impact_bps = 0 WHERE company_id = %s", (kept, end, co["id"]))
            level = _index_level(conn, ex, companies, closes, day)
            conn.execute("INSERT INTO world_index_days (exchange, day, level) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING", (ex["code"], day, level))
            written += 1
            _big_day(conn, ex, day, level, end)
            day += timedelta(days=1)
    return written


def _index_level(conn: Connection, ex: dict, companies: list[dict], closes: dict, day: date) -> int:
    """The exchange's index: its ten companies by the value of their shares, chained from one close to the next."""
    before = _one(conn, "SELECT level, day FROM world_index_days WHERE exchange = %s AND day < %s ORDER BY day DESC LIMIT 1", (ex["code"], day))
    if before is None:
        return data.INDEX_START_LEVEL
    prev = {r["company_id"]: r["close"] for r in _rows(conn, "SELECT company_id, close FROM world_days WHERE day = %s AND company_id = ANY(%s)",
                                                         (before["day"], [c["id"] for c in companies]))}
    was = sum(Decimal(c["shares"]) * prev.get(c["id"], closes[c["id"]]) for c in companies)
    now_ = sum(Decimal(c["shares"]) * closes[c["id"]] for c in companies)
    return max(int(Decimal(before["level"]) * now_ / was), 1) if was else before["level"]


def _big_day(conn: Connection, ex: dict, day: date, level: int, at: datetime) -> None:
    before = _one(conn, "SELECT level FROM world_index_days WHERE exchange = %s AND day < %s ORDER BY day DESC LIMIT 1", (ex["code"], day))
    if not before:
        return
    move = (level - before["level"]) * BPS // max(before["level"], 1)
    if abs(move) < 600:
        return
    words = "falls" if move < 0 else "jumps"
    _alert(conn, kind="world_fall", now=at, headline=f"The {ex['index_name']} {words} {abs(move) / 100:.1f}% in a day",
           words=f"{ex['name']} in {ex['city']}: the {ex['index_name']} closed at {level / 100:,.2f}, {'down' if move < 0 else 'up'}"
                 f" {abs(move) / 100:.1f}% on the day.")
    _news(conn, "world_fall" if move < 0 else "world_rise", at,
          {"index": ex["index_name"], "city": ex["city"], "move": f"{abs(move) / 100:.1f}%", "level": f"{level / 100:,.2f}"})


def quote(conn: Connection, co: dict, now: datetime, *, path: _Path | None = None, ex: dict | None = None) -> dict:
    p = price_of(conn, co, now, path=path, ex=ex)
    return {"price": p, "bid": p * (BPS - data.WORLD_SPREAD_BPS) / BPS, "ask": p * (BPS + data.WORLD_SPREAD_BPS) / BPS}


def last_close(conn: Connection, company_id, before: date | None = None) -> Decimal | None:
    row = _one(conn, "SELECT close FROM world_days WHERE company_id = %s" + (" AND day < %s" if before else "") + " ORDER BY day DESC LIMIT 1",
               (company_id, before) if before else (company_id,))
    return row["close"] if row else None


# ---------------------------------------------------------------------------
# Opening the markets
# ---------------------------------------------------------------------------

def _account(conn: Connection, code: str, kind: str, name: str):
    row = _one(conn, "SELECT id FROM ledger_accounts WHERE code = %s", (code,))
    return row["id"] if row else ledger.create_account(conn, kind=kind, name=name, code=code)


def _first_economies(conn: Connection, period: int, now: datetime) -> None:
    for code, name, bank, trend, target, growth, inflation, rate, _ in data.WORLD_ECONOMIES:
        conn.execute("INSERT INTO world_economies (country, period, growth_bps, inflation_bps, rate_bps, words, at) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                     (code, period, growth, inflation, rate, f"{bank[0].upper() + bank[1:]} holds its rate at {_pct(rate)}.", now))


def economy(conn: Connection, country: str, period: int | None = None) -> dict | None:
    if period is None:
        return _one(conn, "SELECT * FROM world_economies WHERE country = %s ORDER BY period DESC LIMIT 1", (country,))
    return _one(conn, "SELECT * FROM world_economies WHERE country = %s AND period <= %s ORDER BY period DESC LIMIT 1", (country, period))


def long_rate_bps(country: str, rate_bps: int) -> int:
    """What lending for many years pays: halfway between the central bank's rate now and where it usually settles (its neutral
    rate plus its inflation target). Shares are valued on it, so one quarter's move in the rate counts for half."""
    e = ECONOMIES[country]
    return (rate_bps + e[8] + e[4]) // 2


def earnings_yield_bps(sector: str, rate_bps: int) -> int:
    """What investors want a share to earn a year, as a share of its price: the long interest rate, plus the extra for the risk
    of its kind of business, less the growth they expect of it for ever."""
    _, extra, growth = SECTORS[sector]
    low, high = data.WORLD_EARNINGS_YIELD_LIMITS_BPS
    return min(max(rate_bps + extra - growth, low), high)


def _fair(co: dict, eps_ttm: Decimal, rate_bps: int) -> Decimal:
    """`rate_bps` is the long rate (see long_rate_bps)."""
    ey = earnings_yield_bps(co["sector"], rate_bps)
    return max(eps_ttm * BPS / ey, Decimal("1"))


def setup(conn: Connection, now: datetime) -> bool:
    """The markets open the first time the world meets them after the currency desk: the exchanges and their economies,
    the companies and their shares (held by the rest of the world), the Nigerian arms' parents, the indexes and the ETFs."""
    if not ready(conn) or opened(conn) or not fx.opened(conn):
        return False
    world_abroad, _ = abroad.accounts(conn)
    registry = _account(conn, REGISTRY, "escrow", "The registries of the exchanges abroad")
    period = _closed_period(conn)
    for code, name, city, country, zone, currency, opens, closes, index_code, index_name in data.WORLD_EXCHANGES:
        conn.execute("INSERT INTO world_exchanges (code, name, city, country, zone, currency, opens, closes, index_code, index_name, opened_at)"
                     " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                     (code, name, city, country, zone, currency, time(*opens), time(*closes), index_code, index_name, now))
    _first_economies(conn, period, now)
    by_exchange = {e[0]: e for e in data.WORLD_EXCHANGES}
    for (ticker, name, exch, city, sector, revenue_m, shares_m, margin, payout, trend, beta, about) in data.WORLD_COMPANIES:
        asset = f"FSH-{ticker}"
        ledger.create_asset(conn, code=asset, kind="foreign_share", name=name, unit="share", issuer_account_id=registry)
        shares = shares_m * 1_000_000
        ledger.post(conn, kind="foreign_listing", memo=f"{name}: shares listed abroad, held by the rest of the world", period=period,
                    legs=[Leg(registry, -shares, asset), Leg(world_abroad, shares, asset)])
        revenue = revenue_m * 100_000_000
        eps_ttm = Decimal(revenue) * margin / BPS * 4 / shares
        country = by_exchange[exch][3]
        co = {"sector": sector}
        fair = _fair(co, eps_ttm, long_rate_bps(country, ECONOMIES[country][7]))
        dps = (eps_ttm / 4 * payout / BPS).quantize(Decimal("0.0001"))
        row = _one(conn, "INSERT INTO world_companies (ticker, name, exchange, city, sector, asset, shares, revenue, margin_bps, payout_bps,"
                         " trend_bps, beta_bps, about, fair, eps_ttm, dps) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
                         " RETURNING id",
                   (ticker, name, exch, city, sector, asset, shares, revenue, margin, payout, trend, beta, about,
                    fair.quantize(Decimal("0.0001")), eps_ttm.quantize(Decimal("0.0001")), dps))
        conn.execute("INSERT INTO world_quotes (company_id, base, base_at) VALUES (%s, %s, %s)", (row["id"], fair.quantize(Decimal("0.0001")), now))
    _setup_arms(conn, now, period)
    _setup_indexes_and_etfs(conn, now, period)
    return True


def _setup_arms(conn: Connection, now: datetime, period: int) -> None:
    """The founders' stake in each Nigerian arm is the parent's: it is recorded as the parent's from now on."""
    founders = ledger.account_id(conn, ledger.INVESTORS_FOUNDERS)
    for nigerian, parent_ticker in data.WORLD_ARMS:
        company = _one(conn, "SELECT * FROM companies WHERE ticker = %s AND status = 'trading' AND listed", (nigerian,))
        parent = _one(conn, "SELECT * FROM world_companies WHERE ticker = %s", (parent_ticker,))
        if company is None or parent is None:
            continue
        held = ledger.balance(conn, founders, company["share_asset"])
        if held <= 0:
            continue
        account = _account(conn, PARENT_PREFIX + nigerian, "npc_investors", f"{parent['name']} (parent of {company['name']})")
        ledger.post(conn, kind="share_register", memo=f"{company['name']}: the founders' stake recorded as {parent['name']}'s", period=period,
                    legs=[Leg(founders, -held, company["share_asset"]), Leg(account, held, company["share_asset"])])
        conn.execute("INSERT INTO world_arms (company_id, parent_id, parent_account, words) VALUES (%s, %s, %s, %s)",
                     (company["id"], parent["id"], account, f"{company['name']} is the Nigerian arm of {parent['name']}."))


def _setup_indexes_and_etfs(conn: Connection, now: datetime, period: int) -> None:
    """Each exchange's index counted in naira on the Broad Street Exchange (what an ETF of it follows), and the computer's ETFs."""
    from simulation import etfs, indexes
    if not etfs.ready(conn) or not _one(conn, "SELECT 1 AS x FROM market_indexes LIMIT 1"):
        return
    from simulation import exchange
    # The bell's own trading day (a bell rung after 22:00 belongs to the day that just closed): the next bell counts the
    # first day's move, so an ETF and its index start together.
    day = exchange.session_of(now - timedelta(hours=1))[0]
    for code, name, city, country, zone, currency, opens, closes, index_code, index_name in data.WORLD_EXCHANGES:
        if _one(conn, "SELECT 1 AS x FROM market_indexes WHERE code = %s", (index_code,)):
            continue
        idx = _one(conn, "INSERT INTO market_indexes (code, name, kind, rule, rules_words, cap_bps, level, level_day, started_day, created_at,"
                         " div_period) VALUES (%s, %s, 'world', %s, %s, %s, %s, %s, %s, %s, %s) RETURNING *",
                   (index_code, f"{index_name} (in naira)", f"world:{code}",
                    indexes._rules_words("world", f"The ten companies listed on the {name}, counted in naira at the street's rate."),
                    data.INDEX_CAP_BPS, data.INDEX_START_LEVEL, day, day, now, period))
        plan = indexes.plan_for(conn, idx, now)
        indexes._install(conn, index_code, plan, indexes.prices_now(conn, [m["asset"] for m in plan], now), day)
        conn.execute("INSERT INTO index_levels (index_code, session_date, level) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                     (index_code, day, data.INDEX_START_LEVEL))
    households = ledger.account_id(conn, etfs.HOUSEHOLDS)
    for code, name, index_code, fee, seed in data.WORLD_ETFS:
        if _one(conn, "SELECT 1 AS x FROM etfs WHERE code = %s", (code,)):
            continue
        etf = etfs._new_etf(conn, code=code, name=name, index_code=index_code, commodity=None, leverage=10_000, method="full", fee=fee,
                            manager_id=None, computer=True, now=now, period=period,
                            words="Run by Broad Street Asset Management. It holds the foreign shares; its naira go abroad through the street.")
        units = seed * 100 // data.ETF_FIRST_NAV_KOBO // data.ETF_CREATION_UNITS * data.ETF_CREATION_UNITS
        if ledger.balance(conn, households) >= units * data.ETF_FIRST_NAV_KOBO * 2:
            etfs._create_cash(conn, etf, households, units, now, period, fee_bps=0)


def is_world_index(conn: Connection, index_code: str | None) -> bool:
    if not index_code:
        return False
    row = _one(conn, "SELECT kind FROM market_indexes WHERE code = %s", (index_code,))
    return bool(row and row["kind"] == "world")


# ---------------------------------------------------------------------------
# What foreign shares are worth in naira (for indexes, ETFs and net worth)
# ---------------------------------------------------------------------------

def _rate(conn: Connection, currency: str) -> int:
    """Kobo for one unit of the currency at the street's middle rate."""
    return fx.quote(conn, currency)["mid"]


def naira_prices(conn: Connection, assets: list[str], now: datetime) -> dict:
    """Kobo for one share of each, at its price now and the street's middle rate."""
    if not assets or not opened(conn):
        return {}
    path = _Path(conn)
    out = {}
    rates = {}
    for co in _rows(conn, "SELECT c.*, e.currency FROM world_companies c JOIN world_exchanges e ON e.code = c.exchange WHERE c.asset = ANY(%s)",
                    (list(assets),)):
        rates.setdefault(co["currency"], _rate(conn, co["currency"]))
        out[co["asset"]] = max(int(price_of(conn, co, now, path=path) * rates[co["currency"]] / 100), 1)
    return out


def index_candidates(conn: Connection, exchange_code: str, now: datetime) -> list[dict]:
    """The companies an exchange's index counts in naira, largest first, every share freely traded."""
    prices = naira_prices(conn, [r["asset"] for r in _rows(conn, "SELECT asset FROM world_companies WHERE exchange = %s", (exchange_code,))], now)
    out = []
    for co in _rows(conn, "SELECT * FROM world_companies WHERE exchange = %s ORDER BY ticker", (exchange_code,)):
        p = prices.get(co["asset"])
        if p:
            out.append({"id": co["id"], "asset": co["asset"], "ticker": co["ticker"], "name": co["name"], "sector": co["sector"], "price": p,
                        "free": co["shares"], "value": co["shares"] * p})
    return sorted(out, key=lambda c: -c["value"])


def income_per_unit(conn: Connection, assets: list[str], after_period: int, through_period: int) -> dict:
    """Dividends paid on one share of each, in naira at the time, in the quarters after one and up to another."""
    out: dict = {}
    if not assets or not ready(conn):
        return out
    for r in _rows(conn, "SELECT c.asset, sum(d.naira) AS per FROM world_dividends d JOIN world_companies c ON c.id = d.company_id"
                         " WHERE c.asset = ANY(%s) AND d.period > %s AND d.period <= %s GROUP BY c.asset", (list(assets), after_period, through_period)):
        out[r["asset"]] = Decimal(r["per"])
    return out


def etf_buy(conn: Connection, account, asset: str, units: int, price: int, period: int, memo: str) -> int:
    """An ETF (or an index fund) buys foreign shares with naira: the naira go to the rest of the world through the street, at
    half a percent over its middle rate. Returns the shares bought."""
    world_abroad, _ = abroad.accounts(conn)
    each = -(-price * (BPS + data.WORLD_ETF_DEAL_BPS + 10) // BPS)
    n = min(units, max(ledger.balance(conn, account), 0) // max(each, 1), ledger.balance(conn, world_abroad, asset))
    if n <= 0:
        return 0
    ledger.post(conn, kind="etf_basket", memo=memo, period=period,
                legs=[Leg(world_abroad, -n, asset), Leg(account, n, asset), Leg(account, -n * each), Leg(world_abroad, n * each)])
    fx._move_street(conn, fx.to_cents(n * each, fx.street(conn)))
    return n


def etf_sell(conn: Connection, account, asset: str, units: int, price: int, period: int, memo: str) -> int:
    world_abroad, _ = abroad.accounts(conn)
    each = max(price * (BPS - data.WORLD_ETF_DEAL_BPS - 10) // BPS, 1)
    n = min(units, ledger.balance(conn, account, asset), max(ledger.balance(conn, world_abroad), 0) // each)
    if n <= 0:
        return 0
    ledger.post(conn, kind="etf_basket", memo=memo, period=period,
                legs=[Leg(account, -n, asset), Leg(world_abroad, n, asset), Leg(world_abroad, -n * each), Leg(account, n * each)])
    fx._move_street(conn, -fx.to_cents(n * each, fx.street(conn)))
    return n


# ---------------------------------------------------------------------------
# Dealing: players and empires buy and sell with their dollars, pounds and euros
# ---------------------------------------------------------------------------

def _acting(conn: Connection, player_id, for_empire: bool) -> tuple:
    """(account, empire or None). For an empire, its head, its Investment Banker or its Asset Manager deals."""
    if not for_empire:
        account = ledger.player_account_id(conn, player_id)
        if account is None:
            raise WorldError("You need an account first.")
        return account, None
    seat = empires.seat_of(conn, player_id)
    if seat is None or seat["empire_status"] != "active" or seat["empire_kind"] == "pension":
        raise WorldError("You hold no seat in an open empire.")
    empire = empires._empire(conn, seat["empire_id"])
    if empire["head_player_id"] != player_id and seat["build"] not in ("investment_banker", "asset_manager"):
        raise WorldError("The head, the Investment Banker or the Asset Manager deals in foreign shares for the empire.")
    return empire["account_id"], empire


def _company(conn: Connection, ticker: str, *, lock: bool = False) -> dict:
    if not isinstance(ticker, str) or not ticker.isalpha():
        raise WorldError("There is no such company abroad.")
    co = _one(conn, "SELECT c.*, e.currency FROM world_companies c JOIN world_exchanges e ON e.code = c.exchange WHERE c.ticker = %s"
                    + (" FOR UPDATE OF c" if lock else ""), (ticker.upper(),))
    if co is None:
        raise WorldError("There is no such company abroad.")
    return co


def _whole(value, least: int = 1, most: int | None = None) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= least and (most is None or value <= most)


def _most_deal(conn: Connection, currency: str) -> int:
    """The largest deal, in the currency's cents: $2 million's worth."""
    return int(data.WORLD_MOST_DEAL_CENTS / fx.cross(conn, currency))


def deal(conn: Connection, player_id, ticker: str, side: str, shares: int, now: datetime, *, for_empire: bool = False) -> dict:
    """Buy or sell shares listed abroad, at once, while their exchange is open: from the brokers, at the price plus (or
    less) 0.15%, and what the deal itself moves the price."""
    if side not in ("buy", "sell"):
        raise WorldError("Buy or sell.")
    if not _whole(shares, 1, 10 ** 9):
        raise WorldError("Deal in whole shares.")
    with conn.transaction():
        if not opened(conn):
            raise WorldError("The markets abroad open at the next closing bell.")
        try:
            careers.books_open(conn, now)
        except careers.CareerError as closing:
            raise WorldError(str(closing)) from None
        account, _ = _acting(conn, player_id, for_empire)
        co = _company(conn, ticker, lock=True)
        ex = _exchange(conn, co["exchange"])
        if not is_open(ex, now):
            opens, closes = hours_in_lagos(ex, now)
            raise WorldError(f"The {ex['name']} is closed. It trades from {opens} to {closes}, Lagos time.")
        advance(conn, now)
        q = _quote_row(conn, co["id"], lock=True)
        path = _Path(conn)
        mid = price_of(conn, co, now, path=path, ex=ex, q=q)
        cur = co["currency"]
        value = int(mid * shares)
        if value > _most_deal(conn, cur):
            raise WorldError(f"Deal at most {_cash(_most_deal(conn, cur), cur)}'s worth at a time.")
        today = _one(conn, "SELECT coalesce(sum(shares), 0)::bigint AS n FROM world_trades WHERE account_id = %s AND company_id = %s AND at >= %s",
                     (account, co["id"], session(ex, local_day(ex, now))[0]))["n"]
        if (today + shares) * BPS > co["shares"] * data.WORLD_DAY_MOST_SHARES_BPS:
            raise WorldError(f"At most {co['shares'] * data.WORLD_DAY_MOST_SHARES_BPS // BPS:,} of its shares a day.")
        cap = Decimal(co["shares"]) * mid
        move = int(Decimal(value) * BPS * data.WORLD_IMPACT_TIMES / max(cap, Decimal(1)))
        signed = move if side == "buy" else -move
        # The deal is done halfway along its own push on the price: nobody buys before their own buying shows.
        dealt = mid * Decimal(str(math.exp(signed / 2 / BPS)))
        world_abroad, _ = abroad.accounts(conn)
        period = careers.world_now(conn, now)["period"]
        if side == "buy":
            each = int((dealt * (BPS + data.WORLD_SPREAD_BPS) / BPS).to_integral_value(rounding=ROUND_CEILING))
            amount = each * shares
            if ledger.balance(conn, account, cur) < amount:
                raise WorldError(f"That costs {_cash(amount, cur)}. Buy {fx.NAMES[cur].lower()}s on the Currencies tab first.")
            if ledger.balance(conn, world_abroad, co["asset"]) < shares:
                raise WorldError("The brokers have no more of its shares to sell.")
            ledger.post(conn, kind="fx_abroad", memo=f"Bought {shares:,} shares of {co['name']}", period=period,
                        legs=[Leg(account, -amount, cur), Leg(world_abroad, amount, cur), Leg(world_abroad, -shares, co["asset"]),
                              Leg(account, shares, co["asset"])])
        else:
            if ledger.balance(conn, account, co["asset"]) < shares:
                raise WorldError("You do not hold that many.")
            each = max(int(dealt * (BPS - data.WORLD_SPREAD_BPS) // BPS), 1)
            amount = each * shares
            ledger.post(conn, kind="fx_abroad", memo=f"Sold {shares:,} shares of {co['name']}", period=period,
                        legs=[Leg(account, -shares, co["asset"]), Leg(world_abroad, shares, co["asset"]), Leg(world_abroad, -amount, cur),
                              Leg(account, amount, cur)])
        conn.execute("UPDATE world_quotes SET impact_bps = greatest(least(impact_bps + %s, 800), -800) WHERE company_id = %s", (signed, co["id"]))
        rate = _rate(conn, cur)
        _own_people(conn, account, for_empire, player_id, co, side, ex, now)
        if for_empire:
            try:
                empires.foreign_deal(conn, player_id, fx.to_naira(amount, rate), f"{side} {shares:,} {co['ticker']} abroad", now)
            except empires.EmpireError as refused:
                raise WorldError(str(refused)) from None
        conn.execute("INSERT INTO world_trades (account_id, company_id, side, shares, price, amount, rate, period, at)"
                     " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)", (account, co["id"], side, shares, each, amount, rate, period, now))
        _position(conn, account, co, side, shares, amount, rate)
        return {"side": side, "ticker": co["ticker"], "shares": shares, "price": each, "amount": amount, "currency": cur}


def _own_people(conn: Connection, account, for_empire: bool, player_id, co: dict, side: str, ex: dict, now: datetime) -> None:
    """Nobody deals against their own empire: an empire's deal in a company abroad is refused if one of its people dealt in it
    the other way today, and a member's own deal if their empire did (so nobody can sell their own shares into the empire's
    buying)."""
    since = session(ex, local_day(ex, now))[0]
    seat = empires.seat_of(conn, player_id)
    if seat is None or seat["empire_kind"] == "pension":
        return
    if for_empire:
        others = [r["id"] for r in _rows(conn, "SELECT a.id FROM empire_seats s JOIN ledger_accounts a ON a.player_id = s.player_id WHERE s.empire_id = %s",
                                         (seat["empire_id"],))]
        whose = "One of the empire's people"
    else:
        others = [seat["account_id"]]
        whose = "Your empire"
    if _one(conn, "SELECT 1 AS x FROM world_trades WHERE account_id = ANY(%s) AND company_id = %s AND side <> %s AND at >= %s LIMIT 1",
            (others, co["id"], side, since)):
        raise WorldError(f"{whose} dealt in {co['name']} the other way today. Nobody deals against their own empire.")


def _position(conn: Connection, account, co: dict, side: str, shares: int, amount: int, rate: int) -> None:
    pos = _one(conn, "SELECT * FROM world_positions WHERE account_id = %s AND company_id = %s FOR UPDATE", (account, co["id"]))
    if side == "buy":
        conn.execute("INSERT INTO world_positions (account_id, company_id, cost, cost_naira) VALUES (%s, %s, %s, %s)"
                     " ON CONFLICT (account_id, company_id) DO UPDATE SET cost = world_positions.cost + EXCLUDED.cost,"
                     " cost_naira = world_positions.cost_naira + EXCLUDED.cost_naira",
                     (account, co["id"], amount, fx.to_naira(amount, rate)))
        return
    if pos is None:
        return
    held_before = ledger.balance(conn, account, co["asset"]) + shares
    keep = Decimal(held_before - shares) / Decimal(max(held_before, 1))
    conn.execute("UPDATE world_positions SET cost = %s, cost_naira = %s WHERE account_id = %s AND company_id = %s",
                 (int(pos["cost"] * keep), int(pos["cost_naira"] * keep), account, co["id"]))


# ---------------------------------------------------------------------------
# At the close: the economies abroad, the companies' quarters, dividends
# ---------------------------------------------------------------------------

def _oil_change_bps(conn: Connection, period: int) -> int:
    now, before = abroad.state(conn, period - 1), abroad.state(conn, period - 2)
    if not now or not before:
        return 0
    return (now["oil_cents"] - before["oil_cents"]) * BPS // max(before["oil_cents"], 1)


def _round_step(value: float) -> int:
    step = data.WORLD_RATE_STEP_BPS
    return int(round(value / step) * step)


def _economies_close(conn: Connection, period: int, now: datetime, seed: str) -> dict:
    """Each economy's quarter: growth back towards its trend with the world's swings, inflation back towards 2% (higher when
    growth runs hot or oil is dearer), and the central bank's rate moved part of the way to what its rule says."""
    common = stochastic.factor(seed, "economy", period) * 0.5 + stochastic.normal(seed, "world", "cycle", period) * 0.85
    oil = _oil_change_bps(conn, period)
    out = {}
    for code, name, bank, trend, target, *_rest in data.WORLD_ECONOMIES:
        neutral = _rest[-1]
        was = economy(conn, code)
        g = was["growth_bps"] + (trend - was["growth_bps"]) * data.WORLD_GROWTH_RETURN_BPS / BPS
        g += (common + stochastic.normal(seed, "world", code, "growth", period) * 0.8) * data.WORLD_GROWTH_SHOCK_BPS
        g = int(min(max(g, -800), 900))
        inf = was["inflation_bps"] + (target - was["inflation_bps"]) * data.WORLD_INFLATION_RETURN_BPS / BPS
        inf += (g - trend) * data.WORLD_INFLATION_HEAT_BPS / BPS + oil * data.WORLD_INFLATION_OIL_BPS / BPS
        inf += stochastic.normal(seed, "world", code, "inflation", period) * data.WORLD_INFLATION_SHOCK_BPS
        inf = int(min(max(inf, -300), 1_500))
        rule = neutral + inf + (inf - target) * 0.5 + (g - trend) * 0.5
        low, high = data.WORLD_RATE_LIMITS_BPS
        rate = was["rate_bps"] + (rule - was["rate_bps"]) * data.WORLD_RATE_SPEED_BPS / BPS
        rate = min(max(_round_step(rate), low), high)
        move = rate - was["rate_bps"]
        who = bank[0].upper() + bank[1:]
        if move > 0:
            words = f"{who} raises its rate by {_pct(move)} to {_pct(rate)}, with inflation at {_pct(inf)}."
        elif move < 0:
            words = f"{who} cuts its rate by {_pct(-move)} to {_pct(rate)}, with inflation at {_pct(inf)}."
        else:
            words = f"{who} holds its rate at {_pct(rate)}."
        conn.execute("INSERT INTO world_economies (country, period, growth_bps, inflation_bps, rate_bps, words, at) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                     (code, period, g, inf, rate, words, now))
        out[code] = {"name": name, "bank": who, "growth": g, "inflation": inf, "rate": rate, "move": move, "words": words}
    return out


def _companies_close(conn: Connection, period: int, now: datetime, seed: str, path: _Path) -> None:
    """Each company's quarter (sales, profit, dividend), what its share is now worth, the price moved halfway there at
    once, and the dividend paid."""
    oil_now = abroad.state(conn, period - 1)
    oil_ratio = (oil_now["oil_cents"] / data.OIL_START_CENTS / abroad.world_prices(period)) if oil_now else 1.0
    metals = _one(conn, "SELECT metals_bps FROM economy_results WHERE period = %s", (period - 1,))
    metals_ratio = (metals["metals_bps"] / BPS) if metals else 1.0
    received: dict = {}
    for co in _rows(conn, "SELECT c.*, e.currency, e.country FROM world_companies c JOIN world_exchanges e ON e.code = c.exchange ORDER BY c.ticker"):
        home = economy(conn, co["country"])
        trend = ECONOMIES[co["country"]][3]
        beta = co["beta_bps"] / BPS
        growth = (home["growth_bps"] + co["trend_bps"] + (home["growth_bps"] - trend) * (beta - 1) * 2) / 4 / BPS
        swing = stochastic.normal(seed, "world", co["ticker"], "sales", period) * data.WORLD_REVENUE_SWING_BPS / BPS
        revenue = max(int(co["revenue"] * (1 + growth + swing) * (1 + 0.025 / 4)), 1)
        margin = co["margin_bps"] + (home["growth_bps"] - trend) * beta * 0.8
        margin += stochastic.normal(seed, "world", co["ticker"], "margin", period) * data.WORLD_MARGIN_SWING_BPS
        sales = revenue
        if co["sector"] == "oil_gas":
            sales = int(revenue * oil_ratio)
            margin += (oil_ratio - 1) * 1_500
        elif co["sector"] == "mining":
            sales = int(revenue * metals_ratio)
            margin += (metals_ratio - 1) * 1_500
        elif co["sector"] in ("banking", "insurance"):
            margin += (home["rate_bps"] - 300) * 1.5
        margin = int(min(max(margin, -3_000), 6_000))
        profit = sales * margin // BPS
        eps = Decimal(profit) / co["shares"]
        earlier = [r["eps"] for r in _rows(conn, "SELECT eps FROM world_results WHERE company_id = %s ORDER BY period DESC LIMIT 3", (co["id"],))]
        eps_ttm = eps + sum(earlier) + (co["eps_ttm"] / 4) * (3 - len(earlier))
        dps = max(eps_ttm / 4 * co["payout_bps"] / BPS, Decimal(0)).quantize(Decimal("0.0001"))
        long_rate = long_rate_bps(co["country"], home["rate_bps"])
        # Investors look through a bad year: a share is valued on at least 40% of what it earns at its usual margin.
        usual = Decimal(sales) * 4 * co["margin_bps"] / BPS / co["shares"] * Decimal("0.4")
        fair = _fair(co, max(eps_ttm, usual), long_rate).quantize(Decimal("0.0001"))
        pe = (Decimal(BPS) / earnings_yield_bps(co["sector"], long_rate)).quantize(Decimal("0.01"))
        before = co["fair"]
        surprise = (fair / before - 1) * 100 if before else Decimal(0)
        words = (f"Sales {_cash(sales, co['currency'])}, profit {_cash(profit, co['currency'])};"
                 f" worth about {_cash(fair, co['currency'])} a share ({'up' if surprise >= 0 else 'down'} {abs(float(surprise)):.1f}%).")
        conn.execute("INSERT INTO world_results (company_id, period, revenue, profit, eps, dps, fair, pe, words) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                     (co["id"], period, sales, profit, eps.quantize(Decimal("0.0001")), dps, fair, pe, words[:300]))
        conn.execute("UPDATE world_companies SET revenue = %s, fair = %s, eps_ttm = %s, dps = %s WHERE id = %s",
                     (revenue, fair, eps_ttm.quantize(Decimal("0.0001")), dps, co["id"]))
        co = {**co, "fair": fair}
        if before and before > 0:
            _rebase(conn, co, now, float(fair / before) ** (data.WORLD_NEWS_PRICED_BPS / BPS), path)
        _pay_dividend(conn, co, dps, period, now, path, received)
    # One pop-up for each holder: everything their foreign shares paid them this quarter.
    for account, got in received.items():
        total = ", ".join(_cash(v, c) for c, v in sorted(got.items()))
        _alert(conn, kind="world_dividend", now=now, account=account, headline=f"Your foreign shares paid {total} in dividends",
               words="Paid into your dollar, pound and euro balances, after 15% tax kept abroad.")


def _pay_dividend(conn: Connection, co: dict, dps: Decimal, period: int, now: datetime, path: _Path, received: dict | None = None) -> None:
    """The dividend, after the tax kept abroad, to everybody holding the shares outside the rest of the world: players and
    empires in the currency; funds and ETFs in naira at the street's middle rate (less half a percent). The price falls by it."""
    if dps <= 0:
        return
    world_abroad, _ = abroad.accounts(conn)
    registry = ledger.account_id(conn, REGISTRY)
    net = dps * (BPS - data.WORLD_WITHHOLDING_BPS) / BPS
    rate = _rate(conn, co["currency"])
    naira_each = net * rate / 100
    holders = _rows(conn, "SELECT b.account_id, b.balance::bigint AS units, a.kind FROM ledger_balances b JOIN ledger_accounts a ON a.id = b.account_id"
                          " WHERE b.asset = %s AND b.balance > 0 AND b.account_id <> ALL(%s) ORDER BY b.account_id",
                    (co["asset"], [world_abroad, registry]))
    paid = 0
    for h in holders:
        if h["kind"] in ("player", "empire"):
            amount = int(net * h["units"])
            if amount > 0:
                ledger.post(conn, kind="fx_abroad", memo=f"{co['name']}: dividend, after tax kept abroad", period=period,
                            legs=[Leg(world_abroad, -amount, co["currency"]), Leg(h["account_id"], amount, co["currency"])])
                paid += amount
                if received is not None:
                    got = received.setdefault(h["account_id"], {})
                    got[co["currency"]] = got.get(co["currency"], 0) + amount
        else:
            kobo = int(naira_each * (BPS - data.WORLD_ETF_DEAL_BPS) / BPS * h["units"])
            kobo = min(kobo, max(ledger.balance(conn, world_abroad), 0))
            if kobo > 0:
                ledger.transfer(conn, payer=world_abroad, receiver=h["account_id"], amount=kobo, kind="fx_abroad",
                                memo=f"{co['name']}: dividend, after tax kept abroad, changed into naira", period=period)
                paid += fx.to_cents(kobo, rate)
    conn.execute("INSERT INTO world_dividends (company_id, period, per_share, naira, paid) VALUES (%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
                 (co["id"], period, net.quantize(Decimal("0.0001")), naira_each.quantize(Decimal("0.0001")), paid))
    p = price_of(conn, co, now, path=path, with_impact=False)
    if p > 0:
        _rebase(conn, co, now, max(float((p - dps) / p), 0.5), path)


def at_close(conn: Connection, period: int, now: datetime) -> dict | None:
    """As a quarter closes (before the oil price and the naira are set for the next): the economies abroad, the central
    banks' rates, the companies' quarters and their dividends."""
    if not opened(conn) or _one(conn, "SELECT 1 AS x FROM world_economies WHERE period = %s LIMIT 1", (period,)):
        return None
    advance(conn, now)
    seed = _seed(conn)
    moves = _economies_close(conn, period, now, seed)
    _companies_close(conn, period, now, seed, _Path(conn))
    w = careers.world_now(conn, now)
    for code, m in moves.items():
        if m["move"] != 0:
            _alert(conn, kind="world_rate", now=now, headline=f"{m['bank']} {'raises' if m['move'] > 0 else 'cuts'} its rate to {_pct(m['rate'])}",
                   words=m["words"] + (" Higher rates abroad make Nigeria less attractive to foreign investors." if code == "US" and m["move"] > 0 else ""))
            _news(conn, "world_rates", now, {"bank": m["bank"], "country": m["name"], "rate": _pct(m["rate"]), "move": _pct(abs(m["move"])),
                                             "side": "raises" if m["move"] > 0 else "cuts", "inflation": _pct(m["inflation"])}, key=code)
    us, uk, ea = moves["US"], moves["UK"], moves["EA"]
    _news(conn, "world_growth", now, {"us": _pct(us["growth"]), "uk": _pct(uk["growth"]), "ea": _pct(ea["growth"]),
                                      "quarter": clock.period_label(period)}, key=str(w["period"]))
    return moves


# ---------------------------------------------------------------------------
# What the economies abroad do to Nigeria
# ---------------------------------------------------------------------------

def rate_abroad(conn: Connection) -> int:
    """What lending abroad pays: America's interest rate (before the markets open, the old fixed figure)."""
    if not opened(conn):
        return data.WORLD_RATE_BPS
    return economy(conn, "US")["rate_bps"]


def inflation_abroad(conn: Connection) -> int:
    if not opened(conn):
        return data.WORLD_INFLATION_BPS
    return economy(conn, "US")["inflation_bps"]


def oil_demand_bps(conn: Connection, period: int) -> int:
    """How much growth abroad above (or below) its trend lifts (or lowers) the next oil price."""
    if not opened(conn):
        return 0
    gap = 0.0
    for code, w in data.WORLD_OIL_WEIGHTS.items():
        e = economy(conn, code, period)
        if e is None or e["period"] != period:
            return 0
        gap += (e["growth_bps"] - ECONOMIES[code][3]) * w / BPS
    return int(gap * data.WORLD_OIL_DEMAND_BPS / 100)


def cross_next(conn: Connection, period: int, gbp: float, eur: float) -> tuple[float, float] | None:
    """The pound and the euro against the dollar for the next quarter: up when their interest rates rise against America's
    (or their growth runs faster), pulled back a little towards their usual levels, and their own swing. None before the
    markets open (the old wandering applies)."""
    if not opened(conn):
        return None
    rows = {(r["country"], r["period"]): r for r in _rows(conn, "SELECT * FROM world_economies WHERE period IN (%s, %s)", (period, period - 1))}
    if ("US", period) not in rows or ("US", period - 1) not in rows:
        return None
    seed = _seed(conn)
    out = []
    for code, value, start, name in (("UK", gbp, data.FX_GBP_USD_START, "gbp"), ("EA", eur, data.FX_EUR_USD_START, "eur")):
        diff_now = rows[(code, period)]["rate_bps"] - rows[("US", period)]["rate_bps"]
        diff_before = rows[(code, period - 1)]["rate_bps"] - rows[("US", period - 1)]["rate_bps"]
        growth_gap = (rows[(code, period)]["growth_bps"] - ECONOMIES[code][3]) - (rows[("US", period)]["growth_bps"] - ECONOMIES["US"][3])
        # (Rates and growth in basis points: a hundred of them is a point.)
        move = (diff_now - diff_before) / 100 * data.WORLD_CROSS_RATE_BPS / BPS + growth_gap / 100 * data.WORLD_CROSS_GROWTH_BPS / BPS / 4
        move += stochastic.normal(seed, "fx", name, period) * data.FX_CROSS_SWING_BPS / BPS * 0.7
        v = value + (start - value) * data.FX_CROSS_RETURN_BPS / BPS
        out.append(v * (1 + move))
    return out[0], out[1]


# ---------------------------------------------------------------------------
# After the Central Bank's move: parents send dividends home, and some decide to leave
# ---------------------------------------------------------------------------

def _arm_company(conn: Connection, arm: dict) -> dict:
    return _one(conn, "SELECT * FROM companies WHERE id = %s", (arm["company_id"],))


def _parent(conn: Connection, arm: dict) -> dict:
    return _one(conn, "SELECT * FROM world_companies WHERE id = %s", (arm["parent_id"],))


def parent_room(conn: Connection) -> int:
    """Dollars (cents) the parents abroad may send home this quarter between them: at most 3% of the reserves, less as the
    reserves fall below comfortable, none under one quarter of imports. A floating naira: as much as they like, at the street."""
    q = fx.current(conn)
    if q is None:
        return 0
    if q["regime"] == "float":
        return BIG
    cb = ledger.account_id(conn, ledger.CENTRAL_BANK)
    reserves = ledger.balance(conn, cb, "USD")
    share = min(max((q["cover_bps"] - data.FX_FLOAT_COVER_BPS) / (data.FX_COMFORT_COVER_BPS - data.FX_FLOAT_COVER_BPS), 0), 1)
    return int(apply_bps(reserves, data.WORLD_PARENT_ROOM_BPS) * share)


def _repatriate(conn: Connection, period: int, now: datetime) -> None:
    arms = _rows(conn, "SELECT * FROM world_arms ORDER BY company_id")
    waiting = {a["company_id"]: max(ledger.balance(conn, a["parent_account"]), 0) for a in arms}
    total = sum(waiting.values())
    if total <= 0:
        for a in arms:
            conn.execute("INSERT INTO world_repatriation (company_id, period, waiting, sent, dollars) VALUES (%s, %s, 0, 0, 0) ON CONFLICT DO NOTHING",
                         (a["company_id"], period))
        return
    room = parent_room(conn)
    q = fx.current(conn)
    rate = fx.official(conn) if q["regime"] == "managed" else fx.street(conn)
    room_kobo = BIG if room >= BIG else fx.to_naira(room, rate)
    world_abroad, _ = abroad.accounts(conn)
    for a in arms:
        have = waiting[a["company_id"]]
        share = have if room_kobo >= total else room_kobo * have // max(total, 1)
        sent, dollars = 0, 0
        if share > 0:
            parent = _parent(conn, a)
            if q["regime"] == "managed":
                before = ledger.balance(conn, a["parent_account"])
                cb_short = ledger.balance(conn, ledger.account_id(conn, ledger.CENTRAL_BANK), "USD") < fx.to_cents(share, rate)
                dollars = fx._buy_dollars(conn, a["parent_account"], fx.to_cents(share, rate), [(world_abroad, 1)], period,
                                          f"{parent['name']}: dividends sent home", most=share)
                sent = before - ledger.balance(conn, a["parent_account"])
                if cb_short and dollars > 0:
                    fx._move_street(conn, dollars)          # (the Central Bank had too few: they were bought on the street)
            else:
                sent = ledger.pay_up_to(conn, payer=a["parent_account"], receiver=world_abroad, wanted=share, kind="fx_abroad",
                                        memo=f"{parent['name']}: dividends sent home through the street", period=period)
                dollars = fx.to_cents(sent, rate)
                fx._move_street(conn, dollars)
        conn.execute("INSERT INTO world_repatriation (company_id, period, waiting, sent, dollars) VALUES (%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
                     (a["company_id"], period, have, sent, dollars))


def trapped(conn: Connection, arm: dict) -> int:
    return max(ledger.balance(conn, arm["parent_account"]), 0)


def _yearly_dividends_to_parent(conn: Connection, arm: dict, company: dict) -> int:
    rows = _rows(conn, "SELECT dividends_paid, shares_in_issue FROM company_results WHERE company_id = %s ORDER BY period DESC LIMIT 4", (company["id"],))
    held = ledger.balance(conn, arm["parent_account"], company["share_asset"])
    return sum(r["dividends_paid"] * held // max(r["shares_in_issue"], 1) for r in rows)


def _decide(conn: Connection, period: int, now: datetime, seed: str) -> None:
    """Each parent still here weighs leaving: years of dividends stuck in naira, or a naira that has lost much of its value."""
    for arm in _rows(conn, "SELECT * FROM world_arms WHERE status = 'parent' ORDER BY company_id FOR UPDATE"):
        company = _arm_company(conn, arm)
        if ledger.balance(conn, arm["parent_account"], company["share_asset"]) <= 0:
            # It sold everything to a takeover offer: it has left.
            parent = _parent(conn, arm)
            conn.execute("UPDATE world_arms SET status = 'left', sold_to = 'a takeover offer', sold_period = %s, words = %s WHERE company_id = %s",
                         (period, f"{parent['name']} sold its stake to a takeover offer in {clock.period_label(period)}.", arm["company_id"]))
            continue
        if company["status"] != "trading":
            continue
        stuck = trapped(conn, arm)
        yearly = _yearly_dividends_to_parent(conn, arm, company)
        q_now = _one(conn, "SELECT market FROM fx_quarters WHERE period <= %s ORDER BY period DESC LIMIT 1", (period,))
        q_then = _one(conn, "SELECT market FROM fx_quarters WHERE period <= %s ORDER BY period DESC LIMIT 1", (period - 8,))
        fall = (q_now["market"] - q_then["market"]) * BPS // max(q_now["market"], 1) if q_now and q_then else 0
        reason = (yearly > 0 and stuck >= yearly * data.WORLD_PARENT_TRAPPED_YEARS) or fall >= data.WORLD_PARENT_NAIRA_FALL_BPS
        if not reason:
            conn.execute("UPDATE world_arms SET pressure = 0 WHERE company_id = %s", (arm["company_id"],))
            if yearly > 0 and stuck >= yearly:
                _trapped_alert(conn, arm, company, stuck, now, period)
            continue
        conn.execute("UPDATE world_arms SET pressure = pressure + 1 WHERE company_id = %s", (arm["company_id"],))
        if stuck > 0:
            _trapped_alert(conn, arm, company, stuck, now, period)
        roll = stochastic._unit(seed, "world", "leave", company["ticker"], period)
        if roll * BPS < data.WORLD_PARENT_LEAVE_CHANCE_BPS:
            _announce_leaving(conn, arm, company, period, now, stuck, fall)


def _trapped_alert(conn: Connection, arm: dict, company: dict, stuck: int, now: datetime, period: int) -> None:
    if _one(conn, "SELECT 1 AS x FROM fx_alerts WHERE kind = 'world_trapped' AND headline LIKE %s AND at > %s",
            (f"%{company['name']}%", now - timedelta(days=6))):
        return
    parent = _parent(conn, arm)
    _alert(conn, kind="world_trapped", now=now, headline=f"{_money(stuck)} of {company['name']}'s dividends wait for dollars",
           words=f"{parent['name']} cannot send its dividends from {company['name']} home: the Central Bank has too few dollars to spare.")
    _news(conn, "world_trapped", now, {"parent": parent["name"], "company": company["name"], "amount": _money(stuck), "ticker": company["ticker"]},
          key=company["ticker"], tickers=[company["ticker"]])


def _announce_leaving(conn: Connection, arm: dict, company: dict, period: int, now: datetime, stuck: int, fall: int) -> None:
    parent = _parent(conn, arm)
    why = (f"{_money(stuck)} of its dividends are stuck waiting for dollars" if stuck > 0 and fall < data.WORLD_PARENT_NAIRA_FALL_BPS
           else f"the naira has lost {fall / 100:.0f}% of its value in two years")
    conn.execute("UPDATE world_arms SET status = 'leaving', announced_period = %s, deadline_period = %s, asking_bps = %s, words = %s"
                 " WHERE company_id = %s",
                 (period, period + data.WORLD_PARENT_SALE_QUARTERS, data.WORLD_PARENT_ASKING_BPS,
                  f"{parent['name']} is selling its stake and leaving Nigeria: {why}.", arm["company_id"]))
    held = ledger.balance(conn, arm["parent_account"], company["share_asset"])
    _alert(conn, kind="world_exit", now=now, headline=f"{parent['name']} is leaving Nigeria: its stake in {company['name']} is for sale",
           words=f"For two quarters empires may buy pieces of its {held:,} shares at the market price (Markets, World markets),"
                 " and any takeover offer gets them. What is left then goes to the pension funds.")
    _news(conn, "world_leaving", now, {"parent": parent["name"], "company": company["name"], "why": why, "ticker": company["ticker"]},
          key=company["ticker"], tickers=[company["ticker"]])


def market_price(conn: Connection, company_id) -> int:
    row = _one(conn, "SELECT coalesce(last_price, reference_price) AS p FROM market_instruments WHERE company_id = %s", (company_id,))
    return row["p"] if row else 0


def stake_price(conn: Connection, company_id) -> int:
    """What a leaving parent asks for each share: the highest of the last trade, the last session's settled price and the average
    price of the last five sessions' trades. One small trade cannot pull it down."""
    m = _one(conn, "SELECT last_price, reference_price FROM market_instruments WHERE company_id = %s", (company_id,)) or {}
    vwap = _one(conn, "SELECT (sum(price * quantity) / nullif(sum(quantity), 0))::bigint AS p FROM market_trades WHERE company_id = %s"
                      " AND session_date >= (SELECT coalesce(max(session_date), '1900-01-01'::date) - 4 FROM market_trades WHERE company_id = %s)",
                (company_id, company_id))["p"]
    return max(m.get("last_price") or 0, m.get("reference_price") or 0, vwap or 0, 1)


def _deadlines(conn: Connection, period: int, now: datetime) -> None:
    """A leaving parent whose stake is gone has left; at its deadline what is left goes to the pension funds, 20% below the market."""
    funds = ledger.account_id(conn, ledger.INVESTORS_INSTITUTIONS)
    for arm in _rows(conn, "SELECT * FROM world_arms WHERE status = 'leaving' ORDER BY company_id FOR UPDATE"):
        company = _arm_company(conn, arm)
        parent = _parent(conn, arm)
        held = ledger.balance(conn, arm["parent_account"], company["share_asset"])
        if held > 0 and period >= arm["deadline_period"]:
            price = max(stake_price(conn, company["id"]) * (BPS - data.WORLD_PARENT_FINAL_BPS) // BPS, 1)
            n = min(held, max(ledger.balance(conn, funds), 0) // 2 // price)
            if n > 0:
                ledger.post(conn, kind="share_trade", memo=f"{parent['name']} sells its stake in {company['name']} to the pension funds", period=period,
                            legs=[Leg(arm["parent_account"], -n, company["share_asset"]), Leg(funds, n, company["share_asset"]),
                                  Leg(funds, -n * price), Leg(arm["parent_account"], n * price)])
                conn.execute("INSERT INTO world_stake_sales (company_id, buyer, account_id, shares, price, period, at) VALUES (%s, 'the pension funds', %s, %s, %s, %s, %s)",
                             (company["id"], funds, n, price, period, now))
            held -= n
        if held <= 0:
            # Who bought is said by kind only: what one empire holds is its own business.
            kinds = [r["k"] for r in _rows(conn, "SELECT DISTINCT CASE WHEN buyer = 'the pension funds' THEN 1 ELSE 2 END AS k FROM world_stake_sales"
                                                 " WHERE company_id = %s ORDER BY 1", (company["id"],))]
            sold_to = " and ".join({1: "the pension funds", 2: "empires"}[k] for k in kinds) or "a takeover offer"
            conn.execute("UPDATE world_arms SET status = 'left', sold_to = %s, sold_period = %s, words = %s WHERE company_id = %s",
                         (sold_to[:200], period, f"{parent['name']} sold its stake and left Nigeria in {clock.period_label(period)}.", arm["company_id"]))
            _alert(conn, kind="world_sold", now=now, headline=f"{parent['name']} has left Nigeria",
                   words=f"Its stake in {company['name']} went to {sold_to}. Dividends still waiting for dollars will be sent home as they can.")
            _news(conn, "world_sold", now, {"parent": parent["name"], "company": company["name"], "buyer": sold_to, "ticker": company["ticker"]},
                  key=company["ticker"], tickers=[company["ticker"]])


def buy_stake(conn: Connection, player_id, ticker: str, shares: int, now: datetime) -> dict:
    """The head of an empire buys part of a leaving parent's stake, at the market price, staying under 30%."""
    from simulation import firm_dealmaking
    if not _whole(shares, 1, 10 ** 12):
        raise WorldError("Buy a whole number of shares.")
    with conn.transaction():
        try:
            careers.books_open(conn, now)
        except careers.CareerError as closing:
            raise WorldError(str(closing)) from None
        try:
            empire = empires._head(conn, player_id)
        except empires.EmpireError:
            raise WorldError("Only the head of an empire buys a parent's stake.") from None
        if empire["kind"] == "pension":
            raise WorldError("A pension empire does not buy stakes.")
        company = _one(conn, "SELECT * FROM companies WHERE ticker = %s", (str(ticker).upper(),))
        arm = _one(conn, "SELECT * FROM world_arms WHERE company_id = %s FOR UPDATE", (company["id"],)) if company else None
        if arm is None or arm["status"] != "leaving":
            raise WorldError("That company's parent is not selling.")
        held = ledger.balance(conn, arm["parent_account"], company["share_asset"])
        if shares > held:
            raise WorldError(f"The parent has {held:,} shares left to sell.")
        try:
            firm_dealmaking.buying_guard(conn, empire["id"], company["id"], shares)
        except empires.EmpireError as refused:
            raise WorldError(str(refused)) from None
        price = max(stake_price(conn, company["id"]) * (BPS - arm["asking_bps"]) // BPS, 1)
        cost = price * shares
        if ledger.balance(conn, empire["account_id"]) < cost:
            raise WorldError(f"That costs {_money(cost)}. The empire has not that much cash.")
        period = careers.world_now(conn, now)["period"]
        parent = _parent(conn, arm)
        ledger.post(conn, kind="share_trade", memo=f"{empire['name']} buys part of {parent['name']}'s stake in {company['name']}", period=period,
                    legs=[Leg(arm["parent_account"], -shares, company["share_asset"]), Leg(empire["account_id"], shares, company["share_asset"]),
                          Leg(empire["account_id"], -cost), Leg(arm["parent_account"], cost)])
        conn.execute("INSERT INTO world_stake_sales (company_id, buyer, account_id, shares, price, period, at) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                     (company["id"], empire["name"], empire["account_id"], shares, price, period, now))
        empires._log(conn, empire["id"], f"The head bought {shares:,} shares of {company['name']} from its leaving parent for {_money(cost)}.", now)
        return {"shares": shares, "price": price, "cost": cost}


def leaving_parent(conn: Connection, company_id) -> dict | None:
    """The parent account of a Nigerian arm whose parent is selling (it gives its shares to any takeover offer)."""
    if not ready(conn):
        return None
    return _one(conn, "SELECT * FROM world_arms WHERE company_id = %s", (company_id,))


def _households(conn: Connection, period: int, now: datetime) -> None:
    """Households keep part of their index money in ETFs of foreign shares: more when the street pays well over the official
    rate (a way to hold something that does not fall with the naira)."""
    from simulation import etfs
    if not etfs.ready(conn):
        return
    vehicles = _rows(conn, "SELECT * FROM etfs WHERE status = 'open' AND method = 'full' AND index_code IN (SELECT code FROM market_indexes WHERE kind = 'world')"
                           " ORDER BY id")
    if not vehicles:
        return
    households = ledger.account_id(conn, etfs.HOUSEHOLDS)
    premium = max(fx.public(conn).get("gap_bps", 0), 0)
    share = data.WORLD_HOUSEHOLD_SHARE_BPS + premium * data.WORLD_HOUSEHOLD_PREMIUM_TIMES // 100
    target = etfs.passive_value(conn, now) * min(share, 1_500) // BPS
    have = sum(ledger.balance(conn, households, e["asset"]) * etfs.nav_now(conn, e, now) for e in vehicles)
    move = (target - have) * data.WORLD_HOUSEHOLD_STEP_BPS // BPS
    scores = [etfs._score(conn, "etf", e) for e in vehicles]
    total = sum(scores) or 1
    for e, sc in zip(vehicles, scores):
        amount = int(move * sc / total)
        nav = etfs.nav_now(conn, e, now)
        units = abs(amount) // max(nav, 1) // data.ETF_CREATION_UNITS * data.ETF_CREATION_UNITS
        if units <= 0:
            continue
        try:
            if amount > 0 and ledger.balance(conn, households) >= units * nav * 2:
                etfs._create_cash(conn, e, households, units, now, period, fee_bps=etfs.DEALING_COST_BPS)
            elif amount < 0:
                units = min(units, ledger.balance(conn, households, e["asset"]) // data.ETF_CREATION_UNITS * data.ETF_CREATION_UNITS)
                if units > 0:
                    etfs._redeem(conn, e, households, units, "cash", now, period, fee_bps=etfs.DEALING_COST_BPS)
        except etfs.EtfError:
            continue


def after_fx(conn: Connection, period: int, now: datetime) -> None:
    """After the Central Bank's move: parents send home what dividends they can; leaving parents' deadlines; parents weigh
    leaving; households' money in ETFs of foreign shares."""
    if not opened(conn) or _one(conn, "SELECT 1 AS x FROM world_repatriation WHERE period = %s LIMIT 1", (period,)):
        return
    seed = _seed(conn)
    _repatriate(conn, period, now)
    _deadlines(conn, period, now)
    _decide(conn, period, now, seed)
    _households(conn, period, now)


# ---------------------------------------------------------------------------
# The loop: closing prices written down, the markets opened at a bell
# ---------------------------------------------------------------------------

def tick(conn: Connection, now: datetime) -> int:
    if not ready(conn) or not _one(conn, "SELECT 1 AS x FROM world_state"):
        return 0
    if not opened(conn):
        if not fx.opened(conn):
            return 0
        bell = _one(conn, "SELECT rung_at FROM closing_bells WHERE rung_at <= %s ORDER BY session_date DESC LIMIT 1", (now,))
        if bell is None or not _one(conn, "SELECT 1 AS x FROM fx_progress WHERE dealt_through IS NOT NULL"):
            return 0
        try:
            with conn.transaction():
                setup(conn, bell["rung_at"])
        except Exception:
            log.exception("Opening the markets abroad failed")
            return 0
    if not _one(conn, "SELECT 1 AS x FROM market_indexes WHERE kind = 'world' LIMIT 1") and _one(conn, "SELECT 1 AS x FROM market_indexes LIMIT 1"):
        # The game's indexes and ETFs came after the markets abroad opened: their indexes and ETFs join them now.
        try:
            with conn.transaction():
                _setup_indexes_and_etfs(conn, now, _closed_period(conn))
        except Exception:
            log.exception("Setting up the indexes and ETFs of foreign shares failed")
    try:
        with conn.transaction():
            return advance(conn, now)
    except Exception:
        log.exception("Writing down the closing prices abroad failed")
        return 0


# ---------------------------------------------------------------------------
# Pop-ups and news (pop-ups share the currency desk's)
# ---------------------------------------------------------------------------

def _alert(conn: Connection, *, kind: str, headline: str, words: str, now: datetime, account=None) -> None:
    fx._alert(conn, kind=kind, headline=headline, words=words, now=now, account=account)


def _news(conn: Connection, kind: str, now: datetime, facts: dict, key: str = "", tickers=()) -> None:
    from simulation import news
    if kind not in news.BY_NAME:
        return
    w = careers.world_now(conn, now)
    news.publish(conn, period=w["period"], day=w["day"], kind=kind, story=f"world:{kind}:{key}:{w['period']}:{w['day']}", facts=facts,
                 tickers=tickers)


# ---------------------------------------------------------------------------
# Net worth and the books
# ---------------------------------------------------------------------------

def held_value(conn: Connection, account, now: datetime | None = None) -> int:
    """What an account's foreign shares are worth now (kobo): what the brokers would pay, at what the street pays for the currency."""
    if not opened(conn):
        return 0
    # Without a time (a closing bell's count of everybody's worth): the moment of the last closing bell, the world's own clock.
    now = now or (_one(conn, "SELECT max(rung_at) AS t FROM closing_bells")["t"] or _one(conn, "SELECT now() AS t")["t"])
    total = 0
    path = _Path(conn)
    for co in _rows(conn, "SELECT c.*, e.currency, b.balance::bigint AS held FROM world_companies c JOIN world_exchanges e ON e.code = c.exchange"
                          " JOIN ledger_balances b ON b.asset = c.asset WHERE b.account_id = %s AND b.balance > 0", (account,)):
        bid = price_of(conn, co, now, path=path) * (BPS - data.WORLD_SPREAD_BPS) / BPS
        total += int(bid * co["held"] * fx.quote(conn, co["currency"])["buy"] / 100)
    return total


def _players_world(conn: Connection) -> dict:
    out: dict = {}
    if not opened(conn):
        return out
    for r in _rows(conn, "SELECT DISTINCT b.account_id FROM ledger_balances b JOIN ledger_accounts a ON a.id = b.account_id"
                         " WHERE a.kind = 'player' AND b.balance > 0 AND b.asset LIKE 'FSH-%%'"):
        out[r["account_id"]] = (0, held_value(conn, r["account_id"]))
    return out


def _register() -> None:
    from simulation import marketview
    if _players_world not in marketview._OTHER_HOLDINGS:
        marketview._OTHER_HOLDINGS.append(_players_world)


_register()


def check_books(conn: Connection) -> list[str]:
    if not opened(conn):
        return []
    problems = []
    registry = ledger.account_id(conn, REGISTRY)
    for co in _rows(conn, "SELECT * FROM world_companies ORDER BY ticker"):
        out = -ledger.balance(conn, registry, co["asset"])
        if out != co["shares"]:
            problems.append(f"{co['name']}: {out} shares in issue against {co['shares']}.")
        held = _one(conn, "SELECT coalesce(sum(balance), 0)::bigint AS n FROM ledger_balances WHERE asset = %s AND balance > 0", (co["asset"],))["n"]
        if held != co["shares"]:
            problems.append(f"{co['name']}: {held} shares held against {co['shares']}.")
    return problems


# ---------------------------------------------------------------------------
# What players see
# ---------------------------------------------------------------------------

def _sector_name(sector: str) -> str:
    return SECTORS.get(sector, (sector.replace("_", " ").title(), 0, 0))[0]


def _companies_view(conn: Connection, now: datetime, path: _Path) -> list[dict]:
    out = []
    arms = {r["parent_id"]: r for r in _rows(conn, "SELECT a.parent_id, a.status, c.ticker, c.name FROM world_arms a JOIN companies c ON c.id = a.company_id")}
    exs = {e["code"]: e for e in exchanges(conn)}
    for co in _rows(conn, "SELECT c.*, e.currency FROM world_companies c JOIN world_exchanges e ON e.code = c.exchange ORDER BY array_position(ARRAY['HSE', 'THX', 'RMX'], c.exchange), c.ticker"):
        ex = exs[co["exchange"]]
        p = price_of(conn, co, now, path=path, ex=ex)
        prev = last_close(conn, co["id"], local_day(ex, now))            # the day before's close: today's move
        prev = prev or co["fair"]
        arm = arms.get(co["id"])
        out.append({
            "ticker": co["ticker"], "name": co["name"], "exchange": co["exchange"], "city": co["city"], "sector": _sector_name(co["sector"]),
            "currency": co["currency"], "price": float(p), "bid": float(p * (BPS - data.WORLD_SPREAD_BPS) / BPS),
            "ask": float(p * (BPS + data.WORLD_SPREAD_BPS) / BPS), "change_bps": int((p / prev - 1) * BPS) if prev else 0,
            "pe": round(float(p / co["eps_ttm"]), 1) if co["eps_ttm"] > 0 else None,
            "yield_bps": int(co["dps"] * 4 * BPS / p) if p > 0 else 0, "cap": int(p * co["shares"]),
            "arm": {"ticker": arm["ticker"], "name": arm["name"], "status": arm["status"]} if arm else None,
        })
    return out


def _wallet(conn: Connection, account, now: datetime, path: _Path) -> dict:
    holdings = []
    rows = _rows(conn, "SELECT c.*, e.currency, b.balance::bigint AS held, p.cost, p.cost_naira FROM world_companies c"
                       " JOIN world_exchanges e ON e.code = c.exchange JOIN ledger_balances b ON b.asset = c.asset"
                       " LEFT JOIN world_positions p ON p.account_id = b.account_id AND p.company_id = c.id"
                       " WHERE b.account_id = %s AND b.balance > 0 ORDER BY c.ticker", (account,))
    for r in rows:
        bid = price_of(conn, r, now, path=path) * (BPS - data.WORLD_SPREAD_BPS) / BPS
        value = int(bid * r["held"])
        rate = fx.quote(conn, r["currency"])["buy"]
        value_naira = value * rate // 100
        cost, cost_naira = r["cost"] or 0, r["cost_naira"] or 0
        share_gain = (value - cost) * rate // 100
        currency_gain = cost * rate // 100 - cost_naira
        holdings.append({"ticker": r["ticker"], "name": r["name"], "currency": r["currency"], "shares": r["held"], "price": float(bid),
                         "value": value, "value_naira": value_naira, "cost": cost, "cost_naira": cost_naira,
                         "share_gain_naira": share_gain, "currency_gain_naira": currency_gain})
    return {
        "balances": {c: ledger.balance(conn, account, c) for c in fx.CURRENCIES},
        "holdings": holdings, "worth": sum(h["value_naira"] for h in holdings),
        "trades": [{**t, "at": t["at"]} for t in _rows(conn, "SELECT c.ticker, t.side, t.shares, t.price, t.amount, e.currency, t.at FROM world_trades t"
                                                            " JOIN world_companies c ON c.id = t.company_id JOIN world_exchanges e ON e.code = c.exchange"
                                                            " WHERE t.account_id = %s ORDER BY t.id DESC LIMIT 15", (account,))],
    }


def economies_view(conn: Connection) -> dict:
    """The economies abroad, every quarter: growth, inflation and the central bank's rate (never its next move)."""
    if not opened(conn):
        return {"open": False}
    out = []
    for code, name, bank, trend, target, *_ in data.WORLD_ECONOMIES:
        rows = _rows(conn, "SELECT period, growth_bps, inflation_bps, rate_bps, words FROM world_economies WHERE country = %s ORDER BY period", (code,))
        out.append({"code": code, "name": name, "bank": bank[0].upper() + bank[1:], "trend_bps": trend, "target_bps": target,
                    "latest": rows[-1], "history": [{**r, "label": clock.period_label(r["period"] + 1)} for r in rows[-24:]]})
    q = fx.current(conn)
    return {"open": True, "economies": out, "gbp_usd": float(fx.cross(conn, "GBP")), "eur_usd": float(fx.cross(conn, "EUR")),
            "rate_abroad": rate_abroad(conn), "regime": q["regime"] if q else None,
            "rules": "Each central bank raises its rate when inflation runs above 2% or growth runs above its usual pace, and cuts it when they"
                     " fall below, moving part of the way each quarter in steps of a quarter point. America's rate is what lending abroad pays:"
                     " foreign investors in Nigeria want more of it when it is low. Growth abroad moves the oil price. The pound and the euro"
                     " rise against the dollar when their rates rise against America's."}


def page(conn: Connection, player_id, now: datetime) -> dict:
    if not opened(conn):
        return {"open": False}
    path = _Path(conn)
    exs = []
    for ex in exchanges(conn):
        opens, closes = hours_in_lagos(ex, now)
        days = list(reversed(_rows(conn, "SELECT day, level FROM world_index_days WHERE exchange = %s ORDER BY day DESC LIMIT 60", (ex["code"],))))
        live = None
        companies = _rows(conn, "SELECT * FROM world_companies WHERE exchange = %s", (ex["code"],))
        if days:
            closes_now = {c["id"]: price_of(conn, c, now, path=path, ex=ex) for c in companies}
            last_day = days[-1]["day"]
            prev = {r["company_id"]: r["close"] for r in _rows(conn, "SELECT company_id, close FROM world_days WHERE day = %s", (last_day,))}
            was = sum(Decimal(c["shares"]) * prev.get(c["id"], closes_now[c["id"]]) for c in companies)
            live = int(Decimal(days[-1]["level"]) * sum(Decimal(c["shares"]) * closes_now[c["id"]] for c in companies) / was) if was else days[-1]["level"]
        exs.append({"code": ex["code"], "name": ex["name"], "city": ex["city"], "currency": ex["currency"], "is_open": is_open(ex, now),
                    "opens": opens, "closes": closes, "next_change": next_change(ex, now), "index_name": ex["index_name"],
                    "index_code": ex["index_code"], "level": live, "close": days[-1]["level"] if days else None,
                    "days": days})
    me = ledger.player_account_id(conn, player_id)
    seat = empires.seat_of(conn, player_id)
    empire = empires._empire(conn, seat["empire_id"]) if seat and seat["empire_status"] == "active" and seat["empire_kind"] != "pension" else None
    can_empire = bool(empire and (empire["head_player_id"] == player_id or seat["build"] in ("investment_banker", "asset_manager")))
    arms = []
    for a in _rows(conn, "SELECT a.*, c.ticker, c.name, c.share_asset, w.name AS parent_name, w.ticker AS parent_ticker FROM world_arms a"
                         " JOIN companies c ON c.id = a.company_id JOIN world_companies w ON w.id = a.parent_id ORDER BY c.ticker"):
        arms.append(arm_view(conn, a, now))
    return {
        "open": True, "exchanges": exs, "companies": _companies_view(conn, now, path),
        "economies": economies_view(conn)["economies"],
        "mine": _wallet(conn, me, now, path) if me else None,
        "empire": {"name": empire["name"], **_wallet(conn, empire["account_id"], now, path)} if can_empire else None,
        "is_head": bool(empire and empire["head_player_id"] == player_id),
        "arms": arms,
        "etfs": [{"code": e["code"], "name": e["name"]} for e in _rows(conn, "SELECT code, name FROM etfs WHERE status = 'open' AND index_code IN"
                                                                       " (SELECT code FROM market_indexes WHERE kind = 'world') ORDER BY id")],
        "rules": {"spread_bps": data.WORLD_SPREAD_BPS, "withholding_bps": data.WORLD_WITHHOLDING_BPS, "most_deal_usd": data.WORLD_MOST_DEAL_CENTS},
    }


def arm_view(conn: Connection, a: dict, now: datetime) -> dict:
    company = _one(conn, "SELECT * FROM companies WHERE id = %s", (a["company_id"],))
    parent = _parent(conn, a)
    issued = ledger.amount_in_existence(conn, company["share_asset"])
    held = ledger.balance(conn, a["parent_account"], company["share_asset"])
    last = _one(conn, "SELECT * FROM world_repatriation WHERE company_id = %s ORDER BY period DESC LIMIT 1", (a["company_id"],))
    price = stake_price(conn, company["id"])
    return {"ticker": company["ticker"], "name": company["name"], "parent": parent["name"], "parent_ticker": parent["ticker"],
            "exchange": parent["exchange"], "status": a["status"], "stake_bps": held * BPS // max(issued, 1), "shares": held,
            "trapped": trapped(conn, a), "sent_last": last["sent"] if last else 0,
            "asking": max(price * (BPS - a["asking_bps"]) // BPS, 1) if a["status"] == "leaving" else None,
            "deadline": clock.period_label(a["deadline_period"]) if a["deadline_period"] else None, "words": a["words"]}


def arm_for(conn: Connection, ticker: str, now: datetime) -> dict | None:
    if not opened(conn):
        return None
    a = _one(conn, "SELECT a.* FROM world_arms a JOIN companies c ON c.id = a.company_id WHERE c.ticker = %s", (str(ticker).upper(),))
    return arm_view(conn, a, now) if a else None


def company_page(conn: Connection, ticker: str, now: datetime) -> dict:
    if not opened(conn):
        raise WorldError("The markets abroad open at the next closing bell.")
    co = _company(conn, ticker)
    ex = _exchange(conn, co["exchange"])
    path = _Path(conn)
    view = next(c for c in _companies_view(conn, now, path) if c["ticker"] == co["ticker"])
    results = _rows(conn, "SELECT period, revenue, profit, eps, dps, fair, pe, words FROM world_results WHERE company_id = %s ORDER BY period DESC LIMIT 12", (co["id"],))
    days = list(reversed(_rows(conn, "SELECT day, close FROM world_days WHERE company_id = %s ORDER BY day DESC LIMIT 90", (co["id"],))))
    opens, closes = hours_in_lagos(ex, now)
    return {**view, "about": co["about"], "shares": co["shares"], "exchange_name": ex["name"], "is_open": is_open(ex, now), "opens": opens,
            "closes": closes, "fair": float(co["fair"]), "eps_ttm": float(co["eps_ttm"]), "dps": float(co["dps"]),
            "results": [{**r, "label": clock.period_label(r["period"]), "eps": float(r["eps"]), "dps": float(r["dps"]), "fair": float(r["fair"]),
                         "pe": float(r["pe"])} for r in results],
            "days": [{"day": d["day"], "close": float(d["close"])} for d in days]}
