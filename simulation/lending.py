"""Stage 9, Part A: borrowing and short selling.

  personal loan   from the player's own bank, at most a year's salary (and, with any mortgages, no more than
                  four years' salary in all), at the Central Bank's rate plus 8%, repaid evenly over two years.
                  Two quarters missed and the loan is in default: no more borrowing until it is cleared.
  margin loan     a loan against shares and bonds: up to half their value, at the Central Bank's rate plus 2%.
                  The shares stay the borrower's (dividends and votes too). At every Closing Bell the loan is
                  measured against the borrower's shares, bonds and cash: at 70% a margin call; at 80%, or when
                  a call is not met by the next bell, shares are sold to the market's computer investors at 5%
                  below the close until the loan is back to half.
  short selling   shares borrowed from the pension funds (the institutional investors), who lend at most 30% of
                  their holding of a share, for 2% a year. The borrower puts up 150% of the shares' value in cash,
                  held by the exchange. At every Closing Bell: below 125% a margin call; below 110%, or a call
                  not met by the next bell, the shares are bought back by force at 5% above the close. While
                  lent, any dividend is paid to the lender by the borrower. The lender can recall its shares.

Every naira moves through the ledger. All of a player's borrowing together is limited to twice what they
are worth after their debts. An empire borrows and shorts only inside limits its Risk Manager signs; above
them, the head decides.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime

from psycopg import Connection
from psycopg.rows import dict_row

from simulation import clock, ledger
from simulation import world_data as data
from simulation.money import BPS

COLLATERAL = "short:collateral"          # cash held for short sellers
LENDER = ledger.INVESTORS_INSTITUTIONS  # the pension funds lend shares
BUYERS = (ledger.INVESTORS_PUBLIC, ledger.INVESTORS_FOUNDERS, "investors:foreign")   # who buy forced sales and sell buy-ins


class LendingError(Exception):
    """A request about a loan or a short that cannot be done; the message says why, in plain words."""


def _rows(conn: Connection, sql: str, params=()) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def _one(conn: Connection, sql: str, params=()) -> dict | None:
    rows = _rows(conn, sql, params)
    return rows[0] if rows else None


def money(kobo: int) -> str:
    return f"₦{kobo / 100:,.0f}"


def _state(conn: Connection, now: datetime) -> dict:
    from simulation import careers
    return careers.world_now(conn, now)


def ensure(conn: Connection) -> None:
    if _one(conn, "SELECT 1 FROM ledger_accounts WHERE code = %s", (COLLATERAL,)) is None:
        ledger.create_account(conn, kind="escrow", name="The exchange: cash held for short sellers", code=COLLATERAL)


def _collateral_account(conn: Connection):
    ensure(conn)
    return ledger.account_id(conn, COLLATERAL)


def policy_rate(conn: Connection) -> int:
    row = _one(conn, "SELECT next_policy_rate_bps FROM economy_results ORDER BY period DESC LIMIT 1")
    return row["next_policy_rate_bps"] if row else data.NEUTRAL_RATE_BPS


def _event(conn: Connection, account, kind: str, words: str, now: datetime, *, loan_id=None, short_id=None) -> None:
    conn.execute("INSERT INTO lending_events (account, loan_id, short_id, kind, words, at) VALUES (%s, %s, %s, %s, %s, %s)",
                 (account, loan_id, short_id, kind, words, now))


def _kind_of(conn: Connection, account) -> str:
    row = _one(conn, "SELECT kind FROM ledger_accounts WHERE id = %s", (account,))
    if row is None:
        raise LendingError("There is no such account.")
    return row["kind"]


# ---------------------------------------------------------------------------
# Prices and what an account holds
# ---------------------------------------------------------------------------

def prices(conn: Connection) -> dict:
    """Each listed company's price now (the last trade, or its reference price)."""
    return {r["company_id"]: r for r in _rows(conn, """
        SELECT m.company_id, c.ticker, c.name, c.share_asset, coalesce(m.last_price, m.reference_price) AS price
        FROM market_instruments m JOIN companies c ON c.id = m.company_id WHERE c.status = 'trading'""")}


def _share_value(conn: Connection, account, quotes: dict) -> tuple[int, list[dict]]:
    lines = []
    for r in _rows(conn, "SELECT company_id, shares FROM share_owners WHERE account_id = %s AND shares > 0", (account,)):
        q = quotes.get(r["company_id"])
        if q is None:
            continue
        free = ledger.balance(conn, account, q["share_asset"])          # (shares waiting in sell orders are held by the exchange)
        lines.append({**q, "shares": r["shares"], "free": free, "value": r["shares"] * q["price"]})
    return sum(line["value"] for line in lines), lines


def holdings_value(conn: Connection, account, now: datetime) -> dict:
    """What counts as security for a margin loan: shares and bonds at today's prices; and cash."""
    from simulation import bonds
    quotes = prices(conn)
    shares, lines = _share_value(conn, account, quotes)
    bond_value = sum(b["value"] for b in bonds.holdings_of(conn, account, now))
    cash = ledger.balance(conn, account)
    return {"shares": shares, "bonds": bond_value, "cash": cash, "lines": lines, "security": shares + bond_value,
            "total": shares + bond_value + cash}


def short_liability(conn: Connection, account) -> int:
    """What it would cost today to buy back every share the account has borrowed."""
    quotes = prices(conn)
    return sum(s["shares"] * quotes[s["company_id"]]["price"]
               for s in _rows(conn, "SELECT company_id, shares FROM short_positions WHERE borrower = %s AND status = 'open'", (account,))
               if s["company_id"] in quotes)


def collateral_held(conn: Connection, account) -> int:
    return _one(conn, "SELECT coalesce(sum(collateral), 0)::bigint AS c FROM short_positions WHERE borrower = %s AND status = 'open'",
                (account,))["c"]


def loans_owed(conn: Connection, account) -> int:
    return _one(conn, "SELECT coalesce(sum(outstanding), 0)::bigint AS o FROM player_loans WHERE borrower = %s AND status <> 'repaid'",
                (account,))["o"]


def debts(conn: Connection, account) -> int:
    """Everything the account owes: loans, mortgages, and the shares it has borrowed at today's price."""
    mortgages = _one(conn, "SELECT coalesce(sum(outstanding), 0)::bigint AS o FROM mortgages WHERE borrower = %s"
                           " AND status IN ('open', 'shortfall')", (account,))["o"] if _one(
        conn, "SELECT to_regclass('mortgages') IS NOT NULL AS ok")["ok"] else 0
    return loans_owed(conn, account) + mortgages + short_liability(conn, account)


def _equity(conn: Connection, account, now: datetime) -> int:
    from simulation import objectives
    return objectives.wealth(conn, account, now)["total"]


def geared(conn: Connection, account) -> int:
    """Borrowing to invest: loans against shares and bonds, and borrowed shares at today's price."""
    return margin_owed(conn, account) + short_liability(conn, account)


def _leverage_allows(conn: Connection, account, extra: int, now: datetime) -> None:
    """Borrowing to invest (against shares, or by selling short) together is at most twice what the borrower is worth
    after all their debts. (A personal loan or a mortgage is limited by salary instead.)"""
    owed = geared(conn, account) + extra
    equity = _equity(conn, account, now)
    if owed > data.MOST_DEBT_TIMES_EQUITY * max(equity, 0):
        raise LendingError(f"Borrowing to invest may be at most {data.MOST_DEBT_TIMES_EQUITY} times what you are worth after "
                           f"your debts ({money(max(equity, 0))}). This would take it to {money(owed)}.")


def _not_in_default(conn: Connection, account) -> None:
    if _one(conn, "SELECT 1 FROM player_loans WHERE borrower = %s AND status = 'default'", (account,)):
        raise LendingError("A loan of yours is in default. No bank will lend to you until it is repaid.")


def _bank(conn: Connection, company_id) -> dict:
    row = _one(conn, "SELECT id, account_id, name FROM companies WHERE id = %s AND sector = 'banking' AND status = 'trading'", (company_id,))
    if row is None:
        raise LendingError("Choose one of the banks.")
    return row


def _bank_room(conn: Connection, company_id, period: int) -> int:
    from simulation import banking
    for b in banking.banks(conn, period):
        if str(b["id"]) == str(company_id):
            return banking.lending_room(b)
    return 0


# ---------------------------------------------------------------------------
# Personal loans
# ---------------------------------------------------------------------------

def _salary(conn: Connection, player_id, now: datetime) -> int:
    from simulation import careers
    if careers.current_job(conn, player_id) is None:
        return 0
    mine = careers.career(conn, player_id)
    if mine is None:
        return 0
    return careers.salary_per_quarter(mine["level"], careers.world_now(conn, now)["wage_index_bps"])


def personal_limit(conn: Connection, player_id, now: datetime) -> int:
    """The most more a player may borrow on a personal loan now."""
    account = ledger.player_account_id(conn, player_id)
    salary = _salary(conn, player_id, now)
    if salary <= 0 or _one(conn, "SELECT 1 FROM player_loans WHERE borrower = %s AND status = 'default'", (account,)):
        return 0
    personal = _one(conn, "SELECT coalesce(sum(outstanding), 0)::bigint AS o FROM player_loans WHERE borrower = %s AND kind = 'personal'"
                          " AND status <> 'repaid'", (account,))["o"]
    mortgages = _one(conn, "SELECT coalesce(sum(outstanding), 0)::bigint AS o FROM mortgages WHERE borrower = %s"
                           " AND status IN ('open', 'shortfall')", (account,))["o"]
    by_itself = salary * data.PERSONAL_LOAN_SALARY_QUARTERS - personal
    with_mortgages = salary * data.MORTGAGE_SALARY_QUARTERS - personal - mortgages
    return max(min(by_itself, with_mortgages), 0)


def take_personal(conn: Connection, player_id, amount: int, now: datetime) -> dict:
    from simulation import careers
    with conn.transaction():
        conn.execute("SELECT 1 FROM players WHERE id = %s FOR UPDATE", (player_id,))
        state = _state(conn, now)
        account = ledger.player_account_id(conn, player_id)
        if not isinstance(amount, int) or isinstance(amount, bool) or amount <= 0:
            raise LendingError("Name an amount to borrow.")
        _not_in_default(conn, account)
        if careers.current_job(conn, player_id) is None:
            raise LendingError("A bank lends against a salary. Find a job first.")
        bank_row = careers.current_bank(conn, player_id)
        if bank_row is None:
            raise LendingError("Choose a bank first.")
        most = personal_limit(conn, player_id, now)
        if amount > most:
            raise LendingError(f"Your bank will lend you at most {money(most)} more against your salary.")
        if amount > _bank_room(conn, bank_row["company_id"], state["period"]):
            raise LendingError(f"{bank_row['name']} has no room to lend that much now.")
        rate = policy_rate(conn) + data.PERSONAL_LOAN_SPREAD_BPS
        try:
            ledger.transfer(conn, payer=bank_row["account_id"], receiver=account, amount=amount, kind="personal_loan",
                            memo=f"A personal loan from {bank_row['name']}", period=state["period"])
        except ledger.InsufficientFunds:
            raise LendingError(f"{bank_row['name']} has not the cash to lend that now.") from None
        loan = _one(conn, "INSERT INTO player_loans (kind, borrower, bank_company_id, principal, outstanding, rate_bps, taken_period,"
                          " term_quarters, at) VALUES ('personal', %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
                    (account, bank_row["company_id"], amount, amount, rate, state["period"], data.PERSONAL_LOAN_TERM_QUARTERS, now))
        return {"loan_id": loan["id"], "amount": amount, "rate_bps": rate}


# ---------------------------------------------------------------------------
# Loans against shares and bonds
# ---------------------------------------------------------------------------

def margin_owed(conn: Connection, account) -> int:
    return _one(conn, "SELECT coalesce(sum(outstanding), 0)::bigint AS o FROM player_loans WHERE borrower = %s AND kind = 'margin'"
                      " AND status <> 'repaid'", (account,))["o"]


def margin_limit(conn: Connection, account, now: datetime) -> int:
    held = holdings_value(conn, account, now)
    return max(held["security"] * data.MARGIN_LOAN_MOST_BPS // BPS - margin_owed(conn, account), 0)


def take_margin(conn: Connection, account, bank_company_id, amount: int, now: datetime) -> dict:
    """Borrow against shares and bonds. The account's own lock keeps two loans from being taken at once."""
    with conn.transaction():
        state = _state(conn, now)
        conn.execute("SELECT pg_advisory_xact_lock(hashtext('borrower:' || %s::text))", (str(account),))
        if not isinstance(amount, int) or isinstance(amount, bool) or amount <= 0:
            raise LendingError("Name an amount to borrow.")
        _not_in_default(conn, account)
        bank = _bank(conn, bank_company_id)
        most = margin_limit(conn, account, now)
        if amount > most:
            raise LendingError(f"A bank lends at most half the value of your shares and bonds: {money(most)} more now.")
        if amount > _bank_room(conn, bank["id"], state["period"]):
            raise LendingError(f"{bank['name']} has no room to lend that much now.")
        _leverage_allows(conn, account, amount, now)
        rate = policy_rate(conn) + data.MARGIN_LOAN_SPREAD_BPS
        try:
            ledger.transfer(conn, payer=bank["account_id"], receiver=account, amount=amount, kind="margin_loan",
                            memo=f"A loan against shares and bonds from {bank['name']}", period=state["period"])
        except ledger.InsufficientFunds:
            raise LendingError(f"{bank['name']} has not the cash to lend that now.") from None
        loan = _one(conn, "SELECT * FROM player_loans WHERE borrower = %s AND bank_company_id = %s AND kind = 'margin' AND status = 'open'"
                          " FOR UPDATE", (account, bank["id"]))
        if loan:
            conn.execute("UPDATE player_loans SET principal = principal + %s, outstanding = outstanding + %s, rate_bps = %s WHERE id = %s",
                         (amount, amount, rate, loan["id"]))
            loan_id = loan["id"]
        else:
            loan_id = _one(conn, "INSERT INTO player_loans (kind, borrower, bank_company_id, principal, outstanding, rate_bps, taken_period, at)"
                                 " VALUES ('margin', %s, %s, %s, %s, %s, %s, %s) RETURNING id",
                           (account, bank["id"], amount, amount, rate, state["period"], now))["id"]
        return {"loan_id": loan_id, "amount": amount, "rate_bps": rate}


def repay(conn: Connection, account, loan_id: int, amount: int, now: datetime) -> dict:
    with conn.transaction():
        state = _state(conn, now)
        loan = _one(conn, "SELECT l.*, c.account_id AS bank_account, c.name AS bank FROM player_loans l JOIN companies c ON c.id = l.bank_company_id"
                          " WHERE l.id = %s AND l.borrower = %s AND l.status <> 'repaid' FOR UPDATE OF l", (loan_id, account))
        if loan is None:
            raise LendingError("There is no such loan of yours.")
        if not isinstance(amount, int) or isinstance(amount, bool) or amount <= 0:
            raise LendingError("Name an amount to repay.")
        amount = min(amount, loan["outstanding"])
        try:
            ledger.transfer(conn, payer=account, receiver=loan["bank_account"], amount=amount, kind="loan_repayment",
                            memo=f"Repaid to {loan['bank']}", period=state["period"])
        except ledger.InsufficientFunds:
            raise LendingError("There is not the cash.") from None
        left = loan["outstanding"] - amount
        # (A loan in default stays in default until it is repaid in full.)
        conn.execute("UPDATE player_loans SET outstanding = %s, status = %s WHERE id = %s",
                     (left, "repaid" if left == 0 else loan["status"], loan["id"]))
        return {"left": left}


# ---------------------------------------------------------------------------
# Short selling
# ---------------------------------------------------------------------------

def lendable(conn: Connection, company_id) -> int:
    """How many more shares of a company the pension funds will lend now."""
    lender = ledger.account_id(conn, LENDER)
    company = _one(conn, "SELECT share_asset FROM companies WHERE id = %s", (company_id,))
    if company is None:
        return 0
    held = ledger.balance(conn, lender, company["share_asset"])
    lent = _one(conn, "SELECT coalesce(sum(shares), 0)::bigint AS s FROM short_positions WHERE company_id = %s AND lender = %s"
                      " AND status = 'open'", (company_id, lender))["s"]
    return max((held + lent) * data.LENDING_POOL_BPS // BPS - lent, 0)


def open_short(conn: Connection, account, ticker: str, shares: int, now: datetime) -> dict:
    """Borrow shares to sell. The cash collateral (150% of their value) is held at once."""
    with conn.transaction():
        state = _state(conn, now)
        conn.execute("SELECT pg_advisory_xact_lock(hashtext('borrower:' || %s::text))", (str(account),))
        if not isinstance(shares, int) or isinstance(shares, bool) or shares <= 0:
            raise LendingError("Name how many shares to borrow.")
        q = _one(conn, "SELECT c.id, c.ticker, c.name, c.share_asset, coalesce(m.last_price, m.reference_price) AS price"
                       " FROM companies c JOIN market_instruments m ON m.company_id = c.id WHERE c.ticker = %s AND c.status = 'trading'",
                 (ticker,))
        if q is None:
            raise LendingError("Only shares listed on the exchange can be borrowed.")
        conn.execute("SELECT 1 FROM market_instruments WHERE company_id = %s FOR UPDATE", (q["id"],))
        if shares > lendable(conn, q["id"]):
            raise LendingError(f"The pension funds will lend only {lendable(conn, q['id']):,} more {q['ticker']} shares now.")
        _not_in_default(conn, account)
        value = shares * q["price"]
        collateral = value * data.SHORT_COLLATERAL_BPS // BPS
        _leverage_allows(conn, account, value, now)
        held = _collateral_account(conn)
        try:
            ledger.transfer(conn, payer=account, receiver=held, amount=collateral, kind="short_collateral",
                            memo=f"Collateral for {shares:,} borrowed {q['ticker']} shares", period=state["period"])
        except ledger.InsufficientFunds:
            raise LendingError(f"Borrowing these shares needs {money(collateral)} of cash as collateral (150% of their value).") from None
        lender = ledger.account_id(conn, LENDER)
        ledger.transfer(conn, payer=lender, receiver=account, amount=shares, asset=q["share_asset"], kind="share_loan",
                        memo=f"{shares:,} {q['ticker']} shares lent by the pension funds", period=state["period"])
        row = _one(conn, "INSERT INTO short_positions (borrower, lender, company_id, shares, collateral, opened_price, opened_period, at)"
                         " VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
                   (account, lender, q["id"], shares, collateral, q["price"], state["period"], now))
        return {"short_id": row["id"], "shares": shares, "collateral": collateral, "price": q["price"]}


def close_short(conn: Connection, account, short_id: int, now: datetime) -> dict:
    """Give the borrowed shares back (the borrower must hold them again) and take back the collateral."""
    with conn.transaction():
        state = _state(conn, now)
        s = _one(conn, "SELECT s.*, c.share_asset, c.ticker FROM short_positions s JOIN companies c ON c.id = s.company_id"
                       " WHERE s.id = %s AND s.borrower = %s AND s.status = 'open' FOR UPDATE OF s", (short_id, account))
        if s is None:
            raise LendingError("There is no such open short of yours.")
        if ledger.balance(conn, account, s["share_asset"]) < s["shares"]:
            raise LendingError(f"To close it, hold {s['shares']:,} {s['ticker']} shares (not waiting in a sell order): buy them back first.")
        ledger.transfer(conn, payer=account, receiver=s["lender"], amount=s["shares"], asset=s["share_asset"], kind="share_return",
                        memo=f"{s['shares']:,} borrowed {s['ticker']} shares given back", period=state["period"])
        if s["collateral"] > 0:
            ledger.transfer(conn, payer=_collateral_account(conn), receiver=account, amount=s["collateral"], kind="short_release",
                            memo=f"Collateral handed back: {s['ticker']} short closed", period=state["period"])
        price = prices(conn).get(s["company_id"], {}).get("price")
        conn.execute("UPDATE short_positions SET status = 'returned', collateral = 0, closed_price = %s, closed_at = %s WHERE id = %s",
                     (price, now, s["id"]))
        return {"returned": s["shares"], "collateral": s["collateral"]}


def add_collateral(conn: Connection, account, short_id: int, amount: int, now: datetime) -> dict:
    with conn.transaction():
        state = _state(conn, now)
        s = _one(conn, "SELECT * FROM short_positions WHERE id = %s AND borrower = %s AND status = 'open' FOR UPDATE", (short_id, account))
        if s is None:
            raise LendingError("There is no such open short of yours.")
        if not isinstance(amount, int) or isinstance(amount, bool) or amount <= 0:
            raise LendingError("Name an amount.")
        try:
            ledger.transfer(conn, payer=account, receiver=_collateral_account(conn), amount=amount, kind="short_collateral",
                            memo="More collateral for a short", period=state["period"])
        except ledger.InsufficientFunds:
            raise LendingError("There is not the cash.") from None
        conn.execute("UPDATE short_positions SET collateral = collateral + %s, call_since = NULL WHERE id = %s", (amount, s["id"]))
        return {"collateral": s["collateral"] + amount}


def short_interest(conn: Connection) -> dict:
    """Shares lent out to short sellers, as a share of all a company's shares (never who)."""
    out = {}
    for r in _rows(conn, "SELECT s.company_id, sum(s.shares)::bigint AS lent, c.share_asset FROM short_positions s"
                         " JOIN companies c ON c.id = s.company_id WHERE s.status = 'open' GROUP BY s.company_id, c.share_asset"):
        issued = ledger.amount_in_existence(conn, r["share_asset"])
        out[r["company_id"]] = max(r["lent"] * BPS // issued, 1) if issued else 0          # (any short at all shows as at least 0.01%)
    return out


def after_dividend(conn: Connection, company_id, paid_total: int, shares_counted: int, period: int, label: str) -> None:
    """A dividend paid while shares are lent: the borrower pays the lender what it would have had."""
    if shares_counted <= 0 or paid_total <= 0:
        return
    held = None
    for s in _rows(conn, "SELECT * FROM short_positions WHERE company_id = %s AND status = 'open' ORDER BY id FOR UPDATE", (company_id,)):
        owed = paid_total * s["shares"] // shares_counted
        if owed <= 0:
            continue
        got = ledger.pay_up_to(conn, payer=s["borrower"], receiver=s["lender"], wanted=owed, kind="lent_dividend",
                               memo=f"The dividend on lent shares, {label}", period=period)
        if got < owed and s["collateral"] > 0:
            held = held or _collateral_account(conn)
            more = min(owed - got, s["collateral"])
            ledger.transfer(conn, payer=held, receiver=s["lender"], amount=more, kind="lent_dividend",
                            memo=f"The dividend on lent shares, from the collateral, {label}", period=period)
            conn.execute("UPDATE short_positions SET collateral = collateral - %s WHERE id = %s", (more, s["id"]))


# ---------------------------------------------------------------------------
# Forced sales and buy-ins, to and from the market's computer investors
# ---------------------------------------------------------------------------

def _buyers(conn: Connection) -> list:
    out = []
    for code in BUYERS:
        row = _one(conn, "SELECT id FROM ledger_accounts WHERE code = %s", (code,))
        if row:
            out.append(row["id"])
    return out


def _sell_by_force(conn: Connection, account, line: dict, quantity: int, price: int, period: int, why: str) -> int:
    """Sell shares to the computer investors at the given price. Returns the cash raised."""
    raised = 0
    left = quantity
    for buyer in _buyers(conn):
        if left <= 0:
            break
        cash = ledger.balance(conn, buyer)
        can = min(left, cash // max(price, 1))
        if can <= 0:
            continue
        ledger.post(conn, kind="forced_sale", memo=f"{why}: {can:,} {line['ticker']} shares sold at {money(price)}", period=period,
                    legs=[ledger.Leg(account, -can, line["share_asset"]), ledger.Leg(buyer, can, line["share_asset"]),
                          ledger.Leg(buyer, -can * price), ledger.Leg(account, can * price)])
        raised += can * price
        left -= can
    return raised


def _buy_back_by_force(conn: Connection, s: dict, price: int, period: int, why: str) -> dict:
    """Buy the borrowed shares back for the lender, paid from the collateral (then the borrower's cash). Whatever
    shares cannot be found are settled with the lender in cash at the same price."""
    held = _collateral_account(conn)
    left, cost_total = s["shares"], 0
    pot = s["collateral"]
    for seller in _buyers(conn):
        if left <= 0:
            break
        have = ledger.balance(conn, seller, s["share_asset"])
        take = min(left, have)
        if take <= 0:
            continue
        cost = take * price
        from_pot = min(cost, pot)
        legs = [ledger.Leg(seller, -take, s["share_asset"]), ledger.Leg(s["lender"], take, s["share_asset"])]
        if from_pot:
            legs += [ledger.Leg(held, -from_pot), ledger.Leg(seller, from_pot)]
        ledger.post(conn, kind="buy_in", memo=f"{why}: {take:,} {s['ticker']} shares bought back at {money(price)}", period=period, legs=legs)
        pot -= from_pot
        if cost > from_pot:
            ledger.pay_up_to(conn, payer=s["borrower"], receiver=seller, wanted=cost - from_pot, kind="buy_in",
                             memo=f"{why}: the rest of the price", period=period)
        cost_total += cost
        left -= take
    if left > 0:
        # Not enough shares to be had: the lender is paid their value in cash instead.
        owed = left * price
        from_pot = min(owed, pot)
        if from_pot:
            ledger.transfer(conn, payer=held, receiver=s["lender"], amount=from_pot, kind="buy_in",
                            memo=f"{why}: {left:,} {s['ticker']} shares settled in cash", period=period)
            pot -= from_pot
        if owed > from_pot:
            ledger.pay_up_to(conn, payer=s["borrower"], receiver=s["lender"], wanted=owed - from_pot, kind="buy_in",
                             memo=f"{why}: the rest, settled in cash", period=period)
        cost_total += owed
    if pot > 0:
        ledger.transfer(conn, payer=held, receiver=s["borrower"], amount=pot, kind="short_release",
                        memo=f"What was left of the collateral after the buy-in of {s['ticker']}", period=period)
    return {"cost": cost_total, "returned_to_borrower": pot}


# ---------------------------------------------------------------------------
# At every Closing Bell: margin calls, forced sales and buy-ins
# ---------------------------------------------------------------------------

def at_bell(conn: Connection, now: datetime, ended: date) -> dict:
    """Measure every margin loan and short at the day's closing prices."""
    if _one(conn, "SELECT to_regclass('player_loans') IS NOT NULL AS ok")["ok"] is not True:
        return {}
    period = _state(conn, now)["period"]
    quotes = prices(conn)
    done = defaultdict(int)
    for loan in _rows(conn, "SELECT l.*, c.account_id AS bank_account, c.name AS bank FROM player_loans l JOIN companies c"
                            " ON c.id = l.bank_company_id WHERE l.kind = 'margin' AND l.status <> 'repaid' ORDER BY l.id"):
        with conn.transaction():
            loan = {**loan, **_one(conn, "SELECT outstanding, call_since FROM player_loans WHERE id = %s FOR UPDATE", (loan["id"],))}
            if loan["outstanding"] <= 0:
                continue
            held = holdings_value(conn, loan["borrower"], now)
            owed_all = margin_owed(conn, loan["borrower"])
            ratio = owed_all * BPS // max(held["total"], 1)
            unmet = loan["call_since"] is not None and loan["call_since"] < ended
            if ratio >= data.MARGIN_SELL_BPS or (unmet and ratio >= data.MARGIN_CALL_BPS):
                _restore_margin(conn, loan, held, owed_all, period, now)
                done["forced_sales"] += 1
            elif ratio >= data.MARGIN_CALL_BPS:
                if loan["call_since"] is None:
                    conn.execute("UPDATE player_loans SET call_since = %s WHERE id = %s", (ended, loan["id"]))
                    _event(conn, loan["borrower"], "margin_call",
                           f"Margin call: your loan from {loan['bank']} is {ratio / 100:.0f}% of your shares, bonds and cash. Repay some, or "
                           f"hold more, by the next Closing Bell, or shares will be sold.", now, loan_id=loan["id"])
                    done["calls"] += 1
            elif loan["call_since"] is not None:
                conn.execute("UPDATE player_loans SET call_since = NULL WHERE id = %s", (loan["id"],))
                _event(conn, loan["borrower"], "call_met", "The margin call is met.", now, loan_id=loan["id"])
    for s in _rows(conn, "SELECT s.*, c.share_asset, c.ticker FROM short_positions s JOIN companies c ON c.id = s.company_id"
                         " WHERE s.status = 'open' ORDER BY s.id"):
        q = quotes.get(s["company_id"])
        if q is None:
            continue
        with conn.transaction():
            s = {**s, **_one(conn, "SELECT collateral, call_since, status FROM short_positions WHERE id = %s FOR UPDATE", (s["id"],))}
            if s["status"] != "open":
                continue
            value = s["shares"] * q["price"]
            ratio = s["collateral"] * BPS // max(value, 1)
            unmet = s["call_since"] is not None and s["call_since"] < ended
            if ratio < data.SHORT_BUY_IN_BPS or (unmet and ratio < data.SHORT_CALL_BPS):
                _buy_in(conn, s, q["price"], period, now, "A forced buy-in")
                done["buy_ins"] += 1
            elif ratio < data.SHORT_CALL_BPS:
                if s["call_since"] is None:
                    conn.execute("UPDATE short_positions SET call_since = %s WHERE id = %s", (ended, s["id"]))
                    _event(conn, s["borrower"], "short_call",
                           f"Margin call: the collateral on your {s['ticker']} short is {ratio / 100:.0f}% of the shares' value. Add cash "
                           f"or close it by the next Closing Bell, or the shares will be bought back for you.", now, short_id=s["id"])
                    done["calls"] += 1
            elif s["call_since"] is not None:
                conn.execute("UPDATE short_positions SET call_since = NULL WHERE id = %s", (s["id"],))
    return dict(done)


def _restore_margin(conn: Connection, loan: dict, held: dict, owed_all: int, period: int, now: datetime) -> None:
    """Bring a margin loan back to half of what the borrower holds: their cash first, then their shares sold by force."""
    account = loan["borrower"]
    target = held["total"] * data.MARGIN_LOAN_MOST_BPS // BPS
    need = owed_all - target
    paid = 0
    if need > 0:
        # Each naira repaid lowers the loan and what is held alike: repaying x leaves (owed - x) / (total - x).
        # To reach half: x = 2 * owed - total.
        need = max(2 * owed_all - held["total"], 0)
        cash_part = min(need, max(ledger.balance(conn, account), 0))
        if cash_part:
            paid += ledger.pay_up_to(conn, payer=account, receiver=loan["bank_account"], wanted=min(cash_part, loan["outstanding"]),
                                     kind="loan_repayment", memo=f"Margin call not met: cash taken to repay {loan['bank']}", period=period)
        still = need - paid
        for line in sorted(held["lines"], key=lambda x: -x["value"]):
            if still <= 0 or loan["outstanding"] - paid <= 0:
                break
            price = line["price"] * (BPS - data.FORCED_SALE_DISCOUNT_BPS) // BPS
            # Selling raises cash at the discount and removes the shares at the full price, so more must go.
            sell = min(line["free"], -(-still // max(price, 1)))
            if sell <= 0:
                continue
            raised = _sell_by_force(conn, account, line, sell, price, period, "Margin call not met")
            got = ledger.pay_up_to(conn, payer=account, receiver=loan["bank_account"], wanted=min(raised, loan["outstanding"] - paid),
                                   kind="loan_repayment", memo=f"Shares sold by force to repay {loan['bank']}", period=period)
            paid += got
            still -= got
    left = loan["outstanding"] - paid
    conn.execute("UPDATE player_loans SET outstanding = %s, status = %s, call_since = NULL WHERE id = %s",
                 (left, "repaid" if left == 0 else "open", loan["id"]))
    _event(conn, account, "forced_sale", f"Your loan from {loan['bank']} was too large for what you hold: {money(paid)} was repaid "
                                         f"from your cash and from shares sold at 5% below the close.", now, loan_id=loan["id"])


def _buy_in(conn: Connection, s: dict, close_price: int, period: int, now: datetime, why: str) -> None:
    price = close_price * (BPS + data.BUY_IN_PREMIUM_BPS) // BPS
    result = _buy_back_by_force(conn, s, price, period, why)
    conn.execute("UPDATE short_positions SET status = 'bought_in', collateral = 0, closed_price = %s, closed_at = %s WHERE id = %s",
                 (price, now, s["id"]))
    _event(conn, s["borrower"], "buy_in", f"{why}: your borrowed {s['ticker']} shares were bought back at {money(price)} each "
                                          f"(5% above the close). {money(result['returned_to_borrower'])} of the collateral came back to you.",
           now, short_id=s["id"])


# ---------------------------------------------------------------------------
# At each quarter's close: interest, repayments, the lending fee, recalls
# ---------------------------------------------------------------------------

def close(conn: Connection, period: int, now: datetime, rate: int) -> dict:
    if _one(conn, "SELECT to_regclass('player_loans') IS NOT NULL AS ok")["ok"] is not True:
        return {}
    ensure(conn)
    label = clock.period_label(period)
    out = defaultdict(int)
    for loan in _rows(conn, "SELECT l.*, c.account_id AS bank_account, c.name AS bank FROM player_loans l JOIN companies c"
                            " ON c.id = l.bank_company_id WHERE l.status <> 'repaid' ORDER BY l.id"):
        new_rate = rate + (data.PERSONAL_LOAN_SPREAD_BPS if loan["kind"] == "personal" else data.MARGIN_LOAN_SPREAD_BPS)
        interest = loan["outstanding"] * new_rate // BPS // 4
        principal = min(max(loan["principal"] // loan["term_quarters"], 1), loan["outstanding"]) if loan["term_quarters"] else 0
        if loan["status"] == "default":
            principal = loan["outstanding"]                      # a loan in default: the bank takes all it can, each quarter
        paid_interest = ledger.pay_up_to(conn, payer=loan["borrower"], receiver=loan["bank_account"], wanted=interest, kind="player_loan_interest",
                                         memo=f"Interest to {loan['bank']}, {label}", period=period)
        paid_principal = 0
        if paid_interest == interest and principal:
            paid_principal = ledger.pay_up_to(conn, payer=loan["borrower"], receiver=loan["bank_account"], wanted=principal,
                                              kind="loan_repayment", memo=f"Repayment to {loan['bank']}, {label}", period=period)
        out["interest"] += paid_interest
        met = paid_interest == interest and paid_principal == principal
        missed = 0 if met else loan["missed"] + 1
        left = loan["outstanding"] - paid_principal
        status = "repaid" if left == 0 else ("default" if loan["status"] == "default" or missed >= data.LOAN_MISSES_TO_DEFAULT else "open")
        if status == "default" and loan["status"] != "default":
            _event(conn, loan["borrower"], "default", f"Two payments to {loan['bank']} missed: the loan is in default. No bank will lend "
                                                      f"to you until it is repaid, and the bank takes what it can each quarter.", now, loan_id=loan["id"])
            out["defaults"] += 1
        conn.execute("UPDATE player_loans SET outstanding = %s, rate_bps = %s, missed = %s, status = %s WHERE id = %s",
                     (left, new_rate, missed, status, loan["id"]))
    # Short sellers pay the lender's fee; the pension funds recall shares when they have lent too many.
    quotes = prices(conn)
    held = _collateral_account(conn)
    for s in _rows(conn, "SELECT s.*, c.share_asset, c.ticker FROM short_positions s JOIN companies c ON c.id = s.company_id"
                         " WHERE s.status = 'open' ORDER BY s.id"):
        q = quotes.get(s["company_id"])
        if q is None:
            continue
        if s["recalled_period"] is not None and s["recalled_period"] < period:
            _buy_in(conn, s, q["price"], period, now, "Recalled shares not given back")
            out["recall_buy_ins"] += 1
            continue
        fee = s["shares"] * q["price"] * data.SHORT_FEE_BPS // BPS // 4
        got = ledger.pay_up_to(conn, payer=s["borrower"], receiver=s["lender"], wanted=fee, kind="lending_fee",
                               memo=f"The lending fee on borrowed {s['ticker']} shares, {label}", period=period)
        if got < fee and s["collateral"] > 0:
            more = min(fee - got, s["collateral"])
            ledger.transfer(conn, payer=held, receiver=s["lender"], amount=more, kind="lending_fee",
                            memo=f"The lending fee, from the collateral, {label}", period=period)
            conn.execute("UPDATE short_positions SET collateral = collateral - %s WHERE id = %s", (more, s["id"]))
            got += more
        conn.execute("UPDATE short_positions SET fees_paid = fees_paid + %s WHERE id = %s", (got, s["id"]))
        out["fees"] += got
    for r in _rows(conn, "SELECT DISTINCT company_id FROM short_positions WHERE status = 'open'"):
        _recall_if_needed(conn, r["company_id"], period, now)
    return dict(out)


def _recall_if_needed(conn: Connection, company_id, period: int, now: datetime) -> None:
    lender = ledger.account_id(conn, LENDER)
    asset = _one(conn, "SELECT share_asset FROM companies WHERE id = %s", (company_id,))["share_asset"]
    held = ledger.balance(conn, lender, asset)
    positions = _rows(conn, "SELECT * FROM short_positions WHERE company_id = %s AND lender = %s AND status = 'open'"
                            " AND recalled_period IS NULL ORDER BY id DESC", (company_id, lender))
    lent = sum(p["shares"] for p in positions)
    for p in positions:
        if lent * BPS <= (held + lent) * data.LENDING_POOL_BPS:
            break
        conn.execute("UPDATE short_positions SET recalled_period = %s WHERE id = %s", (period, p["id"]))
        _event(conn, p["borrower"], "recall", "The pension funds have recalled the shares you borrowed. Give them back by the next "
                                              "quarter's close, or they will be bought back for you.", now, short_id=p["id"])
        lent -= p["shares"]


# ---------------------------------------------------------------------------
# Checks and views
# ---------------------------------------------------------------------------

def check_books(conn: Connection) -> list[str]:
    if _one(conn, "SELECT to_regclass('short_positions') IS NOT NULL AS ok")["ok"] is not True:
        return []
    row = _one(conn, "SELECT id FROM ledger_accounts WHERE code = %s", (COLLATERAL,))
    if row is None:
        return []
    held = ledger.balance(conn, row["id"])
    recorded = _one(conn, "SELECT coalesce(sum(collateral), 0)::bigint AS c FROM short_positions WHERE status = 'open'")["c"]
    return [] if held == recorded else [f"Short sellers' collateral: {held} held against {recorded} recorded."]


def view(conn: Connection, account, now: datetime, player_id=None) -> dict:
    """What an account owes and has borrowed, for its own owner only."""
    quotes = prices(conn)
    held = holdings_value(conn, account, now)
    loans = []
    for loan in _rows(conn, "SELECT l.*, c.name AS bank FROM player_loans l JOIN companies c ON c.id = l.bank_company_id"
                            " WHERE l.borrower = %s AND l.status <> 'repaid' ORDER BY l.id", (account,)):
        loans.append({"id": loan["id"], "kind": loan["kind"], "bank": loan["bank"], "principal": loan["principal"],
                      "outstanding": loan["outstanding"], "rate_bps": loan["rate_bps"], "missed": loan["missed"], "status": loan["status"],
                      "margin_call": loan["call_since"] is not None})
    owed = margin_owed(conn, account)
    shorts = []
    for s in _rows(conn, "SELECT s.*, c.ticker, c.name FROM short_positions s JOIN companies c ON c.id = s.company_id"
                         " WHERE s.borrower = %s AND s.status = 'open' ORDER BY s.id", (account,)):
        price = quotes.get(s["company_id"], {}).get("price", s["opened_price"])
        value = s["shares"] * price
        shorts.append({"id": s["id"], "ticker": s["ticker"], "name": s["name"], "shares": s["shares"], "opened_price": s["opened_price"],
                       "price": price, "value": value, "collateral": s["collateral"], "cover_bps": s["collateral"] * BPS // max(value, 1),
                       "gain": (s["opened_price"] - price) * s["shares"], "fees_paid": s["fees_paid"], "margin_call": s["call_since"] is not None,
                       "recalled": s["recalled_period"] is not None})
    events = [{"kind": e["kind"], "words": e["words"], "at": e["at"]} for e in _rows(
        conn, "SELECT kind, words, at FROM lending_events WHERE account = %s ORDER BY at DESC, id DESC LIMIT 12", (account,))]
    rate = policy_rate(conn)
    return {
        "loans": loans, "shorts": shorts, "events": events,
        "holdings": {"shares": held["shares"], "bonds": held["bonds"], "cash": held["cash"]},
        "margin": {"owed": owed, "limit": margin_limit(conn, account, now), "ratio_bps": owed * BPS // max(held["total"], 1),
                   "call_bps": data.MARGIN_CALL_BPS, "sell_bps": data.MARGIN_SELL_BPS},
        "personal_limit": personal_limit(conn, player_id, now) if player_id else 0,
        "rates": {"personal_bps": rate + data.PERSONAL_LOAN_SPREAD_BPS, "margin_bps": rate + data.MARGIN_LOAN_SPREAD_BPS,
                  "short_fee_bps": data.SHORT_FEE_BPS},
        "debts": debts(conn, account), "equity": _equity(conn, account, now),
        "most_debt_times": data.MOST_DEBT_TIMES_EQUITY,
    }


def lendable_view(conn: Connection) -> list[dict]:
    """Every share that can be borrowed now, how many, and how much is already lent (as a share of all shares)."""
    interest = short_interest(conn)
    out = []
    for q in sorted(prices(conn).values(), key=lambda x: x["ticker"]):
        out.append({"ticker": q["ticker"], "name": q["name"], "price": q["price"], "lendable": lendable(conn, q["company_id"]),
                    "short_interest_bps": interest.get(q["company_id"], 0)})
    return out


def _players_lending(conn: Connection) -> dict:
    """For players' net worth: collateral held for them counts as their cash; loans and borrowed shares are taken off."""
    out = {}
    if _one(conn, "SELECT to_regclass('player_loans') IS NOT NULL AS ok")["ok"] is not True:
        return out
    accounts = {r["a"] for r in _rows(conn, "SELECT borrower AS a FROM player_loans WHERE status <> 'repaid' UNION "
                                            "SELECT borrower FROM short_positions WHERE status = 'open'")}
    for account in accounts:
        if _kind_of(conn, account) != "player":
            continue
        out[account] = (collateral_held(conn, account), -loans_owed(conn, account) - short_liability(conn, account))
    return out


def _register() -> None:
    from simulation import marketview
    if _players_lending not in marketview._OTHER_HOLDINGS:
        marketview._OTHER_HOLDINGS.append(_players_lending)


_register()


