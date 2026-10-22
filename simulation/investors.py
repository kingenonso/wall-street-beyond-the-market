"""The computer-run investors (design document, sections 4 and 11).

Three kinds of investor own the companies' shares when the world begins: the
founders, the pension funds and the small investors. They keep orders waiting
on the exchange, so that a player always has somebody to trade with, and they
are why prices move even when no player is trading.

How one investor decides, in plain words:

  1. It starts from what the company is worth: the public figure worked out
     from the filed accounts (see valuation.py).
  2. It takes its own view of that figure, a little above or below, different
     each trading day. Small investors' views wander most; founders' least.
  3. Small investors also mark a share up or down on the day's news.
  4. Whoever has been buying from it or selling to it moves its prices: after
     selling a lot it asks more, after buying a lot it offers less. Half of
     that fades each trading day. This is how buying pressure raises a price.
  5. Around the resulting price it keeps a few orders to buy just below and a
     few to sell just above.
  6. A share may not move more than a tenth in a day. If every investor values a
     share beyond that limit, nobody would trade inside it; the exchange then
     moves the price to the limit, once a day, so that it reaches its worth in
     steps instead of standing still for ever.

Where two investors' views overlap, they trade with each other.

An investor's own view comes from the world's secret, so nobody outside the
server can know it in advance. Everything else it uses is public. Buying from
an investor always costs more than selling straight back to it, so pushing a
price up and down again loses money; it cannot be used to milk them.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from psycopg import Connection
from psycopg.rows import dict_row

from simulation import clock, events, exchange, ledger, valuation
from simulation import world_data as data
from simulation.fortune import fortune_bps
from simulation.money import BPS, naira

WITHDRAWN = "Withdrawn while the investor thinks again."


def _rows(conn: Connection, sql: str, params=()) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def accounts(conn: Connection) -> dict:
    """The investors' accounts: code -> id."""
    return {r["code"]: r["id"] for r in _rows(
        conn, "SELECT code, id FROM ledger_accounts WHERE code = ANY(%s)", (list(data.INVESTORS),))}


def order_value(market_value: int) -> int:
    """How much one of an investor's waiting orders is worth, in kobo: larger for a larger company."""
    least, most = (naira(n) for n in data.ORDER_VALUE_LIMITS_NAIRA)
    return min(max(market_value * data.ORDER_VALUE_SHARE_PPM // 1_000_000, least), most)


def ladder(centre: int, margin_bps: int, orders: int, low: int, high: int) -> tuple[list[int], list[int]]:
    """The prices an investor keeps orders at: to buy, just below its price; to sell, just above.
    Nothing outside the day's limits, and never a buying price at or above a selling price."""
    bids, offers = [], []
    for step in range(orders):
        away = margin_bps + step * data.ORDER_STEP_BPS
        bid = centre * (BPS - away) // BPS
        offer = -(-centre * (BPS + away) // BPS)                 # rounded up, so that it is never below the buying price
        if low <= bid <= high and bid not in bids:
            bids.append(bid)
        if low <= offer <= high and offer not in offers:
            offers.append(offer)
    if bids and offers and max(bids) >= min(offers):
        offers = [price for price in offers if price > max(bids)]
    return bids, offers


def _mood_from_todays_news(conn: Connection, companies: list[dict], period: int, day: int) -> dict:
    """What small investors make of events that have already happened this quarter: a share of
    each event's effect on the company's sales. Events still to come play no part."""
    happened = [e for e in events.load(conn, period) if e["day"] <= day]
    mood: dict = {}
    for company in companies:
        effect = events.company_effects(happened, company)
        change = (effect["sales_bps"] - BPS) * data.EVENT_MOOD_BPS // BPS
        change = min(max(change, -data.MOST_EVENT_MOOD_BPS), data.MOST_EVENT_MOOD_BPS)
        if change:
            mood[company["id"]] = (change, effect["events"][-1]["kind"])
    return mood


_EVENT_WORDS = {
    "flood": "a flood", "power_failure": "power failures", "security_incident": "a security incident",
    "port_disruption": "port disruption", "pipeline_incident": "a pipeline incident", "drought": "drought",
    "local_boom": "brisk business where it is based", "sector_strike": "a strike across its industry",
    "sector_demand_surge": "a jump in demand for its industry", "good_harvest": "a good harvest",
    "network_outage": "a network outage", "new_competition": "new competition", "company_strike": "a strike by its staff",
    "scandal": "a scandal", "contract_win": "a contract it won", "factory_fire": "a fire at one of its sites",
    "product_recall": "a product recall", "new_product": "a new product", "story": "a widely read news story",
}


def act(conn: Connection, now: datetime, *, force: bool = False) -> int:
    """Let the investors look at the market and renew their orders. Returns how many orders they placed.

    Safe to call as often as you like, and from several servers: it does its work at most
    once every five minutes while the market is open, and once before each day's opening.
    """
    day, state = exchange.session_of(now)
    with conn.transaction():
        status = _rows(conn, "SELECT * FROM market_status FOR UPDATE")[0]
        world = _rows(conn, "SELECT world_start, weeks_ahead, last_closed_period, fortune_seed FROM world_state")
        if not world or exchange.paused_until(conn, now) is not None:
            return 0
        world = world[0]
        if not force:
            if state is clock.MarketState.OPEN:
                last = status["investors_acted"]
                if last is not None and now - last < timedelta(seconds=data.INVESTOR_REFRESH_SECONDS):
                    return 0
            elif status["acted_session"] == day:
                return 0                              # before the open, once is enough: the orders wait for the auction
        conn.execute("UPDATE market_status SET investors_acted = %s, acted_session = %s", (now, day))

    exchange.open_market(conn, now)                   # start the day, run the auction if it is due
    seed = world["fortune_seed"]
    who = accounts(conn)  # noqa
    worth = valuation.latest(conn)
    shares = _rows(conn, "SELECT c.id, c.ticker, c.sector, c.headquarters FROM market_instruments m"
                         " JOIN companies c ON c.id = m.company_id WHERE m.halted_reason IS NULL ORDER BY c.ticker")
    today = clock.game_date(now, clock.effective_start(world["world_start"], world["weeks_ahead"]))
    # Stage 10: each kind of investor reads the news at its own pace (some at once, some a day or two late, the founders
    # not at all), and players' widely read stories nudge how they value a company for a few days.
    from simulation import newsroom
    game_days_a_day = clock.GAME_DAYS_PER_QUARTER // clock.REAL_DAYS_PER_QUARTER
    moods: dict = {}
    nudged: dict = {}
    for lag in {v for v in data.NEWS_LAG_DAYS.values() if v is not None}:
        seen = today.day_of_quarter - lag * game_days_a_day if today else 0
        moods[lag] = _mood_from_todays_news(conn, shares, world["last_closed_period"] + 1, seen) if today and seen >= 1 else {}
        nudged[lag] = newsroom.nudges_today(conn, day, lag_days=lag)
    day_number = day.toordinal()
    placed = 0
    from simulation import abroad
    foreign_tilt = abroad.tilt_now(conn)
    # How much more the foreign investors may push today: worked out once, and lowered as they trade.
    foreign_budget = abroad.day_budget_left(conn, who[abroad.FOREIGN], day) if abroad.FOREIGN in who else 0
    foreign_left = foreign_budget
    first_new_trade = _rows(conn, "SELECT coalesce(max(id), 0) AS id FROM market_trades")[0]["id"] if foreign_budget > 0 else 0

    from simulation import corporate                  # (it needs this module's neighbours too)
    # Stage 9: each kind of investor has its own temper about a share's recent move (some chase it, some lean
    # against it), and small investors bid up a heavily shorted share that is rising (a squeeze).
    from simulation import lending, marketview
    recent = marketview.recent_closes(conn, 6)
    shorted = lending.short_interest(conn) if _rows(conn, "SELECT to_regclass('short_positions') IS NOT NULL AS ok")[0]["ok"] else {}
    open_bids = {b["target_company_id"]: b for b in _rows(conn, "SELECT * FROM takeovers WHERE status = 'open'")}

    for company in shares:
        if foreign_budget > 0:
            foreign_left = foreign_budget - _rows(
                conn, "SELECT coalesce(sum(price * quantity), 0)::bigint AS v FROM market_trades WHERE id > %s"
                      " AND (buyer_account_id = %s OR seller_account_id = %s)",
                (first_new_trade, who[abroad.FOREIGN], who[abroad.FOREIGN]))[0]["v"]
        value = worth.get(company["id"])
        if value is None:
            continue
        if company["id"] in open_bids:
            # A takeover offer is open: investors price in what it is expected to pay them.
            expected = corporate.expected_value(conn, open_bids[company["id"]], value["value_per_share"])
            if expected:
                value = {**value, "value_per_share": expected}
        # One share at a time, each all-or-nothing, so players' orders in other shares never wait on this.
        with conn.transaction():
            share = exchange._instrument(conn, company["ticker"])
            # A share that has never traded starts from what it is now thought to be worth.
            if share["last_price"] is None and share["reference_price"] != value["value_per_share"]:
                exchange.relist(conn, share["company_id"], value["value_per_share"], now)
                share["reference_price"] = value["value_per_share"]
            low, high = exchange.price_limits(share["reference_price"])
            size = order_value(value["value_per_share"] * value["shares_in_issue"])
            books = {b["account_id"]: b for b in _rows(conn, "SELECT * FROM investor_books WHERE company_id = %s", (share["company_id"],))}

            # What each investor thinks the share is worth today, before the day's price limits are applied.
            views: dict = {}
            for code in data.INVESTORS:
                if code not in who:
                    continue                        # (a world made before foreign investors existed)
                label, own_view, margin, orders, size_percent = data.INVESTORS[code]
                account = who[code]
                book = books.get(account)
                one_order = size * size_percent // 100
                # What past buying and selling has done to this investor's prices: today's in full,
                # earlier days' fading by half each trading day.
                if book is None:
                    carried = 0
                elif book["session_date"] == day:
                    carried = book["carried_bps"]
                else:
                    earlier = _impact(conn, account, share["company_id"], book["session_date"], value, one_order)[0]
                    carried = _within(book["carried_bps"] + earlier) // 2
                todays, net_sold = _impact(conn, account, share["company_id"], day, value, one_order)
                pressure = _within(carried + todays)
                view = fortune_bps(seed, f"investor:{code}:{share['ticker']}", day_number, "view", own_view)
                view += temper_bps(code, recent.get(share["company_id"]), shorted.get(share["company_id"], 0))
                lag = data.NEWS_LAG_DAYS.get(code)
                news, cause = moods[lag].get(share["company_id"], (0, None)) if lag is not None else (0, None)
                story = nudged[lag].get(share["company_id"], 0) if lag is not None else 0
                if story:
                    news, cause = news + story, (cause if abs(news) > abs(story) else "story")
                if code == abroad.FOREIGN and foreign_tilt and foreign_left > 0:
                    # Keen to bring money in (or to take it out) this quarter, until they have traded their share of the day:
                    # after that their orders only wait.
                    view += foreign_tilt
                wanted_centre = value["value_per_share"] * (BPS + view) // BPS * (BPS + news) // BPS * (BPS + pressure) // BPS
                views[code] = (wanted_centre, carried, todays, net_sold, news, cause)

            # If every investor thinks the share is worth less than the lowest price allowed today (or more
            # than the highest), nobody would trade inside the limits and the price could never move again.
            # The exchange then moves the price to the limit: once a trading day, and only if it has not traded.
            if share["last_price"] is not None and share.get("marked_session") != day:
                all_below = all(v[0] < low for v in views.values())
                all_above = all(v[0] > high for v in views.values())
                traded = _rows(conn, "SELECT 1 FROM market_trades WHERE company_id = %s AND session_date = %s LIMIT 1", (share["company_id"], day))
                if (all_below or all_above) and not traded:
                    limit = low if all_below else high
                    exchange.reprice(
                        conn, share["company_id"], limit, now,
                        f"Every investor valued the share {'below the lowest' if all_below else 'above the highest'} price allowed today, "
                        f"so nobody would trade inside the limits. The exchange moved the price to that limit, "
                        f"₦{limit / 100:,.2f}: a tenth {'below' if all_below else 'above'} the day before.")
                    conn.execute("UPDATE market_instruments SET marked_session = %s WHERE company_id = %s", (day, share["company_id"]))
                    share["reference_price"] = share["last_price"] = limit
                    low, high = exchange.price_limits(limit)

            # Not always in the same order, so no one investor always gets the first word.
            turn = sorted(views, key=lambda code: fortune_bps(seed, f"turn:{code}:{share['ticker']}", day_number, "order", 10_000))
            for code in turn:
                label, own_view, margin, orders, size_percent = data.INVESTORS[code]
                account = who[code]
                book = books.get(account)
                one_order = size * size_percent // 100
                centre, carried, todays, net_sold, news, cause = views[code]
                centre = min(max(centre, low), high)

                _explain(conn, share, day, now, label, book, centre, value, news, cause, todays, net_sold)
                conn.execute(
                    "INSERT INTO investor_books (account_id, company_id, session_date, carried_bps, centre, period)"
                    " VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (account_id, company_id) DO UPDATE"
                    " SET session_date = EXCLUDED.session_date, carried_bps = EXCLUDED.carried_bps,"
                    "     centre = EXCLUDED.centre, period = EXCLUDED.period",
                    (account, share["company_id"], day, carried, centre, value["period"]))

                bids, offers = ladder(centre, margin, orders, low, high)
                quantity = max(one_order // centre, 1)
                wanted = {("buy", price): quantity for price in bids} | {("sell", price): quantity for price in offers}
                if code == abroad.FOREIGN and foreign_left <= 0:
                    wanted = {}                     # they have traded their share of the day: their orders come off until tomorrow
                mine = _rows(conn, "SELECT * FROM market_orders WHERE company_id = %s AND account_id = %s AND status = 'open'"
                                   " ORDER BY id FOR UPDATE", (share["company_id"], account))
                standing = {(o["side"], o["limit_price"]): o["remaining"] for o in mine}
                if code == abroad.FOREIGN:
                    # Foreign investors may hold no shares of a company (or no cash yet): they only want the orders they can place,
                    # so that orders they cannot place do not make them take down and put up the rest every few minutes.
                    held = ledger.balance(conn, account, share["asset"]) + sum(o["remaining"] for o in mine if o["side"] == "sell")
                    cash = ledger.balance(conn, account) + sum(o["reserved"] for o in mine if o["side"] == "buy")
                    wanted = {key: amount for key, amount in wanted.items()
                              if (key[0] == "sell" and held > 0) or (key[0] == "buy" and cash * data.MOST_CASH_PER_ORDER_BPS // BPS >= key[1] * 2)}
                if set(standing) == set(wanted) and all(standing[key] * 2 >= amount for key, amount in wanted.items()):
                    continue                                   # its orders are still where it wants them
                books_of_exchange = exchange._accounts(conn)
                for order in mine:
                    exchange._close(conn, order, share, books_of_exchange, now, "cancelled", WITHDRAWN)
                for (side, price), amount in sorted(wanted.items()):
                    if side == "buy":
                        budget = ledger.balance(conn, account) * data.MOST_CASH_PER_ORDER_BPS // BPS
                        amount = min(amount, budget // (price + exchange.fee_due(price) + 1))
                    else:
                        amount = min(amount, ledger.balance(conn, account, share["asset"]))
                    if amount < 1:
                        continue
                    try:
                        exchange.place_order(conn, account=account, ticker=share["ticker"], side=side, kind="limit",
                                             quantity=amount, limit_price=price, now=now)
                        placed += 1
                    except exchange.ExchangeError:
                        continue                               # short of cash or shares, or trading paused: no order
    return placed


def temper_bps(code: str, closes: list | None, short_bps: int) -> int:
    """How an investor's temper moves its view of a share: a share of the last few days' move (with or against
    it), and, for small investors, a push upwards on a rising share that many have sold short."""
    if not closes or len(closes) < 2 or closes[0] <= 0:
        return 0
    move_percent = (closes[-1] - closes[0]) * 100 / closes[0]
    most = data.INVESTOR_TEMPER_MOST_BPS
    temper = int(min(max(data.INVESTOR_TEMPER_BPS.get(code, 0) * move_percent, -most), most))
    if code == "investors:public" and move_percent > 0 and short_bps > 0:
        temper += min(data.SQUEEZE_BPS_PER_SHORT_PERCENT * short_bps // 100, data.SQUEEZE_MOST_BPS)
    return temper


def _within(bps: int) -> int:
    return min(max(bps, -data.MOST_IMPACT_BPS), data.MOST_IMPACT_BPS)


def _impact(conn: Connection, account, company_id, session_date, value: dict, one_order: int) -> tuple[int, int]:
    """How far an investor's trading on one day moves its prices, and the shares it sold net of those it bought."""
    net = _rows(
        conn,
        "SELECT coalesce(sum(CASE WHEN seller_account_id = %s THEN quantity ELSE 0 END)"
        "              - sum(CASE WHEN buyer_account_id = %s THEN quantity ELSE 0 END), 0)::bigint AS net"
        " FROM market_trades WHERE company_id = %s AND session_date = %s AND (seller_account_id = %s OR buyer_account_id = %s)",
        (account, account, company_id, session_date, account, account))[0]["net"]
    return net * value["value_per_share"] * data.IMPACT_PER_LEVEL_BPS // max(one_order, 1), net


def _explain(conn: Connection, share: dict, day, now: datetime, label: str, book: dict | None, centre: int,
             value: dict, news: int, cause: str | None, todays: int, net_sold: int) -> None:
    """Write down, for "Why?", any real change in what an investor is quoting, and its main cause."""
    if book is None:
        return
    change = (centre - book["centre"]) * BPS // book["centre"]
    if abs(change) < 50:
        return
    way = "raised" if change > 0 else "lowered"
    size = f"{abs(change) / 100:.1f}%"
    if book["period"] != value["period"]:
        reason = (f"{label} {way} what they will pay and accept by {size} after the company's "
                  f"{clock.period_label(value['period'])} results were filed.")
    elif abs(todays) >= 50 and (todays > 0) == (change > 0):
        reason = (f"{label} sold {net_sold:,} more shares than they bought today, and {way} their prices by {size}."
                  if net_sold > 0 else
                  f"{label} bought {-net_sold:,} more shares than they sold today, and {way} their prices by {size}.")
    elif news and cause and (news > 0) == (change > 0) and book["session_date"] == day:
        reason = f"{label} marked the share {'up' if change > 0 else 'down'} {size} after {_EVENT_WORDS.get(cause, 'the news')}."
    else:
        return                      # an investor's own change of mind from day to day is not a reason anyone can use
    conn.execute("INSERT INTO market_reasons (company_id, session_date, happened_at, reason) VALUES (%s, %s, %s, %s)",
                 (share["company_id"], day, now, reason))


def withdraw_all(conn: Connection, now: datetime) -> int:
    """Take every investor's orders off the exchange. Done at the instant new company reports
    are filed, so nobody can trade against prices the investors set before they had read them."""
    # They are due back at the server's very next look at the market, not five minutes on.
    conn.execute("UPDATE market_status SET investors_acted = NULL, acted_session = NULL")
    return exchange.withdraw(conn, list(accounts(conn).values()), now,
                             "Withdrawn while the investor reads the new company reports.")
