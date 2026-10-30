"""Index funds and ETFs (the talent and funds stage, Part 3).

An ETF is a fund that copies an index (or the price of oil, or of metals) and whose units trade on the exchange all day,
like a share. Units come into existence only when an approved dealer makes them: the dealer hands the fund a basket of the
shares it holds (or the cash to buy them) and gets new units worth the same; unmaking them is the reverse. The game's own
dealers, the pension funds, make the market in every ETF: they quote a price either side of where they think it is worth,
and that "where" drifts with buying and selling. When the price drifts far enough from the fund's true value, an approved
dealer can buy the cheap side and make or unmake units against the dear one: that is what keeps an ETF's price honest, and
it is a real way to make money. The game's own dealers step in once the gap reaches 0.75% (1.5% for the special ETFs).

Every ETF publishes its value through the day (its "iNAV") and its basket. A full-copy ETF holds every member of its
index in proportion; a sampling one holds only the largest members, up to 80% of the index. The 2x and inverse ETFs, and
the oil and metals ETFs, hold cash and settle the day's move with the pension funds at each closing bell: they reset every
day, so over many days they do not simply give twice (or minus) the index's move. Buying them needs Level 15 in any build
and having read the warning.

An index fund is one of Part 2's funds that copies an index: money in and out at the next bell, and the game deals for it.

The households put a growing share of their savings into index funds and ETFs: 3% of the market at the start, 3% more
each game year, at most 35%. The cheapest, closest-copying vehicles get the most of it. Each index's changes are announced
three bells ahead, so everybody can see what the index funds will have to buy and sell, and trade around it lawfully.
"""

from __future__ import annotations

import hashlib
import logging
import math
from datetime import date, datetime, timedelta
from decimal import Decimal

from psycopg import Connection
from psycopg.rows import dict_row

from simulation import careers, clock, empires, exchange, indexes, ledger, objectives
from simulation import world_data as data
from simulation.ledger import Leg
from simulation.money import BPS, apply_bps, naira

log = logging.getLogger("wsbm.etfs")

HELD = "etf:held"                      # cash held for buy orders, units held for sell orders
HOUSEHOLDS = "households:lagos"
DEALING_COST_BPS = 10                  # dealing with the market's dealers (when a fund buys or sells to copy its index): 0.1%
SPECIAL = {"leverage", "inverse", "commodity"}


class EtfError(Exception):
    """A request about an ETF or an index fund the rules do not allow. The words are for the player."""


def _rows(conn: Connection, sql: str, params=()) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def _one(conn: Connection, sql: str, params=()) -> dict | None:
    rows = _rows(conn, sql, params)
    return rows[0] if rows else None


def ready(conn: Connection) -> bool:
    return bool(_one(conn, "SELECT to_regclass('etfs') IS NOT NULL AS ok")["ok"])


def _money(kobo: int) -> str:
    return objectives._money(kobo)


def _roll(*parts) -> int:
    return int(hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()[:8], 16) % BPS


def _state(conn: Connection, now: datetime) -> dict:
    try:
        careers.books_open(conn, now)
    except careers.CareerError as closing:
        raise EtfError(str(closing)) from None
    return careers.world_now(conn, now)


def held_account(conn: Connection):
    row = _one(conn, "SELECT id FROM ledger_accounts WHERE code = %s", (HELD,))
    return row["id"] if row else ledger.create_account(conn, kind="escrow", name="The exchange: held for ETF orders", code=HELD)


def _etf(conn: Connection, etf_id, *, lock: bool = False) -> dict:
    row = _one(conn, "SELECT * FROM etfs WHERE id = %s" + (" FOR UPDATE" if lock else ""), (etf_id,))
    if row is None:
        raise EtfError("There is no such ETF.")
    return row


def by_code(conn: Connection, code: str) -> dict:
    row = _one(conn, "SELECT * FROM etfs WHERE code = %s", ((code or "").upper(),))
    if row is None:
        raise EtfError("There is no ETF with that code.")
    return row


def kind_of(etf: dict) -> str:
    if etf["commodity"]:
        return "commodity"
    if etf["leverage_bps"] == 20_000:
        return "leverage"
    if etf["leverage_bps"] < 0:
        return "inverse"
    return "index"


def special(etf: dict) -> bool:
    return kind_of(etf) in SPECIAL


def units_out(conn: Connection, etf: dict) -> int:
    return max(-ledger.balance(conn, etf["account_id"], etf["asset"]), 0)


# ---------------------------------------------------------------------------
# What an ETF is worth
# ---------------------------------------------------------------------------

def tracked_now(conn: Connection, etf: dict, now: datetime) -> Decimal | None:
    """The level of what it copies, now: an index's level, oil in naira a barrel, or the metals price index."""
    if etf["index_code"]:
        level = indexes.level_now(conn, etf["index_code"], now)
        return Decimal(level) if level else None
    row = _one(conn, "SELECT oil_cents, fx FROM abroad_results ORDER BY period DESC LIMIT 1") if etf["commodity"] == "OIL" else None
    if etf["commodity"] == "OIL":
        oil = row or {"oil_cents": data.OIL_START_CENTS, "fx": data.FX_START}
        return Decimal(oil["oil_cents"]) * Decimal(oil["fx"]) / 10_000
    row = _one(conn, "SELECT metals_bps FROM economy_results ORDER BY period DESC LIMIT 1")
    return Decimal(row["metals_bps"] if row else BPS)


def holdings_value(conn: Connection, account, now: datetime) -> dict:
    """Cash, and every share and bond an ETF holds at today's prices."""
    lines = _rows(conn, "SELECT asset, balance FROM ledger_balances WHERE account_id = %s AND balance > 0 AND asset <> 'NGN'"
                        " AND asset NOT LIKE 'ETF-%%'", (account,))
    prices = indexes.prices_now(conn, [r["asset"] for r in lines], now)
    out = [{"asset": r["asset"], "units": r["balance"], "price": prices.get(r["asset"], 0), "value": r["balance"] * prices.get(r["asset"], 0)}
           for r in lines]
    cash = ledger.balance(conn, account)
    return {"cash": cash, "lines": out, "total": cash + sum(x["value"] for x in out)}


def nav_now(conn: Connection, etf: dict, now: datetime) -> int:
    """What one unit is worth at this moment, in kobo (the "iNAV")."""
    n = units_out(conn, etf)
    if etf["method"] == "swap":
        level = tracked_now(conn, etf, now)
        if not level or not etf["tracked_level"]:
            return etf["nav"]
        move = (level / Decimal(etf["tracked_level"]) - 1) * etf["leverage_bps"] / BPS
        return max(int(Decimal(etf["nav"]) * (1 + move)), 1)
    if n <= 0:
        return etf["nav"]
    return max(holdings_value(conn, etf["account_id"], now)["total"] // n, 1)


def _target_basket(conn: Connection, etf_or_fund: dict, now: datetime) -> list[dict]:
    """What a fund copying an index should hold, as weights: every member (full copy) or the largest up to 80% (sampling)."""
    weights = indexes.weights_now(conn, etf_or_fund["index_code"], now)
    weights.sort(key=lambda w: -w["weight_bps"])
    if etf_or_fund["method"] == "sample":
        kept, cover = [], 0
        for w in weights:
            if cover >= data.ETF_SAMPLE_COVER_BPS and len(kept) >= 5:
                break
            kept.append(w)
            cover += w["weight_bps"]
        total = sum(w["weight_bps"] for w in kept) or 1
        weights = [{**w, "weight_bps": w["weight_bps"] * BPS // total} for w in kept]
    return [w for w in weights if w["price"] > 0]


# ---------------------------------------------------------------------------
# Dealing with the market's dealers (how a fund copies its index)
# ---------------------------------------------------------------------------

def _dealers(conn: Connection, asset: str) -> list:
    out = [ledger.account_id(conn, ledger.INVESTORS_INSTITUTIONS), ledger.account_id(conn, ledger.INVESTORS_PUBLIC)]
    if asset.startswith("BND-") and _one(conn, "SELECT 1 AS x FROM bonds WHERE asset = %s AND issuer = 'government'", (asset,)):
        out.append(ledger.account_id(conn, ledger.TREASURY))
    return out


def buy_from_dealers(conn: Connection, account, asset: str, units: int, price: int, period: int, memo: str) -> int:
    """Buy up to `units` at the price (plus the dealing cost) from whichever dealers have them. Returns the units bought."""
    each = -(-price * (BPS + DEALING_COST_BPS) // BPS)
    units = min(units, max(ledger.balance(conn, account), 0) // max(each, 1))
    got = 0
    treasury = ledger.account_id(conn, ledger.TREASURY)
    for seller in _dealers(conn, asset):
        if got >= units:
            break
        have = units - got if seller == treasury else min(units - got, ledger.balance(conn, seller, asset))
        if have <= 0:
            continue
        ledger.post(conn, kind="bond_issue" if seller == treasury else "etf_basket", memo=memo, period=period,
                    legs=[Leg(seller, -have, asset), Leg(account, have, asset), Leg(account, -have * each), Leg(seller, have * each)])
        got += have
    return got


def sell_to_dealers(conn: Connection, account, asset: str, units: int, price: int, period: int, memo: str) -> int:
    """Sell up to `units` at the price (less the dealing cost) to whichever dealers can pay. Returns the units sold."""
    each = max(price * (BPS - DEALING_COST_BPS) // BPS, 1)
    units = min(units, ledger.balance(conn, account, asset))
    done = 0
    for buyer in _dealers(conn, asset)[:2]:
        if done >= units:
            break
        n = min(units - done, max(ledger.balance(conn, buyer), 0) // each)
        if n <= 0:
            continue
        ledger.post(conn, kind="etf_basket", memo=memo, period=period,
                    legs=[Leg(account, -n, asset), Leg(buyer, n, asset), Leg(buyer, -n * each), Leg(account, n * each)])
        done += n
    return done


def track(conn: Connection, account, vehicle: dict, now: datetime, *, cash_target_bps: int = data.ETF_CASH_TARGET_BPS,
          period: int | None = None, force: bool = False) -> int:
    """Bring a fund's holdings into line with its index: sell what it should not hold (or holds too much of), then buy.
    Only holdings more than half a percent of the fund away from where they should be are dealt, unless forced (a change
    of members). Returns the number of deals."""
    period = period or careers.world_now(conn, now)["period"]
    h = holdings_value(conn, account, now)
    total = h["total"]
    if total <= 0:
        return 0
    invest = total - apply_bps(total, cash_target_bps)
    target = {w["asset"]: invest * w["weight_bps"] // BPS // w["price"] for w in _target_basket(conn, vehicle, now)}
    held = {x["asset"]: x for x in h["lines"]}
    deals = 0
    band = apply_bps(total, 50)
    name = vehicle.get("name", "A fund")
    for asset, x in held.items():
        want = target.get(asset, 0)
        if x["units"] > want and (force or (x["units"] - want) * x["price"] > band or want == 0):
            deals += 1 if sell_to_dealers(conn, account, asset, x["units"] - want, x["price"], period, f"{name}: copying its index") else 0
    prices = indexes.prices_now(conn, list(target), now)
    for asset, want in sorted(target.items(), key=lambda kv: -kv[1] * prices.get(kv[0], 0)):
        have = held.get(asset, {"units": 0})["units"]
        if want > have and (force or (want - have) * prices.get(asset, 0) > band or have == 0):
            deals += 1 if buy_from_dealers(conn, account, asset, want - have, prices[asset], period, f"{name}: copying its index") else 0
    return deals


def raise_cash(conn: Connection, account, vehicle: dict, need: int, now: datetime, period: int) -> int:
    """Sell a slice of everything (in proportion) to the dealers, to raise `need` in cash. Returns the cash raised."""
    h = holdings_value(conn, account, now)
    invested = h["total"] - h["cash"]
    if need <= 0 or invested <= 0:
        return 0
    before = ledger.balance(conn, account)
    share = min(Decimal(need) / Decimal(invested) * Decimal("1.002"), Decimal(1))
    for x in h["lines"]:
        n = min(int(Decimal(x["units"]) * share) + 1, x["units"])
        sell_to_dealers(conn, account, x["asset"], n, x["price"], period, f"{vehicle.get('name', 'A fund')}: paying investors who leave")
    return ledger.balance(conn, account) - before


# ---------------------------------------------------------------------------
# Setting up: the computer's ETFs and index funds
# ---------------------------------------------------------------------------

def _new_etf(conn: Connection, *, code: str, name: str, index_code: str | None, commodity: str | None, leverage: int, method: str,
             fee: int, manager_id, computer: bool, now: datetime, period: int, words: str = "") -> dict:
    account = ledger.create_account(conn, kind="fund", name=name)
    asset = f"ETF-{code}"
    ledger.create_asset(conn, code=asset, kind="etf", name=name, unit="unit", issuer_account_id=account)
    probe = {"index_code": index_code, "commodity": commodity}
    level = tracked_now(conn, probe, now)
    return _one(conn, "INSERT INTO etfs (code, name, name_key, asset, account_id, founder_id, manager_id, computer, index_code, commodity, leverage_bps,"
                      " method, fee_bps, nav, tracked_level, reference_price, launched_at, launched_period, words)"
                      " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING *",
                (code, name, _key(name), asset, account, manager_id, manager_id, computer, index_code, commodity, leverage, method, fee,
                 data.ETF_FIRST_NAV_KOBO, level, data.ETF_FIRST_NAV_KOBO, now, period, words))


def _key(name: str) -> str:
    return "".join(ch for ch in name.lower() if ch.isalnum())


def setup(conn: Connection, day: date, now: datetime) -> None:
    held_account(conn)
    indexes.setup(conn, day, now)
    if _one(conn, "SELECT 1 AS x FROM etfs WHERE computer LIMIT 1"):
        return
    from simulation import funds
    funds.setup(conn, now)
    period = careers.world_now(conn, now)["period"]
    households = ledger.account_id(conn, HOUSEHOLDS)
    for code, name, tracks, lev, method, fee, seed in data.COMPUTER_ETFS:
        commodity = tracks if tracks in ("OIL", "METALS") else None
        etf = _new_etf(conn, code=code, name=name, index_code=None if commodity else tracks, commodity=commodity, leverage=lev, method=method,
                       fee=fee, manager_id=None, computer=True, now=now, period=period,
                       words="Run by Broad Street Asset Management, the computer's own fund house.")
        units = naira(seed) // data.ETF_FIRST_NAV_KOBO // data.ETF_CREATION_UNITS * data.ETF_CREATION_UNITS
        _create_cash(conn, etf, households, units, now, period, fee_bps=0)
    for name, index_code, fee, seed in data.COMPUTER_INDEX_FUNDS:
        account = ledger.create_account(conn, kind="fund", name=name)
        fund = _one(conn, "INSERT INTO investment_funds (name, name_key, account_id, computer, strategy, index_code, method, fee_bps, high_water,"
                          " least_in, launched_at, launched_period, words) VALUES (%s, %s, %s, true, 'index', %s, 'full', %s, %s, %s, %s, %s, %s)"
                          " RETURNING *", (name, _key(name), account, index_code, fee, funds.FIRST_PRICE, naira(10_000), now, period,
                                           "Run by Broad Street Asset Management. It copies its index, nothing more."))
        paid = ledger.pay_up_to(conn, payer=households, receiver=account, wanted=naira(seed), kind="fund_units_bought",
                                memo=f"{name}: the households' first money", period=period)
        funds._issue(conn, fund, households, paid * funds.UNIT // funds.FIRST_PRICE, now)
        track(conn, account, fund, now, period=period, force=True)


# ---------------------------------------------------------------------------
# Making and unmaking units
# ---------------------------------------------------------------------------

def settle_swap(conn: Connection, etf: dict, now: datetime, period: int) -> dict:
    """A daily-reset ETF settles the move so far with the pension funds, and starts again from here: done at every bell, and
    before units are made or unmade during the day, so new units never collect a move that happened before they existed."""
    if etf["method"] != "swap":
        return etf
    n = units_out(conn, etf)
    level = tracked_now(conn, etf, now)
    if not level or not etf["tracked_level"]:
        return etf
    ratio = level / Decimal(etf["tracked_level"])
    pnl = int(Decimal(n) * Decimal(etf["nav"]) * (ratio - 1) * etf["leverage_bps"] / BPS)
    desk = ledger.account_id(conn, ledger.INVESTORS_INSTITUTIONS)
    if pnl > 0:
        ledger.pay_up_to(conn, payer=desk, receiver=etf["account_id"], wanted=pnl, kind="etf_swap", memo=f"{etf['name']}: the move so far", period=period)
    elif pnl < 0:
        ledger.pay_up_to(conn, payer=etf["account_id"], receiver=desk, wanted=-pnl, kind="etf_swap", memo=f"{etf['name']}: the move so far", period=period)
    nav = max(ledger.balance(conn, etf["account_id"]) // n, 1) if n > 0 else nav_now(conn, etf, now)
    conn.execute("UPDATE etfs SET nav = %s, tracked_level = %s WHERE id = %s", (nav, level, etf["id"]))
    return _etf(conn, etf["id"])


def _create_cash(conn: Connection, etf: dict, payer, units: int, now: datetime, period: int, *, fee_bps: int = data.ETF_CASH_FEE_BPS,
                 receiver=None) -> dict:
    """New units against cash: the payer pays their value and the fee; the fund buys its basket (or, for a daily-reset ETF,
    keeps the cash)."""
    etf = settle_swap(conn, etf, now, period)
    nav = nav_now(conn, etf, now)
    value = units * nav
    fee = apply_bps(value, fee_bps)
    receiver = receiver or payer
    try:
        ledger.transfer(conn, payer=payer, receiver=etf["account_id"], amount=value + fee, kind="etf_create_cash",
                        memo=f"{etf['name']}: {units:,} new units, paid in cash", period=period)
    except ledger.InsufficientFunds:
        raise EtfError(f"That needs {_money(value + fee)} in cash.") from None
    ledger.post(conn, kind="etf_create", memo=f"{etf['name']}: {units:,} new units", period=period,
                legs=[Leg(etf["account_id"], -units, etf["asset"]), Leg(receiver, units, etf["asset"])])
    if etf["method"] != "swap":
        _invest_cash(conn, etf, now, period)
    conn.execute("INSERT INTO etf_creations (etf_id, account_id, side, how, units, nav, fee, at) VALUES (%s, %s, 'create', 'cash', %s, %s, %s, %s)",
                 (etf["id"], receiver, units, nav, fee, now))
    return {"units": units, "nav": nav, "paid": value + fee, "fee": fee}


def _invest_cash(conn: Connection, etf: dict, now: datetime, period: int) -> None:
    """Spare cash goes into the basket, in proportion to the index."""
    h = holdings_value(conn, etf["account_id"], now)
    spare = h["cash"] - apply_bps(h["total"], data.ETF_CASH_TARGET_BPS)
    if spare <= apply_bps(h["total"], 25):
        return
    for w in _target_basket(conn, etf, now):
        n = spare * w["weight_bps"] // BPS // w["price"]
        if n > 0:
            buy_from_dealers(conn, etf["account_id"], w["asset"], n, w["price"], period, f"{etf['name']}: buying its basket")


def basket(conn: Connection, etf: dict, units: int, now: datetime) -> dict:
    """What `units` new units cost as a basket: the fund's own holdings for that many units, and the cash part."""
    n = units_out(conn, etf)
    nav = nav_now(conn, etf, now)
    h = holdings_value(conn, etf["account_id"], now)
    if n > 0:
        lines = [{"asset": x["asset"], "units": x["units"] * units // n, "price": x["price"]} for x in h["lines"]]
    else:
        lines = [{"asset": w["asset"], "units": units * nav * w["weight_bps"] // BPS // w["price"], "price": w["price"]}
                 for w in _target_basket(conn, etf, now)]
    lines = [x for x in lines if x["units"] > 0]
    cash = units * nav - sum(x["units"] * x["price"] for x in lines)
    tickers = {r["asset"]: r["ticker"] for r in _rows(conn, "SELECT share_asset AS asset, ticker FROM companies")}
    for x in lines:
        x["ticker"] = tickers.get(x["asset"], x["asset"][4:])
    return {"units": units, "nav": nav, "lines": lines, "cash": cash, "value": units * nav}


def dealer_account(conn: Connection, player_id) -> tuple:
    """The empire account an approved dealer acts for (only its head acts for it)."""
    seat = empires.seat_of(conn, player_id)
    if seat is None or seat["empire_kind"] == "pension" or seat["empire_status"] != "active":
        raise EtfError("Only an empire approved as a dealer can make or unmake ETF units.")
    if seat["head_player_id"] != player_id:
        raise EtfError("Only the empire's head makes or unmakes ETF units for it.")
    if not _one(conn, "SELECT 1 AS x FROM etf_dealers WHERE empire_id = %s AND status = 'approved'", (seat["empire_id"],)):
        raise EtfError("Your empire is not an approved dealer. Ask to be approved first.")
    return seat["account_id"], seat


def apply_dealer(conn: Connection, player_id, now: datetime) -> dict:
    """An empire worth ₦500 million or more, whose head has a clean record, is approved as a dealer."""
    with conn.transaction():
        _state(conn, now)
        seat = empires.seat_of(conn, player_id)
        if seat is None or seat["empire_kind"] == "pension" or seat["empire_status"] != "active" or seat["head_player_id"] != player_id:
            raise EtfError("Only the head of an empire can ask for it to be approved as a dealer.")
        if _one(conn, "SELECT 1 AS x FROM legal_records WHERE player_id = %s", (player_id,)):
            raise EtfError("A head with wrongdoing proved on their record cannot be approved.")
        worth = objectives.wealth(conn, seat["account_id"], now)["total"]
        if worth < naira(data.ETF_DEALER_LEAST_WORTH_NAIRA):
            raise EtfError(f"An approved dealer must be worth at least {_money(naira(data.ETF_DEALER_LEAST_WORTH_NAIRA))}: your empire is worth"
                           f" {_money(worth)}.")
        conn.execute("INSERT INTO etf_dealers (empire_id, approved_at) VALUES (%s, %s) ON CONFLICT (empire_id) DO UPDATE SET status = 'approved',"
                     " approved_at = EXCLUDED.approved_at", (seat["empire_id"], now))
        return {"empire": seat["empire_name"], "approved": True}


def create(conn: Connection, player_id, code: str, units: int, how: str, now: datetime) -> dict:
    """An approved dealer makes new units: against a basket of the shares the fund holds (0.05%), or cash (0.25%)."""
    with conn.transaction():
        state = _state(conn, now)
        account, _ = dealer_account(conn, player_id)
        etf = _etf(conn, by_code(conn, code)["id"], lock=True)
        _units_ok(units)
        if etf["status"] != "open":
            raise EtfError("That ETF is not making new units.")
        _gate(conn, player_id, etf, True)
        if how == "cash" or etf["method"] == "swap":
            return _create_cash(conn, etf, account, units, now, state["period"])
        if how != "basket":
            raise EtfError("Make units against a basket or cash.")
        b = basket(conn, etf, units, now)
        fee = apply_bps(b["value"], data.ETF_BASKET_FEE_BPS)
        short = [x["ticker"] for x in b["lines"] if ledger.balance(conn, account, x["asset"]) < x["units"]]
        if short:
            raise EtfError(f"The empire does not hold the basket: it is short of {', '.join(short[:5])}.")
        if ledger.balance(conn, account) < max(b["cash"], 0) + fee:
            raise EtfError(f"The basket's cash part and the fee come to {_money(max(b['cash'], 0) + fee)}.")
        legs = []
        for x in b["lines"]:
            legs += [Leg(account, -x["units"], x["asset"]), Leg(etf["account_id"], x["units"], x["asset"])]
        if b["cash"] + fee:
            legs += [Leg(account, -(b["cash"] + fee)), Leg(etf["account_id"], b["cash"] + fee)]
        ledger.post(conn, kind="etf_basket", memo=f"{etf['name']}: a basket for {units:,} new units", period=state["period"], legs=legs)
        ledger.post(conn, kind="etf_create", memo=f"{etf['name']}: {units:,} new units", period=state["period"],
                    legs=[Leg(etf["account_id"], -units, etf["asset"]), Leg(account, units, etf["asset"])])
        conn.execute("INSERT INTO etf_creations (etf_id, account_id, side, how, units, nav, fee, at) VALUES (%s, %s, 'create', 'basket', %s, %s, %s, %s)",
                     (etf["id"], account, units, b["nav"], fee, now))
        return {"units": units, "nav": b["nav"], "fee": fee}


def _units_ok(units) -> None:
    if not isinstance(units, int) or isinstance(units, bool) or units <= 0 or units % data.ETF_CREATION_UNITS:
        raise EtfError(f"Units are made and unmade in blocks of {data.ETF_CREATION_UNITS:,}.")


def redeem(conn: Connection, player_id, code: str, units: int, how: str, now: datetime) -> dict:
    """An approved dealer unmakes units: for its slice of everything the fund holds (0.05%), or for cash (0.25%)."""
    with conn.transaction():
        state = _state(conn, now)
        account, _ = dealer_account(conn, player_id)
        etf = _etf(conn, by_code(conn, code)["id"], lock=True)
        _units_ok(units)
        if ledger.balance(conn, account, etf["asset"]) < units:
            raise EtfError("The empire does not hold that many units.")
        return _redeem(conn, etf, account, units, "cash" if etf["method"] == "swap" else how, now, state["period"])


def _redeem(conn: Connection, etf: dict, account, units: int, how: str, now: datetime, period: int, *, fee_bps: int | None = None) -> dict:
    etf = settle_swap(conn, etf, now, period)
    n = units_out(conn, etf)
    nav = nav_now(conn, etf, now)
    fee_bps = (data.ETF_CASH_FEE_BPS if how == "cash" else data.ETF_BASKET_FEE_BPS) if fee_bps is None else fee_bps
    value = units * nav
    fee = apply_bps(value, fee_bps)
    ledger.post(conn, kind="etf_redeem", memo=f"{etf['name']}: {units:,} units unmade", period=period,
                legs=[Leg(account, -units, etf["asset"]), Leg(etf["account_id"], units, etf["asset"])])
    if how == "basket":
        h = holdings_value(conn, etf["account_id"], now)
        legs = []
        given = 0
        for x in h["lines"]:
            q = x["units"] * units // n if n else 0
            if q > 0:
                legs += [Leg(etf["account_id"], -q, x["asset"]), Leg(account, q, x["asset"])]
                given += q * x["price"]
        cash = max(min(value - given - fee, ledger.balance(conn, etf["account_id"])), 0)
        if cash:
            legs += [Leg(etf["account_id"], -cash), Leg(account, cash)]
        if legs:
            ledger.post(conn, kind="etf_basket", memo=f"{etf['name']}: a basket for {units:,} units unmade", period=period, legs=legs)
        paid = given + cash
    else:
        need = value - fee - ledger.balance(conn, etf["account_id"])
        if need > 0 and etf["method"] != "swap":
            raise_cash(conn, etf["account_id"], etf, need, now, period)
        paid = ledger.pay_up_to(conn, payer=etf["account_id"], receiver=account, wanted=value - fee, kind="etf_redeem_cash",
                                memo=f"{etf['name']}: {units:,} units unmade, paid in cash", period=period)
    conn.execute("INSERT INTO etf_creations (etf_id, account_id, side, how, units, nav, fee, at) VALUES (%s, %s, 'redeem', %s, %s, %s, %s, %s)",
                 (etf["id"], account, how, units, nav, fee, now))
    return {"units": units, "nav": nav, "paid": paid, "fee": fee}


# ---------------------------------------------------------------------------
# The order book: players' orders and the market makers' quotes, matched by the order-matching engine
# ---------------------------------------------------------------------------

def band(etf: dict) -> tuple[int, int]:
    move = etf["reference_price"] * data.ETF_PRICE_BAND_BPS * (2 if special(etf) and not etf["commodity"] else 1) // BPS
    return max(etf["reference_price"] - move, 1), etf["reference_price"] + move


def _maker_depth(conn: Connection, etf: dict) -> int:
    return max(units_out(conn, etf) * data.ETF_MAKER_DEPTH_BPS // BPS, data.ETF_MAKER_LEAST_DEPTH)


def maker_quote(conn: Connection, etf: dict, now: datetime) -> dict:
    nav = nav_now(conn, etf, now)
    centre = nav * (BPS + etf["premium_bps"]) // BPS
    half = data.ETF_MAKER_SPECIAL_HALF_SPREAD_BPS if special(etf) else data.ETF_MAKER_HALF_SPREAD_BPS
    low, high = band(etf)
    bid = min(max(centre * (BPS - half) // BPS, low), high)
    ask = max(min(-(-centre * (BPS + half) // BPS), high), low)
    return {"nav": nav, "bid": bid, "ask": max(ask, bid + 1), "depth": _maker_depth(conn, etf)}


def _refresh_maker(conn: Connection, etf: dict, now: datetime) -> dict:
    """The market makers withdraw their quotes and put up fresh ones around the fund's value now."""
    conn.execute("UPDATE etf_orders SET status = 'cancelled' WHERE etf_id = %s AND maker AND status = 'open'", (etf["id"],))
    q = maker_quote(conn, etf, now)
    maker = ledger.account_id(conn, ledger.INVESTORS_INSTITUTIONS)
    day = exchange.session_of(now)[0]
    buyable = min(q["depth"], max(ledger.balance(conn, maker), 0) // max(q["bid"], 1))
    if buyable > 0:
        conn.execute("INSERT INTO etf_orders (etf_id, account_id, maker, side, limit_price, quantity, remaining, session_date, placed_at)"
                     " VALUES (%s, %s, true, 'buy', %s, %s, %s, %s, %s)", (etf["id"], maker, q["bid"], buyable, buyable, day, now))
    if etf["status"] == "open":
        conn.execute("INSERT INTO etf_orders (etf_id, account_id, maker, side, limit_price, quantity, remaining, session_date, placed_at)"
                     " VALUES (%s, %s, true, 'sell', %s, %s, %s, %s, %s)", (etf["id"], maker, q["ask"], q["depth"], q["depth"], day, now))
    return q


def _gate(conn: Connection, player_id, etf: dict, for_empire: bool) -> None:
    """2x and inverse ETFs: a player of Level 15 in any build (for an empire, its head), who has read the warning."""
    if kind_of(etf) not in ("leverage", "inverse"):
        return
    level = max((careers.career(conn, player_id, b["build"])["level"] for b in _rows(conn, "SELECT build FROM careers WHERE player_id = %s",
                                                                                      (player_id,))), default=0)
    if level < data.ETF_SPECIAL_LEVEL:
        raise EtfError(f"2x and inverse ETFs are for players of Level {data.ETF_SPECIAL_LEVEL} or above in any build. They can lose money fast.")
    if not _one(conn, "SELECT 1 AS x FROM etf_warnings WHERE player_id = %s", (player_id,)):
        raise EtfError("Read the warning about 2x and inverse ETFs first.")


def accept_warning(conn: Connection, player_id, now: datetime) -> None:
    conn.execute("INSERT INTO etf_warnings (player_id, at) VALUES (%s, %s) ON CONFLICT DO NOTHING", (player_id, now))


def _who(conn: Connection, player_id, for_empire: bool, value: int = 0) -> tuple:
    if not for_empire:
        return ledger.player_account_id(conn, player_id), "you"
    seat = empires.seat_of(conn, player_id)
    if seat is None or seat["empire_kind"] == "pension" or seat["empire_status"] != "active":
        raise EtfError("You are not in an empire.")
    if seat["head_player_id"] != player_id:
        raise EtfError("Only the head deals in ETFs for the empire.")
    return seat["account_id"], "the empire"


def place_order(conn: Connection, player_id, code: str, *, side: str, quantity: int, limit_price: int, now: datetime,
                for_empire: bool = False) -> dict:
    """Buy or sell ETF units at a price you name. Matched at once against the waiting orders and the makers' quotes; what is
    left waits until the closing bell."""
    with conn.transaction():
        state = _state(conn, now)
        etf = _etf(conn, by_code(conn, code)["id"], lock=True)
        day, market = exchange.session_of(now)
        if market is not clock.MarketState.OPEN:
            raise EtfError("ETFs trade while the market is open, from 12:00 to 22:00 Lagos time.")
        if etf["status"] != "open":
            raise EtfError("That ETF is closing and no longer trades.")
        if side not in ("buy", "sell") or not isinstance(quantity, int) or isinstance(quantity, bool) or quantity <= 0:
            raise EtfError("Buy or sell a whole number of units above nothing.")
        if not isinstance(limit_price, int) or isinstance(limit_price, bool) or limit_price <= 0:
            raise EtfError("Name a price.")
        low, high = band(etf)
        if not low <= limit_price <= high:
            raise EtfError(f"Today {etf['code']} trades between {_money(low)} and {_money(high)}.")
        account, whose = _who(conn, player_id, for_empire)
        if side == "buy":
            _gate(conn, player_id, etf, for_empire)
        if _one(conn, "SELECT count(*) AS n FROM etf_orders WHERE account_id = %s AND status = 'open'", (account,))["n"] >= 20:
            raise EtfError("You already have 20 ETF orders waiting. Cancel one first.")
        held = held_account(conn)
        if side == "buy":
            reserve = quantity * limit_price
            reserve += -(-reserve * data.ETF_TRADE_FEE_BPS // BPS)
            try:
                ledger.transfer(conn, payer=account, receiver=held, amount=reserve, kind="etf_order_hold",
                                memo=f"{etf['code']}: cash held for a buy order", period=state["period"])
            except ledger.InsufficientFunds:
                raise EtfError(f"{'You do' if whose == 'you' else 'The empire does'} not have {_money(reserve)} in cash.") from None
        else:
            reserve = quantity
            if ledger.balance(conn, account, etf["asset"]) < quantity:
                raise EtfError(f"{'You hold' if whose == 'you' else 'The empire holds'} only {ledger.balance(conn, account, etf['asset']):,} units.")
            ledger.transfer(conn, payer=account, receiver=held, amount=quantity, asset=etf["asset"], kind="etf_order_hold",
                            memo=f"{etf['code']}: units held for a sell order", period=state["period"])
        order = _one(conn, "INSERT INTO etf_orders (etf_id, account_id, player_id, side, limit_price, quantity, remaining, reserved, session_date,"
                           " placed_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING *",
                     (etf["id"], account, player_id, side, limit_price, quantity, quantity, reserve, day, now))
        _refresh_maker(conn, etf, now)
        trades = _match(conn, etf, order, now, state["period"])
        order = _one(conn, "SELECT * FROM etf_orders WHERE id = %s", (order["id"],))
        return {"order": order, "trades": trades}


def _match(conn: Connection, etf: dict, order: dict, now: datetime, period: int) -> list[dict]:
    # Never against an order from the same account, or placed by the same player (a head's own account and their empire's).
    opposite = _rows(conn, "SELECT id, limit_price, remaining, maker, account_id, player_id, reserved, filled_value, fee_paid, side FROM etf_orders"
                           " WHERE etf_id = %s AND side = %s AND status = 'open' AND account_id <> %s AND (player_id IS NULL OR player_id <> %s)"
                           " AND remaining > 0 ORDER BY id FOR UPDATE", (etf["id"], "sell" if order["side"] == "buy" else "buy",
                                                                        order["account_id"], order["player_id"]))
    if not opposite:
        return []
    low, high = band(etf)
    fills, _ = exchange.engine.match(order["side"], order["limit_price"], order["remaining"], opposite, low, high)
    by_id = {o["id"]: o for o in opposite}
    out = []
    maker = ledger.account_id(conn, ledger.INVESTORS_INSTITUTIONS)
    for f in fills:
        other = _one(conn, "SELECT * FROM etf_orders WHERE id = %s", (by_id[f["order_id"]]["id"],))
        mine = _one(conn, "SELECT * FROM etf_orders WHERE id = %s", (order["id"],))
        if other["status"] != "open" or mine["status"] != "open":
            continue
        buy, sell = (mine, other) if order["side"] == "buy" else (other, mine)
        done = _settle(conn, etf, buy, sell, f["price"], min(f["quantity"], other["remaining"], mine["remaining"]), now, period, maker)
        if not done:
            continue
        out.append({"price": f["price"], "quantity": done})
        if other["maker"]:
            sign = 1 if order["side"] == "buy" else -1
            half = data.ETF_MAKER_SPECIAL_HALF_SPREAD_BPS if special(etf) else data.ETF_MAKER_HALF_SPREAD_BPS
            impact = half * done // max(_maker_depth(conn, etf), 1)
            most = data.ETF_SPECIAL_PREMIUM_MOST_BPS if special(etf) else data.ETF_PREMIUM_MOST_BPS
            if impact:
                conn.execute("UPDATE etfs SET premium_bps = greatest(least(premium_bps + %s, %s), %s) WHERE id = %s",
                             (sign * impact, most, -most, etf["id"]))
    if out:
        conn.execute("UPDATE etfs SET last_price = %s, session_date = %s WHERE id = %s", (out[-1]["price"], exchange.session_of(now)[0], etf["id"]))
    return out


def _fee_now(order: dict, value: int) -> int:
    """The fee on this fill: the fee on everything the order has dealt so far, less what it has paid (so rounding never adds up
    to more than was held for it)."""
    if order.get("maker"):
        return 0
    total = -(-(order["filled_value"] + value) * data.ETF_TRADE_FEE_BPS // BPS)
    return max(total - order["fee_paid"], 0)


def _settle(conn: Connection, etf: dict, buy: dict, sell: dict, price: int, qty: int, now: datetime, period: int, maker) -> int:
    if qty <= 0:
        return 0
    held = held_account(conn)
    fees = ledger.account_id(conn, exchange.FEES)
    value = price * qty
    # The market makers sell units they hold, or make them on the spot from their own shares (or cash).
    if sell["maker"]:
        have = ledger.balance(conn, maker, etf["asset"])
        if have < qty:
            blocks = -(-(qty - have) // data.ETF_CREATION_UNITS) * data.ETF_CREATION_UNITS
            try:
                _maker_create(conn, etf, maker, blocks, now, period)
            except (EtfError, ledger.LedgerError):
                return 0
            etf.update(_etf(conn, etf["id"]))
        seller_from = maker
    else:
        seller_from = held
    buyer_fee, seller_fee = _fee_now(buy, value), _fee_now(sell, value)
    if buy["maker"]:
        if ledger.balance(conn, maker) < value:
            return 0
        buyer_from = maker
    else:
        buyer_from = held
        if value + buyer_fee > buy["reserved"]:
            return 0                                            # never more than was held for it
    if seller_fee >= value:
        return 0
    legs = [Leg(seller_from, -qty, etf["asset"]), Leg(buy["account_id"], qty, etf["asset"]),
            Leg(buyer_from, -(value + buyer_fee)), Leg(sell["account_id"], value - seller_fee)]
    if buyer_fee + seller_fee:
        legs.append(Leg(fees, buyer_fee + seller_fee))
    ledger.post(conn, kind="etf_trade", memo=f"{qty:,} {etf['code']} at {_money(price)}", period=period, legs=legs)
    for o, used, fee in ((buy, value + buyer_fee, buyer_fee), (sell, qty, seller_fee)):
        conn.execute("UPDATE etf_orders SET remaining = remaining - %s, reserved = CASE WHEN maker THEN 0 ELSE reserved - %s END,"
                     " filled_value = filled_value + %s, fee_paid = fee_paid + %s WHERE id = %s AND status = 'open'",
                     (qty, used, value, fee, o["id"]))
        after = _one(conn, "SELECT * FROM etf_orders WHERE id = %s", (o["id"],))
        if after["remaining"] == 0:
            _release(conn, etf, after, period, "filled")       # what is left of what was held goes straight back
    conn.execute("INSERT INTO etf_trades (etf_id, buyer, seller, price, quantity, session_date, traded_at) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                 (etf["id"], buy["account_id"], sell["account_id"], price, qty, exchange.session_of(now)[0], now))
    return qty


def _maker_create(conn: Connection, etf: dict, maker, units: int, now: datetime, period: int) -> None:
    """The pension funds make units for themselves: against the shares they hold where they can, the rest in cash."""
    if etf["method"] == "swap":
        _create_cash(conn, etf, maker, units, now, period, fee_bps=0)
        return
    b = basket(conn, etf, units, now)
    # (Against cash, the pension funds pay the fund's dealing cost, so the holders never do.)
    if all(ledger.balance(conn, maker, x["asset"]) >= x["units"] for x in b["lines"]) and ledger.balance(conn, maker) >= max(b["cash"], 0):
        legs = []
        for x in b["lines"]:
            legs += [Leg(maker, -x["units"], x["asset"]), Leg(etf["account_id"], x["units"], x["asset"])]
        if b["cash"] > 0:
            legs += [Leg(maker, -b["cash"]), Leg(etf["account_id"], b["cash"])]
        if legs:
            ledger.post(conn, kind="etf_basket", memo=f"{etf['name']}: the market makers' basket", period=period, legs=legs)
        ledger.post(conn, kind="etf_create", memo=f"{etf['name']}: {units:,} new units", period=period,
                    legs=[Leg(etf["account_id"], -units, etf["asset"]), Leg(maker, units, etf["asset"])])
        conn.execute("INSERT INTO etf_creations (etf_id, account_id, side, how, units, nav, fee, at) VALUES (%s, %s, 'create', 'basket', %s, %s, 0, %s)",
                     (etf["id"], maker, units, b["nav"], now))
    else:
        _create_cash(conn, etf, maker, units, now, period, fee_bps=DEALING_COST_BPS)


def _release(conn: Connection, etf: dict, order: dict, period: int, status: str) -> None:
    """Hand back what is still held for an order that is done (filled, cancelled or expired)."""
    if order["maker"]:
        conn.execute("UPDATE etf_orders SET status = %s WHERE id = %s", (status, order["id"]))
        return
    left = order["reserved"]
    if left > 0:
        held = held_account(conn)
        ledger.transfer(conn, payer=held, receiver=order["account_id"], amount=left, asset=ledger.NGN if order["side"] == "buy" else etf["asset"],
                        kind="etf_order_release", memo=f"{etf['code']}: held for an order, handed back", period=period)
    conn.execute("UPDATE etf_orders SET status = %s, reserved = 0 WHERE id = %s", (status, order["id"]))


def cancel_order(conn: Connection, player_id, order_id: int, now: datetime) -> None:
    with conn.transaction():
        state = _state(conn, now)
        found = _one(conn, "SELECT etf_id FROM etf_orders WHERE id = %s AND player_id = %s", (order_id, player_id))
        if found is None:
            raise EtfError("There is no waiting order of yours with that number.")
        _etf(conn, found["etf_id"], lock=True)                  # the same lock a match takes: one waits for the other
        order = _one(conn, "SELECT * FROM etf_orders WHERE id = %s AND player_id = %s AND status = 'open' FOR UPDATE", (order_id, player_id))
        if order is None:
            raise EtfError("There is no waiting order of yours with that number.")
        _release(conn, _etf(conn, order["etf_id"]), order, state["period"], "cancelled")


# ---------------------------------------------------------------------------
# The closing bell
# ---------------------------------------------------------------------------

def tick(conn: Connection, now: datetime) -> int:
    """After each closing bell: the indexes' levels, every ETF's value and fee, the daily reset of the special ETFs, changes
    of index members, and the orders the index funds place ahead of a change. Returns the bells dealt."""
    if not ready(conn) or not _one(conn, "SELECT 1 AS x FROM world_state"):
        return 0
    progress = _one(conn, "SELECT dealt_through FROM etf_progress")["dealt_through"]
    bells = _rows(conn, "SELECT session_date, rung_at FROM closing_bells WHERE (%s::date IS NULL OR session_date > %s) AND rung_at <= %s"
                        " ORDER BY session_date", (progress, progress, now))
    for bell in bells:
        day, at = bell["session_date"], bell["rung_at"]
        try:
            with conn.transaction():
                started = _one(conn, "SELECT 1 AS x FROM market_indexes LIMIT 1") is None
                if started:
                    setup(conn, day, at)
                changed = [] if started else indexes.at_bell(conn, day, at)
                for e in _rows(conn, "SELECT id FROM etfs WHERE status IN ('open', 'closing') ORDER BY id"):
                    try:
                        with conn.transaction():
                            _at_bell(conn, _etf(conn, e["id"], lock=True), day, at, changed)
                    except Exception:
                        log.exception("An ETF could not be dealt at the bell; the others carry on")
                _place_change_orders(conn, day, at)
                conn.execute("UPDATE etf_progress SET dealt_through = %s", (day,))
        except Exception:
            log.exception("The ETFs could not be dealt at the bell")
            break
    return len(bells)


def _at_bell(conn: Connection, etf: dict, day: date, now: datetime, changed: list[str]) -> None:
    period = careers.world_now(conn, now)["period"]
    for o in _rows(conn, "SELECT * FROM etf_orders WHERE etf_id = %s AND status = 'open' FOR UPDATE", (etf["id"],)):
        _release(conn, etf, o, period, "expired")
    if etf["status"] == "closing":
        _wind_up(conn, etf, day, now, period)
        return
    n = units_out(conn, etf)
    # What it tracks moved this much since the last bell (times its leverage), for the record of how closely it copies.
    tracked = tracked_now(conn, etf, now)
    last_level = _one(conn, "SELECT level FROM index_levels WHERE index_code = %s AND session_date < %s ORDER BY session_date DESC LIMIT 1",
                      (etf["index_code"], day)) if etf["index_code"] else None
    move_bps = None
    if tracked and last_level:
        move_bps = int((tracked / Decimal(last_level["level"]) - 1) * etf["leverage_bps"])
    elif tracked and etf["tracked_level"] and etf["method"] == "swap":
        move_bps = int((tracked / Decimal(etf["tracked_level"]) - 1) * etf["leverage_bps"])
    if etf["method"] == "swap":
        # The daily reset: 2x, inverse and commodity ETFs settle the day's move with the pension funds.
        etf = settle_swap(conn, etf, now, period)
    elif n > 0:
        track(conn, etf["account_id"], etf, now, period=period, force=etf["index_code"] in changed)
    # The day's fee.
    value = holdings_value(conn, etf["account_id"], now)["total"] if n > 0 else 0
    fee = value * etf["fee_bps"] // BPS // data.INVEST_FUND_SESSIONS_PER_YEAR
    if fee > 0:
        if ledger.balance(conn, etf["account_id"]) < fee and etf["method"] != "swap":
            raise_cash(conn, etf["account_id"], etf, fee, now, period)
        payee = ledger.player_account_id(conn, etf["manager_id"]) if etf["manager_id"] else ledger.account_id(conn, ledger.INVESTORS_INSTITUTIONS)
        ledger.pay_up_to(conn, payer=etf["account_id"], receiver=payee, wanted=fee, kind="etf_manager_fee" if etf["manager_id"] else "etf_fee",
                         memo=f"{etf['name']}: the day's fee", period=period)
    nav = max(holdings_value(conn, etf["account_id"], now)["total"] // n, 1) if n > 0 else etf["nav"]
    traded = _one(conn, "SELECT coalesce(sum(quantity), 0)::bigint AS v, (array_agg(price ORDER BY id DESC))[1] AS last FROM etf_trades"
                        " WHERE etf_id = %s AND session_date = %s", (etf["id"], day))
    close = traded["last"] or nav * (BPS + etf["premium_bps"]) // BPS
    flows = _one(conn, "SELECT coalesce(sum(units) FILTER (WHERE side = 'create'), 0)::bigint AS c, coalesce(sum(units) FILTER (WHERE side = 'redeem'), 0)::bigint AS r"
                       " FROM etf_creations WHERE etf_id = %s AND at > %s AND at <= %s", (etf["id"], now - timedelta(days=1), now))
    conn.execute("INSERT INTO etf_days (etf_id, session_date, nav, close, units, volume, created, redeemed, tracked_bps) VALUES"
                 " (%s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
                 (etf["id"], day, nav, close, n, traded["v"], flows["c"], flows["r"], move_bps))
    # Where the makers quote tomorrow: half of today's gap closes, and a new day's mood moves it a little.
    shock = (_roll("etf-mood", etf["id"], day) - BPS // 2) * 2 * data.ETF_PREMIUM_SHOCK_BPS // BPS
    most = data.ETF_SPECIAL_PREMIUM_MOST_BPS if special(etf) else data.ETF_PREMIUM_MOST_BPS
    premium = max(min(etf["premium_bps"] * (BPS - data.ETF_PREMIUM_DECAY_BPS) // BPS + shock, most), -most)
    conn.execute("UPDATE etfs SET nav = %s, nav_day = %s, tracked_level = %s, reference_price = %s, premium_bps = %s WHERE id = %s",
                 (nav, day, tracked or _etf(conn, etf["id"])["tracked_level"], close, premium, etf["id"]))
    off = (close - nav) * BPS // nav if nav else 0
    if abs(off) >= data.ETF_OFF_VALUE_ALERT_BPS and traded["v"]:
        _alert(conn, kind="off_value", etf=etf, headline=f"{etf['code']} closed {abs(off) / 100:.1f}% {'above' if off > 0 else 'below'} its value",
               words=f"{etf['name']} closed at {_money(close)}; its units were worth {_money(nav)}. An approved dealer can "
                     f"{'make units and sell them' if off > 0 else 'buy units and unmake them'} to close the gap.", now=now)
        _news(conn, "etf_off_value", now, {"etf": etf["name"], "code": etf["code"], "gap": f"{abs(off) / 100:.1f}%",
                                          "side": "above" if off > 0 else "below"})
    # The pension funds keep a working stock of units; anything more they unmake.
    maker = ledger.account_id(conn, ledger.INVESTORS_INSTITUTIONS)
    extra = ledger.balance(conn, maker, etf["asset"]) - 2 * _maker_depth(conn, etf)
    extra = extra // data.ETF_CREATION_UNITS * data.ETF_CREATION_UNITS
    if extra > 0 and units_out(conn, etf) > extra:
        _redeem(conn, _etf(conn, etf["id"]), maker, extra, "cash" if etf["method"] == "swap" else "basket", now, period, fee_bps=0)


def _wind_up(conn: Connection, etf: dict, day: date, now: datetime, period: int) -> None:
    """A closing ETF: everything is sold to the dealers and every holder is paid the value of their units in cash."""
    for x in holdings_value(conn, etf["account_id"], now)["lines"]:
        sell_to_dealers(conn, etf["account_id"], x["asset"], x["units"], x["price"], period, f"{etf['name']}: sold as it closes")
    if holdings_value(conn, etf["account_id"], now)["lines"]:
        return                                            # the dealers could not take it all today: again at the next bell
    n = units_out(conn, etf)
    cash = max(ledger.balance(conn, etf["account_id"]), 0)
    holders = _rows(conn, "SELECT account_id, balance FROM ledger_balances WHERE asset = %s AND balance > 0 ORDER BY account_id", (etf["asset"],))
    paid = 0
    for i, h in enumerate(holders):
        share = cash - paid if i == len(holders) - 1 else cash * h["balance"] // n if n else 0
        ledger.post(conn, kind="etf_redeem", memo=f"{etf['name']}: units taken back as it closes", period=period,
                    legs=[Leg(h["account_id"], -h["balance"], etf["asset"]), Leg(etf["account_id"], h["balance"], etf["asset"])])
        if share > 0:
            ledger.transfer(conn, payer=etf["account_id"], receiver=h["account_id"], amount=share, kind="etf_redeem_cash",
                            memo=f"{etf['name']}: paid out as it closes", period=period)
            paid += share
    conn.execute("UPDATE etfs SET status = 'closed', closed_at = %s WHERE id = %s", (now, etf["id"]))
    conn.execute("INSERT INTO etf_days (etf_id, session_date, nav, close, units) VALUES (%s, %s, %s, %s, 0) ON CONFLICT DO NOTHING",
                 (etf["id"], day, cash // n if n else etf["nav"], cash // n if n else etf["nav"]))
    _alert(conn, kind="closed", etf=etf, headline=f"{etf['name']} has closed", words=f"{_money(paid)} was paid out to its {len(holders)} holders.",
           now=now)


def _passive_vehicles(conn: Connection, index_code: str) -> list[dict]:
    """Every ETF and index fund copying an index (full copy or sampling), with what it is worth."""
    out = []
    for e in _rows(conn, "SELECT * FROM etfs WHERE index_code = %s AND status = 'open' AND method <> 'swap'", (index_code,)):
        out.append({"kind": "etf", "row": e, "account": e["account_id"]})
    for f in _rows(conn, "SELECT * FROM investment_funds WHERE strategy = 'index' AND index_code = %s AND status = 'open'", (index_code,)):
        out.append({"kind": "fund", "row": f, "account": f["account_id"]})
    return out


def _place_change_orders(conn: Connection, day: date, now: datetime) -> None:
    """The bell before an index change: the dealers place orders on the exchange for what the index funds will need,
    newcomers to buy and leavers to sell, to be dealt in the next session (half of it; the rest is dealt with the funds at
    the change's own bell). Everybody can see the change coming; the prices move."""
    for ch in _rows(conn, "SELECT * FROM index_changes WHERE status = 'announced' AND NOT orders_placed AND effective_day <= %s FOR UPDATE",
                    (day + timedelta(days=1),)):
        if ch["effective_day"] <= day:
            conn.execute("UPDATE index_changes SET orders_placed = true WHERE id = %s", (ch["id"],))
            continue                                           # (a bell was missed: the change is made with the funds directly)
        conn.execute("UPDATE index_changes SET orders_placed = true WHERE id = %s", (ch["id"],))
        vehicles = _passive_vehicles(conn, ch["index_code"])
        total = sum(holdings_value(conn, v["account"], now)["total"] for v in vehicles)
        if total <= 0:
            continue
        desk = ledger.account_id(conn, ledger.INVESTORS_INSTITUTIONS)
        new = {m["ticker"]: m for m in ch["plan"]}
        for add in ch["adds"]:
            m = new.get(add["ticker"])
            if not m or not m["asset"].startswith("SHR-"):
                continue
            ref = _one(conn, "SELECT m.reference_price FROM market_instruments m JOIN companies c ON c.id = m.company_id WHERE c.ticker = %s",
                       (add["ticker"],))["reference_price"]
            qty = total * m["weight_bps"] // BPS // max(ref, 1) // 2
            low, high = exchange.price_limits(ref)
            try:
                with conn.transaction():
                    exchange.place_order(conn, account=desk, ticker=add["ticker"], side="buy", kind="limit", quantity=max(qty, 1),
                                         limit_price=min(ref * 105 // 100, high), now=now)
            except (exchange.ExchangeError, ledger.LedgerError):
                pass
        for drop in ch["drops"]:
            asset = _one(conn, "SELECT share_asset AS a, id FROM companies WHERE ticker = %s", (drop["ticker"],))
            if not asset:
                continue
            held = sum(ledger.balance(conn, v["account"], asset["a"]) for v in vehicles)
            qty = min(held // 2, ledger.balance(conn, desk, asset["a"]))
            ref = _one(conn, "SELECT reference_price FROM market_instruments WHERE company_id = %s", (asset["id"],))["reference_price"]
            low, _ = exchange.price_limits(ref)
            if qty > 0:
                try:
                    with conn.transaction():
                        exchange.place_order(conn, account=desk, ticker=drop["ticker"], side="sell", kind="limit", quantity=qty,
                                             limit_price=max(ref * 95 // 100, low), now=now)
                except (exchange.ExchangeError, ledger.LedgerError):
                    pass


# ---------------------------------------------------------------------------
# The quarter's close: the review, passive money, tracking records, small ETFs
# ---------------------------------------------------------------------------

def after_close(conn: Connection, period: int, now: datetime) -> None:
    if not ready(conn) or not _one(conn, "SELECT 1 AS x FROM market_indexes LIMIT 1"):
        return
    with conn.transaction():
        for ch in indexes.review(conn, period, now):
            if not ch["adds"] and not ch["drops"]:
                continue
            idx = ch["index"]
            words = "; ".join(filter(None, [("in: " + ", ".join(a["name"] for a in ch["adds"])) if ch["adds"] else "",
                                            ("out: " + ", ".join(d["name"] for d in ch["drops"])) if ch["drops"] else ""]))
            _alert(conn, kind="index_change", index_code=idx["code"], headline=f"{idx['name']}: changes announced",
                   words=f"From the closing bell on {ch['effective_day']:%d %b}, {words}. The funds that copy it will buy and sell on that day.",
                   now=now, everyone=idx["code"] in ("TOP30", "BANKS"))
            _news(conn, "index_change", now, {"index": idx["name"], "adds": ", ".join(a["name"] for a in ch["adds"]) or "nobody",
                                              "drops": ", ".join(d["name"] for d in ch["drops"]) or "nobody"})
    with conn.transaction():
        _tracking(conn, period, now)
    with conn.transaction():
        _passive_money(conn, period, now)
    with conn.transaction():
        for e in _rows(conn, "SELECT * FROM etfs WHERE status = 'open' AND NOT computer AND launched_period <= %s FOR UPDATE", (period - 2,)):
            worth = units_out(conn, e) * e["nav"]
            small = worth < naira(data.ETF_SMALL_NAIRA)
            conn.execute("UPDATE etfs SET small_quarters = %s WHERE id = %s", (e["small_quarters"] + 1 if small else 0, e["id"]))
            if small and e["small_quarters"] + 1 >= data.INVEST_FUND_SMALL_QUARTERS:
                _start_closing(conn, e, f"It has stayed under {_money(naira(data.ETF_SMALL_NAIRA))} for two quarters.", now)


def _quarter_days(conn: Connection, period: int) -> tuple[date, date]:
    w = _one(conn, "SELECT world_start, weeks_ahead FROM world_state")
    start = clock.effective_start(w["world_start"], w["weeks_ahead"]) + timedelta(days=clock.REAL_DAYS_PER_QUARTER) * (period - 1)
    first = clock.to_lagos(start).date()
    return first, first + timedelta(days=clock.REAL_DAYS_PER_QUARTER)


def tracking_figures(pairs: list[tuple[float, float]]) -> dict:
    """From (vehicle's daily return, tracked daily return) pairs: each's total, the gap, and the yearly swing of the daily gaps."""
    if not pairs:
        return {"return_bps": None, "tracked_bps": None, "difference_bps": None, "error_bps": None}
    mine = math.prod(1 + a for a, _ in pairs) - 1
    theirs = math.prod(1 + b for _, b in pairs) - 1
    gaps = [a - b for a, b in pairs]
    mean = sum(gaps) / len(gaps)
    err = math.sqrt(sum((g - mean) ** 2 for g in gaps) / max(len(gaps) - 1, 1)) * math.sqrt(data.INVEST_FUND_SESSIONS_PER_YEAR) if len(gaps) > 1 else 0.0
    return {"return_bps": round(mine * BPS), "tracked_bps": round(theirs * BPS), "difference_bps": round((mine - theirs) * BPS),
            "error_bps": round(err * BPS)}


def _etf_pairs(conn: Connection, etf_id, since: date | None = None, until: date | None = None) -> list[tuple[float, float]]:
    days = _rows(conn, "SELECT session_date, nav, tracked_bps FROM etf_days WHERE etf_id = %s AND (%s::date IS NULL OR session_date > %s)"
                       " AND (%s::date IS NULL OR session_date <= %s) AND units > 0 ORDER BY session_date", (etf_id, since, since, until, until))
    return [(days[i]["nav"] / days[i - 1]["nav"] - 1, (days[i]["tracked_bps"] or 0) / BPS) for i in range(1, len(days))
            if days[i - 1]["nav"] and days[i]["tracked_bps"] is not None]


def _fund_pairs(conn: Connection, fund_id, since: date | None = None, until: date | None = None) -> list[tuple[float, float]]:
    days = _rows(conn, "SELECT session_date, unit_price, benchmark FROM fund_days WHERE fund_id = %s AND (%s::date IS NULL OR session_date > %s)"
                       " AND (%s::date IS NULL OR session_date <= %s) AND benchmark IS NOT NULL ORDER BY session_date", (fund_id, since, since, until, until))
    return [(days[i]["unit_price"] / days[i - 1]["unit_price"] - 1, days[i]["benchmark"] / days[i - 1]["benchmark"] - 1)
            for i in range(1, len(days)) if days[i - 1]["unit_price"] and days[i - 1]["benchmark"]]


def _tracking(conn: Connection, period: int, now: datetime) -> None:
    first, last = _quarter_days(conn, period)
    for e in _rows(conn, "SELECT id FROM etfs WHERE launched_period <= %s", (period,)):
        f = tracking_figures(_etf_pairs(conn, e["id"], first - timedelta(days=1), last))
        conn.execute("INSERT INTO tracking_quarters (vehicle, vehicle_id, period, return_bps, tracked_bps, difference_bps, error_bps)"
                     " VALUES ('etf', %s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING", (e["id"], period, *f.values()))
    for fnd in _rows(conn, "SELECT id FROM investment_funds WHERE strategy = 'index' AND launched_period <= %s", (period,)):
        f = tracking_figures(_fund_pairs(conn, fnd["id"], first - timedelta(days=1), last))
        conn.execute("INSERT INTO tracking_quarters (vehicle, vehicle_id, period, return_bps, tracked_bps, difference_bps, error_bps)"
                     " VALUES ('fund', %s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING", (fnd["id"], period, *f.values()))


def passive_target_bps(conn: Connection, period: int) -> int:
    return min(data.PASSIVE_START_BPS + data.PASSIVE_RISE_BPS_A_YEAR * max(period - 1, 0) // 4, data.PASSIVE_MOST_BPS)


def passive_value(conn: Connection, now: datetime) -> int:
    total = 0
    for e in _rows(conn, "SELECT * FROM etfs WHERE status = 'open' AND method <> 'swap' AND index_code IS NOT NULL"):
        total += units_out(conn, e) * e["nav"]
    from simulation import funds
    for f in _rows(conn, "SELECT * FROM investment_funds WHERE strategy = 'index' AND status = 'open'"):
        total += funds.worth(conn, f, now)
    return total


def market_value(conn: Connection, now: datetime) -> int:
    from simulation import marketview
    return sum(s["market_value"] or 0 for s in marketview._shares(conn, exchange.session_of(now)[0]))


def _score(conn: Connection, kind: str, row: dict) -> float:
    """How attractive a vehicle is to the households: cheap and close-copying wins."""
    t = _one(conn, "SELECT avg(abs(error_bps))::float AS e FROM (SELECT error_bps FROM tracking_quarters WHERE vehicle = %s AND vehicle_id = %s"
                   " AND error_bps IS NOT NULL ORDER BY period DESC LIMIT 4) x", (kind, row["id"]))
    err = t["e"] if t and t["e"] is not None else 50.0
    return 1.0 / (row["fee_bps"] + err / 2 + 10)


def _passive_money(conn: Connection, period: int, now: datetime) -> None:
    """The households move part of the way towards their target share of the market held in index funds and ETFs, split
    among the vehicles by how cheap and how close-copying each is."""
    households = ledger.account_id(conn, HOUSEHOLDS)
    target = passive_target_bps(conn, period)
    market = market_value(conn, now)
    have = passive_value(conn, now)
    move = (market * target // BPS - have) * data.PASSIVE_STEP_BPS // BPS
    vehicles = []
    for e in _rows(conn, "SELECT * FROM etfs WHERE status = 'open' AND method <> 'swap' AND index_code IN (SELECT code FROM market_indexes"
                         " WHERE kind = 'shares')"):
        vehicles.append(("etf", e))
    for f in _rows(conn, "SELECT * FROM investment_funds WHERE strategy = 'index' AND status = 'open' AND index_code IN (SELECT code FROM"
                         " market_indexes WHERE kind = 'shares')"):
        vehicles.append(("fund", f))
    scores = [_score(conn, k, r) for k, r in vehicles]
    total_score = sum(scores) or 1
    from simulation import funds
    for (kind, row), sc in zip(vehicles, scores):
        amount = int(move * sc / total_score)
        if kind == "etf":
            nav = nav_now(conn, row, now)
            units = abs(amount) // max(nav, 1) // data.ETF_CREATION_UNITS * data.ETF_CREATION_UNITS
            if units <= 0:
                continue
            if amount > 0 and ledger.balance(conn, households) >= units * nav * 2:
                _create_cash(conn, row, households, units, now, period, fee_bps=DEALING_COST_BPS)
            elif amount < 0:
                units = min(units, ledger.balance(conn, households, row["asset"]) // data.ETF_CREATION_UNITS * data.ETF_CREATION_UNITS)
                if units > 0:
                    _redeem(conn, row, households, units, "cash", now, period, fee_bps=DEALING_COST_BPS)
            flow = units * nav * (1 if amount > 0 else -1)
        else:
            flow = 0
            if amount > 0:
                amount = min(amount, max(ledger.balance(conn, households), 0) // 2)
                if amount > 0:
                    ledger.transfer(conn, payer=households, receiver=funds.dealing_account(conn), amount=amount, kind="fund_order_hold",
                                    memo=f"{row['name']}: households' money held until the bell", period=period)
                    conn.execute("INSERT INTO fund_orders (fund_id, account_id, side, amount, placed_at) VALUES (%s, %s, 'in', %s, %s)",
                                 (row["id"], households, amount, now))
                    flow = amount
            elif amount < 0:
                held = _one(conn, "SELECT * FROM fund_units WHERE fund_id = %s AND account_id = %s", (row["id"], households))
                price = funds.unit_price(row, funds.worth(conn, row, now))
                units = min(-amount * funds.UNIT // max(price, 1), (held["units"] - held["leaving"]) if held else 0)
                if units > 0:
                    conn.execute("UPDATE fund_units SET leaving = leaving + %s WHERE fund_id = %s AND account_id = %s", (units, row["id"], households))
                    conn.execute("INSERT INTO fund_orders (fund_id, account_id, side, units, placed_at) VALUES (%s, %s, 'out', %s, %s)",
                                 (row["id"], households, units, now))
                    flow = -funds.value_of(units, price)
        if abs(flow) >= naira(data.PASSIVE_RECORD_ALERT_NAIRA):
            _alert(conn, kind="flows", etf=row if kind == "etf" else None, index_code=row["index_code"],
                   headline=f"{_money(abs(flow))} {'into' if flow > 0 else 'out of'} {row['name']}",
                   words=f"The households moved {_money(abs(flow))} {'into' if flow > 0 else 'out of'} {row['name']} this quarter, as money"
                         f" {'pours into' if flow > 0 else 'leaves'} funds that copy the market.", now=now, everyone=True)
            _news(conn, "etf_flows", now, {"fund": row["name"], "amount": _money(abs(flow)), "side": "into" if flow > 0 else "out of"})
    after = passive_value(conn, now)
    conn.execute("INSERT INTO passive_quarters (period, passive_value, market_value, share_bps, target_bps) VALUES (%s, %s, %s, %s, %s)"
                 " ON CONFLICT DO NOTHING", (period, after, market, after * BPS // market if market else 0, target))


# ---------------------------------------------------------------------------
# Launching and running a player's ETF (shared rules with Part 2)
# ---------------------------------------------------------------------------

def launch(conn: Connection, player_id, *, code: str, name: str, index_code: str, method: str, fee_bps: int, seed: int, now: datetime,
           words: str = "") -> dict:
    """An Asset Manager of Level 20 launches an ETF copying an index (the game's or their own): ₦2 million to register, and at
    least ₦5 million of their own money, which makes the first units at ₦100. One ETF per manager at a time."""
    from simulation import funds
    with conn.transaction():
        state = _state(conn, now)
        conn.execute("SELECT 1 FROM players WHERE id = %s FOR UPDATE", (player_id,))
        try:
            funds._manager_ok(conn, player_id)
        except funds.FundError as refused:
            raise EtfError(str(refused)) from None
        if _one(conn, "SELECT 1 AS x FROM etfs WHERE manager_id = %s AND status IN ('open', 'closing')", (player_id,)):
            raise EtfError("You already run an ETF. A manager runs one ETF at a time.")
        idx = _one(conn, "SELECT * FROM market_indexes WHERE code = %s AND status = 'live'", ((index_code or "").upper(),))
        if idx is None:
            raise EtfError("Choose an index that exists.")
        if idx["owner_id"] is not None and idx["owner_id"] != player_id:
            raise EtfError("A manager's own index can be copied only by that manager.")
        if method not in ("full", "sample"):
            raise EtfError("Copy the index in full, or by sampling its largest members.")
        if idx["kind"] == "bonds" and method == "sample":
            raise EtfError("A bond index is copied in full.")
        if not isinstance(fee_bps, int) or isinstance(fee_bps, bool) or not 0 <= fee_bps <= data.ETF_FEE_MOST_BPS:
            raise EtfError(f"An index fund's yearly fee is from 0% to {data.ETF_FEE_MOST_BPS / 100:g}%.")
        code = (code or "").upper().strip()
        if not code.isalpha() or not 3 <= len(code) <= 5:
            raise EtfError("An ETF's code is 3 to 5 letters.")
        taken = {r["c"] for r in _rows(conn, "SELECT ticker AS c FROM companies UNION SELECT code FROM etfs UNION SELECT code FROM market_indexes")}
        if code in taken:
            raise EtfError("That code is taken.")
        name = " ".join((name or "").split())
        if not 3 <= len(name) <= 60 or not name[0].isalpha() or not all((ch.isascii() and ch.isalnum()) or ch in " &'-." for ch in name):
            raise EtfError("An ETF's name is 3 to 60 letters, numbers and spaces.")
        key = _key(name)
        names = {_key(r["name"]) for r in _rows(conn, "SELECT name FROM companies UNION ALL SELECT name FROM empires UNION ALL"
                                                      " SELECT name FROM investment_funds UNION ALL SELECT name FROM etfs")}
        if key in names or any(w in key for w in ("centralbank", "federalgovernment", "treasury", "broadstreet", "regulator")):
            raise EtfError("That name is taken, or is too close to an institution's.")
        if not isinstance(seed, int) or isinstance(seed, bool) or seed < naira(data.INVEST_FUND_SEED_NAIRA):
            raise EtfError(f"A manager puts in at least {_money(naira(data.INVEST_FUND_SEED_NAIRA))} of their own money.")
        me = ledger.player_account_id(conn, player_id)
        fee = naira(data.INVEST_FUND_REGISTRATION_NAIRA)
        units = seed // data.ETF_FIRST_NAV_KOBO // data.ETF_CREATION_UNITS * data.ETF_CREATION_UNITS
        if ledger.balance(conn, me) < fee + units * data.ETF_FIRST_NAV_KOBO:
            raise EtfError(f"Launching costs {_money(fee)} to register, and your own money of {_money(seed)}.")
        ledger.transfer(conn, payer=me, receiver=ledger.account_id(conn, ledger.PRIZE_POOL), amount=fee, kind="fund_registration",
                        memo=f"{name}: registration of an ETF", period=state["period"])
        etf = _new_etf(conn, code=code, name=name, index_code=idx["code"], commodity=None, leverage=10_000, method=method, fee=fee_bps,
                       manager_id=player_id, computer=False, now=now, period=state["period"], words=" ".join((words or "").split())[:400])
        _create_cash(conn, etf, me, units, now, state["period"], fee_bps=0)
        conn.execute("UPDATE etfs SET nav = %s, reference_price = %s WHERE id = %s", (nav_now(conn, _etf(conn, etf["id"]), now),
                                                                                     data.ETF_FIRST_NAV_KOBO, etf["id"]))
        careers._event(conn, player_id, "asset_manager", "fund_opened", f"Launched the ETF {name} ({code}).", now)
        _alert(conn, kind="launched", etf=etf, headline=f"New ETF: {name} ({code})",
               words=f"It copies {idx['name']}{' by sampling its largest members' if method == 'sample' else ''}. Fee {fee_bps / 100:.2f}% a year.",
               now=now)
        _news(conn, "etf_launched", now, {"etf": name, "code": code, "index": idx["name"], "manager": _player_name(conn, player_id)})
        return _etf(conn, etf["id"])


def _player_name(conn: Connection, player_id) -> str:
    row = _one(conn, "SELECT display_name FROM players WHERE id = %s", (player_id,))
    return row["display_name"] if row else "Broad Street Asset Management"


def _managed(conn: Connection, player_id) -> dict:
    row = _one(conn, "SELECT * FROM etfs WHERE manager_id = %s AND status IN ('open', 'closing') FOR UPDATE", (player_id,))
    if row is None:
        raise EtfError("You run no ETF.")
    return row


def lower_fee(conn: Connection, player_id, fee_bps: int, now: datetime) -> dict:
    with conn.transaction():
        _state(conn, now)
        etf = _managed(conn, player_id)
        if not isinstance(fee_bps, int) or isinstance(fee_bps, bool) or not 0 <= fee_bps <= etf["fee_bps"]:
            raise EtfError("The fee can be lowered, never raised.")
        conn.execute("UPDATE etfs SET fee_bps = %s WHERE id = %s", (fee_bps, etf["id"]))
        return _etf(conn, etf["id"])


def close(conn: Connection, player_id, now: datetime) -> dict:
    with conn.transaction():
        _state(conn, now)
        etf = _managed(conn, player_id)
        if etf["status"] != "open":
            raise EtfError("The ETF is already closing.")
        _start_closing(conn, etf, "The manager is closing it.", now)
        return _etf(conn, etf["id"])


def _start_closing(conn: Connection, etf: dict, why: str, now: datetime) -> None:
    conn.execute("UPDATE etfs SET status = 'closing', closing_since = %s WHERE id = %s", (now, etf["id"]))
    period = careers.world_now(conn, now)["period"]
    for o in _rows(conn, "SELECT * FROM etf_orders WHERE etf_id = %s AND status = 'open' FOR UPDATE", (etf["id"],)):
        _release(conn, etf, o, period, "cancelled")
    _alert(conn, kind="closing", etf=etf, headline=f"{etf['name']} is closing",
           words=f"{why} Trading stops now; at the next closing bell everything it holds is sold and every holder paid the value of their units.",
           now=now)


def follow(conn: Connection, player_id, code: str, on: bool, now: datetime) -> None:
    etf = by_code(conn, code)
    if on:
        conn.execute("INSERT INTO etf_follows (player_id, etf_id, at) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING", (player_id, etf["id"], now))
    else:
        conn.execute("DELETE FROM etf_follows WHERE player_id = %s AND etf_id = %s", (player_id, etf["id"]))


# ---------------------------------------------------------------------------
# Pop-ups and news
# ---------------------------------------------------------------------------

def _alert(conn: Connection, *, kind: str, headline: str, words: str, now: datetime, etf: dict | None = None, index_code: str | None = None,
           everyone: bool = False) -> None:
    conn.execute("INSERT INTO etf_alerts (etf_id, index_code, kind, everyone, headline, words, at) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                 (etf["id"] if etf else None, index_code or (etf["index_code"] if etf else None), kind, everyone, headline[:160], words[:600], now))


def _news(conn: Connection, kind: str, now: datetime, facts: dict) -> None:
    from simulation import news
    if kind not in news.BY_NAME:
        return
    w = careers.world_now(conn, now)
    news.publish(conn, period=w["period"], day=w["day"], kind=kind, story=f"etf:{kind}:{w['period']}:{w['day']}:{facts.get('code', facts.get('index', ''))}",
                 facts=facts)


def alerts_for(conn: Connection, player_id, after: int | None, now: datetime) -> dict:
    """Everybody's ETF pop-ups, and those of the ETFs a player (or their empire) holds or follows, and changes to indexes
    whose funds or ETFs they hold."""
    accounts = [ledger.player_account_id(conn, player_id)]
    seat = empires.seat_of(conn, player_id)
    if seat and seat["empire_kind"] != "pension":
        accounts.append(seat["account_id"])
    since = after if after is not None else _one(conn, "SELECT coalesce(max(id), 0) AS m FROM etf_alerts WHERE at < %s", (now - timedelta(hours=24),))["m"]
    found = _rows(conn, """
        SELECT a.id, a.kind, a.headline, a.words, a.at, e.code FROM etf_alerts a LEFT JOIN etfs e ON e.id = a.etf_id
        WHERE a.id > %s AND (a.everyone
           OR EXISTS (SELECT 1 FROM ledger_balances b WHERE b.asset = e.asset AND b.account_id = ANY(%s) AND b.balance > 0)
           OR EXISTS (SELECT 1 FROM etf_follows f WHERE f.etf_id = a.etf_id AND f.player_id = %s)
           OR (a.kind = 'index_change' AND (EXISTS (SELECT 1 FROM etfs x JOIN ledger_balances b ON b.asset = x.asset
                                                    WHERE x.index_code = a.index_code AND b.account_id = ANY(%s) AND b.balance > 0)
                                         OR EXISTS (SELECT 1 FROM investment_funds f JOIN fund_units u ON u.fund_id = f.id
                                                    WHERE f.index_code = a.index_code AND u.account_id = ANY(%s) AND u.units > 0))))
        ORDER BY a.id LIMIT 5""", (since, accounts, player_id, accounts, accounts))
    newest = _one(conn, "SELECT coalesce(max(id), 0) AS m FROM etf_alerts")["m"]
    return {"mark": found[-1]["id"] if len(found) == 5 else max(newest, since), "alerts": found}


# ---------------------------------------------------------------------------
# What it is all worth to its holders
# ---------------------------------------------------------------------------

def held_value(conn: Connection, account) -> int:
    """An account's ETF units at the last bell's value (or the closing price, if lower: one trade at the bell cannot make anybody
    richer), units held for its sell orders, and cash held for its buy orders."""
    if not ready(conn):
        return 0
    total = 0
    for r in _rows(conn, "SELECT b.balance, least(e.nav, e.reference_price) AS p FROM ledger_balances b JOIN etfs e ON e.asset = b.asset"
                         " WHERE b.account_id = %s AND b.balance > 0", (account,)):
        total += r["balance"] * r["p"]
    for o in _rows(conn, "SELECT o.side, o.reserved, least(e.nav, e.reference_price) AS p FROM etf_orders o JOIN etfs e ON e.id = o.etf_id"
                         " WHERE o.account_id = %s AND o.status = 'open' AND NOT o.maker", (account,)):
        total += o["reserved"] if o["side"] == "buy" else o["reserved"] * o["p"]
    return total


def _players_etfs(conn: Connection) -> dict:
    if not ready(conn):
        return {}
    accounts = {r["account_id"] for r in _rows(conn, "SELECT DISTINCT b.account_id FROM ledger_balances b JOIN etfs e ON e.asset = b.asset"
                                                     " JOIN ledger_accounts a ON a.id = b.account_id WHERE a.kind = 'player' AND b.balance > 0"
                                                     " UNION SELECT o.account_id FROM etf_orders o JOIN ledger_accounts a ON a.id = o.account_id"
                                                     " WHERE a.kind = 'player' AND o.status = 'open' AND NOT o.maker")}
    return {a: (0, held_value(conn, a)) for a in accounts}


def _register() -> None:
    from simulation import marketview
    if _players_etfs not in marketview._OTHER_HOLDINGS:
        marketview._OTHER_HOLDINGS.append(_players_etfs)


_register()


def check_books(conn: Connection) -> list[str]:
    """The cash and units held for open orders are exactly what the orders say."""
    if not ready(conn):
        return []
    problems = []
    acc = _one(conn, "SELECT id FROM ledger_accounts WHERE code = %s", (HELD,))
    if acc is None:
        return problems
    cash = _one(conn, "SELECT coalesce(sum(reserved), 0)::bigint AS t FROM etf_orders WHERE status = 'open' AND side = 'buy' AND NOT maker")["t"]
    if ledger.balance(conn, acc["id"]) != cash:
        problems.append(f"ETF orders hold {ledger.balance(conn, acc['id'])} in cash, but their orders say {cash}")
    for e in _rows(conn, "SELECT id, asset, code FROM etfs"):
        units = _one(conn, "SELECT coalesce(sum(reserved), 0)::bigint AS t FROM etf_orders WHERE etf_id = %s AND status = 'open' AND side = 'sell'"
                           " AND NOT maker", (e["id"],))["t"]
        if ledger.balance(conn, acc["id"], e["asset"]) != units:
            problems.append(f"{e['code']}: {ledger.balance(conn, acc['id'], e['asset'])} units held for orders, but their orders say {units}")
    return problems


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

KIND_WORDS = {"index": "Copies its index", "leverage": "Twice the index's daily move (resets every day)",
              "inverse": "The opposite of the index's daily move (resets every day)", "commodity": "Follows a commodity's price"}


def _tracking_line(conn: Connection, kind: str, vehicle_id) -> dict:
    rows = _rows(conn, "SELECT * FROM tracking_quarters WHERE vehicle = %s AND vehicle_id = %s ORDER BY period DESC LIMIT 4", (kind, vehicle_id))
    errs = [r["error_bps"] for r in rows if r["error_bps"] is not None]
    diffs = [r["difference_bps"] for r in rows if r["difference_bps"] is not None]
    return {"error_bps": round(sum(errs) / len(errs)) if errs else None, "difference_bps": sum(diffs) if diffs else None, "quarters": len(rows)}


def _summary(conn: Connection, etf: dict, now: datetime) -> dict:
    nav = nav_now(conn, etf, now)
    price = etf["last_price"] if etf["last_price"] and etf["session_date"] == exchange.session_of(now)[0] else etf["reference_price"]
    days = _rows(conn, "SELECT session_date, nav, close FROM etf_days WHERE etf_id = %s ORDER BY session_date DESC LIMIT 29", (etf["id"],))

    def since(n):
        return (price - days[n]["close"]) * BPS // days[n]["close"] if len(days) > n and days[n]["close"] else None
    tracked = (_one(conn, "SELECT name FROM market_indexes WHERE code = %s", (etf["index_code"],)) or {}).get("name") if etf["index_code"] else \
        {"OIL": "Oil, in naira a barrel", "METALS": "The metals price index (gold and other metals)"}[etf["commodity"]]
    n = units_out(conn, etf)
    return {"id": etf["id"], "code": etf["code"], "name": etf["name"], "kind": kind_of(etf), "kind_words": KIND_WORDS[kind_of(etf)],
            "tracks": tracked, "index_code": etf["index_code"], "method": etf["method"], "fee_bps": etf["fee_bps"], "computer": etf["computer"],
            "manager": _player_name(conn, etf["manager_id"]) if etf["manager_id"] else "Broad Street Asset Management",
            "status": etf["status"], "price": price, "nav": nav, "premium_bps": (price - nav) * BPS // nav if nav else 0,
            "day_bps": since(0), "quarter_bps": since(7), "year_bps": since(28), "units": n, "size": n * nav,
            "volume": (_one(conn, "SELECT coalesce(sum(quantity), 0)::bigint AS v FROM etf_trades WHERE etf_id = %s AND session_date = %s",
                            (etf["id"], exchange.session_of(now)[0])) or {"v": 0})["v"],
            "tracking": _tracking_line(conn, "etf", etf["id"]), "special": special(etf)}


def listing(conn: Connection, player_id, now: datetime) -> dict:
    from simulation import funds
    etfs = [_summary(conn, e, now) for e in _rows(conn, "SELECT * FROM etfs WHERE status IN ('open', 'closing') ORDER BY computer DESC, code")]
    index_funds = []
    for f in _rows(conn, "SELECT * FROM investment_funds WHERE strategy = 'index' AND status IN ('open', 'closing') ORDER BY id"):
        s = funds._summary(conn, f, now)
        s["tracking"] = _tracking_line(conn, "fund", f["id"])
        s["index_code"] = f["index_code"]
        index_funds.append(s)
    seat = empires.seat_of(conn, player_id)
    dealer = bool(seat and _one(conn, "SELECT 1 AS x FROM etf_dealers WHERE empire_id = %s AND status = 'approved'", (seat["empire_id"],)))
    period = careers.world_now(conn, now)["period"]
    last = _one(conn, "SELECT * FROM passive_quarters ORDER BY period DESC LIMIT 1")
    career = careers.career(conn, player_id, "asset_manager")
    build = _one(conn, "SELECT build FROM players WHERE id = %s", (player_id,))["build"]
    return {"indexes": indexes.listing(conn, now), "etfs": etfs, "index_funds": index_funds,
            "passive": {"share_bps": last["share_bps"] if last else (passive_value(conn, now) * BPS // max(market_value(conn, now), 1)),
                        "target_bps": passive_target_bps(conn, period)},
            "dealer": {"approved": dealer, "head": bool(seat and seat["head_player_id"] == player_id),
                       "least_worth": naira(data.ETF_DEALER_LEAST_WORTH_NAIRA)},
            "warning_read": bool(_one(conn, "SELECT 1 AS x FROM etf_warnings WHERE player_id = %s", (player_id,))),
            "special_level": data.ETF_SPECIAL_LEVEL,
            "can_launch": bool(build == "asset_manager" and career and career["level"] >= data.ETF_LEVEL),
            "launch": {"level": data.ETF_LEVEL, "registration": naira(data.INVEST_FUND_REGISTRATION_NAIRA), "seed": naira(data.INVEST_FUND_SEED_NAIRA),
                       "fee_most_bps": data.ETF_FEE_MOST_BPS, "creation_units": data.ETF_CREATION_UNITS},
            "mine": mine(conn, player_id, now), "managing": manager_view(conn, player_id, now),
            "my_indexes": [i for i in indexes.listing(conn, now) if i["custom"] and _one(conn, "SELECT 1 AS x FROM market_indexes WHERE code = %s AND owner_id = %s",
                                                                                          (i["code"], player_id))]}


def factsheet(conn: Connection, code: str, player_id, now: datetime) -> dict:
    etf = by_code(conn, code)
    out = _summary(conn, etf, now)
    out["words"] = etf["words"]
    out["quote"] = maker_quote(conn, etf, now) if etf["status"] == "open" else None
    low, high = band(etf)
    out["band"] = {"low": low, "high": high}
    days = _rows(conn, "SELECT session_date, nav, close, volume, created, redeemed FROM etf_days WHERE etf_id = %s ORDER BY session_date DESC LIMIT 120",
                 (etf["id"],))[::-1]
    out["history"] = [{"day": d["session_date"], "nav": d["nav"], "close": d["close"], "volume": d["volume"],
                       "premium_bps": (d["close"] - d["nav"]) * BPS // d["nav"] if d["nav"] else 0} for d in days]
    out["basket"] = basket(conn, etf, data.ETF_CREATION_UNITS, now) if etf["method"] != "swap" and etf["status"] == "open" else None
    if out["basket"]:
        total = out["basket"]["value"] or 1
        out["basket"]["lines"] = [{**x, "weight_bps": x["units"] * x["price"] * BPS // total} for x in out["basket"]["lines"]]
        out["basket"]["lines"].sort(key=lambda x: -x["weight_bps"])
    book = _rows(conn, "SELECT side, limit_price, sum(remaining)::bigint AS units FROM etf_orders WHERE etf_id = %s AND status = 'open' AND NOT maker"
                       " GROUP BY side, limit_price ORDER BY side, limit_price DESC", (etf["id"],))
    out["book"] = {"buy": [{"limit_price": b["limit_price"], "units": b["units"]} for b in book if b["side"] == "buy"][:5],
                   "sell": sorted([{"limit_price": b["limit_price"], "units": b["units"]} for b in book if b["side"] == "sell"],
                                  key=lambda b: b["limit_price"])[:5]}
    me = ledger.player_account_id(conn, player_id)
    out["mine"] = {"units": ledger.balance(conn, me, etf["asset"]), "value": ledger.balance(conn, me, etf["asset"]) * out["price"]}
    seat = empires.seat_of(conn, player_id)
    if seat and seat["empire_kind"] != "pension":
        out["empire"] = {"units": ledger.balance(conn, seat["account_id"], etf["asset"]), "head": seat["head_player_id"] == player_id}
    out["orders"] = _rows(conn, "SELECT id, side, limit_price, quantity, remaining, status, placed_at FROM etf_orders WHERE etf_id = %s AND player_id = %s"
                                " ORDER BY id DESC LIMIT 10", (etf["id"], player_id))
    out["following"] = bool(_one(conn, "SELECT 1 AS x FROM etf_follows WHERE player_id = %s AND etf_id = %s", (player_id, etf["id"])))
    out["quarters"] = _rows(conn, "SELECT period, return_bps, tracked_bps, difference_bps, error_bps FROM tracking_quarters WHERE vehicle = 'etf'"
                                  " AND vehicle_id = %s ORDER BY period DESC LIMIT 8", (etf["id"],))
    for q in out["quarters"]:
        q["label"] = clock.period_label(q["period"])
    out["creation_units"] = data.ETF_CREATION_UNITS
    out["warning"] = _warning(etf) if special(etf) else None
    return out


def _warning(etf: dict) -> str:
    if kind_of(etf) == "commodity":
        return ("This ETF follows a commodity's price, which moves when the world's prices and the naira move. It holds cash and settles the day's"
                " move with the pension funds.")
    times = "twice" if kind_of(etf) == "leverage" else "the opposite of"
    return (f"This ETF gives {times} the index's move each day, and starts again every day. Over many days that is not {times} the index's"
            " move: in a market that goes up and down it loses value even if the index ends where it began. It is for trading over days, not"
            " for keeping. You can lose most of what you put in.")


def mine(conn: Connection, player_id, now: datetime) -> list[dict]:
    me = ledger.player_account_id(conn, player_id)
    out = []
    for r in _rows(conn, "SELECT e.*, b.balance FROM ledger_balances b JOIN etfs e ON e.asset = b.asset WHERE b.account_id = %s AND b.balance > 0"
                         " ORDER BY e.code", (me,)):
        s = _summary(conn, r, now)
        out.append({**s, "held": r["balance"], "value": r["balance"] * s["price"]})
    return out


def manager_view(conn: Connection, player_id, now: datetime) -> dict | None:
    etf = _one(conn, "SELECT * FROM etfs WHERE manager_id = %s AND status IN ('open', 'closing')", (player_id,))
    if etf is None:
        return None
    out = _summary(conn, etf, now)
    h = holdings_value(conn, etf["account_id"], now)
    out["cash"] = h["cash"]
    out["holdings"] = len(h["lines"])
    out["fees_this_quarter"] = _one(conn, "SELECT coalesce(sum(e.amount), 0)::bigint AS t FROM ledger_entries e JOIN ledger_transactions t ON t.id = e.transaction_id"
                                          " WHERE t.kind = 'etf_manager_fee' AND e.account_id = %s AND e.amount > 0 AND t.period = %s",
                                    (ledger.player_account_id(conn, player_id), careers.world_now(conn, now)["period"]))["t"]
    return out


def track_record(conn: Connection, player_id) -> list[dict]:
    """For Proven Talent: every ETF and index fund the player has run, and how closely it copied what it tracks."""
    if not ready(conn):
        return []
    out = []
    for e in _rows(conn, "SELECT * FROM etfs WHERE founder_id = %s ORDER BY id", (player_id,)):
        f = tracking_figures(_etf_pairs(conn, e["id"]))
        out.append({"name": f"{e['name']} ({e['code']})", "kind": "ETF", "tracks": e["index_code"], **f,
                    "quarters": _one(conn, "SELECT count(*) AS n FROM tracking_quarters WHERE vehicle = 'etf' AND vehicle_id = %s", (e["id"],))["n"]})
    for fnd in _rows(conn, "SELECT * FROM investment_funds WHERE founder_id = %s AND strategy = 'index' ORDER BY id", (player_id,)):
        f = tracking_figures(_fund_pairs(conn, fnd["id"]))
        out.append({"name": fnd["name"], "kind": "Index fund", "tracks": fnd["index_code"], **f,
                    "quarters": _one(conn, "SELECT count(*) AS n FROM tracking_quarters WHERE vehicle = 'fund' AND vehicle_id = %s", (fnd["id"],))["n"]})
    return out
