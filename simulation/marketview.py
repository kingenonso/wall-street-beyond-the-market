"""Reading the market (design document, sections 11 and 18).

Everything here only reads. It turns the exchange's records, the companies'
filed accounts and their worked-out worth into what the market screens show:
the list of shares, the BSX 50 index, price history, a player's portfolio,
the investor's page on one company, and the watchlist.

Everything shown about a company comes from PUBLIC figures: what it filed, its
credit rating, the Central Bank's rate, and prices on the exchange.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from psycopg import Connection
from psycopg.rows import dict_row

from simulation import clock, exchange, ledger, valuation
from simulation import world_data as data
from simulation.money import BPS

INDEX_BASE = 1000                 # the BSX 50 stood at 1,000 when each share first traded
MOST_WATCHED = 30
HISTORY_SESSIONS = 60
MIN_PLAYERS_SHOWN = 20            # below this, what players hold between them is not shown on its own


def _rows(conn: Connection, sql: str, params=()) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def _percent(bps: int) -> str:
    return f"{abs(bps) / 100:.1f}".rstrip("0").rstrip(".") + "%"


def _naira(kobo: int) -> str:
    return f"₦{kobo / 100:,.2f}"


def _big(kobo: int) -> str:
    amount = abs(kobo) / 100
    for size, word in ((1e12, "trillion"), (1e9, "billion"), (1e6, "million")):
        if amount >= size:
            return f"₦{amount / size:.1f} {word}".replace(".0 ", " ")
    return f"₦{amount:,.0f}"


def _shares(conn: Connection, day) -> list[dict]:
    """Every share with its present price and today's trading."""
    rows = _rows(
        conn,
        "SELECT c.id, c.ticker, c.name, s.name AS sector, m.last_price, m.reference_price, m.listing_price, m.session_date,"
        "   (SELECT r.shares_in_issue FROM company_results r WHERE r.company_id = c.id ORDER BY r.period DESC LIMIT 1) AS shares,"
        "   (SELECT p.credit_rating FROM company_reports p WHERE p.company_id = c.id ORDER BY p.period DESC, p.version DESC LIMIT 1) AS rating,"
        "   coalesce(t.volume, 0)::bigint AS volume, coalesce(t.trades, 0) AS trades"
        " FROM market_instruments m JOIN companies c ON c.id = m.company_id JOIN sectors s ON s.code = c.sector"
        " LEFT JOIN (SELECT company_id, sum(quantity) AS volume, count(*) AS trades FROM market_trades"
        "            WHERE session_date = %s GROUP BY company_id) t ON t.company_id = c.id ORDER BY c.ticker", (day,))
    for row in rows:
        # Before the day's first order arrives in a share, its day has not yet been started.
        row["reference"] = (row["last_price"] or row["reference_price"]) if row["session_date"] < day else row["reference_price"]
        row["price"] = row["last_price"] or row["reference_price"]
        row["change_bps"] = (row["price"] - row["reference"]) * BPS // row["reference"]
        row["market_value"] = row["price"] * row["shares"]
    return rows


def index_level(shares: list[dict]) -> int:
    """The BSX 50, in hundredths of a point: every company at its present price against the
    price it was first listed at, each counted by its number of shares."""
    base = sum(s["listing_price"] * s["shares"] for s in shares)
    return sum(s["price"] * s["shares"] for s in shares) * INDEX_BASE * 100 // base if base else INDEX_BASE * 100


def overview(conn: Connection, now: datetime) -> dict:
    """The whole market at a glance."""
    day, state = exchange.session_of(now)
    shares = _shares(conn, day)
    before = sum(s["reference"] * s["shares"] for s in shares)
    value = sum(s["market_value"] for s in shares)
    return {
        "state": state.value, "paused_until": exchange.paused_until(conn, now),
        "index": index_level(shares), "index_change_bps": (value - before) * BPS // before if before else 0,
        "market_value": value, "volume": sum(s["volume"] for s in shares), "trades": sum(s["trades"] for s in shares),
        "shares": shares, "index_history": index_history(conn, shares),
    }


def index_history(conn: Connection, shares: list[dict]) -> list[dict]:
    """The index at the end of each trading day on which anything traded, oldest first."""
    closes = _rows(conn, "SELECT DISTINCT ON (company_id, session_date) company_id, session_date, price FROM market_trades"
                         " ORDER BY company_id, session_date, id DESC")
    if not closes:
        return []
    by_day: dict = {}
    for row in closes:
        by_day.setdefault(row["session_date"], {})[row["company_id"]] = row["price"]
    price = {s["id"]: s["listing_price"] for s in shares}
    count = {s["id"]: s["shares"] for s in shares}
    base = sum(s["listing_price"] * s["shares"] for s in shares)
    history = []
    for day in sorted(by_day):
        price.update(by_day[day])
        history.append({"session_date": day, "level": sum(price[i] * count[i] for i in price) * INDEX_BASE * 100 // base})
    return history[-HISTORY_SESSIONS:]


def history(conn: Connection, ticker: str) -> list[dict] | None:
    """One share's trading days, oldest first: where it opened and closed, its high and low, and how many shares traded."""
    found = _rows(conn, "SELECT c.id FROM companies c JOIN market_instruments m ON m.company_id = c.id WHERE c.ticker = %s", (ticker,))
    if not found:
        return None
    days = _rows(
        conn,
        "SELECT session_date, min(price) AS low, max(price) AS high, sum(quantity)::bigint AS volume,"
        "   (array_agg(price ORDER BY id))[1] AS open, (array_agg(price ORDER BY id DESC))[1] AS close"
        " FROM market_trades WHERE company_id = %s GROUP BY session_date ORDER BY session_date DESC LIMIT %s",
        (found[0]["id"], HISTORY_SESSIONS))
    return days[::-1]


# ---------------------------------------------------------------------------
# A player's portfolio
# ---------------------------------------------------------------------------

def portfolio(conn: Connection, account: UUID | str, now: datetime) -> dict:
    """What an account owns, what it paid, what it is worth now, and the dividends it has had."""
    day, _ = exchange.session_of(now)
    prices = {s["ticker"]: s for s in _shares(conn, day)}
    # What the shares still held cost, by the average-cost method: each purchase adds its cost
    # (with its fee); each sale takes away the average cost of the shares sold.
    held: dict = {}
    for trade in _rows(
        conn,
        "SELECT c.ticker, t.price, t.quantity, t.buyer_fee, t.seller_fee,"
        "   t.buyer_account_id = %s AS bought, t.seller_account_id = %s AS sold"
        " FROM market_trades t JOIN companies c ON c.id = t.company_id"
        " WHERE t.buyer_account_id = %s OR t.seller_account_id = %s ORDER BY t.id", (account, account, account, account)):
        position = held.setdefault(trade["ticker"], {"shares": 0, "cost": 0, "realised": 0})
        value = trade["price"] * trade["quantity"]
        if trade["bought"] and trade["sold"]:
            position["realised"] -= trade["buyer_fee"] + trade["seller_fee"]         # traded with itself: only the fees moved
        elif trade["bought"]:
            position["shares"] += trade["quantity"]
            position["cost"] += value + trade["buyer_fee"]
        else:
            sold = min(trade["quantity"], position["shares"])
            cost_of_sold = position["cost"] * sold // position["shares"] if position["shares"] else 0
            position["shares"] -= sold
            position["cost"] -= cost_of_sold
            position["realised"] += value - trade["seller_fee"] - cost_of_sold
    dividends = {
        r["ticker"]: r["total"] for r in _rows(
            conn,
            "SELECT c.ticker, sum(e.amount)::bigint AS total FROM ledger_entries e"
            " JOIN ledger_transactions t ON t.id = e.transaction_id AND t.kind = 'dividend'"
            " JOIN ledger_entries payer ON payer.transaction_id = t.id AND payer.amount < 0"
            " JOIN companies c ON c.account_id = payer.account_id"
            " WHERE e.account_id = %s AND e.amount > 0 GROUP BY c.ticker", (account,))
    }
    holdings = []
    for row in exchange.holdings_of(conn, account):
        owned = row["shares"] + row["held_for_orders"]
        position = held.get(row["ticker"], {"shares": 0, "cost": 0, "realised": 0})
        # Shares that did not come through the exchange have no purchase cost on record.
        cost = position["cost"] * min(owned, position["shares"]) // position["shares"] if position["shares"] else 0
        share = prices[row["ticker"]]
        holdings.append({
            "ticker": row["ticker"], "name": row["name"], "shares": owned, "held_for_orders": row["held_for_orders"],
            "price": share["price"], "change_bps": share["change_bps"], "value": share["price"] * owned,
            "cost": cost, "gain": share["price"] * owned - cost, "dividends": dividends.get(row["ticker"], 0),
        })
    cash = ledger.balance(conn, account)
    held_cash = _rows(conn, "SELECT coalesce(sum(reserved), 0)::bigint AS total FROM market_orders"
                            " WHERE account_id = %s AND status = 'open'", (account,))[0]["total"]
    invested = sum(h["value"] for h in holdings)
    return {
        "cash": cash, "held_for_orders": held_cash, "shares_value": invested, "total": cash + held_cash + invested,
        "holdings": holdings, "dividends": sum(dividends.values()),
        "realised": sum(p["realised"] for p in held.values()),
    }


# ---------------------------------------------------------------------------
# The investor's page on one company
# ---------------------------------------------------------------------------

def shareholders(conn: Connection, company_id, asset: str) -> list[dict]:
    """Who owns a company's shares, by kind of owner. Shares the exchange is holding for a sell
    order still belong to whoever is selling them."""
    owners = _rows(
        conn,
        "SELECT a.kind, a.code, sum(x.shares)::bigint AS shares FROM ("
        "   SELECT b.account_id, b.balance AS shares FROM ledger_balances b JOIN ledger_accounts k ON k.id = b.account_id"
        "    WHERE b.asset = %s AND b.balance > 0 AND k.kind <> 'exchange'"
        "   UNION ALL"
        "   SELECT o.account_id, o.remaining FROM market_orders o"
        "    WHERE o.company_id = %s AND o.side = 'sell' AND o.status = 'open' AND o.remaining > 0"
        " ) x JOIN ledger_accounts a ON a.id = x.account_id GROUP BY a.kind, a.code", (asset, company_id))
    enough_players = _rows(conn, "SELECT count(*) AS n FROM players")[0]["n"] >= MIN_PLAYERS_SHOWN
    groups = {"Founders": 0, "Pension funds": 0, "Small investors": 0, "Players": 0, "Others": 0}
    for owner in owners:
        if owner["code"] == ledger.INVESTORS_FOUNDERS:
            groups["Founders"] += owner["shares"]
        elif owner["code"] == ledger.INVESTORS_INSTITUTIONS:
            groups["Pension funds"] += owner["shares"]
        elif owner["code"] == ledger.INVESTORS_PUBLIC:
            groups["Small investors"] += owner["shares"]
        elif owner["kind"] == "player":
            # While players are few, their shares are counted with the small investors, so that
            # no line shows one player's holding.
            groups["Players" if enough_players else "Small investors"] += owner["shares"]
        else:
            groups["Others"] += owner["shares"]
    total = sum(groups.values())
    return [{"holder": name, "shares": count, "share_bps": count * BPS // total if total else 0}
            for name, count in groups.items() if count > 0]


def _schedule(worth: dict) -> list[dict]:
    """The sum behind the net present value, year by year, for the whole company."""
    if worth["method"] != "profits" or worth["yearly_profit"] <= 0:
        return []
    g, r, t = worth["growth_bps"] / BPS, worth["discount_bps"] / BPS, worth["long_run_bps"] / BPS
    profit, rows = float(worth["yearly_profit"]), []
    for year in range(1, 6):
        profit *= 1 + g
        rows.append({"label": f"Year {year}", "profit": int(profit), "value_today": int(profit / (1 + r) ** year)})
    after = profit * (1 + t) / (r - t)
    rows.append({"label": "Every year after that", "profit": int(after), "value_today": int(after / (1 + r) ** 5)})
    return rows


def analysis(conn: Connection, ticker: str, now: datetime) -> dict | None:
    """What an investor wants to know about one company: its value on the market, what it is worth
    by its profits (net present value), who owns it, and an analyst's note. Public figures only."""
    day, _ = exchange.session_of(now)
    everything = _shares(conn, day)
    share = next((s for s in everything if s["ticker"] == ticker), None)
    if share is None:
        return None
    worths = valuation.latest(conn)
    worth = worths.get(share["id"])
    if worth is None:
        return None
    filed = _rows(
        conn,
        "SELECT DISTINCT ON (period) period, credit_rating,"
        "   (figures->'income_statement'->>'revenue')::bigint AS revenue,"
        "   (figures->'income_statement'->>'net_profit')::bigint AS net_profit,"
        "   (figures->'cash_flow'->>'dividends_paid')::bigint AS dividends,"
        "   (figures->'balance_sheet'->>'total_equity')::bigint AS equity,"
        "   (figures->'balance_sheet'->>'borrowings')::bigint AS borrowings,"
        "   coalesce((figures->'notes'->>'principal_overdue')::bigint, 0) AS overdue,"
        "   coalesce((figures->'notes'->>'repayments_missed')::bigint, 0) AS missed"
        " FROM company_reports WHERE company_id = %s AND period > %s ORDER BY period, version DESC",
        (share["id"], worth["period"] - 8))
    latest = filed[-1]
    trading = [f for f in filed if f["period"] >= 1]
    year = trading[-4:]
    scale = lambda total: total * 4 // len(year) if year else 0                # noqa: E731
    sales, dividends = scale(sum(f["revenue"] for f in year)), scale(sum(f["dividends"] for f in year))
    profit, count, price = worth["yearly_profit"], worth["shares_in_issue"], share["price"]
    value = price * count
    npv = worth["value_per_share"]
    gap = (price - npv) * BPS // npv

    def times(amount: int) -> int | None:
        """The market value as a multiple of a yearly figure, in hundredths."""
        return value * 100 // amount if amount > 0 else None

    # The whole market's price against its profit, for comparison: profitable companies only.
    market_value = sum(s["market_value"] for s in everything if worths.get(s["id"]) and worths[s["id"]]["yearly_profit"] > 0)
    market_profit = sum(w["yearly_profit"] for w in worths.values() if w["yearly_profit"] > 0)
    market_pe = market_value * 100 // market_profit if market_profit else None
    pe = times(profit)
    dividend_yield = dividends * BPS // value if value else 0

    # --- The analyst's note: a view with its reasons, never a promise. ---
    if worth["method"] == "assets" and trading:
        verdict = "judged on its assets"
        opening = ("It is not making a profit, so it cannot be valued on its profits. It is judged on what is left of its "
                   f"owners' funds: about {_naira(npv)} a share is half of the {_naira(max(worth['book_per_share'], 0))} of owners' funds behind each share.")
    elif not trading:
        verdict = "not yet judged"
        opening = "It has not yet filed any trading results. Until it does, it is taken to be worth the owners' funds in it."
    elif gap <= -1000:
        verdict = "looks cheap"
        opening = (f"At {_naira(price)} the share is {_percent(gap)} below the {_naira(npv)} its expected profits are worth today.")
    elif gap >= 1000:
        verdict = "looks expensive"
        opening = (f"At {_naira(price)} the share is {_percent(gap)} above the {_naira(npv)} its expected profits are worth today.")
    else:
        verdict = "looks about fairly priced"
        opening = (f"At {_naira(price)} the share is within a tenth of the {_naira(npv)} its expected profits are worth today.")
    reasons = [opening]
    if pe is not None and market_pe is not None:
        dearer = pe > market_pe * 11 // 10
        cheaper = pe < market_pe * 9 // 10
        reasons.append(
            f"The whole company costs {pe / 100:.1f} times its yearly profit. Across all profitable companies on the exchange "
            f"the figure is {market_pe / 100:.1f}, so by this measure it is "
            f"{'dearer than' if dearer else 'cheaper than' if cheaper else 'in line with'} the market.")
    if dividend_yield > 0:
        reasons.append(f"Over the past year it paid its owners {_big(dividends)} in dividends: {_percent(dividend_yield)} of what the "
                       "whole company costs today.")
    elif trading:
        reasons.append("It paid its owners no dividend over the past year.")
    reasons += list(worth["reasons"])[:2]

    risks = []
    rating = latest["credit_rating"]
    if rating in ("B", "CCC", "D"):
        risks.append(f"Its credit rating is {rating}: lenders see a real chance it cannot repay what it owes.")
    if latest["overdue"] > 0:
        risks.append(f"{_big(latest['overdue'])} of its borrowing is past its repayment date and unpaid.")
    elif latest["missed"] > 0:
        risks.append("It missed a loan repayment in its latest quarter.")
    if trading and trading[-1]["net_profit"] < 0:
        risks.append("It lost money in its latest quarter.")
    if latest["equity"] > 0 and latest["borrowings"] > latest["equity"]:
        risks.append(f"It has borrowed {latest['borrowings'] / latest['equity']:.1f} times its owners' funds, so a rise in "
                     "interest rates costs it more than most.")
    elif latest["equity"] <= 0:
        risks.append("Its debts are larger than everything it owns: its owners' funds are used up.")
    if len(year) == 4 and len(trading) >= 8:
        before = sum(f["net_profit"] for f in trading[-8:-4])
        if before > 0 and profit < before * 9 // 10:
            risks.append(f"Its profit over the past year is {_percent((profit - before) * BPS // before)} lower than the year before.")
    risks.append(f"The value above assumes profits grow {_percent(worth['growth_bps'])} a year for five years. If they grow more "
                 "slowly, or the Central Bank raises its rate, the company is worth less.")

    return {
        "ticker": share["ticker"], "name": share["name"], "price": price, "period": worth["period"],
        "shares_in_issue": count, "market_value": value, "yearly_profit": profit, "yearly_sales": sales,
        "yearly_dividends": dividends, "owners_funds": latest["equity"], "book_per_share": worth["book_per_share"],
        "price_to_profit": pe, "price_to_sales": times(sales), "price_to_owners_funds": times(latest["equity"]),
        "market_price_to_profit": market_pe, "dividend_yield_bps": dividend_yield,
        "npv_per_share": npv, "npv_total": npv * count, "npv_method": worth["method"], "npv_gap_bps": gap,
        "growth_bps": worth["growth_bps"], "discount_bps": worth["discount_bps"], "long_run_bps": worth["long_run_bps"],
        "schedule": _schedule(worth), "verdict": verdict, "reasons": reasons, "risks": risks,
        "shareholders": shareholders(conn, share["id"], f"SHR-{ticker}"),
    }


# ---------------------------------------------------------------------------
# The watchlist
# ---------------------------------------------------------------------------

class WatchlistError(Exception):
    """A change to a watchlist was refused. The message is written for the player."""


def watch(conn: Connection, player_id, ticker: str, alert_above: int | None, alert_below: int | None) -> None:
    """Add a company to a player's watchlist, or change its alert prices."""
    company = _rows(conn, "SELECT c.id FROM companies c JOIN market_instruments m ON m.company_id = c.id WHERE c.ticker = %s", (ticker,))
    if not company:
        raise WatchlistError("There is no share with that code on the exchange.")
    if alert_above is not None and alert_below is not None and alert_above <= alert_below:
        raise WatchlistError("The price to be told at on the way up must be above the price on the way down.")
    with conn.transaction():
        # One player's changes take turns, so the limit cannot be passed by sending many at once.
        conn.execute("SELECT 1 FROM players WHERE id = %s FOR UPDATE", (player_id,))
        already = _rows(conn, "SELECT company_id FROM watchlist WHERE player_id = %s", (player_id,))
        if company[0]["id"] not in {row["company_id"] for row in already} and len(already) >= MOST_WATCHED:
            raise WatchlistError(f"A watchlist holds at most {MOST_WATCHED} companies. Remove one first.")
        conn.execute(
            "INSERT INTO watchlist (player_id, company_id, alert_above, alert_below) VALUES (%s, %s, %s, %s)"
            " ON CONFLICT (player_id, company_id) DO UPDATE SET alert_above = EXCLUDED.alert_above, alert_below = EXCLUDED.alert_below",
            (player_id, company[0]["id"], alert_above, alert_below))


def unwatch(conn: Connection, player_id, ticker: str) -> None:
    conn.execute("DELETE FROM watchlist w USING companies c WHERE c.id = w.company_id AND w.player_id = %s AND c.ticker = %s",
                 (player_id, ticker))


def watchlist(conn: Connection, player_id, now: datetime) -> list[dict]:
    """A player's watched companies with their prices, and which alerts have been reached."""
    day, _ = exchange.session_of(now)
    prices = {s["id"]: s for s in _shares(conn, day)}
    watched = []
    for row in _rows(conn, "SELECT * FROM watchlist WHERE player_id = %s ORDER BY created_at, company_id", (player_id,)):
        share = prices[row["company_id"]]
        reached = ("above" if row["alert_above"] and share["price"] >= row["alert_above"]
                   else "below" if row["alert_below"] and share["price"] <= row["alert_below"] else None)
        watched.append({
            "ticker": share["ticker"], "name": share["name"], "price": share["price"], "change_bps": share["change_bps"],
            "alert_above": row["alert_above"], "alert_below": row["alert_below"], "reached": reached,
        })
    return watched
