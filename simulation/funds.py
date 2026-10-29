"""Run Your Own Fund (the talent and funds stage, Part 2): open investment funds anybody may put money into.

An Asset Manager of Level 20 or above launches a fund: a name, a strategy, a yearly fee of at most 2%, a performance fee of
at most 20% of the gain above the fund's previous best, and the least an investor may put in. The manager puts in money of
their own first, and keeps at least 1% of the fund (or all they put in) while they run it.

A fund is a ledger account holding cash, shares and bonds, and a register of units. A unit is worth the fund's value
divided by the units in issue. Money comes in and goes out only at the next closing bell's price: an investor never knows
the price they will deal at, so nobody can buy into a rise they have already seen. Money waiting to come in is held in the
fund dealing account. Money coming in pays a quarter of one percent above the price, money going out a quarter below; the
difference stays in the fund, so the investors who stay do not pay for those who come and go.

Who invests: players, empires (their head, within what they may sign for), and the computer's own investors (the
households), who follow the star ratings: good funds draw money each quarter, poor ones lose it. When a fund falls 15% from
its high, or the banks panic, its computer investors run: they ask for their money back, bell after bell. The manager may
put up a gate (leavers are paid at most a tenth of the fund at a bell, for at most a game quarter) and must announce it.
To pay leavers a fund may borrow at most a tenth of itself, repaid as cash allows; it sells what it must.

The rules the game holds a manager to: the strategy (shares, banks, bonds, balanced or anything); no holding above 10% of
the fund; at least 5% in cash; no dealing with the manager or the manager's empire; no buying while leavers wait to be
paid. A manager dealing in a share for themselves just before the fund does is noted by the Money Watch (never shown).
What a fund held at a quarter's end is published one quarter later. Each quarter funds get one to five stars, against the
funds with the same strategy (or, with few of those, against the fund's benchmark).

A fund can be closed (everything sold to the market's dealers and the money paid out at a bell), merged into another fund
whose manager agrees (investors have three days to leave first), or closed by the game when it stays too small. A manager
proved to have taken the fund's money (a false cost in its books, which the regulator's audit may find) repays it with a
fine, is struck off, and the regulator winds the fund down with no fee.

Four computer-run funds are there from the start, one for each main strategy, so every player's fund has peers.
"""

from __future__ import annotations

import hashlib
import logging
import math
from datetime import date, datetime, timedelta

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from simulation import (
    bonds,
    careers,
    clock,
    empires,
    exchange,
    ledger,
    marketview,
    objectives,
)
from simulation import world_data as data
from simulation.money import BPS, apply_bps, naira

log = logging.getLogger("wsbm.funds")

UNIT = 1_000_000                       # unit prices in millionths of a kobo
FIRST_PRICE = 100 * UNIT               # the first unit costs ₦1
DEALING = "fund_dealing"               # the escrow account holding money waiting to come into a fund
HOUSEHOLDS = "households:lagos"        # the computer's own investors: the households' savings, held for them in Lagos
STRATEGIES = {
    "shares": "Nigerian shares", "banks": "Banks", "bonds": "Bonds and bills", "balanced": "Balanced (shares and bonds)",
    "anything": "Anything (shares and bonds, no fixed mix)",
}
STRATEGY_WORDS = {
    "shares": "Holds shares listed on the Broad Street Exchange, and cash.",
    "banks": "Holds shares in banks (at least 80% of what it holds), and cash.",
    "bonds": "Holds Government and company bonds and bills, and cash.",
    "balanced": "Holds shares and bonds, at most 70% of the fund in either.",
    "anything": "Holds shares and bonds in any mix the manager chooses.",
}
BENCHMARK_WORDS = {
    "shares": "the BSX 50", "banks": "the BSX 50", "anything": "the BSX 50",
    "bonds": "the Central Bank's rate, earned day by day", "balanced": "60% the BSX 50 and 40% the Central Bank's rate",
}
MERGE_NOTICE = timedelta(days=3)
MERGE_ANSWER_DAYS = 7


class FundError(Exception):
    """A request about a fund the rules do not allow. The words are for the player."""


def _rows(conn: Connection, sql: str, params=()) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def _one(conn: Connection, sql: str, params=()) -> dict | None:
    rows = _rows(conn, sql, params)
    return rows[0] if rows else None


def ready(conn: Connection) -> bool:
    return bool(_one(conn, "SELECT to_regclass('investment_funds') IS NOT NULL AS ok")["ok"])


def _money(kobo: int) -> str:
    return objectives._money(kobo)


def _pct(bps: int | None) -> str:
    return "n/a" if bps is None else f"{bps / 100:+.1f}%"


def name_key(name: str) -> str:
    return "".join(ch for ch in name.lower() if ch.isalnum())


def _state(conn: Connection, now: datetime) -> dict:
    try:
        careers.books_open(conn, now)
    except careers.CareerError as closing:
        raise FundError(str(closing)) from None
    return careers.world_now(conn, now)


def _roll(*parts) -> int:
    """A number from 0 to 9,999, fixed by what it is about."""
    return int(hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()[:8], 16) % BPS


def _policy_rate(conn: Connection) -> int:
    row = _one(conn, "SELECT next_policy_rate_bps FROM economy_results ORDER BY period DESC LIMIT 1")
    return row["next_policy_rate_bps"] if row else data.OPENING_RATE_BPS


def _bank_tickers(conn: Connection) -> set:
    return {r["ticker"] for r in _rows(conn, "SELECT ticker FROM companies WHERE sector = 'banking'")}


def dealing_account(conn: Connection):
    row = _one(conn, "SELECT id FROM ledger_accounts WHERE code = %s", (DEALING,))
    if row:
        return row["id"]
    return ledger.create_account(conn, kind="escrow", name="Fund dealing (money waiting to come into funds)", code=DEALING)


# ---------------------------------------------------------------------------
# A fund's value and its price
# ---------------------------------------------------------------------------

def _fund(conn: Connection, fund_id, *, lock: bool = False) -> dict:
    fund = _one(conn, "SELECT * FROM investment_funds WHERE id = %s" + (" FOR UPDATE" if lock else ""), (fund_id,))
    if fund is None:
        raise FundError("There is no such fund.")
    return fund


def owed(conn: Connection, fund: dict) -> int:
    return _one(conn, "SELECT coalesce(sum(owed), 0)::bigint AS o FROM fund_loans WHERE fund_id = %s AND status = 'open'", (fund["id"],))["o"]


def holdings(conn: Connection, fund: dict, now: datetime) -> dict:
    """What a fund holds at today's prices: cash, shares and bonds, and what it owes on its loan."""
    w = objectives.wealth(conn, fund["account_id"], now)
    debt = owed(conn, fund)
    return {"cash": w["cash"], "shares": w["shares"], "bonds": w["bonds"], "lines": w["lines"], "bond_lines": w["bond_lines"],
            "owed": debt, "total": w["total"] - debt}


def worth(conn: Connection, fund: dict, now: datetime) -> int:
    return holdings(conn, fund, now)["total"]


def unit_price(fund: dict, total: int, *, side: str | None = None) -> int:
    """What one unit is worth, in millionths of a kobo. Coming in pays a little above, going out gets a little below."""
    if fund["units"] <= 0 or total <= 0:
        mid = FIRST_PRICE
    else:
        mid = max(total * UNIT // fund["units"], 1)
    if side == "in":
        return -(-mid * (BPS + data.INVEST_FUND_SWING_BPS) // BPS)
    if side == "out":
        return mid * (BPS - data.INVEST_FUND_SWING_BPS) // BPS
    return mid


def value_of(units: int, price: int) -> int:
    return units * price // UNIT


# ---------------------------------------------------------------------------
# The computer-run funds, made when the world first meets funds
# ---------------------------------------------------------------------------

def setup(conn: Connection, now: datetime) -> None:
    dealing_account(conn)
    if _one(conn, "SELECT 1 AS x FROM investment_funds WHERE computer LIMIT 1"):
        return
    state = careers.world_now(conn, now)
    public = ledger.account_id(conn, HOUSEHOLDS)
    for name, strategy, fee, seed in data.COMPUTER_FUNDS:
        account = ledger.create_account(conn, kind="fund", name=name)
        fund = _one(conn, "INSERT INTO investment_funds (name, name_key, account_id, computer, strategy, fee_bps, high_water, least_in,"
                          " launched_at, launched_period, words) VALUES (%s, %s, %s, true, %s, %s, %s, %s, %s, %s, %s) RETURNING *",
                    (name, name_key(name), account, strategy, fee, FIRST_PRICE, naira(10_000), now, state["period"],
                     ("Run by Broad Street Asset Management, the computer's own fund house. It holds the market's largest names"
                      " in proportion to their size.")))
        paid = ledger.pay_up_to(conn, payer=public, receiver=account, wanted=naira(seed), kind="fund_units_bought",
                                memo=f"{name}: the households' first money", period=state["period"])
        _issue(conn, fund, public, paid * UNIT // FIRST_PRICE, now)
        _computer_rebalance(conn, _fund(conn, fund["id"]), now)


# ---------------------------------------------------------------------------
# Launching a fund
# ---------------------------------------------------------------------------

def _manager_ok(conn: Connection, player_id) -> None:
    mine = careers.career(conn, player_id, "asset_manager")
    build = _one(conn, "SELECT build FROM players WHERE id = %s", (player_id,))["build"]
    if build != "asset_manager" or mine is None or mine["level"] < data.INVEST_FUND_LEVEL:
        raise FundError(f"Only an Asset Manager of Level {data.INVEST_FUND_LEVEL} or above may launch a fund.")
    if _one(conn, "SELECT 1 AS x FROM legal_records WHERE player_id = %s", (player_id,)):
        raise FundError("Somebody with wrongdoing proved on their record cannot be trusted with other people's money.")


def launch(conn: Connection, player_id, *, name: str, strategy: str, fee_bps: int, perf_fee_bps: int, least_in: int, seed: int,
           now: datetime, words: str = "") -> dict:
    """Launch a fund. One open fund per manager at a time. The registration fee goes to the prize pool; the manager's own
    money (the seed) buys the first units at ₦1."""
    with conn.transaction():
        state = _state(conn, now)
        conn.execute("SELECT 1 FROM players WHERE id = %s FOR UPDATE", (player_id,))
        _manager_ok(conn, player_id)
        if _one(conn, "SELECT 1 AS x FROM investment_funds WHERE manager_id = %s AND status IN ('open', 'closing')", (player_id,)):
            raise FundError("You already run a fund. A manager runs one fund at a time.")
        if strategy not in STRATEGIES:
            raise FundError("Choose one of the strategies.")
        for value, most, what in ((fee_bps, data.INVEST_FUND_FEE_MOST_BPS, "The yearly fee"),
                                  (perf_fee_bps, data.INVEST_FUND_PERF_FEE_MOST_BPS, "The performance fee")):
            if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= most:
                raise FundError(f"{what} is from 0% to {most / 100:g}%.")
        low, high = (naira(x) for x in data.INVEST_FUND_LEAST_IN_LIMITS_NAIRA)
        if not isinstance(least_in, int) or not low <= least_in <= high:
            raise FundError(f"The least an investor may put in is from {_money(low)} to {_money(high)}.")
        if not isinstance(seed, int) or seed < naira(data.INVEST_FUND_SEED_NAIRA):
            raise FundError(f"A manager puts in at least {_money(naira(data.INVEST_FUND_SEED_NAIRA))} of their own money.")
        name = " ".join((name or "").split())
        if not 3 <= len(name) <= 60 or not name[0].isalpha() or not all((ch.isascii() and ch.isalnum()) or ch in " &'-." for ch in name):
            raise FundError("A fund's name is 3 to 60 letters, numbers and spaces.")
        key = name_key(name)
        taken = [name_key(r["name"]) for r in _rows(conn, "SELECT name FROM companies UNION ALL SELECT name FROM empires"
                                                         " UNION ALL SELECT name FROM investment_funds")]
        if key in taken or any(word in key for word in ("centralbank", "federalgovernment", "treasury", "broadstreet", "regulator")):
            raise FundError("That name is taken, or is too close to an institution's.")
        me = ledger.player_account_id(conn, player_id)
        fee = naira(data.INVEST_FUND_REGISTRATION_NAIRA)
        if ledger.balance(conn, me) < fee + seed:
            raise FundError(f"Launching costs {_money(fee)} to register, and your own money of {_money(seed)}: {_money(fee + seed)} in all.")
        account = ledger.create_account(conn, kind="fund", name=name)
        ledger.transfer(conn, payer=me, receiver=ledger.account_id(conn, ledger.PRIZE_POOL), amount=fee, kind="fund_registration",
                        memo=f"{name}: registration of an investment fund", period=state["period"])
        fund = _one(conn, "INSERT INTO investment_funds (name, name_key, account_id, founder_id, manager_id, strategy, fee_bps, perf_fee_bps,"
                          " high_water, least_in, launched_at, launched_period, words) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
                          " RETURNING *", (name, key, account, player_id, player_id, strategy, fee_bps, perf_fee_bps, FIRST_PRICE, least_in, now,
                                           state["period"], " ".join((words or "").split())[:400]))
        ledger.transfer(conn, payer=me, receiver=account, amount=seed, kind="fund_seed", memo=f"{name}: the manager's own money",
                        period=state["period"])
        _issue(conn, fund, me, seed * UNIT // FIRST_PRICE, now)
        careers._event(conn, player_id, "asset_manager", "fund_opened", f"Launched the fund {name}.", now)
        _alert(conn, fund, "launched", f"New fund: {name}", f"{STRATEGIES[strategy]}. Fee {fee_bps / 100:.2f}% a year"
               + (f", and {perf_fee_bps / 100:g}% of gains above its best" if perf_fee_bps else "") + ".", now, everyone=False)
        _news(conn, "fund_launched", fund, now, {"fund": name, "strategy": STRATEGIES[strategy].lower(), "manager": _manager_name(conn, fund)})
        return _fund(conn, fund["id"])


def _issue(conn: Connection, fund: dict, account, units: int, now: datetime) -> None:
    if units <= 0:
        return
    conn.execute("UPDATE investment_funds SET units = units + %s WHERE id = %s", (units, fund["id"]))
    conn.execute("INSERT INTO fund_units (fund_id, account_id, units, since) VALUES (%s, %s, %s, %s)"
                 " ON CONFLICT (fund_id, account_id) DO UPDATE SET units = fund_units.units + EXCLUDED.units", (fund["id"], account, units, now))


def _cancel_units(conn: Connection, fund: dict, account, units: int) -> None:
    conn.execute("UPDATE investment_funds SET units = units - %s WHERE id = %s", (units, fund["id"]))
    conn.execute("UPDATE fund_units SET units = units - %s, leaving = greatest(leaving - %s, 0) WHERE fund_id = %s AND account_id = %s",
                 (units, units, fund["id"], account))


def _manager_name(conn: Connection, fund: dict) -> str:
    if fund["computer"]:
        return "Broad Street Asset Management"
    if fund["manager_id"] is None:
        return "the regulator"
    return _one(conn, "SELECT display_name FROM players WHERE id = %s", (fund["manager_id"],))["display_name"]


# ---------------------------------------------------------------------------
# Investors: money in and money out, at the next closing bell
# ---------------------------------------------------------------------------

def _who(conn: Connection, player_id, for_empire: bool, state: dict, amount: int = 0) -> tuple:
    """The account that invests: the player's own, or their empire's (only its head, within what they may sign for)."""
    if not for_empire:
        return ledger.player_account_id(conn, player_id), "you"
    seat = empires.seat_of(conn, player_id)
    if seat is None or seat["empire_status"] != "active" or seat["empire_kind"] == "pension":
        raise FundError("You are not in an empire.")
    if seat["head_player_id"] != player_id:
        raise FundError("Only the head moves the empire's money into a fund.")
    if amount:
        limit = empires.signing_limit(conn, seat)
        used = _one(conn, "SELECT coalesce(sum(amount), 0)::bigint AS t FROM fund_orders WHERE account_id = %s AND side = 'in'"
                          " AND status <> 'cancelled' AND placed_at >= %s", (seat["account_id"], _quarter_start(conn, state)))["t"]
        if used + amount > limit:
            raise FundError(f"That is more of the empire's money than you may sign for this quarter: {_money(limit)}, of which"
                            f" {_money(used)} is used.")
    return seat["account_id"], "the empire"


def _quarter_start(conn: Connection, state: dict) -> datetime:
    world = _one(conn, "SELECT world_start, weeks_ahead FROM world_state")
    start = clock.effective_start(world["world_start"], world["weeks_ahead"])
    return start + timedelta(days=clock.REAL_DAYS_PER_QUARTER) * (state["period"] - 1)


def invest(conn: Connection, player_id, fund_id: int, amount: int, now: datetime, *, for_empire: bool = False) -> dict:
    """Put money into a fund. The money is held at once; units are bought at the next closing bell's price."""
    with conn.transaction():
        state = _state(conn, now)
        fund = _fund(conn, fund_id, lock=True)
        if fund["status"] != "open" or fund["regulator_run"]:
            raise FundError("That fund is not taking new money.")
        if not isinstance(amount, int) or isinstance(amount, bool) or amount <= 0:
            raise FundError("Put in an amount above nothing.")
        account, whose = _who(conn, player_id, for_empire, state, amount)
        if amount < fund["least_in"] and not _one(conn, "SELECT 1 AS x FROM fund_units WHERE fund_id = %s AND account_id = %s AND units > 0",
                                                  (fund_id, account)):
            raise FundError(f"The least this fund takes from a new investor is {_money(fund['least_in'])}.")
        if _one(conn, "SELECT 1 AS x FROM fund_merges WHERE from_fund = %s AND status = 'agreed'", (fund_id,)):
            raise FundError("That fund is about to merge into another and takes no new money.")
        if _one(conn, "SELECT kind FROM ledger_accounts WHERE id = %s", (account,))["kind"] == "fund":
            raise FundError("A fund cannot invest in another fund.")
        try:
            ledger.transfer(conn, payer=account, receiver=dealing_account(conn), amount=amount, kind="fund_order_hold",
                            memo=f"{fund['name']}: money held until the next closing bell", period=state["period"])
        except ledger.InsufficientFunds:
            raise FundError(f"{'You do' if whose == 'you' else 'The empire does'} not have that much cash.") from None
        order = _one(conn, "INSERT INTO fund_orders (fund_id, account_id, player_id, side, amount, placed_at) VALUES (%s, %s, %s, 'in', %s, %s)"
                           " RETURNING *", (fund_id, account, player_id, amount, now))
        return order


def leave(conn: Connection, player_id, fund_id: int, units: int | None, now: datetime, *, for_empire: bool = False) -> dict:
    """Ask for money back: some units, or all (units None). Paid at the next closing bell's price, as the fund has cash."""
    with conn.transaction():
        state = _state(conn, now)
        fund = _fund(conn, fund_id, lock=True)
        if fund["status"] in ("closed", "merged"):
            raise FundError("That fund has closed.")
        account, _ = _who(conn, player_id, for_empire, state)
        held = _one(conn, "SELECT * FROM fund_units WHERE fund_id = %s AND account_id = %s FOR UPDATE", (fund_id, account))
        free = (held["units"] - held["leaving"]) if held else 0
        units = free if units is None else units
        if not isinstance(units, int) or isinstance(units, bool) or units <= 0 or units > free:
            raise FundError(f"You can ask back at most the units you hold and have not already asked back: {free:,}.")
        if fund["manager_id"] == player_id and not for_empire:
            keep = min(_manager_seed_units(conn, fund), fund["units"] * data.INVEST_FUND_MANAGER_KEEPS_BPS // BPS)
            if held["units"] - held["leaving"] - units < keep:
                raise FundError(f"While you run the fund you keep at least {keep:,} units: 1% of the fund, or all you put in.")
        conn.execute("UPDATE fund_units SET leaving = leaving + %s WHERE fund_id = %s AND account_id = %s", (units, fund_id, account))
        return _one(conn, "INSERT INTO fund_orders (fund_id, account_id, player_id, side, units, placed_at) VALUES (%s, %s, %s, 'out', %s, %s)"
                          " RETURNING *", (fund_id, account, player_id, units, now))


def _manager_seed_units(conn: Connection, fund: dict) -> int:
    row = _one(conn, "SELECT coalesce(sum(e.amount), 0)::bigint AS seed FROM ledger_entries e JOIN ledger_transactions t ON t.id = e.transaction_id"
                     " WHERE e.account_id = %s AND t.kind = 'fund_seed'", (fund["account_id"],))
    return row["seed"] * UNIT // FIRST_PRICE


def cancel(conn: Connection, player_id, order_id: int, now: datetime) -> None:
    """Take back an order the bell has not dealt yet."""
    with conn.transaction():
        _state(conn, now)
        order = _one(conn, "SELECT o.* FROM fund_orders o WHERE o.id = %s AND o.player_id = %s FOR UPDATE", (order_id, player_id))
        if order is None or order["status"] != "waiting":
            raise FundError("There is no waiting order of yours with that number.")
        if order["side"] == "out" and order["units_done"]:
            raise FundError("Part of it has been paid already: the rest stays asked for.")
        placed = clock.to_lagos(order["placed_at"])
        due = order_cutoff(placed.date())
        if placed >= due:
            due += timedelta(days=1)
        if now >= due:
            raise FundError("The market has closed and this order is dealt at tonight's bell: it can no longer be taken back.")
        _undo(conn, order, "Taken back.")


def _undo(conn: Connection, order: dict, words: str) -> None:
    fund = _fund(conn, order["fund_id"])
    if order["side"] == "in":
        ledger.transfer(conn, payer=dealing_account(conn), receiver=order["account_id"], amount=order["amount"], kind="fund_order_release",
                        memo=f"{fund['name']}: money not used, handed back")
    else:
        conn.execute("UPDATE fund_units SET leaving = greatest(leaving - %s, 0) WHERE fund_id = %s AND account_id = %s",
                     (order["units"], order["fund_id"], order["account_id"]))
    conn.execute("UPDATE fund_orders SET status = %s, words = %s WHERE id = %s",
                 ("cancelled" if words == "Taken back." else "refused", words, order["id"]))


def follow(conn: Connection, player_id, fund_id: int, on: bool, now: datetime) -> None:
    _fund(conn, fund_id)
    if on:
        conn.execute("INSERT INTO fund_follows (player_id, fund_id, at) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING", (player_id, fund_id, now))
    else:
        conn.execute("DELETE FROM fund_follows WHERE player_id = %s AND fund_id = %s", (player_id, fund_id))


# ---------------------------------------------------------------------------
# The manager: dealing, under the rules
# ---------------------------------------------------------------------------

def _managed(conn: Connection, manager_id, *, lock: bool = True) -> dict:
    fund = _one(conn, "SELECT * FROM investment_funds WHERE manager_id = %s AND status IN ('open', 'closing')"
                      + (" FOR UPDATE" if lock else ""), (manager_id,))
    if fund is None:
        raise FundError("You run no fund.")
    return fund


def _insiders(conn: Connection, fund: dict) -> list:
    """The manager's own account and their empire's: a fund never deals with them."""
    out = []
    if fund["manager_id"]:
        out.append(ledger.player_account_id(conn, fund["manager_id"]))
        seat = empires.seat_of(conn, fund["manager_id"])
        if seat and seat["empire_kind"] != "pension":
            out.append(seat["account_id"])
    return out


def leavers_waiting(conn: Connection, fund: dict) -> bool:
    return bool(_one(conn, "SELECT 1 AS x FROM fund_orders WHERE fund_id = %s AND side = 'out' AND status = 'waiting' LIMIT 1", (fund["id"],)))


def check_buy(conn: Connection, fund: dict, now: datetime, *, value: int, company: dict | None = None, bond: dict | None = None) -> None:
    """Would this purchase break the fund's rules? Raises FundError with the reason."""
    if leavers_waiting(conn, fund):
        raise FundError("Investors are waiting to be paid. The fund can sell, and can buy nothing until they are.")
    if fund["status"] != "open":
        raise FundError("A fund that is closing buys nothing.")
    h = holdings(conn, fund, now)
    total = h["total"]
    if total <= 0:
        raise FundError("The fund has nothing to invest.")
    cash_now = ledger.balance(conn, fund["account_id"])
    if cash_now - value < apply_bps(total, data.INVEST_FUND_LEAST_CASH_BPS):
        raise FundError(f"A fund keeps at least {data.INVEST_FUND_LEAST_CASH_BPS / 100:g}% of itself in cash: that would leave "
                        f"{_money(max(cash_now - value, 0))} of {_money(total)}.")
    strategy = fund["strategy"]
    # Money already waiting in buy orders counts as if bought: several orders cannot add up past a limit.
    pending = {r["ticker"]: r["reserved"] for r in _rows(conn, "SELECT c.ticker, sum(o.reserved)::bigint AS reserved FROM market_orders o"
                                                               " JOIN companies c ON c.id = o.company_id WHERE o.account_id = %s"
                                                               " AND o.status = 'open' AND o.side = 'buy' GROUP BY c.ticker", (fund["account_id"],))}
    if company is not None:
        if strategy == "bonds":
            raise FundError("A bond fund holds bonds and bills, not shares.")
        held = next((line["value"] for line in h["lines"] if line["ticker"] == company["ticker"]), 0) + pending.get(company["ticker"], 0)
        if held + value > apply_bps(total, data.INVEST_FUND_ONE_HOLDING_BPS):
            raise FundError(f"No holding may be more than {data.INVEST_FUND_ONE_HOLDING_BPS / 100:g}% of the fund: {company['ticker']}"
                            f" would be {_money(held + value)} of {_money(total)}.")
        banks = _bank_tickers(conn)
        if strategy == "banks" and company["ticker"] not in banks:
            not_banks = (sum(line["value"] for line in h["lines"] if line["ticker"] not in banks)
                         + sum(v for t, v in pending.items() if t not in banks) + value)
            invested = h["shares"] + h["bonds"] + sum(pending.values()) + value
            if not_banks * BPS > invested * (BPS - data.INVEST_FUND_STRATEGY_LEAST_BPS):
                raise FundError("A banks fund keeps at least 80% of what it holds in banks.")
        if strategy == "balanced" and h["shares"] + sum(pending.values()) + value > apply_bps(total, data.INVEST_FUND_BALANCED_MOST_BPS):
            raise FundError("A balanced fund holds at most 70% of itself in shares.")
    if bond is not None:
        if strategy in ("shares", "banks"):
            raise FundError(f"A {STRATEGIES[strategy].lower()} fund holds shares, not bonds.")
        held = next((b["value"] for b in h["bond_lines"] if b["code"] == bond["code"]), 0)
        if bond.get("issuer") == "company" and held + value > apply_bps(total, data.INVEST_FUND_ONE_HOLDING_BPS):
            raise FundError(f"No company's bond may be more than {data.INVEST_FUND_ONE_HOLDING_BPS / 100:g}% of the fund.")
        if strategy == "balanced" and h["bonds"] + value > apply_bps(total, data.INVEST_FUND_BALANCED_MOST_BPS):
            raise FundError("A balanced fund holds at most 70% of itself in bonds.")


def _front_running(conn: Connection, fund: dict, company_id, side: str, now: datetime) -> None:
    """The Money Watch notes (never shown) a manager who dealt in a share for themselves, the same way, just before the fund."""
    if not fund["manager_id"]:
        return
    me = ledger.player_account_id(conn, fund["manager_id"])
    day, _ = exchange.session_of(now)
    column = "buyer_account_id" if side == "buy" else "seller_account_id"
    if _one(conn, f"SELECT 1 AS x FROM market_trades WHERE company_id = %s AND {column} = %s AND session_date >= %s LIMIT 1",
            (company_id, me, day - timedelta(days=2))):
        period = careers.world_now(conn, now)["period"]
        conn.execute("INSERT INTO money_watch_flags (period, account_id, reason) VALUES (%s, %s, %s)",
                     (period, me, f"Fund manager dealt in a share for themselves just before their fund ({fund['name']}) did"))


def trade_shares(conn: Connection, manager_id, *, ticker: str, side: str, quantity: int, limit_price: int, now: datetime) -> dict:
    with conn.transaction():
        _state(conn, now)
        fund = _managed(conn, manager_id)
        share = next((s for s in marketview._shares(conn, exchange.session_of(now)[0]) if s["ticker"] == (ticker or "").upper()), None)
        if share is None:
            raise FundError("There is no share with that code.")
        if side not in ("buy", "sell") or not isinstance(quantity, int) or isinstance(quantity, bool) or quantity <= 0:
            raise FundError("Buy or sell a whole number of shares above nothing.")
        if not isinstance(limit_price, int) or isinstance(limit_price, bool) or limit_price <= 0:
            raise FundError("A fund deals only at a price you name.")
        if side == "buy":
            check_buy(conn, fund, now, value=limit_price * quantity, company=share)
        try:
            empires.fair_dealing(share, side, "limit", limit_price, "A fund")
            empires.no_dealing_with_yourself(conn, fund["account_id"], share["id"], side, _insiders(conn, fund), "the fund")
        except empires.EmpireError as refused:
            raise FundError(str(refused)) from None
        _front_running(conn, fund, share["id"], side, now)
        try:
            return exchange.place_order(conn, account=fund["account_id"], ticker=share["ticker"], side=side, kind="limit", quantity=quantity,
                                        limit_price=limit_price, now=now)
        except exchange.ExchangeError as refused:
            raise FundError(str(refused)) from None


def cancel_trade(conn: Connection, manager_id, order_id: int, now: datetime) -> dict:
    with conn.transaction():
        fund = _managed(conn, manager_id)
        try:
            return exchange.cancel_order(conn, account=fund["account_id"], order_id=order_id, now=now)
        except exchange.ExchangeError as refused:
            raise FundError(str(refused)) from None


def trade_bonds(conn: Connection, manager_id, *, code: str, side: str, units: int, now: datetime) -> dict:
    with conn.transaction():
        _state(conn, now)
        fund = _managed(conn, manager_id)
        bond = bonds.find(conn, code)
        if bond is None:
            raise FundError("There is no bond with that code.")
        if side == "buy":
            state = bonds.market(conn, now)
            price = bonds.prices(conn, bond, state, exchange.session_of(now)[0], buying=units, selling=units)["ask"]
            check_buy(conn, fund, now, value=price * (units if isinstance(units, int) else 0), bond={**bond, "code": code})
        try:
            return bonds.trade(conn, account=fund["account_id"], code=code, side=side, units=units, now=now)
        except bonds.BondError as refused:
            raise FundError(str(refused)) from None


def set_gate(conn: Connection, manager_id, on: bool, now: datetime) -> dict:
    """Put up a gate (leavers are paid at most a tenth of the fund at a bell, for at most a game quarter), or take it down.
    Either is announced to every holder and to the market."""
    with conn.transaction():
        _state(conn, now)
        fund = _managed(conn, manager_id)
        if on and fund["gated_at"] is None:
            if fund["gate_lifted_at"] is not None:
                since = _one(conn, "SELECT count(*) AS n FROM closing_bells WHERE rung_at > %s AND rung_at <= %s", (fund["gate_lifted_at"], now))["n"]
                if since < data.INVEST_FUND_GATE_LONGEST_BELLS:
                    raise FundError(f"A gate can go up again only {data.INVEST_FUND_GATE_LONGEST_BELLS} closing bells after the last one came"
                                    f" down ({since} so far): leavers cannot be kept waiting for ever.")
            conn.execute("UPDATE investment_funds SET gated_at = %s WHERE id = %s", (now, fund["id"]))
            _alert(conn, fund, "gated", f"{fund['name']} limits withdrawals",
                   f"Investors leaving are paid at most {data.INVEST_FUND_GATE_BPS / 100:g}% of the fund at each closing bell, for up to"
                   f" {data.INVEST_FUND_GATE_LONGEST_BELLS} bells. The rest wait their turn.", now, everyone=True)
            _news(conn, "fund_gated", fund, now, {"fund": fund["name"], "manager": _manager_name(conn, fund),
                                                  "limit": f"{data.INVEST_FUND_GATE_BPS / 100:g}%"})
        elif not on and fund["gated_at"] is not None:
            _lift_gate(conn, fund, now)
        return _fund(conn, fund["id"])


def _lift_gate(conn: Connection, fund: dict, now: datetime) -> None:
    conn.execute("UPDATE investment_funds SET gated_at = NULL, gate_lifted_at = %s WHERE id = %s", (now, fund["id"]))
    _alert(conn, fund, "gate_lifted", f"{fund['name']} pays leavers in full again", "The limit on withdrawals has been lifted.", now)


def lower_fees(conn: Connection, manager_id, fee_bps: int, perf_fee_bps: int, now: datetime) -> dict:
    """Fees can be lowered at any time, never raised: investors came in at the fees they saw."""
    with conn.transaction():
        _state(conn, now)
        fund = _managed(conn, manager_id)
        for value, current in ((fee_bps, fund["fee_bps"]), (perf_fee_bps, fund["perf_fee_bps"])):
            if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= current:
                raise FundError("Fees can be lowered, never raised.")
        conn.execute("UPDATE investment_funds SET fee_bps = %s, perf_fee_bps = %s WHERE id = %s", (fee_bps, perf_fee_bps, fund["id"]))
        return _fund(conn, fund["id"])


def close(conn: Connection, manager_id, now: datetime) -> dict:
    """Close the fund: at the next bell everything is sold to the market's dealers and the money paid out to every holder."""
    with conn.transaction():
        _state(conn, now)
        fund = _managed(conn, manager_id)
        if fund["status"] != "open":
            raise FundError("The fund is already closing.")
        _start_closing(conn, fund, "The manager is closing the fund.", now)
        return _fund(conn, fund["id"])


def _start_closing(conn: Connection, fund: dict, why: str, now: datetime) -> None:
    conn.execute("UPDATE investment_funds SET status = 'closing', closing_since = %s WHERE id = %s", (now, fund["id"]))
    for order in _rows(conn, "SELECT * FROM fund_orders WHERE fund_id = %s AND side = 'in' AND status = 'waiting' FOR UPDATE", (fund["id"],)):
        _undo(conn, order, "The fund is closing: the money was handed back.")
    for m in _rows(conn, "SELECT * FROM fund_merges WHERE (from_fund = %s OR into_fund = %s) AND status IN ('proposed', 'agreed')",
                   (fund["id"], fund["id"])):
        conn.execute("UPDATE fund_merges SET status = 'withdrawn' WHERE id = %s", (m["id"],))
    _alert(conn, fund, "closing", f"{fund['name']} is closing", f"{why} Everything it holds is sold at the next closing bell and the money"
           " paid out to every holder.", now)


def propose_merge(conn: Connection, manager_id, into_fund_id: int, now: datetime) -> dict:
    with conn.transaction():
        _state(conn, now)
        fund = _managed(conn, manager_id)
        into = _fund(conn, into_fund_id, lock=True)
        if into["id"] == fund["id"] or into["status"] != "open" or into["computer"] or into["regulator_run"] or into["manager_id"] is None:
            raise FundError("A fund can be merged only into another open fund run by a player.")
        if fund["status"] != "open":
            raise FundError("The fund is closing.")
        if owed(conn, fund):
            raise FundError("Repay the fund's loan before merging it.")
        if into["strategy"] not in (fund["strategy"], "anything"):
            raise FundError(f"A {STRATEGIES[fund['strategy']].lower()} fund can merge only into a fund with the same strategy, or one that"
                            " may hold anything: its investors chose what it holds.")
        try:
            return _one(conn, "INSERT INTO fund_merges (from_fund, into_fund, proposed_at) VALUES (%s, %s, %s) RETURNING *",
                        (fund["id"], into["id"], now))
        except Exception as already:
            if "fund_merges_one" in str(already):
                raise FundError("A merger of this fund is already proposed.") from None
            raise


def answer_merge(conn: Connection, manager_id, merge_id: int, accept: bool, now: datetime) -> dict:
    """The receiving fund's manager agrees or refuses. Agreed, it takes effect at the first bell three days later; the
    merging fund's investors are told at once, and may leave before then."""
    with conn.transaction():
        _state(conn, now)
        into = _managed(conn, manager_id)
        merge = _one(conn, "SELECT * FROM fund_merges WHERE id = %s AND into_fund = %s AND status = 'proposed' FOR UPDATE", (merge_id, into["id"]))
        if merge is None:
            raise FundError("There is no merger waiting for your answer.")
        if not accept:
            conn.execute("UPDATE fund_merges SET status = 'refused' WHERE id = %s", (merge_id,))
            return _one(conn, "SELECT * FROM fund_merges WHERE id = %s", (merge_id,))
        conn.execute("UPDATE fund_merges SET status = 'agreed', accepted_at = %s, takes_effect = %s WHERE id = %s", (now, now + MERGE_NOTICE, merge_id))
        source = _fund(conn, merge["from_fund"])
        _alert(conn, source, "merged", f"{source['name']} will merge into {into['name']}",
               f"In three days every unit becomes units of {into['name']} of the same value. Anybody who would rather leave can ask for"
               " their money back before then.", now)
        return _one(conn, "SELECT * FROM fund_merges WHERE id = %s", (merge_id,))


def take_costs(conn: Connection, manager_id, amount: int, now: datetime) -> dict:
    """The shadow side of running other people's money: a cost written into the fund's books that is not real, and the money
    taken. It leaves a trail; the regulator's audit may find it."""
    with conn.transaction():
        state = _state(conn, now)
        fund = _managed(conn, manager_id)
        if not isinstance(amount, int) or isinstance(amount, bool) or amount <= 0:
            raise FundError("An amount above nothing.")
        limit = apply_bps(worth(conn, fund, now), data.INVEST_FUND_COSTS_BPS)
        used = _one(conn, "SELECT coalesce(sum(amount), 0)::bigint AS t FROM fund_books WHERE fund_id = %s AND period = %s",
                    (fund["id"], state["period"]))["t"]
        if used + amount > limit:
            raise FundError(f"A manager can sign for costs of {_money(limit)} in a quarter, of which {_money(used)} is used.")
        try:
            ledger.transfer(conn, payer=fund["account_id"], receiver=ledger.player_account_id(conn, manager_id), amount=amount,
                            kind="fund_costs", memo=f"{fund['name']}: custody and dealing costs", period=state["period"])
        except ledger.InsufficientFunds:
            raise FundError("The fund does not have that much cash.") from None
        conn.execute("INSERT INTO fund_books (fund_id, period, words, amount, genuine, entered_by, at) VALUES (%s, %s, %s, %s, false, %s, %s)",
                     (fund["id"], state["period"], "Custody and dealing costs", amount, manager_id, now))
        return {"amount": amount, "limit": limit, "used": used + amount}


# ---------------------------------------------------------------------------
# The closing bell: fees, money in and out, runs, the computer funds
# ---------------------------------------------------------------------------

def tick(conn: Connection, now: datetime) -> int:
    """After each closing bell: every fund deals the orders placed before it. Returns the bells dealt."""
    if not ready(conn) or not _one(conn, "SELECT 1 AS x FROM world_state"):
        return 0
    with conn.transaction():
        setup(conn, now)
    progress = _one(conn, "SELECT dealt_through FROM fund_progress")["dealt_through"]
    bells = _rows(conn, "SELECT session_date, rung_at FROM closing_bells WHERE (%s::date IS NULL OR session_date > %s) AND rung_at <= %s"
                        " ORDER BY session_date", (progress, progress, now))
    for bell in bells:
        for f in _rows(conn, "SELECT id FROM investment_funds WHERE status IN ('open', 'closing') ORDER BY id"):
            try:
                with conn.transaction():
                    deal(conn, _fund(conn, f["id"], lock=True), bell["session_date"], bell["rung_at"])
            except Exception:
                log.exception("A fund could not deal at the bell")
        with conn.transaction():
            conn.execute("UPDATE fund_progress SET dealt_through = %s", (bell["session_date"],))
    return len(bells)


def _benchmark(conn: Connection, fund: dict, day: date) -> int | None:
    """The fund's benchmark level that day, chained from day to day (in hundred-thousandths)."""
    before = _one(conn, "SELECT session_date, benchmark FROM fund_days WHERE fund_id = %s AND session_date < %s ORDER BY session_date DESC LIMIT 1",
                  (fund["id"], day))
    if before is None or before["benchmark"] is None:
        return 100_000
    level = {r["session_date"]: r["level"] for r in _rows(conn, "SELECT session_date, level FROM index_days WHERE session_date IN (%s, %s)",
                                                         (before["session_date"], day))}
    shares_ret = (level[day] / level[before["session_date"]] - 1) if day in level and before["session_date"] in level else 0.0
    rate_ret = _policy_rate(conn) / BPS / data.INVEST_FUND_SESSIONS_PER_YEAR
    ret = {"bonds": rate_ret, "balanced": 0.6 * shares_ret + 0.4 * rate_ret}.get(fund["strategy"], shares_ret)
    return round(before["benchmark"] * (1 + ret))


def deal(conn: Connection, fund: dict, day: date, rung_at: datetime) -> None:
    now = rung_at
    period = careers.world_now(conn, now)["period"]
    # 1. The day's fee, to the manager (the computer's fund house for its own funds; nothing while the regulator runs it).
    total = worth(conn, fund, now)
    fee = 0
    if fund["fee_bps"] and total > 0 and not fund["regulator_run"]:
        payee = ledger.player_account_id(conn, fund["manager_id"]) if fund["manager_id"] else ledger.account_id(conn, ledger.INVESTORS_INSTITUTIONS)
        fee = ledger.pay_up_to(conn, payer=fund["account_id"], receiver=payee, wanted=total * fund["fee_bps"] // BPS // data.INVEST_FUND_SESSIONS_PER_YEAR,
                               kind="fund_fee", memo=f"{fund['name']}: the day's fee", period=period)
    # 2. Closing: sell everything to the market's dealers and pay everybody.
    if fund["status"] == "closing":
        _wind_up(conn, fund, day, now, period)
        return
    # 3. A merger agreed three days ago takes effect.
    merge = _one(conn, "SELECT * FROM fund_merges WHERE from_fund = %s AND status = 'agreed' AND takes_effect <= %s", (fund["id"], now))
    if merge:
        _merge(conn, fund, merge, day, now, period)
        return
    # 4. The gate lasts at most a quarter's bells.
    if fund["gated_at"] is not None:
        bells = _one(conn, "SELECT count(*) AS n FROM closing_bells WHERE rung_at > %s AND rung_at <= %s", (fund["gated_at"], now))["n"]
        if bells > data.INVEST_FUND_GATE_LONGEST_BELLS:
            _lift_gate(conn, fund, now)
            fund = _fund(conn, fund["id"])
    # 5. Money out, then money in. Only orders placed before the market closed (22:00) are dealt at this bell: an order placed
    # once the closing prices are known waits for the next one. Leavers are paid at the price before any money moves; those
    # coming in buy at the price after the leavers are paid (each side pays its own swing, which stays in the fund).
    cutoff = order_cutoff(day)
    fund = _fund(conn, fund["id"])
    total = worth(conn, fund, now)
    price = unit_price(fund, total)
    money_out = _pay_leavers(conn, fund, total, cutoff, day, period, now)
    fund = _fund(conn, fund["id"])
    money_in = _take_money_in(conn, fund, worth(conn, fund, now), cutoff, day, period, now)
    fund = _fund(conn, fund["id"])
    # 6. The computer funds keep their mix; any fund repays its loan when it can.
    if fund["computer"]:
        _computer_rebalance(conn, fund, now)
    _repay_loan(conn, _fund(conn, fund["id"]), now, period)
    fund = _fund(conn, fund["id"])
    total = worth(conn, fund, now)
    conn.execute("INSERT INTO fund_days (fund_id, session_date, unit_price, worth, units, money_in, money_out, fee, benchmark)"
                 " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
                 (fund["id"], day, unit_price(fund, total) if fund["units"] else price, total, fund["units"], money_in, money_out, fee,
                  _benchmark(conn, fund, day)))
    # 7. Runs: the computer's investors ask for their money back when the fund has fallen far, or the banks panic.
    _run(conn, fund, day, now)


def order_cutoff(day: date) -> datetime:
    """Orders placed before this moment are dealt at that day's closing bell: the market's close, 22:00 Lagos time."""
    return datetime.combine(day, clock.MARKET_CLOSE, tzinfo=clock.LAGOS)


def _pay_leavers(conn: Connection, fund: dict, total: int, cutoff: datetime, day: date, period: int, now: datetime) -> int:
    orders = _rows(conn, "SELECT * FROM fund_orders WHERE fund_id = %s AND side = 'out' AND status = 'waiting' AND placed_at < %s"
                         " ORDER BY placed_at, id FOR UPDATE", (fund["id"], cutoff))
    if not orders:
        return 0
    price = unit_price(fund, total, side="out")
    budget = apply_bps(total, data.INVEST_FUND_GATE_BPS) if fund["gated_at"] is not None else None
    paid_all = 0
    for order in orders:
        left = order["units"] - order["units_done"]
        due = value_of(left, price)
        if budget is not None:
            due_now = min(due, max(budget - paid_all, 0))
        else:
            due_now = due
        cash = max(ledger.balance(conn, fund["account_id"]), 0)
        if cash < due_now:
            cash += _borrow(conn, fund, due_now - cash, total, now, period)
        pay = min(due_now, cash)
        units = left if pay >= due else pay * UNIT // max(price, 1)
        pay = value_of(units, price) if units < left else due
        if units <= 0:
            continue
        ledger.transfer(conn, payer=fund["account_id"], receiver=order["account_id"], amount=pay, kind="fund_units_sold",
                        memo=f"{fund['name']}: {units:,} units sold back at the bell", period=period)
        _cancel_units(conn, fund, order["account_id"], units)
        paid_all += pay
        done = order["units_done"] + units
        conn.execute("UPDATE fund_orders SET units_done = %s, paid = paid + %s, price = %s, session_date = %s, status = %s, dealt_at = %s"
                     " WHERE id = %s", (done, pay, price, day, "dealt" if done >= order["units"] else "waiting", now, order["id"]))
        fund = _fund(conn, fund["id"])
    if leavers_waiting(conn, fund) and fund["gated_at"] is None and not fund["computer"]:
        _raise_cash(conn, fund, now)
    return paid_all


def _borrow(conn: Connection, fund: dict, wanted: int, total: int, now: datetime, period: int) -> int:
    room = apply_bps(total, data.INVEST_FUND_BORROW_MOST_BPS) - owed(conn, fund)
    amount = min(wanted, max(room, 0))
    if amount <= 0:
        return 0
    lender = ledger.account_id(conn, ledger.INVESTORS_INSTITUTIONS)
    got = ledger.pay_up_to(conn, payer=lender, receiver=fund["account_id"], wanted=amount, kind="fund_loan",
                           memo=f"{fund['name']}: a short loan to pay investors who leave", period=period)
    if got:
        conn.execute("INSERT INTO fund_loans (fund_id, owed, rate_bps, taken_at) VALUES (%s, %s, %s, %s)",
                     (fund["id"], got, _policy_rate(conn) + data.INVEST_FUND_LOAN_OVER_POLICY_BPS, now))
    return got


def _repay_loan(conn: Connection, fund: dict, now: datetime, period: int) -> None:
    lender = ledger.account_id(conn, ledger.INVESTORS_INSTITUTIONS)
    for loan in _rows(conn, "SELECT * FROM fund_loans WHERE fund_id = %s AND status = 'open' ORDER BY id FOR UPDATE", (fund["id"],)):
        interest = loan["owed"] * loan["rate_bps"] // BPS // data.INVEST_FUND_SESSIONS_PER_YEAR
        if interest:
            ledger.pay_up_to(conn, payer=fund["account_id"], receiver=lender, wanted=interest, kind="fund_loan_interest",
                             memo=f"{fund['name']}: a day's interest on its loan", period=period)
        total = worth(conn, fund, now)
        spare = ledger.balance(conn, fund["account_id"]) - apply_bps(total, data.INVEST_FUND_LEAST_CASH_BPS)
        if spare <= 0 or leavers_waiting(conn, fund):
            continue
        paid = ledger.pay_up_to(conn, payer=fund["account_id"], receiver=lender, wanted=min(spare, loan["owed"]), kind="fund_loan_repayment",
                                memo=f"{fund['name']}: loan repaid", period=period)
        conn.execute("UPDATE fund_loans SET owed = owed - %s, status = CASE WHEN owed - %s <= 0 THEN 'repaid' ELSE 'open' END WHERE id = %s",
                     (paid, paid, loan["id"]))


def _raise_cash(conn: Connection, fund: dict, now: datetime) -> None:
    """Investors are waiting and the fund is short of cash: it sells bonds to the pension funds (the bond dealers) at once,
    at 1% under their fair value, nearest to being repaid first; then offers its largest share holdings on the exchange (the
    orders wait for the next session's opening auction)."""
    due = sum(value_of(o["units"] - o["units_done"], unit_price(fund, worth(conn, fund, now), side="out"))
              for o in _rows(conn, "SELECT * FROM fund_orders WHERE fund_id = %s AND side = 'out' AND status = 'waiting'", (fund["id"],)))
    need = due - max(ledger.balance(conn, fund["account_id"]), 0)
    if need <= 0:
        return
    institutions = ledger.account_id(conn, ledger.INVESTORS_INSTITUTIONS)
    state = bonds.market(conn, now)
    period = careers.world_now(conn, now)["period"]
    for line in sorted(bonds.holdings_of(conn, fund["account_id"], now), key=lambda x: x["maturity_period"]):
        if need <= 0:
            return
        b = bonds.find(conn, line["code"])
        each = bonds.fair_value(b, state) * 99 // 100
        if each <= 0:
            continue
        n = min(-(-need // each), ledger.balance(conn, fund["account_id"], b["asset"]), max(ledger.balance(conn, institutions), 0) // each)
        if n <= 0:
            continue
        ledger.post(conn, kind="fund_bond_sale", memo=f"{fund['name']}: {n:,} of {b['name']} sold to pay investors", period=period,
                    legs=[ledger.Leg(fund["account_id"], -n, b["asset"]), ledger.Leg(institutions, n, b["asset"]),
                          ledger.Leg(institutions, -n * each), ledger.Leg(fund["account_id"], n * each)])
        need -= n * each
    shares = {s["id"]: s for s in marketview._shares(conn, exchange.session_of(now)[0])}
    for row in _rows(conn, "SELECT company_id, shares FROM share_owners WHERE account_id = %s AND shares > 0 ORDER BY shares DESC", (fund["account_id"],)):
        if need <= 0:
            return
        share = shares.get(row["company_id"])
        if share is None or _one(conn, "SELECT 1 AS x FROM market_orders WHERE account_id = %s AND company_id = %s AND status = 'open'",
                                 (fund["account_id"], row["company_id"])):
            continue
        quantity = min(row["shares"], need // max(share["price"], 1) + 1)
        low, _ = exchange.price_limits(share["reference"])
        try:
            with conn.transaction():
                exchange.place_order(conn, account=fund["account_id"], ticker=share["ticker"], side="sell", kind="limit", quantity=quantity,
                                     limit_price=max(share["reference"] * 98 // 100, low), now=now)
                need -= quantity * share["price"]
        except (exchange.ExchangeError, ledger.LedgerError):
            continue


def _take_money_in(conn: Connection, fund: dict, total: int, cutoff: datetime, day: date, period: int, now: datetime) -> int:
    orders = _rows(conn, "SELECT * FROM fund_orders WHERE fund_id = %s AND side = 'in' AND status = 'waiting' AND placed_at < %s"
                         " ORDER BY placed_at, id FOR UPDATE", (fund["id"], cutoff))
    if not orders:
        return 0
    price = unit_price(fund, total, side="in")
    taken = 0
    for order in orders:
        units = order["amount"] * UNIT // price
        ledger.transfer(conn, payer=dealing_account(conn), receiver=fund["account_id"], amount=order["amount"], kind="fund_units_bought",
                        memo=f"{fund['name']}: money in at the bell", period=period)
        _issue(conn, fund, order["account_id"], units, now)
        fund = _fund(conn, fund["id"])
        conn.execute("UPDATE fund_orders SET status = 'dealt', units_done = %s, price = %s, session_date = %s, dealt_at = %s WHERE id = %s",
                     (units, price, day, now, order["id"]))
        taken += order["amount"]
    return taken


def _run(conn: Connection, fund: dict, day: date, now: datetime) -> None:
    public = ledger.account_id(conn, HOUSEHOLDS)
    held = _one(conn, "SELECT * FROM fund_units WHERE fund_id = %s AND account_id = %s", (fund["id"], public))
    if fund["run_until"] is None or fund["run_until"] < day:
        high = _one(conn, "SELECT max(unit_price) AS h FROM fund_days WHERE fund_id = %s AND session_date > %s", (fund["id"], day - timedelta(days=30)))["h"]
        today = _one(conn, "SELECT unit_price FROM fund_days WHERE fund_id = %s AND session_date = %s", (fund["id"], day))
        panic = False
        from simulation import crisis
        panic = crisis.national(conn) < data.CONFIDENCE_PANIC
        fell = bool(high and today and today["unit_price"] * BPS < high * (BPS - data.INVEST_FUND_RUN_FALL_BPS))
        if (fell or panic) and held and held["units"] > 0:
            conn.execute("UPDATE investment_funds SET run_until = %s WHERE id = %s", (day + timedelta(days=data.INVEST_FUND_RUN_BELLS), fund["id"]))
            why = f"it fell more than {data.INVEST_FUND_RUN_FALL_BPS / 100:g}% from its high" if fell else "the banks are in a panic"
            _alert(conn, fund, "run", f"Investors pull money out of {fund['name']}",
                   f"Its investors are asking for their money back because {why}.", now, everyone=True)
            _news(conn, "fund_run", fund, now, {"fund": fund["name"], "manager": _manager_name(conn, fund), "why": why})
            fund = _fund(conn, fund["id"])
        else:
            return
    if held and held["units"] - held["leaving"] > 0:
        units = (held["units"] - held["leaving"]) * data.INVEST_FUND_RUN_DAILY_BPS // BPS
        if units > 0:
            conn.execute("UPDATE fund_units SET leaving = leaving + %s WHERE fund_id = %s AND account_id = %s", (units, fund["id"], public))
            conn.execute("INSERT INTO fund_orders (fund_id, account_id, side, units, placed_at) VALUES (%s, %s, 'out', %s, %s)",
                         (fund["id"], public, units, now))


# ---------------------------------------------------------------------------
# The computer's own funds: they keep the market's largest names, bought from and sold to the market's dealers
# ---------------------------------------------------------------------------

def _basket(conn: Connection, fund: dict, now: datetime) -> list[dict]:
    day = exchange.session_of(now)[0]
    banks = _bank_tickers(conn)
    shares = [s for s in marketview._shares(conn, day) if s["price"] > 0 and (fund["strategy"] != "banks" or s["ticker"] in banks)]
    halted = {r["company_id"] for r in _rows(conn, "SELECT company_id FROM market_instruments WHERE halted_reason IS NOT NULL")}
    sizes = []
    for s in shares:
        if s["id"] in halted:
            continue
        sizes.append((s, s["price"] * (s["shares"] or 0)))
    sizes.sort(key=lambda x: -x[1])
    top = sizes[:20]
    whole = sum(v for _, v in top) or 1
    weights = [(s, min(v * BPS // whole, data.INVEST_FUND_ONE_HOLDING_BPS - 50)) for s, v in top]
    scale = sum(w for _, w in weights) or 1
    return [{"share": s, "weight": w * BPS // scale} for s, w in weights]


def _computer_rebalance(conn: Connection, fund: dict, now: datetime) -> None:
    """Spare cash buys the basket; too little cash sells some of it. Shares are dealt with the institutions at the last
    price, bonds with the dealers at their fair value: no order touches the exchange."""
    period = careers.world_now(conn, now)["period"]
    institutions = ledger.account_id(conn, ledger.INVESTORS_INSTITUTIONS)
    total = worth(conn, fund, now)
    if total <= 0:
        return
    cash = ledger.balance(conn, fund["account_id"])
    target = apply_bps(total, data.INVEST_FUND_LEAST_CASH_BPS * 2)
    gap = cash - target                                  # >0: buy; <0: sell
    if abs(gap) < apply_bps(total, 100):
        return
    share_part = {"shares": BPS, "banks": BPS, "bonds": 0, "balanced": 6_000}.get(fund["strategy"], BPS)
    if share_part:
        for item in _basket(conn, fund, now):
            s = item["share"]
            value = gap * share_part // BPS * item["weight"] // BPS
            qty = abs(value) // max(s["price"], 1)
            if qty <= 0:
                continue
            asset = f"SHR-{s['ticker']}"
            if value > 0:
                qty = min(qty, ledger.balance(conn, institutions, asset))
                payer_s, receiver_s = institutions, fund["account_id"]
            else:
                qty = min(qty, ledger.balance(conn, fund["account_id"], asset), max(ledger.balance(conn, institutions), 0) // max(s["price"], 1))
                payer_s, receiver_s = fund["account_id"], institutions
            if qty <= 0:
                continue
            amount = qty * s["price"]
            try:
                with conn.transaction():
                    ledger.post(conn, kind="fund_rebalance", memo=f"{fund['name']}: {qty:,} {s['ticker']} at {_money(s['price'])}", period=period,
                                legs=[ledger.Leg(payer_s, -qty, asset), ledger.Leg(receiver_s, qty, asset),
                                      ledger.Leg(receiver_s, -amount), ledger.Leg(payer_s, amount)])
            except ledger.LedgerError:
                continue
    if share_part < BPS:
        state = bonds.market(conn, now)
        part = gap * (BPS - share_part) // BPS
        if part > 0:
            # Buying: the Government's nearest bills and bonds, from the pension funds where they have them, otherwise from the
            # Treasury itself (which sells its own as many as are asked for).
            treasury = ledger.account_id(conn, ledger.TREASURY)
            bills = [b for b in bonds._load(conn, "b.issuer = 'government' AND b.redeemed_period IS NULL")
                     if b["maturity_period"] > state["period"]][:4]
            for b in bills:
                fair = bonds.fair_value(b, state)
                if fair <= 0:
                    continue
                units = part // max(len(bills), 1) // fair
                from_dealers = min(units, ledger.balance(conn, institutions, b["asset"]))
                for seller, n in ((institutions, from_dealers), (treasury, units - from_dealers)):
                    if n <= 0:
                        continue
                    try:
                        with conn.transaction():
                            ledger.post(conn, kind="fund_rebalance" if seller == institutions else "bond_issue", memo=f"{fund['name']}: {n:,} of {b['name']}", period=period,
                                        legs=[ledger.Leg(seller, -n, b["asset"]), ledger.Leg(fund["account_id"], n, b["asset"]),
                                              ledger.Leg(fund["account_id"], -n * fair), ledger.Leg(seller, n * fair)])
                    except ledger.LedgerError:
                        continue
        else:
            # Selling: what the fund holds, nearest to being repaid first, to the pension funds as far as they can pay.
            need = -part
            for line in sorted(bonds.holdings_of(conn, fund["account_id"], now), key=lambda x: x["maturity_period"]):
                b = bonds.find(conn, line["code"])
                fair = bonds.fair_value(b, state)
                if need <= 0 or fair <= 0:
                    break
                n = min(-(-need // fair), ledger.balance(conn, fund["account_id"], b["asset"]), max(ledger.balance(conn, institutions), 0) // fair)
                if n <= 0:
                    continue
                try:
                    with conn.transaction():
                        ledger.post(conn, kind="fund_rebalance", memo=f"{fund['name']}: {n:,} of {b['name']} sold", period=period,
                                    legs=[ledger.Leg(fund["account_id"], -n, b["asset"]), ledger.Leg(institutions, n, b["asset"]),
                                          ledger.Leg(institutions, -n * fair), ledger.Leg(fund["account_id"], n * fair)])
                    need -= n * fair
                except ledger.LedgerError:
                    continue


def _sell_everything(conn: Connection, fund: dict, now: datetime, period: int) -> None:
    """Closing or merging into nothing: every share is sold to the institutions at 2% below its last price, every bond to the
    dealers at 1% below its fair value."""
    institutions = ledger.account_id(conn, ledger.INVESTORS_INSTITUTIONS)
    exchange.withdraw(conn, [fund["account_id"]], now, "The fund is closing")
    prices = {s["id"]: s for s in marketview._shares(conn, exchange.session_of(now)[0])}
    halted = {r["company_id"] for r in _rows(conn, "SELECT company_id FROM market_instruments WHERE halted_reason IS NOT NULL")}
    for row in _rows(conn, "SELECT company_id, shares FROM share_owners WHERE account_id = %s AND shares > 0", (fund["account_id"],)):
        s = prices.get(row["company_id"])
        if s is None or row["company_id"] in halted:
            continue                                      # a share whose trading is stopped waits until it trades again
        asset = f"SHR-{s['ticker']}"
        qty = ledger.balance(conn, fund["account_id"], asset)
        if qty <= 0:
            continue
        each = max(s["price"] * 98 // 100, 1)
        qty = min(qty, max(ledger.balance(conn, institutions), 0) // each)       # only as much as the dealers can pay for today
        if qty <= 0:
            continue
        ledger.post(conn, kind="fund_wind_up", memo=f"{fund['name']}: {qty:,} {s['ticker']} sold as it closes", period=period,
                    legs=[ledger.Leg(fund["account_id"], -qty, asset), ledger.Leg(institutions, qty, asset),
                          ledger.Leg(institutions, -qty * each), ledger.Leg(fund["account_id"], qty * each)])
    state = bonds.market(conn, now)
    for line in bonds.holdings_of(conn, fund["account_id"], now):
        b = bonds.find(conn, line["code"])
        units = ledger.balance(conn, fund["account_id"], b["asset"])
        if units <= 0:
            continue
        each = max(bonds.fair_value(b, state) * 99 // 100, 1)
        units = min(units, max(ledger.balance(conn, institutions), 0) // each)
        if units <= 0:
            continue
        ledger.post(conn, kind="fund_wind_up", memo=f"{fund['name']}: {units:,} of {b['name']} sold as it closes", period=period,
                    legs=[ledger.Leg(fund["account_id"], -units, b["asset"]), ledger.Leg(institutions, units, b["asset"]),
                          ledger.Leg(institutions, -units * each), ledger.Leg(fund["account_id"], units * each)])
    for loan in _rows(conn, "SELECT * FROM fund_loans WHERE fund_id = %s AND status = 'open'", (fund["id"],)):
        paid = ledger.pay_up_to(conn, payer=fund["account_id"], receiver=institutions, wanted=loan["owed"], kind="fund_loan_repayment",
                                memo=f"{fund['name']}: loan repaid as it closes", period=period)
        conn.execute("UPDATE fund_loans SET owed = owed - %s, status = CASE WHEN owed - %s <= 0 THEN 'repaid' ELSE 'open' END WHERE id = %s",
                     (paid, paid, loan["id"]))


def _wind_up(conn: Connection, fund: dict, day: date, now: datetime, period: int) -> None:
    if not fund["regulator_run"] and _regulator_audit(conn, fund, period, now, last=True):
        fund = _fund(conn, fund["id"])
    _sell_everything(conn, fund, now, period)
    fund = _fund(conn, fund["id"])
    left = _one(conn, "SELECT count(*) AS n FROM ledger_balances WHERE account_id = %s AND asset <> 'NGN' AND balance > 0", (fund["account_id"],))["n"]
    if left or owed(conn, fund):
        # The market's dealers could not take it all today: the rest is offered on the exchange, and the fund tries again at
        # the next bell. Nobody is paid until everything is sold, so every holder gets the same.
        for row in _rows(conn, "SELECT c.ticker, o.shares, m.reference_price FROM share_owners o JOIN companies c ON c.id = o.company_id"
                               " JOIN market_instruments m ON m.company_id = o.company_id WHERE o.account_id = %s AND o.shares > 0",
                         (fund["account_id"],)):
            low, _ = exchange.price_limits(row["reference_price"])
            try:
                with conn.transaction():
                    exchange.place_order(conn, account=fund["account_id"], ticker=row["ticker"], side="sell", kind="limit", quantity=row["shares"],
                                         limit_price=max(row["reference_price"] * 98 // 100, low), now=now)
            except (exchange.ExchangeError, ledger.LedgerError):
                continue
        return
    cash = max(ledger.balance(conn, fund["account_id"]), 0)
    units_all = fund["units"]
    holders = _rows(conn, "SELECT * FROM fund_units WHERE fund_id = %s AND units > 0 ORDER BY account_id", (fund["id"],))
    paid_all = 0
    for i, h in enumerate(holders):
        share = cash - paid_all if i == len(holders) - 1 else cash * h["units"] // units_all if units_all else 0
        if share > 0:
            ledger.transfer(conn, payer=fund["account_id"], receiver=h["account_id"], amount=share, kind="fund_units_sold",
                            memo=f"{fund['name']}: paid out as it closes", period=period)
            paid_all += share
    conn.execute("UPDATE fund_units SET units = 0, leaving = 0 WHERE fund_id = %s", (fund["id"],))
    for order in _rows(conn, "SELECT * FROM fund_orders WHERE fund_id = %s AND status = 'waiting'", (fund["id"],)):
        if order["side"] == "in":
            _undo(conn, order, "The fund closed: the money was handed back.")
        else:
            part = (order["units"] - order["units_done"]) * cash // units_all if units_all else 0
            conn.execute("UPDATE fund_orders SET status = 'dealt', dealt_at = %s, session_date = %s, paid = paid + %s, units_done = units,"
                         " words = 'Paid out as the fund closed.' WHERE id = %s", (now, day, part, order["id"]))
    conn.execute("UPDATE investment_funds SET units = 0, status = 'closed', closed_at = %s, gated_at = NULL WHERE id = %s", (now, fund["id"]))
    conn.execute("INSERT INTO fund_days (fund_id, session_date, unit_price, worth, units, money_out) VALUES (%s, %s, %s, 0, 0, %s)"
                 " ON CONFLICT DO NOTHING", (fund["id"], day, cash * UNIT // units_all if units_all else FIRST_PRICE, paid_all))
    _alert(conn, fund, "closed", f"{fund['name']} has closed", f"Everything it held was sold and {_money(paid_all)} paid out to its"
           f" {len(holders)} holders.", now)
    _news(conn, "fund_closed", fund, now, {"fund": fund["name"], "manager": _manager_name(conn, fund), "paid": _money(paid_all)})


def _merge(conn: Connection, fund: dict, merge: dict, day: date, now: datetime, period: int) -> None:
    into = _fund(conn, merge["into_fund"], lock=True)
    if into["status"] != "open" or owed(conn, fund):
        conn.execute("UPDATE fund_merges SET status = 'withdrawn' WHERE id = %s", (merge["id"],))
        return
    # Leavers who asked in time are paid first, at this bell.
    total = worth(conn, fund, now)
    _pay_leavers(conn, fund, total, order_cutoff(day), day, period, now)
    fund = _fund(conn, fund["id"])
    if leavers_waiting(conn, fund):
        return                                            # try again at the next bell, once they are paid
    if _regulator_audit(conn, fund, period, now, last=True):
        return                                            # the regulator found money taken: it winds the fund down instead
    for order in _rows(conn, "SELECT * FROM fund_orders WHERE fund_id = %s AND side = 'in' AND status = 'waiting' FOR UPDATE", (fund["id"],)):
        _undo(conn, order, f"The fund merged into {into['name']}: the money was handed back.")
    exchange.withdraw(conn, [fund["account_id"]], now, "The fund is merging")
    total = worth(conn, fund, now)
    their_price = unit_price(into, worth(conn, into, now))
    # Everything the fund holds moves across, as it is.
    legs = []
    for row in _rows(conn, "SELECT asset, balance FROM ledger_balances WHERE account_id = %s AND balance > 0", (fund["account_id"],)):
        legs += [ledger.Leg(fund["account_id"], -row["balance"], row["asset"]), ledger.Leg(into["account_id"], row["balance"], row["asset"])]
    if legs:
        ledger.post(conn, kind="fund_merge", memo=f"{fund['name']} merged into {into['name']}", period=period, legs=legs)
    for h in _rows(conn, "SELECT * FROM fund_units WHERE fund_id = %s AND units > 0", (fund["id"],)):
        value = h["units"] * total // fund["units"] if fund["units"] else 0
        _issue(conn, into, h["account_id"], value * UNIT // max(their_price, 1), now)
        into = _fund(conn, into["id"])
    conn.execute("UPDATE fund_units SET units = 0, leaving = 0 WHERE fund_id = %s", (fund["id"],))
    conn.execute("UPDATE investment_funds SET units = 0, status = 'merged', merged_into = %s, closed_at = %s WHERE id = %s", (into["id"], now, fund["id"]))
    conn.execute("UPDATE fund_merges SET status = 'done' WHERE id = %s", (merge["id"],))
    _alert(conn, fund, "merged", f"{fund['name']} has merged into {into['name']}", f"Its holders now hold units of {into['name']} of the same value.", now)
    _news(conn, "fund_merged", fund, now, {"fund": fund["name"], "into": into["name"], "manager": _manager_name(conn, into)})


# ---------------------------------------------------------------------------
# The quarter's close: the performance fee, disclosures, stars, the computer's money, the regulator
# ---------------------------------------------------------------------------

def after_close(conn: Connection, period: int, now: datetime) -> None:
    if not ready(conn) or not _one(conn, "SELECT 1 AS x FROM investment_funds LIMIT 1"):
        return                                   # the funds start at the first closing bell the server deals (see tick)
    closes = {}
    for f in _rows(conn, "SELECT id FROM investment_funds WHERE status IN ('open', 'closing') ORDER BY id"):
        try:
            with conn.transaction():
                closes[f["id"]] = _close_one(conn, _fund(conn, f["id"], lock=True), period, now)
        except Exception:
            log.exception("A fund's quarter close failed")
    with conn.transaction():
        _rate(conn, period, now, closes)
    for f in _rows(conn, "SELECT id FROM investment_funds WHERE status = 'open' ORDER BY id"):
        with conn.transaction():
            _computer_money(conn, _fund(conn, f["id"], lock=True), period, now)
    for m in _rows(conn, "SELECT * FROM fund_merges WHERE status = 'proposed' AND proposed_at < %s", (now - timedelta(days=MERGE_ANSWER_DAYS),)):
        conn.execute("UPDATE fund_merges SET status = 'refused' WHERE id = %s", (m["id"],))


def _close_one(conn: Connection, fund: dict, period: int, now: datetime) -> dict:
    _regulator_audit(conn, fund, period, now)
    fund = _fund(conn, fund["id"])
    h = holdings(conn, fund, now)
    total = h["total"]
    price = unit_price(fund, total)
    perf = 0
    if fund["perf_fee_bps"] and fund["manager_id"] and not fund["regulator_run"] and fund["units"] and price > fund["high_water"]:
        gain = value_of(fund["units"], price - fund["high_water"])
        perf = ledger.pay_up_to(conn, payer=fund["account_id"], receiver=ledger.player_account_id(conn, fund["manager_id"]),
                                wanted=apply_bps(gain, fund["perf_fee_bps"]), kind="fund_fee",
                                memo=f"{fund['name']}: the performance fee, {clock.period_label(period)}", period=period)
        total -= perf
        price = unit_price(fund, total)
    if price > fund["high_water"]:
        conn.execute("UPDATE investment_funds SET high_water = %s WHERE id = %s", (price, fund["id"]))
    lines = [{"ticker": line["ticker"], "weight_bps": line["value"] * BPS // total if total > 0 else 0} for line in h["lines"]]
    lines += [{"ticker": b["code"], "name": b["name"], "weight_bps": b["value"] * BPS // total if total > 0 else 0} for b in h["bond_lines"]]
    lines.sort(key=lambda x: -x["weight_bps"])
    conn.execute("INSERT INTO fund_disclosures (fund_id, period, holdings) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                 (fund["id"], period, Jsonb({"lines": lines[:15], "cash_bps": h["cash"] * BPS // total if total > 0 else 0})))
    published = _one(conn, "SELECT period FROM fund_disclosures WHERE fund_id = %s AND period = %s", (fund["id"], period - 1))
    if published:
        _alert(conn, fund, "holdings", f"{fund['name']} publishes what it held",
               f"Its holdings at the end of {clock.period_label(period - 1)} are now on its page.", now)
    holders = _one(conn, "SELECT count(*) AS n FROM fund_units WHERE fund_id = %s AND units > 0", (fund["id"],))["n"]
    # A fund too small, two quarter ends running after its first two, is closed.
    if not fund["computer"] and fund["status"] == "open" and period - fund["launched_period"] >= 2:
        small = total < naira(data.INVEST_FUND_SMALL_NAIRA)
        conn.execute("UPDATE investment_funds SET small_quarters = %s WHERE id = %s", ((fund["small_quarters"] + 1) if small else 0, fund["id"]))
        if small and fund["small_quarters"] + 1 >= data.INVEST_FUND_SMALL_QUARTERS:
            _start_closing(conn, _fund(conn, fund["id"]), f"It has stayed under {_money(naira(data.INVEST_FUND_SMALL_NAIRA))} for two quarters.", now)
    return {"unit_price": price, "worth": total, "holders": holders, "perf_fee": perf}


def _quarter_returns(conn: Connection, fund: dict, period: int, quarters: int, start: datetime) -> tuple[float, float, float, int] | None:
    """Over the last `quarters` quarters (as far as the record goes): the fund's return, its benchmark's, and its yearly swing."""
    first = start + timedelta(days=clock.REAL_DAYS_PER_QUARTER) * (period - quarters)
    days = _rows(conn, "SELECT session_date, unit_price, benchmark FROM fund_days WHERE fund_id = %s AND session_date > %s ORDER BY session_date",
                 (fund["id"], clock.to_lagos(first).date()))
    if len(days) < 5:
        return None
    rets = [days[i]["unit_price"] / days[i - 1]["unit_price"] - 1 for i in range(1, len(days)) if days[i - 1]["unit_price"]]
    mine = days[-1]["unit_price"] / days[0]["unit_price"] - 1
    bench = (days[-1]["benchmark"] / days[0]["benchmark"] - 1) if days[0]["benchmark"] and days[-1]["benchmark"] else 0.0
    mean = sum(rets) / len(rets)
    swing = math.sqrt(sum((r - mean) ** 2 for r in rets) / max(len(rets) - 1, 1)) * math.sqrt(data.INVEST_FUND_SESSIONS_PER_YEAR)
    return mine, bench, swing, len(days)


def _rate(conn: Connection, period: int, now: datetime, closes: dict) -> None:
    """One to five stars, each quarter, for every fund with a full quarter of record: on its return for the risk it took
    over the last year (or as much of it as there is). Against the funds with the same strategy when there are five or more
    of them; otherwise against its benchmark. The quarter's row (permanent) is written once, with its rating."""
    world = _one(conn, "SELECT world_start, weeks_ahead FROM world_state")
    start = clock.effective_start(world["world_start"], world["weeks_ahead"])
    rate = _policy_rate(conn)
    scored = []
    for fund in _rows(conn, "SELECT * FROM investment_funds WHERE id = ANY(%s) AND status = 'open' AND launched_period <= %s",
                      (list(closes), period - 1)):
        r = _quarter_returns(conn, fund, period, 4, start)
        if r is None:
            continue
        q = _quarter_returns(conn, fund, period, 1, start)
        mine, bench, swing, _ = r
        ratio = (mine - rate / BPS) / swing if swing > 0 else 0.0
        scored.append({"fund": fund, "mine": mine, "bench": bench, "ratio": ratio, "quarter": q[0] if q else None})
    by_strategy: dict[str, list] = {}
    for s in scored:
        by_strategy.setdefault(s["fund"]["strategy"], []).append(s)
    rated = {}
    for group in by_strategy.values():
        group.sort(key=lambda s: s["ratio"])
        n = len(group)
        for i, s in enumerate(group):
            if n >= 5:
                rank = (i + 0.5) / n
                stars = 1 if rank < 0.10 else 2 if rank < 0.325 else 3 if rank < 0.675 else 4 if rank < 0.90 else 5
            else:
                excess = s["mine"] - s["bench"]
                stars = 5 if excess >= 0.05 else 4 if excess >= 0.02 else 3 if excess >= -0.02 else 2 if excess >= -0.05 else 1
            rated[s["fund"]["id"]] = (stars, s)
    for fund_id, c in closes.items():
        stars, s = rated.get(fund_id, (None, None))
        conn.execute("INSERT INTO fund_quarters (fund_id, period, unit_price, worth, holders, perf_fee, stars, quarter_bps, year_bps, bench_bps,"
                     " risk_ratio) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
                     (fund_id, period, c["unit_price"], c["worth"], c["holders"], c["perf_fee"], stars,
                      round(s["quarter"] * BPS) if s and s["quarter"] is not None else None, round(s["mine"] * BPS) if s else None,
                      round(s["bench"] * BPS) if s else None, round(s["ratio"], 2) if s else None))
        if stars is None:
            continue
        fund = s["fund"]
        before = _one(conn, "SELECT stars FROM fund_quarters WHERE fund_id = %s AND period < %s AND stars IS NOT NULL ORDER BY period DESC LIMIT 1",
                      (fund_id, period))
        if before is None or before["stars"] != stars:
            _alert(conn, fund, "stars", f"{fund['name']}: {'★' * stars}{'☆' * (5 - stars)}",
                   f"Its rating {'is now' if before else 'starts at'} {stars} star{'s' if stars > 1 else ''}"
                   + (f" (it was {before['stars']})." if before else "."), now)
            if stars == 5 and not fund["computer"]:
                _news(conn, "fund_five_stars", fund, now, {"fund": fund["name"], "manager": _manager_name(conn, fund),
                                                           "year": _pct(round(s["mine"] * BPS))})


def stars_of(conn: Connection, fund_id) -> int | None:
    row = _one(conn, "SELECT stars FROM fund_quarters WHERE fund_id = %s AND stars IS NOT NULL ORDER BY period DESC LIMIT 1", (fund_id,))
    return row["stars"] if row else None


def _computer_money(conn: Connection, fund: dict, period: int, now: datetime) -> None:
    """The households follow the stars: money in to good funds, out of poor ones, at the next bell."""
    public = ledger.account_id(conn, HOUSEHOLDS)
    total = worth(conn, fund, now)
    if total <= 0:
        return
    stars = stars_of(conn, fund["id"])
    bps = data.INVEST_FUND_STAR_FLOWS_BPS[stars] if stars else data.INVEST_FUND_NEW_FLOW_BPS
    if bps > 0:
        amount = max(apply_bps(total, bps), naira(data.INVEST_FUND_NEW_FLOW_LEAST_NAIRA) if not stars else 0)
        amount = min(amount, max(ledger.balance(conn, public), 0))
        if amount > 0:
            ledger.transfer(conn, payer=public, receiver=dealing_account(conn), amount=amount, kind="fund_order_hold",
                            memo=f"{fund['name']}: households' money held until the bell", period=period)
            conn.execute("INSERT INTO fund_orders (fund_id, account_id, side, amount, placed_at) VALUES (%s, %s, 'in', %s, %s)",
                         (fund["id"], public, amount, now))
    elif bps < 0:
        held = _one(conn, "SELECT * FROM fund_units WHERE fund_id = %s AND account_id = %s", (fund["id"], public))
        if held and held["units"] - held["leaving"] > 0:
            units = (held["units"] - held["leaving"]) * -bps // BPS
            if units > 0:
                conn.execute("UPDATE fund_units SET leaving = leaving + %s WHERE fund_id = %s AND account_id = %s", (units, fund["id"], public))
                conn.execute("INSERT INTO fund_orders (fund_id, account_id, side, units, placed_at) VALUES (%s, %s, 'out', %s, %s)",
                             (fund["id"], public, units, now))


def _regulator_audit(conn: Connection, fund: dict, period: int, now: datetime, *, last: bool = False) -> bool:
    """The regulator looks at every fund's books for the quarter just closed, and once more at a fund's books as it closes or
    merges (so closing a fund is no way to escape it). It finds a false cost less often than not; a manager proved to have
    taken money repays it and a fine, is struck off, and the regulator winds the fund down. True if it found anything."""
    entries = _rows(conn, "SELECT * FROM fund_books WHERE fund_id = %s AND NOT genuine AND NOT found", (fund["id"],))
    found = [e for e in entries if _roll("fund-audit", "last" if last else "quarter", fund["id"], period, e["id"]) < data.INVEST_FUND_AUDIT_FINDS_BPS]
    if not found:
        return False
    manager = fund["manager_id"]
    taken = sum(e["amount"] for e in found)
    conn.execute("UPDATE fund_books SET found = true WHERE id = ANY(%s)", ([e["id"] for e in found],))
    if manager:
        me = ledger.player_account_id(conn, manager)
        back = ledger.pay_up_to(conn, payer=me, receiver=fund["account_id"], wanted=taken, kind="fund_repayment",
                                memo=f"{fund['name']}: money taken, repaid", period=period)
        fine = ledger.pay_up_to(conn, payer=me, receiver=ledger.account_id(conn, ledger.TREASURY), wanted=apply_bps(taken, data.INVEST_FUND_FINE_BPS),
                                kind="fine", memo=f"{fund['name']}: a fine for taking the fund's money", period=period)
        conn.execute("INSERT INTO legal_records (player_id, kind, words, at) VALUES (%s, 'theft', %s, %s)",
                     (manager, f"Proved to have taken {_money(taken)} from the fund {fund['name']}; repaid {_money(back)} and fined {_money(fine)}.", now))
        careers._event(conn, manager, "asset_manager", "struck_off", f"Struck off as manager of {fund['name']}.", now)
    conn.execute("UPDATE investment_funds SET manager_id = NULL, regulator_run = true, fee_bps = 0, perf_fee_bps = 0 WHERE id = %s", (fund["id"],))
    fund = _fund(conn, fund["id"])
    _alert(conn, fund, "struck_off", f"{fund['name']}'s manager is struck off", "The regulator proved the manager took the fund's money."
           " The money was paid back; the regulator now runs the fund, charges no fee, and is winding it down.", now, everyone=True)
    _news(conn, "fund_struck_off", fund, now, {"fund": fund["name"], "amount": _money(taken)})
    if fund["status"] == "open":
        _start_closing(conn, fund, "The regulator is winding the fund down.", now)
    return True


# ---------------------------------------------------------------------------
# Pop-ups and news
# ---------------------------------------------------------------------------

def _alert(conn: Connection, fund: dict, kind: str, headline: str, words: str, now: datetime, *, everyone: bool = False) -> None:
    conn.execute("INSERT INTO fund_alerts (fund_id, kind, everyone, headline, words, at) VALUES (%s, %s, %s, %s, %s, %s)",
                 (fund["id"], kind, everyone, headline[:160], words[:600], now))


def _news(conn: Connection, kind: str, fund: dict, now: datetime, facts: dict) -> None:
    from simulation import news
    if kind not in news.BY_NAME:
        return
    w = careers.world_now(conn, now)
    news.publish(conn, period=w["period"], day=w["day"], kind=kind, story=f"fund:{fund['id']}:{kind}", facts=facts)


def alerts_for(conn: Connection, player_id, after: int | None, now: datetime) -> dict:
    """The pop-ups a player should see: everybody's, and those of the funds they (or their empire) hold or follow."""
    accounts = [ledger.player_account_id(conn, player_id)]
    seat = empires.seat_of(conn, player_id)
    if seat and seat["empire_kind"] != "pension":
        accounts.append(seat["account_id"])
    since = after if after is not None else (_one(conn, "SELECT coalesce(max(id), 0) AS m FROM fund_alerts WHERE at < %s", (now - timedelta(hours=24),))["m"])
    found = _rows(conn, "SELECT a.id, a.kind, a.headline, a.words, a.at, a.fund_id, f.name AS fund FROM fund_alerts a JOIN investment_funds f ON f.id = a.fund_id"
                       " WHERE a.id > %s AND (a.everyone OR EXISTS (SELECT 1 FROM fund_units u WHERE u.fund_id = a.fund_id AND u.account_id = ANY(%s) AND u.units > 0)"
                       " OR EXISTS (SELECT 1 FROM fund_follows w WHERE w.fund_id = a.fund_id AND w.player_id = %s)"
                       " OR (a.kind = 'merged' AND EXISTS (SELECT 1 FROM fund_merges m JOIN fund_units u ON u.fund_id = m.into_fund"
                       "     WHERE m.from_fund = a.fund_id AND u.account_id = ANY(%s) AND u.units > 0)))"
                       " ORDER BY a.id LIMIT 5", (since, accounts, player_id, accounts))
    newest = _one(conn, "SELECT coalesce(max(id), 0) AS m FROM fund_alerts")["m"]
    return {"mark": found[-1]["id"] if len(found) == 5 else max(newest, since), "alerts": found}


# ---------------------------------------------------------------------------
# What it is all worth to its holders (net worth, an empire's wealth)
# ---------------------------------------------------------------------------

def held_value(conn: Connection, account, now: datetime | None = None) -> int:
    """An account's units at each fund's selling price, and its money waiting to come in."""
    if not ready(conn):
        return 0
    total = 0
    for h in _rows(conn, "SELECT f.*, u.units AS held FROM fund_units u JOIN investment_funds f ON f.id = u.fund_id WHERE u.account_id = %s AND u.units > 0",
                   (account,)):
        last = _one(conn, "SELECT unit_price FROM fund_days WHERE fund_id = %s ORDER BY session_date DESC LIMIT 1", (h["id"],))
        price = last["unit_price"] if last else FIRST_PRICE
        total += value_of(h["held"], price * (BPS - data.INVEST_FUND_SWING_BPS) // BPS)
    total += _one(conn, "SELECT coalesce(sum(amount), 0)::bigint AS t FROM fund_orders WHERE account_id = %s AND side = 'in' AND status = 'waiting'",
                  (account,))["t"]
    return total


def _players_holdings(conn: Connection) -> dict:
    out: dict = {}
    if not ready(conn):
        return out
    rows = _rows(conn, "SELECT DISTINCT u.account_id FROM fund_units u JOIN ledger_accounts a ON a.id = u.account_id WHERE a.kind = 'player' AND u.units > 0"
                       " UNION SELECT DISTINCT o.account_id FROM fund_orders o JOIN ledger_accounts a ON a.id = o.account_id WHERE a.kind = 'player'"
                       " AND o.side = 'in' AND o.status = 'waiting'")
    for r in rows:
        out[r["account_id"]] = (0, held_value(conn, r["account_id"]))
    return out


def _register() -> None:
    if _players_holdings not in marketview._OTHER_HOLDINGS:
        marketview._OTHER_HOLDINGS.append(_players_holdings)


_register()


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

def _days(conn: Connection, fund_id, limit: int = 200) -> list[dict]:
    return _rows(conn, "SELECT * FROM (SELECT session_date, unit_price, worth, money_in, money_out, benchmark FROM fund_days WHERE fund_id = %s"
                       " ORDER BY session_date DESC LIMIT %s) d ORDER BY session_date", (fund_id, limit))


def _summary(conn: Connection, fund: dict, now: datetime) -> dict:
    days = _days(conn, fund["id"])
    price = days[-1]["unit_price"] if days else FIRST_PRICE
    total = days[-1]["worth"] if days else worth(conn, fund, now)
    def back(n):
        return days[-1 - n] if len(days) > n else None
    def change(row):
        return (price - row["unit_price"]) * BPS // row["unit_price"] if row and row["unit_price"] else None
    peak, worst = 0, 0
    for d in days:
        peak = max(peak, d["unit_price"])
        if peak:
            worst = min(worst, (d["unit_price"] - peak) * BPS // peak)
    since = (price - FIRST_PRICE) * BPS // FIRST_PRICE
    bench = None
    if days and days[0]["benchmark"] and days[-1]["benchmark"]:
        bench = (days[-1]["benchmark"] - days[0]["benchmark"]) * BPS // days[0]["benchmark"]
    first = days[0]["unit_price"] if days else FIRST_PRICE
    return {
        "id": fund["id"], "name": fund["name"], "strategy": fund["strategy"], "strategy_name": STRATEGIES[fund["strategy"]],
        "manager": _manager_name(conn, fund),
        "computer": fund["computer"], "regulator_run": fund["regulator_run"], "status": fund["status"], "gated": fund["gated_at"] is not None,
        "run": bool(fund["run_until"] and fund["run_until"] >= exchange.session_of(now)[0]),
        "fee_bps": fund["fee_bps"], "perf_fee_bps": fund["perf_fee_bps"], "least_in": fund["least_in"],
        "unit_price": price, "worth": total, "stars": stars_of(conn, fund["id"]),
        "day_bps": change(back(1)), "quarter_bps": change(back(7)), "year_bps": change(back(28)),
        "since_bps": since, "shown_bps": (price - first) * BPS // first if first else None, "bench_bps": bench, "worst_fall_bps": worst,
        "holders": _one(conn, "SELECT count(*) AS n FROM fund_units WHERE fund_id = %s AND units > 0", (fund["id"],))["n"],
        "launched_period": clock.period_label(fund["launched_period"]),
    }


def listing(conn: Connection, player_id, now: datetime) -> dict:
    funds = [_summary(conn, f, now) for f in _rows(conn, "SELECT * FROM investment_funds WHERE status IN ('open', 'closing') ORDER BY id")]
    tables = {}
    for key in STRATEGIES:
        group = [f for f in funds if f["strategy"] == key]
        group.sort(key=lambda f: (-(f["stars"] or 0), -(f["year_bps"] if f["year_bps"] is not None else -10**9)))
        tables[key] = [f["id"] for f in group]
    career = careers.career(conn, player_id, "asset_manager")
    build = _one(conn, "SELECT build FROM players WHERE id = %s", (player_id,))["build"]
    runs = _one(conn, "SELECT 1 AS x FROM investment_funds WHERE manager_id = %s AND status IN ('open', 'closing')", (player_id,))
    return {"funds": funds, "tables": tables, "strategies": STRATEGIES, "strategy_words": STRATEGY_WORDS,
            "can_launch": bool(build == "asset_manager" and career and career["level"] >= data.INVEST_FUND_LEVEL and not runs),
            "launch": {"level": data.INVEST_FUND_LEVEL, "registration": naira(data.INVEST_FUND_REGISTRATION_NAIRA),
                       "seed": naira(data.INVEST_FUND_SEED_NAIRA), "fee_most_bps": data.INVEST_FUND_FEE_MOST_BPS,
                       "perf_most_bps": data.INVEST_FUND_PERF_FEE_MOST_BPS,
                       "least_in_limits": [naira(x) for x in data.INVEST_FUND_LEAST_IN_LIMITS_NAIRA]}}


def factsheet(conn: Connection, fund_id: int, player_id, now: datetime) -> dict:
    fund = _fund(conn, fund_id)
    state = careers.world_now(conn, now)
    out = _summary(conn, fund, now)
    out["words"] = fund["words"]
    out["strategy_words"] = STRATEGY_WORDS[fund["strategy"]]
    out["benchmark"] = BENCHMARK_WORDS[fund["strategy"]]
    days = _days(conn, fund_id)
    base_p = days[0]["unit_price"] if days else FIRST_PRICE
    base_b = days[0]["benchmark"] if days and days[0]["benchmark"] else None
    out["chart"] = [{"day": d["session_date"], "fund_bps": (d["unit_price"] - base_p) * BPS // base_p,
                     "bench_bps": (d["benchmark"] - base_b) * BPS // base_b if base_b and d["benchmark"] else None} for d in days]
    out["quarters"] = _rows(conn, "SELECT period, stars, quarter_bps, year_bps, bench_bps, risk_ratio, holders FROM fund_quarters WHERE fund_id = %s"
                                  " ORDER BY period DESC LIMIT 12", (fund_id,))
    for q in out["quarters"]:
        q["label"] = clock.period_label(q["period"])
        q["risk_ratio"] = float(q["risk_ratio"]) if q["risk_ratio"] is not None else None
    shown = _one(conn, "SELECT period, holdings FROM fund_disclosures WHERE fund_id = %s AND period <= %s ORDER BY period DESC LIMIT 1",
                 (fund_id, state["period"] - 2))
    out["holdings"] = {"label": clock.period_label(shown["period"]), **shown["holdings"]} if shown else None
    if out["holdings"]:
        names = {r["ticker"]: r["name"] for r in _rows(conn, "SELECT ticker, name FROM companies")}
        out["holdings"]["lines"] = [{**line, "name": line.get("name") or names.get(line["ticker"], line["ticker"])} for line in out["holdings"]["lines"]]
    out["rules"] = [
        f"No holding above {data.INVEST_FUND_ONE_HOLDING_BPS / 100:g}% of the fund; at least {data.INVEST_FUND_LEAST_CASH_BPS / 100:g}% in cash.",
        STRATEGY_WORDS[fund["strategy"]],
        "Money in and out is dealt at the next closing bell's price; coming in pays 0.25% above it, going out 0.25% below (kept by the fund).",
        f"It may borrow at most {data.INVEST_FUND_BORROW_MOST_BPS / 100:g}% of itself, only to pay investors who leave.",
        "The manager may never deal with the fund, and keeps at least 1% of it (or all they put in) while running it.",
        "What it held at a quarter's end is published one quarter later.",
    ]
    accounts = [ledger.player_account_id(conn, player_id)]
    seat = empires.seat_of(conn, player_id)
    empire_account = seat["account_id"] if seat and seat["empire_kind"] != "pension" else None
    mine = _one(conn, "SELECT units, leaving FROM fund_units WHERE fund_id = %s AND account_id = %s", (fund_id, accounts[0]))
    out["mine"] = {"units": mine["units"] if mine else 0, "leaving": mine["leaving"] if mine else 0,
                   "value": value_of(mine["units"], unit_price(fund, out["worth"], side="out")) if mine else 0}
    if empire_account:
        e = _one(conn, "SELECT units, leaving FROM fund_units WHERE fund_id = %s AND account_id = %s", (fund_id, empire_account))
        out["empire"] = {"units": e["units"] if e else 0, "leaving": e["leaving"] if e else 0, "head": seat["head_player_id"] == player_id,
                         "value": value_of(e["units"], unit_price(fund, out["worth"], side="out")) if e else 0}
    out["orders"] = _rows(conn, "SELECT id, side, amount, units, status, placed_at, dealt_at, units_done, paid, words FROM fund_orders"
                                " WHERE fund_id = %s AND player_id = %s ORDER BY id DESC LIMIT 10", (fund_id, player_id))
    out["following"] = bool(_one(conn, "SELECT 1 AS x FROM fund_follows WHERE fund_id = %s AND player_id = %s", (fund_id, player_id)))
    out["merging"] = _one(conn, "SELECT m.status, m.takes_effect, f.name AS into FROM fund_merges m JOIN investment_funds f ON f.id = m.into_fund"
                                " WHERE m.from_fund = %s AND m.status = 'agreed'", (fund_id,))
    out["recent"] = _rows(conn, "SELECT headline, words, at FROM fund_alerts WHERE fund_id = %s ORDER BY id DESC LIMIT 6", (fund_id,))
    return out


def mine(conn: Connection, player_id, now: datetime) -> dict:
    """The player's (and their empire's) funds, for the Money section."""
    me = ledger.player_account_id(conn, player_id)
    seat = empires.seat_of(conn, player_id)
    accounts = [(me, "you")] + ([(seat["account_id"], "empire")] if seat and seat["empire_kind"] != "pension" else [])
    lines = []
    for account, whose in accounts:
        for h in _rows(conn, "SELECT f.*, u.units AS held, u.leaving AS held_leaving FROM fund_units u JOIN investment_funds f ON f.id = u.fund_id WHERE u.account_id = %s"
                             " AND u.units > 0 ORDER BY f.name", (account,)):
            s = _summary(conn, h, now)
            lines.append({**s, "whose": whose, "units": h["held"], "leaving": h["held_leaving"],
                          "value": value_of(h["held"], s["unit_price"] * (BPS - data.INVEST_FUND_SWING_BPS) // BPS)})
    waiting = _rows(conn, "SELECT o.id, o.side, o.amount, o.units, o.placed_at, f.name AS fund, f.id AS fund_id FROM fund_orders o"
                          " JOIN investment_funds f ON f.id = o.fund_id WHERE o.player_id = %s AND o.status = 'waiting' ORDER BY o.id", (player_id,))
    return {"lines": lines, "waiting": waiting, "value": sum(line["value"] for line in lines if line["whose"] == "you")}


def manager_view(conn: Connection, manager_id, now: datetime) -> dict | None:
    fund = _one(conn, "SELECT * FROM investment_funds WHERE manager_id = %s AND status IN ('open', 'closing')", (manager_id,))
    if fund is None:
        return None
    state = careers.world_now(conn, now)
    h = holdings(conn, fund, now)
    total = h["total"]
    out = _summary(conn, fund, now)
    largest = max([line["value"] for line in h["lines"]] + [b["value"] for b in h["bond_lines"] if b.get("ticker")] + [0])
    out.update({
        "cash": h["cash"], "shares_value": h["shares"], "bonds_value": h["bonds"], "owed": h["owed"], "worth_now": total,
        "cash_bps": h["cash"] * BPS // total if total > 0 else 0, "largest_bps": largest * BPS // total if total > 0 else 0,
        "shares_bps": h["shares"] * BPS // total if total > 0 else 0, "bonds_bps": h["bonds"] * BPS // total if total > 0 else 0,
        "lines": [{"ticker": line["ticker"], "shares": line["shares"], "value": line["value"]} for line in h["lines"]],
        "bond_lines": [{"code": b["code"], "name": b["name"], "units": b["units"], "value": b["value"]} for b in h["bond_lines"]],
        "orders": exchange.orders_of(conn, fund["account_id"], limit=10),
        "leavers_waiting": leavers_waiting(conn, fund),
        "waiting_in": _one(conn, "SELECT coalesce(sum(amount), 0)::bigint AS t FROM fund_orders WHERE fund_id = %s AND side = 'in' AND status = 'waiting'",
                           (fund["id"],))["t"],
        "waiting_out_units": _one(conn, "SELECT coalesce(sum(units - units_done), 0)::bigint AS t FROM fund_orders WHERE fund_id = %s AND side = 'out'"
                                        " AND status = 'waiting'", (fund["id"],))["t"],
        "costs_limit": apply_bps(total, data.INVEST_FUND_COSTS_BPS),
        "costs_used": _one(conn, "SELECT coalesce(sum(amount), 0)::bigint AS t FROM fund_books WHERE fund_id = %s AND period = %s",
                           (fund["id"], state["period"]))["t"],
        "merges_waiting": _rows(conn, "SELECT m.id, f.name AS from_fund FROM fund_merges m JOIN investment_funds f ON f.id = m.from_fund"
                                      " WHERE m.into_fund = %s AND m.status = 'proposed'", (fund["id"],)),
        "merge_out": _one(conn, "SELECT m.status, f.name AS into FROM fund_merges m JOIN investment_funds f ON f.id = m.into_fund"
                                " WHERE m.from_fund = %s AND m.status IN ('proposed', 'agreed')", (fund["id"],)),
        "high_water": fund["high_water"],
    })
    return out


# ---------------------------------------------------------------------------
# Proven Talent: the manager's track record
# ---------------------------------------------------------------------------

def track_record(conn: Connection, player_id) -> dict:
    """Every fund the player has run: return since launch, against its benchmark, stars, and whether it came through a run."""
    if not ready(conn):
        return {"funds": [], "best_stars": None, "five_star_quarters": 0, "runs_survived": 0}
    funds = []
    for f in _rows(conn, "SELECT * FROM investment_funds WHERE founder_id = %s ORDER BY id", (player_id,)):
        days = _rows(conn, "SELECT unit_price, benchmark FROM fund_days WHERE fund_id = %s ORDER BY session_date", (f["id"],))
        quarters = _rows(conn, "SELECT stars FROM fund_quarters WHERE fund_id = %s AND stars IS NOT NULL", (f["id"],))
        ret = (days[-1]["unit_price"] - FIRST_PRICE) * BPS // FIRST_PRICE if days else None
        bench = ((days[-1]["benchmark"] - days[0]["benchmark"]) * BPS // days[0]["benchmark"]) if days and days[0]["benchmark"] and days[-1]["benchmark"] else None
        funds.append({"name": f["name"], "strategy": STRATEGIES[f["strategy"]], "since": clock.period_label(f["launched_period"]),
                      "status": "struck off" if f["regulator_run"] else f["status"], "return_bps": ret, "bench_bps": bench,
                      "stars_now": quarters[-1]["stars"] if quarters else None, "best_stars": max((q["stars"] for q in quarters), default=None),
                      "five_star_quarters": sum(1 for q in quarters if q["stars"] == 5), "quarters_rated": len(quarters),
                      "run_survived": _came_through_run(conn, f)})
    return {"funds": funds, "best_stars": max((f["best_stars"] or 0 for f in funds), default=0) or None,
            "five_star_quarters": sum(f["five_star_quarters"] for f in funds), "runs_survived": sum(1 for f in funds if f["run_survived"])}


def _came_through_run(conn: Connection, fund: dict) -> bool:
    """A run on the fund, and the fund still open (and not taken over by the regulator) a game quarter after it began."""
    run = _one(conn, "SELECT min(at) AS at FROM fund_alerts WHERE fund_id = %s AND kind = 'run'", (fund["id"],))["at"]
    if run is None or fund["regulator_run"]:
        return False
    lasted_until = fund["closed_at"] if fund["status"] in ("closed", "merged") else None
    if lasted_until is not None and lasted_until < run + timedelta(days=clock.REAL_DAYS_PER_QUARTER):
        return False
    return bool(lasted_until is not None or _one(conn, "SELECT 1 AS x FROM closing_bells WHERE rung_at >= %s LIMIT 1",
                                                 (run + timedelta(days=clock.REAL_DAYS_PER_QUARTER),)))


def check_books(conn: Connection) -> list[str]:
    """Units add up; money waiting to come in is all in the dealing account."""
    problems = []
    for f in _rows(conn, "SELECT f.id, f.name, f.units, coalesce(sum(u.units), 0) AS held FROM investment_funds f LEFT JOIN fund_units u ON u.fund_id = f.id"
                         " GROUP BY f.id"):
        if f["units"] != f["held"]:
            problems.append(f"{f['name']}: {f['units']} units in issue, {f['held']} held")
    acc = _one(conn, "SELECT id FROM ledger_accounts WHERE code = %s", (DEALING,))
    if acc:
        waiting = _one(conn, "SELECT coalesce(sum(amount), 0)::bigint AS t FROM fund_orders WHERE side = 'in' AND status = 'waiting'")["t"]
        if ledger.balance(conn, acc["id"]) != waiting:
            problems.append(f"Fund dealing holds {ledger.balance(conn, acc['id'])}, but {waiting} is waiting to come in")
    return problems
