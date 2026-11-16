"""The Archegos moment (owner, 16 November 2026: "ok build"): prime brokerage on the Floor, and the day it goes wrong.

A computer hedge fund asks the players' open bank desks to hold shares of one company for it on a swap. A bank that says
yes buys the shares with its own cash (from the institutions, at the market price) and holds them; the fund posts 20% of
the value with the bank as margin. Each bank sees only its own swap: never how much the fund has asked of the others.

When the fund's time is up it either closes quietly (it buys the shares back at the market price, takes its margin back
and pays the bank its interest) or, now and then, blows up: it misses a margin call, the banks keep its margin and are
left holding its shares with nobody behind them. The share falls 12% at once and another 20% ten minutes later, and
bounces a little twenty minutes after that. The banks race to sell; whoever is still holding at the second fall is the
"last out". Whether a fund blows up is decided from the world's secret when it starts, so nobody can know in advance.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta

from psycopg import Connection
from psycopg.rows import dict_row

from simulation import clock, exchange
from simulation import world_data as data

BPS = 10_000


class PrimeError(Exception):
    """A swap the rules do not allow, with a message for the player."""


def _rows(conn: Connection, sql: str, params=()) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def _one(conn: Connection, sql: str, params=()) -> dict | None:
    rows = _rows(conn, sql, params)
    return rows[0] if rows else None


def _unit(*key) -> float:
    digest = hashlib.sha256("|".join(str(k) for k in key).encode()).digest()
    return int.from_bytes(digest[:8], "big") / 2**64


def ready(conn: Connection) -> bool:
    return bool(_one(conn, "SELECT to_regclass('floor_funds') IS NOT NULL AS ok")["ok"])


def _price(conn: Connection, ticker: str, now: datetime) -> int:
    q = exchange.quote(conn, ticker, now, depth=1)
    return q["last_price"] or q["reference_price"]


def _note(conn: Connection, key: str, words: str, now: datetime, ticker: str | None = None) -> None:
    from simulation import floor
    floor._note(conn, key, "drop", words, now, ticker)


def _net(legs: list) -> list:
    """Legs summed for each account and asset (the books take one line for each)."""
    from simulation.ledger import Leg
    total: dict = {}
    for leg in legs:
        key = (str(leg.account_id), leg.asset)
        total[key] = total.get(key, 0) + leg.amount
    return [Leg(account, amount, asset) for (account, asset), amount in total.items() if amount]


def _start(conn: Connection, now: datetime) -> dict | None:
    from simulation import floor
    seed, slot = floor._seed(conn), int(now.timestamp()) // 30
    if _unit(seed, "fund-start", slot) * data.FLOOR_FUND_CHANCE >= 1:
        return None
    listed = _rows(conn, "SELECT c.id, c.ticker FROM companies c JOIN market_instruments m ON m.company_id = c.id"
                         " WHERE m.halted_reason IS NULL ORDER BY c.ticker")
    if not listed:
        return None
    company = listed[int(_unit(seed, "fund-share", slot) * len(listed))]
    low, high = data.FLOOR_FUND_HOURS
    hours = low + _unit(seed, "fund-hours", slot) * (high - low)
    name = data.FLOOR_FUND_NAMES[int(_unit(seed, "fund-name", slot) * len(data.FLOOR_FUND_NAMES))]
    blows = _unit(seed, "fund-blows", slot) * BPS < data.FLOOR_FUND_BLOWUP_BPS
    return _one(conn, "INSERT INTO floor_funds (name, company_id, created_at, ends_at, blows_up, entry_price) VALUES (%s, %s, %s, %s, %s, %s)"
                      " RETURNING *", (name, company["id"], now, now + timedelta(hours=hours), blows, _price(conn, company["ticker"], now)))


def _offer(conn: Connection, fund: dict, now: datetime) -> None:
    """The fund asks every open bank desk it has not asked yet to hold shares for it."""
    from simulation import floor, ledger
    ticker = _one(conn, "SELECT ticker FROM companies WHERE id = %s", (fund["company_id"],))["ticker"]
    price = _price(conn, ticker, now)
    for d in _rows(conn, "SELECT d.player_id FROM floor_desks d JOIN players p ON p.id = d.player_id WHERE d.open AND p.build = 'investment_banker'"
                         " AND NOT EXISTS (SELECT 1 FROM floor_swaps s WHERE s.fund_id = %s AND s.player_id = d.player_id)", (fund["id"],)):
        cash = ledger.balance(conn, ledger.player_account_id(conn, d["player_id"]))
        shares = cash * data.FLOOR_SWAP_CASH_BPS // BPS // max(price, 1) // 100 * 100
        if shares <= 0:
            continue
        conn.execute("INSERT INTO floor_swaps (fund_id, player_id, shares, rate_bps, offered_at, answer_by) VALUES (%s, %s, %s, %s, %s, %s)",
                     (fund["id"], d["player_id"], shares, data.FLOOR_SWAP_RATE_BPS, now, now + timedelta(minutes=data.FLOOR_SWAP_ANSWER_MINUTES)))
        floor._ping_player(conn, d["player_id"])


def answer(conn: Connection, player_id, swap_id: int, accept: bool, now: datetime) -> dict:
    """The bank takes the swap on (it buys the shares from the institutions at the market price, and the fund posts its
    margin) or turns it down."""
    from simulation import corporate, floor, ledger
    from simulation.ledger import Leg
    with conn.transaction():
        s = _one(conn, "SELECT s.*, f.status AS fund_status, f.company_id, f.name AS fund, c.ticker, c.share_asset, c.name AS company"
                       " FROM floor_swaps s JOIN floor_funds f ON f.id = s.fund_id JOIN companies c ON c.id = f.company_id"
                       " WHERE s.id = %s FOR UPDATE OF s", (swap_id,))
        if s is None or str(s["player_id"]) != str(player_id):
            raise PrimeError("There is no such swap for your desk.")
        if s["status"] != "offered" or now >= s["answer_by"] or s["fund_status"] != "building":
            raise PrimeError("That swap is no longer on offer.")
        if not accept:
            conn.execute("UPDATE floor_swaps SET status = 'declined', closed_at = %s WHERE id = %s", (now, swap_id))
            return {"declined": swap_id}
        if clock.market_state(now).value != "open":
            raise PrimeError("A swap is taken on while the market is open.")
        bank = ledger.player_account_id(conn, player_id)
        fund = ledger.account_id(conn, ledger.INVESTORS_INSTITUTIONS)
        price = _price(conn, s["ticker"], now)
        cost = price * s["shares"]
        margin = cost * data.FLOOR_SWAP_MARGIN_BPS // BPS
        if ledger.balance(conn, bank) < cost:
            raise PrimeError(f"Holding the shares costs {floor._money(cost)}. Your desk has not that much cash.")
        if ledger.balance(conn, fund, s["share_asset"]) < s["shares"]:
            raise PrimeError("There are not enough of those shares to be had for the swap now.")
        ledger.post(conn, kind="floor_swap", memo=f"{s['shares']:,} {s['company']} shares held for {s['fund']} on a swap", reference=f"swap:{swap_id}",
                    legs=_net([Leg(fund, -s["shares"], s["share_asset"]), Leg(bank, s["shares"], s["share_asset"]),
                               Leg(bank, -cost), Leg(fund, cost), Leg(fund, -margin), Leg(bank, margin)]))
        conn.execute("INSERT INTO holding_events (account_id, company_id, kind, shares, amount, after_trade_id) VALUES (%s, %s, 'floor', %s, %s, %s)",
                     (bank, s["company_id"], s["shares"], cost, corporate._after_trade(conn)))
        conn.execute("UPDATE floor_swaps SET status = 'open', price = %s, margin = %s, opened_at = %s WHERE id = %s", (price, margin, now, swap_id))
    return {"open": swap_id, "price": price, "margin": margin}


def _close_quietly(conn: Connection, fund: dict, now: datetime) -> None:
    """The fund's time is up and all is well: it buys the shares back at the market price, takes its margin back and pays
    the bank its interest. A bank that sold the shares meanwhile must buy them back first, or the swap is settled in cash."""
    from simulation import corporate, ledger
    from simulation.ledger import Leg
    company = _one(conn, "SELECT id, ticker, share_asset, name FROM companies WHERE id = %s", (fund["company_id"],))
    price = _price(conn, company["ticker"], now)
    fund_account = ledger.account_id(conn, ledger.INVESTORS_INSTITUTIONS)
    for s in _rows(conn, "SELECT * FROM floor_swaps WHERE fund_id = %s AND status = 'open'", (fund["id"],)):
        bank = ledger.player_account_id(conn, s["player_id"])
        held = min(ledger.balance(conn, bank, company["share_asset"]), s["shares"])
        interest = s["price"] * s["shares"] * s["rate_bps"] // BPS
        legs = [Leg(bank, -s["margin"]), Leg(fund_account, s["margin"]), Leg(fund_account, -interest), Leg(bank, interest)]
        if held:
            legs += [Leg(bank, -held, company["share_asset"]), Leg(fund_account, held, company["share_asset"]),
                     Leg(fund_account, -held * price), Leg(bank, held * price)]
        legs = _net(legs)
        owed = sum(leg.amount for leg in legs if str(leg.account_id) == str(bank) and leg.asset == ledger.NGN)
        if ledger.balance(conn, bank) + owed < 0:
            continue                                   # the bank cannot hand the margin back: left for the next look
        ledger.post(conn, kind="floor_swap", memo=f"The swap for {fund['name']} closed", reference=f"swap-close:{s['id']}", legs=legs)
        if held:
            conn.execute("INSERT INTO holding_events (account_id, company_id, kind, shares, amount, after_trade_id) VALUES (%s, %s, 'floor', %s, %s, %s)",
                         (bank, company["id"], -held, held * price, corporate._after_trade(conn)))
        conn.execute("UPDATE floor_swaps SET status = 'closed', closed_at = %s, interest = %s WHERE id = %s", (now, interest, s["id"]))
    conn.execute("UPDATE floor_swaps SET status = 'lapsed', closed_at = %s WHERE fund_id = %s AND status = 'offered'", (now, fund["id"]))
    if not _one(conn, "SELECT 1 AS x FROM floor_swaps WHERE fund_id = %s AND status = 'open'", (fund["id"],)):
        conn.execute("UPDATE floor_funds SET status = 'closed' WHERE id = %s", (fund["id"],))


def _held_now(conn: Connection, s: dict, asset: str) -> int:
    from simulation import ledger
    return min(ledger.balance(conn, ledger.player_account_id(conn, s["player_id"]), asset), s["shares"])


def _blow_up(conn: Connection, fund: dict, now: datetime) -> None:
    """The fund misses its margin call. The banks keep its margin and are left with its shares; the share falls, in two
    steps ten minutes apart, then bounces a little. Who got out before each fall is written down."""
    from simulation import floor
    company = _one(conn, "SELECT id, ticker, share_asset, name FROM companies WHERE id = %s", (fund["company_id"],))
    step = fund["stage"]
    gap = timedelta(minutes=data.FLOOR_BLOWUP_GAP_MINUTES)
    if step == 0:
        conn.execute("UPDATE floor_swaps SET status = 'defaulted', closed_at = %s WHERE fund_id = %s AND status = 'open'", (now, fund["id"]))
        conn.execute("UPDATE floor_swaps SET status = 'lapsed', closed_at = %s WHERE fund_id = %s AND status = 'offered'", (now, fund["id"]))
        for sw in _rows(conn, "SELECT * FROM floor_swaps WHERE fund_id = %s AND status = 'defaulted'", (fund["id"],)):
            if _held_now(conn, sw, company["share_asset"]) == 0:
                conn.execute("UPDATE floor_swaps SET out_before = 1 WHERE id = %s", (sw["id"],))   # already out before the first fall
        banks = _one(conn, "SELECT count(*)::int AS n FROM floor_swaps WHERE fund_id = %s AND status = 'defaulted'", (fund["id"],))["n"]
        fall = data.FLOOR_BLOWUP_FALLS_BPS[0]
        exchange.reprice(conn, company["id"], _price(conn, company["ticker"], now) * (BPS - fall) // BPS, now,
                         f"{fund['name']} missed a margin call: its banks are selling")
        conn.execute("UPDATE floor_funds SET status = 'blown', stage = 1, blown_at = %s WHERE id = %s", (now, fund["id"]))
        _note(conn, f"fund:{fund['id']}:blown", f"{fund['name']} has missed a margin call. Banks were holding {company['ticker']} for it; "
              f"{banks} of them on the Floor. {company['ticker']} falls {fall / 100:.0f}%. More selling is expected.", now, company["ticker"])
        for s in _rows(conn, "SELECT player_id FROM floor_swaps WHERE fund_id = %s AND status = 'defaulted'", (fund["id"],)):
            floor._ping_player(conn, s["player_id"])
    elif step == 1 and now >= fund["blown_at"] + gap:
        for s in _rows(conn, "SELECT * FROM floor_swaps WHERE fund_id = %s AND status = 'defaulted' AND out_before IS NULL", (fund["id"],)):
            if _held_now(conn, s, company["share_asset"]) == 0:
                conn.execute("UPDATE floor_swaps SET out_before = 2 WHERE id = %s", (s["id"],))
        fall = data.FLOOR_BLOWUP_FALLS_BPS[1]
        exchange.reprice(conn, company["id"], _price(conn, company["ticker"], now) * (BPS - fall) // BPS, now,
                         f"The banks behind {fund['name']} dumped their shares")
        conn.execute("UPDATE floor_funds SET stage = 2 WHERE id = %s", (fund["id"],))
        last = _one(conn, "SELECT count(*)::int AS n FROM floor_swaps WHERE fund_id = %s AND status = 'defaulted' AND out_before IS NULL", (fund["id"],))["n"]
        _note(conn, f"fund:{fund['id']}:second", f"{company['ticker']} falls another {fall / 100:.0f}% as the banks behind {fund['name']} dump their shares."
              + (f" {last} bank{'s' if last != 1 else ''} on the Floor still holding: the last out." if last else " Every bank on the Floor got out in time."),
              now, company["ticker"])
        for s in _rows(conn, "SELECT player_id FROM floor_swaps WHERE fund_id = %s AND status = 'defaulted'", (fund["id"],)):
            floor._ping_player(conn, s["player_id"])
    elif step == 2 and now >= fund["blown_at"] + gap * 3:
        exchange.reprice(conn, company["id"], _price(conn, company["ticker"], now) * (BPS + data.FLOOR_BLOWUP_RECOVERY_BPS) // BPS, now,
                         f"Bargain hunters return to {company['ticker']} after {fund['name']}")
        conn.execute("UPDATE floor_funds SET stage = 3 WHERE id = %s", (fund["id"],))
        _note(conn, f"fund:{fund['id']}:settled", f"The dust settles on {company['ticker']}: bargain hunters lift it {data.FLOOR_BLOWUP_RECOVERY_BPS / 100:.0f}%.",
              now, company["ticker"])


def tick(conn: Connection, now: datetime) -> None:
    if not ready(conn):
        return
    conn.execute("UPDATE floor_swaps SET status = 'lapsed', closed_at = %s WHERE status = 'offered' AND answer_by <= %s", (now, now))
    for fund in _rows(conn, "SELECT * FROM floor_funds WHERE status = 'blown' AND stage < 3 ORDER BY id"):
        with conn.transaction():
            # Who got out before the first fall: sold their shares before it came (between taking the swap on and the blow-up).
            _blow_up(conn, fund, now)
    open_market = clock.market_state(now).value == "open"
    for fund in _rows(conn, "SELECT * FROM floor_funds WHERE status = 'building' ORDER BY id"):
        with conn.transaction():
            if now >= fund["ends_at"] and open_market:
                if fund["blows_up"]:
                    _blow_up(conn, fund, now)
                else:
                    _close_quietly(conn, fund, now)
            elif open_market and now < fund["ends_at"] - timedelta(minutes=data.FLOOR_SWAP_ANSWER_MINUTES):
                _offer(conn, fund, now)
    if open_market and not _one(conn, "SELECT 1 AS x FROM floor_funds WHERE status = 'building' OR (status = 'blown' AND stage < 3)"):
        with conn.transaction():
            fund = _start(conn, now)
            if fund:
                _offer(conn, fund, now)


def view(conn: Connection, player_id, now: datetime) -> list[dict]:
    """A bank's own swaps: never how much the fund asked of anybody else, nor whether it will blow up."""
    if not ready(conn):
        return []
    from simulation import ledger
    out = []
    for s in _rows(conn, "SELECT s.*, f.name AS fund, f.status AS fund_status, f.stage, c.ticker, c.name AS company, c.share_asset"
                         " FROM floor_swaps s JOIN floor_funds f ON f.id = s.fund_id JOIN companies c ON c.id = f.company_id"
                         " WHERE s.player_id = %s ORDER BY s.status IN ('offered', 'open', 'defaulted') DESC, s.id DESC LIMIT 6", (player_id,)):
        price = _price(conn, s["ticker"], now)
        held = min(ledger.balance(conn, ledger.player_account_id(conn, player_id), s["share_asset"]), s["shares"]) if s["status"] in ("open", "defaulted") else 0
        out.append({"id": s["id"], "fund": s["fund"], "ticker": s["ticker"], "company": s["company"], "shares": s["shares"], "status": s["status"],
                    "answer_by": s["answer_by"], "price": s["price"], "price_now": price, "margin": s["margin"], "rate_bps": s["rate_bps"],
                    "interest": s["interest"], "held_now": held, "stage": s["stage"] if s["status"] == "defaulted" else None,
                    "out_before": s["out_before"],
                    "offer_value": price * s["shares"] if s["status"] == "offered" else None})
    return out
