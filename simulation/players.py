"""A player's place in the economy: their ledger account and their starting cash."""

from __future__ import annotations

from uuid import UUID

from psycopg import Connection

from simulation import ledger
from simulation import world_data as data
from simulation.money import naira


def open_player_account(conn: Connection, player_id: UUID | str) -> None:
    """Give a player their ledger account and their starting cash.

    The starting grant is paid in parts: the first on joining, the rest as the player does
    real things in the game (see simulation/grants.py). The cash is paid by the Federal Government Treasury, so it is not
    new money, and the payment has a named payer (design document, section 10).
    It can only ever be paid once per player.

    Raises ledger.LedgerError if the world has not been created yet, and
    ledger.InsufficientFunds if the Treasury cannot pay.
    """
    player_id = UUID(str(player_id))        # one spelling of the id, whoever is calling
    treasury = ledger.account_id(conn, ledger.TREASURY)
    account = ledger.player_account_id(conn, player_id)
    if account is None:
        account = ledger.create_account(conn, kind="player", name="Player account", player_id=player_id)
    ledger.transfer(
        conn,
        payer=treasury,
        receiver=account,
        amount=naira(data.GRANT_ON_JOINING_NAIRA),
        kind="starting_grant",
        memo="Starting grant to a new professional: the first part",
        reference=str(account),             # the database allows one grant per account
        idempotency_key=f"starting_grant:{player_id}",
    )
