"""Stage 9, Part B: the crash fund.

Empires pay into a shared fund each quarter for cover. When the BSX 50 falls by the trigger (15%) or more over
a quarter, the fund pays each member its cover (shared out in proportion if the fund cannot pay everybody in
full). The Risk Manager asks for cover and the head approves (the head may set it directly). Cover is at most
half of what the empire is worth. The premium is 3% of the cover each quarter; what the fund does not pay out
stays in it for the next crash. Every naira moves through the ledger.
"""

from __future__ import annotations

from datetime import datetime

from psycopg import Connection
from psycopg.rows import dict_row

from simulation import clock, empires, firm, ledger
from simulation import world_data as data
from simulation.empires import EmpireError
from simulation.money import BPS

FUND = "crash:fund"


def _rows(conn: Connection, sql: str, params=()) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def _one(conn: Connection, sql: str, params=()) -> dict | None:
    rows = _rows(conn, sql, params)
    return rows[0] if rows else None


def _fund(conn: Connection):
    if _one(conn, "SELECT 1 FROM ledger_accounts WHERE code = %s", (FUND,)) is None:
        ledger.create_account(conn, kind="escrow", name="The crash fund", code=FUND)
    return ledger.account_id(conn, FUND)


def _set(conn: Connection, empire: dict, cover: int, now: datetime) -> dict:
    if not isinstance(cover, int) or isinstance(cover, bool) or cover < 0:
        raise EmpireError("Cover is a whole number of kobo, nought or more.")
    worth = empires.worth(conn, empire, now)["total"]
    most = max(worth, 0) * data.CRASH_MOST_COVER_BPS // BPS
    if cover > most:
        raise EmpireError(f"Cover may be at most half of what the empire is worth: ₦{most // 100:,}.")
    conn.execute("INSERT INTO crash_fund_members (empire_id, cover, since, active) VALUES (%s, %s, %s, %s)"
                 " ON CONFLICT (empire_id) DO UPDATE SET cover = EXCLUDED.cover, active = EXCLUDED.active",
                 (empire["id"], cover, now, cover > 0))
    empires._log(conn, empire["id"], (f"The empire took cover of ₦{cover // 100:,} in the crash fund." if cover
                                      else "The empire left the crash fund."), now)
    return {"cover": cover, "premium": cover * data.CRASH_PREMIUM_BPS // BPS}


def ask_cover(conn: Connection, player_id, cover: int, now: datetime) -> dict:
    """The Risk Manager asks for cover (the head approves); the head sets it directly."""
    from simulation import careers
    with conn.transaction():
        seat, empire = firm._active(conn, player_id)
        if empire["head_player_id"] == player_id:
            return _set(conn, empire, cover, now)
        if seat["build"] != "risk_manager":
            raise EmpireError("The Risk Manager asks for cover in the crash fund.")
        state = careers.world_now(conn, now)
        request = firm.ask(conn, empire, kind="crash_cover", desk="head", asked_by=player_id,
                           title=f"Cover of ₦{cover // 100:,} in the crash fund ({data.CRASH_PREMIUM_BPS // 100}% a quarter)",
                           amount=cover * data.CRASH_PREMIUM_BPS // BPS, payload={"cover": cover, "why": ["protection against a crash"]},
                           period=state["period"], now=now)
        return {"waiting": True, "approval_id": request["id"]}


def _execute(conn: Connection, approval: dict, now: datetime) -> None:
    _set(conn, empires._empire(conn, approval["empire_id"]), approval["payload"]["cover"], now)


def _view(conn: Connection, approval: dict, viewer_id, now: datetime) -> dict:
    return {"why": approval["payload"].get("why", []), "fund": ledger.balance(conn, _fund(conn))}


def _staff(conn: Connection, approval: dict, now: datetime) -> tuple[bool, str]:
    return True, "The staff allowed it: cover is protection."


def close(conn: Connection, period: int, now: datetime, index_end: int) -> dict:
    """Each quarter: did the market crash? Pay out if so; then collect next quarter's premiums."""
    if _one(conn, "SELECT to_regclass('crash_fund_members') IS NOT NULL AS ok")["ok"] is not True:
        return {}
    fund = _fund(conn)
    label = clock.period_label(period)
    before = _one(conn, "SELECT index_end FROM crash_fund_quarters WHERE period = %s", (period - 1,))
    start = before["index_end"] if before else index_end
    fall = (start - index_end) * BPS // start if start else 0
    triggered = before is not None and fall >= data.CRASH_TRIGGER_BPS
    members = _rows(conn, "SELECT m.*, e.account_id, e.name FROM crash_fund_members m JOIN empires e ON e.id = m.empire_id"
                          " WHERE m.active AND e.status = 'active' ORDER BY m.empire_id")
    paid_out = 0
    if triggered and members:
        pot = ledger.balance(conn, fund)
        wanted = sum(m["cover"] for m in members)
        for m in members:
            share = m["cover"] if pot >= wanted else pot * m["cover"] // max(wanted, 1)
            if share > 0:
                ledger.transfer(conn, payer=fund, receiver=m["account_id"], amount=share, kind="crash_payout",
                                memo=f"The crash fund pays out: the BSX 50 fell {fall / 100:.1f}% in {label}", period=period)
                conn.execute("UPDATE crash_fund_members SET paid_out = paid_out + %s WHERE empire_id = %s", (share, m["empire_id"]))
                empires._log(conn, m["empire_id"], f"The crash fund paid ₦{share // 100:,}: the BSX 50 fell {fall / 100:.1f}% this quarter.", now)
                paid_out += share
    premiums = 0
    for m in members:
        premium = m["cover"] * data.CRASH_PREMIUM_BPS // BPS
        got = ledger.pay_up_to(conn, payer=m["account_id"], receiver=fund, wanted=premium, kind="crash_premium",
                               memo=f"Crash fund: cover for the quarter after {label}", period=period)
        premiums += got
        conn.execute("UPDATE crash_fund_members SET paid_in = paid_in + %s, active = %s WHERE empire_id = %s",
                     (got, got == premium, m["empire_id"]))
        if got < premium:
            empires._log(conn, m["empire_id"], "The empire could not pay the crash fund's premium: its cover has lapsed.", now)
    conn.execute("INSERT INTO crash_fund_quarters (period, index_start, index_end, triggered, premiums, paid_out) VALUES (%s, %s, %s, %s, %s, %s)"
                 " ON CONFLICT DO NOTHING", (period, start, index_end, triggered, premiums, paid_out))
    return {"triggered": triggered, "paid_out": paid_out, "premiums": premiums}


def view(conn: Connection, empire: dict) -> dict:
    mine = _one(conn, "SELECT * FROM crash_fund_members WHERE empire_id = %s", (empire["id"],))
    history = _rows(conn, "SELECT * FROM crash_fund_quarters ORDER BY period DESC LIMIT 8")
    return {"cover": mine["cover"] if mine and mine["active"] else 0, "paid_in": mine["paid_in"] if mine else 0,
            "paid_out": mine["paid_out"] if mine else 0, "fund": ledger.balance(conn, _fund(conn)),
            "premium_bps": data.CRASH_PREMIUM_BPS, "trigger_bps": data.CRASH_TRIGGER_BPS,
            "history": [{"label": clock.period_label(h["period"]), "change_bps": (h["index_end"] - h["index_start"]) * BPS // max(h["index_start"], 1),
                         "triggered": h["triggered"]} for h in history]}


firm.EXECUTORS["crash_cover"] = _execute
firm.VIEWERS["crash_cover"] = _view
firm.STAFF_RULES["crash_cover"] = _staff
