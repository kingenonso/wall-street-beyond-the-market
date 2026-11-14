"""Insurance: four policies a player can buy, under Money (owner, 9 November 2026).

Each policy answers a loss the game already inflicts, and every claim is made against a loss the game has recorded:

  1. Property and premises    the wear on buildings you own, the repair less an excess. Wear on a building whose upkeep
                              was not kept is the owner's own doing and is not covered.
  2. Directors' and officers' the tribunal's costs and damages ordered against you. The disgorgement and the fine never:
                              giving back a gain is not a loss, and a punishment that could be insured would not punish.
                              It answers cases opened two years or more after the cover began, so no wrong done before
                              it can be insured after.
  3. Income protection        half your last salary, each quarter for up to a year, after a dismissal, while out of work.
                              Resigning, changing build and moving employer are your own choice and are not covered.
  4. Personal umbrella        a top-up: when a loss is larger than the cover of the policy that answers it, the umbrella
                              pays the rest, up to its own cover.

The premium is the expected loss read from the last year of the game's own record, plus a loading, plus a small charge
on the cover so no cover is free. It loses money on average, as insurance does; what it buys is certainty and a cheaper
personal loan, because a lender charges less to a borrower whose assets and income are insured.

Every naira moves through the ledger: premiums into the policy account at `insurance:pool`, claims out of it. The pool
pays only what it holds: a claim larger than the pool is paid in part, and the shortfall is shown.

A claim on a loss the claimant caused is refused, the premium is kept, and the insurer refers it to the tribunal as
insurance fraud. The second such refusal ends all of the player's cover, and no insurer writes for them again.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from psycopg import Connection
from psycopg.rows import dict_row

from simulation import careers, clock, ledger
from simulation import world_data as data
from simulation.money import BPS, naira

POOL = "insurance:pool"
KINDS = ("property", "directors", "income", "umbrella")
NAMES = {
    "property": "Property and premises",
    "directors": "Directors' and officers'",
    "income": "Income protection",
    "umbrella": "Personal umbrella",
}
# The policies a lender counts. The umbrella only tops the others up, so it does not count on its own.
LENDER_COUNTS = ("property", "directors", "income")


class InsuranceError(Exception):
    """A request the insurer refuses, in words for the player."""


def _rows(conn: Connection, sql: str, params=()) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def _one(conn: Connection, sql: str, params=()) -> dict | None:
    rows = _rows(conn, sql, params)
    return rows[0] if rows else None


def money(kobo: int) -> str:
    return f"₦{kobo / 100:,.2f}"


def ready(conn: Connection) -> bool:
    return _one(conn, "SELECT to_regclass('insurance_policies') IS NOT NULL AS ok")["ok"] is True


def pool(conn: Connection):
    """The policy account: premiums in, claims out, nothing else. Made the first time it is needed."""
    row = _one(conn, "SELECT id FROM ledger_accounts WHERE code = %s", (POOL,))
    if row:
        return row["id"]
    made = ledger.create_account(conn, kind="escrow", name="The insurers' policy account", code=POOL)
    # The insurers start with capital of their own, put up by the pension funds, so the first claims are not paid out of
    # a handful of premiums. It is theirs: what premiums earn beyond the claims stays in the account.
    ledger.pay_up_to(conn, payer=ledger.account_id(conn, ledger.INVESTORS_INSTITUTIONS), receiver=made,
                     wanted=naira(data.INSURANCE_POOL_CAPITAL_NAIRA), kind="insurance_capital",
                     memo="The insurers' own capital, put up by the pension funds")
    return made


def _quarter_start(conn: Connection, period: int) -> datetime:
    world = _one(conn, "SELECT world_start, weeks_ahead FROM world_state")
    start = clock.effective_start(world["world_start"], world["weeks_ahead"])
    return start + timedelta(days=clock.REAL_DAYS_PER_QUARTER * (max(period, 1) - 1))


def _running_period(conn: Connection) -> int:
    return _one(conn, "SELECT last_closed_period FROM world_state")["last_closed_period"] + 1


# ---------------------------------------------------------------------------
# What a player has to insure
# ---------------------------------------------------------------------------

def _buildings(conn: Connection, account) -> list[dict]:
    """The standing buildings a player holds a share of, and what their share is worth today."""
    from simulation import property as prop
    rate = prop.policy_rate(conn)
    ds = prop.districts(conn)
    out = []
    for p in _rows(conn, "SELECT p.*, h.share_bps, h.since_period FROM property_holdings h JOIN properties p ON p.id = h.property_id"
                         " WHERE h.account_id = %s AND p.status = 'standing' AND p.kind <> 'land' ORDER BY p.id", (account,)):
        worth = prop.value(p, ds[p["district_id"]], rate)
        out.append({"id": p["id"], "name": p["name"], "condition": p["condition"], "share_bps": p["share_bps"],
                    "since_period": p["since_period"], "value": worth * p["share_bps"] // BPS})
    return out


def _salary(conn: Connection, player_id, now: datetime) -> int:
    if careers.current_job(conn, player_id) is None:
        return 0
    mine = careers.career(conn, player_id)
    if mine is None:
        return 0
    return careers.salary_per_quarter(mine["level"], careers.world_now(conn, now)["wage_index_bps"])


def _in_force(conn: Connection, player_id, kind: str | None = None) -> list[dict]:
    sql = "SELECT * FROM insurance_policies WHERE player_id = %s AND ended_at IS NULL"
    params: tuple = (player_id,)
    if kind:
        sql += " AND kind = %s"
        params += (kind,)
    return _rows(conn, sql + " ORDER BY id", params)


def most_cover(conn: Connection, player_id, kind: str, now: datetime) -> int:
    """The most cover of a kind the insurer will write: never more than there is to lose."""
    if kind == "property":
        account = ledger.player_account_id(conn, player_id)
        return sum(b["value"] for b in _buildings(conn, account)) if account else 0
    if kind == "directors":
        return naira(data.INSURANCE_DIRECTORS_MOST_NAIRA)
    if kind == "income":
        return _salary(conn, player_id, now) * data.INSURANCE_INCOME_SHARE_BPS // BPS * data.INSURANCE_INCOME_QUARTERS
    if kind == "umbrella":
        return sum(p["cover"] for p in _in_force(conn, player_id) if p["kind"] != "umbrella")
    raise InsuranceError("The insurer sells four policies: property, directors' and officers', income and umbrella.")


# ---------------------------------------------------------------------------
# The price: the expected loss read from the record, a loading, and a charge on the cover
# ---------------------------------------------------------------------------

def _window(period: int) -> tuple[int, int]:
    """The last year of closed quarters before `period`."""
    return period - data.INSURANCE_RECORD_QUARTERS, period - 1


def _players(conn: Connection) -> int:
    return max(_one(conn, "SELECT count(*) AS n FROM players")["n"], 1)


def wear_rate_bps(conn: Connection, period: int) -> int:
    """What a quarter's wear cost, as a share of the buildings' worth, over the last year of the record: the repair
    of the points lost by buildings that were kept up (wear on a building left without upkeep is not insured)."""
    first, last = _window(period)
    row = _one(conn, """
        SELECT coalesce(sum(CASE WHEN prev.condition - r.condition BETWEEN 1 AND %s::integer
                                 THEN (prev.condition - r.condition)::numeric * r.value * %s::numeric / (%s::numeric * %s::numeric) ELSE 0 END), 0) AS cost,
               coalesce(sum(r.value), 0) AS worth
        FROM property_results r
        JOIN property_results prev ON prev.property_id = r.property_id AND prev.period = r.period - 1
        JOIN properties p ON p.id = r.property_id
        WHERE r.period BETWEEN %s AND %s AND p.kind <> 'land'
    """, (data.WEAR_WITH_UPKEEP, data.RENOVATION_BPS, data.RENOVATION_POINTS, BPS, first, last))
    if not row["worth"]:
        return data.WEAR_WITH_UPKEEP * data.RENOVATION_BPS // data.RENOVATION_POINTS
    return int(row["cost"] * BPS / row["worth"])


def expected_loss(conn: Connection, player_id, kind: str, cover: int, excess: int, period: int, now: datetime) -> int:
    """A quarter's expected claim on this policy, from the record of the last year. Never a number made up."""
    first, last = _window(period)
    if kind == "property":
        account = ledger.player_account_id(conn, player_id)
        rate = wear_rate_bps(conn, period)
        total = 0
        for b in _buildings(conn, account) if account else []:
            total += max(min(b["value"] * rate // BPS - excess, cover), 0)
        return total
    if kind == "directors":
        start, end = _quarter_start(conn, first), _quarter_start(conn, last + 1)
        cases = _rows(conn, "SELECT costs + damages AS covered FROM court_cases WHERE status = 'judged'"
                            " AND decided_at >= %s AND decided_at < %s", (start, end))
        total = sum(max(min(c["covered"] - excess, cover), 0) for c in cases)
        return total // (_players(conn) * data.INSURANCE_RECORD_QUARTERS)
    if kind == "income":
        dismissed = _one(conn, "SELECT count(*) AS n FROM employments WHERE ended_reason LIKE 'dismissed:%%'"
                               " AND ended_period BETWEEN %s AND %s", (first, last))["n"]
        employed = max(_one(conn, "SELECT count(*) AS n FROM employments WHERE ended_at IS NULL")["n"], 1)
        payout = max(min(_salary(conn, player_id, now) * data.INSURANCE_INCOME_SHARE_BPS // BPS
                         * data.INSURANCE_INCOME_QUARTERS - excess, cover), 0)
        return payout * dismissed // (employed * data.INSURANCE_RECORD_QUARTERS)
    if kind == "umbrella":
        topped = _one(conn, "SELECT coalesce(sum(umbrella), 0) AS t, count(*) FILTER (WHERE umbrella > 0) AS n"
                            " FROM insurance_claims WHERE period BETWEEN %s AND %s", (first, last))
        if not topped["n"]:
            return 0
        return min(topped["t"] // topped["n"], cover) * topped["n"] // (_players(conn) * data.INSURANCE_RECORD_QUARTERS)
    raise InsuranceError("There is no such policy.")


def _record(conn: Connection, player_id, kind: str) -> dict:
    row = _one(conn, "SELECT * FROM insurance_records WHERE player_id = %s AND kind = %s", (player_id, kind))
    return row or {"clean_quarters": 0, "counted_period": 0}


def no_claims_bps(conn: Connection, player_id, kind: str) -> int:
    years = _record(conn, player_id, kind)["clean_quarters"] // clock.QUARTERS_PER_YEAR
    return min(years * data.INSURANCE_NO_CLAIMS_STEP_BPS, data.INSURANCE_NO_CLAIMS_MOST_BPS)


def quote(conn: Connection, player_id, kind: str, cover: int, excess: int, now: datetime, *, period: int | None = None) -> dict:
    """A quarter's premium, line by line, so the player can see what it is made of."""
    if kind not in KINDS:
        raise InsuranceError("The insurer sells four policies: property, directors' and officers', income and umbrella.")
    period = period if period is not None else careers.world_now(conn, now)["period"]
    expected = expected_loss(conn, player_id, kind, cover, excess, period, now)
    loading = expected * data.INSURANCE_LOADING_BPS // BPS
    on_cover = cover * data.INSURANCE_RATE_ON_COVER_BPS // BPS
    before = expected + loading + on_cover
    discount_bps = no_claims_bps(conn, player_id, kind)
    discount = before * discount_bps // BPS
    return {"kind": kind, "cover": cover, "excess": excess, "expected_loss": expected, "loading": loading,
            "on_cover": on_cover, "no_claims_bps": discount_bps, "discount": discount,
            "premium": max(before - discount, 1)}


# ---------------------------------------------------------------------------
# Buying and cancelling
# ---------------------------------------------------------------------------

def barred(conn: Connection, player_id) -> bool:
    return _one(conn, "SELECT 1 AS x FROM insurance_bars WHERE player_id = %s", (player_id,)) is not None


def _whole(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def buy(conn: Connection, player_id, kind: str, cover: int, excess: int, now: datetime) -> dict:
    """Buy a policy. The first quarter's premium is paid at once, from your own account into the policy account."""
    with conn.transaction():
        careers.books_open(conn, now)
        conn.execute("SELECT 1 FROM players WHERE id = %s FOR UPDATE", (player_id,))
        if kind not in KINDS:
            raise InsuranceError("The insurer sells four policies: property, directors' and officers', income and umbrella.")
        if barred(conn, player_id):
            raise InsuranceError("No insurer will write for you again: two of your claims were refused because you "
                                 "caused the loss.")
        if not _whole(cover) or cover <= 0:
            raise InsuranceError("Name the cover you want, in naira.")
        if not _whole(excess) or excess < 0 or excess >= cover:
            raise InsuranceError("The excess is the part of each loss you bear yourself: nought or more, and less than the cover.")
        if _in_force(conn, player_id, kind):
            raise InsuranceError(f"You already hold {NAMES[kind].lower()} cover. Cancel it first to buy it on other terms.")
        most = most_cover(conn, player_id, kind, now)
        if most <= 0:
            raise InsuranceError({
                "property": "You own no buildings to insure.",
                "income": "Income protection is sold to people in work. Find a job first.",
                "umbrella": "The umbrella tops up your other cover. Buy one of the other policies first.",
            }.get(kind, "There is nothing to insure."))
        if cover > most:
            raise InsuranceError(f"The insurer will cover at most {money(most)}: no more than there is to lose.")
        account = ledger.player_account_id(conn, player_id)
        period = careers.world_now(conn, now)["period"]
        priced = quote(conn, player_id, kind, cover, excess, now, period=period)
        try:
            ledger.transfer(conn, payer=account, receiver=pool(conn), amount=priced["premium"], kind="insurance_premium",
                            memo=f"{NAMES[kind]} cover, the premium for {clock.period_label(period)}", period=period)
        except ledger.InsufficientFunds:
            raise InsuranceError(f"The first quarter's premium is {money(priced['premium'])}, which you do not have.") from None
        row = _one(conn, "INSERT INTO insurance_policies (player_id, kind, cover, excess, premium, started_period, started_at,"
                         " paid_through) VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
                   (player_id, kind, cover, excess, priced["premium"], period, now, period))
        conn.execute("INSERT INTO insurance_records (player_id, kind) VALUES (%s, %s) ON CONFLICT DO NOTHING", (player_id, kind))
        return {"policy_id": row["id"], **priced, "period": period}


def _end(conn: Connection, policy_id: int, reason: str, period: int, now: datetime) -> None:
    conn.execute("UPDATE insurance_policies SET ended_period = %s, ended_at = %s, ended_reason = %s"
                 " WHERE id = %s AND ended_at IS NULL", (period, now, reason, policy_id))


def cancel(conn: Connection, player_id, kind: str, now: datetime) -> dict:
    """Cancel a policy. The quarter already paid for is not refunded; the no-claims record is kept."""
    with conn.transaction():
        careers.books_open(conn, now)
        conn.execute("SELECT 1 FROM players WHERE id = %s FOR UPDATE", (player_id,))
        held = _in_force(conn, player_id, kind)
        if not held:
            raise InsuranceError("You hold no cover of that kind.")
        period = careers.world_now(conn, now)["period"]
        _end(conn, held[0]["id"], "cancelled", period, now)
        # An umbrella with nothing left under it has nothing to top up.
        if kind != "umbrella" and not [p for p in _in_force(conn, player_id) if p["kind"] != "umbrella"]:
            for u in _in_force(conn, player_id, "umbrella"):
                _end(conn, u["id"], "cancelled", period, now)
        return {"kind": kind, "ended": "cancelled", "period": period}


# ---------------------------------------------------------------------------
# What it does for borrowing
# ---------------------------------------------------------------------------

def _debts(conn: Connection, account) -> int:
    loans = _one(conn, "SELECT coalesce(sum(outstanding), 0)::bigint AS o FROM player_loans WHERE borrower = %s"
                       " AND kind = 'personal' AND status <> 'repaid'", (account,))["o"]
    mortgages = _one(conn, "SELECT coalesce(sum(outstanding), 0)::bigint AS o FROM mortgages WHERE borrower = %s"
                           " AND status IN ('open', 'shortfall')", (account,))["o"]
    return loans + mortgages


def lender_cover(conn: Connection, player_id) -> int:
    """The cover a lender counts: in force, its premium paid for the running quarter, and not the umbrella."""
    if not ready(conn):
        return 0
    period = _running_period(conn)
    return _one(conn, "SELECT coalesce(sum(cover), 0)::bigint AS c FROM insurance_policies WHERE player_id = %s"
                      " AND ended_at IS NULL AND paid_through >= %s AND kind = ANY(%s)",
                (player_id, period, list(LENDER_COUNTS)))["c"]


def personal_spread_bps(conn: Connection, player_id, now: datetime | None = None, *, borrowing: int = 0) -> int:
    """The spread over the Central Bank's rate on a personal loan: less when cover is at least half the debt, and less
    again when it is the whole debt. The debt is what is owed on personal loans and mortgages, with what is being
    borrowed now."""
    spread = data.PERSONAL_LOAN_SPREAD_BPS
    cover = lender_cover(conn, player_id)
    if cover <= 0:
        return spread
    account = ledger.player_account_id(conn, player_id)
    debt = (_debts(conn, account) if account else 0) + max(borrowing, 0)
    steps = int(cover * 2 >= debt) + int(cover >= debt)
    return spread - min(steps, data.INSURED_SPREAD_STEPS) * data.INSURED_SPREAD_STEP_BPS


# ---------------------------------------------------------------------------
# Losses on the record, and claims against them
# ---------------------------------------------------------------------------

def losses(conn: Connection, player_id, now: datetime) -> list[dict]:
    """Every loss on the player's record in the last year that a policy could answer, each named by the record it is
    read from. The amounts are the game's; a claim can only be made against one of these."""
    period = careers.world_now(conn, now)["period"]
    first = period - data.INSURANCE_CLAIM_WINDOW_QUARTERS
    account = ledger.player_account_id(conn, player_id)
    out: list[dict] = []
    if account is not None:
        for r in _rows(conn, """
            SELECT r.period, r.property_id, r.value, r.condition, prev.condition AS before, p.name, h.share_bps
            FROM property_results r
            JOIN property_results prev ON prev.property_id = r.property_id AND prev.period = r.period - 1
            JOIN properties p ON p.id = r.property_id
            JOIN property_holdings h ON h.property_id = r.property_id AND h.account_id = %s AND h.since_period <= r.period
            WHERE r.period >= %s AND r.period < %s AND prev.condition > r.condition AND p.kind <> 'land'
            ORDER BY r.period, r.property_id
        """, (account, first, period)):
            points = r["before"] - r["condition"]
            loss = points * r["value"] * data.RENOVATION_BPS // (data.RENOVATION_POINTS * BPS) * r["share_bps"] // BPS
            kept = points <= data.WEAR_WITH_UPKEEP
            out.append({"key": f"property:{r['property_id']}:{r['period']}", "kind": "property", "period": r["period"],
                        "at": _quarter_start(conn, r["period"] + 1), "loss": loss, "property_id": r["property_id"],
                        "caused": not kept,
                        "words": (f"{r['name']} lost {points} points of condition in {clock.period_label(r['period'])}, "
                                  + ("with its upkeep kept." if kept else "with its upkeep not kept."))})
    for e in _rows(conn, "SELECT e.id, e.ended_at, e.ended_period, e.ended_reason, e.build FROM employments e"
                         " WHERE e.player_id = %s AND e.ended_at IS NOT NULL AND e.ended_period >= %s ORDER BY e.id",
                   (player_id, first)):
        reason = e["ended_reason"] or ""
        if reason.startswith("dismissed:"):
            caused = False
        elif reason == "resigned":
            caused = True
        else:
            continue                                  # changing build or employer is a move, not a loss
        mine = careers.career(conn, player_id, e["build"])
        salary = careers.salary_per_quarter(mine["level"] if mine else 1, careers.world_now(conn, now)["wage_index_bps"])
        out.append({"key": f"job:{e['id']}", "kind": "income", "period": e["ended_period"], "at": e["ended_at"],
                    "loss": salary * data.INSURANCE_INCOME_QUARTERS, "salary": salary, "caused": caused,
                    "words": f"Left a job in {clock.period_label(e['ended_period'])}: {reason}."})
    if _one(conn, "SELECT to_regclass('court_cases') IS NOT NULL AS ok")["ok"]:
        for c in _rows(conn, "SELECT id, kind, words, costs, damages, fine, disgorgement, opened_period, opened_at, decided_at"
                             " FROM court_cases WHERE defendant_id = %s AND status = 'judged' AND decided_at >= %s"
                             " ORDER BY id", (player_id, _quarter_start(conn, first))):
            out.append({"key": f"case:{c['id']}", "kind": "directors", "period": c["opened_period"], "at": c["decided_at"],
                        "loss": c["costs"] + c["damages"], "case_id": c["id"], "opened_at": c["opened_at"],
                        "caused": False, "uninsurable": c["fine"] + c["disgorgement"],
                        "words": (f"Judged in case {c['id']}: {c['words']} The costs and damages are "
                                  f"{money(c['costs'] + c['damages'])}; the fine and disgorgement, "
                                  f"{money(c['fine'] + c['disgorgement'])}, are never insurable.")})
    return out


def _covering(conn: Connection, player_id, kind: str, loss: dict) -> dict | None:
    """The policy in force when the loss happened, with that quarter's premium paid."""
    for p in _rows(conn, "SELECT * FROM insurance_policies WHERE player_id = %s AND kind = %s ORDER BY id DESC",
                   (player_id, kind)):
        if p["paid_through"] < loss["period"] or p["started_period"] > loss["period"]:
            continue
        if p["started_at"] >= loss["at"] or (p["ended_at"] is not None and p["ended_at"] <= loss["at"]):
            continue
        return p
    return None


def _refuse(conn: Connection, player_id, loss: dict, policy: dict, period: int, now: datetime) -> dict:
    """A claim on a loss the claimant caused: refused, the premium kept, and referred to the tribunal."""
    from simulation import courts
    claim = _one(conn, "INSERT INTO insurance_claims (player_id, policy_id, kind, loss_key, loss, decision, reason, period, at)"
                       " VALUES (%s, %s, %s, %s, %s, 'refused', %s, %s, %s) RETURNING id",
                 (player_id, policy["id"], loss["kind"], loss["key"], loss["loss"],
                  "Refused: the loss was the claimant's own doing.", period, now))
    case_id = None
    if courts.ready(conn) and loss["loss"] >= naira(data.COURT_MIN_CLAIM_NAIRA):
        courts.ensure(conn)
        case_id = courts.open_case(
            conn, kind="insurance_fraud", defendant_id=player_id, claimant_id=None, company_id=None, amount=loss["loss"],
            evidence={"key": f"insurance_fraud:{claim['id']}", "total": loss["loss"],
                      "lines": [{"claim": claim["id"], "loss": loss["key"], "words": loss["words"], "at": now.isoformat()}]},
            words=f"Claimed {money(loss['loss'])} on {NAMES[loss['kind']].lower()} cover for a loss of their own making: "
                  f"{loss['words']}", period=period, now=now)
        conn.execute("UPDATE insurance_claims SET case_id = %s WHERE id = %s", (case_id, claim["id"]))
    refusals = _one(conn, "SELECT count(*) AS n FROM insurance_claims WHERE player_id = %s AND decision = 'refused'",
                    (player_id,))["n"]
    ended = False
    if refusals >= data.INSURANCE_REFUSALS_TO_BAR:
        conn.execute("INSERT INTO insurance_bars (player_id, at) VALUES (%s, %s) ON CONFLICT DO NOTHING", (player_id, now))
        for p in _in_force(conn, player_id):
            _end(conn, p["id"], "barred", period, now)
        ended = True
    words = "Refused: the loss was your own doing. The premium is kept and the insurer has referred it to the tribunal."
    if case_id is None:
        words = "Refused: the loss was your own doing. The premium is kept."
    if ended:
        words += " It is the second refusal: all your cover has ended, and no insurer will write for you again."
    return {"claim_id": claim["id"], "decision": "refused", "words": words, "case_id": case_id, "paid": 0}


def _decline(conn: Connection, player_id, loss: dict, policy: dict | None, reason: str, period: int, now: datetime) -> dict:
    claim = _one(conn, "INSERT INTO insurance_claims (player_id, policy_id, kind, loss_key, loss, decision, reason, period, at)"
                       " VALUES (%s, %s, %s, %s, %s, 'declined', %s, %s, %s) RETURNING id",
                 (player_id, policy and policy["id"], loss["kind"], loss["key"], loss["loss"], reason, period, now))
    return {"claim_id": claim["id"], "decision": "declined", "words": reason, "paid": 0}


def _reset_record(conn: Connection, player_id, kind: str, period: int) -> None:
    conn.execute("INSERT INTO insurance_records (player_id, kind, clean_quarters, counted_period) VALUES (%s, %s, 0, %s)"
                 " ON CONFLICT (player_id, kind) DO UPDATE SET clean_quarters = 0, counted_period = EXCLUDED.counted_period",
                 (player_id, kind, period))


def claim(conn: Connection, player_id, key: str, now: datetime) -> dict:
    """Claim against a loss on your record. The insurer reads the same record: who caused the loss, whether cover was in
    force and paid for when it happened, and how much of it the policy answers."""
    with conn.transaction():
        careers.books_open(conn, now)
        conn.execute("SELECT 1 FROM players WHERE id = %s FOR UPDATE", (player_id,))
        found = next((x for x in losses(conn, player_id, now) if x["key"] == key), None)
        if found is None:
            raise InsuranceError("That is not a loss on your record from the last year.")
        if _one(conn, "SELECT 1 AS x FROM insurance_claims WHERE player_id = %s AND loss_key = %s", (player_id, key)):
            raise InsuranceError("That loss has already been claimed. A loss is claimed once.")
        period = careers.world_now(conn, now)["period"]
        kind = found["kind"]
        policy = _covering(conn, player_id, kind, found)
        if policy is None:
            return _decline(conn, player_id, found, None,
                            f"Declined: no {NAMES[kind].lower()} cover was in force and paid for when the loss happened.",
                            period, now)
        if found["caused"]:
            return _refuse(conn, player_id, found, policy, period, now)
        if kind == "property":
            start = _one(conn, "SELECT condition FROM property_results WHERE property_id = %s AND period = %s",
                         (found["property_id"], policy["started_period"] - 1))
            if start and start["condition"] < data.POOR_CONDITION:
                return _decline(conn, player_id, found, policy, "Declined: the building was already run down when the "
                                "cover began, and a wreck is not insured.", period, now)
        if kind == "directors":
            case = _one(conn, "SELECT opened_period, opened_at FROM court_cases WHERE id = %s", (found["case_id"],))
            if (case["opened_period"] < policy["started_period"] + data.INSURANCE_DIRECTORS_WAIT_QUARTERS
                    or case["opened_at"] <= policy["started_at"]):
                return _decline(conn, player_id, found, policy, "Declined: directors' cover answers cases opened two years "
                                "or more after it began, so no wrong done before the cover can be insured.", period, now)
        insured = found["loss"] * data.INSURANCE_INCOME_SHARE_BPS // BPS if kind == "income" else found["loss"]
        over = max(insured - policy["excess"], 0)
        base = min(over, policy["cover"])
        umbrella_policy = _covering(conn, player_id, "umbrella", found) if over > base else None
        topped = min(over - base, umbrella_policy["cover"]) if umbrella_policy else 0
        payable = base + topped
        if payable <= 0:
            return _decline(conn, player_id, found, policy, "Declined: the loss is within your excess.", period, now)
        if kind == "income" and careers.current_job(conn, player_id) is not None:
            return _decline(conn, player_id, found, policy, "Declined: you are back in work, so there is no income to "
                            "replace.", period, now)
        _reset_record(conn, player_id, kind, period)
        if topped:
            _reset_record(conn, player_id, "umbrella", period)
        if kind == "income":
            row = _one(conn, "INSERT INTO insurance_claims (player_id, policy_id, kind, loss_key, loss, excess, payable,"
                             " umbrella, instalments, decision, reason, period, at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s,"
                             " 'paying', %s, %s, %s) RETURNING id",
                       (player_id, policy["id"], kind, key, found["loss"], policy["excess"], payable, topped,
                        data.INSURANCE_INCOME_QUARTERS, "Accepted: paid each quarter while you are out of work.", period, now))
            return {"claim_id": row["id"], "decision": "paying", "payable": payable, "paid": 0,
                    "words": f"Accepted: {money(payable)} in all, paid over the next {data.INSURANCE_INCOME_QUARTERS} "
                             "quarters while you are out of work."}
        account = ledger.player_account_id(conn, player_id)
        paid = ledger.pay_up_to(conn, payer=pool(conn), receiver=account, wanted=payable, kind="insurance_claim",
                                memo=f"{NAMES[kind]} claim: {found['words'][:120]}", period=period)
        short = payable - paid
        reason = "Paid." if not short else f"Paid in part: the policy account held only {money(paid)}."
        row = _one(conn, "INSERT INTO insurance_claims (player_id, policy_id, kind, loss_key, loss, excess, payable, umbrella,"
                         " paid, decision, reason, period, at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'paid', %s, %s, %s)"
                         " RETURNING id",
                   (player_id, policy["id"], kind, key, found["loss"], policy["excess"], payable, topped, paid, reason,
                    period, now))
        if kind == "directors" and paid:
            # What the cover pays goes first to what the tribunal ordered and is still owed.
            from simulation import courts
            courts.pay(conn, found["case_id"], period, now)
        return {"claim_id": row["id"], "decision": "paid", "payable": payable, "paid": paid, "shortfall": short,
                "words": reason}


# ---------------------------------------------------------------------------
# The quarter close
# ---------------------------------------------------------------------------

def close(conn: Connection, period: int, now: datetime) -> dict:
    """The insurer's quarter, run once as the quarter closes: income protection paid to those still out of work, the
    no-claims record aged, and next quarter's premium charged, or the cover lapses."""
    if not ready(conn):
        return {}
    out = {"instalments": 0, "charged": 0, "lapsed": 0}
    if _one(conn, "SELECT 1 AS x FROM insurance_policies LIMIT 1") is None:
        return out                                    # nobody has ever bought cover: the insurers have not opened
    fund = pool(conn)
    for c in _rows(conn, "SELECT * FROM insurance_claims WHERE decision = 'paying' ORDER BY id FOR UPDATE"):
        if careers.current_job(conn, c["player_id"]) is not None:
            conn.execute("UPDATE insurance_claims SET decision = 'paid', payable = paid, instalments = 0,"
                         " reason = 'Stopped: back in work.' WHERE id = %s", (c["id"],))
            continue
        due = (c["payable"] - c["paid"]) // max(c["instalments"], 1)
        account = ledger.player_account_id(conn, c["player_id"])
        got = ledger.pay_up_to(conn, payer=fund, receiver=account, wanted=due, kind="insurance_claim",
                               memo=f"Income protection, {clock.period_label(period)}", period=period) if due > 0 else 0
        left = c["instalments"] - 1
        if left <= 0:
            reason = "Paid in full." if c["paid"] + got >= c["payable"] else "Paid in part: the policy account ran short."
            conn.execute("UPDATE insurance_claims SET paid = paid + %s, instalments = 0, decision = 'paid', payable ="
                         " paid + %s, reason = %s WHERE id = %s", (got, got, reason, c["id"]))
        else:
            # An instalment the pool could not pay is not owed later: the claim promises what the pool holds.
            conn.execute("UPDATE insurance_claims SET paid = paid + %s, instalments = %s, payable = payable - %s"
                         " WHERE id = %s", (got, left, due - got, c["id"]))
        out["instalments"] += got
    for p in _rows(conn, "SELECT * FROM insurance_policies WHERE ended_at IS NULL ORDER BY id FOR UPDATE"):
        # A quarter paid for and closed with no claim is a clean quarter on the record.
        if p["paid_through"] >= period:
            conn.execute("INSERT INTO insurance_records (player_id, kind, clean_quarters, counted_period) VALUES (%s, %s, 1, %s)"
                         " ON CONFLICT (player_id, kind) DO UPDATE SET clean_quarters = insurance_records.clean_quarters + 1,"
                         " counted_period = EXCLUDED.counted_period WHERE insurance_records.counted_period < EXCLUDED.counted_period",
                         (p["player_id"], p["kind"], period))
    nxt = period + 1
    for p in _rows(conn, "SELECT * FROM insurance_policies WHERE ended_at IS NULL ORDER BY kind = 'umbrella', id"):
        most = most_cover(conn, p["player_id"], p["kind"], now)
        if most <= 0:
            _end(conn, p["id"], "lapsed", nxt, now)
            out["lapsed"] += 1
            continue
        cover = min(p["cover"], most)
        excess = min(p["excess"], cover - 1)
        priced = quote(conn, p["player_id"], p["kind"], cover, excess, now, period=nxt)
        account = ledger.player_account_id(conn, p["player_id"])
        if account is None or ledger.balance(conn, account) < priced["premium"]:
            _end(conn, p["id"], "lapsed", nxt, now)
            out["lapsed"] += 1
            continue
        ledger.transfer(conn, payer=account, receiver=fund, amount=priced["premium"], kind="insurance_premium",
                        memo=f"{NAMES[p['kind']]} cover, the premium for {clock.period_label(nxt)}", period=period)
        conn.execute("UPDATE insurance_policies SET cover = %s, excess = %s, premium = %s, paid_through = %s WHERE id = %s",
                     (cover, excess, priced["premium"], nxt, p["id"]))
        out["charged"] += priced["premium"]
    return out


def check_books(conn: Connection) -> list[str]:
    """The policy account holds exactly its capital and the premiums taken in, less the claims paid out."""
    if not ready(conn):
        return []
    row = _one(conn, "SELECT id FROM ledger_accounts WHERE code = %s", (POOL,))
    if row is None:
        return []
    flows = _one(conn, """
        SELECT coalesce(sum(CASE WHEN t.kind = 'insurance_premium' THEN l.amount ELSE 0 END), 0) AS premiums,
               coalesce(sum(CASE WHEN t.kind = 'insurance_claim' THEN -l.amount ELSE 0 END), 0) AS claims,
               coalesce(sum(CASE WHEN t.kind = 'insurance_capital' THEN l.amount ELSE 0 END), 0) AS capital,
               coalesce(sum(CASE WHEN t.kind NOT IN ('insurance_premium', 'insurance_claim', 'insurance_capital')
                                 THEN 1 ELSE 0 END), 0) AS other
        FROM ledger_entries l JOIN ledger_transactions t ON t.id = l.transaction_id
        WHERE l.account_id = %s AND l.asset = 'NGN'
    """, (row["id"],))
    problems = []
    if flows["other"]:
        problems.append("The insurers' policy account moved money that was not its capital, a premium or a claim.")
    paid = _one(conn, "SELECT coalesce(sum(paid), 0) AS p FROM insurance_claims")["p"]
    if paid != flows["claims"]:
        problems.append(f"Insurance claims record {money(paid)} paid, but the policy account paid out {money(flows['claims'])}.")
    if ledger.balance(conn, row["id"]) != flows["capital"] + flows["premiums"] - flows["claims"]:
        problems.append("The insurers' policy account does not hold its capital and premiums less its claims.")
    return problems


# ---------------------------------------------------------------------------
# The page
# ---------------------------------------------------------------------------

WORDS = {
    "property": "Pays the repair of wear on the buildings you own, less your excess. Wear on a building whose upkeep was "
                "not kept is your own doing and is not covered, and a building already run down when the cover begins is "
                "not insured.",
    "directors": "Pays the costs and damages the tribunal orders against you. Never the disgorgement or the fine. It "
                 "answers cases opened two years or more after the cover began.",
    "income": "Pays half your last salary each quarter, for up to a year, after a dismissal, while you are out of work. "
              "In this game a player is only dismissed by the newsroom, so it rarely pays. Resigning is not covered.",
    "umbrella": "Tops up your other cover: when a loss is larger than the policy that answers it, the umbrella pays the "
                "rest, up to its own cover.",
}
HONEST = ("A premium is the expected loss plus a loading, so on average insurance loses you money. What it buys is "
          "certainty, and a cheaper personal loan. The policy account pays only what it holds.")


def _pool_balance(conn: Connection) -> int:
    row = _one(conn, "SELECT id FROM ledger_accounts WHERE code = %s", (POOL,))
    return ledger.balance(conn, row["id"]) if row else 0


def view(conn: Connection, player_id, now: datetime) -> dict:
    if not ready(conn):
        return {"ready": False}
    period = careers.world_now(conn, now)["period"]
    account = ledger.player_account_id(conn, player_id)
    held = {p["kind"]: p for p in _in_force(conn, player_id)}
    claimed = {c["loss_key"]: c for c in _rows(conn, "SELECT * FROM insurance_claims WHERE player_id = %s", (player_id,))}
    policies = []
    for kind in KINDS:
        most = most_cover(conn, player_id, kind, now)
        p = held.get(kind)
        policies.append({
            "kind": kind, "name": NAMES[kind], "words": WORDS[kind], "most_cover": most,
            "no_claims_bps": no_claims_bps(conn, player_id, kind),
            "clean_quarters": _record(conn, player_id, kind)["clean_quarters"],
            "quote": quote(conn, player_id, kind, most, 0, now, period=period) if most > 0 else None,
            "held": None if p is None else {"cover": p["cover"], "excess": p["excess"], "premium": p["premium"],
                                            "since": clock.period_label(p["started_period"]),
                                            "paid_through": clock.period_label(p["paid_through"])},
        })
    debt = _debts(conn, account) if account else 0
    record = []
    for x in losses(conn, player_id, now):
        c = claimed.get(x["key"])
        record.append({"key": x["key"], "kind": x["kind"], "name": NAMES[x["kind"]], "words": x["words"], "loss": x["loss"],
                       "quarter": clock.period_label(x["period"]),
                       "claim": None if c is None else {"decision": c["decision"], "reason": c["reason"],
                                                         "payable": c["payable"], "paid": c["paid"]}})
    history = [{"kind": c["kind"], "name": NAMES[c["kind"]], "decision": c["decision"], "reason": c["reason"],
                "loss": c["loss"], "payable": c["payable"], "paid": c["paid"], "case_id": c["case_id"],
                "quarter": clock.period_label(c["period"])}
               for c in _rows(conn, "SELECT * FROM insurance_claims WHERE player_id = %s ORDER BY id DESC LIMIT 20",
                              (player_id,))]
    return {
        "ready": True, "period": clock.period_label(period), "policies": policies, "losses": record, "claims": history,
        "barred": barred(conn, player_id), "honest": HONEST,
        "refusals": _one(conn, "SELECT count(*) AS n FROM insurance_claims WHERE player_id = %s AND decision = 'refused'",
                         (player_id,))["n"],
        "borrowing": {"debt": debt, "cover": lender_cover(conn, player_id),
                      "spread_uninsured_bps": data.PERSONAL_LOAN_SPREAD_BPS,
                      "spread_bps": personal_spread_bps(conn, player_id),
                      "step_bps": data.INSURED_SPREAD_STEP_BPS},
        "pool": _pool_balance(conn),
    }
