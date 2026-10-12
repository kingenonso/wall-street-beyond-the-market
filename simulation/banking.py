"""Banks lend for real (Stage 3, Part B; design document, section 11).

  * Households borrow from the banks, pay interest every quarter and repay a
    little of what they owe. How much they borrow depends on the interest
    rate and on their mindset.
  * Company loans carry a floating rate: the Central Bank's rate plus an
    amount for the borrower's credit rating. So a rate change reaches every loan.
  * A bank lends only while it has the owners' funds to support it, and keeps
    a reserve of ready cash. When it is short of cash to lend, it borrows from
    the Central Bank. That is the one way new money now comes into existence;
    when the bank repays, the money goes out of existence again.

Every naira moves through the ledger.
"""

from __future__ import annotations

from uuid import UUID

from psycopg import Connection
from psycopg.rows import dict_row

from simulation import clock, economy, ledger, macro
from simulation import world_data as data
from simulation.money import BPS, apply_bps

CENTRAL_BANK_LOAN_TERM = 4000        # quarters: in effect, open-ended


def _rows(conn: Connection, sql: str, params=()) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def banks(conn: Connection, period: int) -> list[dict]:
    """Every bank that lends to households, with what it needs to decide its lending."""
    return _rows(
        conn,
        "SELECT c.id, c.name, c.ticker, c.account_id, r.total_equity, r.customer_funds,"
        "   (SELECT coalesce(sum(principal), 0)::bigint FROM household_debts h WHERE h.bank_company_id = c.id) AS household_loans,"
        "   (SELECT coalesce(sum(principal_outstanding - provision), 0)::bigint FROM company_debts d"
        "     WHERE d.lender_account_id = c.account_id)"
        "   + (SELECT coalesce(sum(outstanding), 0)::bigint FROM mortgages m WHERE m.bank_company_id = c.id"
        "      AND m.status IN ('open', 'shortfall')) AS company_loans"
        " FROM companies c JOIN company_results r ON r.company_id = c.id AND r.period = %s"
        " WHERE EXISTS (SELECT 1 FROM household_debts h WHERE h.bank_company_id = c.id) ORDER BY c.ticker",
        (period - 1,),
    )


def lending_room(bank: dict) -> int:
    """How much more a bank may lend before its lending passes the limit set by its owners' funds."""
    return max(data.BANK_LENDING_LIMIT_X * max(bank["total_equity"], 0) - bank["household_loans"] - bank["company_loans"], 0)


def reserve(bank: dict) -> int:
    """The ready cash a bank must keep against its customers' money."""
    return apply_bps(bank["customer_funds"], data.BANK_RESERVE_BPS)


def reprice_loans(conn: Connection, period: int, policy_rate_bps: int) -> None:
    """Bring every floating-rate loan to this quarter's rate: the Central Bank's rate plus
    an amount for the borrower's latest credit rating. Bonds keep the rate they were sold at."""
    loans = _rows(
        conn,
        "SELECT d.id, d.kind, d.name,"
        "   (SELECT p.credit_rating FROM company_reports p WHERE p.company_id = d.company_id"
        "     ORDER BY p.period DESC, p.version DESC LIMIT 1) AS rating"
        " FROM company_debts d WHERE d.kind IN ('bank_loan', 'central_bank_loan') AND d.principal_outstanding > 0",
    )
    for loan in loans:
        if loan["kind"] == "central_bank_loan":
            rate = policy_rate_bps
        else:
            rate = macro.loan_rate_bps(policy_rate_bps, loan["rating"], loan["name"].startswith("overdue"))
        conn.execute("UPDATE company_debts SET annual_rate_bps = %s WHERE id = %s", (rate, loan["id"]))


def ensure_cash(conn: Connection, world: economy.World, bank: dict, needed: int, period: int,
                policy_rate_bps: int) -> None:
    """Make sure a bank can pay out `needed` and still hold its reserve, borrowing from the
    Central Bank if it must. This is where new money comes into existence."""
    short = needed + reserve(bank) - ledger.balance(conn, bank["account_id"])
    if short <= 0:
        return
    # The Central Bank lends only to a bank that still has funds of its own, and never more
    # in all than a fixed multiple of them. A bank that has lost its owners' funds is left
    # to fall behind on its bills like any other failing company.
    owed = _rows(conn, "SELECT coalesce(sum(principal_outstanding), 0)::bigint AS total FROM company_debts"
                       " WHERE company_id = %s AND kind = 'central_bank_loan'", (bank["id"],))[0]["total"]
    short = min(short, max(data.CENTRAL_BANK_LENDING_LIMIT_X * max(bank["total_equity"], 0) - owed, 0))
    if short <= 0:
        return
    ledger.transfer(
        conn, payer=world.central_bank, receiver=bank["account_id"], amount=short, kind="central_bank_lending",
        memo=f"Central Bank lends to {bank['name']}, {clock.period_label(period)}", period=period,
    )
    updated = conn.execute(
        "UPDATE company_debts SET principal_outstanding = principal_outstanding + %s,"
        " original_principal = original_principal + %s, annual_rate_bps = %s"
        " WHERE company_id = %s AND kind = 'central_bank_loan'",
        (short, short, policy_rate_bps, bank["id"]),
    ).rowcount
    if not updated:
        conn.execute(
            "INSERT INTO company_debts (company_id, lender_account_id, kind, name, original_principal,"
            " principal_outstanding, annual_rate_bps, start_period, maturity_period, repayment)"
            " VALUES (%s, %s, 'central_bank_loan', 'borrowing from the Central Bank', %s, %s, %s, %s, %s, 'bullet')",
            (bank["id"], world.central_bank, short, short, policy_rate_bps, period, period + CENTRAL_BANK_LOAN_TERM),
        )


def repay_central_bank(conn: Connection, world: economy.World, bank: dict, period: int) -> int:
    """A bank holding far more cash than it needs pays back what it borrowed from the
    Central Bank. The money repaid goes out of existence."""
    owed = _rows(conn, "SELECT id, principal_outstanding FROM company_debts WHERE company_id = %s"
                       " AND kind = 'central_bank_loan' AND principal_outstanding > 0", (bank["id"],))
    if not owed:
        return 0
    spare = ledger.balance(conn, bank["account_id"]) - 3 * reserve(bank)
    amount = min(spare, owed[0]["principal_outstanding"])
    if amount <= 0:
        return 0
    ledger.transfer(
        conn, payer=bank["account_id"], receiver=world.central_bank, amount=amount, kind="debt_repayment",
        memo=f"{bank['name']} repays the Central Bank, {clock.period_label(period)}", period=period,
        reference=f"debt:{owed[0]['id']}",
    )
    conn.execute("UPDATE company_debts SET principal_outstanding = principal_outstanding - %s WHERE id = %s",
                 (amount, owed[0]["id"]))
    return amount


def room_to_borrow_bps(owed: int, quarterly_income: int) -> int:
    """How freely households add to their debts (10000 = the usual growth).

    Owing about three quarters' income is comfortable. The more they owe beyond
    that, the less they add; at twice that level their borrowing stops growing.
    Owing less, they add more freely, up to twice the usual.
    """
    comfortable = data.HOUSEHOLD_DEBT_COMFORT_QUARTERS * quarterly_income
    if comfortable <= 0:
        return 0
    return int(min(max(2 * BPS - owed * BPS // comfortable, 0), 2 * BPS))


def household_credit(conn: Connection, world: economy.World, period: int, policy_rate_bps: int,
                     borrow_bps: dict[str, int], lending_factor_bps: int) -> tuple[dict[str, int], dict[str, int]]:
    """One quarter of household borrowing. Returns what each location's households newly
    borrowed, and what they paid the banks in interest and repayments.

      1. Households pay interest on what they owe.
      2. They repay part of it.
      3. Banks lend again: more when the interest rate is low and households are
         confident, less when it is high, and never beyond what a bank's own funds allow.
    """
    label = clock.period_label(period)
    all_banks = banks(conn, period)
    by_id = {bank["id"]: bank for bank in all_banks}
    debts = _rows(conn, "SELECT * FROM household_debts WHERE principal > 0 ORDER BY bank_company_id, location")
    rate = policy_rate_bps + data.HOUSEHOLD_LOAN_SPREAD_BPS

    # 1 and 2: each location pays all its banks at once.
    service = {location: 0 for location in world.households}
    for location, household in world.households.items():
        mine = [d for d in debts if d["location"] == location]
        if not mine:
            continue
        interest = {by_id[d["bank_company_id"]]["account_id"]: (d["principal"] * rate + 2 * BPS) // (4 * BPS) for d in mine}
        service[location] += ledger.pay_split_up_to(
            conn, payer=household["account_id"], amounts=interest, kind="loan_interest",
            memo=f"Households of {location}: interest on their loans, {label}", period=period,
        )
        repaid: dict[UUID, int] = {}
        service[location] += ledger.pay_split_up_to(
            conn, payer=household["account_id"], kind="household_loan_repayment", paid_to=repaid,
            amounts={by_id[d["bank_company_id"]]["account_id"]: apply_bps(d["principal"], data.HOUSEHOLD_REPAY_BPS) for d in mine},
            memo=f"Households of {location}: loan repayments, {label}", period=period,
        )
        for d in mine:
            paid = repaid.get(by_id[d["bank_company_id"]]["account_id"], 0)
            if paid:
                conn.execute("UPDATE household_debts SET principal = principal - %s WHERE bank_company_id = %s AND location = %s",
                             (paid, d["bank_company_id"], location))
                d["principal"] -= paid
                by_id[d["bank_company_id"]]["household_loans"] -= paid

    # 3: new lending, bank by bank.
    appetite = macro.credit_appetite_bps(policy_rate_bps)
    # How heavily each location's households are already in debt, against what they earn.
    income = {
        r["location"]: r["income"]
        for r in _rows(conn, "SELECT location, income FROM household_results WHERE period = %s", (period - 1,))
    }
    owed = {location: sum(d["principal"] for d in debts if d["location"] == location) for location in world.households}
    borrowed = {location: 0 for location in world.households}
    for bank in all_banks:
        repay_central_bank(conn, world, bank, period)
        wanted: dict[UUID, int] = {}
        for d in debts:
            if d["bank_company_id"] != bank["id"]:
                continue
            # What was just repaid is lent again, plus a little growth, scaled by how
            # attractive borrowing is at this rate and by the mood of that location.
            usual = apply_bps(d["principal"], data.HOUSEHOLD_REPAY_BPS
                              + apply_bps(data.CREDIT_GROWTH_BPS, room_to_borrow_bps(owed[d["location"]], income.get(d["location"], 0))))
            amount = apply_bps(apply_bps(apply_bps(usual, appetite), borrow_bps.get(d["location"], BPS)), lending_factor_bps)
            wanted[world.households[d["location"]]["account_id"]] = amount
        total = sum(wanted.values())
        room = lending_room(bank)
        if total > room:                                     # the bank's own funds limit what it may lend
            wanted = economy.split(room, wanted)
            total = sum(wanted.values())
        if total <= 0:
            continue
        ensure_cash(conn, world, bank, total, period, policy_rate_bps)
        lent: dict[UUID, int] = {}
        ledger.pay_split_up_to(
            conn, payer=bank["account_id"], amounts=wanted, kind="household_loan", paid_to=lent,
            memo=f"{bank['name']}: new loans to households, {label}", period=period,
        )
        for location, household in world.households.items():
            amount = lent.get(household["account_id"], 0)
            if amount:
                conn.execute("UPDATE household_debts SET principal = principal + %s WHERE bank_company_id = %s AND location = %s",
                             (amount, bank["id"], location))
                borrowed[location] += amount
    return borrowed, service
