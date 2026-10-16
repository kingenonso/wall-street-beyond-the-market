"""The firm's money: who owns the empire, what it borrows, what it pays out, what each desk may spend.

  partners         an empire run by players is owned in units by those who put money in
  raising money    a loan from a bank, a bond sold to the pension funds, or a stake sold to anybody:
                   the Investment Banker designs it, the Accountant and the Risk Manager approve it,
                   the Legal Counsel reads the paper, the head signs
  what is owed     interest every quarter, the promises tested every quarter, repayment when due
  dividends        the partners vote a payout of up to half the quarter's profit
  treasury policy  the members vote how the empire's money is split between cash, bonds and shares
  budgets          the head gives each desk a budget; a desk that does its work under budget earns a pool
  expenses         any cost above a threshold waits for the Accountant's desk
  the accounts     the empire's own quarterly accounts, closed and kept for good

Nothing here makes money. Every naira moves through the ledger from one account to another.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from psycopg import Connection

from simulation import banking, careers, clock, empires, firm, leagues, ledger
from simulation.empires import EmpireError, _log, _money, _one, _open, _rows
from simulation.money import BPS, apply_bps, naira

DEBT_MOST_BPS = 5000                  # an empire may owe up to half of what it owns
DIVIDEND_MOST_BPS = 5000              # a payout may be up to half of the last closed quarter's profit
EXPENSE_APPROVAL_NAIRA = 250_000      # a cost above this waits for the Accountant's desk
LOAN_SPREAD_BPS = 400                 # a bank lends to an empire at the Central Bank's rate and four points
BOND_SPREAD_BPS = 250                 # the pension funds lend at two and a half points over it, for a bond
BOND_LEAST_NAIRA = 50_000_000         # a bond issue is for at least this much
LOAN_LEAST_NAIRA = 5_000_000
STAKE_LEAST_NAIRA = 5_000_000         # a stake offer is for at least this much; a raising counts as done only once this much has come in
TERMS = (4, 8)                        # quarters a loan or a bond runs
STAKE_DAYS = 3                        # a stake offer stays open this many real days
STAKE_MOST_BPS = 2500                 # a stake offer may raise up to a quarter of the empire's worth
STRUCK_FAIR_BPS = 50                  # each fair clause struck out costs half a point on the rate
POOL_SHARE_BPS = 2000                 # a desk under budget earns a fifth of what it did not spend, for its members
TRAINING_EXPERIENCE_PER_NAIRA = 10_000   # a member's training: a point of experience for each ₦10,000...
TRAINING_MOST_EXPERIENCE = 500           # ...up to this much in a quarter
CASH_COVER_QUARTERS = 1               # the standard promise: cash at least one quarter's interest

LOAN_CLAUSES = [
    {"code": "interest", "trap": False, "words": "Interest is paid every quarter at the rate on the front page.",
     "plain": "The ordinary promise to pay interest."},
    {"code": "repay", "trap": False, "words": "The whole sum is repaid on the date on the front page.",
     "plain": "The ordinary promise to repay."},
    {"code": "information", "trap": False, "words": "The borrower sends the lender its quarterly accounts.",
     "plain": "Usual: the lender wants to see the accounts."},
    {"code": "gearing", "trap": False, "words": "The borrower will not owe more than half of what it owns.",
     "plain": "The standard promise about borrowing. The game's own limit is the same."},
    {"code": "cash_cover", "trap": False, "words": "The borrower keeps cash of at least one quarter's interest.",
     "plain": "The standard promise about cash."},
    {"code": "law", "trap": False, "words": "This agreement is governed by the laws of the Federation.",
     "plain": "Which law applies. Harmless."},
    {"code": "notices", "trap": False, "words": "Notices are given in writing to the addresses on the front page.",
     "plain": "How letters are sent. Harmless."},
    {"code": "rate_step", "trap": True, "words": "If the borrower's worth falls in any quarter, the rate rises by three points for the rest of the term.",
     "plain": "A trap: one bad quarter makes the loan much dearer for good."},
    {"code": "call_anytime", "trap": True, "words": "The lender may demand repayment in full at any time, for any reason, on one day's notice.",
     "plain": "A trap: the lender can call in the loan whenever it likes."},
    {"code": "repay_fee", "trap": True, "words": "Repaying before the date carries a fee of five per cent of the sum.",
     "plain": "A trap: the empire is locked in, or pays to get out."},
    {"code": "guarantee", "trap": True, "words": "The head of the borrower guarantees the debt personally, from their own money.",
     "plain": "A trap for the head: if the empire cannot pay, the head pays a tenth of it from their own pocket."},
    {"code": "tight_cash", "trap": True, "words": "The borrower keeps cash of at least a quarter of the sum owed at all times.",
     "plain": "A trap: a promise so tight it is easily broken, and then the loan can be called."},
    {"code": "cross_default", "trap": True, "words": "If any other debt of the borrower is called, this one is called too.",
     "plain": "A trap: one called loan brings down every loan."},
]

STAKE_CLAUSES = [
    {"code": "units", "trap": False, "words": "Each new partner receives units at the price on the front page.",
     "plain": "The ordinary terms of a stake."},
    {"code": "dividends", "trap": False, "words": "New units share in dividends equally with the old.", "plain": "Fair to everybody."},
    {"code": "law", "trap": False, "words": "This offer is governed by the laws of the Federation.", "plain": "Harmless."},
    {"code": "information", "trap": False, "words": "Partners receive the empire's quarterly accounts.", "plain": "Usual."},
    {"code": "cheap_units", "trap": True, "words": "The organiser of the offer may take units for itself at half the price.",
     "plain": "A trap: somebody outside gets the empire cheap."},
    {"code": "first_call", "trap": True, "words": "New partners are paid back their money before any dividend to the old.",
     "plain": "A trap: the old partners stand behind the new."},
]
TRAP_NAMES = {c["code"]: c["plain"] for c in LOAN_CLAUSES + STAKE_CLAUSES if c["trap"]}


# ---------------------------------------------------------------------------
# Partners and units
# ---------------------------------------------------------------------------

def _owned(conn: Connection, empire: dict, now: datetime) -> int:
    from simulation import objectives
    return objectives.wealth(conn, empire["account_id"], now)["total"]


def ensure_units(conn: Connection, empire: dict) -> None:
    """Units are first counted from what each partner has put in: one unit for each kobo."""
    if empire["kind"] != "player" or _one(conn, "SELECT 1 FROM empire_units WHERE empire_id = %s LIMIT 1", (empire["id"],)):
        return
    for row in _rows(conn, "SELECT player_id, sum(amount)::bigint AS put FROM empire_capital WHERE empire_id = %s GROUP BY player_id"
                           " HAVING sum(amount) > 0", (empire["id"],)):
        conn.execute("INSERT INTO empire_units (empire_id, holder_account, player_id, units) VALUES (%s, %s, %s, %s)",
                     (empire["id"], ledger.player_account_id(conn, row["player_id"]), row["player_id"], row["put"]))


def units_total(conn: Connection, empire_id) -> int:
    return _one(conn, "SELECT coalesce(sum(units), 0)::bigint AS n FROM empire_units WHERE empire_id = %s", (empire_id,))["n"]


def unit_price(conn: Connection, empire: dict, now: datetime) -> int:
    """What one unit of the empire is worth, to the kobo, for showing. Units are bought and sold with
    exact arithmetic (see `units_for` and `value_of`), never at this rounded figure."""
    ensure_units(conn, empire)
    total = units_total(conn, empire["id"])
    worth = empires.worth(conn, empire, now)["total"]
    return worth // total if total else 0


def units_for(conn: Connection, empire: dict, amount: int, now: datetime) -> int:
    """How many units money put in buys at today's worth, exactly: amount × units ÷ worth. Nobody
    already in is diluted. Nothing is sold while the empire is worth nothing or less."""
    ensure_units(conn, empire)
    total = units_total(conn, empire["id"])
    worth = empires.worth(conn, empire, now)["total"]
    if not total:
        return amount
    if worth <= 0:
        raise EmpireError("The empire is worth nothing or less: no units can be sold until it recovers.")
    return amount * total // worth


def value_of(conn: Connection, empire: dict, units: int, now: datetime) -> int:
    """What some units are worth today, exactly: units × worth ÷ units in issue, and nothing below nought."""
    total = units_total(conn, empire["id"])
    worth = empires.worth(conn, empire, now)["total"]
    return units * worth // total if total and worth > 0 else 0


def _add_units(conn: Connection, empire: dict, player_id, units: int) -> None:
    if units <= 0:
        return
    conn.execute("INSERT INTO empire_units (empire_id, holder_account, player_id, units) VALUES (%s, %s, %s, %s)"
                 " ON CONFLICT (empire_id, holder_account) DO UPDATE SET units = empire_units.units + excluded.units",
                 (empire["id"], ledger.player_account_id(conn, player_id), player_id, units))


def capital_in(conn: Connection, empire: dict, player_id, amount: int, now: datetime) -> None:
    """More capital put into an open empire buys units at today's price, so nobody already in is diluted."""
    if empire["kind"] != "player" or empire["status"] != "active" or amount <= 0:
        return
    _add_units(conn, empire, player_id, units_for(conn, empire, amount, now))


def partners(conn: Connection, empire: dict, now: datetime) -> list[dict]:
    ensure_units(conn, empire)
    total = units_total(conn, empire["id"])
    rows = _rows(conn, "SELECT u.player_id, u.units, p.display_name FROM empire_units u LEFT JOIN players p ON p.id = u.player_id"
                       " WHERE u.empire_id = %s AND u.units > 0 ORDER BY u.units DESC", (empire["id"],))
    return [{"player_id": r["player_id"], "name": r["display_name"] or "Outside investors", "units": r["units"],
             "share_bps": r["units"] * BPS // total if total else 0, "value": value_of(conn, empire, r["units"], now)} for r in rows]


# ---------------------------------------------------------------------------
# What is owed
# ---------------------------------------------------------------------------

def _policy(conn: Connection, now: datetime) -> int:
    return careers.world_now(conn, now)["policy_rate_bps"]


def debts(conn: Connection, empire_id) -> list[dict]:
    return _rows(conn, "SELECT * FROM empire_debts WHERE empire_id = %s ORDER BY id", (empire_id,))


def _lender_bank(conn: Connection, period: int, amount: int) -> dict | None:
    """The bank with the most room to lend that has the cash for it."""
    fits = []
    for bank in banking.banks(conn, period):
        room = banking.lending_room(bank)
        cash = ledger.balance(conn, bank["account_id"]) - banking.reserve(bank)
        if room >= amount and cash >= amount:
            fits.append((room, bank))
    return max(fits, key=lambda f: (f[0], f[1]["ticker"]))[1] if fits else None


def _quarter_interest(debt: dict) -> int:
    return debt["outstanding"] * debt["rate_bps"] // BPS // 4


def gearing_room(conn: Connection, empire: dict, now: datetime) -> int:
    """How much more the empire may borrow before it owes half of what it owns."""
    owned = _owned(conn, empire, now)
    return max(apply_bps(owned, DEBT_MOST_BPS) - firm.debt_of(conn, empire["id"]), 0)


def design_raising(conn: Connection, player_id, kind: str, amount: int, quarters: int, now: datetime) -> dict:
    """The Investment Banker designs a way to raise money for the empire. It goes to the Accountant's
    desk to check what the empire can carry, then to the Risk Manager's, then the Legal Counsel reads the
    paper, then the head signs. Any of them may stop it."""
    with conn.transaction():
        state = _open(conn, now)
        seat, empire = firm._active(conn, player_id)
        if not firm.player_run(empire):
            raise EmpireError("An empire run by the computer does not borrow.")
        if seat["build"] != "investment_banker" and empire["head_player_id"] != player_id:
            raise EmpireError("Raising money is designed by the empire's Investment Banker (or by its head).")
        if kind not in ("loan", "bond", "stake"):
            raise EmpireError("Raise money by a loan, a bond or a stake.")
        if not firm._whole(amount, 1):
            raise EmpireError("An amount above nought, in kobo.")
        if kind != "stake" and quarters not in TERMS:
            raise EmpireError(f"A loan or a bond runs for {TERMS[0]} or {TERMS[1]} quarters.")
        if _one(conn, "SELECT 1 FROM empire_approvals WHERE empire_id = %s AND kind IN ('raise_check', 'raise_risk', 'raise_sign')"
                      " AND status = 'waiting'", (empire["id"],)) or _one(
                conn, "SELECT 1 FROM empire_documents WHERE empire_id = %s AND kind IN ('loan', 'bond', 'stake') AND status = 'draft'", (empire["id"],)):
            raise EmpireError("A raising is already on its way through the desks. Let it finish first.")
        if kind == "loan" and amount < naira(LOAN_LEAST_NAIRA):
            raise EmpireError(f"A bank lends at least {_money(naira(LOAN_LEAST_NAIRA))}.")
        if kind == "bond" and amount < naira(BOND_LEAST_NAIRA):
            raise EmpireError(f"A bond issue is for at least {_money(naira(BOND_LEAST_NAIRA))}.")
        policy = _policy(conn, now)
        if kind == "stake" and amount < naira(STAKE_LEAST_NAIRA):
            raise EmpireError(f"A stake offer is for at least {_money(naira(STAKE_LEAST_NAIRA))}.")
        if kind != "stake" and _one(conn, "SELECT 1 FROM empire_debts WHERE empire_id = %s AND status = 'defaulted'", (empire["id"],)):
            raise EmpireError("The empire is in default on a debt. Nobody lends to it until that is paid.")
        terms = {"kind": kind, "amount": amount, "quarters": quarters if kind != "stake" else 0,
                 "rate_bps": policy + (LOAN_SPREAD_BPS if kind == "loan" else BOND_SPREAD_BPS) if kind != "stake" else 0}
        what = {"loan": "a bank loan", "bond": "a bond sold to the pension funds", "stake": "a stake in the empire"}[kind]
        title = f"Raise {_money(amount)} by {what}" + (f" over {quarters} quarters at {terms['rate_bps'] / 100:.2f}%" if kind != "stake" else "")
        approval = firm.ask(conn, empire, kind="raise_check", desk="accountant", asked_by=player_id, title=title, amount=amount, payload=terms,
                            period=state["period"], now=now)
        _log(conn, empire["id"], f"{firm._name(conn, player_id)} designed a way to raise money: {title}. It goes to the Accountant's desk.", now)
        for hook in firm.RAISE_DESIGNED:
            hook(conn, empire, approval, now)
        return {"approval_id": approval["id"], "title": title, "terms": terms}


def _raise_view(conn: Connection, approval: dict, viewer_id, now: datetime) -> dict:
    empire = empires._empire(conn, approval["empire_id"])
    terms = approval["payload"]
    owned = _owned(conn, empire, now)
    owed = firm.debt_of(conn, empire["id"])
    after = owed + (terms["amount"] if terms["kind"] != "stake" else 0)
    return {"terms": terms, "owned": owned, "owed_now": owed, "owed_after": after,
            "gearing_after_bps": after * BPS // owned if owned else None, "most_bps": DEBT_MOST_BPS,
            "interest_a_quarter": terms["amount"] * terms["rate_bps"] // BPS // 4 if terms["kind"] != "stake" else 0,
            "cash": ledger.balance(conn, empire["account_id"])}


def _raise_checked(conn: Connection, approval: dict, now: datetime) -> None:
    """The Accountant's desk says the empire can carry it: on to the Risk Manager's desk."""
    empire = empires._empire(conn, approval["empire_id"])
    terms = approval["payload"]
    if terms["kind"] != "stake" and terms["amount"] > gearing_room(conn, empire, now):
        raise EmpireError(f"The empire would owe more than half of what it owns. It may borrow up to {_money(gearing_room(conn, empire, now))} more.")
    firm.ask(conn, empire, kind="raise_risk", desk="risk_manager", asked_by=approval["asked_by"], title=approval["title"], amount=approval["amount"],
             payload=terms, period=careers.world_now(conn, now)["period"], now=now)


def _raise_risked(conn: Connection, approval: dict, now: datetime) -> None:
    """The Risk Manager's desk agrees: the paper is drawn up for the Legal Counsel to read."""
    empire = empires._empire(conn, approval["empire_id"])
    terms = approval["payload"]
    pool = STAKE_CLAUSES if terms["kind"] == "stake" else LOAN_CLAUSES
    clauses = firm.draw_clauses(conn, pool, 6 if terms["kind"] == "stake" else 8, (1, 2) if terms["kind"] == "stake" else (1, 3),
                                "raise", empire["id"], approval["id"])
    firm.draft_document(conn, empire, kind=terms["kind"], title=approval["title"], ref=f"raise:{approval['id']}", clauses=clauses,
                        period=careers.world_now(conn, now)["period"], now=now)


def _raise_read(conn: Connection, empire: dict, doc: dict, now: datetime) -> None:
    """The paper has been read: it goes to the head to sign."""
    if doc["kind"] not in ("loan", "bond", "stake") or not (doc["ref"] or "").startswith("raise:"):
        return
    first = _one(conn, "SELECT * FROM empire_approvals WHERE id = %s", (int(doc["ref"].split(":")[1]),))
    terms = {**first["payload"], "document_id": doc["id"]}
    kept = ", ".join(TRAP_NAMES[t].split(":")[0] for t in doc["kept_traps"]) if doc["kept_traps"] else ""
    # The head signs for the empire: it is the empire that asks, so a head who designed it may still sign it.
    firm.ask(conn, empire, kind="raise_sign", desk="head", asked_by=None, title=first["title"], amount=first["amount"],
             payload=terms, period=careers.world_now(conn, now)["period"], now=now)
    _log(conn, empire["id"], f"The paper for \"{first['title']}\" has been read" + (". Something in it was left unstruck." if kept else
                                                                                       ", and it is clean.") + " It waits for the head's signature.", now)


def _raise_signed(conn: Connection, approval: dict, now: datetime) -> None:
    """The head signs: the money arrives (or the stake offer opens)."""
    empire = empires._empire(conn, approval["empire_id"], lock=True)
    terms = approval["payload"]
    state = careers.world_now(conn, now)
    doc = firm.read_document(conn, terms["document_id"])
    conn.execute("UPDATE empire_documents SET status = 'signed' WHERE id = %s", (doc["id"],))
    if terms["kind"] == "stake":
        open_stake(conn, empire, terms["amount"], approval["id"], doc, now)
        return
    if terms["amount"] > gearing_room(conn, empire, now):
        raise EmpireError("Since this was designed the empire's position has changed: it would now owe more than half of what it owns.")
    rate = terms["rate_bps"] + STRUCK_FAIR_BPS * len(doc["wrongly_struck"])
    if terms["kind"] == "loan":
        bank = _lender_bank(conn, state["period"], terms["amount"])
        if bank is None:
            raise EmpireError("No bank has the room or the cash to lend that much this quarter.")
        lender, lender_name = bank["account_id"], bank["name"]
    else:
        lender, lender_name = ledger.account_id(conn, ledger.INVESTORS_INSTITUTIONS), "The pension funds"
        if ledger.balance(conn, lender) < terms["amount"]:
            raise EmpireError("The pension funds have not that much cash to lend this quarter.")
    ledger.transfer(conn, payer=lender, receiver=empire["account_id"], amount=terms["amount"], kind="empire_borrowing",
                    memo=f"{empire['name']}: {terms['kind']} from {lender_name}", period=state["period"], reference=f"approval:{approval['id']}")
    debt = _one(conn, "INSERT INTO empire_debts (empire_id, kind, lender_account, lender_name, principal, outstanding, rate_bps, taken_period,"
                      " due_period, document_id, traps, signed_by, at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING *",
                (empire["id"], terms["kind"], lender, lender_name, terms["amount"], terms["amount"], rate, state["period"],
                 state["period"] + terms["quarters"], doc["id"], doc["kept_traps"], empire["head_player_id"], now))
    _log(conn, empire["id"], f"The empire borrowed {_money(terms['amount'])} from {lender_name} at {rate / 100:.2f}% a year, "
                             f"to be repaid by {clock.period_label(debt['due_period'])}.", now)
    for hook in firm.RAISED:
        hook(conn, empire, {"kind": terms["kind"], "amount": terms["amount"], "debt_id": debt["id"]}, now)


def _raise_dropped(conn: Connection, approval: dict, now: datetime) -> None:
    _log(conn, approval["empire_id"], f"The raising \"{approval['title']}\" was stopped.", now)


def _raise_doc_dropped(conn: Connection, empire: dict, doc: dict, now: datetime) -> None:
    if (doc["ref"] or "").startswith("raise:"):
        _log(conn, empire["id"], f"Nobody read the paper for \"{doc['title']}\" in three days. The raising was dropped.", now)


def _staff_raise_rule(conn: Connection, approval: dict, now: datetime) -> tuple[bool, str]:
    empire = empires._empire(conn, approval["empire_id"])
    terms = approval["payload"]
    if terms["kind"] != "stake" and terms["amount"] > gearing_room(conn, empire, now):
        return False, "The staff will not let the empire owe more than half of what it owns."
    return True, "Within the empire's limits."


def repay(conn: Connection, head_id, debt_id: int, now: datetime) -> dict:
    """The head repays a debt early, in full."""
    with conn.transaction():
        state = _open(conn, now)
        empire = empires._head(conn, head_id)
        debt = _one(conn, "SELECT * FROM empire_debts WHERE id = %s AND empire_id = %s FOR UPDATE", (debt_id, empire["id"]))
        if debt is None or debt["status"] not in ("open", "called"):
            raise EmpireError("There is no such debt open.")
        fee = apply_bps(debt["outstanding"], 500) if "repay_fee" in debt["traps"] else 0
        try:
            ledger.transfer(conn, payer=empire["account_id"], receiver=debt["lender_account"], amount=debt["outstanding"] + fee,
                            kind="empire_repayment", memo=f"{empire['name']}: repaid to {debt['lender_name']}" + (" with the early-repayment fee" if fee else ""),
                            period=state["period"])
        except ledger.InsufficientFunds:
            raise EmpireError(f"Repaying needs {_money(debt['outstanding'] + fee)} in cash.") from None
        conn.execute("UPDATE empire_debts SET outstanding = 0, status = 'repaid' WHERE id = %s", (debt_id,))
        _log(conn, empire["id"], f"The empire repaid {_money(debt['outstanding'])} to {debt['lender_name']}"
                                 + (f", with a fee of {_money(fee)} under a clause nobody struck out" if fee else "") + ".", now)
        return {"repaid": debt["outstanding"], "fee": fee}


def covenant_test(conn: Connection, empire: dict, debt: dict, now: datetime) -> list[str]:
    """The promises in a debt that are broken right now."""
    owned = _owned(conn, empire, now)
    owed = firm.debt_of(conn, empire["id"])
    cash = ledger.balance(conn, empire["account_id"])
    broken = []
    if owed * BPS > owned * DEBT_MOST_BPS:
        broken.append("It owes more than half of what it owns.")
    if cash < _quarter_interest(debt) * CASH_COVER_QUARTERS:
        broken.append("Its cash is below one quarter's interest.")
    if "tight_cash" in debt["traps"] and cash * 4 < debt["outstanding"]:
        broken.append("Its cash is below a quarter of what it owes (a clause nobody struck out).")
    if "cross_default" in debt["traps"] and _one(conn, "SELECT 1 FROM empire_debts WHERE empire_id = %s AND id <> %s AND status = 'called'",
                                                 (empire["id"], debt["id"])):
        broken.append("Another of its debts has been called (a clause nobody struck out).")
    return broken


def _seize(conn: Connection, empire: dict, debt: dict, wanted: int, period: int, now: datetime) -> int:
    """What cash cannot pay, the lender takes in shares, at today's prices, largest holding first."""
    from simulation import exchange, marketview
    prices = {s["id"]: s for s in marketview._shares(conn, exchange.session_of(now)[0])}
    took = 0
    for row in _rows(conn, "SELECT c.id, c.ticker, c.share_asset, b.balance AS shares FROM ledger_balances b JOIN companies c ON c.share_asset = b.asset"
                           " WHERE b.account_id = %s AND b.balance > 0 ORDER BY b.balance DESC", (empire["account_id"],)):
        if took >= wanted:
            break
        price = prices.get(row["id"], {}).get("price")
        if not price:
            continue
        shares = min(row["shares"], -(-(wanted - took) // price))
        ledger.transfer(conn, payer=empire["account_id"], receiver=debt["lender_account"], amount=shares, asset=row["share_asset"],
                        kind="empire_default", memo=f"{empire['name']}: {shares:,} {row['ticker']} shares taken by {debt['lender_name']}", period=period)
        took += min(shares * price, wanted - took)
    return took


def _default(conn: Connection, empire: dict, debt: dict, owed: int, period: int, now: datetime, *, interest: bool) -> None:
    """The empire cannot pay what is due: the lender takes what cash there is, then shares; the head who
    signed pays under a personal guarantee. What was due as interest is not taken off what is owed."""
    took = ledger.pay_up_to(conn, payer=empire["account_id"], receiver=debt["lender_account"], wanted=owed, kind="empire_default",
                            memo=f"{empire['name']}: what could be paid of a debt in default", period=period)
    if took < owed and debt.get("kind") == "buyout" and not interest:
        # A buyout loan is secured on the company it paid for: the bank takes that first.
        from simulation import firm_deals
        took += firm_deals.enforce_security(conn, empire, debt, owed - took, period, now)
    if took < owed:
        took += _seize(conn, empire, debt, owed - took, period, now)
    left = owed - took
    guarantor = debt.get("signed_by")
    if left > 0 and "guarantee" in debt["traps"] and guarantor and not debt.get("guarantee_called"):
        took += ledger.pay_up_to(conn, payer=ledger.player_account_id(conn, guarantor), receiver=debt["lender_account"],
                                 wanted=min(left, debt["principal"] // 10), kind="empire_guarantee",
                                 memo=f"{empire['name']}: the personal guarantee of the head who signed", period=period)
    paid_off = 0 if interest else took
    conn.execute("UPDATE empire_debts SET outstanding = greatest(outstanding - %s, 0), status = CASE WHEN outstanding - %s <= 0 THEN 'repaid'"
                 " ELSE 'defaulted' END WHERE id = %s", (paid_off, paid_off, debt["id"]))
    if debt["status"] != "defaulted":
        leagues.award(conn, empire["id"], -5, f"Defaulted on a debt to {debt['lender_name']}", period, now, reference=f"default:{debt['id']}")
        if empire["head_player_id"]:
            firm.ceo_note(conn, empire["head_player_id"], empire["id"], "default", f"The empire defaulted on a debt to {debt['lender_name']}.",
                          period, now, good=False, reference=f"default:{debt['id']}")
    _log(conn, empire["id"], f"The empire could not pay {debt['lender_name']} in full: it is in default. {_money(took)} of {_money(owed)} was taken.", now)


def _close_debts(conn: Connection, empire: dict, period: int, now: datetime) -> None:
    """As a quarter closes: interest is paid, debts due are repaid, a called debt must be repaid now,
    and the promises are tested. A broken promise lets the lender call the debt for the next close."""
    # (The bank is paid before the mezzanine lender: that is what ranking after the bank means.)
    for debt in _rows(conn, "SELECT * FROM empire_debts WHERE empire_id = %s AND status IN ('open', 'called', 'defaulted')"
                            " ORDER BY (kind = 'mezzanine'), id FOR UPDATE", (empire["id"],)):
        interest = _quarter_interest(debt)
        if interest:
            paid = ledger.pay_up_to(conn, payer=empire["account_id"], receiver=debt["lender_account"], wanted=interest, kind="empire_interest",
                                    memo=f"{empire['name']}: interest to {debt['lender_name']}", period=period)
            if paid:
                empires._book(conn, empire["id"], period, "Interest", f"Interest to {debt['lender_name']}", paid, True, now, kind="interest")
            if paid < interest:
                _default(conn, empire, debt, interest - paid, period, now, interest=True)
                debt = _one(conn, "SELECT * FROM empire_debts WHERE id = %s", (debt["id"],))
                if debt["status"] == "repaid":
                    continue
        if debt["status"] in ("called", "defaulted") or debt["due_period"] <= period:
            paid = ledger.pay_up_to(conn, payer=empire["account_id"], receiver=debt["lender_account"], wanted=debt["outstanding"],
                                    kind="empire_repayment", memo=f"{empire['name']}: repaid to {debt['lender_name']}", period=period)
            if paid < debt["outstanding"]:
                conn.execute("UPDATE empire_debts SET outstanding = outstanding - %s WHERE id = %s", (paid, debt["id"]))
                _default(conn, empire, {**debt, "outstanding": debt["outstanding"] - paid}, debt["outstanding"] - paid, period, now, interest=False)
            else:
                conn.execute("UPDATE empire_debts SET outstanding = 0, status = 'repaid' WHERE id = %s", (debt["id"],))
                _log(conn, empire["id"], f"The empire repaid {_money(debt['outstanding'])} to {debt['lender_name']}.", now)
            continue
        if "rate_step" in debt["traps"]:
            before = _one(conn, "SELECT worth FROM empire_worth WHERE empire_id = %s AND period = %s", (empire["id"], period - 1))
            if before and empires.worth(conn, empire, now)["total"] < before["worth"] and debt["breach_since"] is None:
                conn.execute("UPDATE empire_debts SET rate_bps = rate_bps + 300 WHERE id = %s", (debt["id"],))
                _log(conn, empire["id"], f"The empire's worth fell: under a clause nobody struck out, {debt['lender_name']} raised its rate by three points.", now)
        if debt["kind"] == "buyout":
            from simulation import firm_deals
            broken = firm_deals.covenant_test(conn, debt)       # the bank tests the company it lent against
        else:
            broken = covenant_test(conn, empire, debt, now)
        if broken:
            conn.execute("UPDATE empire_debts SET status = 'called', called_at = %s, breach_since = coalesce(breach_since, %s) WHERE id = %s",
                         (now, period, debt["id"]))
            _log(conn, empire["id"], f"A promise to {debt['lender_name']} is broken: {' '.join(broken)} The lender has called the debt: "
                                     f"{_money(debt['outstanding'])} must be repaid by the next close.", now)
            for hook in CALLED:
                hook(conn, empire, debt, broken, period, now)


def call_on_demand(conn: Connection, empire: dict, debt: dict, now: datetime) -> None:
    """A lender with the call-at-any-time clause in force calls its loan (an empire event)."""
    conn.execute("UPDATE empire_debts SET status = 'called', called_at = %s WHERE id = %s AND status = 'open'", (now, debt["id"]))


# ---------------------------------------------------------------------------
# A stake in the empire
# ---------------------------------------------------------------------------

def open_stake(conn: Connection, empire: dict, wanted: int, approval_id: int, doc: dict, now: datetime) -> dict:
    worth = empires.worth(conn, empire, now)["total"]
    if wanted > apply_bps(worth, STAKE_MOST_BPS):
        raise EmpireError(f"A stake offer may raise up to a quarter of the empire's worth: {_money(apply_bps(worth, STAKE_MOST_BPS))}.")
    if _one(conn, "SELECT 1 FROM empire_stake_offers WHERE empire_id = %s AND status = 'open'", (empire["id"],)):
        raise EmpireError("A stake offer is already open.")
    price = max(unit_price(conn, empire, now), 1)            # for showing: units are counted at each purchase from that moment's worth
    offer = _one(conn, "INSERT INTO empire_stake_offers (empire_id, wanted, unit_price, approval_id, traps, opened_at, closes_at)"
                       " VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING *",
                 (empire["id"], wanted, price, approval_id, doc["kept_traps"], now, now + timedelta(days=STAKE_DAYS)))
    _log(conn, empire["id"], f"The empire offered a stake in itself: up to {_money(wanted)}, open for {STAKE_DAYS} days to anybody.", now)
    return offer


def buy_stake(conn: Connection, player_id, offer_id: int, amount: int, now: datetime) -> dict:
    """Anybody may put money into an empire's stake offer, at the offer's price, for units."""
    with conn.transaction():
        state = _open(conn, now)
        offer = _one(conn, "SELECT * FROM empire_stake_offers WHERE id = %s FOR UPDATE", (offer_id,))
        if offer is None or offer["status"] != "open" or offer["closes_at"] <= now:
            raise EmpireError("That stake offer is not open.")
        empire = empires._empire(conn, offer["empire_id"], lock=True)
        if not firm._whole(amount, 1):
            raise EmpireError("An amount above nought, in kobo.")
        if empire["head_player_id"] == player_id:
            raise EmpireError("The head does not buy into their own offer. Put capital in as a member instead.")
        left = offer["wanted"] - offer["raised"]
        if amount > left:
            raise EmpireError(f"The offer has {_money(left)} left.")
        units = units_for(conn, empire, amount, now)                 # at this moment's worth: never at a stale price
        if units <= 0:
            raise EmpireError("That is too little to buy a unit.")
        try:
            ledger.transfer(conn, payer=ledger.player_account_id(conn, player_id), receiver=empire["account_id"], amount=amount,
                            kind="empire_capital", memo=f"{empire['name']}: a stake bought", period=state["period"], reference=f"stake:{offer_id}")
        except ledger.InsufficientFunds:
            raise EmpireError("You do not have that much cash.") from None
        conn.execute("INSERT INTO empire_capital (empire_id, player_id, amount, from_savings, at, period) VALUES (%s, %s, %s, 0, %s, %s)",
                     (empire["id"], player_id, amount, now, state["period"]))
        _add_units(conn, empire, player_id, units)
        conn.execute("INSERT INTO stake_buys (offer_id, player_id, units, paid, at) VALUES (%s, %s, %s, %s, %s)", (offer_id, player_id, units, amount, now))
        conn.execute("UPDATE empire_stake_offers SET raised = raised + %s WHERE id = %s", (amount, offer_id))
        return {"units": units, "paid": amount}


def _close_stakes(conn: Connection, now: datetime) -> None:
    for offer in _rows(conn, "SELECT * FROM empire_stake_offers WHERE status = 'open' AND closes_at <= %s", (now,)):
        empire = empires._empire(conn, offer["empire_id"])
        first_call = offer["raised"] if "first_call" in offer["traps"] else 0
        conn.execute("UPDATE empire_stake_offers SET status = 'closed', first_call_left = %s WHERE id = %s", (first_call, offer["id"]))
        _log(conn, offer["empire_id"], f"The stake offer closed: {_money(offer['raised'])} was put in.", now)
        if "cheap_units" in offer["traps"] and offer["raised"]:
            # A clause nobody struck out: the organiser of the offer (the pension funds, for a client) takes units for a tenth of
            # what was raised, at half their worth. The partners already in are diluted by it.
            buyer = ledger.account_id(conn, ledger.INVESTORS_INSTITUTIONS)
            pays = min(offer["raised"] // 20, max(ledger.balance(conn, buyer), 0))
            if pays > 0:
                units = units_for(conn, empire, pays * 2, now)
                ledger.transfer(conn, payer=buyer, receiver=empire["account_id"], amount=pays, kind="empire_capital",
                                memo=f"{empire['name']}: units taken by the offer's organiser at half their worth",
                                period=careers.world_now(conn, now)["period"], reference=f"stake:{offer['id']}:cheap")
                conn.execute("INSERT INTO empire_units (empire_id, holder_account, player_id, units) VALUES (%s, %s, NULL, %s)"
                             " ON CONFLICT (empire_id, holder_account) DO UPDATE SET units = empire_units.units + excluded.units",
                             (empire["id"], buyer, units))
                _log(conn, empire["id"], f"Under a clause nobody struck out, the offer's organiser took {units:,} units at half their worth.", now)
        if offer["raised"] >= naira(STAKE_LEAST_NAIRA):
            for hook in firm.RAISED:
                hook(conn, empire, {"kind": "stake", "amount": offer["raised"]}, now)


def stake_offers(conn: Connection, now: datetime) -> list[dict]:
    return [{"id": o["id"], "empire": o["name"], "wanted": o["wanted"], "raised": o["raised"], "unit_price": o["unit_price"], "closes_at": o["closes_at"]}
            for o in _rows(conn, "SELECT o.*, e.name FROM empire_stake_offers o JOIN empires e ON e.id = o.empire_id WHERE o.status = 'open'"
                                 " AND o.closes_at > %s ORDER BY o.id", (now,))]


# ---------------------------------------------------------------------------
# Dividends to the partners
# ---------------------------------------------------------------------------

def last_profit(conn: Connection, empire_id) -> tuple[int | None, int]:
    row = _one(conn, "SELECT period, figures FROM empire_accounts WHERE empire_id = %s ORDER BY period DESC LIMIT 1", (empire_id,))
    return (row["period"], int(row["figures"]["profit"])) if row else (None, 0)


def _dividend_check(conn: Connection, empire: dict, payload: dict, now: datetime) -> dict:
    amount = payload.get("amount")
    if not firm._whole(amount, 1):
        raise EmpireError("Name the payout, in kobo.")
    period, profit = last_profit(conn, empire["id"])
    if period is None or profit <= 0:
        raise EmpireError("A dividend is paid out of profit. The empire made none in its last closed quarter.")
    paid = _one(conn, "SELECT coalesce(sum(amount), 0)::bigint AS n FROM empire_payouts WHERE empire_id = %s AND period = %s",
                (empire["id"], careers.world_now(conn, now)["period"]))["n"]
    most = apply_bps(profit, DIVIDEND_MOST_BPS) - paid
    if amount > most:
        raise EmpireError(f"A payout may be up to half of the last quarter's profit: {_money(max(most, 0))} is left.")
    return {"amount": amount, "profit": profit, "profit_period": period}


def _dividend_carry(conn: Connection, empire: dict, resolution: dict, now: datetime) -> str:
    amount = resolution["payload"]["amount"]
    _dividend_check(conn, empire, {"amount": amount}, now)              # checked again: the figures may have changed while the vote ran
    state = careers.world_now(conn, now)
    ensure_units(conn, empire)
    holders = _rows(conn, "SELECT holder_account, units FROM empire_units WHERE empire_id = %s AND units > 0", (empire["id"],))
    total = sum(h["units"] for h in holders)
    if not total:
        raise EmpireError("The empire has no partners to pay.")
    if ledger.balance(conn, empire["account_id"]) < amount:
        raise EmpireError("The empire has not that much cash.")
    share = {h["holder_account"]: amount * h["units"] // total for h in holders}
    first = _one(conn, "SELECT * FROM empire_stake_offers WHERE empire_id = %s AND first_call_left > 0 ORDER BY id LIMIT 1 FOR UPDATE", (empire["id"],))
    if first:
        # A clause nobody struck out: the partners who came in by that offer are paid first, until they have their money back.
        buys = _rows(conn, "SELECT player_id, sum(paid)::bigint AS paid FROM stake_buys WHERE offer_id = %s GROUP BY player_id", (first["id"],))
        put = sum(b["paid"] for b in buys)
        first_pay = min(amount, first["first_call_left"])
        share = {ledger.player_account_id(conn, b["player_id"]): first_pay * b["paid"] // put for b in buys} if put else {}
        rest = amount - sum(share.values())
        for h in holders:
            share[h["holder_account"]] = share.get(h["holder_account"], 0) + rest * h["units"] // total
        conn.execute("UPDATE empire_stake_offers SET first_call_left = first_call_left - %s WHERE id = %s", (first_pay, first["id"]))
    paid = ledger.pay_split_up_to(conn, payer=empire["account_id"], amounts=share, kind="empire_dividend",
                                  memo=f"{empire['name']}: dividend to the partners", period=state["period"])
    conn.execute("INSERT INTO empire_payouts (empire_id, period, amount, units, resolution_id, at) VALUES (%s, %s, %s, %s, %s, %s)",
                 (empire["id"], state["period"], paid, total, resolution["id"], now))
    return f"{_money(paid)} was paid to the partners, in proportion to their units."


# ---------------------------------------------------------------------------
# The treasury policy: how the empire's money is split
# ---------------------------------------------------------------------------
POLICY_DEFAULT = {"cash_least_bps": 1000, "shares_most_bps": 6000}


def mix(conn: Connection, empire: dict, now: datetime) -> dict:
    from simulation import objectives
    have = objectives.wealth(conn, empire["account_id"], now)
    total = max(have["total"], 1)
    return {"cash": have["cash"], "bonds": have["bonds"], "shares": have["shares"], "total": have["total"],
            "cash_bps": have["cash"] * BPS // total, "bonds_bps": have["bonds"] * BPS // total, "shares_bps": have["shares"] * BPS // total}


def policy(conn: Connection, empire_id) -> dict:
    return {**POLICY_DEFAULT, **(firm.article(conn, empire_id, "treasury") or {})}


def policy_breaches(conn: Connection, empire: dict, now: datetime, extra_shares: int = 0) -> list[str]:
    rule, have = policy(conn, empire["id"]), mix(conn, empire, now)
    total = max(have["total"], 1)
    out = []
    if (have["shares"] + extra_shares) * BPS > rule["shares_most_bps"] * total:
        out.append(f"shares would be more than {rule['shares_most_bps'] / 100:.0f}% of the empire")
    if (have["cash"] - extra_shares) * BPS < rule["cash_least_bps"] * total:
        out.append(f"cash would be less than {rule['cash_least_bps'] / 100:.0f}% of the empire")
    return out


def _treasury_check(conn: Connection, empire: dict, payload: dict, now: datetime) -> dict:
    cash, shares = payload.get("cash_least_bps"), payload.get("shares_most_bps")
    if not firm._whole(cash, 0, 5000) or not firm._whole(shares, 0, BPS) or cash + shares > BPS + 5000:
        raise EmpireError("Cash at least 0% to 50%; shares at most 0% to 100%.")
    return {"cash_least_bps": cash, "shares_most_bps": shares}


def _treasury_carry(conn: Connection, empire: dict, resolution: dict, now: datetime) -> str:
    firm.set_article(conn, empire["id"], "treasury", resolution["payload"], resolution["period"], now, resolution["id"])
    p = resolution["payload"]
    return f"The treasury policy is now: cash at least {p['cash_least_bps'] / 100:.0f}%, shares at most {p['shares_most_bps'] / 100:.0f}%."


def _risk_appetite_check(conn: Connection, empire: dict, payload: dict, now: datetime) -> dict:
    loss = payload.get("worst_year_bps")
    if not firm._whole(loss, 100, 5000):
        raise EmpireError("The most the empire will accept losing in a bad year: from 1% to 50%.")
    return {"worst_year_bps": loss}


def _risk_appetite_carry(conn: Connection, empire: dict, resolution: dict, now: datetime) -> str:
    firm.set_article(conn, empire["id"], "risk_appetite", resolution["payload"], resolution["period"], now, resolution["id"])
    return f"The empire's risk appetite: it will accept losing up to {resolution['payload']['worst_year_bps'] / 100:.0f}% in a bad year."


# ---------------------------------------------------------------------------
# Budgets, and each desk's spending
# ---------------------------------------------------------------------------

def set_budgets(conn: Connection, head_id, budgets: dict, now: datetime) -> None:
    """The head gives each desk its budget for the running quarter. What a desk spends is counted against it."""
    with conn.transaction():
        state = _open(conn, now)
        empire = empires._head(conn, head_id)
        if not isinstance(budgets, dict) or not budgets:
            raise EmpireError("Give each desk an amount.")
        total = 0
        for desk, amount in budgets.items():
            if desk not in firm.DESKS or not firm._whole(amount, 0):
                raise EmpireError("A budget is a whole amount for one of the desks.")
            total += amount
        if total > ledger.balance(conn, empire["account_id"]):
            raise EmpireError("The budgets add up to more than the empire's cash.")
        for desk, amount in budgets.items():
            conn.execute("INSERT INTO empire_budgets (empire_id, period, desk, amount, set_by, at) VALUES (%s, %s, %s, %s, %s, %s)"
                         " ON CONFLICT (empire_id, period, desk) DO UPDATE SET amount = excluded.amount, set_by = excluded.set_by, at = excluded.at",
                         (empire["id"], state["period"], desk, amount, head_id, now))
        _log(conn, empire["id"], f"The head set the desks' budgets for the quarter: {_money(total)} in all.", now)


def budget_of(conn: Connection, empire_id, period: int, desk: str) -> int | None:
    row = _one(conn, "SELECT amount FROM empire_budgets WHERE empire_id = %s AND period = %s AND desk = %s", (empire_id, period, desk))
    return row["amount"] if row else None


def spent_by(conn: Connection, empire_id, period: int, desk: str) -> int:
    """What a desk spent in a quarter: its costs, its staff and its share of the task work. What a
    thief took, disguised as the desk's cost, counts too: that is how a budget shows something wrong."""
    return _one(conn, "SELECT coalesce(sum(amount), 0)::bigint AS n FROM empire_books WHERE empire_id = %s AND period = %s AND desk = %s",
                (empire_id, period, desk))["n"]


def _desk_of_book(seat: dict | None, kind: str, build: str | None = None) -> str | None:
    if build:
        return build
    if seat is None:
        return None
    return "head" if seat["head_player_id"] == seat["player_id"] else seat["build"]


def needs_countersign(conn: Connection, empire_id, player_id, amount: int, period: int) -> bool:
    """A cost waits for the Accountant's desk when, with what the member has already signed this quarter, it passes the threshold."""
    return empires._spent(conn, empire_id, player_id, period) + amount > naira(EXPENSE_APPROVAL_NAIRA)


def sign_cost(conn: Connection, player_id, purpose: str, amount: int, member_id, now: datetime) -> dict:
    """A member signs a genuine cost for their desk: training for a member of the empire. It goes into
    the books under the desk's ordinary heading, as any cost of the desk does; above the threshold it
    waits for the Accountant's desk, which sees the heading and the amount, as for any other cost."""
    with conn.transaction():
        state = _open(conn, now)
        seat, empire = firm._active(conn, player_id)
        if purpose != "training":
            raise EmpireError("A desk may sign for training.")
        if not firm._whole(amount, naira(10_000)):
            raise EmpireError("Training costs at least ₦10,000.")
        target = member_id or player_id
        member = empires.seat_of(conn, target)
        if member is None or member["empire_id"] != empire["id"]:
            raise EmpireError("Training is for a member of your empire.")
        desk = _desk_of_book(seat, "cost")
        category, description = empires.data.DISGUISES[desk]
        payload = {"purpose": purpose, "member_id": str(target), "desk": desk, "category": category, "description": description}
        limit, used = empires.signing_limit(conn, seat), empires._spent(conn, empire["id"], player_id, state["period"])
        if used + amount > limit:
            raise EmpireError(f"Your signing limit for the quarter is {_money(limit)}, of which {_money(used)} is used.")
        if firm.player_run(empire) and needs_countersign(conn, empire["id"], player_id, amount, state["period"]):
            approval = firm.ask(conn, empire, kind="expense", desk="accountant", asked_by=player_id, title=f"{category}: {_money(amount)}",
                                amount=amount, payload=payload, period=state["period"], now=now)
            return {"waiting": True, "approval_id": approval["id"]}
        _pay_cost(conn, empire, player_id, amount, payload, state["period"], now)
        return {"waiting": False}


def _pay_cost(conn: Connection, empire: dict, player_id, amount: int, payload: dict, period: int, now: datetime) -> None:
    seat = empires.seat_of(conn, player_id)
    if seat is None or seat["empire_id"] != empire["id"]:
        raise EmpireError("Whoever signed it is no longer in the empire.")
    limit, used = empires.signing_limit(conn, seat), empires._spent(conn, empire["id"], player_id, period, waiting=False)
    if used + amount > limit:
        raise EmpireError(f"The signing limit for the quarter is {_money(limit)}, of which {_money(used)} is used.")
    households = _one(conn, "SELECT account_id FROM households ORDER BY location LIMIT 1")
    try:
        ledger.transfer(conn, payer=empire["account_id"], receiver=households["account_id"], amount=amount, kind="empire_expense",
                        memo=f"{empire['name']}: training", period=period)
    except ledger.InsufficientFunds:
        raise EmpireError("The empire has not that much cash.") from None
    category, description = empires.data.DISGUISES[payload.get("desk") or "head"]
    empires._book(conn, empire["id"], period, category, description, amount, True, now, entered_by=player_id, desk=payload.get("desk"))
    member = payload["member_id"]
    mseat = empires.seat_of(conn, member)
    if mseat and mseat["empire_id"] == empire["id"]:
        trained = _one(conn, "SELECT coalesce(sum(amount), 0)::bigint AS n FROM empire_books WHERE empire_id = %s AND period = %s"
                             " AND kind = 'cost' AND genuine AND entered_by IS NOT NULL", (empire["id"], period))["n"]
        room = max(TRAINING_MOST_EXPERIENCE - (trained - amount) // naira(TRAINING_EXPERIENCE_PER_NAIRA), 0)
        gain = min(amount // naira(TRAINING_EXPERIENCE_PER_NAIRA), room)
        if gain:
            careers.add_experience(conn, member, mseat["build"], gain, now)


def _expense_view(conn: Connection, approval: dict, viewer_id, now: datetime) -> dict:
    """What the Accountant sees of a cost waiting for approval: the heading and description it would
    go into the books under, the amount, and the desk's budget. Not whether it is genuine."""
    p = approval["payload"]
    desk = p.get("desk") or "head"
    period = approval["period"]
    return {"heading": p.get("category"), "description": p.get("description"),
            "desk": firm.DESK_NAMES.get(desk, desk), "budget": budget_of(conn, approval["empire_id"], period, desk),
            "spent": spent_by(conn, approval["empire_id"], period, desk)}


def _expense_execute(conn: Connection, approval: dict, now: datetime) -> None:
    empire = empires._empire(conn, approval["empire_id"], lock=True)
    p = approval["payload"]
    if p.get("diverted"):
        _divert_now(conn, empire, approval, now)
    else:
        _pay_cost(conn, empire, approval["asked_by"], approval["amount"], p, careers.world_now(conn, now)["period"], now)


def _divert_now(conn: Connection, empire: dict, approval: dict, now: datetime) -> None:
    """A cost that is not what it says, approved: the money goes to whoever asked."""
    seat = empires.seat_of(conn, approval["asked_by"])
    if seat is None or seat["empire_id"] != empire["id"]:
        raise EmpireError("Whoever signed it is no longer in the empire.")
    period = careers.world_now(conn, now)["period"]
    limit, used = empires.signing_limit(conn, seat), empires._spent(conn, empire["id"], approval["asked_by"], period, waiting=False)
    if used + approval["amount"] > limit:
        raise EmpireError(f"The signing limit for the quarter is {_money(limit)}.")
    try:
        ledger.transfer(conn, payer=empire["account_id"], receiver=ledger.player_account_id(conn, approval["asked_by"]), amount=approval["amount"],
                        kind="empire_expense", memo=f"{empire['name']}: {approval['payload']['category'].lower()}", period=period)
    except ledger.InsufficientFunds:
        raise EmpireError("The empire has not that much cash.") from None
    mine = careers.career(conn, approval["asked_by"], seat["build"])
    empires._book(conn, empire["id"], period, approval["payload"]["category"], approval["payload"]["description"], approval["amount"], False, now,
                  entered_by=approval["asked_by"], thief_level=mine["level"] if mine else 1, desk=approval["payload"]["desk"])


def divert_needs_approval(conn: Connection, seat: dict, amount: int, now: datetime) -> dict | None:
    """Called by the shadow feature: a cost above the threshold in an empire run by players goes to
    the Accountant's desk like any other. Returns the request, or None if it may go through at once."""
    empire = empires._empire(conn, seat["empire_id"])
    state = careers.world_now(conn, now)
    # In an empire the computer runs, nobody sets budgets and the staff approve every cost: it goes straight through, as it always did.
    # Otherwise the threshold counts what the member has already signed this quarter, so a cost split into pieces still waits;
    # and an Accountant's own cost waits for the other Accountant, or for the head.
    if empire["kind"] != "player" or empire["head_player_id"] is None or not needs_countersign(conn, empire["id"], seat["player_id"], amount, state["period"]):
        return None
    category, description = empires.data.DISGUISES["head" if seat["head_player_id"] == seat["player_id"] else seat["build"]]
    desk = "head" if seat["head_player_id"] == seat["player_id"] else seat["build"]
    return firm.ask(conn, empire, kind="expense", desk="accountant", asked_by=seat["player_id"], title=f"{category}: {_money(amount)}",
                    amount=amount, payload={"category": category, "description": description, "desk": desk, "diverted": True},
                    period=state["period"], now=now)


def _staff_expense_rule(conn: Connection, approval: dict, now: datetime) -> tuple[bool, str]:
    """The staff approve a cost if the desk's budget allows it. They cannot tell what is not genuine."""
    p = approval["payload"]
    desk = p.get("desk") or "head"
    budget = budget_of(conn, approval["empire_id"], approval["period"], desk)
    if budget is not None and spent_by(conn, approval["empire_id"], approval["period"], desk) + approval["amount"] > budget:
        return False, "It would take the desk over its budget."
    return True, "Within the desk's budget."


def _scorecard(conn: Connection, empire: dict, build: str, period: int, card: dict) -> dict:
    budget = budget_of(conn, empire["id"], period, build)
    spent = spent_by(conn, empire["id"], period, build)
    out = {"budget": budget or 0, "spent": spent, "notes": []}
    if budget is not None and spent > budget:
        out["adjust"] = -10
        out["notes"].append(f"Over budget by {_money(spent - budget)}.")
    elif budget:
        out["notes"].append(f"Under budget by {_money(budget - spent)}.")
    return out


def _bonus_pools(conn: Connection, empire: dict, period: int, now: datetime) -> None:
    """A desk that did its duties well and spent less than its budget earns a pool for its members:
    a fifth of what it did not spend, inside the head's bonus limit."""
    if not firm.player_run(empire):
        return
    paid_already = _one(conn, "SELECT coalesce(sum(amount), 0)::bigint AS n FROM empire_books WHERE empire_id = %s AND period = %s AND kind = 'bonus'",
                        (empire["id"], period))["n"]
    room = max(empires.bonus_limit(conn, empire, now) - paid_already, 0)
    for row in _rows(conn, "SELECT desk, amount FROM empire_budgets WHERE empire_id = %s AND period = %s AND desk <> 'head' ORDER BY desk",
                     (empire["id"], period)):
        spent = spent_by(conn, empire["id"], period, row["desk"])
        score = _one(conn, "SELECT coalesce(avg(score), 0)::int AS s FROM desk_duties WHERE empire_id = %s AND build = %s AND period = %s"
                           " AND status = 'done' AND NOT by_staff", (empire["id"], row["desk"], period))["s"]
        members = firm.desk_members(conn, empire["id"], row["desk"])
        if spent >= row["amount"] or score < firm.DUTY_PASS or not members:
            continue
        pool = min(apply_bps(row["amount"] - spent, POOL_SHARE_BPS), room)
        # A member whose contract promises a share of the desk's pool is paid that first; the rest is shared equally.
        promised = {m: apply_bps(pool, c["bonus_bps"]) for m in members if (c := _one(conn, "SELECT bonus_bps FROM member_contracts WHERE empire_id = %s"
                                                                                   " AND player_id = %s AND status = 'signed'", (empire["id"], m)))}
        left = max(pool - sum(promised.values()), 0)
        for member in members:
            each = promised.get(member, 0) + left // len(members)
            if each <= 0:
                continue
            got = ledger.pay_up_to(conn, payer=empire["account_id"], receiver=ledger.player_account_id(conn, member), wanted=each,
                                   kind="empire_bonus", memo=f"{empire['name']}: the desk's pool for coming in under budget", period=period)
            if got:
                empires._book(conn, empire["id"], period, "Bonuses", "The desk's pool for coming in under budget", got, True, now, kind="bonus",
                              desk=row["desk"])
                room -= got
        if pool:
            _log(conn, empire["id"], f"The {firm.DESK_NAMES[row['desk']]} desk came in under budget and earned a pool of {_money(pool)}.", now)


# ---------------------------------------------------------------------------
# The bonus pool the Accountant proposes and the head approves
# ---------------------------------------------------------------------------

def propose_bonuses(conn: Connection, player_id, shares: dict, now: datetime) -> dict:
    """The Accountant proposes who gets what from the quarter's bonus pool. The head approves."""
    with conn.transaction():
        state = _open(conn, now)
        seat, empire = firm._active(conn, player_id)
        if seat["build"] != "accountant":
            raise EmpireError("The bonus pool is proposed by the empire's Accountant.")
        if not firm.player_run(empire):
            raise EmpireError("An empire run by the computer pays no bonuses.")
        members = {str(h["player_id"]): h for h in empires.humans(conn, empire["id"])}
        clean, total = {}, 0
        for member, amount in (shares or {}).items():
            if member not in members or not firm._whole(amount, 1) or member == str(empire["head_player_id"]):
                raise EmpireError("Each share of the pool goes to a member (not the head), as a whole amount.")
            clean[member] = amount
            total += amount
        if not clean:
            raise EmpireError("Name at least one member.")
        most = empires.bonus_limit(conn, empire, now)
        if total > most:
            raise EmpireError(f"The pool may not pass the head's bonus limit of {_money(most)}.")
        approval = firm.ask(conn, empire, kind="bonus_pool", desk="head", asked_by=player_id, title=f"The quarter's bonus pool: {_money(total)}",
                            amount=total, payload={"shares": clean}, period=state["period"], now=now)
        return {"approval_id": approval["id"]}


def _bonus_pool_view(conn: Connection, approval: dict, viewer_id, now: datetime) -> dict:
    return {"lines": [{"name": firm._name(conn, member), "amount": amount} for member, amount in approval["payload"]["shares"].items()]}


def _bonus_pool_execute(conn: Connection, approval: dict, now: datetime) -> None:
    empire = empires._empire(conn, approval["empire_id"])
    for member, amount in approval["payload"]["shares"].items():
        seat = empires.seat_of(conn, member)
        if seat is None or seat["empire_id"] != empire["id"]:
            continue
        _pay_bonus_inside(conn, empire, member, amount, "From the quarter's bonus pool", now)


def _pay_bonus_inside(conn: Connection, empire: dict, member_id, amount: int, why: str, now: datetime) -> None:
    state = careers.world_now(conn, now)
    most = empires.bonus_limit(conn, empire, now)
    paid = _one(conn, "SELECT coalesce(sum(amount), 0)::bigint AS total FROM empire_books WHERE empire_id = %s AND period = %s AND kind = 'bonus'",
                (empire["id"], state["period"]))["total"]
    if paid + amount > most:
        raise EmpireError(f"Bonuses may not pass {_money(most)} in a quarter; {_money(paid)} is paid.")
    try:
        ledger.transfer(conn, payer=empire["account_id"], receiver=ledger.player_account_id(conn, member_id), amount=amount, kind="empire_bonus",
                        memo=f"{empire['name']}: bonus", period=state["period"])
    except ledger.InsufficientFunds:
        raise EmpireError("The empire has not that much cash.") from None
    empires._book(conn, empire["id"], state["period"], "Bonuses", why, amount, True, now, kind="bonus")


# ---------------------------------------------------------------------------
# The empire's own quarterly accounts
# ---------------------------------------------------------------------------

def accounts_for(conn: Connection, empire: dict, period: int, now: datetime) -> dict:
    """What the empire's accounts for a quarter say: what it was worth at the start and the end, what
    came in and went out, and the profit (the change in worth, less capital put in, plus what was paid out)."""
    before = _one(conn, "SELECT worth FROM empire_worth WHERE empire_id = %s AND period = %s", (empire["id"], period - 1))
    have = empires.worth(conn, empire, now)
    opening = before["worth"] if before else 0
    capital = _one(conn, "SELECT coalesce(sum(amount), 0)::bigint AS n FROM empire_capital WHERE empire_id = %s AND period = %s",
                   (empire["id"], period))["n"]
    payouts = _one(conn, "SELECT coalesce(sum(amount), 0)::bigint AS n FROM empire_payouts WHERE empire_id = %s AND period = %s",
                   (empire["id"], period))["n"]
    costs = {r["category"]: r["n"] for r in _rows(conn, "SELECT category, sum(amount)::bigint AS n FROM empire_books WHERE empire_id = %s"
                                                        " AND period = %s GROUP BY category ORDER BY category", (empire["id"], period))}
    received = ledger.received_in_period(conn, empire["account_id"], period, ("dividend", "bond_coupon", "coupon", "bond_interest"))
    profit = have["total"] - opening - capital + payouts
    return {"opening": opening, "closing": have["total"], "cash": have["cash"], "shares": have["shares"], "bonds": have["bonds"],
            "debt": have.get("debt", 0), "capital_in": capital, "paid_out": payouts, "costs": costs, "total_costs": sum(costs.values()),
            "income_received": received, "profit": profit}


def _close_accounts(conn: Connection, empire: dict, period: int, now: datetime) -> None:
    figures = accounts_for(conn, empire, period, now)
    conn.execute("INSERT INTO empire_accounts (empire_id, period, figures) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                 (empire["id"], period, firm._json(figures)))


# ---------------------------------------------------------------------------
# What a member sees
# ---------------------------------------------------------------------------

def view(conn: Connection, seat: dict, empire: dict, state: dict, now: datetime) -> dict:
    is_head = empire["head_player_id"] == seat["player_id"]
    owned = _owned(conn, empire, now)
    debts_now = [{"id": d["id"], "kind": d["kind"], "lender": d["lender_name"], "principal": d["principal"], "outstanding": d["outstanding"],
                  "rate_bps": d["rate_bps"], "due": clock.period_label(d["due_period"]), "status": d["status"],
                  "traps": [TRAP_NAMES.get(t, t) for t in d["traps"]], "interest_a_quarter": _quarter_interest(d),
                  "broken": covenant_test(conn, empire, d, now) if d["status"] == "open" else []}
                 for d in debts(conn, empire["id"]) if d["status"] in ("open", "called", "defaulted")]
    accounts = _rows(conn, "SELECT period, figures FROM empire_accounts WHERE empire_id = %s ORDER BY period DESC LIMIT 4", (empire["id"],))
    budgets = {r["desk"]: r["amount"] for r in _rows(conn, "SELECT desk, amount FROM empire_budgets WHERE empire_id = %s AND period = %s",
                                                     (empire["id"], state["period"]))}
    _p, profit = last_profit(conn, empire["id"])
    return {
        "owned": owned, "owed": firm.debt_of(conn, empire["id"]), "borrow_room": gearing_room(conn, empire, now),
        "debts": debts_now, "policy": policy(conn, empire["id"]), "mix": mix(conn, empire, now),
        "breaches": policy_breaches(conn, empire, now),
        "risk_appetite": firm.article(conn, empire["id"], "risk_appetite"),
        "partners": [{**p, "player_id": None, "you": p["player_id"] == seat["player_id"]} for p in partners(conn, empire, now)]
        if empire["kind"] == "player" else [],
        "unit_price": unit_price(conn, empire, now) if empire["kind"] == "player" else None,
        "stake_offer": next((o for o in stake_offers(conn, now) if o["empire"] == empire["name"]), None),
        "accounts": [{"period": a["period"], "label": clock.period_label(a["period"]), **a["figures"]} for a in accounts],
        "dividend_room": max(apply_bps(profit, DIVIDEND_MOST_BPS), 0),
        "budgets": [{"desk": d, "name": firm.DESK_NAMES[d], "budget": budgets.get(d), "spent": spent_by(conn, empire["id"], state["period"], d)}
                    for d in firm.DESKS],
        "can_set_budgets": is_head, "expense_threshold": naira(EXPENSE_APPROVAL_NAIRA),
        "limits": {"debt_most_bps": DEBT_MOST_BPS, "dividend_most_bps": DIVIDEND_MOST_BPS, "loan_spread_bps": LOAN_SPREAD_BPS,
                   "bond_spread_bps": BOND_SPREAD_BPS, "terms": list(TERMS), "policy_rate_bps": state["policy_rate_bps"],
                   "loan_least": naira(LOAN_LEAST_NAIRA), "bond_least": naira(BOND_LEAST_NAIRA)},
        "can_design": seat["build"] == "investment_banker" or is_head,
        "can_propose_bonuses": seat["build"] == "accountant",
    }


# ---------------------------------------------------------------------------
# Hooks
# ---------------------------------------------------------------------------
CALLED: list = []           # (conn, empire, debt, broken, period, now)


def _close(conn: Connection, empire: dict, period: int, now: datetime) -> None:
    if empire["kind"] == "player":
        ensure_units(conn, empire)
    _close_debts(conn, empire, period, now)
    _bonus_pools(conn, empire, period, now)


def _closed_accounts(conn: Connection, period: int, now: datetime) -> None:
    for row in _rows(conn, "SELECT id FROM empires WHERE status = 'active' AND kind <> 'pension' ORDER BY id"):
        with conn.transaction():
            _close_accounts(conn, empires._empire(conn, row["id"]), period, now)


def _bell(conn: Connection, now: datetime) -> None:
    with conn.transaction():
        _close_stakes(conn, now)


firm.EXECUTORS.update({"raise_check": _raise_checked, "raise_risk": _raise_risked, "raise_sign": _raise_signed,
                       "expense": _expense_execute, "bonus_pool": _bonus_pool_execute})
firm.REFUSERS.update({"raise_check": _raise_dropped, "raise_risk": _raise_dropped, "raise_sign": _raise_dropped})
firm.STAFF_RULES.update({"raise_check": _staff_raise_rule, "raise_risk": _staff_raise_rule, "expense": _staff_expense_rule})
firm.VIEWERS.update({"raise_check": _raise_view, "raise_risk": _raise_view, "raise_sign": _raise_view, "expense": _expense_view,
                     "bonus_pool": _bonus_pool_view})
firm.DOCUMENT_READ.append(_raise_read)
firm.DOCUMENT_DROPPED.append(_raise_doc_dropped)
firm.SCORECARD.append(_scorecard)
firm.CLOSE.append(_close)
firm.BELL.append(_bell)
firm.VIEW["money"] = view
firm.REASON_KINDS = (*firm.REASON_KINDS, "raise_risk")
firm.RESOLUTIONS.update({
    "dividend": firm.Resolution("dividend", "Pay a dividend to the partners", lambda seat, head: head or seat["build"] == "accountant",
                                _dividend_check, _dividend_carry, lambda p: f"Pay {_money(p['amount'])} to the partners as a dividend", big=True),
    "treasury": firm.Resolution("treasury", "Set the treasury policy", lambda seat, head: head or seat["build"] in ("asset_manager", "risk_manager"),
                                _treasury_check, _treasury_carry,
                                lambda p: f"Keep cash at least {p['cash_least_bps'] / 100:.0f}% and shares at most {p['shares_most_bps'] / 100:.0f}%",
                                big=True),
    "risk_appetite": firm.Resolution("risk_appetite", "Set the risk appetite", lambda seat, head: head or seat["build"] == "risk_manager",
                                     _risk_appetite_check, _risk_appetite_carry,
                                     lambda p: f"Accept losing up to {p['worst_year_bps'] / 100:.0f}% in a bad year"),
})
firm.ARTICLE_DEFAULTS.update({"treasury": POLICY_DEFAULT, "risk_appetite": {"worst_year_bps": 1500}})
firm.CLOSED.insert(0, _closed_accounts)


# ---------------------------------------------------------------------------
# The gap stage, Part 3: empire-paid work above what is left of a desk's budget waits for the head
# ---------------------------------------------------------------------------

def committed_to_work(conn: Connection, empire: dict, period: int, desk: str) -> int:
    """What the desk has taken on this quarter in work the empire pays for (rewards, paid or still to pay), by the build
    each piece was taken under: members who have since left or moved still count."""
    return _one(conn, """
        SELECT coalesce(sum(o.reward), 0)::bigint AS n FROM objectives o
        WHERE o.payer_account_id = %s AND o.period = %s AND o.state IN ('active', 'passed') AND NOT o.terms ? 'step_id'
          AND o.build = %s AND o.player_id IS DISTINCT FROM %s""",
                (empire["account_id"], period, desk, empire["head_player_id"]))["n"]


def objectives_error(words: str):
    from simulation import objectives
    return objectives.ObjectiveError(words)


def work_over_budget(conn: Connection, player_id, code: str, title: str, reward: int, period: int, now: datetime) -> dict | None:
    """Inside objectives.accept: if this work would take the member's desk past what is left of its budget for the
    quarter, ask the head and return what to tell the member; otherwise None. The head's own work never waits."""
    seat = empires.seat_of(conn, player_id)
    if seat is None:
        return None
    # (The empire's row is locked: two members of a desk asking at once are counted one after the other.)
    empire = _one(conn, "SELECT * FROM empires WHERE id = %s FOR UPDATE", (seat["empire_id"],))
    if empire["head_player_id"] == player_id or not firm.player_run(empire):
        return None
    desk = seat["build"]
    budget = budget_of(conn, empire["id"], period, desk)
    if budget is None:
        return None
    used = spent_by(conn, empire["id"], period, desk) + committed_to_work(conn, empire, period, desk)
    if used + reward <= budget:
        return None
    asked = _one(conn, "SELECT status FROM empire_approvals WHERE empire_id = %s AND kind = 'empire_work' AND period = %s"
                       " AND asked_by = %s AND payload->>'code' = %s AND status IN ('waiting', 'refused') ORDER BY id DESC LIMIT 1",
                 (empire["id"], period, player_id, code))
    if asked and asked["status"] == "waiting":
        return {"waiting": True, "words": "Your request for this work is already with the head."}
    if asked:
        raise objectives_error("The head refused this work this quarter. It may be asked for again next quarter.")
    approval = firm.ask(conn, empire, kind="empire_work", desk="head", asked_by=player_id, title=f"Work above the desk's budget: {title}",
                        amount=reward, payload={"code": code, "member_id": str(player_id), "desk": desk, "budget": budget, "used": used},
                        period=period, now=now)
    _log(conn, empire["id"], f"A member asked to take on {title} ({_money(reward)}), past what is left of the "
                             f"{firm.DESK_NAMES.get(desk, desk)}'s budget. It waits for the head.", now)
    return {"waiting": True, "approval_id": approval["id"],
            "words": f"That would take your desk past its budget for the quarter ({_money(used)} of {_money(budget)} used). "
                     f"The head has been asked to approve it."}


def _execute_work(conn: Connection, approval: dict, now: datetime) -> None:
    from simulation import objectives
    p = approval["payload"]
    if careers.world_now(conn, now)["period"] != approval["period"]:
        # A budget is for one quarter: approval given after it closed would let work past the next quarter's budget too.
        raise EmpireError("That request was for a quarter that has closed. The member may ask again this quarter.")
    seat = empires.seat_of(conn, approval["asked_by"])
    if seat is None or seat["empire_id"] != approval["empire_id"] or seat["build"] != p.get("desk"):
        raise EmpireError("The member no longer sits at that desk of the empire: the request lapses.")
    try:
        objectives.accept(conn, approval["asked_by"], p["code"], now, approved=True)
    except objectives.ObjectiveError as refused:
        raise EmpireError(f"Approved, but the work could not be taken on now: {refused}") from None


def _work_view(conn: Connection, approval: dict, viewer_id, now: datetime) -> dict:
    """What the head sees: the desk's budget and what is used of it now, and every other request of the desk still waiting."""
    p = approval["payload"]
    desk = p.get("desk")
    empire = empires._empire(conn, approval["empire_id"])
    budget = budget_of(conn, empire["id"], approval["period"], desk) or 0
    used = spent_by(conn, empire["id"], approval["period"], desk) + committed_to_work(conn, empire, approval["period"], desk)
    others = _one(conn, "SELECT count(*) AS n, coalesce(sum(amount), 0)::bigint AS a FROM empire_approvals WHERE empire_id = %s AND kind = 'empire_work'"
                        " AND status = 'waiting' AND id <> %s AND payload->>'desk' = %s", (empire["id"], approval["id"], desk))
    lines = [f"For the {firm.DESK_NAMES.get(desk, desk)} desk, whose budget for the quarter is {_money(budget)}",
             f"{_money(used)} of it is spent or promised now; this work would pay {_money(approval['amount'])}"]
    if others["n"]:
        lines.append(f"{others['n']} other request{'s' if others['n'] != 1 else ''} from the desk wait too, for {_money(others['a'])}")
    lines.append("Approve to let the member take it on; refuse and it is not taken")
    return {"why": lines}


def _work_staff(conn: Connection, approval: dict, now: datetime) -> tuple:
    return False, "Only the head (or, after two days, the deputy) approves work past a desk's budget."


firm.EXECUTORS["empire_work"] = _execute_work
firm.VIEWERS["empire_work"] = _work_view
firm.STAFF_RULES["empire_work"] = _work_staff
