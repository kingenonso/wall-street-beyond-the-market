"""The ledger: the permanent record of every naira and every share.

Stage 2 checklist items 1 to 4. Many of these tests go around the game's code
and talk to the database directly, to prove the rules hold even against a
programming mistake.
"""

from __future__ import annotations

import threading

import pytest
from psycopg import errors

from simulation import ledger
from simulation.ledger import NGN, InsufficientFunds, LedgerError, Leg
from simulation.money import naira


@pytest.fixture
def accounts(db):
    """Two ordinary accounts, each holding ₦1,000 paid by the Treasury."""
    treasury = ledger.account_id(db, ledger.TREASURY)
    a = ledger.create_account(db, kind="npc_public", name="Test account A")
    b = ledger.create_account(db, kind="npc_public", name="Test account B")
    for account in (a, b):
        ledger.transfer(db, payer=treasury, receiver=account, amount=naira(1_000), kind="test", memo="Test funding")
    return a, b


def _counts(db):
    return db.execute(
        "SELECT (SELECT count(*) FROM ledger_transactions), (SELECT count(*) FROM ledger_entries)"
    ).fetchone()


# --- Item 1: every movement has a payer, a receiver, an amount and a reason ---

def test_a_transfer_records_payer_receiver_amount_and_reason(db, accounts):
    a, b = accounts
    tx = ledger.transfer(db, payer=a, receiver=b, amount=naira(250), kind="test_payment", memo="A pays B for a service")

    assert ledger.balance(db, a) == naira(750)
    assert ledger.balance(db, b) == naira(1_250)
    kind, memo = db.execute("SELECT kind, memo FROM ledger_transactions WHERE id = %s", (tx,)).fetchone()
    assert (kind, memo) == ("test_payment", "A pays B for a service")
    entries = db.execute(
        "SELECT account_id, amount, asset FROM ledger_entries WHERE transaction_id = %s ORDER BY amount", (tx,)
    ).fetchall()
    assert entries == [(a, -naira(250), NGN), (b, naira(250), NGN)]     # payer out, receiver in


def test_every_transaction_in_the_ledger_adds_up_to_zero(db):
    unbalanced = db.execute(
        "SELECT transaction_id FROM ledger_entries GROUP BY transaction_id, asset HAVING sum(amount) <> 0"
    ).fetchall()
    assert unbalanced == []


def test_a_reason_is_required(db, accounts):
    a, b = accounts
    with pytest.raises(errors.CheckViolation):
        ledger.transfer(db, payer=a, receiver=b, amount=1, kind="test", memo="")


def test_the_game_code_refuses_a_transaction_that_does_not_add_up(db, accounts):
    a, b = accounts
    with pytest.raises(LedgerError):
        ledger.post(db, kind="test", memo="Money from nowhere", legs=[Leg(a, -100), Leg(b, 150)])
    with pytest.raises(LedgerError):
        ledger.post(db, kind="test", memo="One-sided", legs=[Leg(b, 150)])


def test_the_database_itself_refuses_money_from_nowhere(db, accounts):
    """Even code that skips the ledger module cannot create money."""
    a, _ = accounts
    before = _counts(db)
    with pytest.raises(errors.IntegrityError) as refused:
        with db.transaction():
            tx = db.execute(
                "INSERT INTO ledger_transactions (kind, memo) VALUES ('cheat', 'Free money') RETURNING id"
            ).fetchone()[0]
            db.execute("INSERT INTO ledger_entries (transaction_id, account_id, asset, amount) VALUES (%s, %s, 'NGN', 5000000)", (tx, a))
    assert refused.value.diag.constraint_name == "ledger_transaction_balanced"
    assert _counts(db) == before
    assert ledger.balance(db, a) == naira(1_000)


def test_the_database_refuses_a_transaction_with_no_entries(db):
    with pytest.raises(errors.IntegrityError):
        db.execute("INSERT INTO ledger_transactions (kind, memo) VALUES ('empty', 'Nothing moved')")


# --- Item 2: entries can be added, never edited or deleted ---

@pytest.mark.parametrize("statement", [
    "UPDATE ledger_entries SET amount = amount * 2",
    "DELETE FROM ledger_entries",
    "TRUNCATE ledger_entries",
    "UPDATE ledger_transactions SET memo = 'rewritten'",
    "DELETE FROM ledger_transactions",
    "TRUNCATE ledger_transactions CASCADE",
    "UPDATE ledger_accounts SET name = 'renamed'",
    "DELETE FROM ledger_accounts",
    "UPDATE assets SET issuer_account_id = (SELECT id FROM ledger_accounts WHERE code = 'households:lagos')",
    "DELETE FROM assets",
])
def test_ledger_records_cannot_be_edited_or_deleted(db, statement):
    before = _counts(db)
    with pytest.raises(errors.RestrictViolation):
        db.execute(statement)
    assert _counts(db) == before


@pytest.mark.parametrize("statement", [
    "UPDATE ledger_balances SET balance = balance + 100000000",
    "INSERT INTO ledger_balances (account_id, asset, balance) SELECT id, 'SHR-IKB', 1000 FROM ledger_accounts WHERE code = 'households:lagos'",
    "DELETE FROM ledger_balances",
    "TRUNCATE ledger_balances",
])
def test_balances_cannot_be_written_directly(db, statement):
    with pytest.raises(errors.RestrictViolation):
        db.execute(statement)


def test_nothing_can_be_added_to_a_finished_transaction(db, accounts):
    a, b = accounts
    tx = ledger.transfer(db, payer=a, receiver=b, amount=100, kind="test", memo="Finished")
    with pytest.raises(errors.RestrictViolation) as refused:
        with db.transaction():
            db.execute(
                "INSERT INTO ledger_entries (transaction_id, account_id, asset, amount) VALUES (%s, %s, 'NGN', 500), (%s, %s, 'NGN', -500)",
                (tx, a, tx, b),
            )
    assert refused.value.diag.constraint_name == "ledger_transaction_closed"


def test_the_database_stamps_the_time_itself(db, accounts):
    a, b = accounts
    with db.transaction():
        tx = db.execute(
            "INSERT INTO ledger_transactions (kind, memo, created_at, created_txid)"
            " VALUES ('test', 'Backdated', '2001-01-01', 1) RETURNING id"
        ).fetchone()[0]
        db.execute(
            "INSERT INTO ledger_entries (transaction_id, account_id, asset, amount) VALUES (%s, %s, 'NGN', -5), (%s, %s, 'NGN', 5)",
            (tx, a, tx, b),
        )
    created_at = db.execute("SELECT created_at FROM ledger_transactions WHERE id = %s", (tx,)).fetchone()[0]
    assert created_at.year >= 2026


# --- Item 3: whole kobo, with the currency ---

def test_money_is_stored_as_whole_kobo_with_its_currency(db):
    column = db.execute(
        "SELECT data_type FROM information_schema.columns WHERE table_name = 'ledger_entries' AND column_name = 'amount'"
    ).fetchone()[0]
    assert column == "bigint"                      # a whole-number column: fractions cannot be stored
    assert db.execute("SELECT kind, unit FROM assets WHERE code = 'NGN'").fetchone() == ("currency", "kobo")
    assert db.execute("SELECT count(*) FROM ledger_entries WHERE asset IS NULL").fetchone()[0] == 0


@pytest.mark.parametrize("bad", [0, -500, 10.5, "100", None, True, 2**63])
def test_bad_amounts_are_refused(db, accounts, bad):
    a, b = accounts
    before = _counts(db)
    with pytest.raises((LedgerError, errors.NumericValueOutOfRange)):
        ledger.transfer(db, payer=a, receiver=b, amount=bad, kind="test", memo="Bad amount")
    assert _counts(db) == before
    assert ledger.balance(db, a) == naira(1_000)


def test_the_database_refuses_a_zero_entry(db, accounts):
    a, b = accounts
    with pytest.raises(errors.CheckViolation):
        with db.transaction():
            tx = db.execute("INSERT INTO ledger_transactions (kind, memo) VALUES ('test', 'Zero') RETURNING id").fetchone()[0]
            db.execute("INSERT INTO ledger_entries (transaction_id, account_id, asset, amount) VALUES (%s, %s, 'NGN', 0)", (tx, a))


def test_paying_yourself_is_refused(db, accounts):
    a, _ = accounts
    with pytest.raises(LedgerError):
        ledger.transfer(db, payer=a, receiver=a, amount=100, kind="test", memo="To myself")


# --- Nobody can spend what they do not have ---

def test_nobody_can_spend_more_than_they_have(db, accounts):
    a, b = accounts
    before = _counts(db)
    with pytest.raises(InsufficientFunds):
        ledger.transfer(db, payer=a, receiver=b, amount=naira(1_000) + 1, kind="test", memo="One kobo too many")
    assert _counts(db) == before
    assert (ledger.balance(db, a), ledger.balance(db, b)) == (naira(1_000), naira(1_000))


def test_the_database_itself_refuses_an_overdraft(db, accounts):
    a, b = accounts
    with pytest.raises(errors.CheckViolation) as refused:
        with db.transaction():
            tx = db.execute("INSERT INTO ledger_transactions (kind, memo) VALUES ('cheat', 'Overdraft') RETURNING id").fetchone()[0]
            db.execute(
                "INSERT INTO ledger_entries (transaction_id, account_id, asset, amount) VALUES (%s, %s, 'NGN', -999999999999), (%s, %s, 'NGN', 999999999999)",
                (tx, a, tx, b),
            )
    assert refused.value.diag.constraint_name == "ledger_insufficient_balance"
    assert ledger.balance(db, b) == naira(1_000)


def test_only_the_central_bank_can_issue_naira(db):
    """The Central Bank's negative balance IS the money in existence. Nobody else may go below zero."""
    negative = db.execute(
        "SELECT a.code FROM ledger_balances b JOIN ledger_accounts a ON a.id = b.account_id"
        " WHERE b.asset = 'NGN' AND b.balance < 0"
    ).fetchall()
    assert negative == [(ledger.CENTRAL_BANK,)]


def test_two_payments_at_the_same_instant_cannot_both_spend_the_same_money(db, accounts, connect):
    """Loophole question 4 (timing): a balance cannot be spent twice by racing."""
    a, b = accounts
    barrier = threading.Barrier(2)
    outcomes: list[str] = []

    def spend_everything():
        conn = connect()
        barrier.wait()
        try:
            ledger.transfer(conn, payer=a, receiver=b, amount=naira(1_000), kind="test", memo="Race")
            outcomes.append("paid")
        except InsufficientFunds:
            outcomes.append("refused")

    threads = [threading.Thread(target=spend_everything) for _ in range(2)]
    [t.start() for t in threads]
    [t.join() for t in threads]

    assert sorted(outcomes) == ["paid", "refused"]
    assert (ledger.balance(db, a), ledger.balance(db, b)) == (0, naira(2_000))


def test_pay_up_to_pays_only_what_the_payer_has(db, accounts):
    a, b = accounts
    with db.transaction():
        paid = ledger.pay_up_to(db, payer=a, receiver=b, wanted=naira(5_000), kind="test", memo="As much as possible")
    assert paid == naira(1_000)
    assert ledger.balance(db, a) == 0
    with db.transaction():
        assert ledger.pay_up_to(db, payer=a, receiver=b, wanted=naira(5), kind="test", memo="Nothing left") == 0


# --- A thing that must happen once happens once ---

def test_a_keyed_payment_happens_only_once(db, accounts):
    """Loophole question 3 (farming): a one-time reward cannot be collected again."""
    a, b = accounts
    first = ledger.transfer(db, payer=a, receiver=b, amount=100, kind="reward", memo="One-time reward", idempotency_key="reward:1")
    again = ledger.transfer(db, payer=a, receiver=b, amount=100, kind="reward", memo="One-time reward", idempotency_key="reward:1")
    assert first is not None and again is None
    assert ledger.balance(db, b) == naira(1_000) + 100


def test_a_keyed_payment_claimed_twice_at_the_same_instant_pays_once(db, accounts, connect):
    a, b = accounts
    barrier = threading.Barrier(4)
    results = []

    def claim():
        conn = connect()
        barrier.wait()
        results.append(ledger.transfer(conn, payer=a, receiver=b, amount=100, kind="reward", memo="Race for a reward", idempotency_key="reward:race"))

    threads = [threading.Thread(target=claim) for _ in range(4)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert sum(r is not None for r in results) == 1
    assert ledger.balance(db, b) == naira(1_000) + 100


def test_a_refused_payment_does_not_undo_earlier_work(db, accounts):
    a, b = accounts
    with db.transaction():
        ledger.transfer(db, payer=a, receiver=b, amount=100, kind="test", memo="Good")
        with pytest.raises(InsufficientFunds):
            ledger.transfer(db, payer=a, receiver=b, amount=naira(10_000), kind="test", memo="Too much")
        ledger.transfer(db, payer=a, receiver=b, amount=50, kind="test", memo="Also good")
    assert ledger.balance(db, b) == naira(1_000) + 150


# --- The whole ledger adds up ---

@pytest.mark.world("eight")
def test_balances_always_agree_with_the_entries(db):
    """The running balances are a convenience. They must equal the sum of the permanent entries."""
    mismatched = db.execute(
        "SELECT count(*) FROM ("
        "  SELECT account_id, asset, sum(amount) AS total FROM ledger_entries GROUP BY account_id, asset"
        ") e FULL JOIN ledger_balances b USING (account_id, asset) WHERE e.total IS DISTINCT FROM b.balance"
    ).fetchone()[0]
    assert mismatched == 0


@pytest.mark.world("eight")
def test_everything_in_the_ledger_sums_to_zero(db):
    totals = db.execute("SELECT asset, sum(balance) FROM ledger_balances GROUP BY asset").fetchall()
    companies = db.execute("SELECT count(*) FROM companies").fetchone()[0]                # 70 listed, 45 private, and start-ups
    # (Since the gap stage, preferred shares and warrants are assets of their own too.)
    assert len([asset for asset, _ in totals if not asset.startswith(("BND-", "PRF-", "WRT-", "DEP-"))]) == 1 + companies >= 81      # naira and a share class each
    # (Since the crises stage, each bank's savings are an asset of their own too.)
    assert any(asset.startswith("BND-") for asset, _ in totals)                            # ...and, since Stage 4, the bonds
    assert all(total == 0 for _, total in totals)


# --- Shares live in the same ledger, under the same rules ---

def test_shares_cannot_be_created_from_nothing(db):
    public = ledger.account_id(db, "households:lagos")
    small = ledger.account_id(db, ledger.INVESTORS_PUBLIC)
    assert ledger.balance(db, public, "SHR-IKB") == 0
    with pytest.raises(InsufficientFunds):
        ledger.transfer(db, payer=public, receiver=small, amount=1_000, asset="SHR-IKB", kind="test", memo="Selling shares it does not own")


def test_money_and_shares_cannot_be_mixed_to_fake_a_balance(db, accounts):
    a, b = accounts
    with pytest.raises(LedgerError):
        ledger.post(db, kind="test", memo="Kobo out, shares in", legs=[Leg(a, -100, NGN), Leg(b, 100, "SHR-IKB")])
