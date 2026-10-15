"""The gap stage, Part 1: swaps.

A swap is a private contract between two parties: a player, an empire, or a bank. Two kinds:
  rate  one side pays a fixed rate on a sum, the other pays the Central Bank's rate on it, every quarter;
  oil   one side pays a fixed price for a number of barrels, the other pays the oil price that quarter.
Only the difference moves, at each quarter's close, from the first quarter after it is signed (the level for the
quarter that is running is already known, so it would be no bargain at all).

A bank takes the other side at once, at its own price (a little in its favour). Another player or empire must accept.
Inside an empire a swap is the Investment Banker's to structure (or the head's), then Legal Counsel drafts it, the
Risk Manager signs, and the head signs: each a request that passes up the usual way if a desk is slow.

Nobody holds collateral. If one side cannot pay, the other is owed what is missing (a shortfall, in default). Measuring
that exposure is the Risk Manager's work: each swap shows what it is worth to each side at today's levels.
"""

from __future__ import annotations

from datetime import datetime

from psycopg import Connection
from psycopg.rows import dict_row

from simulation import empires, firm, ledger
from simulation import world_data as data
from simulation.empires import EmpireError
from simulation.money import BPS


class SwapError(Exception):
    pass


def _rows(conn: Connection, sql: str, params=()) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def _one(conn: Connection, sql: str, params=()) -> dict | None:
    rows = _rows(conn, sql, params)
    return rows[0] if rows else None


def money(kobo: int) -> str:
    return f"₦{kobo / 100:,.0f}"


def _state(conn: Connection, now: datetime) -> dict:
    from simulation import careers
    return careers.world_now(conn, now)


# ---------------------------------------------------------------------------
# The levels the floating leg follows
# ---------------------------------------------------------------------------

def rate_for(conn: Connection, period: int) -> int:
    """The Central Bank's rate in force during a quarter (set at the close before it)."""
    row = _one(conn, "SELECT next_policy_rate_bps AS r FROM economy_results WHERE period = %s", (period - 1,))
    if row:
        return row["r"]
    row = _one(conn, "SELECT next_policy_rate_bps AS r FROM economy_results ORDER BY period DESC LIMIT 1")
    return row["r"] if row else data.NEUTRAL_RATE_BPS


def oil_for(conn: Connection, period: int | None = None) -> int:
    """Oil in naira, kobo a barrel: the price in force during a quarter (or the latest)."""
    row = (_one(conn, "SELECT oil_cents, fx FROM abroad_results WHERE period = %s", (period - 1,)) if period is not None else None) \
        or _one(conn, "SELECT oil_cents, fx FROM abroad_results ORDER BY period DESC LIMIT 1")
    cents, fx = (row["oil_cents"], row["fx"]) if row else (data.OIL_START_CENTS, data.FX_START)
    return cents * fx // 100


def _bank_fixed(conn: Connection, kind: str, proposer_side: str, now: datetime) -> int:
    """A bank's price: today's level, a little in the bank's favour."""
    state = _state(conn, now)
    if kind == "rate":
        level = rate_for(conn, state["period"] + 1)
        return level + data.SWAP_BANK_RATE_SPREAD_BPS if proposer_side == "pay_fixed" else max(level - data.SWAP_BANK_RATE_SPREAD_BPS, 0)
    level = oil_for(conn)
    spread = level * data.SWAP_BANK_OIL_SPREAD_BPS // BPS
    return level + spread if proposer_side == "pay_fixed" else max(level - spread, 1)


# ---------------------------------------------------------------------------
# Who is acting, for whom
# ---------------------------------------------------------------------------

def _acting(conn: Connection, player_id, for_empire: bool) -> tuple:
    """(account, empire or None). For an empire, the Investment Banker or the head acts."""
    if not for_empire:
        return ledger.player_account_id(conn, player_id), None
    seat, empire = firm._active(conn, player_id)
    if empire.get("kind") == "pension":
        raise SwapError("A pension fund does not deal in swaps.")
    if empire["head_player_id"] != player_id and seat["build"] != "investment_banker":
        raise SwapError("The Investment Banker structures swaps for the empire (or the head).")
    return empire["account_id"], empire


def _empire_of(conn: Connection, account) -> dict | None:
    return _one(conn, "SELECT * FROM empires WHERE account_id = %s", (account,))


def _counterparty(conn: Connection, counterparty: dict) -> tuple:
    """(account, bank company id or None)."""
    if counterparty.get("bank"):
        bank = _one(conn, "SELECT id, account_id FROM companies WHERE id = %s AND sector = 'banking' AND status = 'trading'",
                    (counterparty["bank"],))
        if bank is None:
            raise SwapError("Choose one of the banks.")
        return bank["account_id"], bank["id"]
    if counterparty.get("player"):
        row = _one(conn, "SELECT a.id FROM players p JOIN ledger_accounts a ON a.player_id = p.id WHERE lower(p.display_name) = lower(%s)",
                   (counterparty["player"],))
        if row is None:
            raise SwapError("There is no player of that name.")
        return row["id"], None
    if counterparty.get("empire"):
        row = _one(conn, "SELECT account_id FROM empires WHERE (id::text = %s OR lower(name) = lower(%s)) AND status = 'active'"
                         " AND kind <> 'pension'", (str(counterparty["empire"]), str(counterparty["empire"])))
        if row is None:
            raise SwapError("There is no open empire of that name.")
        return row["account_id"], None
    raise SwapError("Name the other side: a bank, a player or an empire.")


def _note(conn: Connection, account, words: str, now: datetime) -> None:
    empire = _empire_of(conn, account)
    if empire is not None:
        empires._log(conn, empire["id"], words, now)
    elif _one(conn, "SELECT 1 FROM ledger_accounts WHERE id = %s AND kind = 'player'", (account,)):
        conn.execute("INSERT INTO lending_events (account, kind, words, at) VALUES (%s, 'swap', %s, %s)", (account, words, now))


def describe(s: dict) -> str:
    q = f"{s['quarters']} quarter{'s' if s['quarters'] != 1 else ''}"
    if s["kind"] == "rate":
        return f"Rate swap on {money(s['notional'])}: {s['fixed_bps'] / 100:.2f}% fixed against the Central Bank's rate, {q}"
    return f"Oil swap on {s['barrels']:,} barrels a quarter: {money(s['fixed_price'])} a barrel fixed against the oil price, {q}"


# ---------------------------------------------------------------------------
# Proposing, signing, accepting
# ---------------------------------------------------------------------------

def propose(conn: Connection, player_id, *, kind: str, counterparty: dict, side: str, quarters: int, now: datetime,
            notional: int | None = None, barrels: int | None = None, fixed: int | None = None, for_empire: bool = False) -> dict:
    from simulation import derivatives
    with conn.transaction():
        state = _state(conn, now)
        account, empire = _acting(conn, player_id, for_empire)
        derivatives.unlock(conn, player_id, "advanced")
        if kind not in ("rate", "oil"):
            raise SwapError("A swap is on the interest rate or on oil.")
        if side not in ("pay_fixed", "receive_fixed"):
            raise SwapError("Pay the fixed side, or receive it.")
        if not isinstance(quarters, int) or isinstance(quarters, bool) or not 1 <= quarters <= data.SWAP_MOST_QUARTERS:
            raise SwapError(f"A swap runs from one to {data.SWAP_MOST_QUARTERS} quarters.")
        if kind == "rate":
            if not isinstance(notional, int) or isinstance(notional, bool) or not 0 < notional <= data.SWAP_MOST_NOTIONAL:
                raise SwapError(f"Name the sum, at most {money(data.SWAP_MOST_NOTIONAL)}.")
            barrels = None
        else:
            if not isinstance(barrels, int) or isinstance(barrels, bool) or not 0 < barrels <= data.SWAP_MOST_BARRELS:
                raise SwapError(f"Name the barrels a quarter, at most {data.SWAP_MOST_BARRELS:,}.")
            notional = None
        other, bank = _counterparty(conn, counterparty)
        if other == account:
            raise SwapError("A swap needs two different sides.")
        if empire is not None and _empire_of(conn, other) is not None and _empire_of(conn, other)["id"] == empire["id"]:
            raise SwapError("A swap needs two different sides.")
        seat = empires.seat_of(conn, player_id)
        if empire is None and seat is not None and seat.get("account_id") == other:
            raise SwapError("A member does not deal with their own empire.")
        if empire is not None and _one(conn, "SELECT 1 FROM empire_seats s JOIN ledger_accounts a ON a.player_id = s.player_id"
                                             " WHERE s.empire_id = %s AND a.id = %s", (empire["id"], other)):
            raise SwapError("An empire does not deal with its own members.")
        if bank:
            fixed = _bank_fixed(conn, kind, side, now)
        elif not isinstance(fixed, int) or isinstance(fixed, bool) or fixed <= 0 or (kind == "rate" and fixed > 10_000):
            raise SwapError("Name the fixed rate (in hundredths of a percent) or the fixed price (in kobo a barrel).")
        row = _one(conn, "INSERT INTO swaps (kind, proposer, proposer_side, counterparty, bank_company_id, notional, barrels, fixed_bps,"
                         " fixed_price, quarters, status, proposed_by, at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
                         " RETURNING *",
                   (kind, account, side, other, bank, notional, barrels, fixed if kind == "rate" else None,
                    fixed if kind == "oil" else None, quarters, "signing" if empire else "proposed", player_id, now))
        if empire is not None:
            _ask(conn, row, empire, "swap_draft", "lawyer", player_id, "proposer", state["period"], now)
            return {"swap_id": row["id"], "waiting": True, "status": "signing"}
        return _after_proposer(conn, row, now)


def _after_proposer(conn: Connection, swap: dict, now: datetime) -> dict:
    """The proposer's side is signed: a bank takes it at once; anybody else is asked."""
    if swap["bank_company_id"]:
        return _activate(conn, swap, None, now)
    conn.execute("UPDATE swaps SET status = 'proposed' WHERE id = %s", (swap["id"],))
    _note(conn, swap["counterparty"], f"A swap is offered to you: {describe(swap)}. You would "
                                      f"{'receive' if swap['proposer_side'] == 'pay_fixed' else 'pay'} the fixed side.", now)
    return {"swap_id": swap["id"], "status": "proposed"}


def accept(conn: Connection, player_id, swap_id: int, now: datetime, *, for_empire: bool = False) -> dict:
    from simulation import derivatives
    with conn.transaction():
        state = _state(conn, now)
        account, empire = _acting(conn, player_id, for_empire)
        swap = _one(conn, "SELECT * FROM swaps WHERE id = %s AND counterparty = %s AND status = 'proposed' FOR UPDATE", (swap_id, account))
        if swap is None:
            raise SwapError("There is no such swap offered to you.")
        derivatives.unlock(conn, player_id, "advanced")
        if empire is not None:
            conn.execute("UPDATE swaps SET status = 'countersigning', accepted_by = %s WHERE id = %s", (player_id, swap_id))
            _ask(conn, swap, empire, "swap_draft", "lawyer", player_id, "counter", state["period"], now)
            return {"swap_id": swap_id, "waiting": True, "status": "countersigning"}
        return _activate(conn, swap, player_id, now)


def decline(conn: Connection, player_id, swap_id: int, now: datetime, *, for_empire: bool = False) -> dict:
    with conn.transaction():
        account, _ = _acting(conn, player_id, for_empire)
        swap = _one(conn, "SELECT * FROM swaps WHERE id = %s AND status IN ('proposed', 'signing') AND (counterparty = %s OR proposer = %s)"
                          " FOR UPDATE", (swap_id, account, account))
        if swap is None:
            raise SwapError("There is no such swap waiting.")
        status = "cancelled" if swap["proposer"] == account else "declined"
        conn.execute("UPDATE swaps SET status = %s WHERE id = %s", (status, swap_id))
        _note(conn, swap["proposer"] if status == "declined" else swap["counterparty"],
              f"The swap was {status}: {describe(swap)}.", now)
        return {"status": status}


def _activate(conn: Connection, swap: dict, accepted_by, now: datetime) -> dict:
    state = _state(conn, now)
    first = state["period"] + 1
    payer, other = (swap["proposer"], swap["counterparty"]) if swap["proposer_side"] == "pay_fixed" else (swap["counterparty"], swap["proposer"])
    conn.execute("UPDATE swaps SET status = 'active', fixed_payer = %s, float_payer = %s, first_period = %s, last_period = %s,"
                 " accepted_by = coalesce(accepted_by, %s), active_at = %s WHERE id = %s",
                 (payer, other, first, first + swap["quarters"] - 1, accepted_by, now, swap["id"]))
    for party in (swap["proposer"], swap["counterparty"]):
        _note(conn, party, f"The swap is signed and runs from the close of the next quarter: {describe(swap)}.", now)
    return {"swap_id": swap["id"], "status": "active", "fixed": swap["fixed_bps"] if swap["kind"] == "rate" else swap["fixed_price"],
            "first_period": first}


# Inside an empire: Legal Counsel drafts, the Risk Manager signs, the head signs (each passes up if the desk is slow).

def _ask(conn: Connection, swap: dict, empire: dict, kind: str, desk: str, asked_by, side: str, period: int, now: datetime) -> None:
    titles = {"swap_draft": "Draft the swap", "swap_risk": "Sign the swap's risk", "swap_sign": "Sign the swap"}
    firm.ask(conn, empire, kind=kind, desk=desk, asked_by=asked_by, title=f"{titles[kind]}: {describe(swap)}",
             amount=swap["notional"] or swap["barrels"] * swap["fixed_price"], payload={"swap_id": swap["id"], "side": side,
                                                                                       "why": [describe(swap)]},
             period=period, now=now)


def _draft(conn: Connection, approval: dict, now: datetime) -> None:
    swap = _one(conn, "SELECT * FROM swaps WHERE id = %s FOR UPDATE", (approval["payload"]["swap_id"],))
    words = (f"{describe(swap)}. The fixed side pays the fixed {'rate on the sum' if swap['kind'] == 'rate' else 'price for the barrels'}; "
             f"the floating side pays the {'Central Bank rate in force that quarter' if swap['kind'] == 'rate' else 'oil price in force that quarter'}; "
             "only the difference is paid, at each quarter's close. No collateral is held: what one side fails to pay is owed to the "
             "other. Neither side may end it early.")
    conn.execute("UPDATE swaps SET contract = %s WHERE id = %s", (words, swap["id"]))
    empire = empires._empire(conn, approval["empire_id"])
    _ask(conn, swap, empire, "swap_risk", "risk_manager", approval["asked_by"], approval["payload"]["side"], approval["period"], now)


def _risk(conn: Connection, approval: dict, now: datetime) -> None:
    swap = _one(conn, "SELECT * FROM swaps WHERE id = %s", (approval["payload"]["swap_id"],))
    empire = empires._empire(conn, approval["empire_id"])
    _ask(conn, swap, empire, "swap_sign", "head", approval["asked_by"], approval["payload"]["side"], approval["period"], now)


def _sign(conn: Connection, approval: dict, now: datetime) -> None:
    swap = _one(conn, "SELECT * FROM swaps WHERE id = %s FOR UPDATE", (approval["payload"]["swap_id"],))
    if approval["payload"]["side"] == "proposer" and swap["status"] == "signing":
        _after_proposer(conn, swap, now)
    elif approval["payload"]["side"] == "counter" and swap["status"] == "countersigning":
        _activate(conn, swap, None, now)
    else:
        raise EmpireError("That swap is no longer waiting to be signed.")


def _refused(conn: Connection, approval: dict, now: datetime) -> None:
    swap = _one(conn, "SELECT * FROM swaps WHERE id = %s FOR UPDATE", (approval["payload"]["swap_id"],))
    if swap and swap["status"] in ("signing", "countersigning"):
        status = "cancelled" if approval["payload"]["side"] == "proposer" else "declined"
        conn.execute("UPDATE swaps SET status = %s WHERE id = %s", (status, swap["id"]))


def _view(conn: Connection, approval: dict, viewer_id, now: datetime) -> dict:
    swap = _one(conn, "SELECT * FROM swaps WHERE id = %s", (approval["payload"]["swap_id"],))
    return {"why": approval["payload"].get("why", []), "contract": swap and swap["contract"]}


def _staff(kind: str):
    def rule(conn: Connection, approval: dict, now: datetime) -> tuple[bool, str]:
        if kind == "swap_sign":
            return False, "The staff do not sign swaps for the head."
        if kind == "swap_risk":
            swap = _one(conn, "SELECT * FROM swaps WHERE id = %s", (approval["payload"]["swap_id"],))
            empire = empires._empire(conn, approval["empire_id"])
            worth = empires.worth(conn, empire, now)["total"]
            size = swap["notional"] or swap["barrels"] * swap["fixed_price"]
            return (size <= max(worth, 0) // 10, "The staff signed: the swap is no more than a tenth of what the empire is worth."
                    if size <= max(worth, 0) // 10 else "The staff would not sign a swap this large.")
        return True, "The staff drafted the swap's terms."
    return rule


for _kind, _fn in (("swap_draft", _draft), ("swap_risk", _risk), ("swap_sign", _sign)):
    firm.EXECUTORS[_kind] = _fn
    firm.VIEWERS[_kind] = _view
    firm.STAFF_RULES[_kind] = _staff(_kind)
    firm.REFUSERS[_kind] = _refused


# ---------------------------------------------------------------------------
# At each quarter's close: the payments
# ---------------------------------------------------------------------------

def close(conn: Connection, period: int, now: datetime) -> dict:
    if _one(conn, "SELECT to_regclass('swaps') IS NOT NULL AS ok")["ok"] is not True:
        return {}
    from simulation import lending
    paid, owed = 0, 0
    for swap in _rows(conn, "SELECT * FROM swaps WHERE status = 'active' AND first_period <= %s ORDER BY id FOR UPDATE", (period,)):
        if period <= swap["last_period"] and not _one(conn, "SELECT 1 FROM swap_payments WHERE swap_id = %s AND period = %s",
                                                      (swap["id"], period)):
            if swap["kind"] == "rate":
                floating = rate_for(conn, period)
                net = swap["notional"] * (floating - swap["fixed_bps"]) // BPS // 4
            else:
                floating = oil_for(conn, period)
                net = swap["barrels"] * (floating - swap["fixed_price"])
            payer, receiver = (swap["float_payer"], swap["fixed_payer"]) if net > 0 else (swap["fixed_payer"], swap["float_payer"])
            amount = abs(net)
            got = 0
            if amount:
                got = ledger.pay_up_to(conn, payer=payer, receiver=receiver, wanted=amount, kind="swap_payment",
                                       memo=f"Swap {swap['id']}, the quarter's difference", period=period)
                if got < amount:
                    lending.record_shortfall(conn, payer, receiver, amount - got, f"Swap {swap['id']}", period, now)
                    owed += amount - got
            conn.execute("INSERT INTO swap_payments (swap_id, period, floating, amount, payer, receiver, paid, at)"
                         " VALUES (%s, %s, %s, %s, %s, %s, %s, %s)", (swap["id"], period, floating, amount, payer, receiver, got, now))
            paid += got
        if period >= swap["last_period"]:
            conn.execute("UPDATE swaps SET status = 'ended' WHERE id = %s", (swap["id"],))
    return {"paid": paid, "owed": owed}


# ---------------------------------------------------------------------------
# What the two sides see
# ---------------------------------------------------------------------------

def value_to(conn: Connection, swap: dict, account) -> int:
    """What the swap is worth to one side at today's levels: the quarters left at today's difference."""
    if swap["status"] != "active":
        return 0
    state = _state(conn, _one(conn, "SELECT now() AS n")["n"])
    left = max(swap["last_period"] - max(state["period"], swap["first_period"] - 1), 0)
    if swap["kind"] == "rate":
        per = swap["notional"] * (rate_for(conn, state["period"] + 1) - swap["fixed_bps"]) // BPS // 4
    else:
        per = swap["barrels"] * (oil_for(conn) - swap["fixed_price"])
    worth = per * left
    return worth if account == swap["fixed_payer"] else -worth


def view(conn: Connection, accounts: list) -> list[dict]:
    out = []
    for s in _rows(conn, "SELECT s.*, (SELECT name FROM companies WHERE id = s.bank_company_id) AS bank FROM swaps s"
                         " WHERE (s.proposer = ANY(%s) OR s.counterparty = ANY(%s)) AND s.status NOT IN ('declined', 'cancelled')"
                         " ORDER BY s.id DESC LIMIT 40", (accounts, accounts)):
        mine = s["proposer"] if s["proposer"] in accounts else s["counterparty"]
        other = s["counterparty"] if mine == s["proposer"] else s["proposer"]
        other_name = s["bank"] or _name_of(conn, other)
        side = s["proposer_side"] if mine == s["proposer"] else ("receive_fixed" if s["proposer_side"] == "pay_fixed" else "pay_fixed")
        payments = _rows(conn, "SELECT period, floating, amount, payer, paid FROM swap_payments WHERE swap_id = %s ORDER BY period", (s["id"],))
        out.append({"id": s["id"], "kind": s["kind"], "name": describe(s), "status": s["status"], "side": side, "other": other_name,
                    "yours_to_answer": s["status"] == "proposed" and mine == s["counterparty"], "empire_side": mine != accounts[0], "contract": s["contract"],
                    "first_period": s["first_period"], "last_period": s["last_period"], "value": value_to(conn, s, mine),
                    "payments": [{"period": p["period"], "floating": p["floating"],
                                  "amount": (p["paid"] if p["payer"] != mine else -p["paid"]), "unpaid": p["amount"] - p["paid"]}
                                 for p in payments]})
    return out


def _name_of(conn: Connection, account) -> str:
    row = _one(conn, "SELECT coalesce((SELECT name FROM empires WHERE account_id = a.id), (SELECT display_name FROM players WHERE id = a.player_id),"
                     " a.name) AS n FROM ledger_accounts a WHERE a.id = %s", (account,))
    return row["n"] if row else "another side"


def _players_swaps(conn: Connection) -> dict:
    """For players' net worth: what their swaps are worth at today's levels."""
    out: dict = {}
    if _one(conn, "SELECT to_regclass('swaps') IS NOT NULL AS ok")["ok"] is not True:
        return out
    for s in _rows(conn, "SELECT * FROM swaps WHERE status = 'active'"):
        for account in (s["fixed_payer"], s["float_payer"]):
            if _one(conn, "SELECT 1 FROM ledger_accounts WHERE id = %s AND kind = 'player'", (account,)):
                cash, inv = out.get(account, (0, 0))
                out[account] = (cash, inv + value_to(conn, s, account))
    return out


def _register() -> None:
    from simulation import marketview
    if _players_swaps not in marketview._OTHER_HOLDINGS:
        marketview._OTHER_HOLDINGS.append(_players_swaps)


_register()
