"""Pension funds run by players (design document, section 13; added by the owner in Stage 6).

An Asset Manager who has reached Level 20 may open a pension fund. Other players may move their
retirement savings into it. From then on the savings are real money in the fund's own account in
the ledger, and the manager invests it in shares and bonds on the same market as everybody else.

A saver owns units of the fund. A unit is worth the fund's whole value divided by the units in
issue, so every saver gains and loses in the same proportion, and nobody can join or leave at a
price that takes from the others.

A fund keeps books and is audited exactly as an empire is, and a manager who takes its money is
dealt with in the same way: the regulator audits every fund each quarter, any saver may hire the
AI audit in an audit season, and a manager proved to have taken money repays it with a fine and
is struck off. A saver can always ask for their savings back; they are paid as the fund has cash,
and the regulator sells what the fund holds if the manager will not.
"""

from __future__ import annotations

from datetime import datetime

from psycopg import Connection, errors
from psycopg.rows import dict_row

from simulation import bonds, careers, clock, empires, exchange, ledger, marketview, objectives
from simulation import world_data as data
from simulation.money import BPS, apply_bps, naira

UNIT = 1_000_000                       # unit prices are kept in millionths of a kobo
FIRST_PRICE = 100 * UNIT               # the first unit of a fund costs ₦1


class FundError(Exception):
    """A request about a pension fund that the rules do not allow. The words are for the player."""


def _rows(conn: Connection, sql: str, params=()) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def _one(conn: Connection, sql: str, params=()) -> dict | None:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchone()


def _money(kobo: int) -> str:
    return objectives._money(kobo)


def _open(conn: Connection, now: datetime) -> dict:
    try:
        careers.books_open(conn, now)
    except careers.CareerError as closing:
        raise FundError(str(closing)) from None
    return careers.world_now(conn, now)


def _fund(conn: Connection, fund_id, *, lock: bool = False) -> dict:
    fund = _one(conn, "SELECT * FROM empires WHERE id = %s AND kind = 'pension'" + (" FOR UPDATE" if lock else ""), (fund_id,))
    if fund is None:
        raise FundError("There is no such pension fund.")
    return fund


def _managed(conn: Connection, manager_id, *, lock: bool = True) -> dict:
    fund = _one(conn, "SELECT * FROM empires WHERE kind = 'pension' AND head_player_id = %s AND status = 'active'"
                      + (" FOR UPDATE" if lock else ""), (manager_id,))
    if fund is None:
        raise FundError("You manage no pension fund.")
    return fund


def worth(conn: Connection, fund: dict, now: datetime) -> dict:
    return objectives.wealth(conn, fund["account_id"], now)


def unit_price(fund: dict, total: int, *, buying: bool = False) -> int:
    """What one unit is worth, in millionths of a kobo. Somebody buying units pays the price
    rounded up, so that rounding never takes anything from the savers already in the fund."""
    if fund["units"] <= 0 or total <= 0:
        return FIRST_PRICE
    return -(-total * UNIT // fund["units"]) if buying else total * UNIT // fund["units"]


def _value(units: int, price: int) -> int:
    return units * price // UNIT


# ---------------------------------------------------------------------------
# Opening a fund
# ---------------------------------------------------------------------------

def open_fund(conn: Connection, player_id, name: str, fee_bps: int, now: datetime) -> dict:
    """Open a pension fund. Only an Asset Manager of Level 20 or above; one fund each, for good.
    The registration fee is paid into the prize pool."""
    with conn.transaction():
        state = _open(conn, now)
        conn.execute("SELECT 1 FROM players WHERE id = %s FOR UPDATE", (player_id,))
        mine = careers.career(conn, player_id, "asset_manager")
        build = _one(conn, "SELECT build FROM players WHERE id = %s", (player_id,))["build"]
        if build != "asset_manager" or mine is None or mine["level"] < data.FUND_MANAGER_LEVEL:
            raise FundError(f"Only an Asset Manager of Level {data.FUND_MANAGER_LEVEL} or above may open a pension fund.")
        if _one(conn, "SELECT 1 FROM empires WHERE kind = 'pension' AND manager_id = %s", (player_id,)):
            raise FundError("You have opened a pension fund before. A manager opens one fund, once.")
        if _one(conn, "SELECT 1 FROM legal_records WHERE player_id = %s AND kind = 'theft'", (player_id,)):
            raise FundError("Somebody with a proved theft on their record cannot be trusted with other people's pensions.")
        if not isinstance(fee_bps, int) or not 0 <= fee_bps <= data.FUND_FEE_MOST_BPS:
            raise FundError(f"The fee is from 0% to {data.FUND_FEE_MOST_BPS / 100:.2f}% of the fund each quarter.")
        try:
            name = empires._name_ok(conn, name)
        except empires.EmpireError:
            raise FundError("That name is taken, or is not 3 to 40 letters, numbers and spaces.") from None
        fee = naira(data.FUND_REGISTRATION_NAIRA)
        account = ledger.create_account(conn, kind="fund", name=name)
        try:
            ledger.transfer(conn, payer=ledger.player_account_id(conn, player_id), receiver=ledger.account_id(conn, ledger.PRIZE_POOL),
                            amount=fee, kind="fund_registration", memo=f"{name}: registration of a pension fund", period=state["period"])
        except ledger.InsufficientFunds:
            raise FundError(f"Registering a pension fund costs {_money(fee)}, from your own cash.") from None
        fund = _one(conn, "INSERT INTO empires (name, kind, status, account_id, head_player_id, manager_id, founded_period, fee_bps, created_at)"
                          " VALUES (%s, 'pension', 'active', %s, %s, %s, %s, %s, %s) RETURNING *",
                    (name, account, player_id, player_id, state["period"], fee_bps, now))
        empires._log(conn, fund["id"], f"{name} was opened. Its fee is {fee_bps / 100:.2f}% of the fund each quarter.", now)
        careers._event(conn, player_id, "asset_manager", "fund_opened", f"Opened the pension fund {name}.", now)
        return fund


def set_fee(conn: Connection, manager_id, fee_bps: int, now: datetime) -> None:
    """A manager may lower the fee at any time. It cannot be raised: savers joined at the fee they saw."""
    with conn.transaction():
        fund = _managed(conn, manager_id)
        if not isinstance(fee_bps, int) or not 0 <= fee_bps <= fund["fee_bps"]:
            raise FundError("The fee can be lowered, never raised.")
        conn.execute("UPDATE empires SET fee_bps = %s WHERE id = %s", (fee_bps, fund["id"]))
        empires._log(conn, fund["id"], f"The fee was lowered to {fee_bps / 100:.2f}% a quarter.", now)


# ---------------------------------------------------------------------------
# Savers: joining and leaving
# ---------------------------------------------------------------------------

def join(conn: Connection, player_id, fund_id: int, now: datetime) -> dict:
    """Move retirement savings into a fund run by a player. The money is paid over by the pension
    funds that held it, and buys units at the fund's value at this moment. Like any change of fund,
    it can be done once in a game year."""
    with conn.transaction():
        state = _open(conn, now)
        fund = _fund(conn, fund_id, lock=True)
        if fund["status"] != "active" or fund["struck_off"] or fund["head_player_id"] is None:
            raise FundError("That fund is not taking savers.")
        if fund["head_player_id"] == player_id:
            raise FundError("A manager's own pension is not kept in the fund they run.")
        conn.execute("INSERT INTO retirement_accounts (player_id) VALUES (%s) ON CONFLICT DO NOTHING", (player_id,))
        account = _one(conn, "SELECT * FROM retirement_accounts WHERE player_id = %s FOR UPDATE", (player_id,))
        if account["managed_fund_id"] is not None:
            raise FundError("Your savings are already with a fund run by a player. Leave it first.")
        chosen = account["fund_chosen_period"]
        if chosen is not None and state["period"] - chosen < clock.QUARTERS_PER_YEAR:
            raise FundError(f"A fund can be changed once in a game year. You can change again in "
                            f"{clock.period_label(chosen + clock.QUARTERS_PER_YEAR)}.")
        if account["value"] <= 0:
            raise FundError("You have no retirement savings to move yet.")
        pension_funds = ledger.account_id(conn, ledger.INVESTORS_INSTITUTIONS)
        if ledger.balance(conn, pension_funds) < account["value"]:
            raise FundError("The pension funds cannot release that much cash today. Try again after the quarter closes.")
        price = unit_price(fund, worth(conn, fund, now)["total"], buying=True)
        ledger.transfer(conn, payer=pension_funds, receiver=fund["account_id"], amount=account["value"], kind="pension_transfer",
                        memo=f"{fund['name']}: a saver's retirement savings moved in", period=state["period"])
        units = account["value"] * UNIT // price
        conn.execute("UPDATE empires SET units = units + %s WHERE id = %s", (units, fund["id"]))
        conn.execute("UPDATE retirement_accounts SET managed_fund_id = %s, units = %s, fund_chosen_period = %s, leaving = false,"
                     " value = 0 WHERE player_id = %s", (fund["id"], units, state["period"], player_id))
        build = _one(conn, "SELECT build FROM players WHERE id = %s", (player_id,))["build"]
        careers._event(conn, player_id, build, "fund_chosen", f"Moved retirement savings to {fund['name']}, a fund run by a player.", now)
        return {"units": units, "unit_price": price, "moved": account["value"]}


def leave(conn: Connection, player_id, now: datetime) -> dict:
    """Ask for the savings back. They are paid at once as far as the fund has cash; the rest follows
    as it sells. Until then the manager can buy nothing more."""
    with conn.transaction():
        _open(conn, now)
        account = _one(conn, "SELECT * FROM retirement_accounts WHERE player_id = %s FOR UPDATE", (player_id,))
        if account is None or account["managed_fund_id"] is None:
            raise FundError("Your savings are not with a fund run by a player.")
        conn.execute("UPDATE retirement_accounts SET leaving = true WHERE player_id = %s", (player_id,))
        fund = _fund(conn, account["managed_fund_id"], lock=True)
        _settle(conn, fund, now)
        after = _one(conn, "SELECT managed_fund_id, value, units FROM retirement_accounts WHERE player_id = %s", (player_id,))
        return {"done": after["managed_fund_id"] is None, "value": after["value"], "units_left": after["units"]}


def _settle(conn: Connection, fund: dict, now: datetime) -> int:
    """Pay savers who have asked to leave, oldest request first, as far as the fund's cash goes.
    Returns what is still owed to them."""
    period = careers.world_now(conn, now)["period"]
    pension_funds = ledger.account_id(conn, ledger.INVESTORS_INSTITUTIONS)
    owed = 0
    for account in _rows(conn, "SELECT * FROM retirement_accounts WHERE managed_fund_id = %s AND leaving ORDER BY player_id FOR UPDATE",
                         (fund["id"],)):
        fund = _fund(conn, fund["id"])
        price = unit_price(fund, worth(conn, fund, now)["total"])
        due = _value(account["units"], price)
        cash = max(ledger.balance(conn, fund["account_id"]), 0)
        pay = min(due, cash)
        units = account["units"] if pay == due else pay * UNIT // price
        if pay > 0:
            ledger.transfer(conn, payer=fund["account_id"], receiver=pension_funds, amount=pay, kind="pension_transfer",
                            memo=f"{fund['name']}: a saver's retirement savings moved out", period=period)
        conn.execute("UPDATE empires SET units = units - %s WHERE id = %s", (units, fund["id"]))
        if pay == due:
            conn.execute("UPDATE retirement_accounts SET managed_fund_id = NULL, units = 0, leaving = false, value = value + %s"
                         " WHERE player_id = %s", (pay, account["player_id"]))
        else:
            conn.execute("UPDATE retirement_accounts SET units = units - %s, value = value + %s WHERE player_id = %s",
                         (units, pay, account["player_id"]))
            owed += due - pay
    return owed


def _saver_value(conn: Connection, account: dict, now: datetime) -> int:
    fund = _fund(conn, account["managed_fund_id"])
    return _value(account["units"], unit_price(fund, worth(conn, fund, now)["total"]))


# ---------------------------------------------------------------------------
# The manager: investing, and taking
# ---------------------------------------------------------------------------

def _buying_allowed(conn: Connection, fund: dict) -> None:
    if _one(conn, "SELECT 1 FROM retirement_accounts WHERE managed_fund_id = %s AND leaving", (fund["id"],)):
        raise FundError("A saver is waiting for their savings back. The fund can sell, and can buy nothing until they are paid.")


def trade_shares(conn: Connection, manager_id, *, ticker: str, side: str, kind: str, quantity: int, limit_price: int | None,
                 now: datetime) -> dict:
    with conn.transaction():
        _open(conn, now)
        fund = _managed(conn, manager_id)
        if side == "buy":
            _buying_allowed(conn, fund)
        try:
            return exchange.place_order(conn, account=fund["account_id"], ticker=ticker, side=side, kind=kind, quantity=quantity,
                                        limit_price=limit_price, now=now)
        except exchange.ExchangeError as refused:
            raise FundError(str(refused)) from None


def cancel_order(conn: Connection, manager_id, order_id: int, now: datetime) -> dict:
    with conn.transaction():
        fund = _managed(conn, manager_id)
        try:
            return exchange.cancel_order(conn, account=fund["account_id"], order_id=order_id, now=now)
        except exchange.ExchangeError as refused:
            raise FundError(str(refused)) from None


def trade_bonds(conn: Connection, manager_id, *, code: str, side: str, units: int, now: datetime) -> dict:
    with conn.transaction():
        _open(conn, now)
        fund = _managed(conn, manager_id)
        if side == "buy":
            _buying_allowed(conn, fund)
        try:
            return bonds.trade(conn, account=fund["account_id"], code=code, side=side, units=units, now=now)
        except bonds.BondError as refused:
            raise FundError(str(refused)) from None


def signing_limit(conn: Connection, fund: dict, now: datetime) -> int:
    return apply_bps(worth(conn, fund, now)["total"], data.FUND_SIGNING_BPS)


def divert(conn: Connection, manager_id, amount: int, now: datetime) -> dict:
    """The shadow side of running other people's money: the manager takes some, written into the
    fund's books as a cost. It leaves a trail in the ledger, and an audit may find it."""
    with conn.transaction():
        state = _open(conn, now)
        fund = _managed(conn, manager_id)
        if not isinstance(amount, int) or amount <= 0:
            raise FundError("An amount above nought.")
        limit = signing_limit(conn, fund, now)
        used = empires._spent(conn, fund["id"], manager_id, state["period"])
        if used + amount > limit:
            raise FundError(f"A manager can sign for costs of {_money(limit)} in a quarter, of which {_money(used)} is used.")
        try:
            ledger.transfer(conn, payer=fund["account_id"], receiver=ledger.player_account_id(conn, manager_id), amount=amount,
                            kind="empire_expense", memo=f"{fund['name']}: custody and dealing costs", period=state["period"])
        except ledger.InsufficientFunds:
            raise FundError("The fund does not have that much cash.") from None
        level = careers.career(conn, manager_id, "asset_manager")["level"]
        book = empires._book(conn, fund["id"], state["period"], "Custody and dealing costs", "Custody, brokerage and dealing costs",
                             amount, False, now, entered_by=manager_id, thief_level=level)
        return {"book_id": book, "amount": amount, "limit": limit, "used": used + amount}


def strike_off(conn: Connection, fund: dict, now: datetime) -> None:
    """A manager proved to have taken savers' money is removed. The regulator runs the fund from
    then on: it charges no fee, buys nothing, and pays every saver who asks to leave."""
    manager = fund["head_player_id"]
    conn.execute("UPDATE empires SET head_player_id = NULL, struck_off = true, fee_bps = 0 WHERE id = %s", (fund["id"],))
    empires._log(conn, fund["id"], "The manager was struck off by the regulator, which now runs the fund. It charges no fee. "
                                   "Savers may stay, or ask for their savings back.", now)
    if manager:
        careers._event(conn, manager, "asset_manager", "struck_off", f"Struck off as manager of {fund['name']}.", now)


def ai_audit(conn: Connection, player_id, now: datetime) -> dict:
    """A saver hires the AI audit of the fund their pension is in, with their own money, in an audit season."""
    with conn.transaction():
        state = _open(conn, now)
        account = _one(conn, "SELECT managed_fund_id FROM retirement_accounts WHERE player_id = %s", (player_id,))
        if account is None or account["managed_fund_id"] is None:
            raise FundError("Your savings are not with a fund run by a player.")
        fund = _fund(conn, account["managed_fund_id"], lock=True)
        try:
            return empires._ai_audit(conn, fund, state["period"], now, payer=ledger.player_account_id(conn, player_id), hired_by=player_id)
        except empires.EmpireError as refused:
            raise FundError(str(refused)) from None


# ---------------------------------------------------------------------------
# The quarter's end
# ---------------------------------------------------------------------------

def at_bell(conn: Connection, now: datetime) -> None:
    for fund in _rows(conn, "SELECT id FROM empires WHERE kind = 'pension' AND status = 'active' ORDER BY id"):
        with conn.transaction():
            _settle(conn, _fund(conn, fund["id"], lock=True), now)


def after_close(conn: Connection, period: int, now: datetime) -> None:
    """After a quarter has closed, for every fund run by a player: the regulator audits its books;
    the manager's fee is paid; what savers and their employers paid in this quarter arrives and buys
    units; pensions are paid; savers who asked to leave are paid, the regulator selling if it must;
    and the price of a unit is written down for good."""
    pension_funds = ledger.account_id(conn, ledger.INVESTORS_INSTITUTIONS)
    for row in _rows(conn, "SELECT id FROM empires WHERE kind = 'pension' AND status = 'active' ORDER BY id"):
        with conn.transaction():
            fund = _fund(conn, row["id"], lock=True)
            _regulator_audit(conn, fund, period, now)
            fund = _fund(conn, row["id"])
            total = worth(conn, fund, now)["total"]
            if fund["head_player_id"] and fund["fee_bps"] and total > 0:
                paid = ledger.pay_up_to(conn, payer=fund["account_id"], receiver=ledger.player_account_id(conn, fund["head_player_id"]),
                                        wanted=apply_bps(total, fund["fee_bps"]), kind="fund_fee", period=period,
                                        memo=f"{fund['name']}: manager's fee, {clock.period_label(period)}")
                if paid:
                    empires._book(conn, fund["id"], period, "Manager's fee", f"The manager's fee of {fund['fee_bps'] / 100:.2f}%", paid, True, now)
            for account in _rows(conn, "SELECT * FROM retirement_accounts WHERE managed_fund_id = %s ORDER BY player_id FOR UPDATE", (fund["id"],)):
                fund = _fund(conn, row["id"])
                price = unit_price(fund, worth(conn, fund, now)["total"])
                before = _one(conn, "SELECT closing FROM retirement_entries WHERE player_id = %s ORDER BY period DESC LIMIT 1",
                              (account["player_id"],))
                opening = account["value"] + _value(account["units"], price)
                slip = _one(conn, "SELECT pension_yours, pension_employer FROM payslips WHERE player_id = %s AND period = %s",
                            (account["player_id"], period))
                yours, employer = (slip["pension_yours"], slip["pension_employer"]) if slip else (0, 0)
                paid_in = 0 if account["leaving"] else ledger.pay_up_to(
                    conn, payer=pension_funds, receiver=fund["account_id"], wanted=yours + employer, kind="pension_transfer",
                    period=period, memo=f"{fund['name']}: a saver's contributions for the quarter")
                bought = paid_in * UNIT // unit_price(fund, worth(conn, fund, now)["total"] - paid_in, buying=True)
                units = account["units"] + bought
                conn.execute("UPDATE empires SET units = units + %s WHERE id = %s", (bought, fund["id"]))
                paid_out = 0
                if account["retired_period"] is not None and units > 0:
                    value = _value(units, price)
                    wanted = value if value < naira(10_000) else apply_bps(value, data.PENSION_PAID_BPS)
                    paid_out = ledger.pay_up_to(conn, payer=fund["account_id"], receiver=ledger.player_account_id(conn, account["player_id"]),
                                                wanted=wanted, kind="pension_payment", period=period,
                                                memo=f"Pension for {clock.period_label(period)}", reference=f"pension:{account['player_id']}:{period}")
                    sold = min(units, paid_out * UNIT // price)
                    units -= sold
                    conn.execute("UPDATE empires SET units = units - %s WHERE id = %s", (sold, fund["id"]))
                # While a saver is leaving, what is paid in for them stays with the ordinary funds.
                kept = account["value"] + (yours + employer if account["leaving"] else 0)
                closing = kept + _value(units, price)
                shown_opening = before["closing"] if before else opening
                conn.execute("UPDATE retirement_accounts SET units = %s, value = %s WHERE player_id = %s", (units, kept, account["player_id"]))
                conn.execute("INSERT INTO retirement_entries (player_id, period, fund, opening, growth, paid_in_by_you, paid_in_by_employer,"
                             " closing, paid_out) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
                             (account["player_id"], period, "managed", shown_opening,
                              closing + paid_out - yours - employer - shown_opening, yours, employer, closing, paid_out))
            fund = _fund(conn, row["id"], lock=True)
            owed = _settle(conn, fund, now)
            if owed > 0:
                _regulator_sells(conn, fund, owed, now)
                _settle(conn, _fund(conn, row["id"]), now)
            fund = _fund(conn, row["id"])
            total = worth(conn, fund, now)["total"]
            savers = _one(conn, "SELECT count(*) AS n FROM retirement_accounts WHERE managed_fund_id = %s", (fund["id"],))["n"]
            conn.execute("INSERT INTO fund_prices (fund_id, period, unit_price, worth, units, savers) VALUES (%s, %s, %s, %s, %s, %s)"
                         " ON CONFLICT DO NOTHING", (fund["id"], period, unit_price(fund, total), total, fund["units"], savers))


def _regulator_audit(conn: Connection, fund: dict, period: int, now: datetime) -> None:
    """The regulator looks at every fund's books for the quarter just closed. It finds a false entry
    less often than not; in an audit season it sometimes sends in the AI audit, at the fund's cost."""
    entries = empires._unfound(conn, fund["id"], period, period)
    false = [e for e in entries if not e["genuine"]]
    if false:
        audit = _one(conn, "INSERT INTO empire_audits (empire_id, kind, period, from_period, to_period, examined, at)"
                           " VALUES (%s, 'staff', %s, %s, %s, %s, %s) RETURNING id", (fund["id"], period, period, period, len(entries), now))["id"]
        found = [e for e in false if empires._roll(conn, "regulator", audit, e["id"])
                 < empires._auditor_finds_bps(data.STAFF_LEVEL, (e["thief_level"] or 1) + 30)]
        conn.execute("UPDATE empire_audits SET findings = %s, reported = %s WHERE id = %s", ([e["id"] for e in found], [e["id"] for e in found], audit))
        for entry in found:
            empires._prove(conn, _fund(conn, fund["id"]), entry, audit, now)
    if empires.audit_season(period) and empires._roll(conn, "season", fund["id"], period) < 5000 and _one(
            conn, "SELECT 1 FROM empire_books WHERE empire_id = %s AND entered_by IS NOT NULL AND category <> 'Manager''s fee' AND period > %s LIMIT 1",
            (fund["id"], period - data.AI_AUDIT_LOOKS_BACK)):
        try:
            with conn.transaction():
                empires._ai_audit(conn, _fund(conn, fund["id"]), period, now, payer=fund["account_id"], hired_by=None)
        except empires.EmpireError:
            pass


def _regulator_sells(conn: Connection, fund: dict, owed: int, now: datetime) -> None:
    """Savers are waiting and the fund has too little cash: its bonds are sold to the dealing desk,
    and then its shares are offered on the exchange, until enough has been raised."""
    for line in bonds.holdings_of(conn, fund["account_id"], now):
        if owed <= 0:
            return
        if line["units"] <= 0 or line["value"] <= 0:
            continue
        units = min(line["units"], owed * line["units"] // line["value"] + 1)
        try:
            with conn.transaction():
                done = bonds.trade(conn, account=fund["account_id"], code=line["code"], side="sell", units=units, now=now)
                owed -= done["value"]
        except (bonds.BondError, ledger.LedgerError):
            continue
    shares = {s["id"]: s for s in marketview._shares(conn, exchange.session_of(now)[0])}
    for row in _rows(conn, "SELECT company_id, shares FROM share_owners WHERE account_id = %s AND shares > 0 ORDER BY shares DESC",
                     (fund["account_id"],)):
        if owed <= 0:
            return
        share = shares[row["company_id"]]
        quantity = min(row["shares"], owed // max(share["price"], 1) + 1)
        low, _high = exchange.price_limits(share["reference"])
        try:
            with conn.transaction():
                exchange.place_order(conn, account=fund["account_id"], ticker=share["ticker"], side="sell", kind="limit",
                                     quantity=quantity, limit_price=max(share["price"] * 97 // 100, low), now=now)
                owed -= quantity * share["price"]
        except (exchange.ExchangeError, ledger.LedgerError):
            continue


# ---------------------------------------------------------------------------
# What players see
# ---------------------------------------------------------------------------

def _history(conn: Connection, fund_id) -> list[dict]:
    return _rows(conn, "SELECT period, unit_price, worth, savers FROM fund_prices WHERE fund_id = %s ORDER BY period DESC LIMIT 12", (fund_id,))


def listing(conn: Connection, player_id, now: datetime) -> dict:
    """Every pension fund run by a player, as a saver choosing one sees it; and the player's own."""
    state = careers.world_now(conn, now)
    mine = _one(conn, "SELECT managed_fund_id, units, leaving, value FROM retirement_accounts WHERE player_id = %s", (player_id,))
    funds = []
    for fund in _rows(conn, "SELECT e.*, p.display_name AS manager FROM empires e LEFT JOIN players p ON p.id = e.manager_id"
                            " WHERE e.kind = 'pension' AND e.status = 'active' ORDER BY e.id"):
        have = worth(conn, fund, now)
        price = unit_price(fund, have["total"])
        history = _history(conn, fund["id"])
        year = [h for h in history if h["period"] > state["period"] - 5]
        over_year = (price - year[-1]["unit_price"]) * BPS // year[-1]["unit_price"] if year else None
        funds.append({
            "id": fund["id"], "name": fund["name"], "manager": fund["manager"], "struck_off": fund["struck_off"],
            "run_by_regulator": fund["head_player_id"] is None, "fee_bps": fund["fee_bps"], "worth": have["total"],
            "cash": have["cash"], "shares_value": have["shares"], "bonds_value": have["bonds"], "unit_price": price / UNIT / 100,
            "savers": _one(conn, "SELECT count(*) AS n FROM retirement_accounts WHERE managed_fund_id = %s", (fund["id"],))["n"],
            "since": fund["founded_period"], "over_year_bps": over_year,
            "history": [{"period": h["period"], "unit_price": h["unit_price"] / UNIT / 100} for h in reversed(history)],
            "proved_thefts": _one(conn, "SELECT count(*) AS n FROM empire_cases WHERE empire_id = %s", (fund["id"],))["n"],
            "yours": bool(mine and mine["managed_fund_id"] == fund["id"]),
            "your_value": _value(mine["units"], price) if mine and mine["managed_fund_id"] == fund["id"] else 0,
            "leaving": bool(mine and mine["managed_fund_id"] == fund["id"] and mine["leaving"]),
        })
    career = careers.career(conn, player_id)
    build = _one(conn, "SELECT build FROM players WHERE id = %s", (player_id,))["build"]
    opened = _one(conn, "SELECT 1 FROM empires WHERE kind = 'pension' AND manager_id = %s", (player_id,))
    return {"funds": funds, "manager_level": data.FUND_MANAGER_LEVEL, "registration_fee": naira(data.FUND_REGISTRATION_NAIRA),
            "fee_most_bps": data.FUND_FEE_MOST_BPS, "audit_season": empires.audit_season(state["period"]),
            "can_open": bool(build == "asset_manager" and career and career["level"] >= data.FUND_MANAGER_LEVEL and not opened),
            "managing": manager_view(conn, player_id, now)}


def manager_view(conn: Connection, manager_id, now: datetime) -> dict | None:
    """What the manager sees of the fund they run."""
    fund = _one(conn, "SELECT * FROM empires WHERE kind = 'pension' AND head_player_id = %s AND status = 'active'", (manager_id,))
    if fund is None:
        return None
    state = careers.world_now(conn, now)
    have = worth(conn, fund, now)
    limit = signing_limit(conn, fund, now)
    return {
        "id": fund["id"], "name": fund["name"], "fee_bps": fund["fee_bps"], "worth": have["total"], "cash": have["cash"],
        "shares_value": have["shares"], "bonds_value": have["bonds"], "unit_price": unit_price(fund, have["total"]) / UNIT / 100,
        "holdings": [{"ticker": line["ticker"], "shares": line["shares"], "value": line["value"]} for line in have["lines"]],
        "bond_holdings": [{"code": b["code"], "name": b["name"], "units": b["units"], "value": b["value"]} for b in have["bond_lines"]],
        "orders": exchange.orders_of(conn, fund["account_id"], limit=10),
        "savers": _one(conn, "SELECT count(*) AS n FROM retirement_accounts WHERE managed_fund_id = %s", (fund["id"],))["n"],
        "leaving": _one(conn, "SELECT count(*) AS n FROM retirement_accounts WHERE managed_fund_id = %s AND leaving", (fund["id"],))["n"],
        "signing_limit": limit, "signing_used": empires._spent(conn, fund["id"], manager_id, state["period"]),
        "books": _rows(conn, "SELECT id, period, category, description, amount, found FROM empire_books WHERE empire_id = %s"
                             " ORDER BY id DESC LIMIT 30", (fund["id"],)),
        "events": _rows(conn, "SELECT words, at FROM empire_events WHERE empire_id = %s ORDER BY id DESC LIMIT 15", (fund["id"],)),
    }


def saver_value(conn: Connection, player_id, now: datetime) -> dict | None:
    """The value today of savings held in a fund run by a player, for the career page."""
    account = _one(conn, "SELECT * FROM retirement_accounts WHERE player_id = %s", (player_id,))
    if account is None or account["managed_fund_id"] is None:
        return None
    fund = _fund(conn, account["managed_fund_id"])
    return {"fund_id": fund["id"], "name": fund["name"], "value": account["value"] + _saver_value(conn, account, now),
            "leaving": account["leaving"], "run_by_regulator": fund["head_player_id"] is None}
