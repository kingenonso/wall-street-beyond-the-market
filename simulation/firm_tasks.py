"""The firm's work and what the world throws at it.

  tasks          four kinds (invest, rescue a struggling company, defend a holding, raise money), up
                 to three in hand at once, one of each kind started in a quarter; the head sets their
                 priority and gives each step to a member
  the shortlist  the Investment Banker brings the board three companies; the head picks the next
                 investment from the banker's list instead of the server's draw
  rivals         each empire has a rival in its division, and a head-to-head score
  events         a lender calls in a loan, a holding collapses, a regulator inspects, a buyer makes an
                 offer with a deadline: two or three desks must answer in time, and the head makes the call
  insurance      the Risk Manager buys cover against what may happen, from the insurance companies

Nothing here makes money. A fine goes to the Treasury, a claim is paid by the insurer from its own cash,
and a sale to a buyer is paid by the buyer.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from psycopg import Connection, errors

from simulation import (
    careers,
    clock,
    empires,
    exchange,
    firm,
    leagues,
    ledger,
    marketview,
    objectives,
)
from simulation.empires import (
    BUILD_NAMES,
    EmpireError,
    _log,
    _money,
    _one,
    _open,
    _roll,
    _rows,
    _text,
)
from simulation.money import BPS, apply_bps, naira

OPEN_TASKS_MOST = 3
TASK_KINDS = {
    "investment": "Invest in a company",
    "rescue": "Rescue a company that is struggling",
    "defend": "Defend a holding that is under pressure",
    "raise_money": "Raise money for the empire",
}
DEFEND_FALL_BPS = 1000              # a holding is under pressure when its price is 10% below what the empire paid on average, or a bid is open for it
# The chains name three builds, not six (owner, 9 November 2026). The Accountant's check is the Asset Manager's,
# the Legal Counsel's reading of the paper is the Investment Banker's, and the research note that opened the
# defence sits with the desk that now keeps the accounts. The wording of each step is kept.
RAISE_STEPS = (
    ("investment_banker", None, "Design the raising: a loan, a bond or a stake", "The design, to the Asset Manager"),
    ("asset_manager", None, "Check what the empire can carry", "The check, to the Risk Manager"),
    ("risk_manager", None, "Approve the risk", "The approval, to the Investment Banker"),
    ("investment_banker", None, "Read the paper and strike out the traps", "The paper, to the head"),
    ("head", None, "Sign", "The money, in the empire's account"),
)
DEFEND_STEPS = (
    ("asset_manager", "jr_results", "Find out what is happening to the company", "A research note, to the same desk for the accounts"),
    ("asset_manager", "ac_ratios", "Check its accounts: is it still sound?", "A review, to the Risk Manager"),
    ("risk_manager", "rm_stress", "What would a bad quarter do to it now?", "A risk assessment, to the Investment Banker"),
    ("investment_banker", "lw_control", "Who controls it, and is a bid in the way?", "An opinion, to the head"),
    ("head", None, "Decide: hold, or sell", "The decision, recorded and judged as the next quarter closes"),
)
HAPPENING_CHANCE_BPS = 2500         # at each Closing Bell, the chance something happens to an empire with players in it
HAPPENING_HOURS = 48
COVER = {"holding_collapse": ("A holding collapses", 600), "inspection": ("A regulator's inspection", 300),
         "headquarters": ("The headquarters falls down", 250)}    # premium a quarter, in bps of the cover
COVER_MOST_BPS = 1000               # cover up to a tenth of the empire's worth, for each kind
COVER_QUARTERS = 4
INSPECTION_FINE_BPS = 50            # a failed inspection costs half of one percent of the empire's worth, paid to the Treasury
OFFER_PREMIUM_BPS = (500, 2500)
STAFF_RIGHT_BPS = 7000              # the staff give the right answer to an event seven times in ten


def _steps_for(kind: str):
    return {"investment": empires.INVESTMENT_STEPS, "rescue": empires.INVESTMENT_STEPS, "defend": DEFEND_STEPS, "raise_money": RAISE_STEPS}[kind]


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------

def _held(conn: Connection, empire: dict) -> list[dict]:
    """What the empire holds."""
    return _rows(conn, "SELECT o.company_id, o.shares, c.ticker, c.name FROM share_owners o JOIN companies c ON c.id = o.company_id"
                       " WHERE o.account_id = %s AND o.shares > 0 ORDER BY c.ticker", (empire["account_id"],))


def _paid_average(conn: Connection, account, company_id) -> int | None:
    row = _one(conn, "SELECT sum(t.price * t.quantity)::bigint AS cost, sum(t.quantity)::bigint AS q FROM market_trades t"
                     " JOIN market_orders o ON o.id = t.buy_order_id WHERE o.account_id = %s AND o.company_id = %s", (account, company_id))
    return row["cost"] // row["q"] if row and row["q"] else None


def _pressed(conn: Connection, empire: dict, now: datetime) -> list[dict]:
    """The empire's holdings that are under pressure: well below what it paid, or the subject of a bid."""
    prices = {s["id"]: s for s in marketview._shares(conn, exchange.session_of(now)[0])}
    out = []
    from simulation import corporate
    for h in _held(conn, empire):
        price = prices[h["company_id"]]["price"]
        paid = _paid_average(conn, empire["account_id"], h["company_id"])
        if corporate.bid_for(conn, h["company_id"]) or (paid and price * BPS < paid * (BPS - DEFEND_FALL_BPS)):
            out.append({**h, "price": price, "paid": paid})
    return out


def _rescue_target(conn: Connection, empire: dict, period: int, now: datetime):
    ctx = {"conn": conn, "now": now, "period": period, "player_id": f"empire:{empire['id']}", "wage_index_bps": BPS}
    held = {row["company_id"] for row in _held(conn, empire)}
    weak = {c["company_id"] for c in objectives._strained(conn, period - 1)}
    weak |= {c["company_id"] for c in objectives._filed(conn, period - 1) if (c["credit_rating"] or "")[:1] in ("B", "C")
             and c["credit_rating"] not in ("BBB",)}
    fits = []
    for company in sorted(objectives._filed(conn, period - 1), key=lambda c: c["ticker"]):
        if company["company_id"] in weak and company["company_id"] not in held:
            probe = {**ctx, "target": company["company_id"]}
            if all(objectives.TEMPLATES[code].offer(probe) for _b, code, _w, _h in empires.INVESTMENT_STEPS if code and code != "em_execute"):
                fits.append(company)
    return fits[_roll(conn, "rescue", empire["id"], period) % len(fits)] if fits else None


def start(conn: Connection, head_id, kind: str, priority: int, now: datetime, target_id=None) -> dict:
    """The head starts a task of a kind. Up to three can be in hand at once, one of each kind a quarter."""
    with conn.transaction():
        state = _open(conn, now)
        empire = empires._head(conn, head_id)
        return start_inside(conn, empire, kind, priority, state["period"], now, started_by=head_id, target_id=target_id)


def start_inside(conn: Connection, empire: dict, kind: str, priority: int, period: int, now: datetime, started_by=None, target_id=None) -> dict:
    if kind not in TASK_KINDS:
        raise EmpireError("There is no such kind of task.")
    if not firm._whole(priority, 1, 3):
        raise EmpireError("A priority from 1 (first) to 3.")
    if empire["status"] != "active":
        raise EmpireError("The empire is not open yet.")
    if _one(conn, "SELECT count(*) AS n FROM empire_tasks WHERE empire_id = %s AND status = 'open'", (empire["id"],))["n"] >= OPEN_TASKS_MOST:
        raise EmpireError(f"The empire already has {OPEN_TASKS_MOST} tasks in hand. Finish one first.")
    if _one(conn, "SELECT 1 FROM empire_tasks WHERE empire_id = %s AND kind = %s AND period = %s", (empire["id"], kind, period)):
        raise EmpireError("A task of that kind has already been started this quarter. One of each kind a quarter.")
    if kind == "investment":
        if target_id is not None:
            target = next((c for c in objectives._filed(conn, period - 1) if str(c["company_id"]) == str(target_id)), None)
            if target is None:
                raise EmpireError("That company has no filed accounts to work from.")
            return _insert(conn, empire, kind, target, priority, period, now, started_by, _investment_amount(conn, empire))
        task = empires._start_task(conn, empire, period, now, started_by=started_by)
        conn.execute("UPDATE empire_tasks SET priority = %s WHERE id = %s", (priority, task["id"]))
        return task
    if kind == "rescue":
        target = _rescue_target(conn, empire, period, now)
        if target is None:
            raise EmpireError("No struggling company can be looked at this quarter.")
        return _insert(conn, empire, kind, target, priority, period, now, started_by, _investment_amount(conn, empire) // 2)
    if kind == "defend":
        pressed = _pressed(conn, empire, now)
        if not pressed:
            raise EmpireError("None of the empire's holdings is under pressure: nothing to defend.")
        target = pressed[_roll(conn, "defend", empire["id"], period) % len(pressed)]
        return _insert(conn, empire, kind, target, priority, period, now, started_by, 0)
    if not firm.player_run(empire):
        raise EmpireError("An empire run by the computer does not borrow.")
    return _insert(conn, empire, kind, None, priority, period, now, started_by, 0)


def _investment_amount(conn: Connection, empire: dict) -> int:
    from simulation import world_data as data
    most = data.CEO_TASK_MOST_NAIRA if empires.is_ceo(conn, empire["head_player_id"]) else data.TASK_MOST_NAIRA
    amount = min(apply_bps(ledger.balance(conn, empire["account_id"]), data.TASK_SHARE_OF_CASH_BPS), naira(most))
    if amount < naira(100_000):
        raise EmpireError("The empire has too little cash to make an investment worth the work.")
    return amount


def _insert(conn: Connection, empire: dict, kind: str, target, priority: int, period: int, now: datetime, started_by, amount: int) -> dict:
    task = _one(conn, "INSERT INTO empire_tasks (empire_id, kind, company_id, period, amount, started_by, at, priority)"
                      " VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING *",
                (empire["id"], kind, target["company_id"] if target else None, period, amount, started_by, now, priority))
    for position, (build, template, what, hands_on) in enumerate(_steps_for(kind), 1):
        conn.execute("INSERT INTO empire_task_steps (task_id, position, build, what, hands_on, template, status, ready_at)"
                     " VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                     (task["id"], position, build, what, hands_on, template, "current" if position == 1 else "waiting", now if position == 1 else None))
    about = f" ({target['name']}, {target['ticker']})" if target else ""
    _log(conn, empire["id"], f"A task was started: {TASK_KINDS[kind].lower()}{about}. Priority {priority}.", now)
    return task


def set_priority(conn: Connection, head_id, task_id: int, priority: int, now: datetime) -> None:
    with conn.transaction():
        _open(conn, now)
        empire = empires._head(conn, head_id)
        if not firm._whole(priority, 1, 3):
            raise EmpireError("A priority from 1 (first) to 3.")
        if not conn.execute("UPDATE empire_tasks SET priority = %s WHERE id = %s AND empire_id = %s AND status = 'open'",
                            (priority, task_id, empire["id"])).rowcount:
            raise EmpireError("There is no such task open.")


def assign_step(conn: Connection, head_id, step_id: int, member_id, now: datetime) -> None:
    """The head gives a step to one member of its build (or takes it back). Only they may take it."""
    with conn.transaction():
        _open(conn, now)
        empire = empires._head(conn, head_id)
        step = empires._step(conn, step_id)
        if step is None or step["empire_id"] != empire["id"] or step["task_status"] != "open" or step["status"] == "done" or step["build"] == "head":
            raise EmpireError("There is no such step waiting.")
        if member_id is not None and member_id not in firm.desk_members(conn, empire["id"], step["build"]):
            raise EmpireError(f"They are not on the {BUILD_NAMES[step['build']]} desk.")
        conn.execute("UPDATE empire_task_steps SET assigned_to = %s WHERE id = %s", (member_id, step_id))


def decide_defence(conn: Connection, head_id, step_id: int, choice: str, reason: str, now: datetime) -> None:
    """The head's call in a defence: hold the shares, or sell them. It goes on the head's record and
    is judged as the next quarter closes: did the price go the way the head bet?"""
    with conn.transaction():
        state = _open(conn, now)
        empire = empires._head(conn, head_id)
        step = empires._step(conn, step_id)
        if step is None or step["empire_id"] != empire["id"] or step["build"] != "head" or step["status"] != "current":
            raise EmpireError("There is nothing waiting for your decision.")
        task = _one(conn, "SELECT * FROM empire_tasks WHERE id = %s FOR UPDATE", (step["task_id"],))
        if task["kind"] != "defend" or choice not in ("hold", "sell"):
            raise EmpireError("Hold, or sell.")
        reason = _text(reason or "")[:300]
        if not reason:
            raise EmpireError("Give your reason in writing.")
        price = next(s["price"] for s in marketview._shares(conn, exchange.session_of(now)[0]) if s["id"] == task["company_id"])
        conn.execute("UPDATE empire_tasks SET decision = %s WHERE id = %s", (firm._json({"choice": choice, "price": price, "reason": reason}), task["id"]))
        firm.sign_opinion(conn, head_id, "head", empire["id"], "defence", f"{'Hold' if choice == 'hold' else 'Sell'} the shares under pressure",
                          {"choice": choice, "price": price, "company_id": str(task["company_id"])}, state["period"], state["period"] + 1, now)
        empires._finish_step(conn, step, now, done_by=head_id)


def _settle_defence(conn: Connection, opinion: dict, period: int, now: datetime):
    price = next((s["price"] for s in marketview._shares(conn, exchange.session_of(now)[0]) if str(s["id"]) == opinion["call"]["company_id"]), None)
    if price is None:
        return ("void", "The company is no longer listed.")
    rose = price > opinion["call"]["price"]
    right = rose if opinion["call"]["choice"] == "hold" else not rose
    return ("right" if right else "wrong", f"The price went from {_money(opinion['call']['price'])} to {_money(price)}.")


# Raising money as a task: its steps are done by the desks' real decisions.
def _raise_step(conn: Connection, empire: dict, build: str, who, now: datetime) -> None:
    step = _one(conn, "SELECT s.* FROM empire_task_steps s JOIN empire_tasks t ON t.id = s.task_id WHERE t.empire_id = %s AND t.kind = 'raise_money'"
                      " AND t.status = 'open' AND s.status = 'current' AND s.build = %s ORDER BY t.id LIMIT 1 FOR UPDATE OF s", (empire["id"], build))
    if step:
        empires._finish_step(conn, {**step, "empire_id": empire["id"]}, now, done_by=who)


def _on_designed(conn: Connection, empire: dict, approval: dict, now: datetime) -> None:
    _raise_step(conn, empire, "investment_banker", approval["asked_by"], now)


def _on_decided(conn: Connection, approval: dict, seat: dict, now: datetime) -> None:
    if approval["status"] != "approved":
        return
    empire = empires._empire(conn, approval["empire_id"])
    build = {"raise_check": "asset_manager", "raise_risk": "risk_manager", "raise_sign": "head"}.get(approval["kind"])
    if build == "head" and approval["payload"].get("kind") == "stake":
        return                                             # a stake offer is done only when the money has come in (see _on_raised)
    if build:
        _raise_step(conn, empire, build, approval["decided_by"] if approval["decided_as"] == "desk" or build == "head" else None, now)


def _on_raised(conn: Connection, empire: dict, raised: dict, now: datetime) -> None:
    if raised["kind"] == "stake":
        _raise_step(conn, empire, "head", empire["head_player_id"], now)


def _on_read(conn: Connection, empire: dict, doc: dict, now: datetime) -> None:
    if (doc["ref"] or "").startswith("raise:"):
        _raise_step(conn, empire, "investment_banker", doc["reviewed_by"], now)


# ---------------------------------------------------------------------------
# The banker's shortlist
# ---------------------------------------------------------------------------

def shortlist(conn: Connection, player_id, company_ids: list, reason: str, now: datetime) -> dict:
    """The Investment Banker brings the board three companies the empire does not hold, with a
    reason. The head picks one, and the next investment task is on it."""
    with conn.transaction():
        state = _open(conn, now)
        seat, empire = firm._active(conn, player_id)
        if seat["build"] != "investment_banker":
            raise EmpireError("The shortlist is brought by the empire's Investment Banker.")
        if not isinstance(company_ids, list) or len(set(company_ids)) != 3:
            raise EmpireError("Bring three different companies.")
        company_ids = [str(c) for c in company_ids]
        filed = {str(c["company_id"]): c for c in objectives._filed(conn, state["period"] - 1)}
        held = {str(h["company_id"]) for h in _held(conn, empire)}
        if any(c not in filed or c in held for c in company_ids):
            raise EmpireError("Each must be a listed company with filed accounts that the empire does not already hold.")
        reason = _text(reason or "")[:400]
        if len(reason) < 10:
            raise EmpireError("Give the board your case in a sentence or two.")
        if _one(conn, "SELECT 1 FROM empire_approvals WHERE empire_id = %s AND kind = 'shortlist' AND status = 'waiting'", (empire["id"],)):
            raise EmpireError("A shortlist is already waiting for the head.")
        prices = {s["id"]: s["price"] for s in marketview._shares(conn, exchange.session_of(now)[0])}
        names = ", ".join(filed[c]["ticker"] for c in company_ids)
        approval = firm.ask(conn, empire, kind="shortlist", desk="head", asked_by=player_id, title=f"The banker's shortlist: {names}",
                            payload={"targets": company_ids, "reason": reason, "prices": {c: prices.get(filed[c]["company_id"]) for c in company_ids}},
                            period=state["period"], now=now)
        return {"approval_id": approval["id"]}


def pick(conn: Connection, head_id, approval_id: int, company_id, now: datetime) -> dict:
    """The head picks one company from the banker's shortlist. The investment task is started on it,
    and the banker's choice is judged as the next quarter closes against the market as a whole."""
    with conn.transaction():
        state = _open(conn, now)
        empire = empires._head(conn, head_id)
        approval = firm._approval(conn, approval_id, empire["id"])
        if approval["kind"] != "shortlist" or approval["status"] != "waiting":
            raise EmpireError("There is no shortlist waiting for you.")
        company_id = str(company_id)
        if company_id not in approval["payload"]["targets"]:
            raise EmpireError("Pick one of the three on the shortlist.")
        task = start_inside(conn, empire, "investment", 1, state["period"], now, started_by=head_id, target_id=company_id)
        conn.execute("UPDATE empire_approvals SET status = 'approved', reason = %s, decided_by = %s, decided_as = 'head', decided_at = %s WHERE id = %s",
                     (f"Picked company {company_id}", head_id, now, approval_id))
        firm.sign_opinion(conn, approval["asked_by"], "investment_banker", empire["id"], "shortlist", approval["title"],
                          {"picked": company_id, "price": approval["payload"]["prices"].get(company_id), "index": objectives.index_now(conn, now)},
                          state["period"], state["period"] + 1, now)
        return {"task_id": task["id"]}


def _settle_shortlist(conn: Connection, opinion: dict, period: int, now: datetime):
    call = opinion["call"]
    price = next((s["price"] for s in marketview._shares(conn, exchange.session_of(now)[0]) if str(s["id"]) == call["picked"]), None)
    if price is None or not call.get("price") or not call.get("index"):
        return ("void", "It could not be checked.")
    index = objectives.index_now(conn, now)
    beat = price * call["index"] > index * call["price"]
    return ("right" if beat else "wrong", f"The company the board picked moved {(price - call['price']) * 100 / call['price']:+.1f}%; "
                                          f"the market {(index - call['index']) * 100 / call['index']:+.1f}%.")


# ---------------------------------------------------------------------------
# Rivals
# ---------------------------------------------------------------------------

def _assign_rivals(conn: Connection, now: datetime) -> None:
    """Each open empire without a rival is given the one in its division nearest to it in worth."""
    open_ = _rows(conn, "SELECT * FROM empires WHERE status = 'active' AND kind <> 'pension' ORDER BY id")
    worth = {e["id"]: empires.worth(conn, e, now)["total"] for e in open_}
    for e in open_:
        if e["rival_id"] and any(o["id"] == e["rival_id"] for o in open_):
            continue
        same = [o for o in open_ if o["id"] != e["id"] and o["division"] == e["division"]] or [o for o in open_ if o["id"] != e["id"]]
        if same:
            rival = min(same, key=lambda o: (abs(worth[o["id"]] - worth[e["id"]]), o["id"]))
            conn.execute("UPDATE empires SET rival_id = %s WHERE id = %s", (rival["id"], e["id"]))


def choose_rival(conn: Connection, head_id, rival_id: int, now: datetime) -> None:
    with conn.transaction():
        _open(conn, now)
        empire = empires._head(conn, head_id)
        rival = empires._empire(conn, rival_id)
        if rival["id"] == empire["id"] or rival["status"] != "active" or rival["kind"] == "pension":
            raise EmpireError("Choose another open empire.")
        conn.execute("UPDATE empires SET rival_id = %s WHERE id = %s", (rival_id, empire["id"]))
        _log(conn, empire["id"], f"The head named {rival['name']} as the empire's rival.", now)


def head_to_head(conn: Connection, empire: dict) -> dict | None:
    """Quarter by quarter: who earned more league points, the empire or its rival."""
    if not empire["rival_id"]:
        return None
    rival = empires._empire(conn, empire["rival_id"])
    rows = _rows(conn, "SELECT period, sum(points) FILTER (WHERE empire_id = %s)::int AS ours, sum(points) FILTER (WHERE empire_id = %s)::int AS theirs"
                       " FROM league_points WHERE empire_id IN (%s, %s) GROUP BY period ORDER BY period DESC LIMIT 12",
                 (empire["id"], rival["id"], empire["id"], rival["id"]))
    won = sum(1 for r in rows if (r["ours"] or 0) > (r["theirs"] or 0))
    lost = sum(1 for r in rows if (r["ours"] or 0) < (r["theirs"] or 0))
    return {"rival": rival["name"], "rival_id": rival["id"], "won": won, "lost": lost, "drawn": len(rows) - won - lost,
            "quarters": [{"label": clock.period_label(r["period"]), "ours": r["ours"] or 0, "theirs": r["theirs"] or 0} for r in rows]}


# ---------------------------------------------------------------------------
# Events: what the world throws at an empire
# ---------------------------------------------------------------------------
HAPPENINGS = {
    "loan_called": {"title": "A lender calls in its loan", "desks": ["investment_banker", "asset_manager", "head"]},
    "holding_collapse": {"title": "A holding's price collapses", "desks": ["investment_banker", "risk_manager", "head"]},
    "inspection": {"title": "A regulator inspects the books", "desks": ["asset_manager", "investment_banker", "risk_manager"]},
    "deadline_offer": {"title": "A buyer makes an offer with a deadline", "desks": ["investment_banker", "risk_manager", "head"]},
}


def _value_per_share(conn: Connection, company_id) -> int | None:
    row = _one(conn, "SELECT value_per_share FROM company_valuations WHERE company_id = %s ORDER BY period DESC LIMIT 1", (company_id,))
    return row["value_per_share"] if row else None


def _draw(conn: Connection, empire: dict, period: int, now: datetime) -> dict | None:
    """What could happen to this empire now, given what it holds and owes."""
    day = clock.to_lagos(now).date().isoformat()
    shares = {s["id"]: s for s in marketview._shares(conn, exchange.session_of(now)[0])}
    held = [h for h in _held(conn, empire) if h["company_id"] in shares]
    open_debt = [d for d in _rows(conn, "SELECT * FROM empire_debts WHERE empire_id = %s AND status = 'open' ORDER BY id", (empire["id"],))]
    can = []
    if open_debt:
        can.append(("loan_called", 3 if any("call_anytime" in d["traps"] for d in open_debt) else 1))
    falling = [h for h in held if shares[h["company_id"]]["change_bps"] <= -500]
    if falling:
        can.append(("holding_collapse", 2))
    can.append(("inspection", 1))
    valued = [h for h in held if _value_per_share(conn, h["company_id"])]
    if valued:
        can.append(("deadline_offer", 1))
    done = {r["kind"] for r in _rows(conn, "SELECT kind FROM empire_happenings WHERE empire_id = %s AND period = %s", (empire["id"], period))}
    can = [(k, w) for k, w in can if k not in done]
    if not can:
        return None
    pick_at = _roll(conn, "happening_kind", empire["id"], day) % sum(w for _k, w in can)
    for kind, weight in can:
        if pick_at < weight:
            break
        pick_at -= weight
    if kind == "loan_called":
        debt = open_debt[_roll(conn, "which_debt", empire["id"], day) % len(open_debt)]
        cash = ledger.balance(conn, empire["account_id"])
        best = "repay" if cash >= debt["outstanding"] else "sell" if cash + _holdings_value(conn, empire, shares) >= debt["outstanding"] else "refinance"
        return {"kind": kind, "body": f"A letter from {debt['lender_name']}: the {_money(debt['outstanding'])} lent is called back. The empire has two days to say how it will pay.",
                "payload": {"debt_id": debt["id"], "owed": debt["outstanding"], "_best": best, "_cash": cash}}
    if kind == "holding_collapse":
        h = falling[_roll(conn, "which_holding", empire["id"], day) % len(falling)]
        s = shares[h["company_id"]]
        value = _value_per_share(conn, h["company_id"])
        report = objectives._filed_one(conn, h["company_id"], period - 1)
        prior = objectives._filed_one(conn, h["company_id"], period - 2)
        cause = "sales" if report and prior and report["figures"].get("revenue", 0) < prior["figures"].get("revenue", 0) else "rating" \
            if report and prior and report["credit_rating"] != prior["credit_rating"] else "market"
        return {"kind": kind, "body": f"{s['name']} ({s['ticker']}) is down {-s['change_bps'] / 100:.1f}% today. The empire holds {h['shares']:,} of its shares.",
                "payload": {"company_id": str(h["company_id"]), "ticker": s["ticker"], "shares": h["shares"], "price": s["price"],
                            "reference": s["reference"], "loss": h["shares"] * max(s["reference"] - s["price"], 0),
                            "_cause": cause, "_best": "hold" if value and value > s["price"] else "sell"}}
    if kind == "inspection":
        costs = _one(conn, "SELECT coalesce(sum(amount), 0)::bigint AS n FROM empire_books WHERE empire_id = %s AND period = %s",
                     (empire["id"], period))["n"]
        from simulation import corporate, firm_money
        breaches = firm_money.policy_breaches(conn, empire, now)
        issued = {sid: sh["shares"] for sid, sh in shares.items()}
        big = [h for h in held if h["shares"] * BPS >= 500 * max(issued.get(h["company_id"], 1), 1)]
        filings = ("holdings_and_bids" if any(corporate.bid_for(conn, h["company_id"]) for h in big) else "holdings") if big else "none"
        return {"kind": kind, "body": "The financial regulator has sent an inspector. The Accountant must state the quarter's costs to date, the Legal Counsel "
                                      "the filings the empire is bound by, and the Risk Manager whether the empire is inside its own treasury policy.",
                "payload": {"_costs": costs, "_inside": not breaches, "_filings": filings}}
    h = valued[_roll(conn, "which_offer", empire["id"], day) % len(valued)]
    s = shares[h["company_id"]]
    premium = OFFER_PREMIUM_BPS[0] + _roll(conn, "premium", empire["id"], day) % (OFFER_PREMIUM_BPS[1] - OFFER_PREMIUM_BPS[0])
    value = _value_per_share(conn, h["company_id"])
    # A buyer bids from the lower of the day's price and what the company is thought to be worth: a price pushed up for the day buys nothing.
    offer = min(s["price"], s["reference"], value) * (BPS + premium) // BPS
    return {"kind": "deadline_offer", "body": f"A buyer offers {_money(offer)} a share for all {h['shares']:,} of the empire's {s['name']} ({s['ticker']}) shares: "
                                              f"{(offer - s['price']) * 100 / s['price']:+.0f}% against today's price. The offer lapses in two days.",
            "payload": {"company_id": str(h["company_id"]), "ticker": s["ticker"], "shares": h["shares"], "offer": offer, "price": s["price"],
                        "_value": value, "_best": "accept" if offer > value else "decline"}}


def _holdings_value(conn: Connection, empire: dict, shares: dict) -> int:
    return sum(h["shares"] * shares[h["company_id"]]["price"] for h in _held(conn, empire) if h["company_id"] in shares)


CHOICES = {
    "loan_called": {"investment_banker": ("repay", "sell", "refinance"), "asset_manager": ("repay", "sell", "refinance"), "head": ("repay", "sell", "refinance")},
    "holding_collapse": {"investment_banker": ("sales", "rating", "market"), "risk_manager": ("hold", "sell"), "head": ("hold", "sell")},
    "inspection": {"asset_manager": "amount", "investment_banker": ("holdings", "holdings_and_bids", "none"), "risk_manager": ("inside", "outside")},
    "deadline_offer": {"investment_banker": ("above", "below"), "risk_manager": ("accept", "decline"), "head": ("accept", "decline")},
}
PROMPTS = {
    ("loan_called", "investment_banker"): "How should the empire pay? Repay from cash, sell holdings, or refinance with a new lender.",
    ("loan_called", "asset_manager"): "From the cash and holdings, which way can the empire actually pay?",
    ("loan_called", "head"): "Your call as head: repay, sell, or refinance.",
    ("holding_collapse", "investment_banker"): "What is behind the fall? Its last sales fell, its credit rating changed, or the whole market.",
    ("holding_collapse", "risk_manager"): "Hold, or sell? Compare the price with what the company is thought to be worth.",
    ("holding_collapse", "head"): "Your call as head: hold, or sell.",
    ("inspection", "asset_manager"): "State the quarter's costs in the empire's books to date, in kobo.",
    ("inspection", "investment_banker"): "What is the empire bound to file? Its holdings above the thresholds; its holdings and any bid; or nothing.",
    ("inspection", "risk_manager"): "Is the empire inside its own treasury policy?",
    ("deadline_offer", "investment_banker"): "Is the offer above or below what the company is thought to be worth a share?",
    ("deadline_offer", "risk_manager"): "Accept, or decline?",
    ("deadline_offer", "head"): "Your call as head: accept, or decline.",
}


def _truth(h: dict, desk: str):
    p = h["payload"]
    if h["kind"] == "loan_called":
        return p["_best"]
    if h["kind"] == "holding_collapse":
        return p["_cause"] if desk == "investment_banker" and crisis == "holding_collapse" else p["_best"]
    if h["kind"] == "inspection":
        return {"asset_manager": p["_costs"], "investment_banker": p.get("_filings", "none"), "risk_manager": "inside" if p["_inside"] else "outside"}[desk]
    if desk == "investment_banker":
        return "above" if p["offer"] > (p["_value"] or 0) else "below"
    return p["_best"]


def _mark(h: dict, desk: str, choice: str) -> int:
    truth = _truth(h, desk)
    if h["kind"] == "inspection" and desk == "asset_manager":
        try:
            given = int(choice)
        except (TypeError, ValueError):
            return 0
        return 100 if abs(given - truth) <= max(truth // 200, 100) else 0
    return 100 if choice == truth else 0


def _open_happenings(conn: Connection, now: datetime) -> None:
    period = careers.world_now(conn, now)["period"]
    day = clock.to_lagos(now).date().isoformat()
    for row in _rows(conn, "SELECT id FROM empires WHERE status = 'active' AND kind = 'player' ORDER BY id"):
        with conn.transaction():
            empire = empires._empire(conn, row["id"], lock=True)
            if not empires.humans(conn, empire["id"]) or _roll(conn, "happening", empire["id"], day) >= HAPPENING_CHANCE_BPS:
                continue
            drawn = _draw(conn, empire, period, now)
            if drawn is None:
                continue
            spec = HAPPENINGS[drawn["kind"]]
            try:
                with conn.transaction():
                    _one(conn, "INSERT INTO empire_happenings (empire_id, kind, title, body, desks, payload, period, opened_at, due_at)"
                                   " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING *",
                             (empire["id"], drawn["kind"], spec["title"], drawn["body"], spec["desks"], firm._json(drawn["payload"]), period, now,
                              now + timedelta(hours=HAPPENING_HOURS)))
            except errors.UniqueViolation:
                continue
            if drawn["kind"] == "loan_called":
                from simulation import firm_money
                firm_money.call_on_demand(conn, empire, {"id": drawn["payload"]["debt_id"]}, now)
            _log(conn, empire["id"], f"{spec['title']}: {drawn['body']}", now)


def answer(conn: Connection, player_id, happening_id: int, desk: str, choice, now: datetime) -> dict:
    """A desk answers an event. The head answers for the head's desk; each other desk is answered by one of its members."""
    with conn.transaction():
        _open(conn, now)
        seat, empire = firm._active(conn, player_id)
        h = _one(conn, "SELECT * FROM empire_happenings WHERE id = %s AND empire_id = %s FOR UPDATE", (happening_id, empire["id"]))
        if h is None or h["status"] != "open" or now > h["due_at"]:
            raise EmpireError("That event is no longer waiting for an answer.")
        if desk not in h["desks"]:
            raise EmpireError("That desk is not asked to answer this.")
        mine = (desk == "head" and empire["head_player_id"] == player_id) or (desk != "head" and seat["build"] == desk)
        if not mine:
            raise EmpireError(f"That answer falls to the {firm.DESK_NAMES[desk]}'s desk.")
        allowed = CHOICES[h["kind"]][desk]
        if allowed == "amount":
            if not firm._whole(choice, 0):
                raise EmpireError("Give an amount in kobo.")
            choice = str(choice)
        elif choice not in allowed:
            raise EmpireError("Choose one of the answers offered.")
        try:
            with conn.transaction():
                conn.execute("INSERT INTO happening_answers (happening_id, desk, player_id, choice, at) VALUES (%s, %s, %s, %s, %s)",
                             (happening_id, desk, player_id, choice, now))
        except errors.UniqueViolation:
            raise EmpireError("That desk has already answered.") from None
        if desk == "head" and h["kind"] == "deadline_offer" and choice == "accept":
            _accept_offer(conn, empire, h, now)
        return {"answered": True}


def _accept_offer(conn: Connection, empire: dict, h: dict, now: datetime) -> None:
    """The buyer (the pension funds, for a client) buys the shares at the price offered. The shares
    the empire still holds are sold, as far as the buyer has the cash."""
    p = h["payload"]
    held = _one(conn, "SELECT coalesce(sum(balance), 0)::bigint AS n FROM ledger_balances WHERE account_id = %s AND asset = "
                      "(SELECT share_asset FROM companies WHERE id = %s)", (empire["account_id"], p["company_id"]))["n"]
    shares = min(held, p["shares"])
    buyer = ledger.account_id(conn, ledger.INVESTORS_INSTITUTIONS)
    shares = min(shares, max(ledger.balance(conn, buyer), 0) // p["offer"])
    if shares <= 0:
        _log(conn, empire["id"], "The buyer's offer could not be completed: the shares are no longer free to sell, or the buyer has no cash.", now)
        return
    asset = _one(conn, "SELECT share_asset FROM companies WHERE id = %s", (p["company_id"],))["share_asset"]
    period = careers.world_now(conn, now)["period"]
    ledger.post(conn, kind="empire_block_sale", memo=f"{empire['name']}: {shares:,} {p['ticker']} shares sold to a buyer at {_money(p['offer'])}",
                period=period, reference=f"happening:{h['id']}",
                legs=[ledger.Leg(buyer, -shares * p["offer"]), ledger.Leg(empire["account_id"], shares * p["offer"]),
                      ledger.Leg(empire["account_id"], -shares, asset), ledger.Leg(buyer, shares, asset)])
    _log(conn, empire["id"], f"The empire sold {shares:,} {p['ticker']} shares to the buyer for {_money(shares * p['offer'])}.", now)


def _settle_happenings(conn: Connection, now: datetime) -> None:
    """When an event's two days are up: desks nobody answered are answered by the staff (where there
    are staff) or count as nothing; the event is scored, and what follows from it is done."""
    for row in _rows(conn, "SELECT id FROM empire_happenings WHERE status = 'open' AND due_at <= %s ORDER BY id", (now,)):
        with conn.transaction():
            h = _one(conn, "SELECT * FROM empire_happenings WHERE id = %s AND status = 'open' FOR UPDATE", (row["id"],))
            if h is None:
                continue
            empire = empires._empire(conn, h["empire_id"], lock=True)
            answers = {a["desk"]: a for a in _rows(conn, "SELECT * FROM happening_answers WHERE happening_id = %s", (h["id"],))}
            marks, lines = [], []
            for desk in h["desks"]:
                a = answers.get(desk)
                if a is None and firm.desk_staffed(conn, empire["id"], desk):
                    right = _roll(conn, "staff_answers", h["id"], desk) < STAFF_RIGHT_BPS
                    truth = _truth(h, desk)
                    choice = str(truth) if right else ("0" if CHOICES[h["kind"]][desk] == "amount" else
                                                       next(c for c in CHOICES[h["kind"]][desk] if c != truth))
                    conn.execute("INSERT INTO happening_answers (happening_id, desk, player_id, choice, at) VALUES (%s, %s, NULL, %s, %s)",
                                 (h["id"], desk, choice, now))
                    a = {"desk": desk, "choice": choice, "player_id": None}
                if a is None:
                    marks.append(0)
                    lines.append(f"The {firm.DESK_NAMES[desk]}'s desk did not answer.")
                    continue
                m = _mark(h, desk, a["choice"])
                marks.append(m)
                lines.append(f"The {firm.DESK_NAMES[desk]}'s desk answered {a['choice']}" + (" (the staff)" if a["player_id"] is None else "")
                             + (": right." if m else f": the right answer was {_truth(h, desk)}."))
            score = sum(marks) // max(len(marks), 1)
            cost, covered, outcome = 0, 0, ""
            period = careers.world_now(conn, now)["period"]
            if h["kind"] == "loan_called":
                debt = _one(conn, "SELECT * FROM empire_debts WHERE id = %s FOR UPDATE", (h["payload"]["debt_id"],))
                from simulation import firm_money
                if debt and debt["status"] == "called" and score >= firm.DUTY_PASS and not firm_money.covenant_test(conn, empire, debt, now):
                    conn.execute("UPDATE empire_debts SET status = 'open', called_at = NULL, rate_bps = rate_bps + 100 WHERE id = %s", (debt["id"],))
                    outcome = "The desks' answer satisfied the lender: it will leave the loan in place, at a point more interest."
                else:
                    outcome = "The lender was not satisfied: the loan must be repaid as the quarter closes."
            elif h["kind"] == "inspection":
                if score < firm.DUTY_PASS:
                    cost = apply_bps(max(empires.worth(conn, empire, now)["total"], 0), INSPECTION_FINE_BPS)
                    cost = ledger.pay_up_to(conn, payer=empire["account_id"], receiver=ledger.account_id(conn, ledger.TREASURY), wanted=cost,
                                            kind="empire_fine", memo=f"{empire['name']}: a regulator's fine after a failed inspection", period=period)
                    if cost:
                        empires._book(conn, empire["id"], period, "Fines", "A regulator's fine after an inspection", cost, True, now, kind="fee")
                    outcome = f"The inspection found the empire wanting. It was fined {_money(cost)}."
                else:
                    outcome = "The inspection found nothing wrong."
            elif h["kind"] == "holding_collapse":
                p = h["payload"]
                price = next((x["price"] for x in marketview._shares(conn, exchange.session_of(now)[0]) if str(x["id"]) == p["company_id"]), p["reference"])
                still = _one(conn, "SELECT coalesce(sum(shares), 0)::bigint AS n FROM share_owners WHERE account_id = %s AND company_id = %s",
                             (empire["account_id"], p["company_id"]))["n"]
                cost = min(p["loss"], min(still, p["shares"]) * max(p["reference"] - price, 0))
                outcome = f"The fall cost the empire {_money(cost)} on the shares it still holds." if cost else "The price has come back: nothing was lost."
            else:
                head = answers.get("head")
                outcome = "The head accepted the offer." if head and head["choice"] == "accept" else "The offer lapsed."
            if cost:
                covered = _claim(conn, empire, h["kind"], cost, period, now)
                if covered:
                    outcome += f" The insurer paid {_money(covered)} under the empire's cover."
            leagues.award(conn, empire["id"], 2 if score >= firm.DUTY_PASS else -1,
                          f"{h['title']}: the desks {'answered well' if score >= firm.DUTY_PASS else 'fell short'}", period, now,
                          reference=f"happening:{h['id']}")
            if empire["head_player_id"] and "head" in h["desks"]:
                firm.ceo_note(conn, empire["head_player_id"], empire["id"], "crisis", f"{h['title']}: the empire scored {score}. {outcome}",
                              period, now, good=score >= firm.DUTY_PASS, reference=f"crisis:{h['id']}")
            conn.execute("UPDATE empire_happenings SET status = 'settled', score = %s, cost = %s, covered = %s, outcome = %s, settled_at = %s WHERE id = %s",
                         (score, cost, covered, (outcome + " " + " ".join(lines))[:2000], now, h["id"]))
            _log(conn, empire["id"], f"{h['title']}: scored {score} out of 100. {outcome}", now)


def happenings_view(conn: Connection, seat: dict, empire: dict, now: datetime) -> list[dict]:
    _me, is_head = seat["player_id"], empire["head_player_id"] == seat["player_id"]
    out = []
    for h in _rows(conn, "SELECT * FROM empire_happenings WHERE empire_id = %s ORDER BY (status = 'open') DESC, id DESC LIMIT 8", (empire["id"],)):
        answers = {a["desk"]: a for a in _rows(conn, "SELECT a.*, p.display_name FROM happening_answers a LEFT JOIN players p ON p.id = a.player_id"
                                                     " WHERE a.happening_id = %s", (h["id"],))}
        settled = h["status"] == "settled"
        desks = []
        for desk in h["desks"]:
            a = answers.get(desk)
            mine = (desk == "head" and is_head) or (desk != "head" and seat["build"] == desk)
            allowed = CHOICES[h["kind"]][desk]
            desks.append({"desk": desk, "name": firm.DESK_NAMES[desk], "prompt": PROMPTS[(h["kind"], desk)],
                          "choices": None if allowed == "amount" else list(allowed), "amount": allowed == "amount",
                          "answered": a is not None, "by": (a["display_name"] or "The staff") if a else None,
                          "choice": a["choice"] if a and (mine or settled) else None,
                          "yours": mine and a is None and not settled and now <= h["due_at"],
                          "right": _truth(h, desk) if settled else None})
        out.append({"id": h["id"], "kind": h["kind"], "title": h["title"], "body": h["body"], "status": h["status"], "due_at": h["due_at"],
                    "score": h["score"], "cost": h["cost"], "covered": h["covered"], "outcome": h["outcome"],
                    "facts": {k: v for k, v in h["payload"].items() if not k.startswith("_")}, "desks": desks})
    return out


# ---------------------------------------------------------------------------
# Insurance
# ---------------------------------------------------------------------------

def _insurers(conn: Connection) -> list[dict]:
    return _rows(conn, "SELECT id, name, ticker, account_id FROM companies WHERE sector = 'insurance' ORDER BY ticker")


def buy_cover(conn: Connection, player_id, kind: str, insurer_id, cover: int, now: datetime) -> dict:
    """The Risk Manager buys cover for the empire for four quarters, paying the premium now. The
    insurer pays claims from its own cash: an insurer short of cash pays what it can."""
    with conn.transaction():
        state = _open(conn, now)
        seat, empire = firm._active(conn, player_id)
        if seat["build"] != "risk_manager" and not (empire["head_player_id"] == player_id and not firm.desk_members(conn, empire["id"], "risk_manager")):
            raise EmpireError("Insurance is bought by the empire's Risk Manager.")
        if kind not in COVER:
            raise EmpireError("Cover is sold against a holding's collapse, or a regulator's fine.")
        insurer = next((i for i in _insurers(conn) if str(i["id"]) == str(insurer_id)), None)
        if insurer is None:
            raise EmpireError("Choose one of the insurance companies.")
        most = apply_bps(max(empires.worth(conn, empire, now)["total"], 0), COVER_MOST_BPS)
        if not firm._whole(cover, naira(100_000), most):
            raise EmpireError(f"Cover from ₦100,000 up to a tenth of the empire's worth: {_money(most)}.")
        if _one(conn, "SELECT 1 FROM empire_cover WHERE empire_id = %s AND kind = %s AND to_period >= %s", (empire["id"], kind, state["period"])):
            raise EmpireError("The empire already has cover of that kind running.")
        premium = apply_bps(cover, COVER[kind][1]) * COVER_QUARTERS
        try:
            ledger.transfer(conn, payer=empire["account_id"], receiver=insurer["account_id"], amount=premium, kind="insurance_premium",
                            memo=f"{empire['name']}: cover against {COVER[kind][0].lower()}", period=state["period"])
        except ledger.InsufficientFunds:
            raise EmpireError(f"The premium for four quarters is {_money(premium)}. The empire has not the cash.") from None
        book = empires._book(conn, empire["id"], state["period"], "Insurance", f"Cover against {COVER[kind][0].lower()}", premium, True, now,
                             kind="fee", desk="risk_manager")             # an empire's premium, not a member's signature: it is not counted against a signing limit
        conn.execute("INSERT INTO empire_cover (empire_id, kind, insurer_id, premium, cover, from_period, to_period, bought_by, at)"
                     " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                     (empire["id"], kind, insurer["id"], premium, cover, state["period"], state["period"] + COVER_QUARTERS - 1, player_id, now))
        _log(conn, empire["id"], f"The empire bought {_money(cover)} of cover against {COVER[kind][0].lower()} from {insurer['name']}.", now)
        return {"premium": premium, "book_id": book}


def _claim(conn: Connection, empire: dict, kind: str, cost: int, period: int, now: datetime) -> int:
    cover = _one(conn, "SELECT c.*, i.account_id, i.name FROM empire_cover c JOIN companies i ON i.id = c.insurer_id WHERE c.empire_id = %s"
                       " AND c.kind = %s AND c.from_period <= %s AND c.to_period >= %s FOR UPDATE OF c", (empire["id"], kind, period, period))
    if cover is None:
        return 0
    want = min(cost, cover["cover"] - cover["claimed"])
    paid = ledger.pay_up_to(conn, payer=cover["account_id"], receiver=empire["account_id"], wanted=want, kind="insurance_claim",
                            memo=f"{cover['name']}: a claim by {empire['name']}", period=period) if want > 0 else 0
    if paid:
        conn.execute("UPDATE empire_cover SET claimed = claimed + %s WHERE id = %s", (paid, cover["id"]))
    return paid


def cover_view(conn: Connection, empire: dict, now: datetime) -> dict:
    period = careers.world_now(conn, now)["period"]
    running = _rows(conn, "SELECT c.*, i.name AS insurer FROM empire_cover c JOIN companies i ON i.id = c.insurer_id WHERE c.empire_id = %s"
                          " AND c.to_period >= %s ORDER BY c.id", (empire["id"], period))
    return {"running": [{"kind": c["kind"], "name": COVER[c["kind"]][0], "insurer": c["insurer"], "cover": c["cover"], "claimed": c["claimed"],
                         "until": clock.period_label(c["to_period"])} for c in running],
            "kinds": [{"kind": k, "name": v[0], "premium_bps": v[1]} for k, v in COVER.items()],
            "insurers": [{"id": i["id"], "name": i["name"], "cash": ledger.balance(conn, i["account_id"])} for i in _insurers(conn)],
            "most": apply_bps(max(empires.worth(conn, empire, now)["total"], 0), COVER_MOST_BPS), "quarters": COVER_QUARTERS}


# ---------------------------------------------------------------------------
# What a member sees
# ---------------------------------------------------------------------------

def tasks_view(conn: Connection, seat: dict, empire: dict, now: datetime) -> list[dict]:
    me, is_head = seat["player_id"], empire["head_player_id"] == seat["player_id"]
    out = []
    for t in _rows(conn, "SELECT t.*, c.name AS company, c.ticker FROM empire_tasks t LEFT JOIN companies c ON c.id = t.company_id"
                         " WHERE t.empire_id = %s AND (t.status = 'open' OR t.done_at > %s) ORDER BY (t.status = 'open') DESC, t.priority, t.id DESC LIMIT 8",
                   (empire["id"], now - timedelta(days=7))):
        steps = _rows(conn, "SELECT s.*, p.display_name AS done_name, q.display_name AS given_name FROM empire_task_steps s"
                            " LEFT JOIN players p ON p.id = s.done_by LEFT JOIN players q ON q.id = s.assigned_to WHERE s.task_id = %s ORDER BY s.position",
                      (t["id"],))
        out.append({"id": t["id"], "kind": t["kind"], "kind_name": TASK_KINDS.get(t["kind"], t["kind"]), "company": t["company"], "ticker": t["ticker"],
                    "status": t["status"], "priority": t["priority"], "amount": t["amount"], "decision": t["decision"].get("choice") if t["decision"] else None,
                    "steps": [{"id": s["id"], "build": s["build"], "name": firm.DESK_NAMES.get(s["build"], s["build"]), "what": s["what"],
                               "status": s["status"], "done_by": s["done_name"] or ("The staff" if s["done_by_staff"] else None),
                               "given_to": s["given_name"], "yours": s["status"] == "current" and (s["build"] == seat["build"] or (s["build"] == "head" and is_head))
                               and s["assigned_to"] in (None, me), "can_assign": is_head and s["status"] != "done" and s["build"] != "head",
                               "decide_defence": is_head and t["kind"] == "defend" and s["build"] == "head" and s["status"] == "current"}
                              for s in steps]})
    return out


def view(conn: Connection, seat: dict, empire: dict, state: dict, now: datetime) -> dict:
    is_head = empire["head_player_id"] == seat["player_id"]
    started = {r["kind"] for r in _rows(conn, "SELECT kind FROM empire_tasks WHERE empire_id = %s AND period = %s", (empire["id"], state["period"]))}
    open_n = _one(conn, "SELECT count(*) AS n FROM empire_tasks WHERE empire_id = %s AND status = 'open'", (empire["id"],))["n"]
    shortlist_waiting = _one(conn, "SELECT * FROM empire_approvals WHERE empire_id = %s AND kind = 'shortlist' AND status = 'waiting'", (empire["id"],))
    companies = {str(c["company_id"]): c for c in objectives._filed(conn, state["period"] - 1)}
    held = {str(h["company_id"]) for h in _held(conn, empire)}
    return {
        "tasks": tasks_view(conn, seat, empire, now),
        "kinds": [{"kind": k, "name": v, "started": k in started} for k, v in TASK_KINDS.items()],
        "open": open_n, "most": OPEN_TASKS_MOST, "can_start": is_head,
        "shortlist": {"id": shortlist_waiting["id"], "reason": shortlist_waiting["payload"]["reason"],
                      "targets": [{"id": c, "name": companies[c]["name"] if c in companies else c, "ticker": companies[c]["ticker"] if c in companies else ""}
                                  for c in shortlist_waiting["payload"]["targets"]]} if shortlist_waiting else None,
        "can_shortlist": seat["build"] == "investment_banker" and not shortlist_waiting,
        "candidates": [{"id": str(c["company_id"]), "name": c["name"], "ticker": c["ticker"]} for c in sorted(companies.values(), key=lambda c: c["ticker"])
                       if str(c["company_id"]) not in held] if seat["build"] == "investment_banker" else [],
        "rivalry": head_to_head(conn, empire),
        "rivals": [{"id": e["id"], "name": e["name"]} for e in _rows(conn, "SELECT id, name FROM empires WHERE status = 'active' AND kind <> 'pension'"
                                                                           " AND id <> %s ORDER BY name", (empire["id"],))] if is_head else [],
        "events": happenings_view(conn, seat, empire, now),
        "cover": cover_view(conn, empire, now),
    }


def _bell(conn: Connection, now: datetime) -> None:
    with conn.transaction():
        _assign_rivals(conn, now)
    _settle_happenings(conn, now)
    _open_happenings(conn, now)


def _close(conn: Connection, empire: dict, period: int, now: datetime) -> None:
    pass


def _waiting(conn: Connection, seat: dict, empire: dict, now: datetime) -> int:
    n = 0
    for h in _rows(conn, "SELECT * FROM empire_happenings WHERE empire_id = %s AND status = 'open' AND due_at > %s", (empire["id"], now)):
        answered = {a["desk"] for a in _rows(conn, "SELECT desk FROM happening_answers WHERE happening_id = %s", (h["id"],))}
        mine = ["head"] if empire["head_player_id"] == seat["player_id"] else []
        mine.append(seat["build"])
        n += sum(1 for d in h["desks"] if d in mine and d not in answered)
    return n


firm.BELL.append(_bell)
firm.WAITING.append(_waiting)
firm.VIEW["work"] = view
firm.DECIDED.append(_on_decided)
firm.DOCUMENT_READ.append(_on_read)
firm.OPINION_SETTLERS.update({"defence": _settle_defence, "shortlist": _settle_shortlist})
firm.OPINION_NAMES.update({"defence": "Defences decided", "shortlist": "Shortlists brought to the board"})


firm.RAISE_DESIGNED.append(_on_designed)

firm.RAISED.append(_on_raised)
