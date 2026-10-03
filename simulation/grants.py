"""The starting grant, paid in parts (design document, section 10).

A new player receives ₦100,000 on joining. The other ₦400,000 comes in four
parts of ₦100,000, each for a real thing the player has done:

  first_trade            traded on the exchange with somebody else
  held_through_results   held a share when a quarter closed and results were filed
  lent_to_government     held a Government bill or bond when a quarter closed
  took_part              voted at a company meeting, applied for new shares, or
                         answered a takeover offer

At most one part is paid in any twenty real hours, so the whole grant takes
several days of play to collect. This is what makes opening many accounts to
harvest grants slow and laborious instead of instant. The money comes from the
Treasury, as the first part does, so it is not new money; and the database
itself allows each part to be paid once to each account.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from psycopg import Connection
from psycopg.rows import dict_row

from simulation import ledger
from simulation import world_data as data
from simulation.money import naira

STEPS = {
    "first_trade": "Make your first trade on the exchange with another investor.",
    "held_through_results": "Hold a share when a quarter closes and companies file their results.",
    "lent_to_government": "Hold a Government bill or bond when a quarter closes.",
    "took_part": "Vote at a company meeting, apply for new shares, or answer a takeover offer.",
}


def _rows(conn: Connection, sql: str, params=()) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def _earn(conn: Connection, player_id, step: str, now: datetime) -> None:
    conn.execute("INSERT INTO grant_steps (player_id, step, earned_at) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING", (player_id, step, now))


def mark_holders(conn: Connection, now: datetime) -> None:
    """As a quarter closes: note which players hold a share, and which a Government bill or bond."""
    conn.execute(
        "INSERT INTO grant_steps (player_id, step, earned_at)"
        " SELECT DISTINCT a.player_id, 'held_through_results', %s FROM share_owners o JOIN ledger_accounts a ON a.id = o.account_id"
        "  WHERE a.kind = 'player' ON CONFLICT DO NOTHING", (now,))
    conn.execute(
        "INSERT INTO grant_steps (player_id, step, earned_at)"
        " SELECT DISTINCT a.player_id, 'lent_to_government', %s FROM ledger_entries e"
        "   JOIN ledger_transactions t ON t.id = e.transaction_id JOIN ledger_accounts a ON a.id = e.account_id"
        "  WHERE a.kind = 'player' AND e.asset = 'NGN' AND e.amount > 0 AND t.kind IN ('bond_coupon', 'bond_redemption')"
        " ON CONFLICT DO NOTHING", (now,))


def review(conn: Connection, player_id, now: datetime) -> dict:
    """Note anything newly earned, pay the next part if one is due, and say where the player stands."""
    with conn.transaction():
        # One player's reviews take turns, so that two at the same moment cannot both pay.
        conn.execute("SELECT 1 FROM players WHERE id = %s FOR UPDATE", (player_id,))
        account = ledger.player_account_id(conn, player_id)
        if account is None:
            return {"received": 0, "total": naira(data.STARTING_GRANT_NAIRA), "steps": [], "next_payment_at": None}
        if _rows(conn, "SELECT 1 FROM market_trades WHERE (buyer_account_id = %s OR seller_account_id = %s) AND NOT same_owner LIMIT 1",
                 (account, account)):
            _earn(conn, player_id, "first_trade", now)
        # (A vote can only be cast by somebody holding the company's shares; an acceptance only with shares put up.)
        if _rows(conn, "SELECT 1 FROM vote_ballots WHERE account_id = %s UNION ALL SELECT 1 FROM offer_subscriptions WHERE account_id = %s"
                       " AND (shares > 0 OR allotted > 0) UNION ALL SELECT 1 FROM takeover_tenders WHERE account_id = %s AND shares > 0"
                       " UNION ALL SELECT 1 FROM holding_events WHERE account_id = %s AND kind = 'takeover' LIMIT 1",
                 (account, account, account, account)):
            _earn(conn, player_id, "took_part", now)

        steps = {r["step"]: r for r in _rows(conn, "SELECT * FROM grant_steps WHERE player_id = %s", (player_id,))}
        last = _rows(conn, "SELECT max(t.created_at) AS at FROM ledger_entries e JOIN ledger_transactions t ON t.id = e.transaction_id"
                           " WHERE e.account_id = %s AND e.amount > 0 AND t.kind = 'starting_grant'", (account,))[0]["at"]
        last = max([moment for moment in [last, *(s["paid_at"] for s in steps.values())] if moment is not None], default=None)
        due_from = last + timedelta(hours=data.GRANT_STEP_GAP_HOURS) if last else now
        waiting = sorted((s for s in steps.values() if s["paid_at"] is None), key=lambda s: (s["earned_at"], s["step"]))
        if waiting and now >= due_from:
            step = waiting[0]
            try:
                paid = ledger.transfer(
                    conn, payer=ledger.account_id(conn, ledger.TREASURY), receiver=account, amount=naira(data.GRANT_STEP_NAIRA),
                    kind="grant_step", memo="Starting grant: a further part, for " + STEPS[step["step"]][0].lower() + STEPS[step["step"]][1:-1],
                    reference=f"{account}:{step['step']}", idempotency_key=f"grant_step:{player_id}:{step['step']}")
            except ledger.InsufficientFunds:
                paid = None                                    # the Treasury is short; it is tried again next time
            if paid:
                conn.execute("UPDATE grant_steps SET paid_at = %s WHERE player_id = %s AND step = %s", (now, player_id, step["step"]))
                step["paid_at"] = now
                due_from = now + timedelta(hours=data.GRANT_STEP_GAP_HOURS)
        paid_count = sum(1 for s in steps.values() if s["paid_at"] is not None)
        still_waiting = any(s["paid_at"] is None for s in steps.values())
        return {
            "received": naira(data.GRANT_ON_JOINING_NAIRA) + paid_count * naira(data.GRANT_STEP_NAIRA),
            "total": naira(data.STARTING_GRANT_NAIRA),
            "steps": [{"step": code, "what": words, "earned": code in steps, "paid": code in steps and steps[code]["paid_at"] is not None}
                      for code, words in STEPS.items()],
            "next_payment_at": due_from if still_waiting and now < due_from else None,
        }
