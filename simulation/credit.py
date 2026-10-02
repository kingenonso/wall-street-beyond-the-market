"""Credit ratings.

A rating says how safely a company can repay what it owes: AAA is the safest,
D means it has already failed to repay. A weaker rating raises the interest a
company must pay to borrow (design document, section 11).

The rating is worked out from the figures a company FILED, not from the true
record. So from Stage 11, a company that files false accounts can earn a
rating it does not deserve, until someone finds out.

Every rating comes with its reasons in plain words (design law: complex
underneath, clear on top).
"""

from __future__ import annotations

SCALE = ("AAA", "AA", "A", "BBB", "BB", "B", "CCC", "D")

# Total points needed for each rating. Below the last line is CCC.
_BANDS = ((85, "AAA"), (73, "AA"), (61, "A"), (48, "BBB"), (35, "BB"), (22, "B"))


def _points(value: float, steps: tuple[tuple[float, int], ...]) -> int:
    """Points for the first step the value reaches. Steps run from best to worst."""
    return next((points for floor, points in steps if value >= floor), 0)


def _cap(rating: str, ceiling: str) -> str:
    """The weaker of a rating and a ceiling."""
    return ceiling if SCALE.index(rating) < SCALE.index(ceiling) else rating


def rate(figures: dict, trailing: list[dict]) -> tuple[str, list[str]]:
    """Rate a company from its filed figures.

    `figures` is the latest filing. `trailing` is the last few filings that
    cover real trading (up to four quarters, newest last, opening position
    excluded), used so one odd quarter does not swing the rating.
    """
    sheet = figures["balance_sheet"]
    equity = sheet["total_equity"]
    assets = sheet["total_assets"]
    borrowings = sheet["borrowings"]

    # Failures first. These override everything else.
    if figures["notes"]["principal_overdue"] > 0:
        return "D", ["Debt that has passed its repayment date is still unpaid."]
    if equity <= 0 or assets <= 0:
        return "D", ["It owes more than everything it owns."]

    reasons: list[str] = []
    points = 0

    financial = sheet["customer_funds"] > 0      # banks and insurers hold other people's money

    # 1. How much of the business is funded by debt (up to 30 points).
    if financial:
        # For a bank or insurer the test is the owners' cushion against losses.
        cushion = equity / assets
        points += _points(cushion, ((0.30, 30), (0.22, 24), (0.15, 16), (0.10, 8)))
        reasons.append(f"Owners' funds are {cushion:.0%} of everything it holds.")
    elif borrowings == 0:
        points += 30
        reasons.append("It has no borrowings.")
    else:
        gearing = borrowings / equity
        points += 27 if gearing <= 0.15 else 22 if gearing <= 0.3 else 15 if gearing <= 0.6 else 8 if gearing <= 1.2 else 2
        reasons.append(f"It has borrowed {gearing:.2f} naira for each naira of owners' funds.")

    # 2. Can it meet its obligations? (up to 30 points for trading companies)
    if financial:
        # Could it hand customers their money back if they asked?
        ready = sheet["cash"] / sheet["customer_funds"]
        points += _points(ready, ((0.6, 28), (0.4, 22), (0.25, 16), (0.12, 8)))
        reasons.append(f"It holds {ready:.0%} of its customers' money in ready cash.")

    if not trailing:
        # No trading yet: judge on the balance sheet alone, and say so.
        points += (0 if financial else 15) + 10 + 10
        reasons.append("It has no trading history yet, so this rating rests on its balance sheet alone.")
    else:
        income = [f["income_statement"] for f in trailing]
        operating_profit = sum(i["operating_profit"] for i in income)
        interest = sum(i["interest_expense"] for i in income)
        earned = sum(i["revenue"] + i["interest_income"] for i in income)
        net_profit = sum(i["net_profit"] for i in income)

        if not financial:
            if interest == 0:
                points += 30
            else:
                cover = operating_profit / interest
                points += _points(cover, ((12, 28), (8, 24), (5, 18), (3, 10), (1.5, 5)))
                if cover >= 1:
                    reasons.append(f"Profit covers its interest bill {cover:.1f} times.")
                else:
                    reasons.append("Profit does not cover its interest bill.")

        # 3. Does it make money? (up to 20 points)
        margin = net_profit / earned if earned > 0 else -1.0
        points += _points(margin, ((0.20, 20), (0.12, 16), (0.07, 11), (0.03, 6), (0.0, 3)))
        if margin >= 0:
            reasons.append(f"It keeps {margin * 100:.0f} kobo of every naira it earns as profit.")
        else:
            reasons.append("It is making a loss.")

        # 4. Can it pay its bills from cash? (up to 20 points)
        latest = income[-1]
        quarterly_costs = latest["operating_expenses"] + latest["interest_expense"]
        quarters = sheet["cash"] / quarterly_costs if quarterly_costs > 0 else 99.0
        points += _points(quarters, ((4, 20), (2.5, 15), (1.5, 10), (0.75, 5)))
        reasons.append(f"Cash would cover {min(quarters, 99):.1f} quarters of running costs and interest.")

    rating = next((name for floor, name in _BANDS if points >= floor), "CCC")

    # EBITDA: what the business itself produces before interest, tax and wear.
    if trailing:
        yearly_ebitda = sum(i.get("ebitda", i["operating_profit"] + i["depreciation"]) for i in income) * 4 // len(income)
        if yearly_ebitda <= 0:
            # A business that produces nothing cannot be highly rated, debts or no debts.
            if borrowings > 0 and not financial:
                rating = _cap(rating, "CCC")
                reasons.append("Its business produces no cash before interest and tax (EBITDA), yet it has debts to service.")
            else:
                rating = _cap(rating, "B")
                reasons.append("Its business produces no cash before interest and tax (EBITDA).")
        elif borrowings > 0 and not financial:
            # How many years of EBITDA it would take to repay everything it has borrowed.
            years = borrowings / yearly_ebitda
            reasons.append(f"Its borrowings equal {years:.1f} years of EBITDA.")
            if years > 6:
                rating = _cap(rating, "B")
            elif years > 4:
                rating = _cap(rating, "BB")

    # A missed loan repayment is one step from default.
    if figures["notes"].get("repayments_missed", 0) > 0:
        rating = _cap(rating, "CCC")
        reasons.insert(0, "It missed a loan repayment that fell due this quarter.")

    # Unpaid bills cap the rating, however strong the rest looks.
    if sheet["payables"] > 0 and SCALE.index(rating) < SCALE.index("CCC"):
        rating = "CCC"
        reasons.insert(0, "It has bills it could not pay on time.")

    return rating, reasons
