"""Stage 9, Part A: an empire borrows against its holdings and sells short, inside its Risk Manager's limits.

The Risk Manager signs two limits: the most the empire may owe on loans against its shares and bonds, and
the most its short sales may be worth. Until they are signed, both are nought. The Asset Manager (or the
head) acts for the empire inside them. Above them, the request goes to the head, who decides.
"""

from __future__ import annotations

from datetime import datetime

from psycopg import Connection

from simulation import careers, empires, firm, lending
from simulation.empires import EmpireError
from simulation.money import naira

LIMIT_KEYS = ("borrow_limit_naira", "short_limit_naira")
ACTORS = ("asset_manager",)


def _seat(conn: Connection, player_id) -> tuple[dict, dict]:
    seat, empire = firm._active(conn, player_id)
    if empire.get("kind") == "pension":
        raise EmpireError("A pension fund does not borrow or sell short.")
    return seat, empire


def set_limits(conn: Connection, player_id, borrow_naira: int | None, short_naira: int | None, now: datetime) -> dict:
    """The Risk Manager (or the head, if nobody sits at that desk) signs the empire's borrowing and short-selling limits."""
    with conn.transaction():
        seat, empire = _seat(conn, player_id)
        if seat["build"] != "risk_manager" and not (empire["head_player_id"] == player_id
                                                    and not firm.desk_members(conn, empire["id"], "risk_manager")):
            raise EmpireError("The Risk Manager signs the limits on borrowing and short selling.")
        state = careers.world_now(conn, now)
        for key, value in zip(LIMIT_KEYS, (borrow_naira, short_naira)):
            if value is not None and (not isinstance(value, int) or isinstance(value, bool) or value < 0):
                raise EmpireError("A limit is a whole number of naira, nought or more.")
            firm.set_article(conn, empire["id"], key, value or 0, state["period"], now)
        empires._log(conn, empire["id"], f"The Risk Manager set the limits: borrowing against holdings up to ₦{borrow_naira or 0:,}; "
                                         f"short sales up to ₦{short_naira or 0:,}.", now)
        return limits(conn, empire)


def limits(conn: Connection, empire: dict) -> dict:
    return {key: firm.article(conn, empire["id"], key) or 0 for key in LIMIT_KEYS}


def _may_act(conn: Connection, seat: dict, empire: dict, player_id) -> bool:
    """True for the head; the Asset Manager acts inside the limits; anybody else may not."""
    if empire["head_player_id"] == player_id:
        return True
    if seat["build"] in ACTORS:
        return False
    raise EmpireError("The Asset Manager (or the head) borrows and sells short for the empire.")


def borrow(conn: Connection, player_id, bank_company_id, amount: int, now: datetime) -> dict:
    seat, empire = _seat(conn, player_id)
    head = _may_act(conn, seat, empire, player_id)
    limit = naira(limits(conn, empire)["borrow_limit_naira"])
    if not head and lending.margin_owed(conn, empire["account_id"]) + amount > limit:
        return _ask(conn, empire, player_id, "empire_borrow", f"Borrow ₦{amount // 100:,} against the empire's holdings", amount,
                    {"bank": str(bank_company_id), "amount": amount}, now)
    result = lending.take_margin(conn, empire["account_id"], bank_company_id, amount, now)
    empires._log(conn, empire["id"], f"The empire borrowed ₦{amount // 100:,} against its shares and bonds.", now)
    return result


def short(conn: Connection, player_id, ticker: str, shares: int, now: datetime) -> dict:
    seat, empire = _seat(conn, player_id)
    head = _may_act(conn, seat, empire, player_id)
    limit = naira(limits(conn, empire)["short_limit_naira"])
    price = lending._one(conn, "SELECT coalesce(m.last_price, m.reference_price) AS p FROM companies c JOIN market_instruments m"
                               " ON m.company_id = c.id WHERE c.ticker = %s", (ticker,))
    if price is None:
        raise lending.LendingError("Only shares listed on the exchange can be borrowed.")
    value = price["p"] * shares if isinstance(shares, int) else 0
    if not head and lending.short_liability(conn, empire["account_id"]) + value > limit:
        return _ask(conn, empire, player_id, "empire_short", f"Sell short {shares:,} {ticker} for the empire", value,
                    {"ticker": ticker, "shares": shares}, now)
    result = lending.open_short(conn, empire["account_id"], ticker, shares, now)
    empires._log(conn, empire["id"], f"The empire borrowed {shares:,} {ticker} shares to sell short.", now)
    return result


def _ask(conn: Connection, empire: dict, player_id, kind: str, title: str, amount: int, payload: dict, now: datetime) -> dict:
    with conn.transaction():
        state = careers.world_now(conn, now)
        request = firm.ask(conn, empire, kind=kind, desk="head", asked_by=player_id, title=title, amount=amount,
                           payload={**payload, "why": ["it is above the limit the Risk Manager signed"]}, period=state["period"], now=now)
    return {"waiting": True, "approval_id": request["id"]}


def _execute_borrow(conn: Connection, approval: dict, now: datetime) -> None:
    empire = empires._empire(conn, approval["empire_id"])
    p = approval["payload"]
    try:
        lending.take_margin(conn, empire["account_id"], p["bank"], p["amount"], now)
    except lending.LendingError as refused:
        raise EmpireError(str(refused)) from None


def _execute_short(conn: Connection, approval: dict, now: datetime) -> None:
    empire = empires._empire(conn, approval["empire_id"])
    p = approval["payload"]
    try:
        lending.open_short(conn, empire["account_id"], p["ticker"], p["shares"], now)
    except lending.LendingError as refused:
        raise EmpireError(str(refused)) from None


def _view(conn: Connection, approval: dict, viewer_id, now: datetime) -> dict:
    empire = empires._empire(conn, approval["empire_id"])
    return {"why": approval["payload"].get("why", []), "limits": limits(conn, empire),
            "owed": lending.margin_owed(conn, empire["account_id"]), "shorted": lending.short_liability(conn, empire["account_id"])}


def _staff_rule(conn: Connection, approval: dict, now: datetime) -> tuple[bool, str]:
    return False, "The staff will not borrow or sell short above the Risk Manager's limit."


def act_for_empire(conn: Connection, player_id, action: str, ref: int, amount: int, now: datetime) -> dict:
    """Repay a loan, close a short, or add collateral, for the empire (the head or the Asset Manager)."""
    seat, empire = _seat(conn, player_id)
    _may_act(conn, seat, empire, player_id)
    account = empire["account_id"]
    if action == "repay":
        return lending.repay(conn, account, ref, amount, now)
    if action == "close_short":
        return lending.close_short(conn, account, ref, now)
    if action == "add_collateral":
        return lending.add_collateral(conn, account, ref, amount, now)
    raise EmpireError("Unknown action.")


firm.EXECUTORS.update({"empire_borrow": _execute_borrow, "empire_short": _execute_short})
firm.VIEWERS.update({"empire_borrow": _view, "empire_short": _view})
firm.STAFF_RULES.update({"empire_borrow": _staff_rule, "empire_short": _staff_rule})
for _key in LIMIT_KEYS:
    firm.ARTICLE_DEFAULTS.setdefault(_key, 0)
