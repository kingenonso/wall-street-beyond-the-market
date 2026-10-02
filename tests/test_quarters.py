"""Closing game quarters: every company's accounts, every quarter.

Stage 2 checklist items 7, 9 and 10, and the test that finishes the stage:

    Eight game quarters run. Every balance sheet balances.
    No naira appears without a recorded payer.
"""

from __future__ import annotations

import threading
from datetime import timedelta

import pytest
from psycopg import errors
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from simulation import companies, ledger, quarters
from simulation.companies import BALANCE_SHEET_LINES, CASH_FLOW_LINES, INCOME_LINES
from simulation.money import naira
from tests.conftest import WORLD_START, after_quarters


def _dicts(db, sql, params=()):
    with db.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def _company(db, ticker):
    return _dicts(db, "SELECT * FROM companies WHERE ticker = %s", (ticker,))[0]


# ---------------------------------------------------------------------------
# THE STAGE TEST
# ---------------------------------------------------------------------------

@pytest.mark.world("eight")
class TestStageTwo:
    def test_eight_game_quarters_ran(self, db):
        assert db.execute("SELECT last_closed_period FROM world_state").fetchone()[0] == 8
        per_period = db.execute("SELECT period, count(*) FROM company_results GROUP BY period ORDER BY period").fetchall()
        assert per_period == [(p, 40) for p in range(9)]          # the opening position and eight quarters

    def test_every_balance_sheet_balances_from_independent_records(self, db):
        """Each figure is re-read from where it is truly kept, then the sheet is added up again."""
        checked = 0
        for r in _dicts(db, "SELECT r.*, c.name, c.account_id FROM company_results r JOIN companies c ON c.id = r.company_id"):
            assert r["total_assets"] == r["cash"] + r["customer_loans"] + r["loans_to_companies"] + r["fixed_assets"], r["name"]
            assert r["total_liabilities"] == r["borrowings"] + r["payables"] + r["customer_funds"], r["name"]
            assert r["total_equity"] == r["share_capital"] + r["retained_earnings"], r["name"]
            assert r["total_assets"] == r["total_liabilities"] + r["total_equity"], f"{r['name']} period {r['period']}"
            checked += 1
        assert checked == 360

        # At the latest quarter, the sheet's figures match the ledger and the debt records.
        for r in _dicts(db, "SELECT r.*, c.name, c.id, c.account_id FROM company_results r JOIN companies c ON c.id = r.company_id WHERE r.period = 8"):
            assert r["cash"] == ledger.balance(db, r["account_id"]), r["name"]
            owed = db.execute("SELECT coalesce(sum(principal_outstanding), 0) FROM company_debts WHERE company_id = %s", (r["id"],)).fetchone()[0]
            lent = db.execute("SELECT coalesce(sum(principal_outstanding), 0) FROM company_debts WHERE lender_account_id = %s", (r["account_id"],)).fetchone()[0]
            assert (r["borrowings"], r["loans_to_companies"]) == (owed, lent), r["name"]

    def test_no_naira_appears_without_a_recorded_payer(self, db):
        # 1. Every transaction has at least one payer and one receiver, and adds up to zero.
        broken = db.execute(
            "SELECT count(*) FROM (SELECT transaction_id FROM ledger_entries GROUP BY transaction_id, asset"
            " HAVING sum(amount) <> 0 OR count(*) FILTER (WHERE amount < 0) = 0 OR count(*) FILTER (WHERE amount > 0) = 0) x"
        ).fetchone()[0]
        assert broken == 0

        # 2. The only payer that can pay without having been paid first is the Central Bank,
        #    and it paid out once: the opening balances. Nothing since.
        issued_kinds = db.execute(
            "SELECT DISTINCT t.kind FROM ledger_entries e JOIN ledger_transactions t ON t.id = e.transaction_id"
            " JOIN ledger_accounts a ON a.id = e.account_id WHERE a.code = 'central_bank' AND e.asset = 'NGN'"
        ).fetchall()
        assert issued_kinds == [("opening_balance",)]

        # 3. So the money in existence after eight quarters is exactly the opening money.
        opening = db.execute(
            "SELECT sum(e.amount) FROM ledger_entries e JOIN ledger_transactions t ON t.id = e.transaction_id"
            " WHERE t.kind = 'opening_balance' AND e.amount > 0"
        ).fetchone()[0]
        assert ledger.amount_in_existence(db) == opening

        # 4. And nobody but the Central Bank is below zero.
        assert db.execute(
            "SELECT count(*) FROM ledger_balances b JOIN assets a ON a.code = b.asset"
            " WHERE b.balance < 0 AND b.account_id <> a.issuer_account_id"
        ).fetchone()[0] == 0

    def test_every_transaction_carries_a_reason(self, db):
        assert db.execute("SELECT count(*) FROM ledger_transactions WHERE kind = '' OR memo = ''").fetchone()[0] == 0
        kinds = {k for (k,) in db.execute("SELECT DISTINCT kind FROM ledger_transactions").fetchall()}
        assert kinds == {
            "opening_balance", "share_issue", "customer_revenue", "cost_of_sales", "operating_expenses",
            "debt_interest", "company_tax", "debt_repayment", "capital_spending", "dividend",
            "government_spending", "investor_spending",
        }


# ---------------------------------------------------------------------------
# Item 7 and 9: the three statements, updated every quarter
# ---------------------------------------------------------------------------

@pytest.mark.world("eight")
def test_the_income_statement_adds_up(db):
    for r in _dicts(db, "SELECT * FROM company_results WHERE period >= 1"):
        assert r["operating_profit"] == r["revenue"] + r["interest_income"] - r["cost_of_sales"] - r["operating_expenses"] - r["depreciation"]
        assert r["profit_before_tax"] == r["operating_profit"] - r["interest_expense"]
        assert r["net_profit"] == r["profit_before_tax"] - r["tax"]
        assert r["tax"] >= 0 and r["revenue"] > 0


@pytest.mark.world("eight")
def test_the_cash_flow_statement_is_what_the_ledger_shows(db):
    """Opening cash plus the quarter's flows equals closing cash, and each flow matches ledger movements."""
    for r in _dicts(db, "SELECT r.*, c.account_id, c.name FROM company_results r JOIN companies c ON c.id = r.company_id WHERE r.period >= 1"):
        assert r["cash_closing"] == r["cash_opening"] + r["cash_from_operations"] + r["cash_from_investing"] + r["cash_from_financing"]
        moved = db.execute(
            "SELECT coalesce(sum(e.amount), 0) FROM ledger_entries e JOIN ledger_transactions t ON t.id = e.transaction_id"
            " WHERE e.account_id = %s AND e.asset = 'NGN' AND t.period = %s",
            (r["account_id"], r["period"]),
        ).fetchone()[0]
        assert moved == r["cash_closing"] - r["cash_opening"], f"{r['name']} period {r['period']}"

    # Each quarter opens where the last one closed.
    gaps = db.execute(
        "SELECT count(*) FROM company_results a JOIN company_results b"
        " ON b.company_id = a.company_id AND b.period = a.period + 1 WHERE b.cash_opening <> a.cash_closing"
    ).fetchone()[0]
    assert gaps == 0


@pytest.mark.world("eight")
def test_accounts_change_every_quarter(db):
    for c in _dicts(db, "SELECT id, name FROM companies"):
        revenues = [r[0] for r in db.execute("SELECT revenue FROM company_results WHERE company_id = %s AND period >= 1 ORDER BY period", (c["id"],)).fetchall()]
        assert len(revenues) == 8 and len(set(revenues)) == 8, c["name"]


@pytest.mark.world("eight")
def test_debt_outstanding_matches_the_repayments_in_the_ledger(db):
    for d in _dicts(db, "SELECT * FROM company_debts"):
        repaid = db.execute(
            "SELECT coalesce(sum(e.amount), 0) FROM ledger_entries e JOIN ledger_transactions t ON t.id = e.transaction_id"
            " WHERE t.kind = 'debt_repayment' AND t.reference = %s AND e.amount > 0",
            (f"debt:{d['id']}",),
        ).fetchone()[0]
        assert d["principal_outstanding"] == d["original_principal"] - repaid, d["name"]


@pytest.mark.world("eight")
def test_a_lenders_interest_income_is_exactly_what_its_borrowers_paid(db):
    for bank in _dicts(db, "SELECT * FROM companies WHERE sector = 'banking'"):
        for period in (1, 8):
            income = db.execute("SELECT interest_income FROM company_results WHERE company_id = %s AND period = %s", (bank["id"], period)).fetchone()[0]
            paid = db.execute(
                "SELECT coalesce(sum(e.amount), 0) FROM ledger_entries e JOIN ledger_transactions t ON t.id = e.transaction_id"
                " WHERE t.kind = 'debt_interest' AND t.period = %s AND e.account_id = %s AND e.amount > 0",
                (period, bank["account_id"]),
            ).fetchone()[0]
            assert income == paid > 0, bank["name"]


@pytest.mark.world("eight")
def test_dividends_are_shared_in_proportion_to_shares_held(db):
    company = _company(db, "IDC")
    tx = db.execute(
        "SELECT t.id FROM ledger_transactions t JOIN ledger_entries e ON e.transaction_id = t.id"
        " WHERE t.kind = 'dividend' AND t.period = 8 AND e.account_id = %s", (company["account_id"],)
    ).fetchone()[0]
    legs = dict(db.execute("SELECT account_id, amount FROM ledger_entries WHERE transaction_id = %s", (tx,)).fetchall())
    paid_out = -legs.pop(company["account_id"])
    shares = dict(db.execute("SELECT account_id, balance FROM ledger_balances WHERE asset = %s AND balance > 0", (company["share_asset"],)).fetchall())
    total_shares = sum(shares.values())
    assert sum(legs.values()) == paid_out
    for holder, amount in legs.items():
        assert abs(amount - paid_out * shares[holder] // total_shares) <= 1      # exact share, within a kobo


def test_a_payment_still_being_saved_when_the_quarter_closes_is_not_lost(db, connect):
    """Loophole question 4 (timing): a payment to a company that overlaps the
    quarter close is counted in full, and the books still balance."""
    company = _company(db, "ONP")
    extra = naira(7_000_000)
    paying = connect()
    paying.execute("BEGIN")
    ledger.transfer(paying, payer=ledger.account_id(paying, ledger.PUBLIC), receiver=company["account_id"],
                    amount=extra, kind="customer_revenue", memo="A sale still being saved")

    closed: list[list[int]] = []
    closer = threading.Thread(target=lambda: closed.append(quarters.close_due_quarters(connect(), after_quarters(1))))
    closer.start()
    closer.join(timeout=1.5)
    assert closer.is_alive()                       # the close waits for the payment; it does not skip it
    paying.execute("COMMIT")
    closer.join(timeout=60)

    assert closed == [[1]]
    q1 = _dicts(db, "SELECT * FROM company_results WHERE company_id = %s AND period = 1", (company["id"],))[0]
    planned = db.execute(
        "SELECT e.amount FROM ledger_entries e JOIN ledger_transactions t ON t.id = e.transaction_id"
        " WHERE t.kind = 'customer_revenue' AND t.period = 1 AND e.account_id = %s", (company["account_id"],)
    ).fetchone()[0]
    assert q1["revenue"] == planned + extra
    assert q1["cash"] == ledger.balance(db, company["account_id"])
    assert q1["total_assets"] == q1["total_liabilities"] + q1["total_equity"]


# ---------------------------------------------------------------------------
# The calendar: a quarter closes once, in order, and never early
# ---------------------------------------------------------------------------

def test_a_quarter_cannot_close_before_it_has_ended(db):
    """Loophole question 10 (the clock)."""
    assert quarters.close_due_quarters(db, WORLD_START - timedelta(days=30)) == []
    assert quarters.close_due_quarters(db, WORLD_START + timedelta(days=6, hours=23, minutes=59)) == []
    assert db.execute("SELECT count(*) FROM company_results WHERE period = 1").fetchone()[0] == 0
    assert quarters.close_due_quarters(db, WORLD_START + timedelta(days=7)) == [1]


def test_closing_again_does_not_pay_anything_twice(db):
    """Loophole question 3 (farming): a quarter's payments happen once."""
    assert quarters.close_due_quarters(db, after_quarters(2)) == [1, 2]
    snapshot = db.execute("SELECT count(*), sum(abs(amount)) FROM ledger_entries").fetchone()
    assert quarters.close_due_quarters(db, after_quarters(2)) == []
    assert quarters.close_due_quarters(db, after_quarters(2)) == []
    assert db.execute("SELECT count(*), sum(abs(amount)) FROM ledger_entries").fetchone() == snapshot


def test_missed_quarters_are_caught_up_in_order(db):
    assert quarters.close_due_quarters(db, after_quarters(3)) == [1, 2, 3]
    assert quarters.close_due_quarters(db, after_quarters(5)) == [4, 5]


def test_two_servers_closing_at_the_same_instant_close_each_quarter_once(db, connect):
    """Loophole question 4 (timing)."""
    barrier = threading.Barrier(3)
    closed: list[list[int]] = []

    def close():
        conn = connect()
        barrier.wait()
        closed.append(quarters.close_due_quarters(conn, after_quarters(2)))

    threads = [threading.Thread(target=close) for _ in range(3)]
    [t.start() for t in threads]
    [t.join() for t in threads]

    assert sorted(sum(closed, [])) == [1, 2]
    assert db.execute("SELECT count(*) FROM company_results WHERE period IN (1, 2)").fetchone()[0] == 80
    assert db.execute("SELECT count(*) FROM ledger_transactions WHERE kind = 'government_spending'").fetchone()[0] == 2


@pytest.mark.world("empty")
def test_nothing_closes_before_the_world_exists(db):
    assert quarters.close_due_quarters(db, after_quarters(4)) == []


# ---------------------------------------------------------------------------
# Item 10: the reported record is kept apart from the true record
# ---------------------------------------------------------------------------

@pytest.mark.world("eight")
def test_every_company_files_a_report_every_quarter(db):
    assert db.execute("SELECT count(*), count(DISTINCT (company_id, period)) FROM company_reports").fetchone() == (360, 360)


@pytest.mark.world("eight")
def test_honest_companies_report_exactly_what_happened(db):
    for row in _dicts(db, "SELECT r.*, p.figures FROM company_results r JOIN company_reports p ON p.company_id = r.company_id AND p.period = r.period AND p.version = 1"):
        filed = row["figures"]
        for section, lines in (("income_statement", INCOME_LINES), ("cash_flow", CASH_FLOW_LINES), ("balance_sheet", BALANCE_SHEET_LINES)):
            assert filed[section] == {line: row[line] for line in lines}


@pytest.mark.world("eight")
def test_a_false_report_can_be_filed_without_touching_the_truth(db):
    """The foundation for fraud (Stage 11): what is filed and what happened are separate records."""
    company = _company(db, "ONP")
    truth_before = _dicts(db, "SELECT * FROM company_results WHERE company_id = %s AND period = 8", (company["id"],))[0]
    honest = db.execute("SELECT figures FROM company_reports WHERE company_id = %s AND period = 8", (company["id"],)).fetchone()[0]

    false_figures = {**honest, "income_statement": {**honest["income_statement"], "revenue": honest["income_statement"]["revenue"] + naira(310_000_000)}}
    db.execute(
        "INSERT INTO company_reports (company_id, period, version, figures, credit_rating, rating_reasons, filed_by)"
        " VALUES (%s, 8, 2, %s, 'AAA', '[]', 'Company management')",
        (company["id"], Jsonb(false_figures)),
    )

    truth_after = _dicts(db, "SELECT * FROM company_results WHERE company_id = %s AND period = 8", (company["id"],))[0]
    assert truth_after == truth_before
    gap = false_figures["income_statement"]["revenue"] - truth_after["revenue"]
    assert gap == naira(310_000_000)               # the gap an auditor will one day find


@pytest.mark.world("eight")
@pytest.mark.parametrize("statement", [
    "UPDATE company_results SET revenue = revenue * 2",
    "DELETE FROM company_results",
    "TRUNCATE company_results",
    "UPDATE company_reports SET credit_rating = 'AAA'",
    "DELETE FROM company_reports",
    "TRUNCATE company_reports",
])
def test_true_and_reported_records_cannot_be_rewritten(db, statement):
    with pytest.raises(errors.RestrictViolation):
        db.execute(statement)


def test_the_database_refuses_a_balance_sheet_that_does_not_balance(db):
    row = _dicts(db, "SELECT * FROM company_results WHERE period = 0 LIMIT 1")[0]
    row.update(period=99, total_assets=row["total_assets"] + 1, drivers={"revenue": [], "notes": []})
    row.pop("closed_at")
    with pytest.raises(errors.CheckViolation):
        companies.insert_result(db, row)


# ---------------------------------------------------------------------------
# When things go wrong, the books still balance and no money appears
# ---------------------------------------------------------------------------

def _drain(db, account, keep=0):
    """Move an account's cash to the Treasury, leaving `keep` behind."""
    amount = ledger.balance(db, account) - keep
    ledger.transfer(db, payer=account, receiver=ledger.account_id(db, ledger.TREASURY), amount=amount, kind="test_drain", memo="Test: cash removed", period=None)


def test_a_cash_movement_the_engine_does_not_understand_stops_the_quarter(db):
    """The engine never guesses. If a company's cash moved for a reason it has no
    place for, the quarter is refused whole: nothing is half-closed."""
    company = _company(db, "DFL")
    money_before = ledger.amount_in_existence(db)
    quarters.close_due_quarters(db, after_quarters(1))
    entries_before = db.execute("SELECT count(*) FROM ledger_entries").fetchone()[0]

    _drain(db, company["account_id"], keep=naira(1_000))
    with pytest.raises(companies.BooksDoNotBalance):
        quarters.close_due_quarters(db, after_quarters(2))

    assert db.execute("SELECT last_closed_period FROM world_state").fetchone()[0] == 1
    assert db.execute("SELECT count(*) FROM company_results WHERE period = 2").fetchone()[0] == 0
    assert db.execute("SELECT count(*) FROM ledger_entries").fetchone()[0] == entries_before + 2   # only the test's own transfer
    assert ledger.amount_in_existence(db) == money_before


def test_sales_paid_between_quarter_closes_are_counted_once_in_the_next_quarter(db):
    """Money a company receives at any time lands in exactly one quarter's accounts."""
    company = _company(db, "ONP")
    quarters.close_due_quarters(db, after_quarters(1))
    extra = naira(5_000_000)
    ledger.transfer(db, payer=ledger.account_id(db, ledger.PUBLIC), receiver=company["account_id"], amount=extra,
                    kind="customer_revenue", memo="A sale made between quarter closes")

    quarters.close_due_quarters(db, after_quarters(3))

    q2, q3 = _dicts(db, "SELECT * FROM company_results WHERE company_id = %s AND period IN (2, 3) ORDER BY period", (company["id"],))
    planned_q2 = db.execute(
        "SELECT e.amount FROM ledger_entries e JOIN ledger_transactions t ON t.id = e.transaction_id"
        " WHERE t.kind = 'customer_revenue' AND t.period = 2 AND e.account_id = %s", (company["account_id"],)
    ).fetchone()[0]
    assert q2["revenue"] == planned_q2 + extra                     # counted in quarter 2
    assert q3["cash_opening"] == q2["cash_closing"]                # and not again in quarter 3
    for r in (q2, q3):
        assert r["total_assets"] == r["total_liabilities"] + r["total_equity"]


def test_customers_short_of_money_buy_less_and_weak_companies_fall_behind_on_bills(db):
    money_before = ledger.amount_in_existence(db)
    public = ledger.account_id(db, ledger.PUBLIC)
    # Customers start the world with only a little money: not enough to buy what companies plan to sell.
    amount = ledger.balance(db, public) - naira(900_000_000_000)
    ledger.transfer(db, payer=public, receiver=ledger.account_id(db, ledger.TREASURY), amount=amount, kind="test_drain", memo="Test: customers are poor", period=None)

    assert quarters.close_due_quarters(db, after_quarters(6)) == [1, 2, 3, 4, 5, 6]

    # Sales fell short of plan somewhere, and the cause was recorded.
    short = db.execute("SELECT count(*) FROM company_results WHERE drivers -> 'revenue' @> '[\"Customers ran short of money and bought less than they wanted\"]'").fetchone()[0]
    assert short > 0
    # Some companies could not pay everything. What they could not pay is owed, not conjured.
    owing = _dicts(db, "SELECT r.*, p.credit_rating FROM company_results r JOIN company_reports p ON p.company_id = r.company_id AND p.period = r.period WHERE r.payables > 0")
    assert owing, "expected at least one company to fall behind"
    for r in owing:
        assert r["total_assets"] == r["total_liabilities"] + r["total_equity"]
        assert r["credit_rating"] in ("CCC", "D")
        assert r["dividends_paid"] == 0            # no dividends while bills are unpaid
    # No money was created, and nobody went below zero.
    assert ledger.amount_in_existence(db) == money_before
    assert db.execute("SELECT count(*) FROM ledger_balances b JOIN assets a ON a.code = b.asset WHERE b.balance < 0 AND b.account_id <> a.issuer_account_id").fetchone()[0] == 0
    # What is owed in the payables table is what the balance sheets say.
    for r in _dicts(db, "SELECT company_id, payables FROM company_results WHERE period = 6"):
        owed = db.execute("SELECT coalesce(sum(amount_outstanding), 0) FROM company_payables WHERE company_id = %s", (r["company_id"],)).fetchone()[0]
        assert owed == r["payables"]


def test_the_books_hold_together_over_a_long_run(db):
    """Thirty-four quarters: past the end date of every bank loan (24) and every bond (32)."""
    money_before = ledger.amount_in_existence(db)
    assert len(quarters.close_due_quarters(db, after_quarters(34))) == 34

    assert ledger.amount_in_existence(db) == money_before
    assert db.execute("SELECT sum(balance) FROM ledger_balances WHERE asset = 'NGN'").fetchone()[0] == 0
    assert db.execute("SELECT count(*) FROM company_results").fetchone()[0] == 40 * 35
    unbalanced = db.execute("SELECT count(*) FROM company_results WHERE total_assets <> total_liabilities + total_equity").fetchone()[0]
    assert unbalanced == 0
    # Every loan and bond that reached its end date was either repaid in full or is flagged as overdue.
    for d in _dicts(db, "SELECT d.*, r.principal_overdue FROM company_debts d JOIN company_results r ON r.company_id = d.company_id AND r.period = 34"):
        assert d["principal_outstanding"] == 0 or d["principal_overdue"] >= d["principal_outstanding"]
    for r in _dicts(db, "SELECT p.credit_rating, r.principal_overdue FROM company_reports p JOIN company_results r ON r.company_id = p.company_id AND r.period = p.period WHERE p.period = 34"):
        assert (r["credit_rating"] == "D") == (r["principal_overdue"] > 0)
