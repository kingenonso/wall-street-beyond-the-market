"""Stage 7: the leadership track (the CEO's syllabus map).

Six modules on running a business, each a piece of practical work on a company's filed accounts,
judged by the server against the same records. The track opens to the head of an empire at once
and to anybody at Level 40; nobody starts the game on it. Its experience goes to the player's own
build, and its mastery counts towards the CEO rank.
"""

from __future__ import annotations

from simulation import clock
from simulation import objectives as o
from simulation.objectives_more import HAND_IN, M, _due_soon, _given, _marked, _price_now, _roll, _text, _year_profit, _yes_no

_FINANCIAL = ("banking", "insurance")


def _trading(ctx) -> list[dict]:
    """Companies that make and sell things: their accounts read the same way."""
    return [c for c in o._filed(ctx["conn"], ctx["period"] - 1) if c["sector"] not in _FINANCIAL]


# ---------------------------------------------------------------------------
# 1. Return on capital
# ---------------------------------------------------------------------------

def _return_offer(ctx):
    candidates = [c for c in _trading(ctx) if c["figures"]["balance_sheet"]["total_equity"] > 0
                  and c["figures"]["balance_sheet"]["borrowings"] > 0 and c["figures"]["income_statement"]["interest_expense"] > 0
                  and c["figures"]["income_statement"]["operating_profit"] > 0]
    def clear(c):                # a business whose return and cost of debt are within a fifth of a point is too close to call
        income, sheet = c["figures"]["income_statement"], c["figures"]["balance_sheet"]
        earned = 4 * income["operating_profit"] / (sheet["total_equity"] + sheet["borrowings"]) * 100
        return abs(earned - 4 * income["interest_expense"] / sheet["borrowings"] * 100) >= 0.2
    company = o._choose(ctx, "ce_return", [c for c in candidates if clear(c)])
    if company is None:
        return None
    income, sheet = company["figures"]["income_statement"], company["figures"]["balance_sheet"]
    keep = {"operating": income["operating_profit"], "interest": income["interest_expense"], "equity": sheet["total_equity"],
            "debt": sheet["borrowings"]}
    return {
        "client": o._client(company),
        "situation": f"The board of {company['name']} wants a first test of whether borrowing is paying its way: does the business "
                     f"earn more on the money tied up in it than its borrowed money costs? The figures are from its accounts for "
                     f"{clock.period_label(company['period'])}.",
        "task": ["Put the quarter's operating profit and interest on a yearly footing (four times the quarter's).",
                 "Return on capital = a year's operating profit ÷ (owners' funds + borrowings).",
                 "Cost of debt = a year's interest ÷ borrowings.",
                 "Give both as percentages to one decimal place, and say whether the business earns more than its debt costs."],
        "pass_when": "At least two of the three answers are right.", "deadline": HAND_IN,
        "given": [_given("Operating profit, the quarter", keep["operating"]), _given("Interest paid, the quarter", keep["interest"]),
                  _given("Owners' funds (total equity)", keep["equity"]), _given("Total borrowings", keep["debt"])],
        "fields": [{"key": "return", "label": "Return on capital, a year", "kind": "percent"},
                   {"key": "cost", "label": "Cost of debt, a year", "kind": "percent"},
                   _yes_no("earns", "Does it earn more than its debt costs?")],
        "company_id": str(company["company_id"]), **keep,
    }


def _return_submit(ctx, objective, answers):
    t = objective["terms"]
    earned = 4 * t["operating"] / (t["equity"] + t["debt"]) * 100
    cost = 4 * t["interest"] / t["debt"] * 100
    earns = earned > cost
    return _marked(objective, answers, [("return", "Return on capital", earned, 0.1), ("cost", "Cost of debt", cost, 0.1),
                                        ("earns", "Earns more than debt costs", "yes" if earns else "no", 0)], 2,
                   plain=f"A business uses money from its owners and its lenders. This one earns {earned:.1f}% a year on all of it "
                         f"and pays {cost:.1f}% on the borrowed part, so borrowing "
                         + ("adds to what is left for the owners." if earns else "takes away from what is left for the owners.")
                         + " That is the first test only: the owners' own money has a cost too, and a higher one, because they are paid last.",
                   method="Use profit before interest, because interest is the lenders' reward and both groups' money is in the "
                          "bottom of the sum. Compare like with like: a year with a year. The full test sets the return against "
                          "the blended cost of the owners' and the lenders' money together. A leader who grows a business that "
                          "earns less than its capital costs makes it bigger and its owners poorer. One quarter multiplied by four "
                          "is a quick reading; a careful one uses the last four quarters.",
                   maths=f"Return = 4 × {M(t['operating']):,.2f} ÷ ({M(t['equity']):,.2f} + {M(t['debt']):,.2f}) = {earned:.1f}%. "
                         f"Cost of debt = 4 × {M(t['interest']):,.2f} ÷ {M(t['debt']):,.2f} = {cost:.1f}%.")


# ---------------------------------------------------------------------------
# 2. Dividend policy
# ---------------------------------------------------------------------------

def _payout_offer(ctx):
    conn = ctx["conn"]
    prices = _price_now(conn, ctx["now"])
    candidates = []
    for company in _trading(ctx):
        profit = _year_profit(conn, company["company_id"], ctx["period"] - 1)
        if profit and profit > 0 and company["company_id"] in prices:
            candidates.append({**company, "year_profit": profit})
    company = o._choose(ctx, "ce_payout", candidates)
    if company is None:
        return None
    sheet = company["figures"]["balance_sheet"]
    # An ordinary payout, or a special one: more than a year's profit, paid out of profits kept from earlier years.
    share = (40, 60, 100, 200, 300)[_roll(ctx["player_id"], "ce_payout", ctx["period"], company["company_id"]) % 5]
    keep = {"profit": company["year_profit"], "cash": sheet["cash"], "bills": sheet["payables"],
            "due": _due_soon(company["figures"], ctx["period"] - 1),
            "shares": prices[company["company_id"]]["shares"], "share": share}
    return {
        "client": o._client(company),
        "situation": f"The board of {company['name']} is considering paying out {share}% of the last year's profit to the owners "
                     f"as a dividend" + (", a special payment out of profits kept from earlier years," if share > 100 else "")
                     + " and wants to know what that comes to and whether the cash is there.",
        "task": [f"Work out the dividend in all ({share}% of the year's profit after tax) and for each share.",
                 "Then take from the cash the dividend, the unpaid bills, and the debt that reaches its end date within a year, "
                 "and say whether the company can afford the dividend: it can if what is left is nought or more.",
                 "Money in millions of naira, and the dividend for each share in naira, both to two decimal places."],
        "pass_when": "At least three of the four answers are right.", "deadline": HAND_IN,
        "given": [_given("Profit after tax, last four quarters", keep["profit"]), _given("Cash", keep["cash"]),
                  _given("Bills unpaid", keep["bills"]), _given("Debt reaching its end date within a year", keep["due"]),
                  _text("Shares in issue", f"{keep['shares']:,}")],
        "fields": [{"key": "total", "label": "The dividend in all", "kind": "millions"},
                   {"key": "each", "label": "For each share", "kind": "naira"},
                   {"key": "left", "label": "Cash left after the dividend, the bills and the debt falling due", "kind": "millions"},
                   _yes_no("afford", "Can it afford the dividend?")],
        "company_id": str(company["company_id"]), **keep,
    }


def _payout_submit(ctx, objective, answers):
    t = objective["terms"]
    total = t["profit"] * t["share"] / 100
    each = total / t["shares"] / 100
    left = t["cash"] - total - t["bills"] - t["due"]
    return _marked(objective, answers, [("total", "The dividend in all", M(total), 0.05), ("each", "For each share", each, 0.005),
                                        ("left", "Cash left", M(left), 0.5), ("afford", "Whether it can afford it", "yes" if left >= 0 else "no", 0)], 3,
                   plain=f"A dividend is declared out of profit but paid out of cash, and the two are not the same thing. "
                         f"{t['share']}% of the year's profit is {o._money(int(total))}, or ₦{each:,.2f} a share. After paying it, "
                         f"the bills already due and the debt that must be repaid within the year, the company would "
                         + (f"have {o._money(int(left))} left." if left >= 0
                            else f"be {o._money(int(-left))} short: it cannot afford it without borrowing again."),
                   method="Set a payout the business can keep up in a poor year, because owners punish a dividend that is cut far "
                          "more than they reward one that is raised. This test is the least a board should ask: a careful one "
                          "also keeps a working balance of cash, allows for what it plans to spend, and checks that the law "
                          "lets it pay (a dividend may only come out of profits kept from past years). Money the business can "
                          "invest at a good return should stay in it; money it cannot should go back to the owners.",
                   maths=f"Dividend = {M(t['profit']):,.2f} × {t['share']}% = {M(total):,.2f} million. Each share = {M(total):,.2f} million ÷ "
                         f"{t['shares']:,} = ₦{each:,.2f}. Left = {M(t['cash']):,.2f} − {M(total):,.2f} − {M(t['bills']):,.2f} − "
                         f"{M(t['due']):,.2f} = {M(left):,.2f} million.")


# ---------------------------------------------------------------------------
# 3. Costs and break-even
# ---------------------------------------------------------------------------

def _breakeven_offer(ctx):
    candidates = [c for c in _trading(ctx) if c["figures"]["income_statement"]["revenue"] > c["figures"]["income_statement"]["cost_of_sales"] > 0]
    company = o._choose(ctx, "ce_breakeven", candidates)
    if company is None:
        return None
    income = company["figures"]["income_statement"]
    keep = {k: income[k] for k in ("revenue", "cost_of_sales", "operating_expenses", "depreciation", "interest_expense")}
    return {
        "client": o._client(company),
        "situation": f"The management of {company['name']} wants to know how far sales could fall before the business stops "
                     f"making a profit. The figures are one quarter's.",
        "task": ["The cost of what is sold rises and falls with sales. Running costs, depreciation and interest do not: they "
                 "are the fixed costs.",
                 "Margin = (sales − cost of what is sold) ÷ sales. Break-even sales = fixed costs ÷ margin.",
                 "Margin of safety = (sales − break-even sales) ÷ sales.",
                 "Give the margin and the margin of safety as percentages to one decimal place (a minus figure if sales are "
                 "already below break-even), and break-even sales in millions of naira."],
        "pass_when": "At least two of the three figures are right.", "deadline": HAND_IN,
        "given": [_given("Sales", keep["revenue"]), _given("Cost of what it sold", keep["cost_of_sales"]),
                  _given("Running costs", keep["operating_expenses"]), _given("Depreciation", keep["depreciation"]),
                  _given("Interest paid", keep["interest_expense"])],
        "fields": [{"key": "margin", "label": "Margin on sales", "kind": "percent"},
                   {"key": "breakeven", "label": "Break-even sales", "kind": "millions"},
                   {"key": "safety", "label": "Margin of safety", "kind": "percent"}],
        "company_id": str(company["company_id"]), **keep,
    }


def _breakeven_submit(ctx, objective, answers):
    t = objective["terms"]
    margin = (t["revenue"] - t["cost_of_sales"]) / t["revenue"]
    fixed = t["operating_expenses"] + t["depreciation"] + t["interest_expense"]
    level = fixed / margin
    safety = (t["revenue"] - level) / t["revenue"] * 100
    return _marked(objective, answers, [("margin", "Margin on sales", margin * 100, 0.1),
                                        ("breakeven", "Break-even sales", M(level), max(M(level) * 0.005, 0.5)),
                                        ("safety", "Margin of safety", safety, 0.3)], 2,
                   plain=f"Every naira of sales leaves {margin * 100:.1f} kobo after the cost of what was sold. "
                         f"That has to pay the costs that do not move. The business breaks even at sales of {o._money(int(level))} "
                         f"a quarter, so sales could fall by {safety:.1f}% before it makes a loss."
                         if safety >= 0 else
                         f"The margin of {margin * 100:.1f}% is not enough to carry the fixed costs: sales would have to reach "
                         f"{o._money(int(level))} a quarter to break even, {-safety:.1f}% above where they are.",
                   method="Know which costs move with sales and which do not before deciding anything about price or size. A "
                          "business with high fixed costs earns a great deal above break-even and loses a great deal below it; "
                          "one with low fixed costs is safer and duller. The margin of safety is the first number to look at "
                          "before taking on debt.",
                   maths=f"Margin = ({M(t['revenue']):,.2f} − {M(t['cost_of_sales']):,.2f}) ÷ {M(t['revenue']):,.2f} = {margin * 100:.1f}%. "
                         f"Fixed costs = {M(fixed):,.2f}. Break-even = {M(fixed):,.2f} ÷ {margin:.4f} = {M(level):,.2f} million. "
                         f"Safety = ({M(t['revenue']):,.2f} − {M(level):,.2f}) ÷ {M(t['revenue']):,.2f} = {safety:.1f}%.")


# ---------------------------------------------------------------------------
# 4. Capital allocation
# ---------------------------------------------------------------------------

def _allocate_offer(ctx):
    conn = ctx["conn"]
    prices = _price_now(conn, ctx["now"])
    pool = []
    for company in sorted(o._filed(conn, ctx["period"] - 1), key=lambda c: c["ticker"]):
        profit = _year_profit(conn, company["company_id"], ctx["period"] - 1)
        if profit and profit > 0 and company["company_id"] in prices:
            pool.append((company, profit, prices[company["company_id"]]))
    if len(pool) < 6:
        return None
    first = _roll(ctx["player_id"], "ce_allocate", ctx["period"]) % len(pool)
    chosen = [pool[(first + n * 5) % len(pool)] for n in range(3)]
    if len({c[0]["ticker"] for c in chosen}) < 3:
        return None
    options = [{"ticker": c["ticker"], "name": c["name"], "profit": profit, "value": share["price"] * share["shares"]}
               for c, profit, share in chosen]
    yields = [x["profit"] / x["value"] for x in options]
    if max(yields) - sorted(yields)[1] < 0.002:            # too close to call fairly
        return None
    return {
        "situation": "Your board has money to put to work and three companies it could buy into at today's prices. Before "
                     "anything else it wants to know what each naira would earn.",
        "task": ["For each company, the earnings yield = the last year's profit after tax ÷ its market value today.",
                 "Give each as a percentage to one decimal place, and name the company where a naira earns most."],
        "pass_when": "At least three of the four answers are right, and the choice is one of them.", "deadline": HAND_IN,
        "given": [_text(f"{x['name']} ({x['ticker']})", f"profit {M(x['profit']):,.2f} m; market value {M(x['value']):,.2f} m") for x in options],
        "fields": [{"key": f"yield_{n}", "label": f"Earnings yield, {x['ticker']}", "kind": "percent"} for n, x in enumerate(options)]
                  + [{"key": "choice", "label": "Where a naira earns most", "kind": "choice",
                      "options": [{"code": x["ticker"], "label": x["name"]} for x in options]}],
        "options": [[x["ticker"], x["profit"], x["value"]] for x in options],
    }


def _allocate_submit(ctx, objective, answers):
    options = objective["terms"]["options"]
    yields = [profit / value * 100 for _t, profit, value in options]
    best = options[yields.index(max(yields))][0]
    figures = [(f"yield_{n}", f"Earnings yield, {ticker}", yields[n], 0.1) for n, (ticker, _p, _v) in enumerate(options)]
    return _marked(objective, answers, figures + [("choice", "Where a naira earns most", best, 0)], 3, must=("choice",),
                   plain="Money is the one thing every part of a business competes for. The earnings yield puts each use of it on "
                         f"the same footing: what a naira earns in a year. Here it is highest at {best}.",
                   method="Rank the uses of money by what they earn against what they cost and what could go wrong. The earnings "
                          "yield is a first cut: a high one can mean a bargain or a business in decline, so the next question "
                          "is always whether the profit will last. Money with no good use goes back to the owners.",
                   maths="; ".join(f"{ticker}: {M(profit):,.2f} ÷ {M(value):,.2f} = {yields[n]:.1f}%" for n, (ticker, profit, value) in enumerate(options)) + ".")


# ---------------------------------------------------------------------------
# 5. Acquisitions
# ---------------------------------------------------------------------------

def _buy_offer(ctx):
    conn = ctx["conn"]
    prices = _price_now(conn, ctx["now"])
    candidates = []
    for company in _trading(ctx):
        profit = _year_profit(conn, company["company_id"], ctx["period"] - 1)
        if profit and profit > 0 and company["company_id"] in prices and company["figures"]["income_statement"]["revenue"] > 0:
            candidates.append({**company, "year_profit": profit})
    company = o._choose(ctx, "ce_buy", candidates)
    if company is None:
        return None
    share = prices[company["company_id"]]
    premium = (20, 25, 30, 35, 40)[_roll(ctx["player_id"], "ce_buy", ctx["period"], company["company_id"]) % 5]
    saving = (2, 3, 4)[_roll(ctx["player_id"], "ce_buy", ctx["period"], company["company_id"], "s") % 3]
    keep = {"value": share["price"] * share["shares"], "profit": company["year_profit"], "premium": premium, "saving": saving,
            "sales": 4 * company["figures"]["income_statement"]["revenue"], "tax_bps": o._tax_rate(conn),
            "debt": company["figures"]["balance_sheet"]["borrowings"]}
    return {
        "client": o._client(company),
        "situation": f"Your board is weighing an offer for the whole of {company['name']} at {premium}% above today's market value. "
                     f"Its advisers believe joining the two businesses would save {saving}% of the target's yearly sales in costs.",
        "task": ["Work out what the offer would cost.",
                 "Years of profit = the cost ÷ a year's profit after tax: how many years of today's profit the price is.",
                 f"Then work it out again with the yearly saving added to the profit. The saving is taxed like any other profit, at "
                 f"{keep['tax_bps'] / 100:.0f}%: only what is left after tax is added.",
                 "The cost in millions of naira; both answers in years, to one decimal place."],
        "pass_when": "At least two of the three figures are right.", "deadline": HAND_IN,
        "given": [_given("Market value today", keep["value"]), _given("Profit after tax, last four quarters", keep["profit"]),
                  _given("Sales, a year (four times the quarter's)", keep["sales"])],
        "fields": [{"key": "cost", "label": "Cost of the offer", "kind": "millions"},
                   {"key": "payback", "label": "Years of today's profit", "kind": "times"},
                   {"key": "payback_with", "label": "Years of profit, with the saving", "kind": "times"}],
        "company_id": str(company["company_id"]), **keep,
    }


def _buy_submit(ctx, objective, answers):
    t = objective["terms"]
    cost = t["value"] * (100 + t["premium"]) / 100
    saved = t["sales"] * t["saving"] / 100
    kept = saved * (10_000 - t["tax_bps"]) / 10_000
    plain, better = cost / t["profit"], cost / (t["profit"] + kept)
    return _marked(objective, answers, [("cost", "Cost of the offer", M(cost), 0.5), ("payback", "Years of today's profit", plain, 0.06),
                                        ("payback_with", "Years of profit, with the saving", better, 0.06)], 2,
                   plain=f"The offer costs {o._money(int(cost))}: {plain:.1f} years of the target's present profit. If the promised "
                         f"saving arrives, {o._money(int(kept))} a year is left of it after tax, and the price falls to {better:.1f} "
                         f"years of profit. The whole case for paying {t['premium']}% over the market rests on that saving.",
                   method="The premium is paid on the day; the savings arrive later, cost money to get, and often come in below "
                          "plan. A careful leader asks what the deal is worth if only half the saving turns up, and walks away "
                          "from a price that needs everything to go right. This is a first reading: the buyer also takes on the "
                          f"target's debts ({o._money(t['debt'])} here), and a full valuation works from the cash the business "
                          "will throw off, not from one year's profit.",
                   maths=f"Cost = {M(t['value']):,.2f} × {1 + t['premium'] / 100:.2f} = {M(cost):,.2f} million. Years = {M(cost):,.2f} ÷ "
                         f"{M(t['profit']):,.2f} = {plain:.1f}. Saving = {M(t['sales']):,.2f} × {t['saving']}% = {M(saved):,.2f}; after tax at "
                         f"{t['tax_bps'] / 100:.0f}% = {M(kept):,.2f}. With it = {M(cost):,.2f} ÷ {M(t['profit'] + kept):,.2f} = {better:.1f} years.")


# ---------------------------------------------------------------------------
# 6. People and productivity
# ---------------------------------------------------------------------------

def _people_offer(ctx):
    candidates = [c for c in _trading(ctx) if c["figures"]["notes"].get("staff", 0) > 0 and c["figures"]["notes"].get("wages", 0) > 0
                  and c["figures"]["income_statement"]["revenue"] > 0]
    company = o._choose(ctx, "ce_people", candidates)
    if company is None:
        return None
    income, notes = company["figures"]["income_statement"], company["figures"]["notes"]
    keep = {"staff": notes["staff"], "wages": notes["wages"], "revenue": income["revenue"], "operating": income["operating_profit"]}
    return {
        "client": o._client(company),
        "situation": f"{company['name']} employs {keep['staff']:,} people. Its board wants to see, on one line, what they cost "
                     f"and what they bring in.",
        "task": ["Work out the sales for each person employed and the wages for each, for the quarter, in whole naira.",
                 "Then wages as a percentage of sales, to one decimal place."],
        "pass_when": "At least two of the three figures are right.", "deadline": HAND_IN,
        "given": [_text("People employed", f"{keep['staff']:,}"), _given("Wages, the quarter", keep["wages"]),
                  _given("Sales, the quarter", keep["revenue"]), _given("Operating profit", keep["operating"])],
        "fields": [{"key": "sales_each", "label": "Sales for each person", "kind": "naira"},
                   {"key": "wage_each", "label": "Wages for each person", "kind": "naira"},
                   {"key": "share", "label": "Wages as a share of sales", "kind": "percent"}],
        "company_id": str(company["company_id"]), **keep,
    }


def _people_submit(ctx, objective, answers):
    t = objective["terms"]
    sales_each, wage_each = t["revenue"] / t["staff"] / 100, t["wages"] / t["staff"] / 100
    share = t["wages"] / t["revenue"] * 100
    return _marked(objective, answers, [("sales_each", "Sales for each person", sales_each, max(sales_each * 0.001, 1)),
                                        ("wage_each", "Wages for each person", wage_each, max(wage_each * 0.001, 1)),
                                        ("share", "Wages as a share of sales", share, 0.1)], 2,
                   plain=f"Each person employed brought in ₦{sales_each:,.0f} of sales in the quarter and was paid ₦{wage_each:,.0f}. "
                         f"Wages take {share:.1f}% of sales. These three figures, watched over time and set beside rivals', say "
                         f"whether a business is getting more out of its people or simply growing its payroll.",
                   method="Never judge pay on its own: judge it against what the work brings in. A rising wage share with flat "
                          "sales is a warning; a falling one bought by cutting people the business needs is a different warning. "
                          "Laying off saves wages at once and costs skills that take years to rebuild.",
                   maths=f"Sales each = {M(t['revenue']):,.2f} million ÷ {t['staff']:,} = ₦{sales_each:,.0f}. Wages each = "
                         f"{M(t['wages']):,.2f} million ÷ {t['staff']:,} = ₦{wage_each:,.0f}. Share = {share:.1f}%.")


T = o.Template
o.TEMPLATES.update({t.code: t for t in (
    T("ce_return", "ceo", "Return on capital", "Does the business earn its keep?", 1, 80_000, 120, "hand_in",
      "A business is worth growing only while it earns more on its money than the money costs.",
      "client", _return_offer, submit=_return_submit),
    T("ce_payout", "ceo", "Dividend policy", "Can it afford the dividend?", 1, 80_000, 120, "hand_in",
      "A dividend is declared out of profit and paid out of cash.", "client", _payout_offer, submit=_payout_submit),
    T("ce_breakeven", "ceo", "Costs and break-even", "How far could sales fall?", 1, 80_000, 120, "hand_in",
      "Costs that do not move with sales decide how far sales can fall before profit is gone.",
      "client", _breakeven_offer, submit=_breakeven_submit),
    T("ce_allocate", "ceo", "Capital allocation", "Where does a naira earn most?", 1, 100_000, 150, "hand_in",
      "Every use of money competes with every other; rank them by what a naira earns.",
      "employer", _allocate_offer, submit=_allocate_submit),
    T("ce_buy", "ceo", "Acquisitions", "What is the offer worth paying?", 1, 100_000, 150, "hand_in",
      "The premium is paid on the day; the savings that justify it arrive later, if at all.",
      "client", _buy_offer, submit=_buy_submit),
    T("ce_people", "ceo", "People and productivity", "What do its people cost and bring in?", 1, 80_000, 120, "hand_in",
      "Pay is judged against what the work brings in, never on its own.", "client", _people_offer, submit=_people_submit),
)})
