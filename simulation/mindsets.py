"""The ten kinds of people (design document, section 4).

Computer-run people do not all think alike. Each location's households are a
mix of ten mindsets, and the same news draws a different reaction from each.
This module turns what has just happened into how each mindset responds, and
then into how a whole location's households behave.
"""

from __future__ import annotations

from dataclasses import dataclass

from simulation import world_data as data
from simulation.money import BPS


@dataclass(frozen=True)
class Signals:
    """What households can see when they decide how much to spend and borrow."""
    income_change_bps: int = 0          # their own income, last quarter against the one before
    earlier_income_change_bps: int = 0  # the same, one quarter further back
    national_spending_change_bps: int = 0   # what everybody else is visibly doing
    rate_above_neutral_bps: int = 0     # how far the interest rate is above its neutral level
    inflation_bps: int = data.INFLATION_TARGET_BPS
    jobs_change_bps: int = 0            # local jobs, last quarter against the one before
    severe_local_event: bool = False    # a flood, an attack, a disaster in their own location


def _clamp(value: float, low: int, high: int) -> int:
    return int(min(max(value, low), high))


def reactions(s: Signals) -> dict[str, tuple[int, int]]:
    """How each mindset responds: (change in spending, change in willingness to borrow), in hundredths of a percent."""
    prices_running_hot = s.inflation_bps > data.INFLATION_TARGET_BPS + data.INFLATION_BAND_BPS
    frightened = s.severe_local_event or s.jobs_change_bps < -300 or s.inflation_bps > 1500
    return {
        # Expects growth. Spends, invests and borrows more readily.
        "optimistic": (200 + _clamp(s.income_change_bps * 0.3, -100, 300), 3000),
        # Expects decline. Becomes defensive.
        "pessimistic": (-200 + _clamp(s.income_change_bps * 0.3, -300, 100), -3000),
        # Puts safety and ready cash first: saves when rates are high, and after any shock.
        "risk_averse": (_clamp(-s.rate_above_neutral_bps * 0.5, -300, 150) - (300 if s.severe_local_event else 0), -4000),
        # Accepts swings for a chance of higher returns.
        "risk_seeking": (150, 5000),
        # Follows what the crowd is visibly doing.
        "herding": (_clamp(s.national_spending_change_bps * 0.8, -600, 600), _clamp(s.national_spending_change_bps * 4, -3000, 3000)),
        # Goes against the crowd.
        "contrarian": (_clamp(-s.national_spending_change_bps * 0.5, -400, 400), _clamp(-s.national_spending_change_bps * 2, -2000, 2000)),
        # Sticks with familiar companies and brands: steady, and shops close to home (see `loyalty_bps`).
        "loyal": (0, 0),
        # Can panic under severe uncertainty.
        "fearful": (-900 if frightened else 0, -6000 if frightened else 0),
        # Waits for confirmation before acting: responds to what happened two quarters ago.
        "sceptical": (_clamp(s.earlier_income_change_bps * 0.3, -200, 200), -1000),
        # Hunts for bargains: spends when prices are calm, borrows when borrowing is cheap.
        "opportunistic": (-150 if prices_running_hot else 150, _clamp(-s.rate_above_neutral_bps * 10, -3000, 4000)),
    }


def location_response(mix: dict[str, int], signals: Signals) -> dict:
    """How one location's households behave, given their mix of mindsets.

    Returns the change to their spending and to their borrowing (each as a
    multiplier where 10000 is "as usual"), how strongly they favour local
    companies, and which mindset moved them most.
    """
    by_mindset = reactions(signals)
    spend = sum(mix.get(name, 0) * by_mindset[name][0] for name in data.MINDSETS) // BPS
    borrow = sum(mix.get(name, 0) * by_mindset[name][1] for name in data.MINDSETS) // BPS
    strongest = max(data.MINDSETS, key=lambda name: abs(mix.get(name, 0) * by_mindset[name][0]))
    return {
        "spend_bps": BPS + spend,
        "borrow_bps": max(BPS + borrow, 1000),
        # The loyal shop close to home: the more of them, the stronger the local preference.
        "loyalty_bps": data.LOCAL_PREFERENCE_BPS + mix.get("loyal", 0) * 2,
        "moved_most_by": strongest if mix.get(strongest, 0) * by_mindset[strongest][0] != 0 else None,
    }
