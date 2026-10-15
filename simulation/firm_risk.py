"""The Risk Manager's teeth: limits on trading, the freeze, and the report at every Closing Bell.

  limits      the Risk Manager sets the most a member may put into one trade for the empire; a
              bigger trade, a first step into an industry the empire holds nothing in, or a trade
              that would break the treasury policy, waits for the Risk Manager's desk
  the freeze  the Risk Manager may stop a member trading for the empire; the head can lift it, on the record
  the report  at every Closing Bell the desk writes the empire's risk figures down, for good
"""

from __future__ import annotations

from datetime import datetime

from psycopg import Connection

from simulation import careers, clock, empires, exchange, firm
from simulation.empires import EmpireError, _log, _money, _one, _open, _rows, _text
from simulation.money import BPS, naira

TRADE_LIMIT_DEFAULT_NAIRA = None        # no limit until the Risk Manager sets one


def set_trade_limit(conn: Connection, player_id, limit_naira: int | None, now: datetime) -> None:
    """The Risk Manager (or the head, when there is none) sets the most one trade may be without approval."""
    with conn.transaction():
        state = _open(conn, now)
        seat, empire = firm._active(conn, player_id)
        _risk_desk(conn, seat, empire)
        if limit_naira is not None and not firm._whole(limit_naira, 1):
            raise EmpireError("A limit in naira above nought, or none.")
        firm.set_article(conn, empire["id"], "trade_limit_naira", limit_naira, state["period"], now)
        _log(conn, empire["id"], "The Risk Manager's desk set the most one trade may be without approval: "
                                 + (_money(naira(limit_naira)) if limit_naira else "no limit") + ".", now)


def _risk_desk(conn: Connection, seat: dict, empire: dict) -> None:
    if seat["build"] != "risk_manager" and not (empire["head_player_id"] == seat["player_id"]
                                                 and not firm.desk_members(conn, empire["id"], "risk_manager")):
        raise EmpireError("That is for the empire's Risk Manager (or the head, when the empire has none).")


def freeze(conn: Connection, player_id, member_id, frozen: bool, reason: str, now: datetime) -> None:
    """The kill switch. The Risk Manager stops a member trading for the empire; only the head can lift
    a freeze the Risk Manager put on, and that goes on the head's record."""
    with conn.transaction():
        state = _open(conn, now)
        seat, empire = firm._active(conn, player_id)
        is_head = empire["head_player_id"] == player_id
        if frozen:
            _risk_desk(conn, seat, empire)
        elif not is_head and seat["build"] != "risk_manager":
            raise EmpireError("A freeze is lifted by the Risk Manager, or by the head on the record.")
        target = _one(conn, "SELECT * FROM empire_seats WHERE empire_id = %s AND player_id = %s FOR UPDATE", (empire["id"], member_id))
        if target is None or member_id == empire["head_player_id"]:
            raise EmpireError("You can freeze a member's trading, not the head's.")
        reason = _text(reason or "")[:300]
        if not reason:
            raise EmpireError("Give your reason in writing.")
        conn.execute("UPDATE empire_seats SET frozen = %s WHERE id = %s", (frozen, target["id"]))
        if frozen:
            # Whatever the member had waiting for approval is dropped: a freeze stops trades already on their way, too.
            conn.execute("UPDATE empire_approvals SET status = 'lapsed', reason = 'The member was frozen.', decided_at = %s"
                         " WHERE empire_id = %s AND asked_by = %s AND kind IN ('trade', 'bond_trade') AND status = 'waiting'", (now, empire["id"], member_id))
        name = firm._name(conn, member_id)
        _log(conn, empire["id"], f"{name}'s trading for the empire was {'frozen' if frozen else 'unfrozen'}: {reason}", now)
        if not frozen and is_head and seat["build"] != "risk_manager":
            firm.ceo_note(conn, player_id, empire["id"], "unfreeze", f"Lifted the Risk Manager's freeze on {name}'s trading: \"{reason}\"",
                          state["period"], now, reference=f"unfreeze:{target['id']}:{now.isoformat()}")


def _frozen(conn: Connection, seat_id) -> bool:
    row = _one(conn, "SELECT frozen FROM empire_seats WHERE id = %s", (seat_id,))
    return bool(row and row["frozen"])


def gate_bond(conn: Connection, seat: dict, code: str, side: str, units: int, value: int, state: dict, now: datetime) -> dict | None:
    """A bond trade for an empire run by players waits for the Risk Manager's desk when it passes the
    limit for one trade, or would take the empire's cash below its policy."""
    if seat["empire_kind"] != "player":
        return None
    if _frozen(conn, seat["id"]):
        raise EmpireError("The Risk Manager has frozen your trading for the empire. Ask them, or the head, to lift it.")
    if seat["head_player_id"] == seat["player_id"] or seat["build"] == "risk_manager":
        return None
    empire = empires._empire(conn, seat["empire_id"])
    why = []
    limit = firm.article(conn, empire["id"], "trade_limit_naira")
    if limit and value > naira(limit):
        why.append(f"it is above the limit of {_money(naira(limit))} for one trade")
    if side == "buy":
        from simulation import firm_money
        rule, have = firm_money.policy(conn, empire["id"]), firm_money.mix(conn, empire, now)
        if (have["cash"] - value) * BPS < rule["cash_least_bps"] * max(have["total"], 1):
            why.append(f"it would break the treasury policy: cash would be less than {rule['cash_least_bps'] / 100:.0f}% of the empire")
    if not why:
        return None
    desk = "risk_manager" if (firm.desk_members(conn, empire["id"], "risk_manager") or firm.desk_staffed(conn, empire["id"], "risk_manager")) else "head"
    request = firm.ask(conn, empire, kind="bond_trade", desk=desk, asked_by=seat["player_id"],
                       title=f"{'Buy' if side == 'buy' else 'Sell'} {units:,} of {code} for about {_money(value)}", amount=value,
                       payload={"code": code, "side": side, "units": units, "why": why}, period=state["period"], now=now)
    return {"waiting": True, "approval_id": request["id"], "why": why}


def _bond_execute(conn: Connection, approval: dict, now: datetime) -> None:
    from simulation import bonds
    p = approval["payload"]
    seat = empires.seat_of(conn, approval["asked_by"])
    if seat is None or seat["empire_id"] != approval["empire_id"]:
        raise EmpireError("Whoever asked is no longer in the empire.")
    if _frozen(conn, seat["id"]):
        raise EmpireError("The member has been frozen since: the trade is not carried out.")
    state = careers.world_now(conn, now)
    try:
        done = bonds.trade(conn, account=seat["account_id"], code=p["code"], side=p["side"], units=p["units"], now=now)
    except bonds.BondError as refused:
        raise EmpireError(str(refused)) from None
    empires._within_trade_limit(conn, seat, state, done["value"], now)
    conn.execute("INSERT INTO empire_trades (empire_id, player_id, period, what, value, at) VALUES (%s, %s, %s, %s, %s, %s)",
                 (seat["empire_id"], seat["player_id"], state["period"], f"{p['side']} {p['units']:,} of {p['code']} (approved)", done["value"], now))


def gate_trade(conn: Connection, seat: dict, share: dict, side: str, kind: str, quantity: int, limit_price: int | None, value: int,
               state: dict, now: datetime) -> dict | None:
    """Before a member's trade for an empire run by players goes to the exchange: is it frozen, or
    does it need the Risk Manager's desk? Returns the request when it must wait."""
    if seat["empire_kind"] != "player":
        return None
    if _frozen(conn, seat["id"]):
        raise EmpireError("The Risk Manager has frozen your trading for the empire. Ask them, or the head, to lift it.")
    if seat["head_player_id"] == seat["player_id"] or seat["build"] == "risk_manager":
        return None
    empire = empires._empire(conn, seat["empire_id"])
    why = []
    limit = firm.article(conn, empire["id"], "trade_limit_naira")
    if limit and value > naira(limit):
        why.append(f"it is above the limit of {_money(naira(limit))} for one trade")
    if side == "buy":
        held_sectors = {r["sector"] for r in _rows(conn, "SELECT c.sector FROM share_owners o JOIN companies c ON c.id = o.company_id"
                                                         " WHERE o.account_id = %s", (seat["account_id"],))}
        sector = _one(conn, "SELECT sector FROM companies WHERE id = %s", (share["id"],))["sector"]
        if held_sectors and sector not in held_sectors:
            why.append("it takes the empire into an industry it holds nothing in")
        from simulation import firm_money
        breaches = firm_money.policy_breaches(conn, empire, now, extra_shares=value)
        if breaches:
            why.append("it would break the treasury policy: " + "; ".join(breaches))
    if not why:
        return None
    if not firm.desk_members(conn, empire["id"], "risk_manager") and not firm.desk_staffed(conn, empire["id"], "risk_manager"):
        desk = "head"
    else:
        desk = "risk_manager"
    request = firm.ask(conn, empire, kind="trade", desk=desk, asked_by=seat["player_id"],
                       title=f"{'Buy' if side == 'buy' else 'Sell'} {quantity:,} {share['ticker']} for about {_money(value)}",
                       amount=value, payload={"ticker": share["ticker"], "side": side, "kind": kind, "quantity": quantity, "limit_price": limit_price,
                                              "why": why, "venture": any("industry" in w for w in why)},
                       period=state["period"], now=now)
    return {"waiting": True, "approval_id": request["id"], "why": why}


def _trade_execute(conn: Connection, approval: dict, now: datetime) -> None:
    p = approval["payload"]
    seat = empires.seat_of(conn, approval["asked_by"])
    if seat is None or seat["empire_id"] != approval["empire_id"]:
        raise EmpireError("Whoever asked is no longer in the empire.")
    if _frozen(conn, seat["id"]):
        raise EmpireError("The member has been frozen since: the trade is not carried out.")
    state = careers.world_now(conn, now)
    empires._within_trade_limit(conn, seat, state, approval["amount"], now)
    try:
        exchange.place_order(conn, account=seat["account_id"], ticker=p["ticker"], side=p["side"], kind=p["kind"], quantity=p["quantity"],
                             limit_price=p["limit_price"], now=now)
    except exchange.ExchangeError as refused:
        raise EmpireError(str(refused)) from None
    conn.execute("INSERT INTO empire_trades (empire_id, player_id, period, what, value, at) VALUES (%s, %s, %s, %s, %s, %s)",
                 (seat["empire_id"], seat["player_id"], state["period"], f"{p['side']} {p['quantity']:,} {p['ticker']} (approved)", approval["amount"], now))


def _trade_view(conn: Connection, approval: dict, viewer_id, now: datetime) -> dict:
    from simulation import firm_money
    empire = empires._empire(conn, approval["empire_id"])
    return {"why": approval["payload"]["why"], "mix": firm_money.mix(conn, empire, now), "policy": firm_money.policy(conn, empire["id"])}


def _staff_trade_rule(conn: Connection, approval: dict, now: datetime) -> tuple[bool, str]:
    if any("treasury policy" in w for w in approval["payload"]["why"]):
        return False, "The staff will not break the treasury policy the members voted."
    return True, "The staff allowed it: within the policy."


def _settle_trade(conn: Connection, approval: dict, period: int):
    """An overruled refusal of a trade: did the price go the way the trade bet, by the next close?"""
    p = approval["payload"]
    row = _one(conn, "SELECT m.last_price, m.reference_price FROM market_instruments m JOIN companies c ON c.id = m.company_id WHERE c.ticker = %s",
               (p["ticker"],))
    if not row or not p.get("limit_price"):
        return None
    price = row["last_price"] or row["reference_price"]
    return price >= p["limit_price"] if p["side"] == "buy" else price <= p["limit_price"]


# ---------------------------------------------------------------------------
# The report at every Closing Bell
# ---------------------------------------------------------------------------

def figures(conn: Connection, empire: dict, now: datetime) -> dict:
    from simulation import firm_money, objectives
    have = objectives.wealth(conn, empire["account_id"], now)
    total = max(have["total"], 1)
    biggest = max(have["lines"], key=lambda l: l["value"], default=None)
    sectors: dict = {}
    for line in have["lines"]:
        sectors[line["sector"]] = sectors.get(line["sector"], 0) + line["value"]
    owed = firm.debt_of(conn, empire["id"])
    interest = sum(d["outstanding"] * d["rate_bps"] // BPS // 4 for d in _rows(conn, "SELECT * FROM empire_debts WHERE empire_id = %s"
                                                                                       " AND status IN ('open', 'called')", (empire["id"],)))
    before = _one(conn, "SELECT worth FROM empire_worth WHERE empire_id = %s ORDER BY period DESC LIMIT 1", (empire["id"],))
    return {"worth": have["total"] - owed, "cash": have["cash"], "shares": have["shares"], "bonds": have["bonds"], "owed": owed,
            "biggest": biggest["ticker"] if biggest else None, "biggest_bps": biggest["value"] * BPS // total if biggest else 0,
            "biggest_sector": max(sectors, key=sectors.get) if sectors else None,
            "biggest_sector_bps": max(sectors.values()) * BPS // total if sectors else 0,
            "gearing_bps": owed * BPS // total, "cash_cover": have["cash"] // interest if interest else None,
            "since_close_bps": (have["total"] - owed - before["worth"]) * BPS // before["worth"] if before and before["worth"] else None,
            "breaches": firm_money.policy_breaches(conn, empire, now)}


def _write_reports(conn: Connection, now: datetime) -> None:
    day = clock.to_lagos(now).date()
    for row in _rows(conn, "SELECT id FROM empires WHERE status = 'active' AND kind <> 'pension' ORDER BY id"):
        with conn.transaction():
            empire = empires._empire(conn, row["id"])
            conn.execute("INSERT INTO empire_risk_reports (empire_id, day, figures) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                         (empire["id"], day, firm._json(figures(conn, empire, now))))


def view(conn: Connection, seat: dict, empire: dict, state: dict, now: datetime) -> dict:
    reports = _rows(conn, "SELECT day, figures FROM empire_risk_reports WHERE empire_id = %s ORDER BY day DESC LIMIT 7", (empire["id"],))
    frozen = [firm._name(conn, r["player_id"]) for r in _rows(conn, "SELECT player_id FROM empire_seats WHERE empire_id = %s AND frozen"
                                                                     " AND player_id IS NOT NULL", (empire["id"],))]
    is_risk = seat["build"] == "risk_manager" or (empire["head_player_id"] == seat["player_id"]
                                                   and not firm.desk_members(conn, empire["id"], "risk_manager"))
    return {"reports": [{"day": r["day"], **r["figures"]} for r in reports], "now": figures(conn, empire, now),
            "trade_limit_naira": firm.article(conn, empire["id"], "trade_limit_naira"), "frozen": frozen, "you_set_limits": is_risk,
            "frozen_seats": [r["id"] for r in _rows(conn, "SELECT id FROM empire_seats WHERE empire_id = %s AND frozen", (empire["id"],))],
            "you_frozen": bool(_one(conn, "SELECT frozen FROM empire_seats WHERE id = %s", (seat["id"],))["frozen"])}


def _bell(conn: Connection, now: datetime) -> None:
    _write_reports(conn, now)


firm.EXECUTORS.update({"trade": _trade_execute, "bond_trade": _bond_execute})
firm.VIEWERS.update({"trade": _trade_view, "bond_trade": _trade_view})
firm.STAFF_RULES.update({"trade": _staff_trade_rule, "bond_trade": _staff_trade_rule})
firm.OVERRULE_SETTLERS["trade"] = _settle_trade
firm.ARTICLE_DEFAULTS["trade_limit_naira"] = TRADE_LIMIT_DEFAULT_NAIRA
firm.BELL.append(_bell)
firm.VIEW["risk"] = view


from simulation import lending_empire  # noqa: E402,F401  (an empire's borrowing and short selling, Stage 9)
from simulation import crashfund  # noqa: E402,F401  (the crash fund's approvals, Stage 9)
