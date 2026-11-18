"""Floor extras, slice 2 (owner, 17 November 2026: "go on"): the bank desk.

Bankers lend on the Floor, as a bank's money desk does: short money, such as cash to pay for a big order before the
client's own money comes in.

  asking     a client asks for an amount, for 1, 3, 7 or 14 game days, from one to five banks (the computer banks and
             the open player desks), and gives them 15 to 60 seconds. A player may borrow on the Floor at most what they
             are worth after their debts, and not while a loan of theirs is in default.
  the file   every bank sees the client's credit file: a grade from A to D (for a player, from what they owe against what
             they are worth, and any default), and the purpose. Each grade has its own chance of failing, over a year; a
             loan's chance is that times its days over 360.
  pricing    a bank answers with a yearly rate, at most 90%. A computer bank asks the Central Bank's rate, plus twice the
             loss it expects, plus 3%. A player banker may undercut, or charge more, as they judge the risk.
  taking     the client takes one rate (a computer client takes the cheapest, at its countdown's end). The lender pays the
             money over at once, so a banker lends their own cash, and a loan is one deal under the desk's one-deal limit.
  repaying   on the due day the borrower pays back the money and the interest built up (a player may repay early, paying
             at least a day's interest). A player who cannot pay all of it owes the rest as a debt in default, collected
             from their cash, shares and bonds each quarter. A computer client fails by chance, drawn from the world's
             secret: it pays back only 40% of the money, the lender bears the loss, the Floor is told, and the loss counts
             towards the desk's day's loss limit.

Every naira moves through the ledger. A loan lent is still the lender's (it counts in what they are worth until repaid);
a loan owed counts in what the borrower owes.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from psycopg import Connection

from simulation import careers, clock, ledger, lending
from simulation import floor as fl
from simulation import world_data as data
from simulation.floor import BPS, FloorError, _money, _one, _rows, _unit

GAME_DAY_SECONDS = clock.REAL_DAYS_PER_QUARTER * 86_400 // 90
GRADE_WORDS = {
    "A": "Strong: owes little against what it is worth, and has always repaid.",
    "B": "Sound: owes a fair amount against what it is worth.",
    "C": "Stretched: owes about as much as, or more than, it is worth.",
    "D": "Weak: worth little after its debts, or has failed to repay before.",
}


def ready(conn: Connection) -> bool:
    return _one(conn, "SELECT to_regclass('floor_loans') IS NOT NULL AS ok")["ok"]


def _period(conn: Connection, now: datetime) -> int:
    return careers.world_now(conn, now)["period"]


def expected_loss_bps(grade: str) -> int:
    """A year's expected loss on a loan of this grade: its chance of failing times what is not recovered."""
    return data.FLOOR_LOAN_GRADES[grade] * (BPS - data.FLOOR_LOAN_RECOVERY_BPS) // BPS


def computer_rate(conn: Connection, ask: dict, code: str) -> int:
    jitter = round(_unit(fl._seed(conn), "floor-loan-rate", ask["id"], code) * 200) - 100
    rate = lending.policy_rate(conn) + 2 * expected_loss_bps(ask["grade"]) + data.FLOOR_LOAN_BANK_MARGIN_BPS + jitter
    return max(min(rate, data.FLOOR_LOAN_MOST_RATE_BPS), 1)


def interest(principal: int, rate_bps: int, since: datetime, until: datetime) -> int:
    return lending.accrued(principal, rate_bps, since, until)


# ---------------------------------------------------------------------------
# Credit files
# ---------------------------------------------------------------------------

def owed(conn: Connection, account) -> int:
    """What an account owes on open Floor loans (the money; interest is paid when the loan closes)."""
    if not ready(conn):
        return 0
    return _one(conn, "SELECT coalesce(sum(principal), 0)::bigint AS o FROM floor_loans WHERE borrower_account = %s AND status = 'open'",
                (account,))["o"]


def lent(conn: Connection, account) -> int:
    """What an account has lent on the Floor and not yet had back: still the lender's."""
    if not ready(conn):
        return 0
    return _one(conn, "SELECT coalesce(sum(principal), 0)::bigint AS o FROM floor_loans WHERE lender_account = %s AND status = 'open'",
                (account,))["o"]


def credit_file(conn: Connection, account, now: datetime) -> dict:
    """A player's credit file, as every bank sees it."""
    worth = lending._equity(conn, account, now)
    debts = lending.debts(conn, account)
    in_default = bool(_one(conn, "SELECT 1 AS x FROM player_loans WHERE borrower = %s AND status = 'default'", (account,)))
    history = _one(conn, "SELECT count(*) FILTER (WHERE status = 'repaid')::int AS repaid, count(*) FILTER (WHERE status = 'shortfall')::int AS"
                         " failed FROM floor_loans WHERE borrower_account = %s", (account,))
    if in_default or worth <= 0 or history["failed"]:
        grade = "D"
    elif debts * 4 <= worth:
        grade = "A"
    elif debts <= worth:
        grade = "B"
    elif debts <= 2 * worth:
        grade = "C"
    else:
        grade = "D"
    return {"grade": grade, "words": GRADE_WORDS[grade], "worth": worth, "debts": debts, "in_default": in_default,
            "repaid": history["repaid"], "failed": history["failed"]}


# ---------------------------------------------------------------------------
# Asking for money
# ---------------------------------------------------------------------------

def _check_amount(amount: int) -> None:
    low, high = data.FLOOR_LOAN_NAIRA
    if not fl._whole(amount) or not low * 100 <= amount <= high * 100:
        raise FloorError(f"Ask to borrow {_money(low * 100)} to {_money(high * 100)}.")


def _check_days(days: int) -> None:
    if days not in data.FLOOR_LOAN_DAYS:
        raise FloorError("Borrow for " + ", ".join(str(d) for d in data.FLOOR_LOAN_DAYS[:-1]) + f" or {data.FLOOR_LOAN_DAYS[-1]} days.")


def _open_ask(conn: Connection, *, account, player_id, name: str, purpose: str, grade: str, amount: int, days: int, seconds: int,
              desks: list[str], now: datetime) -> dict:
    ask = _one(conn, "INSERT INTO floor_loan_asks (client_account, client_player, client_name, purpose, grade, amount, days, created_at,"
                     " quotes_until) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING *",
               (account, player_id, name, purpose, grade, amount, days, now, now + timedelta(seconds=seconds)))
    for desk in desks:
        player = fl._desk_player(desk)
        conn.execute("INSERT INTO floor_loan_ask_desks (ask_id, desk, desk_player) VALUES (%s, %s, %s)", (ask["id"], desk, player))
        if player:
            fl._ping_player(conn, player)
        else:
            conn.execute("INSERT INTO floor_loan_quotes (ask_id, desk, rate_bps, created_at) VALUES (%s, %s, %s, %s)",
                         (ask["id"], desk, computer_rate(conn, ask, desk.split(":", 1)[1]), now))
    return ask


def ask(conn: Connection, player_id, amount: int, days: int, seconds: int, desks: list[str], now: datetime) -> dict:
    """A player asks the Floor's banks for a loan."""
    fl._market_open(now)
    account = ledger.player_account_id(conn, player_id)
    if account is None:
        raise FloorError("Your account is not open yet.")
    _check_amount(amount)
    _check_days(days)
    fl._check_window(seconds)
    fl._check_desks(conn, player_id, desks, now)
    if _one(conn, "SELECT 1 AS x FROM player_loans WHERE borrower = %s AND status = 'default'", (account,)):
        raise FloorError("A loan of yours is in default. No bank on the Floor will lend to you until it is repaid.")
    waiting = _one(conn, "SELECT count(*)::int AS n FROM floor_loan_asks WHERE client_account = %s AND status = 'open'", (account,))["n"]
    if waiting >= data.FLOOR_LOAN_MOST_OPEN:
        raise FloorError(f"You have {waiting} money requests waiting. Take or let one go first.")
    file = credit_file(conn, account, now)
    if owed(conn, account) + amount > max(file["worth"], 0):
        raise FloorError(f"On the Floor you may borrow at most what you are worth after your debts ({_money(max(file['worth'], 0))}), "
                         f"and you already owe {_money(owed(conn, account))} here.")
    name = _one(conn, "SELECT display_name FROM players WHERE id = %s", (player_id,))["display_name"]
    with conn.transaction():
        found = _open_ask(conn, account=account, player_id=player_id, name=name, purpose="for their own trading", grade=file["grade"],
                          amount=amount, days=days, seconds=seconds, desks=desks, now=now)
    return {"ask_id": found["id"], "grade": file["grade"]}


def _computer_asks(conn: Connection, now: datetime) -> int:
    """Computer clients ask the open player desks for money now and then (with two computer banks, so there is competition)."""
    desks = _rows(conn, "SELECT d.player_id FROM floor_desks d JOIN players p ON p.id = d.player_id"
                        " WHERE d.open AND p.build = 'investment_banker' ORDER BY d.player_id")
    seed, slot = fl._seed(conn), int(now.timestamp()) // 60
    account = ledger.account_id(conn, ledger.INVESTORS_INSTITUTIONS)
    made = 0
    for d in desks:
        if _unit(seed, "floor-loan-call", slot, d["player_id"]) * data.FLOOR_LOAN_CALL_CHANCE >= 1:
            continue
        if _one(conn, "SELECT 1 AS x FROM floor_loan_asks a JOIN floor_loan_ask_desks k ON k.ask_id = a.id"
                      " WHERE k.desk_player = %s AND a.client_player IS NULL AND a.status = 'open'", (d["player_id"],)):
            continue                                # one computer money request at a time to each desk
        key = (slot, d["player_id"])
        name, _style, seconds = data.FLOOR_COMPUTER_CLIENTS[int(_unit(seed, "floor-loan-client", *key) * len(data.FLOOR_COMPUTER_CLIENTS))]
        purpose = data.FLOOR_LOAN_PURPOSES[int(_unit(seed, "floor-loan-purpose", *key) * len(data.FLOOR_LOAN_PURPOSES))]
        draw, grade = _unit(seed, "floor-loan-grade", *key) * BPS, "D"
        for g, share in data.FLOOR_LOAN_GRADE_MIX:
            if draw < share:
                grade = g
                break
            draw -= share
        low, high = data.FLOOR_LOAN_CLIENT_NAIRA
        amount = (low + round(_unit(seed, "floor-loan-size", *key) * (high - low))) // 1_000_000 * 1_000_000 * 100
        days = data.FLOOR_LOAN_DAYS[int(_unit(seed, "floor-loan-days", *key) * len(data.FLOOR_LOAN_DAYS))]
        rivals = sorted(fl.COMPUTER, key=lambda c: _unit(seed, "floor-loan-rival", *key, c))[:2]
        with conn.transaction():
            _open_ask(conn, account=account, player_id=None, name=name, purpose=purpose, grade=grade, amount=amount, days=days,
                      seconds=max(seconds, 30), desks=[f"player:{d['player_id']}"] + [f"computer:{c}" for c in rivals], now=now)
        made += 1
    return made


# ---------------------------------------------------------------------------
# Pricing and taking
# ---------------------------------------------------------------------------

def _ask_row(conn: Connection, ask_id: int, *, lock: bool = False) -> dict | None:
    return _one(conn, "SELECT * FROM floor_loan_asks WHERE id = %s" + (" FOR UPDATE" if lock else ""), (ask_id,))


def quote(conn: Connection, player_id, ask_id: int, rate_bps: int, now: datetime) -> dict:
    """A banker answers a money request with a yearly rate (a new rate replaces their last)."""
    from simulation import floor_extras
    if not isinstance(rate_bps, int) or isinstance(rate_bps, bool) or not 1 <= rate_bps <= data.FLOOR_LOAN_MOST_RATE_BPS:
        raise FloorError(f"Give a yearly rate above nought and at most {data.FLOOR_LOAN_MOST_RATE_BPS // 100}%.")
    ask_now = _ask_row(conn, ask_id, lock=True)
    desk = f"player:{player_id}"
    if ask_now is None or not _one(conn, "SELECT 1 AS x FROM floor_loan_ask_desks WHERE ask_id = %s AND desk = %s", (ask_id, desk)):
        raise FloorError("That request was not sent to your desk.")
    if ask_now["status"] != "open" or ask_now["quotes_until"] <= now:
        raise FloorError("That request has closed.")
    if not _one(conn, "SELECT 1 AS x FROM floor_desks WHERE player_id = %s AND open", (player_id,)):
        raise FloorError("Open your desk to answer requests.")
    if floor_extras.frozen(conn, player_id, now):
        raise FloorError("Your desk is frozen for the rest of the trading day: today's losses passed your limit.")
    limit = floor_extras.limits_of(conn, player_id)["deal_most"]
    if ask_now["amount"] > limit:
        raise FloorError(f"That loan is past your limit of {_money(limit)} for one deal.")
    if ledger.balance(conn, ledger.player_account_id(conn, player_id)) < ask_now["amount"]:
        raise FloorError(f"You would lend your own cash, and you have less than {_money(ask_now['amount'])}.")
    with conn.transaction():
        conn.execute("UPDATE floor_loan_quotes SET status = 'withdrawn' WHERE ask_id = %s AND desk = %s AND status = 'live'", (ask_id, desk))
        row = _one(conn, "INSERT INTO floor_loan_quotes (ask_id, desk, rate_bps, created_at) VALUES (%s, %s, %s, %s) RETURNING id",
                   (ask_id, desk, rate_bps, now))
    if ask_now["client_player"]:
        fl._ping_player(conn, ask_now["client_player"])
    return {"quote_id": row["id"], "rate_bps": rate_bps}


def _lend(conn: Connection, ask_now: dict, q: dict, now: datetime) -> dict:
    """The loan is made: the lender pays the money to the borrower."""
    lender_account = fl._desk_account(conn, q["desk"])
    lender_player = fl._desk_player(q["desk"])
    if ledger.balance(conn, lender_account) < ask_now["amount"]:
        conn.execute("UPDATE floor_loan_quotes SET status = 'withdrawn' WHERE id = %s", (q["id"],))
        raise FloorError("That bank no longer has the cash to lend it.")
    period = _period(conn, now)
    loan = _one(conn, "INSERT INTO floor_loans (ask_id, quote_id, lender_desk, lender_account, lender_player, borrower_account, borrower_player,"
                      " borrower_name, grade, principal, rate_bps, days, starts_at, due_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,"
                      " %s, %s, %s) RETURNING *",
                (ask_now["id"], q["id"], q["desk"], lender_account, lender_player, ask_now["client_account"], ask_now["client_player"],
                 ask_now["client_name"], ask_now["grade"], ask_now["amount"], q["rate_bps"], ask_now["days"], now,
                 now + timedelta(seconds=ask_now["days"] * GAME_DAY_SECONDS)))
    ledger.transfer(conn, payer=lender_account, receiver=ask_now["client_account"], amount=ask_now["amount"], kind="floor_loan",
                    memo=f"A Floor loan from {fl._desk_name(conn, q['desk'])} to {ask_now['client_name']}, for {ask_now['days']} days at "
                         f"{q['rate_bps'] / 100:.2f}% a year", period=period, reference=f"floor-loan:{loan['id']}")
    conn.execute("UPDATE floor_loan_quotes SET status = CASE WHEN id = %s THEN 'won' ELSE 'lost' END WHERE ask_id = %s AND status = 'live'",
                 (q["id"], ask_now["id"]))
    conn.execute("UPDATE floor_loan_asks SET status = 'taken', done_at = %s WHERE id = %s", (now, ask_now["id"]))
    for d in _rows(conn, "SELECT desk_player FROM floor_loan_ask_desks WHERE ask_id = %s AND desk_player IS NOT NULL", (ask_now["id"],)):
        fl._ping_player(conn, d["desk_player"])
    return loan


def take(conn: Connection, player_id, ask_id: int, quote_id: int, now: datetime) -> dict:
    """A player client takes one bank's rate."""
    with conn.transaction():
        ask_now = _ask_row(conn, ask_id, lock=True)
        if ask_now is None or str(ask_now["client_player"]) != str(player_id):
            raise FloorError("That is not one of your requests.")
        if ask_now["status"] != "open" or ask_now["quotes_until"] + timedelta(seconds=data.FLOOR_LOAN_TAKE_SECONDS) <= now:
            raise FloorError("That request has closed.")
        q = _one(conn, "SELECT * FROM floor_loan_quotes WHERE id = %s AND ask_id = %s AND status = 'live'", (quote_id, ask_id))
        if q is None:
            raise FloorError("That rate is no longer offered.")
        if owed(conn, ask_now["client_account"]) + ask_now["amount"] > max(lending._equity(conn, ask_now["client_account"], now), 0):
            raise FloorError("You may borrow on the Floor at most what you are worth after your debts.")
        try:
            with conn.transaction():
                loan = _lend(conn, ask_now, q, now)
        except FloorError:
            conn.execute("UPDATE floor_loan_quotes SET status = 'withdrawn' WHERE id = %s", (q["id"],))
            raise
    return {"loan_id": loan["id"], "principal": loan["principal"], "rate_bps": loan["rate_bps"], "due_at": loan["due_at"]}


def _computer_takes(conn: Connection, ask_now: dict, now: datetime) -> None:
    """At its countdown's end a computer client takes the cheapest rate it was offered."""
    quotes = _rows(conn, "SELECT * FROM floor_loan_quotes WHERE ask_id = %s AND status = 'live' ORDER BY rate_bps, created_at", (ask_now["id"],))
    with conn.transaction():
        locked = _ask_row(conn, ask_now["id"], lock=True)
        if locked["status"] != "open":
            return
        for q in quotes:
            if q["desk"].startswith("computer:"):
                # Lent between computers: nothing on the Floor's books, and the player desks lost it.
                conn.execute("UPDATE floor_loan_quotes SET status = CASE WHEN id = %s THEN 'won' ELSE 'lost' END WHERE ask_id = %s"
                             " AND status = 'live'", (q["id"], ask_now["id"]))
                conn.execute("UPDATE floor_loan_asks SET status = 'taken', done_at = %s WHERE id = %s", (now, ask_now["id"]))
                break
            try:
                with conn.transaction():
                    _lend(conn, locked, q, now)
                break
            except FloorError:
                continue
        else:
            conn.execute("UPDATE floor_loan_asks SET status = 'passed', done_at = %s WHERE id = %s", (now, ask_now["id"]))
        for d in _rows(conn, "SELECT desk_player FROM floor_loan_ask_desks WHERE ask_id = %s AND desk_player IS NOT NULL", (ask_now["id"],)):
            fl._ping_player(conn, d["desk_player"])


# ---------------------------------------------------------------------------
# Repaying
# ---------------------------------------------------------------------------

def _close(conn: Connection, loan: dict, until: datetime, now: datetime, *, early: bool = False) -> dict:
    period = _period(conn, now)
    since = loan["starts_at"]
    if early:
        until = max(until, since + timedelta(seconds=GAME_DAY_SECONDS))       # at least a day's interest
    due_interest = interest(loan["principal"], loan["rate_bps"], since, until)
    wanted = loan["principal"] + due_interest
    memo = f"A Floor loan repaid to {fl._desk_name(conn, loan['lender_desk'])} by {loan['borrower_name']}"
    lost = 0
    if loan["borrower_player"] is None:
        chance = data.FLOOR_LOAN_GRADES[loan["grade"]] * loan["days"] // 360
        fails = _unit(fl._seed(conn), "floor-loan-fails", loan["id"]) * BPS < chance
        pay = loan["principal"] * data.FLOOR_LOAN_RECOVERY_BPS // BPS if fails else wanted
        paid = ledger.pay_up_to(conn, payer=loan["borrower_account"], receiver=loan["lender_account"], wanted=pay, kind="floor_loan_repaid",
                                memo=memo + (" in part: it failed to pay the rest" if fails else ""), period=period,
                                reference=f"floor-loan-repaid:{loan['id']}")
        lost = wanted - paid
        status = "defaulted" if lost else "repaid"
        if fails:
            fl._note(conn, f"loan-fail:{loan['id']}", "loan", f"{loan['borrower_name']} failed to repay a Floor loan of "
                     f"{_money(loan['principal'])} to {fl._desk_name(conn, loan['lender_desk'])}, paying back only {_money(paid)}.", now)
    else:
        paid = ledger.pay_up_to(conn, payer=loan["borrower_account"], receiver=loan["lender_account"], wanted=wanted, kind="floor_loan_repaid",
                                memo=memo, period=period, reference=f"floor-loan-repaid:{loan['id']}")
        short = wanted - paid
        status = "shortfall" if short else "repaid"
        if short:
            lending.record_shortfall(conn, loan["borrower_account"], loan["lender_account"], short,
                                     f"A Floor loan from {fl._desk_name(conn, loan['lender_desk'])} could not be repaid in full", period, now)
        fl._ping_player(conn, loan["borrower_player"])
    conn.execute("UPDATE floor_loans SET status = %s, interest = %s, paid = %s, lost = %s, closed_at = %s WHERE id = %s",
                 (status, due_interest, paid, lost, now, loan["id"]))
    if loan["lender_player"]:
        fl._ping_player(conn, loan["lender_player"])
    return {"loan_id": loan["id"], "status": status, "interest": due_interest, "paid": paid, "lost": lost}


def repay(conn: Connection, player_id, loan_id: int, now: datetime) -> dict:
    """A player repays a Floor loan early, with the interest to now (at least a day's)."""
    account = ledger.player_account_id(conn, player_id)
    with conn.transaction():
        loan = _one(conn, "SELECT * FROM floor_loans WHERE id = %s FOR UPDATE", (loan_id,))
        if loan is None or loan["borrower_account"] != account:
            raise FloorError("That is not one of your loans.")
        if loan["status"] != "open":
            raise FloorError("That loan is already closed.")
        wanted = loan["principal"] + interest(loan["principal"], loan["rate_bps"], loan["starts_at"],
                                              max(now, loan["starts_at"] + timedelta(seconds=GAME_DAY_SECONDS)))
        if ledger.balance(conn, account) < wanted:
            raise FloorError(f"Repaying it now takes {_money(wanted)}, and you have less than that.")
        return _close(conn, loan, now, now, early=True)


def tick(conn: Connection, now: datetime) -> None:
    """Computer clients take their rates and ask for money; requests whose time is up close; loans due are repaid."""
    if not ready(conn):
        return
    for a in _rows(conn, "SELECT * FROM floor_loan_asks WHERE status = 'open' AND client_player IS NULL AND quotes_until <= %s ORDER BY id", (now,)):
        _computer_takes(conn, a, now)
    with conn.transaction():
        conn.execute("UPDATE floor_loan_quotes q SET status = 'lost' FROM floor_loan_asks a WHERE a.id = q.ask_id AND q.status = 'live'"
                     " AND a.status = 'open' AND a.client_player IS NOT NULL AND a.quotes_until <= %s",
                     (now - timedelta(seconds=data.FLOOR_LOAN_TAKE_SECONDS),))
        conn.execute("UPDATE floor_loan_asks SET status = 'expired', done_at = %s WHERE status = 'open' AND client_player IS NOT NULL"
                     " AND quotes_until <= %s", (now, now - timedelta(seconds=data.FLOOR_LOAN_TAKE_SECONDS)))
    for loan in _rows(conn, "SELECT id FROM floor_loans WHERE status = 'open' AND due_at <= %s ORDER BY id", (now,)):
        with conn.transaction():
            row = _one(conn, "SELECT * FROM floor_loans WHERE id = %s AND status = 'open' FOR UPDATE", (loan["id"],))
            if row:
                _close(conn, row, row["due_at"], now)
    if clock.market_state(now).value == "open":
        _computer_asks(conn, now)


# ---------------------------------------------------------------------------
# The day's result, and what each side sees
# ---------------------------------------------------------------------------

def day_result(conn: Connection, banker, since: datetime, until: datetime) -> int:
    """What a desk's loans closed in a time earned in interest, less what was lost."""
    if not ready(conn):
        return 0
    row = _one(conn, "SELECT coalesce(sum(paid - principal), 0)::bigint AS n FROM floor_loans WHERE lender_player = %s AND status <> 'open'"
                     " AND closed_at >= %s AND closed_at <= %s", (banker, since, until))
    return row["n"]


def _loan_view(conn: Connection, loan: dict, now: datetime) -> dict:
    out = {k: loan[k] for k in ("id", "borrower_name", "grade", "principal", "rate_bps", "days", "starts_at", "due_at", "status",
                                "interest", "paid", "lost", "closed_at")}
    out["lender"] = fl._desk_name(conn, loan["lender_desk"])
    out["interest_now"] = interest(loan["principal"], loan["rate_bps"], loan["starts_at"], min(now, loan["due_at"])) \
        if loan["status"] == "open" else loan["interest"]
    return out


def record(conn: Connection, banker) -> dict:
    row = _one(conn, "SELECT count(*)::int AS loans, coalesce(sum(principal), 0)::bigint AS lent,"
                     " coalesce(sum(paid - principal) FILTER (WHERE status <> 'open'), 0)::bigint AS earned,"
                     " coalesce(sum(lost), 0)::bigint AS lost, count(*) FILTER (WHERE status IN ('defaulted', 'shortfall'))::int AS failed"
                     " FROM floor_loans WHERE lender_player = %s", (banker,))
    return row


def view(conn: Connection, player_id, now: datetime) -> dict:
    if not ready(conn):
        return {"ready": False}
    account = ledger.player_account_id(conn, player_id)
    out: dict = {"ready": True, "policy_rate_bps": lending.policy_rate(conn), "days": list(data.FLOOR_LOAN_DAYS),
                 "least": data.FLOOR_LOAN_NAIRA[0] * 100, "most": data.FLOOR_LOAN_NAIRA[1] * 100,
                 "most_rate_bps": data.FLOOR_LOAN_MOST_RATE_BPS, "window": list(data.FLOOR_WINDOW_SECONDS),
                 "grades": [{"grade": g, "words": GRADE_WORDS[g], "yearly_fail_bps": data.FLOOR_LOAN_GRADES[g],
                             "expected_loss_bps": expected_loss_bps(g)} for g in data.FLOOR_LOAN_GRADES],
                 "recovery_bps": data.FLOOR_LOAN_RECOVERY_BPS, "game_day_seconds": GAME_DAY_SECONDS}
    if account is None:
        return out
    out["desks"] = [{"key": d["key"], "name": d["name"], "kind": d["kind"]} for d in fl.desks_for(conn, player_id)]
    out["file"] = credit_file(conn, account, now)
    out["owed"] = owed(conn, account)
    out["asks"] = []
    for a in _rows(conn, "SELECT * FROM floor_loan_asks WHERE client_account = %s AND client_player = %s AND status = 'open' ORDER BY id DESC",
                   (account, player_id)):
        quotes = _rows(conn, "SELECT id, desk, rate_bps FROM floor_loan_quotes WHERE ask_id = %s AND status = 'live' ORDER BY rate_bps", (a["id"],))
        out["asks"].append({"id": a["id"], "amount": a["amount"], "days": a["days"], "quotes_until": a["quotes_until"],
                            "take_until": a["quotes_until"] + timedelta(seconds=data.FLOOR_LOAN_TAKE_SECONDS),
                            "quotes": [{"id": q["id"], "bank": fl._desk_name(conn, q["desk"]), "rate_bps": q["rate_bps"],
                                        "interest": interest(a["amount"], q["rate_bps"], now, now + timedelta(seconds=a["days"] * GAME_DAY_SECONDS))}
                                       for q in quotes]})
    out["borrowed"] = [_loan_view(conn, loan, now) for loan in _rows(
        conn, "SELECT * FROM floor_loans WHERE borrower_account = %s ORDER BY (status = 'open') DESC, id DESC LIMIT 10", (account,))]
    if fl._is_banker(conn, player_id):
        desk = f"player:{player_id}"
        incoming = []
        for a in _rows(conn, "SELECT a.* FROM floor_loan_asks a JOIN floor_loan_ask_desks k ON k.ask_id = a.id WHERE k.desk = %s"
                             " AND a.status = 'open' AND a.quotes_until > %s ORDER BY a.quotes_until", (desk, now)):
            mine = _one(conn, "SELECT rate_bps FROM floor_loan_quotes WHERE ask_id = %s AND desk = %s AND status = 'live'", (a["id"], desk))
            item = {"id": a["id"], "client": a["client_name"], "computer": a["client_player"] is None, "purpose": a["purpose"],
                    "grade": a["grade"], "grade_words": GRADE_WORDS[a["grade"]], "amount": a["amount"], "days": a["days"],
                    "quotes_until": a["quotes_until"], "my_rate_bps": mine["rate_bps"] if mine else None,
                    "expected_loss_bps": expected_loss_bps(a["grade"]),
                    "loan_fail_bps": data.FLOOR_LOAN_GRADES[a["grade"]] * a["days"] // 360}
            if a["client_player"] is not None:
                f = credit_file(conn, a["client_account"], now)
                item["file"] = {k: f[k] for k in ("worth", "debts", "in_default", "repaid", "failed")}
            incoming.append(item)
        out["incoming"] = incoming
        out["book"] = [_loan_view(conn, loan, now) for loan in _rows(
            conn, "SELECT * FROM floor_loans WHERE lender_player = %s ORDER BY (status = 'open') DESC, id DESC LIMIT 12", (player_id,))]
        out["record"] = record(conn, player_id)
    return out
