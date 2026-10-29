"""The gap stage, Part 3: the work library brought to the design's 350 pieces.

Sixty-six new pieces of work, each in the three settings (alone, with the empire, and the weekend challenge), so 198
more templates. They fill the higher bands of each syllabus (Levels 41 to 100) and the subjects of Stages 8 and 9
(property, development, home loans, funds, swaps, preferred shares, warrants, mezzanine, earn-outs, hedging). Every piece
is practical work judged by the server from figures it gives, with a "How to do this" card (the method, never the
answer) and a debrief at three depths afterwards. Figures are drawn for each player and quarter (so nobody can copy a
neighbour's answers), and where it matters they start from the live world: the Central Bank's rate today.

Each piece is written as data: what the client asks, the figures given, the answers asked for (with how each is
worked out), and the words of the debrief.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field
from typing import Callable

from simulation import objectives as o
from simulation import world_data as data
from simulation.objectives_more import HAND_IN, _marked, _text

# ---------------------------------------------------------------------------
# The machinery
# ---------------------------------------------------------------------------

class Roll:
    """Numbers for one player, one piece of work, one quarter (and one setting: the salt)."""

    def __init__(self, ctx, code: str):
        self.seed = f"{ctx['player_id']}:{code}:{ctx['period']}:{o.SALT.get()}"
        self.n = 0

    def _next(self) -> int:
        self.n += 1
        return int.from_bytes(hashlib.sha256(f"{self.seed}:{self.n}".encode()).digest()[:8], "big")

    def int(self, low: int, high: int, step: int = 1) -> int:
        """A whole number from low to high, in steps."""
        count = (high - low) // step + 1
        return low + (self._next() % count) * step

    def pick(self, options):
        return options[self._next() % len(options)]


@dataclass
class Q:
    key: str
    label: str
    kind: str                     # percent, millions, naira, number, times, choice
    work: Callable                # (f) -> the right answer
    tol: float | None = None
    options: list = field(default_factory=list)   # for a choice: [(code, label)]


TOL = {"percent": 0.1, "millions": 0.05, "naira": 1.0, "number": 0.1, "times": 0.05}


def _rate_bps(ctx) -> int:
    row = o._one(ctx["conn"], "SELECT next_policy_rate_bps FROM economy_results ORDER BY period DESC LIMIT 1")
    return row["next_policy_rate_bps"] if row else data.NEUTRAL_RATE_BPS


def m(naira_amount: float) -> str:
    """₦ in words for the given figures: millions, to two places."""
    return f"₦{naira_amount:,.2f} million"


def pc(x: float) -> str:
    return f"{x:,.2f}%"


NEW: list = []


def piece(code: str, build: str, module: str, title: str, level: int, idea: str, setup: Callable, questions: list[Q], *,
          plain: Callable, method: str, maths: Callable, need: int | None = None, reward: int = 0, experience: int = 0,
          into: list | None = None, client: str | None = None) -> None:
    """Add one piece of work. `setup(ctx, roll)` returns the brief: situation, task, given (label, text) pairs, and the
    figures `f` the answers are worked out from; or None when it cannot be offered now."""
    need = need if need is not None else max(len(questions) - 1, 1)
    reward = reward or 60_000 + level * 2_500
    experience = experience or 100 + level * 3

    def offer(ctx):
        if client is not None:
            from simulation import clients
            if not clients.offers(ctx["conn"], ctx["player_id"], client, level):
                return None
        brief = setup(ctx, Roll(ctx, code))
        if brief is None:
            return None
        if client is not None:
            brief = {**brief, "situation": clients.introduce(client) + " " + brief["situation"]}
            paper = o._one(ctx["conn"], "SELECT id FROM companies WHERE ticker = %s", (clients.PAPER[client],))
            brief["company_id"] = str(paper["id"]) if paper else None
        fields = []
        for q in questions:
            spec = {"key": q.key, "label": q.label, "kind": q.kind}
            if q.kind == "choice":
                spec["options"] = [{"code": c, "label": lbl} for c, lbl in q.options]
            fields.append(spec)
        extra = {"company_id": brief["company_id"]} if brief.get("company_id") else {}
        return {**extra, "situation": brief["situation"], "task": brief["task"],
                "pass_when": f"At least {need} of the {len(questions)} answers are right.", "deadline": HAND_IN,
                "given": [_text(label, text) for label, text in brief["given"]], "fields": fields, "figures": brief["f"]}

    def submit(ctx, objective, answers):
        f = objective["terms"]["figures"]
        truths = {q.key: q.work(f) for q in questions}
        marked = [(q.key, q.label, truths[q.key], q.tol if q.tol is not None else TOL.get(q.kind, 0.1)) for q in questions]
        return _marked(objective, answers, marked, need, plain=plain(f, truths), method=method, maths=maths(f, truths))

    submit.method_text = method          # ("How to do this": read by objectives.how_to)
    if client is not None:
        from simulation import clients
        clients.PIECES[code] = client
    (NEW if into is None else into).append(o.Template(code, build, module, title, level, reward, experience, "hand_in", idea,
                                                      "client" if client else "employer", offer, submit=submit))


def choice(key, label, work, *options) -> Q:
    return Q(key, label, "choice", work, 0, list(options))


YES_NO = (("yes", "Yes"), ("no", "No"))


def yn(flag: bool) -> str:
    return "yes" if flag else "no"


# ===========================================================================
# ACCOUNTANT (Levels 41 to 100)
# ===========================================================================

def _ac_valuation(ctx, r):
    rent = r.int(40, 400, 5)                       # ₦m a year when full
    occ = r.int(70, 98)
    costs = r.int(8, 20)
    y = max(_rate_bps(ctx) - data.PROPERTY_YIELD_BELOW_RATE_BPS, data.PROPERTY_LEAST_YIELD_BPS) / 100
    return {"situation": "A client wants a building valued for its accounts by the income method: what a buyer would pay for the rent it "
                         "earns, after costs, at the yield investors want today.",
            "task": ["Work out the yearly income after empty space and running costs.", "Divide by the yield to give the value.",
                     "Say whether the value is above or below the price the client paid."],
            "given": [("Rent a year when full", m(rent)), ("How full it is", f"{occ}%"), ("Running costs, as a share of the rent collected", f"{costs}%"),
                      ("Yield investors want", pc(y)), ("Price the client paid", m(rent * 8))],
            "f": {"rent": rent, "occ": occ, "costs": costs, "y": y, "paid": rent * 8}}


def _ac_valuation_net(f):
    return f["rent"] * f["occ"] / 100 * (1 - f["costs"] / 100)


piece("ac_income_value", "accountant", "Valuing property by its income", "Value the building from its rent", 41,
      "A building is worth the income it earns, after empty space and costs, divided by the yield investors want.", _ac_valuation,
      [Q("net", "Income a year after costs (₦m)", "millions", _ac_valuation_net),
       Q("value", "Value (₦m)", "millions", lambda f: _ac_valuation_net(f) / (f["y"] / 100)),
       choice("above", "Is the value above the price paid?", lambda f: yn(_ac_valuation_net(f) / (f["y"] / 100) > f["paid"]), *YES_NO)],
      plain=lambda f, t: f"The building earns {m(t['net'])} a year after costs, worth {m(t['value'])} at a {pc(f['y'])} yield.",
      method="Start from the rent when full, take off the empty space, then the running costs: that is the income a buyer is "
             "buying. Divide it by the yield investors want today (which moves with the Central Bank's rate). Compare the value with "
             "the price paid: the difference is a gain or a loss in the accounts.",
      maths=lambda f, t: f"{m(f['rent'])} × {f['occ']}% × (1 − {f['costs']}%) = {m(t['net'])}; ÷ {pc(f['y'])} = {m(t['value'])}.")


def _ac_lease(ctx, r):
    rent = r.int(20, 120, 5)
    years = r.int(3, 8)
    rate = (_rate_bps(ctx) + 300) / 100
    return {"situation": "Your employer sold its head office and leased it back. The lease must go on the balance sheet: the right to use "
                         "the building is an asset, and the rent still to pay is a debt, both at what the rent is worth today.",
            "task": ["Work out the lease debt: each year's rent, brought back to today at the company's borrowing rate.",
                     "Work out the first year's interest on that debt, and the first year's depreciation of the right of use "
                     "(the asset spread evenly over the lease)."],
            "given": [("Rent a year, paid at each year's end", m(rent)), ("Years of the lease", str(years)), ("Borrowing rate", pc(rate))],
            "f": {"rent": rent, "years": years, "rate": rate}}


def _annuity(payment: float, rate_pct: float, years: int) -> float:
    i = rate_pct / 100
    return payment * (1 - (1 + i) ** -years) / i


piece("ac_lease", "accountant", "Leases on the balance sheet", "Put the leaseback on the balance sheet", 45,
      "A lease is a debt: the rent still to pay, worth less than its face because it is paid later. The right to use the "
      "building is the matching asset.", _ac_lease,
      [Q("debt", "The lease debt today (₦m)", "millions", lambda f: _annuity(f["rent"], f["rate"], f["years"])),
       Q("interest", "First year's interest (₦m)", "millions", lambda f: _annuity(f["rent"], f["rate"], f["years"]) * f["rate"] / 100),
       Q("depreciation", "First year's depreciation (₦m)", "millions", lambda f: _annuity(f["rent"], f["rate"], f["years"]) / f["years"])],
      plain=lambda f, t: f"The lease is a debt of {m(t['debt'])}; the first year's interest is {m(t['interest'])} and the right of use "
                         f"wears down by {m(t['depreciation'])}.",
      method="Bring each rent payment back to today at the rate the company would pay to borrow, and add them up: that is the debt, "
             "and the asset starts at the same figure. Each year the debt grows by its interest and falls by the rent paid; the asset "
             "is spread evenly over the lease. The cost in profit is interest plus depreciation, not the rent.",
      maths=lambda f, t: f"Debt = {f['rent']} × (1 − (1 + {f['rate'] / 100:.4f})^−{f['years']}) ÷ {f['rate'] / 100:.4f} = {t['debt']:.2f}m; "
                         f"interest = {t['debt']:.2f} × {f['rate']:.2f}%; depreciation = {t['debt']:.2f} ÷ {f['years']}.")


def _ac_dilution(ctx, r):
    profit = r.int(500, 5000, 50)                  # ₦m
    shares = r.int(100, 900, 10)                   # millions
    warrants = r.int(5, 60)                        # millions
    price = r.int(20, 200)
    strike = int(price * r.int(60, 140) / 100)
    return {"situation": "The company has warrants outstanding: each lets its holder buy one new share at a set price. The accounts must "
                         "show profit per share as it is, and as it would be if every warrant worth using were used (the company buys "
                         "back shares with the money it receives, at today's price).",
            "task": ["Work out basic profit per share.", "Say whether the warrants are worth using (the price is above the strike).",
                     "Work out diluted profit per share."],
            "given": [("Profit for the year", m(profit)), ("Shares in issue", f"{shares} million"), ("Warrants outstanding", f"{warrants} million"),
                      ("Strike of each warrant", f"₦{strike}"), ("Share price today", f"₦{price}")],
            "f": {"profit": profit, "shares": shares, "warrants": warrants, "price": price, "strike": strike}}


def _diluted(f):
    if f["price"] <= f["strike"]:
        return f["profit"] / f["shares"]
    extra = f["warrants"] - f["warrants"] * f["strike"] / f["price"]
    return f["profit"] / (f["shares"] + extra)


piece("ac_dilution", "accountant", "Profit per share and dilution", "Profit per share, with the warrants", 52,
      "Warrants worth using add shares, less the shares the company could buy back with the money they bring in.", _ac_dilution,
      [Q("basic", "Basic profit per share (₦)", "naira", lambda f: f["profit"] / f["shares"], 0.01),
       choice("used", "Are the warrants worth using?", lambda f: yn(f["price"] > f["strike"]), *YES_NO),
       Q("diluted", "Diluted profit per share (₦)", "naira", _diluted, 0.01)],
      plain=lambda f, t: f"Basic profit per share is ₦{t['basic']:.2f}; diluted, ₦{t['diluted']:.2f}.",
      method="Only warrants whose strike is below today's price would be used. For those, add the new shares and take away the "
             "shares the company could buy back at today's price with the cash the holders pay in. Profit stays the same: only the "
             "number of shares changes.",
      maths=lambda f, t: f"Basic = {f['profit']} ÷ {f['shares']} = {t['basic']:.2f}. New shares = {f['warrants']} − {f['warrants']} × "
                         f"{f['strike']} ÷ {f['price']}; diluted = {f['profit']} ÷ ({f['shares']} + new) = {t['diluted']:.2f}.")


def _ac_hedge(ctx, r):
    barrels = r.int(10, 200, 10)                  # thousand barrels
    locked = r.int(60, 110)                       # $ a barrel
    spot = locked + r.int(-25, 25)
    fx = r.int(1300, 1700, 10)
    return {"situation": "An oil producer sold futures on part of next quarter's oil at a fixed price. At the quarter's end the futures are "
                         "settled in cash against the market price. The accounts show the hedge's gain or loss beside the sales.",
            "task": ["Work out the hedge's gain or loss in naira (a loss is a minus figure).", "Work out the oil's sales at the market price.",
                     "Work out what the producer received in all, per barrel, in naira."],
            "given": [("Barrels hedged and sold", f"{barrels},000"), ("Price locked by the futures", f"${locked} a barrel"),
                      ("Market price at the end", f"${spot} a barrel"), ("Naira to the dollar", f"₦{fx:,}")],
            "f": {"barrels": barrels * 1000, "locked": locked, "spot": spot, "fx": fx}}


piece("ac_hedge", "accountant", "Hedge accounting", "Book the oil hedge", 58,
      "A sold future gains when the price falls and loses when it rises: together with the oil sold, the producer gets the "
      "locked price.", _ac_hedge,
      [Q("hedge", "Hedge gain or loss (₦m)", "millions", lambda f: (f["locked"] - f["spot"]) * f["barrels"] * f["fx"] / 1e6),
       Q("sales", "Sales at the market price (₦m)", "millions", lambda f: f["spot"] * f["barrels"] * f["fx"] / 1e6),
       Q("per_barrel", "Received in all, per barrel (₦)", "naira", lambda f: f["locked"] * f["fx"], 1)],
      plain=lambda f, t: f"The hedge {'gained' if t['hedge'] >= 0 else 'lost'} {m(abs(t['hedge']))}; with sales of {m(t['sales'])} the "
                         f"producer received ₦{t['per_barrel']:,.0f} a barrel: the locked price.",
      method="A seller of futures gains the fall below the locked price and pays the rise above it, on every barrel. Add that to the "
             "sales at the market price and the result is always the locked price: that is what a hedge is for. Show the hedge "
             "beside the sales, not hidden in them.",
      maths=lambda f, t: f"Hedge = (${f['locked']} − ${f['spot']}) × {f['barrels']:,} × ₦{f['fx']:,}; sales = ${f['spot']} × "
                         f"{f['barrels']:,} × ₦{f['fx']:,}; per barrel = ${f['locked']} × ₦{f['fx']:,}.")


def _ac_deferred(ctx, r):
    profit = r.int(200, 3000, 10)
    extra = r.int(20, 400, 5)                     # tax allowances on new machines above the accounts' depreciation
    rate = data.COMPANY_TAX_BPS / 100 if hasattr(data, "COMPANY_TAX_BPS") else 30
    return {"situation": "The tax office lets the company write its new machines off faster than its accounts do. It pays less tax now and "
                         "more later. The accounts must show the tax it will owe later as a debt: deferred tax.",
            "task": ["Work out the tax paid this year (on profit less the extra allowance).", "Work out the deferred tax to add to the debts.",
                     "Work out the tax charge in the accounts (paid plus deferred)."],
            "given": [("Profit before tax in the accounts", m(profit)), ("Tax allowances above the accounts' depreciation", m(extra)),
                      ("Tax rate", pc(rate))],
            "f": {"profit": profit, "extra": extra, "rate": rate}}


piece("ac_deferred", "accountant", "Deferred tax", "Show the tax put off", 63,
      "Tax put off is still owed: the accounts show it as a debt so that the tax charge matches the profit reported.", _ac_deferred,
      [Q("paid", "Tax paid this year (₦m)", "millions", lambda f: (f["profit"] - f["extra"]) * f["rate"] / 100),
       Q("deferred", "Deferred tax added (₦m)", "millions", lambda f: f["extra"] * f["rate"] / 100),
       Q("charge", "Tax charge in the accounts (₦m)", "millions", lambda f: f["profit"] * f["rate"] / 100)],
      plain=lambda f, t: f"It pays {m(t['paid'])} now and owes {m(t['deferred'])} later: the charge is {m(t['charge'])}.",
      method="Tax is worked out on taxable profit, which the tax office's allowances can make lower than the profit in the accounts. "
             "The difference is not a saving, only a delay: book it as a deferred tax debt, so the charge always matches the profit "
             "the accounts report.",
      maths=lambda f, t: f"Paid = ({f['profit']} − {f['extra']}) × {pc(f['rate'])}; deferred = {f['extra']} × {pc(f['rate'])}; charge = paid + deferred.")


def _ac_consolidate(ctx, r):
    own = r.int(51, 90)
    sub_profit = r.int(100, 1500, 10)
    parent_profit = r.int(500, 5000, 50)
    return {"situation": "Your employer owns most, but not all, of another company. Group accounts add all of the subsidiary's profit in, "
                         "then show the part belonging to the other shareholders separately: the non-controlling interest.",
            "task": ["Work out the group's profit.", "Work out the non-controlling interest's share.", "Work out the profit belonging to the owners of the parent."],
            "given": [("Parent's own profit", m(parent_profit)), ("Subsidiary's profit", m(sub_profit)), ("The parent owns", f"{own}%")],
            "f": {"own": own, "sub": sub_profit, "parent": parent_profit}}


piece("ac_consolidate", "accountant", "Group accounts", "Consolidate the subsidiary", 70,
      "A group shows all of a subsidiary it controls, then sets aside the share that belongs to the other shareholders.", _ac_consolidate,
      [Q("group", "Group profit (₦m)", "millions", lambda f: f["parent"] + f["sub"]),
       Q("nci", "Non-controlling interest (₦m)", "millions", lambda f: f["sub"] * (100 - f["own"]) / 100),
       Q("owners", "Profit for the parent's owners (₦m)", "millions", lambda f: f["parent"] + f["sub"] * f["own"] / 100)],
      plain=lambda f, t: f"The group made {m(t['group'])}; {m(t['nci'])} belongs to the other shareholders.",
      method="Control, not ownership, decides what is added in: a subsidiary the parent controls goes in whole. Then the share of its "
             "profit owned by others is shown as theirs. Never add in only the parent's share line by line.",
      maths=lambda f, t: f"Group = {f['parent']} + {f['sub']}; NCI = {f['sub']} × {100 - f['own']}%; owners = {f['parent']} + {f['sub']} × {f['own']}%.")


def _ac_impair(ctx, r):
    book = r.int(1000, 8000, 50)
    cash = r.int(80, 900, 10)
    years = r.int(5, 12)
    rate = (_rate_bps(ctx) + 200) / 100
    sale = int(book * r.int(40, 90) / 100)
    return {"situation": "A factory's sales have fallen. The auditors want an impairment test: is the factory worth at least what the books say? "
                         "Its worth is the higher of what it would sell for and what its cash will be worth.",
            "task": ["Work out the value of its cash: the yearly cash brought back to today.", "Work out its recoverable amount (the higher of the two).",
                     "Work out the impairment to book (nought if none)."],
            "given": [("Book value", m(book)), ("Cash it earns a year", m(cash)), ("Years left", str(years)), ("Rate to use", pc(rate)),
                      ("What it would sell for", m(sale))],
            "f": {"book": book, "cash": cash, "years": years, "rate": rate, "sale": sale}}


def _recoverable(f):
    return max(_annuity(f["cash"], f["rate"], f["years"]), f["sale"])


piece("ac_impair", "accountant", "Impairment", "Test the factory for impairment", 78,
      "An asset is never carried above what it can bring in: by selling it or by using it.", _ac_impair,
      [Q("use", "Value in use (₦m)", "millions", lambda f: _annuity(f["cash"], f["rate"], f["years"])),
       Q("recoverable", "Recoverable amount (₦m)", "millions", _recoverable),
       Q("impairment", "Impairment (₦m)", "millions", lambda f: max(f["book"] - _recoverable(f), 0))],
      plain=lambda f, t: f"It can bring in {m(t['recoverable'])}: " + (f"write {m(t['impairment'])} off." if t["impairment"] else "no write-off."),
      method="Work out both ways an asset can earn its keep, by its cash in use (brought back to today) and by selling it, and take the "
             "higher. Only if the books carry it above that is the difference written off, at once and in full.",
      maths=lambda f, t: f"In use = {f['cash']} × annuity({pc(f['rate'])}, {f['years']} years) = {t['use']:.2f}; recoverable = max(that, "
                         f"{f['sale']}); impairment = {f['book']} − recoverable if positive.")


def _ac_fx(ctx, r):
    assets = r.int(5, 60)                         # $ millions
    debts = r.int(1, assets)
    opening = r.int(1200, 1500, 10)
    closing = opening + r.int(-150, 300, 10)
    return {"situation": "The group owns a company abroad whose books are in dollars. Its net assets are translated into naira at the "
                         "quarter's closing rate; the change from the opening rate goes to a translation reserve, not to profit.",
            "task": ["Work out the net assets in naira at the opening rate.", "At the closing rate.", "The translation gain or loss (a loss is a minus figure)."],
            "given": [("Assets", f"${assets} million"), ("Debts", f"${debts} million"), ("Opening rate", f"₦{opening:,} to $1"),
                      ("Closing rate", f"₦{closing:,} to $1")],
            "f": {"net": assets - debts, "opening": opening, "closing": closing}}


piece("ac_fx", "accountant", "Foreign currency", "Translate the company abroad", 86,
      "A company abroad is worth more naira when the naira weakens: the change sits in a reserve until the company is sold.", _ac_fx,
      [Q("open", "Net assets at the opening rate (₦m)", "millions", lambda f: f["net"] * f["opening"]),
       Q("close", "Net assets at the closing rate (₦m)", "millions", lambda f: f["net"] * f["closing"]),
       Q("change", "Translation gain or loss (₦m)", "millions", lambda f: f["net"] * (f["closing"] - f["opening"]))],
      plain=lambda f, t: f"Translated, the net assets moved by {m(t['change'])}.",
      method="Translate what the company abroad owns less what it owes, at the rate on each date. The difference is a translation "
             "gain or loss: it goes to a reserve in equity, not to profit, because nothing has been sold.",
      maths=lambda f, t: f"${f['net']}m × ₦{f['opening']:,} and × ₦{f['closing']:,}; change = ${f['net']}m × (₦{f['closing']:,} − ₦{f['opening']:,}).")


def _ac_cycle(ctx, r):
    sales = r.int(2000, 20000, 100)
    cost = int(sales * r.int(50, 80) / 100)
    stock = int(cost * r.int(10, 40) / 100)
    debtors = int(sales * r.int(5, 30) / 100)
    creditors = int(cost * r.int(5, 30) / 100)
    return {"situation": "The finance director wants to know how long the company's cash is tied up between paying suppliers and being paid "
                         "by customers: the cash cycle. A year is 360 days here.",
            "task": ["Days of stock (stock ÷ cost of sales × 360).", "Days customers take to pay (debtors ÷ sales × 360).",
                     "Days the company takes to pay (creditors ÷ cost of sales × 360).", "The cash cycle (stock days + customer days − supplier days)."],
            "given": [("Sales a year", m(sales)), ("Cost of sales a year", m(cost)), ("Stock", m(stock)), ("Owed by customers", m(debtors)),
                      ("Owed to suppliers", m(creditors))],
            "f": {"sales": sales, "cost": cost, "stock": stock, "debtors": debtors, "creditors": creditors}}


def _cycle(f):
    return f["stock"] / f["cost"] * 360 + f["debtors"] / f["sales"] * 360 - f["creditors"] / f["cost"] * 360


piece("ac_cycle", "accountant", "Working capital", "How long is the cash tied up?", 94,
      "Cash is tied up from the day suppliers are paid to the day customers pay: the shorter, the less borrowing the business needs.",
      _ac_cycle,
      [Q("stock_days", "Days of stock", "number", lambda f: f["stock"] / f["cost"] * 360, 0.5),
       Q("debtor_days", "Days customers take", "number", lambda f: f["debtors"] / f["sales"] * 360, 0.5),
       Q("creditor_days", "Days the company takes", "number", lambda f: f["creditors"] / f["cost"] * 360, 0.5),
       Q("cycle", "Cash cycle (days)", "number", _cycle, 1)],
      plain=lambda f, t: f"The company's cash is tied up for {t['cycle']:.0f} days.",
      method="Measure stock against what it cost, customers' debts against sales, and suppliers' bills against cost. Add the days the "
             "cash is out and take away the days the suppliers lend it for free. Each day saved frees a day's sales of cash.",
      maths=lambda f, t: f"{t['stock_days']:.1f} + {t['debtor_days']:.1f} − {t['creditor_days']:.1f} = {t['cycle']:.1f} days.")


# ===========================================================================
# ASSET MANAGER
# ===========================================================================

def _am_sharpe(ctx, r):
    rf = _rate_bps(ctx) / 100
    a_ret, a_vol = rf + r.int(2, 14), r.int(8, 35)
    b_ret, b_vol = rf + r.int(2, 14), r.int(8, 35)
    return {"situation": "Two funds are pitched to your client. The one with the higher return is not necessarily better: what matters is "
                         "the return above the Central Bank's rate for each unit of swing (the Sharpe ratio).",
            "task": ["Work out each fund's Sharpe ratio.", "Choose the better fund."],
            "given": [("Central Bank's rate", pc(rf)), ("Fund A: return, swing", f"{pc(a_ret)}, {pc(a_vol)}"),
                      ("Fund B: return, swing", f"{pc(b_ret)}, {pc(b_vol)}")],
            "f": {"rf": rf, "a_ret": a_ret, "a_vol": a_vol, "b_ret": b_ret, "b_vol": b_vol}}


def _sh(ret, vol, rf):
    return (ret - rf) / vol


piece("am_sharpe", "asset_manager", "Risk-adjusted return", "Which fund earns more for its risk?", 41,
      "Return above the safe rate, for each unit of swing: the Sharpe ratio.", _am_sharpe,
      [Q("a", "Fund A's Sharpe ratio", "number", lambda f: _sh(f["a_ret"], f["a_vol"], f["rf"]), 0.01),
       Q("b", "Fund B's Sharpe ratio", "number", lambda f: _sh(f["b_ret"], f["b_vol"], f["rf"]), 0.01),
       choice("better", "The better fund", lambda f: "a" if _sh(f["a_ret"], f["a_vol"], f["rf"]) >= _sh(f["b_ret"], f["b_vol"], f["rf"]) else "b",
              ("a", "Fund A"), ("b", "Fund B"))],
      plain=lambda f, t: f"A earns {t['a']:.2f} per unit of risk, B {t['b']:.2f}: Fund {t['better'].upper()} is better.",
      method="Take the safe rate off each fund's return: only the extra was earned by taking risk. Divide by the fund's yearly swing. "
             "The higher figure gives more reward for each unit of risk, whatever the headline return.",
      maths=lambda f, t: f"A: ({f['a_ret']:.2f} − {f['rf']:.2f}) ÷ {f['a_vol']} = {t['a']:.3f}; B: ({f['b_ret']:.2f} − {f['rf']:.2f}) ÷ {f['b_vol']} = {t['b']:.3f}.")


def _am_beta(ctx, r):
    worth = r.int(500, 5000, 50)                  # ₦m
    beta = r.int(60, 160) / 100
    index = r.int(80_000, 140_000, 100) / 100     # index points
    return {"situation": "A client's share portfolio moves with the market more or less than one for one: its beta. It wants to be protected "
                         "against a fall for a quarter by selling BSX 50 futures (each is on ₦100 a point of the index).",
            "task": ["Work out how much of the market the portfolio is like (its worth × beta).", "Work out how many futures to sell (to the nearest whole)."],
            "given": [("Portfolio worth", m(worth)), ("Its beta", f"{beta:.2f}"), ("BSX 50 future", f"{index:,.2f} points")],
            "f": {"worth": worth, "beta": beta, "index": index}}


piece("am_beta_hedge", "asset_manager", "Hedging with index futures", "How many futures protect the portfolio?", 48,
      "A portfolio with a beta of 1.2 moves like 1.2 times its worth in the market: sell that much in index futures.", _am_beta,
      [Q("exposure", "Market exposure (₦m)", "millions", lambda f: f["worth"] * f["beta"]),
       Q("contracts", "Futures to sell", "number", lambda f: round(f["worth"] * f["beta"] * 1e6 / (f["index"] * 100)), 1)],
      plain=lambda f, t: f"The portfolio is like {m(t['exposure'])} of the market: sell {t['contracts']:.0f} futures.",
      method="Multiply what the portfolio is worth by its beta: that is how much market risk it carries. Divide by what one future is "
             "on (the index level times the naira a point). Selling that many leaves only the risk peculiar to the shares chosen.",
      maths=lambda f, t: f"{f['worth']} × {f['beta']:.2f} = {t['exposure']:.2f}m; ÷ ({f['index']:,.2f} × ₦100) = {t['contracts']:.0f} contracts.")


def _am_duration(ctx, r):
    rate = _rate_bps(ctx) / 100
    coupon = r.int(8, 20)
    years = r.int(2, 6)
    move = r.pick([50, 100, 150, 200])
    return {"situation": "A pension client holds a government bond paying a coupon once a year. Before the Central Bank meets, it wants to "
                         "know how much the bond would fall if yields rose.",
            "task": ["Work out the bond's price for ₦100 of face at today's yield.", "Work out its duration (the average wait for its cash, in years).",
                     "Estimate the fall in price for the rise given (duration ÷ (1 + yield) × the rise)."],
            "given": [("Coupon", pc(coupon)), ("Years to repayment", str(years)), ("Yield today", pc(rate)), ("Rise in yields", f"{move / 100:.2f} points")],
            "f": {"coupon": coupon, "years": years, "y": rate, "move": move}}


def _bond(f):
    y = f["y"] / 100
    flows = [(t, f["coupon"] + (100 if t == f["years"] else 0)) for t in range(1, f["years"] + 1)]
    price = sum(c / (1 + y) ** t for t, c in flows)
    duration = sum(t * c / (1 + y) ** t for t, c in flows) / price
    return price, duration


piece("am_duration", "asset_manager", "Bond duration", "How far would the bond fall?", 55,
      "Duration is the average wait for a bond's cash; the longer the wait, the more its price moves when yields do.", _am_duration,
      [Q("price", "Price for ₦100 of face (₦)", "naira", lambda f: _bond(f)[0], 0.05),
       Q("duration", "Duration (years)", "number", lambda f: _bond(f)[1], 0.02),
       Q("fall", "Estimated fall (%)", "percent", lambda f: _bond(f)[1] / (1 + f["y"] / 100) * f["move"] / 100, 0.05)],
      plain=lambda f, t: f"The bond costs ₦{t['price']:.2f}; its duration is {t['duration']:.2f} years, so a {f['move'] / 100:.2f}-point rise "
                         f"takes about {t['fall']:.2f}% off.",
      method="Bring each payment back to today at the yield and add them: that is the price. Weight each payment's date by its share "
             "of the price: that average is the duration. Divide it by one plus the yield and multiply by the rise to estimate the fall.",
      maths=lambda f, t: f"Price = Σ cash ÷ (1 + {f['y'] / 100:.4f})^t = {t['price']:.2f}; duration = Σ t × cash ÷ (1 + y)^t ÷ price = "
                         f"{t['duration']:.3f}; fall ≈ {t['duration']:.3f} ÷ {1 + f['y'] / 100:.4f} × {f['move'] / 100:.2f}%.")


def _am_nav(ctx, r):
    buildings = r.int(2000, 20000, 100)
    cash = r.int(100, 2000, 10)
    owed = r.int(0, 1500, 10)
    units = r.int(500, 5000, 10)
    spread = data.PROPERTY_FUND_SPREAD_BPS / 100
    return {"situation": "A client wants units in a property fund. A unit is worth the fund's buildings and cash, less what it owes, divided "
                         "by the units in issue. Buyers pay a little above that, sellers get a little below, and the difference stays in the fund.",
            "task": ["Work out the fund's value.", "Work out one unit's value.", "Work out what a buyer pays for a unit."],
            "given": [("Buildings at today's prices", m(buildings)), ("Cash", m(cash)), ("Owed (tax, loans)", m(owed)),
                      ("Units in issue", f"{units} million"), ("Buyers pay above the value", pc(spread))],
            "f": {"b": buildings, "c": cash, "o": owed, "u": units, "s": spread}}


piece("am_fund_units", "asset_manager", "Property funds", "Price the fund's units", 44,
      "A fund's units are priced at what it owns less what it owes, so no buyer or seller takes from the others.", _am_nav,
      [Q("nav", "The fund's value (₦m)", "millions", lambda f: f["b"] + f["c"] - f["o"]),
       Q("unit", "A unit's value (₦)", "naira", lambda f: (f["b"] + f["c"] - f["o"]) / f["u"], 0.01),
       Q("buy", "A buyer pays for a unit (₦)", "naira", lambda f: (f["b"] + f["c"] - f["o"]) / f["u"] * (1 + f["s"] / 100), 0.01)],
      plain=lambda f, t: f"The fund is worth {m(t['nav'])}: ₦{t['unit']:.2f} a unit, ₦{t['buy']:.2f} to buy.",
      method="Value everything the fund owns at today's prices, take off everything it owes, and divide by the units. A buyer pays "
             "slightly more to cover the cost of putting the money to work; that small difference stays with the existing holders.",
      maths=lambda f, t: f"({f['b']} + {f['c']} − {f['o']}) ÷ {f['u']} = {t['unit']:.4f}; × (1 + {f['s']:.2f}%) = {t['buy']:.4f}.")


def _am_covered(ctx, r):
    shares = r.int(10, 200, 5)                    # thousand
    price = r.int(20, 200)
    strike = price + r.int(-10, 30)
    premium = r.int(1, 15)
    end = max(price + r.int(-40, 50), 1)
    return {"situation": "A client holds shares and writes (sells) call options on them for income: if the price ends above the strike, the "
                         "shares are given up at the strike.",
            "task": ["Work out the premium received.", "Work out the shares' value at the end, capped at the strike if called.",
                     "Work out the total at the end (shares as capped, plus the premium)."],
            "given": [("Shares held", f"{shares},000"), ("Price now", f"₦{price}"), ("Strike of the calls", f"₦{strike}"),
                      ("Premium per share", f"₦{premium}"), ("Price at the end", f"₦{end}")],
            "f": {"n": shares * 1000, "p": price, "k": strike, "prem": premium, "end": end}}


piece("am_covered_call", "asset_manager", "Option income", "Write calls on the client's shares", 60,
      "Writing calls on shares you hold brings income now and gives up the gain above the strike.", _am_covered,
      [Q("premium", "Premium received (₦m)", "millions", lambda f: f["n"] * f["prem"] / 1e6),
       Q("capped", "Shares at the end, capped (₦m)", "millions", lambda f: f["n"] * min(f["end"], f["k"]) / 1e6),
       Q("total", "Total at the end (₦m)", "millions", lambda f: f["n"] * (min(f["end"], f["k"]) + f["prem"]) / 1e6)],
      plain=lambda f, t: f"The premium brings {m(t['premium'])}; at the end the position is worth {m(t['total'])}.",
      method="The premium is kept whatever happens. If the price ends above the strike, the shares go at the strike; below it, the "
             "client keeps them at their market value. It earns most when the price ends at the strike.",
      maths=lambda f, t: f"Premium = {f['n']:,} × ₦{f['prem']}; shares = {f['n']:,} × min(₦{f['end']}, ₦{f['k']}); total = both.")


def _am_rebalance(ctx, r):
    eq, bd, pr = r.int(300, 900, 10), r.int(200, 800, 10), r.int(50, 400, 10)
    te = r.int(40, 70)
    tb = r.int(15, 100 - te - 5)
    return {"situation": "A client's mix has drifted after a quarter of price moves. Bring it back to the agreed weights.",
            "task": ["Work out the shares to buy (a sale is a minus figure).", "The bonds to buy.", "The property to buy."],
            "given": [("Shares", m(eq)), ("Bonds", m(bd)), ("Property", m(pr)),
                      ("Target weights", f"shares {te}%, bonds {tb}%, property {100 - te - tb}%")],
            "f": {"e": eq, "b": bd, "p": pr, "te": te, "tb": tb}}


def _tot(f):
    return f["e"] + f["b"] + f["p"]


piece("am_rebalance", "asset_manager", "Rebalancing", "Bring the mix back to its targets", 66,
      "Rebalancing sells what has grown past its share and buys what has fallen behind: it buys low and sells high by rule.", _am_rebalance,
      [Q("e", "Shares to buy (₦m)", "millions", lambda f: _tot(f) * f["te"] / 100 - f["e"]),
       Q("b", "Bonds to buy (₦m)", "millions", lambda f: _tot(f) * f["tb"] / 100 - f["b"]),
       Q("p", "Property to buy (₦m)", "millions", lambda f: _tot(f) * (100 - f["te"] - f["tb"]) / 100 - f["p"])],
      plain=lambda f, t: f"Shares {t['e']:+.2f}m, bonds {t['b']:+.2f}m, property {t['p']:+.2f}m: the trades add up to nothing.",
      method="Add up the whole portfolio, multiply by each target weight, and compare with what is held. Buy the shortfalls and sell the "
             "excesses: the trades always add up to nothing.",
      maths=lambda f, t: f"Total = {_tot(f)}; shares {_tot(f)} × {f['te']}% − {f['e']}; bonds {_tot(f)} × {f['tb']}% − {f['b']}; property the rest − {f['p']}.")


def _am_tracking(ctx, r):
    diffs = [r.int(-30, 30) / 10 for _ in range(4)]
    return {"situation": "A fund that follows the BSX 50 has drifted from it. The trustees want the tracking error: how far, typically, its "
                         "quarterly return differs from the index's.",
            "task": ["Work out the average difference.", "Work out the tracking error (the swing of the differences, dividing by the count less one)."],
            "given": [("Differences, fund less index, last four quarters", ", ".join(f"{d:+.1f}%" for d in diffs))],
            "f": {"d": diffs}}


def _te(d):
    mean = sum(d) / len(d)
    return math.sqrt(sum((x - mean) ** 2 for x in d) / (len(d) - 1))


piece("am_tracking", "asset_manager", "Index funds", "How closely does the fund track the index?", 75,
      "Tracking error is the swing of the gap between a fund and its index: the smaller, the closer it follows.", _am_tracking,
      [Q("mean", "Average difference (%)", "percent", lambda f: sum(f["d"]) / len(f["d"]), 0.02),
       Q("te", "Tracking error (%)", "percent", lambda f: _te(f["d"]), 0.03)],
      plain=lambda f, t: f"On average the fund was {t['mean']:+.2f}% off the index, with a tracking error of {t['te']:.2f}%.", need=2,
      method="Take each quarter's return of the fund less the index's. Their average shows a steady gap (fees, cash held); their "
             "swing (the standard deviation) shows how unreliably the fund follows. Divide by one less than the count, as for a sample.",
      maths=lambda f, t: f"Mean = {t['mean']:.3f}; tracking error = √(Σ(d − mean)² ÷ {len(f['d']) - 1}) = {t['te']:.3f}.")


def _am_real(ctx, r):
    nominal = r.int(5, 30)
    inflation = r.int(5, 30)
    return {"situation": "A client earned a good return in naira, but prices rose too. What was the return in what the money will buy?",
            "task": ["Work out the real return ((1 + return) ÷ (1 + inflation) − 1).", "Say whether the client is better off in what the money buys."],
            "given": [("Return in naira", pc(nominal)), ("Inflation over the year", pc(inflation))],
            "f": {"n": nominal, "i": inflation}}


piece("am_real_return", "asset_manager", "Inflation and real returns", "Did the client really gain?", 85,
      "A return only counts after inflation: the real return is what the money will buy.", _am_real,
      [Q("real", "Real return (%)", "percent", lambda f: ((1 + f["n"] / 100) / (1 + f["i"] / 100) - 1) * 100, 0.05),
       choice("better", "Better off in what the money buys?", lambda f: yn(f["n"] > f["i"]), *YES_NO)],
      plain=lambda f, t: f"The real return is {t['real']:.2f}%.", need=2,
      method="Divide one plus the return by one plus inflation, and take one away. Subtracting inflation from the return is only a rough "
             "guide, and a poor one when both are high, as they often are here.",
      maths=lambda f, t: f"(1 + {f['n']}%) ÷ (1 + {f['i']}%) − 1 = {t['real']:.3f}%.")


def _am_immunise(ctx, r):
    owed = r.int(500, 5000, 50)
    years = r.int(3, 10)
    rate = _rate_bps(ctx) / 100
    return {"situation": "A pension fund must pay a lump sum in some years' time. It buys a zero-coupon government bond maturing on that date, "
                         "so rate changes cannot hurt it: immunisation.",
            "task": ["Work out what to invest today (the lump sum brought back at the yield).",
                     "Work out the price of the zero-coupon bond for ₦100 of face."],
            "given": [("Lump sum owed", m(owed)), ("Years until it is due", str(years)), ("Yield on government bonds", pc(rate))],
            "f": {"o": owed, "t": years, "y": rate}}


piece("am_immunise", "asset_manager", "Matching assets to debts", "Lock in the pension payment", 95,
      "A fund that owes a fixed sum on a fixed date is safest holding a bond that pays that sum on that date.", _am_immunise,
      [Q("invest", "To invest today (₦m)", "millions", lambda f: f["o"] / (1 + f["y"] / 100) ** f["t"]),
       Q("price", "Price for ₦100 of face (₦)", "naira", lambda f: 100 / (1 + f["y"] / 100) ** f["t"], 0.02)],
      plain=lambda f, t: f"Invest {m(t['invest'])} in a bond paying out in {f['t']} years.", need=2,
      method="Bring the sum owed back to today at the yield: that is what to invest. Match the duration of what is held to the date it "
             "is owed, so a rise in rates lowers both by the same amount.",
      maths=lambda f, t: f"{f['o']} ÷ (1 + {f['y'] / 100:.4f})^{f['t']} = {t['invest']:.2f}m; ₦100 ÷ (1 + y)^{f['t']} = ₦{t['price']:.2f}.")


# ===========================================================================
# INVESTMENT BANKER
# ===========================================================================

def _ib_wacc(ctx, r):
    rate = _rate_bps(ctx) / 100
    beta = r.int(60, 160) / 100
    premium = r.int(5, 9)
    debt_rate = rate + r.int(2, 6)
    equity = r.int(30, 90)
    tax = 30
    return {"situation": "A client needs the rate to judge its projects by: what its investors and lenders expect, weighted by how much of "
                         "each it uses (WACC).",
            "task": ["Work out the cost of equity: the Central Bank's rate plus beta × the market premium.",
                     "Work out the cost of debt after tax.", "Work out the WACC."],
            "given": [("Central Bank's rate", pc(rate)), ("Beta", f"{beta:.2f}"), ("Market premium", pc(premium)),
                      ("Borrowing rate", pc(debt_rate)), ("Tax rate", pc(tax)), ("Equity's share of the funding", f"{equity}%")],
            "f": {"rf": rate, "b": beta, "mp": premium, "kd": debt_rate, "t": tax, "e": equity}}


def _ke(f):
    return f["rf"] + f["b"] * f["mp"]


def _wacc(f):
    return _ke(f) * f["e"] / 100 + f["kd"] * (1 - f["t"] / 100) * (100 - f["e"]) / 100


piece("ib_wacc", "investment_banker", "The cost of capital", "Work out the client's WACC", 41,
      "A business must earn at least what its investors and lenders expect, each weighted by its share of the funding.", _ib_wacc,
      [Q("ke", "Cost of equity (%)", "percent", _ke, 0.05),
       Q("kd", "Cost of debt after tax (%)", "percent", lambda f: f["kd"] * (1 - f["t"] / 100), 0.05),
       Q("wacc", "WACC (%)", "percent", _wacc, 0.05)],
      plain=lambda f, t: f"Equity costs {t['ke']:.2f}%, debt {t['kd']:.2f}% after tax: the WACC is {t['wacc']:.2f}%.",
      method="Equity's cost is the safe rate plus the share's beta times the extra the market pays for risk. Debt's cost is its rate, "
             "less the tax saved on interest. Weight each by its share of the funding and add.",
      maths=lambda f, t: f"Ke = {f['rf']:.2f} + {f['b']:.2f} × {f['mp']} = {t['ke']:.2f}; Kd = {f['kd']:.2f} × (1 − {f['t']}%) = {t['kd']:.2f}; "
                         f"WACC = {t['ke']:.2f} × {f['e']}% + {t['kd']:.2f} × {100 - f['e']}% = {t['wacc']:.2f}%.")


def _ib_terminal(ctx, r):
    cash = r.int(100, 2000, 10)
    growth = r.int(2, 8)
    wacc = growth + r.int(6, 14)
    years = r.int(3, 7)
    return {"situation": "In a valuation, the years beyond the forecast are summed up in one figure: the terminal value, the next year's cash "
                         "growing for ever, divided by the WACC less the growth. It must then be brought back to today.",
            "task": ["Work out the terminal value at the end of the forecast.", "Bring it back to today."],
            "given": [("Cash in the forecast's last year", m(cash)), ("Growth for ever", pc(growth)), ("WACC", pc(wacc)),
                      ("Years of the forecast", str(years))],
            "f": {"c": cash, "g": growth, "w": wacc, "n": years}}


def _tv(f):
    return f["c"] * (1 + f["g"] / 100) / ((f["w"] - f["g"]) / 100)


piece("ib_terminal", "investment_banker", "Terminal value", "Value the years beyond the forecast", 46,
      "Beyond the forecast, a business is valued as its cash growing for ever: the terminal value.", _ib_terminal,
      [Q("tv", "Terminal value (₦m)", "millions", _tv),
       Q("pv", "Brought back to today (₦m)", "millions", lambda f: _tv(f) / (1 + f["w"] / 100) ** f["n"])],
      plain=lambda f, t: f"The years beyond are worth {m(t['tv'])} then, {m(t['pv'])} today.", need=2,
      method="Grow the last year's cash by one year, then divide by the WACC less the growth rate. That value stands at the end of the "
             "forecast, so bring it back to today. The growth must stay well below the WACC, or the figure means nothing.",
      maths=lambda f, t: f"TV = {f['c']} × (1 + {f['g']}%) ÷ ({f['w']}% − {f['g']}%) = {t['tv']:.2f}; ÷ (1 + {f['w']}%)^{f['n']} = {t['pv']:.2f}.")


def _ib_lbo(ctx, r):
    price = r.int(5000, 40000, 500)
    loan = int(price * r.int(40, 55) / 100)
    mezz = int(price * r.int(5, 20) / 100)
    exit_price = int(price * r.int(110, 190) / 100)
    years = r.int(3, 6)
    repaid = int(loan * r.int(20, 60) / 100)
    return {"situation": "An empire is buying a company with a bank loan, mezzanine debt ranked after the bank, and its own money. It plans "
                         "to sell after some years. The bank's loan is partly repaid from the company's cash meanwhile; the mezzanine is repaid "
                         "at the sale with its interest rolled up.",
            "task": ["Work out the empire's own money in.", "Work out the mezzanine owed at the sale (rolled up at 20% a year).",
                     "Work out the empire's money out at the sale.", "Work out the times money (out ÷ in)."],
            "given": [("Price", m(price)), ("Bank loan", m(loan)), ("Mezzanine", m(mezz)), ("Repaid on the bank loan before the sale", m(repaid)),
                      ("Sale price", m(exit_price)), ("Years held", str(years))],
            "f": {"p": price, "l": loan, "z": mezz, "x": exit_price, "n": years, "r": repaid}}


def _lbo_out(f):
    return f["x"] - (f["l"] - f["r"]) - f["z"] * 1.2 ** f["n"]


piece("ib_lbo", "investment_banker", "Buyouts with mezzanine", "What does the buyout return?", 52,
      "Borrowing most of the price multiplies the owners' return, if the sale price covers the debts first.", _ib_lbo,
      [Q("equity", "Own money in (₦m)", "millions", lambda f: f["p"] - f["l"] - f["z"]),
       Q("mezz", "Mezzanine owed at the sale (₦m)", "millions", lambda f: f["z"] * 1.2 ** f["n"]),
       Q("out", "Own money out (₦m)", "millions", _lbo_out),
       Q("times", "Times money", "times", lambda f: _lbo_out(f) / (f["p"] - f["l"] - f["z"]), 0.02)],
      plain=lambda f, t: f"{m(t['equity'])} in becomes {m(t['out'])}: {t['times']:.2f} times the money.",
      method="The owners' money is the price less every loan. At the sale, the bank is repaid first, then the mezzanine with all its "
             "rolled-up interest, and only then the owners. Divide what they get by what they put in.",
      maths=lambda f, t: f"In = {f['p']} − {f['l']} − {f['z']}; mezzanine = {f['z']} × 1.2^{f['n']}; out = {f['x']} − ({f['l']} − {f['r']}) − mezz.")


def _ib_earnout(ctx, r):
    upfront = r.int(2000, 20000, 100)
    earn = int(upfront * r.int(10, 30) / 100)
    chance = r.int(30, 90)
    seller_weight = data.EARNOUT_SELLER_COUNTS_BPS // 100
    cash_share = r.int(30, 90)                     # the cash bid offers this share of the earn-out on top of the upfront sum
    return {"situation": "Two bids for a company: one all cash, one with part of the price as an earn-out paid a year later if the company "
                         "hits its sales target. The seller counts an earn-out at only part of its face, because it may never come.",
            "task": ["Work out what the seller counts the earn-out bid at.", "Work out what the earn-out bid is expected to cost the buyer "
                     "(the chance of paying it × the earn-out).", "Say whether the earn-out bid beats the cash bid in the seller's eyes."],
            "given": [("Earn-out bid: paid now", m(upfront)), ("Earn-out bid: paid later if the target is hit", m(earn)),
                      ("Chance the target is hit", f"{chance}%"), ("Seller counts an earn-out at", f"{seller_weight}%"),
                      ("Cash bid", m(upfront + earn * cash_share // 100))],
            "f": {"u": upfront, "e": earn, "c": chance, "w": seller_weight, "cash": upfront + earn * cash_share // 100}}


piece("ib_earnout", "investment_banker", "Earn-outs", "Is the earn-out bid the better bid?", 58,
      "An earn-out pays part of the price only if the company performs: the seller values it below its face.", _ib_earnout,
      [Q("counted", "The seller counts the bid at (₦m)", "millions", lambda f: f["u"] + f["e"] * f["w"] / 100),
       Q("expected", "Expected cost to the buyer (₦m)", "millions", lambda f: f["u"] + f["e"] * f["c"] / 100),
       choice("wins", "Does the earn-out bid win?", lambda f: yn(f["u"] + f["e"] * f["w"] / 100 > f["cash"]), *YES_NO)],
      plain=lambda f, t: f"The seller counts it at {m(t['counted'])} against a cash bid of {m(f['cash'])}; it should cost the buyer {m(t['expected'])}.",
      method="Value an earn-out two ways: as the seller sees it (a fixed discount for the risk) and as the buyer expects to pay it (the "
             "chance of paying times the amount). A good earn-out bid wins in the seller's eyes while costing the buyer less on average.",
      maths=lambda f, t: f"Counted = {f['u']} + {f['e']} × {f['w']}%; expected = {f['u']} + {f['e']} × {f['c']}%.")


def _ib_accretion(ctx, r):
    a_profit, a_shares, a_price = r.int(1000, 8000, 50), r.int(200, 1000, 10), r.int(20, 120)
    t_profit = r.int(100, 2000, 10)
    pay = int(t_profit * r.int(8, 20))
    return {"situation": "Your client will pay for a target with new shares issued at today's price. Will its profit per share go up "
                         "(accretive) or down (dilutive)?",
            "task": ["Work out the new shares issued (the price paid ÷ the share price).", "Work out profit per share after the deal.",
                     "Say whether the deal is accretive."],
            "given": [("Buyer's profit", m(a_profit)), ("Buyer's shares", f"{a_shares} million"), ("Buyer's share price", f"₦{a_price}"),
                      ("Target's profit", m(t_profit)), ("Price paid for the target", m(pay))],
            "f": {"ap": a_profit, "as": a_shares, "px": a_price, "tp": t_profit, "pay": pay}}


def _after_eps(f):
    return (f["ap"] + f["tp"]) / (f["as"] + f["pay"] / f["px"])


piece("ib_accretion", "investment_banker", "Accretion and dilution", "Does the deal lift profit per share?", 64,
      "A deal paid in shares lifts profit per share only if the target earns more for each new share than the buyer does.", _ib_accretion,
      [Q("new", "New shares (millions)", "number", lambda f: f["pay"] / f["px"], 0.05),
       Q("eps", "Profit per share after (₦)", "naira", _after_eps, 0.01),
       choice("accretive", "Is it accretive?", lambda f: yn(_after_eps(f) > f["ap"] / f["as"]), *YES_NO)],
      plain=lambda f, t: f"Profit per share goes from ₦{f['ap'] / f['as']:.2f} to ₦{t['eps']:.2f}.",
      method="Divide the price by the buyer's share price for the new shares. Add the two profits and divide by all the shares after. "
             "Compare with the buyer's profit per share before: a deal paid in expensive shares for a cheap target lifts it.",
      maths=lambda f, t: f"New shares = {f['pay']} ÷ {f['px']} = {t['new']:.2f}m; after = ({f['ap']} + {f['tp']}) ÷ ({f['as']} + {t['new']:.2f}) = {t['eps']:.3f}.")


def _ib_swap_rate(ctx, r):
    rates = [(_rate_bps(ctx) + r.int(-300, 300, 25)) / 100 for _ in range(4)]
    size = r.int(500, 5000, 100)
    spread = r.pick([25, 50, 75, 100])
    return {"situation": "A client wants to swap a floating rate for a fixed one for four quarters. A fair fixed rate makes the swap worth "
                         "nothing on the day: here, the average of the floating rates the market expects (equal weights, as the quarters are "
                         "close together).",
            "task": ["Work out the fair fixed rate.", "If the client pays your bank's fixed rate, above the fair one by the spread given, "
                     "work out the bank's margin on the swap for a quarter."],
            "given": [("Expected floating rates, quarter by quarter", ", ".join(pc(x) for x in rates)), ("Swap size", m(size)),
                      ("Bank's spread above the fair rate", f"{spread / 100:.2f} points")],
            "f": {"r": rates, "size": size, "spread": spread}}


piece("ib_swap_rate", "investment_banker", "Swap pricing", "Set the swap's fixed rate", 70,
      "A swap's fair fixed rate is the one that makes it worth nothing today: the floating rates the market expects, averaged.",
      _ib_swap_rate,
      [Q("fixed", "Fair fixed rate (%)", "percent", lambda f: sum(f["r"]) / len(f["r"]), 0.02),
       Q("margin", "Bank's margin for a quarter (₦m)", "millions", lambda f: f["size"] * f["spread"] / 10_000 / 4, 0.01)],
      plain=lambda f, t: f"The fair fixed rate is {t['fixed']:.2f}%; the spread earns the bank {m(t['margin'])} a quarter.",
      need=2,
      method="List the floating rates the market expects for each period and weight them by how long each runs (and, strictly, by when it "
             "is paid). The fair fixed rate makes both sides worth the same; anything the bank adds is its margin for the risk it takes.",
      maths=lambda f, t: f"({' + '.join(f'{x:.2f}' for x in f['r'])}) ÷ {len(f['r'])} = {t['fixed']:.3f}%; {f['size']} × {f['spread'] / 100:.2f}% ÷ 4 = {t['margin']:.3f}m.")


def _ib_residual(ctx, r):
    gdv = r.int(2000, 30000, 100)                 # what the finished building will sell for
    build = int(gdv * r.int(35, 60) / 100)
    fees = r.int(8, 15)
    profit = r.int(15, 25)
    return {"situation": "A developer asks what it can pay for a plot. Work back from what the finished building will be worth: take off "
                         "the building costs, the fees, and the profit a developer needs; what is left is what the land is worth.",
            "task": ["Work out the fees (a share of the building costs).", "Work out the developer's profit (a share of the finished value).",
                     "Work out the residual land value."],
            "given": [("Finished value", m(gdv)), ("Building costs", m(build)), ("Fees, on building costs", f"{fees}%"),
                      ("Developer's profit, on finished value", f"{profit}%")],
            "f": {"g": gdv, "b": build, "fe": fees, "p": profit}}


piece("ib_residual", "investment_banker", "Development appraisal", "What can the developer pay for the land?", 78,
      "Land is worth what is left of a finished building's value after building it and paying the developer.", _ib_residual,
      [Q("fees", "Fees (₦m)", "millions", lambda f: f["b"] * f["fe"] / 100),
       Q("profit", "Developer's profit (₦m)", "millions", lambda f: f["g"] * f["p"] / 100),
       Q("land", "Residual land value (₦m)", "millions", lambda f: f["g"] - f["b"] * (1 + f["fe"] / 100) - f["g"] * f["p"] / 100)],
      plain=lambda f, t: f"The plot is worth {m(t['land'])} to a developer.",
      method="Start at the end: what the finished building will sell for. Take off every cost of building it, the professional fees, "
             "and the profit a developer needs for the risk. The land can be worth no more than what is left.",
      maths=lambda f, t: f"{f['g']} − {f['b']} × (1 + {f['fe']}%) − {f['g']} × {f['p']}% = {t['land']:.2f}m.")


def _ib_synergy(ctx, r):
    saving = r.int(50, 800, 10)
    cost = r.int(100, 1500, 10)
    wacc = r.int(14, 24)
    premium = r.int(500, 6000, 50)
    return {"situation": "A merger will save costs every year for ever, after a one-off cost to combine the businesses. The buyer is paying a "
                         "premium over the target's market value. Is the premium covered?",
            "task": ["Work out the savings' value today (the yearly saving ÷ the WACC).", "Work out the net value of the synergies (less the one-off cost).",
                     "Say whether they cover the premium."],
            "given": [("Yearly saving, after tax", m(saving)), ("One-off cost to combine", m(cost)), ("WACC", pc(wacc)), ("Premium paid", m(premium))],
            "f": {"s": saving, "c": cost, "w": wacc, "pr": premium}}


piece("ib_synergy", "investment_banker", "Mergers and synergies", "Do the savings pay for the premium?", 88,
      "A premium is only worth paying if the combined business is worth more by at least as much.", _ib_synergy,
      [Q("pv", "Savings' value today (₦m)", "millions", lambda f: f["s"] / (f["w"] / 100)),
       Q("net", "Net value of the synergies (₦m)", "millions", lambda f: f["s"] / (f["w"] / 100) - f["c"]),
       choice("covered", "Do they cover the premium?", lambda f: yn(f["s"] / (f["w"] / 100) - f["c"] >= f["pr"]), *YES_NO)],
      plain=lambda f, t: f"The synergies are worth {m(t['net'])} net, against a premium of {m(f['pr'])}.",
      method="A saving that lasts for ever is worth the yearly amount divided by the rate. Take off what it costs to get it. If what is "
             "left is less than the premium, the buyer's shareholders pay the target's for the privilege.",
      maths=lambda f, t: f"{f['s']} ÷ {f['w']}% = {t['pv']:.2f}; − {f['c']} = {t['net']:.2f}.")


def _ib_warrant_offer(ctx, r):
    shares = r.int(200, 1000, 10)
    new = r.int(20, 200, 5)
    price = r.int(20, 150)
    discount = r.int(10, 30)
    return {"situation": "A company raises money with a rights issue at a discount. What happens to "
                         "the share price once the new shares are in (the price after the issue)?",
            "task": ["Work out the issue price.", "Work out the money raised.", "Work out the price after the issue (all the shares' value ÷ all the shares)."],
            "given": [("Shares now", f"{shares} million"), ("New shares", f"{new} million"), ("Price now", f"₦{price}"), ("Discount", f"{discount}%")],
            "f": {"s": shares, "n": new, "p": price, "d": discount}}


piece("ib_rights_price", "investment_banker", "Rights issues", "Price the rights issue", 95,
      "New shares sold below the price pull it down to a blend of the old price and the issue price.", _ib_warrant_offer,
      [Q("issue", "Issue price (₦)", "naira", lambda f: f["p"] * (1 - f["d"] / 100), 0.01),
       Q("raised", "Money raised (₦m)", "millions", lambda f: f["n"] * f["p"] * (1 - f["d"] / 100)),
       Q("after", "Price after the issue (₦)", "naira", lambda f: (f["s"] * f["p"] + f["n"] * f["p"] * (1 - f["d"] / 100)) / (f["s"] + f["n"]), 0.01)],
      plain=lambda f, t: f"Issued at ₦{t['issue']:.2f}, raising {m(t['raised'])}; the price settles near ₦{t['after']:.2f}.",
      method="The issue price is the price less the discount. After the issue, the company is worth what it was plus the money raised, "
             "spread over all the shares. Shareholders who take up their rights lose nothing; those who do not are diluted.",
      maths=lambda f, t: f"({f['s']} × {f['p']} + {f['n']} × {t['issue']:.2f}) ÷ ({f['s']} + {f['n']}) = {t['after']:.3f}.")


# ===========================================================================
# RISK MANAGER
# ===========================================================================

def _rm_stress(ctx, r):
    shares, bonds, prop_ = r.int(200, 2000, 10), r.int(200, 2000, 10), r.int(100, 1500, 10)
    s_fall, b_fall, p_fall = r.int(15, 45), r.int(3, 15), r.int(5, 30)
    return {"situation": "The board asks what a severe but plausible crisis would cost: shares, bonds and property all falling at once.",
            "task": ["Work out the loss on each.", "Work out the total loss as a share of the whole."],
            "given": [("Shares", f"{m(shares)}, falling {s_fall}%"), ("Bonds", f"{m(bonds)}, falling {b_fall}%"), ("Property", f"{m(prop_)}, falling {p_fall}%")],
            "f": {"s": shares, "b": bonds, "p": prop_, "sf": s_fall, "bf": b_fall, "pf": p_fall}}


def _stress_loss(f):
    return f["s"] * f["sf"] / 100 + f["b"] * f["bf"] / 100 + f["p"] * f["pf"] / 100


piece("rm_crisis", "risk_manager", "Crisis scenarios", "What would a crisis cost?", 41,
      "A stress test asks what a bad but plausible day would cost everything at once, not one thing at a time.", _rm_stress,
      [Q("shares", "Loss on shares (₦m)", "millions", lambda f: f["s"] * f["sf"] / 100),
       Q("total", "Total loss (₦m)", "millions", _stress_loss),
       Q("share", "Loss as a share of the whole (%)", "percent", lambda f: _stress_loss(f) / (f["s"] + f["b"] + f["p"]) * 100, 0.05)],
      plain=lambda f, t: f"The crisis would cost {m(t['total'])}, {t['share']:.2f}% of everything.",
      method="Apply each shock to what is held, all on the same day, and add the losses: in a crisis things fall together. State the "
             "loss against the whole, and against the capital that must absorb it.",
      maths=lambda f, t: f"{f['s']} × {f['sf']}% + {f['b']} × {f['bf']}% + {f['p']} × {f['pf']}% = {t['total']:.2f}m.")


def _rm_swap_exposure(ctx, r):
    notional = r.int(500, 10000, 100)
    fixed = r.int(14, 26)
    now_rate = fixed + r.int(-5, 5)
    quarters = r.int(2, 8)
    return {"situation": "Your empire receives the fixed rate on a swap with another player. If they failed, what would the empire lose? Today's "
                         "exposure is the swap's value to the empire, if positive: the difference in rates on the sum, for the quarters left.",
            "task": ["Work out the swap's value to the empire (the fixed rate less today's rate, on the sum, for the quarters left; ignore discounting).",
                     "Work out the exposure (nought if the value is negative)."],
            "given": [("Sum", m(notional)), ("Fixed rate received", pc(fixed)), ("Today's floating rate", pc(now_rate)), ("Quarters left", str(quarters))],
            "f": {"n": notional, "fx": fixed, "fl": now_rate, "q": quarters}}


piece("rm_swap_exposure", "risk_manager", "Counterparty risk", "What if the other side fails?", 47,
      "On a swap, only the side that is owing money matters: what you would lose is its value to you, if positive.", _rm_swap_exposure,
      [Q("value", "Value to the empire (₦m)", "millions", lambda f: f["n"] * (f["fx"] - f["fl"]) / 100 * f["q"] / 4),
       Q("exposure", "Exposure (₦m)", "millions", lambda f: max(f["n"] * (f["fx"] - f["fl"]) / 100 * f["q"] / 4, 0))],
      plain=lambda f, t: f"The swap is worth {m(t['value'])} to the empire; the exposure is {m(t['exposure'])}.", need=2,
      method="A swap is worth the difference between what you receive and what you pay, over the time left. If it is worth something to "
             "you, the other side owes it: that is your exposure. If it is worth less than nothing, their failure costs you nothing today.",
      maths=lambda f, t: f"{f['n']} × ({f['fx']}% − {f['fl']}%) × {f['q']} ÷ 4 = {t['value']:.2f}m.")


def _rm_fund(ctx, r):
    fund = r.int(50, 1000, 10)
    exposures = sorted([r.int(10, 600, 5) for _ in range(3)], reverse=True)
    return {"situation": "The clearing house keeps a default fund. A common rule is that it should cover the two members with the biggest "
                         "losses failing at once (beyond their margin).",
            "task": ["Work out what the two biggest would need from the fund.", "Say whether the fund covers them.", "Work out the shortfall (nought if covered)."],
            "given": [("Default fund", m(fund)), ("Losses beyond margin, three biggest members", ", ".join(m(x) for x in exposures))],
            "f": {"fund": fund, "x": exposures}}


piece("rm_default_fund", "risk_manager", "Clearing and default funds", "Is the default fund big enough?", 53,
      "A default fund should survive its two biggest members failing on the same day.", _rm_fund,
      [Q("need", "The two biggest need (₦m)", "millions", lambda f: f["x"][0] + f["x"][1]),
       choice("covered", "Does the fund cover them?", lambda f: yn(f["fund"] >= f["x"][0] + f["x"][1]), *YES_NO),
       Q("short", "Shortfall (₦m)", "millions", lambda f: max(f["x"][0] + f["x"][1] - f["fund"], 0))],
      plain=lambda f, t: f"The two biggest would need {m(t['need'])} against a fund of {m(f['fund'])}.",
      method="Take the members whose losses beyond their margin would be largest and suppose two fail at once. If the fund is smaller, the "
             "winners on the other side are paid short: raise the fees that feed the fund, or the margin, until it covers them.",
      maths=lambda f, t: f"{f['x'][0]} + {f['x'][1]} = {t['need']}; shortfall = max(that − {f['fund']}, 0).")


def _rm_homes(ctx, r):
    book = r.int(10000, 80000, 500)
    base = data.HOME_DEFAULT_BASE_BPS / 100
    rise = r.int(1, 8)
    recovery = data.HOME_RECOVERY_BPS // 100
    return {"situation": "A bank's home loans in one city. If the Central Bank raises its rate sharply, more households default. The bank's model: "
                         f"a quarter's defaults are {base:.2f}% of the book plus {data.HOME_DEFAULT_PER_RATE_POINT_BPS / 100:.2f}% for each point "
                         "the rate has risen over the year. Repossessed homes fetch part of the loan.",
            "task": ["Work out the quarter's default rate after the rise.", "Work out the loans defaulting.", "Work out the bank's loss after what the homes fetch."],
            "given": [("Home loans", m(book)), ("Rise in the rate over the year", f"{rise} points"), ("Repossessed homes fetch", f"{recovery}% of the loan")],
            "f": {"b": book, "base": base, "rise": rise, "per": data.HOME_DEFAULT_PER_RATE_POINT_BPS / 100, "rec": recovery}}


def _default_rate(f):
    return f["base"] + f["rise"] * f["per"]


piece("rm_home_loans", "risk_manager", "Mortgage credit risk", "What does a rate rise cost the bank?", 60,
      "When rates rise sharply, more households fall behind; forced sales fetch less than the loans.", _rm_homes,
      [Q("rate", "Default rate this quarter (%)", "percent", _default_rate, 0.02),
       Q("defaulted", "Loans defaulting (₦m)", "millions", lambda f: f["b"] * _default_rate(f) / 100),
       Q("loss", "Bank's loss (₦m)", "millions", lambda f: f["b"] * _default_rate(f) / 100 * (1 - f["rec"] / 100))],
      plain=lambda f, t: f"{t['rate']:.2f}% default: {m(t['defaulted'])} of loans, costing the bank {m(t['loss'])}.",
      method="Defaults follow the rise in rates and the loss of jobs. Multiply the default rate by the book for the loans that fail, "
             "then take off what the repossessed homes fetch. The forced sales also push home prices down, which lowers what the next "
             "ones fetch.",
      maths=lambda f, t: f"{f['base']:.2f} + {f['rise']} × {f['per']:.2f} = {t['rate']:.2f}%; × {f['b']} = {t['defaulted']:.2f}; × (1 − {f['rec']}%) = {t['loss']:.2f}.")


def _rm_liquidity(ctx, r):
    cash, bills, bonds = r.int(100, 1500, 10), r.int(100, 1500, 10), r.int(100, 2000, 10)
    outflows = r.int(300, 3000, 10)
    return {"situation": "Could the business pay a bad month's outflows from what it can turn into cash quickly? Cash counts in full, treasury "
                         "bills at 95%, government bonds at 85% (they would be sold in a hurry).",
            "task": ["Work out the liquid assets after the haircuts.", "Work out the coverage (liquid assets ÷ outflows).", "Say whether it passes (coverage of at least 100%)."],
            "given": [("Cash", m(cash)), ("Treasury bills", m(bills)), ("Government bonds", m(bonds)), ("A bad month's outflows", m(outflows))],
            "f": {"c": cash, "t": bills, "b": bonds, "o": outflows}}


def _liquid(f):
    return f["c"] + f["t"] * 0.95 + f["b"] * 0.85


piece("rm_cash_cover", "risk_manager", "Liquidity", "Could it pay a bad month?", 67,
      "What matters in a crisis is not what you own but what you can turn into cash quickly.", _rm_liquidity,
      [Q("liquid", "Liquid assets (₦m)", "millions", _liquid),
       Q("coverage", "Coverage (%)", "percent", lambda f: _liquid(f) / f["o"] * 100, 0.1),
       choice("pass", "Does it pass?", lambda f: yn(_liquid(f) >= f["o"]), *YES_NO)],
      plain=lambda f, t: f"It could raise {m(t['liquid'])} quickly: {t['coverage']:.1f}% of a bad month.",
      method="Count only what could be sold quickly, cut by how much it would lose in a forced sale. Compare with a bad month's payments, "
             "not an average one. Below 100%, it relies on borrowing at the worst moment.",
      maths=lambda f, t: f"{f['c']} + {f['t']} × 95% + {f['b']} × 85% = {t['liquid']:.2f}; ÷ {f['o']} = {t['coverage']:.1f}%.")


def _rm_concentration(ctx, r):
    w = [r.int(5, 40) for _ in range(4)]
    total = sum(w)
    weights = [round(x * 100 / total, 1) for x in w]
    weights[-1] = round(100 - sum(weights[:-1]), 1)
    return {"situation": "How concentrated is the loan book? The Herfindahl index adds up the squares of each borrower's share (in percent): "
                         "10,000 is one borrower, 2,500 is four equal ones.",
            "task": ["Work out the index.", "Work out the number of equal borrowers it is like (10,000 ÷ the index).", "Say whether it is concentrated (index above 3,000)."],
            "given": [("Shares of the book", ", ".join(f"{x:.1f}%" for x in weights))],
            "f": {"w": weights}}


def _hhi(f):
    return sum(x * x for x in f["w"])


piece("rm_concentration", "risk_manager", "Concentration risk", "Is the loan book too concentrated?", 74,
      "Many small loans fail independently; a few big ones can sink the lender together.", _rm_concentration,
      [Q("hhi", "Herfindahl index", "number", _hhi, 2), Q("equal", "Like this many equal borrowers", "number", lambda f: 10_000 / _hhi(f), 0.02),
       choice("concentrated", "Is it concentrated?", lambda f: yn(_hhi(f) > 3000), *YES_NO)],
      plain=lambda f, t: f"The index is {t['hhi']:.0f}: like {t['equal']:.2f} equal borrowers.",
      method="Square each borrower's share in percent and add them: the larger the figure, the more the book depends on a few names. "
             "Dividing 10,000 by it gives the number of equal borrowers that would be as diversified.",
      maths=lambda f, t: f"{' + '.join(f'{x:.1f}²' for x in f['w'])} = {t['hhi']:.0f}; 10,000 ÷ {t['hhi']:.0f} = {t['equal']:.2f}.")


def _rm_el(ctx, r):
    ead = r.int(100, 5000, 10)
    pd = r.int(1, 15)
    lgd = r.int(30, 80)
    return {"situation": "Price a loan for its risk: the expected loss is the chance of default × the share lost if it defaults × what is owed.",
            "task": ["Work out the expected loss.", "Work out the extra rate needed to cover it (expected loss ÷ the loan)."],
            "given": [("Owed at default", m(ead)), ("Chance of default in a year", f"{pd}%"), ("Share lost if it defaults", f"{lgd}%")],
            "f": {"e": ead, "p": pd, "l": lgd}}


piece("rm_expected_loss", "risk_manager", "Expected loss", "Price the loan for its risk", 82,
      "Expected loss = chance of default × share lost × amount owed: the cost of risk a lender must charge for.", _rm_el,
      [Q("el", "Expected loss (₦m)", "millions", lambda f: f["e"] * f["p"] / 100 * f["l"] / 100),
       Q("spread", "Extra rate needed (%)", "percent", lambda f: f["p"] * f["l"] / 100, 0.02)],
      plain=lambda f, t: f"The expected loss is {m(t['el'])} a year: {t['spread']:.2f}% on the loan.", need=2,
      method="Multiply the three: how likely the borrower is to fail, how much would be lost if it did, and how much would be owed then. "
             "That is a cost of lending like any other, so it belongs in the rate charged, before any profit.",
      maths=lambda f, t: f"{f['e']} × {f['p']}% × {f['l']}% = {t['el']:.2f}m; {f['p']}% × {f['l']}% = {t['spread']:.2f}%.")


def _rm_two_asset(ctx, r):
    a, b = r.int(100, 1000, 10), r.int(100, 1000, 10)
    sa, sb = r.int(10, 40), r.int(10, 40)
    rho = r.int(-5, 9) / 10
    return {"situation": "Two positions do not always move together. Their combined risk depends on how closely they move: the correlation.",
            "task": ["Work out each position's yearly swing in naira.", "Work out the combined swing: √(a² + b² + 2 × correlation × a × b).",
                     "Work out the saving from diversification (the sum of the two less the combined)."],
            "given": [("Position A", f"{m(a)}, swing {sa}% a year"), ("Position B", f"{m(b)}, swing {sb}% a year"), ("Correlation", f"{rho:.1f}")],
            "f": {"a": a * sa / 100, "b": b * sb / 100, "rho": rho}}


def _combined(f):
    return math.sqrt(f["a"] ** 2 + f["b"] ** 2 + 2 * f["rho"] * f["a"] * f["b"])


piece("rm_diversify", "risk_manager", "Correlation and diversification", "How much does mixing them save?", 90,
      "Two risks that do not move together add up to less than their sum.", _rm_two_asset,
      [Q("sum", "The two swings added (₦m)", "millions", lambda f: f["a"] + f["b"]), Q("combined", "Combined swing (₦m)", "millions", _combined),
       Q("saving", "Saving from diversification (₦m)", "millions", lambda f: f["a"] + f["b"] - _combined(f))],
      plain=lambda f, t: f"Together they swing {m(t['combined'])}, not {m(t['sum'])}: diversification saves {m(t['saving'])}.",
      method="Turn each swing into naira. Combine them with the correlation: at 1 they simply add; below 1 the total is less; at −1 they "
             "can cancel. The gap between the sum and the combined figure is what diversification is worth.",
      maths=lambda f, t: f"√({f['a']:.2f}² + {f['b']:.2f}² + 2 × {f['rho']:.1f} × {f['a']:.2f} × {f['b']:.2f}) = {t['combined']:.3f}.")


def _rm_gap(ctx, r):
    ra = r.int(500, 5000, 50)
    rl = r.int(500, 5000, 50)
    move = r.pick([1, 2, 3])
    return {"situation": "A bank's assets and debts that reprice within a year: if rates rise, interest on both changes. The gap tells which way "
                         "the bank's income moves.",
            "task": ["Work out the gap (assets repricing − debts repricing).", "Work out the change in a year's interest income for the rise given.",
                     "Say whether a rise helps the bank."],
            "given": [("Assets repricing within a year", m(ra)), ("Debts repricing within a year", m(rl)), ("Rise in rates", f"{move} points")],
            "f": {"a": ra, "l": rl, "m": move}}


piece("rm_rate_gap", "risk_manager", "Interest-rate risk", "Does a rate rise help the bank?", 98,
      "A bank whose loans reprice faster than its deposits gains when rates rise, and loses when they fall.", _rm_gap,
      [Q("gap", "Gap (₦m)", "millions", lambda f: f["a"] - f["l"]), Q("change", "Change in interest income (₦m)", "millions", lambda f: (f["a"] - f["l"]) * f["m"] / 100),
       choice("helps", "Does a rise help?", lambda f: yn(f["a"] > f["l"]), *YES_NO)],
      plain=lambda f, t: f"The gap is {m(t['gap'])}: a {f['m']}-point rise changes income by {m(t['change'])}.",
      method="Set what reprices on the assets side against what reprices on the debts side within the year. Multiply the gap by the move "
             "in rates: a positive gap gains from a rise, a negative one loses. Match the two to stop worrying about rates.",
      maths=lambda f, t: f"({f['a']} − {f['l']}) × {f['m']}% = {t['change']:.2f}m.")


# ===========================================================================
# LEGAL COUNSEL
# ===========================================================================

def _lw_zoning(ctx, r):
    zone = r.pick(list(data.ZONES))
    want = r.pick(["home", "office", "shop", "factory", "warehouse", "hotel", "mall", "farmland"])
    return {"situation": f"A client wants to put up {data.PROPERTY_KIND_NAMES[want].lower()} on a plot zoned {data.ZONE_NAMES[zone].lower()}. "
                         "What may stand on each zone is set by the planning office.",
            "task": ["Say whether the plan fits the zone.", "Say whether the client must ask the planning office to rezone before building."],
            "given": [("The plot's zone", data.ZONE_NAMES[zone]), ("The plan", data.PROPERTY_KIND_NAMES[want]),
                      ("What each zone allows", "; ".join(f"{data.ZONE_NAMES[z]}: {', '.join(data.PROPERTY_KIND_NAMES[k].lower() for k in data.ZONE_ALLOWS[z])}"
                                                          for z in data.ZONES))],
            "f": {"zone": zone, "want": want}}


piece("lw_zoning", "lawyer", "Zoning", "May the client build it here?", 41,
      "A building must fit its plot's zone; if it does not, the zone must be changed first.", _lw_zoning,
      [choice("fits", "Does the plan fit the zone?", lambda f: yn(f["want"] in data.ZONE_ALLOWS[f["zone"]]), *YES_NO),
       choice("rezone", "Must the client ask to rezone first?", lambda f: yn(f["want"] not in data.ZONE_ALLOWS[f["zone"]]), *YES_NO)],
      plain=lambda f, t: f"{data.PROPERTY_KIND_NAMES[f['want']]} {'fits' if t['fits'] == 'yes' else 'does not fit'} a {data.ZONE_NAMES[f['zone']].lower()} zone.",
      need=2,
      method="Read the zone first, before the price or the design: a plan the zone does not allow cannot be built until the planning office "
             "rezones the plot, and it decides by what the city needs, not by what the client wants.",
      maths=lambda f, t: f"Allowed on {data.ZONE_NAMES[f['zone']].lower()}: {', '.join(data.ZONE_ALLOWS[f['zone']])}.")


def _lw_claims(ctx, r):
    price = r.int(100, 3000, 10)
    loan = int(price * r.int(5, 20) / 100) if r.int(0, 1) else 0
    way = r.int(0, 1)
    dispute = r.int(0, 2) == 0
    return {"situation": "The claims search on a building your client is buying came back. Advise what the client faces after buying it.",
            "task": ["Work out what the client must pay off on an old loan (nought if none).", "Work out what a right of way takes off the price "
                     f"({data.CLAIM_RIGHT_OF_WAY_CUT_BPS // 100}% of it, nought if none).", "Say whether the client could build, sell or lease it at once."],
            "given": [("Price", m(price)), ("Old loan secured on it", m(loan) if loan else "None"), ("Right of way", "Yes" if way else "No"),
                      ("Family dispute recorded", "Yes" if dispute else "No")],
            "f": {"p": price, "loan": loan, "way": way, "dispute": dispute}}


piece("lw_claims_advice", "lawyer", "Claims on land", "Advise on the claims search", 45,
      "An old loan must be paid off, a right of way lowers the value, and a dispute freezes the property until settled.", _lw_claims,
      [Q("loan", "To pay off (₦m)", "millions", lambda f: f["loan"]), Q("cut", "Taken off by a right of way (₦m)", "millions",
                                                                         lambda f: f["p"] * data.CLAIM_RIGHT_OF_WAY_CUT_BPS / 10_000 if f["way"] else 0),
       choice("free", "Could the client deal with it at once?", lambda f: yn(not f["dispute"]), *YES_NO)],
      plain=lambda f, t: "A dispute freezes it until settled." if f["dispute"] else "Nothing freezes it.",
      method="Read every entry on the claims search, not only the title. A loan secured on the land follows the land: the new owner pays it. "
             "A right of way is permanent and lowers the value. A dispute freezes everything until it is settled; price all three before "
             "agreeing the terms.",
      maths=lambda f, t: f"Loan {f['loan']}; right of way {f['p']} × {data.CLAIM_RIGHT_OF_WAY_CUT_BPS / 100:.0f}% if any.")


def _lw_fees(ctx, r):
    price = r.int(50, 5000, 10)
    return {"situation": "A private purchase of land needs the Governor's consent and registration at the Land Registry, each with its fee "
                         "on the price. Give the client the total cost of the purchase.",
            "task": ["Work out the consent fee.", "Work out the registration fee.", "Work out the total cost, price included."],
            "given": [("Price", m(price)), ("Consent fee", pc(data.CONSENT_FEE_BPS / 100)), ("Registration fee", pc(data.REGISTRATION_FEE_BPS / 100))],
            "f": {"p": price}}


piece("lw_consent", "lawyer", "Consent and registration", "What will the purchase cost in all?", 50,
      "A land purchase is not complete without the Governor's consent and registration, and both cost money.", _lw_fees,
      [Q("consent", "Consent fee (₦m)", "millions", lambda f: f["p"] * data.CONSENT_FEE_BPS / 10_000),
       Q("registration", "Registration fee (₦m)", "millions", lambda f: f["p"] * data.REGISTRATION_FEE_BPS / 10_000),
       Q("total", "Total cost (₦m)", "millions", lambda f: f["p"] * (1 + (data.CONSENT_FEE_BPS + data.REGISTRATION_FEE_BPS) / 10_000))],
      plain=lambda f, t: f"In all the purchase costs {m(t['total'])}.",
      method="Budget for every step of the purchase: the consent, which takes days, and the registration, which makes the client the owner "
             "on the record. A purchase never registered leaves the seller as the owner in law.",
      maths=lambda f, t: f"{f['p']} × {data.CONSENT_FEE_BPS / 100:.2f}% and × {data.REGISTRATION_FEE_BPS / 100:.2f}%; total = price + both.")


def _lw_closeout(ctx, r):
    swaps = [r.int(-300, 300, 5) for _ in range(3)]
    return {"situation": "The other side to three swaps with your client has failed. Under the master agreement, all three are closed out and "
                         "netted into one figure: what one side owes the other.",
            "task": ["Work out the net amount (a figure owed to your client is positive).", "Say whether your client is owed money."],
            "given": [("Values to your client of the three swaps", ", ".join(m(x) for x in swaps))],
            "f": {"s": swaps}}


piece("lw_closeout", "lawyer", "Netting on default", "Close out the swaps", 56,
      "Netting turns many contracts with a failed side into one sum, so a liquidator cannot pick the ones it likes.", _lw_closeout,
      [Q("net", "Net amount (₦m)", "millions", lambda f: sum(f["s"])),
       choice("owed", "Is your client owed money?", lambda f: yn(sum(f["s"]) > 0), *YES_NO)],
      plain=lambda f, t: f"Netted, the figure is {m(t['net'])}.", need=2,
      method="On default, value every contract under the agreement at once and add them, gains and losses alike. Without netting, the "
             "liquidator would collect what your client owes and leave your client queueing for what it is owed.",
      maths=lambda f, t: f"{' + '.join(str(x) for x in f['s'])} = {t['net']}.")


def _lw_waterfall(ctx, r):
    sale = r.int(1000, 10000, 50)
    bank = int(sale * r.int(30, 70) / 100)
    mezz = int(sale * r.int(10, 30) / 100)
    return {"situation": "A bought-out company is sold in distress. The agreements rank who is paid first: the bank, then the mezzanine lender, "
                         "then the owners.",
            "task": ["Work out what the bank gets.", "What the mezzanine lender gets.", "What the owners get."],
            "given": [("Sale proceeds", m(sale)), ("Owed to the bank", m(bank)), ("Owed to the mezzanine lender", m(mezz))],
            "f": {"s": sale, "b": bank, "z": mezz}}


piece("lw_waterfall", "lawyer", "Ranking of debts", "Who is paid from the sale?", 62,
      "Debts are paid in order of rank: each class is paid in full before the next gets anything.", _lw_waterfall,
      [Q("bank", "The bank gets (₦m)", "millions", lambda f: min(f["s"], f["b"])),
       Q("mezz", "The mezzanine lender gets (₦m)", "millions", lambda f: min(max(f["s"] - f["b"], 0), f["z"])),
       Q("owners", "The owners get (₦m)", "millions", lambda f: max(f["s"] - f["b"] - f["z"], 0))],
      plain=lambda f, t: f"Bank {m(t['bank'])}, mezzanine {m(t['mezz'])}, owners {m(t['owners'])}.",
      method="Pay each rank in full before moving down: the bank first, then the mezzanine lender, then the owners. A lender lower down "
             "charges more because it is the first to lose; the owners are paid only what is left.",
      maths=lambda f, t: f"Bank min({f['s']}, {f['b']}); mezzanine min(rest, {f['z']}); owners what remains.")


def _lw_lease(ctx, r):
    rent = r.int(10, 200, 5)
    missed = r.int(0, 3)
    return {"situation": f"Your client leased back its building. The lease is broken if {data.LEASEBACK_MISSES_TO_BREAK} rents are missed; "
                         "what was missed is owed whatever happens.",
            "task": ["Work out what is owed for missed rent.", "Say whether the lease is broken."],
            "given": [("Rent a quarter", m(rent)), ("Rents missed", str(missed))],
            "f": {"r": rent, "m": missed}}


piece("lw_lease_break", "lawyer", "Leases", "Is the lease broken?", 68,
      "A lease set a number of missed rents that ends it; the rent owed stays owed.", _lw_lease,
      [Q("owed", "Owed for missed rent (₦m)", "millions", lambda f: f["r"] * f["m"]),
       choice("broken", "Is the lease broken?", lambda f: yn(f["m"] >= data.LEASEBACK_MISSES_TO_BREAK), *YES_NO)],
      plain=lambda f, t: f"{m(t['owed'])} is owed; the lease {'is' if t['broken'] == 'yes' else 'is not'} broken.", need=2,
      method="Read the default clause for its trigger and its consequence separately. Breaking the lease ends the client's use of the "
             "building; it does not wipe out the rent already owed, which the landlord can still claim.",
      maths=lambda f, t: f"{f['r']} × {f['m']} = {t['owed']}.")


def _lw_insolvency(ctx, r):
    assets = r.int(500, 8000, 50)
    secured = int(assets * r.int(20, 70) / 100)
    staff = r.int(20, 300, 5)
    unsecured = r.int(200, 6000, 50)
    return {"situation": "A company is wound up. Its assets go first to secured lenders (up to what is owed), then to staff wages owed, then "
                         "shared among unsecured creditors in proportion.",
            "task": ["Work out what is left for unsecured creditors.", "Work out the share of their claims they recover (%)."],
            "given": [("Assets realised", m(assets)), ("Secured lenders", m(secured)), ("Staff wages owed", m(staff)), ("Unsecured creditors", m(unsecured))],
            "f": {"a": assets, "s": secured, "w": staff, "u": unsecured}}


def _left(f):
    return max(f["a"] - f["s"] - f["w"], 0)


piece("lw_insolvency", "lawyer", "Winding-up and creditors", "What will the creditors recover?", 75,
      "In a winding-up, secured lenders and staff come first; unsecured creditors share what is left.", _lw_insolvency,
      [Q("left", "Left for unsecured creditors (₦m)", "millions", _left),
       Q("recovery", "Share recovered (%)", "percent", lambda f: min(_left(f) / f["u"] * 100, 100), 0.1)],
      plain=lambda f, t: f"Unsecured creditors share {m(t['left'])}: {t['recovery']:.1f}% of what they are owed.", need=2,
      method="Apply the order of payment strictly: secured lenders up to their security, then preferential claims such as wages, then "
             "the rest pro rata. A creditor's best protection is taken before the trouble starts.",
      maths=lambda f, t: f"{f['a']} − {f['s']} − {f['w']} = {t['left']}; ÷ {f['u']} = {t['recovery']:.1f}%.")


def _lw_preferred(ctx, r):
    par = r.int(500, 5000, 50)
    rate = r.int(8, 18)
    missed = r.int(0, 4)
    return {"situation": "A company's preferred shares are cumulative: a missed preferred dividend is carried forward, and must be paid in full "
                         "before the ordinary shareholders get anything.",
            "task": ["Work out a quarter's preferred dividend.", "Work out the arrears.", "Work out what must be paid before an ordinary dividend this quarter."],
            "given": [("Preferred shares at par", m(par)), ("Dividend rate a year", pc(rate)), ("Quarters missed", str(missed))],
            "f": {"p": par, "r": rate, "m": missed}}


piece("lw_preferred", "lawyer", "Preferred shares", "What must be paid before the ordinary dividend?", 84,
      "Cumulative preferred dividends pile up when missed, and come before any ordinary dividend.", _lw_preferred,
      [Q("quarter", "A quarter's preferred dividend (₦m)", "millions", lambda f: f["p"] * f["r"] / 100 / 4),
       Q("arrears", "Arrears (₦m)", "millions", lambda f: f["p"] * f["r"] / 100 / 4 * f["m"]),
       Q("before", "To pay first (₦m)", "millions", lambda f: f["p"] * f["r"] / 100 / 4 * (f["m"] + 1))],
      plain=lambda f, t: f"{m(t['before'])} must be paid before the ordinary shares see a kobo.",
      method="Read whether the preferred shares are cumulative. If so, every missed dividend is carried forward, and the arrears plus "
             "this quarter's dividend must be paid before the ordinary shareholders are paid anything.",
      maths=lambda f, t: f"{f['p']} × {f['r']}% ÷ 4 = {t['quarter']:.2f}; × {f['m']} missed; plus this quarter's.")


def _lw_earnout(ctx, r):
    earn = r.int(100, 3000, 10)
    target = r.int(1000, 10000, 50)
    sales = int(target * r.int(50, 130) / 100)
    return {"situation": "The seller of a company claims its earn-out. The agreement says: paid in full if the company's sales over the year reach "
                         "the target; in proportion if less. The seller says the buyer held sales back.",
            "task": ["Work out the earn-out due under the agreement.", "Say whether the buyer must pay in full."],
            "given": [("Earn-out", m(earn)), ("Sales target", m(target)), ("Sales achieved", m(sales))],
            "f": {"e": earn, "t": target, "s": sales}}


piece("lw_earnout", "lawyer", "Earn-out disputes", "What is the seller owed?", 94,
      "An earn-out pays what the agreement's formula says on the figures reported; manipulating them is a claim of its own.", _lw_earnout,
      [Q("due", "Earn-out due (₦m)", "millions", lambda f: f["e"] if f["s"] >= f["t"] else f["e"] * f["s"] / f["t"]),
       choice("full", "In full?", lambda f: yn(f["s"] >= f["t"]), *YES_NO)],
      plain=lambda f, t: f"The seller is owed {m(t['due'])}.", need=2,
      method="Apply the formula to the figures exactly as agreed. If the seller says the buyer held sales back, that is a separate claim "
             "for breach of the duty to run the business fairly, and needs evidence; it does not change what the formula gives.",
      maths=lambda f, t: f"{f['e']} × min({f['s']} ÷ {f['t']}, 1) = {t['due']:.2f}.")


# ===========================================================================
# FINANCIAL JOURNALIST
# ===========================================================================

def _jn_index(ctx, r):
    before, after = r.int(9000, 14000, 10), r.int(9000, 14000, 10)
    return {"situation": "The property price index for a district moved this quarter. Write it up accurately: the change, and the right headline.",
            "task": ["Work out the change (%).", "Choose the headline."],
            "given": [("Index last quarter", f"{before / 100:.2f}"), ("Index this quarter", f"{after / 100:.2f}")],
            "f": {"b": before, "a": after}}


piece("jn_property_index", "journalist", "Reporting property prices", "Write up the district's prices", 41,
      "A change is reported against the earlier figure, and the headline must match its size.", _jn_index,
      [Q("change", "Change (%)", "percent", lambda f: (f["a"] - f["b"]) / f["b"] * 100, 0.05),
       choice("headline", "Headline", lambda f: "boom" if (f["a"] - f["b"]) / f["b"] >= 0.1 else ("slump" if (f["a"] - f["b"]) / f["b"] <= -0.1 else "steady"),
              ("boom", "Prices boom"), ("slump", "Prices slump"), ("steady", "Prices steady"))],
      plain=lambda f, t: f"Prices moved {t['change']:+.2f}%.", need=2,
      method="Measure the change against last quarter's figure, not this one's. Keep words like 'boom' and 'slump' for moves of a tenth or "
             "more; a smaller move is news only with context.",
      maths=lambda f, t: f"({f['a'] / 100:.2f} − {f['b'] / 100:.2f}) ÷ {f['b'] / 100:.2f} = {t['change']:.2f}%.")


def _jn_infra(ctx, r):
    uplift = r.pick([1200, 1800, 2200])
    done = r.int(0, 4)
    length = 4
    return {"situation": "A big public project is going up beside a district. Readers want to know how much of its effect on prices has already "
                         "happened. The rule of thumb: a quarter of the gain on the announcement, the rest as the works progress.",
            "task": ["Work out the gain priced in so far (%).", "Work out the gain still to come (%)."],
            "given": [("Gain expected when finished", pc(uplift / 100)), ("Quarters of works done", f"{done} of {length}")],
            "f": {"u": uplift / 100, "d": done, "l": length}}


def _so_far(f):
    return f["u"] if f["d"] >= f["l"] else f["u"] / 4 + f["u"] * 3 / 4 * f["d"] / f["l"]


piece("jn_infrastructure", "journalist", "Reporting public works", "How much has the project lifted prices?", 46,
      "Markets price a project in as it becomes certain, not on opening day.", _jn_infra,
      [Q("so_far", "Gain priced in so far (%)", "percent", _so_far, 0.02),
       Q("to_come", "Gain still to come (%)", "percent", lambda f: f["u"] - _so_far(f), 0.02)],
      plain=lambda f, t: f"{t['so_far']:.2f}% is priced in; {t['to_come']:.2f}% is still to come.", need=2,
      method="Report what is already in prices, not the full headline gain: owners who bought after the announcement paid for part of it "
             "already. Say what remains and what could stop it (delays, cost overruns).",
      maths=lambda f, t: f"{f['u']:.2f} ÷ 4 + {f['u']:.2f} × ¾ × {f['d']} ÷ {f['l']} = {t['so_far']:.2f}.")


def _jn_repo(ctx, r):
    before, now = r.int(50, 2000, 10), r.int(50, 3000, 10)
    return {"situation": "Repossessions in a city this quarter and last. Report the change, and say whether it is a surge (up by half or more).",
            "task": ["Work out the change (%).", "Is it a surge?"],
            "given": [("Homes repossessed last quarter", f"{before:,}"), ("This quarter", f"{now:,}")],
            "f": {"b": before, "n": now}}


piece("jn_repossessions", "journalist", "Reporting the housing market", "Report the repossessions", 52,
      "Numbers of people hurt are reported plainly: the count, the change, and the cause.", _jn_repo,
      [Q("change", "Change (%)", "percent", lambda f: (f["n"] - f["b"]) / f["b"] * 100, 0.1),
       choice("surge", "Is it a surge?", lambda f: yn(f["n"] >= f["b"] * 1.5), *YES_NO)],
      plain=lambda f, t: f"Repossessions changed {t['change']:+.1f}%.", need=2,
      method="Give the count and the change from the last quarter, and link it to its cause (the mortgage rate, jobs) only where the figures "
             "support it. Never name a household.",
      maths=lambda f, t: f"({f['n']} − {f['b']}) ÷ {f['b']} = {t['change']:.1f}%.")


def _jn_bank_loss(ctx, r):
    profit = r.int(1000, 20000, 100)
    loss = r.int(100, 8000, 50)
    return {"situation": "A bank reports its quarter: profit before losses on loans, and the loans it wrote off. Readers want the result after "
                         "the losses, and whether the losses ate half or more of the profit.",
            "task": ["Work out the profit after loan losses.", "Work out the losses as a share of the profit before them.", "Did they eat half or more?"],
            "given": [("Profit before loan losses", m(profit)), ("Loan losses", m(loss))],
            "f": {"p": profit, "l": loss}}


piece("jn_bank_losses", "journalist", "Reporting banks", "Report the bank's losses", 58,
      "A bank's profit is what is left after the loans that will not be repaid.", _jn_bank_loss,
      [Q("after", "Profit after loan losses (₦m)", "millions", lambda f: f["p"] - f["l"]),
       Q("share", "Losses against profit (%)", "percent", lambda f: f["l"] / f["p"] * 100, 0.1),
       choice("half", "Half or more?", lambda f: yn(f["l"] >= f["p"] / 2), *YES_NO)],
      plain=lambda f, t: f"After losses of {m(f['l'])}, the bank made {m(t['after'])}.",
      method="Report the profit after loan losses, not before: that is what the owners earned. Put the losses against the profit to show "
             "their scale, and say where they came from (households, companies) if the bank says.",
      maths=lambda f, t: f"{f['p']} − {f['l']} = {t['after']}; {f['l']} ÷ {f['p']} = {t['share']:.1f}%.")


def _jn_open_interest(ctx, r):
    longs = r.int(1000, 50000, 100)
    traded = r.int(500, 30000, 100)
    return {"situation": "The clearing house publishes each contract's open interest (contracts still open) and today's trading. Write the market "
                         "item: how heavy was the trading against what is open?",
            "task": ["Work out the turnover (traded ÷ open interest, %).", "Choose the headline (heavy trading at 50% or more)."],
            "given": [("Open interest", f"{longs:,} contracts"), ("Traded today", f"{traded:,} contracts")],
            "f": {"o": longs, "t": traded}}


piece("jn_open_interest", "journalist", "Reporting derivatives", "Report the day in futures", 64,
      "Open interest counts contracts still open; trading counts those that changed hands today.", _jn_open_interest,
      [Q("turnover", "Turnover (%)", "percent", lambda f: f["t"] / f["o"] * 100, 0.1),
       choice("headline", "Headline", lambda f: "heavy" if f["t"] >= f["o"] / 2 else "quiet", ("heavy", "Heavy trading in futures"), ("quiet", "A quiet day in futures"))],
      plain=lambda f, t: f"Turnover was {t['turnover']:.1f}% of the open contracts.", need=2,
      method="Open interest says how many bets are still on; trading says how busy the day was. Their ratio shows whether positions are "
             "changing hands fast. Never say who holds them: the clearing house does not, and neither do you.",
      maths=lambda f, t: f"{f['t']:,} ÷ {f['o']:,} = {t['turnover']:.1f}%.")


def _jn_hedge(ctx, r):
    hedge = r.int(-3000, 3000, 10)
    profit = r.int(500, 10000, 50)
    return {"situation": "An airline's results include a gain or loss on its fuel hedges. Readers want to know how much of the profit came from "
                         "the hedges, and the profit from flying alone.",
            "task": ["Work out the profit before the hedges.", "Work out the hedges as a share of the reported profit (%; a loss is negative)."],
            "given": [("Reported profit", m(profit)), ("Gain on fuel hedges (negative for a loss)", m(hedge))],
            "f": {"p": profit, "h": hedge}}


piece("jn_hedging", "journalist", "Reporting hedges", "How much came from the hedges?", 70,
      "A hedge gain is not the business doing better: report the profit from the business alone beside it.", _jn_hedge,
      [Q("before", "Profit before the hedges (₦m)", "millions", lambda f: f["p"] - f["h"]),
       Q("share", "Hedges as a share of profit (%)", "percent", lambda f: f["h"] / f["p"] * 100, 0.1)],
      plain=lambda f, t: f"Without its hedges the airline made {m(t['before'])}.", need=2,
      method="Take the hedges out to show how the business itself did; then report the hedges separately. A hedge that gains when fuel is "
             "dear is doing its job, not making the airline more profitable for ever.",
      maths=lambda f, t: f"{f['p']} − ({f['h']}) = {t['before']}; {f['h']} ÷ {f['p']} = {t['share']:.1f}%.")


def _jn_pref(ctx, r):
    par = 100
    rate = r.int(10, 22)
    price = r.int(70, 130)
    gov = _rate_bps(ctx) / 100
    return {"situation": "A company's preferred shares are trading. Readers want the yield at today's price, and how it compares with a "
                         "government bond.",
            "task": ["Work out the yield (dividend ÷ price).", "Work out the extra over the government bond (points)."],
            "given": [("Dividend a year, on ₦100", f"₦{rate}"), ("Price", f"₦{price}"), ("Government bond yield", pc(gov))],
            "f": {"d": rate, "p": price, "g": gov, "par": par}}


piece("jn_preferred", "journalist", "Reporting fixed income", "Report the preferred shares' yield", 77,
      "A fixed dividend's yield moves opposite to the price: cheaper shares yield more.", _jn_pref,
      [Q("yield", "Yield (%)", "percent", lambda f: f["d"] / f["p"] * 100, 0.05),
       Q("extra", "Extra over government (points)", "number", lambda f: f["d"] / f["p"] * 100 - f["g"], 0.05)],
      plain=lambda f, t: f"At ₦{f['p']} the preferred shares yield {t['yield']:.2f}%, {t['extra']:+.2f} points over government.", need=2,
      method="Divide the fixed dividend by today's price, not by the par value. The extra over a government bond is what investors demand "
             "for the company's risk and the dividend's lower rank.",
      maths=lambda f, t: f"{f['d']} ÷ {f['p']} = {t['yield']:.2f}%; − {f['g']:.2f} = {t['extra']:.2f}.")


def _jn_breadth(ctx, r):
    up = r.pick([n for n in range(5, 46) if n != 25])
    down = 50 - up
    index = r.pick([x / 10 for x in range(-30, 31) if x != 0])
    return {"situation": "The BSX 50 moved, but how many of its fifty shares went with it? Breadth tells whether a move is broad or carried by a few.",
            "task": ["Work out the share of members that rose (%).", "Say whether the move was broad (most members moved the index's way)."],
            "given": [("Members up", str(up)), ("Members down", str(down)), ("Index change", f"{index:+.1f}%")],
            "f": {"u": up, "d": down, "i": index}}


piece("jn_breadth", "journalist", "Reporting the market", "Was the move broad?", 85,
      "An index can rise on a few big shares while most fall: breadth shows which.", _jn_breadth,
      [Q("up", "Members that rose (%)", "percent", lambda f: f["u"] / 50 * 100, 0.05),
       choice("broad", "Was the move broad?", lambda f: yn((f["i"] >= 0 and f["u"] > 25) or (f["i"] < 0 and f["d"] > 25)), *YES_NO)],
      plain=lambda f, t: f"{t['up']:.0f}% of members rose while the index moved {f['i']:+.1f}%.", need=2,
      method="Count the members moving each way. If most moved with the index, the move was broad; if not, a few large shares carried it, "
             "and the story is about them, not the whole market.",
      maths=lambda f, t: f"{f['u']} ÷ 50 = {t['up']:.0f}%.")


def _jn_real(ctx, r):
    wage = r.int(2, 30)
    inflation = r.int(5, 30)
    return {"situation": "Wages rose this year, but so did prices. Report what happened to what a wage buys.",
            "task": ["Work out the real change in wages.", "Choose the headline."],
            "given": [("Wages up", pc(wage)), ("Prices up", pc(inflation))],
            "f": {"w": wage, "i": inflation}}


piece("jn_real_wages", "journalist", "Reporting the economy", "Are workers better off?", 96,
      "A pay rise below inflation is a cut in what the pay buys.", _jn_real,
      [Q("real", "Real change in wages (%)", "percent", lambda f: ((1 + f["w"] / 100) / (1 + f["i"] / 100) - 1) * 100, 0.05),
       choice("headline", "Headline", lambda f: "better" if f["w"] > f["i"] else "worse", ("better", "Pay outpaces prices"), ("worse", "Prices outrun pay"))],
      plain=lambda f, t: f"In what it buys, pay changed {t['real']:+.2f}%.", need=2,
      method="Divide one plus the pay rise by one plus inflation and take one away. Report that, not the headline rise: it is what workers "
             "feel at the market.",
      maths=lambda f, t: f"(1 + {f['w']}%) ÷ (1 + {f['i']}%) − 1 = {t['real']:.2f}%.")


# ===========================================================================
# CEO (the leadership track)
# ===========================================================================

def _ce_npv(ctx, r):
    rate = r.int(14, 26)
    projects = []
    for name in ("A", "B", "C"):
        cost = r.int(200, 2000, 10)
        yearly = r.int(50, 700, 10)
        years = r.int(3, 8)
        projects.append({"n": name, "c": cost, "y": yearly, "t": years})
    return {"situation": "The board has money for one project. Rank them by what they add to the company's value today (net present value).",
            "task": ["Work out each project's NPV (yearly cash brought back to today, less its cost).", "Choose the project to back."],
            "given": [("Rate to use", pc(rate))] + [(f"Project {p['n']}", f"costs {m(p['c'])}, earns {m(p['y'])} a year for {p['t']} years") for p in projects],
            "f": {"r": rate, "p": projects}}


def _npv(p, rate):
    return _annuity(p["y"], rate, p["t"]) - p["c"]


piece("ce_npv", "ceo", "Choosing projects", "Which project adds most?", 61,
      "Back the project that adds most value today, not the one with the biggest profits or the quickest payback.", _ce_npv,
      [Q("a", "Project A's NPV (₦m)", "millions", lambda f: _npv(f["p"][0], f["r"])),
       Q("b", "Project B's NPV (₦m)", "millions", lambda f: _npv(f["p"][1], f["r"])),
       Q("c", "Project C's NPV (₦m)", "millions", lambda f: _npv(f["p"][2], f["r"])),
       choice("best", "Back project", lambda f: max(f["p"], key=lambda p: _npv(p, f["r"]))["n"].lower(), ("a", "A"), ("b", "B"), ("c", "C"))],
      plain=lambda f, t: f"NPVs: A {t['a']:.1f}m, B {t['b']:.1f}m, C {t['c']:.1f}m. Back {t['best'].upper()}.",
      method="Bring each project's cash back to today at the rate investors expect, and take off what it costs. Back the largest positive "
             "figure; a negative one destroys value however big its profits look.",
      maths=lambda f, t: "; ".join(f"{p['n']}: {p['y']} × annuity({f['r']}%, {p['t']}) − {p['c']}" for p in f["p"]))


def _ce_buyback(ctx, r):
    cash = r.int(500, 5000, 50)
    price = r.int(20, 200)
    shares = r.int(200, 2000, 10)
    profit = r.int(500, 8000, 50)
    return {"situation": "The company has spare cash to return. A buyback at today's price reduces the shares; profit per share rises if the cash "
                         "was earning little.",
            "task": ["Work out the shares bought back (millions).", "Work out profit per share after (ignoring interest lost on the cash)."],
            "given": [("Cash to return", m(cash)), ("Share price", f"₦{price}"), ("Shares in issue", f"{shares} million"), ("Profit a year", m(profit))],
            "f": {"c": cash, "p": price, "s": shares, "pr": profit}}


piece("ce_buyback", "ceo", "Returning cash", "Buy back shares or pay a dividend?", 66,
      "A buyback and a dividend return the same cash; a buyback at a fair price leaves every remaining owner with more of the company.",
      _ce_buyback,
      [Q("bought", "Shares bought back (millions)", "number", lambda f: f["c"] / f["p"], 0.05),
       Q("eps", "Profit per share after (₦)", "naira", lambda f: f["pr"] / (f["s"] - f["c"] / f["p"]), 0.01)],
      plain=lambda f, t: f"{t['bought']:.2f} million shares go; profit per share rises to ₦{t['eps']:.2f}.", need=2,
      method="Divide the cash by the price for the shares bought back, and spread the same profit over the fewer shares. A buyback is good "
             "for the owners who stay only if the price paid is below what a share is truly worth.",
      maths=lambda f, t: f"{f['c']} ÷ {f['p']} = {t['bought']:.2f}m; {f['pr']} ÷ ({f['s']} − {t['bought']:.2f}) = {t['eps']:.3f}.")


def _ce_leaseback(ctx, r):
    value = r.int(1000, 10000, 50)
    rate = _rate_bps(ctx) / 100
    yld = max(rate - data.PROPERTY_YIELD_BELOW_RATE_BPS / 100, data.PROPERTY_LEAST_YIELD_BPS / 100)
    price = value * (10_000 - data.LEASEBACK_DISCOUNT_BPS) / 10_000
    rent = price * (yld + data.LEASEBACK_EXTRA_YIELD_BPS / 100) / 100
    return_on = r.int(10, 35)
    return {"situation": "A buyer offers to buy the head office and lease it back. The cash would go into the business, which earns a return on "
                         "what it invests. Is the cash worth more in the business than the rent costs?",
            "task": ["Work out the cash received.", "Work out the yearly rent as a share of it (%).", "Say whether to sell (the business's return beats the rent's cost)."],
            "given": [("The building is worth", m(value)), ("Price offered (a discount on its worth)", m(price)), ("Rent a year", m(rent)),
                      ("Return the business earns on new money", pc(return_on))],
            "f": {"p": price, "r": rent, "ret": return_on}}


piece("ce_leaseback", "ceo", "Property strategy", "Sell the head office and lease it back?", 70,
      "Selling and leasing back frees cash; it pays only if the business earns more on the cash than the rent costs.", _ce_leaseback,
      [Q("cash", "Cash received (₦m)", "millions", lambda f: f["p"]),
       Q("cost", "Rent as a share of the cash (%)", "percent", lambda f: f["r"] / f["p"] * 100, 0.05),
       choice("sell", "Sell and lease back?", lambda f: yn(f["ret"] > f["r"] / f["p"] * 100), *YES_NO)],
      plain=lambda f, t: f"The rent costs {t['cost']:.2f}% of the cash; the business earns {f['ret']}%: " + ("sell." if t["sell"] == "yes" else "keep it."),
      method="Treat the rent as the interest on the cash raised. If the business earns more on that cash than the rent costs, selling "
             "adds value; if not, the company is borrowing dearly against its own building. Remember the lease can be broken by missed rent.",
      maths=lambda f, t: f"{f['r']:.2f} ÷ {f['p']:.2f} = {t['cost']:.2f}% against {f['ret']}%.")


def _ce_hedge(ctx, r):
    fuel = r.int(500, 5000, 50)                   # ₦m of fuel a year
    rise = r.int(10, 50)
    margin = r.int(500, 6000, 50)
    share = r.int(25, 100, 25)
    return {"situation": "Fuel is a big cost. The board asks how much of next year's fuel to lock in with futures. A rise in fuel prices would come "
                         "straight off the profit.",
            "task": ["Work out what the rise would cost without a hedge.", "Work out what it would cost with the share hedged.",
                     "Work out the profit left with the hedge."],
            "given": [("Fuel a year", m(fuel)), ("A plausible rise in fuel prices", f"{rise}%"), ("Profit before the rise", m(margin)),
                      ("Share of fuel hedged", f"{share}%")],
            "f": {"f": fuel, "r": rise, "p": margin, "h": share}}


piece("ce_hedging", "ceo", "Hedging policy", "How much fuel should we lock in?", 80,
      "A hedge gives up the gain from a fall in costs to protect against a rise that could break the business.", _ce_hedge,
      [Q("unhedged", "Cost of the rise unhedged (₦m)", "millions", lambda f: f["f"] * f["r"] / 100),
       Q("hedged", "Cost with the hedge (₦m)", "millions", lambda f: f["f"] * f["r"] / 100 * (1 - f["h"] / 100)),
       Q("left", "Profit left with the hedge (₦m)", "millions", lambda f: f["p"] - f["f"] * f["r"] / 100 * (1 - f["h"] / 100))],
      plain=lambda f, t: f"Unhedged the rise costs {m(t['unhedged'])}; hedged, {m(t['hedged'])}.",
      method="Size the hedge from what the business could not survive, not from a guess about prices. Only the unhedged share of the fuel "
             "moves with the market; the rest is fixed, in both directions.",
      maths=lambda f, t: f"{f['f']} × {f['r']}% = {t['unhedged']}; × (1 − {f['h']}%) = {t['hedged']}; {f['p']} − that = {t['left']}.")


def _ce_walkaway(ctx, r):
    standalone = r.int(2000, 20000, 100)
    synergies = int(standalone * r.int(5, 30) / 100)
    costs = int(synergies * r.int(10, 60) / 100)
    bid = int(standalone * r.int(100, 140) / 100)
    return {"situation": "You are bidding for a company. Decide the price at which you walk away: its value alone plus the net value of what "
                         "combining adds. Above that, winning loses money.",
            "task": ["Work out the walk-away price.", "Say whether to match the rival's bid."],
            "given": [("Value on its own", m(standalone)), ("Value of synergies", m(synergies)), ("Cost of getting them", m(costs)), ("Rival's bid", m(bid))],
            "f": {"s": standalone, "y": synergies, "c": costs, "b": bid}}


piece("ce_walkaway", "ceo", "Bidding discipline", "When do we walk away?", 86,
      "Set the most you will pay before the auction starts, and walk away above it: the winner's curse is paying too much.", _ce_walkaway,
      [Q("walk", "Walk-away price (₦m)", "millions", lambda f: f["s"] + f["y"] - f["c"]),
       choice("match", "Match the rival's bid?", lambda f: yn(f["b"] <= f["s"] + f["y"] - f["c"]), *YES_NO)],
      plain=lambda f, t: f"Walk away above {m(t['walk'])}.", need=2,
      method="Add what the company is worth alone to the synergies you can really get, less what they cost to get. That is the most it is "
             "worth to you; decide it before bidding and keep to it.",
      maths=lambda f, t: f"{f['s']} + {f['y']} − {f['c']} = {t['walk']}.")


def _ce_gearing(ctx, r):
    ebitda = r.int(500, 6000, 50)
    debt = int(ebitda * r.int(5, 50) / 10)
    target = r.pick([2, 2.5, 3])
    return {"situation": "The board sets the most the company should owe: a multiple of its yearly earnings before interest, tax and "
                         "depreciation. How far is it from the target?",
            "task": ["Work out debt ÷ earnings.", "Work out the debt to repay (or that could be added: a minus figure) to reach the target."],
            "given": [("Debt", m(debt)), ("Earnings a year", m(ebitda)), ("Target", f"{target} times earnings")],
            "f": {"d": debt, "e": ebitda, "t": target}}


piece("ce_gearing", "ceo", "Capital structure", "Is the company borrowing too much?", 92,
      "Debt is measured against what the business earns: too much, and one bad year can break it.", _ce_gearing,
      [Q("times", "Debt ÷ earnings", "times", lambda f: f["d"] / f["e"], 0.02),
       Q("repay", "To repay (₦m)", "millions", lambda f: f["d"] - f["e"] * f["t"])],
      plain=lambda f, t: f"It owes {t['times']:.2f} times earnings against a target of {f['t']}.", need=2,
      method="Divide what is owed by a year's earnings before interest, tax and depreciation. Compare with the board's target and the "
             "lenders' promises; reach it by repaying, by raising equity, or by earning more.",
      maths=lambda f, t: f"{f['d']} ÷ {f['e']} = {t['times']:.2f}; {f['d']} − {f['e']} × {f['t']} = {t['repay']}.")


def _ce_incentive(ctx, r):
    options = r.int(1, 20)
    strike = r.int(20, 150)
    price = int(strike * r.int(70, 200) / 100)
    years = r.int(3, 5)
    return {"situation": "The board is setting the chief executive's long-term pay: options on the company's shares, used after some years. "
                         "Its value to the executive depends on the share price then.",
            "task": ["Work out the options' value if the price is the given one when they can be used.",
                     "Say whether they are worth anything at that price."],
            "given": [("Options", f"{options} million"), ("Strike", f"₦{strike}"), ("Share price when they can be used", f"₦{price}"),
                      ("Years until they can be used", str(years))],
            "f": {"n": options, "k": strike, "p": price, "t": years}}


piece("ce_incentives", "ceo", "Executive pay", "What is the long-term pay worth?", 99,
      "Options pay the executive only what the share price rises above the strike: pay tied to what owners gain.", _ce_incentive,
      [Q("value", "Value when used (₦m)", "millions", lambda f: f["n"] * max(f["p"] - f["k"], 0)),
       choice("worth", "Are they worth anything at that price?", lambda f: yn(f["p"] > f["k"]), *YES_NO)],
      plain=lambda f, t: f"The options would be worth {m(t['value'])}.", need=2,
      method="An option is worth the share price above the strike, times the number, and nothing below it: the executive gains only "
             "when the owners do. Set the strike at today's price or above, and the time long enough to reward lasting results.",
      maths=lambda f, t: f"{f['n']} × max(₦{f['p']} − ₦{f['k']}, 0) = {t['value']}.")


def _ce_working(ctx, r):
    sales = r.int(2000, 20000, 100)
    days_now = r.int(40, 120)
    days_target = r.int(20, days_now - 5)
    return {"situation": "Customers take too long to pay. If they paid faster, cash tied up in their debts would be freed for the business.",
            "task": ["Work out what customers owe now (sales ÷ 360 × days).", "At the target days.", "The cash freed."],
            "given": [("Sales a year", m(sales)), ("Days customers take now", str(days_now)), ("Target days", str(days_target))],
            "f": {"s": sales, "n": days_now, "t": days_target}}


piece("ce_working", "ceo", "Working capital", "How much cash would faster payment free?", 74,
      "Every day customers take to pay is a day's sales of cash the business lends them for nothing.", _ce_working,
      [Q("now", "Owed now (₦m)", "millions", lambda f: f["s"] / 360 * f["n"]),
       Q("target", "Owed at the target (₦m)", "millions", lambda f: f["s"] / 360 * f["t"]),
       Q("freed", "Cash freed (₦m)", "millions", lambda f: f["s"] / 360 * (f["n"] - f["t"]))],
      plain=lambda f, t: f"Collecting faster frees {m(t['freed'])}.",
      method="A day's sales is the year's sales over 360. Multiply by the days customers take: that is cash tied up. Cutting the days frees "
             "it once, for good, without borrowing a kobo.",
      maths=lambda f, t: f"{f['s']} ÷ 360 × ({f['n']} − {f['t']}) = {t['freed']:.2f}.")


# ===========================================================================
# Four more, to reach the design's 350
# ===========================================================================

def _ac_going(ctx, r):
    cash = r.int(100, 3000, 10)
    burn = r.int(50, 800, 10)
    loan_due = r.int(0, 2000, 10)
    return {"situation": "The auditors ask whether the company can keep going for the next year (a going concern). It is losing cash each "
                         "quarter, and a loan falls due within the year.",
            "task": ["Work out the quarters its cash lasts at the present loss (cash ÷ the quarterly loss).",
                     "Work out the cash short over the year, loan included (nought if none).", "Say whether there is a going-concern doubt."],
            "given": [("Cash", m(cash)), ("Cash lost a quarter", m(burn)), ("Loan due within the year", m(loan_due))],
            "f": {"c": cash, "b": burn, "l": loan_due}}


piece("ac_going_concern", "accountant", "Going concern", "Can the company keep going?", 100,
      "Accounts assume the business carries on; if it may not last the year, the readers must be told.", _ac_going,
      [Q("quarters", "Quarters the cash lasts", "number", lambda f: f["c"] / f["b"], 0.05),
       Q("short", "Cash short over the year (₦m)", "millions", lambda f: max(f["b"] * 4 + f["l"] - f["c"], 0)),
       choice("doubt", "Is there a going-concern doubt?", lambda f: yn(f["b"] * 4 + f["l"] > f["c"]), *YES_NO)],
      plain=lambda f, t: f"The cash lasts {t['quarters']:.1f} quarters; over the year it is short by {m(t['short'])}.",
      method="Look a full year ahead: the cash the business will lose, plus every debt that falls due, against the cash it has and can "
             "surely raise. If it falls short without a firm plan to fill the gap, the doubt must be disclosed.",
      maths=lambda f, t: f"{f['c']} ÷ {f['b']} = {t['quarters']:.2f}; short = {f['b']} × 4 + {f['l']} − {f['c']}.")


def _am_yield_gap(ctx, r):
    gov = _rate_bps(ctx) / 100
    prop_yield = r.int(5, 20)
    growth = r.int(0, 15)
    return {"situation": "Should the client hold more property or more government bonds? Compare property's rent yield plus the growth in rent "
                         "investors expect with the bond's yield.",
            "task": ["Work out property's expected return (yield + growth).", "Work out the gap over government bonds (points).",
                     "Say whether property looks the better buy."],
            "given": [("Government bond yield", pc(gov)), ("Property rent yield", pc(prop_yield)), ("Expected growth in rent", pc(growth))],
            "f": {"g": gov, "y": prop_yield, "gr": growth}}


piece("am_yield_gap", "asset_manager", "Property against bonds", "Property or government bonds?", 80,
      "Property's return is its rent yield plus the growth in rent; compare it with the bond's fixed yield.", _am_yield_gap,
      [Q("ret", "Property's expected return (%)", "percent", lambda f: f["y"] + f["gr"], 0.02),
       Q("gap", "Gap over bonds (points)", "number", lambda f: f["y"] + f["gr"] - f["g"], 0.02),
       choice("property", "Does property look better?", lambda f: yn(f["y"] + f["gr"] > f["g"]), *YES_NO)],
      plain=lambda f, t: f"Property should return {t['ret']:.2f}%, {t['gap']:+.2f} points against bonds.",
      method="Add the rent yield to the growth in rent you can defend; set it against the government bond's yield. Property must offer a "
             "clear gap for being harder to sell and for the risk that rents fall.",
      maths=lambda f, t: f"{f['y']} + {f['gr']} = {t['ret']}; − {f['g']:.2f} = {t['gap']:.2f}.")


def _ib_mezz(ctx, r):
    mezz = r.int(500, 5000, 50)
    rate = r.int(18, 28)
    equity_pct = data.MEZZ_EQUITY_BPS / 100
    value = r.int(5000, 40000, 500)
    years = r.int(3, 6)
    growth = r.int(5, 25)
    return {"situation": "A mezzanine lender is paid a high rate rolled up to the sale, and takes a small share of the company at the start. "
                         "What is the lender's whole return worth at the sale?",
            "task": ["Work out the debt with its rolled-up interest at the sale.", "Work out the lender's share of the company then "
                     "(its share × the company's value grown).", "Work out the lender's times money."],
            "given": [("Mezzanine lent", m(mezz)), ("Rate, rolled up each year", pc(rate)), ("Share of the company taken", pc(equity_pct)),
                      ("Company's value now", m(value)), ("Growth in its value a year", pc(growth)), ("Years to the sale", str(years))],
            "f": {"z": mezz, "r": rate, "e": equity_pct, "v": value, "g": growth, "n": years}}


def _mezz_out(f):
    return f["z"] * (1 + f["r"] / 100) ** f["n"] + f["v"] * (1 + f["g"] / 100) ** f["n"] * f["e"] / 100


piece("ib_mezzanine", "investment_banker", "Mezzanine finance", "What does the mezzanine lender earn?", 83,
      "Mezzanine is paid after the bank, so it charges a high rate and takes a slice of the upside too.", _ib_mezz,
      [Q("debt", "Debt with interest at the sale (₦m)", "millions", lambda f: f["z"] * (1 + f["r"] / 100) ** f["n"]),
       Q("stake", "The lender's share then (₦m)", "millions", lambda f: f["v"] * (1 + f["g"] / 100) ** f["n"] * f["e"] / 100),
       Q("times", "Times money", "times", lambda f: _mezz_out(f) / f["z"], 0.02)],
      plain=lambda f, t: f"The lender gets back {t['times']:.2f} times its money.",
      method="Roll the interest up year by year on the growing debt; add the value of the share it took, at the company's value when it "
             "is sold. That combination is why mezzanine costs a buyer far more than the bank does.",
      maths=lambda f, t: f"{f['z']} × (1 + {f['r']}%)^{f['n']} + {f['v']} × (1 + {f['g']}%)^{f['n']} × {f['e']}%; ÷ {f['z']}.")


def _rm_hedge_ratio(ctx, r):
    corr = r.int(50, 95) / 100
    s_spot = r.int(10, 40)
    s_fut = r.int(10, 40)
    exposure = r.int(500, 5000, 50)
    return {"situation": "Fuel bought is hedged with oil futures, but fuel and oil do not move exactly together. The hedge ratio that removes "
                         "most risk is the correlation × the fuel's swing ÷ the future's swing.",
            "task": ["Work out the hedge ratio.", "Work out the futures position to take (₦m of oil)."],
            "given": [("Correlation of fuel and oil", f"{corr:.2f}"), ("Fuel's swing", pc(s_spot)), ("Oil future's swing", pc(s_fut)),
                      ("Fuel bought a year", m(exposure))],
            "f": {"c": corr, "s": s_spot, "f": s_fut, "x": exposure}}


piece("rm_hedge_ratio", "risk_manager", "Hedge ratios", "How much oil hedges the fuel?", 86,
      "When the hedge does not move exactly with what it protects, the best hedge is scaled by how closely they move.", _rm_hedge_ratio,
      [Q("ratio", "Hedge ratio", "number", lambda f: f["c"] * f["s"] / f["f"], 0.01),
       Q("position", "Futures position (₦m)", "millions", lambda f: f["x"] * f["c"] * f["s"] / f["f"])],
      plain=lambda f, t: f"Hedge {t['ratio']:.2f} of the fuel: {m(t['position'])} of oil futures.", need=2,
      method="Multiply the correlation by the swing of what is hedged and divide by the swing of the hedge. Hedging one for one when the two "
             "move differently leaves risk on the table, or adds it.",
      maths=lambda f, t: f"{f['c']:.2f} × {f['s']} ÷ {f['f']} = {t['ratio']:.3f}; × {f['x']} = {t['position']:.2f}.")


# ---------------------------------------------------------------------------
# Into the library (each piece then grows its empire and weekend settings in objectives.py)
# ---------------------------------------------------------------------------

o.TEMPLATES.update({t.code: t for t in NEW})
