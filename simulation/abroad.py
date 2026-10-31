"""The rest of the world (economy upgrade, owner, 12 October 2026). A simple version: the crises
stage builds on it.

Three things now come from outside Nigeria:

  * The oil price, in US dollars a barrel. It drifts back towards its usual level and swings
    with the world's secret randomness, and jumps when events hit supply. It sets what energy
    costs at home, what the country earns selling oil abroad, and the Government's oil income.
  * The naira's exchange rate. It weakens when prices at home rise faster than abroad, when oil
    falls, when the country buys more abroad than it sells, and strengthens the other way; high
    interest rates hold it up a little. A weaker naira makes everything bought abroad dearer.
  * Foreign investors. They bring money in and buy shares when Nigerian interest rates pay well
    over what lending abroad pays (after the naira's expected fall), and sell and take it out
    when they do not. They trade on the exchange through ordinary orders, like everybody else.

The rest of the world is one ledger account. It holds naira: what it is paid for what
companies buy abroad, and what foreign investors send back. It spends them on what the
country sells abroad, and on the foreign investors' money. Nothing is created: it started
with an opening balance like everybody else, and every naira after that moves through the ledger.

Each quarter's oil price and exchange rate are set when the quarter before closes, and are
public from that moment, like the Central Bank's interest rate. What they will be after that
comes from the world's secret randomness, and nobody can know it in advance.
"""

from __future__ import annotations

from psycopg import Connection
from psycopg.rows import dict_row

from simulation import clock, ledger, stochastic
from simulation import world_data as data
from simulation.money import BPS, apply_bps

ABROAD = "abroad"
FOREIGN = "investors:foreign"


def _rows(conn: Connection, sql: str, params=()) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def world_prices(period: int) -> float:
    """How far prices abroad have risen since the world began (1.0 = as they were)."""
    return (1 + data.WORLD_INFLATION_BPS / BPS) ** (max(period, 0) / 4)


def opening_imports(shapes: dict[str, dict]) -> int:
    """What companies buy abroad in an opening quarter: each one's supplies, times the share of them
    its kind of company buys from abroad."""
    total = 0
    for company in data.COMPANIES:
        shape = shapes.get(company.ticker)
        if shape is None:
            continue
        supplies = sum(bps for sector, bps in data.INPUTS.get(company.sector, {}).items() if sector in data.IMPORTABLE_SUPPLIES)
        total += apply_bps(apply_bps(shape["base_revenue"], supplies), data.IMPORT_SHARE_BPS.get(company.sector, 0))
    return total


def create_accounts(conn: Connection):
    """The rest of the world, and the foreign investors who come from it."""
    abroad = ledger.create_account(conn, kind="rest_of_world", name="The rest of the world", code=ABROAD)
    foreign = ledger.create_account(conn, kind="npc_investors", name="Foreign investors", code=FOREIGN)
    return abroad, foreign


def opening_reserve(imports: int) -> int:
    return imports * data.ABROAD_RESERVE_QUARTERS


def write_opening(conn: Connection, imports: int) -> None:
    conn.execute(
        "INSERT INTO abroad_results (period, oil_cents, fx, reserve, export_base, reason) VALUES (0, %s, %s, %s, %s, %s)",
        (data.OIL_START_CENTS, data.FX_START, opening_reserve(imports), imports,
         "The opening oil price and exchange rate."))


def state(conn: Connection, period: int) -> dict | None:
    """The row written when `period` closed: the oil price and exchange rate for the quarter after it."""
    rows = _rows(conn, "SELECT * FROM abroad_results WHERE period = %s", (period,))
    return rows[0] if rows else None


def accounts(conn: Connection) -> tuple:
    return ledger.account_id(conn, ABROAD), ledger.account_id(conn, FOREIGN)


def import_factor_bps(conn: Connection, period: int, price_index_bps: int) -> int:
    """How dear goods from abroad are this quarter against when the world began, after prices at home:
    10000 = the same. A weaker naira raises it; so do prices rising abroad."""
    now = state(conn, period - 1)
    if now is None:
        return BPS
    return round(now["fx"] / data.FX_START * world_prices(period) * BPS * BPS / max(price_index_bps, 1))


def import_share_bps(sector: str, factor_bps: int) -> int:
    """The share of the goods a kind of company buys abroad. Less when goods abroad are dear (a weak
    naira), more when they are cheap, and never more than twice the usual share."""
    usual = data.IMPORT_SHARE_BPS.get(sector, 0)
    switched = usual * (BPS / max(factor_bps, 1)) ** (data.IMPORT_SWITCH_BPS / BPS)
    return int(min(switched, 2 * usual, BPS // 2))


def pay_imports(conn: Connection, company: dict, wanted: int, factor_bps: int, period: int) -> int:
    """A company pays for what it buys abroad. Returns what it paid."""
    amount = apply_bps(wanted, factor_bps)
    if amount <= 0:
        return 0
    return ledger.pay_up_to(conn, payer=company["account_id"], receiver=ledger.account_id(conn, ABROAD), wanted=amount,
                            kind="imports", memo=f"{company['name']}: supplies bought abroad, {clock.period_label(period)}",
                            period=period)


def buy_exports(conn: Connection, world, period: int) -> dict:
    """The rest of the world buys what the country sells abroad: oil and gas above all, and some
    farm produce and factory goods. The Government takes its share of the oil money.
    Returns what was bought."""
    from simulation import economy
    now = state(conn, period - 1)
    abroad = ledger.account_id(conn, ABROAD)
    label = clock.period_label(period)
    in_naira = now["fx"] / data.FX_START * world_prices(period)
    oil = round(apply_bps(now["export_base"], data.OIL_EXPORT_SHARE_BPS) * now["oil_cents"] / data.OIL_START_CENTS * in_naira)
    # Farm produce and factory goods sell better abroad when the naira is cheap against prices at home.
    prices_home = _price_index(conn, period - 1)
    cheap = in_naira * BPS / max(prices_home, 1)
    other = round(apply_bps(now["export_base"], BPS - data.OIL_EXPORT_SHARE_BPS) * in_naira
                  * min(max(cheap ** (data.EXPORT_SWITCH_BPS / BPS), 0.5), 2.0))
    # It never spends more than part of what it holds in one quarter.
    can = apply_bps(ledger.balance(conn, abroad), data.ABROAD_MOST_SPEND_BPS)
    if oil + other > can and oil + other > 0:
        oil, other = oil * can // (oil + other), other * can // (oil + other)
    royalty = apply_bps(oil, data.OIL_ROYALTY_BPS)
    paid_royalty = ledger.pay_up_to(conn, payer=abroad, receiver=world.treasury, wanted=royalty, kind="oil_royalty",
                                    memo=f"The Government's share of oil sold abroad, {label}", period=period)
    oil_paid = ledger.pay_split_up_to(
        conn, payer=abroad, amounts=economy.allocate(world, oil - royalty, {"oil_gas": 1}), kind="exports",
        memo=f"Oil and gas sold abroad, {label}", period=period)
    other_paid = ledger.pay_split_up_to(
        conn, payer=abroad, amounts=economy.allocate(world, other, dict(data.NON_OIL_EXPORTS)), kind="exports",
        memo=f"Farm produce and factory goods sold abroad, {label}", period=period)
    return {"exports": paid_royalty + oil_paid + other_paid, "oil_exports": paid_royalty + oil_paid, "oil_royalty": paid_royalty}


def _price_index(conn: Connection, period: int) -> int:
    rows = _rows(conn, "SELECT price_index_bps FROM economy_results WHERE period = %s", (period,))
    return rows[0]["price_index_bps"] if rows else BPS


def next_oil(conn: Connection, period: int, seed: str, energy_event_bps: int) -> int:
    """Next quarter's oil price: back towards its usual level, its own swing, and any event hitting supply."""
    now = state(conn, period - 1)["oil_cents"]
    usual = data.OIL_START_CENTS * world_prices(period + 1)
    drifted = now + (usual - now) * data.OIL_RETURN_BPS / BPS
    swing = stochastic.shock_bps(seed, "oil", period, "price", data.OIL_SWING_BPS, data.OIL_LOADINGS)
    jump = energy_event_bps * data.OIL_EVENT_MULTIPLE
    # Part 4b: growth abroad above (or below) its usual pace lifts (or lowers) the demand for oil.
    from simulation import world
    demand = world.oil_demand_bps(conn, period)
    low, high = data.OIL_LIMITS_CENTS
    return int(min(max(drifted * (BPS + swing) / BPS * (BPS + jump) / BPS * (BPS + demand) / BPS, low), high))


def energy_index_bps(oil_cents: int, fx: int) -> int:
    """What energy costs at home against when the world began: the oil price in naira."""
    return max(round(BPS * oil_cents / data.OIL_START_CENTS * fx / data.FX_START), 1000)


def import_push_bps(conn: Connection, period: int) -> int:
    """How much this quarter's change in the naira's value pushed prices at home up (or down):
    goods bought abroad are part of what households pay for."""
    now, before = state(conn, period - 1), state(conn, period - 2)
    if now is None or before is None:
        return 0
    change = now["fx"] * world_prices(period) / (before["fx"] * world_prices(period - 1)) - 1
    return round(change * BPS * data.IMPORT_PRICE_WEIGHT_BPS / BPS)


def foreign_holdings(conn: Connection) -> int:
    """What the foreign investors' shares are worth at today's prices."""
    foreign = ledger.account_id(conn, FOREIGN)
    row = _rows(conn, "SELECT coalesce(sum(o.shares * coalesce(m.last_price, m.reference_price)), 0)::bigint AS v"
                      " FROM share_owners o JOIN market_instruments m ON m.company_id = o.company_id WHERE o.account_id = %s",
                (foreign,))
    return int(row[0]["v"])


def close(conn: Connection, period: int, seed: str, *, oil_next: int, inflation_bps: int, next_rate_bps: int,
          trade: dict, imports: int) -> dict:
    """At the close: the naira's exchange rate for next quarter, and what foreign investors do."""
    now = state(conn, period - 1)
    abroad, foreign = accounts(conn)
    label = clock.period_label(period)
    fx = now["fx"]
    reserve = ledger.balance(conn, abroad)
    # Part 4b: prices and interest abroad are America's, once the markets abroad are open (a fixed figure before).
    from simulation import world
    inflation_abroad, rate_abroad = world.inflation_abroad(conn), world.rate_abroad(conn)
    # 1. The exchange rate.
    ppp = (inflation_bps - inflation_abroad) / 4
    # Its usual value: where prices at home against prices abroad say it should be. It is pulled back towards it.
    usual_fx = data.FX_START * _price_index(conn, period) / BPS / world_prices(period + 1)
    anchor = (usual_fx - fx) / fx * data.FX_ANCHOR_BPS
    oil_effect = -(oil_next - now["oil_cents"]) / now["oil_cents"] * data.FX_OIL_BPS
    surplus = (trade["exports"] - imports) / max(imports, 1)
    trade_effect = -surplus * data.FX_TRADE_BPS
    usual_reserve = max(imports, 1) * data.ABROAD_RESERVE_QUARTERS
    reserve_effect = (reserve - usual_reserve) / usual_reserve * data.FX_RESERVE_BPS
    rate_effect = -(next_rate_bps - data.NEUTRAL_RATE_BPS) / 4 * data.FX_RATE_BPS / BPS
    swing = stochastic.shock_bps(seed, "naira", period, "fx", data.FX_SWING_BPS, data.NAIRA_LOADINGS)
    move = ppp + anchor + oil_effect + trade_effect + reserve_effect + rate_effect + swing
    move = min(max(move, -data.FX_MOST_MOVE_BPS), data.FX_MOST_MOVE_BPS)
    fx_next = max(round(fx * (BPS + move) / BPS), 100)
    reason = fx_reason(move, {"prices": ppp, "anchor": anchor, "oil": oil_effect, "trade": trade_effect,
                              "reserve": reserve_effect, "rate": rate_effect, "swing": swing})

    # 2. The foreign investors. What they earn here over lending abroad, after the naira's expected fall.
    expected_fall = (inflation_bps - inflation_abroad) + (fx_next - fx) / fx * BPS * 4 / 2
    carry = next_rate_bps - rate_abroad - expected_fall
    usual = apply_bps(opening_reserve(_row0(conn)["export_base"]), data.FOREIGN_START_SHARE_BPS) * fx_next / data.FX_START * world_prices(period)
    want_bps = min(max(BPS + carry * data.FOREIGN_CARRY_BPS / 100, data.FOREIGN_WANT_LIMITS_BPS[0]), data.FOREIGN_WANT_LIMITS_BPS[1])
    want = round(usual * want_bps / BPS)
    cash = ledger.balance(conn, foreign)
    shares = foreign_holdings(conn)
    held = cash + shares
    gap = round((want - held) * data.FOREIGN_MOVE_BPS / BPS)
    inflow = 0
    if gap > 0:
        inflow = ledger.pay_up_to(conn, payer=abroad, receiver=foreign, wanted=min(gap, reserve // 2), kind="foreign_investment",
                                  memo=f"Foreign investors bring money in, {label}", period=period)
    backlog = 0
    if gap < 0:
        # Part 4a: leaving needs dollars. While the Central Bank manages the naira, only what it can spare leaves; the rest waits.
        from simulation import fx
        wanted_out = min(-gap, cash)
        allowed = fx.exit_room(conn, wanted_out, fx_next)
        backlog = wanted_out - allowed
        inflow = -ledger.pay_up_to(conn, payer=foreign, receiver=abroad, wanted=allowed, kind="foreign_withdrawal",
                                   memo=f"Foreign investors take money out, {label}", period=period) if allowed > 0 else 0
    cash += inflow
    # How keen they are on shares next quarter: their extra return, and how far their cash is from
    # being mostly in shares. Positive: they price shares above what they are worth, and buy.
    in_shares = shares * BPS // max(cash + shares, 1)
    # (A small extra pull towards shares while most of their money is cash; it fades as they buy.)
    tilt = carry * data.FOREIGN_TILT_PER_CARRY_BPS / BPS + (8000 - in_shares) * 50 / BPS
    if want < held:
        tilt = min(tilt, -abs(tilt) / 2 - 50)        # taking money out: they sell
    if backlog > 0:
        # Money stuck waiting for dollars makes the rest keener to get out while they can.
        tilt -= min(backlog * data.FX_BACKLOG_TILT_BPS / max(usual, 1) * 4, 2 * data.FX_BACKLOG_TILT_BPS)
    tilt = int(min(max(tilt, -data.FOREIGN_MOST_TILT_BPS), data.FOREIGN_MOST_TILT_BPS))
    last_trade = _rows(conn, "SELECT coalesce(max(id), 0) AS id FROM market_trades")[0]["id"]
    traded = _rows(conn, """
        SELECT coalesce(sum(CASE WHEN buyer_account_id = %s THEN quantity * price ELSE 0 END), 0)::bigint AS bought,
               coalesce(sum(CASE WHEN seller_account_id = %s THEN quantity * price ELSE 0 END), 0)::bigint AS sold
        FROM market_trades WHERE id > %s AND id <= %s""", (foreign, foreign, now["last_trade_id"], last_trade))
    row = {
        "period": period, "oil_cents": oil_next, "fx": fx_next, "exports": trade["exports"], "oil_exports": trade["oil_exports"],
        "imports": imports, "oil_royalty": trade["oil_royalty"], "reserve": ledger.balance(conn, abroad),
        "foreign_inflow": inflow, "foreign_cash": cash, "foreign_shares": shares,
        "foreign_bought": traded[0]["bought"], "foreign_sold": traded[0]["sold"], "tilt_bps": tilt,
        "export_base": now["export_base"], "last_trade_id": last_trade, "fx_backlog": backlog,
        "reason": f"The naira moved mostly on {reason}.",
    }
    cols = list(row)
    conn.execute(f"INSERT INTO abroad_results ({', '.join(cols)}) VALUES ({', '.join(['%s'] * len(cols))})", list(row.values()))
    return row


# What each cause of a move is called, weakening the naira (+) or strengthening it (-).
_FX_WORDS = {
    "prices": ("prices at home rising faster than abroad", "prices at home rising slower than abroad"),
    "anchor": ("the naira being dearer than prices at home and abroad justify", "the naira being cheaper than prices at home and abroad justify"),
    "oil": ("cheaper oil", "dearer oil"),
    "trade": ("buying more abroad than selling", "selling more abroad than buying"),
    "reserve": ("the rest of the world holding more naira than usual", "the rest of the world holding fewer naira than usual"),
    "rate": ("low interest rates at home", "high interest rates at home"),
    "swing": ("currency traders selling naira", "currency traders buying naira"),
}


def fx_reason(move: float, effects: dict[str, float]) -> str:
    """The main cause of a move, among the causes pushing the same way as the move itself."""
    same = {k: v for k, v in effects.items() if (v > 0) == (move > 0) and v != 0}
    if not same or move == 0:
        return "a quiet quarter for the naira"
    biggest = max(same, key=lambda k: abs(same[k]))
    return _FX_WORDS[biggest][0 if move > 0 else 1]


def _row0(conn: Connection) -> dict:
    return state(conn, 0)


def day_budget_left(conn: Connection, foreign, day) -> int:
    """How much more the foreign investors may trade today, in kobo: about 5% of what everybody else
    traded on an average one of the last five trading days, less what they have traded today."""
    others = _rows(conn, """
        SELECT coalesce(avg(total), 0)::bigint AS average FROM (
            SELECT session_date, sum(price * quantity) AS total FROM market_trades
            WHERE session_date < %s AND buyer_account_id <> %s AND seller_account_id <> %s AND NOT same_owner
            GROUP BY session_date ORDER BY session_date DESC LIMIT 5) recent""", (day, foreign, foreign))[0]["average"]
    budget = max(apply_bps(int(others), data.FOREIGN_DAY_SHARE_BPS), data.FOREIGN_DAY_LEAST_NAIRA * 100)
    today = _rows(conn, "SELECT coalesce(sum(price * quantity), 0)::bigint AS total FROM market_trades"
                        " WHERE session_date = %s AND (buyer_account_id = %s OR seller_account_id = %s)", (day, foreign, foreign))[0]["total"]
    return budget - int(today)


def tilt_now(conn: Connection) -> int:
    """How keen foreign investors are on shares this quarter, from the last close."""
    rows = _rows(conn, "SELECT tilt_bps FROM abroad_results ORDER BY period DESC LIMIT 1")
    return rows[0]["tilt_bps"] if rows else 0


def public(conn: Connection) -> dict:
    """What players may see: every quarter's oil price, exchange rate, trade and foreign investors'
    money, from closes already made. The figures for the quarter now running were set at the last close."""
    rows = _rows(conn, "SELECT * FROM abroad_results ORDER BY period")
    history = []
    for r in rows:
        history.append({
            "period": r["period"] + 1, "period_label": clock.period_label(r["period"] + 1),
            "oil_cents": r["oil_cents"], "fx": r["fx"],
        })
    trade = [{"period": r["period"], "period_label": clock.period_label(r["period"]), "exports": r["exports"],
              "oil_exports": r["oil_exports"], "imports": r["imports"], "oil_royalty": r["oil_royalty"],
              "foreign_inflow": r["foreign_inflow"], "foreign_bought": r["foreign_bought"], "foreign_sold": r["foreign_sold"],
              "foreign_holdings": r["foreign_shares"], "reason": r["reason"]}
             for r in rows if r["period"] >= 1]
    latest = rows[-1] if rows else None
    return {
        "oil_cents": latest["oil_cents"] if latest else data.OIL_START_CENTS,
        "fx": latest["fx"] if latest else data.FX_START,
        "previous_oil_cents": rows[-2]["oil_cents"] if len(rows) > 1 else None,
        "previous_fx": rows[-2]["fx"] if len(rows) > 1 else None,
        "reason": latest["reason"] if latest else "",
        "history": history, "trade": trade,
    }
