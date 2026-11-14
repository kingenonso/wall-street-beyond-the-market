"""Private equity stage, part 2A: finding and buying a private company.

  the data room      a company's private papers, shown only after Legal Counsel has signed a
                     confidentiality agreement for the empire
  the six checks     background (Intelligence desk), the accounts (Accountant), valuation (Investment
                     Banker), stress test and site inspection (Risk Manager), ownership and contracts
                     (Legal Counsel); a fairness opinion before a large deal; the head decides
  the agreement      the seller's draft, argued clause by clause: its promises, the seller's escape
                     clauses, and the protections the buyer asks for. Every change has a price
  bids               sealed, or at an auction the seller runs, against other empires (the computer-run
                     ones bid too). Paid with the empire's cash, partners' money, and a buyout loan
                     secured on the company itself, with promises the bank tests every quarter
  completion         money, shares and loan move together through the ledger as the quarter closes;
                     part of the price is held back against claims if the agreement says so
  claims             a promise that turns out false is claimed against the seller

A deal needs all three: the Banker brings it, the Accountant checks it, the Risk Manager signs its
risks. Each puts their name to it, and the record later shows whether they were right.

Nothing here creates money. Every naira moves through the ledger, from a real account to a real account.
"""

from __future__ import annotations

from datetime import datetime

from psycopg import Connection
from psycopg.types.json import Jsonb

from simulation import banking, careers, clock, empires, firm, leagues, ledger, private
from simulation import firm_duties as fd
from simulation import world_data as data
from simulation.empires import EmpireError, _log, _money, _one, _open, _rows
from simulation.money import BPS, apply_bps, million_naira

ESCROW = "deals:escrow"
STEPS = {   # step -> (desk, title, why)
    "background": ("investment_banker", "Background digging",
                   "What the papers leave out: who its customers are, and what is about to change."),
    "accounts": ("asset_manager", "Check the accounts against the bank",
                 "Management accounts can be dressed up. Bank statements cannot."),
    "valuation": ("investment_banker", "Value the company",
                  "What it is worth decides what to bid. The banker who brings a deal answers for this figure."),
    "stress": ("risk_manager", "Stress test and site inspection",
               "Can it carry the loan if things go wrong, and are its assets what the papers say?"),
    "legal": ("investment_banker", "Ownership and contracts",
              "What the registry and the courts hold on it: charges, claims and suits."),
    "fairness": ("investment_banker", "Fairness opinion",
                 "Before a large deal, a banker signs whether the price is fair."),
}
NEEDED = ("accounts", "valuation", "stress")       # a deal needs all three before a bid
FAIRNESS_ABOVE = million_naira(20_000)             # a deal above ₦20 billion needs a fairness opinion
STAFF_FINDS_BPS = 7000                             # computer-run staff find what is there this often
LOAN_MOST_BPS = 6000                               # a buyout loan is at most 60% of the price...
LOAN_EBITDA_X = 4                                  # ...and at most four years of the company's earnings
BUYOUT_SPREAD_BPS = 300                            # a buyout loan costs this much more than the company's own rate
COVENANTS = {"debt_x_most": 5, "cover_least_bps": 15_000}   # at most 5x yearly earnings owed; earnings at least 1.5x the interest
AUCTION_STEP_BPS = 200                             # an auction bid must beat the highest by 2%
ESCROW_BPS = 1000                                  # held back from the seller when the agreement says so
CLAIM_WINDOW = 4                                   # quarters for a claim, unless the window is shortened
COMPUTER_BID_CASH_BPS = 6000                       # a computer-run empire bids at most 60% of its cash
OVERPAY_MOST_BPS = 15_000                          # no bid above 150% of the company's worth or its asking price

CLAUSES = {
    # Fair clauses: the seller's promises, and the ordinary terms. Striking one out costs 0.5% and gains nothing.
    "accounts_warranty": ("The seller promises the accounts given are true and complete.", False, 50),
    "debts_warranty": ("The seller promises every debt and tax bill of the company has been disclosed.", False, 50),
    "assets_warranty": ("The seller promises the assets are in the condition stated in the register.", False, 50),
    "title_warranty": ("The seller promises it owns the shares outright and nobody else has a claim to them.", False, 50),
    "completion": ("The sale completes as the quarter closes, when the price is paid.", False, 50),
    "non_compete": ("The founders will not start a rival business for two years.", False, 50),
    # The seller's escape clauses. Each costs the buyer if left in; striking one out has a price.
    "as_is": ("The buyer takes the company as it stands: no promise in this agreement may be claimed on.", True, 300),
    "claim_cap": ("Any claim against the seller is limited to one percent of the price.", True, 100),
    "short_window": ("Claims must be made within one quarter of completion.", True, 50),
}
PROTECTIONS = {   # what the buyer may ask to add, and its price
    "escrow": ("Ten percent of the price is held back for four quarters to meet any claims.", 100),
    "title_indemnity": ("The seller will make good any claim on the company's ownership.", 50),
}
WARRANTY_OF = {"dressed_revenue": "accounts_warranty", "hidden_debt": "debts_warranty", "worn_assets": "assets_warranty",
               "ownership_claim": "title_warranty"}
SHOWN_BY = {"accounts": ("dressed_revenue",), "stress": ("worn_assets",), "legal": ("hidden_debt", "ownership_claim")}
FINDS_OF = {"background": ("customer_leaving", "contract_coming"), "accounts": ("dressed_revenue",),
            "valuation": ("underpriced",), "stress": ("worn_assets",), "legal": ("hidden_debt", "ownership_claim")}


def escrow_account(conn: Connection):
    row = _one(conn, "SELECT id FROM ledger_accounts WHERE code = %s", (ESCROW,))
    return row["id"] if row else ledger.create_account(conn, kind="escrow", name="Deals: money held in escrow", code=ESCROW)


def _seat(conn: Connection, player_id) -> tuple[dict, dict]:
    seat, empire = firm._active(conn, player_id)
    if not firm.player_run(empire):
        raise EmpireError("Only an empire run by players buys and runs companies this way.")
    return seat, empire


def _process(conn: Connection, process_id, *, lock: bool = False) -> dict:
    sale = _one(conn, "SELECT s.*, c.name AS company, c.ticker, c.sector, c.headquarters FROM sale_processes s JOIN companies c ON c.id = s.company_id"
                      " WHERE s.id = %s" + (" FOR UPDATE OF s" if lock else ""), (process_id,))
    if sale is None:
        raise EmpireError("There is no such sale.")
    return sale


def _file(conn: Connection, empire_id, file_id, *, lock: bool = False) -> dict:
    found = _one(conn, "SELECT * FROM deal_files WHERE id = %s AND empire_id = %s" + (" FOR UPDATE" if lock else ""), (file_id, empire_id))
    if found is None:
        raise EmpireError("Your empire has no such deal file.")
    return found


def _desk_ok(conn: Connection, empire: dict, seat: dict, build: str) -> bool:
    """A member of the desk does its work; the head does it when the desk has nobody and no staff."""
    if seat["build"] == build:
        return True
    return (empire["head_player_id"] == seat["player_id"] and not firm.desk_members(conn, empire["id"], build)
            and not firm.desk_staffed(conn, empire["id"], build))


# ---------------------------------------------------------------------------
# Bringing a deal, and the data room
# ---------------------------------------------------------------------------

def _conflicted(conn: Connection, empire_id, process_id) -> str | None:
    """A firm auditing or running a sale is on the seller's side: its founder's empire may not buy."""
    row = _one(conn, "SELECT f.name FROM firm_jobs j JOIN pro_firms f ON f.id = j.firm_id JOIN empire_seats s ON s.player_id = f.founder_id"
                     " WHERE j.process_id = %s AND j.kind IN ('audit', 'mandate') AND s.empire_id = %s LIMIT 1", (process_id, empire_id))
    return row["name"] if row else None


def open_file(conn: Connection, player_id, process_id: int, now: datetime) -> dict:
    """The Investment Banker brings a company on sale to the empire. The six checks are set out."""
    with conn.transaction():
        state = _open(conn, now)
        seat, empire = _seat(conn, player_id)
        sale = _process(conn, process_id, lock=True)
        if sale["status"] != "open":
            raise EmpireError("That sale is over.")
        if sale["seller_empire_id"] == empire["id"]:
            raise EmpireError("Your empire is the seller.")
        if not _desk_ok(conn, empire, seat, "investment_banker"):
            raise EmpireError("A deal is brought by the empire's Investment Banker.")
        conflict = _conflicted(conn, empire["id"], process_id)
        if conflict:
            raise EmpireError(f"{conflict}, run from your empire, is working for the seller on this sale. Your empire may not buy it.")
        try:
            with conn.transaction():
                made = _one(conn, "INSERT INTO deal_files (empire_id, process_id, brought_by, at) VALUES (%s, %s, %s, %s) RETURNING *",
                            (empire["id"], process_id, player_id, now))
        except Exception:
            raise EmpireError("Your empire already has a file on that sale.") from None
        for step, (build, _title, _why) in STEPS.items():
            if step == "fairness" and sale["asking"] <= FAIRNESS_ABOVE:
                continue
            conn.execute("INSERT INTO deal_steps (file_id, step, build) VALUES (%s, %s, %s)", (made["id"], step, build))
        firm.sign_opinion(conn, player_id, seat["build"], empire["id"], "deal_brought", f"Brought: {sale['company']}",
                          {"process_id": process_id}, state["period"], None, now)
        _log(conn, empire["id"], f"{firm._name(conn, player_id)} brought a deal: {sale['company']} is for sale {_how(sale)}.", now)
        return {"file_id": made["id"]}


def _how(sale: dict) -> str:
    return "by sealed bids" if sale["mode"] == "sealed" else "at auction"


def sign_nda(conn: Connection, player_id, file_id: int, now: datetime) -> dict:
    """Legal Counsel drafts and signs the confidentiality agreement. The data room opens, and the seller
    sends its draft of the sale agreement."""
    with conn.transaction():
        _open(conn, now)
        seat, empire = _seat(conn, player_id)
        found = _file(conn, empire["id"], file_id, lock=True)
        if found["nda_at"]:
            raise EmpireError("The confidentiality agreement is already signed.")
        if not _desk_ok(conn, empire, seat, "investment_banker"):
            raise EmpireError("A confidentiality agreement is drafted by the empire's Legal Counsel.")
        _sign_nda(conn, empire, found, player_id, now)
        return {"signed": True}


def _sign_nda(conn: Connection, empire: dict, found: dict, player_id, now: datetime) -> None:
    sale = _process(conn, found["process_id"])
    conn.execute("UPDATE deal_files SET nda_by = %s, nda_at = %s WHERE id = %s", (player_id, now, found["id"]))
    seed = private._seed(conn)
    for code, (_words, trap, _charge) in CLAUSES.items():
        if trap and private.roll(seed, sale["id"], empire["id"], "clause", code) % 3 != 0:
            continue                                   # each escape clause is in the seller's draft one time in three
        conn.execute("INSERT INTO deal_terms (process_id, empire_id, code, status, at) VALUES (%s, %s, %s, 'in', %s) ON CONFLICT DO NOTHING",
                     (sale["id"], empire["id"], code, now))
    _log(conn, empire["id"], f"A confidentiality agreement was signed for {sale['company']}. The data room is open.", now)


def data_room(conn: Connection, company_id, empire_id, process_id=None) -> dict:
    """What the seller shows a buyer who has signed: its papers, its assets as stated, its debts, its
    manager, its routes, and its place in its industry. What the empire has found is shown beside it."""
    company = _one(conn, "SELECT c.*, s.name AS sector_name FROM companies c JOIN sectors s ON s.code = c.sector WHERE c.id = %s", (company_id,))
    papers = private.papers(conn, company_id)
    p = private.profile(conn, company_id)
    boss = private.manager(conn, company_id)
    # Its share of its industry: its papers' sales against the listed rivals' filed sales (other private companies publish nothing).
    listed = _one(conn, "SELECT coalesce(sum((r.figures->'income_statement'->>'revenue')::bigint), 0)::bigint AS n FROM companies c"
                        " JOIN LATERAL (SELECT figures FROM company_reports WHERE company_id = c.id ORDER BY period DESC, version DESC LIMIT 1) r ON true"
                        " WHERE c.sector = %s AND c.listed", (company["sector"],))["n"]
    mine = papers[-1]["revenue"] if papers else 0
    total = listed + mine or 1
    return {
        "company": {"name": company["name"], "ticker": company["ticker"], "sector": company["sector_name"], "city": company["headquarters"]},
        "papers": papers, "assets": private.asset_register(conn, company_id, true=False),
        "debts": [{"name": d["name"], "outstanding": d["principal_outstanding"], "rate_bps": d["annual_rate_bps"],
                   "due": clock.period_label(d["maturity_period"]) if d["maturity_period"] > 0 else "overdue"}
                  for d in _rows(conn, "SELECT * FROM company_debts WHERE company_id = %s AND principal_outstanding > 0 ORDER BY id", (company_id,))],
        "manager": {"name": boss["name"], "quality": boss["quality"]} if boss else None,
        "management": p["management"] if p else None,
        "market_share_bps": mine * BPS // total if listed else None,      # with no listed rival, there is nothing to set it against
        "routes": _routes(conn, company_id),
        "found": finds(conn, empire_id, company_id),
        "audit": firm_practice().audit_opinion(conn, process_id) if process_id else None,     # the auditor's opinion, if the sale has one
        "adviser": _one(conn, "SELECT f.name FROM sale_processes s JOIN pro_firms f ON f.id = s.adviser_firm_id WHERE s.id = %s",
                        (process_id,)) if process_id else None,
    }


def firm_practice():
    from simulation import firm_practice as practice
    return practice


def _routes(conn: Connection, company_id) -> list[dict]:
    return [{"id": r["id"], "from": r["city_a"], "to": r["city_b"], "fare_bps": r["fare_bps"], "planes": r["planes"]}
            for r in _rows(conn, "SELECT r.*, (SELECT count(*) FROM company_assets a WHERE a.route_id = r.id AND a.status = 'working') AS planes"
                                 " FROM airline_routes r WHERE r.company_id = %s AND r.closed_period IS NULL ORDER BY r.city_a, r.city_b", (company_id,))]


def finds(conn: Connection, empire_id, company_id) -> list[dict]:
    return [{"code": r["code"], "what": private.SECRET_NAMES.get(r["code"], r["code"]), "how": r["how"]}
            for r in _rows(conn, "SELECT * FROM deal_finds WHERE empire_id = %s AND company_id = %s ORDER BY at", (empire_id, company_id))]


def _found(conn: Connection, empire_id, company_id, code: str, how: str, now: datetime) -> None:
    conn.execute("INSERT INTO deal_finds (empire_id, company_id, code, how, at) VALUES (%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
                 (empire_id, company_id, code, how, now))


# ---------------------------------------------------------------------------
# The six checks
# ---------------------------------------------------------------------------

def _rate_bps(conn: Connection, company_id) -> int:
    """What the company would pay its bank: the Central Bank's rate and its rating's spread."""
    from simulation import world_data as data
    rating = _one(conn, "SELECT credit_rating FROM company_reports WHERE company_id = %s ORDER BY period DESC, version DESC LIMIT 1", (company_id,))
    policy = _one(conn, "SELECT next_policy_rate_bps FROM economy_results ORDER BY period DESC LIMIT 1")
    return (policy["next_policy_rate_bps"] if policy else data.OPENING_RATE_BPS) + data.LOAN_SPREAD_BPS.get(
        rating["credit_rating"] if rating else "BBB", 750)


def _prepare(conn: Connection, step: str, sale: dict, empire_id) -> dict:
    company_id = sale["company_id"]
    papers = private.papers(conn, company_id)
    if not papers:
        raise EmpireError("The company has no accounts yet. Look again after the quarter closes.")
    if step == "background":
        bank = private.bank_receipts(conn, company_id)
        first, last = bank[0]["total"], bank[-1]["total"]
        growth = (last - first) * BPS // max(first, 1)
        return fd.terms(
            "Your sources have sent the company's sales, as its customers paid them, by kind of customer. Work out how far its "
            "sales moved from the first quarter shown to the last. Read them rightly and your sources tell you what is about to change.",
            [fd.fact(f"{b['label']}: households / businesses / government", f"{_money(b['households'])} / {_money(b['business'])} / "
                     f"{_money(b['government'])}", "text") for b in bank],
            [fd.q_percent("growth", "Change in its sales, first quarter to last (%)")], {"growth": growth},
            method="(last quarter's sales − first quarter's) ÷ first quarter's, all three kinds of customer added together.")
    if step == "accounts":
        bank = private.bank_receipts(conn, company_id)
        shown = sum(p["revenue"] for p in papers)
        received = sum(b["total"] for b in bank)
        gap = (shown - received) * BPS // max(received, 1)
        return fd.terms(
            "Set the sales in the management accounts against what the bank statements say customers paid. How far above the "
            "bank's figure are the accounts? A gap means the accounts have been dressed up.",
            [*[fd.fact(f"Accounts say, {p['label']}", p["revenue"]) for p in papers],
             *[fd.fact(f"Bank received, {b['label']}", b["total"]) for b in bank]],
            [fd.q_percent("gap", "How far the accounts are above the bank's figure (%)")], {"gap": gap},
            method="(sales in the accounts − cash the bank received from customers) ÷ cash received, over all the quarters shown.")
    if step == "valuation":
        rate = _rate_bps(conn, company_id) + 300
        growth = 300
        year = papers[-4:]
        profit = sum(p["operating_profit"] for p in year) * len(year) // max(len(year), 1) * 4 // max(len(year), 1)
        after_tax = apply_bps(profit, BPS - 3000)
        debt, cash = papers[-1]["borrowings"], papers[-1]["cash"]
        value = (max(after_tax, 0) * (BPS + growth) // max(rate - growth, 100)) - debt + cash
        return fd.terms(
            "Value the whole company from its accounts: a year's operating profit after 30% tax, growing for ever at the rate "
            "given, discounted at the rate given; then take off its debts and add its cash.",
            [fd.fact("Operating profit over the last four quarters (a year)", profit), fd.fact("Tax", 3000, "percent"),
             fd.fact("Growth a year, for ever", growth, "percent"), fd.fact("Discount rate", rate, "percent"),
             fd.fact("Borrowings", debt), fd.fact("Cash", cash), fd.fact("Asking price", sale["asking"])],
            [fd.q_number("value", "What the whole company is worth (₦)")], {"value": value},
            method="profit × 0.7 × (1 + growth) ÷ (discount − growth) − borrowings + cash")
    if step == "stress":
        year = papers[-4:]
        ebitda = sum(p["operating_profit"] + p["depreciation"] for p in year) * 4 // max(len(year), 1)
        loan = apply_bps(sale["asking"], 5000)
        rate = _rate_bps(conn, company_id) + BUYOUT_SPREAD_BPS + 500
        cover = apply_bps(ebitda, 7000) * BPS // max(apply_bps(loan, rate), 1)
        register = private.asset_register(conn, company_id, true=False)
        old = sum(1 for a in register if a["age_quarters"] * BPS >= a["life_quarters"] * 6000)
        share = old * BPS // max(len(register), 1)
        return fd.terms(
            "Two tests. First: if its earnings fell by 30% and rates rose five points, how many times would its earnings cover a "
            "year's interest on a loan of half the asking price? Second, from the register: what share of its assets are past "
            "three-fifths of their working life, whatever condition the seller states?",
            [fd.fact("Earnings before interest, tax and wear, a year (EBITDA)", ebitda), fd.fact("Loan", loan),
             fd.fact("Interest rate after the rise", rate, "percent"),
             *[fd.fact(f"{a['name']}: age / life (quarters), stated condition", f"{a['age_quarters']} / {a['life_quarters']}, "
                       f"{a['condition_bps'] // 100}%", "text") for a in register]],
            [fd.q_number("cover", "Times covered, in hundredths (for 1.84 times, type 184)", money=False),
             fd.q_percent("old", "Share of assets past three-fifths of their life (%)")],
            {"cover": cover // 100, "old": share},
            method="cover = EBITDA × 0.7 ÷ (loan × rate), in hundredths; old = assets with age ≥ 60% of life ÷ all assets")
    if step == "legal":
        lines = private.registry(conn, company_id, private._seed(conn))
        live = sum(line["amount"] for line in lines if line["live"] and line["kind"] == "claim")
        return fd.terms(
            "Read the registry and court entries. Add up the claims and suits still live against the company (leave out "
            "charges for its loans, and anything settled or discharged).",
            [fd.fact(line["entry"], line["amount"]) for line in lines],
            [fd.q_number("claims", "Live claims and suits, in all (₦)")], {"claims": live},
            method="only entries that are claims or suits, and still live")
    if step == "fairness":
        year = papers[-4:]
        profit = sum(p["net_profit"] for p in year) * 4 // max(len(year), 1)
        listed = _one(conn, "SELECT avg(v.value_per_share::numeric * r.shares_in_issue / nullif(r.net_profit * 4, 0)) AS pe FROM companies c"
                            " JOIN LATERAL (SELECT * FROM company_valuations WHERE company_id = c.id ORDER BY period DESC LIMIT 1) v ON true"
                            " JOIN LATERAL (SELECT * FROM company_results WHERE company_id = c.id ORDER BY period DESC LIMIT 1) r ON true"
                            " WHERE c.listed AND c.sector = %s AND r.net_profit > 0", (sale["sector"],))
        multiple = int((listed["pe"] or 8) * 100) if listed else 800
        fair = sale["asking"] * 100 <= profit * multiple * 11 // 10
        return fd.terms(
            "Is the asking price fair? Set it against what listed companies in the same industry are worth for each naira of "
            "yearly profit. Fair means no more than a tenth above that multiple.",
            [fd.fact("Asking price", sale["asking"]), fd.fact("Profit a year in its accounts", profit),
             fd.fact("Listed rivals are worth, for each naira of yearly profit", f"{multiple / 100:.1f} times", "text")],
            [fd.q_choice("fair", "Is the price fair?", ["fair", "not fair"])], {"fair": "fair" if fair else "not fair"},
            method="asking ≤ yearly profit × the industry's multiple × 1.1")
    raise EmpireError("No such check.")


def open_step(conn: Connection, player_id, step_id: int, now: datetime) -> dict:
    """Open one of the checks on your desk. What it asks is fixed from the papers of this moment."""
    with conn.transaction():
        _open(conn, now)
        seat, empire, step, found, sale = _step_for(conn, player_id, step_id)
        if step["terms"] is None:
            terms = _prepare(conn, step["step"], sale, empire["id"])
            conn.execute("UPDATE deal_steps SET terms = %s, assigned_to = %s WHERE id = %s", (Jsonb(terms), player_id, step_id))
            step = {**step, "terms": terms}
            # What these facts put in front of the empire, it knows from now, whether or not the check is done well:
            # a buyer cannot answer wrongly on purpose and then claim for what it saw.
            p = private.profile(conn, sale["company_id"])
            for code in SHOWN_BY.get(step["step"], ()):
                if any(s["code"] == code for s in (p["secrets"] if p else [])):
                    conn.execute("INSERT INTO deal_shown (empire_id, company_id, code, at) VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING",
                                 (empire["id"], sale["company_id"], code, now))
        elif step["assigned_to"] not in (None, player_id):
            raise EmpireError("A colleague has that check open.")
        return {"id": step_id, "terms": firm._public_terms(step["terms"])}


def _step_for(conn: Connection, player_id, step_id: int):
    seat, empire = _seat(conn, player_id)
    step = _one(conn, "SELECT s.* FROM deal_steps s JOIN deal_files f ON f.id = s.file_id WHERE s.id = %s AND f.empire_id = %s FOR UPDATE OF s",
                (step_id, empire["id"]))
    if step is None:
        raise EmpireError("Your empire has no such check.")
    found = _file(conn, empire["id"], step["file_id"], lock=True)
    if found["status"] != "open":
        raise EmpireError("That deal file is closed.")
    if not found["nda_at"]:
        raise EmpireError("Nothing can be checked until the confidentiality agreement is signed and the data room is open.")
    if step["status"] != "due":
        raise EmpireError("That check is done.")
    if step["firm_id"]:
        raise EmpireError("That check was sent to an outside firm. The firm does it.")
    if not _desk_ok(conn, empire, seat, step["build"]):
        raise EmpireError(f"That check belongs to the {firm.DESK_NAMES[step['build']]}'s desk.")
    sale = _process(conn, found["process_id"])
    if sale["status"] != "open":
        raise EmpireError("That sale is over.")
    return seat, empire, step, found, sale


def hand_in_step(conn: Connection, player_id, step_id: int, answers: dict, now: datetime) -> dict:
    """Hand in a check. It is marked against the company's true figures. Done well, it turns up what is there to find."""
    with conn.transaction():
        state = _open(conn, now)
        seat, empire, step, found, sale = _step_for(conn, player_id, step_id)
        if step["terms"] is None or step["assigned_to"] != player_id:
            raise EmpireError("Open the check first. It is handed in once, by whoever opened it.")
        if not isinstance(answers, dict):
            raise EmpireError("The answers did not arrive in a form that can be read.")
        result = fd.mark({"conn": conn}, step["terms"], answers)
        score = max(0, min(100, int(result["score"])))
        # The right answer is not shown: a check done badly must not tell the empire what it failed to find.
        result = {**result, "lines": [{"label": line["label"], "right": line["right"]} for line in result["lines"]], "words": ""}
        words = _finish_step(conn, empire, found, sale, step, score >= firm.DUTY_PASS, now)
        conn.execute("UPDATE deal_steps SET status = 'done', score = %s, done_by = %s, answers = %s, found = %s, done_at = %s WHERE id = %s",
                     (score, player_id, Jsonb(answers), Jsonb(words), now, step_id))
        if step["step"] == "valuation":
            value = answers.get("value")
            if isinstance(value, int) and not isinstance(value, bool):
                conn.execute("UPDATE deal_files SET valuation = %s WHERE id = %s", (value, found["id"]))
        mine = careers.career(conn, player_id, seat["build"])
        gained = firm.DUTY_EXPERIENCE * score // 100 * (1 + (mine["rank"] if mine else 0))
        if gained and mine:
            careers.add_experience(conn, player_id, seat["build"], gained, now)
        firm.sign_opinion(conn, player_id, seat["build"], empire["id"], f"deal_{step['step']}", f"{STEPS[step['step']][1]}: {sale['company']}",
                          {"file_id": found["id"], "score": score, "found": [w for w in words]}, state["period"], state["period"] + 4, now)
        _log(conn, empire["id"], f"{firm._name(conn, player_id)} did the check \"{STEPS[step['step']][1].lower()}\" on {sale['company']} "
                                 f"(marked {score} out of 100).", now)
        return {"score": score, "result": result, "found": words}


def _finish_step(conn: Connection, empire: dict, found: dict, sale: dict, step: dict, well: bool, now: datetime) -> list[str]:
    """What a check turns up: the secrets on its subject, if it was done well."""
    p = private.profile(conn, sale["company_id"])
    secrets = {s["code"]: s for s in (p["secrets"] if p else []) if not s["done"] or s["code"] in ("dressed_revenue", "worn_assets")}
    words = []
    for code in FINDS_OF.get(step["step"], ()):
        if code in secrets and well:
            _found(conn, empire["id"], sale["company_id"], code, STEPS[step["step"]][1], now)
            words.append(private.SECRET_NAMES[code] + ".")
    if not words:
        words.append("Nothing out of the ordinary was found." if well else "The check was not done well enough to be sure of anything.")
    return words


def _staff_steps(conn: Connection, now: datetime) -> None:
    """At each Closing Bell, the computer-run staff do the checks that have waited a day on a staffed desk
    with no player, and sign the confidentiality agreement where Legal Counsel's desk is staffed."""
    for row in _rows(conn, "SELECT f.* FROM deal_files f JOIN sale_processes s ON s.id = f.process_id WHERE f.status = 'open' AND s.status = 'open'"
                           " ORDER BY f.id"):
        with conn.transaction():
            found = _one(conn, "SELECT * FROM deal_files WHERE id = %s AND status = 'open' FOR UPDATE", (row["id"],))
            if found is None or firm._hours(found["at"], now) < firm.APPROVAL_HOURS:
                continue
            empire = empires._empire(conn, found["empire_id"])
            if not found["nda_at"]:
                if firm.desk_staffed(conn, empire["id"], "investment_banker") and not firm.desk_members(conn, empire["id"], "investment_banker"):
                    _sign_nda(conn, empire, found, None, now)
                continue
            sale = _process(conn, found["process_id"])
            for step in _rows(conn, "SELECT * FROM deal_steps WHERE file_id = %s AND status = 'due' AND terms IS NULL AND firm_id IS NULL FOR UPDATE",
                                (found["id"],)):
                if firm.desk_members(conn, empire["id"], step["build"]) or not firm.desk_staffed(conn, empire["id"], step["build"]):
                    continue
                well = private.roll(private._seed(conn), "staff_check", step["id"]) < STAFF_FINDS_BPS
                words = _finish_step(conn, empire, found, sale, step, well, now)
                conn.execute("UPDATE deal_steps SET status = 'done', score = %s, by_staff = true, found = %s, done_at = %s WHERE id = %s",
                             (firm.STAFF_DUTY_SCORE, Jsonb(words), now, step["id"]))


# ---------------------------------------------------------------------------
# The sale agreement, clause by clause
# ---------------------------------------------------------------------------

def mark_terms(conn: Connection, player_id, file_id: int, changes: dict, now: datetime) -> dict:
    """Legal Counsel strikes out clauses of the seller's draft and asks for protections. The founders
    answer at once, each change at its price. An empire that is selling answers through its own
    Legal Counsel (or its head) before the sale closes; what it has not answered by then is refused."""
    with conn.transaction():
        _open(conn, now)
        seat, empire = _seat(conn, player_id)
        found = _file(conn, empire["id"], file_id, lock=True)
        if not _desk_ok(conn, empire, seat, "investment_banker"):
            raise EmpireError("The sale agreement is negotiated by the empire's Legal Counsel.")
        if not found["nda_at"] or found["status"] != "open":
            raise EmpireError("The agreement can be argued over only while the file is open and the data room signed for.")
        sale = _process(conn, found["process_id"])
        if sale["status"] != "open":
            raise EmpireError("That sale is over.")
        if _one(conn, "SELECT 1 FROM deal_bids WHERE process_id = %s AND empire_id = %s AND status IN ('pending', 'live')",
                (sale["id"], empire["id"])):
            raise EmpireError("Your empire has a bid standing: the agreement is settled. Withdraw the bid to argue it again.")
        if not isinstance(changes, dict) or len(changes) > 20:
            raise EmpireError("Mark each clause: strike or keep, and each protection: ask or not.")
        draft = {r["code"]: r for r in _rows(conn, "SELECT * FROM deal_terms WHERE process_id = %s AND empire_id = %s FOR UPDATE",
                                             (sale["id"], empire["id"]))}
        seller_is_empire = sale["seller_empire_id"] is not None and firm.player_run(empires._empire(conn, sale["seller_empire_id"]))
        for code, what in changes.items():
            if code in CLAUSES and what in ("strike", "keep"):
                row = draft.get(code)
                if row is None:
                    continue
                if what == "strike" and row["status"] == "in":
                    status = "asked" if seller_is_empire else "struck"
                    conn.execute("UPDATE deal_terms SET status = %s, charge_bps = %s, by_player = %s, at = %s WHERE id = %s",
                                 (status, CLAUSES[code][2], player_id, now, row["id"]))
            elif code in PROTECTIONS and what in ("ask", "drop"):
                if what == "ask" and code not in draft:
                    conn.execute("INSERT INTO deal_terms (process_id, empire_id, code, status, charge_bps, by_player, at)"
                                 " VALUES (%s, %s, %s, %s, %s, %s, %s)",
                                 (sale["id"], empire["id"], code, "asked" if seller_is_empire else "agreed", PROTECTIONS[code][1], player_id, now))
            else:
                raise EmpireError("That is not a clause of this agreement.")
        return {"terms": terms_view(conn, sale["id"], empire["id"])}


def answer_terms(conn: Connection, player_id, process_id: int, buyer_empire_id: int, answers: dict, now: datetime) -> dict:
    """The selling empire's Legal Counsel (or its head) agrees or refuses what a buyer asked."""
    with conn.transaction():
        _open(conn, now)
        seat, empire = _seat(conn, player_id)
        sale = _process(conn, process_id, lock=True)
        if sale["seller_empire_id"] != empire["id"] or sale["status"] != "open":
            raise EmpireError("Your empire is not selling that company.")
        if not _desk_ok(conn, empire, seat, "investment_banker") and empire["head_player_id"] != player_id:
            raise EmpireError("A buyer's changes are answered by Legal Counsel or the head.")
        if _one(conn, "SELECT 1 FROM deal_bids WHERE process_id = %s AND empire_id = %s AND status = 'live'", (process_id, buyer_empire_id)):
            raise EmpireError("That buyer has bid: the agreement it bid on is settled.")
        for code, yes in (answers or {}).items():
            row = _one(conn, "SELECT * FROM deal_terms WHERE process_id = %s AND empire_id = %s AND code = %s AND status = 'asked' FOR UPDATE",
                       (process_id, buyer_empire_id, code))
            if row is None or not isinstance(yes, bool):
                continue
            if code in CLAUSES:
                status = "struck" if yes else "refused"
            else:
                status = "agreed" if yes else "refused"
            conn.execute("UPDATE deal_terms SET status = %s, at = %s WHERE id = %s", (status, now, row["id"]))
        return {"terms": terms_view(conn, process_id, buyer_empire_id)}


def terms_view(conn: Connection, process_id, empire_id) -> list[dict]:
    out = []
    for r in _rows(conn, "SELECT * FROM deal_terms WHERE process_id = %s AND empire_id = %s ORDER BY id", (process_id, empire_id)):
        words, trap = (CLAUSES[r["code"]][0], CLAUSES[r["code"]][1]) if r["code"] in CLAUSES else (PROTECTIONS[r["code"]][0], False)
        out.append({"code": r["code"], "words": words, "status": r["status"], "charge_bps": r["charge_bps"],
                    "protection": r["code"] in PROTECTIONS, "escape": trap})
    return out


def in_force(conn: Connection, process_id, empire_id) -> dict:
    """The clauses that bind once the sale completes: those in the draft and not struck, and protections agreed."""
    out = {}
    for r in _rows(conn, "SELECT * FROM deal_terms WHERE process_id = %s AND empire_id = %s", (process_id, empire_id)):
        if r["code"] in CLAUSES:
            out[r["code"]] = r["status"] in ("in", "refused", "asked")
        else:
            out[r["code"]] = r["status"] == "agreed"
    return {k: v for k, v in out.items() if v}


def charge_bps(conn: Connection, process_id, empire_id) -> int:
    """What the seller adds to the price for the changes it agreed to."""
    return _one(conn, "SELECT coalesce(sum(charge_bps), 0)::int AS c FROM deal_terms WHERE process_id = %s AND empire_id = %s"
                      " AND status IN ('struck', 'agreed')", (process_id, empire_id))["c"]


# ---------------------------------------------------------------------------
# Partners
# ---------------------------------------------------------------------------

def invite_partner(conn: Connection, head_id, file_id: int, empire_id: int, amount: int, now: datetime) -> dict:
    """The head invites another empire to put money into the bid for a share of the company."""
    with conn.transaction():
        _open(conn, now)
        empire = empires._head(conn, head_id)
        found = _file(conn, empire["id"], file_id, lock=True)
        if found["status"] != "open":
            raise EmpireError("That deal file is closed.")
        if not isinstance(amount, int) or isinstance(amount, bool) or amount < million_naira(100):
            raise EmpireError("A partner puts in at least ₦100 million.")
        partner = _one(conn, "SELECT * FROM empires WHERE id = %s AND status = 'active' AND kind = 'player'", (empire_id,))
        if partner is None or partner["id"] == empire["id"]:
            raise EmpireError("Partners are other empires run by players.")
        sale = _process(conn, found["process_id"])
        if sale["seller_empire_id"] == partner["id"]:
            raise EmpireError("The seller cannot be a partner in buying its own company.")
        bid = _standing_bid(conn, sale["id"], empire["id"])
        if bid:
            raise EmpireError("Invite partners before the bid is placed.")
        pending = _one(conn, "SELECT * FROM deal_bids WHERE process_id = %s AND empire_id = %s AND status = 'pending' AND amount = 1",
                       (sale["id"], empire["id"]))
        holder = pending or _one(conn, "INSERT INTO deal_bids (process_id, empire_id, file_id, amount, status, at) VALUES (%s, %s, %s, 1, 'pending', %s)"
                                       " RETURNING *", (sale["id"], empire["id"], found["id"], now))
        try:
            with conn.transaction():
                row = _one(conn, "INSERT INTO deal_partners (bid_id, account_id, empire_id, amount, at) VALUES (%s, %s, %s, %s, %s) RETURNING id",
                           (holder["id"], partner["account_id"], partner["id"], amount, now))
        except Exception:
            raise EmpireError("That empire is already invited.") from None
        _log(conn, partner["id"], f"{empire['name']} invites the empire to put {_money(amount)} into its bid for {sale['company']}.", now)
        return {"partner_id": row["id"]}


def answer_partner(conn: Connection, head_id, partner_id: int, accept: bool, now: datetime) -> dict:
    """The invited empire's head accepts (its money is held in escrow until the sale is decided) or declines."""
    with conn.transaction():
        state = _open(conn, now)
        empire = empires._head(conn, head_id)
        row = _one(conn, "SELECT * FROM deal_partners WHERE id = %s AND empire_id = %s FOR UPDATE", (partner_id, empire["id"]))
        if row is None or row["status"] != "invited":
            raise EmpireError("There is no such invitation waiting.")
        bid = _one(conn, "SELECT * FROM deal_bids WHERE id = %s FOR UPDATE", (row["bid_id"],))
        if bid["status"] not in ("pending",):
            raise EmpireError("That bid has moved on.")
        if not accept:
            conn.execute("UPDATE deal_partners SET status = 'declined' WHERE id = %s", (partner_id,))
            return {"accepted": False}
        try:
            ledger.transfer(conn, payer=empire["account_id"], receiver=escrow_account(conn), amount=row["amount"], kind="deal_escrow",
                            memo=f"{empire['name']}: held for a partner's share of a bid", period=state["period"], reference=f"partner:{partner_id}")
        except ledger.InsufficientFunds:
            raise EmpireError(f"Pledging needs {_money(row['amount'])} in cash.") from None
        conn.execute("UPDATE deal_partners SET status = 'pledged' WHERE id = %s", (partner_id,))
        _log(conn, empire["id"], f"The empire pledged {_money(row['amount'])} as a partner in a bid. It is held in escrow until the sale is decided.", now)
        return {"accepted": True}


def _standing_bid(conn: Connection, process_id, empire_id) -> dict | None:
    return _one(conn, "SELECT * FROM deal_bids WHERE process_id = %s AND empire_id = %s AND status = 'live' FOR UPDATE", (process_id, empire_id))


# ---------------------------------------------------------------------------
# Bidding
# ---------------------------------------------------------------------------

def loan_quote(conn: Connection, sale: dict, price: int, period: int) -> dict:
    """What a bank would lend against the company: at most 60% of the price and four years of its true
    earnings (the bank reads the real accounts), at its own rate plus three points."""
    # The bank lends on the papers it is shown, as the buyer does. If they are dressed up, the bank's promises bite later.
    papers = private.papers(conn, sale["company_id"])
    ebitda = sum(r["operating_profit"] + r["depreciation"] for r in papers) * 4 // max(len(papers), 1)
    most = max(min(apply_bps(price, LOAN_MOST_BPS), ebitda * LOAN_EBITDA_X), 0)
    from simulation import firm_money
    bank = firm_money._lender_bank(conn, period, most) if most > 0 else None
    return {"most": most if bank else 0, "rate_bps": _rate_bps(conn, sale["company_id"]) + BUYOUT_SPREAD_BPS,
            "lender": bank["name"] if bank else None, "lender_account": bank["account_id"] if bank else None,
            "covenants": {"debt_x_most": COVENANTS["debt_x_most"], "cover_least_bps": COVENANTS["cover_least_bps"]}}


def mezzanine_quote(conn: Connection, sale: dict, price: int, loan: int) -> dict:
    """What the pension funds lend after the bank: up to a fifth of the price (and the bank's loan and theirs together no
    more than four fifths), at the bank's rate plus six points, with warrants for 5% of the company used at once."""
    most = max(min(apply_bps(price, data.MEZZ_MOST_BPS), apply_bps(price, data.MEZZ_WITH_LOAN_MOST_BPS) - loan), 0)
    return {"most": most, "rate_bps": _rate_bps(conn, sale["company_id"]) + BUYOUT_SPREAD_BPS + data.MEZZ_EXTRA_BPS,
            "equity_bps": data.MEZZ_EQUITY_BPS}


def place_bid(conn: Connection, head_id, file_id: int, amount: int, loan: int, now: datetime, *, mezzanine: int = 0,
              earnout: int = 0) -> dict:
    """The head bids. A deal needs all three: the Banker brought it, the Accountant has checked the
    accounts, the Risk Manager has signed the stress test (and a banker the fairness opinion, for a
    large deal). The empire's part of the price is held in escrow while the bid stands."""
    with conn.transaction():
        state = _open(conn, now)
        empire = empires._head(conn, head_id)
        if not firm.player_run(empire):
            raise EmpireError("Only an empire run by players bids this way.")
        found = _file(conn, empire["id"], file_id, lock=True)
        sale = _process(conn, found["process_id"], lock=True)
        if sale["status"] != "open" or found["status"] != "open":
            raise EmpireError("That sale is over.")
        conflict = _conflicted(conn, empire["id"], sale["id"])
        if conflict:
            raise EmpireError(f"{conflict}, run from your empire, is working for the seller on this sale. Your empire may not buy it.")
        for value in (amount, loan, mezzanine, earnout):
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise EmpireError("Amounts are whole kobo, nought or more.")
        if amount <= 0:
            raise EmpireError("Name a price.")
        steps = {s["step"]: s for s in _rows(conn, "SELECT * FROM deal_steps WHERE file_id = %s", (file_id,))}
        missing = [STEPS[s][1] for s in NEEDED if steps.get(s, {}).get("status") != "done"]
        if amount > FAIRNESS_ABOVE and steps.get("fairness", {}).get("status") != "done":
            if "fairness" not in steps:
                conn.execute("INSERT INTO deal_steps (file_id, step, build) VALUES (%s, 'fairness', 'investment_banker') ON CONFLICT DO NOTHING", (file_id,))
            missing.append(STEPS["fairness"][1])
        if missing:
            raise EmpireError("A deal needs all three: the Banker brings it, the Accountant checks it, the Risk Manager signs its risks. "
                              "Still to do: " + ", ".join(missing) + ".")
        live = _standing_bid(conn, sale["id"], empire["id"])
        if sale["mode"] == "sealed" and live:
            raise EmpireError("A sealed bid is made once. Withdraw it first to bid again.")
        if sale["mode"] == "auction":
            least = max(sale["asking"] * 80 // 100, apply_bps(sale["highest"] or 0, BPS + AUCTION_STEP_BPS))
            if amount < least:
                raise EmpireError(f"At this auction a bid must be at least {_money(least)}.")
        charge = apply_bps(amount, charge_bps(conn, sale["id"], empire["id"]))
        price = amount + charge
        worth = private.value_of(conn, sale["company_id"]) * sale["shares"] // max(ledger.amount_in_existence(
            conn, _one(conn, "SELECT share_asset FROM companies WHERE id = %s", (sale["company_id"],))["share_asset"]), 1)
        if price * BPS > max(worth, sale["asking"]) * OVERPAY_MOST_BPS // BPS * BPS:
            raise EmpireError("No board would let a price that high through: it is far above both the asking price and what the "
                              "company is worth.")
        pending = _one(conn, "SELECT * FROM deal_bids WHERE process_id = %s AND empire_id = %s AND status = 'pending' FOR UPDATE",
                       (sale["id"], empire["id"]))
        holder = live or pending
        partners = sum(r["amount"] for r in _rows(conn, "SELECT amount FROM deal_partners WHERE bid_id = %s AND status = 'pledged' FOR UPDATE",
                                                  (holder["id"],))) if holder else 0
        quote = loan_quote(conn, sale, price, state["period"])
        if loan > quote["most"]:
            raise EmpireError("No bank will lend that much against this company at this price. See the bank's offer in the file.")
        mezz = mezzanine_quote(conn, sale, price, loan)
        if mezzanine > mezz["most"]:
            raise EmpireError(f"The pension funds lend at most {_money(mezz['most'])} after the bank on this deal.")
        if earnout > apply_bps(price, data.EARNOUT_MOST_BPS):
            raise EmpireError(f"At most {data.EARNOUT_MOST_BPS // 100}% of the price may be paid later, against the company's results.")
        if sale["seller_empire_id"] and earnout:
            raise EmpireError("An earn-out is agreed only with a seller the computer runs.")
        from simulation import firm_money
        promised = _one(conn, "SELECT coalesce(sum(loan), 0)::bigint AS n FROM deal_bids WHERE empire_id = %s AND status = 'live' AND process_id <> %s",
                        (empire["id"], sale["id"]))["n"]
        if loan + promised > firm_money.gearing_room(conn, empire, now) + price // 2:
            raise EmpireError("With this loan the empire would owe more than its rules allow.")
        equity = price - loan - mezzanine - earnout - partners
        if equity < 0:
            raise EmpireError("The partners and the loan come to more than the price. Bid more, or borrow less.")
        if (mezzanine or earnout) and equity + partners < apply_bps(price, data.DEAL_LEAST_EQUITY_BPS):
            raise EmpireError(f"With mezzanine or an earn-out, the buyers must still put in at least {data.DEAL_LEAST_EQUITY_BPS // 100}% "
                              f"of the price in cash ({_money(apply_bps(price, data.DEAL_LEAST_EQUITY_BPS))}).")
        top_up = equity - (live["held"] if live else 0)
        if top_up > 0:
            try:
                ledger.transfer(conn, payer=empire["account_id"], receiver=escrow_account(conn), amount=top_up, kind="deal_escrow",
                                memo=f"{empire['name']}: held while its bid for {sale['company']} stands", period=state["period"],
                                reference=f"process:{sale['id']}")
            except ledger.InsufficientFunds:
                raise EmpireError(f"The empire's part of the price is {_money(equity)}, held while the bid stands. It has not the cash.") from None
        signed = {"banker": str(found["brought_by"]) if found["brought_by"] else "staff",
                  "asset_manager": str(steps["accounts"]["done_by"]) if steps["accounts"]["done_by"] else "staff",
                  "risk_manager": str(steps["stress"]["done_by"]) if steps["stress"]["done_by"] else "staff", "head": str(head_id)}
        if live:
            conn.execute("UPDATE deal_bids SET amount = %s, clause_charge = %s, equity = %s, loan = %s, lender_account = %s, loan_rate_bps = %s,"
                         " covenants = %s, held = %s, signed_by = %s, at = %s, mezzanine = %s, mezz_rate_bps = %s, earnout = %s WHERE id = %s",
                         (amount, charge, equity, loan, quote["lender_account"] if loan else None, quote["rate_bps"], Jsonb(quote["covenants"]),
                          equity, Jsonb(signed), now, mezzanine, mezz["rate_bps"], earnout, live["id"]))
            bid_id = live["id"]
        elif pending:
            conn.execute("UPDATE deal_bids SET amount = %s, clause_charge = %s, equity = %s, loan = %s, lender_account = %s, loan_rate_bps = %s,"
                         " covenants = %s, held = %s, signed_by = %s, status = 'live', at = %s, mezzanine = %s, mezz_rate_bps = %s, earnout = %s"
                         " WHERE id = %s",
                         (amount, charge, equity, loan, quote["lender_account"] if loan else None, quote["rate_bps"], Jsonb(quote["covenants"]),
                          equity, Jsonb(signed), now, mezzanine, mezz["rate_bps"], earnout, pending["id"]))
            bid_id = pending["id"]
        else:
            bid_id = _one(conn, "INSERT INTO deal_bids (process_id, empire_id, file_id, amount, clause_charge, equity, loan, lender_account, loan_rate_bps,"
                                " covenants, held, status, signed_by, at, mezzanine, mezz_rate_bps, earnout) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s,"
                                " %s, %s, 'live', %s, %s, %s, %s, %s) RETURNING id",
                          (sale["id"], empire["id"], file_id, amount, charge, equity, loan, quote["lender_account"] if loan else None,
                           quote["rate_bps"], Jsonb(quote["covenants"]), equity, Jsonb(signed), now, mezzanine, mezz["rate_bps"], earnout))["id"]
        if top_up < 0:
            ledger.transfer(conn, payer=escrow_account(conn), receiver=empire["account_id"], amount=-top_up, kind="deal_escrow_back",
                            memo=f"{empire['name']}: escrow handed back as its bid changed", period=state["period"], reference=f"bid:{bid_id}")
        if sale["mode"] == "auction":
            conn.execute("UPDATE sale_processes SET highest = %s WHERE id = %s", (amount, sale["id"]))
        firm.ceo_note(conn, head_id, empire["id"], "deal_bid", f"Bid {_money(amount)} for {sale['company']}" + (f", {_money(loan)} of it borrowed" if loan else ""),
                      state["period"], now, reference=f"bid:{bid_id}")
        _log(conn, empire["id"], f"The head bid {_money(amount)} for {sale['company']} {_how(sale)}"
                                 + (f" (the seller adds {_money(charge)} for the clauses changed)" if charge else "") + ".", now)
        return {"bid_id": bid_id, "price": price, "equity": equity, "loan": loan, "partners": partners, "mezzanine": mezzanine,
                "earnout": earnout}


def withdraw_bid(conn: Connection, head_id, file_id: int, now: datetime) -> None:
    """A sealed bid may be withdrawn before the sale closes; an auction bid stands."""
    with conn.transaction():
        state = _open(conn, now)
        empire = empires._head(conn, head_id)
        found = _file(conn, empire["id"], file_id, lock=True)
        sale = _process(conn, found["process_id"], lock=True)
        live = _standing_bid(conn, sale["id"], empire["id"])
        if live is None:
            raise EmpireError("There is no bid standing.")
        if sale["mode"] == "auction":
            raise EmpireError("A bid at auction cannot be withdrawn.")
        _release(conn, live, "withdrawn", state["period"])


def _release(conn: Connection, bid: dict, status: str, period: int) -> None:
    """Hand back what a bid held in escrow: the empire's part, and each partner's pledge."""
    empire = empires._empire(conn, bid["empire_id"])
    if bid["held"] > 0:
        ledger.transfer(conn, payer=escrow_account(conn), receiver=empire["account_id"], amount=bid["held"], kind="deal_escrow_back",
                        memo=f"{empire['name']}: escrow handed back ({status})", period=period, reference=f"bid:{bid['id']}")
    for row in _rows(conn, "SELECT * FROM deal_partners WHERE bid_id = %s AND status = 'pledged' FOR UPDATE", (bid["id"],)):
        ledger.transfer(conn, payer=escrow_account(conn), receiver=row["account_id"], amount=row["amount"], kind="deal_escrow_back",
                        memo="A partner's pledge handed back", period=period, reference=f"partner:{row['id']}")
        conn.execute("UPDATE deal_partners SET status = 'returned' WHERE id = %s", (row["id"],))
    conn.execute("UPDATE deal_bids SET status = %s, held = 0 WHERE id = %s", (status, bid["id"]))


def _computer_bidders(conn: Connection, sale: dict, period: int) -> list[dict]:
    """The computer-run empires bid too: what they think it is worth, give or take, within their cash."""
    worth = private.value_of(conn, sale["company_id"]) * sale["shares"] // max(
        ledger.amount_in_existence(conn, _one(conn, "SELECT share_asset FROM companies WHERE id = %s", (sale["company_id"],))["share_asset"]), 1)
    seed = private._seed(conn)
    out = []
    for e in _rows(conn, "SELECT * FROM empires WHERE kind = 'computer' AND status = 'active' ORDER BY id"):
        if e["id"] == sale["seller_empire_id"]:
            continue
        r = private.roll(seed, "computer_bid", sale["id"], e["id"])
        if r % 3 == 0:
            continue                                    # not interested
        offer = apply_bps(apply_bps(worth, 7500 + r % 2500), BPS + (sale.get("pitch_bps") or 0))   # a pitch book that holds up lifts it
        cash = ledger.balance(conn, e["account_id"])
        if offer <= 0 or offer > apply_bps(cash, COMPUTER_BID_CASH_BPS):
            continue
        out.append({"empire": e, "account": e["account_id"], "name": e["name"], "amount": offer, "order": e["id"]})
    # The pension funds buy private companies too, for the long run, at a little below what they are worth.
    funds = ledger.account_id(conn, ledger.INVESTORS_INSTITUTIONS)
    r = private.roll(seed, "funds_bid", sale["id"])
    offer = apply_bps(apply_bps(worth, 8000 + r % 1500), BPS + (sale.get("pitch_bps") or 0))
    if r % 2 == 0 and 0 < offer <= ledger.balance(conn, funds) // 2 and sale["seller_account"] != funds:
        out.append({"empire": None, "account": funds, "name": "The pension funds", "amount": offer, "order": 0})
    return out


def _bell_auctions(conn: Connection, now: datetime) -> None:
    """At each Closing Bell, a computer-run empire still keen raises an auction's highest bid by a step."""
    for sale in _rows(conn, "SELECT * FROM sale_processes WHERE status = 'open' AND mode = 'auction' ORDER BY id"):
        with conn.transaction():
            sale = _one(conn, "SELECT s.*, c.name AS company FROM sale_processes s JOIN companies c ON c.id = s.company_id"
                              " WHERE s.id = %s AND s.status = 'open' FOR UPDATE OF s", (sale["id"],))
            if sale is None:
                continue
            keen = [b for b in _computer_bidders(conn, sale, sale["opened_period"])
                    if b["amount"] > apply_bps(sale["highest"] or 0, BPS + AUCTION_STEP_BPS)]
            if keen:
                step = max(apply_bps(sale["highest"] or sale["asking"] * 80 // 100, BPS + AUCTION_STEP_BPS), sale["asking"] * 80 // 100)
                conn.execute("UPDATE sale_processes SET highest = %s WHERE id = %s", (min(step, max(b["amount"] for b in keen)), sale["id"]))


# ---------------------------------------------------------------------------
# Deciding a sale as the quarter closes, and completing it
# ---------------------------------------------------------------------------

def decide_sales(conn: Connection, period: int, now: datetime) -> None:
    for row in _rows(conn, "SELECT id FROM sale_processes WHERE status = 'open' AND closes_period <= %s ORDER BY id", (period,)):
        with conn.transaction():
            sale = _one(conn, "SELECT s.*, c.name AS company, c.ticker, c.sector, c.share_asset, c.status AS company_status FROM sale_processes s"
                              " JOIN companies c ON c.id = s.company_id WHERE s.id = %s AND s.status = 'open' FOR UPDATE OF s", (row["id"],))
            if sale is None:
                continue
            _decide(conn, sale, period, now)


def _decide(conn: Connection, sale: dict, period: int, now: datetime) -> None:
    bids = _rows(conn, "SELECT * FROM deal_bids WHERE process_id = %s AND status = 'live' ORDER BY amount + clause_charge DESC, at, id FOR UPDATE",
                 (sale["id"],))
    computers = [] if sale["company_status"] != "trading" else _computer_bidders(conn, sale, period)
    if sale["mode"] == "auction":
        # At auction the computer-run bidders go no higher than they have bid at the bells.
        computers = [{**c, "amount": min(c["amount"], sale["highest"] or 0)} for c in computers if (sale["highest"] or 0) > 0]
    best_player = bids[0] if bids else None
    best_computer = max(computers, key=lambda c: (c["amount"], -c["order"]), default=None)
    seller_has = ledger.balance(conn, sale["seller_account"], sale["share_asset"])
    winner = None
    # The seller counts an earn-out at only part of its face: it may never be paid.
    def counted(bid: dict) -> int:
        return bid["amount"] - apply_bps(bid["earnout"], BPS - data.EARNOUT_SELLER_COUNTS_BPS)
    if best_player:
        best_player = max(bids, key=lambda b: (counted(b) + b["clause_charge"], -b["id"]))
    if best_player and counted(best_player) + best_player["clause_charge"] >= sale["reserve"] and (
            best_computer is None or counted(best_player) >= best_computer["amount"]):
        winner = ("player", best_player)
    elif best_computer and best_computer["amount"] >= sale["reserve"]:
        winner = ("computer", best_computer)
    if seller_has < sale["shares"] or sale["company_status"] != "trading":
        winner = None
    for bid in bids:
        if winner and winner[0] == "player" and bid["id"] == winner[1]["id"]:
            continue
        _release(conn, bid, "lost", period)
        conn.execute("UPDATE deal_files SET status = 'lost' WHERE id = %s", (bid["file_id"],))
    for pending in _rows(conn, "SELECT * FROM deal_bids WHERE process_id = %s AND status = 'pending' FOR UPDATE", (sale["id"],)):
        _release(conn, pending, "withdrawn", period)
    if winner is None:
        conn.execute("UPDATE sale_processes SET status = 'failed', outcome = %s WHERE id = %s",
                     ("No bid reached the price the seller would take.", sale["id"]))
        conn.execute("UPDATE deal_files SET status = 'lost' WHERE process_id = %s AND status = 'open'", (sale["id"],))
        return
    if winner[0] == "player":
        _complete(conn, sale, winner[1], period, now)
    else:
        _complete_computer(conn, sale, winner[1], period, now)
    conn.execute("UPDATE deal_files SET status = 'lost' WHERE process_id = %s AND status = 'open'", (sale["id"],))


def _pay_seller(conn: Connection, sale: dict, price: int, escrow: int, payer, period: int, reference: str) -> None:
    ledger.transfer(conn, payer=payer, receiver=sale["seller_account"], amount=price - escrow, kind="company_sale",
                    memo=f"The price of {sale['company']}" + (f", less {_money(escrow)} held back against claims" if escrow else ""),
                    period=period, reference=reference)


def _complete(conn: Connection, sale: dict, bid: dict, period: int, now: datetime) -> None:
    """Money, loan and shares move together. The empire and each partner own shares in proportion to what they put in."""
    empire = empires._empire(conn, bid["empire_id"], lock=True)
    price = bid["amount"] + bid["clause_charge"]
    terms = in_force(conn, sale["id"], empire["id"])
    escrow = apply_bps(price, ESCROW_BPS) if terms.get("escrow") else 0
    pot = escrow_account(conn)
    reference = f"process:{sale['id']}"
    if bid["mezzanine"] > 0 and ledger.balance(conn, ledger.account_id(conn, ledger.INVESTORS_INSTITUTIONS)) < bid["mezzanine"]:
        # The pension funds can no longer lend the mezzanine: the deal falls through, and everything held is handed back.
        _release(conn, bid, "lost", period)
        conn.execute("UPDATE sale_processes SET status = 'failed', outcome = %s WHERE id = %s",
                     ("The winning bidder's mezzanine lender could no longer lend. The sale fell through.", sale["id"]))
        conn.execute("UPDATE deal_files SET status = 'lost' WHERE id = %s", (bid["file_id"],))
        _log(conn, empire["id"], f"The pension funds could no longer lend the mezzanine: the purchase of {sale['company']} fell through.", now)
        return
    if bid["loan"] > 0:
        lender = _one(conn, "SELECT a.id, c.name FROM ledger_accounts a LEFT JOIN companies c ON c.account_id = a.id WHERE a.id = %s",
                      (bid["lender_account"],))
        banks = {b["account_id"]: b for b in banking.banks(conn, period)}
        bank = banks.get(bid["lender_account"])
        if bank is None or ledger.balance(conn, bank["account_id"]) - banking.reserve(bank) < bid["loan"] or banking.lending_room(bank) < bid["loan"]:
            # The bank can no longer lend it: the deal falls through, and everything held is handed back.
            _release(conn, bid, "lost", period)
            conn.execute("UPDATE sale_processes SET status = 'failed', outcome = %s WHERE id = %s",
                         ("The winning bidder's bank could no longer lend the money. The sale fell through.", sale["id"]))
            conn.execute("UPDATE deal_files SET status = 'lost' WHERE id = %s", (bid["file_id"],))
            _log(conn, empire["id"], f"The bank could no longer lend what was promised: the purchase of {sale['company']} fell through.", now)
            return
        ledger.transfer(conn, payer=bank["account_id"], receiver=pot, amount=bid["loan"], kind="empire_borrowing",
                        memo=f"{empire['name']}: a buyout loan from {lender['name']} for {sale['company']}", period=period, reference=reference)
        _one(conn, "INSERT INTO empire_debts (empire_id, kind, lender_account, lender_name, principal, outstanding, rate_bps, taken_period,"
                          " due_period, company_id, covenants, signed_by, at) VALUES (%s, 'buyout', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING *",
                    (empire["id"], bank["account_id"], lender["name"], bid["loan"], bid["loan"], bid["loan_rate_bps"], period, period + 20,
                     sale["company_id"], Jsonb(bid["covenants"]), empire["head_player_id"], now))
    mezz_lender = None
    if bid["mezzanine"] > 0:
        mezz_lender = ledger.account_id(conn, ledger.INVESTORS_INSTITUTIONS)
        ledger.transfer(conn, payer=mezz_lender, receiver=pot, amount=bid["mezzanine"], kind="empire_borrowing",
                        memo=f"{empire['name']}: mezzanine from the pension funds for {sale['company']}", period=period, reference=reference)
        _one(conn, "INSERT INTO empire_debts (empire_id, kind, lender_account, lender_name, principal, outstanding, rate_bps, taken_period,"
                   " due_period, company_id, signed_by, at) VALUES (%s, 'mezzanine', %s, 'The pension funds (mezzanine)', %s, %s, %s, %s, %s, %s,"
                   " %s, %s) RETURNING id",
             (empire["id"], mezz_lender, bid["mezzanine"], bid["mezzanine"], bid["mezz_rate_bps"], period, period + 24, sale["company_id"],
              empire["head_player_id"], now))
    _pay_seller(conn, sale, price - bid["earnout"], escrow, pot, period, reference)
    adviser_fee = firm_practice().mandate_fee(conn, sale, price, period, now)        # the advisory firm that ran the sale, from the seller
    partners = _rows(conn, "SELECT * FROM deal_partners WHERE bid_id = %s AND status = 'pledged' FOR UPDATE", (bid["id"],))
    given = 0
    legs = []
    for row in partners:
        part = sale["shares"] * row["amount"] // price
        given += part
        legs.append((row["account_id"], part))
        conn.execute("UPDATE deal_partners SET status = 'used' WHERE id = %s", (row["id"],))
    if mezz_lender is not None:
        kicker = sale["shares"] * data.MEZZ_EQUITY_BPS // BPS          # the mezzanine's warrants, used at once
        given += kicker
        legs.append((mezz_lender, kicker))
    legs.insert(0, (empire["account_id"], sale["shares"] - given))
    for account, shares in legs:
        if shares > 0:
            ledger.transfer(conn, payer=sale["seller_account"], receiver=account, amount=shares, asset=sale["share_asset"], kind="company_sale",
                            memo=f"{sale['company']}: shares bought", period=period, reference=reference)
    conditions = {str(a["id"]): a["condition_bps"] for a in private.assets(conn, sale["company_id"])}
    deal = _one(conn, "INSERT INTO deals (process_id, bid_id, company_id, empire_id, seller_account, price, shares, escrow_account, escrow,"
                      " escrow_until, terms, conditions, period, at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING *",
                (sale["id"], bid["id"], sale["company_id"], empire["id"], sale["seller_account"], price, sale["shares"], pot, escrow,
                 period + (1 if terms.get("short_window") else CLAIM_WINDOW), Jsonb(terms), Jsonb(conditions), period, now))
    if bid["earnout"] > 0:
        # Part of the price is paid later: in full a year on, if the company's sales over that year reach the target.
        papers = private.papers(conn, sale["company_id"])
        recent = papers[-4:]
        yearly = sum(r["revenue"] for r in recent) * 4 // max(len(recent), 1)
        conn.execute("INSERT INTO deal_earnouts (deal_id, empire_id, seller_account, amount, target_sales, from_period, due_period, at)"
                     " VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                     (deal["id"], empire["id"], sale["seller_account"], bid["earnout"], yearly * data.EARNOUT_TARGET_BPS // BPS, period + 1,
                      period + data.EARNOUT_QUARTERS, now))
    conn.execute("UPDATE deal_bids SET status = 'won', held = 0 WHERE id = %s", (bid["id"],))
    conn.execute("UPDATE deal_files SET status = 'won' WHERE id = %s", (bid["file_id"],))
    conn.execute("UPDATE sale_processes SET status = 'sold', winner_bid = %s, price = %s, outcome = %s WHERE id = %s",
                 (bid["id"], price, f"Sold to {empire['name']} for {_money(price)}.", sale["id"]))
    add_stake(conn, sale["company_id"], empire["id"], price - sum(r["amount"] for r in partners), period)
    for row in partners:
        if row["empire_id"]:
            add_stake(conn, sale["company_id"], row["empire_id"], row["amount"], period)
    if sale["seller_empire_id"]:
        from simulation import firm_owned
        firm_owned.exited(conn, sale["seller_empire_id"], sale["company_id"], "to_empire", price - escrow - adviser_fee, period, now)
    _take_control(conn, sale["company_id"], period, now, deal_id=deal["id"])
    _book_purchase(conn, empire, sale, price - sum(r["amount"] for r in partners), period, now)
    for code in ("dressed_revenue", "worn_assets"):
        p = private.profile(conn, sale["company_id"])
        if any(s["code"] == code for s in p["secrets"]):
            _found(conn, empire["id"], sale["company_id"], code, "Learnt on taking over the books", now)
    private._news(conn, period + 1, 2, "private_deal", f"deal:{deal['id']}",
                  {"buyer": empire["name"], "company": sale["company"], "amount": _money(price), "how": "after sealed bids" if sale["mode"] == "sealed" else "at auction"})
    _log(conn, empire["id"], f"The empire bought {sale['company']} for {_money(price)}"
                             + (f", {_money(bid['loan'])} of it borrowed against the company" if bid["loan"] else "")
                             + (f". {_money(escrow)} is held back from the seller against claims until {clock.period_label(deal['escrow_until'])}" if escrow else "")
                             + ".", now)
    for member in empires.humans(conn, empire["id"]):
        careers._event(conn, member["player_id"], member["build"], "deal", f"{empire['name']} bought {sale['company']} for {_money(price)}.", now)
    leagues.award(conn, empire["id"], 2, f"Bought {sale['company']}", period, now, reference=f"deal:{deal['id']}")


def _book_purchase(conn: Connection, empire: dict, sale: dict, paid: int, period: int, now: datetime) -> None:
    """The purchase is on the empire's books as an investment, not a cost."""
    _log(conn, empire["id"], f"Investment: {sale['company']}, {_money(paid)} of the empire's own money and its loan.", now)


def _complete_computer(conn: Connection, sale: dict, winner: dict, period: int, now: datetime) -> None:
    """A computer-run buyer won (an empire the computer runs, or the pension funds): it pays from its cash and owns the company."""
    empire = winner["empire"]
    price = winner["amount"]
    reference = f"process:{sale['id']}"
    ledger.transfer(conn, payer=winner["account"], receiver=sale["seller_account"], amount=price, kind="company_sale",
                    memo=f"The price of {sale['company']}", period=period, reference=reference)
    ledger.transfer(conn, payer=sale["seller_account"], receiver=winner["account"], amount=sale["shares"], asset=sale["share_asset"],
                    kind="company_sale", memo=f"{sale['company']}: shares bought", period=period, reference=reference)
    conn.execute("UPDATE sale_processes SET status = 'sold', price = %s, outcome = %s WHERE id = %s",
                 (price, f"Sold to {winner['name']} for {_money(price)}.", sale["id"]))
    adviser_fee = firm_practice().mandate_fee(conn, sale, price, period, now)
    if empire:
        add_stake(conn, sale["company_id"], empire["id"], price, period)
    if sale["seller_empire_id"]:
        from simulation import firm_owned
        firm_owned.exited(conn, sale["seller_empire_id"], sale["company_id"], "to_empire", price - adviser_fee, period, now)
    _take_control(conn, sale["company_id"], period, now)
    private._news(conn, period + 1, 2, "private_deal", f"deal:computer:{sale['id']}",
                  {"buyer": winner["name"], "company": sale["company"], "amount": _money(price),
                   "how": "after sealed bids" if sale["mode"] == "sealed" else "at auction"})


def add_stake(conn: Connection, company_id, empire_id, cost: int, period: int) -> None:
    """What an empire paid for its shares of a company, added to what it paid before."""
    conn.execute("INSERT INTO company_stakes (company_id, empire_id, cost, since_period) VALUES (%s, %s, %s, %s)"
                 " ON CONFLICT (company_id, empire_id) DO UPDATE SET cost = company_stakes.cost + excluded.cost", (company_id, empire_id, cost, period))


def _take_control(conn: Connection, company_id, period: int, now: datetime, *, deal_id=None) -> None:
    """The empire holding the most shares of a company controls it. Its cost is what it paid for its stake.
    An empire that keeps control keeps its row (and the day it took control)."""
    company = _one(conn, "SELECT share_asset, listed, status FROM companies WHERE id = %s", (company_id,))
    holders = _rows(conn, "SELECT e.id, b.balance FROM ledger_balances b JOIN empires e ON e.account_id = b.account_id"
                          " WHERE b.asset = %s AND b.balance > 0 ORDER BY b.balance DESC, e.id", (company["share_asset"],))
    now_row = _one(conn, "SELECT * FROM owned_companies WHERE company_id = %s", (company_id,))
    top = holders[0]["id"] if holders and not company["listed"] and company["status"] == "trading" else None
    if now_row and now_row["empire_id"] == top:
        return
    conn.execute("DELETE FROM owned_companies WHERE company_id = %s", (company_id,))
    if top is None:
        return
    stake = _one(conn, "SELECT cost FROM company_stakes WHERE company_id = %s AND empire_id = %s", (company_id, top))
    conn.execute("INSERT INTO owned_companies (company_id, empire_id, bought_period, cost, deal_id, since) VALUES (%s, %s, %s, %s, %s, %s)",
                 (company_id, top, period, stake["cost"] if stake else 0, deal_id, now))


# ---------------------------------------------------------------------------
# Claims against the seller
# ---------------------------------------------------------------------------

def claim(conn: Connection, player_id, deal_id: int, code: str, now: datetime) -> dict:
    """Legal Counsel (or the head) claims against the seller for a promise that turned out false. The
    promise must be in force (no "as is" clause), the claim made in time, and the truth now known to the empire."""
    with conn.transaction():
        state = _open(conn, now)
        seat, empire = _seat(conn, player_id)
        if not _desk_ok(conn, empire, seat, "investment_banker") and empire["head_player_id"] != player_id:
            raise EmpireError("A claim is made by Legal Counsel or the head.")
        deal = _one(conn, "SELECT * FROM deals WHERE id = %s AND empire_id = %s FOR UPDATE", (deal_id, empire["id"]))
        if deal is None:
            raise EmpireError("Your empire made no such purchase.")
        if code not in WARRANTY_OF:
            raise EmpireError("No promise in the agreement covers that.")
        if _one(conn, "SELECT 1 FROM deal_claims WHERE deal_id = %s AND code = %s", (deal_id, code)):
            raise EmpireError("That claim has been made.")
        known = _one(conn, "SELECT * FROM deal_finds WHERE empire_id = %s AND company_id = %s AND code = %s", (empire["id"], deal["company_id"], code))
        if not known:
            raise EmpireError("The empire cannot claim what it does not know: nothing shows that promise was false.")
        shown = _one(conn, "SELECT at FROM deal_shown WHERE empire_id = %s AND company_id = %s AND code = %s", (empire["id"], deal["company_id"], code))
        if known["at"] < deal["at"] or (shown and shown["at"] < deal["at"]):
            raise EmpireError("The empire's own checks put this in front of it before it bought. A buyer cannot claim for what it priced in.")
        p = private.profile(conn, deal["company_id"])
        secret = next((s for s in p["secrets"] if s["code"] == code), None) if p else None
        terms = deal["terms"]
        words, amount = "", 0
        if secret is None:
            words = "The promise was true. The claim is refused."
        elif terms.get("as_is"):
            words = "The agreement says the company was taken as it stood. Nothing can be claimed."
        elif not terms.get(WARRANTY_OF[code]):
            words = "That promise was struck out of the agreement. Nothing can be claimed."
        elif code == "ownership_claim" and terms.get("title_indemnity") and secret["done"]:
            words = "The seller has already made good the partner's claim under its indemnity. Nothing more can be claimed."
        elif state["period"] > deal["escrow_until"]:
            words = "The time for claims has passed."
        else:
            amount = _harm(conn, deal, secret)
            if terms.get("claim_cap"):
                amount = min(amount, apply_bps(deal["price"], 100))
        paid = 0
        if amount > 0:
            from_escrow = min(amount, deal["escrow"])
            if from_escrow:
                ledger.transfer(conn, payer=deal["escrow_account"], receiver=empire["account_id"], amount=from_escrow, kind="deal_claim",
                                memo="A claim paid from the money held back", period=state["period"], reference=f"deal:{deal_id}")
                conn.execute("UPDATE deals SET escrow = escrow - %s WHERE id = %s", (from_escrow, deal_id))
            rest = ledger.pay_up_to(conn, payer=deal["seller_account"], receiver=empire["account_id"], wanted=amount - from_escrow,
                                    kind="deal_claim", memo="A claim paid by the seller", period=state["period"], reference=f"deal:{deal_id}")
            paid = from_escrow + rest
            words = f"The seller's promise was false. {_money(paid)} was paid" + (f" of {_money(amount)} claimed" if paid < amount else "") + "."
        conn.execute("INSERT INTO deal_claims (deal_id, code, amount, paid, status, words, by_player, at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                     (deal_id, code, amount, paid, "paid" if paid else "refused", words, player_id, now))
        _log(conn, empire["id"], f"A claim against the seller of a company: {words}", now)
        return {"amount": amount, "paid": paid, "words": words}


def _harm(conn: Connection, deal: dict, secret: dict) -> int:
    """What a false promise cost the buyer."""
    if secret["code"] == "dressed_revenue":
        return deal["price"] * secret["bps"] // (BPS + secret["bps"])
    if secret["code"] == "hidden_debt":
        return secret["amount"]
    if secret["code"] == "worn_assets":
        at_sale = deal["conditions"] or {}
        return sum(a["cost"] * max((a["stated_bps"] or 0) - at_sale.get(str(a["id"]), a["stated_bps"] or 0), 0) // BPS
                   for a in private.assets(conn, deal["company_id"], all_=True) if a["bought_period"] < deal["period"])
    if secret["code"] == "ownership_claim":
        return apply_bps(deal["price"], secret["bps"])
    return 0


def _release_escrow(conn: Connection, period: int, now: datetime) -> None:
    """Money held back is paid on to the seller once the time for claims is over."""
    for deal in _rows(conn, "SELECT * FROM deals WHERE escrow > 0 AND escrow_until < %s FOR UPDATE", (period + 1,)):
        if deal["escrow_until"] > period:
            continue
        ledger.transfer(conn, payer=deal["escrow_account"], receiver=deal["seller_account"], amount=deal["escrow"], kind="company_sale",
                        memo="Money held back against claims, paid on as the time for claims ended", period=period, reference=f"deal:{deal['id']}")
        conn.execute("UPDATE deals SET escrow = 0 WHERE id = %s", (deal["id"],))
        seller = _one(conn, "SELECT id FROM empires WHERE account_id = %s", (deal["seller_account"],))
        if seller:
            conn.execute("UPDATE deal_exits SET proceeds = proceeds + %s, gain = gain + %s WHERE id = (SELECT id FROM deal_exits WHERE empire_id = %s"
                         " AND company_id = %s AND kind = 'to_empire' ORDER BY id DESC LIMIT 1)", (deal["escrow"], deal["escrow"], seller["id"], deal["company_id"]))


def _ownership_claims(conn: Connection, period: int, now: datetime) -> None:
    """A former partner's claim on a company that was sold comes to court the quarter after: the buyers hand
    over the shares claimed. With the seller's indemnity, the seller pays them their worth."""
    for deal in _rows(conn, "SELECT * FROM deals WHERE period = %s - 1", (period,)):
        p = private.profile(conn, deal["company_id"])
        secret = next((s for s in (p["secrets"] if p else []) if s["code"] == "ownership_claim" and not s["done"]), None)
        if secret is None:
            continue
        company = _one(conn, "SELECT * FROM companies WHERE id = %s", (deal["company_id"],))
        founders = ledger.account_id(conn, ledger.INVESTORS_FOUNDERS)
        empire = empires._empire(conn, deal["empire_id"])
        held = ledger.balance(conn, empire["account_id"], company["share_asset"])
        lost = min(apply_bps(deal["shares"], secret["bps"]), held)
        if lost > 0:
            ledger.transfer(conn, payer=empire["account_id"], receiver=founders, amount=lost, asset=company["share_asset"], kind="ownership_claim",
                            memo=f"{company['name']}: shares handed to a former partner who proved a claim", period=period)
        words = f"A former partner proved a claim to part of {company['name']}: {lost:,} shares were handed over."
        if deal["terms"].get("title_indemnity") and lost:
            worth = private.value_of(conn, company["id"]) * lost // max(ledger.amount_in_existence(conn, company["share_asset"]), 1)
            paid = ledger.pay_up_to(conn, payer=deal["seller_account"], receiver=empire["account_id"], wanted=worth, kind="deal_claim",
                                    memo="The seller makes good a claim on the company's ownership", period=period, reference=f"deal:{deal['id']}")
            words += f" Under the seller's indemnity, the seller paid {_money(paid)} for them."
        secret["done"] = True
        conn.execute("UPDATE private_profiles SET secrets = %s WHERE company_id = %s", (Jsonb(p["secrets"]), company["id"]))
        _found(conn, empire["id"], company["id"], "ownership_claim", "Came to court", now)
        _log(conn, empire["id"], words, now)
        _take_control(conn, company["id"], period, now, deal_id=deal["id"])


# ---------------------------------------------------------------------------
# A buyout loan: the bank's promises, and taking the company if they are broken
# ---------------------------------------------------------------------------

def covenant_test(conn: Connection, debt: dict) -> list[str]:
    """What the bank tests every quarter: the company's yearly earnings against the loan and its interest."""
    rows = _rows(conn, "SELECT operating_profit, depreciation FROM company_results WHERE company_id = %s AND period >= 1 ORDER BY period DESC LIMIT 4",
                 (debt["company_id"],))
    ebitda = sum(r["operating_profit"] + r["depreciation"] for r in rows) * 4 // max(len(rows), 1)
    terms = debt["covenants"] or COVENANTS
    if _one(conn, "SELECT status FROM companies WHERE id = %s", (debt["company_id"],))["status"] != "trading":
        return ["The company that secured the loan has failed."]
    broken = []
    if debt["outstanding"] > ebitda * terms.get("debt_x_most", 5):
        broken.append(f"The loan is more than {terms.get('debt_x_most', 5)} times the company's yearly earnings.")
    interest = apply_bps(debt["outstanding"], debt["rate_bps"])
    if interest and ebitda * BPS < interest * terms.get("cover_least_bps", 15_000):
        broken.append("The company's earnings no longer cover the interest one and a half times.")
    return broken


def enforce_security(conn: Connection, empire: dict, debt: dict, wanted: int, period: int, now: datetime) -> int:
    """The bank takes the company it lent against: the empire's shares are sold to the pension funds at
    the company's valuation, and the bank is paid from the price. Anything above the debt goes to the empire."""
    company = _one(conn, "SELECT * FROM companies WHERE id = %s", (debt["company_id"],))
    held = ledger.balance(conn, empire["account_id"], company["share_asset"])
    if held <= 0 or company["status"] != "trading":
        return 0                                         # the company that secured it is gone: there is nothing to take
    from simulation import firm_owned
    funds = ledger.account_id(conn, ledger.INVESTORS_INSTITUTIONS)
    price = firm_owned.buyer_offer(conn, company["id"])["per_share"] * held     # the buyer's usual price, no better
    took = 0
    if 0 < price <= ledger.balance(conn, funds):
        ledger.transfer(conn, payer=empire["account_id"], receiver=funds, amount=held, asset=company["share_asset"], kind="security_enforced",
                        memo=f"{company['name']}: shares taken by the bank and sold", period=period)
        took = min(price, wanted)
        ledger.transfer(conn, payer=funds, receiver=debt["lender_account"], amount=took, kind="empire_repayment",
                        memo=f"{company['name']}: the bank paid from the sale of its security", period=period)
        if price > took:
            ledger.transfer(conn, payer=funds, receiver=empire["account_id"], amount=price - took, kind="security_enforced",
                            memo=f"{company['name']}: what the sale raised above the debt", period=period)
    else:
        # Nobody will pay for them: the bank keeps the shares themselves, and the debt is not reduced.
        ledger.transfer(conn, payer=empire["account_id"], receiver=debt["lender_account"], amount=held, asset=company["share_asset"],
                        kind="security_enforced", memo=f"{company['name']}: shares taken by the bank", period=period)
    firm_owned.exited(conn, empire["id"], company["id"], "to_buyer", max(price - took, 0), period, now, forced=True)
    _take_control(conn, company["id"], period, now)
    _log(conn, empire["id"], f"{debt['lender_name']} took {company['name']}, which secured its loan, and sold it for {_money(price)}.", now)
    return took


# ---------------------------------------------------------------------------
# Opinions on a deal, settled later
# ---------------------------------------------------------------------------

def _settle_check(conn: Connection, opinion: dict, period: int, now: datetime):
    """A check was right if what it reported (something found, or nothing) matches the truth."""
    step = opinion["kind"].removeprefix("deal_")
    found = opinion["call"].get("file_id")
    f = _one(conn, "SELECT f.*, s.company_id FROM deal_files f JOIN sale_processes s ON s.id = f.process_id WHERE f.id = %s", (found,))
    if f is None:
        return ("void", "The file is gone.")
    p = private.profile(conn, f["company_id"])
    present = {s["code"] for s in (p["secrets"] if p else [])} & set(FINDS_OF.get(step, ()))
    if step == "fairness":
        return ("right" if opinion["call"].get("score", 0) >= firm.DUTY_PASS else "wrong", "Judged by the figures at the time.")
    if step == "valuation":
        later = private.value_of(conn, f["company_id"])
        mine = f["valuation"] or 0
        if later <= 0:
            return ("wrong", "The company is worth nothing now.") if mine > 0 else ("right", "It was valued at nothing, and is worth nothing.")
        near = abs(mine - later) * BPS <= later * 2500
        return ("right" if near else "wrong", f"Valued at {_money(mine)}; worth {_money(later)} a year on.")
    spotted = {r["code"] for r in _rows(conn, "SELECT code FROM deal_finds WHERE empire_id = %s AND company_id = %s AND how = %s",
                                        (f["empire_id"], f["company_id"], STEPS.get(step, ("", ""))[1]))}
    if present - spotted:
        return ("wrong", "Something was there to find, and was missed.")
    return ("right", "What was reported matched what was there.")


for _kind in ("deal_background", "deal_accounts", "deal_valuation", "deal_stress", "deal_legal", "deal_fairness"):
    firm.OPINION_SETTLERS[_kind] = _settle_check
firm.OPINION_NAMES.update({"deal_brought": "Deals brought", "deal_background": "Background digging", "deal_accounts": "Accounts checked",
                           "deal_valuation": "Companies valued", "deal_stress": "Stress tests", "deal_legal": "Ownership and contracts",
                           "deal_fairness": "Fairness opinions"})


# ---------------------------------------------------------------------------
# What a member sees
# ---------------------------------------------------------------------------

def view(conn: Connection, seat: dict, empire: dict, state: dict, now: datetime) -> dict:
    me = seat["player_id"]
    is_head = empire["head_player_id"] == me
    sales = []
    for sale in _rows(conn, "SELECT s.*, c.name AS company, c.ticker, c.headquarters, sec.name AS sector FROM sale_processes s"
                            " JOIN companies c ON c.id = s.company_id JOIN sectors sec ON sec.code = c.sector WHERE s.status = 'open' ORDER BY s.id"):
        f = _one(conn, "SELECT * FROM deal_files WHERE empire_id = %s AND process_id = %s", (empire["id"], sale["id"]))
        item = {"id": sale["id"], "company": sale["company"], "sector": sale["sector"], "city": sale["headquarters"], "mode": sale["mode"],
                "asking": sale["asking"], "highest": sale["highest"] if sale["mode"] == "auction" else None,
                "closes": clock.period_label(sale["closes_period"]), "yours_to_sell": sale["seller_empire_id"] == empire["id"],
                "file": None, "can_bring": f is None and _desk_ok(conn, empire, seat, "investment_banker") and sale["seller_empire_id"] != empire["id"]}
        if f:
            item["file"] = _file_view(conn, f, sale, seat, empire, now)
        if sale["seller_empire_id"] == empire["id"]:
            item["asked_of_you"] = [{"empire_id": r["empire_id"], "code": r["code"], "status": r["status"]}
                                    for r in _rows(conn, "SELECT * FROM deal_terms WHERE process_id = %s AND status = 'asked' ORDER BY id", (sale["id"],))]
        sales.append(item)
    invitations = [{"id": r["id"], "from": r["from_empire"], "company": r["company"], "amount": r["amount"], "status": r["status"]}
                   for r in _rows(conn, "SELECT p.*, e.name AS from_empire, c.name AS company FROM deal_partners p JOIN deal_bids b ON b.id = p.bid_id"
                                        " JOIN empires e ON e.id = b.empire_id JOIN sale_processes s ON s.id = b.process_id JOIN companies c ON c.id = s.company_id"
                                        " WHERE p.empire_id = %s AND p.status IN ('invited', 'pledged') ORDER BY p.id", (empire["id"],))] if is_head else []
    deals = [{"id": d["id"], "company": d["company"], "price": d["price"], "period": clock.period_label(d["period"]), "status": d["status"],
              "escrow": d["escrow"], "claims_until": clock.period_label(d["escrow_until"]) if d["escrow_until"] else None,
              "terms": sorted(d["terms"]), "claims": [{"code": c["code"], "paid": c["paid"], "words": c["words"]}
                                                      for c in _rows(conn, "SELECT * FROM deal_claims WHERE deal_id = %s ORDER BY id", (d["id"],))],
              "found": finds(conn, empire["id"], d["company_id"])}
             for d in _rows(conn, "SELECT d.*, c.name AS company FROM deals d JOIN companies c ON c.id = d.company_id WHERE d.empire_id = %s"
                                  " ORDER BY d.id DESC LIMIT 12", (empire["id"],))]
    outside = [x for x in firm_practice().firms(conn)
               if not _one(conn, "SELECT 1 FROM pro_firms f JOIN empire_seats s ON s.player_id = f.founder_id WHERE f.id = %s AND s.empire_id = %s",
                           (x["id"], empire["id"]))]
    return {"sales": sales, "invitations": invitations, "deals": deals, "fairness_above": FAIRNESS_ABOVE, "outside_firms": outside,
            "step_firms": firm_practice().STEP_FIRMS,
            "partners": [{"id": e["id"], "name": e["name"]} for e in _rows(conn, "SELECT id, name FROM empires WHERE kind = 'player' AND status = 'active'"
                                                                                 " AND id <> %s ORDER BY name", (empire["id"],))] if is_head else []}


def _file_view(conn: Connection, f: dict, sale: dict, seat: dict, empire: dict, now: datetime) -> dict:
    me = seat["player_id"]
    steps = []
    is_head = empire["head_player_id"] == me
    for s in _rows(conn, "SELECT s.*, p.display_name AS doer, x.name AS firm FROM deal_steps s LEFT JOIN players p ON p.id = s.done_by"
                         " LEFT JOIN pro_firms x ON x.id = s.firm_id WHERE s.file_id = %s ORDER BY s.id", (f["id"],)):
        mine = _desk_ok(conn, empire, seat, s["build"]) and not s["firm_id"]
        steps.append({"id": s["id"], "step": s["step"], "title": STEPS[s["step"]][1], "why": STEPS[s["step"]][2], "desk": firm.DESK_LABELS[s["build"]],
                      "status": s["status"], "score": s["score"], "found": s["found"],
                      "by": (f"{s['firm']} (outside firm)" if s["firm"] else s["doer"]) or ("The staff" if s["by_staff"] else None),
                      "firm": s["firm"], "can_send": is_head and s["status"] == "due" and s["terms"] is None and not s["firm_id"] and f["nda_at"] is not None
                      and s["step"] in firm_practice().STEP_FIRMS,
                      "yours": mine and s["status"] == "due" and s["assigned_to"] in (None, me),
                      "terms": firm._public_terms(s["terms"]) if s["assigned_to"] == me and s["status"] == "due" else None})
    bid = _one(conn, "SELECT * FROM deal_bids WHERE process_id = %s AND empire_id = %s AND status IN ('pending', 'live')", (sale["id"], empire["id"]))
    partners = [{"id": r["id"], "empire": r["name"], "amount": r["amount"], "status": r["status"]}
                for r in _rows(conn, "SELECT p.*, e.name FROM deal_partners p JOIN empires e ON e.id = p.empire_id WHERE p.bid_id = %s ORDER BY p.id",
                               (bid["id"],))] if bid else []
    out = {"id": f["id"], "status": f["status"], "nda": f["nda_at"] is not None, "steps": steps, "valuation": f["valuation"],
           "can_sign_nda": f["nda_at"] is None and _desk_ok(conn, empire, seat, "investment_banker"),
           "can_negotiate": _desk_ok(conn, empire, seat, "investment_banker"), "is_head": empire["head_player_id"] == me,
           "bid": {"amount": bid["amount"], "charge": bid["clause_charge"], "equity": bid["equity"], "loan": bid["loan"], "status": bid["status"],
                   "mezzanine": bid.get("mezzanine") or 0, "earnout": bid.get("earnout") or 0}
                  if bid and bid["status"] == "live" else None,
           "partners": partners, "clauses": [{"code": k, "words": v[0], "escape": v[1]} for k, v in CLAUSES.items()],
           "protections": [{"code": k, "words": v[0]} for k, v in PROTECTIONS.items()]}
    if f["nda_at"]:
        out["data_room"] = data_room(conn, sale["company_id"], empire["id"], sale["id"])
        out["terms"] = terms_view(conn, sale["id"], empire["id"])
        out["charge_bps"] = charge_bps(conn, sale["id"], empire["id"])
        if empire["head_player_id"] == me:
            out["loan_quote"] = {k: v for k, v in loan_quote(conn, sale, sale["highest"] or sale["asking"], careers.world_now(conn, now)["period"]).items()
                                 if k != "lender_account"}
            out["mezzanine_quote"] = mezzanine_quote(conn, sale, sale["highest"] or sale["asking"], out["loan_quote"]["most"])
            out["earnout_most_bps"] = data.EARNOUT_MOST_BPS if not sale["seller_empire_id"] else 0
    return out


def waiting(conn: Connection, seat: dict, empire: dict, now: datetime) -> int:
    me = seat["player_id"]
    n = 0
    for s in _rows(conn, "SELECT s.* FROM deal_steps s JOIN deal_files f ON f.id = s.file_id JOIN sale_processes p ON p.id = f.process_id"
                         " WHERE f.empire_id = %s AND f.status = 'open' AND p.status = 'open' AND s.status = 'due' AND f.nda_at IS NOT NULL AND s.firm_id IS NULL",
                   (empire["id"],)):
        if _desk_ok(conn, empire, seat, s["build"]) and s["assigned_to"] in (None, me):
            n += 1
    if _desk_ok(conn, empire, seat, "investment_banker"):
        n += _one(conn, "SELECT count(*) AS n FROM deal_files f JOIN sale_processes p ON p.id = f.process_id WHERE f.empire_id = %s"
                        " AND f.status = 'open' AND p.status = 'open' AND f.nda_at IS NULL", (empire["id"],))["n"]
    if empire["head_player_id"] == me:
        n += _one(conn, "SELECT count(*) AS n FROM deal_partners WHERE empire_id = %s AND status = 'invited'", (empire["id"],))["n"]
    return n


def check_books(conn: Connection) -> list[str]:
    """The escrow account holds exactly what live bids, pledges and money held back from sellers add up to."""
    pot = _one(conn, "SELECT id FROM ledger_accounts WHERE code = %s", (ESCROW,))
    if pot is None:
        return []
    held = _one(conn, "SELECT ((SELECT coalesce(sum(held), 0) FROM deal_bids WHERE status IN ('pending', 'live'))"
                      " + (SELECT coalesce(sum(amount), 0) FROM deal_partners WHERE status = 'pledged')"
                      " + (SELECT coalesce(sum(escrow), 0) FROM deals))::bigint AS total")["total"]
    balance = ledger.balance(conn, pot["id"])
    return [] if balance == held else [f"Deals escrow holds {balance} kobo but bids, pledges and holdbacks come to {held}."]


def _bell(conn: Connection, now: datetime) -> None:
    _staff_steps(conn, now)
    _bell_auctions(conn, now)


def settle_earnouts(conn: Connection, period: int, now: datetime) -> None:
    """An earn-out falls due. If the company's sales over the earn-out quarters reached the target, the buyer pays the
    seller the rest of the price; if they fell short, it pays in proportion (so holding sales back to avoid paying
    saves little); what it cannot pay is owed."""
    if _one(conn, "SELECT to_regclass('deal_earnouts') IS NOT NULL AS ok")["ok"] is not True:
        return
    from simulation import lending
    for e in _rows(conn, "SELECT e.*, d.company_id, c.name AS company FROM deal_earnouts e JOIN deals d ON d.id = e.deal_id"
                         " JOIN companies c ON c.id = d.company_id WHERE e.status = 'running' AND e.due_period <= %s ORDER BY e.id FOR UPDATE OF e",
                   (period,)):
        row = _one(conn, "SELECT coalesce(sum(revenue), 0)::bigint AS s, count(*) AS n FROM company_results WHERE company_id = %s"
                         " AND period BETWEEN %s AND %s", (e["company_id"], e["from_period"], e["due_period"]))
        sales = row["s"]
        empire = empires._empire(conn, e["empire_id"])
        due = e["amount"] if sales >= e["target_sales"] else e["amount"] * max(sales, 0) // max(e["target_sales"], 1)
        if row["n"] < e["due_period"] - e["from_period"] + 1:
            due = e["amount"]          # a company wound up, sold on or not reporting cannot be used to escape the earn-out
        if due <= 0:
            conn.execute("UPDATE deal_earnouts SET status = 'missed' WHERE id = %s", (e["id"],))
            _log(conn, e["empire_id"], f"{e['company']} made no sales over the earn-out: the {_money(e['amount'])} still to pay is not owed.", now)
            continue
        paid = ledger.pay_up_to(conn, payer=empire["account_id"], receiver=e["seller_account"], wanted=due, kind="company_sale",
                                memo=f"The earn-out on {e['company']}", period=period)
        if paid < due:
            lending.record_shortfall(conn, empire["account_id"], e["seller_account"], due - paid, f"The earn-out on {e['company']}", period, now)
        status = "short" if paid < due else "paid" if due == e["amount"] else "part"
        conn.execute("UPDATE deal_earnouts SET status = %s, paid = %s WHERE id = %s", (status, paid, e["id"]))
        _log(conn, e["empire_id"], (f"{e['company']}'s sales reached the earn-out's target" if due == e["amount"] else
                                    f"{e['company']}'s sales reached {_money(sales)} of the {_money(e['target_sales'])} the earn-out "
                                    f"targeted, so it pays in proportion") + f": {_money(paid)} paid to the seller.", now)


def _closed(conn: Connection, period: int, now: datetime) -> None:
    decide_sales(conn, period, now)
    with conn.transaction():
        _release_escrow(conn, period, now)
        _ownership_claims(conn, period, now)
        settle_earnouts(conn, period, now)


firm.BELL.append(_bell)
firm.CLOSED.append(_closed)
firm.VIEW["deals"] = lambda conn, seat, empire, state, now: view(conn, seat, empire, state, now) if firm.player_run(empire) else None
firm.WAITING.append(lambda conn, seat, empire, now: waiting(conn, seat, empire, now) if firm.player_run(empire) else 0)
