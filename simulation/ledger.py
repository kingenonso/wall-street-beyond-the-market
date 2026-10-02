"""The ledger: the permanent record of everything of value that moves.

This file is the ONLY way the rest of the game moves money or shares. It owns
"player cash and wealth" and "who owns which shares" (design document,
section 19, "one owner per value").

The rules themselves are enforced inside the database (see
database/migrations/002_ledger.sql). This file adds a safe, convenient way to
use them, and checks the obvious mistakes early so the error is clear.

Words used here:
  account      something that can hold money or shares: a player, a company,
               the Treasury...
  asset        what is held: "NGN" (naira, counted in kobo) or a company's shares
  transaction  one event, e.g. "Ikenga Bank pays tax"
  leg          one side of a transaction: an account and an amount. A negative
               amount pays out, a positive amount receives. The legs of a
               transaction always add up to zero.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from psycopg import Connection
from psycopg.errors import CheckViolation

from simulation.money import MAX_AMOUNT, is_whole_amount

NGN = "NGN"

# Fixed handles for the accounts the game itself looks up.
CENTRAL_BANK = "central_bank"
TREASURY = "treasury"
PRIZE_POOL = "prize_pool"
PUBLIC = "public"
INVESTORS_FOUNDERS = "investors:founders"
INVESTORS_INSTITUTIONS = "investors:institutions"
INVESTORS_PUBLIC = "investors:public"


class LedgerError(Exception):
    """The ledger refused something."""


class InsufficientFunds(LedgerError):
    """The payer does not have enough to make the payment."""


@dataclass(frozen=True)
class Leg:
    account_id: UUID | str
    amount: int
    asset: str = NGN


def create_account(
    conn: Connection,
    *,
    kind: str,
    name: str,
    code: str | None = None,
    player_id: UUID | str | None = None,
) -> UUID:
    row = conn.execute(
        "INSERT INTO ledger_accounts (kind, name, code, player_id) VALUES (%s, %s, %s, %s) RETURNING id",
        (kind, name, code, player_id),
    ).fetchone()
    return _first(row)


def create_asset(conn: Connection, *, code: str, kind: str, name: str, unit: str, issuer_account_id) -> None:
    conn.execute(
        "INSERT INTO assets (code, kind, name, unit, issuer_account_id) VALUES (%s, %s, %s, %s, %s)",
        (code, kind, name, unit, issuer_account_id),
    )


def account_id(conn: Connection, code: str) -> UUID:
    row = conn.execute("SELECT id FROM ledger_accounts WHERE code = %s", (code,)).fetchone()
    if row is None:
        raise LedgerError(f"There is no account with the code {code!r}. Has the world been created?")
    return _first(row)


def player_account_id(conn: Connection, player_id: UUID | str) -> UUID | None:
    row = conn.execute("SELECT id FROM ledger_accounts WHERE player_id = %s", (player_id,)).fetchone()
    return _first(row) if row else None


def balance(conn: Connection, account: UUID | str, asset: str = NGN) -> int:
    row = conn.execute(
        "SELECT balance FROM ledger_balances WHERE account_id = %s AND asset = %s", (account, asset)
    ).fetchone()
    return _first(row) if row else 0


def amount_in_existence(conn: Connection, asset: str = NGN) -> int:
    """How much of an asset exists. It is exactly what its issuer has put out."""
    row = conn.execute(
        "SELECT coalesce(-b.balance, 0) FROM assets a"
        " LEFT JOIN ledger_balances b ON b.account_id = a.issuer_account_id AND b.asset = a.code"
        " WHERE a.code = %s",
        (asset,),
    ).fetchone()
    if row is None:
        raise LedgerError(f"Unknown asset {asset!r}.")
    return _first(row)


def post(
    conn: Connection,
    *,
    kind: str,
    memo: str,
    legs: Sequence[Leg],
    period: int | None = None,
    reference: str | None = None,
    idempotency_key: str | None = None,
) -> UUID | None:
    """Record one transaction.

    Returns the new transaction's id. If `idempotency_key` was already used, nothing
    is recorded and None is returned: the thing has already happened once.

    Everything is checked before anything is written, and the write is all-or-nothing.
    """
    _check_legs(legs)

    # A savepoint: if the database refuses any part, this transaction leaves no trace,
    # but work the caller did earlier is kept.
    try:
        with conn.transaction():
            row = conn.execute(
                "INSERT INTO ledger_transactions (kind, memo, reference, period, idempotency_key)"
                " VALUES (%s, %s, %s, %s, %s)"
                " ON CONFLICT (idempotency_key) DO NOTHING RETURNING id",
                (kind, memo, reference, period, idempotency_key),
            ).fetchone()
            if row is None:
                return None
            transaction_id = _first(row)

            # Always touch accounts in the same order, receipts before payments, so two
            # transactions running at the same moment cannot block each other forever.
            ordered = sorted(legs, key=lambda leg: (str(leg.account_id), leg.asset, -leg.amount))
            values_sql = ", ".join(["(%s, %s, %s, %s)"] * len(ordered))
            params: list = []
            for leg in ordered:
                params += [transaction_id, leg.account_id, leg.asset, leg.amount]
            conn.execute(
                f"INSERT INTO ledger_entries (transaction_id, account_id, asset, amount) VALUES {values_sql}",
                params,
            )
            return transaction_id
    except CheckViolation as error:
        if error.diag.constraint_name == "ledger_insufficient_balance":
            raise InsufficientFunds(str(error.diag.message_primary)) from error
        raise


def transfer(
    conn: Connection,
    *,
    payer: UUID | str,
    receiver: UUID | str,
    amount: int,
    kind: str,
    memo: str,
    asset: str = NGN,
    period: int | None = None,
    reference: str | None = None,
    idempotency_key: str | None = None,
) -> UUID | None:
    """Move `amount` from one account to another. The amount must be a positive whole number."""
    if not is_whole_amount(amount) or amount <= 0:
        raise LedgerError("A transfer must be a positive whole amount.")
    if str(payer) == str(receiver):
        raise LedgerError("The payer and the receiver must be different accounts.")
    return post(
        conn,
        kind=kind,
        memo=memo,
        legs=[Leg(payer, -amount, asset), Leg(receiver, amount, asset)],
        period=period,
        reference=reference,
        idempotency_key=idempotency_key,
    )


def pay_up_to(
    conn: Connection,
    *,
    payer: UUID | str,
    receiver: UUID | str,
    wanted: int,
    kind: str,
    memo: str,
    asset: str = NGN,
    period: int | None = None,
    reference: str | None = None,
) -> int:
    """Pay `wanted`, or as much of it as the payer actually has. Returns the amount paid."""
    if not is_whole_amount(wanted) or wanted < 0:
        raise LedgerError("The amount wanted must be a whole number, zero or more.")
    if wanted == 0:
        return 0
    # Lock the payer's balance so nobody else can spend it between the look and the payment.
    row = conn.execute(
        "SELECT balance FROM ledger_balances WHERE account_id = %s AND asset = %s FOR UPDATE",
        (payer, asset),
    ).fetchone()
    available = max(_first(row), 0) if row else 0
    amount = min(wanted, available)
    if amount > 0:
        transfer(
            conn, payer=payer, receiver=receiver, amount=amount, kind=kind, memo=memo,
            asset=asset, period=period, reference=reference,
        )
    return amount


def _check_legs(legs: Sequence[Leg]) -> None:
    if len(legs) < 2:
        raise LedgerError("A transaction needs at least a payer and a receiver.")
    totals: dict[str, int] = defaultdict(int)
    for leg in legs:
        if not is_whole_amount(leg.amount):
            raise LedgerError("Amounts must be whole numbers.")
        if leg.amount == 0:
            raise LedgerError("An amount of zero moves nothing.")
        if abs(leg.amount) > MAX_AMOUNT:
            raise LedgerError("That amount is too large to record.")
        totals[leg.asset] += leg.amount
    unbalanced = [asset for asset, total in totals.items() if total != 0]
    if unbalanced:
        raise LedgerError(
            "A transaction must add up to zero: every amount paid must be received by someone."
        )


def _first(row):
    """The first column of a row, whether rows come back as tuples or as dictionaries."""
    if isinstance(row, dict):
        return next(iter(row.values()))
    return row[0]
