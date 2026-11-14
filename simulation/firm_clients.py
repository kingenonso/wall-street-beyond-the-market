"""Work for outside clients, done from the empire's desk: the bookkeeper on retainer.

A player hires an Accountant to look at their money for the quarter just closed. The Accountant
works it out from the client's own record of payments (which only the server reads) and sends a
plain report; the client pays the fee on delivery and may rate the work.

When the Accountant holds a seat in an empire, the fee is the firm's: 60% goes to the empire and
40% to the Accountant. An Accountant without a seat keeps it all. (Owner's decision, 3 October 2026.)

Nothing here makes money: the fee moves from the client to the empire and the Accountant.
"""

from __future__ import annotations

from datetime import datetime

from psycopg import Connection, errors

from simulation import careers, empires, firm, ledger
from simulation.empires import EmpireError, _log, _money, _one, _open, _rows, _text
from simulation.money import apply_bps, naira

EMPIRE_SHARE_BPS = 6000             # of a fee earned from a seat in an empire, the empire's share
FEE_LEAST_NAIRA = 50_000
FEE_MOST_NAIRA = 5_000_000
KIND_NAMES = {"salary": "Pay", "professional_fee": "Fees for work", "empire_bonus": "Bonuses", "trade": "Shares bought and sold",
              "dividend": "Dividends", "bond_coupon": "Interest on bonds", "grant_step": "The starting grant", "fee": "Fees",
              "empire_capital": "Money put into an empire", "rank_case_fee": "Rank case fees"}


def hire(conn: Connection, client_id, adviser_key: str, fee: int, now: datetime) -> dict:
    """A player hires an Accountant for the quarter, named by the key shown in the list. The fee is paid when the report is delivered."""
    with conn.transaction():
        state = _open(conn, now)
        adviser = adviser_by_key(conn, adviser_key, state["period"])
        if adviser == client_id:
            raise EmpireError("You cannot be your own bookkeeper.")
        player = _one(conn, "SELECT id, build, display_name FROM players WHERE id = %s", (adviser,))
        if player is None or player["build"] != "asset_manager":
            raise EmpireError("A bookkeeper is an Accountant.")
        if not firm._whole(fee, naira(FEE_LEAST_NAIRA), naira(FEE_MOST_NAIRA)):
            raise EmpireError(f"A fee from {_money(naira(FEE_LEAST_NAIRA))} to {_money(naira(FEE_MOST_NAIRA))}.")
        if ledger.balance(conn, ledger.player_account_id(conn, client_id)) < fee:
            raise EmpireError("You do not have the cash for that fee.")
        seat = empires.seat_of(conn, adviser)
        empire_id = seat["empire_id"] if seat and seat["empire_status"] == "active" and seat["empire_kind"] == "player" else None
        try:
            with conn.transaction():
                row = _one(conn, "INSERT INTO client_engagements (client_id, adviser_id, empire_id, fee, period, at) VALUES (%s, %s, %s, %s, %s, %s)"
                                 " RETURNING *", (client_id, adviser, empire_id, fee, state["period"], now))
        except errors.UniqueViolation:
            raise EmpireError("You have already hired a bookkeeper this quarter.") from None
        return {"id": row["id"]}


def cancel(conn: Connection, client_id, engagement_id: int, now: datetime) -> None:
    with conn.transaction():
        _open(conn, now)
        if not conn.execute("UPDATE client_engagements SET status = 'cancelled' WHERE id = %s AND client_id = %s AND status = 'open' AND report IS NULL",
                            (engagement_id, client_id)).rowcount:
            raise EmpireError("There is no open engagement of yours to cancel.")


def _movements(conn: Connection, account, period: int) -> dict:
    rows = _rows(conn, "SELECT t.kind, sum(e.amount) FILTER (WHERE e.amount > 0)::bigint AS came_in, -sum(e.amount) FILTER (WHERE e.amount < 0)::bigint AS went_out"
                       " FROM ledger_entries e JOIN ledger_transactions t ON t.id = e.transaction_id WHERE e.account_id = %s AND e.asset = 'NGN'"
                       " AND t.period = %s GROUP BY t.kind ORDER BY t.kind", (account, period))
    return {r["kind"]: {"in": r["came_in"] or 0, "out": r["went_out"] or 0} for r in rows}


def open_work(conn: Connection, adviser_id, engagement_id: int, now: datetime) -> dict:
    """The Accountant opens the client's figures for the quarter just closed. What is shown is fixed from this moment."""
    with conn.transaction():
        state = _open(conn, now)
        row = _one(conn, "SELECT * FROM client_engagements WHERE id = %s AND adviser_id = %s FOR UPDATE", (engagement_id, adviser_id))
        if row is None or row["status"] != "open":
            raise EmpireError("There is no open engagement of yours.")
        if row["report"] is None:
            moves = _movements(conn, ledger.player_account_id(conn, row["client_id"]), state["period"] - 1)
            if not moves:
                raise EmpireError("The client had no payments last quarter: there is nothing to report on.")
            came, went = sum(m["in"] for m in moves.values()), sum(m["out"] for m in moves.values())
            outs = {k: m["out"] for k, m in moves.items() if m["out"]}
            biggest = KIND_NAMES.get(max(outs, key=outs.get), max(outs, key=outs.get)) if outs else "Nothing went out"
            report = {"given": [{"label": KIND_NAMES.get(k, k.replace("_", " ").capitalize()), "in": str(m["in"]), "out": str(m["out"])} for k, m in moves.items()],
                      "choices": sorted({KIND_NAMES.get(k, k.replace("_", " ").capitalize()) for k in outs} | {"Nothing went out"}),
                      "_truth": {"net": came - went, "biggest": biggest}}
            conn.execute("UPDATE client_engagements SET report = %s WHERE id = %s", (firm._json(report), engagement_id))
            row = {**row, "report": report}
        return {k: v for k, v in row["report"].items() if not k.startswith("_")}


def deliver(conn: Connection, adviser_id, engagement_id: int, net: int, biggest: str, note: str, now: datetime) -> dict:
    """The Accountant hands in the report. It is marked against the client's own payments, and the
    client pays the fee: 60% to the Accountant's empire and 40% to them, or all of it without a seat."""
    with conn.transaction():
        state = _open(conn, now)
        row = _one(conn, "SELECT * FROM client_engagements WHERE id = %s AND adviser_id = %s FOR UPDATE", (engagement_id, adviser_id))
        if row is None or row["status"] != "open" or row["report"] is None:
            raise EmpireError("Open the client's figures first.")
        if not isinstance(net, int) or isinstance(net, bool) or not isinstance(biggest, str):
            raise EmpireError("Give the net change in the client's cash, in kobo, and the largest kind of payment out.")
        truth = row["report"]["_truth"]
        right_net = abs(net - truth["net"]) <= max(abs(truth["net"]) // 200, naira(1))
        right_big = biggest == truth["biggest"]
        score = 50 * right_net + 50 * right_big
        note = _text(note or "")[:400]
        report = {**row["report"], "answers": {"net": net, "biggest": biggest}, "note": note, "score": score}
        payer = ledger.player_account_id(conn, row["client_id"])
        paid = 0
        seat = empires.seat_of(conn, adviser_id)
        empire = None
        if row["empire_id"] and seat and seat["empire_id"] == row["empire_id"] and seat["empire_status"] == "active":
            empire = empires._empire(conn, row["empire_id"])
        to_empire = apply_bps(row["fee"], EMPIRE_SHARE_BPS) if empire else 0
        amounts = {ledger.player_account_id(conn, adviser_id): row["fee"] - to_empire}
        if empire:
            amounts[empire["account_id"]] = to_empire
        paid = ledger.pay_split_up_to(conn, payer=payer, amounts=amounts, kind="professional_fee",
                                      memo="A bookkeeper's fee for the quarter's report", period=state["period"], reference=f"engagement:{engagement_id}")
        conn.execute("UPDATE client_engagements SET status = 'done', report = %s, done_at = %s WHERE id = %s", (firm._json(report), now, engagement_id))
        if score:
            mine = careers.career(conn, adviser_id, "asset_manager")
            careers.add_experience(conn, adviser_id, "asset_manager", firm.DUTY_EXPERIENCE * score // 100 * (1 + (mine["rank"] if mine else 0)), now)
        if empire:
            _log(conn, empire["id"], f"The Accountant's desk earned {_money(to_empire)} from a client's bookkeeping.", now)
        return {"score": score, "paid": paid, "to_empire": to_empire}


def rate(conn: Connection, client_id, engagement_id: int, stars: int, now: datetime) -> None:
    """The client rates the work, once. A good rating lifts the bookkeeper's reputation a little; a poor one lowers it."""
    with conn.transaction():
        _open(conn, now)
        if not isinstance(stars, int) or isinstance(stars, bool) or not 1 <= stars <= 5:
            raise EmpireError("From one to five.")
        row = _one(conn, "SELECT * FROM client_engagements WHERE id = %s AND client_id = %s AND status = 'done' AND rating IS NULL FOR UPDATE",
                   (engagement_id, client_id))
        if row is None:
            raise EmpireError("There is no finished report of yours waiting for a rating.")
        conn.execute("UPDATE client_engagements SET rating = %s WHERE id = %s", (stars, engagement_id))
        change = 1 if stars >= 4 else -1 if stars <= 2 else 0
        if change:
            conn.execute("UPDATE players SET reputation = least(greatest(reputation + %s, 0), 100) WHERE id = %s", (change, row["adviser_id"]))


def lapse(conn: Connection, period: int) -> None:
    """An engagement not delivered in its quarter lapses; the client pays nothing."""
    conn.execute("UPDATE client_engagements SET status = 'lapsed' WHERE status = 'open' AND period <= %s", (period,))


def view(conn: Connection, player_id, now: datetime) -> dict:
    """What a player sees: the bookkeepers they could hire, their own engagements, and (for an Accountant) their clients."""
    period = careers.world_now(conn, now)["period"]
    mine = _rows(conn, "SELECT c.*, p.display_name AS adviser FROM client_engagements c JOIN players p ON p.id = c.adviser_id WHERE c.client_id = %s"
                       " ORDER BY c.id DESC LIMIT 6", (player_id,))
    clients = _rows(conn, "SELECT c.*, p.display_name AS client FROM client_engagements c JOIN players p ON p.id = c.client_id WHERE c.adviser_id = %s"
                          " ORDER BY c.id DESC LIMIT 12", (player_id,))
    advisers = _rows(conn, "SELECT p.id, p.display_name, p.reputation, (SELECT avg(rating)::numeric(3, 1) FROM client_engagements e WHERE e.adviser_id = p.id"
                           " AND e.rating IS NOT NULL) AS stars FROM players p WHERE p.build = 'asset_manager' AND p.id <> %s ORDER BY p.reputation DESC, p.display_name"
                           " LIMIT 20", (player_id,))

    def public(row, as_client):
        report = row["report"] or {}
        shown = {k: v for k, v in report.items() if not k.startswith("_")}
        if row["status"] != "done" and as_client:
            shown = {}
        return {"id": row["id"], "who": row["adviser"] if as_client else row["client"], "fee": row["fee"], "status": row["status"], "period": row["period"],
                "report": shown, "rating": row["rating"], "opened": row["report"] is not None}
    return {"advisers": [{"name": a["display_name"], "reputation": a["reputation"],
                          "stars": float(a["stars"]) if a["stars"] is not None else None, "key": _adviser_key(conn, a["id"], period)} for a in advisers],
            "mine": [public(r, True) for r in mine], "clients": [public(r, False) for r in clients],
            "fee_least": naira(FEE_LEAST_NAIRA), "fee_most": naira(FEE_MOST_NAIRA), "empire_share_bps": EMPIRE_SHARE_BPS}


def _adviser_key(conn: Connection, adviser_id, period: int) -> str:
    """A key that names a bookkeeper for hiring without showing their player number: their seat if they hold one, otherwise
    a code drawn from the world's secret for this quarter."""
    from simulation.empires import _roll
    return f"{_roll(conn, 'adviser', adviser_id, period):04d}{_roll(conn, 'adviser-2', adviser_id, period):04d}"


def adviser_by_key(conn: Connection, key: str, period: int):
    for a in _rows(conn, "SELECT id FROM players WHERE build = 'asset_manager'"):
        if _adviser_key(conn, a["id"], period) == key:
            return a["id"]
    raise EmpireError("There is no such bookkeeper.")



def _closed(conn: Connection, period: int, now: datetime) -> None:
    with conn.transaction():
        lapse(conn, period)


firm.CLOSED.append(_closed)
