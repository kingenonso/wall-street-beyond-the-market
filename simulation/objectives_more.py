"""Stage 6: the professional objectives of the Investment Banker, the Risk Manager, the
Legal Counsel and the Financial Journalist. They follow the same rules as the first twelve (see objectives.py):
practical work from one learning module, judged by the server against the game's own records,
paid by a named payer.
"""

from __future__ import annotations

import hashlib

from simulation import bonds, clock, exchange, insight, marketview
from simulation import objectives as o
from simulation import world_data as data
from simulation.money import BPS, apply_bps, naira

M = o._millions
BAND = (data.INFLATION_TARGET_BPS - data.INFLATION_BAND_BPS, data.INFLATION_TARGET_BPS + data.INFLATION_BAND_BPS)


def _roll(*parts) -> int:
    """A number fixed by its inputs: the same player, work and quarter always draw the same."""
    return int.from_bytes(hashlib.sha256((":".join(str(p) for p in parts) + o.SALT.get()).encode()).digest()[:8], "big")


def _marked(objective, answers, figures: list, need: int, *, must: tuple = (), plain: str, method: str, maths: str) -> dict:
    """Mark a paper of figures and choices. `figures` is a list of (key, label, right answer, tolerance):
    a number is right within its tolerance; a choice must match exactly."""
    right = {}
    for key, _label, truth, tolerance in figures:
        given = answers.get(key)
        right[key] = (str(given).strip().upper() == str(truth).upper()) if isinstance(truth, str) \
            else o._close_enough(given, truth, absolute=tolerance)
    points = 100 // len(figures)
    milestones = [o._milestone(label, points, right[key]) for key, label, _t, _tol in figures]
    count = sum(right.values())
    passed = count >= need and all(right[key] for key in must)
    return o._verdict("passed" if passed else "failed", f"{count} of {len(figures)} right.", milestones,
                      plain=plain, method=method, maths=maths,
                      answers={key: (truth if isinstance(truth, str) else round(truth, 2)) for key, _l, truth, _t in figures})


def _price_now(conn, now) -> dict:
    day, _ = exchange.session_of(now)
    return {s["id"]: s for s in marketview._shares(conn, day)}


def _year_profit(conn, company_id, upto: int) -> int | None:
    rows = o._rows(conn, "SELECT DISTINCT ON (period) (figures->'income_statement'->>'net_profit')::bigint AS profit FROM company_reports"
                         " WHERE company_id = %s AND period BETWEEN %s AND %s AND period >= 1 ORDER BY period, version DESC",
                   (company_id, upto - 3, upto))
    return sum(r["profit"] for r in rows) if len(rows) == 4 else None


def _yes_no(key: str, label: str) -> dict:
    return {"key": key, "label": label, "kind": "choice", "options": [{"code": "yes", "label": "Yes"}, {"code": "no", "label": "No"}]}


def _given(label: str, kobo: int) -> dict:
    return {"label": label, "kobo": kobo}


def _text(label: str, text: str) -> dict:
    return {"label": label, "text": text}


HAND_IN = "Hand it in before this quarter ends. It can be handed in once."
CALL = "Hand your call in before this quarter ends. It can be handed in once. The world decides the rest."


# ===========================================================================
# INVESTMENT BANKER
# ===========================================================================

def _multiples_offer(ctx):
    conn = ctx["conn"]
    prices = _price_now(conn, ctx["now"])
    candidates = []
    for company in o._filed(conn, ctx["period"] - 1):
        profit = _year_profit(conn, company["company_id"], ctx["period"] - 1)
        if profit and profit > 0 and company["figures"]["balance_sheet"]["total_equity"] > 0 and company["company_id"] in prices:
            candidates.append({**company, "year_profit": profit})
    company = o._choose(ctx, "ib_multiples", candidates)
    if company is None:
        return None
    share = prices[company["company_id"]]
    return {
        "client": o._client(company),
        "situation": f"A buyer has asked your bank what {company['name']} costs at today's share price, and whether that is dear "
                     f"or cheap. The first page of every pitch is the same four figures.",
        "task": ["Work out the four figures below from the share price and the filed accounts.",
                 "Profit per share uses the last four quarters' profit after tax.",
                 "Give market value in millions of naira, profit per share in naira, and the two ratios to one decimal place."],
        "pass_when": "At least three of the four figures are right.", "deadline": HAND_IN,
        "given": [_text("Share price", f"₦{share['price'] / 100:,.2f}"), _text("Shares in issue", f"{share['shares']:,}"),
                  _given("Profit after tax, last four quarters", company["year_profit"]),
                  _given("Owners' funds (total equity)", company["figures"]["balance_sheet"]["total_equity"])],
        "fields": [{"key": "market_value", "label": "Market value", "kind": "millions"},
                   {"key": "eps", "label": "Profit per share, a year", "kind": "naira"},
                   {"key": "pe", "label": "Price ÷ profit per share", "kind": "times"},
                   {"key": "pb", "label": "Price ÷ owners' funds per share", "kind": "times"}],
        "company_id": str(company["company_id"]), "price": share["price"], "shares": share["shares"],
        "year_profit": company["year_profit"], "equity": company["figures"]["balance_sheet"]["total_equity"],
    }


def _multiples_submit(ctx, objective, answers):
    t = objective["terms"]
    value = t["price"] * t["shares"]
    eps = t["year_profit"] / t["shares"] / 100
    pe, pb = value / t["year_profit"], value / t["equity"]
    return _marked(objective, answers, [("market_value", "Market value", M(value), 0.05), ("eps", "Profit per share", eps, 0.02),
                                        ("pe", "Price to profit", pe, 0.06), ("pb", "Price to owners' funds", pb, 0.06)], 3,
                   plain=f"Market value is what the whole company costs at today's price. Price to profit says how many years of "
                         f"today's profit a buyer is paying for: {pe:.1f} here. Price to owners' funds compares the price with what "
                         f"the accounts say the owners have put in and kept: {pb:.1f} times.",
                   method="Always use a full year's profit, because one quarter can be a strong or a weak season. Compare the "
                          "ratios with other companies in the same industry before calling a share dear or cheap: a fast-growing "
                          "company deserves a higher price for each naira of profit.",
                   maths=f"Market value = ₦{t['price'] / 100:,.2f} × {t['shares']:,} = {M(value):,.2f} million. Profit per share = "
                         f"{M(t['year_profit']):,.2f} million ÷ {t['shares']:,} = ₦{eps:,.2f}. Price ÷ profit = {pe:.1f}. "
                         f"Price ÷ owners' funds = {M(value):,.2f} ÷ {M(t['equity']):,.2f} = {pb:.1f}.")


DEBT_LIMIT = 4            # lenders grow wary above four times a year's EBITDA


def _capacity_offer(ctx):
    candidates = [c for c in o._filed(ctx["conn"], ctx["period"] - 1)
                  if c["figures"]["income_statement"]["ebitda"] > 0 and c["figures"]["balance_sheet"]["borrowings"] > 0
                  and c["sector"] not in ("banking", "insurance")]
    company = o._choose(ctx, "ib_capacity", candidates)
    if company is None:
        return None
    income, sheet = company["figures"]["income_statement"], company["figures"]["balance_sheet"]
    return {
        "client": o._client(company),
        "situation": f"{company['name']} wants to borrow to expand and has asked your bank how much more lenders would stand.",
        "task": [f"Lenders in this market grow wary when debt passes {DEBT_LIMIT} times a year's EBITDA.",
                 "Work out a year's EBITDA (four times the quarter's), today's debt against it, and how much more the company "
                 "could borrow before reaching the limit. If it is already past the limit, the room is nought.",
                 "Money in millions of naira; the ratio to one decimal place."],
        "pass_when": "At least two of the three figures are right, and the room to borrow is one of them.", "deadline": HAND_IN,
        "given": [_given("EBITDA last quarter", income["ebitda"]), _given("Total borrowings", sheet["borrowings"])],
        "fields": [{"key": "year_ebitda", "label": "A year's EBITDA", "kind": "millions"},
                   {"key": "ratio", "label": "Debt ÷ a year's EBITDA", "kind": "times"},
                   {"key": "room", "label": "Room to borrow more", "kind": "millions"}],
        "company_id": str(company["company_id"]), "ebitda": income["ebitda"], "debt": sheet["borrowings"],
    }


def _capacity_submit(ctx, objective, answers):
    t = objective["terms"]
    year = 4 * t["ebitda"]
    room = max(DEBT_LIMIT * year - t["debt"], 0)
    return _marked(objective, answers, [("year_ebitda", "A year's EBITDA", M(year), 0.05), ("ratio", "Debt to EBITDA", t["debt"] / year, 0.06),
                                        ("room", "Room to borrow", M(room), 0.2)], 2, must=("room",),
                   plain=f"A lender looks first at how many years of the business's own cash it would take to repay everything "
                         f"borrowed. This company owes {t['debt'] / year:.1f} times a year's EBITDA and could take on about "
                         f"{o._money(room)} more before lenders grow wary.",
                   method="Debt capacity is a ceiling, not a target. A banker also checks that profit covers interest at least "
                          "twice, and asks what happens to both in a bad year. A company at the limit in good times is over it in bad ones.",
                   maths=f"Year's EBITDA = 4 × {M(t['ebitda']):,.2f} = {M(year):,.2f}. Debt ÷ EBITDA = {M(t['debt']):,.2f} ÷ {M(year):,.2f} = "
                         f"{t['debt'] / year:.1f}. Room = {DEBT_LIMIT} × {M(year):,.2f} − {M(t['debt']):,.2f} = {M(room):,.2f} million.")


def _rights_offer(ctx):
    conn = ctx["conn"]
    prices = _price_now(conn, ctx["now"])
    candidates = [c for c in o._filed(conn, ctx["period"] - 1) if c["company_id"] in prices and prices[c["company_id"]]["price"] >= 500]
    company = o._choose(ctx, "ib_rights", candidates)
    if company is None:
        return None
    share = prices[company["company_id"]]
    new, held = data.RIGHTS_TERMS
    return {
        "client": o._client(company),
        "situation": f"{company['name']} is considering raising money from its own shareholders with a rights issue, and has "
                     f"asked your bank to set out the terms on this exchange's usual basis.",
        "task": [f"The usual terms: {new} new share for every {held} held, at {data.RIGHTS_DISCOUNT_BPS // 100}% below the market price.",
                 "Work out the price of a new share, how many new shares there would be, the money raised, and what one share "
                 "should be worth afterwards (old and new shares averaged).",
                 "Prices in naira to two places; shares and money in millions."],
        "pass_when": "At least three of the four figures are right.", "deadline": HAND_IN,
        "given": [_text("Share price", f"₦{share['price'] / 100:,.2f}"), _text("Shares in issue", f"{share['shares']:,}")],
        "fields": [{"key": "rights_price", "label": "Price of a new share", "kind": "naira"},
                   {"key": "new_shares", "label": "New shares (millions)", "kind": "number"},
                   {"key": "raised", "label": "Money raised", "kind": "millions"},
                   {"key": "after", "label": "Worth of one share afterwards", "kind": "naira"}],
        "company_id": str(company["company_id"]), "price": share["price"], "shares": share["shares"],
    }


def _rights_submit(ctx, objective, answers):
    t = objective["terms"]
    new, held = data.RIGHTS_TERMS
    price = t["price"] / 100
    rights = price * (BPS - data.RIGHTS_DISCOUNT_BPS) / BPS
    shares = t["shares"] * new / held
    after = (held * price + new * rights) / (held + new)
    return _marked(objective, answers, [("rights_price", "Price of a new share", rights, 0.02), ("new_shares", "New shares", shares / 1e6, 0.05),
                                        ("raised", "Money raised", shares * rights / 1e6, 0.5), ("after", "Worth afterwards", after, 0.02)], 3,
                   plain="A rights issue offers new shares to the existing owners first, cheaply, so that they are not pushed aside. "
                         "The share price falls afterwards, but an owner who takes up the rights is no worse off: they hold more "
                         "shares, each worth a little less. An owner who does nothing is diluted.",
                   method="The price after the issue is the average of the old shares at the old price and the new ones at the "
                          "rights price. The discount does not give anything away to anybody who takes up their rights; it only "
                          "makes sure the issue is taken up.",
                   maths=f"New share = ₦{price:,.2f} × {(BPS - data.RIGHTS_DISCOUNT_BPS) / 100:.0f}% = ₦{rights:,.2f}. New shares = "
                         f"{t['shares']:,} × {new}/{held} = {shares / 1e6:,.2f} million. Raised = {shares * rights / 1e6:,.2f} million. "
                         f"Afterwards = ({held} × {price:,.2f} + {new} × {rights:,.2f}) ÷ {held + new} = ₦{after:,.2f}.")


def _bond_for(ctx, code: str):
    """A plain bond with two to eight quarters left: short enough to price by hand."""
    lines = [b for b in bonds.listing(ctx["conn"], ctx["now"]) if b["kind"] == "fixed" and 2 <= b["quarters_left"] <= 8 and not b["distressed"]]
    lines.sort(key=lambda b: b["code"])
    if not lines:
        return None
    bond = dict(lines[_roll(ctx["player_id"], code, ctx["period"]) % len(lines)])
    if ":case:" in o.SALT.get():
        shift = (-150, -120, -90, -60, -30, 30, 60, 90, 120, 150)[_roll(ctx["player_id"], code, ctx["period"], "case") % 10]
        bond["yield_bps"] = max(bond["yield_bps"] + shift, 100)
        bond["case_note"] = True
    return bond


def _present_value(coupon_bps: int, quarters: int, yield_bps: int) -> float:
    """The price of a ₦1,000 bond paying a quarter of its yearly interest each quarter, in naira."""
    face, y = bonds.FACE / 100, yield_bps / BPS
    coupon = face * coupon_bps / BPS / 4
    return sum((coupon + (face if k == quarters else 0)) / (1 + y) ** (k / 4) for k in range(1, quarters + 1))


def _bond_terms(bond) -> list:
    return [_text("Bond", bond["name"]), _text("Repaid at the end", "₦1,000 a bond"),
            _text("Interest", f"{bond['coupon_bps'] / 100:.2f}% a year, a quarter of it paid each quarter"),
            _text("Quarters left", str(bond["quarters_left"])),
            _text("Return lenders want" + (" (as set for this case)" if bond.get("case_note") else " today"), f"{bond['yield_bps'] / 100:.2f}% a year")]


def _bondprice_offer(ctx):
    bond = _bond_for(ctx, "ib_bond")
    if bond is None:
        return None
    return {
        "situation": f"A client wants to sell a block of {bond['name']} and has asked your bank for a price before going to the desk.",
        "task": ["Price one bond: count each payment still to come for less the further off it is.",
                 "A payment k quarters away is divided by (1 + the yearly return wanted) to the power k/4.",
                 "Give the price in naira to two places, and say whether it is above or below ₦1,000."],
        "pass_when": "The price is within ₦3 of the right one, and you say rightly which side of ₦1,000 it is.", "deadline": HAND_IN,
        "given": _bond_terms(bond),
        "fields": [{"key": "price", "label": "Price of one bond", "kind": "naira"},
                   {"key": "side", "label": "Against ₦1,000", "kind": "choice",
                    "options": [{"code": "above", "label": "Above"}, {"code": "below", "label": "Below"}]}],
        "coupon_bps": bond["coupon_bps"], "quarters": bond["quarters_left"], "yield_bps": bond["yield_bps"],
    }


def _bondprice_submit(ctx, objective, answers):
    t = objective["terms"]
    price = _present_value(t["coupon_bps"], t["quarters"], t["yield_bps"])
    side = "above" if price > bonds.FACE / 100 else "below"
    return _marked(objective, answers, [("price", "The price", price, 3.0), ("side", "Above or below ₦1,000", side, 0)], 2,
                   plain=f"A bond is a string of promised payments. Its price is what those payments are worth today. When lenders "
                         f"want more than the bond pays ({t['yield_bps'] / 100:.2f}% against {t['coupon_bps'] / 100:.2f}%), nobody "
                         f"will pay full price for it, so it trades below ₦1,000; when they want less, it trades above.",
                   method="List every payment with its date, discount each one, and add them up. The last payment includes the "
                          "₦1,000 itself, which is why most of a bond's value sits at the end and long bonds move most when rates change.",
                   maths=f"{t['quarters']} payments of ₦{bonds.FACE / 100 * t['coupon_bps'] / BPS / 4:,.2f}, the last with ₦1,000 added, "
                         f"each ÷ (1 + {t['yield_bps'] / BPS:.4f})^(k/4), come to ₦{price:,.2f}.")


def _bid_scenario(ctx, code: str):
    """A bidder and a target from the same industry, and an offer the server draws."""
    conn = ctx["conn"]
    prices = _price_now(conn, ctx["now"])
    filed = sorted(o._filed(conn, ctx["period"] - 1), key=lambda c: c["ticker"])
    worth = {s["company_id"]: s["worth"] for s in o._priced(conn, ctx["now"])}
    pairs = []
    for target in filed:
        for bidder in filed:
            if bidder["sector"] == target["sector"] and bidder["company_id"] != target["company_id"] \
                    and prices[bidder["company_id"]]["market_value"] > 2 * prices[target["company_id"]]["market_value"]:
                pairs.append((bidder, target))
    if not pairs:
        return None
    bidder, target = pairs[_roll(ctx["player_id"], code, ctx["period"]) % len(pairs)]
    premium = (2000, 2500, 2800, 3000, 3500, 4000)[_roll(ctx["player_id"], code, ctx["period"], "p") % 6]
    t = prices[target["company_id"]]
    return {"bidder": bidder, "target": target, "premium_bps": premium, "price": t["price"], "shares": t["shares"],
            "worth": worth.get(target["company_id"], t["price"]), "bidder_value": prices[bidder["company_id"]]["market_value"]}


def _bid_numbers(t: dict) -> dict:
    offer = t["price"] * (BPS + t["premium_bps"]) // BPS
    stake = t["shares"] * data.TAKEOVER_STAKE_BPS // BPS
    return {"offer": offer, "stake": stake, "cost": offer * stake,
            "board": t["premium_bps"] >= data.BOARD_ACCEPTS_PREMIUM_BPS,
            "funds": t["premium_bps"] >= data.FUNDS_ACCEPT_PREMIUM_BPS and offer >= t["worth"],
            "vote": offer * stake * BPS > data.TAKEOVER_VOTE_ABOVE_BPS * t["bidder_value"]}


def _bid_given(s) -> list:
    return [_text("Target's share price", f"₦{s['price'] / 100:,.2f}"), _text("Target's shares in issue", f"{s['shares']:,}"),
            _text("Target's worth per share, from its filed figures", f"₦{s['worth'] / 100:,.2f}"),
            _text("Offer", f"{s['premium_bps'] / 100:.0f}% above the market price, for {data.TAKEOVER_STAKE_BPS // 100}% of the shares"),
            _given("Bidder's market value", s["bidder_value"])]


def _bid_terms(s) -> dict:
    return {"company_id": str(s["bidder"]["company_id"]), "price": s["price"], "shares": s["shares"], "worth": s["worth"],
            "premium_bps": s["premium_bps"], "bidder_value": s["bidder_value"], "target": o._client(s["target"])}


def _bid_offer(ctx):
    s = _bid_scenario(ctx, "ib_bid")
    if s is None:
        return None
    return {
        "client": o._client(s["bidder"]),
        "situation": f"{s['bidder']['name']} is thinking of bidding for {s['target']['name']} and has asked your bank to cost the "
                     f"offer and say how it would be received.",
        "task": ["Work out the offer price for a share and what the whole stake would cost.",
                 f"Then say how it would be received. On this exchange a target's board recommends an offer "
                 f"{data.BOARD_ACCEPTS_PREMIUM_BPS // 100}% or more above the market price. Pension funds accept one that is "
                 f"{data.FUNDS_ACCEPT_PREMIUM_BPS // 100}% or more above the market price and not below the share's worth."],
        "pass_when": "At least three of the four answers are right.", "deadline": HAND_IN, "given": _bid_given(s),
        "fields": [{"key": "offer", "label": "Offer price for a share", "kind": "naira"},
                   {"key": "cost", "label": "Cost of the stake", "kind": "millions"},
                   _yes_no("board", "Will the target's board recommend it?"), _yes_no("funds", "Will the pension funds accept it?")],
        **_bid_terms(s),
    }


def _bid_submit(ctx, objective, answers):
    t = objective["terms"]
    n = _bid_numbers(t)
    yes = lambda flag: "yes" if flag else "no"          # noqa: E731
    return _marked(objective, answers, [("offer", "Offer price", n["offer"] / 100, 0.02), ("cost", "Cost of the stake", M(n["cost"]), 1.0),
                                        ("board", "The board", yes(n["board"]), 0), ("funds", "The pension funds", yes(n["funds"]), 0)], 3,
                   plain=f"A bidder must pay more than the market price, or nobody would sell: that extra is the premium. At "
                         f"{t['premium_bps'] / 100:.0f}% the offer is ₦{n['offer'] / 100:,.2f} a share and the stake costs {o._money(n['cost'])}. "
                         f"The board {'would' if n['board'] else 'would not'} recommend it; the pension funds {'would' if n['funds'] else 'would not'} accept.",
                   method="Price an offer from both ends: what the target is worth to the bidder sets the most it should pay; what "
                          "the owners will accept sets the least. An offer the board rejects can still go straight to the owners "
                          "(a hostile bid), but it needs more than half of them.",
                   maths=f"Offer = ₦{t['price'] / 100:,.2f} × {1 + t['premium_bps'] / BPS:.2f} = ₦{n['offer'] / 100:,.2f}. Stake = "
                         f"{data.TAKEOVER_STAKE_BPS // 100}% × {t['shares']:,} = {n['stake']:,} shares; cost = {M(n['cost']):,.2f} million. "
                         f"Worth per share ₦{t['worth'] / 100:,.2f}.")


def _open_bids(conn) -> list[dict]:
    return o._rows(conn, "SELECT t.id, t.price, t.premium_bps, t.hostile, t.closes_period, coalesce(b.name, e.name) AS bidder, c.name AS target, c.ticker"
                         " FROM takeovers t LEFT JOIN companies b ON b.id = t.bidder_company_id LEFT JOIN empires e ON e.id = t.bidder_empire_id"
                         " JOIN companies c ON c.id = t.target_company_id"
                         " WHERE t.status = 'open' ORDER BY t.id")


def _outcome_offer(ctx):
    open_bids = _open_bids(ctx["conn"])
    if not open_bids:
        return None
    bid = open_bids[_roll(ctx["player_id"], "ib_outcome", ctx["period"]) % len(open_bids)]
    return {
        "situation": f"{bid['bidder']} has offered ₦{bid['price'] / 100:,.2f} a share for {bid['target']} ({bid['ticker']}), "
                     f"{bid['premium_bps'] / 100:.0f}% above the market price. {'The board has rejected it: it is a hostile bid.' if bid['hostile'] else 'The board recommends it.'} "
                     f"Your desk must tell its clients whether it will succeed.",
        "task": ["Decide whether the bidder will win more than half of the shares when the offer closes.",
                 "Look at who owns the target (Market, Who owns what), the premium, and the share's worth."],
        "pass_when": "Your call matches the result when the offer closes.", "deadline": CALL, "given": [],
        "fields": [{"key": "call", "label": "Your call", "kind": "choice",
                    "options": [{"code": "won", "label": "The bid will succeed"}, {"code": "failed", "label": "The bid will fail"}]}],
        "takeover_id": bid["id"], "for_period": bid["closes_period"],
    }


def _outcome_close(ctx, objective, period):
    bid = o._one(ctx["conn"], "SELECT status, outcome FROM takeovers WHERE id = %s", (objective["terms"]["takeover_id"],))
    if bid["status"] == "open":
        return None
    if objective["submission"] is None:
        return o._not_done("No call was handed in before the offer closed.")
    right = objective["submission"]["call"] == bid["status"]
    return o._verdict("passed" if right else "failed", f"The bid {'succeeded' if bid['status'] == 'won' else 'failed'}. {bid['outcome'] or ''}",
                      [o._milestone("The call matched the result", 100, right)],
                      plain="A takeover succeeds when the owners of more than half the shares accept. The owners are not one "
                            "person: founders, pension funds and small investors each decide by their own rule. " + (bid["outcome"] or ""),
                      method="Count the votes before the offer closes. Find who holds the shares, ask what each kind of holder needs "
                             "to see (a premium, a price above worth, the board's blessing), and add up who will say yes.",
                      maths="More than 50% of the shares must be offered for the bid to succeed.", answers={"call": bid["status"]})


# ===========================================================================
# RISK MANAGER
# ===========================================================================

def _due_soon(figures: dict, period: int) -> int:
    return sum(b["principal_outstanding"] for b in figures["notes"].get("borrowings", []) if b["maturity_period"] <= period + 3)


def _liquidity_offer(ctx):
    candidates = [c for c in o._filed(ctx["conn"], ctx["period"] - 1)
                  if c["sector"] not in ("banking", "insurance") and c["figures"]["income_statement"]["cost_of_sales"] > 0]
    company = o._choose(ctx, "rm_liquidity", candidates)
    if company is None:
        return None
    income, sheet = company["figures"]["income_statement"], company["figures"]["balance_sheet"]
    out = income["cost_of_sales"] + income["operating_expenses"] + income["interest_expense"]
    due = _due_soon(company["figures"], ctx["period"])
    return {
        "client": o._client(company),
        "situation": f"Your desk lends to {company['name']}. Before the limit is renewed, the credit committee wants to know how "
                     f"long the company could keep paying its way if no money came in.",
        "task": ["Work out the cash cover (cash ÷ a quarter's outgoings), how many days of outgoings the cash would pay for "
                 "(a quarter is 90 days), and the cash left if every debt due within a year had to be repaid today.",
                 "Cover to two decimal places; days as a whole number; money in millions (a shortfall is a minus figure)."],
        "pass_when": "At least two of the three figures are right.", "deadline": HAND_IN,
        "given": [_given("Cash", sheet["cash"]), _given("A quarter's outgoings (costs, running costs, interest)", out),
                  _given("Debt due within a year", due)],
        "fields": [{"key": "cover", "label": "Cash cover", "kind": "times"}, {"key": "days", "label": "Days of cash", "kind": "number"},
                   {"key": "after", "label": "Cash after repaying debt due", "kind": "millions"}],
        "company_id": str(company["company_id"]), "cash": sheet["cash"], "out": out, "due": due,
    }


def _liquidity_submit(ctx, objective, answers):
    t = objective["terms"]
    cover = t["cash"] / t["out"]
    return _marked(objective, answers, [("cover", "Cash cover", cover, 0.02), ("days", "Days of cash", cover * 90, 1.5),
                                        ("after", "Cash after debt due", M(t["cash"] - t["due"]), 0.2)], 2,
                   plain=f"Liquidity risk is the danger of running out of cash while still being a sound business. This company "
                         f"holds enough for {cover * 90:.0f} days of outgoings, and "
                         f"{'could' if t['cash'] >= t['due'] else 'could not'} repay the debt due within a year from cash alone.",
                   method="Set what is certain (cash in hand) against what must be paid, and assume the worst about what comes in. "
                          "Then look at the dates debts fall due: a company usually renews them, but a lender who refuses turns a "
                          "liquidity question into a crisis overnight.",
                   maths=f"Cover = {M(t['cash']):,.2f} ÷ {M(t['out']):,.2f} = {cover:.2f}. Days = {cover:.2f} × 90 = {cover * 90:.0f}. "
                         f"After debt due = {M(t['cash']):,.2f} − {M(t['due']):,.2f} = {M(t['cash'] - t['due']):,.2f} million.")


STRESS_FALL_BPS = 2000


def _stress_offer(ctx):
    candidates = [c for c in o._filed(ctx["conn"], ctx["period"] - 1)
                  if c["sector"] not in ("banking", "insurance") and c["figures"]["income_statement"]["interest_expense"] > 0
                  and c["figures"]["income_statement"]["cost_of_sales"] > 0]
    company = o._choose(ctx, "rm_stress", candidates)
    if company is None:
        return None
    income = company["figures"]["income_statement"]
    keep = {k: income[k] for k in ("revenue", "cost_of_sales", "operating_expenses", "depreciation", "interest_expense")}
    return {
        "client": o._client(company),
        "situation": f"The risk committee wants to know what a bad quarter would do to {company['name']}: sales "
                     f"{STRESS_FALL_BPS // 100}% lower than the last one.",
        "task": [f"Cut sales by {STRESS_FALL_BPS // 100}%. The cost of what is sold falls in the same proportion. Running costs, "
                 "depreciation and interest do not fall at all.",
                 "Work out operating profit and profit before tax in that quarter, and how many times operating profit would "
                 "cover the interest. Money in millions (a loss is a minus figure); cover to one decimal place."],
        "pass_when": "At least two of the three figures are right.", "deadline": HAND_IN,
        "given": [_given("Sales", keep["revenue"]), _given("Cost of what it sold", keep["cost_of_sales"]),
                  _given("Running costs", keep["operating_expenses"]), _given("Depreciation", keep["depreciation"]),
                  _given("Interest paid", keep["interest_expense"])],
        "fields": [{"key": "operating", "label": "Operating profit under stress", "kind": "millions"},
                   {"key": "before_tax", "label": "Profit before tax under stress", "kind": "millions"},
                   {"key": "cover", "label": "Interest cover under stress", "kind": "times"}],
        "company_id": str(company["company_id"]), **keep,
    }


def _stress_submit(ctx, objective, answers):
    t = objective["terms"]
    left = (BPS - STRESS_FALL_BPS) / BPS
    operating = (t["revenue"] - t["cost_of_sales"]) * left - t["operating_expenses"] - t["depreciation"]
    before = operating - t["interest_expense"]
    cover = operating / t["interest_expense"]
    return _marked(objective, answers, [("operating", "Operating profit", M(operating), 0.5), ("before_tax", "Profit before tax", M(before), 0.5),
                                        ("cover", "Interest cover", cover, 0.06)], 2,
                   plain=f"A stress test asks what a bad day would cost before it happens. Costs that do not fall with sales are what "
                         f"turn a dip in sales into a much bigger fall in profit. Here a {STRESS_FALL_BPS // 100}% fall in sales leaves "
                         f"operating profit of {o._money(int(operating))}, covering interest {cover:.1f} times.",
                   method="Split costs into those that move with sales and those that do not. The more fixed costs and debt a company "
                          "carries, the harder a fall in sales hits it. Choose a scenario that is bad but believable, and write the "
                          "limit before running the numbers.",
                   maths=f"({M(t['revenue']):,.2f} − {M(t['cost_of_sales']):,.2f}) × {left:.2f} − {M(t['operating_expenses']):,.2f} − "
                         f"{M(t['depreciation']):,.2f} = {M(operating):,.2f}. Before tax = {M(operating):,.2f} − {M(t['interest_expense']):,.2f} = "
                         f"{M(before):,.2f}. Cover = {cover:.1f}.")


def _shock_offer(ctx):
    bond = _bond_for(ctx, "rm_shock")
    if bond is None:
        return None
    return {
        "situation": f"The desk holds {bond['name']}. The risk committee wants to know what a rise of one full point in the "
                     f"return lenders want would cost.",
        "task": ["Price one bond at today's wanted return, and again with that return one point higher.",
                 "A payment k quarters away is divided by (1 + the yearly return) to the power k/4.",
                 "Give both prices in naira, and the loss as a percentage of today's price."],
        "pass_when": "At least two of the three figures are right.", "deadline": HAND_IN, "given": _bond_terms(bond),
        "fields": [{"key": "now", "label": "Price today", "kind": "naira"}, {"key": "after", "label": "Price after the rise", "kind": "naira"},
                   {"key": "loss", "label": "Loss", "kind": "percent"}],
        "coupon_bps": bond["coupon_bps"], "quarters": bond["quarters_left"], "yield_bps": bond["yield_bps"],
    }


def _shock_submit(ctx, objective, answers):
    t = objective["terms"]
    now = _present_value(t["coupon_bps"], t["quarters"], t["yield_bps"])
    after = _present_value(t["coupon_bps"], t["quarters"], t["yield_bps"] + 100)
    loss = (now - after) / now * 100
    return _marked(objective, answers, [("now", "Price today", now, 3.0), ("after", "Price after", after, 3.0), ("loss", "The loss", loss, 0.1)], 2,
                   plain=f"When lenders want one point more, this bond falls from ₦{now:,.2f} to ₦{after:,.2f}: a loss of {loss:.2f}%. "
                         f"That figure, the loss for a one-point rise, is how risk managers compare bonds of different lengths.",
                   method="Reprice, do not guess. The loss for a one-point move is roughly the bond's remaining life in years, a "
                          "little less: a rule of thumb worth checking against the full sum. Limits on a bond desk are set in "
                          "these terms, not in naira held.",
                   maths=f"{t['quarters']} payments discounted at {t['yield_bps'] / 100:.2f}% = ₦{now:,.2f}; at {(t['yield_bps'] + 100) / 100:.2f}% = "
                         f"₦{after:,.2f}. Loss = ({now:,.2f} − {after:,.2f}) ÷ {now:,.2f} = {loss:.2f}%.")


LIMITS = {"total": 150_000, "largest_bps": 2000, "cash_bps": 1000, "invested_bps": 5000, "bells": 3, "limit": 6}


def _limits_offer(ctx):
    return {
        "situation": "A risk manager who cannot keep their own book inside limits will not be trusted with anybody else's. The "
                     "desk has set three.",
        "task": [f"No single share more than {LIMITS['largest_bps'] // 100}% of everything you own.",
                 f"At least {LIMITS['cash_bps'] // 100}% in cash, and at least {LIMITS['invested_bps'] // 100}% in shares and bonds.",
                 f"You must own at least ₦{LIMITS['total']:,} in all. Be inside all three at {LIMITS['bells']} Closing Bells in a row."],
        "pass_when": f"Inside the limits at {LIMITS['bells']} Closing Bells running, within the next {LIMITS['limit']} bells.",
        "deadline": f"{LIMITS['limit']} Closing Bells from now.", "given": [], "fields": [],
    }


def _limits_bell(ctx, objective, day):
    have = o.wealth(ctx["conn"], ctx["account"], ctx["now"])
    total = have["total"]
    largest = max((line["value"] for line in have["lines"]), default=0)
    seen = {"largest_bps": largest * BPS // total if total else 0, "cash_bps": have["cash"] * BPS // total if total else 0,
            "invested_bps": (have["shares"] + have["bonds"]) * BPS // total if total else 0, "total": total}
    inside = (total >= naira(LIMITS["total"]) and seen["largest_bps"] <= LIMITS["largest_bps"] and seen["cash_bps"] >= LIMITS["cash_bps"]
              and seen["invested_bps"] >= LIMITS["invested_bps"])
    p = objective["progress"]
    p["bells"] = p.get("bells", 0) + 1
    p["run"] = p.get("run", 0) + 1 if inside else 0
    p["ever"] = p.get("ever", False) or inside
    p["tried"] = p.get("tried", False) or have["shares"] + have["bonds"] > 0
    p["last"] = seen
    if p["run"] < LIMITS["bells"] and p["bells"] < LIMITS["limit"]:
        return None
    passed = p["run"] >= LIMITS["bells"]
    return o._verdict("passed" if passed else "failed" if p["tried"] else "not_done",
                      f"At the bell: largest share {o._pct(seen['largest_bps'])}, cash {o._pct(seen['cash_bps'])}, invested {o._pct(seen['invested_bps'])}.",
                      [o._milestone("Inside the limits at a Closing Bell", 50, p["ever"]), o._milestone("Held it at three bells running", 50, passed)],
                      plain="A limit is a decision taken calmly, in advance, about how much can be lost in one place. It only works "
                            "if it is kept when keeping it is uncomfortable: a share that has doubled is now twice as large a bet.",
                      method="Measure against everything owned, not against what was paid. Check limits at the close of every day, "
                             "because prices move them without any trade. When one is broken, cut back to it at once and record why.",
                      maths=f"Largest share ÷ total = {o._pct(seen['largest_bps'])} (limit {o._pct(LIMITS['largest_bps'])}). Cash "
                            f"{o._pct(seen['cash_bps'])} (at least {o._pct(LIMITS['cash_bps'])}). Invested {o._pct(seen['invested_bps'])} "
                            f"(at least {o._pct(LIMITS['invested_bps'])}).")


def _direction_offer(ctx):
    if ctx["period"] < 3:
        return None
    company = o._choose(ctx, "rm_credit", o._unsettled(ctx["conn"], ctx["period"] - 1))
    if company is None:
        return None
    income, sheet = company["figures"]["income_statement"], company["figures"]["balance_sheet"]
    return {
        "client": o._client(company),
        "situation": f"Your desk has money lent to {company['name']}, rated {company['credit_rating']}. The credit committee meets "
                     f"before its next results and wants your view of where the rating is going.",
        "task": ["Say whether its credit rating will be higher, the same or lower when it files for the quarter now running."],
        "pass_when": "The rating moves the way you said.", "deadline": CALL,
        "given": [_given("EBITDA last quarter", income["ebitda"]), _given("Total borrowings", sheet["borrowings"]),
                  _given("Interest paid last quarter", income["interest_expense"]), _given("Cash", sheet["cash"]),
                  _given("Bills unpaid", sheet["payables"])],
        "fields": [{"key": "call", "label": "Its rating will be", "kind": "choice",
                    "options": [{"code": "up", "label": "Higher"}, {"code": "same", "label": "The same"}, {"code": "down", "label": "Lower"}]}],
        "company_id": str(company["company_id"]), "for_period": ctx["period"], "rating": company["credit_rating"],
    }


def _direction_close(ctx, objective, period):
    t = objective["terms"]
    if period < t["for_period"]:
        return None
    if objective["submission"] is None:
        return o._not_done("No call was handed in before the quarter ended.")
    now_rated = o._filed_one(ctx["conn"], t["company_id"], t["for_period"])["credit_rating"]
    was, new = o.RATINGS.index(t["rating"]), o.RATINGS.index(now_rated)
    happened = "up" if new < was else "down" if new > was else "same"
    right = objective["submission"]["call"] == happened
    return o._verdict("passed" if right else "failed", f"It was rated {t['rating']} and is now rated {now_rated}.",
                      [o._milestone("The rating moved the way you said", 100, right)],
                      plain="Credit risk is the chance of not being repaid. A rating moving down means that chance has risen, and "
                            "everything lent to that company is worth a little less from that day.",
                      method="Watch the figures the rating follows (debt against EBITDA, interest cover, cash, unpaid bills) and ask "
                             "what this quarter does to each. Ratings move slowly, so a manager who sees the direction early can "
                             "cut the exposure before the price of the debt falls.",
                      maths=f"The ladder runs AAA, AA, A, BBB, BB, B, CCC, D. {t['rating']} to {now_rated}: {happened}.",
                      answers={"call": happened})


def _inflation_offer(ctx):
    economy = o._one(ctx["conn"], "SELECT inflation_bps, next_policy_rate_bps FROM economy_results ORDER BY period DESC LIMIT 1")
    if ctx["period"] < 5 or economy is None:
        return None
    return {
        "situation": f"Prices rose {o._pct(economy['inflation_bps'])} over the last year. Every limit on the desk assumes something "
                     f"about where that figure goes next.",
        "task": ["Say where the yearly rise in prices will stand when this quarter ends: more than half a point higher, more than "
                 "half a point lower, or about the same.",
                 "The Economy page shows prices, wages, commodity prices and what households are spending."],
        "pass_when": "The figure published when the quarter ends is where you said.", "deadline": CALL,
        "given": [_text("Rise in prices over the last year", o._pct(economy["inflation_bps"])),
                  _text("The Central Bank's rate", o._pct(economy["next_policy_rate_bps"]))],
        "fields": [{"key": "call", "label": "The yearly rise in prices will be", "kind": "choice",
                    "options": [{"code": "higher", "label": "More than half a point higher"},
                                {"code": "same", "label": "About the same"}, {"code": "lower", "label": "More than half a point lower"}]}],
        "for_period": ctx["period"], "inflation_bps": economy["inflation_bps"],
    }


def _inflation_close(ctx, objective, period):
    t = objective["terms"]
    if period < t["for_period"]:
        return None
    if objective["submission"] is None:
        return o._not_done("No call was handed in before the quarter ended.")
    now = o._one(ctx["conn"], "SELECT inflation_bps FROM economy_results WHERE period = %s", (t["for_period"],))["inflation_bps"]
    move = now - t["inflation_bps"]
    happened = "higher" if move > 50 else "lower" if move < -50 else "same"
    right = objective["submission"]["call"] == happened
    return o._verdict("passed" if right else "failed", f"Prices had risen {o._pct(t['inflation_bps'])} over the year; now {o._pct(now)}.",
                      [o._milestone("The figure is where you said", 100, right)],
                      plain="Rising prices eat the value of money lent and of cash held, and they bring the Central Bank's rate up "
                            "after them. A risk manager who sees inflation turning can shorten bonds and trim lending before the rate moves.",
                      method="Follow what feeds prices: wages, commodity prices, how hard the economy is running against what it "
                             "can produce, and how fast money is growing. The Money Watch and the Economy page show each one.",
                      maths=f"{o._pct(now)} − {o._pct(t['inflation_bps'])} = {move / 100:+.2f} points. More than half a point either way counts as a move.",
                      answers={"call": happened})


# ===========================================================================
# LAWYER
# ===========================================================================

def _control_offer(ctx):
    conn = ctx["conn"]
    company = o._choose(ctx, "lw_control", o._filed(conn, ctx["period"] - 1))
    if company is None:
        return None
    asset = o._one(conn, "SELECT share_asset FROM companies WHERE id = %s", (company["company_id"],))["share_asset"]
    holders = marketview.shareholders(conn, company["company_id"], asset)
    return {
        "client": o._client(company),
        "situation": f"A client is thinking of dealing with {company['name']} and has asked who really controls it. The register "
                     f"of owners is public.",
        "task": ["From the register below, give the largest holder's share of the company, how many holders have 5% or more "
                 "(each must be named in any offer document), and whether any single holder controls it (more than half).",
                 "Give the share as a percentage to one decimal place."],
        "pass_when": "At least two of the three answers are right, and the largest holder's share is one of them.", "deadline": HAND_IN,
        "given": [_text(h["holder"], f"{h['shares']:,} shares") for h in holders],
        "fields": [{"key": "largest", "label": "Largest holder's share", "kind": "percent"},
                   {"key": "notifiable", "label": "Holders with 5% or more", "kind": "number"},
                   _yes_no("control", "Does any single holder control it?")],
        "company_id": str(company["company_id"]), "holders": [[h["holder"], h["shares"]] for h in holders],
    }


def _control_submit(ctx, objective, answers):
    holders = objective["terms"]["holders"]
    total = sum(shares for _, shares in holders)
    largest = max(shares for _, shares in holders) / total * 100
    count = sum(1 for _, shares in holders if shares * 20 >= total)
    return _marked(objective, answers, [("largest", "Largest holder's share", largest, 0.06), ("notifiable", "Holders with 5% or more", count, 0.1),
                                        ("control", "Control", "yes" if largest > 50 else "no", 0)], 2, must=("largest",),
                   plain=f"Whoever holds more than half of the votes decides who sits on the board, and so controls the company. "
                         f"Here the largest holder has {largest:.1f}%, so {'one holder controls it' if largest > 50 else 'nobody controls it alone, and any decision needs holders to agree'}.",
                   method="Read the register before the contract. Count shares, not names, and remember that shares vote. Large "
                          "holders must be disclosed because their decisions move the company; a holder just under half can "
                          "usually carry a vote, since many small holders never vote at all.",
                   maths=f"All shares: {total:,}. Largest = {max(s for _, s in holders):,} ÷ {total:,} = {largest:.1f}%. "
                         f"Holders at or above 5%: {count}.")


def _debts_offer(ctx):
    candidates = [c for c in o._filed(ctx["conn"], ctx["period"] - 1) if len(c["figures"]["notes"].get("borrowings", [])) >= 1]
    company = o._choose(ctx, "lw_debts", candidates)
    if company is None:
        return None
    debts = company["figures"]["notes"]["borrowings"]
    return {
        "client": o._client(company),
        "situation": f"A buyer is looking at {company['name']}. Your part of the due diligence is the debts: what is owed, to "
                     f"whom, and what falls due soon after the deal.",
        "task": ["From the schedule of borrowings in its filed accounts, give the total owed, how much reaches its end date within "
                 f"a year (by {clock.period_label(ctx['period'] + 3)}), and the highest yearly interest rate on any of it.",
                 "A loan already past its end date and still unpaid counts as ending within a year: it can be demanded today.",
                 "Money in millions of naira; the rate as a percentage."],
        "pass_when": "At least two of the three figures are right.", "deadline": HAND_IN,
        "given": [_text(f"{d['name']} ({d['lender']})",
                        f"{M(d['principal_outstanding']):,.2f} m at {d['annual_rate_bps'] / 100:.2f}%, "
                        + ("past its end date and still unpaid (overdue)" if d["maturity_period"] < ctx["period"]
                           else f"ends {clock.period_label(d['maturity_period'])}"))
                  for d in debts],
        "fields": [{"key": "total", "label": "Total owed", "kind": "millions"}, {"key": "due", "label": "Ending within a year", "kind": "millions"},
                   {"key": "rate", "label": "Highest interest rate", "kind": "percent"}],
        "company_id": str(company["company_id"]), "debts": [[d["principal_outstanding"], d["annual_rate_bps"], d["maturity_period"]] for d in debts],
        "by": ctx["period"] + 3,
    }


def _debts_submit(ctx, objective, answers):
    t = objective["terms"]
    total = sum(d[0] for d in t["debts"])
    due = sum(d[0] for d in t["debts"] if d[2] <= t["by"])
    rate = max(d[1] for d in t["debts"]) / 100
    return _marked(objective, answers, [("total", "Total owed", M(total), 0.2), ("due", "Ending within a year", M(due), 0.2),
                                        ("rate", "Highest rate", rate, 0.02)], 2,
                   plain=f"A buyer takes on a company's debts with it. {o._money(total)} is owed, and {o._money(due)} of it reaches "
                         f"its end date within a year: money the new owner must repay or persuade the lender to renew.",
                   method="Read every loan for three things: when it ends, what it costs, and what lets the lender demand it back "
                          "early (a change of owner often does). Put the dates in one schedule; a deal that looks cheap can be "
                          "expensive if half the debt falls due the quarter after.",
                   maths=f"Total = {M(total):,.2f} million. Ending by {clock.period_label(t['by'])} = {M(due):,.2f} million. Highest rate = {rate:.2f}%.")


def _rules_offer(ctx):
    s = _bid_scenario(ctx, "lw_rules")
    if s is None:
        return None
    return {
        "client": o._client(s["bidder"]),
        "situation": f"{s['bidder']['name']} intends to bid for {s['target']['name']}. Before anything is announced, its board wants "
                     f"to know what the takeover rules will require.",
        "task": [f"The rules of this exchange: a target's board rejects an offer less than {data.BOARD_ACCEPTS_PREMIUM_BPS // 100}% "
                 f"above the market price, which makes the bid hostile. A purchase costing more than "
                 f"{data.TAKEOVER_VOTE_ABOVE_BPS // 100}% of the bidder's own market value needs a vote of the bidder's shareholders. "
                 f"A bid succeeds only if more than half of all the target's shares are offered.",
                 "Answer the three questions. Give the shares in millions, to two places."],
        "pass_when": "At least two of the three answers are right.", "deadline": HAND_IN, "given": _bid_given(s),
        "fields": [_yes_no("hostile", "Will the bid be hostile?"), _yes_no("vote", "Must the bidder's own shareholders vote?"),
                   {"key": "needed", "label": "Shares that must be offered for it to succeed (millions)", "kind": "number"}],
        **_bid_terms(s),
    }


def _rules_submit(ctx, objective, answers):
    t = objective["terms"]
    n = _bid_numbers(t)
    yes = lambda flag: "yes" if flag else "no"          # noqa: E731
    return _marked(objective, answers, [("hostile", "Hostile or not", yes(not n["board"]), 0), ("vote", "The bidder's vote", yes(n["vote"]), 0),
                                        ("needed", "Shares needed", t["shares"] / 2 / 1e6, 0.02)], 2,
                   plain=f"Takeover rules exist so that every owner is treated alike and nobody gains control by stealth. This bid "
                         f"{'would be hostile' if not n['board'] else 'would have the board behind it'}; the bidder's own shareholders "
                         f"{'must' if n['vote'] else 'need not'} vote; and it needs more than {t['shares'] // 2:,} shares.",
                   method="Work through the rules in the order they bite: first whether the bidder may bid at all without asking its "
                          "own owners, then how the target's board will answer, then what acceptance is needed. Each answer changes "
                          "the timetable and the documents.",
                   maths=f"Premium {t['premium_bps'] / 100:.0f}% against the board's {data.BOARD_ACCEPTS_PREMIUM_BPS // 100}%. Cost "
                         f"{M(n['cost']):,.2f} million against {data.TAKEOVER_VOTE_ABOVE_BPS // 100}% of {M(t['bidder_value']):,.2f} million = "
                         f"{M(t['bidder_value']) * data.TAKEOVER_VOTE_ABOVE_BPS / BPS:,.2f} million. Half of {t['shares']:,} shares = {t['shares'] / 2 / 1e6:,.2f} million.")


def _claims_offer(ctx):
    company = o._choose(ctx, "lw_claims", o._strained(ctx["conn"], ctx["period"] - 1))
    if company is None:
        return None
    sheet = company["figures"]["balance_sheet"]
    keep = {k: sheet[k] for k in ("borrowings", "payables", "customer_funds", "total_liabilities", "total_assets")}
    return {
        "client": o._client(company),
        "situation": f"A supplier owed money by {company['name']} has asked what it could expect if the company were wound up.",
        "task": ["Draw up the schedule of claims from the filed balance sheet: what is owed in all, and how many times the "
                 "company's assets cover it at the value in the accounts.",
                 "Then say whether everybody could be paid in full if the assets fetched that value.",
                 "Money in millions; cover to two decimal places."],
        "pass_when": "At least two of the three answers are right.", "deadline": HAND_IN,
        "given": [_given("Owed to lenders", keep["borrowings"]), _given("Bills unpaid", keep["payables"]),
                  _given("Customers' money it holds", keep["customer_funds"]), _given("Everything it owns, as valued in its accounts", keep["total_assets"])],
        "fields": [{"key": "owed", "label": "Owed in all", "kind": "millions"}, {"key": "cover", "label": "Assets ÷ what is owed", "kind": "times"},
                   _yes_no("full", "Could everybody be paid in full?")],
        "company_id": str(company["company_id"]), **keep,
    }


def _claims_submit(ctx, objective, answers):
    t = objective["terms"]
    cover = t["total_assets"] / t["total_liabilities"] if t["total_liabilities"] else 99.0
    return _marked(objective, answers, [("owed", "Owed in all", M(t["total_liabilities"]), 0.5), ("cover", "Cover", cover, 0.02),
                                        ("full", "Paid in full", "yes" if cover >= 1 else "no", 0)], 2,
                   plain=f"When a company is wound up, what it owns is sold and shared among those it owes, in order. Here the "
                         f"accounts show assets of {cover:.2f} times what is owed. Owners come last and get only what is left.",
                   method="Start from the balance sheet but do not trust its values: buildings sold in a hurry fetch less than the "
                          "accounts say. List the claims in their order of priority and work down until the money runs out. "
                          "Whoever is at the bottom should settle early.",
                   maths=f"Owed = {M(t['borrowings']):,.2f} + {M(t['payables']):,.2f} + {M(t['customer_funds']):,.2f} = "
                         f"{M(t['total_liabilities']):,.2f} million. Cover = {M(t['total_assets']):,.2f} ÷ {M(t['total_liabilities']):,.2f} = {cover:.2f}.")


def _default_offer(ctx):
    pool = [c for c in o._strained(ctx["conn"], ctx["period"] - 1) if c["credit_rating"] != "D"]
    company = o._choose(ctx, "lw_default", pool)
    if company is None:
        return None
    sheet, notes = company["figures"]["balance_sheet"], company["figures"]["notes"]
    return {
        "client": o._client(company),
        "situation": f"A lender to {company['name']} (rated {company['credit_rating']}) wants to know whether to prepare papers "
                     f"for a default before the next results.",
        "task": ["Decide whether the company will be rated D, in default, when it files for the quarter now running.",
                 "A company is in default when debt past its repayment date stays unpaid."],
        "pass_when": "Your call matches its rating at the next filing.", "deadline": CALL,
        "given": [_given("Cash", sheet["cash"]), _given("Bills unpaid", sheet["payables"]),
                  _given("Debt past its repayment date", notes.get("principal_overdue", 0)),
                  _given("Debt reaching its end date this quarter", _due_soon(company["figures"], ctx["period"] - 3))],
        "fields": [{"key": "call", "label": "Your call", "kind": "choice",
                    "options": [{"code": "default", "label": "It will be in default"}, {"code": "not", "label": "It will not"}]}],
        "company_id": str(company["company_id"]), "for_period": ctx["period"],
    }


def _default_close(ctx, objective, period):
    t = objective["terms"]
    if period < t["for_period"]:
        return None
    if objective["submission"] is None:
        return o._not_done("No call was handed in before the quarter ended.")
    rated = o._filed_one(ctx["conn"], t["company_id"], t["for_period"])["credit_rating"]
    happened = "default" if rated == "D" else "not"
    right = objective["submission"]["call"] == happened
    return o._verdict("passed" if right else "failed", f"It is now rated {rated}.", [o._milestone("The call matched the rating", 100, right)],
                      plain="Default is a legal event, not an opinion: a payment that was due was not made. From that day lenders "
                            "may demand everything back, and the company's fate passes from its owners to those it owes.",
                      method="Read the loan's end dates against the cash, and ask whether the lender will renew: banks renew for a "
                             "borrower with a sound rating and no unpaid bills. Prepare papers early; the lender who moves first "
                             "is paid first.",
                      maths=f"Rating at the filing for {clock.period_label(t['for_period'])}: {rated}.", answers={"call": happened})


# ===========================================================================
# JOURNALIST
# ===========================================================================

def _story_offer(ctx):
    conn = ctx["conn"]
    if ctx["period"] < 3:
        return None
    company = o._choose(ctx, "jr_results", [c for c in o._filed(conn, ctx["period"] - 1)
                                             if c["figures"]["income_statement"]["revenue"] > 0])
    if company is None:
        return None
    compare = ctx["period"] - 5 if o._filed_one(conn, company["company_id"], ctx["period"] - 5) and ctx["period"] - 5 >= 1 else ctx["period"] - 2
    label, against = clock.period_label(ctx["period"] - 1), clock.period_label(compare)
    return {
        "client": o._client(company),
        "situation": f"Your editor wants 200 words on {company['name']}'s results for {label}, and will not print a figure that "
                     f"has not been checked against the filing.",
        "task": [f"Find the filing on the company's page and give the three facts the story rests on: sales for {label}, how they "
                 f"compare with {against}, and profit after tax.",
                 "Sales and profit in millions of naira; the change as a percentage (a fall is a minus figure)."],
        "pass_when": "All three facts are right.", "deadline": HAND_IN, "given": [],
        "fields": [{"key": "sales", "label": f"Sales, {label}", "kind": "millions"},
                   {"key": "change", "label": f"Change in sales on {against}", "kind": "percent"},
                   {"key": "profit", "label": "Profit after tax", "kind": "millions"}],
        "company_id": str(company["company_id"]), "filed_period": ctx["period"] - 1, "compare_period": compare,
    }


def _story_submit(ctx, objective, answers):
    t = objective["terms"]
    now = o._filed_one(ctx["conn"], t["company_id"], t["filed_period"])["figures"]["income_statement"]
    was = o._filed_one(ctx["conn"], t["company_id"], t["compare_period"])["figures"]["income_statement"]
    change = (now["revenue"] - was["revenue"]) / was["revenue"] * 100 if was["revenue"] else 0.0
    return _marked(objective, answers, [("sales", "Sales", M(now["revenue"]), 0.5), ("change", "The change", change, 0.15),
                                        ("profit", "Profit after tax", M(now["net_profit"]), 0.5)], 3,
                   plain=f"A results story stands on three checked facts: what was sold, how that compares, and what was left. "
                         f"{objective['terms']['client']['name']} sold {o._money(now['revenue'])}, {change:+.1f}% on "
                         f"{clock.period_label(t['compare_period'])}, and made {o._money(now['net_profit'])} after tax.",
                   method="Take figures from the filing itself, never from somebody's summary of it. Compare like with like: the "
                          "same quarter a year ago where there is one, because many businesses have seasons. Say what the "
                          "comparison is in the story.",
                   maths=f"Change = ({M(now['revenue']):,.2f} − {M(was['revenue']):,.2f}) ÷ {M(was['revenue']):,.2f} = {change:+.1f}%.")


def _economy_offer(ctx):
    economy = o._one(ctx["conn"], "SELECT period, inflation_bps, next_policy_rate_bps, price_index_bps FROM economy_results ORDER BY period DESC LIMIT 1")
    if economy is None or ctx["period"] < 2:
        return None
    return {
        "situation": "The paper runs a box on the economy every quarter. Your editor wants this quarter's, each figure checked "
                     "against what the Central Bank has published.",
        "task": ["From the Economy page, give the rise in prices over the last year, the Central Bank's interest rate now, and "
                 "how far prices have risen in all since the world began.",
                 f"Then say whether the yearly rise is inside the band the Central Bank accepts "
                 f"({BAND[0] // 100}% to {BAND[1] // 100}%)."],
        "pass_when": "At least three of the four answers are right.", "deadline": HAND_IN, "given": [],
        "fields": [{"key": "inflation", "label": "Rise in prices over the last year", "kind": "percent"},
                   {"key": "rate", "label": "The Central Bank's rate", "kind": "percent"},
                   {"key": "since", "label": "Rise in prices since the start", "kind": "percent"},
                   _yes_no("inside", "Is the yearly rise inside the band?")],
        "economy_period": economy["period"],
    }


def _economy_submit(ctx, objective, answers):
    e = o._one(ctx["conn"], "SELECT inflation_bps, next_policy_rate_bps, price_index_bps FROM economy_results WHERE period = %s",
               (objective["terms"]["economy_period"],))
    low, high = BAND
    inside = "yes" if low <= e["inflation_bps"] <= high else "no"
    since = (e["price_index_bps"] - BPS) / 100
    return _marked(objective, answers, [("inflation", "Rise in prices", e["inflation_bps"] / 100, 0.06), ("rate", "The rate", e["next_policy_rate_bps"] / 100, 0.06),
                                        ("since", "Since the start", since, 0.15), ("inside", "Inside the band", inside, 0)], 3,
                   plain=f"Prices rose {e['inflation_bps'] / 100:.1f}% over the year and the Central Bank's rate is "
                         f"{e['next_policy_rate_bps'] / 100:.1f}%. Readers plan their saving and borrowing by those two figures, so "
                         f"they have to be right.",
                   method="Go to the source, quote the period each figure covers, and never mix a yearly figure with a quarterly "
                          "one. When a figure is outside the Central Bank's band, say so and say what the bank's published rule "
                          "says it will do next.",
                   maths=f"Price index {e['price_index_bps'] / BPS:.4f} against 1.0000 at the start = {since:.1f}% in all. Band "
                         f"{low / 100:.0f}% to {high / 100:.0f}%.")


def _claims_about(conn, company: dict, period: int, player_id) -> list[dict]:
    """Three statements about a company. Each is true or has been changed, by a draw fixed for this player."""
    income, sheet = company["figures"]["income_statement"], company["figures"]["balance_sheet"]
    before = o._filed_one(conn, company["company_id"], period - 1)
    change = (income["revenue"] - before["figures"]["income_statement"]["revenue"]) * 100 / before["figures"]["income_statement"]["revenue"]
    flips = [_roll(player_id, "jr_verify", period, n) % 2 == 0 for n in range(3)]
    if all(flips) or not any(flips):
        flips[1] = not flips[1]                      # never all true or all false
    rating = company["credit_rating"]
    wrong_rating = o.RATINGS[(o.RATINGS.index(rating) + 2) % len(o.RATINGS)]
    return [
        {"key": "c1", "true": flips[0],
         "text": f"\"Sales {'rose' if (change >= 0) == flips[0] else 'fell'} {abs(change):.1f}% on the quarter before.\""},
        {"key": "c2", "true": flips[1],
         "text": f"\"It ended the quarter with {o._money(sheet['cash'] if flips[1] else sheet['cash'] * 3 // 2 + 1_000_000_00)} in cash.\""},
        {"key": "c3", "true": flips[2], "text": f"\"Its credit rating is {rating if flips[2] else wrong_rating}.\""},
    ]


def _verify_offer(ctx):
    conn = ctx["conn"]
    if ctx["period"] < 3:
        return None
    company = o._choose(ctx, "jr_verify", [c for c in o._filed(conn, ctx["period"] - 1)
                                            if c["figures"]["income_statement"]["revenue"] > 0 and c["figures"]["balance_sheet"]["cash"] > 0])
    if company is None:
        return None
    claims = _claims_about(conn, company, ctx["period"] - 1, ctx["player_id"])
    choice = lambda c: {"key": c["key"], "label": c["text"], "kind": "choice",                   # noqa: E731
                        "options": [{"code": "true", "label": "True"}, {"code": "false", "label": "False"}]}
    return {
        "client": o._client(company),
        "situation": f"A message is going round the market about {company['name']}'s results for "
                     f"{clock.period_label(ctx['period'] - 1)}. Three claims in it are below. A rival paper is about to print them.",
        "task": ["Check each claim against the company's filing and its page, and mark it true or false."],
        "pass_when": "All three are marked rightly.", "deadline": HAND_IN, "given": [],
        "fields": [choice(c) for c in claims],
        "company_id": str(company["company_id"]), "filed_period": ctx["period"] - 1,
    }


def _verify_submit(ctx, objective, answers):
    t = objective["terms"]
    company = next(c for c in o._filed(ctx["conn"], t["filed_period"]) if str(c["company_id"]) == t["company_id"])
    claims = _claims_about(ctx["conn"], company, t["filed_period"], objective["player_id"])
    return _marked(objective, answers, [(c["key"], c["text"], "true" if c["true"] else "false", 0) for c in claims], 3,
                   plain="A claim repeated by many people is still one claim. Until it has been set beside the record it is a "
                         "rumour, and printing a rumour that proves false costs a paper its readers' trust.",
                   method="Take each claim apart into something that can be checked: a figure, a date, a name. Find the record for "
                          "each. Print only what the record supports, and say plainly what could not be confirmed.",
                   maths=" ".join(f"{c['text']} {'True' if c['true'] else 'False'}." for c in claims))


def _league_offer(ctx):
    # An industry is offered once it has three listed companies, because a leader and its share of an industry
    # of one or two says nothing. Part 4c's six have three listed each (the fourth is private and files nothing),
    # so they are offered on the same rule as every other industry and never fall below it.
    sectors = [s for s in insight.industries(ctx["conn"], ctx["now"]) if len(s["companies"]) >= 3 and s["sales"] > 0]
    if not sectors:
        return None
    sector = sectors[_roll(ctx["player_id"], "jr_league", ctx["period"]) % len(sectors)]
    return {
        "situation": f"The business desk is preparing a feature on {sector['name'].lower()}. It opens with who leads the industry "
                     f"and by how much.",
        "task": ["From the Industries page (Market, Industries), give the three-letter code of the company with the largest share "
                 "of the industry's sales over the last year, that share, and how many listed companies are in the industry.",
                 "Give the share as a percentage to one decimal place."],
        "pass_when": "At least two of the three answers are right, and the leader is one of them.", "deadline": HAND_IN, "given": [],
        "fields": [{"key": "ticker", "label": "The leader (its three-letter code)", "kind": "ticker"},
                   {"key": "share", "label": "Its share of the industry's sales", "kind": "percent"},
                   {"key": "count", "label": "Companies in the industry", "kind": "number"}],
        "sector": sector["code"],
    }


def _league_submit(ctx, objective, answers):
    sector = next(s for s in insight.industries(ctx["conn"], ctx["now"]) if s["code"] == objective["terms"]["sector"])
    leader = sector["companies"][0]
    return _marked(objective, answers, [("ticker", "The leader", leader["ticker"], 0), ("share", "Its share", leader["share_bps"] / 100, 0.15),
                                        ("count", "Companies", len(sector["companies"]), 0.1)], 2, must=("ticker",),
                   plain=f"{leader['name']} leads {sector['name'].lower()} with {leader['share_bps'] / 100:.1f}% of the industry's sales. "
                         f"Who leads, and how far ahead, tells a reader who sets prices in an industry and who must follow.",
                   method="Rank by sales over a full year, not one quarter. Say what the ranking measures, since the largest by "
                          "sales is not always the most profitable or the most valuable.",
                   maths=f"{leader['ticker']}: {M(leader['sales']):,.0f} million of {M(sector['sales']):,.0f} million = {leader['share_bps'] / 100:.1f}%. "
                         f"{len(sector['companies'])} companies.")


def _ratecall_offer(ctx):
    economy = o._one(ctx["conn"], "SELECT next_policy_rate_bps, inflation_bps FROM economy_results ORDER BY period DESC LIMIT 1")
    if economy is None or ctx["period"] < 2:
        return None
    return {
        "situation": f"The Central Bank decides its interest rate when this quarter ends. It is {o._pct(economy['next_policy_rate_bps'])} "
                     f"now, and prices rose {o._pct(economy['inflation_bps'])} over the year. Your editor wants the paper's forecast "
                     f"on the front page the day before.",
        "task": ["Say what the Central Bank will do. The Economy page gives the rule it follows."],
        "pass_when": "The Central Bank does what you said.", "deadline": CALL,
        "given": [_text("The Central Bank's rate now", o._pct(economy["next_policy_rate_bps"])),
                  _text("Prices over the last year", o._pct(economy["inflation_bps"]))],
        "fields": [{"key": "call", "label": "The paper's forecast", "kind": "choice",
                    "options": [{"code": code, "label": label} for code, label in o.CALLS.items()]}],
        "for_period": ctx["period"], "rate_bps": economy["next_policy_rate_bps"],
    }


def _ratecall_close(ctx, objective, period):
    t = objective["terms"]
    if period < t["for_period"]:
        return None
    if objective["submission"] is None:
        return o._not_done("No forecast was handed in before the decision.")
    after = o._one(ctx["conn"], "SELECT next_policy_rate_bps, rate_reason FROM economy_results WHERE period = %s", (t["for_period"],))
    happened = "rise" if after["next_policy_rate_bps"] > t["rate_bps"] else "fall" if after["next_policy_rate_bps"] < t["rate_bps"] else "hold"
    right = objective["submission"]["call"] == happened
    return o._verdict("passed" if right else "failed",
                      f"The rate went from {o._pct(t['rate_bps'])} to {o._pct(after['next_policy_rate_bps'])}.",
                      [o._milestone("The forecast was right", 100, right)],
                      plain=f"The Central Bank's rate is the price of money for everybody else. {after['rate_reason'] or ''}",
                      method="The bank publishes its rule, so a forecast is a reading of the rule, not a guess: set the rise in "
                             "prices against its target, look at how hard the economy is running, and remember it moves at most "
                             "half a point at a time.",
                      maths=f"{o._pct(t['rate_bps'])} to {o._pct(after['next_policy_rate_bps'])}: {happened}.", answers={"call": happened})


def _behind(figures: dict) -> bool:
    return figures["balance_sheet"]["payables"] > 0 or figures["notes"].get("principal_overdue", 0) > 0 \
        or figures["notes"].get("repayments_missed", 0) > 0


def _scoop_offer(ctx):
    if ctx["period"] < 3:
        return None
    return {
        "situation": "Every paper reports a company in trouble after it files. The story that makes a name is the one printed "
                     "before: which company, paying its way today, will fall behind this quarter?",
        "task": ["Name one company that was up to date with its bills and its lenders at its last filing and will not be at its next.",
                 "Read the filings, the credit ratings, this quarter's news and what is happening in each industry."],
        "pass_when": "The company you name was up to date at its last filing and has fallen behind at its next.", "deadline": CALL,
        "given": [], "fields": [{"key": "ticker", "label": "The company (its three-letter code)", "kind": "ticker"}],
        "for_period": ctx["period"],
    }


def _scoop_submit(ctx, objective, answers):
    ticker = str(answers.get("ticker", "")).upper().strip()
    company = next((c for c in o._filed(ctx["conn"], objective["terms"]["for_period"] - 1) if c["ticker"] == ticker), None)
    if company is None:
        raise o.ObjectiveError("There is no company with that code.")
    if _behind(company["figures"]):
        raise o.ObjectiveError(f"{company['name']} was already behind at its last filing. That is not news.")
    answers["ticker"] = ticker
    objective["progress"]["named"] = {"company_id": str(company["company_id"]), "name": company["name"]}
    return None


def _scoop_close(ctx, objective, period):
    t = objective["terms"]
    if period < t["for_period"]:
        return None
    named = objective["progress"].get("named")
    if named is None:
        return o._not_done("No company was named before the quarter ended.")
    fell = _behind(o._filed_one(ctx["conn"], named["company_id"], t["for_period"])["figures"])
    others = [c["name"] for c in o._filed(ctx["conn"], t["for_period"]) if _behind(c["figures"])
              and not _behind(o._filed_one(ctx["conn"], c["company_id"], t["for_period"] - 1)["figures"])]
    return o._verdict("passed" if fell else "failed", f"{named['name']} {'fell behind' if fell else 'paid everything that fell due'}.",
                      [o._milestone("The company named fell behind", 100, fell)],
                      plain="An investigation starts from a question the records can answer. "
                            + (f"This quarter the companies that newly fell behind were: {', '.join(others)}." if others
                               else "This quarter no company newly fell behind: there was no story to find, and saying so is also journalism."),
                      method="Look for strain before it shows: cash falling quarter after quarter, a rating slipping, debt reaching "
                             "its end date, an industry hit by this quarter's events. Then ask who would lose, and check with the record.",
                      maths="Behind means bills unpaid, debt past its date, or a repayment missed in the quarter.",
                      answers={"newly_behind": others})


# ===========================================================================
# Into the library
# ===========================================================================

T = o.Template
o.TEMPLATES.update({t.code: t for t in (
    T("ib_multiples", "investment_banker", "Valuation by comparison", "What does the company cost?", 1, 40_000, 60, "hand_in",
      "Market value, and price against profit and against owners' funds, are the first page of every deal.",
      "client", _multiples_offer, submit=_multiples_submit),
    T("ib_capacity", "investment_banker", "Raising debt", "How much more can it borrow?", 1, 50_000, 80, "hand_in",
      "Lenders measure debt against the cash a business throws off in a year.", "client", _capacity_offer, submit=_capacity_submit),
    T("ib_rights", "investment_banker", "Share issues", "Set out a rights issue", 2, 60_000, 100, "hand_in",
      "A rights issue raises money from the owners first, at a discount, without pushing them aside.",
      "client", _rights_offer, submit=_rights_submit),
    T("ib_bond", "investment_banker", "Bond issues", "Price the bond", 2, 80_000, 120, "hand_in",
      "A bond's price is what its promised payments are worth today.", "employer", _bondprice_offer, submit=_bondprice_submit),
    T("ib_bid", "investment_banker", "Takeovers", "Cost the offer", 3, 100_000, 150, "hand_in",
      "A bid is priced between what the target is worth to the bidder and what its owners will accept.",
      "client", _bid_offer, submit=_bid_submit),
    T("ib_outcome", "investment_banker", "Deal execution", "Will the bid succeed?", 4, 120_000, 180, "hand_in",
      "A takeover is won by counting who owns the shares and what each needs to see.",
      "employer", _outcome_offer, submit=o._choice_submit("call", ("won", "failed")), close=_outcome_close),

    T("rm_liquidity", "risk_manager", "Liquidity risk", "How long could it keep paying?", 1, 40_000, 60, "hand_in",
      "A sound business can still fail if it runs out of cash before the money comes in.",
      "employer", _liquidity_offer, submit=_liquidity_submit),
    T("rm_stress", "risk_manager", "Stress testing", "Stress the sales", 1, 50_000, 80, "hand_in",
      "Costs that do not fall with sales turn a dip in sales into a much bigger fall in profit.",
      "employer", _stress_offer, submit=_stress_submit),
    T("rm_shock", "risk_manager", "Market risk", "A one-point rate shock", 2, 80_000, 120, "hand_in",
      "The loss for a one-point rise in rates is how bonds of different lengths are compared.",
      "employer", _shock_offer, submit=_shock_submit),
    T("rm_limits", "risk_manager", "Exposure limits", "Stay inside the limits", 2, 70_000, 110, "market",
      "A limit is a decision taken in advance about how much can be lost in one place.", "employer", _limits_offer, bell=_limits_bell),
    T("rm_credit", "risk_manager", "Credit risk", "Where is the rating going?", 3, 70_000, 100, "hand_in",
      "A rating moving down means the chance of not being repaid has risen.",
      "employer", _direction_offer, submit=o._choice_submit("call", ("up", "same", "down")), close=_direction_close),
    T("rm_inflation", "risk_manager", "Risk in the economy", "Where are prices going?", 4, 90_000, 130, "hand_in",
      "Rising prices eat the value of money lent and bring interest rates up after them.",
      "employer", _inflation_offer, submit=o._choice_submit("call", ("higher", "same", "lower")), close=_inflation_close),

    T("lw_control", "investment_banker", "Company law: ownership and control", "Who controls the company?", 1, 40_000, 60, "hand_in",
      "Shares vote. Whoever holds more than half of them controls the company.", "client", _control_offer, submit=_control_submit),
    T("lw_debts", "investment_banker", "Due diligence", "The schedule of debts", 1, 50_000, 80, "hand_in",
      "A buyer takes on a company's debts with it: what is owed, at what cost, and when it falls due.",
      "client", _debts_offer, submit=_debts_submit),
    T("lw_rules", "investment_banker", "Takeover law", "What do the takeover rules require?", 2, 70_000, 110, "hand_in",
      "Takeover rules exist so that every owner is treated alike and nobody gains control by stealth.",
      "client", _rules_offer, submit=_rules_submit),
    T("lw_claims", "investment_banker", "Insolvency", "The schedule of claims", 2, 70_000, 110, "hand_in",
      "When a company is wound up, what it owns is shared among those it owes, in order; owners come last.",
      "employer", _claims_offer, submit=_claims_submit),
    T("lw_default", "investment_banker", "Lending and default", "Will it default?", 4, 90_000, 130, "hand_in",
      "Default is a legal event: a payment that was due was not made.",
      "employer", _default_offer, submit=o._choice_submit("call", ("default", "not")), close=_default_close),

    T("jr_results", "investment_banker", "Company reporting", "File the results story", 1, 40_000, 60, "hand_in",
      "A results story stands on three facts checked against the filing.", "employer", _story_offer, submit=_story_submit),
    T("jr_economy", "investment_banker", "Economic reporting", "The economy in four figures", 1, 40_000, 60, "hand_in",
      "Readers plan by the rise in prices and the Central Bank's rate, so both have to be right.",
      "employer", _economy_offer, submit=_economy_submit),
    T("jr_verify", "investment_banker", "Verification", "Check the claims before they are printed", 2, 60_000, 100, "hand_in",
      "A claim repeated by many people is still one claim until it is set beside the record.",
      "employer", _verify_offer, submit=_verify_submit),
    T("jr_league", "investment_banker", "Industry research", "Who leads the industry?", 2, 60_000, 100, "hand_in",
      "Who leads an industry, and by how much, tells who sets prices and who must follow.",
      "employer", _league_offer, submit=_league_submit),
    T("jr_rate", "investment_banker", "Economic research", "Forecast the Central Bank", 3, 70_000, 100, "hand_in",
      "The Central Bank publishes its rule, so a forecast is a reading of the rule.",
      "employer", _ratecall_offer, submit=o._choice_submit("call", tuple(o.CALLS)), close=_ratecall_close),
    T("jr_scoop", "investment_banker", "Investigation", "Name the company in trouble before it files", 4, 150_000, 200, "hand_in",
      "The story that makes a name is the one printed before the filing.",
      "employer", _scoop_offer, submit=_scoop_submit, close=_scoop_close),
)})


# ===========================================================================
# Stage 7. A sixth piece of work for the Legal Counsel to do alone (Contracts), and the portfolio review
# that is part of the Asset Manager's rank case.
# ===========================================================================

def _covenant_offer(ctx):
    candidates = [c for c in o._filed(ctx["conn"], ctx["period"] - 1)
                  if c["sector"] not in ("banking", "insurance") and c["figures"]["income_statement"]["ebitda"] > 0
                  and c["figures"]["income_statement"]["interest_expense"] > 0 and c["figures"]["balance_sheet"]["borrowings"] > 0]
    company = o._choose(ctx, "lw_contract", candidates)
    if company is None:
        return None
    income, sheet = company["figures"]["income_statement"], company["figures"]["balance_sheet"]
    ratio, cover = sheet["borrowings"] / (4 * income["ebitda"]), income["operating_profit"] / income["interest_expense"]
    # The limits are drawn, but never within a tenth of the company's own figure: a contract is not decided on a rounding.
    limits = [m for m in (30, 35, 40, 45, 50) if abs(ratio - m / 10) >= 0.1]
    floors = [f for f in (15, 20, 25, 30) if abs(cover - f / 10) >= 0.1]
    most = limits[_roll(ctx["player_id"], "lw_contract", ctx["period"], company["company_id"], "d") % len(limits)]
    least = floors[_roll(ctx["player_id"], "lw_contract", ctx["period"], company["company_id"], "c") % len(floors)]
    return {
        "client": o._client(company),
        "situation": f"A lender to {company['name']} has asked your firm to read its loan agreement against the accounts for "
                     f"{clock.period_label(company['period'])}. The agreement holds two promises (covenants) the company must keep.",
        "task": [f"Promise one: debt must not be more than {most / 10:.1f} times a year's EBITDA (four times the quarter's).",
                 f"Promise two: operating profit must cover the interest at least {least / 10:.1f} times.",
                 "Work out both figures to one decimal place, and say whether either promise is broken. If one is, the lender "
                 "may demand the whole loan back.",
                 "This agreement measures a year's EBITDA as four times the last quarter's. (Many measure the last four quarters; "
                 "the contract's own definition is the one that counts.)"],
        "pass_when": "At least two of the three answers are right, and whether a promise is broken is one of them.",
        "deadline": HAND_IN,
        "given": [_given("EBITDA last quarter", income["ebitda"]), _given("Operating profit", income["operating_profit"]),
                  _given("Interest paid", income["interest_expense"]), _given("Total borrowings", sheet["borrowings"])],
        "fields": [{"key": "ratio", "label": "Debt ÷ a year's EBITDA", "kind": "times"},
                   {"key": "cover", "label": "Interest cover", "kind": "times"},
                   _yes_no("broken", "Is a promise broken?")],
        "company_id": str(company["company_id"]), "ebitda": income["ebitda"], "operating": income["operating_profit"],
        "interest": income["interest_expense"], "debt": sheet["borrowings"], "most": most, "least": least,
    }


def _covenant_submit(ctx, objective, answers):
    t = objective["terms"]
    ratio = t["debt"] / (4 * t["ebitda"])
    cover = t["operating"] / t["interest"]
    broken = ratio > t["most"] / 10 or cover < t["least"] / 10
    return _marked(objective, answers, [("ratio", "Debt to EBITDA", ratio, 0.06), ("cover", "Interest cover", cover, 0.06),
                                        ("broken", "Whether a promise is broken", "yes" if broken else "no", 0)], 2, must=("broken",),
                   plain=f"A loan agreement is a contract with promises in it. Break one and the lender may ask for everything back "
                         f"at once, even if every payment so far was made on time. Here debt is {ratio:.1f} times a year's EBITDA "
                         f"(the limit is {t['most'] / 10:.1f}) and interest is covered {cover:.1f} times (the least allowed is "
                         f"{t['least'] / 10:.1f}): " + ("a promise is broken." if broken else "both promises are kept."),
                   method="Read the definitions before the numbers: a contract says exactly which profit and which debt are meant, "
                          "and over what period. Test each promise on its own. When one is broken, the usual course is not to "
                          "demand the money but to agree a waiver for a fee, on tighter terms; the lawyer's work is to protect "
                          "the client's right to do either.",
                   maths=f"Debt ÷ (4 × EBITDA) = {M(t['debt']):,.2f} ÷ {M(4 * t['ebitda']):,.2f} = {ratio:.1f}. "
                         f"Cover = {M(t['operating']):,.2f} ÷ {M(t['interest']):,.2f} = {cover:.1f}.")


REVIEW_LARGEST_BPS, REVIEW_CASH_BPS = 3000, 500


def _review_offer(ctx):
    """A client's portfolio, drawn from the live market, to be reviewed against a mandate."""
    shares = sorted(_price_now(ctx["conn"], ctx["now"]).values(), key=lambda s: s["ticker"])
    if len(shares) < 4:
        return None
    seed = (ctx["player_id"], "am_review", ctx["period"])
    first = _roll(*seed) % len(shares)
    lines = []
    for n in range(4):
        share = shares[(first + n * 7) % len(shares)]
        if any(line["ticker"] == share["ticker"] for line in lines):
            return None
        target = naira((40_000, 25_000, 20_000, 60_000, 15_000, 35_000)[_roll(*seed, n) % 6])
        lines.append({"ticker": share["ticker"], "name": share["name"], "shares": max(target // share["price"], 1), "price": share["price"]})
    options = (2_000, 5_000, 8_000, 12_000, 20_000)
    start = _roll(*seed, "cash") % 5
    values = [line["shares"] * line["price"] for line in lines]
    cash = None
    for n in range(5):                         # a portfolio a hair from a limit is not set: the review must have a clear answer
        candidate = naira(options[(start + n) % 5])
        total = sum(values) + candidate
        if abs(max(values) / total * 100 - REVIEW_LARGEST_BPS / 100) >= 0.2 and abs(candidate / total * 100 - REVIEW_CASH_BPS / 100) >= 0.2:
            cash = candidate
            break
    if cash is None:
        return None
    return {
        "situation": "A client has brought your firm the portfolio below and asked for a review against their mandate: no single "
                     f"holding above {REVIEW_LARGEST_BPS // 100}% of the whole, and at least {REVIEW_CASH_BPS // 100}% kept in cash.",
        "task": ["Value each holding at today's price and add the cash.",
                 "Give the portfolio's total value in naira, the largest holding as a percentage of the whole, the cash as a "
                 "percentage of the whole (both to one decimal place), and whether the portfolio is inside the mandate."],
        "pass_when": "At least three of the four answers are right.", "deadline": HAND_IN,
        "given": [_text(f"{line['name']} ({line['ticker']})", f"{line['shares']:,} shares at ₦{line['price'] / 100:,.2f}") for line in lines]
                 + [_given("Cash", cash)],
        "fields": [{"key": "total", "label": "Total value", "kind": "naira"},
                   {"key": "largest", "label": "Largest holding, share of the whole", "kind": "percent"},
                   {"key": "cash", "label": "Cash, share of the whole", "kind": "percent"},
                   _yes_no("inside", "Is it inside the mandate?")],
        "lines": [[line["shares"], line["price"]] for line in lines], "cash": cash,
    }


def _review_submit(ctx, objective, answers):
    t = objective["terms"]
    values = [shares * price for shares, price in t["lines"]]
    total = sum(values) + t["cash"]
    largest, cash = max(values) / total * 100, t["cash"] / total * 100
    inside = largest <= REVIEW_LARGEST_BPS / 100 and cash >= REVIEW_CASH_BPS / 100
    return _marked(objective, answers, [("total", "Total value", total / 100, 5.0), ("largest", "Largest holding", largest, 0.1),
                                        ("cash", "Cash", cash, 0.1), ("inside", "Inside the mandate", "yes" if inside else "no", 0)], 3,
                   plain=f"A mandate is the client's instruction about risk, written as limits. This portfolio is worth "
                         f"{o._money(total)}; its largest holding is {largest:.1f}% of it and {cash:.1f}% is in cash, so it is "
                         f"{'inside' if inside else 'outside'} the mandate.",
                   method="Value everything at today's price, not at what was paid. Measure each limit against the whole portfolio, "
                          "cash included. A holding drifts over a limit simply by rising in price, which is why a portfolio is "
                          "reviewed on a timetable and not only when something is bought.",
                   maths="Holdings: " + " + ".join(f"{v / 100:,.0f}" for v in values) + f" + cash {t['cash'] / 100:,.0f} = ₦{total / 100:,.0f}. "
                         f"Largest = {max(values) / 100:,.0f} ÷ {total / 100:,.0f} = {largest:.1f}%. Cash = {cash:.1f}%.")


o.TEMPLATES.update({t.code: t for t in (
    T("lw_contract", "investment_banker", "Contracts", "Has the borrower broken its promises?", 3, 80_000, 120, "hand_in",
      "A contract is a set of promises; what follows when one is broken is written in it before anything goes wrong.",
      "client", _covenant_offer, submit=_covenant_submit),
    T("am_review", "asset_manager", "Portfolio review", "Review a client's portfolio", 1, 0, 0, "hand_in",
      "A portfolio is judged against the client's mandate, at today's prices.", "employer", _review_offer, submit=_review_submit,
      listed=False),
)})
