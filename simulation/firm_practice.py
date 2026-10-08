"""Private equity stage, part 2B: firms players found, and the work they do for others.

  firms          an Accountant may found an audit firm, a Risk Manager a risk consultancy, an Investment
                 Banker an advisory firm, an Asset Manager a small bank (with capital of their own).
                 The founder runs it from their seat in an empire: of every fee, 60% goes to that empire
                 and 40% to the founder (all of it to the founder without a seat)
  outside work   an empire sends one of its checks on a deal to a firm of the right kind, for a fee
  audits         the founders have a company they are selling audited; the auditor checks the accounts
                 against the bank, visits the sites, and signs clean or refuses to sign. Buyers see it.
                 An empire may have a company it owns audited too: an audit finds money taken from it
  mandates       an advisory firm runs a sale: its pitch book, if well made, lifts the bids; it is paid
                 a success fee when the company is sold
  underwriting   a small bank stands behind a listing and buys the shares the public does not
  restructuring  an advisory firm's plan puts a failing company's bank loans on terms it can bear;
                 paid only if it works
  bank loans     a small bank lends to empires from its capital

A firm's reputation rises with good work and falls with bad; buyers and clients see it.
"""

from __future__ import annotations

from datetime import datetime

from psycopg import Connection
from psycopg.types.json import Jsonb

from simulation import careers, empires, firm, firm_clients, firm_deals, ledger, private
from simulation import firm_duties as fd
from simulation.empires import EmpireError, _log, _money, _one, _open, _rows, _text
from simulation.money import BPS, apply_bps, million_naira

KINDS = {   # kind -> (build that may found it, what it is called, what it does)
    "audit": ("accountant", "Audit firm", "Audits companies before a sale, and checks the accounts on a deal."),
    "risk": ("risk_manager", "Risk consultancy", "Stress-tests and inspects companies on a deal."),
    "advisory": ("investment_banker", "Advisory firm", "Runs sales, values companies, writes fairness opinions, restructures debts."),
    "bank": ("asset_manager", "Small bank", "Lends to empires from its capital, and underwrites listings."),
}
STEP_FIRMS = {"accounts": "audit", "stress": "risk", "valuation": "advisory", "fairness": "advisory"}
BANK_CAPITAL_LEAST = million_naira(50)
JOB_FEE_LEAST, JOB_FEE_MOST = million_naira(1), million_naira(500)
CHECK_FEE_BPS = 50                  # a check on a deal costs at most 0.5% of the asking price (and at most the fee most)
AUDIT_SALES_BPS = 100               # an audit of an owned company costs at most 1% of a quarter's sales, once a quarter
LOAN_RATE_ABOVE_MOST = 1500         # a small bank lends at no more than 15 points above the Central Bank's rate
AUDIT_FEE_BPS = 20                  # the founders pay an audit 0.2% of the asking price...
AUDIT_FEE_RANGE = (million_naira(2), million_naira(50))
MANDATE_FEE_BPS = 100               # an advisory firm's success fee: 1% of the price
MANDATE_ABOVE = million_naira(20_000)   # the founders hire an adviser for a sale asking more than this
PITCH_LIFT_BPS = 300                # a well-made pitch book lifts the computer-run bids by 3%
UNDERWRITING_FEE_BPS = 200
RESTRUCTURE_RATE_CUT_BPS = 300
RESTRUCTURE_QUARTERS = 8
REPUTATION_GOOD, REPUTATION_BAD, REPUTATION_MISSED = 1, -3, -15


# ---------------------------------------------------------------------------
# Founding a firm
# ---------------------------------------------------------------------------

def found(conn: Connection, player_id, kind: str, name: str, capital: int, now: datetime) -> dict:
    """Found a firm. Its founder must hold a seat in an empire run by players, and have the build its kind needs."""
    with conn.transaction():
        state = _open(conn, now)
        if kind not in KINDS:
            raise EmpireError("Choose the kind of firm.")
        seat = empires.seat_of(conn, player_id)
        if seat is None or seat["empire_status"] != "active" or seat["empire_kind"] != "player":
            raise EmpireError("A firm is run from a seat in an empire run by players. Take one first.")
        build = KINDS[kind][0]
        if seat["build"] != build:
            raise EmpireError(f"A {KINDS[kind][1].lower()} is founded by {careers._a(empires.BUILD_NAMES[build])}.")
        name = _text(name or "")
        if not 3 <= len(name) <= 60:
            raise EmpireError("A firm's name is 3 to 60 characters.")
        if kind == "bank":
            if not isinstance(capital, int) or isinstance(capital, bool) or capital < BANK_CAPITAL_LEAST:
                raise EmpireError(f"A small bank needs at least {_money(BANK_CAPITAL_LEAST)} of its founder's own money as capital.")
        else:
            capital = 0
        if _one(conn, "SELECT 1 FROM pro_firms WHERE name = %s OR (founder_id = %s AND status = 'open')", (name, player_id)):
            raise EmpireError("That name is taken, or you already run a firm.")
        account = ledger.create_account(conn, kind="firm", name=name)
        made = _one(conn, "INSERT INTO pro_firms (kind, name, founder_id, account_id, capital, founded_period, at) VALUES (%s, %s, %s, %s, %s, %s, %s)"
                          " RETURNING *", (kind, name, player_id, account, capital, state["period"], now))
        if capital:
            try:
                ledger.transfer(conn, payer=ledger.player_account_id(conn, player_id), receiver=account, amount=capital, kind="firm_capital",
                                memo=f"{name}: its founder's capital", period=state["period"], reference=f"firm:{made['id']}")
            except ledger.InsufficientFunds:
                raise EmpireError(f"You have not {_money(capital)} in cash.") from None
        careers._event(conn, player_id, build, "firm", f"Founded {name}, {careers._a(KINDS[kind][1].lower())}.", now)
        _log(conn, seat["empire_id"], f"{firm._name(conn, player_id)} founded {name}, {careers._a(KINDS[kind][1].lower())}, run from the empire's desk.", now)
        return {"firm_id": made["id"]}


def _firm(conn: Connection, firm_id, *, lock: bool = False) -> dict:
    f = _one(conn, "SELECT * FROM pro_firms WHERE id = %s" + (" FOR UPDATE" if lock else ""), (firm_id,))
    if f is None or f["status"] != "open":
        raise EmpireError("There is no such firm open.")
    return f


def _mine(conn: Connection, player_id) -> dict:
    f = _one(conn, "SELECT * FROM pro_firms WHERE founder_id = %s AND status = 'open' FOR UPDATE", (player_id,))
    if f is None:
        raise EmpireError("You do not run a firm.")
    seat = empires.seat_of(conn, player_id)
    if seat is None or seat["empire_status"] != "active":
        raise EmpireError("A firm is run from a seat in an empire. Without one, its work waits.")
    return f


def _split_fee(conn: Connection, f: dict, payer, fee: int, memo: str, period: int, reference: str) -> int:
    """Pay a firm's fee: 60% to the empire its founder sits in, 40% to the founder; all to the founder without a seat.
    Returns what was paid."""
    if fee <= 0:
        return 0
    seat = empires.seat_of(conn, f["founder_id"])
    to_empire = apply_bps(fee, firm_clients.EMPIRE_SHARE_BPS) if seat and seat["empire_status"] == "active" else 0
    amounts = {ledger.player_account_id(conn, f["founder_id"]): fee - to_empire}
    if to_empire:
        amounts[seat["account_id"]] = to_empire
    return ledger.pay_split_up_to(conn, payer=payer, amounts=amounts, kind="professional_fee", memo=memo, period=period, reference=reference)


def _reputation(conn: Connection, firm_id, change: int) -> None:
    conn.execute("UPDATE pro_firms SET reputation = least(greatest(reputation + %s, 0), 100) WHERE id = %s", (change, firm_id))


def firms(conn: Connection, kind: str | None = None) -> list[dict]:
    """The open firms, with their reputation: a public list. Founders are shown by display name."""
    return [{"id": r["id"], "kind": r["kind"], "kind_name": KINDS[r["kind"]][1], "name": r["name"], "founder": r["founder"],
             "reputation": r["reputation"], "jobs_done": r["jobs_done"]}
            for r in _rows(conn, "SELECT f.*, p.display_name AS founder FROM pro_firms f JOIN players p ON p.id = f.founder_id"
                                 " WHERE f.status = 'open'" + (" AND f.kind = %s" if kind else "") + " ORDER BY f.reputation DESC, f.id",
                           (kind,) if kind else ())]


# ---------------------------------------------------------------------------
# Outside work on a deal
# ---------------------------------------------------------------------------

def send_step(conn: Connection, head_id, step_id: int, firm_id: int, fee: int, now: datetime) -> dict:
    """The head sends one of the checks on a deal to an outside firm of the right kind, for a fee paid when it is handed in."""
    with conn.transaction():
        state = _open(conn, now)
        empire = empires._head(conn, head_id)
        step = _one(conn, "SELECT s.*, f.empire_id, f.nda_at, f.status AS file_status FROM deal_steps s JOIN deal_files f ON f.id = s.file_id"
                          " WHERE s.id = %s AND f.empire_id = %s FOR UPDATE OF s", (step_id, empire["id"]))
        if step is None or step["status"] != "due" or step["terms"] is not None or step["firm_id"]:
            raise EmpireError("That check is done, already open, or already sent out.")
        if step["file_status"] != "open" or not step["nda_at"]:
            raise EmpireError("A check is sent out only from an open file, once the confidentiality agreement is signed.")
        f = _firm(conn, firm_id)
        if STEP_FIRMS.get(step["step"]) != f["kind"]:
            raise EmpireError("That check is not the work of that kind of firm.")
        if empires.seat_of(conn, f["founder_id"]) and empires.seat_of(conn, f["founder_id"])["empire_id"] == empire["id"]:
            raise EmpireError("A firm run from your own empire is not an outside firm: its founder does the check at their desk.")
        sale = _one(conn, "SELECT p.* FROM sale_processes p JOIN deal_files f ON f.process_id = p.id WHERE f.id = %s", (step["file_id"],))
        most = max(min(apply_bps(sale["asking"], CHECK_FEE_BPS), JOB_FEE_MOST), JOB_FEE_LEAST)
        if not isinstance(fee, int) or isinstance(fee, bool) or not JOB_FEE_LEAST <= fee <= most:
            raise EmpireError(f"A fee from {_money(JOB_FEE_LEAST)} to {_money(most)} (half a percent of the asking price at most).")
        job = _one(conn, "INSERT INTO firm_jobs (firm_id, kind, client_account, client_empire_id, company_id, process_id, step_id, fee, period, at)"
                         " VALUES (%s, 'deal_check', %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
                   (f["id"], empire["account_id"], empire["id"], sale["company_id"], sale["id"], step_id, fee, state["period"], now))
        conn.execute("UPDATE deal_steps SET firm_id = %s WHERE id = %s", (f["id"], step_id))
        _log(conn, empire["id"], f"The check \"{firm_deals.STEPS[step['step']][1].lower()}\" was sent to {f['name']} for a fee of {_money(fee)}.", now)
        return {"job_id": job["id"]}


def _job(conn: Connection, player_id, job_id: int) -> tuple[dict, dict]:
    f = _mine(conn, player_id)
    job = _one(conn, "SELECT * FROM firm_jobs WHERE id = %s AND firm_id = %s FOR UPDATE", (job_id, f["id"]))
    if job is None or job["status"] != "open":
        raise EmpireError("Your firm has no such job waiting.")
    if job["words"] == AWAITING_OWNER:
        raise EmpireError("The company's owners have not accepted your offer yet.")
    if job["process_id"]:
        sale = _one(conn, "SELECT status FROM sale_processes WHERE id = %s", (job["process_id"],))
        if sale["status"] != "open" and job["kind"] in ("deal_check", "audit", "mandate"):
            raise EmpireError("That sale is over.")
    return f, job


def open_job(conn: Connection, player_id, job_id: int, now: datetime) -> dict:
    """The founder opens a job. What it asks is fixed from the figures of this moment."""
    with conn.transaction():
        state = _open(conn, now)
        f, job = _job(conn, player_id, job_id)
        if job["terms"] is None:
            terms = _prepare(conn, job, state["period"])
            conn.execute("UPDATE firm_jobs SET terms = %s WHERE id = %s", (Jsonb(terms), job_id))
            job = {**job, "terms": terms}
        return {"id": job_id, "terms": firm._public_terms(job["terms"])}


def _prepare(conn: Connection, job: dict, period: int) -> dict:
    if job["kind"] == "deal_check":
        step = _one(conn, "SELECT * FROM deal_steps WHERE id = %s", (job["step_id"],))
        sale = firm_deals._process(conn, job["process_id"])
        return firm_deals._prepare(conn, step["step"], sale, job["client_empire_id"])
    if job["kind"] == "audit":
        return _audit_terms(conn, job)
    if job["kind"] == "mandate":
        return _pitch_terms(conn, job)
    if job["kind"] == "restructuring":
        return _restructure_terms(conn, job)
    raise EmpireError("That job has nothing to work out.")


def hand_in_job(conn: Connection, player_id, job_id: int, answers: dict, now: datetime) -> dict:
    """The founder hands in a job. It is marked against the truth; the work takes effect and the client pays."""
    with conn.transaction():
        state = _open(conn, now)
        f, job = _job(conn, player_id, job_id)
        if job["terms"] is None:
            raise EmpireError("Open the job first.")
        if not isinstance(answers, dict):
            raise EmpireError("The answers did not arrive in a form that can be read.")
        result = fd.mark({"conn": conn}, job["terms"], answers)
        score = max(0, min(100, int(result["score"])))
        well = score >= firm.DUTY_PASS
        result = {**result, "lines": [{"label": line["label"], "right": line["right"]} for line in result["lines"]], "words": ""}
        words, opinion = "", None
        if job["kind"] == "deal_check":
            words = _finish_check(conn, f, job, score, well, answers, now, state["period"])
        elif job["kind"] == "audit":
            opinion = answers.get("opinion") if answers.get("opinion") in ("clean", "refused") else "clean"
            well = well and opinion == job["terms"]["_truth"]["opinion"]          # an audit with the wrong opinion is not good work, whatever the sums
            words = _finish_audit(conn, f, job, opinion, well, now, state["period"])
        elif job["kind"] == "mandate":
            words = _finish_pitch(conn, f, job, well, now)
        elif job["kind"] == "restructuring":
            words = _finish_restructuring(conn, f, job, well, now, state["period"])
        conn.execute("UPDATE firm_jobs SET answers = %s, score = %s, opinion = %s, words = %s, status = 'done', done_at = %s WHERE id = %s",
                     (Jsonb(answers), score, opinion, words[:600], now, job_id))
        paid_work = job["fee"] > 0
        if paid_work:
            # Work done for nothing earns no name and teaches nothing: reputation cannot be farmed with free jobs.
            conn.execute("UPDATE pro_firms SET jobs_done = jobs_done + 1 WHERE id = %s", (f["id"],))
            _reputation(conn, f["id"], REPUTATION_GOOD if well else REPUTATION_BAD)
        elif not well:
            _reputation(conn, f["id"], REPUTATION_BAD)
        build = KINDS[f["kind"]][0]
        mine = careers.career(conn, player_id, build)
        gained = firm.DUTY_EXPERIENCE * score // 100 * (1 + (mine["rank"] if mine else 0)) if paid_work else 0
        if gained and mine:
            careers.add_experience(conn, player_id, build, gained, now)
        return {"score": score, "result": result, "words": words}


def _finish_check(conn: Connection, f: dict, job: dict, score: int, well: bool, answers: dict, now: datetime, period: int) -> str:
    empire = empires._empire(conn, job["client_empire_id"])
    step = _one(conn, "SELECT * FROM deal_steps WHERE id = %s FOR UPDATE", (job["step_id"],))
    found = _one(conn, "SELECT * FROM deal_files WHERE id = %s", (step["file_id"],))
    sale = firm_deals._process(conn, job["process_id"])
    words = firm_deals._finish_step(conn, empire, found, sale, step, well, now)
    conn.execute("UPDATE deal_steps SET status = 'done', score = %s, done_by = %s, answers = %s, found = %s, done_at = %s, terms = %s WHERE id = %s",
                 (score, f["founder_id"], Jsonb(answers), Jsonb(words), now, Jsonb(job["terms"]), step["id"]))
    if step["step"] == "valuation" and isinstance(answers.get("value"), int):
        conn.execute("UPDATE deal_files SET valuation = %s WHERE id = %s", (answers["value"], found["id"]))
    firm.sign_opinion(conn, f["founder_id"], KINDS[f["kind"]][0], empire["id"], f"deal_{step['step']}",
                      f"{firm_deals.STEPS[step['step']][1]} for {empire['name']}: {sale['company']}",
                      {"file_id": found["id"], "score": score, "found": words}, period, period + 4, now)
    # The fee is paid for a check done well; a check that does not hold up earns nothing.
    paid = _split_fee(conn, f, empire["account_id"], job["fee"], f"{empire['name']}: {f['name']}'s fee for a check on a deal", period,
                      f"job:{job['id']}") if well else 0
    if paid:
        empires._book(conn, empire["id"], period, "Professional fees", f"{f['name']}: a check on a deal", paid, True, now, kind="fee", desk="head")
    _log(conn, empire["id"], f"{f['name']} handed in the check \"{firm_deals.STEPS[step['step']][1].lower()}\" on {sale['company']}.", now)
    return " ".join(words)


# ---------------------------------------------------------------------------
# Audits: before a sale, and of a company an empire owns
# ---------------------------------------------------------------------------

def appoint_auditor(conn: Connection, sale: dict, period: int, now: datetime) -> int | None:
    """When the founders put a company up for sale, they have it audited, if there is an audit firm to do it:
    the one with the best reputation. They pay its fee when the audit is handed in."""
    f = _one(conn, "SELECT * FROM pro_firms WHERE kind = 'audit' AND status = 'open' ORDER BY reputation DESC, id LIMIT 1")
    if f is None:
        return None
    fee = min(max(apply_bps(sale["asking"], AUDIT_FEE_BPS), AUDIT_FEE_RANGE[0]), AUDIT_FEE_RANGE[1])
    return _one(conn, "INSERT INTO firm_jobs (firm_id, kind, client_account, company_id, process_id, fee, period, at)"
                      " VALUES (%s, 'audit', %s, %s, %s, %s, %s, %s) RETURNING id",
                (f["id"], sale["seller_account"], sale["company_id"], sale["id"], fee, period, now))["id"]


def commission_audit(conn: Connection, head_id, company_id, firm_id: int, fee: int, now: datetime) -> dict:
    """The head has a company the empire controls audited by an audit firm, for a fee the company pays."""
    with conn.transaction():
        state = _open(conn, now)
        empire = empires._head(conn, head_id)
        owned = _one(conn, "SELECT * FROM owned_companies WHERE company_id = %s AND empire_id = %s", (company_id, empire["id"]))
        if owned is None:
            raise EmpireError("Your empire does not control that company.")
        f = _firm(conn, firm_id)
        if f["kind"] != "audit":
            raise EmpireError("An audit is done by an audit firm.")
        seat = empires.seat_of(conn, f["founder_id"])
        if seat and seat["empire_id"] == empire["id"]:
            raise EmpireError("An auditor must be independent: not from the empire that owns the company.")
        from simulation import firm_owned
        most = max(min(apply_bps(firm_owned._quarter_sales(conn, company_id), AUDIT_SALES_BPS), JOB_FEE_MOST), JOB_FEE_LEAST)
        if not isinstance(fee, int) or isinstance(fee, bool) or not JOB_FEE_LEAST <= fee <= most:
            raise EmpireError(f"A fee from {_money(JOB_FEE_LEAST)} to {_money(most)} (1% of a quarter's sales at most).")
        if _one(conn, "SELECT 1 FROM firm_jobs WHERE company_id = %s AND kind = 'audit' AND (status = 'open' OR period = %s)",
                (company_id, state["period"])):
            raise EmpireError("An audit of that company is already under way, or was done this quarter.")
        company = _one(conn, "SELECT * FROM companies WHERE id = %s", (company_id,))
        job = _one(conn, "INSERT INTO firm_jobs (firm_id, kind, client_account, client_empire_id, company_id, fee, period, at)"
                         " VALUES (%s, 'audit', %s, %s, %s, %s, %s, %s) RETURNING id",
                   (f["id"], company["account_id"], empire["id"], company_id, fee, state["period"], now))
        _log(conn, empire["id"], f"The head had {f['name']} audit {company['name']}, for a fee of {_money(fee)} paid by the company.", now)
        return {"job_id": job["id"]}


def _taken_from(conn: Connection, empire_id, company_id) -> list[dict]:
    """Money members took out of a company the empire owns, written in its books as consulting fees (still unfound)."""
    return _rows(conn, "SELECT * FROM empire_books WHERE empire_id = %s AND NOT genuine AND NOT found AND company_id = %s ORDER BY id",
                 (empire_id, company_id))


def _audit_terms(conn: Connection, job: dict) -> dict:
    company_id = job["company_id"]
    papers = private.papers(conn, company_id)
    bank = private.bank_receipts(conn, company_id)
    if not papers:
        raise EmpireError("The company has no accounts yet to audit.")
    shown, received = sum(p["revenue"] for p in papers), sum(b["total"] for b in bank)
    gap = (shown - received) * BPS // max(received, 1)
    register = private.asset_register(conn, company_id, true=False)
    old = sum(1 for a in register if a["age_quarters"] * BPS >= a["life_quarters"] * 6000)
    share = old * BPS // max(len(register), 1)
    owner = private.controller(conn, company_id)
    account = _one(conn, "SELECT account_id FROM companies WHERE id = %s", (company_id,))["account_id"]
    # Every fee the company paid to a person in the last year, and to whom: the auditor sets the names against its owners' people.
    paid_to = _rows(conn, "SELECT coalesce(p.display_name, a.name) AS name, sum(e.amount)::bigint AS amount FROM ledger_transactions t"
                          " JOIN ledger_entries o ON o.transaction_id = t.id AND o.account_id = %s AND o.amount < 0"
                          " JOIN ledger_entries e ON e.transaction_id = t.id AND e.amount > 0 AND e.asset = 'NGN'"
                          " JOIN ledger_accounts a ON a.id = e.account_id LEFT JOIN players p ON p.id = a.player_id"
                          " WHERE t.kind = 'professional_fee' AND a.kind = 'player' AND t.period > %s"
                          " GROUP BY 1 ORDER BY 1", (account, (job["period"] or 0) - 4))
    insiders = [h["display_name"] for h in empires.humans(conn, owner["empire_id"])] if owner else []
    taken = sum(r["amount"] for r in paid_to if r["name"] in insiders)
    p = private.profile(conn, company_id)
    problem = any(s["code"] in ("dressed_revenue", "worn_assets") and not s["done"] for s in (p["secrets"] if p else [])) and not owner
    return fd.terms(
        "Audit the company. Set the sales in its accounts against what the bank says customers paid; visit its sites and count "
        "the assets past three-fifths of their working life; add up what it paid as consulting fees to people inside its owners. "
        "Then sign the accounts clean, or refuse to sign. Buyers and owners will read your opinion.",
        [*[fd.fact(f"Accounts say, {x['label']}", x["revenue"]) for x in papers], *[fd.fact(f"Bank received, {b['label']}", b["total"]) for b in bank],
         *[fd.fact(f"{a['name']}: age / life (quarters)", f"{a['age_quarters']} / {a['life_quarters']}", "text") for a in register],
         *[fd.fact(f"Fees paid to {r['name']}", r["amount"]) for r in paid_to],
         fd.fact("People of the empire that owns it", ", ".join(insiders) or "None: the founders own it", "text")],
        [fd.q_percent("gap", "How far the accounts are above the bank's figure (%)"),
         fd.q_percent("old", "Share of assets past three-fifths of their life (%)"),
         fd.q_number("consulting", "Fees paid to people of the empire that owns it (₦)"),
         fd.q_choice("opinion", "Your opinion", ["clean", "refused"])],
        {"gap": gap, "old": share, "consulting": taken, "opinion": "refused" if problem or taken > 0 else "clean"},
        method="The accounts are not true if the sales are above the bank's figure or money left as fees to insiders: refuse to sign.")


def _finish_audit(conn: Connection, f: dict, job: dict, opinion: str, well: bool, now: datetime, period: int) -> str:
    company = _one(conn, "SELECT * FROM companies WHERE id = %s", (job["company_id"],))
    truth = job["terms"]["_truth"]
    right = opinion == truth["opinion"]
    words = (f"{f['name']} signed the accounts of {company['name']} clean." if opinion == "clean"
             else f"{f['name']} refused to sign the accounts of {company['name']}.")
    paid = _split_fee(conn, f, job["client_account"], job["fee"], f"{company['name']}: {f['name']}'s audit fee", period,
                      f"job:{job['id']}") if well else 0
    owner = private.controller(conn, company["id"])
    if owner and well and truth["consulting"] > 0:
        # A good audit finds the money members took out of the company as consulting fees: the empire's case follows.
        empire = empires._empire(conn, owner["empire_id"])
        audit = _one(conn, "INSERT INTO empire_audits (empire_id, kind, period, from_period, to_period, fee, at)"
                           " VALUES (%s, 'firm', %s, %s, %s, %s, %s) RETURNING id", (empire["id"], period, period - 4, period, paid, now))["id"]
        for book in _taken_from(conn, empire["id"], company["id"]):
            empires._prove(conn, empire, book, audit, now)
        words += " The auditor found money taken out of the company by insiders."
    if not right:
        _reputation(conn, f["id"], REPUTATION_MISSED if opinion == "clean" else REPUTATION_BAD)
    firm.sign_opinion(conn, f["founder_id"], "accountant", owner["empire_id"] if owner else None, "audit_opinion",
                      f"Audit of {company['name']}: {opinion}", {"job_id": job["id"], "opinion": opinion}, period, None, now)
    opinion_id = _one(conn, "SELECT id FROM signed_opinions WHERE player_id = %s ORDER BY id DESC LIMIT 1", (f["founder_id"],))["id"]
    firm.settle_opinion(conn, opinion_id, "right" if right else "wrong",
                        "The opinion matched the books." if right else "The opinion did not match what the books held.", now)
    if owner:
        _log(conn, owner["empire_id"], words, now)
    return words


def audit_opinion(conn: Connection, process_id) -> dict | None:
    """What buyers see of the audit of a company on sale."""
    job = _one(conn, "SELECT j.*, f.name AS firm, f.reputation FROM firm_jobs j JOIN pro_firms f ON f.id = j.firm_id WHERE j.process_id = %s"
                     " AND j.kind = 'audit' ORDER BY j.id DESC LIMIT 1", (process_id,))
    if job is None:
        return None
    return {"firm": job["firm"], "reputation": job["reputation"], "status": job["status"], "opinion": job["opinion"]}


# ---------------------------------------------------------------------------
# Mandates: an advisory firm runs a sale
# ---------------------------------------------------------------------------

def appoint_adviser(conn: Connection, sale: dict, period: int, now: datetime, firm_id=None) -> int | None:
    """An advisory firm is hired to run a sale: by a selling empire's head (who names it), or by the founders for a large sale."""
    if not firm_id and sale["seller_empire_id"]:
        return None                       # a selling empire chooses its own adviser, or none
    f = (_firm(conn, firm_id) if firm_id else
         _one(conn, "SELECT * FROM pro_firms WHERE kind = 'advisory' AND status = 'open' ORDER BY reputation DESC, id LIMIT 1"))
    if f is None or (not firm_id and sale["asking"] < MANDATE_ABOVE):
        return None
    if f["kind"] != "advisory":
        raise EmpireError("A sale is run by an advisory firm.")
    seat = empires.seat_of(conn, f["founder_id"])
    if firm_id and seat and sale["seller_empire_id"] and seat["empire_id"] == sale["seller_empire_id"]:
        raise EmpireError("An advisory firm run from your own empire is not independent: name another.")
    conn.execute("UPDATE sale_processes SET adviser_firm_id = %s WHERE id = %s", (f["id"], sale["id"]))
    return _one(conn, "INSERT INTO firm_jobs (firm_id, kind, client_account, client_empire_id, company_id, process_id, fee, period, at)"
                      " VALUES (%s, 'mandate', %s, %s, %s, %s, %s, %s, %s) RETURNING id",
                (f["id"], sale["seller_account"], sale["seller_empire_id"], sale["company_id"], sale["id"], MANDATE_FEE_BPS, period, now))["id"]


def industry_multiple(conn: Connection, sector: str, leave_out=None) -> int:
    """What listed companies in an industry are worth for each naira of a year's profit, in hundredths (8 times if none can tell)."""
    listed = _one(conn, "SELECT avg(v.value_per_share::numeric * r.shares_in_issue / nullif(r.net_profit * 4, 0)) AS pe FROM companies c"
                        " JOIN LATERAL (SELECT * FROM company_valuations WHERE company_id = c.id ORDER BY period DESC LIMIT 1) v ON true"
                        " JOIN LATERAL (SELECT * FROM company_results WHERE company_id = c.id ORDER BY period DESC LIMIT 1) r ON true"
                        " WHERE c.listed AND c.sector = %s AND r.net_profit > 0 AND c.id IS DISTINCT FROM %s", (sector, leave_out))
    return min(max(int((listed["pe"] or 8) * 100), 200), 4000) if listed else 800


def _pitch_terms(conn: Connection, job: dict) -> dict:
    sale = firm_deals._process(conn, job["process_id"])
    year = private.papers(conn, job["company_id"])[-4:]
    profit = sum(p["net_profit"] for p in year) * 4 // max(len(year), 1)
    multiple = industry_multiple(conn, sale["sector"])
    value = max(profit, 0) * multiple // 100
    return fd.terms(
        "Write the pitch book for the sale: value the company the way buyers will, by what listed companies in its industry are "
        "worth for each naira of yearly profit. A pitch book that holds up brings better bids.",
        [fd.fact("Profit a year, from the accounts", profit), fd.fact("Listed rivals are worth, for each naira of yearly profit",
                                                                     f"{multiple / 100:.2f} times", "text"), fd.fact("Asking price", sale["asking"])],
        [fd.q_number("value", "What the company is worth on that measure (₦)")], {"value": value},
        method="yearly profit × the industry's multiple")


def _finish_pitch(conn: Connection, f: dict, job: dict, well: bool, now: datetime) -> str:
    if well:
        conn.execute("UPDATE sale_processes SET pitch_bps = %s WHERE id = %s", (PITCH_LIFT_BPS, job["process_id"]))
    return "The pitch book holds up: bidders will pay a little more." if well else "The pitch book does not hold up; it changes nothing."


def mandate_fee(conn: Connection, sale: dict, price: int, period: int, now: datetime) -> int:
    """At a completed sale, the advisory firm that ran it (and handed in its pitch book) is paid its success fee by the seller."""
    job = _one(conn, "SELECT * FROM firm_jobs WHERE process_id = %s AND kind = 'mandate' AND status = 'done' AND score >= %s",
               (sale["id"], firm.DUTY_PASS))
    if job is None:
        return 0
    f = _one(conn, "SELECT * FROM pro_firms WHERE id = %s", (job["firm_id"],))
    paid = _split_fee(conn, f, sale["seller_account"], apply_bps(price, job["fee"]), f"{f['name']}: success fee for running the sale of "
                      f"{sale['company']}", period, f"job:{job['id']}")
    if paid and sale["seller_empire_id"]:
        empires._book(conn, sale["seller_empire_id"], period, "Professional fees", f"{f['name']}: success fee for the sale of {sale['company']}",
                      paid, True, now, kind="fee", desk="head")
    return paid


# ---------------------------------------------------------------------------
# Restructuring a failing company's loans
# ---------------------------------------------------------------------------

def propose_restructuring(conn: Connection, player_id, company_id, fee: int, now: datetime) -> dict:
    """An advisory firm offers to restructure a failing private company's bank loans: a year more, and a lower rate.
    Its plan must hold up; the fee is paid only if the company is out of trouble two quarters later."""
    with conn.transaction():
        state = _open(conn, now)
        f = _mine(conn, player_id)
        if f["kind"] != "advisory":
            raise EmpireError("Debts are restructured by an advisory firm.")
        company = _one(conn, "SELECT * FROM companies WHERE id = %s AND NOT listed AND status = 'trading' FOR UPDATE", (company_id,))
        from simulation import firm_owned
        if company is None or not firm_owned.failing(conn, company_id):
            raise EmpireError("Only a private company in trouble needs its debts restructured.")
        if not _one(conn, "SELECT 1 FROM company_debts WHERE company_id = %s AND kind = 'bank_loan' AND principal_outstanding > 0", (company_id,)):
            raise EmpireError("It has no bank loan to restructure.")
        if not isinstance(fee, int) or isinstance(fee, bool) or not 0 <= fee <= apply_bps(firm_owned._quarter_sales(conn, company_id), 500):
            raise EmpireError("A fee of at most 5% of a quarter's sales.")
        owner = private.controller(conn, company_id)
        seat = empires.seat_of(conn, player_id)
        if owner and seat and seat["empire_id"] == owner["empire_id"]:
            raise EmpireError("An adviser from the empire that owns the company is not independent.")
        if _one(conn, "SELECT 1 FROM firm_jobs WHERE company_id = %s AND kind = 'restructuring' AND (status = 'open' OR period > %s)",
                (company_id, state["period"] - 4)):
            raise EmpireError("A company's debts are restructured once a year at most.")
        owner_empire = empires._empire(conn, owner["empire_id"]) if owner else None
        asks_owner = bool(owner_empire and firm.player_run(owner_empire))
        job = _one(conn, "INSERT INTO firm_jobs (firm_id, kind, client_account, client_empire_id, company_id, fee, period, at, words)"
                         " VALUES (%s, 'restructuring', %s, %s, %s, %s, %s, %s, %s) RETURNING id",
                   (f["id"], company["account_id"], owner["empire_id"] if owner else None, company_id, fee, state["period"], now,
                    AWAITING_OWNER if asks_owner else None))
        if asks_owner:
            # A company run by players' empire is restructured only if its head agrees to the adviser and the fee.
            firm.ask(conn, owner_empire, kind="restructuring_offer", desk="head", asked_by=player_id,
                     title=f"{f['name']} offers to restructure the bank loan of {company['name']}, for {_money(fee)} if it works",
                     amount=fee, payload={"job_id": job["id"]}, period=state["period"], now=now)
            _log(conn, owner["empire_id"], f"{f['name']} has offered to restructure the debts of {company['name']}. The head decides.", now)
        return {"job_id": job["id"]}


AWAITING_OWNER = "Waiting for the owners to accept."


def _restructuring_accepted(conn: Connection, approval: dict, now: datetime) -> None:
    conn.execute("UPDATE firm_jobs SET words = NULL WHERE id = %s AND status = 'open' AND words = %s", (approval["payload"]["job_id"], AWAITING_OWNER))


def _restructuring_refused(conn: Connection, approval: dict, now: datetime) -> None:
    conn.execute("UPDATE firm_jobs SET status = 'cancelled', words = 'The owners turned it down.' WHERE id = %s AND status = 'open'",
                 (approval["payload"]["job_id"],))


def _restructure_terms(conn: Connection, job: dict) -> dict:
    debt = _one(conn, "SELECT * FROM company_debts WHERE company_id = %s AND kind = 'bank_loan' AND principal_outstanding > 0"
                      " ORDER BY principal_outstanding DESC LIMIT 1", (job["company_id"],))
    if debt is None:
        raise EmpireError("The company has no bank loan left to restructure.")
    rows = _rows(conn, "SELECT operating_profit, depreciation FROM company_results WHERE company_id = %s AND period >= 1 ORDER BY period DESC LIMIT 4",
                 (job["company_id"],))
    ebitda = sum(r["operating_profit"] + r["depreciation"] for r in rows) * 4 // max(len(rows), 1)
    policy = _one(conn, "SELECT next_policy_rate_bps FROM economy_results ORDER BY period DESC LIMIT 1")["next_policy_rate_bps"]
    new_rate = max(debt["annual_rate_bps"] - RESTRUCTURE_RATE_CUT_BPS, policy)
    cover = max(ebitda, 0) * 100 // max(apply_bps(debt["principal_outstanding"], new_rate), 1)
    return fd.terms(
        "Restructure the company's largest bank loan: the bank gives it two more years and cuts the rate by up to three points "
        "(never below the Central Bank's). How many times would a year's earnings cover a year's interest on the new terms?",
        [fd.fact("Earnings before interest, tax and wear, a year (EBITDA)", ebitda), fd.fact("Loan", debt["principal_outstanding"]),
         fd.fact("Rate now", debt["annual_rate_bps"], "percent"), fd.fact("Rate on the new terms", new_rate, "percent")],
        [fd.q_number("cover", "Times covered, in hundredths (for 1.84 times, type 184)", money=False)], {"cover": cover},
        debt_id=str(debt["id"]), new_rate=new_rate, method="EBITDA ÷ (loan × new rate), in hundredths")


def _finish_restructuring(conn: Connection, f: dict, job: dict, well: bool, now: datetime, period: int) -> str:
    """A plan that holds up and shows the company can carry the loan, the bank accepts."""
    terms = job["terms"]
    from simulation import firm_owned
    debt = _one(conn, "SELECT * FROM company_debts WHERE id = %s", (terms["debt_id"],))
    company = _one(conn, "SELECT status, listed FROM companies WHERE id = %s", (job["company_id"],))
    if debt is None or debt["principal_outstanding"] <= 0 or company["status"] != "trading" or company["listed"] \
            or not firm_owned.failing(conn, job["company_id"]):
        conn.execute("UPDATE firm_jobs SET fee = 0 WHERE id = %s", (job["id"],))
        return "The company no longer needs it: its loan is gone, it is sold or listed, or it is out of trouble. Nothing was changed."
    if not well or terms["_truth"]["cover"] < 100:
        return "The bank turned the plan down: it did not hold up, or showed the company cannot carry the loan even so."
    conn.execute("UPDATE company_debts SET annual_rate_bps = %s, maturity_period = greatest(maturity_period, %s) + %s WHERE id = %s",
                 (terms["new_rate"], period, RESTRUCTURE_QUARTERS, terms["debt_id"]))
    conn.execute("UPDATE firm_jobs SET period = %s WHERE id = %s", (period, job["id"]))
    owner = private.controller(conn, job["company_id"])
    company = _one(conn, "SELECT name FROM companies WHERE id = %s", (job["company_id"],))
    if owner:
        _log(conn, owner["empire_id"], f"{f['name']} restructured the loan of {company['name']}: two more years, at a lower rate.", now)
    return "The bank accepted the plan: two more years, at a lower rate. The fee is paid if the company is out of trouble in two quarters."


def _judge_restructurings(conn: Connection, period: int, now: datetime) -> None:
    from simulation import firm_owned
    for job in _rows(conn, "SELECT * FROM firm_jobs WHERE kind = 'restructuring' AND status = 'done' AND period = %s - 2 AND fee > 0"
                           " AND words LIKE 'The bank accepted%%' FOR UPDATE", (period,)):
        company = _one(conn, "SELECT * FROM companies WHERE id = %s", (job["company_id"],))
        f = _one(conn, "SELECT * FROM pro_firms WHERE id = %s", (job["firm_id"],))
        if company["status"] == "trading" and not firm_owned.failing(conn, company["id"]):
            _split_fee(conn, f, company["account_id"], job["fee"], f"{company['name']}: {f['name']}'s fee for a restructuring that worked",
                       period + 1, f"job:{job['id']}")
            _reputation(conn, f["id"], 3)
        conn.execute("UPDATE firm_jobs SET fee = 0 WHERE id = %s", (job["id"],))


# ---------------------------------------------------------------------------
# A small bank: lending to empires, underwriting listings, paying out profits
# ---------------------------------------------------------------------------

def offer_loan(conn: Connection, player_id, empire_id: int, amount: int, rate_bps: int, quarters: int, now: datetime) -> dict:
    """A small bank offers an empire a loan from its capital. The empire's head accepts or not."""
    with conn.transaction():
        state = _open(conn, now)
        f = _mine(conn, player_id)
        if f["kind"] != "bank":
            raise EmpireError("Only a small bank lends.")
        borrower = _one(conn, "SELECT * FROM empires WHERE id = %s AND status = 'active' AND kind = 'player'", (empire_id,))
        if borrower is None:
            raise EmpireError("A small bank lends to empires run by players.")
        if empires.seat_of(conn, player_id)["empire_id"] == empire_id:
            raise EmpireError("A bank does not lend to the empire its founder sits in.")
        if not isinstance(amount, int) or isinstance(amount, bool) or amount < million_naira(10):
            raise EmpireError("A loan of at least ₦10 million.")
        if not isinstance(rate_bps, int) or isinstance(rate_bps, bool) or not 0 < rate_bps <= 6000 or not isinstance(quarters, int) or not 1 <= quarters <= 20:
            raise EmpireError("A rate up to 60% a year, for 1 to 20 quarters.")
        if amount > ledger.balance(conn, f["account_id"]):
            raise EmpireError("The bank has not that much cash to lend.")
        _rate_ok(rate_bps, state["policy_rate_bps"])
        offer = _one(conn, "INSERT INTO bank_loan_offers (firm_id, empire_id, amount, rate_bps, quarters, period, at) VALUES (%s, %s, %s, %s, %s, %s, %s)"
                           " RETURNING id", (f["id"], empire_id, amount, rate_bps, quarters, state["period"], now))
        _log(conn, empire_id, f"{f['name']}, a small bank, offers the empire a loan of {_money(amount)} at {rate_bps / 100:.2f}% for {quarters} quarters.", now)
        return {"offer_id": offer["id"]}


def _rate_ok(rate_bps: int, policy_bps: int) -> None:
    if rate_bps < policy_bps:
        raise EmpireError(f"No bank lends below the Central Bank's rate ({policy_bps / 100:.2f}%).")
    if rate_bps > policy_bps + LOAN_RATE_ABOVE_MOST:
        raise EmpireError(f"A small bank lends at no more than {LOAN_RATE_ABOVE_MOST // 100} points above the Central Bank's rate "
                          f"({(policy_bps + LOAN_RATE_ABOVE_MOST) / 100:.2f}%).")


def answer_loan(conn: Connection, head_id, offer_id: int, accept: bool, now: datetime) -> dict:
    """The head takes the bank's loan (it is serviced like any of the empire's debts) or turns it down."""
    with conn.transaction():
        state = _open(conn, now)
        empire = empires._head(conn, head_id)
        offer = _one(conn, "SELECT * FROM bank_loan_offers WHERE id = %s AND empire_id = %s AND status = 'offered' FOR UPDATE", (offer_id, empire["id"]))
        if offer is None:
            raise EmpireError("There is no such loan offer waiting.")
        if not accept:
            conn.execute("UPDATE bank_loan_offers SET status = 'refused' WHERE id = %s", (offer_id,))
            return {"accepted": False}
        f = _one(conn, "SELECT * FROM pro_firms WHERE id = %s FOR UPDATE", (offer["firm_id"],))
        if f["status"] != "open":
            raise EmpireError("That bank has closed.")
        _rate_ok(offer["rate_bps"], state["policy_rate_bps"])          # the Central Bank's rate may have moved since the offer
        founder_seat = empires.seat_of(conn, f["founder_id"])
        if founder_seat and founder_seat["empire_id"] == empire["id"]:
            raise EmpireError("The bank's founder now sits in your empire: a bank does not lend to its founder's empire.")
        from simulation import firm_money
        if offer["amount"] > firm_money.gearing_room(conn, empire, now):
            raise EmpireError("With this loan the empire would owe more than half of what it owns.")
        try:
            ledger.transfer(conn, payer=f["account_id"], receiver=empire["account_id"], amount=offer["amount"], kind="empire_borrowing",
                            memo=f"{empire['name']}: loan from {f['name']}", period=state["period"], reference=f"bank_offer:{offer_id}")
        except ledger.InsufficientFunds:
            raise EmpireError("The bank no longer has that much cash.") from None
        conn.execute("INSERT INTO empire_debts (empire_id, kind, lender_account, lender_name, principal, outstanding, rate_bps, taken_period,"
                     " due_period, signed_by, at) VALUES (%s, 'loan', %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                     (empire["id"], f["account_id"], f["name"], offer["amount"], offer["amount"], offer["rate_bps"], state["period"],
                      state["period"] + offer["quarters"], head_id, now))
        conn.execute("UPDATE bank_loan_offers SET status = 'taken' WHERE id = %s", (offer_id,))
        _log(conn, empire["id"], f"The empire borrowed {_money(offer['amount'])} from {f['name']}.", now)
        return {"accepted": True}


def pay_out(conn: Connection, player_id, amount: int, now: datetime) -> dict:
    """The founder pays out a small bank's profit: cash above its capital and what it has lent. 60% to the founder's
    empire and 40% to the founder, as for any fee."""
    with conn.transaction():
        state = _open(conn, now)
        f = _mine(conn, player_id)
        if f["kind"] != "bank":
            raise EmpireError("Only a small bank keeps money to pay out.")
        lent = _one(conn, "SELECT coalesce(sum(outstanding), 0)::bigint AS n FROM empire_debts WHERE lender_account = %s AND status IN ('open', 'called', 'defaulted')",
                    (f["account_id"],))["n"]
        spare = ledger.balance(conn, f["account_id"]) + lent - f["capital"]
        if not isinstance(amount, int) or isinstance(amount, bool) or not 0 < amount <= min(spare, ledger.balance(conn, f["account_id"])):
            raise EmpireError(f"The bank's profit that can be paid out is {_money(max(min(spare, ledger.balance(conn, f['account_id'])), 0))}.")
        paid = _split_fee(conn, f, f["account_id"], amount, f"{f['name']}: profit paid out", state["period"], f"firm:{f['id']}")
        return {"paid": paid}


def sell_holding(conn: Connection, player_id, company_id, quantity: int, limit_price: int, now: datetime) -> dict:
    """The founder of a small bank sells shares the bank holds (from an underwriting, or a borrower's default) on the exchange."""
    from simulation import exchange
    with conn.transaction():
        _open(conn, now)
        f = _mine(conn, player_id)
        if f["kind"] != "bank":
            raise EmpireError("Only a small bank holds shares.")
        company = _one(conn, "SELECT ticker, share_asset, listed FROM companies WHERE id = %s", (company_id,))
        if company is None or not company["listed"] or ledger.balance(conn, f["account_id"], company["share_asset"]) <= 0:
            raise EmpireError("The bank holds no shares of that company that trade on the exchange.")
        try:
            return exchange.place_order(conn, account=f["account_id"], ticker=company["ticker"], side="sell", kind="limit", quantity=quantity,
                                        limit_price=limit_price, now=now)
        except exchange.ExchangeError as refused:
            raise EmpireError(str(refused)) from None


def underwriting_ask(conn: Connection, offer_id: int, firm_id: int, empire_id, now: datetime) -> int:
    """A listing asks a small bank to underwrite it. The bank's founder accepts before the offer closes."""
    f = _firm(conn, firm_id)
    if f["kind"] != "bank":
        raise EmpireError("A listing is underwritten by a small bank.")
    seat = empires.seat_of(conn, f["founder_id"])
    if seat and seat["empire_id"] == empire_id:
        raise EmpireError("A bank run from your own empire cannot stand behind your own listing.")
    offer = _one(conn, "SELECT * FROM share_offers WHERE id = %s", (offer_id,))
    return _one(conn, "INSERT INTO firm_jobs (firm_id, kind, client_account, client_empire_id, company_id, fee, period, at, words)"
                      " VALUES (%s, 'underwriting', (SELECT account_id FROM companies WHERE id = %s), %s, %s, %s, %s, %s, %s) RETURNING id",
                (f["id"], offer["company_id"], empire_id, offer["company_id"], UNDERWRITING_FEE_BPS, offer["opens_period"], now,
                 f"offer:{offer_id}"))["id"]


def accept_underwriting(conn: Connection, player_id, job_id: int, now: datetime) -> dict:
    """The bank's founder agrees to stand behind the listing: it will buy, at the offer price, the shares the public does not."""
    with conn.transaction():
        _open(conn, now)
        f, job = _job(conn, player_id, job_id)
        if job["kind"] != "underwriting":
            raise EmpireError("That is not an underwriting.")
        offer_id = int(job["words"].split(":")[1])
        offer = _one(conn, "SELECT * FROM share_offers WHERE id = %s AND status = 'open' FOR UPDATE", (offer_id,))
        if offer is None:
            raise EmpireError("That listing has closed.")
        if offer["underwriter_firm_id"]:
            raise EmpireError("Another bank already stands behind it.")
        if ledger.balance(conn, f["account_id"]) < offer["shares"] * offer["price"]:
            raise EmpireError(f"To stand behind it the bank must have the cash to buy every share on offer: {_money(offer['shares'] * offer['price'])}.")
        conn.execute("UPDATE share_offers SET underwriter_firm_id = %s, underwriting_fee_bps = %s WHERE id = %s", (f["id"], job["fee"], offer_id))
        conn.execute("UPDATE firm_jobs SET status = 'done', done_at = %s, words = %s WHERE id = %s",
                     (now, f"offer:{offer_id} accepted", job_id))
        return {"offer_id": offer_id}


def underwrite(conn: Connection, offer: dict, left: int) -> int:
    """At the close of an underwritten listing: how many of the shares nobody took the bank buys, as far as its cash goes."""
    f = _one(conn, "SELECT * FROM pro_firms WHERE id = %s", (offer["underwriter_firm_id"],))
    if f is None or left <= 0:
        return 0
    return max(min(left, ledger.balance(conn, f["account_id"]) // max(offer["price"], 1)), 0)


def underwritten(conn: Connection, offer: dict, company: dict, f: dict, took: int, raised: int, period: int, now: datetime) -> str:
    """The listing has closed: the company pays the bank its fee out of what was raised."""
    # The fee is for the part of the offer the bank could truly have bought: a promise it could not keep earns nothing.
    backed = min(max(ledger.balance(conn, f["account_id"]), 0) + took * offer["price"], offer["shares"] * offer["price"])
    fee = apply_bps(min(raised, backed), offer["underwriting_fee_bps"])
    paid = _split_fee(conn, f, company["account_id"], fee, f"{company['name']}: {f['name']}'s fee for underwriting its listing", period,
                      f"offer:{offer['id']}")
    conn.execute("UPDATE pro_firms SET jobs_done = jobs_done + 1 WHERE id = %s", (f["id"],))
    careers._event(conn, f["founder_id"], "asset_manager", "firm", f"{f['name']} underwrote the listing of {company['name']}"
                   + (f" and bought {took:,} shares nobody else took." if took else "."), now)
    return (f" {f['name']} stood behind the offer" + (f" and bought the {took:,} shares nobody else took" if took else "")
            + f"; its fee was {_money(paid)}.")


# ---------------------------------------------------------------------------
# What players see, and the closes
# ---------------------------------------------------------------------------

def view(conn: Connection, seat: dict, empire: dict, state: dict, now: datetime) -> dict:
    me = seat["player_id"]
    mine = _one(conn, "SELECT * FROM pro_firms WHERE founder_id = %s AND status = 'open'", (me,))
    out = {"directory": firms(conn), "kinds": {k: {"name": v[1], "build": v[0], "does": v[2]} for k, v in KINDS.items()},
           "can_found": seat["build"] if mine is None and empire["kind"] == "player" else None, "bank_capital_least": BANK_CAPITAL_LEAST,
           "fee_least": JOB_FEE_LEAST, "fee_most": JOB_FEE_MOST, "mine": None, "step_firms": STEP_FIRMS}
    if mine:
        jobs = []
        for j in _rows(conn, "SELECT j.*, c.name AS company FROM firm_jobs j LEFT JOIN companies c ON c.id = j.company_id WHERE j.firm_id = %s"
                             " ORDER BY (j.status = 'open') DESC, j.id DESC LIMIT 20", (mine["id"],)):
            jobs.append({"id": j["id"], "kind": j["kind"], "company": j["company"], "fee": j["fee"], "status": j["status"],
                         "terms": firm._public_terms(j["terms"]) if j["status"] == "open" else None, "opinion": j["opinion"],
                         "score": j["score"], "words": j["words"], "opened": j["terms"] is not None})
        lent = _rows(conn, "SELECT d.outstanding, d.rate_bps, d.status, e.name FROM empire_debts d JOIN empires e ON e.id = d.empire_id"
                           " WHERE d.lender_account = %s AND d.status <> 'repaid' ORDER BY d.id", (mine["account_id"],))
        held = [{"company_id": r["id"], "name": r["name"], "ticker": r["ticker"], "shares": r["balance"]}
                for r in _rows(conn, "SELECT c.id, c.name, c.ticker, b.balance FROM ledger_balances b JOIN companies c ON c.share_asset = b.asset"
                                     " WHERE b.account_id = %s AND b.balance > 0 ORDER BY c.name", (mine["account_id"],))]
        failing = []
        if mine["kind"] == "advisory":
            from simulation import firm_owned
            failing = [{"company_id": r["id"], "name": r["name"]} for r in _rows(
                conn, "SELECT DISTINCT c.id, c.name FROM companies c JOIN company_debts d ON d.company_id = c.id AND d.kind = 'bank_loan'"
                      " AND d.principal_outstanding > 0 WHERE NOT c.listed AND c.status = 'trading' ORDER BY c.name") if firm_owned.failing(conn, r["id"])]
        out["mine"] = {"id": mine["id"], "kind": mine["kind"], "name": mine["name"], "reputation": mine["reputation"], "jobs_done": mine["jobs_done"],
                       "holdings": held, "failing": failing,
                       "cash": ledger.balance(conn, mine["account_id"]), "capital": mine["capital"], "jobs": jobs,
                       "lent": [{"to": r["name"], "outstanding": r["outstanding"], "rate_bps": r["rate_bps"], "status": r["status"]} for r in lent],
                       "borrowers": [{"id": e["id"], "name": e["name"]} for e in _rows(conn, "SELECT id, name FROM empires WHERE kind = 'player' AND"
                                                                                        " status = 'active' AND id <> %s ORDER BY name", (empire["id"],))]
                                    if mine["kind"] == "bank" else []}
    if empire["head_player_id"] == me:
        out["loan_offers"] = [{"id": r["id"], "bank": r["bank"], "amount": r["amount"], "rate_bps": r["rate_bps"], "quarters": r["quarters"]}
                              for r in _rows(conn, "SELECT o.*, f.name AS bank FROM bank_loan_offers o JOIN pro_firms f ON f.id = o.firm_id"
                                                   " WHERE o.empire_id = %s AND o.status = 'offered' ORDER BY o.id", (empire["id"],))]
    return out


def waiting(conn: Connection, seat: dict, empire: dict, now: datetime) -> int:
    mine = _one(conn, "SELECT id FROM pro_firms WHERE founder_id = %s AND status = 'open'", (seat["player_id"],))
    n = _one(conn, "SELECT count(*) AS n FROM firm_jobs WHERE firm_id = %s AND status = 'open'", (mine["id"],))["n"] if mine else 0
    if empire["head_player_id"] == seat["player_id"]:
        n += _one(conn, "SELECT count(*) AS n FROM bank_loan_offers WHERE empire_id = %s AND status = 'offered'", (empire["id"],))["n"]
    return n


def _closed(conn: Connection, period: int, now: datetime) -> None:
    """As a quarter closes: jobs on sales now decided lapse if not done (no fee, and the firm's name suffers a little)."""
    with conn.transaction():
        for job in _rows(conn, "SELECT j.* FROM firm_jobs j JOIN sale_processes s ON s.id = j.process_id WHERE j.status = 'open'"
                               " AND s.status <> 'open' FOR UPDATE OF j"):
            conn.execute("UPDATE firm_jobs SET status = 'lapsed' WHERE id = %s", (job["id"],))
            if job["step_id"]:
                conn.execute("UPDATE deal_steps SET firm_id = NULL WHERE id = %s AND status = 'due'", (job["step_id"],))
            _reputation(conn, job["firm_id"], -1)
        conn.execute("UPDATE firm_jobs SET status = 'lapsed' WHERE status = 'open' AND kind IN ('restructuring', 'audit') AND process_id IS NULL"
                     " AND period < %s", (period - 1,))
        conn.execute("UPDATE bank_loan_offers SET status = 'lapsed' WHERE status = 'offered' AND period <= %s", (period,))
        # A listing nobody stood behind closes the request to underwrite it.
        conn.execute("UPDATE firm_jobs j SET status = 'lapsed' FROM share_offers o WHERE j.kind = 'underwriting' AND j.status = 'open'"
                     " AND o.id = split_part(split_part(j.words, ':', 2), ' ', 1)::bigint AND o.status <> 'open'")
        _judge_restructurings(conn, period, now)


firm.CLOSED.append(_closed)
firm.EXECUTORS["restructuring_offer"] = _restructuring_accepted
firm.REFUSERS["restructuring_offer"] = _restructuring_refused
firm.VIEW["practice"] = lambda conn, seat, empire, state, now: view(conn, seat, empire, state, now) if firm.player_run(empire) else None
firm.WAITING.append(lambda conn, seat, empire, now: waiting(conn, seat, empire, now) if firm.player_run(empire) else 0)
firm.OPINION_NAMES.update({"audit_opinion": "Audit opinions"})
