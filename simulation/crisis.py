"""The crises stage, Part 1: trust in the banks, bank runs that spread and can be stopped, and who fights back
(owner's suggestions 2 and 4; design document, section 14).

There is no button that starts a run. Every game day each bank's trust (0 to 100) moves part of the way towards where
its public signals put it: its owners' funds against its loans, its loans gone bad, its cash against what it owes its
savers, its credit rating, how fast its savers are leaving, what the papers say about it, its share price, and what
is happening at the other banks. When trust falls:

  * worried (below 45): the biggest savers, whose money is above the ₦5 million guarantee, start to draw it out;
  * a run (below 35): queues at the branches; even small savers draw some out;
  * panic (below 20): everyone who can.

Most of what is drawn out goes the same day to the banks people trust most; the rest is kept at home and comes back as
calm returns. A bank pays from its cash; when that is not enough the Central Bank lends to it, at a penalty rate and
only against its loans, as long as it is sound. A bank in a run for three days raises new money from its big owners.
When trust in the banks taken together falls far, or two banks run at once, the Government (computer-run until the
Government stage) promises that every saving is safe. A bank that cannot pay, or whose losses have eaten its owners'
funds, is closed by the Central Bank: savers above the guarantee bear their share of the hole, the Deposit Guarantee
Fund the rest; the Auction House sells it to whoever puts in the most new money, and if nobody will, it is taken into
public hands and sold again a year later. No naira is created or lost on the way.

Each crisis is recorded from its first warning sign to its place in history, in the design's ten steps (shown as the
owner's five phases), and leaves a permanent Crisis Report. Most warnings fade away.

Everything a bank's trust is made of is public. What made the crisis possible (its hidden weakness) is kept back
until the crisis ends.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from simulation import clock, deposits, ledger
from simulation import world_data as data
from simulation.money import BPS, apply_bps

STATES = ("calm", "worried", "run", "panic", "closed")
STEPS = {
    1: "A hidden weakness",
    2: "A warning sign",
    3: "A local event",
    4: "Institutions respond",
    5: "It spreads",
    6: "The tipping point",
    7: "The crisis",
    8: "Intervention",
    9: "Recovery",
    10: "History",
}
# The owner's five phases, each a group of the design's steps.
PHASES = (("Warning", (1, 2)), ("Trigger", (3, 4)), ("Spread", (5, 6)), ("Crisis", (7, 8)), ("Recovery", (9, 10)))
PART_NAMES = {
    "capital": "its owners' funds against its loans", "bad_loans": "its loans gone bad", "cash": "its cash against its savers' money",
    "rating": "its credit rating", "withdrawals": "savers leaving", "news": "what the papers say", "share_price": "its share price",
    "other_banks": "trouble at other banks", "guarantee": "the Government's guarantee", "support": "emergency help (borrowed, or new money)",
}
FUNDAMENTAL = ("capital", "bad_loans", "cash", "rating")


class CrisisError(Exception):
    """Something the crisis rules do not allow, in plain words."""


def _rows(conn: Connection, sql: str, params=()) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def _one(conn: Connection, sql: str, params=()) -> dict | None:
    rows = _rows(conn, sql, params)
    return rows[0] if rows else None


def ready(conn: Connection) -> bool:
    return bool(_one(conn, "SELECT to_regclass('bank_confidence') IS NOT NULL AS ok")["ok"]) and deposits.ready(conn)


def money(kobo: int) -> str:
    from simulation import news
    return news.money_words(kobo)


def phase_of(step: int) -> str:
    return next(name for name, steps in PHASES if step in steps)


def state_of(score: int) -> str:
    if score < data.CONFIDENCE_PANIC:
        return "panic"
    if score < data.CONFIDENCE_RUN:
        return "run"
    if score < data.CONFIDENCE_WORRIED:
        return "worried"
    return "calm"


# ---------------------------------------------------------------------------
# A bank's figures, as the public sees them
# ---------------------------------------------------------------------------

def _filed(conn: Connection, company_id) -> dict | None:
    return _one(conn, "SELECT * FROM company_results WHERE company_id = %s ORDER BY period DESC LIMIT 1", (company_id,))


def _rating(conn: Connection, company_id) -> str | None:
    row = _one(conn, "SELECT credit_rating FROM company_reports WHERE company_id = %s ORDER BY period DESC, version DESC LIMIT 1", (company_id,))
    return row["credit_rating"] if row else None


def _cb_owed(conn: Connection, company_id) -> int:
    return _one(conn, "SELECT coalesce(sum(principal_outstanding), 0)::bigint AS t FROM company_debts WHERE company_id = %s"
                      " AND kind = 'central_bank_loan'", (company_id,))["t"]


def _emergency_owed(conn: Connection, company_id) -> int:
    return _one(conn, "SELECT coalesce(sum(principal_outstanding), 0)::bigint AS t FROM company_debts WHERE company_id = %s"
                      " AND kind = 'central_bank_loan' AND name LIKE 'emergency%%'", (company_id,))["t"]


def loans_of(filed: dict | None) -> int:
    return (filed["customer_loans"] + filed["loans_to_companies"]) if filed else 0


def capital_moved(conn: Connection, company_id, filed_period: int | None) -> int:
    """What has been added to a bank's owners' funds since its last filed accounts (a hole filled, new money put in)."""
    if filed_period is None:
        return 0
    return _one(conn, "SELECT coalesce(sum(amount), 0)::bigint AS t FROM bank_capital_moves WHERE company_id = %s AND filed_period = %s",
                (company_id, filed_period))["t"]


def _capital_move(conn: Connection, company_id, amount: int, why: str, now: datetime) -> None:
    filed = _filed(conn, company_id)
    if amount and filed:
        conn.execute("INSERT INTO bank_capital_moves (company_id, filed_period, amount, why, at) VALUES (%s, %s, %s, %s, %s)",
                     (company_id, filed["period"], amount, why, now))


def figures(conn: Connection, b: dict) -> dict:
    """The public figures behind a bank's trust: from its last filed accounts (with what has since filled a hole or added
    new money), and its cash and savers' money today."""
    filed = _filed(conn, b["id"])
    loans = loans_of(filed)
    equity = (filed["total_equity"] + capital_moved(conn, b["id"], filed["period"])) if filed else 0
    owes = deposits.owed(conn, b["id"]) or 0
    cash = max(ledger.balance(conn, b["account_id"]), 0)
    losses = filed["loan_losses"] if filed else 0
    return {"loans": loans, "equity": equity, "owed": owes, "cash": cash,
            "capital_bps": equity * BPS // loans if loans > 0 else BPS,
            "bad_bps": losses * 4 * BPS // loans if loans > 0 else 0,
            "cash_bps": cash * BPS // owes if owes > 0 else BPS,
            "rating": _rating(conn, b["id"]), "emergency": _emergency_owed(conn, b["id"])}


# ---------------------------------------------------------------------------
# Trust: where its signals put a bank today
# ---------------------------------------------------------------------------

# What trouble at another bank does to a bank's trust: (elsewhere, in the same city), by the other bank's state.
CONTAGION = {"worried": (1, 2), "run": (4, 6), "panic": (7, 10), "closed": (10, 14)}
RATING_POINTS = {"AAA": 6, "AA": 4, "A": 2, "BBB": 0, "BB": -4, "B": -9, "CCC": -20, "D": -40}


def _capital_points(capital_bps: int, equity: int) -> int:
    if equity < 0:
        return -55
    if capital_bps >= 1_500:
        return 0
    if capital_bps >= 800:
        return -(1_500 - capital_bps) * 20 // 700
    return -20 - (800 - capital_bps) * 25 // 800


def _withdrawn_recently(conn: Connection, company_id, period: int, day: int) -> int:
    """What savers drew out of a bank over the last three game days (today included)."""
    # (A company drawing its savings back as it closes its quarter, and putting them back after, is routine, not fear.)
    row = _one(conn, "SELECT coalesce(sum(amount), 0)::bigint AS t FROM deposit_flows WHERE company_id = %s"
                     " AND (kind = 'run' OR (kind = 'withdrawn' AND holder <> 'company')) AND (period * 100 + day) BETWEEN %s AND %s",
               (company_id, period * 100 + day - 2, period * 100 + day))
    if day <= 2 and period > 1:      # the last days of the quarter before count too
        row2 = _one(conn, "SELECT coalesce(sum(amount), 0)::bigint AS t FROM deposit_flows WHERE company_id = %s"
                          " AND (kind = 'run' OR (kind = 'withdrawn' AND holder <> 'company')) AND period = %s AND day > %s",
                    (company_id, period - 1, clock.GAME_DAYS_PER_QUARTER - (3 - day)))
        return row["t"] + row2["t"]
    return row["t"]


def _news_points(conn: Connection, ticker: str, period: int, day: int) -> int:
    """What the papers said about a bank in the last five game days: a bad story costs trust, a report of trouble not yet
    confirmed costs more; a good story wins a little back."""
    points = 0
    for s in _rows(conn, "SELECT tone, lead IS NOT NULL AS rumour FROM stories WHERE status = 'published' AND %s = ANY(tickers)"
                         " AND (period * 100 + day) BETWEEN %s AND %s", (ticker, period * 100 + day - 4, period * 100 + day)):
        if s["tone"] < 0:
            points -= 6 if s["rumour"] else 3
        elif s["tone"] > 0:
            points += 1
    return max(min(points, 5), -20)


def _price_points(closes: dict, company_id) -> int:
    days = closes.get(company_id) or []
    if len(days) < 2 or days[0][1] <= 0:
        return 0
    fall = (days[0][1] - days[-1][1]) * BPS // days[0][1]
    return -min(max(fall - 500, 0) // 100, 15)


def target(conn: Connection, b: dict, period: int, day: int, others: dict, closes: dict, blanket: bool) -> tuple[int, dict]:
    """Where a bank's trust is heading today, and each part of it (all public)."""
    f = figures(conn, b)
    parts = {
        "capital": _capital_points(f["capital_bps"], f["equity"]),
        "bad_loans": -min(max(f["bad_bps"] - 200, 0) * 3 // 100, 20),
        "cash": -min(max(1_000 - f["cash_bps"], 0) // 100, 10),
        "rating": RATING_POINTS.get(f["rating"] or "BBB", 0),
        "withdrawals": -min((_withdrawn_recently(conn, b["id"], period, day) * BPS // f["owed"]) * 4 // 100 if f["owed"] else 0, 30),
        "news": _news_points(conn, b["ticker"], period, day),
        "share_price": _price_points(closes, b["id"]),
        "other_banks": 0, "guarantee": data.BLANKET_TRUST_POINTS if blanket else 0,
        "support": -4 if f["emergency"] > 0 else 0,
    }
    hit = 0
    for other_id, o in others.items():
        if other_id == b["id"]:
            continue
        near = o["headquarters"] == b["headquarters"]
        hit -= CONTAGION.get(o["state"], (0, 0))[1 if near else 0]
    parts["other_banks"] = max(hit, -data.CONTAGION_MOST)
    placed = _one(conn, "SELECT 1 AS x FROM emergency_placements WHERE company_id = %s AND (period * 100 + day) >= %s",
                  (b["id"], period * 100 + day - 10))
    if placed:
        parts["support"] += 5
    # A bank just opened again under a new owner, with fresh money: its savers give it time, and the price its shares
    # were set at is not read as a fall.
    if _one(conn, "SELECT 1 AS x FROM bank_resolutions WHERE company_id = %s AND reopened_period IS NOT NULL"
                  " AND (reopened_period * 100 + reopened_day) >= %s", (b["id"], period * 100 + day - data.REOPEN_GRACE_DAYS)):
        parts["share_price"] = 0
        parts["withdrawals"] = max(parts["withdrawals"], -5)
        parts["support"] += data.REOPEN_SUPPORT_POINTS
    score = data.CONFIDENCE_BASE + sum(parts.values())
    return max(min(score, 100), 0), parts


def trust_now(conn: Connection) -> dict:
    """Each bank's latest trust, its state, and how it moved on its last day: {company_id: {...}}."""
    if not ready(conn):
        return {}
    out = {}
    for r in _rows(conn, """
            SELECT DISTINCT ON (company_id) company_id, score, state, parts, period, day,
                   score - coalesce(lag(score) OVER (PARTITION BY company_id ORDER BY period, day), score) AS change
            FROM bank_confidence ORDER BY company_id, period DESC, day DESC"""):
        out[r["company_id"]] = {"score": r["score"], "state": r["state"], "parts": r["parts"], "change": r["change"],
                                "period": r["period"], "day": r["day"]}
    return out


def _last(conn: Connection, company_id) -> dict | None:
    return _one(conn, "SELECT * FROM bank_confidence WHERE company_id = %s ORDER BY period DESC, day DESC LIMIT 1", (company_id,))


def national(conn: Connection) -> int:
    row = _one(conn, "SELECT national FROM crisis_days ORDER BY period DESC, day DESC LIMIT 1") if ready(conn) else None
    return row["national"] if row else data.CONFIDENCE_START


# ---------------------------------------------------------------------------
# Paying savers: cash, then the Central Bank
# ---------------------------------------------------------------------------

def emergency_room(conn: Connection, b: dict) -> int:
    """How much more the Central Bank will lend a bank in an emergency: only against its loans (three-fifths of them), only
    while its owners' funds are above nothing, and never past its usual limit."""
    f = figures(conn, b)
    if f["equity"] <= 0 or deposits.closed(conn, b["id"]):
        return 0
    owed = _cb_owed(conn, b["id"])
    by_collateral = apply_bps(f["loans"], data.EMERGENCY_COLLATERAL_BPS) - owed
    by_funds = data.CENTRAL_BANK_LENDING_LIMIT_X * f["equity"] - owed
    return max(min(by_collateral, by_funds), 0)


def secure_cash(conn: Connection, b: dict, amount: int, period: int, day: int, now: datetime) -> int:
    """Make sure a bank can pay out `amount`, borrowing from the Central Bank in an emergency if it must. Returns how much
    of it the bank can pay."""
    cash = max(ledger.balance(conn, b["account_id"]), 0)
    owes = deposits.owed(conn, b["id"]) or 0
    keep = apply_bps(max(owes - amount, 0), data.BANK_RESERVE_BPS)
    short = amount + keep - cash
    if short > 0:
        lent = min(short, emergency_room(conn, b))
        if lent > 0:
            _emergency_loan(conn, b, lent, period, day, now)
            cash += lent
    return min(amount, cash)


def _emergency_loan(conn: Connection, b: dict, amount: int, period: int, day: int, now: datetime) -> None:
    from simulation import economy
    world = economy.load_world(conn)
    policy = _policy_rate(conn)
    rate = policy + data.EMERGENCY_PENALTY_BPS
    ledger.transfer(conn, payer=world.central_bank, receiver=b["account_id"], amount=amount, kind="central_bank_lending", period=period,
                    memo=f"Central Bank: emergency lending to {b['name']}, against its loans, at a penalty rate")
    updated = conn.execute("UPDATE company_debts SET principal_outstanding = principal_outstanding + %s, original_principal = original_principal + %s,"
                           " annual_rate_bps = %s WHERE company_id = %s AND kind = 'central_bank_loan' AND name LIKE 'emergency%%'",
                           (amount, amount, rate, b["id"])).rowcount
    if not updated:
        conn.execute("INSERT INTO company_debts (company_id, lender_account_id, kind, name, original_principal, principal_outstanding,"
                     " annual_rate_bps, start_period, maturity_period, repayment) VALUES (%s, %s, 'central_bank_loan',"
                     " 'emergency lending from the Central Bank', %s, %s, %s, %s, %s, 'bullet')",
                     (b["id"], world.central_bank, amount, amount, rate, period, period + 4000))
    first = not _one(conn, "SELECT 1 AS x FROM central_bank_support WHERE company_id = %s AND period = %s", (b["id"], period))
    conn.execute("INSERT INTO central_bank_support (company_id, period, day, amount, at) VALUES (%s, %s, %s, %s, %s)",
                 (b["id"], period, day, amount, now))
    if first:
        _news(conn, period, day, "central_bank_support", f"support:{b['ticker']}:{period}",
              {"company": b["name"], "ticker": b["ticker"], "amount": money(amount)}, tickers=(b["ticker"],))
        _link(conn, f"support:{b['ticker']}:{period}:{day}", f"run:{b['ticker']}:{period}",
              f"Its savers were leaving faster than its cash could pay, so the Central Bank lent {b['name']} {money(amount)} against its loans.",
              period, now)
        _advance(conn, b, 4, period, day, now, f"The Central Bank lent {b['name']} {money(amount)} against its loans.")


def _policy_rate(conn: Connection) -> int:
    row = _one(conn, "SELECT next_policy_rate_bps FROM economy_results ORDER BY period DESC LIMIT 1")
    return row["next_policy_rate_bps"] if row else data.NEUTRAL_RATE_BPS


def note_withdrawal(conn: Connection, company_id, amount: int, period: int, day: int) -> None:
    """A saver drew money out (already in deposit_flows, which is what the next day's trust reads). Kept for the callers."""
    return


def short_ban_for(conn: Connection, b: dict, now: datetime, why: str) -> None:
    """The Securities Regulator (a rule-based stand-in): no new short sales in a bank's shares while its savers run."""
    from simulation import exchange
    if not _one(conn, "SELECT to_regclass('short_bans') IS NOT NULL AS ok")["ok"]:
        return
    today, _ = exchange.session_of(now)
    until = today + timedelta(days=data.SHORT_BAN_DAYS)
    if _one(conn, "SELECT 1 AS x FROM short_bans WHERE company_id = %s AND until_day >= %s", (b["id"], today)):
        conn.execute("UPDATE short_bans SET until_day = greatest(until_day, %s) WHERE company_id = %s AND until_day >= %s",
                     (until, b["id"], today))
        return
    conn.execute("INSERT INTO short_bans (company_id, from_day, until_day, reason, at) VALUES (%s, %s, %s, %s, %s)",
                 (b["id"], today, until, why, now))


# ---------------------------------------------------------------------------
# One game day
# ---------------------------------------------------------------------------

def _last_day(conn: Connection) -> tuple[int, int]:
    row = _one(conn, "SELECT period, day FROM crisis_days ORDER BY period DESC, day DESC LIMIT 1")
    return (row["period"], row["day"]) if row else (0, 0)


def tick(conn: Connection, now: datetime) -> None:
    """Every few minutes: every game day of the running quarter that has ended and not been worked through is worked
    through, in order."""
    if not ready(conn) or not _one(conn, "SELECT 1 AS x FROM world_state"):
        return
    from simulation import careers
    w = careers.world_now(conn, now)
    closed_to = _one(conn, "SELECT last_closed_period FROM world_state")["last_closed_period"]
    if w["period"] != closed_to + 1:
        return                    # the quarter has ended and waits to be closed: the close works through its last days
    run_days(conn, w["period"], w["day"] - 1, now)


def run_days(conn: Connection, period: int, through: int, now: datetime) -> int:
    """Work through each game day of `period` up to `through` not yet worked through. Returns how many."""
    if not ready(conn):
        return 0
    done = 0
    with conn.transaction():
        conn.execute("SELECT pg_advisory_xact_lock(hashtext('crisis-days'))")
        deposits.setup(conn, period - 1, now)
        last_p, last_d = _last_day(conn)
        start = last_d + 1 if last_p == period else 1
        if last_p > period:
            return 0
        closes = _closes(conn)
        for day in range(start, min(through, clock.GAME_DAYS_PER_QUARTER) + 1):
            _one_day(conn, period, day, now, closes)
            done += 1
    return done


def _closes(conn: Connection) -> dict:
    try:
        from simulation import risk
        return risk.closes(conn, 6)
    except Exception:              # no trading yet: no share-price signal
        return {}


def _one_day(conn: Connection, period: int, day: int, now: datetime, closes: dict) -> None:
    banks = deposits.banks(conn)
    if not banks:
        return
    blanket = deposits.blanket(conn)
    before = {b["id"]: {**(_last(conn, b["id"]) or {"score": data.CONFIDENCE_START, "state": "calm"}), "headquarters": b["headquarters"]}
              for b in banks}
    today: dict = {}
    for b in banks:
        prev = before[b["id"]]
        if deposits.closed(conn, b["id"]):
            score, parts, state = 0, {}, "closed"
        else:
            aim, parts = target(conn, b, period, day, before, closes, blanket)
            score = prev["score"] + (aim - prev["score"]) * data.CONFIDENCE_DAILY_MOVE_BPS // BPS
            if score == prev["score"] and aim != prev["score"]:
                score += 1 if aim > prev["score"] else -1
            score = max(min(score, 100), 0)
            state = state_of(score)
        today[b["id"]] = {"score": score, "state": state, "parts": parts, "withdrawn": 0, "headquarters": b["headquarters"]}
    # Savers act on today's trust.
    for b in banks:
        t = today[b["id"]]
        if t["state"] in ("worried", "run", "panic"):
            t["withdrawn"] = _savers_run(conn, b, t["state"], today, period, day, now)
            if deposits.closed(conn, b["id"]):
                t.update(score=0, state="closed")
    for b in banks:
        t = today[b["id"]]
        conn.execute("INSERT INTO bank_confidence (company_id, period, day, score, state, parts, withdrawn, at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"
                     " ON CONFLICT (company_id, period, day) DO NOTHING",
                     (b["id"], period, day, t["score"], t["state"], Jsonb(t["parts"]), t["withdrawn"], now))
        _on_change(conn, b, before[b["id"]].get("state", "calm"), t, period, day, now)
    weights = {b["id"]: deposits.owed(conn, b["id"]) or 0 for b in banks}
    total = sum(weights.values()) or 1
    nat = sum(today[i]["score"] * w for i, w in weights.items()) // total
    runs = sum(1 for t in today.values() if t["state"] in ("run", "panic", "closed"))
    conn.execute("INSERT INTO crisis_days (period, day, national, blanket, at) VALUES (%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
                 (period, day, nat, blanket, now))
    if not blanket and (nat <= data.BLANKET_NATIONAL or runs >= data.BLANKET_RUNS):
        _blanket_on(conn, period, day, now, nat, runs)
    if nat >= data.CALM_NATIONAL:
        _come_home(conn, today, period, day, now)
    for b in banks:
        _maybe_placement(conn, b, period, day, now)
    _crisis_day(conn, banks, today, nat, period, day, now)


def _trusted(today: dict, banks: list[dict], leaving_id) -> list[tuple[dict, int]]:
    """Where frightened savers put their money: the banks still calm, more to the more trusted."""
    out = [(b, today[b["id"]]["score"]) for b in banks if b["id"] != leaving_id and today[b["id"]]["state"] == "calm"]
    return [(b, s) for b, s in out if s >= data.CONFIDENCE_WARNING] or out


def _spread(total: int, places: list[tuple[dict, int]]) -> list[tuple[dict, int]]:
    weight = sum(s for _, s in places)
    if total <= 0 or weight <= 0:
        return []
    parts = [(b, total * s // weight) for b, s in places]
    if parts:
        parts[0] = (parts[0][0], parts[0][1] + total - sum(a for _, a in parts))
    return [(b, a) for b, a in parts if a > 0]


def _savers_run(conn: Connection, b: dict, state: str, today: dict, period: int, day: int, now: datetime) -> int:
    """Households, and companies with savings there, draw money out of a bank they no longer trust. Returns what left."""
    above_bps, under_bps = data.RUN_WITHDRAWAL_BPS[state]
    banks = deposits.banks(conn)
    homes = _rows(conn, "SELECT location, account_id FROM households ORDER BY location")
    wanted: list[tuple[str, object, int, str | None]] = []
    for h in homes:
        above, under = deposits.household_split(conn, b, h["location"], h["account_id"])
        amount = apply_bps(above, above_bps) + apply_bps(under, under_bps)
        if amount > 0:
            wanted.append(("households", h["account_id"], amount, h["location"]))
    for c in _rows(conn, "SELECT a.id AS account_id, l.balance FROM ledger_balances l JOIN ledger_accounts a ON a.id = l.account_id"
                         " WHERE l.asset = %s AND l.balance > 0 AND a.kind = 'company' ORDER BY a.id", (b["asset"],)):
        g = deposits.guaranteed_part(conn, c["balance"])
        amount = apply_bps(c["balance"] - g, above_bps) + apply_bps(g, under_bps)
        if amount > 0:
            wanted.append(("company", c["account_id"], amount, None))
    need = sum(w[2] for w in wanted)
    if need <= 0:
        return 0
    conn.execute("SELECT pg_advisory_xact_lock(hashtext('bank-cash:' || %s::text))", (str(b["id"]),))   # one payer at a time
    can = secure_cash(conn, b, need, period, day, now)
    share_bps = can * BPS // need if need else 0
    left = 0
    trusted = _trusted(today, banks, b["id"])
    for holder, account, amount, location in wanted:
        amount = amount if share_bps >= BPS else apply_bps(amount, share_bps)
        if amount <= 0:
            continue
        if holder == "households":
            got = deposits.households_draw(conn, location, account, b, amount, period, day, now)
            again = apply_bps(got, data.REDEPOSIT_SAME_DAY_BPS)
            placed = sum(deposits.households_place(conn, location, account, ob, a, "returned", period, day, now)
                         for ob, a in _spread(again, trusted))
            conn.execute("UPDATE household_cash_held SET amount = amount + %s WHERE location = %s", (got - placed, location))
        else:
            got = deposits.company_draw(conn, account, b, amount, period, day, now)
            if trusted and got > 0:
                best = max(trusted, key=lambda x: x[1])[0]
                deposits.company_place(conn, account, best, got, period, day, now)
        left += got
    if can < need:
        # It could not pay all its savers asked for today: the Central Bank closes it.
        cannot_pay(conn, b, period, day, now)
    return left


def _come_home(conn: Connection, today: dict, period: int, day: int, now: datetime) -> None:
    """On a calm day, a twentieth of what households kept at home goes back into the banks they trust."""
    banks = deposits.banks(conn)
    trusted = [(b, today[b["id"]]["score"]) for b in banks if today[b["id"]]["state"] == "calm"]
    for h in _rows(conn, "SELECT c.location, c.amount, h.account_id FROM household_cash_held c JOIN households h ON h.location = c.location"
                         " WHERE c.amount > 0 ORDER BY c.location"):
        back = max(apply_bps(h["amount"], data.HOME_RETURN_BPS), min(h["amount"], deposits.guarantee()))
        placed = sum(deposits.households_place(conn, h["location"], h["account_id"], b, a, "returned", period, day, now)
                     for b, a in _spread(back, trusted))
        conn.execute("UPDATE household_cash_held SET amount = greatest(amount - %s, 0) WHERE location = %s", (placed, h["location"]))


def _maybe_placement(conn: Connection, b: dict, period: int, day: int, now: datetime) -> None:
    """A bank in a run for three days running raises new money: its big institutional owners buy new shares at a discount."""
    if deposits.closed(conn, b["id"]):
        return
    last = _rows(conn, "SELECT state FROM bank_confidence WHERE company_id = %s ORDER BY period DESC, day DESC LIMIT %s",
                 (b["id"], data.PLACEMENT_DAYS))
    if len(last) < data.PLACEMENT_DAYS or any(r["state"] not in ("run", "panic") for r in last):
        return
    if _one(conn, "SELECT 1 AS x FROM emergency_placements WHERE company_id = %s AND period = %s", (b["id"], period)):
        return
    f = figures(conn, b)
    if f["equity"] <= 0:
        return
    company = _one(conn, "SELECT * FROM companies WHERE id = %s", (b["id"],))
    price = _price(conn, b["id"])
    if not price:
        return
    price = max(price * (BPS - data.PLACEMENT_DISCOUNT_BPS) // BPS, 1)
    buyer = ledger.account_id(conn, ledger.INVESTORS_INSTITUTIONS)
    amount = min(apply_bps(f["equity"], data.PLACEMENT_EQUITY_BPS), max(ledger.balance(conn, buyer), 0))
    shares = amount // price
    if shares <= 0:
        return
    amount = shares * price
    from simulation import exchange
    exchange.cancel_all_in(conn, b["id"], now, "New shares were issued: every waiting order in this share was cancelled")
    exchange.allow_index_for(conn, shares * (_price(conn, b["id"]) or price))
    ledger.post(conn, kind="share_issue", period=period,
                memo=f"{b['name']}: new shares sold to its institutional owners at {money(price)} each, to raise money in a run", legs=[
                    ledger.Leg(company["account_id"], -shares, company["share_asset"]), ledger.Leg(buyer, shares, company["share_asset"]),
                    ledger.Leg(buyer, -amount), ledger.Leg(company["account_id"], amount)])
    _owners_changed(conn, b["id"], buyer)
    conn.execute("INSERT INTO emergency_placements (company_id, period, day, shares, price, amount, at) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                 (b["id"], period, day, shares, price, amount, now))
    _capital_move(conn, b["id"], amount, "new shares sold in a run", now)
    _news(conn, period, day, "bank_new_shares", f"placement:{b['ticker']}:{period}",
          {"company": b["name"], "ticker": b["ticker"], "amount": money(amount)}, tickers=(b["ticker"],))
    _link(conn, f"placement:{b['ticker']}:{period}", f"run:{b['ticker']}:{period}",
          f"After three days of queues, {b['name']} raised {money(amount)} by selling new shares to its big owners.", period, now)
    _advance(conn, b, 4, period, day, now, f"{b['name']} raised {money(amount)} of new money from its owners.")


def _price(conn: Connection, company_id) -> int | None:
    row = _one(conn, "SELECT coalesce(last_price, reference_price) AS p FROM market_instruments WHERE company_id = %s", (company_id,))
    return row["p"] if row else None


def _owners_changed(conn: Connection, company_id, account) -> None:
    """Who owns a company's shares is read from the ledger itself (a view), so it is always in step: nothing to do."""
    return


# ---------------------------------------------------------------------------
# What changes of state set off
# ---------------------------------------------------------------------------

def _on_change(conn: Connection, b: dict, was: str, t: dict, period: int, day: int, now: datetime) -> None:
    now_state = t["state"]
    order = {s: i for i, s in enumerate(STATES)}
    if now_state == was:
        return
    if now_state in ("run", "panic") and order[now_state] > order.get(was, 0):
        short_ban_for(conn, b, now, f"A run on {b['name']}: no new short sales while its savers queue")
        kind = "bank_run" if now_state == "run" else "bank_panic"
        cause = _main_cause(t["parts"])
        _news(conn, period, day, kind, f"{kind}:{b['ticker']}:{period}:{day}",
              {"company": b["name"], "ticker": b["ticker"], "location": b["headquarters"], "cause": cause}, tickers=(b["ticker"],))
        _link(conn, f"run:{b['ticker']}:{period}", f"trust:{b['ticker']}:{period}:{day}",
              f"Trust in {b['name']} fell to {t['score']} of 100, mostly from {cause}: savers began to queue.", period, now,
              {"trust": t["score"], **{k: v for k, v in t["parts"].items() if v}})
        _note_run_stories(conn, b, period, day, now)
        from simulation import chronicle
        chronicle.write(conn, "company", f"run:{b['ticker']}:{period}:{day}", "bank_run", f"A run on {b['name']}",
                        f"Trust in {b['name']} fell to {t['score']} of 100, mostly from {cause}. Savers queued to draw their money out.",
                        period, day, now, company_id=b["id"])


def _note_run_stories(conn: Connection, b: dict, period: int, day: int, now: datetime) -> None:
    """Keep, for the courts, the bad stories about a bank printed in the five game days before its run, and whether the
    rumour each carried was planted (and by whom). Never shown to players."""
    for s in _rows(conn, "SELECT id, author_id, lead FROM stories WHERE status = 'published' AND tone < 0 AND %s = ANY(tickers)"
                         " AND (period * 100 + day) BETWEEN %s AND %s", (b["ticker"], period * 100 + day - 5, period * 100 + day)):
        planted = None
        item_id = (s["lead"] or {}).get("item_id")
        if item_id:
            row = _one(conn, "SELECT planted_by FROM intel_items WHERE id = %s", (item_id,))
            planted = row["planted_by"] if row else None
        conn.execute("INSERT INTO run_stories (company_id, period, day, story_id, author_id, planted_by, at) VALUES (%s, %s, %s, %s, %s, %s, %s)"
                     " ON CONFLICT DO NOTHING", (b["id"], period, day, s["id"], s["author_id"], planted, now))


def _main_cause(parts: dict) -> str:
    worst = min(((v, k) for k, v in (parts or {}).items() if v < 0), default=None)
    return PART_NAMES[worst[1]] if worst else "fear"


def _blanket_on(conn: Connection, period: int, day: int, now: datetime, nat: int, runs: int) -> None:
    reason = (f"{runs} banks had runs at once" if runs >= data.BLANKET_RUNS else f"trust in the banks fell to {nat} of 100")
    row = _one(conn, "INSERT INTO blanket_guarantees (from_period, from_day, reason, at) VALUES (%s, %s, %s, %s) RETURNING id",
               (period, day, reason, now))
    _news(conn, period, day, "savings_guarantee", f"blanket:{row['id']}", {"reason": reason})
    for c in _rows(conn, "SELECT * FROM economic_crises WHERE status = 'open'"):
        _link(conn, f"guarantee:{row['id']}", f"crisis:{c['id']}",
              f"The Government promised every saving is safe, whatever its size, because {reason}.", period, now)
        _set_step(conn, c, 8, period, day, now, f"The Government promised that every saving is safe, whatever its size ({reason}).")


def blanket_lift(conn: Connection, period: int, now: datetime) -> None:
    """At a close: the Government lifts its promise once trust in the banks is back."""
    if not deposits.blanket(conn) or national(conn) < data.BLANKET_LIFT_NATIONAL:
        return
    if _one(conn, "SELECT 1 AS x FROM bank_resolutions WHERE status = 'open'"):
        return
    conn.execute("UPDATE blanket_guarantees SET until_period = %s, until_day = %s WHERE until_period IS NULL",
                 (period, clock.GAME_DAYS_PER_QUARTER))
    _news(conn, period + 1, 1, "guarantee_lifted", f"blanket-lifted:{period}", {"guarantee": money(deposits.guarantee())})


# ---------------------------------------------------------------------------
# A bank that cannot pay: closed, its hole filled, sold or taken into public hands
# ---------------------------------------------------------------------------

def cannot_pay(conn: Connection, b: dict, period: int, day: int, now: datetime, reason: str | None = None) -> int | None:
    """The Central Bank closes a bank that cannot pay its savers, or whose losses have eaten its owners' funds. Returns the
    resolution's number (or the one already open)."""
    open_one = _one(conn, "SELECT id FROM bank_resolutions WHERE company_id = %s AND status = 'open'", (b["id"],))
    if open_one:
        return open_one["id"]
    f = figures(conn, b)
    reason = reason or "it could not pay its savers what they asked for"
    equity = f["equity"]
    hole = max(-equity, 0)
    # The hole is filled by savers above the guarantee (unless every saving is guaranteed), then by the guarantee fund.
    bail = 0 if deposits.blanket(conn) else _bail_in(conn, b, hole, period, day, now)
    covered = 0
    if hole - bail > 0:
        covered = deposits.fund_pays(conn, b["account_id"], hole - bail, period, now,
                                     f"Deposit Guarantee Fund: fills what is left of {b['name']}'s hole, so every guaranteed saving is safe")
    _capital_move(conn, b["id"], bail + covered, "its hole filled when it was closed", now)
    owes = deposits.owed(conn, b["id"]) or 0
    needed = max(apply_bps(f["loans"], data.BANK_MINIMUM_CAPITAL_BPS) - max(equity, 0), apply_bps(owes, data.BANK_RESERVE_BPS), 1)
    words = (f"The Central Bank closed {b['name']}: {reason}. Its owners' funds were {money(equity)}. "
             + (f"Savers above the guarantee bore {money(bail)} of the hole. " if bail else "")
             + (f"The Deposit Guarantee Fund put in {money(covered)}. " if covered else "")
             + f"It needs {money(needed)} of new money to open again.")
    row = _one(conn, "INSERT INTO bank_resolutions (company_id, period, day, reason, equity, bail_in, covered, capital_needed, words, at)"
                     " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
               (b["id"], period, day, reason, equity, bail, covered, needed, words, now))
    conn.execute("UPDATE market_instruments SET halted_reason = %s WHERE company_id = %s",
                 (f"Closed by the Central Bank on day {day} of {clock.period_label(period)}: trading is stopped until it is resolved", b["id"]))
    _cancel_orders(conn, b["id"], now)
    _news(conn, period, day, "bank_closed", f"closed:{b['ticker']}:{row['id']}",
          {"company": b["name"], "ticker": b["ticker"], "location": b["headquarters"], "needed": money(needed)}, tickers=(b["ticker"],))
    _link(conn, f"closure:{b['ticker']}:{row['id']}", f"run:{b['ticker']}:{period}", words, period, now,
          {"equity": equity, "bail_in": bail, "covered": covered, "needed": needed})
    from simulation import chronicle
    chronicle.write(conn, "world", f"closure:{row['id']}", "bank_closed", f"{b['name']} closed by the Central Bank", words, period, day, now,
                    company_id=b["id"])
    _advance(conn, b, 7, period, day, now, f"The Central Bank closed {b['name']}.")
    from simulation import auctions
    auctions.open_bank_auction(conn, row["id"], now, period)
    return row["id"]


def _cancel_orders(conn: Connection, company_id, now: datetime) -> None:
    from simulation import exchange
    exchange.cancel_all_in(conn, company_id, now, "Trading in this share was stopped: the Central Bank closed the bank")


def _bail_in(conn: Connection, b: dict, hole: int, period: int, day: int, now: datetime) -> int:
    """Savers above the guarantee bear the hole, each in proportion to what they had above it. Returns what was written down."""
    if hole <= 0:
        return 0
    g = deposits.guarantee()
    holders = []
    for h in _rows(conn, "SELECT location, account_id FROM households ORDER BY location"):
        above, _ = deposits.household_split(conn, b, h["location"], h["account_id"])
        if above > 0:
            holders.append((h["account_id"], above, "households", h["location"]))
    for r in _rows(conn, "SELECT l.account_id, l.balance, a.kind FROM ledger_balances l JOIN ledger_accounts a ON a.id = l.account_id"
                         " WHERE l.asset = %s AND l.balance > %s AND a.kind IN ('player', 'empire', 'company') ORDER BY l.account_id",
                   (b["asset"], g)):
        holders.append((r["account_id"], r["balance"] - g, r["kind"], None))
    above_all = sum(h[1] for h in holders)
    take = min(hole, above_all)
    if take <= 0:
        return 0
    legs, written = [], 0
    for account, above, kind, location in holders:
        cut = above * take // above_all
        if cut <= 0:
            continue
        legs.append(ledger.Leg(account, -cut, b["asset"]))
        written += cut
        deposits._flow(conn, b["id"], account, "households" if kind == "households" else ("company" if kind == "company" else kind),
                       location, "bail_in", cut, period, day, now)
    if written <= 0:
        return 0
    legs.append(ledger.Leg(b["account_id"], written, b["asset"]))
    ledger.post(conn, kind="bail_in", period=period, legs=legs,
                memo=f"{b['name']} closed: savings above the guarantee written down to fill its hole")
    return written


def resolved(conn: Connection, resolution_id: int, *, buyer, paid: int, how: str, period: int, now: datetime) -> None:
    """A closed bank's new owner has put in its new money: it opens again. `how` is 'sold' or 'public'."""
    r = _one(conn, "SELECT * FROM bank_resolutions WHERE id = %s FOR UPDATE", (resolution_id,))
    company = _one(conn, "SELECT * FROM companies WHERE id = %s", (r["company_id"],))
    old = ledger.amount_in_existence(conn, company["share_asset"])
    # The old owners keep 5%; more if the bank still had owners' funds of its own when it was closed (a buyer pays for
    # what is put in, not for what was already there).
    kept_bps = data.RESCUE_OLD_OWNERS_BPS
    if r["equity"] > 0 and paid > 0:
        kept_bps = max(kept_bps, min(r["equity"] * BPS // (r["equity"] + paid), BPS - data.RESCUE_OLD_OWNERS_BPS))
    new = max(old * (BPS - kept_bps) // kept_bps, 1)
    price = max(paid // max(new, 1), 1)
    from simulation import exchange
    exchange.allow_index_for(conn, new * price)
    ledger.post(conn, kind="share_issue", period=period, memo=f"{company['name']}: new shares to its new owner, for the new money it put in",
                legs=[ledger.Leg(company["account_id"], -new, company["share_asset"]), ledger.Leg(buyer, new, company["share_asset"])])
    _owners_changed(conn, company["id"], buyer)
    conn.execute("UPDATE market_instruments SET halted_reason = NULL WHERE company_id = %s", (company["id"],))
    exchange.reprice(conn, company["id"], price, now, f"{company['name']} opened again with new owners and new money: its shares are"
                     f" priced at what the new owner paid for each new share")
    status = "sold" if how == "sold" else "public"
    resale = period + data.PUBLIC_RESALE_QUARTERS if how == "public" else None
    w = _now(conn, now)
    last_p, last_d = _last_day(conn)
    conn.execute("UPDATE bank_resolutions SET status = %s, new_owner = %s, price = %s, resale_period = %s, ended_at = %s,"
                 " reopened_period = %s, reopened_day = %s WHERE id = %s",
                 (status, buyer, paid, resale, now, last_p or w["period"], last_d, resolution_id))
    _capital_move(conn, company["id"], paid, "new money from its new owner", now)
    # Its savers trust it again, a little: a sound owner and fresh money behind it (on the last day worked through, so the
    # day-by-day record carries on from it).
    if last_p:
        conn.execute("INSERT INTO bank_confidence (company_id, period, day, score, state, parts, withdrawn, at) VALUES (%s, %s, %s, %s, 'calm', %s, 0, %s)"
                     " ON CONFLICT (company_id, period, day) DO UPDATE SET score = EXCLUDED.score, state = 'calm'",
                     (company["id"], last_p, last_d, data.CONFIDENCE_REOPEN, Jsonb({"support": 0}), now))
    name = _owner_name(conn, buyer)
    kind = "bank_rescued" if how == "sold" else "bank_public"
    _news(conn, w["period"], w["day"], kind, f"{kind}:{resolution_id}",
          {"company": company["name"], "ticker": company["ticker"], "buyer": name, "amount": money(paid)}, tickers=(company["ticker"],))
    _link(conn, f"rescue:{company['ticker']}:{resolution_id}", f"closure:{company['ticker']}:{resolution_id}",
          f"{name} put {money(paid)} of new money into {company['name']} and owns it now; it opened again.", period, now)
    b = {"id": company["id"], "ticker": company["ticker"], "name": company["name"], "headquarters": company["headquarters"]}
    _advance(conn, b, 8, w["period"], w["day"], now, f"{company['name']} opened again under {name}.")


def _owner_name(conn: Connection, account) -> str:
    row = _one(conn, "SELECT a.kind, a.name, a.code, p.display_name, e.name AS empire FROM ledger_accounts a"
                     " LEFT JOIN players p ON p.id = a.player_id LEFT JOIN empires e ON e.account_id = a.id WHERE a.id = %s", (account,))
    if row is None:
        return "a new owner"
    if row["code"] == deposits.GUARANTEE_FUND:
        return "the Deposit Guarantee Fund (public hands)"
    return row["empire"] or row["display_name"] or row["name"]


def public_hands(conn: Connection, resolution_id: int, period: int, now: datetime) -> None:
    """Nobody bid enough: the Deposit Guarantee Fund puts in the new money (borrowing from the Treasury) and owns the bank
    until it is sold again."""
    r = _one(conn, "SELECT r.*, c.account_id, c.name FROM bank_resolutions r JOIN companies c ON c.id = r.company_id WHERE r.id = %s", (resolution_id,))
    fund = ledger.account_id(conn, deposits.GUARANTEE_FUND)
    paid = deposits.fund_pays(conn, r["account_id"], r["capital_needed"], period, now,
                              f"Deposit Guarantee Fund: new money into {r['name']}, for new shares, taken into public hands", kind="share_issue")
    resolved(conn, resolution_id, buyer=fund, paid=paid, how="public", period=period, now=now)


def resell_public(conn: Connection, period: int, now: datetime) -> None:
    """At a close: a bank a year in public hands goes back on sale at the Auction House."""
    from simulation import auctions
    for r in _rows(conn, "SELECT * FROM bank_resolutions WHERE status = 'public' AND resale_period <= %s ORDER BY id", (period,)):
        if not _one(conn, "SELECT 1 AS x FROM auctions WHERE bank_id = %s AND status = 'open'", (r["company_id"],)):
            auctions.open_bank_resale(conn, r["id"], now, period)


def resold(conn: Connection, resolution_id: int, buyer, price: int, period: int, now: datetime) -> None:
    conn.execute("UPDATE bank_resolutions SET status = 'resold', new_owner = %s, price = coalesce(price, 0) + %s WHERE id = %s",
                 (buyer, price, resolution_id))
    r = _one(conn, "SELECT r.*, c.name, c.ticker FROM bank_resolutions r JOIN companies c ON c.id = r.company_id WHERE r.id = %s", (resolution_id,))
    w = _now(conn, now)
    _news(conn, w["period"], w["day"], "bank_resold", f"resold:{resolution_id}",
          {"company": r["name"], "ticker": r["ticker"], "buyer": _owner_name(conn, buyer), "price": money(price)}, tickers=(r["ticker"],))
    deposits.repay_fund_loans(conn, period)


def _now(conn: Connection, now: datetime) -> dict:
    from simulation import careers
    return careers.world_now(conn, now)


# ---------------------------------------------------------------------------
# The record of each crisis
# ---------------------------------------------------------------------------

def _weakness(conn: Connection, banks: list[dict]) -> str:
    """The hidden weakness a crisis grew from (kept back until it ends): the weakest bank's weakest fundamental."""
    worst = None
    for b in banks:
        f = figures(conn, b)
        for name, points in (("capital", _capital_points(f["capital_bps"], f["equity"])),
                             ("bad_loans", -min(max(f["bad_bps"] - 200, 0) * 3 // 100, 20)),
                             ("cash", -min(max(1_000 - f["cash_bps"], 0) // 100, 10)), ("rating", RATING_POINTS.get(f["rating"] or "BBB", 0))):
            if worst is None or points < worst[0]:
                worst = (points, name, b, f)
    if worst is None or worst[0] >= 0:
        return "No single bank was weak: it was fear that spread."
    points, name, b, f = worst
    if name == "capital":
        return f"{b['name']} had owners' funds of only {f['capital_bps'] / 100:.1f}% of its loans."
    if name == "bad_loans":
        return f"{b['name']} wrote off {f['bad_bps'] / 400:.1f}% of its loans in its last quarter: borrowers who did not repay."
    if name == "cash":
        return f"{b['name']} held cash of only {f['cash_bps'] / 100:.1f}% of what its savers had with it."
    return f"{b['name']} was rated {f['rating']}."


def _open_crisis(conn: Connection, kind: str, b: dict, banks: list[dict], period: int, day: int, now: datetime, words: str) -> dict:
    title = f"{'Banking' if kind == 'banking' else 'Confidence'} crisis, {clock.period_label(period)}: {b['name']}"
    row = _one(conn, "INSERT INTO economic_crises (kind, title, step, started_period, started_day, banks, weakness, steps, at)"
                     " VALUES (%s, %s, 2, %s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING RETURNING *",
               (kind, title, period, day, [b["id"]], _weakness(conn, banks),
                Jsonb([{"step": 2, "period": period, "day": day, "words": words}]), now))
    if row:
        _link(conn, f"crisis:{row['id']}", f"trust:{b['ticker']}:{period}:{day}", words, period, now)
    return row


def _set_step(conn: Connection, c: dict, step: int, period: int, day: int, now: datetime, words: str, bank_id=None) -> None:
    c = _one(conn, "SELECT * FROM economic_crises WHERE id = %s FOR UPDATE", (c["id"],))
    if c is None or c["status"] != "open":
        return
    steps = list(c["steps"] or [])
    banks = list(c["banks"] or [])
    if bank_id is not None and bank_id not in banks:
        banks.append(bank_id)
    if step <= c["step"] and step != 9:
        conn.execute("UPDATE economic_crises SET banks = %s WHERE id = %s", (banks, c["id"]))
        return
    if any(s["step"] == step for s in steps):
        return
    steps.append({"step": step, "period": period, "day": day, "words": words})
    conn.execute("UPDATE economic_crises SET step = greatest(step, %s), steps = %s, banks = %s WHERE id = %s",
                 (step, Jsonb(steps), banks, c["id"]))


def _advance(conn: Connection, b: dict, step: int, period: int, day: int, now: datetime, words: str) -> None:
    """Move every open crisis forward a step, for something a bank or an institution did."""
    for c in _rows(conn, "SELECT * FROM economic_crises WHERE status = 'open'"):
        _set_step(conn, c, step, period, day, now, words, bank_id=b.get("id"))


def _crisis_day(conn: Connection, banks: list[dict], today: dict, nat: int, period: int, day: int, now: datetime) -> None:
    by_id = {b["id"]: b for b in banks}
    warned = [i for i, t in today.items() if t["state"] != "closed" and t["score"] < data.CONFIDENCE_WARNING]
    worried = [i for i, t in today.items() if t["state"] in ("worried", "run", "panic")]
    running = [i for i, t in today.items() if t["state"] in ("run", "panic")]
    panic = [i for i, t in today.items() if t["state"] in ("panic", "closed")]
    open_ = _rows(conn, "SELECT * FROM economic_crises WHERE status = 'open' AND kind IN ('banking', 'confidence') ORDER BY id")
    if not open_ and warned:
        first = min(warned, key=lambda i: today[i]["score"])
        parts = today[first]["parts"] or {}
        fundamental = sum(v for k, v in parts.items() if k in FUNDAMENTAL and v < 0)
        fear = sum(v for k, v in parts.items() if k not in FUNDAMENTAL and v < 0)
        kind = "banking" if fundamental <= fear else "confidence"
        b = by_id[first]
        c = _open_crisis(conn, kind, b, banks, period, day, now,
                         f"Trust in {b['name']} fell below {data.CONFIDENCE_WARNING}, mostly from {_main_cause(parts)}.")
        open_ = [c] if c else []
    for c in open_:
        if worried:
            b = by_id[worried[0]]
            _set_step(conn, c, 3, period, day, now, f"Savers began to leave {b['name']}.", bank_id=b["id"])
        if len(worried) >= 2:
            _set_step(conn, c, 5, period, day, now, f"The worry spread: {', '.join(by_id[i]['name'] for i in worried)}.", bank_id=worried[1])
        if running or len(worried) >= 3:
            who = by_id[(running or worried)[0]]
            _set_step(conn, c, 6, period, day, now, f"Queues at {who['name']}: the tipping point.", bank_id=who["id"])
        if panic:
            _set_step(conn, c, 7, period, day, now, f"Panic at {by_id[panic[0]]['name']}.", bank_id=panic[0])
        c = _one(conn, "SELECT * FROM economic_crises WHERE id = %s", (c["id"],))
        # Fading, recovering, ending.
        calm_streak = _streak(conn, lambda r: r["min_score"] >= data.CONFIDENCE_WARNING, period, day)
        safe_streak = _streak(conn, lambda r: r["min_score"] >= data.CONFIDENCE_WORRIED and not r["closed"], period, day)
        nat_streak = _streak(conn, lambda r: r["national"] >= data.CALM_NATIONAL and not r["closed"], period, day)
        if c["step"] < 6 and calm_streak >= data.CRISIS_FADE_DAYS:
            _end(conn, c, "faded", period, day, now)
            continue
        if c["step"] >= 6 and safe_streak >= data.CRISIS_RECOVERY_DAYS:
            _set_step(conn, c, 9, period, day, now, "Every bank's savers had stayed put for days: the recovery began.")
            c = _one(conn, "SELECT * FROM economic_crises WHERE id = %s", (c["id"],))
        if c["step"] >= 9 and nat_streak >= data.CRISIS_END_DAYS and calm_streak >= data.CRISIS_END_DAYS \
                and not _one(conn, "SELECT 1 AS x FROM bank_resolutions WHERE status = 'open'"):
            _end(conn, c, "ended", period, day, now)


def _streak(conn: Connection, ok, period: int, day: int) -> int:
    """How many game days running, back from today, met a test (on the lowest bank's trust and the national figure)."""
    rows = _rows(conn, """
        SELECT d.period, d.day, d.national, min(c.score) FILTER (WHERE c.state <> 'closed') AS min_score,
               bool_or(c.state = 'closed') AS closed
        FROM crisis_days d JOIN bank_confidence c ON c.period = d.period AND c.day = d.day
        WHERE (d.period * 100 + d.day) <= %s GROUP BY d.period, d.day ORDER BY d.period DESC, d.day DESC LIMIT 30""", (period * 100 + day,))
    n = 0
    for r in rows:
        if r["min_score"] is None or not ok(r):
            break
        n += 1
    return n


def _end(conn: Connection, c: dict, how: str, period: int, day: int, now: datetime) -> None:
    """A crisis fades, or ends and goes into history, with its permanent report."""
    steps = list(c["steps"] or [])
    if how == "ended" and not any(s["step"] == 10 for s in steps):
        steps.append({"step": 10, "period": period, "day": day, "words": "It ended, and went into the history books."})
    long = period - c["started_period"] >= data.CRISIS_LONG_WEAKNESS_QUARTERS and how == "ended"
    report = _report(conn, c, steps, how, period, day, long)
    conn.execute("UPDATE economic_crises SET status = %s, step = %s, steps = %s, ended_period = %s, ended_day = %s, report = %s WHERE id = %s",
                 (how, 10 if how == "ended" else c["step"], Jsonb(steps), period, day, Jsonb(report), c["id"]))
    if how == "ended":
        _news(conn, period, day, "banks_calm", f"calm:{c['id']}", {"title": c["title"], "lesson": report["lesson"]})
        from simulation import chronicle
        chronicle.write(conn, "world", f"crisis:{c['id']}", "crisis", c["title"], report["summary"], period, day, now)
    if long:
        conn.execute("UPDATE economic_crises SET report = report || %s WHERE id = %s", (Jsonb({"long_weakness": True}), c["id"]))


def _report(conn: Connection, c: dict, steps: list, how: str, period: int, day: int, long: bool) -> dict:
    """The permanent Crisis Report: causes (from the Ripple), who was hit, who came through, and what stopped it."""
    banks = _rows(conn, "SELECT id, name, ticker FROM companies WHERE id = ANY(%s)", (list(c["banks"] or []),))
    since = c["started_period"] * 100 + c["started_day"]
    until = period * 100 + day
    hit, through = [], []
    for b in _rows(conn, "SELECT c.id, c.name, c.ticker FROM companies c JOIN bank_deposits d ON d.company_id = c.id ORDER BY c.name"):
        lowest = _one(conn, "SELECT min(score) AS s, bool_or(state = 'closed') AS shut, coalesce(sum(withdrawn), 0)::bigint AS gone"
                            " FROM bank_confidence WHERE company_id = %s AND (period * 100 + day) BETWEEN %s AND %s", (b["id"], since, until))
        entry = {"bank": b["name"], "ticker": b["ticker"], "lowest_trust": lowest["s"], "closed": bool(lowest["shut"]), "drawn_out": lowest["gone"]}
        (hit if (lowest["s"] or 100) < data.CONFIDENCE_WORRIED or lowest["shut"] else through).append(entry)
    support = _one(conn, "SELECT coalesce(sum(amount), 0)::bigint AS t FROM central_bank_support WHERE (period * 100 + day) BETWEEN %s AND %s",
                   (since, until))["t"]
    placed = _one(conn, "SELECT coalesce(sum(amount), 0)::bigint AS t FROM emergency_placements WHERE (period * 100 + day) BETWEEN %s AND %s",
                  (since, until))["t"]
    closures = _rows(conn, "SELECT r.*, c.name FROM bank_resolutions r JOIN companies c ON c.id = r.company_id"
                           " WHERE (r.period * 100 + r.day) BETWEEN %s AND %s ORDER BY r.id", (since, until))
    guarantee = _one(conn, "SELECT * FROM blanket_guarantees WHERE (from_period * 100 + from_day) BETWEEN %s AND %s ORDER BY id LIMIT 1",
                     (since, until))
    stopped = []
    if support:
        stopped.append(f"the Central Bank's emergency lending ({money(support)})")
    if placed:
        stopped.append(f"new money from banks' owners ({money(placed)})")
    if guarantee:
        stopped.append("the Government's promise that every saving was safe")
    for r in closures:
        stopped.append(f"closing {r['name']} and finding it new money ({money(r['capital_needed'])})")
    if how == "faded":
        stopped = stopped or ["trust came back before savers ran"]
    causes = [l["words"] for l in _rows(conn, "SELECT words FROM ripple_links WHERE effect LIKE 'crisis:%%' AND effect = %s ORDER BY id",
                                        (f"crisis:{c['id']}",))]
    phases = [{"phase": name, "steps": [s for s in steps if s["step"] in nums]} for name, nums in PHASES]
    summary = (f"{c['title']} {'faded before it became a crisis' if how == 'faded' else 'ran its course'}"
               f" (from day {c['started_day']} of {clock.period_label(c['started_period'])} to day {day} of {clock.period_label(period)})."
               f" What made it possible: {c['weakness']} What stopped it: {'; '.join(stopped) or 'nothing was needed'}.")
    lesson = ("A bank that keeps strong owners' funds and plenty of cash can let fear pass."
              if not closures else "A bank whose losses ate its owners' funds could not be saved by cash alone.")
    return {"summary": summary, "weakness": c["weakness"], "causes": causes, "phases": phases, "hit": hit, "came_through": through,
            "stopped_by": stopped, "central_bank": support, "new_money": placed, "closures": [r["name"] for r in closures],
            "lesson": lesson, "long_weakness": long, "how": how}


# ---------------------------------------------------------------------------
# At the quarter's close
# ---------------------------------------------------------------------------

def before_close(conn: Connection, period: int, now: datetime) -> None:
    """Before the banks close their quarter: the quarter's last game days are worked through."""
    run_days(conn, period, clock.GAME_DAYS_PER_QUARTER, now)


def at_close(conn: Connection, period: int, now: datetime) -> None:
    """After every company has filed: a bank whose losses have eaten its owners' funds is closed; the Government's promise
    is lifted if trust is back; a bank a year in public hands goes back on sale; the Crisis Watch takes its reading."""
    if not ready(conn):
        return
    for b in deposits.banks(conn):
        filed = _one(conn, "SELECT total_equity FROM company_results WHERE company_id = %s AND period = %s", (b["id"], period))
        if filed and filed["total_equity"] + capital_moved(conn, b["id"], period) < 0 and not deposits.closed(conn, b["id"]):
            # (Recorded in the next quarter: this one's accounts are already filed.)
            cannot_pay(conn, b, period + 1, 1, now, reason="its losses had eaten all its owners' funds")
    blanket_lift(conn, period, now)
    resell_public(conn, period, now)
    from simulation import crisiswatch
    crisiswatch.measure(conn, period, now)


def rate_relief_bps(conn: Connection) -> int:
    """In a banking crisis that has reached its tipping point, the Central Bank leans towards a lower rate."""
    if not ready(conn):
        return 0
    c = _one(conn, "SELECT max(step) AS s FROM economic_crises WHERE status = 'open' AND kind IN ('banking', 'confidence')")
    if c and c["s"] and c["s"] >= 6:
        return -data.CRISIS_RATE_RELIEF_BPS
    return 0


def lending_bps(conn: Connection, company_id) -> int:
    """How much of its usual new lending a bank does in its state: a bank whose savers are leaving lends less."""
    if not ready(conn):
        return BPS
    last = _last(conn, company_id)
    return data.CRISIS_LENDING_BPS.get(last["state"] if last else "calm", BPS)


# ---------------------------------------------------------------------------
# News and the Ripple
# ---------------------------------------------------------------------------

def _news(conn: Connection, period: int, day: int, kind: str, story: str, facts: dict, tickers=()) -> None:
    from simulation import news
    news.publish(conn, period=period, day=min(max(day, 1), clock.GAME_DAYS_PER_QUARTER), kind=kind, story=story, facts=facts, tickers=tickers)


def _link(conn: Connection, effect: str, cause: str, words: str, period: int, now: datetime, numbers: dict | None = None) -> None:
    from simulation import ripple
    ripple.link(conn, effect, cause, words, period, now, numbers)


# ---------------------------------------------------------------------------
# What players see
# ---------------------------------------------------------------------------

def bank_view(conn: Connection, now: datetime) -> list[dict]:
    """Each bank's trust and its public parts, its recent days, and whether it is closed. Never a saver's money."""
    if not ready(conn):
        return []
    trust = trust_now(conn)
    out = []
    for b in deposits.banks(conn):
        t = trust.get(b["id"], {})
        days = _rows(conn, "SELECT period, day, score, state FROM bank_confidence WHERE company_id = %s ORDER BY period DESC, day DESC LIMIT 30",
                     (b["id"],))
        r = _one(conn, "SELECT id, words, status, capital_needed FROM bank_resolutions WHERE company_id = %s ORDER BY id DESC LIMIT 1", (b["id"],))
        out.append({"ticker": b["ticker"], "name": b["name"], "headquarters": b["headquarters"], "trust": t.get("score"),
                    "state": t.get("state", "calm"), "change": t.get("change"),
                    "parts": [{"part": k, "name": PART_NAMES.get(k, k), "points": v} for k, v in (t.get("parts") or {}).items() if v],
                    "days": [{"period": d["period"], "day": d["day"], "score": d["score"], "state": d["state"]} for d in reversed(days)],
                    "closed": deposits.closed(conn, b["id"]),
                    "resolution": {"words": r["words"], "status": r["status"]} if r else None})
    return out


def crises_view(conn: Connection, now: datetime) -> list[dict]:
    """Every crisis on the record. An open one's hidden weakness is never shown; its report appears when it ends."""
    if not ready(conn):
        return []
    out = []
    for c in _rows(conn, "SELECT * FROM economic_crises ORDER BY id DESC LIMIT 40"):
        names = [r["name"] for r in _rows(conn, "SELECT name FROM companies WHERE id = ANY(%s) ORDER BY name", (list(c["banks"] or []),))]
        out.append({"id": c["id"], "kind": c["kind"], "title": c["title"], "status": c["status"], "step": c["step"],
                    "step_name": STEPS[c["step"]], "phase": phase_of(c["step"]),
                    "started": {"period": c["started_period"], "day": c["started_day"], "label": clock.period_label(c["started_period"])},
                    "ended": {"period": c["ended_period"], "day": c["ended_day"], "label": clock.period_label(c["ended_period"])} if c["ended_period"] else None,
                    "banks": names, "steps": [{**s, "name": STEPS[s["step"]], "phase": phase_of(s["step"])} for s in (c["steps"] or [])],
                    "report": c["report"] if c["status"] != "open" else None,
                    "why": _rows(conn, "SELECT words FROM ripple_links WHERE effect = %s ORDER BY id", (f"crisis:{c['id']}",))})
    return out


def check_books(conn: Connection) -> list[str]:
    """The crises stage's own checks, at every close: savers' money adds up, the guarantee fund's loans are sane, and a
    closed bank's shares do not trade."""
    if not ready(conn):
        return []
    problems = []
    for b in deposits.banks(conn):
        owes = deposits.owed(conn, b["id"]) or 0
        held = _one(conn, "SELECT coalesce(sum(balance), 0)::bigint AS t FROM ledger_balances WHERE asset = %s AND balance > 0", (b["asset"],))["t"]
        if owes != held or owes < 0:
            problems.append(f"{b['name']}: what it owes its savers ({owes}) is not what its savers hold ({held}).")
        over = _one(conn, "SELECT count(*) AS n FROM household_deposits_covered c JOIN households h ON h.location = c.location"
                          " WHERE c.company_id = %s AND c.covered > coalesce((SELECT balance FROM ledger_balances l WHERE l.account_id = h.account_id"
                          " AND l.asset = %s), 0)", (b["id"], b["asset"]))["n"]
        if over:
            problems.append(f"{b['name']}: more households' savings marked as guaranteed than they hold.")
    if _one(conn, "SELECT 1 AS x FROM guarantee_fund_loans WHERE outstanding > amount OR outstanding < 0"):
        problems.append("A Deposit Guarantee Fund loan stands above what was lent.")
    if _one(conn, "SELECT 1 AS x FROM bank_resolutions r JOIN market_instruments m ON m.company_id = r.company_id"
                  " WHERE r.status = 'open' AND m.halted_reason IS NULL"):
        problems.append("A bank the Central Bank closed is still trading.")
    return problems
