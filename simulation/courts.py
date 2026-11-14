"""Stage 11: the courts, as a docket.

The court's subject is money, its evidence is the ledger, and its remedy is money moving. It does not decide guilt: it
proves a number and makes it be paid. A case is a claim with an amount, the lines of the record that prove the amount,
and a remedy that moves money.

Four kinds of case in this part, all against the market:

  insider            dealing on confidential information (confidential_dealings, recorded since Stage 10B)
  manipulation       ramping and wash trading (market_trades.same_owner, recorded since Stage 4)
  undisclosed_stake  a holding past 5% that was never made public (stake_disclosures against the ledger)
  naked_short        borrowed shares that had to be bought in (short_positions, recorded since Stage 9)

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
KINDS = ("insider", "manipulation", "undisclosed_stake", "naked_short", "insurance_fraud")

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
        ledger.create_account(conn, kind="escrow", name="The court's compensation fund", code=COMPENSATION_FUND)


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
    }


def case(conn: Connection, case_id: int) -> dict | None:
    row = _one(conn, CASE_SQL + " WHERE k.id = %s", (case_id,))
    return _case(row) if row else None


def docket(conn: Connection) -> list[dict]:
    """Every case the court has open. Public: a docket is read by anybody."""
    return [_case(row) for row in _rows(conn, CASE_SQL + " WHERE k.status = 'open' ORDER BY k.id DESC")]


def my_cases(conn: Connection, player_id) -> dict:
    """The cases a player is defending, the ones they brought, and their legal record."""
    return {
        "defending": [_case(row) for row in _rows(conn, CASE_SQL + " WHERE k.defendant_id = %s ORDER BY k.id DESC",
                                                  (player_id,))],
        "brought": [_case(row) for row in _rows(conn, CASE_SQL + " WHERE k.claimant_id = %s ORDER BY k.id DESC",
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
                f"Trading is banned until {clock.period_label(row['until'])}: the court's order.")


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


def _insurance_fraud_wrongs(conn: Connection, period: int, now: datetime) -> list[dict]:
    """Insurance fraud: a second attempt on a policy permanently ends cover for good.

    Reads the insurance_claims and insurance_refusals tables to find cases where
    a player has already had a claim refused (or a second open claim) on the same
    policy kind. A second attempt ends the policy permanently.
    """
    wrongs: list[dict] = []
    since = _quarter_start(conn, period - data.COURT_WINDOW_QUARTERS + 1)

    # Check for second open claims on the same policy kind
    second_claims = _rows(conn, """
        SELECT policy_player_id, policy_kind, count(*) AS n
        FROM insurance_claims
        WHERE state = 'open'
        AND at >= %s
        GROUP BY policy_player_id, policy_kind
        HAVING count(*) > 1
    """, (since,))

    for s in second_claims:
        # A second open claim on the same policy kind means fraud / policy ends
        wrongs.append({
            "kind": "insurance_fraud",
            "defendant_id": s["policy_player_id"],
            "company_id": None,
            "key": f"insurance_fraud:{s['policy_player_id']}:{s['policy_kind']}",
            "amount": naira(data.COURT_MIN_CLAIM_NAIRA),
            "lines": [],
            "words": f"Second claim on {s['policy_kind']} policy for player {s['policy_player_id']}: a second attempt permanently ends cover for good.",
        })

    # Check for prior refusals: if a claim was refused, a second attempt also ends cover
    prior_refusals = _rows(conn, """
        SELECT player_id AS policy_player_id, kind AS policy_kind, count(*) AS n
        FROM insurance_refusals
        GROUP BY player_id, kind
    """)

    for r in prior_refusals:
        wrongs.append({
            "kind": "insurance_fraud",
            "defendant_id": r["policy_player_id"],
            "company_id": None,
            "key": f"insurance_fraud_refusal:{r['policy_player_id']}:{r['policy_kind']}",
            "amount": naira(data.COURT_MIN_CLAIM_NAIRA),
            "lines": [],
            "words": f"Prior refusal on {r['policy_kind']} policy for player {r['policy_player_id']}: a second attempt ends cover for good.",
        })

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

    for wrong in _stake_wrongs(conn, period, now) + _short_wrongs(conn, since) + _insurance_fraud_wrongs(conn, period, now):
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
        raise CourtError("The court hears five kinds of case against the market: dealing on confidential information, "
                         "manipulation, an undisclosed stake, a naked short, and insurance fraud.")
    if amount < naira(data.COURT_MIN_CLAIM_NAIRA):
        raise CourtError(f"A claim of {_naira(amount)} is not worth the court's time.")
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
    if wrong["kind"] in ("manipulation", "naked_short"):
        return "Only the regulator can bring that kind of case."
    account = ledger.player_account_id(conn, player_id)
    if account is None:
        return "You have no account to bring a case from."
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
        raise CourtError("The court hears five kinds of case against the market: dealing on confidential information, "
                         "manipulation, an undisclosed stake, a naked short, and insurance fraud.")
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


def respond(conn: Connection, player_id, case_id: int, choice: str, period: int, now: datetime) -> dict:
    """The defendant answers a case: settle it at once, or let it be judged."""
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
    raise CourtError("A case is answered by settling it or by fighting it.")


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


def judge(conn: Connection, case_id: int, period: int, now: datetime) -> dict:
    """The verdict, which reads like arithmetic: the profit is disgorged, a fine is added, the loser pays the winner's
    costs, and a manipulation or a naked short carries a trading ban."""
    row = _one(conn, CASE_SQL + " WHERE k.id = %s", (case_id,))
    if row is None:
        raise CourtError("There is no such case.")
    if row["status"] != "open":
        raise CourtError("That case has already been decided.")
    amount = row["amount"]
    disgorgement = amount if row["kind"] in ("insider", "undisclosed_stake") else 0
    fine = apply_bps(amount, data.COURT_FINE_BPS[row["kind"]])
    costs = apply_bps(amount, data.COURT_COSTS_BPS)
    ban = data.COURT_BAN_QUARTERS.get(row["kind"], 0)
    conn.execute("UPDATE court_cases SET status = 'judged', outcome = 'judged', decided_at = %s, disgorgement = %s,"
                 " fine = %s, costs = %s, ban_quarters = %s WHERE id = %s",
                 (now, disgorgement, fine, costs, ban, case_id))
    _legal(conn, row["defendant_id"], "judged",
           f"Judged to pay {_naira(disgorgement + fine + costs)}: {row['words']}", now)
    conn.execute("UPDATE players SET reputation = greatest(reputation - %s, 0) WHERE id = %s",
                 (data.COURT_REPUTATION, row["defendant_id"]))
    if ban:
        conn.execute("INSERT INTO court_bans (player_id, case_id, until_period, at) VALUES (%s, %s, %s, %s)",
                     (row["defendant_id"], case_id, period + ban, now))
    _return_bond(conn, row, period, now)
    pay(conn, case_id, period, now)
    return case(conn, case_id)


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
    judged = _lapsed(conn, period, now)
    paid = _collect(conn, period, now)
    return {"opened": opened, "judged": judged, "paid": paid}
