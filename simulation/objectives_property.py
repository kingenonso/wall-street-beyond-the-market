"""Stage 8: work about land and property, one piece for each of the six builds.

The Asset Manager judges whether a building is worth buying for its rent; the Accountant follows a mortgaged
building's cash for a quarter; the Investment Banker puts together the money for a purchase; the Risk Manager
stress-tests a mortgage against a fall in prices; Legal Counsel reads a title before a purchase; the Financial
Journalist reports a district's quarter. They follow the same rules as the rest of the library (objectives.py):
practical work, judged by the server, paid by the player's employer.

The real property in the game is used only for what anybody may see (its rent, its value, its district's
figures). A title's flaws are never used: Legal Counsel's case files are exercises, made up for the paper.
"""

from __future__ import annotations

import hashlib

from simulation import objectives as o
from simulation import property as prop
from simulation import world_data as data
from simulation.money import BPS
from simulation.objectives_more import HAND_IN, _given, _marked, _text, _yes_no

M = o._millions


def _roll(*parts) -> int:
    return int.from_bytes(hashlib.sha256((":".join(str(p) for p in parts) + o.SALT.get()).encode()).digest()[:8], "big")


def _draw(ctx, code: str, candidates: list):
    """The server draws the property or district: the same for one player, piece of work and quarter."""
    if ctx.get("target") is not None:
        return None                                   # (an empire's task is about a company, not a building)
    return o._pick(ctx["player_id"], code, ctx["period"], candidates)


def _buildings(ctx) -> list[dict]:
    conn = ctx["conn"]
    if o._one(conn, "SELECT to_regclass('properties') IS NOT NULL AS ok")["ok"] is not True:
        return []
    ds = prop.districts(conn)
    rate = prop.policy_rate(conn)
    out = []
    for p in o._rows(conn, "SELECT * FROM properties WHERE status = 'standing' AND kind <> 'land' ORDER BY id"):
        d = ds[p["district_id"]]
        rent = prop.rent_due(p, d)
        worth = prop.value(p, d, rate)
        if rent > 0 and worth > 0:
            out.append({**p, "district": d["name"], "city": d["city"], "rent": rent, "worth": worth, "rate": rate})
    return out


def _pct(x: float) -> str:
    return f"{x:.1f}%"


# ===========================================================================
# ASSET MANAGER: is the building worth buying for its rent?
# ===========================================================================

def _yield_offer(ctx):
    b = _draw(ctx, "am_property", _buildings(ctx))
    if b is None:
        return None
    # The asking price: somewhere from a fifth below to a fifth above what the market says it is worth.
    ask = b["worth"] * (8000 + _roll(ctx["player_id"], "am_property", ctx["period"], "ask") % 4001) // BPS
    want = prop.yield_bps(b["rate"])
    return {
        "situation": f"A client of your firm is offered {b['name']} in {b['district']}, {b['city']}, and asks whether to buy it to "
                     "let to tenants. The client wants a return on the price, after tax and upkeep, at least as high as the "
                     "yield property investors are asking for today.",
        "task": ["Work out a year's rent (four quarters of this quarter's rent), and the gross yield: a year's rent over the price.",
                 f"Take off a year's property and land tax ({(data.PROPERTY_TAX_BPS + data.LAND_TAX_BPS) / 100:.1f}% of the price) "
                 f"and a year's upkeep ({data.UPKEEP_BPS * 4 / 100:.1f}% of the price), and give the net yield on the price.",
                 "Say whether the client should buy at this price."],
        "pass_when": "At least three of the four answers are right, and the buy-or-not must be one of them.", "deadline": HAND_IN,
        "given": [_given("Asking price", ask), _given("Rent this quarter (with today's tenants)", b["rent"]),
                  _text("The yield investors ask for today", _pct(want / 100))],
        "fields": [{"key": "rent", "label": "A year's rent", "kind": "millions"},
                   {"key": "gross", "label": "Gross yield", "kind": "percent"},
                   {"key": "net", "label": "Net yield, after tax and upkeep", "kind": "percent"},
                   _yes_no("buy", "Buy at this price?")],
        "ask": ask, "quarter_rent": b["rent"], "want_bps": want,
    }


def _yield_submit(ctx, objective, answers):
    t = objective["terms"]
    rent = t["quarter_rent"] * 4
    gross = rent / t["ask"] * 100
    costs = t["ask"] * (data.PROPERTY_TAX_BPS + data.LAND_TAX_BPS + data.UPKEEP_BPS * 4) / BPS
    net = (rent - costs) / t["ask"] * 100
    buy = net >= t["want_bps"] / 100
    return _marked(objective, answers, [("rent", "A year's rent", M(rent), 0.05), ("gross", "Gross yield", gross, 0.1),
                                        ("net", "Net yield", net, 0.1), ("buy", "Buy or not", "yes" if buy else "no", 0)], 3,
                   must=("buy",),
                   plain=f"The building earns {gross:.1f}% of its price in rent before costs and {net:.1f}% after tax and upkeep. "
                         f"Investors ask {t['want_bps'] / 100:.1f}% today, so at this price it is "
                         f"{'worth buying' if buy else 'too dear for its rent'}.",
                   method="Judge a building by the rent it earns against the price, after the costs that come with owning it: "
                          "tax, upkeep, and the months it stands empty. Compare that yield with what investors ask today, which "
                          "rises and falls with interest rates. A price that only makes sense if prices keep rising is a bet on "
                          "the bubble, not an investment in the rent.",
                   maths=f"A year's rent = 4 × {o._money(t['quarter_rent'])} = {o._money(rent)}. Gross yield = {o._money(rent)} ÷ "
                         f"{o._money(t['ask'])} = {gross:.1f}%. Costs = {(data.PROPERTY_TAX_BPS + data.LAND_TAX_BPS + data.UPKEEP_BPS * 4) / 100:.1f}% "
                         f"of the price = {o._money(int(costs))}. Net yield = ({o._money(rent)} − {o._money(int(costs))}) ÷ "
                         f"{o._money(t['ask'])} = {net:.1f}%.")


# ===========================================================================
# ACCOUNTANT: a mortgaged building's cash for one quarter
# ===========================================================================

def _cash_offer(ctx):
    b = _draw(ctx, "ac_property", _buildings(ctx))
    if b is None:
        return None
    roll = _roll(ctx["player_id"], "ac_property", ctx["period"])
    borrowed_bps = (5000, 6000, 7000, 8000)[roll % 4]
    loan = b["worth"] * borrowed_bps // BPS
    rate = b["rate"] + data.MORTGAGE_SPREAD_BPS
    return {
        "situation": f"A client bought {b['name']} in {b['district']}, {b['city']}, for {o._money(b['worth'])}, borrowing "
                     f"{borrowed_bps // 100}% of the price from a bank. The client asks what the building will leave in cash "
                     "this quarter, after the bank and the tax office have been paid.",
        "task": ["Work out the quarter's mortgage interest (a quarter of the yearly rate on the loan) and the quarter's repayment "
                 f"(the loan repaid evenly over {data.MORTGAGE_TERM_QUARTERS} quarters).",
                 f"Take off the quarter's property and land tax ({(data.PROPERTY_TAX_BPS + data.LAND_TAX_BPS) / 100:.1f}% of the price a year) "
                 f"and upkeep ({data.UPKEEP_BPS / 100:.1f}% of the price a quarter) from the rent, and give the cash left.",
                 "Say whether the rent covers everything."],
        "pass_when": "At least three of the four answers are right.", "deadline": HAND_IN,
        "given": [_given("Price paid", b["worth"]), _given("The loan", loan), _text("Mortgage rate, a year", _pct(rate / 100)),
                  _given("Rent this quarter", b["rent"])],
        "fields": [{"key": "interest", "label": "Interest this quarter", "kind": "naira"},
                   {"key": "repayment", "label": "Repayment this quarter", "kind": "naira"},
                   {"key": "left", "label": "Cash left after everything (negative if short)", "kind": "naira"},
                   _yes_no("covers", "Does the rent cover everything?")],
        "price": b["worth"], "loan": loan, "rate_bps": rate, "quarter_rent": b["rent"],
    }


def _cash_submit(ctx, objective, answers):
    t = objective["terms"]
    interest = t["loan"] * t["rate_bps"] / BPS / 4
    repayment = t["loan"] / data.MORTGAGE_TERM_QUARTERS
    tax = t["price"] * (data.PROPERTY_TAX_BPS + data.LAND_TAX_BPS) / BPS / 4
    upkeep = t["price"] * data.UPKEEP_BPS / BPS
    left = t["quarter_rent"] - interest - repayment - tax - upkeep
    tol = max(abs(left), interest) / 100 * 0.01 + 1
    return _marked(objective, answers, [("interest", "Interest", interest / 100, max(interest / 100 * 0.005, 1)),
                                        ("repayment", "Repayment", repayment / 100, max(repayment / 100 * 0.005, 1)),
                                        ("left", "Cash left", left / 100, tol),
                                        ("covers", "Covers or not", "yes" if left >= 0 else "no", 0)], 3,
                   plain=f"The rent of {o._money(t['quarter_rent'])} has to meet interest, repayment, tax and upkeep. "
                         + (f"It leaves {o._money(int(left))}." if left >= 0 else f"It falls {o._money(int(-left))} short: the owner pays the rest."),
                   method="Follow the cash, not the profit: a mortgage repayment is not a cost in the accounts, but it is cash "
                          "that leaves. Put every payment the building brings with it against the rent for the same period. "
                          "A building that does not pay its own way must be carried from the owner's other income, and two "
                          "missed mortgage payments let the bank sell it.",
                   maths=f"Interest = {o._money(t['loan'])} × {t['rate_bps'] / 100:.2f}% ÷ 4 = {o._money(int(interest))}. "
                         f"Repayment = {o._money(t['loan'])} ÷ {data.MORTGAGE_TERM_QUARTERS} = {o._money(int(repayment))}. "
                         f"Tax = {o._money(int(tax))}. Upkeep = {o._money(int(upkeep))}. Left = {o._money(t['quarter_rent'])} − all four = "
                         f"{o._money(int(left))}.")


# ===========================================================================
# INVESTMENT BANKER: the money for a purchase
# ===========================================================================

def _funding_offer(ctx):
    b = _draw(ctx, "ib_property", _buildings(ctx))
    if b is None:
        return None
    roll = _roll(ctx["player_id"], "ib_property", ctx["period"])
    price = b["worth"]
    cash = price * (2000 + roll % 5000) // BPS            # from a fifth to seven tenths of the price: some need a partner, some do not
    reserve = price * (500 + (roll // 7) % 500) // BPS
    return {
        "situation": f"An empire wants to buy {b['name']} in {b['district']}, {b['city']}, for {o._money(price)}. It must keep a "
                     "reserve of cash untouched. A bank lends an empire at most "
                     f"{data.EMPIRE_MORTGAGE_MOST_BPS // 100}% of a property's price. Whatever is still missing must come from a "
                     "partner, who then owns that share of the building.",
        "task": ["Work out how much of its own cash the empire can put in (its cash less the reserve), then how much it must "
                 "borrow from the bank, up to the bank's limit.",
                 "Give the loan as a percentage of the price, whether a partner is needed, and the partner's share of the "
                 "price (nought if none is needed)."],
        "pass_when": "At least three of the four answers are right.", "deadline": HAND_IN,
        "given": [_given("Price", price), _given("The empire's cash", cash), _given("Reserve it must keep", reserve)],
        "fields": [{"key": "loan", "label": "The bank's loan", "kind": "millions"},
                   {"key": "loan_pct", "label": "The loan, share of the price", "kind": "percent"},
                   _yes_no("partner", "Is a partner needed?"),
                   {"key": "partner_pct", "label": "The partner's share of the price", "kind": "percent"}],
        "price": price, "cash": cash, "reserve": reserve,
    }


def _funding_submit(ctx, objective, answers):
    t = objective["terms"]
    own = max(t["cash"] - t["reserve"], 0)
    most = t["price"] * data.EMPIRE_MORTGAGE_MOST_BPS / BPS
    loan = min(max(t["price"] - own, 0), most)
    rest = max(t["price"] - own - loan, 0)
    loan_pct, partner_pct = loan / t["price"] * 100, rest / t["price"] * 100
    return _marked(objective, answers, [("loan", "The loan", M(loan), 0.05), ("loan_pct", "Loan share", loan_pct, 0.1),
                                        ("partner", "Partner needed", "yes" if rest > 0 else "no", 0),
                                        ("partner_pct", "Partner's share", partner_pct, 0.1)], 3,
                   plain=f"The empire can put in {o._money(int(own))} of its own. The bank lends {loan_pct:.1f}% of the price"
                         + (f", and a partner must bring the last {partner_pct:.1f}%." if rest > 0 else ", and no partner is needed."),
                   method="Start from what the buyer can spare, not from what it has: a reserve is kept for the unexpected. Borrow "
                          "next, because a loan leaves the buyer owning the whole building; bring in a partner last, because a "
                          "partner takes a share of the rent and of any rise in price for ever. Check every limit before the "
                          "bid goes in, since a bid cannot be paid for after it has won.",
                   maths=f"Own cash = {o._money(t['cash'])} − {o._money(t['reserve'])} = {o._money(int(own))}. Loan = the smaller of "
                         f"{o._money(t['price'])} − {o._money(int(own))} and {data.EMPIRE_MORTGAGE_MOST_BPS // 100}% of the price = "
                         f"{o._money(int(loan))} ({loan_pct:.1f}%). Missing = {o._money(int(rest))} ({partner_pct:.1f}%).")


# ===========================================================================
# RISK MANAGER: a mortgage against a fall in prices
# ===========================================================================

STRESS_FALLS = (1500, 2500, 3500)


def _ltv_offer(ctx):
    b = _draw(ctx, "rm_property", _buildings(ctx))
    if b is None:
        return None
    roll = _roll(ctx["player_id"], "rm_property", ctx["period"])
    owed = b["worth"] * (4000 + roll % 4500) // BPS
    fall = STRESS_FALLS[(roll // 11) % len(STRESS_FALLS)]
    return {
        "situation": f"Your bank has lent against {b['name']} in {b['district']}, {b['city']}. The risk committee wants to know "
                     f"what happens to the loan if property prices in the district fall {fall // 100}%, as they did when the "
                     "last bubble burst.",
        "task": ["Work out the loan against the building's value today (loan-to-value), and again after the fall.",
                 "Give the owner's stake after the fall (value less loan, negative if the loan is bigger), and say whether the "
                 "loan would then be bigger than the building is worth."],
        "pass_when": "At least three of the four answers are right.", "deadline": HAND_IN,
        "given": [_given("Value today", b["worth"]), _given("Owed on the loan", owed), _text("The fall to test", f"{fall // 100}%")],
        "fields": [{"key": "ltv", "label": "Loan-to-value today", "kind": "percent"},
                   {"key": "ltv_after", "label": "Loan-to-value after the fall", "kind": "percent"},
                   {"key": "equity", "label": "The owner's stake after the fall", "kind": "millions"},
                   _yes_no("under", "Is the loan then bigger than the building?")],
        "value": b["worth"], "owed": owed, "fall_bps": fall,
    }


def _ltv_submit(ctx, objective, answers):
    t = objective["terms"]
    after = t["value"] * (BPS - t["fall_bps"]) / BPS
    ltv, ltv_after = t["owed"] / t["value"] * 100, t["owed"] / after * 100
    equity = after - t["owed"]
    return _marked(objective, answers, [("ltv", "Loan-to-value today", ltv, 0.1), ("ltv_after", "Loan-to-value after", ltv_after, 0.1),
                                        ("equity", "Stake after", M(equity), 0.05), ("under", "Under water", "yes" if equity < 0 else "no", 0)], 3,
                   plain=f"Today the loan is {ltv:.1f}% of the building's value. After a {t['fall_bps'] // 100}% fall it is "
                         f"{ltv_after:.1f}%, and the owner's stake is {o._money(int(equity))}."
                         + (" The loan is under water: selling the building would not repay it." if equity < 0 else ""),
                   method="A loan against property is only as safe as the price of the property. Measure the loan against "
                          "today's value, then test it against a fall as deep as the worst the market has seen. An owner whose "
                          "stake is wiped out has little reason to keep paying, and the bank that must sell in a falling market "
                          "sells cheap.",
                   maths=f"Loan-to-value = {o._money(t['owed'])} ÷ {o._money(t['value'])} = {ltv:.1f}%. Value after = "
                         f"{o._money(t['value'])} × (1 − {t['fall_bps'] / 100:.0f}%) = {o._money(int(after))}. Loan-to-value after = "
                         f"{ltv_after:.1f}%. Stake = {o._money(int(after))} − {o._money(t['owed'])} = {o._money(int(equity))}.")


# ===========================================================================
# LEGAL COUNSEL: reading a title before a purchase (a case file made up for the paper)
# ===========================================================================

def _title_offer(ctx):
    conn = ctx["conn"]
    if o._one(conn, "SELECT to_regclass('districts') IS NOT NULL AS ok")["ok"] is not True:
        return None
    ds = list(prop.districts(conn).values())
    d = _draw(ctx, "lw_property", ds)
    if d is None:
        return None
    roll = _roll(ctx["player_id"], "lw_property", ctx["period"])
    seller_share = (10000, 10000, 7500, 6000)[roll % 4]
    claim = (0, 0, 2000, 3500)[(roll // 5) % 4]
    charge = bool((roll // 23) % 2)
    other = 10000 - seller_share
    entries = [f"Owner: the seller, {seller_share / 100:.0f}% of the plot."]
    if other:
        entries.append(f"Owner: a cousin of the seller, {other / 100:.0f}% of the plot, registered by inheritance.")
    if charge:
        entries.append("Charge: a mortgage to a bank, registered against the whole plot, not yet discharged.")
    if claim:
        entries.append(f"Caution: a claim lodged by a neighbour to {claim / 100:.0f}% of the seller's share, waiting for the court.")
    return {
        "situation": f"A client is about to buy the whole of a plot in {d['name']}, {d['city']}, from a seller. Before paying, your "
                     "firm has searched the lands registry. The extract is below. (This case file is an exercise made up for "
                     "the paper; it says nothing about the title of any real property in the game.)",
        "task": ["Read the extract. Give the share of the plot the seller can actually sell today without anybody else "
                 "joining in (a share under a court claim cannot be sold clean until the court decides).",
                 "Say whether a mortgage must be paid off from the price before the client takes the plot, and whether it is "
                 "safe to complete the purchase of the whole plot as it stands."],
        "pass_when": "All three answers are right.", "deadline": HAND_IN,
        "given": [_text(f"Registry entry {n}", e) for n, e in enumerate(entries, 1)],
        "fields": [{"key": "share", "label": "Share the seller can sell clean", "kind": "percent"},
                   _yes_no("charge", "Must a mortgage be paid off at completion?"),
                   _yes_no("safe", "Is it safe to complete the purchase of the whole plot?")],
        "seller_bps": seller_share, "claim_bps": claim, "charge": charge,
    }


def _title_submit(ctx, objective, answers):
    t = objective["terms"]
    clean = max(t["seller_bps"] * (BPS - t["claim_bps"]) / BPS, 0) / 100
    safe = t["seller_bps"] == BPS and t["claim_bps"] == 0
    return _marked(objective, answers, [("share", "Share sold clean", clean, 0.1), ("charge", "Mortgage to clear", "yes" if t["charge"] else "no", 0),
                                        ("safe", "Safe to complete", "yes" if safe else "no", 0)], 3,
                   plain=f"The seller can sell {clean:.1f}% clean. "
                         + ("A registered mortgage must be paid off out of the price at completion. " if t["charge"] else "")
                         + ("The whole plot can be bought safely." if safe else "Buying the whole plot now would leave the client "
                            "owning less than it paid for."),
                   method="Read every entry on the register, not only the owner's name. A share held by someone else must be "
                          "bought from them too; a registered charge is paid off from the price before the buyer takes the "
                          "property; a claim waiting for a court is a share nobody can sell clean until it is decided. Complete "
                          "only when the seller can pass on everything the buyer is paying for.",
                   maths=f"Clean share = seller's {t['seller_bps'] / 100:.0f}% × (1 − the {t['claim_bps'] / 100:.0f}% under claim) = {clean:.1f}%.")


# ===========================================================================
# FINANCIAL JOURNALIST: a district's quarter
# ===========================================================================

def _district_offer(ctx):
    conn = ctx["conn"]
    if o._one(conn, "SELECT to_regclass('district_results') IS NOT NULL AS ok")["ok"] is not True:
        return None
    last = ctx["period"] - 1
    rows = o._rows(conn, "SELECT r.*, d.name, d.city FROM district_results r JOIN districts d ON d.id = r.district_id"
                         " WHERE r.period = %s ORDER BY r.district_id", (last,))
    before = {r["district_id"]: r for r in o._rows(conn, "SELECT * FROM district_results WHERE period = %s", (last - 1,))}
    candidates = [{**r, "before": before[r["district_id"]]} for r in rows if r["district_id"] in before and before[r["district_id"]]["price_bps"] > 0]
    d = _draw(ctx, "jn_property", candidates)
    if d is None:
        return None
    b = d["before"]
    return {
        "situation": f"Your editor wants a short report on property in {d['name']}, {d['city']}, for last quarter. The Auction "
                     "House's figures are below, as an index: 100 is where prices and rents stood when the world began.",
        "task": ["Work out how far prices moved on the quarter, and how far rents moved, each as a percentage.",
                 "Say whether prices ran ahead of rents (prices rose more than rents by over two points: the sign of a bubble), "
                 "and choose the headline."],
        "pass_when": "At least three of the four answers are right.", "deadline": HAND_IN,
        "given": [_text("Price index, the quarter before", f"{b['price_bps'] / 100:.2f}"),
                  _text("Price index, last quarter", f"{d['price_bps'] / 100:.2f}"),
                  _text("Rent index, the quarter before", f"{b['rent_bps'] / 100:.2f}"),
                  _text("Rent index, last quarter", f"{d['rent_bps'] / 100:.2f}"),
                  _text("Share of space let, last quarter", f"{d['occupancy_bps'] / 100:.1f}%")],
        "fields": [{"key": "prices", "label": "Prices on the quarter", "kind": "percent"},
                   {"key": "rents", "label": "Rents on the quarter", "kind": "percent"},
                   _yes_no("ahead", "Did prices run ahead of rents?"),
                   {"key": "headline", "label": "Headline", "kind": "choice",
                    "options": [{"code": "up", "label": "Property prices rise"}, {"code": "down", "label": "Property prices fall"},
                                {"code": "flat", "label": "Property prices steady (within half a point)"}]}],
        "p0": b["price_bps"], "p1": d["price_bps"], "r0": b["rent_bps"], "r1": d["rent_bps"],
    }


def _district_submit(ctx, objective, answers):
    t = objective["terms"]
    prices = (t["p1"] - t["p0"]) / t["p0"] * 100
    rents = (t["r1"] - t["r0"]) / t["r0"] * 100
    ahead = prices - rents > 2
    headline = "flat" if abs(prices) < 0.5 else "up" if prices > 0 else "down"
    return _marked(objective, answers, [("prices", "Prices", prices, 0.1), ("rents", "Rents", rents, 0.1),
                                        ("ahead", "Ahead of rents", "yes" if ahead else "no", 0), ("headline", "Headline", headline, 0)], 3,
                   plain=f"Prices moved {prices:+.1f}% and rents {rents:+.1f}%. "
                         + ("Prices ran ahead of rents: buyers are paying for hope as well as for the rent." if ahead
                            else "Prices did not run ahead of rents."),
                   method="Report the change, not the level: readers want to know what happened this quarter. Put prices "
                          "beside rents, because rent is what a building earns, and a price that climbs faster than its rent "
                          "is being carried by buyers' enthusiasm. Write the headline from the figure, never from the mood.",
                   maths=f"Prices: ({t['p1'] / 100:.2f} − {t['p0'] / 100:.2f}) ÷ {t['p0'] / 100:.2f} = {prices:+.1f}%. "
                         f"Rents: ({t['r1'] / 100:.2f} − {t['r0'] / 100:.2f}) ÷ {t['r0'] / 100:.2f} = {rents:+.1f}%.")


# ===========================================================================
# Into the library
# ===========================================================================

T = o.Template
o.TEMPLATES.update({t.code: t for t in (
    T("am_property", "asset_manager", "Property investment", "Is the building worth its price?", 2, 70_000, 110, "hand_in",
      "A building is worth what its rent, after tax and upkeep, pays on the price, against what investors ask today.",
      "employer", _yield_offer, submit=_yield_submit),
    T("ac_property", "accountant", "Property cash flow", "Does the building pay its way?", 2, 60_000, 100, "hand_in",
      "A mortgaged building's rent must meet the bank, the tax office and the builders before it leaves anything.",
      "employer", _cash_offer, submit=_cash_submit),
    T("ib_property", "investment_banker", "Financing a purchase", "Put the money together for a building", 3, 90_000, 130, "hand_in",
      "A purchase is paid for from cash that can be spared, then a loan, then a partner, in that order.",
      "employer", _funding_offer, submit=_funding_submit),
    T("rm_property", "risk_manager", "Property risk", "Stress-test a mortgage", 2, 70_000, 110, "hand_in",
      "A loan against property is tested against a fall in prices as deep as the worst the market has seen.",
      "employer", _ltv_offer, submit=_ltv_submit),
    T("lw_property", "lawyer", "Land and title", "Read the title before the client pays", 2, 70_000, 110, "hand_in",
      "A buyer gets only what the register shows the seller can pass on.",
      "employer", _title_offer, submit=_title_submit),
    T("jn_property", "journalist", "Property reporting", "Report a district's quarter", 1, 50_000, 80, "hand_in",
      "Property prices are reported beside rents, because a price that outruns its rent is a warning.",
      "employer", _district_offer, submit=_district_submit),
)})
