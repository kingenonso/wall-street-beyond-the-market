"""The Money Watch (design document, section 10).

A permanent check on money in circulation. Too much money chasing the same
goods makes every price rise and every player's savings worth less. Once a
quarter this module measures the money in existence and gives a reading:

  green   money is growing in step with the economy
  amber   money is growing faster than the economy, or pooling in one place
  red     money is growing far too fast

It never removes money from anybody. On amber or red it asks the Central Bank
to lean harder on its interest rate; on red, new lending is slowed as well.

Separately, any player account that gains money faster than honest play allows
is put on a list for a person to look at. That list is private, and it never
changes the reading: nobody can move the whole country's interest rate by
moving money between accounts.
"""

from __future__ import annotations

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from simulation import ledger
from simulation import world_data as data
from simulation.money import BPS, naira

HOLDERS = (
    ("Households", "a.code LIKE 'households:%%'"),
    ("Companies", "a.kind = 'company' AND c.sector NOT IN ('banking', 'insurance')"),
    ("Banks and insurers", "a.kind = 'company' AND c.sector IN ('banking', 'insurance')"),
    ("Pension funds", "a.code = 'investors:institutions'"),
    ("Private investors", "a.code IN ('investors:founders', 'investors:public')"),
    ("Government", "a.kind IN ('government', 'prize_pool')"),
    ("The exchange", "a.kind = 'exchange'"),
    ("Players", "a.kind = 'player'"),
)
# What each reading asks for.
RATE_EXTRA_BPS = {"green": 0, "amber": 50, "red": 100}
LENDING_FACTOR_BPS = {"green": BPS, "amber": BPS, "red": 5000}


def _rows(conn: Connection, sql: str, params=()) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def holders(conn: Connection) -> dict[str, int]:
    """Where all the naira sits right now, by kind of holder."""
    held = {}
    for name, condition in HOLDERS:
        held[name] = _rows(
            conn,
            "SELECT coalesce(sum(b.balance), 0)::bigint AS total FROM ledger_balances b"
            " JOIN ledger_accounts a ON a.id = b.account_id LEFT JOIN companies c ON c.account_id = a.id"
            f" WHERE b.asset = 'NGN' AND b.balance > 0 AND {condition}",
        )[0]["total"]
    return held


def _percent(bps: int) -> str:
    return f"{bps / 100:.1f}".rstrip("0").rstrip(".") + "%"


def measure(conn: Connection, period: int, *, money: int, money_growth_bps: int, output_growth_bps: int,
            inflation_bps: int = 0) -> dict:
    """Take this quarter's reading and record it."""
    held = holders(conn)
    shares = {name: (amount * BPS // money if money else 0) for name, amount in held.items()}
    year_ago = _rows(conn, "SELECT holders FROM money_watch_results WHERE period = %s", (period - 4,))
    reasons: list[str] = []
    reading = "green"

    def worsen(to: str) -> None:
        nonlocal reading
        if to == "red" or reading == "green":
            reading = to

    # 1. Money against the economy. Money must itself be growing fast: when sales fall in a
    #    slump, the gap opens by itself, and tightening then would only deepen the slump.
    gap = money_growth_bps - output_growth_bps
    if gap > data.MONEY_RED_GAP_BPS and money_growth_bps > data.MONEY_RED_GROWTH_BPS:
        worsen("red")
        reasons.append(f"Money grew {_percent(money_growth_bps)} over the year while the economy's sales grew "
                       f"{_percent(output_growth_bps)}: far too fast.")
    elif gap > data.MONEY_AMBER_GAP_BPS and money_growth_bps > data.MONEY_AMBER_GROWTH_BPS:
        worsen("amber")
        reasons.append(f"Money grew {_percent(money_growth_bps)} over the year while the economy's sales grew "
                       f"{_percent(output_growth_bps)}: faster than the economy.")

    # 2. Prices. Too much money shows up as prices running away, even when sales in naira keep pace
    #    (the extra money itself swells the sales figure).
    if inflation_bps > data.MONEY_RED_INFLATION_BPS:
        worsen("red")
        reasons.append(f"Prices rose {_percent(inflation_bps)} over the year: far too fast.")
    elif inflation_bps > data.MONEY_AMBER_INFLATION_BPS:
        worsen("amber")
        reasons.append(f"Prices rose {_percent(inflation_bps)} over the year: well above what the Central Bank accepts.")

    # 3. Money pooling in one place.
    if year_ago:
        for name, share in shares.items():
            rise = share - year_ago[0]["holders"].get(name, share)
            if rise > data.MONEY_POOLING_AMBER_BPS:
                worsen("amber")
                reasons.append(f"{name} now hold {_percent(share)} of all money, up {_percent(rise)} of the total in a year.")

    # 4. Accounts gaining money faster than honest play allows. These go on a list for a person
    #    to look at. They never change the reading, the interest rate or lending: otherwise a few
    #    players passing money back and forth could switch the whole country's lending off.
    #    What counts is what an account GAINED since the last reading (money in, less money out),
    #    going by when each payment was recorded, so a payment carrying no quarter is still seen.
    since = _rows(conn, "SELECT closed_at FROM money_watch_results WHERE period = %s", (period - 1,))
    limit = naira(data.MONEY_UNUSUAL_RECEIPT_NAIRA)
    unusual = _rows(
        conn,
        "SELECT e.account_id, sum(e.amount)::bigint AS gained FROM ledger_entries e"
        " JOIN ledger_transactions t ON t.id = e.transaction_id JOIN ledger_accounts a ON a.id = e.account_id"
        " WHERE a.kind = 'player' AND e.asset = 'NGN' AND t.kind <> 'starting_grant'"
        " AND (%s::timestamptz IS NULL OR t.created_at > %s::timestamptz)"
        " GROUP BY e.account_id HAVING sum(e.amount) > %s",
        (since[0]["closed_at"] if since else None, since[0]["closed_at"] if since else None, limit),
    )
    for account in unusual:
        conn.execute(
            "INSERT INTO money_watch_flags (period, account_id, reason) VALUES (%s, %s, %s)",
            (period, account["account_id"], f"Gained {account['gained']} kobo in one quarter."),
        )

    # 5. The Treasury's reserve.
    treasury = ledger.balance(conn, ledger.account_id(conn, ledger.TREASURY))
    grants_left = treasury // naira(data.STARTING_GRANT_NAIRA)
    if grants_left < data.MONEY_LOW_GRANTS:
        worsen("amber")
        reasons.append(f"The Treasury's reserve can pay only {grants_left:,} more starting grants.")

    if not reasons:
        reasons.append("Money is growing in step with the economy, and is not pooling in one place.")
    action = {
        "green": "No action needed.",
        "amber": "The Central Bank leans harder on its interest rate: half a point above what its rule alone would set.",
        "red": "The Central Bank leans a full point harder on its interest rate, and new lending is halved next quarter.",
    }[reading]

    conn.execute(
        "INSERT INTO money_watch_results (period, reading, money, money_growth_bps, output_growth_bps, holders,"
        " unusual_accounts, grants_left, reasons, action, paid_to_players) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
        (period, reading, money, money_growth_bps, output_growth_bps, Jsonb(shares), len(unusual), grants_left,
         Jsonb(reasons), action, Jsonb(paid_to_players(conn, period))),
    )
    return {"reading": reading, "reasons": reasons, "action": action, "rate_extra_bps": RATE_EXTRA_BPS[reading],
            "flagged": len(unusual)}


def lending_factor_bps(conn: Connection, period: int) -> int:
    """How freely banks may lend this quarter, given last quarter's reading."""
    last = _rows(conn, "SELECT reading FROM money_watch_results WHERE period = %s", (period - 1,))
    return LENDING_FACTOR_BPS[last[0]["reading"]] if last else BPS


# What counts as money paid to a player for their work or by the game's rules (not from their own investing).
PLAYER_INCOME = ("salary", "starting_grant", "professional_fee", "deposit_interest")


def paid_to_players(conn: Connection, period: int) -> dict:
    """Stage 5's measure: what players were paid in one quarter, by reason, and how many were paid."""
    rows = _rows(conn, "SELECT t.kind, sum(e.amount)::bigint AS total, count(DISTINCT e.account_id) AS players"
                       " FROM ledger_entries e JOIN ledger_transactions t ON t.id = e.transaction_id"
                       " JOIN ledger_accounts a ON a.id = e.account_id WHERE a.kind = 'player' AND e.asset = 'NGN' AND e.amount > 0"
                       " AND t.period = %s AND t.kind = ANY(%s) GROUP BY t.kind", (period, list(PLAYER_INCOME)))
    return {r["kind"]: {"total": r["total"], "players": r["players"]} for r in rows}
