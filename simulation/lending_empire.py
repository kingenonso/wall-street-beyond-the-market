"""Stage 9, Part A: an empire borrows against its holdings and sells short, inside its Risk Manager's limits.

The Risk Manager signs three limits: the most the empire may owe on loans against its shares and bonds, the
most its short sales may be worth, and the most it may put into options and futures. Until they are signed,
all are nought. Lowering a limit takes effect at once; raising one needs the head's approval (so the seat that
signs the limits cannot sign itself room to speculate). The Asset Manager (or the head) acts for the empire
inside them; the Risk Manager only buys protection (options). Above them, the request goes to the head.
Each check is made under the empire's own lock, so two requests at once cannot both slip under a limit.
"""

from __future__ import annotations

from datetime import datetime

from psycopg import Connection

from simulation import careers, empires, firm, lending
from simulation.empires import EmpireError
from simulation.money import naira

LIMIT_KEYS = ("borrow_limit_naira", "short_limit_naira", "derivatives_limit_naira")
ACTORS = ("asset_manager",)


def _seat(conn: Connection, player_id) -> tuple[dict, dict]:
    seat, empire = firm._active(conn, player_id)
    if empire.get("kind") == "pension":
        raise EmpireError("A pension fund does not borrow or sell short.")
    return seat, empire


def set_limits(conn: Connection, player_id, borrow_naira: int | None, short_naira: int | None, now: datetime,
               derivatives_naira: int | None = None) -> dict:
    """The Risk Manager (or the head, if nobody sits at that desk) signs the empire's borrowing and short-selling limits."""
    with conn.transaction():
        seat, empire = _seat(conn, player_id)
        if seat["build"] != "risk_manager" and not (empire["head_player_id"] == player_id
                                                    and not firm.desk_members(conn, empire["id"], "risk_manager")):
            raise EmpireError("The Risk Manager signs the limits on borrowing and short selling.")
        state = careers.world_now(conn, now)
        if derivatives_naira is None:
            derivatives_naira = firm.article(conn, empire["id"], "derivatives_limit_naira") or 0
        wanted = {}
        for key, value in zip(LIMIT_KEYS, (borrow_naira, short_naira, derivatives_naira)):
            if value is not None and (not isinstance(value, int) or isinstance(value, bool) or value < 0):
                raise EmpireError("A limit is a whole number of naira, nought or more.")
            wanted[key] = value or 0
        now_limits = limits(conn, empire)
        if empire["head_player_id"] != player_id and any(wanted[k] > now_limits[k] for k in LIMIT_KEYS):
            request = firm.ask(conn, empire, kind="empire_limits", desk="head", asked_by=player_id,
                               title=(f"Raise the limits: borrowing ₦{wanted['borrow_limit_naira']:,}, short sales ₦{wanted['short_limit_naira']:,},"
                                      f" options and futures ₦{wanted['derivatives_limit_naira']:,}"),
                               amount=0, payload={"limits": wanted, "why": ["a limit can be lowered at once; raising one needs the head"]},
                               period=state["period"], now=now)
            return {**now_limits, "waiting": True, "approval_id": request["id"]}
        _apply_limits(conn, empire, wanted, state["period"], now)
        return limits(conn, empire)


def _apply_limits(conn: Connection, empire: dict, wanted: dict, period: int, now: datetime) -> None:
    for key in LIMIT_KEYS:
        firm.set_article(conn, empire["id"], key, wanted[key], period, now)
    empires._log(conn, empire["id"], f"The limits now: borrowing against holdings up to ₦{wanted['borrow_limit_naira']:,}; "
                                     f"short sales up to ₦{wanted['short_limit_naira']:,}; options and futures up to "
                                     f"₦{wanted['derivatives_limit_naira']:,}.", now)


def _execute_limits(conn: Connection, approval: dict, now: datetime) -> None:
    state = careers.world_now(conn, now)
    _apply_limits(conn, empires._empire(conn, approval["empire_id"]), approval["payload"]["limits"], state["period"], now)


def _lock(conn: Connection, account) -> None:
    conn.execute("SELECT pg_advisory_xact_lock(hashtext('borrower:' || %s::text))", (str(account),))


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
    with conn.transaction():
        seat, empire = _seat(conn, player_id)
        head = _may_act(conn, seat, empire, player_id)
        _lock(conn, empire["account_id"])
        return _borrow(conn, player_id, empire, head, bank_company_id, amount, now)


def _borrow(conn: Connection, player_id, empire: dict, head: bool, bank_company_id, amount: int, now: datetime) -> dict:
    limit = naira(limits(conn, empire)["borrow_limit_naira"])
    if not head and lending.margin_owed(conn, empire["account_id"]) + amount > limit:
        return _ask(conn, empire, player_id, "empire_borrow", f"Borrow ₦{amount // 100:,} against the empire's holdings", amount,
                    {"bank": str(bank_company_id), "amount": amount}, now)
    result = lending.take_margin(conn, empire["account_id"], bank_company_id, amount, now, player_id=player_id)
    empires._log(conn, empire["id"], f"The empire borrowed ₦{amount // 100:,} against its shares and bonds.", now)
    return result


def short(conn: Connection, player_id, ticker: str, shares: int, now: datetime) -> dict:
    with conn.transaction():
        seat, empire = _seat(conn, player_id)
        head = _may_act(conn, seat, empire, player_id)
        _lock(conn, empire["account_id"])
        return _short(conn, player_id, empire, head, ticker, shares, now)


def _short(conn: Connection, player_id, empire: dict, head: bool, ticker: str, shares: int, now: datetime) -> dict:
    limit = naira(limits(conn, empire)["short_limit_naira"])
    price = lending._one(conn, "SELECT coalesce(m.last_price, m.reference_price) AS p FROM companies c JOIN market_instruments m"
                               " ON m.company_id = c.id WHERE c.ticker = %s", (ticker,))
    if price is None:
        raise lending.LendingError("Only shares listed on the exchange can be borrowed.")
    value = price["p"] * shares if isinstance(shares, int) else 0
    if not head and lending.short_liability(conn, empire["account_id"]) + value > limit:
        return _ask(conn, empire, player_id, "empire_short", f"Sell short {shares:,} {ticker} for the empire", value,
                    {"ticker": ticker, "shares": shares}, now)
    result = lending.open_short(conn, empire["account_id"], ticker, shares, now, player_id=player_id)
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
        lending.take_margin(conn, empire["account_id"], p["bank"], p["amount"], now, player_id=approval["asked_by"])
    except lending.LendingError as refused:
        raise EmpireError(str(refused)) from None


def _execute_short(conn: Connection, approval: dict, now: datetime) -> None:
    empire = empires._empire(conn, approval["empire_id"])
    p = approval["payload"]
    try:
        lending.open_short(conn, empire["account_id"], p["ticker"], p["shares"], now, player_id=approval["asked_by"])
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


# ---------------------------------------------------------------------------
# Options and futures for the empire, and the hedging desk (Part B)
# ---------------------------------------------------------------------------

def committed(conn: Connection, account) -> int:
    """What the empire has put into options and futures: margin held, and what its bought options cost."""
    from simulation import derivatives
    row = derivatives._one(conn, "SELECT coalesce(sum(margin), 0)::bigint AS m, coalesce(sum(CASE WHEN p.side = 'long' AND s.kind <> 'future'"
                                 " THEN p.entry_price * p.contracts ELSE 0 END), 0)::bigint AS paid FROM derivative_positions p"
                                 " JOIN derivative_series s ON s.id = p.series_id WHERE p.account = %s AND p.status = 'open'", (account,))
    waiting = derivatives._one(conn, "SELECT coalesce(sum(reserved), 0)::bigint AS r FROM derivative_orders WHERE account = %s"
                                     " AND status = 'open'", (account,))["r"]
    return row["m"] + row["paid"] + waiting


def trade(conn: Connection, player_id, series_id: int, side: str, contracts: int, now: datetime, purpose: str | None = None,
          limit: int | None = None) -> dict:
    """The Asset Manager trades options and futures for the empire; the Risk Manager buys protection (a hedge,
    scored when it ends). Inside the derivatives limit they act; above it, the head decides."""
    with conn.transaction():
        seat, empire = _seat(conn, player_id)
        head = empire["head_player_id"] == player_id
        if not head and seat["build"] not in ("asset_manager", "risk_manager"):
            raise EmpireError("The Asset Manager trades options and futures for the empire; the Risk Manager buys protection.")
        _lock(conn, empire["account_id"])
        return _trade(conn, player_id, seat, empire, head, series_id, side, contracts, now, purpose, limit)


def _trade(conn: Connection, player_id, seat: dict, empire: dict, head: bool, series_id: int, side: str, contracts: int,
           now: datetime, purpose: str | None, limit: int | None = None) -> dict:
    from simulation import derivatives
    s = derivatives._series(conn, series_id)
    if seat["build"] == "risk_manager" and not head:
        if s["kind"] == "future" or side != "long":
            raise EmpireError("The Risk Manager buys protection: options bought, not futures or options written. The Asset Manager "
                              "trades those.")
        purpose = (purpose or "protection for the empire")[:120]
    q = derivatives.quote(conn, s, now)
    level = derivatives.spot(conn, s, now)
    if s["kind"] == "future":
        cost = derivatives.value_of(conn, s, level) * derivatives.data.FUTURE_MARGIN_BPS // derivatives.BPS * contracts
    elif side == "long":
        cost = q["ask"] * contracts
    else:
        cost = derivatives.writer_margin(conn, s, now, level) * contracts
    limit = naira(limits(conn, empire)["derivatives_limit_naira"])
    if not head and committed(conn, empire["account_id"]) + cost > limit:
        return _ask(conn, empire, player_id, "empire_derivative", f"{'Buy' if side == 'long' else 'Sell'} {contracts:,} {derivatives.describe(s)}",
                    cost, {"series_id": series_id, "side": side, "contracts": contracts, "purpose": purpose, "limit": limit}, now)
    result = derivatives.open_position(conn, empire["account_id"], series_id, side, contracts, now, player_id=player_id, purpose=purpose,
                                       limit=limit)
    empires._log(conn, empire["id"], f"{'Bought' if side == 'long' else 'Sold'} {contracts:,} {derivatives.describe(s)}"
                                     + (f" as a hedge: {purpose}" if purpose else "") + ".", now)
    return result


def close_derivative(conn: Connection, player_id, position_id: int, now: datetime) -> dict:
    from simulation import derivatives
    seat, empire = _seat(conn, player_id)
    if empire["head_player_id"] != player_id and seat["build"] not in ("asset_manager", "risk_manager"):
        raise EmpireError("The Asset Manager or the Risk Manager closes the empire's options and futures.")
    return derivatives.close_position(conn, empire["account_id"], position_id, now)


def _execute_derivative(conn: Connection, approval: dict, now: datetime) -> None:
    from simulation import derivatives
    empire = empires._empire(conn, approval["empire_id"])
    p = approval["payload"]
    try:
        derivatives.open_position(conn, empire["account_id"], p["series_id"], p["side"], p["contracts"], now,
                                  player_id=approval["asked_by"], purpose=p.get("purpose"), limit=p.get("limit"))
    except derivatives.DerivativesError as refused:
        raise EmpireError(str(refused)) from None


firm.EXECUTORS.update({"empire_borrow": _execute_borrow, "empire_short": _execute_short, "empire_derivative": _execute_derivative,
                       "empire_limits": _execute_limits})
firm.VIEWERS.update({"empire_borrow": _view, "empire_short": _view, "empire_derivative": _view, "empire_limits": _view})
firm.STAFF_RULES.update({"empire_borrow": _staff_rule, "empire_short": _staff_rule, "empire_derivative": _staff_rule,
                         "empire_limits": lambda conn, approval, now: (False, "The staff will not raise the limits.")})
for _key in LIMIT_KEYS:
    firm.ARTICLE_DEFAULTS.setdefault(_key, 0)
