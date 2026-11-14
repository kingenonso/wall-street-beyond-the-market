"""Stage 9: work about borrowing, short selling and derivatives, one piece for each of the six builds.

The Asset Manager measures a loan against shares through a fall; the Accountant prices a future from the cost of
carry; the Investment Banker uses put-call parity; the Risk Manager works out value at risk; Legal Counsel reads a
securities lending agreement; the Financial Journalist reports a share's short interest. They follow the same
rules as the rest of the library (objectives.py): practical work, judged by the server, paid by the employer.
Only public figures are used: share prices, each share's own swing, and today's interest rate.
"""

from __future__ import annotations

import hashlib
import math

from simulation import objectives as o
from simulation import risk
from simulation import world_data as data
from simulation.money import BPS
from simulation.objectives_more import HAND_IN, _given, _marked, _text, _yes_no

M = o._millions


def _roll(*parts) -> int:
    return int.from_bytes(hashlib.sha256((":".join(str(p) for p in parts) + o.SALT.get()).encode()).digest()[:8], "big")


def _shares(ctx) -> list[dict]:
    rows = o._rows(ctx["conn"], "SELECT c.id, c.ticker, c.name, coalesce(m.last_price, m.reference_price) AS price FROM market_instruments m"
                                " JOIN companies c ON c.id = m.company_id WHERE c.status = 'trading' ORDER BY c.ticker")
    return [r for r in rows if r["price"] and r["price"] > 0]


def _draw(ctx, code: str, candidates: list):
    if ctx.get("target") is not None:
        return None
    return o._pick(ctx["player_id"], code, ctx["period"], candidates)


def _rate(ctx) -> int:
    row = o._one(ctx["conn"], "SELECT next_policy_rate_bps FROM economy_results ORDER BY period DESC LIMIT 1")
    return row["next_policy_rate_bps"] if row else data.NEUTRAL_RATE_BPS


def _naira(kobo: float) -> str:
    return f"₦{kobo / 100:,.2f}"


# ===========================================================================
# ASSET MANAGER: a loan against shares, through a fall
# ===========================================================================

def _margin_offer(ctx):
    share = _draw(ctx, "am_margin", _shares(ctx))
    if share is None:
        return None
    roll = _roll(ctx["player_id"], "am_margin", ctx["period"])
    worth = (20_000_000 + (roll % 9) * 5_000_000) * 100                  # ₦20m to ₦60m of shares
    loan = worth * (3000 + (roll // 9) % 2000) // BPS                    # 30% to 50% borrowed against them
    fall = (10, 20, 30, 40)[(roll // 97) % 4]
    return {
        "situation": f"A client holds {_naira(worth)} of {share['name']} ({share['ticker']}) shares and has borrowed {_naira(loan)} against "
                     f"them. The cash borrowed has been spent. The bank makes a margin call when the loan reaches "
                     f"{data.MARGIN_CALL_BPS // 100}% of what the client holds, and then wants the loan brought back to "
                     f"{data.MARGIN_LOAN_MOST_BPS // 100}%.",
        "task": ["Work out the loan as a share of the holding now, and after the share price falls the amount given.",
                 "Say whether the fall brings a margin call, and how much the client must repay to bring the loan back to "
                 f"{data.MARGIN_LOAN_MOST_BPS // 100}% of the holding after the fall (nought if there is no call)."],
        "pass_when": "At least three of the four answers are right.", "deadline": HAND_IN,
        "given": [_given("The shares are worth", worth), _given("The loan", loan), _text("The fall in the share price", f"{fall}%")],
        "fields": [{"key": "ltv", "label": "Loan as a share of the holding now", "kind": "percent"},
                   {"key": "ltv_after", "label": "Loan as a share of the holding after the fall", "kind": "percent"},
                   _yes_no("call", "Is there a margin call?"),
                   {"key": "repay", "label": "To repay (if there is a call)", "kind": "millions"}],
        "worth": worth, "loan": loan, "fall": fall,
    }


def _margin_submit(ctx, objective, answers):
    t = objective["terms"]
    after = t["worth"] * (100 - t["fall"]) / 100
    ltv, ltv_after = t["loan"] / t["worth"] * 100, t["loan"] / after * 100
    call = ltv_after >= data.MARGIN_CALL_BPS / 100
    repay = max(t["loan"] - after * data.MARGIN_LOAN_MOST_BPS / BPS, 0) if call else 0
    return _marked(objective, answers, [("ltv", "Loan now", ltv, 0.1), ("ltv_after", "Loan after the fall", ltv_after, 0.1),
                                        ("call", "Margin call", "yes" if call else "no", 0), ("repay", "To repay", M(repay), 0.05)], 3,
                   plain=f"The loan is {ltv:.1f}% of the holding now and {ltv_after:.1f}% after a {t['fall']}% fall. "
                         + (f"That brings a margin call: the client must repay {o._money(int(repay))}." if call else "That is below the call."),
                   method="Borrowing against shares multiplies both gains and losses: the loan stays the same while the shares move. "
                          "Measure the loan against what the shares are worth after a fall, not before. A margin call is met by "
                          "repaying or by holding more; if it is not met, the bank sells the shares, at the worst moment, at a discount.",
                   maths=f"Now: {o._money(t['loan'])} ÷ {o._money(t['worth'])} = {ltv:.1f}%. After: the shares are worth {o._money(int(after))}, "
                         f"so {o._money(t['loan'])} ÷ {o._money(int(after))} = {ltv_after:.1f}%. To repay = loan − half of the holding = "
                         f"{o._money(int(repay))}.")


# ===========================================================================
# ACCOUNTANT: a future's price from the cost of carry
# ===========================================================================

def _carry_offer(ctx):
    if ctx.get("target") is not None:
        return None
    from simulation import exchange, marketview
    day, _ = exchange.session_of(ctx["now"])
    level = marketview.index_level(marketview._shares(ctx["conn"], day), marketview.index_base(ctx["conn"]))
    if not level:
        return None
    roll = _roll(ctx["player_id"], "ac_carry", ctx["period"])
    weeks = 1 + roll % 7                                                 # real days to settlement, in a quarter of seven
    rate = _rate(ctx)
    quoted_bps = (-80, -30, 30, 80)[(roll // 7) % 4]
    fair_points = level / 100 * (1 + rate / BPS * weeks / data.GAME_YEAR_REAL_DAYS)
    quoted = round(fair_points * (BPS + quoted_bps) / BPS, 2)
    return {
        "situation": "Your employer's treasury wants to know whether the market makers' price for the BSX 50 future is fair. "
                     "A future's fair price is today's level carried to the day it settles at the interest rate: whoever buys the "
                     "future instead of the shares keeps their cash in the bank meanwhile.",
        "task": ["Work out the fair price: the index today times (1 + the yearly rate × the part of a game year left). A game year is "
                 f"{data.GAME_YEAR_REAL_DAYS} trading days.",
                 f"Give the cost of carry for one contract in naira (₦{data.INDEX_KOBO_PER_POINT // 100} a point), and say whether the quoted "
                 "price is above the fair price."],
        "pass_when": "At least two of the three answers are right.", "deadline": HAND_IN,
        "given": [_text("The BSX 50 today", f"{level / 100:,.2f}"), _text("The Central Bank's rate", f"{rate / 100:.2f}% a year"),
                  _text("Trading days to settlement", str(weeks)), _text("The quoted futures price", f"{quoted:,.2f}")],
        "fields": [{"key": "fair", "label": "Fair futures price (points)", "kind": "number"},
                   {"key": "carry", "label": "Cost of carry, one contract", "kind": "naira"},
                   _yes_no("above", "Is the quoted price above the fair price?")],
        "level": level, "days": weeks, "rate": rate, "quoted": quoted,
    }


def _carry_submit(ctx, objective, answers):
    t = objective["terms"]
    spot = t["level"] / 100
    fair = spot * (1 + t["rate"] / BPS * t["days"] / data.GAME_YEAR_REAL_DAYS)
    carry = (fair - spot) * data.INDEX_KOBO_PER_POINT / 100
    above = t["quoted"] > fair
    return _marked(objective, answers, [("fair", "Fair price", fair, 0.05), ("carry", "Cost of carry", carry, max(carry * 0.01, 1)),
                                        ("above", "Quoted above fair", "yes" if above else "no", 0)], 2,
                   plain=f"Carried at {t['rate'] / 100:.2f}% for {t['days']} trading days, {spot:,.2f} becomes {fair:,.2f}. The quote of "
                         f"{t['quoted']:,.2f} is {'above' if above else 'below'} that.",
                   method="A future is the asset delivered later, so its fair price is today's price plus what it costs to wait: the interest "
                          "the buyer keeps meanwhile (less any income the asset pays). Compare the quote with that: a future dearer than "
                          "its carry is worth selling against the asset; cheaper, worth buying.",
                   maths=f"Fair = {spot:,.2f} × (1 + {t['rate'] / 100:.2f}% × {t['days']}/{data.GAME_YEAR_REAL_DAYS}) = {fair:,.2f}. Carry = "
                         f"({fair:,.2f} − {spot:,.2f}) × ₦{data.INDEX_KOBO_PER_POINT // 100} = ₦{carry / 100:,.2f}.")


# ===========================================================================
# INVESTMENT BANKER: put-call parity
# ===========================================================================

def _parity_offer(ctx):
    share = _draw(ctx, "ib_parity", _shares(ctx))
    if share is None:
        return None
    from simulation import derivatives
    roll = _roll(ctx["player_id"], "ib_parity", ctx["period"])
    spot = share["price"]
    strike = derivatives._strike(spot, (9000, 10000, 11000)[roll % 3])
    days = 2 + (roll // 3) % 5
    rate = _rate(ctx)
    t = days / data.GAME_YEAR_REAL_DAYS
    vol = max((risk.share_risk(ctx["conn"]).get(share["id"]) or {}).get("volatility_bps", 3000), data.OPTION_LEAST_VOLATILITY_BPS) / BPS
    call = derivatives.black_scholes("call", spot, strike, t, vol, rate / BPS)
    return {
        "situation": f"A client wants to protect a holding of {share['name']} ({share['ticker']}) with a put. The market makers quote only "
                     "the call. Your desk prices the put from the call: a call, less a put, at the same strike and date, is worth the "
                     "share less the strike paid later (put-call parity).",
        "task": ["Work out the strike's value today: the strike × e^(−rate × time), with time in game years (28 trading days a year).",
                 "Then the put's price per share: call − share price + the strike's value today.",
                 "Give the call's intrinsic value (what it would pay now: share price − strike, or nought) and its time value (its price "
                 "less its intrinsic value)."],
        "pass_when": "At least three of the four answers are right.", "deadline": HAND_IN,
        "given": [_text("Share price", _naira(spot)), _text("Strike", _naira(strike)), _text("Call price, per share", _naira(call)),
                  _text("Interest rate", f"{rate / 100:.2f}% a year"), _text("Trading days left", str(days))],
        "fields": [{"key": "pv", "label": "The strike's value today", "kind": "naira"},
                   {"key": "put", "label": "Put price, per share", "kind": "naira"},
                   {"key": "intrinsic", "label": "Call's intrinsic value", "kind": "naira"},
                   {"key": "time", "label": "Call's time value", "kind": "naira"}],
        "spot": spot, "strike": strike, "call": round(call), "days": days, "rate": rate,
    }


def _parity_submit(ctx, objective, answers):
    t = objective["terms"]
    years = t["days"] / data.GAME_YEAR_REAL_DAYS
    pv = t["strike"] * math.exp(-t["rate"] / BPS * years)
    put = t["call"] - t["spot"] + pv
    intrinsic = max(t["spot"] - t["strike"], 0)
    time_value = t["call"] - intrinsic
    tol = lambda x: max(abs(x) / 100 * 0.005, 0.02)                       # noqa: E731
    return _marked(objective, answers, [("pv", "Strike today", pv / 100, tol(pv)), ("put", "Put", put / 100, tol(put) + 0.02),
                                        ("intrinsic", "Intrinsic value", intrinsic / 100, tol(intrinsic)),
                                        ("time", "Time value", time_value / 100, tol(time_value) + 0.02)], 3,
                   plain=f"The put is worth {_naira(put)} a share. The call's {_naira(t['call'])} is {_naira(intrinsic)} of value it could "
                         f"take now and {_naira(time_value)} for the chance that the share moves before the end.",
                   method="Parity ties a call and a put at the same strike and date: owning the call and lending the strike's value today "
                          "is the same as owning the share and the put. So either price gives the other. If quoted prices break the "
                          "rule, a desk can buy the cheap side and sell the dear one for a profit with no risk.",
                   maths=f"Strike today = {_naira(t['strike'])} × e^(−{t['rate'] / 100:.2f}% × {t['days']}/{data.GAME_YEAR_REAL_DAYS}) = {_naira(pv)}. "
                         f"Put = {_naira(t['call'])} − {_naira(t['spot'])} + {_naira(pv)} = {_naira(put)}.")


# ===========================================================================
# RISK MANAGER: value at risk
# ===========================================================================

Z95 = 1.645


def _var_offer(ctx):
    shares = _shares(ctx)
    share = _draw(ctx, "rm_var", shares)
    if share is None:
        return None
    roll = _roll(ctx["player_id"], "rm_var", ctx["period"])
    vol = (risk.share_risk(ctx["conn"]).get(share["id"]) or {}).get("volatility_bps", round(risk.USUAL_DAILY * math.sqrt(28) * BPS))
    daily_bps = round(vol / math.sqrt(data.GAME_YEAR_REAL_DAYS))
    position = (10_000_000 + (roll % 10) * 10_000_000) * 100
    limit = position * (300 + (roll // 10) % 900) // BPS
    return {
        "situation": f"The empire holds {_naira(position)} of {share['name']} ({share['ticker']}). The board has set a limit on what it may "
                     f"lose in ten trading days, one time in twenty: {_naira(limit)}.",
        "task": [f"From the share's daily swing, work out the one-day value at risk at 95%: {Z95} × the daily swing × the position.",
                 "Scale it to ten days (times the square root of ten), and say whether the position is within the limit."],
        "pass_when": "At least two of the three answers are right.", "deadline": HAND_IN,
        "given": [_given("Position", position), _text("The share's daily swing (from its record)", f"{daily_bps / 100:.2f}%"),
                  _given("The ten-day limit", limit)],
        "fields": [{"key": "var1", "label": "One-day value at risk", "kind": "millions"},
                   {"key": "var10", "label": "Ten-day value at risk", "kind": "millions"},
                   _yes_no("within", "Is it within the limit?")],
        "position": position, "daily_bps": daily_bps, "limit": limit,
    }


def _var_submit(ctx, objective, answers):
    t = objective["terms"]
    var1 = Z95 * t["daily_bps"] / BPS * t["position"]
    var10 = var1 * math.sqrt(10)
    within = var10 <= t["limit"]
    return _marked(objective, answers, [("var1", "One-day", M(var1), 0.05), ("var10", "Ten-day", M(var10), 0.05),
                                        ("within", "Within", "yes" if within else "no", 0)], 2,
                   plain=f"One day in twenty the position could lose {o._money(int(var1))} or more; over ten days, {o._money(int(var10))}. "
                         + ("That is within the limit." if within else "That is beyond the limit: cut the position or protect it."),
                   method="Value at risk says how much could be lost, with a given confidence, over a given time, if the past is a fair "
                          "guide. It grows with the square root of time, not in step with it. It says nothing about how bad the worst "
                          "days are, so it is read together with a stress test of a crash.",
                   maths=f"One day = {Z95} × {t['daily_bps'] / 100:.2f}% × {o._money(t['position'])} = {o._money(int(var1))}. Ten days = "
                         f"{o._money(int(var1))} × √10 = {o._money(int(var10))}.")


# ===========================================================================
# LEGAL COUNSEL: a securities lending agreement (a case file made up for the paper)
# ===========================================================================

def _lending_offer(ctx):
    share = _draw(ctx, "lw_lending", _shares(ctx))
    if share is None:
        return None
    roll = _roll(ctx["player_id"], "lw_lending", ctx["period"])
    shares = (10_000, 20_000, 50_000)[roll % 3]
    start = share["price"]
    rise = (5, 15, 25, 35)[(roll // 3) % 4]
    now_price = start * (100 + rise) // 100
    collateral = shares * start * data.SHORT_COLLATERAL_BPS // BPS
    dividend = (0, 0, 50, 120)[(roll // 13) % 4] * 100
    clauses = [f"Clause 3. The borrower holds cash collateral of at least {data.SHORT_COLLATERAL_BPS // 100}% of the lent shares' value.",
               f"Clause 4. If the collateral falls below {data.SHORT_CALL_BPS // 100}% of their value at a day's close, the borrower must "
               f"restore it to {data.SHORT_COLLATERAL_BPS // 100}% by the next close.",
               "Clause 6. Any dividend paid on the lent shares while they are lent is paid by the borrower to the lender."]
    return {
        "situation": f"A client borrowed {shares:,} {share['ticker']} shares under the agreement below, holding {_naira(collateral)} of "
                     f"cash collateral. The shares have since risen {rise}%" + (f", and a dividend of {_naira(dividend)} a share has been paid."
                                                                                     if dividend else ". No dividend has been paid.")
                     + " (This case file is an exercise made up for the paper.)",
        "task": ["Give the collateral as a percentage of the shares' value now, and say whether the borrower must top it up.",
                 "Give how much cash restores the collateral to the agreed level (nought if none), and what the borrower owes the lender "
                 "for dividends."],
        "pass_when": "At least three of the four answers are right, and whether a top-up is due must be one of them.", "deadline": HAND_IN,
        "given": [_text(f"Clause {n}", c.split(". ", 1)[1]) for n, c in zip((3, 4, 6), clauses)]
                 + [_text("Share price now", _naira(now_price)), _given("Collateral held", collateral)],
        "fields": [{"key": "cover", "label": "Collateral as a share of value now", "kind": "percent"},
                   _yes_no("topup", "Must the borrower top it up?"),
                   {"key": "amount", "label": "Cash to restore it", "kind": "naira"},
                   {"key": "dividend", "label": "Owed for dividends", "kind": "naira"}],
        "shares": shares, "now_price": now_price, "collateral": collateral, "dividend": dividend,
    }


def _lending_submit(ctx, objective, answers):
    t = objective["terms"]
    value = t["shares"] * t["now_price"]
    cover = t["collateral"] / value * 100
    topup = cover < data.SHORT_CALL_BPS / 100
    amount = max(value * data.SHORT_COLLATERAL_BPS / BPS - t["collateral"], 0) if topup else 0
    owed = t["dividend"] * t["shares"]
    return _marked(objective, answers, [("cover", "Cover now", cover, 0.1), ("topup", "Top-up due", "yes" if topup else "no", 0),
                                        ("amount", "To restore", amount / 100, max(amount / 100 * 0.005, 1)),
                                        ("dividend", "Dividends owed", owed / 100, 1)], 3, must=("topup",),
                   plain=f"The collateral is {cover:.1f}% of the shares' value now. " + (f"Below {data.SHORT_CALL_BPS // 100}%: the borrower must add "
                                                                                       f"{_naira(amount)}." if topup else "No top-up is due.")
                         + (f" The borrower owes {_naira(owed)} for the dividend." if owed else ""),
                   method="Read the triggers and the remedies separately: a clause says when something must happen (the call level) and "
                          "what must be done (restore to the agreed level, not merely to the trigger). Measure against today's value of "
                          "what was lent. A borrower of shares owes the lender everything the shares would have paid.",
                   maths=f"Value now = {t['shares']:,} × {_naira(t['now_price'])} = {_naira(value)}. Cover = {_naira(t['collateral'])} ÷ that = {cover:.1f}%.")


# ===========================================================================
# FINANCIAL JOURNALIST: short interest
# ===========================================================================

def _interest_offer(ctx):
    share = _draw(ctx, "jn_short", _shares(ctx))
    if share is None:
        return None
    roll = _roll(ctx["player_id"], "jn_short", ctx["period"])
    issued = (50, 100, 200, 400)[roll % 4] * 1_000_000
    lent = issued * (50 + (roll // 4) % 1200) // 10_000
    volume = issued * (5 + (roll // 41) % 60) // 10_000
    return {
        "situation": f"Your editor wants a short item on how many traders are betting against {share['name']} ({share['ticker']}). The "
                     "exchange publishes the shares lent to short sellers (never who), and the average number traded in a day.",
        "task": ["Give the short interest (shares lent as a share of all shares) and the days to cover (shares lent ÷ the average day's "
                 "trading: how long the short sellers would take to buy them all back).",
                 "Say whether a squeeze is a real risk (days to cover above five) and choose the headline."],
        "pass_when": "At least three of the four answers are right.", "deadline": HAND_IN,
        "given": [_text("Shares in issue", f"{issued:,}"), _text("Shares lent to short sellers", f"{lent:,}"),
                  _text("Average shares traded a day", f"{volume:,}")],
        "fields": [{"key": "interest", "label": "Short interest", "kind": "percent"},
                   {"key": "days", "label": "Days to cover", "kind": "number"},
                   _yes_no("squeeze", "Is a squeeze a real risk?"),
                   {"key": "headline", "label": "Headline", "kind": "choice",
                    "options": [{"code": "bet", "label": "Traders bet heavily against the share"},
                                {"code": "calm", "label": "Few traders bet against the share"}]}],
        "issued": issued, "lent": lent, "volume": volume,
    }


def _interest_submit(ctx, objective, answers):
    t = objective["terms"]
    interest = t["lent"] / t["issued"] * 100
    days = t["lent"] / max(t["volume"], 1)
    squeeze = days > 5
    headline = "bet" if interest >= 5 else "calm"
    return _marked(objective, answers, [("interest", "Short interest", interest, 0.05), ("days", "Days to cover", days, 0.1),
                                        ("squeeze", "Squeeze risk", "yes" if squeeze else "no", 0), ("headline", "Headline", headline, 0)], 3,
                   plain=f"{interest:.2f}% of the shares are sold short; buying them back would take {days:.1f} days of normal trading. "
                         + ("A rise could force a scramble to buy: a squeeze." if squeeze else "They could get out without a scramble."),
                   method="Short interest shows how many are betting on a fall; days to cover shows how hard it would be for them to get "
                          "out. Report both, and never name the sellers: the exchange does not, and a large short is a view, not "
                          "wrongdoing. A headline says 'heavily' only from about 5% of the shares upwards.",
                   maths=f"Short interest = {t['lent']:,} ÷ {t['issued']:,} = {interest:.2f}%. Days to cover = {t['lent']:,} ÷ {t['volume']:,} = {days:.1f}.")


# ===========================================================================
# Into the library
# ===========================================================================

T = o.Template
o.TEMPLATES.update({t.code: t for t in (
    T("am_margin", "asset_manager", "Leverage and margin", "Will the loan bring a margin call?", 3, 80_000, 120, "hand_in",
      "Borrowing against shares multiplies gains and losses; a fall can bring a margin call.", "employer", _margin_offer, submit=_margin_submit),
    T("ac_carry", "asset_manager", "Futures and the cost of carry", "Is the future fairly priced?", 3, 80_000, 120, "hand_in",
      "A future's fair price is today's price carried at the interest rate to the day it settles.", "employer", _carry_offer, submit=_carry_submit),
    T("ib_parity", "investment_banker", "Option pricing", "Price the put from the call", 4, 100_000, 150, "hand_in",
      "A call less a put at the same strike and date is worth the share less the strike's value today.", "employer", _parity_offer,
      submit=_parity_submit),
    T("rm_var", "risk_manager", "Value at risk", "Is the position within its loss limit?", 3, 80_000, 120, "hand_in",
      "Value at risk: how much could be lost, one time in twenty, over a few days, if the past is a fair guide.", "employer", _var_offer,
      submit=_var_submit),
    T("lw_lending", "investment_banker", "Securities lending", "Read the lending agreement after a rise", 3, 80_000, 120, "hand_in",
      "A borrower of shares must keep the collateral up and pay the lender every dividend.", "employer", _lending_offer, submit=_lending_submit),
    T("jn_short", "investment_banker", "Market positioning", "Report the bets against a share", 2, 60_000, 100, "hand_in",
      "Short interest and days to cover show how many bet on a fall, and how hard it would be for them to get out.", "employer",
      _interest_offer, submit=_interest_submit),
)})
