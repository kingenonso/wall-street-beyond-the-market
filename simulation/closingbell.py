"""The Closing Rush and the Closing Bell (design document, section 5).

The Closing Rush is the last ten minutes of the trading day, 21:50 to 22:00 Lagos
time. The market is open as usual, but trading fees are halved and every large
order a player places is shown to everybody as it arrives: its size, never its owner.

At 22:00 the market shuts and the Closing Bell goes out: a short broadcast put
together from the day's real records. It names the day's biggest winner, biggest
loser and boldest move, gives a short reading of the economy (the market
advisory), and says what is coming next. Nothing in it is invented, and nothing
in it is hidden knowledge: an event later in the quarter is never hinted at.

Ringing the bell also writes down the BSX 50 for the day and what each player
was worth, so that charts can be drawn later.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from simulation import bonds, clock, corporate, exchange, marketview, news
from simulation import world_data as data
from simulation.money import BPS


# A player's bonds, and what the exchange holds for their applications and acceptances, count towards what they are worth.
marketview._OTHER_HOLDINGS[:] = [bonds.values_by_account, corporate.held_by_account]


def _rows(conn: Connection, sql: str, params=()) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def _percent(bps: int) -> str:
    return f"{abs(bps) / 100:.1f}".rstrip("0").rstrip(".") + "%"


def _naira(kobo: int) -> str:
    return f"₦{kobo / 100:,.2f}"


def rush(conn: Connection, now: datetime) -> dict:
    """Whether the Closing Rush is on, what trading costs now, and the large orders shown so far today."""
    day, _ = exchange.session_of(now)
    on = clock.in_closing_rush(now)
    full = data.EXCHANGE_FEE_BPS + data.STAMP_DUTY_BPS
    return {
        "in_rush": on, "fee_bps": full * (BPS - data.RUSH_FEE_DISCOUNT_BPS) // BPS if on else full, "usual_fee_bps": full,
        "large_orders": _rows(
            conn, "SELECT c.ticker, c.name, o.side, o.quantity, o.value, o.shown_at FROM market_large_orders o"
                  " JOIN companies c ON c.id = o.company_id WHERE o.session_date = %s ORDER BY o.id DESC LIMIT 30", (day,)),
    }


# ---------------------------------------------------------------------------
# The market advisory: a short reading of the economy, from published figures only.
# ---------------------------------------------------------------------------

def advisory(conn: Connection) -> list[str]:
    state = _rows(conn, "SELECT * FROM economy_results ORDER BY period DESC LIMIT 5")
    if not state or state[0]["period"] < 1:
        return ["The first quarter has not closed yet, so there are no figures for the economy to read."]
    now = state[0]
    lines = []
    rate, before = now["next_policy_rate_bps"], now["policy_rate_bps"]
    moved = ("raised it from " + _percent(before) if rate > before else
             "cut it from " + _percent(before) if rate < before else "left it unchanged")
    if rate >= data.NEUTRAL_RATE_BPS + 100:
        stance = "That is high: borrowing is dear, which holds prices down and weighs on what shares are worth."
    elif rate <= data.NEUTRAL_RATE_BPS - 100:
        stance = "That is low: borrowing is cheap, which helps companies grow and lifts what shares are worth."
    else:
        stance = "That is close to the level that neither pushes the economy on nor holds it back."
    lines.append(f"The Central Bank's interest rate is {_percent(rate)}. At the end of {clock.period_label(now['period'])} "
                 f"it {moved}. {stance}")
    inflation = now["inflation_bps"]
    low, high = data.INFLATION_TARGET_BPS - data.INFLATION_BAND_BPS, data.INFLATION_TARGET_BPS + data.INFLATION_BAND_BPS
    where = ("above the range the Central Bank accepts, so expect it to keep rates up" if inflation > high else
             "below the range the Central Bank accepts, so it has room to cut rates" if inflation < low else
             "inside the range the Central Bank accepts")
    lines.append(f"Prices are rising {_percent(inflation)} a year, {where} ({_percent(low)} to {_percent(high)}).")
    year_ago = next((s for s in state if s["period"] == now["period"] - 4 and s["period"] >= 1), None)
    if year_ago and year_ago["company_sales"] > 0:
        growth = (now["company_sales"] - year_ago["company_sales"]) * BPS // year_ago["company_sales"]
        real = growth - inflation
        lines.append(
            f"Companies sold {_percent(growth)} {'more' if growth >= 0 else 'less'} than in the same quarter a year ago. "
            f"After taking out rising prices, the economy is {'growing' if real >= 0 else 'shrinking'} about {_percent(real)} a year.")
    watch = _rows(conn, "SELECT reading FROM money_watch_results ORDER BY period DESC LIMIT 1")
    if watch and watch[0]["reading"] != "green":
        lines.append(f"The Money Watch reads {watch[0]['reading']}: there is more money about than the economy's output "
                     "justifies. The Central Bank leans against that with a higher rate.")
    return lines


# ---------------------------------------------------------------------------
# Ringing the bell
# ---------------------------------------------------------------------------

def _what_is_next(now: datetime, world: dict) -> str:
    start = clock.effective_start(world["world_start"], world["weeks_ahead"])
    if now < start:
        return "The first game quarter has not begun."
    ends = clock.next_quarter_end(now, start)
    label = clock.period_label(clock.periods_completed(now, start) + 1)
    hours = (ends - now).total_seconds() / 3600
    when = f"{clock.to_lagos(ends):%H:%M} Lagos time on {clock.to_lagos(ends):%A}"
    if hours <= 24:
        return (f"Before the next Closing Bell, at {when}, every company files its results for {label} and the Central "
                "Bank sets its interest rate. The computer-run investors take their orders off the exchange while they read them.")
    days = int(hours // 24)
    return (f"{days} more trading day{'s' if days != 1 else ''} until every company files its results for {label}, "
            f"at {when}. The market opens again at 12:00, after the opening auction at 11:30.")


def ring(conn: Connection, now: datetime) -> bool:
    """Ring the Closing Bell for the trading day that has just ended, if it has not been rung.
    Safe to call as often as you like, and from several servers."""
    today, _ = exchange.session_of(now)
    ended = today - timedelta(days=1)
    with conn.transaction():
        world = _rows(conn, "SELECT world_start, weeks_ahead, last_closed_period FROM world_state FOR UPDATE")
        if not world or _rows(conn, "SELECT 1 FROM closing_bells WHERE session_date = %s", (ended,)):
            return False
        world = world[0]
        if clock.to_lagos(world["world_start"]).date() > ended:
            return False                                 # the world had not begun on that day

        moves = _rows(
            conn,
            "SELECT c.ticker, c.name, t.close, t.volume::bigint AS volume, t.value::bigint AS value, t.trades,"
            "       coalesce(p.price, m.listing_price) AS before"
            " FROM (SELECT company_id, (array_agg(price ORDER BY id DESC))[1] AS close, sum(quantity) AS volume,"
            "         sum(price * quantity) AS value, count(*) AS trades, min(id) AS first_id"
            "       FROM market_trades WHERE session_date = %s GROUP BY company_id) t"
            " JOIN market_instruments m ON m.company_id = t.company_id JOIN companies c ON c.id = t.company_id"
            " LEFT JOIN LATERAL (SELECT x.price / split_factor(x.company_id, x.id) AS price"
            "     FROM market_trades x WHERE x.company_id = t.company_id AND x.id < t.first_id ORDER BY x.id DESC LIMIT 1) p ON true"
            " ORDER BY c.ticker", (ended,))
        for move in moves:
            move["change_bps"] = (move["close"] - move["before"]) * BPS // move["before"]
        shares = marketview._shares(conn, today)
        level = marketview.index_level(shares, marketview.index_base(conn))
        earlier = _rows(conn, "SELECT level FROM index_days WHERE session_date < %s ORDER BY session_date DESC LIMIT 1", (ended,))
        index_before = earlier[0]["level"] if earlier else marketview.INDEX_BASE * 100
        index_change = (level - index_before) * BPS // index_before

        lines = []
        direction = "rose" if index_change > 0 else "fell" if index_change < 0 else "ended where it began"
        lines.append(
            f"The BSX 50 {direction}{' ' + _percent(index_change) if index_change else ''} to {level / 100:,.2f}. "
            + (f"{sum(m['volume'] for m in moves):,} shares changed hands in {sum(m['trades'] for m in moves):,} trades, "
               f"worth {marketview._big(sum(m['value'] for m in moves))}." if moves else "No share traded today."))
        winner = max(moves, key=lambda m: m["change_bps"], default=None)
        loser = min(moves, key=lambda m: m["change_bps"], default=None)
        if winner and winner["change_bps"] > 0:
            lines.append(f"Biggest winner: {winner['name']} ({winner['ticker']}), up {_percent(winner['change_bps'])} "
                         f"to {_naira(winner['close'])}.")
        if loser and loser["change_bps"] < 0:
            lines.append(f"Biggest loser: {loser['name']} ({loser['ticker']}), down {_percent(loser['change_bps'])} "
                         f"to {_naira(loser['close'])}.")
        bold = _rows(conn, "SELECT c.ticker, c.name, t.price, t.quantity, t.taker_side FROM market_trades t"
                           " JOIN companies c ON c.id = t.company_id WHERE t.session_date = %s"
                           " ORDER BY t.price * t.quantity DESC, t.id LIMIT 1", (ended,))
        if bold:
            b = bold[0]
            how = {"buy": "One buyer took", "sell": "One seller parted with"}.get(b["taker_side"], "The opening auction moved")
            lines.append(f"Boldest move: {how} {b['quantity']:,} {b['name']} shares at {_naira(b['price'])} in a single "
                         f"trade worth {marketview._big(b['price'] * b['quantity'])}.")

        # The day's main stories: only what a reader could already see today.
        stories = []
        date = clock.game_date(now, clock.effective_start(world["world_start"], world["weeks_ahead"]))
        if date:
            period_now = (date.year - 1) * clock.QUARTERS_PER_YEAR + date.quarter
            first_day = max(date.day_of_quarter - 13, 1)           # one real day is about thirteen game days
            seen = set()
            for item in sorted(news.visible(conn, period_now, date.day_of_quarter, limit=60), key=lambda i: -i["importance"]):
                if item["period"] == period_now and item["day"] >= first_day and item["story"] not in seen:
                    seen.add(item["story"])
                    stories.append(item["headline"])
                if len(stories) == 3:
                    break

        content = {
            "index": level, "index_change_bps": index_change, "lines": lines, "stories": stories,
            "advisory": advisory(conn), "next": _what_is_next(now, world),
            "winner": winner and {k: winner[k] for k in ("ticker", "name", "close", "change_bps")},
            "loser": loser and {k: loser[k] for k in ("ticker", "name", "close", "change_bps")},
            "risers": sum(1 for m in moves if m["change_bps"] > 0), "fallers": sum(1 for m in moves if m["change_bps"] < 0),
        }
        conn.execute("INSERT INTO closing_bells (session_date, rung_at, content) VALUES (%s, %s, %s)",
                     (ended, now, Jsonb(content)))
        conn.execute("INSERT INTO index_days (session_date, level) VALUES (%s, %s) ON CONFLICT DO NOTHING", (ended, level))
        snapshot_net_worth(conn, ended)
        return True


def snapshot_net_worth(conn: Connection, day) -> None:
    """Write down what every player is worth today: cash (with what is held for orders and
    offers) and investments at their present prices."""
    worth = marketview.net_worth_of_players(conn)
    for account, (cash, investments) in worth.items():
        conn.execute("INSERT INTO net_worth_days (account_id, session_date, cash, investments) VALUES (%s, %s, %s, %s)"
                     " ON CONFLICT DO NOTHING", (account, day, cash, investments))


def latest(conn: Connection) -> dict | None:
    found = _rows(conn, "SELECT session_date, rung_at, content FROM closing_bells ORDER BY session_date DESC LIMIT 1")
    return found[0] if found else None
