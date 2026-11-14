"""Part 4c: the work the six new industries bring to the players' builds.

One piece for each new industry, and one to each build, so that no build is left without new
work when six industries open at once:

  mining        the Investment Banker     a bond in dollars, and what a weaker naira does to it
  technology    the Asset Manager         a growth share when the long interest rate moves
  retail        the Accountant            a grocer's margin, and how little sales may fall
  entertainment the Journalist            a studio's quarter, and what it looks like without the hit
  fertiliser    the Risk Manager          a cost that follows the gas price
  pharma        the Legal Counsel         a supply contract, and who carries the currency risk

Each is one new module in its build's syllabus, at Level 5, so the four modules a new player
starts with are untouched. Each comes in the three settings like every other piece, because
`objectives` grows the library after this file is imported.

Nothing here names an exam body or shows a question paper (working rule 6).
"""

from __future__ import annotations

from simulation import objectives as o
from simulation.objectives_gap import Q, choice, piece

INDUSTRIES: list = []

# Who carries a rise in the price of what is imported under a contract.
CARRIES = (("buyer", "The buyer"), ("seller", "The seller"), ("shared", "They share it"))

# Which piece of work belongs to which new industry, so that no industry and no build is left out.
# The test `test_every_industry_has_work_for_every_build` reads this and checks it against the library.
INDUSTRY_WORK: dict[str, str] = {
    "mining": "ib_mining_bond",
    "technology": "am_growth_rates",
    "retail": "ac_retail_margin",
    "entertainment": "jn_film_quarter",
    "fertiliser": "rm_gas_cost",
    "pharma": "lw_currency_clause",
}


# ---------------------------------------------------------------------------
# The Investment Banker: a miner's bond in dollars (mining)
# ---------------------------------------------------------------------------

def _mining_bond(ctx, r):
    borrowed = r.int(120, 260, 20)                      # millions of dollars
    coupon = r.int(60, 85, 5) / 10                      # per cent a year
    fx_now = r.int(1400, 1700, 25)                      # naira for a dollar
    fall = r.pick([10, 15, 20])                         # the naira falls this much over the year
    dollars_in = r.int(30, 70, 5)                       # millions of dollars a year the mine earns abroad
    return {"situation": "A mining company will borrow in dollars to open a new pit, and be paid in dollars for what it digs. "
                         "The naira is expected to fall over the year the bond runs.",
            "task": ["Give the interest it owes in naira over the first year, and the same interest if the naira falls as expected.",
                     "Say how many times its dollar earnings cover the interest, before any fall."],
            "given": [("The bond", f"${borrowed} million at {coupon:.1f}% a year"),
                      ("The naira today", f"₦{fx_now:,} to the dollar"),
                      ("The naira over the year", f"down {fall}%"),
                      ("What the mine earns abroad", f"${dollars_in} million a year")],
            "f": {"borrowed": borrowed, "coupon": coupon, "fx": fx_now, "fall": fall, "dollars_in": dollars_in}}


def _mining_interest(f) -> float:
    return f["borrowed"] * f["coupon"] / 100 * f["fx"]


piece("ib_mining_bond", "investment_banker", "Borrowing in another country's money", "Price the miner's dollar bond", 5,
      "A bond in dollars is a promise to pay dollars: what it costs in naira depends on the rate on the day, and it rises when the naira falls.",
      _mining_bond,
      [Q("naira_now", "The interest, in naira, this year", "millions", lambda f: _mining_interest(f)),
       Q("naira_after", "The same interest if the naira falls as expected", "millions",
         lambda f: _mining_interest(f) * (1 + f["fall"] / 100)),
       Q("cover", "Its dollar earnings cover the interest this many times", "times",
         lambda f: f["dollars_in"] / (f["borrowed"] * f["coupon"] / 100))],
      plain=lambda f, t: (f"The bond is ${f['borrowed']} million at {f['coupon']:.1f}%, so "
                          f"₦{t['naira_now']:,.2f} million of interest this year. If the naira falls {f['fall']}% it is "
                          f"₦{t['naira_after']:,.2f} million, and its dollars cover that {t['cover']:.2f} times over. "
                          "Borrowing abroad is cheaper until the naira falls; that is the whole of it."),
      method="Work the interest out in the currency it is owed in first, then turn it into naira at the rate of the day. "
             "A borrower is paid in its own money and owes in someone else's: measure the cover, the dollars earned against "
             "the dollars owed, because that is what decides whether the bond can be paid at all.",
      maths=lambda f, t: (f"${f['borrowed']}m × {f['coupon']:.1f}% = "
                          f"${f['borrowed'] * f['coupon'] / 100:,.2f}m a year. At ₦{f['fx']:,} = ₦{t['naira_now']:,.2f}m; "
                          f"× {1 + f['fall'] / 100:.2f} = ₦{t['naira_after']:,.2f}m. Cover: ${f['dollars_in']}m ÷ "
                          f"${f['borrowed'] * f['coupon'] / 100:,.2f}m = {t['cover']:.2f} times."),
      reward=100_000, experience=150, into=INDUSTRIES)


# ---------------------------------------------------------------------------
# The Asset Manager: a growth share when the rate moves (technology)
# ---------------------------------------------------------------------------

def _growth_value(f) -> float:
    return f["profit"] * (1 + f["growth"] / 100) / ((f["rate"] - f["growth"]) / 100)


def _growth_share(ctx, r):
    profit = r.int(2000, 6000, 500)                     # millions of naira, this year
    growth = r.pick([8, 10, 12])                        # per cent a year, for years to come
    rate = r.int(16, 20, 1)                             # the long interest rate, per cent
    rise = 1                                            # a one-point rise
    return {"situation": "A technology company is valued on what its profit is expected to become, not on what it earned. "
                         "The long interest rate has moved, and the market's valuation follows it.",
            "task": ["Value a share of the business as a whole at today's long rate, and again after a one-point rise.",
                     "Give the fall in the value as a percentage."],
            "given": [("Profit this year", f"₦{profit:,} million"),
                      ("Profit expected to grow", f"{growth}% a year"),
                      ("The long interest rate", f"{rate}%"),
                      ("The rise being tested", f"{rise} point")],
            "f": {"profit": profit, "growth": growth, "rate": rate, "rise": rise}}


piece("am_growth_rates", "asset_manager", "Growth shares and interest rates", "What a rate rise does to a growth share", 5,
      "A share whose value rests on profits still to come loses most when the rate used to discount them goes up.",
      _growth_share,
      [Q("value_now", "What the business is worth today", "millions", lambda f: _growth_value(f)),
       Q("value_after", "What it is worth after the rise", "millions",
         lambda f: _growth_value({**f, "rate": f["rate"] + f["rise"]})),
       Q("fall", "The fall in its value", "percent",
         lambda f: (1 - _growth_value({**f, "rate": f["rate"] + f["rise"]}) / _growth_value(f)) * 100)],
      plain=lambda f, t: (f"₦{t['value_now']:,.2f} million today, ₦{t['value_after']:,.2f} million after a "
                          f"{f['rise']}-point rise: down {t['fall']:.2f}%. The nearer the rate sits to the growth rate, "
                          "the harder a rise bites, which is why fast-growing shares move furthest on a rate decision."),
      method="Value a growing business by dividing the profit expected next year by the gap between the rate and the growth. "
             "That gap is small for a growth company, so a one-point move in the rate moves the answer a great deal. This is "
             "why a rate rise hurts technology shares more than banks, which earn more from a higher rate.",
      maths=lambda f, t: (f"₦{f['profit']:,}m × {1 + f['growth'] / 100:.2f} = ₦{f['profit'] * (1 + f['growth'] / 100):,.2f}m. ÷ "
                          f"({f['rate']}% − {f['growth']}%) = {f['rate'] - f['growth']}% → ₦{t['value_now']:,.2f}m. "
                          f"÷ ({f['rate'] + f['rise']}% − {f['growth']}%) = {f['rate'] + f['rise'] - f['growth']}% → "
                          f"₦{t['value_after']:,.2f}m. Fall = {t['fall']:.2f}%."),
      reward=100_000, experience=150, into=INDUSTRIES)


# ---------------------------------------------------------------------------
# The Accountant: a grocer's margin (retail)
# ---------------------------------------------------------------------------

def _grocer(ctx, r):
    sales = r.int(20_000, 90_000, 5_000)                # millions of naira a year
    margin = r.pick([12, 15, 18])                       # per cent kept on what it sells
    overhead = r.int(60, 85, 5)                         # this much of the gross profit goes on rent, wages and vans
    return {"situation": "A grocery chain keeps a little on every naira it takes and carries a large rent bill. "
                         "Its bank wants to know how much its sales could fall before it makes a loss.",
            "task": ["Give its gross profit, and its profit after the running costs.",
                     "Give the fall in sales, in per cent, that would wipe the profit out."],
            "given": [("Sales last year", f"₦{sales:,} million"),
                      ("What it keeps on each sale", f"{margin}%"),
                      ("Rent, wages and vans", f"{overhead}% of the gross profit")],
            "f": {"sales": sales, "margin": margin, "overhead": overhead}}


def _gross_profit(f) -> float:
    return f["sales"] * f["margin"] / 100


def _grocer_profit(f) -> float:
    return _gross_profit(f) * (1 - f["overhead"] / 100)


piece("ac_retail_margin", "asset_manager", "Thin margins and the rent bill", "How far can the shops' sales fall?", 5,
      "A shop that keeps a tenth of what it takes has no room for a fall in sales: the rent does not fall with them.",
      _grocer,
      [Q("gross", "Its gross profit", "millions", lambda f: _gross_profit(f)),
       Q("profit", "Its profit after running costs", "millions", lambda f: _grocer_profit(f)),
       Q("fall", "The fall in sales that wipes the profit out", "percent",
         lambda f: _grocer_profit(f) / _gross_profit(f) * 100)],
      plain=lambda f, t: (f"Gross profit ₦{t['gross']:,.2f} million; after rent, wages and vans, ₦{t['profit']:,.2f} million. "
                          f"Sales can fall {t['fall']:.2f}% before that is gone. A shop's safety margin is thin because its "
                          "costs are fixed while its sales are not."),
      method="Take the sales, apply the margin the business keeps, then take off the costs that do not move with sales. "
             "The room left over, divided by the gross profit, is how far sales may fall before there is nothing left. "
             "That is the same test a lender applies before it lends to a retailer.",
      maths=lambda f, t: (f"₦{f['sales']:,}m × {f['margin']}% = ₦{t['gross']:,.2f}m. × (1 − {f['overhead']}%) = "
                          f"₦{t['profit']:,.2f}m. ₦{t['profit']:,.2f}m ÷ ₦{t['gross']:,.2f}m = {t['fall']:.2f}%."),
      reward=70_000, experience=115, into=INDUSTRIES)


# ---------------------------------------------------------------------------
# The Journalist: a studio's quarter (film and entertainment)
# ---------------------------------------------------------------------------

def _studio_quarter(ctx, r):
    hit = r.int(3_000, 9_000, 500)                      # millions of naira the hit release took
    other = r.int(1_500, 3_000, 250)                    # everything else it took
    cost = r.int(30, 70, 5)                             # per cent of the two together
    return {"situation": "A film studio has had one release that did well and a slate that did not. Its quarter is the two "
                         "together, less what it costs to run the studio.",
            "task": ["Give its sales and its profit for the quarter.",
                     "Say what the quarter would have looked like without the hit."],
            "given": [("The hit release", f"₦{hit:,} million"),
                      ("Everything else", f"₦{other:,} million"),
                      ("The cost of running the studio", f"{cost}% of its sales")],
            "f": {"hit": hit, "other": other, "cost": cost}}


def _studio_sales(f) -> float:
    return f["hit"] + f["other"]


def _studio_cost(f) -> float:
    return _studio_sales(f) * f["cost"] / 100


piece("jn_film_quarter", "investment_banker", "Reporting a hit-or-miss industry", "A studio's quarter, with and without the hit", 5,
      "In an industry where one release decides the quarter, a story that leaves the hit out tells the reader the opposite of the truth.",
      _studio_quarter,
      [Q("sales", "Its sales for the quarter", "millions", lambda f: _studio_sales(f)),
       Q("profit", "Its profit for the quarter", "millions", lambda f: _studio_sales(f) - _studio_cost(f)),
       Q("without", "What its profit would have been without the hit", "millions",
         lambda f: f["other"] - _studio_cost(f))],
      plain=lambda f, t: (f"Sales ₦{t['sales']:,.2f} million and profit ₦{t['profit']:,.2f} million. Without the hit the "
                          f"quarter would have been ₦{t['without']:,.2f} million, so the hit is the whole of the profit and "
                          "more. An industry that works this way is reported on a slate, not on one release."),
      method="Add the two streams of takings, then take off the costs of running the studio, which do not fall when a release "
             "flops. Then take the hit out and see what is left: if the quarter turns to a loss without it, the paper must say "
             "that the profit came from one release, and say what happens when the next one does not do as well.",
      maths=lambda f, t: (f"₦{f['hit']:,}m + ₦{f['other']:,}m = ₦{t['sales']:,.2f}m. Costs {f['cost']}% = "
                          f"₦{_studio_cost(f):,.2f}m. Profit ₦{t['profit']:,.2f}m. Without the hit: ₦{f['other']:,}m − "
                          f"₦{_studio_cost(f):,.2f}m = ₦{t['without']:,.2f}m."),
      reward=70_000, experience=115, into=INDUSTRIES)


# ---------------------------------------------------------------------------
# The Risk Manager: a cost that follows gas (fertiliser)
# ---------------------------------------------------------------------------

def _gas_cost(ctx, r):
    sales = r.int(40_000, 90_000, 5_000)                # millions of naira a year
    cost = r.int(55, 70, 5)                             # per cent of sales
    gas_share = r.int(40, 60, 5)                        # this much of the cost is gas
    rise = r.pick([15, 20, 25])                         # the gas price rises this much
    return {"situation": "A fertiliser maker turns gas into urea. Its gas bill is most of what it spends, and the gas price "
                         "has moved. Its lender wants the damage measured before the quarter is out.",
            "task": ["Give its gas bill now and its profit now.",
                     "Give its profit after the rise, and the fall in profit as a percentage."],
            "given": [("Sales", f"₦{sales:,} million a year"),
                      ("Its cost of making what it sells", f"{cost}% of sales"),
                      ("Of that cost, gas", f"{gas_share}%"),
                      ("The gas price", f"up {rise}%")],
            "f": {"sales": sales, "cost": cost, "gas_share": gas_share, "rise": rise}}


def _gas_bill(f) -> float:
    return f["sales"] * f["cost"] / 100 * f["gas_share"] / 100


def _gas_profit(f) -> float:
    return f["sales"] - f["sales"] * f["cost"] / 100


def _gas_after(f) -> float:
    return f["sales"] - (f["sales"] * f["cost"] / 100 + _gas_bill(f) * f["rise"] / 100)


piece("rm_gas_cost", "risk_manager", "Cost risk from an input price", "When the gas price moves", 5,
      "An input that is most of the cost is the whole of the risk: a modest rise in gas is a large fall in profit.",
      _gas_cost,
      [Q("bill", "Its gas bill now", "millions", lambda f: _gas_bill(f)),
       Q("profit_now", "Its profit now", "millions", lambda f: _gas_profit(f)),
       Q("profit_after", "Its profit after the rise", "millions", lambda f: _gas_after(f)),
       Q("fall", "The fall in its profit", "percent", lambda f: (1 - _gas_after(f) / _gas_profit(f)) * 100)],
      plain=lambda f, t: (f"Its gas bill is ₦{t['bill']:,.2f} million of a ₦{f['sales']:,} million year, and its profit "
                          f"₦{t['profit_now']:,.2f} million. A {f['rise']}% rise in gas takes it to ₦{t['profit_after']:,.2f} "
                          f"million, down {t['fall']:.2f}%. That is the shape of cost risk: the input is a small share of "
                          "sales and a large share of profit."),
      method="Follow the rise through the accounts in order: the input price, then the cost, then the profit. Measure the "
             "result against profit, not against sales, because profit is what absorbs it. This is why the same gas price "
             "that barely shows in an oil company's results can halve a fertiliser maker's.",
      maths=lambda f, t: (f"Cost ₦{f['sales'] * f['cost'] / 100:,.2f}m; of it gas {f['gas_share']}% = ₦{t['bill']:,.2f}m. "
                          f"Profit ₦{t['profit_now']:,.2f}m. Gas × {1 + f['rise'] / 100:.2f} adds "
                          f"₦{_gas_bill(f) * f['rise'] / 100:,.2f}m → profit ₦{t['profit_after']:,.2f}m. "
                          f"Fall {t['fall']:.2f}%."),
      reward=70_000, experience=115, into=INDUSTRIES)


# ---------------------------------------------------------------------------
# The Legal Counsel: who carries the currency risk (pharma)
# ---------------------------------------------------------------------------

def _supply_contract(ctx, r):
    order = r.int(20_000, 60_000, 5_000)                # millions of naira for a year's ingredients
    share = r.pick([50, 60, 75])                        # the buyer's share of any rise in the rate
    fall = r.pick([10, 15, 20])                         # the naira falls this much before delivery
    return {"situation": "A medicine maker buys its ingredients abroad on a year's contract. The supplier will not carry the "
                         "naira's risk, so the contract says how a fall in the naira is shared before the goods are delivered.",
            "task": ["Give the extra cost the fall in the naira adds to the order.",
                     "Give the part of it the buyer pays under the sharing clause, and say who carries the rest."],
            "given": [("The order", f"₦{order:,} million, priced in dollars"),
                      ("If the naira falls", f"{fall}% before delivery"),
                      ("The clause", f"the buyer pays {share}% of any rise in the naira")],
            "f": {"order": order, "share": share, "fall": fall}}


piece("lw_currency_clause", "investment_banker", "Contracts for imported goods", "Who carries the currency risk?", 5,
      "A price in someone else's money is a risk, and a contract that does not say who carries it will be argued about later.",
      _supply_contract,
      [Q("extra", "The extra cost the fall adds to the order", "millions", lambda f: f["order"] * f["fall"] / 100),
       Q("buyer_pays", "The part of it the buyer pays", "millions",
         lambda f: f["order"] * f["fall"] / 100 * f["share"] / 100),
       choice("who", "Who carries the rest of it?", lambda f: "seller", *CARRIES)],
      plain=lambda f, t: (f"The fall adds ₦{t['extra']:,.2f} million to a ₦{f['order']:,} million order. Under the clause the "
                          f"buyer pays ₦{t['buyer_pays']:,.2f} million and the seller the rest. Read the clause before the "
                          "goods move, not after: it is the same money whoever pays it, but it is not the same argument."),
      method="Price the order in the currency it is owed in, apply the fall, then apply the share the clause sets. Take the "
             "figures across the whole order rather than one delivery, because a rate that moves against the buyer will have "
             "moved on every delivery made under the same contract. A clause that shares a rise in the rate shares a fall in "
             "it too, unless it says otherwise.",
      maths=lambda f, t: (f"₦{f['order']:,}m × {f['fall']}% = ₦{t['extra']:,.2f}m. Buyer: "
                          f"₦{t['extra']:,.2f}m × {f['share']}% = ₦{t['buyer_pays']:,.2f}m. Seller: the remaining "
                          f"{100 - f['share']}%."),
      reward=80_000, experience=125, into=INDUSTRIES)


o.TEMPLATES.update({t.code: t for t in INDUSTRIES})
