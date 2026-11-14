"""Each desk's standing duties: the work that comes round every quarter.

Every duty is set from the empire's own figures at the moment the member opens it, and marked by the
server against those figures: no question papers, nothing to look up outside the game. A duty nobody
does is done by the staff where the empire has staff in that seat (reliably, and no better than
70 out of 100); otherwise it is missed, and the desk's scorecard and the league table show it.

Some duties also lead to something real: the board's plan, a vote cast on the empire's shares, the
filings the rules require, the shortlist the banker brings, the letter to the partners.
"""

from __future__ import annotations

from datetime import datetime

from psycopg import Connection

from simulation import (
    banking,
    careers,
    clock,
    corporate,
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
    _rows,
    _text,
)
from simulation.firm import Duty
from simulation.money import BPS, apply_bps, naira

OPINION_SCORE = 60                       # a judgement is a pass when handed in; it earns the rest when the record shows it was right
FILING_BPS = 500                         # a holding of 5% or more of a company's shares must be filed each quarter
MISSED_FILING_FINE_BPS = 10              # each filing not made costs a tenth of one percent of the empire's worth
DANGERS = {
    "rate_rise": "The Central Bank raises its rate",
    "holding_fall": "A holding falls hard",
    "debt_called": "A lender calls in a debt",
    "bank_trouble": "A bank the empire relies on gets into trouble",
    "fine": "A regulator's fine",
    "theft": "Money is taken from the empire",
}


# ---------------------------------------------------------------------------
# Questions, and marking them
# ---------------------------------------------------------------------------

def q_number(key: str, label: str, money: bool = True) -> dict:
    return {"key": key, "label": label, "kind": "money" if money else "number"}


def q_percent(key: str, label: str) -> dict:
    return {"key": key, "label": label, "kind": "percent"}


def q_choice(key: str, label: str, choices: list) -> dict:
    return {"key": key, "label": label, "kind": "choice", "choices": choices}


def q_pick(key: str, label: str, choices: list, count: int | None = None) -> dict:
    return {"key": key, "label": label, "kind": "pick", "choices": choices, "count": count}


def q_text(key: str, label: str, most: int = 600) -> dict:
    return {"key": key, "label": label, "kind": "text", "most": most}


def terms(brief: str, given: list, asks: list, truth: dict, **more) -> dict:
    return {"brief": brief, "given": given, "asks": asks, "_truth": truth, **more}


def fact(label: str, value, kind: str = "money") -> dict:
    return {"label": label, "value": value, "kind": kind}


def _close_number(given, truth: int) -> bool:
    try:
        given = int(given)
    except (TypeError, ValueError):
        return False
    return abs(given - truth) <= max(abs(truth) // 200, naira(1))                    # within half a percent, or a naira


def _close_percent(given, truth_bps: int) -> bool:
    try:
        given_bps = round(float(given) * 100)
    except (TypeError, ValueError):
        return False
    return abs(given_bps - truth_bps) <= 20                                          # within a fifth of a point


def _value_words(kind: str, value) -> str:
    if value is None:
        return "none"
    if kind == "money":
        return _money(int(value))
    if kind == "percent":
        return f"{value / 100:.2f}%"
    if isinstance(value, list):
        return ", ".join(str(v) for v in value) or "none"
    return str(value)


def mark(ctx, t: dict, answers: dict) -> dict:
    """Mark every scored question: a number within half a percent, a percentage within a fifth of a
    point, a choice exactly, a set of picks by how many were right. Written answers are kept, not scored."""
    truth, lines, got, out_of = t["_truth"], [], 0, 0
    for ask in t["asks"]:
        key = ask["key"]
        if ask["kind"] == "text":
            continue
        out_of += 1
        given, right = answers.get(key), truth.get(key)
        if ask["kind"] in ("money", "number"):
            ok = _close_number(given, right)
            score = 1.0 if ok else 0.0
        elif ask["kind"] == "percent":
            ok = _close_percent(given, right)
            score = 1.0 if ok else 0.0
        elif ask["kind"] == "choice":
            ok = given == right
            score = 1.0 if ok else 0.0
        else:
            want = set(right or [])
            have = set(given or []) if isinstance(given, list) else set()
            score = (len(want & have) / max(len(want | have), 1)) if (want or have) else 1.0
            ok = score == 1.0
        got += score
        lines.append({"label": ask["label"], "right": ok, "answer": _value_words("percent" if ask["kind"] == "percent" else
                                                                                 "money" if ask["kind"] == "money" else "other", right)})
    score = round(100 * got / out_of) if out_of else 100
    return {"score": score, "lines": lines, "words": t.get("method", "")}


def _texts(t: dict, answers: dict) -> dict:
    out = {}
    for ask in t["asks"]:
        if ask["kind"] == "text":
            value = answers.get(ask["key"])
            if not isinstance(value, str):
                raise EmpireError("Write the words asked for.")
            out[ask["key"]] = _text(value)[:ask["most"]]
    return out


def _mark_with_text(ctx, t: dict, answers: dict) -> dict:
    words = _texts(t, answers)
    result = mark(ctx, t, answers)
    return {**result, "text": words}


def duty(code: str, build: str, title: str, why: str, prepare, **more) -> Duty:
    rule = Duty(code, build, title, why, prepare, more.pop("mark", mark), **more)
    firm.DUTIES[code] = rule
    return rule


# ---------------------------------------------------------------------------
# Figures the duties are set from
# ---------------------------------------------------------------------------

def _wealth(ctx) -> dict:
    return objectives.wealth(ctx["conn"], ctx["empire"]["account_id"], ctx["now"])


def _opening(ctx) -> int | None:
    row = _one(ctx["conn"], "SELECT worth FROM empire_worth WHERE empire_id = %s AND period = %s", (ctx["empire"]["id"], ctx["period"] - 1))
    return row["worth"] if row else None


def _index_at_close(conn: Connection, period: int) -> int | None:
    """The market index as a quarter closed (it is written down with the pension funds' results)."""
    row = _one(conn, "SELECT index_level FROM pension_fund_results WHERE period = %s LIMIT 1", (period,))
    return row["index_level"] if row else None


def _bills_next(ctx) -> dict:
    """What the empire must pay as the quarter closes: its staff, the interest on its debts, and debts due or called."""
    conn, empire = ctx["conn"], ctx["empire"]
    staff = _one(conn, "SELECT count(*) AS n FROM empire_seats WHERE empire_id = %s AND player_id IS NULL AND staffed", (empire["id"],))["n"]
    salary = careers.salary_per_quarter(empires.data.STAFF_LEVEL, careers.world_now(conn, ctx["now"])["wage_index_bps"])
    debts = _rows(conn, "SELECT * FROM empire_debts WHERE empire_id = %s AND status IN ('open', 'called')", (empire["id"],))
    interest = sum(d["outstanding"] * d["rate_bps"] // BPS // 4 for d in debts)
    due = sum(d["outstanding"] for d in debts if d["status"] == "called" or d["due_period"] <= ctx["period"])
    return {"staff": staff * salary, "interest": interest, "due": due, "total": staff * salary + interest + due}


# ---------------------------------------------------------------------------
# The Asset Manager's desk
# ---------------------------------------------------------------------------

def _am_mandate(ctx):
    opening = _opening(ctx)
    if not opening:
        return None
    conn = ctx["conn"]
    worth = empires.worth(conn, ctx["empire"], ctx["now"])["total"]
    start = _index_at_close(conn, ctx["period"] - 1)
    index = objectives.index_now(conn, ctx["now"])
    if not start:
        return None
    ours, market = (worth - opening) * BPS // opening, (index - start) * BPS // start
    return terms("Report the empire's return this quarter against the market, as the mandate asks.",
                 [fact("Worth as the last quarter closed", opening), fact("Worth now", worth),
                  fact("Market index as the last quarter closed", start, "number"), fact("Market index now", index, "number")],
                 [q_percent("ours", "The empire's return so far this quarter (%)"), q_percent("market", "The market's return so far (%)"),
                  q_choice("beat", "Has the empire beaten the market?", ["yes", "no"])],
                 {"ours": ours, "market": market, "beat": "yes" if ours > market else "no"},
                 method="Return = (worth now − worth at the start) ÷ worth at the start. The same for the index. Compare the two.")


def _am_pots(ctx):
    from simulation import firm_money
    conn, empire = ctx["conn"], ctx["empire"]
    have = firm_money.mix(conn, empire, ctx["now"])
    bills = _bills_next(ctx)
    rule = firm_money.policy(conn, empire["id"])
    return terms("Check the three pots against the treasury policy and the bills that fall due as the quarter closes.",
                 [fact("Cash (the safe pot)", have["cash"]), fact("Bonds and bills (the main pot)", have["bonds"]), fact("Shares (the growth pot)", have["shares"]),
                  fact("Staff pay due at the close", bills["staff"]), fact("Interest due at the close", bills["interest"]),
                  fact("Debts due or called", bills["due"]), fact("Policy: cash at least", rule["cash_least_bps"], "percent"),
                  fact("Policy: shares at most", rule["shares_most_bps"], "percent")],
                 [q_number("bills", "What must be paid as the quarter closes?"),
                  q_choice("cash_enough", "Does the safe pot cover it?", ["yes", "no"]),
                  q_percent("growth", "Shares as a share of everything the empire owns (%)"),
                  q_choice("inside", "Is the empire inside its treasury policy?", ["yes", "no"])],
                 {"bills": bills["total"], "cash_enough": "yes" if have["cash"] >= bills["total"] else "no", "growth": have["shares_bps"],
                  "inside": "no" if firm_money.policy_breaches(conn, empire, ctx["now"]) else "yes"},
                 method="Add the bills. Compare with cash. Shares ÷ (cash + bonds + shares). Then the policy's two limits.")


def _open_votes(ctx) -> list[dict]:
    return _rows(ctx["conn"], "SELECT v.*, c.ticker, c.name FROM company_votes v JOIN companies c ON c.id = v.company_id"
                              " JOIN share_owners o ON o.company_id = v.company_id AND o.account_id = %s AND o.shares > 0"
                              " WHERE v.status = 'open' ORDER BY v.id", (ctx["empire"]["account_id"],))


def _am_vote(ctx):
    votes = _open_votes(ctx)
    if not votes:
        return None
    v = votes[0]
    return terms(f"{v['name']} ({v['ticker']}) asks its shareholders: {v['question']} The empire holds shares, so it has a vote. Cast it.",
                 [fact("What the board says", v["explanation"], "text"), fact("The board recommends", v["board"], "text")],
                 [q_choice("vote", "The empire votes", ["for", "against"]), q_text("why", "Why, in a sentence", 300)],
                 {"vote": None}, vote_id=v["id"], method="Read what the board says and whether it serves the shareholders.")


def _am_vote_mark(ctx, t, answers):
    words = _texts(t, answers)
    if answers.get("vote") not in ("for", "against"):
        raise EmpireError("For, or against.")
    try:
        corporate.cast_vote(ctx["conn"], account=ctx["empire"]["account_id"], vote_id=t["vote_id"], choice=answers["vote"], now=ctx["now"])
    except corporate.CorporateError as refused:
        raise EmpireError(str(refused)) from None
    ok = len(words.get("why", "")) >= 10
    return {"score": 70 if ok else 60, "lines": [{"label": "The vote was cast", "right": True, "answer": answers["vote"]}],
            "words": "A vote with a reason on the record." if ok else "The vote was cast; the reason was too short to be of use.", "text": words}


def _am_cash(ctx):
    bills = _bills_next(ctx)
    cash = ledger.balance(ctx["conn"], ctx["empire"]["account_id"])
    return terms("Ladder the cash: will the empire have enough when the quarter closes?",
                 [fact("Cash now", cash), fact("Staff pay", bills["staff"]), fact("Interest", bills["interest"]), fact("Debts due or called", bills["due"])],
                 [q_number("shortfall", "How much short would the empire be? (0 if none)")],
                 {"shortfall": max(bills["total"] - cash, 0)}, method="Shortfall = bills − cash, or nothing if cash is enough.")


def _am_idea(ctx):
    companies = sorted(objectives._filed(ctx["conn"], ctx["period"] - 1), key=lambda c: c["ticker"])
    if not companies:
        return None
    return terms("Bring the investment committee one idea: a company, buy or avoid, and the case for it. The head approves it or not; "
                 "as the next quarter closes it is judged against the market.",
                 [], [q_choice("company", "The company", [c["ticker"] for c in companies]), q_choice("call", "Your call", ["buy", "avoid"]),
                      q_text("case", "The case, in two or three sentences", 400)], {})


def _am_idea_mark(ctx, t, answers):
    words = _texts(t, answers)
    conn, empire = ctx["conn"], ctx["empire"]
    ticker, call = answers.get("company"), answers.get("call")
    if call not in ("buy", "avoid") or ticker not in t["asks"][0]["choices"] or len(words.get("case", "")) < 20:
        raise EmpireError("Choose a company, buy or avoid, and write the case.")
    share = next(s for s in marketview._shares(conn, exchange.session_of(ctx["now"])[0]) if s["ticker"] == ticker)
    firm.ask(conn, empire, kind="idea", desk="head", asked_by=ctx["player_id"], title=f"Investment idea: {call} {ticker}",
             payload={"ticker": ticker, "call": call, "case": words["case"]}, period=ctx["period"], now=ctx["now"])
    firm.sign_opinion(conn, ctx["player_id"], "asset_manager", empire["id"], "idea", f"{call.title()} {ticker}",
                      {"ticker": ticker, "call": call, "price": share["price"], "index": objectives.index_now(conn, ctx["now"])},
                      ctx["period"], ctx["period"] + 1, ctx["now"])
    return {"score": OPINION_SCORE, "lines": [{"label": "Brought to the committee", "right": True, "answer": f"{call} {ticker}"}],
            "words": "Your idea is with the head, and on your record. It is judged as the next quarter closes.", "text": words}


def _settle_idea(conn, opinion, period, now):
    call = opinion["call"]
    share = next((s for s in marketview._shares(conn, exchange.session_of(now)[0]) if s["ticker"] == call["ticker"]), None)
    if share is None:
        return ("void", "It is no longer listed.")
    index = objectives.index_now(conn, now)
    beat = share["price"] * call["index"] > index * call["price"]
    right = beat if call["call"] == "buy" else not beat
    return ("right" if right else "wrong", f"{call['ticker']} moved {(share['price'] - call['price']) * 100 / call['price']:+.1f}%, "
                                           f"the market {(index - call['index']) * 100 / call['index']:+.1f}%.")


def _plan_fund(ctx):
    fid = firm.article(ctx["conn"], ctx["empire"]["id"], "pension_plan")
    return _one(ctx["conn"], "SELECT * FROM empires WHERE id = %s AND kind = 'pension' AND status = 'active'", (fid,)) if fid else None


def _am_plan(ctx):
    fund = _plan_fund(ctx)
    if fund is None:
        return None
    rows = _rows(ctx["conn"], "SELECT period, worth FROM empire_worth WHERE empire_id = %s ORDER BY period DESC LIMIT 2", (fund["id"],))
    if len(rows) < 2 or not rows[1]["worth"]:
        return None
    change = (rows[0]["worth"] - rows[1]["worth"]) * BPS // rows[1]["worth"]
    return terms(f"Report to the members on their pension plan, {fund['name']}: how did it do last quarter?",
                 [fact(f"Worth as {clock.period_label(rows[1]['period'])} closed", rows[1]["worth"]),
                  fact(f"Worth as {clock.period_label(rows[0]['period'])} closed", rows[0]["worth"])],
                 [q_percent("change", "Its change in worth last quarter (%)"), q_text("note", "A note to the members", 300)],
                 {"change": change}, method="(Later − earlier) ÷ earlier. Money moving in and out of a fund changes its worth too: say so in the note.")


# ---------------------------------------------------------------------------
# The Accountant's desk
# ---------------------------------------------------------------------------

def _ac_close(ctx):
    from simulation import firm_money
    conn, empire = ctx["conn"], ctx["empire"]
    figures = firm_money.accounts_for(conn, empire, ctx["period"], ctx["now"])
    given = [fact("Worth at the start of the quarter", figures["opening"]), fact("Worth now", figures["closing"]),
             fact("Capital put in this quarter", figures["capital_in"]), fact("Paid out to partners this quarter", figures["paid_out"])]
    given += [fact(f"Costs: {cat}", amount) for cat, amount in figures["costs"].items()]
    return terms("Prepare the empire's accounts for the quarter so far.", given,
                 [q_number("costs", "Total costs in the books"), q_number("profit", "Profit so far (the change in worth, less capital put in, plus what was paid out)")],
                 {"costs": figures["total_costs"], "profit": figures["profit"]},
                 method="Costs: add the lines. Profit = worth now − worth at the start − capital put in + paid out.")


def _ac_budget(ctx):
    from simulation import firm_money
    conn, empire = ctx["conn"], ctx["empire"]
    rows = []
    for desk in firm.DESKS:
        budget = firm_money.budget_of(conn, empire["id"], ctx["period"], desk)
        if budget is not None:
            rows.append((desk, budget, firm_money.spent_by(conn, empire["id"], ctx["period"], desk)))
    if not rows:
        return None
    over = max(rows, key=lambda r: r[2] - r[1])
    return terms("The budget war room: how is each desk doing against its budget?",
                 [fact(f"{firm.DESK_NAMES[d]}: budget / spent", f"{_money(b)} / {_money(s)}", "text") for d, b, s in rows],
                 [q_choice("worst", "Which desk is furthest over its budget?", [firm.DESK_NAMES[d] for d, _b, _s in rows] + ["None"]),
                  q_number("left", "What is left unspent across all the budgets? (0 if none)")],
                 {"worst": firm.DESK_NAMES[over[0]] if over[2] > over[1] else "None", "left": sum(max(b - s, 0) for _d, b, s in rows)},
                 method="For each desk: spent − budget. The largest positive figure is the worst. Unspent: add (budget − spent) where it is positive.")


def _ac_covenants(ctx):
    from simulation import firm_money
    conn, empire = ctx["conn"], ctx["empire"]
    debts = [d for d in firm_money.debts(conn, empire["id"]) if d["status"] == "open"]
    if not debts:
        return None
    d = debts[0]
    have = objectives.wealth(conn, empire["account_id"], ctx["now"])
    return terms(f"Test the promises in the empire's debt to {d['lender_name']} before the lender does.",
                 [fact("Everything the empire owns", have["total"]), fact("Everything it owes", firm.debt_of(conn, empire["id"])),
                  fact("Cash", have["cash"]), fact("This debt", d["outstanding"]), fact("Its rate a year", d["rate_bps"], "percent"),
                  fact("Promise: owe no more than", 5000, "percent"), fact("Promise: cash at least one quarter's interest", "", "text")]
                 + ([fact("A further clause in force", firm_money.TRAP_NAMES[t], "text") for t in d["traps"]]),
                 [q_choice("broken", "Is any promise broken right now?", ["yes", "no"]), q_number("interest", "One quarter's interest on this debt")],
                 {"broken": "yes" if firm_money.covenant_test(conn, empire, d, ctx["now"]) else "no",
                  "interest": d["outstanding"] * d["rate_bps"] // BPS // 4},
                 method="Owed ÷ owned against one half; cash against a quarter's interest (outstanding × rate ÷ 4); and any clause in force.")


def _ac_partners(ctx):
    from simulation import firm_money
    conn, empire = ctx["conn"], ctx["empire"]
    if empire["kind"] != "player":
        return None
    firm_money.ensure_units(conn, empire)
    holders = firm_money.partners(conn, empire, ctx["now"])
    total = firm_money.units_total(conn, empire["id"])
    if not holders or not total:
        return None
    worth = empires.worth(conn, empire, ctx["now"])["total"]
    top = holders[0]
    price = max(worth // total, 1)
    return terms("Report to the partners: what is a unit of the empire worth, and what is the largest stake worth?",
                 [fact("The empire's worth (owned less owed)", worth), fact("Units in issue", total, "number"),
                  fact("The largest partner's units", top["units"], "number")],
                 [q_number("price", "The worth of one unit"), q_number("top", "The worth of the largest partner's stake")],
                 {"price": price, "top": top["units"] * price}, method="Unit = worth ÷ units. A stake = its units × the unit's worth.")


def _ac_bonus(ctx):
    conn, empire = ctx["conn"], ctx["empire"]
    if not firm.player_run(empire):
        return None
    worth = empires.worth(conn, empire, ctx["now"])["total"]
    is_ceo = empires.is_ceo(conn, empire["head_player_id"])
    share = empires.data.CEO_BONUS_BPS if is_ceo else empires.data.HEAD_BONUS_BPS
    paid = _one(conn, "SELECT coalesce(sum(amount), 0)::bigint AS n FROM empire_books WHERE empire_id = %s AND period = %s AND kind = 'bonus'",
                (empire["id"], ctx["period"]))["n"]
    return terms("Work out the room left in this quarter's bonus pool, before you propose who gets what.",
                 [fact("The empire's worth", worth), fact("Bonuses may be up to", share, "percent"), fact("Already paid this quarter", paid)],
                 [q_number("room", "The room left in the pool")], {"room": max(apply_bps(worth, share) - paid, 0)},
                 method="Pool = worth × the share the head's rank allows; room = pool − paid already.")


# ---------------------------------------------------------------------------
# The Investment Banker's desk
# ---------------------------------------------------------------------------

def _ac_positions(ctx):
    """The gap stage: the Accountant values the empire's options, futures and swaps at the desk's fair prices."""
    from simulation import derivatives, swaps
    conn, empire, now = ctx["conn"], ctx["empire"], ctx["now"]
    account = empire["account_id"]
    positions = _rows(conn, "SELECT p.*, s.kind, s.underlying, s.company_id, s.strike, s.expiry_period FROM derivative_positions p"
                            " JOIN derivative_series s ON s.id = p.series_id WHERE p.account = %s AND p.status = 'open' ORDER BY p.id", (account,))
    held = _rows(conn, "SELECT * FROM swaps WHERE status = 'active' AND (fixed_payer = %s OR float_payer = %s) ORDER BY id", (account, account))
    if not positions and not held:
        return None
    given = []
    for p in positions:
        fair = derivatives.fair(conn, p, now)
        sign = "bought" if p["side"] == "long" else ("sold" if p["kind"] == "future" else "written")
        given.append(fact(f"{derivatives.describe(p)}: {p['contracts']:,} {sign}; fair price a contract / "
                          f"{'last settlement price' if p['kind'] == 'future' else 'margin held'}",
                          f"{_money(fair)} / {_money(p['mark'] if p['kind'] == 'future' else p['margin'])}", "text"))
        if p["kind"] == "future":
            given.append(fact(f"{derivatives.describe(p)}: margin held", p["margin"]))
    waiting = _one(conn, "SELECT coalesce(sum(reserved), 0)::bigint AS r FROM derivative_orders WHERE account = %s AND status = 'open'",
                   (account,))["r"]
    if waiting:
        given.append(fact("Cash held for orders still waiting", waiting))
    for s in held:
        given.append(fact(f"{swaps.describe(s)}: worth to the empire at today's levels", swaps.value_to(conn, s, account)))
    truth = derivatives.held_value(conn, account, now) + sum(swaps.value_to(conn, s, account) for s in held)
    return terms("Value the empire's options, futures and swaps for the quarter's books.", given,
                 [q_number("value", "What they are worth to the empire in all (margin held included)")], {"value": truth},
                 method="A future: (fair price − last settlement price) × contracts, + for bought and − for sold, plus its margin. "
                        "A bought option: fair price × contracts. A written option: its margin − fair price × contracts. Add the cash held "
                        "for waiting orders and each swap's worth.")


def _ib_capital(ctx):
    from simulation import firm_money
    conn, empire = ctx["conn"], ctx["empire"]
    if not firm.player_run(empire):
        return None
    owned = objectives.wealth(conn, empire["account_id"], ctx["now"])["total"]
    owed = firm.debt_of(conn, empire["id"])
    rate = careers.world_now(conn, ctx["now"])["policy_rate_bps"] + firm_money.LOAN_SPREAD_BPS
    room = max(apply_bps(owned, firm_money.DEBT_MOST_BPS) - owed, 0)
    return terms("Advise the board on how much more the empire could borrow, and what it would cost.",
                 [fact("Everything the empire owns", owned), fact("Everything it owes", owed), fact("The most it may owe", firm_money.DEBT_MOST_BPS, "percent"),
                  fact("A bank's rate to the empire, a year", rate, "percent")],
                 [q_number("room", "How much more it may borrow"), q_number("interest", "A quarter's interest if it borrowed all of that from a bank")],
                 {"room": room, "interest": room * rate // BPS // 4}, method="Room = owned × one half − owed. Interest = room × rate ÷ 4.")


def _ib_shortlist(ctx):
    conn, empire = ctx["conn"], ctx["empire"]
    from simulation import firm_tasks
    held = {h["company_id"] for h in firm_tasks._held(conn, empire)}
    companies = [c for c in sorted(objectives._filed(conn, ctx["period"] - 1), key=lambda c: c["ticker"]) if c["company_id"] not in held]
    if len(companies) < 3 or _one(conn, "SELECT 1 FROM empire_approvals WHERE empire_id = %s AND kind = 'shortlist' AND period = %s",
                                  (empire["id"], ctx["period"])):
        return None
    return terms("Bring the board three companies the empire does not hold, and the case for them. The head picks one, and the next "
                 "investment task is on it. Your pick is judged against the market.", [],
                 [q_pick("targets", "Three companies", [c["ticker"] for c in companies], 3), q_text("case", "The case for them", 400)], {},
                 tickers={c["ticker"]: str(c["company_id"]) for c in companies})


def _ib_shortlist_mark(ctx, t, answers):
    words = _texts(t, answers)
    picks = answers.get("targets")
    if not isinstance(picks, list) or len(set(picks)) != 3 or any(p not in t["tickers"] for p in picks):
        raise EmpireError("Pick three companies from the list.")
    from simulation import firm_tasks
    firm_tasks.shortlist(ctx["conn"], ctx["player_id"], [t["tickers"][p] for p in picks], words.get("case", ""), ctx["now"])
    return {"score": OPINION_SCORE, "lines": [{"label": "Brought to the board", "right": True, "answer": ", ".join(picks)}],
            "words": "The shortlist is with the head.", "text": words}


# ---------------------------------------------------------------------------
# The Risk Manager's desk
# ---------------------------------------------------------------------------

def _rm_report(ctx):
    from simulation import firm_risk
    f = firm_risk.figures(ctx["conn"], ctx["empire"], ctx["now"])
    have = objectives.wealth(ctx["conn"], ctx["empire"]["account_id"], ctx["now"])
    if not have["lines"]:
        return None
    return terms("Sign off the risk report: the figures behind it are below. Check them before you put your name to them.",
                 [fact(f"{l['ticker']}: shares held × price", l["value"]) for l in have["lines"]]
                 + [fact("Cash", have["cash"]), fact("Bonds", have["bonds"]), fact("Owed", f["owed"])],
                 [q_percent("biggest", "The largest holding as a share of everything owned (%)"),
                  q_choice("breach", "Is the treasury policy broken?", ["yes", "no"])],
                 {"biggest": f["biggest_bps"], "breach": "yes" if f["breaches"] else "no"},
                 method="Largest line ÷ (cash + bonds + every share line).")


def _rm_counterparty(ctx):
    conn = ctx["conn"]
    banks = banking.banks(conn, ctx["period"])
    rows = [(b, (b["household_loans"] + b["company_loans"]) * 100 // max(b["total_equity"], 1)) for b in banks if b["total_equity"] > 0]
    if len(rows) < 2:
        return None
    weakest = max(rows, key=lambda r: (r[1], r[0]["ticker"]))[0]
    return terms("Counterparty watch: which bank lends the most against its own funds? That is the one to watch.",
                 [fact(f"{b['name']}: lending / owners' funds", f"{_money(b['household_loans'] + b['company_loans'])} / {_money(b['total_equity'])}", "text")
                  for b, _r in rows],
                 [q_choice("weakest", "The bank most stretched", [b["name"] for b, _r in rows])], {"weakest": weakest["name"]},
                 method="For each bank: lending ÷ owners' funds. The highest is the most stretched.")


def _rm_liquidity(ctx):
    conn = ctx["conn"]
    bills = _bills_next(ctx)
    have = objectives.wealth(conn, ctx["empire"]["account_id"], ctx["now"])
    stressed = have["cash"] + have["bonds"] + have["shares"] * 7 // 10
    return terms("The liquidity plan: if shares fell 30% tomorrow, could the empire still pay what falls due?",
                 [fact("Cash", have["cash"]), fact("Bonds and bills", have["bonds"]), fact("Shares", have["shares"]), fact("Due at the close", bills["total"])],
                 [q_number("stressed", "What the empire could raise with shares 30% lower"), q_choice("can_pay", "Could it pay?", ["yes", "no"])],
                 {"stressed": stressed, "can_pay": "yes" if stressed >= bills["total"] else "no"},
                 method="Cash + bonds + shares × 0.7, against what is due.")


def _rm_appetite(ctx):
    conn, empire = ctx["conn"], ctx["empire"]
    season = leagues.season_of(ctx["period"])
    start = _one(conn, "SELECT worth FROM empire_worth WHERE empire_id = %s AND period = %s", (empire["id"], (season - 1) * 4))
    if not start or not start["worth"]:
        return None
    worth = empires.worth(conn, empire, ctx["now"])["total"]
    appetite = (firm.article(conn, empire["id"], "risk_appetite") or {}).get("worst_year_bps", 1500)
    change = (worth - start["worth"]) * BPS // start["worth"]
    return terms("Measure the year so far against the risk appetite the members voted.",
                 [fact("Worth as the year began", start["worth"]), fact("Worth now", worth), fact("The most the empire will accept losing", appetite, "percent")],
                 [q_percent("change", "Change in worth this year so far (%)"), q_choice("within", "Is the empire within its appetite?", ["yes", "no"])],
                 {"change": change, "within": "yes" if change >= -appetite else "no"}, method="(Now − start) ÷ start, against minus the appetite.")


def _rm_postmortem(ctx):
    conn, empire = ctx["conn"], ctx["empire"]
    row = _one(conn, "SELECT figures FROM empire_accounts WHERE empire_id = %s AND period = %s", (empire["id"], ctx["period"] - 1))
    if not row or row["figures"]["profit"] >= 0:
        return None
    f = row["figures"]
    market = -(f["profit"] + f["total_costs"] - f["income_received"])          # what is left of the loss once costs and income are counted: prices
    causes = {"Costs": f["total_costs"], "Prices of what it holds": max(market, 0)}
    worst = max(causes, key=causes.get)
    return terms("Last quarter the empire lost money. Write the post-mortem: what did most of the damage? It is kept for good, and every member can read it.",
                 [fact("The loss", -f["profit"]), fact("Costs", f["total_costs"]), fact("Income received", f["income_received"])],
                 [q_choice("cause", "What did most of the damage?", list(causes)), q_text("lesson", "What the empire should do differently", 400)],
                 {"cause": worst}, method="Loss = costs − income + the fall in prices. Compare the parts.")


def _rm_dangers(ctx):
    return terms("The risk report to the board: name the three biggest dangers for next quarter. As it closes, the record shows which came.",
                 [], [q_pick("dangers", "Three dangers", list(DANGERS.values()), 3)], {})


def _rm_dangers_mark(ctx, t, answers):
    picks = answers.get("dangers")
    keys = {v: k for k, v in DANGERS.items()}
    if not isinstance(picks, list) or len(set(picks)) != 3 or any(p not in keys for p in picks):
        raise EmpireError("Name three dangers from the list.")
    conn, empire = ctx["conn"], ctx["empire"]
    firm.sign_opinion(conn, ctx["player_id"], "risk_manager", empire["id"], "dangers", "The three biggest dangers",
                      {"dangers": [keys[p] for p in picks], "rate": careers.world_now(conn, ctx["now"])["policy_rate_bps"]},
                      ctx["period"], ctx["period"] + 1, ctx["now"])
    return {"score": OPINION_SCORE, "lines": [{"label": "Put to the board", "right": True, "answer": ", ".join(picks)}],
            "words": "On your record: the next quarter shows which came."}


def _settle_dangers(conn, opinion, period, now):
    empire_id, came = opinion["empire_id"], set()
    if careers.world_now(conn, now)["policy_rate_bps"] > opinion["call"]["rate"]:
        came.add("rate_rise")
    if _one(conn, "SELECT 1 FROM empire_happenings WHERE empire_id = %s AND period = %s AND kind = 'holding_collapse'", (empire_id, period)):
        came.add("holding_fall")
    if _one(conn, "SELECT 1 FROM empire_debts WHERE empire_id = %s AND called_at IS NOT NULL AND status IN ('called', 'defaulted')", (empire_id,)):
        came.add("debt_called")
    if _one(conn, "SELECT 1 FROM empire_books WHERE empire_id = %s AND period = %s AND category = 'Fines'", (empire_id, period)):
        came.add("fine")
    if _one(conn, "SELECT 1 FROM empire_cases WHERE empire_id = %s AND at >= (SELECT min(at) FROM league_points WHERE period = %s)", (empire_id, period)):
        came.add("theft")
    named = set(opinion["call"]["dangers"])
    if not came:
        return ("void", "None of the dangers came.")
    hit = named & came
    return ("right" if hit else "wrong", f"What came: {', '.join(DANGERS[c] for c in sorted(came))}. Named and came: {len(hit)}.")


# ---------------------------------------------------------------------------
# The Legal Counsel's desk
# ---------------------------------------------------------------------------

def _holdings_pct(ctx) -> list[dict]:
    conn = ctx["conn"]
    rows = _rows(conn, "SELECT o.company_id, o.shares, c.ticker, c.name FROM share_owners o JOIN companies c ON c.id = o.company_id"
                       " WHERE o.account_id = %s AND o.shares > 0 ORDER BY c.ticker", (ctx["empire"]["account_id"],))
    issued = {s["id"]: s["shares"] for s in marketview._shares(conn, exchange.session_of(ctx["now"])[0])}
    return [{**r, "bps": r["shares"] * BPS // max(issued.get(r["company_id"], 1), 1)} for r in rows]


def _lw_filings(ctx):
    rows = _holdings_pct(ctx)
    if not rows:
        return None
    return terms("The rules require a notice for every company in which the empire holds 5% or more of the shares. Which must be filed this quarter?",
                 [fact(f"{r['ticker']}: shares held / in issue", f"{r['shares']:,} ({r['bps'] / 100:.2f}%)", "text") for r in rows],
                 [q_pick("file", "File a notice for", [r["ticker"] for r in rows])], {"file": [r["ticker"] for r in rows if r["bps"] >= FILING_BPS]},
                 method="Shares held ÷ shares in issue. Five per cent or more must be filed. A notice missed is a fine.")


def _lw_filings_staff(ctx, duty):
    pass                                                    # the staff file correctly: no fine


def _filings_close(conn: Connection, empire: dict, period: int, now: datetime) -> None:
    """As the quarter closes: each holding of 5% or more that was not filed costs a fine, paid to the Treasury."""
    duty = _one(conn, "SELECT * FROM desk_duties WHERE empire_id = %s AND period = %s AND code = 'lw_filings'", (empire["id"], period))
    rows = _holdings_pct({"conn": conn, "empire": empire, "now": now})
    needed = {r["ticker"] for r in rows if r["bps"] >= FILING_BPS}
    filed = set()
    if (duty is None or duty["status"] == "due") and firm.desk_staffed(conn, empire["id"], "investment_banker"):
        filed = needed                                      # the staff will file them as the quarter closes
    elif duty is not None and duty["status"] == "done":
        filed = needed if duty["by_staff"] else set((duty["answers"] or {}).get("file") or [])
    missed = needed - filed
    if not missed:
        return
    fine = apply_bps(max(empires.worth(conn, empire, now)["total"], 0), MISSED_FILING_FINE_BPS) * len(missed)
    paid = ledger.pay_up_to(conn, payer=empire["account_id"], receiver=ledger.account_id(conn, ledger.TREASURY), wanted=fine, kind="empire_fine",
                            memo=f"{empire['name']}: fine for notices not filed", period=period)
    if paid:
        empires._book(conn, empire["id"], period, "Fines", "Fine for holdings notices not filed", paid, True, now, kind="fee")
        _log(conn, empire["id"], f"Notices the rules require were not filed ({', '.join(sorted(missed))}): a fine of {_money(paid)}.", now)


def _lw_register(ctx):
    conn, empire = ctx["conn"], ctx["empire"]
    cases = _one(conn, "SELECT count(*) AS n, coalesce(sum(amount), 0)::bigint AS a FROM empire_cases WHERE empire_id = %s AND status = 'open'",
                 (empire["id"],))
    called = _one(conn, "SELECT count(*) AS n, coalesce(sum(outstanding), 0)::bigint AS a FROM empire_debts WHERE empire_id = %s AND status = 'called'",
                  (empire["id"],))
    traps = _one(conn, "SELECT count(*) AS n FROM empire_debts WHERE empire_id = %s AND status IN ('open', 'called') AND cardinality(traps) > 0",
                 (empire["id"],))
    events = _one(conn, "SELECT count(*) AS n FROM empire_happenings WHERE empire_id = %s AND status = 'open'", (empire["id"],))
    matters = {"Theft cases waiting": (cases["n"], cases["a"]), "Debts called in": (called["n"], called["a"]),
               "Debts with a trap in force": (traps["n"], 0), "Events waiting for an answer": (events["n"], 0)}
    total = sum(n for n, _a in matters.values())
    if not total:
        return None
    worst = max(matters, key=lambda k: (matters[k][1], matters[k][0]))
    return terms("Keep the legal risk register: every open matter, and which could cost the most.",
                 [fact(k, f"{n} ({_money(a)})" if a else str(n), "text") for k, (n, a) in matters.items()],
                 [q_number("count", "Open matters in all", money=False), q_choice("worst", "The matter that could cost the most", list(matters))],
                 {"count": total, "worst": worst}, method="Count every open matter. The largest sum at stake is the worst.")


# ---------------------------------------------------------------------------
# The Intelligence desk
# ---------------------------------------------------------------------------

def _jr_intel(ctx):
    conn, empire = ctx["conn"], ctx["empire"]
    if not empire["rival_id"]:
        return None
    table = leagues.table(conn, ctx["now"])
    rival = next((e for d in table for e in d["empires"] if e["id"] == empire["rival_id"]), None)
    if rival is None:
        return None
    return terms(f"Brief the head on the rival, {rival['name']}, from what is public: the league table.",
                 [fact("The league table", "Open the League page and read it.", "text")],
                 [q_number("points", "The rival's league points this year", money=False), q_number("place", "Its place in its division", money=False),
                  q_number("division", "Its division", money=False), q_text("note", "One line for the head", 300)],
                 {"points": rival["points"], "place": rival["place"], "division": rival["division"]},
                 method="Read the table: points, place, division. Only public facts.")


def _jr_scout(ctx):
    conn, empire = ctx["conn"], ctx["empire"]
    builds = list(empires.data.EMPIRE_BUILDS)
    build = builds[empires._roll(conn, "scout", empire["id"], ctx["period"]) % len(builds)]
    table = leagues.build_table(conn, build, limit=50)
    inside = {h["display_name"] for h in empires.humans(conn, empire["id"])}
    outside = [p for p in table["top"] if p["name"] not in inside]
    if len(outside) < 3:
        return None
    return terms(f"Talent scouting: from the public table of {BUILD_NAMES[build]}s, name the three highest-placed who are not in this empire.",
                 [fact("The build table", f"Open the League page, {BUILD_NAMES[build]}s.", "text")],
                 [q_pick("names", "Three names", [p["name"] for p in table["top"]], 3)], {"names": [p["name"] for p in outside[:3]]},
                 build=build, method="Read the table top down; skip anybody who already sits in this empire.")


def _jr_letter(ctx):
    conn, empire = ctx["conn"], ctx["empire"]
    row = _one(conn, "SELECT period, figures FROM empire_accounts WHERE empire_id = %s ORDER BY period DESC LIMIT 1", (empire["id"],))
    if not row or not row["figures"]["opening"]:
        return None
    f = row["figures"]
    return terms(f"Write the letter to the partners for {clock.period_label(row['period'])}. State the figures plainly and correctly; "
                 "the letter is published to everybody who has put money in.",
                 [fact("Worth at the start", f["opening"]), fact("Worth at the close", f["closing"]), fact("Profit", f["profit"]),
                  fact("Paid out to partners", f["paid_out"])],
                 [q_number("profit", "The profit, as stated in the letter"), q_percent("growth", "The change in worth (%)"),
                  q_text("letter", "The letter", 600)],
                 {"profit": f["profit"], "growth": (f["closing"] - f["opening"]) * BPS // f["opening"]},
                 method="State the profit as the accounts give it; change in worth = (close − start) ÷ start.")


# ---------------------------------------------------------------------------
# The head's desk
# ---------------------------------------------------------------------------

def _hd_board(ctx):
    conn, empire = ctx["conn"], ctx["empire"]
    if not firm.player_run(empire):
        return None
    last = ctx["period"] - 1
    cards = _rows(conn, "SELECT build, score, missed FROM desk_scores WHERE empire_id = %s AND period = %s ORDER BY build", (empire["id"], last))
    from simulation import firm_tasks
    return terms("Chair the board meeting: read the desks' scorecards, set the priorities and the plan for next quarter. Budgets are set on the "
                 "Money tab; the plan is published to every member.",
                 [fact(f"{firm.DESK_NAMES[c['build']]}: last quarter's score", f"{c['score']} out of 100" + (f", {c['missed']} missed" if c["missed"] else ""), "text")
                  for c in cards],
                 [q_pick("priorities", "Next quarter's priorities, in order", list(firm_tasks.TASK_KINDS.values()), 2),
                  q_choice("focus", "The desk that needs the most attention", [firm.DESK_NAMES[b] for b in empires.data.EMPIRE_BUILDS]),
                  q_text("plan", "The plan, in a few sentences", 600)],
                 {"focus": firm.DESK_NAMES[min(cards, key=lambda c: (c["score"], c["build"]))["build"]] if cards else None},
                 method="The weakest desk is the one with the lowest score.")


def _hd_board_mark(ctx, t, answers):
    words = _texts(t, answers)
    picks = answers.get("priorities")
    if not isinstance(picks, list) or not 1 <= len(picks) <= 2 or len(words.get("plan", "")) < 20:
        raise EmpireError("Choose the priorities and write the plan.")
    conn, empire = ctx["conn"], ctx["empire"]
    budgets = _one(conn, "SELECT count(*) AS n FROM empire_budgets WHERE empire_id = %s AND period = %s", (empire["id"], ctx["period"]))["n"]
    score = 50 + (25 if budgets else 0)
    lines = [{"label": "The plan was set", "right": True, "answer": ", ".join(picks)},
             {"label": "Budgets set for this quarter", "right": bool(budgets), "answer": "yes" if budgets else "not yet"}]
    if t["_truth"].get("focus"):
        ok = answers.get("focus") == t["_truth"]["focus"]
        score += 25 if ok else 0
        lines.append({"label": "The weakest desk", "right": ok, "answer": t["_truth"]["focus"]})
    else:
        score += 25
    conn.execute("INSERT INTO board_plans (empire_id, period, plan, set_by, at) VALUES (%s, %s, %s, %s, %s) ON CONFLICT (empire_id, period)"
                 " DO UPDATE SET plan = excluded.plan, set_by = excluded.set_by, at = excluded.at",
                 (empire["id"], ctx["period"] + 1, firm._json({"priorities": picks, "focus": answers.get("focus"), "plan": words["plan"]}),
                  ctx["player_id"], ctx["now"]))
    _log(conn, empire["id"], "The head chaired the board meeting and set the plan for next quarter.", ctx["now"])
    return {"score": min(score, 100), "lines": lines, "words": "The plan is published to the members.", "text": words}


def _hd_letter(ctx):
    conn, empire = ctx["conn"], ctx["empire"]
    if ctx["period"] % 4 or not firm.player_run(empire):
        return None
    start = _one(conn, "SELECT worth FROM empire_worth WHERE empire_id = %s AND period = %s", (empire["id"], ctx["period"] - 4))
    if not start or not start["worth"]:
        return None
    worth = empires.worth(conn, empire, ctx["now"])["total"]
    paid = _one(conn, "SELECT coalesce(sum(amount), 0)::bigint AS n FROM empire_payouts WHERE empire_id = %s AND period > %s",
                (empire["id"], ctx["period"] - 4))["n"]
    return terms("Write the year's letter, as the head. It goes on your record and is published with the empire's results.",
                 [fact("Worth a year ago", start["worth"]), fact("Worth now", worth), fact("Paid to partners this year", paid)],
                 [q_percent("growth", "The year's change in worth (%)"), q_number("paid", "Paid to partners this year"), q_text("letter", "The letter", 600)],
                 {"growth": (worth - start["worth"]) * BPS // start["worth"], "paid": paid},
                 method="(Now − a year ago) ÷ a year ago.")


def _hd_letter_after(ctx, duty, result):
    text = (result.get("text") or {}).get("letter", "")
    firm.ceo_note(ctx["conn"], ctx["player_id"], ctx["empire"]["id"], "letter", text[:600] or "The year's letter.", ctx["period"], ctx["now"],
                  reference=f"letter:{ctx['empire']['id']}:{ctx['period']}")


# ---------------------------------------------------------------------------
# The duties
# ---------------------------------------------------------------------------
duty("am_mandate", "asset_manager", "Report against the mandate", "The partners want to know whether the portfolio beat the market.", _am_mandate)
duty("am_pots", "asset_manager", "Check the three pots", "The bills must be covered and the policy kept.", _am_pots)
duty("am_cash", "asset_manager", "Ladder the cash", "Staff pay, interest and repayments must be met when the quarter closes.", _am_cash)
duty("am_vote", "asset_manager", "Vote the empire's shares", "A shareholder that does not vote has no say.", _am_vote, mark=_am_vote_mark)
duty("am_idea", "asset_manager", "Bring an idea to the investment committee", "Good ideas, judged afterwards, build a record.", _am_idea,
     mark=_am_idea_mark)
duty("am_plan", "asset_manager", "Report on the members' pension plan", "The members' retirement depends on it.", _am_plan, mark=_mark_with_text)
duty("ac_close", "asset_manager", "Close the books", "Late or wrong books cost the empire its league points and its partners' trust.", _ac_close)
duty("ac_budget", "asset_manager", "Run the budget war room", "Overspending shows first in the budgets: sometimes it is more than overspending.", _ac_budget)
duty("ac_covenants", "asset_manager", "Watch the promises in the empire's debts", "A broken promise lets a lender call in its money.", _ac_covenants)
duty("ac_partners", "asset_manager", "Report to the partners", "Everybody who put money in is owed a plain statement of what it is worth.", _ac_partners,
     player_run_only=True)
duty("ac_positions", "asset_manager", "Value the empire's options, futures and swaps", "The partners' figures must include what the "
     "empire's contracts are worth today, not what they cost.", _ac_positions)
duty("ac_bonus", "asset_manager", "Work out the bonus pool", "Bonuses must stay inside what the rules allow.", _ac_bonus, player_run_only=True)
duty("ib_capital", "investment_banker", "Advise on how much to borrow", "Borrowing well makes the empire bigger; too much can break it.", _ib_capital,
     player_run_only=True)
duty("ib_shortlist", "investment_banker", "Bring the board a shortlist", "The board picks the next investment from the banker's list.", _ib_shortlist,
     mark=_ib_shortlist_mark, player_run_only=True)
duty("rm_report", "risk_manager", "Sign off the risk report", "The members rely on the figures the Risk Manager signs.", _rm_report)
duty("rm_counterparty", "risk_manager", "Watch the banks", "A bank in trouble can take the empire's plans down with it.", _rm_counterparty)
duty("rm_liquidity", "risk_manager", "Test the liquidity plan", "An empire that cannot pay in a bad week fails, whatever it owns.", _rm_liquidity)
duty("rm_appetite", "risk_manager", "Measure against the risk appetite", "The members voted how much they would accept losing.", _rm_appetite)
duty("rm_postmortem", "risk_manager", "Write the post-mortem", "A loss nobody explains is a loss that comes again.", _rm_postmortem, mark=_mark_with_text)
duty("rm_dangers", "risk_manager", "Name the three biggest dangers", "Foresight is kept on the record.", _rm_dangers, mark=_rm_dangers_mark)
duty("lw_filings", "investment_banker", "File the notices the rules require", "A notice missed is a fine.", _lw_filings, staff=_lw_filings_staff)
duty("lw_register", "investment_banker", "Keep the legal risk register", "Every open dispute, and what it could cost.", _lw_register)
duty("jr_intel", "investment_banker", "Brief the head on the rival", "Know what the rival is doing, from public facts.", _jr_intel, mark=_mark_with_text)
duty("jr_scout", "investment_banker", "Scout for talent", "The head's hiring and poaching list.", _jr_scout)
duty("jr_letter", "investment_banker", "Write the letter to the partners", "Plain, correct words keep the partners' trust.", _jr_letter, mark=_mark_with_text)
duty("hd_board", "head", "Chair the board meeting", "The plan the whole empire works to.", _hd_board, mark=_hd_board_mark, player_run_only=True)
duty("hd_letter", "head", "Write the year's letter", "The head's public account of the year.", _hd_letter, mark=_mark_with_text, after=_hd_letter_after,
     player_run_only=True)

firm.OPINION_SETTLERS.update({"idea": _settle_idea, "dangers": _settle_dangers})
firm.OPINION_NAMES.update({"idea": "Ideas brought to the committee", "dangers": "Dangers named to the board"})
firm.CLOSE.append(_filings_close)


def _idea_execute(conn, approval, now):
    _log(conn, approval["empire_id"], f"The head approved the idea: {approval['title']}.", now)


firm.EXECUTORS["idea"] = _idea_execute


def _plan_check(conn, empire, payload, now):
    fund = _one(conn, "SELECT * FROM empires WHERE id = %s AND kind = 'pension' AND status = 'active'", (payload.get("fund_id"),))
    if fund is None:
        raise EmpireError("Choose an open pension fund.")
    managers = {h["player_id"] for h in empires.humans(conn, empire["id"]) if h["build"] == "asset_manager"}
    if fund["head_player_id"] not in managers:
        raise EmpireError("The members' plan is a fund run by one of the empire's own Asset Managers.")
    return {"fund_id": fund["id"], "name": fund["name"]}


def _plan_carry(conn, empire, resolution, now):
    firm.set_article(conn, empire["id"], "pension_plan", resolution["payload"]["fund_id"], resolution["period"], now, resolution["id"])
    return f"{resolution['payload']['name']} is now the members' pension plan."


firm.ARTICLE_DEFAULTS["pension_plan"] = None
firm.RESOLUTIONS["pension_plan"] = firm.Resolution("pension_plan", "Name the members' pension plan",
                                                   lambda seat, head: head or seat["build"] == "asset_manager",
                                                   _plan_check, _plan_carry, lambda p: f"Make {p['name']} the members' pension plan")


def board(conn: Connection, seat: dict, empire: dict, state: dict, now: datetime) -> dict:
    """The board meeting: the plan the head set, each desk's report for the quarter, the votes on big items,
    the post-mortems, the letters."""
    plan = _one(conn, "SELECT plan, at FROM board_plans WHERE empire_id = %s AND period = %s", (empire["id"], state["period"]))
    reports = []
    for d in _rows(conn, "SELECT d.code, d.build, d.score, d.status, d.by_staff, d.result, d.done_at, p.display_name FROM desk_duties d"
                         " LEFT JOIN players p ON p.id = d.done_by WHERE d.empire_id = %s AND d.period IN (%s, %s) AND d.status <> 'due'"
                         " ORDER BY d.done_at DESC NULLS LAST LIMIT 40", (empire["id"], state["period"], state["period"] - 1)):
        rule = firm.DUTIES.get(d["code"])
        public = d["code"] in ("rm_postmortem", "jr_letter", "hd_letter", "am_plan", "jr_intel")
        reports.append({"desk": firm.DESK_NAMES[d["build"]], "title": rule.title if rule else d["code"], "score": d["score"], "status": d["status"],
                        "by": d["display_name"] or ("The staff" if d["by_staff"] else None),
                        "text": (d["result"] or {}).get("text") if public else None})
    return {"plan": plan["plan"] if plan else None, "plan_at": plan["at"] if plan else None, "reports": reports,
            "big_votes": [r for r in firm.resolutions_view(conn, seat, empire, now)["votes"] if r["status"] == "open"]}


firm.VIEW["board"] = board
