"""Professional objectives (design document, section 9).

A piece of practical work drawn from one learning module. There are no question papers:
the player does the work in the live world, and the server judges the result against the
game's own records. Then it explains: plain language first, then the professional method,
then the mathematics.

The loop is the same for every objective: the idea, a situation in the live world, a
decision, what came of it, and why.

Every reward has a named payer, who pays out of their own cash: the client whose work it
was, or the player's employer. A failed objective costs the reward and nothing else.

Two kinds of work:
  hand-in   the player prepares figures from a company's filed accounts and hands them in
            once. The server works the same figures out from the records and compares.
  market    the player acts in the market with their own money. The server looks at what
            they actually hold at each Closing Bell, and at what the world then did.
"""

from __future__ import annotations

import contextvars
import dataclasses
import hashlib
import logging
import math
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable

from psycopg import Connection, errors
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from simulation import bonds, careers, clock, corporate, exchange, ledger, marketview
from simulation import world_data as data
from simulation.money import BPS, apply_bps, naira

log = logging.getLogger("wsbm.objectives")
STRICT = os.environ.get("OBJECTIVES_STRICT") == "true"       # in tests, a fault in judging is raised, not logged
FAILED_STATES = ("failed", "not_done", "withdrawn")
# What counts as money coming to a player from outside their own investing.
OUTSIDE_INCOME = ("salary", "starting_grant", "professional_fee", "deposit_interest", "savings_interest")       # as the Money Watch counts it


class ObjectiveError(Exception):
    """A request about an objective that the rules do not allow. The words are for the player."""


def _rows(conn: Connection, sql: str, params=()) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def _one(conn: Connection, sql: str, params=()) -> dict | None:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchone()


def _money(kobo: int) -> str:
    """An amount in words: ₦1,234.56 million for company figures, ₦50,000 for a player's."""
    if abs(kobo) >= 100_000_000_00:
        return f"{'-' if kobo < 0 else ''}₦{abs(kobo) / 1e8:,.2f} million"
    return f"{'-' if kobo < 0 else ''}₦{abs(kobo) / 100:,.0f}"


def _pct(bps: int | float) -> str:
    return f"{bps / 100:.2f}%"


def _millions(kobo: int) -> float:
    return kobo / 1e8


@dataclass(frozen=True)
class Template:
    code: str
    build: str
    module: str               # the learning module, by its name in the game
    title: str
    level: int                # the level at which it opens
    reward_naira: int         # at the start of the game; it keeps pace with wages
    experience: int
    kind: str                 # 'hand_in' or 'market'
    idea: str                 # the concept, in one or two plain sentences
    payer: str                # 'client' or 'employer'
    offer: Callable           # (ctx) -> terms, or None when it cannot be offered now
    submit: Callable | None = None      # (ctx, objective, answers) -> verdict, or None when it is judged later
    bell: Callable | None = None        # (ctx, objective, day) -> verdict or None
    close: Callable | None = None       # (ctx, objective, period) -> verdict or None
    listed: bool = True                 # False: never on the board; it exists only as a step in an empire's task
    setting: str = "solo"               # 'solo' (alone), 'empire' (with the empire) or 'live' (a weekend challenge)
    base: str | None = None             # the solo piece of work this is another setting of
    bonus_bps: int = BPS                # what it pays and teaches, against the solo piece

    @property
    def root(self) -> str:
        return self.base or self.code

    @property
    def track(self) -> str:
        """The syllabus map this work belongs to: one of the six builds, or 'ceo'."""
        return self.build


# Each setting of a piece of work draws its own client and its own numbers: the same player in the
# same quarter is never handed the work they have just seen the answers to.
SALT: contextvars.ContextVar[str] = contextvars.ContextVar("salt", default="")


def _verdict(state: str, summary: str, milestones: list, plain: str, method: str, maths: str, **more) -> dict:
    earned = sum(m["points"] for m in milestones if m["earned"])
    return {"state": state, "summary": summary, "score": earned, "milestones": milestones,
            "debrief": {"plain": plain, "method": method, "maths": maths}, **more}


def _milestone(label: str, points: int, earned: bool) -> dict:
    return {"label": label, "points": points, "earned": bool(earned)}


# ---------------------------------------------------------------------------
# Reading the world
# ---------------------------------------------------------------------------

def _choose(ctx, template: str, candidates: list):
    """The client for a piece of work. Ordinarily the server draws it. When the work is a step
    in an empire's task, it is the company the task is about (if this work can be done on it)."""
    target = ctx.get("target")
    if target is not None:
        return next((c for c in candidates if str(c["company_id"]) == str(target)), None)
    return _pick(ctx["player_id"], template, ctx["period"], candidates)


def _pick(player_id, template: str, period: int, candidates: list):
    """The server chooses the client, the same way every time for one player, piece of work and
    quarter. The player cannot choose an easy one, or ask again for another."""
    if not candidates:
        return None
    digest = hashlib.sha256(f"{player_id}:{template}:{period}{SALT.get()}".encode()).digest()
    return candidates[int.from_bytes(digest[:8], "big") % len(candidates)]


def _filed(conn: Connection, period: int) -> list[dict]:
    """Every company's filed accounts for one quarter (the latest version of each)."""
    return _rows(
        conn,
        "SELECT DISTINCT ON (r.company_id) r.company_id, c.ticker, c.name, c.sector, c.account_id, r.period, r.figures, r.credit_rating"
        " FROM company_reports r JOIN companies c ON c.id = r.company_id WHERE r.period = %s AND c.listed"
        " ORDER BY r.company_id, r.version DESC", (period,))


def _filed_one(conn: Connection, company_id, period: int) -> dict | None:
    return _one(conn, "SELECT r.figures, r.credit_rating, r.period FROM company_reports r WHERE r.company_id = %s AND r.period = %s"
                      " ORDER BY r.version DESC LIMIT 1", (company_id, period))


def _client(company: dict) -> dict:
    return {"ticker": company["ticker"], "name": company["name"]}


def private_share(conn: Connection, company_id, account=None) -> dict:
    """A share that has no market price (a private company). An empire carries its stake at what it paid until
    it sells (nothing about the company's private figures shows in its worth); anyone else at the latest
    valuation. A company wound up is worth nothing."""
    row = _one(conn, "SELECT c.ticker, c.status, c.share_asset, s.name AS sector, (SELECT v.value_per_share FROM company_valuations v WHERE v.company_id = c.id"
                     " ORDER BY v.period DESC LIMIT 1) AS value FROM companies c JOIN sectors s ON s.code = c.sector WHERE c.id = %s",
               (company_id,))
    price = max(row["value"] or 0, 0)
    if account is not None:
        stake = _one(conn, "SELECT k.cost FROM company_stakes k JOIN empires e ON e.id = k.empire_id WHERE k.company_id = %s AND e.account_id = %s",
                     (company_id, account))
        if stake is not None:
            held = ledger.balance(conn, account, row["share_asset"])
            price = stake["cost"] // max(held, 1)
    if row["status"] != "trading":
        price = 0
    return {"ticker": row["ticker"], "sector": row["sector"], "price": price, "private": True}


def wealth(conn: Connection, account, now: datetime) -> dict:
    """What a player owns right now, in its three parts: cash, shares and bonds."""
    day, _ = exchange.session_of(now)
    prices = {s["id"]: s for s in marketview._shares(conn, day)}
    lines = []
    for row in _rows(conn, "SELECT company_id, shares FROM share_owners WHERE account_id = %s", (account,)):
        share = prices.get(row["company_id"]) or private_share(conn, row["company_id"], account)
        lines.append({"ticker": share["ticker"], "sector": share["sector"], "shares": row["shares"],
                      "price": share["price"], "value": row["shares"] * share["price"]})
    held = bonds.holdings_of(conn, account, now)
    cash = ledger.balance(conn, account)
    # Savings at the banks (the crises stage) are cash kept with a bank: still the owner's.
    from simulation import deposits
    cash += deposits.savings_of(conn, account)
    # Cash held in escrow while a bid for a company stands, or pledged as a partner, is still its owner's.
    cash += _one(conn, "SELECT ((SELECT coalesce(sum(b.held), 0) FROM deal_bids b JOIN empires e ON e.id = b.empire_id"
                       " WHERE e.account_id = %s AND b.status IN ('pending', 'live'))"
                       " + (SELECT coalesce(sum(amount), 0) FROM deal_partners WHERE account_id = %s AND status = 'pledged'))::bigint AS total",
                 (account, account))["total"]
    cash += _one(conn, "SELECT coalesce(sum(reserved), 0)::bigint AS total FROM market_orders WHERE account_id = %s AND status = 'open'",
                 (account,))["total"]
    in_offers = corporate.held_by_account(conn).get(account, (0, 0))
    cash += in_offers[0]
    # Cash held for bids at the Auction House is still its owner's (Stage 8).
    if _one(conn, "SELECT to_regclass('auction_bids') IS NOT NULL AS ok")["ok"]:
        cash += _one(conn, "SELECT ((SELECT coalesce(sum(held), 0) FROM auction_bids WHERE bidder = %s AND status = 'live')"
                           " + (SELECT coalesce(sum(held), 0) FROM auction_partners WHERE partner = %s AND status = 'agreed'))::bigint AS total",
                     (account, account))["total"]
    shares_value = sum(line["value"] for line in lines) + in_offers[1]       # shares offered to a takeover are still theirs until it closes
    bonds_value = sum(b["value"] for b in held)
    property_value = 0
    if _one(conn, "SELECT to_regclass('property_holdings') IS NOT NULL AS ok")["ok"]:
        from simulation import property as property_market
        property_value = property_market.equity_of(conn, account)["equity"]      # what it owns in property, less what it owes on it
    borrowing, contracts = 0, 0
    if _one(conn, "SELECT to_regclass('player_loans') IS NOT NULL AS ok")["ok"]:
        # Stage 9: cash held as a short seller's collateral is still theirs; loans and borrowed shares are owed.
        from simulation import lending
        cash += lending.collateral_held(conn, account)
        borrowing = lending.loans_owed(conn, account) + lending.short_liability(conn, account)
    if _one(conn, "SELECT to_regclass('derivative_positions') IS NOT NULL AS ok")["ok"]:
        from simulation import derivatives
        contracts = derivatives.held_value(conn, account, now)              # options and futures, their margin included
    return {"cash": cash, "shares": shares_value, "bonds": bonds_value, "property": property_value, "borrowing": -borrowing,
            "derivatives": contracts, "total": cash + shares_value + bonds_value + property_value - borrowing + contracts,
            "lines": lines, "bond_lines": held, "day": day}


def index_now(conn: Connection, now: datetime) -> int:
    day, _ = exchange.session_of(now)
    return marketview.index_level(marketview._shares(conn, day), marketview.index_base(conn))


def bells_left(conn: Connection, now: datetime) -> int:
    """How many Closing Bells will ring before the running quarter ends."""
    world = _one(conn, "SELECT world_start, weeks_ahead FROM world_state")
    start = clock.effective_start(world["world_start"], world["weeks_ahead"])
    if now < start:
        return 0
    ends = clock.next_quarter_end(now, start)
    lagos = clock.to_lagos(now)
    bell = lagos.replace(hour=clock.MARKET_CLOSE.hour, minute=0, second=0, microsecond=0)
    if bell <= lagos:
        bell += timedelta(days=1)
    count = 0
    while bell <= ends:
        count += 1
        bell += timedelta(days=1)
    return count


# ---------------------------------------------------------------------------
# ACCOUNTANT 1. Reading financial statements: the key ratios working paper.
# ---------------------------------------------------------------------------

def _ratios_offer(ctx):
    candidates = []
    for company in _filed(ctx["conn"], ctx["period"] - 1):
        income, sheet = company["figures"]["income_statement"], company["figures"]["balance_sheet"]
        if income["revenue"] > 0 and income["ebitda"] > 0 and income["interest_expense"] > 0 and sheet["borrowings"] > 0 \
                and income["operating_profit"] > 0:
            candidates.append(company)
    company = _choose(ctx, "ac_ratios", candidates)
    if company is None:
        return None
    income, sheet = company["figures"]["income_statement"], company["figures"]["balance_sheet"]
    label = clock.period_label(company["period"])
    return {
        "client": _client(company),
        "situation": f"{company['name']}'s bank is reviewing its loans and wants a one-page view of the company from its "
                     f"accounts for {label}. Your firm has been asked to prepare it.",
        "task": ["Work out the four figures below from the filed accounts and hand them in.",
                 "Give money in millions of naira and ratios to one decimal place.",
                 "For debt against EBITDA, use a year's EBITDA: four times the quarter's."],
        "pass_when": "At least three of the four figures are right.",
        "deadline": "Hand it in before this quarter ends. It can be handed in once.",
        "given": [
            {"label": "Sales", "kobo": income["revenue"]},
            {"label": "Operating profit", "kobo": income["operating_profit"]},
            {"label": "Wear on buildings and machines (depreciation)", "kobo": income["depreciation"]},
            {"label": "Interest paid on its debts", "kobo": income["interest_expense"]},
            {"label": "Profit after tax", "kobo": income["net_profit"]},
            {"label": "Total borrowings", "kobo": sheet["borrowings"]},
        ],
        "fields": [
            {"key": "ebitda", "label": "EBITDA", "kind": "millions"},
            {"key": "margin", "label": "Profit after tax as a share of sales", "kind": "percent"},
            {"key": "debt_to_ebitda", "label": "Debt against a year's EBITDA", "kind": "times"},
            {"key": "interest_cover", "label": "Interest cover (operating profit ÷ interest)", "kind": "times"},
        ],
        "company_id": str(company["company_id"]), "filed_period": company["period"],
    }


def _close_enough(given, truth: float, *, relative: float = 0.005, absolute: float = 0.06) -> bool:
    try:
        value = float(given)
    except (TypeError, ValueError):
        return False
    if not math.isfinite(value):
        return False
    return abs(value - truth) <= max(abs(truth) * relative, absolute)


def _ratios_submit(ctx, objective, answers):
    filed = _filed_one(ctx["conn"], objective["terms"]["company_id"], objective["terms"]["filed_period"])
    income, sheet = filed["figures"]["income_statement"], filed["figures"]["balance_sheet"]
    ebitda = income["operating_profit"] + income["depreciation"]
    truth = {
        "ebitda": _millions(ebitda),
        "margin": income["net_profit"] / income["revenue"] * 100,
        "debt_to_ebitda": sheet["borrowings"] / (4 * ebitda),
        "interest_cover": income["operating_profit"] / income["interest_expense"],
    }
    right = {key: _close_enough(answers.get(key), value) for key, value in truth.items()}
    names = {"ebitda": "EBITDA", "margin": "Profit margin", "debt_to_ebitda": "Debt against EBITDA", "interest_cover": "Interest cover"}
    milestones = [_milestone(names[key], 25, right[key]) for key in truth]
    passed = sum(right.values()) >= 3
    name = objective["terms"]["client"]["name"]
    return _verdict(
        "passed" if passed else "failed",
        f"{sum(right.values())} of 4 figures right.", milestones,
        plain=f"These four figures tell a lender most of what it needs. EBITDA is the cash the business itself throws off. "
              f"The margin is how much of each naira of sales is left for the owners. Debt against EBITDA is how many years "
              f"of that cash it would take to repay everything borrowed. Interest cover is how many times over the profit "
              f"pays the interest. {name}: EBITDA {_money(ebitda)}, margin {truth['margin']:.1f}%, debt "
              f"{truth['debt_to_ebitda']:.1f} times a year's EBITDA, interest covered {truth['interest_cover']:.1f} times.",
        method="Start from operating profit and add back depreciation, because no cash left the company for it. Always put a "
               "quarter's profit on a yearly footing before comparing it with a debt, which is a total and not a rate. "
               "Lenders usually grow wary above about four times EBITDA, and when interest cover falls below about two.",
        maths=f"EBITDA = {_millions(income['operating_profit']):,.2f} + {_millions(income['depreciation']):,.2f} = {truth['ebitda']:,.2f} million. "
              f"Margin = {_millions(income['net_profit']):,.2f} ÷ {_millions(income['revenue']):,.2f} = {truth['margin']:.1f}%. "
              f"Debt ÷ (4 × EBITDA) = {_millions(sheet['borrowings']):,.2f} ÷ {4 * truth['ebitda']:,.2f} = {truth['debt_to_ebitda']:.1f}. "
              f"Cover = {_millions(income['operating_profit']):,.2f} ÷ {_millions(income['interest_expense']):,.2f} = {truth['interest_cover']:.1f}.",
        answers={key: round(value, 2) for key, value in truth.items()},
    )


# ---------------------------------------------------------------------------
# ACCOUNTANT 2. The cash flow statement: sort the quarter's cash movements.
# ---------------------------------------------------------------------------

def _cash_items(figures: dict) -> list[dict]:
    """The quarter's cash movements of one company, each with the heading it belongs under."""
    income, flow = figures["income_statement"], figures["cash_flow"]
    received = income["revenue"] + income["interest_income"]
    day_to_day = flow["cash_from_operations"] - received + income["interest_expense"] + income["tax"]
    other_investing = flow["cash_from_investing"] + flow["capital_spending"]
    other_financing = flow["cash_from_financing"] + flow["dividends_paid"] + flow["debt_repaid"]
    items = [
        ("customers", "Received from customers, and interest on money it has lent", received, "operating"),
        ("running", "Paid to staff and suppliers, with the change in bills not yet paid", day_to_day, "operating"),
        ("interest", "Interest paid to its lenders", -income["interest_expense"], "operating"),
        ("tax", "Company tax", -income["tax"], "operating"),
        ("building", "Buildings and machines bought", -flow["capital_spending"], "investing"),
        ("lending", "Lending made or repaid to it, and shares bought in other companies", other_investing, "investing"),
        ("dividends", "Dividends paid to its owners", -flow["dividends_paid"], "financing"),
        ("debt", "Debt repaid" if flow["debt_repaid"] >= 0 else "New borrowing", -flow["debt_repaid"], "financing"),
        ("shares", "New shares sold, and bonds swapped for shares", other_financing, "financing"),
    ]
    return [{"key": key, "label": label, "kobo": amount, "heading": heading} for key, label, amount, heading in items if amount]


def _cash_offer(ctx):
    candidates = [c for c in _filed(ctx["conn"], ctx["period"] - 1)
                  if len(_cash_items(c["figures"])) >= 6 and c["figures"]["cash_flow"]["cash_closing"] > 0]
    company = _choose(ctx, "ac_cash_flow", candidates)
    if company is None:
        return None
    items = _cash_items(company["figures"])
    # Shown in an order that gives nothing away.
    items.sort(key=lambda item: hashlib.sha256(f"{ctx['player_id']}:{item['key']}".encode()).hexdigest())
    label = clock.period_label(company["period"])
    return {
        "client": _client(company),
        "situation": f"{company['name']} is preparing its cash flow statement for {label}. Its bookkeeper has listed the "
                     f"quarter's cash movements but has not sorted them.",
        "task": ["Put each movement under its heading: day-to-day business (operating), buying and selling long-term things "
                 "(investing), or dealings with owners and lenders (financing).",
                 "Companies in this country file interest and tax under day-to-day business.",
                 "Then give the total under each heading and the cash at the end of the quarter, in millions of naira."],
        "pass_when": "Every movement but one, at most, is under the right heading, and the four totals are right.",
        "deadline": "Hand it in before this quarter ends. It can be handed in once.",
        "given": [{"label": "Cash at the start of the quarter", "kobo": company["figures"]["cash_flow"]["cash_opening"]}],
        "fields": [
            {"key": "headings", "label": "The quarter's cash movements", "kind": "classify",
             "options": [{"code": "operating", "label": "Day-to-day business"}, {"code": "investing", "label": "Investing"},
                         {"code": "financing", "label": "Owners and lenders"}],
             "items": [{"key": item["key"], "label": item["label"], "kobo": item["kobo"]} for item in items]},
            {"key": "operating", "label": "Cash from day-to-day business", "kind": "millions"},
            {"key": "investing", "label": "Cash from investing", "kind": "millions"},
            {"key": "financing", "label": "Cash from owners and lenders", "kind": "millions"},
            {"key": "closing", "label": "Cash at the end of the quarter", "kind": "millions"},
        ],
        "company_id": str(company["company_id"]), "filed_period": company["period"],
    }


def _cash_submit(ctx, objective, answers):
    filed = _filed_one(ctx["conn"], objective["terms"]["company_id"], objective["terms"]["filed_period"])
    flow = filed["figures"]["cash_flow"]
    items = _cash_items(filed["figures"])
    chosen = answers.get("headings") if isinstance(answers.get("headings"), dict) else {}
    sorted_right = sum(1 for item in items if chosen.get(item["key"]) == item["heading"])
    totals = {"operating": flow["cash_from_operations"], "investing": flow["cash_from_investing"],
              "financing": flow["cash_from_financing"], "closing": flow["cash_closing"]}
    right = {key: _close_enough(answers.get(key), _millions(value), absolute=0.05) for key, value in totals.items()}
    sorting_ok = sorted_right >= len(items) - 1
    milestones = [
        _milestone(f"Movements under the right heading ({sorted_right} of {len(items)})", 50, sorting_ok),
        _milestone("The three totals", 30, right["operating"] and right["investing"] and right["financing"]),
        _milestone("Cash at the end of the quarter", 20, right["closing"]),
    ]
    passed = sorting_ok and all(right.values())
    words = {"operating": "day-to-day business", "investing": "investing", "financing": "owners and lenders"}
    return _verdict(
        "passed" if passed else "failed",
        f"{sorted_right} of {len(items)} movements sorted correctly; {sum(right.values())} of 4 totals right.", milestones,
        plain="A company can show a profit and still run out of cash, so the cash flow statement sorts every naira that moved "
              "into three piles. Day-to-day business should bring cash in. Investing usually takes it out, as the company buys "
              "buildings and machines. The third pile shows what was paid to, or raised from, owners and lenders. "
              f"Here: {_money(totals['operating'])} from day-to-day business, {_money(totals['investing'])} from investing, "
              f"{_money(totals['financing'])} from owners and lenders.",
        method="Ask of each movement: would it happen in an ordinary week of trading? Then it is operating. Does it buy or sell "
               "something meant to last for years, or lend money out? Investing. Is it between the company and the people who "
               "funded it? Financing. The three totals must add up to the change in cash: that is the check.",
        maths="; ".join(f"{item['label']}: {_millions(item['kobo']):,.2f} ({words[item['heading']]})" for item in items)
              + f". Opening {_millions(flow['cash_opening']):,.2f} + {_millions(totals['operating']):,.2f} + "
                f"{_millions(totals['investing']):,.2f} + {_millions(totals['financing']):,.2f} = closing {_millions(totals['closing']):,.2f} million.",
        answers={"headings": {item["key"]: item["heading"] for item in items},
                 **{key: round(_millions(value), 2) for key, value in totals.items()}},
    )


# ---------------------------------------------------------------------------
# ACCOUNTANT 3. Company tax: close the income statement and work out the tax.
# ---------------------------------------------------------------------------

def _tax_rate(conn) -> int:
    return _one(conn, "SELECT company_tax_bps FROM world_state")["company_tax_bps"]


def _income_offer(ctx):
    rate = _tax_rate(ctx["conn"])
    candidates = []
    for company in _filed(ctx["conn"], ctx["period"] - 1):
        income = company["figures"]["income_statement"]
        operating = (income["revenue"] + income["interest_income"] - income["cost_of_sales"] - income["operating_expenses"]
                     - income["depreciation"])
        before_tax = operating - income["interest_expense"]
        tax = apply_bps(before_tax, rate) if before_tax > 0 else 0
        # Only companies whose filed accounts follow the plain arithmetic (a bank's loan losses do not).
        if operating == income["operating_profit"] and before_tax == income["profit_before_tax"] and tax == income["tax"]:
            candidates.append(company)
    company = _choose(ctx, "ac_income", candidates)
    if company is None:
        return None
    income = company["figures"]["income_statement"]
    return {
        "client": _client(company),
        "situation": f"{company['name']}'s finance team has the quarter's totals for {clock.period_label(company['period'])} "
                     f"but its income statement is not finished, and the tax office wants its payment.",
        "task": ["Finish the income statement from the totals below and work out the company tax.",
                 "Companies in this country count interest earned on money they have lent as part of operating profit; interest "
                 "paid on their own debts comes after it.",
                 f"Company tax is {rate / 100:.0f}% of profit before tax. A company that made a loss pays none.",
                 "Give every figure in millions of naira. A loss is a minus figure."],
        "pass_when": "The tax is right, and at least two of the other three figures.",
        "deadline": "Hand it in before this quarter ends. It can be handed in once.",
        "given": [
            {"label": "Sales", "kobo": income["revenue"]},
            {"label": "Interest earned on money it has lent", "kobo": income["interest_income"]},
            {"label": "Cost of what it sold", "kobo": income["cost_of_sales"]},
            {"label": "Running costs", "kobo": income["operating_expenses"]},
            {"label": "Wear on buildings and machines (depreciation)", "kobo": income["depreciation"]},
            {"label": "Interest paid on its debts", "kobo": income["interest_expense"]},
        ],
        "fields": [
            {"key": "operating_profit", "label": "Operating profit", "kind": "millions"},
            {"key": "profit_before_tax", "label": "Profit before tax", "kind": "millions"},
            {"key": "tax", "label": "Company tax", "kind": "millions"},
            {"key": "net_profit", "label": "Profit after tax", "kind": "millions"},
        ],
        "company_id": str(company["company_id"]), "filed_period": company["period"], "tax_bps": rate,
    }


def _income_submit(ctx, objective, answers):
    filed = _filed_one(ctx["conn"], objective["terms"]["company_id"], objective["terms"]["filed_period"])
    income = filed["figures"]["income_statement"]
    keys = ("operating_profit", "profit_before_tax", "tax", "net_profit")
    names = {"operating_profit": "Operating profit", "profit_before_tax": "Profit before tax", "tax": "Company tax",
             "net_profit": "Profit after tax"}
    right = {key: _close_enough(answers.get(key), _millions(income[key]), absolute=0.05) for key in keys}
    milestones = [_milestone(names[key], 40 if key == "tax" else 20, right[key]) for key in keys]
    passed = right["tax"] and sum(right.values()) >= 3
    rate = objective["terms"]["tax_bps"]
    m = {key: _millions(income[key]) for key in income}
    return _verdict(
        "passed" if passed else "failed", f"{sum(right.values())} of 4 figures right.", milestones,
        plain="An income statement walks down from sales to what is left for the owners. Take the cost of what was sold and "
              "the running costs from the money that came in, allow for wear on buildings and machines, and you have operating "
              "profit: what the business itself earned. Lenders are paid next. The Government takes its share of what is left, "
              "and only a company that made a profit pays it.",
        method="Keep the order: operating profit first, then interest, then tax. Tax is worked out on profit after interest, "
               "because interest on borrowing is a cost the tax office allows. A loss carries no tax for the quarter.",
        maths=f"Operating profit = {m['revenue']:,.2f} + {m['interest_income']:,.2f} − {m['cost_of_sales']:,.2f} − "
              f"{m['operating_expenses']:,.2f} − {m['depreciation']:,.2f} = {m['operating_profit']:,.2f}. "
              f"Before tax = {m['operating_profit']:,.2f} − {m['interest_expense']:,.2f} = {m['profit_before_tax']:,.2f}. "
              f"Tax = {rate / 100:.0f}% × {max(m['profit_before_tax'], 0):,.2f} = {m['tax']:,.2f}. "
              f"After tax = {m['net_profit']:,.2f} million.",
        answers={key: round(m[key], 2) for key in keys},
    )


# ---------------------------------------------------------------------------
# ACCOUNTANT 4. Budgeting and forecasting: forecast this quarter's sales.
# ---------------------------------------------------------------------------

def _history(conn, company_id, upto: int, quarters: int = 6) -> list[dict]:
    rows = _rows(conn, "SELECT DISTINCT ON (period) period, figures->'income_statement' AS income FROM company_reports"
                       " WHERE company_id = %s AND period BETWEEN %s AND %s AND period >= 1 ORDER BY period, version DESC",
                 (company_id, upto - quarters + 1, upto))
    return [{"period": r["period"], "label": clock.period_label(r["period"]), "revenue": r["income"]["revenue"],
             "net_profit": r["income"]["net_profit"]} for r in rows]


def _forecast_offer(ctx):
    if ctx["period"] < 3:
        return None                       # there is no history to forecast from yet
    candidates = [c for c in _filed(ctx["conn"], ctx["period"] - 1) if c["sector"] not in ("banking", "insurance")]
    company = _choose(ctx, "ac_forecast", candidates)
    if company is None:
        return None
    past = _history(ctx["conn"], company["company_id"], ctx["period"] - 1)
    return {
        "client": _client(company),
        "situation": f"{company['name']}'s board is setting its budget and needs to know what sales to expect in "
                     f"{clock.period_label(ctx['period'])}, the quarter now running.",
        "task": ["Forecast the company's sales for the quarter now running, in millions of naira.",
                 "Its past sales are below. Look for the season (the same quarter a year ago), the trend, and what the news "
                 "and its industry are saying this quarter."],
        "pass_when": "Your forecast is within 3% of the sales the company files when the quarter ends.",
        "deadline": "Hand your forecast in before this quarter ends. It can be handed in once. The world decides the rest.",
        "given": [{"label": f"Sales, {row['label']}", "kobo": row["revenue"]} for row in past],
        "fields": [{"key": "revenue", "label": f"Sales forecast for {clock.period_label(ctx['period'])}", "kind": "millions"}],
        "company_id": str(company["company_id"]), "for_period": ctx["period"], "last_revenue": past[-1]["revenue"] if past else 0,
    }


def _forecast_submit(ctx, objective, answers):
    try:
        value = float(answers.get("revenue"))
    except (TypeError, ValueError):
        raise ObjectiveError("Give your forecast as a number, in millions of naira.") from None
    if not math.isfinite(value) or value <= 0 or value > 1e9:
        raise ObjectiveError("Give your forecast as a number above nought, in millions of naira.")
    answers["revenue"] = value            # kept as the number it is
    return None                           # judged when the company files


def _forecast_close(ctx, objective, period):
    if period < objective["terms"]["for_period"]:
        return None
    if objective["submission"] is None:
        return _not_done("No forecast was handed in before the quarter ended.")
    filed = _filed_one(ctx["conn"], objective["terms"]["company_id"], objective["terms"]["for_period"])
    actual = filed["figures"]["income_statement"]["revenue"]
    forecast = float(objective["submission"]["revenue"])
    miss_bps = round(abs(forecast - _millions(actual)) / _millions(actual) * BPS)
    year_ago = _filed_one(ctx["conn"], objective["terms"]["company_id"], objective["terms"]["for_period"] - 4)
    last = objective["terms"]["last_revenue"]
    milestones = [_milestone("Within 6% of the filed sales", 40, miss_bps <= 600),
                  _milestone("Within 3%", 40, miss_bps <= 300), _milestone("Within 1.5%", 20, miss_bps <= 150)]
    seasonal = ""
    if year_ago:
        was = year_ago["figures"]["income_statement"]["revenue"]
        seasonal = (f" The same quarter a year ago it sold {_money(was)}; a forecaster who started from that and added the "
                    f"year's growth would have said about {_money(was * last // max(_history_revenue(ctx['conn'], objective, 5), 1))}.")
    return _verdict(
        "passed" if miss_bps <= 300 else "failed",
        f"You forecast {forecast:,.2f} million; it filed {_millions(actual):,.2f} million: {_pct(miss_bps)} out.", milestones,
        plain=f"A budget is only as good as its sales forecast, because every other line follows from it. The company sold "
              f"{_money(actual)} this quarter, against {_money(last)} the quarter before.{seasonal}",
        method="Do not simply repeat last quarter. Many businesses have seasons, so compare with the same quarter a year ago "
               "and then allow for growth since. Read the quarter's news for the industry and for what households are "
               "spending. State the forecast as one figure and check afterwards how far out it was: that is how forecasts improve.",
        maths=f"Error = |{forecast:,.2f} − {_millions(actual):,.2f}| ÷ {_millions(actual):,.2f} = {_pct(miss_bps)}. "
              f"The pass mark is 3.00%.",
        answers={"revenue": round(_millions(actual), 2)},
    )


def _history_revenue(conn, objective, back: int) -> int:
    """Sales of the quarter `back` quarters before the one forecast (for the debrief)."""
    filed = _filed_one(conn, objective["terms"]["company_id"], objective["terms"]["for_period"] - back)
    return filed["figures"]["income_statement"]["revenue"] if filed else objective["terms"]["last_revenue"]


def _not_done(why: str) -> dict:
    return _verdict("not_done", why, [], plain=why, method="", maths="")


# ---------------------------------------------------------------------------
# ACCOUNTANT 5. Audit: can the company pay what falls due?
# ---------------------------------------------------------------------------

def _strained(conn, period: int) -> list[dict]:
    """Companies whose ability to pay is in real doubt, from their filed accounts: lately behind
    on a bill or a debt, or holding little cash against a quarter's costs."""
    filed = _filed(conn, period)
    behind = {r["company_id"] for r in _rows(
        conn, "SELECT DISTINCT company_id FROM company_reports WHERE period BETWEEN %s AND %s"
              " AND ((figures->'balance_sheet'->>'payables')::bigint > 0 OR (figures->'notes'->>'principal_overdue')::bigint > 0)",
        (period - 3, period))}

    def cover(company) -> float:
        income = company["figures"]["income_statement"]
        costs = income["operating_expenses"] + income["interest_expense"] + income["cost_of_sales"]
        return company["figures"]["balance_sheet"]["cash"] / costs if costs > 0 else 99.0

    filed.sort(key=lambda c: (c["company_id"] not in behind, cover(c)))
    return filed[:max(8, len(behind))]


def _bills_offer(ctx):
    company = _pick(ctx["player_id"], "ac_bills", ctx["period"], _strained(ctx["conn"], ctx["period"] - 1))
    if company is None:
        return None
    income, sheet = company["figures"]["income_statement"], company["figures"]["balance_sheet"]
    notes = company["figures"]["notes"]
    due = sum(b["principal_outstanding"] for b in notes.get("borrowings", [])
              if b["maturity_period"] <= ctx["period"])
    return {
        "client": _client(company),
        "situation": f"You are on the audit of {company['name']}. Before the auditors sign, they must decide whether the "
                     f"company can pay what falls due. Your partner wants your call on the quarter now running.",
        "task": ["Read its accounts and decide: will it pay every bill and every repayment due this quarter in full, "
                 "or will it fall behind?",
                 "Look at its cash against a quarter's costs, at bills already unpaid, and at debt reaching its end date."],
        "pass_when": "Your call matches what the company's accounts show when the quarter ends.",
        "deadline": "Hand your call in before this quarter ends. It can be handed in once. The world decides the rest.",
        "given": [
            {"label": "Cash", "kobo": sheet["cash"]},
            {"label": "Bills unpaid at the last quarter end", "kobo": sheet["payables"]},
            {"label": "Debt past its repayment date", "kobo": notes.get("principal_overdue", 0)},
            {"label": "Debt reaching its end date this quarter", "kobo": due},
            {"label": "Running costs and cost of sales last quarter", "kobo": income["operating_expenses"] + income["cost_of_sales"]},
            {"label": "Interest paid last quarter", "kobo": income["interest_expense"]},
            {"label": "Profit after tax last quarter", "kobo": income["net_profit"]},
        ],
        "fields": [{"key": "call", "label": "Your call", "kind": "choice",
                    "options": [{"code": "pays", "label": "It will pay everything due in full"},
                                {"code": "behind", "label": "It will fall behind"}]}],
        "company_id": str(company["company_id"]), "for_period": ctx["period"], "rating": company["credit_rating"],
    }


def _choice_submit(key: str, allowed: tuple):
    def submit(ctx, objective, answers):
        if answers.get(key) not in allowed:
            raise ObjectiveError("Choose one of the answers offered.")
        return None
    return submit


def _bills_close(ctx, objective, period):
    if period < objective["terms"]["for_period"]:
        return None
    if objective["submission"] is None:
        return _not_done("No call was handed in before the quarter ended.")
    filed = _filed_one(ctx["conn"], objective["terms"]["company_id"], objective["terms"]["for_period"])
    sheet, notes = filed["figures"]["balance_sheet"], filed["figures"]["notes"]
    behind = sheet["payables"] > 0 or notes.get("principal_overdue", 0) > 0 or notes.get("repayments_missed", 0) > 0
    right = (objective["submission"]["call"] == "behind") == behind
    name = objective["terms"]["client"]["name"]
    happened = (f"{name} fell behind: {_money(sheet['payables'])} of bills unpaid, "
                f"{_money(notes.get('principal_overdue', 0))} of debt past its date."
                if behind else f"{name} paid everything that fell due, and ended the quarter with {_money(sheet['cash'])} in cash.")
    return _verdict(
        "passed" if right else "failed", ("Your call was right. " if right else "Your call was wrong. ") + happened,
        [_milestone("The call matched what happened", 100, right)],
        plain="An auditor has to say whether a company can go on paying its way: it is called the going-concern judgement. "
              "A company does not fail because it made a loss. It fails on the day it cannot pay a bill. " + happened,
        method="Set the cash it holds against what must leave in the quarter: wages and suppliers, interest, tax, and any debt "
               "reaching its end date that the lender may not renew. A lender renews for a borrower with a sound credit rating "
               "and no unpaid bills. Bills already unpaid, or debt already past its date, are the strongest warning there is.",
        maths=f"At the end of the quarter: bills unpaid {_millions(sheet['payables']):,.2f} million, debt past its date "
              f"{_millions(notes.get('principal_overdue', 0)):,.2f} million, repayments missed in the quarter "
              f"{_millions(notes.get('repayments_missed', 0)):,.2f} million. Any of these above nought means it fell behind.",
        answers={"call": "behind" if behind else "pays"},
    )


# ---------------------------------------------------------------------------
# ACCOUNTANT 6. Credit analysis: call the credit rating at the next filing.
# ---------------------------------------------------------------------------
RATINGS = ("AAA", "AA", "A", "BBB", "BB", "B", "CCC", "D")


def _unsettled(conn, period: int) -> list[dict]:
    """Companies whose credit rating has changed in the last year: the ones worth a call."""
    moved = {r["company_id"] for r in _rows(
        conn, "SELECT company_id FROM (SELECT company_id, credit_rating, lag(credit_rating) OVER (PARTITION BY company_id ORDER BY period) AS was"
              " FROM (SELECT DISTINCT ON (company_id, period) company_id, period, credit_rating FROM company_reports"
              "       WHERE period BETWEEN %s AND %s ORDER BY company_id, period, version DESC) latest) x"
              " WHERE was IS NOT NULL AND was <> credit_rating", (period - 4, period))}
    filed = _filed(conn, period)
    chosen = [c for c in filed if c["company_id"] in moved]
    if len(chosen) < 8:
        # Too few have moved: add those with the weakest ratings, which move most.
        rest = sorted((c for c in filed if c["company_id"] not in moved), key=lambda c: -RATINGS.index(c["credit_rating"]))
        chosen += rest[:8 - len(chosen)]
    return sorted(chosen, key=lambda c: c["ticker"])


def _rating_offer(ctx):
    if ctx["period"] < 3:
        return None
    company = _pick(ctx["player_id"], "ac_rating", ctx["period"], _unsettled(ctx["conn"], ctx["period"] - 1))
    if company is None:
        return None
    income, sheet = company["figures"]["income_statement"], company["figures"]["balance_sheet"]
    ebitda = income["ebitda"]
    past = _rows(ctx["conn"], "SELECT DISTINCT ON (period) period, credit_rating FROM company_reports WHERE company_id = %s"
                              " AND period BETWEEN %s AND %s ORDER BY period, version DESC",
                 (company["company_id"], ctx["period"] - 4, ctx["period"] - 1))
    reasons = _one(ctx["conn"], "SELECT rating_reasons FROM company_reports WHERE company_id = %s AND period = %s"
                                " ORDER BY version DESC LIMIT 1", (company["company_id"], company["period"]))["rating_reasons"]
    return {
        "client": _client(company),
        "situation": f"A lender to {company['name']} wants to know where its credit rating is heading before agreeing new "
                     f"terms. It is rated {company['credit_rating']} today.",
        "task": ["Decide what its credit rating will be when it files its accounts for the quarter now running.",
                 "A rating follows the filed figures: debt against EBITDA, how well profit covers interest, cash in hand, "
                 "and whether any bill or debt is unpaid.",
                 "Its recent ratings: " + ", ".join(f"{clock.period_label(r['period'])} {r['credit_rating']}" for r in past) + "."],
        "pass_when": "You name the exact rating it is given at its next filing.",
        "deadline": "Hand your call in before this quarter ends. It can be handed in once. The world decides the rest.",
        "given": [
            {"label": "EBITDA last quarter", "kobo": ebitda},
            {"label": "Total borrowings", "kobo": sheet["borrowings"]},
            {"label": "Interest paid last quarter", "kobo": income["interest_expense"]},
            {"label": "Cash", "kobo": sheet["cash"]},
            {"label": "Bills unpaid", "kobo": sheet["payables"]},
            {"label": "Profit after tax last quarter", "kobo": income["net_profit"]},
        ],
        "notes": [str(r) for r in (reasons if isinstance(reasons, list) else [])][:4],
        "fields": [{"key": "rating", "label": "Its rating at the next filing", "kind": "choice",
                    "options": [{"code": r, "label": r} for r in RATINGS]}],
        "company_id": str(company["company_id"]), "for_period": ctx["period"], "rating": company["credit_rating"],
    }


def _rating_close(ctx, objective, period):
    if period < objective["terms"]["for_period"]:
        return None
    if objective["submission"] is None:
        return _not_done("No call was handed in before the quarter ended.")
    filed = _one(ctx["conn"], "SELECT credit_rating, rating_reasons FROM company_reports WHERE company_id = %s AND period = %s"
                              " ORDER BY version DESC LIMIT 1", (objective["terms"]["company_id"], objective["terms"]["for_period"]))
    said, was, now_rated = objective["submission"]["rating"], objective["terms"]["rating"], filed["credit_rating"]
    exact = said == now_rated
    near = abs(RATINGS.index(said) - RATINGS.index(now_rated)) <= 1
    direction = lambda a, b: (RATINGS.index(b) > RATINGS.index(a)) - (RATINGS.index(b) < RATINGS.index(a))   # noqa: E731
    reasons = filed["rating_reasons"] if isinstance(filed["rating_reasons"], list) else []
    return _verdict(
        "passed" if exact else "failed",
        f"You said {said}. It was rated {now_rated} (it was {was}).",
        [_milestone("Right direction (up, down or unchanged)", 40, direction(was, said) == direction(was, now_rated)),
         _milestone("Within one step", 20, near), _milestone("The exact rating", 40, exact)],
        plain=f"A credit rating is a lender's shorthand for how likely a borrower is to pay everything back on time. "
              f"{objective['terms']['client']['name']} is now rated {now_rated}. "
              + ("What decided it: " + " ".join(str(r) for r in reasons[:3]) if reasons else ""),
        method="Work from the figures the rating follows, not from the share price: debt against a year's EBITDA, interest "
               "cover, cash, and any unpaid bill or overdue debt, which pulls a rating down hard. Then ask what this quarter "
               "changes: a seasonal dip in sales, new borrowing, a rise in the interest rate on its loans.",
        maths="The ladder runs AAA, AA, A, BBB, BB, B, CCC, D. " + (f"From {was} to {now_rated} is "
              f"{abs(RATINGS.index(now_rated) - RATINGS.index(was))} step(s) "
              f"{'down' if RATINGS.index(now_rated) > RATINGS.index(was) else 'up'}." if now_rated != was else "It did not move."),
        answers={"rating": now_rated},
    )


# ---------------------------------------------------------------------------
# ASSET MANAGER 1. Portfolio construction: spread the risk.
# ---------------------------------------------------------------------------
SPREAD = {"value": 100_000, "companies": 5, "industries": 3, "largest_bps": 3000, "bells": 2, "limit": 5}


def _spread_offer(ctx):
    return {
        "situation": "The investment committee will not give a new manager clients' money until they have shown they can "
                     "build a portfolio that one bad company cannot sink. Show it with your own.",
        "task": [f"Hold shares worth at least ₦{SPREAD['value']:,} in at least {SPREAD['companies']} companies from at least "
                 f"{SPREAD['industries']} industries.",
                 f"No one company may be more than {SPREAD['largest_bps'] // 100}% of your shares by value.",
                 f"Have it in place at {SPREAD['bells']} Closing Bells in a row."],
        "pass_when": f"The portfolio meets all of this at {SPREAD['bells']} Closing Bells running, within the next "
                     f"{SPREAD['limit']} bells.",
        "deadline": f"{SPREAD['limit']} Closing Bells from now.",
        "given": [], "fields": [],
    }


def _spread_check(have: dict) -> dict:
    lines = [line for line in have["lines"] if line["value"] > 0]
    largest = max((line["value"] for line in lines), default=0)
    return {
        "value": have["shares"], "companies": len(lines), "industries": len({line["sector"] for line in lines}),
        "largest_bps": largest * BPS // have["shares"] if have["shares"] else 0,
        "largest": max(lines, key=lambda line: line["value"])["ticker"] if lines else None,
    }


def _spread_bell(ctx, objective, day):
    seen = _spread_check(wealth(ctx["conn"], ctx["account"], ctx["now"]))
    meets = (seen["value"] >= naira(SPREAD["value"]) and seen["companies"] >= SPREAD["companies"]
             and seen["industries"] >= SPREAD["industries"] and seen["largest_bps"] <= SPREAD["largest_bps"])
    progress = objective["progress"]
    progress["bells"] = progress.get("bells", 0) + 1
    progress["run"] = progress.get("run", 0) + 1 if meets else 0
    progress["ever"] = progress.get("ever", False) or meets
    progress["last"] = seen
    if progress["run"] < SPREAD["bells"] and progress["bells"] < SPREAD["limit"]:
        return None
    passed = progress["run"] >= SPREAD["bells"]
    summary = (f"At the bell you held {_money(seen['value'])} of shares in {seen['companies']} companies from {seen['industries']} "
               f"industries; the largest, {seen['largest']}, was {_pct(seen['largest_bps'])} of it." if seen["companies"]
               else "You held no shares at the bell.")
    state = "passed" if passed else "failed" if progress["ever"] or seen["companies"] else "not_done"
    return _verdict(
        state, summary,
        [_milestone("Built the portfolio", 60, progress["ever"]), _milestone("Held it at two bells running", 40, passed)],
        plain="Any one company can have a bad year, and no analysis rules that out. Spreading money over several companies "
              "in different industries means one failure costs a part of the portfolio and not all of it. Industries matter "
              "because companies in the same industry tend to fall together.",
        method="Set a limit on any single holding before buying anything, and keep to it as prices move: a share that has "
               "risen strongly becomes a bigger part of the portfolio without a single purchase, and has to be trimmed. "
               "Count industries, not just companies. Five banks are one bet.",
        maths=f"Largest holding ÷ all shares = {_pct(seen['largest_bps'])} (limit {_pct(SPREAD['largest_bps'])}). "
              f"Companies {seen['companies']} (at least {SPREAD['companies']}). Industries {seen['industries']} "
              f"(at least {SPREAD['industries']}). Value {_money(seen['value'])} (at least ₦{SPREAD['value']:,}).",
    )


# ---------------------------------------------------------------------------
# ASSET MANAGER 2. Money markets: put idle cash to work in Government bills.
# ---------------------------------------------------------------------------
BILLS = {"units": 50, "bells": 2}


def _bills_held(conn, account) -> int:
    return _one(conn, "SELECT coalesce(sum(h.balance), 0)::bigint AS units FROM ledger_balances h JOIN bonds b ON b.asset = h.asset"
                      " WHERE h.account_id = %s AND b.kind = 'bill' AND b.issuer = 'government' AND b.redeemed_period IS NULL",
                (account,))["units"]


def _idle_offer(ctx):
    if bells_left(ctx["conn"], ctx["now"]) < BILLS["bells"]:
        return None                       # too late in the quarter to do it properly
    return {
        "situation": "Cash waiting to be invested earns almost nothing. The desk keeps money it will need soon in Government "
                     "bills: loans to the Government for three months, repaid in full when the quarter ends.",
        "task": [f"Buy at least {BILLS['units']} Government bills (₦{BILLS['units'] * bonds.FACE // 100:,} at face value) on the "
                 f"Bonds and bills page.",
                 f"Hold them at {BILLS['bells']} Closing Bells or more, and until the quarter ends, when the Government repays them."],
        "pass_when": "You held the bills at two or more Closing Bells and were repaid when the quarter ended.",
        "deadline": "The end of this quarter.",
        "given": [], "fields": [], "for_period": ctx["period"],
    }


def _idle_bell(ctx, objective, day):
    if _bills_held(ctx["conn"], ctx["account"]) >= BILLS["units"]:
        objective["progress"]["bells"] = objective["progress"].get("bells", 0) + 1
    return None


def _idle_close(ctx, objective, period):
    if period < objective["terms"]["for_period"]:
        return None
    repaid = _one(ctx["conn"], "SELECT coalesce(sum(e.amount), 0)::bigint AS total FROM ledger_entries e JOIN ledger_transactions t"
                               " ON t.id = e.transaction_id JOIN bonds b ON t.reference = 'bond:' || b.id"
                               " WHERE e.account_id = %s AND e.asset = 'NGN' AND e.amount > 0 AND t.kind = 'bond_redemption'"
                               " AND t.period = %s AND b.kind = 'bill'", (ctx["account"], period))["total"]
    paid = _one(ctx["conn"], "SELECT coalesce(sum(t.units * t.price), 0)::bigint AS cost, coalesce(sum(t.units), 0)::bigint AS units"
                             " FROM bond_trades t JOIN bonds b ON b.id = t.bond_id WHERE t.account_id = %s AND t.side = 'buy'"
                             " AND b.kind = 'bill' AND b.redeemed_period = %s", (ctx["account"], period))
    bells = objective["progress"].get("bells", 0)
    enough = repaid >= BILLS["units"] * bonds.FACE
    passed = enough and bells >= BILLS["bells"]
    gain = repaid - paid["cost"] if paid["units"] and repaid else 0
    state = "passed" if passed else "failed" if bells or repaid else "not_done"
    return _verdict(
        state,
        f"You held the bills at {bells} Closing Bell(s) and were repaid {_money(repaid)}." if bells or repaid
        else "You bought no Government bills.",
        [_milestone("Held bills at two Closing Bells", 50, bells >= BILLS["bells"]), _milestone("Repaid in full at the quarter end", 50, enough)],
        plain="A bill pays no interest. You buy it for less than ₦1,000 and the Government repays ₦1,000 when the quarter ends: "
              "the difference is your return. It is the safest thing in the market, which is why it pays the least. "
              + (f"You paid {_money(paid['cost'])} and were repaid {_money(repaid)}: {_money(gain)} earned on money that would "
                 f"otherwise have sat idle." if gain > 0 else ""),
        method="Match the loan to when the money is needed. Cash needed within the quarter belongs in bills; a bond that runs "
               "for years could be worth less on the day you need to sell it. The earlier in the quarter a bill is bought, the "
               "cheaper it is and the more it earns.",
        maths=(f"Return = ({_millions(repaid) * 1e6:,.0f} − {_millions(paid['cost']) * 1e6:,.0f}) ÷ {_millions(paid['cost']) * 1e6:,.0f} = "
               f"{_pct((repaid - paid['cost']) * BPS // paid['cost'])} for the part of the quarter it was held."
               if paid["cost"] and repaid else "Return on a bill = (₦1,000 − price paid) ÷ price paid."),
    )


# ---------------------------------------------------------------------------
# ASSET MANAGER 3. Interest rates and bond prices: position for the rate decision.
# ---------------------------------------------------------------------------
RATES_MIN_NAIRA = 50_000
CALLS = {"rise": "The rate will rise", "hold": "The rate will stay where it is", "fall": "The rate will fall"}


def _benchmark(conn, now) -> dict | None:
    """The Government's ordinary bond nearest to five years: what a bond book is measured against."""
    lines = [b for b in bonds.listing(conn, now) if b["issuer"] == "Federal Government" and b["kind"] == "fixed"]
    return min(lines, key=lambda b: abs(b["quarters_left"] - 20)) if lines else None


def _rates_offer(ctx):
    conn = ctx["conn"]
    if bells_left(conn, ctx["now"]) < 1 or _benchmark(conn, ctx["now"]) is None:
        return None
    economy = _one(conn, "SELECT next_policy_rate_bps, inflation_bps FROM economy_results ORDER BY period DESC LIMIT 1")
    return {
        "situation": f"The Central Bank decides its interest rate when this quarter ends. It is {_pct(economy['next_policy_rate_bps'])} "
                     f"now, and prices rose {_pct(economy['inflation_bps'])} over the last year against a target of "
                     f"{_pct(data.INFLATION_TARGET_BPS)}. When the rate rises, bonds already issued fall in price, and the "
                     f"longest fall most. When it falls, they rise.",
        "task": ["Say which way you expect the rate to go.",
                 f"Position your bonds to match: hold at least ₦{RATES_MIN_NAIRA:,} of bonds or bills at the last Closing Bell "
                 f"before the decision. Short ones (bills, floating-rate) if you expect a rise; long ones if you expect a fall.",
                 "The Economy page shows the rule the Central Bank follows."],
        "pass_when": "Your call is right, and over the decision your bonds did at least as well as the Government's "
                     "five-year bond would have.",
        "deadline": "Hand in your call before the last Closing Bell of this quarter. It can be handed in once.",
        "given": [{"label": "The Central Bank's rate now", "text": _pct(economy["next_policy_rate_bps"])},
                  {"label": "Prices over the last year", "text": _pct(economy["inflation_bps"])}],
        "fields": [{"key": "call", "label": "Your call", "kind": "choice",
                    "options": [{"code": code, "label": label} for code, label in CALLS.items()]}],
        "for_period": ctx["period"], "rate_bps": economy["next_policy_rate_bps"],
    }


def _coupon(line: dict, policy_bps: int) -> int:
    """What one bond pays its holder as a quarter closes, in kobo."""
    if line["kind"] == "bill":
        return 0
    if line["kind"] == "floating":
        return line["face"] * (policy_bps + line["coupon_bps"]) // BPS // 4
    return line["face"] * line["coupon_bps"] // BPS // 4


def _rates_bell(ctx, objective, day):
    conn, now = ctx["conn"], ctx["now"]
    held = [b for b in bonds.holdings_of(conn, ctx["account"], now) if b["units"] > 0]
    value = sum(b["units"] * b["fair"] for b in held)
    bench = _benchmark(conn, now)
    if value < naira(RATES_MIN_NAIRA) or bench is None or objective["submission"] is None:
        objective["progress"].pop("book", None)      # only the last bell before the decision counts
        return None
    keep = ("code", "kind", "coupon_bps", "face", "fair", "name", "quarters_left")
    objective["progress"]["book"] = {
        "day": str(day), "value": value, "lines": [{**{k: b[k] for k in keep}, "units": b["units"]} for b in held],
        "benchmark": {k: bench[k] for k in keep},
    }
    return None


def _value_after(conn, line: dict, state: dict, policy_before: int) -> int:
    bond = bonds.find(conn, line["code"])
    if bond is None or bond["redeemed_period"] is not None:
        return line["face"] + _coupon(line, policy_before)             # repaid at the close
    return bonds.fair_value(bond, state) + _coupon(line, policy_before)


def _rates_close(ctx, objective, period):
    if period < objective["terms"]["for_period"]:
        return None
    conn = ctx["conn"]
    if objective["submission"] is None:
        return _not_done("No call was handed in before the decision.")
    book = objective["progress"].get("book")
    before = objective["terms"]["rate_bps"]
    after = _one(conn, "SELECT next_policy_rate_bps FROM economy_results WHERE period = %s", (period,))["next_policy_rate_bps"]
    happened = "rise" if after > before else "fall" if after < before else "hold"
    said = objective["submission"]["call"]
    moved = {"rise": f"rose from {_pct(before)} to {_pct(after)}", "fall": f"fell from {_pct(before)} to {_pct(after)}",
             "hold": f"stayed at {_pct(before)}"}[happened]
    if book is None:
        return _verdict("failed" if said else "not_done",
                        f"The rate {moved}. You held less than ₦{RATES_MIN_NAIRA:,} of bonds at the last Closing Bell, so there was no position to judge.",
                        [_milestone("Called the decision", 40, said == happened), _milestone("Bonds did as well as the five-year bond", 60, False)],
                        plain="A view is only worth something when money is placed on it. Hold the bonds that suit your call at the last bell before the decision.",
                        method="", maths="")
    state = bonds.market(conn, ctx["now"])
    was = sum(line["units"] * line["fair"] for line in book["lines"])
    now_worth = sum(line["units"] * _value_after(conn, line, state, before) for line in book["lines"])
    mine_bps = (now_worth - was) * BPS // was
    bench = book["benchmark"]
    bench_bps = (_value_after(conn, bench, state, before) - bench["fair"]) * BPS // bench["fair"]
    kept_up = mine_bps >= bench_bps - 2
    passed = said == happened and kept_up
    longest = max(book["lines"], key=lambda line: line["quarters_left"])
    return _verdict(
        "passed" if passed else "failed",
        f"The rate {moved}; you said \"{CALLS[said].lower()}\". Over the decision your bonds returned {_pct(mine_bps)} and the "
        f"five-year bond {_pct(bench_bps)}.",
        [_milestone("Called the decision", 40, said == happened), _milestone("Bonds did as well as the five-year bond", 60, kept_up)],
        plain="A bond's payments are fixed on the day it is issued. When the interest rate rises, new bonds pay more, so nobody "
              "will pay full price for an old one and its price falls until its return matches. The longer the bond has to run, "
              f"the more payments are affected and the further it moves. The rate {moved}: your bonds returned {_pct(mine_bps)}, "
              f"the five-year bond {_pct(bench_bps)}.",
        method="First read the Central Bank's rule: it raises the rate when prices are rising faster than its target and cuts "
               "when they are rising more slowly. Then choose how long your bonds run. Expecting a rise, shorten: bills and "
               "floating-rate bonds barely move. Expecting a fall, lengthen: the ten-year bond gains most. Managers call this "
               "choosing the portfolio's duration.",
        maths=f"Your bonds: {_millions(was) * 1e6:,.0f} before, {_millions(now_worth) * 1e6:,.0f} after with interest received = "
              f"{_pct(mine_bps)}. Five-year bond: {bench['fair'] / 100:,.2f} before, "
              f"{_value_after(conn, bench, state, before) / 100:,.2f} after with interest = {_pct(bench_bps)}. Your longest bond had "
              f"{longest['quarters_left']} quarter(s) to run.",
    )


# ---------------------------------------------------------------------------
# ASSET MANAGER 4. Asset allocation: hold a balanced mandate.
# ---------------------------------------------------------------------------
MANDATE = {"total": 150_000, "shares": (4000, 6000), "bonds": (3000, 5000), "cash": (500, 2000), "bells": 3, "limit": 6}


def _mandate_offer(ctx):
    band = lambda b: f"{b[0] // 100}% to {b[1] // 100}%"      # noqa: E731
    return {
        "situation": "A client has given the desk a balanced mandate: a fixed mix of shares, bonds and cash that the manager "
                     "must keep to whatever the market does. Run your own money to the same mandate.",
        "task": [f"Keep shares at {band(MANDATE['shares'])} of everything you own, bonds and bills at {band(MANDATE['bonds'])}, "
                 f"and cash at {band(MANDATE['cash'])}.",
                 f"You must own at least ₦{MANDATE['total']:,} in all.",
                 f"Be inside all three limits at {MANDATE['bells']} Closing Bells in a row."],
        "pass_when": f"Inside the mandate at {MANDATE['bells']} Closing Bells running, within the next {MANDATE['limit']} bells.",
        "deadline": f"{MANDATE['limit']} Closing Bells from now.",
        "given": [], "fields": [],
    }


def _mandate_bell(ctx, objective, day):
    have = wealth(ctx["conn"], ctx["account"], ctx["now"])
    total = have["total"]
    mix = {part: have[part] * BPS // total if total else 0 for part in ("shares", "bonds", "cash")}
    inside = total >= naira(MANDATE["total"]) and all(MANDATE[part][0] <= mix[part] <= MANDATE[part][1] for part in mix)
    progress = objective["progress"]
    progress["bells"] = progress.get("bells", 0) + 1
    progress["run"] = progress.get("run", 0) + 1 if inside else 0
    progress["ever"] = progress.get("ever", False) or inside
    progress["tried"] = progress.get("tried", False) or (have["shares"] > 0 and have["bonds"] > 0)
    progress["last"] = {**mix, "total": total}
    if progress["run"] < MANDATE["bells"] and progress["bells"] < MANDATE["limit"]:
        return None
    passed = progress["run"] >= MANDATE["bells"]
    return _verdict(
        "passed" if passed else "failed" if progress["tried"] else "not_done",
        f"At the bell: shares {_pct(mix['shares'])}, bonds {_pct(mix['bonds'])}, cash {_pct(mix['cash'])} of {_money(total)}.",
        [_milestone("Inside the mandate at a Closing Bell", 50, progress["ever"]), _milestone("Held it at three bells running", 50, passed)],
        plain="How money is divided between shares, bonds and cash decides most of what a portfolio earns and most of what it "
              "can lose, far more than which shares are picked. A mandate fixes that division in advance, so that a client "
              "knows what risk they are carrying.",
        method="Prices move the mix every day without any trade: after shares rise they are too large a part, and the manager "
               "sells some and buys bonds. That is rebalancing. It feels wrong, because it sells what has done well, and it is "
               "the discipline that keeps the risk where the client asked for it.",
        maths=f"Shares {_pct(mix['shares'])} (limits {_pct(MANDATE['shares'][0])} to {_pct(MANDATE['shares'][1])}); bonds "
              f"{_pct(mix['bonds'])} ({_pct(MANDATE['bonds'][0])} to {_pct(MANDATE['bonds'][1])}); cash {_pct(mix['cash'])} "
              f"({_pct(MANDATE['cash'][0])} to {_pct(MANDATE['cash'][1])}). Each is its value ÷ {_money(total)}.",
    )


# ---------------------------------------------------------------------------
# ASSET MANAGER 5. Share valuation: back your own valuation through the results.
# ---------------------------------------------------------------------------
VALUE = {"naira": 50_000}


def _priced(conn, now) -> list[dict]:
    """Every share with its price today and what its last filed figures say a share is worth."""
    day, _ = exchange.session_of(now)
    worth = {r["company_id"]: r["value_per_share"] for r in _rows(
        conn, "SELECT DISTINCT ON (company_id) company_id, value_per_share FROM company_valuations ORDER BY company_id, period DESC")}
    return [{"company_id": share["id"], "ticker": share["ticker"], "name": share["name"], "price": share["price"],
             "worth": worth.get(share["id"], share["price"])} for share in marketview._shares(conn, day)]


def _value_offer(ctx):
    if bells_left(ctx["conn"], ctx["now"]) < 1:
        return None
    return {
        "situation": "Today's share prices are built on last quarter's results. New results are filed when this quarter ends, "
                     "and each company's worth per share will be worked out again from them. The research desk wants your "
                     "best idea: the share whose worth will rise most.",
        "task": ["Choose one share you believe will be worth more after its next results than the market expects. Each "
                 "company's page shows how its worth per share is worked out: from its profit, its growth and the interest rate.",
                 "Read the season, the industry and this quarter's news for what will change those.",
                 f"Own at least ₦{VALUE['naira']:,} of it when you name it, and do not sell any of those shares until the "
                 f"first Closing Bell after the results.",
                 "Name your share here once you own it."],
        "pass_when": "From the moment you name it to the first Closing Bell after the results, your share does better than the BSX 50.",
        "deadline": "Name your share before this quarter ends. It can be named once.",
        "given": [], "fields": [{"key": "ticker", "label": "Your share (its three-letter code)", "kind": "ticker"}],
        "for_period": ctx["period"],
    }


def _value_submit(ctx, objective, answers):
    conn, now = ctx["conn"], ctx["now"]
    ticker = str(answers.get("ticker", "")).upper().strip()
    share = next((s for s in _priced(conn, now) if s["ticker"] == ticker), None)
    if share is None:
        raise ObjectiveError("There is no share with that code.")
    held = _one(conn, "SELECT coalesce(sum(shares), 0)::bigint AS shares FROM share_owners WHERE account_id = %s AND company_id = %s",
                (ctx["account"], share["company_id"]))["shares"]
    if held * share["price"] < naira(VALUE["naira"]):
        raise ObjectiveError(f"You need to own at least ₦{VALUE['naira']:,} of {ticker} before you name it. "
                             f"You own {_money(held * share['price'])}.")
    objective["progress"]["pick"] = {
        "company_id": str(share["company_id"]), "ticker": ticker, "name": share["name"], "price": share["price"],
        "worth": share["worth"], "shares": held, "index": index_now(conn, now), "period": ctx["period"],
    }
    return None


def _split_since(conn, company_id, period: int) -> int:
    ratio = 1
    for split in _rows(conn, "SELECT ratio FROM share_splits WHERE company_id = %s AND period >= %s", (company_id, period)):
        ratio *= split["ratio"]
    return ratio


def _value_bell(ctx, objective, day):
    conn = ctx["conn"]
    pick = objective["progress"].get("pick")
    if pick is None:
        return None
    ratio = _split_since(conn, pick["company_id"], pick["period"])
    held = _one(conn, "SELECT coalesce(sum(shares), 0)::bigint AS shares FROM share_owners WHERE account_id = %s AND company_id = %s",
                (ctx["account"], pick["company_id"]))["shares"]
    price = next(s["price"] for s in marketview._shares(conn, exchange.session_of(ctx["now"])[0]) if str(s["id"]) == pick["company_id"])
    share_bps = (price * ratio - pick["price"]) * BPS // pick["price"]
    index_bps = (index_now(conn, ctx["now"]) - pick["index"]) * BPS // pick["index"]
    debrief = dict(
        plain=f"A share's price is what people will pay today. Its worth is what the company's future profits are worth today, "
              f"and that changes every time new results show the profits were better or worse than expected. "
              f"{pick['name']} cost ₦{pick['price'] / 100:,.2f} when you named it, against a worth of ₦{pick['worth'] / 100:,.2f} "
              f"on the figures filed before.",
        method="A valuation has three levers: the profit a company makes, how fast that profit grows, and the interest rate "
               "its future profits are discounted at. Ask which of the three this quarter will move, and for which company "
               "most. Then judge the result against the market, not against nought: a share that rose 3% while the market "
               "rose 8% was a poor choice; one that fell 2% while the market fell 9% was a good one.",
        maths=f"Share: (₦{price * ratio / 100:,.2f} − ₦{pick['price'] / 100:,.2f}) ÷ ₦{pick['price'] / 100:,.2f} = {_pct(share_bps)}. "
              f"BSX 50 over the same time: {_pct(index_bps)}.")
    if held < pick["shares"] * ratio:
        return _verdict("failed", f"You sold {pick['ticker']} before the results were in.",
                        [_milestone("Held through the results", 40, False), _milestone("Did better than the BSX 50", 60, False)], **debrief)
    if objective["progress"].get("results_in") is None:
        return None                                  # the quarter has not closed yet
    beat = share_bps > index_bps
    return _verdict("passed" if beat else "failed",
                    f"{pick['ticker']} returned {_pct(share_bps)} since you named it; the BSX 50 returned {_pct(index_bps)}.",
                    [_milestone("Held through the results", 40, True), _milestone("Did better than the BSX 50", 60, beat)], **debrief)


def _value_close(ctx, objective, period):
    if period < objective["terms"]["for_period"]:
        return None
    if objective["progress"].get("pick") is None:
        return _not_done("No share was named before the quarter ended.")
    objective["progress"]["results_in"] = period
    return None


# ---------------------------------------------------------------------------
# ASSET MANAGER 6. Measuring performance: beat the BSX 50 over a quarter's bells.
# ---------------------------------------------------------------------------
BEAT = {"total": 200_000, "invested_bps": 6000, "bells": 7, "start_within": 2}


def _beat_offer(ctx):
    return {
        "situation": "The desk measures every manager against the BSX 50. Anybody can match the index by owning a little of "
                     "everything. A manager is paid to do better.",
        "task": [f"Have at least ₦{BEAT['total']:,} in all at the next Closing Bell: that is where the measurement starts.",
                 f"Keep at least {BEAT['invested_bps'] // 100}% of it in shares and bonds at every Closing Bell.",
                 f"The measurement runs for {BEAT['bells']} Closing Bells. Salary and other money paid to you is left out, so only "
                 f"your investing counts."],
        "pass_when": f"Over the {BEAT['bells']} bells, what you own grew by more than the BSX 50 did.",
        "deadline": f"{BEAT['bells']} Closing Bells after the measurement starts.",
        "given": [], "fields": [],
    }


def _beat_bell(ctx, objective, day):
    conn, now = ctx["conn"], ctx["now"]
    have = wealth(conn, ctx["account"], now)
    progress = objective["progress"]
    invested_bps = (have["shares"] + have["bonds"]) * BPS // have["total"] if have["total"] else 0
    if "start" not in progress:
        progress["waited"] = progress.get("waited", 0) + 1
        if have["total"] >= naira(BEAT["total"]) and invested_bps >= BEAT["invested_bps"]:
            # The moment is taken from the database's own clock, the one the ledger is stamped with.
            recorded = _one(conn, "SELECT clock_timestamp() AS at")["at"]
            progress["start"] = {"total": have["total"], "index": index_now(conn, now), "at": recorded.isoformat(), "bells": 0}
            return None
        if progress["waited"] >= BEAT["start_within"]:
            return _not_done(f"The measurement never started: at the first {BEAT['start_within']} Closing Bells you did not have "
                             f"₦{BEAT['total']:,} with {BEAT['invested_bps'] // 100}% of it invested.")
        return None
    start = progress["start"]
    start["bells"] += 1
    inflow = _one(conn, "SELECT coalesce(sum(e.amount), 0)::bigint AS total FROM ledger_entries e JOIN ledger_transactions t"
                        " ON t.id = e.transaction_id WHERE e.account_id = %s AND e.asset = 'NGN' AND e.amount > 0"
                        " AND t.kind = ANY(%s) AND t.created_at > %s", (ctx["account"], list(OUTSIDE_INCOME), start["at"]))["total"]
    mine_bps = (have["total"] - inflow - start["total"]) * BPS // start["total"]
    index_bps = (index_now(conn, now) - start["index"]) * BPS // start["index"]
    debrief = dict(
        plain=f"A manager's result means little alone. Up 4% is poor in a quarter when the market rose 9%, and down 2% is "
              f"excellent when it fell 10%. So the result is always set beside a benchmark. Yours was {_pct(mine_bps)} against "
              f"{_pct(index_bps)} for the BSX 50.",
        method="Take out money that arrived from outside (salary, fees), or a manager could look brilliant by being paid. "
               "What is left, divided by what you started with, is the return. The gap between it and the index is what the "
               "manager added or lost by choosing differently from the market: which shares, how much in bonds, how much in cash.",
        maths=f"({_millions(have['total']) * 1e6:,.0f} now − {_millions(inflow) * 1e6:,.0f} paid in − {_millions(start['total']) * 1e6:,.0f} "
              f"at the start) ÷ {_millions(start['total']) * 1e6:,.0f} = {_pct(mine_bps)}. BSX 50: {_pct(index_bps)}. "
              f"Difference: {_pct(mine_bps - index_bps)}.")
    if invested_bps < BEAT["invested_bps"]:
        return _verdict("failed", f"At a Closing Bell only {_pct(invested_bps)} of what you own was invested; the mandate asks for "
                                  f"{_pct(BEAT['invested_bps'])}.",
                        [_milestone("Stayed invested at every bell", 40, False), _milestone("Beat the BSX 50", 60, False)], **debrief)
    if start["bells"] < BEAT["bells"]:
        return None
    beat = mine_bps > index_bps
    return _verdict("passed" if beat else "failed",
                    f"Over {BEAT['bells']} bells you returned {_pct(mine_bps)}; the BSX 50 returned {_pct(index_bps)}.",
                    [_milestone("Stayed invested at every bell", 40, True), _milestone("Beat the BSX 50", 60, beat)], **debrief)


# ---------------------------------------------------------------------------
# The library. Stage 5 opens with six pieces of work in each of two builds.
# ---------------------------------------------------------------------------
TEMPLATES: dict[str, Template] = {t.code: t for t in (
    Template("ac_ratios", "accountant", "Reading financial statements", "The lender's one-page view", 1, 40_000, 60, "hand_in",
             "A handful of ratios turn three pages of accounts into a judgement a lender can act on.",
             "client", _ratios_offer, submit=_ratios_submit),
    Template("ac_cash_flow", "accountant", "The cash flow statement", "Sort the quarter's cash", 1, 50_000, 80, "hand_in",
             "Profit is an opinion; cash is a fact. The cash flow statement shows where every naira came from and went.",
             "client", _cash_offer, submit=_cash_submit),
    Template("ac_income", "accountant", "Company tax", "Finish the income statement and the tax", 2, 60_000, 100, "hand_in",
             "Tax is charged on profit after interest, and only on a profit.",
             "client", _income_offer, submit=_income_submit),
    Template("ac_forecast", "accountant", "Budgeting and forecasting", "Forecast the quarter's sales", 2, 90_000, 140, "hand_in",
             "Every budget starts from a sales forecast. Seasons and trend matter more than last quarter's figure.",
             "client", _forecast_offer, submit=_forecast_submit, close=_forecast_close),
    Template("ac_bills", "accountant", "Audit: can it keep going?", "Will it pay what falls due?", 3, 70_000, 100, "hand_in",
             "A company fails on the day it cannot pay a bill, whatever profit it shows.",
             "client", _bills_offer, submit=_choice_submit("call", ("pays", "behind")), close=_bills_close),
    Template("ac_rating", "accountant", "Credit analysis", "Call the credit rating", 4, 70_000, 100, "hand_in",
             "A credit rating follows the filed figures: debt, interest cover, cash and unpaid bills.",
             "client", _rating_offer, submit=_choice_submit("rating", RATINGS), close=_rating_close),
    Template("am_spread", "asset_manager", "Portfolio construction", "Spread the risk", 1, 50_000, 80, "market",
             "Spreading money across companies and industries means one failure cannot sink the portfolio.",
             "employer", _spread_offer, bell=_spread_bell),
    Template("am_idle", "asset_manager", "Money markets", "Put idle cash to work", 1, 40_000, 60, "market",
             "Cash needed soon belongs in Government bills: safe, short, and better than nothing.",
             "employer", _idle_offer, bell=_idle_bell, close=_idle_close),
    Template("am_rates", "asset_manager", "Interest rates and bond prices", "Position for the rate decision", 2, 80_000, 120, "market",
             "When interest rates rise, bonds already issued fall in price, and long bonds fall furthest.",
             "employer", _rates_offer, submit=_choice_submit("call", tuple(CALLS)), bell=_rates_bell, close=_rates_close),
    Template("am_mandate", "asset_manager", "Asset allocation", "Run a balanced mandate", 2, 70_000, 110, "market",
             "The split between shares, bonds and cash decides most of a portfolio's risk and return.",
             "employer", _mandate_offer, bell=_mandate_bell),
    Template("am_value", "asset_manager", "Share valuation", "Back your valuation", 3, 100_000, 150, "market",
             "Price is what you pay; worth is what the company's future profits are worth today.",
             "employer", _value_offer, submit=_value_submit, bell=_value_bell, close=_value_close),
    Template("am_beat", "asset_manager", "Measuring performance", "Beat the BSX 50", 4, 150_000, 200, "market",
             "A result means nothing until it is set beside a benchmark and money from outside is taken out.",
             "employer", _beat_offer, bell=_beat_bell),
)}


from simulation import (  # noqa: E402
    empires,  # noqa: E402,F401          (adds the work that exists only inside an empire)
    leagues,
    objectives_ceo,  # noqa: E402,F401   (adds the leadership work of the CEO track)
    objectives_gap,  # noqa: E402,F401   (the gap stage: the library brought to 350, Levels 41 to 100)
    objectives_intel,  # noqa: E402,F401 (Stage 10, Part 2: sources, investigations and economic intelligence)
    objectives_more,  # noqa: E402,F401  (adds the work of the other four builds to the library)
    objectives_news,  # noqa: E402,F401  (Stage 10: work about the news, and the editors who come back)
    objectives_property,  # noqa: E402,F401  (adds the work about land and property, Stage 8)
    objectives_stage9,  # noqa: E402,F401  (adds the work about borrowing, short selling and derivatives, Stage 9)
    ranks,
)

# ---------------------------------------------------------------------------
# Three settings. Every module's work comes alone, with the empire, and as a weekend challenge
# in the shared world (the stand-in for live events until they are built).
# ---------------------------------------------------------------------------

def weekend(now: datetime) -> dict:
    """The weekend challenge window: Friday 18:00 to Sunday 22:00, Lagos time. Returns whether it
    is open, and when it next opens and closes."""
    local = clock.to_lagos(now)
    (open_day, open_hour), (close_day, close_hour) = data.WEEKEND_OPENS, data.WEEKEND_CLOSES
    monday = (local - timedelta(days=local.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    opens = monday + timedelta(days=open_day, hours=open_hour)
    closes = monday + timedelta(days=close_day, hours=close_hour)
    if local >= closes:
        opens, closes = opens + timedelta(days=7), closes + timedelta(days=7)
    return {"open": opens <= local < closes, "opens": opens, "closes": closes}


def _salted(salt: str, handler: Callable | None) -> Callable | None:
    if handler is None:
        return None

    def run(*args):
        token = SALT.set(salt)
        try:
            return handler(*args)
        finally:
            SALT.reset(token)
    return run


def _for_empire(base: Template) -> Template:
    def offer(ctx):
        seat = empires.seat_of(ctx["conn"], ctx["player_id"])
        if seat is None or seat["empire_status"] != "active":
            return None
        terms = base.offer(ctx)
        if terms is None:
            return None
        terms["setting_note"] = (f"This is work for {seat['empire_name']}. The empire pays for it out of its own cash, and each piece "
                                 f"passed adds to its points in the league.")
        terms["empire_id"] = seat["empire_id"]
        return terms
    return dataclasses.replace(base, code=base.code + "_e", payer="empire", setting="empire", base=base.code, listed=True,
                               offer=_salted(":empire", offer), submit=_salted(":empire", base.submit),
                               bell=_salted(":empire", base.bell), close=_salted(":empire", base.close))


def _late(objective: dict, now: datetime) -> bool:
    by = objective["terms"].get("hand_in_by")
    return by is not None and now > datetime.fromisoformat(by)


def _for_weekend(base: Template) -> Template:
    def offer(ctx):
        window = weekend(ctx["now"])
        if not window["open"]:
            return None
        terms = base.offer(ctx)
        if terms is None:
            return None
        terms["setting_note"] = ("A weekend challenge, open to everybody of your build at the same moment in the shared world. "
                                 "It pays and teaches one and a half times as much.")
        if base.submit is not None:
            by = min(ctx["now"] + timedelta(hours=data.WEEKEND_HOURS), window["closes"])
            terms["hand_in_by"] = by.isoformat()
            terms["deadline"] = (f"Hand it in within {data.WEEKEND_HOURS} hours of taking it on, and before the challenge closes on "
                                 f"Sunday at 22:00 (Lagos time). It can be handed in once.")
        return terms

    def submit(ctx, objective, answers):
        if _late(objective, ctx["now"]):
            return _not_done("It was handed in after the time allowed for a weekend challenge.")
        return base.submit(ctx, objective, answers)

    return dataclasses.replace(base, code=base.code + "_w", setting="live", base=base.code, listed=True,
                               bonus_bps=data.WEEKEND_BONUS_BPS,
                               offer=_salted(":weekend", offer), submit=_salted(":weekend", submit if base.submit else None),
                               bell=_salted(":weekend", base.bell), close=_salted(":weekend", base.close))


def _grow_library() -> None:
    for base in [t for t in TEMPLATES.values() if t.listed and t.setting == "solo"]:
        for variant in (_for_empire(base), _for_weekend(base)):
            TEMPLATES[variant.code] = variant


_grow_library()
TRACKS = (*careers.BUILDS, "ceo")


def track_name(track: str) -> str:
    return "Leadership" if track == "ceo" else careers.BUILDS[track]["name"]


def modules(build: str) -> list[dict]:
    return [{"module": t.module, "template": t.code, "title": t.title, "idea": t.idea, "level": t.level}
            for t in TEMPLATES.values() if t.build == build and t.setting == "solo" and t.listed]


def mastery(conn: Connection, player_id, track: str) -> list[dict]:
    """A player's syllabus map for one track: every module, and which of its three stages are
    reached. Learned: passed alone. Practised: passed with the empire. Proven: passed in a
    weekend challenge."""
    passed = {}
    for row in _rows(conn, "SELECT template, setting, count(*) AS n FROM objectives WHERE player_id = %s AND track = %s AND state = 'passed'"
                           " GROUP BY template, setting", (player_id, track)):
        template = TEMPLATES.get(row["template"])
        if template is not None:
            key = (template.module, row["setting"])
            passed[key] = passed.get(key, 0) + row["n"]
    last = {r["module"]: r["state"] for r in _rows(
        conn, "SELECT DISTINCT ON (module) module, state FROM objectives WHERE player_id = %s AND track = %s AND state <> 'active'"
              " ORDER BY module, judged_seq DESC", (player_id, track))}
    out = []
    for m in modules(track):
        learned, practised, proven = (passed.get((m["module"], setting), 0) for setting in ("solo", "empire", "live"))
        stage = 3 if learned and practised and proven else 2 if learned and practised else 1 if learned else 0
        out.append({**m, "learned": bool(learned), "practised": bool(practised), "proven": bool(proven), "stage": stage,
                    "stage_name": ("Not yet", "Learned", "Practised", "Proven")[stage],
                    "passes": learned + practised + proven, "practise_again": last.get(m["module"]) in FAILED_STATES})
    return out


def coverage(conn: Connection, player_id, track: str) -> dict:
    """The coverage tracker: how much of a syllabus map the player has worked through."""
    rows = mastery(conn, player_id, track)
    total = len(rows)
    count = {stage: sum(1 for r in rows if r[stage]) for stage in ("learned", "practised", "proven")}
    return {"track": track, "name": track_name(track), "modules": total, **count,
            "learned_pct": round(100 * count["learned"] / total) if total else 0,
            "practised_pct": round(100 * count["practised"] / total) if total else 0,
            "proven_pct": round(100 * count["proven"] / total) if total else 0,
            "mastered": sum(1 for r in rows if r["stage"] == 3)}


# ---------------------------------------------------------------------------
# Taking work on, handing it in, giving it up
# ---------------------------------------------------------------------------

def _context(conn: Connection, player_id, now: datetime) -> dict:
    state = careers.world_now(conn, now)
    mine = careers.career(conn, player_id)
    account = ledger.player_account_id(conn, player_id)
    return {"conn": conn, "now": now, "period": state["period"], "day": state["day"], "wage_index_bps": state["wage_index_bps"],
            "player_id": player_id, "account": account, "career": mine, "job": careers.current_job(conn, player_id)}


def _reward(template: Template, wage_index_bps: int) -> int:
    return apply_bps(apply_bps(naira(template.reward_naira), wage_index_bps), template.bonus_bps) // 100_000 * 100_000   # to the nearest ₦1,000


def _experience(template: Template, career: dict | None) -> int:
    """What a piece of work teaches. Work done after a rank case teaches more: it is multiplied by
    one more than the number of rank cases passed."""
    return apply_bps(template.experience, template.bonus_bps) * (1 + (career["rank"] if career else 0))


def _payer(conn, ctx, template: Template, terms: dict) -> dict | None:
    """Who pays for this piece of work, if they can. The client pays for work done for it; the
    employer pays performance pay. Either must have the cash many times over."""
    step = ctx.get("step")
    if step or template.payer == "empire":
        # Work done for an empire is paid for by the empire, out of its own cash.
        seat = empires.seat_of(conn, ctx["player_id"])
        if seat is None or seat["empire_status"] != "active" or (step and seat["empire_id"] != step["empire_id"]):
            return None
        if ledger.balance(conn, seat["account_id"]) < _reward(template, ctx["wage_index_bps"]):
            return None
        return {"account": seat["account_id"], "name": seat["empire_name"], "why": "pay for work done for the empire"}
    if template.payer == "client" and template.root in _client_pieces() and terms.get("company_id"):
        company = _one(conn, "SELECT id, name, account_id FROM companies WHERE id = %s", (terms["company_id"],))
        why = "a fee for work for the paper"              # Stage 10: an editor's paper pays, employed or independent
    elif ctx["job"] is None:
        return None
    elif template.payer == "client":
        company = _one(conn, "SELECT id, name, account_id FROM companies WHERE id = %s", (terms["company_id"],))
        why = "an accountancy fee"
    else:
        company = _one(conn, "SELECT id, name, account_id FROM companies WHERE id = %s", (ctx["job"]["company_id"],))
        why = "performance pay"
    if ledger.balance(conn, company["account_id"]) < 20 * _reward(template, ctx["wage_index_bps"]):
        return None
    return {"account": company["account_id"], "name": company["name"], "why": why, "company_id": company["id"]}


def _client_pieces() -> dict:
    from simulation import clients
    return clients.PIECES


_HOW: dict[str, str | None] = {}


def how_to(template: Template) -> str | None:
    """The professional method for a piece of work, in words: the same text the debrief shows afterwards
    under "The professional method". It is general advice written for every player alike, never the
    answer, so it can be shown before the work is started ("How to do this", the redesign).
    It is read once from the judging code of the piece of work and kept."""
    if template.code in _HOW:
        return _HOW[template.code]
    if template.base and template.base in TEMPLATES and template.base != template.code:
        _HOW[template.code] = how_to(TEMPLATES[template.base])
        return _HOW[template.code]
    if getattr(template.submit, "method_text", None):
        _HOW[template.code] = template.submit.method_text
        return _HOW[template.code]
    import ast
    import inspect
    import textwrap
    texts: set[str] = set()
    for judge in (template.submit, template.bell, template.close):
        if judge is None:
            continue
        try:
            tree = ast.parse(textwrap.dedent(inspect.getsource(judge)))
        except (OSError, TypeError, SyntaxError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.keyword) and node.arg == "method":
                if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                    if node.value.value.strip():
                        texts.add(node.value.value.strip())
                else:
                    texts.add("\0")          # a method built from the work's own figures: never shown beforehand
    # Only one fixed text, the same whatever the outcome, is safe to show before the work is done.
    found = next(iter(texts)) if len(texts) == 1 and "\0" not in texts else None
    _HOW[template.code] = found
    return found


def _public(objective: dict) -> dict:
    """An objective as its own player may see it. Nothing here gives away an answer before it is judged."""
    template = TEMPLATES[objective["template"]]
    terms = {k: objective["terms"].get(k) for k in ("client", "situation", "task", "pass_when", "deadline", "given", "fields", "notes", "setting_note", "hand_in_by")
             if objective["terms"].get(k) is not None}
    progress = {k: v for k, v in objective["progress"].items() if k in ("bells", "run", "last", "pick", "waited", "start", "named")}
    if "book" in objective["progress"]:
        progress["book_value"] = objective["progress"]["book"]["value"]
    return {
        "id": objective["id"], "template": objective["template"], "module": objective["module"], "title": objective["title"],
        "kind": template.kind, "idea": template.idea, "how": how_to(template), "terms": terms, "reward": objective["reward"],
        "setting": objective["setting"], "setting_name": data.SETTINGS[objective["setting"]], "track": objective["track"],
        "experience": objective["experience"], "payer": objective["payer_name"], "accepted_at": objective["accepted_at"],
        "state": objective["state"], "progress": progress, "submission": objective["submission"],
        "submitted_at": objective["submitted_at"], "result": objective["result"], "judged_at": objective["judged_at"],
        "paid": objective["paid"],
        "can_hand_in": objective["state"] == "active" and template.submit is not None and objective["submission"] is None,
    }


def ceo_open(conn: Connection, player_id, career: dict | None) -> bool:
    """The leadership work opens to the head of an empire at once, and to anybody at Level 40."""
    if career is None:
        return False
    if career["level"] >= data.CEO_MEMBER_LEVEL:
        return True
    seat = empires.seat_of(conn, player_id)
    return bool(seat and seat["head_player_id"] == player_id and seat["empire_status"] == "active" and seat["empire_kind"] != "pension")


def _open_to(conn: Connection, template: Template, player_id, career: dict | None) -> bool:
    if career is None:
        return False
    return template.build == career["build"] or (template.build == "ceo" and ceo_open(conn, player_id, career))


def _empire_work_done(conn: Connection, player_id, period: int) -> int:
    return _one(conn, "SELECT count(*) AS n FROM objectives WHERE player_id = %s AND period = %s AND setting = 'empire'"
                      " AND NOT terms ? 'step_id'", (player_id, period))["n"]


def board(conn: Connection, player_id, now: datetime) -> dict:
    """The player's work: what is in hand, what is on offer in each of the three settings, what is
    finished, and the syllabus map."""
    ctx = _context(conn, player_id, now)
    mine = ctx["career"]
    window = weekend(now)
    challenge = {"open": window["open"], "opens": window["opens"], "closes": window["closes"], "hours": data.WEEKEND_HOURS}
    if mine is None:
        return {"ready": False, "why": "Choose a build to see the work on offer.", "active": [], "offers": [], "finished": [],
                "skills": [], "coverage": {"learned": 0, "modules": 0}, "limit": data.MAX_ACTIVE_OBJECTIVES, "weekend": challenge,
                "tracks": [], "settings": data.SETTINGS}
    build = mine["build"]
    tracks = [build] + (["ceo"] if ceo_open(conn, player_id, mine) else [])
    rows = _rows(conn, "SELECT * FROM objectives WHERE player_id = %s AND build = %s ORDER BY id DESC LIMIT 90", (player_id, build))
    active = [_public(o) for o in rows if o["state"] == "active"]
    finished = [_public(o) for o in rows if o["state"] != "active"][:12]
    maps = {track: mastery(conn, player_id, track) for track in tracks}
    skills = []
    for track in tracks:
        for m in maps[track]:
            template = TEMPLATES[m["template"]]
            skills.append({**m, "track": track, "track_name": track_name(track), "open": mine["level"] >= template.level,
                           "stage_number": m["stage"], "stage": m["stage_name"].lower(), "finished": m["passes"]})
    again = {(k["track"], k["module"]): k["practise_again"] for k in skills}
    seat = empires.seat_of(conn, player_id)
    in_empire = bool(seat and seat["empire_status"] == "active")
    empire_done = _empire_work_done(conn, player_id, ctx["period"])
    offers = []
    why = None
    if ctx["job"] is None:
        why = "Work comes through an employer. Find a job first."
    taken = {o["template"] for o in rows if o["period"] == ctx["period"] and "step_id" not in o["terms"]}
    taken_roots = {(o["track"], o["root"]) for o in rows if o["period"] == ctx["period"] and "step_id" not in o["terms"]}
    in_hand = {o["template"] for o in rows if o["state"] == "active"}
    for template in (t for t in TEMPLATES.values() if t.build in tracks and t.listed):
        offer = {"template": template.code, "module": template.module, "title": template.title, "idea": template.idea,
                 "how": how_to(template),
                 "kind": template.kind, "level": template.level, "reward": _reward(template, ctx["wage_index_bps"]),
                 "experience": _experience(template, mine), "available": False, "why_not": None, "payer": None, "client": None,
                 "setting": template.setting, "setting_name": data.SETTINGS[template.setting], "track": template.build,
                 "practise_again": again.get((template.build, template.module), False)}
        if mine["level"] < template.level:
            offer["why_not"] = f"Opens at Level {template.level}."
        elif template.code in in_hand:
            offer["why_not"] = "You have this work in hand already."
        elif template.code in taken:
            offer["why_not"] = "Already taken this quarter. Each piece of work can be taken once a quarter."
        elif (template.build, template.root) in taken_roots:
            offer["why_not"] = ("You have worked this module in another setting this quarter. One setting of each module a quarter: "
                                "it is on offer here again next quarter.")
        elif template.payer == "empire" and not in_empire:
            offer["why_not"] = ("This work is for a Legal Counsel with a seat in an open empire." if template.code == "lw_pact"
                                else "For members of an open empire. Take a seat in one to practise this with your empire.")
        elif template.payer == "empire" and empire_done >= data.EMPIRE_WORK_A_QUARTER:
            offer["why_not"] = (f"You have done {data.EMPIRE_WORK_A_QUARTER} pieces of work for your empire this quarter, "
                                f"which is the most one member may.")
        elif template.setting == "live" and not window["open"]:
            offer["why_not"] = f"Weekend challenges open on {window['opens']:%A %d %B} at {window['opens']:%H:%M} (Lagos time)."
        elif ctx["job"] is None and template.payer != "empire" and template.code not in _client_pieces():
            offer["why_not"] = "Work comes through an employer. Find a job first."
        else:
            terms = template.offer(ctx)
            payer = terms and _payer(conn, ctx, template, terms)
            if terms is None:
                offer["why_not"] = "Not on offer at this point in the quarter."
            elif payer is None:
                offer["why_not"] = "Nobody with the cash to pay for it is asking for this work at the moment."
            else:
                if template.setting == "live" and template.submit is not None:
                    # The clock starts when the work is taken on, so the client and the figures are not shown before.
                    offer.update(available=True, payer=None, client=None, pass_when=terms["pass_when"], deadline=terms["deadline"],
                                 situation="The client and the figures are drawn and shown the moment you take the challenge on. "
                                           "The clock starts then.")
                else:
                    offer.update(available=True, payer=payer["name"], client=terms.get("client"), situation=terms["situation"],
                                 pass_when=terms["pass_when"], deadline=terms["deadline"])
        offers.append(offer)
    own = maps[build]
    return {"ready": ctx["job"] is not None, "why": why, "active": active, "offers": offers, "finished": finished, "skills": skills,
            "coverage": {"learned": sum(1 for s in own if s["learned"]), "modules": len(own)},
            "tracks": [coverage(conn, player_id, track) for track in tracks],
            "limit": data.MAX_ACTIVE_OBJECTIVES, "weekend": challenge, "settings": data.SETTINGS,
            "in_empire": in_empire, "empire_work": {"done": empire_done, "most": data.EMPIRE_WORK_A_QUARTER}}


def accept(conn: Connection, player_id, code: str, now: datetime, step: dict | None = None, *, approved: bool = False) -> dict:
    """Take on a piece of work. Its terms are fixed at this moment.

    `step` is given only by the empires module, when the work is a step in an empire's task: the
    company is then the one the task is about, and the empire pays. Work the empire pays for that would take a desk
    past what is left of its budget for the quarter waits for the head's approval (the gap stage); `approved` is given
    when the head has approved it."""
    template = TEMPLATES.get(code)
    with conn.transaction():
        try:
            careers.books_open(conn, now)
        except careers.CareerError as closing:
            raise ObjectiveError(str(closing)) from None
        _one(conn, "SELECT id FROM players WHERE id = %s FOR UPDATE", (player_id,))
        ctx = _context(conn, player_id, now)
        if step:
            ctx.update(step=step, target=step["target"])
        mine = ctx["career"]
        if template is None or mine is None or not _open_to(conn, template, player_id, mine) or (not template.listed and not step):
            raise ObjectiveError("That work is not open to your build.")
        if template.setting == "live" and not weekend(now)["open"]:
            raise ObjectiveError("Weekend challenges are open from Friday 18:00 to Sunday 22:00 (Lagos time).")
        if template.payer == "empire" and not step and _empire_work_done(conn, player_id, ctx["period"]) >= data.EMPIRE_WORK_A_QUARTER:
            raise ObjectiveError(f"One member may do {data.EMPIRE_WORK_A_QUARTER} pieces of work for their empire in a quarter.")
        if ctx["job"] is None and not step and template.payer != "empire" and template.code not in _client_pieces():
            raise ObjectiveError("Work comes through an employer. Find a job first.")
        if mine["level"] < template.level and not step:
            raise ObjectiveError(f"That work opens at Level {template.level}.")
        if _one(conn, "SELECT count(*) AS n FROM objectives WHERE player_id = %s AND state = 'active'", (player_id,))["n"] \
                >= data.MAX_ACTIVE_OBJECTIVES:
            raise ObjectiveError(f"You can have {data.MAX_ACTIVE_OBJECTIVES} pieces of work in hand at once. Finish one first.")
        if _one(conn, "SELECT 1 FROM objectives WHERE player_id = %s AND template = %s AND state = 'active'", (player_id, code)):
            raise ObjectiveError("You have this work in hand already. Finish it before taking it on again.")
        if not step:
            before = _one(conn, "SELECT template FROM objectives WHERE player_id = %s AND track = %s AND root = %s AND period = %s"
                                " AND NOT terms ? 'step_id'", (player_id, template.build, template.root, ctx["period"]))
            if before and before["template"] == code:
                raise ObjectiveError("You have already taken this work this quarter. Each piece can be taken once a quarter.")
            if before:
                raise ObjectiveError("You have already taken this module's work this quarter, in another setting. Each module can be "
                                     "worked in one setting a quarter: alone, with your empire, or in the weekend challenge.")
        if template.payer == "empire" and not step:
            seat = empires.seat_of(conn, player_id)
            if seat is None or seat["empire_status"] != "active":
                raise ObjectiveError("That work is for members of an open empire. Take a seat in one first.")
        terms = template.offer(ctx)
        if terms is None:
            raise ObjectiveError("That work is not on offer at this point in the quarter.")
        if step:
            terms["step_id"] = step["step_id"]
        payer = _payer(conn, ctx, template, terms)
        if payer is None:
            raise ObjectiveError("Nobody with the cash to pay for it is asking for this work at the moment.")
        if template.payer == "empire" and not step and not approved:
            from simulation import firm_money
            reward = _reward(template, ctx["wage_index_bps"])
            waiting = firm_money.work_over_budget(conn, player_id, code, template.title, reward, ctx["period"], now)
            if waiting is not None:
                return waiting
        try:
            with conn.transaction():
                row = _one(
                    conn,
                    "INSERT INTO objectives (player_id, build, template, module, period, client_company_id, payer_account_id, payer_name,"
                    " title, terms, reward, experience, accepted_at, setting, track, root)"
                    " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING *",
                    (player_id, mine["build"], code, template.module, ctx["period"], terms.get("company_id"), payer["account"],
                     payer["name"], template.title, Jsonb(terms), _reward(template, ctx["wage_index_bps"]),
                     _hq_experience(conn, player_id, terms, _experience(template, mine)) if (step or template.setting == "empire")
                     else _experience(template, mine), now, "empire" if step else template.setting, template.build, template.root))
        except errors.UniqueViolation:
            raise ObjectiveError("You have already taken this work this quarter.") from None
        return _public(row)


def _hq_experience(conn: Connection, player_id, terms: dict, experience: int) -> int:
    """Work for the empire teaches more in a fine headquarters, and twice as much more for a client in one of its
    city's industries (Stage 8)."""
    seat = empires.seat_of(conn, player_id)
    if seat is None:
        return experience
    from simulation import headquarters
    sector = None
    if terms.get("company_id"):
        row = _one(conn, "SELECT sector FROM companies WHERE id::text = %s", (str(terms["company_id"]),))
        sector = row["sector"] if row else None
    return apply_bps(experience, BPS + headquarters.bonus_bps(conn, seat["empire_id"], sector))


def _own(conn: Connection, player_id, objective_id: int) -> dict:
    row = _one(conn, "SELECT * FROM objectives WHERE id = %s AND player_id = %s FOR UPDATE", (objective_id, player_id))
    if row is None:
        raise ObjectiveError("There is no such piece of work.")
    if row["state"] != "active":
        raise ObjectiveError("That piece of work is finished.")
    return row


def submit(conn: Connection, player_id, objective_id: int, answers: dict, now: datetime) -> dict:
    """Hand work in. It can be handed in once."""
    with conn.transaction():
        objective = _own(conn, player_id, objective_id)
        template = TEMPLATES[objective["template"]]
        if template.submit is None:
            raise ObjectiveError("There is nothing to hand in for this work: it is judged on what you hold.")
        if objective["submission"] is not None:
            raise ObjectiveError("This work has already been handed in. It can be handed in once.")
        ctx = _context(conn, player_id, now)
        if ctx["period"] > objective["period"]:
            raise ObjectiveError("The quarter this work was for has ended.")
        fields = {f["key"] for f in objective["terms"].get("fields", [])}
        answers = {k: v for k, v in answers.items() if k in fields}
        verdict = template.submit(ctx, objective, answers)
        conn.execute("UPDATE objectives SET submission = %s, submitted_at = %s, progress = %s WHERE id = %s",
                     (Jsonb(answers), now, Jsonb(objective["progress"]), objective_id))
        if verdict is not None:
            _finish(conn, objective, verdict, now, ctx["period"])
        return _public(_one(conn, "SELECT * FROM objectives WHERE id = %s", (objective_id,)))


def withdraw(conn: Connection, player_id, objective_id: int, now: datetime) -> dict:
    """Give a piece of work up. It counts as work not passed."""
    with conn.transaction():
        objective = _own(conn, player_id, objective_id)
        ctx = _context(conn, player_id, now)
        _finish(conn, objective, _verdict("withdrawn", "You gave this work up.", [], plain="You gave this work up before it was judged.",
                                          method="", maths=""), now, ctx["period"])
        return _public(_one(conn, "SELECT * FROM objectives WHERE id = %s", (objective_id,)))


# ---------------------------------------------------------------------------
# Judging
# ---------------------------------------------------------------------------

def _finish(conn: Connection, objective: dict, verdict: dict, now: datetime, judged_period: int) -> None:
    """Record the result, have the payer pay, add the experience, and look at the player's record."""
    state = verdict["state"]
    account = ledger.player_account_id(conn, objective["player_id"])
    paid = 0
    if state == "passed":
        paid = ledger.pay_up_to(
            conn, payer=objective["payer_account_id"], receiver=account, wanted=objective["reward"], kind="professional_fee",
            memo=f"{objective['payer_name']}: {objective['title']} ({objective['module']})", reference=f"objective:{objective['id']}",
            period=judged_period)
        if paid < objective["reward"]:
            verdict["payment_note"] = (f"{objective['payer_name']} had only {_money(paid)} to pay with. A reward is paid from the "
                                       f"payer's own cash, and nobody makes up the difference.")
        careers.add_experience(conn, objective["player_id"], objective["build"], objective["experience"], now)
        from simulation import firm_people
        firm_people.apprentice_gain(conn, objective["player_id"], objective["build"], objective["experience"], now)
        conn.execute("UPDATE players SET reputation = least(reputation + 1, 100) WHERE id = %s", (objective["player_id"],))
    root = TEMPLATES[objective["template"]].root if objective["template"] in TEMPLATES else None
    if root in _client_pieces():
        # Stage 10: the editor remembers. Work given up, not handed in or done badly counts against them.
        from simulation import clients
        clients.judged(conn, objective["player_id"], _client_pieces()[root], state == "passed")
    result = {k: v for k, v in verdict.items() if k != "state"}
    seq = _one(conn, "UPDATE objectives SET state = %s, result = %s, judged_at = %s, judged_period = %s, paid = %s, progress = %s,"
                     " judged_seq = nextval('objectives_judged_seq') WHERE id = %s AND state = 'active' RETURNING judged_seq",
               (state, Jsonb(result), now, judged_period, paid, Jsonb(objective["progress"]), objective["id"]))["judged_seq"]
    _review(conn, objective, seq, now)
    if objective["terms"].get("step_id"):
        empires.step_result(conn, objective["terms"]["step_id"], state, objective["player_id"], now)
    elif state == "passed" and objective["setting"] in ("empire", "live"):
        leagues.work_passed(conn, objective, judged_period, now)
    if state == "passed":
        ranks.ceo_check(conn, objective["player_id"], now)


def _review(conn: Connection, objective: dict, seq: int, now: datetime) -> None:
    """Five failures in any ten consecutive objectives opens a performance review. The next five
    pieces of work decide it: three passes close it; otherwise the player steps down one level.
    One failed objective never does this, and the player is always told why and how to recover."""
    player, build = objective["player_id"], objective["build"]
    mine = careers.career(conn, player, build, lock=True)
    if mine["review_open"]:
        since = _rows(conn, "SELECT state FROM objectives WHERE player_id = %s AND build = %s AND judged_seq > %s",
                      (player, build, mine["review_from"]))
        passes = sum(1 for o in since if o["state"] == "passed")
        if passes >= data.REVIEW_PASSES_NEEDED:
            conn.execute("UPDATE careers SET review_open = false, reviewed_up_to = %s WHERE player_id = %s AND build = %s",
                         (seq, player, build))
            careers._event(conn, player, build, "review_closed",
                           f"Performance review closed: {passes} pieces of work passed. Well recovered.", now)
        elif len(since) >= data.REVIEW_LENGTH:
            level = mine["level"]
            floor = careers.experience_for(max(level - 1, 1))
            conn.execute("UPDATE careers SET review_open = false, reviewed_up_to = %s, experience = %s WHERE player_id = %s AND build = %s",
                         (seq, min(mine["experience"], floor), player, build))
            careers._event(conn, player, build, "demoted",
                           f"Performance review ended with {passes} of {len(since)} pieces of work passed: "
                           + (f"stepped down from Level {level} to Level {level - 1}." if level > 1 else "experience went back to the start of Level 1.")
                           + " Pass work to climb again; nothing else was lost.", now)
        return
    last = _rows(conn, "SELECT state FROM objectives WHERE player_id = %s AND build = %s AND judged_seq > %s"
                       " ORDER BY judged_seq DESC LIMIT %s", (player, build, mine["reviewed_up_to"], data.REVIEW_WINDOW))
    failures = sum(1 for o in last if o["state"] in FAILED_STATES)
    if failures >= data.REVIEW_FAILURES:
        conn.execute("UPDATE careers SET review_open = true, review_opened_at = %s, review_from = %s WHERE player_id = %s AND build = %s",
                     (now, seq, player, build))
        careers._event(conn, player, build, "review_opened",
                       f"Performance review opened: {failures} of your last {len(last)} pieces of work were not passed. "
                       f"Pass {data.REVIEW_PASSES_NEEDED} of your next {data.REVIEW_LENGTH} to close it.", now)


def _judge(conn: Connection, objective: dict, now: datetime, judged_period: int, step: str, arg) -> bool:
    """Run one objective's bell or close step, and finish it if that produced a verdict.
    The row is locked first and read again, so work handed in a moment ago is never overwritten."""
    template = TEMPLATES[objective["template"]]
    handler = getattr(template, step)
    if handler is None:
        return False
    with conn.transaction():
        locked = _one(conn, "SELECT * FROM objectives WHERE id = %s AND state = 'active' FOR UPDATE", (objective["id"],))
        if locked is None:
            return False
        if step == "bell":
            # Each objective sees each bell once, and only bells that rang after it was taken on.
            if locked["progress"].get("bell_day") == str(arg) or clock.to_lagos(locked["accepted_at"]) >= _bell_moment(arg):
                return False
            locked["progress"]["bell_day"] = str(arg)
        ctx = _context(conn, locked["player_id"], now)
        verdict = handler(ctx, locked, arg)
        if verdict is not None:
            _finish(conn, locked, verdict, now, judged_period)
        else:
            conn.execute("UPDATE objectives SET progress = %s WHERE id = %s", (Jsonb(locked["progress"]), locked["id"]))
    return True


def _safely(conn: Connection, objective: dict, now: datetime, judged_period: int, step: str, arg) -> bool:
    """One objective that cannot be judged must never stop the Closing Bell or the quarter for
    everybody else. It is left as it was, and the fault is written down for the operators."""
    try:
        return _judge(conn, objective, now, judged_period, step, arg)
    except Exception:                                              # noqa: BLE001
        if STRICT:
            raise
        log.exception("Objective %s could not be judged at its %s step.", objective["id"], step)
        return False


def at_bell(conn: Connection, now: datetime, day) -> int:
    """As a Closing Bell rings: look at what every player with market work in hand actually holds.
    Each objective sees each bell once. Returns how many objectives were looked at."""
    period = careers.world_now(conn, now)["period"]
    count = 0
    for objective in _rows(conn, "SELECT id, template FROM objectives WHERE state = 'active' ORDER BY id"):
        if TEMPLATES[objective["template"]].bell is not None and _safely(conn, objective, now, period, "bell", day):
            count += 1
    return count


def _bell_moment(day) -> datetime:
    return datetime.combine(day, clock.MARKET_CLOSE, tzinfo=clock.LAGOS)


def at_close(conn: Connection, period: int, now: datetime) -> None:
    """After a quarter has closed and every company has filed: judge the work that waited for it.
    Hand-in work that was never handed in is recorded as not done. The results count towards
    the pay day of the quarter that has just begun."""
    for objective in _rows(conn, "SELECT * FROM objectives WHERE state = 'active' AND period <= %s ORDER BY id", (period,)):
        template = TEMPLATES[objective["template"]]
        if template.close is not None:
            _safely(conn, objective, now, period + 1, "close", period)
        elif template.kind == "hand_in" and objective["submission"] is None:
            with conn.transaction():
                locked = _one(conn, "SELECT * FROM objectives WHERE id = %s AND state = 'active' FOR UPDATE", (objective["id"],))
                if locked:
                    _finish(conn, locked, _not_done("The work was not handed in before the quarter ended."), now, period + 1)
