"""The Broad Street Exchange (design document, section 11).

Players and computer-run investors buy and sell companies' shares here.

How one order is handled, in plain words:

  1. The cash (to buy) or the shares (to sell) are moved to the exchange to hold.
     This is the "reserve": the same cash or shares cannot be promised twice.
  2. While the market is open, the order-matching engine is asked who the order
     trades with. The engine is a separate small program written in Rust; it holds
     nothing and moves nothing. It only answers "this order trades with those
     waiting orders, at these prices".
  3. Every pairing it proposes is checked here, then settled through the ledger:
     shares to the buyer, cash to the seller, fees to the exchange and the Government.
  4. Whatever is not traded waits in the order book (a limit order) or is cancelled
     and handed back (a market order).

Everything that moves, moves through the ledger, so no naira and no share can
appear or vanish here.
"""

from __future__ import annotations

import os
import subprocess
import threading
from datetime import datetime, timedelta
from pathlib import Path
from uuid import UUID

from psycopg import Connection
from psycopg.rows import dict_row

from simulation import clock, ledger
from simulation import world_data as data
from simulation.ledger import NGN, Leg
from simulation.money import BPS, MAX_AMOUNT

ESCROW = "exchange:held"          # cash and shares held for open orders
FEES = "exchange:fees"            # the exchange's own income
TRADER_KINDS = ("player", "npc_investors", "empire", "fund", "firm")


class ExchangeError(Exception):
    """The exchange refused something. The message is written for the player."""


class EngineFailure(Exception):
    """The order-matching engine could not be reached or answered nonsense."""


# ---------------------------------------------------------------------------
# The order-matching engine: a separate program, kept running, spoken to in plain text.
# ---------------------------------------------------------------------------

def _engine_path() -> str:
    candidates = [
        os.environ.get("BSX_ENGINE"),
        str(Path(__file__).resolve().parent.parent / "engine" / "target" / "release" / "bsx-engine"),
        "/usr/local/bin/bsx-engine",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return candidate
    raise EngineFailure("The order-matching engine has not been built. Run: cargo build --release (in the engine folder).")


class Engine:
    """One running copy of the engine. One request at a time; restarted if it ever stops."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._process: subprocess.Popen | None = None

    def _start(self) -> subprocess.Popen:
        return subprocess.Popen([_engine_path()], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)

    def _ask(self, request: str) -> list[list[int]]:
        """Send one request. Returns the answer: its first line, then one list of numbers per line."""
        with self._lock:
            for attempt in (1, 2):
                if self._process is None or self._process.poll() is not None:
                    self._process = self._start()
                try:
                    self._process.stdin.write(request)
                    self._process.stdin.flush()
                    head = self._process.stdout.readline().split()
                    if not head:
                        raise BrokenPipeError
                    if head[0] != "OK":
                        raise EngineFailure("The engine refused the request: " + " ".join(head[1:]))
                    answer = [[int(head[1]), int(head[2])]]
                    for _ in range(answer[0][0]):
                        answer.append([int(word) for word in self._process.stdout.readline().split()])
                    return answer
                except (BrokenPipeError, OSError, ValueError, IndexError) as problem:
                    # The engine holds nothing, so starting it again loses nothing.
                    self._process.kill()
                    self._process = None
                    if attempt == 2:
                        raise EngineFailure("The order-matching engine is not answering.") from problem
        raise EngineFailure("The order-matching engine is not answering.")

    def match(self, side: str, limit: int | None, quantity: int, opposite: list[dict], low: int, high: int) -> tuple[list[dict], int]:
        lines = [f"MATCH {'B' if side == 'buy' else 'S'} {limit if limit is not None else '-'} {quantity} {low} {high} {len(opposite)}"]
        lines += [f"{o['id']} {o['limit_price']} {o['remaining']} {o.get('seq', o['id'])}" for o in opposite]
        answer = self._ask("\n".join(lines) + "\n")
        fills = [{"order_id": row[0], "price": row[1], "quantity": row[2]} for row in answer[1:]]
        return fills, answer[0][1]

    def uncross(self, orders: list[dict], low: int, high: int, reference: int) -> tuple[int | None, list[dict]]:
        lines = [f"UNCROSS {low} {high} {reference} {len(orders)}"]
        lines += [f"{o['id']} {'B' if o['side'] == 'buy' else 'S'} {o['limit_price']} {o['remaining']} {o['id']}" for o in orders]
        answer = self._ask("\n".join(lines) + "\n")
        price = answer[0][1] or None
        return price, [{"buy_id": row[0], "sell_id": row[1], "quantity": row[2]} for row in answer[1:]]


engine = Engine()


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _rows(conn: Connection, sql: str, params=()) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def _one(conn: Connection, sql: str, params=()) -> dict | None:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchone()


def price_limits(reference: int) -> tuple[int, int]:
    """The lowest and highest price a share may trade at today: a tenth below and above
    the last price of the session before."""
    move = reference * data.DAILY_PRICE_LIMIT_BPS // BPS
    return max(reference - move, 1), max(reference + move, 1)


def fee_due(value: int) -> int:
    """The fee on trades worth `value` kobo in all, rounded up to a whole kobo, so that
    splitting one trade into many tiny ones never makes the fee smaller."""
    return -(-value * (data.EXCHANGE_FEE_BPS + data.STAMP_DUTY_BPS) // BPS)


def _split_fee(fee: int) -> tuple[int, int]:
    """One fee divided between the exchange and the Government's stamp duty."""
    duty = fee * data.STAMP_DUTY_BPS // (data.EXCHANGE_FEE_BPS + data.STAMP_DUTY_BPS)
    return fee - duty, duty


def session_of(now: datetime) -> tuple:
    """The trading day `now` belongs to, and what the market is doing.

    A trading day runs from the close at 22:00 to the next close: an order placed at
    night is for the next day's opening auction."""
    lagos = clock.to_lagos(now)
    day = (lagos + timedelta(hours=24 - clock.MARKET_CLOSE.hour)).date()
    return day, clock.market_state(now)


# ---------------------------------------------------------------------------
# Setting up
# ---------------------------------------------------------------------------

def setup(conn: Connection, now: datetime) -> None:
    """Create the exchange's accounts and list every company's shares. Safe to run again."""
    for code, name in ((ESCROW, "Broad Street Exchange: held for open orders"), (FEES, "Broad Street Exchange")):
        if _one(conn, "SELECT 1 AS found FROM ledger_accounts WHERE code = %s", (code,)) is None:
            ledger.create_account(conn, kind="exchange", name=name, code=code)
    day, _ = session_of(now)
    unlisted = _rows(
        conn,
        "SELECT c.id, c.ticker, r.total_equity, r.shares_in_issue FROM companies c"
        " JOIN company_results r ON r.company_id = c.id"
        " AND r.period = (SELECT max(period) FROM company_results WHERE company_id = c.id)"
        " WHERE c.listed AND NOT EXISTS (SELECT 1 FROM market_instruments m WHERE m.company_id = c.id) ORDER BY c.ticker",
    )
    for company in unlisted:
        # TEMPORARY STAND-IN (the next slice has investors value each company from its
        # profits): a share is listed at the owners' funds behind it, and never below ₦1.
        listing = max(company["total_equity"] // company["shares_in_issue"], data.LOWEST_LISTING_PRICE_KOBO)
        conn.execute(
            "INSERT INTO market_instruments (company_id, asset, listing_price, reference_price, session_date)"
            " VALUES (%s, %s, %s, %s, %s)",
            (company["id"], f"SHR-{company['ticker']}", listing, listing, day),
        )


def _accounts(conn: Connection) -> dict:
    return {
        "held": ledger.account_id(conn, ESCROW), "fees": ledger.account_id(conn, FEES),
        "treasury": ledger.account_id(conn, ledger.TREASURY),
        # The game quarter now running: trades are recorded against it, so the stamp duty
        # on them counts as the Government's income of that quarter.
        "period": _one(conn, "SELECT last_closed_period + 1 AS period FROM world_state")["period"],
    }


# ---------------------------------------------------------------------------
# The trading day
# ---------------------------------------------------------------------------

def _instrument(conn: Connection, ticker: str) -> dict:
    """One share's row, locked: everything else touching this share waits its turn."""
    row = _one(
        conn,
        "SELECT m.*, c.ticker, c.name, (SELECT r.shares_in_issue FROM company_results r WHERE r.company_id = c.id"
        "   ORDER BY r.period DESC LIMIT 1) AS shares_in_issue"
        " FROM market_instruments m JOIN companies c ON c.id = m.company_id WHERE c.ticker = %s FOR UPDATE OF m",
        (ticker,),
    )
    if row is None:
        raise ExchangeError("There is no share with that code on the exchange.")
    return row


def _bring_up_to_date(conn: Connection, share: dict, now: datetime, accounts: dict) -> None:
    """Start a new trading day if one has begun, and run the opening auction once the market is open."""
    day, state = session_of(now)
    if share["session_date"] < day:
        # Yesterday's last price is what today's limits are measured from.
        reference = share["last_price"] or share["reference_price"]
        conn.execute("UPDATE market_instruments SET session_date = %s, reference_price = %s, auction_done = false,"
                     " updated_at = %s WHERE company_id = %s", (day, reference, now, share["company_id"]))
        share.update(session_date=day, reference_price=reference, auction_done=False)
        # Orders left waiting too long are handed back.
        stale = _rows(conn, "SELECT * FROM market_orders WHERE company_id = %s AND status = 'open' AND placed_at < %s"
                            " ORDER BY id FOR UPDATE", (share["company_id"], now - timedelta(days=data.ORDER_LIFE_DAYS)))
        for order in stale:
            _close(conn, order, share, accounts, now, "expired",
                   f"It waited {data.ORDER_LIFE_DAYS} days without being matched.")
    if state is clock.MarketState.OPEN and not share["auction_done"]:
        _run_auction(conn, share, now, accounts)
        conn.execute("UPDATE market_instruments SET auction_done = true WHERE company_id = %s", (share["company_id"],))
        share["auction_done"] = True


def _run_auction(conn: Connection, share: dict, now: datetime, accounts: dict) -> None:
    waiting = _rows(conn, "SELECT * FROM market_orders WHERE company_id = %s AND status = 'open' ORDER BY id FOR UPDATE",
                    (share["company_id"],))
    if not waiting:
        return
    low, high = price_limits(share["reference_price"])
    price, pairs = engine.uncross(waiting, low, high, share["reference_price"])
    if price is None:
        return
    if not low <= price <= high:
        raise EngineFailure("The engine proposed an auction price outside the day's limits.")
    by_id = {order["id"]: order for order in waiting}
    for pair in pairs:
        buy, sell = by_id.get(pair["buy_id"]), by_id.get(pair["sell_id"])
        if (buy is None or sell is None or buy["side"] != "buy" or sell["side"] != "sell" or pair["quantity"] <= 0
                or pair["quantity"] > min(buy["remaining"], sell["remaining"])
                or buy["limit_price"] < price or sell["limit_price"] > price):
            raise EngineFailure("The engine proposed an auction pairing that breaks the rules.")
        _settle(conn, share, buy, sell, price, pair["quantity"], now, accounts, in_auction=True)
    for order in by_id.values():
        if order["remaining"] == 0:
            _close(conn, order, share, accounts, now, "filled", None)


def open_market(conn: Connection, now: datetime) -> None:
    """Bring every share up to date: start the day and run the opening auction where due.
    Called by the server from time to time; each share is also brought up to date
    whenever anybody places or cancels an order in it."""
    accounts = _accounts(conn)
    for row in _rows(conn, "SELECT c.ticker FROM market_instruments m JOIN companies c ON c.id = m.company_id ORDER BY c.ticker"):
        with conn.transaction():
            _bring_up_to_date(conn, _instrument(conn, row["ticker"]), now, accounts)


# ---------------------------------------------------------------------------
# Settlement
# ---------------------------------------------------------------------------

def _settle(conn: Connection, share: dict, buy: dict, sell: dict, price: int, quantity: int, now: datetime,
            accounts: dict, *, in_auction: bool, taker_side: str | None = None) -> dict:
    """One trade: shares to the buyer, cash to the seller, fees to the exchange and the Government.
    All of it is one ledger transaction, so it happens completely or not at all."""
    value = price * quantity
    fees = {}
    rush = not in_auction and clock.in_closing_rush(now)
    for order in (buy, sell):
        order["value_filled"] += value
        # The full fee so far, less what the order has already paid or been let off.
        full = fee_due(order["value_filled"]) - order["fees_paid"] - order["fee_rebate"]
        rebate = full * data.RUSH_FEE_DISCOUNT_BPS // BPS if rush else 0     # fees are reduced in the Closing Rush
        fee = full - rebate
        order["fees_paid"] += fee
        order["fee_rebate"] += rebate
        order["remaining"] -= quantity
        fees[order["side"]] = fee
    buy["reserved"] -= value + fees["buy"]
    if buy["reserved"] < 0 or value - fees["sell"] <= 0:
        raise ExchangeError("That trade is too small to cover its fees.")

    exchange_part = _split_fee(fees["buy"])[0] + _split_fee(fees["sell"])[0]
    duty_part = _split_fee(fees["buy"])[1] + _split_fee(fees["sell"])[1]
    legs = [
        Leg(accounts["held"], -(value + fees["buy"])),
        Leg(sell["account_id"], value - fees["sell"]),
        Leg(accounts["fees"], exchange_part),
        Leg(accounts["treasury"], duty_part),
        Leg(accounts["held"], -quantity, share["asset"]),
        Leg(buy["account_id"], quantity, share["asset"]),
    ]
    transaction = ledger.post(
        conn, kind="share_trade", legs=[leg for leg in legs if leg.amount != 0],
        memo=f"{quantity:,} {share['name']} shares at ₦{price / 100:,.2f}", reference=f"order:{buy['id']}:{sell['id']}",
        period=accounts["period"],
    )
    for order in (buy, sell):
        conn.execute("UPDATE market_orders SET remaining = %s, value_filled = %s, fees_paid = %s, fee_rebate = %s, reserved = %s"
                     " WHERE id = %s", (order["remaining"], order["value_filled"], order["fees_paid"], order["fee_rebate"],
                                        order["reserved"], order["id"]))
    trade = {
        "company_id": share["company_id"], "price": price, "quantity": quantity, "buy_order_id": buy["id"],
        "sell_order_id": sell["id"], "buyer_account_id": buy["account_id"], "seller_account_id": sell["account_id"],
        "buyer_fee": fees["buy"], "seller_fee": fees["sell"], "in_auction": in_auction,
        "same_owner": buy["account_id"] == sell["account_id"], "session_date": share["session_date"],
        "taker_side": taker_side,
        "ledger_transaction": transaction, "traded_at": now,
    }
    columns = list(trade)
    conn.execute(f"INSERT INTO market_trades ({', '.join(columns)}) VALUES ({', '.join(['%s'] * len(columns))})",
                 list(trade.values()))
    conn.execute("UPDATE market_instruments SET last_price = %s, updated_at = %s WHERE company_id = %s",
                 (price, now, share["company_id"]))
    share["last_price"] = price
    return trade


def _close(conn: Connection, order: dict, share: dict, accounts: dict, now: datetime, status: str, reason: str | None) -> None:
    """Close an order and hand back whatever the exchange still holds for it."""
    if order["side"] == "buy" and order["reserved"] > 0:
        ledger.transfer(conn, payer=accounts["held"], receiver=order["account_id"], amount=order["reserved"],
                        kind="order_release", memo=f"Cash handed back: order for {share['name']} shares",
                        reference=f"order:{order['id']}")
    if order["side"] == "sell" and order["remaining"] > 0:
        ledger.transfer(conn, payer=accounts["held"], receiver=order["account_id"], amount=order["remaining"],
                        asset=share["asset"], kind="order_release",
                        memo=f"Shares handed back: order to sell {share['name']}", reference=f"order:{order['id']}")
    conn.execute("UPDATE market_orders SET status = %s, reserved = 0, closed_reason = %s, closed_at = %s WHERE id = %s",
                 (status, reason, now, order["id"]))
    order.update(status=status, reserved=0, closed_reason=reason)


# ---------------------------------------------------------------------------
# Placing and cancelling orders
# ---------------------------------------------------------------------------

def place_order(conn: Connection, *, account: UUID | str, ticker: str, side: str, kind: str, quantity: int,
                limit_price: int | None, now: datetime) -> dict:
    """Place an order. Returns the order as it stands afterwards, and the trades it made.

    Raises ExchangeError, with a message for the player, if the order cannot be accepted.
    Nothing is left half-done: either the whole order is recorded or none of it.
    """
    if side not in ("buy", "sell") or kind not in ("limit", "market"):
        raise ExchangeError("An order is to buy or to sell, at a price you choose or at the best price available.")
    if not isinstance(quantity, int) or isinstance(quantity, bool) or quantity <= 0:
        raise ExchangeError("The number of shares must be a whole number above zero.")
    if kind == "limit" and (not isinstance(limit_price, int) or isinstance(limit_price, bool) or limit_price <= 0):
        raise ExchangeError("The price must be above zero.")
    if kind == "market":
        limit_price = None

    with conn.transaction():
        owner = _one(conn, "SELECT kind FROM ledger_accounts WHERE id = %s", (account,))
        if owner is None or owner["kind"] not in TRADER_KINDS:
            raise ExchangeError("That account cannot trade on the exchange.")
        accounts = _accounts(conn)
        share = _instrument(conn, ticker)
        if owner["kind"] in ("player", "empire"):
            from simulation import newsroom          # Stage 10: no trading around one's own story
            newsroom.check_trade(conn, account, share["company_id"], now)
        _bring_up_to_date(conn, share, now, accounts)
        _, state = session_of(now)
        low, high = price_limits(share["reference_price"])
        until = paused_until(conn, now)
        if until is not None:
            raise ExchangeError(
                f"Trading is paused until {clock.to_lagos(until):%H:%M} Lagos time after a sharp fall across the whole "
                "market. You can still cancel orders that are waiting.")

        if quantity > share["shares_in_issue"]:
            raise ExchangeError("That is more shares than the company has in issue.")
        if kind == "limit" and not low <= limit_price <= high:
            raise ExchangeError(
                f"Today this share can trade only between ₦{low / 100:,.2f} and ₦{high / 100:,.2f}: "
                "no more than a tenth above or below yesterday's last price.")
        if kind == "market" and state is not clock.MarketState.OPEN:
            raise ExchangeError("An order at the best price available can only be placed while the market is open "
                                "(12:00 to 22:00 Lagos time). Until then, choose your price.")
        if owner["kind"] == "player":
            waiting = _one(conn, "SELECT count(*) AS n FROM market_orders WHERE account_id = %s AND status = 'open'", (account,))
            if waiting["n"] >= data.MOST_OPEN_ORDERS:
                raise ExchangeError(f"You already have {data.MOST_OPEN_ORDERS} orders waiting. Cancel one first.")

        # 1. Reserve: the exchange holds the cash or the shares for as long as the order stands.
        reserved = 0
        try:
            if side == "buy":
                most = (limit_price if kind == "limit" else high) * quantity
                reserved = most + fee_due(most)
                if reserved > MAX_AMOUNT:
                    raise ExchangeError("That order is too large.")
                ledger.transfer(conn, payer=account, receiver=accounts["held"], amount=reserved, kind="order_reserve",
                                memo=f"Cash held for an order to buy {share['name']} shares")
            else:
                ledger.transfer(conn, payer=account, receiver=accounts["held"], amount=quantity, asset=share["asset"],
                                kind="order_reserve", memo=f"Shares held for an order to sell {share['name']}")
        except ledger.InsufficientFunds:
            if side == "buy":
                raise ExchangeError(f"You do not have enough cash. This order needs ₦{reserved / 100:,.2f} "
                                    "including fees.") from None
            raise ExchangeError("You do not own that many shares of this company.") from None

        order = _one(
            conn,
            "INSERT INTO market_orders (account_id, company_id, side, kind, limit_price, quantity, remaining, reserved, placed_at)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING *",
            (account, share["company_id"], side, kind, limit_price, quantity, quantity, reserved, now),
        )

        # In the Closing Rush every large order is shown to everybody as it arrives: its size, never its owner.
        worth = (limit_price or share["reference_price"]) * quantity
        if owner["kind"] == "player" and clock.in_closing_rush(now) and worth >= data.LARGE_ORDER_NAIRA * 100:
            conn.execute("INSERT INTO market_large_orders (company_id, session_date, side, quantity, value, shown_at)"
                         " VALUES (%s, %s, %s, %s, %s, %s)", (share["company_id"], share["session_date"], side, quantity, worth, now))

        # 2. Match, while the market is open. At other times the order waits for the opening auction.
        trades: list[dict] = []
        if state is clock.MarketState.OPEN:
            opposite = _rows(
                conn,
                "SELECT * FROM market_orders WHERE company_id = %s AND status = 'open' AND side = %s AND id <> %s"
                " ORDER BY id FOR UPDATE",
                (share["company_id"], "sell" if side == "buy" else "buy", order["id"]),
            )
            fills, left = engine.match(side, limit_price, quantity, opposite, low, high)
            by_id = {o["id"]: o for o in opposite}
            _check(fills, left, order, by_id, low, high)
            for fill in fills:
                other = by_id[fill["order_id"]]
                buy, sell = (order, other) if side == "buy" else (other, order)
                trades.append(_settle(conn, share, buy, sell, fill["price"], fill["quantity"], now, accounts,
                                      in_auction=False, taker_side=side))
                if other["remaining"] == 0:
                    _close(conn, other, share, accounts, now, "filled", None)

        if trades:
            _pause_if_the_market_is_falling(conn, now)

        # 3. Whatever is left waits in the book, or is handed back.
        if order["remaining"] == 0:
            _close(conn, order, share, accounts, now, "filled", None)
        elif kind == "market":
            _close(conn, order, share, accounts, now, "cancelled",
                   "No more shares were on offer inside today's price limits." if side == "buy"
                   else "No more buyers were waiting inside today's price limits.")
        elif order["side"] == "buy" and trades:
            # A buyer who paid less than their limit gets the difference back at once; the
            # exchange keeps only what the shares still wanted could cost.
            needed = order["limit_price"] * order["remaining"]
            needed += fee_due(order["value_filled"] + needed) - order["fees_paid"] - order["fee_rebate"]
            if order["reserved"] > needed:
                ledger.transfer(conn, payer=accounts["held"], receiver=account, amount=order["reserved"] - needed,
                                kind="order_release", memo=f"Cash handed back: {share['name']} shares bought for less than your limit",
                                reference=f"order:{order['id']}")
                order["reserved"] = needed
                conn.execute("UPDATE market_orders SET reserved = %s WHERE id = %s", (needed, order["id"]))
        return {"order": order, "trades": trades}


# ---------------------------------------------------------------------------
# The pause after a sharp fall across the whole market
# ---------------------------------------------------------------------------

def market_move_bps(conn: Connection) -> int:
    """How far the whole market has moved today: every company at its latest price against
    the price the day's limits are measured from, each counted by its size."""
    row = _one(
        conn,
        "SELECT coalesce(sum(coalesce(m.last_price, m.reference_price)::numeric * v.shares), 0) AS now,"
        "       coalesce(sum(m.reference_price::numeric * v.shares), 0) AS before"
        " FROM market_instruments m JOIN LATERAL (SELECT r.shares_in_issue AS shares FROM company_results r"
        "   WHERE r.company_id = m.company_id ORDER BY r.period DESC LIMIT 1) v ON true")
    return int((row["now"] - row["before"]) * BPS / row["before"]) if row["before"] else 0


def paused_until(conn: Connection, now: datetime) -> datetime | None:
    row = _one(conn, "SELECT paused_until FROM market_status")
    return row["paused_until"] if row and row["paused_until"] and row["paused_until"] > now else None


def _pause_if_the_market_is_falling(conn: Connection, now: datetime) -> None:
    day, _ = session_of(now)
    if market_move_bps(conn) > -data.MARKET_PAUSE_FALL_BPS:
        return
    until = now + timedelta(minutes=data.MARKET_PAUSE_MINUTES)
    paused = conn.execute(
        "UPDATE market_status SET paused_until = %s, paused_session = %s"
        " WHERE paused_session IS DISTINCT FROM %s", (until, day, day)).rowcount          # once a day
    if paused:
        conn.execute(
            "INSERT INTO market_reasons (company_id, session_date, happened_at, reason) VALUES (NULL, %s, %s, %s)",
            (day, now, f"The whole market fell more than {data.MARKET_PAUSE_FALL_BPS // 100}% in a day. Trading was paused "
                       f"for {data.MARKET_PAUSE_MINUTES} minutes so that everybody could take stock."))


def relist(conn: Connection, company_id, price: int, now: datetime) -> None:
    """Move the starting price of a share that has NEVER traded to what it is now thought to be
    worth. Once a share has traded, only trading moves its price."""
    before = _one(conn, "SELECT m.listing_price, -b.balance AS shares FROM market_instruments m JOIN assets a ON a.code = m.asset"
                        " JOIN ledger_balances b ON b.account_id = a.issuer_account_id AND b.asset = m.asset"
                        " WHERE m.company_id = %s AND m.last_price IS NULL", (company_id,))
    if before is None:
        return
    conn.execute("UPDATE market_instruments SET listing_price = %s, reference_price = %s, updated_at = %s"
                 " WHERE company_id = %s AND last_price IS NULL", (price, price, now, company_id))
    # Once the index's base is kept on record, it moves with the starting price, so that
    # a share standing at its starting price still counts as "unchanged since listing".
    conn.execute("UPDATE market_status SET index_base = index_base + %s WHERE index_base IS NOT NULL",
                 ((price - before["listing_price"]) * before["shares"],))


def cancel_all_in(conn: Connection, company_id, now: datetime, reason: str) -> int:
    """Cancel every waiting order in one share, whoever placed it, and hand back what was held.
    Done when the share itself changes: new shares issued, or a split."""
    ticker = _one(conn, "SELECT ticker FROM companies WHERE id = %s", (company_id,))["ticker"]
    if _one(conn, "SELECT 1 AS found FROM market_instruments WHERE company_id = %s", (company_id,)) is None:
        return 0
    accounts = _accounts(conn)
    share = _instrument(conn, ticker)
    orders = _rows(conn, "SELECT * FROM market_orders WHERE company_id = %s AND status = 'open' ORDER BY id FOR UPDATE", (company_id,))
    for order in orders:
        _close(conn, order, share, accounts, now, "cancelled", reason)
    return len(orders)


def reprice(conn: Connection, company_id, price: int, now: datetime, reason: str) -> None:
    """Set a share's price by rule, not by a trade. Only for a change to the share itself
    (new shares issued, a split): the reason is written down for "Why?"."""
    day, _ = session_of(now)
    price = max(price, 1)
    conn.execute("UPDATE market_instruments SET reference_price = %s, last_price = CASE WHEN last_price IS NULL THEN NULL ELSE %s END,"
                 " updated_at = %s WHERE company_id = %s", (price, price, now, company_id))
    conn.execute("INSERT INTO market_reasons (company_id, session_date, happened_at, reason) VALUES (%s, %s, %s, %s)",
                 (company_id, day, now, reason))


def allow_index_for(conn: Connection, added_value: int) -> None:
    """Raise the figure the BSX 50 is measured against, in step with `added_value` kobo of new
    shares coming to the market, so that new shares alone never move the index. Call it
    BEFORE the shares are issued."""
    row = _one(
        conn,
        "SELECT coalesce(sum(coalesce(m.last_price, m.reference_price)::numeric * -b.balance), 0) AS value,"
        "       coalesce(sum(m.listing_price::numeric * -b.balance), 0) AS listed"
        " FROM market_instruments m JOIN assets a ON a.code = m.asset"
        " JOIN ledger_balances b ON b.account_id = a.issuer_account_id AND b.asset = m.asset")
    status = _one(conn, "SELECT index_base FROM market_status FOR UPDATE")
    base = status["index_base"] or row["listed"]
    if not base:
        return
    if row["value"] > 0 and added_value > 0:
        base = base * (row["value"] + added_value) // row["value"]
    conn.execute("UPDATE market_status SET index_base = %s", (int(base),))


def list_company(conn: Connection, company_id, price: int, now: datetime) -> None:
    """Bring a company's shares to the exchange for the first time, at the price of its first sale to the public."""
    company = _one(conn, "SELECT id, ticker, share_asset FROM companies WHERE id = %s", (company_id,))
    day, _ = session_of(now)
    shares = ledger.amount_in_existence(conn, company["share_asset"])
    status = _one(conn, "SELECT index_base FROM market_status")
    if status and status["index_base"]:
        allow_index_for(conn, price * shares)
    conn.execute("INSERT INTO market_instruments (company_id, asset, listing_price, reference_price, session_date)"
                 " VALUES (%s, %s, %s, %s, %s)", (company["id"], company["share_asset"], price, price, day))
    conn.execute("UPDATE companies SET listed = true WHERE id = %s", (company["id"],))      # a private company is listed from now on


def withdraw(conn: Connection, account_ids: list, now: datetime, reason: str) -> int:
    """Cancel every waiting order of the given accounts, share by share. Returns how many."""
    accounts = _accounts(conn)
    count = 0
    tickers = _rows(conn, "SELECT DISTINCT c.ticker FROM market_orders o JOIN companies c ON c.id = o.company_id"
                          " WHERE o.status = 'open' AND o.account_id = ANY(%s) ORDER BY c.ticker", (account_ids,))
    for row in tickers:
        share = _instrument(conn, row["ticker"])
        for order in _rows(conn, "SELECT * FROM market_orders WHERE company_id = %s AND status = 'open' AND account_id = ANY(%s)"
                                 " ORDER BY id FOR UPDATE", (share["company_id"], account_ids)):
            _close(conn, order, share, accounts, now, "cancelled", reason)
            count += 1
    return count


def why(conn: Connection, ticker: str, now: datetime) -> dict | None:
    """Why a share's price is where it is today, from what is on record: who was in a hurry
    to trade, what the investors did, and what they think it is worth."""
    share = _one(conn, "SELECT m.*, c.ticker, c.name FROM market_instruments m JOIN companies c ON c.id = m.company_id"
                       " WHERE c.ticker = %s", (ticker,))
    if share is None:
        return None
    day, _ = session_of(now)
    today = share["session_date"] == day
    flow = _one(
        conn,
        "SELECT coalesce(sum(quantity) FILTER (WHERE taker_side = 'buy'), 0)::bigint AS bought,"
        "       coalesce(sum(quantity) FILTER (WHERE taker_side = 'sell'), 0)::bigint AS sold,"
        "       coalesce(sum(quantity) FILTER (WHERE in_auction), 0)::bigint AS auction,"
        "       count(*) AS trades, min(price) AS lowest, max(price) AS highest"
        " FROM market_trades WHERE company_id = %s AND session_date = %s", (share["company_id"], day))
    reference = share["reference_price"] if today else (share["last_price"] or share["reference_price"])
    last = share["last_price"] if today and flow["trades"] else None
    move = (last - reference) * BPS // reference if last else 0

    if not flow["trades"]:
        summary = "It has not traded today, so its price has not moved."
    else:
        naira = lambda kobo: f"₦{kobo / 100:,.2f}"            # noqa: E731
        if abs(move) < 10:
            direction = f"The price is where it finished the day before, at {naira(last)}."
        else:
            direction = (f"The price is {'up' if move > 0 else 'down'} {abs(move) / 100:.1f}% today, "
                         f"from {naira(reference)} to {naira(last)}.")
        bought, sold = flow["bought"], flow["sold"]
        if bought > sold * 6 // 5:
            pressure = (f" There was more buying than selling: buyers in a hurry took {bought:,} shares from the sellers "
                        f"waiting, paying up to {naira(flow['highest'])}, while sellers in a hurry sold {sold:,}.")
        elif sold > bought * 6 // 5:
            pressure = (f" There was more selling than buying: sellers in a hurry sold {sold:,} shares to the buyers "
                        f"waiting, accepting as little as {naira(flow['lowest'])}, while buyers in a hurry took {bought:,}.")
        elif bought or sold:
            pressure = f" Buying and selling were evenly matched: {bought:,} shares bought in a hurry, {sold:,} sold."
        else:
            pressure = f" All {flow['auction']:,} shares traded in the opening auction, at one price."
        summary = direction + pressure
    worth = _one(conn, "SELECT * FROM company_valuations WHERE company_id = %s ORDER BY period DESC LIMIT 1", (share["company_id"],))
    return {
        "ticker": share["ticker"], "name": share["name"], "summary": summary, "move_bps": move,
        "reference_price": reference, "last_price": last,
        "bought_in_a_hurry": flow["bought"], "sold_in_a_hurry": flow["sold"],
        "reasons": [r["reason"] for r in _rows(
            conn, "SELECT reason FROM market_reasons WHERE (company_id = %s OR company_id IS NULL) AND session_date = %s"
                  " ORDER BY id DESC LIMIT 8", (share["company_id"], day))],
        "valuation_period": worth["period"] if worth else None,
        "valuation_reasons": worth["reasons"] if worth else [],
    }


def _check(fills: list[dict], left: int, order: dict, by_id: dict, low: int, high: int) -> None:
    """Never act on the engine's word alone: every pairing must obey the rules, or nothing is settled."""
    seen: set = set()
    traded = 0
    for fill in fills:
        other = by_id.get(fill["order_id"])
        crosses = order["limit_price"] is None or (
            fill["price"] <= order["limit_price"] if order["side"] == "buy" else fill["price"] >= order["limit_price"])
        if (other is None or fill["order_id"] in seen or fill["quantity"] <= 0 or fill["quantity"] > other["remaining"]
                or fill["price"] != other["limit_price"] or not low <= fill["price"] <= high or not crosses):
            raise EngineFailure("The engine proposed a pairing that breaks the rules. Nothing was traded.")
        seen.add(fill["order_id"])
        traded += fill["quantity"]
    if traded + left != order["quantity"] or left < 0:
        raise EngineFailure("The engine's figures do not add up. Nothing was traded.")


def cancel_order(conn: Connection, *, account: UUID | str, order_id: int, now: datetime) -> dict:
    """Cancel an order that is still waiting. Only whoever placed it can."""
    with conn.transaction():
        found = _one(conn, "SELECT o.company_id, c.ticker FROM market_orders o JOIN companies c ON c.id = o.company_id"
                           " WHERE o.id = %s AND o.account_id = %s", (order_id, account))
        if found is None:
            raise ExchangeError("You have no order with that number.")
        accounts = _accounts(conn)
        share = _instrument(conn, found["ticker"])          # the share first, then the order: always the same sequence
        _bring_up_to_date(conn, share, now, accounts)
        order = _one(conn, "SELECT * FROM market_orders WHERE id = %s FOR UPDATE", (order_id,))
        if order["status"] != "open":
            raise ExchangeError("That order is no longer waiting: it has been filled, cancelled or has expired.")
        _close(conn, order, share, accounts, now, "cancelled", "Cancelled by whoever placed it.")
        return order


# ---------------------------------------------------------------------------
# Reading the market
# ---------------------------------------------------------------------------

def quote(conn: Connection, ticker: str, now: datetime, *, depth: int = 5) -> dict | None:
    """What anybody may see of one share: its last price, today's limits, and the best prices waiting."""
    share = _one(conn, "SELECT m.*, c.ticker, c.name FROM market_instruments m JOIN companies c ON c.id = m.company_id"
                       " WHERE c.ticker = %s", (ticker,))
    if share is None:
        return None
    day, state = session_of(now)
    # If today's first order has not yet arrived, the day's reference is still to be rolled forward.
    reference = (share["last_price"] or share["reference_price"]) if share["session_date"] < day else share["reference_price"]
    low, high = price_limits(reference)

    def levels(side: str, best_first: str) -> list[dict]:
        return _rows(conn, "SELECT limit_price AS price, sum(remaining)::bigint AS quantity, count(*) AS orders FROM market_orders"
                           f" WHERE company_id = %s AND status = 'open' AND side = %s AND limit_price BETWEEN %s AND %s"
                           f" GROUP BY limit_price ORDER BY limit_price {best_first} LIMIT %s",
                     (share["company_id"], side, low, high, depth))

    return {
        "ticker": share["ticker"], "name": share["name"], "last_price": share["last_price"],
        "reference_price": reference, "lowest_today": low, "highest_today": high, "state": state.value,
        "bids": levels("buy", "DESC"), "offers": levels("sell", "ASC"),
        "trades": _rows(conn, "SELECT price, quantity, in_auction, traded_at FROM market_trades WHERE company_id = %s"
                              " ORDER BY id DESC LIMIT 20", (share["company_id"],)),
    }


def orders_of(conn: Connection, account: UUID | str, *, limit: int = 50) -> list[dict]:
    return _rows(conn, "SELECT o.id, c.ticker, c.name, o.side, o.kind, o.limit_price, o.quantity, o.remaining, o.reserved,"
                       " o.value_filled, o.fees_paid, o.status, o.closed_reason, o.placed_at, o.closed_at"
                       " FROM market_orders o JOIN companies c ON c.id = o.company_id WHERE o.account_id = %s"
                       " ORDER BY (o.status = 'open') DESC, o.id DESC LIMIT %s", (account, limit))


def holdings_of(conn: Connection, account: UUID | str) -> list[dict]:
    """The shares an account owns outright, and those the exchange is holding for its sell orders."""
    return _rows(
        conn,
        "SELECT c.ticker, c.name, coalesce(b.balance, 0)::bigint AS shares,"
        "   coalesce((SELECT sum(o.remaining) FROM market_orders o WHERE o.account_id = %s AND o.company_id = c.id"
        "     AND o.side = 'sell' AND o.status = 'open'), 0)::bigint AS held_for_orders,"
        "   m.last_price, m.reference_price"
        " FROM market_instruments m JOIN companies c ON c.id = m.company_id"
        " LEFT JOIN ledger_balances b ON b.asset = m.asset AND b.account_id = %s"
        " WHERE coalesce(b.balance, 0) > 0 OR EXISTS (SELECT 1 FROM market_orders o WHERE o.account_id = %s"
        "   AND o.company_id = c.id AND o.side = 'sell' AND o.status = 'open') ORDER BY c.ticker",
        (account, account, account),
    )


def check_books(conn: Connection) -> list[str]:
    """What the exchange holds must be exactly what its open orders say it holds. An empty list means it is."""
    problems = []
    held = ledger.account_id(conn, ESCROW)
    cash = ledger.balance(conn, held)
    owed = _one(conn, "SELECT coalesce(sum(reserved), 0)::bigint AS total FROM market_orders WHERE status = 'open'")["total"]
    if cash != owed:
        problems.append(f"The exchange holds {cash} kobo for open orders but they account for {owed}.")
    shares = _rows(
        conn,
        "SELECT m.asset, coalesce(b.balance, 0)::bigint AS held,"
        "   coalesce((SELECT sum(o.remaining) FROM market_orders o WHERE o.company_id = m.company_id AND o.side = 'sell'"
        "     AND o.status = 'open'), 0)::bigint AS owed"
        " FROM market_instruments m LEFT JOIN ledger_balances b ON b.asset = m.asset AND b.account_id = %s", (held,))
    for row in shares:
        if row["held"] != row["owed"]:
            problems.append(f"The exchange holds {row['held']} of {row['asset']} but open sell orders account for {row['owed']}.")
    return problems
