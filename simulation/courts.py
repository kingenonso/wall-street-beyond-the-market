"""Stage 11: the courts, as a docket.

The court's subject is money, its evidence is the ledger, and its remedy is money moving. It does not decide guilt: it
proves a number and makes it be paid. A case is a claim with an amount, the lines of the record that prove the amount,
and a remedy that moves money.

Four kinds of case in this part, all against the market:

  insider            dealing on confidential information (confidential_dealings, recorded since Stage 10B)
  manipulation       ramping and wash trading (market_trades.same_owner, recorded since Stage 4)
  undisclosed_stake  a holding past 5% that was never made public (stake_disclosures against the ledger)
  naked_short        borrowed shares that had to be bought in (short_positions, recorded since Stage 9)

and since then insurance fraud, and on the Floor (16 November 2026) a bank's wrongs to its client (simulation/floor.py):

  front_running      trading on the exchange on the client's side while the client's request was open to the desk
  order_leak         writing the share's code to somebody else, who then traded on the client's side
  collusion          two banks that priced the same request writing to each other while it was open

The regulator is a computer institution with a budget. It pays to prove each case, and half of every fine it wins funds
it, so enforcement is a choice about what is worth proving. A player may bring a case too, but posts a bond and pays the
other side's costs if the claim fails.

Words used here:
  case        a claim against a person, with a number and the lines that prove it
  docket      the list of cases the court has open
  evidence    the lines of the record that prove the number, frozen when the case is opened
  remedy      what the court orders: disgorgement, a fine, costs, a trading ban
  bond        what a player posts to bring a case, returned if the claim is proved
  settlement  what the defendant pays to end a case without a judgment
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from simulation import careers, clock, exchange, ledger, marketview
from simulation import world_data as data
from simulation.money import BPS, apply_bps, naira

REGULATOR = "regulator"
COMPENSATION_FUND = "compensation_fund"
KINDS = ("insider", "manipulation", "undisclosed_stake", "naked_short", "insurance_fraud",
         "front_running", "order_leak", "collusion",       # the Floor's wrongs (16 November 2026)
         "union_bribery",                                    # paying a union leader (17 November 2026)
         "jury_tampering")                                   # offering a juror money, or taking it (17 November 2026)

CASE_SQL = (
    "SELECT k.*, d.display_name AS defendant_name, c.display_name AS claimant_name, co.ticker"
    " FROM court_cases k JOIN players d ON d.id = k.defendant_id"
    " LEFT JOIN players c ON c.id = k.claimant_id LEFT JOIN companies co ON co.id = k.company_id"
)


class CourtError(Exception):
    """Something the court's rules do not allow. The words are for the player."""


def _rows(conn: Connection, sql: str, params=()) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def _one(conn: Connection, sql: str, params=()) -> dict | None:
    rows = _rows(conn, sql, params)
    return rows[0] if rows else None


def _roll(conn: Connection, *parts) -> int:
    """A draw from 0 to 9,999 that nobody can know in advance: it hangs on the world's secret."""
    seed = _one(conn, "SELECT fortune_seed FROM world_state")["fortune_seed"]
    digest = hashlib.sha256(":".join([seed, *(str(p) for p in parts)]).encode()).digest()
    return int.from_bytes(digest[:8], "big") % BPS


def _naira(kobo: int) -> str:
    return f"₦{kobo / 100:,.2f}"


def _quarter_start(conn: Connection, period: int) -> datetime:
    world = _one(conn, "SELECT world_start, weeks_ahead FROM world_state")
    start = clock.effective_start(world["world_start"], world["weeks_ahead"])
    return start + timedelta(days=clock.REAL_DAYS_PER_QUARTER * (max(period, 1) - 1))


# ---------------------------------------------------------------------------
# Setting up
# ---------------------------------------------------------------------------

def ready(conn: Connection) -> bool:
    return _one(conn, "SELECT to_regclass('court_cases') IS NOT NULL AS ok")["ok"] is True


def ensure(conn: Connection) -> None:
    """The regulator's budget and the compensation fund, made the first time the court is used.

    Both are ledger accounts, not tables: every naira the court moves is a ledger transaction (working rule 8).
    """
    if _one(conn, "SELECT 1 AS x FROM ledger_accounts WHERE code = %s", (REGULATOR,)) is None:
        ledger.create_account(conn, kind="government", name="The market regulator's budget", code=REGULATOR)
        ledger.pay_up_to(
            conn, payer=ledger.account_id(conn, ledger.TREASURY), receiver=ledger.account_id(conn, REGULATOR),
            wanted=naira(data.COURT_REGULATOR_START_NAIRA), kind="court_budget",
            memo="The Government's first budget for the market regulator")
    if _one(conn, "SELECT 1 AS x FROM ledger_accounts WHERE code = %s", (COMPENSATION_FUND,)) is None:
        ledger.create_account(conn, kind="escrow", name="The tribunal's compensation fund", code=COMPENSATION_FUND)


# ---------------------------------------------------------------------------
# Reading the docket
# ---------------------------------------------------------------------------

def _owed(row: dict) -> int:
    return max(row["disgorgement"] + row["damages"] + row["fine"] + row["costs"] - row["paid"], 0)


def _case(row: dict) -> dict:
    return {
        "id": row["id"], "kind": row["kind"], "status": row["status"],
        "defendant": row["defendant_name"], "claimant": row["claimant_name"] or "The regulator",
        "ticker": row["ticker"], "amount": row["amount"], "bond": row["bond"],
        "words": row["words"], "evidence": row["evidence"],
        "opened_period": row["opened_period"], "opened_at": row["opened_at"],
        "outcome": row["outcome"], "disgorgement": row["disgorgement"], "damages": row["damages"],
        "fine": row["fine"], "costs": row["costs"], "paid": row["paid"], "owed": _owed(row),
        "ban_quarters": row["ban_quarters"],
        "settle_price": apply_bps(row["amount"], data.COURT_SETTLE_BPS) if row["status"] == "open" else 0,
        "decided_by": row.get("decided_by"), "proved_bps": row.get("proved_bps"), "penalty": row.get("penalty"),
        "defence": row.get("defence"), "claim_note": row.get("claim_note"), "jury_until": row.get("jury_until"),
        "appeal_until": row.get("appeal_until"), "appealed_by": row.get("appealed_by"),
    }


def case(conn: Connection, case_id: int) -> dict | None:
    row = _one(conn, CASE_SQL + " WHERE k.id = %s", (case_id,))
    return {**_case(row), "jury": _jury_of(conn, row)} if row else None


def docket(conn: Connection) -> list[dict]:
    """Every case the court has open, or before a jury. Public: a docket is read by anybody."""
    return [{**_case(row), "jury": _jury_of(conn, row)}
            for row in _rows(conn, CASE_SQL + " WHERE k.status IN ('open', 'jury', 'verdict', 'appeal') ORDER BY k.id DESC")]


def verdicts(conn: Connection, limit: int = 10) -> list[dict]:
    """The latest juries' verdicts, in the open: every vote and its reason (the jurors are not named)."""
    if not _one(conn, "SELECT to_regclass('jurors') IS NOT NULL AS ok")["ok"]:
        return []
    return [{**_case(row), "jury": _jury_of(conn, row)}
            for row in _rows(conn, CASE_SQL + " WHERE k.decided_by = 'jury' ORDER BY k.decided_at DESC LIMIT %s", (limit,))]


def my_cases(conn: Connection, player_id) -> dict:
    """The cases a player is defending, the ones they brought, and their legal record. A side sees who sits on its jury."""
    juries = _one(conn, "SELECT to_regclass('jurors') IS NOT NULL AS ok")["ok"]

    def full(row: dict) -> dict:
        return {**_case(row), "jury": _jury_of(conn, row) if juries else None, "panel": panel_for(conn, row, player_id) if juries else None}
    return {
        "defending": [full(row) for row in _rows(conn, CASE_SQL + " WHERE k.defendant_id = %s ORDER BY k.id DESC",
                                                 (player_id,))],
        "brought": [full(row) for row in _rows(conn, CASE_SQL + " WHERE k.claimant_id = %s ORDER BY k.id DESC",
                                               (player_id,))],
        "record": legal_record(conn, player_id),
        "banned_until": banned_until(conn, player_id),
    }


def legal_record(conn: Connection, player_id, limit: int = 20) -> list[dict]:
    return _rows(conn, "SELECT kind, words, at FROM legal_records WHERE player_id = %s ORDER BY id DESC LIMIT %s",
                 (player_id, limit))


def regulator(conn: Connection) -> dict:
    """The regulator's budget, and what it has done with it."""
    ensure(conn)
    budget = ledger.balance(conn, ledger.account_id(conn, REGULATOR))
    counts = _one(conn, "SELECT count(*) AS brought,"
                        " count(*) FILTER (WHERE status = 'judged') AS won,"
                        " count(*) FILTER (WHERE status = 'settled') AS settled,"
                        " coalesce(sum(fine), 0)::bigint AS fines"
                        " FROM court_cases WHERE claimant_id IS NULL")
    return {"budget": budget, "cost": naira(data.COURT_CASE_COST_NAIRA), **counts}


def banned_until(conn: Connection, player_id) -> int | None:
    row = _one(conn, "SELECT max(until_period) AS until FROM court_bans WHERE player_id = %s", (player_id,))
    return row["until"] if row and row["until"] else None


def check_trade(conn: Connection, account, now: datetime) -> None:
    """A trading ban: no trading until the quarter named. Called before any order is accepted.

    An empire's account is checked against its head, so a banned head cannot trade through the empire instead.
    """
    if not ready(conn):
        return
    row = _one(conn, "SELECT max(b.until_period) AS until FROM court_bans b WHERE b.player_id IN ("
                     " SELECT a.player_id FROM ledger_accounts a WHERE a.id = %s AND a.player_id IS NOT NULL"
                     " UNION"
                     " SELECT e.head_player_id FROM empires e JOIN ledger_accounts a ON a.id = e.account_id"
                     " WHERE a.id = %s AND e.head_player_id IS NOT NULL)", (account, account))
    if row and row["until"]:
        period = careers.world_now(conn, now)["period"]
        if row["until"] > period:
            # The exchange's own error, so the order route refuses it the same way it refuses any other order.
            raise exchange.ExchangeError(
                f"Trading is banned until {clock.period_label(row['until'])}: the tribunal's order.")


# ---------------------------------------------------------------------------
# The evidence: what the record proves, and the number it proves
# ---------------------------------------------------------------------------

def _insider_evidence(conn: Connection, dealing: dict) -> dict | None:
    """The profit on the informed trade: what the account paid against what it got back, from the tip to the close of
    the position. Shares still held are valued at the last price the account traded at."""
    trades = _rows(conn, "SELECT t.id, t.traded_at, t.price, t.quantity, t.buyer_fee, t.seller_fee,"
                         " t.buyer_account_id = %s AS bought, t.seller_account_id = %s AS sold FROM market_trades t"
                         " WHERE t.company_id = %s AND (t.buyer_account_id = %s OR t.seller_account_id = %s)"
                         " AND t.traded_at >= %s ORDER BY t.id",
                   (dealing["account_id"], dealing["account_id"], dealing["company_id"], dealing["account_id"],
                    dealing["account_id"], dealing["at"]))
    if not trades:
        return None
    lots: list[list[int]] = []
    realised = 0
    fees = 0
    for trade in trades:
        # Only the fees this account itself paid: the other side's fee is not its loss.
        fees += (trade["buyer_fee"] if trade["bought"] else 0) + (trade["seller_fee"] if trade["sold"] else 0)
        if trade["bought"]:
            lots.append([trade["price"], trade["quantity"]])
            continue
        left = trade["quantity"]
        while left > 0 and lots:
            price, quantity = lots[0]
            take = min(left, quantity)
            realised += (trade["price"] - price) * take
            left -= take
            if take == quantity:
                lots.pop(0)
            else:
                lots[0][1] -= take
    held = sum(quantity for _, quantity in lots)
    cost_of_held = sum(price * quantity for price, quantity in lots)
    profit = realised + held * trades[-1]["price"] - cost_of_held - fees
    if profit <= 0:
        return None
    lines = [{"what": "trade", "id": t["id"], "at": t["traded_at"].isoformat(),
              "side": "both" if t["bought"] and t["sold"] else ("bought" if t["bought"] else "sold"),
              "price": t["price"], "quantity": t["quantity"],
              "amount": t["price"] * t["quantity"]} for t in trades]
    return {"amount": profit, "company_id": dealing["company_id"], "ticker": dealing["ticker"], "lines": lines,
            "words": f"Dealt on confidential information about {dealing['ticker']}: {_naira(profit)} of profit on the "
                     f"informed trade, from the tip on {dealing['at']:%d %B %Y}."}


def _manipulation_evidence(conn: Connection, account, company_id, since: datetime, until: datetime,
                           ticker: str) -> dict | None:
    """Wash trading first: trades where the same account was on both sides. The number is the turnover that was not
    real. Failing that, a ramp: buys that lift the price, then sales into the rise."""
    wash = _rows(conn, "SELECT t.id, t.traded_at, t.price, t.quantity FROM market_trades t"
                       " WHERE t.same_owner AND t.buyer_account_id = %s AND t.company_id = %s"
                       " AND t.traded_at >= %s AND t.traded_at <= %s ORDER BY t.id",
                 (account, company_id, since, until))
    if len(wash) >= data.COURT_WASH_TRADES:
        turnover = sum(t["price"] * t["quantity"] for t in wash)
        lines = [{"what": "wash trade", "id": t["id"], "at": t["traded_at"].isoformat(), "price": t["price"],
                  "quantity": t["quantity"], "amount": t["price"] * t["quantity"]} for t in wash]
        return {"amount": turnover, "company_id": company_id, "ticker": ticker, "lines": lines,
                "words": f"Traded with itself in {ticker} {len(wash)} times in one quarter: {_naira(turnover)} of trades "
                         f"that were the same person on both sides."}
    return _ramp_evidence(conn, account, company_id, since, until, ticker)


def _ramp_evidence(conn: Connection, account, company_id, since: datetime, until: datetime,
                   ticker: str) -> dict | None:
    trades = _rows(conn, "SELECT t.id, t.traded_at, t.price, t.quantity, t.buyer_account_id = %s AS bought"
                         " FROM market_trades t WHERE t.company_id = %s"
                         " AND (t.buyer_account_id = %s OR t.seller_account_id = %s)"
                         " AND t.traded_at >= %s AND t.traded_at <= %s ORDER BY t.id",
                   (account, company_id, account, account, since, until))
    buys = [t for t in trades if t["bought"]]
    sells = [t for t in trades if not t["bought"]]
    if len(buys) < data.COURT_RAMP_BUYS or not sells:
        return None
    before = _one(conn, "SELECT price FROM market_trades WHERE company_id = %s AND traded_at < %s"
                        " ORDER BY id DESC LIMIT 1", (company_id, since))
    if before is None:
        return None
    gain = sum((t["price"] - before["price"]) * t["quantity"] for t in sells if t["price"] > before["price"])
    if gain <= 0:
        return None
    lines = [{"what": "bought" if t["bought"] else "sold", "id": t["id"], "at": t["traded_at"].isoformat(),
              "price": t["price"], "quantity": t["quantity"], "amount": t["price"] * t["quantity"]} for t in trades]
    return {"amount": gain, "company_id": company_id, "ticker": ticker, "lines": lines,
            "words": f"Bought {ticker} {len(buys)} times to lift the price, then sold into the rise: {_naira(gain)} of "
                     f"gain on sales above the {_naira(before['price'])} the share stood at before the campaign."}


def _stake_wrongs(conn: Connection, period: int, now: datetime) -> list[dict]:
    """A holding past a 5% step that was never made public. The number is the value of the step kept out of sight."""
    day, _ = exchange.session_of(now)
    prices = {s["ticker"]: s["price"] for s in marketview._shares(conn, day)}
    wrongs = []
    for row in _rows(conn, "SELECT e.id AS empire_id, e.name AS empire, e.head_player_id, c.id AS company_id,"
                           " c.ticker,"
                           " (SELECT r.shares_in_issue FROM company_results r WHERE r.company_id = c.id"
                           "  ORDER BY r.period DESC LIMIT 1) AS shares_in_issue,"
                           " sum(b.balance)::bigint AS shares, coalesce(d.bps, 0) AS disclosed"
                           " FROM ledger_balances b JOIN ledger_accounts a ON a.id = b.account_id"
                           " JOIN empires e ON e.account_id = a.id"
                           " JOIN companies c ON b.asset = 'SHR-' || c.ticker"
                           " LEFT JOIN stake_disclosures d ON d.empire_id = e.id AND d.company_id = c.id"
                           " WHERE b.balance > 0 AND e.head_player_id IS NOT NULL GROUP BY 1, 2, 3, 4, 5, 6, 8"):
        if not row["shares_in_issue"]:
            continue
        held = row["shares"] * BPS // row["shares_in_issue"]
        step = held // data.COURT_STAKE_STEP_BPS * data.COURT_STAKE_STEP_BPS
        if step <= row["disclosed"]:
            continue
        price = prices.get(row["ticker"])
        if not price:
            continue
        hidden = step - row["disclosed"]
        amount = hidden * row["shares_in_issue"] // BPS * price
        if amount <= 0:
            continue
        wrongs.append({
            "kind": "undisclosed_stake", "key": f"stake:{row['empire_id']}:{row['company_id']}:{period}",
            "defendant_id": row["head_player_id"], "company_id": row["company_id"], "ticker": row["ticker"],
            "amount": amount,
            "lines": [{"what": "holding", "empire": row["empire"], "ticker": row["ticker"], "shares": row["shares"],
                       "held_bps": held, "disclosed_bps": row["disclosed"], "hidden_bps": hidden, "price": price,
                       "amount": amount}],
            "words": f"Held {held / 100:.1f}% of {row['ticker']} and made public only {row['disclosed'] / 100:.1f}%: "
                     f"{_naira(amount)} of stake kept out of sight."})
    return wrongs


def _short_wrongs(conn: Connection, since: datetime) -> list[dict]:
    """Borrowed shares that had to be bought in. The number is the profit on the uncovered short, or what forcing the
    buy-in cost if the short lost money."""
    wrongs = []
    for row in _rows(conn, "SELECT s.id, s.shares, s.opened_price, s.closed_price, s.closed_at, a.player_id,"
                           " s.company_id, c.ticker FROM short_positions s"
                           " JOIN ledger_accounts a ON a.id = s.borrower JOIN companies c ON c.id = s.company_id"
                           " WHERE s.status = 'bought_in' AND s.closed_at >= %s AND a.player_id IS NOT NULL",
                     (since,)):
        profit = max((row["opened_price"] - row["closed_price"]) * row["shares"], 0)
        premium = apply_bps(row["closed_price"] * row["shares"], data.COURT_SHORT_PREMIUM_BPS)
        amount = profit if profit > 0 else premium
        if amount <= 0:
            continue
        wrongs.append({
            "kind": "naked_short", "key": f"short:{row['id']}", "defendant_id": row["player_id"],
            "company_id": row["company_id"], "ticker": row["ticker"], "amount": amount,
            "lines": [{"what": "short", "id": row["id"], "ticker": row["ticker"], "shares": row["shares"],
                       "opened_price": row["opened_price"], "bought_in_at": row["closed_price"],
                       "at": row["closed_at"].isoformat(), "profit": profit, "premium": premium, "amount": amount}],
            "words": (f"Short of {row['shares']:,} {row['ticker']} shares that had to be bought in at "
                      f"{_naira(row['closed_price'])}: {_naira(amount)} "
                      + ("of profit on the uncovered short." if profit > 0 else "of cost in forcing the buy-in."))})
    return wrongs


def _wrongs(conn: Connection, period: int, now: datetime) -> list[dict]:
    """Every recorded wrong the court has not yet tried, with the lines that prove its number.

    A wrong is tried once: a case already opened for it, or still open against the same person over the same company,
    is not brought again. That is what stops a continuing breach from filling the docket.
    """
    since = _quarter_start(conn, period - data.COURT_WINDOW_QUARTERS + 1)
    quarter = _quarter_start(conn, period)
    tried = {r["key"] for r in _rows(conn, "SELECT evidence->>'key' AS key FROM court_cases")}
    open_now = {(r["kind"], str(r["defendant_id"]), str(r["company_id"]))
                for r in _rows(conn, "SELECT kind, defendant_id, company_id FROM court_cases WHERE status = 'open'")}
    wrongs: list[dict] = []
    seen: set = set()          # one case per person per company per kind, even within one look at the record

    def add(wrong: dict) -> None:
        key = (wrong["kind"], str(wrong["defendant_id"]), str(wrong["company_id"]))
        if wrong["key"] in tried or key in open_now or key in seen:
            return
        tried.add(wrong["key"])
        seen.add(key)
        wrongs.append(wrong)

    for dealing in _rows(conn, "SELECT d.id, d.player_id, d.account_id, d.company_id, d.at, c.ticker"
                               " FROM confidential_dealings d JOIN companies c ON c.id = d.company_id"
                               " WHERE d.at >= %s ORDER BY d.id", (since,)):
        found = _insider_evidence(conn, dealing)
        if found:
            add({"kind": "insider", "key": f"insider:{dealing['id']}", "defendant_id": dealing["player_id"], **found})

    for row in _rows(conn, "SELECT DISTINCT t.buyer_account_id AS account, t.company_id, a.player_id, c.ticker"
                           " FROM market_trades t JOIN ledger_accounts a ON a.id = t.buyer_account_id"
                           " JOIN companies c ON c.id = t.company_id"
                           " WHERE t.same_owner AND t.traded_at >= %s AND a.player_id IS NOT NULL", (quarter,)):
        account = row.get("account")
        if account is None:
            continue
        found = _manipulation_evidence(conn, account, row["company_id"], quarter, now, row["ticker"])
        if found:
            add({"kind": "manipulation", "key": f"manipulation:{account}:{row['company_id']}:{period}",
                 "defendant_id": row["player_id"], **found})

    for row in _rows(conn, "SELECT t.buyer_account_id AS account, t.company_id, a.player_id, c.ticker, count(*) AS buys"
                           " FROM market_trades t JOIN ledger_accounts a ON a.id = t.buyer_account_id"
                           " JOIN companies c ON c.id = t.company_id"
                           " WHERE t.traded_at >= %s AND a.player_id IS NOT NULL"
                           " GROUP BY 1, 2, 3, 4 HAVING count(*) >= %s", (quarter, data.COURT_RAMP_BUYS)):
        account = row.get("account")
        if account is None:
            continue
        found = _ramp_evidence(conn, account, row["company_id"], quarter, now, row["ticker"])
        if found:
            add({"kind": "manipulation", "key": f"ramp:{row['account']}:{row['company_id']}:{period}",
                 "defendant_id": row["player_id"], **found})

    for wrong in _stake_wrongs(conn, period, now) + _short_wrongs(conn, since):
        add(wrong)
    from simulation import floor               # the Floor's wrongs (16 November 2026)
    for wrong in floor.wrongs(conn, since, now):
        add(wrong)
    from simulation import unions              # paying a union leader (17 November 2026)
    for wrong in unions.wrongs(conn, since, now):
        add(wrong)
    for wrong in tampering_wrongs(conn, since):  # tampering with a jury (17 November 2026)
        add(wrong)
    return [w for w in wrongs if w["amount"] >= naira(data.COURT_MIN_CLAIM_NAIRA)]


def _evidence_of(wrong: dict) -> dict:
    return {"key": wrong["key"], "total": wrong["amount"], "lines": wrong["lines"]}


# ---------------------------------------------------------------------------
# Opening a case
# ---------------------------------------------------------------------------

def open_case(conn: Connection, *, kind: str, defendant_id, claimant_id, company_id, amount: int, evidence: dict,
              words: str, period: int, now: datetime, bond: int = 0) -> int:
    if kind not in KINDS:
        raise CourtError("The tribunal hears ten kinds of case: dealing on confidential information, manipulation, an undisclosed "
                         "stake, a naked short, insurance fraud, on the Floor trading ahead of a client, passing on a client's "
                         "order and banks agreeing their prices, paying a union leader, and tampering with a jury.")
    if amount < naira(data.COURT_MIN_CLAIM_NAIRA):
        raise CourtError(f"A claim of {_naira(amount)} is not worth the tribunal's time.")
    # The row is read by name: the website's connection hands back dictionaries, a test's hands back tuples, and the
    # court must work on both.
    row = _one(
        conn,
        "INSERT INTO court_cases (kind, defendant_id, claimant_id, company_id, amount, bond, evidence, words,"
        " opened_period, opened_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
        (kind, defendant_id, claimant_id, company_id, amount, bond, Jsonb(evidence), words, period, now),
    )
    return row["id"]


def _regulator_brings(conn: Connection, wrong: dict, period: int, now: datetime) -> int | None:
    """The regulator brings a case, if its budget can pay to prove it."""
    cost = naira(data.COURT_CASE_COST_NAIRA)
    budget = ledger.account_id(conn, REGULATOR)
    if ledger.balance(conn, budget) < cost:
        return None
    ledger.transfer(conn, payer=budget, receiver=ledger.account_id(conn, ledger.TREASURY), amount=cost,
                    kind="court_cost", memo=f"The cost of proving a case: {wrong['words'][:80]}", period=period)
    return open_case(conn, kind=wrong["kind"], defendant_id=wrong["defendant_id"], claimant_id=None,
                     company_id=wrong["company_id"], amount=wrong["amount"], evidence=_evidence_of(wrong),
                     words=wrong["words"], period=period, now=now)


def _standing(conn: Connection, player_id, wrong: dict) -> str | None:
    """Whether a player may bring this case, and if not, why. The regulator may bring any of them; a player only the
    ones they were on the other side of."""
    if wrong["kind"] in ("manipulation", "naked_short", "collusion"):
        return "Only the regulator can bring that kind of case."
    account = ledger.player_account_id(conn, player_id)
    if account is None:
        return "You have no account to bring a case from."
    if wrong["kind"] == "jury_tampering":
        if wrong.get("victim_player") and str(wrong["victim_player"]) == str(player_id):
            return None
        return "Only the regulator, or the other side of the case that was tampered with, can bring that case."
    if wrong["kind"] == "union_bribery":
        if wrong.get("victim_player") and str(wrong["victim_player"]) == str(player_id):
            return None
        return "Only the regulator, or the head of the empire whose company was hit, can bring that case."
    if wrong["kind"] in ("front_running", "order_leak"):
        return None if str(wrong.get("victim_account")) == str(account) else "Only the client who was wronged can bring that case."
    if wrong["kind"] == "insider":
        side = wrong["lines"][0].get("side") if wrong["lines"] else None
        other_side = _one(conn, "SELECT 1 AS x FROM market_trades t WHERE t.company_id = %s"
                                " AND ((%s = 'bought' AND t.seller_account_id = %s)"
                                "   OR (%s = 'sold' AND t.buyer_account_id = %s)) LIMIT 1",
                          (wrong["company_id"], side, account, side, account))
        if other_side is None:
            return "Only somebody who traded the other side of that dealing can bring the case."
    if wrong["kind"] == "undisclosed_stake":
        holding = _one(conn, "SELECT 1 AS x FROM ledger_balances b JOIN ledger_accounts a ON a.id = b.account_id"
                             " WHERE a.player_id = %s AND b.asset = %s AND b.balance > 0 LIMIT 1",
                       (player_id, f"SHR-{wrong['ticker']}"))
        if holding is None:
            return "Only a shareholder of that company can bring the case."
    return None


def claims(conn: Connection, player_id, period: int, now: datetime) -> list[dict]:
    """The cases a player could bring: the recorded wrongs they were on the other side of, with the bond each needs."""
    out = []
    for wrong in _wrongs(conn, period, now):
        if str(wrong["defendant_id"]) == str(player_id) or _standing(conn, player_id, wrong) is not None:
            continue
        defendant = _one(conn, "SELECT display_name FROM players WHERE id = %s", (wrong["defendant_id"],))
        out.append({
            "kind": wrong["kind"], "defendant_id": wrong["defendant_id"], "defendant": defendant["display_name"],
            "company_id": wrong["company_id"], "ticker": wrong["ticker"], "amount": wrong["amount"],
            "bond": max(apply_bps(wrong["amount"], data.COURT_BOND_BPS), naira(data.COURT_BOND_FLOOR_NAIRA)),
            "words": wrong["words"],
        })
    return out


def bring(conn: Connection, player_id, *, kind: str, defendant_id, company_id=None, period: int,
          now: datetime) -> dict:
    """A player brings a case. The court finds the evidence and the number itself: a player cannot name a number the
    record does not support. The bond is a tenth of the claim, and is lost if the claim fails."""
    if kind not in KINDS:
        raise CourtError("The tribunal hears ten kinds of case: dealing on confidential information, manipulation, an undisclosed "
                         "stake, a naked short, insurance fraud, on the Floor trading ahead of a client, passing on a client's "
                         "order and banks agreeing their prices, paying a union leader, and tampering with a jury.")
    if str(player_id) == str(defendant_id):
        raise CourtError("You cannot bring a case against yourself.")
    ensure(conn)
    wrong = next((w for w in _wrongs(conn, period, now)
                  if w["kind"] == kind and str(w["defendant_id"]) == str(defendant_id)
                  and (company_id is None or str(w["company_id"]) == str(company_id))), None)
    if wrong is None:
        raise CourtError("The record does not support a claim of that kind against that person.")
    refused = _standing(conn, player_id, wrong)
    if refused:
        raise CourtError(refused)
    bond = max(apply_bps(wrong["amount"], data.COURT_BOND_BPS), naira(data.COURT_BOND_FLOOR_NAIRA))
    account = ledger.player_account_id(conn, player_id)
    if account is None or ledger.balance(conn, account) < bond:
        raise CourtError(f"Bringing this case needs a bond of {_naira(bond)}, which you do not have.")
    ledger.transfer(conn, payer=account, receiver=ledger.account_id(conn, ledger.TREASURY), amount=bond,
                    kind="court_bond", memo=f"A bond for a case of {kind}", period=period)
    case_id = open_case(conn, kind=kind, defendant_id=defendant_id, claimant_id=player_id,
                        company_id=wrong["company_id"], amount=wrong["amount"], evidence=_evidence_of(wrong),
                        words=wrong["words"], period=period, now=now, bond=bond)
    return case(conn, case_id)


# ---------------------------------------------------------------------------
# Answering a case: settle, or fight
# ---------------------------------------------------------------------------

def _claimant_account(conn: Connection, row: dict):
    """Where a remedy is paid: the claimant, or the compensation fund when the regulator brought the case."""
    if row["claimant_id"] is not None:
        account = ledger.player_account_id(conn, row["claimant_id"])
        if account is not None:
            return account
    return ledger.account_id(conn, COMPENSATION_FUND)


def respond(conn: Connection, player_id, case_id: int, choice: str, period: int, now: datetime, defence: str = "") -> dict:
    """The defendant answers a case: settle it at once, let the judge decide, or ask for a jury of players."""
    row = _one(conn, CASE_SQL + " WHERE k.id = %s", (case_id,))
    if row is None:
        raise CourtError("There is no such case.")
    if row["status"] != "open":
        raise CourtError("That case has already been decided.")
    if str(row["defendant_id"]) != str(player_id):
        raise CourtError("Only the person the case is against can answer it.")
    ensure(conn)
    if choice == "settle":
        return _settle(conn, row, period, now)
    if choice == "fight":
        return judge(conn, case_id, period, now)
    if choice == "jury":
        return summon_jury(conn, row, period, now, defence)
    raise CourtError("A case is answered by settling it, by letting the judge decide, or by asking for a jury.")


def _return_bond(conn: Connection, row: dict, period: int, now: datetime) -> None:
    """A player's bond comes back when the claim is proved: it is a deposit, not a fee. The regulator posts none."""
    if row["claimant_id"] is None or not row["bond"]:
        return
    account = ledger.player_account_id(conn, row["claimant_id"])
    if account is None:
        return
    ledger.transfer(conn, payer=ledger.account_id(conn, ledger.TREASURY), receiver=account, amount=row["bond"],
                    kind="court_bond_return", memo=f"The bond returned on case {row['id']}", period=period)


def _settle(conn: Connection, row: dict, period: int, now: datetime) -> dict:
    price = apply_bps(row["amount"], data.COURT_SETTLE_BPS)
    account = ledger.player_account_id(conn, row["defendant_id"])
    if account is None or ledger.balance(conn, account) < price:
        raise CourtError(f"Settling costs {_naira(price)} at once, which you do not have. The case will be judged "
                         "instead.")
    ledger.transfer(conn, payer=account, receiver=_claimant_account(conn, row), amount=price, kind="court_settlement",
                    memo=f"Settlement of case {row['id']}", period=period)
    conn.execute("UPDATE court_cases SET status = 'settled', outcome = 'settled', decided_at = %s, paid = %s"
                 " WHERE id = %s", (now, price, row["id"]))
    conn.execute("INSERT INTO court_payments (case_id, amount, at) VALUES (%s, %s, %s)", (row["id"], price, now))
    _return_bond(conn, row, period, now)
    _legal(conn, row["defendant_id"], "settled",
           f"Settled a claim of {_naira(row['amount'])} for {_naira(price)}: {row['words']}", now)
    return case(conn, row["id"])


def judge(conn: Connection, case_id: int, period: int, now: datetime, *, proved_bps: int = BPS, penalty: str = "standard",
          by: str = "judge") -> dict:
    """The verdict, which reads like arithmetic: the profit is disgorged, a fine is added, the loser pays the winner's
    costs, and a manipulation or a naked short carries a trading ban. A jury may find only part of the claim proved,
    or none of it, and may ask for a lenient or a harsh penalty (juries, 17 November 2026); the judge finds it all
    proved, at the standard penalty, as before."""
    row = _one(conn, CASE_SQL + " WHERE k.id = %s", (case_id,))
    if row is None:
        raise CourtError("There is no such case.")
    if row["status"] not in ("open", "jury", "verdict", "appeal"):
        raise CourtError("That case has already been decided.")
    if proved_bps <= 0:
        return _acquit(conn, row, period, now, by)
    amount = apply_bps(row["amount"], proved_bps)
    disgorgement = amount if row["kind"] in ("insider", "undisclosed_stake", "front_running", "order_leak") else 0
    fine = apply_bps(apply_bps(amount, data.COURT_FINE_BPS[row["kind"]]), data.JURY_PENALTY_BPS[penalty])
    costs = apply_bps(amount, data.COURT_COSTS_BPS)
    ban = data.COURT_BAN_QUARTERS.get(row["kind"], 0)
    ban = ban // 2 if penalty == "lenient" else ban + 2 if penalty == "harsh" and ban else ban
    conn.execute("UPDATE court_cases SET status = 'judged', outcome = 'judged', decided_at = %s, disgorgement = %s,"
                 " fine = %s, costs = %s, ban_quarters = %s, decided_by = %s, proved_bps = %s, penalty = %s WHERE id = %s",
                 (now, disgorgement, fine, costs, ban, by, proved_bps, penalty, case_id))
    found = "" if proved_bps == BPS else f" (the jury found {proved_bps // 100}% of the claim proved)"
    _legal(conn, row["defendant_id"], "judged",
           f"Judged{' by a jury' if by == 'jury' else ''} to pay {_naira(disgorgement + fine + costs)}{found}: {row['words']}", now)
    conn.execute("UPDATE players SET reputation = greatest(reputation - %s, 0) WHERE id = %s",
                 (data.COURT_REPUTATION, row["defendant_id"]))
    if ban:
        conn.execute("INSERT INTO court_bans (player_id, case_id, until_period, at) VALUES (%s, %s, %s, %s)",
                     (row["defendant_id"], case_id, period + ban, now))
    _return_bond(conn, row, period, now)
    pay(conn, case_id, period, now)
    return case(conn, case_id)


def _acquit(conn: Connection, row: dict, period: int, now: datetime, by: str) -> dict:
    """Not proved. The defendant owes nothing. A player who brought it loses the bond to the defendant, as the costs
    of defending; the regulator pays the defendant's costs from its budget, as far as it can."""
    conn.execute("UPDATE court_cases SET status = 'judged', outcome = 'acquitted', decided_at = %s, decided_by = %s, proved_bps = 0"
                 " WHERE id = %s", (now, by, row["id"]))
    defendant = ledger.player_account_id(conn, row["defendant_id"])
    if defendant is not None:
        if row["claimant_id"] is not None and row["bond"]:
            ledger.transfer(conn, payer=ledger.account_id(conn, ledger.TREASURY), receiver=defendant, amount=row["bond"],
                            kind="court_bond_forfeit", memo=f"The claimant's bond on case {row['id']}, to the acquitted defendant",
                            period=period)
        elif row["claimant_id"] is None:
            costs = min(apply_bps(row["amount"], data.COURT_COSTS_BPS), max(ledger.balance(conn, ledger.account_id(conn, REGULATOR)), 0))
            if costs > 0:
                ledger.transfer(conn, payer=ledger.account_id(conn, REGULATOR), receiver=defendant, amount=costs,
                                kind="court_costs", memo=f"The defendant's costs on case {row['id']}, acquitted", period=period)
    _legal(conn, row["defendant_id"], "acquitted", f"Acquitted{' by a jury' if by == 'jury' else ''}: {row['words']}", now)
    return case(conn, row["id"])


# ---------------------------------------------------------------------------
# Juries (owner, 17 November 2026)
# ---------------------------------------------------------------------------

PROVED_CHOICES = (0, 2500, 5000, 7500, 10_000)
PENALTIES = ("lenient", "standard", "harsh")


def _eligible(conn: Connection, row: dict) -> list:
    """Players who may sit: a career at least a few levels in, not either side, not in either side's empire, not banned,
    and not defending a case of their own."""
    sides = [row["defendant_id"]] + ([row["claimant_id"]] if row["claimant_id"] else [])
    return [r["id"] for r in _rows(
        conn,
        "SELECT DISTINCT p.id FROM players p JOIN careers c ON c.player_id = p.id"
        " WHERE c.experience >= %s AND p.id <> ALL(%s::uuid[])"
        " AND NOT EXISTS (SELECT 1 FROM empire_seats s JOIN empire_seats t ON t.empire_id = s.empire_id"
        "                 WHERE s.player_id = p.id AND t.player_id = ANY(%s::uuid[]))"
        " AND NOT EXISTS (SELECT 1 FROM court_cases k WHERE k.defendant_id = p.id AND k.status IN ('open', 'jury', 'verdict', 'appeal'))"
        " AND NOT EXISTS (SELECT 1 FROM court_bans b WHERE b.player_id = p.id AND b.until_period >= %s)"
        " ORDER BY p.id",
        (careers.experience_for(data.JURY_MIN_LEVEL), sides, sides, row["opened_period"]))]


def summon_jury(conn: Connection, row: dict, period: int, now: datetime, defence: str = "") -> dict:
    """The defendant asks for a jury. Five players with no tie to either side are summoned, chosen by a draw nobody can
    know in advance. With too few who may sit, the judge decides as before."""
    defence = " ".join((defence or "").split())
    if len(defence) > 600:
        raise CourtError("A statement to the jury is at most 600 characters.")
    if len(_pool(conn, row)) < data.JURY_QUORUM:
        return judge(conn, row["id"], period, now)
    until = now + timedelta(hours=data.JURY_HOURS)
    conn.execute("UPDATE court_cases SET status = 'jury', jury_until = %s, defence = %s WHERE id = %s", (until, defence or None, row["id"]))
    _draw(conn, row, 1, data.JURY_SIZE, now)
    return case(conn, row["id"])


def _pool(conn: Connection, row: dict) -> list:
    """Who may still be drawn for a case: the eligible, less everybody drawn for it before (in either round), in an order
    fixed by a draw nobody can know in advance."""
    drawn = {r["player_id"] for r in _rows(conn, "SELECT player_id FROM jurors WHERE case_id = %s", (row["id"],))} \
        if _one(conn, "SELECT to_regclass('jurors') IS NOT NULL AS ok")["ok"] else set()
    pool = [p for p in _eligible(conn, row) if p not in drawn]
    pool.sort(key=lambda p: _roll(conn, "jury", row["id"], p))
    return pool


def _draw(conn: Connection, row: dict, round_: int, count: int, now: datetime) -> int:
    seat = _one(conn, "SELECT coalesce(max(seat), 0) AS n FROM jurors WHERE case_id = %s", (row["id"],))["n"]
    drawn = 0
    for player in _pool(conn, row)[:count]:
        seat += 1
        conn.execute("INSERT INTO jurors (case_id, player_id, seat, summoned_at, round) VALUES (%s, %s, %s, %s, %s)",
                     (row["id"], player, seat, now, round_))
        drawn += 1
    return drawn


def _round(row: dict) -> int:
    return 2 if row.get("appealed_by") else 1


def _side(row: dict, player_id) -> str | None:
    if str(row["defendant_id"]) == str(player_id):
        return "defendant"
    if row["claimant_id"] is not None and str(row["claimant_id"]) == str(player_id):
        return "claimant"
    return None


def claimant_note(conn: Connection, player_id, case_id: int, note: str) -> dict:
    """A player who brought the case may put a statement before the jury while it sits."""
    row = _one(conn, CASE_SQL + " WHERE k.id = %s", (case_id,))
    if row is None or row["status"] != "jury":
        raise CourtError("There is no jury sitting on that case.")
    if row["claimant_id"] is None or str(row["claimant_id"]) != str(player_id):
        raise CourtError("Only the player who brought the case can speak for the claim.")
    note = " ".join((note or "").split())
    if not note or len(note) > 600:
        raise CourtError("A statement to the jury is between 1 and 600 characters.")
    conn.execute("UPDATE court_cases SET claim_note = %s WHERE id = %s", (note, case_id))
    return case(conn, case_id)


def vote(conn: Connection, player_id, case_id: int, proved_bps: int, penalty: str, reason: str, now: datetime) -> dict:
    """A juror votes, once: how much of the claim the record proves, and the penalty. A vote cannot be changed."""
    if proved_bps not in PROVED_CHOICES:
        raise CourtError("Find all of the claim proved, three quarters, half, a quarter, or none of it.")
    if penalty not in PENALTIES:
        raise CourtError("Ask for a lenient, a standard or a harsh penalty.")
    reason = " ".join((reason or "").split())
    if len(reason) > 300:
        raise CourtError("A reason is at most 300 characters.")
    seat = _one(conn, "SELECT j.*, k.status, k.jury_until, k.appealed_by FROM jurors j JOIN court_cases k ON k.id = j.case_id"
                      " WHERE j.case_id = %s AND j.player_id = %s FOR UPDATE OF j", (case_id, player_id))
    if seat is None or seat["struck_by"] is not None or seat["round"] != _round(seat):
        raise CourtError("You are not on that jury.")
    if seat["status"] not in ("jury", "appeal") or seat["jury_until"] <= now:
        raise CourtError("That jury has finished sitting.")
    if seat["voted_at"] is not None:
        raise CourtError("You have already voted, and a vote cannot be changed.")
    conn.execute("UPDATE jurors SET proved_bps = %s, penalty = %s, reason = %s, voted_at = %s WHERE case_id = %s AND player_id = %s",
                 (proved_bps, penalty, reason or None, now, case_id, player_id))
    left = _one(conn, "SELECT count(*) FILTER (WHERE voted_at IS NULL) AS n FROM jurors WHERE case_id = %s AND round = %s"
                      " AND struck_by IS NULL", (case_id, seat["round"]))["n"]
    if left == 0:
        verdict(conn, case_id, now)
    return case(conn, case_id)


def _middle(values: list[int]) -> int:
    values = sorted(values)
    return values[(len(values) - 1) // 2]          # the lower middle of an even count: doubt goes to the defendant


def verdict(conn: Connection, case_id: int, now: datetime) -> dict:
    """The jury's verdict: the middle vote on how much is proved and on the penalty. Every juror who voted is paid the
    fee by the Treasury; a vote that matches the verdict earns a point of reputation. Too few votes: the judge decides.
    A first jury's verdict waits a day for an appeal (part 2); an appeal jury's verdict is final."""
    period = careers.world_now(conn, now)["period"]
    row = _one(conn, CASE_SQL + " WHERE k.id = %s", (case_id,))
    round_ = _round(row)
    votes = _rows(conn, "SELECT * FROM jurors WHERE case_id = %s AND round = %s AND struck_by IS NULL AND voted_at IS NOT NULL"
                        " ORDER BY seat", (case_id, round_))
    _tell_offers(conn, row, round_, now)
    if len(votes) < data.JURY_QUORUM:
        if round_ == 2:                                   # an appeal jury that does not sit: the first verdict stands
            done = judge(conn, case_id, period, now, proved_bps=row["first_proved_bps"], penalty=row["first_penalty"], by="jury")
        else:
            done = judge(conn, case_id, period, now)
    else:
        proved = _middle([v["proved_bps"] for v in votes])
        penalty = PENALTIES[_middle([PENALTIES.index(v["penalty"]) for v in votes])]
        for v in votes:
            agreed = v["proved_bps"] == proved and (proved == 0 or v["penalty"] == penalty)
            conn.execute("UPDATE jurors SET agreed = %s WHERE case_id = %s AND player_id = %s", (agreed, case_id, v["player_id"]))
            if agreed:
                conn.execute("UPDATE players SET reputation = least(reputation + %s, 100) WHERE id = %s",
                             (data.JURY_FAIR_REPUTATION, v["player_id"]))
        if round_ == 1:
            conn.execute("UPDATE court_cases SET status = 'verdict', proved_bps = %s, penalty = %s, appeal_until = %s WHERE id = %s",
                         (proved, penalty, now + timedelta(hours=data.JURY_APPEAL_HOURS), case_id))
            done = case(conn, case_id)
        else:
            done = judge(conn, case_id, period, now, proved_bps=proved, penalty=penalty, by="jury")
            _refund_appeal(conn, row, proved, penalty, period)
    fee = naira(data.JURY_FEE_NAIRA)
    for v in votes:
        account = ledger.player_account_id(conn, v["player_id"])
        if account is not None:
            ledger.transfer(conn, payer=ledger.account_id(conn, ledger.TREASURY), receiver=account, amount=fee, kind="jury_fee",
                            memo=f"A juror's fee, case {case_id}", period=period)
            conn.execute("UPDATE jurors SET fee = %s WHERE case_id = %s AND player_id = %s", (fee, case_id, v["player_id"]))
    return done


def _better_for(side: str, first: tuple[int, str], second: tuple[int, str]) -> bool:
    """Did the appeal win the appellant anything? The defendant wants less proved or a lighter penalty; the claimant more."""
    (p1, k1), (p2, k2) = first, second
    if side == "defendant":
        return p2 < p1 or (p2 == p1 and p2 > 0 and PENALTIES.index(k2) < PENALTIES.index(k1))
    return p2 > p1 or (p2 == p1 and p2 > 0 and PENALTIES.index(k2) > PENALTIES.index(k1))


def _refund_appeal(conn: Connection, row: dict, proved: int, penalty: str, period: int) -> None:
    if not row["appeal_fee"]:
        return
    if not _better_for(row["appealed_by"], (row["first_proved_bps"], row["first_penalty"]), (proved, penalty)):
        return
    who = row["defendant_id"] if row["appealed_by"] == "defendant" else row["claimant_id"]
    account = ledger.player_account_id(conn, who)
    if account is not None:
        ledger.transfer(conn, payer=ledger.account_id(conn, ledger.TREASURY), receiver=account, amount=row["appeal_fee"],
                        kind="court_appeal_refund", memo=f"The appeal fee on case {row['id']}, returned: the appeal won", period=period)


def appeal(conn: Connection, player_id, case_id: int, now: datetime) -> dict:
    """The side that lost a jury's verdict pays a fee to have a fresh jury hear the case, within a day. The second verdict
    is final, and the fee comes back if it wins the appellant anything."""
    row = _one(conn, CASE_SQL + " WHERE k.id = %s FOR UPDATE OF k", (case_id,))
    if row is None or row["status"] != "verdict":
        raise CourtError("There is no jury's verdict on that case waiting for an appeal.")
    if row["appeal_until"] <= now:
        raise CourtError("The time to appeal has passed.")
    side = _side(row, player_id)
    if side == "defendant" and row["proved_bps"] == 0:
        raise CourtError("You were acquitted: there is nothing to appeal.")
    if side == "claimant" and row["proved_bps"] == BPS and row["penalty"] == "harsh":
        raise CourtError("The jury found everything you claimed, at the harshest penalty: there is nothing to appeal.")
    if side is None:
        raise CourtError("Only the two sides can appeal, and the regulator does not.")
    fee = max(apply_bps(row["amount"], data.JURY_APPEAL_FEE_BPS), naira(data.JURY_APPEAL_FEE_NAIRA))
    account = ledger.player_account_id(conn, player_id)
    if account is None or ledger.balance(conn, account) < fee:
        raise CourtError(f"An appeal costs {_naira(fee)}, which you do not have.")
    if len(_pool(conn, row)) < data.JURY_QUORUM:
        raise CourtError("Too few players may sit on a fresh jury, so the verdict stands.")
    period = careers.world_now(conn, now)["period"]
    ledger.transfer(conn, payer=account, receiver=ledger.account_id(conn, ledger.TREASURY), amount=fee, kind="court_appeal",
                    memo=f"The appeal fee on case {case_id}", period=period)
    conn.execute("UPDATE court_cases SET status = 'appeal', appealed_by = %s, appeal_fee = %s, first_proved_bps = proved_bps,"
                 " first_penalty = penalty, jury_until = %s WHERE id = %s", (side, fee, now + timedelta(hours=data.JURY_HOURS), case_id))
    _draw(conn, row, 2, data.JURY_SIZE, now)
    return case(conn, case_id)


def challenge(conn: Connection, player_id, case_id: int, seat: int, now: datetime) -> dict:
    """Each side may strike out one juror who has not voted, early in a sitting, and another is drawn in their place."""
    row = _one(conn, CASE_SQL + " WHERE k.id = %s FOR UPDATE OF k", (case_id,))
    if row is None or row["status"] not in ("jury", "appeal"):
        raise CourtError("There is no jury sitting on that case.")
    side = _side(row, player_id)
    if side is None:
        raise CourtError("Only the two sides can challenge a juror.")
    round_ = _round(row)
    if now > row["jury_until"] - timedelta(hours=data.JURY_HOURS) + timedelta(hours=data.JURY_CHALLENGE_HOURS):
        raise CourtError(f"A juror can only be challenged in the first {data.JURY_CHALLENGE_HOURS} hours of a sitting.")
    if _one(conn, "SELECT 1 AS x FROM jurors WHERE case_id = %s AND round = %s AND struck_by = %s", (case_id, round_, side)):
        raise CourtError("Each side may challenge one juror in a sitting, and you have.")
    juror = _one(conn, "SELECT * FROM jurors WHERE case_id = %s AND round = %s AND seat = %s FOR UPDATE", (case_id, round_, seat))
    if juror is None or juror["struck_by"] is not None:
        raise CourtError("There is no such juror on this jury.")
    if juror["voted_at"] is not None:
        raise CourtError("That juror has already voted.")
    conn.execute("UPDATE jurors SET struck_by = %s WHERE case_id = %s AND player_id = %s", (side, case_id, juror["player_id"]))
    conn.execute("UPDATE jury_offers SET status = 'lapsed' WHERE case_id = %s AND juror_id = %s AND status = 'offered'",
                 (case_id, juror["player_id"]))
    _draw(conn, row, round_, 1, now)
    return case(conn, case_id)


# --- Tampering ----------------------------------------------------------------

def offer(conn: Connection, player_id, case_id: int, seat: int, amount: int, wants: str, now: datetime) -> dict:
    """A side offers a juror money for a vote. A crime between players: the juror takes it or reports it. Nothing moves
    until the juror takes it."""
    if wants not in ("acquit", "convict"):
        raise CourtError("Say what you want the juror to vote for.")
    if amount < naira(data.COURT_MIN_CLAIM_NAIRA):
        raise CourtError(f"An offer worth less than {_naira(naira(data.COURT_MIN_CLAIM_NAIRA))} would not tempt anybody.")
    row = _one(conn, CASE_SQL + " WHERE k.id = %s", (case_id,))
    if row is None or row["status"] not in ("jury", "appeal"):
        raise CourtError("There is no jury sitting on that case.")
    if _side(row, player_id) is None:
        raise CourtError("Only the two sides know who sits on the jury.")
    round_ = _round(row)
    juror = _one(conn, "SELECT * FROM jurors WHERE case_id = %s AND round = %s AND seat = %s AND struck_by IS NULL", (case_id, round_, seat))
    if juror is None or juror["voted_at"] is not None:
        raise CourtError("That juror is not there to approach, or has already voted.")
    account = ledger.player_account_id(conn, player_id)
    if account is None or ledger.balance(conn, account) < amount:
        raise CourtError("You do not have that much to offer.")
    before = _one(conn, "SELECT count(*) AS n FROM jury_offers WHERE briber_id = %s AND status IN ('taken', 'reported')", (player_id,))["n"]
    chance = min(data.JURY_OFFER_TELL_BASE_BPS + data.JURY_OFFER_TELL_PER_REPEAT_BPS * before, 9000)
    try:
        conn.execute("INSERT INTO jury_offers (case_id, round, briber_id, juror_id, amount, wants, tell_bps, at)"
                     " VALUES (%s, %s, %s, %s, %s, %s, %s, %s)", (case_id, round_, player_id, juror["player_id"], amount, wants, chance, now))
    except Exception as clash:
        raise CourtError("You have already approached that juror.") from clash
    return {"offered": amount, "tell_bps": chance}


def answer_offer(conn: Connection, player_id, offer_id: int, take: bool, now: datetime) -> dict:
    """The juror takes the money (it moves at once) or reports the offer (it is exposed, and the juror is commended)."""
    o = _one(conn, "SELECT o.*, k.status AS case_status FROM jury_offers o JOIN court_cases k ON k.id = o.case_id"
                   " WHERE o.id = %s AND o.juror_id = %s FOR UPDATE OF o", (offer_id, player_id))
    if o is None or o["status"] != "offered":
        raise CourtError("There is no such offer waiting for you.")
    period = careers.world_now(conn, now)["period"]
    if not take:
        conn.execute("UPDATE jury_offers SET status = 'reported', exposed_how = 'reported', exposed_at = %s WHERE id = %s", (now, offer_id))
        conn.execute("UPDATE players SET reputation = least(reputation + %s, 100) WHERE id = %s", (data.JURY_REPORT_REPUTATION, player_id))
        _legal(conn, o["briber_id"], "tampering", f"Reported by a juror for offering {_naira(o['amount'])} for a vote on case {o['case_id']}.", now)
        return {"reported": True}
    payer = ledger.player_account_id(conn, o["briber_id"])
    receiver = ledger.player_account_id(conn, player_id)
    if payer is None or receiver is None or ledger.balance(conn, payer) < o["amount"]:
        conn.execute("UPDATE jury_offers SET status = 'lapsed' WHERE id = %s", (offer_id,))
        raise CourtError("The money is no longer there: the offer has lapsed.")
    ledger.transfer(conn, payer=payer, receiver=receiver, amount=o["amount"], kind="private_payment", memo="A private payment", period=period)
    conn.execute("UPDATE jury_offers SET status = 'taken' WHERE id = %s", (offer_id,))
    return {"taken": o["amount"]}


def _tell_offers(conn: Connection, row: dict, round_: int, now: datetime) -> None:
    """At the verdict, a juror who took money may tell: the chance fixed when it was offered."""
    if not _one(conn, "SELECT to_regclass('jury_offers') IS NOT NULL AS ok")["ok"]:
        return
    conn.execute("UPDATE jury_offers SET status = 'lapsed' WHERE case_id = %s AND round = %s AND status = 'offered'", (row["id"], round_))
    for o in _rows(conn, "SELECT * FROM jury_offers WHERE case_id = %s AND round = %s AND status = 'taken' AND exposed_how IS NULL",
                   (row["id"], round_)):
        if _roll(conn, "jury-told", o["id"]) < o["tell_bps"]:
            conn.execute("UPDATE jury_offers SET exposed_how = 'told', exposed_at = %s WHERE id = %s", (now, o["id"]))
            for who, what in ((o["briber_id"], "paid a juror"), (o["juror_id"], "took money as a juror")):
                _legal(conn, who, "tampering", f"It came out that they {what} on case {row['id']}.", now)


def tampering_wrongs(conn: Connection, since: datetime) -> list[dict]:
    """Offers that came out, as wrongs the tribunal can hear: the one who offered, and a juror who took it."""
    if not _one(conn, "SELECT to_regclass('jury_offers') IS NOT NULL AS ok")["ok"]:
        return []
    out = []
    for o in _rows(conn, "SELECT o.*, k.defendant_id, k.claimant_id FROM jury_offers o JOIN court_cases k ON k.id = o.case_id"
                         " WHERE o.exposed_how IS NOT NULL AND o.at >= %s ORDER BY o.id", (since,)):
        other = o["claimant_id"] if str(o["briber_id"]) == str(o["defendant_id"]) else o["defendant_id"]
        lines = [{"what": f"Offered a juror {_naira(o['amount'])} to vote to {o['wants']} on case {o['case_id']}"},
                 {"what": "Reported by the juror" if o["exposed_how"] == "reported" else "The juror took it, and it came out"}]
        out.append({"kind": "jury_tampering", "key": f"jury_tampering:{o['id']}:offer", "defendant_id": o["briber_id"], "company_id": None,
                    "ticker": None, "amount": o["amount"], "victim_player": other, "lines": lines,
                    "words": f"Offered a juror money for a vote on case {o['case_id']}."})
        if o["status"] == "taken":
            out.append({"kind": "jury_tampering", "key": f"jury_tampering:{o['id']}:took", "defendant_id": o["juror_id"], "company_id": None,
                        "ticker": None, "amount": o["amount"], "victim_player": other, "lines": lines,
                        "words": f"Took money as a juror for a vote on case {o['case_id']}."})
    return out


def juries_due(conn: Connection, now: datetime) -> int:
    """Juries whose time is up give their verdict."""
    if not _one(conn, "SELECT to_regclass('jurors') IS NOT NULL AS ok")["ok"]:
        return 0
    done = 0
    for row in _rows(conn, "SELECT id FROM court_cases WHERE status IN ('jury', 'appeal') AND jury_until <= %s ORDER BY id"
                           " FOR UPDATE SKIP LOCKED", (now,)):
        verdict(conn, row["id"], now)
        done += 1
    if _one(conn, "SELECT to_regclass('jury_offers') IS NOT NULL AS ok")["ok"]:
        period = careers.world_now(conn, now)["period"]
        for row in _rows(conn, "SELECT id, proved_bps, penalty FROM court_cases WHERE status = 'verdict' AND appeal_until <= %s ORDER BY id"
                               " FOR UPDATE SKIP LOCKED", (now,)):
            judge(conn, row["id"], period, now, proved_bps=row["proved_bps"], penalty=row["penalty"], by="jury")
            done += 1
    return done


def jury_duty(conn: Connection, player_id, now: datetime) -> dict:
    """A player's summonses (the case files to read and vote on), any offers made to them, and their record as a juror."""
    sitting = []
    for j in _rows(conn, "SELECT j.*, k.jury_until FROM jurors j JOIN court_cases k ON k.id = j.case_id"
                         " WHERE j.player_id = %s AND k.status IN ('jury', 'appeal') AND j.struck_by IS NULL"
                         " AND j.round = CASE WHEN k.appealed_by IS NULL THEN 1 ELSE 2 END ORDER BY k.jury_until", (player_id,)):
        c = case(conn, j["case_id"])
        offers = _rows(conn, "SELECT o.id, o.amount, o.wants, p.display_name AS who FROM jury_offers o JOIN players p ON p.id = o.briber_id"
                             " WHERE o.case_id = %s AND o.juror_id = %s AND o.status = 'offered' ORDER BY o.id", (j["case_id"], player_id)) \
            if _one(conn, "SELECT to_regclass('jury_offers') IS NOT NULL AS ok")["ok"] else []
        sitting.append({**c, "jury_until": j["jury_until"], "appeal_round": j["round"] == 2, "offers": offers,
                        "my_vote": {"proved_bps": j["proved_bps"], "penalty": j["penalty"]} if j["voted_at"] else None})
    record = _one(conn, "SELECT count(*) FILTER (WHERE struck_by IS NULL) AS summoned, count(voted_at) AS voted,"
                        " count(*) FILTER (WHERE agreed) AS agreed, coalesce(sum(fee), 0) AS fees FROM jurors WHERE player_id = %s", (player_id,))
    return {"sitting": sitting, "record": record,
            "rules": {"size": data.JURY_SIZE, "quorum": data.JURY_QUORUM, "hours": data.JURY_HOURS, "fee": naira(data.JURY_FEE_NAIRA),
                      "penalty_bps": data.JURY_PENALTY_BPS, "challenge_hours": data.JURY_CHALLENGE_HOURS,
                      "appeal_hours": data.JURY_APPEAL_HOURS, "appeal_fee_bps": data.JURY_APPEAL_FEE_BPS,
                      "appeal_fee_floor": naira(data.JURY_APPEAL_FEE_NAIRA)}}


def _jury_of(conn: Connection, row: dict) -> dict | None:
    """The jury on a case, for everybody: during a sitting, how many have voted; after, every vote, in the open, without
    names. An appealed case shows the first jury's votes and the second's."""
    if not _one(conn, "SELECT to_regclass('jurors') IS NOT NULL AS ok")["ok"]:
        return None
    seats = _rows(conn, "SELECT j.seat, j.round, j.proved_bps, j.penalty, j.reason, j.voted_at, j.struck_by FROM jurors j"
                        " WHERE j.case_id = %s ORDER BY j.seat", (row["id"],))
    if not seats:
        return None
    round_ = _round(row)
    now_seats = [s for s in seats if s["round"] == round_ and s["struck_by"] is None]

    def votes(r: int) -> list[dict]:
        return [{"seat": s["seat"], "proved_bps": s["proved_bps"], "penalty": s["penalty"], "reason": s["reason"]}
                for s in seats if s["round"] == r and s["struck_by"] is None and s["voted_at"]]
    out = {"seats": len(now_seats), "struck": sum(1 for s in seats if s["struck_by"]), "round": round_,
           "first_votes": votes(1) if round_ == 2 else None, "first": {"proved_bps": row.get("first_proved_bps"), "penalty": row.get("first_penalty")}
           if round_ == 2 else None, "appeal_until": row.get("appeal_until"), "appealed_by": row.get("appealed_by")}
    if row["status"] in ("jury", "appeal"):
        return {**out, "sitting": True, "voted": sum(1 for s in now_seats if s["voted_at"]), "until": row["jury_until"]}
    return {**out, "sitting": False, "votes": votes(round_)}


def panel_for(conn: Connection, row: dict, player_id) -> dict | None:
    """What the two sides see of a sitting jury: who sits (so they may challenge one), and what they may still do."""
    side = _side(row, player_id)
    if side is None or row["status"] not in ("jury", "appeal", "verdict"):
        return None
    round_ = _round(row)
    out: dict = {"side": side}
    if row["status"] in ("jury", "appeal"):
        start = row["jury_until"] - timedelta(hours=data.JURY_HOURS)
        out["jurors"] = [{"seat": j["seat"], "name": j["display_name"], "voted": j["voted_at"] is not None}
                         for j in _rows(conn, "SELECT j.seat, j.voted_at, p.display_name FROM jurors j JOIN players p ON p.id = j.player_id"
                                              " WHERE j.case_id = %s AND j.round = %s AND j.struck_by IS NULL ORDER BY j.seat", (row["id"], round_))]
        out["challenge_until"] = start + timedelta(hours=data.JURY_CHALLENGE_HOURS)
        out["challenged"] = bool(_one(conn, "SELECT 1 AS x FROM jurors WHERE case_id = %s AND round = %s AND struck_by = %s",
                                      (row["id"], round_, side)))
    if row["status"] == "verdict":
        lost = (side == "defendant" and row["proved_bps"] > 0) or \
               (side == "claimant" and not (row["proved_bps"] == BPS and row["penalty"] == "harsh"))
        out["can_appeal"] = lost
        out["appeal_fee"] = max(apply_bps(row["amount"], data.JURY_APPEAL_FEE_BPS), naira(data.JURY_APPEAL_FEE_NAIRA))
    return out


def _legal(conn: Connection, player_id, kind: str, words: str, now: datetime) -> None:
    conn.execute("INSERT INTO legal_records (player_id, kind, words, at) VALUES (%s, %s, %s, %s)",
                 (player_id, kind, words[:400], now))


# ---------------------------------------------------------------------------
# Paying what was ordered
# ---------------------------------------------------------------------------

def pay(conn: Connection, case_id: int, period: int, now: datetime) -> int:
    """Pay as much of a judgment as the defendant has, split between the fund, the regulator, the Treasury and the
    claimant. Restitution is paid down over quarters, so a case can be judged and still be owed."""
    row = _one(conn, CASE_SQL + " WHERE k.id = %s", (case_id,))
    if row is None:
        return 0
    owed = _owed(row)
    if owed <= 0:
        return 0
    account = ledger.player_account_id(conn, row["defendant_id"])
    if account is None:
        return 0
    fund = ledger.account_id(conn, COMPENSATION_FUND)
    amounts: dict = {}
    if row["disgorgement"] or row["damages"]:
        receiver = _claimant_account(conn, row)
        amounts[receiver] = amounts.get(receiver, 0) + row["disgorgement"] + row["damages"]
    if row["fine"]:
        to_regulator = apply_bps(row["fine"], data.COURT_FINE_TO_REGULATOR_BPS)
        amounts[ledger.account_id(conn, REGULATOR)] = amounts.get(ledger.account_id(conn, REGULATOR), 0) + to_regulator
        amounts[ledger.account_id(conn, ledger.TREASURY)] = (
            amounts.get(ledger.account_id(conn, ledger.TREASURY), 0) + row["fine"] - to_regulator)
    if row["costs"]:
        receiver = _claimant_account(conn, row)
        amounts[receiver] = amounts.get(receiver, 0) + row["costs"]
    total = sum(amounts.values())
    if total <= 0:
        return 0
    # Only what is still owed and what the defendant can actually pay, in the same proportions as what was ordered.
    payable = min(owed, ledger.balance(conn, account))
    if payable <= 0:
        return 0
    amounts = {receiver: amount * payable // total for receiver, amount in amounts.items()}
    amounts = {receiver: amount for receiver, amount in amounts.items() if amount > 0}
    if not amounts:
        return 0
    # Rounding leaves a few kobo: they go to the largest receiver, so the whole payment is made and none is left behind.
    short = payable - sum(amounts.values())
    if short > 0:
        biggest = max(amounts, key=amounts.get)
        amounts[biggest] += short
    paid = ledger.pay_split_up_to(conn, payer=account, amounts=amounts, kind="court_payment",
                                  memo=f"Payment on case {case_id}", period=period)
    if paid:
        conn.execute("INSERT INTO court_payments (case_id, amount, at) VALUES (%s, %s, %s)", (case_id, paid, now))
        conn.execute("UPDATE court_cases SET paid = paid + %s WHERE id = %s", (paid, case_id))
    return paid


# ---------------------------------------------------------------------------
# Each quarter: what the regulator brings, what lapses, what is paid
# ---------------------------------------------------------------------------

def enforce(conn: Connection, period: int, now: datetime) -> int:
    """The regulator looks at the record and brings the cases it decides are worth proving. Enforcement is
    probabilistic: a recorded wrong raises the chance of a case, and only some become one."""
    opened = 0
    for wrong in _wrongs(conn, period, now):
        if _roll(conn, "court", wrong["key"]) >= data.COURT_ENFORCE_BPS[wrong["kind"]]:
            continue
        if _regulator_brings(conn, wrong, period, now) is not None:
            opened += 1
    return opened


def _lapsed(conn: Connection, period: int, now: datetime) -> int:
    """A defendant who did not answer a case is judged at the next close."""
    judged = 0
    for row in _rows(conn, CASE_SQL + " WHERE k.status = 'open' AND k.opened_period < %s ORDER BY k.id", (period,)):
        judge(conn, row["id"], period, now)
        judged += 1
    return judged


def _collect(conn: Connection, period: int, now: datetime) -> int:
    total = 0
    for row in _rows(conn, CASE_SQL + " WHERE k.status = 'judged'"
                                      " AND k.disgorgement + k.damages + k.fine + k.costs > k.paid ORDER BY k.id"):
        total += pay(conn, row["id"], period, now)
    return total


def at_close(conn: Connection, period: int, now: datetime) -> dict:
    """The court's quarter: the regulator brings what it will, cases left unanswered are judged, and what is owed is
    paid down."""
    if not ready(conn):
        return {}
    ensure(conn)
    opened = enforce(conn, period, now)
    judged = juries_due(conn, now) + _lapsed(conn, period, now)
    paid = _collect(conn, period, now)
    return {"opened": opened, "judged": judged, "paid": paid}
