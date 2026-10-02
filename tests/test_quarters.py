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
from tests.conftest import WORLD_START, after_quarters, money_accounted_for


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
        assert per_period == [(p, 50) for p in range(9)]          # the opening position and eight quarters

    def test_every_balance_sheet_balances_from_independent_records(self, db):
        """Each figure is re-read from where it is truly kept, then the sheet is added up again."""
        checked = 0
        for r in _dicts(db, "SELECT r.*, c.name, c.account_id FROM company_results r JOIN companies c ON c.id = r.company_id"):
            assert r["total_assets"] == r["cash"] + r["customer_loans"] + r["loans_to_companies"] + r["fixed_assets"], r["name"]
            assert r["total_liabilities"] == r["borrowings"] + r["payables"] + r["customer_funds"], r["name"]
            assert r["total_equity"] == r["share_capital"] + r["retained_earnings"], r["name"]
            assert r["total_assets"] == r["total_liabilities"] + r["total_equity"], f"{r['name']} period {r['period']}"
            checked += 1
        assert checked == 450

        # At the latest quarter, the sheet's figures match the ledger and the debt records.
        for r in _dicts(db, "SELECT r.*, c.name, c.id, c.account_id FROM company_results r JOIN companies c ON c.id = r.company_id WHERE r.period = 8"):
            # Cash on the sheet is everything the ledger had received less everything paid, at the close.
            in_and_out = sum(k["received"] - k["paid"] for k in r["ledger_totals"].values())
            assert r["cash"] == in_and_out, r["name"]
            # Anything that has arrived since (the Government's orders, other companies' building
            # work) is in the bank already and will be counted as next quarter's sales.
            assert ledger.balance(db, r["account_id"]) >= r["cash"], r["name"]
            owed = db.execute("SELECT coalesce(sum(principal_outstanding), 0) FROM company_debts WHERE company_id = %s", (r["id"],)).fetchone()[0]
            # A lender shows its loans at what it still expects to be repaid: less what it has written off.
            lent = db.execute("SELECT coalesce(sum(principal_outstanding - provision), 0) FROM company_debts WHERE lender_account_id = %s", (r["account_id"],)).fetchone()[0]
            assert (r["borrowings"], r["loans_to_companies"]) == (owed, lent), r["name"]

    def test_no_naira_appears_without_a_recorded_payer(self, db):
        # 1. Every transaction has at least one payer and one receiver, and adds up to zero.
        broken = db.execute(
            "SELECT count(*) FROM (SELECT transaction_id FROM ledger_entries GROUP BY transaction_id, asset"
            " HAVING sum(amount) <> 0 OR count(*) FILTER (WHERE amount < 0) = 0 OR count(*) FILTER (WHERE amount > 0) = 0) x"
        ).fetchone()[0]
        assert broken == 0

        # 2. The only payer that can pay without having been paid first is the Central Bank.
        #    It pays out for two reasons only: the opening balances, and its loans to banks.
        issued_kinds = {k for (k,) in db.execute(
            "SELECT DISTINCT t.kind FROM ledger_entries e JOIN ledger_transactions t ON t.id = e.transaction_id"
            " JOIN ledger_accounts a ON a.id = e.account_id WHERE a.code = 'central_bank' AND e.asset = 'NGN' AND e.amount < 0"
        ).fetchall()}
        assert issued_kinds <= {"opening_balance", "central_bank_lending"} and "opening_balance" in issued_kinds

        # 3. So the money in existence after eight quarters is exactly the opening money plus
        #    what banks still owe the Central Bank, counted from the loan records.
        assert ledger.amount_in_existence(db) == money_accounted_for(db)

        # 4. And nobody but the Central Bank is below zero.
        assert db.execute(
            "SELECT count(*) FROM ledger_balances b JOIN assets a ON a.code = b.asset"
            " WHERE b.balance < 0 AND b.account_id <> a.issuer_account_id"
        ).fetchone()[0] == 0

    def test_every_transaction_carries_a_reason(self, db):
        assert db.execute("SELECT count(*) FROM ledger_transactions WHERE kind = '' OR memo = ''").fetchone()[0] == 0
        kinds = {k for (k,) in db.execute("SELECT DISTINCT kind FROM ledger_transactions").fetchall()}
        assert kinds == {
            "opening_balance", "share_issue", "customer_revenue", "business_purchase", "cost_of_sales", "wages",
            "debt_interest", "company_tax", "debt_repayment", "capital_spending", "dividend",
            "government_purchase", "government_wages", "pension_payment",
            "loan_interest", "household_loan", "household_loan_repayment", "insurance_claim", "new_loan",
            "central_bank_lending",
        }


# ---------------------------------------------------------------------------
# Item 7 and 9: the three statements, updated every quarter
# ---------------------------------------------------------------------------

@pytest.mark.world("eight")
def test_the_income_statement_adds_up(db):
    for r in _dicts(db, "SELECT * FROM company_results WHERE period >= 1"):
        assert r["operating_profit"] == (r["revenue"] + r["interest_income"] - r["cost_of_sales"] - r["operating_expenses"]
                                         - r["depreciation"] - r["loan_losses"])
        assert r["profit_before_tax"] == r["operating_profit"] - r["interest_expense"]
        assert r["net_profit"] == r["profit_before_tax"] - r["tax"]
        assert r["tax"] >= 0 and r["revenue"] > 0


@pytest.mark.world("eight")
def test_the_cash_flow_statement_is_what_the_ledger_shows(db):
    """Opening cash plus the quarter's flows equals closing cash, and each flow matches ledger movements."""
    for r in _dicts(db, "SELECT r.*, c.account_id, c.name FROM company_results r JOIN companies c ON c.id = r.company_id WHERE r.period >= 1"):
        assert r["cash_closing"] == r["cash_opening"] + r["cash_from_operations"] + r["cash_from_investing"] + r["cash_from_financing"]
        # Closing cash is exactly what the ledger had received less what it had paid, at the close.
        assert r["cash_closing"] == sum(k["received"] - k["paid"] for k in r["ledger_totals"].values()), \
            f"{r['name']} period {r['period']}"

    # The whole ledger, added up from scratch, agrees with the latest balances.
    assert ledger.audit(db) == []

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
    lenders = _dicts(db, "SELECT * FROM companies c WHERE EXISTS (SELECT 1 FROM company_debts d WHERE d.lender_account_id = c.account_id)")
    assert len(lenders) == 6                                 # the six commercial banks that lend to companies
    for bank in lenders:
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
    ledger.transfer(paying, payer=ledger.account_id(paying, "households:lagos"), receiver=company["account_id"],
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
        "SELECT sum(e.amount) FROM ledger_entries e JOIN ledger_transactions t ON t.id = e.transaction_id"
        " WHERE t.kind = 'customer_revenue' AND t.period = 1 AND e.account_id = %s", (company["account_id"],)
    ).fetchone()[0]
    assert q1["sales_households"] == planned + extra
    assert q1["cash"] == sum(k["received"] - k["paid"] for k in q1["ledger_totals"].values())
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
    assert db.execute("SELECT count(*) FROM company_results WHERE period IN (1, 2)").fetchone()[0] == 100
    assert db.execute("SELECT count(*) FROM ledger_transactions WHERE kind = 'government_wages'").fetchone()[0] == 2
    assert db.execute("SELECT count(*) FROM household_results WHERE period IN (1, 2)").fetchone()[0] == 10


@pytest.mark.world("empty")
def test_nothing_closes_before_the_world_exists(db):
    assert quarters.close_due_quarters(db, after_quarters(4)) == []


# ---------------------------------------------------------------------------
# Item 10: the reported record is kept apart from the true record
# ---------------------------------------------------------------------------

@pytest.mark.world("eight")
def test_every_company_files_a_report_every_quarter(db):
    assert db.execute("SELECT count(*), count(DISTINCT (company_id, period)) FROM company_reports").fetchone() == (450, 450)


@pytest.mark.world("eight")
def test_honest_companies_report_exactly_what_happened(db):
    for row in _dicts(db, "SELECT r.*, p.figures FROM company_results r JOIN company_reports p ON p.company_id = r.company_id AND p.period = r.period AND p.version = 1"):
        filed = row["figures"]
        for section, lines in (("income_statement", INCOME_LINES), ("cash_flow", CASH_FLOW_LINES), ("balance_sheet", BALANCE_SHEET_LINES)):
            expected = {line: row[line] for line in lines}
            if section == "income_statement":
                expected["ebitda"] = row["operating_profit"] + row["depreciation"]
            assert filed[section] == expected


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


def test_money_moved_outside_a_companys_normal_business_is_shown_and_never_stops_the_calendar(db):
    """Found by the independent review: one stray payment touching a company used to
    stop every future quarter from closing, for ever. Now it is shown in that
    company's accounts and the calendar carries on."""
    taken_from, given_to = _company(db, "DFL"), _company(db, "IDC")
    treasury = ledger.account_id(db, ledger.TREASURY)
    money_before = ledger.amount_in_existence(db)
    quarters.close_due_quarters(db, after_quarters(1))

    ledger.transfer(db, payer=taken_from["account_id"], receiver=treasury, amount=naira(1_000_000),
                    kind="something_new", memo="Test: money leaves a company for a reason the engine has never seen")
    ledger.transfer(db, payer=treasury, receiver=given_to["account_id"], amount=naira(2_000_000),
                    kind="gift", memo="Test: money reaches a company for a reason the engine has never seen")

    assert quarters.close_due_quarters(db, after_quarters(3)) == [2, 3]          # the calendar carries on

    loser, gainer = (_dicts(db, "SELECT * FROM company_results WHERE company_id = %s AND period = 2", (c["id"],))[0]
                     for c in (taken_from, given_to))
    assert "Money left it outside its normal business this quarter. It is shown as a cost." in loser["drivers"]["notes"]
    assert "It received money outside its normal business this quarter. It is shown as other sales." in gainer["drivers"]["notes"]
    for r in (loser, gainer):
        assert r["total_assets"] == r["total_liabilities"] + r["total_equity"]
        assert r["cash_closing"] == r["cash_opening"] + r["cash_from_operations"] + r["cash_from_investing"] + r["cash_from_financing"]
    # It is counted once: the quarter after carries no such note.
    later = _dicts(db, "SELECT drivers FROM company_results WHERE period = 3 AND company_id IN (%s, %s)",
                   (taken_from["id"], given_to["id"]))
    assert not any("outside its normal business" in note for r in later for note in r["drivers"]["notes"])
    assert ledger.amount_in_existence(db) == money_accounted_for(db) and ledger.audit(db) == []


@pytest.mark.world("eight")
def test_in_a_world_nobody_has_interfered_with_no_company_has_unexplained_money(db):
    """The safety net above must stay empty in normal running: it is not a place to hide mistakes."""
    stray = db.execute("SELECT count(*) FROM company_results WHERE drivers::text LIKE '%outside its normal business%'").fetchone()[0]
    assert stray == 0


def test_sales_paid_between_quarter_closes_are_counted_once_in_the_next_quarter(db):
    """Money a company receives at any time lands in exactly one quarter's accounts."""
    company = _company(db, "ONP")
    quarters.close_due_quarters(db, after_quarters(1))
    extra = naira(5_000_000)
    ledger.transfer(db, payer=ledger.account_id(db, "households:lagos"), receiver=company["account_id"], amount=extra,
                    kind="customer_revenue", memo="A sale made between quarter closes")

    quarters.close_due_quarters(db, after_quarters(3))

    q2, q3 = _dicts(db, "SELECT * FROM company_results WHERE company_id = %s AND period IN (2, 3) ORDER BY period", (company["id"],))
    planned_q2 = db.execute(
        "SELECT sum(e.amount) FROM ledger_entries e JOIN ledger_transactions t ON t.id = e.transaction_id"
        " WHERE t.kind = 'customer_revenue' AND t.period = 2 AND e.account_id = %s", (company["account_id"],)
    ).fetchone()[0]
    assert q2["sales_households"] == planned_q2 + extra            # counted in quarter 2
    assert q3["cash_opening"] == q2["cash_closing"]                # and not again in quarter 3
    for r in (q2, q3):
        assert r["total_assets"] == r["total_liabilities"] + r["total_equity"]


def test_customers_short_of_money_buy_less_and_weak_companies_fall_behind_on_bills(db):
    money_before = ledger.amount_in_existence(db)
    # Households start the world with only a little money: far less than they would normally spend.
    left_each = naira(40_000_000_000)
    for (account,) in db.execute("SELECT account_id FROM households").fetchall():
        ledger.transfer(db, payer=account, receiver=ledger.account_id(db, ledger.TREASURY),
                        amount=ledger.balance(db, account) - left_each, kind="test_drain", memo="Test: households are poor")

    assert quarters.close_due_quarters(db, after_quarters(6)) == [1, 2, 3, 4, 5, 6]

    # Households cannot spend what they do not have, so companies sold far less to them.
    sold = db.execute("SELECT sum(sales_households) FROM company_results WHERE period = 1").fetchone()[0]
    # (All they can spend is the little they have left and what the banks will lend them.)
    borrowed = db.execute("SELECT sum(borrowed) FROM household_results WHERE period = 1").fetchone()[0]
    assert 0 < sold <= 5 * left_each + borrowed + naira(1)
    # Some companies could not pay everything. What they could not pay is owed, not conjured.
    owing = _dicts(db, "SELECT r.*, p.credit_rating FROM company_results r JOIN company_reports p ON p.company_id = r.company_id AND p.period = r.period WHERE r.payables > 0")
    assert owing, "expected at least one company to fall behind"
    for r in owing:
        assert r["total_assets"] == r["total_liabilities"] + r["total_equity"]
        assert r["credit_rating"] in ("CCC", "D")
        assert r["dividends_paid"] == 0            # no dividends while bills are unpaid
    # No money appeared from nowhere, and nobody went below zero.
    assert ledger.amount_in_existence(db) == money_accounted_for(db)
    assert db.execute("SELECT count(*) FROM ledger_balances b JOIN assets a ON a.code = b.asset WHERE b.balance < 0 AND b.account_id <> a.issuer_account_id").fetchone()[0] == 0
    # What is owed in the payables table is what the balance sheets say.
    for r in _dicts(db, "SELECT company_id, payables FROM company_results WHERE period = 6"):
        owed = db.execute("SELECT coalesce(sum(amount_outstanding), 0) FROM company_payables WHERE company_id = %s", (r["company_id"],)).fetchone()[0]
        assert owed == r["payables"]


def test_the_books_hold_together_over_a_long_run(db):
    """Thirty-four quarters: past the end date of every bank loan (24) and every bond (32)."""
    money_before = ledger.amount_in_existence(db)
    assert len(quarters.close_due_quarters(db, after_quarters(34))) == 34

    assert ledger.amount_in_existence(db) == money_accounted_for(db) > money_before
    assert db.execute("SELECT sum(balance) FROM ledger_balances WHERE asset = 'NGN'").fetchone()[0] == 0
    assert db.execute("SELECT count(*) FROM company_results").fetchone()[0] == 50 * 35
    unbalanced = db.execute("SELECT count(*) FROM company_results WHERE total_assets <> total_liabilities + total_equity").fetchone()[0]
    assert unbalanced == 0
    assert ledger.audit(db) == []
    # Every loan and bond now past its end date was either repaid in full or is flagged as overdue.
    # (A sound borrower's debt is renewed, so its end date moves on.)
    for d in _dicts(db, "SELECT d.*, r.principal_overdue FROM company_debts d JOIN company_results r ON r.company_id = d.company_id AND r.period = 34 WHERE d.maturity_period <= 34"):
        assert d["principal_outstanding"] == 0 or d["principal_overdue"] >= d["principal_outstanding"]
    for r in _dicts(db, "SELECT p.credit_rating, r.principal_overdue, r.total_equity FROM company_reports p JOIN company_results r ON r.company_id = p.company_id AND r.period = p.period WHERE p.period = 34"):
        assert (r["credit_rating"] == "D") == (r["principal_overdue"] > 0 or r["total_equity"] <= 0)
    # The economy is still turning over: households are earning and spending, and most companies are still selling.
    first, last = (db.execute("SELECT sum(revenue) FROM company_results WHERE period = %s", (p,)).fetchone()[0] for p in (2, 34))
    assert last > first * 7 // 10
    earning = db.execute("SELECT min(income), min(spending) FROM household_results WHERE period = 34").fetchone()
    assert earning[0] > 0 and earning[1] > 0


# ---------------------------------------------------------------------------
# Good times and bad times (owner, 2 October 2026).
# ---------------------------------------------------------------------------

@pytest.mark.world("eight")
def test_ratings_run_all_the_way_from_aaa_to_d(db):
    ratings = {r for (r,) in db.execute("SELECT DISTINCT credit_rating FROM company_reports WHERE period = 8").fetchall()}
    assert ratings == {"AAA", "AA", "A", "BBB", "BB", "B", "CCC", "D"}


@pytest.mark.world("eight")
def test_some_companies_lose_money_and_most_do_not(db):
    losing = db.execute("SELECT count(DISTINCT company_id) FROM company_results WHERE period >= 1 AND net_profit < 0").fetchone()[0]
    assert 4 <= losing <= 20


@pytest.mark.world("eight")
def test_companies_in_one_sector_no_longer_move_in_step(db):
    """Before, every company in a sector grew by exactly the same percentage."""
    for (sector,) in db.execute("SELECT code FROM sectors").fetchall():
        growth = db.execute(
            "SELECT count(DISTINCT round(a.revenue * 10000.0 / b.revenue)) FROM company_results a"
            " JOIN company_results b ON b.company_id = a.company_id AND b.period = 7"
            " JOIN companies c ON c.id = a.company_id WHERE a.period = 8 AND c.sector = %s", (sector,),
        ).fetchone()[0]
        members = db.execute("SELECT count(*) FROM companies WHERE sector = %s", (sector,)).fetchone()[0]
        assert growth == members, sector


@pytest.mark.world("eight")
def test_a_bad_quarter_says_why(db):
    row = _dicts(db, "SELECT p.figures FROM company_reports p JOIN companies c ON c.id = p.company_id"
                     " WHERE c.ticker = 'OGA' AND p.period >= 1 ORDER BY p.period")
    causes = [cause for r in row for cause in r["figures"]["notes"]["why_revenue"]]
    assert any("customers from its rivals" in cause or "customers to its rivals" in cause for cause in causes)
    assert any("Households spent more on" in cause or "Households spent less on" in cause for cause in causes)
    assert all("of its sales were to" in r["figures"]["notes"]["why_revenue"][0] for r in row)


def test_fortune_is_fixed_by_the_worlds_secret_and_stays_within_its_limits():
    from simulation.companies import fortune_bps
    draws = [fortune_bps("seed", "IDC", period, "sales", 500) for period in range(1, 400)]
    assert all(-500 <= d <= 500 for d in draws)
    assert min(draws) < -200 and max(draws) > 200                    # real swings both ways
    assert abs(sum(draws)) < 500 * 20                                # and no built-in lean either way
    assert draws == [fortune_bps("seed", "IDC", period, "sales", 500) for period in range(1, 400)]   # repeatable
    assert draws != [fortune_bps("other", "IDC", period, "sales", 500) for period in range(1, 400)]  # a different world differs
    assert fortune_bps("seed", "IDC", 1, "sales", 0) == 0


@pytest.mark.world("eight")
def test_the_worlds_secret_and_each_companys_steadiness_are_never_sent_to_players(client, player):
    for path in ("/api/companies", "/api/companies/OGA", "/api/world/status", "/api/world/clock"):
        text = client.get(path).text
        assert "a-fixed-secret" not in text and "fortune_seed" not in text and "volatility" not in text
